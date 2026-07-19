# CLAUDE.md — noorinalabs (Organization)

Guidance for Claude Code in the parent `noorinalabs-main` directory. **Noorina Labs** hosts projects for Islamic scholarly research, computational analysis, and community tools; this parent repo owns shared team configuration, cross-repo coordination, and org-wide conventions.

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

Each child repo has its own `CLAUDE.md` — refer to it for repo-specific build commands, architecture, and conventions.

## Architecture

`noorinalabs-main` is a **parent-level git repo that `.gitignore`s child repos** — children are independent git repositories (own branches, PRs, CI) cloned beneath it. Org-wide team config and hooks live here; cross-repo coordination runs through the Program Director.

## Team Workflow

**All work MUST be executed through the simulated team structure.** No work begins without spawning the team.

- **Charter & rules:** `.claude/team/charter.md` · **Roster:** `.claude/team/roster/` (one file per member) · **Roster lookup (hooks):** `.claude/team/roster.json` · **Feedback log:** `.claude/team/feedback_log.md`

### Team Composition (org-level coordination team)

| Role | Level | Name | File |
|------|-------|------|------|
| Program Director | Senior VP (Executive) | Nadia Khoury | `roster/program_director_nadia.md` |
| Technical Program Manager | Staff | Wanjiku Mwangi | `roster/tpm_wanjiku.md` |
| Release Coordinator | Senior | Santiago Ferreira | `roster/release_coordinator_santiago.md` |
| Standards & Quality Lead | Staff | Aino Virtanen | `roster/standards_lead_aino.md` |

### Session team architecture

The harness provides a **single implicit team per orchestrator session** (no `TeamCreate`/`TeamDelete`). Spawned agents do NOT have the `Agent` tool — only the orchestrating instance spawns, passing `team_name: "noorinalabs"`: hub-and-spoke; managers request implementer spawns via `SendMessage`. Cross-repo waves use `team_name: "noorinalabs"` for **every** agent (managers AND implementers across all 7 child repos); per-repo team names apply only to isolated repo-only sessions. Per-repo rosters under `<repo>/.claude/team/roster/` remain canonical for **commit identity, domain ownership, and reviewer pairing**. Full mechanics: [`.claude/team/charter/agents/orchestration-model.md` § Single-Leader Constraint](.claude/team/charter/agents/orchestration-model.md) — read before spawning the team in a new session.

### Key Rules
- **Commit identity:** each member commits with per-commit `-c` flags — their name + `parametrization+{FirstName}.{LastName}@gmail.com` — **never** global/repo git config. Full table: `.claude/team/charter.md` § Commit Identity.
- **Worktrees** are the preferred isolation method for all code-writing agents.
- Program Director spawns team members, creates cross-repo meta-issues, owns timelines, and coordinates with repo-level managers to prevent cross-team blocking.
- Feedback flows up and down; severe feedback triggers fire-and-replace. A Program Director who receives significant negative user feedback is replaced. Team evolves toward minimal negative feedback.

## Developer Tooling & Orchestration

- **gh-cli** and **SSH access** are available from the terminal.
- **GitHub Projects** (boards) + **GitHub Issues** (stories/tasks/bugs, created by the Program Director) + **GitHub Actions** (CI/CD) are the **core orchestration layer** — do not introduce alternative tools for these concerns.
- **Branching strategy:** feature branches named `{FirstInitial}.{LastName}/{IIII}-{issue-name}` (e.g., `N.Khoury/0042-update-charter`) merged to `main` via PR.

### Shell environment: zsh

The dev shell — interactive **and** the agent Bash tool — is **`zsh`**, not bash. Bash-only idioms (`declare -A`, `${!arr[@]}`, unquoted URLs/globs) silently break; default to POSIX-portable constructs, `bash -c '…'` when bash is genuinely required. Do/don't list: [`docs/TOOLCHAIN.md`](docs/TOOLCHAIN.md) § Shell environment, codified in [`ontology/conventions.md`](ontology/conventions.md). Prefer `ast-grep` (invoke as `ast-grep`, never `sg`) over `grep`/`sed` for structural search/replace — TOOLCHAIN.md § Structural & AST tooling. Optional native **LSP** (exact-symbol nav + post-edit diagnostics, ~0 context cost) is available via the committed `code-intelligence` plugin — one-time enable in TOOLCHAIN.md § Native LSP.

### Local Hooks (pre-commit + pre-push)

`.pre-commit-config.yaml` **mirrors `.github/workflows/ci.yml`** so a local commit/push fails fast. Install BOTH hook types once:

```bash
pre-commit install                          # commit-stage hooks
pre-commit install --hook-type pre-push     # push-stage hooks
```

- **commit stage:** `ruff-format`, `ruff-lint` over `.claude/hooks/` + `.claude/lib/` — fast, with `--fix`.
- **push stage:** `mypy` + the `pytest` suite (`.claude/hooks/tests/`, `.claude/lib/tests/`) — the heavy checks, before code leaves the machine.

Keep the ruff `rev` aligned with CI and sibling repos (isnad-graph pins ruff 0.15.11). **Sync-drift gate:** `.claude/lib/pre_commit_ci_sync.py` (CI job) fails the build if a CI-enforced check is not mirrored in `.pre-commit-config.yaml`; run locally: `python3 .claude/lib/pre_commit_ci_sync.py .`. It is the template each child repo wires into its own CI.

**Full local⇄CI parity + no-force (org-wide, mandatory — owner 2026-06-14):** every repo's `.pre-commit-config.yaml` MUST mirror the **complete** CI check-set (tests AND every linter/formatter, type-check, **cspell**, actionlint, gitleaks, drift gate). And **never commit, push, or merge a PR with a known-failing check — even a pre-existing one not caused by your change — without explicit owner permission**; `--no-verify` is blocked, and a red gate is a stop, not a speed bump. Rollout of complete gate enforcement is tracked by [#684](https://github.com/noorinalabs/noorinalabs-main/issues/684) — until it closes, the sync-gate's silence on an unclassified kind (e.g. cspell) is NOT evidence of parity. Canonical rule: [`.claude/team/charter/pull-requests/ci-gates.md` § Full Local⇄CI Tooling Parity + No Force-Merging Failing Checks](.claude/team/charter/pull-requests/ci-gates.md); spawn-brief enforcement: [`agents/orchestration-model.md` § Orchestrator checklist when spawning an implementer](.claude/team/charter/agents/orchestration-model.md).

## Cross-Repo Coordination

When a feature spans multiple repositories:
1. Program Director creates a **meta-issue** in `noorinalabs-main`
2. Per-repo issues are created in each affected repo, linked back to the meta-issue
3. GitHub Project cards track the cross-repo feature as a single unit
4. Program Director coordinates sequencing (e.g., backend API before frontend integration)
5. TPM tracks cross-repo dependencies and timeline risks
6. Release Coordinator manages deployment sequencing across repos

## Bug Report Workflow

When the user reports a bug, broken behavior, or missing feature in conversation, execute the full issue-to-PR lifecycle automatically — no explicit request needed:

1. **File the GitHub issue** — correct repo, validate labels exist first (hook enforced)
2. **Label for the current wave**
3. **Add to the project board** (project 2, `gh project item-add 2 --owner noorinalabs --url <url>`)
4. **Fix the bug** — spawn a team member if needed, work in a worktree
5. **Create a PR** — link it to the issue; charter conventions (2 reviewers, branch naming, commit identity)

This is the default behavior for all bug reports. Filing alone is never sufficient.

## Project Memory

Project memory is **version-controlled at `.claude/memory/`**, NOT the user-space auto-memory directory (cwd-keyed, not git-shareable; a committed CLAUDE.md `@import` is the only zero-setup-on-pull mechanism). The index auto-loads into every session:

@.claude/memory/MEMORY.md

`MEMORY.md` is the always-loaded index (one line per memory); topic files in `.claude/memory/*.md` are read on demand when a line looks relevant.

**Recording a memory (overrides the default auto-memory tool):** create/edit `.claude/memory/<kebab-slug>.md` with the standard frontmatter (`name`, `description`, `metadata.type` = `user` | `feedback` | `project` | `reference`), add a one-line `MEMORY.md` pointer (`- [Title](file.md) — hook`), and **commit it**. Link related memories with `[[other-slug]]`. Never write to the user-space auto-memory path. Update an existing file covering the same fact instead of duplicating; delete memories that prove wrong.

> `.claude/memory/**` is excluded from the markdown/cspell/lychee linters (dense note prose with names, SHAs, `[[wikilinks]]`, Arabic). `session_handoff.md` is gitignored (per-session, machine-local). Each child repo commits its own `.claude/memory/` + `@import` in its own CLAUDE.md — repos do not import across directories.
>
> **Cold-archive tier (`.claude/memory/archive/`):** a genuinely-historical memory can be moved here — it stays git-tracked and grep-able but is **not** always-loaded (no `MEMORY.md` pointer) and is **not** counted by the budget gate (which globs the top-level `*.md` only). The `/wave-retro` decay sweep (`memory_budget.py --staleness`, Step 7.8) surfaces size/age candidates; archiving is a human decision, never automatic.
>
> **Stable cached prefix (keep volatile state out):** `CLAUDE.md` + the `@import`-ed `MEMORY.md` form the always-loaded, prompt-cached context prefix. Volatile per-session state must NOT live inside it (a rewrite invalidates the cache — write ≈ 12.5× read cost — and goes stale). The handoff pointer line is therefore **static**; the volatile handoff summary lives only in the gitignored `session_handoff.md`, and volatile wave/status state is read on demand via the status digest (`wave_status.py digest`, #987), never embedded in the index (#998).

## Ontology

Structured knowledge base in `ontology/` — domain entities, service topology, conventions across all repos. **Canonical entry point (setup, purpose, the full two-layer model, day-to-day usage): [`ontology/README.md`](ontology/README.md).** Operational essentials:

- **Semantic overlay** (`ontology/{domain,services}.yaml`, `conventions.md`, `repos/*.yaml`; tracked by `checksums.json`) is hand-curated. A PostToolUse change-tracker hook updates `checksums.json` on every Edit/Write to it; **`/ontology-rebuild`** reconciles the dirty entries.
- **Structural index** (`ontology/structural/`) is a **generated, gitignored build product** — never hand-edit, never commit, not checksum-tracked; `/ontology-rebuild` never touches it. Regenerate: `PYTHONPATH=.claude/lib python3 -m ontology_gen.aggregate .` (single repo: `PYTHONPATH=.claude/lib python3 -m ontology_gen . --out ontology/structural/`).
- **`/ontology-librarian`** is the read-only reference — staleness check for both layers + context lookup.
- Lifecycle integration (session-start Step 3, wave-wrapup Step 12, wave-retro step 1) is owned by those skills.

### Session start — MANDATORY, NON-NEGOTIABLE

> **CRITICAL: Run `/session-start` as your VERY FIRST action in every new session.**
> Do NOT read the user's message first. Do NOT respond with text first. Do NOT run any other tool first.
> The literal first thing you do is invoke the `/session-start` skill. No exceptions. No "let me just..." first.
> This has been a recurring failure — if you skip this, the user WILL notice and WILL call it out.

The skill runs the full startup protocol (handoff check, team orientation, both-layer ontology freshness, annunaki check, wave/phase orientation, charter freshness — see `.claude/skills/session-start/`). After it reports the status table, THEN address what the user asked.

### Session end (automatic)

A `Stop` hook writes a handoff to project memory after every response (throttled to 5-minute intervals) — git state, open PRs/issues, wave status, ontology staleness; the next session auto-loads it. For a richer handoff with conversational context, run `/handoff` before exiting.

### Before any code changes (advisory)

**Every agent — orchestrator, team member, or one-off — SHOULD run `/ontology-librarian {topic}` before making code changes** (e.g. `/ontology-librarian narrator API endpoints`). Enforcement is an **advisory**, non-blocking PreToolUse `systemMessage` on Edit/Write/NotebookEdit when the librarian was not consulted this session (`enforce_librarian_consulted`, charter `hooks.md` § Hook 15 — advisory because the structural layer is always-current-by-regeneration; the hand-curated overlay still benefits from the nudge). **Spawn briefs:** every Agent prompt SHOULD include a "first action: run `/ontology-librarian {topic}` before any Edit/Write" instruction — the hook scans the agent's own transcript, so the agent must invoke the librarian itself.

## Shared Conventions

- All repos use **GitHub Flow** (feature branches off `main`, PRs for merge)
- All repos use the same team roster and commit identity system
- Hooks in `.claude/` enforce commit identity, block `--no-verify`, and block `git config` user changes
- Standards & Quality Lead audits repos for convention compliance
- **Artifact ownership** (which `.claude/` + ontology artifact class is owned/executes where, meta vs child; collision + create-time-placement rules): [`.claude/team/charter/artifact-ownership.md`](.claude/team/charter/artifact-ownership.md)
