---
name: project_phase9_data_quality
description: Phase 9 (Data Quality & Choke-Point Completion) plan — owner-approved 2026-07-17. Tracker main#977, cutover milestone main#978. 22 issues across 3 waves (25/26/27) + a re-run cutover milestone; donor-readiness pushed to P10. NOT yet kicked off.
metadata:
  type: project
---

# Phase 9 — Data Quality & Choke-Point Completion

Owner-approved 2026-07-17 (right after the prod cutover / [[project_narrator_chokepoints_enrich]] deploy#610+#611 closed). Owner ask: "handle all the non-blocking followups in the next wave" → "I want all the data quality backlog handled in the next phase, too." Scaffolding built by orchestrator (Nadia Khoury); **NOT yet kicked off** — issues labeled + boarded, no implementers spawned, `cross-repo-status.json` still says P8/wave-24 (leave until a real `/wave-kickoff`).

- **Tracker:** main#977 · **Cutover milestone:** main#978 · **Board:** project 2 (all 22 + both meta-issues added).
- **Labels:** `phase-9` (main/da/ig) + `wave-25`/`wave-26`/`wave-27` (da; ig has wave-27). `phase-9` pre-existed in ig as a stale early-scheme label — verified unused on open issues before reuse.

## Sequencing principle (load-bearing)
The ~7.5h resolve re-run is the expensive stage. Per [[feedback_sweep_expensive_stage_before_launch]], **every parse/resolve defect merges BEFORE the re-run** or it costs the whole stage again. Hence: upstream fixes (W25+W26) → re-run cutover (milestone) → downstream/consumer (W27).

## Waves (exact issue→wave map, as labeled)
- **Wave 25 (P9.1a) — narrator disambiguation & split correctness** *(gates re-run)*: da#248, #346, #347, #352, #431, #439, #444.
- **Wave 26 (P9.1b) — parse recovery, bio-promote & name quality** *(gates re-run)*: da#366, #373, #397, #398, #424, #427, #298, #299, #300, #301, #295, #446, #380. Highest-value: da#366 (recovers ~122k matn-embedded isnads), da#373.
- **Cutover milestone (P9.2, main#978)** — resolve re-run → new artifact → repeat promote→reload→prune→enrich→flag on prod, **owner-gated at every prod write** (mirrors deploy#610/#611; makes per-node `over_merge_note` durable via the typed reload). Precondition: ALL of W25+W26 merged. Per-repo cutover sub-issues created at ITS kickoff, not now.
- **Wave 27 (P9.3) — downstream/consumer/spike** *(after re-cutover)*: ig#1185 (chain endpoint discloses `over_merged`); da#443 = **source-acquisition SPIKE** (acquire an external rijāl authority dataset — person-ids/nasab/ṭabaqa/teacher-student edges; the actual hub split is a FUTURE phase once a source is secured — corpus-internal split proven NO/NO, see [[project_narrator_chokepoints_enrich]]).

## Out of scope (stay in general backlog, NOT P9)
Acquisition roadmap (da#280–293 school-of-thought corpora, da#98/#178), CLI/exit-code tooling (da#388–396), CI (da#421/#422), old test-coverage TD. P9 is narrator/hadith **data correctness** only.

## Donor-readiness → P10
Previously penciled as the P9 opener ([[project_donor_readiness_wave]]); moved to **P10** — the demo is better on the re-cut clean choke-point graph. Falls out of the ordering naturally.
