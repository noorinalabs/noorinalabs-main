# Pull Requests — CI Gates

> Part of the [pull-requests charter index](../pull-requests.md) — re-shelved from `charter/pull-requests.md` for section-level loading (#963). Rules unchanged.

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

## CI Workflow `pull_request` Triggers Must Cover Wave Branches <!-- promotion-target: none -->

CI workflows using a `pull_request` trigger MUST include active wave branches in the `branches` filter, OR omit the filter entirely so the workflow triggers on any base branch. Workflows whose `branches` filter is locked to `["main"]` (or any other single-branch list) silently skip CI on PRs targeting `deployments/phase-{N}/wave-{M}` — the wave PRs that aggregate before the main merge. This is the inverse of the push-trigger rule above: push triggers must cover `deployments/**`, AND PR triggers must cover them too.

**Required pattern** — explicit branch list including wave branches:

```yaml
on:
  pull_request:
    branches: ["main", "deployments/**"]
```

**OR — path-filtered (no branches filter at all):**

```yaml
on:
  pull_request:
    paths:
      - "src/**"
      - "tests/**"
```

**Anti-pattern** — main-only filter that drops wave-branch PRs:

```yaml
on:
  pull_request:
    branches: ["main"]   # WRONG: wave-branch PRs skip CI silently
```

**Reviewer enforcement:** When a PR adds or modifies a `.github/workflows/*.yml` file with a `pull_request: branches:` filter, reviewers MUST flag any single-branch list that does NOT include `deployments/**`, unless the PR body explicitly justifies the exclusion (e.g., "this workflow only runs on main-merge promotions, not pre-merge PRs").

**Why:** P2W10 surfaced this convention gap twice independently. (1) `noorinalabs-user-service/ci.yml` had `branches: ["main"]` — Anya's user-service#80 alembic-merge PR targeting `deployments/phase-2/wave-10` produced an empty `statusCheckRollup` (filed user-service#81). (2) `noorinalabs-deploy/integration-tests.yml` had the same anti-pattern — wave-10 PRs touching `integration-tests/**` would skip CI (filed deploy#152, fix in deploy#154). Both are the same CI-trigger-filter-written-against-single-branch-PR-flow error. Per [`feedback_enforcement_hierarchy.md`](../../feedback_log.md), charter codification is step 1 + 2 (rule + reviewer reference); a future `validate_ci_trigger_branches` PreToolUse hook is filed as step 3 if the convention proves robust without manual reviewer reminders.

## CI Must Be Green Before Merge <!-- promotion-target: none -->
**No PR may be merged while CI is failing, even if failures are pre-existing.** If a new CI workflow is introduced and it catches pre-existing violations, those violations must be fixed before or in the same PR as the workflow addition.

- If CI is red on the target branch due to pre-existing issues, fix forward — create a predecessor PR that resolves the violations, merge it first, then merge the CI workflow PR.
- If CI is red on a feature branch, the PR author must fix the failures before requesting review.
- Merging a PR with known CI failures is a **moderate feedback event**.

**Why:** In Phase 2 Wave 1, PR #72 introduced a hook CI workflow that immediately failed on pre-existing ruff I001 lint in other files. CI went red on main because the violations weren't fixed before merge.

## Full Local⇄CI Tooling Parity + No Force-Merging Failing Checks (Mandatory) <!-- promotion-target: none -->

Two owner directives (2026-06-14, `noorinalabs-main#684`) on local-hook/CI discipline, binding on **every** repo.

### 1. Full local⇄CI tooling parity

Every repo's `.pre-commit-config.yaml` (commit-stage AND push-stage hooks together) MUST mirror the **complete** set of checks its CI enforces — not a subset. If CI runs it, a local hook must run it too: the relevant test suite, **every** linter and formatter, the type-checker, **cspell**, `actionlint`, `gitleaks`, schema/drift gates, and any other gate in `.github/workflows/`. The point is that a clean local commit/push is a faithful predictor of green CI — a partial mirror that omits (say) cspell lets a spelling failure reach CI that the developer had no local signal for.

- **Commit vs push staging is a latency choice, not a coverage choice.** Fast checks (format, lint) belong on the commit stage; heavier checks (typecheck, full test suite, cspell over the tree, actionlint) belong on the push stage. Either way, the *union* of the two stages must equal the CI check-set.
- The `.claude/lib/pre_commit_ci_sync.py` **sync-drift gate** is the machine-enforcement of this parity, and its enforcement must be **complete** — today it silently ignores check kinds it cannot classify (e.g. cspell), which is exactly the blind spot this rule closes. Closing that gap (classifying every CI kind so an unmirrored cspell/actionlint/gitleaks job fails the gate) and rolling the full-parity hook set out to every child repo is tracked by **`noorinalabs-main#684`**. Do NOT treat the current gate's silence on an unclassified kind as evidence of parity, and do NOT claim to fix the gate code under this section — that is #684's per-repo work.

### 2. No force-committing / force-pushing / force-merging failing checks

Never commit, push, or merge a PR with a **known-failing check** without explicit owner permission — and this holds **even when the failing check is pre-existing and not caused by your change**. `--no-verify` is already hard-blocked (`hooks.md` Hook 2 `block_no_verify`); this rule extends the same stance to the *outcome*: a red gate is a stop, not a speed bump.

- A pre-existing red check is **not** a unilateral "carve-out." Per § CI Must Be Green Before Merge, the path is *fix-forward* (a predecessor PR that greens the check, merged first) — never "merge through it because it was already broken."
- If a check genuinely cannot be greened in-scope (infra-dependent runtime gate, advisory-DB drift, etc.), that is an **owner decision** — surfaced with the one-line diagnosis and the evidence, not a self-granted exception. The recognized admin-merge exception classes (§ Admin-merge exception list) are the *only* pre-authorized bypasses; anything else needs explicit owner sign-off.
- **Severity:** force-merging a failing check without owner sign-off is a **moderate** feedback event (matching § CI Must Be Green Before Merge); doing so on a security-relevant gate (`gitleaks`, `security-audit`) is **severe**.

**Cross-references:** § Pre-Push Checklist (run the gates before you push), § CI Must Be Green Before Merge (fix-forward, not merge-through), `hooks.md` Hook 2 (`block_no_verify`), `agents.md` § Orchestrator checklist when spawning an implementer (the green-before-push spawn-discipline item), and the `CLAUDE.md` § Local Hooks section (full-parity + no-force restated for the orchestrator repo).

## Org-Wide Branch Protection + Admin-Merge Exceptions (Mandatory) <!-- promotion-target: none -->

### No-PR path allowlist — the four exempt paths and why it is a risk, not a nothing (#1487) <!-- promotion-target: none -->

Four paths in **`noorinalabs-main` only** commit to `main` without a PR: `.claude/memory/**`, `cross-repo-status.json`, `ontology/**`, `.claude/generic_prompt_ledger.json`. A commit is exempt only if **every** path it touches is on the list. `CLAUDE.md` § Developer Tooling carries the rule; this section carries the reasoning, and **anyone proposing to widen the list must re-argue the trade below rather than cite precedent.**

**Do not justify this as "generated files" or "records of work already reviewed elsewhere."** That was the original rationale on #1487 and it is **false for three of the four members**:

| path | why the original rationale is wrong |
|---|---|
| `.claude/memory/**` | `@import`-ed into `CLAUDE.md` via `MEMORY.md` (grep `^@\.claude/memory` — deliberately no line number; this PR's own edits moved it once already) — it is **prompt**, carrying the same authority as `CLAUDE.md` itself. The rule PR-gates `CLAUDE.md` and un-gates its own import target. |
| `cross-repo-status.json` | Read by `validate_wave_audit` (PreToolUse, blocks `/wave-wrapup`), which **allows** when `wave_active == false` or when the file is missing/malformed. A one-token unreviewed edit can flip a blocking gate to ALLOW. |
| `ontology/**` | Of 13 tracked files, **12 are hand-curated** — including `conventions.md`, which `CLAUDE.md` cites as normative for shell rules. Only `checksums.json` is machine-written (`ontology_tracker.py` → `checksums_io.write_checksums`), and the *generated* layer `ontology/structural/` is gitignored and tracked **zero** times here. So "generated" fits exactly one member — and that member is **65 of 70** `ontology/` touches **in PR-unassociated (no-PR) commits** over 300 first-parent commits — the only population this rule governs, counted by the PR-association method § Measured basis mandates below. (Counted the deprecated ways instead you get 70/76 over all first-parent commits, or 69/75 over non-merge commits; the share is ~92–93% under all three, so the argument is unaffected — but a paragraph teaching a classification rule must not report a number computed by the method it deprecates.) That makes *"narrow the glob to `ontology/checksums.json`"* the obvious next proposal. It is deliberately **not** taken here: the other 12 files are low-churn, and the measured practice being codified covers the whole tree. Anyone narrowing it should re-measure rather than infer from this note. |
| `.claude/generic_prompt_ledger.json` | The one member the original rationale actually fits — a wave-wrapup artifact. |

**The real reasons this is tolerable** are narrower than the original claim: these are high-churn coordination artifacts the lifecycle skills write inline; post-push CI still runs on `main`; and the practice is **long-standing, not a recent trend** — see § Measured basis below, and note that the "held for a month" version of this sentence was itself an artifact of the miscount recorded there. **The residual risk is real and deliberately accepted** — an unreviewed commit to these paths can change the model's own instructions or a gate's verdict.

**Measured basis, with its denominator — and the methodology trap that makes it easy to get wrong.** Over the 60 most recent first-parent commits on `main` (2026-09-03): 31 via PR, 29 direct, the 29 touching only these four paths. Widening the window does not overturn this but does require care: `--squash` was banned org-wide on 2026-07-29 (`2d8bd91`), so **before that date a squash-merged PR appears on `main` as a non-merge commit and a shape-based scan miscounts it as direct.** Classify by **PR association** (`gh api repos/{o}/{r}/commits/<sha>/pulls`), not by parent count. On that basis the only off-allowlist direct commits in the last 200 are **six** charter/docs bookkeeping commits ending 2026-08-02 — `trust_matrix.md`, `feedback_log.md` ×2, the two `pull-requests/` policy docs, `CLAUDE.md`, `.gitignore` — and **never a hook, lib, skill, or workflow**.

This warning is here because the trap was sprung on this very rule: a shape-based re-derivation counted **16** off-allowlist commits, of which **10** were reviewed squash-merged PRs (#1126, #1127, #1128, #1130, #1136, #1143, #1154, #1155, #1156, #1173). That produced a false "the practice tightened on 2026-08-03" story, when the real discontinuity is `2d8bd91` — eleven minutes after the last squash-merge, with zero squash-shaped commits after it. So this allowlist codifies a **long-standing narrow practice that was never written down**, not a recent trend.

Branch protection stays **ON** — ruleset `17139856` is `active` — but that fact does not enforce the allowlist. **The allowlist is a policy, enforced by nothing at any layer (#1493):**

- **Not the ruleset.** `rules: ["deletion", "non_fast_forward", "pull_request"]` carries no path condition, and GitHub rulesets cannot express a path-scoped push exemption — a ruleset can only forbid all direct pushes to `main` or permit all of them for a bypass actor, never "these four paths only." The bypass actor here is the built-in Repository-admin role at `bypass_mode: "always"`, over every path equally, not just the four listed.
- **Not a local hook.** `hooks.pre_bash` in `.claude/framework.config.json` holds **23** hooks; none of them inspects the paths touched by a push resolving to `main` against this allowlist. The four that look adjacent — `validate_pr_review`, `validate_pr_ci_status`, `validate_branch_freshness`, `block_squash_wave_merge` — are all PR-shaped and never fire on a bare push.
- **Not CI.** CI runs `on: push` / `on: pull_request` after a change has already landed on `main` — it can observe, never prevent.

So **"a commit is exempt only if every path it touches is listed" is honour-system, not a checked precondition.** What `Bypassed rule violations` actually attests is only that the push bypassed the ruleset's `pull_request` rule — it says nothing about which paths were touched or whether every one of them was on the list.

**Owner ruling (2026-09-09, #1493).** The owner's verbatim word answering this question was **"ratified."** The reading that the current honour-system state is what's ratified — the allowlist stays honour-system, and no hook, CI check, or path rule is added on the strength of this ruling — is the *orchestrator's interpretation*, recorded separately from the owner's own word (`#1493` comments; `cross-repo-status.json`).

**This paragraph is documentation-only.** It states the honour-system status honestly; it does **not** close a tier-1 enforcement gap, because none is closed here — the gap is ratified, not fixed. The `pre_bash` hook design proposed in #1493 (block a push to `main` unless every touched path is allowlisted, failing closed on an unparseable range) remains a valid future option; it is simply not scheduled.

Emergency Mode's `[EMERGENCY]` direct path is unaffected.


Phase-3 end-state criterion #4 (`noorinalabs-main#322`): **CI failures block all merges** on every repo's default branch, org-wide — not just by team discipline, but enforced server-side by GitHub. As of W13, 7 of 8 repos (all child repos + `noorinalabs-main`) had NO branch protection and relied SOLELY on the Hook 4 comment-gate; that single-layer gap is what let the W11 batch-loop merge evade review (`feedback_batch_loop_merge_evades_pr_review_hook`). This section is the canonical spec that closes that gap; the live pilot proves it and the remaining repos adopt it per the application-status note (the spec, not a blanket apply, is the durable artifact).

This section is the **canonical ruleset spec** — the shape every repo's protection must take. It is the high-value deliverable of #322 because it resolves a real tension: GitHub's native "require approvals" counts formal reviews our team structurally cannot produce, so a naive protection rule would deadlock our merge flow. The spec below defines a shape that enforces protection *without* that deadlock.

### Application status

The spec, the hook-side admin-merge gate, and the live pilot landed in **W13** (`Refs #322`); the org-wide rollout to the remaining repos followed as the **W14 fast-follow**. **`#322` closed 2026-06-02T02:15:09Z** — criterion #4 is met: all 8 default branches carry a ruleset, per a read-only sweep of `gh api repos/noorinalabs/<repo>/rulesets` re-run on `#1464` (2026-09-10):

| Repo | Ruleset id | Enforcement |
|---|---|---|
| noorinalabs-main | `17139856` | active |
| noorinalabs-deploy | `17139848` | active |
| noorinalabs-data-acquisition | `17091263` | active |
| noorinalabs-user-service | `17139747` | active |
| noorinalabs-design-system | `17139787` | active |
| noorinalabs-landing-page | `17140822` | active |
| noorinalabs-isnad-ingest-platform | `17139757` | active |
| noorinalabs-isnad-graph | `17139768` (plus its pre-existing `14482071` deployments-branch rule) | active |

The remaining open work is the **push-side** gaps named on `#1464` (§ Two path-filtered repos below) — org-wide *rollout* is complete; org-wide *enforcement completeness* is not, and that distinction is the reason `#1464`, not `#322`, stays open.

**Pilot (W13, live):** the spec is proven live on **one** repo with no in-flight W13 PRs — `noorinalabs-data-acquisition` (ruleset id `17091263`): `~DEFAULT_BRANCH`, active, `pull_request` (0 reviews) + `required_status_checks` (strict; `Lint`, `Type Check`, `Test`, `Integration Tests`) + `deletion` + `non_fast_forward` + Repository-admin `always` bypass. Read-back-verified at origin. `noorinalabs-isnad-graph` already carried its own pre-existing protection and is untouched.

**Remaining 6 repos (historical — landed W14):** the apply was **mechanical re-creation from this spec** — `gh api -X POST repos/<repo>/rulesets --input <json>` per repo with the required-check contexts tabulated below, read-back-verified. All 6 landed during the W14 fast-follow (see the per-repo table above for current ids); this paragraph documents the apply method, not an open TODO.

### The ruleset shape (and why it's shaped this way)

The ruleset each repo adopts is a **repository ruleset** targeting `~DEFAULT_BRANCH`, `enforcement: active`, with (the pilot already carries it; the remaining repos adopt it per the application-status note above):

- a `pull_request` rule with **`required_approving_review_count: 0`**, and
- a `required_status_checks` rule (`strict_required_status_checks_policy: true`) listing that repo's **unconditional PR-gate check contexts**, and
- `deletion` + `non_fast_forward` protection, and
- a single `bypass_actors` entry: the built-in **Repository admin** role (`actor_id: 5`, `bypass_mode: always`).

The load-bearing design decision is **0 required approvals, not 1.** GitHub's "require approvals" counts **formal GitHub PR reviews** — which our team cannot produce: the `gh` auth principal IS the PR author (`parametrization`), so a formal self-approval 422s (`feedback_gh_cli_gotchas`), and our review discipline runs on **issue-comment verdicts** validated by Hook 4 (`validate_pr_review`), not formal reviews. A naive "require 1 approval" rule would therefore **deadlock every merge**. So the ruleset enforces only what it can enforce without breaking us — *a PR must exist* + *CI must be green* — and leaves reviewer-count enforcement to Hook 4, where the issue's own scope note ("Required-reviewer count beyond charter — already covered by `validate_pr_review`") puts it.

The **Repository-admin `always` bypass** is what keeps the established flow working: the orchestrator's `--admin` wave→main wrapup merges, the wave-bootstrap and doc-sweep single-reviewer exceptions, and Emergency-Mode restore merges all run as admin. The bypass is the GitHub-side counterpart to the hook-side exception list below — protection for everyone, an audited escape valve for the established exceptions.

**Naming convention (owner ruling, 2026-09-10, `#1464`):** every repo's ruleset was originally named `Protect main — require PR + green CI (P3 end-state #4, main#322)`. For the two path-filtered repos (`noorinalabs-main`, `noorinalabs-deploy` — see below), that name overclaimed: the ruleset itself enforces no CI-green condition on those two, since `required_status_checks` is omitted there by design. The owner ruled the name should be renamed to match the shape it actually enforces rather than the aspiration. `noorinalabs-main`'s ruleset (`17139856`) was renamed live on 2026-09-10T10:34:52-04:00 to `Protect main — require PR; CI green enforced by validate_pr_ci_status hook (P3 end-state #4, main#322, tracker #1464)` — read-back-verified: only `name` and `updated_at` changed, `rules`/`conditions`/`bypass_actors`/`enforcement` byte-identical to before — PR-only + no-force-push at the ruleset layer, CI-green enforced one layer down by the hook, named as such. `noorinalabs-deploy`'s matching rename (ruleset `17139848`, same stale name) is tracked as a follow-up in that repo's own PR, not this one.

### Two path-filtered repos require PR-before-merge only

`noorinalabs-main` and `noorinalabs-deploy` have **fully path-filtered CI** — every PR-triggered workflow carries a `paths:` filter, so a PR that doesn't touch those paths (e.g. a charter/docs-only PR) produces **zero check-runs**. GitHub treats a hard-required-but-never-reported check as perpetually pending → it would deadlock the majority of PRs in those two repos. The spec therefore assigns these two a **PR-before-merge + deletion/non-fast-forward** ruleset that does NOT hard-require status-check contexts. For these two, CI-green enforcement falls to the **`validate_pr_ci_status` hook** (which reads the live `statusCheckRollup` at `gh pr merge` time and blocks on red/pending — and, per `main#802`, on an **empty** rollup too when the repo has a covering `on.pull_request` workflow with no `paths:` filter, so an empty rollup is treated as an anomalous dropped-trigger, not green CI; a fully path-filtered repo with no such workflow keeps a warn-allow for the legitimate docs-only zero-check case) plus the admin-merge exception gate below. (Note: `noorinalabs-main`'s `commit-identity.yml` runs on every PR with no `paths:` filter, so in practice its PRs always report ≥1 check; a truly-empty rollup there is anomalous. See `state-claims.md` § Empty `statusCheckRollup` Is Hard Not-Ready for the readiness-claim discipline and the `.claude/lib/pr_ci_state.py` oracle.) The five remaining repos (data-acquisition, user-service, design-system, landing-page, ingest-platform) have unconditional PR CI, so the spec assigns them a ruleset that DOES hard-require their gate contexts. The per-repo required-check contexts the W14 rollout will apply:

| Repo | CI posture | Required check contexts (strict) |
|---|---|---|
| data-acquisition | unconditional PR CI | `Lint`, `Type Check`, `Test`, `Integration Tests` |
| user-service | unconditional PR CI | `check`, `openapi-snapshot-drift` |
| design-system | unconditional PR CI | `ci (20.x)`, `validate-package` |
| landing-page | unconditional PR CI | `Lint, Type Check & Build`, `E2E Tests (Playwright)` |
| ingest-platform | unconditional PR CI | `lint-and-typecheck`, `security-audit`, `test` |
| **noorinalabs-main** | path-filtered | (none — PR-before-merge only) |
| **noorinalabs-deploy** | path-filtered | (none — PR-before-merge only) |

(Contexts enumerated from each repo's default-branch check-runs at 2026-05-31; the rollout re-confirms them at apply time, since a repo's CI job names can change.)

**Known measurement gap (`#1464`):** "0 admin overrides per wave" (§ Admin-merge exception list, below) is measured for **merges** only (`gh_quota_gate`/gate-integrity audit counts `gh pr merge --admin` invocations) — a **push** that bypasses the ruleset (`Bypassed rule violations`, printed on any direct push to `main` by the admin-bypass role, including but not limited to the no-PR allowlist paths, § above) is counted by nothing. This is an unmeasured gap, not a fixed one; it is filed and tracked on `#1464`, not resolved by this PR.

### Admin-merge exception list (hook-validated)

`--admin` is no longer a silent bypass. `validate_pr_ci_status` blocks a `gh pr merge --admin` unless the operator declares a **charter-listed exception** via `ADMIN_MERGE_EXCEPTION="<class>:<rationale>"`. The `<rationale>` is required (non-empty) and **logged to the Annunaki audit trail** so each admin merge is reviewable at retro time (the issue's "auditable + reviewed at retro time" / "0 admin overrides per wave is a measured indicator"). The recognized classes:

| Class | Charter source |
|---|---|
| `wave-bootstrap` | § Single-Reviewer Exception (Wave-Bootstrap Only) |
| `doc-sweep` | § Trivial Cross-Repo Doc Sweep |
| `wave-merge` | the wave→main wrapup merge (orchestrator-merged) |
| `emergency` | `emergency-mode.md` § Allowed bypasses (`[EMERGENCY]`-prefixed) |

An absent or unrecognized exception **blocks** (fail-safe per `feedback_safety_direction_over_ux_friction`). Adding a class here requires adding the matching entry to `_CHARTER_ADMIN_EXCEPTIONS` in the hook — the two are kept in lockstep.

**Why:** criterion #4 closes the silent-bypass class directly via two complementary gates. The ruleset is the server-side gate (covers UI merges, external actors, the batch-loop-evasion class); the hook is the operator-side gate (covers `gh pr merge`, names the exceptions, writes the audit trail). Defense in depth — neither alone is sufficient, because the ruleset's admin bypass would otherwise be unaudited and the hook alone doesn't cover non-`gh`-CLI merges. The hook-side gate is **active now** (this PR); the server-side ruleset is **active on the pilot now** and rolls out org-wide in W14 per the rollout-status note above. Note the two gates are mutually reinforcing on the apply order: because the hook already requires `ADMIN_MERGE_EXCEPTION` for `--admin`, the W14 rollout can apply default-branch rulesets without the admin-bypass becoming an unaudited hole the moment it exists.

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

