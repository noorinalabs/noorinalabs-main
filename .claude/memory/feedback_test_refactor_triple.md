---
name: feedback_test_refactor_triple
description: "For ANY test refactor, three mechanical checks must all be unmoved: collected count + node-ID identity + per-file assertion density. The count alone is preserved by a refactor that keeps the functions and guts the bodies; assertion density is what falsifies that directly. Cheap enough (~1 min, three AST/collection passes) to be non-negotiable."
metadata:
  type: feedback
last_verified: 2026-08-03
---

Derived by Aino Virtanen at the W29 #1333 (G4) merge gate, then made a hard requirement for #1117 (G5).

## The instrument

| # | Check | What it catches that the previous one doesn't |
|---|---|---|
| 1 | **Collected count** identical before/after | gross loss of tests |
| 2 | **Sorted node-ID list diffs clean** | a test renamed, dropped and replaced, or silently re-parametrised — count-preserving |
| 3 | **Per-file assertion density** (AST-count every `assert` + `self.assert*`) identical **per file**, not just in total | **"kept the functions, gutted the bodies"** — id- *and* count-preserving |

Measured at #1333: 2772 collected, node ids identical to base, **4282 assertions at base and 4282 at head with zero per-file differences**, across six successive heads. That is what established the refactor never weakened the suite.

**(3) is the one that matters and the one nobody runs.** A count is preserved by any refactor that keeps test *functions* while emptying them. Ids are preserved too. Only assertion density falsifies it directly — and it must be **per-file**, because a total can be held constant by adding assertions in one file while removing them in another.

## Why this is non-negotiable rather than aspirational

Three AST/collection passes, well under a minute on a ~2,800-test suite. **"The refactor was too large to check" is therefore never the reason it wasn't run** — largeness is the argument *for* running it.

## The complement it needs

The triple is necessary, not sufficient — it proves the *instrument* wasn't weakened, not that the refactor is correct. Pair it with:

- **A mutation check driven through the refactored path** — revert a real production fix and confirm the suite still goes red *via a merged/parametrised group*, not merely somewhere.
- **A standalone per-file sweep** (`pytest <one file>` for every file). An aggregate run masks import-order bugs: a file can pass only because an alphabetically-earlier file already put a directory on `sys.path`. This caught a real ordering bug at #1333 that ruff's isort autofix had introduced (moving a `sys.path` bootstrap below the import needing it), invisible in the combined run. See [[feedback_prose_guarantee_vs_mechanism]].

## The parametrisation-specific trap

Structurally identical is **not** safely mergeable. An AST normaliser that strips string constants over-groups badly — at G5 a crude pass reported one "group" of 102 members across two files, where the literal payload *was* the distinguishing feature of each test. Collapsing those keeps the case count and loses what each case pinned. Hence the standing criterion: **params keep case ids**, and per-file `--collect-only` id counts stay equal — which is exactly check (2).

## How to apply

- Run all three **before and after**, and publish both sets with the invocation used.
- Measure at the head you publish against — a number measured on an earlier tree is the recurring defect ([[feedback_state_the_denominator_with_the_number]]).
- Per-file, not aggregate, for (3).
- A reviewer should run the triple independently rather than read it; it is cheap enough that reproducing beats trusting.

**Why:** in a test refactor the deliverable and the instrument are the same artifact, so a weakened instrument reports success. Nothing in a green suite distinguishes "still tests everything" from "tests less and passes."
