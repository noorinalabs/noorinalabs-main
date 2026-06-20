---
name: feedback_cwd_collision_cross_spawn
description: "When orchestrator + spawned implementer target the same physical cwd via different branches, the second `git checkout` silently changes the first's working state. Cross-spawn cwd collision causes commits to land on wrong branch."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 80ad8eee-00ce-46cf-924e-13907f259631
---

Before any Edit/Write/git-commit in a session that shares a cwd with active spawn(s), run `git branch --show-current` and verify the branch matches your spawn-brief expectation. The orchestrator session can land on a teammate's feature branch unbeknownst when their spawn ran `git checkout` in the same physical directory.

**Why:** P3W10 2026-05-13 — PD Nadia Khoury edited `cross-repo-status.json` for a 15-line manager-boundary reviewer reallocation, committed with Nadia Khoury identity. Commit `5d76f27` landed on `W.Mwangi/0423-wave-wrapup-cross-window-fix` (Wanjiku TPM's feature branch) instead of `deployments/phase-3/wave-10`. Reflog showed `HEAD@{1}: checkout: moving from deployments/phase-3/wave-10 to W.Mwangi/0423-wave-wrapup-cross-window-fix` — Wanjiku's spawn had switched the cwd's branch during the session without realizing the orchestrator was actively working in the same physical dir. Both agents' spawn briefs said `isolation: "worktree"` but only one physical worktree existed (`git worktree list` returned ONE entry). Wanjiku then committed `b0bfd5c` on top + pushed both commits to origin; PR #428 carried the bundled pair. Recovery options (C1 let-it-ride bundle, C2 surgical force-push extraction) both had real costs; team-lead chose C1.

**How to apply:**
- Before EVERY Edit/Write that targets a tracked file, run `git branch --show-current` and assert it matches the spawn-brief's expected branch (`{FirstInitial}.{LastName}/{IIII}-{slug}` for implementers, or `deployments/phase-3/wave-N` for the orchestrator's coordination work).
- Before EVERY `git commit`, re-verify branch — the checkout drift may have happened between Edit and commit.
- Treat "isolation: worktree" in a spawn brief as a directive that demands a SEPARATE physical worktree path, not just a branch. Verify via `git worktree list` includes the expected path for the spawn.
- When a coordination defect of this class is observed, the recovery cost grows with downstream commits + remote pushes — escalate early (within the same turn as the misplaced commit), don't wait for a teammate to commit on top.

**Enforcement future:** PreToolUse hook on Edit/Write/NotebookEdit that reads the spawn-brief's expected branch (from `.claude/.spawn-context.json` or similar) and blocks if `git branch --show-current` doesn't match. Companion to Hook 14 (ontology context) and Hook 15 (librarian consulted). Routed through /annunaki-attack post-W10-wave-wrapup.

**Second instance — 2026-05-16 P3W10 retro adoption (PR #444):** Team-lead's post-merge `git pull --ff-only` on origin/main failed because the orchestrator's cwd was on Aino Virtanen's feature branch `A.Virtanen/0443-charter-adoption-w10-retro-proposals` (not main). Aino's spawn brief specified `isolation: "worktree"`, so the orchestrator expected its own cwd to remain pinned to main during Aino's work. Recovery was safe (`git checkout main && git reset --hard origin/main`) because Aino's local commit `27874e1` was already absorbed into the squash `ccc7edf` — but the near-miss confirms the pattern recurs even when both parties followed protocol. Strengthens the case for the future PreToolUse hook above: spawn-time isolation flags do NOT reliably produce physical-worktree separation; the contract is honored at branch-name level but not at physical-cwd level. Until the hook lands, BOTH orchestrator AND spawned implementer should run `git branch --show-current` immediately before EVERY `git pull`/`git checkout`/`git commit` operation.

**Sibling rules**: [[verify-diagnosis-before-delegating]] (verify-via-artifact-before-action), [[refresh-before-status-claim]] (re-verify state before claims) — both share the "trust-but-verify-the-current-state" stance.
