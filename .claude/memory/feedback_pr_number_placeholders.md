---
name: feedback_pr_number_placeholders
description: "Don't draft messages with predicted PR numbers — GitHub allocates them at open time and parallel cluster work consumes them faster than you stage. Verify with gh pr view <N> before referencing."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 80ad8eee-00ce-46cf-924e-13907f259631
---

Rule: NEVER use a predicted/sequential PR number in a SendMessage, spawn-request, or status update for a PR you haven't opened yet. Use a placeholder like "(TBD-on-open)" or describe by branch name only. Read the real number back via `gh pr view <N>` after `gh pr create` returns.

**Why:** P3W10 2026-05-13 — I wrote "PR #431" in a reviewer-spawn-request and status message for my forthcoming #403 main PR, predicted by adding +1 to the most-recent PR# in the repo. While I was holding the branch (waiting for precursor PR #430 to merge), Lucas opened his main#402 auto-close-issues cluster in parallel and consumed #431 (his PR `L.Ferreira/0402-auto-close-issues-propagation`). My next available PR# is now #432+, but two of my messages still cited #431 — confusing for Wanjiku and team-lead, required follow-up corrections to both.

**How to apply:** When drafting a message that references a PR you haven't opened yet:

1. Use "(TBD-on-open)" or "[my upcoming main PR]" as the identifier. Describe by **branch name** (`A.Idrissi/0403-branch-protection-7-repos`) — branches are deterministic, PR numbers are not.
2. After `gh pr create` succeeds and prints the URL, immediately read back the actual number: `gh pr view <N> --json number,headRefName,baseRefName --jq '.'`.
3. Only THEN send the spawn-request or status update with the verified PR#.
4. If you have to forward-reference a PR before opening it (e.g. "after #430 merges, I'll open the manifest PR"), say "the manifest PR" not "#431".

**Companion rules:**
- [[feedback_refresh_before_status_claim]] — same principle for PRs you DO know exist: re-verify the number resolves to what you think it does before claiming state.
- Verify against origin, not a local prediction (origin-over-local for still-open claims).
- Parallel cluster work in same repo (multiple agents opening PRs against same base branch) accelerates PR# consumption. Common during Lucas-style cross-repo cluster + Aisha-style precursor + main pair patterns. Don't assume sequential allocation.

**Trigger:** Any time you're about to write a "#N" reference in an outbound message AND PR #N has not been confirmed via `gh pr view` in the current session, stop and either (a) verify or (b) use a placeholder.
