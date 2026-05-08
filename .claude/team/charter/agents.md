# Agent Naming, Lifecycle & Orchestration

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

## Agent Lifecycle Management <!-- promotion-target: skill -->
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
6. **Trust matrix update** — update scores in `.claude/team/trust_matrix.md` on `main`, add done-well/needs-improvement notes, update roster cards with performance history. All changes go to `main` — no separate branches for trust data.
7. **Hook/skill audit** — for every failure or friction point from the wave, ask: "Could a hook have prevented this? Could a skill have automated this?" Present candidates to the user. Prefer hooks over skills, skills over LLM generation. Create issues for approved implementations.
8. **Present full retro summary to the user** — output directly in the conversation (not just written to files). Must include: per-engineer assessments with severity, trust matrix changes, top 3 going well, top 3 pain points, proposed process changes, and any fire/hire actions. The user reviews and approves before proceeding.
9. **Only then** shut down agents.

Skipping retros is a **moderate feedback event** for the orchestrator.

### Per-Repo Worktree Isolation (Child Repos)

**The Agent tool's `isolation: "worktree"` only isolates the parent repo (`noorinalabs-main`). Child repos inside the worktree still share their original working directory.** This means two agents spawned with worktree isolation can still clobber each other's branches inside a child repo.

**Rule:** When spawning a code-writing agent for a child repo, the orchestrator MUST include **explicit per-repo worktree setup** in the agent's prompt:

```bash
# In the agent's prompt — BEFORE any code work:
cd /home/parameterization/code/noorinalabs-main/{child-repo}
git worktree add /tmp/{agent-name} origin/{branch-name}
# All work happens in /tmp/{agent-name}, NOT the main directory
```

**Orchestrator checklist for code-writing agent prompts:**
1. **Run `/ontology-librarian {topic}` first** — before any code changes, consult the ontology for domain context on the area being modified. Include the librarian's output in the agent's prompt so the agent starts with full context. If the librarian flags stale references, note them.
2. Include `git worktree add /tmp/{agent-name} {base}` as the first setup step
3. Tell the agent to `cd /tmp/{agent-name}` and work exclusively there
4. Tell the agent to `git worktree remove /tmp/{agent-name}` on completion (or the orchestrator cleans up)
5. **Never** instruct two agents to work in the same child repo directory

**Why:** In Wave C Phase 2, two agents sharing the isnad-graph directory cross-contaminated commits — session management code mixed with email verification code, requiring multiple cleanup pushes and blocking CI. This rule prevents that failure mode.

Spawning a code-writing agent without per-repo worktree setup is a **moderate feedback event** for the orchestrator.

### Scaffold Migration Chain Strategy

When a scaffold commit includes Alembic model stubs for parallel feature branches, it MUST also establish a **migration chain base**:

1. **Create a stub migration** in the scaffold that serves as the known chain point (e.g., `0002_phase3_scaffold.py` that adds no schema changes but establishes the revision).
2. **Document in MIGRATION_RANGES.md** that all feature branch migrations must use `down_revision = "{scaffold_migration_id}"` — not the initial migration.
3. **Include the chain rule in each agent's prompt** — specify the exact `down_revision` value.

**Why:** In Phase 3 Wave 1, all 4 feature PRs independently set `down_revision = "0001"`, which would create multiple Alembic heads and break `alembic upgrade head`. Reviewers caught this, but it required fix cycles on every PR. A scaffold migration base prevents this class of error entirely.

Omitting migration chain instructions when spawning parallel Alembic-aware agents is a **minor feedback event** for the orchestrator.

### Worktree Lock Management

Agents working in worktrees MUST manage lockfiles to prevent premature pruning and ghost locks:

1. **Lock on spawn** — when an agent starts in a worktree, lock it: `git worktree lock <path> --reason "agent:<agent-name> started:<timestamp>"`. This prevents `git worktree prune` from removing the worktree while the agent is active.
2. **Unlock on shutdown** — before an agent terminates (including shutdown_request handling), unlock: `git worktree unlock <path>`.
3. **Prune at wave end** — `git worktree prune` runs during `/wave-wrapup` AFTER all agents are shut down and unlocked. Never prune while agents are running.
4. **Stale lock detection** — during `/wave-wrapup`, Aino checks for locked worktrees whose agents are no longer running. Stale locks are removed with `git worktree unlock` and logged as a warning.

5. **Timeout cleanup** — worktree locks include a timestamp in their reason string. During `/wave-wrapup` or session start, any lock older than **20 minutes** is considered stale and automatically removed. This handles agents that crash without unlocking.

Failing to unlock a worktree on shutdown blocks future agents from using that branch. This is a **minor feedback event**.

### Auto-Trigger

When all PRs for a wave are merged into the deployments branch, the orchestrator must **automatically** trigger `/wave-wrapup`. Do not wait for the user to prompt this — the trigger condition (all wave PRs merged) is unambiguous.

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

## Hub-and-Spoke Orchestration Model <!-- promotion-target: none -->
The orchestrator is the **single point that can create agents**. The Program Director coordinates and plans; the orchestrator executes the spawning. This is a hub-and-spoke model, not recursive delegation.

**Workflow:**

1. **Orchestrator spawns the Program Director** — who investigates, plans, creates GitHub issues, and coordinates across repos.
2. **Program Director does NOT do implementation work inline.** When the Program Director needs team members (for audits, releases, or standards work), they send a **spawn request** back to the orchestrator via SendMessage. The spawn request must include full context: task description, target files, acceptance criteria, git identity, and any dependencies.
3. **Orchestrator spawns team members** on behalf of the Program Director, routing results back via SendMessage.
4. **Team members report completion** to the orchestrator, who relays to the Program Director or acts on the results.

### Spawn Request Delegation

**When any team member requests that another agent be spawned, the orchestrator MUST honor the request immediately.** Do not redirect the requesting agent to "do it yourself" — spawned agents do not have access to the Agent tool.

**Protocol:**
1. The requesting agent names the person to spawn and provides the task context
2. The orchestrator reads the named person's roster card to load identity and personality
3. The orchestrator spawns the agent with the context provided by the requester
4. The orchestrator confirms the spawn back to the requesting agent

**Rationale:** Sub-agents cannot spawn other agents (Agent tool limitation). Telling them to "do it yourself" wastes round-trips and stalls execution. This was identified in Wave C when Santiago requested Nadia Boukhari 3 times before the orchestrator acted.

Failing to honor a spawn request within the same response is a **minor feedback event** for the orchestrator.

### No Direct-to-Engineer Spawns

**The orchestrator MUST NOT spawn engineers directly without first spawning the Program Director.** Even for "simple" or "mechanical" fixes, the team hierarchy must be followed:

1. Spawn the Program Director
2. PD coordinates with the relevant repo manager(s)
3. Repo managers request engineer spawns via the PD
4. Orchestrator spawns engineers on behalf of the PD

**Rationale:** Bypassing the hierarchy loses manager visibility, skips peer review coordination, and undermines accountability. This was identified as a recurring pattern in Waves 1/A/B ("lead layer bypassed entirely") and repeated in Wave C Phase 1. The only exception is if the user explicitly authorizes a direct spawn.

Spawning engineers without the PD is a **moderate feedback event** for the orchestrator.

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

## Single-Leader Constraint: One Team Per Orchestrator Session <!-- promotion-target: none -->

The harness enforces **one team per orchestrator session** — `TeamCreate` fails with "Already leading team" if a team already exists. Combined with the Agent-tool limitation above, this shapes how waves run:

### What this means in practice

- **The `Team Names` table above is only operative when you open a session dedicated to one repo.** If a session is opened in `noorinalabs-main` to run a cross-repo wave, `TeamCreate("noorinalabs")` fires at session start and no other team can be created in that session. Agents for deploy, isnad-graph, user-service, landing-page, etc. are all spawned as members of the single `noorinalabs` team.
- **Cross-repo waves always use `team_name: "noorinalabs"`** for every agent — managers AND implementers — because the single-team constraint makes anything else technically impossible.
- **Per-repo team names** (`noorinalabs-isnad-graph`, `noorinalabs-deploy`, etc.) only apply when a session is run in isolation in that repo — not the common case for wave-kickoff work orchestrated from `noorinalabs-main`.

### Delegation mechanics (reinforcement of § Hub-and-Spoke)

1. **Orchestrator** calls `TeamCreate("noorinalabs")` at session start. Spawns managers (Program Director + per-repo managers) as members of this single team.
2. **Managers** do NOT have the Agent tool. When they need implementers, they `SendMessage` the orchestrator (team-lead) with a spawn request: "please spawn {Name} from {repo}/{roster-card} for {issue}, branch {X}, reviewers {Y, Z}."
3. **Orchestrator spawns implementers** with the context the manager provided PLUS the Ontology Context bake (per `enforce_ontology_context.py` hook — see § Orchestrator checklist below) PLUS the MANDATORY `/ontology-librarian` first-action instruction (per Hook 15 in `hooks.md`).
4. **Implementers report** back to their assigning manager via `SendMessage`. Cross-manager coordination is in-band (`SendMessage`) plus on-GitHub (meta-issue comments + Cross-Contract PRs).
5. **Per-repo rosters remain canonical** for commit identity, domain ownership, and reviewer pairing — the session team is a logical overlay on top of them.

### Reviewer slate discipline (FIRST-LINE in every spawn prompt)

> **Position-first rule (resolves [main#201](https://github.com/noorinalabs/noorinalabs-main/issues/201)).** The reviewer slate is the first decision the spawn prompt forces the orchestrator (or PD-via-spawn-request) to make — not buried mid-checklist where it gets back-filled after scope/branch/sequencing have already framed the assignment. Every spawn prompt template MUST place this section immediately after the identity / git-identity preamble and BEFORE the `## Ontology Context` section.
>
> **You MUST NOT name as reviewer:**
> - The **manager of the implementer's repo** (manager-boundary rule — see `pull-requests.md` § Two-Reviewer Assignment, observed-and-corrected ≥4× across three managers in P2W10).
> - The **author of the upstream PR being reviewed** (self-review boundary — `block_gh_pr_review.py` enforces, but spawn-time prevention is cheaper than merge-time block).
> - An agent currently **owning a gating issue** for this PR (independence — the gating-issue owner needs to drive resolution, not bless the implementation).
> - An **Advisor-only role** on a cross-team consultation (per task-framework Statement A/B distinction — Advisor reviews shape decisions, not PR diffs).
>
> **Valid reviewer sources:**
> - **Same-team technical peers** — primary slot (e.g., user-service tech-lead reviewing user-service implementer).
> - **Cross-team technical peers with substantive domain overlap** — secondary slot (e.g., deploy SRE reviewing user-service CI workflow change).
> - **Standards & Quality Lead (Aino Virtanen)** for charter-convention questions only — not as a generic peer-review slot.
>
> **Name BOTH reviewers explicitly in the spawn prompt** AND in the kickoff comment AND in the meta-issue execution-plan table BEFORE any branches are created. If the PD's execution-plan table is missing a 2nd reviewer for any expected PR, the orchestrator pauses spawning and asks the PD to fill the gap (see `pull-requests.md` § Two-Reviewer Assignment at Wave Kickoff).
>
> **Why position-first:** P2W10 surfaced four+ instances across three managers' spawn prompts where the manager-as-reviewer anti-pattern slipped through despite charter rule existing. Pattern: reviewer-naming had already happened mentally during the early-drafting pass (scope/branch/sequencing first, reviewers as a back-fill). The charter rule was correctly applied in isolated contexts but missed when embedded in a multi-section spawn prompt. Moving the rule to first-line position makes "who reviews this" a first-order architectural decision the template forces the agent to make before advancing. Discipline becomes architectural, not memorial. Co-signed by Bereket (deploy manager), Nadia Boukhari (isnad-graph + user-service manager), Marcia (landing-page manager) — each had a concrete instance during W10.

### Orchestrator checklist when spawning an implementer

Every implementer spawn prompt MUST include, **in order**:

1. **Reviewer slate** (first-line per § Reviewer slate discipline above) — both reviewers named, manager-boundary verified, valid-source check applied.
2. **`## Ontology Context`** section (literal heading) with librarian output baked in — `enforce_ontology_context.py` scans for this heading and blocks the spawn if absent.
3. **MANDATORY first-action** instruction to run `/ontology-librarian {topic}` in the spawned agent's own session — Hook 15 scans the agent's transcript independently and blocks Edit/Write otherwise.
4. **Git identity** flags (`git -c user.name="..." -c user.email="parametrization+FirstName.LastName@gmail.com"`).
5. **Branch name** matching `{FirstInitial}.{LastName}/{IIII}-{slug}` and **PR target** (typically `deployments/phase-{N}/wave-{M}`).
6. **Cross-Contract rule** reference if the PR is part of a cross-contract cluster (charter `pull-requests.md`).
7. **Charter enforcement reminders** (2 reviewers, CI green before merge, no `--no-verify`, no global/repo git config, `/ontology-librarian` per agent).
8. **Reporting pattern** — who they report to (usually their manager) and when (draft open, CI green, blocker, merge).
9. **/tmp file-race discipline:** When using `--body-file` with `gh issue/pr comment` or `git commit -F`, write the file to an issue#-keyed path (e.g., `/tmp/{issue#}-{purpose}.md`) IMMEDIATELY before the gh/git call — no other tool calls between the Write and the consuming Bash. Hook `block_stale_tmp_message_file` blocks files older than 30s. P3W6 surfaced 3 such blocks in spawned-agent gh-comment flows; this discipline prevents them.

### Origin

Documented during P2W10 kickoff 2026-04-23. Prior charter already had the spawn-delegation mechanics (§ Hub-and-Spoke Orchestration Model), but not the explicit single-leader constraint that eliminates multi-team orchestration as an option. The § Team Names table was ambiguous on whether "Work in noorinalabs-isnad-graph" meant a dedicated isnad-graph-only session or any session touching that repo — this section resolves it in favor of the single-session-team pattern for cross-repo work.


## Pre-Spawn State Check + Crossed-Message Race Protocol <!-- promotion-target: none -->

Phase 3 Wave 1 surfaced a recurring failure shape: implementer ships work + status report → orchestrator's task_assignment for that same work was already in flight in the message bus → implementer receives "do X" message AFTER having shipped X. This is **architecturally distinct from `feedback_refresh_before_status_claim`** — no individual discipline fix prevents the race; verification-before-claim doesn't help when the message bus delivers messages in the order they were *queued*, not the order events resolved.

### Default protocol — accept as cost-of-throughput

The implementer-anticipates-context discipline (implementers reading upstream charter/brief aggressively and starting work before the formal `task_assignment` lands) is high-leverage for wave throughput. P3W1 delivered 8/8 PRs in ~2.5 hours partly because Lucas + Aisha both anticipated Round-2/3 charters from coordinator briefs and started implementing during the team-lead's compose window.

Killing that anticipation to eliminate the race would cost more than the race costs. So the default is to ACCEPT the race and standardize the implementer's response shape:

```
ack — task #N — already shipped at PR #M at YYYY-MM-DDTHH:MM:SSZ; no action needed
```

The implementer who finds themselves in this race posts the canonical-shape ack and idles. No retraction of the orchestrator's task_assignment is needed — it is informationally redundant with the implementer's status report, not contradictory.

### Narrow trigger — orchestrator poll before SPAWN assignments

When the orchestrator is about to send an assignment that **spawns a new implementer instance** OR **changes branch/worktree paths** (i.e., assignments where the consequences of duplicate work are non-trivial), the orchestrator MUST first verify the work is not already done:

```bash
gh pr list --repo <repo> --search "in:title <issue-keyword>" --state all --json number,state,mergedAt --limit 5
gh issue view <N> --repo <repo> --json state,closedAt
```

If the work is already shipped (PR open or merged, issue closed), the orchestrator no-ops the assignment + sends a "noted, work already done" acknowledgment instead of spawning a new instance.

Assignments to **already-active implementers in known-active scope** (e.g., follow-on tasks within an existing worktree) skip the poll — the throughput cost on those is not justified by the small noise cost.

### Severity

- Crossed-in-flight race on already-active implementer (covered by default protocol): minor noise, no feedback log entry.
- Spawn duplication (orchestrator spawns a new implementer for work already shipped): moderate — the duplicate spawn wastes context and may produce conflicting PRs. Pre-spawn poll prevents this.
- Implementer who fails to use canonical-shape ack and produces ambiguous duplicate-work messages: minor; correct-the-shape feedback in retro.

### Adoption signal

Track instance count at each retro. If the count grows materially (e.g., crossed-in-flight races trigger downstream coordination overhead that consumes >5% of wave time), revisit and consider Option 1 (full orchestrator-poll-before-every-assignment) or Option 2 (implementer-blocks-on-task-assignment) at that point.

### Why

P3W1 saw ~4 Lucas-side message-ordering races plus ≥1 analogous Aisha-side instance, all professionally handled but each costing ~30s of attention overhead. None caused duplicate work or wrong-direction shipping. The narrow trigger captures the high-consequence variant (spawn duplication) without sacrificing the wave-throughput-positive implementer-anticipates-context discipline.

<!-- Promoted from memory: feedback_child_repo_implementer_rule.md (P3W5 retro 2026-05-06) -->

## Child-Repo Implementer Rule + Spawn-Brief Verification (Mandatory) <!-- promotion-target: hook -->

When spawning an implementer for a PR or feature in a child repo, the implementer's identity (`user.name` + `user.email`) MUST come from **that child repo's** team roster (`<child>/.claude/team/roster/` and `<child>/.claude/team/roster.json`) — NOT from the parent's org-level coordination team and NOT from a sibling repo's roster.

### Why

Hook 5 (`validate_commit_identity`) scans the working repo's `roster.json` and BLOCKS commits whose `user.name` isn't a roster member. Per the enforcement-hierarchy principle (hook > skill > charter), the hook is the binding source of truth — a wrong-roster spawn will fail at first commit, costing a respawn cycle. Each child repo has its own simulated team with its own role fit; cross-roster authorship is a category error the hook catches.

### Orchestrator-side spawn-brief checklist

Before authoring an implementer spawn brief for a child-repo issue:

1. **Determine working repo for the change.** Read the issue body. Note that **issue location ≠ working repo** (e.g., a `noorinalabs-deploy` issue body may say the changes go in `noorinalabs-landing-page`). The repo that hosts the FILES the implementer will edit is the working repo.
2. **Read that repo's roster.** `cat <working-repo>/.claude/team/roster.json` or list `<working-repo>/.claude/team/roster/`.
3. **Pick a roster member with role fit** for the change class (frontend Dockerfile → frontend engineer; CI workflow → devops/platform engineer; security/CVE → security engineer; observability config → observability engineer; etc.).
4. **In the spawn brief, set the implementer's identity to that roster member's `user.name` + `user.email`.**
5. **Reviewer assignment is a separate decision.** Cross-team reviewer is OK (e.g., parent / sibling-team reviewer reading a child-repo PR). Don't conflate REVIEWER class with IMPLEMENTER class — see § Role-Class-Specific Boundaries elsewhere in charter for the distinction.

### Per-repo implementer pools (verify at spawn time — these snapshots may drift)

- `noorinalabs-deploy`: Lucas Ferreira, Aisha Idrissi, Bereket Tadesse, Weronika Zielinska, Nino Kavtaradze, others
- `noorinalabs-isnad-graph`: Idris Yusuf, Linh Pham, Anya Kowalczyk, Mateo Salazar, others
- `noorinalabs-user-service`: Mateo Salazar, Anya Kowalczyk, others
- `noorinalabs-landing-page`: Anika Diop-Sarr, Cédric Novák, Kofi Mensah-Williams, Marcia Vasquez-Paredes, Nazia Rahman
- `noorinalabs-main` (parent): Wanjiku Mwangi (TPM), Aino Virtanen (Standards), Santiago Ferreira (RC), Nadia Khoury (PD)
- `noorinalabs-design-system`, `noorinalabs-data-acquisition`, `noorinalabs-isnad-ingest-platform`: per-repo rosters

The verbatim canonical roster lives in each child repo's `.claude/team/roster.json` — read that at spawn time, not this snapshot.

### Exceptions

- **User explicitly directs otherwise** in a given session ("have Lucas do the landing-page work" overrides). Hook would still block; user would need to register the agent in the target roster first or accept the block.
- **Child repo has no `.claude/team/` defined yet** — check recent git history for de-facto implementer (`git log --format='%an' -- <path>`) and match, or ask the user before defaulting.

### Severity if violated

Wrong-roster spawn (hook-blocked at first commit, respawn required): minor — auto-corrected by Hook 5; cost is one wasted Aino-spawn. Wrong-roster spawn that bypasses Hook 5 (e.g., committed via a different mechanism that escapes the hook): moderate — the child-repo's role-fit signal is corrupted in git history.

### Failure modes seen and what blocked them

| Date | Surface | What went wrong | What blocked it |
|---|---|---|---|
| 2026-04-22 | child-repo#139 prereqs | Deferred-under-misread of user intent | Owner correction next turn |
| 2026-05-03 | P3W3 deploy#242 spawn brief | Spawned Lucas Ferreira (deploy roster) for landing-page work; conflated reviewer-class permission with implementer-class | Hook 5 blocked Lucas-242's first commit; Lucas-242 surfaced charter Pattern B catch (verify-vs-artifact: roster.json) and recommended Kofi from landing-page roster |
