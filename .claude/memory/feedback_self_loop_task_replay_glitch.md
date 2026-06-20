---
name: feedback_self_loop_task_replay_glitch
description: Implementer agents may receive their own completed TaskCreate entries replayed back as fresh task_assignment messages; verify against TaskGet + ignore self-loops
type: feedback
originSessionId: 33831276-0bd2-46e7-8ddd-345abb927046
promotion_target: none
promotion_threshold:
  retro_citations: 3
status: active
---
The team task system (TaskCreate / TaskUpdate / inbox) sometimes replays an agent's own completed tasks back to them as inbound `task_assignment` JSON messages with `assignedBy: <self-id>`. Confirmed pattern at P3W3 kickoff 2026-05-03 from Idris-853 implementer session:

- taskId 2 ("Read target files...") — replayed ~10min after PR open; described work already shipped
- taskId 5 ("Choose Trivy CVE fix strategy") — replayed; work already shipped
- taskId 6 ("Implement fix on I.Yusuf/0853-trivy-cve-fix branch") — replayed; work already shipped

Replays arrive in original task creation order, ~30s apart, after the agent goes idle post-shipping. `TaskGet <id>` returns "Task not found" on the replayed IDs (already collected/GC'd).

**Why:** unclear; possibly the inbox-to-mailbox bridge is replaying retained-but-collected task records during state transitions or GC. Not a behavior the team task primitives should expose, but the pattern is reproducible enough to recognize.

**Detection (agent-side decision tree):**
1. Inbound `task_assignment` arrives with `assignedBy: <my own agent id>`?
   - If matches a task I already shipped (verify via TaskGet returning not-found OR matches a completed task in my own creation log): **silently ignore, do NOT re-execute.** Log internally, no orchestrator ping.
   - If unfamiliar / describes work I haven't done: **flag to orchestrator before acting** (load-bearing case — could be a real reroute).
2. Inbound `task_assignment` from a different `assignedBy`: standard check (out-of-scope-class-correction — see `feedback_role_class_specific_boundaries.md`).

**How to apply:** every implementer's spawn brief should mention this pattern so they don't waste a turn pinging the orchestrator on each self-loop replay. Add to the standard implementer prelude:

> If you receive a `task_assignment` JSON with `assignedBy` matching your own agent id, AND the described work matches something you've already shipped (verify via TaskGet → not-found), silently ignore. Self-loop replays are a known harness glitch. Only flag to orchestrator if the description is unfamiliar OR describes unfinished work.

**Why this matters:** without this rule, an implementer in idle-monitor mode after PR open ends up either (a) re-executing already-shipped work (worst case: opens duplicate PR), or (b) sending a clarification ping per replay (4-6 unnecessary inbox messages per shipped PR). Neither is recoverable cost-free.

**Triggered by:** Idris-853 caught the pattern on the second occurrence (taskId 5), correctly identified the third (taskId 6) without orchestrator help, and went silent on the rest. Strong implementer-class state-claim discipline. The 1-of-6 misroute (taskId 2) that he flagged to me earlier WAS a different signal — described deploy#252 work routed to isnad-graph implementer — so he had calibrated correctly that not all "weird inbound tasks" are the same shape.
