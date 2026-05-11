#!/usr/bin/env python3
"""PreToolUse hook: Require TWO PR review comments before merge.

Blocks `gh pr merge` unless the PR has at least two reviews from distinct
non-authors, using either formal GitHub reviews or charter-format
comment-based reviews from different team members. Honors the
Single-Reviewer Exception for wave-bootstrap PRs reviewed by a charter-
enforcer role.

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

Charter-format review comments (canonical per `pull-requests.md` § Comment-Based Reviews,
resolves #233):

  Requestor: <comment author>     # always the team member POSTING the comment
  Requestee: <comment target>     # always the team member ADDRESSED by the comment
  RequestOrReplied: <Request|Reply|Approved|ChangesRequested>
  TechDebt: none | #15, #16, ...

  Direction by RequestOrReplied:
    - Request          — Requestor=PR author,  Requestee=reviewer (NOT a verdict)
    - Reply / Replied  — Requestor=replier,    Requestee=person-being-replied-to (NOT a verdict)
    - Approved         — Requestor=reviewer,   Requestee=PR author (verdict)
    - ChangesRequested — Requestor=reviewer,   Requestee=PR author (verdict)

  The reviewer for a verdict comment is the comment AUTHOR — i.e. the
  Requestor. The prior hook counted distinct Requestee values across
  Approved/ChangesRequested comments, which on verdicts is always the PR
  author and so collapsed to a single value (resolves #244).

Reviewer counting rule (resolves #244):
  - Verdict comments (Approved / ChangesRequested) → Requestor is the reviewer
  - Request / Reply comments → not reviews; do not contribute to reviewer count
  - Two-reviewer rule satisfied when there are TWO DISTINCT REVIEWER NAMES across
    Approved comments, neither of which is the PR author.

Reviewer dedup key:
  The reviewer set is keyed on the FULL reviewer name (lowercased), not on
  the lastname. Two distinct reviewers with the same lastname (e.g.,
  "Lucas Ferreira" and "Santiago Ferreira") are counted as TWO reviewers
  toward the two-peer-review requirement (issue #164).
  The author-equality check uses lastname because branches are named
  `{Initial}.{Lastname}/...` and we only have the author's lastname to
  compare against.

Single-Reviewer Exception (resolves #228):
  When the PR is labeled `wave-bootstrap` AND there is exactly ONE distinct
  reviewer who is a charter-enforcer role in the local roster, the hook
  permits merge with one Approved comment instead of two. Charter
  `pull-requests.md` § Single-Reviewer Exception (Wave-Bootstrap Only)
  defines the policy; this is its hook-side enforcement.

  Charter-enforcer roles are derived from the local repo's
  `.claude/team/roster/` filenames matching the prefix allowlist:
    standards_lead_*    (parent: Aino)
    program_director_*  (parent: Nadia)
    manager_*           (children: e.g. Maeve, Dilara, Bereket)
    project_lead_*      (children: e.g. Marcia)
    tech_lead_*         (children: e.g. Anya)
  Each file's `**Name:** <Full Name>` line is parsed for the canonical name.

Exit codes:
  0 — allow (not a merge command, two reviews, or single-reviewer exception)
  2 — block (fewer than two reviews and exception does not apply, or a
      verdict is missing TechDebt)
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from annunaki_log import log_pretooluse_block

# Charter-enforcer role prefixes for the Single-Reviewer Exception. Derived
# from `pull-requests.md § Single-Reviewer Exception (Wave-Bootstrap Only)`
# "Standards & Quality Lead (Aino) or a comparable charter enforcer". The
# prefix list captures the equivalent roles across parent + child rosters
# observed in the org: standards_lead, program_director (parent), manager,
# project_lead, tech_lead (children).
_CHARTER_ENFORCER_ROLE_PREFIXES = (
    "standards_lead_",
    "program_director_",
    "manager_",
    "project_lead_",
    "tech_lead_",
)


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

    Returns dict with keys: author (login str), number, reviews, headRefName,
    labels (list of label-name strings).
    Returns None if the fetch fails.
    """
    try:
        cmd = ["gh", "pr", "view"]
        if pr_number:
            cmd.append(pr_number)
        if repo:
            cmd.extend(["--repo", repo])
        cmd.extend(["--json", "author,number,reviews,headRefName,labels"])
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            return None

        data = json.loads(result.stdout)
        labels = [label.get("name", "") for label in data.get("labels", [])]
        return {
            "author": data.get("author", {}).get("login", ""),
            "number": data.get("number", pr_number),
            "reviews": data.get("reviews", []),
            "headRefName": data.get("headRefName", ""),
            "labels": labels,
        }

    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return None


def extract_branch_author_lastname(head_ref: str) -> str | None:
    """Extract the last name from branch format '{FirstInitial}.{LastName}[-/]...'.

    Accepts both separator styles seen in practice:
    - slash: `A.Virtanen/0179-branch-regex-fix` (legacy/charter spec)
    - dash:  `A.Virtanen-0179-branch-regex-fix` (observed on recent branches)

    Returns None if the head_ref does not match the `{Initial}.{LastName}` prefix
    followed by one of the accepted separators.
    """
    match = re.match(r"[A-Za-z]\.([A-Za-z]+)[-/]", head_ref)
    if match:
        return match.group(1)
    return None


PROJECT_NUMBER = 2
ORG = "noorinalabs"

# Path to the local repo's roster directory. Resolved relative to the hook
# file: /<repo_root>/.claude/hooks/validate_pr_review.py → /<repo_root>/.claude/team/roster.
_ROSTER_DIR = Path(__file__).resolve().parent.parent / "team" / "roster"


class CommentReviewResult:
    """Result of checking PR comments for charter-format reviews."""

    def __init__(self) -> None:
        self.reviewers: set[str] = set()
        self.reviews_missing_tech_debt: list[str] = []  # reviewer names missing TechDebt line
        self.tech_debt_issue_numbers: list[str] = []  # issue numbers from TechDebt: lines


# Only these RequestOrReplied values represent actual review verdicts that
# REQUIRE the TechDebt attestation line. Request / Reply comments are
# process metadata (review requests, author replies) and do NOT require it.
# Issue #147: the prior implementation flagged any Requestee+RequestOrReplied
# comment, which over-enforced TechDebt on Request/Replied traffic.
#
# Includes both the canonical `ChangesRequested` (one word, charter-line-14)
# and the spaced/short variants observed in practice.
_VERDICT_REQUIRING_TECH_DEBT = {
    "approved",
    "changes requested",
    "changesrequested",
    "changes",
}


def _is_verdict(value: str) -> bool:
    """Return True if a RequestOrReplied value is an actual review verdict.

    Comparison is case-insensitive and whitespace-trimmed. Accepts the
    canonical `ChangesRequested` (per charter line 14), the spaced
    `Changes Requested` form, and the shorter `Changes` variant noted in
    charter discussion as seen in practice. Does NOT accept Request (a
    review request) or Reply / Replied (an author's reply).
    """
    normalized = value.strip().lower()
    # Strip trailing markdown markers and stray punctuation
    normalized = normalized.rstrip("*").strip()
    return normalized in _VERDICT_REQUIRING_TECH_DEBT


def _is_approved(value: str) -> bool:
    """Return True if a RequestOrReplied value is specifically Approved.

    The 2-reviewer rule (charter line 36) counts distinct Requestor values
    across `Approved` comments only — NOT ChangesRequested. A
    ChangesRequested comment is a verdict (TechDebt required) but does not
    contribute to the 2-reviewer threshold.
    """
    normalized = value.strip().lower().rstrip("*").strip()
    return normalized == "approved"


def _extract_charter_field(field_name: str, body: str) -> str | None:
    """Extract a charter-format field value from a comment body.

    Handles markdown bold (`**Field:**`) and plain (`Field:`) variants.
    Returns the first-line value with markdown markers and parenthetical
    role descriptions stripped. Returns None if the field is not present.
    """
    pattern = rf"\*{{0,2}}{re.escape(field_name)}:\*{{0,2}}\s*(.+)"
    match = re.search(pattern, body)
    if not match:
        return None
    value = match.group(1).strip()
    # Drop trailing content after first newline (single-line field).
    value = value.split("\n", 1)[0].strip()
    # Strip markdown bold and parenthetical role descriptions.
    value = value.strip("*").strip()
    value = re.sub(r"\s*\(.*?\)\s*$", "", value).strip()
    return value or None


def _name_lastname(full_name: str) -> str:
    """Return the last name from a `Firstname Lastname` or `Firstname.Lastname` string."""
    parts = re.split(r"[\s.]+", full_name)
    if len(parts) >= 2:
        return parts[-1]
    return full_name


def check_comment_reviews(
    pr_number: str | int,
    branch_author_lastname: str,
    repo: str | None = None,
) -> CommentReviewResult:
    """Check PR comments for charter-format review comments from different authors.

    Returns a CommentReviewResult with distinct reviewer names (keyed on full
    name, lowercased) and any reviews missing the mandatory TechDebt line.

    Reviewer identification per charter (resolves #244):
      - Approved / ChangesRequested → reviewer is the Requestor (comment author)
      - Request / Reply → not a review; does not contribute to reviewer set
      - 2-reviewer threshold counts distinct Requestor values across Approved
        comments only (ChangesRequested is a verdict-with-TechDebt but does
        not count toward the threshold).
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

        # Fetch ALL PR comments via the issues API. `--paginate` concatenates
        # each page's JSON array into one combined response; without it, the
        # hook silently misses reviews appearing after comment #100 (#303).
        # Bumped the subprocess timeout to 30s to give pagination room — most
        # PRs have <100 comments and complete in <5s; the few high-traffic
        # PRs that need multiple pages take longer.
        comments_result = subprocess.run(
            [
                "gh",
                "api",
                "--paginate",
                f"repos/{owner}/{repo_name}/issues/{pr_number}/comments?per_page=100",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if comments_result.returncode != 0:
            return result

        comments = json.loads(comments_result.stdout)
        for comment in comments:
            body = comment.get("body", "")
            requestor = _extract_charter_field("Requestor", body)
            ror_value = _extract_charter_field("RequestOrReplied", body)

            # A charter-format comment must have BOTH Requestor and
            # RequestOrReplied. Comments missing either are not parsed.
            if not (requestor and ror_value):
                continue

            is_verdict_comment = _is_verdict(ror_value)
            is_approved_comment = _is_approved(ror_value)

            # Only Approved comments contribute to the reviewer set toward
            # the 2-reviewer threshold (charter line 36, resolves #244).
            if is_approved_comment:
                reviewer_lastname = _name_lastname(requestor)
                if reviewer_lastname.lower() != branch_author_lastname.lower():
                    result.reviewers.add(requestor.lower())

            # TechDebt attestation is required on every verdict
            # (Approved + ChangesRequested) — issue #147 fix.
            if is_verdict_comment:
                has_tech_debt = re.search(r"\*{0,2}TechDebt:\*{0,2}\s*(.+)", body)
                if not has_tech_debt:
                    # Reviewer name = Requestor on verdicts (charter line 30).
                    result.reviews_missing_tech_debt.append(requestor)
                else:
                    td_value = has_tech_debt.group(1).strip().strip("*").strip()
                    if td_value.lower() != "none":
                        # Extract issue numbers (#15, #16, etc.)
                        issue_nums = re.findall(r"#(\d+)", td_value)
                        result.tech_debt_issue_numbers.extend(issue_nums)

        return result

    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return result


def load_charter_enforcer_names() -> set[str]:
    """Read the local roster dir and return canonical names of charter enforcers.

    Charter enforcers are roster files matching the
    `_CHARTER_ENFORCER_ROLE_PREFIXES` allowlist. Each file's
    `**Name:** <Full Name>` line is parsed for the canonical name.
    Returns an empty set on any I/O failure (fail-closed for the exception
    path: if we can't read the roster, we don't grant the exception).

    Names are returned in lowercase to match `CommentReviewResult.reviewers`'
    dedup key (full name, lowercased).
    """
    enforcers: set[str] = set()
    try:
        if not _ROSTER_DIR.is_dir():
            return enforcers
        for entry in _ROSTER_DIR.iterdir():
            if entry.suffix != ".md":
                continue
            if not any(entry.name.startswith(p) for p in _CHARTER_ENFORCER_ROLE_PREFIXES):
                continue
            try:
                content = entry.read_text(encoding="utf-8")
            except OSError:
                continue
            # Look for `**Name:** <Full Name>` (charter persona convention).
            match = re.search(r"\*\*Name:\*\*\s*([^\n]+)", content)
            if match:
                enforcers.add(match.group(1).strip().lower())
    except OSError:
        return set()
    return enforcers


def is_single_reviewer_exception(
    pr_labels: list[str],
    reviewers: set[str],
) -> bool:
    """Return True if the PR qualifies for the Single-Reviewer Exception.

    Strict conditions per charter `pull-requests.md` § Single-Reviewer Exception
    (Wave-Bootstrap Only):
      1. PR is labeled `wave-bootstrap`
      2. There is EXACTLY ONE distinct reviewer in `reviewers`
      3. That reviewer is a charter-enforcer role in the local roster

    Resolves #228 — hook-side enforcement of the charter exception that was
    previously not honored.
    """
    if "wave-bootstrap" not in pr_labels:
        return False
    if len(reviewers) != 1:
        return False
    sole_reviewer = next(iter(reviewers))
    enforcers = load_charter_enforcer_names()
    return sole_reviewer in enforcers


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
    labels = pr_data["labels"]

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
        elif head_ref.startswith("deployments/") and "/wave-" in head_ref:
            # Wave-merge PR (head = deployments/phase-{N}/wave-{M}); no implementer-branch
            # author. Pass empty sentinel so the reviewer-vs-author lastname comparison
            # admits any non-empty reviewer name. See main#294.
            comment_review_result = check_comment_reviews(number, "", repo=repo)

    distinct_reviewers = formal_reviewers | comment_review_result.reviewers
    total_distinct = len(distinct_reviewers)

    pr_display = f"#{pr_number}" if pr_number else "(current branch)"

    # Single-Reviewer Exception (resolves #228) — wave-bootstrap PRs reviewed
    # by a charter enforcer may merge with one Approved comment instead of
    # two. Charter-enforcer role check uses the local roster.
    if total_distinct == 1 and is_single_reviewer_exception(labels, distinct_reviewers):
        # Exception applies — fall through to TechDebt check, then allow.
        pass
    elif total_distinct < 2:
        result = {
            "decision": "block",
            "reason": (
                f"BLOCKED: PR {pr_display} has {total_distinct}/2 required peer reviews. "
                "At least TWO Approved reviews from distinct non-authors are required before "
                "merge.\n"
                "Charter § Comment-Based Reviews counts distinct Requestor values across "
                "Approved comments (resolves main#244).\n"
                "Use `gh pr comment <PR#> --body '...'` with charter format:\n"
                "  Requestor: <reviewer>  Requestee: <PR author>  "
                "RequestOrReplied: Approved  TechDebt: none | #issue, ...\n\n"
                "Common failure mode — Reply vs Approved:\n"
                "  RequestOrReplied: Reply / Replied / Request / ChangesRequested do NOT\n"
                "  count toward the 2-reviewer threshold, EVEN IF the body prose says\n"
                '  "Approved" or "looks good." The hook parses the RequestOrReplied:\n'
                "  field directly — body prose is not inspected for verdict signals.\n"
                "  If a reviewer's intent was to approve, they must post a NEW comment\n"
                "  with `RequestOrReplied: Approved` (Reply comments cannot be edited\n"
                "  in-place to change the field).\n\n"
                "Common failure mode — Requestor / Requestee swap:\n"
                "  Requestor is the REVIEWER (the team member POSTING the comment).\n"
                "  Requestee is the PR AUTHOR (the team member ADDRESSED by the\n"
                "  comment). The hook counts distinct Requestor values across Approved\n"
                "  comments. If two reviewers BOTH set `Requestor:` to the PR author\n"
                "  (treating Requestor as 'addressed-to'), the hook sees 1 distinct\n"
                "  reviewer (the author's name, twice) even though two people approved.\n"
                "  This is the W9 PR#349 cascade root cause — orchestrator spawn brief\n"
                "  template had the fields swapped; 7 reviewer comments posted before\n"
                "  the hook surfaced the count mismatch.\n"
                "  Diagnose the swap directly:\n"
                "    gh api repos/<owner>/<repo>/issues/<PR>/comments \\\n"
                "      --jq '[.[] | select(.body | "
                'contains("RequestOrReplied: Approved"))\n'
                "             | .body "
                '| capture("Requestor: *(?<r>[^\\\\n]+)") '
                "| .r] | unique'\n"
                "  Expected: distinct reviewer names. Seen: PR author's name repeated\n"
                "  → swap. Charter `pull-requests.md § Comment-Based Reviews` Direction\n"
                "  table (Approved row): Requestor=reviewer, Requestee=PR author.\n\n"
                "Diagnose the count yourself before retrying merge:\n"
                "  gh api repos/<owner>/<repo>/issues/<PR>/comments \\\n"
                "    --jq '[.[] | select(.body | "
                'contains("RequestOrReplied: Approved"))] | length\'\n\n'
                "Single-Reviewer Exception (charter § Single-Reviewer Exception (Wave-Bootstrap "
                "Only)): label PR `wave-bootstrap` AND have a charter-enforcer review (Standards "
                "Lead, Manager, Tech Lead, Project Lead, or Program Director).\n"
                "Pass `--admin` for emergency overrides only.\n"
                "See memory feedback_validate_pr_review_approved_not_reply.md for full context."
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
                "Charter § Comment-Based Reviews requires every Approved/ChangesRequested "
                "comment to include:\n"
                "  TechDebt: none        (if no tech-debt found)\n"
                "  TechDebt: #15, #16    (if issues were filed)\n"
                "Reviewer must create tech-debt labeled issues for all non-blocking "
                "findings BEFORE posting the verdict.\n"
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
