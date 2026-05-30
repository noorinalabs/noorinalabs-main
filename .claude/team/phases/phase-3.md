---
name: Phase 3 plan — fix our tools, fix our deployment
description: Phase definition, end-state criteria, exit gate, wave history
phase: 3
status: active
created: 2026-04-30
last_updated: 2026-05-30
---

# Phase 3 — fix our tools, fix our deployment

## Theme

Phase 3 runs two tracks simultaneously:

1. **Fix our tools** — leave the tooling/process meta-loop. Disambiguate ownership between meta repo and child repos. Bring CI parity and pre-commit/pre-push parity to every repo. Cover all committed artifacts (code, tests, `.claude/`, docs) with the same checks.
2. **Fix our deployment** — get staging and production live and continuously deployed. Wave wrap-ups gate on a successful staging promotion. Smoke tests run automatically post-deploy.

Both tracks must move together. Finishing only one is not phase exit.

## End-state criteria — Phase 3 exits when ALL hold

| # | Criterion | Tracker |
|---|-----------|---------|
| 1 | Live, working **staging** environment — continuous, not one-shot | noorinalabs-main#323 |
| 2 | Live, working **production** environment | noorinalabs-main#324 |
| 3 | `/wave-wrapup` requires successful **stg promotion** as wave-completion criterion | noorinalabs-main#325 |
| 4 | **CI failures block all merges** (no merging on red; no admin overrides except per charter exceptions) | noorinalabs-main#322 |
| 5 | **All committed artifacts pass all checks** — code, tests, `.claude/`, docs alike | noorinalabs-main#326 |
| 6 | **Pre-commit + pre-push hooks in every repo, mirroring GitHub Actions checks** — local catches what CI catches | noorinalabs-main#327 |
| 7 | **Hook/skill/charter ownership disambiguated** between meta repo and child repos — which artifacts live where, which execute where, who owns what | noorinalabs-main#328 |
| 8 | **Post-deploy smoke tests (UI + API)** running automatically on stg and prod after every promotion | noorinalabs-main#329 |
| 9 | **Tech-debt + tooling issues = <10% of new AND <10% of cumulative open** — both metrics must hold | noorinalabs-main#330 |

## Out of scope for P3

- New product features beyond what's needed to validate stg/prod liveness
- Migration to new infrastructure providers
- Adoption of new languages/frameworks beyond current stack
- Bot-driven moderation, search ranking changes, or other non-foundational features

## Wave themes — chosen, not assumed

- Each wave's theme is **set by the owner** at `/wave-scope` time via dialogue. The skill blocks until a theme is recorded.
- `/phase-review` runs **before** `/wave-scope` to surface what's done, what remains, and what's blocked — so theme picking is informed, not reactive.
- Cross-phase review happens via `/roadmap` (mandatory before any phase transition).

## Phase exit gate

Owner runs `/phase-review` and verifies all 9 end-state rows are `Done`, plus the tech-debt ratio test (criterion 9) holds. On confirmation, owner runs `/roadmap` to define Phase 4 before any P4 wave can kick off.

## Phase history — P3W1 to P3W9

| Wave | Theme | Outcome |
|------|-------|---------|
| W1 | Foundation — phase init, label scaffolding | Closed; few artifacts |
| W2 | Emergency-mode incident → charter sub-doc | Reactive; emergency-mode codified |
| W3 | Post-emergency stabilization + frontend-API absolute-URLs phase 2 | 14 PRs + 5 wave-merges |
| W4 | Tooling+process cleanup (31 issues, 6 repos) | 14 PRs, 0 admin overrides |
| W5 | Multi-repo fan-out + memory classification + skill self-improvement | 11 PRs, 0 admin overrides |
| W6 | Cross-repo backlog triage (Tier-1 across 8 repos + runbook fan-out) | 11 PRs, 0 admin overrides, top-concentration 18% |
| W7 | Hook parser-fixture coverage backport audit | 12 PRs, 0 admin overrides |
| W8 | Foundation reset — hook/skill/charter ownership disambiguation + artifact-CI scope definition | 11 PRs, 0 admin overrides, 0 ChangesRequested cycles |
| W9 | Tech-debt reduction (main-only) | 6 PRs, 0 admin overrides, 0 CR cycles, 67% concentration (Aino 4/6 by commit identity) |
| W10 | Tech-debt reduction (non-deploy remainder, 6 child repos + main) | 11 PRs across 5 repos (main 4, user-service 2, design-system 2, data-acquisition 2, landing-page 1); 0 admin overrides; retro adopted 3/4 process proposals (charter PR #444, Hook 21 #446) |
| W11 | Tech debt & deployment (deploy entirety + main retro/audit follow-ups) | 86 PRs to wave-11 (deploy 46, main 16, isnad-graph 10, ingest 8, user-service 3, design-system 3); 16 ChangesRequested cycles; top-concentration 15% (Lucas, 13 PRs); deploy#348 close-out + #523/#524 coordination; **prod canonical-redirect LIVE** (.net/.org → .com); 3 charter changes adopted (close-on-verified-live, provider-validated apply-time acceptance, cwd-anchor fix epic) |
| W12 | Tech-debt sweep + cross-cutting security/CI | 15 PRs (main 4, deploy 11); **0 ChangesRequested cycles** (cleanest in P3 history); 27% top-concentration (Lucas + Weronika tied at 4 each); plus 5 cross-cutting direct-to-main PRs (isnad-graph #933 starlette security, #930 node24, deploy #369/#370 vhost carve-out, main #538 hook fix); tier-1 #164 SSH key split (supersedes ADR 0003); node24 sweep complete across 5 repos (June 2 deadline met); 3 charter changes proposed (throttle-stall detection, hook test coverage, meta-issue freshness) — issues #542/#543/#544 |

12 of 12 waves were tooling/meta-loop (W3 had a small frontend feature; W11 shipped substantive deploy infrastructure — ADRs 0003/0004/0005, env restructure, SSH key split, cloud-init parity, backblaze bootstrap — but live-staging/production operational verification still unstarted). This is the gap that drove the 2026-05-08 phase reset and shapes W11 (deploy entirety), and re-surfaces at 2026-05-30 /phase-review as a still-open trajectory question (see § Trajectory reality check).

## Wave plan addendum — 2026-05-12 owner partition directive

After W9 wrapped main-only (6 PRs Aino-concentrated by theme-fit), the
remaining 115 W9-labeled issues were partitioned by owner directive
2026-05-12T22:30Z:

- **W10 = non-deploy remainder** — 54 issues across 5 child repos (isnad-graph 27,
  user-service 12, landing-page 9, design-system 3, data-acquisition 3) + 8 main
  issues (#402/#403/#255 carry-forwards + #262 promoted from W9 + #417/#418/#419
  audit follow-ups + #421 this issue).
- **W11 = deploy entirety** — 60 deploy issues + deploy#285 (sender-side
  asymmetric dispatch contract from #413 review). Single-repo wave.

Theme directive for W10: tech-debt reduction continues. Phase-3 exit
criterion #9 (`<10% tech-debt ratio`) is NOT softened — additional sweep
wave(s) may be added after W11 if math still doesn't close.

Stored mirror: `cross-repo-status.json` § `wave_9_decisions.partition_directive_2026_05_12`.

## Sweep-wave reservation (W12, possibly W13) — 2026-05-13 owner directive

Pre-W10 `/phase-review` math (2026-05-13) projected post-W11 ~30% TD
ratio; pre-W11 actuals (2026-05-17) confirm the trajectory but TD reduction
is happening slightly faster than projected — W10 closed 61 issues (vs the
projection's 61) but the open-TD count dropped from 133 → 98 because retro
+ audit follow-ups also closed obsolete TD outside the scope.

| State | Open total (8 repos) | Open TD | TD ratio | vs <10% gate |
|-------|---------------------|---------|----------|-------------|
| Pre-W10 (2026-05-13 projection) | 198 | 133 | 67% | far over |
| Pre-W11 (2026-05-17 actual) | 166 | 98 | **59%** | far over |
| Post-W11 (2026-05-24 actual) | 93 | 34 | **37%** | far over |
| Post-W12 (2026-05-30 actual) | 88 | 30 | **34.1%** | over (3.4× gate) |
| New-filed phase-to-date (2026-05-30) | 311 | 261 | **83.9%** | catastrophically over (criterion #9 second axis) |
| Target | — | — | <10% (both axes) | — |

Even with W11 perfectly themed at tech-debt reduction (117 issues in scope,
of which ~85 are TD), post-W11 projected ratio is ~20% — still 2× the
criterion #9 gate. Owner directive 2026-05-13: **W12 (and W13 if needed)
is reserved as a tech-debt sweep wave** to bring the cumulative-open ratio
under 10%. The sweep reservation remains warranted at the pre-W11 actuals.

Sweep-wave themes are intentionally NOT pre-committed — the exact scope
depends on the residual surface at /phase-review pre-W12. Likely contents:

- Remaining tech-debt items not absorbed by the W10/W11 fix-what-fits passes
- Tooling/process-cleanup tickets that block the deploy track
- Cross-repo audit follow-ups surfaced during W10/W11 retros

Phase exit gate (all 9 criteria done AND TD ratio <10% on both counters)
will be re-evaluated at /phase-review pre-W12 and again pre-W13. Phase 3
exits when both gates close, not before — owner directive: no softening.

Stored mirror: `cross-repo-status.json` § `phase_3_sweep_wave_reservation_2026_05_13`
(to be written by next `/wave-wrapup` or set explicitly via upsert helper).

## Trajectory reality check — 2026-05-30 (post-W12 /phase-review)

Math doesn't close on the timeline-as-implied. Post-W12 actuals + the new-filed-this-phase axis surface three gaps:

- **Cumulative TD ratio after 2 explicit sweep waves (W11+W12): 34.1%.** Sweep waves closed substantial issues but the rate is ~5pp per wave (W11: 59%→37%; W12: 37%→34.1%). At ~5pp/wave, reaching <10% requires ~5 more sweep waves.
- **New-filed phase-to-date TD ratio: 83.9% (261/311).** Criterion #9 has TWO axes, both must be <10%. The new-filed axis cannot be retroactively fixed — fixing it requires the volume of NEW issues filed during P3 to taper off, which only happens after the meta-loop work tapers. Meta-loop tapers when the deploy track ships + product surface re-opens.
- **Deploy track operational verification unstarted.** Criteria #1 (live staging), #2 (live production), #3 (wrapup gates on stg), #8 (post-deploy smoke tests) are all OPEN. W11 shipped substantive deploy *infrastructure* (ADRs, terraform, SSH, cloud-init, env restructure, backblaze bootstrap) — but staging + production live verification on prod hostnames is operational work that hasn't started.
- **4 criteria substantively done but untracked-as-closed:** #4 (CI failures block merges — W11 #432 landed branch protection across 8 repos); #5 (artifacts pass checks — W7/W8/W11 hooks-lint/CI); #6 (pre-commit + pre-push hooks — partial, needs cross-repo audit); #7 (hook/skill/charter ownership disambiguated — W8 foundation reset). Verification + explicit close pass would move 3-4 criteria from OPEN → DONE.

### Two-track tension

The phase plan says: "Both tracks must move together. Finishing only one is not phase exit." But 12 waves in:
- **Tools track**: substantively complete (charter/hooks/skills/tooling). Residual is TD-labeled cleanups + W13's 3 charter changes (#542/#543/#544).
- **Deploy track**: infrastructure substantively done. Live-stg + live-prod operational verification not started. Smoke tests blocked on stg/prod.

The implicit "both tracks move together" rule has been violated in every wave so far (tools moved, deploy operational didn't). Either the rule isn't load-bearing in practice (and should be relaxed), or W13+ must include explicit deploy-track operational work.

## Proposed spec revisions — owner-pending 2026-05-30

Three concrete proposals. Owner ratifies, modifies, or rejects each; PR landing approval enacts them.

### Proposal A — Criterion #9 reality-check: relax cumulative gate; reshape new-filed axis

**Current**: `<10% of new AND <10% of cumulative open`
**Proposed**: `<20% of cumulative open` as the hard phase-exit gate, AND `new-filed ratio trending DOWN month-over-month` as the directional axis (rather than fixed <10%).

**Rationale**: At ~5pp/sweep-wave reduction, hitting <10% cumulative requires ~5 more sweep waves — another 6-10 weeks of pure-TD waves while deploy track stays unstarted, deepening the two-track gap. <20% is achievable in W13+W14 with realistic effort. The new-filed axis at 83.9% reflects the phase's meta-loop nature — fixing it requires the meta-loop work to taper, which is the actual exit signal, not a fixed percentage.

**Owner-explicit "no softening" stance (2026-05-13)** acknowledged. This proposal asks whether that stance is still load-bearing 2.5 weeks later given post-W12 actuals.

### Proposal B — Two-track move-together: codify deploy-track-alongside requirement from W13+

**Current**: "Both tracks must move together. Finishing only one is not phase exit."
**Proposed addition**: "From W13 onward, every wave MUST include at least one deploy-track operational item (criteria #1/#2/#3/#8 — substantive operational progress, not infra-only) UNLESS the wave is themed `verification-and-close-sweep` (move OPEN-but-substantively-done criteria to DONE)."

**Rationale**: W13 as locked-by-owner is TD reduction for us/deploy/ingest-platform. Encoding deploy-track-alongside means W13 picks up one deploy-track operational item *in addition to* the TD sweep — or is themed verification-and-close-sweep. If neither is acceptable, the "both tracks move together" line is functionally dead and should be removed.

### Proposal C — Verification-and-close sweep (possibly W13 stretch, or W14)

**Action**: Spawn an audit pass (Aino-class) walking #322 / #326 / #327 / #328 declaring each:
- **Done** — close the tracking issue with summary comment of the work that closed it
- **Mostly done, X remaining** — keep open with explicit residual scope
- **Open, no progress** — keep open as-is

**Rationale**: 4 criteria appear substantively done but tracked-open. Closing 3 of 9 in a half-day audit pass would move the visible-criterion-count from 0/9 to 3/9 immediately — more honest representation of P3 progress than the current "all 9 open" surface.

Could fold into W13 as a stretch task or be a dedicated mini-wave (W13.5 or W14).

---

## Open questions

- `/roadmap` skill build — scope for which wave?
- Phase-4 spec definition — does P4 happen after P3 fully exits (slow), or after a partial-exit pivot (faster, requires Proposal A acceptance)?

## References

- `cross-repo-status.json` — live counters (`wave_*_scope`, `phase_3_carry_forwards`)
- `.claude/team/charter.md` — eternal team rules
- `.claude/skills/phase-review/SKILL.md` — phase track-check (mandatory pre-`/wave-scope`)
- `.claude/skills/wave-scope/SKILL.md` — wave reconciliation (theme required)
- Memory: `project_post_w3_multirepo_planning.md` — owner directive (2026-05-03) to fold child-repo backlogs into multi-repo waves
