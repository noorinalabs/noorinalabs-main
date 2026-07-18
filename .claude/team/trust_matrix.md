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
