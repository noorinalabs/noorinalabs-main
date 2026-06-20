---
name: feedback_ruff_format_check_before_push
description: Pre-push muscle memory — `uvx ruff@<pinned> format --check .claude/hooks/` catches what hooks-lint CI will block on, avoiding additive format-fix commits
type: feedback
originSessionId: 327bdb0e-5fea-4971-8f0f-e1e28b937e1c
promotion_target: hook
promotion_threshold:
  retro_citations: 3
status: active
---
When pushing changes under `.claude/hooks/` (production code OR tests), run
`uvx ruff@<pinned-version> format --check .claude/hooks/` locally before
pushing. The `hooks-lint` CI gate runs the same command at the same pinned
version (`uvx ruff@0.15.11 format --check .claude/hooks/`) and FAILS the
check if anything's unformatted, which then blocks `gh pr merge` via the
`validate_pr_ci_status.py` hook.

**Why:** P3W4 isnad-graph#858 (Linh Pham, 2026-05-04) — added a new test
file under `.claude/hooks/tests/` that wasn't ruff-formatted. CI flagged it
post-push, requiring an additive whitespace-only fix commit. Wasted ~5 min
of CI cycle and required the team-lead to flag it back. Reviewers' approvals
stayed load-bearing because the additive diff was pure format, but it's
churn that's avoidable.

**How to apply:** before any `git push` from a worktree where you've
edited or added files under `.claude/hooks/`, run:
```
uvx ruff@<version-pinned-in-CI> format --check .claude/hooks/
```
Look up the pinned version in the CI workflow if unsure. Format any files
that fail the check before staging the commit. Don't push, then patch.

This applies to ALL repos with a `hooks-lint` CI gate (parent + every
child repo with a `.claude/hooks/` tree and matching workflow).
