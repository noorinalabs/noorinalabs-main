---
name: session-start
description: "MANDATORY first action in every session — runs full startup protocol (worktree, team, handoff, ontology, annunaki, wave, charter)"
---

# Session Start Protocol

**This skill MUST be invoked as the FIRST action in every new session.** Do not respond to the user's message, do not read files, do not run any other tool — invoke `/session-start` first. The user's actual request is handled AFTER this completes.

> See [`.claude/team/lifecycle.md`](../../team/lifecycle.md) § Session Lifecycle for the canonical skill order and preconditions.

> Note: all repo paths in bash blocks below are rooted at `$REPO_ROOT` to avoid cwd drift when the skill is invoked from a worktree or child-repo subdirectory (#149). `$REPO_ROOT` is anchored to the **parent org repo** deterministically via the parent of `git rev-parse --git-common-dir` (not `--show-toplevel`, which resolves to a worktree if run from one) and verified against the parent marker `cross-repo-status.json` + `CLAUDE.md` (#533). Each bash block re-derives it, since Skill blocks run as independent shells.

## Instructions

Execute all 7 steps below. Steps that are independent of each other SHOULD run in parallel. Present results in a single concise status table at the end.

### Step 0 — Worktree cleanup (parent + child repos)

Worktrees accumulate in BOTH the parent repo and every child repo (under
`<child>/.claude/worktrees/`, `<child>/.worktrees/`, and sometimes `/tmp/`).
Prior to #526, Step 0 only cleaned the parent — on 2026-05-24 ~33 stale
child-repo worktrees were found uncaught. The block below iterates the parent
and all 7 child repos, applying a **verify-merged-then-remove guard**:

- **Auto-remove** a worktree only when its HEAD is an ancestor of that repo's
  `origin/main` (i.e. the branch is fully merged). Safe to drop.
- **FLAG (list, do not remove)** any worktree that is NOT verified-merged
  (work in flight, superseded, or closed-issue cases) and any **locked**
  worktree (e.g. the `/tmp/hotfix-user-service` lock case). Surface these for
  a manual decision — never auto-remove unmerged work.

```bash
# Anchor REPO_ROOT to the PARENT org repo deterministically (#533). Using a
# bare `git rev-parse --show-toplevel` resolves to a WORKTREE if /session-start
# is ever invoked from one, which silently breaks child-repo discovery below
# (the `$REPO_ROOT/$child/.git` probes find nothing). --git-common-dir points
# at the MAIN repo's `.git` even from a linked worktree, so its parent is the
# real org root in both the parent-checkout and run-from-worktree cases. We
# then verify the parent marker (cross-repo-status.json + CLAUDE.md) and warn
# loudly rather than silently skip children if it isn't found.
resolve_repo_root() {
  local common_dir candidate
  common_dir="$(git rev-parse --git-common-dir 2>/dev/null)" || common_dir=""
  if [ -n "$common_dir" ]; then
    candidate="$(cd "$common_dir/.." 2>/dev/null && pwd)"
  fi
  if [ -z "$candidate" ]; then
    candidate="$(git rev-parse --show-toplevel 2>/dev/null)"
  fi
  if [ -n "$candidate" ] && [ -f "$candidate/cross-repo-status.json" ] && [ -f "$candidate/CLAUDE.md" ]; then
    printf '%s\n' "$candidate"; return 0
  fi
  printf 'WARN: parent-repo marker not found under %s — child-repo discovery may be incomplete. ' "${candidate:-<unresolved>}" >&2
  printf 'Run /session-start from the parent main checkout (its mandated invocation path).\n' >&2
  printf '%s\n' "${candidate:-$(pwd)}"; return 1
}
REPO_ROOT="$(resolve_repo_root)"

# Parent repo + the 7 canonical child repos (CLAUDE.md Repository Map).
REPOS=("$REPO_ROOT")
for child in \
  noorinalabs-isnad-graph \
  noorinalabs-user-service \
  noorinalabs-deploy \
  noorinalabs-design-system \
  noorinalabs-data-acquisition \
  noorinalabs-isnad-ingest-platform \
  noorinalabs-landing-page; do
  [ -d "$REPO_ROOT/$child/.git" ] && REPOS+=("$REPO_ROOT/$child")
done

FLAGGED=()
for repo in "${REPOS[@]}"; do
  git -C "$repo" worktree prune
  # Refresh remote tip so the merged-ancestor test is accurate.
  git -C "$repo" fetch --quiet origin main 2>/dev/null || true
  main_repo="$(git -C "$repo" rev-parse --show-toplevel)"

  # Walk worktrees in porcelain form. Records are blank-line separated;
  # fields we care about: worktree <path>, HEAD <sha>, locked [<reason>].
  wt="" head="" locked=0
  while IFS= read -r line; do
    case "$line" in
      "worktree "*) wt="${line#worktree }"; head=""; locked=0 ;;
      "HEAD "*)     head="${line#HEAD }" ;;
      "locked"*)    locked=1 ;;
      "")  # end of a record — evaluate it
        [ -z "$wt" ] && continue
        if [ "$wt" = "$main_repo" ]; then wt=""; continue; fi  # skip main checkout
        if [ "$locked" -eq 1 ]; then
          FLAGGED+=("LOCKED  $repo :: $wt")
        elif [ -n "$head" ] && git -C "$repo" merge-base --is-ancestor "$head" origin/main 2>/dev/null; then
          echo "removing merged worktree: $wt"
          git -C "$repo" worktree remove "$wt" 2>/dev/null \
            || git -C "$repo" worktree remove --force "$wt" 2>/dev/null \
            || FLAGGED+=("REMOVE-FAILED  $repo :: $wt")
        else
          FLAGGED+=("UNMERGED  $repo :: $wt (HEAD ${head:-?})")
        fi
        wt="" ;;
    esac
  done < <(git -C "$repo" worktree list --porcelain; echo)
done

echo "--- remaining worktrees (parent + children) ---"
for repo in "${REPOS[@]}"; do git -C "$repo" worktree list; done

if [ "${#FLAGGED[@]}" -gt 0 ]; then
  echo "--- FLAGGED for manual decision (NOT removed) ---"
  printf '%s\n' "${FLAGGED[@]}"
fi
```

Report how many merged worktrees were auto-removed and surface the FLAGGED
list (locked + unmerged) to the user for a manual call. Do not force-remove a
FLAGGED worktree without explicit confirmation.

### Step 1 — Team cleanup

Stale team state from prior sessions causes "does not exist" / "already leading" errors. Always start fresh:

1. Run `TeamDelete` (will succeed even if no team exists)
2. Run `TeamCreate` with `team_name: "noorinalabs"` and `description: "Org-level coordination team for noorinalabs-main"`

Never try to reuse an existing team. Never skip this step.

> **Single-leader constraint:** This `TeamCreate` call establishes THE session team. Additional `TeamCreate` calls in this session will fail with "Already leading team." All managers and implementers spawned during the session — regardless of which repo they work on — join this single `noorinalabs` team. See charter `agents.md` § Single-Leader Constraint for the delegation pattern (team lead is sole `Agent`-tool caller; managers `SendMessage` the team lead to request implementer spawns).

### Step 2 — Handoff check

Read the session handoff file from project memory:

```
Read: ~/.claude/projects/-home-parameterization-code-noorinalabs-main/memory/session_handoff.md
```

If it exists, extract:
- What was done last session
- What's next
- Current branch, open PRs, open issues
- Any user notes

Summarize in 2-3 sentences. If the file doesn't exist, note "No handoff from previous session."

### Step 3 — Ontology rebuild

Run `/ontology-rebuild` to resolve any dirty files from the previous session.

- If 0 dirty files, report "Ontology is current" and move on
- If dirty files exist, process them and commit the result
- This ensures the ontology reflects all changes before any new work begins

### Step 4 — Annunaki error check

Run `/annunaki` to check the error monitor.

- Report: hook active/inactive, error count, any new errors since last session
- If 5+ unprocessed errors, flag for `/annunaki-attack`
- If 0 errors or all are resolved PreToolUse blocks, report "No action needed"

### Step 5 — Wave/phase orientation

Read the current project state:

```bash
# Re-anchor REPO_ROOT (each Skill bash block is an independent shell — the
# Step 0 value does not carry over). Same parent-anchor as Step 0 (#533):
# parent of --git-common-dir resolves the org root even from a worktree.
REPO_ROOT="$(cd "$(git rev-parse --git-common-dir 2>/dev/null)/.." 2>/dev/null && pwd)"
[ -f "$REPO_ROOT/cross-repo-status.json" ] || REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
cat "$REPO_ROOT/cross-repo-status.json"
gh issue list --repo noorinalabs/noorinalabs-main --state open --limit 10 --json number,title,labels
```

Report:
- Active wave and phase
- Whether `cross-repo-status.json` is stale (check `last_updated` fields)
- Open issue count and any blockers
- Open PRs across repos

If the report surfaces unexpected gaps between board view and open-issue counts (e.g., wave-labeled issues missing from project 2, or Wave-field values out of sync with `p{N}-wave-{M}` labels), invoke `/board-audit` to detect and (with confirmation) repair the drift. Per main#199, labels are canonical and the project's Wave field is a derived projection synced by `/board-audit`.

### Step 5a — Red default-branch workflow detection (P3W14 retro Proposed Change #2)

Surface any **publish/deploy/release workflow whose latest run on the repo's default branch FAILED**, across all org repos. *Rationale:* the GHCR frontend publish (isnad-graph commit 5804476) sat RED on `main` for ~12 days undetected — silently breaking every staging deploy at the frontend-pull step — because nothing surfaced a red default-branch publish at session start.

For each org repo, list the latest default-branch run of each workflow and flag any whose conclusion is `failure`/`timed_out`/`cancelled`, filtered to publish/deploy/release-class workflows (these are the ones whose redness silently rots — a red lint run is loud at PR time; a red publish on `main` is not):

```bash
REPO_ROOT="$(cd "$(git rev-parse --git-common-dir 2>/dev/null)/.." 2>/dev/null && pwd)"
[ -f "$REPO_ROOT/cross-repo-status.json" ] || REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
# Primary: the most-recent `wave_<N>_repos_in_scope` array (the canonical org repo set;
# there is no top-level `.repos` key). Falls through to the hardcoded list if the file is
# missing/unparseable or has no such key.
REPOS=$(jq -r '
  [to_entries[]
   | select(.key | test("^wave_[0-9]+_repos_in_scope$"))
   | {n: (.key | capture("^wave_(?<n>[0-9]+)_repos_in_scope$").n | tonumber), v: .value}]
  | max_by(.n) | .v[]? // empty
' "$REPO_ROOT/cross-repo-status.json" 2>/dev/null)
[ -n "$REPOS" ] || REPOS="noorinalabs-main noorinalabs-isnad-graph noorinalabs-user-service noorinalabs-deploy noorinalabs-design-system noorinalabs-data-acquisition noorinalabs-isnad-ingest-platform noorinalabs-landing-page"
RED=()
for repo in $REPOS; do
  branch=$(gh api "repos/noorinalabs/$repo" --jq '.default_branch' 2>/dev/null || echo main)
  # Latest run per workflow on the default branch; keep only publish/deploy/release-class names with a non-success conclusion.
  while IFS=$'\t' read -r name conclusion url; do
    case "$conclusion" in
      failure|timed_out|cancelled|startup_failure)
        RED+=("$repo :: $name :: $conclusion :: $url") ;;
    esac
  done < <(
    gh api "repos/noorinalabs/$repo/actions/runs?branch=$branch&per_page=50" \
      --jq '[.workflow_runs[] | select((.name // .display_title) | test("publish|deploy|release|promote|ghcr|image";"i"))]
            | group_by(.workflow_id) | map(max_by(.run_started_at))
            | .[] | [(.name // .display_title), .conclusion, .html_url] | @tsv' 2>/dev/null
  )
done
if [ ${#RED[@]} -gt 0 ]; then
  printf 'RED default-branch publish/deploy run(s) — investigate before relying on staging:\n'
  printf '  %s\n' "${RED[@]}"
else
  echo "All publish/deploy/release workflows green on default branches."
fi
```

Report any red runs prominently — a red publish/deploy on a default branch is a stop-and-investigate signal, not background noise: it usually means the artifact consumers (staging, downstream pulls) are silently running stale or broken bits. If `gh api` calls fail (auth/rate-limit), say so rather than reporting a false all-green.

### Step 6 — Charter freshness check

Read the tail of the feedback log:

```bash
# Re-anchor REPO_ROOT to the parent (independent shell block — see Step 0 / #533).
REPO_ROOT="$(cd "$(git rev-parse --git-common-dir 2>/dev/null)/.." 2>/dev/null && pwd)"
[ -f "$REPO_ROOT/cross-repo-status.json" ] || REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
tail -40 "$REPO_ROOT/.claude/team/feedback_log.md"
```

Check for:
- Unapplied retro proposals (action items without corresponding changes)
- New hooks or skills introduced since the last charter update
- Any pending fire/hire actions

Report findings or "Charter is current."

## Output format

After all steps complete, present a single status block:

```
**Session Start — Complete**

| Step | Status |
|------|--------|
| 0. Worktree | {clean / N stale removed} |
| 1. Team | {created fresh / error} |
| 2. Handoff | {summary} |
| 3. Ontology | {N dirty resolved / current} |
| 4. Annunaki | {N errors, action needed? / clear} |
| 5. Wave | {active wave, stale?, issues} |
| 5a. Red default-branch runs | {N red publish/deploy runs / all green} |
| 6. Charter | {current / proposals pending} |

{Then address the user's actual message/request}
```

## What this skill does NOT do

- It does not begin any implementation work
- It does not create issues or PRs
- It does not modify the charter or team roster
- It only establishes situational awareness so the session starts informed
