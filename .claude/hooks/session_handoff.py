#!/usr/bin/env python3
"""Stop hook: Auto-generate session handoff on exit.

Fires when Claude finishes its final response. Captures machine-readable
project state (git, PRs, issues, ontology staleness) and writes a handoff
file to project memory for the next session to pick up.

This replaces the need to manually run /handoff before exiting. The handoff
won't include conversational context (what was discussed), but the next
session can infer that from git log and the state captured here.

Exit codes:
  0 — always (advisory, never blocks)
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib")
sys.path.insert(0, os.path.abspath(_LIB_DIR))
# `checksums_io` is the ONE implementation of the dirty predicate (#1142) —
# `_get_ontology_staleness` below consumes it instead of re-deriving the
# `last_tracked != last_resolved` comparison.
import checksums_io  # noqa: E402
from org_repos import ALL_REPOS, ORG  # noqa: E402

# Project memory is version-controlled in-repo (#732 relocation) so it travels
# with a git pull. The handoff file itself stays gitignored — it's per-session
# machine-local churn — but it MUST live alongside the corpus so the SessionStart
# hook (session_start.py) and the /session-start skill read the same file. When
# this lived under the user-space ~/.claude/projects/ auto-memory dir while the
# skill read in-repo, the two diverged (split-brain, #741).
#
# We deliberately do NOT auto-rewrite the tracked MEMORY.md index line from this
# Stop hook: mutating a version-controlled file on every session exit is exactly
# the churn the gitignore on the handoff file avoids. The /handoff skill owns the
# committed index line (a deliberate, intentional write).
MEMORY_DIR = REPO_ROOT / ".claude" / "memory"
HANDOFF_FILE = MEMORY_DIR / "session_handoff.md"


def _run(cmd: str, cwd: str | None = None, timeout: int = 10) -> str:
    """Run a shell command and return stdout, or empty string on failure."""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd or str(REPO_ROOT),
        )
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""


def _get_git_state() -> dict:
    """Capture current git state."""
    return {
        "branch": _run("git branch --show-current"),
        "recent_commits": _run("git log --oneline -10"),
        "status": _run("git status --short"),
        "uncommitted": bool(_run("git status --porcelain")),
    }


# GitHub's search API pages at 100 results/request and caps at 1000 total.
# We stay at exactly one page (--limit == the page max) so "one search call"
# is literally one HTTP request, not gh silently paginating under the hood.
PR_SEARCH_LIMIT = 100


class PrQueryResult(NamedTuple):
    """Outcome of the single org-wide open-PR search.

    `failed` and an empty `lines` list are DISTINCT states — a failed query
    must never render the same as "the org genuinely has zero open PRs"
    (main#1120). `truncated` flags a possible partial result: the result set
    hit PR_SEARCH_LIMIT, so PRs beyond the cap (e.g. a large repo crowding
    out others under `--sort updated`) may be missing without any command
    error. `unknown_repos` are repos the search returned that are NOT in
    org_repos.ALL_REPOS — the inverse of BUG-08 (a repo added org-side that
    the SSOT list doesn't know about yet), something the old per-repo loop
    could structurally never detect since it only ever queried repos already
    in its list.
    """

    lines: list[str]
    failed: bool
    truncated: bool
    unknown_repos: tuple[str, ...]


def _get_open_prs() -> PrQueryResult:
    """Get open PRs across the whole org in a single search call.

    Replaces the previous 7-serial (pre-#1238) / 8-serial (post-#1238) loop
    of `gh pr list --repo ...` subprocesses — worst case ~120s against a 30s
    Stop-hook timeout (main#1120 / audit G8) — with one `gh search prs
    --owner noorinalabs` call spanning all repos the token can see, so it no
    longer needs a repo list to construct the query at all (pairs with G6).

    Collapsing 8 independent calls into 1 changes the failure shape: before,
    one repo's `gh pr list` timing out only dropped that repo's PRs (still
    silently — `_run()` swallows failures into ""), leaving the other 7
    repos' results intact. Now a single failed call drops the WHOLE org's PR
    list in one shot. `_run()` returns "" on any failure, which is
    byte-for-byte different from a genuine empty result ("[]" parses to an
    empty list, not ""), so that distinction is preserved explicitly here
    and surfaced up through `failed` — main() must render "query failed",
    never "None", when `failed` is True.
    """
    raw = _run(
        f"gh search prs --owner {ORG} --state open --sort updated "
        f"--json number,title,repository --limit {PR_SEARCH_LIMIT}",
        timeout=15,
    )
    if not raw:
        return PrQueryResult(lines=[], failed=True, truncated=False, unknown_repos=())
    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        return PrQueryResult(lines=[], failed=True, truncated=False, unknown_repos=())

    lines = []
    repos_seen: set[str] = set()
    for item in items:
        try:
            repo = item["repository"]["name"]
            lines.append(f"  - {repo}#{item['number']}: {item['title']}")
            repos_seen.add(repo)
        except (KeyError, TypeError):
            continue

    truncated = len(items) >= PR_SEARCH_LIMIT
    unknown_repos = tuple(sorted(repos_seen - set(ALL_REPOS)))
    return PrQueryResult(
        lines=lines, failed=False, truncated=truncated, unknown_repos=unknown_repos
    )


def _render_prs_section(result: PrQueryResult) -> list[str]:
    """Build the '### Open PRs' markdown block from a PrQueryResult.

    A failed query is never rendered as "None" — that would misreport an
    unknown PR state as "the org has zero open PRs". Truncation at the
    search cap and unexpected repos are both surfaced as explicit notes
    rather than silently folded into (or dropped from) the list.
    """
    section = ["### Open PRs"]
    if result.failed:
        section.append(
            "  - QUERY FAILED (gh search prs errored or timed out) — PR state "
            "unknown, NOT confirmed empty"
        )
        return section
    if not result.lines:
        section.append("  - None")
    else:
        section.extend(result.lines)
    if result.truncated:
        section.append(
            f"  - NOTE: hit the {PR_SEARCH_LIMIT}-result search cap — some open "
            "PRs may be missing from this list"
        )
    if result.unknown_repos:
        section.append(
            "  - NOTE: PR(s) found in repo(s) not in org_repos.ALL_REPOS: "
            f"{', '.join(result.unknown_repos)} — SSOT list may be stale"
        )
    return section


def _get_open_issues() -> list[str]:
    """Get open issues on main repo."""
    raw = _run(
        "gh issue list --repo noorinalabs/noorinalabs-main"
        " --state open --limit 10 --json number,title,labels",
        timeout=15,
    )
    issues = []
    if raw:
        try:
            items = json.loads(raw)
            for item in items:
                label_names = [lb["name"] for lb in item.get("labels", [])]
                label_str = f" [{', '.join(label_names)}]" if label_names else ""
                issues.append(f"  - #{item['number']}: {item['title']}{label_str}")
        except (json.JSONDecodeError, KeyError):
            pass
    return issues


def _get_ontology_staleness() -> str:
    """Check ontology checksums for dirty files.

    Delegates to ``checksums_io.read_status`` (#1142) instead of re-deriving
    ``last_tracked != last_resolved``. The handoff this writes is what the next
    session reads first, so a wrong "Ontology is current (0 dirty files)" here
    is a wrong belief carried across a session boundary — which is exactly how
    the #1142 miscount propagated into a handoff in the first place.
    """
    checksums_file = REPO_ROOT / "ontology" / "checksums.json"
    if not checksums_file.exists():
        return "No ontology checksums found"
    try:
        status = checksums_io.read_status(checksums_file)
    except checksums_io.ChecksumsUnreadable:
        return "Could not read checksums"
    if status.clean:
        return "Ontology is current (0 dirty files)"
    parts = []
    if status.dirty:
        suffix = "..." if len(status.dirty) > 5 else ""
        parts.append(f"{len(status.dirty)} dirty files: {', '.join(status.dirty[:5])}{suffix}")
    if status.malformed:
        names = [rel for rel, _ in status.malformed[:5]]
        suffix = "..." if len(status.malformed) > 5 else ""
        parts.append(f"{len(status.malformed)} malformed entries: {', '.join(names)}{suffix}")
    return f"Ontology has {'; '.join(parts)}"


def _wave_phase_started(data: dict) -> tuple[str, str, str]:
    """Resolve (phase, wave, started) from a cross-repo-status.json dict.

    Reads the canonical lifecycle keys maintained by the wave skills:
      - phase   ← ``current_phase``
      - wave    ← ``current_wave`` (e.g. "wave-5")
      - started ← ``wave_<N>_started_at`` for N parsed from ``current_wave``,
                  falling back to ``wave_<N>_kicked_off_at``, then "unknown".

    The flat ``phase``/``wave``/``started``/``last_updated`` keys are NOT used
    as the source of truth — ``phase`` lags a phase behind (cross-phase key
    collision, #683) and ``wave``/``started`` do not exist (#708).
    """
    phase = data.get("current_phase", "unknown")
    wave = data.get("current_wave", "unknown")
    started = "unknown"
    if isinstance(wave, str):
        match = re.search(r"(\d+)", wave)
        if match:
            n = match.group(1)
            # `or` chains past both missing keys AND present-but-null values.
            started = (
                data.get(f"wave_{n}_started_at") or data.get(f"wave_{n}_kicked_off_at") or "unknown"
            )
    return str(phase), str(wave), started


def _get_wave_status() -> str:
    """Read cross-repo status for the active phase/wave."""
    status_file = REPO_ROOT / "cross-repo-status.json"
    if not status_file.exists():
        return "No cross-repo-status.json found"
    try:
        with open(status_file) as f:
            data = json.load(f)
        phase, wave, started = _wave_phase_started(data)
        return f"Phase {phase}, Wave {wave} (started {started})"
    except (json.JSONDecodeError, OSError):
        return "Could not read status file"


THROTTLE_SECONDS = 300  # Only regenerate if file is older than 5 minutes


def main() -> None:
    # Throttle: skip if handoff was written recently (avoids gh API spam)
    if HANDOFF_FILE.exists():
        age = datetime.now(timezone.utc).timestamp() - HANDOFF_FILE.stat().st_mtime
        if age < THROTTLE_SECONDS:
            sys.exit(0)

    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d %H:%M UTC")

    git = _get_git_state()
    pr_result = _get_open_prs()
    issues = _get_open_issues()
    ontology = _get_ontology_staleness()
    wave = _get_wave_status()

    # Build handoff content
    lines = [
        "---",
        "name: Session handoff",
        "description: Auto-generated pickup prompt — read this first to resume work",
        "type: project",
        "---",
        "",
        f"## Last session: {date_str}",
        "",
        "### Git state",
        f"- **Branch:** {git['branch']}",
        f"- **Uncommitted changes:** {'Yes' if git['uncommitted'] else 'No'}",
        "",
        "**Recent commits:**",
        "```",
        git["recent_commits"],
        "```",
        "",
        "### Wave/phase status",
        f"- {wave}",
        "",
        "### Ontology",
        f"- {ontology}",
        "",
    ]

    lines.extend([*_render_prs_section(pr_result), ""])

    if issues:
        lines.extend(["### Open issues (noorinalabs-main)", *issues, ""])
    else:
        lines.extend(["### Open issues (noorinalabs-main)", "  - None", ""])

    lines.extend(
        [
            "### Notes",
            "This handoff was auto-generated on session exit. For conversational context,",
            "check the git log above — commit messages capture what was done.",
        ]
    )

    content = "\n".join(lines) + "\n"

    # Write handoff file
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(HANDOFF_FILE, "w", encoding="utf-8") as f:
            f.write(content)
    except OSError:
        sys.exit(0)

    # Note: the tracked MEMORY.md index line is intentionally NOT updated here —
    # see the MEMORY_DIR comment above. The committed index line is owned by the
    # /handoff skill so this Stop hook never dirties a version-controlled file.

    # Build a compact display version for the conversation
    display_lines = [
        f"[Session Handoff — {date_str}]",
        f"Branch: {git['branch']} | Uncommitted: {'Yes' if git['uncommitted'] else 'No'}",
        f"Wave: {wave} | Ontology: {ontology}",
    ]
    if pr_result.failed:
        display_lines.append("Open PRs: QUERY FAILED — see handoff file, NOT confirmed empty")
    else:
        suffix = " (truncated at cap)" if pr_result.truncated else ""
        display_lines.append(f"Open PRs: {len(pr_result.lines)}{suffix}")
        display_lines.extend(pr_result.lines[:5])
        if pr_result.unknown_repos:
            display_lines.append(
                f"Unknown repos in PR results: {', '.join(pr_result.unknown_repos)}"
            )
    if issues:
        display_lines.append(f"Open issues (main): {len(issues)}")
        display_lines.extend(issues[:5])
    display_lines.append("Handoff saved to project memory — next session will auto-load it.")

    result = {
        "systemMessage": "\n".join(display_lines),
    }
    print(json.dumps(result))
    sys.exit(0)


if __name__ == "__main__":
    main()
