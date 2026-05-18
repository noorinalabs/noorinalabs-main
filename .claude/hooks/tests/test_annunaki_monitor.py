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


class SilentBooleanTestIdiomTests(unittest.TestCase):
    """#474 coverage: documented boolean-test idioms whose by-design failure
    branch is non-zero exit with empty output must NOT produce log entries
    after #473 closed the silent-failure capture path. Each idiom gets a
    NEGATIVE-match test (no log) plus a precedence test that confirms a real
    stderr-pattern match still wins."""

    def setUp(self):
        self._saved_env = {
            "ENVIRONMENT": os.environ.pop("ENVIRONMENT", None),
            "NOORIN_HOOK_TEST_MODE": os.environ.pop("NOORIN_HOOK_TEST_MODE", None),
        }
        am._seen_hashes.clear()
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

    # --- Each documented idiom: NEG match on silent exit-1 ---

    def test_posix_bracket_silent_exit_not_logged(self):
        """NEG: `[ -d /nonexistent ]` exit 1 silent → no log."""
        result = am.check(_bash_event("[ -d /nonexistent ]", exit_code=1))
        self.assertIsNone(result)
        self.assertFalse(self._errors_path.exists())

    def test_bash_double_bracket_silent_exit_not_logged(self):
        """NEG: `[[ -f /nonexistent ]]` exit 1 silent → no log."""
        result = am.check(_bash_event("[[ -f /nonexistent ]]", exit_code=1))
        self.assertIsNone(result)

    def test_test_builtin_silent_exit_not_logged(self):
        """NEG: `test -f /nonexistent` exit 1 silent → no log."""
        result = am.check(_bash_event("test -f /nonexistent", exit_code=1))
        self.assertIsNone(result)

    def test_grep_q_no_match_silent_exit_not_logged(self):
        """NEG: `grep -q pattern file` non-error miss → no log."""
        result = am.check(_bash_event("grep -q needle /tmp/haystack.txt", exit_code=1))
        self.assertIsNone(result)

    def test_grep_q_with_flags_silent_exit_not_logged(self):
        """NEG: `grep -qE` / `grep -qi` variants → no log."""
        for cmd in ("grep -qE '^foo' f.txt", "grep -qi BAR f.txt", "grep -Eq '^foo' f.txt"):
            am._seen_hashes.clear()
            result = am.check(_bash_event(cmd, exit_code=1))
            self.assertIsNone(result, f"{cmd!r} must not log")

    def test_pgrep_no_match_silent_exit_not_logged(self):
        """NEG: `pgrep nginx` not-running → no log."""
        result = am.check(_bash_event("pgrep nginx", exit_code=1))
        self.assertIsNone(result)

    def test_pkill_no_match_silent_exit_not_logged(self):
        """NEG: `pkill -0 nginx` not-running → no log."""
        result = am.check(_bash_event("pkill -0 nginx", exit_code=1))
        self.assertIsNone(result)

    def test_which_not_found_silent_exit_not_logged(self):
        """NEG: `which foo` not-installed → no log."""
        result = am.check(_bash_event("which nonexistent-binary", exit_code=1))
        self.assertIsNone(result)

    def test_command_v_not_found_silent_exit_not_logged(self):
        """NEG: `command -v foo` not-installed → no log."""
        result = am.check(_bash_event("command -v nonexistent-binary", exit_code=1))
        self.assertIsNone(result)

    def test_diff_quiet_differs_silent_exit_not_logged(self):
        """NEG: `diff --quiet a b` files differ → no log."""
        result = am.check(_bash_event("diff --quiet /tmp/a /tmp/b", exit_code=1))
        self.assertIsNone(result)

    def test_git_diff_quiet_dirty_silent_exit_not_logged(self):
        """NEG: `git diff --quiet` working tree dirty → no log."""
        result = am.check(_bash_event("git diff --quiet", exit_code=1))
        self.assertIsNone(result)

    def test_if_bracket_conditional_false_branch_exit_zero_not_logged(self):
        """NEG: `if [ -f /nonexistent ]; then echo unreachable; fi` exits 0
        (false branch, body skipped) → no log. The whole-`if` regex was
        removed in #490 because it silenced body failures (gap #3); the
        false-branch path is now handled by exit_code=0 not being an error,
        not by idiom-skip."""
        result = am.check(
            _bash_event("if [ -f /nonexistent ]; then echo unreachable; fi", exit_code=0)
        )
        self.assertIsNone(result)

    def test_if_double_bracket_conditional_false_branch_exit_zero_not_logged(self):
        """NEG: same shape with `[[`. exit 0 → no log."""
        result = am.check(
            _bash_event("if [[ -f /nonexistent ]]; then echo unreachable; fi", exit_code=0)
        )
        self.assertIsNone(result)

    # --- Precedence: pattern match wins over idiom-on-silent-exit ---

    def test_idiom_with_stderr_pattern_still_logged(self):
        """POS: `[ -f x ]` would normally be silent-skip, BUT if stderr has
        a real error pattern (e.g., `fatal:`), it still logs. Pattern matches
        take precedence — the idiom-skip only suppresses the bare exit_code
        signal."""
        result = am.check(
            _bash_event(
                "[ -f /nonexistent ]",
                stderr="fatal: unexpected internal state\n",
                exit_code=1,
            )
        )
        self.assertIsNotNone(result, "stderr pattern match must override idiom skip")
        rec = _read_records(self._errors_path)[0]
        # Both signals present: exit_code AND stderr pattern
        self.assertIn("exit_code=1", rec["matched_patterns"])
        self.assertTrue(any("fatal" in p for p in rec["matched_patterns"]))

    def test_idiom_with_stdout_pattern_still_logged(self):
        """POS: silent-test idiom that produces a stdout Traceback (would be
        absurd in reality, but the precedence rule must hold) → logs."""
        result = am.check(
            _bash_event(
                "test -f /nonexistent",
                stdout="Traceback (most recent call last):\nValueError: x\n",
                exit_code=1,
            )
        )
        self.assertIsNotNone(result)

    def test_real_silent_failure_still_logged(self):
        """POS regression for #472: `false` is NOT in the idiom list, so the
        silent-failure capture path still works for non-idiom commands."""
        result = am.check(_bash_event("false", exit_code=1))
        self.assertIsNotNone(result, "non-idiom silent failures must still log")

    def test_idiom_exit_zero_not_logged(self):
        """NEG: idiom command exits 0 (true branch) → no log because not
        even is_error=True. Sanity check that the idiom filter doesn't get
        in the way of the happy path."""
        result = am.check(_bash_event("[ -f /tmp ]", exit_code=0))
        self.assertIsNone(result)


class AinoFollowupTests(unittest.TestCase):
    """Aino's two non-blocking follow-up cases from PR #473 review."""

    def setUp(self):
        self._saved_env = {
            "ENVIRONMENT": os.environ.pop("ENVIRONMENT", None),
            "NOORIN_HOOK_TEST_MODE": os.environ.pop("NOORIN_HOOK_TEST_MODE", None),
        }
        am._seen_hashes.clear()
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

    def test_exit_zero_with_stderr_pattern_still_captured(self):
        """Aino #1: command succeeds (exit 0) but stderr contains a pattern
        like `error:` → must still log via stderr pattern match. Guards
        against a future refactor that gates pattern matching on a non-zero
        exit code."""
        result = am.check(
            _bash_event(
                "some-tool --warn",
                stderr="error: deprecated flag --warn used, ignored\n",
                exit_code=0,
            )
        )
        self.assertIsNotNone(result, "exit-0 with stderr error pattern must capture")
        rec = _read_records(self._errors_path)[0]
        self.assertEqual(rec["exit_code"], 0)
        self.assertTrue(any("error" in p for p in rec["matched_patterns"]))

    def test_ignore_pattern_takes_precedence_over_nonzero_exit(self):
        """Aino #2: command matches `_should_ignore` (e.g., `grep -i error`)
        AND exits non-zero → ignore-pattern check fires before exit-code
        capture, so no log. Guards against the exit-code capture path
        bypassing the false-positive guards from `_should_ignore`."""
        result = am.check(
            _bash_event(
                "grep -i error logs.txt",
                exit_code=1,
            )
        )
        self.assertIsNone(result, "_should_ignore must precede exit-code capture")
        self.assertFalse(self._errors_path.exists())


class IdiomTighteningTests(unittest.TestCase):
    """#490 coverage: the 3 gaps + micro-cleanup Aisha surfaced on PR #481's
    secondary review. Headline regression case is gap #3 — `if [ ... ]; then
    real-failure; fi` must log the body's exit-1 failure, not be silenced."""

    def setUp(self):
        self._saved_env = {
            "ENVIRONMENT": os.environ.pop("ENVIRONMENT", None),
            "NOORIN_HOOK_TEST_MODE": os.environ.pop("NOORIN_HOOK_TEST_MODE", None),
        }
        am._seen_hashes.clear()
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

    # --- Gap #1: split-flag grep -q forms ---

    def test_grep_split_flag_dash_E_dash_q_silent_exit_not_logged(self):
        """NEG (#490 gap #1): `grep -E -q pattern file` exit 1 silent → no
        log. Split-flag form was missed by the combined-flag-only regex
        before tightening."""
        result = am.check(_bash_event("grep -E -q '^foo' /tmp/file.txt", exit_code=1))
        self.assertIsNone(result, "split-flag `grep -E -q` must skip")

    def test_grep_split_flag_dash_i_dash_q_silent_exit_not_logged(self):
        """NEG (#490 gap #1): `grep -i -q pattern file` exit 1 silent → no
        log. Order-independent."""
        result = am.check(_bash_event("grep -i -q bar /tmp/file.txt", exit_code=1))
        self.assertIsNone(result)

    # --- Gap #2: diff --quiet exit_code discrimination ---

    def test_diff_quiet_exit_2_trouble_logged(self):
        """POS (#490 gap #2): `diff --quiet a b` exit 2 (couldn't open,
        permission denied) → MUST log even with empty stderr. Exit 2 is
        "trouble", not by-design differs-signal."""
        result = am.check(_bash_event("diff --quiet /tmp/a /tmp/b", exit_code=2))
        self.assertIsNotNone(result, "diff --quiet exit=2 trouble must log")
        rec = _read_records(self._errors_path)[0]
        self.assertEqual(rec["exit_code"], 2)
        self.assertIn("exit_code=2", rec["matched_patterns"])

    def test_git_diff_quiet_exit_2_trouble_logged(self):
        """POS (#490 gap #2): git diff --quiet variant of the trouble exit
        discrimination. Exit 2 → log."""
        result = am.check(_bash_event("git diff --quiet", exit_code=2))
        self.assertIsNotNone(result, "git diff --quiet exit=2 trouble must log")

    def test_diff_quiet_exit_1_differs_still_skipped(self):
        """NEG (#490 gap #2 regression guard): exit 1 (the by-design
        differs-signal) → still skipped per #474. The fix narrows the skip
        condition, doesn't broaden the log condition."""
        result = am.check(_bash_event("diff --quiet /tmp/a /tmp/b", exit_code=1))
        self.assertIsNone(result, "diff --quiet exit=1 differs is still by-design")

    # --- Gap #3 HEADLINE: if [ ...; ]; then real-failure; fi must log ---

    def test_if_bracket_with_failing_body_logged(self):
        """POS (#490 gap #3 HEADLINE): `if [ -d /tmp ]; then false; fi`
        exit 1 (body failed, condition was truthy) → MUST log. This was the
        regression case — the old `^\\s*if\\s+\\[` regex matched the outer
        `if [` and suppressed the real body failure."""
        result = am.check(_bash_event("if [ -d /tmp ]; then false; fi", exit_code=1))
        self.assertIsNotNone(
            result, "if-conditional body failure must log; idiom-skip must not silence it"
        )
        rec = _read_records(self._errors_path)[0]
        self.assertEqual(rec["exit_code"], 1)

    def test_if_double_bracket_with_failing_body_logged(self):
        """POS (#490 gap #3): `[[` variant of the headline case → log."""
        result = am.check(_bash_event("if [[ -d /tmp ]]; then false; fi", exit_code=1))
        self.assertIsNotNone(result)

    def test_if_bracket_false_condition_exit_zero_skipped(self):
        """NEG (#490 gap #3 invariant): false condition (exit 0 because
        else-branch is empty / body not entered) → no log. Preserves the
        existing "happy path of the false branch is silent" behavior."""
        result = am.check(
            _bash_event("if [ -d /nonexistent ]; then echo unreachable; fi", exit_code=0)
        )
        self.assertIsNone(result, "false-condition exit-0 stays silent")

    # --- Micro-cleanup: redundant `^\s*\[\[` removal regression guard ---

    def test_bash_double_bracket_still_skipped_after_dedup(self):
        """NEG (#490 micro-cleanup regression guard): `[[ -f x ]]` exit 1
        silent → no log. The line-79 `^\\s*\\[\\[` regex was removed because
        `^\\s*\\[` already matches `[[` (both start with `[`). This test
        confirms `[[` is still covered by the dedup'd list."""
        result = am.check(_bash_event("[[ -f /nonexistent ]]", exit_code=1))
        self.assertIsNone(result, "[[ idiom must still skip after dedup")


if __name__ == "__main__":
    unittest.main(verbosity=2)
