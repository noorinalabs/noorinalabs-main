---
name: wave-lifecycle
description: Deterministic wave-lifecycle core for noorina's cross-repo state — the single entry point over lifecycle.py that drives allocate → start → scope → kickoff → wrapup → retro, delegating to the owning modules (wave_seq / wave_merge_model / wave_status).
---

# wave-lifecycle

Drive one iteration ("wave") of cross-repo team work through its lifecycle:

    allocate → start → scope → kickoff → (work) → wrapup → retro

This skill is **deterministic-first**: every state mutation goes through
`.claude/lib/lifecycle.py`, a thin facade over noorina's **existing** cross-repo
state. Prompts only fill in the decisions a human must make (the wave theme, the
in-scope repo list, the merge model). Everything else is mechanical.

## Org-scale reality — this is NOT botfarm's single-repo lifecycle

botfarm's `lifecycle.py` owns a private single-repo `.claude/state.json`. **noorina
is org-scale / cross-repo**: wave state lives in the repo-root
`cross-repo-status.json` (a flat dict of ~400 keys accreted across every wave,
read on demand via `wave_status.py digest`, #987), and it was already driven by
three deterministic modules:

| Concern | Owning module | Keys it owns |
|---------|---------------|--------------|
| Wave-id allocation (monotonic, reservation-aware) | `wave_seq.py` | `global_wave_seq`, `wave_{W}_phase`, `wave_{W}_phase_ordinal` |
| One-merge-model-per-wave + mid-wave reachability | `wave_merge_model.py` | `wave_{W}_merge_model` |
| In-scope repos, merged-PR set, wave counters, digest | `wave_status.py` | `wave_{W}_final_pr_count`, `wave_{W}_changes_requested_cycles`, `wave_{W}_top_concentration_pct` |

`lifecycle.py` does **not** introduce a competing state file and does **not**
re-implement any of that. It is a **facade** that:

- **delegates** the transitions that already have deterministic code — `allocate`
  → `wave_seq`, `merge-model` / `reachability` → `wave_merge_model`, `counters` →
  `wave_status` (so the keyspace and the counter can never disagree); and
- **adds deterministic writes** for the transitions that until now lived only in
  the `/wave-*` skill prose — the `start` / `scope` / `kickoff` timestamp / `wrapup`
  / `retro` lifecycle **pointers** — routing every write through the same
  `upsert_status_keys` helper the modules above use, so the file's compact-inline
  shape is preserved and each rewrite is JSON-validated before AND after
  (main#332/#456).

**Wave ids are GLOBAL monotonic ids** (`wave_25`), not per-phase ordinals — phase
is a derived display attribute (`wave_seq.py`, main#804). `--status` defaults to
the repo-root `cross-repo-status.json`, resolved from the file's own location so
it is correct from any cwd or worktree.

## Relationship to the existing `wave-*` skills (additive, for now)

This PR is **additive foundation only** (main#1019, the epic). The 10 existing
`wave-*` / `phase-*` skills and the wave hooks are **unchanged** — nothing is
deleted or demoted here. In follow-up PRs (see the epic sequence) the
state-transition prose in `/wave-start`, `/wave-kickoff`, `/wave-wrapup` and
`/wave-retro` will be progressively **demoted to thin references** that call
`lifecycle.py` for the mechanical writes, keeping only the genuinely human-
decision and cross-repo-orchestration prose (branch creation across repos, issue
labelling, reviewer slates, PR merge sequencing). The canonical order,
preconditions and state effects remain documented in
[`.claude/team/lifecycle.md`](../../team/lifecycle.md) — that doc stays
authoritative for the ordering; this skill is the deterministic execution layer.

## Preconditions

- Run from anywhere in the repo; `lifecycle.py` resolves `cross-repo-status.json`
  from its own path.
- `cross-repo-status.json` is on `main`. When the orchestrator writes it while
  parked on `main`, the established recipe is the `gh api PUT /contents` commit
  under the TPM (Wanjiku) identity (`/wave-kickoff` Step 1a) — `lifecycle.py`
  writes the LOCAL file (exactly as `wave_seq`/`wave_merge_model`/`wave_status`
  already do); committing that change to `main` follows the same PUT-contents path
  the skills use today.

## Steps

### 1. Allocate the wave id (monotonic, never reused) — delegates to `wave_seq`

```bash
python3 .claude/lib/lifecycle.py wave peek                        # next id (no write)
python3 .claude/lib/lifecycle.py wave allocate --phase {P} --write
```

`allocate --write` advances `global_wave_seq` and stamps `wave_{W}_phase` +
`wave_{W}_phase_ordinal` (the "Phase P, Wave N" display). Reservation-aware: an id
reserved ahead of the counter (a `wave_{N}_meta_issue` written by `/wave-retro`
Step 9) is claimed, not skipped.

### 2. Start the wave

```bash
python3 .claude/lib/lifecycle.py wave start {W}
```

Sets `current_wave`, `wave_{W}_active=true`, `wave_{W}_started_at`.

### 3. Scope it (owner decision: which repos)

Decide the in-scope repo subset for this wave, then record it:

```bash
python3 .claude/lib/lifecycle.py wave scope {W} \
    --repos noorinalabs-isnad-graph,noorinalabs-user-service --phase {P}
```

Writes `wave_{W}_repos_in_scope` + `wave_{W}_scope_reconciled_at` (+ the display
`wave_{W}_phase`). The richer `wave_{W}_scope` block (theme/shape) and the
meta-issue reservation stay owned by `/wave-scope` — this facade writes only the
machine-readable subset that the kickoff pre-flight and `wave_status` read.

### 4. Kick off (owner decision: merge model) — merge model validated by `wave_merge_model`

A wave uses exactly ONE merge model for its whole life — `wave-branch` (per-issue
PRs base on `deployments/phase-{P}/wave-{W}`; one wave→main PR at wrapup) or
`direct-to-main` (every PR bases on `main`). Mixing strands work (main#801).

```bash
python3 .claude/lib/lifecycle.py wave kickoff {W} --merge-model wave-branch
```

Records `wave_{W}_kicked_off_at` (the #423 cross-window filter boundary), re-points
`current_wave`, and writes the validated `wave_{W}_merge_model`. Then create the
wave branch in every in-scope repo and spawn implementers/reviewers per the roster.

### 5. Mid-wave (on demand) — delegates to `wave_merge_model`

```bash
python3 .claude/lib/lifecycle.py reachability {P} {W}        # model-aware stranding check
```

For every in-scope repo it compares the wave branch against `main` and classifies
the gap against the declared model. A `direct-to-main` wave with commits on the
wave branch is a hard **violation** (exit 1); a `wave-branch` wave ahead with no
open wave→main PR is an **advisory** (it will strand unless wrapup opens the PR).

### 6. Wrap up

Merge ready PRs, close resolved issues, clean worktrees (the cross-repo
orchestration stays in `/wave-wrapup`). Compute + write the counters via the
authoritative owner, then close the lifecycle pointers:

```bash
python3 .claude/lib/lifecycle.py counters {P} {W} --write     # → wave_status (authoritative writer)
python3 .claude/lib/lifecycle.py wave wrapup {W}
```

`counters --write` upserts the three canonical counter keys (owned by
`wave_status`; `/wave-retro` Step 2.5 only **verifies** them). `wave wrapup` writes
only the lifecycle pointers — `wave_{W}_active=false`, `wave_{W}_completed_at`,
`last_completed_wave` — and deliberately writes **no** counter, so there is exactly
one counter writer.

### 7. Retro

```bash
python3 .claude/lib/lifecycle.py wave retro {W}
```

Stamps `wave_{W}_retro_completed_at` — the key `/wave-kickoff` Step 0a reads to
gate the NEXT wave (its `scope_reconciled_at` must post-date this). Trust-matrix
and feedback-log writes remain owned by `/wave-retro` (they are narrative
assessments, not lifecycle pointers). Do **not** apply charter/process changes
without owner approval.

## Inspecting state

```bash
python3 .claude/lib/lifecycle.py state show               # dump the full status file
python3 .claude/lib/lifecycle.py state digest             # current-wave/phase slice (→ wave_status)
python3 .claude/lib/lifecycle.py merge-model get {P} {W}
```

## Why determinism-first

The lifecycle is a state machine; encoding its transitions in code
(`lifecycle.py`) instead of prose means the keyspace, the counter and the pointers
can never disagree, every write preserves the file shape and is JSON-validated,
and re-running a step is idempotent. The skill is the thin human-decision layer on
top — and, uniquely for noorina, the facade **reuses** the org-scale modules that
already own cross-repo reconciliation rather than replacing them.
