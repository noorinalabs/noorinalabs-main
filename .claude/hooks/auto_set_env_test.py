#!/usr/bin/env python3
"""PreToolUse hook: Auto-set ENVIRONMENT=test before test runner commands.

Ensures ENVIRONMENT=test is present in the environment for actual test
execution commands (pytest, vitest, npm test, make test, etc.). Only matches
commands in executable position — not strings that happen to contain test
runner names in arguments, commit messages, or comment bodies.

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

    # Only match actual test execution commands, not strings that happen to
    # contain "pytest" or "test" in arguments, commit messages, or comment
    # bodies.  We require the test runner to appear in command position: at
    # the start of the line, or after a shell operator (&&, ||, ;, |).
    # Optional leading env-var assignments (FOO=bar) are allowed before the
    # command word.
    _CMD_POS = r"(?:^|&&|\|\||[;|])\s*(?:\w+=\S*\s+)*"
    _TEST_RUNNERS = [
        r"pytest\b",                  # pytest / uv run pytest (handled via prefix)
        r"python\s+-m\s+pytest\b",    # python -m pytest
        r"uv\s+run\s+pytest\b",       # uv run pytest
        r"make\s+test\b",             # make test
        r"npm\s+test\b",              # npm test
        r"npx\s+vitest\b",            # npx vitest
        r"vitest\b",                  # vitest
    ]
    _PATTERN = _CMD_POS + r"(?:" + "|".join(_TEST_RUNNERS) + r")"
    is_test_cmd = bool(re.search(_PATTERN, command))

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
