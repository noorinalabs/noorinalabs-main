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

    def test_explicit_repo_root_is_honored(self) -> None:
        with _tmp_dir() as root:
            elsewhere = root / "elsewhere"
            elsewhere.mkdir()
            (elsewhere / "kept.md").write_text("x", encoding="utf-8")
            path = self._seed(root, {"kept.md": {"last_tracked": "s"}})
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
            self.assertEqual(rc, 0)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(list(data["files"]), ["kept.md"])

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

    def test_clean_ledger_is_clean(self) -> None:
        status = checksums_io.compute_status(
            {"files": {"a.md": {"last_tracked": "1", "last_resolved": "1"}}}
        )
        self.assertTrue(status.clean)
        self.assertEqual((status.total, status.dirty, status.malformed), (1, (), ()))

    def test_empty_ledger_is_clean(self) -> None:
        status = checksums_io.compute_status({"files": {}})
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
        with _tmp_dir() as root:
            path = self._seed(root, {"a.md": {"last_tracked": "1", "last_resolved": "1"}})
            with _capture_stdout() as out:
                rc = checksums_io.main(["checksums_io.py", "status", "--checksums", str(path)])
        self.assertEqual(rc, 0)
        self.assertIn("1 tracked, 0 dirty, 0 malformed", out.getvalue())

    def test_dirty_ledger_reports_count_and_paths(self) -> None:
        with _tmp_dir() as root:
            path = self._seed(
                root,
                {
                    "a.md": {"last_tracked": "1", "last_resolved": "1"},
                    "team/trust_matrix.md": {"last_tracked": "3fe1", "last_resolved": "d35e"},
                },
            )
            with _capture_stdout() as out:
                rc = checksums_io.main(["checksums_io.py", "status", "--checksums", str(path)])
        printed = out.getvalue()
        self.assertEqual(rc, 1)
        self.assertIn("2 tracked, 1 dirty, 0 malformed", printed)
        self.assertIn("team/trust_matrix.md", printed)

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
                    "ok.md": {"last_tracked": "1", "last_resolved": "1"},
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

    def test_status_never_writes_the_ledger(self) -> None:
        """A reader is read-only — including its byte-for-byte non-touching."""
        with _tmp_dir() as root:
            path = self._seed(root, {"a.md": {"last_tracked": "1", "last_resolved": "2"}})
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
        with _tmp_dir() as root:
            path = self._seed(root, {"a.md": {"last_tracked": "1", "last_resolved": "1"}})
            proc = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve().parent.parent / "checksums_io.py"),
                    "status",
                    "--checksums",
                    str(path),
                ],
                capture_output=True,
                text=True,
            )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("1 tracked, 0 dirty, 0 malformed", proc.stdout)


if __name__ == "__main__":
    unittest.main()
