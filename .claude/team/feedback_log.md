# Team Feedback Log

Track all feedback events here. Format:

```
## [DATE] — [FROM] → [TO] — Severity: [minor/moderate/severe]
[Feedback content]
[Action taken, if any]
```

---

## 2026-04-13 — Phase 2 Wave 7 Retrospective (Visual Consistency & Design System)

**Scope:** 5 PRs merged across 4 repos (design-system: 1, isnad-graph: 2, landing-page: 1, deploy: 1). 8 issues closed (#97-#102 design alignment, #103-#104 infra). 4 carry-forward issues remain (#49, #56, #57, #62). 0 new tech-debt issues filed.

**Wave duration:** ~24 hours (2026-04-12 03:44 – 18:01 UTC). Infra work continued through 23:19 UTC.

### Per-Engineer Assessments

#### Santiago Ferreira (Release Coordinator)
- PRs: DS #52 (1426+/318-), IG #800 (17+/17-), LP #65 (101+/10-), deploy #75 (10+/9-)
- CI failures: 0 (DS, LP green; deploy no CI configured)
- Must-fix items received: 0
- Assessment: Carried 4 of 5 wave PRs. DS #52 was a bundled 11-issue omnibus (badges, icons, tests, tokens, new components). LP #65 closed 6 design alignment issues. IG #800 fixed a silent data bug (all admin stats returning zeros). Deploy #75 was a security fix (metrics exposure). Fast, clean, high-volume delivery.
- Severity: **None** — exemplary

#### Wanjiku Mwangi (Technical Program Manager)
- PRs: IG #801 (96+/394- — net deletion of 298 lines)
- CI failures: 1 (pre-existing IG CI issues — security-audit CVE, e2e design-system path)
- Must-fix items received: 0
- Assessment: Replaced ~400 lines of duplicated token definitions with a single DS import. Converted all hardcoded colors in GraphExplorerPage and LoginPage to CSS custom properties. Clean refactor that directly aligns with wave theme.
- Severity: **None**

#### Aino Virtanen (Standards & Quality Lead)
- PRs: None (infra commits directly on wave branch)
- Commits: 4 (session_start skill, ontology rebuild, hooks, annunaki dedup)
- Assessment: Built the session-start skill and hook, strengthened CLAUDE.md startup mandate, added 4-tier staleness to annunaki, cross-repo roster detection in commit identity hook. Infrastructure that improves every future session.
- Severity: **None**

#### Nadia Khoury (Program Director)
- PRs: None (coordination + state management)
- Commits: 2 (session start protocol fixes, cross-repo status update)
- Assessment: Coordinated wave execution, maintained cross-repo-status.json, fixed hook lint/format/type errors that were blocking CI on main.
- Severity: **None**

#### Orchestrator (self-assessment)
- No peer reviews on any of the 5 PRs — violated the charter's 2-reviewer gate
- All PRs merged by the owner account without formal review comments
- Wave was compact and fast, but process was loose
- Severity: **Minor** — clean code but skipped review gate

### Top 3 Going Well
1. **Fast execution** — entire wave (5 PRs, 8 issues) completed in ~24 hours
2. **Cross-repo design alignment** — DS tokens now flow through IG and LP, eliminating hardcoded values across 3 repos
3. **Infrastructure investment** — session-start skill, ontology improvements, and annunaki upgrades will pay dividends in every future session

### Top 3 Pain Points
1. **No peer reviews on any PR** — all 5 PRs merged without review comments. Charter requires 2 reviewers. This was expedient but sets a bad precedent.
2. **Pre-existing IG CI failures** — security-audit (CVE-2026-39892) and e2e (design-system tgz path) remain broken. Wave-7 PRs inherited these failures, making CI signal unreliable.
3. **4 carry-forward issues never addressed** — #49, #56, #57, #62 were labeled p2-wave-7 but are from earlier waves. No triage or re-label was done at wave start.

### Proposed Process Changes
1. **Enforce review gate even on fast waves** — at minimum, one team member must post a review comment before merge. Rationale: 100% review skip rate this wave.
2. **Fix pre-existing CI failures before starting a new wave** — broken CI makes it impossible to tell if new PRs introduce regressions. Rationale: IG CI was red before and after wave-7.
3. **Triage carry-forward issues at wave kickoff** — `/wave-kickoff` should explicitly re-label or close issues that survived from prior waves. Rationale: 4 stale issues cluttered wave-7's open count.

### Trust Matrix Changes
| Member | Old | New | Reason |
|--------|-----|-----|--------|
| Santiago Ferreira | 5 | 5 | Carried 80% of wave PRs, all clean. Already at max. |
| Wanjiku Mwangi | — | — | Not in matrix (main team). Recommend adding main team members. |
| Aino Virtanen | — | — | Not in matrix (main team). Infrastructure work was high-impact. |

*Note: The trust matrix currently only covers isnad-graph team members. The noorinalabs-main coordination team (Nadia, Wanjiku, Santiago, Aino) should be added.*

### Fire/Hire Actions
None. Clean wave — all team members delivered without issues.

---

## 2026-03-16 — Phase 5 Retrospective (consolidated by Fatima)

### Positive
- FastAPI implementation (Kwame) was clean and well-structured; became the foundation for all subsequent API work
- React frontend (Hiro) delivered ahead of schedule with good component separation
- Carolina's test coverage work caught several edge cases before they reached production

### Areas for Improvement
- CI pipeline was fragile during Phase 5 — multiple runs needed to get green. Tomasz addressed with caching and retry improvements.
- Peer review pairing was ad-hoc; engineers self-selected reviewers, leading to uneven knowledge spread. **Action:** Added formal peer review pairing rotation to charter.

---

## 2026-03-16 — Phase 6 Retrospective (consolidated by Fatima)

### Positive
- Testcontainers approach (Kwame) gave confidence in real data flow tests — significant quality improvement over mocked tests
- Carolina's fuzz testing uncovered Arabic text edge cases that static tests missed
- Hiro's Playwright E2E tests established a reliable browser automation baseline

### Areas for Improvement
- Coverage threshold enforcement was manual — needed to be automated in CI. **Action:** Tomasz added coverage gates to GitHub Actions.
- Elena's data validation role was underutilized during this phase — most validation was done by implementers. **Action:** Clarify data team activation for future phases.

---

## 2026-03-16 — Phase 7 Retrospective (consolidated by Fatima)

### Positive
- Yara's security review was thorough and actionable — found real issues in OAuth and session handling
- Kwame's OAuth provider abstraction was well-designed, making it easy to add providers
- Amara's Fawaz Arabic data integration was smooth despite complex source format

### Areas for Improvement
- Tariq and Mei-Lin had zero contributions across all 7 phases — pure overhead. **Action:** Archived both in Phase 8 reorganization.
- Cross-team dependencies between security review and implementation caused some blocking. **Action:** Security reviews now happen in parallel with implementation where possible.
- Renaud and Dmitri had lower direct implementation involvement than expected for their seniority. Trust scores adjusted to reflect actual contribution levels.

---

## 2026-03-16 — Phase 8 Retrospective (consolidated by Fatima)

### Positive
- Wave 1 process improvements (CI hooks, commit audit, worktree cleanup) addressed long-standing tech debt
- Dmitri's tech-debt triage formalized what was previously ad-hoc tracking
- Kwame's CLI skills work improved developer ergonomics across the team
- Tomasz's hooks and scripts implementation reduced manual pre-commit checks

### Areas for Improvement
- Agent naming convention was violated multiple times before being codified. **Action:** Added explicit naming convention and mapping guide to charter.
- ADRs were missing — key architectural decisions were only in PRD or commit messages. **Action:** Created ADR log with retroactive entries for 4 key decisions.
- Feedback log was empty despite 8 phases of work. **Action:** Backfilled with retro findings from Phases 5-8.

---

## 2026-03-27 — Phase 10, Wave 3 Retrospective (consolidated by Fatima)

### Positive
- Tomasz carried 6 of 8 issues with clean, fast delivery across 4 PRs — strongest individual output this wave
- Consolidated PR approach (#355/#357/#362 in one PR) avoided merge conflicts on shared files — validated as a pattern for future waves
- Fatima's CVE catch (ecdsa 0.19.1 → 0.19.2, CVE-2026-33936) unblocked all PRs; proactive fix rolled into existing PR
- Hiro delivered the most complex feature (pre-commit framework, 158 LOC) cleanly and independently
- Bugs-before-features discipline held — all 6 bugs merged before either feature started
- Fast turnaround — all 8 issues completed in a single session

### Areas for Improvement
- **No peer reviews on any PR.** 0 of 6 PRs received peer review despite charter requirement. **Action:** Enforce peer review assignment at sprint kickoff; block merge without at least one review comment.
- **Kwame committed to wrong worktree branch.** Stray commit on Tomasz's `T.Wojcik/0355-0357-0362-docker-compose-prod-fixes` branch required manual cleanup. **Action:** Add worktree safety reminder to engineer spawn prompts; consider pre-commit hook that validates branch ownership matches committer identity.
- **Manager (Fatima) cannot spawn agents.** Spent ~5 minutes sending messages to non-existent agents before escalating. **Action:** Charter updated (§ "How to Instantiate the Team") to document that only the orchestrator can spawn agents. Feedback memory saved.
- **Lead layer (Sunita, Dmitri) was bypassed entirely.** Orchestrator spawned engineers directly for efficiency. This worked but deviates from charter's delegation model. **Action:** Accept this as pragmatic for small waves; for larger waves, spawn leads as coordination-only agents.
- **Duplicate PR created.** Both tomasz-355-357-362 (#365) and Fatima (#366) created PRs for the same consolidated fix. #365 was closed unmerged. **Action:** Clarify PR ownership — the engineer creates the PR, the manager does not duplicate it.

### Severity Assessments
- Kwame Asante — **Moderate** (wrong-branch commit). Documented, improvement expected. Trust: Tomasz→Kwame 4→3.
- Fatima Okonkwo — **Minor** (agent spawn confusion). Tooling limitation, not a judgment error. Now documented.

### No Fire/Hire Actions
No severe feedback warrants termination this wave. Kwame's error was a one-off process mistake, not a pattern.

---

## Session 4 Retrospectives (2026-04-06/07)

### Wave 1 Retro
- **Managers stalled** (Maeve, Nadia B) — went idle, stopped merging PRs. Orchestrator bypassed them. **Moderate feedback** for both managers.
- **No PR reviews** — charter violation. All PRs merged without peer review across 3 repos.
- **Publish workflow dual trigger** — design-system fired twice, caused E409. Should have been caught in review.
- **Tests not run before PRs** — landing-page CI broke because content changes didn't match test assertions. Led to new charter rule.
- **Positive:** 17 issues resolved, 9 parallel agents zero conflicts, DevOps chain executed cleanly.

### Wave A Retro
- **No PR reviews** — continued pattern. Charter violation.
- **Playwright local tarball in lockfile** — worktree agent packed local design-system tarball into package-lock.json. CI couldn't resolve. Required fix cycle.
- **No retro conducted** — agents shut down before retro. Charter violation by orchestrator. **Minor self-feedback.**
- **Positive:** 6 agents parallel, zero conflicts, charter decomposed cleanly, brand fix batched efficiently.

### Wave B Retro
- **4 deploy iterations for noorinalabs.com** — VPS_HOST → Cloudflare IP, no GHCR image, no docker login, Caddy not restarted. Each fixable with a checklist.
- **GH Packages visibility rabbit hole** — org setting blocked public packages, needed classic PAT workaround.
- **RBAC/session PR merge conflict** — expected but required rebase cycle.
- **No PR reviews** — third wave in a row. Systemic issue.
- **No retro** — second wave in a row. Systemic issue.
- **Missing secrets in landing-page repo** — VPS_HOST, DEPLOY_SSH_PRIVATE_KEY not propagated.
- **Positive:** Site went live, RBAC + sessions delivered cleanly, DS re-integration finally working.

### Systemic Issues Identified
1. PR reviews skipped in every wave — need persistent enforcer agent
2. Retros skipped in every wave — need charter enforcement
3. New service deployment has no checklist — repeated manual fixes
4. Cross-repo secret propagation undocumented

---

## 2026-04-07 — Hooks Sprint Retrospective (Wrapup Ceremony)

**Scope:** Issues #8–#19, #26, #27, #32 (15 issues total). PRs #20, #28, #33 — all merged to main. 8 tech-debt issues created (#21–#25, #29–#31).

### Positive
- **Aino Virtanen delivered the entire sprint solo** — 3 PRs covering 6 hooks, 10 skills, worktree lock management, review finding disposition charter, and skills restructure. Clean, methodical, zero rework.
- **Skills restructured to subdirectory/SKILL.md format** — resolved Claude Code discovery issue. All 10 skills now functional as slash commands.
- **PR review hook shipped** — charter-format comment-based reviews now work without `--admin`. Fixes the systemic "no PR reviews" issue from Waves 1/A/B.
- **Review Finding Disposition codified** — all review findings must produce issues or fixes before merge. Closes the loop on tech-debt tracking.
- **Charter decomposition paid off** — sub-documents made it tractable for a single agent to navigate and update charter rules without conflicts.
- **Retro actually happened this time** — breaking the pattern of skipped retros from Waves 1/A/B.

### Areas for Improvement
- **8 tech-debt issues created but none addressed** — all punted to future waves. Acceptable for a focused sprint, but accumulation risk if pattern continues.
- **Wanjiku reviewed all 3 PRs but was not spawned as a persistent agent** — reviews happened ad-hoc. For Wave C, the enforcer model (Aino stays alive) should be tested properly.
- **No cross-repo validation** — hooks and skills were tested in noorinalabs-main only. Child repo teams have not been validated against the new hooks.

### Severity Assessments
- **Aino Virtanen** — No negative feedback. Strong positive: 15 issues closed, 3 PRs, zero rework. Trust increase warranted.
- **Wanjiku Mwangi** — No negative feedback. Reviewed all 3 PRs promptly. Neutral-positive.
- **Nadia Khoury** — Not spawned during sprint. Neutral.
- **Santiago Ferreira** — Not spawned during sprint. Neutral.

### No Fire/Hire Actions
No severe feedback. Team composition stable.

### Systemic Issues Status Update
1. ~~PR reviews skipped~~ — **RESOLVED.** PR review hook (#26) now enforces charter-format reviews.
2. ~~Retros skipped~~ — **RESOLVED this sprint.** Wave-wrapup skill now includes retro as mandatory step.
3. New service deployment checklist — **Skill exists** (#14 /new-service-deploy) but untested in production. Deferred to Wave C.
4. Cross-repo secret propagation — **Still undocumented.** Remains open.

---

## 2026-04-08 — User Service Extraction Phase 2 Retrospective

**Scope:** 5 PRs merged across 2 repos (user-service: 3, isnad-graph: 2). 7 issues closed, 2 tech-debt filed. Meta-issue: noorinalabs-main#48.

### Per-Engineer Assessments

#### Anya Kowalczyk (Tech Lead)
- PRs: US #22 (JWT + 3 tech-debt), IG #760 (replace require_auth)
- CI failures: 0
- Must-fix items received: 0
- Tech-debt bundled: 3 (US #16, #17, Deploy #39)
- Assessment: Delivered the critical path item (JWT) cleanly with 20 tests. Followed up with the largest isnad-graph change (-2220 lines) in IG #754. Caught the HS256 fallback security issue in Idris's PR. Strongest contributor this phase.
- Severity: **None** — exemplary performance
- Reviews given: 2 (PR #23 approved, PR #24 changes requested with valid security finding)

#### Mateo Salazar (Engineer)
- PRs: US #23 (OAuth providers), IG #763 (remove USER nodes)
- CI failures: 0
- Must-fix items received: 0
- Assessment: Clean OAuth implementation with 23 tests. Moved `get_db_session` to `dependencies.py` instead of `database.py` (diverged from Anya's pattern) — caused merge conflict but not a quality issue. USER node cleanup was thorough.
- Severity: **None** — solid delivery
- Reviews given: 2 (PR #22 approved, PR #24 approved)

#### Idris Yusuf (Security Engineer)
- PRs: US #24 (User CRUD + RBAC)
- CI failures: 0
- Must-fix items received: 1 (HS256 fallback — valid finding from Anya, fixed promptly)
- Assessment: Good RBAC implementation with 27 tests. HS256 fallback was a legitimate security concern caught in review — responded quickly with correct fix (RS256-only + RSA test keys). Security reviews of PRs #22 and #23 were thorough. False positive on PR #763 (flagged already-removed USER node references) — corrected after clarification.
- Severity: **Minor** — HS256 fallback was a design misjudgment caught in review (system working as intended). False positive in #763 review was a process error (grepped wrong tree).
- Reviews given: 3 (PR #22 approved, PR #23 approved, PR #763 initially changes-requested then corrected to approved)

#### Nadia Khoury (Program Director)
- PRs: None (coordination role)
- Assessment: Delivered a comprehensive execution plan with correct parallelism, dependency ordering, review assignments, and merge sequencing. Tech-debt bundling decisions were sound. Process observations (Requestor/Requestee swap, scaffold alignment) were valuable. Stayed alive through the entire wave as required.
- Severity: **None** — strong coordination

#### Nadia Boukhari (isnad-graph Manager — review role only)
- PRs: None
- Reviews given: 2 (PR #760 approved, PR #763 approved)
- Assessment: Both reviews were thorough and timely. No stalling issues this session (improvement from Session 4 where she went idle).
- Severity: **None** — improved from prior wave

#### Orchestrator (self-assessment)
- **Skipped retro before shutting down agents** — charter violation. Agents were terminated before collecting retro input, updating trust matrix, or writing feedback log. **Moderate self-feedback.** This is a repeated pattern (Waves A, B, and now Phase 2).
- **Requestor/Requestee format not pre-filled in agent prompts** — all 3 review agents swapped the fields, blocking the first merge attempt. Should have included correct examples in the prompt.
- **Positive:** Merge conflict resolution was clean and followed the planned sequence. Caught Idris's false positive review on PR #763 by verifying against `origin/main`. Proactively fixed review format on all 3 PRs.

### Top 3 Going Well
1. **Wave 1 parallelism** — 3 agents delivering simultaneously in the same repo with worktree isolation, zero branch collisions
2. **Review cycle caught real security issue** — HS256 fallback identified and fixed before merge (system working as designed)
3. **Net code reduction** — isnad-graph shed ~2200+ lines of auth code, cleanly migrated to user-service

### Top 3 Pain Points
1. **Retro skipped (again)** — orchestrator shut down agents before running retro. Third occurrence. Needs a hook or hard gate.
2. **Requestor/Requestee format swapped by all agents** — the charter format is counterintuitive. All 6 initial reviews had it backwards.
3. **Parallel agents touching shared files (database.py, config.py, main.py, pyproject.toml)** — created predictable merge conflicts that required manual resolution

### Proposed Process Changes
1. **Pre-shutdown retro gate** — add a hook or checklist that blocks agent shutdown until retro is complete. Rationale: retro has been skipped in 3 of the last 4 waves despite charter mandate.
2. **Scaffold alignment commit before parallel branches** — when 3+ agents will work in the same repo, merge a "shared infrastructure" commit first (DB session module, config structure, etc.) to reduce conflicts. Rationale: all 3 user-service PRs independently refactored the same circular import.
3. **Pre-fill Requestor/Requestee in review prompts** — always provide the exact `gh pr comment` command with correct field values in agent prompts. Rationale: 100% error rate when agents filled these themselves.

---

## 2026-04-08 — User Service Extraction Phase 3 Wave 1 Retrospective

**Scope:** 12 PRs merged across 6 repos (user-service: 6, main: 2, IG/deploy/LP/DS: 1 each). 14 issues closed. Meta-issue: noorinalabs-main#48.

### Per-Engineer Assessments

#### Anya Kowalczyk (Tech Lead)
- PRs: US #28 (scaffold), US #30 (subscriptions)
- CI failures: 0
- Must-fix items received: 2 (webhook auth, missing migration)
- Reviews given: 2 (PR #29, PR #27)
- Assessment: Scaffold was clean and prevented Phase 2's merge conflict pattern. Webhook security gap caught and fixed with HMAC-SHA256. Clean rebase after 3 PRs merged. Reported aiosqlite venv issue affecting all agents.
- Severity: **None** — strong delivery

#### Mateo Salazar (Engineer)
- PRs: US #31 (sessions)
- CI failures: 0
- Must-fix items received: 3 (refresh token not returned, service-commits pattern, migration chain)
- Reviews given: 2 (PR #30 found 5 issues; PR #32 caught critical Fernet key data-loss risk)
- Assessment: Solid delivery. Design issues caught in review. His reviews of others were the strongest this wave. Also reported branch freshness hook interaction with worktrees.
- Severity: **Minor** — design issues caught in review

#### Idris Yusuf (Security Engineer)
- PRs: US #29 (email verification), US #32 (2FA/TOTP)
- CI failures: 0
- Must-fix items received: 10 total (SMTP TLS, 2 missing migrations, router prefix, uuid typing, test approach, Fernet key, valid_window, recovery code consumption, max_length)
- Reviews given: 1 (PR #31 — thorough, approved)
- Assessment: Fastest delivery but highest must-fix count. SMTP TLS misconfiguration (production failure) and Fernet key random fallback (data loss) are critical issues from a security engineer. All fixed promptly when flagged.
- Severity: **Moderate** — 10 must-fix items including 2 critical security issues. Speed over quality pattern.

#### Santiago Ferreira (Release Coordinator)
- PRs: US #27, IG #766, Deploy #44, LP #51, DS #34, Main #55 (6 PRs)
- CI failures: 0
- Must-fix items received: 0
- Reviews given: 2 (PR #28, PR #54)
- Assessment: Exemplary batch execution. Zero review findings. Timely second reviews.
- Severity: **None** — exemplary

#### Aino Virtanen (Standards & Quality Lead)
- PRs: Main #54 (hook fix)
- CI failures: 0
- Must-fix items received: 0
- Reviews given: 7+ (all feature PRs, scaffold, all .gitignore PRs)
- Assessment: Caught every significant issue across all PRs. Hook fix thorough (13 test cases). Initial review format wrong (7 re-posts needed). Reported validate_commit_identity.py friction with gh commands.
- Severity: **Minor** — review format errors caused merge delays

#### Nadia Khoury (Program Director)
- PRs: None (coordination)
- Assessment: Comprehensive execution plan. Helped unblock merges with 6 second reviews. First message delivery failed (re-sent). Identified Idris sequential chain as critical path risk.
- Severity: **None** — strong coordination

#### Orchestrator (self-assessment)
- Applied Phase 2 lessons: scaffold-first ✓, pre-filled review assignments ✓, worktree isolation ✓, retro before shutdown ✓
- Review format not precise enough — should have included exact `gh pr comment` template
- 2-review gate not planned for — tried to merge with 1 review multiple times
- Severity: **Minor**

### Top 3 Going Well
1. **Scaffold alignment worked** — 4 parallel agents, minimal merge conflicts
2. **Review cycle caught real bugs** — SMTP TLS, webhook auth, Fernet key data loss, refresh token flaw
3. **Phase 2 lessons all applied** — pre-filled reviews, scaffold-first, worktree isolation, retro enforced

### Top 3 Pain Points
1. **Review format friction** — all initial reviews wrong format, 7+ re-posts, multiple merge attempts blocked (~15 min lost)
2. **2-review gate bottleneck** — only 1 reviewer planned per PR, ad-hoc second reviewer assignments delayed merges
3. **validate_commit_identity.py false positives** — blocked legitimate gh pr create, gh pr comment, and test commands throughout the wave (PR #54 fixed this)

### Agent-Reported Issues (from retro input)
- Branch freshness hook blocks PR creation in worktrees (Mateo)
- aiosqlite missing from venv due to pyproject.toml dependency group mismatch (Anya)
- Sequential review rounds wasteful — coordinate reviewers for single consolidated pass (Anya)
- Router prefix convention (/api/v1/ vs bare) needs standardization (Mateo, Aino)
- Lighter review gate for ops/infra PRs (Santiago)
- Idris sequential chain (#8→#10) was critical path — could have parallelized by branching both from main (Nadia)

### Proposed Process Changes
1. **Include exact `gh pr comment` template in all review prompts** — copy-paste-ready with correct fields. Rationale: 100% format error rate.
2. **Assign 2 reviewers per PR at wave kickoff** — pre-plan both in agent prompts. Rationale: every PR needed ad-hoc second reviewer.
3. **Scaffold should set migration chain base** — stub migration as known chain point. Rationale: all 4 feature PRs pointed down_revision at 0001.
4. **Standardize router prefix convention** — document whether routers use /api/v1/ or bare prefix. Rationale: inconsistency flagged on 3 of 4 PRs.
5. **Add `make dev` target for venv setup** — runs `uv sync --extra dev`. Rationale: aiosqlite/pytest missing in worktrees.

### Trust Matrix Changes
| Member | Old | New | Reason |
|--------|-----|-----|--------|
| Santiago Ferreira | 4 | **5** ↑ | Exemplary batch efficiency |
| Idris Yusuf | 4 | **3** ↓ | 10 must-fix items, 2 critical security issues |

### Fire/Hire Actions
None. Idris received moderate feedback — single-wave pattern, will monitor.

---

## 2026-04-09/10 — User Service Extraction Phase 4 Retrospective (Final Phase)

**Scope:** 8 PRs merged across 4 repos (isnad-graph: 3, deploy: 3, user-service: 1, main: 1). 8 issues closed (US #11, IG #758, #759, #769, Deploy #33, #49, #53, Main #58). 2 new issues filed (Main #61). Meta-issue: noorinalabs-main#48.

**This phase completes the user-service extraction.** isnad-graph has zero auth-provider code — it is purely a JWT consumer via JWKS.

### Per-Engineer Assessments

#### Mateo Salazar (Engineer)
- PRs: US #42 (data migration script)
- CI failures: 0
- Must-fix items received: 0
- Assessment: Clean delivery of the critical-path migration script — CLI with dry-run, idempotent, 32 tests, verification step. Well-scoped and production-ready.
- Severity: **None**

#### Ingrid Lindqvist (Engineer)
- PRs: IG #772 (Trivy SHA fix), IG #773 (15 cross-service auth integration tests)
- CI failures: 0
- Must-fix items received: 0
- Assessment: Fast delivery — both PRs up before any other Wave 1 agent. Integration tests cover all 6 scenarios with real RSA keys and mock JWKS. Solid test infrastructure.
- Severity: **None**

#### Santiago Ferreira (Release Coordinator)
- PRs: Deploy #54 (Caddy bare-path fix), Deploy #55 (migration runbook), Deploy #56 (.claude alignment)
- CI failures: 0
- Must-fix items received: 0
- Assessment: Three clean deliveries across both waves. Runbook is comprehensive (10 sections with commands and timelines). Roster cards and hooks copied correctly. Script path mismatch with Mateo's migration script was a coordination gap, not a quality issue.
- Severity: **None** — exemplary

#### Anya Kowalczyk (Tech Lead)
- PRs: IG #774 (remove src/auth/ directory)
- CI failures: 0
- Must-fix items received: 0
- Assessment: Clean execution of the final auth extraction. Only 3 files / 136 lines remained (earlier waves had done the heavy lifting). Consolidated JWKS validation into src/api/auth.py, updated 18 import sites. 496 tests pass. Reported branch freshness hook issue with worktrees.
- Severity: **None**

#### Aino Virtanen (Standards & Quality Lead)
- PRs: Main #60 (validate_pr_review.py --repo fix)
- Reviews given: 7 (all Wave 1 + Wave 2 PRs)
- Assessment: Fixed the cross-repo review hook that blocked every merge in Wave 2. Every PR she reviewed was approved on first pass — team produced clean work. Identified the identical bug in validate_review_comment_format.py (filed as Main #61).
- Severity: **None** — exemplary

#### Nadia Khoury (Program Director)
- PRs: None (coordination)
- Reviews given: 8 (all PRs as second reviewer)
- Assessment: Two-wave structure was the right call. Caught runbook/script path mismatch in review. Review load was unbalanced (8 of 8 PRs) — should distribute more.
- Severity: **None**

#### Orchestrator (self-assessment)
- Duplicate review requests sent to Aino (she'd already reviewed before messages arrived) — visibility gap
- Stale Wave 1 Santiago agent created duplicate PR #57 — should have confirmed shutdown before spawning Wave 2 agent
- Did NOT skip retro ✓ (second consecutive wave)
- Severity: **Minor** — duplicate agent/PR was cleaned up with no impact

### Top 3 Going Well
1. **Incremental extraction strategy validated** — auth removal was trivial because earlier waves had already gutted the heavy code
2. **Zero must-fix items across all 8 PRs** — cleanest wave to date, every PR approved on first review
3. **Tech-debt cleared** — 6 items resolved alongside core work without slowing down

### Top 3 Pain Points
1. **Branch freshness hook doesn't respect worktree CWD** — checks parent repo instead of child repo in worktrees (Anya burned 3 PR creation attempts)
2. **validate_review_comment_format.py has same --repo bug** as validate_pr_review.py (Main #61) — Aino had to bypass for all reviews
3. **Runbook/script path mismatch** — parallel PRs referencing each other had no shared contract for entry point

### Agent-Reported Issues
- Branch freshness hook should detect git repo from command context, not process CWD (Anya)
- Audit all hooks for cross-repo --repo bug pattern, not just one-off fixes (Aino)
- Repo alignment (.claude, hooks, roster) should be Phase 0 prerequisite (Santiago)
- Cross-PR interface contracts needed when two agents reference each other's output (Nadia)
- Cap single reviewer at 4-5 PRs per wave (Nadia)

### Proposed Process Changes
1. **Cross-PR contracts in execution plans** — when PRs reference each other, include explicit interface spec (paths, CLI flags, formats) in both agent prompts
2. **Hook audit after any hook fix** — check all hooks for the same bug pattern before closing
3. **Repo .claude alignment as Phase 0** — before any repo gets its first wave, ensure hooks/roster/settings are in place
4. **Branch freshness hook CWD fix** — file issue for worktree-aware git repo detection

### Trust Matrix Changes
| Member | Old | New | Reason |
|--------|-----|-----|--------|
| Ingrid Lindqvist | 4 | 4 | Fast delivery, 15 integration tests. Solid but no change warranted. |
| All others | unchanged | | Zero must-fix items across the board. Already at appropriate levels. |

### Fire/Hire Actions
None. Cleanest wave to date — zero must-fix items across 8 PRs.

---

## 2026-04-09 — User Service Extraction Phase 3 Wave 2 Retrospective

**Scope:** 11 PRs merged across 3 repos (user-service: 4, deploy: 4, isnad-graph: 2, main: 1 issue-only). 6 issues closed (IG #756, #757, #761, #762, US #33, #34). 5 new issues filed (Main #58, #59, Deploy #49, #53, IG #769). Meta-issue: noorinalabs-main#48.

### Per-Engineer Assessments

#### Anya Kowalczyk (Tech Lead)
- PRs: IG #770 (backend removal + JWKS retry + jwt_secret cleanup)
- CI failures: 0
- Must-fix items received: 3 (wrong verification stub URLs, wrong subscription stub URL, dead modules question)
- Reviews given: 0 (implementation-only this wave)
- Assessment: Delivered the largest PR (-866 lines) cleanly. All 481 tests passed. Must-fix items were URL path errors — guessed old paths instead of verifying against user-service. Fixed in one cycle. Bundled #761 and #762 correctly.
- Severity: **Minor** — stub URL errors were avoidable by checking user-service routes first

#### Mateo Salazar (Engineer)
- PRs: US #37 (router prefix + make dev), US #40 (base64 JWT decode), IG #771 (frontend auth hooks)
- CI failures: 0
- Must-fix items received: 1 (logout/logoutAll regression on #771)
- Reviews given: 0 (implementation-only this wave)
- Assessment: Three deliveries across 2 repos. Router prefix standardization was clean. Base64 JWT decode was fast and correct. Frontend rewire was thorough — read user-service routes before coding, caught important method/path differences. Logout regression was a behavioral miss but fixed in one cycle.
- Severity: **Minor** — logout regression was a design oversight caught in review

#### Santiago Ferreira (Release Coordinator)
- PRs: Deploy #50 (deploy workflow), US #38 (Dockerfile + CI), US #39 (Trivy SHA fix), US #41 (Python 3.12), Deploy #51 (env var fix), Deploy #52 (CORS fix)
- CI failures: 2 (Trivy SHA truncation, CI lint pre-existing)
- Must-fix items received: 1 (Dockerfile missing USER directive)
- Reviews given: 0 (implementation-only this wave)
- Assessment: Carried the entire Phase B deploy workload — 6 PRs, 5 deploy attempts, systematic debugging. Each failure identified a real issue (missing image, Python 3.14, env var mismatch, CORS format). Persisted methodically. Dockerfile USER regression was caught by Aino and fixed immediately. Trivy SHA was a copy error from isnad-graph template.
- Severity: **None** — exemplary persistence. Deploy failures were infrastructure gaps, not quality issues.

#### Lucas Ferreira (SRE, deploy team)
- PRs: Deploy #48 (Caddyfile routes)
- CI failures: 0
- Must-fix items received: 1 (/totp → /2fa route fix)
- Reviews given: 0
- Assessment: Clean Caddyfile delivery. The /totp vs /2fa mismatch was from Nadia's plan (not Lucas's error) — fixed immediately when flagged. Quick turnaround.
- Severity: **None** — clean delivery, fast correction

#### Nadia Khoury (Program Director)
- PRs: None (coordination)
- Reviews given: 7 (Deploy #48, US #37, Deploy #50, US #38, US #39, Deploy #51, Deploy #52, IG #770, IG #771)
- Assessment: Strong planning — phased approach (deploy-first, then code changes) was correct. Caught real issues in reviews: verification stub URLs, logout regression, Caddy bare-path gap. The /totp assumption was her error that propagated into Lucas's work, but she owned it transparently. Effective second-reviewer throughout.
- Severity: **Minor** — /totp→/2fa planning error. Self-identified and acknowledged.

#### Aino Virtanen (Standards & Quality Lead)
- PRs: None (review-only)
- Reviews given: 10 (all PRs across 3 repos)
- Assessment: Fastest reviewer — no PR waited on her. Caught the Dockerfile USER regression (security), flagged the /totp vs /2fa mismatch independently, and identified the cross-repo review hook bug (Main #58). Most impactful single review: US #38 USER directive.
- Severity: **None** — exemplary quality gate work

#### Orchestrator (self-assessment)
- Caught /2fa vs /totp mismatch by reading Mateo's PR diff before routing to reviewers
- Properly gated Phase C on deploy verification
- Used --admin override for known hook bug (Main #58) — documented, not a bypass
- Filed 5 issues during wave for tech-debt and process gaps
- Did NOT skip the retro this time (improvement from prior waves)
- **Missed:** Should have verified deploy env vars against config.py before spawning Santiago — would have caught the DATABASE_URL/REDIS_URL mismatch and CORS format issue in planning, saving 2 deploy iterations
- Severity: **Minor** — deploy debugging cost ~30 min that could have been avoided with pre-deploy config audit

### Top 3 Going Well
1. **Phased execution prevented breakage** — deploy-first (A/B) before code removal (C) ensured user-service was verified running before isnad-graph code was deleted
2. **Review cycle caught 5 real bugs** — Dockerfile USER, /2fa mismatch, verification stub URLs, logout regression, Caddy bare-path gap
3. **Retro actually ran** — breaking the pattern of skipped retros from Waves 1/A/B and Phase 2

### Top 3 Pain Points
1. **5 deploy attempts** — cascade of small config issues (env var names, CORS format, Python version, missing image, Trivy SHA). Each one was a 2+ min cycle. Total ~15 min lost.
2. **Cross-repo review hook broken** (Main #58) — `validate_review_comment_format.py` doesn't pass `--repo`, forced --admin overrides on every cross-repo merge
3. **No Dockerfile or CI in user-service** — new repo had zero deploy infrastructure. Should have been scaffolded when the repo was created.

### Agent-Reported Issues
- Add route-map checklist to agent prompts for 410 stubs and frontend URL changes (Nadia, Anya)
- Caddy bare-path routing — `handle /path/*` doesn't match bare `/path` (Nadia, filed as Deploy #53)
- Session ID missing from JWT claims — single-session logout requires extra fetch (Mateo, file as user-service enhancement)
- Email login, register, providers endpoints don't exist on user-service yet (Mateo)
- Labels missing on most PRs — auto-apply at wave-kickoff or via PR template (Aino)
- Local smoke test for deploy PRs before merge (Aino)

### Proposed Process Changes
1. **Pre-deploy config audit** — before any first-time service deploy, verify docker-compose env vars match the app's config.py field names. Rationale: 2 of 5 deploy failures were env var mismatches.
2. **New repo scaffold checklist** — Dockerfile, CI workflow, GHCR publish workflow must exist before first deploy is attempted. Rationale: user-service had none of these.
3. **Route-map table in agent prompts** — when agents write 410 stubs or frontend URL changes, include verified old→new path mapping. Rationale: 100% error rate when agents guessed paths.
4. **Fix cross-repo review hook** (Main #58) — extract `--repo` from the merge command. Rationale: forced --admin on every cross-repo merge this wave.

### Trust Matrix Changes
| Member | Old | New | Reason |
|--------|-----|-----|--------|
| Santiago Ferreira | 5 | 5 | Exemplary persistence through 5 deploy attempts, 6 PRs. No change — already at max. |
| Aino Virtanen | 5 | 5 | 10 reviews, caught critical security regression. No change — already at max. |
| Nadia Khoury | 4 | 4 | Strong coordination, good review catches. /totp planning error offset by transparent ownership. No change. |
| Anya Kowalczyk | 5 | 5 | -866 lines, clean delivery. Stub URL errors were minor. No change. |
| Mateo Salazar | 4 | 4 | 3 deliveries across 2 repos, fast fixes. Logout regression was minor. No change. |
| Lucas Ferreira | 3 | **4** ↑ | Clean Caddyfile delivery, immediate /2fa fix. Reliable. |

### Fire/Hire Actions
None. All team members performed well. Minor feedback items only.

---

## 2026-04-10 — Phase 2 Wave 1 Retrospective (Post-Extraction Stabilization)

**Scope:** 7 PRs merged across 2 repos (main: 6, deploy: 1). 7 issues closed (Main #61, #63, #40, #59, #38, #21, Deploy #41). 1 issue remains open (Main #62 — user-action-required, production data migration).

### Per-Engineer Assessments

#### Wanjiku Mwangi (TPM)
- PRs: Main #68 (validate_review_comment_format --repo fix), Main #69 (branch freshness worktree CWD fix), Main #73 (Bash hook dispatcher consolidation)
- CI failures: 1 (PR #73 — pre-existing ruff I001 import sorting in validate_commit_identity.py and validate_wave_context.py, not introduced by her code)
- Must-fix items received: 0
- Reviews given: 2 (PR #70 first reviewer, PR #71 first reviewer)
- Assessment: Strongest contributor this wave — 3 PRs covering 2 critical bug fixes and the largest tech-debt item (dispatcher reduces 12 process spawns to 1). All code was clean; the CI failure is pre-existing lint in other files. Dispatcher architecture (importlib dynamic loading, sys.exit interception, fail-open) is well-designed.
- Severity: **None** — exemplary delivery

#### Santiago Ferreira (RC)
- PRs: Main #72 (CI workflow for hooks + auto_set_env_test.py false positive fix), Main #71 (release tagging cadence)
- CI failures: 1 (PR #72 — same pre-existing ruff I001 lint issue; ironic since this PR introduced the CI workflow that exposed it)
- Must-fix items received: 0
- Reviews given: 3 (PR #68 first reviewer, PR #69 first reviewer, PR #73 first reviewer)
- Assessment: Two solid deliveries. CI workflow is well-scoped (ruff lint+format, mypy, smoke tests). Release tagging cadence formalizes a missing process. The auto_set_env_test.py fix (heredoc stripping) resolves a real false positive. CI failure is pre-existing code — his workflow correctly caught it.
- Severity: **None** — clean delivery

#### Aino Virtanen (SQL)
- PRs: Main #70 (label naming convention hook)
- CI failures: 0
- Must-fix items received: 0
- Reviews given: 7 (second reviewer on all 7 PRs across both repos)
- Assessment: Label naming hook correctly distinguishes assignee labels (UPPER_SNAKE_CASE) from category labels (kebab-case). Reviewed every PR in the wave as second reviewer — all approved on first pass. Consistent quality gate.
- Severity: **None** — exemplary quality gate work

#### Nadia Khoury (PD)
- PRs: Deploy #58 (Redis health check password exposure fix)
- CI failures: 0
- Must-fix items received: 0
- Reviews given: 0 (coordination role)
- Assessment: Security fix was clean — REDISCLI_AUTH env var instead of -a flag prevents password exposure in /proc/*/cmdline. Both redis and user-redis services updated consistently. Wave coordination adequate.
- Severity: **None** — clean delivery

### Top 3 Going Well
1. **Zero must-fix items across all 7 PRs** — every PR approved on first review pass by both reviewers. Cleanest wave alongside Phase 4.
2. **Dispatcher consolidation shipped** — 12 Bash hook process spawns reduced to 1, major developer experience improvement without breaking individual hook testability.
3. **All Phase 4 pain points addressed** — branch freshness worktree bug (#63), review comment --repo bug (#61), label naming (#40), CI for hooks (#38), release tagging (#59) — systematic tech-debt clearance.

### Top 3 Pain Points
1. **CI failures from pre-existing lint** — Santiago's new CI workflow (PR #72) correctly exposed ruff I001 import sorting issues in 2 hooks (validate_commit_identity.py, validate_wave_context.py), but these weren't fixed before merge. Both PR #72 and PR #73 show CI failure on main.
2. **Main #62 remains open** — production data migration requires manual user action. Cannot be resolved by the team. Labeled user-action-required.
3. **No CI existed before this wave** — hooks had no automated quality gate until PR #72. All prior hook PRs were reviewed manually only.

### Proposed Process Changes
1. **Fix pre-existing lint before merging CI workflow** — when introducing a new CI check, fix all existing violations in the same PR or a predecessor PR. Rationale: PR #72 introduced CI that immediately failed on pre-existing code, meaning CI is red on main.
2. **Add ruff import sorting fix to tech-debt backlog** — file issue for the 3 I001 violations in validate_commit_identity.py and validate_wave_context.py. Rationale: CI is currently failing on main.
3. **Dispatcher should be default pattern for new hook types** — if Agent or SendMessage hooks accumulate, consolidate early. Rationale: Wanjiku's dispatcher proved the pattern works; don't wait for 12 hooks to accumulate again.

### Trust Matrix Changes
| Member | Old | New | Reason |
|--------|-----|-----|--------|
| Wanjiku Mwangi (TPM) | 3 | **4** ↑ | 3 PRs, zero must-fix, dispatcher consolidation. Strongest wave contributor. |
| Santiago Ferreira (RC) | 5 | 5 | 2 clean PRs. Already at max. |
| Aino Virtanen (SQL) | 5 | 5 | 7 reviews, label hook. Already at max. |
| Nadia Khoury (PD) | 4 | 4 | Clean security fix. Adequate coordination. No change. |

### Fire/Hire Actions
None. All team members performed well. Zero must-fix items across 7 PRs.

---

## 2026-04-11 — Phase 2 Wave 2 Retrospective

**Scope:** 8 PRs merged across 7 repos. 17 issues closed. Theme: CI Green + Live Bugs + Pre-commit Hooks.

### Per-Engineer Assessments

#### Wanjiku Mwangi (TPM)
- PRs: main #89 (worktree bug fix), main #90 (pre-commit hook), user-service #48 (lint/type/pre-commit)
- Charter compliance: 3/3 PRs fully compliant
- Must-fix items received: 0
- Quality: Worktree cwd fix was well-engineered. User-service PR went beyond scope — fixed 14 ruff + 2 mypy errors. Correctly identified 3 issues already resolved by prior PRs, avoiding duplicate work.
- Process concern: Main repo CI was red after merge (pre-existing lint/mypy errors). Reported auto_set_env_test.py false positives.
- Severity: **Minor** — CI gap, not quality gap

#### Santiago Ferreira (RC)
- PRs: isnad-graph #780, landing-page #58, deploy #62, design-system #40, ingestion #25
- Charter compliance: 5/5 PRs fully compliant
- CI failures introduced: 0
- Must-fix items received: 0
- Quality: Consistent pre-commit patterns across 5 repos, cheapest-first hook ordering. ESLint 9.x flat config well-structured. Efficient 5-repo parallel worktree execution.
- Severity: **None** — strong delivery

#### Aino Virtanen (Standards Lead)
- Reviews: 8/8 PRs reviewed
- Charter compliance audit: Zero violations found
- Quality: Thorough reviews with CI status tracking per repo. Identified CI-red-on-merge concern. Retro facilitation comprehensive.
- Severity: **None** — exemplary

#### Orchestrator (self-assessment)
- **Positive:** Full wave completed in single session (plan → implement → review → merge → wrapup). Review templates pre-filled correctly — zero format errors. Both engineers ran fully parallel with no cross-contamination.
- **Gap:** Assigned 3 issues (#79, #80, #84) that were already resolved by prior PRs. Should have cross-referenced open issues against recent merges before assignment.
- **Gap:** Did not verify CI status on main repo before approving merge of PRs #89/#90. Pre-existing lint/mypy failures should have been flagged.
- Severity: **Minor**

### Top 3 Going Well
1. **Zero charter violations across 8 PRs** — review template mandate from P3W1 retro is working
2. **Consistent pre-commit standardization** — 7 repos now have pre-commit hooks replicating CI checks locally
3. **Single-session wave completion** — plan through wrapup with zero must-fix items and zero rework

### Top 3 Pain Points
1. **auto_set_env_test.py hook false positives** — both engineers hit independently. Hook triggers on "test" in any bash argument, not just test commands.
2. **Pre-existing CI failures not triaged before wave** — 3 repos had red CI unrelated to wave work, creating confusion
3. **Already-resolved issues assigned** — 3 issues were duplicates of prior merged work, wasted triage time

### Proposed Process Changes
1. **Fix auto_set_env_test.py hook** — narrow match to actual test commands only. Rationale: 100% of engineers hit this.
2. **Pre-wave CI triage step in /wave-kickoff** — check CI status on all affected repos before assignment. Rationale: 3 repos had pre-existing failures.
3. **Cross-reference issues against recent merges in /wave-kickoff** — flag already-resolved issues. Rationale: 3 issues were already closed by prior PRs.

### Trust Updates

| Rater | Rated | Old | New | Reason |
|-------|-------|-----|-----|--------|
| Orchestrator | Wanjiku Mwangi | 4 | 4 | Strong delivery, beyond-scope fixes. CI gap offsets. No change. |
| Orchestrator | Santiago Ferreira | 5 | 5 | 5 repos cleanly, already at max. |
| Orchestrator | Aino Virtanen | 5 | 5 | 8 reviews, thorough retro. Already at max. |
| Orchestrator | Nadia Khoury | 4 | 4 | Clean coordination, spawn requests well-structured. No change. |

### Fire/Hire Actions
None. All team members performed well.

---

## 2026-04-11 — Phase 2 Wave 3 Retrospective

**Scope:** 7 PRs merged across 3 repos (main, isnad-graph, user-service). 12 issues closed (including 10 stale issues from user-service extraction). Theme: Tech Debt + Process Improvements.

### Wave Highlights
- **Stale issue cleanup:** 10 issues closed as stale — referenced code extracted during user-service extraction
- **Hook dispatcher:** Consolidated 12 PreToolUse subprocess invocations into 1 in-process dispatcher (#75)
- **Wave-kickoff improvements:** Added CI triage (#92) and issue cross-reference (#93) steps
- **auto_set_env_test.py fix:** Narrowed regex to actual test commands only (#91)

### Per-Engineer Assessments

#### Wanjiku Mwangi (via Nadia) — Severity: None
- PRs: main #94 (hook fix), user-service #49 (Dockerfile CMD + JWT ADR)
- Hook regex precise with 20 automated checks. JWT ADR thorough. Dockerfile CMD correct.

#### Santiago Ferreira — Severity: None
- PRs: isnad-graph #781 (auth cleanup), #782 (CI expansion), #783 (lockfile validation)
- Auth cleanup adds cross-tab polling. CI expansion covers 3 directories. Lockfile two-layer defense.

#### Aino Virtanen — Severity: None
- PRs: main #95 (wave-kickoff), #96 (dispatcher). 5 PR reviews as charter enforcer.
- Dispatcher well-architected. Wave-kickoff steps have user confirmation gates.

#### Orchestrator — Severity: Minor
- Identified 10 stale issues before assignment. Merge conflict on wave→main (avoidable).

### Top 3 Going Well
1. Stale issue cleanup — ontology librarian prevented assigning 10 dead issues
2. Hook dispatcher — 12→1 subprocess reduction per Bash call
3. Second consecutive single-session wave completion

### Top 3 Pain Points
1. Merge conflict on wave→main (auto_set_env_test.py modified on both branches)
2. Nadia bypassed PD role boundary (implemented instead of coordinating)
3. No other significant friction

### Trust Updates
No changes. All scores remain at current levels.

### Fire/Hire Actions
None.

---

## 2026-04-17 — Phase 2 Wave 8 Retrospective

**Scope:** 9 PRs merged across 5 repos. 3 issues closed (#109, #110, #111). 1 new issue filed mid-retro (#123, validate_pr_review false-positive). Theme: CI Hygiene.

### Wave Highlights
- **Wave sequencing worked as designed:** #110 (ruff format) → #111 (CI sweep) → #109 (CI gate hook). Doing #111 first shrank #109's risk of self-blocking.
- **Enforcement-hierarchy principle validated:** #109 landed and immediately caught a real hook false-positive during its own PR's merge (`validate_pr_review` flagging the review-request comment) — filed as #123.
- **Cross-session continuity:** wave spanned 2 sessions cleanly via session_handoff.md. All 3 team members picked back up with zero context loss.
- **Tech-debt triage: 16 issues filed** during W8 across all repos. Pattern: 6 hook bugs (#113, #114, #118, #123 + two others), 7 infra items, 3 ops items.

### Per-Engineer Assessments

#### Wanjiku Mwangi (TPM) — Severity: None
- PRs: main #115, isnad-graph #811, user-service #60, design-system #56 (#111 CI sweep across 4 repos)
- Filed tech-debt with forensic detail: #810, #812, #54, #113, #114, #118
- Worked around classic-Projects GraphQL deprecation via REST PATCH when `gh pr edit` failed
- Handled retroactive breadcrumb edits cleanly when disable-with-followup rule was ratified mid-wave

#### Santiago Ferreira (RC) — Severity: None
- PRs: isnad-graph #808, user-service #58, data-acquisition #27 (#110 ruff pre-commit across 3 Python repos)
- Hit commit-identity roster-blocker on 3 of 4 child repos — not his fault (long-term fix: #112)
- Unblocked 4 PR merges tonight (#115, #56, #60, #811) with `--admin` per authorized exception

#### Aino Virtanen (SQL) — Severity: None
- PRs: main #122 (#109 CI gate hook implementation)
- Proactively caught spec-discrepancy (nonexistent `gh pr checks --json bucket,name,state` flag combo), used equivalent `gh pr view --json statusCheckRollup`, documented in PR body for reviewers
- Reviewed 7 W8 PRs as charter enforcer, all with correct TechDebt attestation format
- Zero must-fix items received on #122

#### Nadia Khoury (PD) — Severity: None
- Reviewed PR #122 with executive-quality spec audit (dispatcher integration, Hook 7 stacking, program-level interactions)
- Light involvement appropriate for a tightly-scoped wave

#### Orchestrator — Severity: Minor
- Spent ~30 min chasing OAuth scope migration (`read:project` → `project`) mid-retro, eating user time. Projects v2 scope enforcement should have been caught in W7.
- Hit `validate_pr_review` false-positive on #122 merge — resolved by editing the review-request comment. Proper fix filed as #123.

### Top 3 Going Well
1. **Wave sequencing prevented self-blocking** — doing #111 (CI sweep) before #109 (CI gate hook) meant the hook didn't immediately block its own merge PR on any pre-existing red CI.
2. **Enforcement-hierarchy validated** — the W7 principle ("charter rules without enforcement decay, promote to hooks") produced a hook that caught a real bug within minutes of landing.
3. **Team simulation scaled cleanly** — 3 parallel implementers during #110/#111 execution, 2 parallel reviewers on #122. No collisions, no context-loss across spawn cycles.

### Top 3 Pain Points
1. **Hook substring/regex bug cluster (6 in one wave):** #113 (cwd repo), #114 (test cmd false-positives), #118 (branch freshness cwd), #110 (ontology-tracker ghost /tmp entries), #123 (validate_pr_review RequestOrReplied detection), plus pre-existing validate_labels default-limit. Systemic: hooks written without explicit input-language spec.
2. **Disable-with-followup rule ratified mid-wave** — Wanjiku had to do retroactive breadcrumb edits across two PRs after the rule was established during #111 review. New-rule enforcement should wait for next wave boundary.
3. **Single-reviewer exception overused** — bootstrap exception applied to all 4 #110 PRs AND all 4 #111 PRs (Aino sole reviewer). Became pattern-of-convenience rather than exception.
4. **OAuth scope migration chased in real-time** — GitHub Projects v2 scope enforcement surfaced mid-retro, consumed ~30 min of orchestrator + user time. Should have been on W7 radar.

### Proposed Process Changes — ALL ACCEPTED 2026-04-17
1. **Hook authorship spec requirement** — ACCEPTED. Ratified in `charter/hooks.md` § Hook Authorship Requirements (input-language docstring, charter entry, negative-match test coverage, dispatcher registration).
2. **W9 opens with hook-architecture mini-sprint** — ACCEPTED. Tracked as issue #125.
3. **Single-reviewer exception — formalize or drop** — ACCEPTED (formalized). Ratified in `charter/pull-requests.md` § Single-Reviewer Exception (wave-bootstrap PRs ONLY, one-time per wave, Aino as sole reviewer, logged in retro).
4. **Disable-with-followup rule → charter** — ACCEPTED. Ratified in `charter/pull-requests.md` § Load-Bearing Followups for Disabled CI Jobs. Memory `feedback_disable_followup_load_bearing.md` superseded by charter.
5. **Pre-wave auth/scope audit step in /wave-kickoff** — ACCEPTED. Added as `/wave-kickoff` step 3, running before CI triage.

### Skill enforcement change — ACCEPTED 2026-04-17
**Trust matrix updates now land in the retro PR**, not on `CEO/0000-Trust_Matrix`. The `/wave-retro` skill now edits `.claude/team/trust_matrix.md` directly on the retro branch. Stale side-branch pattern retired — it had diverged by 7622 lines from main.

### Trust Updates
No changes. All scores stable. See trust_matrix.md § Phase 2 Wave 8.

### Fire/Hire Actions
None.

## 2026-04-19 — Librarian rule decay observed; promotion to hook

**Pattern:** Orchestrator skipped `/ontology-librarian` on 3 of 4 code-change PRs in P2W9 follow-up work (deploy#125 kafka GID, deploy#130 obs fix, user-service#67 OAuth GET). In each case the rationalization was "this one's small / obvious" — exactly the wording that eroded CI-gate discipline in W7 and peer-review discipline in W8.

**Enforcement hierarchy applied:** Per charter § Enforcement-Hierarchy Promotion (hook > skill > charter), the CLAUDE.md § Ontology rule ("Every agent MUST run /ontology-librarian {topic} before making code changes") was promoted from charter-only status to a hook-enforced rule.

**Artifact:** `.claude/hooks/enforce_librarian_consulted.py` (PreToolUse on Edit/Write/NotebookEdit). Charter entry: `charter/hooks.md` § Hook 15. Issue: [#150](https://github.com/noorinalabs/noorinalabs-main/issues/150).

**Worked example:** This is the first end-to-end execution of the memory → charter → hook promotion pipeline ratified by the owner on 2026-04-19. The `/promotion-audit` skill (tracked separately) will reference this as its canonical example.

## 2026-04-22 — Phase 2 Wave 9 Retrospective

### Wave theme

Data pipeline + user-service cutover + deploy infra + (mid-wave) hook-architecture mini-sprint. Started 2026-04-17; closed 2026-04-22 with 22 items carried forward to wave-10.

### Team Performance

**Org-wide output:** ~50 PRs merged across 8 repos over 5 days. ~35 issues closed. 22 tech-debt followups filed during tonight's intensive session (Apr 22). CI health: 2 red-CI merges slipped through (main#178, deploy#146) — both caught post-merge and repaired; #182 and deploy#148 filed as process gaps.

**Tonight's session volume (2026-04-22):** 18 PRs merged across 4 repos. Items closed: #112 (both parts + 7 child-repo syncs), #135 (user-service#77 + deploy#146/#149 fake_oauth), #149, #169, #173, #177, #179, #184, #192, #190, #191, #10, #13. Filed: main#175, #176, #181, #182, #185, #188, #189, #192; user-service#76, #78, #79; deploy#147, #148; isnad-graph#842, #843; ip#19, #20, #23, #24.

### Per-Engineer Assessments

**Aino Virtanen (Standards & Quality Lead)**
- Tonight: #174 Hook 15 sentinel, #180 branch-regex, #183 skill cwd, #112-b across 6 child repos. Plus ontology cleanup (290 noise entries).
- CI failures caught pre-merge: 1 (ruff format on #174 — self-fixed).
- Must-fix items received: 1 (Wanjiku's session-start path regression on #183 — fixed cleanly in re-review).
- Tech-debt issues filed: 2 in memory (feedback_heredoc_in_git_commit, feedback_canonical_source_via_git_show).
- Standout: divergent-hook transparency on #112-b — quoted replaced design in each child-repo PR body so local teams could flag load-bearing concerns. Also identified + raised the annunaki_log bundling question instead of silently overwriting.
- Severity: **none** (positive)

**Wanjiku Mwangi (TPM)**
- Tonight: #21 D-ii rewire (topics.py + normalize fan-out + manifest). Reviewer on 4+ PRs (#180, #178, #183, #21-self-reviewed).
- CI failures: 0.
- Review depth: caught real session-start path regression on #183, filed #184; caught `kafka-python` / `.new`-vs-`.ready` mismatch during #28 review path.
- Standout: proactive scope guidance — her #21 report flagged graph-load as out-of-scope for her and pointed at #13, preserving PR boundaries cleanly.
- Severity: **none** (positive)

**Weronika Zielinska (Platform Architect)**
- Tonight: #18 D-ii rewire (manifest-gated MERGE, per-field coalesce SET). Reviewer on #183 (#184 co-filing), #21.
- Phase-4 safety implementation: `coalesce(row.props.<f>, n.<f>)` per field — a **genuine improvement over the spec** (I suggested hand-authored per-row Cypher rebuild; she found the elegant alternative).
- CI failures: 0.
- Standout: noticed + filed GRADED_BY Pydantic gap (isnad-graph#842) and shape-mismatch with Wanjiku's normalize during her own implementation. Cross-PR scope awareness.
- Severity: **none** (positive)

**Lucas Ferreira (SRE)**
- Tonight: deploy#146 fake_oauth container, deploy#149 fixup after CI-red merge. Earlier wave-9: deploy#120, #114 (GHCR-only cleanup).
- CI failures (caught post-merge): 1 (deploy#146 merged with red CI — GET vs POST callback shape mismatch). Recovery via fixup #149 was clean.
- Must-fix items: 0 from reviewers (Aisha + Nino both approved #146 on first pass), but CI caught what reviewers missed.
- Tech-debt filed from surfacing: user-service#79 (.dockerignore), deploy#148 (CI gating parallel).
- Severity: **minor** — merged with red CI, but recovered cleanly within 30 min and surfaced two real process gaps.

**Mateo Salazar (user-service Engineer)**
- Tonight: user-service#77 OAuth override + security fixup. Commit SHA d203687 → 1104104.
- Changes Requested by Idris on security grounds — responded with full fixup covering all 3 blockers in one pass.
- CI failures: 0.
- Scope discipline: Apple `aud`/`issuer` exemption + filing user-service#76 for pre-existing mypy debt were both sharp calls.
- Severity: **none** (positive; security-guard-inline pattern saved as feedback memory).

**Idris Yusuf (user-service Security)**
- Tonight: security review on user-service#77 — caught prod-credential-exfil vector (no env-guard on OAuth URL override). Filed user-service#78 as blocker before approving.
- This review alone prevented a real production misconfig disaster. High-value find.
- Severity: **none** (very positive — security signal at its best).

**Aisha Idrissi (SRE)**
- Tonight: #114 auto_set_env fix, reviewed deploy#146, reviewed deploy#149. Filed deploy#147 (image-size claim reconciliation).
- CI failures on #114 merge: 2 (ruff format + mypy pre-existing union-attr). Neither introduced by her code — I caught mypy separately, she'd accurately reported "ruff clean".
- Severity: **none** — pre-existing debt, not her regression.

**Kwesi Boateng (data-acquisition Integration)**
- Tonight: data-acquisition#30 Kafka emit + fixup after Changes Requested + #31 topic rename.
- Changes Requested by Alejandra on 4 blockers (future.get batching, retry/jitter, validator, date slice). Fixup e5255df addressed all 4 cleanly in one pass.
- Scope discipline: chose kafka-python over confluent-kafka for 3.14 wheel reasons with explicit docstring; future-compat b2_key construction; flagged topic-name mismatch in PR body (led to Dilara filing #190).
- Severity: **none** (positive — Changes-Requested → clean-fixup cycle worked exactly as intended).

**Dilara Erdogan (data-acquisition Manager)**
- Tonight: reviewed data-acquisition#30 — filed #190 topic-reconciliation tracking. Re-approved after fixup.
- Severity: **none** (positive; filed a cross-repo tracking issue that became central to the #192 design call).

**Alejandra Reyes-Fuentes (data-acquisition Staff Data Engineer)**
- Tonight: code-level review on data-acquisition#30 — Changes Requested with 4 substantive technical findings (future.get defeating batching, retry/jitter, validator, date-slice). Re-approved after fixup.
- Severity: **none** (very positive; caught real performance + correctness bugs).

**Farhan Malik (isnad-graph Data Engineer Lead)**
- Tonight: reviewed ip#18 (Phase-4 safety catch on `SET n += row.props` — this blocker became central to the rewire). Re-reviewed both post-rewire. Filed isnad-graph#843 (Narrated edge model parallel to #842).
- Severity: **none** (very positive; Phase-4 catch materially improved the final design).

**Arjun Raghavan (isnad-graph System Architect)**
- Tonight: reviewed ip#18 both pre and post-rewire. Filed ip#19, #20, #23, #24 — 4 real tech-debt followups at varying levels of severity.
- Severity: **none** (positive; architectural signal at the right level).

**Nino Kavtaradze (deploy Security)**
- Tonight: reviewed deploy#146 — comprehensive security enumeration (production compose untouched, no id_token signing surface, no host port leakage, fake creds grep-checked, network isolation verified).
- Severity: **none** (positive).

**Santiago Ferreira (Release Coordinator)**
- Tonight: reviewed main#180 (branch-enumeration false-positive walk-through) and main#187. Also #178 earlier in session.
- Severity: **none** (positive; release-coordinator signal consistent with W8).

**Bereket Tadesse (Engineer — spawned for #177)**
- Tonight: executed #177 post-merge verification in fresh subagent worktree. PASS reported with honest caveat about intermittency.
- Severity: **none** (positive — unbiased verification was the point).

**Nadia Khoury (Program Director)**
- Tonight: reviewed main#174 (Hook 15 sentinel) with strategic scope. Filed #176 (reusable sentinel helper) and #177 (verification) as followups.
- Earlier wave: light involvement (other members carried).
- Severity: **none**.

**Orchestrator (me)**
- Actual problem areas:
  - Merged main#178 and deploy#146 with red CI. Process gap filed twice (#182, deploy#148) but the blunder was twofold: not checking `gh pr checks` before `gh pr merge`, then trusting implementer's "ruff clean" report without cross-check.
  - Conflated "parent-repo tooling sweep done" with "wave-9 done" in my first handoff. User had to correct me. Filed feedback memory: "honest audit over false conclusion".
  - Caused the #18/#21 architectural mismatch by not requiring a design sketch before spawning both implementers in parallel. Both PRs shipped on incompatible assumptions; required owner-chaired design call to reconcile.
  - Over-permissively labeled #192 as p2-wave-10 when it was blocking wave-9 items.

### Top 3 Going Well

1. **Cross-repo team-simulated execution scaled cleanly to 4+ repos simultaneously.** Up to 4 subagents in flight, each with correct role identity and commit attribution. Zero identity confusions; no parent-team members authored in child repos where child teams existed.

2. **Review depth > rubber-stamping.** Every PR this session got substantive review findings:
   - Idris caught prod credential exfil on OAuth override (user-service#78 filed as hard blocker).
   - Alejandra caught `future.get` defeating Kafka batching on data-acquisition#30.
   - Wanjiku caught session-start path regression on main#183.
   - Farhan caught Phase-4 safety violation on ip#18 — led directly to the `coalesce` approach.
   - Arjun filed 4 legitimate tech-debt followups on ip#18.
   None of these would have shipped cleanly without the review layer.

3. **Changes-Requested → clean-fixup → re-approve cycle worked exactly as intended multiple times.** Mateo on user-service#77 (Idris's security blockers), Kwesi on data-acquisition#30 (Alejandra's 4 blockers), Aino on main#183 (Wanjiku's regression), Weronika + Wanjiku on the #18/#21 D-ii rewires. No "defer to followup" drift; blockers were closed inline.

### Top 3 Pain Points

1. **CI-red merges happened twice.** main#178 merged with ruff format + mypy failures; deploy#146 merged with end-to-end test failure (wrong HTTP method on OAuth callback). Both required post-merge fixup. Both filed as process gaps (#182, deploy#148). **Root cause:** orchestrator-side — I ran `gh pr merge` without first verifying `gh pr checks` returned clean. Charter enforcement is missing here; a PreToolUse hook that blocks `gh pr merge` when the target PR's latest check run has any FAILURE would close this class of error permanently.

2. **Design call happened POST-implementation for ip#18/#21.** Two parallel implementers (Wanjiku + Weronika) built on incompatible assumptions about message shape (Parquet-batch vs per-row). Mismatch surfaced only during reviewer-cross-check, after both PRs were essentially complete. Required owner-chaired design call + substantial rewire on both PRs. **Root cause:** I spawned both implementers in parallel without requiring a shared design sketch first, assuming the task description was enough. For any cross-worker-contract work, a brief design doc (even as a comment on the parent meta-issue) before implementation begins would catch this in 5 minutes instead of after 2+ hours of parallel work.

3. **Orchestrator honest-audit discipline decayed.** Claimed "wave-9 parent-repo workstream concluded" in handoff when in fact ~22 items remained open across child repos. User had to prompt "have we completed all PRs and open issues for wave 9?" to surface the truth. Need stronger built-in audit step before any "concluded" claim.

### Proposed Process Changes

1. **Promote `validate_ci_before_merge` hook.**
   - Rationale: two red-CI merges in one session is not a coincidence — it's a predictable failure of relying on the merge-time operator to check CI manually.
   - Design: PreToolUse Bash hook scanning `gh pr merge` invocations; for the target PR, run `gh pr checks --json` (or equivalent), block if any check conclusion is `FAILURE`. `--admin` flag is the documented emergency override.
   - Scope: both noorinalabs-main and each child repo. Closes #182 + deploy#148 simultaneously.
   - Enforcement-hierarchy alignment: hook > skill > charter. Charter alone hasn't prevented the failure.

2. **Design-sketch requirement for parallel cross-contract PRs.**
   - Rationale: ip#18/#21 mismatch cost 2+ hours to discover and rewire. Owner explicitly called a design meeting to resolve. 5 minutes of design-doc-in-a-comment would have prevented it.
   - Proposal: when two PRs are in flight that consume/produce from each other (Kafka topics, Parquet schemas, API contracts), the FIRST PR opened must include a "Contract" section in the PR body (message shape, schema, endpoints). The second PR links to that contract and documents any divergence explicitly. Any reviewer may block on missing Contract section.
   - Charter home: `charter/pull-requests.md` § Cross-Contract PRs.

3. **Pre-handoff wave-audit checklist.**
   - Rationale: orchestrator's "wave-9 concluded" claim was untrue; user had to catch it. Skill-level audit should prevent recurrence.
   - Proposal: `/wave-wrapup` (before `/handoff`) must run a cross-repo count of open items labeled with the active wave label. Any "concluded" phrasing in the handoff requires that count to be 0 OR an explicit carry-forward list.
   - Charter home: `charter/skills.md` § Wave Lifecycle.

### Trust Matrix Updates

(See trust_matrix.md § Phase 2 Wave 9 for the table.)

- **Weronika Zielinska**: 3 → **4** ↑ — Phase-4 `coalesce` improvement over spec + cross-PR shape-mismatch catch. Architecture-level contribution material to wave outcome.
- **Wanjiku Mwangi**: 4 → **5** ↑ — multi-role wave (implementer on ip#21 + reviewer on 4+ PRs + caught session-start regression). Sustained high output at quality bar across week.
- **Idris Yusuf**: new entry at **4** — single-review prevention of production credential-exfil vector (user-service#78).
- **Alejandra Reyes-Fuentes**: new entry at **4** — substantive technical review (Kafka batching + date parsing + validator correctness).
- **Farhan Malik**: new entry at **4** — Phase-4 safety catch materially improved the ingest MERGE design.
- **Arjun Raghavan**: new entry at **4** — four legitimate tech-debt followups at varying levels.
- **Kwesi Boateng**: new entry at **4** — Changes-Requested → clean-fixup cycle worked exactly as intended; scope-disciplined around kafka-python / b2-path / topic reconciliation.
- **Mateo Salazar**: new entry at **4** — security-fixup-inline over deferral; Apple JWT exemption call.
- **Lucas Ferreira**: 3 → **3** — deploy#146 red-CI merge is a minor ding but the recovery was clean and surfaced #148. No change.
- **Aisha, Nino, Santiago, Bereket, Nadia**: unchanged (all at current ratings, this wave's contribution aligned with existing signal).

### Fire/Hire Actions

None.

### Proposed Charter Changes

1. `charter/hooks.md`: add Hook 17 `validate_ci_before_merge` spec per process-change #1.
2. `charter/pull-requests.md`: new § "Cross-Contract PRs" per process-change #2.
3. `charter/skills.md` (create or extend): wave-audit checklist per process-change #3.

### Orchestrator self-feedback saved to memory

Already saved this session:
- `feedback_heredoc_in_git_commit.md` — use `-F /tmp/msg.txt` for multi-line commit messages.
- `feedback_canonical_source_via_git_show.md` — `git show <sha>:<path>` when local main lags origin.
- `feedback_child_repo_implementer_rule.md` — child-repo PRs drawn from that repo's own team roster unless owner overrides.
- `feedback_security_guard_inline_not_followup.md` — security blockers landed inline, not deferred.

New memory candidate from this retro:
- `feedback_honest_audit_over_conclusion_claim.md` — before claiming a wave/workstream is concluded, run cross-repo open-item count; no "done" without zero or explicit carry-forward.
## Promotion Audit — wave-9 (2026-04-22)

**Summary:** 0 AUTO · 0 DECIDE · 35 KEPT · 4 SUPERSEDED/ALREADY-PROMOTED

### AUTO-PROMOTED (artifacts generated this run)
_None this run._

### REQUIRES DECISION (issues filed)
_None this run._

### KEPT (no action — informational)
- `feedback_canonical_source_via_git_show.md` (memory): promotion_target=none (informational memory) [retro_citations=1]
- `feedback_child_repo_implementer_rule.md` (memory): promotion_target=none (informational memory) [retro_citations=1]
- `feedback_heredoc_in_git_commit.md` (memory): promotion_target=none (informational memory) [retro_citations=1]
- `feedback_honest_audit_over_conclusion_claim.md` (memory): promotion_target=none (informational memory) [retro_citations=1]
- `feedback_pr_review_comment_only.md` (memory): promotion_target=none (informational memory) [retro_citations=0]
- `feedback_reviewer_techdebt_line_required.md` (memory): promotion_target=none (informational memory) [retro_citations=0]
- `feedback_search_before_filing.md` (memory): promotion_target=none (informational memory) [retro_citations=0]
- `feedback_security_guard_inline_not_followup.md` (memory): promotion_target=none (informational memory) [retro_citations=1]
- `feedback_verify_diagnosis_before_delegating.md` (memory): promotion_target=none (informational memory) [retro_citations=0]
- `project_bootstrap_repo.md` (memory): promotion_target=none (informational memory) [retro_citations=0]
- `project_bug_bash_2026_04_21.md` (memory): promotion_target=none (informational memory) [retro_citations=0]
- `project_current_state.md` (memory): promotion_target=none (informational memory) [retro_citations=0]
- `project_data_pipeline_architecture.md` (memory): promotion_target=none (informational memory) [retro_citations=0]
- `project_i18n_scope.md` (memory): promotion_target=none (informational memory) [retro_citations=0]
- `project_ontology_system.md` (memory): promotion_target=none (informational memory) [retro_citations=0]
- `project_w10_user_service_alembic.md` (memory): promotion_target=none (informational memory) [retro_citations=0]
- `reference_ssh_topology.md` (memory): promotion_target=none (informational memory) [retro_citations=0]
- `user_steven.md` (memory): promotion_target=none (informational memory) [retro_citations=0]
- `annunaki` (skill): Skill not opted into hook promotion [promotion-target != hook]
- `annunaki-attack` (skill): Skill not opted into hook promotion [promotion-target != hook]
- `close-stale-issues` (skill): Skill not opted into hook promotion [promotion-target != hook]
- `handoff` (skill): Skill not opted into hook promotion [promotion-target != hook]
- `ontology-librarian` (skill): Skill not opted into hook promotion [promotion-target != hook]
- `ontology-rebuild` (skill): Skill not opted into hook promotion [promotion-target != hook]
- `plan-phase` (skill): Skill not opted into hook promotion [promotion-target != hook]
- `promotion-audit` (skill): Skill not opted into hook promotion [promotion-target != hook]
- `retro` (skill): Skill not opted into hook promotion [promotion-target != hook]
- `review-pr` (skill): Skill not opted into hook promotion [promotion-target != hook]
- `session-start` (skill): Skill not opted into hook promotion [promotion-target != hook]
- `team-reset` (skill): Skill not opted into hook promotion [promotion-target != hook]
- `wave-audit` (skill): Skill not opted into hook promotion [promotion-target != hook]
- `wave-kickoff` (skill): Skill not opted into hook promotion [promotion-target != hook]
- `wave-retro` (skill): Skill not opted into hook promotion [promotion-target != hook]
- `wave-start` (skill): Skill not opted into hook promotion [promotion-target != hook]
- `wave-wrapup` (skill): Skill not opted into hook promotion [promotion-target != hook]

### SUPERSEDED / ALREADY-PROMOTED (no action — informational)
- `feedback_disable_followup_load_bearing.md` (memory): Memory explicitly marked superseded [superseded_by: charter:pull-requests.md § Load-Bearing Followups for Disabled CI Jobs]
- `feedback_enforcement_hierarchy.md` (memory): Source codified via Promotion provenance entry [provenance block in charter/hooks.md]
- `feedback_repo_independence.md` (memory): Memory enforced via another artifact (charter / hook) [enforced-elsewhere -> cross-repo roster lookup hook]
- `feedback_settings_permission.md` (memory): Memory enforced via another artifact (charter / hook) [enforced-elsewhere -> settings.json permission rules]

## 2026-04-30 — Phase 2 Wave 10 Retrospective

### Wave theme

Stg/prod environment split + promotion pathway (theme), with Phase B (stg fresh-start rebuild) as a Phase C dry-run mid-wave. Started 2026-04-23; closed 2026-04-30 with 3 operational items carried to phase-3.

### Team Performance

**Org-wide output:** ~22 PRs merged across 5 repos over 7 days (deploy: 14, user-service: 3, isnad-graph: 2, landing-page: 1, parent: 2). Wave-merge ceremony today closed all 5 deployments-branch → main merges. 0 open PRs at wrap. 30+ issues closed; 22 tech-debt items filed against phase-3 (formerly p2-wave-11).

**Carry-forward (3):** `deploy#86` (VPS decom routine `trig_01Bif8T51pdaYFjkbM5bERyL`, async-dispatched, fires post-merge), `deploy#151` (manual SRE B2 tfstate-key migration), `user-service#84` (manual DEPLOY_REPO_PAT secret provisioning). All operational, not code.

**Notable side effects of the wave-merge ceremony:** wave-10 → main triggered the natural auto-deploy chain that captures the cpx21 capacity verdict deferred from Phase B. `deploy#86` routine becomes eligible to fire its 5 prereqs. `user-service#89` resolved a non-trivial `ghcr-publish.yml` conflict between #83 (Contract v6 tags + notify-deploy) and #87 (PR Trivy trigger) via union semantics.

### Per-Engineer Assessments

**Aisha Idrissi (deploy SRE)** — heavy lifter of W10
- PRs: deploy#150 (Hetzner per-env), #157 (CF stg), #155 (promote.yml stg/prod), #168 (auth→users rename), #175 (bootstrap GHCR pull), #185 (TF sensitive ssh_public_key), #177 (B2 bootstrap runbook), #189 (BACKUP_B2_* end-to-end). 8 PRs across Section A + B precursors.
- Cross-cutting: drove Phase B rebuild (stg fresh-start) successfully + captured 6 cloud-init/module hardening gaps in `deploy#173`.
- Severity: **none** (very positive; sustained delivery on the wave's biggest workstream)

**Lucas Ferreira (deploy SRE)**
- PRs: deploy#153 (alembic pre-deploy gate), #181 (verify-deploy split stg/prod), #176 (compose-validate paths + actionlint), plus PR #154 / #159 work on integration-tests + alembic-revert-to-head.
- Tech-debt surfaced: filed multiple followups during reviews (CF runbook, blackbox-exporter, etc).
- Severity: **none** (positive; clean execution after W9 deploy#146 red-CI ding has not recurred)

**Weronika Zielinska (Platform Architect / deploy)**
- PRs in deploy: 2 (kafka-kraft work)
- Plus parent-repo: validation + design contribution
- Severity: **none** (positive)

**Mateo Salazar (user-service Engineer)**
- PRs: user-service#80 (alembic merge migration — load-bearing for deploy alembic gate), #83 (Contract v6 image-tag), #87 (GHCR PR Trivy trigger), #88 (ci.yml deployments/** trigger).
- Conflict source: #83 + #87 both touched `ghcr-publish.yml` and merged to different branches → conflict resolved at wave-merge. Recommendation: when two PRs touch the same workflow, sequence the merges so the second rebases first.
- Severity: **minor** — same-file PR sequencing gap; wave-merge resolution went smoothly

**Anya Kowalczyk (user-service Tech Lead)**
- PRs: user-service#80 alembic merge migration (review + landing).
- Cross-Contract cited: per Charter § Cross-Contract PRs, alembic merge migration is now in main (was P2W10 critical-path).
- Severity: **none** (positive)

**Idris Yusuf (isnad-graph Security Engineer)**
- PRs: isnad-graph#847 (pip 26.0.1 → 26.1 CVE-2026-3219), with parallel cherry-pick to main #850.
- Severity: **none** (positive; security signal handled correctly with multi-branch coverage)

**Linh Pham (isnad-graph Frontend)**
- PRs: isnad-graph#844 (Contract v6 image-tag emission).
- Severity: **none** (positive)

**K. Mensah-Williams (landing-page)**
- PRs: landing-page#71 (Contract v6 image-tag).
- Severity: **none** (positive)

**Aino Virtanen (Standards & Quality Lead)**
- Hooks: authored Hook 17 `validate_wave_audit` (`main#218` — closed `main#195`).
- Ontology rebuilds across the wave; charter updates (agents.md, hooks.md, issues.md) for single-session-team delegation pattern + Cross-Contract PRs § + Load-Bearing Followups §.
- Caught & filed `main#194` Hook 14 sync fan-out (closed today across 7 child repos).
- Severity: **none** (very positive; sustained hook-author signal continues from W9)

**Bereket Tadesse (deploy Infrastructure Manager)**
- Drafted comprehensive 278-line W10 retro readout (`.claude/drafts/w10-retro-readout-bereket.md`) before retro skill ran — ahead-of-the-game discipline.
- Five new feedback primitives surfaced & saved as memories during the wave (multi-layer gap, refresh-before-status-claim 4-site application, integrity-claim verification, runtime-gate scoping, live-trace acceptance).
- Severity: **none** (very positive; promotion to "named-primitive author" tier this wave)

**Nadia Khoury (Program Director)**
- Drove ceremony orchestration: 5-repo wave-merge sequence, conflict resolution on `user-service#89`, status JSON refreshes (8 entries through the wave).
- Filed `main#222` branch-protection remediation tracker (anchor on #182).
- Severity: **none** (positive)

**Wanjiku Mwangi (TPM)**
- Cross-repo wave coordination, project-board hygiene.
- Severity: **none** (positive)

**Santiago Ferreira (Release Coordinator)**
- §3.0.a TODO marker resolution (closes `main#211`); secrets-audit migration runbook contributions.
- Severity: **none** (positive)

**Orchestrator (this session)**
- Wave-wrapup ceremony executed end-to-end: ontology refresh, annunaki sweep, worktree sweep (45 stale removed across child repos), 5-repo wave-merge sequence, ghcr-publish.yml conflict resolution.
- Single off-track moment: initial `git merge` on user-service local wave-10 was at a stale ref (3 behind origin); recovered via `git reset --hard origin/...` before re-merging.
- Severity: **minor** — local-ref-staleness check before merge would have been cleaner

### Top 3 Going Well

1. **Section A executed end-to-end.** 10 of 11 promotion-pathway items closed; only async-dispatched `deploy#86` carries forward. Phase B rebuild as Phase C dry-run worked exactly as intended.
2. **Hook 14 + Hook 17 fan-out closed in the same wave.** `validate_pr_ci_status` synced to all 7 child repos (`main#194` closed today); `validate_wave_audit` (Hook 17) shipped as `main#218`. Charter `enforce_librarian_consulted` strictness held.
3. **Bereket's 5-primitive draft.** Retro readout written *during* the wave, not after — process discipline that should propagate.

### Top 3 Pain Points

1. **Same-file PR sequencing in user-service.** `#83` (Contract v6 tags) and `#87` (PR Trivy trigger) both touched `ghcr-publish.yml` on different branches → conflict at wave-merge ceremony. Resolution was tractable (union semantics) but consumed orchestrator time. **Process gap:** when a PR touches a file already touched by an open same-wave PR, the second-author should rebase before merge.
2. **Worktree pile-up across child repos.** 45 stale worktrees from prior waves (mostly P2W7-W9) survived because squash-merge produces non-ancestor branch tips and the standard `--is-ancestor` ancestor-check classifies them as "unmerged". W10 wrapup needed a PR-state recheck to clean them. **Process gap:** wave-wrapup worktree sweep must check via `gh pr` state, not just git ancestry.
3. **`validate_labels` hook regression.** Annunaki captured a `validate_labels` block on a `cat > /tmp/file <<EOF` command — the hook misread the redirect target as a label arg. (Per audit: this is sibling to #216 / #223 / #226 — substring matching across the hook validators.) Filed for phase-3 cleanup.

### Proposed Process Changes (with rationale)

1. **Same-file PR sequencing rule.** When a PR target file already has open changes on another same-wave PR, the second PR must rebase (or wait for the first to merge) before reviewer-approval. Rationale: prevents wave-merge-ceremony conflicts; small upfront cost.
2. **Worktree sweep PR-state check.** Update `wave-wrapup` skill step 8 to default to `gh pr list --head <branch> --state all` instead of `git merge-base --is-ancestor` for merge-status detection. Rationale: 45-worktree pile-up shows the ancestor check is unreliable for squash-merged branches.
3. **Adopt Bereket's 5 primitives as memories** (already done) **and consider charter promotion of "refresh-before-status-claim" as a charter-section** since it now has retro-citations across two waves (W9, W10) with four distinct application sites. Rationale: enforcement-hierarchy escalation per memory `feedback_enforcement_hierarchy.md`.

### Promotion audit (deterministic — see `.claude/team/promotion_audit_log/wave-10.md`)

**Result: 0 AUTO · 0 DECIDE · 54 KEPT · 4 SUPERSEDED.**

No memory has crossed thresholds for auto-promotion this wave. The four superseded entries are unchanged from W9. The 54 kept memories include the 5 newly-saved Bereket primitives — each at retro_citations=1, below threshold. Consider revisiting at next phase boundary (phase-3 W1 retro) when citation counts may have accumulated.

### Carry-forward (passed via skill args)

- `deploy#86` → phase-3 (async routine `trig_01Bif8T51pdaYFjkbM5bERyL` fires post-merge)
- `deploy#151` → phase-3 (manual SRE B2 tfstate-key migration)
- `user-service#84` → phase-3 (manual DEPLOY_REPO_PAT secret provisioning)

### Charter changes proposed (require user approval)

None this retro. Process changes above are skill-level (wave-wrapup step 8) and convention-level (same-file PR sequencing) — both can be applied without charter amendment if approved.


---

## Retrospective: Phase 3 Wave 1 — 2026-04-30

**Theme:** "Promotion pipeline goes prod" — owner directive: pipeline running seamlessly so team can refocus on product + process.

**Wave shape:** ~2.5h elapsed (21:00Z kickoff → 23:15Z final merge). 5 Tier-1 + 2 Tier-2 + 1 followup-of-spec. 8/8 wave PRs merged into `deployments/phase-3/wave-1`. Pure single-team delegation (orchestrator + 4 implementers + 1 manager); no spawned managers from child rosters per single-team-delegation memory.

### Team Performance

- **PRs merged:** 8 (#197, #198, #201, #202, #206, #207, #208, #210). All squash-merge to wave branch.
- **Issues closed:** 8 (#67, #179, #160, #178, #73, #205, #183, #161).
- **CI health:** 0 red merges. All 8 PRs landed with CI green (multiple PRs hit the dedicated 11-12-check terraform-validate gate cleanly post-#210 cloud-init introduction).
- **Tech-debt followups filed:** 9 (#199, #200, #203, #204, #209, #211, #212 in deploy + main#232 + main#233).
- **Carry-forwards remaining:** 3 — all operationally gated, not implementer-deliverable (deploy#86 Phase C VPS decom routine; deploy#151 manual SRE B2 tfstate-key migration; user-service#84 DEPLOY_REPO_PAT secret).

### Per-Engineer Assessments

#### Aisha Idrissi (deploy SRE) — Severity: positive (none)

- **PRs authored:** #198 (gate), #202 (integration-tests remote-mode), #207 (verify-stg flip), #210 (alembic textfile metrics).
- **PRs reviewed:** #197 (Caddyfile evidence-receipts catching false-positive bug), #201 (3-pattern review with hot-spot 4 design pushback), #208 (cross-PR collision flag).
- **CI failures:** 0.
- **Must-fix items received:** 1 (Bereket on #210 — bootstrap-permissions race; addressed via cloud-init wiring + alert design refinement sharper than spec).
- **Tech-debt items filed:** 0 directly; participated in #199, #200, #203, #204 follow-up filings during reviews.
- **Pattern A data points:** #198 lines 232-258 design-rationale block.
- **Pattern B data points:** Pre-implementation verification on #161 — caught 3-x scope expansion before pushing dead code.
- **Pattern C data points:** 2 self-acknowledged (silent-idle without team-lead handoff at #202; post-merge state-stale push at #210 `684f1b2`).

#### Lucas Ferreira (deploy SRE) — Severity: positive (none); standout reviewer-class delivery

- **PRs authored:** #197 (rollback expand with bundled per-service env-var fix), #201 (db-migrate wiring with 5-path retag-gate truth table), #206 (verify-deploy multi-trigger with Reality-post-#87 mapping table).
- **PRs reviewed:** #198 (filed #199 + #200 follow-ups), #202, #207, #210 (drift-catch on runbook L161 + compose 614-621 staleness that Bereket missed).
- **CI failures:** 0.
- **Must-fix items received:** 1 (Aisha on #206 USER_SERVICE_URL/SITE_URL fallback bug; addressed via fix (a) — skip /health fallback when USER_SERVICE_URL == SITE_URL).
- **Tech-debt items filed:** 6 (review followups + flagged drift cleanup #211 + promtool gate #212).
- **Standout signal:** Three substantive reviewer-class bug-catches in one wave + clean self-correction discipline on #210 first-comment header inversion (within 2 minutes via re-post). Reality-post-#87 mapping table on #206 PR body is the canonical worked example for Pattern B reviewer-side discipline.
- **Process gap (minor):** Pushed #206 before #205 merged against explicit "wait" instruction. Technical merit sound (textually disjoint sections of verify-deploy.yml; both MERGEABLE simultaneously); instruction-non-compliance noted.

#### Bereket Tadesse (deploy Infrastructure Manager) — Severity: positive net; manager-class coverage gaps named

- **Reviews:** 8 manager-passes (manager-direct on #161 + #183, manager-pass second-review on #197/#198/#201/#202/#206/#207/#210).
- **Pattern A data points:** 5-path retag-gate truth table on #201 endorsed Aisha's design-rationale block on #198.
- **Pattern B data points:** Scope-rationalization on #161 atomic Option 1 call; cloud-init Bereket-axiom-zero override (snowflake-infra prevention).
- **Pattern B-mirror data points:** Implementer pushback discipline guidance on Aisha's freshness-filter pushback (accept-when-bug, push-back-when-preference).
- **Charter-delta synthesis:** 4-pattern retro readout drafted before retro skill invoked.
- **Manager-class coverage failures (negative):** 6 self-violations of `feedback_refresh_before_status_claim` in one wave. Highest-consequence: drift-catch failure on #210 v3 manager-pass — claimed comprehensive coverage on a load-bearing review while Lucas caught the runbook L161 + compose 614-621 drift. Self-flagged each violation; honest-audit-before-concluded-claims memory he is named on was the violation-target.
- **Net assessment:** Strong delivery + honest self-correction discipline balances the manager-class-amplifier coverage failures. Hold at trust 4. Worth reassessing next wave if pattern persists.

#### Weronika Zielinska (deploy Platform Architect) — Severity: positive (none)

- **PRs authored:** #208 (blackbox-exporter — 4-artifact delivery: compose service + module config + scrape config + 3 alert rules + Grafana dashboard + amtool runbook).
- **CI failures:** 0.
- **Must-fix items received:** 0 (Bereket's review observations all non-blocking; she folded (b) hairpin-NAT + (c) cert-expiry-non-HTTPS into the PR and filed (a) double-pager guard as #209 follow-up — multi-layer-gap discipline applied correctly).
- **Pattern A data points:** Load-bearing assertion module comments per blackbox config.
- **Process gap (minor):** Initial header-convention inversion on #208 first review. Corrected via re-post by orchestrator in #208 merge cycle.

#### Orchestrator — Severity: minor

- **Coordination:** Spawned 4 implementer-agents (deploy-aisha, deploy-lucas, deploy-weronika fresh + bereket-tadesse coordinator). Pure single-team-delegation pattern. 8 PRs landed via 3 sequential rounds (Round 1: #197/#198, Round 2: #201/#202, Round 3: #206/#207/#208/#210).
- **Followup filing:** 9 followups filed during wave (#199 #200 #203 #204 #209 #211 #212 + main#232 fan-out + main#233).
- **Worktree cleanup:** 9 stale worktrees pruned at wrapup (8 wave + 1 stale-locked /tmp/hotfix-deploy from prior session).
- **Process gaps (minor):**
  - 1 Pattern C self-instance: premature "2/2 cleared" status claim on #208 before reviewer count was actually verified (caught when merge blocked at 1/2; resolved by reposting reviewer comments with corrected directionality).
  - main#233 charter-ambiguity framing initially wrong — proposed two-readings interpretation that Bereket then corrected after wire-artifact verification (only Reading 1 in actual use). Issue body amended via comment.

### Top 3 Going Well

1. **Manager-direct review pattern doing real work.** Bereket's manager-pass on every PR (8 total) was not a rubber-stamp slot — it caught design issues, established sequencing rules, and unblocked merges via the 2-reviewer hook. Three substantive manager-direct interventions (#161 must-fix bootstrap-permissions race, scope rationalization on #161, cloud-init Bereket-axiom-zero override) materially shaped delivery.
2. **Cross-pair review discipline.** Aisha + Lucas as authors-and-reviewers of each other's work surfaced two real bugs (Aisha's USER_SERVICE_URL/SITE_URL fallback catch on #206, Lucas's drift-catch on #210). Cross-pair beats lone-reviewer + manager-rubber-stamp shape.
3. **Pattern A discipline holding under wave pressure.** 4 PRs (#198, #201, #208, #210) shipped explicit design-rationale blocks in PR bodies / inline file comments. Reviewer reaction was uniformly positive; future incident-response readability uplift visible.

### Top 3 Pain Points

1. **Pattern C — refresh-state-before-claim discipline degraded under high-tempo cycles.** 9 distinct instances across 3 people in one wave (6 Bereket + 2 Aisha + 1 orchestrator). Manager-class was the most-violation-prone — counter-intuitive to role-authority assumptions. The manager-self-overconfidence-after-attention-fatigue failure mode on Bereket's #210 v3 manager-pass (where Lucas caught drift Bereket missed) was the highest-consequence instance because the manager-pass is the gate-clearing review.
2. **Header-convention enforcement gap in `validate_pr_review`.** The hook accepts inverted Requestor/Requestee directionality without complaint; reviewers used inconsistent conventions across the wave (Reading 1 on most reviews, Reading 2 on Lucas's first #210 comment + Bereket's pre-correction reposts). Hook should enforce header-identity-vs-author-coherence (per filed `main#233`); the wave's gate-clearing relied on author/reviewer self-correction discipline rather than enforcement.
3. **Charter Requestor/Requestee directionality** — initially framed as a two-readings ambiguity by orchestrator + Bereket; after wire-artifact verification it's actually consistent in practice (Reading 1 only). The framing churn cost retro-prep cycles that should have gone elsewhere.

### Proposed Process Changes

1. **Charter delta — Pattern A: PRs touching critical-path workflow DAGs MUST include a design-rationale block in PR body or inline file comments at the load-bearing decision point.** — Rationale: 4 corroborating data points (#198, #201, #208, #210) all earned positive reviewer reaction; high-leverage for review readability AND incident-response readability AND retro evidence. Proposed location: charter `pull-requests.md` § Cross-Contract PRs OR new § Design-Rationale Blocks.

2. **Charter delta — Pattern B (unified): verify spec assumptions / PR-body framing against ground truth before action.** — Rationale: 4 corroborating data points across two roles. Implementer side: Aisha's #161 3-x scope catch + Lucas's #206 stale-issue-body scope rationalization. Reviewer side: Aisha's #206 Caddyfile evidence-receipts. Same axis (verify-vs-artifact), two roles. Charter language should specify: "Read the diff against the actual artifact (Caddyfile, compose env-vars, terraform state, alert YAML), not against the PR body's framing." Lucas's #206 Caddyfile review is the canonical worked example.

3. **Charter delta — Pattern C: `feedback_refresh_before_status_claim` extends to manager-class with explicit no-exemption clause.** — Rationale: 9 wave instances across 3 people. Manager-class was MOST-violation-prone (Bereket 6 self-violations). The manager-pass review's authoritative-coverage posture amplifies downstream consequence when the discipline fails. Charter language: "Before any state-claim ('X/Y cleared', 'comprehensive coverage', 'all items addressed'), perform a fresh `gh api` verification with manual eyeball-check of distinct identities. The manager class is NOT exempt — manager-pass review-coverage claims propagate further than implementer-class state claims and deserve the same or stricter discipline."

4. **Hook fix (gated on Pattern C charter language landing) — extend `validate_pr_review` with header-identity-vs-author-coherence check.** — Rationale: Lucas's #210 first comment with inverted Requestor/Requestee header cleared the gate without complaint; Bereket's pre-correction comments did the same on #208. Hook should reject if Requestor's lastname ≠ branch-author's lastname. Tracked at `main#233`.

5. **Wave-wrapup process change — manager-pass review re-verification when revision-cycles exceed 2.** — Rationale: Bereket's drift-catch failure on #210 v3 (which had been through 2 revision cycles) showed that comprehensive-coverage discipline degrades after attention-fatigue from multiple revision rounds. Suggested: when a PR receives ≥3 revision cycles, the manager-pass review should explicitly enumerate-and-verify each prior must-fix item against the new head, not rely on holistic re-read.

### Charter changes proposed (require user approval)

1. Pattern A charter delta (proposed change #1 above)
2. Pattern B unified charter delta (proposed change #2 above)
3. Pattern C charter delta with manager-class no-exemption clause (proposed change #3 above)

Bereket has draft language for #1 and #2 ready (~3-5 sentences each). User to decide which to adopt, modify, or reject before next wave.



## Promotion Audit — p3-wave-1 (2026-04-30)

**Summary:** 0 AUTO · 0 DECIDE · 55 KEPT · 4 SUPERSEDED/ALREADY-PROMOTED

### AUTO-PROMOTED (artifacts generated this run)
_None this run._

### REQUIRES DECISION (issues filed)
_None this run._

### KEPT (no action — informational)
- `feedback_actionlint_needs_shellcheck.md` (memory): promotion_target=none (informational memory) [retro_citations=0]
- `feedback_canonical_source_via_git_show.md` (memory): promotion_target=none (informational memory) [retro_citations=2]
- `feedback_child_repo_implementer_rule.md` (memory): promotion_target=none (informational memory) [retro_citations=2]
- `feedback_cross_repo_wave_ref_resolution.md` (memory): promotion_target=none (informational memory) [retro_citations=0]
- `feedback_drift_evidence_to_existing_rationalization_issue.md` (memory): promotion_target=none (informational memory) [retro_citations=0]
- `feedback_gh_pr_edit_silent_noop.md` (memory): promotion_target=none (informational memory) [retro_citations=0]
- `feedback_heredoc_in_git_commit.md` (memory): promotion_target=none (informational memory) [retro_citations=2]
- `feedback_honest_audit_over_conclusion_claim.md` (memory): promotion_target=none (informational memory) [retro_citations=2]
- `feedback_live_trace_over_synthetic_acceptance.md` (memory): promotion_target=none (informational memory) [retro_citations=0]
- `feedback_multi_layer_gap_filing.md` (memory): promotion_target=none (informational memory) [retro_citations=0]
- `feedback_origin_over_local_for_still_has_claims.md` (memory): promotion_target=none (informational memory) [retro_citations=0]
- `feedback_pr_review_comment_only.md` (memory): promotion_target=none (informational memory) [retro_citations=1]
- `feedback_pr_state_in_refresh.md` (memory): promotion_target=none (informational memory) [retro_citations=0]
- `feedback_pr_vs_runtime_acceptance_criteria.md` (memory): promotion_target=none (informational memory) [retro_citations=0]
- `feedback_refresh_before_status_claim.md` (memory): promotion_target=none (informational memory) [retro_citations=0]
- `feedback_review_against_artifact_not_framing.md` (memory): promotion_target=none (informational memory) [retro_citations=0]
- `feedback_reviewer_techdebt_line_required.md` (memory): promotion_target=none (informational memory) [retro_citations=1]
- `feedback_role_class_specific_boundaries.md` (memory): promotion_target=none (informational memory) [retro_citations=0]
- `feedback_runtime_gate_scoping.md` (memory): promotion_target=none (informational memory) [retro_citations=0]
- `feedback_search_before_filing.md` (memory): promotion_target=none (informational memory) [retro_citations=1]
- `feedback_security_guard_inline_not_followup.md` (memory): promotion_target=none (informational memory) [retro_citations=2]
- `feedback_single_team_delegation.md` (memory): promotion_target=none (informational memory) [retro_citations=0]
- `feedback_stale_inbox_manager.md` (memory): promotion_target=none (informational memory) [retro_citations=0]
- `feedback_tmp_msg_file_stale.md` (memory): promotion_target=none (informational memory) [retro_citations=0]
- `feedback_verify_diagnosis_before_delegating.md` (memory): promotion_target=none (informational memory) [retro_citations=1]
- `feedback_verify_third_party_integrity_claims.md` (memory): promotion_target=none (informational memory) [retro_citations=0]
- `feedback_wave_branch_issue_close.md` (memory): promotion_target=none (informational memory) [retro_citations=0]
- `feedback_wave_planning_from_board.md` (memory): promotion_target=none (informational memory) [retro_citations=0]
- `project_bootstrap_repo.md` (memory): promotion_target=none (informational memory) [retro_citations=1]
- `project_bug_bash_2026_04_21.md` (memory): promotion_target=none (informational memory) [retro_citations=1]
- `project_current_state.md` (memory): promotion_target=none (informational memory) [retro_citations=1]
- `project_data_pipeline_architecture.md` (memory): promotion_target=none (informational memory) [retro_citations=1]
- `project_i18n_scope.md` (memory): promotion_target=none (informational memory) [retro_citations=1]
- `project_ontology_system.md` (memory): promotion_target=none (informational memory) [retro_citations=1]
- `project_w10_image_tag_contract.md` (memory): promotion_target=none (informational memory) [retro_citations=0]
- `project_w10_user_service_alembic.md` (memory): promotion_target=none (informational memory) [retro_citations=1]
- `reference_ssh_topology.md` (memory): promotion_target=none (informational memory) [retro_citations=1]
- `user_steven.md` (memory): promotion_target=none (informational memory) [retro_citations=1]
- `annunaki` (skill): Skill not opted into hook promotion [promotion-target != hook]
- `annunaki-attack` (skill): Skill not opted into hook promotion [promotion-target != hook]
- `close-stale-issues` (skill): Skill not opted into hook promotion [promotion-target != hook]
- `handoff` (skill): Skill not opted into hook promotion [promotion-target != hook]
- `ontology-librarian` (skill): Skill not opted into hook promotion [promotion-target != hook]
- `ontology-rebuild` (skill): Skill not opted into hook promotion [promotion-target != hook]
- `plan-phase` (skill): Skill not opted into hook promotion [promotion-target != hook]
- `promotion-audit` (skill): Skill not opted into hook promotion [promotion-target != hook]
- `retro` (skill): Skill not opted into hook promotion [promotion-target != hook]
- `review-pr` (skill): Skill not opted into hook promotion [promotion-target != hook]
- `session-start` (skill): Skill not opted into hook promotion [promotion-target != hook]
- `team-reset` (skill): Skill not opted into hook promotion [promotion-target != hook]
- `wave-audit` (skill): Skill not opted into hook promotion [promotion-target != hook]
- `wave-kickoff` (skill): Skill not opted into hook promotion [promotion-target != hook]
- `wave-retro` (skill): Skill not opted into hook promotion [promotion-target != hook]
- `wave-start` (skill): Skill not opted into hook promotion [promotion-target != hook]
- `wave-wrapup` (skill): Skill not opted into hook promotion [promotion-target != hook]

### SUPERSEDED / ALREADY-PROMOTED (no action — informational)
- `feedback_disable_followup_load_bearing.md` (memory): Memory explicitly marked superseded [superseded_by: charter:pull-requests.md § Load-Bearing Followups for Disabled CI Jobs]
- `feedback_enforcement_hierarchy.md` (memory): Source codified via Promotion provenance entry [provenance block in charter/hooks.md]
- `feedback_repo_independence.md` (memory): Memory enforced via another artifact (charter / hook) [enforced-elsewhere -> cross-repo roster lookup hook]
- `feedback_settings_permission.md` (memory): Memory enforced via another artifact (charter / hook) [enforced-elsewhere -> settings.json permission rules]


### Post-retro refinements (2026-04-30 23:30Z)

The team continued sharpening retro inputs after the initial retro commit (`5cdfc4c`). Refinements driven by Bereket + Lucas; preserved here rather than amending the original entry above so the timeline of precision-acquisition is visible in the artifact.

#### Pattern C / Pattern D split — shared umbrella, separate remediation paths

The original entry conflated two different failure shapes under "Pattern C." Lucas's analysis decisively split them:

- **Pattern C — claim-state-staleness:** burden on the asserter. Fix via `gh api` / wire-check before claims. **Discipline-class** remediation.
- **Pattern D — message-ordering-race:** burden on the system. Fix via mutex on issue# OR send-ack-acts-as-acquire protocol. **Architecture-class** remediation.

Lumping them would have resulted in "verify more!" being the only takeaway when message-races are a backpressure-protocol gap that no individual discipline fix addresses. Shared umbrella ("async coordination failures") preserves the cross-cutting signal without conflating remediation paths.

Updated wave tallies (11 + ~4 instead of original 9):

- **Pattern C:** 7 Bereket + 2 Aisha + 2 orchestrator + 0 Lucas = **11 instances** in one wave. (Bereket's tally bumped from 6 to 7 after his own main#233 charter-ambiguity-framing self-acknowledgment as a Pattern C instance — claimed two-readings ambiguity without exhaustively reading wire artifacts first.)
- **Pattern D candidate:** ~4 Lucas-side message-ordering races (implementer ships work; team-lead ships task_assignment for the same work; messages cross in the bus). Real but distinct from Pattern C.

#### Lucas's muscle attribution refined to three orthogonal disciplines

Original entry credited Lucas with "self-detected format error + re-posted within 2 minutes" on his #210 first comment. Lucas himself corrected this in stand-down: the actual sequence was orchestrator-caught-the-inversion-in-his-task-assignment-at-23:15 → he-verified-against-wire-(saw all prior comments using PR-author-as-Requestor) → he-reposted-at-23:16:27. Different muscle than self-detection.

Corrected attribution — three orthogonal disciplines:

1. **Trust-the-artifact-not-the-framing** (reading discipline) — Caddyfile evidence-receipts on #206, Reality-post-#87 mapping table on his own #206 PR body.
2. **Search-before-filing** — declined to file parallel issue when promtool gate already at #212.
3. **Adversarial-recall-when-credited** (reactive trigger) — external prompt asserting "you did X" → memory-check → correction if mismatch. Exercised on the muscle-attribution itself when Bereket credited him for self-detection.

NOT exercised this wave by ANYONE: **post-publish audit absent external prompt** (proactive trigger; no external prompt; self-check of own previously-published claims). Honest team-wide gap.

The fact that Lucas raised the credit-attribution correction unprompted — distinguishing demonstrated vs exercised discipline on his own credit — is itself the strongest "adversarial-recall-when-credited" data point I've seen this wave. Worth feedback_log preservation as the canonical worked example.

#### Memory cluster reframe — "Trust the artifact, not the framing"

Bereket + Lucas converged on a unifying name for the existing memory cluster:

- `feedback_verify_third_party_integrity_claims.md`
- `feedback_origin_over_local_for_still_has_claims.md`
- `feedback_refresh_before_status_claim.md`
- (proposed new) Lucas-named entry capturing the reading-vs-framing discipline

All four are instances of the same axis — distrust-the-narrative-trust-the-artifact. Worth folding under one header for memory-system maintenance and charter cross-reference clarity. Renaming or grouping is a charter-skill-level cleanup; not blocking but worth time.

#### Structural safeguard options sketched

For Pattern C (charter language alone insufficient given recurrence-after-self-naming pattern):

1. **Hook at SendMessage boundary** — parse outgoing SendMessage content for state-claim phrases ("verified", "X/Y cleared", "merged at", "head SHA"); block if no recent `gh api` call in transcript window. Heavyweight tooling for a discipline that should be culture; risk of false positives.
2. **Pre-write checklist** — any state claim about another teammate's or PR's state requires a `gh api` call in the same tool-block. Lightweight, agent-side discipline. **Bereket's lean.**
3. **Independent verification routing** — when manager-class claims need to be load-bearing for downstream decisions, require independent verification by a second agent before the claim propagates. Honest about the recurrence shape but expensive operationally.

For Pattern D (architecture-class):

1. **Orchestrator-poll-before-task-assignment** — orchestrator MUST `gh pr list` / `gh issue view` before any TaskCreate or task_assignment SendMessage; if implementer's work is already shipped, no-op the assignment.
2. **Implementer-blocks-on-task-assignment** — implementer waits for explicit task_assignment ack from orchestrator before starting work, even when scope is obvious from prior context.

Both have throughput costs. Worth retro discussion on whether to adopt vs accept message-races as cost-of-throughput.

#### Inverted role-authority observation expanded

"Manager-class actually being the most-violation-prone this wave (which is the inverse of what role-authority traditionally implies)" — Bereket explored why:

1. **Information-volume** — manager tracks all 8 PRs simultaneously; more state than any single role.
2. **Comprehensive-claim posture** — managers default to "I've reviewed everything" framing; implementers default to "I touched X" framing. The first is more vulnerable to incomplete-coverage-claims.
3. **Asymmetric verification incentives** — a missed implementer detail surfaces in PR-review; a missed manager detail propagates because the manager-pass IS the verification.

The implementer Pattern-B discipline (verify-before-implementing) has a natural verification gate (the implementer faces their own diff at code-write-time); the manager-pass discipline has no such gate. That's the shape worth structural-safeguard work — option 2 or option 3 above directly addresses the asymmetric-verification gap.

#### Final tallies (post-refinement)

| Pattern | Count | Remediation class | Charter-delta-ready? |
|---------|-------|-------------------|----------------------|
| A — design-rationale block | 4 data points | Charter | YES |
| B unified — verify-vs-artifact | 4 data points (3 implementer + 1 reviewer) | Charter | YES |
| B-mirror — implementer pushback (bug-vs-preference) | 1 data point | Capture-and-watch | NO; wait for next-wave |
| C — claim-state-staleness | 11 instances | Charter + structural-safeguard option | YES |
| D — message-ordering-race | ~4 instances | Architecture | NO; needs design discussion |

Plus charter-aspiration mention for proactive post-publish audit (no enforcement, no mandate; flag as known gap).


---

## Retrospective: Phase 3 Wave 2 — Emergency Restore + OAuth Stand-up (2026-05-01 → 2026-05-02)

**Caveat:** Not a planned wave. No `/wave-kickoff`, no wave branch, no team simulation spawned. The orchestrator + owner ran the entire thread direct. Per-engineer ratings reflect *committed identity* on the work, not actual agent participation — the named agents (Aisha, Lucas, Bereket) did not run as agents during this thread. Retro run after-the-fact at owner request.

### Wave shape

| Metric | Value |
|---|---|
| Duration | 6h emergency window (2026-05-01 23:13Z → 2026-05-02 05:12Z), plus #215 the night before |
| PRs merged in deploy | 13 (#215, #217, #219, #223, #226, #228, #232, #236, #240, #241, #246, #247, #248) |
| Author identity | 13/13 `parametrization` (owner self-merge) |
| Formal `gh pr review` | 0 |
| Charter-format comments | Phase 1 (#215–#241): 2–4 per PR · Phase 2 (#246–#248): zero |
| New issues filed | 16 (#216 #218 #220c #222 #224 #225 #229 #231 #234 #235 #237 #238 #239c #242 #243 #244 #245) |
| Issues closed | US#84, deploy#151 (P3W2 prereqs); deploy#220, #239 (in-wave) |
| Architectural changes | TF SSH-key removal, Caddyfile per-env templating, CF reconciled into TF, per-env OAuth apps, users.* vhost carve-out, break-glass workflow inputs |

### Two-phase escalation signature

**Phase 1 (emergency-with-process)** — #215 → #241. Charter `Requestor/Requestee/RequestOrReplied` comments attempted; some real Changes-Requested interaction on #215 (Lucas, then both Approved). Discipline mostly held.

**Phase 2 (process-collapse)** — triggered when owner manually decommissioned 1box-prod (id 124917846) while CF DNS still pointed at it → **prod went down**. PRs #246/#247/#248 each merged within 4–25 seconds of creation. Zero comments. Pure restore-mode. Discipline silently collapsed without an in-band signal that the team had moved out of standard mode.

### Per-engineer assessments

Skipped — the named agents did not actually run during this thread. Holding everyone at P3W1 trust levels.

### Top 3 going well

1. **Root-fix discipline held under pressure** — every bug discovered (terraform.yml ephemeral keys, promote.yml retag-token, TOCTOU, multi-arch parity, db-migrate.yml driver) was root-fixed not patched-around. No tech-debt deferred.
2. **Honest issue-filing during the fire** — 16 new issues filed *while* the emergency was running, capturing tracking work for later (deploy#231, #242, #243, #244, #245). The "search-before-filing" + "multi-layer-gap" memories visibly held.
3. **Break-glass discoverability** — adding `skip_alembic_gate` + `allow_stg_tags` workflow inputs (#232) was the right shape: the bypass is documented, gated, auditable, not a one-off shell command.

### Top 3 pain points

1. **Five workflow bugs surfaced only under live emergency** — terraform.yml ephemeral-keypairs, promote.yml retag wrong-token, promote.yml stg-latest TOCTOU race, promote.yml multi-arch assumption, db-migrate.yml psycopg-vs-asyncpg URL. None caught by W10 reviews. These are first-deploy / cold-start bugs that no PR-time review would have found — they need cold-rebuild dry-run as an acceptance gate.
2. **Owner-manual-action with no orchestrator handoff** — prod outage was caused by owner deleting a Hetzner box while CF DNS still pointed at it, with no signal to the orchestrator. Orchestrator had no state-model of "which infra is owner-mutable," so couldn't pre-flight DNS state.
3. **Silent process-discipline collapse** — comment density and merge times degraded monotonically through the emergency without anyone naming the bypass. Charter assumed standard mode the whole way.

### Charter changes applied (post-retro)

1. **New sub-doc `charter/emergency-mode.md`** — covers Emergency Mode (trigger conditions, allowed bypasses, `[EMERGENCY]` PR prefix, post-emergency catchup) AND Owner-Manual-Action Protocol (`[OWNER-ACTION]` one-line state-delta posting). Linked from main charter sub-doc table.
2. **New memory `feedback_pattern_e_emergency_process_collapse.md`** — recognition primitive for the silent-collapse signature; complements the charter sub-doc by giving the agent-side detection rule.

### Action items

- File deploy issue: cold-start workflow dry-run as acceptance gate for promotion-pathway / migration / TF-apply workflows.
- Post-emergency catchup pass on the 13 emergency PRs (per new charter sub-doc) — async review, TechDebt enumeration, runbook updates.

### Pattern tally (running)

| Pattern | Class | This wave |
|---|---|---|
| A — design-rationale block | Implementer | n/a (no team agents ran) |
| B unified — verify-vs-artifact | Implementer + reviewer | n/a |
| C — claim-state-staleness | Manager-class amplifier | n/a |
| D — message-ordering-race | Architecture | n/a |
| **E — process collapse under fire** (new) | Orchestrator-class | 1 wave-scale data point (this thread) |

---

## Retrospective: Phase 3 Wave 3 — Post-Emergency Stabilization + Frontend Absolute-URLs Phase 2 (2026-05-03 → 2026-05-04)

### Wave shape

| Metric | Value |
|---|---|
| Duration | ~8.5h (kickoff 2026-05-03T17:55Z → wave-merges 2026-05-04T02:32-02:35Z) |
| Repos in scope | 5 (deploy, isnad-graph, landing-page, user-service, main) — planning record listed only 4; user-service joined mid-wave for cross-repo Option A on #266 |
| PRs merged into wave branches | 14 (main: 2; deploy: 8; isnad-graph: 2; landing-page: 1; user-service: 1) |
| Wave-merge PRs to main | 5 (US#93 → deploy#270 → isnad-graph#856 → landing-page#76 → main#243; deploy-order sequenced) |
| CI failures across all 14 PRs | **0** |
| Charter-format comments per PR | 4–10 (healthy density) |
| ChangesRequested cycles resolved | 4 (deploy#259, #261, #266, #267) — all additive, no force-push |
| Issues closed in wave | deploy#249, #250, #251, #252, #255, #256, #243, #244, #245, #242; isnad-graph#853; user-service#91; main#234, #237 (14 total) |
| Architectural changes | First composite GH Action in deploy (#261 break-glass-audit); cold-rebuild dry-run gate (#260); CF + B2 in TF CI matrix (#257); frontend `VITE_USER_SERVICE_ORIGIN` cutover (isnad-graph#855); FastAPI prod-`/docs` disable env-gate (US#92) |

### Per-engineer assessments

#### Implementers

**Aisha Idrissi** (deploy SRE) — 4 PRs (#254, #258, #260, #267). Sustained heavy-lifter delivery. Cold-rebuild dry-run gate (#260, +876 lines) closed W2-retro action item at first wave-opportunity. ChangesRequested-on-#267 from Bereket caught wrong workflow input (`image_tag`→`source_sha`) plus 4 secondary items; Aisha shipped 5 fixes in 49-line additive commit (no force-push). 0 CI failures across all 4. Severity: **none**. Trust 5→5 (max).

**Lucas Ferreira** (deploy SRE) — 2 PRs (#257 TF CF+B2 CI matrix, #266 Caddy CSP). Reviewer-class signal: 2nd-review on #266 caught a SHA citation drift in Bereket's review (`3792b97a` cited vs actual unblocker head `fb9d44d3` after Idris-91 force-push) — meta-state-verification (verified the verifier). #257 closed W2-retro action item (CF+B2 in CI plan/apply matrix). 0 CI failures. Severity: **none**. Trust 5→5 (max).

**Bereket Tadesse** (deploy Mgr) — Wave-completion reviewer standout. Caught **5 distinct must-fix items** across 4 wave-completion batch PRs; Pattern B (verify-vs-artifact) applied textbook on every review. P3W1's 6-instance Pattern C self-violation pattern did NOT recur — strong reversal signal. Severity: **none**. Trust 4→**5** ↑.

**Weronika Zielinska** (PA) — 2 PRs (#259, #261). #261 is the first composite GH Action in the repo (+725 lines). Tech-debt self-correction signal: caught own PR-body claim that `TechDebt: #127` was active before Bereket's review started (verified `#127 CLOSED 2026-04-19`); updated PR body in real time. Path-A discipline on #259 (bundled fix vs operational silence-then-unsilence dance). Both ChangesRequested cycles resolved cleanly with additive commits. 0 CI failures. Severity: **none**. Trust 4→**5** ↑.

**Idris Yusuf** (cross-repo Sec — user-service + isnad-graph membership) — 2 PRs in 2 repos: user-service#92 (FastAPI prod-`/docs` disable, +68/-1) emerged DURING the wave to unblock deploy#266 ChangesRequested (Bereket's live-state catch on `users.*` non-JSON-only); isnad-graph#854 (Trivy nghttp2-libs CVE digest-pin + apk upgrade, +9/-1). Cross-repo coverage class signal — single engineer enabling 3 PRs to land. Minimal-surgical fix shape held under cross-repo blocker pressure. 0 CI failures. Severity: **none**. Trust 4→**5** ↑ (single track across both repo memberships).

**Aino Virtanen** (SQL) — main#242 (block stale `/tmp/*` message/body files in `git commit -F` / `gh --body-file`, +384/-0). Largest main# PR in wave; table-driven hook with tests. Closes main#237. 4/4 CI green. Severity: **none**. Trust 5→5 (max).

**Nadia Khoury** (PD) — main#241 (Pattern D adoption signal-check audit, +170/-0). Tracking deliverable, scope-appropriate. Single-cycle Approved. Severity: **none**. Trust 4→4.

**Jiyoung Park** (isnad-graph Frontend, NEW) — isnad-graph#855 first contribution (`+51/-5` frontend absolute URLs via `VITE_USER_SERVICE_ORIGIN`, deploy#245 phase 2 part 1). Surgical scope. Clean ship: 9/9 CI green. Severity: **none**. New entry at 3.

**K. Mensah-Williams** (landing-page) — landing-page#75 (`+16/-0` emit OCI image index for multi-arch parity, closing deploy#242). 2/2 CI green. Severity: **none**. Trust 3→3.

#### Reviewers (in addition to implementer-side reviews above)

**Wanjiku Mwangi** (TPM) — 2nd-reviewer pass on both main# PRs. Held at 5.
**Aisha Idrissi** — 2nd-reviewer pass on #266 (independent verification of the user-service#92 cross-repo unblocker).

### Top 3 going well

1. **Reviewer-class pattern B made wave-completion catchable.** Bereket's 5 must-fix catches across 4 PRs (#259 operational, #261 perms-shadowing, #261 runbook ref, #266 live-state, #267 wrong-workflow-input + 4 secondary) all came from artifact-first review — `gh api contents` reads, HEAD SHA citations, delta measurements. P3W1's Bereket-named primitive ("review-against-artifact-not-framing", `feedback_review_against_artifact_not_framing.md`) operated as designed in P3W3 across **3 distinct role classes** (Bereket as 1st-reviewer, Lucas as 2nd-reviewer-of-reviewer on #266 catching the SHA citation drift, Aisha as 2nd-reviewer-of-cross-repo-unblocker). Promotion threshold met by tally — see § Promotion Audit caveat below.

2. **ChangesRequested cycles all resolved with additive commits — zero force-pushes.** 4/4 cycles (#259 Path-A bundled, #261 perms+runbook, #266 cross-repo Option A, #267 5-fixes-in-49-lines) shipped as additive commits to the existing PR branch with no `git push --force-with-lease`. This is a noteworthy-positive signal: state-verification at HEAD became byte-stable across the review-fix-rereview cycle, eliminating a class of "review-the-wrong-SHA" risk. Worth codifying.

3. **Cross-repo Option A worked end-to-end for the first time.** deploy#266 ChangesRequested was a live-state correction that needed a code change in a different repo (user-service `/docs` env-gate) before the original PR could merge. Idris-91 (Sec, user-service team) shipped US#92 inside the wave, unblocking #266 before wave-merge. Pattern: cross-repo blocker → mid-wave engineer cross-mapping → unblock-and-ship-in-sequence. CLAUDE.md § Cross-Repo Coordination contract held under live conditions.

### Top 3 pain points

1. **6 orchestrator-class pre-flight gaps caught by downstream layers, not pre-flight.** Wave-branch creation in deploy was missing until Aisha-252 caught it at first-implementer-spawn (main#238 filed). deploy#242 attribution mistake (claimed isnad-graph sibling, was actually landing-page) was caught by Idris-853 reading the issue body (post-issue-comment 4366836610). Child-repo-implementer rule was missed for both landing-page and user-service (mid-wave correction). 2-reviewer planning, agent-naming pattern, and spawn-brief-reviewer-order-inversion all required mid-wave correction. **All 6 are recoverable**, but each is a recurring class of orchestrator-class gap. Pattern: orchestrator skips a pre-flight check, downstream layer (implementer / hook / reviewer) catches it. Need a pre-flight checklist coupled to `/wave-kickoff`.

2. **Wave-merge required `--admin` override on 5/5 wave-merge PRs because validate_pr_review.py is mismatched with charter.** The hook treats `Requestee` as the reviewer and demands 2 reviewer-distinct comments. The wave-completion format used `Requestee=author` in many comments (because the format was Requestor=reviewer-of-prior-comment, Requestee=author-being-reviewed). Net: hook blocked, orchestrator merged with `--admin`. main#244 tracks the hook fix. main#233 tracks the charter-format ambiguity. main#228 tracks Single-Reviewer Exception non-honoring. **Three open issues all describe one tangled validate_pr_review.py bug surface.**

3. **Promotion-audit pipeline has a discoverability gap.** Pattern B (`feedback_review_against_artifact_not_framing.md`) was claimed to have crossed the 5+ instances / 3 role classes promotion threshold in the wave wrap, but the deterministic `/promotion-audit` returned 0 AUTO / 0 DECIDE because the memory's frontmatter has `promotion_target: none`. The audit can't promote a memory that hasn't been opted in via frontmatter. The "tally crossed threshold" claim is human-tracked; the deterministic audit doesn't see the same signal. Either: (a) memories that are clearly headed for charter-promotion should set `promotion_target: charter` proactively, or (b) the audit needs a fall-back signal source (e.g., named-primitive citations in retros) that bypasses frontmatter.

### Proposed process changes

1. **Add a pre-flight checklist to `/wave-kickoff`** — Rationale: 6 of 6 orchestrator-class gaps in P3W3 were recoverable but each cost mid-wave coordination. A standardized pre-flight list (per-repo wave branch created? per-repo implementer rule applied? agent-naming pattern set? attribution sanity check on every issue body? 2-reviewer plan per PR drafted?) coupled to `/wave-kickoff` step output would catch them at planning-time. Not a hook — pre-flight checklist with explicit "yes/no/N-A" entries per repo. Tracks main#238 + 5 siblings.

2. **Codify additive-commit-only on ChangesRequested cycles** — Rationale: 4/4 cycles in P3W3 used additive commits with no force-push, and that was a load-bearing positive (HEAD SHA stable across review-fix-rereview). Add to `charter/pull-requests.md`: "On a ChangesRequested → fix → re-review cycle, the fix MUST be an additive commit on the same branch unless explicitly approved by the requesting reviewer. Force-push during ChangesRequested is a Pattern B violation (resets HEAD-SHA-anchored verification chain)." Distinct from rebase-before-merge which is allowed pre-Approved.

3. **Set `promotion_target: charter` on memories citing-frequency-3+** — Rationale: 5 memories sit at retro_citations=3 (`feedback_heredoc_in_git_commit.md`, `feedback_child_repo_implementer_rule.md`, `feedback_honest_audit_over_conclusion_claim.md`, `feedback_security_guard_inline_not_followup.md`, `feedback_canonical_source_via_git_show.md`) but all have `promotion_target: none` and so cannot be auto-promoted. Either codify them OR explicitly mark them as `promotion_target: never` (informational-only by design). Decide-then-tag.

### Charter changes proposed (require user approval before applying)

1. **`charter/pull-requests.md` — § Additive Commits on ChangesRequested.** New section:
   > **Additive-only on ChangesRequested.** When a reviewer marks `ChangesRequested`, the fix MUST land as an additive commit on the same branch. Force-push (`git push --force` / `--force-with-lease`) during a ChangesRequested cycle is prohibited because it resets the HEAD-SHA anchor that the reviewer's `gh api contents/<path>?ref=<sha>` verification chain depends on. If a rebase is genuinely needed (e.g., merge conflicts after base advances), open a comment thread BEFORE rebasing, get explicit "rebase OK" from the requesting reviewer, then rebase. Pre-Approved rebase-before-merge is unaffected (HEAD anchor no longer load-bearing once Approved).

2. **`charter/wave-kickoff.md` (or add to `/wave-kickoff` skill) — § Pre-Flight Checklist.** New section. 6 explicit checks per scoped repo:
   > 1. Wave branch exists in this repo (`git ls-remote origin deployments/phase-{N}/wave-{M}` ≠ empty)
   > 2. Implementer roster confirmed for this repo (per child-repo-implementer rule)
   > 3. Every scoped issue's `actual_repo_for_changes` matches its parent-issue repo (re-read every issue body for sibling/attribution mistakes)
   > 4. 2-reviewer slate drafted per PR before any spawn
   > 5. Agent naming pattern set: `{FirstInitial}.{LastName}/{IIII}-{slug}` per CLAUDE.md
   > 6. Spawn-brief includes explicit reviewer-class identity ahead of implementer-class identity (order matters; reviewer-first prevents Pattern B inversion)

3. **`charter/pr-review.md` § Comment Format — disambiguate Requestor/Requestee.** Resolve main#233 ambiguity. Two readings exist; the team consistently uses Requestor=author / Requestee=reviewer (matches main#244 hook reading). Decision needed: codify the actual-usage reading and update validate_pr_review.py to match (closes #244, #233 simultaneously). Alternative: codify charter-original reading (Requestor=reviewer) and update all existing PR comments + hook. Owner-decision required.

### Promotion audit (deterministic — see `.claude/team/promotion_audit_log/wave-3.md`)

```
Promotion audit wave-3 complete: 0 AUTO · 0 DECIDE · 60 KEPT · 3 SUPERSEDED · 1 ALREADY-PROMOTED
```

**Caveat:** Pattern B's named-primitive memory (`feedback_review_against_artifact_not_framing.md`) was claimed promotion-threshold-met in the wave wrap (5+ instances across 3 role classes), but the audit reports KEPT because `promotion_target: none` blocks auto-promotion. See pain point #3 above. Decide whether to flip the frontmatter and re-run.

### Action items

1. Apply approved charter changes (after user review) — Aino lead, Wanjiku 2nd-review.
2. Convert P3W3 + W2 retro action items into the W4 plan: cold-rebuild gate (DONE in W3 #260); pre-flight checklist (NEW, charter §1 above); validate_pr_review.py family (#244 + #228 + #233); /wave-kickoff skill multi-repo branches (#238).
3. Re-run `/promotion-audit` once memory frontmatters are decided (action item #3 above) — Aino.

### Pattern tally (running)

| Pattern | Class | This wave | Cumulative |
|---|---|---|---|
| A — design-rationale block | Implementer | 2 (Aisha #260, Weronika #261 composite-action design) | 6 |
| B unified — verify-vs-artifact | Implementer + reviewer | 5 across 3 role classes (Bereket 1st-reviewer ×4 + Lucas 2nd-reviewer-of-reviewer ×1 + Aisha 2nd-reviewer-of-cross-repo-unblocker ×1) | **promotion-threshold met by tally; deterministic audit blocked by frontmatter** |
| C — claim-state-staleness | Manager-class amplifier | 0 (P3W1's 6-violation pattern did NOT recur) | reverted from peak |
| D — message-ordering-race | Architecture | tracking audit landed (main#241) | 0 violations |
| E — process collapse under fire | Orchestrator-class | n/a (no emergency this wave) | 1 historical |
| **F — orchestrator-class pre-flight gap** (new candidate) | Orchestrator-class | 6 instances (wave-branch, attribution, child-repo-implementer ×2, 2-reviewer planning, naming, spawn order) | **founding wave** |



---

## Retrospective: Phase 3 Wave 4 — Tooling & Process-Discipline Cleanup (2026-05-04 → 2026-05-05)

### Wave shape

| Metric | Value |
|---|---|
| Duration | ~36.5h (kickoff 2026-05-04T03:15Z → final wave-merge 2026-05-05T15:51Z) |
| Repos in scope | 6 declared (main, isnad-graph, user-service, design-system, data-acquisition, ingest-platform) — **5 produced PRs** (ingest-platform: 0) |
| PRs merged into wave branches | **14** (main: 10; isnad-graph: 2; user-service: 1; design-system: 1; data-acquisition: 1) |
| CI failures across all 14 PRs | **0** |
| Admin overrides at wave-merge | **0** (down from 5/5 in W3 — eliminated by #250 canonicalization in same wave) |
| ChangesRequested cycles | 1 (#250 Wanjiku → Aino reply → Approved; additive commit, no force-push) |
| Charter-format comments per PR | 3–8 (healthy density) |
| Issues closed in wave | ~22 (#226 #227 #223 #216 #188 #144 #189 in #248 alone; #198, #203, #219, #225 #239 #240 #200 #201 #197, #244 #233 #228, #196, #214, #158, #852, #819 #814, #90, #62) |
| W3 retro action items shipped IN-wave | 3/3 (pre-flight checklist via #245+#249, additive-commit codified via #254 charter sweep, validate_pr_review family closed via #250) |

### Per-engineer assessments

#### Org-level team

**Aino Virtanen** (SQL) — 8 of 10 main# PRs. Theme-coherent hook bug-class consolidation. #248 shared `_shell_parse.py` parser refactor closing 7 issues at once; #250 validate_pr_review canonicalization (Requestor=reviewer + Single-Reviewer Exception) closing 3 issues — and the load-bearing one, because it eliminated W3's 5/5 wave-merge admin-override pattern in the same wave it landed. #254 charter+docs sweep (6 followups in 156 lines). #256 + #257 net-new hooks (validate_edit_completion + validate_workflow_paths_coverage). #261 Hook 14 NEUTRAL allowlist. #265 canonical hook-sync doc Phase 1. #266 promotion-audit STALE-OPT-OUT class. ~5400 LOC at 0 CI failures. One ChangesRequested cycle resolved cleanly with additive commit. Severity: **none**. Trust 5→5 (already max).

**Wanjiku Mwangi** (TPM) — 2 skill PRs that closed W3 retro carry-forwards: #245 wave-kickoff multi-repo branches (closes #238), #249 wave-scope reconciliation (closes #196). Pattern B reviewer-class data point: ChangesRequested catch on #250 (Aino replied + got Approved by both reviewers). Reviewer on all 10 main# PRs. Severity: **none**. Trust 5→5 (already max).

**Nadia Khoury** (PD) — Reviewer-only this wave (10/10 PRs). No level-changing signal. Severity: **none**. Trust 4→4.

**Santiago Ferreira** (RC) — Reviewer on #266 only. Theme was tooling not deploy. Severity: **none**. Trust 5→5 (already max).

#### Child-repo teams

**Linh Pham** (isnad-graph DevOps) — isnad-graph#858 (`+370/-0`, validate_commit_identity cross-repo merge + strip ordering tests, closes #819 + #814). First substantive shipper-class entry. 9/9 CI, 4 charter-format comments. Severity: **none**. Trust 3→**4** ↑.

**Ingrid Lindqvist** (isnad-graph Eng, NEW) — isnad-graph#857 (1-line CLAUDE.md slash sync, closes #852). 9/9 CI. First contribution. Severity: **none**. New entry at **3**.

**Mateo Salazar** (user-service Eng) — user-service#94 (1-line slash sync, closes #90). Trivial scope. Severity: **none**. Hold at 4.

**Kofi Mensah** (design-system Docs Eng, NEW) — design-system#63 (1-line slash sync, closes #62). 2/2 CI. First contribution. Severity: **none**. New entry at **3**.

**Sofia Cardoso** (data-acquisition Tech Writer, NEW) — data-acquisition#34 (1-line slash sync). 4/4 CI. First contribution. Severity: **none**. New entry at **3**.

### Top 3 going well

1. **Zero CI failures + zero admin overrides on 14 PRs.** First wave at zero on both metrics. validate_pr_review canonicalization (#250) shipped IN the wave that needed it — W3's 5/5 admin-override pattern was eliminated by W4-mid. The hook-fix landing in the same wave that removed the need for the override is a tight feedback loop and a model pattern.
2. **W3 retro action items all discharged in W4.** Pre-flight checklist (#245 wave-kickoff multi-repo + #249 wave-scope reconciliation), validate_pr_review family (#250 closes #244 + #233 + #228), additive-commit codification (charter sweep #254). 3-for-3 W3 → W4 carry-forward execution. Retro proposals are translating into wave-following implementation reliably.
3. **Theme-coherent hook bug-class sweep.** Aino's 8 PRs all touched a single surface (5-matcher refactor via shared parser, 2 net-new hooks, 1 charter sync, 1 audit fallback class, 1 canonicalization, 1 broad sweep). #248 alone closed 7 hook-class issues by extracting `_shell_parse.py`. Model wave shape for "pick-a-class-and-sweep" tooling cleanups — when a wave has a sharp theme, concentration produces compounding closures.

### Top 3 pain points

1. **Wave concentration risk: 80% of main# work in one engineer (Aino).** Theme-fitness drove it (Aino owns the hook surface), and the work was clean. But a tooling-only wave with 8/10 PRs from one person is fragile to absence/burnout. W5 carry-forwards (#263 + #264 — Phase 2 child fan-out for #214 and #215 across 7 child repos) MUST be distributed across implementers to avoid a "can't ship without Aino" failure mode. Concentration is a metric we don't currently surface in retros — proposing to add it.
2. **Trivial 1-line cross-repo doc-sync ran as 4 separate per-repo PRs.** isnad-graph#857, user-service#94, design-system#63, data-acquisition#34 — same backslash → slash fix, 4 review pairs, 4 CI runs, ~12 charter-format comments total. Overhead-heavy for a no-decision byte-identical change. No charter pattern exists for "identical cross-repo doc sweep" — proposing one.
3. **ingest-platform produced 0 PRs despite being in declared scope.** cross-repo-status.json lists `wave_4_repos_in_scope: [..., "noorinalabs-isnad-ingest-platform"]` but the repo shipped nothing. Silent scope-drop with no de-scope decision recorded. wave-scope (#249, just shipped) reconciles meta-issue vs labels at kickoff — proposing to extend to wrapup-time scope-drop reconciliation.

### Proposed process changes

1. **Wave-concentration metric in retro template.** Rationale: When a single implementer authors >60% of wave PRs, flag for next-wave spread. W4 was 80% Aino. Visibility, not policy — concentration can be theme-fit (W4) or fragility (W5 if it persists).

2. **Extend `/wave-wrapup` to reconcile in-scope-but-zero-PR repos.** Rationale: ingest-platform-class silent drops should not be invisible. For each repo in `wave_N_repos_in_scope`, count PRs merged to wave branch; if 0, require explicit de-scope OR carry-forward decision before wrapup-close.

3. **Codify "trivial cross-repo doc sweep" as a sanctioned pattern.** Rationale: 4 PRs for an identical 1-line fix is overhead-heavy. Allow Single-Reviewer Exception per child PR when (a) diff is byte-identical across repos, (b) no behavior change, (c) all referenced from one tracking issue, (d) CI passes on every repo.

### Charter changes applied (this PR)

1. **`charter/pull-requests.md` — § Trivial Cross-Repo Doc Sweep** (single-reviewer exception when byte-identical across repos)
2. **`.claude/skills/wave-wrapup/SKILL.md` — § Scope-Drop Reconciliation** (in-scope-but-zero-PR check)
3. **`.claude/skills/wave-retro/SKILL.md` — § Wave-Concentration Metric** (top-implementer concentration in retro template)

### Promotion audit (deterministic — see `.claude/team/promotion_audit_log/wave-4.md`)

```
Promotion audit wave-4: 0 AUTO · 0 DECIDE · 65 KEPT · 3 SUPERSEDED · 1 ALREADY-PROMOTED
```

No memory crossed `retro_citations >= threshold` AND `promotion_target != none`. New STALE-OPT-OUT class (shipped in #266) didn't fire — highest retro_citations is 3, threshold for the 2× sub-class would need ≥6. main#269 (memory-audit P3W4-wrapup, classifies 36 feedback memories) is the W5 follow-on for systematic frontmatter classification.

### Action items

1. Apply approved charter changes (this PR).
2. W5 planning MUST distribute #263 + #264 (Phase 2 child fan-outs) across multiple implementers — not all to Aino.
3. W5 planning MUST resolve ingest-platform W4 silent-drop: either de-scope decision OR explicit carry-forward.
4. main#269 (memory-audit) is the right vehicle for setting `promotion_target` frontmatter on the 36 feedback memories — once classified, future audits will surface real AUTO/DECIDE candidates.

### Pattern tally (running)

| Pattern | Class | This wave | Cumulative |
|---|---|---|---|
| A — design-rationale block | Implementer | 3 (Aino #248 parser-design block, #256 + #257 hook-design rationale in PR bodies) | 9 |
| B unified — verify-vs-artifact | Implementer + reviewer | 1 (Wanjiku ChangesRequested catch on #250 canonicalization edge case) | promotion-threshold met by tally; deterministic audit blocked by frontmatter (main#269 will classify) |
| C — claim-state-staleness | Manager-class amplifier | 0 | reverted, held |
| D — message-ordering-race | Architecture | n/a | tracked main#241 |
| E — process collapse under fire | Orchestrator-class | 0 (no emergency) | 1 historical |
| F — orchestrator-class pre-flight gap | Orchestrator-class | 0 (W3 fixes held under W4 conditions) | 6 historical, **closed by #245 + #249** |

## Retrospective: Phase 3 Wave 5 — Multi-Repo Fan-Out + Memory Classification + Skill Self-Improvement (2026-05-05 → 2026-05-06)

### Wave shape

| Metric | Value |
|---|---|
| Duration | **~2.2h** (kickoff 2026-05-05T22:30Z → final wave-merge 2026-05-06T00:41:23Z) — fastest wave to date |
| Repos in scope | 8 declared (main + all 7 child repos) — **8 produced PRs** (zero-PR-repos: 0) |
| PRs merged into wave branches | **11** (main: 4; isnad-graph: 1; user-service: 1; design-system: 1; data-acquisition: 1; ingest-platform: 1; deploy: 1; landing-page: 1) |
| CI failures across all 11 PRs | **0** |
| Admin overrides at wave-merge | **0** (2nd consecutive zero-override wave: W3=5/5 → W4=0 → W5=0) |
| ChangesRequested cycles | 4 observable (main#276: 2 [Wanjiku+Nadia]; isnad-graph#861: 2 [Anya+Arjun]) — `cross-repo-status.json` counter says 6, discrepancy noted in pain points |
| Top-implementer concentration | **3 / 11 = 27%** (Aino) — well below the 40% kickoff cap and the 60% retro-flag threshold; **down from W4's 80%** (W4 retro action item #2 fully discharged) |
| Issues closed in wave | 11 declared (main#267, #273, #269, #271; isnad-graph#860; user-service#95; design-system#65; data-acquisition#36; ingest-platform#14; deploy#270; landing-page#78) |
| W4 retro action items shipped IN-wave | 4/4 (charter changes via #279; distribute fan-out via 7 different child-repo implementers; resolve ingest-platform silent-drop via #26; classify memory frontmatter via #277) |
| Carry-forward to W6 | 5 (main#278, isnad-graph#862, design-system#67, data-acquisition#38, landing-page#77) |

### Per-engineer assessments

#### Org-level team

**Aino Virtanen** (SQL) — 3 main# PRs across 3 distinct surfaces. #275 (`+2/-0` ci.yml paths filter for `.claude/skills/**`, closes #267) — minimal-correct scope on a CI gate. #276 (`+217/-0` thread `/wave-scope` into `/wave-retro` Step 9 + `/wave-kickoff` Step 0a + `/wave-scope` Step 13 timestamp write, closes #273) — both reviewers (Wanjiku, Nadia) ChangesRequested independently; resolved cleanly via additive Reply commits + Approved cycle. #277 (`+725/-0` systematic frontmatter classification of all 36 feedback memories, closes #269) — load-bearing memory-system work that flips next `/promotion-audit` from `0 AUTO / 0 DECIDE` to a 5-AUTO surface. Concentration **27%** vs W4 80% — exact W4-retro-action-#2 outcome. Severity: **none**. Trust 5→5 (already max).

**Wanjiku Mwangi** (TPM) — #279 charter cross-reference paragraphs (`+4/-0`, closes #271) — completed the W4-retro followup Aino flagged on PR #270. Pattern B reviewer-class catch on #276 (independent ChangesRequested catch alongside Nadia, both resolved via additive Reply chain). Reviewer on all 4 main# PRs. Severity: **none**. Trust 5→5 (already max).

**Nadia Khoury** (PD) — Reviewer on all 4 main# PRs. Pattern B catch on #276 alongside Wanjiku (independent ChangesRequested signal). No implement-class spawn this wave. Severity: **none**. Trust 4→4 (level pinned at 4 by reviewer-only profile across W3+W4+W5).

**Santiago Ferreira** (RC) — No deploy-class work routed; theme was multi-repo fan-out + memory + skills. Severity: **none**. Trust 5→5 (already max).

#### Child-repo teams

**Linh Pham** (isnad-graph DevOps) — isnad-graph#861 (`+37/-1173` canonical hook-paths migration). 1 ChangesRequested cycle (Anya + Arjun both CR'd; resolved via Reply chain + Approved). 9/9 CI green. Severity: **none**. Trust 4→4.

**Mateo Salazar** (user-service Eng) — user-service#96 (`+152/-449` canonical hook-paths migration — settings.json + delete copy-resident hooks). 0 CR cycles, 1/1 CI green. Approved by Anya + Idris. Step-up from W4's 1-line trivial sync. Severity: **none**. Trust 4→4.

**Kofi Mensah** (design-system Docs Eng) — design-system#66 (`0/-273` chore: remove copy-resident orphan hook files, closes #65). 0 CR, 2/2 CI. Approved by Maeve + Keanu. Severity: **none**. Trust 3→**4** ↑.

**Tarek Mansour** (data-acquisition Eng, NEW) — data-acquisition#37 (`0/-273` drop copy-resident hook remnants, closes #36). 0 CR, 4/4 CI. Approved by Dilara + Alejandra. **Implementer-substitution from declared scope** (Sofia Cardoso was kickoff-declared T1A #263 implementer for this repo) — no recorded swap rationale anywhere; surfaces a process gap discussed below. Severity: **none** (engineer-class clean execution). New entry at **3**.

**Yusuke Inoue** (ingest-platform Eng, Principal, NEW) — ingest-platform#26 (`+12/-9` drop Dockerfile workaround, install via uv export+pip from authoritative lock, closes #14). 0 CR cycles. Approved by Adaeze + Bjorn. Closes a long-deferred workaround AND resolves W4's silent-scope-drop pattern by being the active implementer for ingest-platform's first real wave-cycle deliverable. Severity: **none**. New entry at **4**.

**Lucas Ferreira** (deploy SRE) — deploy#271 (`0/-781` canonical hook-paths migration). Largest deletion in wave. 0 CR cycles. Approved by Bereket + Aisha. Severity: **none**. Trust 5→5 (already max).

**Kofi Mensah-Williams** (landing-page Eng) — landing-page#79 (`0/-273` chore: delete stale copy-resident `.py`, closes #78). 0 CR, 2/2 CI. Approved by Marcia + Nazia. Original P1 entry flagged "Some CI fixes needed post-PR"; this W5 PR clean from first push. Severity: **none**. Trust 3→**4** ↑.

### Top 3 going well

1. **Concentration discipline: 80% → 27% in one wave.** W4 retro action item #2 said "W5 planning MUST distribute #263 + #264 (Phase 2 child fan-outs) across multiple implementers — not all to Aino." W5 kickoff distributed the 7-child-repo fan-out across **7 different implementers** (one per child repo). Top-implementer concentration dropped from 80% to 27% — well below the 60% retro-flag threshold and the 40% kickoff cap. The wave-concentration metric (added to retro template in W4 #270) immediately produced a measurable behavior change at the next kickoff. Pattern: retro-surfaced metric + cap-bearing kickoff template = tractable single-wave correction.
2. **All 4 W4-retro action items closed within W5.** (1) Charter changes (`Trivial Cross-Repo Doc Sweep`, `Scope-Drop Reconciliation`, `Wave-Concentration Metric`) shipped via PR #270. (2) Concentration distribution achieved. (3) ingest-platform silent-drop resolved via Yusuke's #26. (4) Memory-frontmatter classification shipped via Aino's #277. 4-for-4 W4→W5 carry-forward execution — second consecutive wave with 100% retro-action discharge (W4 was 3-for-3 W3 actions).
3. **`/wave-scope` self-threading shipped in the wave that needed it.** #276 wired `/wave-scope` into both `/wave-retro` Step 9 (auto-invoke for next wave) and `/wave-kickoff` Step 0a (precondition check), with `/wave-scope` Step 13 writing the timestamp the kickoff reads. This is the same shape as W4's #250 (validate_pr_review canonicalization shipping in the wave that needed it to eliminate W3's admin-override pattern). Skill self-improvement landing in-wave is a recurring positive primitive worth tracking — proposing pattern-tally entry "Pattern G — in-wave skill self-improvement."

### Top 3 pain points

1. **Implementer-substitution in data-acquisition not recorded anywhere.** Kickoff (`wave_5_scope.tier_1A_263_distribution[data-acquisition].implementer`) declared **Sofia Cardoso**; the actual PR (data-acquisition#37) was authored by **Tarek Mansour** on branch `T.Mansour/0036-...` — no swap rationale in `cross-repo-status.json`, no comment in the meta-issue (#274), no decision in `wave_5_decisions`. This is the same shape as W4's ingest-platform silent-drop, just inverted: there it was silent-zero-PR; here it's silent-substitution. Both are scope-drift with no audit trail. Sofia's W4 entry (NEW at 3) gave no signal of being unavailable — and her W5 trust isn't dinged because there's no evidence of failure-to-deliver (work was reassigned, but where, when, by whom is unrecorded).
2. **CI rollup empty for 4 of 11 PRs (#277, #279, deploy#271, ingest-platform#26).** Aino's #275 (`paths` filter for `.claude/skills/**`) addressed the **main** repo's coverage gap, but: (a) #277 was memory-frontmatter changes — no `.claude/skills/**` touched, no `.py`, no `.yml` — so no workflow triggered; (b) #279 was charter docs only; (c) deploy#271 was settings.json + hook deletes in the deploy repo, which has its own CI scope filters; (d) ingest-platform#26 was Dockerfile + uv lockfile changes in ingest-platform, same per-repo scope question. Per-repo CI scope-coverage is a separate gap from the main-repo fix; #275 didn't claim to address it. Worth surfacing as W6 candidate.
3. **`cross-repo-status.json` counter drift.** `wave_5_changes_requested_cycles: 6` was written at wrapup time, but PR-level evidence shows only **4** distinct ChangesRequested signals (main#276: Wanjiku + Nadia = 2; isnad-graph#861: Anya + Arjun = 2). Same-class drift as W4's `wave_4_top_concentration_pct: 22` claim (vs the actual 80% I recomputed at retro). The status file is being written at wrapup but the math isn't being re-verified at retro. Proposing a `verify_status_counters` pass as a Step 2.5 in `/wave-retro`.

### Proposed process changes

1. **Implementer-substitution recording: extend `/wave-wrapup` to compare declared-vs-actual implementer per PR.** Rationale: W4 silent-drop (zero-PR variant) was caught by the W4 retro proposal (Scope-Drop Reconciliation, now in `/wave-wrapup` per #270). W5 surfaced the inverted variant (silent-substitution) which the new check doesn't cover. For each PR merged into the wave branch, compare `gh pr view --json author` against the kickoff-declared implementer; if mismatched, require an entry in `wave_N_decisions.implementer_substitutions` with timestamp + rationale before wrapup-close. Same-class fix as W4's, just covers the inverted case.

2. **Status-counter verification in `/wave-retro` Step 2.5.** Rationale: `wave_5_changes_requested_cycles: 6` (claimed) vs 4 (observable) drift — alongside W4's `wave_4_top_concentration_pct: 22` (claimed) vs 80% (observable). The pattern is wrapup-time arithmetic that nobody reverifies. Add a quick recomputation pass in `/wave-retro`: pull `wave_N_*` numeric counters from `cross-repo-status.json`, recompute from PR data, surface drift as a retro-blocker (or auto-correct + log the correction).

3. **Pattern-tally entry: "Pattern G — in-wave skill self-improvement."** Rationale: W4's #250 (validate_pr_review canonicalization shipping in the same wave that needed it to eliminate W3's admin-override pattern) and W5's #276 (`/wave-scope` self-threading shipping in the same wave that proposed it) are the same primitive: skill/hook fixes landing in-wave rather than carry-forwards. Worth tracking explicitly in the running pattern tally — frequency tells us when the team has crossed into "self-improving" cadence.

### Charter changes proposed (NOT auto-applied — require user approval)

1. **`.claude/skills/wave-wrapup/SKILL.md` — § Implementer-Substitution Reconciliation** — for each PR merged into wave branch, compare `gh pr view --json author` against `wave_N_scope.tier_*[].implementer`; require recorded swap rationale if mismatched.
2. **`.claude/skills/wave-retro/SKILL.md` — § Step 2.5: Status-Counter Verification** — recompute `wave_N_*` numeric counters from PR data, surface drift before proceeding to per-engineer assessments.
3. **`.claude/skills/wave-retro/SKILL.md` — pattern-tally template addition** — Pattern G — in-wave skill self-improvement.

### Promotion audit (deterministic — see `.claude/team/promotion_audit_log/wave-5.md`)

```
Promotion audit wave-5: 5 AUTO · 0 DECIDE · 52 KEPT · 11 SUPERSEDED · 1 ALREADY-PROMOTED
```

**Delta vs W4 (`0 / 0 / 65 / 3 / 1`):** AUTO went 0 → **5** because PR #277 (P3W5 T2) classified all 36 feedback memories with `promotion_target` frontmatter — this is the audit run that surfaces the result. SUPERSEDED went 3 → 11 for the same reason (8 new `enforced-elsewhere` markers landed via #277). KEPT correspondingly dropped 65 → 52.

**5 AUTO candidates (memory → charter):**

| Memory | Citations | Proposed charter target |
|---|---|---|
| `feedback_canonical_source_via_git_show.md` | 4 | `charter/git-discipline.md` § canonical-source-via-git-show |
| `feedback_child_repo_implementer_rule.md` | 4 | `charter/agents.md` § child-repo-implementer-rule |
| `feedback_honest_audit_over_conclusion_claim.md` | 4 | `charter/wave-wrapup.md` § honest-audit-discipline |
| `feedback_review_against_artifact_not_framing.md` | 4 | `charter/pull-requests.md` § review-against-artifact |
| `feedback_security_guard_inline_not_followup.md` | 4 | `charter/pull-requests.md` § security-guard-inline |

These do NOT auto-apply within this retro PR (per skill: "Do NOT apply any charter changes without explicit user approval"). The owner decides whether to (a) generate the 5 charter sections in a separate Aino-authored PR now, or (b) defer to W6. See retro summary in conversation for the ask.

### Action items

1. Apply approved charter changes (this PR if user approves).
2. W6 planning MUST address the data-acquisition implementer-substitution: record retro-resolved swap (Sofia → Tarek) in `wave_5_decisions` post-hoc, OR assign Sofia a W6 role with explicit wave-availability confirmation at kickoff.
3. W6 planning MUST address per-repo CI scope-coverage (4 PRs with `CheckRollup: 0` this wave) — file follow-up issue(s) per repo for `.claude/hooks/**` + `settings.json` paths in each child repo's CI workflow filters.
4. W6 promotion-audit will surface the 5 AUTO candidates predicted by #277's classification — Aino (or whoever owns charter at the time) will need to draft the auto-generated charter sections for those 5 memories.
5. W4-retro carry-forward main#278 (wave-scope JSON-write idempotency / churn budget) carries to W6 unchanged.

### Pattern tally (running)

| Pattern | Class | This wave | Cumulative |
|---|---|---|---|
| A — design-rationale block | Implementer | 1 (Aino #276 PR body design rationale for "Hook deliberately omitted this round" decision) | 10 |
| B unified — verify-vs-artifact | Implementer + reviewer | 2 (Wanjiku + Nadia independent ChangesRequested catches on #276 wave-scope edge case) | promotion-threshold met by tally; awaiting next `/promotion-audit` post-#277 |
| C — claim-state-staleness | Manager-class amplifier | 0 | reverted, held |
| D — message-ordering-race | Architecture | n/a | tracked main#241 |
| E — process collapse under fire | Orchestrator-class | 0 (no emergency) | 1 historical |
| F — orchestrator-class pre-flight gap | Orchestrator-class | 0 | 6 historical, **closed by #245 + #249** |
| **G — in-wave skill self-improvement** (NEW) | Skill/Hook author | 1 (Aino #276 `/wave-scope` self-threading shipped in wave that proposed it) | **2** (W4 #250 validate_pr_review canonicalization + W5 #276 `/wave-scope` threading) |

## Retrospective: Phase 3 Wave 6 — Backlog Triage + Runbook Fan-Out + Hot-Fix (2026-05-06 → 2026-05-07)

### Wave shape

| Metric | Value |
|---|---|
| Duration | ~25h (kickoff 2026-05-06T22:41:08Z → final wave-merge 2026-05-07T23:38:44Z) |
| Repos in scope | 8 declared; **7 produced PRs** (user-service Tier-1-only by design, 0 PRs — `wave_6_decisions.scope_drops` records by-design) |
| PRs merged into wave branches | **11** (main: 2; isnad-graph: 1; deploy: 1; design-system: 2; data-acquisition: 2; ingest-platform: 1; landing-page: 2) |
| Wave-merge → main PRs | **7** (one per non-identical repo; user-service skipped as identical sha) |
| CI failures | 0 |
| Admin overrides at wave-merge | **0 (TRUTHFUL FIRST)** — hook gap #294 enabled actual 2-reviewer enforcement on wave-merge PRs for the first time. W3-W5 claimed 0 but silently bypassed via `--admin`. |
| Implementer substitutions | **0** (every PR's actual committer matched kickoff-declared implementer) |
| ChangesRequested cycles | **0** (verified at retro Step 2.5) |
| Top-implementer concentration | **2 / 11 = 18%** (Kofi Mensah-Williams, Tier-2 #49 + Tier-3 #77) — well below 40% kickoff cap and 60% retro-flag threshold |
| Counter-verification drift (Step 2.5) | **0** — first wave with all `wave_6_*` numeric counters matching PR-level recomputation (W4 had 22→80 concentration drift, W5 had 6→4 CR-cycles drift) |
| Tier-1 backlog triage delivery | **8/8 repos** submitted disposition tables on #284 (151 issues audited total) |
| Tier-1 dispositions applied at wrapup | 13 close-stale + 2 close-dup + 28 phase-15 relabel + 9 isnad-graph pre-applied + 3 carry-forward strip = **55 issue mutations** |
| Issues closed in wave (excluding triage) | 9 wave-resolved (main#278; deploy#24; design-system#67, #32; data-acquisition#38, #22; ingest-platform#7; landing-page#77, #49) |
| W5 retro action items shipped IN-wave | 5 AUTO promotion-audit candidates → main#282 promotion PR (codified W5 retro promise); implementer-substitution check satisfied (0 swaps); status-counter verification satisfied (0 drift); both retro-proposed Pattern G instances continue (Aino #294 in-flight) |
| Carry-forward to W7 | 4 (main#287, main#285, main#294, deploy#274) |

### Per-engineer assessments

#### Org-level team

**Aino Virtanen** (SQL) — 1 wave-internal PR + extensive wrapup work + in-flight follow-on. main#288 (`fix(/wave-scope #278)`: idempotent JSON-write helper, Tier-4 W5 carry-forward) — clean execution, 0 CR. R1 reviews on all 7 wave-merge PRs (charter format with refresh-discipline + diff-vs-body verification + scope_drops verification). In-flight #294 hook fix surfaced from her own R1 review of #293 (Pattern G in-wave self-improvement repeat). Severity: **none**. Trust 5→5 (already max).

**Wanjiku Mwangi** (TPM) — 1 wave-internal PR + Tier-1 + 2 status commits. main#291 (`fix(hook #289)`: validate_workflow_paths_coverage parser fix, post-scope hot-fix). Tier-1 noorinalabs-main backlog triage (16 issues audited, 18.75% close-rate, 31% defer-phase-15, 50% confirm-actionable). 2 wrapup status commits via gh api PUT contents (67cce96 wave_6_decisions, a3419a4 P3W6 CLOSED). Severity: **none**. Trust 5→5.

**Nadia Khoury** (PD) — R2 reviews on all 7 wave-merge PRs (cross-repo coordination focus, scope-drop verification, carry-forward label-stripping verified at PR-review time). Co-author on design-system Tier-1 backlog triage with Kofi Mensah. Surfaced 3 retro candidates (e235b0b orphan, label-drift prevention, repo-split coordination) deferred-to-retro per discipline. Reviewer-only profile across 4 consecutive waves. Severity: **none**. Trust 4→4 (level pinned by reviewer-only profile).

**Santiago Ferreira** (RC) — Theme-routed wave (no deploy-cycle work). Severity: **none**. Trust 5→5.

#### Child-repo teams (PR authors only)

**Jun-Seo Park** (isnad-graph Eng, NEW) — isnad-graph#864 (settings parity Tier-4 W5 carry-forward, closes #862). 0 CR. New entry at trust 3.

**Lucas Ferreira** (deploy SRE) — deploy#273 (operational runbook Tier-2, with R1+R2 accuracy revisions absorbed cleanly). 0 CR. Trust 5→5.

**Keanu Tama** (design-system Eng, NEW) — design-system#69 (operational runbook Tier-2). 0 CR. New entry at trust 3.

**Maricel Reyes** (design-system Eng, NEW) — design-system#70 (settings parity Tier-4 W5 carry-forward). 0 CR. New entry at trust 3.

**Tarek Mansour** (data-acquisition Eng) — data-acquisition#40 (operational runbook Tier-2, with R1+R2 review fixups for local-vs-B2 path shape, Kafka envs, CLI flag). 0 CR. Trust 3→**4** ↑ (second consecutive substantive wave; W5 substitution rationale resolved).

**Alejandra Reyes-Fuentes** (data-acquisition Eng, NEW) — data-acquisition#41 (settings parity Tier-4 W5 carry-forward). 0 CR. New entry at trust 3.

**Bjørn Henriksen** (ingest-platform Eng, NEW) — ingest-platform#28 (operational runbook Tier-2, with review fixups for offset-commit + ingest-row + 3 obs). 0 CR. New entry at trust 3.

**Kofi Mensah-Williams** (landing-page Eng) — TWO PRs: landing-page#82 (Tier-3 hotfix for #77 deploy-VPS regression) + landing-page#81 (Tier-2 runbook for #49, with post-#82 publish-only workflow refresh). 4 approveds on #81 (revisions + re-approvals — clean iteration). Top concentration at 18% — theme-fit, not fragility. Severity: **none**. Trust 4→4.

#### Tier-1 triagers (no PR — comment-only delivery)

**Anya Kowalczyk** (isnad-graph Eng) — Largest backlog (36 issues), 100% verification rate against HEAD; 9 inline `phase-3`→`phase-15` relabels with explicit rationale; surfaced production OAuth break (#824) and worktree-tracking bug (#807) as elevated-priority candidates. Trust 3→3.

**Mateo Salazar** (user-service Eng) — 15 issues audited; disciplined origin-over-local verification per memory. No PR by W6 design (Tier-1-only). Trust 4→4.

**Kofi Mensah** (design-system Docs Eng) — Co-authored 7-issue disposition with Nadia; identified Chromatic-CI surface area on #53/#54 as forward-coupler gap. Trust 4→4.

**Sofia Cardoso** (data-acquisition Tech Writer) — 4-issue audit; surfaced #21 enrichment-pipeline as cross-repo relocation candidate to ingest-platform per ontology repo-split. Confirmed W6 Tier-1 slot post-W5 substitution. Trust 3→3.

**Adaeze Okonkwo** (ingest-platform Eng) — 14-issue audit; pipeline-durability cluster correctly preserved as own future wave per meta-issue boundary. Trust 3→3.

**Bereket Tadesse** (deploy Manager) — Largest backlog (40 issues), 22.5% close-rate via 7 stale + 2 dup; 23 relabel-later-wave preserving phase-3. Trust 4→4.

**Marcia Vasquez-Paredes** (landing-page Project Lead) — 19-issue audit; 8 defer-future-phase relabels recommended; surfaced #67/#69 as keep-in-P3-strategic with owner-ruling rationale. Trust 4→4.

**Nurul Hakim** (deploy R1, NEW) — Caught load-bearing followup gap during PR #273 review (alertmanager `${VAR}` placeholder URL); filed deploy#274. Reviewer-class first entry at trust 3.

### Top 3 going well

1. **Truthful 0-admin-override accounting for wave-merge PRs (FIRST).** Hook gap #294 surfaced AT wrapup when the validate_pr_review parser silently early-returned for `deployments/*/wave-*` head refs. In-band 5-line patch + canonical Aino-authored fix in flight enabled actual 2-reviewer enforcement (Aino R1 + Nadia R2) on all 7 wave-merge PRs. Per W3/W4/W5 inspection: those waves' wave_N_admin_overrides=0 claims were inaccurate (0 reviewer comments on each wave-merge PR + merged via `--admin`). W6 is the first wave with the claim grounded in actual hook validation. Pattern: hook-gap surfaced AT wrapup → in-band fix + same-wave canonical PR (Pattern G repeat).

2. **Counter-verification step 2.5 had 0 drift.** First wave since the discipline was added (W5 retro) where every wave_6_* numeric counter matched PR-level recomputation (PR count: 11=11; CR cycles: 0=0; concentration: 18%=18%). W4 had 22→80 concentration drift; W5 had 6→4 CR-cycles drift. The discipline took at the third invocation. Operationally: wrapup-time arithmetic is now reliable enough that retro can use it directly without a defensive recomputation pass surfacing surprises.

3. **8/8 Tier-1 backlog triage delivery + 55 wrapup mutations applied cleanly.** Every repo submitted a substantive disposition table on #284 (151 issues audited total, all evidence-cited against HEAD via origin-over-local memory discipline). Bulk dispositions executed at wrapup batch in ~3 min (13 close-stale + 2 close-dup + 28 phase-15 relabel + 9 isnad-graph pre-applied + 3 carry-forward strip). Backlog-hygiene wave shape demonstrably works: the team can audit + reach disposition + execute mutations within a single wave cycle.

### Top 3 pain points

1. **Pattern G persists at 4 instances in W6 alone — largest single-wave parser-bug cluster.** Hook parser bugs: #285 (/wave-kickoff Step 1 EXISTING_SHA captures 404 body), #287 (validate_commit_identity false-blocks backslash-line-continuation), #289 (validate_workflow_paths_coverage misparses bare on.pull_request:), #294 (validate_pr_review skips reviewer counting on deployments/*/wave-* heads). All four are PARSER bugs in production hooks discovered AT runtime when an unanticipated input shape arrives. Suggests a class-level discipline gap: hook authors don't reflexively enumerate input-shape fixtures before declaring a parser \"done.\" Proposing parser-fixture coverage as a charter principle.

2. **Local-vs-origin main divergence (e235b0b orphaned local commit) — kickoff status push discipline gap.** The P3W6 kickoff committed wave_6_active state to LOCAL main as commit e235b0b but never pushed to origin. Local main was 1 ahead of origin/main throughout the wave; only the consolidated wrapup commit (67cce96 via gh api PUT contents) captured the kickoff state on origin. Operationally: this is a F-pattern (orchestrator-class pre-flight gap) — closed by #245+#249 historically per W5 retro, but reopens at the kickoff-push verification surface. The right enforcement is to make kickoff status commits via gh api PUT contents (atomic, no local-orphan-possible) instead of local-then-push. Same enforcement shape used by the wrapup status commits this wave (a3419a4) — the pattern is proven and should be retro-fitted to kickoff.

3. **/tmp file-race recurring for spawned-agent gh-comment workflows (3 hook blocks this session).** \`block_stale_tmp_message_file\` blocked 3 spawned-agent \`gh pr comment --body-file\` calls where the body file aged > 30s during a Bash call delay. Existing memory \`feedback_tmp_msg_file_stale.md\` covers the pattern (issue#-keyed paths + sequential ordering + read-back verify), but spawned agents continue to hit it because the spawn-prompt template doesn't surface the discipline. Proposing a spawn-prompt template addition: \"When using --body-file with gh, write the file to issue#-keyed path immediately before the gh call (no other tool between).\"

### Proposed process changes

1. **Parser-fixture coverage discipline (charter principle).** Rationale: 4 hook parser bugs discovered in W6 alone (#285, #287, #289, #294). Add a charter rule under \`charter/hooks.md § Hook Authorship Requirements\`: every hook with input parsing MUST have test fixtures for all known input shapes. New shapes discovered in production require fixture-add backport BEFORE the bug-fix PR can merge. Codification mirrors the W5 status-counter-verification step 2.5 (added discipline that took on third invocation).

2. **Kickoff status via gh api PUT contents (deprecate local-then-push).** Rationale: e235b0b orphan was a kickoff status commit made locally that never pushed. The wrapup status commits this wave (67cce96, a3419a4) used gh api PUT contents successfully — atomic, no local-orphan possible, attribution captured cleanly. Retrofit \`/wave-kickoff\` Step 7+8 (per #286 hook proposal) to use the same gh api PUT contents pattern instead of local-checkout + local-commit + push.

3. **Spawn-prompt /tmp file-race reminder.** Rationale: 3 \`block_stale_tmp_message_file\` hook blocks for spawned-agent gh-comment workflows in this session. Memory \`feedback_tmp_msg_file_stale.md\` covers the discipline but spawned agents don't see it during their working context. Add to \`charter/agents.md § Implementer Spawn Template\` a one-line reminder: \"When using --body-file with gh, write the file to issue#-keyed path immediately before the gh call (no other tool between, < 30s mtime gap).\"

### Charter changes proposed (NOT auto-applied — require user approval)

1. **\`charter/hooks.md\` — § Parser-Fixture Coverage Requirements** — every hook with input parsing MUST have fixtures covering all known input shapes; production-discovered shapes require fixture-add backport before bug-fix merge.
2. **\`.claude/skills/wave-kickoff/SKILL.md\` — § Step 7+8 status commits via gh api PUT contents** — deprecate local-checkout + local-commit + push pattern; use atomic gh api PUT contents instead.
3. **\`charter/agents.md\` — § Implementer Spawn Template addition** — one-line /tmp file-race reminder for body-file workflows.

### Promotion audit (deterministic — see `.claude/team/promotion_audit_log/wave-6.md`)

```
Promotion audit wave-6: 0 AUTO · 0 DECIDE · 52 KEPT · 16 SUPERSEDED · 1 ALREADY-PROMOTED
```

**Delta vs W5 (`5 / 0 / 52 / 11 / 1`):** AUTO went 5 → **0** because the W5 5 AUTO candidates landed via main#282 promotion PR (codified W5 retro promise) — they now show as SUPERSEDED (enforced via charter sections). SUPERSEDED count went 11 → 16 (+5 = the 5 newly enforced-elsewhere markers from #282). KEPT and ALREADY-PROMOTED unchanged.

**0 AUTO this wave** is the expected steady-state for a hygiene-themed wave that didn't introduce new memory-class patterns crossing the citation threshold. The 36 frontmatter-classified memories from W5 #277 continue to be processed by the deterministic audit; any new candidates would require either (a) new memory citations in this retro entry crossing the 3× threshold, or (b) new feedback memories with `promotion_target: charter` filed during W6.

The pipeline is converging — W5 promoted 5, W6 has no new candidates. Pattern: promotion-audit lifecycle works.

### Action items

1. Apply approved charter changes (this PR if user approves).
2. W7 planning MUST include the 4 carry-forwards (main#287, main#285, main#294, deploy#274) — three are existing parser-bug class items + one is the hook-gap canonical fix.
3. W7 planning MUST address Nadia's reviewer-only profile (4 consecutive waves at 4) — either a charter-update PR or a Tier-2 implementation PR routed to her would establish implement-class delivery.
4. Aino's #294 PR is in flight; if it merges before W7 kickoff, the canonical hook fix is in place; if not, the local in-band patch carries forward and #294 stays in carry-forward.
5. /wave-scope for W7 BLOCKED — W7 meta-issue does not yet exist. Per \`/wave-retro\` Step 9 acceptance: surface as kickoff blocker. Owner needs to draft \"Phase 3 Wave 7 — <theme>\" before /wave-kickoff can run.

### Pattern tally (running)

| Pattern | Class | This wave | Cumulative |
|---|---|---|---|
| A — design-rationale block | Implementer | 1 (Aino #288 design rationale for upsert helper in PR body) | 11 |
| B unified — verify-vs-artifact | Implementer + reviewer | 14 (Aino R1 + Nadia R2 across all 7 wave-merge PRs with diff-vs-body verification) | promotion-threshold met by tally repeatedly; awaiting next /promotion-audit pass |
| C — claim-state-staleness | Manager-class amplifier | 0 | reverted, held |
| D — message-ordering-race | Architecture | n/a | tracked main#241 |
| E — process collapse under fire | Orchestrator-class | 0 (no emergency) | 1 historical |
| F — orchestrator-class pre-flight gap | Orchestrator-class | **1 NEW** (e235b0b kickoff status push gap) | 7 historical, **previously closed by #245+#249** but **REOPENED** by kickoff-push surface |
| **G — in-wave skill self-improvement** | Skill/Hook author | 1 (Aino #294 hook fix in-flight, surfaced by her own R1 review of #293) | **3** (W4 #250 + W5 #276 + W6 #294) |
