# Trust Identity Matrix — Phase 4 archive

> Archived byte-for-byte from `.claude/team/trust_matrix.md`
> at phase close (#964, meta #960), preserving original file order. Do not edit —
> append-only history; new entries go to the live file for the current phase.

---

## Phase 4 Wave 1 Trust Updates (2026-06-10) — Clean slate (bugs + security + tech-debt burn-down)

First wave of Phase 4. 23 PRs / 7 repos / **1 changes-requested cycle** (deploy#415) / **0 failing CI checks** at any PR head / staging promotion green. Top-implementer concentration **13%** (3 PRs — Nurul Hakim and Aisha Idrissi tied), the most distributed wave on record — a *theme-fit* low (the wave was deliberately a broad burn-down across tiers, not a single-owner domain). Security tier landed in full (deploy#384/#386 scrape-block pair, isnad-graph#955, deploy#244 OAuth dual-env). Directional summary: **everyone at established levels holds** — a clean, well-distributed wave produces little numeric movement when most of the roster already sits at max. No negative signal, no demotions.

### Org-Level Team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| **Nadia Khoury** (PD) | 5 | 5 | (hold at max) Wave executed cleanly across 7 repos; the one latent defect (deploy#418) was a missing-gate gap, not a coordination failure. |
| **Wanjiku Mwangi** (TPM) | 5 | 5 | (hold at max) Counter integrity held — wrapup counters (23 / 1 / 13%) reconciled at retro with zero drift. |
| **Santiago Ferreira** (RC) | 5 | 5 | (hold at max) Staging-promotion gate green; owns the new `/watch-deploy` release-monitoring skill authored this session. |
| **Aino Virtanen** (SQL) | 5 | 5 | (hold at max) Tech-debt tier (the bulk of the wave) landed clean; standards review backbone. |

### Deploy / Service Implementers

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| **Nurul Hakim** (deploy Obs) | 5 | 5 | (hold at max) 3 PRs (deploy#384 security, observability scrape, main#596) — joint top-implementer, fourth consecutive clean wave. |
| **Aisha Idrissi** (deploy SRE) | 5 | 5 | (hold at max) 3 PRs (deploy#395/#398 tech-debt) — joint top-implementer, all clean. |
| **Lucas Ferreira** (deploy SRE) | 5 | 5 | (hold at max) deploy#402/#86/#410 + main#613; authored the deploy#418 fix this session through full lifecycle. |
| **Nino Kavtaradze** (deploy Sec) | 5 | 5 | (hold at max) deploy#386 + #244 security tier landed. |
| **Mateo Salazar** (user-service Eng) | 4 | 4 | (hold) 2 clean bug PRs (us#65 config-URL, us#74 OAuth SQLAlchemyError). Consistent with the W15 3→4 bump; one more clean wave keeps the trajectory toward 5. |
| **Idris Yusuf** (isnad-graph / user-service Eng) | 4 | 4 | (hold) 2 clean security PRs (us#73, isnad-graph#955). Rebuilding cleanly after the W15 #872 anti-pattern note; positive trajectory. |

### Orchestrator (Self-Assessment)

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| **Orchestrator (Steven via Claude)** | 4 | 4 | (hold) This session: diagnosed the live "frontend image not-found" to root (per-service tag mis-routing, **not** the first-hypothesised publish race — pivoted honestly when the evidence contradicted the initial theory), fixed it (deploy#418/PR#419) and built `/watch-deploy` (main#623/PR#624), both through the full 2-reviewer + green-CI lifecycle, and **self-caught a real run-resolution bug in the skill during pre-merge review**. Added a landing-parity completeness pass unprompted. **Hold-not-promote:** the deploy#418 defect itself shipped through W1 undetected — defensible (no user-service-only stg deploy ever exercised the path, and the catching gate didn't exist), but promotion wants a wave with no latent-defect surface attributable to prior orchestrator-driven execution. |

### Done Well / Needs Improvement (Phase 4 Wave 1)

| Member | Done Well | Needs Improvement |
|--------|-----------|-------------------|
| **Nurul Hakim / Aisha Idrissi** | Joint top-implementers (3 each), zero CI failures, zero must-fix items | None this wave |
| **Lucas Ferreira** | Tech-debt + docs delivery; live-session deploy#418 root-cause fix | None this wave |
| **Mateo Salazar / Idris Yusuf** | Clean bug + security delivery; the user-service/isnad bug+security backbone | None this wave |
| **Org-level team** | 13% concentration (most distributed wave on record), 1 CR, 0 CI failures, stg green | Commit-identity hygiene: deploy#409 authored as bare `parametrization`; `Kofi Mensah` vs `Kofi Mensah-Williams` divergence (cross-repo persona reconciliation) |
| **Orchestrator** | Honest diagnosis pivot; self-caught skill bug pre-merge; full-lifecycle discipline on both PRs | The deploy#418 class slipped through W1 undetected (now gated by `/watch-deploy` + the fix) |

## Phase 4 Wave 2 Trust Updates (2026-06-11) — Pipeline first light + auth account-linking

### Org-Level Team
| Rated | Old | New | Reason |
|---|---|---|---|
| Nadia Khoury (PD) | 5 | 5 | Wave orchestration + clean wrapup; hold at max |
| Wanjiku Mwangi (TPM) | 5 | 5 | Reviews + counter discipline; hold at max |
| Santiago Ferreira (RC) | 5 | 5 | Caught the merge-commit false-positive in the identity gate — material; hold at max |
| Aino Virtanen (Standards) | 5 | 5 | Identity gate + annunaki + the honest #136 duplication audit + #634 catch; exemplary, hold at max |

### Data-Acquisition / Pipeline
| Rated | Old | New | Reason |
|---|---|---|---|
| Kwesi Boateng | — | +1 (cap 5) | Keystone slice, live load, null-safe loader fix, in-book-ordinal evidence graph, flawless rebase choreography + self-correction |
| Alejandra Reyes-Fuentes | — | +1 (cap 5) | Scraper fix + converged to the more-honest in-book-ordinal extraction |
| Oyunbileg Batbayar | — | +1 (cap 5) | Edge-key real-graph assertion + caught masked empty-graph fixture + SET-null-removes-key subtlety |
| Nikolaos Papadopoulos | — | +1 (cap 5) | E2E harness + live run + found id double-prefix + cross-PR contract alignment |
| Tomás Carvalho (ingest) | — | +1 (cap 5) | Worker-chain E2E + honest xfail-with-diagnosis surfacing ig#69 |

### User-Service
| Rated | Old | New | Reason |
|---|---|---|---|
| Mateo Salazar | — | +1 (cap 5) | Coherent auth-linking guard + real-Postgres-container proof |
| Idris Yusuf | — | +1 (cap 5) | Gating security review — verified guard genuine server-side, not mock-only |
| Anya Kowalczyk | — | +1 (cap 5) | Thorough tech-lead reviews (us#156 + ig#961) |

### Isnad-Graph / Ingest reviewers
| Rated | Old | New | Reason |
|---|---|---|---|
| Ingrid Lindqvist | — | +1 (cap 5) | Config component-env fix with URL-hostile-password tests |
| Imelda Santos, Sayed Reza, Jean-Claude Habimana, Arjun Raghavan | — | hold | Solid review verdicts; no negative signal |

### Done Well / Needs Improvement (Phase 4 Wave 2)
- **Done well:** data-first thesis delivered (real data on screen); integrity culture (mock-masks-production named + hunted, self-correcting); peer-to-peer cross-PR contract alignment.
- **Needs improvement (orchestrator):** reviewer-brief TechDebt-attestation phrasing; advisory-gating handling; crossed-message churn discipline.

## Phase 4 Wave 3 Trust Updates (2026-06-12) — Open the doors: real data in a usable product

Wave shape: **34 PRs / 7 repos / 19 distinct implementers**, top-concentration **15%** (Kwesi Boateng 5/34 — theme-fit, the da adapter light-up sweep), **6 changes-requested cycles** (all on appropriately-sensitive surfaces: admin OBLITERATE reset UI, DS-audit format, theme/charset, team bios, reset endpoint), **0 CI failures**, staging green, **1 prod incident** (deploy path, recovered — see pain points).

### Org-Level Team
| Rated | Old | New | Reason |
|---|---|---|---|
| Nadia Khoury (PD) | 5 | 5 | Largest wave to date (34 PRs) wrapped clean; hold at max |
| Wanjiku Mwangi (TPM) | 5 | 5 | Counter discipline held — all three wrapup counters matched retro recompute exactly (0 drift); hold at max |
| Santiago Ferreira (RC) | 5 | 5 | Clean 7-repo wave→main merge sequencing + branch retention; hold at max |
| Aino Virtanen (Standards) | 5 | 5 | Ontology + gate hygiene; hold at max |

### Data-Acquisition / Pipeline (the data-first sweep)
| Rated | Old | New | Reason |
|---|---|---|---|
| Kwesi Boateng | 5 | 5 | Top implementer (5 PRs: L1/L3/L4/L5 adapter light-ups + T0-B conformance gate), all clean, theme-fit; hold at max |
| Ivana Horvat | — | +1 (cap 5) | NEW Itqan adapter — largest narrator source (115k profiles) integrated clean, single PR, no CR |
| Farhan Malik | — | +1 (cap 5) | Historical-overlay enrichment (new HistoricalEvent node + ACTIVE_DURING links) delivered solo + clean |
| Alejandra Reyes-Fuentes | 5 | 5 | X1 cross-source resolution + L6 sanadset, clean; hold |
| Jean-Claude Habimana | — | hold | X2 cross-sect PARALLEL_OF + T0-A source_id scheme, clean |
| Nikolaos Papadopoulos | 5 | 5 | Thaqalayn Shia E2E, clean; hold |

### Isnad-Graph (admin surface + search + enrich)
| Rated | Old | New | Reason |
|---|---|---|---|
| Idris Yusuf | 4 | 4 | 3 PRs (OBLITERATE reset UI, admin-404 restrict, us bootstrap-admin); 1 CR on the destructive reset UI = appropriate rigor; clean trajectory, hold |
| Jun-Seo Park | — | +1 (cap 5) | Data-mgmt panel + empty-q search no-op, both clean, no CR |
| Aisling Brennan | — | hold | Narrator fulltext index + lockfile bump, clean |
| Ingrid Lindqvist | 5 | 5 | User-mgmt panel rewire to user-service admin API, clean; hold |
| Rohan Wickramasinghe | — | hold | DS-alignment audit landed but took 2 CR cycles (scope/format iteration) — net neutral |

### Deploy
| Rated | Old | New | Reason |
|---|---|---|---|
| Aisha Idrissi | — | hold | Delivered the real v2 promote-gate fix (#425 env-prefix) + runtime-config smoke (#420); **but** the first RCA (#424, blamed `\r`) was wrong and shipped before reviewers reproducing BOTH invocation forms caught the real bug. Strong recovery, minor RCA-rigor note — net hold, not down |
| Weronika Zielinska | — | hold | Secrets-manager ADR 0007 authored clean with owner A+B decision recorded |

### Landing-Page (design-system alignment)
| Rated | Old | New | Reason |
|---|---|---|---|
| Marcia Vasquez-Paredes | — | +1 (cap 5) | 3 clean PRs (monogram retint, data-theme resolution fix, canonical-origin fix) + rebase choreography; the theme fix is what makes DS semantic tokens resolve at all |
| Cédric Novak | — | +1 (cap 5) | DS iconography PR clean AND caught the byte-1300 `<meta charset>` regression in review (real i18n defect, well-measured) |
| Kwame Mensah-Williams | — | hold | Match look&feel via DS semantic tokens, clean |
| Nadia Rahman | — | hold | Regression coverage for lp#69 symptom classes, clean |
| Amara Diop-Sarr | — | hold | The Team page (7 bio cards); 1 CR (bio-card iteration), landed clean |

### Ingest-Platform
| Rated | Old | New | Reason |
|---|---|---|---|
| Léopold Mbongo | — | hold | HTTP reset endpoints (1 CR on the admin surface = appropriate) + pip PYSEC bump, both clean |

### Orchestrator (Self-Assessment)
| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| **Orchestrator (Steven via Claude)** | 4 | 4 | (hold) Drove the largest wave on record (34 PRs/7 repos) to a clean wrap with exact counter fidelity; **honestly corrected** an optimistic "app probably rolled fine" prod read after SSH ground-truth showed caddy/frontend stuck `Created` (total 521 outage), then recovered non-destructively (targeted `up -d frontend caddy`) and held the kafka volume-wipe for pipeline-owner sign-off. **Hold-not-promote:** two self-caught process slips this wave — a premature `gh issue close 970` paired in-batch with an unverified #984 merge (reopened), and the optimistic outage read before ground-truth. Both caught + corrected, but promotion wants a wave with no self-inflicted slip. |

### Done Well / Needs Improvement (Phase 4 Wave 3)
- **Done well:** the data-first thesis delivered at scale (multi-source Sunni+Shia ingestion light-up + Itqan's 115k narrators + cross-sect PARALLEL_OF); most-distributed wave on record (19 implementers, 15% concentration); review rigor landed exactly where it should (every CR cycle on a destructive/security/visual-correctness surface); reviewer catches were real (Cédric's charset regression, the both-invocation-form repro that caught the #424 wrong-RCA).
- **Needs improvement (orchestrator):** (1) never pair `issue close` with an unverified PR `merge` in one batch — confirm `merged:true` first (memory [[feedback_parallel_panels_shared_file_serialize]]); (2) lead prod-incident reads with SSH ground-truth, not the compose dependency graph; (3) RCA discipline — reviewers must reproduce the FAILING invocation form, not an accidentally-correct one (memory [[feedback_passing_repro_masks_bug_wrong_invocation_form]]).

## Phase 4 Wave 4 Trust Updates (2026-06-12) — Data fan-out, FE light-up & standardization

### Org-Level + Child-Repo Team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Ingrid Lindqvist (ig) | 5 | 5 | Owned the full FE color chain; headless-Playwright-verified each step; surfaced+escalated the @theme-no-op constraint instead of shipping a silent break; absorbed heavy (orchestrator-caused) vehicle churn cleanly. Maintain at ceiling. |
| Junseo Park (ig) | new | 4 | Rigorous ig#1002 review surfacing the real DS-publish-drift adjacent finding (→DS#111); re-verified against ground truth and owned the wrong primary conclusion transparently. Strong first appearance. |
| Nino Kavtaradze (deploy) | 5 | 5 | Caught CWE-214 (DB password on argv) on #435 with a verified one-line fix. Maintain. |
| Oyunbileg Batbayar (da) | 5 | 5 | Caught the #118 fuzzy-cluster over-merge pre-merge. Maintain. |
| Idris Yusuf (ig) | — | 4 | Independently registry-verified the #1006 CVE base-image digest before approving. Solid security review. |
| Mateo Rossi (ig) | new | 4 | Independent registry verification of the #1006 digest; clean infra review. |
| Lucas Ferreira (deploy) | 5 | 5 | #426 admin-bootstrap (gate-isolated, no-op-safe) + #1006 CVE fix; verified env-path correctness, not blind. Maintain. |
| Ravi Desai (ux/ig) | new | 4 | Mechanical token-mapping reviews (#999/#1002/#1003 — 65 @theme keys 1:1); retargeted #1001→#1003 himself on the vehicle swap. |

### Done Well / Needs Improvement (Phase 4 Wave 4)

**Done well:** review rigor caught every real defect pre-merge (CWE-214, over-merge, DS-publish drift, CVE digest); FE color system shipped correctly (owner's correct-over-expedient call); data-first core landed.

**Needs improvement (orchestrator):** (1) state-toggle churn on #1001 (serial contradictory close/reopen instructions crossing the agent's actions); (2) merged #1002 at 2/3 reviewers before the deliberately-assigned 3rd (build/dep) lens finished. Both are charter-proposal items this retro.

## Phase 4 Wave 5 Trust Updates (2026-06-13) — Exit drive: verify → audit & close → tech-debt intake

### Org-Level + Child-Repo Team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Aisha Idrissi (ig) | — | +1 (cap 5) | #601 verification surfaced Phase-4 end-state #1 NOT MET on staging (zero narrator graph, pipeline never ran), evidenced via ssh + cypher-shell — prevented a false Phase-4 exit and seeded the P4W6 spine. Highest-value contribution of the wave. |
| Nino Kavtaradze (deploy) | 5 | 5 | Caught a CWE-214 awk-argv leak on #438 (2nd consecutive wave catching an argv-on-cmdline class) + ran #605 security audit with a live curl 403-verify. Maintain at ceiling. |
| Ingrid Lindqvist (ig) | 5 | 5 | Clean #1012 delivery, 0 CR. Maintain at ceiling. |
| Astrid Lindqvist (ds) | — | +1 (cap 5) | Clean #113 delivery, 0 CR. |
| Nurul Hakim (deploy) | — | +1 (cap 5) | Clean #437 delivery, 0 CR. |
| Santiago Ferreira (main/release) | — | hold | Clean #648 (trivial cspell CR, edited-in-place) + ran the wave wrapup. |
| Marisol Vega-Cruz (ig) | — | hold | #1014 coverage-honesty gap (omitted /billing/checkout) caught by review + addressed. Minor. |
| Lucas Ferreira (deploy) | 5 | hold | #438 addressed both CRs cleanly, but shipped a CWE-214 argv-leak into review (caught by Nino) — same class as W4's deploy argv finding. Process clean; net-neutral. Forward ask: secure-by-construction on the argv surface. |
| Aino Virtanen (standards) | — | hold | Clean #604 audit; authored this retro. |
| Wanjiku Mwangi (tpm) | — | hold | #607 verification MET, clean. |

### Orchestrator (Self-Assessment)
| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| **Orchestrator (Steven via Claude)** | 4 | 4 | (hold) Clean wave wrap with exact counter fidelity (6/3/17, claimed==recomputed); ran a disciplined Option-A disposition (#601 not-met, dup-searched 3 gaps, mirrored #602/#603 precedent) and an honest live-staging exploratory pass that source-verified 2 real auth bugs before filing. **Hold-not-promote:** the #601 not-met state itself reflects a prior-wave gap (W4 "data-first shipped" lore was harness-only) that should have been caught at W4 wrapup, not W5 — the live-env-verification charter change (#1) is the fix. |

### Done Well / Needs Improvement (Phase 4 Wave 5)

**Done well:** honest verification cited live-env evidence (#601 ssh/cypher, #605 curl-403) not harness; best load distribution on record (17%, 6/6 distinct authors); the 2-reviewer gate caught a real CWE-214 leak + a coverage-honesty gap pre-merge; the baseline exploratory Chrome pass found a high-impact forced-logout-on-401 bug (ig#1016) in ~2 minutes.

**Needs improvement (org):** (1) "shipped in CI ≠ shipped on the VPS" — end-state claims weren't validated against the deployed env until a wave late (charter change #1); (2) Lucas's recurring argv-leak class on the deploy surface (2 waves running) — a secure-by-construction lint/review-lens follow-up may be warranted if it recurs.

## Phase 4 Wave 6 Trust Updates (2026-06-13) — Real data on the VPS

### Org-Level + Child-Repo Implementers
| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Alejandra Reyes-Fuentes | 5 | 5 | Wave MVP — found+fixed the #601 root cause, produced the real data, clean load-only path + gated-run spec; already at ceiling, maintain at 5 |
| Bjørn Henriksen | 3 | 4 | Mechanism-only delivery, refused to auto-fire live infra, thorough verified gated-run advisory |
| Aisha Idrissi | 5 | 5 | Profile-gating safety call + latent topic fix + image contract; maintain at ceiling (at 5 since W5) |
| Imelda Santos | — | 4 | First numeric rating (prior appearances were prose-only): null-safe loader fix + caught ingest-path key drift + real-neo4j regression |
| Kavitha Sundaramurthy | — | 4 | First numeric rating: durable edge-relation routing fix, clean 2/2 |
| Jun-Seo Park | 4 | 4 | Single-flight refresh, sound security framing, proactive follow-up flag; hold (at 4 since W4) |
| Ingrid Lindqvist | 5 | 5 | Clean fix + exemplary self-flagged rebase re-review discipline; maintain at ceiling (5 since W3, three waves running) |
| Aino Virtanen | 5 | 5 | Clean /wave-start fix + extra drift sweep; maintain at ceiling |

### Reviewers
| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Nikolaos Papadopoulos | 5 | 5 | Caught the da#120 dup (saved redundant work) + thorough root-cause verification; maintain at ceiling (5 since W3) |
| Nadia Khoury | 5 | 5 | Caught a real doc-drift miss AND the trust-matrix baseline error on this very retro; maintain at ceiling |
| Camila Restrepo | — | 3 | First numeric rating; HOLD — stale-tree misread cost a critical-path cycle (−), honest immediate self-correction on disproof (+); net flat at 3 |

### Orchestrator (Self-Assessment)
| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Orchestrator (Steven via Claude) | 4 | 4 | (hold) Drove the #601 live load to a verified MET — real narrator graph on staging, on-box-only credentials, checkpointed gating, honest batch-vs-streaming framing. Hold-not-promote: two self-inflicted slips — reviewer briefs omitted the mandatory TechDebt attestation line (blocked the first merge; 7 verdicts retrofitted), and a compound-command label apply silently skipped the kickoff hook (main#650, recurred). Both owned + corrected; promotion wants a slip-free wave. |

### Done Well / Needs Improvement (Phase 4 Wave 6)
- **Done well:** independent verification over deference (reviewers + orchestrator both verified peer claims against artifacts — reviewers also caught the trust-matrix baseline error on this retro); risk-gating of live infra; fully-distributed load (8/8 implementers).
- **Needs improvement (orchestrator):** use the verbatim reviewer-brief template (TechDebt line) — its omission blocked the first merge; avoid compound-command label applies (main#650).

## Phase 4 Wave 7 Trust Updates (2026-06-14) — Phase 4 close-out & exit

### Implementers + Reviewers
| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Aino Virtanen (standards) | 5 | 5 | Implemented main#650 — root-caused the issue's own "split on `;`" framing as a **misdiagnosis** and fixed the real bug (shared parser required `--repo`, silently dropping in-repo label edits); repo-Optional + ambient-repo recovery, both hook consumers benefit, DI-tested, 8/8 CI. Maintain at ceiling. |
| Weronika Zielinska (platform/deploy) | 5 | 5 | Dual contribution: clean surgical deploy#413 (2-line read-back wording, shellcheck-clean) AND peer review on #658 that **independently verified** Aino's misdiagnosis claim (not rubber-stamped) + surfaced the CREATE-path sibling gap (#659). Maintain at ceiling. |
| Nino Kavtaradze (deploy/security) | 5 | 5 | Reviewed **both** wave PRs (security angle): cleared the #658 injection surface (argv-form git, no shell), confirmed safe failure mode, independently named the same CREATE-path sibling + a charter-promotion candidate. Maintain at ceiling. |
| Aisha Idrissi (deploy/SRE) | 5 | 5 | Secondary review on deploy#447 — operator-clarity verdict + a useful retro micro-watch (operator-facing string drifted out of sync with the authoritative in-code comment). Maintain at ceiling. |

### Orchestrator (Self-Assessment)
| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Orchestrator (Steven via Claude) | 4 | 4 | (hold) Clean close-out wave: 2 PRs, 4 first-pass Approved reviews, **0 CR cycles**, counters exact (2/0/50, claimed==recomputed), all wrapup gates passed. Directly remediated the W6 promotion-blocker — main#650 (the compound-label-apply skip) was **root-fixed** this wave, not worked around; all 4 verdicts carried the TechDebt line + PR-head-SHA confirmation first-pass (W6's blocker did not recur). Hold-not-promote: two minor self-inflicted recoverable slips — an `echo "$RESP" \| jq` round-trip mangled a large status PUT (409, recovered via `--jq` fetch) and a zsh word-split bash-ism (`set -- $ref`) in a retro query (recovered). The W6 bar was a slip-free wave. |

### Done Well / Needs Improvement (Phase 4 Wave 7)
- **Done well:** root-cause discipline beat issue-framing (Aino disproved the issue's prescribed fix and root-fixed the real bug); reviewers independently verified peer claims AND converged un-prompted on the same forward-looking sibling gap (#659); thin-wave hygiene held (TechDebt + head-SHA on all 4 verdicts first-pass).
- **Needs improvement (orchestrator):** prefer `gh api --jq` over `echo "$RESP" \| jq` for large API payloads (avoids the shell-mangle 409 class); keep Bash-tool commands zsh-safe (no `set -- $unquoted` word-split assumptions).

