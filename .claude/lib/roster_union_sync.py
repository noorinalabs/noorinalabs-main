#!/usr/bin/env python3
"""Sync-drift gate: the committed parent roster must cover every child persona.

Why this exists (noorinalabs-main#634)
======================================
The commit-identity gate (`verify_commit_identity.py`) resolves "known roster
names" from the COMMITTED parent roster `.claude/team/roster.json`, which is
maintained as the org-wide UNION manifest (parent team + every child-repo
persona). That manifest is the only thing CI can see — the commit-identity
workflow does a single-repo checkout of `noorinalabs-main`, so sibling child
repos are NOT present (the original bug: a live filesystem scan of sibling
rosters was inert in CI, #634).

A hand-maintained union manifest rots: when a child repo onboards a persona,
nobody is forced to fold that name into the parent roster, and a future
child-persona-authored PR to `main` would be FALSE-BLOCKED by the
commit-identity gate. This module is the drift GATE that keeps the manifest
honest: it fetches each child repo's `roster.json` via the GitHub API and
asserts the committed parent roster is a SUPERSET of the child union, naming
any persona the parent is missing.

It is the roster analogue of `pre_commit_ci_sync.py` — a committed
cross-repo-derived artifact paired with a sync-drift gate that detects when the
artifact has fallen behind its sources.

Non-blocking by design (continue-on-error)
==========================================
Per the org pattern for CI checks over cross-repo-derived artifacts (a single
`noorinalabs-main` PR cannot deterministically reconcile a name that a SIBLING
repo just added, and the GitHub-API fetch is non-hermetic), the CI job that
runs this script is `continue-on-error: true`. A drift finding surfaces as a
red ADVISORY check naming the missing personas to fold into the parent roster;
it does not hard-block the PR. See charter `org_wide_artifact_gate_non_blocking`
(deploy#363/PR396) and `cross_repo_ghcr_registry_auth_proof`.

Fetch is fail-open per child repo: a child with no `roster.json` (e.g. a repo
that keeps only a `roster/` directory of per-member files), a private repo the
CI token cannot read, or a transient API error contributes no names and is
reported as SKIPPED — never a drift failure on its own. Drift is only ever
asserted on names we positively observed in a child roster.

The reverse direction: manifest orphans (#1181)
================================================
The gate above answers "is the parent roster MISSING anyone a child vouches
for?" — one-directional. #1181 measured the org's actual state and found the
other direction rotting silently: `roster.json` (78 entries) carries 18 names
backed by NO card anywhere in the org (union of every repo's roster cards:
60), and nothing ever prunes an entry once its card is deleted — an offboarded
persona's manifest row outlives the persona indefinitely (#1181's "liveness"
framing). Compounding it, #1178 (#1162) made the manifest a resolution
authority for review-class scope slots, so an unbacked entry is not merely
stale bookkeeping — it can resolve as a live reviewer.

`compute_manifest_orphans` is the reverse assertion: manifest ⊆ (this repo's
own roster cards) ∪ (every child's own roster CARD directory) ∪ (every
successfully-fetched child `roster.json`). #1183 independently measured the
same 18 names checking against child `roster.json`s directly instead of child
cards and reported `card-only == 0` (no persona has a card but no entry in
that child's own roster.json) — but that measurement itself drifted: a live
re-check while building this gate found `noorinalabs-isnad-graph/roster/
data_scientist_mei.md` (Mei-Lin Chang) absent from that SAME repo's own
`roster.json`, and `noorinalabs-deploy` has NO `roster.json` at all (its
`sre_engineer_aisha.md` persona is invisible to every roster.json-only check).
Trusting `card-only == 0` as a standing invariant would have shipped an
orphan check that immediately false-positives on two real, carded people, so
`fetch_child_card_names` fetches every child's card directory directly (one
`gh api` directory listing + one fetch per `.md` file) rather than relying on
that assumption staying true. See `DEFAULT_CARD_REPOS` for why the repo list
here is NOT the same as `DEFAULT_CHILD_REPOS`.

Two of the 18 are not a reconciliation question at all — `Annunaki` (the
error-monitor's own commit identity) and `Steven French` (the bare
`parametrization@gmail.com` principal, no `+alias`) are DEFINITIONALLY not
personas, matched by `_PERSONA_ALIAS_RE` the same way
`.claude/hooks/validate_pr_review.py` and
`.claude/skills/wave-scope/validate_matrix_names.py` already exclude them from
review-class resolution (#1179/#1181). Those two are reported separately, as
information, not as something to prune or onboard: pruning `Annunaki` would
break its own commit identity (the annunaki-attack skill commits AS
`Annunaki`), and `Steven French` is the owner's bare-principal mapping
`verify_commit_identity.py` special-cases on purpose. The remaining
persona-shaped orphans ARE an open reconciliation question (prune the row, or
onboard the persona with a real card) — but their disposition is explicitly
OUT of #1181's scope (still undecided), so this check reports them loudly
without gating on them; see "Exit codes" below for why.

An INCOMPLETE fetch (any roster.json OR card-directory SKIPPED) makes the
orphan report unreliable in the unsafe direction — a name backed only by
something we failed to read would misreport as an orphan — so the orphan
check does not run at all in that case, rather than risk a false "prune
this" instruction. The card fetch pass only runs once the roster.json pass
is already clean (no point fetching cards for a run that is already
disqualified).

The orphan check NEVER moves the exit code (owner correction, PR #1240 review)
=================================================================================
The forward direction (#634) above predates this reverse check and keeps its
established `continue-on-error` contract: the WORKFLOW run stays green even
when it exits 1, because a single PR cannot deterministically reconcile a
name a sibling repo just added. That contract does NOT extend cleanly to a
non-zero exit from a check whose findings are individually out of THIS PR's
scope to fix: `continue-on-error: true` only protects the workflow RUN's own
conclusion — it does not change what the JOB itself reports into the PR's
`statusCheckRollup`, which is exactly the surface `pr_ci_state.py` /
`validate_pr_ci_status.py` (the org's actual merge-readiness oracle) reads.
Measured: the reverse check returning exit 1 for the (already-known,
disposition-still-open) 16 unreconciled names turned this job FAILING on
every PR in the repo, not just this one — a permanently-red check that no
amount of continue-on-error hides from the tooling that actually gates merges,
which is precisely the state the org's "a red check is a stop, not a speed
bump" rule exists to prevent (charter, owner directive). So the orphan branch
below reports loudly (stderr, unabbreviated) but deliberately never sets
`exit_code` — only a genuine forward-direction violation (#634: a child
persona entirely missing from the parent) can fail this job. A future
disposition of the 16 (§ above) could reasonably promote them to blocking;
that is a separate, explicit decision, not a side effect of this check
existing.

Observability: job summary + stream ordering (#1254)
======================================================================
The orphan report above is advisory in EXIT STATUS (previous section), but
that left it advisory in VISIBILITY too: its only channel was text in the
log of a job that is ALWAYS green (continue-on-error, forward section
above), and a fetch failure (any roster.json or card-directory SKIP)
suppresses the whole orphan check — which, at every surface except the log
text, was indistinguishable from a clean pass. Two fixes:

1. Every line of the orphan-check verdict is ALSO written, Markdown-
   structured, to `$GITHUB_STEP_SUMMARY` (a file GitHub Actions provides to
   every step automatically — no workflow YAML change needed), so it renders
   on the workflow run's Summary page without opening any job's log, green
   or not. The verdict is always exactly one of three explicit, disjoint
   states — `DID NOT RUN`, `CLEAN`, or `ORPHANS FOUND (N)` — so "did not
   run" can never render like "clean" (the requirement recorded in #1254).
   `_write_step_summary` is a silent no-op when the env var is unset (local
   runs, unit tests, non-GHA CI) — never raises, never touches `exit_code`.
2. Every `print()` call in `main` now passes `flush=True`. Pre-fix, the
   per-repo `OK`/`SKIPPED` context lines went to stdout (block-buffered
   under a pipe — CI's actual I/O shape) while the DRIFT/MANIFEST-ORPHAN
   blocks went to stderr (unbuffered), so stdout's buffered lines were only
   written at process exit — AFTER every stderr line had already landed.
   Measured on a live run (#1254): the `MANIFEST ORPHAN` block printed
   ABOVE the `OK ...` context lines it must be read against. `flush=True`
   forces each print's underlying `write()` syscall to happen at the point
   of the call (program order) rather than being deferred by Python's stdio
   buffering, so the two streams interleave in the order the script
   actually emits them regardless of which fd a downstream consumer (e.g. a
   CI log that merges a step's stdout+stderr onto one pipe) merges them onto.

Input Language
==============
CLI:  roster_union_sync.py [--repo-root <dir>] [--repos a,b,c] [--owner <org>]

`--repos` overrides the default child-repo list (used by tests to avoid the
network). `--owner` defaults to `noorinalabs`.

Exit codes (CLI):
    0 — no forward drift (#634). The reverse orphan report (#1181) is ALWAYS
        advisory-only and never affects this — see "The orphan check NEVER
        moves the exit code" above. Printed output still names every
        unreconciled/non-persona orphan found; only the process exit stays 0.
    1 — forward drift ONLY: a child persona positively observed in a child
        `roster.json` is missing from the committed parent roster (#634)
    2 — usage / parent-roster load error
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from org_repos import CHILD_REPOS as _ALL_CHILD_REPOS

# The org's child repos that publish an aggregated `.claude/team/roster.json`.
# Filtered from org_repos.CHILD_REPOS (main#1118 / audit G6, the org repo-list
# SSOT) — `noorinalabs-deploy` is intentionally EXCLUDED: it keeps only a
# per-member `roster/` directory (no aggregated roster.json), so there is
# nothing to fetch — its personas are folded into the parent roster directly.
# A child not listed here is simply not cross-checked; add it back when it
# grows an aggregated roster.json.
DEFAULT_CHILD_REPOS: tuple[str, ...] = tuple(
    r for r in _ALL_CHILD_REPOS if r != "noorinalabs-deploy"
)

ROSTER_PATH_IN_REPO = ".claude/team/roster.json"

# A manifest entry is a PERSONA only if its address is a charter-conformant
# per-persona commit identity: `<principal>+<First>.<Last>@<domain>`. Same
# matcher as `.claude/hooks/validate_pr_review.py::_PERSONA_ALIAS_RE` (#1179)
# and `.claude/skills/wave-scope/validate_matrix_names.py::_PERSONA_ALIAS_RE`
# (#1181) — a third small duplicate rather than an import across the
# lib/hook/skill boundary, the established pattern for this regex (see either
# sibling's own docstring for why).
_PERSONA_ALIAS_RE = re.compile(r"^[^\s@+]+\+[^\s@+]+\.[^\s@+]+@[^\s@]+\.[^\s@]+$")

# Card name extractors — mirrors
# `.claude/skills/wave-scope/validate_matrix_names._load_roster_names` (#1010:
# both the OLD verbose `**Name:**` card field and the NEW slim H1 template are
# matched, so a mixed-format roster dir mid-transition resolves every card).
_CARD_NAME_RE = re.compile(r"\*\*Name:\*\*\s+(.+?)\s*$", re.MULTILINE)
_CARD_H1_RE = re.compile(r"^#\s+(.+?)\s+[—–-]\s+.+$", re.MULTILINE)


def parent_roster_map(repo_root: Path) -> dict[str, str]:
    """Raw `{name: email}` from the committed parent `roster.json`, or `{}` on failure."""
    roster = repo_root / ".claude" / "team" / "roster.json"
    try:
        data = json.loads(roster.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def parent_roster_names(repo_root: Path) -> set[str]:
    """Names in the committed parent roster — the union manifest under test."""
    return set(parent_roster_map(repo_root).keys())


def local_card_names(repo_root: Path) -> set[str]:
    """Parse member names from the LOCAL repo's own `.claude/team/roster/*.md` cards.

    This is the PARENT-repo-only half of the #1181 card union: this script
    runs in CI with just the `noorinalabs-main` checkout, so a child repo's
    card directory is never on disk here — only a NETWORK fetch can see it.
    `fetch_child_card_names` below is that fetch — it exists precisely
    because #1183's "card-only == 0" assumption (no persona has a card but no
    entry in that child's own `roster.json`) turned out to be false (see the
    module docstring § "The reverse direction: manifest orphans" for the live
    Mei-Lin Chang / Aisha Idrissi counterexamples). `compute_manifest_orphans`
    is called with `local_card_names(repo_root)` unioned with every fetched
    child's card set, never with this function's return value alone.
    """
    roster_dir = repo_root / ".claude" / "team" / "roster"
    names: set[str] = set()
    if not roster_dir.is_dir():
        return names
    for md_file in roster_dir.glob("*.md"):
        try:
            text = md_file.read_text()
        except OSError:
            continue
        for match in list(_CARD_NAME_RE.finditer(text)) + list(_CARD_H1_RE.finditer(text)):
            name = match.group(1).strip()
            name = re.sub(r"\s*\(.*?\)\s*$", "", name)
            if name:
                names.add(name)
    return names


def compute_manifest_orphans(
    parent_map: dict[str, str],
    card_names: set[str],
    child_rosters: dict[str, dict[str, str]],
) -> dict[str, list[str]]:
    """Reverse of `compute_drift` (#1181): manifest entries backed by NOTHING.

    Pure: given the already-loaded parent manifest, local card names, and the
    already-fetched child rosters, returns

        {"unreconciled": [...], "non_persona": [...]}

    sorted lexicographically. `"unreconciled"` is a persona-shaped manifest
    entry with no backing card or child-roster entry anywhere observed — an
    open disposition question (prune the row, or onboard the persona with a
    real card), and what the caller treats as actionable. `"non_persona"` is
    a manifest entry whose address does not match `_PERSONA_ALIAS_RE` at all
    (`Annunaki`, `Steven French`) — also unbacked, but definitionally not a
    reviewer regardless of a card, so it is reported for visibility only and
    never treated as something to reconcile.

    A name present in ANY backing source (card or ANY child roster) is not an
    orphan, matching #1183's broader measurement methodology (manifest vs.
    union of cards ∪ every child `roster.json`).
    """
    backing: set[str] = set(card_names)
    for roster in child_rosters.values():
        backing |= set(roster)
    orphans: dict[str, list[str]] = {"unreconciled": [], "non_persona": []}
    for name, address in parent_map.items():
        if not isinstance(name, str) or not name.strip():
            continue
        if name in backing:
            continue
        bucket = (
            "unreconciled"
            if isinstance(address, str) and _PERSONA_ALIAS_RE.match(address.strip())
            else "non_persona"
        )
        orphans[bucket].append(name)
    orphans["unreconciled"].sort()
    orphans["non_persona"].sort()
    return orphans


def fetch_child_roster(owner: str, repo: str) -> dict[str, str] | None:
    """Fetch a child repo's roster.json via `gh api`, or None if unavailable.

    Returns the parsed name→email mapping, or None when the file does not exist,
    the repo is unreadable by the CI token, or the response cannot be parsed
    (fail-open — the caller treats None as SKIPPED, never as drift).
    """
    try:
        proc = subprocess.run(
            [
                "gh",
                "api",
                f"repos/{owner}/{repo}/contents/{ROSTER_PATH_IN_REPO}",
                "--jq",
                ".content",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    raw = proc.stdout.strip()
    if not raw:
        return None
    try:
        decoded = base64.b64decode(raw).decode("utf-8")
        data = json.loads(decoded)
    except (ValueError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


CARD_PATH_IN_REPO = ".claude/team/roster"

# Repos whose CARD directories the #1181 reverse (orphan) check fetches —
# DEFAULT_CHILD_REPOS plus `noorinalabs-deploy`. Measured live (#1181): a
# repo's own `roster.json` aggregate can itself lag its own card directory
# (`noorinalabs-isnad-graph/roster/data_scientist_mei.md` names `Mei-Lin
# Chang`, absent from that SAME repo's `roster.json`), so fetching only
# `roster.json` false-positives the orphan check on a genuinely-carded
# persona. `noorinalabs-deploy` has NO `roster.json` at all (see
# DEFAULT_CHILD_REPOS comment above) so it is invisible to `fetch_child_roster`
# entirely, but it DOES keep a card directory (`sre_engineer_aisha.md` names
# `Aisha Idrissi`) — without fetching it, deploy's every persona would
# misreport as an orphan.
DEFAULT_CARD_REPOS: tuple[str, ...] = (*DEFAULT_CHILD_REPOS, "noorinalabs-deploy")


def fetch_child_card_names(owner: str, repo: str) -> set[str] | None:
    """Fetch a child repo's roster CARD names via `gh api`, or None if unavailable.

    Complements `fetch_child_roster` for the #1181 reverse check — see
    `DEFAULT_CARD_REPOS` above for why the aggregate `roster.json` is not a
    safe substitute for the card directory here, unlike for the forward drift
    check (which is deliberately asymmetric: a card genuinely NOT yet folded
    into `roster.json` is that repo's own bookkeeping lag, not evidence a
    persona from a THIRD repo is missing from the PARENT manifest).

    Two `gh api` calls per repo with content (a directory listing, then one
    fetch per `.md` file) — the parsed card-name union, or `None` when the
    directory is missing/unreadable or every per-file fetch failed. Fail-open,
    same posture as `fetch_child_roster`: the ORPHAN check (the only consumer)
    already treats ANY skip — roster.json or cards — as "cannot compute
    reliably" and does not run at all (see `main`), so a false SKIPPED here
    never manufactures a false orphan; it can only suppress the whole check.
    """
    try:
        listing = subprocess.run(
            ["gh", "api", f"repos/{owner}/{repo}/contents/{CARD_PATH_IN_REPO}", "--jq", ".[].name"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    filenames = [
        line.strip() for line in listing.stdout.splitlines() if line.strip().endswith(".md")
    ]
    if not filenames:
        return None
    names: set[str] = set()
    for filename in filenames:
        try:
            content = subprocess.run(
                [
                    "gh",
                    "api",
                    f"repos/{owner}/{repo}/contents/{CARD_PATH_IN_REPO}/{filename}",
                    "--jq",
                    ".content",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            text = base64.b64decode(content.stdout.strip()).decode("utf-8")
        except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
            continue
        for match in list(_CARD_NAME_RE.finditer(text)) + list(_CARD_H1_RE.finditer(text)):
            name = match.group(1).strip()
            name = re.sub(r"\s*\(.*?\)\s*$", "", name)
            if name:
                names.add(name)
    return names if names else None


def compute_drift(
    parent_names: set[str], child_rosters: dict[str, dict[str, str]]
) -> dict[str, list[str]]:
    """Return {missing_name: [child repos that have it]} for names absent from parent.

    Pure: the network/IO lives in fetch_child_roster, so this is fully testable
    with injected rosters. A name present in several child repos lists them all.
    """
    missing: dict[str, list[str]] = {}
    for repo, roster in child_rosters.items():
        for name in roster:
            if name not in parent_names:
                missing.setdefault(name, []).append(repo)
    return {name: sorted(repos) for name, repos in sorted(missing.items())}


def _write_step_summary(lines: list[str]) -> None:
    """Append the manifest-orphan report to the GitHub Actions job summary (#1254).

    `GITHUB_STEP_SUMMARY` is a file path GitHub Actions sets for every step
    automatically (no workflow YAML change needed) — content appended to it
    renders on the workflow run's Summary page, visible without opening any
    job's log, green or not. Best-effort / advisory-safe: if the env var is
    unset (local runs, unit tests, non-GHA CI) or the file can't be opened,
    this is a silent no-op — it never raises and never touches `exit_code`.
    Appends (never truncates), matching GHA's own convention of accumulating
    one summary file across every step in a job.
    """
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    try:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
            fh.write("\n")
    except OSError:
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", help="repo root hosting the parent roster.json")
    parser.add_argument(
        "--owner", default="noorinalabs", help="GitHub org/owner of the child repos"
    )
    parser.add_argument(
        "--repos",
        help="comma-separated child repo list (default: the org's child repos)",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).expanduser().resolve()
    parent_map = parent_roster_map(repo_root)
    parent_names = set(parent_map.keys())
    if not parent_names:
        print(
            f"ERROR: no parent roster names loaded from {repo_root}/{ROSTER_PATH_IN_REPO}.",
            file=sys.stderr,
            flush=True,
        )
        return 2

    repos = (
        [r.strip() for r in args.repos.split(",") if r.strip()]
        if args.repos
        else list(DEFAULT_CHILD_REPOS)
    )

    child_rosters: dict[str, dict[str, str]] = {}
    skipped: list[str] = []
    for repo in repos:
        roster = fetch_child_roster(args.owner, repo)
        if roster is None:
            skipped.append(repo)
            print(f"SKIPPED {repo}: no readable {ROSTER_PATH_IN_REPO} (fail-open).", flush=True)
        else:
            child_rosters[repo] = roster
            print(f"OK      {repo}: {len(roster)} persona(s).", flush=True)

    exit_code = 0

    # Forward direction (#634): parent roster ⊇ every observed child persona.
    drift = compute_drift(parent_names, child_rosters)
    if drift:
        print(
            "\nDRIFT: the committed parent roster .claude/team/roster.json is MISSING "
            "child-repo persona(s) below. Fold each into the parent roster so the "
            "commit-identity gate (verify_commit_identity.py) recognizes them on a "
            "cross-repo main PR (#634):",
            file=sys.stderr,
            flush=True,
        )
        for name, owners in drift.items():
            print(f'  - "{name}"  (canonical in: {", ".join(owners)})', file=sys.stderr, flush=True)
        exit_code = 1
    else:
        observed = sum(len(r) for r in child_rosters.values())
        if not child_rosters:
            print(
                f"\nNo child roster could be read ({len(skipped)} skipped); "
                "nothing to cross-check for drift. Passing (advisory).",
                flush=True,
            )
        else:
            print(
                f"\nParent roster covers all {observed} observed child persona(s) "
                f"across {len(child_rosters)} repo(s). No drift.",
                flush=True,
            )

    # Reverse direction (#1181): manifest ⊆ (this repo's cards) ∪ (every
    # child's own card directory) ∪ (every successfully-fetched child
    # roster.json). Skipped entirely when any roster.json OR card fetch
    # failed — an orphan report over partial data could misreport a name
    # backed only by a repo/directory we failed to fetch (see module
    # docstring). The card fetch only runs at all once the roster.json pass
    # is already clean, since a skip there already disqualifies the check.
    card_skipped: list[str] = []
    child_cards: dict[str, set[str]] = {}
    if not skipped:
        card_repos = list(dict.fromkeys([*repos, *DEFAULT_CARD_REPOS[len(DEFAULT_CHILD_REPOS) :]]))
        for repo in card_repos:
            names = fetch_child_card_names(args.owner, repo)
            if names is None:
                card_skipped.append(repo)
                print(
                    f"SKIPPED {repo}: no readable {CARD_PATH_IN_REPO}/*.md (fail-open).",
                    flush=True,
                )
            else:
                child_cards[repo] = names
                print(f"OK      {repo}: {len(names)} card(s).", flush=True)

    # #1254: the job-summary rendering of the orphan-check verdict below is
    # ALWAYS exactly one of three disjoint, explicitly-labelled states — a
    # SKIPPED (did-not-run) verdict must never share text with a CLEAN
    # (zero-orphans) one, so a summary reader can never mistake "this check
    # made no claim" for "this check looked and found nothing."
    summary_lines = ["### Manifest-orphan check (#1181)", ""]

    if skipped or card_skipped:
        unreadable = len(skipped) + len(card_skipped)
        skip_msg = (
            f"Manifest-orphan check (#1181) SKIPPED: {unreadable} repo/directory fetch(es) "
            "unreadable — an orphan report over partial data could wrongly flag a name backed "
            "only by something we failed to fetch."
        )
        print(f"\n{skip_msg}", flush=True)
        summary_lines.extend(
            [
                f"**Status: DID NOT RUN** — {unreadable} repo/directory fetch(es) unreadable.",
                "",
                "_This is NOT the same as a clean pass — the check did not execute, so it "
                "made no claim about orphans either way._",
            ]
        )
    else:
        card_names = local_card_names(repo_root)
        for names in child_cards.values():
            card_names |= names
        orphans = compute_manifest_orphans(parent_map, card_names, child_rosters)
        if orphans["non_persona"]:
            non_persona_header = (
                "Manifest carries non-persona entrie(s) (#1181) — informational only, never "
                "a reconciliation target (pruning would break their own use, e.g. the "
                "annunaki-attack skill's own commit identity):"
            )
            print(f"\n{non_persona_header}", flush=True)
            summary_lines.append(
                f"**Non-persona entries** (informational only): {non_persona_header}"
            )
            for name in orphans["non_persona"]:
                print(f'  - "{name}"', flush=True)
                summary_lines.append(f'- "{name}"')
            summary_lines.append("")
        if orphans["unreconciled"]:
            # Advisory ONLY (owner correction, PR #1240 review): this must NOT
            # move exit_code. continue-on-error at the WORKFLOW level does not
            # make the JOB's conclusion advisory — `pr_ci_state.py` /
            # `validate_pr_ci_status.py` (the org's actual merge-readiness
            # oracle) read the per-check rollup, not the run conclusion, so a
            # non-zero exit here would mark every future PR in this repo
            # "failing" until the (explicitly out-of-scope-for-#1181)
            # disposition of these names is resolved — exactly the
            # permanently-red state the "red is a stop" rule exists to
            # prevent. Reported loudly (stderr) precisely so it stays visible
            # without blocking. Only the forward direction (#634) above,
            # which predates this reverse check and has its own established
            # contract, may set exit_code — see module docstring.
            print(
                "\nMANIFEST ORPHAN (#1181, advisory — does not fail this job): "
                "persona-shaped parent-roster entry with NO backing card or child "
                "roster.json observed anywhere in the org. Pick one:\n"
                "  (a) onboard the persona — add a real roster card in the repo it belongs to, or\n"
                "  (b) the persona is retired — remove the row from .claude/team/roster.json.",
                file=sys.stderr,
                flush=True,
            )
            summary_lines.extend(
                [
                    f"**Status: ORPHANS FOUND** ({len(orphans['unreconciled'])} unreconciled) "
                    "— advisory, does not fail this job.",
                    "",
                    "Pick one: (a) onboard the persona with a real roster card, or (b) remove "
                    "the row from `.claude/team/roster.json` if the persona is retired.",
                    "",
                ]
            )
            for name in orphans["unreconciled"]:
                print(f'  - "{name}"', file=sys.stderr, flush=True)
                summary_lines.append(f'- "{name}"')
        else:
            clean_msg = (
                "Manifest-orphan check (#1181): every persona-shaped manifest entry is backed "
                "by a card or a child roster.json. No unreconciled orphans."
            )
            print(f"\n{clean_msg}", flush=True)
            summary_lines.append(f"**Status: CLEAN** — {clean_msg}")

    _write_step_summary(summary_lines)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
