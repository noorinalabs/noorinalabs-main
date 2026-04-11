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


def check(input_data: dict) -> dict | None:
    """Check for ENVIRONMENT=test on test commands. Returns result dict if blocking, None if allowed."""
    tool_name = input_data.get("tool_name", "")
    if tool_name != "Bash":
        return None

    command = input_data.get("tool_input", {}).get("command", "")

    is_test_cmd = bool(re.search(r"\bpytest\b", command) or re.search(r"\bmake\s+test\b", command))

    if not is_test_cmd:
        return None

    if re.search(r"\bENVIRONMENT=test\b", command):
        return None

    return {
        "decision": "block",
        "reason": (
            "ENVIRONMENT=test is required for test commands but was not found in "
            "the command. Please prepend ENVIRONMENT=test to the command:\n"
            f"  ENVIRONMENT=test {command}"
        ),
    }


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
