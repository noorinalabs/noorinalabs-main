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

## The hole is not always INSIDE `check()` (#1243, W30)

Both rules above search the body of `check()`. Two fail-opens in
`validate_wave_audit.py` (Hook 17, a hard-blocking PreToolUse gate) sat entirely
**outside** it, where no `decision`-grep can reach:

1. **The module-level import.** `from org_repos import ALL_REPOS` on a missing
   module raised out of the module body → traceback, **exit 1**. PreToolUse
   treats exit **2** as block and *every other* non-zero exit as a non-blocking
   error, so exit 1 IS an allow. `check()` was never called. The gate stopped
   gating at exactly the moment it broke, indistinguishable from an approval.
2. **The runner's exception swallow.** `_hook_main.run_blocking` catches every
   `check()` exception and exits 0 by design ("a hook must never crash"). So any
   raise on the *block* path — e.g. the annunaki log call inside `_block` — turns
   a BLOCK into a silent, **output-free** allow. Build the verdict first; wrap
   the logging, never the decision.

**Reusable rule:** for a blocking gate, the verdict surface is the **exit code**,
not the returned dict. Audit the whole process lifecycle — imports, the runner,
`main()` — not just `check()`. And the test must be a **subprocess** invocation
of the registered entry point: `check()` unit tests are blind to both holes
(#1376's `MainEntrypointExitCode` is the sibling case — swapping `run_blocking`
→ `run_advisory` printed a byte-identical `{"decision": "block"}` while exiting
0, and all 17 `check()` tests stayed green).

**Corollary — the class is generic, so fixing one instance is not fixing it.**
Every hook built on `run_blocking` has both properties. #1243 closed Hook 17;
the rest of `settings.json`'s blocking gates were not swept.

**And mutation-test the constant, not just the logic.** The same PR found
`_ORG_REPOS` had no SSOT-identity guard: a hand-copied 8-tuple with ONE typo'd
repo name survived all 4185 tests while the audit swept a nonexistent repo.
`assertIs(hook._ORG_REPOS, org_repos.ALL_REPOS)`, not `assertEqual` — a copy is
correct on the day it is typed and rots silently after, so identity is the only
assertion that fails on day one. Beware the *incidental* detector: one test did
catch the length-changing variant, but only via a `"any of the 8 org repo(s)"`
message-text assertion. That is not a guard.

Related: [[feedback_safety_direction_over_ux_friction]],
[[feedback_lint_gate_cover_all_syntactic_forms]], [[feedback_pr_review_verdict_format]],
[[feedback_corpus_misses_its_constant_dimension]].
