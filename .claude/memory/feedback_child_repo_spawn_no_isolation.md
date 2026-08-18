---
name: feedback_child_repo_spawn_no_isolation
description: "`isolation: worktree` fences an agent to a PARENT-repo worktree and the harness then refuses every git op against a nested child repo — so a child-repo implementer spawned that way can read but never branch/commit/push/PR. Spawn child-repo implementers NON-isolated and have each build its own worktree inside the child clone; keep isolation for parent-repo spawns only."
metadata:
  type: feedback
last_verified: 2026-08-17
promotion_target: charter
promotion_threshold:
  retro_citations: 3
status: active
---

At wave-28 kickoff (Phase 10, 2026-07-26) **all 7 child-repo implementer spawns failed identically.** `Agent(isolation: "worktree")` pins the agent to a worktree of the **parent** repo (`noorinalabs-main`), and the harness then refuses any git operation the agent attempts against a nested child repo. All three routes are rejected:

- `git -C <child> …`
- `cd <child> && git …`
- `EnterWorktree <child>`

with *"a worktree-isolated agent's git operations must target its own worktree"* / *"changes directory to the shared checkout … refusing"* — and **`dangerouslyDisableSandbox: true` does not lift it.** The agent can read the child repo and can never write to it.

The 3 **parent-repo** agents in the same batch (work under `.claude/hooks/`, `.github/`) succeeded, because for them the target repo *is* their own worktree.

## The charter is wrong on this point (still, as of 2026-08-17)

`charter/agents/orchestration-model.md` § Spawn Isolation Default says:

> All implementer-class spawns from the orchestrator MUST be invoked with `isolation: "worktree"`, **even when the parent-side worktree is cosmetic (e.g., the agent's actual code work lives in a child-repo clone).**

The parenthetical is exactly the case that does not work. The parent worktree is not cosmetic for child-repo work — it is **load-bearing in the wrong direction**, making the child repo unreachable. An orchestrator following the charter literally will lose every child-repo spawn in the batch.

The charter's stated rationale (workspace presentation — non-isolated agents render as generic "background tasks") is a real UI cost, but it is traded against total functional failure, so it cannot win for child-repo spawns. Tracked as a charter-correction issue (noorinalabs-main#1471); until that lands, **this note overrides the charter for child-repo spawns**, on the narrow ground that a rule which cannot be complied with cannot be binding — the charter's instruction here does not merely produce a worse outcome, it produces no outcome at all. That argument stands on its own; it is not an application of [[feedback_enforcement_hierarchy]], which ranks hook > skill > charter when choosing where to *author* new enforcement and says nothing about memory-vs-charter precedence.

## How to apply

**Child-repo implementer spawn:**

1. Spawn **without** `isolation` — the agent inherits the orchestrator's reachable context.
2. Have the agent create its **own** isolated worktree *inside the child clone*:
   ```
   git -C <abs-child> worktree add /home/…/w<N>-<slug> -b <branch> origin/main
   ```
3. `cd` into that worktree — **not** the shared child checkout — and do every edit / commit / push / PR there.

**Parent-repo (`noorinalabs-main`) implementer spawn:** keep `isolation: "worktree"`. It works and the presentation benefit is real.

Verified: the orchestrator, non-isolated, can create and remove a child worktree off `origin/main`.

## Reconciling the apparent contradiction with [[feedback_subagent_worktree_wrong_repo]]

That note warns: *"Do not 'fix' this by spawning without isolation — two agents sharing one cwd on different branches is the collision hazard in [[feedback_cwd_collision_cross_spawn]]."* Both notes are correct; they are answering different questions.

The collision hazard is real, but its cause is **two agents sharing one checkout**, not the absence of `isolation`. Step 2 above removes the hazard by giving each agent its own worktree *in the child repo* — which is the isolation that was actually wanted. What `isolation: "worktree"` provides for a child-repo agent is isolation in the **wrong repo**, which buys nothing and costs write access.

So: non-isolated spawn **plus a per-agent child worktree** — never non-isolated spawn sharing the child's main checkout.

Related: [[feedback_spawn_worktree_follows_orchestrator_cwd]] (the worktree is based off the orchestrator's cwd at spawn time, so a stray `cd` misroutes it — an independent trap that also bites here), [[feedback_child_repo_implementer_rule]] (child-repo PRs take implementers from that child's roster), [[feedback_commit_identity_roster_from_cwd]] (once in the child worktree, `cd` there before committing so the identity gate loads the right roster).
