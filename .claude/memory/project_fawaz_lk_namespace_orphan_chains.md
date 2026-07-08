---
name: project_fawaz_lk_namespace_orphan_chains
description: ~196k six-books isnad chains keyed fawaz:<book>:<n> are orphaned from lk:<book>:<n> hadith nodes (cross-source id-namespace mismatch); surfaced by the da#325 migrate gate on stg 2026-07-07.
metadata:
  type: project
---

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
