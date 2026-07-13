# Briefing Pack — Implementer

Enumerated reading list for an agent spawned to **write code and open a PR** (org repo or child repo). Links only — the rules live in the linked sections; this pack copies nothing (#963). Read in order; load a section only when its trigger applies.

## Always read

1. [`commits.md`](../commits.md) — per-commit `-c` identity flags + co-author trailers; never `git config`.
2. [`branching.md`](../branching.md) — `{FirstInitial}.{LastName}/{IIII}-{issue-name}` branch names off the wave branch; worktree isolation.
3. [`pull-requests/authoring.md` § PR Template](../pull-requests/authoring.md#pr-template) — canonical `gh pr create` command and body shape.
4. [`pull-requests/authoring.md` § Pre-Push Checklist](../pull-requests/authoring.md#pre-push-checklist) — lint, format, typecheck, full tests, branch-name check before every push.
5. [`pull-requests/ci-gates.md` § Full Local⇄CI Tooling Parity + No Force-Merging Failing Checks](../pull-requests/ci-gates.md#full-localci-tooling-parity--no-force-merging-failing-checks-mandatory) — a red gate is a stop, even pre-existing.
6. [`pull-requests/ci-gates.md` § CI Enforcement After PR Creation](../pull-requests/ci-gates.md#ci-enforcement-after-pr-creation) — watch your PR's checks after creation; report `statusCheckRollup`, not local results.
7. [`pull-requests/reviews.md` § Comment-Based Reviews](../pull-requests/reviews.md#comment-based-reviews-mandatory) — the four-field review-comment grammar you use to request review and reply.

## When responding to review

8. [`pull-requests/reviews.md` § Additive Commits on ChangesRequested](../pull-requests/reviews.md#additive-commits-on-changesrequested-mandatory) — fix via additive commits; never force-push mid-review.
9. [`pull-requests/reviews.md` § Review Finding Disposition](../pull-requests/reviews.md#review-finding-disposition) — every finding dispositioned before merge.

## When your change involves tests, fixtures, or claims about file state

10. [`pull-requests/evidence-standards.md` § Text-Processing / NER / Graph Fixtures](../pull-requests/evidence-standards.md#text-processing--ner--graph-fixtures-must-use-production-realistic-input-mandatory) — fixtures derive from real upstream samples.
11. [`pull-requests/evidence-standards.md` § Sandbox Test-Verification Pattern](../pull-requests/evidence-standards.md#sandbox-test-verification-pattern--unit-construct--cite-ci-when-the-suite-hangs-mandatory) — unit-construct + cite CI when the suite needs backing services.
12. [`pull-requests/evidence-standards.md` § Origin > Local Clone](../pull-requests/evidence-standards.md#origin--local-clone-for-still-has-x-file-content-claims-mandatory) — still-has-X claims query origin, not the local clone.

## When your issue has a runtime/production component

13. [`pull-requests/acceptance-scope.md` § PR-Time Acceptance vs Runtime Acceptance](../pull-requests/acceptance-scope.md#pr-time-acceptance-vs-runtime-acceptance-mandatory) — deliver the PR mechanic; runtime gates are tracked, not silently claimed.
14. [`pull-requests/authoring.md` § Closes-vs-Refs Disposition](../pull-requests/authoring.md#closes-vs-refs-disposition--decided-at-brief-time-never-flipped) — the disposition in your brief is final; do not flip it.
15. [`pull-requests/acceptance-scope.md` § Security Guards Belong Inline](../pull-requests/acceptance-scope.md#security-guards-belong-inline-not-in-a-followup-mandatory) — runtime guards land in the PR itself.

## Working in a child repo

16. [`agents/spawn-discipline.md` § Child-Repo Implementer Rule](../agents/spawn-discipline.md#child-repo-implementer-rule--spawn-brief-verification-mandatory) — your identity comes from the child repo's roster.

## Hooks you will hit

17. [`hooks/catalog-01-12.md`](../hooks/catalog-01-12.md) — commit identity (1), `--no-verify` block (2), `git config` block (3), `ENVIRONMENT=test` (4), label validation (5), branch freshness (9).
18. [`hooks/catalog-13-17.md` § Hook 14](../hooks/catalog-13-17.md#hook-14-validate-pr-ci-status-validate_pr_ci_statuspy) and [`hooks/catalog-18-22.md` § Hook 18](../hooks/catalog-18-22.md#hook-18-validate-edit-completion-validate_edit_completionpy) — CI-status merge gate; edit-completion gate.
