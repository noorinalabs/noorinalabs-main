---
name: feedback_parallel_panels_shared_file
description: "Pre-assigned distinct LOGICAL file ownership does NOT prevent git merge conflicts when parallel PRs all append to the same SHARED files (router/client/nav/types). Such PRs must merge SERIALLY with a rebase between each; never batch-merge them. Also: never close an issue in the same batch as its PR merge before confirming the merge actually succeeded."
metadata:
  node_type: memory
  type: feedback
  originSessionId: 090bf6d5-0d19-47c9-9b85-67bfff1c5396
---

P4W3 admin-panel fan-out (ig#805/#806/#970 → PRs #985/#986/#984, 2026-06-12): three panels were launched in parallel off one tip with "collision-safe" pre-assigned file ownership — each owned a distinct function GROUP in `admin-client.ts`, a distinct page file, a distinct route. That prevents LOGICAL collisions but NOT git conflicts: all three **append to the same shared files** (`admin-client.ts`, `App.tsx` route list, `AdminLayout.tsx` nav, `types/admin.ts`). When I batch-merged all three, #985 merged first and #986 + #984 immediately went `CONFLICTING` (adjacent appends to the same regions). They had to be rebased + merged one at a time.

Second mistake same batch: I ran `gh issue close 970` in the SAME shell block right after the `#984` merge command — but the #984 merge FAILED (conflict) while the close ran anyway, leaving ig#970 closed with its PR unmerged. Had to reopen.

**Why:** distinct logical ownership ≠ non-overlapping diff hunks. A shared registry/aggregator file (a route table, a client module everyone appends fns to, a nav list, a barrel `types` file) is a single conflict surface no matter how cleanly you partition the logical content. And REST `merge` is not transactional with a following `issue close` — a failed merge doesn't stop the next command in a `&&`-less block.

**How to apply:**
- Parallel PRs that all touch a shared registry/aggregator file (router, api-client, nav, barrel export, `__init__.py` router-include, a central enum/types file): **merge them SERIALLY**, rebasing each remaining one onto the new tip after every merge. Don't batch-merge. Sequence: merge #1 → tell #2's author to rebase onto the new tip (keep BOTH sides) → merge #2 → rebase #3 → merge #3. A clean conflict-only rebase preserves existing approvals (re-verify the diff is conflict-resolution-only, merge without full re-review).
- BETTER design to avoid it entirely: have each parallel unit register via its OWN file (e.g. one route module per panel auto-discovered/included, separate client files) so there is no shared append surface. Worth specifying in the spawn brief when fanning out N parallel additions to one app shell.
- NEVER pair an `issue close` with a PR `merge` in the same un-guarded batch. Confirm `merged:true` (or re-read PR state) BEFORE closing the issue — a wave-branch merge doesn't auto-close anyway, so the close is always a separate deliberate step gated on verified merge. Companion to [[feedback_gh_cli_gotchas]].
