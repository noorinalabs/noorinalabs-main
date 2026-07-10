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

**The gate is DYNAMIC, and it lives in the issue BODY.** Owner 2026-07-09: *"The gate list should be dynamic, add issues to it when you find more."* A gate enumerated once at filing time silently decays into a snapshot. So: any newly discovered at-or-upstream defect is added **the moment it is found**, before triage/assignment/costing; a row leaves only when **merged**, not when fixed/approved/understood; anyone may add, only the orchestrator removes; **if unsure whether it is upstream, add it** — a false positive costs one line, a false negative costs the whole stage. Keep it in the issue **body**, never in a comment: comments scroll, and the newest one reads as authoritative even when stale.

**Removal is an EVENT with an OWNER, not a condition.** "A row leaves when merged" is a predicate that nobody evaluates. Written that way the gate has an add-trigger and no remove-trigger, and it drifts within the hour — a rule with no execution site decays exactly like an advisory hook that writes no state ([[feedback_generic_prompt_hook_advisory_decay]]). So: **on every merge of a gate-row PR, the orchestrator re-derives that row's state from the API and edits the body.** Put the step in `/wave-wrapup` so it survives a session boundary.

Two corollaries, both learned by watching a ledger rot in about thirty minutes:

- **Never restate API-owned state in a ledger cell.** Review verdicts, head shas, and mergeability belong to GitHub; a cell that copies them drifts, always. The durable content of a row is **issue number, stage, and quality risk** — those do not change. If a review state must appear, stamp it `as-of <UTC>`: a body carries no timestamp at all, where a comment at least carries one. The body fixes *ordering ambiguity*, not staleness.
- **A row and its issue must agree.** Corrections land in the gate and never propagate back, so an implementer opens the issue and reads the superseded mechanism first. When you reword a row, retitle its issue.

**Second axis: quality risk, which decides membership — not severity.** Two upstream fixes can have opposite risk. A fix that only *reads* data already segmented on disk infers nothing and cannot regress correctness (da#368's 6,143 chains in an unread column; `tusi`'s 17,089 already-separated isnads). A fix that *extracts* structure from free text can — and its failure mode is the very pollution the re-run exists to remove (da#366's matn-embedded chains). **The re-run must produce a graph that is strictly more correct.** Zero-inference completeness rides along; extraction-based completeness waits for a validated splitter and costs its own re-run — which it would have cost regardless.

State it as a **procedure**, not an intuition, or a reader who wasn't there cannot classify a new defect and has to ask you:

> **Does this fix invent structure that is not already explicit in the source bytes?**
> - **Yes** → it waits for a validated splitter, and costs its own re-run.
> - **No** → it rides along.
> - **Risk contingent on merge order, or on another row landing** → it still rides along, but the constraint is recorded **in the same row**. An unordered merge of a zero-risk fix is not a zero-risk merge.

That third branch is not a footnote. A routing fix that is harmless *after* the fallback is removed, and *is the defect* before it, has no fixed risk value at all — its risk is a function of merge order. So is a fix that is correct only alongside its sibling. Both ride along; neither is safe alone.

A splitter must be validated against **every convention its corpus uses**, not the one its author had in mind: sanadset's chains open with a bare narrator name, `lk`'s with a receipt verb, and a splitter tuned on one passes green while silently failing the other. See [[feedback_silent_zero_is_not_a_measurement]] — the size of da#366's population is itself a measurement, and it was wrong three times before it was a bound.

**How to apply:**
- Identify the earliest stage carrying **any** known defect. That is the restart point — not the stage of the *worst* defect. (Ours moved `resolve` → `parse` because of a parser column mismatch, da#353.)
- Enumerate **all** open issues by stage. Fix everything at-or-before the restart point, regardless of individual severity.
- Explicitly list what may land in parallel (downstream of the choke point) so the team isn't idle — and so nobody edits an upstream file mid-launch.
- Serialize agents editing the same upstream module; parallelise those in different stages.
- Beware the corollary: **your verification gate may itself be produced by a stage you are about to change.** Our top-10-by-mention-count check was reading `name_ar` labels chosen by the very bug it was meant to detect (da#356), so it read "clean" over a graph in which ʿĀʾisha did not exist. A gate downstream of a defect is not a gate.

Siblings: [[feedback_silent_zero_is_not_a_measurement]] (a probe that cannot return nonzero), [[feedback_fixture_makes_guard_assertion_inert]] (an assertion that cannot go red). This is the third member of the family — **a gate that reads its input from the thing it is checking.** All three: *verify the instrument before trusting the reading.*

## The mirror: a gate UPSTREAM of the fix is not a gate either (added 2026-07-09, da#384 Amendment Q)

*A gate downstream of a defect is not a gate* has an exact mirror image, and I walked into it the same evening I wrote the original.

Reviewing da#384/PR#387 — the PR that replaces a hand-maintained list of reserved exit codes with an `IntEnum` — I demanded a static guard reddening on any `sys.exit(<int literal != 0>)` anywhere under `src/`. Sound rule. But I had, two amendments earlier, **explicitly forbidden that PR's author from touching `_cmd_load`**, because that line belongs to a different open PR whose reviewers' verdicts hang on it. And `_cmd_load` held the **last** bare integer in the file.

So the guard could not go green on the tree it was ordered onto. The author's only remaining move was to ship it with an exemption list naming the line — **a hand-maintained list of permitted bare exits.** The same object as the hand-maintained reserved-value list the PR existed to delete, and as the hand-maintained AST node-type table a reviewer had deleted an hour before. *The guard written to close the defect class would have been the third instance of it, authored by the amendment that named the class.*

**A codebase-wide prohibition has a precondition on the tree, and it is not "my change is correct" — it is "no instance remains anywhere."**

> **Before demanding a prohibition, run it against `HEAD`. If it reds, you have specified a fix, not a guard — and if the offending line is not yours, you have specified it against someone else's file.**

So a prohibition **must be introduced by the change that removes the last instance of it**, or it ships with a catalogue of what it tolerates. The guard is the *closing brace* of an invariant, and the brace goes where the invariant closes — retime it onto the PR that deletes the final offender, never onto the PR that merely establishes the vocabulary.

Two things generalize past exit codes:

- **An exemption list is the defect wearing the guard's uniform.** Any time a new guard needs an allowlist to pass on the current tree, the allowlist *is* the thing the guard was supposed to abolish. Delete the instances or delay the guard; never enumerate them.
- **Check rulings against each other, not only against the code.** Amendment I drew an ownership boundary; Amendment J stepped over it two paragraphs later. Each was individually verified against `src/`. Neither was verified against the other. The same hour, the implementer made the mirror-image error — applying a correct rule (*"a call site emitting the wrong code is the bug"*) to a call site that was not his. **The rule was right and the ownership was not**, in both directions, from both people. Ownership boundaries are invisible to a diff review; they live in the ruling, and only a read of the ruling catches them.

Sibling: [[feedback_fixture_makes_guard_assertion_inert]] — there an assertion cannot go red; here a guard *can only* go red, which is the same failure of a gate to be a gate. And the companion law from the same night, which explains why nobody caught it sooner: **an instrument built to catch a failure is the most likely to contain it, because building it is exactly when you stop suspecting yourself.**
