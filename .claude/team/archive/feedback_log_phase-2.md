# Feedback Log — Phase 2 archive

> Archived byte-for-byte from `.claude/team/feedback_log.md`
> at phase close (#964, meta #960), preserving original file order. Do not edit —
> append-only history; new entries go to the live file for the current phase.

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

### Promotion audit (deterministic — see `.claude/team/promotion_audit_log/p2-wave-10.md`)

**Result: 0 AUTO · 0 DECIDE · 54 KEPT · 4 SUPERSEDED.**

No memory has crossed thresholds for auto-promotion this wave. The four superseded entries are unchanged from W9. The 54 kept memories include the 5 newly-saved Bereket primitives — each at retro_citations=1, below threshold. Consider revisiting at next phase boundary (phase-3 W1 retro) when citation counts may have accumulated.

### Carry-forward (passed via skill args)

- `deploy#86` → phase-3 (async routine `trig_01Bif8T51pdaYFjkbM5bERyL` fires post-merge)
- `deploy#151` → phase-3 (manual SRE B2 tfstate-key migration)
- `user-service#84` → phase-3 (manual DEPLOY_REPO_PAT secret provisioning)

### Charter changes proposed (require user approval)

None this retro. Process changes above are skill-level (wave-wrapup step 8) and convention-level (same-file PR sequencing) — both can be applied without charter amendment if approved.


---

