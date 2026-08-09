---
name: feedback_flag_precision_decays_with_age
description: "A conservative classifier's FLAGGED list has a false-positive rate that RISES with the age of what it classifies — verified right on the fresh case and wrong on all four aged ones in the same run. The list is candidates to verify, never a batch to act on, and it is least trustworthy exactly when it is longest."
metadata:
  type: feedback
last_verified: 2026-08-09
---

`.claude/lib/check_worktree_merged.py` (the /session-start Step 0 merged-vs-unmerged
classifier, #1212) was measured across 5 worktrees in one session on 2026-08-09:

| worktree | age | verdict | truth |
|---|---|---|---|
| `S.Cardoso-506-runbook` (data-acquisition) | fresh squash-merge | `merged (content-equivalent)` | **correct** — the #1212 patch-id fallback working exactly as designed |
| `W.Mwangi+wave-29-promotion-audit-log` | aged | `UNMERGED` | false — the `wave-29.md` blob was **byte-identical** to `origin/main`'s |
| `aino-1354-memory` | aged | `UNMERGED` | false — note + section identical; only `MEMORY.md` differed and **main was newer** |
| `agent-a16cedd15fc809be2` | aged | `DIRTY` | false — 13/13 staged blobs byte-identical to `origin/main`, no untracked files |
| `agent-ae176eba584e8543d` | aged | `DIRTY` | false — 45/45 staged blobs byte-identical, no untracked files |

**1 correct / 4 false positives, and the split is exactly along age.**

**Why:** the fallback asks whether the branch's cumulative diff is present on
`origin/main`. That test decays as main moves — content that landed under a
*different commit* while unrelated later commits kept touching the same files no
longer matches as a unit. The fresh branch had nothing to decay against.

**This is not a defect, and do not "fix" it.** The conservatism is deliberate and
load-bearing: Step 0 never force-removes, so a false `UNMERGED`/`DIRTY` costs at
most a stale directory, while a false `merged` could cost work. The classifier is
correctly biased. What is wrong is *reading its output as a verdict*.

**The operational rule:** a FLAGGED list is **candidates to verify, ordered by
suspicion — never a batch to act on.** Verify content, not the flag: compare the
blobs (`git diff <branch> origin/main -- <path>`, or hash them) before removing
anything, and reset a "DIRTY" tree to HEAD first so the removal stays non-force
and the Step 0 invariant survives.

**The generalizable shape, and why it is counterintuitive:** a conservative
classifier is *least* reliable precisely when its output is *longest*. A long
FLAGGED list looks like strong evidence of a real problem; it is more often
evidence that nobody has swept in a while, and each additional day lowers the
per-item precision. So the exact condition that tempts a bulk force-remove — "look
how many there are" — is the condition under which bulk action is least safe.
Age is a free prior: sort by it and expect the old end to be noise.

Direct sibling in mechanism and in remedy: [[feedback_memory_judge_overflags_fully_stale]]
(a Haiku staleness judge's fully-stale bucket is likewise candidates, not a delete
list — 18/18 false positives). Both are conservative instruments whose output is
routinely misread as a decision. Same family as
[[feedback_silent_zero_is_not_a_measurement]] (verify the instrument before the
reading) and [[feedback_pr_body_table_is_a_claim]] (a classifier's own output is a
claim; re-derive it before acting).
