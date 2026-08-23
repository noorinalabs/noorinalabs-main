#!/usr/bin/env python3
"""Gate-integrity audit — measure the review gate's own enforcement rate (main#1477).

Every other post-merge property has a `/wave-wrapup` gate: reachability
(Step 11.5), deployable-merge green (11.5a), staging promotion (11.6).
**Gate integrity had none.** Nothing measured whether the 2-reviewer merge gate
actually BOUND on the PRs that merged — so when it did not bind, nobody found
out.

That is not hypothetical. A hand sweep on 2026-08-22 found **3** PRs merged with
zero review artifacts and no applicable admin-exception class —
`noorinalabs-main#1467` (the wave-30 retrospective), `noorinalabs-main#1088`,
and `noorinalabs-deploy#706`. All three had sat undetected for weeks; they
surfaced only because an unrelated audit was requested. That is the
`feedback_enforcement_hierarchy` "rules without enforcement decay" pattern
applied to an enforcement mechanism itself.

BACKFILL — this tool, run over the same window (main#1477)
==========================================================
Window: the 8 org repos, `--since 2026-07-11T04:25:50Z` (the commit
`695d6ad2` at which content-binding verdict staleness became enforceable) to
2026-08-22. Population **225** merged PRs, cross-checked against an independent
instrument (`gh pr list --search "merged:>=2026-07-11"` summed over the 8 repos:
238 at day granularity, **225** at the exact epoch — an exact match). The "236"
quoted while scoping the issue was a day-boundary artifact of the hand sweep;
225 is the figure two instruments agree on.

Verdict: **210 PASS · 6 EXEMPT · 9 UNREVIEWED · 0 UNDETERMINED**, an enforcement
rate of **95.9%** over the 219 non-exempt merges.

The 9 UNREVIEWED are a strict SUPERSET of the hand sweep's 3, because the two
count different things. The hand sweep asked "did any review artifact exist";
this tool asks the question hard requirement #1 mandates — "would the merge gate
have bound" — and the gate's own rules exclude verdicts the naked eye counts:

  * zero countable verdicts (the hand sweep's 3, reproduced exactly):
    `main#1467` (no comments, no formal reviews), `main#1088` (5 formal reviews,
    all state COMMENTED — none APPROVED), `deploy#706` (dependabot, nothing).
  * `main#979` — two charter-format comments, both carrying the
    `RequestOrReplied` value `Request` rather than `Approved`. Review-shaped
    prose, no verdict the gate can count.
  * `main#1065`, `main#1031`, `main#1029` — two Approved verdicts each, ALL of
    them cast BEFORE the branch's latest authored commit and therefore excluded
    as stale (#950). A head move drops every verdict, and materiality is not an
    input.
  * `user-service#213`, `ingest-platform#149` — 1/2 current reviewers.

None of the extra 6 is a false positive: in each, the merge gate replayed
against the merged PR returns BLOCK. What they show is that the hand sweep's
instrument was the loose one.

This module is the detective control. For every PR merged in a window it
re-runs the merge gate's OWN verdict resolution and classifies the merge:

  * ``PASS``         — the gate would have allowed the merge (>=2 distinct
                       CURRENT reviewers, or the wave-bootstrap single-reviewer
                       exception, and no verdict missing its TechDebt line).
  * ``EXEMPT``       — a charter admin-merge exception class covers it, and the
                       exception's own conditions are met.
  * ``UNREVIEWED``   — neither. The gate did not bind and no exception was
                       declared: a real process breach.
  * ``UNDETERMINED`` — the gate's verdict could not be replayed for this PR
                       (a gh/API failure). NEVER folded into PASS.

Reuse, not reimplementation
===========================
The verdict comes from :func:`pr_review_state.compute_review_state`, which
delegates wholesale to the gate's single shared entry point
``validate_pr_review.resolve_review_verdicts`` (#1048). This module does NOT
re-derive the content-binding / comment-scan / roster-filter / union pipeline,
and deliberately does not call ``resolve_review_verdicts`` with its own
argument list either. main#1046 is why: a driver that re-assembled that
pipeline omitted ``content_ts``, so ``T_content`` was never computed and it
reported PASS on approvals the gate rejects. An audit that drifts from the gate
measures nothing — it measures a fork of the gate.

Replaying the gate NOW against a MERGED PR yields the merge-time answer,
because a merged PR gains no further commits: ``T_content`` is frozen at the
merge, so every verdict's freshness is evaluated against exactly the head the
gate saw. (A verdict posted *after* the merge would count here and not there —
so the audit is, in that one direction, more lenient than the gate was. It
therefore never manufactures a false UNREVIEWED.)

Exemption classes, and how each is identified from the artifact
==============================================================
The four charter admin-merge exception classes live in
``validate_pr_ci_status._CHARTER_ADMIN_EXCEPTIONS``; they are DECLARED at merge
time through the ``ADMIN_MERGE_EXCEPTION`` environment variable, which leaves no
trace on the PR itself. So this audit can only recognise a class by a marker the
charter requires on the PR artifact:

``wave-merge``
    ``charter_trailer.is_wave_branch(head_ref)`` — the SAME predicate the merge
    gate uses. `pull-requests/wave-merge.md` § Wave Merge PR Verification
    point 5: the code on a wave branch was already 2x-reviewed on its per-issue
    PRs, the integration PR authors no content of its own, fresh 2-reviewer
    approval is **not required**, and the gate's 0/2 block on these is
    "expected and audited". An audit that flags them emits ~3 false positives
    per wave and gets ignored within two waves.

    NOTE — this is deliberately NOT keyed off the ``wave-integration``
    comment-scan mode (``validate_pr_review.COMMENT_SCAN_WAVE_INTEGRATION``).
    That mode governs *self-review exclusion* (#1216): it makes reaching 2
    easier, not unnecessary. Different rule, same-sounding name; conflating
    them is an easy and consequential misreading.

``emergency``
    Title prefixed ``[EMERGENCY]`` — `emergency-mode.md` § Allowed bypasses
    mandates exactly that prefix "so post-emergency catchup can find them".

``doc-sweep``
    `pull-requests/authoring.md` § Trivial Cross-Repo Doc Sweep requires the PR
    body to carry a sweep line citing the tracking issue. Crucially this class
    grants a **Single-Reviewer** Exception, not a zero-reviewer one, so the
    marker alone is not enough: the PR must also carry at least one current
    distinct reviewer and no verdict missing its TechDebt line. A sweep-marked
    PR with ZERO reviewers is still ``UNREVIEWED``.

``wave-bootstrap``
    Not handled here at all — and that is correct. The gate itself applies the
    wave-bootstrap single-reviewer exception inside
    ``resolve_review_verdicts``/``ReviewState.passes()``, so such a PR
    classifies ``PASS`` on the replay. Re-recognising it here would double-count
    it and, worse, could mark it EXEMPT in cases where the gate's own
    ``is_single_reviewer_exception`` said no.

Fail closed, everywhere
=======================
Exit ``0`` verified / ``1`` not verified / ``2`` UNDETERMINED. Every failure
path in this module raises rather than returning an empty result: a failed
``gh`` call, an unparseable payload, a page-limit that may have truncated the
population, or an unresolvable repo all surface as UNDETERMINED (exit 2), never
as "no problems found". That is the #981 fail-open shape (an early
allow-with-warning short-circuiting ahead of the hard checks) and the
``pr_ci_state.py`` empty-is-not-ready discipline. It matters specifically here:
under GraphQL-quota exhaustion a failed ``gh`` call's empty output reads as a
legitimate zero result (`feedback_gh_cli_gotchas` §12), which for an audit means
"zero unreviewed merges" — the most dangerous possible wrong answer.

Run it from the repo ROOT checkout, not a worktree
==================================================
The gate resolves a child repo's roster relative to the directory holding the
parent's `.claude/` (`validate_pr_review._child_roster_dir`), and treats
`--repo noorinalabs/noorinalabs-main` as the PARENT only when that directory is
literally named `noorinalabs-main`. Invoked from `.claude/worktrees/agent-…`,
it is not, so every PR replays as `RosterResolutionError` and every row lands
UNDETERMINED. That is the safe direction — exit 2, loudly, naming the missing
path — but it is not a measurement. `/wave-wrapup` runs from
`git rev-parse --show-toplevel` in the root checkout, where it resolves
correctly.

Enumeration is REST, not search
===============================
Merged PRs are enumerated over ``repos/{repo}/pulls?state=closed&sort=updated``
rather than ``gh pr list --search "merged:>=..."``. The search index is
eventually consistent and silently truncates at ``--limit``; this step runs
immediately after `/wave-wrapup` Step 11 merges the wave->main PRs, so a lagging
index would drop exactly the freshest merges. Paging by ``updated`` descending
is index-free and complete: a PR merged in-window always has
``updated_at >= merged_at >= since``, so the first page whose entries all
predate ``since`` ends the walk with nothing missed.

Usage:
    python3 .claude/lib/gate_integrity.py noorinalabs/noorinalabs-main \\
        --since 2026-08-09T00:00:00Z
    python3 .claude/lib/gate_integrity.py noorinalabs/noorinalabs-main \\
        noorinalabs/noorinalabs-deploy --since 2026-07-11T04:25:50Z --json

Exit codes:
    0 — VERIFIED: every PR merged in the window classifies PASS or EXEMPT.
    1 — NOT VERIFIED: at least one UNREVIEWED merge (and none undetermined).
    2 — UNDETERMINED: at least one PR's verdict could not be replayed, or the
        merged-PR population could not be enumerated. Reported as blocking, and
        outranks a plain UNREVIEWED result — "we cannot tell" must never be
        rendered as the weaker, more comfortable answer.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Siblings live alongside this file in `.claude/lib/`. When run as a script the
# own-directory is already `sys.path[0]`; tests insert the lib dir explicitly
# (the bootstrap every `.claude/lib/tests/test_*.py` uses).
sys.path.insert(0, str(Path(__file__).resolve().parent))
import charter_trailer  # noqa: E402
import gh  # noqa: E402
import pr_review_state  # noqa: E402
from gh import GhError  # noqa: E402

# ---------------------------------------------------------------------------
# Classification vocabulary
# ---------------------------------------------------------------------------

VERDICT_PASS = "PASS"
VERDICT_EXEMPT = "EXEMPT"
VERDICT_UNREVIEWED = "UNREVIEWED"
VERDICT_UNDETERMINED = "UNDETERMINED"

#: Every verdict this module can emit. Kept as a tuple so a totality test can
#: assert the renderer handles each one (the `COMMENT_SCAN_*` lesson from
#: main#1273: a silent catch-all renders an unknown state as a confident,
#: specific, WRONG one).
ALL_VERDICTS = (VERDICT_PASS, VERDICT_EXEMPT, VERDICT_UNREVIEWED, VERDICT_UNDETERMINED)

#: Charter admin-merge exception classes this audit can recognise from the PR
#: artifact alone. Deliberately a SUBSET of
#: `validate_pr_ci_status._CHARTER_ADMIN_EXCEPTIONS`: `wave-bootstrap` is
#: applied by the gate itself (so it lands in PASS, see module docstring).
EXCEPTION_WAVE_MERGE = "wave-merge"
EXCEPTION_EMERGENCY = "emergency"
EXCEPTION_DOC_SWEEP = "doc-sweep"

#: The commit at which content-binding verdict staleness became enforceable
#: (`695d6ad2`, main#950). Replaying today's gate against a PR merged BEFORE
#: this is anachronistic — it judges a merge by a rule that was not in force —
#: so an earlier `--since` gets a warning, not a silent verdict.
CONTENT_BINDING_EPOCH = "2026-07-11T04:25:50Z"

#: The `[EMERGENCY]` title prefix `emergency-mode.md` mandates. Anchored at the
#: start so an incidental mention in a title body cannot buy an exemption.
_EMERGENCY_TITLE_RE = re.compile(r"^\s*\[EMERGENCY\]", re.IGNORECASE)

#: The doc-sweep body marker (`authoring.md` § Trivial Cross-Repo Doc Sweep:
#: "the PR body must include a ... line citing the tracking issue"). Anchored to
#: the start of a LINE — a prose mention mid-sentence is not a declaration.
_DOC_SWEEP_BODY_RE = re.compile(r"^[ \t>*-]*Sweep:[ \t]*\S", re.IGNORECASE | re.MULTILINE)

#: Reviewers a `doc-sweep`-marked PR must still carry for the exemption to
#: apply. `authoring.md` § Trivial Cross-Repo Doc Sweep grants a **Single**-
#: Reviewer Exception, so this is 1 — NOT 0. Named rather than inlined so the
#: mutation harness can drive it to 0 and prove the assertion that depends on
#: it can actually fail.
_DOC_SWEEP_MIN_REVIEWERS = 1

#: Hard ceiling on REST pages walked per repo. Reaching it means the window is
#: larger than this tool was asked to cover; that raises rather than returning a
#: partial population, because a partial population is an undercount of
#: UNREVIEWED merges — silent, and in the unsafe direction.
_MAX_PAGES = 40
_PER_PAGE = 100


class GateIntegrityError(Exception):
    """The audit could not be completed (maps to CLI exit code 2)."""


# ---------------------------------------------------------------------------
# Pure logic (no network — unit-tested directly)
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class MergedPR:
    """One merged PR, as read from the REST pulls listing."""

    number: int
    title: str
    body: str
    head_ref: str
    base_ref: str
    merged_at: str
    url: str
    author: str


@dataclasses.dataclass(frozen=True)
class Classification:
    """The audit's verdict on one merged PR."""

    repo: str
    number: int
    title: str
    head_ref: str
    merged_at: str
    url: str
    verdict: str
    #: The recognised charter exception class, or `""` when none applies.
    exception_class: str = ""
    #: Distinct CURRENT reviewers the gate would have counted. `None` when the
    #: review state was never computed (a pre-state exemption) or could not be
    #: computed (UNDETERMINED) — deliberately not `0`, which would read as a
    #: measurement of zero approvals rather than as "not measured" (#1206).
    reviewers: int | None = None
    #: Human-readable justification for the verdict. Always non-empty.
    reason: str = ""

    @property
    def is_finding(self) -> bool:
        """True when this row is something an operator must act on."""
        return self.verdict in (VERDICT_UNREVIEWED, VERDICT_UNDETERMINED)


def parse_iso8601(value: str | None) -> datetime | None:
    """Parse a GitHub ISO-8601 timestamp to an aware datetime, else None.

    Mirrors `validate_pr_review._parse_iso8601`: the trailing `Z` is normalised
    so every returned datetime is timezone-aware and safely comparable. None
    means UNKNOWN, and every caller here fails closed on it — never "in window"
    and never "fresh".
    """
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def recognise_exception_class(pr: MergedPR) -> str | None:
    """Return the charter exception class discernible from the PR artifact.

    Only the classes whose markers live ON the PR (see module docstring):
    `wave-merge` via the gate's own `is_wave_branch` predicate, `emergency` via
    the mandated title prefix, `doc-sweep` via the mandated body line. Returns
    None when no marker is present.

    Recognising a marker is NOT the same as granting the exemption —
    `doc-sweep` additionally requires a reviewer, which this function cannot
    know. `classify` applies that condition.
    """
    if charter_trailer.is_wave_branch(pr.head_ref):
        return EXCEPTION_WAVE_MERGE
    if _EMERGENCY_TITLE_RE.search(pr.title or ""):
        return EXCEPTION_EMERGENCY
    if _DOC_SWEEP_BODY_RE.search(pr.body or ""):
        return EXCEPTION_DOC_SWEEP
    return None


def needs_review_state(pr: MergedPR) -> bool:
    """True when the gate's verdict must actually be replayed for this PR.

    `wave-merge` and `emergency` are unconditional exemptions, so replaying the
    gate for them would spend three API calls to compute an answer that changes
    nothing — and would let a transient gh failure turn a known-exempt
    integration PR into an UNDETERMINED finding. `doc-sweep` is conditional on
    the reviewer count, so it DOES need the replay.
    """
    recognised = recognise_exception_class(pr)
    return recognised not in (EXCEPTION_WAVE_MERGE, EXCEPTION_EMERGENCY)


def classify(
    repo: str,
    pr: MergedPR,
    state: pr_review_state.ReviewState | None,
    error: str | None = None,
) -> Classification:
    """Classify one merged PR as PASS / EXEMPT / UNREVIEWED / UNDETERMINED.

    Pure: `state` is the already-computed replay of the gate's verdict (None
    when `needs_review_state` said it was unnecessary), and `error` is the
    message from a failed replay. Keeping the network out of here is what lets
    every branch below be exercised — and mutated — by a fixture.
    """

    def _row(
        verdict: str,
        *,
        reason: str,
        exception_class: str = "",
        reviewers: int | None = None,
    ) -> Classification:
        """Bind the PR-identity fields once, per branch below.

        Spelled as a closure rather than a `**base` dict splat so mypy still
        type-checks every call: a dict splat degrades the argument types to
        `object` and the checker stops seeing the constructor's signature at all.
        """
        return Classification(
            repo=repo,
            number=pr.number,
            title=pr.title,
            head_ref=pr.head_ref,
            merged_at=pr.merged_at,
            url=pr.url,
            verdict=verdict,
            exception_class=exception_class,
            reviewers=reviewers,
            reason=reason,
        )

    if error is not None:
        return _row(
            VERDICT_UNDETERMINED,
            reviewers=None,
            reason=f"the gate's verdict could not be replayed: {error}",
        )

    recognised = recognise_exception_class(pr)

    if recognised == EXCEPTION_WAVE_MERGE:
        return _row(
            VERDICT_EXEMPT,
            exception_class=EXCEPTION_WAVE_MERGE,
            reviewers=None,
            reason=(
                f"head ref {pr.head_ref!r} is a charter wave branch, so this is a "
                "wave->main INTEGRATION PR: its commits were already 2x-reviewed on "
                "their per-issue PRs and fresh 2-reviewer approval is not required "
                "(wave-merge.md § Wave Merge PR Verification point 5)."
            ),
        )

    if recognised == EXCEPTION_EMERGENCY:
        return _row(
            VERDICT_EXEMPT,
            exception_class=EXCEPTION_EMERGENCY,
            reviewers=None,
            reason=(
                "title carries the mandated [EMERGENCY] prefix — emergency-mode.md "
                "§ Allowed bypasses. Post-emergency catchup review is owed."
            ),
        )

    if state is None:
        # Defensive: `needs_review_state` said this PR needed a replay and no
        # replay (and no error) arrived. Fail CLOSED — an absent measurement is
        # not a passing one.
        return _row(
            VERDICT_UNDETERMINED,
            reviewers=None,
            reason=(
                "no review state was computed for this PR and no error was reported "
                "— the gate's verdict is unknown, which is not the same as clean."
            ),
        )

    reviewers = state.distinct_reviewer_count

    if state.passes():
        return _row(
            VERDICT_PASS,
            reviewers=reviewers,
            reason=(
                f"{reviewers} distinct current reviewer(s)"
                + (
                    " under the wave-bootstrap single-reviewer exception"
                    if reviewers < pr_review_state.REVIEW_THRESHOLD
                    else ""
                )
                + " — the gate would have allowed this merge."
            ),
        )

    missing_td = list(state.reviews_missing_tech_debt)

    if recognised == EXCEPTION_DOC_SWEEP:
        # A Single-Reviewer Exception, NOT a zero-reviewer one. The marker buys
        # a reduced threshold; it does not buy an unreviewed merge.
        if reviewers >= _DOC_SWEEP_MIN_REVIEWERS and not missing_td:
            return _row(
                VERDICT_EXEMPT,
                exception_class=EXCEPTION_DOC_SWEEP,
                reviewers=reviewers,
                reason=(
                    "PR body declares a trivial cross-repo doc sweep and carries "
                    f"{reviewers} current reviewer — authoring.md § Trivial Cross-Repo "
                    "Doc Sweep grants a Single-Reviewer Exception."
                ),
            )
        shortfall = (
            f"carries {reviewers} current reviewer(s), below the {_DOC_SWEEP_MIN_REVIEWERS} "
            "that class requires"
            if reviewers < _DOC_SWEEP_MIN_REVIEWERS
            else f"has verdict(s) missing the TechDebt line: {', '.join(missing_td)}"
        )
        return _row(
            VERDICT_UNREVIEWED,
            reviewers=reviewers,
            reason=(
                f"PR body declares a doc sweep but {shortfall}. That class grants a "
                "SINGLE-reviewer exception, not a zero-reviewer one, so the exemption "
                "does not apply."
            ),
        )

    if missing_td:
        return _row(
            VERDICT_UNREVIEWED,
            reviewers=reviewers,
            reason=(
                f"{reviewers} distinct current reviewer(s), but the gate would have "
                f"BLOCKED: verdict(s) missing the TechDebt line: {', '.join(missing_td)}."
            ),
        )

    stale = len(state.stale_verdicts)
    stale_note = (
        f" ({stale} verdict(s) excluded as stale against T_content {state.content_sha[:8]})"
        if stale
        else ""
    )
    return _row(
        VERDICT_UNREVIEWED,
        reviewers=reviewers,
        reason=(
            f"{reviewers}/{pr_review_state.REVIEW_THRESHOLD} distinct current "
            f"reviewers{stale_note} and no charter exception class is discernible from "
            "the PR — the gate did not bind and no exception was declared."
        ),
    )


@dataclasses.dataclass
class AuditResult:
    """The audit's verdict over one window, across one or more repos."""

    since: str
    until: str | None
    repos: list[str]
    rows: list[Classification]

    @property
    def counts(self) -> dict[str, int]:
        tally = {verdict: 0 for verdict in ALL_VERDICTS}
        for row in self.rows:
            tally[row.verdict] = tally.get(row.verdict, 0) + 1
        return tally

    @property
    def undetermined(self) -> bool:
        return any(row.verdict == VERDICT_UNDETERMINED for row in self.rows)

    @property
    def unreviewed(self) -> list[Classification]:
        return [row for row in self.rows if row.verdict == VERDICT_UNREVIEWED]

    @property
    def verified(self) -> bool:
        """True iff every merged PR classified PASS or EXEMPT."""
        return not self.undetermined and not self.unreviewed

    @property
    def enforcement_rate(self) -> float | None:
        """Share of NON-exempt merges on which the gate bound, or None.

        None when the window contains no non-exempt merges — a rate over an
        empty denominator is not 100%, it is not a measurement. Reporting it as
        1.0 would print a reassuring number for a window that measured nothing.

        UNDETERMINED rows sit in the DENOMINATOR but never the numerator, so an
        unreplayable PR drags the rate down rather than vanishing from it. A row
        whose verdict is unknown is not evidence the gate bound.
        """
        denominator = [
            row
            for row in self.rows
            if row.verdict in (VERDICT_PASS, VERDICT_UNREVIEWED, VERDICT_UNDETERMINED)
        ]
        if not denominator:
            return None
        passed = sum(1 for row in denominator if row.verdict == VERDICT_PASS)
        return passed / len(denominator)

    def exit_code(self) -> int:
        """0 verified / 1 not verified / 2 undetermined.

        UNDETERMINED outranks UNREVIEWED deliberately: when some rows could not
        be replayed, the count of UNREVIEWED rows is a LOWER BOUND, and exiting
        1 would present a lower bound as a complete finding.
        """
        if self.undetermined:
            return 2
        return 0 if self.verified else 1


def in_window(merged_at: str, since: datetime, until: datetime | None) -> bool:
    """True when `merged_at` falls in [since, until].

    An unparseable or absent `merged_at` returns False — but callers must not
    read that as "safely excluded": :func:`fetch_merged_prs` raises on a closed
    PR that reports a merge it cannot timestamp, rather than dropping it.
    """
    when = parse_iso8601(merged_at)
    if when is None:
        return False
    if when < since:
        return False
    return not (until is not None and when > until)


# ---------------------------------------------------------------------------
# I/O (gh subprocess — mocked in tests)
# ---------------------------------------------------------------------------


def _run_gh(args: list[str]) -> str:
    """Run ``gh <args>``, converting every failure into :class:`GhError`.

    The subprocess call is `gh.run_gh` (explicit arg list, never a shell string
    — main#688). The wrapping is this module's own behaviour and is the whole
    fail-closed contract: a non-zero `gh` exit must become "cannot determine",
    never an empty stdout that the caller reads as zero findings.
    """
    try:
        return gh.run_gh(args)
    except FileNotFoundError as exc:
        raise GhError("gh CLI not found on PATH") from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise GhError(f"gh {' '.join(args)} failed: {stderr}") from exc
    except OSError as exc:
        raise GhError(f"gh {' '.join(args)} failed: {exc}") from exc


def _to_merged_pr(entry: dict) -> MergedPR:
    """Project one REST pulls-listing entry onto :class:`MergedPR`."""
    return MergedPR(
        number=int(entry.get("number") or 0),
        title=entry.get("title") or "",
        body=entry.get("body") or "",
        head_ref=((entry.get("head") or {}).get("ref")) or "",
        base_ref=((entry.get("base") or {}).get("ref")) or "",
        merged_at=entry.get("merged_at") or "",
        url=entry.get("html_url") or "",
        author=((entry.get("user") or {}).get("login")) or "",
    )


def fetch_merged_prs(
    repo: str,
    since: datetime,
    until: datetime | None = None,
    *,
    run_gh=_run_gh,
) -> list[MergedPR]:
    """Every PR in `repo` merged within [since, until], newest-merge first.

    Walks ``repos/{repo}/pulls?state=closed&sort=updated&direction=desc``. See
    the module docstring for why this is REST-by-update rather than
    ``gh pr list --search``. The walk stops at the first page whose entries ALL
    have ``updated_at < since``: a PR merged in-window necessarily satisfies
    ``updated_at >= merged_at >= since``, so nothing in-window can hide behind
    that boundary.

    Raises :class:`GateIntegrityError` on a gh failure, an unparseable payload,
    a closed PR that reports a merge with no readable timestamp, or a walk that
    hits `_MAX_PAGES`. Each of those is a case where the returned list would be
    an UNDERCOUNT of unreviewed merges, and an undercount here is a silent
    fail-open.
    """
    collected: list[MergedPR] = []
    for page in range(1, _MAX_PAGES + 1):
        path = (
            f"repos/{repo}/pulls?state=closed&sort=updated&direction=desc"
            f"&per_page={_PER_PAGE}&page={page}"
        )
        try:
            raw = run_gh(["api", path])
        except GhError as exc:
            raise GateIntegrityError(f"could not list merged PRs for {repo}: {exc}") from exc
        try:
            entries = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise GateIntegrityError(
                f"could not parse the pulls listing for {repo} (page {page}): {exc}"
            ) from exc
        if not isinstance(entries, list):
            raise GateIntegrityError(
                f"unexpected pulls listing shape for {repo} (page {page}): "
                f"{type(entries).__name__}, expected a list"
            )
        if not entries:
            return collected

        page_touches_window = False
        for entry in entries:
            updated = parse_iso8601(entry.get("updated_at"))
            # An UNPARSEABLE `updated_at` keeps the walk going. It is the only
            # safe reading: this flag is the walk's stop condition, so treating
            # "unknown" as "before the window" would end the walk early and
            # silently truncate the population.
            if updated is None or updated >= since:
                page_touches_window = True
            merged_at = entry.get("merged_at")
            if not merged_at:
                # Closed without merging — not in this audit's population.
                # `merged_at` is the authoritative discriminator; GitHub also
                # sets `merge_commit_sha` on closed-unmerged PRs, so that field
                # must NOT be used here.
                continue
            if parse_iso8601(merged_at) is None:
                raise GateIntegrityError(
                    f"{repo}#{entry.get('number')} reports merged_at={merged_at!r}, which "
                    "cannot be parsed. Dropping it would undercount the population, so "
                    "this is a determinate failure."
                )
            if in_window(merged_at, since, until):
                collected.append(_to_merged_pr(entry))

        if not page_touches_window:
            # Every entry on this page was updated before `since`; the listing is
            # sorted by updated descending, so no later page can be in-window.
            return collected

    raise GateIntegrityError(
        f"the merged-PR walk for {repo} exceeded {_MAX_PAGES} pages "
        f"({_MAX_PAGES * _PER_PAGE} closed PRs) without reaching the window start "
        f"{since.isoformat()}. Narrow --since rather than accepting a partial "
        "population — a truncated population undercounts unreviewed merges."
    )


def audit_repo(
    repo: str,
    since: datetime,
    until: datetime | None = None,
    *,
    fetch=fetch_merged_prs,
    compute=pr_review_state.compute_review_state,
) -> list[Classification]:
    """Classify every PR merged in `repo` within the window.

    `fetch`/`compute` are injectable seams so tests drive the whole path
    without touching the network. `compute` defaults to the SHARED entry point
    `pr_review_state.compute_review_state` — never a local re-derivation of the
    gate's pipeline (main#1046).
    """
    rows: list[Classification] = []
    for pr in fetch(repo, since, until):
        if not needs_review_state(pr):
            rows.append(classify(repo, pr, None))
            continue
        try:
            state = compute(str(pr.number), repo=repo)
        except pr_review_state.ReviewStateError as exc:
            rows.append(classify(repo, pr, None, error=str(exc)))
            continue
        rows.append(classify(repo, pr, state))
    return rows


def audit(
    repos: list[str],
    since: datetime,
    until: datetime | None = None,
    *,
    fetch=fetch_merged_prs,
    compute=pr_review_state.compute_review_state,
) -> AuditResult:
    """Run the gate-integrity audit across `repos` for one window."""
    rows: list[Classification] = []
    for repo in repos:
        rows.extend(audit_repo(repo, since, until, fetch=fetch, compute=compute))
    return AuditResult(
        since=since.isoformat(),
        until=until.isoformat() if until else None,
        repos=list(repos),
        rows=rows,
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

_MARKS = {
    VERDICT_PASS: "PASS  ",
    VERDICT_EXEMPT: "EXEMPT",
    VERDICT_UNREVIEWED: "UNREV!",
    VERDICT_UNDETERMINED: "UNDET?",
}


def render_text(result: AuditResult) -> str:
    """Human-readable audit report.

    Findings are printed in full; PASS/EXEMPT rows are summarised. A wrapup
    report that prints 40 green lines to hide 1 red one is not a gate.
    """
    counts = result.counts
    window = f"{result.since} .. {result.until or 'now'}"
    lines = [
        f"Gate-integrity audit — {', '.join(result.repos)}",
        f"  window: {window}",
        f"  merged PRs examined: {len(result.rows)}"
        f"  (PASS {counts[VERDICT_PASS]},"
        f" EXEMPT {counts[VERDICT_EXEMPT]},"
        f" UNREVIEWED {counts[VERDICT_UNREVIEWED]},"
        f" UNDETERMINED {counts[VERDICT_UNDETERMINED]})",
    ]

    rate = result.enforcement_rate
    if rate is None:
        lines.append(
            "  gate enforcement rate: NOT MEASURED — the window contains no "
            "non-exempt merges, so there was nothing for the gate to bind on. "
            "This is not a 100% result."
        )
    else:
        lines.append(f"  gate enforcement rate: {rate * 100:.1f}% of non-exempt merges")

    findings = [row for row in result.rows if row.is_finding]
    if not findings:
        lines.append("  no unreviewed merges found.")
    for row in findings:
        lines.append(f"  {_MARKS.get(row.verdict, row.verdict)} {row.repo}#{row.number}")
        lines.append(f"      {row.title[:96]}")
        lines.append(f"      head {row.head_ref or '(unknown)'} · merged {row.merged_at}")
        lines.append(f"      {row.reason}")
        if row.url:
            lines.append(f"      {row.url}")

    exempt_rows = [row for row in result.rows if row.verdict == VERDICT_EXEMPT]
    if exempt_rows:
        by_class: dict[str, list[str]] = {}
        for row in exempt_rows:
            by_class.setdefault(row.exception_class, []).append(f"#{row.number}")
        for cls, numbers in sorted(by_class.items()):
            lines.append(f"  exempt [{cls}]: {', '.join(numbers)}")

    return "\n".join(lines)


def render_json(result: AuditResult) -> str:
    payload = {
        "since": result.since,
        "until": result.until,
        "repos": result.repos,
        "counts": result.counts,
        "enforcement_rate": result.enforcement_rate,
        "verified": result.verified,
        "undetermined": result.undetermined,
        "exit_code": result.exit_code(),
        "rows": [dataclasses.asdict(row) for row in result.rows],
    }
    return json.dumps(payload, indent=2, sort_keys=True)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gate_integrity",
        description=(
            "Audit the 2-reviewer merge gate's own enforcement rate over a window "
            "of merged PRs, by replaying the gate's verdict resolution. "
            "Exit 0 verified, 1 unreviewed merges found, 2 undetermined."
        ),
    )
    parser.add_argument(
        "repos",
        nargs="+",
        help="one or more repos as OWNER/NAME (e.g. noorinalabs/noorinalabs-main)",
    )
    parser.add_argument(
        "--since",
        required=True,
        help="window start, ISO-8601 (e.g. 2026-08-09T00:00:00Z). Merges before "
        "this are not examined.",
    )
    parser.add_argument(
        "--until",
        default=None,
        help="optional window end, ISO-8601. Defaults to open-ended (now).",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON instead of the report")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    since = parse_iso8601(args.since)
    if since is None:
        print(
            f"gate_integrity: --since {args.since!r} is not a parseable ISO-8601 timestamp.",
            file=sys.stderr,
        )
        return 2
    until = None
    if args.until:
        until = parse_iso8601(args.until)
        if until is None:
            print(
                f"gate_integrity: --until {args.until!r} is not a parseable ISO-8601 timestamp.",
                file=sys.stderr,
            )
            return 2
    if until is not None and until < since:
        print(
            f"gate_integrity: --until {args.until} precedes --since {args.since}; the "
            "window is empty, which would report a clean audit over nothing.",
            file=sys.stderr,
        )
        return 2

    for repo in args.repos:
        if repo.count("/") != 1 or not all(repo.split("/")):
            print(
                f"gate_integrity: repo {repo!r} is not OWNER/NAME. Pass a literal repo "
                "(an unexpanded shell variable can never resolve — main#981).",
                file=sys.stderr,
            )
            return 2

    epoch = parse_iso8601(CONTENT_BINDING_EPOCH)
    if epoch is not None and since < epoch:
        print(
            f"gate_integrity: WARNING — --since {args.since} predates the content-binding "
            f"staleness rule ({CONTENT_BINDING_EPOCH}, main#950). Verdicts on merges "
            "before that date are being judged by a rule that was not yet in force.",
            file=sys.stderr,
        )

    try:
        result = audit(list(args.repos), since, until)
    except GateIntegrityError as exc:
        if args.json:
            print(json.dumps({"verified": False, "undetermined": True, "error": str(exc)}))
        else:
            print(f"UNDETERMINED: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(render_json(result))
    else:
        print(render_text(result))
        code = result.exit_code()
        print({0: "VERIFIED", 1: "NOT VERIFIED", 2: "UNDETERMINED"}.get(code, "UNDETERMINED"))

    return result.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
