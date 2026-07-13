# Trust Identity Matrix — Phase 7 archive

> Archived byte-for-byte from `.claude/team/trust_matrix.md`
> at phase close (#964, meta #960), preserving original file order. Do not edit —
> append-only history; new entries go to the live file for the current phase.

---

## Phase 7 Wave 18 Trust Updates (2026-06-25) — C×T2 framework rollout (carry-forward lead-in)

**No score changes — all hold.** 11 PRs, one per engineer, 9% concentration (perfectly flat → no distribution-discipline ratchet); 0 CR cycles, 0 CI-red merges, 0 genuine must-fix; no decay triggers (every active member signalled). The only mechanical deltas proposed (Aino −1, Bereket −1, both "review false-positive") are **verified extractor artifacts** and are **rejected, not applied** — see the note below.

### Org-Level Team (noorinalabs-main)

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Weronika Zielinska | hold | hold | #873 (extend NODE_KINDS interface/type for TS, #870). 0 must-fix, 0 CI-red. Baseline — held. |
| Santiago Ferreira | hold | hold | #874 (author ontology/README.md, #863). 0 must-fix, 0 CI-red. Baseline — held. |
| Aino Virtanen (SQL) | 5 | 5 | #875 (align framework to C×T2 path, #862) + thorough review on #873. At ceiling — hold. Proposed −1 review-false-positive REJECTED as extractor artifact (see note; #881). |
| Nino Kavtaradze | hold | hold | #876 (standardize merge-driver to plain-script, #871). 0 must-fix, 0 CI-red. Baseline — held. |
| Nurul Hakim | hold | hold | #877 (auto-create Project-2 Wave field option, #868). 0 must-fix, 0 CI-red. Baseline — held. |
| Bereket Tadesse | hold | hold | Substantive approving review on #873 (no authored PR this wave). Proposed −1 review-false-positive REJECTED as extractor artifact (see note; #881). |

### Child-Repo Teams

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Mateo Salazar (user-service) | hold | hold | us#195 — wire C×T2 structural index. 0 must-fix, 0 CI-red. Baseline — held. |
| Aisha Idrissi (deploy) | hold | hold | dep#494 — wire C×T2 structural index stub. 0 must-fix, 0 CI-red. Baseline — held. |
| Astrid Lindqvist (design-system) | hold | hold | ds#131 — wire C×T2 structural index. 0 must-fix, 0 CI-red. Baseline — held. |
| Kofi Mensah-Williams (landing-page) | hold | hold | lp#156 — wire C×T2 structural index (#155). 0 must-fix, 0 CI-red. Baseline — held. |
| Kavitha Sundaramurthy (data-acquisition) | hold | hold | da#215 — wire C×T2 per-repo structural index. 0 must-fix, 0 CI-red. Baseline — held. |
| Yusuke Inoue (isnad-ingest-platform) | hold | hold | ig#117 — wire C×T2 structural index (#116). 0 must-fix, 0 CI-red. Baseline — held. |

**Extractor-artifact note (rejected deltas):** `trust_signals.py score 7 18` proposed −1 for Aino and Bereket on a `review_false_positive` signal. Verified spurious: on **PR #873** both posted `RequestOrReplied: Approved`, and their comment bodies contain "false-positive" only because they were praising the PR's `test_no_false_positive_type_in_non_decl_context` coverage. `_FALSE_POSITIVE_RE` substring-matches approving prose and ignores the Approved verdict. Same misfire recurred from W17 (Aino + Nino). Both deltas rejected; scores held. Bug filed as **#881**, fix in flight at this retro. This is the Step-2.5 "don't narrate a wrong counter as authoritative" discipline applied to trust signals.

### Done Well / Needs Improvement (Phase 7 Wave 18) — evidence-anchored, bare "None" banned

| Member | Done Well (with evidence) | Gap (metric, or explicit "clean: numbers") |
|--------|---------------------------|--------------------------------------------|
| **Weronika Zielinska** | TS NODE_KINDS extension (#873), unblocking the TS fan-out | clean: 0 must-fix received, 0 CI-red |
| **Aino Virtanen** | C×T2 framework alignment (#875) + thorough #873 review | review-false-positive signal is a verified extractor artifact (#881), not a real gap; metrics clean |
| **Bereket Tadesse** | substantive approving review on #873 (regex/test-coverage lens) | review-false-positive signal is a verified extractor artifact (#881), not a real gap; metrics clean |
| **Santiago / Nino / Nurul** | 1 clean on-theme main PR each (#874/#876/#877) | clean: 0 must-fix received, 0 CI-red — baseline, no ratchet |
| **Mateo / Aisha / Astrid / Kofi / Kavitha / Yusuke** | C×T2 structural-index wiring in their child repo (1 clean PR each) | clean: 0 must-fix received, 0 CI-red — baseline, no ratchet |

**Fire/hire:** none.

**Concentration note:** 9% top by implementer — the most evenly distributed wave to date (one PR per engineer across all 7 repos). Theme-fit fan-out; no fragility concentration. The W17 caveat ("carry distributed implementer work forward") was met again.

## Phase 7 Wave 19 Trust Updates (2026-06-25) — framework tooling carry-forward + prod-data quality

Mechanical scoring (`trust_signals.py score 7 19`): 9 PRs, 7 engineers, **0 changes-requested cycles**, 0 CI-red merges, 0 must-fix received/caught, top-concentration 33% (Aino, 3/9). The helper proposed Aino +1 (clean 3-PR delivery); **owner decision 2026-06-25 held all engineers flat** — the whole wave was clean-but-unremarkable, no single-reviewer-catch or other ratchet signal, so no deltas this wave. No `review_false_positive` misfires this wave (the #881 extractor bug did not trigger — all false-positive counts 0).

### Org-Level Team (noorinalabs-main)

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Aino Virtanen | hold | hold | #896 (Hook-4 subshell/compound guard, #894), #895 (lint wiring, #893), #890 (wave_seq reservation-aware, #885). prs_merged=3, 0 must-fix, 0 CI-red. Helper proposed +1; **owner held flat** (clean delivery, no reviewing-catch ratchet). |
| Lucas Ferreira | hold | hold | #891 (narrow validate_pr_review batch-loop guard, #886). 0 must-fix, 0 CI-red. Baseline — held. |
| Nurul Hakim | hold | hold | #892 (board-audit GraphQL pagination + resilient loop, #888). 0 must-fix, 0 CI-red. Baseline — held. |
| Weronika Zielinska | hold | hold | #889 (ontology_gen depth-aware TS extends splitter, #887). 0 must-fix, 0 CI-red. Baseline — held. |

### Child-Repo Teams

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Alejandra Reyes-Fuentes (data-acquisition) | hold | hold | da#218 (ADR-003 sanadset orphan + narrator-pollution investigation A/B, da#202). 0 must-fix, 0 CI-red. Baseline — held. |
| Kavitha Sundaramurthy (data-acquisition) | hold | hold | da#217 (honor explicit None as load-all in HADITH_COMPOSITION, da#196). 0 must-fix, 0 CI-red. Baseline — held. |
| Nneka Obi (isnad-graph) | hold | hold | ig#1133 (repair prod full-text starvation + semantic 500, ig#1110). 0 must-fix, 0 CI-red. Baseline — held. |

### Done Well / Needs Improvement (Phase 7 Wave 19) — evidence-anchored, bare "None" banned

| Member | Done Well (with evidence) | Gap (metric, or explicit "clean: numbers") |
|--------|---------------------------|--------------------------------------------|
| **Aino Virtanen** | 3 clean framework-hardening PRs (#896/#895/#890) — Hook-4 guard, lint wiring, wave_seq reservation | clean: 0 must-fix received, 0 CI-red, 0 false-positives |
| **Lucas / Nurul / Weronika** | 1 clean on-theme main PR each (#891/#892/#889) — guard-narrowing, board-audit pagination, TS extractor | clean: 0 must-fix received, 0 CI-red — baseline, no ratchet |
| **Alejandra / Kavitha** | data-quality fixes in data-acquisition (da#218 investigation, da#217 parser) | clean: 0 must-fix received, 0 CI-red — baseline, no ratchet |
| **Nneka Obi** | prod search repair (full-text starvation + semantic 500, ig#1133) | clean: 0 must-fix received, 0 CI-red — baseline, no ratchet |

**Fire/hire:** none.

**Concentration note:** 33% top by implementer (Aino, 3/9) — below the 60% fragility threshold. Theme-fit: Aino owns the framework-tooling surface this wave themed on. No redistribution action required.

**Process note (not a per-engineer signal):** two wave→main *integration* PRs needed orchestrator fix-forward — #898 (squash collapsed persona authorship → commit-author gate) and da#222 (child structural index not regenerated for a new `.cypher`). Neither is an implementer must-fix (the per-issue PRs were clean); both are orchestrator/process gaps now codified — **Hook 22** (`block_squash_wave_merge`) + **`/wave-wrapup` Step 10.7** (child structural pre-regen). See this wave's feedback_log entry.

## Phase 7 Wave 20 Trust Updates (2026-06-26) — graph integrity + dedup + chains

Mechanical scoring (`trust_signals.py score 7 20`): 6 PRs, 5 implementers, **0 changes-requested cycles**, 0 CI-red merges, 0 must-fix received/caught, top-concentration 33% (Alejandra, 2/6). The helper proposed Alejandra +1 (clean 2-PR delivery); she is already at ceiling **5**, so the bump is absorbed (`clamp(5+1)=5`). All other engineers delta 0 (a single clean PR is not a bump). No `review_false_positive` misfires. Baseline-hold wave — same shape as W18/W19: clean-but-unremarkable, no single-reviewer-catch or other ratchet signal.

**Validation note:** the W19 process changes proved out this wave — **Hook 22** silently did its job (every per-issue PR merged with `--merge`; no squash attempt to block) and **Step 10.7** (child structural pre-regen) meant both wave→main PRs (da#231, ig#1136) were green on staleness-check from the first push, with **zero** fix-forward scrambles (vs two in W19). The two pain points that drove W19's codification did not recur.

### Child-Repo Teams (data-acquisition + isnad-graph)

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Alejandra Reyes-Fuentes (data-acquisition) | 5 | 5 | da#224 (Path B/B1 — emit `collections_sanadset.parquet` foundation, da#219) + da#227 (Path B parent integration verify, da#202). prs_merged=2 (wave top), 0 must-fix, 0 CI-red. Helper proposed +1; **absorbed at ceiling**. Led the two coupled B1+parent items per kickoff plan. |
| Kavitha Sundaramurthy (data-acquisition) | 5 | 5 | da#225 (cross-edition canonical-identity dedup, Path B/B2, da#220). 0 must-fix, 0 CI-red. Baseline — held at ceiling. |
| Ivana Horvat (data-acquisition) | 5 | 5 | da#226 (narrator re-segmentation — `<NAR>` firehose filter, Path B/B3, da#221). 0 must-fix, 0 CI-red. Baseline — held at ceiling. |
| Nikolaos Papadopoulos (data-acquisition) | 5 | 5 | da#223 (da#153 integrity sweep — explicit-null / no-fabrication contracts + inventory). 0 must-fix, 0 CI-red. Baseline — held at ceiling. |
| Jun-Seo Park (isnad-graph) | 4 | 4 | ig#1135 (`GET /validate/chains` — chronological isnad plausibility, ig#1040). 0 must-fix, 0 CI-red. Baseline — held (at 4 since W4). |

### Done Well / Needs Improvement (Phase 7 Wave 20) — evidence-anchored, bare "None" banned

| Member | Done Well (with evidence) | Gap (metric, or explicit "clean: numbers") |
|--------|---------------------------|--------------------------------------------|
| **Alejandra Reyes-Fuentes** | 2 clean coupled PRs on the Path B spine (da#224 B1 foundation + da#227 parent integration verify) — the orphan-resolution acceptance gate | clean: 0 must-fix received, 0 CI-red, 0 false-positives |
| **Kavitha / Ivana / Nikolaos** | 1 clean on-theme data-acquisition PR each (da#225 dedup / da#226 re-segmentation / da#223 integrity contracts) | clean: 0 must-fix received, 0 CI-red — baseline, no ratchet |
| **Jun-Seo Park** | chain-validation endpoint shipped clean (ig#1135 `GET /validate/chains`) — doubles as the segmentation regression signal | clean: 0 must-fix received, 0 CI-red — baseline, no ratchet |
| **Reviewers** (Kavitha, Nikolaos, Ivana, Mateo Salazar, Aisling Brennan, Oyunbileg Batbayar, Kwesi Boateng, Jean-Claude Habimana) | 2 first-pass approvals per PR, 0 CR cycles wave-wide | clean: 0 must-fix-caught because 0 must-fixes existed — no reviewing ratchet either way |

**Fire/hire:** none. Retirement trigger (`trust_signals.retirement_trigger`) fired for no engineer — no bottom-tier-or-CI-red streak.

**Concentration note:** 33% top by implementer (Alejandra, 2/6) — below the 60% fragility threshold. Theme-fit: Path B's sanadset parsing lives in data-acquisition and Alejandra owns the B1+parent coupling by design. No redistribution action required. 5 of 6 implementer-issues in data-acquisition is inherent to the Path B theme, spread across 4 da personas — not fragility.

## Phase 7 Wave 21 Trust Updates (2026-06-26) — narrator dating foundation + prod re-validation

Mechanical scoring (`trust_signals.py score 7 21`): **11 PRs** (10 data-acquisition + 1 isnad-graph), 5 implementers, top-concentration **27%** (Alejandra & Kavitha tied at 3/11), **0 CI-red merges**, 0 `review_false_positives`. Helper-proposed deltas: Alejandra/Kavitha/Ivana/Nikolaos **+1** (clean multi-PR delivery) — all four already at ceiling **5**, so absorbed (`clamp(5+1)=5`); Jun-Seo Park **+0** (single clean PR is not a bump) — held at **4**. Distribution discipline: no new 5s handed out; the four ceiling-holders earned theirs in prior waves.

**Measurement-conflict note (load-bearing — same class as the CR-cycle counter):** the helper reports `must_fix_received=0` and `must_fix_caught=0` for **every** engineer, but this wave had **4 genuine changes-requested cycles** (da#161/#233, da#228/#235, da#165/#241, ig#1039/#1137) that caught **real data-correctness defects** — `TRANSMITTED_TO` provenance-row fabrication, `narrators_dated` always-0 count, single-source range→EXACT precision over-claim, and order-dependent consensus-band widening. All four verdicts were **edited-in-place to Approved** per the charter verdict-amendment rule, which erased the `must_fix_*` surface the helper reads. Per `wave_21_counter_corrections`, the wrapup-time historic **CR-cycles=4 stands as authoritative-historic**; the recomputed 0 is the amendment artifact, NOT a correction. Consequence for trust: the reviewers who made these catches (Kavitha, Nikolaos, Kwesi Boateng, Aisling Brennan) get **no mechanical `must_fix_caught` credit** this wave even though they did substantive catching — a known gap in mechanical scoring vs verdict-amendment, surfaced as a W21 pain point.

### Child-Repo Teams (data-acquisition + isnad-graph)

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Alejandra Reyes-Fuentes (data-acquisition) | 5 | 5 | da#233 (DatePrecision model + date bounds, da#161 root), da#241 (multi-source date reconciliation, da#165), da#236 (collection metadata enrichment, da#230). prs_merged=3 (wave top, tied). Helper proposed +1; **absorbed at ceiling**. da#241 absorbed a real must-fix (single-source range→EXACT over-claim) and shipped the fix clean. |
| Kavitha Sundaramurthy (data-acquisition) | 5 | 5 | da#237 (extend `NARRATORS_CANONICAL_SCHEMA`, da#162), da#235 (mention-link 8 orphan muhaddithat + provenance, da#228), da#234 (in-book ordinal, da#229). prs_merged=3 (wave top, tied). da#235 absorbed the `TRANSMITTED_TO` provenance-fabrication must-fix. Held at ceiling. |
| Ivana Horvat (data-acquisition) | 5 | 5 | da#240 (death-anchored narrator-date extraction, da#164), da#238 (geographic disambiguation stage, da#139). prs_merged=2, 0 CI-red. Held at ceiling. |
| Nikolaos Papadopoulos (data-acquisition) | 5 | 5 | da#242 (ṭabaqa→estimated-window fallback, da#166), da#232 (`src/utils/hijri.py` AH↔CE + pin convertdate, da#163). prs_merged=2, 0 CI-red. Also reviewed/caught on the foundation chain. Held at ceiling. |
| Jun-Seo Park (isnad-graph) | 4 | 4 | ig#1137 (loader writes resolved narrator date props to Neo4j + `_active_window` enricher upgrade, ig#1039). prs_merged=1, 0 CI-red. Absorbed the `narrators_dated` always-0 count must-fix and shipped the `RETURN count(n) AS matched` fix. Single clean PR — not a bump; held at 4. |

### Done Well / Needs Improvement (Phase 7 Wave 21) — evidence-anchored, bare "None" banned

| Member | Done Well (with evidence) | Gap (metric, or explicit "clean: numbers") |
|--------|---------------------------|--------------------------------------------|
| **Alejandra Reyes-Fuentes** | 3 PRs across the date-foundation spine (model root da#233 → reconcile da#241 → metadata da#236); clean fix on the range→EXACT precision defect | clean: 0 CI-red, 0 false-positives, prs_merged=3 — must_fix_received understated by edit-in-place (see conflict note) |
| **Kavitha Sundaramurthy** | 3 PRs (schema da#237, muhaddithat-link da#235, ordinal da#234); absorbed the TRANSMITTED_TO fabrication catch on da#235 | clean: 0 CI-red, 0 false-positives, prs_merged=3 |
| **Ivana Horvat** | death-anchored date parser (da#240) — the extraction heart of the chain — + geo disambiguation (da#238), both clean | clean: 0 CI-red, 0 false-positives, prs_merged=2 |
| **Nikolaos Papadopoulos** | hijri conversion util + convertdate pin (da#232) and ṭabaqa fallback (da#242) — the two arithmetic-sensitive ends of the chain, clean | clean: 0 CI-red, 0 false-positives, prs_merged=2 |
| **Jun-Seo Park** | cross-repo Neo4j loader for date props (ig#1137) — the single isnad-graph consumer of the da chain; fixed the always-0 count under review | clean: 0 CI-red, prs_merged=1 — single PR, no ratchet; held at 4 |
| **Reviewers** (Kavitha, Nikolaos, Kwesi Boateng, Aisling Brennan, Mateo Salazar, + slate) | **4 substantive defect catches** across da#233/#235/#241/#1137 — fabrication, always-0, precision over-claim, order-dependent widening; all with regression tests that fail on pre-fix code | `must_fix_caught` shows 0 mechanically (verdicts edited-in-place to Approved) — real catching is uncredited by the helper; see measurement-conflict note |

**Fire/hire:** none. Retirement trigger (`trust_signals.retirement_trigger`) fired for no engineer.

**Concentration note:** 27% top by implementer (Alejandra & Kavitha tied 3/11) — below the 60% fragility threshold. Theme-fit: narrator dating lives in data-acquisition (10/11 PRs); ig#1039 is the single isnad-graph loader. Load spread across 5 da personas + 1 ig persona. Not fragility.

## Phase 7 Wave 22 Trust Updates (2026-07-01) — final Phase-7 wave: prod hardening + #723 closeout attempt + tooling fixes

Mechanical scoring (`trust_signals.py score 7 22`): **22 PRs** (10 isnad-graph, 6 deploy, 3 main, 3 data-acquisition), 16 implementers, top-concentration **14%** (Lucas Ferreira & Mateo Salazar tied 3/22 — well below the 60% fragility line), **0 CI-red merges**, **1** `review_false_positives`, 1 changes-requested cycle. Helper-proposed deltas: Aisha/Jun-Seo/Kavitha/Nneka **+1**; Alejandra **−1** (1 review false-positive). Distribution discipline applied: **one** new 5 handed out (Nneka — the only +1 earner who also caught a real defect); Jun-Seo's +1 was on two merely-clean PRs (no catch) so held at 4 per the never-a-new-5-for-merely-clean rule; Aisha & Kavitha at ceiling absorb their +1.

### Org-Level Team
No org-level (`noorinalabs-main`) scored changes this wave — the 3 main PRs (Aino #910, Wanjiku #912, Santiago #913) were single clean tooling/hook fixes (delta 0, held). Wanjiku & Santiago held; Aino held at prior.

### Child-Repo Teams (isnad-graph + deploy + data-acquisition)

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Nneka Obi (isnad-graph) | 4 | 5 | prs_merged=2 (ig#1153, ig#1158) + must_fix_caught=1, 0 CI-red, 0 false-positives. Only +1 earner with a substantive review catch this wave; distribution-discipline new-5 goes to the wave's strongest quality+volume signal. |
| Alejandra Reyes-Fuentes (data-acquisition) | 5 | 4 | review_false_positives=1 (mechanical signal — specific review to be identified at PR level). −1 per mechanical scoring. First dock off ceiling; recoverable next clean wave. |
| Aisha Idrissi (deploy) | 5 | 5 | prs_merged=2 (deploy#515, #517), 0 CI-red. Helper proposed +1; absorbed at ceiling. |
| Kavitha Sundaramurthy (data-acquisition) | 5 | 5 | prs_merged=2 (da#254, #255), 0 CI-red. Helper proposed +1; absorbed at ceiling. |
| Jun-Seo Park (isnad-graph) | 4 | 4 | prs_merged=2 (ig#1156, ig#1161), 0 CI-red. +1 earned but on merely-clean PRs (no catch); distribution discipline holds at 4. |

### Done Well / Needs Improvement (Phase 7 Wave 22) — evidence-anchored, bare "None" banned

| Member | Done Well (with evidence) | Gap (metric, or explicit "clean: numbers") |
|--------|---------------------------|--------------------------------------------|
| **Nneka Obi** | 2 isnad-graph PRs + a real review catch; earned the wave's single new 5 | clean: 0 CI-red, 0 false-positives, prs_merged=2, must_fix_caught=1 |
| **Alejandra Reyes-Fuentes** | (no PRs this wave; review participation) | 1 review false-positive (mechanical) — the wave's only negative implementer signal; identify the specific review and calibrate |
| **Aisha Idrissi** | 2 clean deploy PRs on the prod-hardening spine | clean: 0 CI-red, 0 false-positives, prs_merged=2 |
| **Kavitha Sundaramurthy** | 2 clean da PRs (narrator-quality area) | clean: 0 CI-red, 0 false-positives, prs_merged=2 |
| **Lucas Ferreira / Mateo Salazar** | wave top by volume (3 PRs each), 0 CI-red | clean: 0 CI-red — each absorbed 1 must_fix_received (delta 0, held) |
| **Orchestrator (Nadia)** | ran the prod window + full wrapup | **prematurely reported #723 crit-1 "resolved" on an aggregate cypher "matn=0" that a record-level API/UI check refuted (≥7,580 matn nodes live) — validation-discipline miss, caught only by owner prompting the UI walkthrough** |

**Fire/hire:** none. Retirement trigger (`trust_signals.retirement_trigger`) fired for no engineer.

**Concentration note:** 14% top by implementer — lowest of Phase 7; 16 implementers across 4 repos. Healthy spread, not fragility.

