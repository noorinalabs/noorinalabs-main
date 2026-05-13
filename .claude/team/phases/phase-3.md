---
name: Phase 3 plan — fix our tools, fix our deployment
description: Phase definition, end-state criteria, exit gate, wave history
phase: 3
status: active
created: 2026-04-30
last_updated: 2026-05-10
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

9 of 9 waves were tooling/meta (W3 had a small frontend feature; no deploy work shipped yet). This is the gap that drove the 2026-05-08 phase reset and shapes W9 scoping.

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

## Open questions

- `/roadmap` skill build — scope for which wave?

## References

- `cross-repo-status.json` — live counters (`wave_*_scope`, `phase_3_carry_forwards`)
- `.claude/team/charter.md` — eternal team rules
- `.claude/skills/phase-review/SKILL.md` — phase track-check (mandatory pre-`/wave-scope`)
- `.claude/skills/wave-scope/SKILL.md` — wave reconciliation (theme required)
- Memory: `project_post_w3_multirepo_planning.md` — owner directive (2026-05-03) to fold child-repo backlogs into multi-repo waves
