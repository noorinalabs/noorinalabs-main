---
name: feedback_compare_against_the_consumer_not_the_predecessor
description: "Regression from base" is the wrong correctness test for a parser. Compare against the real consumer's ground truth (the renderer, the shell, the API) — the predecessor may itself be the bug.
metadata:
  type: feedback
last_verified: 2026-08-11
---

Wave-30 PR #1393 took **six** review rounds on one function
(`charter_trailer.strip_code_regions`, which decides what the merge gate treats as
reviewer identity). Each round found a new shape where the fix admitted something
it should not, and each was argued as a **"regression from base"** — base handled
the shape safely, head did not. That framing blocked three rounds (MF5, MF6, MF7)
and was about to block a fourth (#1417).

**It was the wrong test.** The merge-gate reviewer settled it by querying GitHub's
own renderer (`POST /markdown`, `mode=gfm`) and classifying strictly on `pre` vs
bare `code`:

- Every MF5/MF6/MF7 prefix (4- and 8-space, tab, blockquote, indent-then-quote)
  renders as a **genuine fenced code block**. The gate was reading, as literal
  trailer fields, content the author could see was code — a visible-versus-parsed
  divergence on **honest traffic**, no adversary required. Those three were real
  defects and would have blocked regardless.
- **No** #1417 prefix (form feed, vertical tab, NBSP, ZWSP, em space, ideographic
  space) renders as a fenced block — they render as inline spans. So the fixed
  predicate **agrees with the renderer**, and base's stripping of them was never
  correctness: base stripped a marker *anywhere*, which was the original bug.

So "base was safe here" was true and irrelevant. The predecessor's behaviour on
those shapes was an accident of a defect, not a specification.

**How to apply:**

- When a parser's correctness is contested, **name the consumer and test against
  it**: the markdown renderer for comment bodies, the shell for command strings,
  the API for payloads. A diff against the previous implementation only tells you
  what changed, never what is right.
- **"Regression from base" is evidence, not a verdict.** Ask whether base's
  behaviour on that shape was itself correct. If base was accidentally right for
  the wrong reason, matching it is not a fix.
- Corollary for deferral arguments: "already subsumed by an open issue" is a weak
  ground (an attacker gains nothing) and does not distinguish the shapes that
  matter. Renderer fidelity distinguished them; subsumption did not. If deferring,
  record *why this one and not the last one*.
- **Measure the candidate fix, do not reason about it.** Here `\s` looked like a
  one-character close. Measured: it fixes 11 of 13 (ZWSP and BOM are not
  Unicode-whitespace), it is a **trade** — the 11 move into the over-strip column,
  re-creating the fail-closed direction — and **the full 4,248-test suite stays
  green under either predicate**, so nothing discriminates them. Even the
  one-character version ships as a widening whose tests pass identically before and
  after, unless it brings its own fixtures.

Related: [[feedback_verify_before_claim]],
[[feedback_agent_liveness_signals_are_unreliable]],
[[feedback_shared_scratchpad_collides_across_agents]] — the wave's recurring shape
is a check that reports success while being structurally unable to detect the
failure it names.
