#!/usr/bin/env python3
"""Tests for validate_pr_review hook.

Covers:
- Issue #147: TechDebt attestation must be required ONLY on actual review
  verdicts (Approved / ChangesRequested), NOT on Request or Reply comments.
- Issue #164: reviewer set must dedup on full reviewer name, NOT on
  lastname — two distinct reviewers sharing a lastname (e.g.,
  Lucas Ferreira and Santiago Ferreira) count as TWO reviewers.
- Issue #244: reviewer for verdict comments is the Requestor (comment
  author), NOT the Requestee. Resolves the prior Requestee-as-reviewer
  mismatch with the canonical charter format (resolves #233).
- Issue #228: Single-Reviewer Exception for wave-bootstrap PRs reviewed
  by a charter-enforcer role.

Charter format used in fixtures (canonical per `pull-requests.md`
§ Comment-Based Reviews — Requestor=comment-author, Requestee=comment-target):
- Request comments     → Requestor=PR author,  Requestee=reviewer
- Reply comments       → Requestor=replier,    Requestee=being-replied-to
- Approved verdicts    → Requestor=reviewer,   Requestee=PR author
- ChangesRequested     → Requestor=reviewer,   Requestee=PR author

Also covers the W8 hook-authorship NEGATIVE-MATCH requirement.

Run: ENVIRONMENT=test python3 -m pytest .claude/hooks/tests/test_validate_pr_review.py -v
Or:  ENVIRONMENT=test python3 .claude/hooks/tests/test_validate_pr_review.py
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
sys.path.insert(0, str(_HOOKS_DIR))

import validate_pr_review as hook  # noqa: E402


class IsVerdictTests(unittest.TestCase):
    """Unit tests for the _is_verdict helper — the core filter for #147."""

    def test_approved_is_verdict(self):
        self.assertTrue(hook._is_verdict("Approved"))

    def test_changes_requested_is_verdict(self):
        self.assertTrue(hook._is_verdict("Changes Requested"))

    def test_changes_alone_is_verdict(self):
        """Some teammates use the shorter `Changes` form — accepted per charter."""
        self.assertTrue(hook._is_verdict("Changes"))

    def test_case_insensitive(self):
        self.assertTrue(hook._is_verdict("approved"))
        self.assertTrue(hook._is_verdict("APPROVED"))
        self.assertTrue(hook._is_verdict("Changes REQUESTED"))

    def test_whitespace_trimmed(self):
        self.assertTrue(hook._is_verdict("  Approved  "))
        self.assertTrue(hook._is_verdict("\tApproved\n"))

    def test_markdown_bold_trailing_stripped(self):
        self.assertTrue(hook._is_verdict("Approved*"))
        self.assertTrue(hook._is_verdict("Approved**"))

    # NEGATIVE MATCHES — the whole point of #147.
    def test_request_is_not_verdict(self):
        """RequestOrReplied: Request is NOT a verdict (review request)."""
        self.assertFalse(hook._is_verdict("Request"))

    def test_replied_is_not_verdict(self):
        """RequestOrReplied: Replied is NOT a verdict (author reply)."""
        self.assertFalse(hook._is_verdict("Replied"))

    def test_empty_is_not_verdict(self):
        self.assertFalse(hook._is_verdict(""))
        self.assertFalse(hook._is_verdict("   "))

    def test_unknown_value_is_not_verdict(self):
        self.assertFalse(hook._is_verdict("Maybe"))
        self.assertFalse(hook._is_verdict("Questioned"))


class _CheckCommentReviewsHarness(unittest.TestCase):
    """Common helpers for driving check_comment_reviews() with fake API data."""

    PR_NUMBER = 99
    BRANCH_AUTHOR = "pham"  # matches branch L.Pham/0001-...
    REPO = "noorinalabs/noorinalabs-isnad-graph"

    @staticmethod
    def _run_with_fake_api(comments_list: list[dict], branch_author: str, repo: str | None = None):
        """Run check_comment_reviews with subprocess.run mocked to return the given comments."""
        # First call is gh repo view (owner/name), skipped if repo is provided.
        # Second call is gh api .../issues/{n}/comments.
        repo_view_stdout = json.dumps({"owner": {"login": "noorinalabs"}, "name": "r"})
        comments_stdout = json.dumps(comments_list)

        call_count = {"n": 0}

        def fake_run(args, capture_output, text, timeout):
            call_count["n"] += 1
            result = mock.MagicMock()
            result.returncode = 0
            if args[0] == "gh" and args[1:3] == ["repo", "view"]:
                result.stdout = repo_view_stdout
            else:
                result.stdout = comments_stdout
            return result

        with mock.patch.object(hook.subprocess, "run", side_effect=fake_run):
            return hook.check_comment_reviews(
                _CheckCommentReviewsHarness.PR_NUMBER,
                branch_author,
                repo=repo,
            )


class TechDebtFilterTests(_CheckCommentReviewsHarness):
    """Issue #147: TechDebt line required only on Approved/Changes Requested.

    Each test builds a fake comment list and verifies the
    reviews_missing_tech_debt list contains exactly the expected names.
    """

    @staticmethod
    def _comment(body: str) -> dict:
        return {"body": body, "user": {"login": "anyone"}}

    def test_request_without_techdebt_does_not_block(self):
        """NEGATIVE MATCH for #147: Request comment lacking TechDebt must NOT be flagged."""
        comments = [
            self._comment(
                "Requestor: Linh Pham\nRequestee: Jelani Mwangi\nRequestOrReplied: Request"
            ),
        ]
        result = self._run_with_fake_api(comments, self.BRANCH_AUTHOR, repo=self.REPO)
        self.assertEqual(result.reviews_missing_tech_debt, [])

    def test_replied_without_techdebt_does_not_block(self):
        """NEGATIVE MATCH for #147: Replied comment lacking TechDebt must NOT be flagged."""
        comments = [
            self._comment(
                "Requestor: Linh Pham\nRequestee: Anya Kowalczyk\nRequestOrReplied: Replied"
            ),
        ]
        result = self._run_with_fake_api(comments, self.BRANCH_AUTHOR, repo=self.REPO)
        self.assertEqual(result.reviews_missing_tech_debt, [])

    def test_approved_without_techdebt_does_block(self):
        """Positive: Approved lacking TechDebt MUST still be flagged — #147 does NOT weaken this.

        Canonical format (resolves #244): Requestor=reviewer, Requestee=PR author.
        """
        comments = [
            self._comment(
                "Requestor: Mateo Santos\nRequestee: Linh Pham\nRequestOrReplied: Approved"
            ),
        ]
        result = self._run_with_fake_api(comments, self.BRANCH_AUTHOR, repo=self.REPO)
        self.assertEqual(result.reviews_missing_tech_debt, ["Mateo Santos"])

    def test_changes_requested_without_techdebt_does_block(self):
        comments = [
            self._comment(
                "Requestor: Anya Kowalczyk\nRequestee: Linh Pham\n"
                "RequestOrReplied: Changes Requested"
            ),
        ]
        result = self._run_with_fake_api(comments, self.BRANCH_AUTHOR, repo=self.REPO)
        self.assertEqual(result.reviews_missing_tech_debt, ["Anya Kowalczyk"])

    def test_approved_with_techdebt_none_passes(self):
        comments = [
            self._comment(
                "Requestor: Mateo Santos\nRequestee: Linh Pham\n"
                "RequestOrReplied: Approved\nTechDebt: none"
            ),
        ]
        result = self._run_with_fake_api(comments, self.BRANCH_AUTHOR, repo=self.REPO)
        self.assertEqual(result.reviews_missing_tech_debt, [])

    def test_approved_with_techdebt_issues_passes_and_collects(self):
        comments = [
            self._comment(
                "Requestor: Mateo Santos\nRequestee: Linh Pham\n"
                "RequestOrReplied: Approved\nTechDebt: #15, #16"
            ),
        ]
        result = self._run_with_fake_api(comments, self.BRANCH_AUTHOR, repo=self.REPO)
        self.assertEqual(result.reviews_missing_tech_debt, [])
        self.assertEqual(sorted(result.tech_debt_issue_numbers), ["15", "16"])

    def test_pr_821_scenario(self):
        """Exact scenario from issue #147 repro, in canonical #244 format.

        PR #821 had 3 real reviews (Jelani+Anya approved, Anya changes-requested —
        all with TechDebt) and 4 non-review comments (3 Request, 1 Reply — no
        TechDebt). The hook blocked on the 4 non-review comments. After the fix,
        only actual-verdict comments without TechDebt should be flagged.

        Canonical format (#244): verdict comments swap to Requestor=reviewer.
        """
        comments = [
            # Review requests — Requestor=PR author, Requestee=reviewer (no TechDebt required)
            self._comment(
                "Requestor: Linh Pham\nRequestee: Jelani Mwangi\nRequestOrReplied: Request"
            ),
            self._comment(
                "Requestor: Linh Pham\nRequestee: Anya Kowalczyk\nRequestOrReplied: Request"
            ),
            # Verdicts — Requestor=reviewer, Requestee=PR author
            self._comment(
                "Requestor: Jelani Mwangi\nRequestee: Linh Pham\n"
                "RequestOrReplied: Approved\nTechDebt: none"
            ),
            self._comment(
                "Requestor: Anya Kowalczyk\nRequestee: Linh Pham\n"
                "RequestOrReplied: Changes Requested\nTechDebt: #200"
            ),
            # Author reply — Requestor=replier (Linh), Requestee=being-replied-to (Anya)
            self._comment(
                "Requestor: Linh Pham\nRequestee: Anya Kowalczyk\nRequestOrReplied: Replied"
            ),
            # Re-request for re-review after changes
            self._comment(
                "Requestor: Linh Pham\nRequestee: Anya Kowalczyk\nRequestOrReplied: Request"
            ),
            # Re-review approval — Requestor=reviewer (Anya)
            self._comment(
                "Requestor: Anya Kowalczyk\nRequestee: Linh Pham\n"
                "RequestOrReplied: Approved\nTechDebt: none"
            ),
        ]
        result = self._run_with_fake_api(comments, self.BRANCH_AUTHOR, repo=self.REPO)
        self.assertEqual(
            result.reviews_missing_tech_debt, [], "non-verdict comments must not be flagged"
        )
        self.assertEqual(sorted(result.tech_debt_issue_numbers), ["200"])

    def test_markdown_bold_ror_value_still_filtered(self):
        """`**RequestOrReplied:** Request` with markdown bold — still not a verdict."""
        comments = [
            self._comment(
                "**Requestor:** Linh Pham\n"
                "**Requestee:** Jelani Mwangi\n"
                "**RequestOrReplied:** Request"
            ),
        ]
        result = self._run_with_fake_api(comments, self.BRANCH_AUTHOR, repo=self.REPO)
        self.assertEqual(result.reviews_missing_tech_debt, [])

    def test_markdown_bold_approved_still_requires_techdebt(self):
        comments = [
            self._comment(
                "**Requestor:** Mateo Santos\n"
                "**Requestee:** Linh Pham\n"
                "**RequestOrReplied:** Approved"
            ),
        ]
        result = self._run_with_fake_api(comments, self.BRANCH_AUTHOR, repo=self.REPO)
        self.assertEqual(result.reviews_missing_tech_debt, ["Mateo Santos"])


class ReviewerDedupTests(_CheckCommentReviewsHarness):
    """Issue #164: reviewer set must dedup on full name, NOT on lastname.

    Prior behavior keyed the set on lastname, so Lucas Ferreira and Santiago
    Ferreira counted as one reviewer. Guard tests for the full-name fix.

    Post-#244 reviewer identification uses Requestor on verdict comments;
    fixtures updated to canonical format (Requestor=reviewer).
    """

    @staticmethod
    def _comment(body: str) -> dict:
        return {"body": body, "user": {"login": "anyone"}}

    def test_two_reviewers_same_lastname_count_as_two(self):
        """NEGATIVE MATCH for #164: two Ferreiras must count as 2, not 1.

        Canonical format: each reviewer is the Requestor of their own
        Approved verdict comment.
        """
        comments = [
            self._comment(
                "Requestor: Lucas Ferreira\nRequestee: Linh Pham\n"
                "RequestOrReplied: Approved\nTechDebt: none"
            ),
            self._comment(
                "Requestor: Santiago Ferreira\nRequestee: Linh Pham\n"
                "RequestOrReplied: Approved\nTechDebt: none"
            ),
        ]
        result = self._run_with_fake_api(comments, self.BRANCH_AUTHOR, repo=self.REPO)
        self.assertEqual(
            len(result.reviewers),
            2,
            f"two distinct reviewers sharing lastname collapsed into: {result.reviewers}",
        )
        self.assertIn("lucas ferreira", result.reviewers)
        self.assertIn("santiago ferreira", result.reviewers)

    def test_same_person_counted_once_across_multiple_comments(self):
        """Positive: same reviewer's verdict counts once even across re-cycles.

        Canonical format: the Approved verdict has Requestor=reviewer.
        Request comments (Requestor=PR author) do NOT contribute to the
        reviewer set after the #244 fix — only Approved verdicts count.
        """
        comments = [
            # Initial review request (Requestor=PR author) — does NOT count toward reviewers
            self._comment(
                "Requestor: Linh Pham\nRequestee: Mateo Santos\nRequestOrReplied: Request"
            ),
            # Verdict (Requestor=reviewer) — counts
            self._comment(
                "Requestor: Mateo Santos\nRequestee: Linh Pham\n"
                "RequestOrReplied: Approved\nTechDebt: none"
            ),
        ]
        result = self._run_with_fake_api(comments, self.BRANCH_AUTHOR, repo=self.REPO)
        self.assertEqual(len(result.reviewers), 1)
        self.assertIn("mateo santos", result.reviewers)

    def test_branch_author_lastname_still_excluded(self):
        """Author-equality check still works on Requestor (post-#244).

        Branch author has lastname `Pham`. If a Pham-surnamed Requestor
        somehow appears on an Approved verdict (a self-approval attempt),
        it must be excluded. Regression guard for the author-equality
        branch on the now-canonical Requestor field.
        """
        comments = [
            self._comment(
                "Requestor: Linh Pham\nRequestee: Linh Pham\n"
                "RequestOrReplied: Approved\nTechDebt: none"
            ),
        ]
        result = self._run_with_fake_api(comments, self.BRANCH_AUTHOR, repo=self.REPO)
        self.assertEqual(result.reviewers, set(), "branch author must not self-review")


class ExtractBranchAuthorLastnameTests(unittest.TestCase):
    """Regression tests for issue #179.

    The regex must accept BOTH separator styles seen in practice — the
    charter-spec slash and the dash-separator that recent branches actually
    use. When the regex missed dash-separator branches, reviewer-counting
    never ran and merges blocked on 0/2 reviews.
    """

    def test_slash_separator_legacy(self):
        """Legacy slash separator still extracts lastname."""
        self.assertEqual(hook.extract_branch_author_lastname("A.Virtanen/0001-foo"), "Virtanen")

    def test_dash_separator_current(self):
        """Dash separator — the fix for #179."""
        self.assertEqual(hook.extract_branch_author_lastname("A.Virtanen-0001-foo"), "Virtanen")

    # NEGATIVE MATCHES — hook-authorship spec requires neg coverage.
    def test_underscore_separator_rejected(self):
        """Underscore is NOT an accepted separator."""
        self.assertIsNone(hook.extract_branch_author_lastname("A.Virtanen_0001-foo"))

    def test_plain_branch_name_rejected(self):
        """A branch without the `{Initial}.{LastName}` prefix returns None."""
        self.assertIsNone(hook.extract_branch_author_lastname("main"))

    def test_no_separator_rejected(self):
        """Prefix present but no separator before trailing content returns None."""
        self.assertIsNone(hook.extract_branch_author_lastname("A.Virtanen0001"))


class MergeCommandMatchTests(unittest.TestCase):
    """Regression tests for the merge-command gate."""

    def test_gh_pr_merge_matches(self):
        self.assertTrue(hook.is_merge_command("gh pr merge 123"))
        self.assertTrue(hook.is_merge_command("gh pr merge 123 --squash"))
        self.assertTrue(hook.is_merge_command("gh pr merge --repo x/y 123"))

    def test_chained_matches(self):
        self.assertTrue(hook.is_merge_command("foo && gh pr merge 1"))
        self.assertTrue(hook.is_merge_command("ENV=1 gh pr merge 1"))

    def test_non_merge_does_not_match(self):
        self.assertFalse(hook.is_merge_command("gh pr list"))
        self.assertFalse(hook.is_merge_command("gh pr view 1"))
        self.assertFalse(hook.is_merge_command("gh pr create"))
        self.assertFalse(hook.is_merge_command("git merge main"))
        self.assertFalse(hook.is_merge_command("gh pr checks"))


class IsApprovedTests(unittest.TestCase):
    """Issue #244: only Approved comments count toward the 2-reviewer rule.

    ChangesRequested is a verdict (TechDebt required) but does NOT contribute
    to the 2-Approved-distinct-reviewer threshold per charter line 36.
    """

    def test_approved_is_approved(self):
        self.assertTrue(hook._is_approved("Approved"))

    def test_lowercase_approved(self):
        self.assertTrue(hook._is_approved("approved"))

    def test_changes_requested_is_not_approved(self):
        self.assertFalse(hook._is_approved("Changes Requested"))

    def test_changesrequested_camelcase_is_not_approved(self):
        self.assertFalse(hook._is_approved("ChangesRequested"))

    def test_request_is_not_approved(self):
        self.assertFalse(hook._is_approved("Request"))

    def test_replied_is_not_approved(self):
        self.assertFalse(hook._is_approved("Replied"))


class RequestorCountingTests(_CheckCommentReviewsHarness):
    """Issue #244: reviewer for verdict comments is the Requestor (comment author).

    Pre-#244 the hook counted distinct Requestee values. Post-#244 it counts
    distinct Requestor values across Approved comments only.
    """

    @staticmethod
    def _comment(body: str) -> dict:
        return {"body": body, "user": {"login": "anyone"}}

    def test_approved_counts_requestor(self):
        """Two Approved verdicts from distinct Requestors → 2 reviewers."""
        comments = [
            self._comment(
                "Requestor: Anya Kowalczyk\nRequestee: Linh Pham\n"
                "RequestOrReplied: Approved\nTechDebt: none"
            ),
            self._comment(
                "Requestor: Jelani Mwangi\nRequestee: Linh Pham\n"
                "RequestOrReplied: Approved\nTechDebt: none"
            ),
        ]
        result = self._run_with_fake_api(comments, self.BRANCH_AUTHOR, repo=self.REPO)
        self.assertEqual(len(result.reviewers), 2)
        self.assertIn("anya kowalczyk", result.reviewers)
        self.assertIn("jelani mwangi", result.reviewers)

    def test_request_does_not_count_toward_reviewers(self):
        """A Request comment (Requestor=PR author) is NOT a review verdict."""
        comments = [
            self._comment(
                "Requestor: Linh Pham\nRequestee: Anya Kowalczyk\nRequestOrReplied: Request"
            ),
        ]
        result = self._run_with_fake_api(comments, self.BRANCH_AUTHOR, repo=self.REPO)
        self.assertEqual(result.reviewers, set())

    def test_changes_requested_does_not_count_toward_approved_threshold(self):
        """ChangesRequested is a verdict but NOT toward the 2-Approved threshold.

        Charter line 36: "two distinct Requestor values" specifically across
        `Approved` comments. CR comments do not satisfy the threshold.
        """
        comments = [
            self._comment(
                "Requestor: Anya Kowalczyk\nRequestee: Linh Pham\n"
                "RequestOrReplied: Changes Requested\nTechDebt: none"
            ),
        ]
        result = self._run_with_fake_api(comments, self.BRANCH_AUTHOR, repo=self.REPO)
        # ChangesRequested has TechDebt so it's a verdict (no missing-attestation
        # error), but the reviewer set stays empty because only Approved counts.
        self.assertEqual(result.reviewers, set())
        self.assertEqual(result.reviews_missing_tech_debt, [])

    def test_p3w3_wave_merge_repro(self):
        """Exact repro of the P3W3 wave-merge --admin episode (issue #244).

        Wave-merge PRs had 2 distinct Approveds, but the prior hook counted
        Requestee (= PR author) and saw 1 distinct value → blocked. With
        #244 fix counting Requestor, both reviewers are recognized.
        """
        comments = [
            # Two distinct reviewers Approved — canonical Requestor=reviewer
            self._comment(
                "Requestor: Bereket Tadesse\nRequestee: Aino Virtanen\n"
                "RequestOrReplied: Approved\nTechDebt: none"
            ),
            self._comment(
                "Requestor: Lucas Ferreira\nRequestee: Aino Virtanen\n"
                "RequestOrReplied: Approved\nTechDebt: none"
            ),
        ]
        # Branch author lastname is "Virtanen" (Aino's wave-merge PR).
        result = self._run_with_fake_api(comments, "Virtanen", repo=self.REPO)
        self.assertEqual(
            len(result.reviewers),
            2,
            "P3W3 #244 repro: should count Bereket + Lucas as 2 distinct Requestors",
        )


class LoadCharterEnforcerNamesTests(unittest.TestCase):
    """Issue #228: charter-enforcer names parsed from local roster filenames.

    Tests against the parent repo's actual roster (Aino Virtanen as
    standards_lead, Nadia Khoury as program_director). The hook uses
    `_ROSTER_DIR` resolved relative to the hook file at module import.
    """

    def test_parent_roster_includes_aino(self):
        """Parent's standards_lead_aino.md → Aino Virtanen is an enforcer."""
        enforcers = hook.load_charter_enforcer_names()
        self.assertIn(
            "aino virtanen",
            enforcers,
            f"Standards Lead missing from charter enforcers: {enforcers}",
        )

    def test_parent_roster_includes_nadia(self):
        """Parent's program_director_nadia.md → Nadia Khoury is an enforcer."""
        enforcers = hook.load_charter_enforcer_names()
        self.assertIn("nadia khoury", enforcers)

    def test_engineer_roles_excluded(self):
        """`sre_engineer_*`, `security_engineer_*`, etc. are NOT enforcers."""
        enforcers = hook.load_charter_enforcer_names()
        # Aisha (sre_engineer) and Nino (security_engineer) must NOT be in the set.
        self.assertNotIn("aisha idrissi", enforcers)
        self.assertNotIn("nino kavtaradze", enforcers)


class SingleReviewerExceptionTests(unittest.TestCase):
    """Issue #228: hook honors charter's Single-Reviewer Exception."""

    def test_exception_grants_with_label_and_enforcer(self):
        """Label `wave-bootstrap` + sole reviewer is a charter enforcer → exception applies."""
        # Use Aino's lowercased full name (matches what reviewers set holds).
        self.assertTrue(
            hook.is_single_reviewer_exception(
                pr_labels=["wave-bootstrap", "tech-debt"],
                reviewers={"aino virtanen"},
            )
        )

    def test_exception_denied_without_label(self):
        """No `wave-bootstrap` label → exception does NOT apply."""
        self.assertFalse(
            hook.is_single_reviewer_exception(
                pr_labels=["tech-debt"],
                reviewers={"aino virtanen"},
            )
        )

    def test_exception_denied_with_zero_reviewers(self):
        """Zero reviewers is not "exactly one" — exception does NOT apply."""
        self.assertFalse(
            hook.is_single_reviewer_exception(
                pr_labels=["wave-bootstrap"],
                reviewers=set(),
            )
        )

    def test_exception_denied_with_two_reviewers(self):
        """Two reviewers means the strict rule is already satisfied — exception unnecessary."""
        self.assertFalse(
            hook.is_single_reviewer_exception(
                pr_labels=["wave-bootstrap"],
                reviewers={"aino virtanen", "nadia khoury"},
            )
        )

    def test_exception_denied_with_non_enforcer_reviewer(self):
        """`wave-bootstrap` label + sole reviewer is NOT a charter enforcer → no exception."""
        self.assertFalse(
            hook.is_single_reviewer_exception(
                pr_labels=["wave-bootstrap"],
                reviewers={"some random engineer"},
            )
        )


class CheckEndToEndTests(unittest.TestCase):
    """End-to-end check() integration tests for #244 + #228 paths."""

    @staticmethod
    def _input(command: str) -> dict:
        return {"tool_name": "Bash", "tool_input": {"command": command}}

    def _patch_pr_data(self, **overrides) -> dict:
        """Build a stub PR-data dict with sensible defaults; override per test."""
        base = {
            "author": "parametrization",
            "number": 100,
            "reviews": [],  # no formal GitHub reviews in any of these tests
            "headRefName": "L.Pham/0001-fix",
            "labels": [],
        }
        base.update(overrides)
        return base

    def test_two_distinct_approved_requestors_allows_merge(self):
        """Canonical happy path: 2 distinct Requestors on Approved comments → allow."""
        review_result = hook.CommentReviewResult()
        review_result.reviewers = {"anya kowalczyk", "jelani mwangi"}
        with (
            mock.patch.object(hook, "get_pr_data", return_value=self._patch_pr_data()),
            mock.patch.object(hook, "check_comment_reviews", return_value=review_result),
        ):
            result = hook.check(self._input("gh pr merge 100 --squash"))
        self.assertIsNone(result, "2 distinct Requestor Approveds should allow merge")

    def test_one_reviewer_without_wave_bootstrap_blocks(self):
        """Strict rule: 1 reviewer + no wave-bootstrap label → block."""
        review_result = hook.CommentReviewResult()
        review_result.reviewers = {"anya kowalczyk"}
        with (
            mock.patch.object(hook, "get_pr_data", return_value=self._patch_pr_data()),
            mock.patch.object(hook, "check_comment_reviews", return_value=review_result),
        ):
            result = hook.check(self._input("gh pr merge 100 --squash"))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["decision"], "block")
        self.assertIn("1/2", result["reason"])

    def test_block_message_explains_reply_vs_approved(self):
        """BLOCKED message MUST surface the Reply-vs-Approved distinction and
        the diagnostic recipe. Codified by #352 after a P3W8 17-addendum
        cascade across 11 PRs where spawn briefs initially specified
        `RequestOrReplied: Reply` and the prior message didn't explain why
        Reply doesn't count.
        """
        review_result = hook.CommentReviewResult()
        review_result.reviewers = {"anya kowalczyk"}  # 1/2
        with (
            mock.patch.object(hook, "get_pr_data", return_value=self._patch_pr_data()),
            mock.patch.object(hook, "check_comment_reviews", return_value=review_result),
        ):
            result = hook.check(self._input("gh pr merge 100 --squash"))
        assert result is not None
        reason = result["reason"]
        # Failure-mode framing: Reply-vs-Approved distinction is named.
        self.assertIn("Reply vs Approved", reason)
        self.assertIn(
            "Reply / Replied / Request / ChangesRequested do NOT",
            reason,
        )
        # Body-prose-not-inspected framing (so operator doesn't think
        # "looks good" or "Approved." in the body fixes it).
        self.assertIn("body prose is not inspected", reason)
        # Diagnostic recipe: gh api jq one-liner is shown.
        self.assertIn("gh api repos/<owner>/<repo>/issues/<PR>/comments", reason)
        self.assertIn('contains("RequestOrReplied: Approved")', reason)
        # Memory pointer: canonical reference for full context.
        self.assertIn("feedback_validate_pr_review_approved_not_reply.md", reason)

    def test_one_reviewer_with_wave_bootstrap_and_enforcer_allows(self):
        """Single-Reviewer Exception (#228): wave-bootstrap + charter enforcer → allow.

        Uses the actual parent roster — Aino Virtanen is the Standards Lead.
        """
        review_result = hook.CommentReviewResult()
        review_result.reviewers = {"aino virtanen"}
        with (
            mock.patch.object(
                hook,
                "get_pr_data",
                return_value=self._patch_pr_data(labels=["wave-bootstrap", "tech-debt"]),
            ),
            mock.patch.object(hook, "check_comment_reviews", return_value=review_result),
        ):
            result = hook.check(self._input("gh pr merge 100 --squash"))
        self.assertIsNone(
            result,
            "wave-bootstrap PR with charter-enforcer Approved should merge with 1 reviewer",
        )

    def test_one_reviewer_with_wave_bootstrap_but_non_enforcer_blocks(self):
        """Single-Reviewer Exception requires a charter-enforcer reviewer.

        wave-bootstrap label alone does NOT grant the exception — the sole
        reviewer must also be a charter-enforcer per local roster.
        """
        review_result = hook.CommentReviewResult()
        review_result.reviewers = {"some engineer"}
        with (
            mock.patch.object(
                hook,
                "get_pr_data",
                return_value=self._patch_pr_data(labels=["wave-bootstrap"]),
            ),
            mock.patch.object(hook, "check_comment_reviews", return_value=review_result),
        ):
            result = hook.check(self._input("gh pr merge 100 --squash"))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["decision"], "block")

    def test_admin_short_circuits(self):
        """--admin allows merge regardless of reviewer count (emergency override)."""
        with mock.patch.object(hook, "get_pr_data") as get_mock:
            result = hook.check(self._input("gh pr merge 100 --admin"))
        self.assertIsNone(result)
        get_mock.assert_not_called()

    def test_wave_merge_head_ref_runs_comment_review(self):
        """Issue #294: wave-merge PRs (head = deployments/phase-{N}/wave-{M}) must
        invoke check_comment_reviews with an empty-string author-lastname sentinel
        rather than silently skipping it.

        Before the fix, extract_branch_author_lastname() returned None for the
        wave-branch shape and the inner `if branch_author_lastname:` short-circuited,
        leaving comment_review_result empty — the 2-reviewer gate blocked legitimate
        wave-merge PRs even when 2 charter-format Approved comments were present.

        With the fix, the new `elif` clause detects deployments/.../wave-... heads
        and calls check_comment_reviews(number, "", repo=repo) so existing
        reviewer-vs-author lastname comparison admits any non-empty reviewer name.
        """
        review_result = hook.CommentReviewResult()
        review_result.reviewers = {"aino virtanen", "nadia khoury"}
        with (
            mock.patch.object(
                hook,
                "get_pr_data",
                return_value=self._patch_pr_data(headRefName="deployments/phase-3/wave-6"),
            ),
            mock.patch.object(
                hook, "check_comment_reviews", return_value=review_result
            ) as ccr_mock,
        ):
            result = hook.check(self._input("gh pr merge 100 --squash"))
        self.assertIsNone(
            result,
            "wave-merge PR with 2 charter-format Approveds should allow merge",
        )
        ccr_mock.assert_called_once()
        # Empty-string sentinel is what permits any non-empty reviewer name.
        call_args = ccr_mock.call_args
        self.assertEqual(call_args.args[0], 100)
        self.assertEqual(call_args.args[1], "")

    def test_wave_merge_head_ref_blocks_with_one_reviewer(self):
        """Issue #294: wave-merge PRs still subject to the 2-reviewer threshold.

        The fix only routes the comment-review check; it does NOT relax the
        reviewer count requirement. A wave-merge PR with a single Approved
        comment must still block (no wave-bootstrap exception applies here).
        """
        review_result = hook.CommentReviewResult()
        review_result.reviewers = {"aino virtanen"}
        with (
            mock.patch.object(
                hook,
                "get_pr_data",
                return_value=self._patch_pr_data(headRefName="deployments/phase-3/wave-6"),
            ),
            mock.patch.object(hook, "check_comment_reviews", return_value=review_result),
        ):
            result = hook.check(self._input("gh pr merge 100 --squash"))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["decision"], "block")
        self.assertIn("1/2", result["reason"])


if __name__ == "__main__":
    unittest.main()
