# Feedback Log — Phase 6 archive

> Archived byte-for-byte from `.claude/team/feedback_log.md`
> at phase close (#964, meta #960), preserving original file order. Do not edit —
> append-only history; new entries go to the live file for the current phase.

---

## Retrospective: Phase 6 Wave 1 — Memory & code-over-prose — 2026-06-21

### Team Performance
P6W1 closed clean. **27 parent PRs** (in-scope `[noorinalabs-main]`) + **6 emergent child-repo cspell-parity PRs** (#684 rolled beyond the parent-only declared scope). **0 CI failures, 0 reviewer Changes-Requested cycles, 0 must-fix-after-merge.** All canonical scope (#732/#733 memory leanness, #734/#735 code-over-prose, #684/#706/#704 TD intake) delivered + closed. Annunaki: **0 genuine failures** (log was 50 exit-0 + 13 exit-None false-positives — the exact class #729 targets).

### Wave-shape table
| Metric | Value |
|--------|-------|
| Parent PRs merged (in-scope) | 27 |
| Emergent child cspell-parity PRs | 6 (ig#1122, us#189, deploy#487, da#211, ingest#113, ds#129) |
| Reviewer Changes-Requested cycles | 0 |
| CI failures across wave | 0 |
| Tech-debt / follow-ups filed | #797, ig#1123, #798(→#799 resolved), #744 unblocked |
| Top-implementer concentration | 22/27 = **81%** A.Virtanen (theme-fit — framework/standards domain) |
| Staging promotion | overridden (no deployable surface) |

### Per-Engineer Assessments
- **Aino Virtanen** — 22 parent PRs (cspell parent fix, mermaid gate, branding, office-epoch, + the #799 stranding reconciliation). All green, 2-reviewer-approved. The #799 reconciliation was exemplary: handled the wave-vs-main test-file divergence (main's newer #748 structural-parse + parity table) by extending rather than copying. Severity: none (strongly positive). Theme-fit concentration, not fragility.
- **Luciana Ferreyra** — design-system #129. **Standout.** Verify-before-trust caught the brief's false premise (the repo *did* have a sync gate that simply didn't classify cspell — the exact #684 blind spot), and rather than shipping mirror-only behind a follow-up, extended to a full parity fix. Then independently recovered a silently-dropped CI trigger via close/reopen (working around the gh-pr-edit projects-classic error). Severity: none (strongly positive).
- **Linh Pham** — isnad-graph #1122. Clean full-fix; surfaced two latent local⇄CI parity gaps (actionlint `if:false`, no CI job running `.claude/lib/tests/`) → filed as #1123. Positive.
- **Mateo Salazar** — user-service #189. Clean; flagged the known `build`-kind false-match on unscoped sync-gate invocation. Positive.
- **Lucas Ferreira** — deploy #487. Clean; correctly diagnosed + ignored a self-loop task-replay glitch. Positive.
- **Fatima Bensalah** — ingest-platform #113. Clean full-fix; also correctly identified the self-loop replay. Positive (first numeric entry).
- **Tarek Mansour** — data-acquisition #211. Clean full-fix (went idle without a written report, but PR was green and complete). Positive (minor: report hygiene).
- **Reviewer corps** (Nadia, Wanjiku, Santiago, Jelani, Anya, Idris, Weronika, Nurul, Bjørn, Petra, Jean-Claude, Oyunbileg, Keanu, Kofi) — Hook-4-compliant verdicts, **zero rubber-stamps**. Notable independent diligence: Wanjiku's decisive completeness re-diff on #799 (proved exactly 5 files stranded, no more), Oyunbileg's + Petra's non-tautology test checks, Nurul's regex-coverage check, Kofi's docs-lens glob check.

### Top 3 Going Well
1. **Clean parallel fan-out** — 8 PRs through full lifecycle, 0 CI failures / 0 reviewer CR / 0 must-fix-after-merge. Hub-and-spoke spawn model held under load.
2. **Verify-before-trust earned its keep twice** — Luciana caught the design-system gate premise error; the wrapup reachability gate caught the stranding. Quality culture is real, not ceremonial.
3. **Reviewers reviewed** — independent completeness/tautology/coverage checks, not approvals-by-assertion.

### Top 3 Pain Points
1. **Mixed merge model → stranding.** P6W1 merged #704/#706/#734/#735 to the wave branch but the doc batch + cspell/mermaid direct to main, and **never opened the wave→main PR** — stranding 5 net-new #734/#735 deliverables off main. Caught only at wrapup by the Step 11.5 reachability gate; resolved via #799. The gate worked, but the stranding should have been impossible / caught earlier.
2. **Wave-key collision (#683) corrupted wrapup markers.** `wave_1_*` keys aren't phase-namespaced, so stale P4W1 completion markers (annunaki/memory/wrapup timestamps, final_pr_count=4, stg=success) masqueraded as P6W1 until overwritten. This is the *third* consecutive retro to flag #683.
3. **Silent CI-trigger drop** (design-system #129) — GitHub dropped the `synchronize` event (zero runs on the new head); recovered via close/reopen. Environmental, but a merge on "no checks reported" would have been a green-looking gap had it not been verified.

### Proposed Process Changes
1. **One merge model per wave, recorded at kickoff** — Rationale: the mixed model is what stranded #734/#735. A wave should be all-direct-to-main OR all-wave-branch, decided at `/wave-kickoff` and recorded in `cross-repo-status.json`; a mid-wave check (session-start) flags any wave-branch commit not reachable from main without an open wave→main PR, so stranding surfaces within hours, not at wrapup.
2. **Bump #683 (phase-namespaced wave keys) to next-wave must-fix** — Rationale: flagged in P5W3, P5W4, and now P6W1; it actively corrupted this wrapup's markers. The per-phase reset (#699) did not prevent the collision. Durable fix is phase-namespaced keys (`p6_wave_1_*`).
3. **Treat "no checks reported" as a hard not-ready state** — Rationale: #129's dropped trigger produced zero runs, which is not the same as green. A merge-readiness check should assert `statusCheckRollup` is non-empty AND all-success, never empty.

### Proposed Charter Change
- **Single merge model per wave** under `charter/pull-requests.md` (or wave-lifecycle): a wave declares its merge model at kickoff; mixing wave-branch and direct-to-main merges within one wave is prohibited because it strands wave-branch work when the wave→main PR is forgotten (P6W1 #734/#735 → #799). Pair with strengthening the reachability gate to fire mid-wave, not only at wrapup.

### Promotion Audit (Step 7.5)
0 AUTO · 0 DECIDE · 210 KEPT · 19 SUPERSEDED — nothing crossed a promotion threshold this wave (steady state). Log: `.claude/team/promotion_audit_log/p6-wave-1.md`.

### Update (P6W2, 2026-06-21) — wave-key collision RESOLVED, but via Design B not phase-namespacing

Carry-forward item #2 above ("phase-namespaced wave keys `p6_wave_1_*`") was reframed by an owner design-input comment on #804 (2026-06-21): instead of phase-namespacing the key, make the wave id a **single global monotonic counter** that never resets per phase (Design B). A global id is never reused, so the P5W2↔P6W2 collision class cannot arise — and the `/wave-start` §5a reset disappears entirely (nothing to reset) rather than being made to fire correctly. Landed in `A.Virtanen/0804-durable-wave-key-identity`: new `.claude/lib/wave_seq.py` allocator, phase demoted to derived display fields (`wave_{X}_phase` + `wave_{X}_phase_ordinal`), `wave_key_reset.py` deleted, grandfather migration (next global wave = 16). The phase-agnostic `wave-{X}` LABEL rename is split to a follow-up (labels already carry the phase, so they never collided — not the bug). See memory [[project_wave_key_cross_phase_collision]].

**Process pain (logged):** the work was nearly lost to a shared-worktree collision — five agents were cycled through `.claude/worktrees/0728-ontology-graphify-spike` on different branches, and a peer `git checkout` wiped uncommitted edits ([[feedback_cwd_collision_cross_spawn]]). Recovered into a dedicated worktree. Reinforces: one cwd per agent, commit/push fast.


---

## Retrospective: Phase 6 Wave 2 — 2026-06-22

**Theme:** durable wave-key fix (#804) · persona/ontology architectural revisits · retro mechanization.
**Repos in scope:** noorinalabs-main, noorinalabs-isnad-graph, noorinalabs-user-service.

### Team Performance (mechanical, verified at retro)
- **PRs merged:** 15 (main 10, isnad-graph 3, user-service 2). All 3 wave→main PRs merged; reachability + staging gates passed.
- **CI-red merges:** 0.
- **Changes-requested cycles:** 1 (Weronika → Aino, #811 — `lifecycle.md` canonical-doc drift; caught + fixed in one pass).
- **Top-implementer concentration:** 1/15 = **7%** (vs P6W1's 81%). 15 implementers, 1 PR each — deliberate de-concentration, theme-fit. **Going-well**, not fragility.
- **Counter verification:** `final_pr_count` 15 ✓, `top_concentration_pct` 7 ✓, `changes_requested_cycles` 1 ✓ (authoritative-historic). No drift; no `counter_corrections` entry needed.
- **Owner decisions recorded:** #727 persona → **B** (+ self-improving cards §4a + mechanical scoring §4b) → exec #819; #728 ontology → **C × T2** (Hybrid × Distributed+overlay) + isolated-branch tooling bake-off → exec #820; #804 wave-key → grandfather migration (next id wave_16).

### Per-Engineer Assessments (evidence-anchored)
See trust_matrix.md § Phase 6 Wave 2 for the full table. Summary: 14 of 15 held steady (1 clean PR, 0 must-fix, 0 CI-red each = baseline); Weronika 4→5 on two concrete signals (deepest spike + only review catch); Aino held at 5 with a named 1-rework-cycle gap (not buried under "None").

### Top 3 Going Well
1. **De-concentration worked** — 7% top-implementer vs 81% in W1; 15 engineers each carried one clean PR. The W1 fragility-concentration pain point was directly addressed.
2. **Zero CI-red merges** across 15 PRs and 3 wave→main merges, despite heavy environmental friction.
3. **Both architectural revisits decided cleanly** (#727 B, #728 C×T2) with measured evidence, plus the durable wave-key fix (#804/#811) — the headline tech-debt — landed.

### Top 3 Pain Points
1. **Environmental friction dominated the wave.** Four distinct blockers: API 529 overload (forced staggered re-spawn), cwd-collision on parallel `isolation:worktree` spawns, `/tmp`-rooted worktree pre-push false-fails (#817), and the `test_pre_commit_ci_sync` parent-checkout drift (#816) that blocks all local direct-to-main pushes. All worked around (PUT-contents, non-/tmp worktrees) but each cost real time.
2. **Ontology rebuild skipped at wrapup** — 20 dirty files remain in `checksums.json` (wrapup pruned 73 stale paths but did not run a full `/ontology-rebuild`). Process gap: wrapup Step is being deferred.
3. **Annunaki backlog unprocessed** — 63 genuine errors captured (54 from this wave's troubleshooting churn), `/annunaki-attack` not yet run. Deferred to the next session.

### Proposed Process Changes (await owner ratification — NOT applied)
1. **Adopt §4b mechanical trust scoring as the retro default (#819).** Rationale: demonstrated this wave — 14/15 held steady vs 15/15 ratcheting under the old model. The owner already decided the direction; this retro is its dry-run.
2. **Codify the non-/tmp worktree rule (#817).** Rationale: `/tmp` worktrees false-fail two pre-push gates (tmp-path pytest + snap-mmdc mermaid). Memory banked; promote to charter/skill so it stops recurring.
3. **Fix or formally bless the #816 workaround.** Rationale: `test_pre_commit_ci_sync` fails in the parent checkout (child repos present) but passes in CI/agent worktrees, blocking local main pushes. Either fix the test's environment assumption or make PUT-contents the documented canonical path for main-targeting bookkeeping/retro writes.
4. **Enforce `/ontology-rebuild` at wrapup.** Rationale: 20 dirty files leaked past wrapup; the rebuild keeps getting deferred.

### Deferred to next session (handoff)
- `/annunaki-attack` on the 63-error backlog
- `/promotion-audit` (P6W2)
- memory-to-automation audit
- `/wave-scope 6 16` once the owner sets the wave_16 theme (stub auto-drafted this retro)

## Retrospective: Phase 6 Wave 16 (global) — Framework / gate hardening — 2026-06-23

**Theme:** burn down framework/toolchain tech-debt — the pre-push/CI-parity gates actively creating friction (local push-to-main blocked, `/tmp`-worktree false-fails, stale-base session starts). Heavy-TD floor (final-but-one framework wave before W17 architectural exit). Owner-set 2026-06-22.
**Repos in scope (counters):** noorinalabs-main only (wave-branch model). Child rollout of #744/#718 landed via direct PRs to each child's own main (counted separately below).

### Team Performance (mechanical, verified at retro)
- **Parent PRs merged:** 7 (all main, via wave branch → main #834). #744/#718 child rollout: 5 child PRs (da #213, ingest #115, lp #154, deploy #491+#489); isnad-graph/user-service/design-system already-done on origin (no-op).
- **CI-red merges:** 0. (deploy #489 E2E flaked once — `httpx.ReadError` on `test_verification` after rebase — re-ran green; not a real regression.)
- **Changes-requested cycles:** parent **0** (counter authoritative); child **1** (both da reviewers on #213 — a real bug: the hook `files:` regex `^tests/.*/fixtures/…` missed the top-level curated corpus; Tarek widened to `^tests/(.*/)?fixtures/…`, verified staged-edit fires).
- **Top-implementer concentration (by commit identity):** 3/7 = **43%** (Wanjiku Mwangi). **Caveat — true concentration is ~100%:** this was an orchestrator-executed framework wave; the 7 parent PRs carry persona commit identity (`-c` flags) but were driven directly by the orchestrator (the throttle-takeover / direct-framework-execution pattern). 43% understates that. **Theme-fit, not fragility** — framework/gate work is orchestrator-owned by nature — but named explicitly so W17 (architectural execution) is planned as real distributed implementer work, not more orchestrator-solo.
- **Counter verification:** `final_pr_count` 7 ✓ (= 7 merged parent PRs), `changes_requested_cycles` 0 ✓ (parent-scoped; child da#213 CR is out-of-scope for the parent counter and stands as context), `top_concentration_pct` 43 ✓ (3/7). No drift; no `counter_corrections` entry needed.
- **Ontology:** current (0 dirty) — wrapup ran the rebuild; the P6W2 "20 dirty leaked past wrapup" pain point did not recur.

### Per-Engineer Assessments (evidence-anchored)
See trust_matrix.md § Phase 6 Wave 16 for the full table. Summary (commit identity):
- **Aino Virtanen** — #833 (#816 root-fix: decoupled `test_pre_commit_ci_sync` from stale child checkouts — the wave's most consequential PR, unblocked local push-to-main, verified by the wrapup push succeeding) + #829 (#663 gh-parser invariant extended to `gh workflow`/`gh api`). Two clean framework PRs; #833 was the inverted-premise root-fix chosen over the expedient #826 (closed). At ceiling (5) — hold with named done-well.
- **Wanjiku Mwangi** — #825 (#822 sync_main allowlist + loud stale-base refusal), #827 (#672 producer-parity checklist), #830 (#810 phase-agnostic wave-label scheme). 3 clean PRs, 0 must-fix. Baseline — hold.
- **Santiago Ferreira** — #824 (#817 mermaid render dir → `$HOME`). 1 clean PR. Baseline — hold.
- **Nadia Khoury** — #828 (#745 liveness/throttle mechanization). 1 clean PR. Baseline — hold.
- **Tarek Mansour** (da) — #213. 1 caught-and-fixed rework cycle (hook regex too narrow). The review system working as designed; not a decrease under §4b. Named gap, hold.
- **Lucas Ferreira** (deploy) — #491 (E2E harness fix: OAuth fragment-vs-query + 429 rate-limit, deploy-side only, no cross-roster contract change) + #489 (base-pin). 2 PRs, 0 must-fix. Baseline — hold.
- **Bjørn Henriksen** (#115), **Kofi Mensah-Williams** (#154) — 1 clean PR each. Baseline — hold.

### Top 3 Going Well
1. **The wave closed three of P6W2's own four pain points.** #816 (local push-to-main block) fixed at root via #833 — *verified* by the wrapup push landing on origin; #817 (`/tmp`-worktree false-fail) fixed via #824; the annunaki backlog was processed this retro (not deferred a third time). The framework-friction theme delivered on its premise.
2. **Honest inverted-premise handling.** Two scoped issues had stale premises discovered at execution — #816 (root cause was stale local child checkouts, not the assumed cspell map-drift; expedient #826 closed, root-fix #833 done) and #705 (targeted the already-deleted `wave_key_reset.py` from #804; closed not-planned, descoped). Both surfaced and corrected rather than implemented-as-briefed.
3. **Annunaki + memory audits actually ran at retro** — first wave where the #344 co-location worked as intended (W14/W15/P6W2 all deferred them). 47 captures triaged: 0 unresolved failures.

### Top 3 Pain Points
1. **Scope-time premise rot.** #705 (deleted-file target) and #816 (inverted root cause) both slipped to execution before their stale premises were caught. `/wave-scope` does not verify that a scoped issue's named file/symbol still exists or that its premise still holds at origin HEAD. Reinforces [[feedback_verify_diagnosis_before_delegating]] + [[feedback_pre_spawn_verify_file_exists]] — but at *scope* time, not just spawn time.
2. **Meta-wave concentration is structural and un-distributed.** Framework/gate work is orchestrator-executed by nature, so persona commit-identity (43% top) is bookkeeping, not real distribution. Acceptable here; flagged so W17 is planned as genuine implementer fan-out.
3. **Annunaki monitor over-captures rc=0 output.** 40 of 47 captures are `exit_code==0` records that pattern-matched `stdout:^FAILED` — pytest "FAILED" lines surfacing through `… | tail` (rc-masking, the [[feedback_push_pipe_masks_rejection]] class) or benign demo output — logged with an empty `hook` field, inflating the count. The 5 `pretooluse_block` + 2 `posttooluse_event` records are hooks working correctly, not errors. Follow-up filed to gate stdout-pattern matches on nonzero rc (or down-rank/relabel rc=0 pipe-mask captures).

### Process Changes — ALL ACCEPTED (owner-ratified 2026-06-23), tracked for implementation
1. **Add a scope-time premise-verification step to `/wave-scope`.** For any scoped issue naming a concrete file/symbol/path, assert it exists at origin HEAD (`git cat-file -e origin/main:<path>`) and surface a STOP if absent. Rationale: #705/#816 both wasted execution cycles on rotted premises this wave. → **#837**.
2. **Tighten the annunaki monitor's rc=0 handling.** Suppress (or relabel as `pipe-mask-suspect`) stdout-pattern matches when `exit_code==0`; populate the `hook` field so counts aren't dominated by "unknown". Rationale: 85% of this wave's captures were rc=0 noise. → **#835**.
3. **Promote the push/merge-pipe-mask rule to a hook (#1044 memory).** A PostToolUse check flagging `git push|gh pr merge … | tail/head` (rc-masking) is a concrete DECIDE-tier candidate — the annunaki data this wave is direct evidence the class recurs. Rationale: surfaced by the memory-to-automation audit (Step 7.7). → **#838**.

> Owner ratified all 3 on 2026-06-23. Implementation tracked via #837/#835/#838 (labeled tech-debt+process, boarded) — to be folded into a wave at `/wave-scope` (W17 +20% TD intake pool). Direction accepted; code lands via the normal PR path.

### Audits run this retro (markers written)
- **/annunaki-attack** (Step 7.6): 47 captures triaged — 40 rc=0 false-positives (historical worktree dev-iteration, all merged green), 5 `pretooluse_block` (enforcement working), 2 `posttooluse_event`. **0 unresolved failures, 0 fixes needed.** 1 monitor-tuning follow-up filed.
- **Memory-to-automation audit** (Step 7.7): one DECIDE-tier candidate surfaced — [[feedback_push_pipe_masks_rejection]] → PostToolUse pipe-mask hook (see Proposed Change #3). Remaining memories are already-enforced or judgment-class; no auto-promotions.

### Handoff to W17 (#823 — FINAL, phase exit)
- W17 = architectural execution: #819 (persona Option B) + #820 (ontology C×T2). Meta-issue #823 exists with a set theme → `/wave-scope 6 17` is the next lifecycle step.
- Open follow-ups carried (not W16): #831 (status-drift), #832 (stale child checkouts), + the annunaki monitor-tuning follow-up filed this retro.

---

## Retrospective: Phase 6 Wave 17 — 2026-06-25 (Architectural execution + phase exit; FINAL wave of Phase 6)

### Team Performance
14 per-issue PRs merged across 2 repos (13 noorinalabs-main + 1 isnad-graph), **9 distinct implementers**, top-concentration **28%** (Weronika 4/14). Both wave→main integration PRs merged (main#861 producer, isnad-graph#1130 consumer, producer-before-consumer ordering). **0 CI-red merges, 0 must-fix received, 0 rework cycles.** Counters verified mechanically (14 / 0 / 28-29%; the 1pt is a round-vs-floor convention diff, within tolerance). Phase 6 exits here.

### Per-Engineer Assessments (mechanical — trust_signals.py score 6 17)
- **Weronika Zielinska** — #845/#853/#854/#859; delta +1; the wave's deepest architectural work (bake-off → owned C×T2 generator). clean: 0 CI-red, 0 must-fix.
- **Bereket Tadesse** — #860/#846; delta +1; aggregator + caught the merge-driver invocation-form bug pre-merge. clean.
- **Aino Virtanen** — #858/#852; delta -1 (1 review false-positive, single occurrence); at ceiling, held.
- **Nino Kavtaradze** — #851 + reviewed #835; delta -1 (1 review false-positive); held.
- **Nurul Hakim / Nadia Khoury / Santiago Ferreira / Wanjiku Mwangi** — 1 clean on-theme PR each (#850/#847/#844/#849); baseline, held.
- **Linh Pham** (isnad-graph) — #1129; clean; baseline, held.

### Top 3 Going Well
1. **Genuine distributed execution.** 28% concentration vs W16's ~100% meta-wave — the W16 retro caveat was met: architectural execution ran as real fan-out across 9 implementers, zero CI-red.
2. **Both architectural decisions executed in full.** #820 C×T2 (per-repo structural generator + central aggregator + Hook-15 softening + checksums-scope) AND #819 persona Option B (governed headcount + mechanical bidirectional trust + card slim) landed and exited Phase 6.
3. **Clean cross-repo merge discipline.** Producer-before-consumer wave→main ordering held (isnad-graph#1130's tool-dep check resolved only after main#861 landed); captured as [[feedback_consumer_wave_merge_ordering]].

### Top 3 Pain Points
1. **Post-merge-only deployable gates have no PR signal.** isnad-graph#1131 — a base-image CVE (libexpat CVE-2026-45186) reddened the GHCR publish on main AFTER #1130's green PR; the Trivy gate is push-to-main-only. Already addressed mid-retro: fixed (#1132) + built `verify_deployable_merge.py` (main#864/#865/#866) + wired into wrapup Step 11.5a.
2. **Wave-field option missing at label-apply.** 8 annunaki captures: Project-2 Wave field had no `W17` option when kickoff applied labels. Per [[feedback_projectv2_field_option]] this is orchestrator-doable via GraphQL — should be created at kickoff before labels, not surfaced as repeated PostToolUse advisories.
3. **Branch-freshness churn during fast fan-out.** 15 validate_branch_freshness blocks — implementer branches go stale vs the fast-moving wave branch, requiring rebase-before-PR-create. The gate worked (no stale merges), but the friction is high in a 14-PR parallel wave.

### Proposed Process Changes
1. **Auto-create the Wave-field option at /wave-kickoff (or /wave-scope) before label-apply** — Rationale: eliminates the 8 repeated "no option W{X}" PostToolUse captures; the GraphQL `createProjectV2FieldOption`-equivalent is orchestrator-doable ([[feedback_projectv2_field_option]]). Move it ahead of the label step.
2. **Deployable-merge verification is now standing practice** — Rationale: ratified by this wave's incident; `verify_deployable_merge.py` + wrapup Step 11.5a already merged. Recorded as [[feedback_deployable_merge_verification]].

### Annunaki-attack
53 captures this wave; **no genuine defects.** Breakdown: 15 validate_branch_freshness (gate working — stale implementer branches), 13 post_label_change_wave_field_sync (8 = missing W17 option → proposal #1 above; 4 = for-loop parse-skip, known limitation), 3 validate_commit_identity (heredoc/identity friction), gates firing as designed (ontology-context/pr-review/ci-status ×1 each), and dev-time test-failure noise (rc=0 stdout-pattern, the #835-fixed over-capture class). No new hooks/issues warranted.

### Memory-to-automation audit
1 promotion realized this wave: the deployable-merge-verification pattern was codified memory→lib+skill (`verify_deployable_merge.py` + wrapup Step 11.5a, main#864). No other memory crossed a promotion threshold; the ontology-path memories are tracked for P7W1 framework-alignment (#862).

---

