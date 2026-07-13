---
name: feedback_gh_cli_gotchas
description: "Consolidated gh-CLI gotcha family — silent no-ops, truncating lists, @file expansion, cwd-resolved bare numbers, async mutations, self-approve 422, closing-keyword semantics, validate_labels false-blocks, ProjectV2 field edits. Universal rule: never trust exit 0 on a gh mutation; read-back-verify via a query that cannot truncate."
metadata:
  type: feedback
---

Consolidates (2026-07-13, #944/#931): feedback_gh_pr_edit_silent_noop, feedback_github_negated_close_keyword, feedback_wave_branch_issue_close, reference_closing_refs_empty_wave_prs, feedback_gh_review_self_approve_422, feedback_update_branch_async_window, feedback_validate_labels_hook_gotchas, feedback_projectv2_field_option. Every rule survives; history in git.

## Surfaces
1. [`gh pr edit` silent no-op → REST PATCH](#1-gh-pr-edit-silent-no-op)
2. [`gh project item-add` silent fail → per-issue read-back](#2-gh-project-item-add-silent-fail)
3. [`item-list --limit` truncation — the limit IS the bug](#3-item-list---limit-truncation)
4. [`gh issue list` silent default limit 30](#4-gh-issue-list-silent-default-limit-30)
5. [`-f body=@file` pastes the literal string](#5--f-bodyfile-literal-paste)
6. [Bare issue/PR numbers resolve against cwd](#6-bare-numbers-resolve-against-cwd)
7. [`update-branch` is async (202) — refetch head sha](#7-update-branch-async-window)
8. [Formal-review APPROVE always 422s — use issue comments](#8-formal-review-approve-422)
9. [Closing-keyword semantics: default-branch-only, negation-blind, refs-empty on wave PRs](#9-closing-keyword-semantics)
10. [`validate_labels` hook false-blocks (body over-match + stale cache)](#10-validate_labels-false-blocks)
11. [ProjectV2 single-select option add is orchestrator-doable (replaces the whole list)](#11-projectv2-field-options)

**Universal rule:** gh's GraphQL-backed surfaces swallow partial mutation failures (projects-classic deprecation) and return exit 0. Never trust the exit code on any gh mutation. Read-back-verify every one; prefer REST (`gh api`) which is transparent — but REST mutations can be async, so verify with a refetch.

## 1. `gh pr edit` silent no-op
`gh pr edit` returns exit 0 without applying `--body-file` (deploy#153), `--add-label` (deploy#254), `--base` (ig#854) — any flag on the GraphQL projects-classic path. Skip straight to REST, then read back:
```bash
jq -n --rawfile body /tmp/new_body.md '{body: $body}' > /tmp/patch.json   # NOT jq -Rs (double-encodes)
gh api -X PATCH /repos/:o/:r/pulls/:N --input /tmp/patch.json
gh api /repos/:o/:r/pulls/:N --jq '.body' | head -5          # read-back verify
gh api -X PATCH /repos/:o/:r/pulls/:N -f base=<branch>       # base ref; verify --jq '.base.ref'
gh api -X POST /repos/:o/:r/issues/:N/labels --input <(jq -n '{labels: ["x","y"]}')  # labels
```

## 2. `gh project item-add` silent fail
Returns exit 0 without adding (~9 silent failures in one wave). Read-back with the **O(1) per-issue check** — never a `--limit`ed board pull (see §3):
```bash
gh issue view <N> --repo noorinalabs/<repo> --json projectItems --jq '.projectItems[].title'
# Non-empty = on the board. Empty = genuinely absent. No limit to lie about.
```
Whole-board `item-list | jq` is additionally fragile: one unescaped control char in any item's content aborts jq → empty output indistinguishable from a no-op (never `2>/dev/null` it). If the add truly failed, fall back to GraphQL `addProjectV2ItemById`.

## 3. `item-list --limit` truncation
`gh project item-list --limit N` silently truncates and answers a confident, well-formed **NO** for anything past the cap. Every hardcoded ceiling has rotted (200 → 900 → 1000 → 1200 all produced false negatives; board >1,690 and rising). Three people chased phantom no-ops, twice on one day, once with the warning already written in this file. **A count that exactly equals your cap is a truncation, not a result. The limit is not the fix; it is the bug.** Use the §2 per-issue check, or paginate GraphQL with a **positive control** (a known-present issue), or assert the returned count ≠ the limit AND against `projectV2.items.totalCount`. Also: multi-repo boards false-match under small limits (post-filter on `.content.url`/`.content.repository.name`).

## 4. `gh issue list` silent default limit 30
Without `--limit`, `gh issue list` (and `gh pr list`, etc.) caps at 30 and says nothing; `--json x --jq 'length'` then returns a clean, authoritative-looking wrong count (P3W11: false "scope discrepancy" from 30-vs-78). Any list feeding a count/comparison/iteration MUST set `--limit` above the true population — and treat result == limit as truncation.

## 5. `-f body=@file` literal paste
`gh api ... -f body=@/tmp/x.md` does NOT read the file — it posts the literal string `@/tmp/x.md`. Four dated reviewer-verdict incidents (ingest#90 ×2, P6W1 10-PR batch, main#924): verdicts posted as garbage, invisible to `validate_pr_review`, 2-reviewer gate unsatisfied while reviewers report "posted." Rules:
- Reviewers post via `gh pr comment <N> --repo <o/r> --body-file <file>` (purpose-built, reads the file).
- For `gh api`: capital `-F body=@file` expands; `--input <path>` takes a bare path (`--input @f` looks for a file literally named `@f`); or `jq -n --rawfile body <file> '{body:$body}'` piped to `--input -`.
- Always read back the posted body (`--jq '.[-1].body' | head -5`) before claiming it landed; orchestrator re-derives verdict state from comment bodies, never from a reviewer's self-report.

## 6. Bare numbers resolve against cwd
Issue/PR numbers collide across every repo in a multi-repo workspace and `gh` silently resolves a bare number against the cwd's repo — no warning (`gh pr view 383` in main vs da = two different real PRs; a reviewer nearly reported head-moved on the wrong one). Asserting a sha proves *which commit*, nothing about *which repository*. Never write a bare number in a cross-repo brief (`da#383`, `owner/repo#N`); pass `-R owner/repo` on every `gh` call that names an issue/PR by number.

## 7. `update-branch` async window
`gh api -X PUT .../pulls/<N>/update-branch` returns 202 immediately; the merge commit lands asynchronously (1–10 s). A `headRefOid` read seconds later may return the OLD sha. Poll until the sha differs from the pre-call value (or check `gh run list --branch <name>` for a fresh run) before any downstream action; when a teammate's read disagrees with yours, both can be honest snapshots of different points in the window (P3W12 #930).

## 8. Formal-review APPROVE 422
`gh api .../pulls/N/reviews` with `event: APPROVE`/`REQUEST_CHANGES` always 422s ("Can not approve your own pull request"): the gh auth principal is `parametrization` for both author and reviewer — persona commit identities never touch the API principal. Don't attempt it; post the verdict as an issue comment (`gh pr comment --body-file`) with the charter trailer block, which is what Hook 4 parses. Wave branches carry no branch protection, so absent formal-review state doesn't gate merge (if protection ever appears, the self-review model breaks — owner decision needed).

## 9. Closing-keyword semantics
Three interlocking behaviors:
- **Auto-close fires ONLY on default-branch merges.** PRs merged into a wave branch leave `Closes #N` issues OPEN (5-issue miss, 2026-04-28). After any non-default-branch merge, `gh issue view <N>` each reference; close explicitly with the merge sha. Some repos run a custom `auto-close-issues.yml` that handles wave branches (isnad-graph, deploy confirmed) — explicit close is then a harmless no-op, but verify it fired; a manual close that loses the race to the bot no-ops its comment too (rationale belongs in the PR body).
- **The parser ignores negation.** "Does **not** close #748" still contains `close #748` → issue auto-closed on default-branch merge (bit twice in one session). To keep an umbrella issue open, never place close/fix/resolve adjacent to its number — even negated. Use `Part of #N` / `Re #N`. Pre-merge, grep PR body + squash message for `(close|fix|resolve)[sd]?\s+#N`.
- **`closingIssuesReferences` is useless on wave PRs.** Not a `gh pr view --json` field at all, and via GraphQL it is ALWAYS empty when the PR base is not the default branch (verified live, PR#700). Tools deciding "which issue does this wave PR close" must parse body+title for the closing-keyword grammar requiring the keyword: `(?:close[sd]?|fix(?:es|ed)?|resolve[sd]?)\b[\s:]+#(\d+)` (what `validate_wave_audit._closing_refs_in_text` does, main#664/PR#700). Unit tests mocking subprocess passed with the broken form — verify gh-shape hooks against real gh.

## 10. `validate_labels` false-blocks
The label-existence PreToolUse hook on `gh issue create/edit` has two false-block modes (P4W7, main#661/#663): (a) **body over-match** — label-shaped tokens in the body (`p{N}-wave-{M}` in backticks) block a create whose `--label` is innocent; reword bodies (`p<N>-wave-<M>`); (b) **stale label cache** — a label created earlier in the session isn't seen; verify via `gh api .../labels/<name>` (NOT `gh label list --search`, which fuzzy-matches), then retry — the cache refreshes across tool calls. When blocked, don't assume the label is missing: api-verify, then retry; keep label-shaped tokens out of issue bodies.

## 11. ProjectV2 field options
Adding an option to a Projects-v2 single-select field (e.g. a Wave option on project 2) is orchestrator-doable via GraphQL `updateProjectV2Field` — never file it as owner-only. **Gotcha:** the mutation REPLACES the full option list; read current options first (`gh project field-list 2 --owner noorinalabs`) and re-send all of them plus the addition, or the rest are wiped. Read back that the option stuck.

Cross-references: [[feedback_refresh_before_status_claim]] (fresh API call before any state claim), [[feedback_verify_diagnosis_before_delegating]] (API state ≠ ground truth until read back), [[feedback_silent_zero_is_not_a_measurement]] (a confident NO from a truncated query is the silent-zero class).
