#!/usr/bin/env python3
"""Per-engineer mechanical trust signals + evidence-anchored scoring (main#842).

Replaces narrative self-grading in the trust matrix with **countable** signals
derived from the wave's merged-PR set (§4b of the persona-model Option-B work,
parent #819 / Finding D). The trust-matrix scoring rules in
``.claude/team/trust_matrix.md`` § Mechanical Scoring describe the same model in
prose; this module is the executable counterpart that ``/wave-wrapup`` and
``/wave-retro`` call so a trust delta always cites a number.

Two cleanly separated layers:

  * **Extraction** (gh-dependent) — :func:`extract_signals` builds a
    ``{engineer_name: Signals}`` map from the merged-PR set. It reuses
    :func:`wave_status.merged_prs` (so the #423 cross-window filter and the
    no-shell / list-arg-vector contract of main#688 are inherited unchanged) and
    parses each PR's verdict comments for the org's ``Requestor:`` /
    ``RequestOrReplied:`` shape (the same shape Hook 4 and ``wave_status``'s
    ChangesRequested counter read).

  * **Scoring** (pure, no I/O) — :func:`score_delta`, :func:`decay`,
    :func:`apply_distribution_discipline`, :func:`negative_signal_line`,
    :func:`validate_negative_signal_pass`, :func:`retirement_trigger`. Every one
    is a pure function so the model is unit-testable without touching gh.

Signals per engineer (all integers, all countable from the merged-PR set):

  ===========================  ============================================
  prs_merged                   PRs merged this wave with them as commit
                               author.
  must_fix_received            ChangesRequested verdicts on PRs they
                               authored (negative — author signal).
  must_fix_caught              ChangesRequested verdicts they issued as the
                               Requestor/reviewer (positive — review
                               signal).
  ci_red_merges                PRs they authored that merged with a failing
                               required check (negative — hard ding).
  rework_cycles                PRs they authored that needed >=1 rework
                               round (received >=1 ChangesRequested).
  review_false_positives       ChangesRequested items they raised that the
                               SAME comment explicitly self-retracts via a
                               dedicated ``Retracted:`` field (negative —
                               review-quality signal). Free-text substring
                               matching on "false positive"/"withdrawn" was
                               tried and dropped (main#1348 — 17/17 wave-29
                               hits were prose false alarms, including
                               grammatically-genuine-looking retraction
                               language pointing at an unrelated finding);
                               only an explicit self-mark counts.
  orchestrator_caused_rework   Subset of must_fix_received whose blocking
                               comment carried ``OrchestratorCaused:`` — the
                               block stemmed from a dispatch/brief error, not
                               the author's work (main#1366). Excluded from
                               the rate bars via
                               ``Signals.attributable_rework()``; the raw
                               must_fix_received count is unchanged.
  ===========================  ============================================

CLI:
  trust_signals.py extract <P> <M> [--status PATH]    # signals as JSON
  trust_signals.py score   <P> <M> [--status PATH]    # signals + proposed
                                                      # deltas + forced
                                                      # negative-signal line
  trust_signals.py calibration <P> <M> [--status PATH]  # rate-band calibration
                                                        # check; EXIT 1 = the
                                                        # bars have drifted
                                                        # (main#1368)
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

# wave_status lives alongside this file in .claude/lib/. Running as a script puts
# this dir on sys.path[0]; the tests add it explicitly.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import wave_state  # noqa: E402
import wave_status  # noqa: E402

_REPO_ROOT = wave_state.REPO_ROOT
_DEFAULT_STATUS = wave_state.DEFAULT_STATUS_PATH

# Neutral / default trust score. Decay drifts unsignalled scores back to it.
NEUTRAL = 3
MIN_SCORE = 1
MAX_SCORE = 5

# Decay: no trust-relevant signal for this many waves → drift one step toward
# NEUTRAL (a 4 with nothing to say for 3 waves is no longer evidence of a 4).
DECAY_AFTER_WAVES = 3

# Retirement: sustained bottom-tier or repeated CI-red merges over K waves.
RETIRE_AFTER_WAVES = 3
BOTTOM_TIER = 2

# Rework bands (main#1349, owner ruling 2026-08-07). Both are must-fix-received
# coefficients **per PR authored**, applied to `prs_merged` as a multiplication
# so the comparison stays integer — no ratio, no float, no zero-guard. Named
# rather than inlined for the same reason NEUTRAL / BOTTOM_TIER /
# DECAY_AFTER_WAVES are: they are tuning knobs, and the charter states their
# values (`.claude/team/trust_matrix.md` § The two rework bands), so a change
# here is a charter change and is pinned as such by the tests.
CLEAN_BAR_MUST_FIX_PER_PR = 1
PENALTY_BAR_MUST_FIX_PER_PR = 2

# ---- Calibration basis for the two bars above (main#1368) ----------------- #
#
# #1349 happened because `must_fix_received >= 3` was calibrated for a 1-2
# reviewer world, silently became wrong at 3-6 review heads, and carried no
# statement of what it assumed — so nobody noticed for eleven waves. The bars
# above are rate-relative, which makes them robust to review *breadth* in a way
# the old absolute threshold was not. They are NOT robust to a change in how
# much rework is normal per PR, which is a function of head count, PR size and
# review depth. So the assumption is recorded here, and `calibration_drift`
# below turns it into something a future wave can mechanically check.
#
# Derived from P10W29 (the wave #1349 was filed against): 45 PRs, 10 authors,
# 3-6 independent review heads. The observed must-fix-per-PR distribution had
# median exactly 1.00 (0.00, 0.25, 0.44, 0.50, 1.00, 1.00, 2.00, 2.00, 2.14,
# 3.00). The clean bar was set AT that median so a typical author clears it,
# and the penalty bar at TWICE it so only a genuine rate outlier is dinged.
#
# The bars stop meaning what they were set to mean if the wave's median rate
# moves materially away from 1.0 — that is the revisit trigger, and it is
# checked by `trust_signals.py calibration <P> <M>`, which exits non-zero.
CALIBRATION_WAVE = "P10W29"
CALIBRATION_MEDIAN_RATE = 1.0
CALIBRATION_REVIEW_HEADS = (3, 6)
# How far the observed wave median may sit from CALIBRATION_MEDIAN_RATE before
# the bars are no longer where they were meant to be. 0.5 keeps the acceptable
# band at [0.5, 1.5]: at 1.5 the clean bar has fallen below the typical author
# (most of the roster forfeits the bump), and at 0.5 the penalty bar has risen
# to 4x the typical author (effectively unreachable).
CALIBRATION_DRIFT_TOLERANCE = 0.5
# A median over a handful of authors is noise, not a measurement — the same
# objection the #1349 ruling raised against median-relative *scoring*. Below
# this many authors the check reports "insufficient sample", never "drifted".
CALIBRATION_MIN_AUTHORS = 5

# A verdict comment field, e.g. ``Requestor: Aino Virtanen`` or the bold form
# ``**Requestor:** Aino Virtanen`` (feedback_pr_review_verdict_format). Optional
# surrounding ``**`` on the label AND the value; value trimmed of trailing bold.
#
# #1347: ``verdict`` used to capture only ``(\w+)`` — the first word — so
# ``RequestOrReplied: Changes Requested`` captured just ``"Changes"`` and the
# equality check against ``"changesrequested"`` silently failed, dropping the
# verdict from every counter. Widened to a full-line capture mirroring
# requestor/requestee; classification of the captured text into a verdict
# kind is now a separate step (`_verdict_kind`, below) so trailing text past
# the first word (e.g. ``Approved (post-merge)``) doesn't defeat an exact
# match either.
_FIELD_RE = {
    "requestor": re.compile(r"^\**Requestor\**:\**\s*(.+?)\**\s*$", re.MULTILINE),
    "requestee": re.compile(r"^\**Requestee\**:\**\s*(.+?)\**\s*$", re.MULTILINE),
    "verdict": re.compile(r"^\**RequestOrReplied\**:\**\s*(.+?)\**\s*$", re.MULTILINE),
}

# Canonical verdict-kind vocabulary for the `RequestOrReplied:` field.
# Reviewers write ChangesRequested three ways in practice: the
# charter-canonical one-word `ChangesRequested`, the human-typed spaced
# `Changes Requested`, and the short `Changes`.
#
# main#1359 (MF1 on this PR, Aino/Nino): an earlier version of this comment
# argued extraction was blocked by a dependency-direction problem and that
# the two sibling hooks already agreed on all three spellings. BOTH claims
# are false and were verified false, not merely disputed:
#
#   * There is no dependency-direction problem. The shared home for this
#     vocabulary already exists, in `.claude/lib/`, not `.claude/hooks/`:
#     `.claude/lib/charter_trailer.py` (main#932/#934) is the org's declared
#     "single source of truth for the charter trailer-block convention",
#     and this module already does `sys.path.insert(0, ...parent)`, so
#     `import charter_trailer` costs zero path changes.
#     `charter_trailer.extract_charter_field("RequestOrReplied", body)`
#     ALREADY returns `"Changes Requested"` correctly — the value
#     `_FIELD_RE["verdict"]` above reproduces was already correct, one file
#     over, before this PR ever touched the regex.
#   * The two sibling hooks do NOT already agree.
#     `.claude/hooks/validate_review_comment_format.py`'s
#     `_VERDICT_DIRECTIONS` (~line 664) deliberately EXCLUDES bare
#     `changes` — its own comment: "The bare 'Changes' prefix is NOT a
#     verdict on its own." `.claude/hooks/validate_pr_review.py`'s
#     `_VERDICT_REQUIRING_TECH_DEBT` (~line 1410) includes it. The siblings
#     disagree with each other, which is an argument FOR one shared owner,
#     not evidence that copies are safe.
#
# `_VERDICT_KIND` / `_normalize_verdict_token` / `_verdict_kind` stay a
# private copy in THIS PR anyway, for the two reasons that survived
# scrutiny: (1) scope discipline — this is a retro PR landing two verified
# defect fixes (#1347, #1348); migrating to `charter_trailer` means adding
# a verdict-KIND classifier to ITS public API (it currently only extracts
# raw field values, it does not classify Request/Reply vs
# Approved/ChangesRequested) and re-verifying two hooks with large test
# surfaces — real, cross-file work that does not belong bundled into this
# fix. (2) a REAL, already-diverged dependency, not a hypothetical one:
# `_strip_code_markup` (below) and `charter_trailer.strip_code_regions` are
# two copies of one concept in the same directory that already disagree
# outcome-changingly for the new `Retracted:` guard —
# `_strip_code_markup` strips `~~~`-fenced code blocks, `strip_code_regions`
# does not, and `_strip_code_markup`'s answer is the more correct one here.
# Folding `~~~` support into `charter_trailer` has to happen as PART of the
# migration, not incidentally alongside it. Extraction is real, tracked
# work: main#1359.
_VERDICT_KIND = {
    "approved": "approved",
    "changesrequested": "changesrequested",
    "changes": "changesrequested",
    "request": "request",
    "reply": "reply",
    "replied": "reply",
}


def _normalize_verdict_token(raw: str) -> str:
    """Casefold + strip everything but alphanumerics from one token.

    Collapses spelling/formatting variants of the SAME token to one key
    (``**ChangesRequested**`` and ``ChangesRequested`` both normalize to
    ``"changesrequested"``).
    """
    return re.sub(r"[^a-z0-9]", "", raw.casefold())


def _verdict_kind(verdict: str | None) -> str:
    """Classify a captured ``RequestOrReplied`` value into a canonical kind.

    Returns ``"approved"``, ``"changesrequested"``, ``"request"``,
    ``"reply"``, or ``""`` for anything unrecognized. Only the FIRST word of
    the (now full-line) captured value is classified — ``"changes"`` alone
    already maps to ``"changesrequested"`` in :data:`_VERDICT_KIND`, so both
    the one-word ``ChangesRequested`` and the spaced ``Changes Requested``
    resolve via their shared first word, and trailing noise past the first
    word (e.g. ``Approved (post-merge)``) never defeats the match.
    """
    if not verdict:
        return ""
    parts = verdict.split()
    if not parts:
        return ""
    return _VERDICT_KIND.get(_normalize_verdict_token(parts[0]), "")


# main#1348: a bare word match (`false[\s-]?positive|withdrawn|...`) over the
# whole comment body was tried first and produced a 100% false-positive rate
# in the wave-29 audit (17/17 hits wrong) — reviewers discussing their own
# false-positive test corpus, naming the defect class in prose, or
# retracting an unrelated note, all read identically to a genuine
# self-retraction to a substring search. One sampled hit ("retracted my
# earlier '...' note") is grammatically indistinguishable from a real
# retraction while pointing at a different finding entirely — no amount of
# regex tightening over free prose can separate the two.
#
# Gated on an explicit, structured same-comment ``Retracted:`` field instead
# (mirrors the `Requestor:`/`Requestee:`/`RequestOrReplied:` field shape).
# This is a narrower, module-local convention — NOT the org's floated
# cross-comment `RequestOrReplied: Retracted` + latest-verdict-wins design
# (`validate_review_comment_format.py` module docstring, "Scope boundary"
# section, ~lines 120-144), which needs comment-ordering semantics and is
# explicitly future work ("proposed there, not implemented here").
#
# main#1364 promoted the field from a module-local convention to a charter
# obligation (`.claude/team/charter/pull-requests/reviews.md` § Optional
# verdict fields) validated by `validate_review_comment_format.py`. A hook
# cannot *require* a conditional field — nothing can tell it a comment is
# retracting something — so the obligation is: documented in the charter,
# named in reviewer briefs, and validated whenever it IS present. Adoption is
# what turns `review_false_positives`'s zero from an artifact into evidence.
_RETRACTION_RE = re.compile(r"^\**Retracted\**:\**\s*\S", re.MULTILINE)

# main#1366: rework caused by an orchestrator dispatch/brief error rather than
# by the author's work. `must_fix_received` counts blocking rounds against the
# author with no way to express this, so misattributed rework lands on their
# score — documented in prose in the wave-29 matrix entry for Lucas Ferreira
# ("partly attributable to the orchestrator's unbatched dispatch during the
# #1333 push freeze") and invisible to the instrument one column over.
#
# Same shape and same constraints as `Retracted:` above, deliberately: an
# explicit structured field on the ChangesRequested comment that raises the
# block, set at the time it happens by whoever raises it. NOT an appeal
# mechanism — it cannot be added after the fact to re-litigate a score,
# because the extractor reads the durable PR thread, and a marker that
# appears later changes nothing already applied. #842 retired narrative
# self-grading; an attribution nobody can check would reintroduce it through
# the back door, which is why this is a countable field and not a retro note.
_ORCHESTRATOR_CAUSED_RE = re.compile(r"^\**OrchestratorCaused\**:\**\s*\S", re.MULTILINE)


def _strip_code_markup(text: str) -> str:
    """Remove fenced code blocks and inline code spans from *text*.

    Called before :data:`_RETRACTION_RE` is applied so that a quoted example
    or symbol name containing the literal ``Retracted:`` field shape inside
    a code span or fenced block (e.g. someone pasting a sample comment) is
    not mistaken for a genuine self-mark.  The removal is positional — we
    replace each code region with whitespace of the same length so that
    surrounding context positions are preserved for any subsequent
    line-oriented parsing, though :data:`_RETRACTION_RE` does not rely on
    positions.
    """
    # Fenced blocks first (```...``` or ~~~...~~~, possibly multiline).
    text = re.sub(r"```.*?```|~~~.*?~~~", lambda m: " " * len(m.group()), text, flags=re.DOTALL)
    # Inline code spans (`...`); single-backtick, non-newline interior.
    text = re.sub(r"`[^`\n]+`", lambda m: " " * len(m.group()), text)
    return text


@dataclass
class Signals:
    """Countable per-engineer signals for one wave. All fields are evidence."""

    prs_merged: int = 0
    must_fix_received: int = 0
    must_fix_caught: int = 0
    ci_red_merges: int = 0
    rework_cycles: int = 0
    review_false_positives: int = 0
    # Subset of must_fix_received marked `OrchestratorCaused:` on the blocking
    # comment — rework the author did not cause (main#1366). Never exceeds
    # must_fix_received: it is only set on a ChangesRequested verdict, which
    # increments both.
    orchestrator_caused_rework: int = 0
    # PR numbers the engineer authored (for the evidence citation in the line).
    authored_prs: list[int] = field(default_factory=list)

    def has_signal(self) -> bool:
        """True if anything trust-relevant happened — drives the decay path."""
        return any(
            (
                self.prs_merged,
                self.must_fix_received,
                self.must_fix_caught,
                self.ci_red_merges,
                self.rework_cycles,
                self.review_false_positives,
            )
        )

    def has_negative(self) -> bool:
        """True if **any** negative signal occurred at all — an absolute test.

        This answers the literal reporting question "is there a gap to cite?",
        and it is what :func:`negative_signal_line` needs: that function's
        ``else`` branch prints a hard-coded ``must_fix_received=0`` in its
        "metrics clean" evidence string, so weakening this predicate would make
        it emit a false number.

        **This is NOT the scoring gate.** The bar that decides whether a wave
        has earned a *bump* is :meth:`qualifies_for_bump`, which is
        deliberately weaker on the rework dimension (main#1349). The two
        predicates were one predicate until #1349; conflating them is the
        defect that issue reports. Do not re-merge them.
        """
        return bool(self.must_fix_received or self.ci_red_merges or self.review_false_positives)

    def attributable_rework(self) -> int:
        """Must-fix rounds attributable to the **author's own work** (main#1366).

        ``must_fix_received`` minus the rounds explicitly marked
        ``OrchestratorCaused:`` on the blocking comment. This is what the rate
        bars measure — the question they are asking is "how much rework did
        this engineer's work generate", and a round caused by an unbatched
        dispatch or a wrong brief is not an answer to it.

        ``must_fix_received`` itself stays the raw, honest count and is what
        :meth:`has_negative` and :func:`negative_signal_line` report, so the
        forced negative-signal pass still shows every round that happened. The
        ``max(0, ...)`` is defensive only; extraction cannot produce a marked
        count above the total.
        """
        return max(0, self.must_fix_received - self.orchestrator_caused_rework)

    # ---- Rework bands (main#1349) ---------------------------------------- #
    #
    # ``must_fix_received`` counts blocking verdict ROUNDS received as an
    # author. Under the 3-6 independent review heads this org runs, those are
    # abundant *by design* — one genuine defect found independently by three
    # reviewers counts three times. An **absolute** threshold over that number
    # therefore measures review breadth, not author quality, which is why the
    # old ``must_fix_received == 0`` clean gate was unreachable for every
    # active author and the old ``>= 3`` penalty tripped on a single defect.
    #
    # Both bars are expressed **per PR authored**, as a multiplication — no
    # float, no zero-guard. ``prs_merged == 0`` implies
    # ``must_fix_received == 0`` (``extract_signals`` only ever increments the
    # two together), so ``0 <= 0`` classifies a non-authoring engineer as
    # within the clean bar naturally.
    #
    #     within clean bar   : must_fix_received <= prs_merged      (<= 1 / PR)
    #     above penalty bar  : must_fix_received >  2 * prs_merged  ( > 2 / PR)
    #
    # Between them sits a **neutral band** — above the clean bar so no bump,
    # below the penalty bar so no ding.

    def rework_within_clean_bar(self) -> bool:
        """True if authoring rework is at or below **1 must-fix per PR merged**.

        The rework half of :meth:`qualifies_for_bump`; on its own it says
        nothing about CI-red merges or review false-positives. The coefficient
        is :data:`CLEAN_BAR_MUST_FIX_PER_PR`.
        """
        return self.attributable_rework() <= CLEAN_BAR_MUST_FIX_PER_PR * self.prs_merged

    def rework_above_penalty_bar(self) -> bool:
        """True if authoring rework exceeds **2 must-fix per PR merged**.

        The ``-1`` rework ding in :func:`score_delta`. Strictly stronger than
        :meth:`rework_within_clean_bar` being false — the gap between the two
        is the neutral band, which is neither a bump nor a ding. The
        coefficient is :data:`PENALTY_BAR_MUST_FIX_PER_PR`.
        """
        return self.attributable_rework() > PENALTY_BAR_MUST_FIX_PER_PR * self.prs_merged

    def qualifies_for_bump(self) -> bool:
        """True if the wave is clean enough to reach :func:`score_delta`'s positive branch.

        Weaker than ``not has_negative()`` on the **rework dimension only**:
        rework is judged against the per-PR clean bar rather than against an
        absolute zero. The two hard dings — CI-red merges and review
        false-positives — still disqualify absolutely, unchanged from the
        pre-#1349 gate (the ruling: "``ci_red_merges`` and
        ``review_false_positives`` remain absolute per-instance ``-1``s, the
        positive branch still requires ``clean``").
        """
        return (
            self.rework_within_clean_bar()
            and not self.ci_red_merges
            and not self.review_false_positives
        )


@dataclass
class Verdict:
    """A parsed verdict comment: who reviewed whom, the call, and its markers."""

    requestor: str | None
    requestee: str | None
    verdict: str | None
    false_positive: bool
    # `OrchestratorCaused:` — this block stems from a dispatch/brief error, not
    # from the author's work (main#1366). Defaulted so existing constructions
    # stay valid.
    orchestrator_caused: bool = False


def parse_verdicts(comment_bodies: list[str]) -> list[Verdict]:
    """Parse the org's verdict-comment shape out of a PR's comment bodies.

    Pure function — no I/O. Accepts both the bare (``Requestor: Name``) and bold
    (``**Requestor:** Name``) forms so it matches everything Hook 4 accepts. A
    comment with no ``RequestOrReplied`` line is not a verdict and is skipped —
    this still builds a :class:`Verdict` for ``Request``/``Reply`` comments
    (some callers want the full set), but see :func:`_verdict_kind`: those two
    kinds can never carry ``false_positive=True`` (main#1348).
    """
    out: list[Verdict] = []
    for body in comment_bodies:
        verdict_m = _FIELD_RE["verdict"].search(body)
        if not verdict_m:
            continue
        req_m = _FIELD_RE["requestor"].search(body)
        ree_m = _FIELD_RE["requestee"].search(body)
        verdict_str = verdict_m.group(1).strip()
        # A retraction only counts on a ChangesRequested comment — the
        # reviewer must have actually raised a finding on THIS comment for
        # there to be anything to retract. Approved never raised one;
        # Request/Reply are process metadata, not verdicts at all
        # (main#1348 defect 2). Strip code spans and fenced blocks first so
        # a quoted/pasted example containing the literal `Retracted:` shape
        # is not mistaken for a real self-mark.
        scanned = _strip_code_markup(body)
        is_changes_requested = _verdict_kind(verdict_str) == "changesrequested"
        is_false_positive = is_changes_requested and bool(_RETRACTION_RE.search(scanned))
        # `OrchestratorCaused:` is gated identically and for the same reason
        # (main#1366): there is no rework round to reattribute unless THIS
        # comment raised a block.
        is_orchestrator_caused = is_changes_requested and bool(
            _ORCHESTRATOR_CAUSED_RE.search(scanned)
        )
        out.append(
            Verdict(
                requestor=req_m.group(1).strip() if req_m else None,
                requestee=ree_m.group(1).strip() if ree_m else None,
                verdict=verdict_str,
                false_positive=is_false_positive,
                orchestrator_caused=is_orchestrator_caused,
            )
        )
    return out


def _is_changes_requested(verdict: str | None) -> bool:
    """True if *verdict* (a captured ``RequestOrReplied`` value) is ChangesRequested.

    #1347: routes through :func:`_verdict_kind` so the three spelling
    variants (``ChangesRequested`` / ``Changes Requested`` / ``Changes``)
    all classify identically — the previous
    ``verdict.lower() == "changesrequested"`` exact-match silently dropped
    the spaced form because the capturing regex used to stop at the first
    space.
    """
    return _verdict_kind(verdict) == "changesrequested"


def _pr_comment_bodies(repo: str, number: int) -> list[str]:
    """Every issue-comment body on a PR (verdict comments live here)."""
    raw = wave_status._run_gh(
        [
            "api",
            f"repos/noorinalabs/{repo}/issues/{number}/comments",
            "--jq",
            "[.[].body]",
        ]
    )
    parsed = json.loads(raw or "[]")
    return [str(b) for b in parsed]


def _pr_ci_is_red(repo: str, number: int) -> bool:
    """True if the PR's latest status rollup carries a failing required check.

    Reads ``statusCheckRollup`` at the PR head. Post-merge this reflects the
    final state of the merged head, which is the closest mechanical proxy for
    "merged with red CI" available after the fact (memory
    feedback_statuscheckrollup_ci_clean — local pass != CI pass; the rollup is
    the oracle). Treats both the checks-API ``conclusion`` and the legacy
    commit-status ``state`` failure vocabularies as red.
    """
    raw = wave_status._run_gh(
        [
            "pr",
            "view",
            str(number),
            "--repo",
            f"noorinalabs/{repo}",
            "--json",
            "statusCheckRollup",
            "--jq",
            ".statusCheckRollup",
        ]
    )
    rollup = json.loads(raw or "[]") or []
    red = {"FAILURE", "ERROR", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED"}
    for check in rollup:
        status = (check.get("conclusion") or check.get("state") or "").upper()
        if status in red:
            return True
    return False


def extract_signals(phase: str, wave: str, status_path: Path) -> dict[str, Signals]:
    """Build the ``{engineer_name: Signals}`` map for one wave.

    Author identity is the head commit's author name (``commit_author_name`` from
    :func:`wave_status.merged_prs` — the same identity the top-concentration
    metric uses). Reviewer identity is the ``Requestor:`` field of the verdict
    comment, because the gh principal that posts comments is the orchestrator,
    not the reviewer (memory feedback_gh_cli_gotchas).
    """
    prs = wave_status.merged_prs(phase, wave, status_path)
    signals: dict[str, Signals] = {}

    def _bucket(name: str) -> Signals:
        return signals.setdefault(name, Signals())

    for pr in prs:
        author = pr.get("commit_author_name") or "(unknown)"
        repo = pr["repo"]
        number = pr["number"]

        author_sig = _bucket(author)
        author_sig.prs_merged += 1
        author_sig.authored_prs.append(number)

        if _pr_ci_is_red(repo, number):
            author_sig.ci_red_merges += 1

        verdicts = parse_verdicts(_pr_comment_bodies(repo, number))
        pr_had_changes_requested = False
        for v in verdicts:
            if _is_changes_requested(v.verdict):
                pr_had_changes_requested = True
                author_sig.must_fix_received += 1
                # Marked rounds still count in the raw total (the round DID
                # happen); attribution is applied by Signals.attributable_rework
                # when the rate bars are evaluated (main#1366).
                if v.orchestrator_caused:
                    author_sig.orchestrator_caused_rework += 1
                if v.requestor:
                    _bucket(v.requestor).must_fix_caught += 1
            if v.false_positive and v.requestor:
                _bucket(v.requestor).review_false_positives += 1
        if pr_had_changes_requested:
            author_sig.rework_cycles += 1

    return signals


def score_delta(sig: Signals) -> int:
    """Evidence-anchored, **bidirectional** trust delta for one wave.

    Pure function of the countable signals — never a narrative judgement. The
    mapping is intentionally simple and symmetric, clamped to [-2, +2] so a
    single wave cannot swing trust across the whole scale:

      negative
        - each CI-red merge:                      -1  (hard ding)
        - each review false-positive:             -1
        - rework above the penalty bar
          (must_fix_received > 2 * prs_merged):   -1
      positive (only when Signals.qualifies_for_bump())
        - 2+ PRs merged:                          +1
        - 2+ must-fix items caught as reviewer:   +1

    **Two-band rework rule (main#1349, owner ruling 2026-08-07).** The rework
    signal is rate-relative, not absolute, and the two bars do not touch:

        must_fix_received <= prs_merged        -> clean   (bump eligible)
        prs_merged < recv <= 2 * prs_merged    -> NEUTRAL (no bump, no ding)
        must_fix_received >  2 * prs_merged    -> penalty (-1)

    The neutral band is the point of the design: an author with more rework
    than the clean bar allows forfeits the bump, but does not take a ding
    until the rate is genuinely an outlier. Both bars live on
    :class:`Signals` (:meth:`~Signals.rework_within_clean_bar`,
    :meth:`~Signals.rework_above_penalty_bar`) so each boundary is
    independently testable.

    The positive branch gate is :meth:`Signals.qualifies_for_bump`, **not**
    :meth:`Signals.has_negative` — see those two docstrings. Before #1349 they
    were the same predicate, which made the entire positive branch unreachable
    for any author who received even one blocking verdict.
    """
    delta = 0
    delta -= sig.ci_red_merges
    delta -= sig.review_false_positives
    if sig.rework_above_penalty_bar():
        delta -= 1

    if sig.qualifies_for_bump():
        if sig.prs_merged >= 2:
            delta += 1
        if sig.must_fix_caught >= 2:
            delta += 1

    return max(-2, min(2, delta))


def rework_rate_median(signals: dict[str, Signals]) -> float | None:
    """Median must-fix-received per PR across the wave's authors.

    ``None`` when nobody authored anything. Non-authoring engineers are
    excluded (a rate is undefined without a denominator); every author counts
    once regardless of volume, because this measures where the *typical author*
    sits, which is what the bars were calibrated against.

    This is the only float in the module and it is deliberately **diagnostic
    only** — it never feeds :func:`score_delta`, whose bars stay integer
    multiplications (main#1349: "no float, no zero-guard"). Nothing here can
    change a score.
    """
    rates = sorted(s.must_fix_received / s.prs_merged for s in signals.values() if s.prs_merged)
    if not rates:
        return None
    mid = len(rates) // 2
    if len(rates) % 2:
        return rates[mid]
    return (rates[mid - 1] + rates[mid]) / 2


def calibration_drift(signals: dict[str, Signals]) -> tuple[bool, str]:
    """Has the wave drifted far enough that the rate bars no longer sit right?

    Returns ``(drifted, human_readable_reason)``. The revisit trigger for
    :data:`CLEAN_BAR_MUST_FIX_PER_PR` / :data:`PENALTY_BAR_MUST_FIX_PER_PR`
    (main#1368) — see the calibration block beside those constants for what
    they assume and why.

    Drift is **not** a defect and not a reason to withhold a wave's scores. It
    is a signal that the coefficients were calibrated against a different
    world and should be re-derived by an owner decision, exactly as #1349
    re-derived the thresholds it replaced.
    """
    authors = sum(1 for s in signals.values() if s.prs_merged)
    if authors < CALIBRATION_MIN_AUTHORS:
        return False, (
            f"insufficient sample: {authors} author(s) < {CALIBRATION_MIN_AUTHORS} — "
            f"a median this thin is noise, not a measurement; calibration not assessed"
        )
    median = rework_rate_median(signals)
    assert median is not None  # authors >= CALIBRATION_MIN_AUTHORS >= 1
    delta = abs(median - CALIBRATION_MEDIAN_RATE)
    band = (
        CALIBRATION_MEDIAN_RATE - CALIBRATION_DRIFT_TOLERANCE,
        CALIBRATION_MEDIAN_RATE + CALIBRATION_DRIFT_TOLERANCE,
    )
    detail = (
        f"observed median {median:.2f} must-fix/PR over {authors} authors; "
        f"calibrated at {CALIBRATION_MEDIAN_RATE:.2f} ({CALIBRATION_WAVE}, "
        f"{CALIBRATION_REVIEW_HEADS[0]}-{CALIBRATION_REVIEW_HEADS[1]} review heads); "
        f"acceptable band [{band[0]:.2f}, {band[1]:.2f}]"
    )
    if delta > CALIBRATION_DRIFT_TOLERANCE:
        return True, (
            f"CALIBRATION DRIFT: {detail}. The clean bar "
            f"({CLEAN_BAR_MUST_FIX_PER_PR}x) and penalty bar "
            f"({PENALTY_BAR_MUST_FIX_PER_PR}x) were set against the calibrated "
            f"median and no longer sit where they were meant to. Re-derive them "
            f"by owner decision (see main#1368); do not silently keep scoring."
        )
    return False, f"calibration OK: {detail}"


def decay(old_score: int, waves_since_signal: int, *, after: int = DECAY_AFTER_WAVES) -> int:
    """Drift an unsignalled score one step toward NEUTRAL after ``after`` waves.

    No signal for N waves is itself a (weak) signal: a stale 4 or 2 is no longer
    earned. Drifts a single step per call so decay is gradual, never a reset.
    """
    if waves_since_signal < after:
        return old_score
    if old_score > NEUTRAL:
        return old_score - 1
    if old_score < NEUTRAL:
        return old_score + 1
    return NEUTRAL


@dataclass
class Proposal:
    """One engineer's pending score change, as fed to distribution discipline.

    Carries ``old_score`` because the cap is an **entry gate**: it exists to
    stop a 5 being handed out too freely, not to evict an engineer who already
    holds one. Before main#1365 this type was a bare
    ``(proposed_score, signals)`` tuple, the old score was never passed, and so
    the entry-vs-eviction distinction lived only in prose in
    ``trust_matrix.md`` and ``wave-retro/SKILL.md`` — untestable, and wrong the
    first time it was applied mechanically (it capped a ceiling-holder with a
    ``+2`` delta down to 4, turning the delta into a net ``-1``).

    Named fields rather than the 3-tuple the issue proposed: ``old_score`` and
    ``proposed_score`` are adjacent same-typed ints, and a positional swap
    between them is silent, plausible, and exactly the misuse this type exists
    to prevent.
    """

    old_score: int
    proposed_score: int
    signals: Signals

    def is_ceiling_holder(self) -> bool:
        """True if the engineer was already at the ceiling before this wave.

        Such an engineer is exempt from the cap — they are not *entering* the
        ceiling, so there is nothing for an entry gate to gate. Four waves of
        applied history agree: W25 held 4 engineers at 5, W26 6, W27 5, W28 5
        — 20 rows, none ever evicted.
        """
        return self.old_score >= MAX_SCORE


def apply_distribution_discipline(
    proposals: dict[str, Proposal],
) -> dict[str, int]:
    """Cap 5 to the wave's exceptional **relative** performers (distribution
    discipline). 5 is reserved — it is not handed out for merely-clean work.

    A proposed 5 is allowed only for the engineer(s) whose composite signal
    score is the wave maximum AND strictly positive; every other proposed 5 is
    capped to 4. Scores of 4 and below pass through untouched, and so does any
    :class:`Proposal` whose ``old_score`` is already at the ceiling
    (:meth:`Proposal.is_ceiling_holder` — this is an entry gate, not an
    eviction rule).

    **The one caller obligation the signature cannot carry: feed it the whole
    roster.** ``top`` is the maximum composite *within the batch*, so a
    restricted batch silently changes the answer — an engineer can become their
    own maximum and keep a 5 the full-roster run would cap. Concretely, over
    wave-29's two ceiling entrants alone the batch maximum becomes 8 (Nadia's
    own composite) instead of 17 (Aino's), and Nadia keeps a 5. This is
    inherent to a relative rule and is pinned by
    ``DistributionDiscipline::test_top_is_batch_relative_so_feed_the_whole_roster``
    so it is known behaviour rather than a surprise.
    """

    def composite(s: Signals) -> int:
        # Reward output + good reviewing; penalise the negatives. Pure ranking
        # key, not a trust score.
        #
        # Uses the RAW must_fix_received, not the orchestrator-adjusted
        # attributable count (main#1366). Deliberate: composite is a relative
        # ranking key for one cap, the attribution adjustment was ruled for the
        # absolute rate bars, and changing a ranking key has no evidence base
        # here. Revisit as its own decision, not incidentally.
        return (
            s.prs_merged
            + s.must_fix_caught
            - s.must_fix_received
            - 2 * s.ci_red_merges
            - 2 * s.review_false_positives
        )

    if not proposals:
        return {}
    top = max(composite(p.signals) for p in proposals.values())
    out: dict[str, int] = {}
    for name, p in proposals.items():
        capped = (
            p.proposed_score >= MAX_SCORE
            and not p.is_ceiling_holder()
            and not (composite(p.signals) == top and top > 0)
        )
        out[name] = MAX_SCORE - 1 if capped else p.proposed_score
    return out


def negative_signal_line(name: str, sig: Signals) -> str:
    """The forced negative-signal pass line for one engineer.

    Bans the bare ``None``: every active engineer gets either a specific,
    evidence-backed gap OR an explicit ``metrics clean: {numbers}`` statement
    that still shows the receipts. Never returns an empty / "None" string.
    """
    if sig.has_negative():
        gaps = []
        if sig.ci_red_merges:
            gaps.append(f"{sig.ci_red_merges} CI-red merge(s)")
        if sig.must_fix_received:
            gap = f"{sig.must_fix_received} must-fix received"
            if sig.orchestrator_caused_rework:
                # Show both numbers — the raw count is what happened, the
                # attributable count is what the rate bars scored (main#1366).
                gap += (
                    f" ({sig.orchestrator_caused_rework} orchestrator-caused, "
                    f"{sig.attributable_rework()} attributable)"
                )
            gaps.append(gap)
        if sig.review_false_positives:
            gaps.append(f"{sig.review_false_positives} review false-positive(s)")
        return f"{name}: " + ", ".join(gaps)
    return (
        f"{name}: metrics clean: prs_merged={sig.prs_merged}, "
        f"must_fix_received=0, ci_red_merges=0, false_positives=0, "
        f"must_fix_caught={sig.must_fix_caught}"
    )


# Bare-"None" detector for the forced negative-signal pass. A negative-signal
# entry of exactly "None" / "n/a" / "-" (case-insensitive, optional bullet /
# trailing punctuation) is the banned shape.
_BARE_NONE_RE = re.compile(r"^\s*[-*]?\s*(none|n/?a|-+)\s*[.;]?\s*$", re.IGNORECASE)


def validate_negative_signal_pass(lines: list[str]) -> list[str]:
    """Return the offending lines that are a bare "None" (forced-pass violation).

    Empty return == the pass is clean. Used by ``/wave-retro`` to mechanically
    reject a retro that left a bare "None" in the negative-signal column.
    """
    return [ln for ln in lines if _BARE_NONE_RE.match(ln)]


def retirement_trigger(
    score_history: list[int],
    ci_red_history: list[int],
    *,
    k: int = RETIRE_AFTER_WAVES,
) -> tuple[bool, str]:
    """Performance-triggered exit. Returns (should_retire, reason).

    Two independent triggers over the most recent ``k`` waves (oldest→newest):
      * sustained bottom-tier: score <= BOTTOM_TIER in each of the last k waves.
      * repeated CI-red merges: >=1 CI-red merge in each of the last k waves.

    Fewer than k waves of history never triggers — there isn't enough evidence.
    """
    recent_scores = score_history[-k:]
    if len(recent_scores) >= k and all(s <= BOTTOM_TIER for s in recent_scores):
        return True, (
            f"sustained bottom-tier: score <= {BOTTOM_TIER} for {k} consecutive "
            f"waves ({recent_scores})"
        )
    recent_ci = ci_red_history[-k:]
    if len(recent_ci) >= k and all(c >= 1 for c in recent_ci):
        return True, (f"repeated CI-red merges: >=1 in each of {k} consecutive waves ({recent_ci})")
    return False, ""


def _cmd_extract(args: argparse.Namespace) -> int:
    sigs = extract_signals(args.phase, args.wave, args.status)
    print(json.dumps({n: asdict(s) for n, s in sigs.items()}, indent=2, sort_keys=True))
    return 0


def _cmd_score(args: argparse.Namespace) -> int:
    sigs = extract_signals(args.phase, args.wave, args.status)
    # This command reports what each engineer would score *seeded from neutral*
    # — it has no access to real old scores — so every proposal is a ceiling
    # entrant by construction (NEUTRAL < MAX_SCORE) and the cap applies to all
    # of them, exactly as it did before main#1365. /wave-retro Step 5 is the
    # caller that passes real old scores and therefore exempts ceiling-holders.
    proposals = {
        n: Proposal(old_score=NEUTRAL, proposed_score=NEUTRAL + score_delta(s), signals=s)
        for n, s in sigs.items()
    }
    disciplined = apply_distribution_discipline(proposals)
    report = {
        n: {
            "signals": asdict(s),
            "delta": score_delta(s),
            "proposed_from_neutral": disciplined[n],
            "negative_signal_line": negative_signal_line(n, s),
        }
        for n, s in sigs.items()
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def _cmd_calibration(args: argparse.Namespace) -> int:
    """Rate-band calibration check (main#1368). **Exit 1 means drifted.**

    Deliberately a separate subcommand with a failing exit code rather than a
    field in ``score``'s JSON: a value someone has to notice is the same shape
    as the eleven-wave silence #1349 was filed about. ``/wave-retro`` runs this
    as a mandatory step, so a drifted wave stops the retro and forces a
    decision instead of scoring quietly against stale coefficients.
    """
    sigs = extract_signals(args.phase, args.wave, args.status)
    drifted, reason = calibration_drift(sigs)
    print(reason)
    return 1 if drifted else 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    def _add_pm(p: argparse.ArgumentParser) -> None:
        p.add_argument("phase", help="phase number (P)")
        p.add_argument("wave", help="wave number (M)")
        wave_state.add_status_argument(p)

    p_extract = sub.add_parser("extract", help="emit per-engineer signals as JSON")
    _add_pm(p_extract)
    p_extract.set_defaults(func=_cmd_extract)

    p_score = sub.add_parser("score", help="emit signals + proposed deltas as JSON")
    _add_pm(p_score)
    p_score.set_defaults(func=_cmd_score)

    p_cal = sub.add_parser(
        "calibration",
        help="check the rate bars against the wave's observed median (exit 1 = drifted)",
    )
    _add_pm(p_cal)
    p_cal.set_defaults(func=_cmd_calibration)
    return parser


def main(argv: list[str]) -> int:
    args = _build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except KeyError as exc:
        print(f"ERROR: missing key in cross-repo-status.json: {exc}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        print(
            f"ERROR: gh call failed (exit {exc.returncode}): {' '.join(exc.cmd)}\n{exc.stderr}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
