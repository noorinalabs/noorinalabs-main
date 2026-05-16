#!/usr/bin/env python3
"""Shared Annunaki error logging utility.

Called by PreToolUse hooks when they block a command, so that blocked
commands appear in the Annunaki error log alongside PostToolUse errors.

Usage in any blocking hook:
    from annunaki_log import log_pretooluse_block
    log_pretooluse_block(hook_name="validate_commit_identity", command=command, reason=reason)
"""

import json
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ERRORS_FILE = REPO_ROOT / ".claude" / "annunaki" / "errors.jsonl"


def append_jsonl_record(path: Path, record: dict) -> None:
    """Append one JSONL record. Skips empty records and guarantees exactly
    one trailing newline per line — never a bare blank line. Shared by
    annunaki_log.py and annunaki_monitor.py so writer hardening stays in
    one place."""
    if not isinstance(record, dict) or not record:
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


def log_pretooluse_diagnostic(
    hook_name: str,
    command: str,
    diagnostic: dict,
    tool_name: str = "Bash",
) -> None:
    """Append a structured diagnostic record alongside a PreToolUse block.

    Distinct from `log_pretooluse_block` because the block-record schema is
    pinned by /annunaki and downstream parsers; this side-channel carries
    per-hook structured forensics without touching that contract. Used
    today by `enforce_librarian_consulted` to capture cwd / sentinel path /
    sentinel mtime / transcript path on every block so #429-style
    "why did it block?" questions are answerable from logs alone.

    Keys in `diagnostic` are hook-specific; values must be JSON-safe
    primitives (no datetime, no Path — stringify upstream). The record's
    top-level `type` is `pretooluse_diagnostic` so /annunaki can filter
    these out of error counts.
    """
    record = {
        "timestamp": datetime.now(UTC).isoformat(),
        "type": "pretooluse_diagnostic",
        "hook": hook_name,
        "tool_name": tool_name,
        "command": command[:500],
        "diagnostic": diagnostic,
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
