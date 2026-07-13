# Feedback Log — Phase 7 archive

> Archived byte-for-byte from `.claude/team/feedback_log.md`
> at phase close (#964, meta #960), preserving original file order. Do not edit —
> append-only history; new entries go to the live file for the current phase.

---

## Retrospective: Phase 7 Wave 18 — 2026-06-25

### Team Performance
**11 per-issue PRs merged across all 7 in-scope repos** (5 noorinalabs-main + 6 child-repo C×T2 structural-index wirings), **12 active members** (11 authors + Bereket reviewing), top-concentration **9%** (1/11 — textbook distributed fan-out). **0 CR cycles, 0 CI-red merges, 0 genuine must-fix, 0 rework.** Theme: C×T2 structural-ontology framework rollout (carry-forward lead-in). Counters verified mechanically (11 authored PRs == final_pr_count; max-by-author 1/11 == 9%).

### Per-Engineer Assessments (mechanical — trust_signals.py score 7 18)
- **All 11 authors** — one clean on-theme PR each (#873 Weronika / #874 Santiago / #875 Aino / #876 Nino / #877 Nurul / us#195 Mateo / dep#494 Aisha / ds#131 Astrid / lp#156 Kofi / da#215 Kavitha / ig#117 Yusuke); 0 must-fix received, 0 CI-red. Baseline — held. No standout relative performer in a perfectly-flat wave → no distribution ratchet.
- **Bereket Tadesse** — substantive approving review on #873 (no authored PR this wave); baseline, held.
- **Aino Virtanen** — #875 + thorough review on #873; at ceiling (5), held.

**Spurious mechanical signal REJECTED (the wave's key finding):** `trust_signals.py score` proposed −1 for **Aino** and **Bereket** ("1 review false-positive" each). Verified spurious: on **PR #873** both posted `RequestOrReplied: Approved`, and their bodies contain "false-positive" only because they were *praising the PR's `test_no_false_positive_type_in_non_decl_context` coverage*. `_FALSE_POSITIVE_RE` substring-matches the phrase in approving prose and ignores the Approved verdict. **This recurs** — the W17 matrix shows the identical misfire (Aino + Nino). Both −1 deltas rejected with evidence; held flat. Filed as **#881** (fix in flight this retro).

### Top 3 Going Well
1. **Perfect distribution.** 11 PRs, one per engineer, 9% concentration — genuine fan-out across all 7 repos, not orchestrator-solo. The W17 "carry distributed work forward" caveat met again.
2. **Zero rework.** 0 CR cycles, 0 CI-red merges, 0 genuine must-fix — clean carry-forward execution of the C×T2 rollout.
3. **Honest audit caught its own drift.** The retro's evidence discipline rejected a spurious mechanical trust signal (the Step-2.5 "don't narrate a wrong counter as authoritative" principle, applied to trust signals) rather than mechanically applying two wrong −1 deltas.

### Top 3 Pain Points
1. **`trust_signals.py` review-false-positive over-count (#881).** Recurring across W17→W18. `_FALSE_POSITIVE_RE` substring-matches "false-positive"/"withdrawn"/"retracted" anywhere in a verdict body and ignores the `RequestOrReplied:` verdict, so approving prose that merely *mentions* the concept scores a −1. Especially misfires on FP-suppression-themed waves. **The headline finding.**
2. **`validate_pr_review` over-broad block.** Annunaki logged it firing on a non-merge `gh run rerun` command during wrapup (no `gh pr merge` present). Candidate for matcher tightening, or confirm acceptable conservatism per [[feedback_safety_direction_over_ux_friction]].
3. **Post-wrapup overlay re-dirtying.** 2 memory files edited after wrapup Step 12a left the semantic overlay dirty; resolved manually at retro. Minor inherent seam when session work continues past wrapup.

### Proposed Process Changes
1. **Fix #881** — scope the FP detector to actual self-withdrawals (gate on verdict != Approved; strip code-spans/identifiers like `test_no_false_positive_*`); add regression tests from the real #873 Aino+Bereket bodies. Rationale: eliminates a recurring spurious trust delta that has now distorted two consecutive matrices.
2. **Evaluate `validate_pr_review` matcher scope** — Rationale: it blocked a non-merge `gh run rerun`; either narrow to `gh pr merge` invocations or document the conservatism. Low-priority; the gate is fail-safe.

### Annunaki-attack
2 captures in-window (both `pretooluse_block`, **0 genuine command failures**): 1 legitimate `validate_branch_freshness` block (handled by rebase), 1 over-broad `validate_pr_review` match on `gh run rerun` (→ pain point #2). No new hooks/issues warranted beyond #881. Marker `wave_18_annunaki_attack_ran_at` written.

### Memory-to-automation audit
1 promotion realized this session: the zsh unquoted-scalar word-split footgun was codified memory→hook (`warn_zsh_wordsplit.py`, main#879/PR#880, advisory PreToolUse), per [[feedback_enforcement_hierarchy]] and recorded in [[feedback_zsh_shell_environment]]. No other memory crossed a promotion threshold in a clean carry-forward wave. Marker `wave_18_memory_audit_ran_at` written.

### Next-wave scope
W19 stub auto-drafted + boarded (**#882**), `wave_19_meta_issue` recorded; carry-forward pre-loaded (#881, #873 generics-splitter, validate_pr_review matcher). Theme TBD — owner to set, then `/wave-scope 7 19` proceeds.

## Retrospective: Phase 7 Wave 19 — 2026-06-25 (framework tooling carry-forward + prod-data quality)

### Team Performance
**9 PRs merged** (6 noorinalabs-main · 2 data-acquisition · 1 isnad-graph), 7 engineers, **0 changes-requested cycles**, 0 CI-red merges, top-concentration 33% (Aino, 3/9 — below the 60% threshold). All per-issue PRs green at merge. Post-merge gates all passed: reachability `all-reachable`, staging promotion `success`, deployable-verify `verified`. 0 new tech-debt issues. Ontology 2 dirty (this session's retro/ledger churn — minor). Plus the **155-candidate generic-prompt backlog cleared** (76 genericized → `2real-team-framework`, 79 skipped, pending now 0).

### Per-Engineer Assessments
Mechanical (`trust_signals.py score 7 19`). All clean (0 must-fix received/caught, 0 CI-red, 0 false-positives). Helper proposed Aino +1 (3-PR delivery); **owner held all flat** (clean-but-unremarkable, no reviewing-catch ratchet).
- **Aino Virtanen** — #896 (Hook-4 subshell/compound guard, #894), #895 (lint wiring, #893), #890 (wave_seq reservation-aware, #885). prs_merged=3.
- **Lucas Ferreira** — #891 (narrow validate_pr_review batch-loop guard, #886).
- **Nurul Hakim** — #892 (board-audit GraphQL pagination + resilient loop, #888).
- **Weronika Zielinska** — #889 (ontology_gen depth-aware TS extends splitter, #887).
- **Alejandra Reyes-Fuentes** — da#218 (ADR-003 sanadset orphan / narrator-pollution investigation A/B, da#202).
- **Kavitha Sundaramurthy** — da#217 (honor explicit None as load-all, da#196).
- **Nneka Obi** — ig#1133 (prod full-text starvation + semantic 500 repair, ig#1110).

### Top 3 Going Well
1. **Clean delivery** — 9/9 per-issue PRs merged green, 0 changes-requested cycles, healthy 33% concentration across 7 engineers.
2. **Generic-prompt framework matured** — 155-candidate backlog cleared; 76 reusable product-neutral prompts seed `2real-team-framework`; tracker SKIP_PREFIXES fix closes the noise inflow at source.
3. **All post-merge gates green** — reachability/staging/deployable-verify all passed; prod-data fixes (search 500s, sanadset orphans, parser None-handling) landed.

### Top 3 Pain Points
1. **Wave→main integration PRs went red twice and needed fix-forward** — #898 (squash collapsed persona authorship → commit-author gate) and da#222 (child structural index not regenerated for a new `.cypher`). Captured in memory mid-wave, but the *process* let them reach the integration PR.
2. **Squash-vs-merge footgun was latent** — only memory protected against it; nothing mechanical stopped a `--squash` into a wave branch.
3. **Generic-prompt agents' idle-heartbeat glitch** ([[feedback_self_loop_task_replay_glitch]]) — agents produced correct files but couldn't reliably return structured JSON; verdicts had to be reconstructed deterministically from disk. No data loss, some orchestration cost.

### Proposed Process Changes (owner-decided 2026-06-25)
1. **Hook 22 (`block_squash_wave_merge.py`)** — PreToolUse hard-block on `gh pr merge <N> --squash` into a `deployments/phase-*/wave-*` base (squash-into-main untouched; network base-resolution fails open). Closes pain-point #1/#2. Owner: "build the hook this retro." Codifies [[feedback_wave_branch_merge_not_squash]] + charter `pull-requests.md § One Merge Model Per Wave`.
2. **`/wave-wrapup` Step 10.7 (child structural pre-regen)** — regenerate each child's structural index before opening the wave→main PR, so the staleness-check is green from the start (closes the da#222 class). Owner: "propose as charter/skill change."

### Annunaki-attack
7 records in the wave window — **all benign hook-fires from the orchestrator's own wave→main recovery** (batch-loop merge guard, stale-tmp block during re-auth, identity-hook on cherry-pick replay, wave-field sync on relocation). Hooks working as designed; **0 actionable**. Marker `wave_19_annunaki_attack_ran_at` written.

### Promotion audit
0 AUTO · 0 DECIDE · 214 KEPT · 22 SUPERSEDED — nothing crossed a threshold mechanically. Standalone log: `promotion_audit_log/p7-wave-19.md`.

### Memory-to-automation audit
1 promotion realized this retro: [[feedback_wave_branch_merge_not_squash]] → **Hook 22** (`--merge`-not-`--squash` rule) + **`/wave-wrapup` Step 10.7** (child structural staleness gotcha). Both halves now codified; the memory carries a promotion provenance note. No other memory crossed a threshold. Marker `wave_19_memory_audit_ran_at` written.

### Next-wave scope
W20 stub auto-drafted + boarded, `wave_20_meta_issue` recorded; carry-forward pre-loaded. Theme TBD — owner to set, then `/wave-scope 7 20` proceeds.

## Retrospective: Phase 7 Wave 20 — 2026-06-26

**Theme:** Graph integrity + dedup + chains (Phase 7 ordinal 3, global wave id 20). Turn the prod data-quality findings (umbrella main#723) into fixes — Path B sanadset orphan resolution, cross-edition dedup, narrator re-segmentation, chain validation. Serves Phase-7 end-state criteria 1, 2, 4.

### Team Performance
6 per-issue PRs merged green to `deployments/phase-7/wave-20`, **0 changes-requested cycles**, 0 CI-red merges, 0 must-fix items wave-wide. 6 issues closed (da#219/220/221/153/202, ig#1040). Both wave→main integration PRs (da#231, ig#1136) merged clean with `--merge`; main no-op (meta-only). Wave branches retained. All post-merge gates green (reachability, deployable-merge, staging deploy-stg success, ig ghcr-publish). Counters verified at retro against PR evidence — no drift (6 / 0 / 33%).

### Per-Engineer Assessments (mechanical — `trust_signals.py score 7 20`)
- **Alejandra Reyes-Fuentes** (da) — da#224 (B1) + da#227 (parent verify), prs_merged=2 (wave top). Clean. Helper +1 absorbed at ceiling 5.
- **Kavitha Sundaramurthy** (da) — da#225 (B2 dedup). Clean. Hold 5.
- **Ivana Horvat** (da) — da#226 (B3 re-segmentation). Clean. Hold 5.
- **Nikolaos Papadopoulos** (da) — da#223 (da#153 integrity sweep). Clean. Hold 5.
- **Jun-Seo Park** (ig) — ig#1135 (GET /validate/chains). Clean. Hold 4.
- Reviewers (Kavitha, Nikolaos, Ivana, Mateo Salazar, Aisling Brennan, Oyunbileg Batbayar, Kwesi Boateng, Jean-Claude Habimana): 2 first-pass approvals/PR, 0 CR cycles → no reviewing ratchet (0 must-fixes existed to catch).

### Top 3 Going Well
1. **W19's process fixes proved out** — Hook 22 + Step 10.7 meant **zero** wave→main fix-forward scrambles (vs two in W19). The exact pain points that drove last wave's codification did not recur — the codification worked.
2. **Path B sequenced cleanly** — B1 (da#219, collections foundation) → B2 (da#220, dedup) → B3 (da#221, re-segmentation) parallel; da#202 parent integration-verify last as the orphan-resolution acceptance gate. No dependency stalls.
3. **Third consecutive clean wave** (W18/W19/W20) — 0 CR cycles, healthy 33% concentration, all gates green. Steady-state execution.

### Top 3 Pain Points
1. **Kickoff PostToolUse hook-parser brittleness** — `post_wave_kickoff_comment` + `post_label_change_wave_field_sync` both returned `skip_parser_returned_empty` on the `cd "$(...)"`-prefixed / newline-prefixed wave-label command, so no kickoff comment auto-posted and no Wave-field auto-synced. Worked around with bare commands mid-kickoff; filed as **#901** (parser) + **#902** (board-audit closed-issue false-clear). Recurring shape (same class hit P4W3/P5W3 per stale annunaki entries) — now tracked.
2. **Board-audit Step 4 false-clears closed-issue Wave fields** — the open-only label join vs all-board-items diff proposed clearing 6 closed issues' Wave fields. Owner chose full-literal sync anyway; defect filed as **#902**.
3. **Stale annunaki backlog** — `errors.jsonl` carries 54 unprocessed entries from prior waves (2026-06-12 → 06-19), dominated by the #901 parser-shape class, known false-matches (PR-body text matching `ModuleNotFoundError:`/`^FAILED`), and the worktree-fragile `test_ontology_tracker` ([[project_ontology_tracker_worktree_test]]). The per-wave marker pattern means the cross-wave backlog never gets swept — minor hygiene gap, no data impact.

### Proposed Process Changes
**None this wave.** W19 already shipped the two structural fixes (Hook 22, Step 10.7) and they validated this wave. The two defects surfaced (#901 parser, #902 board-audit) are already filed as tooling-bug follow-ups against the hook/skill — no charter amendment needed; they are bugs in existing automation, not missing rules.

### Annunaki-attack
**0 captured in the P7W20 window.** `errors.jsonl` holds 54 stale entries (all 2026-06-12 → 06-19, prior waves) — nothing appended during this wave (2026-06-25/26). This wave's only real glitch (kickoff hook-parser) was filed live as #901/#902 during the wave, not via post-hoc capture. Backlog content is non-actionable-or-already-filed: the parser-shape bug (→#901), known stdout false-matches (PR-body text, dev-iteration test failures), and the memory'd worktree-fragile test. **0 new actionable artifacts.** Marker `wave_20_annunaki_attack_ran_at` written.

### Promotion audit
**0 AUTO · 0 DECIDE · 213 KEPT · 23 SUPERSEDED** (`promotion-audit/run.py wave-20`) — nothing crossed a threshold mechanically. [[feedback_wave_branch_merge_not_squash]] now shows under SUPERSEDED (codified to Hook 22 in W19). Standalone log: `promotion_audit_log/p7-wave-20.md`.

### Memory-to-automation audit
**0 new promotions.** The wave's two tooling defects map to already-filed bugs (#901/#902), not soft memories needing codification. Recently-added memories ([[feedback_wave_branch_merge_not_squash]] already promoted to Hook 22 in W19; [[feedback_local_ci_parity_no_force]] tracked for full rollout by #684) are either codified or appropriately situational. No memory crossed a promotion threshold. Marker `wave_20_memory_audit_ran_at` written.

### Next-wave scope
W21 stub auto-drafted + boarded, `wave_21_meta_issue` recorded; carry-forward pre-loaded. Theme TBD — owner to set, then run `/phase-review 7` → `/wave-scope 7 21`.

## Retrospective: Phase 7 Wave 21 — 2026-06-26

### Team Performance
**11 PRs merged** (10 data-acquisition + 1 isnad-graph), 5 implementers, **0 CI-red merges**, top-implementer concentration **27%** (Alejandra & Kavitha tied 3/11). Both wave→main integration PRs merged clean (da#243 → `9cc3969`, ig#1138 → `e4c0c542`); wave branches retained. CR-cycles historic **4** (recomputed 0 — all edited-in-place to Approved; `wave_21_counter_corrections` documents the conflict; historic stands). Theme: narrator-dating foundation (Phase-7 end-state criterion #5) + prod re-validation umbrella (main#723, owner-run, unmerged).

### Per-Engineer Assessments (mechanical — `trust_signals.py score 7 21`)
- **Alejandra Reyes-Fuentes** — da#233/#241/#236, prs_merged=3, +1 absorbed at ceiling 5. Clean fix on range→EXACT precision over-claim (da#241).
- **Kavitha Sundaramurthy** — da#237/#235/#234, prs_merged=3, +1 absorbed at ceiling 5. Absorbed TRANSMITTED_TO fabrication catch (da#235).
- **Ivana Horvat** — da#240/#238, prs_merged=2, held at 5. Death-anchored date parser + geo disambiguation.
- **Nikolaos Papadopoulos** — da#242/#232, prs_merged=2, held at 5. Hijri util + ṭabaqa fallback.
- **Jun-Seo Park** — ig#1137, prs_merged=1, held at 4 (single clean PR = no bump). Fixed always-0 narrators_dated count under review.

### Top 3 Going Well
1. **Dependency-batched spawn held.** Batch A (6 roots: model/hijri/independent TD) before Batch B (parse→reconcile→fallback) kept the shared Narrator model/schema from conflict-thrashing — zero cross-PR rebase churn on the foundation chain.
2. **2-reviewer gate caught 4 real data-correctness defects** — TRANSMITTED_TO provenance fabrication, narrators_dated always-0, single-source range→EXACT over-claim, order-dependent consensus-band widening — each fixed with a regression test that fails on pre-fix code. The gate is doing genuine work, not rubber-stamping.
3. **W19/W20 process changes held a third wave.** Hook 22 (`--merge` not squash) and Step 10.7 (child structural pre-regen) meant both wave→main PRs were green on staleness-check from first push — zero fix-forward scrambles, same as W20.

### Top 3 Pain Points
1. **Mechanical trust scoring can't see reviewer catches when verdicts are edited-in-place.** This wave had 4 substantive must-fix catches, but `must_fix_caught` reads 0 for every reviewer because verdict-amendment rewrites the verdict surface to Approved. The reviewers who caught real defects get no mechanical credit. Same root conflict as the CR-cycle counter — the amendment rule and the recompute read the same surface with opposite intent.
2. **Structural-index serial-merge queue.** Every da PR commits a regenerated `ontology/structural/llms.txt`, so each merge conflicted the next pending PR on that generated file → forced a one-at-a-time merge queue (resolve via regenerate-and-merge). Mechanical but slow; 10 da PRs = 10 serialized merges.
3. **main#723 (prod re-validation) cannot close from code merges alone.** The fixes are on each repo's `main`, but #723 needs the W20/W21 merges *deployed to prod* + the dedup/segmentation pipeline *re-run on prod* — an owner-gated stg/prod deployment, not a spawnable PR. It remains the single open wave item.

### Proposed Process Changes
1. **Credit reviewer catches before verdict-amendment erases them.** — Rationale: `trust_signals.extract` should capture `must_fix_caught` from the PR's review *timeline* (first-pass ChangesRequested verdicts) rather than only current comment state, so edit-in-place amendment doesn't zero out real catching. Mirrors the CR-cycle "wrapup-time historic is authoritative" resolution. (Proposal only — owner decides; ties to a `trust_signals.py` change.)
2. **Consider a wholesale-regenerate merge driver for `ontology/structural/llms.txt`** so same-file structural-index conflicts auto-resolve instead of serializing the merge queue. — Rationale: the file is generated, never hand-merged; a regenerate-on-conflict driver removes the serial bottleneck. (Proposal only.)

### Wave-shape table
| Metric | Value |
|--------|-------|
| PRs merged | 11 (10 da + 1 ig) |
| CI-red merges | 0 |
| Changes-requested cycles (historic) | 4 (recomputed 0 — edit-in-place; historic authoritative) |
| Top-implementer concentration | 3/11 = 27% (Alejandra & Kavitha tied) |
| Tech-debt filed | 0 new (2 proposals above, not yet filed) |
| Fire/hire | none |

## Retrospective: Phase 7 Wave 22 — 2026-07-01

**Final wave of Phase 7.** Theme: prod cutover hardening + #723 data-quality closeout attempt + hook/tooling fixes.

### Team Performance
22 PRs merged (10 isnad-graph, 6 deploy, 3 main, 3 data-acquisition); 16 implementers; **0 CI-red merges**; top-implementer concentration **14%** (Lucas Ferreira & Mateo Salazar tied 3/22); 1 changes-requested cycle; 1 review false-positive. Counter block (`wave_22_final_pr_count=22`, `changes_requested_cycles=1`, `top_concentration_pct=14`) matches PR-level recomputation — no drift. Alongside the PR wave, an out-of-band prod operational window ran (corrected-artifact graph reload + code promotion to stg→prod, code+graph parity achieved).

### Per-Engineer Assessments
Mechanical (`trust_signals.py score 7 22`). Changes: **Nneka Obi 4→5** (2 PRs + a real review catch — the wave's single distribution-discipline new-5); **Alejandra Reyes-Fuentes 5→4** (1 review false-positive); Aisha & Kavitha +1 absorbed at ceiling 5; Jun-Seo +1 held at 4 (merely-clean, no catch). All others held (delta 0). No retirement triggers.

### Top 3 Going Well
1. **CI health: 0 red merges across 22 PRs** — the local⇄CI parity discipline (main#684) is holding across all 4 repos.
2. **Healthy load distribution** — 14% top concentration (lowest of Phase 7), 16 implementers; no fragility.
3. **Prod window executed** — corrected-artifact reload + stg→prod promotion reached exact code+graph parity; 2 of 4 #723 criteria (50-cap lift ig#1147, chains) genuinely landed and are now API/UI-verified.

### Top 3 Pain Points
1. **#723 criterion 1 falsely reported "resolved" (orchestrator validation-discipline miss).** An aggregate cypher "matn=0" pass was treated as sign-off, but a record-level API/UI check (prompted by the owner) found **≥7,580 matn-as-narrator nodes live on prod** — Qur'anic phrases, sentence fragments, whole hadiths rendered as narrator names. Aggregate metric ≠ record-level truth. This is the recurring "cypher-pass ≠ UI walkthrough" lesson, now with a hard number.
2. **da#247 + da#253 were closed on artifact-fix but never reached prod.** The prod reload used curated narrators generated *before* the da#247 NER re-extraction, so a "closed" fix was invisible on the live environment. Closure without target-environment verification.
3. **`must_fix_caught` mechanical blind spot persists (recurring from W21).** Verdict edit-in-place to Approved erases the catch surface the helper reads, so real reviewer catches go uncredited. Same measurement-conflict class as the CR-cycle counter.

### Proposed Process Changes — OWNER-RATIFIED 2026-07-01 (#2 amended)

> **Owner ratification 2026-07-01:** all three approved. **#2 amended** — the close-verification gate is **stg**, not prod (aligns with [[feedback_stg_gate_before_prod]]: prod changes only as promotion of a verified-good stg change). A **standing stg↔prod parity tracking issue** collects data-quality issues verified/closed on stg so they are re-verified — or their stg vs prod results compared — after prod promotion. #1+#2 codified in charter `issues.md § End-State Criterion` (this retro PR #915); #3 filed as a `trust_signals.py` tooling issue; parity tracker filed.

1. **Record-level verification gate for data-quality criteria** — Rationale: a data-quality/corpus criterion may not be signed off on an aggregate metric (count/cypher) alone; sign-off requires sampling **N actual rendered records** via the API or UI. "matn=0" as a COUNT is necessary but not sufficient; the failure mode is a metric that measures a narrower signature than the criterion claims. (Charter validation/acceptance section.) **→ codified: `issues.md § End-State Criterion`.**
2. **A data-quality issue closes on STG record-level verification; prod is validated separately as a promotion** — Rationale (amended by owner): da#247/da#253 were artifact-fixed and closed, but the fix never reached even stg. stg is the validated gate before prod, so a data-quality fix issue stays open until the corpus change is record-level-verified **on stg**. Closure does **not** wait on prod — prod is reached later by promotion — but every stg-closed data-quality issue is entered on a **standing stg↔prod parity tracker** so its live prod state is re-verified (or stg-vs-prod results compared) after promotion, per [[feedback_stg_gate_before_prod]]. **→ codified: `issues.md § End-State Criterion` + standing parity tracker filed.**
3. **Credit reviewer catches that were later edited-in-place** — Rationale: recurring W21/W22 gap; the verdict-amendment rule erases `must_fix_caught`. Either preserve a pre-amendment catch record or read the review timeline, so reviewers aren't mechanically uncredited for real catches. (trust_signals / wrapup Step 10.6.) **→ filed as a `trust_signals.py` tooling issue.**

### Sub-audits
- **Annunaki-attack:** 88 errors captured this wave — all session-local exploration command-failures (62 `cd`-prefix compound-command exit flags from the prod ssh/curl work, plus gh/cat/echo probes). No wave-code defect or systemic pattern; no hook/skill/charter change warranted. Marker written.
- **Memory-to-automation audit:** no new memory→hook/skill/charter promotion candidate this wave; the session's memory work was a correction (prod-pollution state) already captured. Marker written.

---

