---
name: wave-wrapup
description: Finalize a wave — PR review, merge sequencing, issue cleanup, worktree cleanup, and handoff to retro
args: team_name, Phase number, Wave number
---

Finalize a wave by reviewing all open PRs, merging in dependency order, closing resolved issues, and cleaning up. This is the **exit gate** before running `/wave-retro`.

> See [`.claude/team/lifecycle.md`](../../team/lifecycle.md) § Wave Lifecycle for the canonical skill order and preconditions.

> Note: all repo paths in bash blocks below are rooted at `$REPO_ROOT` to avoid cwd drift when the skill is invoked from a worktree or child-repo subdirectory (#149).

## Instructions

### 1. Inventory open PRs

List all PRs targeting the wave's deployment branch:

```bash
gh pr list --state open --base "deployments/phase-{P}/wave-{M}" --json number,title,author,headRefName,reviews,isDraft,createdAt
```

Also check for PRs targeting `main` that belong to this wave (by label or branch pattern):

```bash
gh pr list --state open --base main --label "p{P}-wave-{M}" --json number,title,author,headRefName,reviews
```

### 2. Check CI status for each PR

For each open PR:

```bash
gh pr checks {NUMBER} --json name,conclusion,status
```

Classify each PR:
| Status | Criteria | Action |
|--------|----------|--------|
| **Ready** | CI green, has peer review | Merge |
| **Needs review** | CI green, no peer review | Request review |
| **CI failing** | CI red | Fix before merge |
| **Draft** | Marked as draft | Exclude (report only) |
| **Blocked** | Has unmerged dependency | Defer until dependency merges |

### 3. Determine merge order

Build a merge dependency graph:
- Parse PR bodies for `Depends on #N` or `After #N` references
- Check if any PR modifies files that another PR also modifies (merge conflict risk)
- Independent PRs can merge in parallel; dependent PRs merge in order

Present the proposed merge sequence:

```
**Merge Sequence: Phase {P} Wave {M}**

| Order | PR | Title | Status | Dependencies | Action |
|-------|-----|-------|--------|--------------|--------|
| 1     | #N  | ...   | Ready  | None         | Merge  |
| 2     | #N  | ...   | Ready  | After #M     | Merge  |
| —     | #N  | ...   | CI failing | — | Fix first |
| —     | #N  | ...   | Draft  | — | Skip |
```

**Do NOT merge any PRs until the user approves the sequence.**

### 4. Review each ready PR

For each PR marked "Ready", perform a review using charter format (same as `/review-pr`):

```bash
gh pr diff {NUMBER}
```

Post review comment:

```
Requestor: {Reviewer.Name}
Requestee: {PR author}
RequestOrReplied: Request

**Review: {LGTM or issues}**
Must-fix: {list or "None"}
Tech-debt: {list or "None"}
```

For each tech-debt item, create a GitHub Issue labeled `tech-debt` and the next wave/phase label.

If must-fix items are found, do NOT merge — report and wait for fixes.

### 5. Merge approved PRs

After user approval, merge in the determined order:

```bash
gh pr merge {NUMBER} --merge --delete-branch
```

After each merge, verify:
- CI passes on the target branch
- No merge conflicts introduced for subsequent PRs

If a merge introduces CI failures, stop and report before continuing.

### 6. Close resolved issues

Run `/wave-audit` logic to close issues resolved by the merged PRs:

```bash
# For each merged PR, check for Closes/Fixes/Resolves references
gh pr view {NUMBER} --json body
```

Close referenced issues with audit comments. Also check for issues matched by branch naming convention.

### 7. Verify completeness

Check that all wave issues are resolved:

```bash
gh issue list --state open --label "p{P}-wave-{M}" --json number,title
```

For any remaining open issues:
- If the work was deferred, move to the next wave label
- If the work was partially done, document what remains
- Report all unresolved items

### 8. Clean up worktrees (mandatory)

**All wave worktrees MUST be removed before the wrapup is considered complete.** Stale worktrees accumulate across waves and cause branch contention.

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
# Prune any stale worktree metadata
git -C "$REPO_ROOT" worktree prune

# List all worktrees and identify wave-related ones
git -C "$REPO_ROOT" worktree list

# Remove each wave worktree (branches matching wave assignees)
# Example: git -C "$REPO_ROOT" worktree remove "$REPO_ROOT/.claude/worktrees/W.Mwangi+0063-fix-branch-freshness-worktree" --force
```

For each worktree:
1. Check if it has uncommitted changes (`git -C <path> status --porcelain`)
2. If clean, remove with `git worktree remove <path>`
3. If dirty, report to the user — do NOT force-remove without approval
4. Delete the remote tracking branch if the PR was merged: `git push origin --delete <branch>` — **feature/worktree branches only; NEVER delete a `deployments/phase-*/wave-*` branch** (wave branches are retained permanently per owner directive 2026-06-09 — see Step 11).

Report what was cleaned:
```
**Worktree Cleanup:**
- Removed: {count} worktrees
- Skipped (dirty): {count}
- Remote branches deleted: {count}
```

**Why:** Phase 2 Wave 1 left 6 stale worktrees after merge because cleanup wasn't enforced.

### 9. Update documentation

Check if any merged PRs affect documentation:

```bash
# List files changed across all merged PRs
for pr in {merged_pr_numbers}; do
    gh pr diff "$pr" --name-only
done
```

Flag any changes to:
- API endpoints (update API docs)
- Configuration files (update deployment docs)
- Architecture (update diagrams)
- Charter or process files (note for retro)

### 9.5. Retro PR body-vs-diff sanity check (added P3W9 #414 — 2026-05-13)

Per `charter/pull-requests.md § Retro PR Body-vs-Diff Discipline` (Skill enforcement clause): if a retro PR for this wave is already open, every charter/skill/trust-matrix file claimed in its PR body MUST appear in the PR's diff. Direct-to-main commits for ratified retro outputs are forbidden — they bypass the two-reviewer gate and `validate_pr_ci_status`, and break the audit trail.

Run this check before emitting the Step 10 wrapup table so any mismatch surfaces in the table itself:

```bash
# Discover the open retro PR for this wave (if any).
# Retro PRs are conventionally titled `retro(P{P}W{M}…)`.
RETRO_PR=$(gh pr list --repo noorinalabs/noorinalabs-main --state open \
  --search 'retro( in:title' \
  --json number,title \
  --jq ".[] | select(.title | test(\"retro\\\\(P{P}W{M}\")) | .number" | head -1)

if [ -z "$RETRO_PR" ]; then
  echo "No open retro PR for P{P}W{M} — skipping body-vs-diff check."
else
  gh pr view "$RETRO_PR" --repo noorinalabs/noorinalabs-main --json files --jq '[.files[].path] | sort' > /tmp/retro_${RETRO_PR}_diff.json
  gh pr view "$RETRO_PR" --repo noorinalabs/noorinalabs-main --json body --jq '.body' > /tmp/retro_${RETRO_PR}_body.md

  # Manually inspect /tmp/retro_${RETRO_PR}_body.md's "Files changed" section and
  # compare each claimed path against /tmp/retro_${RETRO_PR}_diff.json. For each
  # path claimed in the body but missing from the diff JSON, ABORT with a clear
  # "body claims X not in diff" error and surface the mismatch in the Step 10
  # wrapup table. Do NOT proceed to Step 10 until the retro author either
  # commits the missing file to the retro branch (preferred) or amends the body
  # to remove the unsupported claim.
fi
```

Worked example of the failure mode this catches: PR [#124](https://github.com/noorinalabs/noorinalabs-main/pull/124) (W8 retro) body claimed 7 files, diff contained 2 (`feedback_log.md` + `ontology/checksums.json`); the other 5 (`trust_matrix.md`, `charter/pull-requests.md`, `charter/hooks.md`, `skills/wave-retro/SKILL.md`, `skills/wave-kickoff/SKILL.md`) were committed direct-to-main as `2b92605` + `ecd1c76`, bypassing review and CI. The check above would have flagged all 5 missing paths and blocked Step 10 emission until the retro PR was fixed. Filed as [#126](https://github.com/noorinalabs/noorinalabs-main/issues/126); skill-side mirror filed as [#414](https://github.com/noorinalabs/noorinalabs-main/issues/414).

This step mirrors `/wave-retro` Step 6.5 by design — the same check fires from both skills so a body-vs-diff mismatch is caught whether the operator runs `/wave-retro` first (post-author check before requesting reviewers) or `/wave-wrapup` after the retro PR is open (pre-wrapup-table check). The two skills converge on the authoritative shape in `charter/pull-requests.md § Retro PR Body-vs-Diff Discipline`.

### 10. Final wave report

```
**Wave Wrapup: Phase {P} Wave {M}**

**PRs:**
- Merged: {count}
- Deferred: {count} (moved to next wave)
- Still failing CI: {count}

**Issues:**
- Closed: {count}
- Remaining open: {count} (deferred)

**Tech-debt created:** {count} new issues

**Staging promotion:** {success | failure | deferred (criterion #1 not yet live) | overridden: <rationale>} {run URL if any}

**Documentation:** {docs updated | docs need update | no doc changes}

**Worktrees cleaned:** {count}

**Next step:** Run `/wave-retro` for full retrospective with assessments and trust updates.
```

### 10.5. Write canonical counter keys to `cross-repo-status.json`

> **High-volume remote-merge checkpoint (added P3W13 #566 — 2026-05-31).** Before the **first local bookkeeping commit** of the wrapup (the counter-key write below, the ontology rebuild commit, the wrap-marker commit), if this wave merged **N ≥ 10 PRs via `gh` against remote branches**, the local checkout may be many commits behind origin. Re-sync first:
>
> ```bash
> REPO_ROOT="$(git rev-parse --show-toplevel)"
> CUR_BRANCH="$(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD)"
> git -C "$REPO_ROOT" fetch --quiet origin "$CUR_BRANCH"
> BEHIND=$(git -C "$REPO_ROOT" rev-list --count "HEAD..origin/$CUR_BRANCH" 2>/dev/null || echo 0)
> if [ "${BEHIND:-0}" -gt 0 ]; then
>   echo "Local is $BEHIND behind origin/$CUR_BRANCH — re-syncing before bookkeeping commit."
>   # Stash/relocate any in-progress local edits FIRST (a hard reset discards them).
>   git -C "$REPO_ROOT" reset --hard "origin/$CUR_BRANCH"
> fi
> ```
>
> **Why:** P3W13 merged 37 PRs remotely while the local parent sat 22 commits behind; the counter-key commit landed on a stale tree and needed a recovery `reset --hard` that discarded uncommitted session state (`.claude/annunaki/errors.jsonl`). Re-syncing **before** the first bookkeeping write — and relocating any local edits first, since the reset is destructive — prevents both the stale-tree commit and the lossy recovery. Origin > local clone for all wrap-time state (charter `pull-requests.md § Origin > Local Clone`).

Write the **top-level** canonical counter keys that `/wave-retro` Step 2.5 verifies. Pre-#318 these were either missing or buried under `wave_{M}_summary.*`, which forced a manual followup commit at retro (P3W7 `fb459b2`). Post-#318 the skill writes them at wrapup time so retro reads cleanly.

Use the shared `upsert_status_keys.py` helper at `.claude/lib/` — it does targeted text-level upsert that preserves the compact-inline shape of `cross-repo-status.json` (a naive `jq … > tmp && mv` reformats every compact line to pretty form, producing a 500-line cosmetic diff per wave — see `main#332`). The helper also validates JSON before AND after the rewrite. Promoted from `/wave-scope` to `.claude/lib/` per `main#292` (multi-consumer → shared lib).

> **Mechanical computation (added P3W10 #421 — 2026-05-13).** Pre-#421 the
> `CHANGES_REQUESTED_CYCLES` and `TOP_CONCENTRATION_PCT` placeholders here
> were filled in by hand by the orchestrator; the resulting null/wrong
> values had to be recomputed at retro for 3 consecutive waves (W4 80%,
> W5 6→4, W9 null+null). The mechanical computation below eliminates the
> recompute pattern by deriving both counters directly from the merged-PR
> set across `wave_{M}_repos_in_scope`. `FINAL_PR_COUNT` remains the
> already-computed Step 10 "PRs: Merged" number.
>
> **Cross-window filter (added P3W10 #423 — 2026-05-13).** When a wave-branch
> is reused across partition events (W9 split mid-wave into pre-partition
> non-deploy PRs + post-partition canonical 6 PRs — owner directive
> 2026-05-12), `gh pr list --base "deployments/phase-{P}/wave-{M}"` returns
> the union of ALL windows, not the canonical wave's window. W9 actuals:
> 30 PRs returned vs 6 canonical → TOP_CONCENTRATION_PCT computed as 50%
> against the cross-window set vs 67% canonical. The fix below uses
> `wave_{M}_kicked_off_at` as a `mergedAt >= X` filter to scope the PR set
> to the canonical window (Option A), plus a `FINAL_PR_COUNT`-vs-tally
> cross-check that loud-fails on residual mismatch (Option B — defense in
> depth for re-roll-within-window edge cases A misses).

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
STATUS="$REPO_ROOT/cross-repo-status.json"
UPSERT="$REPO_ROOT/.claude/lib/upsert_status_keys.py"

# FINAL_PR_COUNT is the Step 10 "PRs: Merged" number — already in hand.
FINAL_PR_COUNT={count_of_merged_PRs}

# Cross-window filter (Option A — #423). The wave's canonical window starts
# at `wave_{M}_kicked_off_at`; anything merged before is from a prior window
# (W9 partition lesson). If the key is missing (legacy waves W1-W3 pre-/wave-start),
# fall back to no-filter and rely solely on Option B's cross-check below.
KICKOFF=$(jq -r '.["wave_{M}_kicked_off_at"] // empty' "$STATUS")

# Build the wave's merged-PR set across all repos in scope. Includes mergedAt
# so the kickoff filter applies; falls through unfiltered when KICKOFF is empty.
PRS_JSON=$(jq -r '.["wave_{M}_repos_in_scope"][]' "$STATUS" | while read -r REPO; do
  if [ -n "$KICKOFF" ]; then
    gh pr list --repo "noorinalabs/$REPO" --state merged \
      --base "deployments/phase-{P}/wave-{M}" \
      --json number,headRefOid,mergedAt \
      --jq ".[] | select(.mergedAt >= \"$KICKOFF\") | . + {repo: \"$REPO\"}"
  else
    gh pr list --repo "noorinalabs/$REPO" --state merged \
      --base "deployments/phase-{P}/wave-{M}" \
      --json number,headRefOid,mergedAt \
      --jq ".[] | . + {repo: \"$REPO\"}"
  fi
done | jq -s .)

# Cross-check (Option B — #423). After the kickoff filter, the PR set should
# match Step 10's `FINAL_PR_COUNT`. A mismatch indicates either a re-roll
# within the canonical window (rare but possible) or a missing `kicked_off_at`
# key. Loud-fail rather than emit silently-wrong counters; the operator must
# manually scope the PR set (e.g., by hand-listing the canonical PR numbers).
GH_COUNT=$(echo "$PRS_JSON" | jq 'length')
if [ "$GH_COUNT" != "$FINAL_PR_COUNT" ]; then
  echo "ERROR: post-kickoff-filter PR count ($GH_COUNT) != FINAL_PR_COUNT ($FINAL_PR_COUNT)" >&2
  echo "Possible cross-window contamination or re-roll within canonical window." >&2
  echo "Inspect: gh pr list --base deployments/phase-{P}/wave-{M} --state merged --json number,mergedAt" >&2
  echo "Then either: (a) verify wave_{M}_kicked_off_at in cross-repo-status.json is correct," >&2
  echo "or (b) manually scope the PR list by editing this step's PRS_JSON construction." >&2
  exit 1
fi

# CHANGES_REQUESTED_CYCLES — count `RequestOrReplied: ChangesRequested` verdict
# comments across every wave PR's issue-comments timeline.
CHANGES_REQUESTED_CYCLES=$(echo "$PRS_JSON" | jq -r '.[] | "\(.repo) \(.number)"' | while read -r R N; do
  gh api "repos/noorinalabs/$R/issues/$N/comments" \
    --jq '[.[] | select(.body | test("RequestOrReplied:\\s*ChangesRequested"))] | length'
done | awk '{s+=$1} END {print s+0}')

# TOP_CONCENTRATION_PCT — derived from commit-identity concentration on each
# PR's head: count PRs per commit-author name, take the top author's PR count
# as a percentage of total. Half-up rounding via awk `printf "%d\n", x + 0.5`
# (4/6 = 66.67 → 67) so the counter matches the human-recorded W9 history row
# (Wanjiku TPM-vote 2026-05-13).
TOP_CONCENTRATION_PCT=$(echo "$PRS_JSON" | jq -r '.[] | "\(.repo) \(.headRefOid)"' | while read -r R SHA; do
  gh api "repos/noorinalabs/$R/commits/$SHA" --jq '.commit.author.name'
done | sort | uniq -c | sort -rn | awk -v total="$(echo "$PRS_JSON" | jq 'length')" \
  'NR==1 {printf "%d\n", $1 * 100 / total + 0.5}')

# Each value MUST be a self-contained JSON literal (integer here — no quotes).
python3 "$UPSERT" "$STATUS" \
    "wave_{M}_final_pr_count=${FINAL_PR_COUNT}" \
    "wave_{M}_changes_requested_cycles=${CHANGES_REQUESTED_CYCLES}" \
    "wave_{M}_top_concentration_pct=${TOP_CONCENTRATION_PCT}"

# Read-back verify (memory `feedback_gh_pr_edit_silent_noop` family — any
# jq/upsert pipeline that silently fails produces zero diff but exit 0).
jq -r --arg m "{M}" '
  "wave_" + $m + "_final_pr_count = " + (.["wave_" + $m + "_final_pr_count"] | tostring),
  "wave_" + $m + "_changes_requested_cycles = " + (.["wave_" + $m + "_changes_requested_cycles"] | tostring),
  "wave_" + $m + "_top_concentration_pct = " + (.["wave_" + $m + "_top_concentration_pct"] | tostring)
' "$STATUS"
```

Optionally also write a richer `wave_{M}_summary` block with wave-shape detail (per-tier PR breakdown, charter-change proposals, thesis text — see P3W7 `cross-repo-status.json` for the canonical shape). Top-level keys above remain **authoritative** for `/wave-retro` Step 2.5; the summary block is a supplementary surface for retro-prose composition.

**Why top-level not nested:** `/wave-retro` Step 2.5 reads via `jq -r ".wave_${M}_final_pr_count"` — a direct top-level lookup. Nesting under `wave_{M}_summary.final_pr_count` would require Step 2.5 changes per wave-counter-key, breaking the canonical-key contract. Top-level keeps the read-side simple.

**Acceptance for /wave-retro Step 2.5:**
- All three keys exist at top-level after `/wave-wrapup` completes.
- Values match the rendered Step 10 wave report.
- A `wave_{M}_summary` block, if also present, must not contradict the top-level values (top-level is authoritative).

If a key cannot be computed (e.g., no PRs merged this wave), write the literal `0` — `/wave-retro` Step 2.5 distinguishes "0 cycles" from "key missing" and only the latter is treated as drift.

### 11. Merge to main per repo (every wave)

**Every wave's wrapup merges its wave branch to main** (changed 2026-06-09 — owner directive; previously gated to the final wave only). Each repo in `wave_{M}_repos_in_scope` has its OWN `deployments/phase-{P}/wave-{M}` branch (created by `/wave-kickoff` step 1) that needs its own PR to main. This is the symmetric counterpart of the multi-repo branch creation gap (main#238). Merging each wave keeps `main` continuously current: the next wave bases off main (`/wave-start` Step 2/3), so an unmerged wave would strand its work the moment the following wave starts.

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
WAVE_REPOS_IN_SCOPE=$(jq -r ".wave_{M}_repos_in_scope[]" "$REPO_ROOT/cross-repo-status.json")
BRANCH="deployments/phase-{P}/wave-{M}"

for R in $WAVE_REPOS_IN_SCOPE; do
  # Skip repos where the wave branch is already merged or doesn't exist
  EXISTING=$(gh api "repos/noorinalabs/$R/git/refs/heads/$BRANCH" --jq '.object.sha' 2>/dev/null || true)
  [ -z "$EXISTING" ] && { echo "$R: no wave branch — skip"; continue; }

  # Check if there's anything to merge (compare branch HEAD vs main HEAD)
  MAIN_SHA=$(gh api "repos/noorinalabs/$R/git/refs/heads/main" --jq '.object.sha')
  if [ "$EXISTING" = "$MAIN_SHA" ]; then
    echo "$R: wave branch ==  main, nothing to merge"; continue
  fi

  # Create PR from this repo's wave branch to its own main
  gh pr create --repo "noorinalabs/$R" --base main --head "$BRANCH" \
    --title "Phase {P} Wave {M} → main ($R)" \
    --body "Final wave merge for $R. All PRs reviewed and merged to wave branch."
done
```

Print a per-repo PR summary table (PR# or "no merge needed") and **wait for user approval before merging any PR**. Each PR must be merged independently.

**Do NOT merge to main without user approval.** This is a significant action that affects all downstream repos.

**Retain the wave branch — do NOT delete it on merge** (owner directive 2026-06-09). Merge each wave→main PR with `gh pr merge <N> --merge` (**never** `--delete-branch`); the `deployments/phase-{P}/wave-{M}` branches are kept permanently as a historical / rollback anchor for every wave. Caveat: if a repo has "Automatically delete head branches" enabled at the repo level, a merge deletes the head branch regardless of the flag — for these repos, either disable that setting or restore the branch immediately after merge (`git push origin <wave-sha>:refs/heads/deployments/phase-{P}/wave-{M}`).

### 11.5. Reachability gate — wave-branch propagation to main (every wave)

After the per-repo wave→main PRs in Step 11 are merged (or declared not-needed), verify each wave-branch is actually reachable from `origin/main`. This is the load-bearing enforcement counterpart to charter `state-claims.md § Sub-rule: merge_commit_sha reachability` — the rule's claim-time discipline becomes a wrapup-time gate.

Origin story: `main#339` — `deployments/phase-3/wave-7` ended up 10 ahead / 15+ behind / diverged from main with no wave→main PR ever opened. The wave was treated as "closed" because individual PRs into the wave-branch were merged, but the wave-branch itself never reached main. PR #305 (the `validate_commit_identity` backslash fix) and 11 hook fixtures sat stranded on a branch no operator was tracking.

This step catches that pattern at wrapup time, before the wave is declared closed.

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
WAVE_REPOS_IN_SCOPE=$(jq -r ".wave_{M}_repos_in_scope[]" "$REPO_ROOT/cross-repo-status.json")
BRANCH="deployments/phase-{P}/wave-{M}"

STRANDED=()
for R in $WAVE_REPOS_IN_SCOPE; do
  # Skip repos where the wave branch doesn't exist (scope-drop case)
  WAVE_SHA=$(gh api "repos/noorinalabs/$R/git/refs/heads/$BRANCH" --jq '.object.sha' 2>/dev/null || true)
  [ -z "$WAVE_SHA" ] && { echo "$R: no wave branch — skip (scope-drop)"; continue; }

  # Compare wave-branch against main at origin (NOT local clone — per charter
  # pull-requests.md § Origin > Local Clone)
  COMPARE=$(gh api "repos/noorinalabs/$R/compare/main...$BRANCH" \
    --jq '{ahead_by, behind_by, status}')
  AHEAD=$(echo "$COMPARE" | jq -r .ahead_by)
  STATUS=$(echo "$COMPARE" | jq -r .status)

  if [ "$AHEAD" -gt 0 ] || [ "$STATUS" = "diverged" ]; then
    # Check if a wave→main PR exists in any state — explains the gap if so
    PR_EXISTS=$(gh pr list --repo "noorinalabs/$R" --base main --head "$BRANCH" \
      --state all --limit 5 --json number,state,mergedAt \
      --jq '[.[] | select(.state == "MERGED" or .state == "OPEN")] | length')
    STRANDED+=("$R: ahead_by=$AHEAD status=$STATUS wave→main PRs found=$PR_EXISTS")
  else
    echo "$R: wave-branch reachable from main (ahead_by=$AHEAD, status=$STATUS) — OK"
  fi
done

if [ ${#STRANDED[@]} -gt 0 ]; then
  echo "════════════════════════════════════════════════════════════"
  echo "BLOCKED: /wave-wrapup cannot close wave {M} — STRANDED repos:"
  for s in "${STRANDED[@]}"; do echo "  $s"; done
  echo ""
  echo "Each STRANDED repo has wave-branch commits NOT reachable from origin/main."
  echo "Fix-forward options:"
  echo "  (a) Open the wave→main PR (re-run Step 11 if no PR exists)"
  echo "  (b) Merge an already-OPEN wave→main PR"
  echo "  (c) If stranding is INTENTIONAL (descoped wave, rolled-back work), set"
  echo "      STRANDING_OVERRIDE_RATIONALE=\"<explicit reason>\" before re-invoking"
  echo "      /wave-wrapup. The override is logged to the wrapup report and to"
  echo "      cross-repo-status.json under wave_{M}_stranding_override."
  echo "════════════════════════════════════════════════════════════"
  exit 1
fi
```

**Override mechanism** (when stranding is intentional):

```bash
# Only use when the wave is deliberately not merged to main
# (descoped, rolled back, or held for sequencing reasons)
export STRANDING_OVERRIDE_RATIONALE="P3W7 work descoped post-#339 audit; \
  wave-7 branch retained for historical reference, no propagation intended"
# Re-invoke /wave-wrapup — the gate sees the rationale, logs it, and proceeds
```

The override is intentionally noisy: rationale is required (no empty string), logged to the wrapup report, and persisted to `cross-repo-status.json` under `wave_{M}_stranding_override` so subsequent /wave-retro and audit passes can surface it.

### 11.6. Staging-promotion gate (Phase-3 end-state criterion #3)

A wave is **not closeable until its merged code has been promoted to staging green**. This is the wrapup-time enforcement of Phase-3 end-state criterion #3 (`main#325`) and the charter rule `pull-requests.md § Wave-Wrapup Staging-Promotion Gate`. It runs AFTER the Step 11.5 reachability-to-main gate (code must be on main before it can be promoted to staging) and BEFORE the ontology rebuild.

The canonical staging deploy is `noorinalabs-deploy/.github/workflows/deploy-stg.yml`. The gate inspects the latest run; blocks on red; **defers** (does not fail) when staging does not yet exist — criterion #3 is blocked by criterion #1 (live staging). An explicit rationale env var overrides a red/absent run.

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
STATUS="$REPO_ROOT/cross-repo-status.json"
UPSERT="$REPO_ROOT/.claude/lib/upsert_status_keys.py"
STG_WORKFLOW="deploy-stg.yml"
DEPLOY_REPO="noorinalabs/noorinalabs-deploy"

# Fetch the latest deploy-stg.yml run. Empty result = staging not live yet.
STG_RUN=$(gh run list --repo "$DEPLOY_REPO" --workflow "$STG_WORKFLOW" \
  --limit 1 --json databaseId,status,conclusion,url,headSha \
  --jq '.[0] // empty' 2>/dev/null || true)

if [ -z "$STG_RUN" ]; then
  # Criterion #1 not satisfied — defer, do NOT hard-fail. Logged, not silent.
  STG_RESULT="deferred"
  STG_URL=""
  echo "staging-promotion gate DEFERRED — criterion #1 (live staging) not yet satisfied"
  echo "  (no $STG_WORKFLOW run history in $DEPLOY_REPO). Gate auto-activates once staging is live."
else
  STG_STATUS=$(echo "$STG_RUN" | jq -r .status)
  STG_CONCLUSION=$(echo "$STG_RUN" | jq -r .conclusion)
  STG_URL=$(echo "$STG_RUN" | jq -r .url)

  if [ "$STG_STATUS" != "completed" ]; then
    echo "staging deploy still in progress ($STG_STATUS) — re-run /wave-wrapup once $STG_URL completes,"
    echo "or set STG_PROMOTION_OVERRIDE_RATIONALE to close anyway."
    STG_CONCLUSION="in_progress"
  fi

  if [ "$STG_CONCLUSION" = "success" ]; then
    STG_RESULT="success"
    echo "staging promotion GREEN — $STG_URL"
  elif [ -n "${STG_PROMOTION_OVERRIDE_RATIONALE:-}" ]; then
    STG_RESULT="overridden"
    echo "staging promotion NOT green ($STG_CONCLUSION) — OVERRIDDEN:"
    echo "  $STG_PROMOTION_OVERRIDE_RATIONALE"
  else
    echo "════════════════════════════════════════════════════════════"
    echo "BLOCKED: /wave-wrapup cannot close wave {M} — staging promotion is $STG_CONCLUSION."
    echo "  Latest $STG_WORKFLOW run: $STG_URL"
    echo "Fix-forward options:"
    echo "  (a) Fix the regression and re-trigger the staging deploy, then re-run /wave-wrapup."
    echo "  (b) Re-dispatch deploy-stg.yml manually:"
    echo "      gh workflow run $STG_WORKFLOW --repo $DEPLOY_REPO"
    echo "  (c) If a red/absent staging run is INTENTIONALLY acceptable (staging infra"
    echo "      mid-migration, meta-only wave with no deployable surface), set"
    echo "      STG_PROMOTION_OVERRIDE_RATIONALE=\"<explicit reason>\" before re-invoking."
    echo "════════════════════════════════════════════════════════════"
    exit 1
  fi
fi

# Persist the result for /wave-retro Step 2.5 + audit passes. Compact-inline
# preserved via upsert_status_keys.py (NOT jq>tmp>mv — see main#332).
python3 "$UPSERT" "$STATUS" \
    "wave_{M}_stg_promotion=\"${STG_RESULT}\"" \
    "wave_{M}_stg_promotion_url=\"${STG_URL}\""
[ "$STG_RESULT" = "overridden" ] && python3 "$UPSERT" "$STATUS" \
    "wave_{M}_stg_promotion_override_rationale=\"${STG_PROMOTION_OVERRIDE_RATIONALE}\""

# Read-back verify (feedback_gh_pr_edit_silent_noop family).
jq -r --arg m "{M}" '"wave_" + $m + "_stg_promotion = " + (.["wave_" + $m + "_stg_promotion"] | tostring)' "$STATUS"
```

**Override mechanism** (when a red/absent staging run is acceptable):

```bash
# Only use when staging green is genuinely not achievable/applicable for this wave
# (staging infra mid-migration, meta-only wave with no deployable surface).
export STG_PROMOTION_OVERRIDE_RATIONALE="W13 is charter/skill-meta only; no service \
  image changed, so no staging deploy is produced. Gate overridden, criterion #3 \
  unaffected (no deployable surface to promote)."
# Re-invoke /wave-wrapup — the gate logs the rationale, persists it, and proceeds.
```

Include the staging-promotion result (`success`/`failure`/`deferred`/`overridden`) and the run URL in the Step 10 final wave report. `/wave-retro` records it in the wave history row alongside PR count and admin overrides.

### 11.6a. Per-merge deploy watch (active — `/watch-deploy`)

The Step 11.6 gate above inspects only the **latest** `deploy-stg.yml` run. That misses the failure mode deploy#418 surfaced: a wave→main merge in one repo triggers a deploy that fails (e.g. a user-service merge that broke the image pull), which is then masked when a later merge's deploy goes green and becomes "latest". To close this, **actively follow the deploy each wave→main merge triggered**, not just the most-recent run.

For each repo in `wave_{M}_repos_in_scope` that participates in the staging fan-in (`noorinalabs-isnad-graph`, `noorinalabs-user-service` — the repos whose `ghcr-publish.yml` dispatches `deploy-stg.yml`), take that repo's Step 11 wave→main merge commit and run:

```
/watch-deploy stg <merge_sha>
```

`/watch-deploy` polls that specific dispatched deploy to a terminal state, classifies any failure, attempts a single bounded fix-forward (e.g. re-dispatch `stg-latest`), and escalates with a diagnosis otherwise. A wave is not closeable while any fan-in merge's deploy is red and unremediated — fold any escalation into the Step 11.6 block/override decision above.

Landing-page and meta-only repos do not participate in the stg fan-in (no dispatch), so they have no per-merge deploy to watch — skip them.

**Production counterpart:** prod deploys are gated on owner approval (owner directive 2026-06-09). `/wave-wrapup` must NOT approve or trigger them. When the owner approves a queued prod deploy for this wave's promotion, run `/watch-deploy prod <sha>` to monitor it the same way; `/watch-deploy` never advances or auto-remediates prod.

### 12. Ontology rebuild

Run `/ontology-rebuild` to process any files that changed during this wave. This ensures the ontology reflects the current state of all repos before the wave closes.

- If no dirty files exist in `ontology/checksums.json`, report "Ontology: up to date" and skip
- The resolver will auto-update docs where appropriate and flag recommend-only changes
- Include ontology changes in the final wave report

### 13. Annunaki error attack

> **Preferred surface is `/wave-retro` Step 7.6 (P3W9 #344).** Retro is the natural moment for this audit — findings feed the retro's charter-change proposals. Wrapup retains this step as a fallback for cases where retro is delayed or skipped. The run-marker below prevents double-execution.

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
ALREADY_RAN=$(jq -r ".wave_${M}_annunaki_attack_ran_at // empty" "$REPO_ROOT/cross-repo-status.json")

if [ -n "$ALREADY_RAN" ]; then
  echo "Annunaki-attack: already ran at $ALREADY_RAN (via /wave-retro Step 7.6). Skipping."
  # Continue to Step 14.
else
  # Proceed with the attack below; on completion write the marker.
fi
```

Run `/annunaki-attack` to process any errors captured by the Annunaki monitor during this wave. This converts observed errors into preventative automation (hooks, skills, charter updates) before the wave closes.

- If `.claude/annunaki/errors.jsonl` is empty or missing, report "Annunaki: No errors captured this wave" and skip the attack — but still write the run-marker so retro's 7.6 doesn't re-check
- Use the current wave label for any issues created
- Include Annunaki-created issues and PRs in the final wave report totals
- This step runs **before** the memory-to-automation audit so that new hooks/skills from error analysis are visible to the memory audit
- On completion, write `wave_${M}_annunaki_attack_ran_at = <ISO-8601 UTC timestamp>` to `cross-repo-status.json`

### 14. Memory-to-automation audit

> **Preferred surface is `/wave-retro` Step 7.7 (P3W9 #344).** Retro is the natural moment for this audit — findings feed the retro's charter-change proposals and the Aino-spawned conversion issues count toward the same retro's per-engineer assessment + trust update pass. Wrapup retains this step as the canonical procedure body (referenced by retro's 7.7) and as a fallback for retro-delayed cases. The run-marker below prevents double-execution.

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
ALREADY_RAN=$(jq -r ".wave_${M}_memory_audit_ran_at // empty" "$REPO_ROOT/cross-repo-status.json")

if [ -n "$ALREADY_RAN" ]; then
  echo "Memory-to-automation audit: already ran at $ALREADY_RAN (via /wave-retro Step 7.7). Skipping."
  # Continue to the rest of the wrapup.
else
  # Proceed with the audit below; on completion write the marker.
fi
```

Examine all memory files in the project memory directory for entries that describe behaviors, rules, or patterns that could be codified as a **hook**, **skill**, or **charter update** instead of remaining as soft memory. On completion, write `wave_${M}_memory_audit_ran_at = <ISO-8601 UTC timestamp>` to `cross-repo-status.json`.

**Process:**

1. **Read all memory files:**
   ```bash
   ls ~/.claude/projects/*/memory/*.md
   ```

2. **For each memory file**, classify it:
   | Category | Criteria | Action |
   |----------|----------|--------|
   | **Hook candidate** | Describes a rule that should be enforced automatically (e.g., "always do X before Y", "never do Z") | Create the hook, add to settings.json, create GH issue for bookkeeping |
   | **Skill candidate** | Describes a repeatable multi-step workflow (e.g., "when doing X, follow these steps") | Create the skill in `.claude/skills/`, create GH issue |
   | **Charter update** | Describes a process rule or convention that should be documented for all agents | Update the relevant charter section, create GH issue |
   | **Keep as memory** | User-specific context, preferences, or project state that doesn't fit the above | Leave as-is |

3. **For each hook/skill/charter candidate:**
   a. Create a GitHub Issue describing the automation opportunity
   b. **Assign to the best-fit team member** based on the charter mapping:
      - Hooks and charter updates → Aino Virtanen (Standards & Quality Lead)
      - Skills → Aino Virtanen or the domain expert for that workflow
      - Code changes → the relevant repo's tech lead
   c. **Spawn or message that person** with the issue details and full context
   d. Wait for them to confirm completion
   e. Once confirmed: verify the implementation (hook works, skill invokes, charter reads correctly)
   f. Push changes and close the issue
   g. **Delete or update the memory file** — if the memory's content is now fully captured in a hook/skill/charter, remove it. If partially captured, update it to reference the new automation.

4. **Report what was converted:**
   ```
   **Memory-to-Automation Audit**

   | Memory File | Classification | Action Taken | Issue |
   |-------------|---------------|--------------|-------|
   | feedback_x.md | Hook | Created validate_x.py | #N |
   | project_y.md | Keep | No action | — |
   | ...         | ...           | ...          | ...   |
   ```

**Why:** Memory files accumulate rules and patterns that should be enforced automatically. If a memory says "always do X", that's a hook. If it says "follow these steps for Y", that's a skill. Leaving these as memories means they only work when the LLM happens to load them — hooks and skills are deterministic.

**Designated owner:** Aino Virtanen handles most conversions (hooks, charter, standards). The orchestrator spawns her with the audit list and she reports back when done.

## What remains manual

- User must approve merge sequence before any PR is merged
- Must-fix items require engineer action before merge
- Deferred issues need user decision on next-wave placement
- Final-wave merge to main requires explicit user approval
- `/wave-retro` must be run separately after wrapup completes
- Memory audit classifications are proposed — user can override keep/convert decisions

## Scope-Drop Reconciliation (added P3W4 retro 2026-05-05)

Before closing a wave, reconcile **declared scope vs delivered scope**. For each repo in `cross-repo-status.json` `wave_{N}_repos_in_scope`:

```bash
gh pr list --repo noorinalabs/{repo} --state merged --base "deployments/phase-{N}/wave-{M}" --json number --jq 'length'
```

If the count is **0**, the repo had declared work that did not ship. Resolve the drop EXPLICITLY — silent drops are not allowed.

**Two valid outcomes:**

1. **De-scoped during wave** — the work was correctly assessed as out-of-scope mid-wave. Move the repo from `wave_{N}_repos_in_scope` to a new `wave_{N}_repos_descoped_during_wave` array in `cross-repo-status.json` with a one-line reason field. Examples: theme misalignment surfaced after kickoff, dependency on next-wave work, planning error.

2. **Carry-forward to next wave** — the work is still real but slipped. File or update the carry-forward issues, label them with the next wave's label, and add references to `cross-repo-status.json` `wave_{N+1}_carry_forward` array.

**Why:** P3W4 declared `noorinalabs-isnad-ingest-platform` in scope but shipped 0 PRs to its wave branch. The drop was invisible at wrap-time because no check enforced reconciliation — the wave closed with a silent scope discrepancy that surfaced only at retro. Operationally, silent drops compound across waves: by W3-of-N, the declared scope drifts arbitrarily far from delivered, and planning-vs-execution accuracy becomes unmeasurable.

**Acceptance:** A wave-wrapup is not complete until every repo in `wave_{N}_repos_in_scope` has either ≥1 PR merged to its wave branch OR an explicit de-scope/carry-forward record. Run this check BEFORE the wave-merge ceremony.

## Implementer-Substitution Reconciliation (added P3W5 retro 2026-05-06)

Symmetric to § Scope-Drop Reconciliation, but for the inverted case: the declared implementer was replaced silently. Before closing a wave, reconcile **declared implementer vs actual PR author** for every PR merged to a wave branch.

```bash
# For each repo in scope, for each merged PR:
for repo in $(jq -r ".wave_{M}_repos_in_scope[]" "$REPO_ROOT/cross-repo-status.json"); do
  for pr in $(gh pr list --repo "noorinalabs/$repo" --state merged --base "deployments/phase-{N}/wave-{M}" --json number --jq '.[].number'); do
    actual=$(gh pr view $pr --repo "noorinalabs/$repo" --json author --jq '.author.login')
    branch=$(gh pr view $pr --repo "noorinalabs/$repo" --json headRefName --jq '.headRefName')
    # Compare actual against wave_{M}_scope.tier_*[].implementer or .tier_*[].assignee for that issue.
    # Branch prefix (e.g., "T.Mansour/...") is the cheap proxy when author is the github org bot.
  done
done
```

If the actual author (or branch-prefix initials) does not match the kickoff-declared implementer, the substitution must be recorded EXPLICITLY — silent swaps are not allowed.

**Required record:** add an entry to `wave_{N}_decisions.implementer_substitutions` in `cross-repo-status.json`:

```json
{
  "implementer_substitutions": [
    {
      "repo": "noorinalabs-data-acquisition",
      "issue": "data-acquisition#36",
      "declared": "Sofia Cardoso",
      "actual": "Tarek Mansour",
      "swapped_at": "2026-05-05T23:42:00Z",
      "rationale": "<one-line reason — e.g., declared implementer unavailable; reassigned by Pipeline Mgr Dilara>"
    }
  ]
}
```

**Why:** P3W5 declared Sofia Cardoso as the T1A #263 implementer for data-acquisition; the actual PR (data-acquisition#37) was authored by Tarek Mansour with no recorded swap rationale. Same shape as W4's ingest-platform silent-drop, just inverted (silent-substitution vs silent-zero-PR). Both are scope-drift with no audit trail. Operationally, silent substitutions compound the same way silent drops do: trust matrix updates apply to the wrong engineer (Sofia gets credit she didn't earn, Tarek's first wave PR is invisible at retro), and planning-vs-execution accuracy degrades.

**Acceptance:** A wave-wrapup is not complete until every PR with a declared-vs-actual mismatch has either an entry in `wave_{N}_decisions.implementer_substitutions` OR an explicit acknowledgment that the swap is benign (e.g., orchestrator-class spawn doing implementer-class work — already covered by other discipline). Run this check BEFORE the wave-merge ceremony, in the same pass as § Scope-Drop Reconciliation.
