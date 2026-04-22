#!/usr/bin/env python3
"""Tests for auto_set_env_test hook.

Covers hook-authorship-spec requirement: NEGATIVE MATCH coverage.
Each test documents which negative-space case it guards against.

Run: python3 -m pytest .claude/hooks/tests/test_auto_set_env_test.py -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
sys.path.insert(0, str(_HOOKS_DIR))

import auto_set_env_test as hook  # noqa: E402


def _bash(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


class NonMatchedToolTests(unittest.TestCase):
    """Tools OTHER than Bash must never block."""

    def test_edit_does_not_block(self) -> None:
        """NEG: Edit is not in the matcher set."""
        result = hook.check({"tool_name": "Edit", "tool_input": {"file_path": "x.py"}})
        self.assertIsNone(result)

    def test_write_does_not_block(self) -> None:
        """NEG: Write is not in the matcher set."""
        result = hook.check({"tool_name": "Write", "tool_input": {"file_path": "x.py"}})
        self.assertIsNone(result)


class GhSubcommandSkipTests(unittest.TestCase):
    """Short-circuit #1: any command whose argv[0] is `gh` is exempt (#114)."""

    def test_gh_pr_comment_with_pytest_in_body(self) -> None:
        """NEG: `gh pr comment ... --body "...pytest..."` — repro case from #114."""
        result = hook.check(
            _bash(
                'gh pr comment 808 --repo noorinalabs/x --body "fixing pytest CVE"'
            )
        )
        self.assertIsNone(result, "gh pr comment mentioning pytest in body must be allowed")

    def test_gh_issue_create_with_make_test_in_body(self) -> None:
        """NEG: `gh issue create --body "make test broke"` — substring false-positive."""
        result = hook.check(
            _bash('gh issue create --title "x" --body "make test broke"')
        )
        self.assertIsNone(result, "gh issue create mentioning make test in body must be allowed")

    def test_gh_pr_create_runs_pytest_mention(self) -> None:
        """NEG: `gh pr create --body "runs pytest in CI"` — PR description text."""
        result = hook.check(_bash('gh pr create --body "runs pytest in CI"'))
        self.assertIsNone(result, "gh pr create mentioning pytest must be allowed")

    def test_gh_skip_beats_env_prefix(self) -> None:
        """NEG: `ENVIRONMENT=test gh pr comment ... --body "pytest"` — gh skip
        takes precedence; we don't want to accidentally encourage the env prefix
        on gh commands by only allowing them if ENVIRONMENT=test is present."""
        result = hook.check(
            _bash('ENVIRONMENT=test gh pr comment 1 --body "pytest"')
        )
        self.assertIsNone(
            result,
            "gh after env-assignment prefix is still a gh invocation, not a test",
        )

    def test_gh_with_multiple_env_prefixes(self) -> None:
        """NEG: multiple leading env assignments still resolve to `gh` argv[0]."""
        result = hook.check(
            _bash('FOO=1 BAR=2 gh pr comment 1 --body "pytest note"')
        )
        self.assertIsNone(result)


class BodyFlagSkipTests(unittest.TestCase):
    """Short-circuit #2: --body / --body-file flags exempt the whole command."""

    def test_body_flag_in_non_gh_command(self) -> None:
        """NEG: `some-tool --body "$(cat pytest.txt)"` — intentionally broad skip
        per hook docstring. False-negatives on exotic tools are acceptable."""
        result = hook.check(_bash('some-tool --body "$(cat pytest.txt)"'))
        self.assertIsNone(result)

    def test_body_file_flag(self) -> None:
        """NEG: --body-file also triggers the skip (same rationale)."""
        result = hook.check(_bash('gh pr create --body-file /tmp/body.md'))
        self.assertIsNone(result)

    def test_body_equals_form(self) -> None:
        """NEG: --body=value (no space) also triggers the skip."""
        result = hook.check(_bash('gh pr comment 1 --body="pytest CVE"'))
        self.assertIsNone(result)

    def test_body_flag_false_friend_not_matched(self) -> None:
        """POS: `--body-foo` should NOT count as a body flag. With pytest present
        and no ENVIRONMENT=test, this should block (not gh, no real --body)."""
        result = hook.check(_bash('custom-tool --body-foo pytest'))
        self.assertIsNotNone(result, "--body-foo is not --body or --body-file")
        self.assertEqual(result.get("decision"), "block")


class PositiveMatchTests(unittest.TestCase):
    """Real test-runner commands must still block without ENVIRONMENT=test."""

    def test_bare_pytest_blocks(self) -> None:
        """POS: `pytest` alone — classic invocation."""
        result = hook.check(_bash("pytest"))
        self.assertIsNotNone(result)
        self.assertEqual(result.get("decision"), "block")

    def test_pytest_with_path_blocks(self) -> None:
        """POS: `pytest tests/` — typical invocation."""
        result = hook.check(_bash("pytest tests/"))
        self.assertIsNotNone(result)
        self.assertEqual(result.get("decision"), "block")

    def test_make_test_blocks(self) -> None:
        """POS: `make test` — make target."""
        result = hook.check(_bash("make test"))
        self.assertIsNotNone(result)

    def test_python_m_pytest_blocks(self) -> None:
        """POS: `python -m pytest` — module invocation."""
        result = hook.check(_bash("python -m pytest"))
        self.assertIsNotNone(result)

    def test_uv_run_pytest_blocks(self) -> None:
        """POS: `uv run pytest` — uv tool runner."""
        result = hook.check(_bash("uv run pytest"))
        self.assertIsNotNone(result)

    def test_env_prefix_with_real_pytest_still_blocks(self) -> None:
        """POS regression: leading env prefix with real test command must still
        block. `DEBUG=1 pytest tests/` has `pytest` as effective argv[0]."""
        result = hook.check(_bash("DEBUG=1 pytest tests/"))
        self.assertIsNotNone(result)
        self.assertEqual(result.get("decision"), "block")


class EnvAlreadySetTests(unittest.TestCase):
    """ENVIRONMENT=test already present — must allow."""

    def test_env_set_on_pytest(self) -> None:
        """NEG: ENVIRONMENT=test already prepended — allow."""
        result = hook.check(_bash("ENVIRONMENT=test pytest tests/"))
        self.assertIsNone(result)

    def test_env_set_on_make_test(self) -> None:
        """NEG: ENVIRONMENT=test on make test — allow."""
        result = hook.check(_bash("ENVIRONMENT=test make test"))
        self.assertIsNone(result)


class NonTestCommandTests(unittest.TestCase):
    """Commands that don't match pytest/make-test regex must allow."""

    def test_ls_allowed(self) -> None:
        """NEG: `ls` — not a test command."""
        result = hook.check(_bash("ls -la"))
        self.assertIsNone(result)

    def test_empty_command_allowed(self) -> None:
        """NEG: empty command."""
        result = hook.check(_bash(""))
        self.assertIsNone(result)

    def test_make_other_target_allowed(self) -> None:
        """NEG: `make build` — not `make test`."""
        result = hook.check(_bash("make build"))
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
