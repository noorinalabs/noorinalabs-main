---
name: feedback_both_ends_tested_join_untested
description: "A value produced in one function and consumed in another can have BOTH ends thoroughly tested while the join between them is untested — deleting the hand-off passes the whole suite. Also: a fixture that REPLACES an adapter can never test that adapter."
metadata:
  type: feedback
last_verified: 2026-08-03
---

Coverage is usually reasoned about per-function. The gap this note is about lives **between** functions: a value produced by `A`, consumed by `B`, with `A`-produces-it and `B`-handles-it both tested, and **nothing asserting it travels from `A` to `B`**. Deleting the hand-off line is invisible to the entire suite.

## The instance (W29, PR #1295, found by Weronika Zielinska at the merge gate)

A base-image pin-drift sweep whose whole purpose is *"a registry we cannot reach must report UNKNOWN, never no-drift."* Deleting one line from `sweep()` —

```python
unknown.extend(drift_unknown)
```

— left **75/75 tests passing** while a total registry outage rendered as:

```
No base-image pin drift over threshold as of 2026-08-03T15:02:19Z.
```

`compute_drift` producing unknowns: tested. `render_check` warning on unknowns: tested. The join: nothing. The single sweep-level unknown test filtered on `kind=="file"`, appended directly in `sweep()` and never routed through `compute_drift` — so the entire registry half of the unknown path had no end-to-end assertion. Five *other* false-clean mutants she tried were correctly killed; only the join survived.

**The author's mutation table had 16 rows and did not contain this one**, because mutation testing tends to target logic inside functions, not the plumbing between them.

## The sibling failure: a fixture that replaces the adapter cannot test the adapter

The same PR's `FakeHttp` substituted for `default_http_get` wholesale, so no test ever exercised the only real-network code path. The reviewer stood up a real `http.server` on a real socket and rewrote only the https→http scheme for loopback — and through *that* path verified all 13 degradation modes. A previously-fixed bug in that adapter (Docker Hub returns a **lowercase** `www-authenticate`; a case-sensitive lookup silently 401'd every real pin) had been caught by luck, not by the suite.

**Substituting a component is how you test its callers; it is never how you test the component.** If the seam you mock is the only place a class of bug can live, mocking it guarantees the suite cannot see that class.

## How to apply

- When a property is stated end-to-end (*"an unreachable registry reports UNKNOWN"*), the test must be **end-to-end**. Per-stage tests of the same property are necessary and not sufficient.
- **Mutate the plumbing, not just the logic.** Delete each hand-off — `x.extend(y)`, `return`ing a collected list, passing a field into a constructor — and see if anything goes red. This is the class an ordinary mutation table misses.
- **A test written in response to a surviving mutant is the one most worth re-verifying.** Two such tests this same wave initially failed to fire (a whole-stream `assertIn` that another row satisfied; an `elif` that still executes when only one of two counters is non-zero).
- For any adapter you routinely fake, keep **one** test that drives the real thing against a local server/fixture process. Otherwise the adapter is permanently unmeasured.

**Why:** both this and the fixture case produce a suite that is *large and green* — 75 tests here — which is precisely what stops anyone looking. Same family as [[feedback_silent_zero_is_not_a_measurement]] (the healthy value and the broken value are indistinguishable at the read) and [[feedback_corpus_misses_its_constant_dimension]] (green proves only what was varied), but the mechanism is **test topology** rather than value or corpus.

Related: [[feedback_mocks_mask_prod]], [[feedback_pr_body_table_is_a_claim]].
