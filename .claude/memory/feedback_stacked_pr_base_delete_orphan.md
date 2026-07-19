---
name: feedback_stacked_pr_base_delete_orphan
description: A PR stacked on another PR's feature branch is auto-CLOSED (and cannot be reopened/retargeted) when the base PR merges with --delete-branch; retarget the stacked PR to the wave branch BEFORE the base merges, or accept a fresh superseding PR.
metadata:
  type: feedback
---

When PR-B is stacked on PR-A's **feature branch** (B's base = A's head ref, not the wave branch), merging A with `--delete-branch` deletes that head ref and GitHub **auto-CLOSES B** — its base branch no longer exists. GitHub then refuses to reopen OR retarget a closed PR whose base branch was deleted (422 both ways; `gh pr edit --base` also trips the projectCards GraphQL bug). The only recovery is a **fresh PR** from B's (already-rebased) branch targeting the wave branch directly — a new PR number.

**Why:** P9W25 — #457 (da#347) was stacked on #455's branch `I.Horvat/0431-kunya-ism-bio-merge`. Merging #455 with `--merge --delete-branch` orphaned+closed #457; Ivana reopened it as **#459** targeting `deployments/phase-9/wave-25` directly (rebased onto merged-#455, 11/11 green). No data lost, but the PR number churned and prior review context did not carry.

**How to apply:**
- **Prevent:** in a stacked-PR chain, retarget the downstream PR's base to the **wave branch** BEFORE the upstream PR merges+deletes its branch. Then the delete is harmless.
- **Or:** don't stack on feature branches at all when the wave uses the wave-branch merge model — base each per-issue PR on `deployments/phase-{P}/wave-{M}` from the start (composition is verified by rebasing/merging, not by stacking base refs).
- **Recover:** if it already orphaned, open a fresh PR from the same branch to the wave branch; it SUPERSEDES the closed one. Re-run the 2-reviewer gate on the new number, and tell reviewers explicitly "review #NEW, not #OLD."
- Do NOT chase reopening the closed PR — GitHub will not allow it once the base ref is gone.

Relates to [[feedback_wave_branch_merge_not_squash]] (wave-branch per-issue PRs use --merge), [[feedback_pr_number_placeholders]] (verify the live PR number post-create).
