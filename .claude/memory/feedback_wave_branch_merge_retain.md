---
name: feedback_wave_branch_merge_retain
description: Wave-branch model — EACH wave merges to main at its own /wave-wrapup (not final-wave-only); phase/wave branches are RETAINED (never deleted).
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 080813cd-f3b8-434d-974c-badf58620c96
---

Owner directives 2026-06-09, two parts:

1. **Each wave merges to main at its own `/wave-wrapup`** — not "final wave only." The skill's Step 11/11.5 were previously gated to the final wave; that was inconsistent with `/wave-start` Step 3, which already bases every wave off `main` (`git checkout main && pull` then branch). Under that base-off-main flow, an unmerged wave strands its work the moment the next wave starts — so the merge must happen every wave. Evidence at change time: P4 `deployments/phase-4/wave-1` was 21 ahead / 0 behind main, unmerged, while prior P3 waves showed ahead=0 (merged).

2. **Phase/wave branches are RETAINED (never deleted)** — merge each wave→main PR with `gh pr merge <N> --merge` (NOT `--delete-branch`). The `deployments/phase-{P}/wave-{M}` branches are a permanent historical / rollback anchor. Feature/worktree branches (`F.Last/NNNN-*`) are still deleted normally; the retain rule applies ONLY to the `deployments/phase-*/wave-*` branches.

**How to apply:**
- `/wave-wrapup` Step 11 (header "every wave" + retain-branch paragraph), Step 11.5 (header "every wave"), Step 8 worktree-cleanup guard (never delete a `deployments/phase-*/wave-*` branch).
- `/wave-start` Step 2 — wave N>1 bases off `main` (prior wave already merged); prior-wave-branch retained only as a safety-net reference, not the base.
- `delete_branch_on_merge` is **false** on all 8 repos (verified 2026-06-09), so a merge will not auto-delete the wave branch — retain is safe with no repo-setting change. If ever flipped true, the wave branch dies on merge regardless of `--delete-branch`, so keep it false.
- Landed via main#620 / PR (process change). Companion to [[feedback_td_intake_20pct_per_wave]] (same session's wave-process changes).
