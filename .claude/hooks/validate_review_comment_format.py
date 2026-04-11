#!/usr/bin/env python3
"""PreToolUse hook: Validate Requestor/Requestee format in PR review comments.

Blocks `gh pr comment` if the Requestee matches the branch author, which
indicates the Requestor and Requestee fields are swapped.

Exit codes:
  0 — allow (not a comment command, not a review comment, or fields correct)
  2 — block (Requestee matches branch author — fields are swapped)
"""

import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from annunaki_log import log_pretooluse_block


def is_comment_command(command: str) -> bool:
    """Check if the command contains a gh pr comment invocation."""
    for segment in re.split(r"\s*(?:&&|\|\||\||;)\s*", command):
        stripped = segment.lstrip()
        while re.match(r"[A-Za-z_][A-Za-z0-9_]*=\S*\s+", stripped):
            stripped = re.sub(r"^[A-Za-z_][A-Za-z0-9_]*=\S*\s+", "", stripped)
        if re.match(r"gh\s+pr\s+comment\b", stripped):
            return True
    return False


def extract_pr_number(command: str) -> str | None:
    """Extract PR number from gh pr comment command."""
    match = re.search(r"\bgh\s+pr\s+comment\s+(\d+)", command)
    if match:
        return match.group(1)
    match = re.search(r"/pull/(\d+)", command)
    if match:
        return match.group(1)
    return None


def extract_comment_body(command: str) -> str | None:
    """Extract the comment body from the gh pr comment command.

    Handles heredoc format: --body "$(cat <<'EOF' ... EOF)"
    and simple quoted strings: --body '...' or --body "..."
    """
    # Heredoc: capture everything between <<'EOF' (or <<EOF) and the closing EOF
    heredoc_match = re.search(
        r"<<'?EOF'?\s*\n(.*?)\nEOF", command, re.DOTALL,
    )
    if heredoc_match:
        return heredoc_match.group(1)

    # --body with single-quoted string
    sq_match = re.search(r"--body\s+'((?:[^'\\]|\\.)*)'", command, re.DOTALL)
    if sq_match:
        return sq_match.group(1)

    # --body with double-quoted string
    dq_match = re.search(r'--body\s+"((?:[^"\\]|\\.)*)"', command, re.DOTALL)
    if dq_match:
        return dq_match.group(1)

    return None


def get_branch_name(pr_number: str) -> str | None:
    """Fetch the head branch name for a PR."""
    try:
        result = subprocess.run(
            ["gh", "pr", "view", pr_number, "--json", "headRefName"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        return data.get("headRefName", "")
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return None


def extract_branch_author_lastname(head_ref: str) -> str | None:
    """Extract the last name from branch format '{FirstInitial}.{LastName}/...'."""
    match = re.match(r"[A-Za-z]\.([A-Za-z]+)/", head_ref)
    if match:
        return match.group(1)
    return None


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    if tool_name != "Bash":
        sys.exit(0)

    command = input_data.get("tool_input", {}).get("command", "")

    if not is_comment_command(command):
        sys.exit(0)

    # Extract the comment body
    body = extract_comment_body(command)
    if not body:
        sys.exit(0)

    # Check if this is a charter-format review comment
    has_requestee = re.search(r"\*{0,2}Requestee:\*{0,2}\s*(.+)", body)
    has_request_or_replied = re.search(r"RequestOrReplied:", body)

    if not (has_requestee and has_request_or_replied):
        # Not a review comment — allow
        sys.exit(0)

    # Extract PR number
    pr_number = extract_pr_number(command)
    if not pr_number:
        # Can't determine PR — allow with warning
        result = {
            "decision": "allow",
            "systemMessage": (
                "WARNING: Could not extract PR number from comment command. "
                "Unable to validate Requestor/Requestee format."
            ),
        }
        print(json.dumps(result))
        sys.exit(0)

    # Get branch name
    branch_name = get_branch_name(pr_number)
    if not branch_name:
        result = {
            "decision": "allow",
            "systemMessage": (
                "WARNING: Could not fetch branch name for PR. "
                "Unable to validate Requestor/Requestee format."
            ),
        }
        print(json.dumps(result))
        sys.exit(0)

    # Extract branch author's last name
    branch_author = extract_branch_author_lastname(branch_name)
    if not branch_author:
        result = {
            "decision": "allow",
            "systemMessage": (
                "WARNING: Could not extract author from branch name. "
                "Unable to validate Requestor/Requestee format."
            ),
        }
        print(json.dumps(result))
        sys.exit(0)

    # Extract Requestee's last name from the comment body
    requestee_raw = has_requestee.group(1).strip()
    requestee_raw = requestee_raw.strip("*").strip()
    requestee_name = re.sub(r"\s*\(.*?\)\s*$", "", requestee_raw).strip()
    parts = re.split(r"[\s.]+", requestee_name)
    if len(parts) >= 2:
        requestee_lastname = parts[-1]
    else:
        requestee_lastname = requestee_name

    # Block if Requestee matches branch author (fields are swapped)
    if requestee_lastname.lower() == branch_author.lower():
        result = {
            "decision": "block",
            "reason": (
                f"BLOCKED: Requestor/Requestee appears swapped. "
                f"Requestor should be the PR author (who requested the review), "
                f"Requestee should be the reviewer (who is doing the review). "
                f"The branch author is {branch_author} — they should be the "
                f"Requestor, not the Requestee."
            ),
        }
        log_pretooluse_block("validate_review_comment_format", command, result["reason"])
        print(json.dumps(result))
        sys.exit(2)

    # Fields are correct
    sys.exit(0)


if __name__ == "__main__":
    main()
