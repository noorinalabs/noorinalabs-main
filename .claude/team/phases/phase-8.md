---
name: Phase 8 plan — Analytical Depth (ML Modeling + Streaming), with data-quality closeout lead-in
description: Phase definition, end-state criteria, exit gate, wave plan
phase: 8
status: active
created: 2026-07-01
last_updated: 2026-07-05
---

# Phase 8 — Analytical Depth: ML Modeling + Streaming

## Theme

Phase 7 made the loaded corpus **queryable** but exited with the data-quality nucleus (`noorinalabs-main#723`) **still open**: the P7W22 prod validation found ≥7,580 matn-as-narrator nodes live, because the reload used curated narrators generated *before* the `da#247` NER re-extraction (`.claude/memory/project_prod_loaded_quality_broken.md`). Phase 8 opens by **finishing that closeout** as a W1 lead-in — the same shape as P7, which opened with the P6 framework carry-forward — and then delivers the two analytical-depth threads the roadmap parked for this phase:

- **ML modeling** — the modeling *nucleus* the roadmap deferred out of P7 (`project_p5w5_prodcutover_p6_dataquality`: "Data-Quality/ML→P7 … ML modeling → Phase 8"). P7 delivered only the *clean data* it depends on; P8 delivers the first model on top of it.
- **Streaming pipeline** — Kafka E2E repeatable one-command bring-up (`main#667`), the former P7 end-state criterion #7, **descoped from P7 → deferred to P8** by owner 2026-06-30.

Owner directives feeding this plan:
- **wave-23 theme = the `#723` data-quality closeout** via the `da#247` integrated NER re-run → regenerate → reload (owner, this session).
- **Data-quality issues close on stg record-level verification**, prod validated as a promotion, tracked for stg↔prod parity (owner-ratified 2026-07-01, charter `issues.md § End-State Criterion → Data-quality criteria`; parity tracker `main#916`).

> **Backlog source:** the project board is the P8 candidate pool (charter `issues.md § Wave Planning — Project Board Is Authoritative`). The data-quality-closeout cluster is already `wave-23`-labeled (`da#248`, `da#258`, `da#259`, `ig#1148`, `deploy#521`); streaming (`main#667`) and ML-enablement (`main#775`) are boarded and carried; the ML-modeling issues themselves are **not yet filed** — the owner shapes that nucleus at the ML wave's `/wave-scope` (see criterion 5).

## End-state criteria — Phase 8 exits when ALL hold

| # | Criterion | Tracker | Nature |
|---|-----------|---------|--------|
| 1 | **Data-quality closeout (`#723`)** — matn-as-narrator pollution resolved by the `da#247` integrated NER re-run; narrators_canonical regenerated; **record-level** verified matn≈0 on **stg**, then re-verified on **prod** after promotion (charter data-quality rule + parity tracker `#916`); `#723` closed | `main#723`, `da#258`, `da#248`, `da#259`, `main#916` | fix + re-run + verify |
| 2 | **Semantic search live on prod** — pgvector provisioned + embeddings backfilled on prod; `/api/v1/search/semantic` returns `200` with results (not the current graceful `503`) | `ig#1148` | provision + fix |
| 3 | **Promotion path unblocked** — `promote.yml` prod-dispatch `403` fixed so a verified-good stg change promotes to prod one-command (the enabler for criterion 1's prod re-verify; today worked around via `deploy-prod.yml`) | `deploy#521` | infra fix |
| 4 | **Streaming pipeline repeatable** — Kafka E2E reproducible one-command bring-up (former P7 end-state #7) | `main#667` | new/infra |
| 5 | **ML modeling nucleus** — local dev env replicating full staging stood up for experimentation; **first ML model delivered** on the clean corpus (scope — e.g. narrator-similarity / isnad-authenticity scoring beyond raw embeddings — owner-defined at the ML wave's `/wave-scope`) | `main#775` + ML issues (TBF) | enablement + new |

## Wave plan (owner-approved 2026-07-02)

| Wave | Theme | Scope summary | Serves |
|------|-------|---------------|--------|
| **W1 = wave-23** (global 23) | **Data-quality closeout + promotion-path fix** | The carried-over `#723` closeout. **`deploy#521` lands first** (unblocks the stg→prod promotion the rest of the wave needs). Then the `da#247` integrated NER re-run → regenerate `narrators_canonical.parquet` → **stg** reload → **record-level** verify matn≈0 (API/UI sample, not aggregate) → promote prod → re-verify on prod (`#916`); `da#248` transmission cycles; `da#259` loader chain_integrity hang; `ig#1148` semantic search provisioned on prod. Closes `#723`. | 1, 2, 3 |
| **W2** (global 24) | **Streaming pipeline** | `main#667` — Kafka E2E repeatable, one-command bring-up. Independent of the graph corpus; can run without contending on data-acquisition. | 4 |
| **W3** (global 25, FINAL) | **ML enablement + modeling nucleus + TD floor** | `main#775` local docker dev env replicating full staging; the **first ML model** on the clean corpus (owner-defined scope at `/wave-scope`). Final wave of the phase → **heavy TD floor** before exit. | 5 |

*Wave ordering is flexible — W2 (streaming) is independent infra and could run before or in parallel with the ML enablement of W3; W1 is fixed first because it carries the open `#723` obligation and because clean data is a precondition for the ML nucleus.*

## Tech-debt intake

Per-wave **+20%** of the wave's feature/bug/security content (rounded up), enforced at `/wave-scope` Step 8.5 (`feedback_td_intake_20pct_per_wave`). On **W3** (final wave of the phase) the +20% is a **floor not a cap** — deliberately pull a large debt chunk to clear before phase exit.

## Phase exit (Phase 8 exits here)

- [ ] All 5 end-state criteria hold, each **applied-and-verified at origin** (charter `issues.md § End-State Criterion`); data-quality criteria verified **record-level** and parity-checked stg↔prod (`#916`).
- [ ] `#723` closed with a record-level prod re-verification cited (not an aggregate `matn=0`).
- [ ] Per-wave TD-intake compliance verified across W1–W3 (W3 = heavy TD floor).
- [ ] On confirmation, `/plan-phase 9` defines the next phase before any P9 wave kicks off.

## Deferred (not in P8)

- ML *serving at scale* / model-ops platform beyond the first-model nucleus — a later phase; P8 delivers the modeling nucleus + its local enablement, not a production inference platform.
- Any product surface not blocking the 5 in-scope criteria — triaged at each `/wave-scope`.
- **Donor-readiness wave (product polish, narrator-centric demo walkthrough)** — owner prioritized a fundraising demo (2026-07-05) but chose to run it **after** the committed analytical-depth work (streaming W24 → ML W25), no hard date. Off-theme for P8 (Analytical Depth), so it seeds the **Phase 9 opener** (or a P8 tail wave) — decided at `/plan-phase 9` on P8 exit. Headline scope: **deploy#523** semantic-search quality (hardens criterion #2 from "200 with garbage" to good results), **da#317** narrator matn-sentence tail, **ig#1166** graph deep-link, **da#318** matn markup leak, + a visual-credibility pass. Critical-path analysis preserved in `.claude/memory/project_donor_readiness_wave.md`.

## References

- Data-quality closeout state + root-cause trace: `.claude/memory/project_prod_loaded_quality_broken.md`, `.claude/memory/project_p7_narrator_pollution_resolve_fixes.md`
- stg-gated data-quality close + parity rule: charter `issues.md § End-State Criterion → Data-quality criteria`; parity tracker `main#916`; `feedback_stg_gate_before_prod`
- Roadmap (P6=Claude Efficiency, P7=Data-Quality, ML→P8): `project_p5w5_prodcutover_p6_dataquality`
- P7 exit carrying `#723` + streaming `#667` → P8: `.claude/team/phases/phase-7.md` (criterion #7 deferred, exit gate)
- Sequencing: kicks off after P7W22 (`#904`) wrapped + retro'd (2026-07-01); wave-23 = global 23 = Phase 8 Wave 1.
