"""Tests for pr_review_state — the deterministic review-state query CLI (#707).

The driver REUSES validate_pr_review's functions, so these tests mock those
gate functions (never the network). Coverage:
  1. 0 distinct Approved -> gate would BLOCK (exit 1).
  2. 1 distinct Approved (no exception) -> BLOCK (exit 1).
  3. 2 distinct Approved, all TechDebt present -> PASS (exit 0).
  4. A verdict missing the TechDebt line -> BLOCK even with 2 reviewers (exit 1).
  5. wave-bootstrap single-reviewer exception -> PASS with one reviewer (exit 0).
  6. branch-author self-review exclusion: the lastname parsed from the head ref
     is the one passed into check_comment_reviews (the gate excludes a same-
     lastname Requestor).
  7. non-roster Approved Requestor is filtered out of the reviewer count.
  8. a PR-fetch failure -> ReviewStateError -> CLI exit 2.
  9. content-staleness binding (#1046, ContentStalenessTests): T_content is
     computed and FORWARDED as `content_ts` to every check_comment_reviews call
     site; stale comment + formal verdicts are excluded from the count, drive
     PASS -> BLOCK, and are surfaced in both renders. A commit-fetch failure is
     a determinate error (exit 2), never a silent content_ts=None fail-open.
"""

from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

# Helper lives at .claude/lib/pr_review_state.py; test is at
# .claude/lib/tests/test_*.py. parent.parent reaches the lib root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pr_review_state as prs  # noqa: E402

# T_content fixtures (#1046). NOW is the branch's latest non-merge commit time;
# a verdict cast at BEFORE predates it and is stale, one at AFTER is current.
_NOW = datetime(2026, 7, 20, 12, 0, 0, tzinfo=timezone.utc)
_BEFORE = _NOW - timedelta(hours=6)
_AFTER = _NOW + timedelta(hours=1)


def _api_commit(
    sha: str, when: datetime, parents: int = 1, name: str = "", email: str = ""
) -> dict:
    """Build a `pulls/{n}/commits` payload entry (#1210).

    The driver's fixtures now stub the FETCH (`fetch_pr_commits`) rather than
    the analysis, so the real `latest_content_commit` and
    `commit_author_identities` run over this — which is what keeps these tests
    binding to the gate's actual behaviour instead of to a stubbed answer.
    """
    return {
        "sha": sha,
        "parents": [{"sha": f"p{i}"} for i in range(parents)],
        "commit": {
            "committer": {"date": when.isoformat().replace("+00:00", "Z")},
            "author": {"name": name, "email": email},
        },
    }


_CONTENT_COMMITS = [_api_commit("ac8bcfa", _NOW)]


def _comment_result(
    reviewers=(),
    missing_tech_debt=(),
    tech_debt_issues=(),
    tech_debt_unparseable=(),
    stale=(),
) -> "prs.gate.CommentReviewResult":
    """Build a CommentReviewResult like check_comment_reviews would return.

    `reviewers` are full names (any case); they are stored lowercased, matching
    the gate's dedup key. `stale` is a sequence of (reviewer, verdict,
    created_at) tuples recorded as excluded-stale verdicts (#950).
    `tech_debt_unparseable` is a sequence of (requestor, raw_value) pairs
    (main#1055) recorded when TechDebt: was present, non-"none", but parsed
    to zero issue numbers.
    """
    result = prs.gate.CommentReviewResult()
    result.reviewers = {r.lower() for r in reviewers}
    result.reviews_missing_tech_debt = list(missing_tech_debt)
    result.tech_debt_issue_numbers = list(tech_debt_issues)
    result.tech_debt_unparseable = list(tech_debt_unparseable)
    result.stale_verdicts = [
        prs.gate.StaleVerdict(reviewer=r, verdict=v, created_at=c) for r, v, c in stale
    ]
    return result


def _pr_data(
    *, author="someauthor", head_ref="S.Ferreira/0707-pr-review-state", labels=(), reviews=()
) -> dict:
    return {
        "author": author,
        "number": "707",
        "reviews": list(reviews),
        "headRefName": head_ref,
        "labels": list(labels),
    }


class ComputeReviewStateTests(unittest.TestCase):
    def _run(
        self,
        *,
        pr_data,
        comment_result,
        roster_names,
        single_reviewer_exception=False,
        commits=None,
    ) -> prs.ReviewState:
        with (
            mock.patch.object(prs.gate, "get_pr_data", return_value=pr_data),
            mock.patch.object(
                prs.gate,
                "fetch_pr_commits",
                return_value=_CONTENT_COMMITS if commits is None else commits,
            ),
            mock.patch.object(prs.gate, "check_comment_reviews", return_value=comment_result),
            mock.patch.object(prs.gate, "_load_roster_names", return_value=roster_names),
            mock.patch.object(
                prs.gate, "is_single_reviewer_exception", return_value=single_reviewer_exception
            ),
        ):
            return prs.compute_review_state("707", repo="noorinalabs/noorinalabs-main")

    def test_zero_approved_blocks(self):
        state = self._run(
            pr_data=_pr_data(),
            comment_result=_comment_result(reviewers=()),
            roster_names=set(),
        )
        self.assertEqual(state.distinct_reviewer_count, 0)
        self.assertFalse(state.passes())

    def test_one_approved_blocks_without_exception(self):
        state = self._run(
            pr_data=_pr_data(),
            comment_result=_comment_result(reviewers=("Aino Virtanen",)),
            roster_names={"aino virtanen"},
        )
        self.assertEqual(state.distinct_reviewer_count, 1)
        self.assertFalse(state.passes())

    def test_two_approved_passes(self):
        state = self._run(
            pr_data=_pr_data(),
            comment_result=_comment_result(
                reviewers=("Aino Virtanen", "Nadia Khoury"),
                tech_debt_issues=("808",),
            ),
            roster_names={"aino virtanen", "nadia khoury"},
        )
        self.assertEqual(state.distinct_reviewer_count, 2)
        self.assertEqual(state.tech_debt_issue_numbers, ["808"])
        self.assertTrue(state.passes())

    def test_bare_tech_debt_number_carried_through(self):
        # main#1055: pr_review_state must not silently drop what the gate
        # itself now surfaces — the field is a straight pass-through of the
        # gate's CommentReviewResult.tech_debt_issue_numbers, which already
        # accepts bare numbers per the gate-level fix.
        state = self._run(
            pr_data=_pr_data(),
            comment_result=_comment_result(
                reviewers=("Aino Virtanen", "Nadia Khoury"),
                tech_debt_issues=("1054",),
            ),
            roster_names={"aino virtanen", "nadia khoury"},
        )
        self.assertEqual(state.tech_debt_issue_numbers, ["1054"])

    def test_unparseable_tech_debt_surfaced_and_does_not_block(self):
        # main#1055: an unparseable TechDebt value is recorded for visibility
        # but must NOT affect passes() — it is an audit-fidelity gap, not a
        # merge-blocking condition (the presence gate already passed).
        state = self._run(
            pr_data=_pr_data(),
            comment_result=_comment_result(
                reviewers=("Aino Virtanen", "Nadia Khoury"),
                tech_debt_unparseable=(("Aino Virtanen", "filed later"),),
            ),
            roster_names={"aino virtanen", "nadia khoury"},
        )
        self.assertEqual(state.tech_debt_unparseable, [("Aino Virtanen", "filed later")])
        self.assertTrue(state.passes())
        self.assertIn("UNPARSEABLE", prs._render_text(state))

    def test_two_approved_but_missing_tech_debt_blocks(self):
        state = self._run(
            pr_data=_pr_data(),
            comment_result=_comment_result(
                reviewers=("Aino Virtanen", "Nadia Khoury"),
                missing_tech_debt=("Nadia Khoury",),
            ),
            roster_names={"aino virtanen", "nadia khoury"},
        )
        self.assertEqual(state.distinct_reviewer_count, 2)
        self.assertEqual(state.reviews_missing_tech_debt, ["Nadia Khoury"])
        self.assertFalse(state.passes())

    def test_wave_bootstrap_single_reviewer_passes(self):
        state = self._run(
            pr_data=_pr_data(labels=("wave-bootstrap",)),
            comment_result=_comment_result(reviewers=("Aino Virtanen",)),
            roster_names={"aino virtanen"},
            single_reviewer_exception=True,
        )
        self.assertEqual(state.distinct_reviewer_count, 1)
        self.assertTrue(state.wave_bootstrap_exception)
        self.assertTrue(state.passes())

    def test_branch_author_lastname_passed_to_check(self):
        """The identity parsed from the head ref drives the gate's self-review
        exclusion, so it must be the value handed to check_comment_reviews.

        Both halves (#1172): the surname alone does not identify a person —
        `S.Ferreira` and `L.Ferreira` are two roster members — so the first
        initial has to arrive with it or the exclusion collapses them.
        """
        captured = {}

        def fake_check(
            number,
            lastname,
            repo=None,
            content_ts=None,
            commit_author_identities=(),
            branch_author_initial="",
        ):
            captured["number"] = number
            captured["lastname"] = lastname
            captured["initial"] = branch_author_initial
            return _comment_result(reviewers=())

        with (
            mock.patch.object(
                prs.gate,
                "get_pr_data",
                return_value=_pr_data(head_ref="S.Ferreira/0707-pr-review-state"),
            ),
            mock.patch.object(prs.gate, "fetch_pr_commits", return_value=_CONTENT_COMMITS),
            mock.patch.object(prs.gate, "check_comment_reviews", side_effect=fake_check),
            mock.patch.object(prs.gate, "_load_roster_names", return_value=set()),
            mock.patch.object(prs.gate, "is_single_reviewer_exception", return_value=False),
        ):
            state = prs.compute_review_state("707", repo="noorinalabs/noorinalabs-main")

        self.assertEqual(captured["lastname"], "Ferreira")
        self.assertEqual(captured["initial"], "s")
        self.assertEqual(state.branch_author_lastname, "Ferreira")

    def test_non_roster_requestor_excluded_from_count(self):
        """An Approved Requestor not in the roster is filtered out (#498) and
        does not count toward the threshold."""
        state = self._run(
            pr_data=_pr_data(),
            comment_result=_comment_result(
                reviewers=("Aino Virtanen", "Imelda Santos"),
            ),
            roster_names={"aino virtanen"},  # Imelda is NOT a roster persona
        )
        self.assertEqual(state.comment_reviewers, ["aino virtanen"])
        self.assertEqual(state.non_roster_requestors, ["imelda santos"])
        self.assertEqual(state.distinct_reviewer_count, 1)
        self.assertFalse(state.passes())

    def test_fetch_failure_raises(self):
        with mock.patch.object(prs.gate, "get_pr_data", return_value=None):
            with self.assertRaises(prs.ReviewStateError):
                prs.compute_review_state("707", repo="noorinalabs/noorinalabs-main")

    def test_delegates_to_the_shared_resolve_review_verdicts_entry_point(self):
        """#1048: `compute_review_state` must call `gate.resolve_review_verdicts`
        and use its output DIRECTLY rather than reassembling the
        content-binding / comment-scan / roster-filter / union pipeline
        inline — the concrete guard for #1048's acceptance criterion
        ('neither check() nor compute_review_state re-derives the verdict
        set'). A fake `ReviewVerdicts` drives the whole result.
        """
        fake_verdicts = prs.gate.ReviewVerdicts(
            number="707",
            head_ref="S.Ferreira/0707-pr-review-state",
            labels=[],
            branch_author_lastname="Ferreira",
            content_sha="ac8bcfa",
            content_ts=_NOW,
            formal_reviewers=set(),
            comment_reviewers={"aino virtanen", "nadia khoury"},
            non_roster_requestors=set(),
            roster_comment_reviewers={"aino virtanen", "nadia khoury"},
            roster_names={"aino virtanen", "nadia khoury"},
            distinct_reviewers={"aino virtanen", "nadia khoury"},
            stale_verdicts_comment=[],
            stale_verdicts_formal=[],
            reviews_missing_tech_debt=[],
            tech_debt_issue_numbers=["808"],
            tech_debt_unparseable=[],
            wave_bootstrap_exception=False,
        )
        with (
            mock.patch.object(prs.gate, "get_pr_data", return_value=_pr_data()),
            mock.patch.object(
                prs.gate, "resolve_review_verdicts", return_value=fake_verdicts
            ) as mock_resolve,
        ):
            state = prs.compute_review_state("707", repo="noorinalabs/noorinalabs-main")

        mock_resolve.assert_called_once()
        self.assertEqual(state.distinct_reviewer_count, 2)
        self.assertEqual(state.tech_debt_issue_numbers, ["808"])
        self.assertTrue(state.passes())

    def test_comment_scan_undetermined_raises_review_state_error(self):
        """`CommentScanUndeterminedError` from the shared boundary must reach
        this driver's own `ReviewStateError` (exit 2) — proving the
        exception, not a re-derived `undetermined` flag, is what drives it."""
        with (
            mock.patch.object(prs.gate, "get_pr_data", return_value=_pr_data()),
            mock.patch.object(
                prs.gate,
                "resolve_review_verdicts",
                side_effect=prs.gate.CommentScanUndeterminedError("HTTP 403: Forbidden"),
            ),
        ):
            with self.assertRaises(prs.ReviewStateError) as ctx:
                prs.compute_review_state("707", repo="noorinalabs/noorinalabs-main")
        self.assertIn("HTTP 403: Forbidden", str(ctx.exception))


# ---------------------------------------------------------------------------
# #1046 — content-staleness binding
#
# The driver called `gate.check_comment_reviews` WITHOUT `content_ts`, so
# T_content was never computed, `stale_verdicts` stayed empty, and the tool
# reported PASS on approvals the merge gate rejects as stale (observed live on
# main#1040: two Approved verdicts cast at 7428f25, additive commit ac8bcfa
# pushed, driver still said PASS).
#
# MUTATION-SENSITIVITY IS THE POINT of this class. Deleting `content_ts=...`
# from either call site in `compute_review_state` MUST turn these red. The
# end-to-end test therefore runs the REAL `check_comment_reviews` over a faked
# `gh api` payload rather than a canned return value — a mock that ignores its
# arguments cannot detect an argument going missing, which is precisely how the
# original defect passed a green suite.
# ---------------------------------------------------------------------------


def _charter_comment(requestor: str, verdict: str, created_at: datetime) -> dict:
    """A charter-format review comment as the `gh api` comments endpoint returns it."""
    return {
        "body": (
            f"Requestor: {requestor}\nRequestee: Someone Else\n"
            f"RequestOrReplied: {verdict}\nTechDebt: none"
        ),
        "created_at": created_at.isoformat().replace("+00:00", "Z"),
    }


class ContentStalenessTests(unittest.TestCase):
    REPO = "noorinalabs/noorinalabs-main"

    def _compute_with_real_comment_check(self, comments, *, roster, commits, reviews=()):
        """Drive compute_review_state through the REAL check_comment_reviews.

        Only the network boundary (`gh api`) is faked, so `content_ts` actually
        governs the filtering. If the driver stops forwarding it, the stale
        comments below start counting and the assertions fail — which is the
        regression guard this whole class exists to provide.
        """

        def fake_run(cmd, **kwargs):
            return mock.Mock(returncode=0, stdout=json.dumps(comments), stderr="")

        with (
            mock.patch.object(
                prs.gate,
                "get_pr_data",
                # Branch author is Mwangi, NOT one of the reviewers below — a
                # same-lastname reviewer is dropped as a self-review by the gate,
                # which would make the staleness assertions pass for the wrong
                # reason (caught by the anti-vacuity guard while writing these).
                return_value=_pr_data(head_ref="W.Mwangi/1040-example", reviews=reviews),
            ),
            mock.patch.object(prs.gate, "fetch_pr_commits", return_value=commits),
            mock.patch.object(prs.gate.subprocess, "run", side_effect=fake_run),
            mock.patch.object(prs.gate, "_load_roster_names", return_value=roster),
            mock.patch.object(prs.gate, "is_single_reviewer_exception", return_value=False),
        ):
            return prs.compute_review_state("1040", repo=self.REPO)

    def test_fixture_yields_a_pass_when_verdicts_are_fresh(self):
        """Anti-vacuity guard (mirrors the gate suite's own fixture check).

        Every assertion below claims a verdict was NOT counted. If this fixture
        failed to produce counted approvals in the FRESH case, those assertions
        would pass for the wrong reason and certify nothing.
        """
        state = self._compute_with_real_comment_check(
            [
                _charter_comment("Lucas Ferreira", "Approved", _AFTER),
                _charter_comment("Nino Kavtaradze", "Approved", _AFTER),
            ],
            roster={"lucas ferreira", "nino kavtaradze"},
            commits=_CONTENT_COMMITS,
        )
        self.assertEqual(state.distinct_reviewer_count, 2)
        self.assertEqual(state.stale_verdicts, [])
        self.assertTrue(state.passes(), "fixture must PASS when fresh, or the tests are vacuous")

    def test_main1040_stale_approvals_do_not_pass(self):
        """The live #1040 reproduction: both approvals predate the head content commit.

        Pre-fix this reported `passes: true` with 2/2 reviewers. It must BLOCK.
        """
        state = self._compute_with_real_comment_check(
            [
                _charter_comment("Lucas Ferreira", "Approved", _BEFORE),
                _charter_comment("Nino Kavtaradze", "Approved", _BEFORE),
            ],
            roster={"lucas ferreira", "nino kavtaradze"},
            commits=_CONTENT_COMMITS,
        )
        self.assertEqual(state.distinct_reviewer_count, 0)
        self.assertEqual(state.comment_reviewers, [])
        self.assertFalse(state.passes())
        self.assertEqual(
            sorted(sv["reviewer"] for sv in state.stale_verdicts),
            ["Lucas Ferreira", "Nino Kavtaradze"],
        )

    def test_mixed_freshness_counts_only_the_current_verdict(self):
        state = self._compute_with_real_comment_check(
            [
                _charter_comment("Lucas Ferreira", "Approved", _BEFORE),
                _charter_comment("Nino Kavtaradze", "Approved", _AFTER),
            ],
            roster={"lucas ferreira", "nino kavtaradze"},
            commits=_CONTENT_COMMITS,
        )
        self.assertEqual(state.comment_reviewers, ["nino kavtaradze"])
        self.assertEqual(state.distinct_reviewer_count, 1)
        self.assertFalse(state.passes())
        self.assertEqual([sv["reviewer"] for sv in state.stale_verdicts], ["Lucas Ferreira"])

    def test_content_ts_forwarded_on_feature_branch_call_site(self):
        """Direct kill-shot for the #1046 mutation on the `:135` call site."""
        captured = {}

        def fake_check(
            number,
            lastname,
            repo=None,
            content_ts=None,
            commit_author_identities=(),
            branch_author_initial="",
        ):
            captured["content_ts"] = content_ts
            return _comment_result(reviewers=())

        with (
            mock.patch.object(
                prs.gate, "get_pr_data", return_value=_pr_data(head_ref="L.Ferreira/1040-x")
            ),
            mock.patch.object(prs.gate, "fetch_pr_commits", return_value=_CONTENT_COMMITS),
            mock.patch.object(prs.gate, "check_comment_reviews", side_effect=fake_check),
            mock.patch.object(prs.gate, "_load_roster_names", return_value=set()),
            mock.patch.object(prs.gate, "is_single_reviewer_exception", return_value=False),
        ):
            prs.compute_review_state("1040", repo=self.REPO)

        self.assertEqual(
            captured["content_ts"],
            _NOW,
            "compute_review_state must forward T_content to check_comment_reviews (#1046)",
        )

    def test_content_ts_forwarded_on_the_no_branch_author_path(self):
        """A head ref naming NO branch author is a second omission surface (#1046).

        Since #1206 this is no longer a separate `deployments/**` call site —
        the resolver has ONE `check_comment_reviews` call for every head-ref
        shape — but the wave-merge ref is still the shape that must arrive with
        the `""` author sentinel, so the assertion is kept and pointed at the
        unified call site. `branch_author_initial` must be `""` here too: a
        non-empty initial would mean the resolver had invented an author for a
        branch that names none.
        """
        captured = {}

        def fake_check(
            number,
            lastname,
            repo=None,
            content_ts=None,
            commit_author_identities=(),
            branch_author_initial="",
        ):
            captured["content_ts"] = content_ts
            captured["lastname"] = lastname
            captured["initial"] = branch_author_initial
            return _comment_result(reviewers=())

        with (
            mock.patch.object(
                prs.gate,
                "get_pr_data",
                return_value=_pr_data(head_ref="deployments/phase-9/wave-26"),
            ),
            mock.patch.object(prs.gate, "fetch_pr_commits", return_value=_CONTENT_COMMITS),
            mock.patch.object(prs.gate, "check_comment_reviews", side_effect=fake_check),
            mock.patch.object(prs.gate, "_load_roster_names", return_value=set()),
            mock.patch.object(prs.gate, "is_single_reviewer_exception", return_value=False),
        ):
            prs.compute_review_state("1040", repo=self.REPO)

        self.assertEqual(captured["lastname"], "")
        self.assertEqual(captured["initial"], "")
        self.assertEqual(captured["content_ts"], _NOW)

    def test_stale_formal_review_is_excluded_and_recorded(self):
        """Formal GitHub reviews are bound to T_content by the same rule (#950).

        The driver shares `gate.partition_formal_reviewers` with Hook 4 rather
        than re-deriving the rule, so this cannot drift the way #1046 did.
        """
        state = self._compute_with_real_comment_check(
            [],
            roster=set(),
            commits=_CONTENT_COMMITS,
            reviews=[
                {
                    "author": {"login": "stale-reviewer"},
                    "state": "APPROVED",
                    "submittedAt": _BEFORE.isoformat().replace("+00:00", "Z"),
                },
                {
                    "author": {"login": "fresh-reviewer"},
                    "state": "APPROVED",
                    "submittedAt": _AFTER.isoformat().replace("+00:00", "Z"),
                },
            ],
        )
        self.assertEqual(state.formal_reviewers, ["fresh-reviewer"])
        self.assertEqual(
            [(sv["reviewer"], sv["source"]) for sv in state.stale_verdicts],
            [("stale-reviewer", "formal")],
        )
        self.assertFalse(state.passes())

    def test_no_non_merge_commits_means_nothing_is_stale(self):
        """An empty commit list = no non-merge commits = no content binding."""
        state = self._compute_with_real_comment_check(
            [
                _charter_comment("Lucas Ferreira", "Approved", _BEFORE),
                _charter_comment("Nino Kavtaradze", "Approved", _BEFORE),
            ],
            roster={"lucas ferreira", "nino kavtaradze"},
            commits=[],
        )
        self.assertEqual(state.distinct_reviewer_count, 2)
        self.assertEqual(state.stale_verdicts, [])
        self.assertTrue(state.passes())

    def test_commit_fetch_failure_is_an_error_not_a_fail_open(self):
        """A commit-fetch failure must raise (exit 2), never degrade to content_ts=None.

        Swallowing `CommitFetchError` and passing None would count every verdict
        regardless of age — reinstating the exact #1046 fail-open. Hook 4
        hard-blocks here; the driver must be equally determinate.

        Every downstream collaborator is mocked to a SUCCESS value, and the
        message is asserted, so the only thing that can raise is the commit-fetch
        path. A bare `assertRaises(ReviewStateError)` here is NOT enough: with
        the swallow mutation applied, execution fell through to the roster
        resolver, which raised `ReviewStateError` for an unrelated reason and the
        test passed green against the very defect it was written to catch.
        """
        with (
            mock.patch.object(prs.gate, "get_pr_data", return_value=_pr_data()),
            mock.patch.object(
                prs.gate,
                "fetch_pr_commits",
                side_effect=prs.gate.CommitFetchError("boom"),
            ),
            mock.patch.object(prs.gate, "check_comment_reviews", return_value=_comment_result()),
            mock.patch.object(prs.gate, "_load_roster_names", return_value=set()),
            mock.patch.object(prs.gate, "is_single_reviewer_exception", return_value=False),
        ):
            with self.assertRaises(prs.ReviewStateError) as ctx:
                prs.compute_review_state("1040", repo=self.REPO)

        message = str(ctx.exception)
        self.assertIn("commit list", message)
        self.assertIn("boom", message)

    def test_stale_verdicts_are_visible_in_both_renders(self):
        """A stale verdict must be SURFACED, not silently subtracted (#1046 point 2)."""
        state = self._compute_with_real_comment_check(
            [_charter_comment("Lucas Ferreira", "Approved", _BEFORE)],
            roster={"lucas ferreira"},
            commits=_CONTENT_COMMITS,
        )

        text = prs._render_text(state)
        self.assertIn("STALE", text)
        self.assertIn("Lucas Ferreira", text)
        self.assertIn("ac8bcfa", text)

        payload = json.loads(prs._render_json(state))
        self.assertEqual(payload["stale_verdict_count"], 1)
        self.assertEqual(payload["stale_verdicts"][0]["reviewer"], "Lucas Ferreira")
        self.assertEqual(payload["content_sha"], "ac8bcfa")
        self.assertFalse(payload["passes"])


class NearWindowStalenessTests(ContentStalenessTests):
    """#1272: T_content staleness (#950) catches a verdict cast BEFORE the
    head moved; it cannot catch the mirror case — a verdict cast AFTER
    T_content by a reviewer who started reading before the push landed and
    had no way to know the head had moved. `comment.created_at > T_content`
    alone cannot distinguish that from an ordinary review that simply landed
    after a routine push, because both produce a `created_at` a few seconds
    after `T_content`.

    Live case (noorinalabs-main#1263, 2026-08-03): the reviewer began
    reviewing head `2c113e7`, the orchestrator pushed `60faad1` at
    03:31:36Z, and the reviewer posted Approved at 03:32:52Z — 76 seconds
    later, having read `2c113e7`. `pr_review_state.py` at `60faad1` reported
    the verdict as a plain CURRENT approval, indistinguishable from one cast
    by a reviewer who had actually read `60faad1`. Reused as a subclass of
    `ContentStalenessTests` so `_compute_with_real_comment_check` drives the
    REAL `check_comment_reviews` / `partition_formal_reviewers` pipeline
    (the #1046 lesson: a mock that ignores its arguments cannot detect a
    forwarding regression).
    """

    _NEAR = _NOW + timedelta(seconds=76)  # the exact PR #1263 delta

    def test_near_window_comment_verdict_is_counted_and_surfaced(self):
        """The near-window verdict counts toward the threshold (#950 stands)
        AND is named as a possible mid-review head move (#1272) — never
        silently indistinguishable from an ordinary fresh approval.
        """
        state = self._compute_with_real_comment_check(
            [_charter_comment("Bereket Tadesse", "Approved", self._NEAR)],
            roster={"bereket tadesse"},
            commits=_CONTENT_COMMITS,
        )

        # #950's rule is unchanged: this verdict is CURRENT, not stale.
        self.assertEqual(state.distinct_reviewer_count, 1)
        self.assertEqual(state.stale_verdicts, [])

        # #1272: but it must be NAMED as a near-window verdict, not silently
        # folded into "current" like any other approval.
        self.assertEqual(len(state.near_window_verdicts), 1)
        near = state.near_window_verdicts[0]
        self.assertEqual(near["reviewer"], "Bereket Tadesse")
        self.assertEqual(near["source"], "comment")
        self.assertAlmostEqual(near["delta_seconds"], 76, delta=1)

    def test_near_window_formal_review_is_counted_and_surfaced(self):
        """The formal-review half of the same rule (mirrors #950's own
        formal/comment symmetry — `partition_formal_reviewers` is bound to
        T_content by the identical rule as `check_comment_reviews`)."""
        state = self._compute_with_real_comment_check(
            [],
            roster=set(),
            commits=_CONTENT_COMMITS,
            reviews=[
                {
                    "author": {"login": "near-reviewer"},
                    "state": "APPROVED",
                    "submittedAt": self._NEAR.isoformat().replace("+00:00", "Z"),
                },
            ],
        )
        self.assertEqual(state.formal_reviewers, ["near-reviewer"])
        self.assertEqual(state.stale_verdicts, [])
        self.assertEqual(len(state.near_window_verdicts), 1)
        near = state.near_window_verdicts[0]
        self.assertEqual(near["reviewer"], "near-reviewer")
        self.assertEqual(near["source"], "formal")

    def test_comfortably_fresh_verdict_is_not_flagged_near_window(self):
        """A verdict well outside the window (the `_AFTER` fixture, +1h) must
        NOT be flagged — the near-window disclosure is for the genuine
        close-call, not every verdict that happens to postdate T_content.
        """
        state = self._compute_with_real_comment_check(
            [_charter_comment("Nino Kavtaradze", "Approved", _AFTER)],
            roster={"nino kavtaradze"},
            commits=_CONTENT_COMMITS,
        )
        self.assertEqual(state.distinct_reviewer_count, 1)
        self.assertEqual(state.near_window_verdicts, [])

    def test_near_window_verdicts_are_visible_in_both_renders(self):
        """Surfaced, never silently counted (#1272 acceptance criterion)."""
        # A second, comfortably-fresh reviewer brings this to 2/2 so the test
        # can assert the near-window verdict COUNTED toward an actual pass,
        # not merely that it wasn't excluded from an already-failing count.
        state = self._compute_with_real_comment_check(
            [
                _charter_comment("Bereket Tadesse", "Approved", self._NEAR),
                _charter_comment("Nino Kavtaradze", "Approved", _AFTER),
            ],
            roster={"bereket tadesse", "nino kavtaradze"},
            commits=_CONTENT_COMMITS,
        )

        text = prs._render_text(state)
        self.assertIn("NEAR-WINDOW", text)
        self.assertIn("Bereket Tadesse", text)
        # It must read as COUNTED, not as a block/exclusion — distinct wording
        # from the STALE block so an operator cannot confuse the two.
        self.assertNotIn("x STALE", text.split("NEAR-WINDOW")[1] if "NEAR-WINDOW" in text else "")

        payload = json.loads(prs._render_json(state))
        self.assertEqual(len(payload["near_window_verdicts"]), 1)
        self.assertEqual(payload["near_window_verdicts"][0]["reviewer"], "Bereket Tadesse")
        self.assertTrue(
            payload["passes"], "a near-window verdict must still COUNT (#950 unchanged)"
        )


class CliExitCodeTests(unittest.TestCase):
    def _main(self, state_or_exc):
        if isinstance(state_or_exc, Exception):
            cm = mock.patch.object(prs, "compute_review_state", side_effect=state_or_exc)
        else:
            cm = mock.patch.object(prs, "compute_review_state", return_value=state_or_exc)
        with cm:
            return prs.main(["707", "--repo", "noorinalabs/noorinalabs-main"])

    def _state(self, *, count, missing=(), exception=False):
        return prs.ReviewState(
            pr_number="707",
            repo="noorinalabs/noorinalabs-main",
            head_ref="S.Ferreira/0707-pr-review-state",
            branch_author_lastname="Ferreira",
            formal_reviewers=[],
            comment_reviewers=[],
            non_roster_requestors=[],
            distinct_reviewer_count=count,
            wave_bootstrap_exception=exception,
            reviews_missing_tech_debt=list(missing),
            tech_debt_issue_numbers=[],
        )

    def test_exit_zero_on_pass(self):
        self.assertEqual(self._main(self._state(count=2)), 0)

    def test_exit_one_on_too_few_reviewers(self):
        self.assertEqual(self._main(self._state(count=1)), 1)

    def test_exit_one_on_missing_tech_debt(self):
        self.assertEqual(self._main(self._state(count=2, missing=("Nadia Khoury",))), 1)

    def test_exit_two_on_undeterminable(self):
        self.assertEqual(self._main(prs.ReviewStateError("boom")), 2)


class UndeterminableRepoAndScanTests(unittest.TestCase):
    """#981: the driver must stay determinate alongside Hook 4's fail-closed fix.

    `compute_review_state` already raised on `pr_data is None`, so it was never
    the fail-open the gate was. These pin the two things #981 adds: a SPECIFIC
    diagnosis for an unresolvable `--repo` (deterministic, not a retry), and an
    incomplete comment scan raising rather than reporting a zero-approval PR.
    Drift between this driver and the gate is what #1046 was.
    """

    def test_unresolvable_repo_raises_before_any_fetch(self):
        with mock.patch.object(prs.gate, "get_pr_data") as get_mock:
            with self.assertRaises(prs.ReviewStateError) as ctx:
                prs.compute_review_state("451", repo="$DA")
        self.assertIn("UNEXPANDED", str(ctx.exception))
        get_mock.assert_not_called()

    def test_unresolvable_repo_diagnosis_matches_the_gate(self):
        """Same input, same diagnosis on both surfaces — no drift."""
        self.assertEqual(prs.gate.repo_argument_defect("$DA"), prs.gate.REPO_DEFECT_UNEXPANDED)
        with self.assertRaises(prs.ReviewStateError) as ctx:
            prs.compute_review_state("451", repo="$DA")
        self.assertIn(
            prs.gate.describe_repo_defect("$DA", prs.gate.REPO_DEFECT_UNEXPANDED),
            str(ctx.exception),
        )

    def test_literal_repo_is_not_rejected_by_the_new_guard(self):
        """False-positive guard: a literal repo must still reach the fetch."""
        with mock.patch.object(prs.gate, "get_pr_data", return_value=None) as get_mock:
            with self.assertRaises(prs.ReviewStateError):
                prs.compute_review_state("451", repo="noorinalabs/noorinalabs-main")
        get_mock.assert_called_once()

    def test_incomplete_comment_scan_is_an_error_not_zero_approvals(self):
        """An unreadable comment thread is exit 2, not a FAIL verdict (exit 1).

        Every other collaborator is mocked to a SUCCESS value so the only thing
        that can raise is the incomplete-scan path.
        """
        undetermined = prs.gate.CommentReviewResult()
        undetermined.undetermined = "the PR comments API call failed: HTTP 403"
        pr_data = {
            "author": "parametrization",
            "number": 451,
            "reviews": [],
            "headRefName": "L.Pham/0001-fix",
            "labels": [],
        }
        with (
            mock.patch.object(prs.gate, "get_pr_data", return_value=pr_data),
            mock.patch.object(prs.gate, "fetch_pr_commits", return_value=[]),
            mock.patch.object(prs.gate, "check_comment_reviews", return_value=undetermined),
            mock.patch.object(prs.gate, "_load_roster_names", return_value={"aino virtanen"}),
        ):
            with self.assertRaises(prs.ReviewStateError) as ctx:
                prs.compute_review_state("451", repo="noorinalabs/noorinalabs-main")
        self.assertIn("HTTP 403", str(ctx.exception))


class CommentScanReportedInTheReportTests(unittest.TestCase):
    """#1206 half two: the report must distinguish NOT-MEASURED from MEASURED-EMPTY.

    On noorinalabs-deploy#691 this tool printed, for a PR carrying two valid
    Approveds:

        distinct Approved reviewers: 0/2 required — (none)
        stale verdicts: none

    Every word of that is a claim about what a scan found. No scan had run. The
    count was recoverable by fixing the dispatch; the misleading REPORT is a
    separate defect, because it is what made the first one survive — a
    non-measurement that renders as a measurement cannot be noticed.

    Both directions are asserted throughout: the not-measured report must carry
    the warning AND the measured one must not. An implementation that printed
    the alarming wording unconditionally would fail here just as loudly as one
    that never printed it.
    """

    @staticmethod
    def _state(comment_scan, **overrides):
        kwargs = dict(
            pr_number="691",
            repo="noorinalabs/noorinalabs-deploy",
            head_ref="dependabot/docker/integration-tests/fake_oauth/python-d3400aa",
            branch_author_lastname=None,
            formal_reviewers=[],
            comment_reviewers=[],
            non_roster_requestors=[],
            distinct_reviewer_count=0,
            wave_bootstrap_exception=False,
            reviews_missing_tech_debt=[],
            tech_debt_issue_numbers=[],
            content_sha="837c272a",
            comment_scan=comment_scan,
        )
        kwargs.update(overrides)
        return prs.ReviewState(**kwargs)

    def test_default_is_not_measured(self):
        """A ReviewState built without the field must claim nothing."""
        state = prs.ReviewState(
            pr_number="1",
            repo=None,
            head_ref="x",
            branch_author_lastname=None,
            formal_reviewers=[],
            comment_reviewers=[],
            non_roster_requestors=[],
            distinct_reviewer_count=0,
            wave_bootstrap_exception=False,
            reviews_missing_tech_debt=[],
            tech_debt_issue_numbers=[],
        )
        self.assertEqual(state.comment_scan, prs.gate.COMMENT_SCAN_NOT_RUN)
        self.assertFalse(state.comment_scan_ran)

    def test_not_measured_and_measured_empty_render_differently(self):
        """The core distinction, on IDENTICAL reviewer data (0 reviewers, no
        stale verdicts). If the two texts were equal, the report would still be
        unable to tell an operator which situation they are in."""
        not_measured = prs._render_text(self._state(prs.gate.COMMENT_SCAN_NOT_RUN))
        measured = prs._render_text(self._state(prs.gate.COMMENT_SCAN_NO_BRANCH_AUTHOR))
        self.assertNotEqual(not_measured, measured)

    def test_not_measured_report_warns_and_measured_one_does_not(self):
        not_measured = prs._render_text(self._state(prs.gate.COMMENT_SCAN_NOT_RUN))
        measured = prs._render_text(self._state(prs.gate.COMMENT_SCAN_NO_BRANCH_AUTHOR))

        self.assertIn("NOT RUN", not_measured)
        self.assertIn("NOT a measurement", not_measured)
        self.assertNotIn("NOT RUN", measured)
        self.assertIn("comment verdict scan: RAN", measured)

    def test_stale_verdicts_none_is_only_claimed_when_the_scan_ran(self):
        """`stale verdicts: none` is TRUE in both cases and honest in only one.

        The measured assertion is the positive control: it proves the exact
        string is reachable, so the not-measured assertion is testing the
        conditional rather than a string that never appears at all.
        """
        not_measured = prs._render_text(self._state(prs.gate.COMMENT_SCAN_NOT_RUN))
        measured = prs._render_text(self._state(prs.gate.COMMENT_SCAN_NO_BRANCH_AUTHOR))

        self.assertIn("  stale verdicts: none\n", measured + "\n")
        self.assertNotIn("  stale verdicts: none\n", not_measured + "\n")
        self.assertIn("NOT MEASURED", not_measured)

    def test_author_excluded_mode_names_the_excluded_author(self):
        """The third mode must be distinguishable too — a report that collapsed
        both scanning modes into one line would hide whether self-review
        exclusion was in force on this PR."""
        text = prs._render_text(
            self._state(
                prs.gate.COMMENT_SCAN_AUTHOR_EXCLUDED,
                head_ref="L.Ferreira/1206-x",
                branch_author_lastname="Ferreira",
            )
        )
        self.assertIn("comment verdict scan: RAN", text)
        self.assertIn("Ferreira", text)
        self.assertIn("self-review exclusion active", text)

    def test_json_output_carries_the_scan_mode(self):
        """A machine consumer must see it too, not just the human report."""
        payload = json.loads(prs._render_json(self._state(prs.gate.COMMENT_SCAN_NOT_RUN)))
        self.assertEqual(payload["comment_scan"], prs.gate.COMMENT_SCAN_NOT_RUN)

    def test_compute_review_state_propagates_the_gate_scan_mode(self):
        """Wiring: without this the field would be correct in the dataclass and
        permanently NOT_RUN in production, so every real report would carry the
        alarming warning and the distinction would be worthless.

        Driven through the REAL `resolve_review_verdicts` over a faked comment
        API, on the exact head-ref shape #1206 is about.
        """
        approved = {
            "body": (
                "Requestor: Lucas Ferreira\nRequestee: Dependabot\n"
                "RequestOrReplied: Approved\nTechDebt: none"
            ),
            "created_at": "2026-07-20T00:00:00Z",
        }
        pr_data = {
            "author": "app/dependabot",
            "number": 691,
            "reviews": [],
            "headRefName": "dependabot/docker/integration-tests/fake_oauth/python-d3400aa",
            "labels": [],
        }

        def fake_run(args, capture_output, text, timeout):  # noqa: ARG001
            result = mock.MagicMock()
            result.returncode = 0
            result.stdout = json.dumps([approved])
            return result

        with (
            mock.patch.object(prs.gate, "get_pr_data", return_value=pr_data),
            mock.patch.object(prs.gate.subprocess, "run", side_effect=fake_run),
            mock.patch.object(prs.gate, "fetch_pr_commits", return_value=[]),
            mock.patch.object(prs.gate, "_load_roster_names", return_value={"lucas ferreira"}),
        ):
            state = prs.compute_review_state("691", repo="noorinalabs/noorinalabs-deploy")

        self.assertEqual(state.comment_scan, prs.gate.COMMENT_SCAN_NO_BRANCH_AUTHOR)
        self.assertTrue(state.comment_scan_ran)
        # And the verdict itself is now counted — the driver-level form of the
        # #1206 defect (this was `[]` / 0 before the fix).
        self.assertEqual(state.comment_reviewers, ["lucas ferreira"])
        self.assertEqual(state.distinct_reviewer_count, 1)


class CommitAuthorScanModeReportTests(unittest.TestCase):
    """#1210 at the report layer: which author source the exclusion used.

    The driver replays the gate, so if it could not render the new mode an
    operator running `pr_review_state` ahead of a merge would see a reviewer
    count they could not reconcile with the comment thread.
    """

    @staticmethod
    def _state(comment_scan, **overrides):
        kwargs = dict(
            pr_number="1210",
            repo="noorinalabs/noorinalabs-main",
            head_ref="feature/hand-made",
            branch_author_lastname=None,
            formal_reviewers=[],
            comment_reviewers=["aino virtanen"],
            non_roster_requestors=[],
            distinct_reviewer_count=1,
            wave_bootstrap_exception=False,
            reviews_missing_tech_debt=[],
            tech_debt_issue_numbers=[],
            content_sha="837c272a",
            comment_scan=comment_scan,
        )
        kwargs.update(overrides)
        return prs.ReviewState(**kwargs)

    def test_commit_author_mode_names_the_derived_author(self):
        text = prs._render_text(
            self._state(
                prs.gate.COMMENT_SCAN_COMMIT_AUTHOR_EXCLUDED,
                commit_authors=["Nino Kavtaradze"],
            )
        )
        self.assertIn("COMMIT IDENTITY", text)
        self.assertIn("Nino Kavtaradze", text)
        self.assertIn("self-review exclusion active", text)

    def test_the_two_no_ref_author_modes_read_differently(self):
        """Exclusion-applied vs exclusion-unavailable are opposite facts about
        whether the count below them can be trusted."""
        applied = prs._render_text(
            self._state(
                prs.gate.COMMENT_SCAN_COMMIT_AUTHOR_EXCLUDED,
                commit_authors=["Nino Kavtaradze"],
            )
        )
        unavailable = prs._render_text(self._state(prs.gate.COMMENT_SCAN_NO_BRANCH_AUTHOR))
        self.assertNotEqual(applied, unavailable)
        self.assertIn("COMMIT IDENTITY", applied)
        self.assertNotIn("COMMIT IDENTITY", unavailable)
        self.assertIn("no self-review exclusion was applied", unavailable)
        self.assertNotIn("no self-review exclusion was applied", applied)

    def test_json_carries_the_derived_authors(self):
        payload = json.loads(
            prs._render_json(
                self._state(
                    prs.gate.COMMENT_SCAN_COMMIT_AUTHOR_EXCLUDED,
                    commit_authors=["Nino Kavtaradze"],
                )
            )
        )
        self.assertEqual(payload["comment_scan"], prs.gate.COMMENT_SCAN_COMMIT_AUTHOR_EXCLUDED)
        self.assertEqual(payload["commit_authors"], ["Nino Kavtaradze"])

    def test_compute_review_state_propagates_the_commit_derived_author(self):
        """Wiring: the field must be populated in production, not just settable.

        Driven through the REAL `resolve_review_verdicts`, on a non-charter ref
        whose commits name the very persona who posted one of the verdicts —
        the #1210 case. The self-approval must be subtracted AND named.
        """
        pr_data = _pr_data(head_ref="feature/hand-made")
        comments = [
            _charter_comment("Nino Kavtaradze", "Approved", _AFTER),
            _charter_comment("Lucas Ferreira", "Approved", _AFTER),
        ]

        def fake_run(args, capture_output, text, timeout):  # noqa: ARG001
            result = mock.MagicMock()
            result.returncode = 0
            result.stdout = json.dumps(comments)
            return result

        with (
            mock.patch.object(prs.gate, "get_pr_data", return_value=pr_data),
            mock.patch.object(prs.gate.subprocess, "run", side_effect=fake_run),
            mock.patch.object(
                prs.gate,
                "fetch_pr_commits",
                return_value=[_api_commit("c0", _NOW, name="Nino Kavtaradze")],
            ),
            mock.patch.object(
                prs.gate,
                "_load_roster_names",
                return_value={"lucas ferreira", "nino kavtaradze"},
            ),
        ):
            state = prs.compute_review_state("1210", repo="noorinalabs/noorinalabs-main")

        self.assertEqual(state.comment_scan, prs.gate.COMMENT_SCAN_COMMIT_AUTHOR_EXCLUDED)
        self.assertEqual(state.commit_authors, ["Nino Kavtaradze"])
        self.assertEqual(state.comment_reviewers, ["lucas ferreira"])
        self.assertEqual(state.distinct_reviewer_count, 1)
        self.assertFalse(state.passes())


class InertCommitDerivationReportTests(unittest.TestCase):
    """#1220 at the report layer: derived an identity, subtracted nothing.

    This is the surface the issue was filed FROM — an operator running the
    oracle on a dependabot PR was told "Their own verdicts are excluded from the
    reviewer set (self-review exclusion active)" about `dependabot[bot]`, on a
    PR where both roster approvals had been counted in full.
    """

    BOT_REF = "dependabot/docker/integration-tests/fake_oauth/python-d3400aa"

    @staticmethod
    def _state(comment_scan, **overrides):
        kwargs = dict(
            pr_number="1220",
            repo="noorinalabs/noorinalabs-deploy",
            head_ref="dependabot/docker/integration-tests/fake_oauth/python-d3400aa",
            branch_author_lastname=None,
            formal_reviewers=[],
            comment_reviewers=["lucas ferreira", "nino kavtaradze"],
            non_roster_requestors=[],
            distinct_reviewer_count=2,
            wave_bootstrap_exception=False,
            reviews_missing_tech_debt=[],
            tech_debt_issue_numbers=[],
            content_sha="837c272a",
            comment_scan=comment_scan,
        )
        kwargs.update(overrides)
        return prs.ReviewState(**kwargs)

    def test_inert_mode_names_the_derivation_and_denies_the_subtraction(self):
        text = prs._render_text(
            self._state(
                prs.gate.COMMENT_SCAN_COMMIT_AUTHOR_NON_ROSTER,
                commit_authors=["dependabot[bot]"],
            )
        )
        self.assertIn("comment verdict scan: RAN", text)
        # Still names WHO was derived — the auditable part.
        self.assertIn("COMMIT IDENTITY", text)
        self.assertIn("dependabot[bot]", text)
        # And denies the subtraction the old line asserted.
        self.assertIn("matches NO roster persona", text)
        self.assertIn("no verdict was subtracted", text)
        self.assertNotIn("self-review exclusion active", text)

    def test_inert_and_live_lines_read_differently(self):
        """Opposite claims about the same count must not share wording."""
        inert = prs._render_text(
            self._state(
                prs.gate.COMMENT_SCAN_COMMIT_AUTHOR_NON_ROSTER,
                commit_authors=["dependabot[bot]"],
            )
        )
        live = prs._render_text(
            self._state(
                prs.gate.COMMENT_SCAN_COMMIT_AUTHOR_EXCLUDED,
                commit_authors=["Nino Kavtaradze"],
            )
        )
        self.assertNotEqual(inert, live)
        self.assertIn("self-review exclusion active", live)
        self.assertNotIn("matches NO roster persona", live)

    def test_unrecognized_mode_says_so_instead_of_borrowing_a_neighbour(self):
        """The catch-all used to be NO_BRANCH_AUTHOR's text, so an unwired mode
        was described as "the PR's commits named no persona" — a specific claim
        about evidence nobody had looked at."""
        text = prs._render_text(self._state("some-future-mode"))
        self.assertIn("UNRECOGNIZED SCAN MODE", text)
        self.assertIn("some-future-mode", text)
        self.assertNotIn("commits named no persona either", text)

    def test_compute_review_state_reports_the_inert_mode_end_to_end(self):
        """Wiring, through the REAL `resolve_review_verdicts` — the issue's own
        reproduction shape: a dependabot head ref, one bot-authored commit, two
        genuine roster approvals. Both must still count (deploy#691) and the
        mode must no longer claim an exclusion."""
        pr_data = {
            "author": "app/dependabot",
            "number": 691,
            "reviews": [],
            "headRefName": self.BOT_REF,
            "labels": [],
        }
        comments = [
            _charter_comment("Lucas Ferreira", "Approved", _AFTER),
            _charter_comment("Nino Kavtaradze", "Approved", _AFTER),
        ]

        def fake_run(args, capture_output, text, timeout):  # noqa: ARG001
            result = mock.MagicMock()
            result.returncode = 0
            result.stdout = json.dumps(comments)
            return result

        with (
            mock.patch.object(prs.gate, "get_pr_data", return_value=pr_data),
            mock.patch.object(prs.gate.subprocess, "run", side_effect=fake_run),
            mock.patch.object(
                prs.gate,
                "fetch_pr_commits",
                return_value=[_api_commit("c0", _NOW, name="dependabot[bot]")],
            ),
            mock.patch.object(
                prs.gate,
                "_load_roster_names",
                return_value={"lucas ferreira", "nino kavtaradze"},
            ),
        ):
            state = prs.compute_review_state("691", repo="noorinalabs/noorinalabs-deploy")

        self.assertEqual(state.comment_scan, prs.gate.COMMENT_SCAN_COMMIT_AUTHOR_NON_ROSTER)
        self.assertEqual(state.commit_authors, ["dependabot[bot]"])
        # deploy#691 stays fixed: the count is untouched by the description fix.
        self.assertEqual(state.comment_reviewers, ["lucas ferreira", "nino kavtaradze"])
        self.assertEqual(state.distinct_reviewer_count, 2)
        self.assertTrue(state.passes())
        self.assertNotIn("self-review exclusion active", prs._render_text(state))


if __name__ == "__main__":
    unittest.main()
