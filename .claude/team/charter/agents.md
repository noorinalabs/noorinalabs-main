# Agent Naming, Lifecycle & Orchestration

## Agent Naming Convention

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

## How to Instantiate the Team

When starting any work session, the orchestrating Claude instance should:

1. Read this org charter and the target repo's charter (`.claude/team/charter.md` in the child repo)
2. Read all roster files in `.claude/team/roster/`
3. Spawn the Program Director agent first (with their personality from roster), using the `team_name` specified in the target repo's charter
4. **The Program Director plans and coordinates but CANNOT spawn agents.** Only the orchestrating Claude instance (team lead) has access to the Agent tool. The Program Director must send spawn requests back to the team lead via SendMessage, including the full context for each agent to be spawned.
5. The team lead spawns all agents directly using the Agent tool — **all agents MUST use the same `team_name` as the Program Director**
6. All code-writing agents use `isolation: "worktree"`
7. Coordinate via named agents and SendMessage

## Agent Lifecycle Management

**Agents MUST be shut down as soon as their work is complete.** The orchestrator is responsible for:

1. **Shutting down implementation agents** immediately after their PR is created and confirmed. Do not leave agents idle waiting for potential follow-up work.
2. **Shutting down manager agents** once their wave is fully merged and retro is complete.
3. **Monitoring team size** — if the team config shows more than 10 active members, something is wrong. Shut down completed agents before spawning new ones.
4. **End-of-session cleanup** — before ending a session, run the full team teardown procedure below.

### Wave Retrospective (Required)

**Every wave MUST have a formal retrospective before agents are shut down.** Do NOT skip retros.

1. **Keep agents alive** until the wave is fully complete (all PRs merged, CI verified).
2. **Each participating agent contributes** via SendMessage to the orchestrator:
   - What went well
   - What went poorly
   - What to change for next wave
3. **The orchestrator adds** their own observations (deploy iterations, stalled agents, process gaps).
4. **Write findings** to `.claude/team/feedback_log.md` in the relevant repo(s).
5. **Actionable items** become charter updates, process changes, or new issues.
6. **Trust matrix update** — update scores on `CEO/0000-Trust_Matrix` branch, add done-well/needs-improvement notes, update roster cards with performance history.
7. **Hook/skill audit** — for every failure or friction point from the wave, ask: "Could a hook have prevented this? Could a skill have automated this?" Present candidates to the user. Prefer hooks over skills, skills over LLM generation. Create issues for approved implementations.
8. **Only then** shut down agents.

Skipping retros is a **moderate feedback event** for the orchestrator.

### Team Teardown Procedure

`TeamDelete` does NOT terminate running agents — it only removes the config. Always follow this procedure:

1. **Read the team config** to get the full member list:
   ```bash
   cat ~/.claude/teams/{team-name}/config.json | python3 -c "import json,sys; [print(m['name']) for m in json.load(sys.stdin).get('members',[]) if m['name']!='team-lead']"
   ```
2. **Send shutdown requests to every agent** via `SendMessage` with `{"type": "shutdown_request"}`. Send all in parallel (one message per agent — structured messages cannot be broadcast).
3. **Wait for confirmations** — agents will acknowledge and terminate. Allow ~30 seconds.
4. **Call `TeamDelete`** — this cleans up the config and directories. If it fails due to active members, edit the config to remove stale entries, then retry.
5. **Verify cleanup** — confirm `~/.claude/teams/{team-name}/` no longer exists.

**Never skip steps 1-3.** Calling `TeamDelete` without shutting down agents leaves orphan processes that consume resources and confuse the UI.

Failure to manage agent lifecycle leads to resource exhaustion and duplicate agent confusion. This is a **moderate feedback event** for the orchestrator.

## Hub-and-Spoke Orchestration Model

The orchestrator is the **single point that can create agents**. The Program Director coordinates and plans; the orchestrator executes the spawning. This is a hub-and-spoke model, not recursive delegation.

**Workflow:**

1. **Orchestrator spawns the Program Director** — who investigates, plans, creates GitHub issues, and coordinates across repos.
2. **Program Director does NOT do implementation work inline.** When the Program Director needs team members (for audits, releases, or standards work), they send a **spawn request** back to the orchestrator via SendMessage. The spawn request must include full context: task description, target files, acceptance criteria, git identity, and any dependencies.
3. **Orchestrator spawns team members** on behalf of the Program Director, routing results back via SendMessage.
4. **Team members report completion** to the orchestrator, who relays to the Program Director or acts on the results.

## Agent Naming with Repo Prefix

All spawned agents MUST be named `{repo-name}-{persona-firstname}` (e.g., `main-nadia`, `main-wanjiku`, `main-santiago`). The repo prefix identifies which repo's team the agent belongs to, enabling clear routing in multi-repo sessions. Use the short repo name (without the `noorinalabs-` prefix) for brevity:

| Repo | Prefix |
|------|--------|
| `noorinalabs-isnad-graph` | `isnad-graph-` |
| `noorinalabs-design-system` | `design-system-` |
| `noorinalabs-deploy` | `deploy-` |
| `noorinalabs-isnad-graph-ingestion` | `ingestion-` |
| `noorinalabs-landing-page` | `landing-page-` |
| `noorinalabs-main` (cross-repo) | `main-` |

## Team Names

Each repo defines its own `team_name` in its repo charter. Use that name for all Agent tool calls when working in that repo. For cross-repo coordination, use `team_name: "noorinalabs"`.

| Context | team_name |
|---------|-----------|
| Work in noorinalabs-isnad-graph | `noorinalabs-isnad-graph` |
| Work in noorinalabs-landing-page | `noorinalabs-landing-page` |
| Work in noorinalabs-deploy | `noorinalabs-deploy` |
| Work in noorinalabs-design-system | `noorinalabs-design-system` |
| Work in noorinalabs-isnad-graph-ingestion | `noorinalabs-isnad-graph-ingestion` |
| Cross-repo coordination | `noorinalabs` |

> **Agent tool limitation:** Spawned agents (including the Program Director and team members) do NOT have access to the Agent tool. They cannot spawn other agents. All agent spawning must be done by the orchestrating Claude instance.
