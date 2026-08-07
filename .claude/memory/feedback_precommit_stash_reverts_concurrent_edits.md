---
name: feedback_precommit_stash_reverts_concurrent_edits
description: Two agents in one worktree — a pre-commit-gated commit by A stashes and restores B's UNCOMMITTED edits, so B's verified change silently reverts mid-session.
metadata:
  type: feedback
last_verified: 2026-08-04
---

**Never put two writing agents in one worktree, even on disjoint file sets.** The
collision is not the index — it is `pre-commit`'s stash/restore.

**Mechanism.** `pre-commit` stashes *unstaged* working-tree changes before running
hooks and restores them after. When agent A commits (even with an explicit pathspec
touching only A's own files), the stash sweeps up **agent B's uncommitted edits to
completely unrelated files**. During the hook window those edits are absent from the
tree; if the restore fails — `error: patch failed: <file>` / `patch does not apply`,
which happens when B writes again mid-window — they are stranded in
`~/.cache/pre-commit/patch<timestamp>-<pid>` and the tree silently reverts to the
committed state.

**Observed, wave-29 retro (2026-08-04).** Two agents shared
`.claude/worktrees/w29-retro` on disjoint files (orchestrator: `feedback_log.md`;
implementer: `trust_signals.py`). The implementer edited a code comment, verified it
with `rg` (no matches for the old text), and a few tool calls later `rg` found the
**old text back in the file** with a clean `git status` at an unexpected HEAD. Nothing
he ran explains it. The orchestrator had committed in between, and one such commit
did emit `error: patch failed: .claude/lib/wave_status.py:72 / patch does not apply`.
Explicit-pathspec commits (`git commit -- <paths>`) do **not** protect against this —
they scope what is *committed*, not what pre-commit *stashes*.

**Why it is dangerous.** It fails the way everything in this wave failed: silently,
with a well-formed wrong answer. `git status` is clean, the file parses, tests pass —
the change is simply gone. An agent that verified its edit and moved on ships nothing.

**How to apply.**

- **Give every writing agent its own worktree.** Serialize into one worktree only when
  work is genuinely sequential (implementer finishes → orchestrator commits).
- If a shared worktree is unavoidable, **commit immediately after editing** — the
  exposure window is edit→commit, and it lasts exactly as long as someone else's hooks.
- **Re-read the file after editing, not just at write time.** The `Edit` tool's success
  response attests the write happened, not that it survived. This is the only detection
  that works; `git status` shows clean either way.
- On `patch does not apply`, look in `~/.cache/pre-commit/patch*` before assuming the
  work is lost — and check both the working tree *and* `git show HEAD:<file>` before
  concluding anything, since the two can disagree.

Related: [[feedback_cwd_collision_cross_spawn]] (two agents, one cwd, different
branches), [[feedback_shared_worktree_review_revert_hazard]] (reviewer revert-to-test
corrupting a concurrent view) — same root cause, three distinct symptoms. Also
[[feedback_verify_after_edit_not_at_write]] if that note exists.
