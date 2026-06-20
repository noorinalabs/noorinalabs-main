---
name: project_prod_loaded_quality_broken
description: "Prod is NO LONGER empty — corpus loaded but segmentation/linkage/search broken; Phase-7 data-quality. meta main#723."
metadata: 
  node_type: memory
  type: project
  originSessionId: f3dcddd8-6ad9-48bf-b25e-92d034607282
---

Prod validation 2026-06-19 (live app https://isnad.noorinalabs.com, signed-in admin, browser walkthrough). Supersedes the earlier "prod is empty" state from the p5w5 corpus-load findings (now homed in data-acquisition memory).

**Prod IS loaded now** (cutover happened): 48 collections, sect tags correct incl. Al-Kāfī=Shia, real Arabic matn + translation, Timeline compilation dates correct (Bukhari 256 AH … Nasa'i 303 AH), auth/admin functional.

**But quality is broken (Admin → Data Management authoritative):**
- **Root cause = `sanadset` source: 650,986 hadith nodes / 0 collections** (85% of all hadiths) — raw isnad bulk-load, never segmented/linked. Real curated corpus = other 6 sources (lk 33,981, thaqalayn 33,190, halimbahae 31,324, tusi 17,421, sunnah 1,896, fawaz 122; ~69,067 collection-linked = APPEARS_IN).
- Hadiths 768,920 total, only **8.98% linked** (orphans = sanadset). Shia thaqalayn 33,190 matches known-clean figure.
- Narrators **132,999 raw** — isnad strings stored as narrator nodes; fragments like "…that"/"He said" as narrators.
- Chains are **SPARSE, not empty** (corrected): TRANSMITTED_TO 52,182, NARRATED 33,977, but STUDIED_UNDER only **186**. Sampled hadith had no chain; graph node rendered isolated.
- Search broken: full-text returns 0 Hadith entities (matns typed as narrators); semantic search **500s** on prod (embeddings staging-only, deploy#470).
- Compare/parallels empty (dedup not run); Timeline events empty (enrichment not run, #673).
- **Remediation:** Admin → Data Management "Danger Zone — Per-source Purge" can delete `sanadset` (irreversible — OWNER decision, do NOT auto-run).
- **Root cause (code trace, da#202):** `parse/sanadset.py` derives collection_name from CSV stem (→all 650K = "sanadset"), ignores the downloaded `books.csv` catalog, and emits NO `collections_sanadset.parquet` (every other parser does) → 0 Collection nodes → all APPEARS_IN skipped. sanadset defaults to load-all in `composition.py` (not listed). It was lit up for its narrator keystone (da#89), not hadiths. FIX Path A (recommended): add `"sanadset": frozenset()` to HADITH_COMPOSITION (mirror `mis` = narrator-only, no Hadith nodes) + purge existing nodes. Path B: parse books.csv→collections + book_id map + cross-edition dedup (heavier). Fully recoverable.

**Works well:** auth/session, RBAC (User Mgmt), System Health all-green (connectivity-only — blind to semantic 500), i18n excellent (7 langs incl RTL ar/ur, UI-only, data untransformed). Minor: usage-analytics counters unwired (0 while popular-narrators populated, raw UUIDs), audit log empty, sources filter slow-loads.

**Filed (Phase-7 data-quality, owner roadmap 3709d34):** meta **main#723**; **da#202** (segmentation pollution + no chains); **ig#1110** (search broken); **ig#1111** (auth deep-link bounce + session accumulation — scoped #666, NOT data-quality); orphan evidence added to **da#153**; validation summary on **main#665** (exit criterion NOT met).

**Label gap:** data-acquisition has no `phase-7` label; no `data-quality` label org-wide — create both at Phase-7 kickoff, relabel da#202/da#153.

Validation done via Claude-controlled Chrome (owner co-driving). Note: hard deep-link to a protected route (e.g. /graph) bounced an authenticated session to /login (hydration-race, ig#1111).
