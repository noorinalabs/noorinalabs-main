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

Also this session: **ig#1179/PR#1180** fixed the staging-deploy embed race — `notify-deploy needs:` widened to `[build-and-push, build-and-push-embed]` (embed is a standing deploy gate since deploy#523; gating on api+frontend only raced the embed publish → tripped deploy-stg's deploy#418 manifest preflight). Ontology overlay `repos/isnad-graph.yaml` corrected to match (dispatch @v4, embed gate). Related: [[feedback_iac_over_oneoffs]] (graph ops via graph-ops.yml, not box one-offs), [[project_donor_readiness_wave]].
