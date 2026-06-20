---
name: feedback_td_intake_20pct_per_wave
description: "Per-wave tech-debt INTAKE policy (+20% of feature/bug scope), replacing brittle cumulative TD-ratio gate; enforced in /wave-scope Step 8.5 + /plan-phase Step 6."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 080813cd-f3b8-434d-974c-badf58620c96
---

Owner directive 2026-06-09: a hard cumulative tech-debt **ratio** gate (Phase-4 criterion #6, the `≤20%`/`<10%` thresholds) gets **wonky when the backlog gets small** — the denominator collapses faster than real debt does, so a genuinely healthy small backlog can still read "over." The Phase-3→4 burn-down already markedly dropped TD, so the goal is met.

**Policy going forward:** when planning a wave, after the feature work + bug fixes (the wave's non-TD content) are decided, **add tech-debt-only issues equal to 20% of that content, rounded up.** If fewer qualifying TD issues exist than the target, add **all** of them — a shortfall is a *good* signal (debt is genuinely low), never something to backfill with invented work.

**Why:** steady TD **intake** per wave is robust where a cumulative **ratio** gate whipsaws. The intake question ("did the wave take its 20%?") is the gate the team works to; the ratio reading stays informational.

**How to apply:**
- `/wave-scope` **Step 8.5** (added) — MANDATORY every wave. Base = in-scope (`$WAVE_LABEL`, post-disposition Step 7) issues NOT `tech-debt` and NOT `meta-issue`, pooled across all 8 repos. `TARGET = ceil(0.20*BASE)`. Candidate pool = open `tech-debt`-labeled, NOT `meta-issue`, NOT already carrying any `p{P}-wave-*` label, oldest-first. Owner-judgment select+confirm (same gate shape as Step 7); queue label-applies into Step 10 batch, fold into `tier_3_tech_debt` (assignment-row dicts per §13.1) + board; record `td_intake:<sel>/<target>`.
- `/plan-phase` **Step 6** (wave-structure proposal) — surfaces the +20% allocation at phase-plan time so wave tables reflect it.
- Interaction with criterion #6: this is the operational mechanism behind the TD goal; the cumulative-ratio reading is now informational, not the brittle gate. Open question for the owner: formally relax/replace #6's hard `<10%` threshold with the intake model.
