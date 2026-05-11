#!/usr/bin/env python3
"""PreToolUse hook: Block `gh pr review` and require comment-based reviews.

All agents share a single GitHub user, so `gh pr review --approve` always
fails with "cannot approve your own pull request". This hook catches the
mistake early and redirects to the comment-based review format.

Exit codes:
  0 — allow (not a gh pr review command)
  2 — block (gh pr review detected)
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from annunaki_log import log_pretooluse_block


def check(input_data: dict) -> dict | None:
    """Check for gh pr review. Returns result dict if blocking, None if allowed."""
    tool_name = input_data.get("tool_name", "")
    if tool_name != "Bash":
        return None

    command = input_data.get("tool_input", {}).get("command", "")

    for segment in re.split(r"\s*(?:&&|\|\||\||;)\s*", command):
        stripped = segment.lstrip()
        if re.match(r"gh\s+pr\s+review\b", stripped):
            result = {
                "decision": "block",
                "reason": (
                    "BLOCKED: `gh pr review` is not supported — all agents share one "
                    "GitHub user, so API-based approvals always fail.\n"
                    "Charter § Pull Requests / § Comment-Based Reviews requires "
                    "comment-based reviews instead.\n\n"
                    "Use `gh pr comment <PR#> --body '...'` with this format:\n"
                    "  Requestor: <reviewer name>      # team member POSTING the comment\n"
                    "  Requestee: <PR author name>     # team member ADDRESSED by it\n"
                    "  RequestOrReplied: Approved | ChangesRequested\n"
                    "  TechDebt: none | #issue, ...\n\n"
                    "Direction reminder (charter § Comment-Based Reviews Direction table):\n"
                    "  Approved / ChangesRequested verdicts → Requestor=reviewer, "
                    "Requestee=PR author.\n"
                    "  Swapping these reproduces the W9 PR#349 cascade — "
                    "`validate_pr_review` counts distinct Requestor values across "
                    "Approved comments, so two reviewers both writing the PR author's "
                    "name as Requestor collapse to 1/2.\n"
                ),
            }
            log_pretooluse_block("block_gh_pr_review", command, result["reason"])
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
