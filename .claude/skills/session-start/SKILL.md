---
name: session-start
description: "MANDATORY first action in every session — runs full startup protocol (worktree, team, handoff, ontology, annunaki, wave, charter)"
---

# Session Start Protocol

**This skill MUST be invoked as the FIRST action in every new session.** Do not respond to the user's message, do not read files, do not run any other tool — invoke `/session-start` first. The user's actual request is handled AFTER this completes.

> See [`.claude/team/lifecycle.md`](../../team/lifecycle.md) § Session Lifecycle for the canonical skill order and preconditions.

> Note: all repo paths in bash blocks below are rooted at `$REPO_ROOT` to avoid cwd drift when invoked from a worktree or child-repo subdirectory (#149). `$REPO_ROOT` is anchored to the **parent org repo** via the parent of `git rev-parse --git-common-dir` (not `--show-toplevel`, which resolves to a worktree) and verified against the parent markers `cross-repo-status.json` + `CLAUDE.md` (#533). Each bash block re-derives it, since Skill blocks run as independent shells. The blocks deliberately avoid process substitution and here-strings — those trip the permission engine's "cannot be statically analyzed" path (2026-06-23); preserve that property when editing them.

## Instructions

Execute all 7 steps below. Steps that are independent of each other SHOULD run in parallel. Present results in a single concise status table at the end.

### Step 0 — Worktree cleanup (parent + child repos)

Worktrees accumulate in the parent AND every child repo (#526 — ~33 stale child worktrees found uncaught on 2026-05-24). The block iterates all 8 repos with a **verify-merged-then-remove guard**: auto-remove only a worktree whose HEAD is fully merged into that repo's `origin/main`; FLAG (never auto-remove) anything locked, unmerged, or that fails to remove cleanly. "Fully merged" is decided by `.claude/lib/check_worktree_merged.py` (#1212, sibling of #1177; guarantee revised by owner decision 2026-08-02, PR #1213 round 3): ancestry is the fast path (the merge-commit majority); the fallback classifies `merged` iff **the branch's cumulative diff since its merge-base is fully present on `origin/main`** — a net-content test, not a per-commit one, searched over `origin/main`'s own history (not a snapshot compare against its current tip, which would decay as unrelated later commits keep touching the same files) — so a squash-merged (single- or multi-commit), rebase-merged, or cherry-picked branch is recognized as landed instead of being flagged `UNMERGED` forever just because its tip is never an ancestor. Verdicts are **order-independent**: the same commit set in a different order always classifies identically, because the primary test depends only on the branch's final tree state, never on the order of the commits that produced it (and the per-commit fallback test is order-independent too, for the separate reason that `git patch-id --stable` is invariant to the line-number shifts a commutative reorder causes) — a per-commit design (tried in an earlier round) could not provide this. A branch's own internal merge commit (round 4, PR #1213) is checked for unique conflict-resolution content (`git diff-tree --cc --no-commit-id`) that `git cherry` structurally cannot see, since `git cherry` never examines merge commits at all — this closes the one path where a merge's resolution could carry unlanded content past both other tests undetected. The disclosed residual is `git patch-id`'s own whitespace-normalization (a change indistinguishable from an already-landed one, character-for-character after whitespace is stripped, is treated as landed — the same reason `--verbatim` is deliberately not used, since it would misclassify the real #1156 fixture as unmerged); see the module docstring for the full guarantee and its two coordinated tests. The check is 100% local git plumbing (no `gh`/network dependency) and degrades to the pre-fix ancestry-only result on any internal git-command failure. **Step 0 never force-removes** (owner decision, round 3): the plain `git worktree remove` call either succeeds or the worktree is FLAGGED — the `--force` fallback that used to destroy uncommitted content on a dirty worktree is gone, so the worst a misclassification can now cost is a stale worktree directory (a commit or branch was never at risk either way, since `worktree remove` never deletes the branch ref).

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

# Pick up any merges/pushes to origin/main since last session (main#713) so the
# session never runs pre-fix hooks/skills off a stale checkout (the failure this
# session hit: opened 22 commits behind, ran the pre-#709 reader). The helper is
# fully guarded — it fast-forwards only a clean, strictly-behind main and refuses
# (no-op) on a diverged/ahead/dirty tree; it never forces or discards local work.
# Non-fatal: a refusal or error must never block session-start.
if [ -f "$REPO_ROOT/.claude/lib/sync_main.py" ]; then
  python3 "$REPO_ROOT/.claude/lib/sync_main.py" "$REPO_ROOT" || true
fi

# Refresh + staleness-guard the embedded child-repo checkouts (#832) — the
# sibling of the sync_main parent fast-forward above, for the children. The
# parent .gitignore's its child clones and they drift badly (during p6-wave-16
# user-service was parked on a phase-3 commit and isnad-graph sat ~207 commits
# behind origin/main — the root cause of #816 and of any agent that reads a
# stale child clone directly). Same safety stance as sync_main: a child that is
# clean and on main is fast-forwarded to origin/main (--ff-only, never force);
# a child that is dirty, diverged, or parked on an old feature branch is FLAGGED
# for a manual decision and left untouched — there is no force-discard path.
# Non-fatal: a flagged/refused child is a SAFE outcome and never blocks session-start.
if [ -f "$REPO_ROOT/.claude/lib/check_child_checkouts.py" ]; then
  python3 "$REPO_ROOT/.claude/lib/check_child_checkouts.py" "$REPO_ROOT" --refresh || true
fi

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
  # Capture porcelain output to a temp file (with a trailing blank line so the
  # last record is flushed) and feed the loop from it — see the note at `done`
  # below for why a temp file rather than `< <(...)` process substitution.
  _wtfile="$(mktemp)"
  { git -C "$repo" worktree list --porcelain; echo; } > "$_wtfile"
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
        elif [ -n "$head" ]; then
          # Delegate the merged-vs-unmerged call to the tested helper (#1212):
          # ancestry is the fast path, with a patch-id content-equivalence
          # fallback so a squash/rebase-merge/cherry-picked branch is not
          # flagged forever just because its tip is never an ancestor. A
          # `$(...)` command substitution assigning to a variable (not a
          # `<(...)` process substitution) stays statically analyzable —
          # same property the temp-file loop above preserves (#839).
          if [ -f "$REPO_ROOT/.claude/lib/check_worktree_merged.py" ]; then
            _mreason="$(python3 "$REPO_ROOT/.claude/lib/check_worktree_merged.py" "$repo" "$head" origin/main 2>/dev/null)"
            _mrc=$?
          else
            # Helper missing (very old checkout) — degrade to the legacy
            # ancestry-only test rather than failing closed.
            git -C "$repo" merge-base --is-ancestor "$head" origin/main 2>/dev/null
            _mrc=$?
            _mreason="ancestry-only (helper not found)"
          fi
          if [ "$_mrc" -eq 0 ]; then
            # Never force-remove (owner decision, PR #1213 round 3): a
            # worktree that does not remove cleanly (uncommitted/untracked
            # content in the way) is FLAGGED for a manual decision instead.
            # `git worktree remove` never deletes the branch ref either way,
            # so dropping the --force fallback means a misclassification by
            # the helper above can cost at most a stale worktree directory —
            # never a commit, never a branch, and (with --force gone) never
            # even uncommitted content either.
            if git -C "$repo" worktree remove "$wt" 2>/dev/null; then
              echo "removed merged worktree: $wt ($_mreason)"
            else
              FLAGGED+=("DIRTY  $repo :: $wt (merged but remove refused — uncommitted/untracked content; never force-removed)")
            fi
          else
            FLAGGED+=("UNMERGED  $repo :: $wt (HEAD ${head:-?}) [$_mreason]")
          fi
        else
          FLAGGED+=("UNMERGED  $repo :: $wt (HEAD ${head:-?})")
        fi
        wt="" ;;
    esac
    # NB: the loop is fed from a temp FILE (not a `< <(...)` process
    # substitution) so the whole Step-0 block stays statically analyzable by
    # the Claude Code permission engine — process substitution trips the
    # "shell syntax that cannot be statically analyzed" path and forces a
    # prompt regardless of the allowlist (main, 2026-06-23). A file redirect
    # is analyzable AND keeps the loop in the current shell, so the FLAGGED
    # array accumulation below survives past `done` (a `| while` pipe would
    # run the body in a subshell and silently drop it).
  done < "$_wtfile"
  rm -f "$_wtfile"
done

echo "--- remaining worktrees (parent + children) ---"
for repo in "${REPOS[@]}"; do git -C "$repo" worktree list; done

if [ "${#FLAGGED[@]}" -gt 0 ]; then
  echo "--- FLAGGED for manual decision (NOT removed) ---"
  printf '%s\n' "${FLAGGED[@]}"
fi
```

Report merged-worktree removals and surface the FLAGGED list (locked + unmerged) for a manual call — never force-remove a FLAGGED worktree without explicit confirmation. Also report the `check_child_checkouts.py` result (#832): children fast-forwarded vs FLAGGED (dirty/diverged/feature-branch — left untouched; a child many commits behind `origin/main` is the #816 stale-config root cause).

### Step 1 — Team orientation

The current harness has **no `TeamCreate`/`TeamDelete` tools** (2026-06-16) — the session runs on a **single implicit team**; nothing to create, tear down, or go stale. Spawning is via the **`Agent` tool** with **no `team_name`** (deprecated and ignored; the `validate_no_team_name` hook blocks a spawn carrying one — #1375); the orchestrator is the sole spawner (spawned agents cannot spawn — charter `agents.md` § Single-Leader Constraint). Report "Single implicit team (no create/delete tools in this harness)" and move on.

### Step 2 — Handoff check

Read the session handoff from in-repo project memory (#732 — version-controlled `.claude/memory/`, not the user-space auto-memory path). This is the ONLY read of its contents — the SessionStart hook prints just an exists-pointer (#962):

```
Read: .claude/memory/session_handoff.md
```

If it exists, summarize in 2-3 sentences: what was done last session, what's next, current branch / open PRs / issues, any user notes. If not, note "No handoff from previous session."

### Step 2.5 — Memory index is two-tier — load sections on demand (#1016)

The in-repo memory index `.claude/memory/MEMORY.md` is a **two-tier** index (#1016). The always-injected file (imported by CLAUDE.md via `@.claude/memory/MEMORY.md`) is a tiny **table of contents** — section names + note counts + a pointer to each section's detail file (~400 tokens, replacing the old ~5.7K-token flat list). The per-note one-liners live in `.claude/memory/section_<slug>.md` files that are **NOT** auto-injected (the flat index injected all ~99 note lines every turn, which the split exists to avoid).

- **Default: load only the ToC.** Do NOT read every `section_*.md` at session start — that re-injects exactly the full index the two-tier split removed. The ToC alone is enough to orient; it is already in context via the CLAUDE.md import.
- **Load one section on demand.** When the task at hand maps to a section (a PR review → *Review / PR / merge mechanics*; spawning an implementer → *Spawn / delegation / agent coordination*; a deploy/data question → *Project state*), `Read .claude/memory/section_<slug>.md` for its one-liners, then the specific note file it points to.
- **Re-tier maintenance (keep the split from decaying).** The memory-recording flow still appends new one-liners; if any land in `MEMORY.md` **outside** the ToC table (flat `- [ ]` rows), fold each into the matching `section_<slug>.md`, bump that section's ToC count, and leave `MEMORY.md` as ToC-only. **Never delete a note — only relocate it.** `memory_budget.py` counts note rows across the section files, so a stray row still counts against budget until folded.

### Step 3 — Ontology freshness (semantic overlay + structural index)

Two independent layers, two checks (#820/C×T2, #862):

**3a. Semantic overlay** — ask the shared reader for the dirty count. **Do not read `checksums.json` by hand (#1142)** — the predicate is `last_tracked != last_resolved`, and every way of getting that read wrong (a field name that is not in the schema, the wrong nesting level) returns a plausible `0`, which is also the healthy value. Two consecutive sessions reported a wrong `0` that way.

```bash
REPO_ROOT="$(cd "$(git rev-parse --git-common-dir 2>/dev/null)/.." 2>/dev/null && pwd)"
[ -f "$REPO_ROOT/cross-repo-status.json" ] || REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
python3 "$REPO_ROOT/.claude/lib/checksums_io.py" status
```

Interpret the exit code, not the vibe of the output:

| Exit | Meaning | Action |
|---|---|---|
| 0 | clean | Report "Semantic overlay: current" |
| 1 | dirty and/or malformed entries | Run `/ontology-rebuild`, process them, commit the result |
| 3 | ledger missing/unparseable | Report it as a problem — this is **not** an empty work list |

A **malformed** entry (unrecognized shape — missing `last_tracked`, a `null` hash) counts separately and blocks "clean" deliberately: unknown state is not resolved state. `/ontology-rebuild` step 1 documents the repair.

**3b. Structural index** — regenerate the generated index from the current source tree. It is a gitignored build product (main#939 — never committed; nothing to compare or commit), so just rebuild it locally; the aggregator refreshes every in-scope repo's index before rolling up:

```bash
# Re-anchor REPO_ROOT to the parent (independent shell block — see Step 0 / #533).
REPO_ROOT="$(cd "$(git rev-parse --git-common-dir 2>/dev/null)/.." 2>/dev/null && pwd)"
[ -f "$REPO_ROOT/cross-repo-status.json" ] || REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"

# Rebuild the structural layer from source: the aggregator regenerates each in-scope
# repo's per-repo index (main + any cloned children) and writes the cross-repo graph.
# These are gitignored build products (main#939) — no add, no commit.
if PYTHONPATH="$REPO_ROOT/.claude/lib" python3 -m ontology_gen.aggregate "$REPO_ROOT" 2>&1; then
  echo "Structural index: regenerated (local build product — not committed, main#939)."
else
  echo "WARN: structural index regeneration failed — librarian lookups may be stale until re-run."
fi
```

**Non-fatal:** a generator failure MUST NOT block session-start — report it and move on; the next run rebuilds it.

### Step 4 — Annunaki error check (count-only, #962)

Report the genuine-error count in ONE line, via the shared trace-filtering reader (#625 — raw line counts overcount on historical mixed logs). A missing log prints `0` (monitoring is passive):

```bash
REPO_ROOT="$(cd "$(git rev-parse --git-common-dir 2>/dev/null)/.." 2>/dev/null && pwd)"
[ -f "$REPO_ROOT/cross-repo-status.json" ] || REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
python3 "$REPO_ROOT/.claude/lib/annunaki_parse.py" "$REPO_ROOT/.claude/annunaki/errors.jsonl" --count
```

Report `Annunaki: N genuine error(s) logged (count-only)`. Do NOT auto-flag or run `/annunaki-attack` from this step — error logs are machine-local, and triage is batched: the attack runs **on demand and at `/wave-wrapup`** (#925/#962).

### Step 5 — Wave/phase orientation

Read the current project state:

```bash
# Re-anchor REPO_ROOT (each Skill bash block is an independent shell — the
# Step 0 value does not carry over). Same parent-anchor as Step 0 (#533):
# parent of --git-common-dir resolves the org root even from a worktree.
REPO_ROOT="$(cd "$(git rev-parse --git-common-dir 2>/dev/null)/.." 2>/dev/null && pwd)"
[ -f "$REPO_ROOT/cross-repo-status.json" ] || REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
# Read a COMPACT current-wave/phase projection, NOT the whole file. The status
# file is a flat dict of ~500 keys accreted over every wave (>200KB / ~53K
# tokens); `cat`-ing it whole was the single biggest guaranteed per-session token
# cost (#987 — bigger than CLAUDE.md + MEMORY.md + this skill combined). The
# digest keeps the lifecycle pointers + current/next-wave + current-phase keys +
# open blockers (a few KB — ~96% smaller), dropping 24 waves of history. Falls back to `cat` only if
# the helper is missing, matching the non-fatal stance of the other Step blocks.
if [ -f "$REPO_ROOT/.claude/lib/wave_status.py" ]; then
  python3 "$REPO_ROOT/.claude/lib/wave_status.py" digest --status "$REPO_ROOT/cross-repo-status.json" \
    || cat "$REPO_ROOT/cross-repo-status.json"
else
  cat "$REPO_ROOT/cross-repo-status.json"
fi
gh issue list --repo noorinalabs/noorinalabs-main --state open --limit 10 --json number,title,labels
```

Report: active wave/phase, staleness of `cross-repo-status.json` (from `last_updated`), open issue count and blockers, open PRs across repos. The Step-5 read is now the compact `wave_status.py digest` projection (#987), not the full file — if you need a historical wave's keys, read `cross-repo-status.json` directly. On unexpected board-vs-issue gaps (wave-labeled issues missing from project 2, or Wave-field out of sync with the canonical `wave-{X}` / grandfathered `p{N}-wave-{M}` labels, #810), invoke `/board-audit` (labels are canonical, the Wave field is a derived projection — main#199).

### Step 5a — Red default-branch workflow verdict (scheduled sweep, #962)

The 8-repo sweep + failed-log classification (P3W14 retro #2 — a red GHCR publish sat undetected ~12 days; base-image classifier main#647) no longer runs per-session. It runs in the scheduled **`red-sweep.yml`** workflow (every 6h + manual dispatch), which persists a JSON verdict to the lightweight ref `refs/meta/red-sweep`. Step 5a is ONE cheap read + staleness guard:

```bash
REPO_ROOT="$(cd "$(git rev-parse --git-common-dir 2>/dev/null)/.." 2>/dev/null && pwd)"
[ -f "$REPO_ROOT/cross-repo-status.json" ] || REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
# One contents-API call + 24h staleness guard. Always exits 0 (informational).
python3 "$REPO_ROOT/.claude/lib/red_sweep.py" check
```

The helper prints exactly one of:

- **All-green line** (with the verdict's `checked_at`) — no action.
- **RED run lines** (`repo :: workflow :: conclusion :: class :: url`) — stop-and-investigate: a red publish/deploy on a default branch means artifact consumers (staging, downstream pulls) are silently running stale or broken bits. A run tagged `base-image-drift` failed on a base-image-CVE signal (trivy/grype/apk/openssl-class) — fix-forward the base image, do not chase the wave diff (main#647).
- **WARNING** when the verdict is missing or older than 24h — report it verbatim; the sweep is stale, red runs are UNKNOWN. Refresh with `gh workflow run red-sweep.yml --repo noorinalabs/noorinalabs-main`. NEVER treat a missing/stale verdict as green — the same degradation stance the in-session classifier had. Repos listed in the verdict's `errors` are likewise UNKNOWN, not green.

### Step 5b — Wave-merged-but-unwrapped nudge (P5W5 retro #1 / #730)

Detects a wave whose PRs merged to main but was never formally wrapped (P5W5: all 45 PRs merged days before `/wave-wrapup`; the wrap markers stayed null and post-wave audits never ran). Signal: `wave_{M}_active` AND no wrapup marker AND 0 open wave PRs — scoped to `current_wave` only (wave keys are NOT phase-namespaced, #683; an any-wave scan false-fires on prior-phase ghosts). Non-fatal, degrades to a benign verdict on missing keys / failed `gh`.

```bash
REPO_ROOT="$(cd "$(git rev-parse --git-common-dir 2>/dev/null)/.." 2>/dev/null && pwd)"
[ -f "$REPO_ROOT/cross-repo-status.json" ] || REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
# Always exits 0 (informational nudge, not a gate). Prints a line beginning
# "NUDGE:" only when the wave is merged-but-unwrapped (or active+unwrapped with
# an undetermined open-PR count); otherwise a one-line in-flight/ok status.
if [ -f "$REPO_ROOT/.claude/lib/wave_unwrapped.py" ]; then
  python3 "$REPO_ROOT/.claude/lib/wave_unwrapped.py" check \
    --status "$REPO_ROOT/cross-repo-status.json" || true
fi
```

Surface an `unwrapped` verdict (or the softer `unwrapped_unverified`) prominently as **"wave merged but unwrapped — run `/wave-wrapup`"**. `in_flight` is a normal active wave: no nudge.

### Step 5c — Wave-branch reachability / merge-model check (main#801)

Surfaces mid-wave any wave-branch commit not reachable from `origin/main`, classified against the wave's declared merge model — so model-mixing or stranding surfaces within hours instead of only at the `/wave-wrapup` Step 11.5 gate (origin: P6W1 mixed models stranded 5 deliverables off main; charter `pull-requests.md` § One Merge Model Per Wave). Model-aware: `direct-to-main` with wave-branch commits = **VIOLATION**; `wave-branch` ahead with an open wave→main PR = OK, ahead with no PR = **ADVISORY**; no declared model degrades to advisory-only. Non-fatal.

```bash
REPO_ROOT="$(cd "$(git rev-parse --git-common-dir 2>/dev/null)/.." 2>/dev/null && pwd)"
[ -f "$REPO_ROOT/cross-repo-status.json" ] || REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
# Derive the live phase/wave from the canonical lifecycle pointers (NOT a max
# over wave numbers — retained prior-phase scopes would mis-select; cf. #712).
PHASE=$(jq -r '.current_phase // empty' "$REPO_ROOT/cross-repo-status.json" 2>/dev/null)
WAVE=$(jq -r '(.current_wave // "" | ltrimstr("wave-"))' "$REPO_ROOT/cross-repo-status.json" 2>/dev/null)
if [ -n "$PHASE" ] && [ -n "$WAVE" ] && [ -f "$REPO_ROOT/.claude/lib/wave_merge_model.py" ]; then
  # Helper prints the per-repo report; exit 1 ONLY on a model VIOLATION.
  python3 "$REPO_ROOT/.claude/lib/wave_merge_model.py" reachability "$PHASE" "$WAVE" \
    || echo "⚠ merge-model VIOLATION above — a wave branch carries commits the declared model forbids (#801). Investigate before merging more."
else
  echo "reachability check skipped — current_phase/current_wave not set or helper absent."
fi
```

Report a **VIOLATION** prominently (stop-and-investigate); **ADVISORY** lines are stranding-risk reminders (surface, don't block); **OK** needs no action.

### Step 6 — Charter freshness check

```bash
# Re-anchor REPO_ROOT to the parent (independent shell block — see Step 0 / #533).
REPO_ROOT="$(cd "$(git rev-parse --git-common-dir 2>/dev/null)/.." 2>/dev/null && pwd)"
[ -f "$REPO_ROOT/cross-repo-status.json" ] || REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
tail -40 "$REPO_ROOT/.claude/team/feedback_log.md"
```

Check for unapplied retro proposals, new hooks/skills not yet documented in the charter, and pending fire/hire actions. Report findings or "Charter is current."

## Output format

After all steps complete, present a single status block:

```
**Session Start — Complete**

| Step | Status |
|------|--------|
| 0. Worktree | {clean / N stale removed} |
| 0b. Child checkouts | {N fast-forwarded / M flagged (dirty/diverged/feature-branch) / all current} |
| 1. Team | {single implicit team} |
| 2. Handoff | {summary} |
| 3. Ontology | Semantic: {N dirty resolved / current}; Structural: {regenerated / regen-failed} |
| 4. Annunaki | {N genuine errors (count-only)} |
| 5. Wave | {active wave, stale?, issues} |
| 5a. Red default-branch verdict | {all green as of T / N red (M base-image-drift) / WARNING stale-missing} |
| 5b. Wave wrap state | {wave merged but unwrapped — run /wave-wrapup / in flight / wrapped} |
| 5c. Wave reachability | {OK / N advisory (stranding risk) / VIOLATION (merge-model mixing) / skipped} |
| 6. Charter | {current / proposals pending} |

{Then address the user's actual message/request}
```

## What this skill does NOT do

- It does not begin any implementation work
- It does not create issues or PRs
- It does not modify the charter or team roster
- It only establishes situational awareness so the session starts informed
