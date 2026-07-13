# Trust Identity Matrix — Phase 5 archive

> Archived byte-for-byte from `.claude/team/trust_matrix.md`
> at phase close (#964, meta #960), preserving original file order. Do not edit —
> append-only history; new entries go to the live file for the current phase.

---

## Phase 5 Wave 1 Trust Updates (2026-06-14) — Data spine

First Phase-5 wave (data-acquisition only). 4 PRs, **0 ChangesRequested cycles**, all first-pass Approved; top-concentration 25% (4/4 distinct authors — healthy). Reviews were uniformly sharp — three sources independently surfaced forward-looking throughlines, and the keystone review caught a real precision bug the fix's own test masked.

### Implementers
| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Alejandra Reyes-Fuentes | 5 | 5 | **Wave MVP** — triple contribution: implemented da#138 (caught a real nasab-reversal false-merge, order-guard not threshold-bump) AND reviewed #150 AND the standout keystone review on #151 (reproduced عن mid-word over-segmentation in real narrator names + caught that the new e2e fixture masks it). Maintain at ceiling. |
| Ivana Horvat | 4 | **5** (▲) | da#146 keystone — root-caused the bug AWAY from the issue framing (not the lk adapter; diacritic-free patterns vs voweled text, masked by un-voweled toy fixtures), shipped a tested deterministic splitter (1 blob → 6 mentions; 31,525 chains segmented), honest real-NER follow-up. + reviewed #152. Promote to ceiling. |
| Kwesi Boateng | 5 | 5 | da#144 — diagnosed the upstream 2→3-file dataset restructure, Nodes-decoy-aware selector, live-traced 63,642 edges, kept mis OFF the STUDIED_UNDER allowlist. Maintain at ceiling. |
| Nikolaos Papadopoulos | 5 | 5 | da#148 — honest producer-fixable (shipped) vs data-decision (→da#153) split; investigated + correctly closed the 15-lk-STUDIED_UNDER as cross-corpus identity merge (not a bug). Maintain at ceiling. |
| Kavitha Sundaramurthy | 4 | **5** (▲) | da#147 correctly killed **premise-false** with cross-repo code evidence (verify-don't-fabricate; refused a harmful binary-collapse "fix") + sharp #152 secondary review (fixture covers precision AND recall traps). Promote to ceiling. |

### Reviewers (first numeric ratings)
| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Jean-Claude Habimana | — | **4** | First numeric rating: architect reviews on #149 + #151; confirmed the right-layer (shared arabic.py) fix, caught the "Tracked"-without-issue-number nit (→da#154), and co-surfaced the fixture-masks-bug throughline. |
| Tarek Mansour | — | **4** | First numeric rating: #149 review surfaced the da#133 edge-relation **default-trap** (DEFAULT_EDGE_RELATION falls back to STUDIED_UNDER → silent mis-route for any future transmission producer) — a high-value forward-looking finding. |
| Oyunbileg Batbayar | 5 | 5 | #150 QA review — verified test coverage in BOTH directions (self-loop drop AND distinct-adjacency keep; grade-normalize table breadth). Maintain at ceiling. |

### Orchestrator (Self-Assessment)
| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Orchestrator (Steven via Claude) | 4 | 4 | (hold) Clean wave: scoped → kicked off → 4 PRs → 8 reviewers → wrapped, 0 CR cycles, counters exact (4/0/25, claimed==recomputed). Independently verified da#147 premise-false before closing (good judgment, avoided a harmful fix). Navigated the `validate_labels` multi-cmd + stale-cache hook bugs with bare-command workarounds (the bugs are #661/#663, not orchestrator error). Two consecutive clean waves (P4W7, P5W1) build toward promotion; holding 4 for humility/trend, not for any specific slip. |

### Done Well / Needs Improvement (Phase 5 Wave 1)
- **Done well:** every reviewer verified rather than rubber-stamped — the keystone review even caught that the fix's own test masks a NEW precision bug (fixture-masks-bug recurring one layer down); three independent forward-looking throughlines; premise-false caught by the implementer (Kavitha) AND independently confirmed; honest scope-splitting (da#153/154/155 filed, nothing dropped).
- **Needs improvement (process):** the `validate_labels` hook bit the orchestrator twice (multi-cmd `--repo` cross-association + stale label cache) — tracked in #661/#663, worked around; and the fixture-masks-bug class keeps recurring — proposed as a charter rule this retro.

## Phase 5 Wave 2 Trust Updates (2026-06-14) — API light-up

Clean wave: 5 PRs, **0 ChangesRequested cycles** (every PR approved first-pass), CI green, staging green. Team = isnad-graph roster. One integrity note: the keystone #1024/#1045 shipped under Ingrid's identity but was an **orchestrator-takeover** (the assigned implementer produced no branch/PR/commit and no task was tracked — see feedback_log pain point #1); Ingrid is therefore **held, not credited**, for that PR.

### Implementers
| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Ingrid Lindqvist | 5 | 5 | Hold at ceiling on prior standing. #1045 (narrators 500 keystone) shipped under her identity but was orchestrator-authored after a dispatch stall — **not credited** to her this wave (integrity: don't credit unearned work). No negative signal either — the stall was a dispatch/tracking gap, not her slip. |
| Jun-Seo Park | 4 | 4 | #1033 (search 422) — correct dual-cap fix (keyword 100 / semantic 50), non-vacuous boundary tests both sides, both approvals first-pass. Trivial post-#1028 merge conflict resolved by orchestrator. Hold (clean, at 4 since W4). |
| Ravi Wickramasinghe | 3 | **4** (▲) | #1030 (i18n page-body, TD intake) — clean; reviewers verified 7-locale key parity programmatically (72-key base, 0 missing/extra) + correct grade-filter scope policy. Also reviewed #1028. Recovery from the stale W-early DS-integration neutral. |
| Idris Yusuf | 4 | 4 | #1029 (auth refresh-on-401 across admin+profile clients) — clean, both approvals (Anya + Arjun). Hold (clean trajectory). |
| Mateo Salazar | 5 | 5 | Dual contributor: implemented #1028 (subscriptions/me origin + derive collection facet) AND reviewed #1045 + #1030 (the #1045 review flagged the frontend-TS-nullable follow-up → ig#1046). Maintain at ceiling. |

### Reviewers
| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Marisol Vega-Cruz | 3 | **4** (▲) | **Wave MVP (reviews)** — 4 rigorous code-verified reviews (#1045, #1033, #1030, #1028), each run-the-tests + verify-against-head, and the load-bearing #1033↔#1028 merge-sequencing flag that predicted the exact conflict. Strong recovery from the old tarball-lockfile neutral. |
| Farhan Malik | 5 | 5 | #1033 review — independently reproduced the dual-cap root cause + confirmed tests non-vacuous. Maintain at ceiling. |
| Anya Kowalczyk | 5 | 5 | #1029 review. Maintain at ceiling. |
| Arjun Raghavan | 4 | 4 | #1029 review. Hold. |

### Orchestrator (Self-Assessment)
| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Orchestrator (Steven via Claude) | 4 | 4 | (hold) Drove the wave to a clean close (5 PRs, wave→main, stg green, counters exact 5/0/20) AND handled a wide product/ops surface in parallel (landing-page hotfix, monitoring check-in, 3 issue-set filings for P5W3). Caught the #1024 dispatch stall and took it over correctly (sound fix + regression test), but **the stall itself is a process gap I own** — implementers were spawned without TaskCreate tracking, so a zero-output implementer was invisible until a manual nudge. Holding 4: clean execution offset by the dispatch-tracking gap (proposed fix this retro). |

### Done Well / Needs Improvement (Phase 5 Wave 2)
- **Done well:** cleanest wave in recent memory (0 CR cycles, all first-pass approvals); strong independent review culture (Marisol's 4 verified reviews + the predicted merge-conflict flag; Mateo's TS-nullable follow-up); honest scope handling (#1023 relocated to deploy#449, not silently dropped); the keystone narrators-500 fix unblocks /graph + narrator search.
- **Needs improvement (process):** (1) implementer dispatch had no task-tracking → a zero-output implementer (#1024) was invisible until manual nudge; (2) local full-suite test runs hang on absent sandbox DB services (14-min stall) — needs a documented verify-via-unit-construction-then-cite-CI pattern.

## Phase 5 Wave 3 Trust Updates (2026-06-14) — Trustworthy data & search

Clean-but-not-frictionless wave: **17 PRs across 5 repos**, all 2× Approved + CI green + staging green; **2 ChangesRequested cycles** (both real bugs caught by adversarial review, both fixed before merge); top-concentration **12%** (Mateo Salazar 2/17 — 16 distinct implementers, the lowest concentration of the phase). Two stall-class events recurred (ledger "implementing" cross-wire on ig#1023/#1038; Nneka silent-idle on ig#1038 → orchestrator takeover) — same agent-liveness gap class as P5W2's dispatch stall; the fix proposed last retro has not yet landed.

### Implementers
| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Aino Virtanen | 5 | 5 | main#678 (CREATE-path wave-label drop #659 + validate_labels body over-match #661) — clean hook fix, 2 approvals. Maintain at ceiling. |
| Jun-Seo Park | 4 | 4 | ig#1052 (surface hadith grade via GRADED_BY) — clean, both approvals first-pass. Hold. |
| Mei-Lin Chang | — | **4** | First numeric rating: ig#1053 (compute + load hadith embeddings — the semantic-search data spine), clean 2-approval delivery. **Roster hygiene flag:** roster.json/roster.md name drift surfaced this wave (process item, not a delivery slip — see feedback_log pain point #3). |
| Ingrid Lindqvist | 4 | 4 | ig#1055 (default graph subgraph on landing) — clean. Hold. |
| Farhan Malik | 5 | 5 | ig#1056 (isnad-narrator filter + reachability — a feat, not a fix). Clean, 2 approvals. Maintain at ceiling. |
| Mateo Salazar | 5 | 5 | Dual-repo contributor + top-concentration (ig#1058 honest admin counts/corpus + us#167 admin user-stats endpoint). Clean both. Maintain at ceiling. |
| Thandiwe Moyo | 3 | 3 | ig#1059 (apply collection/grading/century facets) — **1 CR cycle**: initial century-facet matcher leaked later centuries on any single-bucket-below-5 selection (caught *independently by both* Anya + Marisol). Fixed correctly with a fixed `OPEN_ENDED_CENTURY=5` constant + mid-bucket regression test. Real-bug-then-clean-fix = neutral; hold. |
| Nneka Obi | 4 | 4 | ig#1063 (configurable Loki log retention) — shipped a real retention file-writer matching the deploy#455 contract (1 CR cycle, Jelani-verified path/tenant/inode/fallback). **Held, not docked:** the assigned agent went silent-idle pre-commit; orchestrator-takeover recovered *her* uncommitted worktree work (so the work is hers) — the stall is an agent-liveness/infra gap, not her slip. |
| Anya Kowalczyk | 5 | 5 | us#168 (lengthen access-token TTL 15→60) clean impl **+** the independent century-facet catch on ig#1059. Maintain at ceiling. |
| Weronika Zielinska | 4 | 4 | deploy#454 (repoint user-service blackbox probe — resolved the ig#1023 health-404 cross-wire on the deploy side). Clean. Hold. |
| Lucas Ferreira | 3 | **4** (▲) | deploy#455 (compose log-rotation anchor + Loki retention contract) — material cross-repo contract that ig#1063 correctly consumed (the api-container-as-writer provision). Clean, 2 approvals. Promote off the prior single-interaction neutral. |
| Nadia Hakim | — | **4** | First numeric rating: deploy#456 (Email backup + swappable alert channel) — clean feat extending the stg alerting surface (deploy#452/453 lineage). 2 approvals. |
| Kwesi Boateng | 5 | 5 | da#168 (fail-fast on undeclared edge relation — the da#133/#157 edge-relation default-trap durably closed). Maintain at ceiling. |
| Alejandra Reyes-Fuentes | 5 | 5 | da#169 (transliteration fallback for English-name coverage, da#159). Clean. Maintain at ceiling. |
| Kavitha Sundaramurthy | 5 | 5 | da#170 (scale PARALLEL_OF detection). Clean. Maintain at ceiling. |
| Ivana Horvat | 5 | 5 | da#171 (production-robust isnad segmentation). Clean. Maintain at ceiling. |

### Reviewers
| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Marisol Vega-Cruz | 4 | **5** (▲) | **Wave MVP (reviews), 2nd consecutive** — reviewed BOTH CR-cycle PRs: independently reproduced the ig#1059 century-facet leak AND verified ig#1063's Loki writer against the deploy#455 contract. Two straight waves of run-the-tests/verify-against-head reviews that each caught real defects → promote to ceiling. |
| Anya Kowalczyk | 5 | 5 | (reviewer credit) independent ig#1059 century-facet catch — see implementer row. Maintain. |
| Jelani Mwangi | 4 | 4 | ig#1063 review — verified the Loki retention writer against the merged deploy#455 contract (path/tenant/inode-preservation/fallback all confirmed). Hold (clean, precise). |

### Orchestrator (Self-Assessment)
| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Orchestrator (Steven via Claude) | 4 | 4 | (hold) Drove a clean wave→main close (17 PRs, 5-repo wave-merge ceremony, reachability + staging gates green, counters exact 17/2/12) and caught + corrected a real state cross-wire (ig#1023 already-resolved vs ig#1038 unstarted). But **two stall-class events recurred** (ledger cross-wire + Nneka silent-idle) of the **same agent-liveness class** I flagged at P5W2 — and the TaskCreate-per-implementer fix I proposed then still hasn't landed. Also hit the `wave_3_*` cross-phase key-reuse hazard (stale P4W3 values bled in; cleared manually at wrapup). Clean execution offset by a recurring unaddressed process gap → hold 4. |

### Done Well / Needs Improvement (Phase 5 Wave 3)
- **Done well:** strongest review culture of the phase — both CR cycles were *real* bugs surfaced by adversarial review (the century-facet leak caught independently by two reviewers), not nits; lowest concentration of the phase (12%, 16 implementers); honest data-spine work (semantic embeddings, isnad-narrator reachability, fail-fast edge-relation guard) with cross-repo contracts cleanly honored (deploy#455 ↔ ig#1063).
- **Needs improvement (process):** (1) **agent-liveness** — two stall-class events (silent-idle + ledger cross-wire); the P5W2-proposed TaskCreate-per-implementer tracking is still unapplied; (2) **roster drift** — Mei-Lin Chang roster.json/roster.md mismatch needs a consistency check; (3) **cross-repo-status.json wave-key reuse** — `wave_{M}_*` keys carry stale prior-phase values across phases, a correctness hazard hit live this session.

## Phase 5 Wave 4 Trust Updates (2026-06-16) — Trustworthy data & search (capstone)

### Implementers
| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Weronika Zielinska | 4 | **5** (▲) | Authored the re-embed mechanism (ADR 0008 / deploy#462) and delivered two clean, prompt follow-on fixes under capstone pressure (#466 timeout+4G mem, #469 90m) — each green-before-push, each unblocking the next step. End-to-end domain ownership of the wave's centerpiece → ceiling. |
| Linh Pham | 3 | **4** (▲) | Precise root-cause + minimal fix on the embed-image `import src` bug (ig#1094): PYTHONPATH=/app incl. the latent runtime-stage twin, `buildx --check` green, no install creep. Exactly-scoped. |
| Aino Virtanen | 5 | 5 | main#688/#689 deterministic `wave_status.py` shipped end-to-end (kills the zsh word-split class), live-verified 19/4/16, swept the skill loops + charter note. Maintain at ceiling. |
| Mateo Salazar | 5 | 5 | 3 clean PRs incl. the embed code (ig#1089). Maintain at ceiling. |

### Reviewers
| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Jelani Mwangi | 4 | 4 | ig#1094 infra-lens review + filed ig#1095 (proper package-install follow-up). Clean, hold. |
| Nurul Hakim | — | 4 | deploy#466/#469 observability-lens reviews; filed deploy#467 catching that a hard timeout-kill aborts before the `.prom` write (no metric emitted). Sharp. |
| Aisha Idrissi | — | 4 | deploy#466/#469 SRE-lens; the 47.5m/60m margin note drove the 90m safety bump. Forward-looking. |

### Orchestrator (Self-Assessment)
| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Orchestrator (Steven via Claude) | 4 | 4 | (hold) Drove the capstone to a verified staging delivery — found+fixed two latent prod-blocking bugs *before* prod (embed-image packaging, ssh timeout), surfaced prod-empty honestly rather than forcing a pointless cutover, and caught the hand-rolled promotion-audit's 24-AUTO mis-fire before emitting. Offset by: the shell/gh fragility recurred 3× before the #688 fix, and the promotion-audit had to be hand-rolled (mis-fired) for lack of a driver. Clean delivery + good judgment, two known process gaps now filed (#688 done, #690 open) → hold 4. |

### Done Well / Needs Improvement (Phase 5 Wave 4)
- **Done well:** staging-first capstone caught 2 latent bugs before prod and verified real recall; determinism principle codified *and* shipped as code same-session (#688); honest prod-empty surfacing instead of a forced cutover; lowest-friction review culture (TechDebt attestation held, useful follow-ups filed #1095/#467).
- **Needs improvement (process):** (1) shell/gh fragility cost cycles before #688 landed; (2) `/promotion-audit` lacks a canonical driver → hand-rolled mis-fire (#690); (3) MEMORY.md oversized (38KB); (4) `wave_{M}_*` theme/key cross-phase staleness recurred (main#683 still the durable fix).

## Phase 5 Wave 5 Trust Updates (2026-06-20) — Production cutover (real data live on prod)

### Org-Level / Framework (main)
| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Santiago Ferreira | 4 | **5** (▲) | Shipped the **promotion-audit canonical driver** (#701) — directly closes the P5W4 #690 hand-rolled mis-fire pain point — plus `pr_review_state.py` (#710, deterministic review-state) and the REPO_ROOT-independent ontology test (#697). Three clean tooling PRs, one of them a durable retro-loop close. Promote to ceiling. |
| Wanjiku Mwangi | 3 | **4** (▲) | Mechanized **per-phase wave-key reset** (#699) closing #683 — the `wave_{M}_*` cross-phase reuse hazard flagged in *both* P5W3 and P5W4 retros — plus the validate_wave_audit wave-branch-PR exemption (#700). Two clean PRs that retired a recurring correctness hazard. |
| Aino Virtanen | 5 | 5 | 4 charter/hook PRs (#696 fixture-realism charter, #698 cspell CI-parity, #702 gh-parser invariant + hook, #709 session-handoff phase reader). Clean. Maintain at ceiling. |

### Data-acquisition (cutover data spine)
| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Alejandra Reyes-Fuentes | 5 | 5 | da#180 (multi-source Sunni corpora → staging Neo4j, containerized loader) + da#192 (matn_ar fallback) + da#193 (canonical composition encode). 3 PRs on the cutover spine. Maintain at ceiling. |
| Kavitha Sundaramurthy | 5 | 5 | da#181 — real-schema thaqalayn parse + loaded the Shia Four Books to staging (closed the fixture-masked parser gap). Cutover-critical. Maintain at ceiling. |
| Ivana Horvat | 5 | 5 | da#187 — completed Riyad as-Salihin to 1,896 by enumerating named book segments (addresses the da#177 truncation class). Clean. Maintain at ceiling. |
| Jamal Habimana | — | **4** | First numeric rating: da#186 — sourced Tahdhib al-Ahkam + al-Istibsar from ThaqalaynData (CC0), **completing the Shia Four Books**. Cutover-critical, clean. |
| Nikos Papadopoulos | — | **4** | First numeric rating: da#183 — staging itqan narrator load (115,735 bios → 85,840 canonical Narrators), the largest narrator source. Clean. |
| Tarek Mansour | 4 | 4 | da#184 (testcontainers neo4j pin) + da#189 (bleach security pin). Two clean infra/security PRs. Hold. |
| Olzvoi Batbayar | — | **3** | First numeric rating: da#185 (tightened tautological cap-equivalence test). Small, clean. |

### isnad-graph / user-service
| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Mateo Salazar | 5 | 5 | ig#1100 (shared search-result helper) + ig#1106 (rate-limit Redis socket timeouts, closes #1034) + us#176 (security floors). 3 clean PRs. Maintain at ceiling. |
| Linh Pham | 4 | 4 | ig#1097 + ig#1102 (testcontainers neo4j tag + password alignment). Two clean test-infra PRs. Hold. |

### Ingest-platform / Deploy / Design-system / Landing-page
| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Lerato Mbongo | — | **4** | First numeric rating: ingest#98 (reconcile vendored SourceCorpus with da canonical) + ingest#103 (starlette/cryptography security floors). Two clean PRs closing real drift. |
| Astrid Lindqvist | 5 | 5 | ds#118 (motion primitives → framework-neutral CSS) + ds#119 (compiled component-utilities layer, closes the #115 no-op-utilities class) + ds#121 (release bump). 3 clean PRs. Maintain at ceiling. |
| Kojo Mensah-Williams | — | **4** | First numeric rating: 3 lp PRs — #142 (dark-mode toggle), #145 (Direction-C architecture hero), #141 (removed fabricated pre-launch staff). Clean, product-facing. |
| Nadia Hakim | 4 | 4 | deploy#473 (alert on corpus_reembed_last_run_* failed+stale). Clean observability extension. Hold. |
| Lucas Ferreira | 4 | 4 | deploy#472 (gate tiered-rollout service lists ⊆ compose services, closes #434). Clean CI guard. Hold. |
| Weronika Zielinska | 5 | 5 | deploy#471 (sweep stale Kafka topic in preflight fixture). Clean. Maintain at ceiling. |

**Single-clean-PR implementers held at current rating** (no significant directional signal — clean single deliveries): A.Diop-Sarr (lp#143 brand assets), C.Novak (lp#140 candidate assets), B.Henriksen (ingest#97 neo4j-tag centralization), I.Lindqvist (ig#1099 GRADE_LABELS single-source), J.Mwangi (ig#1101 embed-image package install), J.Park (ig#1098 readJsonResponse guard), K.Ranasinghe (ingest#100 bleach security), M.Reyes (ds#116 icons criticalExports), N.Pham (ds#117 a11y color-scheme), N.Obi (ig#1103 i18n page-body extension).

### Orchestrator (Self-Assessment)
| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Orchestrator (Steven via Claude) | 4 | 4 | (hold) Drove the cleanest wave of the program to a verified close (45 PRs, 0 CR, staging+fan-in green, all 8 wave branches reachable) and surfaced the prod data-quality reality **honestly** (sanadset orphans, sparse chains, broken search → meta #723/P7) rather than declaring a hollow cutover. Self-corrected a "zero chains" overstatement mid-validation against the actual graph counts. Offset by: the **wave was merged days before being wrapped** (P5W5 sat `active:true / wrapped_up_at:null` with un-run audits), and the marker-reconciliation push-block had to be resolved reactively. Clean execution + honest reporting, one deferred-ceremony gap (now Proposed Change #1) → hold 4. |

### Done Well / Needs Improvement (Phase 5 Wave 5)
- **Done well:** retro→fix loop genuinely closed (two recurring pain points #690/#683 retired in-wave); cleanest wave of the program (0 CR / 45 PRs, all gates green); lowest concentration ever (9%, 28 implementers) with the cutover data spine still delivered cleanly; honest prod-quality surfacing instead of a hollow "cutover done."
- **Needs improvement (process):** (1) **deferred wrap** — wave merged-then-wrapped-later, audits un-run until this session (Proposed Change #1: wrap-on-last-merge trigger); (2) **annunaki noise** — 85% exit-0 false positives drown the real signal (Proposed Change #2); (3) **cutover ≠ queryability** — prod data present but not usable (search broken, sanadset orphans), carried to P7 #723 (Proposed Change #3: split the two as distinct exit criteria).

