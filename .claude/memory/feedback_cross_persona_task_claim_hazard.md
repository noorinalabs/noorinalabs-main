---
name: feedback_cross_persona_task_claim_hazard
description: "TaskUpdate has no ownership-guard — a mistyped taskId silently completes another persona's pending work. Two recurrences in P3W10 (task"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 80ad8eee-00ce-46cf-924e-13907f259631
---

The team task system lets any agent call `TaskUpdate({taskId: N, status, owner})` on any task ID without an ownership-check. A mistyped taskId in a busy session silently marks another persona's pending work as completed, and the inbound replay carries the MISTYPER's identity (not the original task's owner) — masking that an unrelated agent touched the task.

**Why:** Two instances observed in P3W10 same-session by the same persona (landing-page-marcia) within ~2 hours of each other, despite explicit discipline-awareness after the first incident. Discipline alone is insufficient; the failure mode is structural.

**Incidents:**

1. **Task #56 incident (2026-05-13 ~18:30Z)**: Marcia intended `TaskUpdate({taskId: "67"})` to mark her own PR #94 reviewer-spawn task complete; mistyped `"56"`. Task #56 was Marisol Vega-Cruz's isnad-graph#831 tracking task (`Branch M.Vega-Cruz/0831-{slug}`, reviewers Idris + Anya). TaskUpdate succeeded silently. The task-system bounced the now-completed-but-not-by-Marisol task back as a fresh `task_assignment` with `assignedBy: landing-page-marcia` — Marcia caught the cross-persona mismatch via TaskGet, reverted to `pending` + cleared owner, surfaced to team-lead.

2. **Task #95 incident (2026-05-13 ~21:00Z, same session)**: Marcia intended `TaskUpdate({taskId: "96"})` to mark her own PR #96 ChangesRequested-routing task in_progress; mistyped `"95"`. Task #95 was "Review Lucas 7-PR auto-close-issues.yml cluster" — a Bereket-class cross-repo review across 7 PRs (main#431, user-service#106, design-system#78, landing-page#95, data-acquisition#54, deploy#286, isnad-ingest-platform#30). TaskUpdate succeeded. Marcia caught the cross-persona mismatch via her own read-back, reverted to `pending` + cleared owner, surfaced.

Both incidents: caught within the same minute, no real-world impact on the actual claimed tasks (the mistypist immediately reverted). But both produced an inbox-replay-spam-cycle where the mistyper's identity got attached to a task they had no business touching, masking the structural problem.

**How to apply** (until hook ships):

For every `TaskUpdate` call:
1. **Verify taskId before the call**: explicitly read-back the task ID from the TaskCreate output or TaskList just before TaskUpdate. Do NOT rely on memory across multiple intermediate tool calls — a busy session's TaskCreate/TaskUpdate sequence interleaves with other tool calls, and the "last taskId I touched" is unreliable.
2. **Identity-check post-update**: call `TaskGet(taskId)` immediately after TaskUpdate to verify the task's `subject` and `owner` match what you intended. If they don't, revert immediately.
3. **Suspect inbound task_assignment replays**: if a `task_assignment` message arrives in your inbox carrying `assignedBy: <your-own-identity>` AND a `subject` that doesn't match your active workstream, TaskGet the taskId FIRST before assuming it's a self-loop. The cross-persona-claim case looks like a self-loop in the assignedBy field but is actually a misrouted cross-persona claim.

**Promotion target — charter or hook (post-wave-retro)**:

Hook-tier preferred per [[enforcement-hierarchy]]: `TaskUpdate` should require the calling agent's identity to match the task's existing owner field (or be empty for unclaimed tasks). PreToolUse hook on TaskUpdate blocks the call if `caller != existing.owner AND existing.owner != ""`. Implementation sketch:

```python
# .claude/hooks/validate_task_ownership.py (sketch)
def on_pre_tool_use(tool_name, tool_input):
    if tool_name != "TaskUpdate":
        return  # not our concern
    task_id = tool_input.get("taskId")
    caller_identity = read_caller_persona_from_context()  # via routing.sender
    task = task_system.get(task_id)
    if task.owner and task.owner != caller_identity:
        return block(f"TaskUpdate identity mismatch: caller={caller_identity}, owner={task.owner}. Use TaskGet first to verify, or contact owner.")
```

Authorization to write this memory granted by team-lead 2026-05-13 mid-P3W10. Hook implementation deferred to /wave-retro per "introducing new enforcement mid-cascade is high-risk" (charter freshness check pattern).

**Related memories:**
- [[self-loop-task-replay-glitch]] — task-system replays the agent's own completed tasks back as fresh task_assignments. Related but distinct: self-loop is the agent's own task replaying; cross-persona-claim is the agent erroneously claiming OTHER personas' tasks. Same inbound-replay shape but different failure root.
- [[enforcement-hierarchy]] — hook > skill > charter; this discipline belongs as hook.
- [[refresh-before-status-claim]] — read-back-verify-before-status-claim discipline. The TaskUpdate identity-check is the task-system flavor of the same pattern.
- [[owner-pivot-supersedes-protocol]] — sibling P3W10 race-protocol memory. Coordination-friction at high tempo produces both this hazard and the routing-race hazard.
