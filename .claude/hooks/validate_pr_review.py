#!/usr/bin/env python3
"""PreToolUse hook: Require PR review comment before merge.

Blocks `gh pr merge` unless the PR has at least one review from a non-author,
or a charter-format comment-based review from a different team member.

Exit codes:
  0 — allow (not a merge command, or review exists)
  2 — block (no peer review found)
"""

import json
import re
import subprocess
import sys


def is_merge_command(command: str) -> bool:
    """Check if the command is a gh pr merge invocation (not embedded in a string)."""
    # Strip leading whitespace and optional env variable assignments
    # e.g. "  FOO=bar gh pr merge 123"
    stripped = command.lstrip()
    # Skip past any leading env variable assignments (VAR=value ...)
    while re.match(r"[A-Za-z_][A-Za-z0-9_]*=\S*\s+", stripped):
        stripped = re.sub(r"^[A-Za-z_][A-Za-z0-9_]*=\S*\s+", "", stripped)
    return bool(re.match(r"gh\s+pr\s+merge\b", stripped))


def extract_pr_number(command: str) -> str | None:
    """Extract PR number from gh pr merge command."""
    # gh pr merge 123 or gh pr merge <url>
    match = re.search(r"\bgh\s+pr\s+merge\s+(\d+)", command)
    if match:
        return match.group(1)
    # gh pr merge <url containing /pull/123>
    match = re.search(r"/pull/(\d+)", command)
    if match:
        return match.group(1)
    # gh pr merge with no number (current branch PR)
    return None


def get_pr_reviews(pr_number: str | None) -> tuple[str | None, list[dict]]:
    """Fetch PR author and reviews. Returns (author, reviews)."""
    try:
        # Get PR author
        pr_cmd = ["gh", "pr", "view"]
        if pr_number:
            pr_cmd.append(pr_number)
        pr_cmd.extend(["--json", "author,number"])
        pr_result = subprocess.run(
            pr_cmd, capture_output=True, text=True, timeout=15,
        )
        if pr_result.returncode != 0:
            return None, []

        pr_data = json.loads(pr_result.stdout)
        author = pr_data.get("author", {}).get("login", "")
        number = pr_data.get("number", pr_number)

        # Get reviews
        review_cmd = ["gh", "pr", "view", str(number), "--json", "reviews"]
        review_result = subprocess.run(
            review_cmd, capture_output=True, text=True, timeout=15,
        )
        if review_result.returncode != 0:
            return author, []

        review_data = json.loads(review_result.stdout)
        return author, review_data.get("reviews", [])

    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return None, []


def get_pr_head_ref(pr_number: str | None) -> str | None:
    """Fetch the PR's head ref (branch name)."""
    try:
        pr_cmd = ["gh", "pr", "view"]
        if pr_number:
            pr_cmd.append(pr_number)
        pr_cmd.extend(["--json", "headRefName"])
        result = subprocess.run(
            pr_cmd, capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        return data.get("headRefName")
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return None


def extract_branch_author_lastname(head_ref: str) -> str | None:
    """Extract the last name from branch format '{FirstInitial}.{LastName}/...'."""
    match = re.match(r"[A-Za-z]\.([A-Za-z]+)/", head_ref)
    if match:
        return match.group(1)
    return None


def check_comment_reviews(pr_number: str | None, branch_author_lastname: str) -> bool:
    """Check PR comments for charter-format review comments from a different author."""
    try:
        # We need the repo owner/name and PR number
        pr_cmd = ["gh", "pr", "view"]
        if pr_number:
            pr_cmd.append(pr_number)
        pr_cmd.extend(["--json", "number"])
        result = subprocess.run(
            pr_cmd, capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return False
        data = json.loads(result.stdout)
        number = data.get("number", pr_number)

        # Get repo info
        repo_result = subprocess.run(
            ["gh", "repo", "view", "--json", "owner,name"],
            capture_output=True, text=True, timeout=15,
        )
        if repo_result.returncode != 0:
            return False
        repo_data = json.loads(repo_result.stdout)
        owner = repo_data.get("owner", {}).get("login", "")
        repo_name = repo_data.get("name", "")

        # Fetch PR comments via the issues API
        comments_result = subprocess.run(
            ["gh", "api", f"repos/{owner}/{repo_name}/issues/{number}/comments"],
            capture_output=True, text=True, timeout=15,
        )
        if comments_result.returncode != 0:
            return False

        comments = json.loads(comments_result.stdout)
        for comment in comments:
            body = comment.get("body", "")
            # Check for charter-format review: must contain Requestor:, Requestee:, RequestOrReplied:
            has_requestor = re.search(r"Requestor:\s*(\S+)", body)
            has_requestee = re.search(r"Requestee:", body)
            has_request_or_replied = re.search(r"RequestOrReplied:", body)

            if has_requestor and has_requestee and has_request_or_replied:
                # Extract Requestor name (format: Firstname.Lastname)
                requestor_name = has_requestor.group(1)
                # Extract last name from Firstname.Lastname
                parts = requestor_name.split(".")
                if len(parts) >= 2:
                    requestor_lastname = parts[-1]
                else:
                    requestor_lastname = requestor_name

                # Compare last names case-insensitively — must differ
                if requestor_lastname.lower() != branch_author_lastname.lower():
                    return True

        return False

    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return False


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    if tool_name != "Bash":
        sys.exit(0)

    command = input_data.get("tool_input", {}).get("command", "")

    if not is_merge_command(command):
        sys.exit(0)

    # Allow --admin override only if explicitly present
    if "--admin" in command:
        sys.exit(0)

    pr_number = extract_pr_number(command)
    author, reviews = get_pr_reviews(pr_number)

    if author is None:
        # Could not fetch PR info — allow with warning
        result = {
            "decision": "allow",
            "systemMessage": (
                "WARNING: Could not verify PR review status. "
                "Ensure the PR has at least one peer review before merging."
            ),
        }
        print(json.dumps(result))
        sys.exit(0)

    # Check for at least one formal review from a non-author
    has_peer_review = any(
        review.get("author", {}).get("login", "") != author
        for review in reviews
    )

    if has_peer_review:
        sys.exit(0)

    # No formal review found — check comment-based reviews
    head_ref = get_pr_head_ref(pr_number)
    if head_ref:
        branch_author_lastname = extract_branch_author_lastname(head_ref)
        if branch_author_lastname:
            if check_comment_reviews(pr_number, branch_author_lastname):
                sys.exit(0)

    pr_display = f"#{pr_number}" if pr_number else "(current branch)"
    result = {
        "decision": "block",
        "reason": (
            f"BLOCKED: PR {pr_display} has no peer review. "
            "At least one review from a non-author is required before merge.\n"
            "Charter § Pull Requests requires peer review for all merges.\n"
            "Use `gh pr review` to add a review, or pass `--admin` for emergency overrides.\n"
            "Comment-based reviews are also accepted: post a comment with "
            "Requestor:, Requestee:, and RequestOrReplied: fields."
        ),
    }
    print(json.dumps(result))
    sys.exit(2)


if __name__ == "__main__":
    main()
