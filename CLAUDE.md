# CLAUDE.md — noorinalabs (Organization)

This file provides guidance to Claude Code when working from the parent `noorinalabs-main` directory, which orchestrates all NoorinALabs repositories.

## Organization Overview

**NoorinALabs** is a platform hosting multiple projects related to Islamic scholarly research, computational analysis, and community tools. This parent repository manages shared team configuration, cross-repo coordination, and org-wide conventions.

## Repository Map

| Repository | Description | Path |
|-----------|-------------|------|
| `noorinalabs-isnad-graph` | Computational hadith analysis platform (FastAPI, React, Neo4j) | `noorinalabs-isnad-graph/` |
| `noorinalabs-deploy` | Deployment orchestration (Terraform, Docker Compose, workflows) | `noorinalabs-deploy/` |
| `noorinalabs-design-system` | Shared design system (tokens, components, icons, brand assets) | `noorinalabs-design-system/` |
| `noorinalabs-isnad-graph-ingestion` | Data ingestion pipeline for isnad-graph (Python, PyArrow, Neo4j) | `noorinalabs-isnad-graph-ingestion/` |
| `noorinalabs-landing-page` | Organization landing page | `noorinalabs-landing-page/` |

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

This is the **org-level coordination team** for `noorinalabs-main`. Each child repo has its own team — this team coordinates across repos.

| Role | Level | Name | File |
|------|-------|------|------|
| Program Director | Senior VP (Executive) | Nadia Khoury | `roster/program_director_nadia.md` |
| Technical Program Manager | Staff | Wanjiku Mwangi | `roster/tpm_wanjiku.md` |
| Release Coordinator | Senior | Santiago Ferreira | `roster/release_coordinator_santiago.md` |
| Standards & Quality Lead | Staff | Aino Virtanen | `roster/standards_lead_aino.md` |

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
- **Branching strategy:** Feature branches named `{FirstInitial}.{LastName}\{IIII}-{issue-name}` (e.g., `N.Khoury\0042-update-charter`) merged to `main` via PR

## Cross-Repo Coordination

When a feature spans multiple repositories:
1. Program Director creates a **meta-issue** in `noorinalabs-main` describing the cross-repo work
2. Per-repo issues are created in each affected repo, linked back to the meta-issue
3. GitHub Project cards track the cross-repo feature as a single unit
4. Program Director coordinates sequencing — e.g., backend API before frontend integration
5. TPM tracks cross-repo dependencies and timeline risks
6. Release Coordinator manages deployment sequencing across repos

## Shared Conventions

- All repos use **GitHub Flow** (feature branches off `main`, PRs for merge)
- All repos use the same team roster and commit identity system
- Hooks in `.claude/` enforce commit identity, block `--no-verify`, and block `git config` user changes
- Standards & Quality Lead audits repos for convention compliance
