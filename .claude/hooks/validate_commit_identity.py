#!/usr/bin/env python3
"""PreToolUse hook: Validate git commit identity flags.

Ensures every `git commit` command includes `-c user.name=` and `-c user.email=`
flags matching a roster member from the charter's Commit Identity table.

Exit codes:
  0 — allow (not a git commit, or identity is valid)
  2 — block (missing or invalid identity flags)
"""

import json
import re
import sys
from pathlib import Path

# Load roster from shared JSON file — single source of truth for all hooks
_ROSTER_PATH = Path(__file__).resolve().parent.parent / "team" / "roster.json"
try:
    ROSTER: dict[str, str] = json.loads(_ROSTER_PATH.read_text(encoding="utf-8"))
except (FileNotFoundError, json.JSONDecodeError):
    # Fallback: allow if roster file is missing (don't block all commits)
    ROSTER = {}


def _strip_heredocs(text: str) -> str:
    """Remove heredoc bodies (<<'DELIM' ... DELIM and <<DELIM ... DELIM)."""
    return re.sub(
        r"<<-?\s*['\"]?(\w+)['\"]?.*?\n.*?\n\1\b",
        "",
        text,
        flags=re.DOTALL,
    )


def _strip_quoted_strings(text: str) -> str:
    """Remove content of single- and double-quoted strings."""
    # Remove single-quoted strings (no escaping inside single quotes in shell)
    text = re.sub(r"'[^']*'", "''", text)
    # Remove double-quoted strings (handle escaped quotes)
    text = re.sub(r'"(?:[^"\\]|\\.)*"', '""', text)
    return text


def _is_git_commit_command(command: str) -> bool:
    """Return True only if the command invokes `git ... commit` as a real command.

    Strips heredoc bodies and quoted strings first so that mentions of
    "git commit" inside string literals do not trigger a false positive.
    Then requires `git` to appear as a command — at the start of the
    (trimmed) command or after a shell operator (&&, ||, ;, |).
    """
    cleaned = _strip_heredocs(command)
    cleaned = _strip_quoted_strings(cleaned)

    # Match `git [options] commit` where commit is the subcommand.
    # Git options before the subcommand are: -c key=val, -C path, --flag, etc.
    # We skip those and check if the first non-option argument is "commit".
    return bool(
        re.search(
            r"(?:^|[;&|]\s*|&&\s*|\|\|\s*)\s*git\b"
            r"(?:\s+-c\s+\S+)*"       # skip -c key=val pairs
            r"(?:\s+-[A-Za-z]\s+\S+)*" # skip other -X val options
            r"\s+commit(?:\s|$)",
            cleaned,
            re.MULTILINE,
        )
    )


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    if tool_name != "Bash":
        sys.exit(0)

    command = input_data.get("tool_input", {}).get("command", "")

    # Only match actual `git commit` invocations — not mentions of "git" and
    # "commit" inside heredocs, quoted strings, or other non-command text.
    if not _is_git_commit_command(command):
        sys.exit(0)

    # Extract -c user.name="..." or -c user.name='...' or -c user.name=...
    name_match = re.search(r'-c\s+user\.name=["\']?([^"\']+)["\']?', command)
    email_match = re.search(r'-c\s+user\.email=["\']?([^"\']+)["\']?', command)

    if not name_match:
        result = {
            "decision": "block",
            "reason": (
                "BLOCKED: git commit missing `-c user.name=` flag. "
                "Charter § Commit Identity requires per-commit identity via -c flags. "
                "Example: git -c user.name=\"Kwame Asante\" -c user.email=\"parametrization+Kwame.Asante@gmail.com\" commit -m \"...\""
            ),
        }
        print(json.dumps(result))
        sys.exit(2)

    if not email_match:
        result = {
            "decision": "block",
            "reason": (
                "BLOCKED: git commit missing `-c user.email=` flag. "
                "Charter § Commit Identity requires per-commit identity via -c flags. "
                "Example: git -c user.name=\"Kwame Asante\" -c user.email=\"parametrization+Kwame.Asante@gmail.com\" commit -m \"...\""
            ),
        }
        print(json.dumps(result))
        sys.exit(2)

    name = name_match.group(1).strip()
    email = email_match.group(1).strip()

    # Validate against roster
    if name not in ROSTER:
        result = {
            "decision": "block",
            "reason": (
                f"BLOCKED: user.name=\"{name}\" is not a recognized roster member. "
                f"Valid names: {', '.join(sorted(ROSTER.keys()))}"
            ),
        }
        print(json.dumps(result))
        sys.exit(2)

    expected_email = ROSTER[name]
    if email != expected_email:
        result = {
            "decision": "block",
            "reason": (
                f"BLOCKED: user.email=\"{email}\" does not match roster for {name}. "
                f"Expected: {expected_email}"
            ),
        }
        print(json.dumps(result))
        sys.exit(2)

    # Identity is valid
    sys.exit(0)


if __name__ == "__main__":
    main()
