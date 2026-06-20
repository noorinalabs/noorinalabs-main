---
name: feedback_throttle_takeover
description: When a spawned implementer throttle-stalls mid-task, finish their work directly as orchestrator — faster recovery than respawning.
type: feedback
originSessionId: 7deaa69a-9ef8-44e6-9ca9-39e5a23f368c
promotion_target: charter
promotion_threshold:
  retro_citations: 3
status: enforced-elsewhere
superseded_by: charter:agents.md § Throttle-Stall Recovery — Trigger Thresholds
---
When a spawned implementer agent goes idle mid-implementation due to API throttling (visible signs: idle_notification without a completion SendMessage, partial TaskList progress like "1-2 of 5 done with #3 in_progress", uncommitted-but-meaningful diff in their worktree), **the orchestrator should take over their work directly rather than respawning a fresh agent**.

**Why:** Respawning costs another full context-load + ontology-librarian invocation + persona file read; if throttling is active, the respawn often hits the same wall and you lose another 5+ minutes. Orchestrator-takeover is ~5min recovery (verify partial work, run their tests, finish, commit, push, open PR) vs respawn's ~10-15min (reload context, re-orient to task, then maybe also throttle). P3W4 2026-05-05: Aino throttled on #158 STALE-OPT-OUT after tasks 1-2 done + tests in_progress; orchestrator finished tasks 3-5 in 5min; commit author identity preserved (Aino's name/email per `-c` flags) so attribution is correct.

**How to apply:**
1. Verify the partial work is sound (run tests, read diff)
2. If sound, finish the remaining tasks directly with the spawned-agent's commit identity
3. Document the takeover in the PR body and commit message ("commit shows X identity; orchestrator finished after X's spawn went idle mid-tests")
4. Use TaskUpdate to mark their stale tasks completed if they're still showing as in_progress
5. Skip respawn unless the remaining work is genuinely outside orchestrator-class scope (e.g., novel domain expertise the orchestrator lacks)
6. Note: this is for *implementer* takeover — for reviewer/manager-class roles, prefer SendMessage to the existing idle agent (idle ≠ dead) before assuming takeover is needed
