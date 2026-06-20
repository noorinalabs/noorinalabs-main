---
name: feedback_reviewer_no_branch_switch
description: "Reviewer agents must read code via gh api at PR head, never `git checkout` a review branch in the parent main checkout — leaves UU conflict + branch drift for orchestrator to recover"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 4a42b118-bbc8-48d1-ba53-16b4689915f5
---

Reviewer agents (spawn class: reviewer) MUST read PR code via `gh api repos/.../contents/<path>?ref=<sha>` or `gh pr diff <N>`. They MUST NOT:

- `git checkout` a review-purpose branch in the **parent main checkout**
- `git stash` + `git checkout other-branch` + `git stash pop` patterns on the parent checkout

**Why:** Parent main checkout is shared session state. Orchestrator and other concurrent agents may rely on it being on a specific branch. Branch-switching + stash-pop can leave:
- HEAD on the wrong branch (silent — orchestrator finds it after the agent idles)
- UU unmerged index state on shared files (e.g., `ontology/checksums.json`) — looks like an active merge but isn't
- Local-only review branches (e.g. `pr-477-review`) that need cleanup

**Recurring failure mode in P3W11 — 2 instances same session (2026-05-18):**
- Instance 1 (~00:54Z): Santiago on PR #477 review. Did `git checkout -b pr-477-review` + stash-pop dance. Left parent at `W.Mwangi/0452` (1fb5ea9) with UU on `ontology/checksums.json`. Recovery: `git checkout --ours` + `git restore` + `git switch main`.
- Instance 2 (~01:15Z): unknown agent (Aino/Nurul/Santiago) during PR #479 or #480 review. EXACT same end state — parent at `W.Mwangi/0452` (1fb5ea9), UU on `ontology/checksums.json`. The original memory note had been filed but did NOT propagate to subagent context.

**Why the memory entry alone is insufficient**: it lives in the orchestrator's `.claude/projects/.../memory/` dir and is loaded into the orchestrator's session context only. Spawned subagents start with their own clean context and do not see it. The brief author must EXPLICITLY include the rule in every reviewer-spawn brief (which I started doing after instance 1, but the second instance happened in an agent that had a brief sent BEFORE the memory was filed — race condition).

**Promotion candidates for W11 retro**:
- Hook-tier: PreToolUse Bash hook that blocks `git checkout` or `git switch` in the parent main checkout when invoked from a session whose cwd is the parent — high blast radius, low friction (forces operators to use `git -C <worktree>`)
- Charter-tier: add to `agents.md` "Orchestrator checklist when spawning a reviewer" — explicit "include reviewer-must-not-branch-switch-parent rule" item
- Skill-tier: spawn-brief composer (if one is built) auto-includes the boilerplate

**How to apply:**

1. In every reviewer-spawn brief, add explicit instruction: "READ code via `gh api repos/.../contents/<path>?ref=<sha>` or `gh pr diff <N>`. Do NOT `git checkout` PR branches in the parent main checkout. If you need a local file, write a temp copy to `/tmp/` via the Write tool after fetching with gh api."
2. If a reviewer genuinely needs a tree-level checkout (e.g., to run the test suite locally against the PR head), spawn them in a **dedicated review worktree** created by the orchestrator pre-spawn: `git worktree add /tmp/review-pr-<N> <pr-head-sha>`. Brief specifies the worktree path imperatively (per [[feedback_spawn_brief_field_advisory_pattern]]).
3. Post-review cleanup belongs to the orchestrator, not the reviewer — reviewers post verdict and stop; orchestrator removes review worktrees + temp branches.

Sibling rule to [[feedback_review_against_artifact]] (which establishes gh-api-at-HEAD as the canonical read mechanism — this one extends it with a NEGATIVE-space rule about local-checkout side effects).
