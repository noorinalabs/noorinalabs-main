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
| Manager | Senior VP (Executive) | Fatima Okonkwo | `roster/manager_fatima.md` |
| System Architect | Partner | Renaud Tremblay | `roster/architect_renaud.md` |
| DevOps Architect | Staff | Sunita Krishnamurthy | `roster/devops_architect_sunita.md` |
| DevOps Engineer | Senior | Tomasz Wójcik | `roster/devops_engineer_tomasz.md` |
| Tech Lead | Staff | Dmitri Volkov | `roster/tech_lead_dmitri.md` |
| Engineer | Principal | Kwame Asante | `roster/engineer_kwame.md` |
| Engineer | Senior | Amara Diallo | `roster/engineer_amara.md` |
| Engineer | Senior | Hiro Tanaka | `roster/engineer_hiro.md` |
| Engineer | Senior | Carolina Méndez-Ríos | `roster/engineer_carolina.md` |
| Security Engineer | Senior | Yara Hadid | `roster/security_engineer_yara.md` |
| QA Engineer | Senior | Priya Nair | `roster/qa_engineer_priya.md` |
| Data Engineer (Lead) | Staff | Elena Petrova | `roster/data_lead_elena.md` |
| Data Engineer | Senior | Rashid Osei-Mensah | `roster/data_engineer_rashid.md` |
| Data Scientist | Principal | Mei-Lin Chang | `roster/data_scientist_mei.md` |
| UX Designer | Principal | Sable Nakamura-Whitfield | `roster/ux_designer_sable.md` |

### Key Rules
- **Commit identity:** Each team member commits using per-commit `-c` flags with their name and `parametrization+{FirstName}.{LastName}@gmail.com` email — **never** set global/repo git config. See `.claude/team/charter.md` § Commit Identity for the full table.
- **Worktrees** are the preferred isolation method for all code-writing agents
- Manager spawns team members, creates stories/AC from PRD, and owns timelines
- Manager, System Architect, and DevOps Engineer coordinate to prevent cross-team blocking
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
