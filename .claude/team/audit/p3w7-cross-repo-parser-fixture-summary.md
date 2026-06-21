# P3W7 Cross-Repo Parser-Fixture Coverage Audit — Summary

**Wave:** Phase 3, Wave 7  
**Meta-issue:** noorinalabs-main#300  
**Authored by:** Nadia Khoury (Program Director)  
**Date:** 2026-05-08  
**Status:** All 10 wave PRs merged; 0 admin overrides

---

## 1. Executive Thesis

The wave applied `charter/hooks.md § Parser-Fixture Coverage Requirements` (introduced W6 via PR #299) retroactively across all 8 Noorina Labs repos. The audit's central finding is a gap at the **parent→child update boundary**: fixture-first discipline was enforced in the parent canonical repo (`noorinalabs-main`) but hook-owning child repos that copied hooks in earlier waves did not inherit the fixture discipline. However, the deeper finding from committed-tree inspection (not filesystem enumeration) is that **all 7 child repos have already migrated to dispatcher-style** — they hold 0 committed local `.claude/hooks/` files, delegating entirely to the parent canonical via `settings.json`. The wave's audit work primarily *confirmed* that migration was already complete, while also establishing the first generation of charter reference implementations (PRs #301 and #305) for the new fixture-with-fix rule.

The target state — dispatcher-style children where the parent canonical holds all hook code and all fixtures — is **already realized across the organization**. The backport issues filed this wave address fixture gaps in the parent's own test suite for hooks that were under-tested before the charter rule existed.

---

## 2. Per-Repo State Table

| Repo | Classification | W7 Audit PR | Prior Migration PR | Remaining Work |
|------|---------------|-------------|-------------------|---------------|
| `noorinalabs-main` | **Hook-owning** (parent canonical) | #308 (Wanjiku, main parser audit) | — (canonical origin) | Backport issues filed in-wave; W8 carry-forward list below |
| `noorinalabs-isnad-graph` | **Dispatcher-style** | #871 (Anya Kowalczyk audit) | No committed local files — never had local hooks (worktree artifacts only, per Arjun R2) | Backport issues filed; no local hook maintenance burden |
| `noorinalabs-user-service` | **Dispatcher-style** | #100 (Mateo audit) | P3W5 #96 (commit 2191b1af) removed stale local copies | None — already dispatcher confirmed by Anya-K R2 |
| `noorinalabs-deploy` | **Dispatcher-style** | #279 (Bereket deploy audit) | Stale copies are untracked working-directory artifacts only (Weronika R2) | Untracked artifacts may need cleanup; no committed hook burden |
| `noorinalabs-design-system` | **Dispatcher-style** | #73 (Kofi audit) | W5 #66 removed stale local copies | None — already dispatcher confirmed by Beren R2 |
| `noorinalabs-data-acquisition` | **Dispatcher-style** | #45 (Sofia audit) | `.claude/hooks/` directory never existed in committed tree (Jeanclaude R2) | None |
| `noorinalabs-landing-page` | **Dispatcher-style** | #87 (Nazia audit) | W5 #79 removed stale local copies | None — already dispatcher confirmed |
| `noorinalabs-isnad-ingest-platform` | **No hooks** (placeholder) | — (skip per meta-issue scope) | — | Placeholder slot; no action required |

**Key correction:** Early audit framing used "stale-mirror" language for 3 repos (design-system, user-service, data-acquisition). Committed-tree inspection via `gh api repos/<repo>/git/trees/<sha>?recursive=1` showed no committed local hook files. The "stale-mirror" classification was a methodological error (see § 4 below).

---

## 3. Wave Deliverables Tally

**PRs merged:** 10 total, 0 admin overrides, all at 2026-05-08T02:49–02:50Z

| Tier | Repo | PR | Merge SHA | Authors |
|------|------|-----|-----------|---------|
| T2 | main | #305 (main#287 fix+fixtures) | eef6dc0f | Aino Virtanen |
| T2 | main | #301 (main#285 fix+fixtures) | 3b7b121b | Wanjiku Mwangi |
| T1 | main | #308 (main parser audit) | a08676aa | Wanjiku Mwangi |
| T1 | isnad-graph | #871 (Anya Kowalczyk audit) | 843ce62a | Anya Kowalczyk |
| T1 | user-service | #100 (Mateo audit) | cc54f7e8 | Mateo Salazar |
| T3 | deploy | #278 (Bereket Alertmanager #274) | 61a803d2 | Bereket Tadesse |
| T1 | deploy | #279 (Bereket deploy audit) | d6c03ccf | Bereket Tadesse |
| T1 | design-system | #73 (Kofi audit) | 4ff9f8d9 | Kofi Mensah |
| T1 | data-acquisition | #45 (Sofia audit) | 07275d8d | Sofia Cardoso |
| T1 | landing-page | #87 (Nazia audit) | 9302f8e2 | Nazia (landing-page roster) |

**Backport issues filed:** ~20 across repos (in-wave discovered parser gaps, Node 20 deprecation × 5 at wrapup via #309, plus 5 child-repo issues).

**Implementer substitutions recorded in `cross-repo-status.json`:** 2 (`wave_7_decisions` field).

**Charter reference PRs:** #301 + #305 are the first PRs to land under `charter § Parser-Fixture Coverage Requirements` (rule introduced W6 via #299). They are the worked examples future reviewers can cite.

---

## 4. Cross-Cutting Patterns Identified

### 4a. Pattern G — Live-trace acceptance template (canonical: PR #301)

**Shape:** Production trigger commit (e.g., e906e135) surfaces a parser failure → in-band workaround applied → backport PR filed with fixture that pins the exact trigger input shape, plus adjacent shapes discovered during triage.

**Implementation:** PR #301 (Wanjiku, main#285 fix) is the canonical Pattern G reference implementation: fix + fixture in the same commit, fixture named after the trigger commit, workaround documented in PR body. Recommend this as the required template for all future production-discovered parser bugs.

### 4b. Shared-utility hardening pattern (canonical: PR #305)

**Shape:** Parser fix applied at the `_shell_parse.tokenize()` module level rather than at individual call sites. All hooks that import `_shell_parse` benefit automatically, with no per-hook follow-up required.

**Implementation:** PR #305 (Aino, main#287 fix) is the canonical example. The `_shell_parse` module is the emerging centralization point for shell-input parsing across all parent-canonical hooks. Fixes there propagate organization-wide.

### 4c. Charter rule reference implementations (PRs #301 + #305)

Both PRs are the first post-`§ Parser-Fixture Coverage Requirements` merges. They demonstrate: fixture-with-fix in a single commit, coverage of the bug shape plus adjacent shapes, CI passing as acceptance. Future PR reviewers can cite these as the worked examples for the rule's application.

### 4d. Filesystem enumeration ≠ committed tree (methodological finding)

Three of seven child-repo audits initially misclassified repos as "stale-mirror hook-owning" based on filesystem enumeration. All three misclassifications shared a single root cause: the auditor enumerated working-directory files (including worktree artifacts and untracked files) instead of the committed git tree.

**Verified correct method:** `gh api repos/<owner>/<repo>/git/trees/<head_sha>?recursive=1` — queries the committed tree at a specific SHA, excluding untracked files, worktree artifacts, and gitignored content.

This is a charter-promotion candidate (see § 5, Proposal 2).

### 4e. Silent-no-op family of GitHub CLI bugs (3 surfaces this wave)

Three distinct silent-no-op patterns reproduced this wave:

1. **`gh project item-add`** — silently no-ops on cross-repo project boards. Affected: Wanjiku #308 × 5 issues, Sofia #45 × 2, Mateo #100 × 2. Working pattern: GraphQL `addProjectV2ItemById` mutation + PVTI node read-back verify.

2. **`gh project item-list --limit N`** — returns false matches on multi-repo boards because issue numbers collide across repos. Working pattern: PVTI node lookup, never filter by issue number alone.

3. **`gh api -X PATCH -f body=@file`** — silently passes the literal string `@file` as the body value. Affected: Kofi #73 PR body update. Working pattern: `--field "body=$content"` with inline shell expansion.

Existing memory `feedback_gh_pr_edit_silent_noop.md` should be extended to cover this whole family (see § 5, Proposal 3).

---

## 5. Charter Change Proposals

These proposals are NOT applied in this PR. They require separate review per `feedback_enforcement_hierarchy.md` (hook > skill > charter). Each is filed as a separate issue in W8 scope or marked as a charter-change PR candidate.

### Proposal 1 — Dispatcher-children sub-clause (charter `hooks.md § 5`)

**Target:** `charter/hooks.md § 5. Parser-Fixture Coverage Requirements`

**Change:** Add a sub-clause explicitly exempting children with no committed `.claude/hooks/` files from per-child fixture obligations. The existing rule's requirement ("Every hook with input parsing MUST have test fixtures") applies to hook-owning repos; dispatcher-style children satisfy coverage obligations through the parent-canonical test suite.

**Rationale:** The current rule text is silent on dispatcher-style children, creating ambiguity for future auditors. Design-system and landing-page are exemplars of the exempt pattern.

**Proposed language:**
> **Dispatcher-style children (no committed `.claude/hooks/`):** Children that delegate all hook execution to the parent canonical via `settings.json` are exempt from per-child fixture requirements. Coverage obligations are fulfilled by the parent's test suite. A child is classified as dispatcher-style when `gh api repos/<owner>/<repo>/git/trees/<head_sha>?recursive=1` returns 0 entries under `.claude/hooks/`. Design-system and landing-page (post-W5) are the canonical exemplars.

### Proposal 2 — Audit Protocol section (charter `hooks.md`, new section)

**Target:** `charter/hooks.md` — add `§ Hook Audit Protocol` after existing sections

**Change:** Codify `gh api repos/<repo>/git/trees/<sha>?recursive=1` as the mandatory first verification step in all hook audits. Prohibit classifying a repo's hook status from filesystem enumeration alone.

**Rationale:** Three misclassifications this wave from the same root cause (filesystem vs. committed tree). The correct method is one API call away; codifying it prevents recurrence.

**Proposed section:**
> **§ Hook Audit Protocol**
>
> When auditing a repo's hook ownership status (hook-owning vs. dispatcher-style):
> 1. Fetch the committed tree: `gh api repos/<owner>/<repo>/git/trees/<head_sha>?recursive=1 --jq '[.tree[].path | select(startswith(".claude/hooks/"))]'`
> 2. Classification: if the result is empty (`[]`), the repo is dispatcher-style. If non-empty, it is hook-owning.
> 3. Filesystem enumeration (SSH, ls, find) is NOT a valid substitute — it includes untracked files, worktree artifacts, and gitignored content that are invisible to git.

### Proposal 3 — Memory extension (not a charter change)

**Target:** `feedback_gh_pr_edit_silent_noop.md` in project memory

**Change:** Extend to cover the full silent-no-op family identified this wave (see § 4e above). Current entry covers only `gh pr edit --body-file`. The three new surfaces are `gh project item-add`, `gh project item-list --limit N`, and `gh api -X PATCH -f body=@file`.

**Implementation:** Memory update (no charter PR needed). Team lead or Wanjiku to apply post-merge.

---

## 6. Acceptance Criteria Reconciliation (vs. meta-issue #300)

| Acceptance bullet | Status |
|------------------|--------|
| All 8 Tier-1 audit PRs merged | MET — #308 (main), #871 (isnad-graph), #100 (user-service), #279 (deploy), #73 (design-system), #45 (data-acquisition), #87 (landing-page); ingest-platform = 0-hooks skip per scope |
| Both Tier-2 fix+fixture PRs merged | MET — #301 (main#285), #305 (main#287) |
| deploy#274 merged | MET — PR #278 |
| Cross-repo audit summary PR (★ Nadia) merged | IN PROGRESS — this PR |
| Audit-discovered parser bugs filed in-wave | MET — ~20 backport issues filed; critical bugs (Pattern G) fixed in-wave via #301, #305 |
| 0 admin overrides | MET — 0 overrides across all 10 PRs |

**All acceptance bullets met or actively closing.**

---

## 7. W8 Carry-Forward Recommendations

The following items should be folded into W8 scope during `/wave-scope`:

### Backport issues filed this wave (~20 total)

Exact issue list is in child-repo issue trackers and `cross-repo-status.json`. Priority-order recommendation:

1. **main — parser fixture gaps** from #308 audit (high priority — these are in the canonical hook repo)
2. **deploy — untracked artifact cleanup** — Weronika-flagged stale working-directory hook artifacts; not a registered-hook risk but creates audit noise
3. **isnad-graph — worktree artifact cleanup** — Arjun-flagged `.claude/worktrees/*/` copies; same category as deploy artifacts

### Charter change proposals (Proposals 1 + 2 above)

Both are P3W8 candidates. Proposal 1 (dispatcher-children sub-clause) is lower scope and should be done early in W8 to prevent auditor confusion. Proposal 2 (Audit Protocol section) is a companion and should ship in the same charter-change PR.

### Node 20 deprecation issues (× 5, filed during wrapup via #309)

Filed in parallel during wave wrapup. Should be labeled for W8 and added to project board.

### 5 child-repo issues filed during wrapup

Same as above — verify they have W8 labels and project board entries.

### Memory update (Proposal 3)

Extend `feedback_gh_pr_edit_silent_noop.md` with the 3 new silent-no-op surfaces. Low-effort; can be done by any team member early in W8 session.

---

*Authored by Nadia Khoury (Program Director) — P3W7 ★ cross-repo audit summary*  
*Refs: meta-issue #300, PRs #301 #305 #308 #871 #100 #278 #279 #73 #45 #87*
