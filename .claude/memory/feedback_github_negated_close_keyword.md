---
name: feedback_github_negated_close_keyword
description: GitHub's PR/commit closing-keyword parser ignores negation — "does not close #N" still closes #N on default-branch merge.
metadata:
  type: feedback
---

GitHub's auto-close parser matches `close|fix|resolve` (+ variants) immediately followed by `#N` **anywhere in a PR body or a commit/squash message**, and it does **NOT** understand negation. A PR body reading `Does **not** close #748` contains the substring `close #748` → GitHub closed #748 on squash-merge to the default branch. This bit **twice** in one session on #748 (PR #749 via a stray commit link, then PR #753 via the negation).

**Why:** the parser is a dumb regex over `(keyword)\s+#?\d+`; "not", markdown bold, and surrounding prose are invisible to it. It fires only on **default-branch** merges (cf. [[feedback_wave_branch_issue_close]] — wave-branch merges don't auto-close at all).

**How to apply:** for an umbrella/multi-deliverable issue you want to KEEP open while merging one deliverable, never place the word close/fix/resolve adjacent to that issue number in any PR body or commit/squash message — **even negated, even to disclaim it**. Use neutral refs only: `Part of #N`, `Re #N`, `relates to #N`, `deliverable D3 of #N`. If it auto-closes anyway, `gh issue reopen #N` and scrub the keyword. Pre-merge, grep the PR body + squash subject/body for `(close|fix|resolve)[sd]?\s+#N` before merging.
