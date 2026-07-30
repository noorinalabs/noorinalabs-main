# Pull Requests — Reviews

> Part of the [pull-requests charter index](../pull-requests.md) — re-shelved from `charter/pull-requests.md` for section-level loading (#963). Rules unchanged.

## Comment-Based Reviews (Mandatory) <!-- promotion-target: none -->
All agents share a single GitHub user account. **`gh pr review --approve` is blocked** — it always fails with "cannot approve your own pull request". All PR reviews MUST use comment-based reviews instead.

**Review format** (posted via `gh pr comment`):
```
Requestor: <comment author>
Requestee: <comment target>
RequestOrReplied: Request | Reply | Approved | ChangesRequested
TechDebt: none | #15, #16, ...
```

### Canonical meaning (resolves main#233)

The role names always describe the **comment** (not the PR):

- **`Requestor` is always the comment author** — the team member posting the comment, regardless of whether they are the PR author or a reviewer.
- **`Requestee` is always the comment target** — the team member the comment is addressed to.
- **`RequestOrReplied`** distinguishes the comment kind, NOT the role direction:
  - `Request` — initial review request from PR author (Requestor=PR author, Requestee=reviewer)
  - `Reply` — non-verdict response from any party (Requestor=replier, Requestee=person-being-replied-to)
  - `Approved` — reviewer's approving verdict (Requestor=reviewer, Requestee=PR author)
  - `ChangesRequested` — reviewer's blocking verdict (Requestor=reviewer, Requestee=PR author)

**Key consequence for verdict comments**: on `Approved` and `ChangesRequested` comments, `Requestor` is the reviewer (because the reviewer is the comment author). The hook counts distinct `Requestor` values across `Approved`/`ChangesRequested` comments to verify the 2-reviewer rule (resolves main#244 — the prior hook counted distinct `Requestee` values, which on verdict comments is the PR author, not the reviewer).

**Scope of the `validate_review_comment_format` hook** (resolves main#378, realigned in main#386): This hook enforces Requestor/Requestee non-swap detection ONLY for `Approved` and `Changes Requested` verdict comments, where the Direction table above binds `Requestor = reviewer` and `Requestee = PR author`. Within that scope the hook blocks when the `Requestor` **is the branch author** — i.e., when the PR author is being named as the reviewer (the post-#244 swap shape). Identity is compared on **first-initial + lastname** (`charter_trailer.is_branch_author`), the full discriminator the branch prefix `{FirstInitial}.{LastName}` carries — never the lastname alone, which collapses distinct roster members who share a surname and blocked a correct verdict from *Santiago Ferreira* on *Lucas Ferreira*'s branch (main#1172, the sibling of the main#164 reviewer-dedup collision). Where a first initial is underivable on either side the comparison falls back to lastname-only, the stricter answer. For `Request` and `Reply` comments — where the role bindings invert (`Requestor = PR author`, `Requestee = reviewer`) — the swap heuristic does not apply and the hook returns `None`. Author/reviewer discipline for `Request`/`Reply` traffic is operator-trusted; the hook does not gate it. Unrecognized `RequestOrReplied` values also pass through (the verdict-word vocabulary is `validate_pr_review`'s scope, not this hook's).

### Validation

- The `Requestor` of a `Request`-kind comment must differ from the comment author of the `Approved`/`ChangesRequested` comments (a PR author cannot self-approve their own PR via comment-based review). Enforced by `block_gh_pr_review.py` PreToolUse hook + `validate_pr_review.py` at merge time.
- The `TechDebt:` line is **mandatory** on every `Approved` and `ChangesRequested` comment. If the reviewer found non-blocking observations, they MUST create `tech-debt`-labeled issues BEFORE posting the verdict, then list the issue numbers, e.g. `TechDebt: #1054, #1055`. If no tech-debt was found, write `TechDebt: none`. The `#` is accepted either way (`#1054` or a bare `1054` both capture), but a value that is neither `none` nor a number — free text like "filed later" — parses to ZERO issue references and is recorded as unparseable rather than silently dropped (main#1055). Enforced by `validate_pr_review.py` PreToolUse hook at merge time.
- The 2-reviewer rule is satisfied when there are `Approved` comments from **two distinct `Requestor` values**, neither of which is the PR author. Single-reviewer waivers per § Single-Reviewer Exception (Wave-Bootstrap Only) are honored by the hook (resolves main#228) when the PR is labeled `wave-bootstrap` and the single reviewer is the Standards & Quality Lead.
- Each `Requestor` value on an `Approved` comment must name a persona in the local `.claude/team/roster/` (full-name match against `**Name:**` lines). Non-roster Requestor strings do NOT count toward the 2-reviewer threshold — Hook 4 filters them out and reports them in the BLOCK diagnostic. Mirrors `validate_commit_identity.py`'s strict-roster discipline (resolves main#498).
- Charter-format fields (`Requestor:` / `Requestee:` / `RequestOrReplied:` / `TechDebt:`) MUST appear ONLY in the trailer block — a contiguous structured-fields block at the end of the comment body, ideally after a bare-line `---` separator. Hook 4 extracts fields only from the trailer-block substring (post-last-`---`) and strips inline (`` `…` ``) and fenced (```` ```…``` ````) code regions before matching. Prose that quotes the field syntax above the trailer (or uses backticks to discuss it) will be ignored by the extractor, but reviewers should still avoid duplicating field patterns in prose for clarity. Pre-#511 the regex first-matched any `<Field>:` mention, which false-blocked 3 reviewer verdicts in P3W11 batch 11 (main#509, deploy#337, deploy#339) — each required orchestrator REST PATCH (resolves main#511).

## Review Prompt Template (Mandatory) <!-- promotion-target: none -->
When the orchestrator assigns a review to any agent, the prompt **MUST** include a copy-paste-ready `gh pr comment` command with all fields pre-filled. Do not rely on agents writing the format from memory — this has a 100% error rate.

**Template for orchestrator prompts** (Approved/ChangesRequested verdict — reviewer is the comment author, so Requestor=reviewer):
```
Post your review using this exact command:

gh pr comment {PR_NUMBER} --repo noorinalabs/{REPO} --body "Requestor: {REVIEWER_NAME}
Requestee: {PR_AUTHOR_NAME}
RequestOrReplied: Approved
TechDebt: none

{Your review summary here.}"
```

Replace `Approved` with `ChangesRequested` if blocking issues found. Replace `TechDebt: none` with issue numbers if tech-debt filed. Do NOT add bold markers, parenthetical descriptions, or extra fields.

For `Request`-kind comments (initial review request from PR author), the role direction inverts: Requestor={PR_AUTHOR_NAME}, Requestee={REVIEWER_NAME} (because the PR author is the comment author of the request).

**Why:** In Phase 3 Wave 1, all 7 initial reviews used wrong field names (`Requestee (reviewer):` instead of `Requestee:`) and omitted the `TechDebt:` line, requiring re-posts and blocking merges for ~15 minutes. In P3W3, the wave-completion batch's verdict comments mostly had `Requestee=author` (because Requestor was the reviewer-as-comment-author), which the prior `validate_pr_review.py` interpretation treated as 1 distinct reviewer instead of 2 — forcing `--admin` overrides on 5/5 wave-merge PRs (main#244).

Failing to include the review template in a review assignment prompt is a **minor feedback event** for the orchestrator.

## Two-Reviewer Assignment at Wave Kickoff <!-- promotion-target: none -->
Every PR must have **two reviewers** assigned at wave kickoff — a primary and a secondary. Both reviewers are named in the agent's spawn prompt and in the execution plan.

**Why:** In Phase 3 Wave 1, only one reviewer was planned per PR. Every PR needed ad-hoc second reviewer assignments, causing merge delays while idle agents were redirected.

The Program Director's execution plan MUST include a review matrix with two named reviewers per expected PR. The orchestrator verifies this before spawning agents.

## All Deliberately-Assigned Reviewers Must Approve Before Merge (Blast-Radius PRs) <!-- promotion-target: none -->

The two-reviewer rule above is a **floor**, not a cap. When a PR has **three or more reviewers deliberately assigned** — typically because it has app-wide blast radius and each reviewer carries a distinct lens (e.g. correctness, build/dependency, security) — the orchestrator MUST NOT merge once the 2-reviewer minimum is met. It waits for **every** deliberately-assigned reviewer to approve (or to be explicitly released by the orchestrator with a recorded reason).

### Why

`validate_pr_review` (the 2-distinct-Approved hook) is satisfied at two approvals — but when a third reviewer was assigned *on purpose* to cover a lens the first two don't, merging at 2/3 ships the PR without the lens that reviewer was assigned to provide. The minimum-gate being green is not evidence that the deliberate review slate is complete.

### How to apply

1. Track the **assigned** reviewer slate per PR (from the spawn plan / execution matrix), not just the count of approvals received.
2. For a blast-radius PR (3+ assigned), gate merge on **all** assigned reviewers Approved — even though the hook would let you merge at 2.
3. To merge before an assigned reviewer finishes, the orchestrator must **explicitly release** that reviewer with a recorded reason (e.g. "released build/dep lens — change is docs-only after rebase"); silent merge-at-2/3 is not permitted.
4. This is orchestrator discipline today; a future enhancement could key the merge gate on assigned-reviewer count.

### Severity if violated

- Merge at 2/3 where the 3rd reviewer's lens turns out non-applicable: **minor** (lucky).
- Merge at 2/3 where the 3rd reviewer later surfaces a real finding the merged change embodies: **moderate** — the deliberate slate existed precisely to catch it.

### Origin

P4W4 ig#1002 (the DS `@theme` color bridge — app-wide blast radius): merged at 2/3 approvals before the deliberately-assigned 3rd (build/dependency) reviewer, Junseo, finished. His verdict (a false-alarm primary conclusion but a real adjacent DS-publish-drift finding → DS#111) landed post-merge; the outcome was non-blocking but only by luck. Owner-approved at the P4W4 retro.

## Single-Reviewer Exception (Wave-Bootstrap Only) <!-- promotion-target: none -->
The two-reviewer requirement may be waived **exclusively** for wave-bootstrap PRs — i.e., PRs that establish the tooling/CI/hooks that subsequent wave PRs will be gated by (e.g., the pre-commit hook rollout that the CI sweep depends on).

Strict conditions — **all must hold**:
- The PR is part of wave bootstrap (establishes infra that blocks other wave work)
- No more than **one** such exception per wave
- The single reviewer is the Standards & Quality Lead (Aino) or a comparable charter enforcer
- The exception is logged by name in the wave retro, with explicit justification

All other PRs require two comment-based reviews. `--admin` merges without two reviews are subject to the moderate-feedback-event classification in § Feedback System.

**See also:** § Trivial Cross-Repo Doc Sweep — a separate single-reviewer exception class for byte-identical doc syncs across child repos. The two exceptions are **independent budgets** (the wave-bootstrap 1-per-wave cap does not consume, and is not consumed by, doc-sweep waivers) and are **not cumulative** — a single PR may invoke at most one.

**Why:** In Phase 2 Wave 8, the single-reviewer shortcut was invoked 8× — it had stopped being an exception and become a pattern of convenience. This clause formalizes the boundary.

## Additive Commits on ChangesRequested (Mandatory) <!-- promotion-target: none -->

When a reviewer marks `RequestOrReplied: ChangesRequested`, the fix MUST land as an **additive commit on the same branch**. Force-push (`git push --force` / `git push --force-with-lease`) during a ChangesRequested cycle is **prohibited** because it resets the HEAD-SHA anchor that the reviewer's `gh api contents/<path>?ref=<sha>` verification chain depends on (see § Trust the Artifact, Not the Framing). Without HEAD-SHA stability, the re-review's "delta from prior review" comparison becomes unreliable.

**What is allowed during ChangesRequested:**
- New commits added to the same branch (no rewrite of existing commits)
- A merge commit to update from base if the base advanced (use `git merge origin/<base>`, not `git rebase`)

**What is prohibited during ChangesRequested:**
- `git push --force` / `--force-with-lease`
- `git rebase` followed by force-push
- `git commit --amend` followed by force-push
- Squashing prior commits before re-review

**If a rebase is genuinely needed** (e.g., merge conflict that cannot be resolved by a merge commit, or the requesting reviewer asks for a clean history), the implementer MUST open a comment thread on the PR BEFORE rebasing, get explicit "rebase OK" from the requesting reviewer, then rebase. The reply to a request-to-rebase counts as a `RequestOrReplied: Reply` not an Approval — the re-review cycle restarts from the new HEAD.

**Merging uses `--merge`, NEVER `--squash` — every base, including `main`** (owner directive 2026-07-30). Once both reviewers have posted `RequestOrReplied: Approved`, the HEAD-SHA anchor is no longer load-bearing and the PR may merge, but the merge method is **`gh pr merge <N> --merge`**.

*Why the previous "pre-approved squash is the standard path" wording was withdrawn:* GitHub's squash-merge re-authors the squashed commit to the bare `gh` principal, because every persona email is a Gmail `+alias` of the one `parametrization@gmail.com` account. The persona-authored content commits are discarded and git history attributes the work to nobody. Observed directly on 2026-07-30: PRs #1173/#1153/#1154/#1155/#1156 all merged to `main` as `parametrization <parametrization@gmail.com>`, losing Aino Virtanen / Nurul Hakim / Nadia Khoury / Weronika Zielinska / Lucas Ferreira attribution. `--merge` preserves those content commits; the bare-principal merge commit itself is excluded from author audits by `--no-merges`.

This **generalizes** the wave-branch rule in [`wave-merge.md`](wave-merge.md) § Per-issue → wave-branch merges (main#627/#898/#222) from "never squash into a wave branch" to "never squash, period." Hook 22 (`block_squash_wave_merge.py`) currently enforces only the wave-branch half — extending it to all bases is tracked separately; until that lands, this rule is convention-enforced, so **check the method before merging.**

**Why:** In Phase 3 Wave 3, all 4 ChangesRequested cycles (deploy#259 Path-A bundled, #261 perms+runbook, #266 cross-repo Option A, #267 5-fixes-in-49-lines) shipped as additive commits. The reviewers' second-pass reviews could compute the delta deterministically against the prior HEAD SHA. Zero force-pushes; zero "what changed since I last looked" ambiguity. Codifying the practice that worked.

**Severity if violated:** **Moderate** feedback event for the implementer. The reviewer may either re-do the full review at the new HEAD (slow path) or block merge until the implementer reverts the force-push and re-applies the fix as additive (correct path).

## Review Finding Disposition <!-- promotion-target: none -->
Every finding from a PR review must be dispositioned before merge. No finding may be silently dropped.

| Finding Type | Action Required | Blocks Merge? |
|-------------|----------------|---------------|
| **Must-fix** | PR originator fixes on the branch before merge | Yes |
| **Tech-debt** | Reviewer or originator creates a GitHub Issue for each item before merge | No (but issues must exist) |
| **Quick-fix tech-debt** | PR originator fixes immediately if minimal effort | No |

**Enforcement:** The charter enforcer (Aino) verifies during PR review that:
1. All must-fix items are resolved before approving merge
2. All tech-debt items have corresponding GitHub Issues created
3. Issues are labeled `tech-debt` and assigned to the appropriate team member

