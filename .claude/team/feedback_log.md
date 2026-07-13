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
