---
name: feedback_graphql_quota_ceiling_on_agent_fanout
description: High agent fan-out exhausts the org's 5000/hr GraphQL quota; agents then die mid-task and a failed gh call's output silently reads as a zero result.
metadata:
  type: feedback
last_verified: 2026-08-11
---

During wave-30 execution (2026-08-11) ~14 concurrent agents (8 implementers + 6
reviewers), each running many `gh pr view` / `gh pr checks` / `gh issue view`
calls, drove **GraphQL from 5000 to 0 in roughly one hour**. REST core was barely
touched (4964/5000 remaining at the same moment). Reset is hourly.

**Why this matters — three distinct failure modes, all quiet:**

1. **Agents die mid-task without reporting.** Six review agents were spawned; four
   left **no verdict on the PR and sent no message**. They were simply gone from
   `ListAgents`. One of the two that did post (`ChangesRequested` on PR #1384)
   never reported back either — the verdict was discovered only by querying the
   PR directly. **Never infer review state from agent reports; query the artifact.**
2. **A failed `gh` call still writes to stdout.** `gh pr view … | rg -c "pattern"`
   over a rate-limit error prints `GraphQL: API rate limit already exceeded…` and
   `rg` then reports **0 matches** — indistinguishable from a genuine clean result.
   This produced a false "verified" on a PR-body check until the error line was
   read. Always assert the call succeeded (`jq -e '.number'`, exit code) BEFORE
   interpreting a count. Cf. [[feedback_state_the_denominator_with_the_number]].
3. **The quota is org-wide and shared**, so one session's fan-out blocks every
   other agent and session on the account for the remainder of the hour.

**How to apply:**

- **Check before fanning out:** `gh api rate_limit --jq '.resources.graphql'`.
  Budget roughly: each review agent costs on the order of hundreds of GraphQL
  points. Beyond ~6–8 concurrent gh-heavy agents, expect exhaustion within the hour.
- **Throttle review spawns into batches** rather than one-per-PR simultaneously.
  Implementers are cheaper (mostly git + file I/O); reviewers are the expensive
  class because they poll PR state repeatedly.
- **Prefer REST in agent briefs.** `gh pr view/checks/issue view` are GraphQL;
  `gh api repos/.../pulls/N`, `.../issues/N/comments`, `.../commits/<sha>/check-runs`
  are REST and unaffected. `.claude/lib/gh_rest.py` exists for this; the
  `gh_quota_gate` hook (#1224) blocks GraphQL-shaped calls below a threshold and
  prints the REST rewrite. `git` push/commit are unaffected either way.
- **Two unrelated `gh` traps observed the same session**, both of which *silently
  fail to apply the edit*: `gh pr edit` errors on a Projects-classic GraphQL
  deprecation, and `gh api -f body=@file` writes the literal `@path` string.
  Use `gh api … -X PATCH` with a JSON payload, or `-F body=@file`. **Always
  read the artifact back after an edit** — two separate agents caught these only
  by re-reading.

Related: [[feedback_gh_cli_gotchas]], [[feedback_verify_before_claim]],
[[feedback_orchestration_vs_product_balance]].
