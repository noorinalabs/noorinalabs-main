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
