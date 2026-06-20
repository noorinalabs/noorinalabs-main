---
name: feedback_verdict_amendment_edit_not_append
description: To retrofit TechDebt onto a posted PR review verdict, edit the original Approved/ChangesRequested comment — a new amendment comment does NOT supersede the original for hook-gate purposes.
type: feedback
originSessionId: 52b75b4f-2d1e-4024-b6db-e384bc5f8904
---
When a reviewer posts an `Approved` (or `ChangesRequested`) comment on a PR without the mandatory `TechDebt:` attestation line, and the merge is blocked by `validate_pr_review`, the fix is to **EDIT the original verdict comment to add the line**. Posting a NEW Approved comment that contains the TechDebt line does NOT satisfy the gate.

**Why:** `validate_pr_review.py` (lines 348-354 at 5ce4dce HEAD) iterates every verdict comment in the PR and appends the reviewer's name to `reviews_missing_tech_debt` if ANY of their verdict comments lacks the TechDebt regex. Two Approved comments by one reviewer = both scanned; one without TechDebt = reviewer flagged. The block message reports reviewer names, not specific comment IDs, which masks this from the operator. The hook reads current comment body via `gh api`, so edits ARE picked up on re-scan — that's the path that works.

**How to apply:**

1. Identify the original verdict comment ID(s) via `gh api repos/<o>/<r>/issues/<pr>/comments --jq '.[] | select(.body | contains("RequestOrReplied: Approved")) | {id, body_head: (.body | split("\n")[0:3])}'`.
2. For each missing-TechDebt verdict comment, fetch body, append `\n\nTechDebt: #N[, #M, ...]\n`, PATCH via `gh api -X PATCH repos/<o>/<r>/issues/comments/<id> --input /tmp/patch.json` where the JSON wraps `{"body": <new-body>}`. Do NOT use `--field body=...` (memory `feedback_gh_pr_edit_silent_noop`).
3. Verify post-edit by re-running the audit query and confirming every verdict comment now matches `TechDebt: .+`.
4. Retry the merge.

When the same gh credentials are shared across reviewers (e.g., all teammates use the orchestrator's `parametrization` login), the orchestrator can edit the comments directly — this is mechanical relocation of the reviewer's own attestation, not ghost-writing. When reviewers use distinct GitHub accounts, send the edit instructions back via `SendMessage`.

**Also applies when the PR HEAD changes after you've approved (P3W15 deploy#396, 2026-06-02):** re-reviewing a post-fix head must EDIT the original Approved comment to state it covers the new head — NOT post a fresh post-fix Approved. Posting a second one creates the same two-verdicts-one-reviewer state; if you've already done so, neutralize the redundant comment (strip its RequestOrReplied/TechDebt fields, leave a "superseded, consolidated above" pointer) so exactly one of your comments carries `RequestOrReplied: Approved`. Read-back-verify the count == 1.

**Original W8-retro PR #371 trigger (2026-05-11):** Both reviewers (Aino, Wanjiku) posted Approved-without-TechDebt comments. Orchestrator's first remediation attempt was "post a new Approved comment with TechDebt line" — that doubled the verdict count but left both originals still flagging the gate. Second attempt edited the originals; merge passed. Sibling lesson: `feedback_validate_pr_review_approved_not_reply.md` (Approved-vs-Reply distinction) — same hook, related gate semantics.
