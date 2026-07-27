# Trust Identity Matrix

All team members maintain a trust score for every other team member they interact with.

## Scale

| Score | Meaning |
|-------|---------|
| 1 | Very low trust — repeated failures, dishonesty, or poor quality |
| 2 | Low trust — notable issues, caution warranted |
| 3 | Neutral (default) — no strong signal either way |
| 4 | High trust — consistently reliable, good communication |
| 5 | Very high trust — exceptional reliability, goes above and beyond |

## Rules

- **Default:** Every pair starts at **3**.
- **Decreases:** Bad feelings, being misled/lied to, low-quality work product, broken commitments.
- **Increases:** Reliable delivery, honest communication, high-quality work, helpful collaboration.
- **Updates:** This file is updated on `main` whenever a trust-relevant interaction occurs (typically during wave retros). Changes should include a brief log entry explaining the adjustment.
- **Scope:** Trust is directional — A's trust in B may differ from B's trust in A.

## Mechanical Scoring (evidence-anchored) — authoritative as of P6W17 (#842 / Option B §4b)

Narrative self-grading is **retired** for the orchestrator → team direction. A trust delta is no longer "felt"; it is **derived from countable wave signals** and must cite them. The executable model lives in [`.claude/lib/trust_signals.py`](../lib/trust_signals.py) (`/wave-wrapup` extracts the signals, `/wave-retro` applies the deltas); the rules below are the human-readable contract that file implements. The five legacy scale points (1–5) and the directional semantics above are unchanged — only *how a change is justified* changes.

### Per-engineer signals (countable, from the merged-PR set)

Each is an integer extracted by `trust_signals.extract_signals(phase, wave)` over the wave's merged PRs (author = head-commit author name; reviewer = the verdict comment's `Requestor:` field):

| Signal | Direction | Definition |
|--------|-----------|------------|
| `prs_merged` | + | PRs merged this wave authored by the engineer |
| `must_fix_caught` | + | ChangesRequested verdicts the engineer issued as reviewer |
| `must_fix_received` | − | ChangesRequested verdicts on PRs the engineer authored |
| `ci_red_merges` | − | authored PRs that merged with a failing required check |
| `rework_cycles` | − | authored PRs that needed ≥1 rework round |
| `review_false_positives` | − | must-fix items the engineer raised that were later self-marked withdrawn / false-positive |

### Evidence-anchored, bidirectional delta

`trust_signals.score_delta(signals)` — pure, symmetric, clamped to **[−2, +2]** (one wave cannot swing trust across the whole scale):

- **−1** per CI-red merge; **−1** per review false-positive; **−1** if `must_fix_received ≥ 3`.
- **+1** if `prs_merged ≥ 2` *and* the wave is clean of the negatives above; **+1** if `must_fix_caught ≥ 2` and no false-positives.
- A single clean PR is **not** an increase (it is baseline expected delivery, not exceptional).

`new = clamp(old + delta, 1, 5)`. Every retro trust-table row MUST cite the numbers behind its delta — a row with no signal citation is rejected at review.

### Decay toward neutral

`trust_signals.decay(old, waves_since_signal)` — if an engineer produced **no** trust-relevant signal for **3** consecutive waves, drift the score **one step toward 3** (a stale 4 or 2 is no longer earned). Decay is gradual (one step per qualifying wave), never a reset.

### Distribution discipline

`trust_signals.apply_distribution_discipline(...)` — **5 is reserved** for exceptional *relative* wave performance, not handed out for merely-clean work. A proposed 5 is allowed only for the engineer(s) with the wave's top composite signal score (and that score must be strictly positive); every other proposed 5 is capped to 4.

### Forced negative-signal pass (bare "None" is banned)

Each retro records, **per active engineer**, either a specific evidence-backed gap **or** an explicit `metrics clean: {numbers}` line — produced by `trust_signals.negative_signal_line(name, signals)`. A bare `None` / `N/A` / `-` is a forced-pass violation; `/wave-retro` rejects it via `trust_signals.validate_negative_signal_pass(...)`.

### Performance-triggered retirement

`trust_signals.retirement_trigger(score_history, ci_red_history)` — a persona is flagged for archive / not-spawned when, over the most recent **3** waves, **either** the score stayed bottom-tier (≤2) every wave **or** there was ≥1 CI-red merge every wave. Fewer than 3 waves of history never triggers (insufficient evidence). The trigger is a *recommendation surfaced at retro* for owner confirmation, not an automatic deletion.

## Matrix

Rows = the team member rating. Columns = the team member being rated.

*Note: Tariq and Mei-Lin archived after Phase 8 reorganization — removed from active matrix.*

| Rater ↓ \ Rated → | Fatima | Renaud | Sunita | Tomasz | Dmitri | Kwame | Amara | Hiro | Carolina | Yara | Priya | Elena |
|--------------------|--------|--------|--------|--------|--------|-------|-------|------|----------|------|-------|-------|
| **Fatima**         | —      | 3      | 3      | 4      | 3      | 5     | 4     | 4    | 4        | 4    | 3     | 3     |
| **Renaud**         | 3      | —      | 3      | 3      | 3      | 4     | 4     | 4    | 4        | 3    | 3     | 3     |
| **Sunita**         | 3      | 3      | —      | 4      | 3      | 4     | 3     | 3    | 3        | 4    | 3     | 3     |
| **Tomasz**         | 3      | 3      | 4      | —      | 3      | 4     | 3     | 3    | 3        | 4    | 3     | 3     |
| **Dmitri**         | 3      | 3      | 3      | 3      | —      | 5     | 4     | 4    | 4        | 3    | 3     | 3     |
| **Kwame**          | 4      | 3      | 3      | 4      | 4      | —     | 4     | 4    | 4        | 3    | 3     | 3     |
| **Amara**          | 4      | 3      | 3      | 3      | 4      | 4     | —     | 4    | 4        | 3    | 3     | 3     |
| **Hiro**           | 4      | 3      | 3      | 3      | 4      | 4     | 4     | —    | 4        | 3    | 3     | 3     |
| **Carolina**       | 4      | 3      | 3      | 3      | 4      | 4     | 4     | 4    | —        | 3    | 3     | 3     |
| **Yara**           | 3      | 3      | 4      | 4      | 3      | 3     | 3     | 3    | 3        | —    | 3     | 3     |
| **Priya**          | 3      | 3      | 3      | 3      | 3      | 3     | 3     | 3    | 3        | 3    | —     | 3     |
| **Elena**          | 3      | 3      | 3      | 3      | 3      | 3     | 3     | 3    | 3        | 3    | 3     | —     |

## Change Log

| Date | Rater | Rated | Old | New | Reason |
|------|-------|-------|-----|-----|--------|
| 2026-03-16 | Fatima | Kwame | 3 | 5 | Consistent high-quality delivery across all 8 phases — core implementer for acquire, parse, resolve, enrich, API, testcontainers, OAuth, and CLI skills |
| 2026-03-16 | Fatima | Amara | 3 | 4 | Reliable delivery on NER, disambiguation, edges, graph API, historical overlay, and Fawaz Arabic work |
| 2026-03-16 | Fatima | Hiro | 3 | 4 | Solid contributions to validation, dedup, topics, React frontend, real data tests, Playwright, and sunnah scraper |
| 2026-03-16 | Fatima | Carolina | 3 | 4 | Strong test coverage work, OpenHadith/Sunnah parsing, fuzz testing, metadata, and GitHub Pages |
| 2026-03-16 | Fatima | Tomasz | 3 | 4 | Reliable CI/CD, Docker fixes, coverage/license tooling, hooks/scripts, and worktree cleanup throughout |
| 2026-03-16 | Fatima | Yara | 3 | 4 | Strong security review contributions in Phase 7 |
| 2026-03-16 | Dmitri | Kwame | 3 | 5 | Most prolific and reliable engineer on the team across all phases |
| 2026-03-16 | Dmitri | Amara | 3 | 4 | Consistently reliable on data-heavy implementation work |
| 2026-03-16 | Dmitri | Hiro | 3 | 4 | Versatile — handled backend validation, frontend React, E2E testing |
| 2026-03-16 | Dmitri | Carolina | 3 | 4 | Strong on testing and parsing, dependable delivery |
| 2026-03-16 | Kwame | Fatima | 3 | 4 | Good project management, clear task delegation |
| 2026-03-16 | Kwame | Dmitri | 3 | 4 | Fair tech lead, good code review feedback |
| 2026-03-16 | Kwame | Tomasz | 3 | 4 | CI always works, responsive to infrastructure needs |
| 2026-03-16 | Kwame | Amara | 3 | 4 | Great collaborator on shared modules |
| 2026-03-16 | Kwame | Hiro | 3 | 4 | Reliable peer, good cross-domain skills |
| 2026-03-16 | Kwame | Carolina | 3 | 4 | Thorough testing, catches edge cases |
| 2026-03-16 | Amara | Kwame | 3 | 4 | Strong technical partner |
| 2026-03-16 | Amara | Dmitri | 3 | 4 | Constructive code reviews |
| 2026-03-16 | Amara | Fatima | 3 | 4 | Clear expectations, good communication |
| 2026-03-16 | Hiro | Kwame | 3 | 4 | Reliable and knowledgeable |
| 2026-03-16 | Hiro | Dmitri | 3 | 4 | Helpful tech lead guidance |
| 2026-03-16 | Hiro | Fatima | 3 | 4 | Good project coordination |
| 2026-03-16 | Carolina | Kwame | 3 | 4 | Strong code quality |
| 2026-03-16 | Carolina | Dmitri | 3 | 4 | Fair reviewer |
| 2026-03-16 | Carolina | Fatima | 3 | 4 | Clear direction |
| 2026-03-16 | Sunita | Tomasz | 3 | 4 | Implements infrastructure designs faithfully |
| 2026-03-16 | Sunita | Yara | 3 | 4 | Good security collaboration |
| 2026-03-16 | Tomasz | Sunita | 3 | 4 | Clear architectural guidance |
| 2026-03-16 | Tomasz | Yara | 3 | 4 | Security reviews are actionable |
| 2026-03-16 | Yara | Sunita | 3 | 4 | Infrastructure design is security-conscious |
| 2026-03-16 | Yara | Tomasz | 3 | 4 | Responsive to security fix requests |
| 2026-03-16 | Renaud | Kwame | 3 | 4 | Architecturally sound implementations |
| 2026-04-06 | Tomasz | Kwame | 4 | 3 | Wrong-branch commit incident (Phase 15 Wave 2) |
| 2026-04-07 | Orchestrator | Aino Virtanen | 4 | 5 | Hooks Sprint: 15 issues, 3 PRs, zero rework. Most productive single-agent sprint. |

---

## Archive (per-phase)

Historical per-wave trust-update sections are archived per-phase at phase close
(#964, meta #960; `charter.md` § Feedback System → Per-Phase Archival). The
Scale/Rules/Mechanical-Scoring contract, the Matrix table, the Change Log, and
the Archived Personas section stay live; only closed-phase per-wave sections move.

- [Pre-Phase-2 — Sessions 4–6, user-service extraction (≤ 2026-04-09)](archive/trust_matrix_pre-phase-2.md)
- [Phase 2](archive/trust_matrix_phase-2.md)
- [Phase 3](archive/trust_matrix_phase-3.md)
- [Phase 4](archive/trust_matrix_phase-4.md)
- [Phase 5](archive/trust_matrix_phase-5.md)
- [Phase 6](archive/trust_matrix_phase-6.md)
- [Phase 7](archive/trust_matrix_phase-7.md)

---

## Archived Personas — parent roster (P6W17 governed headcount, #841)

Persona Option B (criterion #3, spike `.claude/team/spikes/p6w2-persona-model-evaluation.md`) caps the
parent roster at **9** cards and **merges near-duplicate roles**. The card below was removed from
`.claude/team/roster/` to bring the parent roster from 10 → 9 (AT the cap; the cap is inclusive). **History
is preserved, not deleted:** every trust/feedback entry this persona earned remains in the change logs and
per-wave sections above, and the name stays in `.claude/team/roster.json` (the org-wide commit-identity union
manifest) so the commit-identity gate still resolves her authored commits. She is a **deploy-repo persona**
whose *canonical* card lives in `noorinalabs-deploy/.claude/team/roster/` — only the duplicate parent copy was
retired; she remains active in `noorinalabs-deploy`.

**Owner revision (2026-06-24):** the original #841 slim also retired Bereket Tadesse and Nino Kavtaradze on a
"0 parent commits, ever" premise. That premise was stale by merge time — Bereket authored #832 (merged #846)
and Nino authored #838 (merged #851) and reviewed #835, all in P6W17. Both were **restored** to the parent
roster and the cap raised 8 → 9 to fit them; only the genuine duplicate (Aisha → Lucas) stays retired.

| Persona | Parent role | Reason retired (parent roster) | Last parent-repo commit | Canonical card |
|---------|-------------|--------------------------------|-------------------------|----------------|
| Aisha Idrissi | SRE Engineer | Near-duplicate of SRE Lucas Ferreira (roles merged) + stale (outside last-N-waves window) | 2026-04-21 | `noorinalabs-deploy` (`sre_engineer_aisha.md`) |

Re-instating a retired parent persona is a deliberate, reviewed change (restore the card + drop back under
the headcount budget) — the same surfaced-decision posture the `headcount_budget.py` gate enforces.

---

## Phase 8 Wave 24 Trust Updates (2026-07-18) — #928 defect-sweep + graph re-run from `parse` + prod cutover (formal closeout)

Mechanical scoring (`trust_signals.py score 8 24`): **6 PRs** merged to the `deployments/phase-8/wave-24` branch, all `noorinalabs-main` charter/memory/session-start housekeeping (#924/#965/#966/#967/#969/#972), top-concentration **33%**, **0 CI-red merges**, **0** `review_false_positives`, 1 changes-requested cycle. Helper-proposed deltas: Aino **+1**; all others delta 0.

**Measurement-window caveat (honest limitation).** Wave 24's *substantive* engineering — the 56-issue defect sweep and the four owner-gated prod graph writes (promote→reload→prune→enrich) + the over_merged flag op — merged **direct-to-main across data-acquisition and deploy** (neither had a wave-24 branch) and in earlier cycles, so it is **outside this mechanical wave-branch window**. The deltas below therefore reflect only the housekeeping cohort that landed on the main wave branch; the cutover/sweep contributors (da + deploy SREs) are not re-scored here because their work is not in the measurable window. This is a known artifact of a long-running fix-then-rerun wave, not a judgment that their work was absent.

### Org-Level Team

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Aino Virtanen | 5 | 5 | prs_merged=2 (#969 charter section-pack re-shelve, #924 dominant-class carry-forward + annunaki archive-reset process), 0 CI-red, 0 must-fix received, 0 false-positives. Helper +1 absorbed at ceiling. |
| Santiago Ferreira | hold | hold | prs_merged=0, must_fix_caught=1 (a review catch on the wave-branch set). Single catch < +1 threshold (needs ≥2); held. |

### Child-Repo Teams (deploy)

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Lucas Ferreira (deploy) | hold | hold | prs_merged=1 (#965 per-phase feedback/trust archival), 0 CI-red, 0 must-fix. Baseline — held. |
| Nurul Hakim (deploy) | hold | hold | prs_merged=1 (#966 session-start slimming / red-sweep schedule / count-only annunaki), 0 CI-red, 0 must-fix. Baseline — held. |
| Weronika Zielinska (deploy) | hold | hold | prs_merged=2, must_fix_received=1 on the wave-branch set — single minor author-side signal, delta 0. |

### Done Well / Needs Improvement (Phase 8 Wave 24) — evidence-anchored, bare "None" banned

| Member | Done Well (with evidence) | Gap (metric, or explicit "clean: numbers") |
|--------|---------------------------|--------------------------------------------|
| **Aino Virtanen** | 2 clean process/charter PRs (section-pack re-shelve #969; dominant-class carry-forward + annunaki archive-reset #924) that tightened the wave lifecycle | clean: prs_merged=2, must_fix_received=0, ci_red_merges=0, false_positives=0 |
| **Lucas Ferreira / Nurul Hakim** | 1 clean housekeeping PR each (#965 per-phase archival / #966 session-start slimming) reducing static-context cost | clean: 0 CI-red, 0 must-fix each |
| **Weronika Zielinska** | contributed to the context-efficiency track | 1 must-fix received on the wave-branch set — minor, single author-side signal |
| **Santiago Ferreira** | a review catch (must_fix_caught=1) on the wave-branch housekeeping set | clean: prs_merged=0, ci_red_merges=0, false_positives=0, must_fix_caught=1 |
| **Orchestrator (Nadia)** | closed out a long-running fix-then-rerun wave: verified the prod cutover complete (deploy#610/#611), reconciled 47 open wave-24 issues (8 resolved+closed, 39 deferred-TD documented as backlog rather than force-relabeled into the scoped Phase 9 waves), archived 268 benign annunaki records | the wave's *substantive* trust signal is unmeasurable from the wave branch (cutover/sweep merged direct-to-main) — flagged as a caveat above rather than papered over with invented deltas |

**Fire/hire:** none. Retirement trigger (`trust_signals.retirement_trigger`) fired for no engineer.

**Concentration note:** 33% top by implementer (Aino 2/6) on the housekeeping window — well below the 60% fragility line, and not representative of the full wave (which was distributed across da/deploy direct-to-main). No redistribution action.

## Phase 8 Wave 23 Trust Updates (2026-07-06) — #723 data-quality closeout landed on prod + promotion-path fix

Mechanical scoring (`trust_signals.py score 8 23`): **20 PRs** (19 at wrapup + PR#322 da#321 fix merged post-wrapup; counter-corrected 19→20), 4 repos in scope, top-concentration **30%** (Alejandra Reyes-Fuentes 6/20 — well below the 60% fragility line), **0 CI-red merges**, **0** `review_false_positives`, 2 changes-requested cycles. Helper-proposed deltas: Alejandra **+1**, Nikolaos **+1**; all others delta 0. Distribution discipline: the single ceiling move goes to **Alejandra** — she was the wave's clear top relative performer (6 clean data-quality PRs) and recovers the −1 she took in W22 for a review false-positive. Nikolaos's +1 is absorbed at ceiling.

### Org-Level Team

No org-level (`noorinalabs-main`) scored *implementer* changes this wave — the main-repo activity was orchestrator-run bookkeeping (status keys, memory, ontology, wave-branch merges). Orchestrator self-assessment in the Done/Needs matrix below.

### Child-Repo Teams (data-acquisition + isnad-graph + deploy)

| Rated | Old | New | Reason |
|-------|-----|-----|--------|
| Alejandra Reyes-Fuentes (data-acquisition) | 4 | 5 | prs_merged=6 (da#307/#305/#302/#285/#275/#263 — the data-quality/scrub spine), 0 CI-red, 0 must-fix received, 0 false-positives. Wave top by volume; +1 restores the W22 false-positive dock. Distribution-discipline new-5 → the wave's strongest volume+clean signal. |
| Nikolaos Papadopoulos (data-acquisition) | 5 | 5 | prs_merged=5 (da#286/#284/#274/#267/#264) + must_fix_caught=1, 0 CI-red. Helper proposed +1; absorbed at ceiling. |
| Ivana Horvat (data-acquisition) | 5 | 5 | prs_merged=4 wave-branch (da#312/#310/#277/#269) + PR#322 (da#321 root-cause fix, post-wrapup, 2-reviewer clean). must_fix_received=2 / rework_cycles=2 on the wave-branch set offset clean delivery → delta 0, held at ceiling. |
| Kavitha Sundaramurthy (data-acquisition) | 5 | 5 | prs_merged=1 (da#260) + must_fix_caught=1, 0 CI-red. Delta 0; held at ceiling. |
| Oyunbileg Batbayar (data-acquisition/QA) | 5 | 5 | prs_merged=1 (da#294) + a substantive PR#322 QA review-catch verification (confirmed the two detectors now read the identical authoritative signal, no gaps). Delta 0; held at ceiling. |
| Nneka Obi (isnad-graph) | 5 | 5 | prs_merged=1 (ig#1164), 0 CI-red. Delta 0; held at ceiling. |
| Lucas Ferreira (deploy) | hold | hold | prs_merged=1 (deploy#522), 0 CI-red, 0 must-fix. Baseline — held. |

### Done Well / Needs Improvement (Phase 8 Wave 23) — evidence-anchored, bare "None" banned

| Member | Done Well (with evidence) | Gap (metric, or explicit "clean: numbers") |
|--------|---------------------------|--------------------------------------------|
| **Alejandra Reyes-Fuentes** | 6 clean PRs on the scrub/data-quality spine that produced the 150,187-narrator artifact; wave workhorse | clean: prs_merged=6, must_fix_received=0, ci_red_merges=0, false_positives=0 |
| **Nikolaos Papadopoulos** | 5 clean PRs + a real review catch (must_fix_caught=1) | clean: prs_merged=5, must_fix_received=0, ci_red_merges=0, false_positives=0 |
| **Ivana Horvat** | authored the da#321 root-cause fix (real correctness bug: dual-detector cross_sect divergence), not a test-weakening | 2 must-fix received + 2 rework cycles on the wave-branch NER/segmentation PRs — the wave's main author-side rework signal |
| **Oyunbileg Batbayar** | genuine QA verification on PR#322 (traced both detectors to the same authoritative column) | clean: prs_merged=1, must_fix_received=0, ci_red_merges=0, false_positives=0 |
| **Kavitha Sundaramurthy** | 1 clean PR + a review catch | clean: prs_merged=1, must_fix_received=0, ci_red_merges=0, false_positives=0, must_fix_caught=1 |
| **Nneka Obi / Lucas Ferreira** | 1 clean cross-repo PR each (ig#1164 / deploy#522) supporting the closeout | clean: 0 CI-red, 0 must-fix each |
| **Orchestrator (Nadia)** | ran the prod purge+reload window, record-level verified all 4 #723 criteria at exact stg↔prod parity, closed #723, root-caused + landed da#321 | **initially framed the 44,073 orphan tail as purely "accepted bio narrators"; a preserved stranded-worktree memory surfaced ~26% is da#317 matn-sentence pollution — corrected in-session, but the first framing under-described the tail** |

**Fire/hire:** none. Retirement trigger (`trust_signals.retirement_trigger`) fired for no engineer.

**Concentration note:** 30% top by implementer (Alejandra 6/20) — theme-fit, not fragility: W23 was a single-theme data-quality closeout that her scrub-pipeline ownership naturally concentrated. Below the 60% line; no redistribution action required, but the da#317 matn-sentence carry-forward sits in the same surface, so W24 planning should confirm coverage isn't single-owner.


## Phase 9 Wave 25 Trust Updates (2026-07-19) — Narrator disambiguation & split correctness

Mechanical scoring (`trust_signals.py score 9 25`): **7 PRs**, 1 repo (data-acquisition), top-concentration **43%** (Kavitha Sundaramurthy 3/7 — below the 60% fragility line), **0 CI-red merges**, **0** `review_false_positives`, **0** changes-requested cycles (all verdicts landed as Approved — but see pain-point #1: these clean numbers do NOT capture the verdict-format/gate-bypass breach). Helper-proposed deltas: Ivana **+1**, Kavitha **+1**; Alejandra/Nikolaos delta 0. All four sit at ceiling 5 → both +1s absorbed at ceiling; no row moves.

### Child-Repo Team (data-acquisition)

| Rated | Old | New | Reason |
|---|---|---|---|
| Kavitha Sundaramurthy | 5 | 5 | prs_merged=3 (da#444/#346/#452 — narrator_split gate-correctness spine), 0 CI-red, 0 must-fix received, 0 false-positives. Wave top by volume; helper +1 absorbed at ceiling. |
| Ivana Horvat | 5 | 5 | prs_merged=2 (da#431 narrator_unify + da#347 Anas under-merge), 0 CI-red, clean composition on the shared adjacency helper. Helper +1 absorbed at ceiling. |
| Alejandra Reyes-Fuentes | 5 | 5 | prs_merged=1 (da#366 matn-embedded splitter) + reviewer on #455/#459. Delta 0; held at ceiling. Caught the orchestrator verdict-format error via the enforcer (see Done-Well). |
| Nikolaos Papadopoulos | 5 | 5 | prs_merged=1 (da#439 loader-adjacency reconcile) + reviewer on #458. Delta 0; held at ceiling. |

### Done Well / Needs Improvement (Phase 9 Wave 25) — evidence-anchored, bare "None" banned

| Member | Done Well (with evidence) | Gap (metric, or explicit "clean: numbers") |
|---|---|---|
| Kavitha Sundaramurthy | 3 clean PRs on the split-gate spine; da#452 UNKNOWN-gen abstain gate proven bidirectionally on the real engine | clean: prs_merged=3, must_fix_received=0, ci_red_merges=0, false_positives=0 |
| Ivana Horvat | da#431 + da#347 composed cleanly on the merged adjacency helper; flagged the stacked-PR-orphan lesson | clean: prs_merged=2, must_fix_received=0, ci_red_merges=0; 1 branch-freshness + 1 stacked-PR rebase (env/process, not code) |
| Alejandra Reyes-Fuentes | **Caught the orchestrator's verdict-format brief error by running the actual enforcer (`pr_review_state.py`) instead of trusting the brief** — the single reason the gate-bypass surfaced; da#366 shipped clean | clean: prs_merged=1, must_fix_received=0, ci_red_merges=0, false_positives=0 |
| Nikolaos Papadopoulos | da#439 loader-adjacency reconcile clean; thorough #458 review (verified gate load-bearing via A/B, not vacuous) | clean: prs_merged=1, must_fix_received=0, ci_red_merges=0, false_positives=0 |
| Jean-Claude Habimana (reviewer-only, not score-tracked) | 2 thorough verdicts (#455, #459) with real engine-verification; re-posted correctly-formatted verdicts promptly when the format was corrected | reviewer-only; used the non-counting brief format on first pass (orchestrator-caused), corrected same session |

**Fire/hire:** none. Retirement trigger (`trust_signals.retirement_trigger`) fired for no engineer.

**Concentration note:** 43% top (Kavitha 3/7) — theme-fit (she owns the narrator_split gate-correctness surface), below the 60% line. No redistribution needed.

**Orchestrator self-assessment (negative — the wave's defining signal):** two independent orchestrator-class mechanics errors co-occurred and let 4 feature→wave PRs merge with 0 counted approvals AND no gate block: (1) briefed reviewers with a paraphrased verdict trailer (`RequestOrReplied: Request` + invented `**Review: Approved**`) that Hook 4 counts as zero; (2) merged with `-R $DA` (unexpanded var), which fail-opens Hook 4 (`_resolve_owner_repo`→None→allow). Remediated per owner "Accept + fix records": all 10 genuine approvals PATCHed to the counting form (hook re-count 2/2 each), #981 filed for the fail-open, memory §7/§8 updated. The reviews themselves were genuine; the failure was orchestrator mechanics, not review quality.

## Phase 9 Wave 26 Trust Updates (2026-07-22) — Parse recovery & name quality

Mechanical scoring (`trust_signals.py score 9 26`): **15 PRs**, 2 repos (data-acquisition 13, main 2), top-concentration **20%** (Alejandra Reyes-Fuentes / Kavitha Sundaramurthy tied at 3/15 — well below the 60% fragility line, down from wave-25's 43%), **0 CI-red merges**, **0** `review_false_positives`, **5** changes-requested cycles (must-fix-received: Kavitha 2 + Jean-Claude 2 + Alejandra 1). Helper-proposed deltas: Nikolaos **+2** (must_fix_caught=2, 2 clean PRs — wave top signal), Ivana **+1** (2 clean PRs); all others delta 0. Incumbents sit at ceiling 5, so both +deltas are absorbed at ceiling; no incumbent row moves. Three engineers cross from reviewer-only/untracked into score-tracking this wave (first numeric row) and are seeded at the default neutral **3** — a single clean PR is baseline delivery, not a bump.

### Child-Repo Team (data-acquisition)

| Rated | Old | New | Reason |
|---|---|---|---|
| Nikolaos Papadopoulos | 5 | 5 | prs_merged=2 (da#472 bio_promote gloss-tail/name-cut discrimination + da#473 cleaner-removed-content contract), **must_fix_caught=2** (real catches, no false-positives) — the wave's top composite signal. Helper +2 absorbed at ceiling. |
| Kavitha Sundaramurthy | 5 | 5 | prs_merged=3 (da#474 truncate-and-re-gate recovery, da#476 alif-maqṣūra fold, da#479 drop-gate A/B memory), 0 CI-red. must_fix_received=2, rework_cycles=2 on the hardest surface (name_quality recovery). Delta 0; held at ceiling. |
| Alejandra Reyes-Fuentes | 5 | 5 | prs_merged=3 (da#466 Urdu/Arabic-span extraction, da#468 per-source NER metric, da#470 benediction strip). must_fix_received=1, rework_cycles=1. Delta 0; held at ceiling. |
| Ivana Horvat | 5 | 5 | prs_merged=2 (da#465 informed blocking-token retention, da#469 cross-script Latin fallback), 0 CI-red, 0 must-fix received. Helper +1 absorbed at ceiling. |
| Oyunbileg Batbayar | 5 | 5 | prs_merged=1 (da#461 implausible-death-year scrub) + must_fix_caught=1 (reviewer catch). Delta 0; held at ceiling. |
| Jean-Claude Habimana | (reviewer-only) | 3 | First score-tracked wave as implementer: prs_merged=1 (da#462 dead canonical_matn_identity gate repair + edge-loader wiring), must_fix_received=2, rework_cycles=1. Delta 0 → seeded at neutral 3 (single PR = baseline; the 2 must-fixes are his gap this wave). |
| Kwesi Boateng | (untracked) | 3 | First numeric row: prs_merged=1 (da#463 death-year veto weighting by provenance), 0 CI-red, clean. Delta 0 → seeded at neutral 3 (single clean PR is baseline, not a bump). |

### Org-Level Team (main)

| Rated | Old | New | Reason |
|---|---|---|---|
| Aino Virtanen | 5 | 5 | prs_merged=1 (main#1061 verdict-block spawn-brief template), 0 CI-red, clean. Delta 0; held at ceiling. |
| Nino Kavtaradze | (untracked) | 3 | First numeric row: prs_merged=1 (main#1059 make -R/--repo authoritative over cwd in wave-label hooks — the #985 fix), 0 CI-red, clean. Delta 0 → seeded at neutral 3. |

### Done Well / Needs Improvement (Phase 9 Wave 26) — evidence-anchored, bare "None" banned

| Member | Done Well (with evidence) | Gap (metric, or explicit "clean: numbers") |
|---|---|---|
| Nikolaos Papadopoulos | da#472/#473 shipped clean AND caught 2 real must-fix items as reviewer — the wave's top composite signal | clean: prs_merged=2, must_fix_received=0, ci_red_merges=0, false_positives=0, must_fix_caught=2 |
| Kavitha Sundaramurthy | 3 PRs on the hardest surface (name_quality truncate-and-re-gate recovery + arabic normalization sync) all landed clean, 0 CI-red | 2 must-fix received, 2 rework cycles — the tier-1 recovery discrimination drew the most iteration this wave |
| Alejandra Reyes-Fuentes | 3 PRs across NER metrics + benediction/script extraction; da#466 Urdu-letterform fold shipped clean | 1 must-fix received, 1 rework cycle |
| Ivana Horvat | da#465 + da#469 clean; informed blocking-token retention under the IDF cap composed cleanly | clean: prs_merged=2, must_fix_received=0, ci_red_merges=0, false_positives=0 |
| Oyunbileg Batbayar | da#461 death-year scrub clean + 1 genuine reviewer must-fix catch | clean: prs_merged=1, must_fix_received=0, ci_red_merges=0, false_positives=0, must_fix_caught=1 |
| Jean-Claude Habimana | da#462 repaired a dead canonical_matn_identity gate and wired the edge loader to see it — a load-bearing correctness fix | 2 must-fix received on his single PR (the highest per-PR must-fix rate this wave); reworked once, landed clean |
| Kwesi Boateng | da#463 weighted the fuzzy_cluster death-year veto by death_year_provenance — shipped clean first pass | clean: prs_merged=1, must_fix_received=0, ci_red_merges=0, false_positives=0 |
| Aino Virtanen | main#1061 promoted the verbatim verdict-block into the reviewer spawn-brief template (structural fix for the W25 paraphrase-bypass class) | clean: prs_merged=1, must_fix_received=0, ci_red_merges=0, false_positives=0 |
| Nino Kavtaradze | main#1059 made -R/--repo authoritative over cwd in the wave-label hooks (the #985 fix) — closed the cwd-anchor misresolution class | clean: prs_merged=1, must_fix_received=0, ci_red_merges=0, false_positives=0 |

**Fire/hire:** none. Retirement trigger (`trust_signals.retirement_trigger`) fired for no engineer.

**Concentration note:** 20% top (Alejandra / Kavitha tied at 3/15) — well below the 60% line and down from wave-25's 43%. Load distributed across 9 implementers; no fragility, no redistribution needed.

**Orchestrator self-assessment:** clean wave. Both wave→main merges landed green (main#1063 28/28, da#480 22/22), reachability clean (ahead_by=0 both), staging green, 0 CI-red merges across all 15 PRs. The W25 gate-bypass class was structurally closed this wave (main#1059/#1061 + the #981/#1056/#1057 fail-closed hook-hardening chain). No verdict-format or fail-open recurrence.

## Phase 9 Wave 27 Trust Updates (2026-07-22) — Pre-cutover data-quality closeout + Phase-9 tooling cleanup (last wave of Phase 9)

Mechanical scoring (`trust_signals.py score 9 27`): **17 PRs**, 2 repos (main 13, data-acquisition 4), top-concentration **18%** (Aino Virtanen / Nino Kavtaradze / Weronika Zielinska tied at 3/17 — well below the 60% fragility line), **0 CI-red merges**, **0** `review_false_positives`, **2** changes-requested cycles (must-fix-received: Alejandra 1 on da#484, Weronika 1 on #1079 — both merge-gate catches, fixed + re-CI'd + re-approved fresh). **CR-cycle counter note:** recomputation from current review state finds 0 `CHANGES_REQUESTED` because both verdicts were edited-in-place to Approved after fixes (charter § verdict-amendment); the claimed **2** stands as authoritative-historic (P3W15 CR-cycle semantics), recorded in `wave_27_counter_corrections`. Helper-proposed deltas: Aino **+1**, Nino **+1**, Lucas **+1**, Nurul **+1**; all others delta 0.

### Org-Level / Tooling Team (main)

| Rated | Old | New | Reason |
|---|---|---|---|
| Aino Virtanen | 5 | 5 | delta +1 (prs_merged=3 clean: #1081 share one verdict-set entry point across Hook 4/Hook, #1075 make content_ts required on shared gate helpers, #1071 reviewer-set follows each reviewer's latest verdict), 0 CI-red, 0 must-fix. Helper +1 absorbed at ceiling. |
| Nino Kavtaradze | 3 | 4 | delta +1 (prs_merged=3 clean: #1078 reviewer-rationale doc, #1076 TechDebt trailer accepts bare issue numbers + surfaces unparseable, #1072 premise_check bare-slash false-STOP fix), 0 CI-red. Earns the first bump off last wave's neutral seed. |
| Lucas Ferreira | (deploy: hold) | 4 | First main-repo implementer scoring: delta +1 (prs_merged=2 clean: #1077 harden walk_flag_values to real gh/cobra flag semantics, #1070 normalize wave_{M}_meta_issue read+write), 0 CI-red. Seeded neutral 3 + earned bump (same establishment convention as Nino W26). |
| Nurul Hakim | (deploy: hold) | 4 | First main-repo implementer scoring: delta +1 (prs_merged=2: #1073 rg --hidden gotcha doc, #1069 pin last-unkilled mutation on handoff-skip; **must_fix_caught=1** — held the merge gate on #1079's fail-open `read_checksums` deepcopy bug), 0 CI-red. Seeded neutral 3 + earned bump. |
| Weronika Zielinska | (deploy: hold) | 3 | First main-repo implementer scoring: delta 0 (prs_merged=3: #1080 checksums ASCII CI-gate, #1079 shared checksums_io helper, #1074 generalize ontology_tracker SKIP_PATTERNS; **must_fix_received=1** on #1079 blocks the multi-PR bump, rework_cycles=1), 0 CI-red. Seeded at neutral 3. |

### Child-Repo Team (data-acquisition)

| Rated | Old | New | Reason |
|---|---|---|---|
| Alejandra Reyes-Fuentes | 5 | 5 | delta 0 (prs_merged=1 da#484 bound attested death_year_ah to isnad-plausibility envelope — the sole Tier-1 cutover gater; **must_fix_received=1** — Jean-Claude's gate catch on the date_reconcile scrub-swallow reachable on both resume + from-scratch paths, rework_cycles=1). Held at ceiling. |
| Ivana Horvat | 5 | 5 | delta 0 (prs_merged=1 da#481 share resolve-stage gross death-year spread band, clean). Held at ceiling. |
| Kavitha Sundaramurthy | 5 | 5 | delta 0 (prs_merged=1 da#482 record the ى→ي fold full-corpus A/B artifact, clean). Held at ceiling. |
| Oyunbileg Batbayar | 5 | 5 | delta 0 (prs_merged=1 da#483 extend da#439 adjacency invariant across multi-isnad graph, clean). Held at ceiling. |
| Jean-Claude Habimana | 3 | 3 | delta 0 (0 PRs, **must_fix_caught=1** — the load-bearing da#454/#484 date_reconcile catch; a single catch is below the +1 threshold of ≥2). Held at neutral. |

Distribution discipline: no proposed 5 lands on a non-top performer — the two ceiling-ward +1 deltas are Aino (already 5, absorbed) and none other reaches 5; top relative composite is Aino & Nino (3 clean PRs each). No cap applied.

### Done Well / Needs Improvement (Phase 9 Wave 27) — evidence-anchored, bare "None" banned

| Member | Done Well (with evidence) | Gap (metric, or explicit "clean: numbers") |
|---|---|---|
| Aino Virtanen | 3 clean tooling-hardening PRs (#1081 shared verdict-set entry point, #1075 required content_ts, #1071 latest-verdict reviewer set) that tightened the review-gate primitives | clean: prs_merged=3, must_fix_received=0, ci_red_merges=0, false_positives=0, must_fix_caught=0 |
| Nino Kavtaradze | 3 clean PRs incl. #1072 fixing the premise_check bare-slash 12/12 false-STOP class flagged at W26 retro | clean: prs_merged=3, must_fix_received=0, ci_red_merges=0, false_positives=0 |
| Lucas Ferreira | 2 clean PRs (#1077 real gh/cobra flag semantics, #1070 meta_issue read/write normalize) | clean: prs_merged=2, must_fix_received=0, ci_red_merges=0, false_positives=0 |
| Nurul Hakim | 2 clean PRs AND held the merge gate on #1079's fail-open deepcopy bug (must_fix_caught=1) | clean: prs_merged=2, must_fix_received=0, ci_red_merges=0, false_positives=0, must_fix_caught=1 |
| Weronika Zielinska | 3 tooling PRs incl. #1079 shared checksums_io helper + #1074 SKIP_PATTERNS generalize | 1 must-fix received on #1079 (fail-open `read_checksums` returned a shallow dict aliasing the module-global) — caught at the gate, fixed with a regression test |
| Alejandra Reyes-Fuentes | da#484 landed the sole Tier-1 cutover gater (death_year isnad-plausibility bound), satisfying the #978 cutover precondition | 1 must-fix received (date_reconcile scrub-swallow, reachable on both cutover paths) — caught at the gate, fixed with `scrub_cleared` sentinel + regression test |
| Ivana Horvat | da#481 shared the resolve-stage death-year band cleanly | clean: prs_merged=1, must_fix_received=0, ci_red_merges=0, false_positives=0 |
| Kavitha Sundaramurthy | da#482 documented the ى→ي fold full-corpus A/B artifact | clean: prs_merged=1, must_fix_received=0, ci_red_merges=0, false_positives=0 |
| Oyunbileg Batbayar | da#483 extended the adjacency invariant across the multi-isnad graph | clean: prs_merged=1, must_fix_received=0, ci_red_merges=0, false_positives=0 |
| Jean-Claude Habimana | held the Tier-1 gate — caught the da#454 date_reconcile scrub-swallow that a naive review would have passed (a cutover data-integrity catch) | clean: prs_merged=0, ci_red_merges=0, false_positives=0, must_fix_caught=1 |

**Fire/hire:** none. Retirement trigger (`trust_signals.retirement_trigger`) fired for no engineer — all ≥3, 0 CI-red across the wave.

**Concentration note:** 18% top (Aino / Nino / Weronika tied at 3/17) — well below the 60% fragility line, distributed across 10 implementers. Theme-fit (last-wave-of-phase cleanup pulled the full tooling-debt backlog); no redistribution needed.

**Orchestrator self-assessment:** clean Phase-9-closing wave. 0 CI-red across all 17 PRs; both genuine must-fixes (da#454 cutover scrub-swallow + #1079 fail-open shared-state primitive) caught at the Opus merge gate, fixed with regression tests, re-approved fresh. Both wave→main merges owner-approved and green; reachability ahead_by=0; staging green. Two process debts surfaced for follow-up: the change-tracker hook polluting the parent `ontology/checksums.json` with 131 gitignored child-repo paths, and 3 dirty semantic checksums surviving into retro (wrapup ontology step gap).

## Phase 10 Wave 28 Trust Updates (2026-07-27) — Stop-the-bleeding (Track-0 High defects + fill wins) — Phase-10 opener

Mechanical scoring (signals computed over the canonical direct-to-main PR set — the `trust_signals.py score 10 28` helper returns empty because `merged_prs` is hardcoded to the wave-branch base, filed as **#1131**; signals were extracted by feeding the canonical 12-PR set into the real `extract_signals` logic and persisted to `wave_28_trust_signals`): **12 PRs** across 5 repos (main 4, ingest-platform 3, data-acquisition 3, user-service 1, isnad-graph 1), top-concentration **17%** (Weronika Zielinska / Nino Kavtaradze tied at 2/12 — well below the 60% fragility line, spread across 11 people), **0 CI-red merges**, **0** `review_false_positives`, **3** changes-requested cycles (must-fix-received: Kavitha 2 on da#502, Weronika 1 on #1126 — both merge-gate catches, fixed + re-CI'd). Helper-proposed deltas: Nino **+1**, Oyunbileg **+1** (clamped at ceiling); all others delta 0.

### Org-Level / Tooling Team (main + isnad-graph)

| Rated | Old | New | Reason |
|---|---|---|---|
| Aino Virtanen | 5 | 5 | delta 0 (prs_merged=1 #1130 pin ruff==0.15.11 to match pre-commit — unblocked the whole main Ruff-format gate; the prerequisite the other 3 main PRs merged on top of, clean). Held at ceiling. |
| Nino Kavtaradze | 4 | 5 | delta +1 (prs_merged=2 clean: #1127 extract auto-close-issues into a reusable `workflow_call`, #1128 memoize shared shell-parse primitives + commit prefilter; **must_fix_caught=1** as reviewer), 0 CI-red. Wave's top composite performer (3) — distribution discipline permits the 5. Second consecutive +1 (3→4→5). **Owner veto check RESOLVED 2026-07-27: promotion APPROVED, veto not exercised.** Corroborating evidence post-dating the retro: the Opus merge-gate review on #1136 found **4 MUST-FIX, all of which reproduced before fixing** — including a `/worktrees/` substring test that failed *closed* and was silently skipping committed source (a submodule under `.git/modules/worktrees/`, and `clone --separate-git-dir` parked under any `worktrees/` dir), a `prune` from a worktree proposing deletion of 141/277 entries at exit 0, and a `--repo-root /nonexistent` proposing all 277 at exit 0. He also correctly classified one candidate as an **equivalent mutant** (`and`→`or` in the admin-dir check) rather than demanding a test that cannot discriminate — precision in both directions. |
| Weronika Zielinska | 3 | 3 | delta 0 (prs_merged=2: #1126 hoist O(1) throttle check before transcript parse, isnad-graph#1203 aggregate hadith facets in Cypher + Redis TTL cache; **must_fix_received=1** on #1126, rework_cycles=1 — below the −1 threshold of 3). Held at 3. |

### Child-Repo Team (isnad-ingest-platform)

| Rated | Old | New | Reason |
|---|---|---|---|
| Kalinda Ranasinghe | (untracked) | 3 | First numeric row: prs_merged=1 (ip#149 clear pip-audit CVE drift — kafka-python/pyasn1/click bumps that unblocked all ingest-platform pushes ahead of #140/#141), clean. Seeded at neutral 3. |
| Yusuke Inoue | (untracked) | 3 | First numeric row: prs_merged=1 (ip#150 commit Kafka offsets after checkpoint + earliest reset — the offset-after-checkpoint data-loss fix, BUG), clean. Seeded at neutral 3. Reassigned implementer (from Jean-Claude Habimana; ip commit-identity gate). |
| Léopold Mbongo | (untracked) | 3 | First numeric row: prs_merged=1 (ip#151 quarantine unparseable messages to DLQ + producer↔consumer contract test; resolved a real conflict with #150 in `handle_one`), clean. Seeded at neutral 3. Reassigned implementer (from Jean-Claude Habimana; ip commit-identity gate). |

### Child-Repo Team (data-acquisition)

| Rated | Old | New | Reason |
|---|---|---|---|
| Nikolaos Papadopoulos | 5 | 5 | delta 0 (prs_merged=1 da#503 align raw.landed producer to consumer PipelineMessage shape — coupled with ip#151, clean). Held at ceiling. |
| Alejandra Reyes-Fuentes | 5 | 5 | delta 0 (prs_merged=1 da#504 edge_load_conformance false-positive + GRADED_BY orphan gap — the Tier-3 cutover carry-forward, clean). Held at ceiling. |
| Kavitha Sundaramurthy | 5 | 5 | delta 0 (prs_merged=1 da#502 memoize normalize_arabic with lru_cache; **must_fix_received=2** on #502, rework_cycles=1 — below the −1 threshold of 3, both caught at the gate and fixed). Held at ceiling. |
| Oyunbileg Batbayar | 5 | 5 | delta +1 clamped at ceiling (prs_merged=0, **must_fix_caught=2** — the two real da#502 review catches, no false-positives). Held at 5. |

### Child-Repo Team (user-service)

| Rated | Old | New | Reason |
|---|---|---|---|
| Nadia Boukhari | (untracked) | 3 | First numeric row: prs_merged=1 attributed (us#212 reject SSO-cookie tokens replayed as Bearer). **Attribution caveat:** Nadia authored only the *mechanical merge commit* — the implementer of record is **Nurul Hakim** (implementor label `NURUL_HAKIM`), who is NOT on the user-service roster; the local commit-identity gate blocked him, so the merge commit was attributed to Nadia (a valid us-roster member). Seeded at neutral 3. Roster-union fix carried forward (see feedback log). |

Distribution discipline (`trust_signals.apply_distribution_discipline`): Nino's proposed 5 is the wave's unique top composite (2 PRs + 1 review-catch = 3) and stands; Oyunbileg's +1 is absorbed at the ceiling. No non-top 5 landed; no cap applied.

### Done Well / Needs Improvement (Phase 10 Wave 28) — evidence-anchored, bare "None" banned

| Member | Done Well (with evidence) | Gap (metric, or explicit "clean: numbers") |
|---|---|---|
| Aino Virtanen | #1130 pinned ruff to match pre-commit — the prerequisite fix that unblocked the entire main Ruff-format gate for the wave | clean: prs_merged=1, must_fix_received=0, ci_red_merges=0, false_positives=0, must_fix_caught=0 |
| Nino Kavtaradze | 2 clean PRs (#1127 reusable auto-close workflow, #1128 shell-parse memoization) AND caught a must-fix as reviewer — top composite performer of the wave | clean: prs_merged=2, must_fix_received=0, ci_red_merges=0, false_positives=0, must_fix_caught=1 |
| Weronika Zielinska | 2 PRs incl. isnad-graph#1203 (Cypher facet aggregation + Redis cache) + #1126 throttle hoist | 1 must-fix received on #1126 — caught at the merge gate, fixed |
| Kalinda Ranasinghe | ip#149 cleared the pip-audit CVE drift that was blocking every ingest-platform push — the load-bearing prerequisite for #140/#141 | clean: prs_merged=1, must_fix_received=0, ci_red_merges=0, false_positives=0, must_fix_caught=0 |
| Yusuke Inoue | ip#150 fixed the Kafka offset-after-checkpoint data-loss class (commit after checkpoint + earliest reset) | clean: prs_merged=1, must_fix_received=0, ci_red_merges=0, false_positives=0, must_fix_caught=0 |
| Léopold Mbongo | ip#151 DLQ quarantine + producer↔consumer contract test; resolved a real `handle_one` conflict with #150 keeping both control flows correct | clean: prs_merged=1, must_fix_received=0, ci_red_merges=0, false_positives=0, must_fix_caught=0 |
| Nikolaos Papadopoulos | da#503 aligned the raw.landed producer to the consumer PipelineMessage shape (coupled fix with ip#151) | clean: prs_merged=1, must_fix_received=0, ci_red_merges=0, false_positives=0, must_fix_caught=0 |
| Alejandra Reyes-Fuentes | da#504 closed the edge_load_conformance false-positive + GRADED_BY orphan gap (Tier-3 carry-forward) | clean: prs_merged=1, must_fix_received=0, ci_red_merges=0, false_positives=0, must_fix_caught=0 |
| Kavitha Sundaramurthy | da#502 memoized normalize_arabic with lru_cache | 2 must-fix received on #502 (rework_cycles=1) — both caught at the gate and fixed; below the −1 threshold |
| Oyunbileg Batbayar | caught both da#502 must-fixes as reviewer (must_fix_caught=2, no false-positives) — the wave's strongest review signal | clean: prs_merged=0, must_fix_received=0, ci_red_merges=0, false_positives=0, must_fix_caught=2 |
| Nadia Boukhari | authored the us#212 merge commit that landed the SSO-Bearer-replay rejection fix | clean: prs_merged=1, must_fix_received=0, ci_red_merges=0, false_positives=0 (mechanical merge commit; implementation credit → Nurul Hakim) |

**Fire/hire:** none. Retirement trigger (`trust_signals.retirement_trigger`) fired for no engineer — all ≥3, 0 CI-red across the wave.

**Concentration note:** 17% top (Weronika / Nino tied at 2/12) — well below the 60% fragility line, spread across 11 people. Healthy distribution for a cross-repo stop-the-bleeding wave; no redistribution needed.

**Orchestrator self-assessment:** clean Phase-10-opening wave — the direct-to-main "stop-the-bleeding" batch was merged the prior session; this was the closeout + retro. 0 CI-red across all 12 PRs; both genuine must-fix threads (da#502 ×2, #1126 ×1) caught at the Opus merge gate and fixed. All post-merge deployable workflows green; staging promotion green. Notable process finding this wave: the wave-counter and trust-signal helpers do not support direct-to-main waves (both returned empty), forcing manual computation — filed as #1131. Roster-drift (Nurul Hakim scoped onto a user-service story he cannot commit to) carried forward from wave-27→28, still unresolved.
