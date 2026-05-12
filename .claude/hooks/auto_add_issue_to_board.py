#!/usr/bin/env python3
"""PostToolUse hook: Auto-add newly created GitHub issues to the project board.

When a `gh issue create` command produces output containing a GitHub issue URL,
this hook automatically adds that issue to the Cross-Repo Wave Plan board
(org project #2).

This enforces charter § Cross-Repo Wave Plan: "New issues created during a wave
must be added to the board immediately."

Input Language:
  Fires on:      PostToolUse Bash
  Matches:       Bash commands containing `gh issue create` with a noorinalabs
                 issue URL in stdout
  Does NOT match: any non-Bash tool, Bash without `gh issue create`, or
                  `gh issue create` whose output lacks a parseable issue URL
  Flag pass-through: stdin JSON is forwarded verbatim to `check()` by the
                     PostToolUse dispatcher (`post_dispatcher.py`)

Exit codes:
  0 — success or not applicable (not a gh issue create, or already handled)
  Non-zero exit does NOT block (PostToolUse hooks are advisory)
"""

import json
import re
import subprocess
import sys

# noorinalabs org project number
PROJECT_NUMBER = 2
ORG = "noorinalabs"


def check(input_data: dict) -> dict | None:
    """Dispatcher-compatible entry point for PostToolUse Bash.

    Returns None when the hook is not applicable; returns a small advisory
    dict (`{"action": "added", "issue_url": ...}`) when the project-board
    add was attempted. The dispatcher treats non-None as advisory only.
    """
    if input_data.get("tool_name", "") != "Bash":
        return None

    command = input_data.get("tool_input", {}).get("command", "")
    if "gh issue create" not in command and "gh issue create" not in command.replace("  ", " "):
        return None

    stdout = input_data.get("tool_output", {}).get("stdout", "")
    if not stdout:
        return None

    url_match = re.search(r"(https://github\.com/noorinalabs/[^/]+/issues/\d+)", stdout)
    if not url_match:
        return None

    issue_url = url_match.group(1)

    try:
        subprocess.run(
            [
                "gh",
                "project",
                "item-add",
                str(PROJECT_NUMBER),
                "--owner",
                ORG,
                "--url",
                issue_url,
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass  # Don't block on failure — advisory hook

    return {"action": "added", "issue_url": issue_url}


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)
    check(input_data)
    sys.exit(0)


if __name__ == "__main__":
    main()
