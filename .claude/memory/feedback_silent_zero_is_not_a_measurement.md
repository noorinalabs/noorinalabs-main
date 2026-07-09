---
name: feedback_silent_zero_is_not_a_measurement
description: "Verify the instrument before trusting the reading. Run the detector on BOTH classes and require it to separate them before reading the number you care about — a zero, a control group, and even a 10x lift are each individually insufficient. Nine instances in one day (2026-07-09)."
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

Two weaker versions were tried on a single problem and each was falsified within hours.

**v1 — "can the probe return nonzero?"** Catches a probe that cannot fire. Misses one that always fires. Same day: a detector for "does this hadith's matn contain an isnad?" keyed on the Arabic tokens `عن`/`قال` called **97.2%** of a target set positive, implying ~160k recoverable chains. Those tokens saturate ordinary Arabic prose — against a **control** of rows whose matn is chain-*free* by construction the base rate is **85.6%**. Lift ≈ 1.0. The probe's answer was fixed before it saw the data.

**v2 — "always run the control group."** Catches a probe that cannot return **low**. Misses one that cannot return **high on a known positive**. Re-keying on strict isnad openers (`حدثنا`/`أخبرنا`/`سمعت`) gave **7.9%** control vs **79.2%** test — a 10× lift, a clean control, and a confident conclusion (`159,558 × 0.792 = 126,398` recoverable chains) that was **wrong twice over**. Checking *recall* against the **positive** class — the 485,285 rows known to carry an isnad — returned **0 / 485,285**, because the source strips the transmission opener from every row it successfully tags. The detector could never fire on a true positive. Opener *presence* is strong evidence; opener *absence* is none at all. So recall is not calibratable here, and the product silently assumed recall = 1 and FPR = 0.

The corrected estimate needed a detector spanning both of the corpus's **two isnad conventions** — receipt-verb (`حدثنا …`; 98.8% of `lk`) and bare-name-then-`عن` (98.5% of `tusi`, **0.0% receipt verbs** in sanadset's tagged rows). Two opener-only probes disagreed (79.2% vs 66.5%) because *neither could see the second convention*. `opener OR (≥2 standalone عن in the first 25 tokens)`, calibrated on the positive **and** negative class of **each** convention, yields ≈**122,013** — still a lower bound, and now labelled as one.

Two corollaries, both earned the same day:

- **Never let the artifact grade its own homework.** A dataset's own annotation (`Sanad = "No SANAD"`) is the corpus author's *claim*, not your measurement. Here it recorded their tagging pipeline failing on 165,701 rows — not the absence of a chain. An issue was nearly closed as a duplicate on that basis.
- **Never audit a defect with an instrument downstream of it.** A 97.1% "extractability" figure was produced by the very matn-mining fallback (da#369) whose output it was meant to audit.

**A high number is exactly as suspect as a zero.**

**Why:** every one of these returns the value you would also get from the healthy state. The signal and the null result are the same string. Unlike a crash, nothing prompts you to look. These cost more than loud failures precisely because they arrive wearing the costume of a result.

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

Sibling: [[feedback_passing_repro_masks_bug]] (a *repro* that cannot go red) and [[feedback_test_mock_masks_prod_failure]] (a *test* that cannot go red). This memory is the *measurement* case: a probe that cannot go nonzero. Same root: **verify the instrument before trusting the reading.**
