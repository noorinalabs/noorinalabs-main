---
name: project_fawaz_lk_namespace_orphan_chains
description: RESOLVED 2026-07-07 — chain-id migrate + fawaz-orphan prune SHIPPED to stg AND prod (exact parity). ~196k fawaz six-books duplicate edges deleted; 2,485,909 resolving chains; empty-chain bug fixed.
metadata:
  type: project
---

**RESOLVED & SHIPPED 2026-07-07 (stg + prod, exact parity).** The chain-id fix + fawaz cleanup shipped together per owner directive. Vehicle = `graph-ops.yml` (deploy), all IaC (no box one-offs except read-only diagnosis). Landed PRs: da#334 (composition gate on chain edges — stops NEW orphans; mis carve-out structural), deploy#539 (migrate gate→invariant + `prune-orphans` op), deploy#541 (cypher-shell `:auto` fix — see [[reference_graph_ops_cypher_shell]]), deploy#543 (migrate verify samples a RESOLVING hadith_id, not an arbitrary edge). Final state BOTH envs: raw-form ids **0**, dangling **0**, resolving **2,485,909**, total TRANSMITTED_TO **2,485,909** (was 2,682,069; −196,160 fawaz six-books duplicates). **465,547 hadiths now have ≥2-edge real isnad chains** (was ~0 resolving pre-migrate — that WAS the "empty chain on search result" bug: all edges were raw-form/non-`hdt:` so the endpoint's `hdt:`-keyed join found nothing). lk:bukhari:10:603 → 5 chain edges; sample chains up to depth 349. API route `/api/v1/graph/hadith/{id}/chain` live (401 auth-gated; verified at data layer = the endpoint's exact query). Run order per env: **migrate FIRST (raw→0), then prune** (run-order guard refuses prune while raw>0 — critical: pre-migrate ALL edges are raw-form/dangling so a premature prune would wipe the graph). Next follow-on: da#326 enrich/centrality (choke-points) on the now-corrected graph.

--- original diagnosis (retained) ---

Surfaced while running the da#325 chain-id migration on **stg** (2026-07-07). The migration itself SUCCEEDED — 0 raw double-prefix ids remain, **487,466** distinct hadith ids' chains now resolve to nodes (was ~0; the "empty chains on search result" bug is FIXED for sanadset/lk/thaqalayn/etc.). But the post-op "0 dangling" gate failed on a **pre-existing, orthogonal** gap.

**The fawaz orphan set:** 196,250 `TRANSMITTED_TO` edges (~7.3% of 2,682,069; 35,807 distinct hadith ids) dangle — 99.99% `fawaz:` corpus, sub-collections exactly the Kutub al-Sittah (`bukhari, muslim, nasai, abudawud, ibnmajah, tirmidhi, malik`). These are **REAL isnad chains of real Narrator nodes** (verified: `hdt:fawaz:bukhari:1` → al-Humaydi → Sufyan → Yaḥyā ibn Saʿīd → … = the classic Bukhari #1 isnad), NOT degenerate.

**Root cause — cross-source id-namespace mismatch:**
- The six-books hadith **NODES** are loaded under the **`lk`** corpus (LK-Hadith-Corpus, `src/parse/lk_corpus.py`): `hdt:lk:bukhari:*` (7238), `lk:muslim` (7314), `lk:nasai` (5680), `lk:abu_dawud` (5138), `lk:ibn_majah` (4402), `lk:tirmidhi` (4209). LK normalizes slugs to underscore form via a map (`lk_corpus.py:50`: `abudawud→abu_dawud`, `ibnmajah→ibn_majah`).
- The orphaned **CHAINS** are keyed `fawaz:<book>:<n>` with the **non-underscore** slugs (`fawaz:abudawud`, `fawaz:ibnmajah`). `hdt:lk:abudawud:*` = 0 nodes (lk spells it `abu_dawud`), so they never join.
- **Anomaly to run down:** the `fawaz` source (`src/parse/fawaz.py`, fawazahmed0/hadith-api) is a hadith-**text** source that sets `isnad_raw_ar/en = None` — it produces **NO chains**. So the provenance of the fawaz-keyed `TRANSMITTED_TO` edges is itself unexplained (which loader attributed six-books isnads to `fawaz:` ids?). Only 122 `fawaz:` Hadith nodes exist total (all `fawaz:dehlawi`).

**Loaded Hadith-node corpora (stg):** sanadset 650,983; lk 33,981; thaqalayn 33,190; halimbahae 31,324; tusi 17,421; sunnah 8,895 (secondary colls: mishkat/riyadussalihin/adab/shamail/bulugh — NOT the six books); bihar 323; fawaz 122.

**CONFIRMED ROOT CAUSE (2026-07-07) — composition dedup gate not applied to chain edges.** Per the owner-confirmed composition (da#191, `src/parse/composition.py`): `lk` is the six-books canonical spine; `fawaz` loads its UNIQUE collections ONLY (Nawawi, Dehlawi, Qudsi) — its six-books hadiths are deliberately deduped to lk. The node loader (`load_nodes`) correctly applies `is_canonical_hadith`/`HADITH_COMPOSITION` and excludes fawaz's six-books NODES. **But the chain-edge path never applies that gate**, so fawaz's NER-derived six-books chain mentions loaded anyway → 196k orphaned `TRANSMITTED_TO` edges keyed `fawaz:<book>:<n>` with no node.

**These are DUPLICATES, not unique data** — verified on stg: every lk six-books hadith ALREADY has its own complete chains (bukhari 7229/7238, muslim 7297/7314, nasai 5674/5680, abu_dawud 5134/5138, ibn_majah 4388/4402, tirmidhi 4178/4209; lk overall 33,900/33,981 = 99.8%). So the fawaz six-books chains duplicate lk's canonical chains for hadiths deduped to lk.

**FIX = DROP the duplicates (not remap — remap would double lk's chains):**
1. **da pipeline**: apply the composition gate (`is_canonical_hadith`) to chain-mention rows / chain-edge loading, so a non-canonical source's chain mentions for a deduped collection are excluded — mirroring the node dedup. (Watch: `mis` is intentionally chains-only for Muslim — keyed to lk-canonical ids — so the gate must exclude fawaz-six-books-orphans without dropping mis's intended canonical-keyed chains.) Stops future orphaned edges.
2. **graph-ops migration**: delete the existing 196,250 orphaned fawaz six-books `TRANSMITTED_TO` edges (reference non-existent nodes; duplicate lk).
Then re-verify stg (0 dangling / gate green), then ship chain-id fix + fawaz-cleanup to prod TOGETHER (owner 2026-07-07 "fix fawaz first, ship together").

**Consequence for the chain-fix rollout:** the da#325 migrate is verified-correct on stg but the graph-ops migrate gate ("0 absolute dangling", `queries/validation/transmitted_to_hadith_ref.cypher`) fails on these pre-existing orphans — it conflates canonicalization (migrate's job, done) with graph completeness. To ship the working chain fix to prod, the gate must assert the migration invariant (0 raw/non-`hdt:` ids + sample chain resolves), not absolute-zero-dangling. Relates to [[project_hadith_id_double_prefix]] (the same id-mismatch class, cross-source here).
