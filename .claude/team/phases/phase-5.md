---
name: Phase 5 plan — real data, usable product
description: Phase definition, end-state criteria, exit gate, wave plan
phase: 5
status: exited
created: 2026-06-14
last_updated: 2026-06-20
exited: 2026-06-20
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

## Wave plan (proposed at /plan-phase 5, owner-approved 2026-06-14; revised 2026-06-14 after P5W2 light-up revealed criteria #1/#2 unmet)

| Wave | Theme | Scope summary | Serves |
|------|-------|---------------|--------|
| **W1** ✅ | **Data spine** | da#146 (keystone — segment isnad chains into narrator entities), da#147 (sect), da#148 (integrity sweep), da#144 (mis adapter). + TD intake. | #1 |
| **W2** ✅ | **API light-up** | ig#1024 (narrators 500 — fast Optional-fields unblock + real data behind it), ig#1025 (search 422), ig#1026 (subscriptions 404 + facet), ig#1023 (health 404), ig#1021 (auth refresh). TD intake folded in parser fixes main#659/#661 (governed by the #663 invariant). | #2 |
| **W3** ▶ | **Trustworthy data & search** | Data spine *depth* — segmentation still ~80% raw blobs (da#158 keystone, da#155/#154 NER, da#159 English names, da#157 edge-relation, da#160 parallels) + search/display (ig#1048 grades, ig#1049 semantic, ig#1050 isnad-filter, ig#1051 counts, ig#1032 chains, ig#1031 graph) + auth/session UX (ig#1027 modal, us#166 TTL→60m, deploy#449 carve-out) + alerting/ops (deploy#452 Slack, deploy#453 dead-man's switch, ig#1038/deploy#450/#451 log rotation). + TD intake (4/4). | #1, #2 |
| **W4** ✅ | **Admin surface + profile + streaming** | #603 admin surface (user mgmt, data-management panel, pipeline controls — ig#989/#988/#987), profile prefs (ig#1044/#1013 + us#165 JSONB), /compare UX (ig#1037), streaming repeatable (deploy#443 + ingest#76, Kafka E2E), admin-gated Grafana + Loki. Post-wrapup: the semantic re-embedding capstone (ig#1071 — real 384-dim model, verify-recall PASS **on staging**; prod deferred since prod is empty). + TD intake. | #3, #5 |
| **W5** (FINAL) | **Production cutover + phase exit** | #666/#602 production cutover — **prod data load + `deploy-prod` roll** (prod Neo4j is empty + compose predates the embed service: deploy#470), real data + product live on prod, solid auth/session UX; **landing-page pre-launch polish** (lp#138 fake staff + placeholder sweep); **corpus completeness** — Shia corpus (da#167) + sunni multi-source gap, per owner 2026-06-16; phase-exit verification of all 5 criteria. **Heavy tech-debt — +20% relaxed to a floor** (final wave). | #4 (+ #1/#2/#3/#5 verification) |

**Critical path:** da#158 (data-spine *depth*) is the live keystone — W1's da#146 segmentation runs but ~80% of production narrator nodes are still raw isnad-chain strings, so the API surface and graph explorer read blobs, not entities. W3 makes the data genuinely trustworthy (real entities, English names, grades, working search) before admin (W4) and prod cutover (W5).

Wave themes are confirmed (not re-chosen) at each `/wave-scope`; scope reconciliation may move issues between waves. **Revision note (2026-06-14):** W3 was originally "Admin + auth UX" but was re-themed to "Trustworthy data & search" after P5W2 revealed criteria #1/#2 are not actually met (data still blobs, search empty). Admin slid to W4; production cutover (criterion #4) to W6; a new W5 absorbed the owner-requested historical-events corpus. **Revision (2026-06-16, owner): Phase 5 WRAPS AT W5.** Admin completed in W4; **W5 becomes the FINAL wave** — production cutover (pulled forward from W6) + heavy TD cleanup (relaxed cap) + landing-page polish + phase-exit verification. The separate W6 is dropped. **Historical timeline & events** (#673, ig#1039–1043, da#161–166) and the deep data-quality epic are **deferred to Phase 6 (Data Quality / ML)**.

## Tech-debt intake (standing policy)

Every wave takes its **+20%** TD intake (`/wave-scope` Step 8.5) — `ceil(20% of feature/bug/security scope)`, all available if fewer. The pooled TD ratio is **informational only** (the cumulative-ratio gate was superseded 2026-06-09). P4W7 process follow-ups feed the W2/W3 intake: main#659 (CREATE-path parser), main#661 (validate_labels over-match), main#663 (parser-invariant charter/standards — owner-adopted), main#664 (validate_wave_audit exemption — owner-adopted).

On the **final wave (W5 — revised 2026-06-16, Phase 5 wraps at W5)** the +20% becomes a **floor, not a cap** (owner 2026-06-16): deliberately pull in a large chunk of debt to clean up before phase exit, sized by the owner at `/wave-scope`.

## Out of scope for P5 (deferred)

- **Billing/payments** (ig#717/#718) — needs product traction first.
- **CDN + performance ops**, **developer portal**, **notifications**, **visual-asset sourcing** — optimize after real traffic.
- **Playwright live-site automation** (main#56/#57), **Hetzner sizing** (main#142) — revisit when prod load is real.
- **Historical timeline & events** (#673, ig#1039–1043, da#161–166) — **Phase 7** or later (was the original W5; deferred at P5W5/prod-cutover 2026-06-16; advanced P6→P7 by the 2026-06-19 roadmap revision below).
- **Deep data-quality epic** (da date-extraction #161–166, integrity da#153, disambiguation da#139, coverage da#98) — the **Phase 7 (Data Quality / ML / demo)** nucleus: NER/entity-resolution accuracy, dedup, embedding quality at scale, a real model served **in prod**, validation/integrity gates, ML analysis to make data demo-ready.

**Roadmap revision (owner 2026-06-19):** a new **Phase 6 = Claude Efficiency** is inserted next (audit/interaction: tighten memories, bias toward code over `.md`/memories, revisit the persona model, explore Google LLM-doc format + graphify to potentially drop the ontology stack, and absorb tech-debt + Claude fixes incl. non-phase-tied). The former **Phase 6 (Data Quality / ML)** advances to **Phase 7** (serious ML + pipeline to make data demo-ready). `/plan-phase 6` then `/plan-phase 7` write the formal plan docs at kickoff. See memory `project_p5w5_prodcutover_p6_dataquality`.

## Phase exit gate

Owner runs `/phase-review 5` and verifies the **4 core end-state rows** are `Done` (#665, #602, #603, #666 closed), including the standing per-wave TD-intake compliance (criterion-6 model carried from P4 — every wave took its +20%). **#667 (streaming-pipeline-repeatable) was moved to Phase 7 by owner direction 2026-06-19** — streaming/pipeline work is centered there; the P5W5 cutover delivered real data on prod via the batch path, so streaming-repeatable is no longer a P5 exit row. On confirmation, `/plan-phase 6` defines the next phase before any P6 wave kicks off.

> **Note (2026-06-19):** prod **semantic search** also defers to Phase 7 ("a real model served in prod"). The P5W5 cutover put real data + the working product (keyword search / graph / app) live on prod; the prod re-embed is gated on promoting the embed image to a prod tag (`promote.yml` currently omits it) — see deploy#470. This is non-blocking for the 4 core P5 criteria.

### Exit gate — MET (owner-confirmed 2026-06-20, `/phase-review 5`)

All 4 core end-state trackers closed:

| # | Criterion | Tracker | Outcome |
|---|-----------|---------|---------|
| 1 | Data real & queryable | #665 ✅ CLOSED | Cutover intent met (real corpus live, chains segmented); queryability/quality (sanadset orphans, sparse linkage) → **P7 #723** |
| 2 | Product API functional on prod | #602 ✅ CLOSED | Timeline/graph live; **search correctness → P7** (ig#1110) |
| 3 | Admin surface complete | #603 ✅ CLOSED | **Fully met** — validated working on prod, no carry-forward |
| 4 | Production cutover + auth/session UX | #666 ✅ CLOSED | Cutover done (staging→prod, green); auth deep-link (ig#1111) + data-quality → **P7** |

**#667** (streaming-repeatable) carried to **Phase 7** (already `phase-7`-labeled; #601 met via batch path). **#692** (P5W5 wave meta) closed at wrapup.

Phase 5 closed on the **cutover bar** — real data + working product live on prod — with the explicit honest carry of **queryability/search/data-quality to Phase 7** (meta #723). The owner accepted the cutover-vs-queryability split at `/phase-review` rather than holding the phase open. Next: `/plan-phase 6` (Claude Efficiency), then `/plan-phase 7` (Data Quality / ML).

## References

- `.claude/team/lifecycle.md` — canonical phase/wave/session skill order
- `.claude/team/phases/phase-4.md` — prior phase (EXITED 2026-06-14; #602/#603 carried here)
- `cross-repo-status.json` — live counters (`phase_5_*` keys)
- P4W7 retro (`feedback_log.md`) — bug-bash provenance + the convergent parser-class follow-ups
