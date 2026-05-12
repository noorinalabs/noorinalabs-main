#!/usr/bin/env python3
"""PreToolUse hook: Validate Requestor/Requestee format in PR review comments.

Blocks `gh pr comment` if the Requestee matches the branch author, which
indicates the Requestor and Requestee fields are swapped.

Scope (closes #378)
===================

This hook enforces Requestor/Requestee non-swap detection ONLY for
`Approved` and `ChangesRequested` verdict comments — i.e., the rows of
the charter `pull-requests.md` § Comment-Based Reviews Direction table
where `Requestee = PR-author`. For these verdicts, "Requestee.lastname
== branch-author.lastname" is a reliable swap signal because the
reviewer (Requestor) should never share the lastname of the PR author
on whose branch they are commenting (modulo same-lastname collisions,
which are out of scope).

For `Request` and `Reply` comments — where the Direction-table role
bindings invert (Requestee = reviewer, Requestor = PR-author) — the
"Requestee.lastname == branch-author.lastname" heuristic misfires: a
legitimate Request to a reviewer from the PR author would have
Requestee = reviewer, which has no relation to the branch author's
lastname. Author/reviewer discipline for Request/Reply traffic is
operator-trusted and not hook-gated.

Unrecognized `RequestOrReplied` values (typos, future verdict types
the hook doesn't know about) fail OPEN — the hook returns None and
lets the comment through. Validating the verdict word itself is
covered by a sibling hook (`validate_pr_review`); duplicating that
logic here would couple two hooks that should remain independent.

Exit codes:
  0 — allow (not a comment command, not a review comment, fields correct,
       or RequestOrReplied is not Approved/ChangesRequested)
  2 — block (Requestee matches branch author on an Approved /
       ChangesRequested verdict — fields are swapped)
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
        r"<<'?EOF'?\s*\n(.*?)\nEOF",
        command,
        re.DOTALL,
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
            capture_output=True,
            text=True,
            timeout=15,
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


# Verdict direction values from charter `pull-requests.md` § Comment-Based
# Reviews Direction table. These are the rows where the swap heuristic is
# sound (Requestee = PR-author).
#
# Tolerated form variants: validate_pr_review counts the literal
# "Changes Requested" (with space) per `feedback_validate_pr_review_approved_not_reply`,
# while some templates and older fixtures use the camelCase "ChangesRequested".
# Both are accepted here. Comparison is case-insensitive on the canonical token
# match. The bare "Changes" prefix is NOT a verdict on its own — we require
# the full token (with or without internal space) to avoid false-narrowing.
_VERDICT_DIRECTIONS = frozenset(
    {
        "approved",
        "changesrequested",
        "changes requested",
    }
)


def _direction_is_verdict(body: str) -> bool:
    """True if the comment body's `RequestOrReplied:` value is a verdict direction.

    Matches the value on the same line as the `RequestOrReplied:` label. The
    value is stripped of trailing markdown bolding / whitespace and lowercased
    before comparison against `_VERDICT_DIRECTIONS`. If no value is captured
    (label present but value empty), returns False (fail-out-of-scope —
    consistent with the path-2 stance of narrowing rather than blocking on
    ambiguous shapes).
    """
    match = re.search(r"RequestOrReplied:\s*(.+)", body)
    if not match:
        return False
    raw = match.group(1).strip()
    raw = raw.strip("*").strip()
    if not raw:
        return False
    # Take the leading verdict word(s). The value may be followed by additional
    # text on the same line in some custom shapes; we only look at what comes
    # before a newline (already handled by `.+` group consuming up to EOL).
    # Lowercase for case-insensitive match against the canonical set.
    canonical = raw.lower()
    # Direct match against the canonical set covers both "approved",
    # "changesrequested", and "changes requested" forms.
    if canonical in _VERDICT_DIRECTIONS:
        return True
    # Tolerate trailing-token noise: e.g. "Approved (post-merge)" should still
    # be treated as Approved. Split on whitespace and join the first 1-2 tokens
    # to attempt the camelCase / two-word verdict match.
    parts = canonical.split()
    if not parts:
        return False
    if parts[0] in _VERDICT_DIRECTIONS:
        return True
    if len(parts) >= 2 and " ".join(parts[:2]) in _VERDICT_DIRECTIONS:
        return True
    return False


def check(input_data: dict) -> dict | None:
    """Check review comment format. Returns result dict if blocking/warning, None if allowed."""
    tool_name = input_data.get("tool_name", "")
    if tool_name != "Bash":
        return None

    command = input_data.get("tool_input", {}).get("command", "")

    if not is_comment_command(command):
        return None

    body = extract_comment_body(command)
    if not body:
        return None

    has_requestee = re.search(r"\*{0,2}Requestee:\*{0,2}\s*(.+)", body)
    has_request_or_replied = re.search(r"RequestOrReplied:", body)

    if not (has_requestee and has_request_or_replied):
        return None

    if not _direction_is_verdict(body):
        # Scope-narrowing per #378 / path 2: the Requestee == branch-author
        # swap heuristic is only sound for verdict directions (Approved /
        # ChangesRequested), where the charter Direction table binds
        # Requestee = PR-author. For Request / Reply (or unrecognized
        # directions) the role bindings invert or are unknown — we cannot
        # safely block on the swap signal. Allow through and let
        # operator/orchestrator discipline cover those surfaces.
        return None

    pr_number = extract_pr_number(command)
    if not pr_number:
        return {
            "decision": "allow",
            "systemMessage": (
                "WARNING: Could not extract PR number from comment command. "
                "Unable to validate Requestor/Requestee format."
            ),
        }

    branch_name = get_branch_name(pr_number)
    if not branch_name:
        return {
            "decision": "allow",
            "systemMessage": (
                "WARNING: Could not fetch branch name for PR. "
                "Unable to validate Requestor/Requestee format."
            ),
        }

    branch_author = extract_branch_author_lastname(branch_name)
    if not branch_author:
        return {
            "decision": "allow",
            "systemMessage": (
                "WARNING: Could not extract author from branch name. "
                "Unable to validate Requestor/Requestee format."
            ),
        }

    requestee_raw = has_requestee.group(1).strip()
    requestee_raw = requestee_raw.strip("*").strip()
    requestee_name = re.sub(r"\s*\(.*?\)\s*$", "", requestee_raw).strip()
    parts = re.split(r"[\s.]+", requestee_name)
    if len(parts) >= 2:
        requestee_lastname = parts[-1]
    else:
        requestee_lastname = requestee_name

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
        return result

    return None


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    result = check(input_data)
    if result is None:
        sys.exit(0)
    print(json.dumps(result))
    if result.get("decision") == "block":
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
