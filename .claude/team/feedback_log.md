# Team Feedback Log

Track all feedback events here. Format:

```
## [DATE] — [FROM] → [TO] — Severity: [minor/moderate/severe]
[Feedback content]
[Action taken, if any]
```

---

## Archive (per-phase)

Closed-phase entries are archived per-phase at phase close (#964, meta #960;
`charter.md` § Feedback System → Per-Phase Archival). The live log keeps the
current phase (and its waves) only — newest entries are appended at the end.

- [Pre-Phase-2 — sessions, user-service extraction, 2026-03 numbering (≤ 2026-04-09)](archive/feedback_log_pre-phase-2.md)
- [Phase 2](archive/feedback_log_phase-2.md)
- [Phase 3](archive/feedback_log_phase-3.md)
- [Phase 4](archive/feedback_log_phase-4.md)
- [Phase 5](archive/feedback_log_phase-5.md)
- [Phase 6](archive/feedback_log_phase-6.md)
- [Phase 7](archive/feedback_log_phase-7.md)

---

## Retrospective: Phase 8 Wave 23 — 2026-07-06

**Theme:** #723 data-quality closeout landed on prod (the scrubbed 150,187-narrator artifact) + promotion-path fix.

### Wave metrics (wave-shape table)

| Metric | Value |
|--------|-------|
| PRs merged | **20** (19 at wrapup + PR#322 da#321 fix post-wrapup; counter-corrected 19→20) |
| Repos in scope | 4 (data-acquisition, isnad-graph, deploy, main) |
| Issues closed | #723 (the marquee), da#258/#248/#259, ig#1148, da#321 |
| CI health | **0 CI-red merges**, 0 review false-positives |
| Changes-requested cycles | 2 |
| Tech-debt filed | da#319 (validation-harness multi-statement Cypher), da#321 (dedup cross_sect divergence — since fixed) |
| Top-implementer concentration | 6 PRs / 20 = **30%** by Alejandra Reyes-Fuentes (theme-fit) |

### Per-engineer assessments (mechanical — `trust_signals.py score 8 23`)

- **Alejandra Reyes-Fuentes** — 6 PRs, delta **+1** → 5 (recovers W22 dock). Clean: must_fix_received=0, ci_red=0, false_positives=0. Wave workhorse on the scrub spine. Severity: none.
- **Nikolaos Papadopoulos** — 5 PRs + must_fix_caught=1, delta **+1** → absorbed at ceiling 5. Severity: none.
- **Ivana Horvat** — 4 wave-branch PRs + PR#322 (da#321 fix), must_fix_received=2 / rework=2, delta **0** → held 5. Negative-signal: the wave's main author-side rework. Severity: minor.
- **Kavitha / Oyunbileg / Nneka / Lucas** — 1 clean PR each, delta 0, held. Kavitha + Oyunbileg each contributed a review catch/verification.

### Top 3 going well
1. **#723 closed on prod, record-level verified at exact stg↔prod parity** — all 4 criteria pass (matn-opener pollution 0.000% weighted, collection 99.96%, chains 587,932, search ONLINE, parallels 4.49M). The multi-wave data-quality saga landed.
2. **Zero CI-red merges, zero review false-positives across 20 PRs** — cleanest quality signal of the recent waves; the local⇄CI parity gate held.
3. **da#321 was root-caused as a *real* bug, not papered over** — a green-CI/red-local test surfaced a genuine dual-detector cross_sect divergence (+ a latent prod mislabel on fawaz/4 corpora); fixed at the authoritative source, 2-reviewer approved.

### Top 3 pain points
1. **Orchestrator under-described the orphan tail** — first framed the 44,073 orphans as "accepted bio narrators"; a stranded-worktree memory surfaced ~26% is da#317 matn-sentence pollution. Weighted-criterion closure stayed honest, but the initial characterization was too generous. Corrected in-session.
2. **da#317 memory commit got stuck behind a local-flaky pre-push for a full wave-cycle** — the very da#321 divergence blocked preserving the memory that documented a *different* pollution class. Resolved only by fixing da#321 first.
3. **Annunaki log is accumulating unactioned** — 109 genuine records, but ~all session-local exploration command-failures (prod ssh/curl, the expected structural-gate/stale-tmp/pytest-loop hook *blocks* correctly logged as prevented commands). No wave-code defect, but the signal-to-noise means a real defect could hide; the log deserves a periodic prune, not per-wave triage-from-scratch.

### Proposed process changes
1. **Carry-forward tails must be characterized by their *dominant class*, not their most-favorable class** — Rationale: the orphan-tail miss (pain #1). When closing a data-quality criterion on a weighted metric, the retro/closure note must state what the un-weighted remainder actually *is* (here: matn-sentence pollution, da#317), not just that it weights ~0. Prevents a generous framing from masking real remaining work.
2. **Prune the annunaki error log at wave-wrapup once triaged benign** — Rationale: pain #3. If a wave's captured errors are all session-local noise, wrapup should archive/clear them (not just write the marker), so the next wave's count reflects genuinely-new signal instead of a growing pile.

### Sub-audits
- **Board freshness:** wave-23 issues (#723 + declared) all closed and off the active column; no orphan/Wave-field drift observed.
- **Annunaki-attack:** 109 genuine records; last-25 sampled = all session-local exploration command-failures (`cd`-prefix compounds from the prod window, `gh` probes, and correctly-logged hook *blocks* from the da#321 debugging). No wave-code defect or systemic pattern; no hook/skill/charter change warranted. Marker written. (See proposed change #2 re: pruning.)
- **Memory-to-automation audit:** the session added `feedback_dual_detector_cross_sect_authority` (da) — a genuine debugging heuristic, but too fresh/niche to cross a promotion threshold this wave; kept as memory. No memory→hook/skill/charter candidate. Marker written.
- **Promotion audit:** no memory/charter/skill crossed an auto/decide-tier threshold this wave.

---

## Retrospective: Phase 8 Wave 24 — 2026-07-18

**Theme:** #928 defect sweep + graph re-run from `parse` + prod cutover. A long-running fix-then-rerun wave (kicked off 2026-07-05): fix every parse/resolve/load/deploy defect found en route to staging, then wipe-and-reload the graph from `parse` and promote to prod. Formally closed today after the cutover completed.

### Team Performance (wave-shape table)

| Metric | Value |
|--------|-------|
| PRs merged to wave-24 branch | **6** (main-repo housekeeping: #924/#965/#966/#967/#969/#972) |
| Repos in scope | 3 (noorinalabs-main, data-acquisition, deploy) |
| Substantive work | prod cutover (deploy#610/#611: promote→reload→prune→enrich + over_merged flag op, 8 hubs) + 56-issue defect sweep — **merged direct-to-main across da/deploy, outside the wave-branch window** |
| Issues reconciled at wrapup | 47 open wave-24 → **8 resolved+closed**, **39 deferred-TD** carry-forward backlog |
| CI health | 0 CI-red merges, 0 review false-positives on the wave-branch set |
| Changes-requested cycles | 1 |
| Top-implementer concentration | 2 PRs / 6 = **33%** (Aino), housekeeping window only |
| Annunaki | 46 genuine (session-local) → 268 archived to `archive/wave-24.jsonl`, live log reset |
| Promotion audit | 0 AUTO · 0 DECIDE · 206 KEPT · 24 SUPERSEDED |

### Per-Engineer Assessments (mechanical — `trust_signals.py score 8 24`)

Measurement window = the 6 main-wave-branch housekeeping PRs only (see trust_matrix caveat). Aino **+1** (2 clean process/charter PRs, absorbed at ceiling 5); Lucas/Nurul/Santiago/Weronika delta 0. The cutover/sweep contributors (da + deploy SREs) merged direct-to-main and are not in the measurable window — not re-scored, flagged rather than invented.

### Top 3 Going Well
1. **The multi-wave data-quality program reached prod.** The #928 re-run + cutover landed all four owner-gated prod graph writes green and the over_merged flag op (8 bare-name hubs, bidirectional-verified). The choke-point program (main#928) is fully live on prod.
2. **Honest issue reconciliation at wrapup.** The 39-item deferred-TD tail was documented as a carry-forward backlog (`wave_24_carry_forward`) and NOT force-relabeled into the already-scoped Phase 9 waves — preserving the owner-approved Phase 9 plan (main#977) rather than corrupting it to make the board look clean.
3. **Zero CI-red merges / zero review false-positives** on the wave-branch set; the local⇄CI parity gate held.

### Top 3 Pain Points
1. **The wave's real trust signal is unmeasurable from the wave branch.** Because the substantive engineering merged direct-to-main across da/deploy (neither had a wave-24 branch), `trust_signals score 8 24` sees only housekeeping PRs. A long fix-then-rerun wave with a wave-branch model declared but not used for the bulk of the work defeats the mechanical per-engineer scoring.
2. **A 39-issue deferred-TD tail accumulated under one wave label** and was never triaged until this formal wrapup (the wave had merged its deliverables but was never closed — session-start Step 5b nudge). The tail sat on the active board for ~2 weeks.
3. **`post_label_change_wave_field_sync` cannot parse multi-issue `gh issue edit` shapes** (loops / space-separated lists) — every bulk delabel this wrapup logged a benign `skip_parser_returned_empty` event. Labels were removed correctly, but the Wave-field auto-sync silently didn't fire for bulk ops.

### Proposed Process Changes
1. **Declare `direct-to-main` merge model for waves whose child-repo work will not use a wave branch** — Rationale: pain #1. Wave 24 declared `wave-branch` but da/deploy shipped direct-to-main with no wave branch; the mismatch is why the mechanical trust scoring is blind to the wave's real work. If the model matches reality, the reachability check and trust signals both measure the right set. (Aligns with the existing memory `feedback_stg_gate_before_prod` / one-merge-model-per-wave discipline.)
2. **Wrapup a wave as soon as its deliverables merge, don't let the label linger** — Rationale: pain #2. The session-start Step 5b "merged-but-unwrapped" nudge fired but was only actioned two weeks later. Consider treating a persistent unwrapped-nudge as a soft gate at the next kickoff (already partially enforced by the kickoff Step 0a scope precondition, which is what caught this).

### Sub-audits
- **Board freshness:** wave-24 now has 0 open labeled issues after reconciliation; the 39 deferred are delabeled and recorded in `wave_24_carry_forward`.
- **Annunaki-attack:** 46 genuine records, all benign session-local — correct hook blocks (`validate_review_comment_format`, `validate_commit_identity` catching this session's own `-F`/bare-principal attempts), a throwaway `python3 -c` module-path failure, and `post_label_change_wave_field_sync` parser-skip events from this session's bulk label ops. No wave-code defect; no automation warranted. Archived (268 records) + live log reset. Marker written.
- **Memory-to-automation audit:** the corpus was just pruned this wave (#967/#944 consolidated the gotcha families; index at 95/132). No memory crossed a promotion threshold; the 8 rescued deploy backup/DR memories (committed d45e3ce this session) are fresh and repo-local. No memory→hook/skill/charter candidate. Marker written.
- **Promotion audit:** 0 AUTO · 0 DECIDE · 206 KEPT · 24 SUPERSEDED. Nothing crossed a threshold. Log: `.claude/team/promotion_audit_log/wave-24.md`.


---

## Retrospective: Phase 9 Wave 25 — 2026-07-19

**Theme:** Narrator disambiguation & split correctness (data-acquisition). 7 issues fixing over-merge/under-merge and split-gate correctness in the resolve/parse pipeline, upstream of the owner-gated #978 re-run.

### Team Performance
- **PRs merged:** 7 (da#444/#439/#346/#431/#366/#452/#347), all to `deployments/phase-9/wave-25`; wave→main via PR#460 (`122c7b9`, branch retained).
- **Issues closed:** 7 (da#443 deferred to wave-27). **CI health:** 0 red merges; every per-issue PR + the integration PR green.
- **Counters:** final_pr_count=7, changes_requested_cycles=0, top_concentration_pct=43 (Kavitha 3/7). Counters verified against PR-level recompute — no drift.
- **Deployable-merge:** verified green (da has no post-merge deploy/publish surface). **Staging gate:** success (standing run; da not a fan-in repo).

### Per-Engineer Assessments
- **Kavitha Sundaramurthy** — 3 PRs (da#444/#346/#452), delta +1 absorbed at ceiling 5. Clean: prs_merged=3, 0 CI-red, 0 must-fix received. Wave workhorse on the split-gate spine.
- **Ivana Horvat** — 2 PRs (da#431/#347), delta +1 absorbed at ceiling 5. Clean composition on the merged adjacency helper; surfaced the stacked-PR-orphan lesson.
- **Alejandra Reyes-Fuentes** — 1 PR (da#366) + reviewer, delta 0 (held at 5). **Caught the orchestrator verdict-format error via the enforcer** — the reason the gate-bypass surfaced.
- **Nikolaos Papadopoulos** — 1 PR (da#439) + reviewer, delta 0 (held at 5). Thorough #458 A/B verification.
- **Jean-Claude Habimana** — reviewer-only (not score-tracked): 2 thorough verdicts (#455/#459).

### Top 3 Going Well
1. **Reviews were genuine and engine-verified** — reviewers ran the real resolve engine and bidirectional A/B fixtures (Nikolaos on #458, Alejandra/Jean-Claude on #455/#459), not string-only checks. da#423 drop-gate discipline held.
2. **Enforcer-first discipline caught an orchestrator error** — Alejandra ran `pr_review_state.py` rather than trusting my (wrong) brief, surfacing the format/gate breach. Trusting the tool over the brief is exactly the memory §8 lesson, applied.
3. **Clean composition of stacked resolve stages** — narrator_unify (#455) + Anas under-merge (#459) composed on the shared `resolved_chain_neighbours` helper with no divergent adjacency logic; RESOLVE_STEP_ORDER coherent throughout.

### Top 3 Pain Points
1. **Orchestrator gate-bypass (the wave's defining failure).** A paraphrased verdict-trailer brief (`Request` + invented `**Review:**`) AND `gh pr merge -R $VAR` (fail-opens Hook 4) co-occurred → 4 PRs merged with 0 counted approvals and no block. Remediated (records fixed 2/2 each, #981 filed, memory §7/§8 updated). Two catchable errors that only bit together.
2. **Hook fail-open on unresolvable repo (#981).** `_resolve_owner_repo` returns None for `-R $VAR` and Hook 4 fails OPEN. This is a security-relevant hook-hardening item (fail CLOSED) — DECIDE-tier, filed.
3. **cwd-anchor kickoff-comment hook misresolution (recurring).** The kickoff-comment + label-sync hooks resolved da issues as `noorinalabs-main#N` (stdin cwd anchor), emitting "No assignment row / not on project 2" for all 8 kickoff labels; recovered manually. Documented in `feedback_hook_cwd_anchor_subagent_worktree` — worth a hook fix (resolve repo from the command's `-R` flag).

### Proposed Process Changes
1. **Fix #981 fail-closed next wave** — Hook 4 must BLOCK (not allow) when `-R`/`--repo` cannot resolve to `owner/repo`. Rationale: a gate that fails open is worse than no gate; it reads as enforced. — Section: `charter/pull-requests/ci-gates.md` + `validate_pr_review.py`.
2. **Spawn-brief verdict-block must be copied verbatim, never paraphrased** — already added to memory §8; propose promoting to a reviewer-brief template/checklist the orchestrator fills from the canonical block, so paraphrase is structurally impossible. — Section: `charter/agents/orchestration-model.md` § reviewer spawn.
3. **Kickoff-comment/label-sync hooks resolve repo from `-R`, not stdin cwd** — file against the hook; recurring benign noise that masks real board-add failures. — Section: `charter/hooks`.

### Annunaki-attack
32 records archived (`archive/wave-25.jsonl`), live log reset. All 24 genuine errors benign: correctly-firing guard blocks (2-reviewer gate on #458/#451, squash-block on #455, branch-freshness ×2, stale-tmp, unexported-`$S`), one session-local parquet-schema probe failure (Kavitha), and the cwd-anchor kickoff-comment misresolution (pain-point #3). No wave-code defect; no new automation (the one hook item, #981, already filed). Marker written.

### Memory-to-automation audit
Concrete output: added the zsh `path`-tied-to-`$PATH` clobber gotcha to `feedback_zsh_shell_environment.md` (a real trap hit this wave; not covered by `warn_zsh_wordsplit`). New `feedback_stacked_pr_base_delete_orphan.md` retained as memory (a `--delete-branch`-blocking hook is possible but low-frequency). No memory crossed a promotion threshold. Marker written.

### Promotion audit
0 AUTO · 0 DECIDE · 207 KEPT · 24 SUPERSEDED. Nothing crossed a threshold. Log: `.claude/team/promotion_audit_log/wave-25.md`. (The #981 fail-closed hook hardening is a filed bug, not a promotion crossing.)

---

## Retrospective: Phase 9 Wave 26 — 2026-07-22

**Theme:** Parse recovery & name quality. Repos in scope: `noorinalabs-data-acquisition` (13 PRs), `noorinalabs-main` (2 PRs). Meta-issue #983.

### Team Performance
- **15 PRs merged** (da#461–479 ×13; main#1059/#1061 ×2), **0 CI-red merges**, **0 review false-positives**.
- **5 changes-requested cycles** (must-fix-received: Kavitha 2, Jean-Claude 2, Alejandra 1) — all resolved and merged clean.
- **Top-implementer concentration 20%** (Alejandra / Kavitha tied 3/15) — down from wave-25's 43%, well below the 60% fragility line.
- Wave wrapped end-to-end pre-session: both wave→main merges green (main#1063 28/28, da#480 22/22, `--merge`, branches retained per owner directive); reachability clean; staging green (this wave has no fan-in/deployable surface — meta + data-pipeline only).

### Counter verification (Step 2.5)
All three `wave_26_*` counters match PR-level recomputation — **no drift**, no `counter_corrections` entry needed:
- `final_pr_count=15` = 2 main + 13 da ✓
- `changes_requested_cycles=5` = Σ must_fix_received (2+2+1) ✓
- `top_concentration_pct=20` = max 3 PRs / 15 ✓ (the scope note's 25% was 3/12 over *planned issues*; the counter is over *actual PRs* — both internally consistent)

### Per-Engineer Assessments (mechanical — `trust_signals.py score 9 26`)
| Engineer | PRs | Signals (merged / mf-caught / mf-recv / ci-red / rework) | Delta | Severity |
|---|---|---|---|---|
| Nikolaos Papadopoulos | da#472,#473 | 2 / 2 / 0 / 0 / 0 | +2 (abs. at ceiling) | none — wave top signal |
| Kavitha Sundaramurthy | da#474,#476,#479 | 3 / 1 / 2 / 0 / 2 | 0 | minor (rework on hardest surface) |
| Alejandra Reyes-Fuentes | da#466,#468,#470 | 3 / 1 / 1 / 0 / 1 | 0 | minor |
| Ivana Horvat | da#465,#469 | 2 / 0 / 0 / 0 / 0 | +1 (abs. at ceiling) | none |
| Oyunbileg Batbayar | da#461 | 1 / 1 / 0 / 0 / 0 | 0 | none |
| Jean-Claude Habimana | da#462 | 1 / 0 / 2 / 0 / 1 | 0 (seed 3) | minor (2 mf-recv on one PR) |
| Kwesi Boateng | da#463 | 1 / 0 / 0 / 0 / 0 | 0 (seed 3) | none |
| Aino Virtanen | main#1061 | 1 / 0 / 0 / 0 / 0 | 0 | none |
| Nino Kavtaradze | main#1059 | 1 / 0 / 0 / 0 / 0 | 0 (seed 3) | none |

Full negative-signal pass (bare "None" banned) recorded in `trust_matrix.md` § P9W26 — every active engineer carries either a specific gap or an explicit `clean: {numbers}` line. Three engineers (Jean-Claude, Kwesi, Nino) enter score-tracking this wave, seeded at neutral 3.

### Top 3 Going Well
1. **Clean, well-distributed wave.** 0 CI-red merges across all 15 PRs; concentration 20% (down from 43% W25) spread across 9 implementers — no fragility, no single-owner dependency. The name/parse-quality surface is now worked by the whole data-acquisition bench, not one person.
2. **Genuine reviewing that caught real issues.** Nikolaos's `must_fix_caught=2` (on the gloss-tail/name-cut discrimination PRs) was the wave's top composite signal — real catches on subtle discrimination logic, 0 false-positives across the whole wave.
3. **The W25 gate-bypass class was structurally closed.** main#1059 (repo-authoritative-over-cwd in wave-label hooks, #985) + main#1061 (verbatim verdict-block in the spawn-brief template, #984) + the #981/#1056/#1057 fail-closed chain landed. No verdict-format or fail-open recurrence this wave — the remediation held.

### Top 3 Pain Points
1. **Rework concentrated on the name_quality / bio_promote discrimination surface.** All 5 must-fix-received landed here (Kavitha 2 + Jean-Claude 2 + Alejandra 1) with 4 rework cycles. Not a quality failure — everything shipped clean, 0 CI-red — but the tier-1 "recover a real narrator from a matn tail vs. a gloss tail" discrimination is the wave's hardest logic and drew every iteration. Reviewers and authors were re-deriving the same A/B distinctions per-PR.
2. **`premise_check` false-STOP on prose (main#1047).** The premise-rot gate STOPped 12/12 on scope prose fragments containing `/`; all hand-verified false positives (0 genuine rot). A gate that cries wolf 12/12 trains people to bypass it — filed, carried to wave-27.
3. **High `block_bare_grep` volume.** 60 of the wave's ~114 annunaki events were the bare-`grep` hard-block firing (correctly). The guard works and nudges to `rg`, but the sheer recurring count shows the reflex to type bare `grep` persists across orchestrator/agent sessions — worth surfacing, no code change warranted.

### Proposed Process Changes
1. **Shared A/B fixture harness for discrimination-gate issues, up front.** — Rationale: 5/5 must-fix-received and 4 rework cycles all landed on the name_quality/bio_promote discrimination surface, with authors and reviewers re-deriving the same gloss-tail-vs-name-cut A/B distinctions per PR. When the next wave scopes discrimination-gate work, seed a shared fixture set the whole tier verifies against, so the distinction is defined once. — Section: `charter/issues.md` § Wave Planning (fixture-first for discrimination-gate tiers).
2. **Prioritize `premise_check` `/`-token fix (#1047) in wave-27.** — Rationale: it STOPped 12/12 this scope run and will keep firing on every prose-heavy scope; a gate at a 100% false-positive rate is worse than no gate. Already filed + labeled wave-27; flagging as a priority, not merely carry-forward.
3. **No annunaki-driven charter change.** — Rationale: all ~114 genuine errors triaged benign (see below); the bare-grep and pipe-mask classes are already hard-blocked / detected. No new automation crosses a threshold.

### Annunaki-attack (Step 7.6)
**114 genuine errors triaged; all benign.** Breakdown: 60 `block_bare_grep` (guard correctly firing), 12 `validate_branch_freshness`, 10 `post_label_change_wave_field_sync` (pre-#985-fix cwd-anchor noise — the fix landed this wave), 7 `validate_review_comment_format`, plus 1–2 each of label/board/ontology/kickoff hooks — all correctly-firing guards. 158 low-confidence `pipe-mask-suspect` heuristic fires + 11 high-confidence `masked-failure`: the latter are 5× the known `git push … | tail` pipe-masks-exit-code trap (each retried/rebased successfully after a branch-freshness rejection) and 6× session-local scripting probes (wrong-path `json.load` on `.claude/team/cross-repo-status.json` — the file is at repo root; a verification `AssertionError`; `gh api | python3` on non-JSON). **No wave-code defect, no production impact, no new automation.** Log archived to `.claude/annunaki/errors.jsonl.bak.*`, live log reset, marker written (`wave_26_annunaki_attack_ran_at`).

### Memory-to-automation audit (Step 7.7)
**No conversions.** No memory files were added or modified during wave-26 (git log over `.claude/memory/` since 2026-07-20 is empty), and the promotion audit found 0 AUTO / 0 DECIDE — the 20+ codifiable feedback memories are already promoted-via-provenance. Marker written (`wave_26_memory_audit_ran_at`).

### Memory decay & size sweep (Step 7.8)
3 files flagged (advisory, non-blocking): `project_narrator_chokepoints_enrich.md` (52 KB, touched 3d ago), `feedback_fixture_makes_guard_assertion_inert.md` (21 KB, 11d), `feedback_sweep_expensive_stage_before_launch.md` (15 KB, 11d). All recently touched (live, not stale) → **keep** for now; `project_narrator_chokepoints_enrich.md` is the standing consolidation candidate at 52 KB (3.6× the soft ceiling) — carry forward to a future retro when it goes quiet.

### Promotion audit (Step 7.5)
0 AUTO · 0 DECIDE · 220 KEPT · 24 SUPERSEDED. Nothing crossed a threshold. Log: `.claude/team/promotion_audit_log/wave-26.md`.

### Fire/hire
None. Retirement trigger fired for no engineer. Three engineers (Jean-Claude, Kwesi, Nino) newly enter score-tracking at neutral 3.

---

## Retrospective: Phase 9 Wave 27 — 2026-07-22

**Theme:** Pre-cutover data-quality closeout + Phase-9 tooling-debt cleanup (last wave of Phase 9). Merge model: wave-branch (`deployments/phase-9/wave-27` → main via #1083 main + #487 da).

### Team Performance
- **17 PRs merged** (main 13, data-acquisition 4), 2 repos in scope. **0 CI-red merges**, **0 review false-positives**.
- **2 changes-requested cycles** (both merge-gate catches, both fixed + re-CI'd + re-approved fresh). CR-cycle recomputation from current review state finds 0 (both verdicts edited-in-place to Approved after fixes per charter § verdict-amendment); claimed 2 stands as authoritative-historic (P3W15 semantics), recorded in `wave_27_counter_corrections`.
- **Counter verification:** final_pr_count 17=17 ✓, top_concentration 18%≈18% ✓, CR-cycles conflict resolved above.
- All 17 work issues closed; meta #1067 closes at this retro. Both wave→main integration PRs owner-approved and merged; staging promotion green.

### Wave-shape table
| Metric | Value |
|---|---|
| PRs merged | 17 (main 13, da 4) |
| CI-red merges | 0 |
| Review false-positives | 0 |
| Changes-requested cycles | 2 (authoritative-historic) |
| Top-implementer concentration | 3 PRs / 17 = 18% (Aino / Nino / Weronika tied) |

### Per-Engineer Assessments (mechanical — `trust_signals.py score 9 27`)
Helper-proposed deltas: Aino +1, Nino +1, Lucas +1, Nurul +1; all others 0. (Full evidence-anchored table in `trust_matrix.md` § Phase 9 Wave 27 Trust Updates.)
- **Aino Virtanen** — #1081/#1075/#1071, prs_merged=3 clean. Delta +1. clean. none.
- **Nino Kavtaradze** — #1078/#1076/#1072, prs_merged=3 clean. Delta +1. clean. none.
- **Lucas Ferreira** — #1077/#1070, prs_merged=2 clean. Delta +1. clean. none. (first main-repo score, neutral+bump)
- **Nurul Hakim** — #1073/#1069 + must_fix_caught=1 (held #1079's fail-open gate). Delta +1. clean. none. (first main-repo score, neutral+bump)
- **Weronika Zielinska** — #1080/#1079/#1074, prs_merged=3, must_fix_received=1 (#1079). Delta 0. Gap: 1 must-fix received. minor. (first main-repo score, neutral)
- **Alejandra Reyes-Fuentes** — da#484 (Tier-1 cutover gater), must_fix_received=1 (date_reconcile scrub-swallow), rework=1. Delta 0. Gap: 1 must-fix received. minor.
- **Ivana Horvat** — da#481 clean. Delta 0. clean. none.
- **Kavitha Sundaramurthy** — da#482 clean. Delta 0. clean. none.
- **Oyunbileg Batbayar** — da#483 clean. Delta 0. clean. none.
- **Jean-Claude Habimana** — 0 PRs, must_fix_caught=1 (load-bearing da#454 catch). Delta 0. clean. none.

Forced negative-signal pass: clean (two specific must-fix-received gaps; rest explicit "metrics clean").

### Top 3 Going Well
1. **Clean Phase-9 close: 0 CI-red across 17 PRs; both genuine must-fixes caught at the Opus merge gate** — da#454 `date_reconcile` scrub-swallow (reachable on both idempotent-resume AND from-scratch cutover paths) and #1079 `read_checksums` fail-open aliasing the module-global. Both fixed with regression tests and re-approved fresh. The gate did its job on the two highest-stakes surfaces (a cutover data gater + a shared-state primitive).
2. **Deliberate +20%-floor tooling-debt drawdown worked** — the full main-repo tooling-debt backlog (10) + 4 resolve-stage closeout candidates all landed clean; Phase 9 exits with the tooling debt drained rather than carried to P10.
3. **Content-staleness discipline held through 3 rebase+re-review cascades** (Cluster A/B) — every head move re-staled prior verdicts and drew fresh dual re-review; `content_ts` prevented any stale-verdict merge.

### Top 3 Pain Points
1. **Change-tracker hook pollutes parent `ontology/checksums.json` with gitignored child-repo paths — 131 entries** (deploy 66, data-acquisition 30, ingest-platform 17, others 18 — user-service 7, landing-page 4, isnad-graph 4, design-system 3). Child repos are independently git-tracked + parent-gitignored and must never enter the parent manifest. Recurring, now quantified (handoff estimated "some"; actual 131). **Hook/charter fix candidate — file as P10 tech-debt.**
2. **3 dirty semantic checksums survived into retro** (`charter/issues.md` 20d, `MEMORY.md` 2d, `project_phase9_close_plan.md` never-resolved). Wrapup's ontology step should have reconciled them — process gap. Needs `/ontology-rebuild` (coordinated with the 131-entry child-path cleanup so the rebuild doesn't re-absorb child paths).
3. **Project-2 Wave field missing the `W24` option** blocks board-field sync for 4 wave-24-labeled issues (ingest-platform#131/#134/#135, isnad-graph#1188 — wave-24 direct-to-main work). One-time owner action (Settings → Fields → Wave → add `W24`), then re-run `/board-audit`. Same missing-option class produced the W27-kickoff annunaki noise before the W27 option was added.

### Annunaki-attack (Step 7.6)
**45 genuine errors triaged; all benign.** 18 `block_bare_grep` (hard-block correctly firing), 7 `smart_grep_ontology` (search correctly routed to structural ontology), 5 `validate_review_comment_format` (batched `gh pr comment` with unreadable body — guard correct), 4 `post_label_change_wave_field_sync` ("no option W27" pre-option-add — see pain point 3), 4 `block_stale_tmp_message_file` (retried), 2 `validate_commit_identity` (retried), 2 `post_wave_kickoff_comment` (scope-not-yet-written timing), + 50 low-confidence `annunaki_monitor` pipe-mask-suspect heuristic fires (session-local `| tee` probes, exit 0). No wave-code defect, no production impact, no new automation crosses a threshold. Log archived to `.claude/annunaki/errors.jsonl.bak.20260722-234547`, live log reset, marker written.

### Memory-to-automation audit (Step 7.7)
**No conversions.** No memory files added/modified during wave-27. Marker written.

### Memory decay & size sweep (Step 7.8)
3 files flagged (advisory) — same as W26, all recently touched → **keep**: `project_narrator_chokepoints_enrich.md` (52 KB, 4d — standing consolidation candidate at 3.6× ceiling, carry forward when it goes quiet), `feedback_fixture_makes_guard_assertion_inert.md` (21 KB, 12d), `feedback_sweep_expensive_stage_before_launch.md` (15 KB, 12d).

### Memory content-staleness judge (Step 7.9)
Store healthy: 88 due notes → **73 still-current** (`last_verified` bump candidates), **15 partially-stale** (all false positives — illustrative prose, keep), **0 fully-stale**. No misdirection risk. The 73 `last_verified: 2026-07-22` bumps are clear-cut but advisory; deferred out of this retro PR to keep the diff focused — carry-forward item.

### Promotion audit (Step 7.5)
**0 AUTO · 0 DECIDE · 221 KEPT · 24 SUPERSEDED.** Nothing crossed a threshold (byte-deterministic). Log: `.claude/team/promotion_audit_log/wave-27.md`.

### Proposed Process / Charter Changes (NOT applied — owner decides)
1. **Fix the change-tracker hook to exclude gitignored child-repo paths from parent checksum tracking.** — Rationale: 131 stray child-repo entries in the parent `ontology/checksums.json` this wave; the hook should skip any path under a known child-repo root (or any parent-gitignored path). — Target: change-tracker hook + `charter/hooks/`. File as P10 tech-debt.
2. **`/wave-wrapup` should verify `/ontology-rebuild` ran (0 dirty checksums) before wrap.** — Rationale: 3 dirty semantic checksums survived into retro; add a wrap-gate assertion (or explicit deferral). — Target: `wave-wrapup` skill + `charter/pull-requests/ci-gates.md`.
3. **No annunaki-driven or promotion-driven charter change** — all 45 errors benign, 0 AUTO/0 DECIDE; guards working as designed.

### Fire/hire
None. Retirement trigger fired for no engineer — all ≥3, 0 CI-red across the wave.

### Owner action items (surfaced, not auto-done)
- Add `W24` option to project-2 Wave field, then re-run `/board-audit` (unblocks 4 wave-24 issues).
- Run `/ontology-rebuild` to reconcile the 3 dirty semantic checksums (coordinated with the 131-entry child-path cleanup).
- Phase 9 closes after this retro; next is the #978 cutover (separate owner-gated session, now unblocked — Tier-1 gate da#454 merged), then P10 opens.
