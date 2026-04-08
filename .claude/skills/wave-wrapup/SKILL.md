---
name: wave-wrapup
description: Finalize a wave — PR review, merge sequencing, issue cleanup, worktree cleanup, and handoff to retro
args: team_name, Phase number, Wave number
---

Finalize a wave by reviewing all open PRs, merging in dependency order, closing resolved issues, and cleaning up. This is the **exit gate** before running `/wave-retro`.

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

### 8. Clean up worktrees

```bash
git worktree prune
git worktree list
```

Remove any worktrees created for this wave's PRs. Report what was cleaned.

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

### 11. Merge to main (final wave only)

If this is the final wave of the phase:

```bash
# Create PR from deployments branch to main
gh pr create --base main --head "deployments/phase{P}/wave-{M}" \
    --title "Phase {P} Wave {M} → main" \
    --body "Final wave merge. All PRs reviewed and merged to deployment branch."
```

**Do NOT merge to main without user approval.** This is a significant action that affects all downstream repos.

### 12. Memory-to-automation audit

Examine all memory files in the project memory directory for entries that describe behaviors, rules, or patterns that could be codified as a **hook**, **skill**, or **charter update** instead of remaining as soft memory.

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
