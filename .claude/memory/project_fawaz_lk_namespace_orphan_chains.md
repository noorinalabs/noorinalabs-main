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

**Fix is a separate, non-trivial data-integration effort** (owner 2026-07-07 chose "investigate fawaz before prod"): needs (1) run-down of where the fawaz-keyed chain edges originate; (2) target-model decision — remap `fawaz:<book>:<n>` → `lk:<book>:<n>` (with slug normalization) IF numbering aligns, vs load fawaz six-books nodes, vs a dedup design; (3) domain verification that `fawaz:bukhari:1` == `lk:bukhari:1` (same hadith/numbering). NOT an inline fix.

**Consequence for the chain-fix rollout:** the da#325 migrate is verified-correct on stg but the graph-ops migrate gate ("0 absolute dangling", `queries/validation/transmitted_to_hadith_ref.cypher`) fails on these pre-existing orphans — it conflates canonicalization (migrate's job, done) with graph completeness. To ship the working chain fix to prod, the gate must assert the migration invariant (0 raw/non-`hdt:` ids + sample chain resolves), not absolute-zero-dangling. Relates to [[project_hadith_id_double_prefix]] (the same id-mismatch class, cross-source here).
