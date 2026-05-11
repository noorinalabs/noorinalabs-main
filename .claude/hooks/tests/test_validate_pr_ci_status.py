#!/usr/bin/env python3
"""Tests for validate_pr_ci_status hook (closes #219).

Covers:
- `classify_check` core logic — pass/fail/pending across the conclusion +
  status + bucket axes.
- #219 NEUTRAL allowlist semantics — `chromatic` CheckRun NEUTRAL is treated
  as pending, all other CheckRuns' NEUTRAL preserved as pass.
- Hook-authorship § 3 negative-match coverage.

Run:
    ENVIRONMENT=test python3 -m pytest \
        .claude/hooks/tests/test_validate_pr_ci_status.py -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
sys.path.insert(0, str(_HOOKS_DIR))

import validate_pr_ci_status as hook  # noqa: E402


def _check(name: str = "ci", *, conclusion: str = "", status: str = "", bucket: str = "") -> dict:
    """Build a CheckRun dict with the fields classify_check inspects."""
    out: dict = {"name": name}
    if conclusion:
        out["conclusion"] = conclusion
    if status:
        out["status"] = status
    if bucket:
        out["bucket"] = bucket
    return out


class ClassifyCheckCoreTests(unittest.TestCase):
    """Existing classify_check semantics (pre-#219, must remain stable)."""

    def test_failure_conclusion_classed_fail(self):
        for c in ("FAILURE", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED", "STARTUP_FAILURE"):
            with self.subTest(conclusion=c):
                self.assertEqual(
                    hook.classify_check(_check(conclusion=c)),
                    "fail",
                    f"conclusion {c} should classify as fail",
                )

    def test_fail_bucket_classed_fail(self):
        # bucket overrides conclusion when bucket is `fail`
        self.assertEqual(hook.classify_check(_check(bucket="fail", conclusion="SUCCESS")), "fail")

    def test_pending_status_classed_pending(self):
        for s in ("QUEUED", "IN_PROGRESS", "WAITING", "PENDING", "REQUESTED"):
            with self.subTest(status=s):
                self.assertEqual(
                    hook.classify_check(_check(status=s)),
                    "pending",
                    f"status {s} should classify as pending",
                )

    def test_completed_no_conclusion_classed_pass(self):
        """status=COMPLETED with empty conclusion is treated as pass."""
        self.assertEqual(hook.classify_check(_check(status="COMPLETED")), "pass")

    def test_success_conclusion_classed_pass(self):
        self.assertEqual(hook.classify_check(_check(conclusion="SUCCESS")), "pass")

    def test_skipped_conclusion_classed_pass(self):
        self.assertEqual(hook.classify_check(_check(conclusion="SKIPPED")), "pass")

    def test_pass_bucket_classed_pass(self):
        # bucket=pass requires a non-empty conclusion or COMPLETED status to
        # bypass the empty-conclusion early-return path.
        self.assertEqual(
            hook.classify_check(_check(bucket="pass", conclusion="SUCCESS")),
            "pass",
        )

    def test_skipping_bucket_classed_pass(self):
        self.assertEqual(
            hook.classify_check(_check(bucket="skipping", conclusion="SKIPPED")),
            "pass",
        )


class NeutralAllowlistTests(unittest.TestCase):
    """Issue #219: chromatic NEUTRAL → pending; all other NEUTRAL → pass.

    Charter `pull-requests.md` § CI Must Be Green is the source of truth;
    this allowlist is the operational mapping for services whose NEUTRAL
    semantics differ from GitHub's "no opinion" default.
    """

    def test_chromatic_neutral_classed_pending(self):
        """REQUIRED test (per #219 acceptance): chromatic + NEUTRAL → block via pending."""
        self.assertEqual(
            hook.classify_check(_check(name="chromatic", conclusion="NEUTRAL")),
            "pending",
        )

    def test_chromatic_success_classed_pass(self):
        """REQUIRED test (per #219 acceptance): chromatic + SUCCESS → allow."""
        self.assertEqual(
            hook.classify_check(_check(name="chromatic", conclusion="SUCCESS")),
            "pass",
        )

    def test_other_check_neutral_still_classed_pass(self):
        """REQUIRED test (per #219 acceptance): non-chromatic + NEUTRAL → allow.

        Negative-match coverage per Hook Authorship Requirement § 3 — the
        allowlist must NOT broaden NEUTRAL → pending for unrelated checks.
        """
        for name in ("ci", "lint", "test", "build", "deploy-stg", "ruff-format"):
            with self.subTest(name=name):
                self.assertEqual(
                    hook.classify_check(_check(name=name, conclusion="NEUTRAL")),
                    "pass",
                    f"check '{name}' NEUTRAL should remain pass (preserves prior behavior)",
                )

    def test_chromatic_case_insensitive(self):
        """Display-name match is case-insensitive — `Chromatic` and `CHROMATIC` also match."""
        for variant in ("Chromatic", "CHROMATIC", "chRoMatic"):
            with self.subTest(name=variant):
                self.assertEqual(
                    hook.classify_check(_check(name=variant, conclusion="NEUTRAL")),
                    "pending",
                )

    def test_chromatic_failure_still_fail(self):
        """Allowlist doesn't soften failures — chromatic FAILURE is still fail."""
        self.assertEqual(
            hook.classify_check(_check(name="chromatic", conclusion="FAILURE")),
            "fail",
        )

    def test_chromatic_pending_status_still_pending(self):
        """If status itself is pending, classification is pending regardless of allowlist."""
        self.assertEqual(
            hook.classify_check(_check(name="chromatic", status="IN_PROGRESS")),
            "pending",
        )

    def test_allowlist_constant_uses_lowercase(self):
        """Sanity check on the constant: entries must be pre-lowercased to match the comparison."""
        for entry in hook._NEUTRAL_PENDING_CHECK_NAMES:
            self.assertEqual(entry, entry.lower(), f"allowlist entry {entry!r} must be lowercase")

    def test_chromatic_in_allowlist(self):
        """Sanity: the canonical W4-motivated entry is present."""
        self.assertIn("chromatic", hook._NEUTRAL_PENDING_CHECK_NAMES)


class CheckNameTests(unittest.TestCase):
    """check_name fallback chain for the allowlist match."""

    def test_name_field(self):
        self.assertEqual(hook.check_name({"name": "chromatic"}), "chromatic")

    def test_context_fallback(self):
        self.assertEqual(hook.check_name({"context": "Chromatic / Visual"}), "Chromatic / Visual")

    def test_workflow_name_fallback(self):
        self.assertEqual(
            hook.check_name({"workflowName": "chromatic-snapshots"}), "chromatic-snapshots"
        )

    def test_no_name_returns_unnamed(self):
        self.assertEqual(hook.check_name({}), "<unnamed>")


class IsMergeCommandTests(unittest.TestCase):
    """Coverage for the merge-command gate (preserves prior behavior; #219 doesn't touch this)."""

    def test_simple_merge(self):
        self.assertTrue(hook.is_merge_command("gh pr merge 123"))

    def test_merge_with_squash(self):
        self.assertTrue(hook.is_merge_command("gh pr merge 123 --squash"))

    def test_chained_merge(self):
        self.assertTrue(hook.is_merge_command("foo && gh pr merge 1"))

    def test_env_prefix(self):
        self.assertTrue(hook.is_merge_command("ENV=1 gh pr merge 1"))

    def test_pr_list_does_not_match(self):
        self.assertFalse(hook.is_merge_command("gh pr list"))

    def test_pr_view_does_not_match(self):
        self.assertFalse(hook.is_merge_command("gh pr view 1"))

    def test_pr_create_does_not_match(self):
        self.assertFalse(hook.is_merge_command("gh pr create"))

    def test_git_merge_does_not_match(self):
        self.assertFalse(hook.is_merge_command("git merge main"))


class EmptyRollupTests(unittest.TestCase):
    """Issue #307: statusCheckRollup = [] — pin warn-allow behavior.

    Empty rollup means no CI checks have run. Root-cause incident:
    deploy#153 (workflow orphan — no on.pull_request trigger covered the PR).
    Pre-fix behavior: silent allow (return None). Post-fix: allow + warn
    systemMessage so the operator sees the signal.

    Charter decision: preserve allow-merge behavior (changing it requires
    operational change per #307 acceptance); add operator-facing warning.
    """

    @staticmethod
    def _bash_input(command: str) -> dict:
        return {"tool_name": "Bash", "tool_input": {"command": command}}

    def test_empty_rollup_returns_warn_systemMessage(self):
        """`gh pr merge N` with [] rollup → allow + WARNING systemMessage."""
        with mock.patch.object(hook, "fetch_checks", return_value=[]):
            result = hook.check(self._bash_input("gh pr merge 42"))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.get("decision"), "allow")
        self.assertIn("systemMessage", result)
        self.assertIn("empty statusCheckRollup", result["systemMessage"])

    def test_empty_rollup_message_references_workflow_paths_coverage(self):
        """Warning message must point operator at the sibling hook for diagnosis."""
        with mock.patch.object(hook, "fetch_checks", return_value=[]):
            result = hook.check(self._bash_input("gh pr merge 42"))
        assert result is not None
        self.assertIn("validate_workflow_paths_coverage", result["systemMessage"])

    def test_empty_rollup_message_references_deploy_153_incident(self):
        """Warning cites the canonical root-cause incident for operator context."""
        with mock.patch.object(hook, "fetch_checks", return_value=[]):
            result = hook.check(self._bash_input("gh pr merge 42"))
        assert result is not None
        self.assertIn("deploy#153", result["systemMessage"])

    def test_empty_rollup_does_not_block(self):
        """Empty rollup must NOT block — only warn. Preserves prior allow behavior."""
        with mock.patch.object(hook, "fetch_checks", return_value=[]):
            result = hook.check(self._bash_input("gh pr merge 42"))
        # `allow` decision is fine; what matters is decision != "block".
        if result is not None:
            self.assertNotEqual(result.get("decision"), "block")

    def test_admin_override_skips_empty_rollup_check(self):
        """`--admin` short-circuits before fetch_checks — empty rollup never inspected."""
        with mock.patch.object(hook, "fetch_checks", return_value=[]) as mock_fetch:
            result = hook.check(self._bash_input("gh pr merge 42 --admin"))
        self.assertIsNone(result)
        mock_fetch.assert_not_called()

    def test_non_merge_command_not_checked(self):
        """`gh pr view` should not trigger empty-rollup logic at all."""
        with mock.patch.object(hook, "fetch_checks", return_value=[]) as mock_fetch:
            result = hook.check(self._bash_input("gh pr view 42"))
        self.assertIsNone(result)
        mock_fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
