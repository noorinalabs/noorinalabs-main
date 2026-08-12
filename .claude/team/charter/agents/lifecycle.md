# Agents — Lifecycle, Liveness & Stall Recovery

> Part of the [agents charter index](../agents.md) — re-shelved from `charter/agents.md` for section-level loading (#963). Rules unchanged.

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

> **Harness note (2026-06-16):** the current harness exposes **no `TeamDelete` tool** — the session runs on a single implicit team that is never explicitly deleted. There is no config directory to remove. What remains relevant is **agent lifecycle**: spawned agents keep running until shut down, so you must still wind them down cleanly. The procedure below is the agent-shutdown procedure (the former step 4/5 config-removal steps no longer apply).

1. **Identify running agents** you spawned this session (their names/IDs from the spawn results).
2. **Send shutdown requests to every agent** via `SendMessage` with `{"type": "shutdown_request"}`. Send all in parallel (one message per agent — structured messages cannot be broadcast).
3. **Wait for confirmations** — agents will acknowledge and terminate. Allow ~30 seconds.

**Never skip the shutdown step.** Leaving agents running without shutting them down leaves orphan processes that consume resources and confuse the UI.

Failure to manage agent lifecycle leads to resource exhaustion and duplicate agent confusion. This is a **moderate feedback event** for the orchestrator.

<!-- Promoted from memory: feedback_reuse_idle_teammates_not_clones.md (P3W9 retro 2026-05-12, owner-approved 2026-05-13; pre-promote-on-first-occurrence variant of the enforcement-hierarchy rule) -->

## Agent Liveness Checkpoint <!-- promotion-target: hook -->

P5W2 and P5W3 each produced a zero-output stall invisible until manual intervention: the P5W2 #1024 narrators-500 dispatch produced no branch, no PR, no commit across the full wave; the P5W3 Nneka (#1038) silent-idle on ig#1038 went undetected until the orchestrator took over. Both required a manual nudge to surface. This section encodes the two-part rule that prevents both failure shapes from recurring silently.

### Part (a): TaskCreate per implementer at spawn (mandatory)

Every spawned implementer MUST have a corresponding `TaskCreate` entry at spawn time (subject = repo + issue ref + slug; owner = implementer name). The task list is the live ledger of in-flight wave work. See `/wave-kickoff` § 9b for the specific mechanics and the point in the kickoff flow at which the `TaskCreate` fires.

**Rationale:** Without a task entry, a zero-output stall is invisible at the next `TaskList` sweep — the orchestrator only discovers it via a manual nudge. A tracked task makes the stall surface automatically at the next sweep.

### Part (b): Zero-artifact after 2 idle notifications = auto-flag (mandatory)

An implementer sending an **idle notification** ("working on it", "running tests", "will report back") but producing **no artifact** (no branch pushed, no PR opened, no commit landed) is not evidence of forward progress. The orchestrator MUST apply the following rule:

- **Idle notification 1 (zero artifact):** Re-probe via `SendMessage`. Verify the task exists in `TaskList`; if absent, re-create it and note the gap.
- **Idle notification 2 (still zero artifact):** Auto-flag for takeover or reassignment. A second successive zero-artifact idle notification is NOT "still working" — it is a stall. The orchestrator initiates the takeover mechanic described in § Throttle-Stall Recovery without waiting for a third notification.

**Silent idle is categorically not evidence of forward progress.** The orchestrator MUST NOT infer progress from the absence of a completion message; the artifact (branch, PR, commit) is the only valid evidence of forward motion.

### Relationship to § Throttle-Stall Recovery

§ Throttle-Stall Recovery covers the **mid-task stall**: an implementer has committed or modified files but is stuck on a subsequent step. The trigger is `worktree dirty + no completion` after 30/45/60 min.

This section covers the **zero-artifact stall**: the implementer has produced nothing at all despite sending idle notifications. The trigger is **notification count, not elapsed time**. The two rules are complementary: this section catches the stall earlier (before any artifact exists to assess worktree-dirty state against).

### Severity

- Orchestrator misses a zero-artifact stall because `TaskList` is empty (Part (a) violated): **moderate** — the stall the task list was designed to surface goes unreported.
- Orchestrator infers "still working" from a second zero-artifact idle notification and takes no action (Part (b) violated): **moderate** — wave-level deadline risk; the P5W2 and P5W3 instances were both narrow misses on shipping the keystone deliverable.

### Enforcement (mechanized) <!-- enforced-by: lib/check_agent_liveness.py -->

Both parts are mechanized by `.claude/lib/check_agent_liveness.py` (main#745, follow-up to #735). There is **no clean tool boundary** to hang a PreToolUse hook on — Part (a)'s violation (a spawn with no matching task) is a cross-tool reconciliation of the `TaskList` ledger against the set of spawned implementers, and Part (b) is driven off artifact counts + idle-notification count, not off any single tool's arguments. The deterministic enforcement surface is therefore a checker the orchestrator runs at each **status sweep** (`/retro`, the `/wave-wrapup` open-item pass, or any in-flight-agent review), fed a snapshot it assembles from tools it already calls (`TaskList` + the `gh`/`git` artifact reads):

```bash
python3 .claude/lib/check_agent_liveness.py <snapshot.json>   # exit 1 = a liveness finding
```

The checker emits a `missing-task` finding (Part (a)) when no `TaskList` entry matches an implementer (owner + issue_ref), and a `zero-artifact` finding (Part (b)) — `reprobe` at 1 idle notification, `auto-flag-takeover` at the 2nd — when a spawned implementer has no branch/PR/commit. Reviewers are excluded. See the module docstring for the snapshot schema and the why-a-lib-not-a-hook rationale.

### Provenance

P5W3 retro (2026-06-14) § Proposed Process Change #1 — recurred two consecutive waves. Part (a) (TaskCreate at spawn) was codified via P5W2 retro in `/wave-kickoff` § 9b. Part (b) (zero-artifact threshold) is the P5W3 addition. Both promoted here to charter level so the liveness rule applies across all spawn contexts, not just those initiated via `/wave-kickoff`.

<!-- Promoted from memory: feedback_throttle_takeover.md (takeover mechanic encoded in this section; marker reconciliation via /promotion-audit 2026-06-19) -->

## Throttle-Stall Recovery — Trigger Thresholds <!-- promotion-target: hook -->

`feedback_throttle_takeover` covers the takeover *mechanic* — when a spawned implementer throttle-stalls mid-task with sound partial work, the orchestrator finishes directly with the implementer's per-commit identity (~5min vs respawn's ~15min). This section encodes the **trigger**: when the orchestrator should detect the stall and invoke that mechanic, rather than discovering it reactively hours later.

### The thresholds

For an implementer agent that has gone idle **mid-task with pending uncommitted work**, the orchestrator runs the following cadence (elapsed time measured from the implementer's last message or last observed progress):

1. **First ping at 30min idle.** Status-check message naming the observed state, e.g.: "Where are you? Worktree shows X modified files since session start, no commits yet." The ping both prompts the implementer and timestamps the orchestrator's detection.
2. **Second ping at 45min idle** if the first ping went unanswered.
3. **Auto-takeover at 60min idle** (or 15min after the second ping, whichever is later). The orchestrator initiates `feedback_throttle_takeover`: take over with the implementer's per-commit identity, preserve attribution in the PR body, and record the takeover in the wave decisions log so the retro trust matrix attributes the work to the original implementer.

### Trigger scope — mid-task-with-pending-work only

The 30/45/60min cadence applies **only** to idle that is mid-step on uncommitted work. Concrete signals:

- worktree is dirty (modified files since session start), OR
- branch pushed but no PR opened, OR
- branch not pushed at all despite a committed-and-ready report.

Normal **idle-after-turn-completion** does NOT trigger this — an implementer who has reported a clean handoff and is awaiting the next assignment is not stalled. The distinguishing signal is pending work the implementer was clearly mid-step on, not silence alone.

### Out of scope

- **Reviewer-agent stalls** — reviewers don't typically carry uncommitted work, so the worktree-dirty signal doesn't apply; different detection pattern, not covered here.
- **Agent-tool spawn timeouts** — a different layer (harness-level), not orchestrator-side cadence.
- **Hook enforcement of the timer** — the threshold is orchestrator-side discipline; whether to promote it to a hook follows the general `feedback_enforcement_hierarchy` decision pattern and is deferred (see promotion-target marker above).

### Worked example (W12 origin)

`isnad-graph#931` (starlette security fix): Idris Yusuf spawned 2026-05-30 04:51Z, sent a status update at 05:00Z ("pytest running... will report back as soon as it finishes"), then went idle. The orchestrator did not notice the stall until **14:37Z — 9 hours 37 minutes later** while doing other work; pytest had been stuck at 1 CPU-second the entire time. Throttle-takeover recovered cleanly in ~5min once detected, but the 9+ hour gap was pure waiting — exactly the loss this cadence exists to prevent. Under the thresholds above, the first ping would have fired at ~05:30Z and takeover by ~06:00Z.

### Severity if violated

Reactive-only detection (no cadence, stall discovered at the next state review): **minor-to-moderate** depending on deadline proximity — the work is recoverable via takeover, but the idle gap is dead time that compounds against wave deadlines (especially hard cutovers like the node24 June-2 class).

### Enforcement (mechanized) <!-- enforced-by: lib/check_agent_liveness.py -->

The 30/45/60-min cadence is mechanized by `.claude/lib/check_agent_liveness.py` (main#745, follow-up to #735) — the same status-sweep checker that enforces § Agent Liveness Checkpoint. Per § Out of scope above this is **not** a hook (the trigger is orchestrator-side elapsed-time off artifact state, with no tool event to intercept); the lib is the deterministic surface the orchestrator runs at each sweep. For an implementer that is mid-task **with pending work** (`worktree_dirty`, or branch-pushed-no-PR, or committed-not-pushed), the checker emits a `throttle-stall` finding keyed to `idle_minutes`: `first-ping` (≥30), `second-ping` (≥45), `auto-takeover` (≥60). Idle after a clean handoff (no pending work) and reviewer agents do not trigger. The `auto-takeover` finding directs the orchestrator into `feedback_throttle_takeover` (the mechanic); this section + the lib are the trigger.

### Provenance

P3W12 retro (PR #540) § Proposed Process Changes #1, filed as `noorinalabs/noorinalabs-main#542` and prioritized for W13 per owner direction 2026-05-30. Sibling memory: `feedback_throttle_takeover` (P3W4 Aino-#158 2026-05-05) — the mechanic. This section is the trigger; the split (charter = when, memory = how) follows the `feedback_pre_spawn_verify_file_existence_at_head` (memory) → pre-spawn-discipline (charter) precedent.
