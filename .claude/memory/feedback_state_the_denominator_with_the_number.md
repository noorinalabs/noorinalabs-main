---
name: feedback_state_the_denominator_with_the_number
description: "Two CORRECT counts under different denominators collide silently — a wrong number gets challenged, a right-under-a-different-denominator number gets absorbed. Carry the denominator in the number itself ('31 converted onto _hook_main', not '31'). More checking does not help; both parties already checked."
metadata:
  type: feedback
last_verified: 2026-08-03
---

Three collisions in a single PR review round (W29 #1330), every one of them **two accurate measurements under different denominators**:

| Collision | Denominator A | Denominator B |
|---|---|---|
| 11 vs 9 stragglers | hooks with a non-delegating `main()` | modules `_hook_modules()` flags (already drops the 2 dispatchers) |
| 33 vs 30 files | the line-count table's glob (`.claude/{hooks,lib}/*.py` minus new modules minus tests) | hooks converted onto `_hook_main` |
| two `_check_and_log` exemplars | `no_worktree_self_delete.py` | `enforce_ontology_context.py` — the diff contained the wrapper **twice**, both cites correct |

## Why this class resists the usual defence (Nino Kavtaradze)

**A wrong number gets challenged. A number that is right-under-a-different-denominator gets absorbed** — because each party can verify their own figure and then reasonably attribute the mismatch to the other's error. Both sides have done their homework, so "check more carefully" is already satisfied and produces nothing.

It is also the case where deferring to the more senior or more confident participant is **most tempting and least justified**.

## The fix is structural and costs one phrase

**Carry the denominator inside the number.** `31 converted onto _hook_main` and `34 in the line-count glob` cannot collide the way `31` and `34` can. Vigilance does not prevent this; naming does.

Note the failure survives having both numbers correct *in your own head*: the orchestrator held both, and still transmitted one under the other's denominator when relaying — which is precisely the step where the label, not the care, is what protects you.

## How to apply

- **Never relay a bare count between two people who measured different things.** Restate the population as part of the number.
- **When two counts disagree, the first hypothesis is different denominators, not error.** Reconcile by deriving the difference (`11 = 9 + dispatcher + post_dispatcher`) rather than by re-measuring — if the delta has a clean explanation, both were right.
- **Put the reconciliation in the written artifact**, not just the conversation. An implementer who sees two numbers in a thread and no reconciliation will pick one and move on, and there is a 50% chance it is the wrong one for their purpose.
- **Derive populations mechanically and state the predicate.** "Modules in `_hook_modules()` that define a top-level `main()`" is a denominator; "the hooks that still need converting" is not.

**Why:** the collision is invisible from inside either party's own verification, so it is not caught by doing the verification better. It is caught by making the two measurements non-comparable on their face.

Related: [[feedback_prose_guarantee_vs_mechanism]] (same round; a claim never traced to its mechanism), [[feedback_pr_body_table_is_a_claim]], [[feedback_honest_audit_over_conclusion_claim]].
