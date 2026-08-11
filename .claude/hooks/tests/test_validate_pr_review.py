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

import dataclasses
import json
import re
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

import _test_helpers  # noqa: E402,F401

_HOOKS_DIR = _test_helpers.HOOKS_DIR

import charter_trailer  # noqa: E402

# The oracle driver (`.claude/lib/`) is the THIRD surface that renders the
# comment-scan enum, alongside `check()`'s block message and its allow-path
# advisory (#1273). `CommentScanModeTotalityTests` below asserts all three agree
# on the same mode set, which is only possible from a module that can see both;
# this import exists for that class and for nothing else. The dependency runs
# test -> lib -> hook (pr_review_state already imports the gate), so it adds no
# cycle to the shipped code.
import pr_review_state as prs  # noqa: E402
import validate_pr_review as hook  # noqa: E402

# Every place check() interpolates the 2-reviewer count into a peer-review BLOCK.
# Used both to anchor a single site's expectation and to assert the WHOLE set of
# counts a reason carries (#1203).
_PEER_REVIEW_COUNT_RE = re.compile(r"has (\d+)/2 required peer reviews")

# Any ratio-shaped token at all, computed or literal. The collision this file's
# assertions kept losing to was a LITERAL matching this shape (#1203).
_ANY_RATIO_RE = re.compile(r"\b\d+/2\b")


def assert_peer_review_count(test: unittest.TestCase, reason: str, *, pr_display: str, count: int):
    """Assert the COMPUTED peer-review ratio inside a Hook 4 BLOCK reason.

    Never assert a bare ratio substring (`assertIn("1/2", reason)`) against
    `result["reason"]`. Hook 4's peer-review BLOCK reason is a ~60-line operator
    help document, so a bare `N/2` literal can match help prose rather than the
    interpolated count. That is the #1203 defect class: five assertions in this
    file were matching three `1/2 false-block` boilerplate lines and stayed green
    with the real ratio at 0/2 — degenerating to "some BLOCK happened", which the
    preceding `decision == "block"` assertion already established.

    Two checks, because the positive one alone is not sufficient:

      1. the full computed clause INCLUDING `pr_display` is present — so a
         mutation reporting the right count against the wrong PR still fails; and
      2. the counts present are EXACTLY `[count]` — a whole-set assertion, so a
         second, disagreeing computed ratio anywhere in the reason fails too, and
         the assertion cannot be satisfied by boilerplate however the help
         document is later reworded.

    Prefer this helper over hand-rolling the anchor at a new site: five hand-rolled
    sites are what produced this issue, and a sixth wrote itself the same way.
    """
    clause = f"BLOCKED: PR {pr_display} has {count}/2 required peer reviews"
    test.assertIn(
        clause,
        reason,
        f"expected the computed peer-review clause {clause!r} — assert the "
        f"interpolated sentence, never a bare ratio (#1203). Reason began: "
        f"{reason[:220]!r}",
    )
    test.assertEqual(
        _PEER_REVIEW_COUNT_RE.findall(reason),
        [str(count)],
        "a peer-review BLOCK reason must carry exactly one computed count",
    )


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
                # commit_author_identities is REQUIRED for the same fail-open
                # reason (#1210); `()` is the explicit "the ref already named the
                # author, no commit-derived identity applies" value these
                # pre-#1210 callers exercise.
                commit_author_identities=(),
            )

    @staticmethod
    def _run_with_fake_api_ts(
        comments_list: list[dict],
        branch_author: str,
        repo: str | None = None,
        content_ts: "datetime | None" = None,
        commit_author_identities: tuple = (),
    ):
        """As `_run_with_fake_api`, but binds verdicts to a T_content (#950).

        Kept as a separate entry point so the ~30 pre-#950 callers of
        `_run_with_fake_api` keep exercising the unbound path unchanged.

        `commit_author_identities` (#1210) defaults to `()` — the pre-#1210
        answer — so those callers stay unchanged; the #1210 tests pass it.
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
                commit_author_identities=commit_author_identities,
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
            hook.check_comment_reviews(
                451,
                "pham",
                repo="noorinalabs/x",
                commit_author_identities=(),
            )  # missing content_ts

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
            result = hook.check_comment_reviews(
                451,
                "pham",
                repo="noorinalabs/x",
                content_ts=None,
                commit_author_identities=(),
            )
        self.assertEqual(result.undetermined, "")

    def test_partition_formal_reviewers_still_accepts_explicit_none(self):
        formal, stale, near_window = hook.partition_formal_reviewers(
            [{"author": {"login": "reviewer-a"}, "state": "APPROVED"}],
            "author-login",
            None,
        )
        self.assertEqual(formal, {"reviewer-a"})
        self.assertEqual(stale, [])
        self.assertEqual(near_window, [], "content_ts=None means no near-window binding either")

    def test_check_comment_reviews_repo_is_keyword_only(self):
        """`repo` moved keyword-only alongside `content_ts` (#1050) — a
        positional third argument must now raise TypeError rather than
        silently binding to `repo`."""
        with self.assertRaises(TypeError):
            hook.check_comment_reviews(
                451,
                "pham",
                "noorinalabs/x",  # repo positional
                content_ts=None,
                commit_author_identities=(),
            )


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


class SharedBranchAuthorParsingTests(unittest.TestCase):
    """The branch-prefix parsers are SHARED, not merely equal (#1175).

    `extract_branch_author_lastname` used to be defined here AND in
    `validate_review_comment_format`. #179 taught this copy the dash separator;
    the other stayed slash-only until #1175 — four months of silent divergence
    that every value-equality test in both suites passed straight through,
    because each suite only ever asserted against its own copy.

    Object identity is the assertion that cannot be satisfied by a coincidence:
    it fails the instant a second definition exists, whatever that definition
    returns. `comment_scan_scope` and `resolve_review_verdicts` both read this
    binding, so a local re-declaration here silently owns the self-review
    exclusion for the whole merge gate.
    """

    def test_lastname_parser_is_the_charter_trailer_one(self):
        self.assertIs(
            hook.extract_branch_author_lastname,
            charter_trailer.extract_branch_author_lastname,
        )

    def test_initial_parser_is_the_charter_trailer_one(self):
        self.assertIs(
            hook.branch_author_first_initial,
            charter_trailer.branch_author_first_initial,
        )

    def test_both_hooks_share_one_binding(self):
        """The two hooks resolve to the SAME object — the #1175 invariant itself.

        Asserted from this suite as well as the format hook's, so deleting
        either file's copy still leaves the invariant pinned somewhere.
        """
        sys.path.insert(0, str(_HOOKS_DIR))
        import validate_review_comment_format as format_hook

        self.assertIs(
            hook.extract_branch_author_lastname,
            format_hook.extract_branch_author_lastname,
        )

    def test_comment_scan_scope_reads_the_shared_parser(self):
        """The merge gate's ref classification is downstream of the shared parser.

        Pins the wiring, not just the import: a dash ref must classify as
        author-excluded, which is only true if `comment_scan_scope` calls a
        parser that accepts dash.
        """
        self.assertEqual(
            hook.comment_scan_scope("A.Virtanen-1175-consolidation"),
            hook.COMMENT_SCAN_AUTHOR_EXCLUDED,
        )
        self.assertEqual(
            hook.comment_scan_scope("A.Virtanen/1175-consolidation"),
            hook.COMMENT_SCAN_AUTHOR_EXCLUDED,
        )
        # #1216: a wave branch now selects its own mode. Still the point of this
        # assertion — the parser must not see an author in it — but the negative
        # is now stated as "not AUTHOR_EXCLUDED" plus the specific mode, so the
        # test keeps pinning the shared-parser wiring rather than the mode name.
        self.assertEqual(
            hook.comment_scan_scope("deployments/phase-3/wave-29"),
            hook.COMMENT_SCAN_WAVE_INTEGRATION,
        )
        self.assertEqual(
            hook.comment_scan_scope("deployments/phase12/cleanup"),
            hook.COMMENT_SCAN_NO_BRANCH_AUTHOR,
        )


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
    `fetch_pr_commits` with real commit data instead.

    Patching the FETCH rather than the analysis (#1210) means the real
    `latest_content_commit` and `commit_author_identities` still run over the
    stub: an empty commit list yields no content binding AND no commit-derived
    branch author, which is exactly the pre-#950/pre-#1210 behaviour these
    tests intend.
    """

    def setUp(self) -> None:
        super().setUp()
        patcher = mock.patch.object(hook, "fetch_pr_commits", return_value=[])
        patcher.start()
        self.addCleanup(patcher.stop)


class CheckEndToEndTests(_NoContentBindingHarness):
    """End-to-end check() integration tests for #244 + #228 paths."""

    _input = staticmethod(_test_helpers.bash_input)

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
        assert_peer_review_count(self, result["reason"], pr_display="#100", count=1)

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
        # The merge is ALLOWED, which is what #294 is about. As of #1211 a
        # wave-merge ref — a no-branch-author ref by construction — carries the
        # scan-mode disclosure with that allow, so the outcome is an explicit
        # `{"decision": "allow", …}` rather than the bare `None` this test
        # originally used as its proxy for "allowed". Assert the decision, not
        # the proxy; asserting `is None` here would now be asserting the ABSENCE
        # of the #1211 disclosure, which is not this test's subject.
        assert result is not None, "wave-merge PR with 2 Approveds must not block"
        self.assertEqual(
            result["decision"],
            "allow",
            "wave-merge PR with 2 charter-format Approveds should allow merge",
        )
        self.assertIn("WITHOUT self-review exclusion", result["systemMessage"])
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
        assert_peer_review_count(self, result["reason"], pr_display="#100", count=1)


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
                self.PR_NUMBER,
                self.BRANCH_AUTHOR,
                repo=self.REPO,
                content_ts=None,
                commit_author_identities=(),
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
    "Imelda Santos" — at the time in no roster anywhere. Pre-fix Hook 4 counted
    both and merged. Post-fix both are filtered out.

    Those two original strings are NO LONGER usable as the fixture (#1179). The
    org has since onboarded real personas by exactly those names —
    `noorinalabs-isnad-ingest-platform/.claude/team/roster/data_lead_camila.md`
    and `data_engineer_imelda.md`, both carried in `.claude/team/roster.json`.
    Once #1179 unions the org manifest into `_load_roster_names`, they resolve,
    and asserting otherwise would assert that two genuine org personas cannot
    review — the #1179 bug in miniature. The SUBJECT of these tests is the
    non-roster filter, not those particular strings, so the fixture moves to
    strings that are definitionally not personas and the history stays here.
    """

    # Deliberately un-personable: no `+First.Last` identity can ever be minted
    # for these, so they cannot silently become real the way #487's names did.
    FABRICATED = ("phantom persona", "fabricated reviewer")

    _input = staticmethod(_test_helpers.bash_input)

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
        review_result.reviewers = set(self.FABRICATED)
        with (
            mock.patch.object(hook, "get_pr_data", return_value=self._pr_data()),
            mock.patch.object(hook, "check_comment_reviews", return_value=review_result),
        ):
            result = hook.check(self._input("gh pr merge 487 --squash"))
        self.assertIsNotNone(result, "non-roster Requestors must not satisfy the 2-reviewer gate")
        assert result is not None
        self.assertEqual(result["decision"], "block")
        reason = result["reason"]
        for fabricated in self.FABRICATED:
            self.assertIn(fabricated, reason.lower())
        self.assertIn("Non-roster:", reason)
        self.assertIn("roster", reason.lower())

    def test_mixed_roster_and_non_roster_blocked(self):
        """1 roster + 1 non-roster → 1/2 (only the roster member counts)."""
        review_result = hook.CommentReviewResult()
        review_result.reviewers = {"aino virtanen", self.FABRICATED[1]}
        with (
            mock.patch.object(hook, "get_pr_data", return_value=self._pr_data()),
            mock.patch.object(hook, "check_comment_reviews", return_value=review_result),
        ):
            result = hook.check(self._input("gh pr merge 487 --squash"))
        self.assertIsNotNone(result, "1 roster + 1 non-roster must not pass 2/2")
        assert result is not None
        self.assertEqual(result["decision"], "block")
        reason = result["reason"]
        self.assertIn(self.FABRICATED[1], reason.lower())
        self.assertNotIn("aino virtanen", reason.lower().split("non-roster:")[1].split("\n")[0])
        # Final count should reflect the filtered roster-only set. Anchored on the
        # computed sentence: a bare `assertIn("1/2", reason)` here matched the help
        # boilerplate and survived the real count dropping to 0/2 (#1203).
        assert_peer_review_count(self, reason, pr_display="#487", count=1)

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
        """An open ``` without a close, on its OWN LINE, conservatively eats
        the rest. Reviewer error mode (forgot close fence) → fail safe by
        not matching trailing chars as fields.

        UPDATED (main#1359 merge-gate review, Aino Virtanen — MF4): this
        fixture's opener used to be mid-line (`"intro ```\\n..."`), which is
        no longer treated as a fence at all — CommonMark does not recognize
        a mid-line marker as an opener either, and the old expectation
        ("eats the rest") depended on that not being enforced. A mid-line
        marker mentioned in ordinary prose (exactly what a reviewer writes
        when discussing fence syntax — the live incident that motivated this
        fix) must now pass through as literal text, not swallow everything
        after it. The body below moves the opener to the start of its own
        line so this fixture still exercises the "unterminated, eats the
        rest" behaviour it is named for; `FenceOpenerMustStartALineTests` in
        `test_charter_trailer.py` covers the mid-line-is-now-prose case this
        fixture used to (accidentally) encode.
        """
        body = "intro\n```\nRequestor: foo"
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

    _input = staticmethod(_test_helpers.bash_input)

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
        assert_peer_review_count(self, result["reason"], pr_display="#935", count=1)

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
        """A child-only persona must NOT satisfy the gate on a parent PR (no leak).

        This is the property #1199 names as the price of making the org-manifest
        union repo-agnostic, so it is the one site here whose looseness costs
        something. #1203 found its ratio assertion inert; the count is now
        anchored, and the REASON the count is 1 is asserted too — the child
        persona must be named as non-roster. Without that, the test could not
        distinguish "rejected as non-roster" (the property) from "dropped by some
        other mechanism" (not the property), and a leak paired with any second
        drop would read identically.
        """
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
        assert_peer_review_count(self, result["reason"], pr_display="#100", count=1)
        non_roster_line = result["reason"].lower().split("non-roster:")[1].split("\n")[0]
        self.assertIn("anya kowalczyk", non_roster_line)
        self.assertNotIn("aino virtanen", non_roster_line)

    def test_child_reviewer_does_not_count_on_parent_pr_off_their_own_branch(self):
        """The no-leak property with the branch-author confound removed (#1203).

        The sibling above inherits `_pr_data`'s head ref `A.Kowalczyk/0900-fix` —
        which names the very persona whose rejection it is asserting. That fixture
        cannot separate the roster filter from self-review exclusion by
        construction; it only passes today because `check_comment_reviews` (where
        the exclusion lives) is mocked out, i.e. the confound is masked by the
        mock rather than absent from the scenario. Re-pin the same property on a
        head ref belonging to somebody else, so the roster filter is the ONLY
        mechanism that can reject the child persona.
        """
        review_result = hook.CommentReviewResult()
        review_result.reviewers = {"aino virtanen", "anya kowalczyk"}
        with (
            mock.patch.object(
                hook,
                "get_pr_data",
                return_value=self._pr_data(headRefName="W.Zielinska/0901-unrelated"),
            ),
            mock.patch.object(hook, "check_comment_reviews", return_value=review_result),
        ):
            result = hook.check(self._input("gh pr merge 100 --squash"))
        self.assertIsNotNone(result, "child persona must not count on a parent-repo PR")
        assert result is not None
        self.assertEqual(result["decision"], "block")
        assert_peer_review_count(self, result["reason"], pr_display="#100", count=1)
        non_roster_line = result["reason"].lower().split("non-roster:")[1].split("\n")[0]
        self.assertIn("anya kowalczyk", non_roster_line)

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


class OrgManifestReviewerUnionTests(_NoContentBindingHarness):
    """Issue #1179: the merge-time reviewer set unions the org-union manifest.

    #1162/#1178 made `/wave-scope` § 12.5 and `/wave-kickoff` § 0b resolve
    REVIEW-class slots against `.claude/team/roster.json` (78 names), so a
    reviewer drawn from a THIRD child repo — charter-permitted by
    `charter/agents/spawn-discipline.md` § Child-Repo Implementer Rule step 5 —
    passes scope. Hook 4 did not: `_load_roster_names` unioned exactly
    parent-cards ∪ target-child-cards (#552), so that reviewer's `Approved` was
    filtered as non-roster (#498), the gate counted zero, and the only exit was
    `--admin` — a moderate feedback event per `charter/pull-requests.md`
    § Single-Reviewer Exception.

    Hermetic on-disk tree: a parent repo with two card personas, a target child
    repo with one, and a manifest carrying those plus a third-child persona, a
    tool identity (`Annunaki`) and a bare-principal identity (`Steven French`).
    """

    PARENT_PERSONAS = {
        "standards_lead_aino": "Aino Virtanen",
        "program_director_nadia": "Nadia Khoury",
    }
    # Charter-enforcer prefix (`manager_*`) so the enforcer path is exercised too.
    CHILD_PERSONAS = {"manager_bereket": "Bereket Tadesse"}
    CHILD_REPO_NAME = "noorinalabs-isnad-ingest-platform"
    CHILD_REPO = f"noorinalabs/{CHILD_REPO_NAME}"

    # Third-child personas: cards live in `noorinalabs-data-acquisition`, which is
    # neither the parent nor the merge target — so from this gate's point of view
    # they exist ONLY in the manifest. This is the live W28 assignment.
    THIRD_CHILD = {
        "Nikolaos Papadopoulos": "parametrization+Nikolaos.Papadopoulos@gmail.com",
        "Oyunbileg Batbayar": "parametrization+Oyunbileg.Batbayar@gmail.com",
    }
    # Non-persona manifest entries (#1181). `Annunaki` is the error monitor — it
    # posts real comments on real PRs, so it is the concrete risk of widening.
    NON_PERSONA = {
        "Annunaki": "parametrization+Annunaki@gmail.com",
        "Steven French": "parametrization@gmail.com",
    }

    _input = staticmethod(_test_helpers.bash_input)

    @staticmethod
    def _pr_data(**overrides) -> dict:
        base = {
            "author": "parametrization",
            "number": 42,
            "reviews": [],
            "headRefName": "N.Kavtaradze/1179-hook4-manifest-union",
            "labels": [],
        }
        base.update(overrides)
        return base

    def _write_roster(self, roster_dir: Path, personas: dict[str, str]) -> None:
        roster_dir.mkdir(parents=True, exist_ok=True)
        for slug, name in personas.items():
            (roster_dir / f"{slug}.md").write_text(
                f"# Roster Card\n\n## Identity\n- **Name:** {name}\n", encoding="utf-8"
            )

    def _write_manifest(self, payload: object) -> None:
        text = payload if isinstance(payload, str) else json.dumps(payload)
        self._manifest_path.write_text(text, encoding="utf-8")

    def setUp(self) -> None:
        import tempfile

        super().setUp()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        parent_repo = Path(self._tmp.name) / "noorinalabs-main"
        self._parent_roster = parent_repo / ".claude" / "team" / "roster"
        self._write_roster(self._parent_roster, self.PARENT_PERSONAS)
        self._write_roster(
            parent_repo / self.CHILD_REPO_NAME / ".claude" / "team" / "roster",
            self.CHILD_PERSONAS,
        )

        # `_load_org_manifest_names` derives the manifest path from `_ROSTER_DIR`
        # at CALL time, so patching `_ROSTER_DIR` keeps this hermetic — the live
        # 78-name manifest never leaks into these assertions.
        self._manifest_path = self._parent_roster.parent / "roster.json"
        self._write_manifest(
            {
                "Aino Virtanen": "parametrization+Aino.Virtanen@gmail.com",
                "Nadia Khoury": "parametrization+Nadia.Khoury@gmail.com",
                "Bereket Tadesse": "parametrization+Bereket.Tadesse@gmail.com",
                **self.THIRD_CHILD,
                **self.NON_PERSONA,
            }
        )

        for attr, value in (
            ("_ROSTER_DIR", self._parent_roster),
            ("_PARENT_REPO_ROOT", parent_repo),
        ):
            patcher = mock.patch.object(hook, attr, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    # --- acceptance 1: a third-child reviewer counts ----------------------

    def test_third_child_reviewer_resolves_via_manifest(self):
        names = hook._load_roster_names(repo=self.CHILD_REPO)
        self.assertIn("nikolaos papadopoulos", names)
        self.assertIn("oyunbileg batbayar", names)
        # Card-derived names are still there — the manifest widens, not replaces.
        self.assertIn("aino virtanen", names)
        self.assertIn("bereket tadesse", names)

    def test_third_child_reviewers_reach_the_two_reviewer_threshold(self):
        """MUTATION TARGET (#1179 acceptance 4).

        Both reviewers are manifest-only from this PR's point of view. Drop the
        `| _load_org_manifest_names()` union in `_load_roster_names` and this
        goes red: 0/2 approvals, BLOCK, `--admin` as the only exit.
        """
        review_result = hook.CommentReviewResult()
        review_result.reviewers = {"nikolaos papadopoulos", "oyunbileg batbayar"}
        with (
            mock.patch.object(hook, "get_pr_data", return_value=self._pr_data()),
            mock.patch.object(hook, "check_comment_reviews", return_value=review_result),
        ):
            result = hook.check(self._input(f"gh pr merge 42 --repo {self.CHILD_REPO} --squash"))
        self.assertIsNone(
            result,
            "two charter-permitted third-child reviewers must reach the 2-reviewer "
            "threshold at merge time, not just at scope time (#1179)",
        )

    def test_manifest_widens_parent_repo_prs_too(self):
        """The union is repo-agnostic, matching the scope-time twin.

        `validate_matrix_names.validate` computes `review_combined` for EVERY
        repo including the parent, and the charter permits a cross-team reviewer
        on any PR. Scoping the union to child PRs would leave the identical
        false block reachable on a parent-repo PR.
        """
        self.assertIn("nikolaos papadopoulos", hook._load_roster_names(repo=None))

    # --- acceptance 3: non-personas must not slip through -----------------

    def test_tool_identity_does_not_count_as_a_reviewer(self):
        self.assertNotIn("annunaki", hook._load_roster_names(repo=self.CHILD_REPO))

    def test_bare_principal_identity_does_not_count_as_a_reviewer(self):
        """`Steven French` → `parametrization@gmail.com`, no `+First.Last` tag."""
        self.assertNotIn("steven french", hook._load_roster_names(repo=self.CHILD_REPO))

    def test_tool_identity_cannot_supply_an_approval(self):
        """End-to-end: `Annunaki` + one real reviewer is 1/2, not 2/2.

        The ratio assertion MUST stay anchored to the computed sentence. This
        landed with #1199 as the one site that got it right while five siblings
        did not; #1203 then fixed those five and moved the anchor into
        `assert_peer_review_count` so there is a single definition to get right.

        Historical note, since the numbers below no longer reproduce: Hook 4's
        BLOCK help text used to embed the literal `1/2 false-block` three times
        unconditionally, so a bare `assertIn("1/2", reason)` matched boilerplate
        rather than the count — measured on this fixture, the real ratio was 1/2
        with 4 occurrences at head and 0/2 with 3 occurrences under a
        union-reverted mutant, and the bare form passed in BOTH. #1203 removed
        those literals from the help text (`BlockReasonRatioCollisionTests` now
        forbids their return), so the collision is gone at the source as well as
        at the call sites. Do not "simplify" this back to a bare substring.
        """
        review_result = hook.CommentReviewResult()
        review_result.reviewers = {"annunaki", "nikolaos papadopoulos"}
        with (
            mock.patch.object(hook, "get_pr_data", return_value=self._pr_data()),
            mock.patch.object(hook, "check_comment_reviews", return_value=review_result),
        ):
            result = hook.check(self._input(f"gh pr merge 42 --repo {self.CHILD_REPO} --squash"))
        self.assertIsNotNone(result, "a tool identity must not supply an approval")
        assert result is not None
        self.assertEqual(result["decision"], "block")
        assert_peer_review_count(self, result["reason"], pr_display="#42", count=1)

    def test_persona_filter_shape(self):
        """Direct coverage of the identity-shape rule, independent of the tree."""
        self.assertEqual(
            hook._load_org_manifest_names(self._manifest_path),
            {
                "aino virtanen",
                "nadia khoury",
                "bereket tadesse",
                "nikolaos papadopoulos",
                "oyunbileg batbayar",
            },
        )

    # --- acceptance 2: the enforcer boundary does not move ----------------

    def test_manifest_does_not_widen_charter_enforcer_names(self):
        """`load_charter_enforcer_names` stays card-only and role-filtered.

        It gates the Single-Reviewer Exception and filters on card FILENAME
        prefixes the flat manifest cannot supply, so a manifest hit must never
        qualify a sole reviewer for the exception.
        """
        enforcers = hook.load_charter_enforcer_names(repo=self.CHILD_REPO)
        self.assertIn("bereket tadesse", enforcers)  # child `manager_*` card
        self.assertNotIn("nikolaos papadopoulos", enforcers)
        self.assertNotIn("annunaki", enforcers)
        self.assertNotIn("steven french", enforcers)

    def test_manifest_persona_cannot_claim_the_single_reviewer_exception(self):
        """A manifest-only sole reviewer on a `wave-bootstrap` PR is still 1/2."""
        self.assertFalse(
            hook.is_single_reviewer_exception(
                ["wave-bootstrap"], {"nikolaos papadopoulos"}, repo=self.CHILD_REPO
            )
        )

    # --- degraded-mode invariants -----------------------------------------

    def test_manifest_never_substitutes_for_an_unreadable_card_tree(self):
        """Empty card set ⇒ empty result, so the caller still fails closed.

        `_load_roster_names`' documented contract is "empty ⇒ roster unreadable".
        A readable manifest beside an unreadable card tree must not quietly
        re-enable the gate. (`_ROSTER_DIR` moves; the manifest beside it stays.)
        """
        with mock.patch.object(hook, "_ROSTER_DIR", self._parent_roster.parent / "gone"):
            self.assertEqual(hook._load_roster_names(repo=None), set())

    def test_missing_child_roster_still_hard_blocks_with_a_manifest_present(self):
        """#552's safe direction survives: `_resolve_roster_dirs` raises first."""
        with self.assertRaises(hook.RosterResolutionError):
            hook._load_roster_names(repo="noorinalabs/noorinalabs-does-not-exist")

    def test_absent_manifest_fails_open_to_pre_1179_behaviour(self):
        self._manifest_path.unlink()
        self.assertEqual(
            hook._load_roster_names(repo=self.CHILD_REPO),
            {"aino virtanen", "nadia khoury", "bereket tadesse"},
        )

    def test_malformed_manifest_fails_open_to_pre_1179_behaviour(self):
        self._write_manifest("{not json")
        self.assertEqual(hook._load_org_manifest_names(self._manifest_path), set())

    def test_non_object_manifest_fails_open(self):
        self._write_manifest(["Nikolaos Papadopoulos"])
        self.assertEqual(hook._load_org_manifest_names(self._manifest_path), set())

    def test_non_string_entry_value_narrows_rather_than_guessing(self):
        """A future richer per-entry schema (#1181) re-blocks; it never admits."""
        self._write_manifest(
            {
                "Nikolaos Papadopoulos": {
                    "email": "parametrization+Nikolaos.Papadopoulos@gmail.com",
                    "persona": True,
                }
            }
        )
        self.assertEqual(hook._load_org_manifest_names(self._manifest_path), set())


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

    _input = staticmethod(_test_helpers.bash_input)

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


def _api_commit(
    sha: str,
    date: str,
    parents: int = 1,
    author_name: str = "",
    author_email: str = "",
) -> dict:
    """Build a `pulls/{n}/commits` payload entry.

    Shaped like the real API response — `parents` list, `commit.committer.date`,
    `commit.author.{name,email}` — so a fixture cannot pass by omitting the very
    field the code under test reads (`feedback_fixture_makes_guard_assertion_
    inert`). `author_name`/`author_email` default to empty, which is the honest
    "this fixture says nothing about who authored it" and yields no #1210
    identity.
    """
    return {
        "sha": sha,
        "parents": [{"sha": f"p{i}"} for i in range(parents)],
        "commit": {
            "committer": {"date": date},
            "author": {"date": date, "name": author_name, "email": author_email},
        },
    }


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
                "fetch_pr_commits",
                return_value=[_api_commit("ac8bcfa", "2026-01-02T00:00:00Z")],
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

    def test_check_surfaces_near_window_verdict_as_nonblocking_advisory(self):
        """#1272: a verdict CURRENT by #950 but cast within
        `NEAR_STALE_WINDOW_SECONDS` of T_content must reach `check()`'s
        advisory path exactly like the main#1055 unparseable-TechDebt case
        above — it counts toward the 2-reviewer threshold (never blocks) and
        is disclosed via a non-blocking `systemMessage` (mirrors #1211's
        allow-path disclosure pattern).
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
            near_window_verdicts_comment=[
                hook.NearWindowVerdict(
                    reviewer="Nino Kavtaradze",
                    verdict="Approved",
                    created_at="2026-08-03T03:32:52Z",
                    delta_seconds=76,
                )
            ],
            near_window_verdicts_formal=[],
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
            mock.patch.object(hook, "resolve_review_verdicts", return_value=fake_verdicts),
        ):
            result = hook.check(input_data)

        self.assertIsNotNone(result, "a near-window verdict must surface a message")
        assert result is not None  # narrow type for the asserts below
        self.assertEqual(result["decision"], "allow", "the advisory must NOT block the merge")
        self.assertIn("Nino Kavtaradze", result["systemMessage"])
        self.assertIn("76", result["systemMessage"])

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

    _commit = staticmethod(_api_commit)

    @staticmethod
    def _fake_commit_api(commits: list[dict]):
        def fake_run(args, capture_output, text, timeout):
            result = mock.MagicMock()
            result.returncode = 0
            result.stdout = json.dumps(commits)
            return result

        return fake_run

    def _latest(self, commits: list[dict]):
        """T_content over a commit list — the pure analysis, no fetch (#1210).

        `latest_content_commit` is now a pure function, so these assertions no
        longer need a subprocess mock at all. `test_commit_fetch_is_paginated`
        below still drives the real `fetch_pr_commits`, so the pagination
        guarantee stays pinned against the code that actually shells out.
        """
        return hook.latest_content_commit(commits)

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
            hook.fetch_pr_commits(423, repo="noorinalabs/x")
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
                hook.fetch_pr_commits(423, repo="noorinalabs/x")

    def test_unparseable_json_raises_commit_fetch_error(self):
        with mock.patch.object(
            hook.subprocess, "run", side_effect=self._failing_api(returncode=0, stdout="<html>")
        ):
            with self.assertRaises(hook.CommitFetchError):
                hook.fetch_pr_commits(423, repo="noorinalabs/x")

    def test_non_merge_commit_without_timestamp_raises(self):
        """Silently skipping it would UNDERSTATE T_content and wave stale verdicts through."""
        commits = [{"sha": "aaaaaaaa", "parents": [{"sha": "p"}], "commit": {"committer": {}}}]
        with self.assertRaises(hook.CommitFetchError):
            hook.latest_content_commit(commits)

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
                "fetch_pr_commits",
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
                "fetch_pr_commits",
                return_value=[_api_commit(DA423_C3_SHA, DA423_C3_AT)],
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
                "fetch_pr_commits",
                return_value=[_api_commit(DA423_C3_SHA, DA423_C3_AT)],
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

    _input = staticmethod(_test_helpers.bash_input)

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

    _input = staticmethod(_test_helpers.bash_input)

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
            result = hook.check_comment_reviews(
                451, "pham", repo="noorinalabs/x", content_ts=None, commit_author_identities=()
            )
        self.assertEqual(result.undetermined, "")
        self.assertEqual(result.reviewers, set())

    def test_comments_api_failure_sets_undetermined(self):
        with mock.patch.object(
            hook.subprocess,
            "run",
            side_effect=self._fake_run(returncode=1, stdout="", stderr="HTTP 403: Forbidden"),
        ):
            result = hook.check_comment_reviews(
                451, "pham", repo="noorinalabs/x", content_ts=None, commit_author_identities=()
            )
        self.assertTrue(result.undetermined)
        self.assertIn("403", result.undetermined)

    def test_timeout_sets_undetermined(self):
        with mock.patch.object(
            hook.subprocess, "run", side_effect=hook.subprocess.TimeoutExpired("gh", 30)
        ):
            result = hook.check_comment_reviews(
                451, "pham", repo="noorinalabs/x", content_ts=None, commit_author_identities=()
            )
        self.assertIn("TimeoutExpired", result.undetermined)

    def test_unparseable_json_sets_undetermined(self):
        with mock.patch.object(
            hook.subprocess, "run", side_effect=self._fake_run(stdout="not json")
        ):
            result = hook.check_comment_reviews(
                451, "pham", repo="noorinalabs/x", content_ts=None, commit_author_identities=()
            )
        self.assertIn("JSONDecodeError", result.undetermined)

    def test_unresolvable_owner_repo_sets_undetermined(self):
        with mock.patch.object(hook, "_resolve_owner_repo", return_value=None):
            result = hook.check_comment_reviews(
                451, "pham", repo=None, content_ts=None, commit_author_identities=()
            )
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


class SurnameCollisionSelfReviewTests(unittest.TestCase):
    """#1172: the #164 collision, reappearing in the self-review exclusion.

    #164 fixed the reviewer DEDUP key (full name, so Lucas and Santiago
    Ferreira count as two). The self-review EXCLUSION a few lines later kept
    comparing surnames, so on `L.Ferreira/1151-…` Santiago's Approved was
    dropped as "the author reviewing himself" and main#1156 sat at 1 of 2
    approvals — while the sibling hook, off the same wrong answer, refused to
    let him post the verdict at all.

    Both hooks now route through `charter_trailer.is_branch_author`, so who
    counts as whom cannot be fixed in one and not the other.

    Every "is admitted" assertion below is paired with the self-review that
    must still be refused. The exclusion is what stops a PR author from
    approving their own work; a fix that removes the false positive by
    removing the check would pass one half of this class and fail the other.
    """

    PR_NUMBER = 1156
    REPO = "noorinalabs/noorinalabs-main"
    BRANCH_LASTNAME = "Ferreira"
    BRANCH_INITIAL = "l"  # branch L.Ferreira/1151-cd-misroute-families

    @staticmethod
    def _verdict_comment(requestor: str, requestee: str, direction: str = "Approved") -> dict:
        return {
            "body": (
                f"Requestor: {requestor}\nRequestee: {requestee}\n"
                f"RequestOrReplied: {direction}\nTechDebt: None"
            ),
            "user": {"login": "anyone"},
        }

    def _reviewers(self, comments: list[dict], *, initial: str) -> set:
        def fake_run(args, capture_output, text, timeout):  # noqa: ARG001
            result = mock.MagicMock()
            result.returncode = 0
            result.stdout = json.dumps(comments)
            return result

        with mock.patch.object(hook.subprocess, "run", side_effect=fake_run):
            return set(
                hook.check_comment_reviews(
                    self.PR_NUMBER,
                    self.BRANCH_LASTNAME,
                    repo=self.REPO,
                    content_ts=None,
                    commit_author_identities=(),
                    branch_author_initial=initial,
                ).reviewers
            )

    def test_same_surname_reviewer_is_counted(self):
        """THE DEFECT: Santiago Ferreira's Approved on Lucas Ferreira's branch."""
        reviewers = self._reviewers(
            [self._verdict_comment("Santiago Ferreira", "Lucas Ferreira")],
            initial=self.BRANCH_INITIAL,
        )
        self.assertIn("santiago ferreira", reviewers)

    def test_branch_author_self_review_is_still_excluded(self):
        """THE TRUE POSITIVE: Lucas Ferreira approving his own branch."""
        reviewers = self._reviewers(
            [self._verdict_comment("Lucas Ferreira", "Aino Virtanen")],
            initial=self.BRANCH_INITIAL,
        )
        self.assertEqual(reviewers, set())

    def test_both_ferreiras_reach_the_two_reviewer_threshold(self):
        """The end the fix serves: #1156's second approval finally counts.

        The self-review is present in the same comment list, so this also
        pins that the exclusion is still doing its job while the colleague
        is admitted.
        """
        reviewers = self._reviewers(
            [
                self._verdict_comment("Aino Virtanen", "Lucas Ferreira"),
                self._verdict_comment("Santiago Ferreira", "Lucas Ferreira"),
                self._verdict_comment("Lucas Ferreira", "Aino Virtanen"),
            ],
            initial=self.BRANCH_INITIAL,
        )
        self.assertEqual(reviewers, {"aino virtanen", "santiago ferreira"})

    def test_changes_requested_from_same_surname_reviewer_is_tracked(self):
        """His ChangesRequested must enter the latest-verdict ledger too.

        `reviewers` holds only latest-verdict-Approved (#940), so a lone
        ChangesRequested is invisible either way and would not discriminate.
        Superseding it with an Approved does: pre-#1172 the colleague was
        dropped at the exclusion and never reached the ledger at all, so the
        set stayed empty.
        """
        reviewers = self._reviewers(
            [
                self._verdict_comment("Santiago Ferreira", "Lucas Ferreira", "Changes Requested"),
                self._verdict_comment("Santiago Ferreira", "Lucas Ferreira", "Approved"),
            ],
            initial=self.BRANCH_INITIAL,
        )
        self.assertEqual(reviewers, {"santiago ferreira"})

    def test_author_self_approval_after_changes_requested_is_still_excluded(self):
        """The same sequence from the author himself stays out of the ledger."""
        reviewers = self._reviewers(
            [
                self._verdict_comment("Lucas Ferreira", "Aino Virtanen", "Changes Requested"),
                self._verdict_comment("Lucas Ferreira", "Aino Virtanen", "Approved"),
            ],
            initial=self.BRANCH_INITIAL,
        )
        self.assertEqual(reviewers, set())

    def test_omitted_initial_degrades_to_the_stricter_surname_answer(self):
        """The `""` default must fail CLOSED, not open.

        Omitting `branch_author_initial` returns the pre-#1172 behaviour:
        the colleague is mistaken for the author and dropped, so the count
        goes DOWN and the merge blocks. Pinned so nobody "simplifies" the
        default into one that admits an uncounted reviewer instead.
        """
        reviewers = self._reviewers(
            [self._verdict_comment("Santiago Ferreira", "Lucas Ferreira")],
            initial="",
        )
        self.assertEqual(reviewers, set())

    def test_resolve_passes_the_branch_initial_through(self):
        """Wiring: the initial must reach the exclusion from the head ref.

        Without this the fix is inert in production — the unit above would
        pass while every real merge still used the `""` default.
        """
        captured: dict = {}

        def fake_check_comment_reviews(number, lastname, **kwargs):  # noqa: ARG001
            captured.update(kwargs)
            return hook.CommentReviewResult()

        pr_data = {
            "author": "parametrization",
            "number": self.PR_NUMBER,
            "reviews": [],
            "headRefName": "L.Ferreira/1151-cd-misroute-families",
            "labels": [],
        }
        with (
            mock.patch.object(
                hook, "check_comment_reviews", side_effect=fake_check_comment_reviews
            ),
            mock.patch.object(hook, "fetch_pr_commits", return_value=[]),
            mock.patch.object(hook, "_load_roster_names", return_value=set()),
        ):
            hook.resolve_review_verdicts(pr_data, repo=self.REPO)

        self.assertEqual(captured.get("branch_author_initial"), "l")


class CommentScanScopeTotalityTests(unittest.TestCase):
    """#1206: `comment_scan_scope` must return a SCANNING mode for every head ref.

    The defect was a dispatch that recognised exactly two head-ref shapes and
    fell through to no scan at all for everything else — so a `dependabot/**`
    PR carrying two correctly-formed, roster-valid, non-stale Approved verdicts
    reported `0/2 required — (none)`, blaming the reviewers for a scan that
    never ran (noorinalabs-deploy#691).

    Totality is the property that kills the whole defect class rather than the
    one observed shape: it is not enough to add `dependabot/**` to the list of
    recognised prefixes, because the next unrecognised shape fails the same way.
    """

    def test_persona_branch_selects_author_exclusion(self):
        """Positive control for the discriminator below: the persona shapes must
        actually resolve to the OTHER mode, or the totality assertions would be
        satisfied by a function that returned NO_BRANCH_AUTHOR unconditionally.
        """
        for ref in (
            "S.Ferreira/1189-wave-status-scoping",
            "A.Virtanen/1206-review-scan-nonpersona-headref",
            "A.Virtanen-0179-branch-regex-fix",  # dash separator, also charter-shaped
        ):
            with self.subTest(ref=ref):
                self.assertEqual(hook.comment_scan_scope(ref), hook.COMMENT_SCAN_AUTHOR_EXCLUDED)

    def test_non_persona_refs_select_the_no_branch_author_scan(self):
        """THE DEFECT, at the dispatch level. Every one of these returned "no
        scan" before #1206; each must now name a real scanning mode.

        `deployments/phase-10/wave-29` moved OUT of this list at #1216 — it
        selects `WAVE_INTEGRATION` now, asserted in
        `WaveBranchScanScopeTests` below. The remaining `deployments/**` entry is
        a REAL production ref (isnad-graph#603/#612) that is NOT a wave branch,
        and it is here to pin that the carve-out did not widen to the whole
        `deployments/` namespace.
        """
        for ref in (
            "dependabot/docker/integration-tests/fake_oauth/python-d3400aa",
            "deployments/phase12/cleanup",
            "feature/some-hand-made-branch",
            "nohashinthisref",  # no `/` at all
            "",  # headRefName absent from the API response
            "renovate/pytest-8.x",
            "1206-bare-issue-number-branch",
        ):
            with self.subTest(ref=ref):
                self.assertEqual(hook.comment_scan_scope(ref), hook.COMMENT_SCAN_NO_BRANCH_AUTHOR)

    def test_the_declared_author_arm_outranks_the_wave_arm(self):
        """#1216 precedence, pinned where it is otherwise UNFALSIFIABLE.

        No real ref can satisfy both shapes — `_BRANCH_AUTHOR_PREFIX_RE` anchors
        at the start and needs `{letter}.`, which `deployments/…` cannot supply —
        so swapping the two `if`s in `comment_scan_scope` is a no-op against
        every input and SURVIVED mutation M7 with the whole suite green.

        A docstring saying "order matters" that no test can falsify is the
        #1215 shape (an anti-vacuity claim that is itself vacuous). So the
        precedence is pinned against the predicate rather than against a ref:
        with `is_wave_branch` forced True, a ref that names its author must
        STILL keep its exclusion. This is not a hypothetical guard — it is the
        exact property that starts mattering the moment anyone widens
        `is_wave_branch`, which is the likeliest future edit to this code.
        """
        with mock.patch.object(hook, "is_wave_branch", return_value=True):
            self.assertEqual(
                hook.comment_scan_scope("A.Virtanen/1216-x"),
                hook.COMMENT_SCAN_AUTHOR_EXCLUDED,
            )
            self.assertEqual(
                hook.comment_scan_scope("A.Virtanen-1216-x"),
                hook.COMMENT_SCAN_AUTHOR_EXCLUDED,
            )
            # Anti-vacuity: the patch must actually be reaching the function, or
            # the assertions above would pass against an unpatched call.
            self.assertEqual(
                hook.comment_scan_scope("feature/hand-made"),
                hook.COMMENT_SCAN_WAVE_INTEGRATION,
            )

    def test_no_head_ref_shape_ever_yields_not_run(self):
        """The invariant itself, stated once: NOT_RUN is not a reachable scope.

        Kept separate from the case list above so the property survives someone
        later adding a third scanning mode — a new mode would keep this green
        and correctly fail only the specific-mode assertions it changes.
        """
        for ref in (
            "",
            "/",
            "a",
            "A.Virtanen/1206-x",
            "dependabot/npm_and_yarn/x-1.2.3",
            "deployments/phase-10/wave-29",
            "..",
            "x" * 300,
        ):
            with self.subTest(ref=ref):
                self.assertNotEqual(hook.comment_scan_scope(ref), hook.COMMENT_SCAN_NOT_RUN)


class _ResolveOverFakeCommentsHarness(unittest.TestCase):
    """Drives the REAL `resolve_review_verdicts` over a faked `gh api` boundary.

    Deliberately does NOT mock `check_comment_reviews`: the #1206 defect lived
    in the resolver's DISPATCH to that function, so a test that stubs the callee
    still exercises the dispatch, but a test that stubs the dispatch would prove
    nothing at all.
    """

    REPO = "noorinalabs/noorinalabs-main"
    ROSTER = {"lucas ferreira", "nino kavtaradze", "aino virtanen", "santiago ferreira"}

    @staticmethod
    def _verdict(requestor: str, requestee: str = "Someone Else", direction: str = "Approved"):
        return {
            "body": (
                f"Requestor: {requestor}\nRequestee: {requestee}\n"
                f"RequestOrReplied: {direction}\nTechDebt: none"
            ),
            "created_at": "2026-07-20T00:00:00Z",
        }

    @staticmethod
    def _pr_data(head_ref: str, *, author="parametrization", reviews=(), labels=()):
        return {
            "author": author,
            "number": 691,
            "reviews": list(reviews),
            "headRefName": head_ref,
            "labels": list(labels),
        }

    # Default commit fixture: one non-merge commit whose author fields are
    # EMPTY, so it yields no #1210 identity. That keeps every pre-#1210 test in
    # this harness exercising the "ref is the only author source" path; a test
    # that wants commit-derived identity passes `commits=` explicitly.
    DEFAULT_COMMITS = [_api_commit("837c272a", "2026-07-15T19:13:59Z")]

    def _resolve(self, head_ref: str, comments: list[dict], *, roster=None, commits=None):
        def fake_run(args, capture_output, text, timeout):  # noqa: ARG001
            result = mock.MagicMock()
            result.returncode = 0
            if args[0] == "gh" and args[1:3] == ["repo", "view"]:
                result.stdout = json.dumps({"owner": {"login": "noorinalabs"}, "name": "r"})
            else:
                result.stdout = json.dumps(comments)
            return result

        with (
            mock.patch.object(hook.subprocess, "run", side_effect=fake_run),
            mock.patch.object(
                hook,
                "fetch_pr_commits",
                # T_content sits BEFORE the fixture comments, so nothing is stale
                # and a shortfall can only come from the scan, not from staleness.
                return_value=self.DEFAULT_COMMITS if commits is None else commits,
            ),
            mock.patch.object(
                hook,
                "_load_roster_names",
                return_value=set(self.ROSTER if roster is None else roster),
            ),
        ):
            return hook.resolve_review_verdicts(self._pr_data(head_ref), repo=self.REPO)


class NonPersonaHeadRefScanTests(_ResolveOverFakeCommentsHarness):
    """#1206: the comment verdict scan must run for EVERY head-ref shape.

    Each assertion below is a kill-shot on the pre-fix resolver: it returned
    `comment_reviewers == set()` and `total_distinct == 0` for all of these
    inputs, so every `assertEqual(..., 2)` here was `0` before the fix.
    """

    DEPENDABOT_REF = "dependabot/docker/integration-tests/fake_oauth/python-d3400aa"

    def test_dependabot_head_ref_with_two_approvals_reaches_two_of_two(self):
        """THE LIVE DEFECT, reproduced offline (noorinalabs-deploy#691)."""
        verdicts = self._resolve(
            self.DEPENDABOT_REF,
            [self._verdict("Lucas Ferreira"), self._verdict("Nino Kavtaradze")],
        )
        self.assertEqual(verdicts.distinct_reviewers, {"lucas ferreira", "nino kavtaradze"})
        self.assertEqual(verdicts.total_distinct, 2)
        self.assertEqual(verdicts.comment_scan, hook.COMMENT_SCAN_NO_BRANCH_AUTHOR)

    def test_head_ref_with_no_slash_neither_crashes_nor_skips(self):
        """A ref with no separator at all used to fall through both branches."""
        verdicts = self._resolve(
            "nohashinthisref",
            [self._verdict("Lucas Ferreira"), self._verdict("Nino Kavtaradze")],
        )
        self.assertEqual(verdicts.total_distinct, 2)
        self.assertTrue(verdicts.comment_scan_ran)

    def test_empty_head_ref_still_scans(self):
        """`get_pr_data` defaults `headRefName` to `""`; that must scan, not skip."""
        verdicts = self._resolve("", [self._verdict("Aino Virtanen")])
        self.assertEqual(verdicts.distinct_reviewers, {"aino virtanen"})
        self.assertTrue(verdicts.comment_scan_ran)

    def test_none_head_ref_does_not_crash(self):
        """A hand-built `pr_data` carrying `None` must degrade, not raise."""
        pr_data = self._pr_data("")
        pr_data["headRefName"] = None

        def fake_run(args, capture_output, text, timeout):  # noqa: ARG001
            result = mock.MagicMock()
            result.returncode = 0
            result.stdout = json.dumps([self._verdict("Aino Virtanen")])
            return result

        with (
            mock.patch.object(hook.subprocess, "run", side_effect=fake_run),
            mock.patch.object(hook, "fetch_pr_commits", return_value=[]),
            mock.patch.object(hook, "_load_roster_names", return_value=set(self.ROSTER)),
        ):
            verdicts = hook.resolve_review_verdicts(pr_data, repo=self.REPO)

        self.assertEqual(verdicts.head_ref, "")
        self.assertEqual(verdicts.distinct_reviewers, {"aino virtanen"})

    def test_non_roster_requestor_on_a_bot_branch_still_does_not_count(self):
        """The gate is not relaxed: widening the sentinel must not smuggle a
        non-roster Requestor past the #498 filter. Paired with a roster name in
        the SAME thread as the positive control — a fix that broke roster
        filtering outright would satisfy neither half.
        """
        verdicts = self._resolve(
            self.DEPENDABOT_REF,
            [self._verdict("Lucas Ferreira"), self._verdict("Mallory Impostor")],
        )
        self.assertEqual(verdicts.roster_comment_reviewers, {"lucas ferreira"})
        self.assertEqual(verdicts.non_roster_requestors, {"mallory impostor"})
        self.assertEqual(verdicts.total_distinct, 1)

    def test_changes_requested_on_a_bot_branch_still_does_not_count(self):
        """Nor may it admit a non-Approved verdict (#940 stays in force)."""
        verdicts = self._resolve(
            self.DEPENDABOT_REF,
            [
                self._verdict("Lucas Ferreira"),
                self._verdict("Nino Kavtaradze", direction="Changes Requested"),
            ],
        )
        self.assertEqual(verdicts.distinct_reviewers, {"lucas ferreira"})
        self.assertEqual(verdicts.total_distinct, 1)

    def test_stale_verdict_on_a_bot_branch_is_still_excluded(self):
        """Content binding (#950) must survive the widened dispatch."""
        stale = self._verdict("Lucas Ferreira")
        stale["created_at"] = "2026-01-01T00:00:00Z"  # before T_content
        verdicts = self._resolve(self.DEPENDABOT_REF, [stale, self._verdict("Nino Kavtaradze")])
        self.assertEqual(verdicts.distinct_reviewers, {"nino kavtaradze"})
        self.assertEqual(len(verdicts.stale_verdicts_comment), 1)
        self.assertEqual(verdicts.stale_verdicts_comment[0].reviewer, "Lucas Ferreira")


class HeadRefScanRegressionTests(_ResolveOverFakeCommentsHarness):
    """The two behaviours #1206 must leave EXACTLY as they were."""

    def test_persona_branch_still_excludes_the_pr_author(self):
        """Self-review exclusion is the reason the head ref is consulted at all.

        Lucas Ferreira's own Approved on `L.Ferreira/…` must stay out, while
        Aino Virtanen's is admitted — the admitted half is the positive control
        proving the scan ran, so a regression that skipped the scan entirely
        would fail this test rather than passing its absence assertion.
        """
        verdicts = self._resolve(
            "L.Ferreira/1206-x",
            [self._verdict("Lucas Ferreira"), self._verdict("Aino Virtanen")],
        )
        self.assertNotIn("lucas ferreira", verdicts.distinct_reviewers)
        self.assertEqual(verdicts.distinct_reviewers, {"aino virtanen"})
        self.assertEqual(verdicts.branch_author_lastname, "Ferreira")
        self.assertEqual(verdicts.comment_scan, hook.COMMENT_SCAN_AUTHOR_EXCLUDED)

    def test_persona_branch_still_admits_the_same_surname_colleague(self):
        """#1172 must not regress: Santiago is not Lucas."""
        verdicts = self._resolve(
            "L.Ferreira/1206-x",
            [self._verdict("Santiago Ferreira"), self._verdict("Lucas Ferreira")],
        )
        self.assertEqual(verdicts.distinct_reviewers, {"santiago ferreira"})

    def test_wave_merge_branch_behaviour_is_unchanged(self):
        """`deployments/phase-N/wave-M` counted every roster reviewer before the
        fix (main#294's empty sentinel) and must still do so — same reviewers,
        same count.

        The MODE changed at #1216 (`WAVE_INTEGRATION`, the policy answer) but the
        counted set did not, which is this test's actual subject and the reason
        it survives #1216 with one line touched.
        """
        verdicts = self._resolve(
            "deployments/phase-10/wave-29",
            [self._verdict("Lucas Ferreira"), self._verdict("Nino Kavtaradze")],
        )
        self.assertEqual(verdicts.distinct_reviewers, {"lucas ferreira", "nino kavtaradze"})
        self.assertEqual(verdicts.total_distinct, 2)
        self.assertEqual(verdicts.comment_scan, hook.COMMENT_SCAN_WAVE_INTEGRATION)
        self.assertIsNone(verdicts.branch_author_lastname)

    def test_two_reviewer_threshold_is_not_relaxed_anywhere(self):
        """One approval is still one approval, on a bot branch as on any other.

        The whole risk of this change is that "count the verdicts that exist"
        slides into "need fewer verdicts". Pinned on the exact shape that was
        broken.
        """
        verdicts = self._resolve(
            NonPersonaHeadRefScanTests.DEPENDABOT_REF, [self._verdict("Lucas Ferreira")]
        )
        self.assertEqual(verdicts.total_distinct, 1)
        self.assertFalse(verdicts.total_distinct >= 2)


class HyphenatedSurnameCountingGateTests(_ResolveOverFakeCommentsHarness):
    """The COUNTING gate on a hyphenated-surname branch (main#1269 review).

    This half was not introduced by #1175 — `validate_pr_review`'s local copy
    already used `[-/]`, so it already truncated `K.Mensah-Williams/…` to
    `Mensah`. It is fixed here because the #1269 charset fix lands in the one
    shared regex both hooks now read, so repairing the format hook repairs this
    too, and an unpinned improvement is one refactor away from being undone.

    `Kofi Mensah` (design-system) and `Kofi Mensah-Williams` (landing-page) are
    two distinct roster members sharing a first initial, so the truncated surname
    matched the WRONG person exactly — the self-review exclusion then fired on a
    legitimate reviewer and failed to fire on the actual author. Both directions
    are asserted; asserting only one would pass under a gate that excludes
    nobody at all.
    """

    ROSTER = {
        "kofi mensah",
        "kofi mensah-williams",
        "aino virtanen",
        "nadia khoury",
    }
    REF = "K.Mensah-Williams/0001-project-scaffolding"

    def test_the_same_initial_colleague_is_counted_not_swallowed(self):
        """THE DEFECT: Kofi Mensah's verdict was dropped as a self-review.

        Pre-fix the ref parsed to `Mensah`, which IS his surname, so a genuine
        reviewer was excluded and the PR sat one approval short with no
        observable explanation.
        """
        verdicts = self._resolve(
            self.REF,
            [self._verdict("Kofi Mensah"), self._verdict("Aino Virtanen")],
        )
        self.assertEqual(verdicts.branch_author_lastname, "Mensah-Williams")
        self.assertIn("kofi mensah", verdicts.distinct_reviewers)
        self.assertEqual(verdicts.distinct_reviewers, {"kofi mensah", "aino virtanen"})
        self.assertEqual(verdicts.total_distinct, 2)

    def test_the_actual_branch_author_is_still_excluded(self):
        """The other direction. Pre-fix `Mensah-Williams` did NOT match the
        truncated `Mensah`, so the real author's self-review was counted —
        a two-reviewer gate satisfiable by one person plus themselves.

        Aino Virtanen is the positive control: her verdict must survive, so a
        regression that excluded everyone would fail here rather than pass the
        absence assertion for free.
        """
        verdicts = self._resolve(
            self.REF,
            [self._verdict("Kofi Mensah-Williams"), self._verdict("Aino Virtanen")],
        )
        self.assertNotIn("kofi mensah-williams", verdicts.distinct_reviewers)
        self.assertEqual(verdicts.distinct_reviewers, {"aino virtanen"})
        self.assertEqual(verdicts.total_distinct, 1)
        self.assertEqual(verdicts.comment_scan, hook.COMMENT_SCAN_AUTHOR_EXCLUDED)

    def test_the_dash_form_of_the_same_ref_behaves_identically(self):
        """The truncation hit both separators, so both are pinned."""
        verdicts = self._resolve(
            "K.Mensah-Williams-0001-project-scaffolding",
            [self._verdict("Kofi Mensah"), self._verdict("Kofi Mensah-Williams")],
        )
        self.assertEqual(verdicts.branch_author_lastname, "Mensah-Williams")
        self.assertEqual(verdicts.distinct_reviewers, {"kofi mensah"})

    def test_the_fixture_ref_is_not_silently_unparsed(self):
        """Anti-vacuity: a ref that parsed to None would ALSO count both
        reviewers (the `""` wave-merge sentinel excludes nobody), so
        `test_the_same_initial_colleague_is_counted_not_swallowed` could pass
        for entirely the wrong reason. Prove the prefix really was read."""
        for ref in (self.REF, "K.Mensah-Williams-0001-project-scaffolding"):
            with self.subTest(ref=ref):
                self.assertEqual(hook.extract_branch_author_lastname(ref), "Mensah-Williams")
                self.assertEqual(hook.branch_author_first_initial(ref), "k")


class CommentScanNotMeasuredTests(_ResolveOverFakeCommentsHarness):
    """#1206 half two: a non-measurement must never render as a measurement.

    The original defect was invisible for months precisely because the report
    said `0/2 required — (none)` and `stale verdicts: none` — two sentences
    that describe findings — when nothing had been looked at. These pin that a
    skipped scan is now loud at every layer.
    """

    def test_review_verdicts_defaults_to_not_measured(self):
        """The DEFAULT must be the honest one. A future field-by-field
        construction that forgets `comment_scan` has to degrade to "not
        measured", never to a false claim that the thread was read."""
        verdicts = hook.ReviewVerdicts(
            number=1,
            head_ref="x",
            labels=[],
            branch_author_lastname=None,
            content_sha="",
            content_ts=None,
            formal_reviewers=set(),
            comment_reviewers=set(),
            non_roster_requestors=set(),
            roster_comment_reviewers=set(),
            roster_names=set(),
            distinct_reviewers=set(),
            stale_verdicts_comment=[],
            stale_verdicts_formal=[],
            reviews_missing_tech_debt=[],
            tech_debt_issue_numbers=[],
            tech_debt_unparseable=[],
            wave_bootstrap_exception=False,
        )
        self.assertEqual(verdicts.comment_scan, hook.COMMENT_SCAN_NOT_RUN)
        self.assertFalse(verdicts.comment_scan_ran)

    def test_a_reintroduced_skip_path_fails_closed_with_a_named_reason(self):
        """The regression guard, exercised rather than asserted-by-comment.

        Patching `comment_scan_scope` to return NOT_RUN simulates exactly the
        future edit this guard exists for — a head-ref shape that dispatches to
        no scan. The resolver must raise rather than return a zero, because a
        zero from an unscanned thread is the absence of evidence, not evidence
        of absence (#981's stance, applied one level up).
        """
        with mock.patch.object(hook, "comment_scan_scope", return_value=hook.COMMENT_SCAN_NOT_RUN):
            with self.assertRaises(hook.CommentScanUndeterminedError) as ctx:
                self._resolve("whatever/ref", [self._verdict("Lucas Ferreira")])
        self.assertIn("not dispatched", ctx.exception.reason)
        self.assertIn("whatever/ref", ctx.exception.reason)

    def test_positive_control_same_setup_does_not_raise_unpatched(self):
        """Proves the experiment above ran: identical inputs WITHOUT the patch
        must resolve cleanly. Without this, the assertRaises could be passing
        on some unrelated failure in the harness."""
        verdicts = self._resolve("whatever/ref", [self._verdict("Lucas Ferreira")])
        self.assertEqual(verdicts.distinct_reviewers, {"lucas ferreira"})
        self.assertTrue(verdicts.comment_scan_ran)

    def _block_reason(self, verdicts) -> str:
        input_data = {
            "tool_name": "Bash",
            "tool_input": {"command": "gh pr merge 691 --repo noorinalabs/noorinalabs-main"},
        }
        with (
            mock.patch.object(
                hook,
                "get_pr_data",
                return_value=self._pr_data("dependabot/docker/x-1.2.3"),
            ),
            mock.patch.object(hook, "resolve_review_verdicts", return_value=verdicts),
            mock.patch.object(hook, "log_pretooluse_block"),
        ):
            result = hook.check(input_data)
        # `assert` rather than `assertIsNotNone` so mypy narrows away the
        # `dict | None` return before the indexing below.
        assert result is not None, "check() must BLOCK a 0/2 PR, not return None"
        self.assertEqual(result["decision"], "block")
        return str(result["reason"])

    @staticmethod
    def _empty_verdicts(comment_scan: str):
        return hook.ReviewVerdicts(
            number=691,
            head_ref="dependabot/docker/x-1.2.3",
            labels=[],
            branch_author_lastname=None,
            content_sha="837c272a",
            content_ts=None,
            formal_reviewers=set(),
            comment_reviewers=set(),
            non_roster_requestors=set(),
            roster_comment_reviewers=set(),
            roster_names={"lucas ferreira"},
            distinct_reviewers=set(),
            stale_verdicts_comment=[],
            stale_verdicts_formal=[],
            reviews_missing_tech_debt=[],
            tech_debt_issue_numbers=[],
            tech_debt_unparseable=[],
            wave_bootstrap_exception=False,
            comment_scan=comment_scan,
        )

    def test_block_message_distinguishes_not_measured_from_measured_empty(self):
        """Same 0/2 count, two different causes, two different messages.

        Both branches are asserted in BOTH directions — the not-measured
        message must say so and the measured one must NOT — so a change that
        emitted the alarming wording unconditionally fails just as loudly as
        one that emitted it never.
        """
        not_measured = self._block_reason(self._empty_verdicts(hook.COMMENT_SCAN_NOT_RUN))
        measured = self._block_reason(self._empty_verdicts(hook.COMMENT_SCAN_NO_BRANCH_AUTHOR))

        self.assertNotEqual(not_measured, measured)
        self.assertIn("DID NOT RUN", not_measured)
        self.assertIn("NOT a measurement", not_measured)
        self.assertNotIn("DID NOT RUN", measured)
        self.assertIn("The scan DID run", measured)
        # Both still block on the same threshold — the wording differs, the
        # gate does not.
        self.assertIn("0/2 required peer reviews", not_measured)
        self.assertIn("0/2 required peer reviews", measured)


class PersonaAliasFromEmailTests(unittest.TestCase):
    """#1210: which commit-author ADDRESSES name a persona, and which do not.

    This is where the squash hazard (#1177) is decided, so the negative cases
    matter more than the positive one.
    """

    def test_persona_alias_resolves(self):
        self.assertEqual(
            hook.persona_alias_from_email("parametrization+Aino.Virtanen@gmail.com"),
            "Aino.Virtanen",
        )

    def test_bare_principal_resolves_to_nothing(self):
        """THE #1177 decision, stated as a test.

        A squash re-authors a persona's commit to the bare principal, so this
        address is evidence that identity was DESTROYED. Mapping it to a name
        would make the gate exclude a persona who may have had nothing to do
        with the branch.
        """
        self.assertEqual(hook.persona_alias_from_email("parametrization@gmail.com"), "")

    def test_roster_json_maps_the_bare_principal_and_this_function_refuses_to(self):
        """The trap is REAL and this function deliberately walks past it.

        `.claude/team/roster.json` genuinely maps `parametrization@gmail.com` to
        a persona name. Anyone "improving" this function by consulting that map
        would ship the silent-wrong-persona bug — so the map's existence is
        asserted here, next to the refusal, rather than left as a comment.
        """
        roster_path = Path(__file__).resolve().parents[2] / "team" / "roster.json"
        roster = json.loads(roster_path.read_text(encoding="utf-8"))
        bare_mapped = [
            name for name, email in roster.items() if email == "parametrization@gmail.com"
        ]
        self.assertTrue(
            bare_mapped,
            "fixture premise gone: roster.json no longer maps the bare principal, so this "
            "test no longer proves the refusal is meaningful — re-check the #1177 reasoning",
        )
        self.assertEqual(hook.persona_alias_from_email("parametrization@gmail.com"), "")

    def test_github_noreply_login_is_not_a_persona(self):
        """`12345+octocat@…` has a `+` but the part after it is a login.

        This is what keeps a GitHub-UI or bot commit from inventing an author,
        without a bot-name blocklist that could be incomplete.
        """
        for email in (
            "49699333+dependabot[bot]@users.noreply.github.com",
            "1234567+octocat@users.noreply.github.com",
            "noreply@github.com",
        ):
            with self.subTest(email=email):
                self.assertEqual(hook.persona_alias_from_email(email), "")

    def test_hyphenated_and_compound_roster_names_resolve(self):
        """Real roster aliases, not idealised ones."""
        for alias in ("Jun-Seo.Park", "Marisol.Vega-Cruz", "Nadia.Boukhari"):
            with self.subTest(alias=alias):
                self.assertEqual(
                    hook.persona_alias_from_email(f"parametrization+{alias}@gmail.com"), alias
                )

    def test_malformed_input_yields_empty(self):
        for value in ("", "not-an-email", "parametrization+@gmail.com", "+Aino@gmail.com"):
            with self.subTest(value=value):
                self.assertEqual(hook.persona_alias_from_email(value), "")


class CommitAuthorIdentityDerivationTests(unittest.TestCase):
    """#1210: deriving the branch author from the PR's commits."""

    @staticmethod
    def _names(identities) -> set[tuple[str, str]]:
        """The comparison KEY of each derived identity — `(lastname, initial)`.

        Asserted on the key rather than on the display string so a test cannot
        pass because two different people happened to render the same way.
        """
        return {(i.lastname.lower(), i.initial) for i in identities}

    def test_author_name_yields_lastname_and_initial(self):
        identities = hook.commit_author_identities(
            [_api_commit("a1", "2026-07-20T00:00:00Z", author_name="Aino Virtanen")]
        )
        self.assertEqual(self._names(identities), {("virtanen", "a")})

    def test_merge_commit_authors_are_not_branch_authors(self):
        """Running `gh pr merge` into a wave branch does not make you its author.

        Excluding merge authors would false-block the wave merges the release
        coordinator is required to review — the `feedback_commit_author_gate_
        exclude_merges` lesson, applied to the identity half.
        """
        identities = hook.commit_author_identities(
            [
                _api_commit("m1", "2026-07-20T00:00:00Z", parents=2, author_name="Nadia Khoury"),
                _api_commit("c1", "2026-07-20T01:00:00Z", author_name="Aino Virtanen"),
            ]
        )
        self.assertEqual(self._names(identities), {("virtanen", "a")})

    def test_every_non_merge_author_is_returned_not_just_the_latest(self):
        """A branch handed between two personas has TWO authors.

        Taking only the latest content commit's author would leave the earlier
        one free to self-approve.
        """
        identities = hook.commit_author_identities(
            [
                _api_commit("c1", "2026-07-20T00:00:00Z", author_name="Lucas Ferreira"),
                _api_commit("c2", "2026-07-20T01:00:00Z", author_name="Aino Virtanen"),
            ]
        )
        self.assertEqual(self._names(identities), {("ferreira", "l"), ("virtanen", "a")})

    def test_name_and_matching_alias_dedupe_to_one_person(self):
        identities = hook.commit_author_identities(
            [
                _api_commit(
                    "c1",
                    "2026-07-20T00:00:00Z",
                    author_name="Aino Virtanen",
                    author_email="parametrization+Aino.Virtanen@gmail.com",
                )
            ]
        )
        self.assertEqual(len(identities), 1)
        self.assertEqual(self._names(identities), {("virtanen", "a")})

    def test_email_alias_recovers_the_person_when_the_name_is_a_handle(self):
        """The union's reason to exist: the two sources disagree exactly when
        one of them is not a name."""
        identities = hook.commit_author_identities(
            [
                _api_commit(
                    "c1",
                    "2026-07-20T00:00:00Z",
                    author_name="octocat",
                    author_email="parametrization+Aino.Virtanen@gmail.com",
                )
            ]
        )
        self.assertIn(("virtanen", "a"), self._names(identities))

    def test_bare_principal_email_contributes_nothing(self):
        """Only the NAME survives a squash-flattened address — never the address."""
        identities = hook.commit_author_identities(
            [
                _api_commit(
                    "c1",
                    "2026-07-20T00:00:00Z",
                    author_name="",
                    author_email="parametrization@gmail.com",
                )
            ]
        )
        self.assertEqual(identities, ())

    def test_empty_author_fields_yield_no_identity(self):
        self.assertEqual(
            hook.commit_author_identities([_api_commit("c1", "2026-07-20T00:00:00Z")]), ()
        )
        self.assertEqual(hook.commit_author_identities([]), ())

    def test_bot_commit_matches_no_roster_persona(self):
        """Bots stay neutral BY CONSTRUCTION, not by a blocklist.

        Asserted at the level that matters — no roster name is treated as a
        self-review — rather than by asserting the derivation returned nothing,
        which would pass for a bot name the derivation happened to mangle.
        """
        identities = hook.commit_author_identities(
            [
                _api_commit(
                    "c1",
                    "2026-07-20T00:00:00Z",
                    author_name="dependabot[bot]",
                    author_email="49699333+dependabot[bot]@users.noreply.github.com",
                )
            ]
        )
        for persona in ("Lucas Ferreira", "Nino Kavtaradze", "Aino Virtanen", "Steven French"):
            with self.subTest(persona=persona):
                self.assertFalse(hook.is_self_review(persona, "", "", identities))


class IsSelfReviewTests(unittest.TestCase):
    """#1210 reuses the ONE person-comparison (#1172), on both author sources."""

    LUCAS = hook.CommitAuthorIdentity(lastname="Ferreira", initial="l", display="Lucas Ferreira")

    def test_commit_author_is_a_self_review(self):
        self.assertTrue(hook.is_self_review("Lucas Ferreira", "", "", (self.LUCAS,)))

    def test_same_surname_colleague_is_not_the_commit_author(self):
        """The Ferreira/Ferreira collision, on the NEW path.

        A hand-rolled surname comparison here would re-create main#1172 in the
        commit-identity source while `charter_trailer` stayed correct.
        """
        self.assertFalse(hook.is_self_review("Santiago Ferreira", "", "", (self.LUCAS,)))

    def test_ref_prefix_arm_is_unchanged(self):
        self.assertTrue(hook.is_self_review("Lucas Ferreira", "Ferreira", "l", ()))
        self.assertFalse(hook.is_self_review("Santiago Ferreira", "Ferreira", "l", ()))

    def test_no_author_from_either_source_excludes_nobody(self):
        self.assertFalse(hook.is_self_review("Lucas Ferreira", "", "", ()))


class RefineCommentScanScopeTests(unittest.TestCase):
    """#1210's allowed transitions, re-keyed by #1220 on roster membership."""

    ROSTER = {"aino virtanen", "santiago ferreira", "nino kavtaradze"}
    IDENT = (hook.CommitAuthorIdentity(lastname="Virtanen", initial="a", display="Aino Virtanen"),)
    BOT = (
        hook.CommitAuthorIdentity(
            lastname="dependabot[bot]", initial="d", display="dependabot[bot]"
        ),
    )

    def test_no_branch_author_upgrades_when_commits_named_a_roster_persona(self):
        self.assertEqual(
            hook.refine_comment_scan_scope(
                hook.COMMENT_SCAN_NO_BRANCH_AUTHOR, self.IDENT, self.ROSTER
            ),
            hook.COMMENT_SCAN_COMMIT_AUTHOR_EXCLUDED,
        )

    def test_wave_integration_is_never_refined_even_with_derived_identities(self):
        """#1216: the POLICY answer cannot be argued out of by commit evidence.

        `resolve_review_verdicts` passes `()` on a wave ref, so in production
        the `not commit_authors` guard already returns this untouched — which is
        exactly why it needs a unit test: the property would otherwise hold by
        the caller's grace rather than by the function's contract, and the next
        caller would not inherit it. Deliberately passes a ROSTER-MATCHING
        identity, the input that would upgrade any other non-terminal mode.
        """
        self.assertEqual(
            hook.refine_comment_scan_scope(
                hook.COMMENT_SCAN_WAVE_INTEGRATION, self.IDENT, self.ROSTER
            ),
            hook.COMMENT_SCAN_WAVE_INTEGRATION,
        )
        self.assertEqual(
            hook.refine_comment_scan_scope(
                hook.COMMENT_SCAN_WAVE_INTEGRATION, self.BOT, self.ROSTER
            ),
            hook.COMMENT_SCAN_WAVE_INTEGRATION,
        )
        # An unreadable roster must not shake it loose either.
        self.assertEqual(
            hook.refine_comment_scan_scope(hook.COMMENT_SCAN_WAVE_INTEGRATION, self.IDENT, set()),
            hook.COMMENT_SCAN_WAVE_INTEGRATION,
        )

    def test_derived_identity_matching_no_roster_persona_is_reported_inert(self):
        """THE #1220 unit-level kill-shot.

        Pre-fix this returned COMMIT_AUTHOR_EXCLUDED — "an identity was derived"
        reported as "an exclusion was applied". `dependabot[bot]` can never be a
        Requestor that survives roster filtering, so nothing was subtracted and
        the mode must not claim one was.
        """
        self.assertEqual(
            hook.refine_comment_scan_scope(
                hook.COMMENT_SCAN_NO_BRANCH_AUTHOR, self.BOT, self.ROSTER
            ),
            hook.COMMENT_SCAN_COMMIT_AUTHOR_NON_ROSTER,
        )

    def test_one_roster_persona_among_several_derivations_is_still_live(self):
        """A human fixup on a bot branch. Exclusion IS live for that human, so
        the inert reading must not win just because a bot is also in the tuple —
        the predicate is ANY, not ALL."""
        self.assertEqual(
            hook.refine_comment_scan_scope(
                hook.COMMENT_SCAN_NO_BRANCH_AUTHOR, self.BOT + self.IDENT, self.ROSTER
            ),
            hook.COMMENT_SCAN_COMMIT_AUTHOR_EXCLUDED,
        )

    def test_same_surname_different_person_is_not_live(self):
        """#1172 must hold in the new predicate too: Lucas is not Santiago.

        The roster here contains `santiago ferreira` and NOT Lucas. A liveness
        check written as a surname `in` test would call this live and re-open the
        Ferreira/Ferreira collision inside the reporting layer.
        """
        lucas = (
            hook.CommitAuthorIdentity(lastname="Ferreira", initial="l", display="Lucas Ferreira"),
        )
        self.assertEqual(
            hook.refine_comment_scan_scope(hook.COMMENT_SCAN_NO_BRANCH_AUTHOR, lucas, self.ROSTER),
            hook.COMMENT_SCAN_COMMIT_AUTHOR_NON_ROSTER,
        )

    def test_unreadable_roster_keeps_the_pre_1220_answer(self):
        """An empty roster means the roster could not be READ, not that the org
        is empty — so "matches no roster persona" would be a finding derived
        from a failed read. The undecidable case keeps the modal EXCLUDED
        wording rather than asserting inertness it cannot establish."""
        self.assertEqual(
            hook.refine_comment_scan_scope(hook.COMMENT_SCAN_NO_BRANCH_AUTHOR, self.IDENT, set()),
            hook.COMMENT_SCAN_COMMIT_AUTHOR_EXCLUDED,
        )

    def test_no_branch_author_stays_when_commits_named_nobody(self):
        self.assertEqual(
            hook.refine_comment_scan_scope(hook.COMMENT_SCAN_NO_BRANCH_AUTHOR, (), self.ROSTER),
            hook.COMMENT_SCAN_NO_BRANCH_AUTHOR,
        )

    def test_ref_derived_author_is_never_downgraded(self):
        self.assertEqual(
            hook.refine_comment_scan_scope(
                hook.COMMENT_SCAN_AUTHOR_EXCLUDED, self.IDENT, self.ROSTER
            ),
            hook.COMMENT_SCAN_AUTHOR_EXCLUDED,
        )

    def test_ref_derived_author_is_not_downgraded_by_a_non_roster_derivation(self):
        """The #1220 arm must not leak onto the ref path either: a declared
        `{Initial}.{Lastname}` author keeps its exclusion whatever the commits
        say, including when they say `dependabot[bot]`."""
        self.assertEqual(
            hook.refine_comment_scan_scope(
                hook.COMMENT_SCAN_AUTHOR_EXCLUDED, self.BOT, self.ROSTER
            ),
            hook.COMMENT_SCAN_AUTHOR_EXCLUDED,
        )

    def test_not_run_is_never_upgraded(self):
        """A scan that did not happen cannot acquire a mode.

        Laundering NOT_RUN into a real mode here would defeat the #1206
        defense-in-depth hard-block one layer up.
        """
        self.assertEqual(
            hook.refine_comment_scan_scope(hook.COMMENT_SCAN_NOT_RUN, self.IDENT, self.ROSTER),
            hook.COMMENT_SCAN_NOT_RUN,
        )

    def test_not_run_is_not_relabelled_as_inert_either(self):
        """#1220 added a second reachable answer, so NOT_RUN now has two ways to
        be laundered. Both must be closed."""
        self.assertEqual(
            hook.refine_comment_scan_scope(hook.COMMENT_SCAN_NOT_RUN, self.BOT, self.ROSTER),
            hook.COMMENT_SCAN_NOT_RUN,
        )

    def test_roster_names_is_required_not_defaulted(self):
        """A caller that forgets the roster must fail loudly.

        A `set()` default would read as "roster unreadable" and hand them a
        plausible EXCLUDED answer for every input — the silent-wrong direction.
        """
        with self.assertRaises(TypeError):
            hook.refine_comment_scan_scope(  # type: ignore[call-arg]
                hook.COMMENT_SCAN_NO_BRANCH_AUTHOR, self.BOT
            )


class CommitIdentitySelfReviewExclusionTests(_ResolveOverFakeCommentsHarness):
    """#1210 end-to-end: the residual #1207 disclosed, closed.

    THE case, from the issue's own table — a human persona on a NON-CHARTER
    branch posts their own `Approved` plus one genuine reviewer approves:

        pre-#1207   0/2 blocked (wrongly — the genuine reviewer was uncounted)
        post-#1207  2/2 PASSES  (wrongly — the self-review was counted)
        correct     1/2 blocked
    """

    NON_CHARTER_REF = "feature/some-hand-made-branch"
    WAVE_REF = "deployments/phase-10/wave-29"
    DEPENDABOT_REF = "dependabot/docker/integration-tests/fake_oauth/python-d3400aa"

    @staticmethod
    def _authored_by(*names: str) -> list[dict]:
        return [
            _api_commit(
                f"c{n}",
                "2026-07-15T19:13:59Z",
                author_name=name,
                author_email=f"parametrization+{name.replace(' ', '.')}@gmail.com",
            )
            for n, name in enumerate(names)
        ]

    def test_self_approval_on_a_non_charter_ref_no_longer_reaches_two_of_two(self):
        """THE #1210 kill-shot. RED before the fix: `total_distinct == 2`."""
        verdicts = self._resolve(
            self.NON_CHARTER_REF,
            [self._verdict("Nino Kavtaradze"), self._verdict("Aino Virtanen")],
            commits=self._authored_by("Nino Kavtaradze"),
        )
        self.assertEqual(verdicts.distinct_reviewers, {"aino virtanen"})
        self.assertEqual(verdicts.total_distinct, 1)
        self.assertEqual(verdicts.comment_scan, hook.COMMENT_SCAN_COMMIT_AUTHOR_EXCLUDED)

    def test_positive_control_two_genuine_reviewers_still_reach_two_of_two(self):
        """Anti-vacuity (`feedback_fixture_makes_guard_assertion_inert`).

        Identical shape, except the branch author is NOT one of the reviewers.
        Without this, the assertion above would be satisfied by a change that
        simply stopped counting comment verdicts on non-charter refs — which
        would re-break #1206.
        """
        verdicts = self._resolve(
            self.NON_CHARTER_REF,
            [self._verdict("Nino Kavtaradze"), self._verdict("Aino Virtanen")],
            commits=self._authored_by("Lucas Ferreira"),
        )
        self.assertEqual(verdicts.distinct_reviewers, {"nino kavtaradze", "aino virtanen"})
        self.assertEqual(verdicts.total_distinct, 2)

    def test_wave_merge_branch_does_not_exclude_its_implementers(self):
        """#1216 REVERSES #1210 on this ref, deliberately. Read the charter first.

        This test replaces `test_wave_merge_branch_now_excludes_its_author_too`,
        which asserted the opposite. That is not a weakened assertion, it is a
        different rule: `pull-requests/reviews.md` § Who Counts as "the PR
        Author" states that a wave->main integration PR has no author on its
        branch — its commits are the wave's implementers, each already
        2x-reviewed on its own per-issue PR, and the integration PR authors
        nothing of its own. #1210 subtracted a genuine Approved reviewer on 4
        real PRs (main#711/#530/#293/#229) by treating them as authors.

        The exclusion #1210 exists for is unaffected: it still fires on every
        non-wave ref, pinned by `test_self_approval_on_a_non_charter_ref_no_
        longer_reaches_two_of_two` and by
        `test_a_non_wave_deployments_ref_keeps_the_commit_derived_exclusion`
        below.
        """
        verdicts = self._resolve(
            self.WAVE_REF,
            [self._verdict("Nadia Khoury"), self._verdict("Aino Virtanen")],
            roster=self.ROSTER | {"nadia khoury"},
            commits=self._authored_by("Nadia Khoury"),
        )
        self.assertEqual(verdicts.distinct_reviewers, {"nadia khoury", "aino virtanen"})
        self.assertEqual(verdicts.total_distinct, 2)
        self.assertEqual(verdicts.comment_scan, hook.COMMENT_SCAN_WAVE_INTEGRATION)
        # ONE tuple, not two (#1297). The carve-out is applied by NOT deriving,
        # so there is no unfiltered second set for a diagnostic to disagree with.
        self.assertEqual(verdicts.commit_author_identities, ())

    def test_a_non_wave_deployments_ref_keeps_the_commit_derived_exclusion(self):
        """The carve-out is the WAVE-BRANCH shape, not the `deployments/` prefix.

        `deployments/phase12/cleanup` is a real production ref (isnad-graph#603
        and #612). Widening `is_wave_branch` to `startswith("deployments/")`
        turns this RED — which is the mutation that would silently re-open #1210
        on a hand-made release branch.
        """
        verdicts = self._resolve(
            "deployments/phase12/cleanup",
            [self._verdict("Nadia Khoury"), self._verdict("Aino Virtanen")],
            roster=self.ROSTER | {"nadia khoury"},
            commits=self._authored_by("Nadia Khoury"),
        )
        self.assertEqual(verdicts.distinct_reviewers, {"aino virtanen"})
        self.assertEqual(verdicts.total_distinct, 1)
        self.assertEqual(verdicts.comment_scan, hook.COMMENT_SCAN_COMMIT_AUTHOR_EXCLUDED)

    def test_the_undashed_phase_wave_ref_gets_the_same_carve_out(self):
        """`deployments/phase15/wave-1` — 32 of 202 real PRs use this form.

        Keying the carve-out on the charter's dashed spelling alone would leave
        4 of the org's 7 repos on the #1210 behaviour while the other 3 moved,
        i.e. two policies decided by a hyphen. RED if `_WAVE_BRANCH_RE` loses
        its `-?`.
        """
        verdicts = self._resolve(
            "deployments/phase15/wave-1",
            [self._verdict("Nadia Khoury"), self._verdict("Aino Virtanen")],
            roster=self.ROSTER | {"nadia khoury"},
            commits=self._authored_by("Nadia Khoury"),
        )
        self.assertEqual(verdicts.distinct_reviewers, {"nadia khoury", "aino virtanen"})
        self.assertEqual(verdicts.comment_scan, hook.COMMENT_SCAN_WAVE_INTEGRATION)

    def test_main_711_replayed_from_its_real_payload(self):
        """The measured false block, reproduced offline (main#711).

        Real ref, real derived identities from the real commit payload, real
        Approved Requestors. Under #1210 this is 1/2 and blocked with Wanjiku
        Mwangi subtracted; under #1216 it is the 2/2 the reviewers actually
        earned. A count assertion, not a substring one (#1203).
        """
        commits = self._authored_by("Aino Virtanen", "Santiago Ferreira", "Wanjiku Mwangi")
        roster = self.ROSTER | {"nadia khoury", "wanjiku mwangi"}
        thread = [self._verdict("Nadia Khoury"), self._verdict("Wanjiku Mwangi")]

        after = self._resolve("deployments/phase-5/wave-5", thread, roster=roster, commits=commits)
        self.assertEqual(after.distinct_reviewers, {"nadia khoury", "wanjiku mwangi"})
        self.assertEqual(after.total_distinct, 2)

        # The pre-#1216 answer on the identical input, so the delta is measured
        # here rather than asserted from memory of what #1210 did.
        with mock.patch.object(hook, "is_wave_branch", return_value=False):
            before = self._resolve(
                "deployments/phase-5/wave-5", thread, roster=roster, commits=commits
            )
        self.assertEqual(before.distinct_reviewers, {"nadia khoury"})
        self.assertEqual(before.total_distinct, 1)

    def test_both_authors_of_a_handed_over_branch_are_excluded(self):
        verdicts = self._resolve(
            self.NON_CHARTER_REF,
            [
                self._verdict("Nino Kavtaradze"),
                self._verdict("Lucas Ferreira"),
                self._verdict("Aino Virtanen"),
            ],
            commits=self._authored_by("Nino Kavtaradze", "Lucas Ferreira"),
        )
        self.assertEqual(verdicts.distinct_reviewers, {"aino virtanen"})

    def test_same_surname_colleague_still_counts_on_a_commit_derived_author(self):
        """#1172 must hold on the new source too: Santiago is not Lucas."""
        verdicts = self._resolve(
            self.NON_CHARTER_REF,
            [self._verdict("Santiago Ferreira"), self._verdict("Aino Virtanen")],
            commits=self._authored_by("Lucas Ferreira"),
        )
        self.assertEqual(verdicts.distinct_reviewers, {"santiago ferreira", "aino virtanen"})

    def test_bot_branch_with_two_roster_approvals_still_passes(self):
        """deploy#691 must stay fixed, and no human author may be fabricated.

        A bot commit is NOT special-cased: `dependabot[bot]` is carried as a
        derived identity like any other author string. It is neutral because it
        matches no roster persona, which is the property that actually matters —
        both approvals still count. The bot's ADDRESS contributes nothing
        (#1181's matcher), so nothing invents a person from it.
        """
        verdicts = self._resolve(
            self.DEPENDABOT_REF,
            [self._verdict("Lucas Ferreira"), self._verdict("Nino Kavtaradze")],
            commits=[
                _api_commit(
                    "c0",
                    "2026-07-15T19:13:59Z",
                    author_name="dependabot[bot]",
                    author_email="49699333+dependabot[bot]@users.noreply.github.com",
                )
            ],
        )
        self.assertEqual(verdicts.distinct_reviewers, {"lucas ferreira", "nino kavtaradze"})
        self.assertEqual(verdicts.total_distinct, 2)
        # Exactly ONE identity, from the NAME — the address named nobody, so no
        # human persona was fabricated for a bot PR.
        self.assertEqual(
            [i.display for i in verdicts.commit_author_identities], ["dependabot[bot]"]
        )
        # #1220: THE assertion this test was missing, and the reason it stayed
        # green through the defect. It pinned the count and the derived
        # identities — the safe half of the claim — while the mode said
        # `commit-author-excluded`, i.e. announced a subtraction of a verdict
        # that was never subtracted. Both approvals are still counted above; the
        # mode must now describe that honestly.
        self.assertEqual(verdicts.comment_scan, hook.COMMENT_SCAN_COMMIT_AUTHOR_NON_ROSTER)

    def test_bot_branch_with_a_human_fixup_commit_still_reports_live_exclusion(self):
        """Anti-vacuity control for the test above (#1220).

        Same dependabot ref, same two roster approvals — except one commit is
        authored by one of the approvers. Without this, the assertion above would
        be satisfied by a change that simply stopped ever reporting
        COMMIT_AUTHOR_EXCLUDED on a non-charter ref, which would re-open #1210:
        Nino's own verdict must still be subtracted AND still be described as
        subtracted.
        """
        verdicts = self._resolve(
            self.DEPENDABOT_REF,
            [self._verdict("Lucas Ferreira"), self._verdict("Nino Kavtaradze")],
            commits=[
                _api_commit(
                    "c0",
                    "2026-07-15T19:13:59Z",
                    author_name="dependabot[bot]",
                    author_email="49699333+dependabot[bot]@users.noreply.github.com",
                ),
                _api_commit(
                    "c1",
                    "2026-07-15T19:13:59Z",
                    author_name="Nino Kavtaradze",
                    author_email="parametrization+Nino.Kavtaradze@gmail.com",
                ),
            ],
        )
        self.assertEqual(verdicts.distinct_reviewers, {"lucas ferreira"})
        self.assertEqual(verdicts.total_distinct, 1)
        self.assertEqual(verdicts.comment_scan, hook.COMMENT_SCAN_COMMIT_AUTHOR_EXCLUDED)

    def test_an_unreadable_roster_does_not_report_the_bot_as_inert(self):
        """The degraded read must not masquerade as an inertness measurement.

        With an unreadable roster (`_load_roster_names` returns the empty set)
        EVERY identity trivially matches nothing, so a naive predicate would
        report `commit-author-non-roster` — a confident claim about roster
        membership derived from a failed roster read. The mode falls back to the
        pre-#1220 answer instead.
        """
        verdicts = self._resolve(
            self.DEPENDABOT_REF,
            [self._verdict("Lucas Ferreira"), self._verdict("Nino Kavtaradze")],
            roster=set(),
            commits=[
                _api_commit(
                    "c0",
                    "2026-07-15T19:13:59Z",
                    author_name="dependabot[bot]",
                    author_email="49699333+dependabot[bot]@users.noreply.github.com",
                )
            ],
        )
        self.assertEqual(verdicts.comment_scan, hook.COMMENT_SCAN_COMMIT_AUTHOR_EXCLUDED)

    def test_squash_flattened_identity_excludes_nobody(self):
        """The bare principal must not resolve to the persona roster.json maps it to.

        A commit whose name is gone and whose address is the bare principal
        (#1177) yields no identity, so `Steven French` — the name that address
        maps to — is NOT excluded and still counts as a reviewer.
        """
        verdicts = self._resolve(
            self.NON_CHARTER_REF,
            [self._verdict("Steven French"), self._verdict("Aino Virtanen")],
            roster=self.ROSTER | {"steven french"},
            commits=[
                _api_commit(
                    "c0",
                    "2026-07-15T19:13:59Z",
                    author_name="",
                    author_email="parametrization@gmail.com",
                )
            ],
        )
        self.assertEqual(verdicts.distinct_reviewers, {"steven french", "aino virtanen"})
        self.assertEqual(verdicts.comment_scan, hook.COMMENT_SCAN_NO_BRANCH_AUTHOR)

    def test_persona_ref_does_not_consult_commit_identity(self):
        """Scope guard: 86.7% of the org's PRs must be byte-for-byte unchanged.

        On `L.Ferreira/…` the ref is authoritative. Nino authored the commits
        here and his Approved must STILL count — if commit identity leaked onto
        the persona path, anyone who pushed a fixup to someone else's branch
        would lose their review.
        """
        verdicts = self._resolve(
            "L.Ferreira/1210-x",
            [self._verdict("Nino Kavtaradze"), self._verdict("Aino Virtanen")],
            commits=self._authored_by("Nino Kavtaradze"),
        )
        self.assertEqual(verdicts.distinct_reviewers, {"nino kavtaradze", "aino virtanen"})
        self.assertEqual(verdicts.comment_scan, hook.COMMENT_SCAN_AUTHOR_EXCLUDED)
        self.assertEqual(verdicts.commit_author_identities, ())

    def test_merge_only_branch_derives_no_author(self):
        """No authored commits ⇒ no identity ⇒ the pre-#1210 state, unchanged.

        Re-targeted from `WAVE_REF` to a non-charter ref at #1216: on a wave ref
        the carve-out now short-circuits the derivation, so a wave ref could no
        longer distinguish "derived nothing" from "did not derive" and this
        test's subject would have quietly become untested (the vacuity shape
        `feedback_fixture_makes_guard_assertion_inert`). The merge-commit skip
        is what is under test, so it is asserted where the derivation still runs.
        """
        verdicts = self._resolve(
            self.NON_CHARTER_REF,
            [self._verdict("Lucas Ferreira"), self._verdict("Nino Kavtaradze")],
            commits=[
                _api_commit("m0", "2026-07-15T19:13:59Z", parents=2, author_name="Lucas Ferreira")
            ],
        )
        self.assertEqual(verdicts.total_distinct, 2)
        self.assertEqual(verdicts.comment_scan, hook.COMMENT_SCAN_NO_BRANCH_AUTHOR)

    def test_commit_fetch_failure_still_hard_blocks_on_a_non_charter_ref(self):
        """Degradation: no commit data ⇒ no branch author ⇒ STOP, never proceed."""
        with (
            mock.patch.object(
                hook, "fetch_pr_commits", side_effect=hook.CommitFetchError("HTTP 502")
            ),
            mock.patch.object(hook, "_load_roster_names", return_value=set(self.ROSTER)),
        ):
            with self.assertRaises(hook.CommitFetchError):
                hook.resolve_review_verdicts(self._pr_data(self.NON_CHARTER_REF), repo=self.REPO)


class OneDerivationDrivesModeAndExclusionTests(_ResolveOverFakeCommentsHarness):
    """One value decides both the reported mode and whether exclusion runs.

    `resolve_review_verdicts` derives `commit_authors` FROM `scan_scope`, so the
    mode that is REPORTED and the tuple the exclusion is APPLIED from cannot
    disagree about whether exclusion is live. #1216 adds a slice where exclusion
    is turned OFF, which is exactly the kind of edit that could desynchronise
    them; these tests pin the equivalence over every mode in both directions.

    SCOPE — THIS DOES NOT CLOSE #1297, WHICH REMAINS OPEN. An earlier version of
    this docstring said it did ("the #1297 shape, closed structurally"). That was
    FALSE and is retracted (#1310 review): #1297's mutation applied verbatim to
    this tree leaves the suite fully GREEN and lets a self-approver reach 2/2 on
    3 of its 4 identity shapes, with the mode never moving. The coupling binds
    whether the tuple is DERIVED; #1297 inserts a filtered COPY downstream of the
    derivation, so derivation and mode still agree and nothing here notices. What
    is caught is the mode-moving variant (M8/M9), which is a real and different
    property. #1297 needs the two count assertions its own closing section
    specifies — it must not be closed on the strength of this class.
    """

    # (head_ref, expected mode, expected reviewer set). The reviewer set is
    # MEASURED per case, not shared: on `A.Virtanen/…` Aino is excluded by the
    # REF arm even though the commit tuple is empty, and folding that case in
    # with the wave refs would either assert something false or weaken the
    # arithmetic assertion for all of them. (Caught by this very test on its
    # first run — the two exclusion arms are not interchangeable.)
    MODES_WITHOUT_DERIVATION = (
        ("A.Virtanen/1216-x", hook.COMMENT_SCAN_AUTHOR_EXCLUDED, {"nino kavtaradze"}),
        (
            "deployments/phase-10/wave-29",
            hook.COMMENT_SCAN_WAVE_INTEGRATION,
            {"aino virtanen", "nino kavtaradze"},
        ),
        (
            "deployments/phase15/wave-1",
            hook.COMMENT_SCAN_WAVE_INTEGRATION,
            {"aino virtanen", "nino kavtaradze"},
        ),
    )

    MODES_WITH_DERIVATION = (
        ("feature/hand-made", hook.COMMENT_SCAN_COMMIT_AUTHOR_EXCLUDED),
        ("deployments/phase12/cleanup", hook.COMMENT_SCAN_COMMIT_AUTHOR_EXCLUDED),
        ("dependabot/npm_and_yarn/x-1.2.3", hook.COMMENT_SCAN_COMMIT_AUTHOR_EXCLUDED),
        ("", hook.COMMENT_SCAN_COMMIT_AUTHOR_EXCLUDED),
    )

    def _resolve_ref(self, head_ref):
        return self._resolve(
            head_ref,
            [self._verdict("Aino Virtanen"), self._verdict("Nino Kavtaradze")],
            commits=[
                _api_commit(
                    "c0",
                    "2026-07-15T19:13:59Z",
                    author_name="Aino Virtanen",
                    author_email="parametrization+Aino.Virtanen@gmail.com",
                )
            ],
        )

    def test_a_mode_that_applies_no_commit_exclusion_carries_no_identities(self):
        """No second tuple can exist for a diagnostic to disagree with."""
        for head_ref, expected_mode, expected_reviewers in self.MODES_WITHOUT_DERIVATION:
            with self.subTest(head_ref=head_ref):
                verdicts = self._resolve_ref(head_ref)
                self.assertEqual(verdicts.comment_scan, expected_mode)
                self.assertEqual(verdicts.commit_author_identities, ())
                # The arithmetic the empty tuple implies, asserted rather than
                # inferred: on the wave refs Aino's own verdict is COUNTED;
                # on the persona ref the REF arm still drops it.
                self.assertEqual(verdicts.distinct_reviewers, expected_reviewers)

    def test_a_mode_that_applies_commit_exclusion_carries_the_identities(self):
        """Anti-vacuity: without this, a mutant that always passes `()` would
        satisfy the test above for every ref and silently kill #1210."""
        for head_ref, expected_mode in self.MODES_WITH_DERIVATION:
            with self.subTest(head_ref=head_ref):
                verdicts = self._resolve_ref(head_ref)
                self.assertEqual(verdicts.comment_scan, expected_mode)
                self.assertEqual(
                    [i.display for i in verdicts.commit_author_identities], ["Aino Virtanen"]
                )
                # Aino authored the branch, so her verdict is SUBTRACTED.
                self.assertEqual(verdicts.distinct_reviewers, {"nino kavtaradze"})
                self.assertEqual(verdicts.total_distinct, 1)

    def test_the_reported_identities_are_the_ones_the_exclusion_used(self):
        """The invariant itself, over both groups: a NON-empty identity tuple
        must coincide exactly with a mode that claims exclusion is live.

        On `main` the reported tuple and the excluded-from tuple are two separate
        expressions that merely happen to be equal today; here they are one
        value, and this asserts it over every mode.

        NOT #1297's closing assertion — that one is a COUNT test on an
        alias-only identity, and it is not written yet (#1297 stays open; see
        the class docstring).
        """
        refs = [case[0] for case in self.MODES_WITHOUT_DERIVATION] + [
            case[0] for case in self.MODES_WITH_DERIVATION
        ]
        for head_ref in refs:
            with self.subTest(head_ref=head_ref):
                verdicts = self._resolve_ref(head_ref)
                exclusion_claimed = verdicts.comment_scan in (
                    hook.COMMENT_SCAN_COMMIT_AUTHOR_EXCLUDED,
                    hook.COMMENT_SCAN_COMMIT_AUTHOR_NON_ROSTER,
                )
                self.assertEqual(
                    bool(verdicts.commit_author_identities),
                    exclusion_claimed,
                    f"{head_ref!r}: mode {verdicts.comment_scan!r} disagrees with the "
                    f"identity tuple {verdicts.commit_author_identities!r}",
                )


class StrictlyNonRelaxingTests(_ResolveOverFakeCommentsHarness):
    """The BAR for #1210: no input may make the gate pass what it blocked.

    The property is checked directly rather than argued: for a matrix of
    (head ref x commit authors x verdict thread), the post-fix reviewer set must
    be a SUBSET of the pre-fix one (pre-fix == the same resolve with no
    commit-derived identity). A subset can only lower `total_distinct`, and
    `check()` allows only on `>= 2` or on `== 1 with the wave-bootstrap
    exception` — neither of which a shrinking set can newly satisfy from a
    blocking state.
    """

    CASES = (
        ("feature/hand-made", ("Nino Kavtaradze",)),
        ("feature/hand-made", ("Lucas Ferreira", "Nino Kavtaradze")),
        ("feature/hand-made", ("Weronika Zielinska",)),
        ("deployments/phase-10/wave-29", ("Nino Kavtaradze",)),
        ("dependabot/npm_and_yarn/x-1.2.3", ("dependabot[bot]",)),
        ("", ("Aino Virtanen",)),
        ("nohashinthisref", ("Santiago Ferreira",)),
        ("L.Ferreira/1210-x", ("Nino Kavtaradze",)),
        ("L.Ferreira/1210-x", ("Lucas Ferreira",)),
    )

    THREAD = (
        "Lucas Ferreira",
        "Nino Kavtaradze",
        "Aino Virtanen",
        "Santiago Ferreira",
    )

    # `CASES` above all run against the 4-name `THREAD`, so `before` lands on 3
    # or 4 distinct reviewers in EVERY one of them — comfortably over the
    # 2-reviewer bar. That makes them useless to
    # `test_a_blocked_pr_never_becomes_an_allowed_one`, whose whole subject is
    # what happens to a PR the gate was BLOCKING: with no blocking start state
    # in the matrix, its guard body never ran and the test passed under a no-op
    # (`feedback_fixture_makes_guard_assertion_inert` / #1203, caught in review
    # of this very PR). These cases start from a thread SHORT of the bar, so
    # `before` blocks and the guard actually executes.
    #
    # Counts below are MEASURED, not reasoned — `before -> after` total_distinct.
    #
    # (head_ref, commit authors, verdict thread)
    BLOCKING_CASES = (
        # Commit-derived exclusion fires from a blocked state: 1 -> 0.
        ("feature/hand-made", ("Nino Kavtaradze",), ("Nino Kavtaradze",)),
        # Nadia's suggested case — the ref names nobody, the author reviews herself. 1 -> 0.
        ("feature/hand-made", ("Aino Virtanen",), ("Aino Virtanen",)),
        # A persona ref, blocked by the REF-prefix exclusion alone (Lucas dropped),
        # with commit authors present in the fixture. 1 -> 1, and that is the point:
        # `resolve_review_verdicts` passes `()` for commit identities whenever the
        # ref already names a persona, so the commit arm is silent here BY
        # CONSTRUCTION. This case pins that the two sources cannot stack into a
        # double exclusion on the same PR.
        ("L.Ferreira/1210-x", ("Nino Kavtaradze",), ("Lucas Ferreira", "Nino Kavtaradze")),
        # Blocked and stays blocked with NO exclusion firing (1 -> 1) — the
        # other half of the guard's domain.
        ("dependabot/npm_and_yarn/x-1.2.3", ("dependabot[bot]",), ("Lucas Ferreira",)),
    )

    def _all_cases(self):
        """`CASES` (allowed-before) + `BLOCKING_CASES` (blocked-before)."""
        return [(head_ref, authors, self.THREAD) for head_ref, authors in self.CASES] + list(
            self.BLOCKING_CASES
        )

    @staticmethod
    def _gate_allows(verdicts) -> bool:
        """`check()`'s OWN allow-condition, transcribed — not a proxy for it.

        Mirrors the `total_distinct == 1 and wave_bootstrap_exception` /
        `total_distinct < 2` ladder in `check()`. Spelling it out here keeps
        "allowed" meaning what the gate means by it, so the property below is
        about the merge decision rather than about a count that resembles one.
        """
        return verdicts.total_distinct >= 2 or (
            verdicts.total_distinct == 1 and verdicts.wave_bootstrap_exception
        )

    def _sets(self, head_ref: str, authors: tuple[str, ...], thread: tuple[str, ...] | None = None):
        commits = [
            _api_commit(f"c{n}", "2026-07-15T19:13:59Z", author_name=name)
            for n, name in enumerate(authors)
        ]
        comments = [self._verdict(name) for name in (self.THREAD if thread is None else thread)]
        after = self._resolve(head_ref, comments, commits=commits)
        # "Before" == the same pipeline with the commit-derived author source
        # switched off, which is exactly the pre-#1210 code path.
        with mock.patch.object(hook, "commit_author_identities", return_value=()):
            before = self._resolve(head_ref, comments, commits=commits)
        return before, after

    def test_reviewer_set_never_grows(self):
        for head_ref, authors, thread in self._all_cases():
            with self.subTest(head_ref=head_ref, authors=authors, thread=thread):
                before, after = self._sets(head_ref, authors, thread=thread)
                self.assertTrue(
                    after.distinct_reviewers <= before.distinct_reviewers,
                    f"{after.distinct_reviewers} is not a subset of {before.distinct_reviewers}",
                )
                self.assertLessEqual(after.total_distinct, before.total_distinct)

    def test_fixture_is_not_vacuous_at_least_one_case_actually_shrinks(self):
        """Guards the subset property against passing because nothing changed.

        A no-op implementation satisfies `after <= before` for every case. At
        least one case must strictly shrink, or the class above certifies
        nothing (`feedback_fixture_makes_guard_assertion_inert`).
        """
        shrank = [
            (head_ref, authors)
            for head_ref, authors in self.CASES
            if self._sets(head_ref, authors)[1].distinct_reviewers
            < self._sets(head_ref, authors)[0].distinct_reviewers
        ]
        self.assertTrue(shrank, "no case exercised the exclusion — the matrix proves nothing")

    def test_a_blocked_pr_never_becomes_an_allowed_one(self):
        """The property expressed as the gate's own verdict, not as a count.

        Scope, stated honestly so nobody reads more into a green run than is
        there: on the CURRENT pipeline no input can actually flip blocked ->
        allowed, because `after` is a subset of `before` and a blocked `before`
        is already at most 1. That was measured, not assumed — the fail-open
        mutant that unifies the two author sources (drop the `() if
        branch_author_lastname` guard in `resolve_review_verdicts`, then let the
        commit arm of `is_self_review` supersede the ref arm) is caught by
        `test_reviewer_set_never_grows`, and this test correctly stays green
        because the mutant only loses the exclusion, it does not push a blocked
        PR over the bar. So the sibling subset test is the load-bearing one;
        this is the TRIPWIRE for a future change that could ADD a reviewer to a
        blocked PR, and its value depends entirely on the guard body actually
        executing — which the anti-vacuity assertions at the bottom enforce.
        """
        reached = []
        for head_ref, authors, thread in self._all_cases():
            with self.subTest(head_ref=head_ref, authors=authors, thread=thread):
                before, after = self._sets(head_ref, authors, thread=thread)
                if self._gate_allows(before):
                    continue
                reached.append((head_ref, authors, thread))
                self.assertFalse(
                    self._gate_allows(after),
                    "a PR the gate blocked before #1210 must not now pass",
                )
        # Anti-vacuity, same discipline as the sibling test above: the guard is
        # inside an `if`, so a matrix in which nothing is blocked-before makes
        # the whole test a no-op that still reports green.
        #
        # BOTH assertions are load-bearing and the order matters. `assertEqual`
        # alone is NOT enough: emptying `BLOCKING_CASES` degrades it to
        # `assertEqual([], [])`, which passes — i.e. deleting the blocking
        # matrix silently restores the exact #1203 inertness this test was
        # rewritten to remove. (Measured, not assumed: emptying the tuple with
        # only the `assertEqual` present left this test green.) `assertTrue`
        # pins the floor — the guard ran at all — and `assertEqual` then pins
        # WHICH cases reached it, catching both a blocking case that quietly
        # stops blocking and a `CASES` entry that starts.
        self.assertTrue(
            reached,
            "no case in the matrix started from a BLOCKED state, so the guard body never "
            "executed — this test would pass under a no-op implementation (#1203)",
        )
        self.assertEqual(
            reached,
            list(self.BLOCKING_CASES),
            "the blocked-before guard did not execute over exactly the blocking matrix — "
            "the property this test is named for was not actually checked",
        )


class SelfReviewExclusionKeepsTechDebtBlockTests(_ResolveOverFakeCommentsHarness):
    """M13: the #1210 exclusion must not swallow the missing-TechDebt block.

    In `check_comment_reviews` the self-review exclusion and the TechDebt
    attestation check are two INDEPENDENT `if is_verdict_comment:` blocks, and
    the non-relaxing argument for #1210 leans on that independence: the
    exclusion may only ever remove a name from the reviewer SET, never relieve
    a verdict of its attestation. Nothing pinned it. Moving the TechDebt block
    inside the `if not is_self_review(...)` branch left the entire suite green
    while a BLOCK turned into a PASS — the sole survivor of Nino Kavtaradze's
    15-mutation run on this PR.

    The transition is real, not theoretical: `check()` reaches the TechDebt
    gate only AFTER clearing the 2-reviewer gate, so a PR with two clean
    approvals plus the branch author's own attestation-less verdict is blocked
    today and merges under the mutant.
    """

    HEAD_REF = "feature/hand-made"  # names no persona — commits are the ONLY author source
    AUTHOR = "Aino Virtanen"

    @staticmethod
    def _verdict_without_tech_debt(requestor: str) -> dict:
        """A well-formed Approved verdict carrying NO `TechDebt:` line."""
        return {
            "body": (
                f"Requestor: {requestor}\nRequestee: Someone Else\nRequestOrReplied: Approved"
            ),
            "created_at": "2026-07-20T00:00:00Z",
        }

    def _comments(self) -> list[dict]:
        # Two clean approvals clear the 2-reviewer gate, so the ONLY thing that
        # can still block is the branch author's missing attestation.
        return [
            self._verdict("Lucas Ferreira"),
            self._verdict("Nino Kavtaradze"),
            self._verdict_without_tech_debt(self.AUTHOR),
        ]

    def _commits(self) -> list[dict]:
        return [_api_commit("c0", "2026-07-15T19:13:59Z", author_name=self.AUTHOR)]

    def test_branch_authors_own_verdict_is_excluded_but_still_owes_tech_debt(self):
        """The two effects are independent: dropped from the set, still attesting."""
        verdicts = self._resolve(self.HEAD_REF, self._comments(), commits=self._commits())
        # Excluded from the reviewer set — the #1210 behaviour, unchanged.
        self.assertEqual(
            verdicts.distinct_reviewers,
            {"lucas ferreira", "nino kavtaradze"},
            "author not excluded",
        )
        self.assertEqual(verdicts.total_distinct, 2)
        # ...and STILL on the hook for the attestation. This is the assertion
        # the mutant kills.
        self.assertEqual(verdicts.reviews_missing_tech_debt, [self.AUTHOR])

    def test_check_still_blocks_the_merge_on_the_authors_missing_attestation(self):
        """The same property as a merge decision — a BLOCK the mutant turns into a PASS."""
        input_data = {
            "tool_name": "Bash",
            "tool_input": {"command": "gh pr merge 691 --repo noorinalabs/noorinalabs-main"},
        }
        comments, commits = self._comments(), self._commits()

        def fake_run(args, capture_output, text, timeout):  # noqa: ARG001
            result = mock.MagicMock()
            result.returncode = 0
            if args[0] == "gh" and args[1:3] == ["repo", "view"]:
                result.stdout = json.dumps({"owner": {"login": "noorinalabs"}, "name": "r"})
            else:
                result.stdout = json.dumps(comments)
            return result

        with (
            mock.patch.object(hook.subprocess, "run", side_effect=fake_run),
            mock.patch.object(hook, "fetch_pr_commits", return_value=commits),
            mock.patch.object(hook, "_load_roster_names", return_value=set(self.ROSTER)),
            mock.patch.object(hook, "get_pr_data", return_value=self._pr_data(self.HEAD_REF)),
            mock.patch.object(hook, "log_pretooluse_block"),
        ):
            result = hook.check(input_data)

        assert result is not None, (
            "check() returned None — the merge was ALLOWED despite the branch author's "
            "verdict carrying no TechDebt line (the M13 mutant's signature)"
        )
        self.assertEqual(result["decision"], "block")
        reason = str(result["reason"])
        # Pin the REASON too: blocking for some unrelated cause (a reviewer
        # shortfall, say) would satisfy a bare `decision == "block"` while the
        # attestation check was in fact suppressed.
        self.assertIn("TechDebt: attestation line", reason)
        self.assertIn(self.AUTHOR, reason)


class CommitAuthorBlockDiagnosticTests(_ResolveOverFakeCommentsHarness):
    """A subtraction the operator cannot see is a tool that looks broken (#950)."""

    def _block_reason(self, verdicts) -> str:
        input_data = {
            "tool_name": "Bash",
            "tool_input": {"command": "gh pr merge 691 --repo noorinalabs/noorinalabs-main"},
        }
        with (
            mock.patch.object(hook, "get_pr_data", return_value=self._pr_data("feature/x")),
            mock.patch.object(hook, "resolve_review_verdicts", return_value=verdicts),
            mock.patch.object(hook, "log_pretooluse_block"),
        ):
            result = hook.check(input_data)
        assert result is not None, "check() must BLOCK a 1/2 PR, not return None"
        self.assertEqual(result["decision"], "block")
        return str(result["reason"])

    @staticmethod
    def _verdicts(comment_scan: str, identities=()):
        return hook.ReviewVerdicts(
            number=691,
            head_ref="feature/x",
            labels=[],
            branch_author_lastname=None,
            content_sha="837c272a",
            content_ts=None,
            formal_reviewers=set(),
            comment_reviewers={"aino virtanen"},
            non_roster_requestors=set(),
            roster_comment_reviewers={"aino virtanen"},
            roster_names={"aino virtanen"},
            distinct_reviewers={"aino virtanen"},
            stale_verdicts_comment=[],
            stale_verdicts_formal=[],
            reviews_missing_tech_debt=[],
            tech_debt_issue_numbers=[],
            tech_debt_unparseable=[],
            wave_bootstrap_exception=False,
            comment_scan=comment_scan,
            commit_author_identities=identities,
        )

    def test_block_message_names_the_commit_derived_author(self):
        reason = self._block_reason(
            self._verdicts(
                hook.COMMENT_SCAN_COMMIT_AUTHOR_EXCLUDED,
                (
                    hook.CommitAuthorIdentity(
                        lastname="Kavtaradze", initial="n", display="Nino Kavtaradze"
                    ),
                ),
            )
        )
        self.assertIn("COMMIT IDENTITY", reason)
        self.assertIn("Nino Kavtaradze", reason)
        self.assertIn("1/2 required peer reviews", reason)

    def test_the_two_no_author_modes_read_differently(self):
        """Exclusion-applied and exclusion-unavailable must not share wording —
        they are opposite facts about whether the count can be trusted."""
        excluded = self._block_reason(
            self._verdicts(
                hook.COMMENT_SCAN_COMMIT_AUTHOR_EXCLUDED,
                (
                    hook.CommitAuthorIdentity(
                        lastname="Khoury", initial="n", display="Nadia Khoury"
                    ),
                ),
            )
        )
        unavailable = self._block_reason(self._verdicts(hook.COMMENT_SCAN_NO_BRANCH_AUTHOR))
        self.assertNotEqual(excluded, unavailable)
        self.assertIn("COMMIT IDENTITY", excluded)
        self.assertNotIn("COMMIT IDENTITY", unavailable)
        self.assertIn("WITHOUT self-review exclusion", unavailable)
        self.assertNotIn("WITHOUT self-review exclusion", excluded)

    BOT = hook.CommitAuthorIdentity(
        lastname="dependabot[bot]", initial="d", display="dependabot[bot]"
    )

    def test_non_roster_derivation_does_not_claim_a_subtraction(self):
        """#1220 at the block surface.

        Pre-fix this input produced the COMMIT_AUTHOR_EXCLUDED text, which told
        the operator "Verdicts from those personas were excluded as self-reviews"
        on a PR where nothing had been excluded — sending them to look for a
        dropped verdict that never existed.
        """
        reason = self._block_reason(
            self._verdicts(hook.COMMENT_SCAN_COMMIT_AUTHOR_NON_ROSTER, (self.BOT,))
        )
        # Still NAMES the derivation — it is what an operator would audit if
        # they suspected the wrong person had been picked.
        self.assertIn("COMMIT IDENTITY", reason)
        self.assertIn("dependabot[bot]", reason)
        # And states the fact the old message got wrong.
        self.assertIn("matches no roster persona", reason)
        self.assertIn("NO verdict was excluded as a self-review", reason)
        # The false claim must be gone, not merely joined by a true one.
        self.assertNotIn("is excluded as a self-review;", reason)
        # The count itself is untouched by the mode (this is a description fix).
        self.assertIn("1/2 required peer reviews", reason)

    def test_inert_and_live_commit_derivations_read_differently(self):
        """The two commit-derived modes make OPPOSITE claims about whether a
        verdict was subtracted, so sharing wording would restore exactly the
        ambiguity #1220 removed. Both name the derivation; only one asserts an
        exclusion."""
        live = self._block_reason(
            self._verdicts(
                hook.COMMENT_SCAN_COMMIT_AUTHOR_EXCLUDED,
                (
                    hook.CommitAuthorIdentity(
                        lastname="Kavtaradze", initial="n", display="Nino Kavtaradze"
                    ),
                ),
            )
        )
        inert = self._block_reason(
            self._verdicts(hook.COMMENT_SCAN_COMMIT_AUTHOR_NON_ROSTER, (self.BOT,))
        )
        self.assertNotEqual(live, inert)
        self.assertIn("is excluded as a self-review", live)
        self.assertNotIn("matches no roster persona", live)
        self.assertIn("matches no roster persona", inert)

    def test_inert_mode_is_not_collapsed_into_the_no_author_wording(self):
        """It must not borrow NO_BRANCH_AUTHOR's text either: that mode's claim
        is "the PR's commits named no persona", and here they named one."""
        inert = self._block_reason(
            self._verdicts(hook.COMMENT_SCAN_COMMIT_AUTHOR_NON_ROSTER, (self.BOT,))
        )
        no_author = self._block_reason(self._verdicts(hook.COMMENT_SCAN_NO_BRANCH_AUTHOR))
        self.assertNotEqual(inert, no_author)
        self.assertIn("commits named no persona either", no_author)
        self.assertNotIn("commits named no persona either", inert)

    def test_wave_integration_block_states_the_short_count_is_not_a_subtraction(self):
        """#1216 at the block surface.

        An operator reading `1/2` on a wave-merge PR must be able to tell,
        without opening the hook, that the gate dropped nobody — and must be
        pointed at the merge path the charter actually prescribes for this PR
        class rather than sent to hunt for a missing approval.
        """
        reason = self._block_reason(self._verdicts(hook.COMMENT_SCAN_WAVE_INTEGRATION))
        self.assertIn("wave->main INTEGRATION PR", reason)
        self.assertIn("no self-review exclusion was applied", reason)
        self.assertIn("nothing was subtracted", reason)
        self.assertIn("wave-merge:<rationale>", reason)
        self.assertIn("1/2 required peer reviews", reason)
        # The claim that would be FALSE here, and that NO_BRANCH_AUTHOR makes.
        self.assertNotIn("commits named no persona either", reason)
        # And it must not announce a derivation it deliberately did not perform.
        self.assertNotIn("COMMIT IDENTITY", reason)

    def test_wave_integration_reads_differently_from_every_other_mode(self):
        """Five modes, five block texts. Two that collapse cannot be told apart
        by the reader, which is the entire reason the enum exists (#1273)."""
        rendered = {
            hook.COMMENT_SCAN_WAVE_INTEGRATION: self._block_reason(
                self._verdicts(hook.COMMENT_SCAN_WAVE_INTEGRATION)
            ),
            hook.COMMENT_SCAN_NO_BRANCH_AUTHOR: self._block_reason(
                self._verdicts(hook.COMMENT_SCAN_NO_BRANCH_AUTHOR)
            ),
            hook.COMMENT_SCAN_COMMIT_AUTHOR_NON_ROSTER: self._block_reason(
                self._verdicts(hook.COMMENT_SCAN_COMMIT_AUTHOR_NON_ROSTER, (self.BOT,))
            ),
            hook.COMMENT_SCAN_COMMIT_AUTHOR_EXCLUDED: self._block_reason(
                self._verdicts(hook.COMMENT_SCAN_COMMIT_AUTHOR_EXCLUDED, (self.BOT,))
            ),
        }
        self.assertEqual(
            len(set(rendered.values())), len(rendered), f"collapsed block texts: {rendered}"
        )


class AllowPathScanDisclosureTests(_ResolveOverFakeCommentsHarness):
    """#1211: the ALLOW path must say when self-review exclusion was unavailable.

    #1206/#1210 made the scan mode loud on the paths that STOP a merge — the
    paths where the missing discriminator did not change the outcome. The
    exposure only bites when the gate PASSES: a persona's own verdict plus one
    genuine reviewer reaches 2/2 on a ref naming nobody, and pre-#1211 the hook
    returned `None` and said nothing. These pin that the disclosure now rides
    the allow path, that it does NOT fire when exclusion was actually applied,
    and — the case a naive fix silently breaks — that it COMPOSES with the
    main#1055 unparseable-TechDebt advisory instead of racing it.
    """

    HEAD_REF = "dependabot/docker/x-1.2.3"

    def _allow_result(self, verdicts, head_ref=None):
        input_data = {
            "tool_name": "Bash",
            "tool_input": {"command": "gh pr merge 691 --repo noorinalabs/noorinalabs-main"},
        }
        with (
            mock.patch.object(
                hook, "get_pr_data", return_value=self._pr_data(head_ref or self.HEAD_REF)
            ),
            mock.patch.object(hook, "resolve_review_verdicts", return_value=verdicts),
            mock.patch.object(hook, "log_pretooluse_block") as mock_log,
        ):
            result = hook.check(input_data)
        # A merge that passes the threshold must never be logged as a block, no
        # matter how many advisories rode along with it.
        mock_log.assert_not_called()
        return result

    def _verdicts(self, comment_scan, *, unparseable=(), identities=(), head_ref=None):
        """Two distinct roster reviewers, nothing missing — a clean 2/2 ALLOW.

        Only `comment_scan` / `tech_debt_unparseable` vary, so any difference in
        the returned message is attributable to those and nothing else.
        """
        return hook.ReviewVerdicts(
            number=691,
            head_ref=head_ref or self.HEAD_REF,
            labels=[],
            branch_author_lastname=None,
            content_sha="837c272a",
            content_ts=None,
            formal_reviewers=set(),
            comment_reviewers={"aino virtanen", "nino kavtaradze"},
            non_roster_requestors=set(),
            roster_comment_reviewers={"aino virtanen", "nino kavtaradze"},
            roster_names=set(self.ROSTER),
            distinct_reviewers={"aino virtanen", "nino kavtaradze"},
            stale_verdicts_comment=[],
            stale_verdicts_formal=[],
            reviews_missing_tech_debt=[],
            tech_debt_issue_numbers=[],
            tech_debt_unparseable=list(unparseable),
            wave_bootstrap_exception=False,
            comment_scan=comment_scan,
            commit_author_identities=identities,
        )

    def test_allowed_merge_discloses_that_exclusion_was_unavailable(self):
        """The core #1211 fix: a passing gate on a no-branch-author ref must
        return an ALLOW carrying the disclosure, not a bare `None`.

        Pre-fix this returned `None` — the `assertIsNotNone` alone is the
        kill-shot, and the content assertions pin WHAT is disclosed so a future
        edit cannot satisfy the test with an empty or unrelated message.
        """
        result = self._allow_result(self._verdicts(hook.COMMENT_SCAN_NO_BRANCH_AUTHOR))

        self.assertIsNotNone(
            result, "an allowed merge with no self-review exclusion must disclose that"
        )
        assert result is not None  # narrow `dict | None` for mypy
        self.assertEqual(result["decision"], "allow", "the disclosure must NOT block the merge")
        message = result["systemMessage"]
        # Names the ref, so the operator can check the classification themselves.
        self.assertIn(self.HEAD_REF, message)
        # States the fact that matters: no verdict was excluded as a self-review.
        self.assertIn("WITHOUT self-review exclusion", message)
        self.assertIn("including any posted by whoever wrote this branch", message)
        # Reports the count the missing discriminator applied to.
        self.assertIn("2/2", message)
        # Proportionate: an advisory, not a verdict on the PR's validity.
        self.assertNotIn("BLOCKED", message)
        self.assertNotIn("WARNING", message)

    def test_exclusion_applied_modes_stay_silent_on_the_allow_path(self):
        """The negative control the positive test cannot supply on its own.

        Applying exclusion can only REMOVE verdicts, so it can never manufacture
        a pass — there is nothing to disclose. Both exclusion-active modes must
        return `None`, so a change that emitted the note unconditionally fails
        here just as loudly as one that emitted it never.
        """
        by_ref = self._allow_result(
            self._verdicts(hook.COMMENT_SCAN_AUTHOR_EXCLUDED, head_ref="A.Virtanen/1211-x"),
            head_ref="A.Virtanen/1211-x",
        )
        by_commit = self._allow_result(
            self._verdicts(
                hook.COMMENT_SCAN_COMMIT_AUTHOR_EXCLUDED,
                identities=(
                    hook.CommitAuthorIdentity(
                        lastname="Virtanen", initial="a", display="Aino Virtanen"
                    ),
                ),
            )
        )
        self.assertIsNone(by_ref, "ref-derived exclusion was applied — nothing to disclose")
        self.assertIsNone(by_commit, "commit-derived exclusion was applied — nothing to disclose")

    def test_wave_integration_allow_discloses_that_an_implementer_may_have_counted(self):
        """#1216 at the surface that matters most: the merge is ALLOWED.

        The whole risk of the carve-out is that a counted approval came from
        someone whose work is in the branch. That is permitted, so the gate does
        not block — but a reader who cannot see it happened cannot audit it, and
        an undisclosed relaxation is the shape this advisory path was built for
        (#1211).
        """
        wave_ref = "deployments/phase-10/wave-29"
        result = self._allow_result(
            self._verdicts(hook.COMMENT_SCAN_WAVE_INTEGRATION, head_ref=wave_ref),
            head_ref=wave_ref,
        )
        assert result is not None, "an allowed wave-integration merge must disclose the carve-out"
        self.assertEqual(result["decision"], "allow")
        message = result["systemMessage"]
        self.assertIn(wave_ref, message)
        self.assertIn("WITHOUT self-review exclusion", message)
        self.assertIn("wave->main INTEGRATION PR", message)
        self.assertIn("their integration verdict counts", message)
        self.assertIn("No verdict was subtracted", message)
        # The count is interpolated, never a literal — a hardcoded `2/2` here
        # survived all 318 tests once (#1292), so it is asserted as a fact about
        # THIS fixture's two reviewers rather than as a constant.
        self.assertIn("2/2", message)
        # The false claim NO_BRANCH_AUTHOR makes and this mode must not borrow.
        self.assertNotIn("commits named no roster persona either", message)
        self.assertNotIn("BLOCKED", message)

    def test_wave_integration_advisory_reports_a_one_of_two_count_honestly(self):
        """Anti-hardcode control for the `2/2` above.

        The wave-bootstrap exception can allow at 1/2, and a literal count in
        the advisory would misreport exactly the PR with the fewest reviewers to
        lose. Same mode, one reviewer, exception on.
        """
        wave_ref = "deployments/phase-10/wave-29"
        verdicts = dataclasses.replace(
            self._verdicts(hook.COMMENT_SCAN_WAVE_INTEGRATION, head_ref=wave_ref),
            comment_reviewers={"aino virtanen"},
            roster_comment_reviewers={"aino virtanen"},
            distinct_reviewers={"aino virtanen"},
            wave_bootstrap_exception=True,
        )
        result = self._allow_result(verdicts, head_ref=wave_ref)
        assert result is not None
        self.assertEqual(result["decision"], "allow")
        self.assertIn("1/2", result["systemMessage"])
        self.assertNotIn("2/2", result["systemMessage"])

    def test_both_advisories_survive_when_both_conditions_hold(self):
        """THE composition test — the case a second early `return` breaks.

        `check()` may emit exactly one `systemMessage`. main#1055's
        unparseable-TechDebt note and #1211's scan disclosure are independent
        facts that can both be true of one PR, so bolting the new advisory on as
        its own early return would make whichever ran first silently swallow the
        other. Both texts must appear in the single returned message.
        """
        result = self._allow_result(
            self._verdicts(
                hook.COMMENT_SCAN_NO_BRANCH_AUTHOR,
                unparseable=[("Nino Kavtaradze", "filed later")],
            )
        )

        assert result is not None, "both advisories must produce a message"
        self.assertEqual(result["decision"], "allow")
        message = result["systemMessage"]
        # main#1055 advisory survived, verbatim payload included.
        self.assertIn("not parseable as issue reference(s)", message)
        self.assertIn("filed later", message)
        self.assertIn("Nino Kavtaradze", message)
        # #1211 advisory survived alongside it.
        self.assertIn("WITHOUT self-review exclusion", message)
        self.assertIn(self.HEAD_REF, message)
        # Two distinct advisories, joined — not one truncated or overwritten.
        self.assertEqual(message.count("NOTE: PR"), 2, f"expected 2 joined advisories: {message!r}")

    def test_each_advisory_still_stands_alone(self):
        """Composition must not have made either advisory depend on the other.

        The TechDebt note must be emitted with the scan mode exclusion-active
        (so only it fires), and its text must be exactly what it was before the
        accumulator — pinning that #1211 refactored the return shape without
        rewording main#1055's message.
        """
        td_only = self._allow_result(
            self._verdicts(
                hook.COMMENT_SCAN_AUTHOR_EXCLUDED,
                unparseable=[("Nino Kavtaradze", "filed later")],
                head_ref="A.Virtanen/1211-x",
            ),
            head_ref="A.Virtanen/1211-x",
        )
        assert td_only is not None, "main#1055 advisory must still fire on its own"
        self.assertEqual(td_only["decision"], "allow")
        self.assertIn("filed later", td_only["systemMessage"])
        self.assertEqual(td_only["systemMessage"].count("NOTE: PR"), 1)
        self.assertNotIn("self-review exclusion", td_only["systemMessage"])

        scan_only = self._allow_result(self._verdicts(hook.COMMENT_SCAN_NO_BRANCH_AUTHOR))
        assert scan_only is not None, "#1211 advisory must still fire on its own"
        self.assertEqual(scan_only["systemMessage"].count("NOTE: PR"), 1)
        self.assertNotIn("filed later", scan_only["systemMessage"])

    def test_clean_pr_still_returns_none(self):
        """No advisory condition, no message. The accumulator must not have
        turned every allowed merge into a chatty one — `None` is the contract
        `main()` reads as 'exit 0, say nothing'."""
        self.assertIsNone(
            self._allow_result(
                self._verdicts(hook.COMMENT_SCAN_AUTHOR_EXCLUDED, head_ref="A.Virtanen/1211-x"),
                head_ref="A.Virtanen/1211-x",
            )
        )

    def test_disclosure_never_relaxes_or_tightens_the_gate(self):
        """The advisory is orthogonal to the decision (#1211's stated scope).

        Same NO_BRANCH_AUTHOR ref, two counts: 1/2 must still BLOCK and 2/2 must
        still ALLOW. Without this, a disclosure implemented as a `decision` key
        on the wrong branch could pass every content assertion above while
        letting a 1/2 PR through.
        """
        short = self._verdicts(hook.COMMENT_SCAN_NO_BRANCH_AUTHOR)
        short.distinct_reviewers = {"aino virtanen"}
        input_data = {
            "tool_name": "Bash",
            "tool_input": {"command": "gh pr merge 691 --repo noorinalabs/noorinalabs-main"},
        }
        with (
            mock.patch.object(hook, "get_pr_data", return_value=self._pr_data(self.HEAD_REF)),
            mock.patch.object(hook, "resolve_review_verdicts", return_value=short),
            mock.patch.object(hook, "log_pretooluse_block"),
        ):
            blocked = hook.check(input_data)
        assert blocked is not None
        self.assertEqual(blocked["decision"], "block")
        self.assertIn("1/2 required peer reviews", blocked["reason"])

        allowed = self._allow_result(self._verdicts(hook.COMMENT_SCAN_NO_BRANCH_AUTHOR))
        assert allowed is not None
        self.assertEqual(allowed["decision"], "allow")

    BOT_IDENTITY = (
        hook.CommitAuthorIdentity(
            lastname="dependabot[bot]", initial="d", display="dependabot[bot]"
        ),
    )

    def test_inert_commit_derivation_also_discloses_on_the_allow_path(self):
        """#1220 extends #1211's disclosure to the mode it split off.

        COMMIT_AUTHOR_NON_ROSTER produces a reviewer set byte-identical to
        NO_BRANCH_AUTHOR's — no verdict was excluded in either — so the #1211
        exposure is identical and the disclosure must fire. Pre-#1220 this input
        was labelled COMMIT_AUTHOR_EXCLUDED and the advisory stayed SILENT on it,
        i.e. the gate skipped the disclosure on the strength of a subtraction it
        had not performed.
        """
        result = self._allow_result(
            self._verdicts(hook.COMMENT_SCAN_COMMIT_AUTHOR_NON_ROSTER, identities=self.BOT_IDENTITY)
        )
        assert result is not None, "an inert derivation excluded nothing — that must be disclosed"
        self.assertEqual(result["decision"], "allow")
        message = result["systemMessage"]
        self.assertIn("WITHOUT self-review exclusion", message)
        self.assertIn("dependabot[bot]", message)
        self.assertIn("matches no roster persona", message)
        self.assertIn(self.HEAD_REF, message)
        self.assertIn("2/2", message)
        self.assertNotIn("BLOCKED", message)

    def test_the_two_no_exclusion_advisories_are_not_the_same_text(self):
        """Both disclose "nothing was excluded" and they do so for different
        reasons — one because nobody was derivable, one because the person
        derived is not a roster persona. A reader has to be able to tell which,
        because only the second one names an identity worth auditing."""
        derived = self._allow_result(
            self._verdicts(hook.COMMENT_SCAN_COMMIT_AUTHOR_NON_ROSTER, identities=self.BOT_IDENTITY)
        )
        none_derived = self._allow_result(self._verdicts(hook.COMMENT_SCAN_NO_BRANCH_AUTHOR))
        assert derived is not None and none_derived is not None
        self.assertNotEqual(derived["systemMessage"], none_derived["systemMessage"])
        self.assertIn("COMMIT IDENTITY", derived["systemMessage"])
        self.assertNotIn("COMMIT IDENTITY", none_derived["systemMessage"])
        # Exactly one advisory each — the new branch must not double-emit.
        self.assertEqual(derived["systemMessage"].count("NOTE: PR"), 1)
        self.assertEqual(none_derived["systemMessage"].count("NOTE: PR"), 1)

    def test_advisory_reports_the_real_count_on_a_wave_bootstrap_single_reviewer(self):
        """The allow tail is reachable at 1/2, and the count must not be a literal.

        `check()` allows a 1/2 PR through the wave-bootstrap single-reviewer
        exception, so this advisory can fire on a PR with ONE reviewer. Every
        pre-existing test here supplies a 2/2 fixture, which is why hardcoding
        the count to `2/2` survived the whole suite — found by Nadia Khoury
        reviewing #1270. Both no-exclusion modes are checked, so neither branch
        can regress to a literal.
        """
        for mode, identities in (
            (hook.COMMENT_SCAN_NO_BRANCH_AUTHOR, ()),
            (hook.COMMENT_SCAN_COMMIT_AUTHOR_NON_ROSTER, self.BOT_IDENTITY),
        ):
            with self.subTest(mode=mode):
                verdicts = self._verdicts(mode, identities=identities)
                verdicts.distinct_reviewers = {"aino virtanen"}
                verdicts.wave_bootstrap_exception = True
                result = self._allow_result(verdicts)
                assert result is not None, "the disclosure must ride the bootstrap allow too"
                self.assertEqual(result["decision"], "allow")
                message = result["systemMessage"]
                self.assertIn("reached 1/2 WITHOUT self-review exclusion", message)
                self.assertNotIn("2/2", message)


class CommentScanModeTotalityTests(unittest.TestCase):
    """Every COMMENT_SCAN_* mode must be WIRED on every surface that renders it.

    #1273: the enum is rendered by three independent hand-written surfaces —
    `check()`'s block `scan_diagnostic`, `check()`'s allow-path advisory, and
    `pr_review_state._describe_comment_scan` — and nothing pinned that a new
    mode reached all three. #1220 added a fifth mode, which is exactly the event
    that would have exercised the gap, so the pin lands with it.

    The coverage table below is DELIBERATE, not derived: a mode's absence from a
    surface is a decision (AUTHOR_EXCLUDED needs no block diagnostic — the ref
    names the author, nothing is surprising), and the `_TABLE` equality guard
    makes adding a sixth mode fail here until someone records that decision.
    """

    # mode -> (block diagnostic expected?, allow advisory expected?)
    _TABLE = {
        # The scan never ran: the block path must SHOUT, and the allow path is
        # unreachable (`resolve_review_verdicts` hard-blocks upstream).
        hook.COMMENT_SCAN_NOT_RUN: (True, False),
        # Nothing excluded, nobody derived: both surfaces disclose (#1206/#1211).
        hook.COMMENT_SCAN_NO_BRANCH_AUTHOR: (True, True),
        # Nothing excluded BY POLICY on a wave->main integration PR: both
        # surfaces disclose (#1216). The block path must say the short count is
        # not a subtraction (and point at the `wave-merge` admin exception); the
        # allow path must say a counted approval may be an implementer's. This
        # is the one mode where the reader could otherwise reasonably assume the
        # gate had dropped someone.
        hook.COMMENT_SCAN_WAVE_INTEGRATION: (True, True),
        # Nothing excluded, someone derived: both surfaces disclose (#1220).
        hook.COMMENT_SCAN_COMMIT_AUTHOR_NON_ROSTER: (True, True),
        # Exclusion applied on commit evidence: block names the subtraction; the
        # allow path stays silent because exclusion can only remove verdicts and
        # so can never manufacture a pass (#1210/#1211).
        hook.COMMENT_SCAN_COMMIT_AUTHOR_EXCLUDED: (True, False),
        # Exclusion applied on the ref the human declared: nothing surprising to
        # report on either surface.
        hook.COMMENT_SCAN_AUTHOR_EXCLUDED: (False, False),
    }

    UNRECOGNIZED = "UNRECOGNIZED SCAN MODE"

    def test_table_covers_exactly_the_declared_mode_set(self):
        """The guard that makes every other test in this class total.

        Without it, adding a sixth constant would leave the loops below iterating
        five modes and passing — the vacuity #1215 is about.
        """
        self.assertEqual(set(self._TABLE), set(hook.ALL_COMMENT_SCAN_MODES))
        self.assertEqual(
            len(hook.ALL_COMMENT_SCAN_MODES),
            len(set(hook.ALL_COMMENT_SCAN_MODES)),
            "ALL_COMMENT_SCAN_MODES must not contain duplicates",
        )

    @staticmethod
    def _verdicts(comment_scan, *, reviewers):
        return hook.ReviewVerdicts(
            number=691,
            head_ref="dependabot/docker/x-1.2.3",
            labels=[],
            branch_author_lastname=None,
            content_sha="837c272a",
            content_ts=None,
            formal_reviewers=set(),
            comment_reviewers=set(reviewers),
            non_roster_requestors=set(),
            roster_comment_reviewers=set(reviewers),
            roster_names={"aino virtanen", "nino kavtaradze"},
            distinct_reviewers=set(reviewers),
            stale_verdicts_comment=[],
            stale_verdicts_formal=[],
            reviews_missing_tech_debt=[],
            tech_debt_issue_numbers=[],
            tech_debt_unparseable=[],
            wave_bootstrap_exception=False,
            comment_scan=comment_scan,
            commit_author_identities=(
                hook.CommitAuthorIdentity(
                    lastname="dependabot[bot]", initial="d", display="dependabot[bot]"
                ),
            ),
        )

    def _check(self, comment_scan, *, reviewers):
        input_data = {
            "tool_name": "Bash",
            "tool_input": {"command": "gh pr merge 691 --repo noorinalabs/noorinalabs-main"},
        }
        with (
            mock.patch.object(
                hook,
                "get_pr_data",
                return_value={
                    "author": "parametrization",
                    "number": 691,
                    "reviews": [],
                    "headRefName": "dependabot/docker/x-1.2.3",
                    "labels": [],
                },
            ),
            mock.patch.object(
                hook,
                "resolve_review_verdicts",
                return_value=self._verdicts(comment_scan, reviewers=reviewers),
            ),
            mock.patch.object(hook, "log_pretooluse_block"),
        ):
            return hook.check(input_data)

    def test_every_mode_gets_its_declared_block_diagnostic(self):
        """A mode with no block branch renders a bare count — the pre-#1206
        state, where a number with no provenance read as a measurement."""
        for mode, (wants_block, _) in self._TABLE.items():
            with self.subTest(mode=mode):
                result = self._check(mode, reviewers={"aino virtanen"})
                assert result is not None
                reason = str(result["reason"])
                # The generic 2-reviewer body is always present; the scan
                # diagnostic is the prefix that precedes it.
                prefix = reason.split("BLOCKED: PR #691 has 1/2 required peer reviews")[0]
                if wants_block:
                    self.assertTrue(
                        prefix.strip(), f"{mode} renders no block scan diagnostic at all"
                    )
                    self.assertIn(
                        "scan",
                        prefix.lower(),
                        f"{mode}'s block diagnostic never mentions the scan",
                    )
                else:
                    self.assertEqual(prefix, "", f"{mode} unexpectedly renders a block diagnostic")

    def test_every_mode_matches_its_declared_allow_advisory_coverage(self):
        for mode, (_, wants_advisory) in self._TABLE.items():
            with self.subTest(mode=mode):
                result = self._check(mode, reviewers={"aino virtanen", "nino kavtaradze"})
                if wants_advisory:
                    assert result is not None, f"{mode} must disclose on the allow path"
                    self.assertEqual(result["decision"], "allow")
                    self.assertIn("self-review exclusion", result["systemMessage"])
                else:
                    self.assertIsNone(result, f"{mode} must stay silent on the allow path")

    def test_every_mode_renders_a_recognized_report_line(self):
        """`pr_review_state._describe_comment_scan` used to end in a bare
        `return` on NO_BRANCH_AUTHOR's text, so an unwired mode was described as
        "the PR's commits named no persona" — confident, specific, wrong. The
        fallback now says UNRECOGNIZED; no declared mode may reach it."""
        for mode in hook.ALL_COMMENT_SCAN_MODES:
            with self.subTest(mode=mode):
                line = prs._describe_comment_scan(
                    _review_state_for_mode(mode, commit_authors=["dependabot[bot]"])
                )
                self.assertTrue(line.strip(), f"{mode} renders an empty report line")
                self.assertNotIn(self.UNRECOGNIZED, line, f"{mode} is unwired in the oracle report")

    def test_report_lines_are_pairwise_distinct(self):
        """Two modes that render identically cannot be told apart by the reader,
        which is the whole reason the enum exists."""
        rendered = {
            mode: prs._describe_comment_scan(
                _review_state_for_mode(mode, commit_authors=["dependabot[bot]"])
            )
            for mode in hook.ALL_COMMENT_SCAN_MODES
        }
        self.assertEqual(
            len(set(rendered.values())),
            len(rendered),
            f"collapsed report lines: {rendered}",
        )

    def test_the_unrecognized_marker_is_actually_reachable(self):
        """Positive control for the two tests above.

        If the fallback were unreachable — or the marker string a typo — the
        `assertNotIn` assertions would pass for every input forever, including
        for a mode nobody wired. An undeclared mode must hit it.
        """
        line = prs._describe_comment_scan(_review_state_for_mode("some-future-mode"))
        self.assertIn(self.UNRECOGNIZED, line)
        self.assertIn("some-future-mode", line)


def _review_state_for_mode(comment_scan, *, commit_authors=()):
    """A minimal `pr_review_state.ReviewState` carrying just the scan mode."""
    return prs.ReviewState(
        pr_number="691",
        repo="noorinalabs/noorinalabs-main",
        head_ref="dependabot/docker/x-1.2.3",
        branch_author_lastname="Ferreira",
        formal_reviewers=[],
        comment_reviewers=[],
        non_roster_requestors=[],
        distinct_reviewer_count=0,
        wave_bootstrap_exception=False,
        reviews_missing_tech_debt=[],
        tech_debt_issue_numbers=[],
        comment_scan=comment_scan,
        commit_authors=list(commit_authors),
    )


class BlockReasonRatioCollisionTests(_NoContentBindingHarness):
    """#1203 — the instrument must not emit a ratio it did not compute.

    The root cause of the five inert assertions this class ships alongside was
    NOT the assertions. It was that `check()`'s peer-review BLOCK reason embedded
    the literal `1/2 false-block` three times in its operator-help document —
    output-shaped text that no ratio assertion can tell apart from the
    interpolated count. Correcting five call sites and leaving the collision in
    place would leave the trap armed for the sixth, which is how #1203 came to
    have five instances in the first place.

    So the property is pinned at the source instead: **every `N/2` token a
    peer-review BLOCK emits equals the computed count.** A future help-text edit
    that reintroduces a ratio literal fails HERE, loudly, rather than silently
    neutering somebody's assertion several waves downstream.
    """

    _input = staticmethod(_test_helpers.bash_input)

    @staticmethod
    def _pr_data(**overrides) -> dict:
        base = {
            "author": "parametrization",
            "number": 100,
            "reviews": [],
            "headRefName": "L.Pham/0001-fix",
            "labels": [],
        }
        base.update(overrides)
        return base

    def _block_reason(self, reviewers: set[str], head_ref: str) -> str:
        review_result = hook.CommentReviewResult()
        review_result.reviewers = set(reviewers)
        with (
            mock.patch.object(
                hook, "get_pr_data", return_value=self._pr_data(headRefName=head_ref)
            ),
            mock.patch.object(hook, "check_comment_reviews", return_value=review_result),
        ):
            result = hook.check(self._input("gh pr merge 100 --squash"))
        self.assertIsNotNone(result, f"{len(reviewers)} reviewer(s) on {head_ref} must BLOCK")
        assert result is not None
        self.assertEqual(result["decision"], "block")
        return result["reason"]

    # Head refs chosen to vary the scan mode, since each mode prepends its own
    # diagnostic paragraph to the same reason — a literal could hide in any of
    # them, not only in the shared help tail.
    HEAD_REFS = (
        "L.Pham/0001-fix",  # ordinary implementer branch
        "deployments/phase-3/wave-6",  # wave-merge carve-out (#1310)
        "dependabot/docker/x-1.2.3",  # no branch author (#1206)
    )

    def test_only_the_computed_count_appears_as_a_ratio(self):
        """No `N/2` token in a BLOCK reason may disagree with the real count.

        Driven at BOTH 0 and 1 reviewers deliberately. A set-equality guard run
        only at 1 reviewer could not see a reintroduced `1/2` literal at all — it
        would collapse into the count that is legitimately there. The zero-reviewer
        row is what gives this assertion teeth, and it is the row to keep if this
        matrix is ever trimmed.
        """
        for head_ref in self.HEAD_REFS:
            for reviewers, expected in ((set(), 0), ({"aino virtanen"}, 1)):
                with self.subTest(head_ref=head_ref, count=expected):
                    reason = self._block_reason(reviewers, head_ref)
                    self.assertEqual(
                        set(_ANY_RATIO_RE.findall(reason)),
                        {f"{expected}/2"},
                        "a peer-review BLOCK reason must contain no ratio-shaped "
                        "token other than its own computed count (#1203)",
                    )

    def test_the_guard_would_catch_a_reintroduced_literal(self):
        """Anti-vacuity: show the guard above actually fires on the old text.

        A guard asserting a set is empty-of-strangers is worthless if the
        scenario it screens for cannot arise. Re-inject the exact boilerplate
        #1203 removed into a real reason and confirm the same predicate rejects
        it. Uses the zero-reviewer reason for the reason named above: at 1
        reviewer the reinjected `1/2` is indistinguishable from the real count,
        which is precisely the bug.
        """
        reason = self._block_reason(set(), "L.Pham/0001-fix")
        self.assertEqual(set(_ANY_RATIO_RE.findall(reason)), {"0/2"})
        reinjected = reason + "\n      Requestor as rest-of-line garbage; 1/2 false-block.\n"
        self.assertEqual(
            set(_ANY_RATIO_RE.findall(reinjected)),
            {"0/2", "1/2"},
            "the guard's predicate must flag a ratio literal that disagrees "
            "with the computed count — otherwise it screens for nothing",
        )

    def test_help_text_still_names_the_historical_instances(self):
        """Removing the ratio must not cost the operator the diagnosis.

        The three P3W11 batch-11 instances are why the trailer-block rule exists;
        the fix was to drop the `N/2` token from those lines, not the lines.
        """
        reason = self._block_reason({"aino virtanen"}, "L.Pham/0001-fix")
        for instance in ("main#509", "deploy#337", "deploy#339"):
            self.assertIn(instance, reason)
        self.assertIn("false-blocked one approval short", reason)
        self.assertIn("Historical instances driving this enforcement", reason)


if __name__ == "__main__":
    unittest.main()
