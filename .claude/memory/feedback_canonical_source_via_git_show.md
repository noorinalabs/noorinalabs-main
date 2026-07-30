---
name: feedback_canonical_source_via_git_show
description: Worktree files can be pre-merge even when origin/main has the canonical merged version. Always retrieve canonical source via git show <sha>:<path>, not from the working tree.
type: feedback
originSessionId: 43b60daf-62e0-4fa1-b083-aef94bac4edf
promotion_target: charter
promotion_threshold:
  retro_citations: 3
status: superseded
superseded_by: charter:state-claims.md § Canonical Source via `git show <sha>:<path>`
superseded_at: 2026-05-06
---
When a task says "use the canonical version from commit X on main", do NOT trust the worktree — local main may not yet include X even if `origin/main` does. Compare: `git log main --oneline | head -5` against `git ls-remote origin main`. If they differ, pull the file via `git show <sha>:<path> > /tmp/canonical.file` and copy FROM there.

**Why:** During noorinalabs-main#112 part (b), the task description said PR #186 at sha 508b6cd was on main. True for origin/main, but the local worktree was on an earlier commit (615f4c8) that DID NOT include #186 — so `.claude/hooks/validate_commit_identity.py` in the worktree was the PRE-#186 design. Silently copying the worktree file to child repos would have downgraded them past the very merge I was syncing forward. `git show 508b6cd:.claude/hooks/validate_commit_identity.py` gave the correct 232-line `_load_merged_roster` version.

**How to apply:** For any "sync from parent sha X" task: (1) confirm `git log --oneline --all | rg <sha>` shows it exists locally, (2) check whether local `main` actually contains it via `git branch --contains <sha>`, (3) pull the file via `git show <sha>:<path>` regardless of worktree state. Worktree is convenience; git object database is truth.

**Recurrence 2026-06-21 (P6W1, main #779) — SIBLING-REPO variant, charter-broadening candidate.** A reviewer (Nadia) ChangesRequested an architecture-diagram PR for omitting two services (`isnad-graph-embed`, `loki-runtime-init`) she'd read in `noorinalabs-deploy` compose at 1505 lines. The author (Santiago) **confidently refuted** the finding — "those services don't exist, `git grep` zero hits" — having read his **local** `../noorinalabs-deploy` working copy, which was stale at `bbf8936` (1383 lines, 28 services, predating both additions). The orchestrator adjudicated by pulling the file at the SIBLING repo's origin HEAD (`gh api repos/noorinalabs/noorinalabs-deploy/contents/compose/docker-compose.prod.yml`, = 273f220, 1505 lines, 30 services) — both services present exactly as the reviewer said. The **1505-vs-1383 line-count mismatch between the two parties was the tell** that they'd read different versions. Lesson: the canonical-source-via-`git show` rule applies just as hard when **verifying or refuting a claim against another repo's file** — read it at that repo's `origin/main` (`git show origin/main:<path>` after `git fetch`, or `gh api .../contents`), never the local sibling checkout, which is frequently many commits behind. Failure mode here was severe: a *correct* review was nearly overturned, and the author's "fix" hardened a now-false exhaustiveness claim before the origin check caught it. Pairs with [[feedback_verify_diagnosis_before_delegating]] (API/working-tree state ≠ ground truth) and [[feedback_refresh_before_status_claim]]. **/promotion-audit:** consider broadening charter:state-claims.md § Canonical Source to explicitly name the sibling-repo / cross-repo refutation case.
