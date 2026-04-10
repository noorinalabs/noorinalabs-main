#!/usr/bin/env python3
"""PreToolUse hook: Validate branch freshness before PR creation.

Blocks `gh pr create` if the feature branch is behind the base branch.

Exit codes:
  0 — allow (not gh pr create, or branch is up to date)
  2 — block (branch is behind base)
"""

import json
import re
import subprocess
import sys


def get_base_branch(command: str) -> str:
    """Extract --base flag value, default to 'main'."""
    match = re.search(r"--base\s+[\"']?(\S+)[\"']?", command)
    if match:
        return match.group(1)
    return "main"


def extract_cwd_from_command(command: str) -> str | None:
    """Extract the working directory from a command with a leading 'cd <dir> &&'.

    Worktree agents commonly prefix commands with 'cd /tmp/agent-name &&'.
    This function detects that pattern and returns the target directory.
    """
    match = re.match(r"cd\s+([^\s;|&]+)\s*&&", command.strip())
    if match:
        return match.group(1).strip("\"'")
    return None


def resolve_git_dir(cwd: str | None = None) -> str | None:
    """Resolve the git toplevel directory, respecting worktree context.

    If cwd is provided, runs git from that directory. Otherwise uses
    the process CWD. Returns the toplevel path or None on failure.
    """
    try:
        cmd = ["git"]
        if cwd:
            cmd.extend(["-C", cwd])
        cmd.extend(["rev-parse", "--show-toplevel"])
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def is_branch_fresh(base: str, git_dir: str | None = None) -> bool:
    """Check if HEAD contains the latest commit from origin/base.

    When git_dir is provided, all git commands run with -C <git_dir>
    to respect worktree context.
    """
    try:
        git_prefix = ["git"]
        if git_dir:
            git_prefix.extend(["-C", git_dir])

        # Fetch latest from origin
        subprocess.run(
            [*git_prefix, "fetch", "origin", base],
            capture_output=True,
            text=True,
            timeout=30,
        )
        # Check if origin/base is an ancestor of HEAD
        result = subprocess.run(
            [*git_prefix, "merge-base", "--is-ancestor", f"origin/{base}", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        # If we can't check, allow
        return True


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    if tool_name != "Bash":
        sys.exit(0)

    command = input_data.get("tool_input", {}).get("command", "")

    if not re.search(r"\bgh\s+pr\s+create\b", command):
        sys.exit(0)

    base = get_base_branch(command)

    # Detect worktree CWD: check for 'cd <dir> &&' prefix in the command,
    # then resolve the git toplevel from that directory.
    cmd_cwd = extract_cwd_from_command(command)
    git_dir = resolve_git_dir(cmd_cwd)

    if is_branch_fresh(base, git_dir=git_dir):
        sys.exit(0)

    result = {
        "decision": "block",
        "reason": (
            f"BLOCKED: Your branch is behind origin/{base}. "
            f"Merge or rebase before creating a PR.\n"
            f"Run: git fetch origin && git merge origin/{base}\n\n"
            "This prevents merge conflicts and ensures CI runs against current code."
        ),
    }
    print(json.dumps(result))
    sys.exit(2)


if __name__ == "__main__":
    main()
