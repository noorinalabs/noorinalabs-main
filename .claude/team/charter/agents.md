# Agent Naming, Lifecycle & Orchestration

> **Section index (#963).** This file's sections now live as per-concern files under [`charter/agents/`](agents/). Every heading below is preserved so existing `agents.md#anchor` deep-links keep resolving — each entry forwards to the section's new location. The promotion markers (`promotion-target` / `promoted-to`) moved with the section bodies; this index is not a promotion-audit input.

## Agent Naming Convention
Every spawned agent maps to a team roster member — no anonymous functional agents. → [agents/naming-and-teams.md](agents/naming-and-teams.md#agent-naming-convention)

## How to Instantiate the Team
Session-start steps for the orchestrating instance to stand up the team. → [agents/naming-and-teams.md](agents/naming-and-teams.md#how-to-instantiate-the-team)

## Governed Headcount (Roster Budget)
Budgeted, machine-enforced persona roster (`lib/headcount_budget.py`); growth needs a budget change first. → [agents/headcount.md](agents/headcount.md#governed-headcount-roster-budget)

## Agent Lifecycle Management
Spawn/shutdown responsibilities — agents are shut down as soon as their work completes. → [agents/lifecycle.md](agents/lifecycle.md#agent-lifecycle-management)

## Orchestrator Spawn Discipline — Reuse Idle Teammates, Don't Clone
SendMessage the idle existing persona instead of spawning a numeric-suffix clone. → [agents/spawn-discipline.md](agents/spawn-discipline.md#orchestrator-spawn-discipline--reuse-idle-teammates-dont-clone)

## Hub-and-Spoke Orchestration Model
The orchestrator is the single point that can create agents; managers request spawns. → [agents/orchestration-model.md](agents/orchestration-model.md#hub-and-spoke-orchestration-model)

## Agent Naming with Repo Prefix
Agents are named `{repo-name}-{persona-firstname}` to identify their repo team. → [agents/naming-and-teams.md](agents/naming-and-teams.md#agent-naming-with-repo-prefix)

## Team Names
Per-repo `team_name` table — operative only for isolated per-repo sessions. → [agents/naming-and-teams.md](agents/naming-and-teams.md#team-names)

## Single-Leader Constraint: One Team Per Orchestrator Session
One implicit team per orchestrator session; full delegation mechanics and the orchestrator checklists for spawning implementers and reviewers. → [agents/orchestration-model.md](agents/orchestration-model.md#single-leader-constraint-one-team-per-orchestrator-session)

## Pre-Spawn State Check + Crossed-Message Race Protocol
Re-verify artifact state before spawn/assignment; resolution rules when messages cross mid-flight. → [agents/spawn-discipline.md](agents/spawn-discipline.md#pre-spawn-state-check--crossed-message-race-protocol)

## Orchestrator State-Correction Discipline — One Aligned Instruction, Never a Serial Toggle
Re-read the agent's current state, then send ONE aligned correction — never a serial toggle. → [agents/spawn-discipline.md](agents/spawn-discipline.md#orchestrator-state-correction-discipline--one-aligned-instruction-never-a-serial-toggle)

## Child-Repo Implementer Rule + Spawn-Brief Verification (Mandatory)
Child-repo implementers use that child's roster identity; spawn briefs are verified at origin HEAD. → [agents/spawn-discipline.md](agents/spawn-discipline.md#child-repo-implementer-rule--spawn-brief-verification-mandatory)

## Agent Liveness Checkpoint
Periodic liveness checks so zero-output stalls surface before the wave ends. → [agents/lifecycle.md](agents/lifecycle.md#agent-liveness-checkpoint)

## Throttle-Stall Recovery — Trigger Thresholds
Trigger thresholds for the orchestrator takeover of a throttle-stalled implementer. → [agents/lifecycle.md](agents/lifecycle.md#throttle-stall-recovery--trigger-thresholds)

## Session-Hygiene Playbook & Lean Briefs
`/clear` at wave boundaries, proactive `/compact`, cache-prefix discipline, tool-result clearing, and lean section-extract briefs (`warn_oversized_brief.py`, `make skeleton`). → [agents/session-hygiene.md](agents/session-hygiene.md#session-hygiene-playbook--lean-briefs-1020)
