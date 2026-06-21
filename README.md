# noorinalabs

**NoorinALabs** is a platform for Islamic scholarly research, computational
hadith analysis, and community tools. This repository — `noorinalabs-main` — is
the org-level parent that orchestrates the child repos (isnad-graph,
user-service, deploy, design-system, data-acquisition, isnad-ingest-platform,
landing-page) and version-controls the shared team configuration, hooks, and
ontology.

For the full team/workflow model — roster, charter, wave process, commit
identity, ontology, and project memory — see [`CLAUDE.md`](CLAUDE.md). This
README is the new-clone entry point: what to **install**, what **secrets** to
provide, how to **develop and test**, and how the seven repos fit together.

## Contributing

New contributors — data scientists, developers, and dataset providers — start
at [`CONTRIBUTING.md`](CONTRIBUTING.md), the org-level contribution model.

## Prerequisites

The repos share one toolchain. The canonical, version-pinned inventory — every
tool, who provisions it, the macOS/Linux install line, and the structural-search
tooling — lives in **[`docs/TOOLCHAIN.md`](docs/TOOLCHAIN.md)**. Read that for the
full list; this section is just the fast path to a working clone.

> The dev shell — interactive **and** the agent Bash tool — is **`zsh`, not
> bash**. Write zsh-safe (ideally POSIX-portable) commands; see
> [`docs/TOOLCHAIN.md` § Shell environment](docs/TOOLCHAIN.md) for the do/don't
> list.

**1. Install the essentials yourself** (everything else is bootstrapped per repo
by `uv` / `npm` / `pre-commit`):

| Tool | Why you need it first | Install |
|------|-----------------------|---------|
| `git` + `gh` | clone, branch, and drive issues/PRs/the project board | system pkg · `brew install gh` / `apt install gh` |
| `python3` (3.12+) | runs the `.claude/` hooks, lib, and skills | system · `uv python install` |
| `uv` | Python package manager for every Python repo | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| `node` (LTS) + `npm` | the JS/TS repos (design-system, isnad-graph frontend, landing-page) | <https://nodejs.org/> · `nvm install --lts` |
| `pre-commit` | local hook framework that mirrors CI | `uv tool install pre-commit` · `pipx install pre-commit` |
| `shellcheck` | **must be on `PATH`** or `actionlint` silently skips shell-lint | `brew install shellcheck` · `apt install shellcheck` |
| `docker` + compose | build/run the containerized services | <https://docs.docker.com/get-docker/> |

Pinned versions matter: ruff `0.15.11`, actionlint `1.7.12`, cspell `8.4.0` (and,
across the org's service repos, gitleaks `8.24.3`). Matching them keeps local
"clean" equal to CI "clean" — org-wide local⇄CI parity is the mandated end-state
([#684](https://github.com/noorinalabs/noorinalabs-main/issues/684), whose
rollout — including gitleaks — is still in progress). `pre-commit` provisions the
pinned `ruff`/`actionlint`/`cspell` for you; `mypy`/`pytest` run against your
system Python at pre-push, so install those yourself.

**2. Install the git hooks** (one-time per clone — both stages):

```bash
pre-commit install                          # commit-stage: ruff-format, ruff-lint, actionlint, cspell
pre-commit install --hook-type pre-push     # push-stage:   mypy, pytest suites, memory-budget gate
```

> The commit stage runs fast linters; the push stage runs the heavier
> type-check + test suites so nothing red leaves your machine. Never bypass a
> hook with `--no-verify`, and never push, merge, or commit over a known-failing
> check without explicit owner permission
> ([#684](https://github.com/noorinalabs/noorinalabs-main/issues/684)).

## Environment variables (external to source control)

Secrets and machine-specific endpoints are **never committed**. Each service
repo ships a `.env.example` listing the names it expects; copy it to `.env` and
fill in real values locally (`cp .env.example .env`). In CI the same names are
supplied as GitHub Actions secrets. The names below are grouped by purpose — the
authoritative per-repo list is always that repo's `.env.example`.

> Only **names and purposes** are documented here — no values. Across the org's
> service repos, `gitleaks` scans diffs for leaked secrets; extending that gate
> to every repo (this one included) is the [#684](https://github.com/noorinalabs/noorinalabs-main/issues/684)
> end-state.

**Shell-exported for org tooling and package auth** (export in your `zsh`
profile, or let `gh auth login` manage the token):

| Name | Purpose |
|------|---------|
| `GH_TOKEN` / `GITHUB_TOKEN` | auth for the `gh` CLI — issues, PRs, project-board, and CI's default token |
| `NODE_AUTH_TOKEN` | npm auth to `npm.pkg.github.com` to install `@noorinalabs/design-system` (project `.npmrc` reads `${NODE_AUTH_TOKEN}`) |
| `GH_PACKAGES_TOKEN` | GHCR / GitHub Packages auth for pulling & publishing `@noorinalabs/*` images and packages |
| `GITLEAKS_LICENSE` | optional org license for the `gitleaks` secret-scan gate |

**Per-service `.env` (copied from each repo's `.env.example`):**

| Name(s) | Purpose | Repo(s) |
|---------|---------|---------|
| `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` | Neo4j graph database connection | isnad-graph, data-acquisition, ingest |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `PG_DSN`, `DATABASE_URL` | PostgreSQL connection / DSN | isnad-graph, user-service, deploy |
| `USER_POSTGRES_USER`, `USER_POSTGRES_PASSWORD`, `USER_POSTGRES_DB` | user-service's dedicated Postgres in the compose stack | deploy |
| `REDIS_URL`, `REDIS_PASSWORD`, `USER_REDIS_PASSWORD` | Redis cache / session store | isnad-graph, user-service, deploy |
| `JWT_PRIVATE_KEY`, `JWT_PUBLIC_KEY`, `JWT_ALGORITHM`, `JWT_SECRET` | JWT signing / verification keypair for auth tokens | user-service, deploy |
| `AUTH_GOOGLE_CLIENT_ID` / `_SECRET`, `AUTH_GITHUB_CLIENT_ID` / `_SECRET`, `AUTH_APPLE_*`, `AUTH_FACEBOOK_*` | OAuth provider credentials | user-service, deploy |
| `AUTH_OAUTH_REDIRECT_BASE_URL`, `AUTH_OAUTH_POST_LOGIN_URL`, `AUTH_OAUTH_STATE_TTL_SECONDS` | OAuth redirect / state-cookie configuration | user-service |
| `VITE_USER_SERVICE_ORIGIN` | frontend → user-service auth origin (build-time) | isnad-graph (frontend) |
| `SUNNAH_API_KEY` | sunnah.com hadith API key | isnad-graph, data-acquisition, ingest |
| `KAGGLE_USERNAME`, `KAGGLE_KEY` | Kaggle dataset download credentials | data-acquisition, ingest |
| `DATA_RAW_DIR`, `DATA_STAGING_DIR`, `DATA_CURATED_DIR` | local data-lake stage paths | data-acquisition, ingest |
| `PIPELINE_B2_KEY_ID`, `PIPELINE_B2_KEY`, `PIPELINE_B2_BUCKET`, `PIPELINE_B2_ENDPOINT`, `PIPELINE_B2_REGION` | Backblaze B2 object storage for pipeline data | deploy, data-acquisition |
| `BACKUP_B2_*` | B2 credentials for backups | deploy |
| `INGEST_CHECKPOINT_BACKEND`, `KAFKA_CLUSTER_ID`, `KAFKA_UI_USER`, `KAFKA_UI_PASSWORD`, `KAFKA_UI_READONLY` | ingest pipeline + Kafka / Kafka-UI configuration | isnad-ingest-platform, deploy |
| `BASE_DOMAIN`, `CLOUDFLARE_API_TOKEN`, `HCLOUD_TOKEN`, `TF_STATE_B2_*`, `DEPLOY_SSH_PRIVATE_KEY`, `DEPLOY_REPO_PAT`, `SECRETS_ADMIN_TOKEN` | infra: domain, Cloudflare DNS/CDN, Hetzner Cloud, Terraform remote state, deploy SSH + cross-repo dispatch | deploy |
| `GRAFANA_ADMIN_USER`, `GRAFANA_ADMIN_PASSWORD`, `GRAFANA_ROOT_URL`, `PROM_CONFIG_FILE`, `ALERTMANAGER_CONFIG_FILE`, `SLACK_WEBHOOK_URL` | observability: Grafana, Prometheus/Alertmanager, alert webhook | deploy, isnad-graph |
| `STG_TEST_EMAIL` / `STG_TEST_PASSWORD`, `STG_TEST_USER_EMAIL` / `STG_TEST_USER_PASSWORD` | staging smoke-test login credentials (CI) | deploy |

> Non-secret tunables also live in `.env.example` (e.g. `CORS_ORIGINS`,
> `LOG_LEVEL`, `LOG_FORMAT`, `RATE_LIMIT_*`, the `AUTH_*_TOKEN_EXPIRE_*` /
> `*_IMAGE_TAG` values) — safe defaults, override per environment.

## Development workflow

All work runs through the simulated team and its charter
([`CLAUDE.md`](CLAUDE.md) → `.claude/team/charter.md`). The day-to-day loop:

1. **Pick up the issue.** Work is tracked as GitHub Issues on Project 2 and
   grouped into waves. Before any edit, run `/ontology-librarian {topic}` — a
   hook blocks `Edit`/`Write` until you have.
2. **Branch off a fresh `main`** using the org naming scheme
   `{FirstInitial}.{LastName}/{IIII}-{issue-name}` (e.g.
   `N.Khoury/0042-update-charter`).
3. **Work in a git worktree** — the preferred isolation method, so parallel
   branches never collide in one checkout:

   ```bash
   git fetch origin
   git worktree add ../noor-wt-myfeature -b F.Last/0042-my-feature origin/main
   ```

4. **Commit with per-commit identity** — pass your name/email with `-c` flags;
   **never** set global or repo `git config`, and never `--no-verify`:

   ```bash
   git -c user.name="First Last" \
       -c user.email="parametrization+First.Last@gmail.com" \
       commit -F /tmp/msg.txt
   ```

5. **Green before push.** `pre-commit run --all-files` locally; a red gate is a
   stop, not a speed bump.
6. **Open a PR to `main`** (`gh pr create --base main`), linking the issue with
   `Closes #NNN`. Charter requires **two reviewers**; reviews use the
   `/review-pr` format. Wave-branch merges don't auto-close issues — close them
   when the wave wraps.

Hooks under `.claude/` enforce the commit identity, block `--no-verify`, and
block `git config` user changes, so these conventions fail fast rather than at
review time.

## Running tests

Match the stack of the repo you touched. The **offline unit tier** — tests that
need no Docker, network, or browser — is what must stay green on every commit;
integration/e2e tiers are opt-in and need running services.

**Org root (`noorinalabs-main`) — hook/lib/skill suites** (pure-Python, offline):

```bash
python3 -m pytest .claude/hooks/tests/ .claude/lib/tests/   # same suites the pre-push hook runs
```

These also run at the `pre-push` stage and in the `ci.yml` Pytest job, so a
clean push means a clean CI.

**Python services** (isnad-graph, user-service, data-acquisition, ingest) — `uv`
+ `pytest`, with markers separating the tiers:

```bash
make test                                  # offline unit tier
pytest -m "not integration and not e2e"    # same, explicit
make test-integration                      # needs Docker (Neo4j / Postgres / Redis)
make test-e2e                              # needs the app running (Playwright)
```

**JS/TS** (design-system, isnad-graph frontend, landing-page) — `npm` + Vitest,
with Playwright for E2E:

```bash
npm install
npm run test          # Vitest unit tests
npx playwright install && make test-e2e    # isnad-graph E2E
```

## Repositories & how they depend on each other

Seven repos, each independently versioned and CI'd, cloned beneath this parent.
Per-repo build/test/architecture details live in each repo's own `CLAUDE.md`.

| Repository | Purpose | Stack |
|------------|---------|-------|
| [`noorinalabs-main`](https://github.com/noorinalabs/noorinalabs-main) | org parent — team config, hooks, ontology, cross-repo coordination | Python (`.claude/`) |
| [`noorinalabs-isnad-graph`](https://github.com/noorinalabs/noorinalabs-isnad-graph) | computational hadith analysis platform | FastAPI · React/Vite · Neo4j · Postgres |
| [`noorinalabs-user-service`](https://github.com/noorinalabs/noorinalabs-user-service) | user / auth / RBAC — JWT issuer, OAuth, sessions | FastAPI · Postgres · Redis |
| [`noorinalabs-design-system`](https://github.com/noorinalabs/noorinalabs-design-system) | shared design tokens, components, icons, brand | TS · Vitest · Storybook |
| [`noorinalabs-landing-page`](https://github.com/noorinalabs/noorinalabs-landing-page) | organization landing / marketing site | Astro |
| [`noorinalabs-data-acquisition`](https://github.com/noorinalabs/noorinalabs-data-acquisition) | source acquisition — scrapers, API connectors, downloaders | Python · PyArrow · B2 |
| [`noorinalabs-isnad-ingest-platform`](https://github.com/noorinalabs/noorinalabs-isnad-ingest-platform) | pipeline processing — Kafka workers (dedup/enrich/normalize/graph-load) | Python · Kafka |
| [`noorinalabs-deploy`](https://github.com/noorinalabs/noorinalabs-deploy) | deployment orchestration | Terraform · Docker Compose · GH Actions |

Inter-repo dependencies. The **build/release** edges — npm-package and
container-image triggers that CI reads to sequence builds — are declared in
[`dependencies.yml`](dependencies.yml); the **runtime/architectural** edges (the
user-service auth origin and the data-pipeline flow) are not in that file and are
shown here for the full picture:

```text
  design-system ──(npm @noorinalabs/design-system, on release)──► landing-page
        │                                                          
        └────(npm @noorinalabs/design-system, on release)──► isnad-graph (frontend)
                                                                   ▲
  user-service ──(JWT/OAuth auth origin, VITE_USER_SERVICE_ORIGIN)─┘

  data-acquisition ──(B2 pipeline data, on manifest-changed)──► isnad-ingest-platform
        ▲                                                              │
        └──────(reads Neo4j nodes/edges)───────────────────► isnad-graph (Neo4j)
                                                                       │
  isnad-ingest-platform ──(normalized graph load)──────────────────►──┘

  deploy ◄──(ghcr images, on image-pushed)── isnad-graph, landing-page
         └──(builds/runs all service containers + infra)
```

In short: **design-system** is the upstream UI dependency for **landing-page**
and the **isnad-graph** frontend; **user-service** is the auth provider every
authenticated frontend talks to; **data-acquisition** → **isnad-ingest-platform**
→ **isnad-graph** is the data pipeline (acquire → process → load into Neo4j); and
**deploy** consumes the published container images and owns the infrastructure
for everything.

## Further reading

- [`docs/TOOLCHAIN.md`](docs/TOOLCHAIN.md) — full pinned tool inventory, zsh
  shell guidance, and structural-search tooling.
- [`CLAUDE.md`](CLAUDE.md) — team roster, charter, wave process, commit identity,
  ontology, and project memory.
- [`ONBOARDING.md`](ONBOARDING.md) — new-teammate setup checklist.
- New domain vocabulary that trips `cspell` goes in
  [`.cspell/project-words.txt`](.cspell/project-words.txt) — add the word, never
  disable the gate.
