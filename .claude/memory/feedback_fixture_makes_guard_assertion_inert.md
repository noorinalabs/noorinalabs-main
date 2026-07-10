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

Corollary for reviewers: a mutation test needs **three** mutants, not two — delete the **branch**, delete a **member**, and **replace a member**. Deleting the branch reds any one case. Deleting a member reds only a case that names that member. **Replacing a member is the one that separates a cardinality guard from a membership guard**, and it is the mutant everyone forgets.

Confirmed independently the same night: a second reviewer dropped `سعد` — one of the 19 stems the six literals do *not* name — and **all 36 tests still passed** while `canonical_surface("سعدا")` silently stopped folding. **The guard pins the rule, not the lexicon.** Six literals prove the branch exists and reaches identity; they say nothing about the other nineteen entries.

The cheap complement, which the loop cannot give you: **pin the collection itself, by equality — not by cardinality.**

An earlier draft of this memory proposed `assert len(_ACCUSATIVE_STEMS) == 25` and claimed it "asserts membership." **It does not. It asserts count**, and the two come apart on the mutant that matters (found by Wanjiku Mwangi reviewing this very amendment, 2026-07-09):

```
baseline                       green
REMOVAL       (len 24)         RED      <- cardinality works
SUBSTITUTION  (len 25)         green    <- cardinality BLIND; the six literals don't name it
frozenset equality             RED      <- catches it
```

Swap `سعد` for a typo of `سعد` and the count is unchanged, the six literals stay green, and `canonical_surface("سعدا")` silently stops folding — **the exact defect the amendment was written to catch, one keystroke from the mutant it does catch.** The corollary above anticipated substitution; the remedy under-delivered on it.

Same length, strictly stronger, and it is this file's own doctrine that *the literals are the independent statement of intent*:

```python
assert _ACCUSATIVE_STEMS == frozenset({...25 literals...})   # reds on removal, addition, AND substitution
```

Literals assert *behaviour* for the members that matter; a frozenset equality asserts *membership* for all of them. Together they cover what the tautological loop only appeared to. **Note that the wrong complement shipped inside the memory warning against inert assertions — and it was caught by a reviewer running the mutant, not by its author re-reading it.**

**Fifth mode — the fixture that cannot occur in production (2026-07-09, da#359).** The four modes above are all one sign of one error: *an assertion that cannot fail.* There is a mirror, and it is invisible from that side.

Alejandra Reyes-Fuentes, checking a claim that was **in her favour** (always the least-checked kind), found that `pa.table({"source_id": [None]}, schema=HADITH_SCHEMA)` **accepts a null into a `not null` field**, and `table.validate(full=True)` **passes**. Enforcement lives one call deeper — `pq.write_table` raises `ArrowInvalid`, `table.cast(schema)` raises `ValueError`. Both are on the production write path.

Consequence: **a fixture that builds a table in memory and hands it straight to a loader exercises a branch production can never reach.** The test is green, the branch is covered, the coverage counter increments — and the state it proves the code handles cannot arrive through any on-disk parquet. Nothing warns you. It is not a test that passes for the wrong reason; it is a test of a reality that does not exist.

**The paired law** (Oyunbileg Batbayar's phrasing):

> **An assertion that cannot fail proves nothing. A fixture that cannot occur proves nothing about production.** Same family, opposite sign.

We had been hunting only the first sign all night. The second has a specific corollary for mutation testing: killing a mutant on an early-return path proves the **return** is reachable from the test, **not** that the *input shape* which reaches it is reachable from production. Say which one you proved.

The practical check: **construct the bad value the way production constructs it** — through the writer, the parser, the wire — not through the in-memory constructor that skips the schema enforcement. If the only way to build your fixture is an API production never calls, the fixture is fiction.

## The law under all of it: a green check must first prove it can go red

Four instruments passed for the wrong reason on 2026-07-09, in one evening, across five PRs:

| instrument | why it was green |
|---|---|
| a probe patching `save_manifest` globally | it raised *before* the load, so `rc=1` looked consistent with the invariant |
| an `rc` probe | it crashed on a bad kwarg before reaching the code under test |
| a mutation | the pattern never matched; the file was unchanged; `19 passed` |
| `pytest -k sole_declarer` vs `TestRegistryIsTheSoleDeclarer` | `-k` is case-sensitive; **0 tests collected**; pytest prints a pass and returns `rc=5` |

**Every one of them was green. Not one announced itself.** The last nearly produced *"all ten forms caught"* from ten runs in which zero tests executed — reported to the author of the guard, about the guard protecting the reporter's own PR.

> **An instrument that agrees with you on the first try has not been tested.**

Three of the four were caught by the person who built the instrument, before anyone else saw the result, using one reflex: *a mutation that changes nothing is not a mutation; a filter that selects nothing is not a filter; a probe that never reaches the code is not a probe.*

**Operationally, for every check you are about to believe:**
- **Prove it red first.** Plant the defect, watch it fail, then remove the plant.
- **Assert the plant applied** — hash or `grep` the file before and after. An unapplied mutation and a surviving mutant are the same green.
- **Assert the check ran** — a non-zero collected count, and the process exit status. `pytest` returns `5` (`EXIT_NOTESTSCOLLECTED`) when a selector matches nothing, and that signal is free.
- **Isolate the thing under test to exactly one occurrence, and prove the fixture does not already satisfy the question.** A probe for "does the scan see `EXIT_AUG += 1`?" written as
  ```python
  EXIT_AUG = 6      # setup
  EXIT_AUG += 1     # the thing under test
  ```
  reports **SEEN** — from the setup line's plain `Assign`, not from the `+=`. **The setup line answered the question the assertion claims to answer.** Nothing in the output distinguishes them. Not an assertion that cannot fail: a fixture whose *precondition* already contains the property. (2026-07-09, da#387 — found by its author, inside a probe written to expose exactly this class.)
- **This binds the author of a criterion hardest.** Proposing an acceptance item that cannot fail is the same defect as writing an assertion that cannot fail — and it is harder to see, because nobody runs a criterion. (2026-07-09, da#387: an "every namer imports the registry" obligation, retracted by its author on testing it — a module naming an un-imported `EXIT_*` raises `NameError`, so the assertion could never fail.)

**And the sharpening that matters most** (Oyunbileg Batbayar): *an instrument built to catch this failure is the **most** likely to contain it, because building it is exactly when you stop suspecting yourself.* Five of the six instances below were found inside work whose subject was inert guards.

**Beware "complete for the set I was handed."** Twice on 2026-07-09 a table of forms was reported as exhaustive when it enumerated only the forms someone else had listed: a mutation table, and an AST-form table that named two blind spots where **six** existed (tuple unpack, walrus, starred, `AugAssign`, `for` target, `with` target — all invisible to a scan that inspects `Assign.targets` / `AnnAssign.target` for an `ast.Name`). **The fix in both cases was to stop enumerating node types and ask the language**: walk for an `ast.Name` in `Store` context; enumerate members through the `enum` API. **A hand-maintained list of node types is the same defect as a hand-maintained list of reserved values** — it was the last one hiding inside the fix for hand-maintained lists.

**Why:** a fixture differs from production along many dimensions (filename, header, encoding, ordering, cardinality). If it differs along **the one dimension the assertion tests**, the assertion is unreachable. Nothing warns you: the test passes, the coverage counter increments, the reviewer sees a guard and moves on. Realism is not a stylistic preference for fixtures — for a negative-guard assertion, it is the difference between a test and a decoration.

Note the parser's *own* guard (`_process_chunk` raising on a missing `Book` column) only trips for fixtures that are actually **used**. It cannot see the unreferenced one. Runtime guards do not substitute for a lint gate.

**How to apply:**
- Writing `assert not <output>.startswith(BAD)` / `assert BAD not in <output>`? **First make a fixture that produces `BAD`, watch the assertion fail, then fix the fixture.** If you cannot make it fail, it is testing nothing. Same discipline as [[feedback_passing_repro_masks_bug]] (a repro that never goes red) and [[feedback_test_mock_masks_prod_failure]].
- **Copy the production filename and header verbatim** into any fixture for a parser that keys on either. The stem, the column names, and the column *spelling* are inputs, not decoration. `Book` vs `book_id` was the whole of da#353.
- When a regression test depends on a subtle fixture property, **say so in the docstring** so nobody "simplifies" it away. (da#353's `TestBooksCsvAbsentIdentity` deliberately reuses `Num_hadith` across two books so the ids collide under the old code; with globally-unique ordinals it proves nothing.)
- **Never iterate the collection under test to generate its own expectations.** `for x in THE_LEXICON: assert folds(x)` cannot fail when a member is removed from `THE_LEXICON`. Write the literals. Then mutate by **deleting a member**, not only by deleting the branch that reads it.
- **Sweep for unreferenced fixtures.** A fixture with no callers is invisible to CI and will be trusted by the next person who wires it up.
- **Build the bad value the way production builds it.** An in-memory constructor that skips the writer's schema enforcement (`pa.table(..., schema=...)` admits a null into a `not null` field; `validate(full=True)` does not catch it) yields a fixture for a state no on-disk artifact can hold. **A green test over an unreachable state is the mirror of an assertion that can never go red.** When you kill a mutant on an early-return path, say whether you proved the *return* reachable or the *input shape* reachable — they are different claims.
- **"Does not occur" and "cannot occur" are different claims, and only the second makes an assertion inert.** A fixture for a shape no artifact *currently* holds, on a path production *can* reach, pins **a reachable path with no current instance** — strictly stronger than a contract guard, strictly weaker than evidence of production use. Say which of the three you are claiming. (Kwesi Boateng, da#383: a reviewer argued a colon-prose fixture was unreachable "by construction" because its only caller feeds an Arabic-normalized field; he measured, and **24,326/24,326 kaggle bio rows in that field carry Latin script**. Absent from the corpus, not excluded by the type. One colon-joined row and the cut fires in production, through the only call site there is.)
- **When you certify which rows are off-disk, you have certified every row you did not name.** A partial provenance label is worse than none: it licenses the reader to infer that the rows it omits *are* attested. A claim about a **set**, written while looking at one member.
- **Write the mutant before the assertion.** Not after, when the assertion is already green and mutating it feels like a formality. (Nikolaos Papadopoulos's own diagnosis of four wrong-reason greens: *"I was fastest to reach for a check when I was most confident of the answer."*) The ordering is what forces the mutant to have something to bite: a test written mutant-first cannot accidentally verify a *different object* than the one under test — as `test_the_decorator_is_actually_applied` did, building its own `IntEnum`, applying `enum.unique` to **that**, and asserting it raised. It would have passed if `ExitCode` had no decorator, no members, and lived in another repository. **A verified plant into an unverified subject.**
- **An unapplied mutation and a broken check are the same green, and they point in opposite directions.** Isolation and plant-applied assertions defend against the *comfortable* green — an author wanting a pass. Nothing defends against the **convenient** one: a reviewer whose contaminated mutant makes a correct guard look inert, manufacturing a finding. *Assert the fixture is what you think it is before reading anything into the result — including when the result is the one you were hoping for.* A reviewer hunting a blocker is exactly as motivated as an author hunting a pass. (Oyunbileg Batbayar, 2026-07-09, who caught it in her own probe.)
- Beware the inverse of the [[feedback_silent_zero_is_not_a_measurement]] rule: there, a probe could not return nonzero; here, an assertion could not go red. Same root — **verify the instrument before trusting the reading.**

`.claude/lib/check_fixture_realism.py` lints Arabic *text* realism (vocalization, the `عن` particle) and cannot see this: the Arabic inside these fixtures was fine, the **schema** was fiction. Extending it with a schema/filename lens is **main#927**. Its own docstring already opens with "the fixture-masks-bug class recurred 5+ times — most damningly inside its own fix"; today added three more.
