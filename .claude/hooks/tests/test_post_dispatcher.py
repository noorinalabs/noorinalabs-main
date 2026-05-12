#!/usr/bin/env python3
"""Tests for post_dispatcher.py — PostToolUse single-entry dispatcher.

Mirrors the structure of the PreToolUse `dispatcher.py` invariants but for
PostToolUse semantics: hooks are advisory (no `block` decision), the
dispatcher aggregates `systemMessage` returns, individual-hook exceptions
are swallowed, and the registry must cover every PostToolUse entry in
`settings.json` at HEAD.

Run:  python3 -m pytest .claude/hooks/tests/test_post_dispatcher.py -v
"""

from __future__ import annotations

import io
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
_REPO_ROOT = _HOOKS_DIR.parent.parent

sys.path.insert(0, str(_HOOKS_DIR))

import post_dispatcher as pd  # noqa: E402


def _run_dispatcher(input_data: dict) -> tuple[int, str]:
    """Run `post_dispatcher.main()` against the given stdin dict.

    Returns (exit_code, stdout_text). `SystemExit` is captured so the test
    can assert exit code without terminating the test runner.
    """
    stdin = io.StringIO(json.dumps(input_data))
    stdout = io.StringIO()
    with mock.patch.object(sys, "stdin", stdin), mock.patch.object(sys, "stdout", stdout):
        try:
            pd.main()
        except SystemExit as e:
            code = int(e.code) if e.code is not None else 0
            return code, stdout.getvalue()
    return 0, stdout.getvalue()


class RegistryCompletenessTests(unittest.TestCase):
    """Every PostToolUse entry in settings.json must be in _REGISTRY."""

    def test_settings_post_tool_use_entries_all_registered(self):
        """If settings.json registered foo.py for matcher M, _REGISTRY[M] must
        list 'foo' (or the entry must already be `post_dispatcher.py`, the
        consolidation entry).
        """
        settings_path = _REPO_ROOT / ".claude" / "settings.json"
        with open(settings_path, encoding="utf-8") as f:
            settings = json.load(f)
        post = settings.get("hooks", {}).get("PostToolUse", [])

        per_matcher: dict[str, list[str]] = {}
        for entry in post:
            matcher = entry.get("matcher", "")
            for hook in entry.get("hooks", []):
                cmd = hook.get("command", "")
                # Extract the module basename from the path
                last = cmd.rsplit("/", 1)[-1]
                module = last.replace(".py", "")
                per_matcher.setdefault(matcher, []).append(module)

        for matcher, registered in per_matcher.items():
            # Allow either: every entry IS the dispatcher itself, OR every
            # individual hook is listed in _REGISTRY for that matcher.
            if all(m == "post_dispatcher" for m in registered):
                self.assertIn(
                    matcher,
                    pd._REGISTRY,
                    f"settings.json registers post_dispatcher for matcher "
                    f"{matcher!r} but _REGISTRY has no entry for it",
                )
                continue
            for module in registered:
                if module == "post_dispatcher":
                    continue
                self.assertIn(
                    module,
                    pd._REGISTRY.get(matcher, []),
                    f"settings.json registers {module!r} for matcher "
                    f"{matcher!r} but _REGISTRY[{matcher!r}] does not include it",
                )

    def test_registry_modules_all_importable(self):
        """Every module in _REGISTRY must be importable from .claude/hooks/."""
        import importlib

        for matcher, modules in pd._REGISTRY.items():
            for module_name in modules:
                try:
                    importlib.import_module(module_name)
                except ImportError as e:
                    self.fail(
                        f"_REGISTRY[{matcher!r}] lists {module_name!r} but it failed to import: {e}"
                    )

    def test_registry_modules_expose_check(self):
        """Every module in _REGISTRY must expose a `check(input_data)` function."""
        import importlib

        for matcher, modules in pd._REGISTRY.items():
            for module_name in modules:
                mod = importlib.import_module(module_name)
                self.assertTrue(
                    callable(getattr(mod, "check", None)),
                    f"{module_name} (registered for {matcher}) has no callable check()",
                )

    def test_edit_write_share_module_list(self):
        """Edit and Write should reference the same module sequence today."""
        self.assertEqual(pd._REGISTRY["Edit"], pd._REGISTRY["Write"])


class DispatchPerMatcherTests(unittest.TestCase):
    """For each matcher, verify every registered module's check() is called."""

    def _assert_all_called(self, matcher: str, extra_input: dict | None = None) -> None:
        input_data = {
            "tool_name": matcher,
            "hook_event_name": "PostToolUse",
            "tool_input": {},
            "tool_response": {},
        }
        if extra_input:
            input_data.update(extra_input)

        mocks: list[mock.MagicMock] = []
        modules = pd._REGISTRY[matcher]

        # Patch each module's `check` so we can assert call counts without
        # exercising real side effects.
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

        self.assertEqual(code, 0, f"matcher {matcher!r} should always exit 0")
        for module_name, m in zip(modules, mocks):
            self.assertEqual(
                m.call_count,
                1,
                f"check() for {module_name!r} ({matcher!r}) called {m.call_count} times",
            )

    def test_bash_dispatches_all_bash_modules(self):
        self._assert_all_called("Bash", {"tool_input": {"command": "echo hi"}})

    def test_edit_dispatches_all_edit_modules(self):
        self._assert_all_called("Edit", {"tool_input": {"file_path": "/tmp/x.py"}})

    def test_write_dispatches_all_write_modules(self):
        self._assert_all_called("Write", {"tool_input": {"file_path": "/tmp/x.py"}})

    def test_notebook_edit_dispatches_all_modules(self):
        self._assert_all_called("NotebookEdit", {"tool_input": {"notebook_path": "/tmp/x.ipynb"}})

    def test_unknown_matcher_dispatches_nothing(self):
        # No matcher → no module calls, clean exit 0
        input_data = {
            "tool_name": "Read",
            "hook_event_name": "PostToolUse",
            "tool_input": {"file_path": "/tmp/x.py"},
            "tool_response": {},
        }
        code, out = _run_dispatcher(input_data)
        self.assertEqual(code, 0)
        self.assertEqual(out, "")


class AggregationTests(unittest.TestCase):
    """systemMessage returns from N hooks aggregate into one output."""

    def test_two_messages_joined(self):
        input_data = {
            "tool_name": "Edit",
            "hook_event_name": "PostToolUse",
            "tool_input": {"file_path": "/tmp/x.py"},
            "tool_response": {},
        }
        with (
            mock.patch("ontology_tracker.check", return_value=None),
            mock.patch("suggest_generic_prompt.check", return_value={"systemMessage": "MSG_A"}),
            mock.patch("validate_edit_completion.check", return_value={"systemMessage": "MSG_B"}),
        ):
            code, out = _run_dispatcher(input_data)

        self.assertEqual(code, 0)
        self.assertNotEqual(out, "")
        parsed = json.loads(out)
        self.assertIn("MSG_A", parsed["systemMessage"])
        self.assertIn("MSG_B", parsed["systemMessage"])
        # Confirm separator
        self.assertIn("\n\n", parsed["systemMessage"])

    def test_all_none_yields_no_output(self):
        input_data = {
            "tool_name": "Edit",
            "hook_event_name": "PostToolUse",
            "tool_input": {"file_path": "/tmp/x.py"},
            "tool_response": {},
        }
        with (
            mock.patch("ontology_tracker.check", return_value=None),
            mock.patch("suggest_generic_prompt.check", return_value=None),
            mock.patch("validate_edit_completion.check", return_value=None),
        ):
            code, out = _run_dispatcher(input_data)
        self.assertEqual(code, 0)
        self.assertEqual(out, "")

    def test_non_systemmessage_returns_ignored(self):
        # `{"action": "tracked", ...}` style returns don't surface to harness
        input_data = {
            "tool_name": "Edit",
            "hook_event_name": "PostToolUse",
            "tool_input": {"file_path": "/tmp/x.py"},
            "tool_response": {},
        }
        with (
            mock.patch("ontology_tracker.check", return_value={"action": "tracked", "path": "x"}),
            mock.patch("suggest_generic_prompt.check", return_value=None),
            mock.patch("validate_edit_completion.check", return_value=None),
        ):
            code, out = _run_dispatcher(input_data)
        self.assertEqual(code, 0)
        self.assertEqual(out, "")


class FailOpenTests(unittest.TestCase):
    """Individual hook exceptions must not propagate."""

    def test_hook_raises_does_not_block_others(self):
        input_data = {
            "tool_name": "Edit",
            "hook_event_name": "PostToolUse",
            "tool_input": {"file_path": "/tmp/x.py"},
            "tool_response": {},
        }
        sibling = mock.MagicMock(return_value={"systemMessage": "SIBLING_FIRED"})
        with (
            mock.patch("ontology_tracker.check", side_effect=RuntimeError("boom")),
            mock.patch("suggest_generic_prompt.check", sibling),
            mock.patch("validate_edit_completion.check", return_value=None),
        ):
            code, out = _run_dispatcher(input_data)
        self.assertEqual(code, 0, "exception must not propagate")
        self.assertEqual(sibling.call_count, 1, "sibling hooks must still run")
        self.assertIn("SIBLING_FIRED", out)

    def test_malformed_stdin_exits_zero(self):
        # Not valid JSON → exit 0 quietly
        stdin = io.StringIO("not json at all")
        stdout = io.StringIO()
        with mock.patch.object(sys, "stdin", stdin), mock.patch.object(sys, "stdout", stdout):
            try:
                pd.main()
                code = 0
            except SystemExit as e:
                code = int(e.code) if e.code is not None else 0
        self.assertEqual(code, 0)
        self.assertEqual(stdout.getvalue(), "")

    def test_missing_check_attr_skipped(self):
        # If a registered module somehow lacks `check`, the dispatcher skips
        # it (mirrors PreToolUse dispatcher) rather than crashing.
        input_data = {
            "tool_name": "Edit",
            "hook_event_name": "PostToolUse",
            "tool_input": {"file_path": "/tmp/x.py"},
            "tool_response": {},
        }
        with (
            # Replace .check with None to simulate missing attribute (the
            # dispatcher uses getattr(..., None), so None and absent are
            # equivalent paths).
            mock.patch("ontology_tracker.check", new=None),
            mock.patch("suggest_generic_prompt.check", return_value={"systemMessage": "OK"}),
            mock.patch("validate_edit_completion.check", return_value=None),
        ):
            code, out = _run_dispatcher(input_data)
        self.assertEqual(code, 0)
        self.assertIn("OK", out)


class BackwardCompatTests(unittest.TestCase):
    """Hooks that were refactored to expose check() must still work via main().

    These are sanity checks that the in-place refactor preserved the
    pre-refactor direct-invocation behavior. Detailed per-hook behavior is
    covered by each hook's own test file.
    """

    def test_auto_add_issue_to_board_main_handles_non_bash(self):
        import auto_add_issue_to_board as h

        stdin = io.StringIO(json.dumps({"tool_name": "Read"}))
        with mock.patch.object(sys, "stdin", stdin):
            try:
                h.main()
                code = 0
            except SystemExit as e:
                code = int(e.code) if e.code is not None else 0
        self.assertEqual(code, 0)

    def test_annunaki_monitor_check_returns_none_on_clean_bash(self):
        import annunaki_monitor as h

        result = h.check(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "echo ok"},
                "tool_output": {"stdout": "ok\n", "stderr": "", "exit_code": 0},
            }
        )
        self.assertIsNone(result)

    def test_ontology_tracker_check_skips_non_edit_tool(self):
        import ontology_tracker as h

        result = h.check({"tool_name": "Read", "tool_input": {"file_path": "/tmp/x.py"}})
        self.assertIsNone(result)

    def test_suggest_generic_prompt_check_skips_non_claude_paths(self):
        import suggest_generic_prompt as h

        result = h.check({"tool_name": "Edit", "tool_input": {"file_path": "/tmp/x.py"}})
        self.assertIsNone(result)

    def test_validate_edit_completion_check_routes_posttooluse_edit(self):
        # PostToolUse Edit with no error → None (no sentinel side-effect)
        import validate_edit_completion as h

        result = h.check(
            {
                "tool_name": "Edit",
                "hook_event_name": "PostToolUse",
                "tool_input": {"file_path": "/tmp/x.py"},
                "tool_response": {"is_error": False},
            }
        )
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
