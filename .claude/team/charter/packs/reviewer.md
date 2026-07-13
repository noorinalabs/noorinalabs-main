# Briefing Pack — Reviewer

Enumerated reading list for an agent spawned to **review a PR**. Links only — the rules live in the linked sections; this pack copies nothing (#963). Read in order; load a section only when its trigger applies.

## Always read

1. [`pull-requests/reviews.md` § Comment-Based Reviews](../pull-requests/reviews.md#comment-based-reviews-mandatory) — the four-field verdict grammar (`gh pr review` is blocked); on verdict comments the comment author is the reviewer.
2. [`pull-requests/reviews.md` § Review Prompt Template](../pull-requests/reviews.md#review-prompt-template-mandatory) — your spawn brief embeds the pre-filled verdict command; use it verbatim.
3. [`pull-requests/evidence-standards.md` § Trust the Artifact, Not the Framing](../pull-requests/evidence-standards.md#trust-the-artifact-not-the-framing-mandatory) — review the diff/code at the PR head via the contents API, never the PR body's claims (and never `git checkout` in the parent).
4. [`pull-requests/reviews.md` § Review Finding Disposition](../pull-requests/reviews.md#review-finding-disposition) — every finding you raise must be dispositioned before merge.
5. [`state-claims.md`](../state-claims.md) — refresh artifact state before any "still at X / already done" assertion.

## Evidence standards for what you accept

6. [`pull-requests/evidence-standards.md` § Live-Trace Evidence > Synthetic-Test Acceptance](../pull-requests/evidence-standards.md#live-trace-evidence--synthetic-test-acceptance-mandatory) — prefer the gate firing on a real artifact.
7. [`pull-requests/evidence-standards.md` § Text-Processing / NER / Graph Fixtures](../pull-requests/evidence-standards.md#text-processing--ner--graph-fixtures-must-use-production-realistic-input-mandatory) — reject hand-authored fixtures that mirror the parser's own schema.
8. [`pull-requests/evidence-standards.md` § Origin > Local Clone](../pull-requests/evidence-standards.md#origin--local-clone-for-still-has-x-file-content-claims-mandatory) — verify file-content claims at origin head_sha.
9. [`pull-requests/acceptance-scope.md` § Security Guards Belong Inline](../pull-requests/acceptance-scope.md#security-guards-belong-inline-not-in-a-followup-mandatory) — ChangesRequested when a needed runtime guard is deferred to a followup.
10. [`pull-requests/acceptance-scope.md` § Design-Rationale Block](../pull-requests/acceptance-scope.md#design-rationale-block-for-critical-path-prs-mandatory) — critical-path PRs must carry rationale at the decision point.
11. [`pull-requests/acceptance-scope.md` § PR-Time vs Runtime Acceptance](../pull-requests/acceptance-scope.md#pr-time-acceptance-vs-runtime-acceptance-mandatory) — do not demand prod-only evidence as PR acceptance; do demand the unit mechanic.

## Verdict mechanics and gates

12. [`pull-requests/reviews.md` § Two-Reviewer Assignment](../pull-requests/reviews.md#two-reviewer-assignment-at-wave-kickoff) and [§ All Deliberately-Assigned Reviewers Must Approve](../pull-requests/reviews.md#all-deliberately-assigned-reviewers-must-approve-before-merge-blast-radius-prs) — who must approve before merge.
13. [`pull-requests/reviews.md` § Additive Commits on ChangesRequested](../pull-requests/reviews.md#additive-commits-on-changesrequested-mandatory) — what a compliant fix-up from the author looks like.
14. [`hooks/catalog-01-12.md` § Hook 7](../hooks/catalog-01-12.md#hook-7-validate-pr-review-validate_pr_reviewpy) and [§ Hook 8](../hooks/catalog-01-12.md#hook-8-block-gh-pr-review-block_gh_pr_reviewpy) — the enforcement behind comment-based reviews; your verdict must parse (roster-form Requestor name, `TechDebt:` literal line, fields after the last `---`).
15. [`pull-requests/ci-gates.md` § CI Must Be Green Before Merge](../pull-requests/ci-gates.md#ci-must-be-green-before-merge) — no approval-to-merge on red CI, even pre-existing.

## When the PR sits on unmerged upstream or a dependency change

16. [`pull-requests/wave-merge.md` § Cross-Contract PRs](../pull-requests/wave-merge.md#cross-contract-prs) and [§ Cross-PR Dependency Sequencing](../pull-requests/wave-merge.md#cross-pr-dependency-sequencing) — co-verify against the upstream source, and check merge ordering.
