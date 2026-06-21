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
- **Repo charters** (each repo's `.claude/team/charter.md`): PRD reference, phases, team_name, deployment details, repo-specific labels

## team_name Convention

| Context | team_name |
|---------|-----------|
| isnad-graph work | `noorinalabs-isnad-graph` |
| Landing page work | `noorinalabs-landing-page` |
| Deploy repo work | `noorinalabs-deploy` |
| Cross-repo coordination | `noorinalabs` |
