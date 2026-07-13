---
name: feedback_hook_cwd_anchor_subagent_worktree
description: "Hooks that derive repo identity from stdin `cwd` payload resolve to the ORCHESTRATOR'S cwd, not the subagent's worktree — child-repo operations get misrouted to parent. Workaround: pass `--repo` explicitly; fix: walk up from actual cwd to nearest .git/config"
metadata:
  node_type: memory
  type: feedback
  originSessionId: 77e35de5-3b28-48a1-92f6-f413bc8debac
---

When a subagent operates inside a child-repo worktree (e.g., `.worktrees/deploy-0242-step2-promote`) and invokes `gh pr create` (or any other gh command that triggers a hook), the hook's stdin payload contains a `cwd` field set to the **orchestrator's** working directory at spawn time, NOT the subagent's actual `pwd` after it has `cd`'d into the worktree.

**Why:** Hooks read `cwd` from the tool-invocation context, which is captured at agent-spawn time by the harness. Subsequent `cd` calls inside the subagent change the subagent's shell state but do NOT propagate back to the hook's view of `cwd`. So `_resolve_implicit_repo` (which walks from `cwd` to find `.git/config` and reads `[remote "origin"]` URL) ends up at the orchestrator's parent dir (`noorinalabs-main`) and resolves repo to `noorinalabs/noorinalabs-main` — wrong target — instead of the child repo the subagent actually wants to push to.

The block manifests as: `gh pr create` (with no `--repo`) → hook rejects with "branch not fresh" or similar parent-repo-keyed error, because the parent repo has no such branch.

**How to apply:**

**Workaround (implementer-side, immediate):** Always pass `--repo <full/name>` and `--head <branch>` explicitly to `gh pr create` (and similar gh commands) when running from a subagent worktree. This routes through the hook's `if repo:` branch and bypasses the cwd-based resolution.

**Spawn-brief side (orchestrator):** When spawning an implementer to work in a child-repo worktree, the brief MUST include explicit `--repo <full/name>` instructions for any gh command that could trigger a cwd-anchored hook. Don't rely on the subagent's `cd` to fix the cwd-anchor.

**Hooks that exhibit this class** (prior art): #144 and #227 fixed the cwd-anchor in two earlier hooks. `validate_branch_freshness` still has it as of 2026-05-19. Other hooks not yet audited; broader cwd-anchor sweep is the proper fix.

**The proper fix:** hooks should either (a) read the calling subprocess's actual `pwd` via process introspection rather than the stdin `cwd` field, or (b) walk up from a known-good reference point (e.g., the `--repo` flag if present, then GH_REPO env var, then `cwd`) — with fallback chain. Filed as noorinalabs-main issue 2026-05-19 (PR #342 surface).

**P3W11 deploy#242 PR #342 (2026-05-19):** Aisha Idrissi hit this on first `gh pr create` from her worktree. She self-debugged by reading the hook's `_resolve_implicit_repo` and adding `--repo --head` explicit flags. Worked. Cost: one round-trip of debugging. Pattern was clear enough that she identified it as same-shape as #144/#227 without prompting. Sibling to [[feedback_spawn_brief_protocol]] (origin-vs-local-clone class) and a sibling to [[feedback_declarative_head_needs_action]] (subagent-state vs orchestrator-state class).
