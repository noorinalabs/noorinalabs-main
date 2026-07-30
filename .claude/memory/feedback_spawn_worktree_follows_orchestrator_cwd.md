---
name: feedback_spawn_worktree_follows_orchestrator_cwd
description: "An isolation:worktree subagent is based off whatever repo the ORCHESTRATOR's persistent Bash cwd is in at spawn time — not necessarily the parent org repo; a stray `cd` into a child repo silently misroutes the next spawn"
metadata:
  node_type: memory
  type: feedback
last_verified: 2026-07-30
---

When the orchestrator spawns an agent with `isolation: "worktree"`, the worktree is created off **whatever repo the orchestrator's Bash-tool working directory is currently in** — *not* unconditionally the parent org repo.

**The Bash tool's cwd persists between calls.** A single earlier `cd <child-repo>` — even for an unrelated read-only check — silently redirects every subsequent isolated spawn into that child repo.

**Why:** The subagent is then hard-pinned to that worktree. The harness refuses git operations targeting anything outside it — `cd … && git`, `git -C …`, all of it. A parent-repo story spawned this way is **unreachable**: the agent cannot read `noorinalabs-main/.claude/`, cannot branch, cannot open its PR. It has no workaround available to it and can only stop and report.

**Observed 2026-07-30 (wave-29 batch-1 fan-out).** I ran `cd …/noorinalabs-isnad-ingest-platform` to verify ip#152's premise against `topics.py` and `CLAUDE.md`, then — without returning — spawned Nurul Hakim on **main#1160**, a `noorinalabs-main` memory-store story, with `isolation: worktree`. His worktree landed at `noorinalabs-isnad-ingest-platform/.claude/worktrees/agent-…`, and `noorinalabs-main` was unreachable from it. He correctly refused to fight the sandbox and asked for a corrected assignment rather than burning cycles. Cost: one wasted spawn (~53K tokens). Yusuke Inoue, spawned **non-isolated** from the same wrong cwd moments earlier, was unaffected — he *wanted* the child repo, and with no worktree he simply inherited the cwd.

**This refines [[feedback_subagent_worktree_wrong_repo]]**, which states that `isolation: worktree` worktrees *the parent org repo*. That is only true when the orchestrator happens to be standing in the parent. The general rule is **"the repo of the orchestrator's cwd"**, and the child-repo case is reachable — which is the more dangerous direction, because it silently produces a worktree in the wrong repo instead of a recognizable cross-repo refusal.

**How to apply:**
- **Prefer `git -C <path>` and absolute paths over `cd`** for inspection. The harness guidance already says this (a `cd` in a compound command can also trigger a permission prompt); the spawn-misrouting consequence is the sharper reason.
- If you do `cd`, **`cd` back to the org root before the next spawn**, and verify with `pwd` — do not assume.
- **Put a self-check in the brief.** Every isolated spawn should begin with the agent verifying its own worktree:
  `git rev-parse --show-toplevel` (assert the expected repo) plus an existence probe for a path the story needs. Tell the agent to **stop and report** on mismatch rather than improvise — that is what turned this into a 1-message recovery instead of a corrupted PR.
- **Child-repo implementers: spawn NON-isolated** and create a worktree *inside the child repo* (`git -C <child> worktree add`). Isolation is for parent-repo (`noorinalabs-main`) spawns only. Remember the commit-identity gate resolves the roster from the shell's **CWD**, not `git -C`'s target, so the agent must `cd` into the child worktree to commit.
- A misrouted worktree with no commits is **auto-removed** when the agent stops, so cleanup is usually free — but verify siblings survived before removing anything by hand.
