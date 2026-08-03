#!/usr/bin/env python3
"""PreToolUse hook: Block commits with local paths in package-lock.json.

Scans staged package-lock.json files for /tmp/ or file:/ references that are
local worktree artifacts and break CI.

Exit codes:
  0 — allow (not a git commit, or no local paths found)
  2 — block (local paths detected in staged lockfiles)
"""

import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hook_main import run_blocking
from annunaki_log import log_pretooluse_block

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib")
sys.path.insert(0, os.path.abspath(_LIB_DIR))
from git import run_git  # noqa: E402

# `run_git` uses `check=True` (raises `CalledProcessError` on a non-zero exit)
# — this file's pre-#1121 hand-rolled calls instead inspected `.returncode`
# and fell through to an empty result. Both `except` clauses below catch
# `CalledProcessError` alongside the original `TimeoutExpired`/
# `FileNotFoundError` to preserve that exact fail-open behavior (main#1121).
_GIT_ERRORS = (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError)


def get_staged_lockfiles() -> list[str]:
    """Return paths of staged package-lock.json files."""
    try:
        stdout = run_git(["diff", "--cached", "--name-only", "--diff-filter=ACM"], timeout=10)
    except _GIT_ERRORS:
        return []
    return [f for f in stdout.strip().splitlines() if f.endswith("package-lock.json")]


def check_lockfile(path: str) -> list[str]:
    """Check a staged lockfile for local path references. Returns offending lines."""
    offending = []
    try:
        stdout = run_git(["show", f":{path}"], timeout=10)
    except _GIT_ERRORS:
        return []
    for i, line in enumerate(stdout.splitlines(), 1):
        if re.search(r"/tmp/|file:/", line):
            offending.append(f"  {path}:{i}: {line.strip()}")
    return offending


def check(input_data: dict) -> dict | None:
    """Check lockfiles for local paths. Returns result dict if blocking, None if allowed."""
    tool_name = input_data.get("tool_name", "")
    if tool_name != "Bash":
        return None

    command = input_data.get("tool_input", {}).get("command", "")

    if not re.search(r"\bgit\b.*\bcommit\b", command):
        return None

    lockfiles = get_staged_lockfiles()
    if not lockfiles:
        return None

    all_offending = []
    for lf in lockfiles:
        all_offending.extend(check_lockfile(lf))

    if not all_offending:
        return None

    details = "\n".join(all_offending)
    result = {
        "decision": "block",
        "reason": (
            "BLOCKED: Staged package-lock.json contains local path references "
            "(/tmp/ or file:/) that will break CI.\n"
            f"Offending lines:\n{details}\n\n"
            "Fix: Remove the local dependency references and regenerate the lockfile "
            "with `npm install` using the published package version."
        ),
    }
    log_pretooluse_block("validate_lockfile_paths", command, result["reason"])
    return result


def main() -> None:
    run_blocking(check, "validate_lockfile_paths")


if __name__ == "__main__":
    main()
