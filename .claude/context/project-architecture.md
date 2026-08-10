# Project Architecture

## Organization

**Noorina Labs** — Islamic scholarly research and computational analysis platform.

- **GitHub Org:** `noorinalabs` (Team plan). Transferred from personal account `parametrization` on 2026-04-04.
- **Org-level GitHub Project:** https://github.com/orgs/noorinalabs/projects/1
- **Non-profit:** Paperwork in progress. All assets will transfer to the non-profit once established.

## Repositories

| Repo | Purpose | Deploy |
|------|---------|--------|
| `noorinalabs-main` | Parent orchestration — team config, charter, hooks, skills | N/A |
| `noorinalabs-isnad-graph` | Hadith analysis platform (FastAPI, React, Neo4j) | VPS via deploy repo |
| `noorinalabs-deploy` | Deployment orchestration (Terraform, Docker Compose, workflows) | Self (GitHub Actions) |
| `noorinalabs-landing-page` | Organization landing page | TBD |

## Parent Repo Pattern

`noorinalabs-main` is a git repo that `.gitignore`s child repos. Child repos are independent git repositories cloned beneath it. This gives:
- Org-wide team config version-controlled in one place
- Child repos retain full independence (own branches, PRs, CI)
- Cross-repo coordination via the Manager role

## Deploy Pipeline

```
noorinalabs-isnad-graph push to main
  → notify-deploy.yml fires repository_dispatch
  → noorinalabs-deploy/deploy-noorinalabs-isnad-graph.yml
  → SSH to VPS → pull source → docker compose up
  → verify-deploy.yml health checks
```

Images published to GHCR via ghcr-publish.yml workflow.

## Infrastructure

- **VPS:** Hetzner CPX41 (8 vCPU, 16GB RAM), Ubuntu 24.04, Ashburn
- **IP:** 87.99.134.161
- **Domain:** isnad-graph.noorinalabs.com
- **DNS:** Cloudflare (noorinalabs.com, .net, .org all registered)
- **Old domain:** how-a-steve-do.com (Squarespace, retiring)
- **Deploy repo on VPS:** `/opt/noorinalabs-deploy`
- **isnad-graph source on VPS:** `/opt/noorinalabs-isnad-graph`

## Charter Split

- **Org charter** (`noorinalabs-main/.claude/team/charter.md`): Team structure, roster, feedback, commit identity, branching conventions, cross-repo coordination protocol
- **Repo charters** (each repo's `.claude/team/charter.md`): PRD reference, phases, deployment details, repo-specific labels

## `team_name` — RETIRED (#1375)

The per-repo `team_name` table that stood here is gone. `team_name` is a **deprecated Agent-tool parameter** — the live schema reads *"Deprecated; ignored. The session has a single implicit team"* — and `validate_no_team_name` (PreToolUse, `Agent` matcher) blocks any spawn that passes one.

There is one implicit team per session, with no name to choose. Which repo an agent works on is expressed by its **worktree and brief**; which repo's *people* it draws on is expressed by the per-repo **roster** under `<repo>/.claude/team/roster/`, which is unaffected and remains canonical for commit identity, domain ownership, and reviewer pairing.
