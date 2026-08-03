---
name: feedback_work_tree_flag_pollutes_shared_index
description: "`git --work-tree=<scratch>` run against the shared main checkout writes to the SHARED index — it stages the scratch tree's contents over live paths, and the damage surfaces on another agent as an unexplained pre-commit failure."
metadata:
  type: feedback
last_verified: 2026-08-03
---

`git --work-tree=<dir>` does **not** create an isolated checkout. It redirects only the *working tree*; `--git-dir`/the discovered `.git` — **including the index** — stays the shared one. So running it against the main checkout to "pull a branch tree somewhere safe for grepping" stages the scratch tree's contents over the live paths in the **shared index** that every other agent in the session is committing against.

**Observed 2026-08-03, wave-29.** A reviewer used `git --work-tree=<scratch>` against the shared main checkout to grep a branch tree; it staged ~30 unrelated files into the live index. She caught it via `git status`, ran `git reset -- .`, verified the tree matched HEAD, and switched to `git archive | tar -x`.

**The damage surfaced on a different agent, as a different symptom.** The orchestrator's next commit failed with:

```
[ERROR] Your pre-commit configuration is unstaged.
`git add .pre-commit-config.yaml` to fix this.
```

while `git status --porcelain` showed that file **clean** and `git diff --stat HEAD -- .pre-commit-config.yaml` returned **nothing**. pre-commit compares index-vs-worktree, so a polluted index makes it complain about a file both other instruments call clean. The orchestrator wrote it off as transient and moved on; the real explanation only arrived when the reviewer disclosed the `--work-tree` run several minutes later.

**How to apply:**
- To read another tree, use **`git archive <ref> | tar -x -C <scratch>`** (no index involvement at all) or a real `git worktree add` / throwaway clone. Never `--work-tree` against a checkout anyone else is using.
- If you must, pair it with `GIT_INDEX_FILE=<scratch>/.git-index` so the index redirects too — but prefer `git archive`, which cannot go wrong.
- **A pre-commit/gate failure that contradicts `git status` is a signal about the INDEX, not a transient.** Check `git diff --cached --stat` before dismissing it. "It worked on retry" is not a diagnosis — here the retry only worked because someone else had already reset.

**Why:** the failure crosses agent boundaries, so the agent that sees the symptom is not the one that caused it and has no context to diagnose it. That is what makes it worth a note rather than a one-off fix — a lone-agent session would never reproduce it.

Related: [[feedback_scratchpad_shared_across_agents]] (same family: session-shared state that reads as agent-private), [[feedback_cwd_collision_cross_spawn]], [[feedback_shared_worktree_review_revert_hazard]].
