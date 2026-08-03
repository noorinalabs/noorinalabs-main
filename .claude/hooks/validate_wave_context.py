#!/usr/bin/env python3
"""PreToolUse hook: Warn when agents are spawned without wave context.

Checks Agent tool calls for an active wave marker in cross-repo-status.json.
Ontology context enforcement is handled separately by enforce_ontology_context.py.

Exit codes:
  0 — always allow (warning only)
"""

import json
from pathlib import Path

from _hook_main import run_advisory

_STATUS_PATH = Path(__file__).resolve().parent.parent.parent / "cross-repo-status.json"


def has_active_wave() -> bool:
    """Check if cross-repo-status.json indicates an active wave."""
    try:
        data = json.loads(_STATUS_PATH.read_text(encoding="utf-8"))
        if data.get("wave_active"):
            return True
        if data.get("current_wave"):
            return True
        return False
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return False


def check(input_data: dict) -> dict | None:
    """Dispatcher-compatible entry point (main#1121 — extracted from the old
    inline `main()` body, no logic change). Returns None to allow silently, or
    an ``allow``-decision advisory dict when no wave context is active."""
    tool_name = input_data.get("tool_name", "")
    if tool_name != "Agent":
        return None

    if not has_active_wave():
        return {
            "decision": "allow",
            "systemMessage": (
                "WARNING: No active wave context detected in cross-repo-status.json. "
                "Run `/wave-kickoff` to set up wave context before spawning agents."
            ),
        }
    return None


def main() -> None:
    run_advisory(check, "validate_wave_context")


if __name__ == "__main__":
    main()
