---
name: feedback_gh_cli_gotchas
description: "Consolidated gh-CLI gotcha family — silent no-ops, truncating lists, @file expansion, cwd-resolved bare numbers, async mutations, self-approve 422, closing-keyword semantics, validate_labels false-blocks, ProjectV2 field edits, GraphQL/REST quota split with enforced REST fallback tooling. Universal rule: never trust exit 0 on a gh mutation; read-back-verify via a query that cannot truncate."
metadata:
  type: feedback
last_verified: 2026-08-02
---

Consolidates (2026-07-13, #944/#931): feedback_gh_pr_edit_silent_noop, feedback_github_negated_close_keyword, feedback_wave_branch_issue_close, reference_closing_refs_empty_wave_prs, feedback_gh_review_self_approve_422, feedback_update_branch_async_window, feedback_validate_labels_hook_gotchas, feedback_projectv2_field_option. Every rule survives; history in git.

## Surfaces
1. [`gh pr edit` silent no-op → REST PATCH](#1-gh-pr-edit-silent-no-op) — **1a: `--add-label` on a PR now HARD-FAILS** (projects-classic deprecation); use the issue-shaped REST labels endpoint
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
gh api --method POST repos/{owner}/{repo}/issues/:N/labels -f "labels[]=X"  # labels — see 1a
```

### 1a. `--add-label` on a PR has since become a HARD FAIL, not a no-op (2026-08-09)

The `--add-label` case above no longer merely returns exit 0 and do nothing. It now **errors outright**:

```
GraphQL: Projects (classic) is being deprecated … (repository.pullRequest.projectCards)
```

gh still requests the sunset `projectCards` field on the PR edit path, so the whole mutation is rejected. **This is the better failure** — the surface moved from silent to loud — but it means a script that tolerated the no-op now aborts, and the fix is not "retry" but "change endpoint."

Working route, verified 2026-08-09 — the **issue-shaped** REST endpoint covers PRs (GitHub models a PR as an issue for labels), and is both live and unbroken:

```bash
gh api --method POST repos/{owner}/{repo}/issues/{n}/labels -f "labels[]=X" -f "labels[]=Y"
```

Prefer this `-f "labels[]=…"` form over the `--input <(jq …)` process substitution: process substitution trips the Claude Code permission engine's "cannot be statically analyzed" path and forces a prompt regardless of the allowlist (same property /session-start Step 0 preserves deliberately).

Same family as §4's stale-index gotcha: the GraphQL-backed convenience path degrades as GitHub sunsets classic Projects, while the REST path keeps working. When any `gh <noun> edit` flag fails or no-ops, the first move is to find the REST endpoint, not to debug the flag.

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

**Same class, worse blast radius: `gh pr create --body @file`** (W30 PR #1390, 2026-08-11). `--body` takes a *string*; `--body-file` takes a path. Passing `--body @/tmp/…/pr_body.md` creates a **syntactically valid PR whose entire body is the 126-char literal `@/tmp/…`**. Nothing catches it: CI is green, the PR is well-formed, `gh pr view` renders the path happily, and the merge gate does not read the body. It surfaced only because a merge-gate reviewer went looking for the precision table the body was supposed to contain.

Why this one is urgent rather than cosmetic: the intended content lived **only in a session-scoped scratchpad** (`/tmp/claude-1000/<repo>/<session-uuid>/scratchpad/`), so the 10.5 KB write-up would have been **irrecoverable once that session ended** — the PR record would have been permanently empty. Recovered by copying the file out and `gh api repos/{o}/{r}/pulls/{N} -X PATCH -F body=@<file>` (capital `-F`; no commit pushed, head unchanged, so no verdict was staled).

Rules: after ANY file-sourced PR body, assert `gh api repos/{o}/{r}/pulls/{N} --jq '.body | length'` is plausible and that `.body` does not match `^@`. Copy a scratchpad-authored body somewhere durable before it becomes the only copy. Note [[feedback_pr_body_vs_commit_linkage]] (#1403) covers the *closing-keyword* divergence between body and commit message; this is the orthogonal "body never arrived at all" failure and no gate covers it.

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

## 12. GraphQL quota exhausts independently of REST — and fails as a silent zero

`gh` splits across two quotas (`gh api rate_limit`): **core** (REST, 5000/h) and **graphql** (5000/h). They drain independently, so REST can read 4988/5000 while GraphQL is flat 0 (observed live 2026-07-20, wave-26 scope run; re-observed live 2026-08-02, `core=4986/5000, graphql=0/5000`, #1224 — building `gh_quota.py`/`gh_rest.py`/`gh_quota_gate.py` against this exact live-exhausted state).

**What burns GraphQL fastest:** `gh project item-list <n> --limit 2000` paginates ~100 items/page, so ONE run is ~20 GraphQL calls. A handful of board queries while chasing a membership question exhausted 5000. Prefer `/board-audit` over hand-rolled board sweeps.

**The failure is a silent zero, not an error you'll notice.** The response body is the bare string `GraphQL: API rate limit exceeded for user ID <n>`; piped into `jq` it is a parse error, and with the customary `2>/dev/null` on the `gh` call the whole thing reads as *an empty result set*. This session nearly reported "all 12 wave-26 issues missing from project board 2" as fact when board state was simply **unknown**. Same class as [[feedback_silent_zero_is_not_a_measurement]] — never let a quota failure masquerade as a negative finding. Drop the `2>/dev/null` when a query returns surprisingly empty.

**Note the convergence with #888.** That bug — `first: > 100` in a `gh api graphql` block, now linted by `lint_skill_graphql_pagination.py` — produced the *identical* symptom: `/board-audit` reading every issue as an orphan. Over-cap paging and quota exhaustion are different causes with the same false-negative shape, so treat "everything is missing from the board" as a **tooling** hypothesis first and a finding second.

**Which subcommands need GraphQL (fail under exhaustion) — measured table, re-derived live 2026-08-02 (#1224):**

| surface | result | notes |
|---|---|---|
| `gh issue view --json`, `gh issue list` (**even without `--json`**) | FAIL | dropping `--json` is not a workaround — the GraphQL dependency isn't about output formatting |
| `gh issue create` | FAIL | **corrects the earlier "already REST" claim below** — modern `gh` needs GraphQL even for a plain create (likely Issue-Types/board metadata resolution); no wrapped helper exists yet, use the raw REST recipe in `gh_quota_gate.py`'s rewrite text |
| `gh pr view --json <fields>`, `gh pr list --json` | FAIL | **flaky at the single-field edge**: `gh pr view N --json number` alone succeeded twice in a row, but any richer field set (`state,headRefOid,baseRefName,mergedAt`) failed every time. Never rely on a single success — the flaky case is not a safe workaround |
| `gh pr checks`, `gh pr comment` | FAIL | |
| `gh project item-list`, `gh project item-add` | FAIL | item-add fails with a **misleading** `unknown owner type`, not a quota message |
| `gh api repos/…` (REST), `gh pr diff`, `gh api rate_limit` | OK | `rate_limit` itself costs **no quota** — free to poll |

**Correction to the org's own assumption: `gh project item-add` DOES have a REST equivalent now.** Verified LIVE 2026-08-02 by actually adding #1224 to project board 2 through it:
```
gh api -X POST orgs/{org}/projectsV2/{project_number}/items -f type=Issue -F id=<issue's REST database id>
```
`type` is `Issue` or `PullRequest` (capitalized); `id` is the numeric REST `id` field — **not** the issue `number`, **not** the GraphQL `node_id`. Read-side counterpart: `GET orgs/{org}/projectsV2/{project_number}/items` (paginated, no server-side content filter — page the whole board and filter client-side on `.content.number` + `.content.repository.full_name`, same multi-repo-collision care as §3). `gh` the CLI tool has **not** been updated to use this endpoint — `gh project item-add` is still GraphQL-backed and still fails under exhaustion; this is a genuine fallback for that gap, not a claim that `gh` itself changed. Only verified for an **org-owned** board with the current token's scopes — a user-owned project or a differently-scoped PAT is unverified. The one project surface confirmed to have **no** REST equivalent at all: classic Projects (`gh api orgs/{org}/projects` → 404, fully removed).

**REST fallbacks that keep working (now backed by `.claude/lib/gh_rest.py`, #1224):**
- post a PR/issue comment → `gh api repos/{owner}/{repo}/issues/{N}/comments -f body='...'` (verified live by Lucas Ferreira on PR#1049 — charter verdict trailer parsed identically), or the wrapped two-step `gh_rest.py comment write-payload` + `comment post`
- **the write-payload/post split is not a style choice — it works around a hook.** `validate_review_comment_format` reads the `--input` file to validate the charter format and false-blocks when that file doesn't exist yet at match time. Writing the payload in an EARLIER, separate tool call (not `write > f.json && gh api ... --input f.json` in one Bash call) sidesteps it.
- `gh issue create` — **NOT REST-safe** (see corrected table above); the "already REST" claim in the original version of this note was wrong
- `gh issue edit` — unverified either way this round; no direct measurement contradicts the original "already REST" claim, so it stays untouched pending a live check
- read comments → `gh api repos/{owner}/{repo}/issues/{N}/comments`, or `gh_rest.py pr comments`
- `gh_rest.py issue view/list`, `pr view/list/checks/timeline`, `project add/items/membership` — every function raises rather than returning `[]`/`{}` on a genuine failure (never masks a real error as an empty result — the exact silent-zero shape this section exists to prevent, recreated at a new layer)
- **traps `gh_rest.py` pins with tests:** (a) `repos/{o}/{r}/issues` returns pull requests too — a naive count once read 57 where the true issue count was 50; every list/view function filters `select(.pull_request == null)` or rejects a PR number outright; (b) pagination — every list read uses `--paginate` (verified live: one compact JSON object per line, across every page), so a >100-item result is never silently truncated, sibling of the `item-list --limit` trap in §3

A reviewer blocked mid-verdict should switch to the REST comment endpoint, not wait out the hour.

**Enforcement promotion (#1224):** this section sat at the weakest enforcement tier (`feedback_enforcement_hierarchy`: hook > skill > charter > memory) for ~2 weeks after being written (2026-07-20) and did not prevent a recurrence — four concurrent agents exhausted the quota again in the session that filed #1224, holding two PR re-reviews ~40 minutes. Promoted to a hook: `gh_quota_gate.py` (PreToolUse) blocks a GraphQL-shaped `gh` call with a concrete REST rewrite when quota is low, or advises (never blocks) when no rewrite is derivable (a raw `gh api graphql` call, or an unmapped project mutation like `item-edit`/`field-list`) — see `ontology/conventions.md` § Automation hooks and § GitHub API quota, `docs/TOOLCHAIN.md` § GitHub API quota. Sensor: `.claude/lib/gh_quota.py` (`gh api rate_limit` costs no quota — free to poll; TTL-cached at the hook). Fallback: `.claude/lib/gh_rest.py`. A quota-check failure degrades to ALLOW, never to block — the sensor itself must not become a new single point of failure.

## 13. CI green: `check-runs` is authoritative, `status` is not

`gh api repos/{o}/{r}/commits/{sha}/status` reports the **legacy Statuses API** only. On a repo whose CI is all GitHub Actions that collection is empty, so the combined state renders `pending` **even when every check has passed** — a false amber that reads as "still running."

Use `gh api repos/{o}/{r}/commits/{sha}/check-runs` (Checks API) for the real verdict; key on `.check_runs[].conclusion`. Verified on PR#1049 head `8729bca`: `status` said pending, `check-runs` showed 14/14 success. Query by **SHA, not PR number** — a PR-number query re-resolves the head and can answer about a different commit than the one you mean to certify (head-SHA anchoring, [[feedback_pr_review_verdict_format]] §7: "the hook counts comments, not shas — an approval predating the head is not an approval").

Cross-references: [[feedback_refresh_before_status_claim]] (fresh API call before any state claim), [[feedback_verify_diagnosis_before_delegating]] (API state ≠ ground truth until read back), [[feedback_silent_zero_is_not_a_measurement]] (a confident NO from a truncated query is the silent-zero class).
