---
name: feedback_patch_id_after_rebase_not_ancestry
description: "After a rebased head move, an ancestry check FAILS and a two-dot diff OVERSTATES the delta — use `git patch-id --stable` to prove the reviewed content survived, then diff from the rewritten base"
metadata:
  node_type: memory
  type: feedback
last_verified: 2026-07-30
---

When a PR's head moves and the branch was **rebased**, the two obvious ways to answer *"what changed since I reviewed?"* both mislead:

| check | on a rebased head | why |
|---|---|---|
| `git merge-base --is-ancestor <old> <new>` | **fails — correctly** | history *was* rewritten. This is a true answer, not a broken check. It just doesn't tell you whether content survived. |
| `git diff <old-head>..<new-head>` | **overstates** | drags in every unrelated commit the branch was rebased *onto* |

**Do not read the ancestry failure as "the check is wrong."** It is answering "was this additive?" and the answer is genuinely no. What it cannot answer is "did my reviewed content survive?" — a different question needing a different instrument:

```bash
git show <old-sha>      | git patch-id --stable   # pre-rebase commit
git show <rewritten-sha>| git patch-id --stable   # same commit after rebase
# identical hash => the reviewed content survived byte-for-byte
git diff --stat <rewritten-sha> <new-head>        # the TRUE delta
```

**Measured 2026-07-30, PR #1187.** Head `061db3c` → `3e0e5e8`. Ancestry: **NO — history rewritten**. Two-dot diff: **6 files** (five of them unrelated memory/ontology commits from `main`). patch-id on `061db3c` and its rewritten twin `eac963c`: **identical** (`9defbb2c…`). True delta `eac963c..3e0e5e8`: **1 file, 1 line**.

**Why it matters more than it looks.** A reviewer who trusts the two-dot diff either re-reviews content the author never touched, or **misattributes another author's commits to this PR**.

**The orchestrator error here was not the instrument — it was asserting the premise.** I told both #1187 reviewers to "confirm ancestry (`061db3c` → `3e0e5e8f`), additive, no force" **without having checked it myself**. There *had* been a force-push. Both reviewers ran the check, got the correct failure, and correctly concluded a rewrite had occurred; one pulled GitHub's literal `head_ref_force_pushed` timeline event (`03:47:03Z`, 4m47s after the ChangesRequested at `03:42:16Z`) rather than inferring it. Neither blocked. **Never hand a reviewer a state assertion you have not verified** — they will (rightly) test it, and if it is false the cost lands on them.

Both reviewers also avoided the two-dot trap unprompted: one resolved the extra paths by **blob SHA against `main`** and attributed them to rebase intake, the other by direct two-SHA content diffs. So patch-id's advantage over a careful tree-and-blob comparison is **cost, not correctness** — one command versus a tarball fetch plus a per-file `cmp` loop plus five blob lookups. Both reviewers adopted it after seeing it.

**This is also why the charter wants additive commits.** `charter/pull-requests/reviews.md:114` allows only *"new commits added to the same branch (no rewrite of existing commits)"* during ChangesRequested; `:115` says use `git merge origin/<base>`, **not** `git rebase`, when the base advances; `:123` requires explicit "rebase OK" from the requesting reviewer first. The rule is not ceremony — it exists so *"what changed since I reviewed?"* stays answerable with the obvious command. That rationale is not stated in the charter and is the part implementers miss: two agents rebased mid-review this wave, both believing it harmless because nothing was lost.

**How to apply:**
- Orchestrator, before telling a reviewer how to verify a head move: **run the ancestry check yourself first, and never assert "additive, no force" without it.** If it fails, say so plainly and hand them the patch-id procedure plus the rewritten base SHA. A confirmed force-push is also a `reviews.md:114` finding they should record — do not present it as a non-event.
- **`head_ref_force_pushed` on the GitHub timeline is the authoritative record**, not an inference from a failed ancestry check: `gh api repos/<o>/<r>/issues/<n>/timeline --paginate --jq '.[] | select(.event=="head_ref_force_pushed")'`. Use it when the finding needs to survive an argument about which git instrument is right.
- Reviewer, re-anchoring after any head move: run patch-id before concluding anything about scope. For a **Python** doc-only follow-up, combine with [[feedback_ast_strip_docstrings_carries_review]] — patch-id proves *content survived the rebase*, AST-strip proves *the new delta is docstring-only*. They answer different questions.
- Implementer: don't rebase during ChangesRequested. If the base must advance, `git merge origin/main`. If a rebase is genuinely unavoidable, get "rebase OK" on the PR first and **state the pre-rebase SHA in the re-request** so reviewers can run patch-id without hunting for it.
- Every verdict drops on any head move regardless — see [[feedback_pr_review_verdict_format]] §9.
