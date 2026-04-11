#!/usr/bin/env python3
"""PreToolUse hook: Block --no-verify on git commit.

Detects `--no-verify` or `-n` (short form) on git commit commands and requires
user confirmation before proceeding.

Exit codes:
  0 — allow (no --no-verify detected, or not a git commit)
  2 — block (--no-verify detected, user must confirm)
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from annunaki_log import log_pretooluse_block


def check(input_data: dict) -> dict | None:
    """Check for --no-verify. Returns result dict if blocking, None if allowed."""
    tool_name = input_data.get("tool_name", "")
    if tool_name != "Bash":
        return None

    command = input_data.get("tool_input", {}).get("command", "")

    if not re.search(r"\bgit\b.*\bcommit\b", command):
        return None

    if "--no-verify" not in command:
        return None

    result = {
        "decision": "block",
        "reason": (
            "BLOCKED: `--no-verify` detected on git commit. "
            "This bypasses pre-commit hooks which are required by the charter. "
            "Engineers must not use --no-verify routinely. "
            "If you have a legitimate emergency reason, remove --no-verify and "
            "fix the underlying hook failure instead."
        ),
    }
    log_pretooluse_block("block_no_verify", command, result["reason"])
    return result


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    result = check(input_data)
    if result and result.get("decision") == "block":
        print(json.dumps(result))
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
