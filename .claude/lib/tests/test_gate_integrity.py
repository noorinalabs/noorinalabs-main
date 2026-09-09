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
  4b. STRUCTURAL PINS (main#1480) — the two non-drift properties in 2 and 4 are
     absence assertions, and an absence assertion is worth exactly what its
     detector is worth. The detectors used to be `assertNotIn` over raw source
     text, which pinned one SPELLING each: six of seven equivalent respellings
     passed the whole suite untouched at origin/main `a65ddeb`. They are now an
     AST walk over what the module EVALUATES, and `StructuralPinTests` runs every
     respelling through the old detector and the new one so the delta is
     measured here rather than claimed in a commit message.
  5. MUTATION — `MutationTests` applies a table of defects to the module and
     asserts each one is CAUGHT by exactly the probes declared for it. An
     assertion no fixture can trip is not evidence (cf. the inert Gates row on
     main#1474, which passed identically with all three hashes zeroed, and the
     vendored base-pin gate silent on 4 of 8 mutants at deploy#707) — and
     neither is a mutation table drawn only from the region the probes happen to
     reach (main#1481, which is why the probe set now spans `audit_repo`,
     `fetch_merged_prs` and `render_text` too).
"""

from __future__ import annotations

import ast
import contextlib
import dataclasses
import inspect
import json
import re
import subprocess
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, NamedTuple
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


def _row(
    *,
    number: int = 1001,
    verdict: str = gi.VERDICT_PASS,
    exception_class: str = "",
    reviewers: int | None = 2,
    title: str = "fix(hooks): narrow the path token",
    head_ref: str = "A.Virtanen/1000-narrow-token",
) -> gi.Classification:
    """Build a `Classification` DIRECTLY, without going through `classify`.

    Used by the aggregation and rendering probes added for main#1481 so that
    each probe exercises one region: a probe that reached `render_text` via
    `classify` would be killed by every classifier mutation as well, and the
    per-mutation kill sets below would stop saying which region each mutation
    actually damages.
    """
    return gi.Classification(
        repo=_REPO,
        number=number,
        title=title,
        head_ref=head_ref,
        merged_at=_IN_WINDOW,
        url=f"https://github.com/{_REPO}/pull/{number}",
        verdict=verdict,
        exception_class=exception_class,
        reviewers=reviewers,
        reason="fixture",
    )


# ---------------------------------------------------------------------------
# Structural surface of gate_integrity.py (main#1480)
#
# The two non-drift properties below used to be pinned with `assertNotIn` over
# the module's raw source text. A source-text grep pins the SPELLING of a
# defect, not the defect: measured against origin/main `a65ddeb`, six of seven
# equivalent respellings of the two defects passed the whole suite untouched.
# These helpers replace the greps with an AST walk over what the module
# actually EVALUATES, so a respelling has nothing to hide behind.
# ---------------------------------------------------------------------------


def _fold_str(node: ast.AST) -> str | None:
    """Constant-fold a string expression, or None if it is not one.

    Handles the literal, `"a" + "b"` concatenation, and an f-string whose parts
    are all constant. Without folding, `"wave-" + "integration"` walks straight
    past a literal-only check — which is exactly the class of evasion the
    source-text greps this replaces were blind to.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _fold_str(node.left), _fold_str(node.right)
        if left is not None and right is not None:
            return left + right
    if isinstance(node, ast.JoinedStr):
        parts = [_fold_str(value) for value in node.values]
        if parts and all(part is not None for part in parts):
            return "".join(part for part in parts if part is not None)
    return None


def _dotted(node: ast.AST) -> str | None:
    """Render an attribute chain rooted at a plain name, e.g. `a.b.c`."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return f"{base}.{node.attr}" if base is not None else None
    return None


class _ExecutableSurface(ast.NodeVisitor):
    """Names, attribute chains and string values a module evaluates at runtime.

    DOCSTRINGS ARE EXCLUDED, deliberately and load-bearingly: `gate_integrity`'s
    module docstring both names `COMMENT_SCAN_WAVE_INTEGRATION` and explains why
    the module must never consult it. Prose that documents a trap must stay
    legal; code that walks into it must not. Comments need no handling — they
    are not in the AST at all.
    """

    def __init__(self) -> None:
        self.names: set[str] = set()
        self.attrs: set[str] = set()
        self.dotted: set[str] = set()
        self.strings: set[str] = set()
        self.imported: set[str] = set()
        self._docstrings: set[int] = set()

    def visit_Module(self, node):  # noqa: N802
        self._note_docstring(node)
        self.generic_visit(node)

    visit_ClassDef = visit_FunctionDef = visit_AsyncFunctionDef = visit_Module

    def _note_docstring(self, node) -> None:
        body = getattr(node, "body", None)
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            if isinstance(body[0].value.value, str):
                self._docstrings.add(id(body[0].value))

    def visit_Name(self, node):  # noqa: N802
        self.names.add(node.id)
        self.generic_visit(node)

    def visit_Attribute(self, node):  # noqa: N802
        self.attrs.add(node.attr)
        chain = _dotted(node)
        if chain is not None:
            self.dotted.add(chain)
        self.generic_visit(node)

    def visit_Import(self, node):  # noqa: N802
        for alias in node.names:
            self.imported.add(alias.name)
            self.names.add(alias.asname or alias.name.split(".")[0])
        self.generic_visit(node)

    def visit_ImportFrom(self, node):  # noqa: N802
        if node.module:
            self.imported.add(node.module)
        for alias in node.names:
            self.names.add(alias.asname or alias.name)
        self.generic_visit(node)

    def visit_Constant(self, node):  # noqa: N802
        if id(node) not in self._docstrings and isinstance(node.value, str):
            self.strings.add(node.value)

    def visit_BinOp(self, node):  # noqa: N802
        folded = _fold_str(node)
        if folded is not None:
            self.strings.add(folded)
        self.generic_visit(node)

    def visit_JoinedStr(self, node):  # noqa: N802
        folded = _fold_str(node)
        if folded is not None:
            self.strings.add(folded)
        self.generic_visit(node)


def _surface(source: str) -> _ExecutableSurface:
    visitor = _ExecutableSurface()
    visitor.visit(ast.parse(source))
    return visitor


#: Family A — the module must never key its `wave-merge` exemption off the
#: `wave-integration` COMMENT-SCAN MODE. That mode governs self-review exclusion
#: (#1216): it makes reaching 2 reviewers easier, not unnecessary. Same-sounding
#: name, unrelated rule.
_FORBIDDEN_SCAN_MODE_IDENTIFIERS = ("COMMENT_SCAN_WAVE_INTEGRATION", "comment_scan")
_FORBIDDEN_SCAN_MODE_SUBSTRINGS = ("wave-integration", "COMMENT_SCAN_WAVE_INTEGRATION")

#: Family B — the module must reach the gate ONLY through
#: `pr_review_state.compute_review_state`. Reaching past it — importing the gate,
#: calling `resolve_review_verdicts`, or going through the already-imported
#: `pr_review_state.gate` alias — lets this module assemble its own argument
#: list, which is the #1046 shape verbatim.
_FORBIDDEN_GATE_IDENTIFIERS = ("validate_pr_review", "resolve_review_verdicts")
_FORBIDDEN_GATE_SUBSTRINGS = ("validate_pr_review", "resolve_review_verdicts")
_FORBIDDEN_GATE_CHAIN_PREFIX = "pr_review_state.gate"


def _scan_mode_violations(source: str) -> list[str]:
    """Family-A violations in `source`'s executable surface."""
    surface = _surface(source)
    found = []
    for ident in _FORBIDDEN_SCAN_MODE_IDENTIFIERS:
        if ident in surface.names or ident in surface.attrs:
            found.append(f"references the identifier {ident!r}")
    for literal in surface.strings:
        for needle in _FORBIDDEN_SCAN_MODE_SUBSTRINGS:
            if needle.lower() in literal.lower():
                found.append(f"evaluates the string {literal!r} (contains {needle!r})")
    return found


def _gate_reach_violations(source: str) -> list[str]:
    """Family-B violations in `source`'s executable surface."""
    surface = _surface(source)
    found = []
    for ident in _FORBIDDEN_GATE_IDENTIFIERS:
        if ident in surface.names or ident in surface.attrs:
            found.append(f"references the identifier {ident!r}")
        if ident in surface.imported:
            found.append(f"imports {ident!r}")
    for chain in surface.dotted:
        if chain == _FORBIDDEN_GATE_CHAIN_PREFIX or chain.startswith(
            _FORBIDDEN_GATE_CHAIN_PREFIX + "."
        ):
            found.append(f"reaches the gate through the alias chain {chain!r}")
    for literal in surface.strings:
        for needle in _FORBIDDEN_GATE_SUBSTRINGS:
            if needle in literal:
                found.append(f"evaluates the string {literal!r} (contains {needle!r})")
    return found


def _superseded_source_text_pins(source: str) -> list[str]:
    """The `assertNotIn` greps these structural checks replaced (main#1480).

    Kept — and executed — so the delta between the old pins and the new ones is
    MEASURED in the suite rather than asserted in a commit message. Every
    respelling below records what the old pins said about it, and all but one
    say nothing at all.
    """
    body = source.split('"""', 2)[2]
    hits = []
    if "COMMENT_SCAN_WAVE_INTEGRATION" in body:
        hits.append('assertNotIn("COMMENT_SCAN_WAVE_INTEGRATION", body)')
    if "comment_scan ==" in source:
        hits.append('assertNotIn("comment_scan ==", source)')
    if "import validate_pr_review" in body:
        hits.append('assertNotIn("import validate_pr_review", body)')
    if "resolve_review_verdicts(" in body:
        hits.append('assertNotIn("resolve_review_verdicts(", body)')
    return hits


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
        never consult it.

        Structural, not textual (main#1480): the check walks what the module
        EVALUATES, so the constant stays legal in the docstring that warns about
        it while any respelling of a live reference is caught. See
        `SupersededSourceTextPinTests` for the measured delta.
        """
        violations = _scan_mode_violations(Path(gi.__file__).read_text(encoding="utf-8"))
        self.assertEqual(
            violations,
            [],
            "gate_integrity consults the wave-integration comment-scan mode: "
            + "; ".join(violations),
        )

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
        this module assemble its own argument list — exactly the #1046 shape.

        Structural, not textual (main#1480). The grep this replaced could not
        see `from validate_pr_review import ...`, a `getattr` by string literal,
        or the `pr_review_state.gate` alias — which is the shortest path to the
        drift, since `pr_review_state` is already imported here.
        """
        violations = _gate_reach_violations(Path(gi.__file__).read_text(encoding="utf-8"))
        self.assertEqual(
            violations,
            [],
            "gate_integrity reaches past the shared entry point: " + "; ".join(violations),
        )


# ---------------------------------------------------------------------------
# 4b. The structural pins' own discriminating power (main#1480)
# ---------------------------------------------------------------------------

#: Anchors the respelling mutants are grafted onto. Asserted to occur exactly
#: once before use, so a refactor that moves them fails with "update this
#: anchor" rather than silently grafting nothing and leaving the mutants inert.
_ANCHOR_IMPORT = "import pr_review_state  # noqa: E402"
_ANCHOR_RECOGNISE = "def recognise_exception_class(pr: MergedPR) -> str | None:"
_ANCHOR_WAVE_BRANCH = "    if charter_trailer.is_wave_branch(pr.head_ref):"


def _graft(source: str, anchor: str, insertion: str) -> str:
    """Return `source` with `insertion` placed immediately before `anchor`."""
    return source.replace(anchor, insertion + anchor)


#: (id, family, patch, old-pin hits). `family` selects the structural check the
#: mutant must trip. `old_pin_hits` is what the SUPERSEDED source-text greps say
#: about the same mutant — 0 for all but the naive spelling, which is the whole
#: reason those greps were replaced.
_RESPELLINGS = (
    (
        "A1 the naive spelling — a compare against the gate's own constant",
        "scan_mode",
        lambda src: _graft(
            src,
            _ANCHOR_WAVE_BRANCH,
            '    if getattr(pr, "scan_mode", "") == '
            "pr_review_state.gate.COMMENT_SCAN_WAVE_INTEGRATION:\n"
            "        return EXCEPTION_WAVE_MERGE\n",
        ),
        1,
    ),
    (
        "A2 the same defect via a membership test",
        "scan_mode",
        lambda src: _graft(
            src,
            _ANCHOR_WAVE_BRANCH,
            '    if getattr(pr, "scan_mode", "") in ("wave-integration",):\n'
            "        return EXCEPTION_WAVE_MERGE\n",
        ),
        0,
    ),
    (
        "A3 the same defect via a bare attribute compare",
        "scan_mode",
        lambda src: _graft(
            src,
            _ANCHOR_WAVE_BRANCH,
            '    if getattr(pr, "scan_mode", "") and pr.scan_mode == "wave-integration":\n'
            "        return EXCEPTION_WAVE_MERGE\n",
        ),
        0,
    ),
    (
        "A4 the mode name split across a concatenation",
        "scan_mode",
        lambda src: _graft(
            src,
            _ANCHOR_WAVE_BRANCH,
            '    if getattr(pr, "scan_mode", "") == "wave-" + "integration":\n'
            "        return EXCEPTION_WAVE_MERGE\n",
        ),
        0,
    ),
    (
        "B1 the #1046 shape through the already-imported gate alias",
        "gate_reach",
        lambda src: _graft(
            src,
            _ANCHOR_RECOGNISE,
            "def _replay_via_the_gate_directly(repo: str, pr: MergedPR):\n"
            '    """Local re-assembly of the gate pipeline — the #1046 shape."""\n'
            "    _g = pr_review_state.gate\n"
            '    _rv = getattr(_g, "resolve_review" + "_verdicts")\n'
            "    return _rv(_g.get_pr_data(str(pr.number), repo=repo), repo=repo)\n\n\n",
        ),
        0,
    ),
    (
        "B2 the gate function reached by a string-literal getattr",
        "gate_reach",
        lambda src: _graft(
            src,
            _ANCHOR_RECOGNISE,
            "def _replay_via_the_gate_directly(repo: str, pr: MergedPR):\n"
            '    _rv = getattr(pr_review_state.gate, "resolve_review_verdicts")\n'
            "    return _rv(pr_review_state.gate.get_pr_data(str(pr.number), repo=repo),"
            " repo=repo)\n\n\n",
        ),
        0,
    ),
    (
        "B3 a from-import of the gate function",
        "gate_reach",
        lambda src: _graft(
            src,
            _ANCHOR_IMPORT,
            "from validate_pr_review import resolve_review_verdicts as _rrv  # noqa: E402\n",
        ),
        0,
    ),
)

_CHECKS = {"scan_mode": _scan_mode_violations, "gate_reach": _gate_reach_violations}


class StructuralPinTests(unittest.TestCase):
    """The pins on the pins (main#1480).

    `test_wave_merge_exemption_is_not_the_wave_integration_scan_mode` and
    `test_this_module_does_not_import_the_gate_directly` both assert an ABSENCE.
    An absence assertion is worth exactly what its detector is worth, and the
    detectors these replaced were `assertNotIn` over raw source text — which
    pinned one spelling each. This class measures the difference rather than
    claiming it: every respelling below is run through BOTH detectors.
    """

    def _source(self) -> str:
        return Path(gi.__file__).read_text(encoding="utf-8")

    # -- the analyser is not vacuous --------------------------------------

    def test_the_analyser_actually_reads_the_module(self):
        """Guard on the guard, and the important one.

        A walker that silently returned empty sets would make every absence
        assertion above pass for the wrong reason — the silent-zero shape
        (`feedback_silent_zero_is_not_a_measurement`). So assert it FINDS the
        references the module genuinely has.
        """
        surface = _surface(self._source())
        self.assertIn("pr_review_state.compute_review_state", surface.dotted)
        self.assertIn("charter_trailer.is_wave_branch", surface.dotted)
        self.assertIn("pr_review_state", surface.imported)
        self.assertIn(gi.EXCEPTION_WAVE_MERGE, surface.strings)

    def test_docstring_prose_is_excluded_and_that_exclusion_is_load_bearing(self):
        """The module docstring NAMES the constant in order to warn about it.

        Documenting a trap must stay legal; walking into it must not. This pins
        both halves — the token really is in the file, and really is not in the
        executable surface — so a future "simplification" to a raw-text scan
        fails here instead of banning the warning.
        """
        source = self._source()
        self.assertIn("COMMENT_SCAN_WAVE_INTEGRATION", source)
        surface = _surface(source)
        self.assertNotIn("COMMENT_SCAN_WAVE_INTEGRATION", surface.names | surface.attrs)
        self.assertFalse([s for s in surface.strings if "wave-integration" in s])

    def test_constant_folding_sees_through_a_split_literal(self):
        """Unit-level: the folder is what makes A4 and B1 catchable."""
        self.assertEqual(
            _fold_str(ast.parse('"wave-" + "integration"').body[0].value), "wave-integration"
        )
        self.assertIsNone(_fold_str(ast.parse("x + y").body[0].value))

    # -- the anchors the mutants graft onto --------------------------------

    def test_the_respelling_anchors_still_exist_exactly_once(self):
        """If an anchor moves, say so — an unfound anchor grafts nothing, and a
        mutant that was never applied is trivially "not caught"."""
        source = self._source()
        for anchor in (_ANCHOR_IMPORT, _ANCHOR_RECOGNISE, _ANCHOR_WAVE_BRANCH):
            with self.subTest(anchor=anchor):
                self.assertEqual(
                    source.count(anchor),
                    1,
                    f"anchor {anchor!r} occurs {source.count(anchor)}x in "
                    "gate_integrity.py — update _RESPELLINGS",
                )

    # -- the measured delta -----------------------------------------------

    def test_every_respelling_is_caught_structurally(self):
        """The load-bearing half: each respelling trips its family's check."""
        source = self._source()
        for label, family, patch, _old_hits in _RESPELLINGS:
            with self.subTest(respelling=label):
                mutated = patch(source)
                self.assertNotEqual(mutated, source, "the graft applied nothing")
                violations = _CHECKS[family](mutated)
                self.assertTrue(
                    violations,
                    f"RESPELLING SURVIVED: {label!r} is the same defect in different "
                    "words and the structural check did not see it.",
                )

    def test_the_superseded_greps_missed_six_of_these_seven(self):
        """Why the greps had to go, measured rather than asserted.

        Against origin/main `a65ddeb` the full suite reported `55 passed, 56
        subtests passed` under A2, A3, A4, B1, B2 and B3 — the defect present,
        the pins silent. Only A1, the spelling the pin was written from, failed.
        The counts below are the same measurement taken in-suite, so if someone
        strengthens the old greps this test tells them the delta changed instead
        of leaving a stale claim in a docstring.
        """
        source = self._source()
        self.assertEqual(_superseded_source_text_pins(source), [], "baseline is clean")
        missed = []
        for label, _family, patch, old_hits in _RESPELLINGS:
            with self.subTest(respelling=label):
                hits = _superseded_source_text_pins(patch(source))
                self.assertEqual(
                    len(hits),
                    old_hits,
                    f"{label}: superseded greps now report {hits}, expected {old_hits} hit(s)",
                )
                if not hits:
                    missed.append(label)
        self.assertEqual(len(missed), 6, f"expected 6 of 7 missed by the old pins, got {missed}")

    def test_a_clean_module_is_not_flagged_by_either_check(self):
        """Negative control — without it, a check that returns a violation for
        every input would satisfy every assertion above."""
        source = self._source()
        self.assertEqual(_scan_mode_violations(source), [])
        self.assertEqual(_gate_reach_violations(source), [])


class ExceptionClassDriftTests(unittest.TestCase):
    """The recognisable classes must stay a subset of the CHARTER's list.

    Raised by Santiago Ferreira on main#1480 during the #1478 operational
    review: `gate_integrity`'s exception vocabulary matches
    `validate_pr_ci_status._CHARTER_ADMIN_EXCEPTIONS` today by coincidence, not
    by assertion. A fifth charter class would go silently unrecognised here.

    It fails in the safe direction — an unrecognised class yields a noisy
    UNREVIEWED false positive, not a silent pass — which is why neither reviewer
    gated on it. It is nevertheless the same shape as the pins above: an
    invariant that holds by luck.

    The charter list is read by AST rather than imported, so this test neither
    executes a hook module nor races an in-flight edit to one.
    """

    def _charter_classes(self) -> set[str]:
        hook = Path(gi.__file__).resolve().parent.parent / "hooks" / "validate_pr_ci_status.py"
        tree = ast.parse(hook.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "_CHARTER_ADMIN_EXCEPTIONS"
                for t in node.targets
            ):
                return set(ast.literal_eval(node.value))
        raise AssertionError(
            "_CHARTER_ADMIN_EXCEPTIONS not found in validate_pr_ci_status.py — "
            "it moved or was renamed; retarget this test rather than deleting it"
        )

    def _audit_classes(self) -> set[str]:
        # Derived from the module, not restated, so a NEW `EXCEPTION_*` constant
        # is picked up here without anyone remembering to add it.
        return {v for k, v in vars(gi).items() if k.startswith("EXCEPTION_")}

    def test_the_charter_list_is_readable_and_non_empty(self):
        """Guard on the guard: an unreadable list must not read as agreement."""
        self.assertGreaterEqual(len(self._charter_classes()), 4)

    def test_recognisable_classes_are_a_subset_of_the_charter_list(self):
        unknown = self._audit_classes() - self._charter_classes()
        self.assertEqual(
            unknown,
            set(),
            f"gate_integrity recognises {sorted(unknown)}, which the charter's "
            "admin-merge exception list does not contain",
        )

    def test_the_only_unrecognised_charter_class_is_wave_bootstrap(self):
        """The gap is deliberate and exactly one class wide.

        `wave-bootstrap` is applied by the GATE itself, so a PR covered by it
        replays as PASS and must not be re-recognised here as EXEMPT (that would
        double-count it, and would mark PRs exempt in cases the gate's own
        `is_single_reviewer_exception` rejects). Any OTHER charter class missing
        from the audit is drift: it would classify UNREVIEWED, a false positive
        that gets the whole report ignored within two waves.
        """
        self.assertEqual(self._charter_classes() - self._audit_classes(), {"wave-bootstrap"})


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


# -- probes added for main#1481 ------------------------------------------------
#
# The fifteen probes above all land in `classify`, `AuditResult.exit_code` /
# `enforcement_rate`, and one `fetch_merged_prs` window case. The mutation table
# could therefore only be drawn from that region, and nine plausible defects in
# `audit_repo`, `fetch_merged_prs` and `render_text` survived the whole set —
# measured, not supposed. These reach the rest of the module.


def _probe_audit_repo_skips_the_replay_for_exempt_by_ref() -> None:
    """`audit_repo`'s `needs_review_state` -> `classify` wiring, end to end.

    Asserts BOTH halves, because they fail independently: the verdicts (an
    exempt-by-ref PR must not become UNDETERMINED) and the replay call log (a
    wave-merge PR must not be replayed at all, or a transient gh failure turns a
    known-exempt integration PR into a finding).
    """
    replayed: list[str] = []

    def _compute(number, repo=None):
        replayed.append(number)
        return _state(reviewers=0)

    rows = gi.audit_repo(
        _REPO,
        _SINCE,
        fetch=lambda *_a: [_pr(1, head_ref="deployments/phase-10/wave-30"), _pr(2)],
        compute=_compute,
    )
    verdicts = [row.verdict for row in rows]
    assert verdicts == [gi.VERDICT_EXEMPT, gi.VERDICT_UNREVIEWED], verdicts
    assert replayed == ["2"], replayed


def _probe_audit_repo_surfaces_a_replay_error() -> None:
    """A `ReviewStateError` from the shared driver must reach `classify` as an
    error, not be swallowed into a state-less PASS."""

    def _compute(_number, repo=None):
        raise pr_review_state.ReviewStateError("HTTP 502")

    rows = gi.audit_repo(_REPO, _SINCE, fetch=lambda *_a: [_pr(1)], compute=_compute)
    assert [row.verdict for row in rows] == [gi.VERDICT_UNDETERMINED], rows


def _probe_replay_error_outranks_an_exemption_marker() -> None:
    """The precedence the issue found unpinned: a FAILED replay is not rescued
    by a marker on the PR. Every marker class, because they exit `classify` at
    different points."""
    for pr in (
        _pr(head_ref="deployments/phase-10/wave-30"),
        _pr(title="[EMERGENCY] restore prod"),
        _pr(body="Sweep: #900"),
    ):
        row = gi.classify(_REPO, pr, None, error="HTTP 502")
        assert row.verdict == gi.VERDICT_UNDETERMINED, (pr.head_ref, row.verdict)
        assert row.exception_class == "", row.exception_class


def _probe_fetch_gh_failure_raises() -> None:
    """The module docstring's headline fail-open: an empty population from a
    failed call reads as "zero unreviewed merges"."""

    def _boom(_args):
        raise gi.GhError("HTTP 502")

    try:
        gi.fetch_merged_prs(_REPO, _SINCE, run_gh=_boom)
    except gi.GateIntegrityError:
        return
    raise AssertionError("a gh failure returned a population instead of raising")


def _probe_fetch_until_bound_excludes_later_merges() -> None:
    """The `--until` upper bound. The in-window PR is there on purpose: without
    it, dropping the bound and emptying the population look the same."""
    run = _pager(
        [
            [
                _rest_entry(10, merged_at="2026-08-20T00:00:00Z"),
                _rest_entry(11, merged_at="2026-08-10T00:00:00Z"),
            ]
        ]
    )
    until = datetime(2026, 8, 15, tzinfo=timezone.utc)
    got = [p.number for p in gi.fetch_merged_prs(_REPO, _SINCE, until, run_gh=run)]
    assert got == [11], got


def _probe_fetch_walks_past_the_first_page() -> None:
    """A walk that stops at page 1 truncates the population, which undercounts
    unreviewed merges — silently, and in the unsafe direction."""
    run = _pager([[_rest_entry(10)], [_rest_entry(9)], []])
    got = [p.number for p in gi.fetch_merged_prs(_REPO, _SINCE, run_gh=run)]
    assert got == [10, 9], got


def _probe_render_text_names_a_finding() -> None:
    """A report that measures correctly and prints nothing is not a gate."""
    result = gi.AuditResult(
        "s",
        None,
        [_REPO],
        [_row(number=1467, verdict=gi.VERDICT_UNREVIEWED, reviewers=0), _row(number=2)],
    )
    text = gi.render_text(result)
    assert "#1467" in text, text


def _probe_render_text_labels_a_finding_as_unreviewed() -> None:
    """Separate from the probe above: printing the row under a PASS mark is a
    different defect from not printing it, and only this one catches it.

    Asserted on the FINDING'S OWN LINE, not on the whole report: the summary
    header interpolates the literal word `UNREVIEWED` from the counts, so a
    naive `"UNREV" in text` passes while every row is mislabelled — measured,
    and it is why this probe is written the long way.

    The expected label is spelled out rather than read from `gi._MARKS`, which
    is the table under test; reading it back would make the probe agree with
    whatever the mutation put there.
    """
    result = gi.AuditResult(
        "s", None, [_REPO], [_row(number=1467, verdict=gi.VERDICT_UNREVIEWED, reviewers=0)]
    )
    text = gi.render_text(result)
    rows = [line.strip() for line in text.splitlines() if f"{_REPO}#1467" in line]
    assert len(rows) == 1, text
    assert rows[0].startswith("UNREV"), rows[0]


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
    (
        "audit_repo skips the replay for exempt-by-ref",
        _probe_audit_repo_skips_the_replay_for_exempt_by_ref,
    ),
    ("audit_repo surfaces a replay error", _probe_audit_repo_surfaces_a_replay_error),
    ("replay error outranks an exemption marker", _probe_replay_error_outranks_an_exemption_marker),
    ("fetch raises on a gh failure", _probe_fetch_gh_failure_raises),
    ("fetch honours the --until bound", _probe_fetch_until_bound_excludes_later_merges),
    ("fetch walks past page 1", _probe_fetch_walks_past_the_first_page),
    ("render_text names a finding", _probe_render_text_names_a_finding),
    ("render_text labels a finding UNREVIEWED", _probe_render_text_labels_a_finding_as_unreviewed),
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


# -- mutant implementations for the defects added in main#1481 ----------------
#
# Captured BEFORE any patching so a mutant can delegate to the real function.

_REAL_CLASSIFY = gi.classify
_REAL_FETCH = gi.fetch_merged_prs
_REAL_IN_WINDOW = gi.in_window


def _fetch_swallowing_gh_failures(repo, since, until=None, *, run_gh=None):
    """MUTATION: a gh failure yields the partial population instead of raising.

    The module docstring's own headline fail-open — an empty list from a failed
    call reads to every caller as "zero unreviewed merges".
    """
    try:
        return _REAL_FETCH(repo, since, until, run_gh=run_gh or gi._run_gh)
    except gi.GateIntegrityError:
        return []


def _fetch_first_page_only(repo, since, until=None, *, run_gh=None):
    """MUTATION: the REST walk reads page 1 and stops.

    Keeps the gh-failure raise intact on purpose, so this mutation's kill set
    isolates the paging defect instead of overlapping the one above.
    """
    run_gh = run_gh or gi._run_gh
    try:
        raw = run_gh(["api", f"repos/{repo}/pulls?state=closed&per_page=100&page=1"])
    except gi.GhError as exc:
        raise gi.GateIntegrityError(str(exc)) from exc
    return [
        gi._to_merged_pr(entry)
        for entry in json.loads(raw)
        if entry.get("merged_at") and gi.in_window(entry["merged_at"], since, until)
    ]


def _in_window_ignoring_until(merged_at, since, until=None):
    """MUTATION: the `--until` upper bound is dropped."""
    return _REAL_IN_WINDOW(merged_at, since, None)


def _classify_marker_outranks_error(repo, pr, state, error=None):
    """MUTATION: `if error is not None:` gains `and recognise_exception_class(pr)
    is None`.

    A plausible refactor — "don't bother reporting a replay failure for a PR we
    were going to exempt anyway" — that renders a failed gate replay as EXEMPT
    on a marker-bearing PR. Nothing in the suite paired the two before #1481.
    """
    if error is not None and gi.recognise_exception_class(pr) is not None:
        error = None
    return _REAL_CLASSIFY(repo, pr, state, error)


def _classify_error_as_unreviewed(repo, pr, state, error=None):
    """MUTATION: a failed replay is folded into UNREVIEWED.

    The exact collapse the module docstring forbids — "could not tell" rendered
    as the weaker, more comfortable answer. It costs the audit its exit-2 signal
    and turns an unknown into a countable finding, which reads as a complete
    result when it is a lower bound.
    """
    row = _REAL_CLASSIFY(repo, pr, state, error)
    if error is not None:
        row = dataclasses.replace(row, verdict=gi.VERDICT_UNREVIEWED, reviewers=0)
    return row


class _Mutation(NamedTuple):
    """One defect, plus the EXACT set of probes it is expected to kill.

    `kills` replaces the previous `assertGreater(survived, 0)` survivorship
    guard, which had close to no discriminating power: patching `gi.classify` to
    raise unconditionally — total breakage of the classifier — still left 1 of
    15 probes surviving, so the assertion passed (main#1481). Naming the exact
    set makes the survivor set exactly determined too, and makes the harness
    fail in BOTH directions: a mutation that stops being caught, and a mutation
    that has quietly grown broad enough to break unrelated regions.

    `survivors_because` is the reason the rest of the probe set is untouched —
    the sentence a reader needs to judge whether the row is a targeted defect or
    a blunt instrument.
    """

    label: str
    factory: Callable[[], contextlib.AbstractContextManager]
    kills: tuple[str, ...]
    survivors_because: str


#: Each mutation is a defect a plausible edit could introduce; the harness
#: asserts every one is caught, and caught by exactly the probes declared.
_MUTATIONS = (
    _Mutation(
        "is_wave_branch always False (wave-merge exemption removed)",
        lambda: _always(gi.charter_trailer, "is_wave_branch", False),
        (
            "wave-merge PR is EXEMPT",
            "empty denominator yields no rate",
            "audit_repo skips the replay for exempt-by-ref",
        ),
        "only fixtures whose head_ref IS a wave branch consult the predicate; the "
        "emergency/doc-sweep, fetch and render probes never reach it.",
    ),
    _Mutation(
        "is_wave_branch always True (every PR exempted)",
        lambda: _always(gi.charter_trailer, "is_wave_branch", True),
        (
            "0-reviewer PR is UNREVIEWED",
            "1-reviewer PR is UNREVIEWED",
            "2-reviewer PR is PASS",
            "[EMERGENCY] mid-title is NOT exempt",
            "doc sweep + 0 reviewers is UNREVIEWED",
            "doc-sweep marker mid-sentence is NOT exempt",
            "UNREVIEWED exits 1",
            "audit_repo skips the replay for exempt-by-ref",
            "audit_repo surfaces a replay error",
        ),
        "the survivors either already expect EXEMPT, or never build a PR at all "
        "(the fetch and render probes, and the two exit-code probes whose rows are "
        "constructed directly).",
    ),
    _Mutation(
        "emergency prefix pattern never matches",
        lambda: _attr(gi, "_EMERGENCY_TITLE_RE", re.compile(r"(?!x)x")),
        ("[EMERGENCY]-prefixed PR is EXEMPT",),
        "only the positive emergency probe depends on the pattern matching; the "
        "mid-title probe already expects UNREVIEWED.",
    ),
    _Mutation(
        "emergency prefix pattern unanchored (a mention buys an exemption)",
        lambda: _attr(gi, "_EMERGENCY_TITLE_RE", re.compile(r"\[EMERGENCY\]", re.IGNORECASE)),
        ("[EMERGENCY] mid-title is NOT exempt",),
        "the anchored and unanchored patterns agree on every fixture except the "
        "mid-title one — which is the entire point of anchoring it.",
    ),
    _Mutation(
        "doc-sweep body pattern never matches",
        lambda: _attr(gi, "_DOC_SWEEP_BODY_RE", re.compile(r"(?!x)x")),
        ("doc sweep + 1 reviewer is EXEMPT",),
        "mirror of the emergency pair: only the positive doc-sweep probe needs the "
        "pattern to match.",
    ),
    _Mutation(
        "doc-sweep body pattern unanchored (prose buys an exemption)",
        lambda: _attr(gi, "_DOC_SWEEP_BODY_RE", re.compile(r"Sweep:", re.IGNORECASE)),
        ("doc-sweep marker mid-sentence is NOT exempt",),
        "only the mid-sentence probe separates a line-anchored declaration from a "
        "substring match anywhere in the body.",
    ),
    _Mutation(
        "doc-sweep threshold dropped to 0 reviewers",
        lambda: _attr(gi, "_DOC_SWEEP_MIN_REVIEWERS", 0),
        ("doc sweep + 0 reviewers is UNREVIEWED",),
        "the threshold is only consulted once the marker matched, and only the "
        "0-reviewer fixture sits on the wrong side of it.",
    ),
    _Mutation(
        "recognise_exception_class returns doc-sweep for everything",
        lambda: _always(gi, "recognise_exception_class", gi.EXCEPTION_DOC_SWEEP),
        (
            "wave-merge PR is EXEMPT",
            "1-reviewer PR is UNREVIEWED",
            "[EMERGENCY]-prefixed PR is EXEMPT",
            "[EMERGENCY] mid-title is NOT exempt",
            "doc-sweep marker mid-sentence is NOT exempt",
            "empty denominator yields no rate",
            "audit_repo skips the replay for exempt-by-ref",
        ),
        "survivors are the probes whose expected verdict is unchanged by a "
        "doc-sweep recognition (a 2-reviewer PASS, a 0-reviewer shortfall) plus the "
        "whole fetch and render regions, which never classify.",
    ),
    _Mutation(
        "recognise_exception_class returns None for everything",
        lambda: _always(gi, "recognise_exception_class", None),
        (
            "wave-merge PR is EXEMPT",
            "[EMERGENCY]-prefixed PR is EXEMPT",
            "doc sweep + 1 reviewer is EXEMPT",
            "empty denominator yields no rate",
            "audit_repo skips the replay for exempt-by-ref",
        ),
        "exactly the probes that expect an EXEMPT verdict (plus the two that "
        "aggregate over one); every probe already expecting PASS or UNREVIEWED is "
        "unaffected by losing the markers.",
    ),
    _Mutation(
        "ReviewState.passes() always True (gate replay ignored)",
        lambda: _prop(pr_review_state.ReviewState, "passes", lambda self: lambda: True),
        (
            "0-reviewer PR is UNREVIEWED",
            "1-reviewer PR is UNREVIEWED",
            "[EMERGENCY] mid-title is NOT exempt",
            "doc sweep + 1 reviewer is EXEMPT",
            "doc sweep + 0 reviewers is UNREVIEWED",
            "doc-sweep marker mid-sentence is NOT exempt",
            "UNREVIEWED exits 1",
            "audit_repo skips the replay for exempt-by-ref",
        ),
        "survivors are the probes that pass a `state` of None (the pre-state "
        "exemptions), already expect PASS, or never build a ReviewState.",
    ),
    _Mutation(
        "AuditResult.undetermined always False (exit 2 unreachable)",
        lambda: _prop(gi.AuditResult, "undetermined", lambda self: False),
        ("UNDETERMINED exits 2",),
        "the property is read only by `exit_code` and `verified`; no other probe "
        "builds a window containing an UNDETERMINED row.",
    ),
    _Mutation(
        "AuditResult.verified always True (exit 1 unreachable)",
        lambda: _prop(gi.AuditResult, "verified", lambda self: True),
        ("UNREVIEWED exits 1",),
        "same shape as the row above — one probe owns the exit-1 contract, and "
        "exit 2 still short-circuits ahead of `verified`.",
    ),
    _Mutation(
        "AuditResult.verified always False (a clean window blocks anyway)",
        lambda: _prop(gi.AuditResult, "verified", lambda self: False),
        ("clean window exits 0",),
        "the fail-CLOSED direction of the row above, and it is here because "
        "`test_every_probe_is_load_bearing_for_at_least_one_mutation` found that "
        "nothing in the table exercised the clean-exit probe. A gate that blocks a "
        "clean wave is not safe, it is a gate that gets switched off.",
    ),
    _Mutation(
        "UNDETERMINED folded into UNREVIEWED (the weaker, comfortable answer)",
        lambda: _attr(gi, "classify", _classify_error_as_unreviewed),
        (
            "replay error is UNDETERMINED",
            "UNDETERMINED exits 2",
            "audit_repo surfaces a replay error",
            "replay error outranks an exemption marker",
        ),
        "everything that distinguishes 'could not tell' from 'told, and it was "
        "bad'; probes over successful replays are untouched. Added because the "
        "converse-coverage test found the replay-error probe exercised by no "
        "mutation at all.",
    ),
    _Mutation(
        "in_window always True (window bound ignored)",
        lambda: _always(gi, "in_window", True),
        ("out-of-window merge is excluded", "fetch honours the --until bound"),
        "only the two enumeration probes with an out-of-window fixture; the "
        "classifier never calls `in_window`.",
    ),
    _Mutation(
        "enforcement_rate reports 1.0 over an empty denominator",
        lambda: _prop(gi.AuditResult, "enforcement_rate", lambda self: 1.0),
        ("empty denominator yields no rate",),
        "the rate feeds only the rendered summary line, and no other probe asserts on it.",
    ),
    _Mutation(
        "REVIEW_THRESHOLD dropped to 1 reviewer",
        lambda: _attr(pr_review_state, "REVIEW_THRESHOLD", 1),
        (
            "1-reviewer PR is UNREVIEWED",
            "[EMERGENCY] mid-title is NOT exempt",
            "doc sweep + 1 reviewer is EXEMPT",
            "doc-sweep marker mid-sentence is NOT exempt",
        ),
        "only the 1-reviewer fixtures straddle the threshold; 0 and 2 reviewers "
        "classify identically at either setting. `doc sweep + 1 reviewer` dies "
        "because the PR now PASSes outright rather than reaching the exemption.",
    ),
    # -- added for main#1481: the regions the probe set never reached ---------
    _Mutation(
        "fetch_merged_prs swallows a gh failure and returns a partial population",
        lambda: _attr(gi, "fetch_merged_prs", _fetch_swallowing_gh_failures),
        ("fetch raises on a gh failure",),
        "the mutant is faithful to the defect and nothing else: it delegates to the "
        "real walk and only converts the raise, so every other enumeration probe "
        "behaves identically.",
    ),
    _Mutation(
        "the REST walk reads page 1 and stops (truncated population)",
        lambda: _attr(gi, "fetch_merged_prs", _fetch_first_page_only),
        ("fetch walks past page 1",),
        "the single-page mutant keeps the gh-failure raise and the window filter, "
        "so it is separable from the row above and from the `--until` row below.",
    ),
    _Mutation(
        "the --until upper bound is ignored",
        lambda: _attr(gi, "in_window", _in_window_ignoring_until),
        ("fetch honours the --until bound",),
        "dropping only the upper bound leaves the `since` lower bound intact, so "
        "the out-of-window probe (which is out on the `since` side) still passes — "
        "which is exactly why `in_window always True` did not cover this case.",
    ),
    _Mutation(
        "needs_review_state always False (the replay never runs)",
        lambda: _always(gi, "needs_review_state", False),
        ("audit_repo skips the replay for exempt-by-ref",),
        "the predicate is called only by `audit_repo`, and only one probe drives "
        "`audit_repo` over a population with both an exempt-by-ref and a normal PR.",
    ),
    _Mutation(
        "needs_review_state always True (exempt-by-ref PRs are replayed anyway)",
        lambda: _always(gi, "needs_review_state", True),
        ("audit_repo skips the replay for exempt-by-ref",),
        "the opposite direction, and it changes NO verdict — a wave-merge PR still "
        "classifies EXEMPT. It is visible only in the replay call log, which is why "
        "that probe asserts on the log as well as on the verdicts.",
    ),
    _Mutation(
        "classify: an exemption marker outranks a replay error",
        lambda: _attr(gi, "classify", _classify_marker_outranks_error),
        ("replay error outranks an exemption marker",),
        "no other probe pairs an `error` with a marker-bearing PR — the gap the "
        "issue found, where the mutation was caught by nothing in the suite.",
    ),
    _Mutation(
        "Classification.is_finding always False (render_text hides every finding)",
        lambda: _prop(gi.Classification, "is_finding", lambda self: False),
        ("render_text names a finding", "render_text labels a finding UNREVIEWED"),
        "`is_finding` is read only by `render_text`'s findings loop; the counts "
        "header and the exempt summary are unaffected, and no classifier probe "
        "renders.",
    ),
    _Mutation(
        "render_text labels every verdict PASS",
        lambda: _attr(gi, "_MARKS", {verdict: "PASS  " for verdict in gi.ALL_VERDICTS}),
        ("render_text labels a finding UNREVIEWED",),
        "the row is still PRINTED, so the probe that only checks the PR number "
        "survives. That split is deliberate: hiding a finding and mislabelling one "
        "are different defects and need different probes.",
    ),
    _Mutation(
        "parse_iso8601 always None (the population is always empty)",
        lambda: _always(gi, "parse_iso8601", None),
        (
            "out-of-window merge is excluded",
            "fetch honours the --until bound",
            "fetch walks past page 1",
        ),
        "every enumeration probe that expects a NON-empty result dies; the "
        "out-of-window probe expects `[]` and dies only because the walk's stop "
        "condition changes. The classifier never parses a timestamp.",
    ),
)

#: Mutations permitted to break the entire probe set, with the reason. Empty,
#: and meant to stay that way: a mutation that breaks everything is not a
#: targeted defect, it is a demolition, and it tells you nothing about which
#: assertion is load-bearing. Listing one here is a deliberate, reviewable act.
_TOTAL_BREAKAGE_ALLOWED: tuple[str, ...] = ()


class MutationTests(unittest.TestCase):
    """Prove each assertion above can actually fail.

    Each test answers a different objection. `test_baseline_probes_pass` shows the
    probes describe the CURRENT behaviour; `test_every_mutation_is_caught` shows
    each mutation is seen by something; and
    `test_each_mutation_kills_exactly_the_declared_probes` shows WHICH something,
    which is the part the previous version of this harness could not say. The rest
    guard the declarations themselves.

    On the harness's own limits (main#1481): the mutation table can only be drawn
    from the region the probes execute. When the probes reached `classify`,
    `exit_code` and one window case only, EIGHT of the eleven defects added below
    survived the whole fifteen-probe set — measured against origin/main `a65ddeb`,
    0 of 15 each — including `classify`'s error-versus-marker precedence, which
    the entire pre-existing suite also missed (source-mutated: `55 passed, 56
    subtests passed`). Several of the others were caught by ordinary unit tests
    elsewhere in this file, which is the real coverage — and precisely the point:
    the harness's own green said nothing about it.

    Two more rows exist for the opposite reason.
    `test_every_probe_is_load_bearing_for_at_least_one_mutation` found that two of
    the fifteen original probes (`replay error is UNDETERMINED`,
    `clean window exits 0`) were killed by NO mutation in the table, so the table
    said nothing about them either; the mutations they now pair with were added to
    close that direction.
    """

    def test_baseline_probes_pass(self):
        for label, probe in _PROBES:
            with self.subTest(probe=label):
                probe()

    def test_probe_labels_are_unique(self):
        """The kill sets are keyed by label, so a duplicate would silently make
        one probe's declaration stand in for another's."""
        labels = [label for label, _probe in _PROBES]
        self.assertEqual(len(labels), len(set(labels)), "duplicate probe label")

    def _kills(self, mutation: _Mutation) -> list[str]:
        caught: list[str] = []
        with mutation.factory():
            for probe_label, probe in _PROBES:
                try:
                    probe()
                except Exception:  # noqa: BLE001 — any failure is a catch
                    caught.append(probe_label)
        return caught

    def test_every_mutation_is_caught(self):
        for mutation in _MUTATIONS:
            with self.subTest(mutation=mutation.label):
                self.assertTrue(
                    self._kills(mutation),
                    f"MUTATION SURVIVED: {mutation.label!r} changed no probe's outcome. "
                    "The assertions covering it are inert — they cannot fail, so they "
                    "are not evidence.",
                )

    def test_each_mutation_kills_exactly_the_declared_probes(self):
        """The survivorship guard, with teeth (main#1481).

        This replaced `assertGreater(survived, 0)`, which had almost no
        discriminating power: patching `gi.classify` to raise unconditionally —
        total breakage of the classifier — still left one probe surviving
        (`out-of-window merge is excluded` never calls `classify`), so the
        assertion passed. It could only fail if a mutation broke every probe at
        once.

        Declaring the exact kill set fixes the survivor set as its complement, so
        this fails in both directions: a mutation that stops being caught by the
        probe it was written for, and a mutation that has quietly grown broad
        enough to damage an unrelated region. The failure message prints the set
        the harness measured, so the maintenance is a paste, not an investigation
        — but read the row's `survivors_because` before pasting: if the reason no
        longer describes the mutation, the mutation is what changed.
        """
        for mutation in _MUTATIONS:
            with self.subTest(mutation=mutation.label):
                measured = tuple(self._kills(mutation))
                self.assertEqual(
                    measured,
                    mutation.kills,
                    f"{mutation.label}: declared kills {mutation.kills}, measured "
                    f"{measured}. Reason on file for the survivors: "
                    f"{mutation.survivors_because}",
                )

    def test_no_mutation_breaks_the_whole_probe_set(self):
        """A mutation that kills everything is a demolition, not a defect.

        Kept as a separate, plainly-stated claim rather than folded into the
        exact-set test above, because it is the property a reader wants to check
        at a glance: every row in the table is targeted, and the allowlist that
        would say otherwise is empty.
        """
        for mutation in _MUTATIONS:
            if mutation.label in _TOTAL_BREAKAGE_ALLOWED:
                continue
            with self.subTest(mutation=mutation.label):
                self.assertLess(
                    len(mutation.kills),
                    len(_PROBES),
                    f"{mutation.label} kills every probe — either it is too blunt to "
                    "localise a defect, or it belongs in _TOTAL_BREAKAGE_ALLOWED with "
                    "a stated reason.",
                )

    def test_every_declared_kill_names_a_real_probe(self):
        """Guard on the guard: a typo'd probe label in a kill set would make the
        exact-set comparison fail confusingly rather than name the typo."""
        known = {label for label, _probe in _PROBES}
        for mutation in _MUTATIONS:
            with self.subTest(mutation=mutation.label):
                self.assertEqual(set(mutation.kills) - known, set())

    def test_every_probe_is_load_bearing_for_at_least_one_mutation(self):
        """The converse coverage question, and the one that surfaced #1481.

        A probe no mutation kills is not evidence of anything — it is a line that
        looks like coverage. Reported as a set so a newly-added probe arrives
        with the obligation to bring the mutation that makes it matter.
        """
        exercised = {label for mutation in _MUTATIONS for label in mutation.kills}
        idle = {label for label, _probe in _PROBES} - exercised
        self.assertEqual(
            idle,
            set(),
            f"probes killed by no mutation: {sorted(idle)}. Add the defect each one "
            "is meant to detect, or drop the probe.",
        )


if __name__ == "__main__":
    unittest.main()
