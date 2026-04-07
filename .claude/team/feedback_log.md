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
