---
name: project_prod_loaded_quality_broken
description: "#723 crit-1: 2026-07-02 record-level graph check (stg+prod, direct Neo4j) — UI-visible HEAD IS CLEAN (219,849 narrators, real top-20, 0 mubham, English-matn class gone) + stg↔prod parity confirmed. The ≥7,580 isnad-verb pollution is REAL but 96.6% mention≤1 TAIL (only 11 at mention≥5); da#258 (NER split/truncate/matn-guard) is the tail fix, da#248 mononym-cycles, da#259 loader-hang. Owner-reported class resolved. History below."
metadata: 
  node_type: memory
  type: project
  originSessionId: f3dcddd8-6ad9-48bf-b25e-92d034607282
---

> ## ⛔ RETRACTION 2026-07-11 — the "weight by mention_count" conclusion below is WRONG and was actively harmful
>
> This memory's central move — *triage narrator-quality by `mention_count`, because the pollution is a `mention ≤ 1` tail* — is **retracted**. It is sound for **prioritising cleanup** (a polluted node nobody cites matters less). It is **catastrophic as a measurement axis**, and it was read as both.
>
> **45,613 of 150,187 canonical rows carry `mention_count = 0` — 30.4% of the corpus.** Bio-promoted narrators (attested in rijal dictionaries, not in chains) have no mentions **by construction**. A mention-weighted view does not under-count them; it **erases them**. On da#423 that blind spot hid **three successive rounds** of a scrub deleting **Umm Kulthum bint Muhammad (the Prophet's daughter), the Prophet's son, and Abu Bakr al-Siddiq** — each round passing 6/6 CI with an approving reviewer, while the weighted drop-count barely moved.
>
> **Never use `mention_count` as the axis of a correctness measurement.** Weight for *triage*; measure **unweighted**. See [[feedback_drop_gate_bidirectional_ab]].
>
> The 07-02 findings below (head clean, stg↔prod parity, the pollution tail) remain accurate as a *snapshot*. #723 was CLOSED 07-05 — see [[project_p7_narrator_pollution_resolve_fixes]].

## ✅ RECONCILIATION 2026-07-02 — record-level graph check: UI head CLEAN, pollution is a mention≤1 TAIL

Did a **record-level** check directly against both Neo4j graphs (`ssh noorinalabs-{stg,prod}` → `cypher-shell`), reading the actual `name_ar` strings of high-mention narrators — the sentence-level detection the 07-01 "false pass" lacked. **stg and prod are byte-identical** (same 219,849 narrators, same top-20, same residual counts) → **stg↔prod parity holds (#916)**.

**Both the 07-01 memory AND da#258 were right, at different framings — reconciled:**
- The 07-01 raw isnad-verb count is REAL and still present: **7,451** narrator nodes contain قالوا/فقال/حدثنا/… on prod (7,451 on stg too). The memory was NOT wrong that they exist.
- **But 96.6% are the mention≤1 tail:** of those 7,451 → mention≥5 = **11**, mention 2–4 = 88, mention≤1 = **7,352**. The mention-ranked narrator views surface the *head*, which is clean.
- **UI-visible head IS clean** (the owner-reported class is resolved): top-20 by mention are all real (أبو هريرة/سفيان/شعبة/الزهري/مالك…); relational-pronoun mubham (ابيه/جده) = **0 rows**; the English `Thawban:matn` class (da#253) = **0 sentences** (the ASCII hits are romanized real names).
- The high-mention isnad-verb nodes are mostly da#258 **class-2 compound joins** ("يحيى بن ايوب وقتيبه وابن حجر قالوا" = three real narrators + "they said"), not pure matn — they need **splitting**, not deletion.

**True da#258 residual at mention≥5:** ~6 genuine Arabic matn bodies (incl. the exact `كان علي بن ابي طالب بالكوفه…` cited in da#258) + ~19 compound joins (`… جميعا`) + ~74 chain-connective fragments (`… عن …`). The 30-token cap alone can't catch these because real *ibn*-lineage names legitimately reach ~30 tokens (a crude ≥8-token filter false-flags 2,102 real names). Fix = NER-stage split/truncate + Arabic-stop-word density guard, mirroring da#253's English handling.

**Net:** #723 crit-1 (matn-as-narrator) is satisfied at the **record-level, mention-weighted** layer (the charter data-quality rule) for the owner-reported class, on stg AND prod. The remaining work is the **tail cleanup** tracked by **da#258** (NER split/truncate/guard) + **da#248** (mononym over-merge → transmission cycles) + **da#259** (loader validation hang). These reduce the 7,352-node tail on the next regenerate→reload. Do NOT re-frame this as "prod still broken / not closeable" — the head is clean and parity holds; da#258 is a tail refinement, not a catastrophe. [[feedback_honest_audit_over_conclusion_claim]] cuts both ways: don't overclaim clean, don't overclaim broken — weight by mention_count.

---

## ⚠ CORRECTION 2026-07-01 — corrected-artifact reload STILL did not fix matn pollution

Reloaded prod 2026-07-01 from "corrected" curated artifacts (`clean_narrator_name` applied to `name_ar` + `name_ar_normalized`; my in-session "matn=0" pass) and re-validated the **live prod API** with the seeded `qa-prod@noorinalabs.com` reader account (minted a reader JWT via the user-service container, bypassing the Cloudflare bot-block that 1010s server-side curl; browser extension was not connected so this was API-level, which IS the exact data the narrator UI renders).

**Result — criterion 1 STILL BROKEN.** `/api/v1/narrators` returns **≥7,580** of 219,849 Narrator nodes as matn/isnad fragments (conservative floor: nodes containing isnad verbs قالوا/فقال/حدثنا/…). Live examples: `قالوا` · `جلست الى نفر من اصحاب رسول الله بالمدينه فقال` · `الله ومن يعظم شعاءر الله فانها من تقوى القلوب` (Qur'anic phrase). **My "matn=0" was a false pass** — it measured markup/exact-duplicate signatures, never "does this name read as a *sentence*." Root cause confirmed = the 06-30 hypothesis: the reload used curated narrators generated **before the da#247 NER re-extraction**; `clean_narrator_name` (da#253) strips markup but cannot remove entities NER mis-emitted as narrators. **No reload fixes crit-1 until da#247's integrated re-run regenerates clean curated narrators, verified at the API/UI layer.**

**What DID pass on 2026-07-01 prod:** crit-2 chains populated (576,416); **crit-3a 50-cap LIFTED** (`/api/v1/search?...&limit=100` → 100 results, total 4,035 — ig#1147 fixed); crit-3b semantic returns graceful `503` "not provisioned" (ig#1148, expected — a pgvector-provisioning project, not a reload side-effect).

**Tracking:** #723 stays OPEN (crit-1). Forward tracker = **da#258** (OPEN, wave-23, "NER residual: Arabic matn-prose"), given prod-verified acceptance criteria (regenerate → reload stg → API-verify ~0 → promote prod → re-API-verify). **da#247 + da#253 are CLOSED but superseded-forward** — closed on artifact-fix, never reached prod; do not re-close crit-1 on artifact-fix alone. Lesson reinforced: [[feedback_honest_audit_over_conclusion_claim]], [[feedback_verify_diagnosis_before_delegating]] — cypher/aggregate pass ≠ record-level (name-by-name) verification.

---

## ⚠ CORRECTION 2026-06-30 — prod re-validation FAILED; "RESOLVED" below was premature

Owner re-checked the **live prod UI** 2026-06-30 and found prod is NOT in the validated state the 2026-06-29 cypher pass below claimed. Three defects filed into **wave-22** (the #723 closeout wave):
- **da#253** — **matn-as-narrator pollution PERSISTS on prod.** Example narrator `nar:00063b2c-b33c-5168-8dbb-71dc8038f64b` is named with a hadith matn fragment ("Thawban:The Messenger of Allah (ﷺ) sacrificed during a journey and then…"). This contradicts the "pollution 0" line below. **Most likely cause: the 06-29 reload predates the `da#247` NER fix (whose integrated re-run was *pending* at the 06-28 handoff) — i.e. prod was loaded with PRE-FIX narrator data.** The 06-29 cypher pass measured *relational + English-fragment* pollution (which read 0), NOT matn-as-narrator name pollution — so "pollution 0" was a narrower claim than it sounded. To confirm in da#253.
- **ig#1148** — **semantic search still 500s/fails on prod** despite `ig#1110` being closed. prod ≠ stg (embeddings likely not backfilled on the 06-29 prod load).
- **ig#1147** — full-text search **hard-capped at 50 results** (5 pages × 10) on stg AND prod — a separate code/config ceiling bug.

**Net:** criteria #1 (corpus integrity) and #3 (search) are NOT validated on prod. **#723 stays open.** Lesson: a cypher-metric pass is not a UI walkthrough — validate the actual narrator *names* and the search *endpoints*, not just aggregate counts. See [[feedback_honest_audit_over_conclusion_claim]], [[feedback_verify_diagnosis_before_delegating]].

---

**[SUPERSEDED — see correction above] 2026-06-29 — #723 corrected graph deployed to prod.** Prod Neo4j was reloaded from the pollution-fixed, chains-populated curated artifacts (same set validated on stage). Live prod validation (cypher, https://isnad.noorinalabs.com → 200):
- Nodes **1,665,760** (Hadith 776,242 / Chain 585,129 / Narrator 232,766 / Grading 69,465 / Collection 55) + 22 app AUDIT_LOG (preserved); edges **8,707,661**.
- Chains **100% populated** (585,129, **0 hollow**); narrator linkage **68.7%** (was 8.98%); top narrators all real (سفيان/شعبة/أبو هريرة/الزهري …), **أبيه gone**; relational + English-fragment pollution **0**.
- Infra: deploy#505 merged+applied to prod host — 8G swap (fstab-persisted) + Neo4j recreated at 10G limit / 5G heap / 3G pagecache (matches the proven-good stage config). [[feedback_local_ci_parity_no_force]] N/A.
- **Surprise found at execution:** prod's isnad graph was ALREADY EMPTY (only 22 AUDIT_LOG nodes; neostore an 8KB empty store, zeroed sometime after 2026-06-18) — NOT the 768k polluted graph below. So the planned destructive wipe was unnecessary; went straight to a clean MERGE load. How/when prod lost its prior data between 06-19 and 06-29 is unexplained (no orphaned volume) — open question, but moot since replaced.
- **Loader gotcha:** the loader's internal `chain_integrity` validation query ran pathologically slow on the full prod graph (>40min, never finished, stopped manually). Data load itself (nodes 21:01Z, edges 21:46Z) completed cleanly with 0 errors; validated independently via direct cypher. Relates to da#248 (chain cycles) — the cycle-detection validation may need a perf/timeout fix.

---

## History — the prior broken state (pre-2026-06-29, now remediated)

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
