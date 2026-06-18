---
name: wave-start
description: Initialize a new wave — worktree cleanup, branch creation, label setup, status file update
args: team_name, Phase number, Wave number
---

Initialize infrastructure for a new wave. This is the **setup step** that parks the orchestrator's checkout on fresh `main`, cleans up stale worktrees, and ensures the wave label. For full wave planning — including the `deployments/phase-{P}/wave-{M}` branch creation (now owned by `/wave-kickoff` Step 1) and issue assignment — use `/wave-kickoff` after this completes.

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

### 2. Park the orchestrator's checkout on fresh `main`

Get the orchestrator's `noorinalabs-main` checkout onto a clean, up-to-date `main` **before** any branch or status work. Without this, a wave can be run while the working tree sits on a stale, already-merged feature branch (the P4W6 #653 hazard): the kickoff-comment hook reads an out-of-date local `cross-repo-status.json`, and any local commit lands against a stale base.

This step **guards** rather than auto-discards — only the regenerable session churn may be set aside. If there is genuine uncommitted or unmerged work, it STOPs so the operator decides.

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"
git fetch origin main

# Paths that regenerate every session and may be safely stashed (NOT a reason to STOP):
#   .claude/annunaki/errors.jsonl, cross-repo-status.json, ontology/checksums.json
REGENERABLE='^(\.claude/annunaki/errors\.jsonl|cross-repo-status\.json|ontology/checksums\.json)$'

# Guard A — non-regenerable uncommitted changes → STOP (do NOT auto-discard).
# `cut -c4-` takes the path field of `git status --porcelain` (handles spaces/renames).
NON_REGEN_DIRTY=$(git status --porcelain | cut -c4- | grep -vE "$REGENERABLE" || true)
if [ -n "$NON_REGEN_DIRTY" ]; then
  echo "STOP: working tree has non-regenerable uncommitted changes:"
  echo "$NON_REGEN_DIRTY" | sed 's/^/  /'
  echo "Commit, stash, or discard them deliberately before /wave-start — this skill will not auto-discard."
  exit 1
fi

# Guard B — current branch is ahead of origin/main (unmerged local work) → STOP.
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
AHEAD=$(git rev-list --count origin/main..HEAD)
if [ "$AHEAD" -gt 0 ]; then
  echo "STOP: current branch '$CURRENT_BRANCH' is $AHEAD commit(s) ahead of origin/main (unmerged work)."
  echo "Land or set it aside before starting a wave — this skill will not auto-discard."
  exit 1
fi

# Safe to park: stash only the regenerable churn (recoverable via `git stash list`), then
# move to fresh main with a fast-forward-only pull (never a merge commit).
git stash push -- .claude/annunaki/errors.jsonl cross-repo-status.json ontology/checksums.json 2>/dev/null || true
git checkout main
git pull --ff-only origin main

# Assert: on a clean main before proceeding.
test "$(git rev-parse --abbrev-ref HEAD)" = "main" || { echo "STOP: not on main after checkout"; exit 1; }
test -z "$(git status --porcelain | cut -c4- | grep -vE "$REGENERABLE" || true)" \
  || { echo "STOP: main checkout is not clean after pull"; exit 1; }
echo "Parked on clean main @ $(git rev-parse --short HEAD)"
```

If either guard STOPs, surface the reason to the user and wait — do not work around it. (zsh note: the block above avoids bash-isms like associative arrays; it runs the same under zsh and bash.)

### 3. Determine base branch

- **Wave 1 of a phase:** Base is `main`
- **Wave N (N > 1):** Base is `main`. Each wave merges to main at its own `/wave-wrapup` (see `/wave-wrapup` Step 11, every-wave merge — changed 2026-06-09), so the previous wave is already integrated. The previous-wave-branch (`deployments/phase-{P}/wave-{M-1}`) is **retained, not deleted**, but it is not the base — it serves only as a safety-net reference if a prior wrapup's merge was somehow skipped (the warning below fires and the wave branch is still cut from `main` regardless — `/wave-kickoff` Step 1 always bases the ref on `origin/main` HEAD).

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

### 4. Wave branch creation — delegated to `/wave-kickoff`

`/wave-start` does **not** create the `deployments/phase-{P}/wave-{M}` branch locally. Branch creation for **every** repo in the wave's scope — including `noorinalabs-main` — is owned by `/wave-kickoff` Step 1, which cuts the ref via `gh api` POST `…/git/refs` from `origin/main` HEAD. That path is idempotent (race-safe `Reference already exists` handling) and needs no clean local checkout by design, so a local `git checkout -b` here is dead weight.

The old local `git checkout main && git pull && git checkout -b …` flow was the only step that left the checkout on a branch; its hygiene half now lives in § 2 (park on `main`), and its branch-create half is superseded by `/wave-kickoff` Step 1. Stay on `main` (per § 2) — you do not need to create or check out the wave branch in this skill.

### 5. Create wave label

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

### 5a. Wave-key per-phase reset (when a phase reuses a wave number)

At phase boundaries, bare `wave_{M}_*` keys from the prior phase's wave M remain in `cross-repo-status.json` under the same names (e.g. `wave_4_final_pr_count`, `wave_4_branches`, `wave_4_scope`). These stale values bleed into the new phase's wave M if not explicitly cleared. (Bare keys — NOT phase-prefixed `p{P}_wave_{M}_*` — are deliberate: the phase-prefix scheme was considered and rejected in main#611 because it would require a coordinated read-contract change across every wave skill. The fix is correct cleanup of the bare keys, not renaming them.)

**This step is fully mechanized** by `.claude/lib/wave_key_reset.py` (main#683). Do NOT hand-roll the detection or the key list in bash — three defects in the old inline version (a `current_phase`-based guard that could never fire for an intra-phase same-number reuse; a detection probe that looked for the wrong key names; and a hand-enumerated reset list that missed ≥10 keys including the dangerous `wave_{M}_branches`) are exactly what that helper exists to prevent.

**Detection signal:** the helper decides staleness from the **phase stamp carried inside the wave's own keys** — `wave_{M}_scope.phase` (written by `/wave-scope`) and the `phase-{X}` segment of `wave_{M}_branches.branch` (written by `/wave-kickoff`). It NEVER consults the global `current_phase` (which tracks the latest phase, not the phase that wrote the stale keys — the root cause of the old guard's blind spot). If any stamp differs from the phase `{P}` you are starting, the wave's keys are stale.

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
STATUS_FILE="$REPO_ROOT/cross-repo-status.json"

# Dry-run first — prints the verdict and the exact keys that would be reset:
python3 "$REPO_ROOT/.claude/lib/wave_key_reset.py" "$STATUS_FILE" {M} {P}

# Apply — removes every stale wave_{M}_* key (prefix-complete; no-op if not stale):
python3 "$REPO_ROOT/.claude/lib/wave_key_reset.py" "$STATUS_FILE" {M} {P} --apply
```

The `--apply` path REMOVES the stale keys (the main#611 bare-key overwrite convention — the new phase's `/wave-start` § 6 and `/wave-scope` then write fresh `wave_{M}_*` keys). It is a safe no-op when the wave's stamps already match `{P}` — i.e. the first wave of a phase, or `/wave-start` re-run within the same phase (idempotent). Removal reuses `upsert_status_keys.remove_top_level_key`, so the file's mixed compact-inline / pretty-indented shape is preserved and the rewrite is JSON-validated before AND after (no 500-line cosmetic diff).

This reset runs BEFORE the § 6 PUT-contents write so the only `wave_{M}_*` values left once the step completes are the active-state keys § 6 writes. When operating on the `main` copy via PUT-contents, run the helper against a local working copy of the fetched content and fold the result into the same § 6 payload to avoid a separate round-trip.

### 6. Update cross-repo status — PUT-contents on `main`

Set the active-wave fields for this repo in `cross-repo-status.json`. This is a **main-targeting** status write, so use the **`gh api` PUT-contents recipe** — the atomic, no-local-orphan pattern documented in `/wave-kickoff` Step 1a (added P3W6 retro, supersedes local-commit-then-push). Do **not** `git add/commit/push` the file from the local tree: a local commit here re-introduces the orphan / stale-tree hazard this issue (#653) closes, and the local `main` parked in § 2 races the remote after the PUT lands.

```bash
# Read current status (for reference / field-setting)
gh api repos/noorinalabs/noorinalabs-main/contents/cross-repo-status.json?ref=main \
  --jq '.content' | base64 -d
```

Recipe (see `/wave-kickoff` Step 1a for the full payload shape):

1. Fetch current `sha` + content via `gh api …/contents/cross-repo-status.json?ref=main`.
2. Set the active-wave fields for this repo via `jq`.
3. base64-encode the new content.
4. `gh api -X PUT repos/noorinalabs/noorinalabs-main/contents/cross-repo-status.json --input <payload>.json` with `message`, `content`, `sha` (current), `branch: "main"`, and `author`/`committer` set to the role running `/wave-start` (typically the TPM).
5. **Read-back-verify** the field landed on `main`: `gh api …/contents/cross-repo-status.json?ref=main --jq '.content' | base64 -d | jq …`.

### 7. Run mid-wave retro (if not Wave 1)

If this is not the first wave, run `/retro` to capture a health check from the previous wave before starting new work. This ensures carry-over items are surfaced.

### 8. Report

```
**Wave Initialized: Phase {P} Wave {M}**

- Checkout: parked on clean `main` @ `{short_sha}`
- Wave branch: `deployments/phase-{P}/wave-{M}` (created by `/wave-kickoff` Step 1, not here)
- Base: `{base_branch}`
- Label: `p{P}-wave-{M}` ({created|already existed})
- Stale worktrees pruned: {count}
- Status file: `cross-repo-status.json` updated on `main` via PUT-contents ({updated|no changes needed})

Ready for `/wave-kickoff` to create the wave branch in all scoped repos, assign issues, and post kickoff comments.
```

## Relationship to wave-kickoff

`/wave-start` handles local hygiene + setup: park the checkout on fresh `main` (§ 2), prune stale worktrees, ensure the wave label, and stamp the active-wave state onto `main` via PUT-contents.
`/wave-kickoff` handles branch creation (the `deployments/phase-{P}/wave-{M}` ref in every scoped repo, via `gh api`) and planning: issue assignment, kickoff comments, execution plan.

Typical flow: `/wave-start` first, then `/wave-kickoff`.

## What remains manual

- User confirms if active worktrees should be removed
- The § 2 park-on-`main` guard STOPs (does not auto-discard) on non-regenerable dirty state or unmerged local commits — the user resolves these before re-running
- Previous wave merge status may require user decision
- The skill does not create the wave branch, assign issues, or post kickoff comments — use `/wave-kickoff` for that
