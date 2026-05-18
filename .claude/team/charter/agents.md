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

<!-- Promoted from memory: feedback_reuse_idle_teammates_not_clones.md (P3W9 retro 2026-05-12, owner-approved 2026-05-13; pre-promote-on-first-occurrence variant of the enforcement-hierarchy rule) -->

## Orchestrator Spawn Discipline — Reuse Idle Teammates, Don't Clone <!-- promotion-target: none -->

When the orchestrator needs to assign new work to a teammate whose persona already exists in the session team, `SendMessage` the idle existing instance — do NOT spawn a fresh `Agent` with a numeric-suffix name (`aino2`, `nadia2`, `wanjiku3`).

### Why

Idle teammates can receive messages — `SendMessage` wakes them up. Spawning a clone creates:

- **Roster clutter.** `aino` and `aino2` side-by-side for the same persona confuses both the operator (which one has the PR context?) and `SendMessage` routing.
- **No shared session memory.** Each fresh `Agent` is a blank slate; the original's accumulated context (PR #409 review history, scratch-file paths, mid-task partial work) is lost.
- **Duplicated Hook 15 librarian overhead.** Every clone must re-invoke `/ontology-librarian` from scratch.
- **Identity-hygiene drift.** Over a multi-PR session the roster grows linearly with PR count instead of staying at the canonical N team members.

### How to apply

- After a teammate sends a "PR ready" or "review complete" idle notification, they are AVAILABLE for the next task. `SendMessage` them with the new spawn-brief content; idle teammates wake on message receipt.
- Only spawn a fresh `Agent` when (a) the persona doesn't yet exist in the session team, OR (b) the existing instance is mid-task and the new work must run truly concurrently with theirs.
- `wanjiku2` (P3W9) is a legitimate parallel-collision precedent: Wanjiku reviewed PR #409 AND PR #410 in the same window; #410 was assigned to `wanjiku2` to keep `/tmp/<reviewer>_review_<PR#>.md` namespaces separate per the [[parallel-reviewer-tmp-filename-collision]] discipline. That precedent does NOT generalize to "always clone for the next task."
- If unsure whether to reuse or clone, default to reuse — clones are recoverable (`SendMessage` shutdown_request, respawn fresh), but the wasted spawn cost is not.

### Severity if violated

- One unnecessary clone in a session: **minor** (roster clutter; ~5min context loss when the clone has to rebuild what the original already knew).
- Pattern across a session (3+ clones in a single wave, as observed in P3W9 with `aino2`/`nadia2`/`wanjiku3`): **moderate** — pre-emptive promotion to charter on first-occurrence rather than waiting for second instance, since the cost (~15min per clone) and the recovery friction justify codifying immediately.

### Origin

P3W9 instances 2026-05-12: orchestrator spawned `aino2` for issue #401 work, `wanjiku3` for issue #163 work, `nadia2` for issue #126 work despite `aino`, `wanjiku2`, `nadia` being idle from prior W9 tasks. Owner flagged the pattern mid-session; this section codifies the correction. Companion to `feedback_throttle_takeover` (orchestrator-class spawn-discipline family — both are "use the agent you have, not a fresh one").

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

### Spawn Isolation Default

**All implementer-class spawns from the orchestrator MUST be invoked with `isolation: "worktree"`,** even when the parent-side worktree is cosmetic (e.g., the agent's actual code work lives in a child-repo clone).

**Rationale:** the harness uses worktree-isolation as the signal for workspace-presented team-member surfaces. Non-isolated subagents render as generic "background tasks" — incorrect for implementer-class agents that the operator needs to monitor as team members.

**Cost:** a temporary parent-repo worktree per agent (auto-cleaned if no changes — see Agent tool docs).

**Benefit:** correct workspace presentation; Hook 14 (`enforce_ontology_context`) fires consistently across all implementer spawns; manager-class agents (per-repo PD/manager) and implementer-class agents (per-repo engineers) both render under their team membership rather than as anonymous background tasks.

**Exception:** research-only forks (e.g., `Agent` calls that omit `subagent_type` to inherit context) need NOT use isolation, since they're explicitly context-inheriting forks rather than fresh implementer workspaces.

**Origin:** owner-named at P3W6 wave-kickoff (2026-05-06) after observing 18 implementer spawns rendered as "background tasks" in the harness UI rather than as workspace-presented team members. The orchestrator weighed the trade-off explicitly during spawn ("17 of 18 implementers do code work in child repos which are `.gitignore`d from the parent — orchestrator-side worktree is cosmetic") and picked "no parent worktree" — that turned out to be the wrong call because the UI presentation cost wasn't surfaced in the trade-off analysis. Codified by noorinalabs-main#290.

Failing to set `isolation: "worktree"` on an implementer spawn is a **minor feedback event** for the orchestrator.

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

> **Position-first rule (resolves [main#201](https://github.com/noorinalabs/noorinalabs-main/issues/201)).** The reviewer slate is the first decision the spawn prompt forces the orchestrator (or PD-via-spawn-request) to make — not buried mid-checklist where it gets back-filled after scope/branch/sequencing have already framed the assignment. Every spawn prompt template MUST place this section immediately after the identity / git-identity preamble and BEFORE the `## Ontology Context` section (when that section is present — see coordinator-class exemption note below).
>
> **Coordinator-class exemption (#468):** the `## Ontology Context` section is MANDATORY for implementer-class spawns and OPTIONAL for coordinator-class spawns (Manager, Pipeline Manager, Project Lead, Program Director, TPM / Technical Program Manager, Release Coordinator). Coordinators communicate primarily via SendMessage and rarely Edit/Write directly; `enforce_ontology_context.py` matches the canonical `You are **{Name}**, {Role}[ for {repo}]` opener and exempts these roles from the spawn-time Agent block. Hook 15 (`enforce_librarian_consulted.py`) still fires at the Edit/Write surface for the few coordinators that do edit. When a coordinator brief DOES include `## Ontology Context`, the position-first rule above continues to apply — the section retains its required location.
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

### Reviewer spawn brief — throughline-watch (default, #320) <!-- promotion-target: none -->

> **Every reviewer-class spawn brief MUST include a "Throughline-watch" instruction.** Reviewers are PR-scoped by primary task, but they often see cross-PR patterns that only become visible when looking at the wave from a reviewer position. Asking explicitly for throughline observations turns this latent signal into a structured surface for the wave retro's ★ summary.
>
> **The section MUST appear in every reviewer-class spawn brief**, regardless of whether the wave is expected to have a wave-level thesis. Single-PR waves can produce "no throughline observed, this is a standalone fix" and that is itself a useful retro signal.
>
> **Required template block (copy-paste verbatim into reviewer-class spawn briefs):**
>
> ```
> ## Throughline-watch (in addition to PR-level review)
>
> As you review this PR, note any pattern that recurs across multiple PRs in
> the wave or any wave-level structural finding that emerges from your
> PR-level review. Surface findings explicitly at the end of your review
> comment under a `## Throughline observations` section — do NOT bury them
> inside TechDebt or per-line inline review.
>
> Typical throughline shapes (illustrative, not exhaustive):
> - "Same root cause appears in {N} PRs across {M} repos" — convergent class
> - "Boundary X (parent→child / hook→skill / detection→strategy) breaks
>   repeatedly" — boundary-class
> - "Charter rule Y is technically followed but operationally undermined
>   by Z" — rule-vs-practice gap
> - "Memory M would prevent class C but isn't promoted to charter/hook
>   yet" — promotion candidate
>
> If you observe no throughline (single-PR wave, or finding is fully
> PR-scoped), write: `## Throughline observations\n\nNo wave-level pattern
> observed — this PR is a standalone fix.` The explicit no-pattern record
> is useful retro-signal too.
>
> The next wave-retro `*` summary pass synthesizes throughline observations
> across all reviewers into the wave thesis (per P3W7 demonstration:
> 5 reviewers + 4 implementers independently arrived at the two-tier wave
> thesis BEFORE the * spawn fired).
> ```
>
> **Why default, not per-wave addition:** P3W7 added the throughline-watch instruction ad-hoc to that wave's reviewer briefs and produced a complete pre-loaded retro thesis (Idris-coined "fixture-first discipline broke at the parent→child update boundary" confirmed by 5 subsequent reviewers; Nadia's ★ spawn synthesized rather than discovered). Making this default — not memorial discipline that the orchestrator must remember to add — propagates the P3W7 win to every wave.
>
> **Origin:** P3W7 retro feedback log § Proposed process changes #5 (orchestrator-class). Promoted via #320.

### Orchestrator checklist when spawning an implementer

Every implementer spawn prompt MUST include, **in order**:

1. **Reviewer slate** (first-line per § Reviewer slate discipline above) — both reviewers named, manager-boundary verified, valid-source check applied.
2. **`## Ontology Context`** section (literal heading) with librarian output baked in — `enforce_ontology_context.py` scans for this heading and blocks the spawn if absent. **Coordinator-class spawns are exempt** (Manager, Pipeline Manager, Project Lead, Program Director, TPM / Technical Program Manager, Release Coordinator) per the carveout above and #468; the hook's `COORDINATOR_ROLE_OPENER` regex matches the canonical `You are **{Name}**, {Role}[ for {repo}]` opener and skips the block. This item remains MANDATORY for implementer-class spawns (Engineer, Tech Lead, Standards & Quality Lead, Security Engineer, Engineering Manager).
3. **MANDATORY first-action** instruction to run `/ontology-librarian {topic}` in the spawned agent's own session — Hook 15 scans the agent's transcript independently and blocks Edit/Write otherwise.
4. **Git identity** flags (`git -c user.name="..." -c user.email="parametrization+FirstName.LastName@gmail.com"`).
5. **Branch name** matching `{FirstInitial}.{LastName}/{IIII}-{slug}` and **PR target** (typically `deployments/phase-{N}/wave-{M}`).
6. **Cross-Contract rule** reference if the PR is part of a cross-contract cluster (charter `pull-requests.md`).
7. **Charter enforcement reminders** (2 reviewers, CI green before merge, no `--no-verify`, no global/repo git config, `/ontology-librarian` per agent).
8. **Reporting pattern** — who they report to (usually their manager) and when (draft open, CI green, blocker, merge).
9. **/tmp file-race discipline:** When using `--body-file` with `gh issue/pr comment` or `git commit -F`, write the file to an issue#-keyed path (e.g., `/tmp/{issue#}-{purpose}.md`) IMMEDIATELY before the gh/git call — no other tool calls between the Write and the consuming Bash. Hook `block_stale_tmp_message_file` blocks files older than 30s. P3W6 surfaced 3 such blocks in spawned-agent gh-comment flows; this discipline prevents them.

### Orchestrator checklist when spawning a reviewer

Every reviewer-class spawn prompt MUST include, **in order**:

1. **PR + author identity** — the specific PR# and head-SHA being reviewed, the author's name (NOT the reviewer's), and the angle the reviewer is being asked to take (TPM angle, charter/QA angle, domain angle, release coordinator angle, etc.).
2. **MANDATORY first-action** instruction to run `/ontology-librarian {topic}` — Hook 15 scans the reviewer's own transcript and blocks Edit/Write otherwise. Reviewer-class spawns don't typically Edit/Write (they post comments), but the librarian is also load-bearing for understanding what the PR touches.
3. **Throughline-watch block** (per § Reviewer spawn brief — throughline-watch above) — copy-paste the verbatim template block. Default, not per-wave addition (#320).
4. **`Requestor: <reviewer name>` / `Requestee: <PR author name>` / `RequestOrReplied: Approved | ChangesRequested` / `TechDebt:` format** — explicit reminder using the canonical Direction-table form (per `pull-requests.md` § Comment-Based Reviews, post-#372 / PR #375 fix). The brief should embed the verbatim "Use `gh pr comment <PR#> --body '...'` with this format:" template block to prevent W9 PR#349-style cascades from re-emerging (per memory `feedback_spawn_brief_requestor_field_semantics`).
   - TechDebt MUST be in the SAME comment as the verdict — edit-appending after the fact gets the verdict-comment dropped from hook counting (per memory `feedback_verdict_amendment_edit_not_append`).

<!-- Promoted from memory: feedback_techdebt_attestation_literal_line.md (P3W9 retro 2026-05-12, owner-approved 2026-05-13) -->

   **Verbatim verdict-comment template (copy-paste into reviewer spawn briefs):**

   > **Canonical source:** see `pull-requests.md § Review Prompt Template (Mandatory)` for the underlying spec. This block is the spawn-brief view; the `pull-requests.md` template is the verbatim source-of-truth reviewers must follow — plain form, no bold markers, no parenthetical descriptions, no extra fields.

   ```bash
   # Use `gh pr comment <PR#> --body-file <path>` — NOT `gh pr review` (block_gh_pr_review enforces).
   # Write the body to a /tmp file FIRST, then comment in the very next tool call
   # (block_stale_tmp_message_file enforces 30s freshness):

   cat > /tmp/<PR#>-review-<reviewer-firstname>.md <<'BODYEOF'
   Requestor: <reviewer-firstname> <reviewer-lastname>
   Requestee: <PR-author-firstname> <PR-author-lastname>
   RequestOrReplied: Approved
   TechDebt: none

   <verdict body — prose, line comments, throughline observations…>

   ## Throughline observations

   <per § Reviewer spawn brief — throughline-watch>
   BODYEOF

   gh pr comment <PR#> --body-file /tmp/<PR#>-review-<reviewer-firstname>.md
   ```

   > Inline `gh pr comment <PR#> --body "..."` is also valid when no /tmp file is involved; `--body-file <path>` is the required form when the body is written to /tmp first (`block_stale_tmp_message_file` 30s freshness rule applies only when a /tmp file is the source). This reconciles the new block above with `pull-requests.md § Review Prompt Template (Mandatory)` lines 47–53 which use inline `--body "..."` — both are legitimate; flag form follows write-path.

   **Required literal forms (hook-enforced):**
   - The line MUST literally start with `TechDebt:` (plain form; `pull-requests.md § Review Prompt Template` forbids bold markers — `validate_pr_review.py` regex tolerates optional `**` for backward-compat with pre-#420 verdicts, but new briefs MUST use plain form). `## TechDebt` section headers + prose do NOT satisfy the regex.
   - Valid values:
     - `TechDebt: none`
     - `TechDebt: none — addressed inline by fixup commit <sha>`
     - `TechDebt: #15, #16` (when issues were filed pre-verdict)
   - `RequestOrReplied: Approved` (NOT `Reply` — `validate_pr_review` counts Approved-only).

   For a ChangesRequested verdict, swap to:
   ```
   RequestOrReplied: ChangesRequested
   TechDebt: none
   ```
   (TechDebt still required even on ChangesRequested — the regex is unconditional.)

   **Why literal:** P3W9 PR #409 cascade — both reviewers followed the prior prose template that prescribed `## TechDebt\n\n…` section header; `gh pr merge` blocked with `BLOCKED: PR #409 has review(s) missing the mandatory TechDebt: attestation line` at merge time, requiring per-comment PATCH amendments. Sibling pattern to P3W8 Approved-vs-Reply cascade — both fixable by spawning-brief template fixed-literal rewrite.

5. **`gh pr review` vs `gh pr comment` discipline** — explicit reminder NOT to use `gh pr review` (`block_gh_pr_review` enforces; spawn-brief mention prevents the trip).
6. **Read-the-diff-at-HEAD discipline** — `gh api repos/.../contents/<path>?ref=<head_sha>` not local clone (per `pull-requests.md` § Origin > Local Clone for "Still-Has-X" File-Content Claims).
7. **Pre-enumeration discipline** — `grep -c` per file then sum, never `| head -N` (per memory `feedback_no_head_in_surface_enumeration`).
8. **Verdict literal-string requirements** — `RequestOrReplied: Approved` (or `ChangesRequested`), NOT `Reply`. `validate_pr_review` counts Approved-verdict comments only; Reply doesn't gate-count (per memory `feedback_validate_pr_review_approved_not_reply`).
9. **Reporting pattern** — who to report verdict + literal-strings-confirmation to (typically team-lead or the manager who requested the review).

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

<!-- Promoted from memories: feedback_no_head_in_surface_enumeration.md + feedback_pre_spawn_verify_at_origin.md + feedback_pre_spawn_brief_verified_at_head.md (P3W8 retro-pickup #341, 2026-05-10) -->

### Surface enumeration

Pre-spawn briefs that enumerate a multi-file code surface (e.g., "all `actions/checkout@v` sites in this repo", "every place we read `B2_APPLICATION_KEY_ID`", "all workflows that reference `secrets.TARGET_HOST`") MUST count **occurrences, not files**. Three companion disciplines apply.

#### Where to verify — origin head_sha, not local checkout

Run `gh api repos/<owner>/<repo>/git/trees/<head_sha>?recursive=1` (or `gh api .../contents/<path>?ref=<head_sha>`) against the **wave-branch HEAD** before scoping the brief. Local main, local feature branches, and stale clones can all diverge from origin during a multi-implementer wave. Audit-deliverable issue bodies framed as "remove X / sync Y / augment Z / clean up dead-code N" routinely reference paths that don't survive the most recent migration; verifying premises at origin head_sha BEFORE spawning lets the manager scope-block + bounce to TPM rather than spend an implementer cycle discovering the gap.

If premises hold at head_sha: proceed with spawn. If premises fail (target file/path/state doesn't exist as the issue body assumes): scope-block with a comment on the issue (sha + verification command + observed result), tag TPM/scope owner, escalate via `SendMessage`. If premises *over-deliver* (issue body assumes a block that's already cleared, e.g., parent audit table already populated): proceed AND note the unblock in the spawn-request message body so the implementer doesn't redo the look-up.

#### How to count — `grep -c` per file + sum; never `| head -N` the per-file output

```bash
total=0
for f in <file-set>; do
  count=$(grep -cE "<pattern>" "$f")
  [ "$count" -gt 0 ] && echo "  $f: $count" && total=$((total + count))
done
echo "TOTAL: $total"
```

Then a sanity-check pass that reads the un-truncated grep:

```bash
grep -nE "<pattern>" <files>  # full output, scan for missed sites
```

**Do NOT pipe per-file grep output through `head -N` before tallying.** Truncation silently drops sites and produces an under-counted brief that looks complete because the visible output is plausible. The under-count would ship as a scope leak into a follow-up PR if the implementer used the brief as a checklist.

When a consolidated cross-repo audit deliverable exists (TPM-style per-repo target-version table at a parent meta-issue), **cite the audit URL in the spawn brief and treat the audit as authoritative; the manager brief is advisory**. Implementers consult the audit + run their own worktree-side scan via the Hook 15 librarian invocation. The manager-brief enumeration figure is explicitly NOT a checklist cap; if both manager-brief and audit surface counts disagree, the implementer's own worktree scan resolves the conflict and the manager re-runs the enumeration before the next spawn.

#### What caveats apply — per-named-caveat applicability sweep

For every named caveat in the parent audit / charter / kickoff (e.g., `upload-artifact@v4` same-name failure, `actions/github-script@v7` breaking-change, deprecated-flag warnings, version-pin requirements), the manager explicitly rules **applicable vs. non-applicable for THIS repo's surface** before sending the brief. Do not pass caveats through as "be careful" — verify them against the enumerated surface and resolve the ruling in the brief body. Implementer's PR body should mirror the manager's verification table + caveat ruling so reviewers can audit the chain.

#### Severity if violated

- Pre-spawn brief enumerates by file count instead of occurrence count, or pipes per-file grep through `head` before tallying: **moderate** (the under-count ships as scope leak if implementer treats the brief as a checklist; saved only by implementer-side discipline overriding flawed manager input).
- Manager spawns an implementer to "discover the gap" on an audit-deliverable issue whose premises don't hold at head_sha: **moderate** (wastes implementer context; correct response was scope-block + TPM bounce).
- Caveat passed through as "be careful" without applicability ruling: **minor**, **moderate** if the unapplied caveat masks a real breaking-change site.
- Implementer-side override catches a flawed manager brief (positive event): logged in retro as discipline working as designed, no penalty.

#### Worked examples (P3W8)

- **deploy#280 spawn-brief** — Bereket's initial enumeration counted files (14 of 15 workflow files contain `actions/checkout@v4`) instead of occurrences (30 actual sites — `terraform.yml` has 8 alone). `actions/github-script@v7` sample also miscounted (saw lines 82, 130; missed line 174 because `head -10` truncated the per-file output). Aisha's independent worktree-side scan via Hook 15 librarian + `grep -nE` hit all 37 sites and surfaced the gap; Wanjiku's #309 freshness-pass audit independently confirmed `30 + 3 + 4 = 37` across 15 files 2-3 hours earlier and was the canonical cross-reference.
- **Marcia / landing-page#88** — verified 6 call sites at wave-branch HEAD, ruled `upload-artifact` same-name caveat non-applicable (single call site `playwright-report` in single job). Per-named-caveat applicability sweep delivered as designed.
- **data-acquisition#43 + #44 (Dilara)** — issue body said "remove dead-code child hook copies" / "augment stale child copy"; origin verification at head_sha returned 0 entries under `.claude/hooks/`. Pre-spawn head_sha check let the manager re-scope to ADR + parent-side fixture instead of spawning an implementer to discover the gap.
- **isnad-graph hook surface (Anya, W8)** — 4 of 5 hook files 404 at origin; 4 W8 issues scope-blocked pre-spawn instead of consuming implementer time.
- **Maeve / parent#309 unblock** — pre-spawn read of parent#309's existing audit table revealed the block had already cleared; spawned with the unblock noted in the brief body. Positive expression of the same head_sha discipline (catch the *unblock* signal too, not just the *block*).

#### Cross-references

- Companion to `pull-requests.md § Origin > Local Clone for "Still-Has-X" File-Content Claims` — reviewer-class artifact-truth principle; this section is the manager-class pre-spawn analogue.
- Companion to `pull-requests.md § Trust the Artifact, Not the Framing` — same primitive at the PR review layer ("read the diff at HEAD, not the PR-body framing"); this section is the spawn-brief layer ("enumerate the surface at HEAD, not the issue-body framing").
- Source memories: `feedback_no_head_in_surface_enumeration.md` (how to count), `feedback_pre_spawn_verify_at_origin.md` (where to verify), `feedback_pre_spawn_brief_verified_at_head.md` (per-caveat applicability).

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

<!-- Promoted from memory: (none — this section codifies retro proposal #4 sub-section under existing parent rule, ratified at P3W10 retro via PR #441 owner-decided 2026-05-16) -->

### Parent-Orchestrator Implementer Declarations Are Advisory

When a cross-repo meta-issue authored by the parent orchestrator declares **per-child-issue implementers** (e.g., "Linh implements isnad-graph#812, Lucas implements deploy#159"), those declarations are **ADVISORY**. The child-repo manager is the canonical authority for who actually implements a child-repo PR.

#### Why

22 substitutions across 65 W10 PRs (**34%**) showed that parent-declared implementers were systematically overridden downstream. The substitution wasn't an error — child managers correctly applied local roster knowledge (current workload, recent role fit, in-flight cluster cohesion) that the parent orchestrator does not have at meta-issue authoring time. The cost of declaring anyway was twofold:

1. **Retro-time trust-matrix-misattribution risk** — a retro that reads declared-vs-actual without the bulk-acknowledgment context would credit the wrong agent.
2. **Wasted orchestrator effort** — composing per-issue declarations that get swapped out 34% of the time is signal-to-noise loss.

#### How to apply

- At **meta-issue authoring time**, parent orchestrators MAY state SUGGESTED implementers as advisory hints OR omit per-issue implementer names entirely. Both are acceptable.
- **Child managers** assign canonical implementers via spawn briefs in their own child-repo session, applying local roster + workload + role-fit knowledge.
- **Trust-matrix attribution at retro time** follows the **commit identity** (who actually authored the merged commits per `git log --format='%an' <merge-base>..<wave-tip>`), NOT the meta-issue declaration. Retros that compare declared-vs-actual without the bulk-acknowledgment of this rule will misattribute.

#### Relationship to the parent § Child-Repo Implementer Rule

The parent section above governs **WHICH ROSTER** an implementer must come from: the working-repo's roster, Hook 5 enforced. This sub-section governs **WHO HAS AUTHORITY** to make the per-issue assignment within that roster: the child manager, not the parent orchestrator.

The two rules are complementary:
- Parent rule (hook-enforced): implementer's `user.name` must be in working-repo `roster.json`.
- This sub-section (advisory): WHICH specific roster member the child manager picks is the child manager's call, not the parent orchestrator's.

#### Severity if violated

- **Parent orchestrator over-specifying** (declaring per-issue implementers in a meta-issue): **minor** — wasted effort, no hook block, no downstream coupling.
- **Parent orchestrator demanding child manager honor advisory declarations** (e.g., re-spawning the child agent to "use the declared implementer instead"): **moderate** — couples teams across the parent/child boundary, defeats the local-knowledge advantage that produced the 34% substitution rate, and corrupts the working-repo's role-fit signal.

#### Provenance

P3W10 retro PR #441 § Proposed Process Changes #4. 22-substitution evidence (34% of 65 W10 PRs). Owner-adopted 2026-05-16 (PR #444). Sibling memory: `feedback_child_repo_implementer_rule.md` (which the parent § Child-Repo Implementer Rule + Spawn-Brief Verification already supersedes for roster-source rules; this sub-section adds the authority-source clarification).
