---
name: Phase 5 plan — real data, usable product
description: Phase definition, end-state criteria, exit gate, wave plan
phase: 5
status: active
created: 2026-06-14
last_updated: 2026-06-14
---

# Phase 5 — real data, usable product

## Theme

Phase 4 proved the pipeline runs and lit up **staging** with a real narrator graph (criterion #1, main#601). But the P4W7 live bug-bash (ig#1018) found the product **loaded-but-non-functional**: 67% of narrators are un-segmented isnad-chain strings (NER never split them), the narrators API 500s, full-text search 422s, and several endpoints 404. The data is *present* but not *real* (queryable entities), and the surface that reads it is broken.

Phase 5 finishes the job Phase 4 started: make the real data **actually usable**, complete the **admin surface**, and **cut over to production** — closing the two P4 criteria (#602/#603) that were deliberately carried forward at the W5 exit-drive.

Owner directive (carried): **data-first** — get real, queryable data visible in the product before broader features/polish.

## End-state criteria — Phase 5 exits when ALL hold

| # | Criterion | Tracker | Anchors |
|---|-----------|---------|---------|
| 1 | **Data is real & queryable** — isnad chains segmented into narrator entities; sect/integrity correct | noorinalabs-main#665 | da#146 (spine), da#147, da#148, da#144 |
| 2 | **Product API surface functional** — narrators/search/subscriptions return 200 with real results; search/timeline/graph usable | noorinalabs-main#602 | ig#1024 (spine), ig#1025, ig#1026, ig#1023, ig#1021 |
| 3 | **Admin surface complete** — user mgmt, data-management panel, pipeline controls | noorinalabs-main#603 | (admin cluster — scoped at /wave-scope) |
| 4 | **Production cutover** — real data + working product on production, solid auth/session UX | noorinalabs-main#666 | #602 (prod half), ig#1027 |
| 5 | **Streaming pipeline repeatable** — Kafka E2E + one-click bring-up | noorinalabs-main#667 | deploy#443 (+ Kafka-E2E work issue) |

## Wave plan (proposed at /plan-phase 5, owner-approved 2026-06-14)

| Wave | Theme | Scope summary | Serves |
|------|-------|---------------|--------|
| **W1** | **Data spine** | da#146 (keystone — segment isnad chains into narrator entities), da#147 (sect), da#148 (integrity sweep), da#144 (mis adapter). + TD intake. | #1 |
| **W2** | **API light-up** | ig#1024 (narrators 500 — fast Optional-fields unblock + real data behind it), ig#1025 (search 422), ig#1026 (subscriptions 404 + facet), ig#1023 (health 404), ig#1021 (auth refresh). TD intake folds in the parser fixes main#659/#661 (governed by the #663 invariant). | #2 |
| **W3** | **Admin + auth UX** | #603 admin surface (user mgmt, data-management panel, pipeline controls), ig#1027 session-expiry UX. + TD intake. | #3 |
| **W4** | **Production cutover + streaming** | #602 production cutover (real data + product live on prod), deploy#443 one-click bring-up, Kafka streaming E2E, prod data load, phase-exit verification. + TD intake. | #4, #5 |

**Critical path:** da#146 (data spine) is the keystone — it turns chain strings into narrator entities, which makes the API surface and graph explorer *meaningful*. ig#1024's narrators-500 has a fast option-1 fix (Optional response-model fields) that unblocks the surface in W2 independently of da#146, while da#146 makes the data behind it real.

Wave themes are confirmed (not re-chosen) at each `/wave-scope`; scope reconciliation may move issues between waves.

## Tech-debt intake (standing policy)

Every wave takes its **+20%** TD intake (`/wave-scope` Step 8.5) — `ceil(20% of feature/bug/security scope)`, all available if fewer. The pooled TD ratio is **informational only** (the cumulative-ratio gate was superseded 2026-06-09). P4W7 process follow-ups feed the W2/W3 intake: main#659 (CREATE-path parser), main#661 (validate_labels over-match), main#663 (parser-invariant charter/standards — owner-adopted), main#664 (validate_wave_audit exemption — owner-adopted).

## Out of scope for P5 (deferred)

- **Billing/payments** (ig#717/#718) — needs product traction first.
- **CDN + performance ops**, **developer portal**, **notifications**, **visual-asset sourcing** — optimize after real traffic.
- **Playwright live-site automation** (main#56/#57), **Hetzner sizing** (main#142) — revisit when prod load is real.

## Phase exit gate

Owner runs `/phase-review 5` and verifies all 5 end-state rows are `Done` (#665, #602, #603, #666, #667 closed), including the standing per-wave TD-intake compliance (criterion-6 model carried from P4 — every wave took its +20%). On confirmation, `/plan-phase 6` defines the next phase before any P6 wave kicks off.

## References

- `.claude/team/lifecycle.md` — canonical phase/wave/session skill order
- `.claude/team/phases/phase-4.md` — prior phase (EXITED 2026-06-14; #602/#603 carried here)
- `cross-repo-status.json` — live counters (`phase_5_*` keys)
- P4W7 retro (`feedback_log.md`) — bug-bash provenance + the convergent parser-class follow-ups
