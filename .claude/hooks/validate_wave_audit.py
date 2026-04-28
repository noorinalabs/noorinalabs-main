#!/usr/bin/env python3
"""PreToolUse hook: Block wave-lifecycle skills until cross-repo audit clears.

The charter mandates (skills.md § Wave Lifecycle — Open-Item Audit) that any
skill claiming a wave is "concluded" / "complete" / "done" must first prove
the cross-repo open-item count is zero OR enumerate an explicit carry-forward
list. P2W9 emitted a "wave-9 parent-repo workstream concluded" handoff with
~22 items still open across child repos; the owner had to prompt to surface
the truth. Per the enforcement-hierarchy principle (hook > skill > charter),
a charter rule that already failed once becomes a hook.

This hook fires on PreToolUse Skill calls for wave-wrapup, wave-retro, and
handoff. It runs the canonical cross-repo audit unconditionally and blocks
the skill's invocation when open items exist without a carry-forward marker
in the skill's `args` payload. The skill's own narrative cannot rationalize
its way past the gate — the args must encode the carry-forward decision
BEFORE the skill is allowed to render.

PostToolUse output-scan was rejected during design review (issue #195 design
comment): by the time PostToolUse fires, the false claim is already on
screen and in the conversation history, defeating the enforcement-hierarchy
point. PreToolUse with audit-execution is the load-bearing surface.

Input Language
==============

Fires on:
    PreToolUse Skill

Matches:
    {tool_name: "Skill", tool_input: {skill: "<name>", args: "..."}}
    where <name> ∈ {"wave-wrapup", "wave-retro", "handoff"}

Does NOT match:
    Skill calls for /ontology-librarian, /session-start, /annunaki, etc.
        (only wave-lifecycle skills are gated; matcher checks
         tool_input.skill exactly against the gated set)
    Bash commands containing "wave-wrapup" / "handoff" as substrings
        (matcher is Skill, not Bash — `tool_name != "Skill"` short-circuits;
         this is the substring-bug guard, sibling of #216)
    Skill calls when wave_active == false in cross-repo-status.json
        (no active wave → no audit possible → allow with system message)

Carry-forward bypass (warn-but-allow):
    The hook scans `tool_input.args` (case-insensitive) for any of:
      - "carry-forward:" or "carry forward:" inline marker
      - "## Carry-forward" / "## Carry forward" markdown heading
      - "#<N> →" / "#<N> -> " arrow patterns naming a destination
    If matched, the audit is informational only — allow with a system
    message summarizing what's being carried.

Block condition:
    matched_skill AND open_count > 0 AND args lacks carry-forward marker

Allow condition:
    Any of:
      - matched_skill is False (different skill, different tool entirely)
      - open_count == 0
      - args contains a carry-forward marker
      - audit shell-out failed for infrastructure reasons (fail-open with
        system warning — see § Failure modes below)

Audit shell-out:
    Iterates the 8 org-known repos (charter skills.md § Audit command),
    running:
        gh issue list --repo "noorinalabs/<repo>" --state open \\
            --label "p2-wave-<N>" --json number --jq 'length'
    Wave label `<N>` is derived from `cross-repo-status.json` field
    `current_wave` (e.g. "wave-10" → "10"). Total open count is the sum
    across all repos.

Failure modes (all fail-open with system warning, never block):
    - `gh` not installed / not authenticated → cannot audit, allow.
    - Network/API failure on a single repo → skip that repo, sum the rest.
    - cross-repo-status.json missing or malformed → cannot determine wave,
      allow with warning.
    - current_wave field missing / not a "wave-<N>" string → cannot derive
      label, allow with warning.
    - Wall-clock budget: 8 gh calls × ~1.5s ≈ 12s. settings.json timeout
      should be 30s.

Bypass policy:
    No in-band override flag. The whole point of the hook is to break the
    "this one's fine, just say concluded" rationalization that put the
    P2W9 incident on owner's desk. If the gate fires, the only paths are
    (a) close the open items, (b) add a carry-forward block to args, or
    (c) emergency override by removing the hook entry from settings.json.
    This matches Hook 15's stance (no in-band override).

Exit codes (per Claude Code hook convention):
    0 — allow (not a matched skill, audit zero, args has carry-forward,
        infra failure fail-open)
    2 — block (matched skill, open count > 0, no carry-forward in args)

Promotion provenance:
    memory feedback_honest_audit_over_conclusion_claim (2026-04-22) →
    charter skills.md § Wave Lifecycle — Open-Item Audit (PR #193) →
    this hook (issue #195). Second worked example of the
    memory→charter→hook promotion pipeline ratified 2026-04-19 (Hook 15
    was the first).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from annunaki_log import log_pretooluse_block  # noqa: E402

# Skills gated by this hook. Exact match against tool_input.skill.
_GATED_SKILLS = frozenset({"wave-wrapup", "wave-retro", "handoff"})

# Org-known repos for cross-repo audit. Sourced from charter skills.md
# § Audit command. This list MUST stay in sync with that charter section.
_ORG_REPOS = (
    "noorinalabs-main",
    "noorinalabs-isnad-graph",
    "noorinalabs-user-service",
    "noorinalabs-deploy",
    "noorinalabs-design-system",
    "noorinalabs-landing-page",
    "noorinalabs-data-acquisition",
    "noorinalabs-isnad-ingest-platform",
)

# Carry-forward detection patterns (case-insensitive). Any one suffices.
# Anchored loosely — looking for explicit author intent, not accidental phrasing.
_CARRY_FORWARD_PATTERNS = (
    re.compile(r"carry[\s-]forward\s*:", re.IGNORECASE),
    re.compile(r"^#{1,6}\s+carry[\s-]forward\b", re.IGNORECASE | re.MULTILINE),
    re.compile(r"#\d+\s*(?:->|→)\s*[A-Za-z_]", re.IGNORECASE),
)

# Path to cross-repo-status.json relative to this hook file.
_STATUS_PATH = Path(__file__).resolve().parent.parent.parent / "cross-repo-status.json"

# gh subprocess timeout per repo (seconds). 8 repos × this = total budget.
_PER_REPO_TIMEOUT_SECONDS = 3


def _read_current_wave_label() -> str | None:
    """Return the active wave label (e.g. 'p2-wave-10') or None.

    Derives the label from cross-repo-status.json `current_wave` field.
    Expected format: "wave-<N>" with `phase` field giving "phase-2" → label
    "p2-wave-<N>". Returns None on any failure (missing file, malformed
    JSON, missing fields, unparseable wave value).
    """
    try:
        data = json.loads(_STATUS_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None

    if not data.get("wave_active"):
        return None

    current = data.get("current_wave", "")
    phase = data.get("phase", "")

    wave_match = re.fullmatch(r"wave-(\d+)", str(current))
    phase_match = re.fullmatch(r"phase-(\d+)", str(phase))
    if not wave_match or not phase_match:
        return None

    return f"p{phase_match.group(1)}-wave-{wave_match.group(1)}"


def _count_open_for_repo(repo: str, label: str) -> int | None:
    """Return open-issue count for `noorinalabs/<repo>` filtered by `label`.

    Returns the integer count on success, None on subprocess failure (gh
    missing, network error, auth failure). Caller decides whether to
    treat None as fail-open or partial.
    """
    try:
        result = subprocess.run(
            [
                "gh",
                "issue",
                "list",
                "--repo",
                f"noorinalabs/{repo}",
                "--state",
                "open",
                "--label",
                label,
                "--json",
                "number",
                "--jq",
                "length",
            ],
            capture_output=True,
            text=True,
            timeout=_PER_REPO_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None

    if result.returncode != 0:
        return None

    out = result.stdout.strip()
    if not out:
        return 0
    try:
        return int(out)
    except ValueError:
        return None


def _audit_open_count(label: str) -> tuple[int | None, dict[str, int]]:
    """Run the cross-repo audit. Returns (total_or_None, per_repo_counts).

    `total_or_None` is None only if EVERY repo's audit failed (full
    infrastructure failure → fail-open). Otherwise it's the sum of all
    successfully-audited repos, even if some individual repos failed
    (partial result is more useful than None).

    `per_repo_counts` maps repo name → count for repos with non-zero
    open issues. Repos with zero opens or with audit failures are omitted.
    """
    per_repo: dict[str, int] = {}
    successes = 0

    for repo in _ORG_REPOS:
        count = _count_open_for_repo(repo, label)
        if count is None:
            continue
        successes += 1
        if count > 0:
            per_repo[repo] = count

    if successes == 0:
        return None, per_repo

    total = sum(per_repo.values())
    return total, per_repo


def _has_carry_forward(args: str) -> bool:
    """Return True iff `args` contains an explicit carry-forward marker."""
    if not args:
        return False
    return any(pattern.search(args) for pattern in _CARRY_FORWARD_PATTERNS)


def _format_per_repo(per_repo: dict[str, int]) -> str:
    """Format the per-repo open-item summary for block/warning messages."""
    if not per_repo:
        return "  (no per-repo breakdown — all audited repos returned 0)"
    lines = []
    for repo in sorted(per_repo.keys()):
        lines.append(f"  - noorinalabs/{repo}: {per_repo[repo]} open")
    return "\n".join(lines)


def check(input_data: dict) -> dict | None:
    """Check the wave-audit precondition. Returns result dict if blocking, None if allowed.

    Public API matches the dispatcher convention. Returns None to allow,
    a dict with `decision: "block"` to block, or a dict with
    `decision: "allow"` plus `systemMessage` to allow with a warning.
    """
    tool_name = input_data.get("tool_name", "")
    if tool_name != "Skill":
        return None

    tool_input = input_data.get("tool_input", {})
    skill_name = tool_input.get("skill", "")

    if skill_name not in _GATED_SKILLS:
        return None

    label = _read_current_wave_label()
    if label is None:
        return {
            "decision": "allow",
            "systemMessage": (
                f"WARNING: Wave-audit hook could not determine an active wave label "
                f"from cross-repo-status.json. Allowing /{skill_name} to proceed without "
                "an audit. If you are claiming a wave is concluded, run the canonical "
                "audit manually (charter skills.md § Wave Lifecycle — Audit command)."
            ),
        }

    total, per_repo = _audit_open_count(label)

    if total is None:
        return {
            "decision": "allow",
            "systemMessage": (
                f"WARNING: Wave-audit hook could not query any of the {len(_ORG_REPOS)} "
                f"org repos for label `{label}` (gh CLI missing, unauthenticated, or "
                f"all calls failed). Allowing /{skill_name} to proceed without an audit. "
                "Run the canonical audit manually before claiming the wave is concluded."
            ),
        }

    if total == 0:
        return None

    args = tool_input.get("args", "")
    if _has_carry_forward(args):
        return {
            "decision": "allow",
            "systemMessage": (
                f"NOTE: {total} open item(s) for `{label}` across {len(per_repo)} repo(s); "
                f"carry-forward marker detected in args, allowing /{skill_name} to proceed.\n"
                f"Per-repo open counts:\n{_format_per_repo(per_repo)}\n"
                "Verify the carry-forward list in your output names every item above."
            ),
        }

    result = {
        "decision": "block",
        "reason": (
            f"BLOCKED: /{skill_name} cannot claim wave conclusion. "
            f"Charter § Wave Lifecycle — Open-Item Audit requires zero open items "
            f"for the active wave OR an explicit carry-forward list in the skill's args.\n\n"
            f"Active wave: {label}\n"
            f"Open items across the org: {total}\n"
            f"Per-repo breakdown:\n{_format_per_repo(per_repo)}\n\n"
            "To proceed, either:\n"
            f"  1. Close the open items above, then re-run /{skill_name}, OR\n"
            f"  2. Pass an explicit carry-forward list in args. Recognized markers:\n"
            "     - 'Carry-forward: #N → next-wave, #M → backlog' inline\n"
            "     - '## Carry-forward' markdown heading followed by item list\n"
            "     - '#N → destination' arrow patterns naming items individually\n\n"
            "There is no in-band bypass flag — see charter/hooks.md § Hook 17 for "
            "emergency procedure."
        ),
    }
    log_pretooluse_block(
        "validate_wave_audit",
        f"skill={skill_name} args={args[:200] if args else '<empty>'}",
        result["reason"],
        tool_name="Skill",
    )
    return result


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    result = check(input_data)
    if result is None:
        sys.exit(0)
    print(json.dumps(result))
    if result.get("decision") == "block":
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
