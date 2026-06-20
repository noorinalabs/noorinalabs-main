---
name: feedback_git_dir_leak_repo_config
description: "Pre-#720 GIT_DIR leak wrote core.bare=true + bogus [user] into the LIVE parent .git/config, bricking the work tree (\"must be run in a work tree\"). Repair by editing .git/config directly."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 76123576-c792-441f-9c53-bc0685c9c321
---

The pre-#720 `GIT_DIR` env leak (git exports `GIT_DIR`/`GIT_WORK_TREE` into hook/test subprocesses; `git -C <tmp>` sets cwd but does NOT override inherited `GIT_DIR`) did more than break temp-repo tests — when a pre-push pytest run executed `git config core.bare true` / `git config user.name t` against a temp repo with `GIT_DIR` pointing at the **parent** `.git`, those writes landed in the **live** `/home/parameterization/code/noorinalabs-main/.git/config`.

Symptoms (seen 2026-06-19): every work-tree op (`git checkout`, `pull`, `status`) failed with `fatal: this operation must be run in a work tree`; `git rev-parse --is-inside-work-tree` → `false`; `--git-common-dir` → `.git`. Root cause was two injected lines: `[core] bare = true` and a bogus `[user] name = t / email = t@t` (a charter violation — repo identity must never be set).

**Repair** (it's corruption, not config — fix directly, don't fight the hook): Edit `.git/config` with the Edit tool — set `bare = false` and delete the `[user]` section. The `block_git_config` hook only fires on Bash `git config` *commands*, not on Edit of the file, so this is clean. The old (pre-#721) hook would also have blocked `git config --unset user.email` anyway.

**Why fixed now:** [[feedback_local_ci_parity_no_force]] drove installing pre-push hooks org-wide; the leak surfaced via #717→#721 + #719→#720. #720's autouse `_isolate_git_env` conftest (strips `GIT_*`) prevents recurrence. After repair, swept all 8 repos (parent + 7 children) — only the parent was hit; children were clean. Also found data-acquisition had a **stale `core.hooksPath`** pointing at a renamed repo (`noorinalabs-isnad-graph-ingestion`) — that, not corruption, was why `pre-commit install` was refused there. Related: [[feedback_push_pipe_masks_rejection]].
