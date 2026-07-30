---
name: feedback_corpus_misses_its_constant_dimension
description: "A differential corpus finds defects only in the dimensions it VARIES — whatever it holds constant is invisible by construction, and knowing this rule does not prevent repeating it"
metadata:
  node_type: memory
  type: feedback
last_verified: 2026-07-30
---

A test corpus that varies N dimensions and holds one fixed will pass cleanly while a defect sits in the fixed one. The corpus is not weak — it is **blind by construction**, and its green result is what makes the blindness convincing.

**Three independent instances, wave-29:**

1. **#1155, three consecutive rounds.** Round 1 varied the sink, round 2 the segment role, round 3 the operator. **Each round's defect sat in whatever the previous corpus held constant, and none was reachable from the round before.** Recorded at the time as one structural property, not three separate misses.

2. **#1193.** The author's `FORMS` table varied interpreter, cluster spelling, option position, quoting, and segment role — five dimensions — and held **payload surface shape** fixed. It proved 8 bypasses closed and 0 weakened across 85 shapes and 7,616 real commands. A reviewer added the one missing dimension and found **24 remaining fail-open holes across 6 shapes**: a command string that merely *starts with `-`* was dropped by a `_looks_like_flag` filter applied across the operand region. Same contract, same shells, one more axis.

3. **The orchestrator repeated it immediately after warning about it.** I had put "vary the structural role, not just the token" into every reviewer brief that wave. Verifying reviewer A's claim, I built a shell oracle, held the payload starting character fixed at `:`, and measured **0 holes at head** — apparently refuting the finding. Varying only that one character produced **4 of 4 shells fail-open**. My refutation was itself an instance of the defect.

4. **Reviewer A's own fix had the same blind spot, one layer down.** A's one-line patch closed all the holes *on A's oracle*. The author applied it, then widened the axis **A had just fixed** — crossing payload prefix × option form × quoting — and found a second independent mechanism it left open: `zsh -abc '<dash-leading payload>'`, where `_consume_wrapper_options` swallows the payload *into* the option run so `operands` is empty and no `--` ever appears. A's patch recovers only payloads reaching the operand region. Measured on the widened 1,068-form oracle: A's fix leaves **36 holes / 36 shapes**; the superset fix leaves **0/0**. Reviewer B, measuring independently on a 418-form ladder, scored the same patch at 20 holes → 0 — different corpus, same conclusion.

**That third case is the point, and the fourth confirms it generalises.** Knowing the rule does not prevent the failure, because the held-constant dimension is *invisible from inside the corpus*: nothing in a green result names what was never varied. Awareness is not a control; enumeration is. Note the progression — author → reviewer → orchestrator → reviewer-again, four parties, each blind in the axis their own corpus fixed.

**Corpus SIZE is itself a dimension, and this is the least obvious one.** Same PR, same base→head comparison, **two different reviewers**, two sweep sizes:

| corpus | reviewer | result | reads as |
|---|---|---|---|
| 17,252 commands | reviewer A | 175/175 BLOCK, **0 verdict changes** | "no effect on real traffic" |
| 74,782 commands (1,830 transcript files) | reviewer B | **0 weakened, 4 strengthened** | live-trace evidence the fix catches real bypasses |

*(Provenance matters here and was initially recorded wrong: these are **two independent reviewers**, not one reviewer's two passes. That makes the lesson stronger, not weaker — two competent people sized the same sweep an order of magnitude apart and drew opposite conclusions about what it proved, with nothing in either result flagging the difference.)*

The four are genuine true positives — three `bash -euo pipefail -c '… git commit …'` and one `bash <script>` that commits. The small sweep was not wrong, but **"0 changes" and "4 true positives found" are very different evidentiary claims**, and only the larger corpus distinguishes "the fix is inert on real traffic" from "the fix fires on real traffic and nothing regressed."

> **A corpus reports its own adequacy; it cannot report what it was too small to hold.** — reviewer B's formulation, and the crispest statement of the whole property. Structurally the same defect as a held-constant axis, one level up: the 17,252-command sweep read *exactly* as clean as the 74,782-command one.

**These are two different sample-size questions and the org has been treating them as one:** a corpus sized to **price false positives** is roughly **10× too small to find rare true positives**. Note which way the error ran here — the clustered-value-letter path (`bash -euo pipefail -c`) had been justified from a *synthetic* oracle, and turned out to be the shape actually live in recorded traffic. State which question your sweep answers. Applies to every hook PR that cites an FP sweep as acceptance evidence.

**The durable form of the control (author's framing, sharper than mine): an adversarial corpus needs a declared DIMENSION list, not a shape list.** A shape list enumerates what you tried; a dimension list enumerates the space, so what you did *not* try is readable off the same artifact. Ship the dimension list with the corpus and a reviewer can find the gap without re-deriving your reasoning.

**Countermeasure for the corpus-size case: give the sweep a positive control.** Seed N known-true-positive shapes into the real-traffic corpus and **report recall alongside the verdict-change count**. A clean run then distinguishes *"nothing there"* from *"too small to contain anything"* — which is precisely what the 17,252-command sweep could not do.

> **A sweep that cannot fail is the same failure mode as a test that cannot fail.** That is the mutation discipline this org already enforces one layer down; a real-traffic sweep is currently exempt from it for no principled reason.

**Pin the axis so it cannot decay.** The eventual fix added payload shape as a first-class dimension (26 forms × 8 prefixes) *plus* `test_oracle_is_sensitive_to_the_payload_dimension`, asserting the new axis actually flips an answer — otherwise a dimension can be present in the matrix and inert in effect, which reads as coverage. Also worth pinning the *insufficiency*: mutation `M11` reverts to reviewer A's one-liner and fails 18 tests, so "this narrower fix is not enough" is now a permanent assertion rather than a memory.

**How to apply:**
- Before trusting a differential, **write down the dimensions it varies, then ask what is missing from that list.** Not "did it pass" — "what did it never try." For command-shaped corpora the usual axes are: interpreter, option spelling, option position, quoting, separator/operator, segment role, sink, relay, and **payload surface shape** (leading `-`, leading whitespace, empty, pure-metacharacter).
- **Treat a clean differential as evidence about the varied axes only.** Report it that way: "0 weakened across {axes}" beats "0 weakened," and it makes the gap auditable by the next reader.
- **A reviewer's job is to add an axis, not re-run the author's.** Re-running a corpus reproduces its blind spot. Both #1193 findings came from adding one dimension to an existing harness rather than building a new one — cheap, and it inherits the author's oracle.
- **When you fail to reproduce someone's finding, suspect your own corpus before their claim.** A non-reproduction is a claim about *your* setup until you have enumerated the dimensions you fixed.
- Pair with an execution oracle that can answer NO ([[feedback_ast_strip_docstrings_carries_review]] is the analogous "make the check an artifact, not a judgement" move). An oracle that always says YES makes every axis look covered.

---

## Provenance caveat — why this note says "reviewer A / reviewer B"

Two **distinct agents** reviewed PR #1193 under the **single roster persona `Weronika Zielinska`** (an orchestrator spawn-routing error: one persona assigned to one PR twice). Both produced real, independent, competent work — but the review record cannot tell them apart, and the first draft of this note narrated their combined measurements as one reviewer's arc.

That is why attributions here are role-labelled rather than named. The distinction is load-bearing for the corpus-size lesson specifically: the 17k-vs-75k contrast is **two people disagreeing about sufficiency**, not one person improving on themselves.

**The gate was not compromised** — `validate_pr_review` counts distinct `Requestor` values, which were exactly `["Lucas Ferreira", "Weronika Zielinska"]` = 2. It *under*-counted rather than over-counted. The dangerous general case is the inverse: **three agents posting under two personas would satisfy a 2-reviewer gate while only two independent reviews exist.** The gate counts personas; the safeguard assumes agents. Tracked as its own issue.
