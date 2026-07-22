---
name: project_phase9_close_plan
description: How Phase 9 closes — wave-27 is pre-cutover data-quality only; the P9.2 cutover is a SEPARATE owner-gated session; downstream + tooling debt go to P10.
metadata:
  type: project
last_verified: 2026-07-22
---

# Phase 9 close sequence (owner decisions, P9W26 retro follow-up 2026-07-22)

Phase 9 (#977 "Data Quality & Choke-Point Completion") is a **data-correctness** phase whose headline deliverable is a **prod graph re-cutover** (#978), NOT a tech-debt phase. Its close is gated by the cutover, not by clearing the tooling backlog.

**Sequence to close Phase 9:**
1. **Wave 27** (meta #1067, "Pre-cutover data-quality closeout + hardening slice") — lands the remaining **re-run-gating** parse/resolve fixes (da#397, da#398, da#454) so the ~7.5h resolve re-run runs once on a clean corpus ([[feedback_sweep_expensive_stage_before_launch]]), plus a **high-value hardening ride-along**: main#940 (Hook-4 monotonic reviewer bug), #1047 (premise_check `/` false-STOP), #1050 (content_ts fail-open). Wave-27 does **NOT** run the cutover.
2. **P9.2 cutover (#978)** — the 7.5h resolve re-run + 7-step owner-gated prod re-cutover (promote→reload→prune→enrich→flag→verify, each prod write a separate `production` env approval). Runs as a **SEPARATE focused session** after wave-27 Tier 1 merges. Owner chose this split to isolate the heavy prod-approval work.
3. **Downstream/consumer (post-re-cut) → P10 opener:** ig#1185 (chain endpoint `over_merged` disclosure), da#443 (rijāl-authority acquisition **spike** only — the real hub-split is a later phase).

**Tooling/process tech-debt is NOT phase-9 mission** (#977 scopes the phase to "narrator/hadith data correctness only"). The lower-value tooling backlog — main#1048/#1051/#1053/#1055/#1060/#1062, the #1019 lifecycle-consolidation epic, #1021, #1037, #1014 — defers to a **P10 hardening wave**. Only #940/#1047/#1050 ride along in wave-27.

Next action: `/wave-scope 9 27` (meta-issue #1067 has a real theme; Gate B satisfied). Then `/wave-kickoff`. Refines the full phase plan in [[project_phase9_data_quality]] (waves 25/26 now DONE; this note carries the current close-sequence decisions).
