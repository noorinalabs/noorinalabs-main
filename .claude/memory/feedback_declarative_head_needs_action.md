---
name: feedback_declarative_head_needs_action
description: "Charter-tier-candidate pattern — landed-at-HEAD artifacts (worktree-isolation flag, post-merge hook dispatcher) do NOT auto-propagate into orchestrator sessions loaded before the merge; explicit orchestrator action required"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 0be57897-3749-48b2-8850-f155e5434000
---

Declarative artifacts that "exist at HEAD" do NOT automatically take effect in a pre-existing orchestrator session — the session's loaded state (worktree paths, dispatcher module list, hook registry) is frozen at session-load time. Becoming-real in the session requires an explicit imperative action by the orchestrator (or a session restart).

**Why:** Four observed instances by 2026-05-16 — each one cost ~10-30 min recovery time before recognition:

1. **P3W10 2026-05-13 PD/Wanjiku `5d76f27` cwd-collision** — `isolation: "worktree"` flag in Agent spawn brief is advisory; without orchestrator `git worktree add`, parent process cwd collides with subagent's branch.
2. **P3W10 2026-05-16 Aino #444 worktree cwd-collision** — same shape, recovered via `git checkout main && git reset --hard origin/main`.
3. **P3W10 2026-05-16 Wanjiku-2 #445 worktree cwd-collision** — recognized pre-Edit, mitigated via explicit pre-created worktree + SUPERSEDES-AS-OF delta. Worked perfectly.
4. **P3W11 2026-05-16 Hook 21 dispatcher silent-skip** — orchestrator session loaded BEFORE Hook 21 PR #446 merged at 22:39:39Z; dispatcher module list frozen → Hook 21 silent-no-op for the FIRST 2 of 41 label-ops. Recovered by full session restart (Option 2).

**How to apply:**

When an artifact has landed at HEAD that should change session behavior:

| Artifact type | Becoming-real action required |
|---|---|
| Spawn-brief `isolation: "worktree"` | Orchestrator `git worktree add` BEFORE first Edit/Write |
| Spawn-brief `cwd: /path/to/worktree` | Orchestrator pre-creates the path AND verifies the agent's first action cd's there |
| Spawn-brief `implementer: NameX` (child-repo) | Orchestrator spawns from the child-repo's roster, not parent's |
| Post-merge PostToolUse hook in dispatcher | Session restart (`/handoff` + restart) OR accept that hook is inert this session |
| Post-merge skill / charter rule | Read-back at next invocation; assume rule applies from next session (charters re-read each session) |
| Post-merge settings.json hook wiring | Session restart (hook config loaded at session start) |

**General principle (Wanjiku-named "spawn-brief field advisory pattern", broadened here):** Every declarative artifact at HEAD has an *advisory* signal value and a *real-effect* mechanism. The orchestrator must consciously bridge the gap — either via an imperative pre-action or via a session restart.

**Charter-promotion candidate (W11 retro):** This is the 4th instance in 3 days (2026-05-13 → 2026-05-16). The promotion shape would be a new `agents.md` section "Pre-Existing Session Limitations on HEAD-Landed Artifacts" with a check-before-acting table similar to the one above. Surface in W11 retro after end-of-wave evidence pool is complete.

Sibling memories: [[feedback_spawn_brief_field_advisory_pattern]] (parent generalization), [[feedback_cwd_collision_cross_spawn]] (instances 1-3 detail).
