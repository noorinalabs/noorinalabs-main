---
name: feedback_silent_zero_is_not_a_measurement
description: "A zero/NULL/empty result from a command that can silently receive no input is NOT a measurement — it is indistinguishable from success. Confirm the probe CAN produce a nonzero before believing a zero. Four independent instances in one day (2026-07-09)."
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

**Why:** every one of these returns the value you would also get from the healthy state. The signal and the null result are the same string. Unlike a crash, nothing prompts you to look. These cost more than loud failures precisely because they arrive wearing the costume of a result.

**How to apply:**
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

Two siblings from the same night:

- **The instrument that confirms a correction must not match the text of the thing being corrected.** Grepping for a retracted sentence finds the retraction quoting it. (Kwesi Boateng — he nearly re-fixed something already fixed.)
- **A citation that names a file for some rows and leaves others unattributed lets the reader infer the named file for all of them.** Partial attribution certifies what it omits. Same shape as the partial honesty label in [[feedback_fixture_makes_guard_assertion_inert]].

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

Sibling: [[feedback_passing_repro_masks_bug]] (a *repro* that cannot go red) and [[feedback_test_mock_masks_prod_failure]] (a *test* that cannot go red). This memory is the *measurement* case: a probe that cannot go nonzero. Same root: **verify the instrument before trusting the reading.**
