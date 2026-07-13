# Agents — Naming & Teams

> Part of the [agents charter index](../agents.md) — re-shelved from `charter/agents.md` for section-level loading (#963). Rules unchanged.

## Agent Naming Convention <!-- promotion-target: none -->
**Every spawned agent MUST map to a team roster member.** No anonymous functional agents.

- **Naming pattern:** `{firstname}-{task-description}` (e.g., `nadia-cross-repo-sync`, `wanjiku-dependency-audit`)
- The orchestrator determines the most appropriate team member for the task BEFORE spawning
- Tasks are assigned based on role fit

**Mapping guide:**
| Task Type | Assigned To |
|-----------|-------------|
| Cross-repo coordination, meta-issues, program planning | Nadia Khoury |
| Dependency tracking, timeline audits, blocker identification | Wanjiku Mwangi |
| Release management, versioning, deployment sequencing, changelogs | Santiago Ferreira |
| Charter maintenance, hooks, org-wide standards, convention audits | Aino Virtanen |

## How to Instantiate the Team <!-- promotion-target: skill -->
When starting any work session, the orchestrating Claude instance should:

1. Read this org charter and the target repo's charter (`.claude/team/charter.md` in the child repo)
2. Read all roster files in `.claude/team/roster/`
3. Spawn the Program Director agent first (with their personality from roster), using the `team_name` specified in the target repo's charter
4. **The Program Director plans and coordinates but CANNOT spawn agents.** Only the orchestrating Claude instance (team lead) has access to the Agent tool. The Program Director must send spawn requests back to the team lead via SendMessage, including the full context for each agent to be spawned.
5. The team lead spawns all agents directly using the Agent tool — **all agents MUST use the same `team_name` as the Program Director**
6. All code-writing agents use `isolation: "worktree"`
7. Coordinate via named agents and SendMessage

## Agent Naming with Repo Prefix <!-- promotion-target: none -->
All spawned agents MUST be named `{repo-name}-{persona-firstname}` (e.g., `main-nadia`, `main-wanjiku`, `main-santiago`). The repo prefix identifies which repo's team the agent belongs to, enabling clear routing in multi-repo sessions. Use the short repo name (without the `noorinalabs-` prefix) for brevity:

| Repo | Prefix |
|------|--------|
| `noorinalabs-isnad-graph` | `isnad-graph-` |
| `noorinalabs-design-system` | `design-system-` |
| `noorinalabs-deploy` | `deploy-` |
| `noorinalabs-data-acquisition` | `acquisition-` |
| `noorinalabs-landing-page` | `landing-page-` |
| `noorinalabs-main` (cross-repo) | `main-` |

## Team Names <!-- promotion-target: none -->

> **Single-Leader Constraint applies.** Per § Single-Leader Constraint below, only ONE team can exist per orchestrator session. The per-repo `team_name` rows in this table are therefore **only operative when you open a session dedicated to that one repo for repo-only work**. The common case — wave-kickoff orchestration from `noorinalabs-main` touching multiple child repos — uses `team_name: "noorinalabs"` for every agent regardless of which repo's code they're editing. Read § Single-Leader Constraint first; the rows below are the per-repo-session fallback, not the cross-repo default.

Each repo defines its own `team_name` in its repo charter. For dedicated per-repo sessions, use that name for all Agent tool calls when working in that repo. For cross-repo coordination (the common case), use `team_name: "noorinalabs"`.

| Context | team_name |
|---------|-----------|
| Cross-repo coordination (default for wave work orchestrated from `noorinalabs-main`) | `noorinalabs` |
| Dedicated session in noorinalabs-isnad-graph (repo-only work) | `noorinalabs-isnad-graph` |
| Dedicated session in noorinalabs-landing-page (repo-only work) | `noorinalabs-landing-page` |
| Dedicated session in noorinalabs-deploy (repo-only work) | `noorinalabs-deploy` |
| Dedicated session in noorinalabs-design-system (repo-only work) | `noorinalabs-design-system` |
| Dedicated session in noorinalabs-data-acquisition (repo-only work) | `noorinalabs-data-acquisition` |

> **Agent tool limitation:** Spawned agents (including the Program Director and team members) do NOT have access to the Agent tool. They cannot spawn other agents. All agent spawning must be done by the orchestrating Claude instance. This is the harness reinforcement of the single-team constraint — see § Hub-and-Spoke Orchestration Model and § Single-Leader Constraint.

