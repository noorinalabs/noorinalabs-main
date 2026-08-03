"""Single source of truth for the charter trailer-block convention.

Why this module exists (main#932/#934, Oyunbileg Batbayar)
==========================================================

The charter defines a review comment as prose followed by a **trailer block**:
the structured fields, last, after a sole `---` line. Two hooks must agree on
what that means:

* ``validate_pr_review`` — counts verdicts (the two-reviewer gate).
* ``validate_review_comment_format`` — validates the field shape and the
  Requestor/Requestee direction.

Before this module, the scoping rules lived only in ``validate_pr_review``.
``validate_review_comment_format`` matched fields with a bare, unscoped
``re.search`` over the whole body. That single line produced **two opposite
failures**, and which one fired depended on the reviewer's sentence:

* **fail-closed** — a correctly-formed, correctly-directed verdict was BLOCKED
  when the reviewer explained the rule in prose and the prose's final token
  happened to be the PR author's surname. ``_extract_lastname`` takes the last
  token, so ``"... Requestor: Wanjiku Mwangi, Requestee: Khoury"`` yielded
  ``Khoury``, matched the branch author, and tripped the swap heuristic.
* **fail-open** — a genuinely swapped trailer PASSED whenever some earlier
  prose match produced a non-author surname first.

The obvious repair — give the format hook its own trailer scan — would leave
the charter's trailer convention defined in two hand-maintained copies. That
is precisely the rot that produced the false "Hook 4 first-matches your prose"
memory (retired; now ``feedback_pr_review_verdict_format`` §6): the rule
described in one place, implemented in another, with nothing
tying them together. So the definition is lifted here and **both hooks scope
through the one function**. A second definition should be impossible, not
kept in sync.

Placement
---------

``.claude/lib/`` by orchestrator decision (main#932). Both hooks add the lib
directory to ``sys.path`` and import from here; nothing else defines these
functions. The requirement is **singularity** — one definition, no drifting
copy — and the location makes it reachable from ``.claude/lib/`` tooling as
well as from the two hooks.

The three functions move together on purpose: ``strip_code_regions`` replaces
code spans with **spaces** rather than deleting them, precisely so that
``trailer_block_substring``'s sole-``---`` line detection still sees the same
line structure. Splitting them would silently break that invariant.
"""

from __future__ import annotations

import re

__all__ = [
    "branch_author_first_initial",
    "extract_branch_author_lastname",
    "extract_charter_field",
    "is_branch_author",
    "is_wave_branch",
    "name_first_initial",
    "name_lastname",
    "strip_code_regions",
    "trailer_block_substring",
]


def strip_code_regions(body: str) -> str:
    """Strip fenced code blocks (```…```) and inline code (`…`) from `body`.

    Returns a body where every char inside a code region is replaced with a
    space (preserving line indices for downstream regex). This prevents
    reviewer prose like `` `Requestor: (TBD)` `` from being captured as the
    actual Requestor value (#511 — Bereket-on-deploy#339 pattern).

    The replacement char is space (not empty) so any `re.search` line/column
    arithmetic remains accurate against the original `body`'s line offsets,
    making `trailer_block_substring`'s `---`-line detection unaffected.
    """
    out: list[str] = []
    i = 0
    n = len(body)
    while i < n:
        # Fenced code: ```...``` (triple-backtick on its own or with lang tag).
        if body.startswith("```", i):
            end = body.find("```", i + 3)
            if end == -1:
                # Unterminated fence — strip rest of body.
                out.append(" " * (n - i))
                break
            out.append(" " * (end + 3 - i))
            i = end + 3
            continue
        # Inline code: `...` on a single span (no newlines inside the run).
        if body[i] == "`":
            end = body.find("`", i + 1)
            if end == -1 or "\n" in body[i + 1 : end]:
                # Not a closed inline span — pass through as literal.
                out.append(body[i])
                i += 1
                continue
            out.append(" " * (end + 1 - i))
            i = end + 1
            continue
        out.append(body[i])
        i += 1
    return "".join(out)


def trailer_block_substring(body: str) -> str:
    """Return the trailer-block substring of `body` for field extraction.

    Trailer-block definition (#511):
      - If `body` contains one or more lines that are a sole `---` separator
        (charter convention for delimiting the structured-fields block), the
        trailer is everything AFTER the LAST such separator line.
      - Otherwise (legacy comments without separator), fall back to the full
        body — `extract_charter_field` then uses last-match-wins to remain
        forgiving while still avoiding most prose-above-trailer false-matches.

    The `---` must be on a line by itself (with optional leading/trailing
    whitespace) to count. Embedded `---` within a sentence does not count.
    """
    lines = body.splitlines(keepends=True)
    last_sep_idx = -1
    for idx, line in enumerate(lines):
        if line.strip() == "---":
            last_sep_idx = idx
    if last_sep_idx == -1:
        return body
    return "".join(lines[last_sep_idx + 1 :])


def extract_charter_field(field_name: str, body: str) -> str | None:
    """Extract a charter-format field value from a comment body.

    Handles markdown bold (`**Field:**`) and plain (`Field:`) variants.
    Returns the value with markdown markers and parenthetical role
    descriptions stripped. Returns None if the field is not present.

    Match-scope discipline (#511):
      - First, strip fenced (``` ... ```) and inline (`...`) code regions to
        prevent reviewer prose-quoting from being captured as a verdict field
        (Bereket-on-deploy#339 pattern).
      - Then narrow to the trailer-block substring per charter convention
        (text after the last `---` separator line). If no separator is
        present, fall back to the full body to remain backward-compatible
        with legacy verdict comments.
      - Within that scope, use LAST-MATCH-WINS so a prose mention of the
        field above the trailer block (without a separator) does not
        outscore the actual trailer line (Wanjiku-on-main#509 / Lucas-on-
        deploy#337 pattern).

    `field_name` is a parameter, so this helper answers for whatever label you
    hand it: `extract_charter_field("Verdict", body)` will happily return
    `"Approved"`. The binding to the charter's field name lives at the call
    site, never here.
    """
    scope = trailer_block_substring(strip_code_regions(body))
    pattern = rf"\*{{0,2}}{re.escape(field_name)}:\*{{0,2}}\s*(.+)"
    matches = list(re.finditer(pattern, scope))
    if not matches:
        return None
    match = matches[-1]
    value = match.group(1).strip()
    # Drop trailing content after first newline (single-line field).
    value = value.split("\n", 1)[0].strip()
    # Strip markdown bold and parenthetical role descriptions.
    value = value.strip("*").strip()
    value = re.sub(r"\s*\(.*?\)\s*$", "", value).strip()
    return value or None


# ---------------------------------------------------------------------------
# Person identity (main#1172)
# ---------------------------------------------------------------------------
#
# Both hooks answer the same question — "is the person named in this charter
# field the PR's branch author?" — and both answered it by comparing LASTNAMES
# alone. The roster has 78 names and it contains surname collisions: `Lucas
# Ferreira` and `Santiago Ferreira` are two distinct people. On branch
# `L.Ferreira/1151-...` a lastname-only comparison folds them together, and the
# two hooks fail in opposite directions off the same wrong answer:
#
#   validate_review_comment_format — Santiago's correct Approved is BLOCKED as
#       a swapped verdict (false positive; there is no observable-body
#       workaround, so the verdict simply cannot be posted).
#   validate_pr_review             — the same verdict is dropped from the
#       reviewer set as "self-review", so the PR sits at 1 of 2 approvals.
#
# `validate_pr_review` already fixed the sibling defect for its reviewer-dedup
# key in #164 by keying on the FULL name rather than the lastname. The identity
# comparison here cannot use the full name (the branch encodes only
# `{FirstInitial}.{LastName}`), so the maximal available discriminator is
# first-initial + lastname — which is exactly what the branch prefix carries.
# `L.Ferreira` vs `Santiago Ferreira` differ on the initial and are correctly
# two people; `L.Ferreira` vs `Lucas Ferreira` agree and are correctly one.
#
# Fail direction: when the initial cannot be derived from EITHER side (a
# single-token name such as a bare `Ferreira`, or a branch whose prefix does
# not parse), the comparison falls back to lastname-only — i.e. it keeps the
# pre-#1172 answer, which errs toward calling a stranger the branch author.
# That is the fail-CLOSED direction for both call sites (block the comment /
# do not count the reviewer). Widening it would trade this fix's false positive
# for a false negative in a gate, which is not a trade a gate may make.


def _name_tokens(field_value: str) -> list[str]:
    """Split a person-name field value into its name tokens.

    Strips markdown bolding, surrounding whitespace, and a trailing
    parenthetical role annotation (e.g. `Nadia Khoury (Program Director)`),
    then splits on whitespace or dot. Empty tokens are dropped, so both
    `Santiago Ferreira` and `S.Ferreira` yield two tokens.
    """
    raw = field_value.strip().strip("*").strip()
    cleaned = re.sub(r"\s*\(.*?\)\s*$", "", raw).strip()
    return [t for t in re.split(r"[\s.]+", cleaned) if t]


def name_lastname(field_value: str) -> str:
    """Extract a lastname from a person-name field value.

    Returns the final name token. Falls back to the single token when the value
    carries no separator, and to `""` when it is empty.
    """
    tokens = _name_tokens(field_value)
    return tokens[-1] if tokens else ""


def name_first_initial(field_value: str) -> str:
    """Return the lowercased first initial of a person-name field value.

    Returns `""` when no initial is derivable — a single-token value (`Ferreira`)
    has no first name to take an initial from, and an empty value has nothing at
    all. Callers MUST treat `""` as "unknown", never as a distinguishing value.

    Accepts both the spelled-out form (`Santiago Ferreira` -> `s`) and the
    branch-style abbreviation (`S.Ferreira` -> `s`).
    """
    tokens = _name_tokens(field_value)
    return tokens[0][0].lower() if len(tokens) >= 2 else ""


# The charter branch prefix, parsed in ONE place (main#1175).
#
# Both `{Initial}` and `{Lastname}` are captured by this single pattern because
# the two readers of it — `branch_author_first_initial` and
# `extract_branch_author_lastname` — must agree on *whether* a ref carries the
# prefix at all, not merely on the substrings they pull out of it. When they
# were two hand-written regexes they drifted: `extract_branch_author_lastname`
# lived in both hooks, #179 taught `validate_pr_review`'s copy the dash
# separator, and `validate_review_comment_format`'s copy stayed slash-only for
# four months. On a dash branch the format hook's local parser returned None and
# short-circuited to allow-with-warning BEFORE `branch_author_first_initial`
# (which did accept dash) was ever consulted — two parsers over the same
# `head_ref`, disagreeing, with the un-consolidated one winning.
#
# Separator alternatives, both observed in production refs:
#   `A.Virtanen/0179-x`  charter spec (`branching.md`)
#   `A.Virtanen-0179-x`  observed on recent branches (#179)
# `_` is deliberately NOT accepted: it is the worktree-directory form, not a ref
# form, and admitting it here would widen who counts as a branch author.
#
# Why the lastname charset admits `-` and `'`, and why the separator carries a
# digit lookahead (main#1269 review, Weronika Zielinska)
# ----------------------------------------------------------------------------
# The first consolidation of this pattern kept the historical `([A-Za-z]+)`
# lastname charset. On a HYPHENATED surname that charset does not fail cleanly:
# the surname's own `-` satisfies the separator, so the match SUCCEEDS and
# returns a truncated lastname — `K.Mensah-Williams/0001-x` -> `Mensah`.
#
# That is not a degradation, it is an inversion, because the roster contains
# `Kofi Mensah` AND `Kofi Mensah-Williams` — two distinct people sharing a first
# initial. The truncated `Mensah` + initial `k` matches the OTHER person exactly,
# so on `K.Mensah-Williams/**` the format hook simultaneously:
#   fail-closed: BLOCKS Kofi Mensah's *correct* verdict as a swap, and
#   fail-open:   silently ALLOWS a genuinely swapped one.
# That is the unblockable-false-positive shape #1172 exists to eliminate and
# #934 already fixed once in this hook — reintroduced by a different mechanism.
# 11 roster members carry a hyphenated surname; 77 open branches across 4 child
# repos matched the prefix at the time of the fix.
#
# The separator is `/` OR `-` *followed by a digit*, rather than a bare `[-/]`,
# because the lastname charset now contains `-` itself. A plain wide charset
# (`([A-Za-z][A-Za-z'-]*)[-/]`) is greedy across the separator and mis-parses a
# dash-form ref with a non-numeric slug —
# `A.Virtanen-branch-name-with-no-number` -> `Virtanen-branch-name-with-no`,
# a confident wrong answer. Requiring a digit (the charter's mandatory `{IIII}`
# issue number) returns None there instead, i.e. it fails SAFE into the existing
# "cannot validate direction, allow with a warning" path.
#
# Known, deliberate limits — tracked on #1271, pinned by tests below:
#   * Non-ASCII surnames (`C.Méndez-Ríos/…`, `C.Novák/…`) return None, exactly as
#     they did before this change. Widening to Unicode letters would also widen
#     `branch_author_first_initial`, which feeds the *counting* merge gate, so it
#     is a separate decision and not smuggled in here. None is the fail-safe
#     direction for the format hook. Note the roster's own commit-identity emails
#     transliterate (`Carolina.Mendez-Rios@`), and every live branch uses the
#     ASCII form, which this pattern DOES parse.
#   * A surname whose hyphen is followed by a digit (`X.Smith-3rd/…` -> `Smith`)
#     still truncates. No roster surname has that shape, and the plain wide
#     charset truncates it identically — the digit lookahead is not the cause.
_BRANCH_AUTHOR_PREFIX_RE = re.compile(r"([A-Za-z])\.([A-Za-z][A-Za-z'-]*?)(?:/|-(?=\d))")


def branch_author_first_initial(head_ref: str) -> str:
    """Return the lowercased first initial from a `{Initial}.{Lastname}[-/]…` branch.

    Returns `""` when the head ref does not carry the charter branch prefix
    (e.g. a `deployments/phase-3/wave-29` wave-merge branch). Both separator
    styles seen in practice are accepted — `A.Virtanen/0179-x` (charter spec)
    and `A.Virtanen-0179-x` (observed). The dash form additionally requires the
    charter's `{IIII}` issue number to follow, so that a hyphenated surname is
    not split at its own hyphen (see `_BRANCH_AUTHOR_PREFIX_RE`).
    """
    match = _BRANCH_AUTHOR_PREFIX_RE.match(head_ref)
    return match.group(1).lower() if match else ""


def extract_branch_author_lastname(head_ref: str) -> str | None:
    """Extract the lastname from a `{FirstInitial}.{LastName}[-/]…` branch ref.

    Returns `None` — never `""` — when the ref carries no charter prefix
    (`main`, `deployments/phase-3/wave-29`, `dependabot/**`, `A.Virtanen_0179-x`).

    `None` vs `""` is **a typed invariant the tests pin**, not a runtime
    discriminator: every non-test consumer normalises the two together
    (`validate_pr_review.comment_scan_scope` and `:2020` test truthiness, `:2032`
    passes `branch_author_lastname or ""`, `validate_review_comment_format.check`
    tests `if not branch_author`). Returning `""` for an unmatched ref changes no
    live control flow — it was measured, and every failure it causes is a
    contract assertion. Keep the invariant (an unmatched ref and an author with an
    empty surname should not be the same value), but do not assume a caller is
    relying on the distinction while refactoring. Corrected from an earlier
    "load-bearing at both call sites" claim by the #1269 review.

    Hyphenated surnames parse whole (`K.Mensah-Williams/0001-x` ->
    `Mensah-Williams`); a truncating charset here silently renames one roster
    member into another. See `_BRANCH_AUTHOR_PREFIX_RE`.

    Case is preserved (`a.virtanen/…` -> `virtanen`); every consumer compares
    through `is_branch_author`, which lowercases both sides.

    Consolidated here from the two hook-local copies by main#1175 — see
    `_BRANCH_AUTHOR_PREFIX_RE` for what those copies cost.
    """
    match = _BRANCH_AUTHOR_PREFIX_RE.match(head_ref)
    if match:
        return match.group(2)
    return None


def is_branch_author(field_value: str, branch_lastname: str, branch_initial: str = "") -> bool:
    """True when the person named in `field_value` IS the branch author.

    `branch_lastname` / `branch_initial` come from the branch's
    `{FirstInitial}.{LastName}` prefix. A match requires the lastnames to agree
    (case-insensitively) AND — when both first initials are known — the initials
    to agree too. When either initial is unknown the lastname decides, which
    preserves pre-#1172 behaviour for names that carry no distinguishing signal.

    An empty `branch_lastname` never matches: the wave-merge sentinel
    (`check_comment_reviews(number, "", …)`, main#294) means "no implementer
    author", so no reviewer is the author.
    """
    if not branch_lastname:
        return False
    if name_lastname(field_value).lower() != branch_lastname.lower():
        return False
    field_initial = name_first_initial(field_value)
    branch_initial = branch_initial.lower()
    if field_initial and branch_initial and field_initial != branch_initial:
        # Same surname, different people (main#1172 — Lucas vs Santiago Ferreira).
        return False
    return True


# The charter's WAVE BRANCH ref shape, parsed in ONE place (main#1216).
#
# A wave branch is the integration branch a `wave-branch`-model wave accumulates
# its per-issue merges on (`pull-requests/wave-merge.md` § One Merge Model Per
# Wave). It is the second charter-defined ref shape, alongside the
# `{Initial}.{Lastname}` author prefix above, and it lives here for the same
# reason that one does: two hooks must agree on what it means.
#
#   validate_pr_review        — a wave->main integration PR applies no
#                               commit-derived self-review exclusion (main#1216).
#   block_squash_wave_merge   — `gh pr merge --squash` into a wave branch is
#                               hard-blocked (Hook 22, main#898/#222).
#
# BOTH `phase-N` AND `phaseN` ARE ACCEPTED, because both are in production. The
# form the charter writes is `deployments/phase-{P}/wave-{M}`; the form 4 of the
# org's repos actually use is `deployments/phase{P}/wave-{M}`. Measured on
# 2026-08-03 over every `deployments/**`-head PR in all 7 repos (202 PRs): 168
# carry the dashed form and **32 carry the undashed one** — 28 distinct refs
# across isnad-graph, design-system, data-acquisition and landing-page
# (`deployments/phase15/wave-1`, `deployments/phase10/wave-4`, …).
#
# That measurement is also a finding about the hook this pattern is consolidated
# FROM: `block_squash_wave_merge.WAVE_BRANCH_RE` was `^deployments/phase-\d+/
# wave-\d+$`, so Hook 22's squash guard answered "not a wave branch" for a wave
# branch on all 32. Reusing one pattern closes that as a byproduct, in the
# fail-CLOSED direction (more squashes blocked, never fewer).
#
# SCOPE OF THAT GAP, STATED HONESTLY: the undashed form is HISTORICAL. All 32
# PRs date from 2026-03-15..2026-04-06 and every wave-branch NAME CONSTRUCTOR in
# the repo emits the dashed form (`wave_merge_model`, `validate_wave_audit`,
# `validate_wave_label_evidence`, `post_wave_kickoff_comment`, `wave_unwrapped`,
# `framework.config.json`), so nothing produces the undashed spelling today. It
# still matters because wave branches are RETAINED permanently as rollback
# anchors (memory `feedback_wave_branch_merge_retain`) — those 28 refs are live
# and squashable — but this is a historical-tail fix, not a live outage.
#
# Writing a second, wider pattern in `validate_pr_review` instead would have left
# the two definitions to drift exactly as `extract_branch_author_lastname`'s two
# copies did for four months (main#1175) — one definition, no drifting copy.
#
# ANCHORED AT BOTH ENDS, deliberately. `deployments/phase-3/wave-6-hotfix` and
# `deployments/phase12/cleanup` (2 real PRs in isnad-graph) are NOT wave
# branches, and each consumer's fail direction on a non-match is the safe one:
# the merge gate keeps its commit-derived exclusion, Hook 22 keeps allowing a
# squash it was already allowing.
_WAVE_BRANCH_RE = re.compile(r"^deployments/phase-?\d+/wave-\d+$")


def is_wave_branch(ref: str) -> bool:
    """True when `ref` is a charter wave branch — `deployments/phase{-}N/wave-M`.

    See `_WAVE_BRANCH_RE` for why both the dashed and undashed `phase` forms are
    accepted and why the pattern is anchored. A `None`/empty ref is False, so a
    caller that could not read the head ref gets "not a wave branch" — the
    answer that leaves every consumer's stricter path in force.
    """
    return bool(ref) and bool(_WAVE_BRANCH_RE.match(ref))
