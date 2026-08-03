#!/usr/bin/env python3
"""Validate implementer/reviewer names in a wave-scope matrix against rosters.

Pre-#319 `/wave-scope` did not validate names in the matrix — a stale alias
like "Anya Volkov" (canonical: "Anya Kowalczyk") propagated through scope
and only surfaced at first-spawn time. P3W7 logged both substitutions in
`wave_7_decisions.implementer_substitutions`. This script runs at scope
time and surfaces unknown names BEFORE `/wave-kickoff` fan-out.

Two orthogonal checks (#319 + #1134)
====================================
1. **Name resolution (#319)** — does the declared name exist at all? Resolved
   against the parent roster UNION the target repo's roster, because org-level
   coordinators legitimately fill child-repo *review* slots. For **review-class**
   slots the org-union manifest is unioned in as well (#1162 — see below).
2. **Repo membership (#1134)** — for the `implementer` slot on a CHILD repo,
   is the name on *that repo's own* roster? A name can resolve (check 1) and
   still fail this, which is exactly the recurring bug: a parent-org persona
   scoped as the implementer of a child-repo story.

Review-class slots resolve against the org-union manifest too (#1162)
=====================================================================
The parent side of the check-1 union is the parent's **card directory**
(`.claude/team/roster/*.md`, 9 names), not the org-union **manifest**
(`.claude/team/roster.json`, 78 names). A reviewer legitimately drawn from a
THIRD child repo — permitted by `charter/agents/spawn-discipline.md`
§ Child-Repo Implementer Rule step 5 — is on neither the parent's cards nor the
target repo's, so it was reported UNRESOLVED with "(no close matches)". Live
instance: `Nikolaos Papadopoulos` / `Oyunbileg Batbayar` (cards in
`noorinalabs-data-acquisition`) reviewing `isnad-ingest-platform` stories in W28.

Manifest entries are filtered to PERSONAS only (#1181)
=======================================================
#1181 measured `roster.json` (78 entries) against the union of every roster
card in the org (60 names) and found 18 manifest-only entries — names the
manifest widens the review-class set with but that back no spawnable persona
anywhere. Two of the 18 are not merely uncarded, they are DEFINITIONALLY not
reviewers: `Annunaki` (the error-monitoring tool's commit identity — it posts
real PR comments, so admitting it as a `reviewer` is a live risk) and
`Steven French` mapping to the bare `parametrization@gmail.com` (no `+alias`
tag — the #1177 squash-collapse address, not a person's own address).

`_load_org_manifest_names` therefore only returns entries whose address is a
charter-conformant per-persona commit identity, `_PERSONA_ALIAS_RE`
(`<principal>+<First>.<Last>@<domain>`) — the SAME matcher
`.claude/hooks/validate_pr_review.py::_PERSONA_ALIAS_RE` uses for the
merge-time twin of this check (#1179/#1181; that gate got this filter first,
this one did not, which is exactly the drift #1181 flags). A small duplicated
regex across the two sibling parsers is the established pattern here (see
`_load_roster_names` below on the H1/verbose card dual-format regexes) rather
than a cross-module import between a hook and a skill.

Filtering on identity SHAPE — not a hand-maintained non-persona blocklist —
is deliberate: it keeps this gate correct today without waiting on a
disposition decision for the other 16 manifest-only names (prune vs onboard,
still open), and it stays correct if the manifest ever grows another tool
identity. The remaining 16 manifest-only names ARE persona-shaped and keep
resolving as reviewers post-#1181 — #1181 narrows the DEFINITIONALLY-wrong
two, it does not reconcile the other 16 (that disposition is tracked
separately; see `.claude/lib/roster_union_sync.py`'s manifest-orphan report).
Pre-existing since #319, but #1134 made § 12.5 mandatory over every canonical
`tier_*` row and added a hard `exit 1` at `/wave-kickoff` § 0b, turning a latent
gap into a STOP on a charter-permitted assignment.

Why the manifest is acceptable HERE and not everywhere. It is the LOOSER of the
two authorities, not the more authoritative one: a card directory is the thing a
repo actually vouches for, while `roster.json` is a flat union manifest that can
carry a name whose card has been removed. It is trusted for review-class slots
because of the CONSEQUENCE asymmetry, not because it is a better source — a
review slot never commits, and a wrong reviewer name fails LOUDLY and later
(the merge gate blocks on a missing approval; cf. #1179, where a third-child
reviewer's approval is not yet counted at all). A wrong IMPLEMENTER name fails
silently and expensively — the W28 mechanical merge-commit re-attribution. Match
the authority to the blast radius; do not read this as licence to widen the
manifest's use to any slot whose failure mode is quiet.

The manifest is deliberately NOT unioned into the `implementer` resolution set.
Doing so would loosen check 2 in the `unverified` case: when the target repo's
roster is unreadable (not cloned — the CI case), membership fails OPEN, so a
third-child implementer that newly *resolved* would exit 0 where today it exits
1 as an unresolved name. Keeping the commit-capable resolution set narrow means
the only way that slot passes is a name the target repo can actually vouch for.

Unknown role slots default to the STRICT side (#1180)
=====================================================
Both loosenings above — the manifest widening the resolution set, and the
membership check not applying — hang off the REVIEW class, so `REVIEW_CLASS_ROLES`
is the allowlist and everything else, *including a role nobody has classified*,
takes the commit-capable path. The seam was originally written the other way
round (`COMMIT_CAPABLE_ROLES` as the allowlist, review as the fall-through),
which meant an unclassified slot silently inherited BOTH loosenings.

Measured against the pre-fix module, on a `co_implementer` slot — a name that is
semantically commit-capable, it would have to commit in the target repo:

    {"noorinalabs-user-service": {"co_implementer": "Nikolaos Papadopoulos"}}
        -> "all 1 names resolved", exit 0   (loosening 1: the manifest widened
           a commit-capable slot; his cards live in a THIRD child repo)

    {"noorinalabs-user-service": {"co_implementer": "Nurul Hakim"}}
        -> "all 1 names resolved", exit 0   (loosening 2: #1134 membership
           skipped — this is the W27/W28 cross-repo-implementer failure exactly,
           re-admitted by nothing more than renaming the slot key)

Note the FIRST measurement is what the `#1180` issue body approximated with a
three-slot matrix (`co_implementer` / `pair_implementer` / `fixer`); that matrix
also names `Annunaki` and `Steven French`, which #1181's persona-shape filter
already rejects, so it exits 1 for reasons unrelated to this seam and MASKS the
one slot that actually passes. Isolate the slot when re-measuring.

The asymmetry is the same consequence argument as § Why the manifest is
acceptable HERE: a slot wrongly treated as review-class fails silently and
expensively (the W28 mechanical merge-commit re-attribution); a slot wrongly
treated as commit-capable fails loudly and cheaply at scope time, and the fix is
one line in `REVIEW_CLASS_ROLES`. Default to the failure you can see.

The same reasoning drives slot DISCOVERY. Scope mode used to iterate a hardcoded
tuple of the four live slots, a third place a role had to be listed, so an
unrecognised key there was not mis-classified but skipped outright (measured: a
3-slot row reported "all 2 names resolved", exit 0). It now walks the row via
`is_role_slot_key`, which admits `KNOWN_ROLE_SLOTS` plus any agentive-shaped key
(`_ROLE_SLOT_KEY_RE`) not explicitly denied in `NON_ROLE_ROW_KEYS`. An admitted
but unclassified key is reported `slot_class="unclassified"` and fails the run —
NOT merely warned about, because a warning printed inside an otherwise-green job
is exactly the advisory posture § Hard fail already records as insufficient.

Suggestions are ADVISORY and are drawn from the WIDEST set (#1182)
==================================================================
The narrow-resolution rule above governs what RESOLVES. It must not also govern
what the report is allowed to SAY. Sourcing `suggestions` from the same narrow
`combined` set made the validator print a claim it could disprove from a local
in the same call frame:

    # noorinalabs-user-service deliberately not cloned; real org roster data
    {"noorinalabs-user-service": {"implementer": "Anya Kowalczyk",
                                  "reviewer":    "Anya Kowalczyk"}}

        implementer: 'Anya Kowalczyk'  ->  suggestions: (no close matches)
        reviewer     resolved=True

`Anya Kowalczyk` is an exact key of the `org_manifest` set `validate()` had
already loaded, and is a real member of the target repo's own roster. So the
report asserted "(no close matches)" about a name it held, and the SAME name in
the SAME run resolved one line above — leaving an operator unable to tell
whether the persona exists at all. The printed remediation then steered toward
recording an `implementer_substitution`, i.e. toward changing a CORRECT
assignment, when the real remedy (`--fetch-missing` / clone the repo) was only
named on the `unverified` path this row never reaches.

`suggestions` is advisory text: nothing reads it, and it never feeds `resolved`
or the exit code. So it is sourced from `review_combined` for every slot, and an
unresolved commit-capable name that IS a known org persona whose target roster
could not be read gets its own diagnostic (`unresolved_reason`) pointing at
`--fetch-missing` instead of at the substitution guidance.

This is deliberately MESSAGE-ONLY. `resolved` stays False and the exit code
stays 1 for exactly the rows they did before — the #1134 carve-out pinned by
`test_manifest_does_not_pass_implementer_on_uncloned_repo` is untouched, and
`test_1182_message_change_is_semantically_inert` pins the inertness directly so
a later "improvement" cannot quietly relax it. Widening the RESOLUTION set here
is the over-broad variant that flips this case to `resolved=True
membership=unverified`, exit 0 — the silent pass #1134 exists to stop.

Why check 2 is implementer-only. The implementer is the only role that must
produce a **commit in the target repo**, where `validate_commit_identity`
(Hook 5) resolves the author against that repo's roster. Reviewers never
commit there, and the charter explicitly permits cross-team reviewers
(`charter/agents/spawn-discipline.md` § Child-Repo Implementer Rule, step 5:
"Reviewer assignment is a separate decision"). Applying membership to review
slots would break that rule and produce noise.

Live instance this closes (#1134): Nurul Hakim (parent roster, NOT on the
user-service roster) was scoped as implementer of `user-service#204` in W27
and again in W28. Check 1 passed — Nurul is a real persona — so scope shipped
green, and at wrap time PR us#212's merge commit was mechanically re-attributed
to Nadia Boukhari while the implementor label still said Nurul
(`wave_28_decisions.implementer_substitutions`). Running check 2 retroactively
over `wave_28_scope` finds a SECOND, never-recorded instance: Weronika
Zielinska on `isnad-graph#1191`.

This gate is the only enforcement point, not merely an earlier one
==================================================================
The issue framed the runtime identity gate as a correct backstop that "fires
too late". Measured 2026-07-27, it does not fire at all for this class:
`validate_commit_identity._load_merged_roster(<child>)` merges the PARENT
`roster.json` — the 78-name org union manifest — over the child's, so from a
child repo root every parent persona resolves; and neither
`noorinalabs-user-service` nor `noorinalabs-isnad-graph` ships its own identity
hook or a CI identity job. That is consistent with the observed W28 split:
Weronika's isnad-graph commits went through unblocked. Closing that runtime gap
is tracked separately; until it lands, scope time is where this rule lives,
which is why the failure below is a hard exit-1 rather than a warning.

Hard fail, with an explicit RECORDED override
=============================================
A cross-repo implementer assignment fails (exit 1) unless the scope row carries
a `roster_union_override` object with a non-empty `rationale`. It is deliberately
NOT a warning and deliberately NOT an unconditional block:

- A bare warning is what already existed — the pre-#1134 validator printed
  "all N names resolved" for the Nurul/user-service pairing. Three waves of
  recurrence (W27 → W28 → W29) is the evidence that advisory output does not
  hold this line.
- An unconditional block with no escape hatch would be worked around, because
  a genuinely-intended cross-repo assignment does occur (parent-flavored work
  landing inside a child repo). A gate operators route around decays, and the
  W28 mechanical-merge re-attribution is precisely that kind of workaround.

The override therefore lives in the scope DATA (`cross-repo-status.json`), so it
is a committed, reviewable diff rather than a verbal decision — which is what
makes "no wave reaches wrap-time with a *silent* substitution" true.

Usage
=====
    # Matrix mode (back-compatible, repo → role-slots)
    validate_matrix_names.py <matrix-json-path>

    # Scope mode (#1134) — reads wave_{M}_scope.tier_*[] rows directly
    validate_matrix_names.py --scope <cross-repo-status.json> --wave 29

Matrix-mode input shape:

    {
        "noorinalabs-isnad-graph": {
            "implementer": "Anya Kowalczyk",
            "reviewer": "Idris Diallo",
            "reviewer_2": "Marcia Vieira"
        },
        "noorinalabs-deploy": {
            "implementer": "Bereket Tesfaye",
            "reviewer": "Lucas Pham",
            "reviewer_2": "Aino Virtanen"
        }
    }

Scope-mode reads the canonical wave-scope rows instead of a hand-transcribed
matrix — the repo is derived from each row's `id` (`noorinalabs-user-service#204`
→ `noorinalabs-user-service`), so the check cannot be defeated by forgetting to
copy a row into the matrix.

Exit codes:
    0 — all names resolve, every child-repo implementer is a repo member (or
        carries a recorded override), and every slot key is classified
    1 — one or more names don't resolve, OR a child-repo implementer is not on
        that repo's roster and has no recorded override, OR a slot key is in
        neither `COMMIT_CAPABLE_ROLES` nor `REVIEW_CLASS_ROLES` (#1180)
    2 — invalid input

Resolution:
    - For each per-repo entry, read `<parent>/<repo>/.claude/team/roster/*.md`
      and extract the member name (both card formats — see _load_roster_names).
    - For parent-repo entries (repo == "noorinalabs-main" or no repo), fall
      back to the parent's own `.claude/team/roster/`.
    - Review-class slots additionally resolve against the parent's org-union
      manifest `.claude/team/roster.json` (#1162).
    - Case-insensitive exact match wins.
    - On miss: fuzzy-match (difflib SequenceMatcher) and print the top-3
      closest matches as suggestions.

Unverifiable repos fail OPEN. If the target child repo is not cloned beside the
parent (the CI case, and the normal case for a repo an operator has not pulled),
its roster dir is absent and membership CANNOT be decided. Such a row is
reported `membership: "unverified"` and does NOT fail the run — the same posture
`roster_union_sync.fetch_child_roster` and `premise_check`'s WARN verdict take
for cross-repo reads. `--fetch-missing` opts into resolving those repos over the
network by reusing `roster_union_sync.fetch_child_roster`, rather than growing a
second GitHub-fetch implementation here.

Relationship to `.claude/lib/roster_union_sync.py`: that gate answers a
DIFFERENT question — "does the committed parent union manifest cover every child
persona?" (manifest coverage, network-backed, advisory/continue-on-error). This
one answers "is this specific implementer a member of the repo they were scoped
into?" Neither subsumes the other; do not merge them.

The script is read-only — it never modifies the matrix, the scope file, or
rosters. The operator makes the substitution decision and re-runs.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

# Role slots that must be able to COMMIT in the target repo: narrow (#319 card)
# resolution + the #1134 repo-membership check.
COMMIT_CAPABLE_ROLES: frozenset[str] = frozenset({"implementer"})

# Review-class slots: the org-union manifest widens their resolution set (#1162)
# and the #1134 membership check does NOT apply to them (charter
# `spawn-discipline.md` § Child-Repo Implementer Rule step 5 permits cross-team
# reviewers). THIS is the allowlist the two loosenings hang off (#1180) — see
# § Unknown role slots default to the STRICT side in the module docstring.
REVIEW_CLASS_ROLES: frozenset[str] = frozenset({"reviewer", "reviewer_2", "merge_gate_reviewer"})

# Every slot key the validator knows how to classify. Scope mode drives its slot
# list off THIS union rather than a second hardcoded tuple, so adding a role to
# either frozenset above is the single edit that makes both modes see it (#1180).
KNOWN_ROLE_SLOTS: frozenset[str] = COMMIT_CAPABLE_ROLES | REVIEW_CLASS_ROLES

# Repo keys that mean "the parent repo itself" — membership is vacuous there
# (the parent roster IS the repo roster), so #1134 never fires on them.
PARENT_REPO_KEYS: frozenset[str] = frozenset({"", "noorinalabs-main", "main"})

# A manifest entry is a PERSONA only if its address is a charter-conformant
# per-persona commit identity: `<principal>+<First>.<Last>@<domain>` (CLAUDE.md
# § Key Rules / charter `pull-requests.md` § Commit Identity). Same matcher as
# `.claude/hooks/validate_pr_review.py::_PERSONA_ALIAS_RE` (#1179) — see
# `_load_org_manifest_names` below for why this module keeps its own small
# duplicate rather than importing across the hook/skill boundary (#1181).
_PERSONA_ALIAS_RE = re.compile(r"^[^\s@+]+\+[^\s@+]+\.[^\s@+]+@[^\s@]+\.[^\s@]+$")

# Scope rows carry role slots alongside free-form metadata (`id`, `ref`, `note`,
# `found_by`, `blocked_on`, ...), so scope mode cannot simply treat every string
# key as a person slot. Role slots in this schema are named after the AGENT that
# fills them, so the key's last `_`-component is agentive — ends in `-er`/`-or`,
# optionally with a `_<n>` ordinal (`reviewer_2`). Measured over all 293 rows in
# every `wave_*_scope` of `cross-repo-status.json` (2026-08-02) this matches the
# four known slots plus `pre_kickoff_blocker` and NOTHING else — the other 24
# metadata keys (`found_by`, `reassigned_from`, `blocked_by`, `coupled_with`,
# `follow_on_to`, `pair_with`, `scope_note`, `slate_note`, `open_risk`,
# `merged_sha`, `sequence`, `bundle`, `spawn`, `status`, `role`, ...) do not end
# in an agentive component.
_ROLE_SLOT_KEY_RE = re.compile(r"(?:^|_)[a-z]+(?:er|or)(?:_\d+)?$")

# Agentive-SHAPED row keys that are explicitly NOT person slots. This is the
# escape hatch that keeps `_ROLE_SLOT_KEY_RE`'s generosity cheap: a false
# positive costs one reviewable line here, not a redesign. `pre_kickoff_blocker`
# is the one live instance (a bool flag, `wave_29_scope`).
NON_ROLE_ROW_KEYS: frozenset[str] = frozenset({"pre_kickoff_blocker"})

# Not a role slot and not metadata — the recorded #1134 escape hatch, consumed
# by `_override_rationale` rather than validated as a name.
OVERRIDE_KEY = "roster_union_override"

# `unresolved_reason` values (#1182). PURELY diagnostic: they select which
# remediation paragraph is printed for an unresolved row and are read nowhere
# else — never by the exit-code arithmetic, which keys off `resolved`.
_REASON_ORG_PERSONA_UNREADABLE = "org-persona-unreadable-roster"
_REASON_UNKNOWN_NAME = "unknown-name"


def is_role_slot_key(key: str) -> bool:
    """Is `key` a scope-row key that names a PERSON filling a role slot? (#1180)

    Used by scope mode to decide which row keys to hand to `validate()`. A key is
    a role slot if it is one of `KNOWN_ROLE_SLOTS`, or — so a slot nobody has
    classified yet cannot be silently skipped — if it is agentive-shaped
    (`_ROLE_SLOT_KEY_RE`) and not explicitly denied in `NON_ROLE_ROW_KEYS`.

    An unknown agentive key is deliberately admitted rather than ignored:
    `validate()` then marks it `slot_class="unclassified"`, which is a hard
    exit-1 telling the operator to classify it. Ignoring it is the #1180 bug in
    its scope-mode form (measured: a 3-slot row reported "all 2 names resolved",
    exit 0 — the third slot was never looked at).
    """
    lowered = key.strip().lower()
    if lowered in KNOWN_ROLE_SLOTS:
        return True
    if lowered in NON_ROLE_ROW_KEYS or lowered == OVERRIDE_KEY:
        return False
    return bool(_ROLE_SLOT_KEY_RE.search(lowered))


def _find_org_dir() -> Path:
    """Find the directory that contains all `noorinalabs-*` repo checkouts.

    Org layout: `~/code/noorinalabs-main/` contains both the parent repo
    (itself, called `noorinalabs-main` at the org level) AND sibling-repo
    checkouts (`noorinalabs-deploy`, `noorinalabs-isnad-graph`, ...). So
    `noorinalabs-deploy` etc. live at `<org_dir>/noorinalabs-deploy/`, and
    the parent repo's own roster lives at `<org_dir>/.claude/team/roster/`.

    When invoked from a worktree (`<org_dir>/.claude/worktrees/<name>/`),
    walk up to the org_dir.
    """
    cwd = Path.cwd().resolve()
    for ancestor in [cwd, *cwd.parents]:
        if (ancestor / "noorinalabs-deploy").is_dir() and (
            ancestor / ".claude" / "team" / "roster"
        ).is_dir():
            return ancestor
    return cwd


def _load_roster_names(roster_dir: Path) -> set[str]:
    """Parse member names from every .md card in roster_dir.

    Handles BOTH roster card templates (union of matches, so a mixed-format
    roster dir mid-transition resolves every card, #1010):

      OLD (verbose): ``- **Name:** Foo Bar``
      NEW (slim):    ``# Foo Bar — Role`` (H1, em/en/hyphen separator)

    The H1 separator regex requires whitespace on BOTH sides of the dash
    (``\\s+[—–-]\\s+``) so a genuinely hyphenated name (``Jun-Seo Park``,
    ``Vega-Cruz``) is never split at its internal hyphen — same guard the
    sibling parsers use (roster_consistency_check.py, validate_pr_review.py).
    """
    names: set[str] = set()
    if not roster_dir.is_dir():
        return names
    name_re = re.compile(r"\*\*Name:\*\*\s+(.+?)\s*$", re.MULTILINE)
    h1_re = re.compile(r"^#\s+(.+?)\s+[—–-]\s+.+$", re.MULTILINE)
    for md_file in roster_dir.glob("*.md"):
        try:
            text = md_file.read_text()
        except OSError:
            continue
        for match in list(name_re.finditer(text)) + list(h1_re.finditer(text)):
            name = match.group(1).strip()
            # Trim role/status parentheticals (`Foo Bar (Tech Lead)`).
            name = re.sub(r"\s*\(.*?\)\s*$", "", name)
            if name:
                names.add(name)
    return names


def _load_org_manifest_names(org_dir: Path) -> set[str]:
    """Parse PERSONA names from the parent's org-union manifest `.claude/team/roster.json`.

    The manifest is a flat `{"<name>": "<email>"}` object covering every persona
    across the org (78 at time of writing) — a strict superset of the parent's
    own card directory, and the only place a persona from a repo that is not the
    target repo can be recognised without cloning that repo.

    **Persona filter (#1181).** Only entries whose address matches
    `_PERSONA_ALIAS_RE` are returned. The manifest is the LOOSER authority — it
    can (and, measured, does) carry an entry that backs no spawnable person:
    18 manifest-only names at #1181's measurement, of which `Annunaki` (the
    error-monitor's commit identity) and `Steven French` (the bare
    `parametrization@gmail.com` principal, no `+alias`) are DEFINITIONALLY not
    reviewers regardless of whether they ever get a roster card. Filtering on
    identity SHAPE keeps this gate correct today without waiting on the
    disposition of the other 16 (real-looking, still-uncarded) names, and
    stays correct if the manifest ever grows another tool identity.

    Fails OPEN (empty set) when the file is missing or malformed: the manifest
    only ever WIDENS the review-class resolution set, so an unreadable manifest
    degrades to exactly the pre-#1162 behaviour rather than blocking a run. A
    non-string address is likewise treated as non-persona rather than crashing
    — if `roster.json` ever grows a richer per-entry schema, this parser
    narrows rather than guessing, which is the recoverable direction.
    """
    path = org_dir / ".claude" / "team" / "roster.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    if not isinstance(data, dict):
        return set()
    return {
        name.strip()
        for name, address in data.items()
        if isinstance(name, str)
        and name.strip()
        and isinstance(address, str)
        and _PERSONA_ALIAS_RE.match(address.strip())
    }


def _load_repo_roster(org_dir: Path, repo: str) -> set[str]:
    """Load roster names for a given repo.

    `repo == "noorinalabs-main"` or empty → org_dir's own `.claude/team/roster/`
    (the parent repo's roster is at org-dir root, not under a sibling subdir).
    Else `<org_dir>/<repo>/.claude/team/roster/`.
    """
    if not repo or repo == "noorinalabs-main":
        return _load_roster_names(org_dir / ".claude" / "team" / "roster")
    return _load_roster_names(org_dir / repo / ".claude" / "team" / "roster")


def _suggest(name: str, candidates: set[str], top: int = 3) -> list[str]:
    """Return up to `top` closest matches from candidates via difflib."""
    if not candidates:
        return []
    return difflib.get_close_matches(name, sorted(candidates), n=top, cutoff=0.5)


def _fetch_repo_roster_names(repo: str, owner: str = "noorinalabs") -> set[str] | None:
    """Fetch a child repo's roster names over the network, or None if unavailable.

    Delegates to `.claude/lib/roster_union_sync.fetch_child_roster` rather than
    growing a second `gh api` implementation in this skill (#1134 review point —
    the org is actively paying down hand-rolled narrower duplicates). Returns
    None on any failure, which the caller treats as `unverified` (fail-open).
    """
    lib_dir = Path(__file__).resolve().parents[2] / "lib"
    if str(lib_dir) not in sys.path:
        sys.path.insert(0, str(lib_dir))
    try:
        from roster_union_sync import fetch_child_roster  # noqa: PLC0415
    except ImportError:
        return None
    roster = fetch_child_roster(owner, repo)
    return set(roster) if roster else None


def _override_rationale(override: object) -> str | None:
    """Extract a non-empty rationale from a `roster_union_override` value.

    Accepted shapes — a dict carrying a rationale, or a bare non-empty string
    used AS the rationale:

        "roster_union_override": {"rationale": "…", "approved_by": "owner"}
        "roster_union_override": "…"

    A bare `true` / `1` is deliberately REJECTED (returns None). An override
    with no stated reason is indistinguishable from the silent workaround this
    gate exists to prevent — the recorded rationale is the whole point.
    """
    if isinstance(override, str):
        return override.strip() or None
    if isinstance(override, dict):
        rationale = override.get("rationale")
        if isinstance(rationale, str) and rationale.strip():
            return rationale.strip()
    return None


def validate(
    matrix: dict[str, dict[str, object]],
    org_dir: Path,
    *,
    fetch_missing: bool = False,
    owner: str = "noorinalabs",
) -> dict[str, list[dict[str, object]]]:
    """Return a per-repo report of name → resolution status.

    Result shape (the `membership` / `override_rationale` keys are #1134
    additions; `role` / `declared` / `resolved` / `suggestions` are unchanged
    from #319 so existing callers keep working):

        {
            "noorinalabs-isnad-graph": [
                {"role": "implementer", "declared": "Anya Volkov",
                 "resolved": False, "membership": "n/a",
                 "suggestions": ["Anya Kowalczyk"]},
                ...
            ],
            ...
        }

    `membership` is one of:
      - ``"member"``     — commit-capable slot; name is on the target repo roster
      - ``"cross-repo"`` — commit-capable slot; name resolves only via the parent
                           union. FAILS unless the row records an override.
      - ``"overridden"`` — ``"cross-repo"`` plus a recorded override rationale
      - ``"unverified"`` — target repo roster unreadable (not cloned / no dir);
                           cannot decide, so does not fail
      - ``"n/a"``        — review-class slot, parent-repo row, or unresolved name

    `unresolved_reason` (#1182) is present on UNRESOLVED entries only and is
    purely diagnostic — it selects which remediation `_print_report_to_stderr`
    prints, and never changes `resolved` or the exit code:
      - ``"org-persona-unreadable-roster"`` — the name is a known org-manifest
        persona and the target repo's roster could not be read (not cloned).
        Remedy: `--fetch-missing` or clone the repo — NOT a substitution.
      - ``"unknown-name"``  — every other unresolved name.

    `slot_class` (#1180) is ``"known"`` when the slot key is in
    `KNOWN_ROLE_SLOTS`, else ``"unclassified"`` — a hard failure in
    `_print_report_to_stderr`. It is orthogonal to `resolved` / `membership`:
    an unclassified slot is ALSO validated (on the strict path), so a run can
    report both "this name does not resolve" and "this slot key is unknown".

    A per-repo `roster_union_override` may be supplied as a slot key alongside
    the role names; scope mode maps each row's own override onto its repo.
    """
    report: dict[str, list[dict[str, object]]] = {}
    # Parent rosters are always loaded — org-level coordinators (Nadia,
    # Wanjiku, Aino, Santiago) can appear in per-repo matrix slots when
    # reviewing parent-flavored work.
    parent_roster = _load_repo_roster(org_dir, "noorinalabs-main")
    # #1162: the org-union manifest widens the REVIEW-class resolution set only.
    org_manifest = _load_org_manifest_names(org_dir)
    for repo, slots in matrix.items():
        repo_roster = _load_repo_roster(org_dir, repo)
        is_parent_repo = repo in PARENT_REPO_KEYS
        # Membership is only decidable when we could actually read the target
        # repo's roster. An empty set from a child repo means "not cloned /
        # no roster dir", NOT "nobody is a member" — fail open (see docstring).
        if not repo_roster and not is_parent_repo and fetch_missing:
            fetched = _fetch_repo_roster_names(repo, owner)
            if fetched:
                repo_roster = fetched
        membership_decidable = is_parent_repo or bool(repo_roster)
        # Commit-capable slots keep the narrow #319 union (see module docstring
        # § Review-class slots for why the manifest must not widen this one).
        combined = parent_roster | repo_roster
        review_combined = combined | org_manifest
        override = _override_rationale(slots.get(OVERRIDE_KEY))
        repo_findings: list[dict[str, object]] = []
        for role, raw in slots.items():
            if role == OVERRIDE_KEY:
                continue
            if not raw or not isinstance(raw, str):
                continue
            declared = raw
            declared_clean = re.sub(r"\s*\(.*?\)\s*$", "", declared).strip()
            # #1180: REVIEW class is the allowlist. Anything else — including a
            # role nobody has classified — takes the strict commit-capable path:
            # narrow resolution AND the #1134 membership check.
            is_review_class = role in REVIEW_CLASS_ROLES
            candidates = review_combined if is_review_class else combined
            resolved = any(declared_clean.lower() == known.lower() for known in candidates)
            entry: dict[str, object] = {
                "role": role,
                "declared": declared,
                "resolved": resolved,
                "membership": "n/a",
                "slot_class": "known" if role in KNOWN_ROLE_SLOTS else "unclassified",
            }
            if not resolved:
                # #1182: advisory text is sourced from the WIDEST name set the
                # call frame holds, NOT from the (deliberately narrow)
                # resolution set — see module docstring § Suggestions are
                # ADVISORY. Nothing downstream reads `suggestions`, so this
                # cannot move `resolved` or the exit code.
                entry["suggestions"] = _suggest(declared_clean, review_combined)
                # An unresolved commit-capable name that IS a known org persona,
                # on a repo whose roster could not be read, is an ENVIRONMENT
                # gap (repo not cloned), not a bad assignment. It gets its own
                # remediation. Unreachable for review-class slots by
                # construction: `review_combined` contains `org_manifest`, so a
                # manifest name in a review slot has already resolved.
                in_manifest = any(declared_clean.lower() == known.lower() for known in org_manifest)
                entry["unresolved_reason"] = (
                    _REASON_ORG_PERSONA_UNREADABLE
                    if in_manifest and not membership_decidable
                    else _REASON_UNKNOWN_NAME
                )
                repo_findings.append(entry)
                continue
            # #1134: commit-capable slots on a child repo must be repo members.
            if not is_review_class and not is_parent_repo:
                if not membership_decidable:
                    entry["membership"] = "unverified"
                elif any(declared_clean.lower() == known.lower() for known in repo_roster):
                    entry["membership"] = "member"
                elif override:
                    entry["membership"] = "overridden"
                    entry["override_rationale"] = override
                else:
                    entry["membership"] = "cross-repo"
                    entry["repo_roster"] = sorted(repo_roster)
            repo_findings.append(entry)
        report[repo] = repo_findings
    return report


def repo_of_row(row: dict[str, object]) -> str:
    """Derive the target repo from a wave-scope assignment row (#1134).

    Rows carry `id` (`noorinalabs-user-service#204`) and usually a short `ref`
    (`user-service#204`). `id` is authoritative; the short form is expanded with
    the `noorinalabs-` prefix (and bare `main` → `noorinalabs-main`) so both
    shapes resolve to the same roster. Returns "" when neither parses, which the
    caller treats as a parent-repo row.
    """
    for key in ("id", "ref"):
        raw = row.get(key)
        if not isinstance(raw, str) or "#" not in raw:
            continue
        repo = raw.split("#", 1)[0].strip()
        if not repo:
            continue
        if repo == "main":
            return "noorinalabs-main"
        return repo if repo.startswith("noorinalabs-") else f"noorinalabs-{repo}"
    return ""


def _iter_tier_rows(scope: dict[str, object]) -> list[dict[str, object]]:
    """Yield every assignment-row dict across the scope object's `tier_*` arrays."""
    rows: list[dict[str, object]] = []
    for key, value in scope.items():
        if not key.startswith("tier_") or not isinstance(value, list):
            continue
        rows.extend(row for row in value if isinstance(row, dict))
    return rows


def validate_scope(
    scope: dict[str, object],
    org_dir: Path,
    *,
    fetch_missing: bool = False,
    owner: str = "noorinalabs",
) -> dict[str, list[dict[str, object]]]:
    """Validate a `wave_{M}_scope` object row-by-row (#1134).

    Each row becomes its own report key (`"<repo> (<ref>)"`) so a repo with
    several stories reports — and overrides — each story independently. Rows
    with no parsable repo are treated as parent-repo rows, matching the
    `/wave-scope` convention that a bare `main#N` lives in `noorinalabs-main`.

    Slot discovery is `is_role_slot_key` (#1180), NOT a hardcoded tuple. The old
    tuple was a THIRD place a role had to be listed, so an unrecognised slot key
    was not merely mis-classified here, it was skipped outright — measured on a
    3-slot row: "all 2 names resolved", exit 0. Now every key in
    `KNOWN_ROLE_SLOTS` is covered automatically, and an agentive-shaped key in
    neither frozenset is still handed to `validate()`, which flags it
    `slot_class="unclassified"` and fails the run.
    """
    report: dict[str, list[dict[str, object]]] = {}
    for row in _iter_tier_rows(scope):
        repo = repo_of_row(row) or "noorinalabs-main"
        slots: dict[str, object] = {}
        for role, value in row.items():
            if not is_role_slot_key(role):
                continue
            if isinstance(value, str) and value:
                slots[role] = value
        if OVERRIDE_KEY in row:
            slots[OVERRIDE_KEY] = row[OVERRIDE_KEY]
        if not slots:
            continue
        ref = row.get("ref") or row.get("id") or "?"
        row_report = validate({repo: slots}, org_dir, fetch_missing=fetch_missing, owner=owner)
        report[f"{repo} ({ref})"] = row_report[repo]
    return report


def _print_report_to_stderr(report: dict[str, list[dict[str, object]]]) -> int:
    """Pretty-print the report to stderr; return exit code.

    Three independent failure classes (#319 name resolution, #1134 repo
    membership, #1180 slot classification). Any one alone returns 1.
    """
    total = 0
    unresolved = 0
    unknown_name = 0
    org_persona_unreadable = 0
    cross_repo = 0
    overridden = 0
    unverified = 0
    unclassified = 0
    for findings in report.values():
        for f in findings:
            total += 1
            if not f["resolved"]:
                unresolved += 1
                if f.get("unresolved_reason") == _REASON_ORG_PERSONA_UNREADABLE:
                    org_persona_unreadable += 1
                else:
                    unknown_name += 1
            if f.get("slot_class") == "unclassified":
                unclassified += 1
            membership = f.get("membership")
            if membership == "cross-repo":
                cross_repo += 1
            elif membership == "overridden":
                overridden += 1
            elif membership == "unverified":
                unverified += 1

    if unresolved:
        print(
            f"validate_matrix_names: {unresolved}/{total} names UNRESOLVED "
            f"across {len(report)} entries.",
            file=sys.stderr,
        )
        for repo, findings in report.items():
            bad = [f for f in findings if not f["resolved"]]
            if not bad:
                continue
            print(f"\n  {repo}:", file=sys.stderr)
            for f in bad:
                if f.get("unresolved_reason") == _REASON_ORG_PERSONA_UNREADABLE:
                    # #1182: printing "suggestions: <the declared name itself>"
                    # here would read as a bug, so this row states the finding.
                    print(
                        f"    - {f['role']}: {f['declared']!r}  →  KNOWN org persona "
                        "(present in .claude/team/roster.json); this repo's roster "
                        "could not be read — not cloned?",
                        file=sys.stderr,
                    )
                    continue
                raw_suggestions = f.get("suggestions")
                suggestions = raw_suggestions if isinstance(raw_suggestions, list) else []
                sug_str = ", ".join(suggestions) if suggestions else "(no close matches)"
                print(
                    f"    - {f['role']}: {f['declared']!r}  →  suggestions: {sug_str}",
                    file=sys.stderr,
                )
        if unknown_name:
            print(
                "\n  Resolve each unknown name before /wave-kickoff fan-out.\n"
                "  Approved substitutions: record under"
                " wave_{M}_decisions.implementer_substitutions"
                " in cross-repo-status.json with rationale.",
                file=sys.stderr,
            )
        if org_persona_unreadable:
            print(
                f"\n  {org_persona_unreadable} of the above is a KNOWN org persona on a repo\n"
                "  whose roster could not be read. That is an ENVIRONMENT gap, not a bad\n"
                "  assignment — do NOT record an implementer_substitution for it, and note\n"
                "  that the same name DOES resolve in a review-class slot (the org-union\n"
                "  manifest widens review-class resolution only, #1162).\n"
                "\n  Pick one and re-run:\n"
                "    (a) --fetch-missing — resolve the target roster over the network, or\n"
                "    (b) clone the repo beside the parent.\n"
                "\n  It stays a failure (exit 1) until then, deliberately: a commit-capable\n"
                "  slot passes only on a name the TARGET repo can vouch for (#1134), and\n"
                "  membership cannot be decided from an unreadable roster.",
                file=sys.stderr,
            )

    if cross_repo:
        print(
            f"\nvalidate_matrix_names: {cross_repo}/{total} CROSS-REPO IMPLEMENTER "
            "assignment(s) with no recorded override (#1134).",
            file=sys.stderr,
        )
        for repo, findings in report.items():
            bad = [f for f in findings if f.get("membership") == "cross-repo"]
            if not bad:
                continue
            print(f"\n  {repo}:", file=sys.stderr)
            for f in bad:
                raw_roster = f.get("repo_roster")
                roster = raw_roster if isinstance(raw_roster, list) else []
                roster_str = ", ".join(roster) if roster else "(empty)"
                print(
                    f"    - {f['role']}: {f['declared']!r} is NOT on this repo's roster.\n"
                    f"      repo roster: {roster_str}",
                    file=sys.stderr,
                )
        print(
            "\n  The implementer is the only role that must COMMIT in the target repo,\n"
            "  where validate_commit_identity (Hook 5) resolves the author against that\n"
            "  repo's roster. Shipping this assignment means the commit is blocked at\n"
            "  wrap time and gets mechanically re-attributed — the #1134 failure.\n"
            "\n  Pick one:\n"
            "    (a) reassign to a member of the target repo's roster (preferred), or\n"
            "    (b) onboard the persona into <repo>/.claude/team/roster/ + roster.json, or\n"
            "    (c) record an explicit override on the scope row and re-run:\n"
            '          "roster_union_override": {"rationale": "<why this cross-repo\n'
            '            assignment is intended and how the commit will be authored>"}\n'
            "\n  A bare `true` is not accepted — the rationale is the audit trail.",
            file=sys.stderr,
        )

    if unclassified:
        print(
            f"\nvalidate_matrix_names: {unclassified}/{total} UNCLASSIFIED role slot(s) (#1180).",
            file=sys.stderr,
        )
        for repo, findings in report.items():
            bad = [f for f in findings if f.get("slot_class") == "unclassified"]
            if not bad:
                continue
            print(f"\n  {repo}:", file=sys.stderr)
            for f in bad:
                print(
                    f"    - {f['role']}: {f['declared']!r} — slot key is in neither "
                    "COMMIT_CAPABLE_ROLES nor REVIEW_CLASS_ROLES.",
                    file=sys.stderr,
                )
        print(
            "\n  An unclassified slot is validated on the STRICT path (narrow #319\n"
            "  resolution + the #1134 membership check) — the safe default, since the\n"
            "  loosenings (org-union manifest, membership exemption) are justified only\n"
            "  for a slot that provably never commits.\n"
            "\n  Classify the key in .claude/skills/wave-scope/validate_matrix_names.py:\n"
            "    COMMIT_CAPABLE_ROLES — the slot must COMMIT in the target repo\n"
            "    REVIEW_CLASS_ROLES   — review-only; never commits (manifest widens it,\n"
            "                           #1134 membership does not apply)\n"
            "    NON_ROLE_ROW_KEYS    — the key is row metadata, not a person slot",
            file=sys.stderr,
        )

    if unresolved or cross_repo or unclassified:
        return 1

    detail = []
    if overridden:
        detail.append(f"{overridden} cross-repo implementer(s) with recorded override")
    if unverified:
        detail.append(f"{unverified} implementer(s) unverified (repo roster unreadable)")
    suffix = f" [{'; '.join(detail)}]" if detail else ""
    print(
        f"validate_matrix_names: all {total} names resolved across {len(report)} entries.{suffix}",
        file=sys.stderr,
    )
    for repo, findings in report.items():
        for f in findings:
            if f.get("membership") == "overridden":
                print(
                    f"  OVERRIDE {repo} {f['role']}={f['declared']!r}: "
                    f"{f.get('override_rationale')}",
                    file=sys.stderr,
                )
            elif f.get("membership") == "unverified":
                print(
                    f"  UNVERIFIED {repo} {f['role']}={f['declared']!r}: "
                    "target repo roster unreadable (not cloned?) — membership not checked. "
                    "Re-run with --fetch-missing to resolve over the network.",
                    file=sys.stderr,
                )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate wave-scope implementer/reviewer names against per-repo rosters."
    )
    parser.add_argument(
        "matrix",
        nargs="?",
        help="path to a matrix JSON file ({repo: {role: name}}). Omit when using --scope.",
    )
    parser.add_argument(
        "--scope",
        metavar="STATUS_JSON",
        help="path to cross-repo-status.json; validates wave_{M}_scope.tier_*[] rows (#1134)",
    )
    parser.add_argument(
        "--wave",
        type=int,
        help="wave id {M} to read from --scope (required with --scope)",
    )
    parser.add_argument(
        "--fetch-missing",
        action="store_true",
        help=(
            "resolve a not-cloned child repo's roster over the network via "
            "roster_union_sync.fetch_child_roster instead of reporting it unverified"
        ),
    )
    parser.add_argument(
        "--owner",
        default="noorinalabs",
        help="GitHub org/owner used by --fetch-missing (default: noorinalabs)",
    )
    return parser


def main(argv: list[str]) -> int:
    args = _build_parser().parse_args(argv[1:])
    if bool(args.scope) == bool(args.matrix):
        print("ERROR: pass exactly one of <matrix-json-path> or --scope", file=sys.stderr)
        return 2
    org_dir = _find_org_dir()

    if args.scope:
        if args.wave is None:
            print("ERROR: --scope requires --wave {M}", file=sys.stderr)
            return 2
        path = Path(args.scope)
        try:
            status = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            print(f"ERROR reading {path}: {exc}", file=sys.stderr)
            return 2
        if not isinstance(status, dict):
            print("ERROR: --scope file must contain a JSON object", file=sys.stderr)
            return 2
        key = f"wave_{args.wave}_scope"
        scope = status.get(key)
        if not isinstance(scope, dict):
            print(f"ERROR: {path} has no object at key {key!r}", file=sys.stderr)
            return 2
        report = validate_scope(scope, org_dir, fetch_missing=args.fetch_missing, owner=args.owner)
        if not report:
            print(
                f"validate_matrix_names: {key} has no tier_* assignment rows to check.",
                file=sys.stderr,
            )
            return 0
        return _print_report_to_stderr(report)

    path = Path(args.matrix)
    try:
        matrix = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR reading {path}: {exc}", file=sys.stderr)
        return 2
    if not isinstance(matrix, dict):
        print("ERROR: top-level must be an object mapping repo → role-slots", file=sys.stderr)
        return 2
    report = validate(matrix, org_dir, fetch_missing=args.fetch_missing, owner=args.owner)
    return _print_report_to_stderr(report)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
