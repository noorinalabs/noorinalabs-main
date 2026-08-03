"""Tests for wave_state — the shared cross-repo-status.json reader (main#1119).

The consolidation this file guards is almost entirely PLUMBING, so these tests
aim at the hand-offs rather than at arithmetic:

  1. The cache can never serve stale data. Four rewrite shapes, each defeating
     a DIFFERENT component of the stat key, so deleting any one component
     fails a test:
       * different size          -> st_size
       * SAME size, later mtime  -> st_mtime_ns
       * atomic rename, OLDER mtime -> st_ino/st_dev
       * same-tick rewrite with a byte-identical stat key -> the racy-tick guard
  2. The cache actually engages (otherwise every invalidation test above would
     pass vacuously, on a loader that never cached anything at all).
  3. The mapping handed back is not mutated by any caller in this package.
  4. The `--status` argparse block and `read_repos` behave as the six/two
     copies they replaced did.
  5. Writes still go through the text-surgical path — `upsert_status_keys`
     neither imports this module nor reformats the file.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

# Helpers live at .claude/lib/*.py; this test is at .claude/lib/tests/test_*.py.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gh  # noqa: E402
import upsert_status_keys  # noqa: E402
import wave_merge_model  # noqa: E402
import wave_state  # noqa: E402
import wave_status  # noqa: E402

_ONE_SECOND_NS = 1_000_000_000


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload))


def _pin_mtime(path: Path, mtime_ns: int) -> None:
    """Force an exact mtime, so a coarse-granularity filesystem can be simulated."""
    os.utime(path, ns=(mtime_ns, mtime_ns))


class _CacheIsolated(unittest.TestCase):
    """Every test starts from an empty cache and zeroed counters."""

    def setUp(self) -> None:
        wave_state.invalidate()
        wave_state.reset_cache_info()
        self.addCleanup(wave_state.invalidate)
        self.addCleanup(wave_state.reset_cache_info)


class TickSettledPredicate(_CacheIsolated):
    """The racy-tick guard in isolation (module docstring § racy-tick guard)."""

    def test_subsecond_bits_imply_a_one_nanosecond_tick(self) -> None:
        mtime = 5 * _ONE_SECOND_NS + 12345  # has sub-second bits
        self.assertTrue(wave_state._tick_has_settled(mtime, mtime + 1))

    def test_subsecond_timestamp_equal_to_now_is_not_settled(self) -> None:
        mtime = 5 * _ONE_SECOND_NS + 12345
        self.assertFalse(wave_state._tick_has_settled(mtime, mtime))

    def test_exact_second_is_treated_as_a_one_second_tick(self) -> None:
        mtime = 5 * _ONE_SECOND_NS
        # Half a second later the tick could still absorb another write.
        self.assertFalse(wave_state._tick_has_settled(mtime, mtime + _ONE_SECOND_NS // 2))
        # A full second later nothing can reproduce this timestamp.
        self.assertTrue(wave_state._tick_has_settled(mtime, mtime + _ONE_SECOND_NS))

    def test_future_dated_file_is_never_settled(self) -> None:
        """Clock skew (network mounts) must not unlock caching."""
        mtime = 10 * _ONE_SECOND_NS + 7
        self.assertFalse(wave_state._tick_has_settled(mtime, mtime - _ONE_SECOND_NS))


class CacheEngages(_CacheIsolated):
    """Without this, every invalidation test below would pass vacuously."""

    def test_repeated_loads_of_a_settled_file_parse_once(self) -> None:
        with TemporaryDirectory() as td:
            path = Path(td) / "cross-repo-status.json"
            _write(path, {"current_wave": "wave-29"})
            _pin_mtime(path, 1_000 * _ONE_SECOND_NS + 5)

            with mock.patch.object(wave_state, "_now_ns", lambda: 2_000 * _ONE_SECOND_NS):
                for _ in range(5):
                    self.assertEqual(wave_state.load_status(path)["current_wave"], "wave-29")

            info = wave_state.cache_info()
            self.assertEqual(info.parses, 1, "cache did not engage — perf claim is unmet")
            self.assertEqual(info.hits, 4)

    def test_hits_are_the_identical_object_not_a_reparse(self) -> None:
        with TemporaryDirectory() as td:
            path = Path(td) / "cross-repo-status.json"
            _write(path, {"a": 1})
            _pin_mtime(path, 1_000 * _ONE_SECOND_NS + 5)
            with mock.patch.object(wave_state, "_now_ns", lambda: 2_000 * _ONE_SECOND_NS):
                first = wave_state.load_status(path)
                second = wave_state.load_status(path)
            self.assertIs(first, second)

    def test_distinct_paths_are_cached_independently(self) -> None:
        with TemporaryDirectory() as td:
            a = Path(td) / "a.json"
            b = Path(td) / "b.json"
            _write(a, {"which": "a"})
            _write(b, {"which": "b"})
            _pin_mtime(a, 1_000 * _ONE_SECOND_NS + 5)
            _pin_mtime(b, 1_000 * _ONE_SECOND_NS + 5)
            with mock.patch.object(wave_state, "_now_ns", lambda: 2_000 * _ONE_SECOND_NS):
                self.assertEqual(wave_state.load_status(a)["which"], "a")
                self.assertEqual(wave_state.load_status(b)["which"], "b")
                self.assertEqual(wave_state.load_status(a)["which"], "a")


class CacheInvalidationOnRewrite(_CacheIsolated):
    """THE load-bearing suite: a rewritten file is never served from cache.

    Each test defeats a different component of the stat key, so no single
    component can be deleted without a failure here.
    """

    def test_rewrite_changing_size_is_seen(self) -> None:
        with TemporaryDirectory() as td:
            path = Path(td) / "cross-repo-status.json"
            _write(path, {"current_wave": "wave-29"})
            _pin_mtime(path, 1_000 * _ONE_SECOND_NS + 5)
            with mock.patch.object(wave_state, "_now_ns", lambda: 2_000 * _ONE_SECOND_NS):
                self.assertEqual(wave_state.load_status(path)["current_wave"], "wave-29")
                _write(path, {"current_wave": "wave-30", "extra": [1, 2, 3]})
                _pin_mtime(path, 1_500 * _ONE_SECOND_NS + 5)
                self.assertEqual(wave_state.load_status(path)["current_wave"], "wave-30")

    def test_rewrite_preserving_size_is_seen(self) -> None:
        """The counter-flip case: `5` -> `6` keeps the byte length identical.

        Size alone cannot catch this; only st_mtime_ns can. cross-repo-status
        .json is full of single-digit counters, so this is the realistic shape.
        """
        with TemporaryDirectory() as td:
            path = Path(td) / "cross-repo-status.json"
            _write(path, {"wave_29_final_pr_count": 5})
            before = path.stat().st_size
            _pin_mtime(path, 1_000 * _ONE_SECOND_NS + 5)
            with mock.patch.object(wave_state, "_now_ns", lambda: 3_000 * _ONE_SECOND_NS):
                self.assertEqual(wave_state.load_status(path)["wave_29_final_pr_count"], 5)

                _write(path, {"wave_29_final_pr_count": 6})
                _pin_mtime(path, 1_500 * _ONE_SECOND_NS + 5)
                self.assertEqual(path.stat().st_size, before, "fixture must be same-size")

                self.assertEqual(wave_state.load_status(path)["wave_29_final_pr_count"], 6)

    def test_rewrite_changing_only_the_size_is_seen(self) -> None:
        """Isolates st_size: mtime and inode are held IDENTICAL across the two
        writes, so nothing but the length can distinguish them. The realistic
        shape is a coarse-granularity filesystem where both writes land in the
        same second."""
        pinned = 4_000 * _ONE_SECOND_NS + 5
        with TemporaryDirectory() as td:
            path = Path(td) / "cross-repo-status.json"
            _write(path, {"current_wave": "wave-29"})
            _pin_mtime(path, pinned)
            ino_before = path.stat().st_ino

            with mock.patch.object(wave_state, "_now_ns", lambda: 9_000 * _ONE_SECOND_NS):
                self.assertEqual(wave_state.load_status(path)["current_wave"], "wave-29")

                _write(path, {"current_wave": "wave-29", "added": "a longer payload"})
                _pin_mtime(path, pinned)  # same mtime
                self.assertEqual(path.stat().st_ino, ino_before)  # same inode

                self.assertEqual(wave_state.load_status(path).get("added"), "a longer payload")

    def test_atomic_replace_with_identical_size_and_mtime_is_seen(self) -> None:
        """Isolates st_ino/st_dev: size AND mtime are held identical across an
        atomic rename, so only the inode can reveal the swap.

        Contrast with `test_identical_stat_key_after_a_settled_tick_...`, which
        performs the same size/mtime-preserving swap IN PLACE (inode unchanged)
        and legitimately serves cache. The pair is what pins the inode's role.
        """
        pinned = 5_000 * _ONE_SECOND_NS + 5
        with TemporaryDirectory() as td:
            path = Path(td) / "cross-repo-status.json"
            tmp = Path(td) / "staged.json"
            _write(path, {"wave_29_final_pr_count": 5})
            _pin_mtime(path, pinned)
            ino_before = path.stat().st_ino

            with mock.patch.object(wave_state, "_now_ns", lambda: 9_000 * _ONE_SECOND_NS):
                self.assertEqual(wave_state.load_status(path)["wave_29_final_pr_count"], 5)

                _write(tmp, {"wave_29_final_pr_count": 6})
                _pin_mtime(tmp, pinned)
                self.assertEqual(tmp.stat().st_size, path.stat().st_size)
                os.replace(tmp, path)
                self.assertNotEqual(path.stat().st_ino, ino_before)
                self.assertEqual(path.stat().st_mtime_ns, pinned)

                self.assertEqual(wave_state.load_status(path)["wave_29_final_pr_count"], 6)

    def test_atomic_replace_with_an_older_mtime_is_seen(self) -> None:
        """write-temp + rename, where the replacement is BACK-dated.

        Neither size nor mtime need move forward here — a rename can install a
        file whose timestamp is older than the one we cached. Only the inode
        catches it.
        """
        with TemporaryDirectory() as td:
            path = Path(td) / "cross-repo-status.json"
            tmp = Path(td) / "staged.json"
            _write(path, {"current_wave": "wave-29"})
            _pin_mtime(path, 5_000 * _ONE_SECOND_NS + 5)

            with mock.patch.object(wave_state, "_now_ns", lambda: 9_000 * _ONE_SECOND_NS):
                self.assertEqual(wave_state.load_status(path)["current_wave"], "wave-29")

                _write(tmp, {"current_wave": "wave-30"})
                _pin_mtime(tmp, 1_000 * _ONE_SECOND_NS + 5)  # OLDER than the cached entry
                self.assertEqual(tmp.stat().st_size, path.stat().st_size)
                os.replace(tmp, path)

                self.assertEqual(wave_state.load_status(path)["current_wave"], "wave-30")

    def test_same_tick_rewrite_on_a_coarse_filesystem_is_seen(self) -> None:
        """The aliasing case the racy-tick guard exists for.

        Simulates a 1-second-granularity filesystem: both writes are pinned to
        the SAME exact-second mtime and produce the SAME size, so the stat key
        is byte-identical across them. The only thing that can save the reader
        is refusing to cache a timestamp whose tick has not settled.

        Delete the `_tick_has_settled` call from `load_status` and this test
        fails with the stale value — which is the whole point of it.
        """
        tick = 4_000 * _ONE_SECOND_NS  # exact second => coarse-FS shape
        with TemporaryDirectory() as td:
            path = Path(td) / "cross-repo-status.json"
            _write(path, {"wave_29_final_pr_count": 5})
            _pin_mtime(path, tick)

            # "now" is inside the same second as the write: unsettled.
            with mock.patch.object(wave_state, "_now_ns", lambda: tick + _ONE_SECOND_NS // 2):
                self.assertEqual(wave_state.load_status(path)["wave_29_final_pr_count"], 5)

                _write(path, {"wave_29_final_pr_count": 6})
                _pin_mtime(path, tick)

                key_repeated = wave_state._stat_key(path.stat())
                self.assertEqual(key_repeated.mtime_ns, tick)

                self.assertEqual(
                    wave_state.load_status(path)["wave_29_final_pr_count"],
                    6,
                    "served a stale parse across an indistinguishable stat key",
                )
            self.assertGreater(wave_state.cache_info().uncacheable, 0)

    def test_identical_stat_key_after_a_settled_tick_is_the_documented_boundary(self) -> None:
        """Pins WHY the guard is required, by showing what happens without it.

        Once a tick has settled, an identical stat key is taken as proof the
        file is unchanged — so a forcibly back-dated rewrite IS served from
        cache. That is not a bug to fix at this layer (a settled tick genuinely
        cannot recur without someone forging timestamps); it is precisely the
        reason `load_status` refuses to cache an UNSETTLED tick, which is the
        only window in which this can happen for real.
        """
        old = 1_000 * _ONE_SECOND_NS + 5
        with TemporaryDirectory() as td:
            path = Path(td) / "cross-repo-status.json"
            _write(path, {"wave_29_final_pr_count": 5})
            _pin_mtime(path, old)
            with mock.patch.object(wave_state, "_now_ns", lambda: 8_000 * _ONE_SECOND_NS):
                self.assertEqual(wave_state.load_status(path)["wave_29_final_pr_count"], 5)
                _write(path, {"wave_29_final_pr_count": 6})
                _pin_mtime(path, old)  # forge the ORIGINAL timestamp back on
                self.assertEqual(wave_state.load_status(path)["wave_29_final_pr_count"], 5)
                # ...and an explicit invalidate is the escape hatch for it.
                wave_state.invalidate(path)
                self.assertEqual(wave_state.load_status(path)["wave_29_final_pr_count"], 6)

    def test_write_through_upsert_status_keys_is_seen_by_a_later_load(self) -> None:
        """End-to-end: the real writer, then a real read, in one process.

        This is the shape that actually occurs (`wave_status counters --write`,
        every `lifecycle` transition) and the one a cache could plausibly break.
        No `invalidate()` call anywhere — the reader must notice on its own.
        """
        with TemporaryDirectory() as td:
            path = Path(td) / "cross-repo-status.json"
            # Multi-line, compact-inline — the real file's shape. The writer is
            # text-surgical, so it needs real line structure to edit.
            path.write_text('{\n  "current_wave": "wave-29",\n  "wave_29_final_pr_count": 5\n}\n')

            self.assertEqual(wave_state.load_status(path)["wave_29_final_pr_count"], 5)
            rc = upsert_status_keys.main(["t", str(path), "wave_29_final_pr_count=6"])
            self.assertEqual(rc, 0)
            self.assertEqual(wave_state.load_status(path)["wave_29_final_pr_count"], 6)

    def test_invalidate_all_drops_every_path(self) -> None:
        with TemporaryDirectory() as td:
            a = Path(td) / "a.json"
            _write(a, {"v": 1})
            _pin_mtime(a, 1_000 * _ONE_SECOND_NS + 5)
            with mock.patch.object(wave_state, "_now_ns", lambda: 5_000 * _ONE_SECOND_NS):
                wave_state.load_status(a)
                self.assertEqual(wave_state.cache_info().parses, 1)
                wave_state.invalidate()
                wave_state.load_status(a)
                self.assertEqual(wave_state.cache_info().parses, 2)


class LoaderBehaviourIsUnchanged(_CacheIsolated):
    """The loader must be a drop-in for `json.loads(path.read_text())`."""

    def test_matches_a_direct_parse(self) -> None:
        with TemporaryDirectory() as td:
            path = Path(td) / "cross-repo-status.json"
            payload = {"current_wave": "wave-29", "nested": {"a": [1, 2]}, "n": None}
            _write(path, payload)
            self.assertEqual(wave_state.load_status(path), json.loads(path.read_text()))

    def test_missing_file_raises_oserror(self) -> None:
        with TemporaryDirectory() as td:
            with self.assertRaises(OSError):
                wave_state.load_status(Path(td) / "absent.json")

    def test_malformed_json_raises_decode_error(self) -> None:
        with TemporaryDirectory() as td:
            path = Path(td) / "cross-repo-status.json"
            path.write_text("{not json")
            with self.assertRaises(json.JSONDecodeError):
                wave_state.load_status(path)

    def test_accepts_a_str_path(self) -> None:
        """wave_unwrapped's copy coerced with `Path(...)`; str input must work."""
        with TemporaryDirectory() as td:
            path = Path(td) / "cross-repo-status.json"
            _write(path, {"current_wave": "wave-29"})
            self.assertEqual(wave_state.load_status(str(path))["current_wave"], "wave-29")

    def test_str_and_path_spellings_share_one_cache_entry(self) -> None:
        with TemporaryDirectory() as td:
            path = Path(td) / "cross-repo-status.json"
            _write(path, {"v": 1})
            _pin_mtime(path, 1_000 * _ONE_SECOND_NS + 5)
            with mock.patch.object(wave_state, "_now_ns", lambda: 5_000 * _ONE_SECOND_NS):
                wave_state.load_status(path)
                wave_state.load_status(str(path))
            self.assertEqual(wave_state.cache_info().parses, 1)


class SharedMappingIsNotMutated(_CacheIsolated):
    """The cache hands back the real object; nothing in this package may mutate it."""

    def test_public_read_apis_leave_the_mapping_untouched(self) -> None:
        payload = {
            "current_wave": "wave-29",
            "current_phase": "10",
            "next_wave": "wave-30",
            "wave_29_repos_in_scope": ["repo-a", "repo-b"],
            "wave_29_merge_model": "direct-to-main",
            "wave_29_kicked_off_at": "2026-08-01T00:00:00Z",
            "owner_decision_gated": ["something"],
            "phase_10_note": "x",
        }
        with TemporaryDirectory() as td:
            path = Path(td) / "cross-repo-status.json"
            _write(path, payload)
            _pin_mtime(path, 1_000 * _ONE_SECOND_NS + 5)

            with mock.patch.object(wave_state, "_now_ns", lambda: 5_000 * _ONE_SECOND_NS):
                loaded = wave_state.load_status(path)
                snapshot = json.loads(json.dumps(loaded))

                wave_status.build_digest(path)
                wave_status.read_repos("29", path)
                wave_merge_model.read_repos("29", path)
                wave_merge_model.read_merge_model("29", path)

                self.assertEqual(loaded, snapshot, "a read API mutated the shared mapping")
                # And the cache is still handing back that same object.
                self.assertIs(wave_state.load_status(path), loaded)


class ReadRepos(_CacheIsolated):
    """The contract the two verbatim copies had, now asserted once."""

    def _path(self, td: str, payload: dict) -> Path:
        path = Path(td) / "cross-repo-status.json"
        _write(path, payload)
        return path

    def test_returns_the_scope_list(self) -> None:
        with TemporaryDirectory() as td:
            path = self._path(td, {"wave_29_repos_in_scope": ["repo-a", "repo-b"]})
            self.assertEqual(wave_state.read_repos("29", path), ["repo-a", "repo-b"])

    def test_missing_key_raises_keyerror(self) -> None:
        with TemporaryDirectory() as td:
            path = self._path(td, {"current_wave": "wave-29"})
            with self.assertRaises(KeyError):
                wave_state.read_repos("29", path)

    def test_non_list_value_raises_typeerror(self) -> None:
        with TemporaryDirectory() as td:
            path = self._path(td, {"wave_29_repos_in_scope": "repo-a"})
            with self.assertRaises(TypeError):
                wave_state.read_repos("29", path)

    def test_entries_are_coerced_to_str(self) -> None:
        with TemporaryDirectory() as td:
            path = self._path(td, {"wave_29_repos_in_scope": [1, "b"]})
            self.assertEqual(wave_state.read_repos("29", path), ["1", "b"])

    def test_wave_prefix_does_not_match_a_longer_ordinal(self) -> None:
        """`wave_2_` must not resolve against `wave_29_` (the #804 key class)."""
        with TemporaryDirectory() as td:
            path = self._path(td, {"wave_29_repos_in_scope": ["repo-a"]})
            with self.assertRaises(KeyError):
                wave_state.read_repos("2", path)

    def test_both_module_spellings_are_the_one_function(self) -> None:
        self.assertIs(wave_status.read_repos, wave_state.read_repos)
        self.assertIs(wave_merge_model.read_repos, wave_state.read_repos)


class StatusArgument(_CacheIsolated):
    """The `--status` block that had drifted into six copies."""

    def test_defaults_to_the_repo_root_copy(self) -> None:
        parser = argparse.ArgumentParser()
        wave_state.add_status_argument(parser)
        self.assertEqual(parser.parse_args([]).status, wave_state.DEFAULT_STATUS_PATH)

    def test_parses_an_explicit_value_as_a_path(self) -> None:
        parser = argparse.ArgumentParser()
        wave_state.add_status_argument(parser)
        parsed = parser.parse_args(["--status", "/tmp/x.json"])
        self.assertIsInstance(parsed.status, Path)
        self.assertEqual(parsed.status, Path("/tmp/x.json"))

    def test_default_path_points_at_cross_repo_status_json(self) -> None:
        self.assertEqual(wave_state.DEFAULT_STATUS_PATH.name, "cross-repo-status.json")
        self.assertEqual(wave_state.DEFAULT_STATUS_PATH.parent, wave_state.REPO_ROOT)

    def test_every_consolidated_module_shares_the_one_default(self) -> None:
        import kickoff_sweep
        import lifecycle
        import trust_signals
        import wave_seq
        import wave_unwrapped

        for mod in (
            wave_status,
            wave_merge_model,
            wave_unwrapped,
            lifecycle,
            wave_seq,
            trust_signals,
            kickoff_sweep,
        ):
            with self.subTest(module=mod.__name__):
                self.assertIs(mod._DEFAULT_STATUS, wave_state.DEFAULT_STATUS_PATH)


class WritesStayTextSurgical(_CacheIsolated):
    """main#1119 must not have started routing writes through the loader."""

    def test_upsert_status_keys_does_not_import_wave_state(self) -> None:
        source = (Path(wave_state.__file__).parent / "upsert_status_keys.py").read_text()
        self.assertNotIn("wave_state", source)

    def test_compact_inline_shape_survives_a_write(self) -> None:
        """A json.dumps round-trip would reformat these lines; assert it doesn't."""
        original = (
            "{\n"
            '  "current_wave": "wave-29",\n'
            '  "wave_29_repos_in_scope": ["repo-a", "repo-b"],\n'
            '  "wave_29_final_pr_count": 5\n'
            "}\n"
        )
        with TemporaryDirectory() as td:
            path = Path(td) / "cross-repo-status.json"
            path.write_text(original)

            rc = upsert_status_keys.main(["t", str(path), "wave_29_final_pr_count=6"])
            self.assertEqual(rc, 0)

            after = path.read_text()
            self.assertIn('"wave_29_repos_in_scope": ["repo-a", "repo-b"],', after)
            self.assertEqual(
                len(original.splitlines()),
                len(after.splitlines()),
                "the write reflowed the file — the compact-inline shape was lost",
            )

    def test_counters_write_path_preserves_shape_and_is_read_back(self) -> None:
        """wave_status --write is the real caller; prove both halves at once."""
        original = (
            "{\n"
            '  "current_wave": "wave-29",\n'
            '  "wave_29_repos_in_scope": ["repo-a"],\n'
            '  "wave_29_final_pr_count": 1,\n'
            '  "wave_29_changes_requested_cycles": 1,\n'
            '  "wave_29_top_concentration_pct": 1\n'
            "}\n"
        )
        with TemporaryDirectory() as td:
            path = Path(td) / "cross-repo-status.json"
            path.write_text(original)

            self.assertEqual(wave_state.load_status(path)["wave_29_final_pr_count"], 1)
            rc = wave_status._write_counters(
                "29",
                {
                    "final_pr_count": 7,
                    "changes_requested_cycles": 2,
                    "top_concentration_pct": 43,
                },
                path,
            )
            self.assertEqual(rc, 0)

            after = path.read_text()
            self.assertEqual(len(original.splitlines()), len(after.splitlines()))
            self.assertIn('"wave_29_repos_in_scope": ["repo-a"],', after)
            self.assertEqual(wave_state.load_status(path)["wave_29_final_pr_count"], 7)


class GhShim(unittest.TestCase):
    """gh.run_gh — the six-way-identical `_run_gh`, and its error contract."""

    def test_invokes_gh_with_an_explicit_arg_list_and_no_shell(self) -> None:
        seen: dict = {}

        def fake(cmd, *a, **kw):
            seen["cmd"] = cmd
            seen["kwargs"] = kw
            return subprocess.CompletedProcess(cmd, 0, stdout="out", stderr="")

        with mock.patch.object(subprocess, "run", fake):
            self.assertEqual(gh.run_gh(["pr", "list", "--repo", "o/r"]), "out")

        self.assertIsInstance(seen["cmd"], list)
        self.assertEqual(seen["cmd"], ["gh", "pr", "list", "--repo", "o/r"])
        self.assertIsNot(seen["kwargs"].get("shell"), True)
        self.assertTrue(seen["kwargs"].get("check"))
        self.assertTrue(seen["kwargs"].get("capture_output"))
        self.assertTrue(seen["kwargs"].get("text"))

    def test_a_multiword_value_stays_one_argv_element(self) -> None:
        """The main#688 regression: a joined repo list must not word-split."""
        seen: dict = {}

        def fake(cmd, *a, **kw):
            seen["cmd"] = cmd
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        joined = "repo-a repo-b repo-c"
        with mock.patch.object(subprocess, "run", fake):
            gh.run_gh(["pr", "list", "--repo", joined])
        self.assertIn(joined, seen["cmd"])
        self.assertEqual(len(seen["cmd"]), 5)

    def test_nonzero_exit_propagates_raw_calledprocesserror(self) -> None:
        """NOT wrapped in GhError — `red_sweep`/`base_pin_drift_sweep` catch the
        raw type to degrade gracefully, so wrapping would turn a graceful
        degrade into an unhandled traceback (gh.py § Error behaviour)."""

        def fake(cmd, *a, **kw):
            raise subprocess.CalledProcessError(1, cmd, stderr="boom")

        with mock.patch.object(subprocess, "run", fake):
            with self.assertRaises(subprocess.CalledProcessError):
                gh.run_gh(["pr", "list"])

    def test_missing_gh_binary_propagates_raw_filenotfounderror(self) -> None:
        def fake(cmd, *a, **kw):
            raise FileNotFoundError("gh")

        with mock.patch.object(subprocess, "run", fake):
            with self.assertRaises(FileNotFoundError):
                gh.run_gh(["pr", "list"])

    def test_red_sweeps_error_tuple_still_matches_what_run_gh_raises(self) -> None:
        """The exact `except` clause that a wrapped error would have broken."""
        import red_sweep

        def fake(cmd, *a, **kw):
            raise subprocess.CalledProcessError(1, cmd, stderr="boom")

        with mock.patch.object(subprocess, "run", fake):
            try:
                gh.run_gh(["pr", "list"])
            except red_sweep._GH_ERRORS:
                pass
            else:
                self.fail("red_sweep._GH_ERRORS no longer catches a gh failure")

    def test_every_consolidated_module_shares_the_one_shim(self) -> None:
        import kickoff_sweep
        import red_sweep
        import wave_unwrapped

        for mod in (wave_status, wave_merge_model, wave_unwrapped, red_sweep, kickoff_sweep):
            with self.subTest(module=mod.__name__):
                self.assertIs(mod._run_gh, gh.run_gh)

    def test_verify_deployable_merge_reuses_the_one_gherror(self) -> None:
        import verify_deployable_merge

        self.assertIs(verify_deployable_merge.GhError, gh.GhError)

    def test_verify_deployable_merge_still_wraps_failures(self) -> None:
        """Its wrapper is its OWN behaviour and must survive the consolidation."""
        import verify_deployable_merge

        def fake(cmd, *a, **kw):
            raise subprocess.CalledProcessError(1, cmd, stderr="boom")

        with mock.patch.object(subprocess, "run", fake):
            with self.assertRaises(gh.GhError):
                verify_deployable_merge._run_gh(["api", "x"])

    def test_gh_rest_shim_is_deliberately_not_the_shared_one(self) -> None:
        """Its different contract (timeout, GhRestError) is load-bearing (#1224)."""
        import gh_rest

        self.assertIsNot(gh_rest._run_gh, gh.run_gh)


if __name__ == "__main__":
    unittest.main()
