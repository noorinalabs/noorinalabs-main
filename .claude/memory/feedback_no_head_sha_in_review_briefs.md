---
name: feedback_no_head_sha_in_review_briefs
description: Don't bake a head SHA into a review spawn brief — send the PR number. The reviewer must re-confirm head at post time anyway, so a baked SHA adds a stale anchor without adding safety.
metadata:
  type: feedback
last_verified: 2026-08-11
---

Wave-30, PR #1388: the orchestrator baked `ReviewedHead: 878a658b…` into both
reviewers' spawn briefs. The author then pushed two more commits during review
(`878a658b` → `ad8a50de` → `83f54f81`). The orchestrator sent a correction naming
`ad8a50de` — which was **itself already stale**, because the correction was
written from a cached read rather than a fresh one. Both SHAs handed to the
reviewer were stale on arrival.

The merge-gate reviewer's feedback, accepted verbatim:

> Send the PR number and let the reviewer resolve head. I have to re-confirm it
> immediately before posting anyway, per evidence-standards, so a SHA in the brief
> adds a stale anchor without adding safety.

**Why:** charter `pull-requests/evidence-standards.md` already requires a reviewer
to record and confirm the head they certify, and makes a verdict stale if the PR
is force-pushed after it. That obligation sits with the reviewer at post time. An
orchestrator-supplied SHA can only be *older* than what the reviewer will resolve —
it is a second, worse source of truth for a fact the reviewer must establish
independently. In the observed case the good reviewer ignored it and certified past
it; a compliant one would have certified a head two commits behind.

**How to apply:**

- Review briefs name the **PR number**, never a head SHA. Say "re-confirm current
  head yourself and record it in `ReviewedHead:`".
- If a brief must reference a specific commit (e.g. "the fix is in the first
  commit, the rest are docs"), describe it by role, not as the head to certify.
- The same rule applies to correcting a brief mid-review: do not send a new SHA,
  send the fact that head moved and let the reviewer re-resolve.
- Corollary for the orchestrator's own status reporting: a head SHA read minutes
  ago is not current. Re-read before asserting anything keyed to it. Cf.
  [[feedback_graphql_quota_ceiling_on_agent_fanout]] on why cached reads mislead,
  and [[feedback_verify_before_claim]].

Related: [[feedback_owner_merge_gate_review_first]], [[feedback_pr_number_placeholders]].
