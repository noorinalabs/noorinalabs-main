---
name: feedback_pr_body_table_is_a_claim
description: "A measurement table in a PR body / review comment / report is a CLAIM and needs the same verify-before-claim discipline as a status report — code and tests get measured, prose is where the unverified number gets in."
metadata:
  type: feedback
last_verified: 2026-08-03
---

Verify-before-claim is usually applied to status reports and gate verdicts. It applies just as hard to the **measurement tables inside PR bodies, review comments, and agent reports** — and that is where it actually fails, because the code and tests are being run while the prose is being written from memory.

**Observed 2026-08-03, wave-29, PR #1277 (#1180), self-caught by Nadia Khoury.** Her PR body reported `origin/main` → "all 3 names resolved, exit 0". She never ran it: she inverted a table in #1180's *issue* body — where that row describes PR #1178's head `256f79a0`, not `main` — and presented it as her own measurement. Her mutation harness (0/9 survived) and her 21-wave regression sweep were genuinely run throughout. The one fabricated number was the one that only ever lived in prose.

**The correction mattered.** Measured, `main` gives `2/3 UNRESOLVED, exit 1` on that matrix — but for an unrelated reason (#1181's persona filter rejects two of the three names), so **the issue's own worked example masks the defect the issue was filed about**. Isolated, the true picture was *worse* than claimed: `{"co_implementer": "Nurul Hakim"}` passes `main` at exit 0 while the same person as `implementer` is blocked — the W27/W28 cross-repo-implementer failure re-admitted by renaming the slot key.

**How to apply:**
- Every number in a PR body, review comment, or report must come from a command run *for that sentence*. If it came from an issue, another agent's report, or an earlier session, cite the source instead of restating it as your own measurement — and re-run it before relying on it.
- **A worked example inside an issue is the author's claim, not a measurement.** Re-run it before using it as a baseline; #1180's example was both stale and masked.
- A PR-body edit is **silent** — GitHub sends no notification. Correcting one requires a visible follow-up comment, or reviewers keep reading the original.

**Why:** the failure is invisible to every gate the org has. CI, mutation harnesses, and the review gate all check the code; nothing checks the prose describing it, and a reviewer reading "measured against main" reasonably treats it as measured. Same family as [[feedback_silent_zero_is_not_a_measurement]] — a plausible number that no instrument produced.

Related: [[feedback_verify_before_claim]], [[feedback_pr_review_verdict_format]] (§7 counting discipline: never trust "Approved, posted" — re-derive), [[feedback_scratchpad_shared_across_agents]] (the harness-level sibling found in the same batch; distinct cause, same symptom of an unverified number reaching a report).
