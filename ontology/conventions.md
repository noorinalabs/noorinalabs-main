# NoorinALabs — Conventions & Patterns

Cross-repo conventions, shared patterns, and architectural decisions.
Updated by `/ontology-rebuild`. Manual edits require `checksums.json` update.

## Coding conventions

### Languages & versions
- **Backend:** Python 3.12+ (user-service), Python 3.14 (isnad-graph, ingestion)
- **Frontend:** TypeScript 5.9, React 19 (isnad-graph), Astro 6 (landing-page)
- **Infrastructure:** Terraform >= 1.5, Docker Compose v2

### Linting & formatting
- **Python:** ruff (lint + format), mypy strict mode
- **TypeScript/JS:** ESLint + Prettier
- **All repos:** pre-commit hooks enforced

### Data modeling
- **Python:** Pydantic v2 frozen models (`ConfigDict(frozen=True)`)
- **Enums:** StrEnum for clean JSON/Parquet serialization
- **IDs:** Prefixed strings for domain entities (`nar:`, `hdt:`, `chn:`, `col:`, `loc:`)
- **UUIDs:** For user management entities (user, role, session, subscription)

### API conventions
- **Framework:** FastAPI with dependency injection
- **Auth:** RS256 JWT tokens, validated via JWKS endpoint
- **Pagination:** Cursor-based (user-service), page-based (isnad-graph)
- **Rate limiting:** Sliding-window via Redis sorted sets
- **Response format:** JSON, Pydantic v2 response models

### CSS & styling
- **Color space:** OKLCH (perceptually uniform)
- **Component variants:** CVA (class-variance-authority)
- **UI primitives:** Radix UI (unstyled, accessible)
- **BiDi support:** CSS logical properties (`ps-3`, `pe-3`, `start`, `end`)
- **Utility classes:** Tailwind CSS 4.x

## Architectural patterns

### Authentication flow
1. Frontend redirects to OAuth provider via user-service
2. User-service handles callback, creates/finds user, issues RS256 JWT pair
3. Access token (15 min) + refresh token (30 days, httpOnly cookie)
4. isnad-graph-api validates JWT via JWKS fetch from user-service
5. Rate limiting: 120 req/min per IP (Redis sliding window)

### Data pipeline (ingestion)
1. **Acquire:** Download raw data from APIs, scrapers, Git repos, Kaggle
2. **Parse:** Raw CSV/JSON → PyArrow Parquet (schema-validated)
3. **Resolve:** Entity resolution — NER, 5-stage disambiguation, FAISS dedup
4. **Load:** Parquet → Neo4j via Cypher MERGE (batch 1000)
5. **Enrich:** Graph metrics (PageRank, betweenness), topic classification, historical linking
- Incremental mode via manifest checksums
- Audit trail per stage (JSON)

### Design system consumption
- Published as `@noorinalabs/design-system` npm package
- Consumers import CSS tokens + React components
- OKLCH tokens defined as CSS custom properties + TypeScript constants
- Domain-specific tokens: hadith grading colors, sect indicators, narrator reliability tiers

### Reverse proxy routing
- Caddy handles TLS termination (Let's Encrypt auto-provisioned)
- Path-based routing: `/auth/*` and user management → user-service, `/api/*` → isnad-graph, `/*` → frontend
- Security headers: CSP, HSTS, X-Frame-Options, Referrer-Policy

### Cloudflare proxy posture (prod-true / stg-false asymmetry)

Production Cloudflare DNS records are orange-cloud (`proxied = true`) — traffic flows through the Cloudflare edge. Staging records for the same subdomains are gray-cloud (`proxied = false`) — DNS only, traffic resolves directly to the origin VPS. The Terraform `var.subdomains` map (`noorinalabs-deploy/terraform/cloudflare/`) carries one `proxied` boolean per name, set per-env via `terraform.tfvars`.

**Root cause — TLS certificate coverage at the CF edge.** Cloudflare's free Universal SSL covers exactly two label depths: the apex (`noorinalabs.com`) and one wildcard level (`*.noorinalabs.com`). Production subdomains (`isnad.noorinalabs.com`, `users.noorinalabs.com`) sit at that one-wildcard level and are covered. Staging subdomains are third-level (`isnad.stg.noorinalabs.com`, `users.stg.noorinalabs.com`) — Universal SSL does NOT cover them, so orange-clouding them produces a TLS handshake failure at the edge before the request ever reaches the origin. Gray-cloud bypasses the edge entirely; the origin Caddy auto-provisions Let's Encrypt certificates for those names and terminates TLS itself.

**Operator trade-off.** Gray-cloud staging loses every edge benefit Cloudflare provides — DDoS absorption, WAF, edge cache, IP masking. The staging origin IP is reachable directly via DNS, which is the acceptable posture for non-prod (staging is not user-facing and is firewalled separately). Anything that depends on edge behavior (e.g., a WAF rule shielding an endpoint) must be validated against prod, not stg.

**Remediation path.** Cloudflare Advanced Certificate Manager (ACM, ~$10/mo) issues certificates covering arbitrary subdomain depths, including `*.stg.noorinalabs.com`. Once ACM is enabled, the `proxied` value for staging records can be flipped to `true` and the asymmetry disappears. This is an owner-budget decision tracked in deploy#229; until then, the stg-false posture is the documented baseline.

**Per-repo reference.** The Terraform module README at `noorinalabs-deploy/terraform/cloudflare/README.md` (file added by deploy#298; proxy-posture section added by deploy#303) documents the same asymmetry from the implementation side and is the source of truth for `var.subdomains` shape and per-env tfvars wiring.

### Container security
- Read-only filesystems on all application containers
- tmpfs for writable paths (/tmp, nginx cache)
- Internal Docker networks for backend services (not exposed)
- Resource limits on all containers (memory + CPU)

## Architecture Decision Records (ADRs)

Cross-repo convention for filename, location, and format. Per-repo content remains repo-scoped; this section governs only the shape so an ADR is identifiable and sortable the same way across the org.

- **Location:** `docs/adr/` at each repo root. Index file: `docs/adr/README.md` (chronological list with title + link + date + status).
- **Filename pattern:** `<NNNN>-<kebab-title>.md` — **4-digit zero-padded** sequential number, hyphen-kebab title. Example: `0001-tf-hetzner-per-env-state-strategy.md`.
- **Format:** Michael Nygard's ADR template (Title / Status / Context / Decision / Consequences). The dominant `adr-tools` ecosystem and most external reference material assume this shape; newcomers reading an ADR will already know it.
- **Numbering:** strictly monotonic within a repo. Numbers are not reused on supersede — a superseded ADR keeps its number and the superseding ADR gets the next free number; both reference each other.
- **Status values:** `Proposed`, `Accepted`, `Deprecated`, `Superseded by NNNN`. No `Rejected` (closed PRs serve that role).

### Why 4-digit zero-padded

Three considerations:

1. **Headroom.** `0001-` supports >999 ADRs without renumbering. `001-` does not. Cheap insurance for a long-lived org.
2. **Alphasort.** Directory listings sort numerically when zero-padded; otherwise `10-...` sorts before `2-...`. 4 digits matches the headroom decision.
3. **External convention alignment.** Nygard's own examples and `adr-tools` zero-pad to 4 digits (`docs/adr/0001-record-architecture-decisions.md`).

### Cross-repo state (2026-05-11)

| Repo | Current ADRs | Convention | Action |
|---|---|---|---|
| `noorinalabs-deploy` | `0001-tf-hetzner-per-env-state-strategy.md` | 4-digit ✓ | None — already canonical |
| `noorinalabs-landing-page` | `0001-astro-build-output-hook-coverage.md` (PR #89) | 4-digit ✓ | None — already canonical |
| `noorinalabs-data-acquisition` | `001-local-hook-policy-dispatcher-style.md` (PR #48) | 3-digit | Follow-up rename PR to `0001-` |
| `noorinalabs-isnad-graph` | `001-` … `004-` (4 ADRs merged) | 3-digit | Out of scope here — track as separate bulk-rename cleanup if pursued |

Existing 3-digit ADRs are not merge-blockers; renames are mechanical and reversible.

## Team & process conventions

### Commit identity
- Per-commit `-c` flags with roster identity — never global git config
- Two Co-Authored-By trailers required (team member + Claude)
- Enforced by `validate_commit_identity.py` hook

### SSH topology (owner workstation → VPSes)
- **Two keys on owner workstation:**
  - `~/.ssh/id_ed25519` (comment `parametrization@gmail.com`) — root user on both VPSes
  - `~/.ssh/noorinalabs_deploy` (comment `deploy@isnad-graph`, fingerprint `SHA256:UP42OaHWXymDpno0mnQ4vfJV902h3K6eYQ3XdrCR4Uo`) — `deploy` user. **Renamed from `isnad_deploy` 2026-04-24** to align with secrets-audit §3.0.a (PR #213).
- **`~/.ssh/config`** uses 4 role-explicit Host aliases (no silent default-fallback): `noorinalabs-stg-{root,deploy}`, `noorinalabs-prod-{root,deploy}`. Each entry sets `IdentitiesOnly yes` to force the declared key only.
- **Per-user authorization on VPSes:**
  - `root`'s `authorized_keys`: `id_ed25519` only (root-only key)
  - `deploy`'s `authorized_keys`: BOTH `id_ed25519` AND `noorinalabs_deploy` (mirrors prod pattern; lets owner reach `deploy@*` from either key, but `root@*` only via root-only key)
- **Per-VPS + per-role key separation tech-debt** tracked in deploy#164. Current shared-key posture is the prod baseline; W10 should not introduce new asymmetry between stg and prod, but the longer-term goal is per-env keys with `DEPLOY_SSH_PRIVATE_KEY` env-scoped via deploy#155 GH Environments.
- **Custodial paths for value-preservation** (per secrets-audit §3.0.a, PR #213 merged): `~/.ssh/noorinalabs_deploy` (DEPLOY_SSH_PRIVATE_KEY), `~/.ssh/jwt_private.pem` + `~/.ssh/jwt_public.pem` (JWT_PRIVATE_KEY/JWT_PUBLIC_KEY).

### Branching
- Feature branches: `{FirstInitial}.{LastName}/{IIII}-{issue-name}`
- Wave branches: `deployments/phase{N}/wave-{M}`
- All PRs target wave deployment branch, not main directly
- Final wave merge: deployment branch → main (user approval required)

### PR workflow
- Minimum 2 reviewers per PR (comment-based, not API reviews)
- Charter-format review comments (Requestor/Requestee/RequestOrReplied/TechDebt)
- Must-fix items block merge; tech-debt items get GitHub Issues
- CI must be green before merge (enforced by hooks)
- Cross-contract PRs (shared Kafka topics, Parquet schemas, wire formats): first PR opened must include a `## Contract` section; subsequent PRs link to it and document divergence (P2W9 retro, 2026-04-22)

### Wave lifecycle
- `/wave-start` → `/wave-kickoff` → work → `/wave-wrapup` → `/wave-retro`
- Wrapup includes: PR merge sequencing, ontology rebuild, Annunaki attack, memory audit
- Retro includes: ontology staleness check, per-engineer assessments, trust matrix updates
- **Open-item audit before "concluded" claims** (charter `skills.md`): every wave-wrapup / handoff / retro that claims a wave or workstream is complete MUST first run the cross-repo open-item count; zero open or an explicit carry-forward list is required. Promotion-target: hook.

### Session continuity
- **Auto-handoff** (`session_handoff.py` Stop hook): Fires on every session exit (throttled to 5 min). Captures git state, open PRs/issues, wave status, ontology staleness. Writes to project memory for next session pickup.
- **Manual handoff** (`/handoff` skill): Richer version that includes conversational context — what was discussed, decisions made, blockers encountered.
- **Session start protocol**: Charter-mandated automatic steps — (0) check handoff file, (1) team cleanup (TeamDelete + TeamCreate), (2) ontology rebuild, (3) Annunaki check, (4) wave/phase orientation, (5) charter freshness check.

### Emergency Mode (charter `charter/emergency-mode.md`)
- **Triggers:** prod-down / active security incident / DR or first-deploy. Discomfort or urgency are NOT triggers.
- **Allowed bypasses:** single- or zero-reviewer merge; `[EMERGENCY]` PR-title prefix; direct-to-main commits with `[EMERGENCY]` subject when a PR cannot be opened. Charter-format review comments may be skipped in favor of one-line PR body context.
- **Not bypassed:** commit-identity / no-verify / secrets hooks, root-fix discipline, honest-audit-before-concluded.
- **Entering / exiting:** in-band declaration ("Entering Emergency Mode … trigger: {…}" / "Exiting Emergency Mode — {…}").
- **Post-emergency catchup (24h):** async charter-format review on every `[EMERGENCY]` PR, file TechDebt items, update runbooks/hooks, Aino sign-off. `/wave-kickoff` blocked until catchup is complete.
- **Owner-Manual-Action Protocol:** when the owner takes infra action outside the orchestrator's tool scope (Hetzner console, secret rotation, local `terraform apply`, etc.), they post a one-line `[OWNER-ACTION] {what was done} — {what state changed} — {what now points where}` to the active session BEFORE proceeding. Orchestrator acknowledges by enumerating the dependent state it will pre-flight check.

### Automation hooks (org-level)
| Hook | Event | Purpose |
|------|-------|---------|
| `validate_commit_identity.py` | PreToolUse (Bash) | Block commits without per-commit `-c` identity flags |
| `block_no_verify.py` | PreToolUse (Bash) | Block `--no-verify` flag on git commands |
| `block_git_config.py` | PreToolUse (Bash) | Block `git config user.*` commands |
| `auto_set_env_test.py` | PreToolUse (Bash) | Auto-set `ENV=test` for pytest commands |
| `validate_labels.py` | PreToolUse (Bash) | Verify labels exist before applying to issues |
| `validate_lockfile_paths.py` | PreToolUse (Bash) | Block commits with absolute lockfile paths |
| `validate_pr_review.py` | PreToolUse (Bash) | Enforce charter review comment format |
| `validate_wave_label_evidence.py` | PreToolUse (Bash) | Verify cited paths at origin before applying p{N}-wave-{M} labels |
| `validate_branch_freshness.py` | PreToolUse (Bash) | Warn if branch is behind origin |
| `validate_vps_host.py` | PreToolUse (Bash) | Block SSH to non-approved VPS hosts |
| `warn_ghcr_image.py` | PreToolUse (Bash) | Warn before pushing GHCR images |
| `block_gh_pr_review.py` | PreToolUse (Bash) | Block `gh pr review` (use comment-based reviews) |
| `validate_review_comment_format.py` | PreToolUse (Bash) | Enforce review comment charter format |
| `validate_wave_context.py` | PreToolUse (Agent) | Warn if agent spawned without wave context or ontology context in prompt |
| `block_shutdown_without_retro.py` | PreToolUse (SendMessage) | Block agent shutdown before retro |
| `auto_add_issue_to_board.py` | PostToolUse (Bash) | Auto-add new issues to project board |
| `validate_pr_ci_status.py` | PreToolUse (Bash) | Block `gh pr merge` when any CI check is failing/cancelled/timed-out |
| `enforce_librarian_consulted.py` | PreToolUse (Edit/Write/NotebookEdit) | Block edits unless `/ontology-librarian` consulted earlier in session |
| `no_worktree_self_delete.py` | PreToolUse (Bash) | Block `git worktree remove` when cwd is inside target worktree |
| `annunaki_log.py` | Utility (imported by hooks) | Shared logging for PreToolUse block events to Annunaki error log |
| `annunaki_monitor.py` | PostToolUse (Bash) | Capture failed commands to error log |
| `ontology_tracker.py` | PostToolUse (Edit/Write) | Track file checksums for ontology changes |
| `suggest_generic_prompt.py` | PostToolUse (Edit/Write) | Suggest generic prompts for `.claude/` changes |
| `session_handoff.py` | Stop | Auto-generate handoff on session exit |

## Shared tooling

### Package management
- **Python:** uv
- **JavaScript:** npm (with `@noorinalabs` scoped packages from GitHub Packages)

### Build tools
- **Python backends:** uvicorn (ASGI server)
- **React frontend:** Vite 6.4 (dev + production build)
- **Astro frontend:** Vite via Astro (static site generation)
- **Design system:** Vite library mode (ES + CJS output)

### Pre-commit hooks
- Every repo has a `.pre-commit-config.yaml` or `scripts/pre-commit.sh` replicating CI checks locally
- Python repos: ruff lint, ruff format, mypy, unit tests
- JS/TS repos: ESLint, Prettier, TypeScript type check, unit tests
- Infrastructure repos: terraform fmt, terraform validate, gitleaks
- All repos include gitleaks for secret detection

### Testing
- **Python:** pytest + pytest-asyncio + testcontainers (Docker-based fixtures)
- **React:** Vitest + Testing Library
- **E2E:** Playwright (all frontend repos)
- **Accessibility:** @axe-core/playwright (WCAG 2.2 AA)
- **Property-based:** hypothesis (Python repos)

### Observability
- **Metrics:** Prometheus scraping FastAPI `/metrics` endpoint
- **Dashboards:** Grafana at `/grafana` path
- **Logs:** Loki + Promtail (Docker socket scraping, JSON pipeline)
- **Alerting:** Alertmanager with webhook receivers
- **Exporters:** node-exporter (system), postgres-exporter (both PG instances)
