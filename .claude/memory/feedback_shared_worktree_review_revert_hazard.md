---
name: feedback_shared_worktree_review_revert_hazard
description: "Two reviewers pointed at the SAME implementer worktree collide when one reverts source to prove tests bite — it transiently corrupts the other's working copy and can produce misleading test runs. Review from an isolated checkout at the committed head SHA."
metadata:
  type: feedback
last_verified: 2026-07-20
---

When multiple reviewers are assigned to one PR and the orchestrator points them at the **implementer's existing worktree** (the one the `Agent`/`isolation: worktree` spawn created), they share one working tree. The regression-verification technique every good reviewer uses — *revert the source hunk, keep the tests, confirm the new tests go red* ([[feedback_gate_early_allow_is_the_failopen]] and the #1041/#1043 "tests must bite" discipline) — **mutates that shared tree**. A second reviewer reading `git status` mid-review sees the source files staged-reverted and the branch code absent, then flipped back to clean moments later. That is not a bug in the PR; it is the other reviewer's revert-to-test in flight.

**Observed:** PRs #1056 / #1058 (Hook 4 fail-closed family). Both Nino Kavtaradze and Lucas Ferreira were pointed at Aino's worktree `agent-a0f5f610…`. Lucas reverted `_shell_parse.py` + `_repo_flag_parse.py` to test-that-tests-bite; Nino, reviewing concurrently, caught the transient dirty/reverted state on `git status`. Nino handled it correctly — he did **not** trust the working copy; he created his OWN detached `git worktree add` at the committed head SHA (`6911ada`) in scratch and reviewed/tested there deterministically.

**Why:** a review verdict must certify the *committed* code, not a working copy some other process is mutating. A shared-worktree test run can pass or fail for reasons that have nothing to do with the PR, and the reviewer would never know which.

**How to apply:**
- **Reviewer:** never review from a worktree another agent might be mutating. `gh pr checkout <N>` into your own dir, or `git worktree add <scratch> <head_sha>` at the PR's committed head SHA, and run tests there. Anchor on the head SHA, not the PR number ([[feedback_verdict_head_sha_anchoring]]) — deterministic and immune to concurrent writes.
- **Orchestrator (brief):** when assigning ≥2 reviewers to one PR, do NOT tell them to reuse the implementer's worktree. Tell each to work from their own isolated checkout at the committed head SHA. The revert-to-test step guarantees a collision otherwise.

Related: [[feedback_cwd_collision_cross_spawn]] (two agents sharing one cwd on different branches), [[feedback_subagent_worktree_wrong_repo]] (worktree isolation targets the parent org repo).
