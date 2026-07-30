#!/usr/bin/env python3
"""Deterministic wave repo-iteration + counter helper (main#688).

zsh — this org's shell (memory ``feedback_zsh_shell_environment``) — does NOT
word-split an unquoted parameter expansion ``$var`` the way bash/sh do. The
hand-rolled ``for R in $WAVE_REPOS_IN_SCOPE`` loops in /wave-wrapup,
/wave-kickoff and /wave-scope therefore collapsed the whole newline-joined
repo list into a SINGLE iteration: the string
``"noorinalabs-isnad-graph noorinalabs-user-service ..."`` was passed to ``gh``
as one repo, which 404'd ("Could not resolve repository") → merged-PR count 0
→ division-by-zero in the top-concentration math. It bit a single P5W4
``/wave-wrapup`` three times — a soft memory had not stopped the recurrence, so
the iteration + counter math is moved here, into deterministic code.

Design contract:
  * EVERY ``gh`` invocation goes through :func:`_run_gh`, which calls
    ``subprocess.run(["gh", *args], ...)`` with an explicit ARG LIST — never a
    shell string, never ``shell=True``. There is no word-splitting anywhere,
    under any shell.
  * ``repos``      — emit ``wave_{M}_repos_in_scope`` one-per-line so a bash
                     caller can iterate safely (``while IFS= read -r R``).
  * ``merged-prs`` — the wave's merged-PR set as JSON, cross-window-filtered by
                     ``wave_{M}_kicked_off_at`` (the #423 partition fix).
  * ``counters``   — ``final_pr_count`` / ``changes_requested_cycles`` /
                     ``top_concentration_pct``; ``--write`` upserts the three
                     canonical top-level keys that /wave-retro Step 2.5 reads
                     (via :mod:`upsert_status_keys`, preserving the
                     compact-inline file shape); ``--expect N`` loud-fails on a
                     count mismatch.

CLI:
  wave_status.py digest              [--status PATH]  # current-wave/phase slice (#987)
  wave_status.py repos       <P> <M> [--status PATH]
  wave_status.py merged-prs  <P> <M> [--status PATH]
  wave_status.py counters    <P> <M> [--write] [--expect N] [--status PATH]
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from collections import Counter
from pathlib import Path

# wave_merge_model lives alongside this file in .claude/lib/. When this module
# is run as a script its own directory is on sys.path[0]; the tests add the
# lib dir explicitly (mirrors the trust_signals.py -> wave_status.py import).
sys.path.insert(0, str(Path(__file__).resolve().parent))
import wave_merge_model  # noqa: E402

# upsert_status_keys.py lives alongside this file in .claude/lib/. When this
# module is run as a script its own directory is on sys.path[0]; the tests add
# the lib dir explicitly. Import lazily inside _write_counters so a missing
# helper only matters for the --write path.

# Repo root = two parents above .claude/lib/ (lib -> .claude -> root). Resolved
# from this file so the default is correct from any cwd or worktree, with no
# `git rev-parse` subprocess (which would re-introduce a shell dependency).
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_STATUS = _REPO_ROOT / "cross-repo-status.json"

# A ChangesRequested verdict comment on a PR's issue-comments timeline. Mirrors
# the regex the pre-#688 bash Step 10.5 block used. The DOUBLED backslash is
# load-bearing: this string is embedded into a jq filter, and jq's own string
# parser collapses ``\\s`` to the regex ``\s`` — a single backslash would be an
# "invalid escape sequence" jq error (caught live, not by the mocked tests).
_CHANGES_REQUESTED_RE = "RequestOrReplied:\\\\s*ChangesRequested"


def _run_gh(args: list[str]) -> str:
    """Run ``gh <args>`` with an explicit arg list and return stdout.

    Never a shell string and never ``shell=True`` — this is the whole point of
    the helper (main#688): no shell means no word-splitting, so a multi-word
    repo list can never collapse into one bogus ``--repo`` value.
    """
    proc = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout


def _load_status(status_path: Path) -> dict:
    return json.loads(status_path.read_text())


def read_repos(wave: str, status_path: Path) -> list[str]:
    """Return ``wave_{M}_repos_in_scope`` as a list of repo names.

    Raises KeyError if the key is absent — by the time any of these subcommands
    runs the wave's scope must already be recorded, so a missing key is an
    operator error to surface rather than silently treat as the empty set.
    """
    data = _load_status(status_path)
    key = f"wave_{wave}_repos_in_scope"
    if key not in data:
        raise KeyError(key)
    repos = data[key]
    if not isinstance(repos, list):
        raise TypeError(f"{key} is not a list: {repos!r}")
    return [str(r) for r in repos]


def _kickoff_ts(wave: str, status_path: Path) -> str | None:
    """The cross-window filter boundary — ``wave_{M}_kicked_off_at`` or None.

    Absent for legacy waves (W1-W3 pre-/wave-start); in that case no filter is
    applied and the caller relies on the base-branch scoping alone (#423).
    """
    data = _load_status(status_path)
    val = data.get(f"wave_{wave}_kicked_off_at")
    return str(val) if val else None


def _commit_author_name(repo: str, sha: str) -> str:
    """The head commit's author name for *sha* — the identity the
    top-concentration metric is computed over.

    *sha* is always a PR's ``headRefOid`` (the PR branch tip, the
    implementer's own last commit) — deliberately NEVER the merge commit
    landed on ``main``. That distinction matters here specifically: this
    org merges with ``--merge`` (never ``--squash``), so a merge commit's
    author is the orchestrator/CLI identity that ran the merge
    (``parametrization``) for every PR, which would collapse
    per-engineer concentration to a single name regardless of who actually
    authored the work (the #1177 persona-loss failure mode). ``headRefOid``
    preserves the real implementer identity.
    """
    return _run_gh(
        [
            "api",
            f"repos/noorinalabs/{repo}/commits/{sha}",
            "--jq",
            ".commit.author.name",
        ]
    ).strip()


def _canonical_issue_numbers_by_repo(wave: str, status_path: Path) -> dict[str, set[int]]:
    """Canonical scope-issue numbers per repo, from ``wave_{M}_scope``.

    ``wave_{M}_scope`` (the record ``/wave-scope`` maintains) holds an
    arbitrary, wave-specific set of ``tier_*`` arrays — tier names are NOT
    fixed across waves (main#1131: wave-29 introduced ``tier_4_...`` that did
    not exist in earlier waves), so every key is iterated generically via
    ``key.startswith("tier_")``, exactly as
    ``post_wave_kickoff_comment.py:find_assignment_row`` does. Each dict row's
    ``id`` field is the fully-qualified ``noorinalabs-<repo>#<number>`` shape;
    rows without a parseable ``id`` (legacy plain-string tier entries) are
    skipped — they carry no repo/number to key on.

    This is the base+timestamp-is-not-sufficient fix from the wave-28 retro:
    a merged-to-main PR in the timestamp window is only in scope if it closes
    an issue that is actually recorded as part of the wave's scope (the
    wave-28 false positive was ``us#213`` — in-window, but never a scope row).
    """
    data = _load_status(status_path)
    scope = data.get(f"wave_{wave}_scope")
    if not isinstance(scope, dict):
        raise KeyError(f"wave_{wave}_scope")

    by_repo: dict[str, set[int]] = {}
    for key, value in scope.items():
        if not key.startswith("tier_") or not isinstance(value, list):
            continue
        for row in value:
            if not isinstance(row, dict):
                continue
            row_id = row.get("id")
            if not isinstance(row_id, str) or "#" not in row_id:
                continue
            repo, _, number = row_id.rpartition("#")
            if not repo or not number.isdigit():
                continue
            by_repo.setdefault(repo, set()).add(int(number))
    return by_repo


def _pr_closing_issue_numbers(repo: str, number: int) -> set[tuple[str, int]]:
    """Repo-qualified issue numbers GitHub recognises *number* as closing.

    Returns ``{(repo_name, issue_number), ...}`` — deliberately NOT bare
    issue numbers (main#1189). A closing reference is not necessarily in
    *repo*: child-repo PRs routinely close a parent meta-issue recorded
    under a different repo (e.g. ``noorinalabs-main``), and two repos can
    independently have an issue #N. Comparing bare numbers against a single
    repo's canonical scope set either silently drops the cross-repo case
    (under-count) or, on a same-number collision across repos, matches the
    wrong issue (mis-attribution) — confirmed live via `gh api graphql`
    against PR #1173. ``repository{name}`` is available on the same GraphQL
    node at no extra cost.

    The REST-backed ``gh pr list --json`` surface (this org pins gh 2.45.0)
    has no ``closingIssuesReferences`` field, so this goes through
    ``gh api graphql`` instead. A row-number match is not assumed: main#1172
    was delivered by PR #1173 (a different number), and #1167/#1168/#1170/
    #1171 were bundled into a single PR — the closing-reference set is the
    only reliable link between a scope row and the PR that actually delivered
    it under a direct-to-main wave.

    ``first:100`` (raised from the pre-#1189 ``first:25``) — the same
    silent-truncation family as :data:`_PR_LIST_LIMIT` below: a PR closing
    more issues than the page size would otherwise drop the excess with no
    signal. 100 is GitHub's GraphQL connection page-size ceiling for this
    field, so it is the maximum obtainable in a single page; a PR closing
    over 100 issues would need real pagination (``endCursor``/``hasNextPage``)
    — no real wave has approached that, so it is flagged here rather than
    silently left uncapped or unremarked.
    """
    query = (
        "query($owner:String!,$name:String!,$number:Int!){"
        "repository(owner:$owner,name:$name){"
        "pullRequest(number:$number){"
        "closingIssuesReferences(first:100){nodes{number repository{name}}}"
        "}}}"
    )
    raw = _run_gh(
        [
            "api",
            "graphql",
            "-f",
            f"query={query}",
            "-f",
            "owner=noorinalabs",
            "-f",
            f"name={repo}",
            "-F",
            f"number={number}",
            "--jq",
            "[.data.repository.pullRequest.closingIssuesReferences.nodes[]"
            " | {number, repo: .repository.name}]",
        ]
    )
    nodes = json.loads(raw or "[]")
    return {(str(n["repo"]), int(n["number"])) for n in nodes}


def _merged_prs_wave_branch(phase: str, wave: str, status_path: Path) -> list[dict]:
    """Build the wave's merged-PR set across every in-scope repo.

    For each repo: list merged PRs based on ``deployments/phase-<P>/wave-<M>``,
    drop any merged before ``wave_{M}_kicked_off_at`` (the #423 cross-window
    filter), and attach the head commit's author name (the identity the
    top-concentration metric is computed over).

    UNCHANGED behavior (main#1131) — this is the pre-existing wave-branch path,
    only renamed so :func:`merged_prs` can dispatch on the declared merge
    model; every line of logic below is identical to the pre-#1131 body.
    """
    repos = read_repos(wave, status_path)
    kickoff = _kickoff_ts(wave, status_path)
    base = f"deployments/phase-{phase}/wave-{wave}"

    out: list[dict] = []
    for repo in repos:
        listed = json.loads(
            _run_gh(
                [
                    "pr",
                    "list",
                    "--repo",
                    f"noorinalabs/{repo}",
                    "--state",
                    "merged",
                    "--base",
                    base,
                    "--json",
                    "number,headRefOid,mergedAt,author",
                ]
            )
        )
        for pr in listed:
            merged_at = pr.get("mergedAt") or ""
            if kickoff and merged_at < kickoff:
                continue
            sha = pr["headRefOid"]
            commit_author = _commit_author_name(repo, sha)
            out.append(
                {
                    "repo": repo,
                    "number": pr["number"],
                    "mergedAt": merged_at,
                    "headRefOid": sha,
                    "author": (pr.get("author") or {}).get("login"),
                    "commit_author_name": commit_author,
                }
            )
    return out


# `gh pr list` defaults to `--limit 30` (main#1131 M2). The wave-branch path
# was structurally immune to this cap -- `--base <wave-branch>` already bounds
# the query to the wave -- but `--base main` on a direct-to-main wave queries
# against FULL repo history, which a live check against this repo returned
# 251 merged-to-main PRs for (`--limit 500`). An unbounded `main` query with
# the gh default cap silently drops the OLDEST matches once the repo
# accumulates more than 30 merges-to-main since a wave's kickoff -- exactly
# the "exits 0, returns a plausible number" failure shape main#1131 exists to
# kill. 1000 is not a real pagination fix (a wave whose window somehow
# accrues >1000 merges-to-main would still truncate), but combined with the
# `--search merged:>=` server-side bound below it comfortably covers any
# realistic wave, and is cheap insurance regardless.
_PR_LIST_LIMIT = 1000


def _merged_prs_direct_to_main(
    wave: str, status_path: Path
) -> tuple[list[dict], set[tuple[str, int]]]:
    """Build the wave's merged-PR set for a ``direct-to-main`` wave (main#1131).

    No wave branch exists under this model, so ``--base <wave-branch>``
    (:func:`_merged_prs_wave_branch`'s filter) silently matches nothing. The
    fix is NOT simply switching the base to ``main`` — base+timestamp alone
    over-counts (wave-28 retro: ``us#213`` was in-window but out-of-scope).
    Instead: list merged-to-main PRs per in-scope repo, apply the existing
    ``wave_{M}_kicked_off_at`` cross-window filter as a pre-filter, then keep
    only the PRs whose GitHub-recognised closing-issue references intersect
    the wave's FULL canonical scope-issue set, across every repo
    (:func:`_canonical_issue_numbers_by_repo`) — not just the queried repo's
    own scope rows (main#1189: a closing reference is not necessarily in the
    same repo as the PR, e.g. a child-repo PR closing a parent meta-issue, and
    matching against only the queried repo's own numbers either drops that
    case or, on a same-number collision across repos, attributes it to the
    wrong issue). A repo with no canonical scope rows of its own is skipped
    entirely rather than querying every merged PR in that repo.

    The listing itself is bounded two ways (main#1131 M2 — `gh pr list`
    defaults to `--limit 30`, and `--base main` removes the wave-branch's
    natural scope, exposing that cap against full repo history): a
    server-side ``--search merged:>=<kickoff>`` qualifier so the query never
    reaches further back than the wave itself, and an explicit
    :data:`_PR_LIST_LIMIT` well above any realistic wave's merge volume. The
    ``merged_at < kickoff`` filter below is kept as defense-in-depth in case
    the search qualifier's date granularity and the recorded kickoff instant
    ever disagree at the second.

    Returns ``(merged_prs, claimed_pairs)`` — alongside the PR list, the set
    of canonical ``(repo, issue_number)`` scope pairs actually claimed by some
    merged PR's closing references. :func:`reconciliation_warning` (main#1190)
    needs this to report scope rows no merged PR claims, without re-running
    every ``gh api graphql`` closing-reference call a second time.
    """
    repos = read_repos(wave, status_path)
    kickoff = _kickoff_ts(wave, status_path)
    issue_numbers_by_repo = _canonical_issue_numbers_by_repo(wave, status_path)
    canonical_pairs: set[tuple[str, int]] = {
        (repo_name, n) for repo_name, nums in issue_numbers_by_repo.items() for n in nums
    }

    out: list[dict] = []
    claimed: set[tuple[str, int]] = set()
    for repo in repos:
        canonical_issues = issue_numbers_by_repo.get(repo)
        if not canonical_issues:
            continue
        args = [
            "pr",
            "list",
            "--repo",
            f"noorinalabs/{repo}",
            "--state",
            "merged",
            "--base",
            "main",
            "--limit",
            str(_PR_LIST_LIMIT),
            "--json",
            "number,headRefOid,mergedAt,author",
        ]
        if kickoff:
            args += ["--search", f"merged:>={kickoff}"]
        listed = json.loads(_run_gh(args))
        for pr in listed:
            merged_at = pr.get("mergedAt") or ""
            if kickoff and merged_at < kickoff:
                continue
            closes = _pr_closing_issue_numbers(repo, pr["number"])
            hit = closes & canonical_pairs
            if not hit:
                continue
            claimed |= hit
            sha = pr["headRefOid"]
            commit_author = _commit_author_name(repo, sha)
            out.append(
                {
                    "repo": repo,
                    "number": pr["number"],
                    "mergedAt": merged_at,
                    "headRefOid": sha,
                    "author": (pr.get("author") or {}).get("login"),
                    "commit_author_name": commit_author,
                }
            )
    return out, claimed


def _merged_prs_with_claims(
    phase: str, wave: str, status_path: Path
) -> tuple[list[dict], set[tuple[str, int]] | None]:
    """Dispatch on merge model, same as :func:`merged_prs`, but also surface
    the claimed-canonical-pairs side channel :func:`_merged_prs_direct_to_main`
    returns (``None`` under the wave-branch model, which has no
    closing-issue-reference dependency to reconcile against). Single source
    for both :func:`compute_counters` and the reconciliation warning so a CLI
    invocation does not re-run every ``gh`` call a second time.
    """
    model = wave_merge_model.read_merge_model(wave, status_path)
    if model == wave_merge_model.DIRECT_TO_MAIN:
        return _merged_prs_direct_to_main(wave, status_path)
    return _merged_prs_wave_branch(phase, wave, status_path), None


def merged_prs(phase: str, wave: str, status_path: Path) -> list[dict]:
    """Build the wave's merged-PR set across every in-scope repo.

    Dispatches on the declared ``wave_{M}_merge_model`` (main#1131):
    ``direct-to-main`` routes through the canonical-scope path
    (:func:`_merged_prs_direct_to_main`, no wave branch exists to filter on);
    ``wave-branch`` and an unrecorded/legacy model (``None``) both keep the
    pre-existing behavior unchanged (:func:`_merged_prs_wave_branch`).
    """
    prs, _claimed = _merged_prs_with_claims(phase, wave, status_path)
    return prs


def _canonical_pairs(wave: str, status_path: Path) -> set[tuple[str, int]]:
    """Flatten :func:`_canonical_issue_numbers_by_repo` into ``(repo, number)``
    pairs across every repo — the same shape :func:`_merged_prs_direct_to_main`
    matches closing references against."""
    issue_numbers_by_repo = _canonical_issue_numbers_by_repo(wave, status_path)
    return {(repo_name, n) for repo_name, nums in issue_numbers_by_repo.items() for n in nums}


def _reconciliation_warning_from_claims(
    wave: str, status_path: Path, claimed: set[tuple[str, int]] | None
) -> str | None:
    """Format the main#1190 reconciliation line from an already-computed
    ``claimed`` set (see :func:`_merged_prs_with_claims`) — a pure function of
    (canonical scope, claimed pairs), so it costs no extra ``gh`` calls beyond
    whatever already produced ``claimed``.

    Deliberately a WARNING, never an error: an open scope row is normal
    mid-wave. Returns ``None`` for a wave-branch wave (``claimed is None`` —
    that path's base+timestamp counting has no closing-reference dependency
    to reconcile against) or when every canonical row is claimed.
    """
    if claimed is None:
        return None
    canonical = _canonical_pairs(wave, status_path)
    if not canonical:
        return None
    unclaimed = sorted(canonical - claimed)
    if not unclaimed:
        return None
    rows = ", ".join(f"{repo_name.removeprefix('noorinalabs-')}#{n}" for repo_name, n in unclaimed)
    return f"scope rows with no matching merged PR: {rows} ({len(unclaimed)} of {len(canonical)})"


def reconciliation_warning(phase: str, wave: str, status_path: Path) -> str | None:
    """Public entry point for main#1190 — canonical scope rows no merged PR's
    closing references claimed, under the direct-to-main path.

    Runs its own single pass via :func:`_merged_prs_with_claims` (for callers,
    e.g. tests, that want the warning in isolation); ``_cmd_counters`` and
    ``_cmd_merged_prs`` instead reuse the pass they already ran, via
    :func:`_reconciliation_warning_from_claims`, so a CLI invocation never
    pays for the closing-reference lookups twice.
    """
    _prs, claimed = _merged_prs_with_claims(phase, wave, status_path)
    return _reconciliation_warning_from_claims(wave, status_path, claimed)


def _changes_requested_cycles(prs: list[dict]) -> int:
    """Sum ChangesRequested verdict comments across every PR's timeline."""
    total = 0
    for pr in prs:
        count = _run_gh(
            [
                "api",
                f"repos/noorinalabs/{pr['repo']}/issues/{pr['number']}/comments",
                "--jq",
                f'[.[] | select(.body | test("{_CHANGES_REQUESTED_RE}"))] | length',
            ]
        ).strip()
        total += int(count or 0)
    return total


def _top_concentration_pct(prs: list[dict]) -> int:
    """Top commit-author's PR-count as a half-up-rounded percentage of total.

    Returns 0 for an empty wave (no PRs) rather than dividing by zero — the
    exact crash main#688 set out to kill. Half-up rounding (``floor(x + 0.5)``)
    matches the pre-#688 bash ``printf "%d" x + 0.5`` so historical counter
    rows reproduce (e.g. 3/19 = 15.78 → 16).
    """
    total = len(prs)
    if total == 0:
        return 0
    counts = Counter(pr["commit_author_name"] for pr in prs)
    top = counts.most_common(1)[0][1]
    return math.floor(top * 100 / total + 0.5)


def _compute_counters_from_prs(prs: list[dict]) -> dict[str, int]:
    return {
        "final_pr_count": len(prs),
        "changes_requested_cycles": _changes_requested_cycles(prs),
        "top_concentration_pct": _top_concentration_pct(prs),
    }


def compute_counters(phase: str, wave: str, status_path: Path) -> dict[str, int]:
    """Compute the three canonical wave counters from the merged-PR set."""
    prs = merged_prs(phase, wave, status_path)
    return _compute_counters_from_prs(prs)


def _write_counters(wave: str, counters: dict[str, int], status_path: Path) -> int:
    """Upsert the three canonical top-level keys via upsert_status_keys.main.

    Reuses the shared helper so the compact-inline shape of
    cross-repo-status.json is preserved and the write is JSON-validated before
    AND after (main#332/#456). Values are plain integers → bare JSON literals.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from upsert_status_keys import main as upsert_main

    # upsert_status_keys.main treats argv[0] as the program name (argv[1] is the
    # status path), so prepend a placeholder element.
    return upsert_main(
        [
            "wave_status",
            str(status_path),
            f"wave_{wave}_final_pr_count={counters['final_pr_count']}",
            f"wave_{wave}_changes_requested_cycles={counters['changes_requested_cycles']}",
            f"wave_{wave}_top_concentration_pct={counters['top_concentration_pct']}",
        ]
    )


# Lifecycle pointer keys always surfaced in the session-start digest — the small
# fixed set /session-start Step 5 reports (active phase/wave, staleness, in-flight
# counts). Everything else in the digest is derived by wave/phase scoping below.
_DIGEST_POINTER_KEYS = (
    "current_phase",
    "current_wave",
    "next_wave",
    "last_completed_wave",
    "global_wave_seq",
    "wave_active",
    "last_updated",
    "open_prs_total",
)


def _wave_ordinal(value: object) -> str | None:
    """Extract the numeric wave ordinal from a ``wave-<N>`` pointer.

    Returns the ordinal as a string (used to build the ``wave_<N>_`` key prefix)
    or None when the pointer is absent/malformed — the digest degrades to
    pointers+phase+blockers rather than raising, matching the non-fatal stance of
    the session-start Step blocks that call it.
    """
    if not isinstance(value, str):
        return None
    tail = value.rsplit("-", 1)[-1]
    return tail if tail.isdigit() else None


def build_digest(status_path: Path) -> dict:
    """Project cross-repo-status.json down to the current-wave/phase slice.

    The full file is a flat dict of ~500 keys accreted across every wave (>200KB,
    ~53K tokens); ``cat``-ing it whole into context each session was the single
    biggest guaranteed per-session token cost (#987). Step 5 only needs the
    lifecycle pointers plus the keys scoped to the *current* wave, the *next*
    wave, and the *current* phase, plus any open owner-decision blockers. This
    returns exactly that as an ordered, valid-JSON-serialisable dict — no
    historical wave/phase keys. Nothing is written; it is a pure read.
    """
    data = _load_status(status_path)

    digest: dict = {}
    for key in _DIGEST_POINTER_KEYS:
        if key in data:
            digest[key] = data[key]

    # Wave-scoped keys for the current + next wave. The trailing underscore in the
    # prefix is load-bearing: ``wave_2_`` must not match ``wave_25_`` keys.
    wave_prefixes = [
        f"wave_{ordinal}_"
        for ordinal in (
            _wave_ordinal(data.get("current_wave")),
            _wave_ordinal(data.get("next_wave")),
        )
        if ordinal is not None
    ]

    # Phase-scoped keys for the current phase (``phase_9_`` won't match
    # ``phase_2_wave_9_work`` — again the trailing underscore disambiguates).
    phase = data.get("current_phase")
    phase_prefix = f"phase_{phase}_" if phase is not None else None

    scoped: dict = {}
    blockers: dict = {}
    for key, value in data.items():
        if key in _DIGEST_POINTER_KEYS:
            continue
        if key.startswith("owner_decision_gated"):
            # Only surface unresolved blockers (a non-empty list / truthy value);
            # the ``owner_decision_gated_resolved_*`` audit keys are history, not
            # live state, so they stay out of the digest even when non-empty.
            if value and "resolved" not in key:
                blockers[key] = value
            continue
        if any(key.startswith(p) for p in wave_prefixes):
            scoped[key] = value
            continue
        if phase_prefix is not None and key.startswith(phase_prefix):
            scoped[key] = value

    for key in sorted(scoped):
        digest[key] = scoped[key]
    for key in sorted(blockers):
        digest[key] = blockers[key]
    return digest


def _cmd_digest(args: argparse.Namespace) -> int:
    print(json.dumps(build_digest(args.status), indent=2))
    return 0


def _cmd_repos(args: argparse.Namespace) -> int:
    for repo in read_repos(args.wave, args.status):
        print(repo)
    return 0


def _cmd_merged_prs(args: argparse.Namespace) -> int:
    prs, claimed = _merged_prs_with_claims(args.phase, args.wave, args.status)
    print(json.dumps(prs, indent=2))

    warning = _reconciliation_warning_from_claims(args.wave, args.status, claimed)
    if warning:
        print(f"WARNING: {warning}", file=sys.stderr)
    return 0


def _cmd_counters(args: argparse.Namespace) -> int:
    prs, claimed = _merged_prs_with_claims(args.phase, args.wave, args.status)
    counters = _compute_counters_from_prs(prs)
    print(json.dumps(counters, indent=2))

    # main#1190: a reconciliation WARNING (never an error -- an open scope
    # row is normal mid-wave), computed from the same pass above so this
    # never re-runs the closing-reference `gh` calls.
    warning = _reconciliation_warning_from_claims(args.wave, args.status, claimed)
    if warning:
        print(f"WARNING: {warning}", file=sys.stderr)

    if args.expect is not None and counters["final_pr_count"] != args.expect:
        print(
            f"ERROR: final_pr_count {counters['final_pr_count']} != --expect {args.expect}",
            file=sys.stderr,
        )
        return 1

    if args.write:
        rc = _write_counters(args.wave, counters, args.status)
        if rc != 0:
            return rc
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    def _add_pm(p: argparse.ArgumentParser) -> None:
        p.add_argument("phase", help="phase number (P)")
        p.add_argument("wave", help="wave number (M)")
        p.add_argument(
            "--status",
            type=Path,
            default=_DEFAULT_STATUS,
            help="path to cross-repo-status.json (default: repo-root copy)",
        )

    p_digest = sub.add_parser(
        "digest",
        help="emit a compact current-wave/phase projection of the status file (session-start)",
    )
    p_digest.add_argument(
        "--status",
        type=Path,
        default=_DEFAULT_STATUS,
        help="path to cross-repo-status.json (default: repo-root copy)",
    )
    p_digest.set_defaults(func=_cmd_digest)

    p_repos = sub.add_parser("repos", help="emit wave_{M}_repos_in_scope one per line")
    _add_pm(p_repos)
    p_repos.set_defaults(func=_cmd_repos)

    p_merged = sub.add_parser("merged-prs", help="emit the wave's merged-PR set as JSON")
    _add_pm(p_merged)
    p_merged.set_defaults(func=_cmd_merged_prs)

    p_counters = sub.add_parser("counters", help="compute (and optionally write) wave counters")
    _add_pm(p_counters)
    p_counters.add_argument(
        "--write",
        action="store_true",
        help="upsert the three canonical top-level keys into cross-repo-status.json",
    )
    p_counters.add_argument(
        "--expect",
        type=int,
        default=None,
        help="loud-fail (exit 1) if final_pr_count != N",
    )
    p_counters.set_defaults(func=_cmd_counters)
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
