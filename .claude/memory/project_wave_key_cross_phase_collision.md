---
name: project_wave_key_cross_phase_collision
description: "RESOLVED (main#804, Design B): cross-repo-status.json wave_{M}_* keys are now a GLOBAL monotonic id (never resets per phase), so the P5W2↔P6W2 collision class is gone. Phase is a derived display field; /wave-start §5a reset retired + wave_key_reset.py deleted."
metadata: 
  node_type: memory
  type: project
  originSessionId: b923c0f4-c87a-4bed-b4b8-91a79287509b
---

**RESOLVED — main#804 (Design B, owner-directed 2026-06-21).** The durable fix landed: wave ids in `cross-repo-status.json` are now a **single global monotonic counter** (`global_wave_seq`), never reset per phase and never reused. P6's first *new* wave is `wave_16`, not `wave_1`. Two same-ordinal waves in different phases (the old P5W2 ↔ P6W2 collision) get DISTINCT keys by construction — the collision class cannot arise. **Phase is a derived display attribute** (`wave_{X}_phase` + `wave_{X}_phase_ordinal`), never part of the key. The `/wave-start` §5a per-phase reset is **retired** and `.claude/lib/wave_key_reset.py` is **deleted** — there is nothing to reset.

- **Allocator:** `.claude/lib/wave_seq.py` (`peek` / `allocate --phase P --write`), run at `/wave-scope` Step 0.0. Self-seeds above all historical per-phase numbers (`HISTORICAL_FLOOR = 15`) if `global_wave_seq` is absent. Writes via `upsert_status_keys.py` (shape-preserving, JSON-validated).
- **Migration = grandfather:** in-flight P6W1 (`wave_1_*`) / P6W2 (`wave_2_*`) keep their keys (an active wrapup is not disrupted by a rename); `global_wave_seq` seeded to 15 so the first new global wave is 16. Prior-phase graveyard keys (`wave_3_*`..`wave_7_*`) left in place — inert because no future wave is numbered ≤15; history is in git + phase docs.
- **`{M}` is the global id EVERYWHERE it already appears** (meta-issue title "Phase P Wave {M}", status keys, `p{P}-wave-{M}` label, `/wave-scope {P} {M}` arg). Phase ordinal is display-only, not woven into titles. The one arithmetic fix: "next wave" is no longer `{M}+1` (after grandfathered `wave_2` the next is `wave_16`) — `/wave-retro` Step 9 + `/wave-scope` next-label now read `wave_seq.py peek`.

**Deferred to follow-up (surfaced in the #804 PR):** the phase-agnostic `wave-{X}` / `wave-x`-placeholder LABEL rename. Labels (`p6-wave-2`) and branches (`deployments/phase-6/wave-2`) already carry the phase, so they do NOT collide — they were never the bug. The rename touches the live ProjectV2 Wave-field options + ~6 hooks + ~15 tests, warranting isolated review.

**Process note (this session):** the implementation was nearly lost to the shared-worktree collision (`.claude/worktrees/0728-ontology-graphify-spike` was cycled across 5 agents' branches; a peer `git checkout` wiped uncommitted edits). Recovered into a dedicated worktree. See [[feedback_cwd_collision_cross_spawn]] — commit/push fast, do not share a cwd. See also [[feedback_canonical_source_via_git_show]].
