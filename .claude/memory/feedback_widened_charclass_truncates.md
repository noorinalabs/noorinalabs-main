---
name: feedback_widened_charclass_truncates
description: "Widening a separator character class can make a parser silently TRUNCATE rather than return None — and a same-initial hyphenated/unhyphenated roster pair turns that truncation into an unblockable false BLOCK on an identity gate."
metadata:
  type: feedback
last_verified: 2026-08-03
---

When a regex separator class is widened (`/` → `[-/]`) and the captured field can itself contain the new separator, the parser does **not** fail on the ambiguous input — it **succeeds with a truncated value**. That is far more dangerous than returning `None`, because `None` is a case every caller already handles and a truncation is a plausible-looking answer nothing checks.

## The live instance (W29, PR #1269 / #1175, found by Weronika Zielinska at the merge gate)

Consolidating two drifted copies of `extract_branch_author_lastname` into `charter_trailer.py` standardised on `([A-Za-z])\.([A-Za-z]+)[-/]`. On `K.Mensah-Williams/0001-x` the surname's own `-` satisfies `[-/]`, so the match succeeds and yields **`Mensah`**.

**`Kofi Mensah` (design-system) and `Kofi Mensah-Williams` (landing-page) are two distinct people in the parent union roster with the same first initial.** Measured through the real `check()`:

| scenario on `K.Mensah-Williams/0001-…` | `origin/main` | PR head |
|---|---|---|
| Kofi Mensah posts a **correct** verdict | allow + warning | **BLOCK** |
| a **genuinely swapped** verdict | allow + warning | allow (silent) |

The hook inverted — fail-closed and fail-open **at the same time**. An unblockable false BLOCK of a *correct* reviewer is the class #1172 exists to eliminate and #934 had already fixed once. Blast radius was 65 open branches across 4 child repos, on **both** separators.

## Three things to carry from it

1. **A silent allow is degraded advice; an unblockable false BLOCK is an outage.** The first is arguably tolerable as tracked debt. The second must land in the PR that creates it. Grade the two directions separately instead of averaging them into "the parser is wrong."
2. **Prefer a separator rule that fails safe over a wider charset.** `([A-Za-z][A-Za-z'-]*)[-/]` is greedy across the separator and mis-parses `A.Virtanen-branch-name-with-no-number` → `Virtanen-branch-name-with-no`. `([A-Za-z][A-Za-z'-]*?)(?:/|-(?=\d))` — non-greedy, requiring a digit after the dash — returns `None` on genuine ambiguity.
3. **An identical pass count across candidate implementations means the suite does not pin the axis.** All three charsets scored exactly `420 passed`, because the suite contained **no hyphenated-surname fixture at all**. Equal scores read as "no regression" and actually mean "not measured" — the [[feedback_corpus_misses_its_constant_dimension]] shape again, at charset granularity.

**How to apply:** before widening a separator class, ask whether the *captured* field can contain the new separator; if it can, enumerate real values that do (here: the roster's 8 hyphenated surnames, one of which — `Méndez-Ríos` — is also non-ASCII and excluded by `[A-Za-z]` regardless). Then check for **collisions between a truncated value and a real distinct entity**, which is what converts a parsing bug into an identity-gate failure.

Related: [[feedback_pr_review_verdict_format]] (the gate this bit), [[feedback_corpus_misses_its_constant_dimension]] (equal scores = unmeasured axis), [[feedback_silent_zero_is_not_a_measurement]] (a plausible wrong answer beats no answer at hiding).
