#!/usr/bin/env python3
"""PreToolUse hook: Block `gh pr merge` if CI is not green.

Queries `gh pr view --json statusCheckRollup` and blocks merge when any
required check has failed, been cancelled, timed out, or requires action.
Pending checks block unless the user passes `--auto` (warn-but-allow).

Input Language
==============

Fires on:      PreToolUse Bash
Matches:       gh pr merge [{N}] [--repo {OWNER/REPO}] [--squash|--merge|--rebase]
                           [--admin] [--auto] (chained via &&/||/|/; OK; leading
                           env-var assignments stripped)
Does NOT match: gh pr list, gh pr view, gh pr checks, gh pr create, gh pr edit,
                git merge, git pull.
Flag pass-through:
    --repo  → forwarded to `gh pr view`
    --admin → validated against the charter admin-merge exception list (see
              "Admin-merge exception validation" below) — NO LONGER an
              unconditional short-circuit
    --auto  → permits pending checks (GitHub auto-merge on green)

Admin-merge exception validation (main#322 — P3 end-state criterion #4)
======================================================================

Org-wide branch-protection rulesets (main#322) let the **Repository admin**
role bypass the GitHub-side required-status-checks gate. That bypass is what
keeps our merge flow working (we use issue-comment verdicts, not GitHub
formal reviews, and the orchestrator merges wave→main with `--admin`). But an
unconditional, unlogged `--admin` short-circuit is exactly the silent escape
hatch criterion #4 exists to close ("--admin merge usage is hook-blocked OR
auditable + reviewed at retro time; charter exceptions are formally listed
and validated at PR-merge hook time").

So `--admin` no longer allows unconditionally. It requires an
`ADMIN_MERGE_EXCEPTION` env var of the form `<class>:<rationale>`, where
`<class>` is one of the charter-listed exception classes
(`_CHARTER_ADMIN_EXCEPTIONS`) and `<rationale>` is a non-empty justification.
The use is logged (via `log_pretooluse_block`, which doubles as the audit
trail the retro reads). An absent or unrecognized exception **blocks** —
fail-safe per `feedback_safety_direction_over_ux_friction` (a broken-but-
blocking gate fails in the safe direction; a silent allow does not).

The exception classes mirror `charter/pull-requests.md` and
`charter/emergency-mode.md`:
    wave-bootstrap → § Single-Reviewer Exception (Wave-Bootstrap Only)
    doc-sweep      → § Trivial Cross-Repo Doc Sweep
    wave-merge     → the wave→main wrapup merge (orchestrator-merged)
    emergency      → § Emergency Mode (`[EMERGENCY]`-prefixed restore work)

NEUTRAL conclusion semantics (resolves #219)
============================================

GitHub's Checks API uses `NEUTRAL` to mean "the check has no opinion." For
most checks this is correctly treated as a pass (e.g., a workflow that
explicitly returns `neutral` because a precondition was not met). However,
**Chromatic** (the dominant visual-regression service for Storybook-based
component libraries) returns `NEUTRAL` on snapshots-pending-review — a state
where the check is structurally not-finished even though GitHub's status
field reports COMPLETED. Treating that as pass would let `gh pr merge`
through while visual-regression review is still pending — defeating the
gate's purpose.

The `_NEUTRAL_PENDING_CHECK_PREFIXES` allowlist below names CheckRun
display-name PREFIXES whose `NEUTRAL` conclusion is treated as **pending**
instead of pass. Match is a case-insensitive `startswith` on the check's
display name (per `check_name`), so multi-step shapes like
`Chromatic / Visual` match the `chromatic` prefix (#262). Any check whose
name does not start with an allowlisted prefix preserves the prior
`NEUTRAL → pass` behavior.

Add a new entry when a service uses `NEUTRAL` to mean "review pending"
rather than "no opinion." Charter `pull-requests.md § CI Must Be Green`
governs the rule; this allowlist is the operational mapping.

Exit codes:
  0 — allow (not a merge command, validated --admin exception, or all checks green)
  2 — block (failing/pending checks without --auto, or --admin without a valid
      charter exception)
"""

import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _repo_flag_parse import extract_repo
from annunaki_log import log_pretooluse_block

# Charter-listed admin-merge exception classes (main#322). An `--admin` merge
# must declare one of these via `ADMIN_MERGE_EXCEPTION=<class>:<rationale>`.
# Keep in lockstep with `charter/pull-requests.md` + `charter/emergency-mode.md`.
_CHARTER_ADMIN_EXCEPTIONS = {
    "wave-bootstrap": "Single-Reviewer Exception (Wave-Bootstrap Only)",
    "doc-sweep": "Trivial Cross-Repo Doc Sweep",
    "wave-merge": "wave→main wrapup merge (orchestrator-merged)",
    "emergency": "Emergency Mode ([EMERGENCY]-prefixed restore work)",
}

# Conclusion values that unambiguously indicate a failed check.
_FAILURE_CONCLUSIONS = {
    "FAILURE",
    "CANCELLED",
    "TIMED_OUT",
    "ACTION_REQUIRED",
    "STARTUP_FAILURE",
}

# Status values that indicate the check has not finished yet.
_PENDING_STATUSES = {"QUEUED", "IN_PROGRESS", "WAITING", "PENDING", "REQUESTED"}

# Bucket values (GitHub check rollup) that map to pass/fail.
_FAIL_BUCKETS = {"fail"}
_PASS_BUCKETS = {"pass", "skipping"}

# CheckRun name PREFIXES whose `NEUTRAL` conclusion is treated as PENDING,
# not PASS (resolves #219; broadened from exact-match per #262). Match is
# case-insensitive `startswith` on the check's display name. Add entries
# here when a service uses NEUTRAL to mean "review pending" rather than "no
# opinion." Currently:
#
#   chromatic — Visual-regression CI (Storybook snapshots). Returns NEUTRAL
#               while snapshots are pending owner review; treating as pass
#               lets visual changes merge un-reviewed.
#
# #262 (forward gap): when design-system actually wires Chromatic into
# `storybook.yml`, the GitHub Actions check name may surface as a
# multi-step shape (`Chromatic / Visual`, `chromatic-visual`, …). v1 used a
# case-insensitive EXACT-string set against `{"chromatic"}`, which those
# shapes would NOT match — silently re-opening the #219 NEUTRAL-bypass gap.
# Switching to a PREFIX match (issue option 2) catches the multi-step
# shapes now, without waiting on the Chromatic wiring to land. Trade-off:
# a non-Chromatic check whose name happens to start with one of these
# prefixes would be pend-classified; the prefixes are kept distinctive
# (`chromatic`) to keep that risk negligible — fails SAFE (a false pend
# blocks a merge that an operator then inspects, vs. a false pass that
# slips an unreviewed visual change through).
_NEUTRAL_PENDING_CHECK_PREFIXES = ("chromatic",)


def is_merge_command(command: str) -> bool:
    """Check if the command is a gh pr merge invocation, including chained commands."""
    for segment in re.split(r"\s*(?:&&|\|\||\||;)\s*", command):
        stripped = segment.lstrip()
        while re.match(r"[A-Za-z_][A-Za-z0-9_]*=\S*\s+", stripped):
            stripped = re.sub(r"^[A-Za-z_][A-Za-z0-9_]*=\S*\s+", "", stripped)
        if re.match(r"gh\s+pr\s+merge\b", stripped):
            return True
    return False


def validate_admin_exception(input_data: dict) -> dict | None:
    """Validate an `--admin` merge against the charter exception list (main#322).

    Returns None when the admin merge is authorized (a recognized exception
    class with a non-empty rationale) — the caller then allows the merge.
    Returns a block result dict when the exception is absent or unrecognized,
    so an undeclared `--admin` fails safe instead of silently bypassing the
    gate. The authorized case is logged too, so the retro has an audit trail
    of every admin-merge exception used during a wave.
    """
    raw = (input_data.get("env", {}) or {}).get("ADMIN_MERGE_EXCEPTION")
    if raw is None:
        raw = os.environ.get("ADMIN_MERGE_EXCEPTION", "")
    raw = (raw or "").strip()

    cls, sep, rationale = raw.partition(":")
    cls = cls.strip()
    rationale = rationale.strip()
    valid_list = ", ".join(sorted(_CHARTER_ADMIN_EXCEPTIONS))

    if not sep or cls not in _CHARTER_ADMIN_EXCEPTIONS or not rationale:
        return {
            "decision": "block",
            "reason": (
                "BLOCKED: `--admin` merge requires a charter-listed exception. "
                'Set ADMIN_MERGE_EXCEPTION="<class>:<rationale>" before merging, '
                f"where <class> is one of: {valid_list}, and <rationale> is a "
                "non-empty justification (logged for retro audit per main#322).\n"
                "Charter: pull-requests.md § Single-Reviewer Exception / § Trivial "
                "Cross-Repo Doc Sweep / § CI Must Be Green Before Merge; "
                "emergency-mode.md § Allowed bypasses.\n"
                f"Received ADMIN_MERGE_EXCEPTION={raw!r}."
            ),
        }
    return None


def extract_pr_number(command: str) -> str | None:
    """Extract PR number from gh pr merge command."""
    match = re.search(r"\bgh\s+pr\s+merge\s+(\d+)", command)
    if match:
        return match.group(1)
    match = re.search(r"/pull/(\d+)", command)
    if match:
        return match.group(1)
    return None


def fetch_checks(pr_number: str | None, repo: str | None) -> list[dict] | None:
    """Fetch statusCheckRollup entries for the PR. Returns None on failure."""
    try:
        cmd = ["gh", "pr", "view"]
        if pr_number:
            cmd.append(pr_number)
        if repo:
            cmd.extend(["--repo", repo])
        cmd.extend(["--json", "statusCheckRollup"])
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        rollup = data.get("statusCheckRollup", [])
        if not isinstance(rollup, list):
            return None
        return rollup
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return None


def classify_check(check: dict) -> str:
    """Return 'fail', 'pending', or 'pass' for a single check entry.

    NEUTRAL conclusion handling (resolves #219; prefix match per #262):
    CheckRuns whose display name starts with an allowlisted prefix in
    `_NEUTRAL_PENDING_CHECK_PREFIXES` (case-insensitive `startswith`) treat
    NEUTRAL as 'pending' rather than 'pass'. All other checks preserve the
    prior NEUTRAL → pass behavior. See module docstring for the allowlist's
    rationale.
    """
    bucket = (check.get("bucket") or "").lower()
    conclusion = (check.get("conclusion") or "").upper()
    status = (check.get("status") or check.get("state") or "").upper()

    if bucket in _FAIL_BUCKETS or conclusion in _FAILURE_CONCLUSIONS:
        return "fail"
    if status in _PENDING_STATUSES or conclusion == "":
        # Completed with no conclusion is treated as success; truly pending
        # checks have status != COMPLETED.
        if status == "COMPLETED":
            return "pass"
        return "pending"
    # NEUTRAL allowlist: CheckRuns whose name starts with an allowlisted
    # prefix treat NEUTRAL as pending (#219; prefix match per #262).
    if conclusion == "NEUTRAL":
        name_lc = check_name(check).lower()
        if any(name_lc.startswith(p) for p in _NEUTRAL_PENDING_CHECK_PREFIXES):
            return "pending"
    if bucket in _PASS_BUCKETS or conclusion in {"SUCCESS", "NEUTRAL", "SKIPPED"}:
        return "pass"
    return "pass"


def check_name(check: dict) -> str:
    """Best-effort display name for a check."""
    return check.get("name") or check.get("context") or check.get("workflowName") or "<unnamed>"


def check_url(check: dict) -> str:
    """Best-effort URL for a check."""
    return check.get("detailsUrl") or check.get("targetUrl") or ""


def format_check_list(checks: list[dict]) -> str:
    lines = []
    for c in checks:
        name = check_name(c)
        conclusion = (c.get("conclusion") or c.get("status") or "").lower() or "unknown"
        url = check_url(c)
        suffix = f" ({url})" if url else ""
        lines.append(f"  - {name} [{conclusion}]{suffix}")
    return "\n".join(lines)


def check(input_data: dict) -> dict | None:
    """Check PR CI status. Returns result dict if blocking, None if allowed."""
    tool_name = input_data.get("tool_name", "")
    if tool_name != "Bash":
        return None

    command = input_data.get("tool_input", {}).get("command", "")

    if not is_merge_command(command):
        return None

    if "--admin" in command:
        # main#322: `--admin` no longer short-circuits unconditionally. It must
        # name a charter-listed exception via ADMIN_MERGE_EXCEPTION, else block.
        exception_block = validate_admin_exception(input_data)
        if exception_block is not None:
            log_pretooluse_block("validate_pr_ci_status", command, exception_block["reason"])
            return exception_block
        # Authorized exception — allow, but log the use for retro audit.
        raw = (input_data.get("env", {}) or {}).get("ADMIN_MERGE_EXCEPTION") or os.environ.get(
            "ADMIN_MERGE_EXCEPTION", ""
        )
        log_pretooluse_block(
            "validate_pr_ci_status",
            command,
            f"ADMIN-MERGE EXCEPTION AUTHORIZED (audit): {raw.strip()}",
        )
        return None

    pr_number = extract_pr_number(command)
    repo = extract_repo(command)
    rollup = fetch_checks(pr_number, repo)

    pr_display = f"#{pr_number}" if pr_number else "(current branch)"

    if rollup is None:
        return {
            "decision": "allow",
            "systemMessage": (
                f"WARNING: Could not verify CI status for PR {pr_display}. "
                "Ensure all checks are green before merging."
            ),
        }

    if not rollup:
        # Empty statusCheckRollup — no CI checks have run. Root cause of
        # deploy#153 (workflow orphan): no on.pull_request trigger covers
        # this branch/paths, so the merge gate has nothing to evaluate.
        # Allow (preserves prior behavior; behavior change requires charter
        # decision per #307), but warn so the operator can investigate.
        return {
            "decision": "allow",
            "systemMessage": (
                f"WARNING: PR {pr_display} has no CI checks (empty statusCheckRollup). "
                "This usually means no workflow's on.pull_request trigger covers this PR. "
                "Verify the workflow coverage via `validate_workflow_paths_coverage` or "
                "`gh pr checks` before merging — silent absence of CI ≠ green CI.\n"
                "See deploy#153 for the root-cause incident pattern."
            ),
        }

    failing: list[dict] = []
    pending: list[dict] = []
    for entry in rollup:
        verdict = classify_check(entry)
        if verdict == "fail":
            failing.append(entry)
        elif verdict == "pending":
            pending.append(entry)

    if failing:
        result = {
            "decision": "block",
            "reason": (
                f"BLOCKED: PR {pr_display} has {len(failing)} failing CI check(s). "
                "Charter § Pull Requests requires green CI before merge.\n"
                f"Failing checks:\n{format_check_list(failing)}\n\n"
                "Fix the failures and re-run, or pass `--admin` for emergency overrides only."
            ),
        }
        log_pretooluse_block("validate_pr_ci_status", command, result["reason"])
        return result

    if pending:
        if "--auto" in command:
            return {
                "decision": "allow",
                "systemMessage": (
                    f"WARNING: PR {pr_display} has {len(pending)} pending CI check(s); "
                    "`--auto` will let GitHub merge when they finish.\n"
                    f"{format_check_list(pending)}"
                ),
            }
        result = {
            "decision": "block",
            "reason": (
                f"BLOCKED: PR {pr_display} has {len(pending)} pending CI check(s). "
                "Wait for CI to finish, pass `--auto` to let GitHub merge on green, "
                "or pass `--admin` for emergency overrides.\n"
                f"Pending checks:\n{format_check_list(pending)}"
            ),
        }
        log_pretooluse_block("validate_pr_ci_status", command, result["reason"])
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
