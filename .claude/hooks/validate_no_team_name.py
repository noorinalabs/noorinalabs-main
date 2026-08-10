#!/usr/bin/env python3
"""PreToolUse hook: Block Agent spawns that pass a `team_name`.

`team_name` is a **deprecated Agent-tool parameter**. The live tool schema
documents it as "Deprecated; ignored. The session has a single implicit
team." — there is no `TeamCreate`/`TeamDelete`, no team object to register
into, and therefore no name to choose. The correct number of `team_name`
values in any spawn is **zero**.

Why block rather than warn (#1375)
==================================

The charter mandated `team_name: "noorinalabs"` on every spawn across 14
sites, for a harness generation that no longer exists. That mandate is the
tier that failed, so the remedy belongs one tier up: per
`feedback_enforcement_hierarchy` (hook > skill > charter > memory), a
charter sentence cannot stop a brief written from a stale cached copy of
the charter — a hook can. Blocking also turns a silently-ignored argument
into an actionable message at the moment of the spawn, instead of leaving
the orchestrator to believe a team was named when none was.

Ported from the sibling repo `botfarm_inc`, which reversed the same
doctrine on the same harness version and whose hook this mirrors. That
hook's history is worth preserving: it originally *validated* that
`~/.claude/teams/<team>/config.json` existed before allowing a `team_name`
spawn. That model is gone, so the check was **inverted** rather than
deleted — the same file now blocks what it used to permit.

Fail-open on malformed input, matching `enforce_ontology_context`: a
PreToolUse hook that raises surfaces to the user as block-with-error, which
is worse than allowing through a malformed shape the tool will reject on
its own.

Exit codes:
  0 — allow (not an Agent call, or no team_name — the expected path)
  2 — block (Agent call carries a non-empty team_name)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hook_main import run_blocking  # noqa: E402
from annunaki_log import log_pretooluse_block  # noqa: E402


def check(input_data: dict) -> dict | None:
    """Pure decision function. Returns None to allow, or a block-dict."""
    if input_data.get("tool_name", "") != "Agent":
        return None

    tool_input = input_data.get("tool_input")
    if not isinstance(tool_input, dict):
        return None

    team_name = tool_input.get("team_name", "")
    if not isinstance(team_name, str):
        return None

    # The expected path: no team_name -> single implicit team -> allow.
    # An empty string is treated as absent: it names no team, so there is
    # nothing to correct and blocking it would be pure friction.
    if not team_name.strip():
        return None

    return {
        "decision": "block",
        "reason": (
            f'BLOCKED: Agent spawn passes team_name="{team_name}", but this '
            "harness has a single implicit team and the parameter is "
            "deprecated and ignored.\n\n"
            "Remove `team_name` from the Agent call and re-spawn. Agents stay "
            "addressable by their agent NAME via SendMessage — that routing "
            "never depended on team_name.\n\n"
            "Which repo an agent works on is expressed by its worktree and "
            "brief; which repo's people it draws on is the per-repo roster "
            "under <repo>/.claude/team/roster/. See CLAUDE.md "
            "§ Session team architecture and charter "
            "agents/naming-and-teams.md § Team Names (#1375)."
        ),
    }


def _check_and_log(input_data: dict) -> dict | None:
    """Wraps `check()` with the annunaki block-log side effect; `check()`
    itself stays pure, matching the sibling hooks (main#1121 convention)."""
    result = check(input_data)
    if result is None:
        return None
    prompt = ""
    tool_input = input_data.get("tool_input")
    if isinstance(tool_input, dict):
        raw = tool_input.get("prompt", "")
        if isinstance(raw, str):
            prompt = raw[:200]
    log_pretooluse_block("validate_no_team_name", prompt, result["reason"])
    return result


def main() -> None:
    run_blocking(_check_and_log, "validate_no_team_name")


if __name__ == "__main__":
    main()
