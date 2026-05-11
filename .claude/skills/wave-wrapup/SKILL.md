---
name: wave-wrapup
description: Finalize a wave — PR review, merge sequencing, issue cleanup, worktree cleanup, and handoff to retro
args: team_name, Phase number, Wave number
---

Finalize a wave by reviewing all open PRs, merging in dependency order, closing resolved issues, and cleaning up. This is the **exit gate** before running `/wave-retro`.

> Note: all repo paths in bash blocks below are rooted at `$REPO_ROOT` to avoid cwd drift when the skill is invoked from a worktree or child-repo subdirectory (#149).

## Instructions

### 1. Inventory open PRs

List all PRs targeting the wave's deployment branch:

```bash
gh pr list --state open --base "deployments/phase{P}/wave-{M}" --json number,title,author,headRefName,reviews,isDraft,createdAt
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
4. Delete the remote tracking branch if the PR was merged: `git push origin --delete <branch>`

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

**Documentation:** {docs updated | docs need update | no doc changes}

**Worktrees cleaned:** {count}

**Next step:** Run `/wave-retro` for full retrospective with assessments and trust updates.
```

### 11. Merge to main per repo (final wave only)

If this is the final wave of the phase, every repo in `wave_{M}_repos_in_scope` has its OWN `deployments/phase-{P}/wave-{M}` branch (created by `/wave-kickoff` step 1) that needs its own PR to main. This is the symmetric counterpart of the multi-repo branch creation gap (main#238).

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
