---
name: feedback_silent_zero_is_not_a_measurement
description: "Verify the instrument before trusting the reading. Run the detector on BOTH classes and require it to separate them before reading the number you care about — a zero, a control group, and even a 10x lift are each individually insufficient."
metadata:
  type: feedback
---

**A probe that cannot fail proves nothing. A probe that can silently observe *nothing* is the same defect wearing a number.** The output `0` (or `NULL`, or empty, or exit 0 with no stdout) is only evidence when you have first established that the probe was capable of returning something else.

Four independent instances in a single session (2026-07-09), each of which nearly shipped a wrong conclusion:

1. **Glob expanded by the wrong user.** `sudo -n du -sh /var/lib/docker/containers/*/*-json.log` → `0`. The glob expanded as the unprivileged `deploy` user *before* `sudo` ran, matched nothing, and `du` summed an empty argument list. Nearly reported "docker logs are negligible." Fix: `sudo -n sh -c "du ... "` so the glob expands as root.

2. **Misspelled Neo4j property.** `RETURN count(n.betweenness)` → `0` across all 160,614 Narrator nodes. The property is `betweenness_centrality`. **Cypher has no strict-property mode**: a typo returns NULL for every row and never errors. Nearly reported "the enrich run was wiped." Fix: enumerate `keys(n)` first. See [[reference_graph_ops_cypher_shell]] §3.

3. **Query killed mid-flight, read as an answer.** `MATCH p=(n)-[:TRANSMITTED_TO*1..2]->(n) RETURN count(p)` under `timeout 600` produced **zero bytes** — not even the trailing `printf "rc=%s"` in the same shell, because SSH was killed before it ran. Read as "no cycles found," da#248 gets closed as fixed. The real population was 23,139 reciprocal pairs. Fix: always emit and check an explicit `rc=` sentinel, and treat *absence of the sentinel* as "did not complete," never as "returned nothing."

4. **Grep against an unexpected quoting.** `grep -c '^nar:' anchors.txt` → `0`. cypher-shell `--format plain` quotes string columns, so every line began with `"`. Nearly concluded the anchor fetch had failed. Fix: inspect one raw line before counting.

Adjacent, same day: `chain_integrity.cypher` reports `100 cycles` for a population of 23,139 because of an undocumented `LIMIT 100`. A gate that silently prints a constant is worse than no gate — it reads as reassurance. And `pq.read_table(..., columns=["id"])` **did** fail loudly (`ArrowInvalid: No match for FieldRef.Name(id)`, real column `canonical_id`) — the counter-example showing what a well-designed probe does with a bad name.

**The general rule, which supersedes both weaker forms below:**

> **Run the detector on BOTH classes. Require it to separate them. Only then read the number you care about.**

## The one-line form. It catches half the instances in this file. (Tomás Carvalho, 2026-07-11)

> ### **Every "all clear" must first prove it looked at something.**
> **Assert the set is non-empty AND complete BEFORE reading its verdict** — a poller, a grep, a scan, a control arm, a `Total:` line, a mutation battery. **If the probe cannot distinguish *"everything passed"* from *"I saw nothing,"* it has not reported a result.**

**On one day this single assertion would have caught five separate defects, in five different languages, committed by four different people:**

| the "all clear" | what it actually saw |
|---|---|
| `until [ pending == 0 ]` on a PR's check rollup | **an empty rollup** — checks had not yet *registered*. Gated four merges. |
| `actionlint` reported clean | **an empty file set** — run before `git add` |
| `docker run img python - <<'PY'` exited 0 | **nothing** — no `-i`, so `python -` read EOF and executed zero lines |
| a control arm "proved" the cache was live | **nothing was CACHED in that job at all** — no control |
| a `gh api` fetch returned no diff | **an empty response** — the API blipped; read as "no change" |

**And the correction that makes this usable, which is the real finding:**

> **The class was known. The instance was not recognised as an instance.** `pending == 0` **IS a silent zero** — an empty check set satisfies *"nothing pending"* exactly as well as a complete-and-passing one does. Healthy state and null state emit the identical string. **It is not a new failure mode standing beside the others; it is the same one wearing a shell loop instead of a Dockerfile.**

That is why *knowing the rule did not help*. The orchestrator had spent the day teaching this class to three engineers, the oracle (`pr_ci_state.py`) already existed, and org memory already said *"empty rollup = hard not-ready"* — **and the broken loop got written anyway, and gated real merges.** They were safe only because the checks happened to have registered before the first poll. **A fine outcome is not evidence the gate worked.**

> **At the moment you type `until [pending -eq 0]`, it does not look like the rule. It looks like a loop. RECOGNITION is the scarce thing, not knowledge.**

So the defence cannot be *"remember harder."* **It has to be mechanical, at the point of use** — which is [[feedback_enforcement_hierarchy]] (hook > skill > charter) arriving from a new direction: *a rule you must recognise an instance of is a rule that will be missed, however well you know it.* Tracked as main#957.

**Corollary, earned the same day:** **people looking hard is not a control.** Every one of the ten instances was caught by someone looking hard — and four were committed by people who were, at that moment, warning others about that exact class. *"It is a coincidence that held ten times."* (Fatima Bensalah)

Two weaker versions were tried on a single problem and each was falsified within hours.

**v1 — "can the probe return nonzero?"** Catches a probe that cannot fire. Misses one that always fires. Same day: a detector for "does this hadith's matn contain an isnad?" keyed on the Arabic tokens `عن`/`قال` called **97.2%** of a target set positive, implying ~160k recoverable chains. Those tokens saturate ordinary Arabic prose — against a **control** of rows whose matn is chain-*free* by construction the base rate is **85.6%**. Lift ≈ 1.0. The probe's answer was fixed before it saw the data.

**v2 — "always run the control group."** Catches a probe that cannot return **low**. Misses one that cannot return **high on a known positive**. Re-keying on strict isnad openers (`حدثنا`/`أخبرنا`/`سمعت`) gave **7.9%** control vs **79.2%** test — a 10× lift, a clean control, and a confident conclusion (`159,558 × 0.7922 ≈ 126,400` recoverable chains) that was **wrong twice over**. Checking *recall* against the **positive** class — the 485,285 rows known to carry an isnad — returned **0 / 485,285**, because the source strips the transmission opener from every row it successfully tags. The detector could never fire on a true positive. Opener *presence* is strong evidence; opener *absence* is none at all. So recall is not calibratable here, and the product silently assumed recall = 1 and FPR = 0.

The corrected estimate needed a detector spanning both of the corpus's **two isnad conventions** — receipt-verb (`حدثنا …`; 98.8% of `lk`) and bare-name-then-`عن` (98.5% of `tusi`, **0.0% receipt verbs** in sanadset's tagged rows).

Here the most transferable part of the episode: **two opener-only probes returned 79.2% and 66.5% on the same question.** They were different term sets over different populations, and neither was wrong about what it measured — one omitted the abbreviated `ثنا`, and *both* were structurally blind to the second convention. Two numbers that disagree are two instruments, not one measurement with noise. Reconciling them is what exposed the convention split; averaging them, or picking the one that suited the argument, would have buried it.

`D = opener OR (≥2 standalone عن in the first 25 tokens)`, calibrated on the positive **and** negative class of **each** convention, fires on `123,202` rows (77.2%); correcting for D's measured false-positive rate leaves ≈**122,013**. It remains a **lower bound** because D's sensitivity on sanadset's *own* bare-name convention is only 39.9% — short chains are invisible to it — so the quantity is **not boundable from above** by any instrument we have. Report the bound and its direction, never the point estimate alone.

Two corollaries, both earned the same day:

- **Never let the artifact grade its own homework.** A dataset's own annotation (`Sanad = "No SANAD"`) is the corpus author's *claim*, not your measurement. Here it recorded their tagging pipeline failing on 165,701 rows — not the absence of a chain. An issue was nearly closed as a duplicate on that basis.
- **Never audit a defect with an instrument downstream of it.** A 97.1% "extractability" figure was produced by the very matn-mining fallback (da#369) whose output it was meant to audit.

**A high number is exactly as suspect as a zero.**

**Why:** every one of these returns the value you would also get from the healthy state. The signal and the null result are the same string. Unlike a crash, nothing prompts you to look. These cost more than loud failures precisely because they arrive wearing the costume of a result.

## The instrument was immaculate and it was never plugged in (ip#130, 2026-07-11)

The furthest form of this: **an experiment can be perfectly designed and connected to nothing.**

A publish workflow had been red for five days on 10 HIGH CVEs that all had published fixes — because the BuildKit GHA cache served the `apt-get -y upgrade` layer from cache, so the upgrade replayed as a no-op. The fix was `no-cache-filter: base` on `docker/build-push-action`. The PR was then **rewritten specifically to make its own proof falsifiable**: the base stage kept byte-identical to `main` so its cache key was unchanged (the layer *would* have hit, so a rebuild could only mean the flag fired), and `build-essential`/`curl` deliberately left installed so Trivy going green could only mean apt actually ran. Two independent, mutually-confirming signals. Genuinely first-rate experimental design.

**The action has no input called `no-cache-filter`. It is `no-cache-filters` — plural.** Singular is the *docker CLI flag*; plural is the *Action input*. **GitHub Actions does not fail on an undeclared `with:` key** — it emits a warning annotation and silently drops it. `actionlint` passes, because it does not validate third-party action input schemas. So the input list was empty, the loop that emits `--no-cache-filter` ran zero times, and buildx never saw the flag.

Caught only because a reviewer went and **read the pinned action's `action.yml` and `src/context.ts` at its exact SHA**, instead of reasoning about the diff.

**Three things to carry:**

- **A config key is an instrument.** Before trusting that a flag/env/input changed behaviour, confirm the *consumer declares that key*. Silently-ignored unknown keys are the norm, not the exception (GH Actions `with:`, most YAML configs, `docker compose`, k8s annotations). The singular/plural, `_`/`-`, and CLI-flag-vs-API-field slips all land here.
- **Failing safe is not harmless.** The inert flag left `main` red, so nothing shouted. But merging it would have made the next reader conclude *"we applied `no-cache-filter` and the CVEs are still there, so the cache wasn't the problem"* — **an inert fix discredits the correct diagnosis.** That is worse than no fix. And this repo was the pathfinder for the identical change in three sibling repos.
- **Verifying that a proof is *sound* is not verifying that it is *connected*.** The first reviewer correctly killed an earlier version for destroying its own proof (it bundled a change that would have made the layer rebuild on content grounds regardless, so a working flag and an inert one produced byte-identical evidence). That review was right and it was not enough. **Ask both: can this experiment distinguish the two outcomes — and is it actually wired to the thing it claims to test?**

**How to apply:**
- **Before reading any number a detector produces, score it on a known-positive class and a known-negative class and show it separates them.** Report the lift, never the bare rate. A detector whose recall on true positives is unmeasured is not measuring the thing you named it after. If the positive class is unavailable, give a **bound** and say so — never a point estimate.
- Correct for false positives before multiplying a rate by a population. `population × observed_rate` assumes recall = 1 and FPR = 0; measure both or the product is fiction.
- Treat a dataset's own metadata as a **claim by its author**, never ground truth — especially a field that records the outcome of *their* pipeline.
- Never audit a defect with an instrument that sits downstream of it.
- Before believing a `0`/`NULL`/empty, ask: **"can this command return nonzero at all, right now, in this exact form?"** If you cannot answer yes from evidence, the reading is void. Prove the probe live by pointing it at something you know is nonzero.
- Any command that can receive **no arguments** (`du $glob`, `wc -l $files`, `grep $pattern`) sums or counts the empty set to `0` without complaint. Guard the argument list, or expand the glob in the same privilege domain that reads it.
- Any query language without strict-name checking (Cypher; also `jq` on a missing key) turns a typo into a uniform NULL. **Enumerate the available keys before selecting one.**
- For remote/long-running commands, emit a terminal sentinel (`printf 'RC=%s\n' $?`) and treat its **absence** as "did not complete." Silence is not zero. `timeout` + pipes + SSH each independently swallow the exit status ([[feedback_push_pipe_masks_rejection]] is the same defect in `git push … | tail`).
- When a diagnostic caps its output (`LIMIT`, `head -N`, `--max-count`), the cap must be reported alongside the number or the number is a lie. Never `| head -N` a per-file count and then sum ([[feedback_no_head_in_surface_enumeration]]).
- Inspect one raw line of any text stream before parsing it (quoting, BOM, CRLF, leading whitespace).

## The control must come from OUTSIDE the scope you are about to trust (2026-07-09, da#383)

The instrument guard this memory prescribes — *make the detector fire on a known positive before believing its zero* — has a blind spot that defeats it entirely, and it was found by the person who had been enforcing it all evening.

A reviewer searched for a fixture string across 6,141,818 values in three `narrators_bio_*` and two `narrator_mentions_*` tables, found zero, and reported that the fixture was fabricated. She **carried a control**: the scan had to find `أبو عمرو الذي`, a row she knew existed, before any zero would count. **It passed.** It was worthless. That row lived in `narrators_bio_itqan` — *inside the subset she was searching*. The string she sought lived in `narrator_aliases_itqan.parquet`, a file the scan never opened. It is on disk in four places, including `narrators_canonical`.

> **A control drawn from inside the search scope proves the scan can see. It cannot prove the scope is right.**

So: *"a zero from a scan that cannot see is not a zero"* has a sibling nobody had stated — **a zero from a scan pointed at the wrong corpus is not a zero either, and the first guard cannot catch the second.** It sits there displaying a green control while you draw a false conclusion. The control must be a value you expect the scan to **miss** if the scope is too narrow: choose it from a file, table, or namespace you are *not* certain is in scope, and widen until it is found.

Corollary for exhaustive claims: **print the scope.** Number of files, number of columns, the file list itself. A reader cannot audit a zero whose search space is implicit, and neither can its author an hour later. Where the zero becomes a written claim about provenance — *"this fixture is not drawn from any artifact"* — **the provenance claim must carry its own provenance.**

That corollary is not optional, and the proof is that the rule alone did not stop it. **Three people ran this scope error in one evening, each with a passing control.** The first caught herself. The second (me) amplified her finding into a merge blocker without running anything. The third re-derived the same zero from the same unopened file and **committed it into the artifact** — a `NOT ON DISK` heading over a row living in a staging table beside the five he searched — inside the very block whose purpose is to say which rows are real. Nobody was careless; a correct label is not the fix. **Stating the scope is the fix**, because it is the only version a reader can falsify.

**And the scope error inverts. The wide side is worse.** Three of the four scans that evening were too *narrow* — false negatives, findable by widening. The fourth was the orchestrator's, over `data/**`, 63 files, reported as *"four places."* Thirty-one of those files were **archival snapshot directories** of superseded runs (`curated.pre-da311-scrub-*`, `curated.pre-wave23-reload-*`, `curated.run5-scrubbed`, `curated.known-good-*`); `data/` held nine copies of `narrators_canonical.parquet`. The scan printed `f.name` — **the basename** — so a superseded snapshot was indistinguishable from the live artifact in its own output. Live scope: **one** hit.

Worse than the count: the row's only appearances in `narrators_canonical` were in **pre-scrub** snapshots, where a matn-derived name in the canonical table *is the defect the scrub removed*. **The bug was cited as proof of the feature.**

> **A scope that is too wide is not the conservative error.** Too narrow yields a false negative you find by widening. **Too wide yields a false positive carrying the authority of an exhaustive search** — and where the extra scope holds superseded artifacts, it will confidently reproduce the very defects that were fixed. A bigger scope *feels* like rigor; `63 files` reads as thoroughness.

So *print the scope* is not enough — the orchestrator printed a **count**, which is a scope nobody can audit. **Print identity, not cardinality:** full paths, or at minimum the directory set. *A basename is a label; a path is a name.* Where a repo carries snapshot/backup directories, a provenance claim must scope to the live artifacts and **say which those are**.

## Verify the claim as written, not as you would have written it

A reviewer checked *"no table carries a colon-joined name"* by measuring **whether the cut fires** — a better instrument than the author's `grep`, pointed at an adjacent proposition. Both are true statements; only one was the sentence on the page. The false premise survived a careful review and, from the outside, the review was indistinguishable from a real verification. (Alejandra Reyes-Fuentes, who found it in her own review — in the same message where the orchestrator did it to her: "verifying" her apposition count of 284 by measuring *substring occurrences* and getting 17.)

> **Verifying a claim means verifying it as written, not as you would have written it.** A better instrument aimed slightly off the proposition is how a false premise survives a careful review.

Corollary for numbers in prose: **name the predicate.** `17`, `17`, and `284` were three questions, not three answers. And when a colleague's number won't reproduce, **ask which predicate before asserting them into a correction** — two people had already acted on numbers they had not reproduced that night.

Two siblings from the same night:

- **The instrument that confirms a correction must not match the text of the thing being corrected.** Grepping for a retracted sentence finds the retraction quoting it. (Kwesi Boateng — he nearly re-fixed something already fixed.)
- **A citation that names a file for some rows and leaves others unattributed lets the reader infer the named file for all of them.** Partial attribution certifies what it omits. Same shape as the partial honesty label in [[feedback_fixture_makes_guard_assertion_inert]].

## An INERT mutation and a CAUGHT mutation are the same red (2026-07-11, deploy#574)

Mutation testing is the instrument we reach for when we distrust a test suite. **It is an instrument, and it needs a control like any other.**

An engineer auditing a destructive-prune gate ran a mutation battery. **Two mutations "survived green" — and neither was a test gap.** They were **inert**: each removed *one* of **two** independent refusals, and the other refusal still fired. The prune was still blocked. The mutation changed nothing that mattered.

She was about to report them as **"caught"** — a green suite under a mutation reads as *the guard held*. It doesn't. It reads as *either the guard held, or your mutation never disarmed anything.* She rebuilt both until they **genuinely unlocked the prune** (a gate that self-signs *both* artifacts; a real early-exit bypass) — and only then were they caught, 10 tests red on the first.

> **A mutation battery that does not first establish its mutations are EFFECTIVE is the same defect as the guard it is auditing.**
>
> — Aisha Idrissi, on her own instrument, having spent the day telling everyone else to verify theirs

**The four-way confusion this creates**, and why it is worse than a plain unrun test: a *surviving* mutant and an *inert* mutant produce the identical signal, and so do a *killed* mutant and a *redundantly-guarded* one. Four states, two observations.

| you mutate, suite is… | could mean | could ALSO mean |
|---|---|---|
| **green** | the guard has a hole (**real finding**) | **your mutation disarmed nothing** |
| **red** | the guard caught it (**real pass**) | **a *different* guard caught it — the one you meant to test is dead** |

**How to apply.** Before a mutation counts as evidence, **prove the mutant is live**: show that the mutated system actually *does the forbidden thing* in the absence of the tests — i.e. that the mutation reaches the objective, not merely the source. Concretely, for a guard: run the mutated system against the input it is supposed to refuse and **confirm it now permits it**. Only then does a red suite mean the test caught it, and only then does a green suite mean a hole.

And the sibling trap, which is the second row of that table: **when a mutation goes red, confirm the *intended* test is the one that failed.** A redundantly-guarded property will red on a neighbouring assertion while the assertion you were auditing is inert — the same shape as the mutation harness satisfied by a plant applied to the wrong file (§ *The third gate: was it the right subject?*).

Sibling of [[feedback_fixture_makes_guard_assertion_inert]] (a fixture that cannot reach the branch) and [[feedback_passing_repro_masks_bug]] (a repro that cannot go red). Here it is the **auditing instrument itself** that cannot move — the last place anyone thinks to look, because it is the thing you brought *in order to* be rigorous.

## An invariant enforced at the producer is NOT enforced at the consumer. Nothing carries it across. (2026-07-11, deploy#577)

The backup PR's author reasoned **exactly correctly** on the producer side: a *partial* backup must not emit the success gauge, and she put `USER_PG_OK` **inside** that condition — because otherwise *"the one store that cannot be rebuilt from the pipeline artifact could be missing from every backup we hold and the dashboards would stay green."*

**The identical argument applies verbatim to the consumer, and was not carried across.** `restore.sh` sets `FAILED=1` only when a dump is **present and its restore fails**. A dump that is **absent entirely** is a warning — `skipped (no dump)` — that never touches `FAILED`. The script prints `=== Restore complete ===` and **exits 0**.

The all-empty case *was* caught. The one-store-missing case was not. **There was a guard on each side of the hole and none in it.** And the script's own comment says *"a restore that did not restore must not be reported as success"* — **the comment was right and the code disagreed with it.**

> **The producer refused to call a partial backup a success. The consumer called a partial restore a success. Same argument, same file pair, opposite conclusion.**

**Why the consumer side is the dangerous half, and this is the part to carry:** the producer's failure is *loud* — the backup alert fires correctly and someone sees it. The consumer's failure is **silent and terminal**: you only invoke restore *after* the thing you were protecting is already gone. **A false "backup failed" costs you a night. A false "restore complete" costs you the data.** The alerting cannot help, because it is watching the backup — and the backup told the truth. **The restore is the thing that lied.**

**How to apply.** When you enforce a completeness/validity invariant at one end of a pipe, **write down the sentence you used** — then go to the other end and check whether it is true there too. It usually is, and it usually isn't enforced. Especially:
- **producer refuses to publish incomplete ⇒ consumer must refuse to consume incomplete.** Do not rely on "the producer wouldn't have written it" — a partial write, an older artifact, or a *pre-fix* artifact all reach the consumer.
- **Completeness is a property of the artifact, so the artifact must declare it** (`_resolve_run.txt` in da#428; a `COMPLETE` marker in a backup dir). A consumer that infers completeness from *presence* — "the newest directory name" — selects the broken artifact by construction, because the broken one is newest.
- **Grade recovery paths hardest.** Every guard in a restore/rollback/undo path is used exactly once, under pressure, when the primary is already lost. It is the last place a silent success is survivable and the first place nobody tests.

## A negative that passes for the WRONG REASON has silently stopped testing (2026-07-11, deploy#577)

The strictest generalization anyone produced, and the author found it **in the commit where she was fixing this exact defect everywhere else.**

She added a completeness gate (an absent store is now fatal). It was correct. It also made **two pre-existing negative fixtures inert**:

```
truncated_dump_matching_checksum: exited 1 — "Restore REFUSED — incomplete"
truncated_user_pg_dump:           exited 1 — "Restore REFUSED — incomplete"
```

Both fixtures held **only** the dump they mutate — so the new gate rejected them for **MISSING STORES**, *before their truncated dump was ever read*. **They still passed.** Green, red-when-expected, exit 1 as designed. **And the truncation path they exist to exercise was no longer tested at all.**

> **A non-zero exit proves the artifact was REJECTED. It does not prove it was rejected BY THE CHECK UNDER TEST.**

This is the mirror of the whole file: everywhere else we worry that a guard *cannot fire*. Here the guard fires **correctly, for the wrong reason**, and the test it silently replaced is gone. **Adding a guard EARLIER in a pipeline can un-test every guard behind it**, and every signal you have stays green.

**The durable fix is not better fixtures — it is a stronger `expect_fail`.** It now takes a **required** expected-reason argument and asserts the failure happened *for that reason*:

```
truncated_dump_matching_checksum -> "PostgreSQL (isnad): pg_restore FAILED"
no_user_pg_dump_at_all           -> "Restore REFUSED — this backup is incomplete"
bitrot_stale_checksum            -> "Checksum MISMATCH"
```

**How to apply:** a negative test must assert **which** guard rejected it, never merely that *something* did. Any `expect_fail` / `assertRaises` / `-ne 0` without a reason is one earlier-guard away from becoming a tautology. And when you add a check **upstream** of existing negatives, **re-derive why each one still fails** — a passing suite is not evidence they still test what they were written for.

### And a guard is pinned by its CALL SITE, not by its existence

Same engineer, same PR: one of her own new tests initially **missed** a revert of the fix. It asserted that `backup_is_complete` **appeared in the file** — which it still does when the call site is neutered to `if true`. The function existed; nothing called it meaningfully.

> **A guard is not pinned by the existence of the function that implements it. It is pinned by the branch that calls it.**

Sibling of [[feedback_fixture_makes_guard_assertion_inert]]. Same family as the ordinal/label confusion above: *the name was present and the behaviour was absent.*

## A true conclusion resting on a DEAD REASON (2026-07-11, ip#138)

The subtlest instance of the whole saga, and the only one where **nothing was ever false.**

A committed comment justified keeping two cache lines: *"these two cannot cache-hit, because `base` is the whole image."* **True when written** — the Dockerfile was single-stage. A later PR **split it**, so `base` became a thin preamble and the stated reason evaporated. The *conclusion* stayed true (they still cannot cache-hit — but now because un-caching the parent **cascades** to its children, a completely different mechanism, established by a completely different experiment).

> **The claim survived as a true CONCLUSION resting on a DEAD REASON.**
>
> Nothing goes red, because the conclusion is still correct. **It reads as verified, and it isn't.**

**This is the one that no instrument catches**, and it is worth seeing why every technique in this file fails on it:
- A test cannot fail — the behaviour is unchanged.
- A **diff** cannot show it — the *text* is stable; only the *world* moved.
- The strip-comments-and-compare trick, which caught everything else, is **structurally blind**: it compares text to text.
- And it is immune to the [[feedback_review_against_artifact]] discipline, because reading the artifact *confirms* the sentence.

**The damage is deferred and total.** The next person to reason from that comment inherits a mechanism that no longer exists. If they act on it — "so if we un-split the image, the lines become useful again" — they are reasoning from a dead premise with a green board behind them. **A correct conclusion with a rotted justification is more dangerous than a wrong one, because a wrong conclusion eventually trips something.**

Sibling of §*A reading and a forecast are not the same kind of thing* (prose about a tree that does not exist yet) — this is its mirror: **prose about a tree that no longer exists.** Both survive indefinitely because nothing can run them.

**How to apply.** When a change invalidates the *reason* for an existing decision, **the comment stating that reason is part of the blast radius**, even when the decision itself still stands. Ask of any change: *what did I just make false that is written down somewhere and still reads as true?* And when you preserve a decision under a changed world, **re-derive its justification from scratch** rather than checking that the conclusion survives — the conclusion surviving is exactly what hides the rot.

*(Bjørn Henriksen found both instances in his own comment, while shipping the change that had killed them.)*

### The instrument never survives the PR that built it

Four harnesses were built across one effort — each proved something real, each was **deleted the moment it answered its question**: the filter-fires proof, the toolchain-free build proof, the cascade A/B, the `mode=min` A/B.

> **The verification capability has never once survived the PR that created it.**

That is a tidiness question right up until a change ships with a **revert condition**. ip#138's read: *"if `[base 2/2]` ever fails to come back CACHED on a no-filter read, `mode=min` killed the detector and this reverts."* Correct, essential — **and unrunnable.** A "no-filter read" is something **production never performs**. Evaluating it requires rebuilding a harness from a merged PR's prose. **The person who most needs that check is the least likely to know how to perform it.**

> **If a change ships with a revert condition, the instrument that evaluates that condition ships with it.** An unrunnable revert condition is a comment, not a guard.

Make the proof a permanent `workflow_dispatch` self-test, not a throwaway: it must (a) run the arm production never runs, (b) be dispatchable by someone who wasn't there, and (c) **prove it can go red.** (Fatima Bensalah, ip#138.)

### …and the rule itself decays. The citation rule decayed into an unstable identifier.

The comment that says *"cite layers by their `[base N/9]` label, never by vertex number"* — the rule written **because** ordinals shuffle between runs — **prescribes a label that no longer exists.** The `/9` was the single-stage era; a later PR split the image and the current build emits `[base 2/2]`, `[builder N/4]`, `[runtime N/6]`. The same comment self-contradicts: prescribes `N/9`, then correctly *uses* `[builder 4/4]` sixty lines on.

**And it fails in precisely the way the rule exists to prevent:** someone follows it literally, greps a current log for `[base N/9]`, finds **nothing**, and concludes the evidence was fabricated — the identical harm as the reader who greps `#10`, finds a `COPY`, and thinks the proof was faked.

> **A guard written against decay is not exempt from decay.** The remedy that hardens a rule (pin to a stable name) has its own shelf life, and *nothing goes red when it expires*.

Corollary, cheap and load-bearing: **when you cite a log, name its era.** A comment citing both a pre-split and a post-split run without saying which leaves the reader unable to distinguish **decay from fabrication** — and they will assume the worse one.

## The failure mode with no instrument in it

Every rule above assumes the reporter executed *something*. The corpus has no clause for **an instrument that was never built.**

A reviewer wrote: *"Planted the shapes myself: `sys.exit(1 if x else 2)` now CAUGHT, `sys.exit(rc)` CAUGHT, permitted forms pass, 39 tests green."* She had planted against the **previous head** and inferred the rest from a diff. At the head she named, `sys.exit(rc)` **permits**. The only true sentence was `39 tests green` — the one thing she had actually run. She retracted in full, unprompted, and named the class better than anyone else could:

> The other failures were **instruments that lied to me.** This one is **me lying to you, in the voice of an instrument.** No probe crashed, no control passed vacuously, no scope was too narrow. **There was no probe.** And the words *"planted the shapes myself"* are what made it credible.

> **"I ran it" is a claim like any other, and it is the one nobody audits.**
> **A reported measurement carries the sha and the command, or it is an opinion.**

This is [[feedback_verify_diagnosis_before_delegating]]'s other blind side.

**Do not conflate it with relaying an unattributed measurement.** The orchestrator did — writing that his *"Nikolaos already planted the `IfExp`"* was the same defect at lower amplitude — and the author of the fabrication refused the comparison, correctly:

> **Yours is a citation with a missing attribution; mine is a citation with a fabricated source.** A reader can repair yours by asking him. Nobody can repair mine, because there is nothing behind it.

Two rules, and they have different remedies. *The reading was taken* catches the fabrication. **Nothing catches a relayed attribution except naming the source**: write *"he reports"* unless you ran it, and paste the output when you did. Note the trap in ranking them at all — placing your own smaller failure alongside someone's larger one **makes the ledger symmetric and reads as accountability while flattering you.**

Note the trap in the aftermath: her false report and a real bug **pointed the same way**. She told the author `sys.exit(rc)` was caught; it was not; he found the hole himself, from an argument of hers drawn from the wrong table. *A correct conclusion from a bad example.* An unrun claim that happens to be right is not evidence, and it is the hardest kind to catch, because nothing downstream contradicts it.

## Labels cannot distinguish the members of the set they label

Three axes, one error (Kwesi Boateng):

- **path** — `f.name` over nine copies of `narrators_canonical.parquet` collapsed a superseded snapshot into the live artifact;
- **text** — grepping for a retracted sentence finds the retraction that quotes it;
- **scope** — `"32 live files"` and `"20,189,229 values"` are unauditable cardinality; `"13,446,708 values across these eight named tables"` is auditable.

> **An instrument that answers with a label cannot distinguish the members of the set it labelled.**

And why the too-wide error is the harder one to escape: **a false negative is falsified by one hit; a false positive is falsified only by understanding the corpus.** You had to know what `curated.pre-da311-scrub` *was*. No instrument tells you that.

## The third gate: was it the right *subject*?

An instrument guard proves the instrument can **see**. It does not prove you **looked in the right place**. This holds at every layer, and each layer was breached the same night:

| gate | answered by | breached by |
|---|---|---|
| did the probe apply? | plant-applied assertion | — |
| did it run? | collected-count pin (`rc=5` is not enough; a typo'd selector matching *one unrelated test* clears a non-emptiness check) | *a non-zero count is not a measurement either* |
| **was it the right subject?** | **nothing** | a test proving `enum.unique` works on an enum **it built itself**, never touching the registry; a scan proving it can see a row **inside the subset it searched** |

A mutation harness's `--expect-file` is satisfied perfectly by a plant applied to the wrong file. **Assert the plant is present in the subject the test imports, not in the file the harness was told about.** Nikolaos Papadopoulos's formulation, on his own tooling: *"Every instrument guard I have written proves the instrument can see. Not one proves I looked in the right place."*

## Reproduce before you escalate

The failure above was cheap for its author, who caught herself and retracted. It was expensive because **the orchestrator amplified it without running it**: escalated it to a merge blocker, told the reviewer to withdraw an approval, and ordered the PR's author to annotate a real, canonical, on-disk narrator name as fabricated — inside the very block whose purpose is to say which rows are real. *The instruction was the defect the block exists to prevent, issued by the person enforcing it.*

> **A finding another person must act on is held to the standard of a finding you would act on yourself. Reproduce before you escalate.**

The asymmetry that makes this hard: *"verify before you delegate"* fires loudly when a finding contradicts you, and silently when it agrees. Four instruments failed that night before anyone checked one that confirmed what they already believed. See [[feedback_verify_diagnosis_before_delegating]] — this is that rule's blind side.

## The identifier is the same; the referent is not (2026-07-10, da#362/da#372)

Four failures in one night, one shape:

| the reading | the scope you assumed | the scope you got |
|---|---|---|
| `statusCheckRollup` green | the head you're merging | a **dead head** |
| the control row was found | the corpus | **the subset the scan searched** |
| the AST walk says `VALIDATION_FINDINGS` | the registry's `5` | `src/graph/__init__.py`'s **`4`** |
| the reviewers approved | *this* PR | a **neighbouring PR** |

Every instrument was sound. Every one was pointed at something the operator had chosen, and the name it returned was correct *for the thing it looked at*. **A name resolves in a scope, and the scope is the part nobody prints.**

Two concrete corollaries, both paid for:

- **The blast radius of a change is the import graph, not the diff.** An AST walk of the file you are editing reads imported constants as unresolved symbols and silently grants them the meaning they have on `main`. `src/cli.py` imported `EXIT_VALIDATION_FINDINGS` from a module that defined it as `4` while the registry defined it as `5`. The walk was correct; its scope was drawn from inside the hypothesis.
- **`git merge-tree` reporting a file conflict-free is not evidence the file is correct post-merge.** `src/cli.py` auto-merged with zero conflict markers and was the file that broke: git compares text, and the invariant lived across a module boundary git has no opinion about. **A clean auto-merge is not a correct merge.** Run the suite.

And the reason this belongs in a harness rather than in anyone's head: *it happened inside the message whose subject was that exact failure*, twice, to two different people, within an hour. **You cannot hold a rule in mind while executing the thing the rule is about.** Alejandra Reyes-Fuentes's sentence, which is the load-bearing one: ***"the reader distrusted me" is not a control.*** A finding survives because it was checked, not because someone happened to be suspicious.

### An unstable identifier can fabricate a refutation as easily as a confirmation (2026-07-11, ip#130)

The proof that the `no-cache-filters` fix fired was cited, by everyone including the orchestrator, as: **control `#10 CACHED` / treatment `#10 DONE 11.8s`.** BuildKit assigns vertex numbers in **solve order**; they are not stable across builds. In the control arm `#10` is `[base 5/9] COPY pyproject.toml uv.lock ./` — the apt layer is `#12`. **The table compared two different layers.**

The conclusion survived re-derivation against the stable `[base 2/9] RUN apt-get … upgrade` label, and only because control's `#10` *also* happened to be CACHED. Had the numbering shuffled it onto `COPY src ./src` (DONE 15.1s), the identical table would have read *"control: DONE"* and **a sound proof would have looked falsified.** The usual worry is a fabricated confirmation; an unstable identifier fabricates either verdict with equal ease, and the false *refutation* is the one that gets you to abandon a correct diagnosis.

The costly half is that the same citation went into a **committed comment**, which outlives the run: it credited *"the uv install (#18, 43.4s)"*. `#18` is `exporting to docker image format` — a vertex that exists only because the proof harness used `load: true`, and which the real `push: true` publish never emits. The uv install is `#14`, at **3.5s**. The comment's *"~80s extra per publish"* therefore bills the publish for ~59s of harness-only work — under the word **MEASURED**, in a comment whose entire purpose is to stop the next reader believing an unmeasured claim.

> **Cite by stable name, not by ordinal.** Vertex numbers, line numbers, array indices, `head -N` positions, and job-step numbers are all assigned by the run, not by the thing. **A number that the tool chose is not an identifier of the object.**

And the scope trap: **a measurement taken under a harness carries the harness's costs.** Before writing a number into a durable comment, ask which of its terms exist only because you were measuring. (Fatima Bensalah, re-deriving from the raw job logs rather than the run summary.)

#### Four numbers, one decision, every one measured in the wrong arm

The decision was trivial: keep or delete two `cache-from`/`cache-to` lines. Four prices were put on it. **All four were wrong, and each was produced by someone who had just correctly refuted the previous one.**

| price | author | measured in |
|---|---|---|
| **~80s** per publish | the reviewer | a `load: true` **proof harness** — the export/import vertices a real `push: true` publish never runs |
| **3.5s** (the layer the cache protects) | the implementer, refuting the ~80s | the **control** arm — where the filter is absent. Once the filter is on, `base` is the whole image, nothing can cache-hit, and the 3.5s is **unreachable** |
| **zero** ("so keeping them is free") | the orchestrator, refuting the 3.5s | **`cache-from` hits only.** It ignored `cache-to`, which *runs on every publish regardless* and — because the filter rebuilds every layer — re-exports the **full** layer set each time |
| the real cost | **nobody, at first** | The harness omitted `cache-to` *by design*, to guarantee zero cache writes — **so the one arm that would have priced it is the one arm nobody ran.** Only when a reviewer went back to the treatment log did half of it become a measurement: `cache-from` = **0.1s** (`importing cache manifest from gha … DONE 0.1s`). `cache-to mode=max` — which re-exports *every* layer on *every* publish, since nothing is cached — remains **unpriced.** |

The reviewer **refused the third number even though it supported the ruling he had already given.** That is the artifact:

> **A number that lands in your favour deserves *more* scrutiny than one that doesn't, not less.**
>
> "I am not going to accept a free lunch that flatters my own conclusion on the same evidentiary standard I have refused three times today from everyone else."

Sibling of *"the sentence that flatters the frame is the sentence to measure"* (§ *The correction is not a safe place to stand*) — but stronger, because here the flattering number arrived **from someone else**, as a gift, pre-argued. That is the form nobody audits.

**The operative move is not a better number. It is refusing to price the decision at all.** The case for keeping the lines was **structural** — `cache-from` is the *detector*: if the filter ever silently breaks, the cache springs back, serves the frozen layer, and Trivy goes **red**; delete it and the same breakage is **green and silent**. That argument survives all four numbers because it never rested on one. **When every measurement of a quantity has been taken in the wrong world, the answer is not to take a fifth — it is to notice the decision was never quantitative.**

And the guard's own fifth costume, caught by the reviewer in the act of defending it: **`cache-to` is what keeps the detector alive.** GHA cache entries evict after ~a week unused. Drop *only* `cache-to` as an "optimisation" and `cache-from` quietly finds nothing — **the guard is dead without anyone touching it.** *A detector that decays into silence.*

#### The log contains your prose about the bug, and your parser cannot tell them apart

The closing act of the same PR, and the sharpest instance in this file because **two people hit it independently within minutes of each other, and each was one keystroke from reverting a working fix.**

The fix landed; the real publish ran; both the implementer and the orchestrator went to read the log for the one question that mattered — *did `[base 2/9] RUN apt-get … upgrade` come back `CACHED`?* Both greps returned **`#11 CACHED`**. Both were about to report **the fix is inert on the real publish.**

It was not. `#11`'s only *build-phase* status is **`DONE 11.1s`** — it rebuilt, apt visibly executed, and Trivy went 10 → 0.

**The string `CACHED` was in the log because the fix's own commit messages are in the log.** `docker/build-push-action` runs with `--attest type=provenance,mode=max`, and the provenance attestation JSON **embeds the commit messages** — messages that read *"the buildx GHA cache serves the apt layer from cache (`#11 CACHED`)"*, because that is what the commit was **describing and fixing**. The implementer's parser kept the *last* match per vertex, so it read `CACHED` **out of his own prose about `CACHED` layers** and reported it as the build status.

> **The instrument manufactured a refutation of the fix, out of the fix's own description of the bug.**

This is the same blade as *"the instrument that confirms a correction must not match the text of the thing being corrected"* (§ *Verify the claim as written*) — but promoted, because here the contaminating text is **injected into the artifact by the toolchain**, not written by a person. You cannot avoid it by being careful about your own grep targets; the log *ships* with your prose in it.

**What saved it, both times, was the same thing: two readings disagreed.** The implementer also saw `#11 9.900 update-alternatives: …` — apt visibly running. The orchestrator noticed the finding was consequential enough to re-derive before reporting. **Neither reading was a measurement until they were reconciled.**

**How to apply.** When grepping a build/CI log for a status token:
- **Scope to the step's own output stream** (`grep -E $'\tBuild and push\t' | grep -v '"message"'`), never the whole run log. A run log is a *concatenation of heterogeneous streams* — job output, JSON payloads, attestations, commit metadata — and a token search treats them as one document.
- Assume the artifact **contains the words of the change being tested**: commit messages, PR titles, and comments all get embedded by provenance/attestation/metadata tooling. **The more precisely your commit message describes the bug, the more certainly it will contaminate the grep that checks the fix.**
- **A status token and a status are different objects.** Take the status from the vertex's *own* status line, not from a substring match anywhere in the run.
- And the general form, which is why this belongs beside the ordinal trap: **a confirmation and a refutation are equally manufacturable.** Everyone braces for the instrument that falsely confirms. This one falsely *refutes* — and a false refutation gets you to revert a correct fix, which is the more expensive direction.

### The fourth costume: absence of a stop read as presence of a go

The three above are readings **taken wrongly**. This one is a reading **never taken**, of a signal **never sent**, whose silence is treated as content.

`da#372` stood at `0/2` — two reviewers at Changes-Requested — for four hours while three people planned the merge chain around it as though it were ready. Nobody decided it was approved. Each inferred it from *not having been blocked*.

> **Nobody has to be careless for this one. It happens by default, and it compounds: every hour of unblocked work is more evidence that you were not blocked.**

It is the same failure from both sides of the same field. The orchestrator wrote *"the two standing approvals"* into a public comment, having read the reviewers' names off a **neighbouring PR's** verdicts; the author read *"nobody has stopped me"* as provisional approval. One inferred a state from an adjacent object, the other from an absent one.

Remedy is mechanical, not attentional: **before any claim about readiness, print the field.** `gh api .../issues/N/comments --jq '… select(test("^RequestOrReplied"))'` costs one call. Related: `feedback_refresh_before_status_claim`, and main#935 (Hook 4 counts verdicts, not shas — an approval given at an old head merges unreviewed code, silently and green).

## A reading and a forecast are not the same kind of thing, and only one gets labelled (2026-07-10, da#392)

`src/exit_codes.py` carried: *"Once it moves to `VALIDATION_FINDINGS`, the only emitters of `1` are `_check_neo4j` … and `_cmd_load`'s genuine failure path."* Written in the **future tense**, about a tree that did not exist yet. Nobody could run it, so nothing reddened, and it was already false about `_check_neo4j` (which emits `8`).

That is the shape: **prose describing a state that has not arrived.** A comment about the present can be checked by reading the file. A comment about what will be true after somebody else's PR lands has no subject to check against, so it survives indefinitely and rots silently.

Worse, its *conclusion* (`rc=1 implies an unwritten manifest`) stayed true — because deleting an emitter of `1` can only narrow the antecedent. **An argument whose conclusion outlives its premises warns no one.** Nothing downstream contradicts it. That is more dangerous than a false conclusion, which someone would eventually trip over.

**The trap catches the person diagnosing it.** The engineer who correctly named this class — *"the comment was written about a tree that has never existed"* — in the same message asserted that after her rebase the emitter set would be **empty**. She had AST-walked `main`. But `main` cannot contain her rebase. Reading her actual diff showed `_cmd_load` has **two** exits: the findings condition she routed, and a genuine-failure path her own PR sends to `EXIT_LOAD_FAILED`, which *is* `1`. The set is a singleton. **She verified the present and predicted the future in the same breath, and labelled only one of them.**

> **Before writing prose about a tree, produce the tree and read it.** Rebase, then AST-walk the *rebased* source and print the set. A reading, not a projection. If you cannot run the command that would falsify the sentence, you are not entitled to the sentence.

Corollary for reviewers, and it is the cheap half: when a colleague's finding *agrees with you and improves on your framing*, that is exactly when you skip verifying it. Reading the diff took one command and overturned the claim.

Sibling: [[feedback_passing_repro_masks_bug]] (a *repro* that cannot go red) and [[feedback_test_mock_masks_prod_failure]] (a *test* that cannot go red). This memory is the *measurement* case: a probe that cannot go nonzero — and, above, a *sentence* that cannot be run at all. Same root: **verify the instrument before trusting the reading.**

## "Changes behaviour" is a two-place predicate written as one-place (2026-07-10, da#372)

The orchestrator instructed an author: *"`isnad-ingest validate` changes behaviour and your PR body does not mention it."* Measured off her **pre-rebase** diff, where `_cmd_validate` went `4 → 5`. True there. False about `main`, where `_cmd_validate` had **already** exited `VALIDATION_FINDINGS` since da#384 Amendment G — only its message text changed.

She ran the check against `main` instead of against the diff she was handed, and refused the instruction.

> **A behaviour change is a delta between two trees. Name both.** A consumer reads it relative to `main`; the instruction had measured it relative to a branch head that would never exist again. Had she complied, the PR body would have sent every operator to audit a call site that behaves identically.

Same family as the verdict/sha confusion below: **the identifier is the same, the referent is not.** `_cmd_validate` names one function and two behaviours, and the sentence picked the wrong one silently, because a diff always has a baseline and prose usually omits it.

## A hand-merged generated file describes no tree that exists (2026-07-10, da#372)

Resolving `ontology/structural/llms.txt` with `--theirs` during a rebase produced the header `files=248 nodes=3080 edges=4842` — **neither side's value**, and no tree's. `main` was `251/3126/4912`; the correct regenerate was `252/3151/4969`.

Nothing would have caught it. Every check that *reads* the header passes; only regenerating disagrees. Contrast `gh pr edit --body-file`, broken on that repo by the Projects-classic deprecation, which fails **loudly** (rc=1, body never lands) — dangerous only to a caller that reads no rc. The generated-file merge is the worse defect precisely because it is silent and plausible.

> **A generated artifact has no `--ours` and no `--theirs`. It has a generator.** Take either side and you have committed a description of a tree nobody built. Resolve by running the generator, then diff the header against the value you expect — and expect it from the *merged* tree, not the one you branched from. **A control against the wrong baseline is not a control:** a no-op regenerate passes it.

Sibling: [[feedback_declarative_head_needs_action]]. See also main#939 (the structural-index conflict tax).

## The correction is not a safe place to stand (2026-07-10, da#387 registry)

Three instances in six hours, each committed **inside a message correcting the same error**:

- The orchestrator wrote *"the two standing approvals"* into a public comment whose subject was asserting states you have not read — having read the names off a neighbouring PR.
- An engineer retracted a false mechanism (`IntEnum` is what makes `sys.exit` preserve the value; actually `__new__`'s `int.__new__` call kills the mutant at import), and in the retraction's own four-way table asserted *"value-equality passes"* for a variant where `Enum.X == 5` is `False`. Predicted observable, wrong mechanism, one line below the retraction of a predicted observable with a wrong mechanism.
- The orchestrator then asked *"if the re-run launches as `isnad-ingest pipeline`, da#394 gates"* — a question whose premise (`_cmd_pipeline` is an invocation form) dies to one `grep` of the `Makefile`, which chains five separate `$(MAKE)` processes.

> **You are most confident and least measured immediately after being right about something adjacent.** The frame feels earned, so the next sentence inside it goes unrun. Correcting an error is not evidence about the sentence you correct it with.

Operational form, and it is cheap: **a claim that would improve the story if true is a claim to run.** Each of the three would have made its own narrative tidier — a merge that was ready, a guard that was blind, a defect that gated. That tidiness is the tell, not the reward.

The corollary for reviewers is the same one this file already gives from the other direction: when a colleague's finding *agrees with you and improves your framing*, that is exactly when you skip verifying it. Both halves reduce to: **the sentence that flatters the frame is the sentence to measure.**

Note what actually caught all three: not care, not review, but somebody running the command. `git show ...:cli.py | grep sys.exit`. `python3 -c 'class B(enum.Enum): X=5; print(B.X == 5)'`. `grep -n pipeline Makefile`. None cost more than a few seconds, and none of the three authors ran theirs.

### The mechanism: the second instrument never gets a control

The engineer who wrote the false variant-B row found the cause himself, and it is the sharpest artifact in this file. His four-way probe asserted `E.X.value == 5`. That form is `True` in **all four** variants, including both broken ones — so the probe was structurally incapable of falsifying any equality claim, while the suite it was arbitrating asserts bare members (`ExitCode.X == 4`), which is `False` under a plain `Enum`. He read a generalization about the suite's assertion form out of an instrument that never touched that form.

Hours earlier, the same engineer had planted a fake binding to prove his offender scan could see an offender. **He ran the control on the first instrument and not on the second** — because by the time he built the second, he was the one doing the correcting.

> **A retraction ships a fresh claim under the credibility of the retraction, and nobody audits the audit** — least of all its author, who has just been visibly rigorous and is spending that.

So the discipline is not "be careful when correcting." It is mechanical, and it is the same one this whole file argues for, applied one level up: **the instrument you built to adjudicate someone else's instrument is an instrument. Control it too.** The `.value` form and the bare-member form are the identical assertion to a reader and different assertions to Python — which is [[feedback_fixture_makes_guard_assertion_inert]] wearing the costume of a probe rather than a test.

Sibling note on writing: he declined to carry the false claim into the issue body even as an explicit retraction, on the grounds that a negation does not survive a skim or a grep — cf. [[feedback_github_negated_close_keyword]], where a negated close-keyword still closes. Reword so the sentence cannot be *matched* as an assertion, rather than trusting "not" to be read.

## A guard that fails closed silently selects against the careful (2026-07-10, Hook 4 / main#940)

`validate_pr_review.py` reads verdict fields only from the **trailer block** — text after the *last* sole `---` line. A reviewer put his charter fields at the top of a 107-line review and used one `---` as a horizontal rule beneath them. The hook parsed lines 8–106, found no fields, and **skipped the comment as though it were not a verdict.** A one-line `Approved` with no rule is counted. His was not.

```
raw body contains 'RequestOrReplied' : True
_extract_charter_field(...)          : None
```

> **The hook punished the more careful comment.** A horizontal rule is what you add when a review is long enough to need structure. The failure mode selects against thoroughness, and it does so without a word to anyone.

Failing closed is the right *direction*; that is `feedback_safety_direction_over_ux_friction`. Failing closed **silently** is a different thing, and it is how a green board and an unmerged PR coexist. The cheap remedy generalizes past this hook: **when a parser finds the shape it is looking for anywhere in the input but extracts nothing from its scope, say so.** `body contains "RequestOrReplied" and extractor returned None` is one line and would have named the defect instantly.

It was found by simulating the hook's count with the hook's own functions before merging — not by trusting a `jq` scan that read the whole body and cheerfully reported two approvals. **My `jq` and the hook read the same comment and disagreed about whether it contained a verdict.** Two instruments, one identifier, different referents. Pick the instrument whose answer is the one that will act.

Sibling: a comment id is not a position. The same hook counts approvals as a monotonic set (a withdrawn approval is never subtracted, so a *blocking* reviewer counts as an approver — that one fails **open**) and retains every superseded verdict as live. All three defects are silent, and the accounting reports a confident integer that can be wrong in either direction.

### Two cheap instrument failures worth memorizing

- **`pytest | grep '^FAILED'` prints nothing when tests failed.** pytest emits ANSI colour codes, so `FAILED` is not at line-start. The grep returns zero matches and the reader concludes zero failures. Run `pytest --color=no` before grepping its output. (Found while pytest itself reported `2 failed` on the same run.)
- **A `cp` restore that silently did not restore reads exactly like a passing test.** After any plant-and-restore cycle, hash the file and compare it to the reference blob. `git hash-object <file>` vs `git rev-parse origin/main:<path>`.
- **`gh issue list --json number --jq 'length'` returns `30` against a true `32`.** `gh issue list` pages at 30 by default and says nothing; the `--jq 'length'` reads like a count of everything. Same family as `gh project item-list --limit N` truncating at exactly `N`. Pass `--limit` above the true count *and check the result is not exactly the limit*, or paginate the REST endpoint.
- **`grep -E 'a\|b'` matches the literal string `a|b`, not `a` or `b`.** Under ERE, `|` is already alternation and the backslash *removes* that meaning — the opposite of BRE, where `\|` supplies it. A search for two alternatives returns `0` on a file containing both. Verified: `grep -cE 'alpha\|beta'` → `0`; `grep -cE 'alpha|beta'` → `2`.

Both belong to the family: **a mutation that never applied, a restore that never restored, and a genuinely surviving mutant are the same green.** The only defence is to make the instrument prove it can move — plant, see red, restore, see green, and hash the file at both ends.

### A failure message names the symptom, not the constraint

`TestRegistryIsTheSoleDeclarer` reds on `EXIT_MALFORMED_IDS = 5` colliding with `VALIDATION_FINDINGS = 5`. The obvious reading is *"pick a free number."* Measured against merged `main`, in a blob-verified sandbox:

```
unmodified                     62 passed          <- control
EXIT_MALFORMED_IDS = 5         2 failed
EXIT_MALFORMED_IDS = 9         2 failed           <- a FREE code. still reds.
restored (blob 0f6689b1)       62 passed          <- control
```

The guard objects to a **declaration outside the registry**, at any value. Renumbering clears the collision the reader inferred and not the constraint the guard enforces. Before acting on a red, run the fix you are about to make and confirm it goes green — **a diagnosis that explains the failure is not the same as one that would remove it.**

### `git -C <dir> hash-object <relative-path>` hashes the wrong file, in both directions

The `-C` flag makes git resolve the **relative path** against `<dir>`, not against your cwd. A plant-and-restore check written as `git -C "$WORKTREE" hash-object src/x.py`, run while inspecting a *sandbox*, silently hashes the worktree's copy:

```
$ git -C sandbox hash-object f.txt   -> d97f014c   (sandbox/f.txt: "SANDBOX CONTENT")
$ git -C .       hash-object f.txt   -> 30cf26ad   (./f.txt:       "WORKTREE CONTENT")
```

The engineer who hit this had `plant applied: YES` (vacuously true — that file always differs from `main`) and `restore: SILENT FAILURE` (vacuously false). **Both readings were meaningless, and one of them looked like a real bug.** Use `git hash-object -- "$ABS_PATH"`.

The repair is the general lesson, not the flag:

> **Validate the instrument in both directions before believing either.** Mutate the file — it must report DIFFERS. Restore it — it must report SAME. *An instrument that cannot report sameness cannot report difference.*

A one-sided control (plant, see red) proves the detector fires. It does not prove the detector is *pointed at your file*. This is [[feedback_verify_the_referent_not_the_value]] territory: the hash was correct, of the wrong object.

### The rule is not the instance

A brief said *"import the alias form, precisely as da#372 did it."* Measured on `main`: `_cmd_load`'s executable exits are all `ExitCode.X`; the alias form appears only in `_cmd_resolve`'s function-local import, and the one `EXIT_LOAD_FAILED` inside `_cmd_load` is **prose in a comment**. The brief's *rule* — "be consistent with how `cli.py` does it" — was right. The *instance* attached to it was wrong, and following the instance would have made `_cmd_load` the only function in the file mixing both forms.

The implementer followed the rule and refused the instance, showing the count. **When an instruction names both a rule and an example, the example is the part that was not measured.**

It cuts symmetrically, and toward the brief-writer first. The same implementer's own error message had told an operator to *"re-run `parse`"* — a rule (*regenerate the artifact*) stated with an unmeasured example of how to satisfy it (`parse` swallows the failure and exits `0`, so the artifact is never regenerated). Same failure, different author, caught by a third person. **An example is a claim about the world; a rule is a claim about what you want. Only one of them can be run, and it is the one nobody runs.**

## A mutation harness that edits in place can test the file it already deleted (2026-07-10, da#359)

CPython's `__pycache__` invalidation keys on **`(mtime, size)`**. A single-digit source edit changes neither. If the mutation and the restore land within the same mtime second — which they do, because a plant-run-restore cycle is fast — the interpreter reuses the `.pyc` compiled from the *previous* state.

Reproduced. `m.py` on disk reads `VALUE = 9`:

```
python3 run.py               -> VALUE = 1     <- stale .pyc
python3 -B run.py            -> VALUE = 1     <- -B only stops WRITING bytecode
PYTHONDONTWRITEBYTECODE=1 …  -> VALUE = 1     <- same; the existing .pyc is still READ
rm -rf __pycache__ ; …       -> VALUE = 9     <- works
PYTHONPYCACHEPREFIX=$(mktemp -d) …  -> VALUE = 9   <- works
```

**The two obvious defences do not work.** `-B` and `PYTHONDONTWRITEBYTECODE` suppress *writing*, not *reading*. A harness that sets them and believes itself isolated is measuring an artifact of the run before.

The engineer who found it (Kwesi Boateng) saw his **second plant print his first plant's error message** — the only symptom, and only visible because the two mutants had different messages. Identical mutants, or a mutant whose failure is generic, would have produced a perfectly plausible red or green with no tell at all.

Remedies, in order of trust:
1. Export a pristine tree per run (`git archive <sha>`) into a fresh directory. No cache exists to be stale.
2. `PYTHONPYCACHEPREFIX=$(mktemp -d)` — relocates the cache per run.
3. `rm -rf __pycache__` between plant and run. Works, and easy to forget in one arm of a loop.

The family: **an unapplied mutation, a restore that never restored, a scoped run that couldn't see the test, and a stale `.pyc` are four different causes of the same green.** None is distinguishable from "the guard is sound" by looking at the result. Only by making the instrument prove it moved — and by making each mutant fail *differently*, so a repeated message is a signal rather than a coincidence.

Sibling of the `git -C` trap above: there the instrument pointed at the wrong file; here it pointed at the right file's *past*.

### The visible change is not necessarily the effective change

A reviewer retracted a stale approval by editing his own comment. The banner said *"the charter fields below are deliberately renamed so the hook no longer reads this as a standing approval,"* and lines 8–10 duly showed `Verdict: Approved` where `RequestOrReplied: Approved` had been. The orchestrator quoted those three lines into a public issue as the mechanism.

The comment was 76 lines. Its last sole `---` was at line **70**. The hook reads only the trailer. **Nothing above line 70 exists as far as the counter is concerned.** Measured, both directions:

```
as posted                     Requestor=None                RoR=None       counts=False
un-rename the BANNER field    Requestor=None                RoR=None       counts=False   <- the claimed mechanism: INERT
un-mangle the TRAILER fields  Requestor=Oyunbileg Batbayar   RoR=Approved   counts=True    <- the real mechanism
```

The trailer carried `Requestor (retracted):` — a parenthetical inserted *before* the colon, which the field regex cannot match. **That** is what un-counted the approval.

The error was committed in an issue whose subject is `_trailer_block_substring` reading a different region than the reader does. The quoted lines were the part that *looked* like the mechanism, and they were in dead text.

> **An edit has a visible change and an effective change, and they need not be the same object.** Before attributing a behaviour to a diff, ask which part of the file the consuming code actually reads — then flip only that part, and only the other part, and see which one moves.

Consequence, which is why this is not a nitpick: a `latest-verdict-wins` design anticipating only the *rename* would have left the real escape hatch — trailer field-name mangling — fully in place. **A fix aimed at the visible change protects nothing.** (Aino Virtanen, main#940; she found it because her control failed.)

## A zero in a harvested corpus is not a measurement of a shape's absence (2026-07-10, main#934)

A hook resolved `cat > f <<'EOF' … EOF; gh pr comment --body-file f` by reading the heredoc out of the command string. `_HEREDOC_WRITE_RE` matched `>{1,2}` — so **append was in scope by design** — but the resolver did `found = match.group("body")` on each match, replacing rather than concatenating. `>` resets. `>>` appends. The code treated them identically.

Reproduced against the PR head, with a control:

```
disk holds a near-miss verdict (wrong field name -> gate 1 must BLOCK)

  cat >> verdict.md <<'EOF'          hook believes body = '(a footnote)\n'      -> ALLOW
  (a footnote)
  EOF
  gh pr comment 934 --body-file verdict.md

  CONTROL: same file, no heredoc     hook believes body = the near-miss verdict -> BLOCK
```

**Appending an innocuous footnote converts a BLOCK into an ALLOW**, in the hook whose entire subject is closing fail-opens.

The only defence *available* was that the 121-row harvested corpus of real invocations contains **zero** appends. Nobody advanced it — the reviewer pre-empted it in the act of blocking. And it is true only under a scope it never states. Measured, detector validated first:

```
heredoc truncates  '> … <<'   : 28    <- detector is live, can return nonzero
heredoc appends    '>> … <<'  : 0
rows containing '>>' at all   : 2     <- one is a real append redirect
```

So the corpus does not merely fail to prove appends absent — **it contains an append.** Just not of the shape the hook parses. The shape was absent from one week of one team's transcripts while the append operator was in everyday use ten lines away. A reader who does the obvious thing (`grep -c '>>'`) gets `2` and concludes the memory is wrong. **Print the scope, or the zero is unauditable** — this file's own corollary, thirty lines above the sentence that violated it. (Aino Virtanen measured it.)

The reviewer's rule:

> **A zero in a corpus harvested from one week of one team's transcripts is not a measurement of a shape's absence** — and a regex that admits `>{1,2}` is evidence its own author expected the shape.

The same reviewer then turned it on the argument that had beaten her own earlier proposal. Heredoc-first had been justified by *"7 of the 16 corpus rows resolve to paths that still exist on a developer box, so this is the common case."* That number is a property of one machine at one minute — job tmp dirs are swept continuously; she measured 15 rows and 4 live paths, not 16 and 7. It does not matter:

> **One stale file is sufficient. Disk-first would be wrong at a count of zero, because it is wrong by construction rather than by frequency.**

Frequency arguments are how a correct conclusion acquires a perishable premise. When the mechanism alone settles it, cite the mechanism — otherwise the next person re-counts, gets a different number, and reopens a closed question. Sibling: [[feedback_fixture_makes_guard_assertion_inert]] on *"does not occur"* vs *"cannot occur"*.
