# Pull Requests

When all work on a feature branch is complete (code committed, review done, must-fixes resolved), the submitting team member **automatically creates a PR to the deployments branch** for their wave using the `gh` CLI. Do not wait for manual instruction.

**PR ownership:** Only the team member who implemented the work creates the PR. The Program Director must NOT create duplicate PRs for the same branch.

> **Section index (#963).** This file's sections now live as per-concern files under [`charter/pull-requests/`](pull-requests/). Every heading below is preserved so existing `pull-requests.md#anchor` deep-links keep resolving — each entry forwards to the section's new location. The promotion markers (`promotion-target` / `promoted-to`) moved with the section bodies; this index is not a promotion-audit input.

## Comment-Based Reviews (Mandatory)
All reviews are `gh pr comment` comments using the four-field review grammar (`gh pr review` is blocked). → [pull-requests/reviews.md](pull-requests/reviews.md#comment-based-reviews-mandatory)

## Review Prompt Template (Mandatory)
Review assignments must embed a copy-paste-ready, pre-filled review-comment command. → [pull-requests/reviews.md](pull-requests/reviews.md#review-prompt-template-mandatory)

## Two-Reviewer Assignment at Wave Kickoff
Every PR gets a named primary + secondary reviewer at wave kickoff. → [pull-requests/reviews.md](pull-requests/reviews.md#two-reviewer-assignment-at-wave-kickoff)

## All Deliberately-Assigned Reviewers Must Approve Before Merge (Blast-Radius PRs)
Three-plus deliberately-assigned reviewers means ALL of them must approve — two is a floor, not a cap. → [pull-requests/reviews.md](pull-requests/reviews.md#all-deliberately-assigned-reviewers-must-approve-before-merge-blast-radius-prs)

## Single-Reviewer Exception (Wave-Bootstrap Only)
The narrow waiver scope for wave-bootstrap tooling PRs. → [pull-requests/reviews.md](pull-requests/reviews.md#single-reviewer-exception-wave-bootstrap-only)

## Load-Bearing Followups for Disabled CI Jobs
A followup that re-enables a disabled CI job must carry re-enablement as first-class acceptance. → [pull-requests/ci-gates.md](pull-requests/ci-gates.md#load-bearing-followups-for-disabled-ci-jobs)

## PR Review Workflow for Deployments Branch PRs
The create → notify → review → merge flow for wave-branch PRs. → [pull-requests/wave-merge.md](pull-requests/wave-merge.md#pr-review-workflow-for-deployments-branch-prs)

## Additive Commits on ChangesRequested (Mandatory)
Fixes for a ChangesRequested verdict land as additive commits — no force-push during review. → [pull-requests/reviews.md](pull-requests/reviews.md#additive-commits-on-changesrequested-mandatory)

## Review Finding Disposition
Every review finding is dispositioned before merge; none silently dropped. → [pull-requests/reviews.md](pull-requests/reviews.md#review-finding-disposition)

## Post-Merge Integration Verification
Verify the integrated result after each merge into a deployments branch before merging the next PR. → [pull-requests/wave-merge.md](pull-requests/wave-merge.md#post-merge-integration-verification)

## CI Workflow `pull_request` Triggers Must Cover Wave Branches
`branches:` filters must include active wave branches or be omitted entirely. → [pull-requests/ci-gates.md](pull-requests/ci-gates.md#ci-workflow-pull_request-triggers-must-cover-wave-branches)

## Cross-Contract PRs
The first of mutually-dependent in-flight PRs must carry the shared-contract block. → [pull-requests/wave-merge.md](pull-requests/wave-merge.md#cross-contract-prs)

## Cross-PR Dependency Sequencing
Ordering rules for dependent PRs within one wave. → [pull-requests/wave-merge.md](pull-requests/wave-merge.md#cross-pr-dependency-sequencing)

## One Merge Model Per Wave (Mandatory)
A wave uses exactly one merge model, chosen at kickoff and never mixed. → [pull-requests/wave-merge.md](pull-requests/wave-merge.md#one-merge-model-per-wave-mandatory)

## Wave Merge PR Verification
Checks the manager runs before presenting the wave-to-main PR. → [pull-requests/wave-merge.md](pull-requests/wave-merge.md#wave-merge-pr-verification)

## Wave-Wrapup Staging-Promotion Gate (Mandatory)
A wave is not closeable until its merged code is staging-green. → [pull-requests/wave-merge.md](pull-requests/wave-merge.md#wave-wrapup-staging-promotion-gate-mandatory)

## End-State Criterion Verification Requires Live-Environment Evidence (Mandatory)
Phase end-state criteria are MET only on cited live-environment evidence. → [pull-requests/wave-merge.md](pull-requests/wave-merge.md#end-state-criterion-verification-requires-live-environment-evidence-mandatory)

## PR Template
Canonical `gh pr create` command and body shape (Summary / Related Issues / Review Checklist), plus the advisory doc-freshness gate. → [pull-requests/authoring.md](pull-requests/authoring.md#pr-template)

## Closes-vs-Refs Disposition — Decided at Brief Time, Never Flipped
`Closes` vs `Refs` is decided once, when the brief is authored — never flipped in flight. → [pull-requests/authoring.md](pull-requests/authoring.md#closes-vs-refs-disposition--decided-at-brief-time-never-flipped)

## Pre-Push Checklist
Lint, format, typecheck, full tests, and branch-name check before every push. → [pull-requests/authoring.md](pull-requests/authoring.md#pre-push-checklist)

## CI Must Be Green Before Merge
No merge on red CI, even when failures are pre-existing. → [pull-requests/ci-gates.md](pull-requests/ci-gates.md#ci-must-be-green-before-merge)

## Full Local⇄CI Tooling Parity + No Force-Merging Failing Checks (Mandatory)
Owner directives (#684): pre-commit/push mirror the COMPLETE CI check-set; a red gate is a stop. → [pull-requests/ci-gates.md](pull-requests/ci-gates.md#full-localci-tooling-parity--no-force-merging-failing-checks-mandatory)

## Org-Wide Branch Protection + Admin-Merge Exceptions (Mandatory)
Server-side required checks on every default branch, plus the narrow admin-merge protocol. → [pull-requests/ci-gates.md](pull-requests/ci-gates.md#org-wide-branch-protection--admin-merge-exceptions-mandatory)

## CI Enforcement After PR Creation
The author's watch duty over their PR's checks after creation. → [pull-requests/ci-gates.md](pull-requests/ci-gates.md#ci-enforcement-after-pr-creation)

## Design-Rationale Block for Critical-Path PRs (Mandatory)
Critical-path PRs carry a design-rationale block at the load-bearing decision point. → [pull-requests/acceptance-scope.md](pull-requests/acceptance-scope.md#design-rationale-block-for-critical-path-prs-mandatory)

## Trust the Artifact, Not the Framing (Mandatory)
Verify spec assumptions and PR-body claims against ground truth before acting. → [pull-requests/evidence-standards.md](pull-requests/evidence-standards.md#trust-the-artifact-not-the-framing-mandatory)

## Trivial Cross-Repo Doc Sweep
Lightweight single-PR-per-repo protocol for identical N-repo doc corrections. → [pull-requests/authoring.md](pull-requests/authoring.md#trivial-cross-repo-doc-sweep)

## Security Guards Belong Inline, Not in a Followup (Mandatory)
Runtime security guards land in the PR itself; followup issues are tracking, not fixes. → [pull-requests/acceptance-scope.md](pull-requests/acceptance-scope.md#security-guards-belong-inline-not-in-a-followup-mandatory)

## Live-Trace Evidence > Synthetic-Test Acceptance (Mandatory)
Prefer the gate firing on a real in-the-wild artifact over synthetic-test acceptance. → [pull-requests/evidence-standards.md](pull-requests/evidence-standards.md#live-trace-evidence--synthetic-test-acceptance-mandatory)

## Text-Processing / NER / Graph Fixtures Must Use Production-Realistic Input (Mandatory)
Fixtures derive from real upstream samples, never hand-authored to the parser's own schema. → [pull-requests/evidence-standards.md](pull-requests/evidence-standards.md#text-processing--ner--graph-fixtures-must-use-production-realistic-input-mandatory)

## PR-Time Acceptance vs Runtime Acceptance (Mandatory)
Split the PR-mechanic delivery from gated runtime steps when an issue has both. → [pull-requests/acceptance-scope.md](pull-requests/acceptance-scope.md#pr-time-acceptance-vs-runtime-acceptance-mandatory)

## Sandbox Test-Verification Pattern — Unit-Construct + Cite-CI When the Suite Hangs (Mandatory)
Unit-construct locally and cite CI when the suite needs backing services the sandbox lacks. → [pull-requests/evidence-standards.md](pull-requests/evidence-standards.md#sandbox-test-verification-pattern--unit-construct--cite-ci-when-the-suite-hangs-mandatory)

## Close Runtime-Gated Issues on Verified-Live, Not on Merge (Mandatory)
Runtime-gated issues use `Refs #N` and close on live verification, not on merge. → [pull-requests/acceptance-scope.md](pull-requests/acceptance-scope.md#close-runtime-gated-issues-on-verified-live-not-on-merge-mandatory)

## Origin > Local Clone for "Still-Has-X" File-Content Claims (Mandatory)
Query origin via the contents API for still-has-X claims — never the local clone. → [pull-requests/evidence-standards.md](pull-requests/evidence-standards.md#origin--local-clone-for-still-has-x-file-content-claims-mandatory)

## Retro PR Body-vs-Diff Discipline (Mandatory)
Every file the retro PR body claims must be in the retro PR's diff. → [pull-requests/wave-merge.md](pull-requests/wave-merge.md#retro-pr-body-vs-diff-discipline-mandatory)

## `gh pr edit` projects-classic deprecation — use REST API for body/title updates (Mandatory)
Use REST PATCH for PR body/title updates — `gh pr edit` silently no-ops on older gh versions. → [pull-requests/authoring.md](pull-requests/authoring.md#gh-pr-edit-projects-classic-deprecation--use-rest-api-for-bodytitle-updates-mandatory)
