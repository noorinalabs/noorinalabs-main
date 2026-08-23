"""Tests for gate_integrity — the wrapup gate-integrity audit (main#1477).

The audit REUSES the merge gate's verdict resolution rather than reimplementing
it, so these tests mock at two seams and never touch the network:

  * `fetch` / `compute` — injected into `audit_repo`/`audit`, so the whole
    classify-and-aggregate path runs over fixtures.
  * `gh.run_gh` — injected into `fetch_merged_prs`, so the REST walk's paging
    and its fail-closed paths are exercised directly.

Coverage:
  1. Classification — every branch of `classify`, including the issue's three
     named acceptance cases (wave->main is EXEMPT not UNREVIEWED; an unreviewed
     non-exempt PR is UNREVIEWED; a gh/API failure yields exit 2, never 0).
  2. Exemption identification — the `wave-merge` predicate is the GATE's own
     `charter_trailer.is_wave_branch`, not a path regex, and is NOT the
     `wave-integration` comment-scan mode (#1216 is a different rule).
  3. Enumeration — window boundaries, the paging stop condition, and every
     fail-closed path (gh failure, malformed payload, unparseable `merged_at`,
     page ceiling) raising rather than returning a short list.
  4. Reuse — `audit_repo`'s default verdict source IS
     `pr_review_state.compute_review_state` (the shared entry point), so a
     future fork of the pipeline fails a test instead of drifting silently
     (main#1046).
  5. MUTATION — `MutationTests` applies a table of defects to the classifier and
     asserts each one is CAUGHT by at least one probe. An assertion no fixture
     can trip is not evidence (cf. the inert Gates row on main#1474, which
     passed identically with all three hashes zeroed, and the vendored base-pin
     gate silent on 4 of 8 mutants at deploy#707).
"""

from __future__ import annotations

import contextlib
import inspect
import json
import re
import subprocess
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

# Helper lives at .claude/lib/gate_integrity.py; this test is at
# .claude/lib/tests/test_*.py. parent.parent reaches the lib root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gate_integrity as gi  # noqa: E402
import pr_review_state  # noqa: E402

_REPO = "noorinalabs/noorinalabs-main"
_SINCE = datetime(2026, 8, 1, 0, 0, 0, tzinfo=timezone.utc)
_IN_WINDOW = "2026-08-10T12:00:00Z"
_BEFORE_WINDOW = "2026-07-20T12:00:00Z"


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _pr(
    number: int = 1001,
    *,
    title: str = "fix(hooks): narrow the path token",
    body: str = "Refs #1000.",
    head_ref: str = "A.Virtanen/1000-narrow-token",
    base_ref: str = "main",
    merged_at: str = _IN_WINDOW,
) -> gi.MergedPR:
    return gi.MergedPR(
        number=number,
        title=title,
        body=body,
        head_ref=head_ref,
        base_ref=base_ref,
        merged_at=merged_at,
        url=f"https://github.com/{_REPO}/pull/{number}",
        author="parametrization",
    )


def _state(
    *,
    reviewers: int = 2,
    missing_tech_debt: tuple[str, ...] = (),
    wave_bootstrap: bool = False,
    stale: int = 0,
    head_ref: str = "A.Virtanen/1000-narrow-token",
) -> pr_review_state.ReviewState:
    """Build a ReviewState exactly as `compute_review_state` would return one.

    Constructed rather than mocked so `passes()` — the gate's own pass/fail
    predicate, which this audit must not reimplement — really runs.
    """
    return pr_review_state.ReviewState(
        pr_number="1001",
        repo=_REPO,
        head_ref=head_ref,
        branch_author_lastname="Virtanen",
        formal_reviewers=[],
        comment_reviewers=[f"reviewer {i}" for i in range(reviewers)],
        non_roster_requestors=[],
        distinct_reviewer_count=reviewers,
        wave_bootstrap_exception=wave_bootstrap,
        reviews_missing_tech_debt=list(missing_tech_debt),
        tech_debt_issue_numbers=[],
        content_sha="ac8bcfa1234567",
        content_ts="2026-08-09T10:00:00+00:00",
        stale_verdicts=[
            {
                "reviewer": f"stale {i}",
                "verdict": "Approved",
                "created_at": "2026-08-01T00:00:00Z",
                "source": "comment",
            }
            for i in range(stale)
        ],
    )


def _rest_entry(
    number: int,
    *,
    merged_at: str | None = _IN_WINDOW,
    updated_at: str | None = None,
    head_ref: str = "A.Virtanen/1000-narrow-token",
    title: str = "fix: something",
    body: str = "",
) -> dict:
    return {
        "number": number,
        "title": title,
        "body": body,
        "head": {"ref": head_ref},
        "base": {"ref": "main"},
        "merged_at": merged_at,
        "updated_at": updated_at if updated_at is not None else (merged_at or _IN_WINDOW),
        "html_url": f"https://github.com/{_REPO}/pull/{number}",
        "user": {"login": "parametrization"},
        "state": "closed",
    }


def _pager(pages: list[list[dict]]):
    """A `run_gh` stub returning one JSON page per call, then empty pages."""
    calls: list[str] = []

    def _run(args: list[str]) -> str:
        calls.append(args[-1])
        index = len(calls) - 1
        return json.dumps(pages[index] if index < len(pages) else [])

    _run.calls = calls  # type: ignore[attr-defined]
    return _run


# ---------------------------------------------------------------------------
# 1 + 2. Classification and exemption identification
# ---------------------------------------------------------------------------


class ClassificationTests(unittest.TestCase):
    def test_two_reviewers_is_pass(self):
        row = gi.classify(_REPO, _pr(), _state(reviewers=2))
        self.assertEqual(row.verdict, gi.VERDICT_PASS)
        self.assertEqual(row.reviewers, 2)
        self.assertEqual(row.exception_class, "")

    def test_wave_bootstrap_single_reviewer_is_pass_not_exempt(self):
        """The GATE applies this exception, so the replay reports PASS.

        Re-recognising it here as an EXEMPT class would double-count it, and
        would mark a PR exempt in cases where the gate's own
        `is_single_reviewer_exception` said no.
        """
        row = gi.classify(_REPO, _pr(), _state(reviewers=1, wave_bootstrap=True))
        self.assertEqual(row.verdict, gi.VERDICT_PASS)
        self.assertEqual(row.exception_class, "")

    def test_zero_reviewers_non_exempt_is_unreviewed(self):
        row = gi.classify(_REPO, _pr(number=1467), _state(reviewers=0))
        self.assertEqual(row.verdict, gi.VERDICT_UNREVIEWED)
        self.assertEqual(row.reviewers, 0)
        self.assertIn("0/2", row.reason)

    def test_one_reviewer_non_exempt_is_unreviewed(self):
        row = gi.classify(_REPO, _pr(), _state(reviewers=1))
        self.assertEqual(row.verdict, gi.VERDICT_UNREVIEWED)

    def test_two_reviewers_missing_tech_debt_is_unreviewed(self):
        row = gi.classify(_REPO, _pr(), _state(reviewers=2, missing_tech_debt=("Nino",)))
        self.assertEqual(row.verdict, gi.VERDICT_UNREVIEWED)
        self.assertIn("TechDebt", row.reason)

    def test_stale_verdicts_are_named_in_the_reason(self):
        """A count that silently drops verdicts reads to an operator as a broken
        tool (the #950 diagnostic lesson) — so the exclusion must be stated."""
        row = gi.classify(_REPO, _pr(), _state(reviewers=0, stale=2))
        self.assertEqual(row.verdict, gi.VERDICT_UNREVIEWED)
        self.assertIn("stale", row.reason)
        self.assertIn("ac8bcfa1", row.reason)

    # -- wave-merge -------------------------------------------------------

    def test_wave_to_main_pr_is_exempt_not_unreviewed(self):
        """The issue's headline false-positive case: an integration PR carries
        0/2 by design (wave-merge.md point 5) and must not be a finding."""
        pr = _pr(head_ref="deployments/phase-10/wave-30", base_ref="main")
        row = gi.classify(_REPO, pr, None)
        self.assertEqual(row.verdict, gi.VERDICT_EXEMPT)
        self.assertEqual(row.exception_class, gi.EXCEPTION_WAVE_MERGE)

    def test_wave_to_main_undashed_phase_form_is_also_exempt(self):
        """4 of 8 repos emit `deployments/phase10/wave-4`; the gate's shared
        predicate accepts both spellings, so the audit does too."""
        pr = _pr(head_ref="deployments/phase10/wave-4")
        self.assertEqual(gi.classify(_REPO, pr, None).verdict, gi.VERDICT_EXEMPT)

    def test_wave_merge_exemption_reports_reviewers_as_not_measured(self):
        """`None`, never `0`. A `0` would read as a measurement of zero
        approvals rather than as "the replay was skipped" (#1206)."""
        pr = _pr(head_ref="deployments/phase-10/wave-30")
        self.assertIsNone(gi.classify(_REPO, pr, None).reviewers)

    def test_wave_merge_exemption_uses_the_gates_own_predicate(self):
        """Keyed off `charter_trailer.is_wave_branch` — the same function the
        merge gate uses — not a local path regex that could drift from it."""
        pr = _pr(head_ref="deployments/phase-10/wave-30")
        with mock.patch.object(gi.charter_trailer, "is_wave_branch") as is_wave:
            is_wave.return_value = True
            gi.recognise_exception_class(pr)
        is_wave.assert_called_once_with("deployments/phase-10/wave-30")

    def test_near_miss_deployment_refs_are_not_exempt(self):
        """`deployments/phase-3/wave-6-hotfix` is NOT a wave branch (the gate's
        pattern is anchored at both ends), so it gets no free pass."""
        for ref in (
            "deployments/phase-3/wave-6-hotfix",
            "deployments/phase12/cleanup",
            "deployments/phase-10/wave-30/extra",
        ):
            with self.subTest(ref=ref):
                row = gi.classify(_REPO, _pr(head_ref=ref), _state(reviewers=0))
                self.assertEqual(row.verdict, gi.VERDICT_UNREVIEWED)

    def test_wave_merge_exemption_is_not_the_wave_integration_scan_mode(self):
        """#1216's `wave-integration` comment-scan mode governs SELF-REVIEW
        EXCLUSION — it makes reaching 2 easier, not unnecessary. Keying the
        exemption off it would conflate two unrelated rules, so this audit must
        never consult it."""
        source = Path(gi.__file__).read_text(encoding="utf-8")
        # The constant may be NAMED in prose (the docstring explains the trap);
        # what must not exist is a comparison against it.
        self.assertNotIn("COMMENT_SCAN_WAVE_INTEGRATION", source.split('"""', 2)[2])
        self.assertNotIn("comment_scan ==", source)

    # -- emergency --------------------------------------------------------

    def test_emergency_prefixed_pr_is_exempt(self):
        pr = _pr(title="[EMERGENCY] restore prod graph from B2 snapshot")
        row = gi.classify(_REPO, pr, None)
        self.assertEqual(row.verdict, gi.VERDICT_EXEMPT)
        self.assertEqual(row.exception_class, gi.EXCEPTION_EMERGENCY)

    def test_emergency_marker_must_be_a_prefix_not_a_mention(self):
        """`emergency-mode.md` mandates the PREFIX. An incidental mention must
        not buy an exemption, or the marker becomes a magic word."""
        pr = _pr(title="revert the [EMERGENCY] hotfix now that prod is stable")
        row = gi.classify(_REPO, pr, _state(reviewers=0))
        self.assertEqual(row.verdict, gi.VERDICT_UNREVIEWED)

    # -- doc-sweep --------------------------------------------------------

    def test_doc_sweep_with_one_reviewer_is_exempt(self):
        pr = _pr(body="Sweep: parent tracking issue #900\n\nByte-identical diff.")
        row = gi.classify(_REPO, pr, _state(reviewers=1))
        self.assertEqual(row.verdict, gi.VERDICT_EXEMPT)
        self.assertEqual(row.exception_class, gi.EXCEPTION_DOC_SWEEP)

    def test_doc_sweep_with_zero_reviewers_is_unreviewed(self):
        """That class grants a SINGLE-reviewer exception, not a zero-reviewer
        one — the marker buys a reduced threshold, not an unreviewed merge."""
        pr = _pr(body="Sweep: parent tracking issue #900")
        row = gi.classify(_REPO, pr, _state(reviewers=0))
        self.assertEqual(row.verdict, gi.VERDICT_UNREVIEWED)
        self.assertEqual(row.exception_class, "")

    def test_doc_sweep_missing_tech_debt_is_unreviewed(self):
        pr = _pr(body="Sweep: parent tracking issue #900")
        row = gi.classify(_REPO, pr, _state(reviewers=1, missing_tech_debt=("Aino",)))
        self.assertEqual(row.verdict, gi.VERDICT_UNREVIEWED)
        self.assertIn("TechDebt", row.reason)

    def test_doc_sweep_marker_must_start_a_line(self):
        """A mid-sentence mention is prose, not a declaration."""
        pr = _pr(body="The charter says the body must carry a Sweep: line citing the issue.")
        row = gi.classify(_REPO, pr, _state(reviewers=1))
        self.assertEqual(row.verdict, gi.VERDICT_UNREVIEWED)

    # -- undetermined -----------------------------------------------------

    def test_replay_error_is_undetermined_never_pass(self):
        row = gi.classify(_REPO, _pr(), None, error="gh pr view failed: HTTP 502")
        self.assertEqual(row.verdict, gi.VERDICT_UNDETERMINED)
        self.assertIsNone(row.reviewers)
        self.assertIn("502", row.reason)

    def test_missing_state_without_error_is_undetermined_not_pass(self):
        """Defensive: an absent measurement is not a passing one."""
        row = gi.classify(_REPO, _pr(), None)
        self.assertEqual(row.verdict, gi.VERDICT_UNDETERMINED)

    def test_every_verdict_has_a_render_mark(self):
        """Totality — an unhandled verdict must not render as a confident,
        specific, WRONG one (the `COMMENT_SCAN_*` catch-all lesson, main#1273)."""
        for verdict in gi.ALL_VERDICTS:
            self.assertIn(verdict, gi._MARKS)

    def test_every_classification_carries_a_reason(self):
        rows = [
            gi.classify(_REPO, _pr(), _state(reviewers=2)),
            gi.classify(_REPO, _pr(head_ref="deployments/phase-10/wave-30"), None),
            gi.classify(_REPO, _pr(title="[EMERGENCY] restore"), None),
            gi.classify(_REPO, _pr(body="Sweep: #900"), _state(reviewers=1)),
            gi.classify(_REPO, _pr(), _state(reviewers=0)),
            gi.classify(_REPO, _pr(), None, error="boom"),
        ]
        for row in rows:
            with self.subTest(verdict=row.verdict):
                self.assertTrue(row.reason.strip())


# ---------------------------------------------------------------------------
# 3. Enumeration — the REST walk and its fail-closed paths
# ---------------------------------------------------------------------------


class FetchMergedPrsTests(unittest.TestCase):
    def test_only_in_window_merges_are_collected(self):
        run = _pager(
            [
                [
                    _rest_entry(10, merged_at=_IN_WINDOW),
                    _rest_entry(9, merged_at=_BEFORE_WINDOW, updated_at=_IN_WINDOW),
                    _rest_entry(8, merged_at=None, updated_at=_IN_WINDOW),
                ]
            ]
        )
        prs = gi.fetch_merged_prs(_REPO, _SINCE, run_gh=run)
        self.assertEqual([p.number for p in prs], [10])

    def test_until_bound_excludes_later_merges(self):
        run = _pager([[_rest_entry(10, merged_at="2026-08-20T00:00:00Z")]])
        until = datetime(2026, 8, 15, tzinfo=timezone.utc)
        self.assertEqual(gi.fetch_merged_prs(_REPO, _SINCE, until, run_gh=run), [])

    def test_walk_stops_at_the_first_wholly_out_of_window_page(self):
        run = _pager(
            [
                [_rest_entry(10)],
                [_rest_entry(9, merged_at=_BEFORE_WINDOW, updated_at=_BEFORE_WINDOW)],
                [_rest_entry(8)],  # would be reached only by an over-long walk
            ]
        )
        prs = gi.fetch_merged_prs(_REPO, _SINCE, run_gh=run)
        self.assertEqual([p.number for p in prs], [10])
        self.assertEqual(len(run.calls), 2)

    def test_unparseable_updated_at_keeps_the_walk_going(self):
        """The stop condition must fail SAFE: an unknown `updated_at` must not
        end the walk, or the population is silently truncated."""
        run = _pager([[_rest_entry(9, merged_at=None, updated_at="not-a-date")], [_rest_entry(8)]])
        prs = gi.fetch_merged_prs(_REPO, _SINCE, run_gh=run)
        self.assertEqual([p.number for p in prs], [8])

    def test_gh_failure_raises_rather_than_returning_an_empty_population(self):
        """Under GraphQL exhaustion a failed call's empty output reads as a
        legitimate zero (`feedback_gh_cli_gotchas` §12) — which here would mean
        'zero unreviewed merges', the most dangerous possible wrong answer."""

        def _boom(_args):
            raise gi.GhError("HTTP 502")

        with self.assertRaises(gi.GateIntegrityError):
            gi.fetch_merged_prs(_REPO, _SINCE, run_gh=_boom)

    def test_malformed_json_raises(self):
        with self.assertRaises(gi.GateIntegrityError):
            gi.fetch_merged_prs(_REPO, _SINCE, run_gh=lambda _a: "not json")

    def test_non_list_payload_raises(self):
        with self.assertRaises(gi.GateIntegrityError):
            gi.fetch_merged_prs(_REPO, _SINCE, run_gh=lambda _a: '{"message":"Not Found"}')

    def test_unparseable_merged_at_raises_rather_than_dropping_the_pr(self):
        run = _pager([[_rest_entry(10, merged_at="yesterday")]])
        with self.assertRaises(gi.GateIntegrityError):
            gi.fetch_merged_prs(_REPO, _SINCE, run_gh=run)

    def test_page_ceiling_raises_rather_than_truncating(self):
        run = _pager([[_rest_entry(n)] for n in range(50)])
        with mock.patch.object(gi, "_MAX_PAGES", 3):
            with self.assertRaises(gi.GateIntegrityError) as ctx:
                gi.fetch_merged_prs(_REPO, _SINCE, run_gh=run)
        self.assertIn("partial population", str(ctx.exception))

    def test_empty_first_page_returns_empty_without_error(self):
        self.assertEqual(gi.fetch_merged_prs(_REPO, _SINCE, run_gh=lambda _a: "[]"), [])

    def test_run_gh_wraps_a_subprocess_failure_as_gh_error(self):
        err = subprocess.CalledProcessError(1, ["gh"], stderr="rate limit exceeded")
        with mock.patch.object(gi.gh, "run_gh", side_effect=err):
            with self.assertRaises(gi.GhError):
                gi._run_gh(["api", "x"])

    def test_run_gh_wraps_a_missing_binary_as_gh_error(self):
        with mock.patch.object(gi.gh, "run_gh", side_effect=FileNotFoundError()):
            with self.assertRaises(gi.GhError):
                gi._run_gh(["api", "x"])


# ---------------------------------------------------------------------------
# 4. Aggregation, reuse of the shared entry point, and the CLI contract
# ---------------------------------------------------------------------------


class AuditTests(unittest.TestCase):
    def _audit(self, prs, states):
        """Run `audit` over fixtures. `states` maps PR number -> ReviewState or
        an exception instance to raise."""

        def _fetch(_repo, _since, _until=None):
            return prs

        def _compute(number, repo=None):
            outcome = states[int(number)]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        return gi.audit([_REPO], _SINCE, fetch=_fetch, compute=_compute)

    def test_clean_window_exits_zero(self):
        result = self._audit([_pr(1)], {1: _state(reviewers=2)})
        self.assertTrue(result.verified)
        self.assertEqual(result.exit_code(), 0)

    def test_an_unreviewed_merge_exits_one(self):
        result = self._audit([_pr(1)], {1: _state(reviewers=0)})
        self.assertEqual(result.exit_code(), 1)
        self.assertEqual([r.number for r in result.unreviewed], [1])

    def test_a_gh_failure_exits_two_and_never_zero(self):
        """The issue's third named acceptance case."""
        result = self._audit(
            [_pr(1)], {1: pr_review_state.ReviewStateError("could not fetch PR #1")}
        )
        self.assertTrue(result.undetermined)
        self.assertEqual(result.exit_code(), 2)
        self.assertNotEqual(result.exit_code(), 0)

    def test_undetermined_outranks_unreviewed(self):
        """With rows unreplayable, the UNREVIEWED count is a LOWER BOUND;
        exiting 1 would present a lower bound as a complete finding."""
        result = self._audit(
            [_pr(1), _pr(2)],
            {1: _state(reviewers=0), 2: pr_review_state.ReviewStateError("HTTP 502")},
        )
        self.assertEqual(result.exit_code(), 2)

    def test_wave_merge_pr_never_calls_the_verdict_replay(self):
        """Exempt-by-ref PRs skip the replay, so a transient gh failure cannot
        turn a known-exempt integration PR into an UNDETERMINED finding."""
        calls: list[str] = []

        def _compute(number, repo=None):
            calls.append(number)
            raise AssertionError("the replay must not run for a wave-merge PR")

        result = gi.audit(
            [_REPO],
            _SINCE,
            fetch=lambda *_a: [_pr(1, head_ref="deployments/phase-10/wave-30")],
            compute=_compute,
        )
        self.assertEqual(calls, [])
        self.assertEqual(result.exit_code(), 0)

    def test_enumeration_failure_propagates_as_undetermined(self):
        def _fetch(*_a):
            raise gi.GateIntegrityError("could not list merged PRs")

        with self.assertRaises(gi.GateIntegrityError):
            gi.audit([_REPO], _SINCE, fetch=_fetch, compute=lambda *_a, **_k: _state())

    def test_enforcement_rate_over_an_empty_denominator_is_not_measured(self):
        """A rate over zero non-exempt merges is NOT 100% — reporting it as
        1.0 would print a reassuring number for a window that measured
        nothing."""
        result = gi.audit(
            [_REPO],
            _SINCE,
            fetch=lambda *_a: [_pr(1, head_ref="deployments/phase-10/wave-30")],
            compute=lambda *_a, **_k: _state(),
        )
        self.assertIsNone(result.enforcement_rate)
        self.assertIn("NOT MEASURED", gi.render_text(result))

    def test_enforcement_rate_excludes_exempt_merges_from_the_denominator(self):
        result = self._audit(
            [_pr(1), _pr(2), _pr(3, head_ref="deployments/phase-10/wave-30")],
            {1: _state(reviewers=2), 2: _state(reviewers=0)},
        )
        self.assertAlmostEqual(result.enforcement_rate, 0.5)

    def test_render_text_names_every_finding(self):
        result = self._audit([_pr(1467), _pr(2)], {1467: _state(reviewers=0), 2: _state()})
        text = gi.render_text(result)
        self.assertIn("#1467", text)
        self.assertIn("UNREV", text)

    def test_render_json_is_machine_readable_and_carries_the_exit_code(self):
        result = self._audit([_pr(1)], {1: _state(reviewers=0)})
        payload = json.loads(gi.render_json(result))
        self.assertEqual(payload["exit_code"], 1)
        self.assertFalse(payload["verified"])
        self.assertEqual(payload["counts"][gi.VERDICT_UNREVIEWED], 1)
        self.assertEqual(payload["rows"][0]["number"], 1)


class SharedEntryPointTests(unittest.TestCase):
    """The audit must REUSE the gate's verdict logic, never fork it (main#1046).

    A fork drifts silently: the #1046 driver re-assembled the pipeline with its
    own argument list, omitted `content_ts`, and reported PASS on approvals the
    gate rejects.
    """

    def test_default_verdict_source_is_the_shared_driver(self):
        for func in (gi.audit_repo, gi.audit):
            with self.subTest(func=func.__name__):
                default = inspect.signature(func).parameters["compute"].default
                self.assertIs(default, pr_review_state.compute_review_state)

    def test_the_shared_driver_delegates_to_the_gates_own_entry_point(self):
        """`pr_review_state` in turn calls `resolve_review_verdicts` — the
        single shared pipeline `validate_pr_review.check()` uses. This audit
        therefore replays the gate, not a copy of it."""
        with (
            mock.patch.object(
                pr_review_state.gate,
                "get_pr_data",
                return_value={
                    "author": "a",
                    "number": "1",
                    "reviews": [],
                    "headRefName": "A.Virtanen/1-x",
                    "labels": [],
                },
            ),
            mock.patch.object(pr_review_state.gate, "resolve_review_verdicts") as resolve,
        ):
            resolve.side_effect = pr_review_state.gate.CommitFetchError("no commits")
            with self.assertRaises(pr_review_state.ReviewStateError):
                pr_review_state.compute_review_state("1", repo=_REPO)
        resolve.assert_called_once()

    def test_this_module_does_not_import_the_gate_directly(self):
        """Reaching past `pr_review_state` into `validate_pr_review` would let
        this module assemble its own argument list — exactly the #1046 shape."""
        source = Path(gi.__file__).read_text(encoding="utf-8")
        body = source.split('"""', 2)[2]
        self.assertNotIn("import validate_pr_review", body)
        self.assertNotIn("resolve_review_verdicts(", body)


class CliTests(unittest.TestCase):
    def test_unparseable_since_exits_two(self):
        self.assertEqual(gi.main([_REPO, "--since", "yesterday"]), 2)

    def test_inverted_window_exits_two_rather_than_auditing_nothing(self):
        code = gi.main(
            [_REPO, "--since", "2026-08-10T00:00:00Z", "--until", "2026-08-01T00:00:00Z"]
        )
        self.assertEqual(code, 2)

    def test_unexpanded_repo_variable_exits_two(self):
        """`$DA` is not a repo and never will be (main#981) — name it, don't
        send the operator to re-check `gh auth status`."""
        self.assertEqual(gi.main(["$DA", "--since", "2026-08-01T00:00:00Z"]), 2)

    def test_enumeration_failure_exits_two(self):
        with mock.patch.object(
            gi, "audit", side_effect=gi.GateIntegrityError("could not list merged PRs")
        ):
            self.assertEqual(gi.main([_REPO, "--since", "2026-08-01T00:00:00Z"]), 2)

    def test_since_before_the_content_binding_epoch_warns(self):
        with mock.patch.object(gi, "audit", return_value=gi.AuditResult("s", None, [], [])):
            with mock.patch("sys.stderr") as err:
                gi.main([_REPO, "--since", "2026-01-01T00:00:00Z"])
        printed = "".join(str(call) for call in err.write.call_args_list)
        self.assertIn("content-binding", printed)


# ---------------------------------------------------------------------------
# 5. MUTATION harness
# ---------------------------------------------------------------------------


def _probe_wave_merge_exempt() -> None:
    row = gi.classify(_REPO, _pr(head_ref="deployments/phase-10/wave-30"), None)
    assert row.verdict == gi.VERDICT_EXEMPT, row.verdict


def _probe_unreviewed_is_flagged() -> None:
    row = gi.classify(_REPO, _pr(), _state(reviewers=0))
    assert row.verdict == gi.VERDICT_UNREVIEWED, row.verdict


def _probe_one_reviewer_is_flagged() -> None:
    row = gi.classify(_REPO, _pr(), _state(reviewers=1))
    assert row.verdict == gi.VERDICT_UNREVIEWED, row.verdict


def _probe_two_reviewers_pass() -> None:
    row = gi.classify(_REPO, _pr(), _state(reviewers=2))
    assert row.verdict == gi.VERDICT_PASS, row.verdict


def _probe_emergency_exempt() -> None:
    row = gi.classify(_REPO, _pr(title="[EMERGENCY] restore prod"), None)
    assert row.verdict == gi.VERDICT_EXEMPT, row.verdict


def _probe_emergency_mention_not_exempt() -> None:
    row = gi.classify(_REPO, _pr(title="revert the [EMERGENCY] hotfix"), _state(reviewers=1))
    assert row.verdict == gi.VERDICT_UNREVIEWED, row.verdict


def _probe_doc_sweep_with_reviewer_exempt() -> None:
    row = gi.classify(_REPO, _pr(body="Sweep: #900"), _state(reviewers=1))
    assert row.verdict == gi.VERDICT_EXEMPT, row.verdict


def _probe_doc_sweep_without_reviewer_flagged() -> None:
    row = gi.classify(_REPO, _pr(body="Sweep: #900"), _state(reviewers=0))
    assert row.verdict == gi.VERDICT_UNREVIEWED, row.verdict


def _probe_doc_sweep_mention_not_exempt() -> None:
    row = gi.classify(_REPO, _pr(body="the body must carry a Sweep: line"), _state(reviewers=1))
    assert row.verdict == gi.VERDICT_UNREVIEWED, row.verdict


def _probe_replay_error_undetermined() -> None:
    row = gi.classify(_REPO, _pr(), None, error="HTTP 502")
    assert row.verdict == gi.VERDICT_UNDETERMINED, row.verdict


def _probe_undetermined_exits_two() -> None:
    result = gi.AuditResult("s", None, [_REPO], [gi.classify(_REPO, _pr(), None, error="HTTP 502")])
    assert result.exit_code() == 2, result.exit_code()


def _probe_unreviewed_exits_one() -> None:
    result = gi.AuditResult("s", None, [_REPO], [gi.classify(_REPO, _pr(), _state(reviewers=0))])
    assert result.exit_code() == 1, result.exit_code()


def _probe_clean_exits_zero() -> None:
    result = gi.AuditResult("s", None, [_REPO], [gi.classify(_REPO, _pr(), _state(reviewers=2))])
    assert result.exit_code() == 0, result.exit_code()


def _probe_out_of_window_merge_excluded() -> None:
    run = _pager([[_rest_entry(9, merged_at=_BEFORE_WINDOW, updated_at=_IN_WINDOW)]])
    assert gi.fetch_merged_prs(_REPO, _SINCE, run_gh=run) == []


def _probe_empty_denominator_is_not_a_rate() -> None:
    result = gi.AuditResult(
        "s",
        None,
        [_REPO],
        [gi.classify(_REPO, _pr(head_ref="deployments/phase-10/wave-30"), None)],
    )
    assert result.enforcement_rate is None, result.enforcement_rate


#: Every probe the mutation harness runs. Each is a contract this audit must
#: hold; a mutation is "caught" when it makes at least one of these fail.
_PROBES = (
    ("wave-merge PR is EXEMPT", _probe_wave_merge_exempt),
    ("0-reviewer PR is UNREVIEWED", _probe_unreviewed_is_flagged),
    ("1-reviewer PR is UNREVIEWED", _probe_one_reviewer_is_flagged),
    ("2-reviewer PR is PASS", _probe_two_reviewers_pass),
    ("[EMERGENCY]-prefixed PR is EXEMPT", _probe_emergency_exempt),
    ("[EMERGENCY] mid-title is NOT exempt", _probe_emergency_mention_not_exempt),
    ("doc sweep + 1 reviewer is EXEMPT", _probe_doc_sweep_with_reviewer_exempt),
    ("doc sweep + 0 reviewers is UNREVIEWED", _probe_doc_sweep_without_reviewer_flagged),
    ("doc-sweep marker mid-sentence is NOT exempt", _probe_doc_sweep_mention_not_exempt),
    ("replay error is UNDETERMINED", _probe_replay_error_undetermined),
    ("UNDETERMINED exits 2", _probe_undetermined_exits_two),
    ("UNREVIEWED exits 1", _probe_unreviewed_exits_one),
    ("clean window exits 0", _probe_clean_exits_zero),
    ("out-of-window merge is excluded", _probe_out_of_window_merge_excluded),
    ("empty denominator yields no rate", _probe_empty_denominator_is_not_a_rate),
)


@contextlib.contextmanager
def _always(module, name, value):
    with mock.patch.object(module, name, lambda *_a, **_k: value):
        yield


@contextlib.contextmanager
def _attr(module, name, value):
    with mock.patch.object(module, name, value):
        yield


@contextlib.contextmanager
def _prop(cls, name, getter):
    with mock.patch.object(cls, name, property(getter)):
        yield


#: (label, mutation-factory). Each mutation is a defect a plausible edit could
#: introduce; the harness asserts every one is caught.
_MUTATIONS = (
    (
        "is_wave_branch always False (wave-merge exemption removed)",
        lambda: _always(gi.charter_trailer, "is_wave_branch", False),
    ),
    (
        "is_wave_branch always True (every PR exempted)",
        lambda: _always(gi.charter_trailer, "is_wave_branch", True),
    ),
    (
        "emergency prefix pattern never matches",
        lambda: _attr(gi, "_EMERGENCY_TITLE_RE", re.compile(r"(?!x)x")),
    ),
    (
        "emergency prefix pattern unanchored (a mention buys an exemption)",
        lambda: _attr(gi, "_EMERGENCY_TITLE_RE", re.compile(r"\[EMERGENCY\]", re.IGNORECASE)),
    ),
    (
        "doc-sweep body pattern never matches",
        lambda: _attr(gi, "_DOC_SWEEP_BODY_RE", re.compile(r"(?!x)x")),
    ),
    (
        "doc-sweep body pattern unanchored (prose buys an exemption)",
        lambda: _attr(gi, "_DOC_SWEEP_BODY_RE", re.compile(r"Sweep:", re.IGNORECASE)),
    ),
    (
        "doc-sweep threshold dropped to 0 reviewers",
        lambda: _attr(gi, "_DOC_SWEEP_MIN_REVIEWERS", 0),
    ),
    (
        "recognise_exception_class returns doc-sweep for everything",
        lambda: _always(gi, "recognise_exception_class", gi.EXCEPTION_DOC_SWEEP),
    ),
    (
        "recognise_exception_class returns None for everything",
        lambda: _always(gi, "recognise_exception_class", None),
    ),
    (
        "ReviewState.passes() always True (gate replay ignored)",
        lambda: _prop(pr_review_state.ReviewState, "passes", lambda self: lambda: True),
    ),
    (
        "AuditResult.undetermined always False (exit 2 unreachable)",
        lambda: _prop(gi.AuditResult, "undetermined", lambda self: False),
    ),
    (
        "AuditResult.verified always True (exit 1 unreachable)",
        lambda: _prop(gi.AuditResult, "verified", lambda self: True),
    ),
    (
        "in_window always True (window bound ignored)",
        lambda: _always(gi, "in_window", True),
    ),
    (
        "enforcement_rate reports 1.0 over an empty denominator",
        lambda: _prop(gi.AuditResult, "enforcement_rate", lambda self: 1.0),
    ),
    (
        "REVIEW_THRESHOLD dropped to 1 reviewer",
        lambda: _attr(pr_review_state, "REVIEW_THRESHOLD", 1),
    ),
)


class MutationTests(unittest.TestCase):
    """Prove each assertion above can actually fail.

    Two halves, and both matter. `test_baseline_probes_pass` shows the probes
    describe the CURRENT behaviour; `test_every_mutation_is_caught` shows each
    of them is load-bearing. A probe that passes under every mutation is inert —
    it looks like coverage and measures nothing.
    """

    def test_baseline_probes_pass(self):
        for label, probe in _PROBES:
            with self.subTest(probe=label):
                probe()

    def test_every_mutation_is_caught(self):
        for label, factory in _MUTATIONS:
            with self.subTest(mutation=label):
                caught: list[str] = []
                with factory():
                    for probe_label, probe in _PROBES:
                        try:
                            probe()
                        except Exception:  # noqa: BLE001 — any failure is a catch
                            caught.append(probe_label)
                self.assertTrue(
                    caught,
                    f"MUTATION SURVIVED: {label!r} changed no probe's outcome. The "
                    "assertions covering it are inert — they cannot fail, so they are "
                    "not evidence.",
                )

    def test_the_probe_set_itself_is_not_trivially_satisfied(self):
        """A guard on the guard: at least one probe must survive each mutation
        too, or the harness is just asserting that everything breaks."""
        for label, factory in _MUTATIONS:
            with self.subTest(mutation=label):
                survived = 0
                with factory():
                    for _probe_label, probe in _PROBES:
                        try:
                            probe()
                            survived += 1
                        except Exception:  # noqa: BLE001
                            pass
                self.assertGreater(survived, 0, f"{label}: every probe failed at once")


if __name__ == "__main__":
    unittest.main()
