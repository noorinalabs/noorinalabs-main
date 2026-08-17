---
name: feedback_cross_repo_wave_ref_resolution
description: Workflows that check out sibling repos for cross-repo tests must resolve refs to the wave branch (with main fallback) when running against wave-PR base
type: feedback
last_verified: 2026-07-27
originSessionId: af6f52a7-e25c-41f4-9365-06539062b665
promotion_target: charter
promotion_threshold:
  retro_citations: 3
status: active
---
When a CI workflow in one repo checks out sibling repos to run a cross-repo test, the sibling-repo `ref:` cannot be hardcoded to `main`. In a wave-coordination workflow where each child repo has its own `deployments/phase-N/wave-M` branch, schema/contract changes that have merged to the wave branch are absent from `main` until wave-wrapup.

**Why:** Discovered 2026-04-24 in P2W10. deploy#159 reverted the `alembic upgrade heads` workaround (US#63), but `integration-tests.yml` checked out `noorinalabs-user-service@main`. user-service#80 (the merge migration `0040_merge_multi_heads.py`) had merged to user-service's wave-10 branch, NOT main. CI failed with `Multiple head revisions are present for given argument 'head'` — exactly the workaround the revert was eliminating. Lucas's #154 (already merged) had explicitly noted the limitation in its body: "actual test runs against user-service and isnad-graph `main`."

**How to apply:** For any workflow that does `actions/checkout@v4` of a *sibling repo* (not the same repo the workflow lives in), resolve the ref dynamically:

1. Read `${{ github.base_ref }}` (set on `pull_request`) or `${{ github.ref_name }}` (set on `push`/`workflow_dispatch`).
2. If the resolved base starts with `deployments/`, attempt `git ls-remote --exit-code https://github.com/<org>/<sibling-repo>.git refs/heads/<base>` to verify the sibling has the same wave branch.
3. If yes, check the sibling out at that wave branch. If no (wave branch doesn't exist on that sibling), fall back to `main`.
4. Echo the resolved refs to `$GITHUB_STEP_SUMMARY` for debugging.

Pattern reference: deploy PR #159 second commit (Aisha, 2026-04-24). Likely belongs in a reusable composite action if cross-repo wave PRs accumulate (file as P2W11 tech-debt).

This rule applies to ANY workflow with sibling-repo checkouts, not just integration-tests. Audit other workflows when adding new cross-repo test patterns.
