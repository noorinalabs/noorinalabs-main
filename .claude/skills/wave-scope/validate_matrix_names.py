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
Pre-existing since #319, but #1134 made § 12.5 mandatory over every canonical
`tier_*` row and added a hard `exit 1` at `/wave-kickoff` § 0b, turning a latent
gap into a STOP on a charter-permitted assignment.

The manifest is deliberately NOT unioned into the `implementer` resolution set.
Doing so would loosen check 2 in the `unverified` case: when the target repo's
roster is unreadable (not cloned — the CI case), membership fails OPEN, so a
third-child implementer that newly *resolved* would exit 0 where today it exits
1 as an unresolved name. Keeping the commit-capable resolution set narrow means
the only way that slot passes is a name the target repo can actually vouch for.

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
    0 — all names resolve, and every child-repo implementer is a repo member
        (or carries a recorded override)
    1 — one or more names don't resolve, OR a child-repo implementer is not on
        that repo's roster and has no recorded override
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

# Role slots that must be able to COMMIT in the target repo. Only these are
# subject to the #1134 repo-membership check; every other slot is review-class
# and keeps the parent-union resolution (#319 semantics).
COMMIT_CAPABLE_ROLES: frozenset[str] = frozenset({"implementer"})

# Repo keys that mean "the parent repo itself" — membership is vacuous there
# (the parent roster IS the repo roster), so #1134 never fires on them.
PARENT_REPO_KEYS: frozenset[str] = frozenset({"", "noorinalabs-main", "main"})


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
    """Parse names from the parent's org-union manifest `.claude/team/roster.json`.

    The manifest is a flat `{"<name>": "<email>"}` object covering every persona
    across the org (78 at time of writing) — a strict superset of the parent's
    own card directory, and the only place a persona from a repo that is not the
    target repo can be recognised without cloning that repo.

    Fails OPEN (empty set) when the file is missing or malformed: the manifest
    only ever WIDENS the review-class resolution set, so an unreadable manifest
    degrades to exactly the pre-#1162 behaviour rather than blocking a run.
    """
    path = org_dir / ".claude" / "team" / "roster.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    if not isinstance(data, dict):
        return set()
    return {name.strip() for name in data if isinstance(name, str) and name.strip()}


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
        override = _override_rationale(slots.get("roster_union_override"))
        repo_findings: list[dict[str, object]] = []
        for role, raw in slots.items():
            if role == "roster_union_override":
                continue
            if not raw or not isinstance(raw, str):
                continue
            declared = raw
            declared_clean = re.sub(r"\s*\(.*?\)\s*$", "", declared).strip()
            candidates = combined if role in COMMIT_CAPABLE_ROLES else review_combined
            resolved = any(declared_clean.lower() == known.lower() for known in candidates)
            entry: dict[str, object] = {
                "role": role,
                "declared": declared,
                "resolved": resolved,
                "membership": "n/a",
            }
            if not resolved:
                entry["suggestions"] = _suggest(declared_clean, candidates)
                repo_findings.append(entry)
                continue
            # #1134: commit-capable slots on a child repo must be repo members.
            if role in COMMIT_CAPABLE_ROLES and not is_parent_repo:
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
    """
    report: dict[str, list[dict[str, object]]] = {}
    for row in _iter_tier_rows(scope):
        repo = repo_of_row(row) or "noorinalabs-main"
        slots: dict[str, object] = {}
        for role in ("implementer", "reviewer", "reviewer_2", "merge_gate_reviewer"):
            value = row.get(role)
            if isinstance(value, str) and value:
                slots[role] = value
        if "roster_union_override" in row:
            slots["roster_union_override"] = row["roster_union_override"]
        if not slots:
            continue
        ref = row.get("ref") or row.get("id") or "?"
        row_report = validate({repo: slots}, org_dir, fetch_missing=fetch_missing, owner=owner)
        report[f"{repo} ({ref})"] = row_report[repo]
    return report


def _print_report_to_stderr(report: dict[str, list[dict[str, object]]]) -> int:
    """Pretty-print the report to stderr; return exit code.

    Two independent failure classes (#319 name resolution, #1134 repo
    membership). Either one alone returns 1.
    """
    total = 0
    unresolved = 0
    cross_repo = 0
    overridden = 0
    unverified = 0
    for findings in report.values():
        for f in findings:
            total += 1
            if not f["resolved"]:
                unresolved += 1
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
                raw_suggestions = f.get("suggestions")
                suggestions = raw_suggestions if isinstance(raw_suggestions, list) else []
                sug_str = ", ".join(suggestions) if suggestions else "(no close matches)"
                print(
                    f"    - {f['role']}: {f['declared']!r}  →  suggestions: {sug_str}",
                    file=sys.stderr,
                )
        print(
            "\n  Resolve each unknown name before /wave-kickoff fan-out.\n"
            "  Approved substitutions: record under wave_{M}_decisions.implementer_substitutions"
            " in cross-repo-status.json with rationale.",
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

    if unresolved or cross_repo:
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
