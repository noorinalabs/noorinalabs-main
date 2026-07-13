---
name: feedback_silent_zero_is_not_a_measurement
description: "Verify the instrument before trusting the reading. Run the detector on BOTH classes and require it to separate them before reading the number you care about — a zero, a control group, and even a 10x lift are each individually insufficient. A high number is exactly as suspect as a zero."
metadata:
  type: feedback
---

> Compacted 2026-07-13 (#944/#931) from a 142 KB long form; full narratives in git history at this path.

## The law

**A probe that cannot fail proves nothing.** `0`/`NULL`/empty/exit-0 is evidence only after you've shown the probe could have returned something else. **Run the detector on BOTH classes (known-positive AND known-negative), require it to separate them, then read the number.** Weaker forms falsified: "can it return nonzero?" misses a detector that always fires (97.2% test vs 85.6% control — lift ≈ 1); "run a control" misses one that can't fire on a true positive (10× lift, recall 0/485,285). Report bounds and their direction; `population × rate` without measured recall/FPR is fiction. **A high number is exactly as suspect as a zero.** (Detector-construction detail — two-convention corpora, never average two instruments — in history.)

Operational form (main#957): **every "all clear" must first prove it looked at something** — assert the set non-empty AND complete before reading its verdict (`pending==0` on an empty rollup, actionlint on an empty file set, `python -` without `-i`: healthy and null emit the identical string). **Recognition, not knowledge, is the scarce thing** — five people wrote instances the day they were teaching the class. People looking hard is not a control.

## Probe-level instances (2026-07-09)

- `sudo du …/*`: glob expands unprivileged → empty args → `0`; wrap in `sudo sh -c`. Any no-arg-capable command counts the empty set silently.
- Misspelled Neo4j property → NULL on every row, no error; enumerate `keys(n)` first ([[reference_graph_ops_cypher_shell]] §3).
- Killed query read as an answer (zero bytes → "no cycles"; real 23,139). Emit an `RC=` sentinel; its ABSENCE = "did not complete."
- Quoting: cypher-shell `"`-prefixes lines → `grep -c '^nar:'` = 0. Inspect one raw line first. A gate printing a constant (hidden `LIMIT 100`) — report the cap with the number ([[feedback_no_head_in_surface_enumeration]]).
- Classics: `pytest | grep '^FAILED'` finds nothing (ANSI — `--color=no`); `gh issue list --jq length` pages at 30 ([[feedback_gh_cli_gotchas]] §4); `grep -E 'a\|b'` matches the literal `a|b`; `git -C <dir> hash-object <rel>` resolves against `<dir>` — use absolute paths, hash both ends of any plant/restore, and validate BOTH directions (mutate→DIFFERS, restore→SAME).

## Scope and referent

- **The control must come from OUTSIDE the scope you trust** (da#383): an inside-scope control proves the scan sees, not that the scope is right. Pick one you'd expect to MISS if the scope is too narrow.
- **Print the scope — identity, not cardinality** (da#383): a basename is a label, a path is a name (`f.name` collapsed nine snapshot copies into "four places," citing pre-scrub defects as proof of the feature). Too-WIDE scope is the worse error: false positives with the authority of exhaustiveness.
- **Same identifier, different referent** (da#362/#372): green rollup of a dead head; AST walk reading an import's `main` value; approvals read off a neighbouring PR. A name resolves in a scope nobody prints. Blast radius = import graph, not diff; a clean auto-merge is not a correct merge — run the suite.
- **Cite by stable name, never ordinal** (ip#130): per-run vertex numbers fabricate confirmations AND refutations — the false refutation reverts a correct fix. A harness measurement carries the harness's costs; name the era of any log cited.
- **The log contains your prose about the bug** (ip#130): attestations embed commit messages — a grep for `CACHED` found the fix's own bug description and nearly reported the fix inert. Scope greps to the step's own stream.
- **Verify the claim AS WRITTEN** (da#383): a better instrument aimed at an adjacent proposition lets a false premise survive review. Name the predicate behind every number; a correction-checking instrument must not text-match the thing corrected. A zero in a harvested corpus is not a measurement of a shape's absence — the corpus CONTAINED the shape (main#934: a `>>` heredoc append flipped BLOCK→ALLOW).

## Guards and gates

- **Levels 1–4** (deploy#577/#584): exists → is called → **returns the right answer** (a textual "it is called" test shipped a never-matching regex; `restore.sh latest` inert on main) → **what happens when it CANNOT EVALUATE?** `|| true`, `2>/dev/null`, bare `$(cmd)` collapse "I could not look" into a verdict; make it a third state.
- **A guard is only as good as the weakest `|| true` upstream** (deploy#584): a fail-open feeding it deletes it for exactly its failure modes. Fix the CLASS, not the reported instance.
- **Failure, commentary, data are three channels** (deploy#584): `2>&1` into a parsed-per-line variable promotes NOTICEs into phantom records (safe when grepping one known token); the regression fired on SUCCESS, the untested path.
- **A negative passing for the wrong reason has stopped testing** (deploy#577): a new upstream gate out-rejected the truncation fixtures — still exit 1, truncation untested. `expect_fail` must assert WHICH guard fired; a guard is pinned by its call site, not its existence.
- **Integrity ≠ provenance** (deploy#574/#584): a checksum binds a file to ITSELF; three independent `find|head -1` assembled a TORN restore from different runs past every guard. Bind multi-artifact consumers to a common run id (producer names it, consumer verifies THAT run; never read the required set from the manifest's own field). Determinism ≠ coherence (`sort -r|head -1` ×3 tears identically). A fixed-name manifest over multiple runs is a race won by the least trustworthy run — attestation granularity must match the attested thing.
- **A test that paraphrases the producer's format tests the paraphrase** (deploy#584): feed the producer's actual bytes. A paraphrase in the PRODUCT is worse — a rename silently NARROWS the parser; anchor on the smallest rigid token, refuse to model the rest. Producer-bound fixtures pin the PRESENT — also exercise shapes the format is ALLOWED to take, with enough decoys to fail deterministically.
- **Class separation is insufficient when a VALUE is read** (deploy#584): local-time mtimes parsed as UTC deflate ages — stale reads fresh while classes still separate. Calibrate the VALUE; bound it BOTH sides (one-sided `-gt` sees only the loud direction); an impossible reading is `instrument_error`, never the benign class. Calibrate on the REAL backend. Never `skipif` the test that IS the guard.
- **Mutation pre-flight** (deploy#574/#591/#580): prove the mutant LIVE or "caught" means nothing; on red, confirm the INTENDED assertion failed; count mutated sites; run in an ISOLATED frozen tree (a mid-run `git stash` healed one mutant; stale `__pycache__` keys on (mtime,size) ran another's past — `-B` only stops writes); confirm the mutant present AFTER. `git diff` is empty on untracked files — `cmp -s` against a pristine copy both ways. **A result in your favour earns more scrutiny, not less.**
- **The falsifier must reproduce the failure MECHANISM** (da#429): truncate-after-write passes under both the tally and the read-back it forbids — write the bad implementation and require the test to kill it. **A measurement of the bug is not a measurement of the fix** (deploy#591): the prescribed `grep -m1` swapped one SIGPIPE-er for another; enumerate the shape; the fixture must distinguish your fix from the naive fix.
- **A config key is an instrument** (ip#130): `no-cache-filter` vs `no-cache-filters` — Actions silently drops undeclared `with:` keys; actionlint doesn't check action schemas. Confirm the consumer declares the key; an inert fix discredits the correct diagnosis. A revert condition ships WITH the instrument that evaluates it — dispatchable, provably red-able (ip#138).
- **A harness under a weaker runtime mode tests a different program** (deploy#584): `set -uo pipefail` minus `-e` missed a crash; match production strictness. Shape-rule: `VAR="$(grep …)"` that can match nothing CRASHES under `-e`+`pipefail` (per-command contracts: [[feedback_enforcement_hierarchy]]).
- **Textual tests misrepresent their evidence kind** (deploy#584): a source-grep greens through broken behavior and reds on legitimate change — declare which guard carries the weight. A guard whose healthy output looks like a failure trains readers to scroll past. Silent fail-closed selects against the careful (main#940) — a parser that sees its shape but extracts nothing should say so.
- **A failure message names the symptom, not the constraint** (da#387): run the fix you're about to make and watch it go green first.

## Claims, relays, and time

- **"I ran it" is a claim nobody audits** (da#383): a measurement carries the sha and the command, or it is an opinion. **A relay is evidence of nothing** (deploy#584): five fixes reported where three were claimed — read the artifact at the head you name; write "he reports" unless you ran it.
- **A state is not a history** (deploy#584, ×4 in one review): the tree cannot tell you what someone knew when they acted; before any "X knew Y and did Z anyway," print the timestamps. A false exoneration is as corrosive as a false claim. Reproduce before you escalate. Absence of a stop is not a go (da#372): print the field.
- **The correction is not a safe place to stand** (da#387): a retraction ships a fresh claim under its own credibility, and the second instrument never gets a control. **The sentence that flatters the frame is the sentence to measure** — especially a number gifted pre-argued (four cache costs, each measured in the wrong arm; the durable answer was structural).
- **A reading and a forecast are different kinds** (da#392): future-tense prose can't redden; a true conclusion on a dead reason (ip#138) reads as verified and isn't — when a change kills a decision's REASON, the comment stating it is in the blast radius. "Changes behaviour" is a two-place predicate — name both trees (da#372).
- **A hand-merged generated file describes no tree that exists** (da#372): resolve by running the generator on the MERGED tree.
- **The rule is not the instance** (da#372): the example attached to a rule is the unmeasured part. **The tell is never that a claim looks wrong — it is that nobody ran it** (deploy#593); prefer the fix that removes the dependency on the claim over the experiment confirming it today.
- **Incidental satisfaction is not satisfaction** (deploy#586): a threat closed by accident is an unlabelled load-bearing control — record WHAT protects. Check an unimplemented ask is implementable before calling it debt.
- **Nothing tests prose** (deploy#588): CI is green on a docs PR whatever it says; a wrong runbook stops the operator thinking. Trace every factual row to the emitting line; orchestrator drafts carry authority and deserve MORE checking.
- **Refuse rather than redact** an unrecoverable leak (`RCLONE_DUMP=auth` base64 evades masking — [[reference_pipeline_b2_publish_key]]).
- **Stop while it is correct** (deploy#584): the fix-introduces-a-bug rate is measurable and nonzero — another round is not free. Carve-out: a path that silently DISARMS the guard the PR adds is not adjacent hardening; fix it now. Count the SHAPES in a fixture set, not the fixtures.
- **The third gate — the right SUBJECT?** (da#387): a plant-applied assertion proves the instrument sees; a count pin proves it ran; nothing proves you pointed it at the right thing — assert the plant is in the subject the test imports.

Siblings: [[feedback_passing_repro_masks_bug]], [[feedback_test_mock_masks_prod_failure]], [[feedback_fixture_makes_guard_assertion_inert]], [[feedback_drop_gate_bidirectional_ab]] (the metric itself as the blind instrument), [[feedback_verify_diagnosis_before_delegating]], [[feedback_push_pipe_masks_rejection]].
