---
name: feedback_reviewer_correction_vs_merge_race
description: "When a reviewer is amending a verdict comment (Edit-not-append) and the orchestrator merges before the edit lands, Hook 4 evaluates the pre-correction state. Pause-merge-until-edit-verified is the safer cadence."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 0be57897-3749-48b2-8850-f155e5434000
---

Before merging a PR with an in-flight reviewer correction, pause the merge until the corrected verdict-comment has been re-fetched at origin AND its `updated_at` timestamp confirms the edit landed.

**Why:** P3W10 2026-05-16, PR #444 — Santiago Ferreira amended his verdict comment (Edit-2, retraction of a false-positive observation) at `22:02:53Z`. The orchestrator (team-lead) merged the PR at `22:02:26Z`, which means Hook 4 evaluated the comment at the Edit-1 state — still containing the false-positive — **27 seconds before the correction landed**. The verdict outcome (Approved/TechDebt:none) was stable across all 3 versions of the comment so the gating result was unaffected, but the principle generalizes: if a reviewer were correcting from Changes-Requested → Approved (or vice versa), racing the merge against the edit would mean the hook sees the wrong gating signal.

The canonical-comment-at-HEAD post-merge IS correct (because EDIT not APPEND was used, the artifact's final state at origin reflects the correction). The race is purely between the merge event AND the edit landing — not between the comment-edit and a downstream append.

**How to apply:**

- When a reviewer is mid-correction (you've received SendMessage signal that they're editing, OR you see a comment with `created_at` that doesn't match the body shape they reported), pause the merge until `gh api repos/.../issues/comments/<ID> --jq '.updated_at'` matches the expected post-edit timestamp.
- Treat reviewer SendMessage "I'm editing the comment to fix X" as a supersedes-as-of header (per `feedback_owner_pivot_supersedes_protocol` discipline applied at the reviewer-vs-orchestrator boundary). Refresh state at origin before acting on the pre-edit comment.
- If the merge has already fired and the correction lands seconds later, the situation is recoverable IF the verdict-outcome was stable across the edit (no harm done, just a transient hook-eval-on-wrong-state). If the verdict-outcome would have CHANGED, the merge is at minimum a process violation and at maximum needs a revert-then-redo cycle.
- For high-stakes PRs (security-sensitive, breaking-change-class), the discipline tightens: do not merge until ALL reviewer-side amendments have landed AND been re-verified at origin via `updated_at`.

**Sibling rules:** [[feedback_owner_pivot_supersedes_protocol]] (same primitive at owner-pivot-on-in-flight-task layer), [[feedback_verdict_amendment_edit_not_append]] (the EDIT-not-APPEND discipline that makes post-merge canonical-state correct even when the eval-time state was wrong), [[feedback_refresh_before_status_claim]] (eval-time-state-at-origin discipline).

**Severity:** Minor when verdict-outcome is stable across the edit (the case observed in #444). Moderate when the edit would change the verdict (would have been a hook-eval false-positive merge). Severe when applied to a breaking-change-class PR.

**Origin:** P3W10 PR #444 charter-adoption merge 2026-05-16. Santiago Ferreira self-surfaced the timing observation after his Edit-2 landed 27s post-merge.
