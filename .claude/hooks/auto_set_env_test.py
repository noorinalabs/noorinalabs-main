#!/usr/bin/env python3
"""PreToolUse hook: Auto-set ENVIRONMENT=test before pytest/make test.

Ensures ENVIRONMENT=test is present in the environment for any pytest or
`make test` command. If not already set, blocks with a corrected command
that prepends ENVIRONMENT=test to the test-bearing segment(s).

Input Language
==============

Fires on:
    PreToolUse Bash

Matches (blocks if ENVIRONMENT=test missing on the test segment):
    Any Bash command containing a real test-runner invocation detected
    by the regexes `\\bpytest\\b` or `\\bmake\\s+test\\b`. The command is
    split on shell separators (`&&`, `||`, `;`, `|`) into segments; each
    test-bearing segment is checked independently for a leading
    `ENVIRONMENT=test` env-block.

    Typical matched forms:
        pytest tests/
        uv run pytest
        python -m pytest
        make test
        DEBUG=1 pytest tests/                  (env prefix preserved)
        cd /path && pytest tests/              (chain — env must be on pytest segment)
        pytest tests/ && pytest tests-other/   (chain — env required on BOTH segments)

Does NOT match (short-circuit skips — #114 fix):
    1. Command whose effective argv[0] is `gh` — `gh` is a GitHub API
       client, never a test runner. `ENVIRONMENT=test gh pr comment ...`
       is nonsensical. Skip even if pytest/make-test text appears inside
       the command (almost always inside --body / --title content).
    2. Command containing a `--body` or `--body-file` flag — structured
       body content almost always contains user-supplied text that may
       mention pytest or `make test` without invoking them. This skip is
       intentionally broad: a non-gh tool like
       `some-tool --body "$(cat pytest.txt)"` is also skipped. The cost
       of a rare false negative on an exotic non-gh tool is lower than
       the cost of blocking every review / issue / comment that
       references pytest.

Both short-circuits run BEFORE the pytest/make-test segment scan and
apply to the WHOLE command (not per-segment).

Detection order:
    1. Strip leading `VAR=value` tokens from the command for argv[0] check.
    2. If the next token is `gh`, ALLOW (return None).
    3. If the command contains `--body` or `--body-file`, ALLOW.
    4. Split on `&&`/`||`/`;`/`|` into segments.
    5. For each segment containing `\\bpytest\\b` or `\\bmake\\s+test\\b`,
       require `\\bENVIRONMENT=test\\b` in that segment's leading env-block;
       else BLOCK with a per-segment-rewritten suggestion.

Per-segment env-block check (the #476 silent-bypass fix):
    `ENVIRONMENT=test cd /x && pytest tests/` does NOT pass — even though
    the env var appears in the command, it lives on the `cd` segment, not
    on the pytest segment. Shell semantics apply env assignments only to
    the immediately-following program in the same segment.

Exit codes:
    0 — allow (not a Bash tool, or skip condition met, or every test
        segment already has ENVIRONMENT=test in its leading env-block)
    2 — block (at least one test segment is missing ENVIRONMENT=test)

Enforcement artifact for: noorinalabs/noorinalabs-main#114, #476
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from annunaki_log import log_pretooluse_block  # noqa: E402

# Matches a leading `VAR=value` token (simple unquoted value).
_ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=\S*\s+")

# `--body` or `--body-file` as a standalone flag. The trailing lookahead
# prevents matching `--body-foo` but still matches both `--body x`,
# `--body=x`, and `--body-file path`.
_BODY_FLAG = re.compile(r"(?<![\w-])--body(?:-file)?(?=[\s=]|$)")

# Shell separators we split on. Order matters in the alternation: longer
# tokens first so `&&` isn't mis-split as two `|`s by the `|` alternative.
# Captured group preserves the separator in the split output so we can
# splice segments back together with original glue.
_SEPARATORS = re.compile(r"(\s*(?:&&|\|\||;|\|)\s*)")

# Test-runner detection: pytest OR `make test`.
_TEST_RUNNER = re.compile(r"\bpytest\b|\bmake\s+test\b")

# The literal env-var we require.
_ENV_TOKEN = re.compile(r"\bENVIRONMENT=test\b")


def _strip_leading_env(command: str) -> str:
    """Remove leading `VAR=value ` assignments, return the remainder."""
    while True:
        m = _ENV_ASSIGN.match(command)
        if not m:
            return command
        command = command[m.end() :]


def _is_gh_invocation(command: str) -> bool:
    """True if the effective argv[0] (after env assignments) is `gh`."""
    stripped = _strip_leading_env(command).lstrip()
    if not stripped:
        return False
    token = stripped.split(None, 1)[0]
    return token == "gh"


def _has_body_flag(command: str) -> bool:
    """True if the command contains a --body or --body-file flag."""
    return bool(_BODY_FLAG.search(command))


def _split_segments(command: str) -> list[str]:
    """Split command on `&&`/`||`/`;`/`|`, preserving separators as
    alternating list entries: [seg0, sep0, seg1, sep1, ..., segN].

    The result always has odd length: segments at even indices, separators
    at odd indices. A command with no separators returns a single-element
    list [command].
    """
    return _SEPARATORS.split(command)


def _segment_has_env_in_leading_block(segment: str) -> bool:
    """True if `ENVIRONMENT=test` is in the LEADING env-block of segment.

    The leading env-block is the sequence of `VAR=value ` tokens at the
    start of the segment (after stripping surrounding whitespace). This
    is the only position where a shell env assignment applies to the
    segment's program.
    """
    stripped = segment.lstrip()
    consumed = stripped[: len(stripped) - len(_strip_leading_env(stripped))]
    return bool(_ENV_TOKEN.search(consumed))


def _is_test_segment(segment: str) -> bool:
    """True if segment contains pytest or `make test` as a real invocation."""
    return bool(_TEST_RUNNER.search(segment))


def _prepend_env_to_segment(segment: str) -> str:
    """Return segment with `ENVIRONMENT=test ` inserted before its first
    real (non-env-assignment, non-whitespace) token.

    Preserves any existing leading env-block (e.g. `DEBUG=1 pytest` →
    `DEBUG=1 ENVIRONMENT=test pytest`) and preserves the segment's
    leading whitespace exactly so splicing back into the chain doesn't
    re-shape the original command's formatting.
    """
    leading_ws_len = len(segment) - len(segment.lstrip())
    leading_ws = segment[:leading_ws_len]
    body = segment[leading_ws_len:]
    body_after_env = _strip_leading_env(body)
    env_block = body[: len(body) - len(body_after_env)]
    return f"{leading_ws}{env_block}ENVIRONMENT=test {body_after_env}"


def _rewrite_command(command: str) -> str:
    """Splice ENVIRONMENT=test onto each test-bearing segment that lacks it."""
    parts = _split_segments(command)
    for i in range(0, len(parts), 2):
        seg = parts[i]
        if _is_test_segment(seg) and not _segment_has_env_in_leading_block(seg):
            parts[i] = _prepend_env_to_segment(seg)
    return "".join(parts)


def check(input_data: dict) -> dict | None:
    """Check for ENVIRONMENT=test on test commands.

    Returns result dict if blocking, None if allowed.
    """
    tool_name = input_data.get("tool_name", "")
    if tool_name != "Bash":
        return None

    command = input_data.get("tool_input", {}).get("command", "")

    # Short-circuit 1: gh subcommands are never test runners.
    if _is_gh_invocation(command):
        return None

    # Short-circuit 2: --body/--body-file flag implies structured content.
    if _has_body_flag(command):
        return None

    parts = _split_segments(command)
    test_segments = [parts[i] for i in range(0, len(parts), 2) if _is_test_segment(parts[i])]
    if not test_segments:
        return None

    if all(_segment_has_env_in_leading_block(seg) for seg in test_segments):
        return None

    rewritten = _rewrite_command(command)
    return {
        "decision": "block",
        "reason": (
            "ENVIRONMENT=test is required for test commands but was not found in "
            "the leading env-block of each test-bearing segment. Shell env "
            "assignments only apply to the immediately-following program in the "
            "same segment, so chains like `cd /x && pytest` need the env on the "
            "pytest segment, not at the start of the whole command. Suggested "
            "command:\n"
            f"  {rewritten}"
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
        command = input_data.get("tool_input", {}).get("command", "")
        log_pretooluse_block(
            "auto_set_env_test",
            command,
            result["reason"],
            tool_name="Bash",
        )
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
