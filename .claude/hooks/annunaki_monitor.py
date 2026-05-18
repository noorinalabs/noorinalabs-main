#!/usr/bin/env python3
"""PostToolUse hook: Annunaki error monitor.

Fires after every Bash tool call. Inspects the output for error signals
(non-zero exit code, stderr content, common error patterns) and appends
each error to .claude/annunaki/errors.jsonl for later analysis by
/annunaki-attack.

Input Language:
  Fires on:      PostToolUse Bash
  Matches:       Bash with non-zero exit_code OR stdout/stderr matching any
                 ERROR_PATTERNS regex (Traceback, fatal:, ModuleNotFoundError,
                 etc.) and NOT matching IGNORE_PATTERNS
  Does NOT match: any non-Bash tool, command-text containing grep-for-error /
                  --error flags / error-named paths (false-positive guards),
                  silent-boolean-test idioms (`[`, `[[`, `test`, `grep -q`,
                  `pgrep`, `pkill`, `which`, `command -v`, `diff --quiet`,
                  `git diff --quiet`, `if [...]`) when their ONLY error signal
                  is a non-zero exit code, session-dedup hits
  Flag pass-through: stdin JSON is forwarded verbatim to `check()` by the
                     PostToolUse dispatcher (`post_dispatcher.py`)

Exit codes:
  0 — always (advisory hook, never blocks)
"""

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from annunaki_log import append_jsonl_record

# Where we log errors — JSONL for easy dedup and processing
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ERRORS_FILE = REPO_ROOT / ".claude" / "annunaki" / "errors.jsonl"

# Session-level dedup: skip errors we've already logged this session
_seen_hashes: set = set()

# Patterns that indicate errors even when exit code is 0
ERROR_PATTERNS = [
    re.compile(r"^error\b", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^fatal:", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^FAILED", re.MULTILINE),
    re.compile(r"Traceback \(most recent call last\)", re.MULTILINE),
    re.compile(r"^E\s+\w+Error:", re.MULTILINE),  # pytest-style
    re.compile(r"panic:", re.MULTILINE),
    re.compile(r"ENOENT|EACCES|EPERM", re.MULTILINE),
    re.compile(r"command not found", re.IGNORECASE | re.MULTILINE),
    re.compile(r"No such file or directory", re.MULTILINE),
    re.compile(r"Permission denied", re.MULTILINE),
    re.compile(r"ModuleNotFoundError:", re.MULTILINE),
    re.compile(r"ImportError:", re.MULTILINE),
    re.compile(r"SyntaxError:", re.MULTILINE),
    re.compile(r"TypeError:|ValueError:|KeyError:|AttributeError:", re.MULTILINE),
    re.compile(r"npm ERR!", re.MULTILINE),
    re.compile(r"exit status [1-9]", re.MULTILINE),
    re.compile(r"failed with exit code", re.IGNORECASE | re.MULTILINE),
]

# Patterns to IGNORE (not real errors)
IGNORE_PATTERNS = [
    re.compile(r"grep.*error", re.IGNORECASE),  # grep searching for "error"
    re.compile(r"--error", re.IGNORECASE),  # flags containing "error"
    re.compile(r"error_log|error\.log|errorhandl", re.IGNORECASE),  # filenames
]

# Silent-boolean-test idioms (#474): commands whose ONLY failure signal is a
# non-zero exit code with empty stdout/stderr — by design, not an error.
# After #473 closed the silent-failure blind spot, these idioms became noise.
# Apply ONLY when matched_patterns is exactly ["exit_code=..."] (no stdout or
# stderr pattern matched) — pattern matches always win, ignore-on-silent-exit
# never suppresses a real error.
SILENT_BOOLEAN_TEST_PATTERNS = [
    re.compile(r"^\s*\["),  # POSIX `[ ... ]` test
    re.compile(r"^\s*\[\["),  # Bash `[[ ... ]]` test
    re.compile(r"^\s*test\b"),  # explicit `test` builtin
    re.compile(r"\bgrep\s+-[a-zA-Z]*q"),  # grep -q (and -qE, -qi, etc.)
    re.compile(r"^\s*(pgrep|pkill)\b"),  # process find/signal, exit 1 on no match
    re.compile(r"^\s*(which|command\s+-v)\b"),  # which/command -v not-found
    re.compile(r"\bdiff\s+--quiet\b"),  # diff --quiet: exit 1 on differences
    re.compile(r"\bgit\s+diff\s+--quiet\b"),  # git diff --quiet: same
    re.compile(r"^\s*if\s+\["),  # `if [ ... ]; then ...; fi` whole-conditional
    re.compile(r"^\s*if\s+\[\["),  # `if [[ ... ]]; then ...; fi`
]


def _is_silent_boolean_test(command: str) -> bool:
    """Return True if command matches a documented silent-boolean-test idiom.

    Caller must additionally verify that the ONLY failure signal is exit_code
    (no stdout/stderr pattern match) — pattern matches always take precedence.
    """
    for pattern in SILENT_BOOLEAN_TEST_PATTERNS:
        if pattern.search(command):
            return True
    return False


def _extract_error_lines(text: str, max_lines: int = 10) -> list[str]:
    """Extract the most relevant error lines from output."""
    lines = text.strip().splitlines()
    error_lines = []
    for i, line in enumerate(lines):
        for pattern in ERROR_PATTERNS:
            if pattern.search(line):
                # Grab this line and up to 2 lines of context after
                context_end = min(i + 3, len(lines))
                error_lines.extend(lines[i:context_end])
                break
        if len(error_lines) >= max_lines:
            break
    return error_lines[:max_lines]


def _should_ignore(command: str, output: str) -> bool:
    """Return True if this looks like a false positive."""
    for pattern in IGNORE_PATTERNS:
        if pattern.search(command):
            return True
    return False


def check(input_data: dict) -> dict | None:
    """Dispatcher-compatible entry point for PostToolUse Bash.

    Returns None when no error is detected (or input doesn't apply); returns
    an advisory dict describing the logged record when an error is appended
    to the JSONL log. The dispatcher treats non-None as advisory only.
    """
    if input_data.get("tool_name", "") != "Bash":
        return None

    command = input_data.get("tool_input", {}).get("command", "")
    # Claude Code's PostToolUse contract passes `tool_response`. Legacy hook
    # fixtures used `tool_output`; we accept both so old tests still pass.
    tool_output = input_data.get("tool_response") or input_data.get("tool_output", {})
    stdout = tool_output.get("stdout", "")
    stderr = tool_output.get("stderr", "")
    exit_code = tool_output.get("exit_code", 0)

    combined_output = f"{stdout}\n{stderr}".strip()

    if _should_ignore(command, combined_output):
        return None

    is_error = False
    matched_patterns: list[str] = []

    # Check exit_code first so silent failures (commands that exit non-zero
    # with no stdout/stderr — `false`, `kill -9 $$`, exit-1-no-output) are
    # captured. Previously an empty-output early-return short-circuited this
    # branch and dropped them on the floor (#472).
    if exit_code and exit_code != 0:
        is_error = True
        matched_patterns.append(f"exit_code={exit_code}")

    if combined_output:
        if stderr and stderr.strip():
            for pattern in ERROR_PATTERNS:
                if pattern.search(stderr):
                    is_error = True
                    matched_patterns.append(f"stderr:{pattern.pattern}")
                    break

        for pattern in ERROR_PATTERNS:
            if pattern.search(stdout):
                is_error = True
                matched_patterns.append(f"stdout:{pattern.pattern}")
                break

    if not is_error:
        return None

    # #474 silent-boolean-test filter: when the ONLY signal is a non-zero
    # exit code (no stderr/stdout pattern matched), suppress documented
    # boolean-test idioms whose failure branch is by-design. Stderr/stdout
    # pattern matches always win — a `[ -f x ]` that somehow emits a real
    # Traceback still logs.
    if matched_patterns == [f"exit_code={exit_code}"] and _is_silent_boolean_test(command):
        return None

    error_lines = _extract_error_lines(combined_output)

    dedup_input = command[:200] + "|||" + "\n".join(error_lines)[:500]
    dedup_hash = hashlib.md5(dedup_input.encode("utf-8")).hexdigest()
    if dedup_hash in _seen_hashes:
        return None
    _seen_hashes.add(dedup_hash)

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "command": command[:500],
        "exit_code": exit_code,
        "matched_patterns": matched_patterns[:5],
        "error_lines": error_lines,
        "stderr_excerpt": stderr[:300] if stderr else "",
        "_dedup_hash": dedup_hash,
    }

    append_jsonl_record(ERRORS_FILE, record)

    return {"action": "logged", "dedup_hash": dedup_hash}


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)
    check(input_data)
    sys.exit(0)


if __name__ == "__main__":
    main()
