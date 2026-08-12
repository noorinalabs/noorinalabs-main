---
name: feedback_relay_a_reviewer_list_verbatim
description: "Relaying a reviewer's must-fix list to an author is the same verbatim-copy problem as relaying a verdict trailer — renumbering or re-describing items silently substitutes one requirement for another, and every downstream party inherits the substitution as fact."
metadata:
  type: feedback
last_verified: 2026-08-12
---

When bundling a reviewer's must-fix items into an author brief, **copy the reviewer's numbering and wording verbatim**. Do not renumber, do not re-describe, do not merge a "recommended" item into the required list.

**Why:** the author fixes what the brief says, labels the commit with the brief's numbering, and the *other* reviewer then rules on the brief's framing too. One substitution at the orchestrator becomes unanimous downstream agreement that the wrong item was discharged. Nobody is in a position to notice, because the brief is the only version of the list any of them has.

**The live case (W30, PR #1425, 2026-08-12).** The merge gate's round-2 review had four items: F4, F5, F6, and F7 — with **F7 explicitly marked *not required***. The orchestrator relayed F4 and F5 correctly, then described **F7** as "F6" and required it, and never passed the real F6. Result:

- The author fixed F7, labeled it F6 in the commit message (faithful to the brief), and did not touch the real F6.
- The second reviewer ruled "F6 discharged" against the same wrong item, inheriting the framing.
- The real F6 — a "3 of the same 11-command corpus" claim, at two sites — survived untouched, and by then **collided with the author's own F4 fix**: one line read "3 of the 6" (true) and another "3 of the 11" (false denominator), two different 3s about the same class, ~400 lines apart. Worse than either alone: a reader who checks one and stops is misled by the other.
- Caught only because the gate compared **its own numbering** against what actually landed, rather than accepting "F6 fixed" in a commit message. It cost a fourth review round on a PR both reviewers agreed was otherwise sound.

**This is the same failure as [[feedback_pr_review_verdict_format]] §8** ("COPY the canonical block verbatim — do NOT paraphrase"), one level up: there the load-bearing tokens are the trailer fields, here they are the reviewer's item numbers. Recognising it as the same shape is the point — it was not recognised in the moment precisely because the existing rule is written about *verdict blocks*, and a requirement list does not look like a verdict block.

**Rules:**
- Quote the reviewer's list structure exactly; if you add framing, add it *around* the quoted items, never instead of them.
- Preserve required-vs-recommended labels. Promoting a "recommended" item to required is a substitution even when the item is real.
- When a reviewer says "fix these N and it is an approve with no further round trip," relay **N**, not N−1 or N+1.
- Corollary for reviewers, and the thing that saved this one: on a re-review, check your **own** item list against what landed. An author's commit message naming your item numbers is not evidence those items are the ones addressed.

Cross-references: [[feedback_pr_review_verdict_format]], [[feedback_spawn_brief_protocol]], [[feedback_bundle_fixup_instructions]], [[feedback_no_head_sha_in_review_briefs]].
