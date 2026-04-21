#!/usr/bin/env python3
"""Tests for validate_branch_freshness hook.

Covers issue #118: --repo flag must be honored instead of cwd.
Also covers W8 hook-authorship NEGATIVE-MATCH requirement.

Run: python3 -m pytest .claude/hooks/tests/test_validate_branch_freshness.py -v
Or:  python3 .claude/hooks/tests/test_validate_branch_freshness.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
sys.path.insert(0, str(_HOOKS_DIR))

import validate_branch_freshness as hook  # noqa: E402


class ExtractBaseTests(unittest.TestCase):
    def test_default(self):
        self.assertEqual(hook.extract_base("gh pr create"), "main")

    def test_long_flag(self):
        self.assertEqual(hook.extract_base("gh pr create --base develop"), "develop")

    def test_short_flag(self):
        self.assertEqual(hook.extract_base("gh pr create -B develop"), "develop")

    def test_equals_form(self):
        self.assertEqual(hook.extract_base("gh pr create --base=develop"), "develop")

    def test_quoted(self):
        self.assertEqual(hook.extract_base('gh pr create --base "release/1.0"'), "release/1.0")


class ExtractHeadTests(unittest.TestCase):
    def test_no_head(self):
        self.assertIsNone(hook.extract_head("gh pr create"))

    def test_long_flag(self):
        self.assertEqual(hook.extract_head("gh pr create --head feature-x"), "feature-x")

    def test_short_flag(self):
        self.assertEqual(hook.extract_head("gh pr create -H feature-x"), "feature-x")

    def test_owner_prefix_stripped(self):
        self.assertEqual(
            hook.extract_head("gh pr create --head fork-owner:feature-x"),
            "feature-x",
        )

    def test_equals_form(self):
        self.assertEqual(hook.extract_head("gh pr create --head=feature-x"), "feature-x")


class ExtractRepoTests(unittest.TestCase):
    def test_long_flag(self):
        self.assertEqual(
            hook.extract_repo("gh pr create --repo noorinalabs/noorinalabs-isnad-graph"),
            "noorinalabs/noorinalabs-isnad-graph",
        )

    def test_short_flag(self):
        self.assertEqual(hook.extract_repo("gh pr create -R owner/repo"), "owner/repo")

    def test_equals_form(self):
        self.assertEqual(hook.extract_repo("gh pr create --repo=owner/repo"), "owner/repo")

    def test_no_repo_flag(self):
        self.assertIsNone(hook.extract_repo("gh pr create"))


class NegativeMatchTests(unittest.TestCase):
    """NEGATIVE-MATCH coverage for #118 + W8 spec.

    Flag values must NOT be extracted from inside another flag's body.
    """

    def test_repo_token_in_body_is_ignored(self):
        cmd = 'gh pr create --body "see also: gh pr create --repo ghost/ghost" --repo real/real'
        self.assertEqual(hook.extract_repo(cmd), "real/real")

    def test_base_token_in_body_is_ignored(self):
        cmd = 'gh pr create --body "rebase onto --base ghost-base before merging" --base develop'
        self.assertEqual(hook.extract_base(cmd), "develop")

    def test_head_token_in_body_is_ignored(self):
        cmd = 'gh pr create --body "the --head ghost-branch flag was renamed" --head real-branch'
        self.assertEqual(hook.extract_head(cmd), "real-branch")

    def test_no_flags_in_body_only(self):
        """Body documents flags but the actual command has none."""
        cmd = 'gh pr create --body "example: --base x --head y --repo a/b"'
        self.assertEqual(hook.extract_base(cmd), "main")  # default
        self.assertIsNone(hook.extract_head(cmd))
        self.assertIsNone(hook.extract_repo(cmd))


class GateMatchingTests(unittest.TestCase):
    """The check() gate fires ONLY on the matched command, not siblings."""

    @staticmethod
    def _input(command: str) -> dict:
        return {"tool_name": "Bash", "tool_input": {"command": command}}

    def test_gh_pr_list_is_ignored(self):
        self.assertIsNone(hook.check(self._input("gh pr list")))

    def test_gh_pr_view_is_ignored(self):
        self.assertIsNone(hook.check(self._input("gh pr view 123")))

    def test_gh_pr_checks_is_ignored(self):
        self.assertIsNone(hook.check(self._input("gh pr checks")))

    def test_gh_pr_edit_is_ignored(self):
        self.assertIsNone(hook.check(self._input("gh pr edit 123 --base main")))

    def test_gh_pr_merge_is_ignored(self):
        self.assertIsNone(hook.check(self._input("gh pr merge 123 --squash")))

    def test_gh_issue_create_is_ignored(self):
        self.assertIsNone(hook.check(self._input("gh issue create --title x")))

    def test_non_bash_tool_is_ignored(self):
        self.assertIsNone(
            hook.check(
                {
                    "tool_name": "Edit",
                    "tool_input": {"command": "gh pr create --base develop"},
                }
            )
        )

    def test_unrelated_command_is_ignored(self):
        self.assertIsNone(hook.check(self._input('echo "gh pr create"')))


class CheckLocalPathTests(unittest.TestCase):
    """End-to-end check() with the cwd-based (no --repo) path mocked."""

    @staticmethod
    def _input(command: str) -> dict:
        return {"tool_name": "Bash", "tool_input": {"command": command}}

    def test_local_fresh_branch_allows(self):
        with mock.patch.object(hook, "is_branch_fresh_local", return_value=True) as mocked:
            result = hook.check(self._input("gh pr create"))
        self.assertIsNone(result)
        mocked.assert_called_once_with("main")

    def test_local_stale_branch_blocks(self):
        with mock.patch.object(hook, "is_branch_fresh_local", return_value=False):
            result = hook.check(self._input("gh pr create"))
        self.assertIsNotNone(result)
        self.assertEqual(result["decision"], "block")
        self.assertIn("origin/main", result["reason"])

    def test_local_path_used_when_no_repo_flag(self):
        """Without --repo, the cwd-based check is the only path consulted."""
        with (
            mock.patch.object(hook, "is_branch_fresh_local", return_value=True) as local_mock,
            mock.patch.object(hook, "is_branch_fresh_remote") as remote_mock,
        ):
            hook.check(self._input("gh pr create --base develop"))
        local_mock.assert_called_once_with("develop")
        remote_mock.assert_not_called()


class CheckRemotePathTests(unittest.TestCase):
    """Bug #118 fix: --repo must route to the API path, not cwd."""

    @staticmethod
    def _input(command: str) -> dict:
        return {"tool_name": "Bash", "tool_input": {"command": command}}

    def test_repo_flag_uses_remote_path(self):
        """When --repo is set and --head is given, hit the API not cwd."""
        cmd = "gh pr create --repo noorinalabs/noorinalabs-isnad-graph --head feature-x --base main"
        with (
            mock.patch.object(hook, "is_branch_fresh_remote", return_value=True) as remote_mock,
            mock.patch.object(hook, "is_branch_fresh_local") as local_mock,
        ):
            result = hook.check(self._input(cmd))
        self.assertIsNone(result)
        remote_mock.assert_called_once_with(
            "noorinalabs/noorinalabs-isnad-graph", "main", "feature-x"
        )
        local_mock.assert_not_called()

    def test_repo_flag_with_stale_remote_blocks(self):
        cmd = (
            "gh pr create --repo noorinalabs/noorinalabs-isnad-graph "
            "--head feature-x --base develop"
        )
        with mock.patch.object(hook, "is_branch_fresh_remote", return_value=False):
            result = hook.check(self._input(cmd))
        self.assertIsNotNone(result)
        self.assertEqual(result["decision"], "block")
        self.assertIn("noorinalabs/noorinalabs-isnad-graph:develop", result["reason"])

    def test_repo_flag_without_head_skips(self):
        """We can't infer head reliably for cross-repo without --head -> skip."""
        cmd = "gh pr create --repo noorinalabs/noorinalabs-isnad-graph"
        with (
            mock.patch.object(hook, "is_branch_fresh_remote") as remote_mock,
            mock.patch.object(hook, "is_branch_fresh_local") as local_mock,
        ):
            result = hook.check(self._input(cmd))
        self.assertIsNone(result)
        remote_mock.assert_not_called()
        local_mock.assert_not_called()

    def test_remote_check_failure_allows(self):
        """API errors fail-open, matching cwd path's behavior."""
        cmd = "gh pr create --repo noorinalabs/noorinalabs-isnad-graph --head feature-x"
        with mock.patch.object(hook, "is_branch_fresh_remote", return_value=None):
            result = hook.check(self._input(cmd))
        self.assertIsNone(result)

    def test_repro_for_issue_118(self):
        """Repro from the issue body: cwd is one repo, --repo targets another.

        Before the fix: hook called git fetch + merge-base in cwd, false-
        positive blocking. After the fix: we hit the gh API for the target.
        """
        cmd = (
            "gh pr create --repo noorinalabs/noorinalabs-isnad-graph "
            "--head L.Pham/0834-feature --base main "
            "--title 't' --body 'b'"
        )
        with (
            mock.patch.object(hook, "is_branch_fresh_remote", return_value=True) as remote_mock,
            mock.patch.object(hook, "is_branch_fresh_local") as local_mock,
        ):
            result = hook.check(self._input(cmd))
        self.assertIsNone(result, "Bug #118: cross-repo PR should not be blocked by cwd state")
        remote_mock.assert_called_once_with(
            "noorinalabs/noorinalabs-isnad-graph", "main", "L.Pham/0834-feature"
        )
        local_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
