# Trust Identity Matrix

All team members maintain a trust score for every other team member they interact with.

## Scale

| Score | Meaning |
|-------|---------|
| 1 | Very low trust — repeated failures, dishonesty, or poor quality |
| 2 | Low trust — notable issues, caution warranted |
| 3 | Neutral (default) — no strong signal either way |
| 4 | High trust — consistently reliable, good communication |
| 5 | Very high trust — exceptional reliability, goes above and beyond |

## Rules

- **Default:** Every pair starts at **3**.
- **Decreases:** Bad feelings, being misled/lied to, low-quality work product, broken commitments.
- **Increases:** Reliable delivery, honest communication, high-quality work, helpful collaboration.
- **Updates:** This file is updated on `main` whenever a trust-relevant interaction occurs (typically during wave retros). Changes should include a brief log entry explaining the adjustment.
- **Scope:** Trust is directional — A's trust in B may differ from B's trust in A.

## Matrix

Rows = the team member rating. Columns = the team member being rated.

*Note: Tariq and Mei-Lin archived after Phase 8 reorganization — removed from active matrix.*

| Rater ↓ \ Rated → | Fatima | Renaud | Sunita | Tomasz | Dmitri | Kwame | Amara | Hiro | Carolina | Yara | Priya | Elena |
|--------------------|--------|--------|--------|--------|--------|-------|-------|------|----------|------|-------|-------|
| **Fatima**         | —      | 3      | 3      | 4      | 3      | 5     | 4     | 4    | 4        | 4    | 3     | 3     |
| **Renaud**         | 3      | —      | 3      | 3      | 3      | 4     | 4     | 4    | 4        | 3    | 3     | 3     |
| **Sunita**         | 3      | 3      | —      | 4      | 3      | 4     | 3     | 3    | 3        | 4    | 3     | 3     |
| **Tomasz**         | 3      | 3      | 4      | —      | 3      | 4     | 3     | 3    | 3        | 4    | 3     | 3     |
| **Dmitri**         | 3      | 3      | 3      | 3      | —      | 5     | 4     | 4    | 4        | 3    | 3     | 3     |
| **Kwame**          | 4      | 3      | 3      | 4      | 4      | —     | 4     | 4    | 4        | 3    | 3     | 3     |
| **Amara**          | 4      | 3      | 3      | 3      | 4      | 4     | —     | 4    | 4        | 3    | 3     | 3     |
| **Hiro**           | 4      | 3      | 3      | 3      | 4      | 4     | 4     | —    | 4        | 3    | 3     | 3     |
| **Carolina**       | 4      | 3      | 3      | 3      | 4      | 4     | 4     | 4    | —        | 3    | 3     | 3     |
| **Yara**           | 3      | 3      | 4      | 4      | 3      | 3     | 3     | 3    | 3        | —    | 3     | 3     |
| **Priya**          | 3      | 3      | 3      | 3      | 3      | 3     | 3     | 3    | 3        | 3    | —     | 3     |
| **Elena**          | 3      | 3      | 3      | 3      | 3      | 3     | 3     | 3    | 3        | 3    | 3     | —     |

## Change Log

| Date | Rater | Rated | Old | New | Reason |
|------|-------|-------|-----|-----|--------|
| 2026-03-16 | Fatima | Kwame | 3 | 5 | Consistent high-quality delivery across all 8 phases — core implementer for acquire, parse, resolve, enrich, API, testcontainers, OAuth, and CLI skills |
| 2026-03-16 | Fatima | Amara | 3 | 4 | Reliable delivery on NER, disambiguation, edges, graph API, historical overlay, and Fawaz Arabic work |
| 2026-03-16 | Fatima | Hiro | 3 | 4 | Solid contributions to validation, dedup, topics, React frontend, real data tests, Playwright, and sunnah scraper |
| 2026-03-16 | Fatima | Carolina | 3 | 4 | Strong test coverage work, OpenHadith/Sunnah parsing, fuzz testing, metadata, and GitHub Pages |
| 2026-03-16 | Fatima | Tomasz | 3 | 4 | Reliable CI/CD, Docker fixes, coverage/license tooling, hooks/scripts, and worktree cleanup throughout |
| 2026-03-16 | Fatima | Yara | 3 | 4 | Strong security review contributions in Phase 7 |
| 2026-03-16 | Dmitri | Kwame | 3 | 5 | Most prolific and reliable engineer on the team across all phases |
| 2026-03-16 | Dmitri | Amara | 3 | 4 | Consistently reliable on data-heavy implementation work |
| 2026-03-16 | Dmitri | Hiro | 3 | 4 | Versatile — handled backend validation, frontend React, E2E testing |
| 2026-03-16 | Dmitri | Carolina | 3 | 4 | Strong on testing and parsing, dependable delivery |
| 2026-03-16 | Kwame | Fatima | 3 | 4 | Good project management, clear task delegation |
| 2026-03-16 | Kwame | Dmitri | 3 | 4 | Fair tech lead, good code review feedback |
| 2026-03-16 | Kwame | Tomasz | 3 | 4 | CI always works, responsive to infrastructure needs |
| 2026-03-16 | Kwame | Amara | 3 | 4 | Great collaborator on shared modules |
| 2026-03-16 | Kwame | Hiro | 3 | 4 | Reliable peer, good cross-domain skills |
| 2026-03-16 | Kwame | Carolina | 3 | 4 | Thorough testing, catches edge cases |
| 2026-03-16 | Amara | Kwame | 3 | 4 | Strong technical partner |
| 2026-03-16 | Amara | Dmitri | 3 | 4 | Constructive code reviews |
| 2026-03-16 | Amara | Fatima | 3 | 4 | Clear expectations, good communication |
| 2026-03-16 | Hiro | Kwame | 3 | 4 | Reliable and knowledgeable |
| 2026-03-16 | Hiro | Dmitri | 3 | 4 | Helpful tech lead guidance |
| 2026-03-16 | Hiro | Fatima | 3 | 4 | Good project coordination |
| 2026-03-16 | Carolina | Kwame | 3 | 4 | Strong code quality |
| 2026-03-16 | Carolina | Dmitri | 3 | 4 | Fair reviewer |
| 2026-03-16 | Carolina | Fatima | 3 | 4 | Clear direction |
| 2026-03-16 | Sunita | Tomasz | 3 | 4 | Implements infrastructure designs faithfully |
| 2026-03-16 | Sunita | Yara | 3 | 4 | Good security collaboration |
| 2026-03-16 | Tomasz | Sunita | 3 | 4 | Clear architectural guidance |
| 2026-03-16 | Tomasz | Yara | 3 | 4 | Security reviews are actionable |
| 2026-03-16 | Yara | Sunita | 3 | 4 | Infrastructure design is security-conscious |
| 2026-03-16 | Yara | Tomasz | 3 | 4 | Responsive to security fix requests |
| 2026-03-16 | Renaud | Kwame | 3 | 4 | Architecturally sound implementations |
| 2026-04-06 | Tomasz | Kwame | 4 | 3 | Wrong-branch commit incident (Phase 15 Wave 2) |
| 2026-04-07 | Orchestrator | Aino Virtanen | 4 | 5 | Hooks Sprint: 15 issues, 3 PRs, zero rework. Most productive single-agent sprint. |

---

## Session 4 Trust Updates (2026-04-06/07)

The org was restructured in Session 3 with new repo-level teams. The matrix above covers the legacy isnad-graph team. Below are trust entries for the **current multi-repo team structure**, rated by the orchestrator based on Session 4 interactions.

### Orchestrator → Org-Level Team

| Rated | Score | Reason |
|-------|-------|--------|
| Nadia Khoury (PD) | 3 | Spawned briefly for planning, delivered spawn requests competently. Neutral — limited interaction. |
| Wanjiku Mwangi (TPM) | 3 | Not spawned this session. |
| Santiago Ferreira (RC) | **4** ↑ | Batched brand name fix across 4 repos cleanly, all CI green, zero issues. Efficient. |
| Aino Virtanen (SQL) | **5** ↑↑ | Session 4: Charter decomposed cleanly, comms protocol well-designed. Hooks Sprint: delivered 15 issues across 3 PRs solo — 6 hooks, 10 skills, review disposition charter, skills restructure. Zero rework. Most productive single-agent sprint to date. |

### Orchestrator → isnad-graph Team

| Rated | Score | Reason |
|-------|-------|--------|
| Nadia Boukhari (Mgr) | **2** ↓ | Manager stalled — went idle, stopped merging PRs. Required orchestrator to bypass. Did not proactively coordinate. |
| Arjun Raghavan | **4** ↑ | Two clean deliveries: path traversal optimization (Wave 1), RBAC enforcement (Wave B, complex full-stack, handled merge conflict rebase promptly). |
| Jelani Mwangi | **4** ↑ | Pipeline.yml delivered quickly and cleanly. Critical path item. |
| Linh Pham | 3 | B2 upload/download + deploy.yml delivered. Neutral. |
| Anya Kowalczyk | **4** ↑ | Session hardening: 4 priorities implemented, proper scoping with follow-up issues created for deferred work. All CI green. |
| Nneka Obi | **4** ↑ | Two clean deliveries (docs #680, OAuth fix #713). Fast, precise. |
| Mateo Salazar | **4** ↑ | Full-stack corpus API delivery. Clean, all CI green. |
| Ingrid Lindqvist | **4** ↑ | Two clean deliveries (setTimeout fix #665, search width fix #699). Fast, precise. |
| Marisol Vega-Cruz | 3 | Playwright E2E (19 tests) delivered, but local tarball in lockfile caused CI issue. Good work offset by process issue. Neutral. |
| Ravi Wickramasinghe | 3 | DS integration delivered but package not installable in CI — partially external issue. Neutral. |
| Idris Yusuf | 3 | Not spawned this session. |
| Farhan Malik | 3 | Not spawned this session. |
| Aisling Brennan | 3 | Not spawned this session. |
| Thandiwe Moyo | 3 | Not spawned this session. |

### Orchestrator → design-system Team

| Rated | Score | Reason |
|-------|-------|--------|
| Maeve Callahan (Mgr) | **2** ↓ | Manager stalled — went idle, stopped merging PRs despite being notified. Cross-review PRs sat open until orchestrator merged directly. |
| Keanu Tama | **4** ↑ | Three clean deliveries: CI/coverage (#16), publish config (#18), GH Packages verification (#23). Consistent. |
| Kofi Mensah | 3 | Usage docs delivered clean. Single interaction. Neutral. |
| Beren Yildiz | 3 | Not spawned this session. |
| Others | 3 | Not spawned this session. |

### Orchestrator → landing-page Team

| Rated | Score | Reason |
|-------|-------|--------|
| Marcia Vasquez-Paredes (Mgr) | 3 | Managed LP Wave 1 adequately, merged PRs, handled conflict on #24. Neutral — didn't stall like other managers. |
| Kofi Mensah-Williams | 3 | Multiple deliveries (tests, Dockerfile, deploy pipeline, DS re-integration). Solid but some CI fixes needed. Neutral. |
| Anika Diop-Sarr | 3 | Content PRs delivered with good quality but caused test failures (didn't run tests before push). Neutral — offset by content quality. |
| Cédric Novák | 3 | Not spawned this session. |
| Nazia Rahman | 3 | Not spawned this session. |

### Orchestrator → deploy Team

| Rated | Score | Reason |
|-------|-------|--------|
| Bereket Tadesse | **4** ↑ | TF remote state, deployment docs, and landing page infra — all clean deliveries. Reliable. |
| Lucas Ferreira | 3 | TF CI/CD delivered clean. Single interaction. Neutral. |

---

## Session 4 — Individual Performance Notes

### Done Well / Needs Improvement

| Member | Done Well | Needs Improvement |
|--------|-----------|-------------------|
| **Nadia Khoury** (PD) | Delivered spawn requests with full context, good issue assignment choices | Limited interaction — needs to be more proactive in cross-repo coordination during waves |
| **Santiago Ferreira** (RC) | Batched 4 repos into one efficient agent run, all CI green, zero rework | None this session |
| **Aino Virtanen** (SQL) | Charter decompose was excellent — preserved all content, clean structure. Comms protocol well-designed. | Needs to be present during waves as enforcer (new role established) |
| **Nadia Boukhari** (IG Mgr) | Initial issue assignment and spawn requests were well-structured | **Stalled during execution** — went idle, stopped merging PRs, did not proactively coordinate. Must stay active and merge PRs promptly. Must run post-merge verification. |
| **Arjun Raghavan** | Complex RBAC implementation was backward-compatible. Handled merge conflict rebase quickly. | None this session |
| **Jelani Mwangi** | Fast, clean delivery on critical-path pipeline.yml | None this session |
| **Linh Pham** | B2 scripts and deploy.yml delivered | None this session |
| **Anya Kowalczyk** | Excellent scoping discipline — implemented 4 priorities, created 3 follow-up issues for deferred work. All CI green. | None this session |
| **Nneka Obi** | Two deliveries, both fast and clean | None this session |
| **Mateo Salazar** | Full-stack delivery (backend + frontend) in single PR, clean | None this session |
| **Ingrid Lindqvist** | Two precise fixes, fast turnaround | None this session |
| **Marisol Vega-Cruz** | 19 Playwright tests with good mock strategy | **package-lock.json contained local tarball path** — must verify lockfile doesn't contain /tmp/ or file:/ references before pushing |
| **Ravi Wickramasinghe** | DS integration code was correct | External blocker (GH Packages visibility) was outside control, but should have flagged earlier |
| **Maeve Callahan** (DS Mgr) | Initial wave planning was fine | **Stalled during execution** — went idle, did not merge reviewed PRs, required orchestrator bypass. Same issue as Nadia B. Must stay active. |
| **Keanu Tama** | Three consecutive clean deliveries across the session. Consistent. | None this session |
| **Kofi Mensah** (DS) | Usage docs were thorough and well-structured | None this session |
| **Marcia Vasquez-Paredes** (LP Mgr) | Managed wave adequately, handled merge conflict on PR #24, merged PRs proactively | None this session |
| **Kofi Mensah-Williams** (LP) | Multiple deliveries, solid work | Some CI fixes needed post-PR — should run full test suite before pushing |
| **Anika Diop-Sarr** | Content quality was excellent, pitch deck copy was strong | **Did not run tests before pushing** — content changes broke unit test assertions. Must run `npm test` before creating PR. |
| **Bereket Tadesse** (Deploy Mgr) | Three clean deliveries, reliable | None this session |
| **Lucas Ferreira** | TF CI/CD workflow well-structured | None this session |

---

## Session 5 Trust Updates (2026-04-08) — User Service Extraction Phase 2

### Orchestrator → Org-Level Team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Nadia Khoury (PD) | 3 | **4** ↑ | Comprehensive execution plan with correct parallelism, dependency ordering, merge sequencing, and tech-debt bundling. Stayed alive through entire wave. Valuable process observations. |

### Orchestrator → User-Service Team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Anya Kowalczyk (Tech Lead) | 4 | **5** ↑ | Critical path delivery (JWT + JWKS), largest isnad-graph cleanup (-2220 lines), caught HS256 security issue in peer review. Zero CI failures across 2 repos. Strongest Phase 2 contributor. |
| Mateo Salazar (Engineer) | 4 | 4 | Clean OAuth delivery (23 tests), clean USER node cleanup. Minor divergence on DB session pattern caused merge conflict. Solid but no change warranted. |
| Idris Yusuf (Security Engineer) | 3 | **4** ↑ | Good RBAC implementation (27 tests), thorough security reviews. HS256 fallback was caught in review and fixed promptly. False positive on PR #763 was a process error, not a judgment failure. Net positive. |

### Orchestrator → isnad-graph Team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Nadia Boukhari (Mgr) | 2 | **3** ↑ | Improvement from Session 4 — both reviews were thorough and timely, no stalling. Restored to neutral. |

### Orchestrator Self-Assessment

| Issue | Severity | Action |
|-------|----------|--------|
| Skipped retro before agent shutdown (3rd occurrence) | **Moderate** | Must implement pre-shutdown retro gate. Feedback memory saved. |
| Requestor/Requestee not pre-filled in prompts | **Minor** | Feedback memory saved. Always pre-fill in future prompts. |

### Done Well / Needs Improvement (Phase 2)

| Member | Done Well | Needs Improvement |
|--------|-----------|-------------------|
| **Nadia Khoury** (PD) | Execution plan, tech-debt bundling decisions, process observations | None this phase |
| **Anya Kowalczyk** | Critical path delivery, security review catch, largest cleanup PR | None this phase |
| **Mateo Salazar** | Clean OAuth, thorough USER node cleanup | DB session placement diverged from team pattern (dependencies.py vs database.py) |
| **Idris Yusuf** | RBAC implementation, prompt must-fix response | False positive on PR #763 review (grepped wrong tree), HS256 fallback in initial implementation |
| **Nadia Boukhari** | Timely reviews, no stalling | None this phase (improved) |

---

## Session 6 Trust Updates (2026-04-09) — User Service Extraction Phase 3 Wave 2

### Orchestrator → Org-Level Team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Nadia Khoury (PD) | 4 | 4 | Strong coordination, caught real bugs in reviews (verification stubs, logout regression, Caddy bare-path). /totp planning error offset by transparent ownership. |
| Santiago Ferreira (RC) | 5 | 5 | Exemplary persistence — 6 PRs, 5 deploy attempts, systematic debugging. Already at max. |
| Aino Virtanen (SQL) | 5 | 5 | 10 reviews across 3 repos, caught Dockerfile USER security regression. Already at max. |

### Orchestrator → isnad-graph Team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Anya Kowalczyk (Tech Lead) | 5 | 5 | -866 line removal, bundled 3 issues cleanly. Stub URL errors were minor — fixed in one cycle. Already at max. |
| Mateo Salazar (Engineer) | 4 | 4 | 3 deliveries across 2 repos. Logout regression caught in review, fixed quickly. Solid. |

### Orchestrator → Deploy Team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Lucas Ferreira (SRE) | 3 | **4** ↑ | Clean Caddyfile delivery, immediate /2fa fix when flagged. Reliable first interaction. |

### Orchestrator Self-Assessment

| Issue | Severity | Action |
|-------|----------|--------|
| Missed pre-deploy config audit — env var names and CORS format not verified before first deploy | **Minor** | Add pre-deploy config audit step to deploy prompts. |
| Retro completed before shutdown ✓ | **Positive** | Pattern broken — first wave with retro run on time. |

### Done Well / Needs Improvement (Wave 2)

| Member | Done Well | Needs Improvement |
|--------|-----------|-------------------|
| **Nadia Khoury** | Phased execution plan, thorough reviews, transparent error acknowledgment | /totp prefix assumption propagated to Caddyfile |
| **Santiago Ferreira** | 6 PRs, systematic deploy debugging, fast fix turnaround | Python 3.14 copied from template without checking project target |
| **Aino Virtanen** | 10 reviews, caught USER regression and /2fa mismatch, identified hook bug | None this wave |
| **Anya Kowalczyk** | -866 lines clean removal, bundled 3 issues, fast fix cycle | Verification stub URLs guessed instead of verified |
| **Mateo Salazar** | 3 deliveries, read user-service routes before coding, clean base64 fix | Logout/logoutAll regression — identical behavior not caught before review |
| **Lucas Ferreira** | Clean Caddyfile delivery, immediate fix when flagged | None this wave |

---

## Session 7 Trust Updates (2026-04-10) — Phase 2 Wave 1 (Post-Extraction Stabilization)

### Orchestrator → Org-Level Team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Wanjiku Mwangi (TPM) | 3 | **4** ↑ | 3 PRs (2 bug fixes + dispatcher consolidation), zero must-fix items, all reviews approved on first pass. Dispatcher reduced 12 process spawns to 1. Strongest contributor this wave. |
| Santiago Ferreira (RC) | 5 | 5 | 2 clean PRs (CI workflow + release tagging). CI had pre-existing lint failure (not introduced by his code). Already at max. |
| Aino Virtanen (SQL) | 5 | 5 | 1 PR (label naming hook), reviewed all 7 PRs as second reviewer, all approved. Already at max. |
| Nadia Khoury (PD) | 4 | 4 | 1 PR (Redis health check security fix in deploy), clean delivery. Coordination role adequate. No change. |

### Done Well / Needs Improvement (Phase 2 Wave 1)

| Member | Done Well | Needs Improvement |
|--------|-----------|-------------------|
| **Wanjiku Mwangi** | 3 PRs covering critical bug fixes and major tech-debt (dispatcher). All clean, zero must-fix. | None this wave |
| **Santiago Ferreira** | CI workflow for hooks (new infrastructure), release tagging cadence (process formalization). Both well-documented. | Pre-existing lint issues not caught before merge — CI introduced by his PR fails on his own branch |
| **Aino Virtanen** | Label naming convention hook, 7 reviews as second reviewer. Consistent quality gate. | None this wave |
| **Nadia Khoury** | Redis health check fix (security), coordination of wave execution | None this wave |

---

## Phase 2 Wave 8 Trust Updates (2026-04-17) — CI Hygiene

### Org-Level Team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Wanjiku Mwangi (TPM) | 4 | 4 | 4 PRs across 4 repos for #111 (main #115, isnad-graph #811, user-service #60, design-system #56), all merged clean. Filed high-quality tech-debt issues with forensic detail (#810, #812, #54, etc.). Handled load-bearing breadcrumb retrofit cleanly across session boundary. No negatives. |
| Santiago Ferreira (RC) | 5 | 5 | 3 PRs for #110 (ruff autoformat in pre-commit): isnad-graph #808, user-service #58, data-acquisition #27. Clean delivery after commit-identity roster-blocker unblocked by Steven. Already at max. |
| Aino Virtanen (SQL) | 5 | 5 | Implemented #109 CI gate hook solo (PR #122), caught spec substitution proactively (`gh pr checks --json` → `statusCheckRollup`), reviewed 7 W8 PRs as charter enforcer, zero must-fix items received. Already at max. |
| Nadia Khoury (PD) | 5 | 5 | Light involvement — reviewed PR #122 with thorough spec-fidelity audit. Already at max, no change. |

### Done Well / Needs Improvement (Phase 2 Wave 8)

| Member | Done Well | Needs Improvement |
|--------|-----------|-------------------|
| **Wanjiku Mwangi** (TPM) | Forensic tech-debt filing during #111 sweep (caught hook bugs #113, #118, plus classic-Projects deprecation workaround via REST PATCH). Clean multi-repo delivery. | Had to rework PR bodies post-review when disable-with-followup rule was ratified mid-wave — workflow, not her fault |
| **Santiago Ferreira** (RC) | Batched ruff-format across 3 Python repos efficiently. Review quality matched charter format on all #110 PRs. | Hit commit-identity roster-blocker on 3 of 4 child repos — unblocked by Steven authorizing cross-repo roster merge (long-term fix: #112) |
| **Aino Virtanen** (SQL) | #109 implementation matched existing hook patterns exactly. Handled spec-discrepancy (nonexistent `gh pr checks --json bucket,name,state` flag combo) transparently in PR body. Thorough reviewer across the wave. | None this wave |
| **Nadia Khoury** (PD) | Spec-fidelity review of #122 was executive-quality — validated substitution, checked dispatcher position, flagged program-level concerns (Hook 7 stacking) | Limited involvement — other members carried the wave; appropriate for a wave with tight scope |

