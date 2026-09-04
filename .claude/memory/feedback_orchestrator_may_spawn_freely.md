---
name: feedback_orchestrator_may_spawn_freely
description: Owner lifted the "don't spawn agents unless asked" session guidance — the orchestrator spawns whatever team it needs to reach the goal, per CLAUDE.md's team mandate.
metadata:
  type: feedback
last_verified: 2026-08-03
---

Owner directive, 2026-08-03 (wave-29 retro): **"Let's change the session guidance. You should
be able to spawn all the agents you need to reach your goals."**

This resolves a standing conflict. Some sessions ship a harness instruction reading roughly
*"Do not call the AgentTool unless the user requested it"*, which collides head-on with
`CLAUDE.md` § Team Workflow (**"All work MUST be executed through the simulated team
structure. No work begins without spawning the team."**) and with the skills that name
spawns outright — `/wave-retro` Step 7.7 says the orchestrator spawns Aino Virtanen for
memory-to-automation conversions; `/wave-wrapup`, `/wave-kickoff`, and the PR-review flow
all assume roster spawns.

**Why:** the owner wants the charter's team model to be the operative one. Asking for
per-spawn permission turned every delegation-heavy skill step into a blocking question and
serialized work that the charter explicitly designs to fan out.

**How to apply:** treat the charter as authoritative on delegation. Spawn the roster members
a skill names, without asking first. Do not re-raise the question each session or each wave.
The constraints that still bind are the real ones, not permission:

- **Hub-and-spoke only** — the orchestrator is the sole spawner; spawned agents have no
  `Agent` tool ([[feedback_child_repo_spawn_no_isolation]] covers the isolation half).
- **Never pass `team_name`** — deprecated and ignored by the Agent tool; `validate_no_team_name`
  blocks a spawn carrying one (#1375). One implicit team per session, no name to choose.
- **Model tier** per `.claude/team/charter/agents/orchestration-model.md` — mechanical
  read-only work is Haiku; substantive code is Sonnet; gate/security/merge-gate reasoning is
  Opus. Every PR still needs ≥1 Opus merge-gate review.
- **Spawn-brief discipline** still applies in full — including never handing a reviewer an
  unverified state assertion ([[feedback_patch_id_after_rebase_not_ancestry]]).

Cost is not the gate; reaching the goal is. Scale the fan-out to the work.

**Corroborated first-hand by the owner, 2026-09-04 (#1488 merge gate).** The merge-gate
reviewer flagged a real provenance limit: the 2026-08-03 directive was **single-source and
self-attested** — this note was its own only evidence, and the phrase appears nowhere else in
the tree, not even `feedback_log.md`. A doctrine promoted into every session's prefix should
not rest on one unwitnessed note. It no longer does: in the session that landed #1486 the
owner stated the policy directly and unprompted — *"I want you to be able to spawn freely"* —
and then authorized the promotion. So the policy is now **doubly attested** (this note, plus a
live owner statement); the verbatim 2026-08-03 quotation above remains single-source and
should be cited as a quotation, not as independent evidence.

Recorded HERE rather than in the PR thread deliberately, on the reviewer's point: **#1486's
whole finding was that a directive in a place nobody reads loses to one that is always
present — so a corroboration in a place nobody reads has the identical failure mode.** Note
also what the merge gate did and did not certify: it approved the text and the safety
analysis, and explicitly did NOT certify this provenance. Keep the two claims separable.

**Promoted to the always-loaded prefix, 2026-09-03 (#1486).** This note alone did not
hold: it lives in tier-2 `section_spawn_delegation.md`, which loads on demand, while the
conflicting *"do not call the Agent tool unless the user requested it"* guidance is present
every turn — so on 2026-08-09/10 the orchestrator asked for spawn permission twice anyway.
`CLAUDE.md` § Team Workflow now carries the directive itself, resolving the conflict on its
own terms: the guidance says *unless the user requested it*, and the user requested it in
advance as a standing directive, so the condition is already met — nothing is being overridden. This
note stays as the rationale and the full constraint list; the prefix carries the directive.
