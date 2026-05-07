#!/usr/bin/env python3
"""Tests for validate_workflow_paths_coverage hook (closes #203).

Run:
    ENVIRONMENT=test python3 -m pytest \
        .claude/hooks/tests/test_validate_workflow_paths_coverage.py -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
sys.path.insert(0, str(_HOOKS_DIR))

import validate_workflow_paths_coverage as hook  # noqa: E402


class IsGhPrGateCommandTests(unittest.TestCase):
    """Coverage for the command-shape gate."""

    def test_gh_pr_create_matches(self):
        self.assertTrue(hook._is_gh_pr_gate_command("gh pr create --base main"))

    def test_gh_pr_ready_matches(self):
        self.assertTrue(hook._is_gh_pr_gate_command("gh pr ready 123"))

    def test_chained_command_matches(self):
        self.assertTrue(hook._is_gh_pr_gate_command("git push && gh pr create --title x"))

    def test_env_var_prefix_matches(self):
        self.assertTrue(hook._is_gh_pr_gate_command("FOO=bar gh pr create"))

    def test_gh_pr_list_does_not_match(self):
        self.assertFalse(hook._is_gh_pr_gate_command("gh pr list"))

    def test_gh_pr_view_does_not_match(self):
        self.assertFalse(hook._is_gh_pr_gate_command("gh pr view 100"))

    def test_gh_pr_checks_does_not_match(self):
        self.assertFalse(hook._is_gh_pr_gate_command("gh pr checks"))

    def test_gh_pr_edit_does_not_match(self):
        self.assertFalse(hook._is_gh_pr_gate_command("gh pr edit 100 --title x"))

    def test_gh_pr_merge_does_not_match(self):
        self.assertFalse(hook._is_gh_pr_gate_command("gh pr merge 100 --squash"))

    def test_git_push_does_not_match(self):
        self.assertFalse(hook._is_gh_pr_gate_command("git push origin main"))

    def test_unrelated_bash_does_not_match(self):
        self.assertFalse(hook._is_gh_pr_gate_command("ls -la"))

    def test_create_inside_echo_does_not_match(self):
        """The phrase `gh pr create` inside an `echo` argument must NOT match.

        Our regex anchors on `gh pr (create|ready)` AFTER a shell-op boundary
        or env-var-prefix-stripped command position. `echo "gh pr create"`
        starts with `echo`, so the regex correctly does not match. Negative-
        match coverage for the substring-bug class.
        """
        self.assertFalse(hook._is_gh_pr_gate_command('echo "gh pr create"'))

    def test_create_inside_grep_does_not_match(self):
        """grep with the phrase in pattern position — should NOT match."""
        self.assertFalse(hook._is_gh_pr_gate_command("grep 'gh pr create' /tmp/file"))


class ExtractFlagTests(unittest.TestCase):
    """_extract_flag covers --flag value, --flag=value, --flag "quoted"."""

    def test_space_separated(self):
        self.assertEqual(hook._extract_flag("gh pr create --base develop", "base"), "develop")

    def test_equals_form(self):
        self.assertEqual(hook._extract_flag("gh pr create --base=develop", "base"), "develop")

    def test_double_quoted(self):
        self.assertEqual(
            hook._extract_flag('gh pr create --title "fix: thing"', "title"),
            "fix: thing",
        )

    def test_single_quoted(self):
        self.assertEqual(
            hook._extract_flag("gh pr create --title 'fix: thing'", "title"),
            "fix: thing",
        )

    def test_absent_flag_returns_none(self):
        self.assertIsNone(hook._extract_flag("gh pr create", "base"))


class ParseWorkflowPathsTests(unittest.TestCase):
    """_parse_workflow_paths covers the canonical block-style YAML forms."""

    def test_pr_with_paths_filter(self):
        yml = (
            "name: CI\n"
            "on:\n"
            "  pull_request:\n"
            "    branches: [main]\n"
            "    paths:\n"
            "      - 'src/**'\n"
            "      - '.github/workflows/ci.yml'\n"
        )
        paths, no_paths = hook._parse_workflow_paths(yml)
        self.assertEqual(paths, {"src/**", ".github/workflows/ci.yml"})
        self.assertFalse(no_paths)

    def test_pr_without_paths_filter(self):
        """`on.pull_request:` with no `paths:` matches all paths."""
        yml = "name: CI\non:\n  pull_request:\n    branches: [main]\n"
        paths, no_paths = hook._parse_workflow_paths(yml)
        self.assertEqual(paths, set())
        self.assertTrue(no_paths)

    def test_pr_last_child_of_on_without_paths_filter(self):
        """Regression for #289: `pull_request:` as LAST child of `on:` with no
        `paths:` key was misparsed as covering-nothing because the on:-block
        boundary cleared `in_pr` without consulting `pr_has_paths_key`.
        """
        yml = (
            "name: CI\n"
            "on:\n"
            "  push:\n"
            "    branches: [main]\n"
            "  pull_request:\n"
            '    branches: [main, "deployments/**"]\n'
            "jobs:\n"
            "  build:\n"
            "    runs-on: ubuntu-latest\n"
        )
        paths, no_paths = hook._parse_workflow_paths(yml)
        self.assertEqual(paths, set())
        self.assertTrue(no_paths)

    def test_pr_with_inline_paths_list(self):
        yml = 'name: CI\non:\n  pull_request:\n    paths: ["src/**", "tests/**"]\n'
        paths, no_paths = hook._parse_workflow_paths(yml)
        self.assertEqual(paths, {"src/**", "tests/**"})
        self.assertFalse(no_paths)

    def test_no_pull_request_trigger(self):
        """Workflow with only `push:` trigger contributes nothing to PR coverage."""
        yml = "name: CI\non:\n  push:\n    branches: [main]\n"
        paths, no_paths = hook._parse_workflow_paths(yml)
        self.assertEqual(paths, set())
        self.assertFalse(no_paths)

    def test_paths_ignore_treated_as_no_paths_filter(self):
        """`paths-ignore:` (without `paths:`) → workflow runs on most paths.

        A workflow with `on.pull_request:` that ONLY has `paths-ignore:`
        runs on every path EXCEPT the ignored ones. For the workflow-orphan
        check, this is closer to "no paths filter" than to "specific paths
        only" — so the parser returns no_paths=True. Future hardening could
        evaluate the paths-ignore complement explicitly; v1 over-allows
        slightly (false negatives — extra coverage assumed) which is the
        safer side for the orphan-blocking goal.
        """
        yml = "name: CI\non:\n  pull_request:\n    paths-ignore:\n      - 'docs/**'\n"
        paths, no_paths = hook._parse_workflow_paths(yml)
        self.assertEqual(paths, set())
        self.assertTrue(
            no_paths,
            "v1 conservative: paths-ignore-only PR trigger treated as no-paths-filter",
        )

    def test_inline_on_pull_request(self):
        yml = "name: CI\non: pull_request\n"
        paths, no_paths = hook._parse_workflow_paths(yml)
        self.assertEqual(paths, set())
        self.assertTrue(no_paths)

    def test_inline_on_list(self):
        yml = "name: CI\non: [push, pull_request]\n"
        paths, no_paths = hook._parse_workflow_paths(yml)
        self.assertEqual(paths, set())
        self.assertTrue(no_paths)


class PathMatchesAnyGlobTests(unittest.TestCase):
    def test_exact_match(self):
        self.assertTrue(
            hook._path_matches_any_glob(
                ".github/workflows/ci.yml",
                {".github/workflows/ci.yml"},
            )
        )

    def test_double_star_match(self):
        self.assertTrue(
            hook._path_matches_any_glob(
                ".github/workflows/db-migrate.yml",
                {".github/workflows/**"},
            )
        )

    def test_no_match(self):
        self.assertFalse(
            hook._path_matches_any_glob(
                ".github/workflows/db-migrate.yml",
                {"src/**", "tests/**"},
            )
        )

    def test_empty_globs(self):
        self.assertFalse(
            hook._path_matches_any_glob(
                ".github/workflows/ci.yml",
                set(),
            )
        )


class IsWorkflowFileTests(unittest.TestCase):
    def test_yml_workflow(self):
        self.assertTrue(hook._is_workflow_file(".github/workflows/ci.yml"))

    def test_yaml_workflow(self):
        self.assertTrue(hook._is_workflow_file(".github/workflows/deploy.yaml"))

    def test_non_workflow(self):
        self.assertFalse(hook._is_workflow_file("src/main.py"))

    def test_hooks_dir(self):
        self.assertFalse(hook._is_workflow_file(".claude/hooks/foo.py"))

    def test_workflows_subdir(self):
        """Files under .github/workflows/<subdir>/ DO match the prefix."""
        self.assertTrue(hook._is_workflow_file(".github/workflows/sub/x.yml"))


class CheckEndToEndTests(unittest.TestCase):
    """End-to-end: check() with mocked API calls."""

    @staticmethod
    def _input(command: str) -> dict:
        return {"tool_name": "Bash", "tool_input": {"command": command}}

    def _patches(
        self,
        *,
        repo: str | None = "noorinalabs/test",
        head: str | None = "feat-branch",
        diff_files: list[str] | None = None,
        coverage: tuple[set[str], bool] | None = None,
    ):
        """Return a context manager that patches the I/O surfaces."""
        from contextlib import ExitStack

        stack = ExitStack()
        stack.enter_context(mock.patch.object(hook, "_resolve_repo", return_value=repo))
        stack.enter_context(mock.patch.object(hook, "_resolve_head", return_value=head))
        stack.enter_context(mock.patch.object(hook, "_list_pr_diff_files", return_value=diff_files))
        stack.enter_context(
            mock.patch.object(hook, "_build_coverage_signal", return_value=coverage)
        )
        return stack

    def test_no_workflow_files_in_diff_allows(self):
        """PR with no `.github/workflows/**` changes should never block."""
        with self._patches(diff_files=["src/main.py", "tests/test_main.py"]):
            result = hook.check(self._input("gh pr create --base main"))
        self.assertIsNone(result)

    def test_workflow_change_uncovered_blocks(self):
        """Workflow file in diff + no covering paths filter → block."""
        with self._patches(
            diff_files=[".github/workflows/db-migrate.yml"],
            coverage=({"src/**"}, False),  # base workflows only cover src/**
        ):
            result = hook.check(self._input("gh pr create"))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["decision"], "block")
        self.assertIn(".github/workflows/db-migrate.yml", result["reason"])

    def test_workflow_change_covered_by_double_star_allows(self):
        """`.github/workflows/**` in any base workflow's paths → covered."""
        with self._patches(
            diff_files=[".github/workflows/db-migrate.yml"],
            coverage=({".github/workflows/**", "src/**"}, False),
        ):
            self.assertIsNone(hook.check(self._input("gh pr create")))

    def test_workflow_change_covered_by_no_paths_pr_trigger_allows(self):
        """ANY base workflow with `on.pull_request:` and no `paths:` → covers all."""
        with self._patches(
            diff_files=[".github/workflows/db-migrate.yml"],
            coverage=(set(), True),  # any_no_paths is True
        ):
            self.assertIsNone(hook.check(self._input("gh pr create")))

    def test_non_pr_create_command_skipped(self):
        with self._patches():
            self.assertIsNone(hook.check(self._input("gh pr list")))

    def test_non_bash_tool_skipped(self):
        with self._patches():
            self.assertIsNone(
                hook.check({"tool_name": "Edit", "tool_input": {"command": "gh pr create"}})
            )

    def test_repo_resolution_failure_fails_open(self):
        with self._patches(repo=None, diff_files=[".github/workflows/x.yml"]):
            # repo = None → fail open even with workflow file in diff
            self.assertIsNone(hook.check(self._input("gh pr create")))

    def test_diff_api_failure_fails_open(self):
        with self._patches(diff_files=None):
            # _list_pr_diff_files = None → fail open
            self.assertIsNone(hook.check(self._input("gh pr create")))

    def test_coverage_api_failure_fails_open(self):
        with self._patches(
            diff_files=[".github/workflows/x.yml"],
            coverage=None,
        ):
            self.assertIsNone(hook.check(self._input("gh pr create")))

    def test_deploy_153_repro(self):
        """Exact repro of the deploy#153 76d7d7f orphan case.

        Before the fix: `db-migrate.yml` modification + base workflows whose
        paths filters were `infra/**` and `src/**` only → no coverage, but
        `validate_pr_ci_status` still allowed merge because rollup was empty.

        After this hook: BLOCKS at `gh pr create` time.
        """
        with self._patches(
            diff_files=[
                ".github/workflows/db-migrate.yml",
                "docs/runbooks/user-service-alembic.md",
                "infra/prometheus/alerts.yml",
            ],
            coverage=({"src/**", "infra/**"}, False),
        ):
            result = hook.check(
                self._input("gh pr create --repo noorinalabs/noorinalabs-deploy --base main")
            )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["decision"], "block")
        self.assertIn("db-migrate.yml", result["reason"])


if __name__ == "__main__":
    unittest.main()
