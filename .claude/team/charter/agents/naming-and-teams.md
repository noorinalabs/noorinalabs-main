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
3. Spawn the Program Director agent first (with their personality from roster). **Do not pass `team_name`** — see § Team Names below.
4. **The Program Director plans and coordinates but CANNOT spawn agents.** Only the orchestrating Claude instance (team lead) has access to the Agent tool. The Program Director must send spawn requests back to the team lead via SendMessage, including the full context for each agent to be spawned.
5. The team lead spawns all agents directly using the Agent tool
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

## Team Names — RETIRED: never pass `team_name` <!-- promotion-target: none -->

> **`team_name` is a deprecated Agent-tool parameter and MUST NOT be passed** (#1375). The live tool schema documents it as *"Deprecated; ignored. The session has a single implicit team."* The correct number of `team_name` values in any spawn is **zero**, and `validate_no_team_name` (PreToolUse, `Agent` matcher) blocks a spawn that carries one.

There is one implicit team per orchestrator session. Nothing creates it, nothing names it, and there is no `TeamCreate`/`TeamDelete` to call — so there is no name to choose and no per-repo table to consult. An agent working on child-repo code is a member of the same single session team as everyone else; **the repo it edits is expressed by its worktree and its brief, not by a team name.**

Agents remain addressable by their **agent name** (§ Agent Naming with Repo Prefix above) via `SendMessage` — that is the routing mechanism, and it never depended on `team_name`.

**What replaced the per-repo table:** nothing needed to. The rows previously listed here (`noorinalabs`, `noorinalabs-isnad-graph`, `noorinalabs-deploy`, …) mapped a session context to a team name for the Agent tool. With the parameter ignored, that mapping has no consumer. Per-repo *rosters* under `<repo>/.claude/team/roster/` remain fully canonical for commit identity, domain ownership, and reviewer pairing — those are unaffected and are what "which repo's team" actually means now.

> **Agent tool limitation:** Spawned agents (including the Program Director and team members) do NOT have access to the Agent tool. They cannot spawn other agents. All agent spawning must be done by the orchestrating Claude instance. This is the harness reinforcement of the single-team constraint — see § Hub-and-Spoke Orchestration Model and § Single-Leader Constraint.

