---
name: feedback_gh_pr_edit_silent_noop
description: `gh pr edit`, `gh project item-add`, `gh project item-list --limit`, and `gh api -X PATCH -f body=@file` all have surfaces that return success without applying the mutation (or with broken semantics). Always read-back-verify.
type: feedback
originSessionId: 33831276-0bd2-46e7-8ddd-345abb927046
promotion_target: hook
promotion_threshold:
  retro_citations: 3
status: active
---
The gh CLI has a recurring failure-mode family: command exits 0 (often with a benign GraphQL projects-classic deprecation warning), but the underlying mutation didn't apply or applied with wrong semantics. Confirmed across multiple surfaces and tools. Treat all of these as **advisory** — never trust the exit code; always read-back-verify and keep a REST-API fallback ready.

## Surface 1 — `gh pr edit` (multi-flag, GraphQL path)

| Flag | First seen | How |
|---|---|---|
| `--body-file` (PR body) | 2026-04-23, noorinalabs-deploy#153 | `gh pr edit <N> --body-file <file>` returned exit 0 but PR body unchanged across two attempts |
| `--add-label` (PR labels) | 2026-05-03, noorinalabs-deploy#254 | `gh pr edit <N> --add-label "p3-wave-3"` returned exit 0 but labels unchanged; Aisha-252 fell back to `gh api -X POST .../issues/<N>/labels --input -` |
| `--base` (PR base ref) | 2026-05-03, noorinalabs-isnad-graph#854 | `gh pr edit <N> --base <branch>` returned exit 0 but baseRef unchanged; Idris-853 fell back to `gh api -X PATCH .../pulls/<N> -f base=<branch>` |

The pattern is consistent: any `gh pr edit` flag that triggers the GraphQL projects-classic mutation path is at risk.

## Surface 2 — `gh project item-add` silent fail

P3W7 hit `gh project item-add 2 --owner noorinalabs --url <issue-url>` returning exit 0 without actually adding the issue to project 2. Cumulative ~9 silent failures across 3 PRs in W7 alone (Wanjiku #308 × 5, Sofia #45 × 2, Mateo #100 × 2).

**How to apply:** after `gh project item-add`, read-back-verify by querying project items and checking the issue is present:

```bash
gh project item-list 2 --owner noorinalabs --format json --limit 1000 \
  | jq --arg url "<issue-url>" '.items[] | select(.content.url == $url) | .id'
# Empty output = silent fail; retry or use the GraphQL mutation directly.
# Note: --limit 200 silently truncated to 200/698 items in P3W8 — see Surface 3 sub-failure 3b.
```

If item-add fails repeatedly, fall back to the GraphQL `addProjectV2ItemById` mutation via `gh api graphql`.

**Sub-failure 2a (P3W11, 2026-05-21):** the whole-board read-back verify (`gh project item-list 2 … --format json | jq …`) is itself fragile — if ANY item's content (title/body) contains an unescaped control character, `jq` aborts the entire payload with `Invalid string: control characters from U+0000 through U+001F must be escaped`. Combined with a `2>/dev/null`, this surfaces as **empty output**, indistinguishable from a genuine silent-no-op — I wrongly concluded two adds (#346, #347) had failed when they'd actually succeeded. **More robust verify: query the issue's own membership** instead of parsing the board:
```bash
gh issue view <N> --repo <owner>/<repo> --json projectItems --jq '.projectItems[].title'
# Non-empty (e.g., "Cross-Repo Wave Plan") = on the board. Avoids parsing every other item's content.
```
Prefer this per-issue check for item-add read-back; reserve the whole-board `jq` pull for when you genuinely need the cross-repo list (and never suppress its stderr).

## Surface 3 — `gh project item-list --limit N` truncation + multi-repo false-matches

Two distinct sub-failures on this surface:

**Sub-failure 3a (W7, Dilara):** `gh project item-list 2 --owner noorinalabs --limit 50` returns false-matching items when the project spans multiple repos and >50 items exist — items appear that don't actually belong to the target repo's filter.

**Sub-failure 3b (P3W8, Sofia 2026-05-09):** `gh project item-list 2 --owner noorinalabs --limit 200` returned exactly 200 items as if that were the truth. Re-running with `--limit 1000` returned 698 items (the actual count). The just-added issue (`noorinalabs-main#342`) was missing from the 200-item result and present in the 1000-item result. **The board has grown past the previous "safe ceiling" of 200.**

**Sub-failure 3c (P8W24, 2026-07-11, Aisha + orchestrator, INDEPENDENTLY, same hour):** the ceiling moved again and **the verification query itself lied.** The board now holds **1,656 items**. Aisha verified an `item-add` with `--limit 900`, got NOT FOUND, and nearly reported a silent no-op — it was a **false negative**; re-querying at 3000 confirmed the item was there all along. The orchestrator hit the identical trap the same hour reading back three new issues at `--limit 500`.

**The lesson is not "raise the number."** It is that this whole surface has a **confident-false-negative** failure mode in *both* directions:
- `item-add` returns rc=0 and may not have applied → so you must verify.
- **The verification query silently truncates → so it reports "not there" when it is.**

A truncated read and a genuine no-op are **indistinguishable** at the call site, and the truncated read is the one that looks like diligence. Chasing a phantom no-op is the *expected* outcome of following the verify advice with a stale limit. This memory's own prescribed ceiling (`1000`) was itself already wrong by 2026-07-11 — **any hardcoded limit rots**, and the ones in this file have rotted twice.

**How to apply:** for project queries spanning multi-repo boards:
0. **Never hardcode a limit and never trust a negative result from a capped list.** Prefer the per-issue membership check (Sub-failure 2a) — it is O(1), immune to board size, and cannot truncate:
   ```bash
   gh issue view <N> --repo <owner>/<repo> --json projectItems --jq '.projectItems[].title'
   ```
   If you must pull the whole board, **assert the returned count against the board's true size** and treat any equality-with-the-limit as truncation, not as truth:
   ```bash
   N=$(gh project item-list 2 --owner noorinalabs --format json --limit 5000 \
       | jq '.items | length')
   # If N == your limit, you were truncated. A count that exactly equals the cap is a red flag, not a result.
   ```
1. If you use `--limit`, it must exceed the live board size (>1700 as of 2026-07-11, and rising) — `200` died in P3W8, `900`/`1000` died in P8W24. **Assume today's number is already stale.**
2. Post-filter via `jq` on `.content.url`, `.content.number`, or `.content.repository.name`. Don't trust implicit ordering or partial pulls.
3. **Read-back-verify pattern for `gh project item-add`** must use the elevated limit:
   ```bash
   gh project item-list 2 --owner noorinalabs --format json --limit 1000 \
     | jq --arg url "<issue-url>" '.items[] | select(.content.url == $url) | .id'
   # Empty = silent fail; retry or fall back to GraphQL `addProjectV2ItemById`.
   ```
4. The 200-cap silent-truncation behavior matches the broader silent-no-op family — the command does not warn when the cap is hit.

## Surface 5 — `gh issue list` silent default-limit=30

`gh issue list --repo X --label Y --state open --json number --jq 'length'` returns AT MOST 30 results — the CLI silently caps at the default page size when no `--limit` is set. The truncated count is returned without any warning.

**First seen** 2026-05-17 P3W11 session-start: spawn-prep recount of deploy=78 W11 issues returned 30 from a no-`--limit` query, triggering a false "scope discrepancy" investigation that consumed ~10 min. The actual scope (kickoff record's 78) was correct; my recount was wrong because of the silent default.

**How to apply:** any `gh issue list` query whose result feeds a count, a comparison, or an iteration MUST set `--limit 200` (or higher if the repo is large). The `--json X --jq 'length'` pattern is especially treacherous because it produces a clean integer that *looks* authoritative.

```bash
# WRONG — silently caps at 30
gh issue list --repo X --label Y --state open --json number --jq 'length'

# CORRECT
gh issue list --repo X --label Y --state open --limit 200 --json number --jq 'length'
```

Same pattern likely affects `gh pr list`, `gh release list`, etc. — verify before trusting `length`.

**Hook implication:** `validate_wave_audit` (PreToolUse on Skill) reported "Open items across the org: 67" at the same session — also probably hit by this default if the helper does an unbounded `gh issue list`. Worth a sweep.

## Surface 4 — `gh api -X PATCH -f body=@file` literal-paste

`gh api -X PATCH /repos/:o/:r/pulls/:N -f body=@/tmp/body.md` does NOT read the file — it literally pastes the string `@/tmp/body.md` into the body field. The `@<path>` shorthand only works in some gh contexts, and **`--input` is not one of them** — it takes a bare path (or `-` for stdin), and `--input @file` looks for a file *literally named* `@file`. Capital `-F`/`--field body=@file` DOES expand `@file` to file contents. Kofi caught it on #73 in W7.

```
# with f.json PRESENT — the precondition is load-bearing
gh api rate_limit --input @f.json   -> rc=1  "open @f.json: no such file or directory"   # @ taken literally
gh api rate_limit -F body=@f.json   -> rc=1  "HTTP 404"                                   # @ resolved, request made
# with f.json ABSENT, row 2 gives 'error parsing "body" value: open f.json: …' and never
# reaches the 404. The conclusion holds; the printed evidence does not reproduce.
```

(An earlier version of this line cited `--input @file` as an example of where `@` *works*. It is the one flag where it does not. Wanjiku Mwangi measured it; the distinguishing evidence is the **stderr**, not the `rc` — both fail, for opposite reasons. **Two commands that both exit non-zero are not thereby the same result.**)

**Recurrence 2026-06-15 (ingest#90 review, Bjørn):** `gh api .../issues/90/comments -f body=@/tmp/bjorn_ingest90_review.md` (comment-CREATE POST, not just PATCH) posted the literal string `@/tmp/...`. Because the `validate_pr_review` hook parses the comment body for `Requestor:`/`RequestOrReplied:`, the Approved verdict was invisible and the 2-reviewer gate stayed unsatisfied until re-posted with `-F`. Lesson: for any file-backed body — comment, review, PATCH — use `-F`/`--field` (not `-f`) and read-back the posted body before claiming the verdict landed.

**How to apply:** use `--input` with a JSON file, or `--field body=@file` (long-form), or pre-compose the JSON via `jq -n --rawfile`:

```bash
# Correct
jq -n --rawfile body /tmp/body.md '{body: $body}' > /tmp/patch.json
gh api -X PATCH /repos/:o/:r/pulls/:N --input /tmp/patch.json

# Also correct — long-form --field treats @ as file-read
gh api -X PATCH /repos/:o/:r/pulls/:N --field body=@/tmp/body.md

# WRONG — -f does NOT do @file expansion
# gh api -X PATCH /repos/:o/:r/pulls/:N -f body=@/tmp/body.md
```

**Recurrence 2026-06-15 (P5W4 ingest#90) — POST comments, reviewer-verdict variant.** Same bug on the *comments* endpoint: two spawned reviewers (Bjørn, Petra) each posted their verdict with `gh api .../issues/90/comments -f body=@/tmp/<name>_review.md` → the PR comment contained the **literal string** `@/tmp/<name>_review.md`, not the verdict. Because `validate_pr_review` parses the comment BODY for `Requestor:`/`RequestOrReplied:`, **both Approved verdicts were invisible and the 2-reviewer gate read as unsatisfied** — caught only because the orchestrator's distinct-Requestor read-back returned `[]`. The reviewers' exit codes were 0 and they reported "verdict posted" with real comment ids; the ids existed but held garbage. **Spawn-brief implication:** any reviewer/implementer spawn-brief that instructs posting a structured artifact via `gh api ... -f body=@file` will silently defeat the gate it feeds. Brief reviewers to use `-F body=@file` (capital, file-read) OR `--input <(jq -n --rawfile body <file> '{body:$body}')`, and to **read-back-verify** the posted comment body (`--jq '.[-1].body' | head -5`) before reporting "posted." Orchestrator must always re-derive the distinct-Requestor set from comment bodies before merging — never trust a reviewer's self-reported "Approved, posted."

**Recurrence 2026-06-21 (P6W1, main #776–#780 doc batch) — THIRD reviewer-verdict instance, orchestrator self-inflicted.** Composed 10 reviewer spawn-briefs that each instructed `gh api .../issues/<PR>/comments -f body=@/tmp/<name>_verdict.txt`. All 10 comments posted the **literal** `@/tmp/<name>_verdict.txt` string; the distinct-Requestor read-back returned `[]` for every PR. This is the precise failure this memory's Surface 4 + spawn-brief implication already warned against — the miss was NOT recalling this memory before authoring the briefs (`feedback_hook_brief_grep_precedent_preflight` discipline applies to verdict-posting commands too). Repaired centrally: reposted each `/tmp` file with `gh pr comment <PR> --body-file <file>`, deleted the broken comments, then re-derived the Requestor set from bodies before merging. Cheap fix, but it cost a full repair pass. **Standing brief template:** reviewers MUST post via `gh pr comment <PR> --repo <o/r> --body-file <file>` (purpose-built, reads the file) — NOT `gh api ... -f body=@file`. This is now the third dated reviewer-verdict citation (Bjørn ingest#90, Petra ingest#90, this batch) → the hook-promotion threshold is met; a PreToolUse rewrite/warn on `-f body=@<path>` would have prevented all three.

**Recurrence 2026-07-05 (P8W24, main #924) — FOURTH reviewer-verdict instance, orchestrator self-inflicted AGAIN.** Composed two reviewer spawn-briefs (Wanjiku, Santiago) that each instructed `gh api .../issues/924/comments -f body=@<file>` — the exact form this memory's "standing brief template" says NOT to use. Both comments posted the literal `@/…/<name>_924.md` string; the distinct-Requestor read-back returned empty and the 2-reviewer gate read unsatisfied. Repaired by `PATCH`-ing each comment body in place with `-f body="$(cat <file>)"` (data, not @-expansion), then re-deriving the Requestor set before merging. **This is the 4th dated citation (Bjørn ingest#90, Petra ingest#90, P6W1 batch, this) — the promotion-to-hook threshold (3) has now been exceeded by every measure and the guard STILL does not exist.** A PreToolUse rewrite/warn on `-f body=@<path>` for the comments/pulls/issues endpoints would have prevented all four. The recurring root cause is the same each time: authoring verdict-posting briefs without re-reading this memory (`feedback_hook_brief_grep_precedent_preflight`). File the hook.

## Universal rule

**Why:** projects-classic deprecation is triggering partial GraphQL mutation failures that gh-CLI swallows across multiple surfaces. REST PATCH endpoints bypass GraphQL entirely. The gh-CLI's "exit 0" is not a reliable signal of mutation success on any GraphQL-backed surface.

**How to apply:**

For PR mutations, don't use `gh pr edit` for any of: `--body-file`, `--base`, `--add-label`, `--remove-label`, `--title`. Skip straight to REST:

```bash
# PR body (multi-field also works — adds title etc. to the jq -n)
jq -n --rawfile body /tmp/new_body.md '{body: $body}' > /tmp/patch.json
gh api -X PATCH /repos/:o/:r/pulls/:N --input /tmp/patch.json
gh api /repos/:o/:r/pulls/:N --jq '.body' | head -5   # read-back verify

# PR base ref
gh api -X PATCH /repos/:o/:r/pulls/:N -f base=<new-base-branch>
gh api /repos/:o/:r/pulls/:N --jq '.base.ref'   # read-back verify

# PR labels (issues API, since PR shares the underlying issue)
gh api -X POST /repos/:o/:r/issues/:N/labels --input <(jq -n --argjson labels '["p3-wave-3","bug"]' '{labels: $labels}')
gh api /repos/:o/:r/issues/:N/labels --jq '[.[].name]'   # read-back verify
```

**Common mistake** when constructing `--rawfile` JSON: use `jq -n --rawfile body <file> '{body: $body}'` — NOT `jq -Rs` (which produces a doubly-encoded JSON string the API rejects). Confirmed on noorinalabs-deploy#168 2026-04-25.

**Read-back-verify is mandatory** — even REST can fail on rate limits, permissions, or stale base SHAs. After every PATCH, query the field back:

```bash
gh api /repos/:o/:r/pulls/:N --jq '.<field>' | head -3
```

If observed value doesn't match intended, the PATCH didn't apply — check stderr, retry, or escalate.

## A bare issue/PR number is not a reference — `gh` resolves it against `cwd` (2026-07-09)

In a multi-repo workspace, issue and PR numbers **collide across every repo**, and `gh` silently picks one by the current directory. It does not warn, and it does not error:

```
$ cd noorinalabs-main && gh pr view 383
751ff976  2026-05-12  tech-debt(hook): block_stale_tmp_message_file ...
$ gh pr view 383 -R noorinalabs/noorinalabs-data-acquisition
c04f70d4  fix(bio_promote): refuse truncated prose names ...
```

A reviewer nearly reported *"head moved to 751ff97"* on the wrong PR.

**This is the one silent-resolution the sha discipline cannot catch.** `751ff976` is a perfectly real sha with a real title and a real `updatedAt`; it answers cleanly. Asserting the sha proves *which commit*, and says nothing about **which repository**. Only `gh repo view --json nameWithOwner` (or `-R owner/repo` on every call) resolves the identity.

- **Never write a bare number in a cross-repo brief.** `da#383`, `ig#1044`, `deploy#559` — or `owner/repo#N`.
- **Pass `-R owner/repo` to every `gh` call** that names an issue or PR by number, especially from a parent org repo whose child clones are nested beneath it.
- Sibling of the *label vs identity* rule: a number is a **label**, `owner/repo#N` is a **name**. Same defect as `f.name` collapsing nine copies of one basename into one row (see [[feedback_silent_zero_is_not_a_measurement]]), and as grepping for a retracted sentence and finding the retraction that quotes it. **An instrument that answers with a label cannot distinguish the members of the set it labelled.**

Cross-references:
- `feedback_verify_diagnosis_before_delegating.md` — API state ≠ ground truth until read-back-verified
- `feedback_refresh_before_status_claim.md` — every claim "PR is at state X" needs an API call first
- `feedback_origin_over_local_for_still_has_claims.md` — sibling rule for content claims
