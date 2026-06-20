---
name: feedback_local_ci_parity_no_force
description: "Owner mandate 2026-06-14: every repo MUST have pre-commit/pre-push hooks mirroring the FULL CI tooling (tests + every linter + cspell + actionlint + …); never commit/push code that fails checks without owner permission; persist in the charter(s)."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: b923c0f4-c87a-4bed-b4b8-91a79287509b
---

**Owner directive 2026-06-14 (P5W4):** "Every repo should contain a precommit or pre push hook that runs the relevant tests, and any tooling (linter, cspell, etc.). Do not force commits or pushes that fail checks without my permission. This should probably be persisted in the charter(s)."

Two binding rules:
1. **Full local⇄CI tooling parity.** Each repo's `.pre-commit-config.yaml` (commit + push stages) MUST mirror *every* check CI enforces — tests, every linter/formatter, type-check, **cspell**, actionlint, gitleaks, etc. — not just the subset (ruff/mypy/pytest) currently mirrored. The `pre_commit_ci_sync.py` drift gate must *enforce* this completeness (it currently ignores unclassified kinds like cspell — blind spot, see [[project_wave_key_cross_phase_collision]]-style "gate has a hole" pattern). Tracked: **main#684**.
2. **No force-pushing failing checks.** Never commit/push code that fails checks without explicit owner permission. `--no-verify` is already hook-blocked; this extends to *not opening a PR red* — a known-failing check (even a pre-existing one like ingest#89's precommit-ci-sync) requires owner sign-off before merge, not a unilateral carve-out. P5W4: I held PR #88 (red precommit-ci-sync) for owner permission rather than merging on my own "pre-existing" judgment.

**Why:** P5W4 Batch 1 shipped 3 PRs red to CI (ig#1080 cspell 'Aqidah', deploy#460 cspell 'Webauth', us#170 ruff I001 on a generated alembic file). Root causes: cspell isn't mirrored locally anywhere AND the sync-gate can't see it; and agents' fresh `git worktree`s have NO pre-commit hooks wired, so "ran clean locally" was a partial manual run. Both classes are preventable with real local⇄CI parity + a green-before-push discipline.

**How to apply:**
- Implementer spawn-briefs MUST require running the repo's *actual* CI check-set over the full tree in the worktree (`uv run ruff check . && ruff format --check`, the cspell command, `pre-commit install && pre-commit run --all-files`, tests) BEFORE opening a PR. Green-on-first-push; no follow-up fix-CI commits. See [[feedback_ruff_parent_config_bleed]] (worktree ≠ CI config) and [[feedback_ruff_format_check_before_push]].
- Before merging any PR with a red check, STOP and get owner permission — even if the red is pre-existing/not-the-PR's-fault.
- Persisted in charter by Aino Virtanen (Standards & Quality Lead) — CI⇄local parity + push discipline section. Cross-repo hook rollout tracked in main#684.
