#!/usr/bin/env python3
"""PreToolUse hook: Require TWO PR review comments before merge.

Blocks `gh pr merge` unless the PR has at least two reviews from distinct
non-authors, using either formal GitHub reviews or charter-format
comment-based reviews from different team members.

Input Language:
  Fires on:      PreToolUse Bash
  Matches:       gh pr merge [{N}] [--repo {OWNER/REPO}] [--squash|--merge|--rebase]
                             [--admin] [--auto]   — including when chained via
                             && / || / | / ; after env-var assignments.
  Does NOT match: gh pr list, gh pr view, gh pr checks, gh pr create,
                  git merge, git pull.
  Flag pass-through:
    --repo   → forwarded to `gh pr view` and comment fetch so the hook checks
               the PR in the repo the user named, not the cwd-resolved repo.
    --admin  → short-circuits (emergency override — allows merge).

Charter-format review comments:
  Each comment is expected to include:
    Requestor: <branch author>
    Requestee: <reviewer>
    RequestOrReplied: <Request|Replied|Approved|Changes Requested>
    TechDebt: none | #15, #16, ...

  Canonical RequestOrReplied values (verified on PR #821 comments):
    - Request            — requesting review (NOT a verdict)
    - Replied            — author responding to review (NOT a verdict)
    - Approved           — actual review verdict (TechDebt line REQUIRED)
    - Changes Requested  — actual review verdict (TechDebt line REQUIRED)

  Only Approved and Changes Requested comments are ACTUAL REVIEWS. Request /
  Replied comments are process metadata and must NOT be required to carry the
  TechDebt attestation line. This is the fix for issue #147.

Exit codes:
  0 — allow (not a merge command, or two reviews exist)
  2 — block (fewer than two peer reviews found, or a verdict is missing TechDebt)
"""

import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from annunaki_log import log_pretooluse_block


def is_merge_command(command: str) -> bool:
    """Check if the command is a gh pr merge invocation, including chained commands.

    Handles direct invocations and commands chained with &&, ||, ;, or |.
    """
    # Split on shell chaining operators to check each sub-command
    for segment in re.split(r"\s*(?:&&|\|\||\||;)\s*", command):
        stripped = segment.lstrip()
        # Skip past any leading env variable assignments (VAR=value ...)
        while re.match(r"[A-Za-z_][A-Za-z0-9_]*=\S*\s+", stripped):
            stripped = re.sub(r"^[A-Za-z_][A-Za-z0-9_]*=\S*\s+", "", stripped)
        if re.match(r"gh\s+pr\s+merge\b", stripped):
            return True
    return False


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


def extract_repo_from_command(command: str) -> str | None:
    """Extract --repo value from gh pr merge command."""
    match = re.search(r"--repo\s+(\S+)", command)
    if match:
        return match.group(1)
    return None


def get_pr_data(pr_number: str | None, repo: str | None = None) -> dict | None:
    """Fetch all needed PR data in a single gh pr view call.

    Returns dict with keys: author (login str), number, reviews, headRefName.
    Returns None if the fetch fails.
    """
    try:
        cmd = ["gh", "pr", "view"]
        if pr_number:
            cmd.append(pr_number)
        if repo:
            cmd.extend(["--repo", repo])
        cmd.extend(["--json", "author,number,reviews,headRefName"])
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            return None

        data = json.loads(result.stdout)
        return {
            "author": data.get("author", {}).get("login", ""),
            "number": data.get("number", pr_number),
            "reviews": data.get("reviews", []),
            "headRefName": data.get("headRefName", ""),
        }

    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return None


def extract_branch_author_lastname(head_ref: str) -> str | None:
    """Extract the last name from branch format '{FirstInitial}.{LastName}/...'."""
    match = re.match(r"[A-Za-z]\.([A-Za-z]+)/", head_ref)
    if match:
        return match.group(1)
    return None


PROJECT_NUMBER = 2
ORG = "noorinalabs"


class CommentReviewResult:
    """Result of checking PR comments for charter-format reviews."""

    def __init__(self) -> None:
        self.reviewers: set[str] = set()
        self.reviews_missing_tech_debt: list[str] = []  # reviewer names missing TechDebt line
        self.tech_debt_issue_numbers: list[str] = []  # issue numbers from TechDebt: lines


# Only these RequestOrReplied values represent actual review verdicts that
# REQUIRE the TechDebt attestation line. Request / Replied comments are
# process metadata (review requests, author replies) and do NOT require it.
# Issue #147: the prior implementation flagged any Requestee+RequestOrReplied
# comment, which over-enforced TechDebt on Request/Replied traffic.
_VERDICT_REQUIRING_TECH_DEBT = {"approved", "changes requested", "changes"}


def _is_verdict(value: str) -> bool:
    """Return True if a RequestOrReplied value is an actual review verdict.

    Comparison is case-insensitive and whitespace-trimmed. Accepts both the
    canonical `Changes Requested` and the shorter `Changes` variant noted in
    charter discussion as seen in practice. Does NOT accept Request (a review
    request) or Replied (an author's reply).
    """
    normalized = value.strip().lower()
    # Strip trailing markdown markers and stray punctuation
    normalized = normalized.rstrip("*").strip()
    return normalized in _VERDICT_REQUIRING_TECH_DEBT


def check_comment_reviews(
    pr_number: str | int,
    branch_author_lastname: str,
    repo: str | None = None,
) -> CommentReviewResult:
    """Check PR comments for charter-format review comments from different authors.

    Returns a CommentReviewResult with distinct reviewer last names and any
    reviews missing the mandatory TechDebt: attestation line.
    """
    result = CommentReviewResult()
    try:
        # Get repo info — prefer --repo flag from the merge command
        if repo and "/" in repo:
            owner, repo_name = repo.split("/", 1)
        else:
            repo_result = subprocess.run(
                ["gh", "repo", "view", "--json", "owner,name"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if repo_result.returncode != 0:
                return result
            repo_data = json.loads(repo_result.stdout)
            owner = repo_data.get("owner", {}).get("login", "")
            repo_name = repo_data.get("name", "")

        # Fetch PR comments via the issues API with pagination
        comments_result = subprocess.run(
            ["gh", "api", f"repos/{owner}/{repo_name}/issues/{pr_number}/comments?per_page=100"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if comments_result.returncode != 0:
            return result

        comments = json.loads(comments_result.stdout)
        for comment in comments:
            body = comment.get("body", "")
            # Check for charter-format review: must contain Requestee: and RequestOrReplied:
            # Handles markdown bold (**Requestee:**) and plain text (Requestee:)
            has_requestee = re.search(r"\*{0,2}Requestee:\*{0,2}\s*(.+)", body)
            ror_match = re.search(r"\*{0,2}RequestOrReplied:\*{0,2}\s*(.+)", body)

            if not (has_requestee and ror_match):
                continue

            # Extract Requestee name (the reviewer)
            requestee_raw = has_requestee.group(1).strip()
            # Strip markdown bold markers and parenthetical role descriptions
            requestee_raw = requestee_raw.strip("*").strip()
            requestee_name = re.sub(r"\s*\(.*?\)\s*$", "", requestee_raw).strip()
            # Extract last name — handle "Firstname Lastname" and "Firstname.Lastname"
            parts = re.split(r"[\s.]+", requestee_name)
            if len(parts) >= 2:
                reviewer_lastname = parts[-1]
            else:
                reviewer_lastname = requestee_name

            # Reviewer must differ from branch author.
            # NOTE: Reviewer counting is NOT filtered by verdict type. It
            # continues to use all Requestee+RequestOrReplied comments as in
            # prior behavior; issue #147 addresses the TechDebt filter only,
            # and weakening the reviewer count would break existing flows.
            if reviewer_lastname.lower() != branch_author_lastname.lower():
                result.reviewers.add(reviewer_lastname.lower())

            ror_value = ror_match.group(1).strip()
            # Keep only the first line of the value, in case the regex greedy-
            # matched into following content on the same line.
            ror_value = ror_value.split("\n", 1)[0].strip()

            # TechDebt attestation is REQUIRED only on actual verdicts
            # (Approved / Changes Requested). Request / Replied comments do
            # NOT require it (issue #147 fix).
            if _is_verdict(ror_value):
                has_tech_debt = re.search(r"\*{0,2}TechDebt:\*{0,2}\s*(.+)", body)
                if not has_tech_debt:
                    result.reviews_missing_tech_debt.append(requestee_name)
                else:
                    td_value = has_tech_debt.group(1).strip().strip("*").strip()
                    if td_value.lower() != "none":
                        # Extract issue numbers (#15, #16, etc.)
                        issue_nums = re.findall(r"#(\d+)", td_value)
                        result.tech_debt_issue_numbers.extend(issue_nums)

        return result

    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return result


def ensure_issues_on_board(repo: str, issue_numbers: list[str]) -> None:
    """Best-effort add tech-debt issues to the project board."""
    for num in issue_numbers:
        url = f"https://github.com/{ORG}/{repo}/issues/{num}"
        try:
            subprocess.run(
                [
                    "gh",
                    "project",
                    "item-add",
                    str(PROJECT_NUMBER),
                    "--owner",
                    ORG,
                    "--url",
                    url,
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass  # Best-effort — don't block merge on board failures


def check(input_data: dict) -> dict | None:
    """Check PR review requirements. Returns result dict if blocking/warning, None if allowed."""
    tool_name = input_data.get("tool_name", "")
    if tool_name != "Bash":
        return None

    command = input_data.get("tool_input", {}).get("command", "")

    if not is_merge_command(command):
        return None

    if "--admin" in command:
        return None

    pr_number = extract_pr_number(command)
    repo = extract_repo_from_command(command)
    pr_data = get_pr_data(pr_number, repo=repo)

    if pr_data is None:
        return {
            "decision": "allow",
            "systemMessage": (
                "WARNING: Could not verify PR review status. "
                "Ensure the PR has at least one peer review before merging."
            ),
        }

    author = pr_data["author"]
    reviews = pr_data["reviews"]
    head_ref = pr_data["headRefName"]
    number = pr_data["number"]

    formal_reviewers: set[str] = set()
    for review in reviews:
        login = review.get("author", {}).get("login", "")
        if login and login != author:
            formal_reviewers.add(login.lower())

    comment_review_result = CommentReviewResult()
    branch_author_lastname = None
    if head_ref:
        branch_author_lastname = extract_branch_author_lastname(head_ref)
        if branch_author_lastname:
            comment_review_result = check_comment_reviews(number, branch_author_lastname, repo=repo)

    total_distinct = len(formal_reviewers) + len(comment_review_result.reviewers)

    pr_display = f"#{pr_number}" if pr_number else "(current branch)"

    if total_distinct < 2:
        found = total_distinct
        result = {
            "decision": "block",
            "reason": (
                f"BLOCKED: PR {pr_display} has {found}/2 required peer reviews. "
                "At least TWO reviews from distinct non-authors are required before merge.\n"
                "Charter § Pull Requests requires two comment-based peer reviews for all merges.\n"
                "Use `gh pr comment <PR#> --body '...'` with charter format:\n"
                "  Requestor: <branch author>  Requestee: <reviewer>  "
                "RequestOrReplied: Approved  TechDebt: none | #issue, ...\n"
                "Pass `--admin` for emergency overrides only."
            ),
        }
        log_pretooluse_block("validate_pr_review", command, result["reason"])
        return result

    missing = comment_review_result.reviews_missing_tech_debt
    if missing:
        names = ", ".join(missing)
        result = {
            "decision": "block",
            "reason": (
                f"BLOCKED: PR {pr_display} has review(s) missing the mandatory "
                f"TechDebt: attestation line.\n"
                f"Reviewers without TechDebt line: {names}\n"
                "Charter § Pull Requests requires every review to include:\n"
                "  TechDebt: none        (if no tech-debt found)\n"
                "  TechDebt: #15, #16    (if issues were filed)\n"
                "Reviewer must create tech-debt labeled issues for all non-blocking "
                "findings BEFORE posting the review.\n"
                "Pass `--admin` for emergency overrides only."
            ),
        }
        log_pretooluse_block("validate_pr_review", command, result["reason"])
        return result

    # All checks passed — ensure any referenced tech-debt issues are on the board
    td_issues = comment_review_result.tech_debt_issue_numbers
    if td_issues:
        board_repo_name = ""
        if repo and "/" in repo:
            board_repo_name = repo.split("/", 1)[1]
        else:
            try:
                repo_result = subprocess.run(
                    ["gh", "repo", "view", "--json", "name"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if repo_result.returncode == 0:
                    board_repo_name = json.loads(repo_result.stdout).get("name", "")
            except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
                pass
        if board_repo_name:
            ensure_issues_on_board(board_repo_name, td_issues)

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
