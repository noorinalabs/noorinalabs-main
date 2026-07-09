---
name: feedback_sweep_expensive_stage_before_launch
description: "When a pipeline stage is expensive, the launch gate is 'every defect at-or-before that stage is fixed' — not 'the blocking one is fixed'. A defect found after launch costs the whole stage again, so sweep the stage exhaustively while the fix is still free."
metadata:
  type: feedback
---

**Before launching an expensive stage, fix every known defect at or before it — not just the one blocking you.** The marginal cost of one more fix *before* launch is zero; the marginal cost of finding one *after* launch is the entire stage.

Established 2026-07-09 on the narrator-resolve re-run (main#928). Owner: *"handle all issues identified, determine which is the earliest in the processing flow, and re-start the process from that point when done. I am unbothered by a timesink or token usage complication, the more correct and repeatable the better right now."*

Pipeline: `acquire → parse → resolve → load → enrich`. `resolve` runs ~7.5 hours and its artifact feeds `load` and `enrich`.

- A `resolve`-stage defect fixed **before** launch is free — the 7.5h is being paid regardless.
- A `resolve`-stage defect found **after** launch costs another 7.5h, plus re-publish, re-wipe, re-load.

So the launch gate is **not** "the blocking defect is fixed." It is **"every known defect at or upstream of the expensive stage is merged."** Cosmetic ones too (name-quality residue, orphaned merge-log refs) — the fact that they are individually not worth a re-run is exactly why they must ride along with the one that is.

Downstream stages invert the logic: `load` and `enrich` are cheap and re-runnable, so their fixes may land *while* the expensive stage runs. Parallelise **after** the choke point, never across it.

**Why:** the instinct is to fix the blocker and go, because the blocker is what is visibly stopping you. But "is this defect blocking?" is the wrong question. The right question is **"is this defect upstream of the next thing I cannot cheaply repeat?"** Triage by *stage position and re-run cost*, not by severity. A trivial bug upstream of a 7.5h stage outranks a serious one downstream of it.

**How to apply:**
- Identify the earliest stage carrying **any** known defect. That is the restart point — not the stage of the *worst* defect. (Ours moved `resolve` → `parse` because of a parser column mismatch, da#353.)
- Enumerate **all** open issues by stage. Fix everything at-or-before the restart point, regardless of individual severity.
- Explicitly list what may land in parallel (downstream of the choke point) so the team isn't idle — and so nobody edits an upstream file mid-launch.
- Serialize agents editing the same upstream module; parallelise those in different stages.
- Beware the corollary: **your verification gate may itself be produced by a stage you are about to change.** Our top-10-by-mention-count check was reading `name_ar` labels chosen by the very bug it was meant to detect (da#356), so it read "clean" over a graph in which ʿĀʾisha did not exist. A gate downstream of a defect is not a gate.

Siblings: [[feedback_silent_zero_is_not_a_measurement]] (a probe that cannot return nonzero), [[feedback_fixture_makes_guard_assertion_inert]] (an assertion that cannot go red). This is the third member of the family — **a gate that reads its input from the thing it is checking.** All three: *verify the instrument before trusting the reading.*
