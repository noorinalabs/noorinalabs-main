"""Tests for check_checksums_ascii — the ontology/checksums.json no-`\\u`-escape gate (#1044).

Deterministic close for the gap flagged during the merge-gate review of
PR #1040: the tracker hook's ensure_ascii=False is code-enforced, but the
agent-driven /ontology-rebuild resolver's serialization was documentation
only. This gate watches the COMMITTED ARTIFACT itself rather than any one
writer, so it catches a re-escape regardless of which writer caused it.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from check_checksums_ascii import check_file, check_text, main  # noqa: E402

# The real file's shape at head (per #1044's issue body): a top-level
# `description` containing literal em-dash/multiplication-sign, zero escapes.
_CLEAN_SAMPLE = (
    '{\n  "version": 1,\n  "description": "SCOPE (#857, #820/C×T2): '
    'semantic overlay — not structural",\n  "files": {}\n}\n'
)

# The exact defect shape: the SAME content re-escaped by ensure_ascii=True.
_ESCAPED_SAMPLE = (
    '{\n  "version": 1,\n  "description": "SCOPE (#857, #820/C\\u00d7T2): '
    'semantic overlay \\u2014 not structural",\n  "files": {}\n}\n'
)


class CheckTextTests(unittest.TestCase):
    def test_clean_literal_utf8_passes(self) -> None:
        self.assertEqual(check_text("checksums.json", _CLEAN_SAMPLE), [])

    def test_escaped_utf8_is_flagged(self) -> None:
        violations = check_text("checksums.json", _ESCAPED_SAMPLE)
        self.assertEqual(len(violations), 1)
        self.assertIn("checksums.json", violations[0])
        self.assertIn("\\u", violations[0])

    def test_violation_message_includes_the_path(self) -> None:
        violations = check_text("some/path/checksums.json", _ESCAPED_SAMPLE)
        self.assertTrue(violations[0].startswith("some/path/checksums.json:"))

    def test_escape_count_is_reported(self) -> None:
        text = '{"a": "\\u0041", "b": "\\u0042"}'
        violations = check_text("f.json", text)
        self.assertIn("2 '\\u'", violations[0])

    def test_empty_file_passes(self) -> None:
        self.assertEqual(check_text("checksums.json", ""), [])

    def test_plain_ascii_with_no_escapes_passes(self) -> None:
        self.assertEqual(check_text("checksums.json", '{"version": 1, "files": {}}\n'), [])


class CheckFileTests(unittest.TestCase):
    def test_missing_file_is_not_a_violation(self) -> None:
        """Nothing has been written yet — a distinct concern from re-escaping."""
        missing = Path("/nonexistent/path/checksums.json")
        self.assertEqual(check_file(missing), [])

    def test_clean_file_on_disk_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "checksums.json"
            path.write_text(_CLEAN_SAMPLE, encoding="utf-8")
            self.assertEqual(check_file(path), [])

    def test_escaped_file_on_disk_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "checksums.json"
            path.write_text(_ESCAPED_SAMPLE, encoding="utf-8")
            violations = check_file(path)
            self.assertEqual(len(violations), 1)


class MainCliTests(unittest.TestCase):
    def test_clean_default_path_exits_zero(self) -> None:
        """The real ontology/checksums.json, checked via its default path resolution."""
        rc = main(["check_checksums_ascii.py"])
        self.assertEqual(rc, 0)

    def test_explicit_clean_file_exits_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "checksums.json"
            path.write_text(_CLEAN_SAMPLE, encoding="utf-8")
            rc = main(["check_checksums_ascii.py", str(path)])
            self.assertEqual(rc, 0)

    def test_explicit_escaped_file_exits_one(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "checksums.json"
            path.write_text(_ESCAPED_SAMPLE, encoding="utf-8")
            rc = main(["check_checksums_ascii.py", str(path)])
            self.assertEqual(rc, 1)

    def test_missing_explicit_file_exits_zero(self) -> None:
        rc = main(["check_checksums_ascii.py", "/nonexistent/checksums.json"])
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
