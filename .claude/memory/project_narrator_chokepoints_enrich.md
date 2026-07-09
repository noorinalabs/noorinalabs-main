---
name: project_narrator_chokepoints_enrich
description: Narrator choke-points (betweenness) enrich SHIPPED to stg, HELD from prod pending generic-name over-merge dedup (da#337).
metadata:
  type: project
---

Owner ask "find choke points of narrators in transmission chains" — code was da#326/#327 (sampled GDS betweenness+pagerank+louvain+degree via `enrich` CLI subcommand); only the RUN remained. Run stg-first via deploy `graph-ops.yml` (env=stg operation=enrich dry_run=false; loader image `noorinalabs-data-acquisition-load:stg-latest`).

**2026-07-08 — enrich RAN + VERIFIED on stg.** 150,187 narrators enriched (full coverage = canonical count). Two bugs surfaced+fixed along the way:
- **da#335/PR#336** — `write_audit_entry` crashed the whole run with `OSError: read-only file system: 'data'` AFTER `enrich_all` already wrote centrality to Neo4j (container fs is read-only by org convention). Fix: catch OSError, warn, return None (best-effort). NOT an OOM (the handoff's OOM warning was wrong).
- **deploy#544/PR#545** — graph-ops enrich verify echo queried `n.name_arabic` (nonexistent) → names logged as `None`. Fixed to `coalesce(n.name_ar, n.name_en)`. Narrator name props are `name_ar` / `name_en` (transliteration fallback via `_narrator_name_en`) / `name_ar_normalized` — there is **no** bare `n.name`.

**Plausibility check (named top-10, stg):** real mega-hubs surface correctly — الزهري al-Zuhrī, أبو هريرة Abū Hurayra, شعبة Shuʿba, سفيان Sufyān, سالم بن عبد الله Sālim b. ʿAbd Allāh → mechanism SOUND. **BUT the top is contaminated by over-merged generic-name nodes** (#1 أبو عبد الله 10.6M ≈2× Abū Hurayra, plus عبد الله / أبو جعفر / fragments عليم, ابن عمران) — same-kunya narrators collapse into one `nar:uuid5(normalized-name)` node, inflating betweenness. Entity-resolution problem UPSTREAM of centrality, same class as [[project_p7_narrator_pollution_resolve_fixes]] name-quality work. Caveat: sampled betweenness magnitudes shifted between two runs (seed 42 but sampled≈approx) — trust RANK not magnitude.

**Owner decision 2026-07-08: HOLD prod enrich until the over-merge dedup is fixed** (so first prod choke-points are all real narrators). stg stays enriched as-is for internal validation. Gate = **da#337** (disambiguate generic-name narrators via ṭabaqa/teacher-student/co-occurrence; acceptance = re-run stg top-10 has no bare-kunya aggregate outranking al-Zuhrī/Abū Hurayra → then promote prod w/ parity). Do NOT run prod enrich until da#337 lands + owner re-confirms.

**2026-07-09 — da#337 resolve re-run COMPLETE + PUBLISHED; stg load BLOCKED.** Full 10-stage `isnad-ingest resolve --no-resume` ran 21:58→05:27Z (rc=0). `narrator_split` landed: canonical **150,187 → 129,234**, 179 nodes split, 194 peel records (`data/curated/narrator_splits.parquet`), 4,005 mentions remapped. **The gate criterion is MET at parquet level** — top-20 by `mention_count` is now real hubs (Abū Hurayra #1 54,610; Shuʿba #5; Sufyān #6; **al-Zuhrī #7 24,910**; Anas #10; Qatāda #11; Nāfiʿ #12; Mālik #15) with no bare-kunya aggregate outranking them. Published to B2 as `staged/narrator-resolve/2026-07-09-dcb6205` (26 objects, verified).

**stg load RAN 2026-07-09T17:04–18:06Z (run 29035731215) — graph MUTATED, `rc=1` on validation. The da#337 gate is NOT yet met, and a reload alone CANNOT meet it.** The B2 Class-B cap (4th blocker, deploy#556) cleared after the owner touched the console; the first three defects were already fixed (da#348/PR#349, deploy#552+#553/PR#554; loader `stg-latest` = `sha-394e8d8`). All four enumerated in [[reference_pipeline_b2_publish_key]].

What the load did: 26 parquet / 1.1 GB pulled, `Narrator created=10,427 merged=118,807` (= **129,234**, the da#337 canonical count — the artifact and the ingest are both correct), 1,563,783 nodes / 235,039 new edges.

**Why the gate is not met — two independent reasons:**
1. **`betweenness_centrality` on stg is STALE** (from the 2026-07-08 enrich on the *old* graph). A data load does not recompute centrality. Exactly 150,187 narrators carry a betweenness value and 10,427 carry none (150,187+10,427 = 160,614 ✓). So the betweenness top-10 still shows the OLD failing ranking — `أبو عبد الله` 1.06e7, ~4.6× Abū Hurayra. **The gate metric is betweenness, so it currently reads FAIL for a stale-property reason, not a data reason.**
2. **The loader is MERGE-only, so the dedup's 31,380 collapsed ids were never deleted** — graph ends at 160,614 narrators, not 129,234 (see [[reference_graph_ops_cypher_shell]] §4). Re-running enrich over that union of old+new topology would produce a meaningless top-10.

**`mention_count` at graph level IS clean** and matches the parquet top-20 exactly: Abū Hurayra 54,610 · Shuʿba 29,280 · Sufyān 28,323 · al-Zuhrī 24,910; `أبو عبد الله` is now genuinely split into two nodes (mc 10,697 and 90), neither near the top. **da#337's mechanism works.**

**Validation `rc=1` — 3 FAILs, triage:** `chain_integrity: 100 cycles` (known, da#248); `transmitted_to_hadith_ref: 3` (known, da#325); **`orphan_narrators: 70,855`** (= zero-degree narrators; the real signal). Of those, **65,840 pre-date this load** (they carry a betweenness value; the top are `mention_count=0, betweenness=0.0` reference-catalog biographical entries never in a chain) and only 5,015 are newly created — the #723 baseline tail was 44,073, so the dedup contributed ~26.8k, NOT the whole 70,855. Do not attribute the full orphan count to da#337. Edge `created=0` on PARALLEL_OF / APPEARS_IN / GRADED_BY is **benign** (MERGE-matched existing): graph holds PARALLEL_OF 4,490,659 · TRANSMITTED_TO 2,679,527 · APPEARS_IN 775,916 · NARRATED 581,094 · STUDIED_UNDER 92,560 · GRADED_BY 48,283.

**Next action (needs an OWNER decision — both steps mutate stg, neither is started):**
1. **Prune** the orphan narrators (id ∉ new canonical set → `DETACH DELETE`). Per [[feedback_iac_over_oneoffs]] this belongs in `graph-ops.yml` as an operation (a small deploy PR), not a box one-off — same shape as the fawaz migrate+prune. Decide first whether to prune only the ~31,380 dedup-collapsed ids or the whole zero-degree tail (the 44,073 pre-existing catalog orphans are arguably legitimate reference nodes).
2. **Re-run enrich** (`graph-ops.yml`, env=stg) to recompute betweenness on the pruned graph. Only then is the top-10 gate test meaningful.

Prod still HELD (owner-gated; stg-verify first). Also seen: loader emits `collapsed_double_corpus_prefix` at **16M+ occurrences** (`sanadset:sanadset:…` → `sanadset:…`) — [[project_hadith_id_double_prefix]] / main#139 is live in the published artifact; the loader's guard normalizes it so the load is not corrupted, but the parquet still carries the doubled form.

Residual anomalies filed, NOT started (owner deferred to quota reset): **da#345** `عائذة` rank-3 at 35,436 (mis-normalized `عائشة`? or unpeeled over-merge); **da#346** bare `عبد الله` 19,412 (over-merge `narrator_split` declined — likely no date-band to discriminate on; needs isnad-neighbor context); **da#347** Anas b. Mālik **under**-merged across `أنس بن مالك` 18,968 / `أنس` 17,983, plus normalization artifacts (`ابن عبس`, `الأعلم`, diacriticized `قَتَادَةَ`). Note #346 and #347 pull in opposite directions (over- vs under-merge) — quantify before changing thresholds.

Also 2026-07-08: **ig#1179/PR#1180** fixed the staging-deploy embed race — `notify-deploy needs:` widened to `[build-and-push, build-and-push-embed]` (embed is a standing deploy gate since deploy#523; gating on api+frontend only raced the embed publish → tripped deploy-stg's deploy#418 manifest preflight). Ontology overlay `repos/isnad-graph.yaml` corrected to match (dispatch @v4, embed gate). Related: [[feedback_iac_over_oneoffs]] (graph ops via graph-ops.yml, not box one-offs), [[project_donor_readiness_wave]].
