#!/usr/bin/env python3
"""PreToolUse hook: Auto-set ENVIRONMENT=test before pytest/make test.

Ensures ENVIRONMENT=test is present in the environment for any pytest or
`make test` command. If not already set, blocks with instructions to prepend
ENVIRONMENT=test to the command.

Input Language:
  Fires on:      PreToolUse Bash
  Matches:       A command (possibly chained with &&/||/|/;) in which at least
                 one segment's effective argv[0] is one of:
                   - pytest
                   - python -m pytest
                   - uv run pytest
                   - make test
                 Leading `VAR=value` env assignments are stripped before
                 inspecting argv[0], so `FOO=bar pytest` still matches.
  Does NOT match:
                 - gh pr comment --body "... pytest ..."   (gh is never a test runner)
                 - gh issue create --body "... make test ..."
                 - gh pr review --body "pytest failed"
                 - git log --grep pytest
                 - echo "run pytest"                       (literal inside quotes)
                 - cat README.md | grep "make test"
                 - any command whose first argv is not a test-runner token
  Flag pass-through:
                 - If ENVIRONMENT=test already appears as a leading env
                   assignment on the matched segment, allow through.

Exit codes:
  0 — allow (not a test command, or already has ENVIRONMENT=test)
  2 — block (test command missing ENVIRONMENT=test)
"""

import json
import re
import shlex
import sys

# Segments of a matched test-runner invocation. Each tuple is matched left-to-right
# against the post-env-strip tokens of a command segment.
_TEST_RUNNER_PREFIXES: tuple[tuple[str, ...], ...] = (
    ("pytest",),
    ("python", "-m", "pytest"),
    ("python3", "-m", "pytest"),
    ("uv", "run", "pytest"),
    ("make", "test"),
)


def _split_segments(command: str) -> list[str]:
    """Split a command string on shell chain operators (&&, ||, |, ;)."""
    return re.split(r"\s*(?:&&|\|\||\||;)\s*", command)


def _strip_leading_env(tokens: list[str]) -> tuple[list[str], bool]:
    """Strip leading VAR=value tokens. Return (remaining_tokens, had_env_test)."""
    had_env_test = False
    i = 0
    env_re = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
    while i < len(tokens) and env_re.match(tokens[i]):
        if tokens[i] == "ENVIRONMENT=test":
            had_env_test = True
        i += 1
    return tokens[i:], had_env_test


def _matches_test_runner(tokens: list[str]) -> bool:
    """Check if tokens start with any known test-runner prefix."""
    for prefix in _TEST_RUNNER_PREFIXES:
        if len(tokens) >= len(prefix) and tuple(tokens[: len(prefix)]) == prefix:
            return True
    return False


def _segment_is_unenvironmented_test(segment: str) -> bool:
    """Return True if this segment is a test-runner invocation lacking ENVIRONMENT=test."""
    segment = segment.strip()
    if not segment:
        return False
    try:
        tokens = shlex.split(segment, posix=True)
    except ValueError:
        # Unbalanced quotes etc — fall back to "no match" rather than over-firing.
        return False
    if not tokens:
        return False
    remaining, had_env_test = _strip_leading_env(tokens)
    if not _matches_test_runner(remaining):
        return False
    return not had_env_test


def check(input_data: dict) -> dict | None:
    """Check for ENVIRONMENT=test on test commands.

    Returns result dict if blocking, None if allowed.
    """
    tool_name = input_data.get("tool_name", "")
    if tool_name != "Bash":
        return None

    command = input_data.get("tool_input", {}).get("command", "")
    if not command:
        return None

    for segment in _split_segments(command):
        if _segment_is_unenvironmented_test(segment):
            return {
                "decision": "block",
                "reason": (
                    "ENVIRONMENT=test is required for test commands but was not found in "
                    "the command. Please prepend ENVIRONMENT=test to the command:\n"
                    f"  ENVIRONMENT=test {command}"
                ),
            }

    return None


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
