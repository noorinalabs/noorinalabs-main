---
name: feedback_fold_in_or_defer_a_gate_finding
description: "Deciding whether a merge-gate finding gets folded into the PR or filed as debt: prevalence alone gives wrong answers. Ask whether a WORKING script could contain the shape, and which direction it fails — a silent miss and a self-evident over-block are not comparable."
metadata:
  type: feedback
last_verified: 2026-08-03
---

Every merge-gate finding forces a fold-in-or-defer call, and the reflex reason — *"how common is this shape?"* — is not sufficient on its own. Wave-29 made four of these calls on one PR (#1302) and prevalence alone would have got two of them wrong.

**Three questions, in order:**

1. **Could a *working* script contain this shape?** Not "is it common" — "does it ever appear in code someone wrote intending it to work." A shape that cannot function in a real shell will not appear in real usage, so a false positive on it costs nothing.
2. **Which direction does it fail?** A **silent miss** (the gate allows what it should block) and a **self-evident over-block** (the gate refuses something obviously legitimate) are not comparable severities. The first is invisible until exploited; the second announces itself and is correctable on the spot by the person it blocks.
3. **Only then, prevalence.**

## The four calls (PR #1302, 2026-08-03)

| finding | shape | call | why |
|---|---|---|---|
| **#1305** `export g=git` | ordinary, idiomatic | **fold in** | same bare literal one token right; most idiomatic spelling of the bug being fixed |
| **#1311** `for …; do g=git; $g …` | ordinary; anyone writes it | **fold in** | silent miss — the gate *allowed* a real commit. Higher prevalence than #1305, same direction |
| **#1308** `typeset` / `readonly` | valid, measurably live | **defer** | genuine but low prevalence; distinct axis from the fix in flight |
| **#1306(c)** unexported var in a single-quoted child payload | **cannot work in a real shell** | **defer** | pure over-block, and no working script contains it — exporting or double-quoting are the only ways to make it function |

The reviewer's formulation on the last row, which is the durable part:

> the prevalence argument doesn't transfer — this shape requires deliberately referencing an *unexported* variable inside *single* quotes passed to a child, a combination that can never work in a real shell, so it's not something a working script would contain. It's also a pure over-block, not a silent security miss.

**How to apply:** state which of the three questions decided it, in the PR body or the issue. "Deferred as lower priority" is not a reason; "deferred because no working script can contain this shape, and it fails in the announce-itself direction" is one a future scoper can check. And when a finding arrives mid-review, **the fold-in call belongs to the merge gate, not to the finder** — surfacing it and letting the gate decide is correct, and the reviewer who does that is not being indecisive.

**Corollary on over-blocks:** an over-block is cheap *only* when it is self-evident. An over-block on a shape people legitimately write is an outage, and belongs in the fold-in column regardless of direction — this hook gates every commit in the org.

Related: [[feedback_widened_charclass_truncates]] (grade the two failure directions separately — a silent allow is degraded advice, an unblockable false block is an outage), [[feedback_pr_review_verdict_format]].
