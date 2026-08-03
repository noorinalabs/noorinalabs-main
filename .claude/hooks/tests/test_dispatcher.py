#!/usr/bin/env python3
"""Tests for dispatcher.py — PreToolUse single-entry dispatcher (#1114).

Mirrors the structure of `test_post_dispatcher.py` (the PostToolUse sibling)
but for PreToolUse semantics: hooks CAN block (`decision: "block"` short-
circuits with exit 2), non-blocking `systemMessage` returns aggregate, and a
tool_name with no matcher entry dispatches nothing.

Prior to #1114 this dispatcher routed ONLY `Bash` (hardcoded); Edit/Write/
NotebookEdit ran via three separate standalone `settings.json` subprocess
entries each (`enforce_librarian_consulted.py` + `validate_edit_completion.py`).
#1114 added a matcher table (`_MATCHER_CFG_KEY`, mirroring `post_dispatcher.py`)
so all four tool types route through this one dispatcher, reading their module
list from `hooks.pre_bash` / `hooks.pre_file` / `hooks.pre_notebook`.

Run:  python3 -m pytest .claude/hooks/tests/test_dispatcher.py -v
"""

from __future__ import annotations

import io
import json
import sys
import unittest
from unittest import mock

import __test_helpers  # noqa: E402,F401

_REPO_ROOT = __test_helpers.HOOKS_DIR.parent.parent


import dispatcher as d  # noqa: E402


def _run_dispatcher(input_data: dict) -> tuple[int, str]:
    """Run `dispatcher.main()` against the given stdin dict.

    Returns (exit_code, stdout_text). `SystemExit` is captured so the test
    can assert exit code without terminating the test runner.
    """
    stdin = io.StringIO(json.dumps(input_data))
    stdout = io.StringIO()
    with mock.patch.object(sys, "stdin", stdin), mock.patch.object(sys, "stdout", stdout):
        try:
            d.main()
        except SystemExit as e:
            code = int(e.code) if e.code is not None else 0
            return code, stdout.getvalue()
    return 0, stdout.getvalue()


class MatcherTableTests(unittest.TestCase):
    """The matcher table maps every dispatched tool_name to the right config key."""

    def test_matcher_table_shape(self) -> None:
        self.assertEqual(
            d._MATCHER_CFG_KEY,
            {
                "Bash": "hooks.pre_bash",
                "Edit": "hooks.pre_file",
                "Write": "hooks.pre_file",
                "NotebookEdit": "hooks.pre_notebook",
            },
        )

    def test_edit_and_write_share_module_list(self) -> None:
        self.assertEqual(d._modules_for("Edit"), d._modules_for("Write"))

    def test_unregistered_tool_name_resolves_to_empty(self) -> None:
        self.assertEqual(d._modules_for("Read"), [])
        self.assertEqual(d._modules_for("SendMessage"), [])

    def test_bash_resolves_pre_bash_list(self) -> None:
        self.assertIn("validate_commit_identity", d._modules_for("Bash"))

    def test_edit_resolves_pre_file_list(self) -> None:
        modules = d._modules_for("Edit")
        self.assertIn("enforce_librarian_consulted", modules)
        self.assertIn("validate_edit_completion", modules)

    def test_notebook_edit_resolves_pre_notebook_list(self) -> None:
        modules = d._modules_for("NotebookEdit")
        self.assertIn("enforce_librarian_consulted", modules)
        self.assertIn("validate_edit_completion", modules)

    def test_registry_modules_all_importable_and_expose_check(self) -> None:
        import importlib

        for matcher in d._MATCHER_CFG_KEY:
            for module_name in d._modules_for(matcher):
                mod = importlib.import_module(module_name)
                self.assertTrue(
                    callable(getattr(mod, "check", None)),
                    f"{module_name} (registered for {matcher}) has no callable check()",
                )


class SettingsRegistrationTests(unittest.TestCase):
    """settings.json PreToolUse entries must agree with the matcher table."""

    def test_settings_pre_tool_use_edit_write_notebook_route_through_dispatcher(self) -> None:
        """Edit/Write/NotebookEdit must each be a SINGLE dispatcher.py entry —
        the #1114 consolidation this issue implements. A regression back to
        two standalone command entries per matcher would silently double the
        process count this issue removed."""
        settings_path = _REPO_ROOT / ".claude" / "settings.json"
        with open(settings_path, encoding="utf-8") as f:
            settings = json.load(f)
        pre = settings.get("hooks", {}).get("PreToolUse", [])

        per_matcher: dict[str, list[str]] = {}
        for entry in pre:
            matcher = entry.get("matcher", "")
            for hook in entry.get("hooks", []):
                cmd = hook.get("command", "")
                module = cmd.rsplit("/", 1)[-1].replace(".py", "")
                per_matcher.setdefault(matcher, []).append(module)

        for matcher in ("Bash", "Edit", "Write", "NotebookEdit"):
            self.assertEqual(
                per_matcher.get(matcher),
                ["dispatcher"],
                f"settings.json matcher {matcher!r} must be a single dispatcher.py "
                f"entry, found: {per_matcher.get(matcher)}",
            )


class DispatchPerMatcherTests(unittest.TestCase):
    """For each matcher, verify every registered module's check() is called
    with `hook_event_name: PreToolUse` (the phase-tagged input the dispatcher
    forwards verbatim)."""

    def _assert_all_called(self, tool_name: str, extra_input: dict | None = None) -> None:
        input_data = {
            "tool_name": tool_name,
            "hook_event_name": "PreToolUse",
            "tool_input": {},
        }
        if extra_input:
            input_data.update(extra_input)

        modules = d._modules_for(tool_name)
        self.assertTrue(modules, f"expected a non-empty module list for {tool_name!r}")

        mocks: list[mock.MagicMock] = []
        patches = []
        for module_name in modules:
            m = mock.MagicMock(return_value=None)
            mocks.append(m)
            patches.append(mock.patch(f"{module_name}.check", m))

        for p in patches:
            p.start()
        try:
            code, _out = _run_dispatcher(input_data)
        finally:
            for p in patches:
                p.stop()

        self.assertEqual(code, 0, f"matcher {tool_name!r} should exit 0 with no blocks")
        for module_name, m in zip(modules, mocks):
            self.assertEqual(
                m.call_count,
                1,
                f"check() for {module_name!r} ({tool_name!r}) called {m.call_count} times",
            )
            self.assertEqual(m.call_args[0][0], input_data)

    def test_bash_dispatches_all_bash_modules(self) -> None:
        self._assert_all_called("Bash", {"tool_input": {"command": "echo hi"}})

    def test_edit_dispatches_all_edit_modules(self) -> None:
        self._assert_all_called("Edit", {"tool_input": {"file_path": "/tmp/x.py"}})

    def test_write_dispatches_all_write_modules(self) -> None:
        self._assert_all_called("Write", {"tool_input": {"file_path": "/tmp/x.py"}})

    def test_notebook_edit_dispatches_all_modules(self) -> None:
        self._assert_all_called("NotebookEdit", {"tool_input": {"notebook_path": "/tmp/x.ipynb"}})

    def test_unknown_matcher_dispatches_nothing(self) -> None:
        input_data = {
            "tool_name": "Read",
            "hook_event_name": "PreToolUse",
            "tool_input": {"file_path": "/tmp/x.py"},
        }
        code, out = _run_dispatcher(input_data)
        self.assertEqual(code, 0)
        self.assertEqual(out, "")


class BlockAndWarningTests(unittest.TestCase):
    """A `decision: block` short-circuits with exit 2; `systemMessage`-only
    returns aggregate and allow (exit 0). This is the load-bearing PreToolUse
    contract dispatcher.py must preserve identically for Edit/Write/
    NotebookEdit as it already did for Bash."""

    def test_edit_blocks_on_first_blocker(self) -> None:
        input_data = {
            "tool_name": "Edit",
            "hook_event_name": "PreToolUse",
            "tool_input": {"file_path": "/tmp/x.py"},
        }
        with (
            mock.patch(
                "enforce_librarian_consulted.check",
                return_value={"decision": "block", "reason": "BLOCKED"},
            ),
            mock.patch("validate_edit_completion.check") as never_called,
        ):
            code, out = _run_dispatcher(input_data)
        self.assertEqual(code, 2)
        parsed = json.loads(out)
        self.assertEqual(parsed["decision"], "block")
        self.assertEqual(parsed["reason"], "BLOCKED")
        # First blocker wins — sibling hooks after it never run.
        never_called.assert_not_called()

    def test_notebook_edit_blocks_on_second_hook(self) -> None:
        input_data = {
            "tool_name": "NotebookEdit",
            "hook_event_name": "PreToolUse",
            "tool_input": {"notebook_path": "/tmp/x.ipynb"},
        }
        with (
            mock.patch("enforce_librarian_consulted.check", return_value=None),
            mock.patch(
                "validate_edit_completion.check",
                return_value={"decision": "block", "reason": "UNACKED"},
            ),
        ):
            code, out = _run_dispatcher(input_data)
        self.assertEqual(code, 2)
        parsed = json.loads(out)
        self.assertEqual(parsed["reason"], "UNACKED")

    def test_write_warnings_aggregate_and_allow(self) -> None:
        input_data = {
            "tool_name": "Write",
            "hook_event_name": "PreToolUse",
            "tool_input": {"file_path": "/tmp/x.py"},
        }
        with (
            mock.patch(
                "enforce_librarian_consulted.check",
                return_value={"systemMessage": "ADVISE_A"},
            ),
            mock.patch("validate_edit_completion.check", return_value=None),
        ):
            code, out = _run_dispatcher(input_data)
        self.assertEqual(code, 0)
        parsed = json.loads(out)
        self.assertEqual(parsed["decision"], "allow")
        self.assertIn("ADVISE_A", parsed["systemMessage"])

    def test_all_none_yields_no_output(self) -> None:
        input_data = {
            "tool_name": "Edit",
            "hook_event_name": "PreToolUse",
            "tool_input": {"file_path": "/tmp/x.py"},
        }
        with (
            mock.patch("enforce_librarian_consulted.check", return_value=None),
            mock.patch("validate_edit_completion.check", return_value=None),
        ):
            code, out = _run_dispatcher(input_data)
        self.assertEqual(code, 0)
        self.assertEqual(out, "")


class FailOpenTests(unittest.TestCase):
    """Individual hook exceptions and missing modules must not crash the
    dispatcher, matching the pre-existing Bash-only behavior."""

    def test_hook_raises_does_not_block_others(self) -> None:
        input_data = {
            "tool_name": "Edit",
            "hook_event_name": "PreToolUse",
            "tool_input": {"file_path": "/tmp/x.py"},
        }
        sibling = mock.MagicMock(return_value=None)
        with (
            mock.patch("enforce_librarian_consulted.check", side_effect=RuntimeError("boom")),
            mock.patch("validate_edit_completion.check", sibling),
        ):
            code, out = _run_dispatcher(input_data)
        self.assertEqual(code, 0, "exception must not propagate or block")
        self.assertEqual(out, "")
        sibling.assert_called_once()

    def test_missing_check_attr_skipped(self) -> None:
        input_data = {
            "tool_name": "Edit",
            "hook_event_name": "PreToolUse",
            "tool_input": {"file_path": "/tmp/x.py"},
        }
        with (
            mock.patch("enforce_librarian_consulted.check", new=None),
            mock.patch("validate_edit_completion.check", return_value={"systemMessage": "OK"}),
        ):
            code, out = _run_dispatcher(input_data)
        self.assertEqual(code, 0)
        self.assertIn("OK", out)

    def test_malformed_stdin_exits_zero(self) -> None:
        stdin = io.StringIO("not json at all")
        stdout = io.StringIO()
        with mock.patch.object(sys, "stdin", stdin), mock.patch.object(sys, "stdout", stdout):
            try:
                d.main()
                code = 0
            except SystemExit as e:
                code = int(e.code) if e.code is not None else 0
        self.assertEqual(code, 0)
        self.assertEqual(stdout.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
