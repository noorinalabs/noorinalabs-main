---
name: feedback_drop_gate_bidirectional_ab
description: A metric derived from the very signal a class of entity structurally lacks does not under-count that class — it ERASES it. A mention-weighted A/B was blind to 30.4% of the corpus and hid three separate defects that deleted the Prophet's daughter, his son, and Abu Bakr al-Siddiq. Run drop-gate A/Bs bidirectionally AND unweighted; give any Arabic name rule an Arabic reviewer.
metadata:
  type: feedback
---

**Owner-visible near-miss, 2026-07-11 (P8W24, da PR #423).** A `name_quality` scrub — the **last row** of the main#928 launch gate, with a 7.5-hour pipeline re-run waiting on it — reached "ready to merge" with: 6/6 CI green, a full local check-set green, **39 red-first tests with verbatim corpus fixtures**, a measured full-corpus A/B, and **one approving reviewer**.

It **deleted Umm Kulthum bint Muhammad — the Prophet's own daughter** — from the isnad graph (`nar:d3937f2e…`, `أم كلثوم بنت سيد البشر رسول الله`, sanadset, **`mention_count = 0`**). It also *minted* 52 new matn-fragment "narrator" nodes, the exact pollution class it existed to remove.

> **It took THREE rounds to actually fix, and the same metric hid the defect every time.** Round 1 was caught by the Arabic-lens reviewer. Her two fixes were correct — and **still deleted 44 real narrators**, because she too had measured weighted. Round 2 was caught only when the implementer was ordered to re-run the A/B **unweighted**, which surfaced `ابو بكر الصديق … خليفه رسول الله` — **Abu Bakr al-Siddiq, the first Caliph** — along with `الطيب ولد رسول الله`, **the Prophet's son**. Every victim, all three rounds, at `mention_count = 0`. **The blind spot is 45,613 of 150,187 rows — 30.4% of the corpus.** Not a tail. Nearly a third of the table, and exactly the third where the Prophet's family and the Rightly-Guided Caliphs live.

> **A footnote that is itself the lesson twice over.** The reviewer's write-up named a *second* victim — Umm Ayman, `أم أيمن حاضنة رسول الله`. The implementer checked, and **that row is not attested in the artifact**: zero rows contain `حاضنة`. He declined to write a test asserting on it, because a fixture for a row that does not exist is an **inert assertion** — the precise failure mode the suite exists to prevent. The mechanism is real and Umm Kulthum is the attested victim; the phantom example changes nothing about the finding. **Do not take even a correct reviewer's example on trust** — verify the row exists before pinning a test to it. See [[feedback_fixture_makes_guard_assertion_inert]].

Caught only by the **second reviewer, on the Arabic lens** (Sofia Cardoso), who rebuilt the author's A/B rather than reading it.

## Two independent lessons. Both are cheap. Both were skipped.

### 1. A drop-gate A/B is not valid unless it runs in BOTH directions

The author diffed rows the change **drops**. He never diffed rows it **stops dropping**.

A one-directional diff is structurally blind to the two worst outcomes of a scrub:
- a real entity that the new rule **deletes** (precision regression), and
- pollution that the new rule **resurrects** (recall regression).

Both were present. Neither was visible.

| | rows dropped | new pollution **kept** |
|---|---|---|
| PR as-is | 751 / 1,268 mentions | **52 rows / 68 mentions** |
| PR + fixes | 749 / 1,266 mentions | **0** |

The drop-count barely moved (751 → 749). **The headline metric was ~unchanged while the PR was deleting the Prophet's daughter.** A summary statistic that moves by 0.3% can hide a categorical error.

**How to apply:** for ANY change to a drop/scrub/filter gate, diff the drop-set **both ways** against the full corpus — `main`-drops-minus-PR-drops AND PR-drops-minus-`main`-drops — and inspect *both* sets by hand. Put both in the PR body. `sibling of [[feedback_silent_zero_is_not_a_measurement]]`: the number you were watching is not the number that would have told you.

### 1b. …and it must be run UNWEIGHTED, not just weighted. This is why the worst defect was invisible.

The bidirectional diff explains the 52 resurrected matn nodes. **It does not explain how Umm Kulthum was missed** — a *second* reviewer (Ivana Horvat) ran her own bidirectional A/B **and** a 40-name adversarial battery of real narrators carrying Prophet references (`فاطمه بنت رسول الله`, `عاءشه زوج النبي`, `ثوبان مولى رسول الله`) and **still did not find her**.

The actual cause (Sofia Cardoso):

> **bio-promoted rows have `mention_count = 0`, and the A/B was mention-weighted — a zero is not evidence of absence.**

A mention-weighted metric makes every **bio-promoted** narrator **structurally invisible**. And bio-promoted rows are exactly where the Prophet's family lives — they are attested in biographical dictionaries, not in chains, so they carry no mentions *by construction*. The evidence could not see the entities it was most important not to delete.

**The sharpest statement of the lesson** (Kwesi Boateng, after the unweighted run found Abu Bakr):

> **A metric derived from the very signal a class of entity structurally lacks does not under-count that class — it *erases* it.**
>
> Three defects, one metric.

**How to apply:** any corpus A/B over an entity table must be run **row-level (unweighted)** as well as weighted. **A zero-weight row is not a zero-importance row.** Ask of any metric: *which rows does it assign zero, and are they zero because they don't matter — or because they don't participate in the thing I'm counting?* If the latter, the metric cannot see them **at any sample size**, and no amount of care in reading it will help.

> ### The correction that makes this lesson actually work (Ivana Horvat)
>
> **"Run it unweighted" is necessary but it is NOT the operative instruction**, and read carelessly it becomes *"add zero-mention names to your battery"* — **which would not have worked.**
>
> > Even unweighted, every name in my 40-name adversarial battery survives at the bad head. My battery had no `أم`-leading name whose role-noun isn't a connector, **because I didn't know that was the shape that mattered.** A synthetic battery can only hold counterexamples you already thought of, and this was a **premise error**. What catches it is the corpus Direction-A diff, **sliced at zero mentions and read row by row**: 44 rows, five minutes. **I reached for a battery instead of reading the diff.**
>
> **A battery tests your imagination. A diff tests the corpus.** For a premise error — where the bug is in what you *believe about the domain*, not in what you coded — a curated adversarial set is structurally incapable of finding it, because you build the set out of the same wrong premise. The operative instruction is therefore:
>
> **Diff against the real corpus, slice the diff by the dimension your metric is blind to, and READ THE ROWS.** Not sample them, not count them — read them. The set that mattered here was 44 rows and took five minutes.

The scale here is the part to remember: **the invisible class was 30.4% of the corpus.** Everyone involved — implementer, two reviewers, and me — reasoned about it as an edge case, because a weighted view is what we all had.

This is [[feedback_silent_zero_is_not_a_measurement]] in its purest form: the zero was not a finding, it was a blind spot.

### 1c. The premise error was bigger than the instance — *rijal biography and narration-provenance are the same shape*

Even after the homograph fix (§2), the rule still deleted 44 Companions. The deeper cause:

> **A companion's biography mentions the Prophet by nature.** `شهد النبي في حجة الوداع` ("he witnessed the Prophet at the Farewell Pilgrimage"), `وفد على رسول الله` ("he came as a delegate to the Messenger of Allah"), `خليفه رسول الله` ("Successor of the Messenger of Allah"). Each is a **Prophet reference + a preposition** — which to an `any()`-based rule is **structurally identical to a narration-provenance fragment**.

There is no token-level discriminator between "this text is provenance cruft" and "this text is why the person is famous." The fix was to stop looking for one: scope the rule **all-residue** — fire only when *every* token is a function word or part of the Prophet reference — reusing the one shape in the module already proven safe, rather than inventing a new discriminator under gate pressure.

**How to apply:** when a drop-rule keeps needing new exceptions, the exceptions are not the bug — **the discriminator is**. Stop patching and ask whether the two classes are separable *at all* on the features you have. Prefer narrowing a rule to a provably-safe shape over widening its exception list.

And the resulting trade is the right one, stated for reuse: **pollution left in is recoverable; a deleted entity is not.** The implementer deliberately *inverted one of his own passing tests* — letting `كمن زار رسول الله` survive — because the rule that dropped it also dropped `وفد على رسول الله`, which names a real Companion. Closing 73% of the mentions instead of 98% was the correct price. **A gate should fail toward the recoverable error.**

### 2. An Arabic name rule needs an Arabic reviewer. This is not a formality.

The defect is **invisible in English and invisible to the tests**:

> `أم` (*umm*), the commonest female kunya connector, normalizes to `ام` — **homographic with the disjunctive particle** `أم` ("or"), which is in `_MATN_PARTICLES`. It is the **only** token in the codebase that is both an apposition connector and a matn particle.

So any narrator shaped `أم X <role> رسول الله` whose role-noun was not already in `_APPOSITION_CONNECTORS` was read as "Prophet reference + particle" and dropped. **`أم سلمة` survived only by luck** — `زوج` happens to be an apposition connector. Umm Ayman's `حاضنة` is not, so she did not.

The author's stated discriminator — *"a real narrator carries zero particles"* — is simply **false in Arabic**. No amount of test coverage finds that; it is a premise error, and only a domain-language reader can see it. The English-lens reviewer (a strong one) **approved**.

**How to apply:** any rule that classifies, drops, merges or renames **Arabic names** gets a reviewer who reads Arabic, as one of the two. Assign the second reviewer for *lens diversity*, not just for a second pair of eyes — two reviewers with the same lens is one reviewer. And when a discriminator is stated in natural language ("a real narrator carries zero particles"), treat that sentence as a **claim about the language** and make someone who speaks it check the claim.

### Corollary — a fixture set can be uniformly biased

All four of the author's oath fixtures **led** with the oath, so they only ever exercised the drop path of a function with *dual* semantics (boundary at index 0 → drop the span; index > 0 → truncate and keep the head). In the real corpus the oath is overwhelmingly **mid-matn**. The untested branch was the one that shipped the bug.

Verbatim corpus fixtures are necessary but **not sufficient** — they must also *span the positional/structural variants* the production data actually contains. Ask of any fixture set: *which branch does none of these reach?*

## Cross-references
- **Retraction this memory canonicalizes:** the 2026-07-02 prod-quality snapshot memory (`project_prod_loaded_quality_broken`, retired to git history; #723 CLOSED 07-05) advised *"weight by mention_count"* as a measurement axis. That advice is **RETRACTED** — it is precisely what hid these deletions. Weighting is sound for *triage priority* only; **measure unweighted**.
- [[feedback_silent_zero_is_not_a_measurement]] — verify the instrument separates the classes before reading the number; here the *metric itself* was the wrong axis.
- [[feedback_fixture_makes_guard_assertion_inert]] — a fixture set that cannot reach the branch proves nothing about it.
- [[feedback_review_against_artifact]] — Sofia rebuilt the A/B rather than reading the PR body's table. That is why she found it.
