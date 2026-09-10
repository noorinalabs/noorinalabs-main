"""Tests for checksums_io — the shared ontology/checksums.json read/write helper (#1042).

Closes the gap left by #1040 (which fixed the ensure_ascii=True re-escaping
churn only in the one code-enforced writer, ontology_tracker.py, leaving the
agent-driven /ontology-rebuild resolver's serialization a documentation-only
convention with nothing to attach a test to). This module gives the resolver
a real CLI subcommand (`mark-resolved`) to shell out to instead, so the
byte-stability contract is enforced by code on BOTH writers, not just one.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import checksums_io  # noqa: E402


@contextmanager
def _tmp_file(contents: str):
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "checksums.json"
        path.write_text(contents, encoding="utf-8")
        yield path


@contextmanager
def _tmp_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@contextmanager
def _capture_stdout():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        yield buf


@contextmanager
def _capture_stderr():
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        yield buf


# --- #1505 helpers -----------------------------------------------------------
# The pre-#1505 tests seeded ledgers describing files that were never created,
# because nothing ever opened them. Now that the reader hashes, an entry has to
# be paired with a real file for its state to mean anything — a ledger entry
# with no file on disk is UNDETERMINABLE, which is a legitimate state but not
# the one those tests were about.


def _materialize(root: Path, rel: str, contents: str) -> str:
    """Write a real file under ``root`` and return its sha256 hex digest."""
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")
    return hashlib.sha256(contents.encode("utf-8")).hexdigest()


def _clean_entry(root: Path, rel: str, contents: str = "content\n") -> dict[str, str]:
    """An entry clean on BOTH predicates: the stored values agree with each
    other AND with the file that is actually on disk."""
    sha = _materialize(root, rel, contents)
    return {"last_tracked": sha, "last_resolved": sha}


def _drifted_entry(root: Path, rel: str, contents: str = "changed by a merge\n") -> dict[str, str]:
    """THE #1505 shape, and the one the old predicate calls clean.

    The two stored values agree with each other — so `last_tracked !=
    last_resolved` is False and the entry reports clean — and neither agrees
    with the file, which has moved on by some route that is not an Edit/Write
    in this checkout. 158 of 314 real entries were in this state.
    """
    _materialize(root, rel, contents)
    stale = hashlib.sha256(b"what the file used to contain").hexdigest()
    return {"last_tracked": stale, "last_resolved": stale}


class ReadChecksumsTests(unittest.TestCase):
    def test_reads_valid_json(self) -> None:
        with _tmp_file('{"version": 1, "files": {"a.yaml": {"last_tracked": "x"}}}') as path:
            data = checksums_io.read_checksums(path)
        self.assertEqual(data["files"]["a.yaml"]["last_tracked"], "x")

    def test_missing_file_returns_empty_default(self) -> None:
        missing = Path("/nonexistent/path/checksums.json")
        data = checksums_io.read_checksums(missing)
        self.assertEqual(data, {"version": 1, "files": {}})

    def test_invalid_json_returns_empty_default(self) -> None:
        with _tmp_file("{not valid json") as path:
            data = checksums_io.read_checksums(path)
        self.assertEqual(data, {"version": 1, "files": {}})

    def test_non_dict_json_returns_empty_default(self) -> None:
        """A JSON array (or any non-mapping) is not a valid checksums document."""
        with _tmp_file("[1, 2, 3]") as path:
            data = checksums_io.read_checksums(path)
        self.assertEqual(data, {"version": 1, "files": {}})

    def test_missing_file_default_does_not_alias_module_global(self) -> None:
        """The fail-open default must be a FRESH structure each call.

        Regression for the shallow-copy defect: returning ``dict(_EMPTY)`` left
        the nested ``"files"`` dict aliasing the module-global. A caller that
        mutates the returned mapping's ``"files"`` (exactly what
        ``ontology_tracker.check()`` does on a missing checksums file) then
        polluted the module-global process-wide, so a later ``read_checksums``
        no longer returned an empty default.
        """
        missing = Path("/nonexistent/path/checksums.json")
        first = checksums_io.read_checksums(missing)
        first["files"]["polluted.yaml"] = {"last_tracked": "x"}
        second = checksums_io.read_checksums(missing)
        self.assertEqual(second, {"version": 1, "files": {}})

    def test_invalid_file_default_does_not_alias_module_global(self) -> None:
        """Same fresh-structure guarantee on the invalid/parse-failure path."""
        with _tmp_file("{not valid json") as path:
            first = checksums_io.read_checksums(path)
            first["files"]["polluted.yaml"] = {"last_tracked": "x"}
            second = checksums_io.read_checksums(path)
        self.assertEqual(second, {"version": 1, "files": {}})


class WriteChecksumsTests(unittest.TestCase):
    def test_write_then_read_round_trips(self) -> None:
        with _tmp_dir() as tmpdir:
            path = tmpdir / "sub" / "checksums.json"
            data = {"version": 1, "files": {"a.yaml": {"last_tracked": "abc"}}}
            checksums_io.write_checksums(path, data)
            self.assertTrue(path.is_file())
            self.assertEqual(checksums_io.read_checksums(path), data)

    def test_non_ascii_description_survives_unescaped(self) -> None:
        """#1038: the writer must not re-escape literal UTF-8 to \\uXXXX."""
        with _tmp_dir() as tmpdir:
            path = tmpdir / "checksums.json"
            description = "SCOPE (#857, #820/C×T2): semantic overlay — not structural"
            checksums_io.write_checksums(
                path, {"version": 1, "description": description, "files": {}}
            )
            raw = path.read_text(encoding="utf-8")
            self.assertIn(description, raw)
            self.assertNotIn("\\u", raw)

    def test_write_creates_parent_directory(self) -> None:
        with _tmp_dir() as tmpdir:
            path = tmpdir / "does" / "not" / "exist" / "checksums.json"
            checksums_io.write_checksums(path, {"version": 1, "files": {}})
            self.assertTrue(path.is_file())

    def test_write_ends_with_trailing_newline(self) -> None:
        with _tmp_dir() as tmpdir:
            path = tmpdir / "checksums.json"
            checksums_io.write_checksums(path, {"version": 1, "files": {}})
            self.assertTrue(path.read_text(encoding="utf-8").endswith("\n"))

    def test_write_leaves_no_tmp_file_behind(self) -> None:
        with _tmp_dir() as tmpdir:
            path = tmpdir / "checksums.json"
            checksums_io.write_checksums(path, {"version": 1, "files": {}})
            self.assertFalse(path.with_suffix(".tmp").exists())

    def test_write_is_byte_stable_across_repeated_writes_of_same_data(self) -> None:
        """A no-op re-write of identical data must not change the bytes."""
        with _tmp_dir() as tmpdir:
            path = tmpdir / "checksums.json"
            data = {"version": 1, "description": "overlay — × scope", "files": {}}
            checksums_io.write_checksums(path, data)
            first = path.read_bytes()
            checksums_io.write_checksums(path, data)
            second = path.read_bytes()
            self.assertEqual(first, second)


class MarkResolvedTests(unittest.TestCase):
    def test_resolves_a_tracked_file(self) -> None:
        data: dict[str, Any] = {
            "version": 1,
            "files": {
                "ontology/domain.yaml": {
                    "last_tracked": "sha123",
                    "last_resolved": "sha_old",
                    "tracked_at": "2026-01-01T00:00:00+00:00",
                    "resolved_at": "2025-12-01T00:00:00+00:00",
                }
            },
        }
        resolved = checksums_io.mark_resolved(
            data, ["ontology/domain.yaml"], "2026-01-02T00:00:00+00:00"
        )
        self.assertEqual(resolved, ["ontology/domain.yaml"])
        entry = data["files"]["ontology/domain.yaml"]
        self.assertEqual(entry["last_resolved"], "sha123")
        self.assertEqual(entry["resolved_at"], "2026-01-02T00:00:00+00:00")

    def test_untracked_path_is_skipped_not_raised(self) -> None:
        data: dict[str, Any] = {"version": 1, "files": {}}
        resolved = checksums_io.mark_resolved(data, ["nope.yaml"], "2026-01-02T00:00:00+00:00")
        self.assertEqual(resolved, [])
        self.assertEqual(data["files"], {})

    def test_mixed_tracked_and_untracked_paths(self) -> None:
        data: dict[str, Any] = {
            "version": 1,
            "files": {"a.yaml": {"last_tracked": "sha_a", "last_resolved": ""}},
        }
        resolved = checksums_io.mark_resolved(data, ["a.yaml", "b.yaml"], "now")
        self.assertEqual(resolved, ["a.yaml"])
        self.assertEqual(data["files"]["a.yaml"]["last_resolved"], "sha_a")


class PruneMissingTests(unittest.TestCase):
    """The cleanup half of the orphan-entry fix (wave-28 ``da-wt-490/*``)."""

    def test_removes_entry_whose_file_is_gone(self) -> None:
        with _tmp_dir() as root:
            data: dict[str, Any] = {
                "version": 1,
                "files": {"da-wt-490/src/cli.py": {"last_tracked": "sha", "last_resolved": ""}},
            }
            removed = checksums_io.prune_missing(data, root)
            self.assertEqual(removed, ["da-wt-490/src/cli.py"])
            self.assertEqual(data["files"], {})

    def test_keeps_entry_whose_file_still_exists(self) -> None:
        with _tmp_dir() as root:
            (root / "ontology").mkdir()
            (root / "ontology" / "domain.yaml").write_text("a: 1", encoding="utf-8")
            data: dict[str, Any] = {
                "version": 1,
                "files": {"ontology/domain.yaml": {"last_tracked": "sha", "last_resolved": "sha"}},
            }
            removed = checksums_io.prune_missing(data, root)
            self.assertEqual(removed, [])
            self.assertIn("ontology/domain.yaml", data["files"])

    def test_keeps_a_dirty_but_present_entry(self) -> None:
        """Prune is about existence only — never about dirtiness or staleness."""
        with _tmp_dir() as root:
            (root / "stale.md").write_text("x", encoding="utf-8")
            data: dict[str, Any] = {
                "version": 1,
                "files": {"stale.md": {"last_tracked": "new", "last_resolved": "old"}},
            }
            self.assertEqual(checksums_io.prune_missing(data, root), [])
            self.assertIn("stale.md", data["files"])

    def test_keeps_a_tracked_directory_entry(self) -> None:
        """``exists()`` not ``is_file()`` — a tracked dir path must survive."""
        with _tmp_dir() as root:
            (root / "somedir").mkdir()
            data: dict[str, Any] = {"version": 1, "files": {"somedir": {"last_tracked": "s"}}}
            self.assertEqual(checksums_io.prune_missing(data, root), [])

    def test_returns_removed_keys_sorted(self) -> None:
        with _tmp_dir() as root:
            data: dict[str, Any] = {
                "version": 1,
                "files": {"z/gone.py": {}, "a/gone.py": {}, "m/gone.py": {}},
            }
            self.assertEqual(
                checksums_io.prune_missing(data, root),
                ["a/gone.py", "m/gone.py", "z/gone.py"],
            )

    def test_empty_files_dict_is_a_noop(self) -> None:
        with _tmp_dir() as root:
            data: dict[str, Any] = {"version": 1, "files": {}}
            self.assertEqual(checksums_io.prune_missing(data, root), [])

    def test_missing_files_key_is_created_not_raised(self) -> None:
        with _tmp_dir() as root:
            data: dict[str, Any] = {"version": 1}
            self.assertEqual(checksums_io.prune_missing(data, root), [])
            self.assertEqual(data["files"], {})


class PruneCliTests(unittest.TestCase):
    @staticmethod
    def _seed(root: Path, files: dict[str, Any]) -> Path:
        path = root / "ontology" / "checksums.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"version": 1, "files": files}), encoding="utf-8")
        return path

    @staticmethod
    def _ballast(root: Path, n: int = 12) -> dict[str, Any]:
        """Present-on-disk filler entries.

        The prune sanity guard refuses a run that would remove more than
        ``PRUNE_SANITY_FRACTION`` of all entries. A two-entry fixture makes a
        single legitimate orphan a 50% prune, which the guard correctly
        refuses — so these tests need a realistic denominator rather than a
        weakened guard.
        """
        out: dict[str, Any] = {}
        for i in range(n):
            (root / f"ballast{i}.md").write_text("x", encoding="utf-8")
            out[f"ballast{i}.md"] = {"last_tracked": "s"}
        return out

    def test_prune_cli_removes_orphans_and_writes(self) -> None:
        with _tmp_dir() as root:
            (root / "ontology").mkdir(parents=True, exist_ok=True)
            (root / "ontology" / "domain.yaml").write_text("a: 1", encoding="utf-8")
            files = self._ballast(root)
            files["ontology/domain.yaml"] = {"last_tracked": "s"}
            files["da-wt-490/src/cli.py"] = {}
            path = self._seed(root, files)
            rc = checksums_io.main(
                ["checksums_io.py", "prune", "--checksums", str(path), "--apply"]
            )
            self.assertEqual(rc, 0)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertNotIn("da-wt-490/src/cli.py", data["files"])
            self.assertIn("ontology/domain.yaml", data["files"])

    def test_repo_root_defaults_to_checksums_grandparent(self) -> None:
        """``<root>/ontology/checksums.json`` -> ``<root>``, so no flags needed."""
        with _tmp_dir() as root:
            (root / "kept.md").write_text("x", encoding="utf-8")
            files = self._ballast(root)
            files["kept.md"] = {"last_tracked": "s"}
            files["gone.md"] = {}
            path = self._seed(root, files)
            self.assertEqual(
                checksums_io.main(
                    ["checksums_io.py", "prune", "--checksums", str(path), "--apply"]
                ),
                0,
            )
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn("kept.md", data["files"])
            self.assertNotIn("gone.md", data["files"])

    def _two_root_fixture(self, root: Path) -> tuple[Path, Path]:
        """A fixture where the two candidate roots disagree about WHICH entry is an orphan.

        #1284's discriminating-observable fixture. Ballast exists under BOTH
        roots (never an orphan either way), and exactly one entry is orphaned
        under each root:

            only_in_root.md       present under `root`, absent under `elsewhere`
            only_in_elsewhere.md  present under `elsewhere`, absent under `root`

        So the prune set is 1-of-14 whichever root wins — Guard 3's 25%
        threshold cannot fire, the exit code is 0 either way, and the ONLY
        channel that distinguishes an honored `--repo-root` from an ignored
        one is the preview list naming the orphan. That is the point: see
        `test_explicit_repo_root_is_honored`.
        """
        elsewhere = root / "elsewhere"
        elsewhere.mkdir()
        files: dict[str, Any] = {}
        for i in range(12):
            (root / f"ballast{i}.md").write_text("x", encoding="utf-8")
            (elsewhere / f"ballast{i}.md").write_text("x", encoding="utf-8")
            files[f"ballast{i}.md"] = {"last_tracked": "s"}
        (root / "only_in_root.md").write_text("x", encoding="utf-8")
        (elsewhere / "only_in_elsewhere.md").write_text("x", encoding="utf-8")
        files["only_in_root.md"] = {"last_tracked": "s"}
        files["only_in_elsewhere.md"] = {"last_tracked": "s"}
        return elsewhere, self._seed(root, files)

    def test_explicit_repo_root_is_honored(self) -> None:
        """`--repo-root` decides WHICH entry is an orphan — assert that, not the exit code.

        #1284 carried a claim that this test "seeds no orphan, so it passes
        whether or not --repo-root is honored". The claim is INVERTED, and
        both merge-gate comments on that issue reproduced the inversion: the
        old 1-entry fixture DID kill a `--repo-root`-ignoring mutant, but
        entirely via Guard 3's 25% sanity threshold tripping on a 1-of-1
        prune. Neither of its assertions tested `--repo-root` semantics, so
        the "obvious fix" — giving the fixture realistic ballast, as the four
        sibling tests have — drops the ratio below the threshold and the
        mutation SURVIVES. The coverage was accidental.

        This asserts the discriminating observable directly: with ballast
        present (so the exit code is 0 under both the correct and the
        mutated implementation), the preview list names `only_in_root.md`
        and NOT `only_in_elsewhere.md`. Honoring the flag is now the only
        way to produce that output.
        """
        with _tmp_dir() as root:
            elsewhere, path = self._two_root_fixture(root)
            with _capture_stdout() as out:
                rc = checksums_io.main(
                    [
                        "checksums_io.py",
                        "prune",
                        "--checksums",
                        str(path),
                        "--repo-root",
                        str(elsewhere),
                    ]
                )
            printed = out.getvalue()
            # Exit code deliberately does NOT discriminate here (that is the
            # whole finding) — it is asserted only to prove the run completed
            # normally rather than being refused by a guard.
            self.assertEqual(rc, 0)
            self.assertIn("only_in_root.md", printed)
            self.assertNotIn("only_in_elsewhere.md", printed)
            self.assertIn(str(elsewhere), printed)

    def test_explicit_repo_root_is_honored_in_the_applied_write(self) -> None:
        """Same discrimination on the OTHER channel a caller consumes: the written file.

        The preview list is what a human reads; the mutated ledger is what
        every later reader consumes. `--apply` on the same fixture must
        delete the entry orphaned under the EXPLICIT root and keep the other
        one — a `--repo-root`-ignoring implementation writes the exact
        inverse, at the same exit code.
        """
        with _tmp_dir() as root:
            elsewhere, path = self._two_root_fixture(root)
            with _capture_stdout():
                rc = checksums_io.main(
                    [
                        "checksums_io.py",
                        "prune",
                        "--checksums",
                        str(path),
                        "--repo-root",
                        str(elsewhere),
                        "--apply",
                    ]
                )
            self.assertEqual(rc, 0)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertNotIn("only_in_root.md", data["files"])
            self.assertIn("only_in_elsewhere.md", data["files"])

    def test_dry_run_leaves_the_file_untouched(self) -> None:
        with _tmp_dir() as root:
            files = self._ballast(root)
            files["gone.md"] = {"last_tracked": "s"}
            path = self._seed(root, files)
            before = path.read_bytes()
            rc = checksums_io.main(
                ["checksums_io.py", "prune", "--checksums", str(path), "--dry-run"]
            )
            self.assertEqual(rc, 0)
            self.assertEqual(path.read_bytes(), before)

    def test_bare_prune_previews_and_does_not_write(self) -> None:
        """#1137: the destructive default is inverted — no flag means no write.

        This is the whole issue. A `prune` run from muscle memory, or a
        copy-paste that dropped `--dry-run`, used to mutate a version-
        controlled artifact on the strength of an on-disk existence test whose
        own docstring flags a documented false-positive scenario.
        """
        with _tmp_dir() as root:
            files = self._ballast(root)
            files["gone.md"] = {"last_tracked": "s"}
            path = self._seed(root, files)
            before = path.read_bytes()
            rc = checksums_io.main(["checksums_io.py", "prune", "--checksums", str(path)])
            self.assertEqual(rc, 0)
            self.assertEqual(path.read_bytes(), before)
            self.assertIn("gone.md", json.loads(path.read_text(encoding="utf-8"))["files"])

    def test_preview_output_names_the_apply_flag(self) -> None:
        """A preview must tell the reader how to proceed, or the flip just
        strands whoever ran the old spelling."""
        with _tmp_dir() as root:
            files = self._ballast(root)
            files["gone.md"] = {"last_tracked": "s"}
            path = self._seed(root, files)
            with _capture_stdout() as out:
                checksums_io.main(["checksums_io.py", "prune", "--checksums", str(path)])
        printed = out.getvalue()
        self.assertIn("Would prune", printed)
        self.assertIn("--apply", printed)

    def test_apply_output_says_pruned_not_would_prune(self) -> None:
        with _tmp_dir() as root:
            files = self._ballast(root)
            files["gone.md"] = {"last_tracked": "s"}
            path = self._seed(root, files)
            with _capture_stdout() as out:
                checksums_io.main(["checksums_io.py", "prune", "--checksums", str(path), "--apply"])
        printed = out.getvalue()
        self.assertIn("Pruned 1 orphan entry", printed)
        self.assertNotIn("Would prune", printed)

    def test_dry_run_plus_apply_is_a_usage_error(self) -> None:
        """Contradictory flags refuse rather than resolve by silent precedence.

        Either precedence is defensible and neither is guessable — the same
        shape as the undocumented `--checksums`-must-come-first rule that
        already bit once. Refusing costs one re-run; guessing wrong in the
        write direction costs the artifact.
        """
        with _tmp_dir() as root:
            files = self._ballast(root)
            files["gone.md"] = {"last_tracked": "s"}
            path = self._seed(root, files)
            before = path.read_bytes()
            rc = checksums_io.main(
                ["checksums_io.py", "prune", "--checksums", str(path), "--dry-run", "--apply"]
            )
            self.assertEqual(rc, 2)
            self.assertEqual(path.read_bytes(), before)

    def test_no_orphans_does_not_rewrite_the_file(self) -> None:
        """A clean prune must be byte-inert — no churn on the committed file."""
        with _tmp_dir() as root:
            (root / "kept.md").write_text("x", encoding="utf-8")
            path = self._seed(root, {"kept.md": {"last_tracked": "s"}})
            before = path.read_bytes()
            self.assertEqual(
                checksums_io.main(["checksums_io.py", "prune", "--checksums", str(path)]), 0
            )
            self.assertEqual(path.read_bytes(), before)

    def test_unexpected_prune_argument_is_usage_error(self) -> None:
        self.assertEqual(checksums_io.main(["checksums_io.py", "prune", "--bogus"]), 2)

    def test_checksums_flag_works_in_any_position(self) -> None:
        """An earlier revision required --checksums FIRST and died otherwise.

        It failed safe, but an undocumented ordering rule on a destructive CLI
        is a trap — `prune --dry-run --checksums X` is the natural spelling.
        """
        with _tmp_dir() as root:
            files = self._ballast(root)
            files["gone.md"] = {"last_tracked": "s"}
            path = self._seed(root, files)
            before = path.read_bytes()
            rc = checksums_io.main(
                ["checksums_io.py", "prune", "--dry-run", "--checksums", str(path)]
            )
            self.assertEqual(rc, 0)
            self.assertEqual(path.read_bytes(), before)

    def test_checksums_flag_in_trailing_position_without_value_is_usage_error(self) -> None:
        self.assertEqual(
            checksums_io.main(["checksums_io.py", "prune", "--dry-run", "--checksums"]), 2
        )

    def test_repo_root_flag_missing_value_is_usage_error(self) -> None:
        self.assertEqual(checksums_io.main(["checksums_io.py", "prune", "--repo-root"]), 2)

    def test_prune_write_preserves_byte_stability_contract(self) -> None:
        """The new writer must go through ``write_checksums``, not a raw dump.

        This PR adds a SECOND programmatic writer to checksums.json. Asserting
        only on key membership let an `ensure_ascii=True` raw-`json.dumps`
        mutant pass the whole suite — re-escaping literal UTF-8 and dropping
        the trailing newline, i.e. reintroducing #1038 through the new door.
        Seeding a non-ASCII `description` gives the contract teeth here.
        """
        with _tmp_dir() as root:
            (root / "kept.md").write_text("x", encoding="utf-8")
            path = root / "ontology" / "checksums.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            description = "semantic overlay — × not structural"
            files = self._ballast(root)
            files["kept.md"] = {"last_tracked": "s"}
            files["gone.md"] = {}
            path.write_text(
                json.dumps(
                    {"version": 1, "description": description, "files": files},
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            self.assertEqual(
                checksums_io.main(
                    ["checksums_io.py", "prune", "--checksums", str(path), "--apply"]
                ),
                0,
            )
            raw = path.read_text(encoding="utf-8")
            self.assertIn(description, raw)
            self.assertNotIn("\\u", raw)
            self.assertTrue(raw.endswith("\n"))
            remaining = json.loads(raw)["files"]
            self.assertIn("kept.md", remaining)
            self.assertNotIn("gone.md", remaining)


class PruneGuardTests(unittest.TestCase):
    """Guards between a mistyped invocation and a mass delete (merge-gate review)."""

    @staticmethod
    def _seed(root: Path, n_present: int, n_missing: int) -> Path:
        files: dict[str, Any] = {}
        for i in range(n_present):
            (root / f"p{i}.md").write_text("x", encoding="utf-8")
            files[f"p{i}.md"] = {"last_tracked": "s"}
        for i in range(n_missing):
            files[f"gone{i}.md"] = {"last_tracked": "s"}
        path = root / "ontology" / "checksums.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"version": 1, "files": files}), encoding="utf-8")
        return path

    def test_nonexistent_repo_root_is_refused(self) -> None:
        """A typo'd root made EVERY entry read as orphaned and exited 0."""
        with _tmp_dir() as root:
            path = self._seed(root, n_present=4, n_missing=0)
            before = path.read_bytes()
            rc = checksums_io.main(
                [
                    "checksums_io.py",
                    "prune",
                    "--checksums",
                    str(path),
                    "--repo-root",
                    str(root / "nonexistent" / "typo"),
                ]
            )
            self.assertEqual(rc, 2)
            self.assertEqual(path.read_bytes(), before)

    def test_nonexistent_repo_root_is_refused_even_with_force(self) -> None:
        """Guard 1 is not overridable — there is no correct use for it."""
        with _tmp_dir() as root:
            path = self._seed(root, n_present=4, n_missing=0)
            rc = checksums_io.main(
                [
                    "checksums_io.py",
                    "prune",
                    "--checksums",
                    str(path),
                    "--repo-root",
                    str(root / "typo"),
                    "--force",
                ]
            )
            self.assertEqual(rc, 2)

    def test_over_threshold_prune_is_refused(self) -> None:
        """8 of 10 entries missing is a wrong root, not a stale file."""
        with _tmp_dir() as root:
            path = self._seed(root, n_present=2, n_missing=8)
            before = path.read_bytes()
            rc = checksums_io.main(["checksums_io.py", "prune", "--checksums", str(path)])
            self.assertEqual(rc, 1)
            self.assertEqual(path.read_bytes(), before)

    def test_over_threshold_prune_is_refused_on_dry_run_too(self) -> None:
        """A preview that prints a mass wipe as normal output invites a rubber stamp."""
        with _tmp_dir() as root:
            path = self._seed(root, n_present=2, n_missing=8)
            rc = checksums_io.main(
                ["checksums_io.py", "prune", "--checksums", str(path), "--dry-run"]
            )
            self.assertEqual(rc, 1)

    def test_force_overrides_the_threshold(self) -> None:
        with _tmp_dir() as root:
            path = self._seed(root, n_present=2, n_missing=8)
            rc = checksums_io.main(
                ["checksums_io.py", "prune", "--checksums", str(path), "--force", "--apply"]
            )
            self.assertEqual(rc, 0)
            self.assertEqual(len(json.loads(path.read_text(encoding="utf-8"))["files"]), 2)

    def test_force_alone_still_only_previews(self) -> None:
        """--force overrides the GUARDS, not the preview default (#1137).

        The two axes are orthogonal: --force says "I know this root is
        unusual", --apply says "write it". Collapsing them would make the
        escape hatch for a false-positive guard also the escape hatch for the
        write, which is precisely the pairing that should stay hard.
        """
        with _tmp_dir() as root:
            path = self._seed(root, n_present=2, n_missing=8)
            before = path.read_bytes()
            rc = checksums_io.main(
                ["checksums_io.py", "prune", "--checksums", str(path), "--force"]
            )
            self.assertEqual(rc, 0)
            self.assertEqual(path.read_bytes(), before)

    def test_under_threshold_prune_still_proceeds(self) -> None:
        """The guard must not block a legitimate steady-state prune."""
        with _tmp_dir() as root:
            path = self._seed(root, n_present=19, n_missing=1)
            rc = checksums_io.main(
                ["checksums_io.py", "prune", "--checksums", str(path), "--apply"]
            )
            self.assertEqual(rc, 0)
            self.assertEqual(len(json.loads(path.read_text(encoding="utf-8"))["files"]), 19)

    def test_empty_file_does_not_divide_by_zero(self) -> None:
        with _tmp_dir() as root:
            path = self._seed(root, n_present=0, n_missing=0)
            self.assertEqual(
                checksums_io.main(["checksums_io.py", "prune", "--checksums", str(path)]), 0
            )

    def test_repo_root_that_is_a_linked_worktree_is_refused(self) -> None:
        """Worktrees are the org's default isolation and lack the child clones."""
        with _tmp_dir() as root:
            repo = root / "repo"
            repo.mkdir()
            env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}

            def git(*a: str, cwd: Path) -> None:
                subprocess.run(["git", *a], cwd=str(cwd), check=True, capture_output=True, env=env)

            git("init", "-q", str(repo), cwd=root)
            (repo / "seed.txt").write_text("s", encoding="utf-8")
            git("add", "seed.txt", cwd=repo)
            git("-c", "user.name=T", "-c", "user.email=t@e.com", "commit", "-qm", "s", cwd=repo)
            wt = root / "wt"
            git("worktree", "add", "-q", "-b", "b1", str(wt), cwd=repo)

            path = self._seed(root, n_present=0, n_missing=0)
            rc = checksums_io.main(
                [
                    "checksums_io.py",
                    "prune",
                    "--checksums",
                    str(path),
                    "--repo-root",
                    str(wt),
                ]
            )
            self.assertEqual(rc, 2)

            # --force is the documented escape hatch for guard 2.
            self.assertEqual(
                checksums_io.main(
                    [
                        "checksums_io.py",
                        "prune",
                        "--checksums",
                        str(path),
                        "--repo-root",
                        str(wt),
                        "--force",
                    ]
                ),
                0,
            )


class IsLinkedWorktreeRootTests(unittest.TestCase):
    """The admin-dir invariant that replaced the ``/worktrees/`` substring test."""

    @staticmethod
    def _git(*a: str, cwd: Path) -> None:
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        subprocess.run(["git", *a], cwd=str(cwd), check=True, capture_output=True, env=env)

    def _repo(self, root: Path) -> Path:
        repo = root / "repo"
        repo.mkdir()
        self._git("init", "-q", str(repo), cwd=root)
        (repo / "seed.txt").write_text("s", encoding="utf-8")
        self._git("add", "seed.txt", cwd=repo)
        self._git("-c", "user.name=T", "-c", "user.email=t@e.com", "commit", "-qm", "s", cwd=repo)
        return repo

    def test_plain_checkout_is_false(self) -> None:
        with _tmp_dir() as root:
            self.assertFalse(checksums_io.is_linked_worktree_root(self._repo(root)))

    def test_linked_worktree_is_true(self) -> None:
        with _tmp_dir() as root:
            repo = self._repo(root)
            wt = root / "wt"
            self._git("worktree", "add", "-q", "-b", "b1", str(wt), cwd=repo)
            self.assertTrue(checksums_io.is_linked_worktree_root(wt))

    def test_submodule_pointer_under_a_worktrees_path_is_false(self) -> None:
        """The substring predicate's false positive #1."""
        with _tmp_dir() as root:
            repo = self._repo(root)
            sub = repo / "vendor" / "libbar"
            sub.mkdir(parents=True)
            modules = repo / ".git" / "modules" / "worktrees" / "libbar"
            modules.mkdir(parents=True)
            (sub / ".git").write_text(f"gitdir: {modules}\n", encoding="utf-8")
            self.assertFalse(checksums_io.is_linked_worktree_root(sub))

    def test_separate_git_dir_under_worktrees_is_false(self) -> None:
        """The substring predicate's false positive #2 — driven through real git."""
        with _tmp_dir() as root:
            repo = self._repo(root)
            sep_git = root / "worktrees" / "sep.git"
            sep_git.parent.mkdir(parents=True, exist_ok=True)
            sep_wt = root / "sepwt"
            self._git(
                "clone", "-q", "--separate-git-dir", str(sep_git), str(repo), str(sep_wt), cwd=root
            )
            self.assertFalse(checksums_io.is_linked_worktree_root(sep_wt))

    def test_missing_dot_git_is_false(self) -> None:
        with _tmp_dir() as root:
            self.assertFalse(checksums_io.is_linked_worktree_root(root))

    def test_unrecognized_pointer_is_false(self) -> None:
        with _tmp_dir() as root:
            (root / ".git").write_text("not a pointer\n", encoding="utf-8")
            self.assertFalse(checksums_io.is_linked_worktree_root(root))

    def test_pointer_to_missing_admin_dir_is_false(self) -> None:
        """Fail open when the pointer target has no gitdir/commondir files."""
        with _tmp_dir() as root:
            (root / ".git").write_text(f"gitdir: {root / 'nope'}\n", encoding="utf-8")
            self.assertFalse(checksums_io.is_linked_worktree_root(root))


class MainCliTests(unittest.TestCase):
    def test_mark_resolved_cli_end_to_end(self) -> None:
        with _tmp_dir() as tmpdir:
            path = tmpdir / "checksums.json"
            path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "files": {
                            "ontology/domain.yaml": {
                                "last_tracked": "shaXYZ",
                                "last_resolved": "",
                                "tracked_at": "t",
                                "resolved_at": "",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            rc = checksums_io.main(
                [
                    "checksums_io.py",
                    "mark-resolved",
                    "--checksums",
                    str(path),
                    "ontology/domain.yaml",
                ]
            )
            self.assertEqual(rc, 0)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(
                data["files"]["ontology/domain.yaml"]["last_resolved"],
                "shaXYZ",
            )

    def test_no_subcommand_is_usage_error(self) -> None:
        self.assertEqual(checksums_io.main(["checksums_io.py"]), 2)

    def test_unknown_subcommand_is_usage_error(self) -> None:
        self.assertEqual(checksums_io.main(["checksums_io.py", "bogus"]), 2)

    def test_mark_resolved_with_no_paths_is_usage_error(self) -> None:
        self.assertEqual(checksums_io.main(["checksums_io.py", "mark-resolved"]), 2)

    def test_checksums_flag_missing_value_is_usage_error(self) -> None:
        self.assertEqual(checksums_io.main(["checksums_io.py", "mark-resolved", "--checksums"]), 2)


class MarkResolvedArgumentTests(unittest.TestCase):
    """#1285: `mark-resolved` was the one subcommand that swallowed unknown flags.

    It is also the only one that WRITES. Anything it did not recognize became
    a `<rel-path>`, so `--checksums=PATH` (a spelling `status` and `prune`
    both rejected with exit 2) selected the DEFAULT committed ledger,
    modified it, and reported `Resolved 1 file(s)` at exit 0. The only signal
    was a `Skipped (not tracked):` line that reads as ordinary output,
    because the resolver legitimately passes path lists wider than what the
    tracker has seen.

    "Wrote the wrong file at exit 0" has to be impossible on every channel,
    so each test below pins the exit code AND the bytes of the ledger that
    must not have been touched.

    These never point at the real `ontology/checksums.json`: the "default"
    ledger under test is a copy of `checksums_io`'s default path, taken and
    restored around each case, and the assertions are on that copy.
    """

    ENTRY = {"last_tracked": "shaXYZ", "last_resolved": "", "tracked_at": "t", "resolved_at": ""}

    @contextmanager
    def _isolated_default(self):
        """Run with `_default_checksums_path` pointed at a temp ledger.

        Patching the module function is what keeps the REAL committed ledger
        out of reach: the defect under test is precisely "wrote the default
        ledger", so the test has to be able to observe a default-ledger write
        without risking one.
        """
        with _tmp_dir() as root:
            default = root / "default-ledger.json"
            target = root / "target-ledger.json"
            payload = json.dumps({"version": 1, "files": {"ontology/domain.yaml": self.ENTRY}})
            default.write_text(payload, encoding="utf-8")
            target.write_text(payload, encoding="utf-8")
            original = checksums_io._default_checksums_path
            checksums_io._default_checksums_path = lambda: default  # type: ignore[assignment]
            try:
                yield default, target
            finally:
                checksums_io._default_checksums_path = original  # type: ignore[assignment]

    @staticmethod
    def _resolved(path: Path) -> str:
        data = json.loads(path.read_text(encoding="utf-8"))
        return str(data["files"]["ontology/domain.yaml"]["last_resolved"])

    def test_equals_form_targets_the_named_ledger_not_the_default(self) -> None:
        """The #1285 headline: `--checksums=PATH` wrote the DEFAULT ledger at exit 0."""
        with self._isolated_default() as (default, target):
            before = default.read_bytes()
            with _capture_stdout() as out:
                rc = checksums_io.main(
                    [
                        "checksums_io.py",
                        "mark-resolved",
                        f"--checksums={target}",
                        "ontology/domain.yaml",
                    ]
                )
            self.assertEqual(rc, 0)
            self.assertEqual(default.read_bytes(), before, "the default ledger must be untouched")
            self.assertEqual(self._resolved(target), "shaXYZ")
            self.assertIn(str(target), out.getvalue())
            self.assertNotIn("Skipped", out.getvalue())

    def test_equals_form_is_accepted_by_status_and_prune_too(self) -> None:
        """One spelling rule for all three subcommands, not three (#1285)."""
        with self._isolated_default() as (default, target):
            with _capture_stdout() as out:
                status_rc = checksums_io.main(
                    ["checksums_io.py", "status", f"--checksums={target}"]
                )
            self.assertEqual(status_rc, 1, "one dirty entry in the NAMED ledger")
            self.assertIn(str(target), out.getvalue())
            with _capture_stdout() as out:
                prune_rc = checksums_io.main(["checksums_io.py", "prune", f"--checksums={target}"])
            self.assertIn(prune_rc, (0, 1))
            self.assertNotIn(str(default), out.getvalue())

    def test_unknown_flag_is_rejected_and_writes_nothing(self) -> None:
        with self._isolated_default() as (default, _target):
            before = default.read_bytes()
            with _capture_stderr() as err:
                rc = checksums_io.main(
                    ["checksums_io.py", "mark-resolved", "--bogus", "ontology/domain.yaml"]
                )
            self.assertEqual(rc, 2)
            self.assertEqual(default.read_bytes(), before)
            self.assertIn("--bogus", err.getvalue())
            self.assertIn("--checksums=PATH", err.getvalue())

    def test_prune_flag_typed_at_mark_resolved_is_rejected(self) -> None:
        """`--apply` is a `prune` flag; at `mark-resolved` it used to become a path."""
        with self._isolated_default() as (default, _target):
            before = default.read_bytes()
            with _capture_stderr():
                rc = checksums_io.main(
                    ["checksums_io.py", "mark-resolved", "--apply", "ontology/domain.yaml"]
                )
            self.assertEqual(rc, 2)
            self.assertEqual(default.read_bytes(), before)

    def test_second_checksums_flag_is_rejected_rather_than_silently_losing(self) -> None:
        """Only the first `--checksums` is consumed; a second must not be swallowed."""
        with self._isolated_default() as (default, target):
            before = default.read_bytes()
            with _capture_stderr() as err:
                rc = checksums_io.main(
                    [
                        "checksums_io.py",
                        "mark-resolved",
                        f"--checksums={target}",
                        "--checksums",
                        str(default),
                        "ontology/domain.yaml",
                    ]
                )
            self.assertEqual(rc, 2)
            self.assertEqual(default.read_bytes(), before)
            self.assertIn("--checksums", err.getvalue())

    def test_empty_equals_value_is_a_usage_error(self) -> None:
        with self._isolated_default() as (default, _target):
            before = default.read_bytes()
            with _capture_stderr() as err:
                rc = checksums_io.main(
                    ["checksums_io.py", "mark-resolved", "--checksums=", "ontology/domain.yaml"]
                )
            self.assertEqual(rc, 2)
            self.assertEqual(default.read_bytes(), before)
            self.assertIn("requires a PATH", err.getvalue())

    def test_a_bare_path_still_resolves_against_the_default(self) -> None:
        """The ordinary path stays ordinary — the guard rejects flags, not work."""
        with self._isolated_default() as (default, _target):
            with _capture_stdout():
                rc = checksums_io.main(["checksums_io.py", "mark-resolved", "ontology/domain.yaml"])
            self.assertEqual(rc, 0)
            self.assertEqual(self._resolved(default), "shaXYZ")


class ClassifyEntryTests(unittest.TestCase):
    """#1142: the ONE dirty predicate, and its third state.

    Every historical wrong read of this ledger produced a comparison that
    quietly evaluated to "equal" — a key that does not exist, a nesting level
    that is not there — so the failure mode was a plausible 0, never an
    error. `classify_entry` exists so nobody re-derives the comparison, and
    MALFORMED exists so a shape it does not recognize cannot land in "clean".
    """

    def test_differing_hashes_are_dirty(self) -> None:
        state, detail = checksums_io.classify_entry({"last_tracked": "aaa", "last_resolved": "bbb"})
        self.assertEqual(state, checksums_io.ENTRY_DIRTY)
        self.assertEqual(detail, "")

    def test_matching_hashes_are_clean(self) -> None:
        state, _ = checksums_io.classify_entry({"last_tracked": "aaa", "last_resolved": "aaa"})
        self.assertEqual(state, checksums_io.ENTRY_CLEAN)

    def test_empty_last_resolved_is_dirty_not_malformed(self) -> None:
        """A freshly (re-)tracked file legitimately carries `last_resolved: ""`.

        The tracker writes that shape on purpose, and `prune_missing`'s
        docstring documents it as the post-re-tracking state. Treating it as
        malformed would flag ~every new file; treating it as clean would hide
        exactly the entries a rebuild needs to process.
        """
        state, _ = checksums_io.classify_entry({"last_tracked": "aaa", "last_resolved": ""})
        self.assertEqual(state, checksums_io.ENTRY_DIRTY)

    def test_missing_both_keys_is_malformed_not_clean(self) -> None:
        """`.get(...) != .get(...)` compares None != None -> "clean". It is not.

        This is the exact shape of the wrong read recorded in #1142: a
        comparison against keys that are not in the schema, yielding equality
        on every entry and a total of 0 dirty.
        """
        state, detail = checksums_io.classify_entry({"sha256": "aaa", "tracked_at": "t"})
        self.assertEqual(state, checksums_io.ENTRY_MALFORMED)
        self.assertIn("last_tracked", detail)
        self.assertIn("last_resolved", detail)

    def test_missing_only_last_tracked_is_malformed(self) -> None:
        """The real in-the-wild case: `{"last_resolved": null, "resolved_at": ...}`.

        Hand-written into the committed ledger by a pre-#1042 resolver pass
        and invisible to every reader since, because None != None is False.
        """
        state, detail = checksums_io.classify_entry(
            {"last_resolved": None, "resolved_at": "2026-06-14T00:16:00Z"}
        )
        self.assertEqual(state, checksums_io.ENTRY_MALFORMED)
        self.assertIn("missing last_tracked", detail)

    def test_null_hash_is_malformed_not_clean(self) -> None:
        """Two nulls compare equal. Equal is not the same as resolved."""
        state, detail = checksums_io.classify_entry({"last_tracked": None, "last_resolved": None})
        self.assertEqual(state, checksums_io.ENTRY_MALFORMED)
        self.assertIn("expected a string", detail)

    def test_non_dict_entry_is_malformed(self) -> None:
        for value in ("a string", 42, None, ["list"]):
            with self.subTest(value=value):
                state, detail = checksums_io.classify_entry(value)
                self.assertEqual(state, checksums_io.ENTRY_MALFORMED)
                self.assertIn("expected an object", detail)

    def test_stored_values_alone_cannot_see_drift(self) -> None:
        """The scope boundary #1505 turns on, asserted rather than assumed.

        `classify_entry` is still allowed to call this entry clean — it only
        ever compares the ledger to itself, and by that comparison the entry
        IS clean. What was wrong was every reader treating that answer as
        "the file matches". `classify_against_file` is the one that opens the
        file, and the next test is the same entry through it.
        """
        stale = hashlib.sha256(b"what the file used to contain").hexdigest()
        state, _ = checksums_io.classify_entry({"last_tracked": stale, "last_resolved": stale})
        self.assertEqual(state, checksums_io.ENTRY_CLEAN)


class ClassifyAgainstFileTests(unittest.TestCase):
    """#1505: the predicate that opens the file.

    Pre-fix there was no such function — no reader hashed anything, so the
    only question ever asked was whether the ledger agreed with itself. Every
    test here fails against the pre-fix module (with an AttributeError, since
    the entry point does not exist), which is the point: the states it
    distinguishes were not distinguishable at all.
    """

    def test_agreeing_stored_values_that_match_the_file_are_clean(self) -> None:
        with _tmp_dir() as root:
            entry = _clean_entry(root, "a.md")
            state, detail = checksums_io.classify_against_file(entry, root / "a.md")
        self.assertEqual(state, checksums_io.ENTRY_CLEAN)
        self.assertEqual(detail, "")

    def test_agreeing_stored_values_that_match_neither_are_drifted(self) -> None:
        """The 158. Pre-fix this entry was clean, at exit 0, forever."""
        with _tmp_dir() as root:
            entry = _drifted_entry(root, "a.md")
            state, detail = checksums_io.classify_against_file(entry, root / "a.md")
        self.assertEqual(state, checksums_io.ENTRY_DRIFTED)
        self.assertIn("ledger stores", detail)

    def test_missing_tracked_file_is_undeterminable_not_clean(self) -> None:
        """ "I could not measure this" is not "I measured it and it was fine".

        The entry is well-formed and its stored values agree, so every
        shape-only predicate calls it clean. Nothing was hashed, because
        there is nothing to hash.
        """
        with _tmp_dir() as root:
            sha = hashlib.sha256(b"gone").hexdigest()
            state, detail = checksums_io.classify_against_file(
                {"last_tracked": sha, "last_resolved": sha}, root / "absent.md"
            )
        self.assertEqual(state, checksums_io.ENTRY_UNDETERMINABLE)
        self.assertIn("absent", detail)

    def test_unreadable_tracked_path_is_undeterminable(self) -> None:
        """A directory where a file is tracked: exists, cannot be hashed.

        Deliberately not a chmod-000 file — the test suite may run as root,
        where mode bits are not enforced and that variant silently passes for
        the wrong reason.
        """
        with _tmp_dir() as root:
            (root / "adir").mkdir()
            sha = hashlib.sha256(b"x").hexdigest()
            state, detail = checksums_io.classify_against_file(
                {"last_tracked": sha, "last_resolved": sha}, root / "adir"
            )
        self.assertEqual(state, checksums_io.ENTRY_UNDETERMINABLE)
        self.assertIn("could not be read", detail)

    def test_dirty_entry_is_never_reclassified_as_drifted(self) -> None:
        """The non-regression #1505 names: dirty short-circuits before the file.

        Other tooling branches on `dirty`, and its remediation
        (`/ontology-rebuild`) already covers this entry. Hashing here could
        only add a second reason for a verdict that does not change.
        """
        with _tmp_dir() as root:
            _materialize(root, "a.md", "some third content\n")
            state, _ = checksums_io.classify_against_file(
                {"last_tracked": "aaa", "last_resolved": "bbb"}, root / "a.md"
            )
        self.assertEqual(state, checksums_io.ENTRY_DIRTY)

    def test_dirty_entry_with_no_file_stays_dirty(self) -> None:
        """Short-circuit again, from the other side: an orphaned dirty entry
        (`prune`'s domain) does not become undeterminable and lose its
        existing, correct remediation."""
        with _tmp_dir() as root:
            state, _ = checksums_io.classify_against_file(
                {"last_tracked": "aaa", "last_resolved": "bbb"}, root / "absent.md"
            )
        self.assertEqual(state, checksums_io.ENTRY_DIRTY)

    def test_malformed_entry_short_circuits_before_the_file(self) -> None:
        with _tmp_dir() as root:
            state, detail = checksums_io.classify_against_file(
                {"last_resolved": None}, root / "absent.md"
            )
        self.assertEqual(state, checksums_io.ENTRY_MALFORMED)
        self.assertIn("missing last_tracked", detail)

    def test_writer_and_reader_share_one_hash_function(self) -> None:
        """`compute_sha256` is the module's own, and it is what the tracker calls.

        A second copy of the hashing would be free to drift from this one, and
        the symptom would be every entry reading as drifted forever. The
        end-to-end pin lives in test_ontology_tracker.py; this is the local
        half — the digest this module computes is a plain sha256 of the bytes.
        """
        with _tmp_dir() as root:
            path = root / "a.md"
            path.write_bytes(b"exact bytes\n")
            self.assertEqual(
                checksums_io.compute_sha256(path),
                hashlib.sha256(b"exact bytes\n").hexdigest(),
            )

    def test_compute_sha256_returns_none_rather_than_raising(self) -> None:
        with _tmp_dir() as root:
            self.assertIsNone(checksums_io.compute_sha256(root / "absent.md"))
            self.assertIsNone(checksums_io.compute_sha256(root))


class ComputeStatusTests(unittest.TestCase):
    def test_counts_dirty_and_reports_paths_sorted(self) -> None:
        status = checksums_io.compute_status(
            {
                "files": {
                    "z.md": {"last_tracked": "1", "last_resolved": "2"},
                    "a.md": {"last_tracked": "1", "last_resolved": "2"},
                    "clean.md": {"last_tracked": "1", "last_resolved": "1"},
                }
            }
        )
        self.assertEqual(status.total, 3)
        self.assertEqual(status.dirty, ("a.md", "z.md"))
        self.assertEqual(status.malformed, ())
        self.assertFalse(status.clean)

    def test_agreeing_stored_values_are_not_dirty(self) -> None:
        """Was `test_clean_ledger_is_clean` before #1505.

        Nothing about the shape-only reading changed — the entry is still not
        dirty and not malformed. What changed is the conclusion drawn from
        that: with no repo root nothing was hashed, so this cannot be
        `clean`. `StatusObjectChannelTests` covers the verified case.
        """
        status = checksums_io.compute_status(
            {"files": {"a.md": {"last_tracked": "1", "last_resolved": "1"}}}
        )
        self.assertEqual((status.total, status.dirty, status.malformed), (1, (), ()))
        self.assertFalse(status.verified)
        self.assertFalse(status.clean)

    def test_empty_ledger_has_nothing_to_report(self) -> None:
        status = checksums_io.compute_status({"files": {}})
        self.assertEqual(status.total, 0)
        self.assertEqual((status.dirty, status.malformed, status.drifted), ((), (), ()))

    def test_empty_ledger_is_clean_once_verified(self) -> None:
        with _tmp_dir() as root:
            status = checksums_io.compute_status({"files": {}}, root)
        self.assertTrue(status.clean)
        self.assertEqual(status.total, 0)

    def test_malformed_entry_blocks_clean(self) -> None:
        """The core #1142 assertion: an unclassifiable entry is NOT clean.

        Everything else is well-formed and resolved, so a reader that folds
        malformed into clean reports a perfectly healthy ledger here — which
        is how the real `last_resolved: null` entry stayed invisible for
        seven weeks.
        """
        status = checksums_io.compute_status(
            {
                "files": {
                    "ok.md": {"last_tracked": "1", "last_resolved": "1"},
                    "broken.md": {"last_resolved": None},
                }
            }
        )
        self.assertEqual(status.dirty, ())
        self.assertFalse(status.clean)
        self.assertEqual([rel for rel, _ in status.malformed], ["broken.md"])

    def test_missing_files_key_raises_rather_than_reporting_zero(self) -> None:
        """The legacy `data.get("files", data)` fallback turned a shape
        mismatch into a plausible zero. Raise instead."""
        with self.assertRaises(checksums_io.ChecksumsUnreadable):
            checksums_io.compute_status({"version": 1})

    def test_non_dict_files_raises(self) -> None:
        with self.assertRaises(checksums_io.ChecksumsUnreadable):
            checksums_io.compute_status({"files": ["a.md"]})


class StatusObjectChannelTests(unittest.TestCase):
    """#1505 on the object channel — the one three hooks branch on.

    `session_start`, `session_handoff` and `smart_grep_ontology` never see the
    CLI's exit code or its stdout; they read `ChecksumsStatus` members
    directly. Correcting the printed counts without moving `.clean` would
    leave all three rendering "current" over a drifted ledger, so the
    difference has to be pinned here too, not only at the CLI.
    """

    def test_drifted_entry_blocks_clean_and_is_listed(self) -> None:
        with _tmp_dir() as root:
            status = checksums_io.compute_status(
                {
                    "files": {
                        "a.md": _clean_entry(root, "a.md"),
                        "b.md": _drifted_entry(root, "b.md"),
                    }
                },
                root,
            )
        self.assertEqual(status.total, 2)
        self.assertEqual(status.dirty, ())
        self.assertEqual(status.malformed, ())
        self.assertEqual([rel for rel, _ in status.drifted], ["b.md"])
        self.assertTrue(status.verified)
        self.assertFalse(status.clean)

    def test_undeterminable_entry_blocks_clean(self) -> None:
        """Every file present and matching except one, which is not there at
        all. Pre-fix: clean. "Cannot evaluate" is not a pass."""
        sha = hashlib.sha256(b"gone").hexdigest()
        with _tmp_dir() as root:
            status = checksums_io.compute_status(
                {
                    "files": {
                        "a.md": _clean_entry(root, "a.md"),
                        "gone.md": {"last_tracked": sha, "last_resolved": sha},
                    }
                },
                root,
            )
        self.assertEqual(status.drifted, ())
        self.assertEqual([rel for rel, _ in status.undeterminable], ["gone.md"])
        self.assertFalse(status.clean)

    def test_verified_matching_ledger_is_clean(self) -> None:
        """The other half of the pin — the fix must not make everything dirty."""
        with _tmp_dir() as root:
            status = checksums_io.compute_status(
                {"files": {"a.md": _clean_entry(root, "a.md"), "b.md": _clean_entry(root, "b.md")}},
                root,
            )
        self.assertTrue(status.verified)
        self.assertTrue(status.clean)
        self.assertEqual((status.dirty, status.drifted, status.undeterminable), ((), (), ()))

    def test_a_status_that_hashed_nothing_can_never_be_clean(self) -> None:
        """Without a repo root no file was opened, so the three empty
        file-derived lists are the empty result of a check that never ran.
        `verified` is what tells those two empties apart."""
        status = checksums_io.compute_status(
            {"files": {"a.md": {"last_tracked": "1", "last_resolved": "1"}}}
        )
        self.assertFalse(status.verified)
        self.assertFalse(status.clean)
        self.assertEqual(status.drifted, ())

    def test_default_constructed_status_is_not_clean(self) -> None:
        """The dataclass default fails closed: a `ChecksumsStatus` assembled
        without hash evidence cannot claim to have any."""
        self.assertFalse(checksums_io.ChecksumsStatus(total=0, dirty=(), malformed=()).clean)

    def test_dirty_entry_is_still_dirty_when_hashing_is_on(self) -> None:
        with _tmp_dir() as root:
            _materialize(root, "b.md", "anything\n")
            status = checksums_io.compute_status(
                {
                    "files": {
                        "a.md": _clean_entry(root, "a.md"),
                        "b.md": {"last_tracked": "1", "last_resolved": "2"},
                    }
                },
                root,
            )
        self.assertEqual(status.dirty, ("b.md",))
        self.assertEqual(status.drifted, ())
        self.assertFalse(status.clean)

    def test_not_current_is_the_union_the_annotating_readers_want(self) -> None:
        sha = hashlib.sha256(b"gone").hexdigest()
        with _tmp_dir() as root:
            _materialize(root, "dirty.md", "x\n")
            status = checksums_io.compute_status(
                {
                    "files": {
                        "ok.md": _clean_entry(root, "ok.md"),
                        "dirty.md": {"last_tracked": "1", "last_resolved": "2"},
                        "drifted.md": _drifted_entry(root, "drifted.md"),
                        "broken.md": {"last_resolved": None},
                        "gone.md": {"last_tracked": sha, "last_resolved": sha},
                    }
                },
                root,
            )
        self.assertEqual(status.not_current, ("broken.md", "dirty.md", "drifted.md", "gone.md"))

    def test_read_status_hashes_by_default(self) -> None:
        """The three hooks call `read_status(path)` with no root — the drift
        check has to be the default, not an opt-in they must remember."""
        with _tmp_dir() as root:
            ledger = root / "ontology" / "checksums.json"
            ledger.parent.mkdir(parents=True)
            ledger.write_text(
                json.dumps({"version": 1, "files": {"a.md": _drifted_entry(root, "a.md")}}),
                encoding="utf-8",
            )
            status = checksums_io.read_status(ledger)
        self.assertTrue(status.verified)
        self.assertEqual([rel for rel, _ in status.drifted], ["a.md"])
        self.assertFalse(status.clean)

    def test_read_status_accepts_an_explicit_root(self) -> None:
        """The linked-worktree escape: check a ledger against another tree."""
        with _tmp_dir() as tree, _tmp_dir() as elsewhere:
            entry = _clean_entry(tree, "a.md")
            ledger = elsewhere / "ontology" / "checksums.json"
            ledger.parent.mkdir(parents=True)
            ledger.write_text(json.dumps({"version": 1, "files": {"a.md": entry}}), "utf-8")
            self.assertFalse(checksums_io.read_status(ledger).clean)
            self.assertTrue(checksums_io.read_status(ledger, tree).clean)


class StrictReadTests(unittest.TestCase):
    """A reader must never turn "could not read" into "0 dirty" (#1142)."""

    def test_missing_file_raises_instead_of_defaulting(self) -> None:
        with self.assertRaises(checksums_io.ChecksumsUnreadable):
            checksums_io.read_status(Path("/nonexistent/path/checksums.json"))

    def test_invalid_json_raises(self) -> None:
        with _tmp_file("{not valid json") as path:
            with self.assertRaises(checksums_io.ChecksumsUnreadable):
                checksums_io.read_status(path)

    def test_non_object_top_level_raises(self) -> None:
        with _tmp_file("[1, 2, 3]") as path:
            with self.assertRaises(checksums_io.ChecksumsUnreadable):
                checksums_io.read_status(path)

    def test_writers_read_path_still_fails_open(self) -> None:
        """The fork is deliberate: `read_checksums` must keep failing open.

        It is the PostToolUse tracker hook's read path, and a hook that raises
        fails the tool call that triggered it. Only the READER side is strict.
        """
        self.assertEqual(
            checksums_io.read_checksums(Path("/nonexistent/path/checksums.json")),
            {"version": 1, "files": {}},
        )

    def test_read_status_round_trips_a_real_ledger(self) -> None:
        with _tmp_file(
            json.dumps(
                {
                    "version": 1,
                    "files": {
                        "a.md": {"last_tracked": "1", "last_resolved": "1"},
                        "b.md": {"last_tracked": "1", "last_resolved": "0"},
                    },
                }
            )
        ) as path:
            status = checksums_io.read_status(path)
        self.assertEqual(status.total, 2)
        self.assertEqual(status.dirty, ("b.md",))


class StatusCliTests(unittest.TestCase):
    """The reader-facing surface #1142 asks for: total / dirty / dirty paths."""

    @staticmethod
    def _seed(root: Path, files: dict[str, Any]) -> Path:
        path = root / "ontology" / "checksums.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"version": 1, "files": files}), encoding="utf-8")
        return path

    def test_clean_ledger_exits_zero(self) -> None:
        """Clean now means measured-and-matching, and says so in words.

        The entry is paired with a real file whose hash is what the ledger
        stores — pre-#1505 the file did not need to exist for this to pass,
        which is precisely how "clean" stopped meaning anything.
        """
        with _tmp_dir() as root:
            path = self._seed(root, {"a.md": _clean_entry(root, "a.md")})
            with _capture_stdout() as out:
                rc = checksums_io.main(["checksums_io.py", "status", "--checksums", str(path)])
        printed = out.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("1 tracked, 0 dirty, 0 drifted, 0 malformed, 0 undeterminable", printed)
        self.assertIn("VERDICT: CLEAN", printed)
        self.assertIn("1 tracked file(s) were hashed", printed)

    def test_dirty_ledger_reports_count_and_paths(self) -> None:
        with _tmp_dir() as root:
            # The dirty entry's file is materialized with content matching
            # NEITHER stored hash: dirty short-circuits before the file is
            # read, so this stays 1 dirty / 0 drifted and exit 1 — the
            # `/ontology-rebuild` branch, not the reconcile branch.
            _materialize(root, "team/trust_matrix.md", "content that matches neither\n")
            path = self._seed(
                root,
                {
                    "a.md": _clean_entry(root, "a.md"),
                    "team/trust_matrix.md": {"last_tracked": "3fe1", "last_resolved": "d35e"},
                },
            )
            with _capture_stdout() as out:
                rc = checksums_io.main(["checksums_io.py", "status", "--checksums", str(path)])
        printed = out.getvalue()
        self.assertEqual(rc, 1)
        self.assertIn("2 tracked, 1 dirty, 0 drifted, 0 malformed, 0 undeterminable", printed)
        self.assertIn("team/trust_matrix.md", printed)
        self.assertIn("VERDICT: NOT CLEAN", printed)

    def test_drifted_ledger_exits_four_and_names_the_paths(self) -> None:
        """THE #1505 test. Pre-fix: "2 tracked, 0 dirty, 0 malformed", exit 0.

        Both entries have `last_tracked == last_resolved`, so the ledger
        agrees with itself and the old predicate had nothing to report. One
        file has since changed by a route that is not an Edit/Write in this
        checkout — a pull, a merge, another session, a worktree — and 158 of
        314 real entries were in exactly that state while `/session-start`
        printed "Semantic overlay: current".

        Pinned on both channels at once: exit 4 (not 0, and not 1 either —
        `mark-resolved` on a drifted entry manufactures a false clean) and a
        rendered report that names the state and the path.
        """
        with _tmp_dir() as root:
            path = self._seed(
                root,
                {
                    "a.md": _clean_entry(root, "a.md"),
                    "ontology/domain.yaml": _drifted_entry(root, "ontology/domain.yaml"),
                },
            )
            with _capture_stdout() as out:
                rc = checksums_io.main(["checksums_io.py", "status", "--checksums", str(path)])
        printed = out.getvalue()
        # Ordered so the pre-fix failure names the defect (exit 0 over a
        # drifted ledger) rather than a missing constant.
        self.assertNotEqual(rc, 0, "a drifted ledger must not exit 0")
        self.assertNotEqual(rc, 1, "drift is not the mark-resolved branch")
        self.assertEqual(rc, 4)
        self.assertEqual(rc, checksums_io.EXIT_DRIFTED)
        self.assertIn("2 tracked, 0 dirty, 1 drifted, 0 malformed, 0 undeterminable", printed)
        self.assertIn("ontology/domain.yaml", printed)
        self.assertIn("NOT with the file", printed)
        self.assertIn("not a `mark-resolved` job", printed.lower())
        self.assertNotIn("VERDICT: CLEAN", printed)

    def test_missing_tracked_file_exits_nonzero_and_is_not_called_clean(self) -> None:
        """A tracked path absent from the tree is unmeasured, not fine.

        Pre-fix: "1 tracked, 0 dirty, 0 malformed" at exit 0 — the reader
        never opened the file, so its absence was invisible. `prune` is the
        separate, guarded operation for removing such entries; `status` just
        must not count them with the entries it actually checked.
        """
        sha = hashlib.sha256(b"gone").hexdigest()
        with _tmp_dir() as root:
            path = self._seed(root, {"gone.md": {"last_tracked": sha, "last_resolved": sha}})
            with _capture_stdout() as out:
                rc = checksums_io.main(["checksums_io.py", "status", "--checksums", str(path)])
        printed = out.getvalue()
        self.assertNotEqual(rc, 0)
        self.assertEqual(rc, checksums_io.EXIT_DRIFTED)
        self.assertIn("1 undeterminable", printed)
        self.assertIn("gone.md", printed)
        self.assertIn("could NOT be hashed", printed)
        self.assertNotIn("VERDICT: CLEAN", printed)

    def test_drift_outranks_dirty_on_the_exit_channel(self) -> None:
        """When both are present the caller must be sent to the branch whose
        remediation is safe for both, not the one that hides half of it."""
        with _tmp_dir() as root:
            _materialize(root, "dirty.md", "x\n")
            path = self._seed(
                root,
                {
                    "dirty.md": {"last_tracked": "1", "last_resolved": "2"},
                    "drifted.md": _drifted_entry(root, "drifted.md"),
                },
            )
            with _capture_stdout() as out:
                rc = checksums_io.main(["checksums_io.py", "status", "--checksums", str(path)])
        self.assertEqual(rc, checksums_io.EXIT_DRIFTED)
        self.assertIn("1 dirty, 1 drifted", out.getvalue())

    def test_repo_root_flag_checks_the_ledger_against_another_tree(self) -> None:
        """The documented escape for a linked worktree, where the gitignored
        child-repo clones are structurally absent."""
        with _tmp_dir() as tree, _tmp_dir() as elsewhere:
            entry = _clean_entry(tree, "a.md")
            path = self._seed(elsewhere, {"a.md": entry})
            with _capture_stdout():
                without = checksums_io.main(["checksums_io.py", "status", "--checksums", str(path)])
            with _capture_stdout() as out:
                with_root = checksums_io.main(
                    [
                        "checksums_io.py",
                        "status",
                        "--checksums",
                        str(path),
                        "--repo-root",
                        str(tree),
                    ]
                )
        self.assertEqual(without, checksums_io.EXIT_DRIFTED)
        self.assertEqual(with_root, 0)
        self.assertIn("VERDICT: CLEAN", out.getvalue())

    def test_repo_root_flag_requires_a_value(self) -> None:
        with _capture_stderr():
            rc = checksums_io.main(["checksums_io.py", "status", "--repo-root"])
        self.assertEqual(rc, 2)

    def test_malformed_entry_does_not_silently_count_as_clean(self) -> None:
        """The whole point of #1142, at the CLI boundary.

        One well-formed resolved entry plus one entry the reader cannot
        classify. A reader that skips what it does not understand prints
        "0 dirty" and exits 0 — indistinguishable from a healthy ledger, and
        the caller has no way to notice. This asserts the opposite on all
        three channels: nonzero exit, a nonzero malformed count, and the
        offending path named in the output.
        """
        with _tmp_dir() as root:
            path = self._seed(
                root,
                {
                    "ok.md": _clean_entry(root, "ok.md"),
                    "broken.md": {"last_resolved": None, "resolved_at": "2026-06-14T00:16:00Z"},
                },
            )
            with _capture_stdout() as out:
                rc = checksums_io.main(["checksums_io.py", "status", "--checksums", str(path)])
        printed = out.getvalue()
        self.assertNotEqual(rc, 0)
        self.assertEqual(rc, 1)
        self.assertIn("1 malformed", printed)
        self.assertIn("broken.md", printed)
        self.assertIn("missing last_tracked", printed)
        # And it must not be sold as clean anywhere in the report.
        self.assertNotIn("0 malformed", printed)

    def test_unreadable_ledger_exits_three_not_zero(self) -> None:
        """Exit 3, never 0 — "I could not read it" is not "it is clean"."""
        with _tmp_dir() as root:
            path = root / "ontology" / "checksums.json"
            with _capture_stdout() as out, _capture_stderr() as err:
                rc = checksums_io.main(["checksums_io.py", "status", "--checksums", str(path)])
        self.assertEqual(rc, 3)
        self.assertNotIn("0 dirty", out.getvalue())
        self.assertIn("cannot read", err.getvalue())

    def test_malformed_json_exits_three(self) -> None:
        with _tmp_file("{not json") as path:
            with _capture_stdout() as out, _capture_stderr() as err:
                rc = checksums_io.main(["checksums_io.py", "status", "--checksums", str(path)])
        self.assertEqual(rc, 3)
        self.assertNotIn("dirty", out.getvalue())
        self.assertIn("not valid JSON", err.getvalue())

    def test_json_output_is_machine_readable(self) -> None:
        with _tmp_dir() as root:
            path = self._seed(
                root,
                {
                    "dirty.md": {"last_tracked": "1", "last_resolved": "2"},
                    "broken.md": {},
                },
            )
            with _capture_stdout() as out:
                rc = checksums_io.main(
                    ["checksums_io.py", "status", "--checksums", str(path), "--json"]
                )
        payload = json.loads(out.getvalue())
        self.assertEqual(rc, 1)
        self.assertEqual(payload["total"], 2)
        self.assertEqual(payload["dirty"], ["dirty.md"])
        self.assertEqual(payload["malformed"][0]["path"], "broken.md")
        self.assertFalse(payload["clean"])
        # #1505 additions — a JSON consumer must be able to see the new states
        # and, separately, whether any hashing happened at all.
        self.assertEqual(payload["drifted"], [])
        self.assertEqual(payload["undeterminable"], [])
        self.assertTrue(payload["verified"])

    def test_json_channel_reports_drift(self) -> None:
        """The machine-readable channel moves with the other three.

        Pre-fix the object was `{total, dirty, malformed, clean}` with
        `clean: true` for exactly this ledger — a consumer branching on
        `payload["clean"]` had no way to see the drift, whatever the prose
        said.
        """
        with _tmp_dir() as root:
            path = self._seed(
                root,
                {
                    "ok.md": _clean_entry(root, "ok.md"),
                    "drifted.md": _drifted_entry(root, "drifted.md"),
                },
            )
            with _capture_stdout() as out:
                rc = checksums_io.main(
                    ["checksums_io.py", "status", "--checksums", str(path), "--json"]
                )
        payload = json.loads(out.getvalue())
        self.assertFalse(payload["clean"], "a drifted ledger must not serialize as clean")
        self.assertEqual(rc, checksums_io.EXIT_DRIFTED)
        self.assertTrue(payload["verified"])
        self.assertEqual([d["path"] for d in payload["drifted"]], ["drifted.md"])
        self.assertEqual(payload["dirty"], [])
        self.assertIn("repo_root", payload)

    def test_json_channel_reports_undeterminable(self) -> None:
        sha = hashlib.sha256(b"gone").hexdigest()
        with _tmp_dir() as root:
            path = self._seed(root, {"gone.md": {"last_tracked": sha, "last_resolved": sha}})
            with _capture_stdout() as out:
                rc = checksums_io.main(
                    ["checksums_io.py", "status", "--checksums", str(path), "--json"]
                )
        payload = json.loads(out.getvalue())
        self.assertEqual(rc, checksums_io.EXIT_DRIFTED)
        self.assertFalse(payload["clean"])
        self.assertEqual([d["path"] for d in payload["undeterminable"]], ["gone.md"])

    def test_status_never_writes_the_ledger(self) -> None:
        """A reader is read-only — including its byte-for-byte non-touching.

        Hashing gave `status` a reason to open files (#1505); it still has
        none to open this one for writing. The drifted entry is here on
        purpose: detecting drift must not tempt the reader into "fixing" it.
        """
        with _tmp_dir() as root:
            path = self._seed(
                root,
                {
                    "a.md": {"last_tracked": "1", "last_resolved": "2"},
                    "drifted.md": _drifted_entry(root, "drifted.md"),
                },
            )
            before = path.read_bytes()
            with _capture_stdout():
                checksums_io.main(["checksums_io.py", "status", "--checksums", str(path)])
            self.assertEqual(path.read_bytes(), before)

    def test_unexpected_status_argument_is_usage_error(self) -> None:
        with _capture_stderr():
            rc = checksums_io.main(["checksums_io.py", "status", "--bogus"])
        self.assertEqual(rc, 2)

    def test_status_is_reachable_as_a_subprocess(self) -> None:
        """The skills shell out to this — the in-process `main()` call is not
        proof the real invocation works."""
        script = str(Path(__file__).resolve().parent.parent / "checksums_io.py")
        with _tmp_dir() as root:
            path = self._seed(root, {"a.md": _clean_entry(root, "a.md")})
            clean = subprocess.run(
                [sys.executable, script, "status", "--checksums", str(path)],
                capture_output=True,
                text=True,
            )
        with _tmp_dir() as root:
            path = self._seed(root, {"a.md": _drifted_entry(root, "a.md")})
            drifted = subprocess.run(
                [sys.executable, script, "status", "--checksums", str(path)],
                capture_output=True,
                text=True,
            )
        self.assertEqual(clean.returncode, 0)
        self.assertIn("1 tracked, 0 dirty, 0 drifted, 0 malformed, 0 undeterminable", clean.stdout)
        self.assertIn("VERDICT: CLEAN", clean.stdout)
        # The real process exit status, not just `main()`'s return value —
        # this is the byte the skills' `$?` actually sees.
        self.assertEqual(drifted.returncode, 4)
        self.assertIn("1 drifted", drifted.stdout)


if __name__ == "__main__":
    unittest.main()
