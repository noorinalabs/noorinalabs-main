# Feedback Log — Phase 4 archive

> Archived byte-for-byte from `.claude/team/feedback_log.md`
> at phase close (#964, meta #960), preserving original file order. Do not edit —
> append-only history; new entries go to the live file for the current phase.

---

## Retrospective: Phase 4 Wave 1 — 2026-06-10

**Theme:** Clean slate — bugs + security + tech-debt burn-down (first wave of Phase 4).

### Team Performance
23 PRs merged across 7 repos; 7/7 wave→main merges (branches retained per the 2026-06-09 every-wave-merge directive); **1 changes-requested cycle** (deploy#415); **0 failing CI checks** at any PR head; **staging promotion green**. All counters reconciled at retro with **zero drift** (PR count 23=23, concentration 13%=13%, CR cycles 1). Ontology current (0 dirty). Top-implementer concentration **13%** (Nurul Hakim & Aisha Idrissi tied at 3) — the most distributed wave on record, theme-fit (broad burn-down, not single-owner domain).

### Per-Engineer Assessments
- **Nurul Hakim** — 3 PRs (deploy#384 security, observability scrape, main#596). Joint top-implementer, fourth consecutive clean wave. Hold at 5. No improvement items.
- **Aisha Idrissi** — 3 PRs (deploy#395/#398 tech-debt). Joint top-implementer, clean. Hold at 5. None.
- **Lucas Ferreira** — deploy#402/#86/#410 + main#613; authored the live-session deploy#418 root-cause fix. Hold at 5. None.
- **Nino Kavtaradze** — deploy#386 + #244 security tier. Hold at 5. None.
- **Mateo Salazar** — us#65 (config-URL), us#74 (OAuth SQLAlchemyError). Clean. Hold at 4, positive trajectory toward 5.
- **Idris Yusuf** — us#73 + isnad-graph#955 (both security). Clean; rebuilding after the W15 #872 anti-pattern note. Hold at 4, positive.
- **Single-PR clean delivery:** Weronika Zielinska, Marcia Vasquez-Paredes, Kwesi Boateng, Kofi Mensah-Williams, Kofi Mensah, Keanu Tama, Ingrid Lindqvist, Cédric Novák, Aino Virtanen.

### Wave-shape table
| Metric | Value |
|--------|-------|
| PRs merged | 23 |
| Repos touched | 7 |
| Changes-requested cycles | 1 (deploy#415) |
| Failing CI at head | 0 |
| Staging promotion | success |
| Top-implementer concentration | 3/23 = 13% (Nurul Hakim / Aisha Idrissi, tied — theme-fit) |

### Top 3 Going Well
1. **Most-distributed wave on record (13%)** with zero CI failures and a single CR cycle across 23 PRs — broad burn-down executed cleanly with no fragility concentration.
2. **Security tier fully landed** — scrape-block pair (deploy#384/#386), isnad-graph#955, and the deploy#244 OAuth dual-env setup (stg + prod IDs/secrets, callback URLs fixed, staging verified live this session).
3. **Honest gate handling end-to-end** — counters reconciled with zero drift; staging promotion genuinely green; the live deploy#418 defect was diagnosed to root (not the first-hypothesised cause) and fixed + gated rather than patched over.

### Top 3 Pain Points
1. **Latent deploy#418 defect shipped through W1 undetected** — `deploy-stg.yml` applied the dispatching service's sha to a single `IMAGE_TAG` (api+frontend), so every user-service-only merge broke the staging image pull. Never caught because no user-service-only stg deploy exercised the path and no gate existed. Fixed this session (PR#419) + monitoring added (`/watch-deploy`, main#623/PR#624).
2. **Commit-identity hygiene** — deploy#409 was authored as bare `parametrization` (not a roster identity); `Kofi Mensah` (design-system#54) vs `Kofi Mensah-Williams` (landing-page) is an unreconciled cross-repo persona divergence. Both evade the per-commit identity convention's intent.
3. **Annunaki error-log pollution** — `errors.jsonl` accumulated 17 benign `posttooluse_dispatch` traces (from `suggest_generic_prompt`) with no exit code or pattern, inflating `/annunaki`'s "error" count and able to misdirect `/annunaki-attack`. Filed main#625.

### Proposed Process Changes
1. **`/watch-deploy` step — DONE this session** (main#623/PR#624). Codifies active per-merge deploy monitoring (stg auto, prod post-approval) + bounded fix-forward, wired into `/wave-wrapup` Step 11.6a. Closes the detection gap that let deploy#418 self-heal-by-luck. *No approval needed — already shipped.*
2. **Commit-identity verification at PR-merge time** — Rationale: deploy#409 (bare `parametrization`) and the Kofi divergence show the per-commit `-c` identity convention has no machine check. Propose a small hook/CI gate that asserts each wave PR's head-commit `author.name` is a known roster name (and flags bare `parametrization`). Enforcement-hierarchy: hook > charter. *Owner decision required.*
3. **Separate annunaki dispatch-traces from errors** — Rationale: main#625. `errors.jsonl` should hold only genuine failures; `/annunaki` + `/annunaki-attack` should ignore `posttooluse_dispatch` traces. *Filed; next-wave tech-debt.*

### Annunaki-Attack — p4-wave-1
**0 genuine errors this wave.** The 17 records in `errors.jsonl` are all benign `posttooluse_dispatch` traces from `suggest_generic_prompt` (config/memory-edit suggestions), carrying no exit code or pattern — not failures. The pollution itself is the only finding → filed **main#625** (log hygiene). No fixes to attack. Marker written.

### Memory-to-Automation Audit — p4-wave-1
One memory added this wave (`feedback_stg_deploy_per_service_tag_routing`) — correctly memory-tier (single-instance deploy heuristic, too fresh to promote). The audit's standing promotion candidate is **process change #2** (commit-identity verification), surfaced here as a hook-tier proposal for owner decision rather than auto-applied (hooks are security-sensitive — D6). No other memory crossed a promotion threshold. Marker written.

## Retrospective: Phase 4 Wave 2 — 2026-06-11

**Theme:** Pipeline first light + auth account-linking. **Result: the data-first thesis delivered** — real Riyad us-Salihin hadiths live in staging Neo4j + a frontend-renderable graph, and the *real* pipeline run flushed out three mock-masked production bugs (all fixed in-wave).

### Team Performance
- **11 PRs merged** (8 to wave branches + 3 direct to ingest-platform main), **12 wave issues closed**, 1 CR cycle (Santiago→#630 merge-commit false-positive; fixed + re-approved), 25% top-implementer concentration (Kwesi/Aino tied at 2 — healthy distribution). Staging promotion GREEN. Zero genuine team-code CI failures (only pre-existing advisory/CVE drift).
- 3 production bugs surfaced by going live, each the same pattern (no-op test fake hiding a real-infra failure): da#77 (APPEARS_IN null-MERGE abort), ig#63 (Hadith id double-prefix), ig#69 (reset bulk delete_objects MissingContentMD5). First two fixed in-wave; ig#69 is a tracked fast-follow with the failing path xfail-guarded.

### Per-Engineer Assessments
- **Kwesi Boateng** (da#73 keystone, da#77 loader fix) — keystone vertical slice + live staging load + null-safe MERGE-on-pair fix + the in-book-ordinal evidence graph + flawless da-cluster rebase choreography (trial-rebased before flagging). Caught + owned an over-statement in his own rebase evidence. **Severity: none; exemplary.**
- **Alejandra Reyes-Fuentes** (da#72) — scraper hadith_number fix; proactively converged to the *more honest* in-book-ordinal extraction (folded da#78 into a #75 amend) rather than the easier collection-ref. **none; strong.**
- **Oyunbileg Batbayar** (da#69) — edge-key real-graph assertion; caught a masked empty-graph fixture bug AND the Neo4j SET-null-removes-key subtlety, advised Kwesi pre-PR. **none; strong.**
- **Nikolaos Papadopoulos** (main#139/ig#62) — faithful in-process E2E harness + live-Neo4j run; found the id double-prefix via a realistic fixture; drove cross-PR contract alignment. **none; strong.**
- **Aino Virtanen** (main#627, main#625) — identity gate + annunaki dual-stream, both clean; the **honest #136 duplication audit** (found her own PR redundant) + the #634 sibling-roster-CI catch are the integrity high-water mark of the wave. **none; exemplary.**
- **Tomás Carvalho** (ig#63 fix, main#136) — comprehensive worker-chain E2E; xfail-with-diagnosis on the reset bug rather than hide-or-fix-mid-PR (surfaced ig#69). **none; strong.**
- **Mateo Salazar** (us#153/154) — coherent single-guard for the coupled auth bugs + real-Postgres-container proof. **none; strong.**
- **Ingrid Lindqvist** (ig#956) — config component-env fix mirroring us#65, percent-encoding + backward-compat + URL-hostile-password tests. **none.**
- **Reviewers** (Idris gating-security on auth, Anya, Jean-Claude, Imelda, Sayed, Arjun, Santiago, Wanjiku) — rigorous, read-at-HEAD, several caught real issues (Santiago's merge-commit gate bug; Oyunbileg's SET-null). **none.**

### Top 3 Going Well
1. **Data-first paid for itself** — going live didn't just produce a graph, it forced the real pipeline and exposed 3 mock-masked production bugs that all green test suites had sailed past.
2. **Integrity culture** — the test-mock-masks-production pattern was named and hunted repeatedly; Aino closed her own redundant PR; Kwesi corrected his own evidence over-statement; Tomás xfail-documented rather than buried a bug.
3. **Self-organizing cross-PR contract alignment** — the da-cluster (da#72/#75 ↔ da#77 ↔ ig#63) was negotiated peer-to-peer to a mutually-consistent design with zero merge surprises.

### Top 3 Pain Points
1. **Verdict-attestation brief gap (orchestrator)** — reviewer briefs said "TechDebt line *if any*" instead of "always `none`/`#N`"; ~13 verdicts merge-blocked until transcribed. Brief-template fix needed.
2. **Advisory-gating on ingest main** — a *required* security-audit check turned red by an external pip-CVE forced `--admin` on 3 merges. The org-wide-non-blocking-gate rule says advisory checks must be continue-on-error.
3. **Crossed-message churn (#136 + dup issues)** — parallel agents + lagging inboxes caused repeated reopen/close cycles and a near-double-file of the reset bug. Mitigated only by verifying state at origin before every action.

### Proposed Process Changes
1. **Reviewer-brief template: require `TechDebt: none`/`#N` on EVERY verdict** (not "if any"). Rationale: validate_pr_review enforces it always; the conditional phrasing blocked 13 merges.
2. **Advisory CI checks → `continue-on-error` / non-required** (esp. ingest security-audit). Rationale: external advisory publication shouldn't hard-gate unrelated PRs (org-wide-non-blocking-gate pattern). Folds into main#633.
3. **Kickoff status pointer writes go to the wave branch, not main** — writing `current_wave`/`kicked_off_at` to main via PUT-contents while the wave branch also edits cross-repo-status.json caused the sole wave→main conflict. Rationale: keep the file's authority on one branch during a wave.
4. **Re-affirm origin-state-verification before destructive/structural action** — caught a falsely-reported "closed #67" and a dup-of-dup issue close by checking origin first. (Already charter; reinforce.)

## Retrospective: Phase 4 Wave 3 — Open the doors: real data in a usable product — 2026-06-12

### Team Performance
34 PRs merged across 7 repos; 1 issue closed at wrap (ig#967, audit shipped); **42 issues carried to W4** (owner directive: carry all remaining). 19 distinct implementers, top-concentration 15% (Kwesi Boateng 5/34 — theme-fit). 6 changes-requested cycles, 0 CI failures on merged PRs, staging promotion green. Wave branches retained in all 7 repos.

**Counter verification (Step 2.5):** all three wrapup counters matched the retro recompute exactly — final_pr_count 34=34, changes_requested_cycles 6=6, top_concentration_pct 15=15. **Zero drift** (first wave with no counter correction needed).

### Wave Shape
| Metric | Value |
|---|---|
| PRs merged | 34 |
| Repos | 7 (main, isnad-graph, user-service, deploy, landing-page, data-acquisition, ingest-platform) |
| Distinct implementers | 19 |
| Top-implementer concentration | 5/34 = 15% (Kwesi Boateng — theme-fit, da adapter sweep) |
| Changes-requested cycles | 6 (#984, #982×2, #129, #123, #73) |
| CI failures (merged) | 0 |
| Staging promotion | success |
| Prod incidents | 1 (deploy path, recovered) |

### Per-Engineer Assessments
- **Kwesi Boateng** (da) — 5 PRs (L1/L3/L4/L5 adapter light-ups + T0-B conformance gate), 0 CR, 0 CI fail. Top implementer, theme-fit. Severity: none.
- **Ivana Horvat** (da) — Itqan adapter (115k narrators), 1 PR clean. Severity: none. (+1 trust)
- **Farhan Malik** (ig) — historical-overlay enrichment, 1 PR clean. Severity: none. (+1 trust)
- **Idris Yusuf** (ig/us) — 3 PRs (OBLITERATE reset UI, admin-404, bootstrap-admin); 1 CR on destructive reset UI (appropriate). Severity: none.
- **Aisha Idrissi** (deploy) — 3 PRs (real v2-gate fix + runtime-config smoke). First RCA (#424, `\r` theory) wrong, superseded by real fix #425; reviewers caught it via both-invocation-form repro. Severity: minor (RCA rigor) — strong recovery.
- **Marcia Vasquez-Paredes** (lp) — 3 clean PRs incl. the data-theme fix that makes DS tokens resolve. Severity: none. (+1 trust)
- **Cédric Novak** (lp) — DS iconography PR + caught the byte-1300 charset regression in review. Severity: none. (+1 trust)
- **Jun-Seo Park** (ig) — data-mgmt panel + empty-q no-op, clean. (+1 trust)
- **Rohan Wickramasinghe** (ig) — DS audit, 2 CR cycles (format iteration), landed clean. Severity: minor.
- Clean, no-significant-signal (hold): Reyes-Fuentes, Habimana, Papadopoulos, Brennan, Lindqvist, Mensah-Williams, Rahman, Diop-Sarr (1 CR, bios), Mbongo (1 CR, reset endpoint), Zielinska.

### Top 3 Going Well
1. **The data-first thesis delivered at scale** — multi-source Sunni+Shia ingestion lit up end-to-end (L1–L6 adapters), Itqan's 115k narrator profiles integrated, cross-sect PARALLEL_OF detection, historical overlay. Real data is in the product.
2. **Most-distributed wave on record** — 19 implementers, 15% concentration (down from 13% floor seen W1 but across nearly 3× the PR volume). No fragility concentration.
3. **Review rigor landed exactly where risk was** — every one of the 6 CR cycles was on a destructive/security/visual-correctness surface (OBLITERATE reset, reset endpoint, DS-audit, theme/charset, team bios). Reviewer catches were real (Cédric's charset regression; the both-form repro that caught the #424 wrong-RCA).

### Top 3 Pain Points
1. **First real v2 prod ship caused a total outage** — `docker compose up --wait` over the FULL prod stack let an unhealthy NON-app service (kafka, dirty bitnami-era volume) abort the dependency-ordered bring-up before caddy/frontend started → 521 total edge outage even though the app + its deps were healthy. Three distinct deploy-path gaps surfaced (deploy#427 transitive-skip, #428 kafka dirty-volume, #429 `up --wait` non-app abort), all filed + carried to W4. Recovery was non-destructive (targeted `up -d frontend caddy`).
2. **A wrong RCA shipped before the real one** — deploy#424 (whitespace-strip, blamed `\r`) was approved by 2 reviewers and merged, but the v2 gate still failed post-merge; the real bug (key passed as python argv not env-prefix → KeyError → empty digest) was only caught when reviewers reproduced BOTH invocation forms for #425. A passing repro that used the accidentally-correct env-prefix form masked it. (Memory written: passing-repro-masks-bug-wrong-invocation-form.)
3. **Orchestrator process slips (self-caught):** (a) paired `gh issue close 970` in-batch with an unverified #984 merge that then conflicted — issue closed with PR unmerged, had to reopen; (b) gave an optimistic "app probably rolled fine" prod read from the compose graph before SSH ground-truth showed caddy/frontend stuck `Created`.

### Proposed Process Changes
1. **Tier the prod rollout `up` — app+edge must come up independently of pipeline/analytics services.** Scope the prod `docker compose up --wait` to api/frontend/caddy + their real deps; bring the pipeline tier up non-gating. — Rationale: pain point #1; a broker hiccup must never down the reverse proxy. (Tracked: deploy#429.)
2. **Charter/skill: never pair an `issue close` with a PR `merge` in the same un-guarded batch — confirm `merged:true` first.** — Rationale: pain point #3a; companion to the existing wave-branch-issue-close rule. (Memory [[feedback_parallel_panels_shared_file_serialize]] already captures this; promotion candidate.)
3. **Reviewer briefs for "fix verified locally" PRs must require reproducing the FAILING invocation form (red) before the fix (green).** — Rationale: pain point #2; an accidentally-correct repro proves nothing. (Memory [[feedback_passing_repro_masks_bug_wrong_invocation_form]]; promotion candidate.)

### Audits
- **Annunaki-attack:** 3 errors captured, all benign — 2× `enforce_librarian_consulted` PreToolUse blocks (Hook 15 working as intended) + 1× `post_label_change_wave_field_sync` telemetry event. No actionable errors; no new automation needed.
- **Memory-to-automation:** the wave's new memories are judgment-class feedback (RCA rigor, merge-serialization, prod-incident discipline) — kept as memory; two (#2, #3 above) are charter/skill promotion candidates surfaced to the proposal block. No clear new-hook candidate.

## Retrospective: Phase 4 Wave 4 — Data fan-out, FE light-up & standardization, CI/deploy/auth hardening — 2026-06-12

### Team Performance
38 PRs merged across all 8 repos (da 14, ig 10, deploy 4, ds 3, ingest 3, us 2, lp 1, main 1); all 8 wave→main PRs merged, reachability 0-stranded. Issues: all p4-wave-4 closed (0 open). Staging: green after the post-merge CVE fix-forward (ig#1006). CR-cycles: 5 (all edited-in-place to Approved — residual recompute 0). Top-implementer concentration: **13% (Ingrid 5/38)** — healthy, theme-fit (FE color chain). Tech-debt/follow-ups filed: DS#111 (DS :root republish hygiene), ig#1005 (openssl CVE, fixed via #1006), ig#969 (exploratory sweep, W5), deploy#387 (DB-rotation, ADR-blocked, W5), da#133 (edge-relation field), ig#993/#998, ds#110.

### Per-Engineer Highlights
- **Ingrid Lindqvist (5 PRs)** — owned the entire FE color chain (#979 ForceGraph, #980 cleanup, #1000/#1002 the @theme bridge, #981/#1001/#1003 full migration). Verified every step with headless-Playwright computed-style parity (light+dark); proactively surfaced the @theme-no-op constraint and escalated rather than shipping a silent break; absorbed heavy orchestrator-caused vehicle churn without losing the work. Exemplary. Severity: none (strong positive).
- **Junseo Park (reviewer)** — deep ig#1002 review: reached the wrong conclusion (inert/transparent) but via genuinely rigorous analysis that surfaced a REAL adjacent issue (DS#107 :root fix never published → DS#111). Re-verified against ground truth when challenged and owned the error transparently. Model reviewer behavior. Positive.
- **Nino Kavtaradze (reviewer)** — caught CWE-214 (DB password on argv → /proc/cmdline) on deploy#435 with a one-line drop-in fix; verified the env-path correctness before approving. Positive.
- **Oyunbileg Batbayar (reviewer)** — caught the da#118 fuzzy-cluster over-merge (single-token-subset + transitive-bridge) pre-merge. Positive.
- **Idris Yusuf + Mateo Rossi (reviewers)** — independently registry-verified the ig#1006 base-image digest (buildx imagetools / docker-content-digest) before approving the CVE fix. Positive.
- **Lucas Ferreira** — deploy#426 admin-bootstrap wiring (gate-isolated, no-op-safe, idempotent) + the #1006 CVE fix-forward; verified env-path correctness, not blind drop-ins. Positive.
- **Data-acquisition cohort (14 PRs)** — landed the data-first core (real NARRATED/STUDIED_UNDER edges from scraped data, Bihar adapter, both-sects parallels).

### Top 3 Going Well
1. **Data-first core shipped** — real edges firing from scraped data; both-sects Browse Parallels; Bihar adapter. The owner's data-first priority materialized.
2. **FE color system done RIGHT, not expedient** — owner's correct-over-expedient call ([[feedback_no_users_prefer_correct_over_expedient]]) drove the @theme bridge that lit up DS color tokens as real Tailwind utilities app-wide, fixing latent no-op bugs (AuthCallback/SearchPage/ProtectedRoute). Verified against the pinned dep via [data-theme] ground truth.
3. **Review rigor caught real issues pre-merge** — CWE-214 (Nino), over-merge (Oyunbileg), DS-publish drift (Junseo), CVE digest verification (Idris/Mateo). The 2-reviewer (+3rd for blast-radius) gate did its job; the wave shipped no silently-wrong code.

### Top 3 Pain Points
1. **Orchestrator state-toggle churn (my failure)** — I issued contradictory close/keep-open/reopen instructions on PR #1001 that crossed Ingrid's in-flight actions, causing a #1001↔#1003 thrash (~6 round-trips of pure PR-state toggling). Root cause: issuing SERIAL corrections that each cross the agent's last action. Resolution that worked: read the agent's CURRENT actual state, issue ONE instruction aligned to it that requires no toggle, and explicitly void all priors.
2. **Merged #1002 on the 2-reviewer gate before the deliberately-assigned 3rd reviewer finished** — Junseo (the build/dependency lens) posted ChangesRequested AFTER I merged. It resolved as non-blocking, but on a blast-radius change where a 3rd reviewer was assigned precisely for that lens, merging at 2/3 was luck, not discipline.
3. **Post-merge advisory/config drift gated staging** — openssl CVE-2026-45447 (Alpine base-image drift) reddened the frontend publish at wrapup (caught by Step 11.6a, fixed forward via #1006); and the Project-2 Wave field was missing P4W4 (annunaki: ~8 sync-hook failures). Both are recurring "drift" classes (cf. pip-audit advisory drift, ProjectV2 field-option).

### Proposed Process Changes (charter)
1. **State-correction discipline** — when correcting a spawned agent's PR/issue state, read its CURRENT state first and issue ONE instruction aligned to it; never a serial close/reopen toggle. Explicitly supersede priors in the same message. (charter agents.md / state-claims.md)
2. **All-assigned-reviewers gate for blast-radius PRs** — when 3+ reviewers are deliberately assigned (app-wide / cross-repo blast radius), do NOT merge on the 2-reviewer minimum; wait for every assigned reviewer. (charter pull-requests.md)
3. **Base-image CVE freshness at publish-merge** — session-start 5a / wrapup 11.6a should flag when a fan-in repo's last publish is red on a base-image CVE, so it's surfaced before wrapup rather than at it. (skills)

### Annunaki-attack
Wave field P4W3/P4W4/P4W5 options added to Project 2 (remediates the ~8 sync-hook failures); other 76 captured lines are skip_parser_returned_empty (known multi-cmd shape) + transient dev-cmd noise. No new hooks warranted.

### Memory-to-automation audit
New memories this wave ([[feedback_no_users_prefer_correct_over_expedient]], [[project_ds_theme_color_utilities_noop]]) are correctly soft memories (owner preference + project gotcha, the latter partly tracked by DS#111). No memory crossed a hook/skill threshold; the orchestrator-discipline lessons go to the charter proposals above.

## Retrospective: Phase 4 Wave 5 — Exit drive (verify → audit & close → tech-debt intake) — 2026-06-13

### Team Performance
6 PRs merged (main 1, ig 2, deploy 2, ds 1) across 4 repos; all 4 wave→main PRs merged via the `wave-merge` admin exception, reachability 0-stranded. Staging-promotion green (post-merge redeploy success). CR-cycles: 3 current-state (+1 on #648 edited-in-place to Approved → 4 review iterations historic). Top-implementer concentration: **17% (6 PRs / 6 distinct authors)** — best distribution on record, theme-fit (audit wave spread across owners). Issues: 10/10 slate resolved — 6 code closed; #604/#605/#607 verified MET + closed; **#601 verified NOT MET → re-pulled to P4W6**. New issues filed: ip#83/da#141/ip#84 (the #601 gaps), ig#1016/ig#1017 (baseline-exploratory auth bugs), main#650 (hook parser gap) = 6.

### Per-Engineer Highlights
- **Aisha Idrissi (#601 verification)** — Standout. Her verification surfaced Phase-4 end-state #1 NOT MET on staging (47 out-of-band sunni hadiths, zero narrator graph, pipeline never run), evidenced via `ssh noorinalabs-stg` + `docker exec cypher-shell`. Prevented a false Phase-4 exit and seeded the entire P4W6 spine. Highest-value contribution of the wave. Positive.
- **Nino Kavtaradze (#605 + reviewer)** — caught a **CWE-214 awk-argv leak** on deploy#438 (second consecutive wave catching an argv-on-cmdline class — cf. W4 #435); ran the #605 security audit with a live `curl` 403-verify of the users-vhost `/metrics` block. Positive.
- **Ingrid Lindqvist (#1012), Astrid Lindqvist (#113), Nurul Hakim (#437)** — clean single-PR deliveries, 0 CR cycles. Positive.
- **Lucas Ferreira (#438)** — addressed both CRs cleanly, but shipped a **CWE-214 argv-leak** into review (caught by Nino) — same class as W4's deploy argv finding. Process clean; secure-by-construction awareness on the argv surface is the forward ask. Severity: moderate (caught + fixed pre-merge).
- **Marisol Vega-Cruz (#1014)** — a coverage-honesty gap (omitted `/billing/checkout` from the asserted set) caught by Anya/Ravi review and addressed. Minor.
- **Santiago Ferreira (#648 + ran wrapup)** — clean bar a trivial cspell-dictionary CR (edited-in-place to Approved). Positive.

### Top 3 Going Well
1. **Honest verification discipline** — #601 caught Phase-4 #1 unmet *before* a false exit; #605 was **runtime** curl-verified (403 on the live users vhost), not just "issue closed." Verification cited live-env evidence, not harness.
2. **Best load distribution on record** — 17% concentration, 6/6 distinct authors; zero fragility going into the heavier P4W6.
3. **The 2-reviewer gate earned its keep** — caught a real CWE-214 leak (#438) and a coverage-honesty gap (#1014) pre-merge; the wave shipped no silently-wrong code.

### Top 3 Pain Points
1. **"Shipped in CI ≠ shipped on the VPS"** — the W4-retro "data-first core shipped" lore was local/CI/harness only; the live staging reality (47 hadiths, no narrators, pipeline never ran) went unverified until W5's exit drive surfaced it a wave late (#601). End-state *claims* weren't validated against the deployed environment. → charter proposal #1.
2. **Wave→main integration-merge friction** — both the `validate_pr_review` 2-reviewer gate and the `--admin` exception gate fired on all 4 already-2×-reviewed wave→main PRs, needing a per-PR `wave-merge` exception. Recurring toil every wave; the expected path wasn't documented. → charter proposal #2.
3. **No live-UI exercise in the wave loop** — the baseline exploratory Chrome pass found a forced-logout-on-401 bug (ig#1016: the data client `fetchJson` emits session-expired on any 401 without attempting `refreshAccessToken()`, unlike the `/me` path) in ~2 minutes of driving the deployed app — a class nothing in the CI/harness loop exercises. → charter proposal #3.

### Proposed Process Changes (charter) — all 3 owner-approved 2026-06-13
1. **End-state criterion verification requires live-environment evidence** (not CI/harness alone). Rationale: #601 lesson — pain point #1. → `pull-requests.md`.
2. **Document the `wave-merge` admin exception as the expected wave→main path** (already-reviewed code; no fresh 2-reviewer pass). Rationale: fired 4× this wave — pain point #2. → `pull-requests.md § Wave Merge PR Verification`.
3. **Per-wave exploratory/E2E pass over the live app**, findings filed per the bug workflow. Rationale: ig#1016 — pain point #3. → `lifecycle.md` (mid-wave on-demand).

### Annunaki-attack
17 captured lines: 14 are expected PreToolUse enforcement blocks (loop-merge → literal-merge → `--admin`-exception adaptation flow) + benign cspell-not-local notes. 1 real gap → filed **main#650**: `post_label_change_wave_field_sync` parser skips `;`-chained multi-command Bash blocks, leaving #601's board Wave field unsynced when its label was removed (`/board-audit` reconciles). No new hooks warranted beyond the #650 fix.

### Memory-to-automation audit
New/updated memories this wave ([[project_staging_pipeline_not_wired]] — staging reality + P4W6 plan) are correctly soft memories (project state). No memory crossed a hook/skill threshold; the live-env-verification and exploratory-pass lessons went to charter proposals #1 and #3 above.

## Retrospective: Phase 4 Wave 6 — 2026-06-13 — "Real data on the VPS"

### Team Performance
8 feature PRs merged (8 distinct implementers — fully distributed, 13% top-concentration), all 2-reviewer gated. 5 wave→main merges. **#601 criterion #1 MET** — real 47,199-narrator isnad graph live on staging Neo4j (153,804 edges, Cypher-verified), wave-6 app deployed to staging green. 4 ChangesRequested cycles (all trivial — 1 reviewer misread, 2 markdown-lint, 1 doc-drift — all edited-in-place to Approved). CI healthy. Tech-debt/follow-ups filed: ig#1021, deploy#442, deploy#443, da#144. da#120 closed as verified dup of #117. ig#1018 carried forward → W7.

### Per-Engineer Assessments
- **Alejandra Reyes-Fuentes** (da#141/#143) — **wave MVP.** Found the #601 "NARRATED:0" root cause (loader read resolved mentions from `staging` while `run_all` writes to `curated` → 0 chain edges), fixed + regression-tested it, produced the real dataset, built a clean `--skip-resolve` load-only path + pre-staged verified loadset, and authored a precise gated-run spec. 1 trivial markdown-lint CR. Severity: none (exemplary).
- **Bjørn Henriksen** (ip#83/#86) — excellent judgment: delivered the worker image + GHCR publish + RUNBOOK as *mechanism only*, refused to auto-fire live infra, and produced a thorough gated-run advisory (3 real gotchas verified). Clean 2/2. Severity: none.
- **Aisha Idrissi** (deploy#440/#441) — profile-gated the workers (key safety call preventing a broken stg deploy), bundled a latent Kafka topic-name fix, defined the image contract. Clean 2/2. Severity: none.
- **Imelda Santos** (ip#84/#85) — null-safe APPEARS_IN MERGE fix + found a key-name drift between ingest paths + real-neo4j container regression. Received a CR that was a reviewer misread (disproven). Severity: none.
- **Kavitha Sundaramurthy** (da#133/#142) — durable edge-relation routing fix, good tests. Clean 2/2. Severity: none.
- **Jun-Seo Park** (ig#1016/#1019) — single-flight refresh-on-401, sound security framing, proactively flagged the admin-path follow-up (ig#1021). Clean 2/2. Severity: none.
- **Ingrid Lindqvist** (ig#1017/#1020) — friendly error messaging; **proactively flagged her own rebase as materially changing the diff** rather than riding stale approvals (excellent discipline); handled the cross-PR test reconciliation cleanly. Severity: none.
- **Aino Virtanen** (main#653) — `/wave-start` park-on-main fix; swept extra lifecycle.md drift beyond brief; handled Nadia's legitimate CR cleanly. Severity: none.

### Reviewers (notable)
- **Nadia Khoury** (#654) — caught a real, well-scoped doc-drift miss the author hadn't swept. Strong catch.
- **Nikolaos Papadopoulos** — caught the da#120 dup (saved redundant implementation) + thorough da#141 root-cause verification.
- **Camila Restrepo** (#85) — posted a ChangesRequested based on a **stale-tree misread** (reviewed a phase-3/wave-11 working tree, not the PR head); cost a critical-path re-verify cycle. BUT corrected herself honestly and immediately when shown the line-level evidence. Mixed: -signal for not verifying head, +signal for honest correction.
- Strong, genuinely-independent review culture across the board (Léopold, Jean-Claude, Dilara, Idris, Nneka, Mateo, Anya, Wanjiku, Petra, Fatima, Lucas, Weronika) — all verified at head, found real non-blocking items, no rubber-stamping.

### Top 3 Going Well
1. **#601 finally MET** — real data live on staging after months of empty graphs, via Alejandra's root-cause find.
2. **High-quality, genuinely-independent review culture** — every PR 2-reviewer gated with real verification; two reviewer disputes resolved by *evidence*, not deference (Camila self-corrected on disproof, Nadia caught real drift).
3. **Excellent execution judgment on the risky parts** — Bjørn/Aisha gating live infra, dependency-staged batches, the gated #601 run with on-box-only credentials and full de-risking before the one live write.

### Top 3 Pain Points
1. **Orchestrator omitted the TechDebt attestation line from reviewer spawn briefs** → the first merge was blocked, requiring 7 verdicts to be retrofitted. The charter ALREADY has a verbatim reviewer-brief template (agents.md) that includes it — it wasn't used.
2. **main#650 (compound-command label-parser gap) recurred** — the #653 wave-label was applied via a `cd …; gh issue edit` compound, which silently skipped the kickoff-comment hook AND tripped the wave-field-sync hook. Second wave biting us; still open.
3. **Stale-tree review (Camila, #85)** — a reviewer judged against a stale local working tree instead of the PR head, producing a disproven blocker on the critical path.

### Proposed Process Changes
1. **Reviewer spawn briefs MUST use the verbatim template** (agents.md § Orchestrator checklist when spawning a reviewer), which includes the `TechDebt:` attestation line. — Rationale: its omission blocked the first merge this wave; the template exists but wasn't followed.
2. **Bump main#650 to W7** (compound-command label-parser gap) — recurred two waves running, silently drops kickoff comments + board sync. — Rationale: repeated recurrence with real bookkeeping impact.
3. **Reviewers must confirm they are at the PR HEAD sha before reviewing** (extend charter review-against-artifact with an explicit "verify head, not a stale local checkout" step). — Rationale: Camila's stale-tree misread cost a critical-path re-verify cycle.

## Retrospective: Phase 4 Wave 7 — Phase 4 close-out & exit — 2026-06-14

### Team Performance
Deliberately thin close-out wave. **2 PRs merged** (main#650, deploy#413) — each to its wave branch, then wave→main; **2 issues closed**; **0 ChangesRequested cycles**; all 4 reviewer verdicts Approved first-pass with the TechDebt line + PR-head-SHA confirmation present (W6's TechDebt-omission blocker did NOT recur). CI 8/8 green on #658; deploy#413 path-filtered (shellcheck-clean locally). **TD intake 1/1.** Staging promotion green. Top-implementer concentration 1/2 = 50% (Aino + Weronika) — theme-fit for a 2-item wave, no fragility flag.

### Wave shape
| Item | PR | Implementer | Reviewers | CR | Notes |
|------|----|-----|-----|----|----|
| main#650 (bug) | #658 | Aino Virtanen | Weronika, Nino | 0 | misdiagnosis-corrected root fix; 7 files (~350 test lines), 8/8 CI |
| deploy#413 (tech-debt) | #447 | Weronika Zielinska | Nino, Aisha | 0 | 2-line read-back wording, shellcheck-clean |

### Per-Engineer Assessments
- **Aino Virtanen** — PR #658. 0 CR, 0 CI failures. Root-caused the issue's own "split on `;`" framing as a misdiagnosis (splitting already worked) and fixed the real bug: shared parser `_wave_label_parse._parse_edit_segment` required `--repo`, silently dropping in-repo label edits. Fix is repo-Optional + new shared `resolve_repo_short_name` ambient recovery (mirrors gh), both hook consumers benefit, DI-tested. Severity: none (positive).
- **Weronika Zielinska** — PR #447 (impl) + #658 review. Surgical 2-line deploy fix; peer review independently verified Aino's diagnosis and surfaced the CREATE-path sibling (#659). Severity: none (positive).
- **Nino Kavtaradze** — reviewed #447 + #658. Security-angle clearance of the #658 injection surface; independently named the CREATE-path sibling + a charter-promotion candidate. Severity: none (positive).
- **Aisha Idrissi** — reviewed #447. Operator-clarity verdict + a retro micro-watch (operator string drifted from authoritative in-code comment). Severity: none (positive).

### Top 3 Going Well
1. **Root-cause discipline beat issue-framing** — Aino disproved the issue's prescribed fix and root-fixed the actual bug; both reviewers verified the diagnosis independently rather than rubber-stamping.
2. **Reviewers converged un-prompted on the same forward-looking sibling gap** (CREATE-path #659) — the throughline-watch surfaced a real convergent-class finding.
3. **W6 process-blocker did not recur** — all verdicts carried the TechDebt line + PR-head-SHA confirmation first-pass; the compound-label-apply bug (#650) was itself root-fixed in-wave.

### Top 3 Pain Points
1. **`validate_labels` over-matches** label-shaped tokens in issue BODY text → false-blocked filing #659 (filed **#661**). Same parser-scoping class as #650/#659.
2. **Wrapup-gate chicken-and-egg:** `validate_wave_audit` counts the wave's own open work-items before /wave-wrapup merges+closes them, blocking the skill from running its own merge steps. Resolved by merge+close-first then re-run — non-obvious friction.
3. **Wave branch born 1-behind main:** the kickoff status-PUT lands on main after the branch is cut, so the wave→main PR trips `validate_branch_freshness` and needs a main→wave merge first. Minor, recurring.

### Convergent-class throughline (reviewer-surfaced)
"Hooks deriving a repo/identity from a raw `gh` command MUST resolve the `--repo`-less (ambient-git-context) case from cwd, never silently drop, and MUST scope token extraction to the actual flag values." Lineage: #144/#521 (cwd anchor) → #455 (multi-cmd) → **#650 (EDIT path, FIXED)** → #659 (CREATE path, open) → #661 (validate_labels body over-match, open).

### Proposed Process Changes
1. **Promote the convergent-class rule** to a charter/standards note + shared-parser invariant: any hook parsing a `gh issue/pr` command MUST scope label/repo extraction to actual flag values via `_shell_parse`/`_wave_label_parse`, and MUST resolve the `--repo`-less case from cwd (or log `skip_no_repo_context`) — never silently drop, never match body text. Rationale: 4 issues in this class (#650 fixed; #659/#661 open). Owner: Aino.
2. **(Skill) /wave-wrapup ordering:** document that the wave's work-issues must be merged+closed BEFORE the first /wave-wrapup invocation (the gate blocks otherwise), OR have the gate exempt issues whose merge-ready PR targets the wave branch. Rationale: the chicken-and-egg cost a re-run this wave.

### Annunaki (19 captures this wave)
6 `post_label_change_wave_field_sync` = the #650 pre-fix signal (now resolved) + kickoff firing; 2 `enforce_librarian_consulted` = working-as-intended agent blocks; 2 `post_wave_kickoff_comment` = normal kickoff; 2 `validate_labels` = the body over-match (→ #661); 1 `validate_wave_audit` = wrapup-gate friction (pain point #2); 1 `validate_branch_freshness` = born-behind friction (pain point #3); 5 unclassified (older/benign). No new automation spawned beyond #661 — the dominant signal (#650) was already root-fixed in-wave.

### Memory-to-automation audit
No new conversions this wave. The one promotion-worthy pattern (convergent repo-identity-from-cwd class) is captured as Proposed Change #1 above (charter/standards + shared-parser invariant), to be actioned in Phase 5 alongside #659/#661. Existing memory remains accurate; nothing retired.

