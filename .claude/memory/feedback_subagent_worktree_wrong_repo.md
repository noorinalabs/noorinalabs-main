---
name: feedback_subagent_worktree_wrong_repo
description: Agent-tool `isolation: worktree` creates a worktree of the PARENT org repo, not the child repo the task targets — child-repo implementers cannot Edit/Write their own sources.
metadata:
  type: feedback
---

**Spawning a child-repo implementer from a `noorinalabs-main` session with `isolation: worktree` gives the agent a worktree of the PARENT repo.** The Agent tool resolves `worktree` against the orchestrator's cwd (`noorinalabs-main`), not against the repo the brief names. Observed 2026-07-09 spawning Alejandra Reyes-Fuentes onto `noorinalabs-data-acquisition` for da#353/PR#357.

**Why:** Consequences for the subagent:
- Edit/Write are **pinned to that parent worktree**, so they cannot reach `noorinalabs-data-acquisition/src/**` at all — the child clone is `.gitignore`d by the parent and is a separate git repo.
- `EnterWorktree` **refuses** the cross-repo switch (the target must be a worktree of the same repository, or — on first entry from the launch directory — of a repo nested inside it).

So the agent is isolated into the wrong repository and its primary editing tools are inert on the files it was asked to change. Silent: nothing errors until the first Edit.

**How to apply:** When spawning an implementer for a child repo:
- Expect this, and say so in the brief: *"confirm your cwd is an isolated checkout of the CHILD repo, not the parent."*
- The workable path the agent took: create a proper child-repo worktree with `git -C <child> worktree add`, then apply edits via a controlled patch script with **exact single-match assertions** (mirroring the Edit tool's uniqueness guarantee) rather than blind `sed`. Commits and pushes still route through the normal hooks — commit identity via `-c` flags, pre-commit/pre-push all fire, structural-ontology index regenerated with `python3` (not `uv run` — see [[feedback_structural_gate_commit_friction]] in the da repo).
- Do **not** let the agent fall back to editing the parent's copy of a path that looks similar. That is [[feedback_cwd_collision_cross_spawn]] with extra steps.
- Verify after the fact: `git -C <child> log --no-merges --format='%an <%ae>' origin/main..<branch>` shows the persona, and `git diff --stat origin/main...<branch>` touches only child-repo paths.

Do not "fix" this by spawning without isolation **and leaving the agent in the child's shared checkout** — two agents sharing one cwd on different branches is the collision hazard in [[feedback_cwd_collision_cross_spawn]] (second checkout moves the first; commits land on the wrong branch).

**Refined 2026-08-17 — non-isolated IS the correct spawn mode for child-repo work, provided each agent gets its own child worktree.** Wave-28 established that `isolation: "worktree"` does not merely put the worktree in the wrong repo (this note's original finding) — it makes the child repo **unwritable**: the harness refuses `git -C <child>`, `cd <child> && git`, and `EnterWorktree <child>` alike, even with `dangerouslyDisableSandbox`. All 7 child-repo spawns that wave failed on it. So the choice is not "isolation vs. collision risk"; it is "isolation and no write access at all" vs. "non-isolated plus a per-agent worktree inside the child clone", which is the isolation that was actually wanted. The bullet above — create a proper child-repo worktree with `git -C <child> worktree add` — is exactly that path, and it removes the collision hazard on its own. See [[feedback_child_repo_spawn_no_isolation]] for the full mechanics and the charter defect it exposes.

Related: [[feedback_child_repo_implementer_rule]] (child-repo PRs get implementers from that child's roster), [[feedback_hook_cwd_anchor_subagent_worktree]] (hooks reading stdin cwd resolve to the orchestrator dir, not the subagent worktree — same root confusion, different blast radius).
