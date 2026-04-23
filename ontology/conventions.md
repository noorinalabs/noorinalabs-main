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

### Container security
- Read-only filesystems on all application containers
- tmpfs for writable paths (/tmp, nginx cache)
- Internal Docker networks for backend services (not exposed)
- Resource limits on all containers (memory + CPU)

## Team & process conventions

### Commit identity
- Per-commit `-c` flags with roster identity — never global git config
- Two Co-Authored-By trailers required (team member + Claude)
- Enforced by `validate_commit_identity.py` hook

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
