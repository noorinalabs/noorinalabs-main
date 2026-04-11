#!/usr/bin/env python3
"""PreToolUse hook: Block agent shutdown until wave retrospective is recorded.

Prevents SendMessage calls containing shutdown_request unless a retrospective
entry exists in feedback_log.md for today's date.

Exceptions:
  - Emergency shutdowns (reason: "error" or "crash")
  - Utility agents (name contains "explorer" or "reviewer")

Exit codes:
  0 — allow
  2 — block (no retro found for today)
"""

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from annunaki_log import log_pretooluse_block

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_FEEDBACK_LOG = _REPO_ROOT / ".claude" / "team" / "feedback_log.md"


def has_retro_for_today() -> bool:
    """Check if feedback_log.md contains a retrospective entry dated today."""
    today_str = date.today().strftime("%Y-%m-%d")
    try:
        content = _FEEDBACK_LOG.read_text(encoding="utf-8")
        # Look for a heading line containing today's date
        for line in content.splitlines():
            if line.startswith("#") and today_str in line:
                return True
        return False
    except FileNotFoundError:
        return False


def is_shutdown_request(message: str) -> bool:
    """Check if the message contains a shutdown request."""
    return "shutdown_request" in message


def is_emergency(message: str) -> bool:
    """Check if this is an emergency shutdown (error/crash)."""
    return '"reason": "error"' in message or '"reason": "crash"' in message


def is_utility_agent(tool_input: dict) -> bool:
    """Check if the target agent is a utility agent that doesn't need retros."""
    target = tool_input.get("to", "").lower()
    return "explorer" in target or "review" in target or "hook" in target


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    if tool_name != "SendMessage":
        sys.exit(0)

    tool_input = input_data.get("tool_input", {})
    message = tool_input.get("message", "")

    # Only care about shutdown requests
    if not is_shutdown_request(message):
        sys.exit(0)

    # Allow emergency shutdowns
    if is_emergency(message):
        sys.exit(0)

    # Allow utility agent shutdowns
    if is_utility_agent(tool_input):
        sys.exit(0)

    # Check for retro
    if has_retro_for_today():
        sys.exit(0)

    # Block: no retro found
    result = {
        "decision": "block",
        "reason": (
            "BLOCKED: Cannot shut down agents before running the wave retrospective. "
            "Run /wave-retro or /retro first, then retry shutdown."
        ),
    }
    log_pretooluse_block("block_shutdown_without_retro", message, result["reason"], tool_name="SendMessage")
    print(json.dumps(result))
    sys.exit(2)


if __name__ == "__main__":
    main()
