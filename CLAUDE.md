# CLAUDE.md — noorinalabs (Organization)

This file provides guidance to Claude Code when working from the parent `noorinalabs-main` directory, which orchestrates all Noorina Labs repositories.

## Organization Overview

**Noorina Labs** is a platform hosting multiple projects related to Islamic scholarly research, computational analysis, and community tools. This parent repository manages shared team configuration, cross-repo coordination, and org-wide conventions.

## Repository Map

| Repository | Description | Path |
|-----------|-------------|------|
| `noorinalabs-isnad-graph` | Computational hadith analysis platform (FastAPI, React, Neo4j) | `noorinalabs-isnad-graph/` |
| `noorinalabs-user-service` | User/auth/RBAC service — JWT issuer, OAuth, sessions (FastAPI, Postgres) | `noorinalabs-user-service/` |
| `noorinalabs-deploy` | Deployment orchestration (Terraform, Docker Compose, workflows) | `noorinalabs-deploy/` |
| `noorinalabs-design-system` | Shared design system (tokens, components, icons, brand assets) | `noorinalabs-design-system/` |
| `noorinalabs-data-acquisition` | Data source acquisition — scrapers, API connectors, downloaders (Python, PyArrow) | `noorinalabs-data-acquisition/` |
| `noorinalabs-isnad-ingest-platform` | Pipeline processing — Kafka workers for dedup/enrich/normalize/graph-load (planned P2W8) | `noorinalabs-isnad-ingest-platform/` |
| `noorinalabs-landing-page` | Organization landing page (Astro) | `noorinalabs-landing-page/` |

Each child repo has its own `CLAUDE.md` with repo-specific build commands, architecture, and conventions. Refer to those for repo-specific work.

## Architecture

This repo (`noorinalabs-main`) is a **parent-level git repo that `.gitignore`s child repos**. Child repos are independent git repositories cloned/managed beneath this directory. This gives us:
- Org-wide team config and hooks version-controlled in one place
- Child repos retain full independence (own branches, PRs, CI)
- Cross-repo coordination via the Program Director role

## Team Workflow

**All work MUST be executed through the simulated team structure.** No work begins without spawning the team.

- **Charter & rules:** `.claude/team/charter.md`
- **Active roster:** `.claude/team/roster/` (one file per team member with persistent name and personality)
- **Roster lookup (hooks):** `.claude/team/roster.json`
- **Feedback log:** `.claude/team/feedback_log.md`

### Team Composition

This is the **org-level coordination team** for `noorinalabs-main`. Each child repo has its own roster of personas, but every spawned agent in a cross-repo session is a member of the single `noorinalabs` session team — see § Session team architecture below.

| Role | Level | Name | File |
|------|-------|------|------|
| Program Director | Senior VP (Executive) | Nadia Khoury | `roster/program_director_nadia.md` |
| Technical Program Manager | Staff | Wanjiku Mwangi | `roster/tpm_wanjiku.md` |
| Release Coordinator | Senior | Santiago Ferreira | `roster/release_coordinator_santiago.md` |
| Standards & Quality Lead | Staff | Aino Virtanen | `roster/standards_lead_aino.md` |

### Session team architecture

The harness provides a **single implicit team per orchestrator session** — there are no `TeamCreate`/`TeamDelete` tools (an earlier harness exposed them and failed a second `TeamCreate` with "Already leading team"; the current one simply has one implicit team). Spawned agents do NOT have access to the `Agent` tool — only the orchestrating Claude instance can spawn, passing `team_name: "noorinalabs"`. Together these eliminate the "each repo is its own team, managers spawn implementers per-repo" mental model and enforce a hub-and-spoke pattern: the team lead spawns everyone, and managers request implementer spawns via `SendMessage`.

**What this means in practice:**

- Cross-repo waves orchestrated from `noorinalabs-main` always use `team_name: "noorinalabs"` for every agent — managers AND implementers across all 7 child repos.
- Per-repo team names (`noorinalabs-isnad-graph`, `noorinalabs-deploy`, etc.) only apply when a session is opened in isolation in that repo for repo-only work — NOT the common case for wave-kickoff orchestration.
- Per-repo rosters under `<repo>/.claude/team/roster/` remain canonical for **commit identity, domain ownership, and reviewer pairing** — the session team is a logical overlay on top of them.

The full constraint and delegation mechanics (orchestrator checklist, spawn-request protocol, why this is hub-and-spoke and not recursive delegation) live in [`.claude/team/charter/agents.md` § Single-Leader Constraint](.claude/team/charter/agents.md). Read that section before spawning the team in any new session.

### Key Rules
- **Commit identity:** Each team member commits using per-commit `-c` flags with their name and `parametrization+{FirstName}.{LastName}@gmail.com` email — **never** set global/repo git config. See `.claude/team/charter.md` § Commit Identity for the full table.
- **Worktrees** are the preferred isolation method for all code-writing agents
- Program Director spawns team members, creates cross-repo meta-issues, and owns timelines
- Program Director coordinates with repo-level managers to prevent cross-team blocking
- Feedback flows up and down; severe feedback triggers fire-and-replace
- If the Program Director receives significant negative feedback from the user, they are replaced
- Team evolves toward steady state of minimal negative feedback

## Developer Tooling & Orchestration

- **gh-cli** is installed and available from the terminal
- **SSH access** is enabled from the terminal
- **GitHub Projects** — project/feature tracking and board management
- **GitHub Issues** — story/task/bug tracking (created by Program Director, assigned to team members)
- **GitHub Actions** — CI/CD pipelines, automated tests, linting, deployment
- These three (Projects, Issues, Actions) are the **core orchestration layer** — do not introduce alternative tools for these concerns
- **Branching strategy:** Feature branches named `{FirstInitial}.{LastName}/{IIII}-{issue-name}` (e.g., `N.Khoury/0042-update-charter`) merged to `main` via PR

### Shell environment: zsh

The dev environment's shell — interactive **and** the agent Bash tool — is **`zsh`**, not bash. Write zsh-safe commands: bash-only idioms (`declare -A`, `${!arr[@]}`, unquoted URLs/globs) silently break under `zsh`. Default to POSIX-portable constructs; use `bash -c '…'` explicitly when bash is genuinely required. Full do/don't list: [`docs/TOOLCHAIN.md`](docs/TOOLCHAIN.md) § Shell environment, codified as a convention in [`ontology/conventions.md`](ontology/conventions.md) § Shell environment (zsh). For structural code search/replace prefer `ast-grep` (invoke as `ast-grep`, never `sg`) over `grep`/`sed` — see [`docs/TOOLCHAIN.md`](docs/TOOLCHAIN.md) § Structural & AST tooling.

### Local Hooks (pre-commit + pre-push)

This repo ships a `.pre-commit-config.yaml` that **mirrors `.github/workflows/ci.yml`** so a local commit/push fails fast instead of surfacing a lint/type/test error only after a PR is opened (Phase-3 end-state criterion #6 / #327). Install BOTH hook types once:

```bash
pre-commit install                          # commit-stage hooks
pre-commit install --hook-type pre-push     # push-stage hooks
```

- **pre-commit stage (every commit):** `ruff-format`, `ruff-lint` over `.claude/hooks/` + `.claude/lib/` — fast, with `--fix`.
- **pre-push stage (every push):** `mypy` typecheck + the `pytest` suite (`.claude/hooks/tests/`, `.claude/lib/tests/`) — the heavier checks, run before code leaves the machine.

Keep the ruff `rev` aligned with the version CI installs and with sibling repos (isnad-graph pins ruff 0.15.11) so the same tool runs locally and in CI.

**Sync-drift gate:** `.claude/lib/pre_commit_ci_sync.py` is a CI job (`Pre-commit ⇄ CI sync-drift gate`) that fails the build if a check CI enforces (ruff/mypy/pytest/…) is NOT mirrored in `.pre-commit-config.yaml`. Run it locally with `python3 .claude/lib/pre_commit_ci_sync.py .`. This is the machine-enforcement that keeps the mirror from rotting (per `feedback_actionlint_needs_shellcheck` — local "clean" must not diverge from CI). The same gate is the template each child repo wires into its own CI.

**Full local⇄CI parity + no-force (org-wide, mandatory — owner 2026-06-14, [#684](https://github.com/noorinalabs/noorinalabs-main/issues/684)):** every repo's `.pre-commit-config.yaml` MUST mirror the **complete** CI check-set across its commit + push stages — the relevant tests AND every linter/formatter, type-check, **cspell**, actionlint, gitleaks, and drift gate — not a subset. And **never commit, push, or merge a PR with a known-failing check — even a pre-existing one not caused by your change — without explicit owner permission** (`--no-verify` is already blocked; this extends the stance to the *outcome*: a red gate is a stop, not a speed bump). The sync-drift gate must enforce parity *completely*; closing its current blind spot for unclassified kinds (e.g. cspell) and rolling the full hook-set out to every child repo is tracked by #684 — until then, the gate's silence on an unclassified kind is NOT evidence of parity. Canonical rule: [`.claude/team/charter/pull-requests.md` § Full Local⇄CI Tooling Parity + No Force-Merging Failing Checks](.claude/team/charter/pull-requests.md); spawn-brief enforcement is in [`agents.md` § Orchestrator checklist when spawning an implementer](.claude/team/charter/agents.md) (green-before-push item).

## Cross-Repo Coordination

When a feature spans multiple repositories:
1. Program Director creates a **meta-issue** in `noorinalabs-main` describing the cross-repo work
2. Per-repo issues are created in each affected repo, linked back to the meta-issue
3. GitHub Project cards track the cross-repo feature as a single unit
4. Program Director coordinates sequencing — e.g., backend API before frontend integration
5. TPM tracks cross-repo dependencies and timeline risks
6. Release Coordinator manages deployment sequencing across repos

## Bug Report Workflow

When the user reports a bug, broken behavior, or missing feature in conversation, execute the full issue-to-PR lifecycle automatically — no explicit request needed:

1. **File the GitHub issue** — correct repo, validate labels exist first (hook enforced)
2. **Label for current wave** — check which wave is in progress and apply the wave label
3. **Add to project board** — add the issue to the GitHub Project (project 2, `gh project item-add 2 --owner noorinalabs --url <url>`)
4. **Fix the bug** — spawn a team member if needed, work through the fix in a worktree
5. **Create a PR** — link it back to the issue, follow charter conventions (2 reviewers, branch naming, commit identity)

This is the default behavior for all bug reports. Filing alone is never sufficient.

## Project Memory

Project memory is **version-controlled in the repo** at `.claude/memory/`, not in the user-space auto-memory directory. This makes the accumulated state **transferable**: a developer who pulls a branch gets the memory with it, with zero per-machine setup. The index below is auto-loaded into every session via a committed CLAUDE.md import:

@.claude/memory/MEMORY.md

`MEMORY.md` is the always-loaded index (one line per memory); the individual topic files in `.claude/memory/*.md` are read on demand when a line looks relevant.

**Why not the auto-memory feature:** Claude Code's auto-memory lives at `~/.claude/projects/<cwd-dashed>/memory/` — user-space, cwd-keyed (so it fragments across worktrees/child-repo cwds), and **not** git-shareable. Its directory override (`autoMemoryDirectory`) is deliberately **ignored when checked into `.claude/settings.json`** (a committed override could redirect the agent's trusted memory context — a prompt-injection vector), so there is no committed setting that makes auto-memory transferable. CLAUDE.md `@import` of committed files is the only zero-setup-on-pull mechanism.

**Recording a memory (overrides the default auto-memory tool):** create or edit `.claude/memory/<kebab-slug>.md` with the standard frontmatter (`name`, `description`, `metadata.type` = `user` | `feedback` | `project` | `reference`), add a one-line pointer to `MEMORY.md` (`- [Title](file.md) — hook`), and **commit it** so it travels with the branch. Link related memories with `[[other-slug]]`. Do **not** write memories to the user-space auto-memory path — they would not transfer. Before adding, check for an existing file covering the same fact and update it instead of duplicating; delete memories that turn out to be wrong.

> `.claude/memory/**` is excluded from the markdown/cspell/lychee linters (dense append-only note prose with names, SHAs, `[[wikilinks]]`, and Arabic — same call as `feedback_log.md`/`trust_matrix.md`). The Stop-hook `session_handoff.md` is gitignored (per-session, machine-local churn). Per-child-repo memory follows the same self-contained pattern: each repo commits its own `.claude/memory/` + `@import` in its own CLAUDE.md — repos do not import across directories.

## Ontology

The project maintains a structured knowledge base in `ontology/` that captures domain entities, service topology, and conventions across all repos. See [`ontology/README.md`](ontology/README.md) for the canonical entry point — setup, purpose, getting started, and day-to-day usage.

### Three roles

| Role | Type | What it does |
|------|------|-------------|
| **Change Tracker** | PostToolUse hook (Edit/Write) | Auto-updates `ontology/checksums.json` with file hashes on every edit — **of the hand-curated semantic overlay only** (skips the generated `ontology/structural/` layer, #857) |
| **Change Resolver** | Skill (`/ontology-rebuild`) | Reads dirty checksums, updates the **semantic overlay** ontology files + auto-updatable docs (the structural layer is regenerated by its owned generator, not resolved here, #857) |
| **Librarian** | Skill (`/ontology-librarian`) | Read-only reference — staleness check, context lookup |

> **Tracker/resolver scope (#857, #820/C×T2).** The change-tracker hook and `/ontology-rebuild` cover the **hand-curated semantic overlay** (`domain.yaml`, `services.yaml`, `conventions.md`, `repos/*.yaml`, hand-edited `*.md`). The **structural** layer at `ontology/structural/` is **generated** (owned generator #855) and therefore always-current-by-regeneration — it is NOT checksum-tracked and `/ontology-rebuild` never resolves it (regenerate it instead). This same regeneration property is why Hook 15 was softened to advisory (below): structural context is current-by-construction, not stale.

### Session start — MANDATORY, NON-NEGOTIABLE

> **CRITICAL: Run `/session-start` as your VERY FIRST action in every new session.**
> Do NOT read the user's message first. Do NOT respond with text first. Do NOT run any other tool first.
> The literal first thing you do is invoke the `/session-start` skill. No exceptions. No "let me just..." first.
> This has been a recurring failure — if you skip this, the user WILL notice and WILL call it out.

The `/session-start` skill executes all 6 steps automatically:

0. **Handoff check** — read `session_handoff.md` from project memory
1. **Team orientation** — confirm the single implicit `noorinalabs` team (current harness has no `TeamCreate`/`TeamDelete` tools; spawn via the `Agent` tool)
2. **Ontology rebuild** — `/ontology-rebuild` to resolve dirty files
3. **Annunaki check** — `/annunaki` to check for captured errors
4. **Wave/phase orientation** — read `cross-repo-status.json` and project board
5. **Charter freshness** — check `feedback_log.md` for unapplied proposals

After the skill completes and reports the status table, THEN address whatever the user asked.

### Session end (automatic)

A `Stop` hook automatically writes a handoff file to project memory after every response (throttled to once per 5 minutes). It captures git state, open PRs, issues, wave status, and ontology staleness. The next session auto-loads this file at step 0.

For a richer handoff that includes conversational context (what was discussed, decisions made), manually run `/handoff` before exiting — but the automatic version covers the essentials.

### Before any code changes (recommended — hook-advisory as of #857, 2026-06-24)

**Every agent — orchestrator, team member, or one-off — SHOULD run `/ontology-librarian {topic}` before making code changes.** This applies to:
- The orchestrator working directly on code
- Team agents spawned for implementation work
- One-off fixes or changes outside of planned wave work

**Enforcement (advisory, not blocking)**: `enforce_librarian_consulted` PreToolUse hook (charter `hooks.md` § Hook 15) emits an **advisory `systemMessage`** on Edit/Write/NotebookEdit when `/ontology-librarian` was not consulted earlier in the session — it does **not** block the edit. It was a hard block (#150); softened to advisory by #857 because the **structural** ontology layer is now generated/always-current (so the staleness it guarded against no longer exists for that layer), while the hand-curated **semantic overlay** still benefits from the nudge. See `hooks.md` § Hook 15.

**Spawning subagents**: every Agent prompt SHOULD still include a "first action: run `/ontology-librarian {topic}` before any Edit/Write" instruction — the consult remains best practice for loading semantic context, and the hook scans the agent's own session transcript, so the agent must invoke the librarian itself for the advisory to be suppressed.

The query should describe the area being modified (e.g., `/ontology-librarian narrator API endpoints`, `/ontology-librarian design system tokens`).

### Ontology structure

```
ontology/
  checksums.json          # Change tracking for the SEMANTIC OVERLAY only (version-controlled)
  structural/             # GENERATED structural layer (owned generator #855) — NOT checksum-tracked
  domain.yaml             # Org-wide entities & relationships
  services.yaml           # Org-wide service map
  conventions.md          # Org-wide conventions & patterns
  repos/
    isnad-graph.yaml      # Per-repo internals
    user-service.yaml
    landing-page.yaml
    design-system.yaml
    deploy.yaml
    ingestion.yaml
```

### Integration

- `/wave-wrapup` runs `/ontology-rebuild` before closing a wave (step 12)
- `/wave-retro` runs `/ontology-librarian` as a staleness check (step 1)
- The change tracker hook fires on all Edit/Write operations across all repos

## Shared Conventions

- All repos use **GitHub Flow** (feature branches off `main`, PRs for merge)
- All repos use the same team roster and commit identity system
- Hooks in `.claude/` enforce commit identity, block `--no-verify`, and block `git config` user changes
- Standards & Quality Lead audits repos for convention compliance
- **Artifact ownership** (which `.claude/` + ontology artifact class is owned/executes where, meta vs child; collision + create-time-placement rules) is canonicalized in [`.claude/team/charter/artifact-ownership.md`](.claude/team/charter/artifact-ownership.md)
