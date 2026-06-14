---
name: Phase 4 plan — light up the product
description: Phase definition, end-state criteria, exit gate, wave plan
phase: 4
status: exited
created: 2026-06-02
last_updated: 2026-06-14
---

# Phase 4 — light up the product

## Theme

Phase 3 left a deployed-but-empty platform: staging and production are live, CI is hardened org-wide, branch protection is enforced — but **the data pipeline has never run end-to-end and the graph holds no real corpus data**. Phase 3's own trajectory analysis named the exit condition: *"the meta-loop tapers when the deploy track ships + the product surface re-opens."*

Phase 4 is that re-opening. Three tracks:

1. **Data** — run the acquisition → B2 → Kafka → workers → Neo4j pipeline end-to-end with real hadith data; make it repeatable.
2. **Product** — make the research surface (search, timeline, graph explorer) usable with real data on production; complete the admin surface.
3. **Debt-to-zero** — resolve the Phase-3 criterion-9 caveat: re-confirm ≤20% at the first `/phase-review`, reach <10% cumulative by phase exit.

## End-state criteria — Phase 4 exits when ALL hold

| # | Criterion | Tracker |
|---|-----------|---------|
| 1 | **Data pipeline runs end-to-end** — sunnah_api → B2 → Kafka → workers → Neo4j on staging, repeatable, dedup-safe | noorinalabs-main#601 |
| 2 | **Product usable with real data** — search/timeline/graph return real corpus results on production | noorinalabs-main#602 |
| 3 | **Admin surface complete** — user mgmt via user-service, data management panel, pipeline controls | noorinalabs-main#603 |
| 4 | **Zero carry-forward bugs** — us#65/#73/#74, lp#69 closed | noorinalabs-main#604 |
| 5 | **Security follow-ups closed** — deploy#386/#384/#244, ig#955 | noorinalabs-main#605 |
| 6 | **Tech-debt intake — each wave takes its +20%** — every wave pulls in tech-debt-only issues = `ceil(20% of its feature/bug/security scope)` per `/wave-scope` Step 8.5 (all available if fewer). **Replaces** the brittle cumulative-ratio gate (superseded 2026-06-09, PR #619 / main#618); the pooled TD ratio stays **informational**, no longer a hard threshold | noorinalabs-main#606 |
| 7 | **P3 retro process changes applied + verified** — all 4 owner-approved changes dispositioned | noorinalabs-main#607 |

> **P4W5 exit-drive re-disposition (2026-06-13, owner-approved at `/wave-scope 4 5`):** criteria **#2 (Product usable with real data on production — main#602)** and **#3 (Admin surface complete — main#603)** are **carried forward to Phase 5**. Staging was lit up and the pipeline runs there, but production cutover + admin completion are P5 work. The **Phase 4 exit gate for W5 therefore covers criteria #1, #4, #5, #6, #7** (#602/#603 explicitly excluded from the P4 exit set and re-scoped at `/plan-phase 5`). W5 theme: *Phase-4 exit drive — verify, audit & close-out*.

## The Phase-3 criterion-9 caveat (inherited obligation) — RESOLVED 2026-06-02

Phase 3 closed at 9/9 **with a caveat** (see `phase-3.md` § Phase exit record): criterion #9's "2 consecutive `/phase-review` runs" requirement is satisfied by run 1 = P3W15 wave-end + **run 2 = Phase 4's first `/phase-review`**, which MUST re-confirm cumulative ≤20% (trending toward <10%) and report the trailing-window new-filed ratio. This re-confirmation is a **blocking precondition for Phase 4 Wave 1 kickoff** — it happens at the `/phase-review 4` that precedes `/wave-scope 4 1`.

**Resolution (2026-06-02, `/phase-review 4`):** the re-confirmation ran; the gate measured **over** (raw 22.2%,
re-baselined 23.6%) due to denominator shrinkage from P3 closures, not new debt. The owner re-baselined the
methodology (`meta-issue`-labeled scaffolding excluded from all TD-ratio measurements) and **waived the kickoff
block**, on the grounds that W1 "Clean slate" is itself the burn-down remedy. Conditions of the waiver:

- ~~The ≤20% gate (re-baselined) is **re-measured at P4W1 `/wave-wrapup` as a hard block** — no second waiver.~~ **Superseded 2026-06-09 (PR #619 / main#618):** the hard ratio re-measure is replaced by the per-wave **tech-debt intake** model (`/wave-scope` Step 8.5 — +20% of each wave's feature/bug/security scope). `/wave-wrapup` no longer enforces any ratio threshold; the pooled ratio is reported as informational only.
- Criterion #6 (main#606) now measures **per-wave intake compliance**, not a `<10%` cumulative exit ratio. Rationale: a cumulative ratio whipsaws as the backlog shrinks (denominator collapses faster than real debt) — owner call 2026-06-09.

Full record: `phase-3.md` § Criterion #9 caveat resolution.

### TD-ratio measurement methodology (re-baselined 2026-06-02; **informational only as of 2026-06-09**)

As of 2026-06-09 (PR #619) the pooled TD ratio is **reported, not gated** — the gate is per-wave intake (`/wave-scope` Step 8.5). When reporting it (phase reviews, wrapup summaries), use:

```
TD ratio = (open issues labeled tech-debt AND NOT meta-issue)
         / (open issues NOT labeled meta-issue)        — pooled across all 8 repos
```

## Wave plan (proposed at /plan-phase, owner-approved 2026-06-02)

| Wave | Theme | Scope summary |
|------|-------|---------------|
| **W1** | **Clean slate** — bugs + security + TD burn-down | All 4 live bugs, 4 security follow-ups, 12 TD carry-forwards. Meta-issue: noorinalabs-main#608. Serves criteria 4/5/6. |
| **W2** | **First light** — pipeline end-to-end | main#139 (keystone), main#136, da#21/#26/#65, ingest#2. Serves criterion 1. |
| **W3** | **Open the doors** — product surface | Admin cluster (ig#804/#805/#806, main#138), us#43 email login, ig#703 i18n, lp#46 Team page, ig#721 geo filtering, **deploy#388 secrets-manager ADR (owner decision, scheduled 2026-06-02)**. Serves criteria 2/3. |
| **W4** | **Phase exit** — verification + close-out | Production data verification, criterion audit, phase retro, **deploy#387 password-rotation automation (depends on #388 ADR)**. Spillover buffer. |

Wave themes are confirmed (not re-chosen) at each `/wave-scope`; scope reconciliation may move issues between waves.

## Out of scope for P4 (deferred)

- **Billing/payments** (ig#717/#718) — needs product traction first
- **CDN + performance ops** (ig#706/#711/#712, lp#33/#34/#35, deploy#12) — optimize after real traffic exists
- **Developer portal** (lp#42, deploy#19), **notifications** (ig#704), **visual-asset sourcing** (ig#719, lp#37, ds#24)
- **Playwright live-site automation** (main#56/#57)
- ~~**Secrets-manager ADR + rotation automation** (deploy#387/#388)~~ → **re-dispositioned 2026-06-02: scheduled into W3 (#388) + W4 (#387)** per owner decision at first `/phase-review`
- **Hetzner sizing analysis** (main#142) — revisit when pipeline load is real

## Phase exit gate

Owner runs `/phase-review 4` and verifies all 7 end-state rows are `Done`, including criterion-6 — **every wave took its +20% tech-debt intake** (`/wave-scope` Step 8.5); the pooled ratio is reported informationally and should be trending down, but is not a hard threshold. On confirmation, the next phase is defined via `/plan-phase` before any P5 wave can kick off (per `lifecycle.md` § Phase Lifecycle).

## Process changes in force from P3 retro (applied at phase setup, 2026-06-02)

1. **Issue-filing premise verification at origin HEAD** — charter `issues.md` § Issue-Filing Premise Verification (applied)
2. **upsert_status_keys.py update-key fix** — main#595, W1 scope
3. **Annunaki content-display suppression** — main#596, W1 scope
4. **CR-cycle counter semantics** — `/wave-retro` Step 2.5 (applied)

## References

- `.claude/team/lifecycle.md` — canonical phase/wave/session skill order
- `.claude/team/phases/phase-3.md` — prior phase (complete 2026-06-02, criterion-9 caveat inherited here)
- `cross-repo-status.json` — live counters (`phase_4_*` keys)
- noorinalabs-main#520 — the wave-10 stranding recovery executed at the P3/P4 boundary (14 PRs)


## Phase exit record (2026-06-14, `/phase-review 4`, owner-confirmed)

**Phase 4 EXITED.** Exit set #1/#4/#5/#6/#7 all satisfied; #2/#3 carried to Phase 5 (W5 exit-drive re-disposition).

| # | Criterion | Tracker | Resolution |
|---|-----------|---------|------------|
| 1 | Data pipeline E2E (staging) | main#601 | Closed P4W6 — real narrator graph live on staging |
| 4 | Zero carry-forward bugs | main#604 | Closed |
| 5 | Security follow-ups closed | main#605 | Closed |
| 6 | Per-wave TD intake (+20%) | main#606 | Closed 2026-06-14 — intake taken every wave W1–W7 (W2 3/2, W3 3/3, W4 8≥7, W5 2/2, W6 1-eff, W7 1/1; W1 clean-slate burn-down) |
| 7 | P3 retro process changes | main#607 | Closed |

**Informational TD ratio at exit:** 30% (19/63 pooled) — reported only, not a gate (superseded 2026-06-09); expected denominator-shrink, most are P5-deferred bug-bash + W7 follow-ups.

**Carried to Phase 5:** product-usable-on-production (#602), admin-surface-complete (#603), plus the live bug-bash spine (da#146 chain-segmentation, ig#1024 narrators-500, ig#1025/1026/1027, da#147/148/144, deploy#443) and W7 process follow-ups (main#659/#661/#663/#664). Scoped at `/plan-phase 5`.
