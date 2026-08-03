---
name: feedback_scratchpad_shared_across_agents
description: "The session scratchpad directory is shared by EVERY agent in the session, not per-agent — two agents writing mutate.py clobber each other, and an agent can unknowingly report another agent's mutation results as its own."
metadata:
  type: feedback
last_verified: 2026-08-03
---

The harness scratchpad path (`/tmp/claude-1000/<project>/<session-id>/scratchpad/`) is keyed to the **session**, not the agent. Every spawned agent gets the identical path. Concurrent agents writing the same conventional filename — `mutate.py`, `fixture/`, `harness.sh`, `before.txt` — silently overwrite each other.

**Observed 2026-08-03, wave-29, 6 concurrent implementers.** Nino Kavtaradze's `mutate.py` was replaced mid-run by another agent's; his harness began emitting `NON_ROLE_ROW_KEYS` / `REVIEW_CLASS_ROLES`, symbols from Nadia Khoury's #1180 task. He caught it **only because the symbols came from a visibly different problem domain** and re-ran everything from a namespaced directory.

**Why this is worse than an ordinary race:** the failure is silent and the corrupted output still *looks* like a valid mutation table. Two agents mutation-testing similarly-shaped Python gates would produce plausible, interchangeable-looking results. An agent could report another agent's numbers as its own, and a reviewer reading "12/12 mutants killed" has no way to tell. Mutation evidence is exactly the artifact this org trusts most, which is what makes the collision expensive.

**How to apply:** every spawn brief that mentions the scratchpad MUST specify a **namespaced subdirectory** — `scratchpad/<name>-<issue>/` (e.g. `scratchpad/nadia-1180/`). Never hand two concurrent agents the bare scratchpad root. If a collision is suspected, re-run from a clean namespaced directory and discount every unreported number; treat already-reported mutation results as unverified until re-run.

**Use a NAME-unique prefix, not initials** (Nadia Khoury, 2026-08-03, correcting this note's first version). This note originally prescribed `<initials>-<issue>` and used `nk-1204` for Nino Kavtaradze — then the orchestrator briefed Nadia Khoury with `nk-1270`. `NK` collides between them, which is the same defect one level up: a namespacing scheme whose keys are not unique. She declined the suggested prefix and used `nadia-1180`.

**Restore from git, not from a scratch backup.** Weronika Zielinska's mutation harness saved `_shell_parse.py.orig` into the shared root and restored from it — so the *restore* step, not just the mutation, was exposed. `git checkout HEAD -- <file>` is immune: git's object store is per-worktree, not in the shared tmp dir. She re-derived all 7 rows that way and they reproduced identically.

**Why:** the brief that caused this told six agents to use the bare root. The org's own convention — keep scratch work OUTSIDE the repo ([[feedback_reviewer_scratch_outside_repo]]) — solved repo pollution and created this instead, because "outside the repo" was specified without "and not shared."

Related: [[feedback_cwd_collision_cross_spawn]] (the same class one level up — two agents sharing a cwd), [[feedback_shared_worktree_review_revert_hazard]] (two reviewers sharing one worktree), [[feedback_silent_zero_is_not_a_measurement]] (a corrupted measurement that still parses is worse than one that errors).
