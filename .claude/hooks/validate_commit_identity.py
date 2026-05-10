#!/usr/bin/env python3
"""PreToolUse hook: Validate git commit identity flags.

Ensures every `git commit` command includes `-c user.name=` and `-c user.email=`
flags matching a roster member from the charter's Commit Identity table.

Parent+child roster merge (#112 part a):
  When the target repo (either the local repo or a `cd <path>` target) is a
  child of another git repo that itself has `.claude/team/roster.json`, the
  parent roster is loaded and merged with the child roster. Same-name entries
  in the child override the parent (child wins). Walk-up is limited to ONE
  level to avoid false positives in nested `code/` trees. This lets org-level
  coordinators commit in child repos without duplicating their entries into
  every child `roster.json`.

Input Language
==============

Fires on:      PreToolUse Bash
Matches:       git [-c k=v ...] [-C path] [other globals] commit [args]
               (any segment in the compound command — split on ;, &&, ||, |;
               leading KEY=value env-vars are stripped)
Does NOT match: prose containing the literal "git commit" inside heredoc
                bodies, --body / --body-file argument values, $(cat <<'EOF' …)
                command substitutions. Tokenized via shlex; the matcher only
                fires on actual command-position git invocations.

Flag pass-through:
    -c user.name=<value>   → required, validated against roster
    -c user.email=<value>  → required, validated against roster
    cd <path> && git ...   → loads <path>'s merged roster (cross-repo commit)

Substring-bug history fixed by tokenization:
    #226 — unquoted -c user.email=val no longer slurps to EOL
    #188 — nested $(cat <<'EOF' ... EOF) no longer mangles the parser
    Both root in regex-against-raw-string parsing; switched to shlex tokens.

Exit codes:
  0 — allow (not a git commit, or identity is valid)
  2 — block (missing or invalid identity flags)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _shell_parse import (  # noqa: E402
    extract_dash_c_pairs,
    find_git_subcommand,
    iter_command_segments,
    strip_heredocs,
    tokenize,
)
from annunaki_log import log_pretooluse_block  # noqa: E402


def _read_roster(roster_path: Path) -> dict[str, str]:
    """Read a roster.json file, returning {} on any failure (fail-open)."""
    try:
        data = json.loads(roster_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _load_merged_roster(repo_path: Path) -> dict[str, str]:
    """Load `repo_path`'s roster, merged with its parent repo's roster if any.

    Parent detection (ONE level up only):
      1. `repo_path/..` must be a directory containing `.git` (i.e. a git repo).
      2. `repo_path/../.claude/team/roster.json` must exist.
    If both hold, the parent roster is loaded and merged under the child roster
    — child keys override parent keys, so a same-name entry in the child wins.
    Any OSError / malformed JSON at any step is swallowed; a broken parent
    roster must never block a child repo's valid commit.
    """
    child_path = repo_path / ".claude" / "team" / "roster.json"
    child_roster = _read_roster(child_path)

    try:
        parent_dir = repo_path.parent
        if (
            parent_dir != repo_path
            and (parent_dir / ".git").exists()
            and (parent_dir / ".claude" / "team" / "roster.json").is_file()
        ):
            parent_roster = _read_roster(parent_dir / ".claude" / "team" / "roster.json")
        else:
            parent_roster = {}
    except OSError:
        parent_roster = {}

    # Child wins on key collision.
    return {**parent_roster, **child_roster}


# Module-level roster for the repo hosting this hook. `_load_merged_roster`
# walks up one level; at this repo (noorinalabs-main) there is no parent repo
# with a roster, so this collapses to the local roster only.
ROSTER: dict[str, str] = _load_merged_roster(Path(__file__).resolve().parent.parent.parent)


def _detect_target_roster(command: str) -> dict[str, str] | None:
    """Detect cross-repo commits and load the target repo's merged roster.

    When the command contains `cd /path/to/repo && git commit ...`, the
    commit targets a different repo. Load that repo's roster.json (merged
    with its parent repo's roster if applicable — see `_load_merged_roster`)
    so we validate against the correct team, not the local one.

    Returns the target merged roster dict, or None to use the local ROSTER.
    """
    cd_match = re.search(r"cd\s+([^\s;&|]+)", command)
    if not cd_match:
        return None
    target_dir = Path(cd_match.group(1)).expanduser().resolve()
    if not target_dir.is_dir():
        return None
    roster_path = target_dir / ".claude" / "team" / "roster.json"
    if not roster_path.is_file():
        return None
    merged = _load_merged_roster(target_dir)
    return merged or None


def _find_commit_segment(command: str) -> list[str] | None:
    """Find the `git ... commit ...` segment in `command`. None if absent.

    Strips heredocs first so a heredoc body containing the literal phrase
    "git commit" cannot be confused with a real invocation. Tokenizes the
    cleaned command with shlex, walks each pipeline segment, and returns
    the first segment whose `find_git_subcommand` resolves to subcommand
    `commit`.

    Returns None on parse failure OR when there is no commit. The caller
    distinguishes the two via `_looks_like_git_commit` so a malformed-but-
    suspicious command falls through to a fail-closed regex path instead
    of being silently allowed (per `_shell_parse.tokenize` contract).
    """
    cleaned = strip_heredocs(command)
    tokens = tokenize(cleaned)
    if tokens is None:
        return None
    for segment in iter_command_segments(tokens):
        decoded = find_git_subcommand(segment)
        if decoded is None:
            continue
        _globals, rest = decoded
        if rest and rest[0] == "commit":
            return segment
    return None


# Regex-only heuristic for the parse-failure fallback: did the command,
# after stripping heredocs, contain `git ... commit` at command position?
# Anchored at start-of-line or after a shell operator. Liberal on purpose
# — when shlex fails we want to err on the side of validating identity.
_COMMIT_FALLBACK_RE = re.compile(
    r"(?:^|[;&|]\s*|&&\s*|\|\|\s*)\s*git\b[^;&|]*?\bcommit\b",
    re.MULTILINE,
)


def _looks_like_git_commit(command: str) -> bool:
    """Regex fallback used when shlex.split fails (unbalanced quotes etc.).

    Strips heredocs, then searches for `git ... commit` in command position.
    This is a deliberately broad heuristic: a parse-failure-and-no-commit-
    looking command falls through to allow, but a parse-failure-with-commit-
    looking command blocks (fail-closed for security-relevant validation,
    per the `_shell_parse.tokenize` caller contract).
    """
    cleaned = strip_heredocs(command)
    return bool(_COMMIT_FALLBACK_RE.search(cleaned))


def check(input_data: dict) -> dict | None:
    """Check commit identity. Returns result dict if blocking, None if allowed."""
    tool_name = input_data.get("tool_name", "")
    if tool_name != "Bash":
        return None

    command = input_data.get("tool_input", {}).get("command", "")

    commit_segment = _find_commit_segment(command)
    if commit_segment is None:
        # Parse-failure fail-closed path: shlex couldn't tokenize, but the
        # command LOOKS like it contains a `git commit`. Block with a
        # parse-failure-specific message so the operator can fix the quoting
        # and retry. Allowing here would create a hole — paste a malformed
        # `git commit` and bypass identity validation.
        if not _looks_like_git_commit(command):
            return None
        result = {
            "decision": "block",
            "reason": (
                "BLOCKED: git commit detected but command failed shlex parsing "
                "(likely unbalanced quotes — common when embedding heredocs "
                'inside `-m "$(cat <<EOF...EOF)"` next to `-c user.name=` flags). '
                "Cannot validate identity flags from a malformed command.\n\n"
                "Fix: write the message to a file and use `-F /path/to/msg.txt`:\n"
                "  printf '%s\\n' \"your commit message\" > /tmp/msg-issue-N.txt\n"
                '  git -c user.name="Foo Bar" -c user.email="..." \\\n'
                "      commit -F /tmp/msg-issue-N.txt\n"
                "(Or for multi-line: heredoc into the file FIRST, then -F.)\n\n"
                "See memory feedback_heredoc_in_git_commit.md for full context."
            ),
        }
        log_pretooluse_block("validate_commit_identity", command, result["reason"])
        return result

    # Cross-repo support: if the command `cd`s into another repo, load that
    # repo's roster instead of the local one.
    roster = _detect_target_roster(command) or ROSTER

    pairs = dict(extract_dash_c_pairs(commit_segment))
    name = pairs.get("user.name")
    email = pairs.get("user.email")

    if not name:
        result = {
            "decision": "block",
            "reason": (
                "BLOCKED: git commit missing `-c user.name=` flag. "
                "Charter § Commit Identity requires per-commit identity via -c flags. "
                'Example: git -c user.name="Kwame Asante" '
                '-c user.email="parametrization+Kwame.Asante@gmail.com" commit -m "..."'
            ),
        }
        log_pretooluse_block("validate_commit_identity", command, result["reason"])
        return result

    if not email:
        result = {
            "decision": "block",
            "reason": (
                "BLOCKED: git commit missing `-c user.email=` flag. "
                "Charter § Commit Identity requires per-commit identity via -c flags. "
                'Example: git -c user.name="Kwame Asante" '
                '-c user.email="parametrization+Kwame.Asante@gmail.com" commit -m "..."'
            ),
        }
        log_pretooluse_block("validate_commit_identity", command, result["reason"])
        return result

    if name not in roster:
        result = {
            "decision": "block",
            "reason": (
                f'BLOCKED: user.name="{name}" is not a recognized roster member. '
                f"Valid names: {', '.join(sorted(roster.keys()))}"
            ),
        }
        log_pretooluse_block("validate_commit_identity", command, result["reason"])
        return result

    expected_email = roster[name]
    if email != expected_email:
        result = {
            "decision": "block",
            "reason": (
                f'BLOCKED: user.email="{email}" does not match roster for {name}. '
                f"Expected: {expected_email}"
            ),
        }
        log_pretooluse_block("validate_commit_identity", command, result["reason"])
        return result

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
