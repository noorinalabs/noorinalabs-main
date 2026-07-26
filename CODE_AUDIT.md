# Noorina Labs — Org-Wide Code Audit

**Focus:** DRY violations · lines-of-code reduction · runtime & memory efficiency
**Date:** 2026-07-26 · **Auditor:** Aino Virtanen (Standards & Quality Lead) with per-repo audit agents
**Purpose:** working backlog document — each task below is written to be lifted into a Jira issue (tracks = epics, tasks = stories, Track 0 = bugs). Every task carries a measured baseline, an estimated after-state, and a verification method.

Audited at these commits (all `main` unless noted):

| Repo | HEAD | Non-blank LOC | Biggest surfaces |
|---|---|---:|---|
| `noorinalabs-main` (parent, branch `claude/noorinalabs-code-audit-1cdsf8`) | `8e76f31` | 98,923 | Python 59,996 (hooks/lib/skills) · Markdown 25,570 |
| `noorinalabs-isnad-graph` | `b1a6119` | 67,521 | TypeScript 22,542 · Python 20,052 |
| `noorinalabs-user-service` | `6bb15da` | 18,238 | Python 12,943 |
| `noorinalabs-deploy` | `d45e3ce` | 60,411 | Python 19,129 · YAML 14,390 · Shell 10,828 |
| `noorinalabs-design-system` | `384393d` | 10,560 | TypeScript 4,223 · CSS 1,485 |
| `noorinalabs-data-acquisition` | `b4f7159` | 80,680 | Python 65,391 |
| `noorinalabs-isnad-ingest-platform` | `4d2aeb4` | 30,663 | Python 27,088 |
| `noorinalabs-landing-page` | `a3229b5` | 7,339 | Astro 2,115 · TypeScript 1,449 |
| **Org total** | | **374,335** | Python 205,788 · Markdown 60,017 · TS 28,214 · YAML 22,772 |

> LOC figures in the table above are non-blank lines with vendored/generated/lock files excluded. Individual findings below sometimes cite raw `wc -l` figures from the per-repo audits; those are labeled where the difference matters.

---

## 1. Executive summary

1. **The single biggest DRY problem is the data-acquisition ↔ isnad-ingest-platform twin.** The P2W8 split copied the pipeline instead of moving it: ~11.7K duplicated lines by window-scan (12,377 data-acquisition `src/` LOC in files ≥50% similar, plus 5,275 test LOC ≥80%). The fork is stale on the ingest side — data-acquisition is newer in 53 of 61 shared files — and it has already produced a **live production break**: the two repos' Kafka message schemas are incompatible, and the consumer parses outside its DLQ guard, so every producer message crashes the dedup worker (BUG-03).
2. **The domain-model layer is triplicated and actively drifting.** The same 10-module Pydantic `src/models/` package exists in data-acquisition, ingest-platform, and isnad-graph (~2,466 src + ~1,778 test LOC total); `narrator.py` — the core entity — is now only 48% shared between isnad-graph and ingest-platform, and the existing `schema-drift.yml` gate watches the wrong file. These models are the producer→pipeline→consumer wire contract; this is a data-integrity risk, not a style issue.
3. **Org gate tooling is vendored 7–8× and drifting.** `pre_commit_ci_sync.py`, `check_dockerfile_base_pin.py`, `check_fixture_realism.py`, `structural_ontology.py` and their tests total **~10.7K raw lines** for what is logically one ~2.8K-line package. The drift is not hypothetical: landing-page's copy cannot classify `cspell`, so its local⇄CI parity gate is false-green on a real gap (BUG-11), and ingest-platform's copy is 140 lines behind the parent's rewrite.
4. **Workflow YAML is ~15.1K lines org-wide with heavy copy-paste**: a byte-identical `auto-close-issues.yml` in all 8 repos, near-identical `docs.yml` in all 8, `structural-ontology.yml` in 5, a shared `ghcr-publish.yml` skeleton in 4, and stg/prod twin deploy workflows + smoke scripts (93% identical) inside deploy. Zero `actions/cache` usage in deploy (16 uncached `setup-python` steps, 12 uncached `terraform init`s).
5. **The audit surfaced 12 fix-now defects** (Track 0) — including a security-relevant JWT check dropped by a copy-paste (BUG-01), Kafka workers that silently drop backlog on every restart because offsets are never committed (BUG-02), and an API endpoint that streams the entire ~870K-row hadith corpus out of Neo4j on every page mount (BUG-04). Most were found *because* of duplication: a copy drifted and lost a property the original had.
6. **Recommendation: create one new repo, `noorinalabs-common`** (uv workspace publishing three Python distributions: `noorina-schema`, `noorina-pipeline-core`, `noorina-devtools`), plus host org reusable workflows in `noorinalabs-main`. No new JS package is needed — `@noorinalabs/design-system` already exists; its gaps are exports/docs, not architecture (Track H).
7. **Estimated total effect** if all tracks land: **≈ 30–38K LOC removed org-wide** (~8–10% of the org, ~15% of non-Markdown code), the twin-repo and vendored-tooling drift classes eliminated structurally, **≈ 1.5–3h cut from the ~7.5h resolve pipeline run** plus an OOM class fixed, user-visible API wins (facets endpoint ~4 orders of magnitude less transfer), auth-path round-trips halved on admin endpoints, per-tool-call hook latency cut ~85% on its dominant cost, and ~3.5 min of runner time per parent CI run removed.

### Estimated LOC reduction by track

| Track | Est. LOC removed | Nature |
|---|---:|---|
| A — Shared libraries | ~11,300 | models dedup (~2.6K), devtools consolidation (~7.9K raw), utils/arabic (~0.8K) |
| B — Twin-repo resolution | ~14,000–17,700 | delete stale ingest-platform copies (src ~12.4K + tests ~5.3K), freight (1.6K) — overlaps A partially |
| C — CI/CD & workflows | ~3,500–4,100 | reusable workflows, dead workflows, stg/prod parameterization, anchors |
| D — isnad-graph | ~1,400 in-repo | CSS dedup (~0.8K), dead code (~0.4K), misc |
| E — user-service | ~500–600 | auth helpers, OAuth descriptors, test fixtures |
| F — pipeline perf & tests | ~1,500–2,100 | test parametrization (~1.2–1.8K), parser/connector tables (~0.25K) |
| G — parent repo | ~2,400–3,300 | test harness + parametrize (~2K–2.4K), hook/lib boilerplate (~0.4–0.9K) |
| H — design-system & landing-page | ~700–800 | forwardRef factory (~0.3K), icons, landing-page dedup |

Estimates are additive but B overlaps A (the models/pipeline-core extraction is counted once); the honest combined range is **~30–38K**.

---

## 2. Methodology

- **LOC baseline:** custom counter, non-blank lines per language per repo; excludes `.git`, `node_modules`, `dist`/`build`, caches, lockfiles, `ontology/structural/` (generated), `.claude/worktrees/`, binaries.
- **Duplication scan:** normalized 6-line-window hashing (jscpd-style) across `.py .ts .tsx .js .astro .sh .tf .yml .css .sql .cypher` in all 8 repos; comment-only/trivial lines dropped; pairs reported at ≥12 duplicated lines. Alembic migration dirs and `ontology/` content excluded. Cross-checked per-repo with `difflib` line-ratio and, where it mattered, byte-level `diff`/`md5`.
- **Per-repo audits:** 8 audit agents (one per repo) with read-only briefs; every finding requires file:line evidence read from the code, confidence labels, and a stated verification path. Several briefed leads were *refuted* by the agents (e.g. isnad-graph's `user-service.d.ts` is generated output, not hand-written; deploy's `promote.yml` sequencing is deliberate safety) — refutations are recorded so they are not re-flagged later.
- **Runtime/memory estimates** are static-analysis reasoning with stated formulas (e.g. FAISS flat search = n²·d MACs at 853,218 vectors × 384 dims); nothing was executed against production. Every perf task below names the measurement that must gate the change.
- Known already-tracked debt was cross-referenced so this document does not double-file it: `main#1019` (lifecycle consolidation — scoped concretely by G7), `main#1021/#1037/#1014` (P10 tooling debt), `deploy#285` (landing-page dispatch asymmetry), `user-service#84` (DEPLOY_REPO_PAT), wave-27 carry-forwards `da#397/#398/#464/#467`, `main#1062`.

---

## 3. Track 0 — Defects to fix first (bug-type issues)

These are correctness/security/performance defects, independent of any refactor. Most are direct products of duplication drift — fixing them should not wait for the tracks that prevent recurrence.

| ID | Repo | Defect | Severity |
|---|---|---|---|
| BUG-01 | user-service | `dependencies.py:41-47` reimplements JWT decode and drops the `type` claim check — a short-lived `type: "sso"` cookie token is accepted as a Bearer access token on every `CurrentUserDep`/`AdminUserDep` endpoint. Fix: call the existing `services/token.py::decode_access_token`. Add the missing reverse-direction test in `tests/test_sso_forward_auth.py`. | **High (security)** |
| BUG-02 | isnad-ingest-platform | Workers never commit Kafka offsets (`enable_auto_commit=False`, zero `consumer.commit()` calls, no `auto_offset_reset`) → every restart cold-starts at `latest`, **silently dropping in-flight backlog**; also makes the RUNBOOK's SEV-2 "no committed offsets" alert vacuously true. Fix: commit after `checkpoint.mark()` in `workers/lib/runner.py`, pass `auto_offset_reset="earliest"` ×4. | **High (data loss)** |
| BUG-03 | data-acquisition ↔ ingest-platform | Kafka contract broken: producer `RawNewMessage{source,b2_key,content_type,size_bytes,acquired_at,checksum_sha256}` vs consumer `PipelineMessage{batch_id,source,b2_path,timestamp,record_count}` with `extra="forbid"`; `parse_message` sits *outside* the DLQ try (`workers/lib/runner.py:102` vs `:112`) so every message **crashes the dedup worker**. Fix: align producer to consumer shape now; move `parse_message` inside the DLQ try; add a cross-repo round-trip contract test. Durable fix = A4. | **High (pipeline down)** |
| BUG-04 | isnad-graph | `/hadiths/facets` runs `MATCH (h:Hadith) RETURN h.topic_tags` with no LIMIT/aggregation — ~870,663 rows over Bolt per request, on every HadithsPage mount (`src/api/routes/hadiths.py:141`). Fix: Cypher-side `UNWIND coalesce(h.topic_tags,[null])` aggregation (~50 rows) + Redis TTL. | **High (perf, user-facing)** |
| BUG-05 | isnad-graph | TanStack Query key collision: `CollectionsPage` and `TimelinePage` share `queryKey: ['collections']` with different limits (20 vs 100) — Timeline's collection filter silently truncates for 5 minutes depending on navigation order; a third key (`'collections-all'`) duplicates the same request. Fix: put args in the key; one query factory. | Medium (wrong data shown) |
| BUG-06 | isnad-graph | RTL regression from CSS fork: `common.css:46` `text-align: left` overrides the design system's logical `start` at equal specificity — table headers don't mirror for Arabic/Urdu, the product's primary content languages. Fix with D2 (adopt DS rule); add a Playwright RTL assertion. | Medium (product correctness) |
| BUG-07 | user-service | Two divergent session-creation paths: primary login/OAuth/refresh flows use `store_refresh_token` (no session cap, no Redis mirror) while only `POST /api/v1/sessions` enforces `MAX_SESSIONS_PER_USER=10` and mirrors to Redis — cap is unenforced on real logins and `last_active` enrichment silently no-ops for them. Fix per E4. | Medium |
| BUG-08 | main | `session_handoff.py:68` carries one of **7 hardcoded org-repo lists** and has drifted — it omits `noorinalabs-isnad-ingest-platform`, so that repo's open PRs have never appeared in any session handoff. Fix per G6 (single `org_repos` source + test against the CLAUDE.md repo map). | Medium |
| BUG-09 | main | `validate_vps_host.py:110` performs **network I/O at module import** (2 × `urlopen`, timeout 3s) and the PreToolUse dispatcher imports it on every Bash call — up to ~6s added latency cold, plus it writes an untracked cache file into the tracked `.claude/hooks/` tree. Fix: fetch lazily behind the `gh variable set VPS_HOST` prefilter; move cache to tmp; add the missing test file. | Medium (latency + hygiene) |
| BUG-10 | design-system | `package.json` exports `./tokens` and `./components/*` point at dist files the Vite build never emits (no `tokens/index` lib entry) — the exact bug class already fixed once for `./icons`; `docs/usage/tokens.md` actively recommends the broken path; the export validator only warns and skips wildcards. Fix: add the build entry, make `./tokens` CI-critical, check one wildcard instance. | Medium |
| BUG-11 | landing-page | Vendored `pre_commit_ci_sync.py` (217 lines vs parent's 436) cannot classify `cspell` — a check its own `docs.yml` enforces — so the sync-drift gate is **false-green** on a real local⇄CI parity gap (the exact scenario `main#684` warns about). Interim: add the cspell pre-commit hook + re-sync the script; durable fix = A2. | Medium (gate integrity) |
| BUG-12 | landing-page | `404.astro:71-120` re-declares `.btn-primary`/`.btn-secondary` and has drifted (font-size, border, hover, missing `:active`); Astro scoped-style specificity makes the stale copy win. The only regression test for this class visits `/` only. Fix: delete the local block; extend the test to `/404`. | Low-Medium |

Related data-quality defect handled inside Track A/B rather than as a standalone bug: **Arabic normalization has drifted 3 ways** — data-acquisition runs an 8-step normalizer that minted the graph's node keys; isnad-graph and ingest-platform carry a byte-identical stale 5-step copy (missing maqṣūra fold, format-mark strip, Urdu fold), so query-time normalization can disagree with key-minting normalization (silent search misses). See A3/D4.

---

## 4. Track A — Shared libraries (`noorinalabs-common`) — *the common-library decision*

### Decision & rationale

**Create one new repository, `noorinalabs-common`**, structured as a uv workspace that publishes **three separately-versioned Python distributions**:

| Package | Contents (source, today) | Consumers |
|---|---|---|
| `noorina-schema` | The Pydantic domain models + enums (`src/models/`: 32 classes — 15 enums, 8 node, 6 edge, 3 result models) **plus** the shared model-conformance test suite, **plus** the Kafka wire contract (topic constants + `PipelineMessage`) | data-acquisition, ingest-platform, isnad-graph |
| `noorina-pipeline-core` | Org-generic pipeline code: `utils/arabic.py` (786 LOC superset), `utils/{logging,neo4j_client,pg_client,grade}.py`, `acquire/base.py` (262 LOC — streaming download + SHA-256 verify + retry), `resolve/_checkpoint.py` (after F2 fix), `utils/hijri.py`, `exit_codes.py`, ingest's `workers/lib/{runner,object_store,checkpoint_pg,dlq}.py` (after BUG-02 fix) | data-acquisition, ingest-platform (+ isnad-graph for arabic/logging/clients) |
| `noorina-devtools` | CI/pre-commit gate tooling now vendored per-repo: `pre_commit_ci_sync.py` (436), `check_dockerfile_base_pin.py` (217), `check_fixture_realism.py` (158), `lint_skill_graphql_pagination.py`, `check_checksums_ascii.py`, `checksums_io.py`, `structural_ontology` generation (the parent's `ontology_gen/` package, 1,871 LOC, is already packaged with `__main__.py` — the cleanest first target), each exposed as console-script entry points, plus a `.pre-commit-hooks.yaml` manifest | all 8 repos |

**Distribution mechanism:** git-tag pins — `uv add "noorina-schema @ git+https://github.com/noorinalabs/noorinalabs-common@vX.Y.Z"` — zero new infrastructure. Private-repo installs in CI/docker need an org-read token; the `DEPLOY_REPO_PAT` pattern already exists for exactly this. For pre-commit consumption, children replace `repo: local` vendored entries with `repo: https://github.com/noorinalabs/noorinalabs-common` + `rev:` pins (pre-commit clones hook repos itself, preserving zero-setup-on-pull).

**Hard constraint honored:** the parent's PreToolUse/PostToolUse **runtime hooks must stay vendored and dependency-free** — the no-install-on-pull contract is documented and load-bearing (`_framework_config.py:14-16`). `noorina-devtools` therefore covers CI/pre-commit gates and generators only, never the runtime hooks. (This is the parent audit's explicit blocker note.)

**Alternatives considered:** (a) one repo per package — more repos, no atomic cross-package changes; rejected at current org size. (b) wheels as GitHub release assets — adds a publish step without removing the token requirement. (c) the sibling-checkout wrapper pattern (landing-page's `structural_ontology.py` does this deliberately and its docstring explains why) — a valid interim for devtools, but it doesn't version-pin and doesn't serve `schema`/`pipeline-core`. (d) no new JS package: `@noorinalabs/design-system` already covers the JS/CSS shared surface; its problems are export/doc gaps (Track H), and the OpenAPI→TS codegen pattern (already proven in isnad-graph for user-service types) covers API types without a published types package.

### Tasks

**A1 — Decision + scaffold `noorinalabs-common`** · Repos: new · Type: architecture · Effort: M
Ratify the split above (or amend), scaffold the uv workspace with 3 packages, CI (ruff/mypy/pytest mirroring org gates), tag-based release flow, and the token story for CI/docker installs. Acceptance: a sibling repo can `uv add` a tagged package and a pre-commit `repo:` pin resolves.
*Baseline:* 0 shared packages; 4 gate tools × 7–8 copies; 3 model copies. *After:* installable pinned packages. *Verify:* consumer smoke install in one repo's CI.

**A2 — Extract `noorina-devtools` and de-vendor the 7 child copies** · Repos: all 8 · Type: DRY · Effort: L · Depends: A1
Move the parent's Tier-1 generic gate tooling (measured: `ontology_gen/` 1,871 + `pre_commit_ci_sync` 436 + `check_dockerfile_base_pin` 217 + `check_fixture_realism` 158 + `lint_skill_graphql_pagination` 149 + `checksums_io` 170 + `check_checksums_ascii` 114 + `charter_trailer` 165 ≈ 3,280 raw LOC) into the package with console scripts; children consume via pre-commit `rev:` pins + CI `pip install` of the tag. Fixes BUG-11's class permanently (landing-page cspell blind spot; ingest-platform 140-line-stale copy).
*Baseline (measured):* org-wide vendored footprint ≈ **10,703 raw lines** (sources 6,216 + test copies 4,487); drift live in 2 repos. *After:* one canonical copy ≈ 2,800 lines + thin config per repo ⇒ **≈ −7,900 lines** org-wide and the drift class eliminated. *Verify:* each repo's sync-drift gate stays green; `pre-commit run --all-files` parity per repo; the design-system classifier test (`scripts/tests/test_pre_commit_ci_sync.py`) moves upstream with the code.

**A3 — Extract `noorina-schema` (models + conformance suite) with drift reconciliation** · Repos: da, ip, ig → common · Type: DRY/correctness · Effort: L · Depends: A1; coordinate with B
Move the 3 identical modules first (`chain.py`, `grading.py`, `historical.py` — zero risk), then reconcile the 7 drifted ones field-by-field keeping the superset (data-acquisition is newest: it alone has `Attestation`, `DatePrecision`, `_validate_date_bound_ordering`; isnad-graph's `edges.py` is 160 vs 120 LOC). The shared `test_all_models.py` ships inside the package as a conformance suite each consumer runs. Retire isnad-graph's `schema-drift.yml` (it gates `workers/ingest/schema.py`, not the two largest drift surfaces) once the package is the single definition.
*Baseline (measured):* 2,466 model LOC + 1,778 test LOC across 3 repos; `narrator.py` 48% shared ig↔ip; 2 of 3 drift surfaces ungated. *After:* ~950 + ~660 in one package ⇒ **≈ −2,600 LOC org-wide** and the drift class removed rather than detected. *Verify:* run all three repos' current test copies against the extracted package before deleting any; Arrow↔Pydantic boundary pins (`tests/test_parse/test_schemas.py`, `tests/test_resolve/test_schemas.py`) stay green.

**A4 — Kafka contracts into `noorina-schema`** · Repos: da, ip → common · Type: correctness · Effort: S–M · Depends: A1; BUG-03 fixed first
One module owning topic constants + message models + a producer↔consumer round-trip test (`parse_message(RawNewMessage(...).to_json())`). Replaces data-acquisition's hand-mirrored `src/messaging/topics.py` (its docstring already begs for this) and ingest's re-declared literals.
*Baseline:* 379 LOC producer-side + 2 consumer files; contract already broken once (BUG-03); zero import-time protection across the boundary. *After:* one contract module + test; a rename becomes an import error, not a silent prod failure. *Verify:* the new round-trip test; both repos' messaging tests.

**A5 — Arabic normalization: one canonical implementation** · Repos: da → common; ig, ip consume · Type: correctness/DRY · Effort: M · Depends: A1
Promote data-acquisition's 786-LOC `utils/arabic.py` (23 functions, 8-step normalizer incl. `normalize_alif_maqsura`, `strip_format_marks`, `normalize_urdu`, `canonical_surface`, `transliterate`) as the only implementation; its 591-LOC test + fuzz suite moves with it. Delete the stale 129-LOC copies (ig's is **dead** — zero `src/` importers — and byte-identical to ip's live one).
*Baseline (measured):* 3 copies (786/129/129); serving-side normalizers missing 3 folds vs the key-minting normalizer. *After:* **≈ −690 LOC** org-wide (incl. ig's dead copy + tests, see D4) and search/lookup normalization becomes provably the function that minted the keys. *Verify:* consumer round-trip test — `normalize_arabic(query)` matches a real canonical id; existing 21-assertion suite moves with the module.

**A6 — `noorina-pipeline-core` remaining utilities** · Repos: da, ip, ig → common · Type: DRY · Effort: M–L · Depends: A1, B1
`logging.py` (96–100% identical ×3), `neo4j_client.py` (fold the F5 session-hoisting fix in at extraction), `pg_client.py` (fold isnad-graph's pooling fix, D6), `acquire/base.py` (100% identical ×2), `_checkpoint.py` (after F2), `hijri.py`, `exit_codes.py`, ingest's generic worker harness (`workers/lib/runner.py` 149 LOC — extract after BUG-02 fix). Unify the two unrelated B2/S3 layers (da's rclone-subprocess `publish_parquet.py` vs ip's boto3 `object_store.py`) behind one client.
*Baseline (measured):* ≈ 4,400 extractable LOC in data-acquisition alone; utils triplicated (~700 LOC in siblings). *After:* single copies; each consumer −several hundred LOC. *Verify:* per-module suites move with the code; integration tests in consumers.

**A7 — OpenAPI→TS type generation as the standard API-boundary pattern** · Repos: isnad-graph (first), reusable workflow in C · Type: DRY/correctness · Effort: S–M
isnad-graph already has the org's best pattern for *cross-repo* types (committed user-service OpenAPI snapshot → `openapi-typescript` → `git diff --exit-code` CI gate) while hand-mirroring its *own* backend's 30 models in `frontend/src/types/api.ts` (357 LOC, 30/31 field-sets identical, comments duplicated verbatim; past incidents #1024/#1046). Emit this repo's own `/openapi.json` snapshot and generate. Generalize the gate as a reusable workflow (C2 family) for any repo consuming a sibling's API.
*Baseline:* 357 hand-maintained LOC, zero drift detection on the intra-repo boundary. *After:* generated file; drift class closed by the same proven gate. *Verify:* `npx tsc --noEmit` (already in CI) + the new drift step.

---

## 5. Track B — Twin-repo resolution (data-acquisition ↔ isnad-ingest-platform)

**Ground truth established by the audits:** ingest-platform is a **stale fork** of the pipeline (data-acquisition newer in 53/61 shared files; every fix since the fork — da#77, #139, #175, #177, #268, #272, #282, #333, #353, #355, #373, #376, #427 — is absent from ip). Ingest-platform's genuinely-own value is its streaming layer (`workers/`, 4 Kafka workers + lib) and its operator control plane (`src/api/` 785 LOC + `src/pipeline/{reset,reprocess,metrics}` 1,154 + `stages.py`). Its worker paths *actually execute* only 32 files / 4,287 lines of `src/`; **43 files / 8,906 lines are never touched by any worker** (import-graph-verified), most of it live only via the copied batch-CLI path that duplicates data-acquisition.

**Sequencing guard:** the P9.2 re-cut cutover (`main#978`) runs the data-acquisition resolve path. Do not move/delete `resolve/`/`graph/` code until the cutover completes; freight deletion in ingest-platform (B2) is safe immediately because nothing in the worker path imports it.

**B1 — Ratify canonical homes per package** · Repos: da, ip · Type: architecture · Effort: S
Adopt the audit's package-by-package map: data-acquisition canonical for `acquire/ parse/ resolve/ graph/ enrich/`; ingest-platform keeps `workers/ src/api/ src/pipeline/{reset,reprocess,metrics,stages}`; `models/ utils/ messaging/` → `noorinalabs-common` (A3–A6). Two fold-don't-pick files: `pipeline/audit.py` (fold ip's `_collect_caller_hints` ~10 LOC into da's failure-tolerant version) and `parse/identity.py` (**keep da's fail-fast policy; ip's silent `_collapse_double_corpus` repair must not merge back** — it would defeat the da#355 producer gate).
*Verify:* decision recorded (ADR); B2/B3 reference it.

**B2 — Delete confirmed dead freight from ingest-platform** · Repos: ip · Type: LOC · Effort: S–M · Depends: B1 (not on #978)
`src/acquire/` (10 files / 1,266 raw lines) + `tests/test_acquire/` (299) are unreachable from workers even transitively and belong to the sibling by the org's own P2W8 decision; plus the `make acquire` target, `_cmd_acquire` CLI leg, and acquisition-only config (`SUNNAH_API_KEY`, `KAGGLE_*` in `.env.example` + `Settings`).
*Baseline (measured):* 1,565 dead lines + config surface. *After:* **−1,565 LOC**; `_cmd_pipeline` updated. *Verify:* ip test suite; import-graph re-run shows no new orphans.

**B3 — Replace ingest-platform's copied pipeline packages with dependencies** · Repos: ip (deletion), da (unchanged), common · Type: DRY · Effort: XL · Depends: A3–A6, B1, **post-#978** for resolve/graph
Delete ip's stale copies of `parse/ resolve/ enrich/ graph/` and the mirrored test trees; workers and batch-CLI import from `noorina-pipeline-core`/da-published packages instead. Reconcile the only bidirectional file (`cli.py` — da's prune/migrate cmds vs ip's reset/control-plane cmds are non-overlapping).
*Baseline (measured):* 12,377 da src LOC ≥50% duplicated into ip; 5,275 test LOC ≥80%; 22 of 52 same-path test files byte-identical. *After:* **≈ −12.4K src + −5.3K test LOC removed from ip**; single-source pipeline. *Verify:* ip worker integration tests + da's suite unchanged; e2e `scripts/e2e_pipeline_run.py`.

**B4 — Dependency slimming + lazy imports in workers** · Repos: ip · Type: memory/efficiency · Effort: S–M
Drop acquisition deps (`kaggle`, `beautifulsoup4`, `lxml`) after B2. Make `src/{models,parse,utils}/__init__.py` lazy (PEP 562) — today eager re-exports force **~3,210 unused lines including the `neo4j` driver and `psycopg` into dedup/normalize worker containers** that never touch either; `src/resolve/__init__.py` already demonstrates the correct lazy pattern in-repo.
*Baseline (measured):* dedup worker always-executes 1,389 lines for a 241-line functional need; normalize 3,989 for 452. *After:* import weight ≈ functional need; smaller images, faster cold start, no cross-module import blast radius. *Verify:* import-graph script re-run (preserved in the audit artifacts); worker smoke tests.

**B5 — One worker image + one entrypoint factory** · Repos: ip · Type: DRY · Effort: S–M
Point the 4 local-dev compose services at the existing top-level multi-stage Dockerfile (prod already does this), differentiate by `command:`, delete the 4 per-worker Dockerfiles (~95% identical); add a `build_kafka_worker(settings, processor)` factory in `workers/lib/` — the 3 pure-consumer `main.py`s are ~85% identical wiring around 5 per-worker values.
*Baseline (measured):* 5 Dockerfiles / 398 lines; 272 lines of `main.py` wiring. *After:* **−272 Dockerfile lines**; main.py wiring 272 → ~95–115; future consumer-construction changes (e.g. BUG-02) edit one place. *Verify:* compose build + worker e2e; `diff` of rendered compose.

**B6 — Share the byte-identical batch↔streaming domain rules** · Repos: ip (+da later) · Type: DRY/correctness · Effort: S
`_classify_pair`/`_is_cross_sect`/sect frozensets and `TOPIC_LABELS`/`MODEL_NAME`/`BATCH_SIZE`/`MIN_TEXT_LENGTH` are byte-identical today between `src/` batch modules and `workers/` processors ("ported" per their own docstrings) — extract to one module each (`dedup_rules.py`, `topic_taxonomy.py`) while the move is still mechanical; also make `workers/enrich/processor.py` read `TOPIC_LABELS` from settings instead of its third hand copy. Neo4j MERGE-generation unification (batch `src/graph/` 1,616 LOC vs `workers/ingest/processor.py` 549) is a **design decision**, not a mechanical move — file separately after B3.
*Baseline:* ~40 duplicated rule lines + a 3rd taxonomy copy; drift-exposed thresholds in a domain where silent batch/streaming mismatch is hard to notice. *Verify:* both paths' tests import the shared modules.

---

## 6. Track C — CI/CD & workflow deduplication

**Hosting decision:** publish org reusable workflows from `noorinalabs-main` (already the org-config home; requires flipping the repo's Actions access setting to "accessible from repositories in the organization"). A dedicated `.github` repo is the conventional alternative — acceptable; decide in C1 and reuse for all of C2–C4. Org workflow baseline: **≈ 15.1K YAML lines** (deploy 9,798; isnad-graph 1,480; main 766; ingest 745; user-service 623; design-system 591; landing-page 579; data-acquisition 526).

**C1 — `auto-close-issues.yml` → one reusable workflow** · Repos: all 7 children + main · Effort: S
Byte-identical in all 8 repos (verified `diff -q` across the 7 children plus a parent↔child `cmp`; 35 lines each = 280 org-wide).
*After:* 1 × ~40-line `workflow_call` + 8 × ~8-line callers ⇒ **≈ −175 lines** and one maintenance point. *Verify:* trigger a close in one repo per caller.

**C2 — `docs.yml` → reusable with inputs** · Repos: all 8 (deploy's diverges most) · Effort: M · Depends: C1 host decision
5 structurally-identical jobs (markdownlint, cspell, linkcheck, config-lint, actionlint, sync-gate) hand-copied with only file-glob/skip-prefix deltas (ds↔lp diff = 54 lines of mostly comments; policy changes today require 7 coordinated edits — e.g. bumping the pinned cspell action SHA).
*Baseline (measured):* 1,698 lines org-wide (raw `wc -l` across the 8 files). *After:* ~300-line reusable + 8 × ~15–25-line callers ⇒ **≈ −1,200 lines**. *Verify:* per-repo runs green with unchanged check semantics; sync-gate kind classification unaffected (A2 coordinates).

**C3 — `ghcr-publish.yml` → reusable build/push/dispatch** · Repos: ig, us, da, ip · Effort: M
Shared skeleton (build, GHCR push, notify-deploy dispatch) across 4 repos, 919 lines total (ig 280, us 209, da 133, ip 297); per-repo deltas = image matrix + dispatch event-type. Fold in the known asymmetries deliberately (landing-page intentionally has no sender — `deploy#285`).
*After:* ~350-line reusable + thin callers ⇒ **≈ −490 lines**; dispatch contract change becomes one edit. *Verify:* stg deploy dispatch fires per repo (ontology `cross_repo_dispatch_contracts` updated once).

**C4 — `structural-ontology.yml` → reusable + devtools console-script** · Repos: 5 children · Effort: S · Depends: A2, C1 host decision
5 × ~91–99-line near-identical workflows regenerating the gitignored structural index.
*After:* 1 reusable + callers ⇒ **≈ −360 lines**, and the generator version is pinned via `noorina-devtools` instead of 7 drifting `structural_ontology.py` copies (161–579 lines each — deploy's has tripled in size vs data-acquisition's). *Verify:* generated index byte-comparison per repo pre/post.

**C5 — deploy: extract the stg/prod post-rollout tail** · Repos: deploy · Effort: M
`deploy-stg.yml`/`deploy-prod.yml`: the 4 post-rollout SSH steps (Converge → Verify health → Reassert admin → Seed QA user) are ~98% identical after label normalization (212/207 lines per side) plus a byte-identical 32-line secrets block. The team already extracted the first half (`write-deploy-env` composite) — this is the missing second half. Converting the whole tail to a `workflow_call` job also unlocks `secrets: inherit` (composite actions can't).
*Baseline (measured):* ~464 duplicated lines of 983 combined. *After:* one composite/reusable (~180–220) + 2 thin callers ⇒ **≈ −200 to −250 lines**; single edit point for health-poll/QA-seed changes. Includes the ~13×-copied container-health-poll loop (~150–190 lines) as a parameter. *Verify:* actionlint; expanded-step diff; stg `workflow_dispatch` rehearsal.

**C6 — deploy: merge the smoke-test twins** · Repos: deploy · Effort: S
`verify_stg_smoke.sh`/`verify_prod_smoke.sh`: 919 combined lines, stripped-code delta = **19 lines** (3 URLs, one budget constant, scratch-file name, header strings). Parameterize into one `verify_smoke.sh` (env-var driven, matching its own override convention).
*After:* ~280–310 lines total ⇒ **≈ −600 lines**; drift becomes impossible instead of humanly-reverified. *Verify:* shellcheck (already CI-gated); byte-diff `$SMOKE_REPORT` output per env against the old scripts.

**C7 — deploy: template the observability config twins** · Repos: deploy · Effort: S–M
`prometheus.{stg,prod}.yml` are **100% code-identical** after hostname normalization (60 code lines each); `alertmanager.{stg,prod}.yml` differ by 6 lines. The repo already ships the fix pattern (Caddyfile `{$BASE_DOMAIN}` env-templating); Prometheus/Alertmanager need an `envsubst` render step since they lack native env interpolation.
*Baseline:* 394 combined lines. *After:* 2 templates ⇒ **≈ −250 lines** and structural-identity guaranteed. *Verify:* `envsubst` render diffed byte-for-byte vs current files; `promtool check config` / `amtool check-config`.

**C8 — deploy: terraform.yml composites + caching** · Repos: deploy · Effort: S–M
(a) Cloudflare preflight+discovery duplicated verbatim between plan/apply jobs (~70 lines) and the PR-comment step tripled (~42) → 2 composite actions (**≈ −60 lines**); the Hetzner matrix is already correct — don't touch. (b) **Zero `actions/cache` repo-wide**: 16 `setup-python` steps (none with `cache: pip`), 10 ad-hoc pip installs, 12 uncached `terraform init`s (no `TF_PLUGIN_CACHE_DIR`) → add `cache: pip` + a pinned `requirements-ci.txt` + provider-plugin cache keyed on `.terraform.lock.hcl`. Docker layer caching verified **not applicable** here (this repo pulls, it doesn't build).
*After:* ~5–10s × 10 pip sites and 5–20s × 12 init sites per run of billed minutes, compounding on every PR touching `terraform/**` or Python. *Verify:* cache-hit annotations + wall-clock delta over two consecutive runs.

**C9 — main: collapse the 7 single-script CI gate jobs + ruff pair** · Repos: main · Effort: S · **Caveat: branch protection**
`ci.yml`: 7 jobs are an identical 6-line runner+checkout+setup-python preamble around one `python3 .claude/lib/<script>.py .` (~25–40s VM overhead each, ~3.5 min/run total); `lint`/`format` are byte-identical except the ruff subcommand.
*After:* one `gates` job with named steps + one `ruff` job ⇒ **−90 YAML lines, −6 runner allocations, ≈ −3 min wall-clock per CI run**. Check-run names change: update `.github/branch-protection/SPEC.md` required checks in the same PR and re-verify the `pre_commit_ci_sync.py` kind-mapping stays classified. *Verify:* sync-gate green; actionlint; branch-protection spec updated atomically.

**C10 — deploy: YAML anchors + one-shot resource limits** · Repos: deploy · Effort: S
Compose prod file already proves the anchor pattern (`x-logging` used 33×) — extend to the 9+ repeated healthcheck cadence tuples (~47 lines) and rotation-inventory profile groups (18 of 32 entries share identical field profiles ⇒ ~70 lines); one 11-line promtool assertion block is copied 3× (~19 lines). Add missing `deploy.resources.limits` to the 3 one-shot services (29/32 have them).
*After:* **≈ −120 lines** + fleet-wide cadence changes become one edit. *Verify:* `docker compose config` rendered-diff must be byte-identical (anchors are authoring-time only); `yaml.safe_load` equality for the inventory; promtool test run.

**C11 — deploy: delete the two dead legacy workflows** · Repos: deploy · Effort: S
`deploy-isnad-graph.yml` + `deploy-landing-page.yml` (248 lines): their own removal condition (`deploy#86`, blocker `deploy#156`) verified **closed** via the GitHub API ~8 weeks ago; `verify-deploy.yml` confirms nothing depends on them. Execute the reference-removal manifest already staged in `docs/runbooks/decommission-old-prod-vps.md` (3 stale docs + 1 dangling `paths:` filter in `cold-rebuild-dryrun.yml:88`).
*After:* **−248 lines** + docs truthful again. *Verify:* actionlint; repo-wide search shows comment-only references remain.

**C12 — deploy: shared shell helper library** · Repos: deploy · Effort: S
`log()` reimplemented in 7 scripts with **already-drifted behavior** (stdout vs stderr, different arg contracts, 2 timestamp formats); `pass()`/`fail()` in 5 with 3 counter conventions — the exact drift class the repo's own memory log has burned on twice. The repo already sources shared libs (`compose_project.sh`, `scratch.sh`) — extend the same discipline: `scripts/lib_log.sh` (+ `wait_for_healthy()` for the shell-side poll loops), with deliberate, renamed exceptions where stderr/GHA-annotation behavior is intentional.
*Baseline:* ~55 drifted helper lines across 9 files (+ shell-side poll copies). *After:* one ~25-line lib + `source` lines; behavior variance becomes explicit. *Verify:* existing `scripts/tests/*` assert on stdout/stderr content — they are the regression net.

---

## 7. Track D — isnad-graph (API + frontend)

**D1 — Facets endpoint: aggregate in Cypher + cache** · Type: perf (fixes BUG-04) · Effort: S
`UNWIND coalesce(h.topic_tags,[null]) AS tag RETURN tag, count(*)` preserves the uncategorized-bucket semantics the in-code comment defends; result is corpus-invariant → Redis TTL keyed on reload marker.
*Baseline:* ~870,663 rows/request over Bolt; multi-second p99; unbounded under concurrency. *After:* ~50 rows; ~4 orders of magnitude less transfer; ~0 steady-state with cache. *Verify:* `tests/test_api/test_hadiths.py` (#1061/#1062 regression cases pin the two behaviors).

**D2 — Delete the design-system CSS fork** · Type: DRY (fixes BUG-06) · Effort: M · Pairs with H1
102 of `common.css`'s 159 rules are byte-identical to DS CSS the app already `@import`s; 4 forked (adopt DS versions — includes the RTL fix); 53 genuinely local stay under a scoped header. Also delete the stale `@source inline` mirror in `theme.css` the DS docs explicitly say to remove, and bump the pin off `0.0.5-wave4.0`. The remaining 288 "novel" lines implement the badge/btn/form classes the DS *documents but never shipped* — deleted after H1 ships them.
*Baseline (measured):* `common.css` 1,184 lines; 802 covered verbatim by shipped DS; 1 live RTL defect. *After:* **≈ −780 LOC now, −288 more after H1**; smaller bundle; DS fixes stop being silently shadowed. *Verify:* Playwright RTL assertion on `.data-table thead tr` computed style under `dir="rtl"`; visual pass on themed pages.

**D3 — Generate this repo's own API types** · Type: DRY · Effort: S–M · = A7 first consumer.

**D4 — Delete dead `arabic.py` + its tests** · Type: LOC · Effort: S · Depends: nothing (A5 for the shared future)
`src/utils/arabic.py` (129 LOC) has zero `src/` importers; its two test files (~300 LOC) exist solely to test it. If query-time normalization is ever needed, consume the canonical superset from `noorina-pipeline-core` — never re-copy (the stale copy lacks the two folds that decide narrator-name match quality).
*After:* **≈ −430 LOC**. *Verify:* `make test` + `mypy --strict`; zero-importer scan re-run.

**D5 — Admin N+1s and the semantic-search constant** · Type: perf · Effort: S
(a) `admin/analytics.py:67-72`: one Neo4j round trip per narrator (default 10) → one `UNWIND $ids` batch. (b) `admin/data.py`: ~15 sequential count-store queries → `UNION ALL`/`apoc.meta.stats()`. (c) `search.py:501-507`: a parameterless full `count(*)` join recomputed on every semantic search → cache (Redis TTL or reload-marker memo).
*Baseline:* 10 + ~15 serialized RTTs; 1 redundant join per search. *After:* 1–2 queries each; search's second-largest cost removed. *Verify:* `test_admin.py`, `test_admin_data.py`, `test_search.py` (1,261 LOC — #1147/#1150/#1151 paging invariants).

**D6 — Postgres connection pooling** · Type: perf · Effort: S
`get_pg()` opens a fresh psycopg connection per request (TCP+TLS+auth, 5–30 ms) on 4 endpoints incl. `/search/semantic`; Neo4j in the same file is already app-pooled — mirror it with `psycopg_pool.ConnectionPool` in `lifespan`. Fold the fix into the shared client at A6 extraction time.
*Verify:* `test_search.py`, `test_admin_config.py`; note the Redis-ping/offline startup hazard in project memory when touching lifespan.

**D7 — Atomic admin-config writes** · Type: correctness/perf · Effort: S
Config updates run 2N independent commits (config upsert + audit insert per key, commit-per-statement in `PgClient.execute`); a mid-loop failure desyncs the audit trail from the config it documents. `execute_transaction` already exists unused in the same client.
*After:* one transaction, 2 statements; 2N→2 round trips. *Verify:* add a mid-loop failure test asserting neither table advanced (`test_admin_config.py`).

**D8 — Pagination + dating-window dedup** · Type: DRY · Effort: S–M
(a) `skip = (page-1)*limit` at 8 sites, count+page Cypher pair at 4, param blocks restated each time → `PageParams` dependency + `paginate_nodes` helper for plain-label endpoints (~50 LOC saved; optionally fold count into the page query via `CALL {}` to halve RTTs). (b) `hadiths.py::_dating_window` self-documents as a copy of `enrich/historical._active_window` — promote one public implementation (~20 LOC saved; two cross-module private imports resolved).
*Verify:* narrators/hadiths/collections endpoint tests; `test_historical.py` (#1039 outer-bounds cases).

**D9 — Frontend hygiene batch** · Type: DRY/LOC/bundle · Effort: S–M
(a) 14 test files hand-roll the same QueryClient+MemoryRouter wrapper → one `renderWithProviders` helper (**≈ −95 LOC**). (b) `import * as d3 from 'd3'` for 4 symbols → 3 submodule imports (**≈ −70 KB gzip** off the page chunk; drop `d3` dep). (c) delete dead `lib/utils.ts::cn` (duplicates the DS export; drop `clsx` + `tailwind-merge` deps) and `getLocaleMeta`. (d) BUG-05 query-key fix. *Verify:* suite green; `tsc --noEmit`; bundle-size check.

**D10 — Repo hygiene: committed build product + stale docs** · Type: hygiene · Effort: S
(a) `ontology/structural/` (848 KB generated) is committed against the org rule — gitignore + `git rm --cached` (confirm `structural-ontology.yml` regenerates rather than reads first). (b) `CLAUDE.md`'s backend table documents 5 modules that no longer exist (`acquire/ parse/ resolve/ graph/ auth/`) — the most likely reason someone reaches for the dead `arabic.py`; fix the table, note destinations.
*Verify:* librarian lookups still resolve; docs lint.

---

## 8. Track E — user-service

**E1 — One JWT decode path** · Type: security/DRY (fixes BUG-01) · Effort: S
Replace the inline decode in `get_current_user` with `decode_access_token`; add the reverse-direction replay test (`type: "sso"` presented as Bearer → 401).
*Verify:* `test_sso_forward_auth.py` (fixtures already parameterize `token_type`), `test_token_service.py`.

**E2 — Stop re-querying roles the dependency already loaded** · Type: perf · Effort: S
`require_admin`/`require_role` issue a second SELECT for roles that `get_current_user`'s `joinedload` already populated (`user.user_roles`) — 2 DB round-trips instead of 1 on 11+ admin endpoints; `routers/users.py:25` already shows the in-memory pattern.
*After:* 1 round-trip per admin request. *Verify:* `test_rbac.py`, `test_users_crud.py`, `test_audit.py`, `test_subscriptions.py` (403 semantics unchanged).

**E3 — `auth.py` uses its own helpers** · Type: DRY · Effort: S
Delete `_load_user_roles` + its 2 inline raw-SQL twins (call `get_user_role_names`, already imported and used at `:508`); replace the 2 inline token-mint sequences with the existing `_issue_token_pair`.
*Baseline:* ~29 triplicated role-loading lines + ~43 duplicated mint lines in the repo's largest file (920). *After:* **≈ −55–60 LOC** and one fewer place for BUG-01-style drift. *Verify:* `test_auth_endpoints.py`, `test_email_auth_endpoints.py`, `test_oauth_callback_get.py`.

**E4 — Unify session creation** · Type: correctness (fixes BUG-07) · Effort: M
Route `store_refresh_token` through the cap-enforcing + Redis-mirroring path (or a shared internal both call). If instead `/api/v1/sessions` is a deliberately distinct feature, document it at both call sites and drop the dead Redis enrichment — but the router docstring reads as the general case, so unification looks intended.
*Verify:* new regression tests — session cap holds across login; `GET /api/v1/sessions` shows fresh `last_active` for login-created sessions (`test_session_service.py` scaffolding exists, 439 LOC).

**E5 — Hot-path micro-fixes** · Type: perf · Effort: S–M
(a) Pipeline the per-session `redis.hget` loop in `list_user_sessions` (its 3 siblings in the same file already pipeline) — up to 10×1 RTT → 1. (b) Add `index=True` + Alembic migration for `sessions.user_id`, `oauth_accounts.user_id`, `verification_tokens.user_id` (all real query filters; the repo indexes equivalent FKs elsewhere; compounded by BUG-07's unbounded session growth). (c) Cache the parsed RSA key objects (PEM is re-parsed on every encode/decode — every authenticated request); profile before claiming a number.
*Verify:* `test_session_service.py` (extend fakes for pipelining); `EXPLAIN` against seeded Postgres for (b) — the SQLite test fixtures cannot surface it; profiling pass for (c).

**E6 — Table-driven OAuth providers** · Type: DRY · Effort: M
4 provider classes share 60–70% structural boilerplate (307 of 424 lines): per-provider descriptor (URLs, scopes, field names) + shared `_post_form`/`_get_json` helpers on the base; GitHub's email fallback and Apple's id_token/JWKS decode stay hand-written. Preserve the env-gated `OAUTH_PROVIDER_BASE_URL_OVERRIDE` hook exactly (its tests depend on it).
*After:* **≈ −120–140 LOC**; adding a provider becomes a descriptor + mapping. *Verify:* `test_oauth_providers.py` (18 tests), `test_oauth_provider_base_url_override.py` (452 LOC).

**E7 — Test-suite consolidation** · Type: DRY (tests) · Effort: M
Hash-verified byte-identical scaffolding across 6–8 files: RSA test keypair (×6), `db_engine` (×8, 3 variants), `db_session` (×8), `seed_roles` (×4), token-mint helper (×6 variants) — while `conftest.py` is 14 lines and mostly unused. Plus the httpx-mock wiring repeated 9× and 2 DB-error tests that are an exact parametrize pair.
*Baseline (measured):* ~320 duplicated setup lines + ~220 OAuth-test lines. *After:* **≈ −330–360 LOC** into shared fixtures/helpers; one canonical place to fix DB-setup bugs. *Verify:* full suite green; collected-test count preserved (parametrized pair counts as 2 ids).

**E8 — Small cleanups** · Type: LOC · Effort: S
Delete dead `UserCreate`/`UserBase` (unused; skips the password-length bound its live counterpart enforces — a footgun if ever wired); standardize `model_config` to `ConfigDict` per the repo's stated convention and add missing `frozen=True`; extract the two verbatim helpers shared by `bootstrap_admin.py`/`bootstrap_test_user.py` (~21 lines).

---

## 9. Track F — Pipeline runtime & memory (data-acquisition, + ingest-platform workers)

**F1 — Dedup: turn on (and tune) the IVF index** · Type: perf · Effort: M · **Measurement-gated**
`run_dedup(index_type="flat")` is never overridden anywhere (verified: no CLI/Makefile/settings pass it) — production does an exhaustive `IndexFlatIP` scan over **853,218** embeddings × 384 dims ≈ 2.8×10¹⁴ MACs ≈ **1.6–3.1 h** of the ~7.5 h resolve; the `"ivf"` branch is dead code and its `nlist=min(100,n)` is mis-tuned (~3,700 per the 4·√n rule).
*After:* under-tuned IVF ≈ 10× (→10–20 min); retuned (`nlist≈3700, nprobe≈24`) ≈ 50–100×. Index memory 1.31 GB unchanged. **IVF is approximate — ship behind a subset A/B (`--stop-after N`) measuring pair-set delta vs flat before flipping the default.** *Verify:* `test_dedup*.py` suites + the A/B gate; `docs/testing-on-subsets.md` procedure.

**F2 — Checkpointing: stop rewriting the world** · Type: perf/IO · Effort: M
`save_checkpoint` JSON-dumps the entire accumulated payload every time; all three resumable stages put monotonically-growing accumulators in it. `parallels`: ~107 checkpoints × growing 6.66M-row list ≈ **~50 GB written where ~1 GB is needed** (plus matching `json.dumps` CPU and a full second in-memory copy per checkpoint).
*Fix:* cursor state in `state.json` + append-only `parts/NNN.jsonl`; one change in the shared `_checkpoint.py` + 3 call sites. *After:* O(final size) writes (~50× less for parallels); checkpoint stalls off the critical path. *Verify:* the strong existing resume suite (`test_checkpoint.py`, `test_parallels_resume.py`, `test_dedup_resume.py`, `test_disambiguate_resume.py`, `test_stop_after.py`) pins output-identity.

**F3 — Cache `normalize_arabic`** · Type: perf · Effort: XS
Pure `str→str`, 8 regex/translate passes, called per **token** (~10⁸ calls over a ~10⁵-form vocabulary) in `name_quality` — ~8–10 min of a full resolve for one `@lru_cache(maxsize=1<<18)` line.
*Verify:* existing 21-assertion suite + 110 name_quality tests (caching a pure function can't change them).

**F4 — Finish the streaming fix + halve edge-load round trips** · Type: memory/perf · Effort: M
The `_iter_parquet_row_batches` fix that cured the #723 OOM was applied to PARALLEL_OF only; TRANSMITTED_TO/NARRATED/APPEARS_IN still materialize ~4 full-corpus structures at once (3.1M mentions). All 6 loaders also do a full endpoint-existence read pass (`_chunked_read`) before writing, doubling Neo4j round trips (~16k→~8k) when the loaded-id set is derivable in-process.
*After:* peak memory O(50k rows) for the three loaders; round trips halved. **Preserve the malformed-id up-front quarantine semantics** (documented — the loop commits per batch). *Verify:* `test_load_edges.py` (1,634 LOC), integration graph-loading suite, exit-code tests; the da#333/#373 gate tests pin semantics.

**F5 — Neo4j session per loader, not per chunk** · Type: perf · Effort: XS
`execute_write_batch` opens a session per 1,000-row chunk (~10⁴ session lifecycles per full load; ~10–30 s of handshakes) — hoist the session; consider batch 5–10k for property-light MERGEs.
*Verify:* integration tests (unit mocks can't catch session lifecycle).

**F6 — `parallels` memory hygiene** · Type: memory · Effort: XS–S
Raw corpus text (~1 GB of `matn_ar`/`matn_en` dicts) stays alive for the whole anchor scan after its last use — `del rows`/tokenize-in-loop; optional token interning (int ids) if still memory-bound.
*Verify:* `test_parallels*.py` (pure-memory change, no output effect).

**F7 — Worker IO: normalize-stage round trips + bounded batches** · Repos: ip · Type: perf/robustness · Effort: S–M
(a) normalize-worker issues ~15–20 B2 calls/batch (per-label `.part` + server-side copy + delete) vs 3 for its siblings; the manifest-written-last convention already provides the visibility gate — decide whether `.part`+rename defends anything real, else plain `put_object` (→ ~7–8 calls, −55–65% B2 RTTs). (b) Neo4j UNWIND and per-batch FAISS in workers are unbounded with no documented ceiling — chunk the UNWIND (1–5k rows/`tx.run`) and document/enforce a max batch size.
*Verify:* worker tests; call-count arithmetic is exact (measured), latency effect needs a B2 measurement.

**F8 — Test-scaffolding consolidation** · Type: DRY (tests) · Effort: M
365 repeated blocks ≈ 2,742 redundant lines. Three clusters: (a) `tests/integration/test_graph_loading.py` re-implements ~432 lines of `test_graph/conftest.py` fixtures; (b) nine `test_*_lightup.py` files (1,222 LOC) differ only in expected counts → parametrize over a table (the same declarative shape `src/adapters.py` already uses) — the 10th source becomes a one-row change; (c) 5+ independent schema-filling parquet writers (95 `pq.write_table` sites) → one `tests/_staging.py::write_table`.
*After:* **≈ −1,200 to −1,800 test LOC** at unchanged assertion count. *Verify:* `pytest --collect-only` id-set unchanged.

**F9 — Finish the table-driven source registry** · Type: DRY · Effort: S–M
`src/adapters.py` is already the registry; absorb the residual bodies: 3 clone-connectors are the same 8 statements with different constants (→ registry rows + one `_clone_connector`), and 2 CSV parsers share a 72-line verbatim tail (→ `parse/base.py::write_hadith_and_collection`, used by all 10 collection-row construction sites). **Side effect closes a real gate bypass:** `lk_corpus.py:288` hand-builds `collection_id`, skipping the da#355 producer gate that `generate_source_id` enforces.
*After:* **≈ −200 to −280 LOC**; new clone-sourced corpus = a registry row. *Verify:* parser/acquire suites + `test_adapters.py` coverage invariant + `test_source_id_corpus_guard.py`.

**F10 — Optional hygiene** · Effort: XS
Drop the committed 389 KB `firstlight_graph.png` evidence artifact (largest tracked file after the lockfile; unreferenced). Optionally split `name_quality.py`'s ~800 lines of lexicon literals into a data file (module is otherwise exemplary — ordering is load-bearing; lowest priority in this track).

**Explicitly verified non-issues (do not re-flag):** the linear matchers in `disambiguate.py` are the differential-testing oracle for the blocking index (tests import them); blocking/LSH is already implemented across disambiguate/fuzzy_cluster/parallels; no `iterrows`/`.apply`, no uncompiled hot-path regex, no per-row network calls — this codebase has had its obvious perf passes.

---

## 10. Track G — Parent repo (`.claude/hooks` + `.claude/lib`)

Hook latency matters: these run in-process on **every** tool call. The dominant per-call cost is redundant parsing, not any single hook.

**G1 — Memoize shell parsing + prefilter commit detection** · Type: perf · Effort: S
Per Bash call today: **12 `shlex.split` passes, 8 heredoc fix-point loops, 1 `bashlex` AST parse** over the same string (11 hooks with no prefilter; table in the audit), plus `_detect_indirect_commit`'s 7 regex sweeps + conditional disk read on every command. Fix: `lru_cache` on `tokenize`/`strip_heredocs`/`normalize_command_separators`/`iter_command_segments_ast` (~20 lines) + a `if "commit" not in command` guard (safe — all 7 shapes require the literal token).
*After:* **≈ −85% of parse work per Bash call**; the sweeps skipped on the overwhelming majority. *Verify:* `test_shell_parse.py` (667 LOC) pins semantics; add a mutation-safety test for the cached-list boundary.

**G2 — `pre_file` dispatcher matcher** · Type: perf · Effort: S
Edit/Write currently spawn 3 Python processes (2 pre + 1 post); both pre-hooks already expose `check()` and the Post side is already consolidated. Add the matcher table + `hooks.pre_file` config.
*After:* **−33% interpreter startups per file edit** (~30–50 ms each); ~24 lines of settings.json removed; Edit-phase gates become config like every other phase. *Verify:* `test_hook_registration_coverage.py` gains `pre_file`/`pre_notebook` keys (its assertions then prove nothing fell out of reach); keep `INTENTIONALLY_UNREGISTERED` empty.

**G3 — Check the throttle before scanning the transcript** · Type: perf · Effort: XS
`enforce_librarian_consulted` full-parses the session JSONL transcript on every Edit/Write *before* the O(1) #1022 throttle check — the worst-scaling per-edit cost in the repo (transcript grows monotonically). Move the marker check up (~8 lines; semantics unchanged).
*Verify:* add an `assert_not_called` test on `_transcript_has_librarian` when the marker exists.

**G4 — Hooks test conftest** · Type: DRY (tests) · Effort: S–M
`.claude/hooks/tests/` (48 files / 24,704 raw lines) has **no conftest**: 33 byte-identical `_input()` builders (6 in one file), 49 `sys.path` preambles, 8 copies of one 22-line annunaki sandbox setUp/tearDown, per-file `tmp_git_repo` re-rolls. `.claude/lib/tests/` already proves the pattern.
*After:* ~660 scaffolding lines → ~90 (**≈ −550–700**), every future hook test ~10 lines shorter. Note: suite is `unittest`-style (45/48) — provide module-level helpers too. *Verify:* collected-test count unchanged.

**G5 — Parametrize the 92 clone groups** · Type: DRY (tests) · Effort: M–L
AST-normalized comparison found **92 groups of ≥3 near-identical test functions = 2,457 lines** across hooks/lib/skills tests (largest: 12× in `test_annunaki_monitor`, 11× in `test_enforce_ontology_context`, 11× in `test_validate_commit_identity`). The in-file loop idiom already exists — apply it consistently (`pytest.mark.parametrize` / `subTest`).
*After:* **≈ −1,400 to −1,700 lines** at unchanged assertion count (params keep case ids). *Verify:* per-file `--collect-only` id count equal; one mutation spot-check (revert a hook fix → suite still fails).

**G6 — Single source of truth for the org repo list** · Type: correctness/DRY (fixes BUG-08) · Effort: S
7 hardcoded lists (one already drifted); comments are the only enforcement. Review widened the surface: beyond the seven audited lists, at least `w4-kickoff.py` and `w4-project-add.py` also carry repo lists omitting ingest-platform (while `warn_ghcr_image.py`'s subset is deliberate — GHCR-publishing repos only) — G6's sweep should enumerate every literal repo list, not just the seven. Add `.claude/lib/org_repos.py` (or read `ontology/repos/*.yaml`), import everywhere, and add the prose→code test asserting the list matches the CLAUDE.md Repository Map (the repo already has gates of exactly this shape).
*After:* **≈ −40 lines**, drift class gone, handoff bug fixed. *Verify:* new `test_org_repos.py`; `test_session_handoff.py` asserts all 8 repos queried.

**G7 — Scope for `main#1019`: `wave_state.py` + `gh.py`** · Type: DRY/perf · Effort: M (feeds the existing epic — do not file a duplicate)
Measured overlap: 5 identical `_run_gh` (docstrings admit the mirroring), 4 identical `_load_status`, `_DEFAULT_STATUS` ×6, the `--status` argparse block ×5, `read_repos` verbatim ×2 — ≈135 duplicated lines — and the **234 KB / 456-key** `cross-repo-status.json` is re-parsed multiple times per CLI invocation (a single `digest` call parses it repeatedly). Extract `wave_state.py` (mtime-keyed cached loader + shared args) and `gh.py` (one `run_gh` + `GhError`).
*After:* **≈ −75–90 lines**; 1 JSON parse per process. *Verify:* the 6 strong per-module suites; add one cache-invalidation-on-rewrite test.

**G8 — Handoff hook: one search call instead of 8 serial subprocesses** · Type: perf · Effort: S
`session_handoff` runs 7 sequential `gh pr list` + 1 issues call (worst case ~120 s vs a 30 s hook timeout). Replace with one `gh search prs --owner noorinalabs` (also removes the literal list — pairs with G6) or a thread pool.
*After:* 7–10× faster handoff writes. *Verify:* `test_session_handoff.py` asserts the issued command shape.

**G9 — `_hook_main` + subprocess wrappers** · Type: DRY · Effort: S–M
35 of 46 hooks repeat the same stdin-decode/emit `main()` with **three coexisting exit-code dialects** (standalone vs dispatched drift is the class `test_hook_registration_coverage` exists to catch) → `_hook_main.run_blocking/run_advisory` (**≈ −240 lines**). 18 hooks hand-roll `subprocess.run(git|gh)` with inconsistent timeouts (10/15/20) and exception tuples → `run_git`/`run_gh` helpers (**≈ −80–110 lines**); injection seams already exist everywhere for tests.
*Verify:* the CI hook smoke-test (`echo '{}' | python3 <hook>`) is the exact preserved invariant; new `_hook_main` unit tests.

**G10 — Per-edit ledger IO** · Type: perf · Effort: S
`post_file` re-reads + re-writes `ontology/checksums.json` (103 KB) and the generic-prompt ledgers (35 KB) on every Edit/Write plus a `git check-ignore` subprocess. Two safe wins: skip the write when the SHA equals `last_tracked` (a no-op re-save currently rewrites 103 KB), and cache `check-ignore` per directory per process. Keep `ensure_ascii=False` + atomic replace (byte-stability is load-bearing, tests pin it). Append-only JSONL is a separate, measured decision.
*After:* **≈ −50–70% of post_file IO** on edit bursts. *Verify:* `test_ontology_tracker.py` (602), `test_checksums_io.py` (225).

**G11 — `validate_pr_review.py::check` decomposition** · Type: maintainability · Effort: M · Do **after** G4/G5
435-line `check()` (23% of a 1,922-line module; 3,387-line test file — also the #1 file in both clone tables). Extract ordered `_gate_*` predicates (mirrors the dispatcher's first-blocker-wins loop). LOC-neutral; each gate becomes independently testable, letting the giant test file shed its repeated end-to-end setup.
*Verify:* pure extraction — existing suite green with zero edits.

Also in this track: **BUG-09** (vps_host import-time fetch) and the observation that `dispatcher.py` still swallows PreToolUse hook exceptions silently (port `post_dispatcher`'s logged-swallow, ~12 lines) — fold into G9's PR.
**Verified non-issues:** zero dead module-level functions (692 checked); zero duplicate blocks across 30 skill `.md` files; `_DEFAULTS` shadowing `framework.config.json` and the pre-commit⇄CI mirroring are deliberate, enforced patterns — the centralization direction is generate-both-from-one-manifest, sequenced after C9, not de-duplication.

---

## 11. Track H — design-system & landing-page

**H1 — Ship the documented-but-missing CSS classes (or fix the docs)** · Repos: ds · Type: correctness/DRY root-cause · Effort: S–M
`docs/usage/styles.md` documents 20 classes (`.badge*`, `.btn*`, `.form-input*`) that exist in **no shipped CSS** — isnad-graph hand-built exactly that promised API (its 288 "novel" `common.css` lines match the doc's table rows name-for-name), and landing-page hand-rolled `.btn-primary/.btn-secondary` for the same reason. Either implement (isnad-graph's copy is a ready-made reference; org-wide net-negative LOC) or delete the doc sections and steer to React components — for the landing page (no React), a framework-neutral button primitive mirrors the `icons/paths` precedent.
*Verify:* consumer adoption tasks (D2 final 288 lines; lp cleanup) unblock; export validator covers new entry points.

**H2 — Fix broken exports + validator gaps** · Repos: ds · Type: bug (BUG-10) · Effort: S
Add the `tokens/index` Vite lib entry (1 line — mirrors the `./icons` fix); decide `./components/*` (real per-component entries = genuine tree-shaking, or remove the subpath); promote `./tokens` to CI-critical and make the validator check at least one wildcard instance.
*Verify:* build output contains the files; validator fails on regression.

**H3 — Document `icons/paths`; swap landing-page to it** · Repos: ds, lp · Effort: S
The framework-neutral geometry export shipped (ds#103) and even names the landing page as its target consumer — but `docs/usage/icons.md` never mentions it, so `Icon.astro` still hand-mirrors byte-identical path data waiting on a feature that exists (lp#119). Add the doc section + exports-table row; then lp: lockfile refresh (`^0.0.5-wave4.0` already permits wave5.0) + replace the mirror with the import + a 5-entry name map.
*After:* lp `Icon.astro` 111 → ~25–30 lines (**≈ −80**); geometry can no longer drift. *Verify:* lp build + visual check; ds docs lint.

**H4 — Single-source the color tokens** · Repos: ds · Type: DRY · Effort: M
124 unique (name,value) pairs are declared **242×** across `colors.css`'s four blocks (the `:root` vs `[data-theme]` duplication is structurally needed; re-typing the values is not) plus **102 more** hand-matched entries in `tokens/index.ts` — 5 manual sync points per color, zero tooling. Generate the CSS blocks + TS objects from one source (in-repo codegen script fits the repo's existing precedent); interim: a CI drift check.
*After:* manual-sync surface 344 → 0; LOC roughly flat. *Verify:* generated output byte-diffed against current files on first run; existing ds#104/#115 CI greps stay green.

**H5 — `styledSlot` factory for forwardRef boilerplate** · Repos: ds · Type: LOC · Effort: S–M
32 of 43 `forwardRef` blocks are the identical wrap-tag/`cn(base, className)`/spread/`displayName` shape (355 measured LOC); the 11 with real structural logic (Portal wrapping, indicators) stay hand-written.
*After:* **≈ −305 LOC** (~6.6% of the repo's TS). *Verify:* vitest + Storybook stories (every variant/state already required by convention).

**H6 — Adoption decisions + small ds/lp items** · Effort: S
(a) `Tooltip`/`Toast`/`DropdownMenu` + 4 icons/illustrations have zero verified consumers — deliberate keep/trim/roadmap decision, not silent accumulation. (b) Extend `badgeVariants` to the narrator-reliability tier palette the tokens already define (unlocks more of isnad-graph's hand-rolled badge CSS). (c) lp: delete the dead `pages` content collection (19 lines + a string-presence "test"); shared `readPage` test helper (~30–35 LOC); compose `.card-surface`/merge byte-identical grid rules (~25–35 LOC); BUG-12; F8 nits (SEO `schemas` prop, unused Arabic 700 font + unwired `lang="ar"` font rule, nginx 1-year immutable caching on unhashed `/public` assets).

---

## 12. Sequencing, dependencies & risks

**Recommended order:**

1. **Track 0 bugs** — all are small, independent diffs except BUG-07 (E4, medium). BUG-03's interim producer-side fix unblocks the raw→dedup handoff immediately; BUG-02 makes worker restarts safe before any pipeline refactor.
2. **A1 (decision) + C1/C2/C4 quick wins** — the reusable-workflow host decision and devtools scaffold gate several tracks; C1 is a half-day proof of the pattern.
3. **A2 devtools + C-series** — kills the vendored-tooling drift class org-wide.
4. **A3–A6 schema/pipeline-core** — models reconciliation needs a domain-aware review (enum supersets, narrator fields); do it while wave load is low, **before** B3.
5. **B2/B4/B5/B6 (constants extraction) immediately; B3 after `main#978` cutover completes.**
6. **D/E/F/G run in parallel** — they are per-repo and mostly independent; F1/F2 gate on the A/B measurement harness, not on other tracks.
7. **H anytime** (H1/H2 first — they unblock D2's final tranche).

**Dependency edges (machine-readable):**
`A2→A1 · A3→A1 · A4→{A1,BUG-03} · A5→A1 · A6→{A1,B1} · A7→(none) · B2→B1 · B3→{A3,A4,A5,A6,B1,main#978} · B4→B2 · B6→(none — constants extract precedes B3; the Neo4j MERGE-unification follow-up it excludes →B3) · C2..C4→C1(host) · C4→A2 · D2→(H1 for final 288) · D3=A7 · D6→A6(fold-in) · E4→BUG-07 decision · F1→A/B harness · G7→main#1019 (feeds, not duplicates) · H3→ds#103(done, docs only)`

**Risks & mitigations:**

- **IVF is approximate** (F1): flip behind the pair-set-delta A/B on subsets; keep `flat` selectable.
- **Check-run renames break branch protection** (C9, C2 callers): update required checks + `pre_commit_ci_sync` kind map in the same PR; the drift gate itself verifies the mirror.
- **Models reconciliation is semantic, not mechanical** (A3): field-by-field review with the graph as ground truth (data-acquisition writes it); ship the 3 identical modules first.
- **No-install-on-pull contract** (A2): runtime hooks stay vendored; devtools covers CI/pre-commit only. This is a hard boundary, documented in the parent.
- **Deliberate patterns must survive refactors:** da's fail-fast `identity.py` policy (never merge ip's silent repair), `src`↔`workers` import direction in ip (pinned by tests), user-service's regression-guarded broad exception catch and env-gated OAuth override, deploy's promote.yml sequential safety gates, main's `_DEFAULTS` config shadowing. Each is called out in the relevant task above.
- **Cutover window** (B3): the re-cut path (`resolve/`, `graph/`) is frozen until #978 lands.

---

## 13. Consolidated task index (for Jira import)

Type: B=bug, D=DRY, L=LOC, P=perf/memory, C=correctness, A=architecture, T=tests, H=hygiene. Effort: XS<2h · S<½d · M ½–2d · L 2–5d · XL>1wk (single engineer).

| ID | Title | Repo(s) | Type | Baseline → After (headline) | Effort | Deps |
|---|---|---|---|---|---|---|
| BUG-01 | JWT decode dup drops `type` check (SSO→Bearer replay) | user-service | B/C | 2 decode paths → 1; gap closed + test | S | — |
| BUG-02 | Kafka offsets never committed → backlog dropped on restart | ingest-platform | B/C | 0 commits → commit-after-checkpoint + `earliest` | S | — |
| BUG-03 | Producer/consumer message schemas incompatible; parse outside DLQ | da+ip | B/C | 100% messages crash worker → contract aligned + quarantined | S | — |
| BUG-04 | Facets endpoint streams ~870K rows per request | isnad-graph | B/P | O(corpus) → ~50 rows + cache | S | — |
| BUG-05 | Query-key collision truncates Timeline filter | isnad-graph | B | 3 keys/2 shapes → args-in-key | XS | — |
| BUG-06 | RTL header regression from CSS fork | isnad-graph | B | fixed with D2 + Playwright RTL test | XS | D2 |
| BUG-07 | Session cap/Redis mirror bypassed by primary auth flow | user-service | B/C | 2 paths → 1 (E4) | M | — |
| BUG-08 | Handoff repo list omits ingest-platform | main | B | 7 lists → 1 module (G6) | S | — |
| BUG-09 | Hook does network fetch at import on every Bash call | main | B/P | ≤6s cold → 0 on non-matching; cache untracked | S | — |
| BUG-10 | package.json exports point at never-built files | design-system | B | 2 broken exports → built + CI-critical | S | — |
| BUG-11 | Stale sync-gate copy blind to cspell (false-green parity) | landing-page | B | interim resync + cspell hook; durable=A2 | S | — |
| BUG-12 | `/404` stale button fork wins via scoped specificity | landing-page | B | −50 LOC; test extended to /404 | XS | — |
| A1 | Decide + scaffold `noorinalabs-common` (3 packages, git-tag pins) | new repo | A | 0 → installable pinned packages | M | — |
| A2 | Extract `noorina-devtools`; de-vendor 7 repos | all 8 | D/L | ~10,703 vendored lines → ~2,800 (−7.9K) | L | A1 |
| A3 | Extract `noorina-schema` + reconcile model drift | da,ip,ig | D/C | 4,244 LOC ×3 repos → ~1,610 (−2.6K) | L | A1 |
| A4 | Kafka contracts package + round-trip test | da,ip | C | broken-once contract → import-time-safe | S–M | A1,BUG-03 |
| A5 | Canonical Arabic normalizer (da superset) | da,ig,ip | C/D | 3 divergent copies → 1 (−690) | M | A1 |
| A6 | pipeline-core utils (logging/clients/checkpoint/base/hijri/runner) | da,ip,ig | D | ~4,400 extractable LOC → shared | M–L | A1,B1 |
| A7 | OpenAPI→TS codegen for own-backend types | isnad-graph | D/C | 357 hand-mirrored LOC → generated+gated | S–M | — |
| B1 | Ratify canonical package homes (ADR; fold audit.py; keep fail-fast identity) | da,ip | A | fork ambiguity → decided | S | — |
| B2 | Delete dead freight (`src/acquire`+tests+config) | ingest-platform | L | −1,565 LOC | S–M | B1 |
| B3 | Replace copied pipeline packages with dependencies | ingest-platform | D/L | −12.4K src, −5.3K test | XL | A3–A6,B1,#978 |
| B4 | Dep slimming + lazy `__init__` (drop neo4j/psycopg from workers) | ingest-platform | P | ~3,210 forced-import lines → ~0 | S–M | B2 |
| B5 | One worker image + entrypoint factory | ingest-platform | D/L | −272 Dockerfile; main.py 272→~105 | S–M | — |
| B6 | Share batch↔streaming rule constants | ingest-platform | D/C | 3rd taxonomy copy + drift exposure → 1 | S | — |
| C1 | auto-close-issues reusable workflow | all | D | 280 lines ×8 → ~40+callers (−175) | S | host decision |
| C2 | docs.yml reusable with inputs | all 8 | D | 1,698 → ~500 (−1.2K) | M | C1 |
| C3 | ghcr-publish reusable | ig,us,da,ip | D | 919 → ~430 (−490) | M | C1 |
| C4 | structural-ontology reusable + devtools script | 5 repos | D | −360 + generator pinned | S | A2,C1 |
| C5 | deploy stg/prod post-rollout composite (+health-poll param) | deploy | D | −200–250; 1 edit point | M | — |
| C6 | Merge smoke-test twins | deploy | D | 919 → ~300 (−600) | S | — |
| C7 | envsubst-template prometheus/alertmanager | deploy | D | 394 → ~140 (−250) | S–M | — |
| C8 | terraform composites + pip/TF caching | deploy | D/P | −60 lines; −(5–20s ×22 sites)/run | S–M | — |
| C9 | main ci.yml gates-job collapse (+branch-protection update) | main | P/D | −90 lines, −6 runners, ~−3 min/run | S | — |
| C10 | compose/inventory/alerts YAML anchors + one-shot limits | deploy | D/H | ~−120 lines; rendered-diff-identical | S | — |
| C11 | Delete dead legacy deploy workflows + stale docs | deploy | L/H | −248 lines; docs truthful | S | — |
| C12 | Shared shell lib (log/pass/fail/wait_for_healthy) | deploy | D/C | drifted helpers ×9 files → 1 lib | S | — |
| D1 | Facets Cypher aggregation + Redis | isnad-graph | P | =BUG-04 | S | — |
| D2 | Delete DS-duplicated CSS (+RTL fix) | isnad-graph | D/L | −780 now, −288 post-H1 | M | H1 partial |
| D3 | =A7 | isnad-graph | D | — | S–M | — |
| D4 | Delete dead arabic.py + tests | isnad-graph | L | −430 | S | — |
| D5 | Admin N+1s + search count cache | isnad-graph | P | ~25 RTTs → ~3; constant off hot path | S | — |
| D6 | Postgres pool in lifespan | isnad-graph | P | 5–30 ms/req connect → amortized | S | — |
| D7 | Atomic config writes via existing helper | isnad-graph | C/P | 2N commits → 1 txn | S | — |
| D8 | PageParams/paginate helper + dating-window dedup | isnad-graph | D | ~−70 LOC; optional RTT halving | S–M | — |
| D9 | Frontend: test wrapper, d3 submodules, dead utils, key fix | isnad-graph | D/L/P | −95 LOC; ~−70 KB gzip; −2 deps | S–M | — |
| D10 | Un-commit structural index; fix CLAUDE.md arch table | isnad-graph | H | −848 KB tracked; docs accurate | S | — |
| E1 | =BUG-01 consolidation | user-service | C | — | S | — |
| E2 | Drop role re-query on admin deps | user-service | P | 2 DB RTTs → 1 on 11+ endpoints | S | — |
| E3 | auth.py uses own helpers | user-service | D | −55–60 LOC in the 920-line file | S | — |
| E4 | Unify session creation (=BUG-07) | user-service | C | cap+mirror enforced on real logins | M | — |
| E5 | Redis pipeline, FK indexes, cached RSA keys | user-service | P | ≤10 RTTs→1; seq-scan→index; per-req PEM parse→1 | S–M | — |
| E6 | Table-driven OAuth providers | user-service | D | 307 → ~180 (−120–140) | M | — |
| E7 | Test fixture consolidation (conftest) | user-service | T | ~−330–360 LOC | M | — |
| E8 | Dead schemas, ConfigDict, bootstrap dedup | user-service | L/H | ~−30 LOC + convention | S | — |
| F1 | Dedup IVF enable + retune (A/B-gated) | data-acquisition | P | ~1.6–3.1h → minutes-to-~20min | M | harness |
| F2 | Append-only checkpoints | data-acquisition | P | ~50 GB writes → ~1 GB (parallels) | M | — |
| F3 | lru_cache normalize_arabic | data-acquisition | P | ~10⁸ calls ≈8–10 min → cache hits | XS | — |
| F4 | Streaming for 3 loaders + drop pre-check pass | data-acquisition | P | 4 corpus structures → O(batch); RTTs halved | M | — |
| F5 | Session-per-loader in neo4j client | data-acquisition | P | ~10⁴ session cycles → ~6 | XS | — |
| F6 | Free raw text in parallels scan | data-acquisition | P | ~1 GB dead resident → freed | XS–S | — |
| F7 | normalize-worker B2 calls; bounded UNWIND/FAISS batches | ingest-platform | P | 15–20 → ~7–8 calls/batch; ceilings documented | S–M | — |
| F8 | Parametrize pipeline test scaffolding | data-acquisition | T | −1,200–1,800 LOC | M | — |
| F9 | Finish table-driven registry (+close lk_corpus gate bypass) | data-acquisition | D/C | −200–280 LOC; gate hole closed | S–M | — |
| F10 | Evidence PNG; lexicon data-file (optional) | data-acquisition | H | −389 KB; readability | XS | — |
| G1 | Memoize shell parse + commit prefilter | main | P | −85% parse work/Bash call | S | — |
| G2 | pre_file dispatcher | main | P | 3→2 processes/edit | S | — |
| G3 | Throttle before transcript scan | main | P | O(transcript)/edit → O(1) | XS | — |
| G4 | Hooks tests conftest | main | T | −550–700 LOC | S–M | — |
| G5 | Parametrize 92 clone groups | main | T | −1,400–1,700 LOC | M–L | G4 |
| G6 | org_repos single source (=BUG-08) | main | C/D | 7 lists → 1 + prose→code test | S | — |
| G7 | wave_state/gh consolidation (feeds #1019) | main | D/P | −75–90 LOC; 234 KB parsed once | M | #1019 |
| G8 | Handoff: 1 search call | main | P | 8 serial subprocesses → 1 | S | G6 |
| G9 | _hook_main + run_git/run_gh (+dispatcher logged-swallow) | main | D | −320–350 LOC; 1 exit-code contract | S–M | — |
| G10 | Ledger IO: skip no-op writes; cache check-ignore | main | P | −50–70% post_file IO | S | — |
| G11 | Decompose validate_pr_review.check (435 lines) | main | H | LOC-neutral; gates unit-testable | M | G4,G5 |
| H1 | Ship documented badge/btn/form CSS (or fix docs) | design-system | C/D | 20 phantom classes → shipped; unblocks −288 in ig | S–M | — |
| H2 | =BUG-10 exports + validator | design-system | B | — | S | — |
| H3 | Document icons/paths; swap lp Icon.astro | ds,lp | D | lp 111 → ~28 LOC; drift impossible | S | — |
| H4 | Token codegen single-source | design-system | D | 344 manual-sync decls → 0 | M | — |
| H5 | styledSlot factory | design-system | L | −305 LOC | S–M | — |
| H6 | Unused-component decision; badge tiers; lp cleanups | ds,lp | D/L/H | keep/trim decided; ~−130 LOC lp | S | — |

---

## Appendix — reproduction notes

- **LOC baseline:** walk each repo skipping `.git node_modules dist build __pycache__ .venv .terraform .astro coverage` + lockfiles + `ontology/structural` + `.claude/worktrees`; count non-blank lines per extension class. (The audit's counter and duplication scanner were session scripts; they are ~150 lines each and re-creatable from the description in §2 — parameters that matter: window K=6 normalized lines, ≥12 dup lines per pair, comment/trivial-line stripping.)
- **Duplication ground truth used above** (for re-verification): `diff -q` byte-identity for `auto-close-issues.yml` ×8 and `check_dockerfile_base_pin.py` ×7; `md5` identity for ig↔ip `arabic.py`; `difflib` ratios for the twin-repo file table; AST symbol-set diffs for drift direction; import-graph closure for ingest-platform's used-vs-freight split.
- **Corpus figures** cited from repo-committed data: 853,218 staged hadith rows (`docs/reports/corpora-shape-audit-da279.md`), 870,663 manifest hadith rows (`data/.manifest.json`, isnad-graph), 6.66M parallel-link rows (`src/graph/load_edges.py:87`), 3.1M mentions (`src/resolve/disambiguate.py:99`), ~7.5h resolve re-run (wave-27 scope notes).
- **Do not re-file as findings** (verified deliberate/correct): sync `def` FastAPI handlers, pooled Neo4j client, TTL-cached JWKS, memoized ForceGraph (isnad-graph); linear-matcher test oracles and blocking/LSH design (data-acquisition); `src`↔`workers` import direction and duplicate-with-pinned-test contracts (ingest-platform); promote.yml sequential gates, hetzner TF matrix, no-apply-backblaze boundary, structural-ontology absence (deploy); `_DEFAULTS` config shadowing, pre-commit⇄CI mirroring-by-design (main); `sideEffects` scoping, single CSS blob at current scale, Storybook LOC ratio (design-system); DS-then-LP CSS order, zero-hydration architecture, ADR-0001 (landing-page).
