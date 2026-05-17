#!/usr/bin/env python3
"""Shared Annunaki error logging utility.

Called by PreToolUse hooks when they block a command, so that blocked
commands appear in the Annunaki error log alongside PostToolUse errors.

Usage in any blocking hook:
    from annunaki_log import log_pretooluse_block
    log_pretooluse_block(hook_name="validate_commit_identity", command=command, reason=reason)

Test-mode suppression (issue #452)
==================================

When `ENVIRONMENT=test` or `NOORIN_HOOK_TEST_MODE=1` is set in the env,
`append_jsonl_record` returns without writing. This prevents the hook
test suite (which exercises matchers against synthetic fixtures like
`gh pr review 42`, `gh issue create --label does-not-exist`) from
polluting the production `.claude/annunaki/errors.jsonl` with hundreds
of fake error entries — pre-#452 a single test-suite run produced ~293
entries (76% of the log's content as captured 2026-05-16).

`ENVIRONMENT=test` is the charter-required env var for pytest (set by
`auto_set_env_test.py` PreToolUse hook); using it as the suppression
signal means no conftest.py setup is needed — every existing test
invocation already sets it. `NOORIN_HOOK_TEST_MODE` is provided as an
explicit opt-in for non-pytest harnesses (CI matrix jobs, ad-hoc shell
fixtures) that need annunaki suppression without claiming `ENVIRONMENT=test`.
"""

import json
import os
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ERRORS_FILE = REPO_ROOT / ".claude" / "annunaki" / "errors.jsonl"


def _is_test_mode() -> bool:
    """True iff annunaki should suppress writes (test harness running).

    Returns True when EITHER:
      - `ENVIRONMENT=test` is set (charter-required for pytest)
      - `NOORIN_HOOK_TEST_MODE=1` is set (explicit non-pytest opt-in)

    Empty / unset / any other value → False (production fall-through).
    """
    if os.environ.get("ENVIRONMENT", "") == "test":
        return True
    if os.environ.get("NOORIN_HOOK_TEST_MODE", "") == "1":
        return True
    return False


def append_jsonl_record(path: Path, record: dict) -> None:
    """Append one JSONL record. Skips empty records and guarantees exactly
    one trailing newline per line — never a bare blank line. Shared by
    annunaki_log.py and annunaki_monitor.py so writer hardening stays in
    one place.

    Test-mode suppression: when `_is_test_mode()` is True (ENVIRONMENT=test
    or NOORIN_HOOK_TEST_MODE=1), the write is skipped entirely. This is the
    #452 fix — the hook test suite pollutes the production error log with
    ~293 fixture entries per run otherwise.
    """
    if not isinstance(record, dict) or not record:
        return
    if _is_test_mode():
        return
    # json.dumps with default settings does not emit newlines, so the
    # serialized form is guaranteed single-line. Strip any stray ones
    # defensively anyway.
    line = json.dumps(record, ensure_ascii=False).replace("\n", " ").strip()
    if not line:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass  # Never fail the hook


def log_pretooluse_block(
    hook_name: str, command: str, reason: str, tool_name: str = "Bash"
) -> None:
    """Append a PreToolUse block event to the Annunaki error log."""
    record = {
        "timestamp": datetime.now(UTC).isoformat(),
        "type": "pretooluse_block",
        "hook": hook_name,
        "tool_name": tool_name,
        "command": command[:500],
        "exit_code": None,
        "matched_patterns": [f"hook_block:{hook_name}"],
        "error_lines": [reason[:500]],
        "stderr_excerpt": "",
    }
    append_jsonl_record(ERRORS_FILE, record)


def log_posttooluse_event(
    hook_name: str, command: str, reason: str, tool_name: str = "Bash"
) -> None:
    """Append a PostToolUse non-blocking event to the Annunaki error log.

    PostToolUse hooks cannot block the tool call (it has already run), so
    they don't "block" — they record events that need follow-up. Used by
    hooks like `post_wave_kickoff_comment` when they cannot complete their
    post-action work (e.g., scope row missing, gh CLI failure) and want a
    visible signal in the Annunaki sweep without raising a failure on the
    underlying tool call.
    """
    record = {
        "timestamp": datetime.now(UTC).isoformat(),
        "type": "posttooluse_event",
        "hook": hook_name,
        "tool_name": tool_name,
        "command": command[:500],
        "exit_code": None,
        "matched_patterns": [f"hook_event:{hook_name}"],
        "error_lines": [reason[:500]],
        "stderr_excerpt": "",
    }
    append_jsonl_record(ERRORS_FILE, record)
