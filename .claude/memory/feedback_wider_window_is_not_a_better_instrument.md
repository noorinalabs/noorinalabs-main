---
name: feedback_wider_window_is_not_a_better_instrument
description: "A correction produced by re-running a broken classifier over MORE data yields a more confident wrong answer, not a less confident one — and it arrives dressed as diligence, delivered to the person who was right."
metadata:
  type: feedback
last_verified: 2026-09-04
---

Measured on PR #1488 (2026-09-04). A reviewer found off-allowlist direct commits over 200
commits and reported **6**. I re-derived over the same window and reported **16** — as a
*correction to her*, with a category table naming hooks, lib, skills, charter and CI, and with
the explicit note that my number was "worse than hers and I'm reporting mine."

**Every row of that table dissolved.** Ten of the sixteen were **squash-merged PRs** — fully
reviewed, merged through the gate. Before `--squash` was banned org-wide, a squash-merged PR
lands on `main` as a single **non-merge first-parent commit**: indistinguishable from a direct
push *by shape*, distinguishable *by provenance*. My classifier tested shape. Verified per
commit with `gh api repos/{o}/{r}/commits/<sha>/pulls`, where each returns a merged PR whose
`merge_commit_sha` **is** the commit: #1126 #1127 #1128 #1130 #1136 #1143 #1154 #1155 #1156 #1173.

**The rule.** A wider window is not a better instrument. Widening the sample multiplies
whatever the classifier gets wrong — so the output arrives *more* confident and *better
evidenced*, which is exactly what makes it land. Two reviewers converged on 6 independently by
different methods; the shape-based scan produced 16 twice.

**Three compounding failures worth separating, because only the first is ordinary:**

1. The original overstatement was **sampling error** — cheap, caught, owned.
2. The *correction* re-ran the same broken classifier. **This is the expensive one**: a
   correction carries more authority than a first claim, and is aimed at whoever was right.
3. It was then committed into the **charter** — into the passage a future widener is told to
   reason *from*. The false version argued the rule rested on a fragile one-month trend, i.e.
   it manufactured the exact argument someone would use to dismiss the rule.

**The tell I had and ignored.** The reviewer named this trap in §1 of the verdict I had
already read. Knowing the mechanism does not prevent it — cf.
[[feedback_corpus_misses_its_constant_dimension]], same property.

**The missing-cause tell.** I wrote *"I looked for a policy commit explaining the cutoff and
found none; the tightening appears emergent."* The commit was **in my own evidence list**:
`2d8bd91` "no `--squash` on ANY base", eleven minutes after the last squash-merge, zero
squash-shaped commits after. **A discontinuity you cannot explain is a hypothesis about your
instrument, not a finding about the world** — and "I searched and found nothing" is the moment
to re-read your own evidence rather than to publish.

**Operational checks, in order of cheapness:**

- Before widening a window, ask **what the classifier cannot distinguish** — not whether it
  ran. Mine could not separate "squash-merged PR" from "direct push", and I never asked.
- **Name the population with the number.** The same repo gave 70/76 (all first-parent), 69/75
  (non-merge), 65/70 (PR-unassociated). None wrong; three populations. Two reviewers and I
  spent a round reconciling numbers that only disagreed about their denominator —
  [[feedback_state_the_denominator_with_the_number]], hit **twice** in one PR.
- Prefer **provenance over shape**: `commits/<sha>/pulls` over parent-count, every time.
- A correction deserves *more* verification than the claim it corrects, not less. Mine got less
  because it felt like diligence.

Sibling: [[feedback_silent_zero_is_not_a_measurement]] — verify the instrument separates the
classes *before* reading the number. This is that rule failing on a **non**-zero number, which
is the harder case: a confident 16 with a supporting table does not look like an instrument
failure, and a zero at least invites suspicion.
