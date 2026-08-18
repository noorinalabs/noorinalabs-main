---
name: feedback_owner_merge_gate_review_first
description: "An owner \"don't merge without my go\" gate is on the MERGE, not on the review — drive every gated PR fully through charter review to Approved, then engage the owner once the whole batch is merge-ready. Pausing before reviews just adds a round-trip."
metadata:
  type: feedback
last_verified: 2026-08-17
promotion_target: charter
promotion_threshold:
  retro_citations: 3
status: active
---

When the owner sets a *"don't merge to main without my go"* gate on a wave's PRs, the gate is on the **merge step only**. Reviews are not gated.

Proceed through the full charter review for **every** gated PR — line up both reviewers, drive them to green + `Approved` — and engage the owner only once **all** of them are reviewed and merge-ready.

**Why (set by the owner 2026-07-26, during wave-28):** the owner wants review work done autonomously, so that the merge decision arrives with everything already staged and green. Stopping at *"green, waiting for the merge call"* before reviews have run means the owner has to make two round-trips instead of one, and the second one is on work that could have been finished without them.

## How to apply

For owner-gated PRs, do **not** stop at "CI green, awaiting merge decision." Instead:

1. Assign or spawn reviewers per the charter.
2. Drive to **2 distinct non-author `Approved` reviews**, at least one of which is an Opus merge-gate review.
3. Present the finished batch to the owner for a single merge decision.

Only the `gh pr merge` step waits on the owner.

Corollary: if a review turns up changes that must be made, make them and re-review — that is still review work, still autonomous, still ahead of the gate. The gate is not a reason to leave a PR in an unfinished state.

Related: [[feedback_pr_review_verdict_format]] (what actually counts as an Approved review — `Reply`/`Request` forms contribute zero), [[feedback_statuscheckrollup_ci_clean]] (what "green" requires — an empty rollup is hard not-ready), [[feedback_commit_identity_roster_from_cwd]].
