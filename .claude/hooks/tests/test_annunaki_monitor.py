#!/usr/bin/env python3
"""Tests for `annunaki_monitor.check()` — PostToolUse Bash error capture.

Issue #472 fix coverage: silent-failure commands (non-zero exit, no
stdout/stderr) must produce a log entry. The pre-fix early-return on
empty `combined_output` short-circuited this path.

Run from the repo root:
    python3 -m pytest .claude/hooks/tests/test_annunaki_monitor.py -v
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
sys.path.insert(0, str(_HOOKS_DIR))

import annunaki_log as alog  # noqa: E402
import annunaki_monitor as am  # noqa: E402


def _bash_event(command: str, stdout: str = "", stderr: str = "", exit_code: int = 0) -> dict:
    return {
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "tool_response": {"stdout": stdout, "stderr": stderr, "exit_code": exit_code},
    }


def _read_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out


class AnnunakiMonitorTests(unittest.TestCase):
    """End-to-end coverage of `check()` for the cases that matter to #472."""

    def setUp(self):
        # Force production-mode so append_jsonl_record actually writes.
        self._saved_env = {
            "ENVIRONMENT": os.environ.pop("ENVIRONMENT", None),
            "NOORIN_HOOK_TEST_MODE": os.environ.pop("NOORIN_HOOK_TEST_MODE", None),
        }
        # Reset session-level dedup so test order is independent.
        am._seen_hashes.clear()
        # Redirect ERRORS_FILE to a tmp path.
        self._tmpdir = tempfile.TemporaryDirectory()
        self._errors_path = Path(self._tmpdir.name) / "errors.jsonl"
        self._orig_monitor_file = am.ERRORS_FILE
        self._orig_log_file = alog.ERRORS_FILE
        am.ERRORS_FILE = self._errors_path
        alog.ERRORS_FILE = self._errors_path

    def tearDown(self):
        am.ERRORS_FILE = self._orig_monitor_file
        alog.ERRORS_FILE = self._orig_log_file
        self._tmpdir.cleanup()
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    # --- #472 regression: silent-failure path ---

    def test_silent_failure_logged(self):
        """`false`-style command: exit 1, empty stdout/stderr → must log."""
        result = am.check(_bash_event("false", exit_code=1))
        self.assertIsNotNone(result, "silent failure must produce a record")
        self.assertEqual(result.get("action"), "logged")

        records = _read_records(self._errors_path)
        self.assertEqual(len(records), 1, "exactly one record for one silent failure")
        rec = records[0]
        self.assertEqual(rec["exit_code"], 1)
        self.assertEqual(rec["command"], "false")
        self.assertIn("exit_code=1", rec["matched_patterns"])
        self.assertEqual(rec["error_lines"], [], "no output → no extractable lines")

    def test_silent_failure_higher_exit_code_logged(self):
        """exit 137 (SIGKILL) with no output → logged with exit_code marker."""
        result = am.check(_bash_event("kill -9 $$", exit_code=137))
        self.assertIsNotNone(result)
        records = _read_records(self._errors_path)
        self.assertEqual(records[0]["exit_code"], 137)
        self.assertIn("exit_code=137", records[0]["matched_patterns"])

    # --- regression guards for the previously working paths ---

    def test_stderr_failure_logged(self):
        """`cat /nonexistent` shape: exit 1, stderr present → logs."""
        result = am.check(
            _bash_event(
                "cat /nonexistent",
                stderr="cat: /nonexistent: No such file or directory\n",
                exit_code=1,
            )
        )
        self.assertIsNotNone(result)
        rec = _read_records(self._errors_path)[0]
        self.assertEqual(rec["exit_code"], 1)
        # exit_code marker AND stderr-pattern marker both expected
        self.assertIn("exit_code=1", rec["matched_patterns"])
        self.assertTrue(any("No such file" in p for p in rec["matched_patterns"]))

    def test_stdout_pattern_match_logged_when_exit_zero(self):
        """Soft-failure: exit 0 but stdout has `Traceback` → still logs."""
        result = am.check(
            _bash_event(
                "python3 script.py",
                stdout="Traceback (most recent call last):\n  File ...\nValueError: x\n",
                exit_code=0,
            )
        )
        self.assertIsNotNone(result)
        rec = _read_records(self._errors_path)[0]
        self.assertEqual(rec["exit_code"], 0)
        self.assertTrue(rec["error_lines"], "stdout error lines should be extracted")

    # --- false-positive guards ---

    def test_exit_zero_no_output_returns_none(self):
        """Successful silent command → no record."""
        result = am.check(_bash_event("true", exit_code=0))
        self.assertIsNone(result)
        self.assertFalse(self._errors_path.exists())

    def test_exit_zero_clean_output_returns_none(self):
        """Successful command with normal stdout → no record."""
        result = am.check(_bash_event("ls /tmp", stdout="file1\nfile2\n", exit_code=0))
        self.assertIsNone(result)
        self.assertFalse(self._errors_path.exists())

    def test_should_ignore_grep_for_error_short_circuits(self):
        """`grep -i error` commands are filtered as false positives."""
        result = am.check(
            _bash_event(
                "grep -i error logs.txt",
                stdout="some_error_log_entry\n",
                exit_code=0,
            )
        )
        self.assertIsNone(result, "grep-for-error commands must be ignored")

    # --- dedup ---

    def test_session_dedup_skips_duplicate(self):
        """Same silent failure twice in one session → only one log entry."""
        am.check(_bash_event("false", exit_code=1))
        second = am.check(_bash_event("false", exit_code=1))
        self.assertIsNone(second, "second identical failure must be deduped")
        self.assertEqual(len(_read_records(self._errors_path)), 1)

    def test_non_bash_tool_ignored(self):
        """Hook only fires on Bash; Edit/Write events return None."""
        result = am.check({"tool_name": "Edit", "tool_response": {"exit_code": 1}})
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
