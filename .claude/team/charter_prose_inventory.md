# Charter Prose Inventory — deterministic-able vs intentionally-prose

> **Deliverable of [#734](https://github.com/noorinalabs/noorinalabs-main/issues/734)** (P6 W1, criterion #2 / epic [#726](https://github.com/noorinalabs/noorinalabs-main/issues/726)).
> This is the **analysis/scoping pass**. The sibling issue [#735](https://github.com/noorinalabs/noorinalabs-main/issues/735) does the actual conversion of the `deterministic-able` set; this doc is its ordered worklist.
> Authored by Nadia Khoury, 2026-06-20, against charter HEAD on `deployments/phase-6/wave-1`.

## Method

Every rule in `.claude/team/charter/*.md` (13 sub-docs, ~3,100 lines) was walked and classified into the three buckets the issue specifies:

- **`already-enforced`** — a hook or `.claude/lib/` check already makes this binding. Cite the artifact. (Not a conversion target.)
- **`deterministic-able`** — could be mechanized as a hook/lib gate but currently is **not** (or only partially). These are the worklist for #735, ranked by leverage below.
- **`intentionally-prose`** — judgment, context, rationale, or a structural fact that cannot or should not be mechanized. One-line rationale each.

**Stable identifier** = `<file> § <Section Heading>` (the H2/H3 as it appears at HEAD).

### Leverage of the pre-existing `promotion-target` marker

The charter already annotates most sections with an HTML comment `<!-- promotion-target: hook | skill | none -->`. Census at HEAD: **`hook` ×7, `skill` ×24, `none` ×72**. This is a *partial* classification that long predates #734, and the inventory uses it as a strong prior — but it is **not** the same axis as this issue's taxonomy, for three reasons, so each section was re-judged rather than copied:

1. `promotion-target` records the *aspirational* tier ("this could become a hook"); it does **not** distinguish "target hook not yet built" from "hook already built." Several `promotion-target: hook` sections are in fact **already-enforced** (e.g. `skills.md § Wave Lifecycle — Open-Item Audit` → Hook 17). The marker never gets flipped once the hook lands.
2. `promotion-target: skill` means "mechanize as a *skill*," which under the enforcement hierarchy (hook > skill > charter > memory) is still **code-over-prose** — so for this issue's purpose a `skill` target counts as `deterministic-able` (mechanization form = skill), not as prose.
3. A handful of `promotion-target: none` sections are in fact trivially mechanizable (e.g. `hooks.md § Dispatcher Consolidation Policy` — a count check). Where the marker and the honest classification diverge, the divergence is flagged in the row (**[marker-divergence]**).

### Alignment with `feedback_enforcement_hierarchy.md` (acceptance criterion #5)

The recalled memory states: **hook > skill > charter > memory; a rule with no enforcement decays.** This inventory operationalizes that thesis: the `deterministic-able` ranking is *exactly* "which still-prose rules decay hardest," and the established **promote-on-first-(or-Nth)-violation** trigger is honored — sections the charter has already *decided to DEFER* (zero observed violations, e.g. `skills.md § Cross-repo-status.json upsert`) are ranked low, not high, because per the hierarchy memo charter-only-without-violations does not warrant a hook yet. Leverage = observed recurrence, not theoretical mechanizability.

---

## Summary counts

| Bucket | Count (sections) |
|---|---|
| already-enforced (hook/lib binding exists) | 24 |
| deterministic-able (conversion candidates for #735) | 23 |
| intentionally-prose | 38 |
| **mixed** (partially already-enforced; a deterministic-able remainder is split out into the worklist) | 9 of the above counted in both their enforced part and their remainder |

The 23 `deterministic-able` sections are ranked below; the per-file tables that follow give the full walk with rationale for every section.

---

## RANKED deterministic-able worklist for #735

Ranked by **leverage** = how often the gap has actually bitten (retro recurrence + memory-corpus footprint + severity-if-violated), highest first. The tier boundaries are the natural break points for #735 to size its scope ("do Tier 1, then re-measure").

### Tier 1 — highest leverage (recurred across multiple waves; explicit hook-target; high severity)

| # | Rule (`file § section`) | marker | Mechanization | Leverage evidence |
|---|---|---|---|---|
| 1 | `pull-requests.md § Text-Processing / NER / Graph Fixtures Must Use Production-Realistic Input` | hook | Lint Arabic-text fixtures for absence of vocalization codepoints (`ً–ْ`) and absence of the عن particle in isnad strings → flag toy/schema-assumed fixtures. (The section already names this as the "optional half of #671".) | **Recurred 5+ times** and once *inside its own fix*: da#146/PR#151, da#155, da#175 (thaqalayn 0% matn), MockNeo4j APPEARS_IN-null, double-prefix hadith-id. The single most-recurrent fixture class; directly upstream of the P7 data-quality breakage (`project_prod_loaded_quality_broken`). |
| 2 | `agents.md § Agent Liveness Checkpoint` | hook | (a) Assert a `TaskCreate` exists per spawned implementer; (b) zero-artifact-after-2-idle-notifications auto-flag (count branch/PR/commit artifacts, not messages). | **Recurred two consecutive waves** — P5W2 #1024 (no branch/PR/commit all wave) + P5W3 Nneka #1038 silent-idle. Both needed manual rescue; both near-missed the keystone deliverable. |
| 3 | `agents.md § Throttle-Stall Recovery — Trigger Thresholds` | hook | 30/45/60-min idle cadence for mid-task-with-pending-work stalls → auto-takeover trigger. (Mechanic already in memory `feedback_throttle_takeover`; this is the *trigger*.) | W12 ig#931 stall went **9h37m** undetected. Sibling of #2 (same liveness family). Harder (orchestrator-side timer, no tool-boundary) → ranked just under #2. |
| 4 | `tech-decisions.md § Base Image Pinning` | none **[marker-divergence: trivially mechanizable]** | `validate_dockerfile_base_pin` PreToolUse/CI lint: every `FROM` digest-pinned **and** carries the matching `apk/apt upgrade` (distro table in-section). The section already names this future hook as "step 3." | Surfaced by ig#853 Trivy CVE; cross-repo (all 8 repos build images); recurring reviewer-reminder load. Mechanical/unambiguous. |

### Tier 2 — clear mechanization path; some recurrence or high severity; several are charter-"decided-deferred"

| # | Rule (`file § section`) | marker | Mechanization | Leverage evidence |
|---|---|---|---|---|
| 5 | `pull-requests.md § Retro PR Body-vs-Diff Discipline` | skill | Wire the body-vs-diff check the section already spells out into `/wave-retro` Step 6/8 + `/wave-wrapup` (compare PR-body "Files changed" vs `gh pr view --json files`). | **Severe**-rated; #124/#126 (5 charter/skill edits landed direct-to-main, bypassed 2-reviewer + CI). Skill-tier, low-risk to wire. |
| 6 | `pull-requests.md § CI Workflow pull_request Triggers Must Cover Wave Branches` | none **[divergence]** | `validate_ci_trigger_branches` (the section names it): block a workflow PR whose `pull_request.branches` is a single-branch list omitting `deployments/**`. Sibling of live Hook 19. | P2W10 ×2 independent (user-service#81, deploy#152/#154); silent-CI-skip class. |
| 7 | `pull-requests.md § Additive Commits on ChangesRequested (Mandatory)` | none **[divergence]** | Detect `git push --force`/`--force-with-lease` on a branch with an open ChangesRequested verdict → block (extends `block_no_verify` family). | Moderate severity; HEAD-SHA anchor is load-bearing for reviewer re-verify chain. Needs ChangesRequested-state lookup (medium effort). |
| 8 | `agents.md § Spawn Isolation Default` | none **[divergence]** | PreToolUse `Agent` hook: implementer-class spawn must set `isolation: "worktree"` (coordinator/fork carve-outs per section). | P3W6: 18 implementer spawns mis-rendered as background tasks (#290). Tool-boundary check (clean). |
| 9 | `artifact-ownership.md § Create-time ownership gate` | none | The section's own "step 2" deferred hook: block Edit/Write that creates a parent-canonical artifact class (shared hook, org skill, org charter) under a *child* repo tree, or a child-shadowing org-skill name. | #328 family; reviewer-enforced today (drift filed as #560). Clear class boundary. |
| 10 | `hooks.md § Dispatcher Consolidation Policy` | none **[divergence]** | Count hooks per matcher in the dispatcher/settings; fail PR that adds a 4th without a dispatcher. | Cheap/unambiguous; low recurrence (consolidation discipline mostly held). |
| 11 | `skills.md § Zsh-safe repo iteration in wave skills` | hook (**DEFER decided**) | `validate_skill_bash_no_param_for_loop` grep-gate over skill `*.md` bash fences for `for \w+ in \$[A-Z_]`. Lib (`wave_status.py`) already removed the live instances. | Bit 3× in one P5W4 wrapup (#688) — but charter has **already decided DEFER** (0 current violations post-lib). Promote on first recurrence. |
| 12 | `pull-requests.md § All Deliberately-Assigned Reviewers Must Approve (Blast-Radius PRs)` | none | Merge gate keyed on the *assigned* reviewer slate count (3+), not just the 2-distinct-Approved minimum. Section itself: "a future enhancement could key the merge gate on assigned-reviewer count." | P4W4 ig#1002 merged 2/3 (lucky). Needs durable slate tracking (harder) → mid-tier. |
| 13 | `hooks.md § Hook Authorship Requirements §5a` (segment-parser 6-class test matrix) | none | The "out-of-scope follow-up" grep CI gate asserting all six `# segment-class:` convention names present. | #537/#538 newline-gap shipped because coverage was partial. §7's analogue **is already a gate** (see already-enforced) — precedent exists. |

### Tier 3 — mechanizable but low value / low recurrence (do only if Tiers 1–2 leave budget)

| # | Rule (`file § section`) | marker | Mechanization / note |
|---|---|---|---|
| 14 | `skills.md § Cross-repo-status.json upsert pattern` | hook (**DEFER decided**) | Lib (`upsert_status_keys.py`) already exists + consumers use it; section explicitly DEFERs the format-guard hook (0 violations W6–W9). Lowest-priority hook. |
| 15 | `pull-requests.md § Pre-Push Checklist` (branch-name sub-item) | none | Lint/test parity already enforced by pre-commit/pre-push; only the `git branch --show-current` format-match is unmechanized. Minor. |
| 16 | `agents.md § Agent Naming with Repo Prefix` + `§ Agent Naming Convention` (pattern only) | none | PreToolUse `Agent` name-format check (`{repo}-{firstname}`). Role-fit half stays prose. Low. |
| 17 | `brand.md` (whole) | (none) | cspell/grep lint: flag `NoorinALabs`/`noorina-labs` in user-facing text (allow code identifier `noorinalabs`). Low recurrence; fits the #684 cspell rollout. |
| 18 | `pull-requests.md § PR Template` + `§ Review Prompt Template` (structure) | none | Validate PR body carries Summary/Related Issues/Review Checklist. Output format already gated by `validate_pr_review`; template-presence is low value. |
| 19 | `issues.md § Manual Issues` (`[MANUAL]` prefix) | none | Trivial prefix lint. Very low. |
| 20 | `pull-requests.md § gh pr edit projects-classic deprecation` | none | Warn-on `gh pr edit --body` (silent-no-op family); read-back already advised. Low. |
| 21 | `agents.md § Worktree Lock Management` (20-min stale-lock timeout) | (none) | Skill-side cleanup mechanization (`/wave-wrapup`). Low. |
| 22 | `agents.md § Auto-Trigger` (`/wave-wrapup` on all-PRs-merged) | (none) | Event-driven trigger; partially covered by `validate_wave_audit`/wrap discipline. Low. |
| 23 | `pull-requests.md § Load-Bearing Followups for Disabled CI Jobs` | skill | Reviewer/skill check that a CI-disabling PR carries the `## Disabled CI jobs` breadcrumb + load-bearing followup issue. Judgment-adjacent; low. |

> **Partially-enforced remainders also feeding #735 (tracked elsewhere, listed for completeness, not re-ranked):**
> - `pull-requests.md § Full Local⇄CI Tooling Parity` — the sync-drift gate exists but is blind to unclassified kinds (cspell); closing that is **already in flight as #684 / task** (do not double-scope).
> - `agents.md § Child-Repo Implementer Rule` — commit-time roster is already Hook-5-enforced; only the *pre-spawn-brief* gate (marker:hook) is the remainder (lower value — Hook 5 already catches it downstream).
> - `issues.md § Issue-Filing Premise Verification at Origin HEAD` — partially covered by Hook 20 at wave-label-time; a general issue-create premise gate is hard (judgment) and stays mostly prose.

---

## Full per-file walk

Legend: **AE** = already-enforced · **DA** = deterministic-able (→ worklist # above) · **IP** = intentionally-prose.

### `hooks.md`

| Section | Class | Rationale / citation |
|---|---|---|
| Hooks 1–21 (each `## Hook N: …`) | **AE** | These *are* the enforcement layer — each entry documents its live `.py` (validate_commit_identity, block_no_verify, block_git_config, auto_set_env_test, validate_labels, validate_lockfile_paths, validate_pr_review, block_gh_pr_review, validate_branch_freshness, validate_vps_host, warn_ghcr_image, validate_wave_context, auto_add_issue_to_board, validate_pr_ci_status, enforce_librarian_consulted, no_worktree_self_delete, validate_wave_audit, validate_edit_completion, validate_workflow_paths_coverage, validate_wave_label_evidence, post_label_change_wave_field_sync). |
| § Bash Hook Dispatcher Architecture | **IP** | Architecture reference; the dispatcher *is* the implementation, the prose just documents it. |
| § Dispatcher Consolidation Policy | **DA #10** | >3-per-matcher count is trivially mechanizable; marker says `none` but it is a count check. |
| § Hook 13/14 inline notes, NEUTRAL allowlist, etc. | **AE** | Behavior of live hooks. |
| § Shared Helpers (`_shell_parse`, `_wave_label_parse`, `_consultation_sentinel`) | **IP** | Reference docs for existing lib primitives; not a rule to gate. |
| § Hook Sync Across Child Repos | **IP** (remainder → see artifact-ownership #9) | Mostly reviewer-verified config convention; the mechanizable part is the create-time gate, owned by `artifact-ownership.md § Create-time gate`. |
| § Hook Authorship Requirements §1 Input-language / §2 charter entry / §3 negative-match tests / §4 dispatcher reg / §6 provenance phrasing | **IP** | Authoring discipline checked at PR review by Standards lead; §6's phrasing is *consumed* by `/promotion-audit` parser (that side is AE) but authoring it is prose. |
| § Hook Authorship Requirements §5 fixture-with-fix | **IP** (deferred CI gate is low-value) | Discipline; the "CI flags PRs that change parser logic without a fixture" is a deferred follow-up, lower leverage than §5a. |
| § Hook Authorship Requirements §5a six-class segment-parser matrix | **DA #13** | Explicit out-of-scope grep gate on the six `# segment-class:` names. |
| § Hook Authorship Requirements §7 gh-command parser invariant | **AE** | Machine-enforced by `.claude/hooks/tests/test_gh_command_parser_invariant.py` (in the pytest suite CI mirrors). |
| § Hook Audit Protocol | **IP** | Method discipline (committed-tree vs filesystem); a procedure, not a gate. |

### `agents.md`

| Section | Class | Rationale |
|---|---|---|
| § Agent Naming Convention | **IP** (pattern sub-part → #16) | Role-fit mapping is judgment; only the name *pattern* is mechanizable. |
| § How to Instantiate the Team | **IP** | Session-bootstrap procedure (partially `/session-start`); prose. |
| § Agent Lifecycle Management + § Wave Retrospective (Required) | **IP** | Procedure realized by wave-lifecycle skills; the *discipline* (don't skip retro) is judgment. |
| § Per-Repo Worktree Isolation (Child Repos) | **IP** | Spawn-brief procedural guidance; child-repo cross-contamination is mitigated by brief content, not a gate. |
| § Scaffold Migration Chain Strategy | **IP** | Context-specific judgment (alembic chain base). |
| § Worktree Lock Management | **DA #21** (stale-lock timeout) | The 20-min timeout cleanup is mechanizable (skill-side); rest is procedure. |
| § Auto-Trigger | **DA #22** | Event-driven `/wave-wrapup` trigger; low. |
| § Team Teardown Procedure | **IP** | Shutdown procedure; harness-dependent. |
| § Orchestrator Spawn Discipline — Reuse Idle Teammates | **IP** | Reuse-vs-clone is judgment. |
| § Hub-and-Spoke Orchestration Model | **AE** (by harness) / **IP** | Enforced structurally — spawned agents lack the Agent tool; not a hook but not convertible either. |
| § Spawn Request Delegation / § No Direct-to-Engineer Spawns | **IP** | Orchestrator judgment/hierarchy discipline. |
| § Spawn Isolation Default | **DA #8** | PreToolUse `Agent` `isolation` check. |
| § Agent Naming with Repo Prefix | **DA #16** | Name-format check on Agent tool. |
| § Team Names | **IP** | Reference table. |
| § Single-Leader Constraint | **AE** (by harness) / **IP** | One implicit team is a harness fact, not a charter-enforceable gate. |
| § Reviewer slate discipline (FIRST-LINE) | **IP** (sub-parts mechanizable) | Manager-of-repo and PR-author exclusions are partly mechanizable, but "valid reviewer source" is judgment; spawn briefs aren't tool-gated. |
| § Reviewer spawn brief — throughline-watch | **IP** | Template-inclusion in a non-gated surface (spawn brief). |
| § Orchestrator checklist when spawning an implementer | **AE** (items 2,3,10) / **IP** | Item 2 → `enforce_ontology_context`, item 3 → Hook 15, item 10 → green-before-push (#684); rest is composition discipline. |
| § Orchestrator checklist when spawning a reviewer | **AE** (verdict format) / **IP** | Verdict literal-form is gated by `validate_pr_review` + `validate_review_comment_format`; brief-composition is prose. |
| § Pre-Spawn State Check + Crossed-Message Race | **IP** | Message-bus race protocol; accept-as-cost-of-throughput is judgment. |
| § Surface enumeration (+ where/how/caveats sub-secs) | **IP** | Pre-spawn counting discipline; judgment. |
| § Orchestrator State-Correction Discipline | **IP** | Anti-serial-toggle judgment. |
| § Child-Repo Implementer Rule + Spawn-Brief Verification | **AE** (Hook 5, commit-time) / remainder IP | `validate_commit_identity` blocks wrong-roster at first commit; the pre-spawn-brief gate (marker:hook) is a low-value remainder since Hook 5 catches it downstream. |
| § Parent-Orchestrator Implementer Declarations Are Advisory | **IP** | Authority-source judgment. |
| § Agent Liveness Checkpoint | **DA #2** | marker:hook; recurred P5W2/W3. |
| § Throttle-Stall Recovery — Trigger Thresholds | **DA #3** | marker:hook; W12 9h stall. |

### `pull-requests.md`

| Section | Class | Rationale |
|---|---|---|
| § Comment-Based Reviews (Mandatory) | **AE** | `validate_pr_review` + `validate_review_comment_format` + `block_gh_pr_review`. |
| § Review Prompt Template (Mandatory) | **IP** (output AE) | Template is guidance; the *resulting* format is hook-gated. |
| § Two-Reviewer Assignment at Wave Kickoff | **AE** (count) / **IP** (planning) | 2-distinct-Approved gated by `validate_pr_review`; "assign at kickoff" is planning prose. |
| § All Deliberately-Assigned Reviewers Must Approve (Blast-Radius) | **DA #12** | assigned-slate merge gate (section invites the enhancement). |
| § Single-Reviewer Exception (Wave-Bootstrap Only) | **AE** | `validate_pr_review` honors the `wave-bootstrap` waiver (main#228). |
| § Load-Bearing Followups for Disabled CI Jobs | **DA #23** | breadcrumb/followup check; judgment-adjacent. |
| § PR Review Workflow for Deployments Branch PRs | **AE** (2-review) / **IP** | gate via `validate_pr_review`; rest procedural. |
| § Additive Commits on ChangesRequested (Mandatory) | **DA #7** | force-push-during-CR detection. |
| § Review Finding Disposition | **AE** (TechDebt line) / **IP** | `validate_pr_review` requires `TechDebt:`; the must-fix/tech-debt triage is judgment. |
| § Post-Merge Integration Verification | **IP** (CI-on-push AE) | manager manual check is judgment; the `deployments/**` push-CI part is config-enforced. |
| § CI Workflow pull_request Triggers Must Cover Wave Branches | **DA #6** | `validate_ci_trigger_branches`; sibling of live Hook 19. |
| § Cross-Contract PRs | **IP** | "is this a cross-contract PR" is judgment. |
| § Cross-PR Dependency Sequencing | **IP** | dependency-order judgment. |
| § Wave Merge PR Verification | **AE/IP** | `/wave-wrapup` skill + `validate_pr_ci_status` + admin-merge gate realize most of it. |
| § Wave-Wrapup Staging-Promotion Gate (Mandatory) | **AE** | `/wave-wrapup` Step 11.6 (skill-tier gate). |
| § End-State Criterion Verification Requires Live-Environment Evidence | **IP** | live-env evidence judgment. |
| § PR Template | **DA #18** | body-section presence check (low). |
| § Closes-vs-Refs Disposition — Decided at Brief Time | **IP** | disposition judgment. |
| § Pre-Push Checklist | **AE** (lint/type/test) / **DA #15** (branch-name) | pre-commit/pre-push hooks run the checks; branch-name match unmechanized. |
| § CI Must Be Green Before Merge | **AE** | `validate_pr_ci_status` (Hook 14). |
| § Full Local⇄CI Tooling Parity + No Force-Merging | **AE** (sync-drift gate + block_no_verify) / remainder = **#684** | gate exists but blind to cspell; closing it is the in-flight #684, not new #735 scope. |
| § Org-Wide Branch Protection + Admin-Merge Exceptions | **AE** | `validate_pr_ci_status` admin-merge gate + GH rulesets (rollout tracked by #322). |
| § CI Enforcement After PR Creation | **AE/IP** | Hook 14 + procedure. |
| § Design-Rationale Block for Critical-Path PRs | **IP** | "is this critical-path" + block quality is judgment. |
| § Trust the Artifact, Not the Framing | **IP** (head-SHA confirm = minor mechanizable) | core discipline (read artifact not framing) is behavioral. |
| § Trivial Cross-Repo Doc Sweep | **AE** (exception class) / **IP** | `doc-sweep` is a recognized admin-merge exception class in the hook; "is it byte-identical" is judgment. |
| § Security Guards Belong Inline, Not in a Followup | **IP** | threat-model judgment. |
| § Live-Trace Evidence > Synthetic-Test Acceptance | **IP** | evidence-quality judgment. |
| § Text-Processing / NER / Graph Fixtures Production-Realistic Input | **DA #1** | marker:hook; the highest-recurrence class. |
| § PR-Time Acceptance vs Runtime Acceptance | **IP** | lifecycle-separation judgment. |
| § Sandbox Test-Verification Pattern | **IP** | environmental judgment. |
| § Close Runtime-Gated Issues on Verified-Live | **IP** | Refs-vs-Closes judgment for runtime gates. |
| § Origin > Local Clone for "Still-Has-X" Claims | **AE** (Hook 20, label-time) / **IP** | `validate_wave_label_evidence` covers the wave-label surface; reviewer-claim discipline otherwise is behavioral. |
| § Retro PR Body-vs-Diff Discipline | **DA #5** | skill-enforcement snippet already written; wire into `/wave-retro`. |
| § gh pr edit projects-classic deprecation | **DA #20** | warn-on-`gh pr edit --body`; low. |

### `issues.md`

| Section | Class | Rationale |
|---|---|---|
| § Delegation Flow | **IP** | decomposition/delegation procedure. |
| § Issue Review Process | **IP** | "speak up only if meaningful" is judgment. |
| § Work Gate: Issues Before Implementation | **IP** | planning judgment. |
| § Issue-Filing Premise Verification at Origin HEAD | **IP** (partial AE via Hook 20) | general premise verification is judgment; wave-label path-existence is Hook-20-gated. |
| § Wave Planning — Project Board Is Authoritative | **AE** | `/board-audit` skill (+ Hook 13 / Hook 21 board sync). |
| § Multi-Step Meta-Issue Freshness Re-Audit | **IP** | 48h re-audit is procedural judgment (skill could host but the trigger is judgment). |
| § Pre-Wave Checklist | **AE/IP** | `/wave-kickoff` realizes most; roster validation overlaps Hook 1. |
| § Implementation Kickoff & Issue Assignment (Assignment / Reassignment / Manual / Hygiene) | **IP** (Manual prefix → #19) | assignment/hygiene judgment; only `[MANUAL]` prefix is a trivial lint. |
| § End-State Criterion: Delivered vs Applied-and-Verified-at-Origin | **IP** | applied-vs-delivered judgment. |
| § Comment Format | **IP** | issue-comment format is not a gated surface (unlike PR verdicts); low value to mechanize. |
| § Reply Protocol | **IP** | swap/notify procedure. |
| § Ticket Update Rules Based on Ownership | **IP** | ownership-driven judgment. |
| § Escalation & Cross-Team Clarification | **IP** | escalation procedure. |

### `skills.md`

| Section | Class | Rationale |
|---|---|---|
| § Wave Lifecycle — Open-Item Audit | **AE** | marker:hook but **already done** — Hook 17 `validate_wave_audit` (line-5 marker confirms). Marker stale. |
| § Cross-repo-status.json upsert pattern | **AE** (lib) / **DA #14** | `.claude/lib/upsert_status_keys.py` exists + consumers use it; the format-guard hook is charter-**DEFERed** (0 violations). |
| § Codify Determinism on Tooling Fragility | **IP** | this is the meta-thesis itself (the principle behind #726). |
| § Zsh-safe repo iteration in wave skills | **AE** (lib) / **DA #11** | `wave_status.py` removed live instances; grep gate DEFERed pending recurrence. |
| § Promotion Pipeline Marker Convention | **AE** (parser) / **IP** | `/promotion-audit` parsers recognize the two shapes; "forbidden shapes" is reviewer-rejected (a lint is possible but low value). |
| § Process-Doc Authorship: Derived-From-SKILL.md-At-HEAD | **IP** | author-from-artifact discipline; behavioral. |
| § Acceptance-Criteria-Bucketing-In-Reports | **IP** | summary-bucketing is authoring judgment. |

### `state-claims.md`

| Section | Class | Rationale |
|---|---|---|
| § Refresh State Before Claim (+ all sub-rules: pre-write checklist, Manager-not-exempt, PR-state/Issue-state field sets, merge_commit_sha reachability, Ledger reconciliation) | **IP** | The section's own "Aspiration" note says the structural SendMessage-boundary hook "remains proposed"; verify-before-claim is fundamentally behavioral. The field-set sub-rules are *recipes*, not gates. |
| § Refresh State Before Acting | **IP** | action-class refresh discipline; behavioral. |
| § Canonical Source via `git show <sha>:<path>` | **IP** | "use the canonical sha not the worktree" is behavioral judgment. |

### Small files

| Section | Class | Rationale |
|---|---|---|
| `branching.md` § Deployments / Feature Branches / Worktree Cleanup | **IP** (branch-name format → overlaps #15) | branch naming partly mechanizable (overlaps Pre-Push branch-name); freshness already Hook-9-gated; cleanup is procedure. |
| `commits.md` (whole) | **AE** | Hook 1 `validate_commit_identity` + Hook 3 `block_git_config`. |
| `communication.md` (whole) | **IP** | cross-repo messaging protocol / shared-state conventions; reference. |
| `brand.md` (whole) | **DA #17** | "Noorina Labs" vs `noorinalabs` is a grep/cspell lint. |
| `artifact-ownership.md` (matrix + collision rules + audit) | **IP** | reference matrix + audit; the one rule is the create-time gate ↓. |
| `artifact-ownership.md § Create-time ownership gate` | **DA #9** | section's own "step 2" deferred PreToolUse gate. |
| `emergency-mode.md` (whole) | **IP** (emergency admin-merge class AE) | trigger conditions are judgment; `emergency` is a recognized admin-merge exception class in `validate_pr_ci_status`; `[EMERGENCY]` prefix is a trivial-but-low lint. |
| `tech-decisions.md § Individual Preferences / Debate / Tie-Breaking (LCA) | **IP** | decision-making process; judgment. |
| `tech-decisions.md § Base Image Pinning` | **DA #4** | `validate_dockerfile_base_pin` (named in-section). |
| `tech-decisions.md § Per-Env OAuth Provisioning` | **IP** | provisioning convention; config/judgment. |

---

## Already-enforced index (citation map — NOT conversion targets)

| Charter rule | Enforced by |
|---|---|
| Commit identity / no git-config | Hook 1 `validate_commit_identity`, Hook 3 `block_git_config` |
| No `--no-verify` | Hook 2 `block_no_verify` |
| `ENVIRONMENT=test` before pytest | Hook 4 `auto_set_env_test` |
| Label hygiene on `gh issue create` | Hook 5 `validate_labels` |
| Lockfile `/tmp/` paths | Hook 6 `validate_lockfile_paths` |
| 2-reviewer / verdict format / no self-approve | Hook 7 `validate_pr_review`, Hook 8 `block_gh_pr_review`, `validate_review_comment_format` |
| Branch freshness before PR | Hook 9 `validate_branch_freshness` |
| Deploy safety (VPS_HOST / GHCR) | Hook 10 `validate_vps_host`, Hook 11 `warn_ghcr_image` |
| Wave context before spawn | Hook 12 `validate_wave_context` |
| Issue → board (create + label-edit) | Hook 13 `auto_add_issue_to_board`, Hook 21 `post_label_change_wave_field_sync` |
| CI green / admin-merge exceptions before merge | Hook 14 `validate_pr_ci_status` |
| Librarian consulted before Edit/Write | Hook 15 `enforce_librarian_consulted` |
| Worktree self-delete | Hook 16 `no_worktree_self_delete` |
| Wave open-item audit before "concluded" | Hook 17 `validate_wave_audit` (= `skills.md § Wave Lifecycle`) |
| Edit-error soft-accept | Hook 18 `validate_edit_completion` |
| Workflow-file orphan coverage | Hook 19 `validate_workflow_paths_coverage` |
| Stale-path wave labeling | Hook 20 `validate_wave_label_evidence` |
| Ontology context baked into spawn | `enforce_ontology_context` |
| gh-command parser invariant | `test_gh_command_parser_invariant.py` |
| Wave-counter / status-file writes | `.claude/lib/wave_status.py`, `.claude/lib/upsert_status_keys.py` |
| Local⇄CI parity (partial) | `.claude/lib/pre_commit_ci_sync.py` sync-drift gate (cspell blind-spot → #684) |
| Board orphan/Wave-field sync | `/board-audit` skill |
| Staging-promotion wave gate | `/wave-wrapup` Step 11.6 |
| Branch protection (server-side) | GH rulesets (rollout tracked by #322) |

---

## Caveats for #735

1. **Re-verify every "DA" at conversion time.** Several rows are charter-**DEFERed** by an explicit hierarchy decision (zero violations) — #11, #14. Per `feedback_enforcement_hierarchy`, do **not** build those on spec; build them on the first/next recorded violation. They are listed so #735 knows they exist, not so it builds all 23.
2. **Flip stale markers as you go.** `skills.md § Wave Lifecycle` is `promotion-target: hook` but Hook 17 already exists; any conversion PR touching these should correct the marker (or the conversion work should add a "marker reflects built-state" pass).
3. **Don't double-scope #684.** The Full-Local⇄CI-parity cspell-classification remainder is already an in-flight wave issue; #735 should reference, not re-open it.
4. **Tool-boundary > orchestrator-timer.** Tiers were set partly by mechanizability: tool-boundary checks (#1 fixture lint, #8 Agent-isolation) are clean PreToolUse hooks; orchestrator-side timers (#3 throttle cadence) have no clean tool boundary and are harder — reflected in their rank.
