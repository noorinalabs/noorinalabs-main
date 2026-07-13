# Pull Requests — Acceptance Scope

> Part of the [pull-requests charter index](../pull-requests.md) — re-shelved from `charter/pull-requests.md` for section-level loading (#963). Rules unchanged.

## PR-Time Acceptance vs Runtime Acceptance (Mandatory) <!-- promotion-target: none -->

When a fix lands a PR for an issue that ALSO has a runtime gate (e.g., "one successful end-to-end backup before DNS-flip", "first deploy succeeds without manual intervention", "CI green on first run after credential rotation"), distinguish the two lifecycle positions:

- **PR-acceptance criteria** — code-correctness, unit-mechanic correctness, hardening, scoped local validation. Reviewable in PR comments. Lives in PR review scope.
- **Runtime-acceptance criteria** — operational events firing on real infrastructure that may not exist yet. Lives in cutover / runbook / operational scope. Verified post-merge in production-event flow.

### Failure modes if conflated

1. **Blocks PR on infrastructure that doesn't exist yet** — e.g., demanding "B2 object key proof of successful upload" from a PR fixing the backup unit, when the new prod box hasn't been provisioned and there's no compose stack to back up. The PR then either waits indefinitely OR is blocked by an irrelevant external dependency.
2. **Forces synthetic-evidence fakery** — implementer fabricates fake "proof" (stub creds, mock invocations) to satisfy reviewer demand for evidence that can't legitimately exist yet. Worse than no proof: it masks the real runtime gate when it fires.

### How to apply

- When scoping a PR for an issue that has a runtime gate, write the PR's Test Plan as **two sections**:
  1. **Pre-merge validation** (PR-acceptance) — what the reviewer can verify from the diff + CI + author's local validation.
  2. **Post-merge validation** (runtime-acceptance) — what fires after merge in production flow, NOT required for merge.
- If a reviewer asks for runtime evidence in PR review, push back: "that gate fires at lifecycle position X (e.g., post-compose-up on new TF-prod box); cannot legitimately exist at PR-review time. Documented in post-merge Test Plan section."
- If a runtime gate is a genuine wave-acceptance criterion, file a SEPARATE issue tracking the runtime gate (not the code fix). The code fix's PR closes its own issue; the runtime gate's issue closes on its own runtime-event trigger.

### Provider-validated expressions are apply-time acceptance (added P3W11 retro 2026-05-24)

Some IaC providers validate field values only at **apply**, not at plan. Cloudflare Ruleset `target_url` / filter (wirefilter) expressions are the canonical case: `terraform plan` shows a clean diff for a syntactically-malformed expression, and the provider rejects it only when `apply` calls the API. Therefore **a green plan + a clean two-reviewer pass cannot certify expression correctness** — the apply is the validation gate.

- For PRs touching provider-validated expressions, the reviewer's Approved verdict certifies code/diff/plan correctness ONLY; expression validity is an explicit **post-merge, apply-time** acceptance line in the Test Plan.
- Where feasible, add a pre-apply check (a CI step exercising the expression against the provider's validation endpoint, or a documented `terraform apply` in a non-prod scope) so the failure surfaces before the prod apply.
- Do not claim "verified" on a clean plan alone for these fields.
- Worked example: `noorinalabs-deploy#349` (P3W11) passed plan + two reviews but failed at apply — `target_url` used `if()`/`len()`, unsupported in CF's redirect expression language ("unknown identifier", apply-time only). Fixed in #350.

### Adjacent to layer-separation

This is the **lifecycle-separation** companion to the **layer-separation** discipline encoded by the multi-layer-gap-filing memory: both are about respecting boundaries when scoping work. Multi-layer says "different layers of one root cause = separate issues." This says "different lifecycle positions of one acceptance criterion = separate scope (PR vs runtime), not bundled."

### Severity if violated

- Reviewer demands runtime evidence in PR scope and implementer concedes by fabricating synthetic proof: **moderate** (synthetic substitute masks the real gate when it fires).
- Implementer bundles runtime-acceptance criteria into PR-acceptance Test Plan, blocking merge on infrastructure that doesn't exist: **minor**, **moderate** if it blocks a wave.
- Reviewer correctly distinguishes and pushes back on conflation: positive feedback event.

### Worked example

`noorinalabs-deploy#121` / PR #187, 2026-04-28. The PR fixed `isnad-backup.{service,timer}` (3 + 2 stacked bugs). `noorinalabs-main#212` cutover-gate required "one successful end-to-end backup within 24h of first compose-up before DNS-flip." Aisha's spawn brief asked for "B2 object key proving end-to-end success" as PR evidence. Aisha correctly DEFERRED that evidence to post-compose-up runtime, documented what she CANNOT validate (no docker-compose stack on stg = `docker compose ps` preflight refuses to proceed = no B2 path reached), shipped unit-mechanic correctness, and added an explicit post-merge Test Plan step for the runtime gate. Bereket endorsed the deferral as canonical: "fix landing now, gate firing later" is the right shape.

## Close Runtime-Gated Issues on Verified-Live, Not on Merge (Mandatory) <!-- promotion-target: none -->

When an issue's real acceptance is a **gated production apply or live behavior** (the runtime-acceptance half of the section above), the PR that implements it MUST reference the issue with `Refs #N`, NOT `Closes #N`. The orchestrator closes the issue manually **after** the post-merge apply succeeds and the live behavior is verified.

### Why

`Closes #N` fires on default-branch merge — which is BEFORE the gated apply runs (the apply is a separate, environment-approval-gated push-to-main run). Merge ≠ live. An auto-close on merge produces a closed-but-not-done issue when the apply then fails or is still pending approval.

### How to apply

- PR body uses `Refs #N` for runtime-gated issues; `Closes #N` is reserved for issues whose acceptance is fully satisfied at merge (code/CI).
- After merge → gated apply → live verification, the orchestrator closes #N with the apply result + live-verification evidence (e.g. apply summary + `curl -sI` output) in the close comment.

### Severity if violated

- `Closes #N` on a runtime-gated issue auto-closes it on merge before the apply runs: **minor** if caught and reopened same-session; **moderate** if it ships a closed-but-broken issue into the backlog.

### Worked example

`noorinalabs-deploy#348`, 2026-05-24. PR #349 merged with "Closes #348" → #348 auto-closed on merge, but the prod apply then FAILED (apply-time CF expression rejection). Had to reopen #348. The fix PR #350 used "Refs #348"; #348 was closed only after the apply succeeded (`0 added / 2 changed / 0 destroyed`) and `curl` confirmed live 301s on `.net`/`.org`.

<!-- Promoted from memory: feedback_cf_plan_not_validate_expr_and_close_on_verified_live.md (P3W11 retro, 2026-05-24) -->

<!-- Promoted from memory: feedback_origin_over_local_for_still_has_claims.md (P3W9 #346 memory audit, 2026-05-10) -->

## Security Guards Belong Inline, Not in a Followup (Mandatory) <!-- promotion-target: skill -->

When reviewing a PR whose security model depends on a runtime guard — env check, scheme restriction (`{http,https}` whitelist), HTTPS-required-outside-test, startup assertion, URL rewriter, auth bypass flag — the guard MUST ship in the same PR. Filing a TechDebt followup issue is a legitimate review artifact (paper trail in case the guard ever regresses), but it is **not a substitute** for the inline guard.

### Reviewer protocol

When the threat model requires a runtime guard:

1. **Post `Changes Requested`**, even if a followup issue exists for the guard.
2. **File the followup BEFORE posting the review comment** so the comment can cite `TechDebt: #N` cleanly.
3. **Frame the ask as:** "Resolve inline; close the followup with the fixup SHA referenced from this PR." The followup is a tracking artifact, not a fix.
4. **Approve only after** the inline guard lands. Acceptable shapes for the guard: env-gate that refuses-to-boot in prod, scheme whitelist, HTTPS-required-outside-test assertion, startup-time check that fails fast, URL-rewriter input validation.

### What this rule applies to

- Environment gates (prod/staging refuse-to-boot under override paths)
- Scheme whitelists (`{http,https}` restrictions on user-controlled URLs)
- HTTPS-required-outside-test assertions
- Startup-time security assertions (boot fails if config is unsafe)
- URL rewriters / proxy redirects (input validation)
- Auth bypass flags (e.g., `OAUTH_PROVIDER_BASE_URL_OVERRIDE`-class knobs)

Docstring warnings, code-comment cautions, and "remember to set X in prod" notes are NEVER sufficient for these.

### What this rule does NOT apply to

- Defense-in-depth hardening that doesn't change the threat surface
- Log-level tuning, observability additions
- Doc updates that describe existing behavior
- Refactors that preserve threat model

These are legitimate followups when the inline change is already safe.

### Severity if violated

- Reviewer Approves a PR with a deferred runtime guard, no inline safeguard: **severe** (silent regression window between merge and followup-fixup).
- Implementer ships a knob without the guard, even if a followup is filed: **moderate** (the followup is paperwork; the threat surface is open until the guard lands).

### Worked example

`noorinalabs-user-service#77` (`OAUTH_PROVIDER_BASE_URL_OVERRIDE`, 2026-04-21). Reviewer filed followup #78 proposing a prod-environment guard + HTTPS-outside-test requirement, and posted `Changes Requested`. Mateo landed both inline in fixup `1104104`; #78 closed same day. Team-lead's verdict: "shipping the env-gate + HTTPS requirement inline rather than deferring to #78 was the right call." Deferring would have left a window where a prod misconfig could exfil `client_secret` via `/token` POSTs with no backstop.

<!-- Promoted from memory: feedback_live_trace_over_synthetic_acceptance.md (P3W9 #346 memory audit, 2026-05-10) -->

## Design-Rationale Block for Critical-Path PRs (Mandatory) <!-- promotion-target: skill -->

PRs that touch critical-path workflow DAGs, observability stacks, or alert-rule definitions MUST include a design-rationale block at the load-bearing decision point.

### When this requirement applies

- PRs touching `.github/workflows/promote.yml`, `deploy-stg.yml`, `deploy-prod.yml`, or any other workflow whose failure-mode propagates to prod gates.
- PRs touching `infra/prometheus/alerts.yml`, `infra/prometheus/prometheus.yml`, blackbox/textfile-exporter configs, or any other observability artifact whose silence vs. firing has operator consequence.
- PRs introducing a new gate, predicate, or DAG ordering whose correctness depends on a specific multi-path outcome matrix.

### What the block must contain

- Either an inline file comment at the gate/predicate/decision point (preferred when the rationale binds to a specific code site), OR a section in the PR body labeled `Design rationale` / `Outcome matrix` / `Sequencing rationale`.
- A walk of the predicate algebra OR an outcome truth table OR a design-rationale-vs-alternatives comparison — whichever load-bears the decision.
- Citations to the issue body's spec (or a `Reality post-#N` mapping if the spec has drifted from current state).

### Worked examples (Phase 3 Wave 1)

- `noorinalabs-deploy#198` lines 232-258 — gate-stg-verify rationale block walking three failure modes (missing artifact, stale artifact, schema-version mismatch).
- `noorinalabs-deploy#201` PR body — 5-path retag-gate truth table (success/skipped/failure crosses + break-glass).
- `noorinalabs-deploy#208` `infra/blackbox-exporter/blackbox.yml` — load-bearing assertion comments per module.
- `noorinalabs-deploy#210` `infra/prometheus/alerts.yml` — dual-alert design comment (Failure vs Stale split rationale).

### Reviewer enforcement

Absence of a design-rationale block on an applicable PR is grounds for Changes-Requested. The block's quality (rather than its mere presence) is what reviewers should engage with.

### Severity if violated

Minor — but recurrence is moderate. The discipline is high-leverage for incident-response readability and retro-evidence quality; both pay dividends across multiple waves.

### Why

Phase 3 Wave 1 produced 4 corroborating data points (above) where the design-rationale block earned positive reviewer engagement, surfaced design alternatives during review, and provided the canonical retro evidence later. Without it, gate-DAG correctness is invisible to anyone reading the PR after merge.

<!-- Promoted from memory: feedback_review_against_artifact_not_framing.md (P3W5 retro 2026-05-06; reviewer-side). The implementer-side data points (#161, #206 Reality-post-#87) predate the dedicated memory and were the original founding examples; the memory codified the reviewer-side counterpart, which this section now incorporates. -->

