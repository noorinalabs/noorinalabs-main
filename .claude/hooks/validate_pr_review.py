#!/usr/bin/env python3
"""PreToolUse hook: Require PR review comment before merge.

Blocks `gh pr merge` unless the PR has at least one review from a non-author.

Exit codes:
  0 — allow (not gh pr merge, or review exists)
  2 — block (no peer review found)
"""

import json
import re
import subprocess
import sys


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


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    if tool_name != "Bash":
        sys.exit(0)

    command = input_data.get("tool_input", {}).get("command", "")

    if not re.search(r"\bgh\s+pr\s+merge\b", command):
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

    # Check for at least one review from a non-author
    has_peer_review = any(
        review.get("author", {}).get("login", "") != author
        for review in reviews
    )

    if has_peer_review:
        sys.exit(0)

    pr_display = f"#{pr_number}" if pr_number else "(current branch)"
    result = {
        "decision": "block",
        "reason": (
            f"BLOCKED: PR {pr_display} has no peer review. "
            "At least one review from a non-author is required before merge.\n"
            "Charter § Pull Requests requires peer review for all merges.\n"
            "Use `gh pr review` to add a review, or pass `--admin` for emergency overrides."
        ),
    }
    print(json.dumps(result))
    sys.exit(2)


if __name__ == "__main__":
    main()
