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
- **Who counts as "the PR author"** — see § Who Counts as "the PR Author" (and Who May Review a Wave→Main Integration PR) below. The exclusion above is of the **PR author**, singular; on a wave→main integration PR that is nobody on the branch, and an implementer whose already-reviewed work the branch contains MAY post a counting `Approved`.
- Charter-format fields (`Requestor:` / `Requestee:` / `RequestOrReplied:` / `TechDebt:`) MUST appear ONLY in the trailer block — a contiguous structured-fields block at the end of the comment body, ideally after a bare-line `---` separator. Hook 4 extracts fields only from the trailer-block substring (post-last-`---`) and strips inline (`` `…` ``) and fenced (```` ```…``` ````) code regions before matching. Prose that quotes the field syntax above the trailer (or uses backticks to discuss it) will be ignored by the extractor, but reviewers should still avoid duplicating field patterns in prose for clarity. Pre-#511 the regex first-matched any `<Field>:` mention, which false-blocked 3 reviewer verdicts in P3W11 batch 11 (main#509, deploy#337, deploy#339) — each required orchestrator REST PATCH (resolves main#511).

## Who Counts as "the PR Author" (and Who May Review a Wave→Main Integration PR) <!-- promotion-target: hook -->

The 2-reviewer rule excludes **the PR author**, singular. Because every agent shares one GitHub account, "the PR author" is not readable from the PR's `author` field; the gate derives it from two independent sources and uses whichever is available:

1. **The head ref's `{FirstInitial}.{LastName}` prefix** — the author the human *declared*. Authoritative whenever present, which is 86.7% of the org's PRs (568/655 measured across 7 repos).
2. **The authors of the PR's own non-merge commits** (main#1210) — the only discriminator available on a ref carrying no prefix (`feature/x`, `dependabot/**`, an empty ref). Without it, a human on a hand-made branch could post their own `Approved`, add one genuine reviewer, and reach 2/2 where 1/2 is correct.

### The rule

**An implementer MAY post a counting `Approved` on the wave→main integration PR that contains their own merged work.** Their commits are on that branch; they are not its author.

**An implementer MAY NOT review the per-issue PR that contains their own commits.** This is unchanged and is where the whole force of the self-review rule lives. A per-issue PR carries the `{FirstInitial}.{LastName}` prefix, so source 1 excludes its author; a per-issue PR on a hand-made ref is caught by source 2.

### Why the wave→main integration PR is the exception

A wave→main integration PR has head ref `deployments/phase-{P}/wave-{M}` and base `main`. Neither source names its author:

- The ref names no persona — it names a wave.
- Its non-merge commits are **the wave's entire implementer roster**, because a wave branch accumulates every per-issue PR merged into it. Those commits **already carried two independent reviewers each, on their own per-issue PR**, and reached the branch through those reviewed merges. The integration PR authors no content of its own.

Treating all of them as "the PR author" applies a content-review rule to a PR that is not a content review — which [`wave-merge.md`](wave-merge.md) § Wave Merge PR Verification point 5 already says in as many words: *"the wave→main PR is an integration merge, not new code to re-review… Collecting fresh 2-reviewer approvals on the integration PR is not required and should not be requested."* This section states explicitly the corollary that was previously left implicit and that a hook had silently decided the other way.

The verdict an implementer casts on an integration PR is an **integration** verdict — this branch merges cleanly into `main`, CI is green on the combined tree, the scope is what the wave declared — not a re-review of their own diff. Reviewers should write it that way (cf. main#711's verdicts: *"an integration verdict over work already 2-reviewed and CI-green on the wave branch, not a line re-review"*).

### What this is NOT

- It is **not** a relaxation of the 2-reviewer threshold. Two distinct roster-valid current `Approved` Requestors are still required, and roster filtering is untouched.
- It is **not** a licence to self-approve anywhere else. On every non-wave ref — including a `deployments/**` ref that is not a wave branch, e.g. `deployments/phase12/cleanup` — commit-derived exclusion is fully in force.
- It does **not** make the integration PR's reviews mandatory. Point 5 of `wave-merge.md` still governs: fresh approvals are not required there, and the `wave-merge` admin exception remains the expected merge path.

### Stated residual

Nothing identifies the persona who *opened* the integration PR. They contribute merge commits (from `gh pr merge <per-issue-PR>` into the wave branch), and merge commits are deliberately excluded from author derivation — running a merge does not make you an author of the merged content. So on this PR class, a persona who both sequenced the wave merges and posts an `Approved` is not subtracted. This is the pre-main#294 state, not a new gap, and it sits inside the tolerance point 5 already grants a PR class that requires no fresh approvals at all. It is recorded here rather than left to be rediscovered.

### Evidence

Measured on 2026-08-03 over **every** `deployments/**`-head PR in all 7 repos (**202** PRs), driven through the gate's own `resolve_review_verdicts`:

| PR | ref | before → after | genuine reviewer subtracted |
|---|---|---|---|
| `noorinalabs-main#711` | `deployments/phase-5/wave-5` | 2/2 → 1/2 | Wanjiku Mwangi |
| `noorinalabs-main#530` | `deployments/phase-3/wave-11` | 2/2 → 1/2 | Aino Virtanen |
| `noorinalabs-main#293` | `deployments/phase-3/wave-6` | 2/2 → 1/2 | Aino Virtanen |
| `noorinalabs-main#229` | `deployments/phase-2/wave-10` | 1/2 → 0/2 | Aino Virtanen |

112 of the 202 derived **two or more** "branch authors"; the largest derived **11**. The eligible reviewer pool does **not** collapse below two — the roster gate unions all 7 repos' rosters (76 personas), so the remaining pool never dropped below 67 in the sweep. The cost is a **false subtraction of review work that was actually done**, plus a block message asserting that five people are "the branch author" of a PR none of them opened.

<!-- Resolves main#1216. Enforced by `validate_pr_review.py` (`COMMENT_SCAN_WAVE_INTEGRATION`, keyed on `charter_trailer.is_wave_branch`). -->

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

