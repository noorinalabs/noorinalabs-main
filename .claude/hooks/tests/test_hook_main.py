#!/usr/bin/env python3
"""Tests for _hook_main.py — the shared standalone main() bodies (main#1121).

Mutation-focused (feedback_both_ends_tested_join_untested): both the
"decision" branch AND the "no decision" branch are exercised for every exit
code, not just one representative case.

Run:  python3 -m pytest .claude/hooks/tests/test_hook_main.py -v
"""

from __future__ import annotations

import io
import json
import sys
import unittest
from unittest import mock

# This file's own hook-side import (`_hook_main`) is an
# underscore-prefixed module whose name sorts alphabetically before
# `_test_helpers` — ruff's isort autofix would otherwise reorder it
# ahead of the sys.path bootstrap it depends on. See
# `_test_helpers.py`'s module docstring.
# isort: skip_file
import _test_helpers  # noqa: E402,F401

import _hook_main as hm  # noqa: E402


def _run(fn, check_fn, hook_name: str, stdin_text: str) -> tuple[int, str]:
    """Run `fn(check_fn, hook_name)` against literal stdin text.

    Returns (exit_code, stdout_text). SystemExit is captured so the test can
    assert the exit code without terminating the test runner. A `fn` that
    falls off the end without calling sys.exit() (a mutant, or a bug) is
    treated as exit code None (distinguishable from an explicit 0).
    """
    stdin = io.StringIO(stdin_text)
    stdout = io.StringIO()
    with mock.patch.object(sys, "stdin", stdin), mock.patch.object(sys, "stdout", stdout):
        try:
            fn(check_fn, hook_name)
        except SystemExit as e:
            code = int(e.code) if e.code is not None else 0
            return code, stdout.getvalue()
    raise AssertionError(f"{fn.__name__} returned without calling sys.exit()")


class MalformedStdinTests(unittest.TestCase):
    """Every malformed-input shape must exit 0 silently, for BOTH helpers."""

    def _assert_malformed_allows(self, fn) -> None:
        never_called = mock.MagicMock()
        for stdin_text in ("", "not json at all", "{unterminated", "   "):
            with self.subTest(stdin_text=stdin_text):
                code, out = _run(fn, never_called, "some_hook", stdin_text)
                self.assertEqual(code, 0)
                self.assertEqual(out, "")
        never_called.assert_not_called()

    def test_run_blocking_malformed_stdin_exits_zero(self) -> None:
        self._assert_malformed_allows(hm.run_blocking)

    def test_run_advisory_malformed_stdin_exits_zero(self) -> None:
        self._assert_malformed_allows(hm.run_advisory)

    def test_unicode_decode_error_exits_zero(self) -> None:
        """UnicodeDecodeError was not guarded by ANY hook pre-#1121 — this is
        the closed gap the module docstring documents. Simulated by making
        stdin.read() raise it directly (json.load calls fp.read())."""
        never_called = mock.MagicMock()
        bad_stdin = mock.MagicMock()
        bad_stdin.read.side_effect = UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid")
        stdout = io.StringIO()
        with (
            mock.patch.object(sys, "stdin", bad_stdin),
            mock.patch.object(sys, "stdout", stdout),
        ):
            with self.assertRaises(SystemExit) as ctx:
                hm.run_blocking(never_called, "some_hook")
        self.assertEqual(ctx.exception.code, 0)
        never_called.assert_not_called()


class RunBlockingTests(unittest.TestCase):
    def test_none_result_exits_zero_no_output(self) -> None:
        check = mock.MagicMock(return_value=None)
        code, out = _run(hm.run_blocking, check, "h", "{}")
        self.assertEqual(code, 0)
        self.assertEqual(out, "")
        check.assert_called_once_with({})

    def test_empty_dict_result_exits_zero_no_output(self) -> None:
        """An empty dict is falsy — same "no advisory" path as None."""
        check = mock.MagicMock(return_value={})
        code, out = _run(hm.run_blocking, check, "h", "{}")
        self.assertEqual(code, 0)
        self.assertEqual(out, "")

    def test_allow_with_message_prints_and_exits_zero(self) -> None:
        check = mock.MagicMock(return_value={"decision": "allow", "systemMessage": "hi"})
        code, out = _run(hm.run_blocking, check, "h", "{}")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), {"decision": "allow", "systemMessage": "hi"})

    def test_block_prints_and_exits_two(self) -> None:
        check = mock.MagicMock(return_value={"decision": "block", "reason": "no"})
        code, out = _run(hm.run_blocking, check, "h", "{}")
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out), {"decision": "block", "reason": "no"})

    def test_result_without_decision_key_does_not_block(self) -> None:
        """Only decision == "block" blocks — a dict with no "decision" key
        must NOT be treated as a block (this is the dialect-3 case
        enforce_ontology_context.py used to special-case differently; its
        check() never actually returns this shape, but the helper itself
        must still get the general contract right)."""
        check = mock.MagicMock(return_value={"systemMessage": "advisory only"})
        code, out = _run(hm.run_blocking, check, "h", "{}")
        self.assertEqual(code, 0)
        self.assertIn("advisory only", out)

    def test_check_fn_receives_parsed_stdin(self) -> None:
        check = mock.MagicMock(return_value=None)
        _run(hm.run_blocking, check, "h", json.dumps({"tool_name": "Bash"}))
        check.assert_called_once_with({"tool_name": "Bash"})

    @mock.patch.object(hm, "log_pretooluse_diagnostic")
    def test_exception_is_swallowed_logged_and_exits_zero(self, mock_log) -> None:
        check = mock.MagicMock(side_effect=RuntimeError("boom"))
        code, out = _run(
            hm.run_blocking, check, "h", json.dumps({"tool_name": "Bash", "tool_input": {}})
        )
        self.assertEqual(code, 0, "an exception must never crash or block")
        self.assertEqual(out, "")
        mock_log.assert_called_once()
        # Loud, not silent: the swallow logs the hook name and exception text.
        args, kwargs = mock_log.call_args
        self.assertEqual(args[0], "h")
        self.assertIn("RuntimeError: boom", str(args[2]) + str(kwargs))

    def test_logging_failure_does_not_crash_the_hook(self) -> None:
        """Logging is itself best-effort — a broken log sink must not turn
        a swallowed exception into a crashing one."""
        check = mock.MagicMock(side_effect=RuntimeError("boom"))
        with mock.patch.object(hm, "log_pretooluse_diagnostic", side_effect=OSError("disk full")):
            code, out = _run(hm.run_blocking, check, "h", "{}")
        self.assertEqual(code, 0)
        self.assertEqual(out, "")

    def test_non_dict_json_top_level_does_not_crash(self) -> None:
        """Valid JSON that isn't an object (e.g. a bare list) makes a typical
        check_fn's input_data.get(...) raise AttributeError — that exception
        must be swallowed like any other, not propagate."""

        def check(input_data):
            return input_data.get("tool_name")  # AttributeError on a list

        code, out = _run(hm.run_blocking, check, "h", "[1, 2, 3]")
        self.assertEqual(code, 0)
        self.assertEqual(out, "")


class RunAdvisoryTests(unittest.TestCase):
    def test_none_result_exits_zero_no_output(self) -> None:
        check = mock.MagicMock(return_value=None)
        code, out = _run(hm.run_advisory, check, "h", "{}")
        self.assertEqual(code, 0)
        self.assertEqual(out, "")

    def test_message_result_prints_but_still_exits_zero(self) -> None:
        check = mock.MagicMock(return_value={"systemMessage": "fyi"})
        code, out = _run(hm.run_advisory, check, "h", "{}")
        self.assertEqual(code, 0)
        self.assertIn("fyi", out)

    def test_block_decision_result_is_printed_but_never_exits_two(self) -> None:
        """The load-bearing distinction from run_blocking: an advisory hook
        NEVER exits 2, even if its check() returns a decision:block-shaped
        dict (which would be a caller bug, but the helper's own contract
        must not silently upgrade an advisory hook into a gate)."""
        check = mock.MagicMock(return_value={"decision": "block", "reason": "irrelevant here"})
        code, out = _run(hm.run_advisory, check, "h", "{}")
        self.assertEqual(code, 0, "run_advisory must never exit 2")
        self.assertIn("irrelevant here", out)

    @mock.patch.object(hm, "log_pretooluse_diagnostic")
    def test_exception_is_swallowed_logged_and_exits_zero(self, mock_log) -> None:
        check = mock.MagicMock(side_effect=ValueError("nope"))
        code, out = _run(hm.run_advisory, check, "h", "{}")
        self.assertEqual(code, 0)
        self.assertEqual(out, "")
        mock_log.assert_called_once()


class CommandExcerptTests(unittest.TestCase):
    """Direct bite-tests on the diagnostic-excerpt fallback chain (#1318 —
    an instrument this thorough deserves direct coverage, not only via the
    swallow path above)."""

    def test_bash_command_excerpt(self) -> None:
        excerpt = hm._command_excerpt({"tool_input": {"command": "echo hi"}})
        self.assertEqual(excerpt, "echo hi")

    def test_file_path_fallback(self) -> None:
        excerpt = hm._command_excerpt({"tool_input": {"file_path": "/tmp/x.py"}})
        self.assertEqual(excerpt, "/tmp/x.py")

    def test_notebook_path_fallback(self) -> None:
        excerpt = hm._command_excerpt({"tool_input": {"notebook_path": "/tmp/x.ipynb"}})
        self.assertEqual(excerpt, "/tmp/x.ipynb")

    def test_non_dict_tool_input_stringified(self) -> None:
        excerpt = hm._command_excerpt({"tool_input": "weird"})
        self.assertEqual(excerpt, "weird")

    def test_non_dict_input_data_stringified(self) -> None:
        excerpt = hm._command_excerpt([1, 2, 3])
        self.assertEqual(excerpt, "[1, 2, 3]")


if __name__ == "__main__":
    unittest.main()
