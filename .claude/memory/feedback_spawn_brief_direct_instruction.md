---
name: feedback_spawn_brief_direct_instruction
description: "Spawned-agent direct instruction to run `git worktree add` IS the imperative action that satisfies [[feedback_spawn_brief_field_advisory_pattern]] — the rule is about declarative-at-HEAD fields, not explicit step-by-step instructions to the agent."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 77e35de5-3b28-48a1-92f6-f413bc8debac
---

When a spawn brief tells a spawned agent to run `git worktree add` (or any imperative command) themselves as a numbered step, the agent CAN and SHOULD run it — they don't need to bounce the request back to the orchestrator citing [[feedback_spawn_brief_field_advisory_pattern]].

**Why:** [[feedback_spawn_brief_field_advisory_pattern]] addresses declarative fields like `isolation: worktree` at the top of a spawn brief, which require the orchestrator (who has Agent / TeamCreate authority) to translate into an action BEFORE spawning. An explicit step-by-step instruction inside the brief body ("run `git worktree add ...`") is fundamentally different: the spawned agent IS the imperative action by following the step. `git worktree add` writes to the parent repo's `.git/worktrees/` shared filesystem and runs fine from a subagent shell.

**How to apply:**
- Declarative top-of-brief flag (e.g., `Isolation: worktree`) → orchestrator's responsibility to satisfy before spawn. Bounce back if missing.
- Numbered imperative step in brief body (e.g., "2. Run `git worktree add ...`") → spawned agent's responsibility to execute. Just do it.
- Test: "Did the brief tell me explicitly to run THIS command?" If yes → run it. If the brief just stated a property and expected the environment to be that way → bounce.

Distinguished from sibling rule [[feedback_declarative_head_needs_action]] which covers landed-at-HEAD artifacts (worktree flags, post-merge dispatchers) needing orchestrator action OR session restart.

Source: P3W11 task #5 us#103 implementer-spawn 2026-05-19 — Anya pre-flighted a routing-confirm bouncing on worktree authority; team-lead clarified the carve-out. Implementation completed without escalation in the second pass.
