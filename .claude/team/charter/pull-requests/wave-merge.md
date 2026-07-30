# Pull Requests — Wave Merge & Promotion

> Part of the [pull-requests charter index](../pull-requests.md) — re-shelved from `charter/pull-requests.md` for section-level loading (#963). Rules unchanged.

## PR Review Workflow for Deployments Branch PRs <!-- promotion-target: skill -->
1. **Create the PR** targeting `deployments/phase-{N}/wave-{M}`.
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

## One Merge Model Per Wave (Mandatory) <!-- promotion-target: skill -->

A wave uses **exactly one merge model for its entire lifetime**, chosen and recorded at `/wave-kickoff`. Mixing the two within a single wave is **prohibited**.

| Model | Where per-issue PRs base | Wave→main integration PR |
|-------|--------------------------|--------------------------|
| `direct-to-main` | every PR bases on `main` | none — work is already on `main`; the `deployments/phase-{P}/wave-{M}` branch stays at the kickoff point and never accumulates commits |
| `wave-branch` | every PR bases on `deployments/phase-{P}/wave-{M}` | opened at `/wave-wrapup` Step 11, merged via the `wave-merge` admin exception |

**Per-issue → wave-branch merges use `--merge`, NEVER `--squash` (hook-enforced).** GitHub squash-merge re-authors the squash commit to the bare gh principal (every persona email is a Gmail +alias of the one `parametrization@gmail.com` account), dropping persona content-commit authorship → the wave→main integration PR fails the `Verify commit authors are roster members` gate at wrapup (main#627). `--merge` preserves the persona-authored content commits (they pass the gate) and the bare-principal merge commit is excluded by `--no-merges`. Enforced by **Hook 22 (`block_squash_wave_merge.py`)**, which hard-blocks `gh pr merge <N> --squash` when the PR's base resolves to a `deployments/phase-*/wave-*` branch. Source: P7W19 #898/#222; memory `feedback_wave_branch_merge_not_squash`.

> **Superseded scope, 2026-07-30 (owner directive): `--squash` is now prohibited on EVERY base, not just wave branches.** The parenthetical that previously read "squash-into-`main` for feature work is untouched" no longer holds, and the companion clause in [`reviews.md`](reviews.md) § Pre-Approved merge that called squash "the standard path" for `main` has been withdrawn. The same re-authoring loss described above applies identically on `main` — confirmed 2026-07-30 when five PRs squash-merged to `main` and all landed as the bare `parametrization` principal. **Hook 22 still only covers the wave-branch case**, so on `main` this is convention-enforced, not gate-enforced; widening the hook is tracked separately. Treat the gate's silence on a `main`-based squash as an enforcement gap, never as permission.

**Origin (P6W1 retro, owner-approved 2026-06-21, [#801](https://github.com/noorinalabs/noorinalabs-main/issues/801)):** P6W1 *mixed* models — #704/#706/#734/#735 merged to the `deployments/phase-6/wave-1` branch while the doc batch + cspell/mermaid work went **direct to main**, and the wave→main PR was never opened. Five net-new deliverables sat stranded off `main`, caught only at `/wave-wrapup` Step 11.5 (resolved via #799).

**Declared at kickoff.** `/wave-kickoff` records the chosen model in `cross-repo-status.json` under `wave_{M}_merge_model` (one of `direct-to-main` / `wave-branch`) via `.claude/lib/wave_merge_model.py set {P} {M} <model>`. The default for cross-repo waves is `wave-branch`; a meta-only or single-repo wave may declare `direct-to-main`.

**Enforced mid-wave, not only at wrapup.** `/session-start` runs `wave_merge_model.py reachability {P} {M}`, which compares each in-scope repo's wave branch against `origin/main` and classifies the gap **against the declared model** — so model-mixing or stranding surfaces within hours instead of at the Step 11.5 wrapup gate (the durable strengthening #801 adds on top of that gate):

- `direct-to-main` + the wave branch carries commits ahead of `main` → **VIOLATION** (someone merged to the wave branch under a direct-to-main wave — the exact P6W1 mixing). Non-zero exit.
- `wave-branch` + ahead + an **open** wave→main PR → **OK** (the integration PR is tracking the work).
- `wave-branch` + ahead + **no** open wave→main PR → **ADVISORY** (expected mid-wave, but it *will* strand unless `/wave-wrapup` opens the PR).

Advisories are expected mid-wave states and do **not** fail `/session-start` (a non-fatal step); only a model VIOLATION exits non-zero. A wave whose `wave_{M}_merge_model` is absent (legacy / pre-#801) degrades to advisory-only with a nudge to declare it — never a false VIOLATION. The classification logic is unit-tested (`.claude/lib/tests/test_wave_merge_model.py`) and the gh I/O layer is shell-free (explicit arg-list, main#688).

## Wave Merge PR Verification <!-- promotion-target: skill -->
At the **end of a wave or phase**, the Manager creates a PR from the deployments branch into `main`. Before presenting the PR to the user:

1. **Verify all CI checks are green** — run `gh pr checks {NUMBER}` and confirm every job passes.
2. **If any check fails**, fix it before notifying the user. The user should NEVER see a wave merge PR with red CI.
3. **Report CI status** explicitly when presenting the PR: "All N checks passing."
4. **Provide full clickable URLs** when presenting PRs to the user — use `https://github.com/{org}/{repo}/pull/{number}`, not `repo#number` format.
5. **Merge via the `wave-merge` admin exception — this is the expected path, not a process failure.** The code on a `deployments/phase-{P}/wave-{M}` branch was already 2×-reviewed on its per-issue wave-branch PRs; the wave→main PR is an *integration* merge, not new code to re-review. After the user approves the merge sequence, the orchestrator merges each with a **literal PR number, one per call** (the `validate_pr_review` hook parses literal numbers — a loop variable fail-opens it): `ADMIN_MERGE_EXCEPTION="wave-merge:<rationale>" gh pr merge <N> --merge --admin`. Collecting *fresh* 2-reviewer approvals on the integration PR is **not** required and should not be requested. The `validate_pr_review` BLOCK (0/2 reviews) and the `--admin` exception prompt firing on these PRs is **expected and audited** (each exception is logged to the Annunaki trail per § Admin-merge exception list) — not a signal that something is wrong. Never `--delete-branch` (wave branches are retained, owner directive 2026-06-09). *Rationale: P4W5 fired this 4× — once per wave repo; the expected path was undocumented, producing per-wave "is this right?" friction.*

The **user approves the merge sequence**; the orchestrator executes the `wave-merge` merges per point 5. Do not proceed to the next phase until every wave→main PR is merged and the Step 11.5 reachability gate is clean.

## Wave-Wrapup Staging-Promotion Gate (Mandatory) <!-- promotion-target: skill -->

A wave is **not closeable** until its merged code has been promoted to **staging green**. This is Phase-3 end-state criterion #3 (`noorinalabs-main#325`): "/wave-wrapup requires successful stg promotion as a wave-completion criterion." The gate is the wrapup-time enforcement counterpart of the same liveness contract the deploy track exists to satisfy — code that merged to main but never reached a green staging deploy is the deploy-track analogue of the stranded-wave-branch pattern (§ the reachability gate in `/wave-wrapup` Step 11.5).

### The gate

`/wave-wrapup` Step 11.6 (immediately after the Step 11.5 reachability-to-main gate) verifies that the staging deploy is green for the wave's merged code:

1. **Workflow:** the canonical staging deploy is `noorinalabs-deploy/.github/workflows/deploy-stg.yml` (triggered by service-repo `repository_dispatch` fan-in on push, or `workflow_dispatch` for a manual redeploy). The gate inspects the latest `deploy-stg.yml` run reachable for the wave's merged commits.
2. **Block on red:** if the latest staging run concluded `failure`/`cancelled`/`timed_out`, the wave is NOT closeable. The operator fixes-forward (re-trigger the deploy, fix the regression) before re-invoking `/wave-wrapup`.
3. **Dependency-aware deferral (criterion #1):** criterion #3 is **blocked by criterion #1** (staging must exist). Until a live staging environment + `deploy-stg.yml` run history exist, the gate reports `staging-promotion gate DEFERRED — criterion #1 (live staging) not yet satisfied` and proceeds. This deferral is itself logged (so it is visible, not silent) and disappears automatically once staging is live. The gate must NOT hard-fail every wrapup before staging exists.
4. **Override (when red is acceptable):** an explicit `STG_PROMOTION_OVERRIDE_RATIONALE="<reason>"` env var lets the operator close a wave despite a red/absent staging run (e.g. staging infra is mid-migration, the wave is meta-only with no deployable surface). Rationale is required (no empty string), logged to the wrapup report, and persisted — mirroring the Step 11.5 `STRANDING_OVERRIDE_RATIONALE` mechanism.
5. **Persistence + retro hand-off:** the staging-promotion result (`success` / `failure` / `deferred` / `overridden`) is written to `cross-repo-status.json` as `wave_{M}_stg_promotion` via the shared `upsert_status_keys.py` helper, alongside the run URL. `/wave-retro` records the stg-promotion result in the wave history row next to PR count and admin overrides.

### Why a gate, not a checklist

A "remember to check staging" checklist item is opt-in and decays (`feedback_enforcement_hierarchy`: "Charter rules without enforcement decay"). Encoding the gate in the `/wave-wrapup` skill with a hard block (and a noisy, rationale-required override) makes staging-green a contractual wave-completion condition — the deploy track's whole purpose per Phase-3 end-state.

<!-- Promoted from memory: feedback_enforcement_hierarchy (hook>skill>charter — gate-over-checklist) — codifies Phase-3 end-state criterion #3 (issue #325, deploy-track-alongside Proposal B ratified 2026-05-31). Skill-tier enforcement lands in /wave-wrapup Step 11.6; a hook MAY further enforce at invocation time (follow-up). -->

## End-State Criterion Verification Requires Live-Environment Evidence (Mandatory) <!-- promotion-target: skill -->

A Phase **end-state criterion** (the `noorinalabs-main#60x`-class tracking meta-issues) may be marked **MET** only when its verification cites **live-environment evidence** — an `ssh` / `cypher-shell` query against the deployed datastore, a `curl` against the live vhost, or a Chrome/Playwright trace of the deployed app. CI-green, testcontainers, and in-process-harness results are **necessary but not sufficient**: they prove the code works, not that the criterion is true on the running system.

**Why:** P4W5 found Phase-4 end-state #1 ("data pipeline runs E2E on staging") had been treated as shipped on the strength of CI/harness runs (ingest-platform#55, main#139), while the live staging Neo4j held 47 out-of-band hadiths and **zero** narrator graph — the deployed pipeline had never run (main#601, verified by `ssh noorinalabs-stg` + `docker exec cypher-shell`). "Shipped in CI ≠ shipped on the VPS." An end-state claim backed only by harness evidence is a false exit waiting to surface a wave — or a phase — late.

**How to apply:** the auditor of a `#60x` end-state criterion records the live-env command + its output (or run URL) in the issue's verification comment (cf. #605's `users.stg.noorinalabs.com/metrics → 403` curl-proof). A criterion whose live-env check is not yet runnable (e.g. blocked by another unmet criterion) stays **OPEN and explicitly NOT-MET** — it is never marked MET on harness evidence alone, and its remediation is dispositioned (carried or re-scheduled), not silently closed.

<!-- Promoted from retro: P4W5 #601 not-met lesson (owner-approved 2026-06-13). Extends § Live-Trace Evidence > Synthetic-Test Acceptance (PR-time) to phase end-state criteria. -->

## Post-Merge Integration Verification <!-- promotion-target: skill -->
**After every PR merge into a deployments branch**, the manager must verify the integrated result before merging the next PR:

1. **Pull the updated deployments branch** locally (or in a worktree).
2. **Run the repo's full check command** (`make check`, `npm run check`, or equivalent — lint + typecheck + build).
3. **If the check fails:** The last-merged PR introduced a regression. The manager must notify the PR author to fix it before any further PRs are merged.
4. **If the check passes:** The next PR may be merged.

This catches semantic conflicts that GitHub's textual merge cannot detect (e.g., two PRs that individually pass CI but break when combined). Managers must NOT merge multiple PRs in rapid succession without verifying in between.

**CI enforcement:** All repositories must configure CI workflows to trigger on pushes to `deployments/**` branches (not just PRs). This provides automatic verification after each merge, complementing the manager's manual check.

## Retro PR Body-vs-Diff Discipline (Mandatory) <!-- promotion-target: skill -->

The retro PR is the **authoritative artifact** for a wave's ratified changes. If the retro accepts charter, skill, or trust-matrix updates, those file edits MUST land **in the retro PR's diff** — not via direct-to-main commits committed alongside.

### Why

The retro PR is where future reviewers, audits, and `git log --first-parent main -- .claude/team/charter/` trace **wave theme → ratified charter changes → trust updates**. Direct-to-main commits for substantive retro outputs break that trace and bypass two gates the charter relies on:

1. **The two-reviewer rule** (`pull-requests.md § Comment-Based Reviews`) — direct-to-main commits skip review entirely. No `RequestOrReplied: Approved` comments, no `validate_pr_review` hook gate, no peer scrutiny of the charter/skill text that future agents are bound by.
2. **`validate_pr_ci_status`** (`hooks.md § Hook validate_pr_ci_status`) — no PR means no CI gate, so charter/skill edits land without `hooks-lint`, schema validation, or any other automated check that the PR path would have run.

The audit-trail break is the more durable harm: a ratified charter section with no PR linkage looks identical, six months later, to a charter section someone slipped in unreviewed. The retro PR body claiming files that aren't in the diff makes the mismatch worse — it manufactures the appearance of review for changes that received none.

### How to apply

**For retro-PR authors:**

- **In-scope for the retro PR diff:** every charter, skill, trust-matrix, or memory file the retro ratified, plus the `feedback_log.md` narrative and `ontology/checksums.json` resolution. Edit on the retro branch; commit; push; let the diff land via the PR.
- **Out-of-scope for direct-to-main:** ratified charter/skill/trust-matrix changes. There is no "small enough to land direct" carve-out — if it was a retro proposal accepted by the user, it goes through the retro PR.
- **PR body discipline:** the "Files changed" section of the retro PR body MUST match `gh pr view <N> --json files --jq '.files[].path'`. If the body lists a file the diff doesn't contain, fix the diff (push the commit) — do NOT amend the body to remove the claim.

**For retro-PR reviewers (Mandatory enforcement clause):**

Before approving a retro PR, run:

```bash
gh pr view <N> --repo <owner>/<repo> --json files --jq '.files[].path' | sort > /tmp/retro_<N>_diff_files.txt
# Then read the PR body's "Files changed" section and compare.
```

If the body claims any file (charter/skill/trust-matrix, in particular) that is not in `/tmp/retro_<N>_diff_files.txt`, post **ChangesRequested** with the specific missing path(s). Approving a retro PR whose body claims files absent from the diff is a charter violation in the reviewer-class.

### Skill enforcement

`/wave-retro` (Step 6 / Step 8) and `/wave-wrapup` SHOULD run a body-vs-diff sanity check before emitting the retro summary or wrapup table:

```bash
RETRO_PR=<N>
gh pr view "$RETRO_PR" --repo <owner>/<repo> --json files --jq '[.files[].path] | sort' > /tmp/retro_diff.json
# Parse the PR body's "Files changed" section.
# For each path claimed in body but missing from /tmp/retro_diff.json, ABORT with a clear "body claims X not in diff" error.
```

Promotion target on this section is `skill` — the retro skill is the natural home for the check, and the `/promotion-audit` pipeline can pick it up on a future pass.

### Severity if violated

- Retro PR body lists a charter/skill file that is not in the diff, and the actual edit is committed direct-to-main: **severe**. Bypasses two-reviewer gate and CI; breaks the audit trail. Reviewer who approved it shares the severity.
- Retro PR body lists files that aren't in the diff, but the edits never actually landed (typo in body, no direct-to-main commit either): **moderate**. The audit trail is salvageable by editing the body, but the misleading framing already shipped to anyone who read the merged PR.
- Retro author commits substantive charter/skill changes direct-to-main alongside the retro PR but does NOT claim those files in the body: **moderate-to-severe** depending on whether the change was substantive. The two-reviewer gate is still bypassed even without the body mismatch.

### Worked example

`noorinalabs/noorinalabs-main` PR [#124](https://github.com/noorinalabs/noorinalabs-main/pull/124) (W8 retro, merged 2026-04-17). The PR body listed seven files: `feedback_log.md`, `trust_matrix.md`, `charter/pull-requests.md` (2 new sections), `charter/hooks.md`, `skills/wave-retro/SKILL.md`, `skills/wave-kickoff/SKILL.md`, `ontology/checksums.json`. The actual PR diff contained two: `feedback_log.md` + `ontology/checksums.json`. The five substantive charter/skill/trust-matrix changes landed via two direct-to-main commits (`2b92605`, `ecd1c76`) with no PR — bypassing two-reviewer review and `validate_pr_ci_status`. Found by Santiago's post-merge review of #124; filed as [#126](https://github.com/noorinalabs/noorinalabs-main/issues/126).

### Cross-references

- `pull-requests.md § Comment-Based Reviews` — the two-reviewer gate this rule protects.
- `hooks.md § Hook validate_pr_ci_status` — the CI gate this rule protects.
- `pull-requests.md § Trust the Artifact, Not the Framing` — sibling rule on the reviewer side: read the artifact, not the body framing. This rule extends the discipline to the **author** side of the retro PR.
- `skills/wave-retro/SKILL.md` — the skill that should adopt the body-vs-diff sanity check per the Skill enforcement clause above.

