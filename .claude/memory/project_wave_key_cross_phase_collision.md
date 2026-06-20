---
name: project_wave_key_cross_phase_collision
description: "cross-repo-status.json wave_{M}_* keys are NOT phase-namespaced, so a phase reusing a prior phase's wave number (e.g. P5W4 reuses P4W4's wave_4_*) collides; /wave-start §5a reset never fires for it (3 defects, main#683). Reset stale keys manually at /wave-scope."
metadata: 
  node_type: memory
  type: project
  originSessionId: b923c0f4-c87a-4bed-b4b8-91a79287509b
---

`cross-repo-status.json` keys are `wave_{M}_*` (bare wave number, NOT phase-namespaced). So when a phase reaches a wave number a **prior** phase already used, the keys collide: P5W4 reads/writes the same `wave_4_*` keys P4W4 wrote. P4 reached wave-7, so **P5W5/W6/W7 will collide too** — expect this every remaining P5 wave ≥4.

`/wave-start` **§5a** ("Wave-key per-phase reset") is supposed to clear the stale keys but **never fires** for this case — 3 verified defects (tracked **main#683**, tech-debt+process, boarded):
1. **Phase guard** `current_phase != {P}` is structurally false — `current_phase` is bumped to the new phase at that phase's W1 kickoff, so by W4 it already == {P}. It tracks the latest phase, not the phase that owns the stale keys.
2. **Detection key mismatch** — probes `wave_{M}_completed_at`/`_wrapped_up_at`, but `/wave-wrapup` actually writes `wave_{M}_wrapup_completed_at`.
3. **`RESET_KEYS` list incomplete** — misses ~10 keys P4 wrote (`wave_{M}_active`, `_branches`, `_carry_forward`, `_counter_corrections`, `_scope`, `_repos_in_scope`, `_meta_issue`, …). `_branches` is the dangerous one: a stale phase-4 branch ref misleads `/wave-kickoff` Step 1.
4. **(found P5W4 kickoff, latent)** `post_wave_kickoff_comment.py` `_kickoff_heading_re` matches `**Wave {M} Kickoff — Phase \d+**` (phase-agnostic) → a P5W4 issue carrying a P4W4 `Phase 4` kickoff comment would be falsely `skip_idempotent`. Didn't bite (no P5W4 issue was in P4W4). Fix = phase-specific regex. Same root cause.

**Kickoff-comment hook mechanics (P5W4):** `post_wave_kickoff_comment` is dispatched via `post_dispatcher.py` (_REGISTRY, Bash) — NOT a direct settings.json entry. It parses ONE literal `gh issue edit <num> --repo … --add-label "p{P}-wave-{M}"` per Bash **tool call**. A batched `for`-loop with `$num`/`$repo` shell variables defeats it (the hook sees unexpanded vars) → no post, no error. Fire one literal single-issue label-apply per tool call (re-applying an already-present label still fires it; idempotent). The comment posts async — don't race-verify immediately.

**Manual procedure (until main#683 lands):** at `/wave-scope {P} {M}`, reset all stale `wave_{M}_*` operational keys to null and write the new-phase `wave_{M}_scope` (include a `phase: {P}` discriminator), `wave_{M}_repos_in_scope`, `wave_{M}_scope_reconciled_at`. Leave `current_wave` alone (advanced at `/wave-kickoff` Step 1a). Done for P5W4 in commit 5cd5842.

**Editing the file safely:** it is fully pretty-printed; `json.dumps(d, indent=2, ensure_ascii=False)` is **byte-idempotent** on it — use plain Python load/modify/dump (validate with `json.loads` before write) for a clean minimal diff. The `upsert_top_level_key` text-helper **breaks on multi-line nested values** (e.g. nulling `wave_4_branches`) — avoid it for object/array-valued keys. Durable fix = phase-namespace the keys (`p{P}_wave_{M}_*` or nested `phases.{P}.waves.{M}`) per P5W3-retro process carry-forward #4. See [[feedback_canonical_source_via_git_show]] (origin > local for base).
