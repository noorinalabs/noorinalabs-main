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
import re
import sys
import unittest
from datetime import datetime
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
                # content_ts is a REQUIRED keyword-only arg (#1050); None is the
                # explicit "no content binding" value these ~30 pre-#950 callers
                # exercise (every verdict counted unconditionally).
                content_ts=None,
            )

    @staticmethod
    def _run_with_fake_api_ts(
        comments_list: list[dict],
        branch_author: str,
        repo: str | None = None,
        content_ts: "datetime | None" = None,
    ):
        """As `_run_with_fake_api`, but binds verdicts to a T_content (#950).

        Kept as a separate entry point so the ~30 pre-#950 callers of
        `_run_with_fake_api` keep exercising the unbound path unchanged.
        """
        comments_stdout = json.dumps(comments_list)

        def fake_run(args, capture_output, text, timeout):
            result = mock.MagicMock()
            result.returncode = 0
            if args[0] == "gh" and args[1:3] == ["repo", "view"]:
                result.stdout = json.dumps({"owner": {"login": "noorinalabs"}, "name": "r"})
            else:
                result.stdout = comments_stdout
            return result

        with mock.patch.object(hook.subprocess, "run", side_effect=fake_run):
            return hook.check_comment_reviews(
                _CheckCommentReviewsHarness.PR_NUMBER,
                branch_author,
                repo=repo,
                content_ts=content_ts,
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

    def test_approved_with_bare_techdebt_number_captures(self):
        """main#1055: a bare issue number (no `#`) must still be captured.

        Reproduction — Nino's verdict on PR #1052 wrote `TechDebt: 1054`; the
        pre-fix regex `#(\\d+)` matched nothing against a value with no `#`.
        """
        comments = [
            self._comment(
                "Requestor: Nino Kavtaradze\nRequestee: Nadia Khoury\n"
                "RequestOrReplied: Approved\nTechDebt: 1054"
            ),
        ]
        result = self._run_with_fake_api(comments, self.BRANCH_AUTHOR, repo=self.REPO)
        self.assertEqual(result.reviews_missing_tech_debt, [])
        self.assertEqual(result.tech_debt_issue_numbers, ["1054"])
        self.assertEqual(result.tech_debt_unparseable, [])

    def test_approved_with_bare_techdebt_number_list_captures(self):
        comments = [
            self._comment(
                "Requestor: Mateo Santos\nRequestee: Linh Pham\n"
                "RequestOrReplied: Approved\nTechDebt: 1054, 1055"
            ),
        ]
        result = self._run_with_fake_api(comments, self.BRANCH_AUTHOR, repo=self.REPO)
        self.assertEqual(sorted(result.tech_debt_issue_numbers), ["1054", "1055"])
        self.assertEqual(result.tech_debt_unparseable, [])

    def test_approved_with_mixed_hash_and_bare_numbers_captures_both(self):
        comments = [
            self._comment(
                "Requestor: Mateo Santos\nRequestee: Linh Pham\n"
                "RequestOrReplied: Approved\nTechDebt: 1054 and #1055"
            ),
        ]
        result = self._run_with_fake_api(comments, self.BRANCH_AUTHOR, repo=self.REPO)
        self.assertEqual(sorted(result.tech_debt_issue_numbers), ["1054", "1055"])

    def test_approved_with_junk_techdebt_value_is_reported_not_swallowed(self):
        """main#1055: free text (neither `none` nor a number) must be RECORDED,
        not silently dropped — the residual case is the actual bug, not just
        the strictness of the regex.
        """
        comments = [
            self._comment(
                "Requestor: Mateo Santos\nRequestee: Linh Pham\n"
                "RequestOrReplied: Approved\nTechDebt: filed later"
            ),
        ]
        result = self._run_with_fake_api(comments, self.BRANCH_AUTHOR, repo=self.REPO)
        self.assertEqual(result.reviews_missing_tech_debt, [])
        self.assertEqual(result.tech_debt_issue_numbers, [])
        self.assertEqual(result.tech_debt_unparseable, [("Mateo Santos", "filed later")])

    def test_techdebt_none_is_not_flagged_as_unparseable(self):
        comments = [
            self._comment(
                "Requestor: Mateo Santos\nRequestee: Linh Pham\n"
                "RequestOrReplied: Approved\nTechDebt: none"
            ),
        ]
        result = self._run_with_fake_api(comments, self.BRANCH_AUTHOR, repo=self.REPO)
        self.assertEqual(result.tech_debt_unparseable, [])

    def test_mutation_verify_old_regex_would_drop_bare_number(self):
        """Pin the exact defect (main#1055): the pre-fix `#(\\d+)` regex
        captures nothing from a bare number. Proves the new `#?(\\d+)` regex
        is the actual fix, not incidental — if someone reverts the `#?` to
        `#`, this assertion demonstrates why that regresses.
        """
        old_regex = r"#(\d+)"
        new_regex = r"#?(\d+)"
        self.assertEqual(re.findall(old_regex, "1054"), [])
        self.assertEqual(re.findall(new_regex, "1054"), ["1054"])

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


class LatestVerdictSupersedesTests(_CheckCommentReviewsHarness):
    """Issue #940: the reviewer set is monotonic — an approval cannot be
    withdrawn, and a reviewer standing at Changes Requested still counts as
    an approver if they ever approved earlier in the thread.

    The fix keys each reviewer's verdict by their LATEST charter-format
    comment (chronological = fixture list order, since these tests pass no
    `content_ts` and so exercise the unbound #950 path). Only a reviewer
    whose latest verdict is Approved contributes to the reviewer set.
    """

    @staticmethod
    def _verdict(requestor: str, ror: str, requestee: str = "Linh Pham") -> dict:
        return {
            "body": (
                f"Requestor: {requestor}\nRequestee: {requestee}\n"
                f"RequestOrReplied: {ror}\nTechDebt: none"
            ),
            "user": {"login": "anyone"},
        }

    def test_approved_then_changes_requested_is_excluded(self):
        """Guard for #940: this must RED under the pre-fix monotonic union.

        An Approved followed by a Changes Requested from the SAME reviewer —
        the fixture shape the issue calls out as the one that proves the
        defect (a fixture with only the reverse order "passes under both
        implementations and proves nothing").
        """
        comments = [
            self._verdict("Oyunbileg Batbayar", "Approved"),
            self._verdict("Oyunbileg Batbayar", "Changes Requested"),
        ]
        result = self._run_with_fake_api(comments, self.BRANCH_AUTHOR, repo=self.REPO)
        self.assertNotIn(
            "oyunbileg batbayar",
            result.reviewers,
            "a later Changes Requested must withdraw the earlier Approved",
        )
        self.assertEqual(result.reviewers, set())

    def test_changes_requested_then_approved_is_included(self):
        """The symmetric case: a later Approved supersedes an earlier block."""
        comments = [
            self._verdict("Kwesi Boateng", "Changes Requested"),
            self._verdict("Kwesi Boateng", "Approved"),
        ]
        result = self._run_with_fake_api(comments, self.BRANCH_AUTHOR, repo=self.REPO)
        self.assertIn("kwesi boateng", result.reviewers)

    def test_da359_shaped_timeline_reproduces_the_correct_verdicts(self):
        """Reproduces the exact da#359 timeline from #940's report.

        Chronological verdicts:
          Oyunbileg Batbayar: Approved -> Changes Requested -> Changes Requested
          Alejandra Reyes-Fuentes: Approved
          Kwesi Boateng: Changes Requested -> Approved

        Standing verdict is Oyunbileg BLOCKING, Alejandra and Kwesi APPROVED —
        exactly 2 current approvers, not the pre-fix count of 3.
        """
        comments = [
            self._verdict("Oyunbileg Batbayar", "Approved"),
            self._verdict("Alejandra Reyes-Fuentes", "Approved"),
            self._verdict("Oyunbileg Batbayar", "Changes Requested"),
            self._verdict("Oyunbileg Batbayar", "Changes Requested"),
            self._verdict("Kwesi Boateng", "Changes Requested"),
            self._verdict("Kwesi Boateng", "Approved"),
        ]
        result = self._run_with_fake_api(comments, self.BRANCH_AUTHOR, repo=self.REPO)
        self.assertEqual(
            result.reviewers,
            {"alejandra reyes-fuentes", "kwesi boateng"},
        )
        self.assertNotIn("oyunbileg batbayar", result.reviewers)
        self.assertEqual(len(result.reviewers), 2)

    def test_stale_verdict_does_not_override_a_later_current_one(self):
        """A verdict predating T_content is excluded from `latest_verdict`
        entirely (#950) — it must not be able to overwrite the reviewer's
        genuinely-latest CURRENT verdict just because it appears later in
        `stale_verdicts` bookkeeping. Here the reviewer's only CURRENT verdict
        is Approved; an earlier STALE Changes Requested must not block them.
        """
        content_ts = hook._parse_iso8601("2026-01-02T00:00:00Z")
        stale_ts = "2026-01-01T00:00:00Z"
        fresh_ts = "2026-01-03T00:00:00Z"
        comments = [
            {
                "body": (
                    "Requestor: Nino Kavtaradze\nRequestee: Linh Pham\n"
                    "RequestOrReplied: Changes Requested\nTechDebt: none"
                ),
                "created_at": stale_ts,
            },
            {
                "body": (
                    "Requestor: Nino Kavtaradze\nRequestee: Linh Pham\n"
                    "RequestOrReplied: Approved\nTechDebt: none"
                ),
                "created_at": fresh_ts,
            },
        ]
        result = self._run_with_fake_api_ts(
            comments, self.BRANCH_AUTHOR, repo=self.REPO, content_ts=content_ts
        )
        self.assertIn("nino kavtaradze", result.reviewers)
        self.assertEqual(len(result.stale_verdicts), 1)


class ContentTsRequiredTests(unittest.TestCase):
    """Issue #1050: `content_ts` must be a REQUIRED argument on both shared
    gate helpers, not a defaulted one.

    #1046 happened because a defaulted `content_ts` let a caller omit it and
    silently get staleness-filtering OFF rather than an error. This class
    proves the fix at the signature level: calling either function WITHOUT
    `content_ts` must now raise `TypeError` at call time — the omission
    becomes loud instead of a silent fail-open. These tests would RED against
    the pre-#1050 signatures (which default `content_ts` to `None`).
    """

    def test_check_comment_reviews_without_content_ts_raises_type_error(self):
        with self.assertRaises(TypeError):
            hook.check_comment_reviews(451, "pham", repo="noorinalabs/x")  # missing content_ts

    def test_partition_formal_reviewers_without_content_ts_raises_type_error(self):
        with self.assertRaises(TypeError):
            hook.partition_formal_reviewers([], "someone")  # missing content_ts

    def test_check_comment_reviews_still_accepts_explicit_none(self):
        """`content_ts=None` remains a legitimate VALUE — only omission is barred."""
        with mock.patch.object(
            hook.subprocess,
            "run",
            side_effect=lambda args, capture_output, text, timeout: mock.MagicMock(
                returncode=0, stdout="[]"
            ),
        ):
            result = hook.check_comment_reviews(451, "pham", repo="noorinalabs/x", content_ts=None)
        self.assertEqual(result.undetermined, "")

    def test_partition_formal_reviewers_still_accepts_explicit_none(self):
        formal, stale = hook.partition_formal_reviewers(
            [{"author": {"login": "reviewer-a"}, "state": "APPROVED"}],
            "author-login",
            None,
        )
        self.assertEqual(formal, {"reviewer-a"})
        self.assertEqual(stale, [])

    def test_check_comment_reviews_repo_is_keyword_only(self):
        """`repo` moved keyword-only alongside `content_ts` (#1050) — a
        positional third argument must now raise TypeError rather than
        silently binding to `repo`."""
        with self.assertRaises(TypeError):
            hook.check_comment_reviews(451, "pham", "noorinalabs/x")  # repo positional


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


class _NoContentBindingHarness(unittest.TestCase):
    """Pins T_content to None so pre-#950 `check()` tests stay hermetic.

    As of #950 `check()` fetches the branch's latest non-merge commit BEFORE
    counting any verdict, and hard-blocks if that fetch fails. The tests below
    predate the binding and assert reviewer-COUNTING behavior that is orthogonal
    to staleness; left alone they would shell out to a real `gh api` and fail (or
    worse, flake on network). Returning None means "no content binding" — every
    verdict counts, exactly as before #950 — which is what these tests intend.

    Staleness itself is covered by `StaleVerdictBindingTests`,
    `BranchUpdateRegressionTests`, and `CommitFetchFailClosedTests`, which patch
    `get_latest_content_commit` with real values instead.
    """

    def setUp(self) -> None:
        super().setUp()
        patcher = mock.patch.object(hook, "get_latest_content_commit", return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)


class CheckEndToEndTests(_NoContentBindingHarness):
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
        """Canonical happy path: 2 distinct Requestors on Approved comments → allow.

        Uses real parent-roster personas (Aino + Nadia) so the #498 roster
        gate admits both. Pre-#498 this test used fictional personas (Anya
        Kowalczyk / Jelani Mwangi) that incidentally passed because Hook 4
        didn't yet cross-check roster membership — exactly the asymmetry
        #498 closes.
        """
        review_result = hook.CommentReviewResult()
        review_result.reviewers = {"aino virtanen", "nadia khoury"}
        with (
            mock.patch.object(hook, "get_pr_data", return_value=self._patch_pr_data()),
            mock.patch.object(hook, "check_comment_reviews", return_value=review_result),
        ):
            result = hook.check(self._input("gh pr merge 100 --squash"))
        self.assertIsNone(result, "2 distinct Requestor Approveds should allow merge")

    def test_one_reviewer_without_wave_bootstrap_blocks(self):
        """Strict rule: 1 reviewer + no wave-bootstrap label → block.

        Uses a real roster persona (Aino) so the failure mode tested is
        purely the count shortfall, not a #498 non-roster rejection.
        """
        review_result = hook.CommentReviewResult()
        review_result.reviewers = {"aino virtanen"}
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
        self.assertIn("feedback_pr_review_verdict_format.md", reason)

    def test_block_message_explains_requestor_requestee_swap(self):
        """BLOCKED message MUST surface the Requestor/Requestee swap failure
        mode (W9 PR#349 cascade), in addition to the Reply-vs-Approved one
        (#352). The two failure modes are field-distinct: Reply-vs-Approved
        is wrong RoR value; swap is wrong Requestor/Requestee assignment.
        Codified by #356 after orchestrator spawn-brief template had the
        Requestor/Requestee fields swapped for 7 reviewer posts on PR#349
        before the hook caught the 1-distinct count.
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
        # Failure-mode framing: swap is named as a distinct mode parallel to
        # Reply-vs-Approved (not merged into it).
        self.assertIn("Requestor / Requestee swap", reason)
        # Field-direction clarification.
        self.assertIn("Requestor is the REVIEWER", reason)
        self.assertIn("Requestee is the PR AUTHOR", reason)
        # Origin-story pointer: name the W9 PR#349 cascade so an operator
        # hitting the same shape can cross-reference.
        self.assertIn("W9 PR#349 cascade", reason)
        # Diagnostic recipe: distinct-Requestor jq one-liner is shown.
        self.assertIn("Requestor:", reason)
        self.assertIn("unique", reason)
        # Charter pointer: § Comment-Based Reviews Direction table.
        self.assertIn(
            "pull-requests.md § Comment-Based Reviews",
            reason,
        )

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


class CommentPaginationTests(_CheckCommentReviewsHarness):
    """Issue #303: PR comments fetched with `gh api --paginate`.

    Pre-fix the hook fetched `?per_page=100` without `--paginate`, silently
    missing reviews on PRs with >100 comments. Post-fix the subprocess
    invocation includes `--paginate`, and gh concatenates each page's JSON
    array into a single merged array for top-level array responses.

    The fixtures here assert (1) the subprocess `args` contain `--paginate`
    and (2) reviewer counting still works correctly when the comments list
    grows past 100 — the scenario that pre-fix would have silently allowed
    merge.
    """

    @staticmethod
    def _comment(body: str) -> dict:
        return {"body": body, "user": {"login": "anyone"}}

    def test_subprocess_invocation_includes_paginate_flag(self):
        """gh api ... must be called with --paginate (#303 fix verification)."""
        captured_args: list[list[str]] = []

        def fake_run(args, capture_output, text, timeout):  # noqa: ARG001
            captured_args.append(list(args))
            result = mock.MagicMock()
            result.returncode = 0
            if args[0] == "gh" and args[1:3] == ["repo", "view"]:
                result.stdout = json.dumps({"owner": {"login": "noorinalabs"}, "name": "r"})
            else:
                result.stdout = json.dumps([])
            return result

        with mock.patch.object(hook.subprocess, "run", side_effect=fake_run):
            hook.check_comment_reviews(
                self.PR_NUMBER, self.BRANCH_AUTHOR, repo=self.REPO, content_ts=None
            )

        gh_api_calls = [a for a in captured_args if a[0] == "gh" and a[1] == "api"]
        self.assertEqual(len(gh_api_calls), 1, "exactly one gh api call expected")
        self.assertIn(
            "--paginate",
            gh_api_calls[0],
            "gh api invocation must include --paginate (#303)",
        )

    def test_paginated_response_with_101_comments_finds_review_at_position_101(self):
        """Review at comment index 100 (the 101st) MUST still register post-fix.

        Pre-fix: per_page=100 with no pagination → comment 101 invisible →
        validate_pr_review counts 1/2 distinct Approved reviewers and
        SILENTLY allows merge if only one Approved was in the first 100.
        Post-fix: --paginate fetches all pages; reviewer at position 101 is
        included; reviewer count is 2/2 and merge proceeds correctly.
        """
        # Build 100 non-review comments (Request/Reply) + 1 Approved at position 101.
        chatter = [
            self._comment(
                f"Requestor: Linh Pham\nRequestee: Reviewer{i}\nRequestOrReplied: Request"
            )
            for i in range(100)
        ]
        review_at_101 = [
            self._comment(
                "Requestor: Anya Kowalczyk\nRequestee: Linh Pham\n"
                "RequestOrReplied: Approved\nTechDebt: none"
            ),
            self._comment(
                "Requestor: Jelani Mwangi\nRequestee: Linh Pham\n"
                "RequestOrReplied: Approved\nTechDebt: none"
            ),
        ]
        comments = chatter + review_at_101
        self.assertEqual(len(comments), 102, "sanity: harness builds the right shape")
        result = self._run_with_fake_api(comments, self.BRANCH_AUTHOR, repo=self.REPO)
        self.assertEqual(
            len(result.reviewers),
            2,
            "post-#303: reviewers past position 100 must be counted",
        )
        self.assertIn("anya kowalczyk", result.reviewers)
        self.assertIn("jelani mwangi", result.reviewers)

    def test_paginated_response_with_250_comments_traverses_full_list(self):
        """3-page-equivalent traversal — the loop iterates the entire merged array."""
        chatter = [
            self._comment(f"Requestor: Author{i}\nRequestee: Linh Pham\nRequestOrReplied: Request")
            for i in range(248)
        ]
        reviews = [
            self._comment(
                "Requestor: Anya Kowalczyk\nRequestee: Linh Pham\n"
                "RequestOrReplied: Approved\nTechDebt: none"
            ),
            self._comment(
                "Requestor: Jelani Mwangi\nRequestee: Linh Pham\n"
                "RequestOrReplied: Approved\nTechDebt: none"
            ),
        ]
        comments = chatter + reviews
        self.assertEqual(len(comments), 250)
        result = self._run_with_fake_api(comments, self.BRANCH_AUTHOR, repo=self.REPO)
        self.assertEqual(len(result.reviewers), 2)


class LoadRosterNamesTests(unittest.TestCase):
    """Issue #498: `_load_roster_names()` returns ALL persona names from the
    local roster (not role-filtered like `load_charter_enforcer_names`).

    Tests against the parent repo's actual roster — Aino, Nadia, Wanjiku,
    Santiago must all be present; engineer roles too (sre, security, etc.).
    """

    def test_includes_standards_lead(self):
        names = hook._load_roster_names()
        self.assertIn("aino virtanen", names, f"missing standards lead: {names}")

    def test_includes_program_director(self):
        self.assertIn("nadia khoury", hook._load_roster_names())

    def test_includes_tpm(self):
        self.assertIn("wanjiku mwangi", hook._load_roster_names())

    def test_includes_release_coordinator(self):
        self.assertIn("santiago ferreira", hook._load_roster_names())

    def test_includes_engineer_roles(self):
        """Unlike `load_charter_enforcer_names`, engineer roles ARE included."""
        names = hook._load_roster_names()
        # sre_engineer_lucas → Lucas Ferreira; sre_engineer_aisha → Aisha Idrissi.
        self.assertIn("lucas ferreira", names)


class RosterValidationGateTests(_NoContentBindingHarness):
    """Issue #498: 2-reviewer gate must reject non-roster Requestor strings.

    Drives `check()` end-to-end with stubbed pr_data and a stubbed
    `check_comment_reviews` result; the only real-roster read is the parent
    repo's `_load_roster_names()` (via `_iter_roster_entries`).

    Repro target: PR #487 verdict comments posted under "Camila Restrepo" and
    "Imelda Santos" — neither in `.claude/team/roster/`. Pre-fix Hook 4
    counted both and merged. Post-fix both are filtered out.
    """

    @staticmethod
    def _input(command: str) -> dict:
        return {"tool_name": "Bash", "tool_input": {"command": command}}

    @staticmethod
    def _pr_data(**overrides) -> dict:
        base = {
            "author": "parametrization",
            "number": 487,
            "reviews": [],
            "headRefName": "S.Ferreira/0470-doc-sync",
            "labels": [],
        }
        base.update(overrides)
        return base

    def test_two_non_roster_requestors_blocked(self):
        """Regression: 2 non-roster Requestors must BLOCK (P3W11 #487 repro)."""
        review_result = hook.CommentReviewResult()
        review_result.reviewers = {"camila restrepo", "imelda santos"}
        with (
            mock.patch.object(hook, "get_pr_data", return_value=self._pr_data()),
            mock.patch.object(hook, "check_comment_reviews", return_value=review_result),
        ):
            result = hook.check(self._input("gh pr merge 487 --squash"))
        self.assertIsNotNone(result, "non-roster Requestors must not satisfy the 2-reviewer gate")
        assert result is not None
        self.assertEqual(result["decision"], "block")
        reason = result["reason"]
        self.assertIn("camila restrepo", reason.lower())
        self.assertIn("imelda santos", reason.lower())
        self.assertIn("Non-roster:", reason)
        self.assertIn("roster", reason.lower())

    def test_mixed_roster_and_non_roster_blocked(self):
        """1 roster + 1 non-roster → 1/2 (only the roster member counts)."""
        review_result = hook.CommentReviewResult()
        review_result.reviewers = {"aino virtanen", "imelda santos"}
        with (
            mock.patch.object(hook, "get_pr_data", return_value=self._pr_data()),
            mock.patch.object(hook, "check_comment_reviews", return_value=review_result),
        ):
            result = hook.check(self._input("gh pr merge 487 --squash"))
        self.assertIsNotNone(result, "1 roster + 1 non-roster must not pass 2/2")
        assert result is not None
        self.assertEqual(result["decision"], "block")
        reason = result["reason"]
        self.assertIn("imelda santos", reason.lower())
        self.assertNotIn("aino virtanen", reason.lower().split("non-roster:")[1].split("\n")[0])
        # Final count should reflect the filtered roster-only set.
        self.assertIn("1/2", reason)

    def test_two_roster_requestors_pass(self):
        """Regression baseline: 2 real roster members → allow (existing behavior)."""
        review_result = hook.CommentReviewResult()
        review_result.reviewers = {"aino virtanen", "nadia khoury"}
        with (
            mock.patch.object(hook, "get_pr_data", return_value=self._pr_data()),
            mock.patch.object(hook, "check_comment_reviews", return_value=review_result),
        ):
            result = hook.check(self._input("gh pr merge 487 --squash"))
        self.assertIsNone(result, "two distinct roster members must pass the 2-reviewer gate")

    def test_empty_roster_blocks_with_diagnostic(self):
        """Fail-closed: if the roster cannot be read, every Requestor is non-roster.

        Critical safe-direction default per `safety_direction_over_ux_friction`
        memory: an unreadable roster must NOT silently pass review gates that
        depend on it. The BLOCK message must surface the empty-roster
        condition diagnostically so an operator can fix the dir, not bypass.
        """
        review_result = hook.CommentReviewResult()
        review_result.reviewers = {"aino virtanen", "nadia khoury"}
        with (
            mock.patch.object(hook, "_load_roster_names", return_value=set()),
            mock.patch.object(hook, "get_pr_data", return_value=self._pr_data()),
            mock.patch.object(hook, "check_comment_reviews", return_value=review_result),
        ):
            result = hook.check(self._input("gh pr merge 487 --squash"))
        self.assertIsNotNone(result, "empty roster must fail closed")
        assert result is not None
        self.assertEqual(result["decision"], "block")
        reason = result["reason"]
        self.assertIn("empty", reason.lower())
        self.assertIn("could not be read", reason)


class StripCodeRegionsTests(unittest.TestCase):
    """Issue #511: `_strip_code_regions` removes fenced and inline code so the
    field extractor cannot capture reviewer prose-quotes of field syntax.

    Replacement char is space (not empty) so line indices stay stable for
    downstream trailer-block detection.
    """

    def test_strips_inline_backticks(self):
        result = hook._strip_code_regions("see `Requestor: foo` for context")
        self.assertNotIn("Requestor", result)
        self.assertEqual(len(result), len("see `Requestor: foo` for context"))

    def test_strips_fenced_triple_backtick_block(self):
        body = "before\n```\nRequestor: foo\n```\nafter"
        result = hook._strip_code_regions(body)
        self.assertNotIn("Requestor", result)
        self.assertIn("before", result)
        self.assertIn("after", result)

    def test_unterminated_inline_backtick_passes_through(self):
        """A lone backtick without a closing pair is treated as literal."""
        result = hook._strip_code_regions("opening ` and then Requestor: foo")
        self.assertIn("Requestor: foo", result)

    def test_unterminated_fenced_block_strips_rest(self):
        """An open ``` without a close conservatively eats the rest. Reviewer
        error mode (forgot close fence) → fail safe by not matching trailing
        chars as fields.
        """
        body = "intro ```\nRequestor: foo"
        result = hook._strip_code_regions(body)
        self.assertIn("intro", result)
        self.assertNotIn("Requestor", result)

    def test_multiline_inline_span_is_not_matched(self):
        """`...` with a newline in between is NOT an inline-code span per
        CommonMark — opening backtick passes through, line preserved.
        """
        body = "opening `\nRequestor: foo\n` closing"
        result = hook._strip_code_regions(body)
        self.assertIn("Requestor: foo", result)


class TrailerBlockSubstringTests(unittest.TestCase):
    """Issue #511: `_trailer_block_substring` returns text after the LAST
    bare-`---` separator line. No-separator → full body (back-compat).
    """

    def test_no_separator_returns_full_body(self):
        body = "Requestor: foo\nRequestee: bar"
        self.assertEqual(hook._trailer_block_substring(body), body)

    def test_one_separator_returns_post_only(self):
        body = "prose intro\n\n---\nRequestor: foo\nRequestee: bar"
        result = hook._trailer_block_substring(body)
        self.assertIn("Requestor", result)
        self.assertNotIn("prose intro", result)

    def test_multiple_separators_last_wins(self):
        body = (
            "intro\n\n---\nfake trailer with Requestor: WRONG\nmore prose\n"
            "---\nRequestor: CORRECT\nRequestee: target"
        )
        result = hook._trailer_block_substring(body)
        self.assertIn("CORRECT", result)
        self.assertNotIn("WRONG", result)

    def test_separator_must_be_on_own_line(self):
        body = "intro with --- embedded\nRequestor: foo"
        self.assertEqual(hook._trailer_block_substring(body), body)

    def test_separator_with_surrounding_whitespace_is_recognized(self):
        body = "intro\n  ---  \nRequestor: foo"
        result = hook._trailer_block_substring(body)
        self.assertIn("Requestor", result)
        self.assertNotIn("intro", result)


class ProseFalseMatchRegressionTests(_CheckCommentReviewsHarness):
    """Issue #511: prose-mention of charter fields above the trailer block
    MUST NOT be captured as the verdict. Three exact-shape regressions for
    the P3W11 batch-11 instances — pre-#511 each false-blocked at 1/2.
    """

    @staticmethod
    def _comment(body: str) -> dict:
        return {"body": body, "user": {"login": "anyone"}}

    def test_main_509_wanjiku_prose_above_trailer_ignored(self):
        """main#509 (Wanjiku) — prose described the bare-line trailer; pre-fix
        captured rest-of-prose-line as Requestor. Post-fix the trailer block
        (after `---`) is the only match scope.
        """
        body = (
            "PR body trailer convention is the literal bare-line block "
            "(Requestor / Requestee / RequestOrReplied: New / TechDebt: none) "
            "at the end of the body. Aino's #509 follows it correctly.\n"
            "\n"
            "---\n"
            "Requestor: Wanjiku Mwangi\n"
            "Requestee: Aino Virtanen\n"
            "RequestOrReplied: Approved\n"
            "TechDebt: none"
        )
        result = self._run_with_fake_api([self._comment(body)], self.BRANCH_AUTHOR, repo=self.REPO)
        self.assertEqual(result.reviewers, {"wanjiku mwangi"})
        self.assertEqual(result.reviews_missing_tech_debt, [])

    def test_deploy_337_lucas_prose_observation_ignored(self):
        """deploy#337 (Lucas) — soft observation about missing trailer block.
        Pre-fix the prose mention of `Requestor: / Requestee: / ...` itself
        captured garbage. Post-fix the actual trailer wins.
        """
        body = (
            "Soft observation: Aisha's PR body does not include the trailer "
            "structured-fields block (Requestor: / Requestee: / "
            "RequestOrReplied: New / TechDebt: none bare-line). Non-blocking — "
            "she can amend post-merge. LGTM on the conftest guard.\n"
            "\n"
            "---\n"
            "Requestor: Lucas Ferreira\n"
            "Requestee: Aisha Idrissi\n"
            "RequestOrReplied: Approved\n"
            "TechDebt: none"
        )
        result = self._run_with_fake_api([self._comment(body)], self.BRANCH_AUTHOR, repo=self.REPO)
        self.assertEqual(result.reviewers, {"lucas ferreira"})
        self.assertEqual(result.reviews_missing_tech_debt, [])

    def test_deploy_339_bereket_backtick_quote_ignored(self):
        """deploy#339 (Bereket) — verdict quoted PR body's `Requestor: (TBD…)`
        inside backticks. Pre-fix backtick contents were extracted as
        Requestor. Post-fix `_strip_code_regions` zeroes the backticks.
        """
        body = (
            "PR body uses `Requestor: (TBD — orchestrator will assign)` "
            "correctly — no reviewer name prediction, deferred per charter "
            "feedback_pr_number_placeholders.\n"
            "\n"
            "---\n"
            "Requestor: Bereket Tadesse\n"
            "Requestee: Lucas Ferreira\n"
            "RequestOrReplied: Approved\n"
            "TechDebt: none"
        )
        result = self._run_with_fake_api([self._comment(body)], self.BRANCH_AUTHOR, repo=self.REPO)
        self.assertEqual(result.reviewers, {"bereket tadesse"})
        self.assertEqual(result.reviews_missing_tech_debt, [])

    def test_legacy_no_separator_uses_last_match_fallback(self):
        """Back-compat: pre-#511 verdict comments without a `---` separator
        still work — the extractor falls back to the full body and uses
        last-match-wins. Prose above an end-of-body trailer is ignored
        because the last match is the real trailer.
        """
        body = (
            "Noting the body has Requestor: oldformat-prose-mention\n"
            "but the real trailer below uses canonical fields:\n"
            "Requestor: Wanjiku Mwangi\n"
            "Requestee: Aino Virtanen\n"
            "RequestOrReplied: Approved\n"
            "TechDebt: none"
        )
        result = self._run_with_fake_api([self._comment(body)], self.BRANCH_AUTHOR, repo=self.REPO)
        self.assertEqual(result.reviewers, {"wanjiku mwangi"})
        self.assertEqual(result.reviews_missing_tech_debt, [])

    def test_multiple_separators_only_last_trailer_matches(self):
        """If a verdict has multiple `---` (e.g., reviewer included an aside
        block with its own separator), only the LAST trailer is the source
        of truth — earlier blocks are ignored even if they look canonical.
        """
        body = (
            "intro prose\n"
            "\n"
            "---\n"
            "Requestor: WrongName Person\n"
            "RequestOrReplied: Approved\n"
            "TechDebt: none\n"
            "\n"
            "(this was an aside block, not the real verdict)\n"
            "\n"
            "---\n"
            "Requestor: Nadia Khoury\n"
            "Requestee: Aino Virtanen\n"
            "RequestOrReplied: Approved\n"
            "TechDebt: none"
        )
        result = self._run_with_fake_api([self._comment(body)], self.BRANCH_AUTHOR, repo=self.REPO)
        self.assertEqual(result.reviewers, {"nadia khoury"})

    def test_existing_canonical_trailer_still_works(self):
        """Regression baseline: a plain canonical verdict (no prose preamble,
        no separator, fields-only body) still parses correctly under the new
        scope discipline. Guards against over-zealous narrowing.
        """
        body = (
            "Requestor: Wanjiku Mwangi\n"
            "Requestee: Aino Virtanen\n"
            "RequestOrReplied: Approved\n"
            "TechDebt: none"
        )
        result = self._run_with_fake_api([self._comment(body)], self.BRANCH_AUTHOR, repo=self.REPO)
        self.assertEqual(result.reviewers, {"wanjiku mwangi"})


class ExtractRepoCallSiteTests(unittest.TestCase):
    """Smoke coverage that `validate_pr_review` exposes `extract_repo`
    (re-exported from the shared `_repo_flag_parse` helper) and that the
    canonical `gh pr merge --repo` happy path still resolves the same
    value.

    Comprehensive parser coverage (all 4 flag forms, tokenize / regex
    fallback, malformed cases) lives in `test_repo_flag_parse.py` alongside
    the helper. These tests pin the hook's import wiring so a future
    refactor that drops the re-export trips here, not at runtime. Mirrors
    `test_validate_review_comment_format.ExtractRepoCallSiteTests` from
    #513.
    """

    def test_present_returns_value(self):
        cmd = "gh pr merge 487 --repo noorinalabs/noorinalabs-deploy --squash"
        self.assertEqual(
            hook.extract_repo(cmd),
            "noorinalabs/noorinalabs-deploy",
        )

    def test_absent_returns_none(self):
        cmd = "gh pr merge 487 --squash"
        self.assertIsNone(hook.extract_repo(cmd))

    def test_equals_form_now_supported(self):
        """`--repo=value` form is supported post-#514 (was the documented
        latent #503-class gap in the original #509 implementation — sister
        consolidation #510 fixed it for two hooks via #513, #514 extends
        the fix to validate_pr_review for the gh-pr-merge code path)."""
        cmd = "gh pr merge 487 --repo=noorinalabs/noorinalabs-deploy --squash"
        self.assertEqual(
            hook.extract_repo(cmd),
            "noorinalabs/noorinalabs-deploy",
        )


class ChildRosterResolutionTests(_NoContentBindingHarness):
    """Issue #552: the roster the 2-reviewer gate validates against must be
    resolved relative to the PR's TARGET repo, not hardcoded to the parent.

    Pre-#552 `_ROSTER_DIR` was fixed to the parent repo's roster, so a child
    repo PR reviewed by legitimate child-repo personas (e.g. Anya Kowalczyk,
    Idris Yusuf) had those reviewers filtered out as "non-roster" — the gate
    blocked the merge or, after the merge was forced, defeated itself via
    `--admin`. In P3W13 this forced `--admin` on 14/37 child-repo PRs.

    The fix unions the parent roster with the named child repo's
    `.claude/team/roster/`. These tests build a hermetic on-disk parent+child
    roster tree under a tmp dir and monkeypatch `_ROSTER_DIR` /
    `_PARENT_REPO_ROOT` so they do not depend on the live sibling checkout.
    """

    PARENT_PERSONAS = {
        "standards_lead_aino": "Aino Virtanen",
        "program_director_nadia": "Nadia Khoury",
    }
    # Child personas — NOT present in the parent roster. `manager_*` is a
    # charter-enforcer prefix; `engineer_*` is a plain reviewer.
    CHILD_PERSONAS = {
        "engineer_anya": "Anya Kowalczyk",
        "engineer_idris": "Idris Yusuf",
        "manager_bereket": "Bereket Tadesse",
    }
    CHILD_REPO_NAME = "noorinalabs-isnad-graph"
    CHILD_REPO = f"noorinalabs/{CHILD_REPO_NAME}"

    def _write_roster(self, roster_dir: Path, personas: dict[str, str]) -> None:
        roster_dir.mkdir(parents=True, exist_ok=True)
        for slug, name in personas.items():
            (roster_dir / f"{slug}.md").write_text(
                f"# Roster Card\n\n## Identity\n- **Name:** {name}\n", encoding="utf-8"
            )

    def setUp(self) -> None:
        import tempfile

        # Chains to _NoContentBindingHarness.setUp, which pins T_content to None
        # so these roster-resolution tests do not shell out to a real commit
        # fetch (#950). Without the chain the patch never starts.
        super().setUp()

        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        # Parent repo root holds .claude/team/roster and the child repo sibling.
        parent_repo = root / "noorinalabs-main"
        self._parent_roster = parent_repo / ".claude" / "team" / "roster"
        self._write_roster(self._parent_roster, self.PARENT_PERSONAS)
        child_roster = parent_repo / self.CHILD_REPO_NAME / ".claude" / "team" / "roster"
        self._write_roster(child_roster, self.CHILD_PERSONAS)

        self._patchers = [
            mock.patch.object(hook, "_ROSTER_DIR", self._parent_roster),
            mock.patch.object(hook, "_PARENT_REPO_ROOT", parent_repo),
        ]
        for p in self._patchers:
            p.start()

    def tearDown(self) -> None:
        for p in self._patchers:
            p.stop()
        self._tmp.cleanup()

    # --- _child_roster_dir resolution -------------------------------------

    def test_child_roster_dir_resolves_for_child_repo(self):
        d = hook._child_roster_dir(self.CHILD_REPO)
        assert d is not None
        self.assertTrue(d.is_dir())
        self.assertEqual(d.parent.parent.parent.name, self.CHILD_REPO_NAME)

    def test_child_roster_dir_none_for_parent_repo(self):
        """`--repo noorinalabs/noorinalabs-main` → no distinct child dir."""
        self.assertIsNone(hook._child_roster_dir("noorinalabs/noorinalabs-main"))

    def test_child_roster_dir_none_for_absent_repo(self):
        self.assertIsNone(hook._child_roster_dir(None))
        self.assertIsNone(hook._child_roster_dir("not-a-repo-spec"))

    # --- union roster -----------------------------------------------------

    def test_load_roster_names_unions_parent_and_child(self):
        names = hook._load_roster_names(repo=self.CHILD_REPO)
        # Parent personas present.
        self.assertIn("aino virtanen", names)
        self.assertIn("nadia khoury", names)
        # Child personas unioned in (#552).
        self.assertIn("anya kowalczyk", names)
        self.assertIn("idris yusuf", names)

    def test_load_roster_names_parent_only_when_no_repo(self):
        """No `--repo` → parent-only resolution (back-compat for parent PRs)."""
        names = hook._load_roster_names(repo=None)
        self.assertIn("aino virtanen", names)
        self.assertNotIn("anya kowalczyk", names)

    def test_enforcer_names_union_includes_child_manager(self):
        """Child-repo `manager_*` is a charter enforcer for that repo's PRs."""
        enforcers = hook.load_charter_enforcer_names(repo=self.CHILD_REPO)
        self.assertIn("bereket tadesse", enforcers)
        # engineer_* personas are NOT enforcers.
        self.assertNotIn("anya kowalczyk", enforcers)

    # --- end-to-end check() behavior --------------------------------------

    @staticmethod
    def _input(command: str) -> dict:
        return {"tool_name": "Bash", "tool_input": {"command": command}}

    @staticmethod
    def _pr_data(**overrides) -> dict:
        base = {
            "author": "parametrization",
            "number": 935,
            "reviews": [],
            "headRefName": "A.Kowalczyk/0900-fix",
            "labels": [],
        }
        base.update(overrides)
        return base

    def test_child_pr_valid_child_reviewers_pass(self):
        """Two distinct child-repo reviewers on a child PR → allow (#552 core)."""
        review_result = hook.CommentReviewResult()
        review_result.reviewers = {"anya kowalczyk", "idris yusuf"}
        with (
            mock.patch.object(hook, "get_pr_data", return_value=self._pr_data()),
            mock.patch.object(hook, "check_comment_reviews", return_value=review_result),
        ):
            result = hook.check(self._input(f"gh pr merge 935 --repo {self.CHILD_REPO} --squash"))
        self.assertIsNone(result, "valid child-repo reviewers must pass the 2-reviewer gate")

    def test_child_pr_unknown_reviewer_blocks(self):
        """A reviewer in NEITHER parent nor child roster is still non-roster."""
        review_result = hook.CommentReviewResult()
        review_result.reviewers = {"anya kowalczyk", "phantom persona"}
        with (
            mock.patch.object(hook, "get_pr_data", return_value=self._pr_data()),
            mock.patch.object(hook, "check_comment_reviews", return_value=review_result),
        ):
            result = hook.check(self._input(f"gh pr merge 935 --repo {self.CHILD_REPO} --squash"))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["decision"], "block")
        self.assertIn("phantom persona", result["reason"].lower())
        self.assertIn("1/2", result["reason"])

    def test_parent_pr_still_passes_with_parent_reviewers(self):
        """Regression: parent-repo PR (no `--repo`) with 2 parent reviewers → allow."""
        review_result = hook.CommentReviewResult()
        review_result.reviewers = {"aino virtanen", "nadia khoury"}
        with (
            mock.patch.object(hook, "get_pr_data", return_value=self._pr_data()),
            mock.patch.object(hook, "check_comment_reviews", return_value=review_result),
        ):
            result = hook.check(self._input("gh pr merge 100 --squash"))
        self.assertIsNone(result, "parent-repo PR with 2 parent reviewers must still pass")

    def test_child_reviewer_does_not_count_on_parent_pr(self):
        """A child-only persona must NOT satisfy the gate on a parent PR (no leak)."""
        review_result = hook.CommentReviewResult()
        review_result.reviewers = {"aino virtanen", "anya kowalczyk"}
        with (
            mock.patch.object(hook, "get_pr_data", return_value=self._pr_data()),
            mock.patch.object(hook, "check_comment_reviews", return_value=review_result),
        ):
            result = hook.check(self._input("gh pr merge 100 --squash"))
        self.assertIsNotNone(result, "child persona must not count on a parent-repo PR")
        assert result is not None
        self.assertEqual(result["decision"], "block")
        self.assertIn("1/2", result["reason"])

    def test_missing_child_roster_dir_hard_blocks(self):
        """Safe direction: `--repo` names a child whose roster dir is absent →
        HARD BLOCK with diagnostic, never silent parent-only fallback
        (feedback_safety_direction_over_ux_friction).
        """
        review_result = hook.CommentReviewResult()
        review_result.reviewers = {"aino virtanen", "nadia khoury"}
        missing_repo = "noorinalabs/noorinalabs-does-not-exist"
        with (
            mock.patch.object(hook, "get_pr_data", return_value=self._pr_data()),
            mock.patch.object(hook, "check_comment_reviews", return_value=review_result),
        ):
            result = hook.check(self._input(f"gh pr merge 935 --repo {missing_repo} --squash"))
        self.assertIsNotNone(result, "unresolvable child roster must fail closed")
        assert result is not None
        self.assertEqual(result["decision"], "block")
        reason = result["reason"]
        self.assertIn("roster", reason.lower())
        self.assertIn("could not be resolved", reason)

    def test_child_pr_single_reviewer_exception_with_child_enforcer(self):
        """Single-Reviewer Exception honors a child-repo enforcer on a child PR.

        wave-bootstrap + sole reviewer is the child repo's manager (enforcer)
        → exception applies even though that persona is not in the parent roster.
        """
        review_result = hook.CommentReviewResult()
        review_result.reviewers = {"bereket tadesse"}
        with (
            mock.patch.object(
                hook,
                "get_pr_data",
                return_value=self._pr_data(labels=["wave-bootstrap", "tech-debt"]),
            ),
            mock.patch.object(hook, "check_comment_reviews", return_value=review_result),
        ):
            result = hook.check(self._input(f"gh pr merge 935 --repo {self.CHILD_REPO} --squash"))
        self.assertIsNone(
            result,
            "child-repo enforcer should satisfy the single-reviewer exception on a child PR",
        )


class ResolveRosterDirsTests(unittest.TestCase):
    """Issue #552: `_resolve_roster_dirs` returns parent + child dirs and raises
    `RosterResolutionError` when a named child roster dir is missing.
    """

    def test_parent_only_when_no_repo(self):
        dirs = hook._resolve_roster_dirs(None)
        self.assertEqual(dirs, [hook._ROSTER_DIR])

    def test_parent_only_when_repo_is_parent(self):
        dirs = hook._resolve_roster_dirs(f"noorinalabs/{hook._PARENT_REPO_ROOT.name}")
        self.assertEqual(dirs, [hook._ROSTER_DIR])

    def test_raises_when_child_roster_missing(self):
        with self.assertRaises(hook.RosterResolutionError):
            hook._resolve_roster_dirs("noorinalabs/noorinalabs-nonexistent-xyz")


class BatchLoopMergeDetectorTests(unittest.TestCase):
    """#567: `is_variable_pr_merge_in_loop` detects a `gh pr merge <var>` inside
    a for/while/until loop — the shape that fail-opens the 2-reviewer gate
    (memory `feedback_batch_loop_merge_evades_pr_review_hook`).

    Six parser classes per charter `hooks.md § 5a` segment-parser coverage:
    newline-separated loop, quoted-var arg, `${}`-form, literal-still-passes,
    while-loop, nested-loop. Plus the body-mention false-positive guard."""

    def test_for_loop_quoted_var_blocked(self):
        # parser-class: quoted-var
        self.assertTrue(
            hook.is_variable_pr_merge_in_loop(
                'for pr in 48 49 50; do gh pr merge "$pr" --repo o/r --merge; done'
            )
        )

    def test_for_loop_bare_var_blocked(self):
        self.assertTrue(
            hook.is_variable_pr_merge_in_loop("for pr in 48 49; do gh pr merge $pr --merge; done")
        )

    def test_brace_form_var_blocked(self):
        # parser-class: ${}-form
        self.assertTrue(
            hook.is_variable_pr_merge_in_loop('for pr in 1 2; do gh pr merge "${pr}" --merge; done')
        )

    def test_while_loop_blocked(self):
        # parser-class: while-loop
        self.assertTrue(
            hook.is_variable_pr_merge_in_loop("while read pr; do gh pr merge ${pr} --merge; done")
        )

    def test_until_loop_blocked(self):
        self.assertTrue(
            hook.is_variable_pr_merge_in_loop('until [ -z "$pr" ]; do gh pr merge $pr; done')
        )

    def test_newline_separated_loop_blocked(self):
        # parser-class: newline
        self.assertTrue(
            hook.is_variable_pr_merge_in_loop(
                'for pr in 48 49\ndo\n  gh pr merge "$pr" --merge\ndone'
            )
        )

    def test_nested_loop_blocked(self):
        # parser-class: nested-loop
        self.assertTrue(
            hook.is_variable_pr_merge_in_loop(
                'for r in a b; do\n  for pr in 1 2; do gh pr merge "$pr" --merge; done\ndone'
            )
        )

    def test_literal_merge_not_blocked(self):
        # parser-class: literal-still-passes — a literal PR number is untouched
        # by the guard (its number parses and the normal gate runs).
        self.assertFalse(hook.is_variable_pr_merge_in_loop("gh pr merge 54 --repo o/r --merge"))

    def test_literal_loop_not_blocked(self):
        # A loop iterating LITERAL merges (no shell variable) is not the
        # fail-open shape — each merge parses a literal number.
        self.assertFalse(
            hook.is_variable_pr_merge_in_loop("for n in 1; do gh pr merge 54 --merge; done")
        )

    def test_var_merge_outside_loop_not_blocked(self):
        # Out of scope for #567: a one-off variable merge with no loop.
        self.assertFalse(hook.is_variable_pr_merge_in_loop('gh pr merge "$PR" --merge'))

    def test_loop_text_in_body_not_blocked(self):
        # False-positive guard: a `--body` payload that merely MENTIONS the
        # loop-merge shape (quoted prose) must NOT be detected. The real
        # command is `gh pr create`, not a merge.
        self.assertFalse(
            hook.is_variable_pr_merge_in_loop(
                'gh pr create --body "for pr in 1; do gh pr merge $pr; done"'
            )
        )

    def test_non_merge_loop_not_blocked(self):
        # A loop that runs some other gh command is irrelevant to the gate.
        self.assertFalse(
            hook.is_variable_pr_merge_in_loop('for pr in 1 2; do gh pr view "$pr"; done')
        )

    def test_886_gh_run_rerun_loop_not_blocked(self):
        # #886 regression — the EXACT non-merge shape that false-blocked at the
        # P7W18 wrapup: a `gh run rerun "$ds_run" --failed` staleness recheck
        # inside a for-loop. No `gh pr merge` anywhere → must not match.
        self.assertFalse(
            hook.is_variable_pr_merge_in_loop(
                "for ds_run in $(gh run list --repo noorinalabs/noorinalabs-deploy "
                '--json databaseId --jq ".[].databaseId"); do '
                'gh run rerun "$ds_run" --repo noorinalabs/noorinalabs-deploy --failed; done'
            )
        )

    def test_886_nonloop_merge_with_unrelated_rerun_loop_not_blocked(self):
        # #886 regression (the actual false-positive mechanism): a multi-line
        # block pairing a NON-loop variable merge with a SEPARATE, unrelated
        # `gh run rerun` staleness loop. The merge is not inside the loop body,
        # so the gate does not fail-open and the guard must NOT fire. Before the
        # #886 narrowing this returned True (merge-var pattern + loop keywords
        # matched independently anywhere in the command).
        cmd = (
            'gh pr merge "$PR" --repo noorinalabs/noorinalabs-deploy --merge\n'
            'echo "wave merged"\n'
            "for ds_run in 11 12 13; do "
            'gh run rerun "$ds_run" --repo noorinalabs/noorinalabs-deploy --failed; done'
        )
        self.assertFalse(hook.is_variable_pr_merge_in_loop(cmd))

    def test_886_batch_loop_merge_still_blocked(self):
        # #886 must NOT weaken the real protection: a `gh pr merge "$pr"` that is
        # genuinely INSIDE the loop body (the fail-open evasion class from
        # `feedback_batch_loop_merge_evades`) is still detected.
        self.assertTrue(
            hook.is_variable_pr_merge_in_loop(
                'for pr in 48 49 50; do gh pr merge "$pr" --repo o/r --merge; done'
            )
        )

    # ---- #894 residual fail-open evasions ----

    def test_894_subshell_wrapped_merge_blocked(self):
        # Gap 1: a merge wrapped in a `( … )` subshell leaves the arg as `$pr)`.
        # The pre-#894 terminator lookahead `(?=\s|;|&|\||$)` omitted `)`, so the
        # merge verb never matched and the loop fail-opened. Now BLOCKED.
        self.assertTrue(
            hook.is_variable_pr_merge_in_loop("for pr in 1 2; do (gh pr merge $pr); done")
        )

    def test_894_subshell_wrapped_quoted_merge_blocked(self):
        # Gap 1 variant: subshell + quoted var arg.
        self.assertTrue(
            hook.is_variable_pr_merge_in_loop('for pr in 1 2; do (gh pr merge "$pr" --merge); done')
        )

    def test_894_subscripted_array_arg_blocked(self):
        # Gap 2: a subscripted `"${prs[$i]}"` arg failed the lone-simple-var
        # unwrap fullmatch and was stripped as opaque prose — the merge arg
        # vanished and the loop fail-opened. Now BLOCKED.
        self.assertTrue(
            hook.is_variable_pr_merge_in_loop('for i in 0 1; do gh pr merge "${prs[$i]}"; done')
        )

    def test_894_command_substitution_arg_blocked(self):
        # Gap 2 variant: a command-substitution `"$(cmd)"` arg, likewise stripped
        # pre-#894. Now BLOCKED.
        self.assertTrue(
            hook.is_variable_pr_merge_in_loop(
                'for i in 0 1; do gh pr merge "$(get_pr)" --merge; done'
            )
        )

    def test_894_command_substitution_arg_with_inner_space_blocked(self):
        # Gap 2 robustness: whitespace INSIDE the `$(…)` expansion must not make
        # the quoted run look like prose — it is still one shell-word argument.
        self.assertTrue(
            hook.is_variable_pr_merge_in_loop('for i in 0 1; do gh pr merge "$(get_pr $i)"; done')
        )

    def test_894_literal_merge_inside_loop_not_blocked(self):
        # Over-broadening guard: a bare-integer `gh pr merge 54` INSIDE a loop is
        # still NOT blocked — the literal parses and the normal gate runs.
        self.assertFalse(
            hook.is_variable_pr_merge_in_loop("for n in 1; do gh pr merge 54 --merge; done")
        )

    def test_894_nonliteral_merge_outside_loop_not_blocked(self):
        # #886 co-location preserved under the #894 broadening: a one-off
        # subscripted/compound merge OUTSIDE any loop, co-occurring with an
        # unrelated `gh run rerun` loop, does NOT fail-open and MUST NOT block.
        cmd = (
            'gh pr merge "${prs[0]}" --repo noorinalabs/noorinalabs-deploy --merge\n'
            "for r in 11 12 13; do "
            'gh run rerun "$r" --repo noorinalabs/noorinalabs-deploy --failed; done'
        )
        self.assertFalse(hook.is_variable_pr_merge_in_loop(cmd))

    def test_894_body_mention_of_compound_merge_not_blocked(self):
        # The #894 unwrap broadening must not re-open the prose-mention guard:
        # a `--body "…"` payload mentioning the compound-arg loop shape (it
        # carries whitespace OUTSIDE the expansion) is still stripped, not matched.
        self.assertFalse(
            hook.is_variable_pr_merge_in_loop(
                'gh pr create --body "for i in 0 1; do gh pr merge ${prs[$i]}; done"'
            )
        )

    # ---- #897 no-positional-argument (current-branch) in-loop evasion ----

    def test_897_no_arg_merge_in_checkout_loop_blocked(self):
        # The canonical #897 fail-open: a NO-positional-argument `gh pr merge`
        # (current-branch form) inside a `do … done` body that iterates
        # `git checkout $b`. With pr_number=None the gate resolves the cwd
        # branch's PR — the branch THIS iteration just checked out — sweeping
        # every branch's PR unverified. #896's non-literal-only matcher missed
        # it (no positional to match). Now BLOCKED.
        self.assertTrue(
            hook.is_variable_pr_merge_in_loop(
                "for b in branch-a branch-b; do git checkout $b && gh pr merge; done"
            )
        )

    def test_897_bare_merge_in_unrelated_loop_blocked(self):
        # A bare `gh pr merge` co-located inside ANY `do … done` body blocks —
        # co-location is the trigger, the absent positional is the fail-open.
        self.assertTrue(hook.is_variable_pr_merge_in_loop("for x in 1 2; do gh pr merge; done"))

    def test_897_flags_only_merge_in_loop_blocked(self):
        # Flags-only (no positional PR) inside a loop is still the no-literal
        # fail-open — `--merge` is not a PR number.
        self.assertTrue(
            hook.is_variable_pr_merge_in_loop("for b in a b; do gh pr merge --merge; done")
        )

    def test_897_bare_merge_outside_loop_not_blocked(self):
        # #886 guard MUST hold: a bare current-branch `gh pr merge` OUTSIDE any
        # loop is legitimate (it resolves its own current PR) and MUST PASS.
        self.assertFalse(hook.is_variable_pr_merge_in_loop("gh pr merge"))

    def test_897_bare_merge_with_flags_outside_loop_not_blocked(self):
        # #886 guard: a flags-only current-branch merge OUTSIDE any loop passes.
        self.assertFalse(hook.is_variable_pr_merge_in_loop("gh pr merge --merge --repo o/r"))

    def test_897_bare_merge_with_unrelated_rerun_loop_not_blocked(self):
        # #886 co-location under the #897 broadening: a one-off bare
        # current-branch merge co-occurring with an unrelated `gh run rerun`
        # loop is NOT inside the loop body, does not fail-open, and MUST NOT
        # block.
        cmd = (
            "gh pr merge --repo noorinalabs/noorinalabs-deploy --merge\n"
            "for r in 11 12 13; do "
            'gh run rerun "$r" --repo noorinalabs/noorinalabs-deploy --failed; done'
        )
        self.assertFalse(hook.is_variable_pr_merge_in_loop(cmd))


class BatchLoopMergeEndToEndTests(_NoContentBindingHarness):
    """#567 end-to-end: check() HARD BLOCKS a batch-loop variable merge, and a
    literal merge still flows to the normal 2-reviewer gate unchanged."""

    @staticmethod
    def _input(command: str) -> dict:
        return {"tool_name": "Bash", "tool_input": {"command": command}}

    def test_loop_var_merge_hard_blocked(self):
        # The guard returns BEFORE get_pr_data; patch it to a sentinel that
        # would NOT itself block, so a passing test proves the LOOP guard
        # (not the downstream gate) produced the block.
        with mock.patch.object(hook, "get_pr_data", return_value=None):
            result = hook.check(
                self._input('for pr in 48 49 50; do gh pr merge "$pr" --merge; done')
            )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.get("decision"), "block")
        self.assertIn("Batch-loop", result["reason"])
        self.assertIn("one pr per call", result["reason"].lower())

    def test_894_subscripted_loop_merge_hard_blocked(self):
        # #894 end-to-end: a subscripted in-loop merge reaches check() and HARD
        # BLOCKS. Patch get_pr_data so a pass proves the LOOP guard fired, not
        # the downstream gate.
        with mock.patch.object(hook, "get_pr_data", return_value=None):
            result = hook.check(
                self._input('for i in 0 1; do gh pr merge "${prs[$i]}" --merge; done')
            )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.get("decision"), "block")
        self.assertIn("Batch-loop", result["reason"])

    def test_894_subshell_loop_merge_hard_blocked(self):
        # #894 end-to-end: a subshell-wrapped in-loop merge HARD BLOCKS.
        with mock.patch.object(hook, "get_pr_data", return_value=None):
            result = hook.check(self._input("for pr in 1 2; do (gh pr merge $pr); done"))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.get("decision"), "block")

    def test_loop_var_merge_with_admin_still_overrides(self):
        # --admin is the emergency override and bypasses the loop guard too.
        result = hook.check(
            self._input('for pr in 1 2; do gh pr merge "$pr" --admin --merge; done')
        )
        self.assertIsNone(result, "--admin must bypass the batch-loop guard")

    def test_897_no_arg_loop_merge_hard_blocked(self):
        # #897 end-to-end: the no-positional-argument current-branch merge inside
        # a `git checkout $b` loop reaches check() and HARD BLOCKS. Patch
        # get_pr_data so a pass proves the LOOP guard fired (get_pr_data(None)
        # would otherwise resolve the cwd branch and fail-open).
        with mock.patch.object(hook, "get_pr_data", return_value=None):
            result = hook.check(
                self._input("for b in branch-a branch-b; do git checkout $b && gh pr merge; done")
            )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.get("decision"), "block")
        self.assertIn("Batch-loop", result["reason"])

    def test_897_bare_merge_outside_loop_reaches_gate(self):
        # #886 guard end-to-end: a bare current-branch `gh pr merge` OUTSIDE any
        # loop must NOT trip the loop guard — it flows to the normal 2-reviewer
        # gate, which with two distinct approvers ALLOWS. Proves the #897
        # broadening did not regress the legitimate current-branch merge.
        review_result = hook.CommentReviewResult()
        review_result.reviewers = {"aino virtanen", "nadia khoury"}
        pr_data = {
            "author": "parametrization",
            "number": 200,
            "reviews": [],
            "headRefName": "L.Pham/0002-fix",
            "labels": [],
        }
        with (
            mock.patch.object(hook, "get_pr_data", return_value=pr_data),
            mock.patch.object(hook, "check_comment_reviews", return_value=review_result),
        ):
            result = hook.check(self._input("gh pr merge --merge"))
        self.assertIsNone(result, "bare current-branch merge with 2 approvals must pass")

    def test_literal_merge_unaffected_by_loop_guard(self):
        # A bare literal merge is NOT loop-shaped; it reaches the normal gate.
        # With 2 distinct approved reviewers it allows (proves the guard did
        # not interfere with the literal path).
        review_result = hook.CommentReviewResult()
        review_result.reviewers = {"aino virtanen", "nadia khoury"}
        pr_data = {
            "author": "parametrization",
            "number": 100,
            "reviews": [],
            "headRefName": "L.Pham/0001-fix",
            "labels": [],
        }
        with (
            mock.patch.object(hook, "get_pr_data", return_value=pr_data),
            mock.patch.object(hook, "check_comment_reviews", return_value=review_result),
        ):
            result = hook.check(self._input("gh pr merge 100 --merge"))
        self.assertIsNone(result, "literal 2-approved merge must still pass the gate")


class StripQuotedRunsKeepVarArgsTests(unittest.TestCase):
    """#567 pure-parser: `_strip_quoted_runs_keep_var_args` drops quoted prose
    but unwraps a lone `"$var"` arg to its bare form."""

    def test_lone_double_quoted_var_unwrapped(self):
        out = hook._strip_quoted_runs_keep_var_args('gh pr merge "$pr" --merge')
        self.assertIn("$pr", out)
        self.assertNotIn('"', out)

    def test_brace_lone_var_unwrapped(self):
        out = hook._strip_quoted_runs_keep_var_args('gh pr merge "${pr}" --merge')
        self.assertIn("${pr}", out)

    def test_prose_double_quoted_run_dropped(self):
        out = hook._strip_quoted_runs_keep_var_args('gh pr create --body "do gh pr merge $pr"')
        # The body content (including its inner merge mention) is removed.
        self.assertNotIn("merge $pr", out)

    def test_single_quoted_run_dropped(self):
        out = hook._strip_quoted_runs_keep_var_args("echo 'for pr in 1; do gh pr merge $pr; done'")
        self.assertNotIn("gh pr merge", out)

    # ---- #894: broadened single-word-expansion unwrap ----

    def test_subscripted_array_arg_unwrapped(self):
        out = hook._strip_quoted_runs_keep_var_args('gh pr merge "${prs[$i]}" --merge')
        self.assertIn("${prs[$i]}", out)
        self.assertNotIn('"', out)

    def test_command_substitution_arg_unwrapped(self):
        out = hook._strip_quoted_runs_keep_var_args('gh pr merge "$(get_pr)" --merge')
        self.assertIn("$(get_pr)", out)

    def test_command_substitution_with_inner_space_unwrapped(self):
        # Whitespace inside the expansion does not make the run prose.
        out = hook._strip_quoted_runs_keep_var_args('gh pr merge "$(get_pr $i)" --merge')
        self.assertIn("$(get_pr $i)", out)

    def test_quoted_literal_word_not_unwrapped(self):
        # A non-expansion single word (e.g. a stray `"done"`) must NOT be
        # unwrapped — that would inject a spurious loop keyword into the view.
        out = hook._strip_quoted_runs_keep_var_args('gh pr comment --body "done"')
        self.assertNotIn("done", out)

    def test_prose_with_expansion_outside_dropped(self):
        # Whitespace OUTSIDE the expansion ⇒ prose ⇒ dropped wholesale.
        out = hook._strip_quoted_runs_keep_var_args('--body "merge ${prs[$i]} now"')
        self.assertNotIn("prs", out)


class StripExpansionsTests(unittest.TestCase):
    """#894 pure-parser: `_strip_expansions` removes balanced ${…}/$(…) groups so
    `_is_single_expansion_word` can tell a one-word arg from prose."""

    def test_brace_group_removed(self):
        self.assertEqual(hook._strip_expansions("${prs[$i]}").strip(), "")

    def test_paren_group_with_inner_space_removed(self):
        self.assertEqual(hook._strip_expansions("$(get_pr $i)").strip(), "")

    def test_nested_paren_group_removed(self):
        self.assertEqual(hook._strip_expansions("$(a $(b) c)").strip(), "")

    def test_bare_var_left_intact(self):
        # A bare `$pr` has no internal whitespace to hide, so it is not a group.
        self.assertEqual(hook._strip_expansions("$pr"), "$pr")

    def test_prose_whitespace_survives(self):
        self.assertTrue(any(c.isspace() for c in hook._strip_expansions("do merge $pr")))


class IsSingleExpansionWordTests(unittest.TestCase):
    """#894: predicate gating the double-quoted-run unwrap."""

    def test_bare_var_is_word(self):
        self.assertTrue(hook._is_single_expansion_word("$pr"))

    def test_subscripted_is_word(self):
        self.assertTrue(hook._is_single_expansion_word("${prs[$i]}"))

    def test_command_sub_with_space_is_word(self):
        self.assertTrue(hook._is_single_expansion_word("$(get_pr $i)"))

    def test_prose_is_not_word(self):
        self.assertFalse(hook._is_single_expansion_word("do gh pr merge $pr"))

    def test_literal_word_is_not_word(self):
        self.assertFalse(hook._is_single_expansion_word("done"))


# ---------------------------------------------------------------------------
# #950 — verdict staleness / content binding
#
# Hook 4 counted every `Approved` trailer without ever asking what commit it was
# cast against, so an approval of commit A still counted after the author
# force-pushed B, C, D. The tests below are built from the REAL timestamps of the
# three instances observed on 2026-07-11 (fetched from the GitHub API, not
# invented), plus the branch-update regression that keeps the fix from becoming a
# repo-wide outage.
# ---------------------------------------------------------------------------

# Real commit timeline of da#423 (`gh api .../pulls/423/commits`), the scrub PR
# whose first revision deleted Umm Kulthum bint Muhammad — the Prophet's daughter
# — and whose second still deleted 44 Companions including Abu Bakr al-Siddiq.
DA423_C1_SHA, DA423_C1_AT = "9afb8e09", "2026-07-11T03:16:25Z"  # deleted the Prophet's daughter
DA423_C2_SHA, DA423_C2_AT = "22d5942b", "2026-07-11T03:56:00Z"  # still deleted 44 Companions
DA423_C3_SHA, DA423_C3_AT = "674fa65a", "2026-07-11T04:09:36Z"  # the actual fix

# Real verdict-comment timestamps on da#423.
DA423_IVANA_AT = "2026-07-11T03:42:58Z"  # cast against 9afb8e09
DA423_SOFIA_APPROVED_AT = "2026-07-11T04:03:38Z"  # cast against 22d5942b

# Real ip#130 data: sole content commit, and the two verdicts that predate it.
IP130_SHA, IP130_AT = "05a57ae0", "2026-07-11T03:54:53Z"
IP130_TOMAS_AT = "2026-07-11T03:50:49Z"  # ChangesRequested — blocked a rewritten-away commit
IP130_FATIMA_AT = "2026-07-11T03:51:25Z"  # Approved — approved a commit that no longer exists


def _ts(value: str) -> datetime:
    """Parse an ISO-8601 `...Z` timestamp the way the hook does."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _verdict_comment(requestor: str, ror: str, created_at: str, tech_debt: str = "none") -> dict:
    """Build an issues-API comment payload carrying a charter verdict trailer.

    The trailer sits after a lone `---` separator because that is what the
    #511 trailer-block parser requires — a fixture that skipped it would parse to
    nothing and make every assertion below vacuously pass
    (`feedback_fixture_makes_guard_assertion_inert`).
    """
    return {
        "created_at": created_at,
        "body": (
            f"Reviewed the diff at the current head.\n\n"
            f"---\n"
            f"Requestor: {requestor}\n"
            f"Requestee: Kwesi Boateng\n"
            f"RequestOrReplied: {ror}\n"
            f"TechDebt: {tech_debt}\n"
        ),
    }


class VerdictFixtureSanityTests(unittest.TestCase):
    """The fixture must be able to produce a COUNTED approval, or nothing below proves anything.

    Every staleness test asserts an approval was NOT counted. If the fixture's
    comment shape simply failed to parse — wrong trailer format, missing `---` —
    those tests would pass for the wrong reason and the suite would certify a
    hook that counts nothing at all. This test pins the other end of the
    instrument: with NO content binding, the same fixture yields two counted
    reviewers (`feedback_silent_zero_is_not_a_measurement` — run the detector on
    both classes and require it to separate them).
    """

    def test_fixture_yields_counted_approvals_when_not_stale(self):
        comments = [
            _verdict_comment("Ivana Horvat", "Approved", DA423_IVANA_AT),
            _verdict_comment("Sofia Cardoso", "Approved", DA423_SOFIA_APPROVED_AT),
        ]
        result = _CheckCommentReviewsHarness._run_with_fake_api(comments, "boateng", repo="o/r")
        self.assertEqual(
            result.reviewers,
            {"ivana horvat", "sofia cardoso"},
            "fixture must parse into 2 counted reviewers when unbound — otherwise the "
            "staleness assertions below are vacuous",
        )
        self.assertEqual(result.stale_verdicts, [])


class ResolveReviewVerdictsSharedBoundaryTests(unittest.TestCase):
    """#1048: `resolve_review_verdicts` is the ONE shared entry point `check()`
    and `pr_review_state.compute_review_state` both call — neither re-derives
    the content-binding / comment-scan / roster-filter / union pipeline with
    its own argument list, which is the #1046 defect class.

    Mutation-sensitivity was manually confirmed while writing this refactor:
    temporarily stripping `content_ts=content_ts` from the feature-branch
    `check_comment_reviews` call inside `resolve_review_verdicts` turned 4
    tests in `.claude/lib/tests/test_pr_review_state.py::ContentStalenessTests`
    red immediately, because that class drives `compute_review_state` through
    the REAL `resolve_review_verdicts` over a faked `gh api` boundary. The
    test below is the equivalent DIRECT guard at the shared function itself.
    """

    REPO = "noorinalabs/noorinalabs-main"

    @staticmethod
    def _pr_data(head_ref="L.Ferreira/1040-x", author="parametrization", reviews=(), labels=()):
        return {
            "author": author,
            "number": 1040,
            "reviews": list(reviews),
            "headRefName": head_ref,
            "labels": list(labels),
        }

    def test_stale_comment_verdict_is_excluded_from_the_reviewer_set(self):
        """Direct kill-shot on the shared boundary (#950 x #1048): a stale
        Approved must not count toward `distinct_reviewers`, and must be
        recorded on `stale_verdicts_comment` so a caller (either check()'s
        block message or the driver's report) can name it. This would RED if
        `resolve_review_verdicts` ever stopped forwarding `content_ts` to
        `check_comment_reviews`.
        """
        stale_comment = {
            "body": (
                "Requestor: Lucas Ferreira\nRequestee: Someone Else\n"
                "RequestOrReplied: Approved\nTechDebt: none"
            ),
            "created_at": "2026-01-01T00:00:00Z",
        }

        def fake_run(args, capture_output, text, timeout):
            result = mock.MagicMock()
            result.returncode = 0
            if args[0] == "gh" and args[1:3] == ["repo", "view"]:
                result.stdout = json.dumps({"owner": {"login": "noorinalabs"}, "name": "r"})
            else:
                result.stdout = json.dumps([stale_comment])
            return result

        with (
            mock.patch.object(hook.subprocess, "run", side_effect=fake_run),
            mock.patch.object(
                hook,
                "get_latest_content_commit",
                return_value=("ac8bcfa", hook._parse_iso8601("2026-01-02T00:00:00Z")),
            ),
            mock.patch.object(hook, "_load_roster_names", return_value={"lucas ferreira"}),
        ):
            verdicts = hook.resolve_review_verdicts(self._pr_data(), repo=self.REPO)

        self.assertEqual(verdicts.distinct_reviewers, set())
        self.assertEqual(len(verdicts.stale_verdicts_comment), 1)
        self.assertEqual(verdicts.stale_verdicts_comment[0].reviewer, "Lucas Ferreira")
        self.assertEqual(verdicts.stale_verdicts_formal, [])
        self.assertEqual(verdicts.stale_verdicts, verdicts.stale_verdicts_comment)

    def test_check_delegates_to_resolve_review_verdicts_and_trusts_it(self):
        """`check()` must call the shared entry point and use its output
        DIRECTLY, rather than reassembling the pipeline inline — the concrete
        guard for #1048's acceptance criterion ('neither check() nor
        compute_review_state re-derives the verdict set'). A fake
        `ReviewVerdicts` with 2 distinct current reviewers and no missing
        TechDebt must ALLOW the merge without `check()` ever recomputing
        `distinct_reviewers` itself.
        """
        input_data = {
            "tool_name": "Bash",
            "tool_input": {"command": "gh pr merge 1040 --repo noorinalabs/noorinalabs-main"},
        }
        fake_verdicts = hook.ReviewVerdicts(
            number=1040,
            head_ref="L.Ferreira/1040-x",
            labels=[],
            branch_author_lastname="Ferreira",
            content_sha="ac8bcfa",
            content_ts=None,
            formal_reviewers=set(),
            comment_reviewers={"nino kavtaradze", "weronika zielinska"},
            non_roster_requestors=set(),
            roster_comment_reviewers={"nino kavtaradze", "weronika zielinska"},
            roster_names={"nino kavtaradze", "weronika zielinska"},
            distinct_reviewers={"nino kavtaradze", "weronika zielinska"},
            stale_verdicts_comment=[],
            stale_verdicts_formal=[],
            reviews_missing_tech_debt=[],
            tech_debt_issue_numbers=[],
            tech_debt_unparseable=[],
            wave_bootstrap_exception=False,
        )
        with (
            mock.patch.object(
                hook,
                "get_pr_data",
                return_value={
                    "author": "someone",
                    "number": 1040,
                    "reviews": [],
                    "headRefName": "L.Ferreira/1040-x",
                    "labels": [],
                },
            ),
            mock.patch.object(
                hook, "resolve_review_verdicts", return_value=fake_verdicts
            ) as mock_resolve,
        ):
            result = hook.check(input_data)

        mock_resolve.assert_called_once()
        self.assertIsNone(result, "2 distinct current reviewers must ALLOW the merge")

    def test_check_surfaces_unparseable_tech_debt_as_nonblocking_advisory(self):
        """main#1055 on the #1048 shape: `tech_debt_unparseable` carried on the
        shared `ReviewVerdicts` must reach `check()`'s advisory path — a merge
        with 2 distinct reviewers, no missing TechDebt, but an unparseable
        TechDebt value ALLOWS (never blocks) while surfacing a `systemMessage`.
        Proves the observability signal rides the new shared structure and does
        NOT flip the merge decision (it is emitted only after every blocking
        check has passed).
        """
        input_data = {
            "tool_name": "Bash",
            "tool_input": {"command": "gh pr merge 1040 --repo noorinalabs/noorinalabs-main"},
        }
        fake_verdicts = hook.ReviewVerdicts(
            number=1040,
            head_ref="L.Ferreira/1040-x",
            labels=[],
            branch_author_lastname="Ferreira",
            content_sha="ac8bcfa",
            content_ts=None,
            formal_reviewers=set(),
            comment_reviewers={"nino kavtaradze", "weronika zielinska"},
            non_roster_requestors=set(),
            roster_comment_reviewers={"nino kavtaradze", "weronika zielinska"},
            roster_names={"nino kavtaradze", "weronika zielinska"},
            distinct_reviewers={"nino kavtaradze", "weronika zielinska"},
            stale_verdicts_comment=[],
            stale_verdicts_formal=[],
            reviews_missing_tech_debt=[],
            tech_debt_issue_numbers=[],
            tech_debt_unparseable=[("Nino Kavtaradze", "filed later")],
            wave_bootstrap_exception=False,
        )
        with (
            mock.patch.object(
                hook,
                "get_pr_data",
                return_value={
                    "author": "someone",
                    "number": 1040,
                    "reviews": [],
                    "headRefName": "L.Ferreira/1040-x",
                    "labels": [],
                },
            ),
            mock.patch.object(hook, "resolve_review_verdicts", return_value=fake_verdicts),
        ):
            result = hook.check(input_data)

        self.assertIsNotNone(result, "an unparseable TechDebt value must surface a message")
        assert result is not None  # narrow type for the asserts below
        self.assertEqual(result["decision"], "allow", "the advisory must NOT block the merge")
        self.assertIn("filed later", result["systemMessage"])

    def test_check_translates_stale_verdict_error_into_a_block(self):
        """`CommentScanUndeterminedError` from the shared boundary must reach
        `check()`'s own #981 block message — proving the exception, not a
        re-derived `undetermined` flag, is what drives the block."""
        input_data = {
            "tool_name": "Bash",
            "tool_input": {"command": "gh pr merge 1040 --repo noorinalabs/noorinalabs-main"},
        }
        with (
            mock.patch.object(
                hook,
                "get_pr_data",
                return_value={
                    "author": "someone",
                    "number": 1040,
                    "reviews": [],
                    "headRefName": "L.Ferreira/1040-x",
                    "labels": [],
                },
            ),
            mock.patch.object(
                hook,
                "resolve_review_verdicts",
                side_effect=hook.CommentScanUndeterminedError("HTTP 403: Forbidden"),
            ),
        ):
            result = hook.check(input_data)

        self.assertIsNotNone(result)
        self.assertEqual(result["decision"], "block")
        self.assertIn("HTTP 403: Forbidden", result["reason"])


class StaleVerdictBindingTests(unittest.TestCase):
    """A verdict cast before the latest non-merge commit does not count (#950)."""

    @staticmethod
    def _run(comments: list[dict], content_ts: datetime | None, branch_author: str = "boateng"):
        return _CheckCommentReviewsHarness._run_with_fake_api_ts(
            comments, branch_author, repo="o/r", content_ts=content_ts
        )

    def test_da423_stale_approval_of_rewritten_revision_does_not_count(self):
        """The worst real case: at 22d5942b, Hook 4 saw TWO Approved trailers.

        Ivana's was cast at 03:42:58 against 9afb8e09 — the revision that deleted
        the Prophet's daughter — and 22d5942b landed at 03:56:00, rewriting it
        precisely because it was catastrophically wrong. The gate counted it
        anyway and would have called the PR merge-ready. It must now count only
        Sofia's.
        """
        comments = [
            _verdict_comment("Ivana Horvat", "Approved", DA423_IVANA_AT),
            _verdict_comment("Sofia Cardoso", "Approved", DA423_SOFIA_APPROVED_AT),
        ]
        result = self._run(comments, _ts(DA423_C2_AT))
        self.assertEqual(
            result.reviewers,
            {"sofia cardoso"},
            "Ivana's approval of the rewritten-away 9afb8e09 must NOT count at 22d5942b",
        )
        self.assertEqual([sv.reviewer for sv in result.stale_verdicts], ["Ivana Horvat"])

    def test_da423_at_final_head_even_the_later_approval_is_stale(self):
        """Live state: at 674fa65a (04:09:36), Sofia's 04:03:38 Approved is itself stale.

        Both approvals predate the branch's newest authored commit, so the PR has
        ZERO current approvals — the correct, and initially surprising, answer.
        """
        comments = [
            _verdict_comment("Ivana Horvat", "Approved", DA423_IVANA_AT),
            _verdict_comment("Sofia Cardoso", "Approved", DA423_SOFIA_APPROVED_AT),
        ]
        result = self._run(comments, _ts(DA423_C3_AT))
        self.assertEqual(result.reviewers, set())
        self.assertEqual(
            sorted(sv.reviewer for sv in result.stale_verdicts),
            ["Ivana Horvat", "Sofia Cardoso"],
        )

    def test_ip130_approval_of_vanished_commit_does_not_count(self):
        """ip#130: Fatima approved at 03:51:25 a commit replaced by 05a57ae0 at 03:54:53."""
        comments = [_verdict_comment("Fatima Bensalah", "Approved", IP130_FATIMA_AT)]
        result = self._run(comments, _ts(IP130_AT), branch_author="carvalho")
        self.assertEqual(result.reviewers, set())
        self.assertEqual([sv.reviewer for sv in result.stale_verdicts], ["Fatima Bensalah"])

    def test_ip130_stale_changes_requested_is_recorded(self):
        """ip#130: Tomás blocked a rewritten-away commit at 03:50:49.

        ChangesRequested never counted toward the threshold, but a stale one must
        still be RECORDED so the diagnostic can explain the PR's true state.
        """
        comments = [_verdict_comment("Tomás Carvalho", "ChangesRequested", IP130_TOMAS_AT)]
        result = self._run(comments, _ts(IP130_AT), branch_author="bensalah")
        self.assertEqual([sv.reviewer for sv in result.stale_verdicts], ["Tomás Carvalho"])

    def test_verdict_exactly_at_t_content_is_current(self):
        """The boundary is `<`, not `<=` — a verdict cast AT T_content counts.

        A reviewer who approves the instant the commit lands reviewed that commit.
        """
        comments = [_verdict_comment("Sofia Cardoso", "Approved", DA423_C2_AT)]
        result = self._run(comments, _ts(DA423_C2_AT))
        self.assertEqual(result.reviewers, {"sofia cardoso"})
        self.assertEqual(result.stale_verdicts, [])

    def test_stale_verdict_is_exempt_from_techdebt_requirement(self):
        """A verdict that carries no weight must not be able to block on TechDebt.

        Blocking the merge because a NOT-COUNTED verdict lacks an attestation
        line would be a false-block with a baffling message.
        """
        stale_no_td = {
            "created_at": DA423_IVANA_AT,
            "body": "---\nRequestor: Ivana Horvat\nRequestOrReplied: Approved\n",
        }
        result = self._run([stale_no_td], _ts(DA423_C2_AT))
        self.assertEqual(result.reviews_missing_tech_debt, [])
        self.assertEqual([sv.reviewer for sv in result.stale_verdicts], ["Ivana Horvat"])

    def test_verdict_with_unparseable_timestamp_is_stale_not_fresh(self):
        """Unknown freshness is not freshness — fail closed."""
        comments = [_verdict_comment("Sofia Cardoso", "Approved", "not-a-timestamp")]
        result = self._run(comments, _ts(DA423_C2_AT))
        self.assertEqual(result.reviewers, set())
        self.assertEqual([sv.reviewer for sv in result.stale_verdicts], ["Sofia Cardoso"])


class BranchUpdateRegressionTests(unittest.TestCase):
    """THE regression that makes #950 safe to ship: an approval SURVIVES a branch update.

    Updating a branch from `main` (`gh api -X PUT .../update-branch`, the routine
    BEHIND → CLEAN step before every merge) creates a MERGE commit that moves the
    head WITHOUT changing what the reviewer read. Binding verdicts to the head sha
    — the naive fix — would therefore invalidate every approval on every PR in the
    org at the moment of merge. Binding to the latest NON-MERGE commit does not.

    If these tests ever fail, the fix has become a repo-wide merge outage. Same
    lesson as `feedback_commit_author_gate_exclude_merges`: a gate over a commit
    range that does not exclude merge commits is corrupted by routine mechanics.
    """

    @staticmethod
    def _commit(sha: str, date: str, parents: int = 1) -> dict:
        return {
            "sha": sha,
            "parents": [{"sha": f"p{i}"} for i in range(parents)],
            "commit": {"committer": {"date": date}, "author": {"date": date}},
        }

    @staticmethod
    def _fake_commit_api(commits: list[dict]):
        def fake_run(args, capture_output, text, timeout):
            result = mock.MagicMock()
            result.returncode = 0
            result.stdout = json.dumps(commits)
            return result

        return fake_run

    def _latest(self, commits: list[dict]):
        with mock.patch.object(hook.subprocess, "run", side_effect=self._fake_commit_api(commits)):
            return hook.get_latest_content_commit(423, repo="noorinalabs/x")

    def test_merge_commit_from_main_does_not_advance_t_content(self):
        """The load-bearing assertion: a `main` merge lands AFTER the approval and
        T_content still points at the older authored commit, so the approval holds.
        """
        content_at = "2026-07-11T04:09:36Z"
        approval_at = "2026-07-11T04:20:00Z"
        branch_update_at = "2026-07-11T05:00:00Z"  # merge commit — newest object on the branch

        commits = [
            self._commit("674fa65a", content_at, parents=1),
            self._commit("ffffffff", branch_update_at, parents=2),  # Merge branch 'main' into ...
        ]
        latest = self._latest(commits)
        assert latest is not None
        sha, ts = latest
        self.assertEqual(sha, "674fa65a", "T_content must ignore the merge commit")
        self.assertEqual(ts, _ts(content_at))

        # And the end-to-end consequence: the approval cast before the branch
        # update — but after the content — still counts.
        self.assertLess(ts, _ts(approval_at), "approval must sit AFTER T_content")

    def test_two_approvals_survive_a_branch_update_end_to_end(self):
        """Full `check()` path: 2 approvals, then a `main` merge → merge still allowed.

        This is the org-outage guard. It drives `check()` exactly as a real
        `gh pr merge` would, with a merge commit as the newest object on the
        branch, and requires the hook to ALLOW.
        """
        content_at = "2026-07-11T04:09:36Z"
        approvals_at = "2026-07-11T04:20:00Z"
        commits = [
            self._commit("674fa65a", content_at, parents=1),
            self._commit("ffffffff", "2026-07-11T05:00:00Z", parents=2),
        ]
        pr_data = {
            "author": "parametrization",
            "number": 423,
            "reviews": [],
            "headRefName": "K.Boateng/0423-scrub",
            "labels": [],
        }
        comments = [
            _verdict_comment("Aino Virtanen", "Approved", approvals_at),
            _verdict_comment("Nadia Khoury", "Approved", approvals_at),
        ]

        def fake_run(args, capture_output, text, timeout):
            result = mock.MagicMock()
            result.returncode = 0
            joined = " ".join(args)
            if args[1:3] == ["repo", "view"]:
                result.stdout = json.dumps({"owner": {"login": "noorinalabs"}, "name": "r"})
            elif "commits?" in joined:
                result.stdout = json.dumps(commits)
            else:
                result.stdout = json.dumps(comments)
            return result

        with (
            mock.patch.object(hook, "get_pr_data", return_value=pr_data),
            mock.patch.object(hook.subprocess, "run", side_effect=fake_run),
        ):
            result = hook.check(
                {
                    "tool_name": "Bash",
                    "tool_input": {
                        "command": "gh pr merge 423 --merge",
                    },
                }
            )
        self.assertIsNone(
            result,
            "a branch update from main MUST NOT invalidate approvals — if this fails, "
            "every merge in the org is blocked",
        )

    def test_root_commit_zero_parents_is_content_not_a_merge(self):
        """0 parents is a root commit, not a merge — non-merge is `< 2` parents."""
        latest = self._latest([self._commit("aaaaaaaa", "2026-07-11T01:00:00Z", parents=0)])
        assert latest is not None
        self.assertEqual(latest[0], "aaaaaaaa")

    def test_all_merge_commits_yields_no_content_binding(self):
        """A branch with no authored commits binds nothing — nothing can be stale."""
        self.assertIsNone(
            self._latest([self._commit("ffffffff", "2026-07-11T05:00:00Z", parents=2)])
        )

    def test_t_content_is_the_max_not_the_last_listed(self):
        """Rebases can list commits out of date order; T_content is the newest."""
        commits = [
            self._commit("bbbbbbbb", "2026-07-11T06:00:00Z", parents=1),
            self._commit("cccccccc", "2026-07-11T02:00:00Z", parents=1),
        ]
        latest = self._latest(commits)
        assert latest is not None
        self.assertEqual(latest[0], "bbbbbbbb")

    def test_commit_fetch_is_paginated(self):
        """>100 commits must not silently truncate T_content (the #303 trap)."""
        captured: list[list[str]] = []

        def fake_run(args, capture_output, text, timeout):
            captured.append(args)
            result = mock.MagicMock()
            result.returncode = 0
            result.stdout = json.dumps([self._commit("aaaaaaaa", "2026-07-11T01:00:00Z")])
            return result

        with mock.patch.object(hook.subprocess, "run", side_effect=fake_run):
            hook.get_latest_content_commit(423, repo="noorinalabs/x")
        self.assertIn("--paginate", captured[0])
        self.assertTrue(any("pulls/423/commits" in a for a in captured[0]))


class CommitFetchFailClosedTests(unittest.TestCase):
    """A commit-fetch failure HARD BLOCKS; it never reverts to counting everything.

    `feedback_safety_direction_over_ux_friction`: when a hook cannot decide
    cleanly, hard-block with a diagnostic, never allow-with-log. A safety gate
    that degrades to permissive under error is not a gate — and reverting to the
    old counting behavior here would silently restore the exact fail-open #950
    exists to close.
    """

    @staticmethod
    def _failing_api(returncode: int = 1, stdout: str = "", stderr: str = "HTTP 502"):
        def fake_run(args, capture_output, text, timeout):
            result = mock.MagicMock()
            result.returncode = returncode
            result.stdout = stdout
            result.stderr = stderr
            return result

        return fake_run

    def test_nonzero_gh_api_raises_commit_fetch_error(self):
        with mock.patch.object(hook.subprocess, "run", side_effect=self._failing_api()):
            with self.assertRaises(hook.CommitFetchError):
                hook.get_latest_content_commit(423, repo="noorinalabs/x")

    def test_unparseable_json_raises_commit_fetch_error(self):
        with mock.patch.object(
            hook.subprocess, "run", side_effect=self._failing_api(returncode=0, stdout="<html>")
        ):
            with self.assertRaises(hook.CommitFetchError):
                hook.get_latest_content_commit(423, repo="noorinalabs/x")

    def test_non_merge_commit_without_timestamp_raises(self):
        """Silently skipping it would UNDERSTATE T_content and wave stale verdicts through."""
        commits = [{"sha": "aaaaaaaa", "parents": [{"sha": "p"}], "commit": {"committer": {}}}]

        def fake_run(args, capture_output, text, timeout):
            result = mock.MagicMock()
            result.returncode = 0
            result.stdout = json.dumps(commits)
            return result

        with mock.patch.object(hook.subprocess, "run", side_effect=fake_run):
            with self.assertRaises(hook.CommitFetchError):
                hook.get_latest_content_commit(423, repo="noorinalabs/x")

    def test_check_blocks_on_commit_fetch_error_with_two_valid_approvals(self):
        """THE fail-open test: a PR that WOULD merge (2 approvals) must BLOCK when
        the commit list cannot be fetched. If this returns None, the fix fails open.
        """
        review_result = hook.CommentReviewResult()
        review_result.reviewers = {"aino virtanen", "nadia khoury"}
        pr_data = {
            "author": "parametrization",
            "number": 423,
            "reviews": [],
            "headRefName": "K.Boateng/0423-scrub",
            "labels": [],
        }
        with (
            mock.patch.object(hook, "get_pr_data", return_value=pr_data),
            mock.patch.object(hook, "check_comment_reviews", return_value=review_result),
            mock.patch.object(
                hook,
                "get_latest_content_commit",
                side_effect=hook.CommitFetchError("HTTP 502"),
            ),
        ):
            result = hook.check(
                {
                    "tool_name": "Bash",
                    "tool_input": {"command": "gh pr merge 423 --merge"},
                }
            )
        self.assertIsNotNone(result, "commit-fetch failure MUST NOT fail open")
        assert result is not None
        self.assertEqual(result["decision"], "block")
        self.assertIn("could not fetch the PR's commit list", result["reason"])
        self.assertIn("HTTP 502", result["reason"])


class StaleVerdictDiagnosticTests(unittest.TestCase):
    """The diagnostic is as load-bearing as the block.

    An operator who sees `0/2 approvals` on a PR showing two green `Approved`
    comments will conclude the hook is broken and reach for `--admin`. The block
    message must name each stale verdict, its timestamp, and the commit that
    invalidated it — and must pre-empt the natural next fear, "did my branch
    update just nuke the approvals?"
    """

    def _block_reason(self) -> str:
        review_result = hook.CommentReviewResult()
        # A PARENT-roster persona: the #498 gate drops non-roster Requestors, and a
        # child-repo name here would make this 0/2 and mask what we mean to assert.
        review_result.reviewers = {"nadia khoury"}  # 1 current
        review_result.stale_verdicts = [
            hook.StaleVerdict("Ivana Horvat", "Approved", DA423_IVANA_AT),
        ]
        pr_data = {
            "author": "parametrization",
            "number": 423,
            "reviews": [],
            "headRefName": "K.Boateng/0423-scrub",
            "labels": [],
        }
        with (
            mock.patch.object(hook, "get_pr_data", return_value=pr_data),
            mock.patch.object(hook, "check_comment_reviews", return_value=review_result),
            mock.patch.object(
                hook,
                "get_latest_content_commit",
                return_value=(DA423_C3_SHA, _ts(DA423_C3_AT)),
            ),
        ):
            result = hook.check(
                {
                    "tool_name": "Bash",
                    "tool_input": {"command": "gh pr merge 423 --merge"},
                }
            )
        assert result is not None
        self.assertEqual(result["decision"], "block")
        return str(result["reason"])

    def test_diagnostic_names_the_stale_reviewer_and_timestamp(self):
        reason = self._block_reason()
        self.assertIn("Ivana Horvat", reason)
        self.assertIn(DA423_IVANA_AT, reason)
        self.assertIn("STALE", reason)

    def test_diagnostic_names_the_invalidating_commit(self):
        reason = self._block_reason()
        self.assertIn(DA423_C3_SHA, reason)

    def test_diagnostic_distinguishes_current_from_stale_count(self):
        reason = self._block_reason()
        self.assertIn("1/2 CURRENT approvals", reason)

    def test_diagnostic_preempts_the_branch_update_fear(self):
        """Operators WILL suspect update-branch. Say it isn't that, in the message."""
        reason = self._block_reason()
        self.assertIn("Branch updates from `main`", reason)
        self.assertIn("do NOT invalidate a verdict", reason)

    def test_diagnostic_states_the_remedy(self):
        reason = self._block_reason()
        self.assertIn("re-review at the current head", reason)


class FormalReviewStalenessTests(unittest.TestCase):
    """Formal GitHub reviews are bound to T_content too — else the fix has a hole.

    `gh pr review` is blocked org-wide by `block_gh_pr_review.py`, so these are
    rare; but leaving them unbound would be an open door straight through the
    staleness gate.
    """

    def _check(self, reviews: list[dict]):
        review_result = hook.CommentReviewResult()  # no comment verdicts
        pr_data = {
            "author": "parametrization",
            "number": 423,
            "reviews": reviews,
            "headRefName": "K.Boateng/0423-scrub",
            "labels": [],
        }
        with (
            mock.patch.object(hook, "get_pr_data", return_value=pr_data),
            mock.patch.object(hook, "check_comment_reviews", return_value=review_result),
            mock.patch.object(
                hook,
                "get_latest_content_commit",
                return_value=(DA423_C3_SHA, _ts(DA423_C3_AT)),
            ),
        ):
            return hook.check(
                {
                    "tool_name": "Bash",
                    "tool_input": {"command": "gh pr merge 423 --merge"},
                }
            )

    def test_stale_formal_reviews_do_not_count(self):
        reviews = [
            {"author": {"login": "reviewer-a"}, "state": "APPROVED", "submittedAt": DA423_IVANA_AT},
            {"author": {"login": "reviewer-b"}, "state": "APPROVED", "submittedAt": DA423_IVANA_AT},
        ]
        result = self._check(reviews)
        self.assertIsNotNone(result, "two STALE formal reviews must not satisfy the gate")
        assert result is not None
        self.assertEqual(result["decision"], "block")
        self.assertIn("0/2 CURRENT approvals", result["reason"])

    def test_current_formal_reviews_still_count(self):
        fresh = "2026-07-11T05:00:00Z"  # after 674fa65a
        reviews = [
            {"author": {"login": "reviewer-a"}, "state": "APPROVED", "submittedAt": fresh},
            {"author": {"login": "reviewer-b"}, "state": "APPROVED", "submittedAt": fresh},
        ]
        self.assertIsNone(self._check(reviews), "two CURRENT formal reviews must allow merge")

    def test_formal_review_without_timestamp_is_stale(self):
        reviews = [
            {"author": {"login": "reviewer-a"}, "state": "APPROVED"},
            {"author": {"login": "reviewer-b"}, "state": "APPROVED"},
        ]
        result = self._check(reviews)
        self.assertIsNotNone(result, "unknown freshness is not freshness")


class RepoArgumentDefectTests(unittest.TestCase):
    """Unit tests for the `repo_argument_defect` classifier (#981)."""

    def test_absent_repo_is_not_a_defect(self):
        """No `--repo` at all is legitimate — the hook resolves it from cwd."""
        self.assertIsNone(hook.repo_argument_defect(None))

    def test_literal_owner_name_is_not_a_defect(self):
        self.assertIsNone(hook.repo_argument_defect("noorinalabs/noorinalabs-main"))

    def test_host_qualified_literal_is_not_a_defect(self):
        """`gh` accepts `[HOST/]OWNER/REPO`; do not over-block the 3-segment form."""
        self.assertIsNone(hook.repo_argument_defect("github.com/noorinalabs/x"))

    def test_bare_variable_is_unexpanded(self):
        self.assertEqual(hook.repo_argument_defect("$DA"), hook.REPO_DEFECT_UNEXPANDED)

    def test_braced_variable_is_unexpanded(self):
        self.assertEqual(hook.repo_argument_defect("${DA}"), hook.REPO_DEFECT_UNEXPANDED)

    def test_command_substitution_is_unexpanded(self):
        self.assertEqual(hook.repo_argument_defect("$(get_repo)"), hook.REPO_DEFECT_UNEXPANDED)

    def test_partially_expanded_value_is_unexpanded(self):
        """`noorinalabs/$REPO` HAS a slash, so the shape test alone would pass it.

        This is the nastiest form: `_resolve_owner_repo` returns
        `("noorinalabs", "$REPO")` — a confidently-wrong "resolved" repo.
        """
        self.assertEqual(
            hook.repo_argument_defect("noorinalabs/$REPO"), hook.REPO_DEFECT_UNEXPANDED
        )

    def test_value_without_slash_is_malformed(self):
        self.assertEqual(hook.repo_argument_defect("justaname"), hook.REPO_DEFECT_MALFORMED)

    def test_empty_owner_or_name_is_malformed(self):
        self.assertEqual(hook.repo_argument_defect("/name"), hook.REPO_DEFECT_MALFORMED)
        self.assertEqual(hook.repo_argument_defect("owner/"), hook.REPO_DEFECT_MALFORMED)


class UnresolvableRepoFailsClosedTests(_NoContentBindingHarness):
    """#981: a merge whose target repo the gate cannot resolve must BLOCK.

    Pre-fix, `gh pr merge 451 -R $DA --merge` returned
    `{"decision": "allow", "systemMessage": "WARNING: Could not verify..."}`.
    The hook parses the command PRE-expansion, so `$DA` reached `gh pr view
    --repo '$DA'`, which exited non-zero, so `get_pr_data` returned None and the
    early `allow` fired — short-circuiting BEFORE `get_latest_content_commit`
    (so the #950 `CommitFetchError` hard-block never ran) and before
    `check_comment_reviews` was ever called. Four P9W25 da merges went through
    it with the 2-reviewer gate silently off.

    NOTE: the issue body attributes the fail-open to `_resolve_owner_repo`
    returning None inside `check_comment_reviews`. That path is NOT reachable on
    the merge path; the reachable one is `pr_data is None` in `check()`.

    Every test here patches `get_pr_data` to a sentinel that would ALLOW if it
    were reached, so a pass proves the new guard fired rather than some
    downstream check happening to block.
    """

    @staticmethod
    def _input(command: str) -> dict:
        return {"tool_name": "Bash", "tool_input": {"command": command}}

    @staticmethod
    def _approved_pr_data() -> dict:
        return {
            "author": "parametrization",
            "number": 451,
            "reviews": [],
            "headRefName": "L.Pham/0001-fix",
            "labels": [],
        }

    def _check_with_passing_downstream(self, command: str):
        """Run check() with a downstream state that would otherwise ALLOW.

        `_load_roster_names` is mocked to the two approvers: naming a child repo
        via `--repo` makes the #552 resolver look for that repo's roster on disk,
        which is absent in a parent-repo worktree. That is orthogonal
        pre-existing behavior, and leaving it live would make these tests block
        for the wrong reason — green for a defect they do not test.
        """
        review_result = hook.CommentReviewResult()
        review_result.reviewers = {"aino virtanen", "nadia khoury"}
        with (
            mock.patch.object(hook, "get_pr_data", return_value=self._approved_pr_data()),
            mock.patch.object(hook, "check_comment_reviews", return_value=review_result),
            mock.patch.object(
                hook, "_load_roster_names", return_value={"aino virtanen", "nadia khoury"}
            ),
        ):
            return hook.check(self._input(command))

    def test_unexpanded_repo_var_blocks(self):
        """THE #981 REGRESSION. Pre-fix this returned decision=allow."""
        result = self._check_with_passing_downstream(
            "gh pr merge 451 -R $DA --merge --delete-branch"
        )
        self.assertIsNotNone(result, "unresolvable repo must not fall through to allow")
        assert result is not None
        self.assertEqual(result["decision"], "block")

    def test_unexpanded_repo_var_never_allows_with_warning(self):
        """Pin the exact pre-fix shape so it cannot be reintroduced."""
        result = self._check_with_passing_downstream("gh pr merge 451 -R $DA --merge")
        assert result is not None
        self.assertNotEqual(result.get("decision"), "allow")
        self.assertNotIn("systemMessage", result)

    def test_braced_and_substitution_forms_block(self):
        for value in ("${DA}", "$(get_repo)", "noorinalabs/$REPO"):
            with self.subTest(repo=value):
                result = self._check_with_passing_downstream(
                    f"gh pr merge 451 --repo {value} --merge"
                )
                assert result is not None
                self.assertEqual(result["decision"], "block")

    def test_malformed_repo_blocks(self):
        result = self._check_with_passing_downstream("gh pr merge 451 --repo justaname --merge")
        assert result is not None
        self.assertEqual(result["decision"], "block")

    def test_attached_short_flag_unexpanded_var_blocks(self):
        """THE #1057 SECURITY ASSERTION — the composition with #1056's classifier.

        `gh pr merge 451 -R$DA` (ATTACHED short-flag, no space) must reach
        `decision: block` through `check()`. Pre-#1057 `extract_repo` returned
        None for the attached spelling, so `repo_argument_defect(None)` was None,
        the mocked-approved `get_pr_data` short-circuited to allow, and the merge
        bypassed the 2-reviewer gate — the #981 hole via the attached form. This
        is the sibling of `test_unexpanded_repo_var_blocks` (which pins the
        SPACED `-R $DA` shape) for the attached `-R$DA` shape."""
        result = self._check_with_passing_downstream("gh pr merge 451 -R$DA --merge")
        self.assertIsNotNone(result, "attached -R$DA must not fall through to allow")
        assert result is not None
        self.assertEqual(result["decision"], "block")
        self.assertIn("UNEXPANDED", result["reason"])

    def test_block_happens_before_any_network_call(self):
        """The guard is deterministic — it must not depend on a fetch failing.

        Pinning this keeps the block working when the API IS reachable (where a
        `--repo '$DA'` fetch might, in principle, not fail the same way).
        """
        with (
            mock.patch.object(hook, "get_pr_data") as get_mock,
            mock.patch.object(hook, "check_comment_reviews") as comments_mock,
        ):
            result = hook.check(self._input("gh pr merge 451 -R $DA --merge"))
        assert result is not None
        self.assertEqual(result["decision"], "block")
        get_mock.assert_not_called()
        comments_mock.assert_not_called()

    def test_admin_still_overrides(self):
        """`--admin` remains the emergency escape, as for every other guard."""
        with mock.patch.object(hook, "get_pr_data") as get_mock:
            result = hook.check(self._input("gh pr merge 451 -R $DA --admin --merge"))
        self.assertIsNone(result)
        get_mock.assert_not_called()

    # --- Requirement (b): the literal, properly-approved path is UNAFFECTED ---

    def test_literal_repo_on_approved_pr_still_allows(self):
        """A literal `--repo owner/name` on a 2-approver PR must still merge.

        This is the false-positive guard: a fail-closed change that also blocks
        legitimate merges has just moved the damage.
        """
        result = self._check_with_passing_downstream(
            "gh pr merge 451 --repo noorinalabs/noorinalabs-data-acquisition --merge"
        )
        self.assertIsNone(result, "literal repo + 2 approvers must still allow")

    def test_no_repo_flag_on_approved_pr_still_allows(self):
        result = self._check_with_passing_downstream("gh pr merge 451 --merge")
        self.assertIsNone(result, "absent --repo is legitimate cwd resolution")

    def test_attached_short_flag_literal_repo_resolves_and_threads_through(self):
        """A LEGITIMATE attached `-Rowner/name` must RESOLVE (not just fail
        closed): the parsed repo string is threaded into `get_pr_data`, and a
        2-approver PR still merges. Pre-#1057 the attached form parsed to None,
        so `get_pr_data` was called with `repo=None` (cwd resolution) — this
        test's `repo=` assertion bites that regression."""
        review_result = hook.CommentReviewResult()
        review_result.reviewers = {"aino virtanen", "nadia khoury"}
        with (
            mock.patch.object(
                hook, "get_pr_data", return_value=self._approved_pr_data()
            ) as get_mock,
            mock.patch.object(hook, "check_comment_reviews", return_value=review_result),
            mock.patch.object(
                hook, "_load_roster_names", return_value={"aino virtanen", "nadia khoury"}
            ),
        ):
            result = hook.check(
                self._input("gh pr merge 451 -Rnoorinalabs/noorinalabs-data-acquisition --merge")
            )
        self.assertIsNone(result, "attached literal repo + 2 approvers must still allow")
        _, kwargs = get_mock.call_args
        self.assertEqual(kwargs.get("repo"), "noorinalabs/noorinalabs-data-acquisition")

    # --- Requirement (c): the two failure kinds are diagnostically distinct ---

    def test_unresolvable_diagnostic_names_the_unexpanded_variable(self):
        result = self._check_with_passing_downstream("gh pr merge 451 -R $DA --merge")
        assert result is not None
        reason = result["reason"]
        self.assertIn("UNEXPANDED", reason)
        self.assertIn("$DA", reason)
        # The actionable fix is a literal repo...
        self.assertIn("--repo noorinalabs/noorinalabs-data-acquisition", reason)
        # ...NOT "retry", which would loop forever on a deterministic defect.
        self.assertNotIn("transient", reason)
        self.assertNotIn("Re-run the merge", reason)

    def test_malformed_diagnostic_names_the_shape_not_a_variable(self):
        result = self._check_with_passing_downstream("gh pr merge 451 --repo justaname --merge")
        assert result is not None
        reason = result["reason"]
        self.assertIn("OWNER/NAME", reason)
        self.assertIn("justaname", reason)
        self.assertNotIn("UNEXPANDED", reason)

    def test_generic_fetch_failure_blocks_with_a_distinct_diagnostic(self):
        """A well-formed repo + failed fetch is auth/network — a DIFFERENT fix.

        Pre-fix this branch returned `allow` too; it must now block, but with
        retry/auth guidance rather than the unexpanded-variable advice.
        """
        with mock.patch.object(hook, "get_pr_data", return_value=None):
            result = hook.check(
                self._input("gh pr merge 451 --repo noorinalabs/noorinalabs-main --merge")
            )
        self.assertIsNotNone(result, "unfetchable PR must not fall through to allow")
        assert result is not None
        self.assertEqual(result["decision"], "block")
        reason = result["reason"]
        self.assertIn("could not fetch the PR", reason)
        self.assertIn("gh auth status", reason)
        self.assertIn("Re-run the merge", reason)
        # Must NOT misdiagnose a network blip as a shell-quoting mistake.
        self.assertNotIn("UNEXPANDED", reason)

    def test_the_two_failure_kinds_do_not_share_a_message(self):
        unresolvable = self._check_with_passing_downstream("gh pr merge 451 -R $DA --merge")
        with mock.patch.object(hook, "get_pr_data", return_value=None):
            generic = hook.check(
                self._input("gh pr merge 451 --repo noorinalabs/noorinalabs-main --merge")
            )
        assert unresolvable is not None and generic is not None
        self.assertNotEqual(unresolvable["reason"], generic["reason"])


class IncompleteCommentScanFailsClosedTests(_NoContentBindingHarness):
    """#981 defense-in-depth: an unreadable comment thread != an unreviewed PR.

    Each early `return result` in `check_comment_reviews` used to hand back an
    empty `CommentReviewResult`, which is indistinguishable from "this PR has no
    charter-format approvals". Besides mis-stating the reviewer count, that
    silently skips the TechDebt attestation check. The scan now records WHY it
    stopped in `undetermined`, and `check()` hard-blocks on it.
    """

    @staticmethod
    def _input(command: str) -> dict:
        return {"tool_name": "Bash", "tool_input": {"command": command}}

    @staticmethod
    def _fake_run(returncode: int = 0, stdout: str = "[]", stderr: str = ""):
        def run(args, capture_output, text, timeout):
            result = mock.MagicMock()
            result.returncode = returncode
            result.stdout = stdout
            result.stderr = stderr
            return result

        return run

    def test_clean_scan_leaves_undetermined_empty(self):
        """The negative match — a successful empty scan must NOT be flagged."""
        with mock.patch.object(hook.subprocess, "run", side_effect=self._fake_run()):
            result = hook.check_comment_reviews(451, "pham", repo="noorinalabs/x", content_ts=None)
        self.assertEqual(result.undetermined, "")
        self.assertEqual(result.reviewers, set())

    def test_comments_api_failure_sets_undetermined(self):
        with mock.patch.object(
            hook.subprocess,
            "run",
            side_effect=self._fake_run(returncode=1, stdout="", stderr="HTTP 403: Forbidden"),
        ):
            result = hook.check_comment_reviews(451, "pham", repo="noorinalabs/x", content_ts=None)
        self.assertTrue(result.undetermined)
        self.assertIn("403", result.undetermined)

    def test_timeout_sets_undetermined(self):
        with mock.patch.object(
            hook.subprocess, "run", side_effect=hook.subprocess.TimeoutExpired("gh", 30)
        ):
            result = hook.check_comment_reviews(451, "pham", repo="noorinalabs/x", content_ts=None)
        self.assertIn("TimeoutExpired", result.undetermined)

    def test_unparseable_json_sets_undetermined(self):
        with mock.patch.object(
            hook.subprocess, "run", side_effect=self._fake_run(stdout="not json")
        ):
            result = hook.check_comment_reviews(451, "pham", repo="noorinalabs/x", content_ts=None)
        self.assertIn("JSONDecodeError", result.undetermined)

    def test_unresolvable_owner_repo_sets_undetermined(self):
        with mock.patch.object(hook, "_resolve_owner_repo", return_value=None):
            result = hook.check_comment_reviews(451, "pham", repo=None, content_ts=None)
        self.assertIn("could not resolve the target repository", result.undetermined)

    def test_check_hard_blocks_on_an_incomplete_scan(self):
        """Even with TWO formal approvers present, an incomplete scan blocks.

        Formal reviews alone would satisfy the threshold, so a pass here proves
        the block came from the incomplete scan and not from a count shortfall.
        """
        review_result = hook.CommentReviewResult()
        review_result.undetermined = "the PR comments API call failed: HTTP 403"
        pr_data = {
            "author": "parametrization",
            "number": 451,
            "reviews": [
                {"author": {"login": "reviewer-a"}, "state": "APPROVED"},
                {"author": {"login": "reviewer-b"}, "state": "APPROVED"},
            ],
            "headRefName": "L.Pham/0001-fix",
            "labels": [],
        }
        with (
            mock.patch.object(hook, "get_pr_data", return_value=pr_data),
            mock.patch.object(hook, "check_comment_reviews", return_value=review_result),
        ):
            result = hook.check(
                self._input("gh pr merge 451 --repo noorinalabs/noorinalabs-main --merge")
            )
        self.assertIsNotNone(result, "an unreadable comment thread must not read as reviewed")
        assert result is not None
        self.assertEqual(result["decision"], "block")
        self.assertIn("could not be read", result["reason"])
        self.assertIn("HTTP 403", result["reason"])

    def test_complete_scan_with_two_approvers_still_allows(self):
        """False-positive guard for the defense-in-depth change."""
        review_result = hook.CommentReviewResult()
        review_result.reviewers = {"aino virtanen", "nadia khoury"}
        pr_data = {
            "author": "parametrization",
            "number": 451,
            "reviews": [],
            "headRefName": "L.Pham/0001-fix",
            "labels": [],
        }
        with (
            mock.patch.object(hook, "get_pr_data", return_value=pr_data),
            mock.patch.object(hook, "check_comment_reviews", return_value=review_result),
            mock.patch.object(
                hook, "_load_roster_names", return_value={"aino virtanen", "nadia khoury"}
            ),
        ):
            result = hook.check(
                self._input("gh pr merge 451 --repo noorinalabs/noorinalabs-main --merge")
            )
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
