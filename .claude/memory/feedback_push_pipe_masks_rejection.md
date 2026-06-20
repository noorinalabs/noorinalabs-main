---
name: feedback_push_pipe_masks_rejection
description: "Piping `git push` (esp. `--force-with-lease`) through tail/head/grep masks a REJECTED push — the pipeline exit status is the pager's 0, not git's failure. Agent believes it pushed when it didn't. Verify push success explicitly."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: b923c0f4-c87a-4bed-b4b8-91a79287509b
---

`git push ... --force-with-lease | tail` (or `| head`, `| grep`) **hides a rejected push**: the shell pipeline's exit status is the LAST command's (tail = 0), so a non-fast-forward / stale-lease rejection from git reads as success. The agent then believes the branch is updated when the remote still has the old head — and a downstream "PR is green" claim is made against an unpushed tree.

**Why:** P5W4 ig#1044 (Ingrid Lindqvist) — `git push --force-with-lease | tail` returned 0 while the push was actually rejected; only caught because the head didn't move on re-check. Same family as [[feedback_gh_pr_edit_silent_noop]] (silent no-op tooling).

**How to apply:**
- Never pipe `git push` through a pager/filter. Run it bare so its exit code surfaces, or capture: `git push ... ; echo "rc=$?"` and assert rc==0.
- After any force-push, read-back-verify: `git ls-remote origin <branch>` (or `gh api .../git/refs/heads/<branch>`) == local HEAD before claiming the PR reflects your latest commit. Pairs with [[feedback_refresh_before_status_claim]].
- `set -o pipefail` does NOT fully save you here — `tail` still exits 0 after consuming git's stderr; the real fix is don't pipe the push.
