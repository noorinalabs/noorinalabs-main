---
name: project_staging_pipeline_not_wired
description: "Staging Neo4j holds only 47 manually-loaded sunni hadiths; the ingest pipeline has NEVER run on staging; no narrator graph. W4 \"real edges on stg\" was local-only. main#601 criterion"
metadata: 
  node_type: memory
  type: project
  originSessionId: 44d2d904-df74-40d3-b13d-f18441e349aa
---

Verified 2026-06-13 via main#601 (Aisha verification) + independent `ssh noorinalabs-stg` + `docker exec` cypher-shell check.

**Staging Neo4j reality:** 47 `Hadith` + 1 `Collection` (riyadussalihin), 47 `APPEARS_IN`. **ZERO Narrator nodes, ZERO NARRATED, ZERO STUDIED_UNDER** (only those two labels exist). Single-prefix IDs (no double-prefix bug on stg). isnad API live + wired to the same Neo4j (bolt://neo4j:7687).

**The crux (why criterion #1 is NOT MET):**
- The 47 hadiths were loaded **out-of-band** via the da#73 direct cypher-shell path — NOT through the deployed B2→Kafka→workers pipeline.
- The deployed ingest pipeline has **NEVER run on staging**: all Kafka topics at offset 0 (zero msgs ever), and **no ingest worker containers deployed** (none running or stopped).
- Repeatability/dedup is therefore **unverifiable on staging** (#139 was satisfied by an in-process harness, ingest-platform#62, not the deployed stg env).

**Lore correction:** the W4-retro "data-first core shipped — real NARRATED/STUDIED_UNDER edges, narrators, both-sects parallels" was **local/CI/harness only — NOT reflected on staging.** Staging is sunni-only, 47 hadiths, isnad graph absent. (This stale lore even misled a P4W5 spawn brief.)

**Latent bug (flag, not yet fixed):** `ingest-platform/src/graph/load_edges.py:279` puts `hadith_number` INSIDE the `APPEARS_IN` MERGE pattern → null `hadith_number` re-triggers the da#73-class load abort on real worker loads.

**To close criterion #1 (main#601):** (a) deploy ingest workers to staging + run the pipeline E2E with real B2/Kafka traffic; (b) load narrators + NARRATED/STUDIED_UNDER + shia/both-sects to staging. Both are infra-sized and live mostly in ingest-platform / data-acquisition (not the 4 P4W5 repos).

**RESOLVED 2026-06-13 — Owner chose Option A** (file gaps), then **scheduled the remediation into P4W6** (NOT Phase 5 — owner overrode: "another wave, tech-debt, Option-A work — proper data processing on the VPS + the rich graph experiment"). Three gap issues filed + boarded — **ingest-platform#83** (deploy workers to VPS + E2E, infra half), **data-acquisition#141** (produce + load rich narrator graph, data half), **ingest-platform#84** (the latent `load_edges.py:279` null-`hadith_number` MERGE-abort bug — verified at HEAD, NOT a dup of the data-acquisition-side da#77 fix). main#601 kept OPEN as the tracked not-met phase-4 end-state #1, `p4-wave-5` removed; **re-pulled into P4W6** (meta-issue **main#651** — "Real data on the VPS: proper pipeline processing + the rich graph experience"). P4W6 finishes Phase-4 #1 before the phase exits. Spine: ip#84 → da#120/da#133 → deploy#NEW (worker compose) → ip#83 → da#141. Also in P4W6: ig#1016 (HIGH: data client force-logs-out on 401 w/o refresh attempt — found in baseline Chrome pass), ig#1017 (raw `API error:` leak to UI), ig#NEW (post-data-load exploratory/rich-graph pass). 5 repos.

Related: [[project_p4_priority_data_first]], [[feedback_appears_in_merge_null]], [[project_staging_unreachable_from_sandbox]], [[project_studied_under_allowlist]].
