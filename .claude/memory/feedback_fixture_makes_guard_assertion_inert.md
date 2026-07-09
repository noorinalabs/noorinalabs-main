---
name: feedback_fixture_makes_guard_assertion_inert
description: "A negative-guard assertion (`assert not id.startswith(BAD_PREFIX)`) is only meaningful if some fixture in the suite CAN produce BAD_PREFIX. An unrealistic fixture silently renders the guard structurally unreachable — it sits green forever while the defect it names runs in production."
metadata:
  type: feedback
---

**An assertion about a value the fixture cannot produce is not a test. It is a comment that costs CI time.**

Found 2026-07-09 while fixing da#353. `tests/integration/test_sanadset_lightup.py` contained, at line 135:

```python
assert not any(h["id"].startswith("hdt:sanadset:sanadset:") for h in hadiths)
```

A direct guard against the doubled-corpus-prefix defect of `main#139` / `ig#63` / da#353. But line 62 wrote the fixture as **`bukhari.csv`**. The sanadset parser derives its fallback collection name from the *CSV stem*, so the ids were `sanadset:bukhari:…`; a doubled `sanadset:sanadset:` was **structurally unreachable**. The assertion sat green and inert in the integration suite for months **while the production corpus emitted the doubled form 16,000,000+ times per load**.

The same test's `assert len(collections) == 1` was worse than inert: it passed *because* of the fallback it should have been guarding against, measuring the bug while its own docstring claimed to verify the Collection was "emitted by the REAL parser path — NOT fabricated out of band." With a realistic fixture the same three rows yield **two** Collections.

Both assertions only became real checks once the fixture used the production filename and header. Two sibling fixtures in the same repo (`test_pathb_integration_verify.py`, `tests/conftest.py::sample_sanadset_csv`) invented the header `hadith_id,book_id,hadith,grade`, which exists in no edition of the corpus. The conftest one had **no callers**, so no CI signal could ever reach it — a loaded gun for the next author, found only by an explicit grep sweep.

**Three distinct failure modes, worth separating** (da#358 records the correction; an early claim conflated them):
- **Pinning the bug** — `test_sanadset_lightup`'s `assert len(collections) == 1` was *correct only for a corpus that had lost its breadth*. The test asserted the defect. This is the genuine wrong-reason pass.
- **Inert guard** — the same file's `assert not id.startswith("hdt:sanadset:sanadset:")` could never fire, because the fixture was named `bukhari.csv`.
- **Tautology** — `test_pathb_integration_verify` asserted `assert emitted` + endpoint-membership, which hold trivially under collapse. Its breadth claim lived only in a **comment**, never an assertion. It did not pass for the wrong reason; it never made the claim.
- (And `test_real_data_flow` asserted only that outputs appeared — it claimed nothing.)

When auditing "what does this test now prove," distinguish these: only the first is a test that was actively lying.

**Fourth mode — the tautological loop over the source-of-truth collection (2026-07-09, da#363).** `_fold_token`'s accusative-stem rule folds a 25-stem closed lexicon `_ACCUSATIVE_STEMS`. Every existing fold test was negative-direction (`test_hazards_are_not_folded`) or idempotence-only, **both of which the rule's *absence* satisfies** — `canonical_surface("عليا")` is a fixed point whether it folds or does nothing. So deleting the rule outright left **30/30 green**. The fix was six hand-written literal pairs; deleting the rule now reds 6.

The trap is what came next. The obvious way to cover the remaining nineteen stems is a loop:

```python
for stem in _ACCUSATIVE_STEMS:                       # INERT
    assert make_canonical_id(stem + "ا") == make_canonical_id(stem)
```

Tested under a stem-removal mutant (`محمد` deleted from `_ACCUSATIVE_STEMS`): **36 passed, survives.** Iterating the collection under test is a **tautology against removal** — the deleted stem is no longer in the set being iterated, so the loop checks zero unfolded stems and passes. It would have *looked* like stronger coverage than six literals while pinning nothing at all.

**The reflex to replace N literals with a loop over the source-of-truth collection is usually right, and is exactly wrong when the collection is the thing under test.** The literal list is not duplication; the literals *are* the independent statement of intent. A test may not derive its expectations from the datum it is testing — that is [[feedback_sweep_expensive_stage_before_launch]]'s "a gate downstream of a defect is not a gate," transposed into a test file.

Corollary for reviewers: a mutation test must delete a **member** of the lexicon, not just the branch that consumes it. Deleting the branch reds any one case; deleting a member reds only a case that names that member. The two mutants prove different things and only the second measures coverage of the data.

**Why:** a fixture differs from production along many dimensions (filename, header, encoding, ordering, cardinality). If it differs along **the one dimension the assertion tests**, the assertion is unreachable. Nothing warns you: the test passes, the coverage counter increments, the reviewer sees a guard and moves on. Realism is not a stylistic preference for fixtures — for a negative-guard assertion, it is the difference between a test and a decoration.

Note the parser's *own* guard (`_process_chunk` raising on a missing `Book` column) only trips for fixtures that are actually **used**. It cannot see the unreferenced one. Runtime guards do not substitute for a lint gate.

**How to apply:**
- Writing `assert not <output>.startswith(BAD)` / `assert BAD not in <output>`? **First make a fixture that produces `BAD`, watch the assertion fail, then fix the fixture.** If you cannot make it fail, it is testing nothing. Same discipline as [[feedback_passing_repro_masks_bug]] (a repro that never goes red) and [[feedback_test_mock_masks_prod_failure]].
- **Copy the production filename and header verbatim** into any fixture for a parser that keys on either. The stem, the column names, and the column *spelling* are inputs, not decoration. `Book` vs `book_id` was the whole of da#353.
- When a regression test depends on a subtle fixture property, **say so in the docstring** so nobody "simplifies" it away. (da#353's `TestBooksCsvAbsentIdentity` deliberately reuses `Num_hadith` across two books so the ids collide under the old code; with globally-unique ordinals it proves nothing.)
- **Never iterate the collection under test to generate its own expectations.** `for x in THE_LEXICON: assert folds(x)` cannot fail when a member is removed from `THE_LEXICON`. Write the literals. Then mutate by **deleting a member**, not only by deleting the branch that reads it.
- **Sweep for unreferenced fixtures.** A fixture with no callers is invisible to CI and will be trusted by the next person who wires it up.
- Beware the inverse of the [[feedback_silent_zero_is_not_a_measurement]] rule: there, a probe could not return nonzero; here, an assertion could not go red. Same root — **verify the instrument before trusting the reading.**

`.claude/lib/check_fixture_realism.py` lints Arabic *text* realism (vocalization, the `عن` particle) and cannot see this: the Arabic inside these fixtures was fine, the **schema** was fiction. Extending it with a schema/filename lens is **main#927**. Its own docstring already opens with "the fixture-masks-bug class recurred 5+ times — most damningly inside its own fix"; today added three more.
