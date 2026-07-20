---
name: feedback_gate_early_allow_is_the_failopen
description: A verify-gate's fail-open is usually an early allow-with-warning branch that short-circuits AHEAD of the hard-blocks added elsewhere — audit every `decision: allow` / warning return on a failed-fetch path, not just the function you think owns the check.
metadata:
  type: feedback
last_verified: 2026-07-20
---

# The fail-open hides in an early allow-with-warning, not in the "verify" function

**#981 (validate_pr_review Hook 4, the 2-reviewer merge gate).** The gate had a
fail-CLOSED `CommitFetchError` hard-block (#950) and a fail-CLOSED roster-resolution
hard-block (#552). It ALSO had, several lines earlier, this:

```python
pr_data = get_pr_data(pr_number, repo=repo)
if pr_data is None:
    return {"decision": "allow", "systemMessage": "WARNING: Could not verify..."}
```

`gh pr merge 451 -R $DA --merge` — the hook parses the command **pre-expansion**, so
`$DA` reached `gh pr view --repo '$DA'`, which exits non-zero → `get_pr_data` returns
None → early `allow`. That branch **short-circuited ahead of** both hard-blocks, so
neither ever ran. Four P9W25 da PRs merged with the gate silently off. The issue body
misdiagnosed it as `_resolve_owner_repo` inside `check_comment_reviews` — a path NOT
reachable on the merge path. **Reproduce, don't trust the reported location.**

## The reusable rule

When you add a fail-CLOSED hard-block to a verify-gate, `rg` the whole `check()` for
every **earlier** `"decision": "allow"` / `systemMessage`-warning / bare `return None`
on a *failed-fetch / unresolved-input* path. Any one of them that sits upstream of your
block re-opens the hole. An allow-with-warning on "could not verify" IS a fail-open —
`feedback_safety_direction_over_ux_friction` (hard-block, never allow-with-log) applies
to it exactly as to the obvious path.

## Distinguish deterministic from transient in the diagnostic

Unresolvable `--repo` (`$VAR`, no `/`) is **deterministic** — fixed by a literal
`--repo owner/name`, never by a retry. A generic fetch failure (auth/network/wrong PR#)
is **transient** — fixed by retry. Blocking both closed is necessary but not sufficient;
the two need OPPOSITE operator advice, so classify and say which. Reuse the file's
existing unexpanded-var machinery (`_is_single_expansion_word`) — a second hand-rolled
matcher is the drift that was #1046.

## Defense-in-depth signature (#1050, latent)

`check_comment_reviews`'s early `return result` on unresolved-repo / API-non-zero / bare
`except` each returned an EMPTY reviewer set that reads as "0 approvals found" rather than
"could not determine". Fixed additively with a `CommentReviewResult.undetermined` string
(NOT a new exception — `pr_review_state.py` constructs/consumes the object directly, so a
raise would break its clean exit-2 path); callers hard-block when it is non-empty.

Related: [[feedback_safety_direction_over_ux_friction]],
[[feedback_lint_gate_cover_all_syntactic_forms]], [[feedback_pr_review_verdict_format]].
