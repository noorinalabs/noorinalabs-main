# noorinalabs

**NoorinALabs** is a platform for Islamic scholarly research, computational
hadith analysis, and community tools. This repository — `noorinalabs-main` — is
the org-level parent that orchestrates the child repos (isnad-graph,
user-service, deploy, design-system, data-acquisition, isnad-ingest-platform,
landing-page) and version-controls the shared team configuration, hooks, and
ontology.

For the full team/workflow model — roster, charter, wave process, commit
identity, ontology, and project memory — see [`CLAUDE.md`](CLAUDE.md). This
README covers only what a fresh clone needs to **install** before it can build,
test, and pass the local hooks.

## Toolchain / Prerequisites

The repos share one toolchain. Install the tools below once; the per-repo
`CLAUDE.md` files list which apply to each child repo. Pinned versions are the
versions our pre-commit and CI enforce — match them so local "clean" equals CI
"clean" (org-wide local⇄CI parity is mandatory; see
[#684](https://github.com/noorinalabs/noorinalabs-main/issues/684)).

After cloning, install the git hooks (both stages):

```bash
pre-commit install                          # commit-stage hooks (ruff)
pre-commit install --hook-type pre-push     # push-stage hooks (mypy, pytest)
```

### Python

The org `.claude/` hooks/lib/skills and the Python child repos (isnad-graph,
user-service, data-acquisition, isnad-ingest-platform) use this set.

| Tool | Purpose | Install |
|------|---------|---------|
| Python 3.x | runtime for hooks, lib, skills, and Python services | <https://www.python.org/downloads/> (or `pyenv install`) |
| uv | fast Python package/venv manager + lockfiles | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| ruff `0.15.11` | Python lint + format (org-canonical pin) | `uv tool install ruff@0.15.11` (or via pre-commit) |
| mypy | static type-check of hooks/lib and services | `uv tool install mypy` |
| pytest | hook, lib, skill, and service test suites | `uv tool install pytest` (usually a project dev-dep) |
| pip-audit | dependency vulnerability scan (isnad-graph, data-acquisition) | `uv tool install pip-audit` |

> ruff is pinned to `0.15.11` org-wide so the same formatter runs locally and in
> CI. Keep the `rev:` in each repo's `.pre-commit-config.yaml` aligned with it.

### JavaScript / TypeScript

The frontend and design-system repos (design-system, isnad-graph frontend,
landing-page) use this set. These tools are declared in each repo's
`package.json` — installing dependencies pulls the pinned versions in, so prefer
the project install over global binaries.

| Tool | Purpose | Install |
|------|---------|---------|
| Node.js (LTS) | JS/TS runtime | <https://nodejs.org/> (or `nvm install --lts`) |
| npm | package manager / script runner | ships with Node.js |
| pnpm | package manager (used where the repo declares it) | `corepack enable && corepack prepare pnpm@latest --activate` |
| eslint | JS/TS lint | `npm install` (project dev-dep) |
| prettier | JS/TS format | `npm install` (project dev-dep) |
| typescript (`tsc`) | type-check / compile | `npm install` (project dev-dep) |
| vitest | JS/TS unit tests (design-system, isnad-graph) | `npm install` (project dev-dep) |
| vite | frontend bundler (isnad-graph, landing-page) | `npm install` (project dev-dep) |
| astro | static-site generator (landing-page) | `npm install` (project dev-dep) |
| playwright | E2E browser tests (isnad-graph) | `npm install && npx playwright install` |

### Cross-cutting docs, lint, and security gates

These run on every repo via pre-commit and the `docs.yml` / `ci.yml` workflows.
Most are provisioned by pre-commit (which downloads pinned hook environments),
so a local `pre-commit run` needs little manual install — the exception is
`shellcheck`, which must be on `PATH` or `actionlint` silently skips its
shell-lint integration.

| Tool | Purpose | Install |
|------|---------|---------|
| pre-commit | local hook framework mirroring CI | `uv tool install pre-commit` (or `pipx install pre-commit`) |
| actionlint `1.7.12` | GitHub Actions workflow lint | pinned pre-commit rev `v1.7.12`; standalone: download the [1.7.12 release binary](https://github.com/rhysd/actionlint/releases/tag/v1.7.12) |
| shellcheck | shell lint (also actionlint's shell backend) | `apt install shellcheck` / `brew install shellcheck` |
| gitleaks `8.24.3` | secret scanning | download the [8.24.3 release binary](https://github.com/gitleaks/gitleaks/releases/tag/v8.24.3) (or via the pinned pre-commit hook) |
| cspell | docs/prose spellcheck | provisioned by pre-commit (`cspell-cli`); standalone: `npm install -g cspell` |
| lychee | internal markdown link check | provisioned by CI; standalone: `cargo install lychee` or the [release binary](https://github.com/lycheeverse/lychee/releases) |
| markdownlint | markdown structure lint | provisioned by the CI action; standalone: `npm install -g markdownlint-cli2` |

> New domain vocabulary that trips cspell goes in
> [`.cspell/project-words.txt`](.cspell/project-words.txt) — add the word, never
> disable the gate.

### Infrastructure

The deploy repo and the containerized services use this set.

| Tool | Purpose | Install |
|------|---------|---------|
| docker + compose | build/run service containers | <https://docs.docker.com/get-docker/> |
| terraform | infrastructure-as-code (deploy) | <https://developer.hashicorp.com/terraform/install> |
| trivy | container image vulnerability scan (deploy) | `brew install trivy` or the [release binary](https://github.com/aquasecurity/trivy/releases) |
| cosign | container image signing (deploy) | `brew install cosign` or the [release binary](https://github.com/sigstore/cosign/releases) |

### Note: the `sg` name collision

On Linux, `command -v sg` resolves to `/usr/bin/sg` — that is **shadow-utils
`sg`** (run a command with a different group ID), **not** ast-grep. The
`ast-grep` binary ships an `sg` alias that collides with this. If we adopt
ast-grep later, invoke it as **`ast-grep`** everywhere (hooks, docs, CI) — a
script or hook that shells out to `sg ...` would silently run shadow-utils
instead of the structural search tool.

> Structural/AST tooling (ast-grep, yq, semgrep, and friends) is **proposed but
> not yet adopted** — it is tracked as a follow-up in
> [#748](https://github.com/noorinalabs/noorinalabs-main/issues/748). This
> README documents only the tools the org already depends on; do not install the
> proposed set on the strength of this file.
