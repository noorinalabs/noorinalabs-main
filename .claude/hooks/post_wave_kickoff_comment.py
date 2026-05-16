#!/usr/bin/env python3
"""PostToolUse hook: Auto-post charter-format kickoff comment on wave-label-apply.

Fires on `gh issue edit <num> --repo noorinalabs/<repo> ... --add-label "p{N}-wave-{M}"`
and posts a charter-format kickoff comment (per
`.claude/team/charter/pull-requests.md` § Kickoff Comment Format — also
mirrored in `/wave-kickoff` SKILL.md Step 8) to the labeled issue. Replaces
the manual orchestrator loop documented in pre-#286 wave-kickoff SKILL.md
Step 8 (closes main#286).

Per `feedback_enforcement_hierarchy`: prefer hook > skill > charter. Skills
can be skipped or mis-executed; hooks fire deterministically on the
trigger event. Concrete failure mode this removes: orchestrator forgets to
post comments after applying labels (caught at next wave-wrapup as silent
drift). The hook makes the post deterministic on the trigger.

Behavior summary
================

1. Parse repo, issue number, wave label from the bash command. Uses
   `_shell_parse.tokenize` + heredoc-stripping (the third hook this wave
   eating its own dogfood — siblings #316, #378, #386).
2. Read `ontology/cross-repo-status.json` (or fallback paths) and find
   the matching assignment row in `wave_{M}_scope.tier_{1,2,3,4}_*`
   arrays. Match by:
     - `id == "<repo>#<num>"` for explicit-issue rows (W7+W8 shape), OR
     - `repo == "<repo>"` for Tier-1 backlog rows (W6+W7 Tier-1 shape).
3. If found, render a charter-format kickoff comment using the row's
   `implementer` / `reviewer` / `reviewer_2` fields.
4. Skip if the issue == `wave_{M}_meta_issue` (meta-issue gets its own
   all-hands kickoff comment, owned separately by /wave-kickoff Step 8b).
5. Idempotency: skip if the issue already has a kickoff comment whose
   body starts with the charter heading `Wave {M} Kickoff — Phase {N}`.
6. Post via `gh issue comment <num> --repo <repo> --body-file <path>`
   where the body file is written FRESH to `.claude/scratch/` immediately
   before the gh call (the `block_stale_tmp_message_file` PreToolUse hook
   would reject a stale /tmp/* path — and using .claude/scratch/ avoids
   both that race AND the /tmp false-positive scope entirely).
7. Failure modes: missing `wave_{M}_scope`, issue not found in any tier,
   gh CLI failure → annunaki-log-and-skip. The underlying label-apply
   already succeeded (this is PostToolUse); the hook never raises a
   failure on the user-visible tool call.

The hook is best-effort post-action automation. PostToolUse hooks cannot
fail the original tool call by design (the tool has already run); a
non-zero exit here only affects whether the harness logs a hook failure
itself. We return 0 unconditionally to match the existing PostToolUse
pattern in this repo (see auto_add_issue_to_board.py).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _shell_parse import (  # noqa: E402
    find_gh_subcommand,
    iter_command_segments,
    strip_heredocs,
    tokenize,
)
from annunaki_log import log_posttooluse_event  # noqa: E402

# Dispatcher opt-in (#425): when post_dispatcher sees this attribute set
# to True AND `check()` returns an action-shaped dict, it synthesizes a
# short `systemMessage` summary so operators see "post_wave_kickoff_comment:
# action=post repo=… issue=…" in the harness UI. The visibility matters
# here specifically because this hook's whole job is posting kickoff
# comments — silent "did it post or did it skip?" was the original #425
# symptom (operator concluded "dispatcher dead" when the hook was actually
# returning skip_idempotent correctly).
EMIT_DISPATCH_SUMMARY = True

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CROSS_REPO_STATUS = REPO_ROOT / "cross-repo-status.json"
# Fallback location (subdir-rooted layouts have used this in earlier waves).
CROSS_REPO_STATUS_ALT = REPO_ROOT / "ontology" / "cross-repo-status.json"

SCRATCH_DIR = REPO_ROOT / ".claude" / "scratch"

# The charter-format kickoff Requestor is the wave-kickoff orchestrator
# persona (per /wave-kickoff SKILL.md Step 8 template). Fatima Okonkwo is
# the named orchestrator in this roster; if the persona is renamed in the
# future, update this constant — there is no roster lookup for "who runs
# wave-kickoff" because that role is implicit.
KICKOFF_REQUESTOR = "Fatima Okonkwo"

# Regex matching the wave label value (e.g. "p3-wave-9"). Used both for
# argument detection and for parsing phase/wave numerics out.
_WAVE_LABEL_RE = re.compile(r"^p(\d+)-wave-(\d+)$")

# Regex matching the kickoff comment heading the charter requires
# (`**Wave {M} Kickoff — Phase {N}**`). Used for idempotency check. The
# emdash is the literal character in the template; we tolerate either
# em-dash or regular hyphen-surrounded form in case of copy-paste drift.
_KICKOFF_HEADING_RE = re.compile(r"\*\*Wave\s+\d+\s+Kickoff\s+[—-]\s+Phase\s+\d+\*\*")


def _read_status() -> dict | None:
    """Read cross-repo-status.json from canonical or fallback path. Return None
    if neither exists OR the file is malformed. Hook fails open."""
    for path in (CROSS_REPO_STATUS, CROSS_REPO_STATUS_ALT):
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None
    return None


def parse_label_apply_command(command: str) -> tuple[str, str, str] | None:
    """Parse `gh issue edit <num> --repo <repo> --add-label "p{N}-wave-{M}"`.

    Returns (repo, issue_number, wave_label) if the command applies a wave
    label, else None. Tolerates additional flags (e.g. extra --add-label
    arguments for implementer label) and arbitrary flag ordering.

    Implementation: tokenize via _shell_parse (heredoc-strip + shlex), walk
    pipeline segments looking for a `gh issue edit` segment with an
    `--add-label "p{N}-wave-{M}"` flag-value pair. Returns the FIRST such
    match per command.
    """
    cleaned = strip_heredocs(command)
    tokens = tokenize(cleaned)
    if tokens is None:
        return None

    for segment in iter_command_segments(tokens):
        gh = find_gh_subcommand(segment)
        if gh is None:
            continue
        _globals, rest = gh
        if len(rest) < 3 or rest[0] != "issue" or rest[1] != "edit":
            continue

        # The issue number is the first positional arg after `edit`.
        issue_number = None
        repo = None
        wave_label = None
        i = 2
        n = len(rest)
        while i < n:
            tok = rest[i]
            if issue_number is None and re.fullmatch(r"\d+", tok):
                issue_number = tok
                i += 1
                continue
            if tok == "--repo" and i + 1 < n:
                repo_full = rest[i + 1]
                # Accept "owner/name" or just "name"
                repo = repo_full.split("/")[-1]
                i += 2
                continue
            if tok.startswith("--repo="):
                repo_full = tok[len("--repo=") :]
                repo = repo_full.split("/")[-1]
                i += 1
                continue
            if tok == "--add-label" and i + 1 < n:
                value = rest[i + 1]
                if _WAVE_LABEL_RE.match(value):
                    wave_label = value
                i += 2
                continue
            if tok.startswith("--add-label="):
                value = tok[len("--add-label=") :]
                if _WAVE_LABEL_RE.match(value):
                    wave_label = value
                i += 1
                continue
            i += 1

        if issue_number and repo and wave_label:
            return repo, issue_number, wave_label

    return None


def find_assignment_row(status: dict, repo: str, issue_number: str, wave_num: int) -> dict | None:
    """Locate the assignment row for (repo, issue_number) in wave_{M}_scope.

    Match priority:
      1. Exact `id == "<repo>#<issue_number>"` in any tier_N array
         (W7+W8 shape — explicit issue rows).
      2. Exact `repo == "<repo>"` AND row has no `id` field, in any
         tier_N array (W6+W7 Tier-1 backlog shape — applies to all
         backlog issues in that repo).

    Returns the row dict (with `implementer` / `reviewer` / `reviewer_2`
    fields) or None if no match.
    """
    scope = status.get(f"wave_{wave_num}_scope") or {}
    if not isinstance(scope, dict):
        return None

    expected_id = f"{repo}#{issue_number}"

    # Pass 1: match by explicit id.
    for key, value in scope.items():
        if not key.startswith("tier_") or not isinstance(value, list):
            continue
        for row in value:
            if isinstance(row, dict) and row.get("id") == expected_id:
                return row

    # Pass 2: match by repo (backlog-tier fallback).
    for key, value in scope.items():
        if not key.startswith("tier_") or not isinstance(value, list):
            continue
        for row in value:
            if isinstance(row, dict) and "id" not in row and row.get("repo") == repo:
                return row

    return None


def render_kickoff_comment(row: dict, wave_num: int, phase_num: int, repo: str) -> str:
    """Render the charter-format kickoff comment body per pull-requests.md
    § Kickoff Comment Format / wave-kickoff SKILL.md Step 8 template.

    Required row fields: `implementer`. Optional: `reviewer`, `reviewer_2`,
    `priority`. Missing optional fields are rendered as "(unassigned)"
    placeholders rather than blanking the bullet — the orchestrator
    follow-up sweep can backfill, and an empty bullet looks like a bug.
    """
    implementer = row.get("implementer") or "(unassigned)"
    reviewer = row.get("reviewer") or "(unassigned)"
    reviewer_2 = row.get("reviewer_2") or "(unassigned)"
    priority = row.get("priority") or "feature"

    branch_base = f"deployments/phase-{phase_num}/wave-{wave_num}"

    lines = [
        f"Requestor: {KICKOFF_REQUESTOR}",
        f"Requestee: {implementer}",
        "RequestOrReplied: Request",
        "",
        f"**Wave {wave_num} Kickoff — Phase {phase_num}**",
        "",
        f"This issue is assigned to you for p{phase_num}-wave-{wave_num}.",
        f"- Peer reviewer: {reviewer}",
        f"- Secondary reviewer: {reviewer_2}",
        f"- Branch from: `{branch_base}`",
        "- Branch naming: `{FirstInitial}.{LastName}/{IIII}-{issue-slug}`",
        f"- Priority: {priority} (per charter § Wave Planning & Priority)",
        "",
        "Please begin implementation.",
    ]
    return "\n".join(lines)


def kickoff_already_posted(repo: str, issue_number: str, fetch_comments=None) -> bool:
    """Idempotency check: True if any existing comment body matches the
    charter kickoff heading regex.

    The `fetch_comments` callable defaults to a real `gh issue view` call;
    tests inject a mock. Returns False on any error fetching comments
    (don't suppress on broken state — let the hook attempt to post and
    surface real errors via annunaki on the actual post call).
    """
    if fetch_comments is None:
        fetch_comments = _gh_fetch_comments

    comments = fetch_comments(repo, issue_number)
    if comments is None:
        return False

    for c in comments:
        body = c.get("body", "") if isinstance(c, dict) else ""
        if _KICKOFF_HEADING_RE.search(body):
            return True
    return False


def _gh_fetch_comments(repo: str, issue_number: str) -> list[dict] | None:
    """Fetch existing comments on an issue via gh. Returns None on any error."""
    try:
        result = subprocess.run(
            [
                "gh",
                "issue",
                "view",
                issue_number,
                "--repo",
                f"noorinalabs/{repo}",
                "--json",
                "comments",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        comments = data.get("comments")
        return comments if isinstance(comments, list) else None
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError, OSError):
        return None


def _gh_post_comment(repo: str, issue_number: str, body_file: Path) -> bool:
    """Post a comment to an issue via gh, reading the body from body_file.

    Returns True on success, False on failure. Failures are NOT raised —
    the caller annunaki-logs and the original label-apply stays succeeded.
    """
    try:
        result = subprocess.run(
            [
                "gh",
                "issue",
                "comment",
                issue_number,
                "--repo",
                f"noorinalabs/{repo}",
                "--body-file",
                str(body_file),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def _write_fresh_body_file(body: str, repo: str, issue_number: str) -> Path:
    """Write the comment body to .claude/scratch/ with a unique fresh name.

    Uses `.claude/scratch/` (not /tmp/) to evade both the
    `block_stale_tmp_message_file` PreToolUse hook entirely AND the false-
    positive scope. Filename includes a millisecond timestamp so concurrent
    label applies on the same issue from a kickoff loop never collide.
    """
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    ts_ms = int(time.time() * 1000)
    safe_repo = re.sub(r"[^A-Za-z0-9_-]", "_", repo)
    path = SCRATCH_DIR / f"kickoff-{safe_repo}-{issue_number}-{ts_ms}.md"
    path.write_text(body, encoding="utf-8")
    return path


def check(
    input_data: dict,
    status_loader=None,
    comment_fetcher=None,
    comment_poster=None,
    body_writer=None,
) -> dict | None:
    """Pure decision function. Returns a dict describing the action taken
    (or skipped), or None when the hook does not apply.

    Result shape (always returned as advisory, never blocking):
      None                                     — hook didn't apply
      {"action": "post", "issue": "<n>", ...}  — comment posted
      {"action": "skip_meta_issue", ...}       — meta-issue skipped
      {"action": "skip_idempotent", ...}       — kickoff already posted
      {"action": "skip_no_scope", ...}         — wave_{M}_scope missing
      {"action": "skip_no_row", ...}           — issue not in any tier
      {"action": "skip_post_failed", ...}      — gh post call failed

    Injection points let tests mock external state without mocking
    subprocess: `status_loader()` returns the status dict, `comment_fetcher
    (repo, num)` returns the comment list, `comment_poster(repo, num, path)`
    returns success bool, `body_writer(body, repo, num)` returns the Path
    of the written body file.
    """
    if input_data.get("tool_name", "") != "Bash":
        return None

    command = input_data.get("tool_input", {}).get("command", "")
    if not command:
        return None

    parsed = parse_label_apply_command(command)
    if parsed is None:
        return None
    repo, issue_number, wave_label = parsed

    m = _WAVE_LABEL_RE.match(wave_label)
    if m is None:
        return None
    phase_num = int(m.group(1))
    wave_num = int(m.group(2))

    status = (status_loader or _read_status)()
    if status is None:
        log_posttooluse_event(
            "post_wave_kickoff_comment",
            command,
            "cross-repo-status.json missing or malformed; cannot resolve assignment row.",
        )
        return {"action": "skip_no_scope", "repo": repo, "issue": issue_number}

    # Meta-issue skip: this hook is for per-issue kickoff; the meta-issue
    # gets a different all-hands comment owned by /wave-kickoff Step 8b.
    meta = status.get(f"wave_{wave_num}_meta_issue")
    if meta is not None and str(meta) == issue_number and repo == "noorinalabs-main":
        return {"action": "skip_meta_issue", "repo": repo, "issue": issue_number}

    scope = status.get(f"wave_{wave_num}_scope")
    if not scope:
        log_posttooluse_event(
            "post_wave_kickoff_comment",
            command,
            (
                f"wave_{wave_num}_scope is missing or empty in cross-repo-status.json; "
                f"cannot render kickoff comment for {repo}#{issue_number}."
            ),
        )
        return {"action": "skip_no_scope", "repo": repo, "issue": issue_number}

    row = find_assignment_row(status, repo, issue_number, wave_num)
    if row is None:
        log_posttooluse_event(
            "post_wave_kickoff_comment",
            command,
            (
                f"No assignment row found in wave_{wave_num}_scope tiers for "
                f"{repo}#{issue_number}. /wave-scope may have missed this issue."
            ),
        )
        return {"action": "skip_no_row", "repo": repo, "issue": issue_number}

    # Idempotency: don't double-post.
    if kickoff_already_posted(repo, issue_number, fetch_comments=comment_fetcher):
        return {"action": "skip_idempotent", "repo": repo, "issue": issue_number}

    body = render_kickoff_comment(row, wave_num, phase_num, repo)
    writer = body_writer or _write_fresh_body_file
    body_path = writer(body, repo, issue_number)

    poster = comment_poster or _gh_post_comment
    success = poster(repo, issue_number, body_path)
    if not success:
        log_posttooluse_event(
            "post_wave_kickoff_comment",
            command,
            f"gh issue comment failed for {repo}#{issue_number} (body at {body_path}).",
        )
        return {"action": "skip_post_failed", "repo": repo, "issue": issue_number}

    return {
        "action": "post",
        "repo": repo,
        "issue": issue_number,
        "wave_label": wave_label,
        "body_path": str(body_path),
    }


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    try:
        check(input_data)
    except Exception as e:  # noqa: BLE001
        # PostToolUse hooks are advisory — never raise. Log the unexpected
        # error and exit clean. The label apply has already succeeded.
        try:
            log_posttooluse_event(
                "post_wave_kickoff_comment",
                input_data.get("tool_input", {}).get("command", "")[:500],
                f"Unexpected hook error: {type(e).__name__}: {e}",
            )
        except Exception:
            pass
    sys.exit(0)


if __name__ == "__main__":
    main()
