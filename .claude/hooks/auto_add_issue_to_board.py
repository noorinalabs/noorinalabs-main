#!/usr/bin/env python3
"""PostToolUse hook: Auto-add newly created GitHub issues to the project board.

When a `gh issue create` command produces output containing a GitHub issue URL,
this hook automatically adds that issue to the Cross-Repo Wave Plan board
(org project #2).

This enforces charter § Cross-Repo Wave Plan: "New issues created during a wave
must be added to the board immediately."

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


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    if tool_name != "Bash":
        sys.exit(0)

    command = input_data.get("tool_input", {}).get("command", "")

    # Only trigger on gh issue create commands
    if "gh issue create" not in command and "gh issue create" not in command.replace("  ", " "):
        sys.exit(0)

    # Extract the issue URL from tool output (stdout)
    stdout = input_data.get("tool_output", {}).get("stdout", "")
    if not stdout:
        sys.exit(0)

    # gh issue create outputs the URL on the last line
    url_match = re.search(
        r"(https://github\.com/noorinalabs/[^/]+/issues/\d+)", stdout
    )
    if not url_match:
        sys.exit(0)

    issue_url = url_match.group(1)

    # Add to project board
    try:
        subprocess.run(
            [
                "gh", "project", "item-add", str(PROJECT_NUMBER),
                "--owner", ORG,
                "--url", issue_url,
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass  # Don't block on failure — advisory hook

    sys.exit(0)


if __name__ == "__main__":
    main()
