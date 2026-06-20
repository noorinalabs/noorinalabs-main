---
name: feedback_pre_spawn_verify_file_exists
description: "Manager pre-spawn \"verified at HEAD\" claim MUST use `git cat-file -e origin/<branch>:<path>` for file-existence, not `ls`/ruff/working-tree state — working tree can lag deletions by months."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 7bef55d7-053c-4d9a-8b6c-969061a60e9c
---

Manager-class pre-spawn briefs that cite per-file findings (e.g., "ruff finds 1 error in `<path>`") MUST verify file existence at the wave-branch HEAD via `git cat-file -e origin/<branch>:<path>`, NOT via filesystem checks (`ls`, ruff run from cwd, `find`, glob).

**Why**: Working tree / local main can lag origin/wave-branch by weeks or months when files have been deleted in intervening waves. A file removed in W5 may still sit in working tree on session resume (no `git clean -fdx` after deletion-merge); ruff cheerfully reports the lint finding against the stale on-disk copy. The "verified at HEAD" line in the brief then encodes a working-tree fact masquerading as a branch-HEAD fact.

Specific instance: P3W11 data-acquisition spawn brief for Tarek on issues #47 (UP017 annunaki_log.py) + #52. Pre-spawn brief asserted "Verified at HEAD" with two sub-bullets:
1. `git show origin/wave-11:.claude/hooks/annunaki_log.py` returned `fatal: path … exists on disk, but not in 'origin/deployments/phase-3/wave-11'` — I MISREAD this as "file exists, just not staged on branch" and inferred "PR rebases on wave-11 will land it."
2. Live `uvx ruff@0.7.4 check .claude/hooks/annunaki_log.py` → `Found 1 error` — I treated this as confirmation.

Actual state: file was deleted in P3W5 PR #37 commit `0c53c9f` "drop copy-resident hook remnants — parent-canonical sweep" (authored by me) on 2026-05-05. Both findings (#47 parent-meta, #52 W7 retro scan ran 2026-05-08) referenced a file already-removed at finding-time. Tarek's pre-spawn verify-at-HEAD caught it; my pre-spawn verify did not because I conflated `ls`-state with branch-HEAD-state.

**How to apply**: For every per-file claim in a spawn brief, run:
```
git cat-file -e origin/<wave-branch>:<path> && echo EXISTS || echo "NOT IN HEAD"
```
The `fatal: path … exists on disk, but not in '<ref>'` from `git show` is the SAME signal as `git cat-file -e` failing — both mean the file is in working tree but NOT in the named ref. Treat that message as a HARD STOP, not a "needs rebase" indicator. If file is absent at wave-HEAD, the finding is stale → close issue, do not spawn.

Sibling to [[feedback_pre_spawn_brief_verified_at_head]] (caveat sweep) and [[feedback_refresh_before_status_claim]] (SUPERSEDED form, charter pull-requests.md § Origin > Local Clone). This memory specializes to the file-existence sub-case and to the manager pre-spawn layer (the SUPERSEDED memory covered reviewer "still has X" claims).

**Cost of not catching at manager layer**: 1 round-trip (manager → team-lead spawn approval → team-lead spawn → implementer verify → release back through team-lead → manager close). Tarek caught it; would have been cheaper to catch in my brief composition.
