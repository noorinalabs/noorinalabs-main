# Contributing to NoorinALabs

Thanks for your interest in contributing. **NoorinALabs** is a platform for
Islamic scholarly research, computational hadith analysis, and community tools.
This document is the org-level entry point for three kinds of contributor —
**data scientists**, **developers**, and **dataset providers** — and points each
at the conventions that already govern the work.

> **Status: this is an _initial_ contribution model — a starting point for owner
> refinement, not a finished policy.** Throughout, items are tagged
> **[Established]** when they are already enforced by the charter, hooks, or CI,
> and **[Proposed]** when they are a suggested default that still needs an owner
> decision. Open questions an owner needs to settle are collected in
> [§ Open questions for the owner](#open-questions-for-the-owner) at the end.

## Repository layout

`noorinalabs-main` is the org-level parent repository. It version-controls the
shared team configuration, hooks, ontology, and these org-wide conventions, and
it orchestrates seven independent child repositories (each its own git repo,
cloned beneath this one and `.gitignore`d here):

| Repository | What it holds |
|-----------|----------------|
| `noorinalabs-isnad-graph` | Computational hadith analysis platform (FastAPI, React, Neo4j) |
| `noorinalabs-user-service` | User / auth / RBAC service (FastAPI, Postgres) |
| `noorinalabs-data-acquisition` | Data-source acquisition — scrapers, API connectors, downloaders |
| `noorinalabs-isnad-ingest-platform` | Pipeline processing — Kafka workers for dedup / enrich / normalize / graph-load |
| `noorinalabs-design-system` | Shared design system (tokens, components, icons, brand) |
| `noorinalabs-deploy` | Deployment orchestration (Terraform, Docker Compose, workflows) |
| `noorinalabs-landing-page` | Organization landing page (Astro) |

Each child repo has its own `CLAUDE.md` with repo-specific build commands,
architecture, and conventions — read it before working in that repo. The repo
home pages live under <https://github.com/noorinalabs>.

## Getting started

Before you can build, test, or pass the local hooks, install the shared
toolchain. The canonical setup lives in **[`README.md`](README.md) §
Toolchain / Prerequisites** (per-language tables with pinned versions), and the
install-and-examples companion is **[`docs/TOOLCHAIN.md`](docs/TOOLCHAIN.md)**.
At minimum, after cloning install both git-hook stages:

```bash
pre-commit install                          # commit-stage hooks (ruff)
pre-commit install --hook-type pre-push     # push-stage hooks (mypy, pytest)
```

The dev environment's shell — interactive and the agent tool — is **zsh**, not
bash; write zsh-safe (ideally POSIX-portable) commands. See
[`docs/TOOLCHAIN.md`](docs/TOOLCHAIN.md) § Shell environment for the do/don't
list.

For the full team / workflow model — roster, charter, wave process, commit
identity, ontology, and project memory — see [`CLAUDE.md`](CLAUDE.md).

---

## 1. Data scientists

You are contributing analysis, modelling, or ML work — narrator disambiguation,
hadith deduplication, graph metrics, embeddings, topic classification, data
profiling.

**Where the work lives.** Analysis and ML code that feeds the graph lives in
the **`noorinalabs-data-acquisition`** repo, organized by pipeline stage
(`src/resolve/` for narrator NER / disambiguation and hadith dedup,
`src/enrich/` for graph metrics and classification, `src/validate/` for data
quality and profiling). Datasets and experiment artifacts are staged on disk
under that repo's `data/` tree: `data/raw/` (as acquired), `data/staging/`
(normalized Parquet), `data/curated/` (resolved/enriched), and `data/reports/`
(profiling output). Treat large data files as build artifacts, not commit
content — they are produced by the pipeline, not version-controlled.

**How to contribute.** [Established] File or pick up a GitHub issue, then follow
the same branch / PR / review flow as developers (see § 2). ML and analysis
changes are code changes: they go through a worktree, a feature branch, two
reviews, and the full local⇄CI gate set. Data-quality and resolution logic is
test-covered — run the repo's `pytest` suite (and any integration tests) before
pushing; content/threshold changes can shift test assertions.

**Local dev path.** [Proposed] A streamlined local development path for data
scientists — a reproducible notebook/experiment environment that does not
require standing up the full Neo4j + Postgres + Kafka stack — is being designed
in [#775](https://github.com/noorinalabs/noorinalabs-main/issues/775). Until it
lands, follow each repo's `CLAUDE.md` for the local-stack bring-up. This section
will be updated to reference the #775 workflow once it is established; do not
treat the streamlined path as available yet.

## 2. Developers

You are contributing application code, services, infrastructure, hooks, or
tooling. The following are all **[Established]** — enforced by hooks, CI, or the
charter.

**Branch naming.** Feature branches are named
`{FirstInitial}.{LastName}/{IIII}-{issue-name}` — for example
`N.Khoury/0042-update-charter`. The `{IIII}` segment is the zero-padded issue
number. Branch from the current base (see
[`.claude/team/charter/branching.md`](.claude/team/charter/branching.md) for the
wave/deployments-branch model used during active waves) after pulling latest.

**Worktree isolation.** Code-writing work uses an isolated git worktree — no two
contributors share a working directory, which prevents branch contention and
accidental cross-branch commits. Verify you are on your own branch
(`git branch --show-current`) before every commit.

**Commit identity.** Set identity **per commit** with `-c` flags; never modify
global or repo-level git config. Each commit message carries **two**
`Co-Authored-By` trailers (the author and Claude). The team convention is:

```bash
git -c user.name="Firstname Lastname" \
    -c user.email="parametrization+Firstname.Lastname@gmail.com" \
    commit -F /tmp/msg.txt
```

The full identity table and rules are in
[`.claude/team/charter/commits.md`](.claude/team/charter/commits.md). (External
contributors will use their own identity and sign-off — that policy is a
[Proposed] owner decision; see § Open questions.)

**Pull-request flow.** Open a PR with the `gh` CLI against the correct base
branch. The body references its issue with `Closes #N` (full delivery) or
`Part of #N` / `Refs #N` (partial). Every PR requires **two reviews** from
distinct non-authors. Reviews are **comment-based** — `gh pr review --approve`
is blocked (all agents share one GitHub account), so verdicts are posted as
structured comments and validated by a hook. The review format, the two-reviewer
rule, and the mandatory `TechDebt:` line are specified in
[`.claude/team/charter/pull-requests.md`](.claude/team/charter/pull-requests.md).

**Local⇄CI parity (offline-green tests).** The repo's `.pre-commit-config.yaml`
mirrors the **complete** CI check-set across its commit and push stages — every
linter, formatter, the type-checker, the test suite, `cspell`, `actionlint`,
`gitleaks`, and the drift gate. A clean local commit/push should faithfully
predict green CI. Run `pre-commit run --all-files` before pushing. Tests must
pass **offline** — they must not depend on network or third-party uptime.

**Never force past a red gate.** Do not commit, push, or merge with a
known-failing check — even a pre-existing one not caused by your change —
without explicit owner permission. `--no-verify` is hard-blocked. A red gate is
a stop, not a speed bump; the path is fix-forward, not merge-through.

**The hooks.** Local hooks (and PreToolUse hooks in the agent harness) enforce
commit identity, block `--no-verify`, block `git config` user changes, validate
issue labels, and gate the PR-review format. If a hook blocks you, read its
diagnostic — it names the rule and the fix.

## 3. Dataset providers

You are proposing or submitting a new hadith data source — a corpus, an API, a
scraped collection — for the platform to ingest.

**Where it lands.** New sources are added to **`noorinalabs-data-acquisition`**
as a downloader/adapter under `src/acquire/` (one module per source, alongside
the existing `sunnah_api`, `thaqalayn`, `open_hadith`, and others), registered
in the multi-source adapter registry. The adapter contract and registry are
documented in that repo's `docs/adapters.md` and
`docs/adr/002-multi-source-adapter-registry.md`. Acquired data flows
`data/raw/` → parsers → normalized Parquet in `data/staging/`, then through the
resolution and graph-load stages.

**How to propose a source.** [Proposed] Open a GitHub issue in
`noorinalabs-data-acquisition` describing the source before writing an adapter,
covering:

1. **Provenance** — where the data comes from, who maintains it, and a stable
   reference (URL, DOI, citation) to the canonical edition.
2. **License** — the explicit license or terms of use of the source data, and
   whether redistribution and derivative use (graph loading, enrichment) are
   permitted.
3. **Access method** — public API, bulk download, or scrape; rate limits,
   auth requirements, and stability.
4. **Shape & coverage** — collection(s) covered, approximate record count, text
   language(s), and how isnad chains and narrators are represented.

A maintainer reviews the proposal for licensing and provenance fit before an
adapter is built. **Licensing and provenance are gating concerns, not
afterthoughts** — a source whose terms do not permit our use cannot be ingested
regardless of its scholarly value.

**Ingestion entry point.** Once approved, the adapter implements the
`src/acquire/base.py` downloader contract and is wired into the registry; the
ingestion pipeline (`noorinalabs-isnad-ingest-platform`) then dedups,
normalizes, enriches, and loads the normalized output into the graph. See the
data-acquisition `RUNBOOK.md` for running an acquisition end to end.

---

## Code of conduct & charter alignment

All contribution happens under the team charter
([`.claude/team/charter.md`](.claude/team/charter.md) and the topic files in
[`.claude/team/charter/`](.claude/team/charter/)). The charter governs how work
is planned, reviewed, and merged, and its standards — honest status reporting,
review discipline, fixing-forward over forcing past failures, and respecting the
provenance of scholarly source material — are the behavioral expectations for
everyone, contributors included.

[Proposed] A dedicated, contributor-facing `CODE_OF_CONDUCT.md` (community
standards, reporting path, enforcement) is **not yet written**; until it exists,
the charter's collaboration norms apply. Adding one is an owner decision.

## Open questions for the owner

This initial model defers the following to owner refinement:

- **External-contributor identity & sign-off** — the per-commit identity table
  is team-internal; whether and how outside contributors authenticate
  (DCO sign-off, CLA, own email) is undecided. [Proposed]
- **Dataset licensing policy** — the bar for an acceptable source license
  (permitted license list, redistribution requirements, attribution format)
  needs an explicit policy, not case-by-case judgement. [Proposed]
- **Data-scientist local dev path** — tracked in
  [#775](https://github.com/noorinalabs/noorinalabs-main/issues/775); this doc
  updates once it lands. [Proposed]
- **A standalone `CODE_OF_CONDUCT.md`** — see above. [Proposed]
