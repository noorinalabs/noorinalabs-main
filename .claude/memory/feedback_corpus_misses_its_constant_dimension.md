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

3. **The orchestrator repeated it immediately after warning about it.** I had put "vary the structural role, not just the token" into every reviewer brief that wave. Verifying the reviewer's claim, I built a shell oracle, held the payload starting character fixed at `:`, and measured **0 holes at head** — apparently refuting her. Varying only that one character produced **4 of 4 shells fail-open**. My refutation was itself an instance of the defect.

4. **The reviewer's own fix had the same blind spot, one layer down.** Her one-line patch closed all 24 holes *on her oracle*. The author applied it, then widened the axis **she** had just fixed — crossing payload prefix × option form × quoting — and found a second independent mechanism her patch left open: `zsh -abc '<dash-leading payload>'`, where `_consume_wrapper_options` swallows the payload *into* the option run so `operands` is empty and no `--` ever appears. Her patch recovers only payloads reaching the operand region. Measured: her fix leaves **36 holes / 36 shapes** on the widened 1,068-form oracle; the superset fix leaves **0/0**.

**That third case is the point, and the fourth confirms it generalises.** Knowing the rule does not prevent the failure, because the held-constant dimension is *invisible from inside the corpus*: nothing in a green result names what was never varied. Awareness is not a control; enumeration is. Note the progression — author → reviewer → orchestrator → reviewer-again, four parties, each blind in the axis their own corpus fixed.

**The durable form of the control (author's framing, sharper than mine): an adversarial corpus needs a declared DIMENSION list, not a shape list.** A shape list enumerates what you tried; a dimension list enumerates the space, so what you did *not* try is readable off the same artifact. Ship the dimension list with the corpus and a reviewer can find the gap without re-deriving your reasoning.

**Pin the axis so it cannot decay.** The eventual fix added payload shape as a first-class dimension (26 forms × 8 prefixes) *plus* `test_oracle_is_sensitive_to_the_payload_dimension`, asserting the new axis actually flips an answer — otherwise a dimension can be present in the matrix and inert in effect, which reads as coverage. Also worth pinning the *insufficiency*: mutation `M11` reverts to the reviewer's one-liner and fails 18 tests, so "this narrower fix is not enough" is now a permanent assertion rather than a memory.

**How to apply:**
- Before trusting a differential, **write down the dimensions it varies, then ask what is missing from that list.** Not "did it pass" — "what did it never try." For command-shaped corpora the usual axes are: interpreter, option spelling, option position, quoting, separator/operator, segment role, sink, relay, and **payload surface shape** (leading `-`, leading whitespace, empty, pure-metacharacter).
- **Treat a clean differential as evidence about the varied axes only.** Report it that way: "0 weakened across {axes}" beats "0 weakened," and it makes the gap auditable by the next reader.
- **A reviewer's job is to add an axis, not re-run the author's.** Re-running a corpus reproduces its blind spot. Both #1193 findings came from adding one dimension to an existing harness rather than building a new one — cheap, and it inherits the author's oracle.
- **When you fail to reproduce someone's finding, suspect your own corpus before their claim.** A non-reproduction is a claim about *your* setup until you have enumerated the dimensions you fixed.
- Pair with an execution oracle that can answer NO ([[feedback_ast_strip_docstrings_carries_review]] is the analogous "make the check an artifact, not a judgement" move). An oracle that always says YES makes every axis look covered.
