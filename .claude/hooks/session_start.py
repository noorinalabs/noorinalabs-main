#!/usr/bin/env python3
"""SessionStart hook: Emit directives for the 7-step startup protocol.

Fires at the beginning of every Claude Code session (startup and resume).
Checks worktree state, team cleanup, ontology staleness, annunaki error count,
handoff state, wave orientation, and charter freshness, then prints directives
to stdout so Claude sees them immediately.

Exit codes:
  0 — always (informational hook, never blocks)
"""

import json
import sys
from pathlib import Path

_PROJECT = Path(__file__).resolve().parent.parent.parent
_CHECKSUMS = _PROJECT / "ontology" / "checksums.json"
_ERRORS_LOG = _PROJECT / ".claude" / "annunaki" / "errors.jsonl"
_CROSS_REPO_STATUS = _PROJECT / "cross-repo-status.json"
# Claude Code encodes project paths by replacing / with - (leading slash becomes leading -)
_ENCODED_PROJECT = str(_PROJECT).replace("/", "-")
_HANDOFF = Path.home() / ".claude" / "projects" / _ENCODED_PROJECT / "memory" / "session_handoff.md"


def _ontology_staleness() -> tuple[int, int]:
    """Return (dirty_count, total_count) from checksums.json."""
    try:
        data = json.loads(_CHECKSUMS.read_text(encoding="utf-8"))
        # Nested format: {version, description, files: {...}}
        data = data.get("files", data)
        dirty = sum(
            1
            for v in data.values()
            if isinstance(v, dict) and v.get("last_tracked") != v.get("last_resolved")
        )
        return dirty, len(data)
    except (OSError, json.JSONDecodeError):
        return -1, 0


def _annunaki_error_count() -> int:
    """Return number of lines in errors.jsonl, or -1 if missing."""
    try:
        text = _ERRORS_LOG.read_text(encoding="utf-8").strip()
        if not text:
            return 0
        return len(text.splitlines())
    except OSError:
        return -1


def _handoff_summary() -> str | None:
    """Return handoff file content if it exists, or None."""
    try:
        text = _HANDOFF.read_text(encoding="utf-8").strip()
        if not text:
            return None
        # Strip frontmatter
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                text = parts[2].strip()
        return text if text else None
    except OSError:
        return None


def _wave_status() -> str | None:
    """Return a brief summary from cross-repo-status.json, or None."""
    try:
        data = json.loads(_CROSS_REPO_STATUS.read_text(encoding="utf-8"))
        phase = data.get("phase", "unknown")
        wave = data.get("wave", "unknown")
        updated = data.get("last_updated", "unknown")
        return f"Phase {phase}, Wave {wave} (last updated: {updated})"
    except (OSError, json.JSONDecodeError):
        return None


def main() -> None:
    lines = [
        "=" * 60,
        "SESSION START PROTOCOL — MANDATORY",
        "=" * 60,
        "",
        "STOP. You MUST complete ALL steps below BEFORE responding to",
        "the user's message. Do NOT skip steps. Do NOT defer. Execute",
        "each step NOW, then summarize results to the user.",
        "",
    ]

    # Step 0: Worktree cleanup (parent + child repos, per #526)
    lines.append("STEP 0 — WORKTREE CLEANUP (parent + child repos):")
    lines.append("  Run the Step 0 block in skills/session-start/SKILL.md.")
    lines.append("  It prunes the parent AND all 7 child repos, auto-removing")
    lines.append("  only worktrees merged into origin/main and FLAGGING locked")
    lines.append("  or unmerged ones for a manual decision (never auto-removed).")
    lines.append("")

    # Step 1: Team cleanup (unique to noorinalabs-main)
    lines.append("STEP 1 — TEAM CLEANUP:")
    lines.append("  Run TeamDelete then TeamCreate for the 'noorinalabs' team.")
    lines.append("  Stale team state from prior sessions causes errors.")
    lines.append("  Always start fresh — never reuse an existing team.")
    lines.append("")

    # Step 2: Session handoff
    handoff = _handoff_summary()
    lines.append("STEP 2 — HANDOFF CHECK:")
    if handoff:
        lines.append("  Handoff found. Read and summarize to user:")
        lines.append("")
        lines.append(handoff)
        lines.append("")
    else:
        lines.append("  No handoff found. Skip.")
        lines.append("")

    # Step 3: Ontology staleness
    dirty, total = _ontology_staleness()
    lines.append("STEP 3 — ONTOLOGY CHECK:")
    if dirty < 0:
        lines.append("  checksums.json not found — run /ontology-rebuild")
    elif dirty == 0:
        lines.append(f"  Current ({dirty}/{total} dirty). No action needed.")
    else:
        lines.append(f"  DIRTY: {dirty}/{total} files need rebuild.")
        lines.append("  ACTION: Run /ontology-rebuild NOW.")
    lines.append("")

    # Step 4: Annunaki errors
    error_count = _annunaki_error_count()
    lines.append("STEP 4 — ANNUNAKI CHECK:")
    if error_count < 0:
        lines.append("  Error log not found. Monitoring is passive, no action needed.")
    elif error_count == 0:
        lines.append("  No errors logged. Monitor active.")
    elif error_count < 5:
        lines.append(f"  {error_count} error(s) logged. Monitor active. Review briefly.")
    else:
        lines.append(f"  {error_count} errors logged — ACTION: Run /annunaki-attack.")
    lines.append("")

    # Step 5: Wave/phase orientation
    wave_info = _wave_status()
    lines.append("STEP 5 — WAVE/PHASE ORIENTATION:")
    if wave_info:
        lines.append(f"  Status from cross-repo-status.json: {wave_info}")
    else:
        lines.append("  cross-repo-status.json not found or unreadable.")
    lines.append(
        "  Run: gh issue list --repo noorinalabs/noorinalabs-main --state open"
        " --limit 10 --json number,title,labels"
    )
    lines.append("  Establish current phase and open work items.")
    lines.append("")

    # Step 6: Charter freshness
    lines.append("STEP 6 — CHARTER FRESHNESS:")
    lines.append("  Check for unapplied retro proposals or undocumented automation.")
    lines.append("")

    # Summary directive
    actions = ["Run worktree cleanup (Step 0)"]
    actions.append("Run team cleanup — TeamDelete + TeamCreate (Step 1)")
    if handoff:
        actions.append("Summarize handoff to user (Step 2)")
    if dirty and dirty > 0:
        actions.append("Run /ontology-rebuild (Step 3)")
    if error_count >= 5:
        actions.append("Run /annunaki-attack (Step 4)")
    actions.append("Complete wave/phase orientation (Step 5)")
    actions.append("Complete charter freshness check (Step 6)")

    lines.append("=" * 60)
    lines.append("ACTIONS REQUIRED (execute in order):")
    for i, action in enumerate(actions, 1):
        lines.append(f"  {i}. {action}")
    lines.append("")
    lines.append("Do NOT respond to the user until all steps are complete.")
    lines.append("=" * 60)

    print("\n".join(lines))
    sys.exit(0)


if __name__ == "__main__":
    main()
