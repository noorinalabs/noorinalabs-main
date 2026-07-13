# Feedback Log — Phase 5 archive

> Archived byte-for-byte from `.claude/team/feedback_log.md`
> at phase close (#964, meta #960), preserving original file order. Do not edit —
> append-only history; new entries go to the live file for the current phase.

---

## Retrospective: Phase 5 Wave 5 — 2026-06-20 — "Production cutover (real data live on prod)"

### Team Performance
**45 PRs merged** to the wave branch across all 8 in-scope repos (main 9, isnad-graph 8, data-acquisition 10, design-system 5, landing-page 5, ingest-platform 4, deploy 3, user-service 1). **0 ChangesRequested cycles** — every PR clean-to-merge. CI green throughout; staging promotion **success** ([deploy-stg 27844114147](https://github.com/noorinalabs/noorinalabs-deploy/actions/runs/27844114147)); both fan-in publishes (isnad-graph, user-service) green on main. All 8 wave→main integration PRs merged (`ahead_by:0` for every wave branch — fully reachable). 11 stale merged worktrees cleaned. Wave meta #692 closed; ontology current (0 dirty).

| Wave-shape | Value |
|-----------|-------|
| PRs merged | 45 (8 repos) |
| ChangesRequested cycles | 0 |
| Top-implementer concentration | 4/45 = **9%** (A.Virtanen) — **28 distinct implementers**, the lowest concentration of any wave (healthy, not fragile) |
| Staging promotion | success (run 27844114147); fan-in publishes green |
| Prior-wave pain points closed | **#690** (promotion-audit canonical driver, S.Ferreira #701) + **#683** (cross-phase wave-key reuse, W.Mwangi #699) — both flagged in P5W3/W4 retros |
| Tech-debt / carry-forward | open `p5-wave-5` issues carried to /plan-phase triage (data-quality → P7; tooling → P6) |

### Per-Engineer Assessments
See `trust_matrix.md` § Phase 5 Wave 5 for the full table. Highlights: **S.Ferreira 4→5** (shipped the promotion-audit canonical driver #701 that *closes the P5W4 #690 hand-rolled mis-fire* + pr_review_state.py #710 + ontology-test fix #697); **W.Mwangi 3→4** (mechanized per-phase wave-key reset #699 closing #683, the cross-phase hazard flagged two waves running, + validate_wave_audit exemption #700); first numeric ratings for **J.Habimana 4** (da#186 — completed the Shia Four Books), **N.Papadopoulos 4** (da#183 — itqan 115,735 bios → 85,840 canonical Narrators), **L.Mbongo 4** (ingest SourceCorpus reconcile #98 + security floors #103), **K.Mensah-Williams 4** (3 lp PRs: dark-mode, Direction-C hero, removed fabricated pre-launch staff). The data-acquisition cutover spine (A.Reyes-Fuentes da#180 multi-source Sunni→staging, K.Sundaramurthy da#181 thaqalayn real-schema + Four Books, I.Horvat da#187 Riyad-complete) held at ceiling 5. ~17 single-clean-PR implementers held at current rating.

### Top 3 Going Well
1. **Two recurring prior-wave pain points durably closed in-wave** — the promotion-audit hand-rolled mis-fire (#690, flagged P5W4) is now a canonical driver (#701), and the `wave_{M}_*` cross-phase key-reuse hazard (#683, flagged P5W3 *and* P5W4) is now mechanically reset per phase (#699). The retro→fix loop actually closed.
2. **Cleanest wave of the program** — 0 ChangesRequested cycles across 45 PRs, all CI green, staging + both fan-in publishes green, all 8 wave branches fully reachable from main. The no-force / green-before-push discipline (main#684) held at scale.
3. **Lowest concentration ever (9%, 28 implementers)** — the production cutover load distributed across the entire roster with no single-engineer fragility, while the cutover-critical data spine (Four Books completion, itqan narrators, multi-source Sunni load) was delivered cleanly by the da team.

### Top 3 Pain Points
1. **Production loaded but quality-broken — the cutover criterion and the usability criterion diverged.** Real corpus is live on prod (~768k nodes) but only ~9% linked: chains sparse, narrators polluted, **sanadset loaded as ~650k orphan hadith nodes** (root cause: parser emits no `collections_sanadset.parquet`, ignores `books.csv` → 0 Collection nodes → all APPEARS_IN skipped), and prod search returns 0 hadiths (full-text mistypes as narrators; semantic 500s). Tracked as meta #723 → **Phase 7 data-quality**. The wave delivered the *cutover* (data present + app running) but not *queryability* — an honest gap, owner-accepted as P7-scoped at /phase-review.
2. **Annunaki signal-to-noise is poor.** 47 "genuine errors" this wave = 40 exit-0 false positives (benign command output containing trigger words) + 5 correct `pretooluse_block`s (hooks working) + 2 informational events. 85% noise. Blanket exit-0 filtering is unsafe (the `git push | tail` rejection-masking class is a real exit-0 failure — `feedback_push_pipe_masks_rejection`), so precision needs a smarter rule, not a coarse one.
3. **Phase-boundary ceremony was deferred, not run.** P5W5 merged all 45 PRs to main days before the wave was formally wrapped (`wave_5_wrapped_up_at` was null, `wave_5_active` true, no counters, no annunaki/memory markers) — the wrap/retro ran retroactively this session. The "merge-then-wrap-later" gap risks a phase closing on un-run audits.

### Proposed Process Changes
1. **Wrap-on-last-merge trigger** — when the final wave→main PR merges, surface a "wave unwrapped" flag at session-start (the `wave_{M}_active && wave_{M}_wrapped_up_at == null && 0 open wave PRs` condition) so the wrap/retro isn't deferred indefinitely. Rationale: P5W5 sat merged-but-unwrapped. Owner: Aino / session-start skill.
2. **Annunaki exit-0 precision pass** — tag exit-0 records whose trigger match is in *echoed output* (not a real failure signal) as a distinct low-confidence sub-class, excluded from the `/annunaki` count but retained for forensics — preserving the exit-0-failure carve-out (`git push | tail`). Rationale: 85% of this wave's "errors" were exit-0 noise. Owner: Aino / annunaki_monitor.
3. **Cutover vs queryability as separate exit criteria** — for data-bearing phases, split "data present on prod" from "data queryable on prod" so a cutover can close honestly while the quality bar is explicitly tracked forward. Rationale: P5 #665/#602/#666 met the cutover intent but not literal queryability; the split avoids re-litigating "is it done" at phase-review. Owner: owner / plan-phase.

### Annunaki-attack (Step 7.6)
47 genuine records triaged: 40 exit-0 false positives (benign output matched trigger words), 5 correct `pretooluse_block`s (a batch-loop `gh pr merge` and a label-validation `gh issue create` — hooks functioning as designed), 2 informational wave-field-sync events. **No novel actionable failure class → no new hook/skill/charter.** Dominant finding (exit-0 noise) folded into Proposed Process Change #2. Marker written (`wave_5_annunaki_attack_ran_at`).

### Memory-to-automation audit (Step 7.7)
Codification is handled deterministically by `/promotion-audit`, which this wave classified **0 AUTO · 0 DECIDE · 248 KEPT · 19 SUPERSEDED** — nothing crosses a promotion threshold; the 2 marker-reconciled memories (`feedback_refresh_before_status_claim`, `feedback_throttle_takeover`) now correctly read SUPERSEDED. No manual conversions warranted. Marker written (`wave_5_memory_audit_ran_at`).

## Promotion Audit — p5-wave-5 (2026-06-20)

0 AUTO · 0 DECIDE · 248 KEPT · 19 SUPERSEDED. No promotions warranted this wave. The marker-reconciliation pass earlier this session (provenance markers added for the two already-encoded memories) is reflected in the 19 SUPERSEDED. Standalone log: `.claude/team/promotion_audit_log/p5-wave-5.md`.

## Retrospective: Phase 5 Wave 3 — 2026-06-14 — "Trustworthy data & search"

### Team Performance
17 PRs merged across 5 repos (main 1, isnad-graph 7, user-service 2, deploy 3, data-acquisition 4); 0 open `p5-wave-3` issues at wrapup. CI green on every PR, all 2× Approved. **2 ChangesRequested cycles** (ig#1059, ig#1063 — both real bugs caught by adversarial review, fixed before merge; CR count is authoritative-historic, edited-in-place to Approved per charter verdict-amendment rule). Wave→main: 5 integration PRs admin-merged (wave-merge exception), reachability + staging gates green (both fan-in `deploy-stg` runs success, Trivy-clean). Counters exact: **17 PRs / 2 CR / 12% top-concentration** (claimed == recomputed).

| Wave-shape | Value |
|-----------|-------|
| PRs merged | 17 (5 repos) |
| ChangesRequested cycles | 2 (ig#1059 century-facet, ig#1063 Loki writer) |
| Top-implementer concentration | 2/17 = 12% (Mateo Salazar) — 16 distinct implementers, lowest of the phase (healthy) |
| Issues closed | 24 (all pre-wrapup) |
| Staging promotion | success (runs 27514746576 + 27514760338) |
| Tech-debt filed | ig#1060/1061/1062 (facet-completeness follow-ups, P5W4-tagged) |

### Per-Engineer Assessments
See `trust_matrix.md` § Phase 5 Wave 3 for the full table. Highlights: **Marisol Vega-Cruz 4→5** (reviewer MVP 2nd consecutive wave — reviewed both CR-cycle PRs, caught real defects in each); **Lucas Ferreira 3→4** (deploy#455 Loki contract cleanly consumed by ig#1063); first numeric ratings **Mei-Lin Chang 4** + **Nadia Hakim 4**. Nneka Obi held at 4 (work hers, recovered post-stall; not docked for the agent-liveness gap). Thandiwe Moyo held at 3 (real century-facet bug, but clean correct fix). 13 implementers held at current (clean single deliveries).

### Top 3 Going Well
1. **Adversarial review caught real bugs, not nits** — the ig#1059 century-facet leak was found *independently by two reviewers* (Anya + Marisol); ig#1063's Loki writer was verified against the merged deploy#455 contract before merge.
2. **Lowest concentration of the phase** — 12% top (16 distinct implementers across 5 repos); no single-engineer fragility.
3. **Cross-repo contracts honored cleanly** — deploy#455 (Loki retention contract) ↔ ig#1063 (api-container writer) matched path/tenant/inode/fallback exactly; data-spine fail-fast guards (da#168 edge-relation) durably closed prior traps.

### Top 3 Pain Points
1. **Agent-liveness gap recurred (2nd wave running)** — two stall-class events: ig#1038 implementer (Nneka) went silent-idle pre-commit (2 idle pings, no artifacts) → orchestrator takeover; and a ledger "implementing" cross-wire (ig#1023 was already resolved via deploy#454; ig#1038 reported implementing was actually unstarted). The **TaskCreate-per-implementer tracking proposed at P5W2 has not landed**, so the same invisibility recurred.
2. **Roster drift** — Mei-Lin Chang's `roster.json` / `roster.md` disagree (name/identity mismatch); surfaced manually, no automated guard.
3. **`cross-repo-status.json` wave-key cross-phase reuse** — the `wave_{M}_*` keys carry stale prior-phase values (P4W3's `final_pr_count=34`, `completed_at`, annunaki/memory `*_ran_at` markers all bled into P5W3 under the same keys); had to be cleared by hand at wrapup, and a stale `*_ran_at` would have made retro silently skip annunaki/memory audits.

### Proposed Process Changes
1. **Agent-liveness checkpoint (re-propose + escalate)** — TaskCreate-per-implementer at kickoff (P5W2 proposal, still unapplied) PLUS a liveness rule: an implementer with no artifact (branch/commit/PR) after 2 idle notifications is auto-flagged to the orchestrator. Rationale: same stall class hit two consecutive waves. Owner: Wanjiku (TPM) / kickoff skill.
2. **Mid-wave ledger↔artifact reconciliation** — before any "implementing/blocked/done" status claim drives a decision, reconcile the implementer ledger against artifacts (gh api branch/PR existence). Rationale: ig#1023/#1038 cross-wire. Owner: Aino (charter `state-claims.md`).
3. **Roster-consistency guard** — a check (hook or audit) that flags `roster.json` ↔ `roster/*.md` name/identity drift. Rationale: Mei-Lin Chang mismatch. Owner: Aino.
4. **Namespace or reset wave-status keys per phase** — either key wave-status as `p{N}_wave_{M}_*` or have `/wave-start` clear all `wave_{M}_*` values when a phase reuses a wave number. Rationale: P4W3→P5W3 stale-value bleed hit live this session. Owner: Aino / wave-start skill.

## Promotion Audit — p5-wave-3 (2026-06-14)

0 AUTO · 0 DECIDE · 240 KEPT · 4 SUPERSEDED · 21 ALREADY-PROMOTED. No promotions warranted this wave.

**Tooling defect found + filed (main#677):** a naive run flagged 24 false charter→skill AUTO promotions, caused by `count_skill_invocations("")` returning 635 (empty-slug match-all) compounded by the `promoted_to_slug` attribute mismatch in SKILL.md Step 3 (real attr: `promoted_to`). Re-run passing `section.promoted_to` (signal 0 for unpromoted sections) yields the correct 0/0. Standalone log: `.claude/team/promotion_audit_log/p5-wave-3.md`.

## Retrospective: Phase 5 Wave 1 — Data spine — 2026-06-14

### Team Performance
First Phase-5 wave (data-acquisition only). **4 PRs merged** (da#146/148/144/138), **0 ChangesRequested cycles**, all first-pass Approved with TechDebt lines; CI green; wave→main merged (#156), staging green. **1 issue killed premise-false** (da#147). TD intake 1/1 (da#138). Top-implementer concentration **25%** (4/4 distinct authors — healthy distribution, no fragility flag). 8 reviewer agents, all sharp.

### Wave shape
| Item | PR | Implementer | Reviewers | CR | Notes |
|------|----|-----|-----|----|----|
| da#146 (keystone) | #151 | Ivana Horvat | Alejandra, Jean-Claude | 0 | diacritic root-cause; 31,525 chains → mentions; +TechDebt da#155 |
| da#148 | #150 | Nikolaos Papadopoulos | Alejandra, Oyunbileg | 0 | self-loop + grade-normalize; remainder da#153 |
| da#144 | #149 | Kwesi Boateng | Tarek, Jean-Claude | 0 | mis adapter 3-file restructure; 63,642 edges |
| da#138 (TD) | #152 | Alejandra Reyes-Fuentes | Ivana, Kavitha | 0 | nasab-reversal false-merge fix + precision/recall harness |
| da#147 | — | (Kavitha) | — | — | closed premise-false (sect IS sect_affiliation) |

### Per-Engineer Assessments
- **Ivana Horvat** (da#146, PR #151) — keystone; root-caused away from the issue framing (diacritic mismatch in shared arabic.py, not the lk adapter), tested deterministic splitter, honest follow-up. + reviewed #152. Severity: none (positive). Trust 4→5 ▲.
- **Alejandra Reyes-Fuentes** (da#138 PR #152 + reviews #150/#151) — **wave MVP**: caught a nasab-reversal false-merge as implementer, then the standout keystone review reproducing عن mid-word over-segmentation + the masking-fixture. Severity: none (positive). Trust 5→5.
- **Kwesi Boateng** (da#144, PR #149) — diagnosed upstream dataset restructure, Nodes-decoy selector, live-trace. Severity: none (positive). Trust 5→5.
- **Nikolaos Papadopoulos** (da#148, PR #150) — honest producer-fix vs data-decision split (da#153); correct non-bug investigation. Severity: none (positive). Trust 5→5.
- **Kavitha Sundaramurthy** (da#147 + review #152) — premise-false verified with code evidence, refused a harmful fix; sharp #152 review. Severity: none (positive). Trust 4→5 ▲.
- **Jean-Claude Habimana** (reviews #149/#151), **Tarek Mansour** (review #149), **Oyunbileg Batbayar** (review #150) — all sharp, verified-not-rubber-stamped; first numeric ratings 4/4 for Jean-Claude/Tarek, Oyunbileg 5→5.

### Top 3 Going Well
1. **Verify-don't-rubber-stamp across the board** — the keystone review caught that the da#146 fix's OWN e2e test masks a new precision bug (عن over-segmentation); Kavitha killed da#147 premise-false with cross-repo code evidence; reviewers reproduced findings locally.
2. **Root-cause discipline beat issue framing** on 3 of 4 PRs — da#146 (not the lk adapter), da#144 (upstream restructure), da#138 (order-insensitivity not threshold).
3. **Honest scope-splitting** — da#153/154/155 filed for deferred/follow-up work; nothing silently dropped; TD intake (da#138) shipped real precision-guard value.

### Top 3 Pain Points
1. **fixture-masks-bug recurred INSIDE the fix for a fixture-masks bug** — da#146 fixed the un-voweled-toy-fixture blob bug, but its replacement Bukhari-h1 fixture contains no عن, masking the new over-segmentation (da#155). Recurring class (MockNeo4j, APPEARS_IN, toy-h1 double-prefix, local-only staging edges). → Proposed Change #1.
2. **`validate_labels` hook bit the orchestrator twice** — multi-cmd `--repo` cross-association (label-create + issue-create in one block) + stale label cache (new `phase-5`/`p5-wave-1` labels not seen until `gh api`-verified). Tracked #661/#663; worked around with bare commands.
3. **da#133 edge-relation default trap** — `DEFAULT_EDGE_RELATION` still falls back to STUDIED_UNDER; any future transmission producer that omits `relation` silently mis-routes onto the studentship allowlist. → Proposed Change #2.

### Proposed Process Changes
1. **Production-realistic fixture rule (charter/standards):** text-processing / Arabic-NER / graph-load fixtures MUST use production-realistic input (voweled Arabic containing high-frequency particles like عن; real-shape rows), NOT hand-built minimal/un-voweled chains. Rationale: the fixture-masks-bug class has now recurred 5+ times including inside its own fix (da#146→da#155). Owner: Aino. (Strongest signal this wave.)
2. **da#133 edge-relation default → fail-safe + wave sweep:** make `DEFAULT_EDGE_RELATION` not silently fall back to STUDIED_UNDER (require explicit relation or raise), and sweep all edge-producers to confirm they set `relation` + the loader routes by it. Code follow-up against da#133 (file as a data-acq issue).
3. **Producer-parity reviewer-checklist item:** "did the streaming (ingest-platform) path get the same invariant?" — every integrity/load invariant must hold on both batch + Kafka streaming paths (da#153 #4 tracks grade_normalized streaming mirror). Reviewer-brief addition.

### Annunaki (34 captures this wave)
Dominant signals: `validate_labels` multi-cmd + stale-cache (orchestrator, → #661/#663) and routine PUT/zsh navigation. No NEW automation warranted beyond #661/#663 already filed. The validate_labels gotchas are also captured in project memory (`feedback_validate_labels_hook_gotchas`).

### Memory-to-automation audit
No new conversions. The wave's promotion-worthy pattern (production-realistic fixtures) is captured as Proposed Change #1 (charter/standards). The `validate_labels` gotcha memory written this session is the only new memory; it stays as memory (operational workaround) until #661/#663 land the durable fix.

## Retrospective: Phase 5 Wave 2 — 2026-06-14 (API light-up)

### Team Performance
5 PRs merged to the wave branch, then wave→main (#1047); CI green throughout; staging promotion GREEN (deploy-stg run 27506467050). 6 issues closed (5 delivered + #1023 relocated→deploy#449). **0 ChangesRequested cycles** — every PR approved first-pass. Counters (5 / 0 / 20%) recomputed at retro == wrapup-claimed (no drift; the `git show origin/main` "null" read was a stale-local-ref artifact, gh api confirmed correct).

### Per-Engineer Assessments
- **Ingrid Lindqvist** — #1045 (narrators 500, keystone). Shipped under her identity but orchestrator-authored after a dispatch stall; held at 5, not credited (integrity). Severity: none (gap is process, not hers).
- **Jun-Seo Park** — #1033 (search 422). Correct dual-cap fix + boundary tests; both first-pass approvals. Hold 4. Severity: none.
- **Ravi Wickramasinghe** — #1030 (i18n page-body, TD). Clean; 7-locale parity verified. 3→4 (▲). Severity: none.
- **Idris Yusuf** — #1029 (auth refresh-on-401). Clean, both approvals. Hold 4. Severity: none.
- **Mateo Salazar** — #1028 (subscriptions/facet) + 2 reviews (#1045, #1030, latter flagged ig#1046). Hold 5. Severity: none.
- **Marisol Vega-Cruz** — 4 verified reviews + the predicted #1033↔#1028 merge-conflict flag. Reviews-MVP. 3→4 (▲).

### Wave-shape table
| Metric | Value |
|--------|-------|
| PRs merged | 5 |
| ChangesRequested cycles | 0 |
| Top-implementer concentration | 1/5 = 20% (5 distinct implementers — healthy, no fragility) |
| Issues closed | 6 (1 relocated) |
| Staging promotion | success (run 27506467050) |
| Tech-debt filed | ig#1046 + P5W3 backlog |

### Top 3 Going Well
1. **Cleanest wave in recent memory** — 0 ChangesRequested, all first-pass approvals, CI + staging green.
2. **Strong independent review culture** — reviewers ran tests + verified against head; Marisol's 4 reviews + the load-bearing merge-sequencing prediction; Mateo's TS-nullable follow-up (ig#1046).
3. **Honest scope discipline** — #1023 relocated to deploy#449 (explicit), not silently dropped; healthy 20% concentration across 5 implementers.

### Top 3 Pain Points
1. **Implementer dispatch had no task-tracking** — the keystone #1024 implementer produced zero output (no branch/PR/commit) and `TaskList` was empty, so the stall was invisible until a manual user nudge. The keystone bug nearly didn't ship. → Proposed Change #1.
2. **Local full-suite test runs hang on absent sandbox DB services** — pytest blocked 14 min on a DB connection (Marisol hit the same ~9-min stall). Wasted wall-clock + masked as "still running." → Proposed Change #2.
3. **PUT-contents commits leave the local `origin/main` ref stale** — counter re-verification read `null` via `git show origin/main` until re-fetched; state claims must use `gh api`, not the local ref (already a memory; recurred).

### Proposed Process Changes
1. **TaskCreate-per-implementer at kickoff** — every spawned implementer gets a tracked task so a zero-output stall is visible (and nudge-able) before wrapup, instead of surfacing only via manual user prompt. Rationale: P5W2's keystone stalled invisibly. Owner: Wanjiku (TPM) / kickoff skill.
2. **Sandbox test-verification pattern (charter/standards):** when the full suite hangs on absent local services, verify logic via targeted unit construction (no app/DB startup) + cite the green CI job, rather than burning wall-clock on a hung run. Document the `uv run` lock-contention gotcha (use `.venv/bin/<tool>` directly). Owner: Aino.

### Annunaki (16 captures this wave — all noise/benign)
8× benign `post_label_change` hook events (kickoff labeling), 2× `enforce_librarian` hook correctly blocking (known #169 worktree-cwd race, already addressed), 6× orchestrator transient session-command errors (cd path fatals, python one-liner tracebacks, the hung-pytest FAILED). No NEW automation warranted. Log cleared, marker written.

### Memory-to-automation audit
No new conversions. 140 memory files; this wave's promotion-worthy patterns are captured as Proposed Changes #1/#2 (process/charter) rather than as standalone memories.

## Retrospective: Phase 5 Wave 4 — Trustworthy data & search (capstone) — 2026-06-16

### Team Performance
- **Merged to wave branches:** 19 PRs across 4 repos (isnad-graph 12 · deploy 3 · user-service 2 · ingest 2). Counters helper-verified `19 / 4 / 16` (`wave_status.py counters 5 4 --expect 19` exit 0 — no drift; first retro use of the main#688 deterministic helper).
- **Wave→main:** 4/4 merged + retained (ig/us/deploy/ingest).
- **Post-wrapup delivery (to main):** the semantic-search capstone arc + determinism work — main#688/#689 (`wave_status.py`), ig#1093/#1094 (embed-image `import src` fix), deploy#465/#466 + #468/#469 (ssh `command_timeout` 10m→90m + embed mem 4G). All 2-reviewed, green, no force.
- **Capstone (#1071):** real 384-dim multilingual model re-embedded the **staging** corpus (33,958/34,028 hadiths) via the repeatable `reembed-corpus.yml` mechanism; **verify-recall PASS** (patience 0.50, prayer 0.77). Closed delivered-on-staging.
- **CI health:** clean; 4 ChangesRequested cycles, all on the `TechDebt:` attestation (ig#1085, ingest#88) — process rigor, not defects.

### Per-Engineer Highlights
- **Weronika Zielinska** — authored the re-embed mechanism (ADR 0008, deploy#462) + two clean, prompt follow-on fixes under capstone pressure (#466 timeout+mem, #469 90m). Domain ownership end-to-end. **Severity: none (strong).**
- **Linh Pham** — diagnosed + fixed the embed-image `import src` latent bug (ig#1094) precisely (PYTHONPATH=/app, incl. the runtime-stage twin), `buildx --check` green-before-push. **none (strong).**
- **Aino Virtanen** — shipped the determinism helper main#688/#689 end-to-end (kills the zsh word-split class structurally), live-verified 19/4/16, swept the skill loops. **none (ceiling).**
- **Mateo Salazar** — 3 clean PRs incl. the embed code (ig#1089). **none.**
- **Reviewers** — strongest review culture again: Jelani filed ig#1095 (proper package-install follow-up), Nurul filed deploy#467 (reembed staleness alert — caught that a timeout-kill aborts before the `.prom` write), Aisha's 47.5m/60m margin note drove the 90m bump. Wanjiku/Santiago cleanly cleared main#689.
- 14 distinct wave authors; remainder single clean PRs.

### Top 3 Going Well
1. **Capstone delivered real semantic search on staging via a repeatable mechanism — and caught 2 latent bugs before prod.** The owner-asked GH-Action/IaC design (not one-off SSH) found + fixed an embed-image packaging defect (masked on the api image by uvicorn's cwd insertion) and an SSH timeout, *then* passed recall. Exactly what staging-first is for.
2. **Determinism principle codified AND shipped as code same-session.** The recurring zsh/gh fragility → main#688 `wave_status.py` (deterministic, `--expect` gate) + charter § zsh-safe iteration. Soft memory → enforced code, the enforcement-hierarchy move done at the moment it bit.
3. **Low concentration + rigorous review culture.** 16% top concentration, 14 authors; the `TechDebt:` attestation gate held firm (4 CR cycles were all attestation rigor).

### Top 3 Pain Points
1. **Shell/gh fragility bit the wrapup 3× before being fixed** (zsh word-split → garbage counters/div-by-zero). Now structurally fixed (main#688), but it cost real cycles mid-wave.
2. **`/promotion-audit` has no canonical driver** — hand-rolling the helper-call sequence at retro mis-fired **24 spurious AUTO** on the section/skill tiers (memory tier correctly 0). Caught before emitting; filed main#690. Same determinism gap as #688.
3. **Prod is empty + MEMORY.md is oversized.** Prod Neo4j has 0 nodes — semantic search (and all data) is staging-only; prod cutover is a large untouched workstream (deploy#470). Separately, MEMORY.md is 38.0KB vs the ~24.4KB limit — index entries need trimming.

### Process Changes (proposed)
1. **Build the `/promotion-audit` canonical driver** (main#690) — `run.py {wave}` with a steady-state test; SKILL.md invokes it instead of prose. Eliminates per-retro hand-rolling.
2. **Trim MEMORY.md index** — entries exceed ~200 chars; move detail into topic files (the file's own warning).
3. **Theme-key staleness** — `wave_4_scope.theme` still reads the stale P4W4 value ("Admin surface + profile + streaming") via the known `wave_{M}_*` cross-phase collision (main#683). Recurs every same-numbered cross-phase wave; the deterministic-key fix remains the durable answer.

### Proposed Charter Change
- **Promote the determinism-codification reflex to a charter principle.** It currently lives as memory `feedback_codify_determinism_on_shell_fragility` + the narrow `charter/skills.md § zsh-safe iteration`. Broaden to a general rule under the enforcement hierarchy: *the first time a shell/gh syntax fragility bites a load-bearing path, write a deterministic `.claude/lib` helper, not a workaround.* (Rationale: bit 3× this wave; the targeted fix (#688) and the audit-driver gap (#690) are the same pattern.)

