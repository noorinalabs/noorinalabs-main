#!/usr/bin/env python3
"""PreToolUse hook: Auto-set ENVIRONMENT=test before pytest/make test.

Ensures ENVIRONMENT=test is present in the environment for any pytest or
`make test` command. If not already set, prepends ENVIRONMENT=test to the
command.

Exit codes:
  0 — allow (always; modifies command if needed via JSON output)
"""

import json
import re
import sys


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    if tool_name != "Bash":
        sys.exit(0)

    command = input_data.get("tool_input", {}).get("command", "")

    # Strip heredoc content to avoid false positives on text inside --body
    # or issue descriptions that mention "pytest"
    stripped = re.sub(r"<<'?EOF'?\s*\n.*?\nEOF", "", command, flags=re.DOTALL)
    # Also strip single-quoted and double-quoted strings (body text, etc.)
    stripped = re.sub(r"'[^']*'", "''", stripped)
    stripped = re.sub(r'"[^"]*"', '""', stripped)

    # Match pytest/uv run pytest/make test as actual commands, not inside text.
    # Check each sub-command in a chained pipeline.
    is_test_cmd = False
    for segment in re.split(r"\s*(?:&&|\|\||\||;)\s*", stripped):
        seg = segment.strip()
        # Skip env var assignments at the front
        while re.match(r"[A-Za-z_][A-Za-z0-9_]*=\S*\s+", seg):
            seg = re.sub(r"^[A-Za-z_][A-Za-z0-9_]*=\S*\s+", "", seg)
        if re.match(r"(?:uv\s+run\s+)?pytest\b", seg) or re.match(r"make\s+test\b", seg):
            is_test_cmd = True
            break

    if not is_test_cmd:
        sys.exit(0)

    # Check if ENVIRONMENT=test is already set in the command
    if re.search(r"\bENVIRONMENT=test\b", command):
        sys.exit(0)

    # Inform Claude to prepend ENVIRONMENT=test
    result = {
        "decision": "block",
        "reason": (
            "ENVIRONMENT=test is required for test commands but was not found in "
            "the command. Please prepend ENVIRONMENT=test to the command:\n"
            f"  ENVIRONMENT=test {command}"
        ),
    }
    print(json.dumps(result))
    sys.exit(2)


if __name__ == "__main__":
    main()
