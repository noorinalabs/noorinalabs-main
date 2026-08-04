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

---

## Retrospective: Phase 10 Wave 28 — 2026-07-27

**Theme:** Stop-the-bleeding — Track-0 High defects (security/data-loss/pipeline/perf) + low-risk LOC/perf fill wins + carry-forward closeout. Phase-10 opener. **Merge model: direct-to-main** (per-story PRs merged straight to each repo's main; no wave branch). All PRs merged the prior session; this session was closeout + retro.

### Team Performance
- **12 PRs merged** across 5 repos (main 4, ingest-platform 3, data-acquisition 3, user-service 1, isnad-graph 1). **0 CI-red merges**, **0 review false-positives**.
- **3 changes-requested cycles** (Kavitha 2 on da#502, Weronika 1 on #1126 — all merge-gate catches, fixed + re-CI'd).
- **Counter verification:** final_pr_count 12=12 ✓, changes_requested_cycles 3=3 ✓, top_concentration 17%≈17% ✓. No drift (counters were computed at wrapup directly from PR data, not the broken helper — see pain point 1).
- All 11 work issues closed; meta #1125 closed at wrapup. No wave→main integration PRs (direct-to-main); post-merge deployable workflows green on both fan-in repos; staging promotion green.

### Wave-shape table
| Metric | Value |
|---|---|
| PRs merged | 12 (main 4, ip 3, da 3, us 1, ig 1) |
| CI-red merges | 0 |
| Review false-positives | 0 |
| Changes-requested cycles | 3 |
| Top-implementer concentration | 2 PRs / 12 = 17% (Weronika / Nino tied) |

### Per-Engineer Assessments (mechanical — signals from `wave_28_trust_signals`, computed over the canonical direct-to-main set)
Helper-proposed deltas: Nino +1 (4→5), Oyunbileg +1 (clamped at ceiling 5); all others 0. (Full evidence-anchored table in `trust_matrix.md` § Phase 10 Wave 28 Trust Updates.)
- **Aino Virtanen** — #1130 (ruff pin, unblocked the main gate), prs_merged=1 clean. Delta 0 (ceiling). clean. none.
- **Nino Kavtaradze** — #1127/#1128, prs_merged=2 clean + must_fix_caught=1. Delta +1 → **5**. Top composite. **2nd consecutive +1; owner-veto flag.**
- **Weronika Zielinska** — #1126 + ig#1203, prs_merged=2, must_fix_received=1 (#1126). Delta 0. Gap: 1 must-fix received. minor.
- **Kalinda Ranasinghe** — ip#149 (pip-audit CVE drift, unblocked ip pushes), prs_merged=1 clean. Delta 0 → seed 3. clean. none. (first row)
- **Yusuke Inoue** — ip#150 (Kafka offset-after-checkpoint data-loss fix), prs_merged=1 clean. Delta 0 → seed 3. clean. none. (first row; reassigned from J.Habimana)
- **Léopold Mbongo** — ip#151 (DLQ quarantine + contract test), prs_merged=1 clean. Delta 0 → seed 3. clean. none. (first row; reassigned from J.Habimana)
- **Nikolaos Papadopoulos** — da#503 (producer shape align), prs_merged=1 clean. Delta 0 (ceiling). clean. none.
- **Alejandra Reyes-Fuentes** — da#504 (edge_load_conformance + GRADED_BY), prs_merged=1 clean. Delta 0 (ceiling). clean. none.
- **Kavitha Sundaramurthy** — da#502 (memoize normalize_arabic), prs_merged=1, must_fix_received=2, rework=1. Delta 0 (ceiling; below −1 threshold). Gap: 2 must-fix received. minor.
- **Oyunbileg Batbayar** — 0 PRs, must_fix_caught=2 (both da#502 catches). Delta +1 clamped at ceiling. clean. none.
- **Nadia Boukhari** — us#212 (mechanical merge commit only; implementation credit → Nurul Hakim). Delta 0 → seed 3. clean. none. (first row; attribution caveat)

Forced negative-signal pass: clean (two specific must-fix-received gaps; rest explicit "metrics clean").

### Top 3 Going Well
1. **Clean stop-the-bleeding execution: 0 CI-red across 12 PRs, 5 Track-0 High defects landed.** The wave's purpose — Kafka offset-after-checkpoint data loss (ip#150), DLQ quarantine (ip#151), producer/consumer shape mismatch (da#503), SSO-Bearer replay (us#204), Cypher facet perf (ig#1191) — all merged with ≥1 Opus merge-gate each, both genuine must-fix threads caught at the gate and fixed.
2. **Healthy work distribution.** 12 PRs across 11 people, 17% top concentration — the opposite of the fragility pattern; no single-engineer bottleneck despite the cross-repo spread.
3. **Coupled-fix discipline held.** da#503↔ip#151 (producer/consumer shape) landed together; the ip#150↔#151 `handle_one` conflict was resolved keeping both control flows correct (poison→DLQ→offset advances; send-failure→no commit→reprocess), confirmed by a fresh merge-gate review.

### Top 3 Pain Points
1. **Wave-counter + trust-signal helpers silently return 0/`{}` for direct-to-main waves** (`wave_status.merged_prs` hardcoded to the wave-branch base). Both wave-28 outputs had to be computed manually (counters by hand; trust signals by feeding the canonical PR set into the real `extract_signals`). Filed as **#1131**. Direct-to-main is common since the 2026-06-09 every-wave-merges-to-main directive, so this recurs every such wave.
2. **user-service roster drift (carried wave-27→28, still unresolved).** Nurul Hakim was scoped onto us#204 but is NOT on the user-service roster (Nadia Boukhari, Anya Kowalczyk, Mateo Salazar, Idris Yusuf); the local commit-identity gate blocked him, so the merge commit was attributed to Nadia and the implementor label to Nurul. A parent persona keeps getting scoped onto a child story he cannot commit to. **Fix the wave-scoping / roster-union.**
3. **Generic-prompt pending ledger polluted (~251 stale undecided candidates).** The per-machine volatile pending state was never reset and has accumulated mostly session `.consulted/*.marker` noise + pre-existing charter files — not genuine wave artifacts. The wave-28 checkpoint correctly scoped to the 3 actually-touched hooks (all skipped as perf refactors), but the tracker's candidate set is unusable as-is.

### Annunaki-attack (Step 7.6)
**104 genuine errors triaged; all benign.** 66 `block_bare_grep` (hard-block correctly firing — inflated by this session's own retries + child-worktree greps), 8 `validate_commit_identity` (retried), 7 `stdout:^error` (git-push output heuristic matches — PYSEC/advisory noise on pushes that succeeded), 6 `validate_review_comment_format` (guard correct), 5 `block_git_config` (guard correct), 3 `block_stale_tmp_message_file` (retried), 3 `post_label_change_wave_field_sync` (resolved — W28 option now exists), 2 `Traceback` (session-local `python3 -c "import ..."` probes in child worktrees, empty excerpts), 2 `validate_pr_review`, 1 `smart_grep_ontology`, 1 `block_no_verify` (all guards correct). No wave-code defect, no production impact, no new automation crosses a threshold. Archived 153 records to `.claude/annunaki/archive/wave-28.jsonl`, live log reset, marker written.

### Memory-to-automation audit (Step 7.7)
**No conversions.** No memory files added/modified during wave-28. Marker written.

### Memory decay & size sweep (Step 7.8)
3 files flagged (advisory) — same as W27, all recently touched → **keep**: `project_narrator_chokepoints_enrich.md` (52 KB, 8d — standing consolidation candidate at 3.6× ceiling), `feedback_fixture_makes_guard_assertion_inert.md` (21 KB, 16d), `feedback_sweep_expensive_stage_before_launch.md` (15 KB, 16d).

### Memory content-staleness judge (Step 7.9)
108 notes, 96 due → **30 still-current** (`last_verified` bump candidates), **57 partially-stale** (dead wikilinks / post-merge branch refs — mostly repairable, keep), **9 fully-stale** (deletion candidates, PR-gated + human-approved): `feedback_cross_repo_wave_ref_resolution.md`, `feedback_no_head_in_surface_enumeration.md`, `feedback_role_class_specific_boundaries.md`, `feedback_self_loop_task_replay_glitch.md`, `feedback_verify_3p_integrity.md`, `project_bootstrap_repo.md`, `reference_ssh_topology.md`, `section_ci_tooling.md`, `user_steven.md`. Deferred out of this retro PR to keep the diff focused — carry-forward for a dedicated memory-curation PR.

### Board audit (Step 1.5)
0 orphans; **24 Wave-field drift synced** (historical W21–W24 + P5W4/P5W5 issues with unpopulated Wave fields — not wave-28). W28 option present; no owner action. Board coherent for retro reporting.

### Promotion audit (Step 7.5)
**0 AUTO · 0 DECIDE · 221 KEPT · 24 SUPERSEDED.** Nothing crossed a threshold (byte-deterministic, same as W27). Log: `.claude/team/promotion_audit_log/wave-28.md`.

### Proposed Process / Charter Changes (NOT applied — owner decides)
1. **Make the wave-counter + trust-signal helpers merge-model-aware (#1131 filed).** — Rationale: both silently return empty for direct-to-main waves, forcing manual computation. Needs a `--base main` + canonical-PR-set scoping path (base+timestamp alone over-counts — us#213 was an in-window out-of-scope false positive). — Target: `wave_status.py` / `trust_signals.py` + regression fixture.
2. **Add a `/wave-wrapup` step to reset the generic-prompt pending ledger per wave.** — Rationale: the per-machine volatile pending state accumulated ~251 stale cross-wave/session candidates, making the checkpoint's worklist unusable. — Target: `wave-wrapup` skill Step 12.5 + `generic_prompt_tracker.py`.
3. **Resolve the user-service roster-union so parent personas aren't scoped onto child stories they can't commit to.** — Rationale: recurring wave-27→28; the identity gate correctly blocks the wrong author, but scoping keeps producing the mismatch. — Target: wave-scoping / roster docs.
4. **No annunaki-driven or promotion-driven charter change** — all 104 errors benign, 0 AUTO/0 DECIDE; guards working as designed.

### Fire/hire
None. Retirement trigger fired for no engineer — all ≥3, 0 CI-red across the wave.

### Owner action items (surfaced, not auto-done)
- **Veto check:** Nino Kavtaradze's 4→5 (2nd consecutive +1; mechanical rule permits it as the wave's top composite performer, but it's a ceiling promotion on a 2-PR wave).
- Decide on the 9 fully-stale memory-deletion candidates (Step 7.9) — a dedicated memory-curation PR.
- Fix the user-service roster-union (pain point 2 / carried from W27).
- Set the wave-29 theme on the auto-drafted meta-issue stub, then run `/wave-scope 10 29`.

### ERRATUM — 2026-07-30 (owner-directed correction; original text above left intact)

Two assertions in the wave-28 retro above are **withdrawn**. Both were re-measured
against live state on 2026-07-30. The original wording is deliberately not edited —
the point of record is that these were reported as done.

**E1. "Board audit (Step 1.5): 24 Wave-field drift synced" — DID NOT HAPPEN, and the
figure itself understated the drift by roughly 50×.**

Measured by paginating the *full* project-2 item set (2019 items; the
`gh project item-list --limit 2000` path silently truncates at exactly this
population, which is how the original number was produced):

| | count |
|---|---|
| items carrying a wave-* label | 1,211 |
| …with the `Wave` field **set** | **26** |
| …with the `Wave` field **unset** | **1,185** |

Of the 26 populated, **25 are wave-29** (written by the kickoff / label-sync hooks
during this wave, not by any board audit) and exactly **one** is historical
(`main#423 → P3W10`). So no historical Wave field was synced by the wave-28 retro —
not the 24 claimed, and the true unsynced population is ~1,185, not 24.

Cause remains **undetermined**: GitHub exposes no `ProjectV2ItemFieldValue` history,
so this cannot be reconstructed. `/board-audit`'s hard Step-5 `y` gate aborts without
mutating and is a *plausible* mechanism, not proof. The 1,185 historical items are
deliberately **left unsynced** — they are the evidence. Only the three wave-29 items
missing the field (#1170, #1171, #1175) were set, as current-wave hygiene.

**E2. "Promotion audit: 0 AUTO · 0 DECIDE" — computed over miscategorized input, in
this and at least the four preceding retros.**

`.claude/skills/promotion-audit/helpers.py:212` reads the memory type as flat
`fm.get("type", "project")` and never descends into the `metadata:` block. Measured
2026-07-30 across `.claude/memory/*.md`: **73 of 104 notes (70%) declare
`metadata.type`** — the form CLAUDE.md documents — and are therefore silently forced
to `type=project, promotion_target=none`. `promotion_target` is read the same flat way.

The zero is over invisible candidates, i.e. *"most candidates were never classified"*,
not *"nothing qualified"*. **CLAUDE.md documents the frontmatter shape the tooling
cannot read.** Tracked as **#1006**.

Scope of the correction: the identical `0 AUTO · 0 DECIDE` line appears in the **W24,
W25, W26, W27 and W28** retros (lines 90/114, 158, 218, 282, 360). The reader predates
all of them, so **five consecutive promotion audits are unreliable**, not just this one.
None should be cited as evidence that the promotion pipeline is quiet until #1006 lands
and the audit is re-run.

**E3. Consequence for "Proposed Process / Charter Changes" item 4 — WITHDRAWN.**

Proposal 4 above reads "No annunaki-driven or promotion-driven charter change — all 104
errors benign, 0 AUTO/0 DECIDE". The promotion half of that conclusion rests entirely on
the number E2 just invalidated and is withdrawn. The annunaki half (104 benign) stands.

**Status of the other three W28 proposals, reconciled 2026-07-30:**

| # | Proposal | Vehicle | State |
|---|---|---|---|
| 1 | merge-model-aware wave counters + trust signals | **#1131** | scoped wave-29 (Santiago Ferreira), **not yet implemented** |
| 2 | per-wave reset of the generic-prompt pending ledger | **#1140** | scoped wave-29 (Wanjiku Mwangi), **not yet implemented** |
| 3 | roster-union so parent personas aren't scoped onto child stories | **#1134** | **PARTIALLY DELIVERED** — PR #1154 merged `fbb528e8` (implementer-side membership check). It also made the pre-existing reviewer-side resolution bug **#1162** newly blocking: `validate_matrix_names.py` resolves every slot against `parent_cards ∪ target_repo_cards`, so a charter-permitted reviewer from a *third* child repo resolves against neither and exits 1. Reproduced on merged main 2026-07-30 (wave-28: 4/30 UNRESOLVED — Nikolaos Papadopoulos, Oyunbileg Batbayar, both real data-acquisition personas present in the 78-name `roster.json`). #1162 is scoped into wave-29 and **must land before `/wave-scope 10 30`**. |

So none of the three is closed; one is half-landed and opened a follow-on.

---

## 2026-07-30 — Nadia Khoury + Weronika Zielinska (reviewers, PR #1187) → Nurul Hakim — Severity: moderate

**Mid-wave feedback event (wave-29), recorded ahead of `/wave-retro` so the per-engineer
assessment does not have to rediscover it.**

**What happened.** On PR #1187 (`tech-debt(memory)`: bare-`grep` → `rg`), the implementer
force-pushed during an open `ChangesRequested` cycle. Timeline, re-verified against the
GitHub API on 2026-07-30 before this entry was written:

| When | Event |
|---|---|
| 03:37:44Z | Wanjiku Mwangi — `Approved` |
| 03:42:16Z | Nadia Khoury — `ChangesRequested` (one unmet acceptance criterion) |
| **03:47:03Z** | **`head_ref_force_pushed`** — 4m47s after the blocking verdict |
| 03:55:14Z | Wanjiku Mwangi — re-affirmed `Approved` at new head, flags the process finding |
| 03:55:36Z | Nadia Khoury — `Approved`, records the violation as non-blocking |

**Why it is a violation.** `charter/pull-requests/reviews.md` § Additive Commits on
ChangesRequested prohibits force-push during a ChangesRequested cycle because it resets
the HEAD-SHA anchor the reviewer's `gh api contents/<path>?ref=<sha>` chain depends on.
The rebase escape hatch requires an explicit "rebase OK" from the requesting reviewer,
obtained on the PR thread **before** rebasing. **Severity per that clause: moderate.**

**Verified aggravating facts** (both established independently by the reviewers, both
re-confirmed here):
- No rebase-OK was requested or granted. The thread contains exactly four comments, all
  reviewer verdicts — the implementer posted nothing.
- The rebase was not forced by a conflict: `git merge-tree ee99676 061db3c` resolves
  clean with zero conflicts, so the charter-permitted `git merge origin/main` would have
  worked and preserved the anchor.
- `git merge-base --is-ancestor 061db3c 3e0e5e8f` returns false; the new head is a
  single-parent replay, i.e. a rebase, not the permitted merge-commit path.

**Mitigating facts.**
- Nothing was smuggled in: 10 of the 11 PR files are byte-identical across the two heads
  (`cmp -s`, 10/10), and the diff stayed +14/−14 over the same 11 paths.
- The charter's slow-path remedy was satisfied — both reviewers re-reviewed at the new
  HEAD rather than merging on stale verdicts, and both caught the ancestry break
  themselves rather than accepting the (incorrect) "additive, no force" framing they had
  been given in their briefs.
- The one-line must-fix was applied verbatim and is correct.

**Correction to the prior orchestrator read (recorded deliberately).** The wave-29 session
handoff argued a bare process note would suffice, on the grounds that the implementer
"escalated the norm question himself, corrected immediately, and committed to
merge-not-rebase." **The PR record does not support that.** #1187 carries four comments,
all reviewer verdicts; the implementer self-reported nothing on the thread. Any
self-escalation happened only in his direct report to the orchestrator, which is not part
of the durable record and could not be re-verified. The softer read rested on an
unverified mitigation and is withdrawn in favour of the charter's stated severity. If the
implementer did raise it privately, that is a genuine mitigation and belongs in the
wave-29 retro — but it is not evidence available on the artifact.

**Action taken.** Documented; improvement expected (charter § Severity Levels — moderate).
No merge was blocked, nothing is reverted, and #1187 merged normally at `3a97f928`. The
expectation going forward is the charter's: additive commits during a ChangesRequested
cycle, or an explicit rebase-OK on the thread first.

**Orchestrator process finding, same event.** The reviewer briefs asserted "additive, no
force" as established fact when the orchestrator had not checked. Both reviewers ran the
check anyway and got the correct answer, so the gate held — but it held because the
reviewers distrusted their brief, which is not a control. Captured in memory as
`feedback_patch_id_after_rebase_not_ancestry`; the standing rule is that a brief must
never hand a reviewer an unverified state assertion.

---

## Retrospective: Phase 10 Wave 29 — 2026-08-03

**Theme:** hook/gate hardening + test-suite consolidation. **Merge model:** direct-to-main. **Repos in scope:** `noorinalabs-main`, `noorinalabs-isnad-ingest-platform`.

### Team Performance

| Metric | Value |
|---|---|
| PRs merged | **45** (main 44, ingest-platform 1) |
| Issues closed | 30 |
| CI health | **0 CI-red merges across all 45 PRs** |
| Changes-requested verdicts | **51** (wrapup recorded 49 — corrected, see below) |
| Top-implementer concentration | 9 / 45 = **20%** (Aino Virtanen) — well below the 60% fragility line |
| Tech-debt filed | 14 during the wave, +3 at retro (#1347, #1348, #1349) |
| Carry-forwards | 86 |
| Contributors | 10 |

Wave-29 was, on the evidence, a **strong delivery wave**: a perfect CI record across 45 PRs, and every merged PR's code held up under mutation testing and differential review harnesses. The defects this wave surfaced lived almost entirely in the **artifacts describing** the code, not the code — and the retro found that this pattern extends to the retro's own instruments.

### Status-counter verification (Step 2.5)

| Counter | Claimed | Actual | Disposition |
|---|---|---|---|
| `wave_29_final_pr_count` | 45 | 45 | ✅ matches |
| `wave_29_top_concentration_pct` | 20 | 20 | ✅ matches |
| `wave_29_changes_requested_cycles` | 49 | **51** | ❌ **drift +2** — corrected, `wave_29_counter_corrections` written |

The +2 gap is **not** the edit-in-place measurement conflict the skill documents (that case is recomputed **<** claimed). Recomputed is *higher* than claimed: two genuine blocking verdicts were never counted at all. Root cause filed as **#1347**.

### Per-Engineer Assessments

Full signal tables, corrected values, and the Done Well / Needs Improvement matrix are in `.claude/team/trust_matrix.md` § Phase 10 Wave 29. Summary: 45 PRs across 10 contributors, 0 CI-red merges, top concentration 20%, no fire/hire actions, no retirement trigger. **All scores HELD** — see pain point 1.

### Top 3 Going Well

1. **A perfect CI record at scale.** 45 PRs, 0 red merges, in a wave whose whole subject was rewiring hooks and gates — the surface most likely to break CI. The full local⇄CI parity requirement is doing its job.
2. **Adversarial review found real defects, repeatedly.** Reviewers built false-positive corpora, ran mutation testing, and reproduced findings in real shells rather than reasoning from documentation. #1345 is the wave's most transferable result: a verified instrument triple **plus** green CI was compatible with 20 of 37 tests silently skipping while `OK` printed. Weronika's 17 review catches and Nino's 11 were the backbone of the wave.
3. **Healthy load distribution.** 20% top concentration across 10 people, on a 45-PR wave. No single-owner fragility, and no redistribution needed for wave-30.

### Top 3 Pain Points

1. **The trust-measurement instrument is broken, and it has been since #842 (P6W17).** Three independent defects, all found this retro, all verified against live PR data:
   - **#1347** — `trust_signals.py` silently drops `Changes Requested` (spaced). `(\w+)` captures `"Changes"`, then `== "changesrequested"` fails. It is the **lone holdout**: the merge gate and Hook 4 both accept all three spellings (hardened under #147), so **merge safety was never at risk** — but two real blocking verdicts vanished from the counters.
   - **#1348** — `review_false_positives` is a bare word match. **17 of 17 wave-29 hits were wrong.** The dominant class is reviewers discussing their own *false-positive test corpus* — and the wave's subject matter was shell-classifier false positives, so the detector fired hardest on the wave it was least able to read. Its docstring guarantees "conservative — only a self-marked retraction, never inferred"; a substring search cannot carry that guarantee. Two hits landed on `Request`/`Reply` comments, which are not verdicts at all.
   - **#1349** — the rubric's positive branch is **unreachable**. `clean = not has_negative()` requires zero must-fix received. Across 45 PRs drawing 51 blocking verdicts under 3-6 review heads, **no engineer was eligible for a bump** — in a wave with zero CI-red merges. Correcting #1347 and #1348 still leaves 7 down, 0 up. The rubric penalizes exactly the review intensity the org deliberately increased, and had it been applied, Weronika would have gone 3→1 on the strength of the wave's best review record.

   **Scores are held for every engineer pending the owner's decision on #1349.** Writing deltas from an instrument proven non-functional into a permanent, load-bearing file is the precise failure this wave was themed on.

2. **The error monitor cries wolf — 15% of the wave's entire error log is one false alarm.** `post_label_change_wave_field_sync` emitted `skip_parser_returned_empty` **64 times**, 15% of all 427 genuine records.

   **Correction to this retro's own first reading.** I initially recorded this as a fail-open in which the hook silently skipped syncing the Wave field. The board audit disproved that, and the corrected finding is narrower and different in kind. The parser returns `[]` **correctly** for the unresolved-variable shape (`for n in 1114 1116; do gh issue edit "$n" --add-label wave-28; done` — `"$n"` is not a digit run), and `parse_unresolved_wave_label_edits()` *does* handle that case. **No board sync was missed.** The defect is that the heuristic at `post_label_change_wave_field_sync.py:681-689` treats every empty parser return as a suspected failure without first asking whether the unresolved-variable path already handled it. A secondary factor: `_CANONICAL_WAVE_LABEL_IN_CMD` also matches wave labels inside shell **comments**, not just flag values.

   The cost is inverted from what I first wrote — not a silent miss, but a **loud false alarm that buries real signal**. A monitor whose top class by volume is its own false positive trains readers to skim it, which is how a genuine error goes unread. Recorded here rather than quietly amended because the misreading is itself the wave's thesis: I asserted a mechanism's behavior from its log line instead of from its code, which is exactly what #1348's docstring did.

   Board audit outcome, run this retro: **0 orphans**, **26 Wave-field drift rows** repaired (24 unset-but-labeled spanning W21-W27, 2 populated-with-no-label cleared), read-back verified at 0 remaining. The drift was historical accumulation across seven waves, **not** caused by these 64 records.

3. **Hooks hand-rolling command grammars narrower than `_shell_parse` — four separate instances this wave.** Denominator for all percentages: the **427** genuine records in the wave window (`annunaki_parse.py`, benign traces and low-confidence excluded). Live counts have since drifted up because the triage session itself wrote records; the frozen 427 is the basis.

   | class | n | % | verdict |
   |---|---|---|---|
   | `block_bare_grep` | 86 | 20.1% | working-as-designed friction — 0 defects; `git grep` *is* carved out |
   | `validate_commit_identity` | 78 | 18.3% | working-as-designed friction |
   | `post_label_change_wave_field_sync` | 64 | 15.0% | monitoring false alarm (pain point 2) |
   | `validate_review_comment_format` | 53 | 12.4% | mixed — 46 are the known #1174 prose class, **1 new defect → #1350** |
   | `annunaki_monitor` | 52 | 12.2% | mixed — 35 genuine catches, **17 false → #1354** |
   | `smart_grep_ontology` | 34 | 8.0% | **mis-shelved** — these are *successful* ontology redirects. 8% of the error log is a working feature reporting itself. Cheapest cleanup available. |
   | `validate_branch_freshness` | 16 | 3.7% | as designed |
   | `block_stale_tmp_message_file` | 11 | 2.6% | **defect — 0/11 precision → #1352** |
   | `enforce_ontology_context` | 10 | 2.3% | friction + a charter divergence (below) |
   | tail (7 hooks) | 23 | 5.4% | as designed except `validate_labels` — **0/3 → #1351** |

   **Correction to this retro's second misreading.** I recorded "52 records where the Annunaki monitor itself errored," reasoning that an error monitor which throws is blind when it matters. That is wrong in both directions. The monitor **did not throw once**: `hook:` is the *writer-attribution* field, not "the hook that failed," and all 52 records carry `exit_code: 0`, `confidence: high`, `category: masked-failure` — the monitor working correctly, catching failures a pipe (`| head`, `|| true`) had masked behind a zero exit. 35 of the 52 are genuine catches. And the `git show b290d611` cluster is **17 records, not 11**, all from one test (`test_wave_status.py::BaseVsHeadDifferential`) whose `git show` of a historical commit failed under `actions/checkout`'s shallow clone — **already fixed in-wave** at `ci.yml:148-158` (`fetch-depth: 0`).

   The real defect there is #1354: `_is_content_display` omits `gh run view --log-failed` and `rg`-over-a-saved-log, and disqualifies any command containing `2>&1` — which a log read requires. So *reading a CI log* mints high-confidence "masked-failure" records. **That class scales with how hard a failure was to debug**, systematically over-weighting already-solved problems in the artifact meant to surface unsolved ones.

   The genuine defects — #1350 (`_PATH_TOKEN` ends at whitespace, so a structurally-required trailing `;` on `--body-file` fail-closes a valid verdict), #1351 (`extract_labels` mints `meta-issue)` from `$( )` capture and `c` from a clustered `-lc`; one of the 3 blocked the creation of #1150 itself), and #1352 (30s mtime threshold, every path under the *current session's* scratchpad, and the documented `touch` workaround is defeated because PreToolUse stats before the command runs) — are all the **same class**: a hook hand-rolling a command grammar narrower than `_shell_parse`, in hooks that **#1150 already names as un-audited**. Wave-29 filed individual instances four times; that demonstrably does not stop the class. #1150's own acceptance criterion — a shared conformance suite that fails CI when a hook hand-rolls a parser — is the only thing that prevents instance 7.

   Separately, `enforce_ontology_context` revealed a **charter divergence worth a line rather than a ticket**: 2 of its 10 blocks carried the `/ontology-librarian` instruction and were blocked anyway, because CLAUDE.md documents a transcript-scanning enforcement model while the hook demands the librarian *output* pasted under a literal `## Ontology Context` heading. Two enforcement models documented for one rule.

### Proposed Process Changes

1. **Verify counters before narrating them, not after.** Rationale: wrapup wrote 49 and the orchestrator repeated it as authoritative. Step 2.5 caught it — but only because it is mandatory. The generalizable rule is `feedback_state_the_denominator_with_the_number`, written *during* this wave and then not applied to the wave's own bookkeeping.
2. **A guarantee stated in a docstring must be tested, or it must be deleted.** Rationale: #1348's "conservative — never inferred" is a promise the mechanism structurally cannot keep, and it went unchallenged for 12 waves because the prose read as a specification. This is the wave's own thesis turned on its own tooling — see `feedback_prose_guarantee_vs_mechanism`.
3. **A shared vocabulary needs one owner, not N private copies.** Rationale: #147 hardened the verdict vocabulary in two places; `trust_signals.py` arrived later and re-implemented it wrong. #1081 already established the shared-entry-point pattern for exactly this. Every new consumer of the verdict vocabulary must route through it.
4. **Batch review findings during a wave tail.** Rationale: the #1333 push freeze — 5 heads in 20 minutes staled 3 verdicts mid-authorship. Orchestrator dispatch failure, already recorded in the wave-29 handoff; restated here because it materially inflates one engineer's rework count.
5. **A hook must distinguish "I could not evaluate this" from "I evaluated it and found nothing."** Rationale: the 64× `skip_parser_returned_empty` records and the 25× `skill_invocations=0 < 5` lines are both a *cannot-evaluate* state rendered as a *benign-result* state. Silence and success must not look identical from outside. (Restated from the original "must say so, not skip" after the board audit showed nothing was actually skipped — the defect is the reporting, not the skipping.)

6. **Ship the #1150 shared parser-conformance suite; stop filing instances.** Rationale — and this is the wave's highest-priority recommendation. #1350, #1351, and #1352 are each "a hook hand-rolls a command grammar narrower than `_shell_parse`," each in a hook **#1150 already names as un-audited**, each found by measurement rather than inspection, and each hard-blocking correct work. One of the three (#1351) blocked the creation of **#1150 itself**. Wave-29 filed individual instances four separate times; that demonstrably does not stop the class. #1150's own acceptance criterion — a shared conformance suite that fails CI when a new hook hand-rolls a parser — is the only thing that prevents instance 7. If exactly one thing ships first, make it **#1352**: 100% false-positive rate, on the `gh pr create` critical path, and the fix is an exemption for the session-scoped scratchpad path.

7. **Reclassify `smart_grep_ontology` out of the error log.** Rationale: its 34 records (8.0% of 427) are *successful* ontology redirects — a working feature reporting itself as an error. Cheapest single cleanup available, and it directly improves the signal-to-noise of the artifact every other finding is read from.

8. **Reconcile the two documented enforcement models for the ontology-context rule.** Rationale: CLAUDE.md documents transcript scanning; `enforce_ontology_context` demands the librarian *output* pasted under a literal `## Ontology Context` heading. 2 of its 10 blocks hit briefs that carried the librarian instruction and were blocked anyway. One rule, two specifications — a charter line, not a ticket.

### Retro-Filed Issues

| # | Title | Source | Labels |
|---|---|---|---|
| #1347 | `trust_signals.py` silently drops `Changes Requested` (spaced) verdicts | Step 2.5 counter check | tech-debt, bug, phase-10 |
| #1348 | `review_false_positives` is a bare word match: 17/17 wrong in wave-29 | Step 4 assessment | tech-debt, bug, phase-10 |
| #1349 | Trust rubric's positive branch is unreachable under multi-head review | Step 5 trust matrix | tech-debt, process, phase-10 |
| #1350 | `validate_review_comment_format._PATH_TOKEN` stops only at whitespace — a trailing `;` on `--body-file` fail-closes a valid verdict | Step 7.6 annunaki | bug, tech-debt, phase-10 |
| #1351 | `validate_labels` mints garbage labels from `$( )` capture and clustered `-lc`; 3/3 wave-29 blocks false | Step 7.6 annunaki | bug, tech-debt, phase-10 |
| #1352 | `block_stale_tmp_message_file` 30s threshold — 0/11 precision, `touch` workaround defeated by PreToolUse ordering | Step 7.6 annunaki | bug, tech-debt, phase-10 |
| #1354 | `annunaki_monitor._is_content_display` misses `gh run view` / `rg`-over-a-log — one CI diagnosis minted 17 false records | Step 7.6 annunaki | bug, tech-debt, phase-10 |
| #1355 | Promotion AUTO tier unreachable: `skill_invocations` counts the not-yet-created target; 0/25 gated sections can qualify | Step 7.5 promotion audit | tech-debt, bug, process, phase-10 |

Filed deliberately **without** a wave label: `wave-30` does not exist until wave-30 kickoff, and a `wave-29` label would create false drift against that wave's labelled==scoped invariant.

**Not filed, deliberately.** Three `post_wave_kickoff_comment` records report *"No assignment row found in `wave_29_scope` tiers"* for #1156, #1210, #1211 — all three carry the `wave-29` label and have zero kickoff comments, i.e. they entered wave scope without a `/wave-scope` assignment row, so no reviewer pairing and no kickoff comment. All three completed anyway, so no harm materialized. This is a `/wave-scope` reconciliation gap rather than a defect, and it belongs in scope reconciliation, not an issue.

**A sibling finding was raised and then retracted after verification.** Two `post_wave_kickoff_comment` `skip_unresolved_issue_number` records were initially read as a second silent-miss fail-open by analogy to pain point 2. They are not: the hook detected the unresolved `"$n"` shape, correctly declined, **named its own remediation** (`.claude/lib/kickoff_sweep.py`), and the sweep then ran — #1140, #1149, #1151, #1152 each received a Wave 29 Kickoff comment 8 seconds later. Working as designed end to end. Recorded because the retraction is the point: the same analogy that produced my pain-point-2 error nearly produced a second one, and only re-verification caught it.

### Memory hygiene (Steps 7.8 + 7.9)

Two orthogonal sweeps ran: `memory_budget.py --staleness` (size/age) and the `/memory-judge` content pass.

**Size/age (advisory, 121 topic files, 5 flagged):**

| file | size | last touch | disposition |
|---|---|---|---|
| `project_narrator_chokepoints_enrich.md` | 52,024 B | 16d | **Archive candidate** — Phase-9 narrator/data-quality work, superseded by the Phase-10 focus. 3.6× the soft ceiling and the largest file in the store. Recommended for `.claude/memory/archive/`; deferred to an explicit owner decision, since archiving is never automatic. |
| `feedback_fixture_makes_guard_assertion_inert.md` | 22,005 B | 1d | **Keep** — written this wave, actively referenced. Consolidation candidate later. |
| `feedback_gh_cli_gotchas.md` | 18,348 B | 1d | **Keep** — age is edit-recency, not reference-recency; this is a high-recall standing convention. |
| `feedback_corpus_misses_its_constant_dimension.md` | 16,639 B | 0d | **Keep** — written today. |
| `feedback_sweep_expensive_stage_before_launch.md` | 15,344 B | 24d | **Keep** — marginally over ceiling, still live. |

**Content staleness (`/memory-judge`, 107 notes examined — every note lacking `last_verified`):**

| classification | count |
|---|---|
| Still-current | 97 |
| Partially-stale | 0 |
| Fully-stale | 0 |
| Already carrying `superseded_by` | 10 |

**Zero false positives this pass** — a material improvement on the wave-28 run, where all 9 "fully-stale" flags were wrong (examples, child-repo refs, external URLs, env vars misread as dead claims). The calibration warning written into the wave-29 judge brief, derived from that failure, appears to have worked. `feedback_memory_judge_overflags_fully_stale` remains accurate as a standing caution and should not be retired on one clean run.

The 10 `superseded_by`-marked notes remain queued for a human-approved prune diff; no deletions were made, per protocol.

### Promotion audit (Step 7.5) — and a fourth unreachable gate

`/promotion-audit` for wave-29 reports **0 AUTO · 0 DECIDE · 243 KEPT · 24 SUPERSEDED/ALREADY-PROMOTED** — nominally a clean steady state. It is not. Checking *why* `skill_invocations=0` recurred throughout the log produced **#1355**.

`skill_invocations` is `0` in **220 of 220** occurrences across every wave audit log ever written, and AUTO promotions have fired exactly once in ~20 recorded waves (`p2-wave-5`, and that predates the main#690 blank-slug guard, i.e. it is from the mis-fire era).

The counter itself is healthy — 21 of 24 skills on disk return non-zero (`wave-scope` 97, `wave-kickoff` 74, `wave-wrapup` 74, `wave-retro` 55). It is being handed the wrong argument. `run.py:253` passes `section.promoted_to` — **the target artifact the section would be promoted INTO**, which by definition does not exist yet. Counting invocations of a not-yet-created skill is always 0.

Measured against the real charter: 114 sections, 34 declaring a real `promotion_target`, of which **25 target `skill`** — the only population the invocation gate reaches — and **all 25 have a blank `promoted_to`**. So **0 of 25 can ever qualify**, exactly matching the 25 `skill_invocations=0 < 5` lines in the wave-29 log. (The other 9 target `hook`, an invalid transition the pipeline rejects earlier — charter sections promote only to skill — so they never reach the gate. My first pass wrote "32 of 34," conflating those two populations; corrected on #1355, and it is the same denominator error this wave keeps producing.)

For **memories** the gate is different and works as intended: `retro_citations` against a threshold of 5, which genuinely accumulates. The two wave-29 memories with the strongest narrative evidence — `feedback_prose_guarantee_vs_mechanism` and `feedback_state_the_denominator_with_the_number` — classified KEPT for mechanical reasons, not judgment: neither sets `promotion_target`, and both sit at `retro_citations=1`. Citation count, not this-wave severity, gates promotion by design. Making either eligible is a deliberate human act (set `promotion_target: charter`), and I did not override the classifier to force it.

The main#690 blank-slug guard is correct and must stay; the defect is that it renders an *unconfigured target* as `Invocation threshold not met; wait for more operator-invoked runs`, telling the reader to wait for something that cannot arrive.

**This is the fourth instance of one failure shape in a single wave**, which is the wave's real finding:

| # | artifact | the shape |
|---|---|---|
| #1348 | `review_false_positives` | docstring guarantees a conservatism the mechanism cannot implement |
| #1349 | `score_delta` | the passing branch is unreachable in practice |
| #1352 | `block_stale_tmp_message_file` | 0/11 precision; the documented workaround is defeated by hook ordering |
| #1355 | `skill_invocations` | the gate measures the wrong side of the transition; 0/34 can qualify |

Each is a mechanism that **reports success or benign inaction while being incapable of the outcome it describes**. None would fail a test that only asserts "it runs without error"; all four survived because the passing state and the broken state are observationally identical from outside. That is the generalizable lesson of wave-29, and it applies to the process tooling exactly as it applied to the shell classifiers the wave was themed on.
