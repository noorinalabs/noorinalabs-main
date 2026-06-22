---
name: project_p6w2_carryforward_trackers
description: P6W2 wrapped (15 PRs); next-wave carry-forward = exec trackers #819 (persona Option B) + #820 (ontology C×T2), W16 placeholder #821; live push/worktree constraints #816/#817.
metadata:
  type: project
---

P6W2 (global wave 15) wrapped 2026-06-22 — 15 PRs merged to main, staging success, 0 CR cycles. Carry-forward into the next wave:

**Architectural-decision execution trackers** (the spike→owner-decision→execution lineage that the open-issue list alone doesn't convey):
- **#819** — Execute **persona-model Option B**: governed slim cards + self-improving cards (§4a) + mechanical trust scoring (§4b). Decided by owner from spike **#727** (`.claude/team/spikes/p6w2-persona-model-evaluation.md`). First mechanical-scoring dry-run already ran in the P6W2 retro (14/15 held, Weronika 4→5).
- **#820** — Execute **ontology C×T2** (Hybrid): distributed per-repo structural index + central semantic overlay; tooling chosen via an isolated-branch bake-off, gated on per-language derivability. Decided by owner from spike **#728** (`.claude/team/spikes/p6w2-ontology-vs-graphify.md`); product = child repos (topology axis folded in).
- **#821** — Phase 6 **Wave 16** placeholder (theme TBD — owner to set before kickoff; auto-drafted stub at retro).

**Live operational constraints until their issues close** (hard-won this wave — apply to any main-targeting work):
- Local pushes to `main` are blocked by **#816** (`test_pre_commit_ci_sync` fails in parent checkout only) → write to main via the `gh api` Contents/Data API, not `git push`.
- **Never** use `/tmp`-rooted worktrees — they false-fail two pre-push gates (**#817**, mermaid-gate cwd-relative workdir). Use `$HOME` or `.claude/worktrees/<unique>`.
- Per-commit `-c user.name`/`-c user.email` identity always; never global git config; never `--no-verify`; wave branches retained permanently.
- Parallel `isolation:worktree` spawns can cwd-collide — give each agent its own unique worktree. See [[feedback_cwd_collision_cross_spawn]].

Related: [[project_wave_key_cross_phase_collision]] (global monotonic wave id, Design B #804), [[project_p5w5_prodcutover_p6_dataquality]] (P7 data-quality scope).
