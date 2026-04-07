#!/usr/bin/env python3
"""PreToolUse hook: Warn when agents are spawned without wave context.

Checks for an active wave marker in cross-repo-status.json. If no active wave
is found, emits a warning (does not block).

Exit codes:
  0 — always allow (warning only)
"""

import json
from pathlib import Path
import sys

_STATUS_PATH = Path(__file__).resolve().parent.parent.parent / "cross-repo-status.json"


def has_active_wave() -> bool:
    """Check if cross-repo-status.json indicates an active wave."""
    try:
        data = json.loads(_STATUS_PATH.read_text(encoding="utf-8"))
        # Check for explicit wave_active marker
        if data.get("wave_active"):
            return True
        if data.get("current_wave"):
            return True
        return False
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return False


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    if tool_name != "Agent":
        sys.exit(0)

    if has_active_wave():
        sys.exit(0)

    result = {
        "decision": "allow",
        "systemMessage": (
            "WARNING: No active wave context detected in cross-repo-status.json. "
            "Run `/wave-kickoff` to set up wave context before spawning agents. "
            "Proceeding without wave context means retros, trust updates, and "
            "charter enforcement may be skipped."
        ),
    }
    print(json.dumps(result))
    sys.exit(0)


if __name__ == "__main__":
    main()
