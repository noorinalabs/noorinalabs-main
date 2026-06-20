---
name: feedback_update_branch_async_window
description: gh pr update-branch (REST PUT) is async — re-fetch head_sha after the call before reading downstream state
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 0cb4f25c-efad-48d9-a1a3-3264ad55369c
---

`gh api -X PUT repos/<owner>/<repo>/pulls/<N>/update-branch` returns `{"message":"Updating pull request branch."}` and a 202 immediately. The merge-from-main commit lands **asynchronously** server-side. A `gh pr view <N> --json headRefOid` call issued seconds later will sometimes report the OLD head sha (pre-update-branch) and sometimes the NEW merge-commit sha, depending on timing.

**Why:** new instance of the gh-CLI silent-no-op family — sibling to `gh pr edit` (no-op on projects-classic) and `gh project item-add` (silent failure on bad URL). REST mutation endpoints that queue work return 202, not 200, and the read-side eventual-consistency window can be 1-10 seconds.

**How to apply:**

- After `gh api -X PUT .../update-branch`, **sleep briefly** (5-10s) OR poll `gh api repos/.../pulls/<N> --jq '.head.sha'` until it differs from the pre-call sha, before any downstream action (reviewer spawn, CI status check, merge readiness).
- If a teammate reports stale state ("head still at <old sha>, no new CI run") immediately after you triggered an update, **don't argue from your own verify** — refetch yourself with a fresh API call AND check `gh run list --branch <name> --limit 5` for a new run kicked off post-call. The presence of a new in-progress run is the load-bearing confirmation.
- Sibling to [[feedback_refresh_before_status_claim]] (every PR# in a teammate message earns one fresh API call first) — same discipline applies to your OWN PR# state, especially post-mutation.

**Precedent:** P3W12 #930 2026-05-30. After triggering update-branch, my own verify call returned the NEW head sha (8a95139), but Anya's read seconds later returned the OLD sha (a8481f9). The async window confirmed via `gh run list` showing a new run kicked off at 15:00:58Z post-call. Both observations were honest — they just landed in different points of the async window.

Companion to [[feedback_gh_pr_edit_silent_noop]] (which uses REST PATCH as the workaround for `gh pr edit`'s silent no-op). Same pattern: when gh CLI behavior is opaque, REST is more transparent — but REST mutations are async, so verify with a refetch.
