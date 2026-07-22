"""Tests for checksums_io — the shared ontology/checksums.json read/write helper (#1042).

Closes the gap left by #1040 (which fixed the ensure_ascii=True re-escaping
churn only in the one code-enforced writer, ontology_tracker.py, leaving the
agent-driven /ontology-rebuild resolver's serialization a documentation-only
convention with nothing to attach a test to). This module gives the resolver
a real CLI subcommand (`mark-resolved`) to shell out to instead, so the
byte-stability contract is enforced by code on BOTH writers, not just one.
"""

from __future__ import annotations

import json
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


if __name__ == "__main__":
    unittest.main()
