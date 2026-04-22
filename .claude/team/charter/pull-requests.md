# Pull Requests

When all work on a feature branch is complete (code committed, review done, must-fixes resolved), the submitting team member **automatically creates a PR to the deployments branch** for their wave using the `gh` CLI. Do not wait for manual instruction.

**PR ownership:** Only the team member who implemented the work creates the PR. The Program Director must NOT create duplicate PRs for the same branch.

## Comment-Based Reviews (Mandatory) <!-- promotion-target: none -->
All agents share a single GitHub user account. **`gh pr review --approve` is blocked** — it always fails with "cannot approve your own pull request". All PR reviews MUST use comment-based reviews instead.

**Review format** (posted via `gh pr comment`):
```
Requestor: <PR author name>
Requestee: <reviewer name>
RequestOrReplied: Approved | Changes Requested
TechDebt: none | #15, #16, ...
```

- The `Requestor` must differ from the branch author (validated by the merge hook). This is enforced by the `block_gh_pr_review.py` PreToolUse hook and validated by `validate_pr_review.py` at merge time.
- The `TechDebt:` line is **mandatory** on every review. If the reviewer found non-blocking observations, they MUST create `tech-debt` labeled issues BEFORE posting the review, then list the issue numbers. If no tech-debt was found, write `TechDebt: none`. This is enforced by the `validate_pr_review.py` PreToolUse hook at merge time.

## Review Prompt Template (Mandatory) <!-- promotion-target: none -->
When the orchestrator assigns a review to any agent, the prompt **MUST** include a copy-paste-ready `gh pr comment` command with all fields pre-filled. Do not rely on agents writing the format from memory — this has a 100% error rate.

**Template for orchestrator prompts:**
```
Post your review using this exact command:

gh pr comment {PR_NUMBER} --repo noorinalabs/{REPO} --body "Requestor: {AUTHOR_NAME}
Requestee: {REVIEWER_NAME}
RequestOrReplied: Approved
TechDebt: none

{Your review summary here.}"
```

Replace `Approved` with `Changes Requested` if blocking issues found. Replace `TechDebt: none` with issue numbers if tech-debt filed. Do NOT add bold markers, parenthetical descriptions, or extra fields.

**Why:** In Phase 3 Wave 1, all 7 initial reviews used wrong field names (`Requestee (reviewer):` instead of `Requestee:`) and omitted the `TechDebt:` line, requiring re-posts and blocking merges for ~15 minutes.

Failing to include the review template in a review assignment prompt is a **minor feedback event** for the orchestrator.

## Two-Reviewer Assignment at Wave Kickoff <!-- promotion-target: none -->
Every PR must have **two reviewers** assigned at wave kickoff — a primary and a secondary. Both reviewers are named in the agent's spawn prompt and in the execution plan.

**Why:** In Phase 3 Wave 1, only one reviewer was planned per PR. Every PR needed ad-hoc second reviewer assignments, causing merge delays while idle agents were redirected.

The Program Director's execution plan MUST include a review matrix with two named reviewers per expected PR. The orchestrator verifies this before spawning agents.

## Single-Reviewer Exception (Wave-Bootstrap Only) <!-- promotion-target: none -->
The two-reviewer requirement may be waived **exclusively** for wave-bootstrap PRs — i.e., PRs that establish the tooling/CI/hooks that subsequent wave PRs will be gated by (e.g., the pre-commit hook rollout that the CI sweep depends on).

Strict conditions — **all must hold**:
- The PR is part of wave bootstrap (establishes infra that blocks other wave work)
- No more than **one** such exception per wave
- The single reviewer is the Standards & Quality Lead (Aino) or a comparable charter enforcer
- The exception is logged by name in the wave retro, with explicit justification

All other PRs require two comment-based reviews. `--admin` merges without two reviews are subject to the moderate-feedback-event classification in § Feedback System.

**Why:** In Phase 2 Wave 8, the single-reviewer shortcut was invoked 8× — it had stopped being an exception and become a pattern of convenience. This clause formalizes the boundary.

## Load-Bearing Followups for Disabled CI Jobs <!-- promotion-target: skill -->
When a PR disables a CI job to unblock merge, the followup tracking issue must be **load-bearing** — the re-enablement of the job is a first-class acceptance criterion of the issue, not a hidden subtask of "fix the underlying bug."

Concrete requirements:
1. **Followup issue exists before the disable PR is approved.** The reviewer verifies the issue number in the PR body under a `## Disabled CI jobs (load-bearing followup)` section.
2. **Followup issue acceptance criteria** must include:
   - A specific fix for the underlying problem
   - Re-enable the CI job (remove `if: false` / `--skip` / equivalent)
   - Verify green CI after re-enablement
   - All three bullets are required in the issue body.
3. **Breadcrumb in PR body.** The PR that disables a job must include a top-level section `## Disabled CI jobs (load-bearing followup)` naming the job disabled, the reason, and the followup issue number.
4. **No silent disables.** A PR that disables a CI job without both the issue and the breadcrumb is a moderate feedback event.

**Why:** Phase 2 Wave 8 ratified this rule mid-wave after two PRs (isnad-graph#811, design-system#56) disabled CI jobs with tracking issues that could be "closed" by just fixing the bug without ever re-enabling the job. Promoting the rule into the charter closes that loophole. Reference: `feedback_disable_followup_load_bearing.md` (historical memory, superseded by this clause).

## PR Review Workflow for Deployments Branch PRs <!-- promotion-target: skill -->
1. **Create the PR** targeting `deployments/phase{N}/wave-{M}`.
2. **Notify reviewers** — the PR creator must notify at least **two** other team members to review the PR. Use SendMessage or a GitHub comment to notify. **A PR MUST NOT be merged without at least two peer reviews from distinct non-authors.** For waves with fewer than 4 engineers, the manager's review counts but must include a substantive review comment (not just "LGTM"). This is enforced by the `validate_pr_review.py` PreToolUse hook. **This rule applies even on fast/compact waves** — speed does not exempt PRs from the review gate. Wave 7 merged 5 PRs with zero reviews; this must not recur.
3. **Reviewer performs the review** and posts a comment-based review on the PR with:
   - **Must-fix items** — blocks merge; the submitter must resolve before proceeding.
   - **Tech debt items** — does not block merge; tracked as GitHub Issues.
   - The reviewer then **notifies the PR creator** (via SendMessage or mention) that the review is complete and what action is needed.
4. **PR creator acts on review**:
   - **Must-fix items**: Fix immediately and push to the branch.
   - **Quick-fix tech debt**: Fix immediately if minimal impact.
   - **Non-trivial tech debt**: Create a GitHub Issue for future planning.
5. **Push final changes** from the review fixes.
6. **The team merges** the PR into the deployments branch themselves — no user approval needed for PRs into deployments branches.

## Review Finding Disposition <!-- promotion-target: none -->
Every finding from a PR review must be dispositioned before merge. No finding may be silently dropped.

| Finding Type | Action Required | Blocks Merge? |
|-------------|----------------|---------------|
| **Must-fix** | PR originator fixes on the branch before merge | Yes |
| **Tech-debt** | Reviewer or originator creates a GitHub Issue for each item before merge | No (but issues must exist) |
| **Quick-fix tech-debt** | PR originator fixes immediately if minimal effort | No |

**Enforcement:** The charter enforcer (Aino) verifies during PR review that:
1. All must-fix items are resolved before approving merge
2. All tech-debt items have corresponding GitHub Issues created
3. Issues are labeled `tech-debt` and assigned to the appropriate team member

## Post-Merge Integration Verification <!-- promotion-target: skill -->
**After every PR merge into a deployments branch**, the manager must verify the integrated result before merging the next PR:

1. **Pull the updated deployments branch** locally (or in a worktree).
2. **Run the repo's full check command** (`make check`, `npm run check`, or equivalent — lint + typecheck + build).
3. **If the check fails:** The last-merged PR introduced a regression. The manager must notify the PR author to fix it before any further PRs are merged.
4. **If the check passes:** The next PR may be merged.

This catches semantic conflicts that GitHub's textual merge cannot detect (e.g., two PRs that individually pass CI but break when combined). Managers must NOT merge multiple PRs in rapid succession without verifying in between.

**CI enforcement:** All repositories must configure CI workflows to trigger on pushes to `deployments/**` branches (not just PRs). This provides automatic verification after each merge, complementing the manager's manual check.

## Cross-Contract PRs <!-- promotion-target: skill -->
When two or more PRs in flight consume/produce from each other (Kafka topics, Parquet schemas, shared API contracts, wire formats between workers or services), the **first PR opened MUST include a "Contract" section** in the PR body. Subsequent PRs that consume or produce against that contract link to it and document any divergence explicitly.

The Contract section must specify:

1. **Message / schema / API shape** — concrete example or reference to a shared constants module (e.g., `workers/lib/topics.py`).
2. **Ownership** — which PR owns the contract; which owner adjudicates disputes.
3. **Divergence** — how other PRs may legitimately deviate (optional fields, label supersets, etc.).

Any reviewer may block a cross-contract PR that fails this requirement.

**Rationale:** in P2W9, noorinalabs-isnad-ingest-platform#18 (Weronika) and #21 (Wanjiku) built in parallel on incompatible assumptions about message shape (per-row `{label, id, props}` vs Parquet batches with `hadiths.parquet` payload). The mismatch surfaced only during reviewer cross-check after both PRs were essentially complete, forcing an owner-chaired design call (noorinalabs-main#192) and substantive rewires on both branches. A 5-minute Contract section in whichever PR opened first would have caught this upfront.

Derived from Phase 2 Wave 9 retrospective, 2026-04-22.

## Cross-PR Dependency Sequencing <!-- promotion-target: skill -->
When multiple PRs in the same wave have dependencies (e.g., PR B depends on changes from PR A):

1. **Identify dependencies** before merging — check if any PR depends on another PR's changes
2. **Merge in dependency order** — base PR first, dependent PR second
3. **Do NOT merge dependent PRs in parallel** — even if both have green CI, the dependent PR's CI ran against the base branch WITHOUT the dependency
4. **After merging the base PR**, the dependent PR must rebase/merge the updated base before its CI result is trusted
5. **Document dependencies** in PR descriptions: "Depends on PR #N (must merge first)"

## Wave Merge PR Verification <!-- promotion-target: skill -->
At the **end of a wave or phase**, the Manager creates a PR from the deployments branch into `main`. Before presenting the PR to the user:

1. **Verify all CI checks are green** — run `gh pr checks {NUMBER}` and confirm every job passes.
2. **If any check fails**, fix it before notifying the user. The user should NEVER see a wave merge PR with red CI.
3. **Report CI status** explicitly when presenting the PR: "All N checks passing."
4. **Provide full clickable URLs** when presenting PRs to the user — use `https://github.com/{org}/{repo}/pull/{number}`, not `repo#number` format.

The **user reviews and merges** this PR. Do not proceed to the next phase until the user has merged.

## PR Template <!-- promotion-target: none -->
```bash
git push -u origin <branch-name>
gh pr create --base deployments/phase{N}/wave-{M} --title "<short title>" --body "$(cat <<'EOF'
## Summary <!-- promotion-target: none -->
<1-3 bullet points describing the change>

## Related Issues <!-- promotion-target: none -->
Closes #<issue-number>

## Review Checklist <!-- promotion-target: none -->
- [ ] Reviewed by another team member
- [ ] Must-fix items resolved
- [ ] Tech debt items filed as GitHub Issues (if any)

Co-Authored-By: Firstname Lastname <parametrization+Firstname.Lastname@gmail.com>
Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

- PR title should be concise (under 70 characters).
- The body must reference the related GitHub Issue(s) with `Closes #N`.
- The submitting team member is responsible for creating the PR immediately upon branch completion.

## Pre-Push Checklist <!-- promotion-target: none -->
Before pushing a branch and creating a PR, every engineer must:

1. **Run the repo's lint check** (`ruff check` / `npm run lint` / equivalent) — fix all errors.
2. **Run the repo's format check** (`ruff format --check` / `npx prettier --check` / equivalent) — fix any formatting issues.
3. **Run the repo's typecheck** (`mypy` / `npm run typecheck` / equivalent) — fix type errors.
4. **Run the full test suite** — `npm run test` / `make test` / equivalent. This includes unit tests AND E2E/Playwright if the repo has them. Do NOT skip tests — content changes can break test assertions.
5. **Verify branch name** — `git branch --show-current` must match `{FirstInitial}.{LastName}/{IIII}-{issue-name}`.

Pushing code that fails lint, formatting, or tests is a **minor feedback event**.

## CI Must Be Green Before Merge <!-- promotion-target: none -->
**No PR may be merged while CI is failing, even if failures are pre-existing.** If a new CI workflow is introduced and it catches pre-existing violations, those violations must be fixed before or in the same PR as the workflow addition.

- If CI is red on the target branch due to pre-existing issues, fix forward — create a predecessor PR that resolves the violations, merge it first, then merge the CI workflow PR.
- If CI is red on a feature branch, the PR author must fix the failures before requesting review.
- Merging a PR with known CI failures is a **moderate feedback event**.

**Why:** In Phase 2 Wave 1, PR #72 introduced a hook CI workflow that immediately failed on pre-existing ruff I001 lint in other files. CI went red on main because the violations weren't fixed before merge.

## CI Enforcement After PR Creation <!-- promotion-target: skill -->
After creating a PR, **every team member** must follow this process:

1. **Wait for all CI jobs to complete.** Do not merge or request review until CI has finished.
2. **If all CI jobs pass:** The PR is ready for review. Proceed with the normal review workflow.
3. **If any CI job fails:**
   - Investigate the failure and attempt to fix the root cause.
   - Push the fix to the **same branch** (the PR will update automatically).
   - Alert the project owner (user) with the following information:
     - Which CI job failed
     - Root cause of the failure
     - What was done to fix it
     - Whether project owner assistance is required
4. **If the failure cannot be resolved:** Do **NOT** merge the PR. Notify the project owner immediately and pause all dependent work until the issue is resolved.

Violating this process (e.g., merging with red CI, ignoring failures, or failing to escalate) is treated as a **moderate feedback event** per the Feedback System.
