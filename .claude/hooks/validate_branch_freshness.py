#!/usr/bin/env python3
"""PreToolUse hook: Validate branch freshness before PR creation.

Blocks the gh-pr-create command if the feature branch is behind the base branch.

Input Language:
  Fires on:      PreToolUse Bash
  Matches:       gh-pr-create [--repo {OWNER/REPO} | -R {OWNER/REPO}]
                              [--base {BASE} | -B {BASE}]
                              [--head {[OWNER:]HEAD} | -H {[OWNER:]HEAD}]
                              [other flags]
  (Above shows the literal token sequence: gh, pr, create.)
  Does NOT match: gh pr list, gh pr view, gh pr checks, gh pr edit, gh pr merge,
                  gh issue create. Also does NOT match --base/--head/--repo
                  substrings that appear INSIDE the value of another flag (e.g.
                  inside --body) -- see Bug #118 below.
  Flag pass-through:
    --repo / -R   -> when present, the freshness check uses the GitHub API
                    compare endpoint against that repo (Bug #118 fix). The
                    cwd-based git fetch / merge-base path is bypassed because
                    the cwd repo may be entirely different from the PR target.
    --base / -B   -> base branch on the target repo (defaults to "main").
    --head / -H   -> feature branch on the target repo. Accepts the
                    OWNER:branch cross-fork form; only the branch part is
                    used. When omitted with --repo, the check skips (we
                    cannot infer head reliably from cwd in that case).
                    Without --repo, the cwd path uses HEAD as before.

Tokenization:
  The command is split with shlex.split(..., posix=True) so quoted argument
  values become single tokens. We walk the token list and only treat a token
  as a flag value when the PRECEDING token is the corresponding flag. Same
  pattern as validate_labels (#113) -- guarantees that text inside a
  --body "..." heredoc cannot leak into base/head/repo extraction.

Exit codes:
  0 -- allow (not the matched command, branch is up to date, or check could not run)
  2 -- block (branch is behind base)
"""

import json
import os
import re
import shlex
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from annunaki_log import log_pretooluse_block

_BASE_FLAGS = {"--base", "-B"}
_HEAD_FLAGS = {"--head", "-H"}
_REPO_FLAGS = {"--repo", "-R"}


def _tokenize(command: str) -> list[str] | None:
    """Tokenize a shell command via shlex. Return None on parse failure."""
    try:
        return shlex.split(command, posix=True)
    except ValueError:
        return None


def _is_gh_pr_create(tokens: list[str]) -> bool:
    """Return True if tokens contain a gh pr create invocation."""
    for i in range(len(tokens) - 2):
        if tokens[i] == "gh" and tokens[i + 1] == "pr" and tokens[i + 2] == "create":
            return True
    return False


def _walk_flags(tokens: list[str], wanted: set[str]) -> list[str]:
    """Return values for wanted flag names, only when they appear as flags.

    A token is treated as a wanted-flag value only if the immediately
    preceding token is exactly one of wanted. The --flag=value form is
    also handled. Values inside other flags (e.g. inside the value of
    --body) are ignored because they are a SINGLE shlex token, never
    preceded by a flag from wanted.
    """
    values: list[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in wanted:
            if i + 1 < len(tokens):
                values.append(tokens[i + 1])
                i += 2
                continue
            i += 1
            continue
        matched = False
        for flag in wanted:
            if flag.startswith("--") and tok.startswith(flag + "="):
                values.append(tok[len(flag) + 1 :])
                matched = True
                break
        if matched:
            i += 1
            continue
        i += 1
    return values


def _first_flag_value(command: str, wanted: set[str]) -> str | None:
    """Tokenize and return the first value for any of wanted, or None.

    Falls back to a regex anchored at a shell-token boundary if shlex fails
    (e.g. malformed quote). The regex tries longer flag names first so that
    --repo is preferred over a hypothetical shorter prefix collision.
    """
    tokens = _tokenize(command)
    if tokens is None:
        for flag in sorted(wanted, key=len, reverse=True):
            pattern = rf"(?:^|\s){re.escape(flag)}(?:=|\s+)(\S+)"
            match = re.search(pattern, command)
            if match:
                return match.group(1)
        return None
    values = _walk_flags(tokens, wanted)
    return values[0] if values else None


def extract_base(command: str) -> str:
    """Extract --base / -B value, default to 'main'."""
    return _first_flag_value(command, _BASE_FLAGS) or "main"


def extract_head(command: str) -> str | None:
    """Extract --head / -H value. Strips OWNER: prefix if present."""
    raw = _first_flag_value(command, _HEAD_FLAGS)
    if raw and ":" in raw:
        return raw.split(":", 1)[1]
    return raw


def extract_repo(command: str) -> str | None:
    """Extract --repo / -R OWNER/REPO value, if any."""
    return _first_flag_value(command, _REPO_FLAGS)


def is_branch_fresh_local(base: str) -> bool:
    """cwd-based check: HEAD contains the latest commit from origin/base."""
    try:
        subprocess.run(
            ["git", "fetch", "origin", base],
            capture_output=True,
            text=True,
            timeout=30,
        )
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", f"origin/{base}", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return True


def is_branch_fresh_remote(repo: str, base: str, head: str) -> bool | None:
    """API-based check: behind_by from gh compare endpoint.

    Returns True if head is at-or-ahead of base, False if behind, None if the
    check could not be performed (network error, missing branch, etc.). None
    is treated as "allow" by callers -- same fail-open behavior as the local
    path.
    """
    try:
        result = subprocess.run(
            [
                "gh",
                "api",
                f"repos/{repo}/compare/{base}...{head}",
                "--jq",
                ".behind_by",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return None
        behind = int(result.stdout.strip())
        return behind == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
        return None


def check(input_data: dict) -> dict | None:
    """Check branch freshness. Returns result dict if blocking, None if allowed."""
    tool_name = input_data.get("tool_name", "")
    if tool_name != "Bash":
        return None

    command = input_data.get("tool_input", {}).get("command", "")

    tokens = _tokenize(command)
    if tokens is not None:
        if not _is_gh_pr_create(tokens):
            return None
    else:
        if not re.search(r"\bgh\s+pr\s+create\b", command):
            return None

    base = extract_base(command)
    repo = extract_repo(command)

    if repo:
        head = extract_head(command)
        if not head:
            return None
        fresh = is_branch_fresh_remote(repo, base, head)
        if fresh is None or fresh:
            return None
    else:
        if is_branch_fresh_local(base):
            return None

    target = f"{repo}:{base}" if repo else f"origin/{base}"
    rebase_hint = (
        f"Rebase the head branch onto {target} on the target repo."
        if repo
        else f"Run: git fetch origin && git merge origin/{base}"
    )
    result = {
        "decision": "block",
        "reason": (
            f"BLOCKED: Your branch is behind {target}. "
            f"Merge or rebase before creating a PR.\n"
            f"{rebase_hint}\n\n"
            "This prevents merge conflicts and ensures CI runs against current code."
        ),
    }
    log_pretooluse_block("validate_branch_freshness", command, result["reason"])
    return result


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
