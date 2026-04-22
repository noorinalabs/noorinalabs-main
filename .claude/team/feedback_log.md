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
