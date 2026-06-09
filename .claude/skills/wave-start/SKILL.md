---
name: wave-start
description: Initialize a new wave — worktree cleanup, branch creation, label setup, status file update
args: team_name, Phase number, Wave number
---

Initialize infrastructure for a new wave. This is the **setup step** that creates the deployment branch and cleans up stale worktrees. For full wave planning with issue assignment and kickoff comments, use `/wave-kickoff` after this completes.

> See [`.claude/team/lifecycle.md`](../../team/lifecycle.md) § Wave Lifecycle for the canonical skill order and preconditions.

> Note: all repo paths in bash blocks below are rooted at `$REPO_ROOT` to avoid cwd drift when the skill is invoked from a worktree or child-repo subdirectory (#149).

## Instructions

### 1. Clean stale worktrees

Remove any leftover worktrees from previous waves:

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
git -C "$REPO_ROOT" worktree prune
git -C "$REPO_ROOT" worktree list
```

Report any worktrees that were pruned. If active worktrees remain, list them and confirm with the user before proceeding (they may belong to in-progress work).

### 2. Determine base branch

- **Wave 1 of a phase:** Base is `main`
- **Wave N (N > 1):** Base is `main`. Each wave merges to main at its own `/wave-wrapup` (see `/wave-wrapup` Step 11, every-wave merge — changed 2026-06-09), so the previous wave is already integrated. The previous-wave-branch (`deployments/phase-{P}/wave-{M-1}`) is **retained, not deleted**, but it is not the base — it serves only as a safety-net reference if a prior wrapup's merge was somehow skipped (the warning below fires and Step 3 bases off main regardless).

```bash
# Check if previous wave branch exists
git -C "$REPO_ROOT" ls-remote --heads origin "deployments/phase-{P}/wave-{M-1}"
```

If the previous wave branch exists but has not been merged to main, warn the user:

```
WARNING: Previous wave branch deployments/phase-{P}/wave-{M-1} has not been
merged to main. Starting from main instead. Ensure previous wave changes
are integrated before merging this wave.
```

### 3. Create the deployment branch

```bash
cd "$REPO_ROOT"
git fetch origin
git checkout main && git pull origin main
git checkout -b "deployments/phase-{P}/wave-{M}"
git push -u origin "deployments/phase-{P}/wave-{M}"
```

If the branch already exists on the remote:

```bash
cd "$REPO_ROOT"
git fetch origin "deployments/phase-{P}/wave-{M}"
git checkout "deployments/phase-{P}/wave-{M}"
git pull origin "deployments/phase-{P}/wave-{M}"
```

Report which case was followed.

### 4. Create wave label

```bash
# Check if label exists
gh label list --search "p{P}-wave-{M}" --json name

# Create if missing
gh label create "p{P}-wave-{M}" --description "Phase {P} Wave {M}" --color "8B5CF6"
```

Also ensure standard category labels exist:

```bash
for label in "tech-debt" "feature" "bug" "security" "infra" "process"; do
    gh label list --search "$label" --json name | grep -q "$label" || \
        gh label create "$label" --description "$label" --color "auto"
done
```

### 5. Update cross-repo status

Update `cross-repo-status.json` to reflect the new active wave:

```bash
# Read current status
cat "$REPO_ROOT/cross-repo-status.json"
```

Set the active wave fields for this repo. Commit directly to the wave branch:

```bash
cd "$REPO_ROOT"
git -c user.name="{Manager Name}" -c user.email="{manager email}" \
    add cross-repo-status.json && \
git -c user.name="{Manager Name}" -c user.email="{manager email}" \
    commit -m "ops: Set Wave {M} active in cross-repo-status.json"
git push origin "deployments/phase-{P}/wave-{M}"
```

### 6. Run mid-wave retro (if not Wave 1)

If this is not the first wave, run `/retro` to capture a health check from the previous wave before starting new work. This ensures carry-over items are surfaced.

### 7. Report

```
**Wave Initialized: Phase {P} Wave {M}**

- Branch: `deployments/phase-{P}/wave-{M}` ({created|already existed})
- Base: `{base_branch}`
- Label: `p{P}-wave-{M}` ({created|already existed})
- Stale worktrees pruned: {count}
- Status file: {updated|no changes needed}

Ready for `/wave-kickoff` to assign issues and post kickoff comments.
```

## Relationship to wave-kickoff

`/wave-start` handles infrastructure: branch, label, cleanup.
`/wave-kickoff` handles planning: issue assignment, kickoff comments, execution plan.

Typical flow: `/wave-start` first, then `/wave-kickoff`.

## What remains manual

- User confirms if active worktrees should be removed
- Previous wave merge status may require user decision
- The skill does not assign issues or post kickoff comments — use `/wave-kickoff` for that
