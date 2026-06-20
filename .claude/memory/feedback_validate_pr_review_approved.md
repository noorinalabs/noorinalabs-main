---
name: feedback_validate_pr_review_approved
description: 2-reviewer merge gate hook counts distinct Requestor across `RequestOrReplied: Approved` comments only. `Reply` doesn't register even if body says "Approved." Spawn briefs must specify `Approved` for gating posts.
type: feedback
originSessionId: 3d519c58-11df-4e60-ba09-74c7024fc9f1
---
The `validate_pr_review` hook (`.claude/hooks/validate_pr_review.py`, lines 242–251 + 282–298) gates `gh pr merge` on **distinct `Requestor:` values across `RequestOrReplied: Approved` comments only**. `Reply` / `Replied` / `Request` / `ChangesRequested` do NOT contribute to the 2-reviewer threshold. The hook parses the `RequestOrReplied:` field directly — body prose is not inspected for verdict signals like "Approved" or "looks good."

Charter ref: `pull-requests.md § Comment-Based Reviews`, resolves `noorinalabs-main#244`.

Single-reviewer exception: PRs labeled `wave-bootstrap` permit merge with one distinct `Approved` comment (hook lines 411, 509). Same `Approved`-only semantics — `Reply` still doesn't count.

Wave-wide canonical pointer: `noorinalabs-main#309` comment 4410998521 (P3W8 cascade-prevention guidance, 2026-05-09).

**Why:** P3W8 wave 2026-05-09 — orchestrator's spawn briefs specified `RequestOrReplied: Reply` for approval comments. Cascade hit ~17 addenda across 11 PRs (#75 first, then #281 / #282 / #48 / #49 / #89 / #90 / #91 / #334 / #338 / #340 cascade). Maeve.Callahan caught it during PR#75 R2 review when the merge gate blocked despite both reviewers having posted substantive `Reply`s with Approved-flavored bodies. Bereket nearly hit it on #281 squash-merge attempt — pre-empted by wave-wide guidance comment.

**How to apply:**

1. **Spawn briefs MUST specify `RequestOrReplied: Approved` for gating reviewer posts.** `Reply` is for substantive critique that does not gate merge. Audit your own spawn brief language before sending.
2. **Reviewers**: prefer `Approved` directly (Shape A: combined verdict + prose). If separating substantive `Reply` from gating `Approved` (Shape B), post both and link the Reply from the Approved.
3. **Managers — pre-merge check (Step 4 in the wave-wide guidance, earned by Bereket #281 cycle 2026-05-09)**: before `gh pr merge`, run

   ```bash
   COUNT=$(gh api repos/<owner>/<repo>/issues/<pr>/comments \
     --jq '[.[] | select(.body | contains("RequestOrReplied: Approved"))] | length')
   [ "$COUNT" -ge 2 ] || echo "BLOCKED: only $COUNT Approved; need 2 (or 1 with wave-bootstrap)"
   ```

   Earliest manager-controlled checkpoint. Replaces "manager memory of did-I-see-Approved" with artifact count at HEAD. If count is short, request addenda BEFORE attempting `gh pr merge` — saves the hook-block round-trip + chase-down cycle. The hook block is the late signal; this is the early one. Wave-wide canonical extension at `noorinalabs-main#309` comment 4411006092.
4. **For addendum cycles**: `gh pr comment <N> --body-file .claude/scratch/<N>-approved-addendum.md` (per `feedback_tmp_msg_file_stale.md`); read-back-verify within 30s per `feedback_gh_pr_edit_silent_noop.md`.
5. Every verdict comment (`Approved` + `ChangesRequested`) needs `TechDebt: <none|#N>` per `feedback_reviewer_techdebt_line_required.md` — including the addendum-class `Approved` post.
6. **BEFORE spawning reviewers, scan PR *issue-comments* for existing verdict blocks — NOT `gh pr view --json reviews`.** Comment-based verdicts do NOT appear in `.reviews` (that field stays `[]`), so a PR can read "0 reviews" while already carrying 2 valid `RequestOrReplied: Approved` comments. Use the point-3 `gh api .../issues/<pr>/comments` count. P5W5 2026-06-17: lp#140 was already reviewed by Anika+Marcia in a *prior (crashed) session*; I checked `.reviews` (empty), declared "0 reviews," and spawned redundant reviewers. Crashed-session leftover risk: the stale Anika verdict was missing its `TechDebt:` line (would have blocked the merge); remediated by **editing that comment in place** to append a `---` + trailer block (a new comment does NOT clear a sibling verdict's missing-TechDebt flag — the hook scans ALL comments). See `feedback_verdict_amendment_edit_not_append.md`. **Durable fix (enforcement hierarchy):** main#707 — a `.claude/lib/pr_review_state.py` CLI that imports `check_comment_reviews()` and reports distinct Approved reviewers + any verdict missing TechDebt, exit-coded to the gate. Run it before spawning reviewers AND before `gh pr merge`; the bash count in point 3 is the interim form until #707 lands.

**Sister memories** (artifact-grounded discipline family):
- `feedback_pre_spawn_verify_at_origin.md` — verify spawn-brief premises against origin head_sha.
- `feedback_pre_spawn_brief_verified_at_head.md` — enumerate from wave-branch HEAD + rule each caveat applicable/non-applicable.
- `feedback_review_against_artifact_not_framing.md` — review against PR diff at head, not body framing.
- `feedback_origin_over_local_for_still_has_claims.md` — file-content assertions via `gh api .../contents` not local clone.

This memory is the "verify-charter-format-rule-references-against-actual-hook-semantics" entry — a sibling to those four. The shared umbrella: **trust the artifact / source / hook semantics, not the framing or spawn-brief language.**
