# Team Feedback Log

Track all feedback events here. Format:

```
## [DATE] — [FROM] → [TO] — Severity: [minor/moderate/severe]
[Feedback content]
[Action taken, if any]
```

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
