---
name: feedback_equivalent_mutant_is_not_an_inert_test
description: "A mutant that survives may be semantically EQUIVALENT to the original — the test suite is not inert, the edit simply changed nothing. Probe the mutated function directly before concluding a guard is untested."
metadata:
  type: feedback
last_verified: 2026-08-03
---

This org treats a surviving mutant as evidence a guard is untested. Usually correct — but there is a second explanation that looks identical from the outside: **the mutation produced a semantically equivalent program.** Nothing changed, so nothing could fail. That is a fact about the *edit*, not about the suite.

The two are indistinguishable from the test output alone. Both read as "mutant survived."

## The instance (W29, PR #1302, found by Weronika Zielinska against her reviewer's finding)

A merge-gate reviewer reported that mutating a variable-reference regex from `\w*` to `\w*?` **corrupts the resolver** (`$gone` → `gitone`, `$g_2` → `git_2`) while all 16 tests pass — filed as an inert-assertion block.

The conclusion was right and the demonstration was wrong. The pattern ends in `\b`, and **a trailing word boundary forces lazy and greedy quantifiers to expand identically** — so `\w*?` alone is an equivalent mutant and corrupts nothing. She established this by probing the real function rather than reasoning about the regex. The genuinely corrupting mutation needs **both** the lazy quantifier **and** the dropped `\b`.

**Why the distinction is load-bearing rather than pedantic:** the block was legitimate — `resolve_simple_assignments` was a new public helper with no direct unit test, and `check()`-verdict-level tests structurally cannot observe resolver corruption (a corrupted name is rejected downstream anyway, so the verdict is unchanged). But had the *stated* mutant been left in the record, the next person reproducing it would watch it survive **after** the tests were added, and conclude the new tests were inert. A wrong repro attached to a right finding manufactures a false negative for whoever checks it next.

## How to apply

- **Before filing "mutant survived → guard untested", probe the mutated function directly** on an input that should differ. If the output is identical, you have an equivalent mutant, not a coverage gap.
- Regex mutations are the richest source: anchors (`\b`, `^`, `$`), greedy↔lazy under a following anchor, `+` vs `*` where the first character is separately required, redundant character classes. Many are equivalent by construction.
- **When a reviewer's repro turns out equivalent, correct the repro and keep the finding** if it stands on other grounds — and say both, so the record does not read as the finding being withdrawn.
- Reaching a corrupting mutation may take **combining** edits (here: lazy quantifier *and* dropped anchor). A single-edit mutation surviving is weak evidence; combined-edit surviving is stronger.

**Why:** the failure is self-concealing in the flattering direction. "Mutant survived" prompts work — adding tests — and the work is usually right, so nobody re-examines the premise. It only surfaces when someone re-runs the stated mutant against the fixed suite and gets a confusing answer.

Related: [[feedback_both_ends_tested_join_untested]] (mutate the plumbing, not just the logic), [[feedback_corpus_misses_its_constant_dimension]] (green proves only what varied), [[feedback_pr_body_table_is_a_claim]] (a mutation table is a claim requiring the same verify-before-claim discipline).
