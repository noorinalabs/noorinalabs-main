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
| `noorinalabs-landing-page` | Organization landing page | `noorinalabs-landing-page/` |

Each child repo has its own `CLAUDE.md` with repo-specific build commands, architecture, and conventions. Refer to those for repo-specific work.

## Architecture

This repo (`noorinalabs-main`) is a **parent-level git repo that `.gitignore`s child repos**. Child repos are independent git repositories cloned/managed beneath this directory. This gives us:
- Org-wide team config and hooks version-controlled in one place
- Child repos retain full independence (own branches, PRs, CI)
- Cross-repo coordination via the Manager role

## Team Workflow

**All work MUST be executed through the simulated team structure.** No work begins without spawning the team.

- **Charter & rules:** `.claude/team/charter.md`
- **Active roster:** `.claude/team/roster/` (one file per team member with persistent name and personality)
- **Roster lookup (hooks):** `.claude/team/roster.json`
- **Feedback log:** `.claude/team/feedback_log.md`

### Team Composition
| Role | Level | Name | File |
|------|-------|------|------|
| Infrastructure Manager | Senior VP (Executive) | Bereket Tadesse | `roster/manager_bereket.md` |
| Platform Architect | Staff | Weronika Zielinska | `roster/platform_architect_weronika.md` |
| SRE Engineer | Senior | Lucas Ferreira | `roster/sre_engineer_lucas.md` |
| SRE Engineer | Senior | Aisha Idrissi | `roster/sre_engineer_aisha.md` |
| Security Engineer | Senior | Nino Kavtaradze | `roster/security_engineer_nino.md` |
| Observability Engineer | Senior | Nurul Hakim | `roster/observability_engineer_nurul.md` |

### Key Rules
- **Commit identity:** Each team member commits using per-commit `-c` flags with their name and `parametrization+{FirstName}.{LastName}@gmail.com` email — **never** set global/repo git config. See `.claude/team/charter.md` § Commit Identity for the full table.
- **Worktrees** are the preferred isolation method for all code-writing agents
- Manager spawns team members, creates stories/AC from PRD, and owns timelines
- Manager, Platform Architect, and SRE Engineers coordinate to prevent cross-team blocking
- Feedback flows up and down; severe feedback triggers fire-and-replace
- If the Manager receives significant negative feedback from the user, the Manager is replaced
- Team evolves toward steady state of minimal negative feedback

## Developer Tooling & Orchestration

- **gh-cli** is installed and available from the terminal
- **SSH access** is enabled from the terminal
- **GitHub Projects** — project/feature tracking and board management
- **GitHub Issues** — story/task/bug tracking (created by Manager, assigned to team members)
- **GitHub Actions** — CI/CD pipelines, automated tests, linting, deployment
- These three (Projects, Issues, Actions) are the **core orchestration layer** — do not introduce alternative tools for these concerns
- **Branching strategy:** Feature branches named `{FirstInitial}.{LastName}\{IIII}-{issue-name}` (e.g., `F.Okonkwo\0042-setup-docker-compose`) merged to `main` via PR

## Cross-Repo Coordination

When a feature spans multiple repositories:
1. Manager creates a **meta-issue** in the primary repo describing the cross-repo work
2. Per-repo issues are created in each affected repo, linked back to the meta-issue
3. GitHub Project cards track the cross-repo feature as a single unit
4. Manager coordinates sequencing — e.g., backend API before frontend integration

## Shared Conventions

- All repos use **GitHub Flow** (feature branches off `main`, PRs for merge)
- All repos use the same team roster and commit identity system
- Hooks in `.claude/` enforce commit identity, block `--no-verify`, and block `git config` user changes
