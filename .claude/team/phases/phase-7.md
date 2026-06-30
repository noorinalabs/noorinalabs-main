---
name: Phase 7 plan — Production Readiness (Data Quality + Platform Hardening)
description: Phase definition, end-state criteria, exit gate, wave plan
phase: 7
status: active
created: 2026-06-25
last_updated: 2026-06-30
---

# Phase 7 — Production Readiness (Data Quality + Platform Hardening)

## Theme

A **product phase**: make the live platform (`https://isnad.noorinalabs.com`) actually deliver its analytical value. Phase 5 cut a real corpus over to prod; the P5W5/owner validation (2026-06-19, meta `noorinalabs-main#723`) found prod is **no longer empty** — 48 collections, real Arabic matn + translation, correct sect tags, auth/admin functional — **but the analytical layer on top of the corpus is broken**: isnad chains are sparse, search is down, dedup/parallels are empty, and narrator chronology is unpopulated. Phase 6 (Claude Efficiency) paid down framework cost; Phase 7 turns the loaded-but-inert corpus into a queryable, demo-grade product.

Owner directive (`/plan-phase 7`, 2026-06-25): scope this as a **broad production-readiness phase** — the data-quality remediation is the core, but also close out auth/session, the streaming pipeline, and the **P6 framework carry-forwards** (which run first, as a dedicated W1 lead-in). ML *modeling* defers to Phase 8; ML *enablement infra* (a local env that replicates staging, `main#775`) is in-scope as productionization.

> **Backlog source:** unlike the P6 framework phase, the **project board IS the P7 candidate pool** (charter `issues.md` § Wave Planning — Project Board Is Authoritative). 23 issues are already `phase-7`/`data-quality` labeled across `noorinalabs-main` / `isnad-graph` / `data-acquisition`; the W1 framework carry-forwards come from `phase_7_carry_forwards` in `cross-repo-status.json`.

> **sanadset is a W2 owner decision, not pre-committed (owner, 2026-06-25).** The root cause of the orphan pollution is the `sanadset` source: 650,986 hadith nodes / 0 collections (85% of the corpus), raw-isnad bulk-load never segmented/linked (`da#202`, root cause code-traced in `project_prod_loaded_quality_broken`). W2 begins with an **investigation** that produces an A/B recommendation — **Path A** (add `sanadset` to `HADITH_COMPOSITION` as narrator-only + purge the 650k orphan Hadith nodes; irreversible purge, recoverable by reload) vs **Path B** (parse `books.csv` → real Collection nodes + book_id map + cross-edition dedup; heavier, non-destructive). The owner picks A or B from the investigation before the fix executes. The per-source purge is owner-run (Admin → Data Management Danger Zone), never auto-run.

## End-state criteria — Phase 7 exits when ALL hold

| # | Criterion | Tracker | Nature |
|---|-----------|---------|--------|
| 1 | **Corpus integrity** — sanadset orphan pollution (650k / 85%) resolved per the W2 decision; raw-isnad-as-narrator pollution cleared; collection-linked % materially up from 8.98% | `da#202`, `da#153`, `da#196` | investigate + fix |
| 2 | **Chains queryable** — isnad chains segmented; `STUDIED_UNDER` populated (not 186); chain-validation API live | `da#202`, `ig#1040` | new + fix |
| 3 | **Search works on prod** — full-text returns Hadith entities; semantic search returns 200 not 500 (embeddings on prod) | `ig#1110` | fix |
| 4 | **Dedup / parallels populated** — compare/parallel pairs non-empty (dedup pipeline run on prod) | `noorinalabs-main#723` (folded) | run pipeline |
| 5 | **Narrator chronology + timeline** — narrator dates resolved & loaded to Neo4j; timeline populated | `main#673`, `da#161–166`, `ig#1039–1043` | new |
| 6 | **Auth/session solid** — deep-link / refresh to a protected route no longer bounces a signed-in user; no session accumulation | `ig#1111` | fix |
| 7 | ~~**Streaming pipeline repeatable** — Kafka E2E reproducible one-command (P5 end-state #5 carryover)~~ | `main#667` | **DEFERRED → Phase 8** (owner 2026-06-30); descoped from P7 end-state |
| 8 | **P6 framework thread closed** — structural-ontology generator fanned out to all child repos; framework consumes the C×T2 path (librarian/lifecycle/CLAUDE.md/memories); ontology README authored | `#820`, `#862`, `#863`, `#868` | carry-forward |

## Wave plan (proposed at /plan-phase 7, owner-approved 2026-06-25)

| Wave | Theme | Scope summary | Serves |
|------|-------|---------------|--------|
| **W1** (global 18) | **Framework carry-forward lead-in** | Close the P6 ontology thread before product work: `#820` structural-generator fan-out → remaining 6 child repos; `#862` framework-align (librarian surfaces `structural/llms.txt`, lifecycle regenerates/staleness-checks, CLAUDE.md §Ontology reframed, memories reconciled); `#863` ontology README; `#868` auto-create Wave-field option at kickoff; generator refinements (ts-enum interface/type kinds, merge-driver invocation-form). No data-acq contention (framework + child-repo CI). | #8 |
| **W2** | **Data-quality root cause** | The urgent prod fix. `da#202` **sanadset investigation → A/B recommendation → execute**; `da#196` composition.py None-value map semantics (couples to the fix); `ig#1110` search broken (full-text + semantic 500s). | #1, #2, #3 |
| **W3** | **Graph integrity + dedup + chains** | After the sanadset decision lands: `da#153` integrity sweep (orphans, NARRATED gaps, grade-parity, collection metadata); dedup/parallels pipeline run on prod; chain segmentation (`STUDIED_UNDER`). | #1, #2, #4 |
| **W4** (global 21) | **Narrator dating + prod re-validation** | `da#161–166` (DatePrecision model → rijāl date parse → multi-source reconciliation → ṭabaqa fallback + hijri conversion); `ig#1039–1043` (loader writes date props + dating/validate-chains/timeline-narrators APIs + ṭabaqa layering); `main#673` meta. **+ prod re-validation checkpoint** (owner 2026-06-26): run the W19/W20 sanadset/dedup/chain code on prod and verify criteria #1–#4 (orphan % down, `STUDIED_UNDER` populated, search 200, dedup pairs non-empty), closing `main#723`. da#228 (link muhaddithat) folds into the narrator thread. | #5 (+ verify #1–#4) |
| **W5 = wave-22** (FINAL) | **Timeline/dating APIs + #723 closeout + auth + TD floor** | *(owner-rescoped 2026-06-30)* The deferred W4 date-serving APIs `ig#1041`/`#1042`/`#1043` (+ close `main#673`); **`main#723` prod re-validation + close** (prod reloaded 2026-06-29 — validate criteria #1–#4 hold, then close); `ig#1111` auth deep-link; `main#775` local ML dev env / `da#136`→`da#178` Bihar (gated) / `da#139` geo as breadth triaged at `/wave-scope`. **Heavy TD floor** before phase exit. `main#667` Kafka streaming **deferred → Phase 8**. | #4, #5, #6 (+ verify #1–#3); #7 → P8 |

## Tech-debt intake

Per-wave **+20%** of the wave's feature/bug/security content (rounded up), enforced at `/wave-scope` Step 8.5 (`feedback_td_intake_20pct_per_wave`). On **W5** (final wave of the phase) the +20% is a **floor not a cap** — deliberately pull a large debt chunk to clear before phase exit.

## Phase exit (Phase 7 exits here)

- [ ] All **7 in-scope** end-state criteria hold (#1–#6 + #8; criterion **#7 streaming deferred → Phase 8** per owner 2026-06-30). #1, #2, #3, #8 already closed; #4, #5, #6 close in wave-22.
- [ ] Per-wave TD-intake compliance verified across W1–W5 (W5 = wave-22, heavy TD floor)
- [ ] sanadset W2 decision recorded + executed; prod re-validated (orphan %, chains, search) — prod reloaded 2026-06-29; wave-22 validates + closes `main#723`
- [ ] On confirmation, `/plan-phase 8` defines the next phase (ML modeling nucleus + carried-forward Kafka streaming `main#667`) before any P8 wave kicks off

## Deferred (not in P7)

- **ML modeling** (training/serving recommendation, semantic-similarity models beyond embeddings) — Phase 8; P7 delivers only the clean data + enablement infra (`main#775`) it depends on.
- **Streaming pipeline repeatable (Kafka E2E, `main#667`)** — **deferred to Phase 8** as infra (owner 2026-06-30); was P7 criterion #7, descoped from the P7 exit gate.
- Any product surface not blocking the in-scope criteria — triaged at each `/wave-scope`.

## References

- Phase 7 nucleus / prod validation: `noorinalabs-main#723`
- Prod-quality state + root-cause trace: `.claude/memory/project_prod_loaded_quality_broken.md`
- P7W1 framework carry-forwards: `cross-repo-status.json` → `phase_7_carry_forwards`
- Roadmap revision (P6=Claude Efficiency, P7=Data-Quality, ML→P8): `project_p5w5_prodcutover_p6_dataquality`
- Sequencing: kicks off after P6W17 (#823) wrapped + retro'd (2026-06-25).
