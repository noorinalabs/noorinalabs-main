---
name: feedback_agent_liveness_signals_are_unreliable
description: ListAgents can show empty while an agent is still working, and agents finish without reporting. Never infer work state from agent presence or agent reports — read the artifact.
metadata:
  type: feedback
last_verified: 2026-08-11
---

Wave-30 execution (2026-08-11) ran ~20 subagents across implementation and review.
Two independent liveness signals both proved unsafe, and trusting either cost real
waste.

**1. `ListAgents` showing no subagents does NOT mean none are running.**
Mid-wave, `ListAgents` returned only peer sessions — zero subagents — while a
merge-gate reviewer was still working. On that basis a replacement reviewer was
spawned; the original then posted its verdict normally, and the replacement posted
a second, near-identical `ChangesRequested` on the same PR. Two full Opus-tier
reviews of the same diff, one of them pure waste. (The gate takes the latest
verdict per reviewer, so the duplicate was harmless to the count — but the tokens
were not.)

**2. Agents complete without reporting.** Across the wave, **seven** agents ended
without sending a message. Several had posted their verdict to the PR first; one
posted a `ChangesRequested` that was discovered only by querying the PR directly,
hours of orchestrator reasoning later. One returned a stub ("I'll wait for the
background task…") having actually opened a PR. A silent agent and a dead agent
are indistinguishable from the orchestrator's side.

**3. A posted verdict is not necessarily a *counted* verdict.** Separately from
liveness: a correctly-formed `Approved` was invisible to `resolve_review_verdicts`
because fence markers in the reviewer's prose caused `strip_code_regions` to
swallow the trailer (#1413). "The reviewer says they approved" and "the reviewer
did approve" and "the gate counts the approval" are three different facts.

**How to apply — one rule: the artifact is the state.**

- Never report review status from an agent's message. Run
  `validate_pr_review.resolve_review_verdicts(pr_data, repo)` and report
  `distinct_reviewers`. It is the same code the merge gate runs, so it is the only
  answer that predicts merge behaviour. Counting `Approved` comments by eye gets it
  wrong three ways: staleness, latest-verdict-per-reviewer, and unparseable trailers.
- Before respawning an agent you believe is dead, check whether its *work* landed
  (branch pushed? PR opened? comment posted?), not whether it appears in
  `ListAgents`. Absence from the listing is not evidence of completion or death.
- When an agent's own report and the artifact disagree, the artifact wins — and the
  disagreement itself is worth investigating, because it usually means a gate is
  reading something different from what the human-readable text says.

Related: [[feedback_graphql_quota_ceiling_on_agent_fanout]] (agents dying on quota
exhaustion, same "silent" failure surface), [[feedback_verify_before_claim]],
[[feedback_no_head_sha_in_review_briefs]] (the reviewer, not the orchestrator,
resolves head — same principle: the party touching the artifact owns the fact).
