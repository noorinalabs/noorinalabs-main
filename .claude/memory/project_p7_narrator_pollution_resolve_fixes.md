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
