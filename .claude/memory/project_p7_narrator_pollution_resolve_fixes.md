---
name: project_p7_narrator_pollution_resolve_fixes
description: P7 #723 resolve-output fixes — build-host is the LOCAL VM, 40% narrator-name pollution (3 causes), fuzzy_cluster OOM + dedup OOM; 3 branches committed, integrated re-run pending
metadata:
  type: project
---

# P7 #723 resolve re-validation — pollution + OOM fixes (2026-06-28)

Worked the prod data-reload runbook (`noorinalabs-deploy/docs/runbooks/prod-data-reload-723.md`)
Step 3 (produce corrected W20/W21 Parquet). The owner's overnight resolve run crashed; this
session diagnosed + fixed the root causes. **Paused before the integrated re-run** (owner call).

## Execution model (corrected a recurring confusion)
- **Resolve runs on the LOCAL VM, not prod.** Runbook §3 builds Parquet on the *build host* (the
  local workstation/WSL VM); §4 pushes to prod via `SSH_HOST=noorinalabs-prod scripts/load_staging.sh`.
  **Prod never runs resolve** (verified: prod up 58 days, no resolve process/checkout). The "VM crash"
  was the **local** VM; the resolve foreground process died on SSH/host loss. Don't go hunting prod for it.
- Disambiguate/bio_promote output (289k exact-name-deduped canonical narrators + `narrator_mentions_resolved`)
  is the load-bearing #723 artifact and persists at `data/curated/` after each run. `fuzzy_cluster` is a
  **recall-INCREMENT on top** (its own docstring) — NOT required for the graph to load.

## Root causes found + fixed (all committed, NOT pushed/PR'd)
1. **Narrator name pollution — 39.9% of canonical narrators (115k/289k)** had junk names. 3 causes:
   `<NAR>`/`<IDF>` markup leakage (sanadset; `_is_narrator_like` missed it because `is_arabic` accepts
   mixed Latin+Arabic), thaqalayn parser dumping whole hadith bodies into the name field, and mubham
   (anonymous) collective descriptors. **Fix = central name-quality filter at NER** (`src/parse/name_quality.py`,
   da#247) → markup eliminated, 41.6k names recovered, 30.5k junk dropped. **Side effect: cluster
   candidate-pairs 1.43B → 230M (6.2×)** because stopword-pollution blocks vanish. Branch `I.Horvat/0247-narrator-name-quality`.
2. **fuzzy_cluster OOM + silent + slow.** Single-token blocking (محمد/الله…) built an unbounded `seen`
   set of billions of pairs → OOM, zero progress logs. Fix: composite **token-PAIR** blocking +
   drop the `seen` set (union-find is idempotent) + size cap (default K=1000, configurable) + **rapidfuzz
   `process.cdist`** size-aware vectorized scoring + progress logs. Output proven byte-identical to the
   original. Worktree `.claude/worktrees/fuzzy-cluster-opt` (first version committed `21fd8d7` in da repo; cdist refinements WIP).
3. **dedup OOM/non-resumable.** Held all chunks + `np.vstack` (2× matrix), lost the multi-hour encode on
   any crash. Fix: memmap-backed crash-resumable encode + per-chunk progress/ETA/RSS (da#245). Branch
   `I.Horvat/0245-dedup-harden`. Follow-up da#246 = parallelize the encode (open).

## Pending next step
**Integrated re-run**: combine da#247 + da#245 + fuzzy-cluster + owner's da#244 (NER unsegmentable fix,
on the data checkout's `I.Horvat/0244-ner-trailing-marker-strip` branch) onto the data-acquisition checkout,
re-run `isnad-ingest resolve` (now tractable + resumable + memory-safe), validate, **then PR the branches**
and continue the runbook (load to prod). Good pre-run output backed up at `data/curated.pre-rerun-2026-06-28`.

Issues: da#245 (dedup OOM), da#246 (parallelize dedup), da#247 (name pollution). Relates to [[project_prod_loaded_quality_broken]].

## Wave-23 residual-pollution audit (da#271, 2026-07-03 — post-NER-fix run-3 data)

DuckDB audit (da#273 tool) of run-3 disambiguate output, replicating the live blocking exactly
(`candidate_pairs_est` 179,759,721 reproduced): the 180M pair pool is **legit flat tail** across 8.25M
blocks — giant blocks already dropped by the 250-cap (1.37B pairs pre-filtered); pool-shrinking is
low-leverage, scoring speed (da#270) is the lever. Residual pollution = 26.5% of 210k canonical nodes,
3 classes: **Latin-transliteration under-merge** (23k nodes, sanadset/fawaz — head-visible duplicates,
e.g. "Anas bin Malik" mc 1152 never folds to the Arabic identity — the one NON-tail class),
benediction/honorific phrase names (16k, thaqalayn/lk), preposition fragments (25k, 96% mc≤1).
Owner approved 2026-07-03: fix all upstream this wave (Latin folding + name_quality benediction scrub,
N.Papadopoulos). Fixes landed as da PR#286 (fawaz→Arabic-extractor route, NOT transliteration: fawaz
full_text_ar is clean voweled isnad → native Arabic merging + full chains ~7.4 narr/hadith; sunnah stays
English deliberately) + PR#284 (benediction scrub + bio_promote clean_narrator_name parity). Root-cause
refinement: the 19,794 "sanadset" Latin nodes are actually the **kaggle narrator BIO table** (24,326
Latin/Urdu rows) reaching canonical via the kaggle_narrators→sanadset alias with bio_promote bypassing
clean_narrator_name; sanadset mentions are 100% Arabic. Residual follow-ups: kaggle Arabic-span+Urdu-fold
(parse layer) and lk Latin name_en fallback (41,998 empty-Arabic mentions) — filed by N.Papadopoulos.
**Owner decision 2026-07-03 (supersedes "deferred"): run 3 KILLED at 34% clustering; full resolve re-run
(run 4) from fresh NER once PR#277 (cluster caps) + #284 + #286 merge to the wave branch** — capped
cluster ~12–18h vs ~40h uncapped remaining; NER mention cache invalid after #286 (use `--no-resume`).

## Wave-23 run 4/4b — clustering crisis + matn-sentence defect (2026-07-04)

Run 4's `fuzzy_cluster` **safe-partition** phase sat silent 24h+. Diagnosed as a single
**172,378-member mega-group** out of union-find (Latin/common-name chain-glue bridging), which
`_safe_partition` re-split into `_can_merge`-clean cliques via a **quadratic greedy linear scan**
(~14.2B guard checks) with no progress logging → looked hung.

- **da#306 / PR#307 (merged 3194d50f)** — token-indexed candidate-subcluster lookup (superset
  property: a subcluster sharing `< _MIN_SHARED_TOKENS`=2 significant tokens can never accept a
  member → index by significant token, test only ≥1-shared-token candidates in creation order,
  first-accepting wins) + `_can_merge_cached` per-record key/token caching + telemetry
  (`cluster_group_sizes`, `safe_partition_progress`). **Byte-identical output, 17–19× speedup.**
  Fingerprint invariant #295 preserved (touches only post-union-find partition) → run 4b resumed
  from checkpoint at launch commit `9cd97be`+fix; safe-partition then finished in ~2.5h with telemetry.
- **Run 4b output: `narrators_canonical.parquet` = 172,532 rows** (healthy: below run-3's polluted
  210,494, well above the naive 62k over-merge floor; top narrators all real — أبو هريرة mc 53,327;
  0 bare relational pronouns; Latin nodes 23k→5,853). Log:
  `resolve-wave23-reload-20260704-run4b-resume.log`.
- **Quality defect found in 4b:** 25,971 canonical rows (~15%) are **hadith-matn / grading-commentary
  sentences** — `clean_narrator_name` scrubbed honorifics but KEPT the sentence body as a "narrator."
  Also **dedup silently skipped** (`dedup_missing_deps`): the `ml` uv dependency-group (sentence-
  transformers/faiss/torch/transformers/camel-tools) is **non-default** — `uv sync` prunes it; host
  needs `uv sync --group ml` (da#309, kept open for a fail-loud + reproducibility code fix; the plain
  `uv sync` also PRUNES the group, a repeatable trap).
- **da#308 / PR#310 (merged 0a3c2a41)** — `_is_matn_sentence` drop-gate in `clean_narrator_name`
  (verb/matn openers, token-anchored grading formulae, «»؟ matn punctuation as CO-FACTOR, nasab-
  connector density guard diacritics-insensitive via `normalize_arabic`). Precision defect caught in
  review: punctuation signal read pre-truncation text and dropped real names trailed by truncated-off
  matn tails (al-Awzāʿī, al-Aʿmash) → fixed by deriving `kept_text` from RETAINED tokens post-
  truncation. Corpus audit on the 172,532 rows: 6,254 drops (3.62% rows / 0.37% mention-weighted),
  100/100 random-drop sample genuinely matn, residual benediction 0.058% (<1% target). Applies at
  BOTH call sites (ner.py, bio_promote.py).

**Owner decision 2026-07-04 ("Fix filter + full re-run"): one more full clean resolve BEFORE any
staging reload** — `run 5`, `--no-resume`, fresh NER (sentence-gate now active at NER, not just
post-hoc) + dedup actually running (host synced `--group ml`). Log
`resolve-wave23-reload-20260704-run5-clean.log`, launched 2026-07-04 20:18Z from wave-23 head
`0a3c2a4`. **Crash-resume note:** a run-5 resume must use `--from-step <stage>` off the CURRENT
wave-23 head — NOT `9cd97be` (that was run-4b's fingerprint baseline; run 5 establishes a new one).
After a clean run 5: verify output vs run-3/4b baselines → stg reload → **owner-gated** prod
promotion (#723, parity tracker main#916). Prod=178.156.214.225 off-limits w/o sign-off;
stg=87.99.137.225.

## Wave-23 run 5 — COMPLETE but verification FAILED; da#308 gate gap (2026-07-05)

Run 5 ran fully clean end-to-end (NER→disambiguate→bio_promote→cluster→dedup→parallels),
**dedup ran this time** (host synced `--group ml`), 100% resolution, **165,939 canonical**
(down from 4b's 172,532). da#306 clustering fix worked perfectly: mega-group 165,636,
safe-partition ~2.9h with telemetry. Top narrators all real, 0 bare pronouns, dedup 6.72M
parallel links. **Those parts are solid.**

**BUT the matn contamination is essentially UNCHANGED from 4b** — ~25,708 canonical rows (15.5%)
still carry benediction/matn text, **10,185 mention-backed** (mc>1, drag real edges into graph).
Concentrated in **thaqalayn (28.3%) + fawaz (18.8%)**; itqan/lk clean (0.3%). Examples:
`عائشة، زوج النبي ﷺ قالت` (mc196), `سألت أبا الحسن (عليه السلام` (mc149), `نهى النبي ﷺ` (mc49).

**Root cause (confirmed `src/parse/name_quality.py:447`): `_MATN_OPENERS` is Sunni/Tirmidhī-tuned
(13 words) and misses the dominant Shia dialogue-hadith openers** — (1) `سألت`/`سُئل` ("I asked/
was asked"), `سمعت`, `حدثنا`, `أخبرنا`, `روى` absent (must match post-`normalize_arabic`: `سالت`,
`سءل`); (2) subject-led matn `عائشة … قالت` — verb 2nd-position, gate only tests `bare[0]`;
(3) short residue `نهى النبي` (2 tok after benediction-strip) < `_MATN_SENTENCE_MIN_TOKENS`.
da#308's own audit missed this (narrower benediction regex on Sunni-weighted cleaned data). This is
why thaqalayn/fawaz (isnad-extraction sources) contaminate while itqan/lk (bio sources) don't.

**da#311 filed. Owner decision 2026-07-05: "fix gate + post-hoc SCRUB" (NOT another 7h re-run).**
Ivana Horvat implementing on `I.Horvat/0311-matn-openers-scrub`: (A) extend `_MATN_OPENERS` +
subject-led + short-residue in `_is_matn_sentence`; (B) scrub tool modeled on existing
`scripts/scrub_relational_pollution.py` — applies corrected gate over run-5 curated + re-prunes
mentions/parallel_links/merge_log for referential consistency, writing to `data/curated.run5-scrubbed/`.
Acceptance: contamination <1%, 0 orphans, real long-nasab/kunya/Imam-honorific names retained.
Precedent for curated-scrub≡NER-filter equivalence: [[project_relational_pollution_scrub_equiv]]
(singleton case; mc>1 rows here need explicit mention/edge re-prune). Scrub RUN against live data =
orchestrator post-merge, THEN verify → stg reload → owner-gated prod.

---

**da#311 RESOLVED — PR #312 merged 2026-07-05 (merge 27d9098 → deployments/phase-8/wave-23).**
Four passes in `src/parse/name_quality.py` (`clean_narrator_name`), each caught a distinct
prod-affecting defect by an INDEPENDENT pyarrow probe on the **load-bearing `name_ar` field**
(not the gate's own output, not `name_ar_normalized` — graph loader reads `name_ar` first,
`load_nodes.py:169`):
- Pass 1-2: matn openers (سالت/سءل/subject-led قالت/short-residue) + clean the RIGHT field.
- Pass 3: cleaned name_ar correctly BUT over-dropped numeric-prefixed real narrators.
- **Round-4 (numeric-prefix recovery, 90af93e):** rule **3b** was DROPPING any span whose first
  token is a bare digit (thaqalayn enumeration artifact "1 علي بن ابراهيم"). False assumption that a
  clean un-numbered canonical existed elsewhere — **Ali ibn Ibrahim al-Qummi (علي بن ابراهيم),
  al-Kafi's most prolific isnad head, existed SOLELY as numbered forms and vanished (0 rows).**
  Fix: STRIP leading ordinal(s) + re-gate remainder → recovered (32 rows/mc2886).
- **Round-4b (all-residue floor, ac0f121 — Kavitha's ChangesRequested):** the numeric-strip
  re-ADMITTED 793 rows/929 mentions of junk round-3 had dropped: passive verb **روي** ("was
  narrated", ya-final — DISTINCT token from روى, `normalize_arabic` does NOT fold ى→ي) at 541
  mentions, attached-waw isnad fragments (وعنه/وباسناده — my waw-strip only handled a SEPARATE و),
  bare mubham. Fix: add روي to `_MATN_OPENERS`; new `_is_isnad_residue_token` (folds leading
  attached-waw so وعنه→عنه drops but real وهب→هب survives) + general **rule 5b** drops a span whose
  EVERY token is residue. **5b also closed the pre-existing guard-5 bare-collective gap** (rule 5
  needs a partitive من): **رجل ("a man") mc-4920**, بعض/شيخ/ناس/نفر/قوم — same أبيه-class pollution
  as [[project_relational_pollution_scrub_equiv]], independent of any numeric prefix.

**Final scrub (merged code) → `data/curated.run5-scrubbed/`:** 165,939 → **150,187** canonical
(15,752 dropped, 64,348 recovered/rewritten). Precision mw-matn 1.03%→**0.054%**; all-residue
survivors **0**. Recall: Ali 32/mc2886, retain سالم 4072 / الزهري 24925. Referential **0 orphans,
0 nulls** / 3,276,238 mentions. 274 tests, 7/7 CI, 2 independent reviews (Nikolaos+Kavitha).
Tool: `scripts/scrub_matn_canonical.py`. Non-blocking tech-debt: da#314 (matn-provenance leakage),
da#315 (particle nodes ما/وبه 0.006%), da#316 (RLM-shielded trailing punct, 49 low-mc canonicals).

**LESSON: independent measurement on the load-bearing field caught what self-reports (circular gate)
AND a first reviewer both missed** — round-4b's روي(541)/رجل(4920) regression was found only by
Kavitha's independent probe after Nikolaos + orchestrator both passed round-4. Two-reviewer rigor paid.

**HELD: artifact ready; staging reload (#723, stg=87.99.137.225) awaits explicit OWNER sign-off.
Prod=178.156.214.225 off-limits without owner sign-off.**

## Wave-23 STG record-level verification — PASSES all 4 #723 criteria (2026-07-05, owner-approved reload)

Owner approved the staging reload 2026-07-05. **Ground truth on checking stg: the scrubbed artifact
is ALREADY loaded** — `noorinalabs-neo4j-1` holds **exactly 150,187 Narrator nodes** (== scrubbed
`narrators_canonical` count; corpus split itqan 46,616 / fawaz 37,107 / thaqalayn 32,428 / sanadset
27,862 / lk 4,886 / sunnah 1,285 / muhaddithat 3). So the "HELD awaits sign-off" line above was
stale vs actual stg state — did NOT re-run a redundant destructive purge+reload; **verified at
record level instead** (per charter: surface reality-vs-described contradiction, don't proceed with
a redundant destructive op). Record-level cypher on the LOAD-BEARING `name_ar` field (the graph
loader reads name_ar first — [[project_relational_pollution_scrub_equiv]] / load_nodes.py:169):

- **Crit #1 matn-as-narrator: PASS.** Known run-5 high-mc pollution GONE — رجل(was mc4920)=0,
  عائشة…قالت(mc196)=0, نهى النبي(mc49)=0. Mention-weighted matn residual = **437 mentions /
  3,276,238 = 0.013%** (target <1%): the `>140`-char non-nasab tail (372 nodes, 59 mc>1) — longer
  matn passages that don't start with an opener token (ما انهر الدم mc3, اقول اللهم باعد mc3). This
  is the da#314/#315/#316 NON-BLOCKING tail, not a criterion failure. NB the opener-filter's "11
  matn-smell" were mostly FALSE positives — رويفع بن ثابت الأنصاري mc42 + رويم بن يزيد mc17 are the
  REAL companion Ruwayfiʿ/Ruwaym (start with روي). Real recovered names present: علي بن ابراهيم
  (al-Qummi), الزهري 379 nodes, top-15 all real (أبو هريرة 54,550).
- **Crit #1 collection linkage: PASS.** APPEARS_IN 775,916 / 776,239 Hadith = **99.96%** (baseline 8.98%).
- **Crit #2: PASS.** STUDIED_UNDER 80,203 (>>186). Chains NOT hollow: 587,932 Chain nodes carry
  `narrator_ids` ARRAY + `hadith_id` as PROPERTIES (not edges) — `id,hadith_id,classification,
  narrator_ids,chain_index,chain_length,is_complete,is_elevated`; TRANSMITTED_TO (2.68M) groups by
  `hadith_id`+`position_in_chain`, NOT `chain_id`. "connected_chains=0" is by design (property model),
  NOT the [[project_chain_hollow_reads_staging]] defect.
- **Crit #3 search: PASS (data layer).** fulltext `hadith_search`(matn_ar/en)+`narrator_search`
  (name_ar/en) both ONLINE; queryNodes returns real Hadith matn + Abu Hurayra. API /search /narrators
  are 401-gated (need users.stg JWT) — verified the index layer the API calls, not the HTTP surface.
- **Crit #4: PASS.** PARALLEL_OF 4,490,659 edges.

stg API image = `stg-5e76ebf` (isnad-graph wave-23 head — current). **Per W22-retro rule (a
data-quality issue closes on STG record-level verification), #723 crit-1 is now stg-VALIDATED.**
Prod promotion remains owner-gated; re-verify on prod after promotion via parity tracker main#916.
Under-merge variants (وأبي هريرة mc150, أبو هريرة الدوسي mc73) = accepted Latin/variant under-merge
tech-debt, not matn.
