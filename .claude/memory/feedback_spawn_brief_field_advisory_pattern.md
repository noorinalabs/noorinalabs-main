---
name: feedback_spawn_brief_field_advisory_pattern
description: "Spawn-brief declarative fields (isolation, worktree, implementer-name) are advisory; the orchestrator must take explicit imperative action to make them real. Same shape as the agents.md § Parent-Orchestrator Implementer Declarations Are Advisory charter rule."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 0be57897-3749-48b2-8850-f155e5434000
---

When a spawn brief contains a declarative field like `isolation: "worktree"`, `implementer: <name>`, or `cwd: <path>`, treat the field as ADVISORY metadata. The orchestrator MUST take explicit imperative action (e.g., `git worktree add`, child-manager re-spawn, explicit `cd`) to make the declarative field real in the spawned agent's environment.

**Why:** P3W10 retro proposal #4 (PR #444) codified `agents.md § Parent-Orchestrator Implementer Declarations Are Advisory` for the parent-orchestrator-declares-implementer-for-child-repo case. The same shape — declarative-field-treated-as-advisory + orchestrator-side-imperative-action-required — recurs across multiple spawn-brief fields:

- **`isolation: "worktree"`**: 3 observed instances in 72h (P3W10 2026-05-13 PD/Wanjiku `5d76f27`; 2026-05-16 Aino #444; 2026-05-16 Wanjiku #445) where the spawn brief said `isolation: "worktree"` but the harness produced no physical-worktree separation. Recovered each time by orchestrator explicitly running `git worktree add -b <branch> <path> <ref>`. See `feedback_cwd_collision_cross_spawn.md` for the full pattern with two of the three instances documented.
- **`implementer: <name>` for child-repo work**: 22 substitutions / 34% of W10 PRs where parent-orchestrator's declared implementer was overridden by child-repo manager. Codified at PR #444 as `agents.md § Parent-Orchestrator Implementer Declarations Are Advisory`.
- **`cwd: <path>`**: not yet observed as a failure mode, but the same shape is latent — a brief that says `cwd: /some/path` does not guarantee the spawned agent's actual cwd will be that path.

The unifying principle: **spawn-brief fields are declarative descriptions of intent, not contracts the harness enforces.** The orchestrator's imperative actions (worktree-add, manager-re-spawn, cd-then-verify) are what make the intent real.

**How to apply:**

- Before relying on any declarative spawn-brief field, the orchestrator must take the imperative action AND verify the action's effect at canonical source (filesystem for cwd, `git worktree list` for worktree, roster.json for implementer-from-correct-team).
- Spawn briefs SHOULD state declarative intent for documentation + downstream-agent-context purposes, but MUST NOT assume the field's presence in the brief is sufficient to achieve the declared state.
- When a spawned agent reports the declarative-field state doesn't match the actual environment, the surface-and-pause discipline (per `feedback_cwd_collision_cross_spawn`) takes precedence — implementer pauses + reports, orchestrator takes imperative recovery action.
- For new spawn-brief fields, the orchestrator team should explicitly document whether the field is harness-enforced OR advisory-with-orchestrator-imperative-action-required, to avoid the implicit-promise trap.

**Charter promotion candidate (W11 retro):** Generalize the advisory-pattern across all spawn-brief fields by writing an `agents.md § Spawn-Brief Declarative Fields Are Advisory; Orchestrator-Imperative Actions Are Canonical` charter rule. The pattern is the same as the proposal-#4 carve-out we landed in #444 — just generalized to other declarative fields. Wanjiku-2 named this primitive at #445 checkpoint 1 (2026-05-16).

**Sibling rules:**
- [[cwd-collision-cross-spawn]] — concrete instance of the pattern at the worktree-isolation declarative-field layer
- [[refresh-before-status-claim]] — verify-at-canonical-source primitive that this pattern extends to spawn-brief-fields
- [[verify-diagnosis-before-delegating]] — verify-via-artifact-before-action primitive that this pattern extends to spawn-time

**Severity:**
- Minor when the spawned agent surfaces the discrepancy pre-Edit (Wanjiku #445 case — caught before any destructive action).
- Moderate when the discrepancy produces a wrong-cwd or wrong-branch commit that gets recovered without cascading downstream (Aino #444 case — orchestrator did `git checkout main && git reset --hard origin/main` safely after squash absorbed the carry-along).
- Severe when the discrepancy produces a wrong-cwd / wrong-branch commit that another teammate commits on top of before recovery (P3W10 2026-05-13 PD/Wanjiku `5d76f27` case — bundled into PR #428 as Option C let-it-ride).

**Origin:** Wanjiku Mwangi (Wanjiku-2 session-clone), P3W10 #445 checkpoint 1, 2026-05-16. Named the pattern in her checkpoint-1 message after the worktree-isolation breach recovery via orchestrator-imperative `git worktree add`.
