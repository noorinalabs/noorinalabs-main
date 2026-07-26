---
name: Phase 10 plan — Code-Audit Program to Depletion (org-wide DRY / LOC / runtime-memory)
description: Phase definition, end-state criteria, exit gate, wave plan
phase: 10
status: active
created: 2026-07-26
last_updated: 2026-07-26
---

# Phase 10 — Code-Audit Program to Depletion

## Theme

Phase 9 closed with the #978 re-cut cutover unblocked and the tooling-debt backlog drained.
Phase 10's spine is a single deliberate cleanup program: **drive the 2026-07 org-wide code
audit (umbrella `main#1089`) to depletion.** The audit (`CODE_AUDIT.md`, auditor Aino
Virtanen + 8 per-repo agents) measured the org at ~374K non-blank LOC and found that the
biggest structural problems are all *duplication-drift* classes — the data-acquisition ↔
ingest-platform twin (~11.7K duplicated lines, already one live prod break), a triplicated
Pydantic domain model, org gate tooling vendored 7–8×, and ~15.1K lines of copy-pasted
workflow YAML — plus **12 fix-now defects (Track 0)** most of which exist *because* a copy
drifted and lost a property the original had.

This is a **debt-reduction phase, not a feature phase.** The goal is to land the audit's
tracks, remove the drift classes structurally (not just detect them), and close the umbrella.
Estimated total effect if all tracks land: **≈ 30–38K LOC removed org-wide** (~8–10% of the
org), the twin-repo and vendored-tooling drift classes eliminated, ~1.5–3h cut from the
~7.5h resolve run, plus an OOM class and several user-facing perf wins fixed.

Owner directives feeding this plan (2026-07-26, all durable — see `session_handoff.md`):

- **Phase 10 spine = the code-audit program until depleted** (it is THE priority).
- **Track 0 (12 defects) folded in as normal stories**; the 4 High-severity defects
  (BUG-01/02/03/04) front-load into wave-28.
- **Feature-intake ceiling** confirmed for the phase — the risk is features crowding out the
  program, not the +20% TD floor. Off-program feature work is triaged in, not assumed.
- **Tracks A & B are FROZEN** pending the owner's review of the `noorinalabs-common` new-repo
  proposal (`CODE_AUDIT.md` §4; A1 decision issue `main#1099`). Do NOT scope any A/B work
  until the owner rules. Tracks 0 / C / D / E / F / G / H proceed.
- **C1 reusable-workflow host = publish from `noorinalabs-main`** (no new repo), mitigated
  with tagged-SHA pins + a scoped `.github/workflows/` prefix. A later migration to a
  dedicated `noorinalabs/.github` repo is tracked separately in `main#1124`.
- **F1 (da IVF default flip) stays behind an A/B pair-set-delta measurement gate** — the
  default change never merges on static reasoning alone.

> **Backlog source:** the project board (Project 2) is the P10 candidate pool (charter
> `issues.md § Wave Planning — Project Board Is Authoritative`). The program is fully filed:
> umbrella `main#1089`, nine track epics `main#1090–1098` (Track 0 + A–H), and 89 audit
> stories, all on the board (verified 0 drift at plan time). Two Phase-9 cutover
> carry-forwards (`da#489`, `da#490`) fold into wave-28.

## Program structure (umbrella `main#1089`)

| Epic | Track | Nature | Est. LOC | Frozen? |
|------|-------|--------|---------:|---------|
| `main#1090` | **Track 0** — 12 fix-now defects (bugs) | correctness / security / perf | — | no |
| `main#1091` | **Track A** — shared org libraries (`noorinalabs-common`) | DRY / architecture | ~11,300 | **FROZEN** (main#1099) |
| `main#1092` | **Track B** — twin-repo resolution (da ↔ ip) | DRY / LOC | ~14–17.7K | **FROZEN** (depends on A) |
| `main#1093` | **Track C** — CI/CD & workflow dedup | DRY | ~3.5–4.1K | no |
| `main#1094` | **Track D** — isnad-graph DRY & runtime | DRY / perf | ~1.4K | no |
| `main#1095` | **Track E** — user-service DRY & auth hot path | DRY / perf | ~0.5–0.6K | no |
| `main#1096` | **Track F** — pipeline runtime & memory | perf / memory | ~1.5–2.1K | no |
| `main#1097` | **Track G** — parent hooks/lib efficiency & DRY | DRY / perf | ~2.4–3.3K | no |
| `main#1098` | **Track H** — design-system & landing-page | DRY / correctness | ~0.7–0.8K | no |

Track A carries the single biggest LOC win (~25K combined with B), so full depletion of the
umbrella is **gated on the A1 owner decision (`main#1099`).** If A/B stay frozen past this
phase, P10 delivers Tracks 0 / C–H and the umbrella depletion criterion below carries the
A/B remainder forward to a later phase — an explicit, owner-visible split, not a silent miss.

## End-state criteria — Phase 10 exits when ALL hold

| # | Criterion | Tracker | Nature |
|---|-----------|---------|--------|
| 1 | **All 12 Track-0 defects landed & verified at origin** — each fix applied-and-verified with its named regression test (charter `issues.md § End-State Criterion`); BUG-03's two coupled PRs land together | `main#1090` (BUG-01…12) | fix + test |
| 2 | **Tracks C–H depleted** — every story in epics `main#1093–1098` merged & verified, or explicitly owner-deferred with a tracker; each epic closed | `main#1093–1098` | DRY / perf |
| 3 | **A1 decision resolved** — the owner ratifies, amends, or declines the `noorinalabs-common` proposal (`main#1099`). If ratified, Tracks A/B execute; if declined/deferred, the A/B remainder is re-homed to a later phase with a written disposition | `main#1099`, `main#1091/1092` | decision |
| 4 | **Umbrella disposition** — `main#1089` closed when Tracks 0 + C–H are depleted AND Tracks A/B are either depleted (if unfrozen) or formally carried forward per criterion 3 | `main#1089` | close-out |
| 5 | **Per-wave TD-intake compliance** verified across all P10 waves; final wave = heavy TD floor (see below) | wave scope keys | policy |

## Wave plan (provisional — wave-28 settled, 29+ scoped per-wave)

Sequencing follows `CODE_AUDIT.md §12` (Track 0 first; C/D/E/F/G/H run in parallel — per-repo
and mostly independent; A/B gated on the A1 decision and, for B3, on the #978 cutover). Only
**wave-28 is settled**; waves 29–32 are a directional sketch — each is concretely scoped at
its own `/wave-scope`, and the A/B tranche only appears once `main#1099` is ratified.

### Wave 28 (global 28) — SETTLED · merge model: direct-to-main per story (BUG-03's two PRs coupled)

**Theme (owner-set, mandatory gate):** *"Stop-the-bleeding — Track-0 high-severity defects
(security / data-loss / pipeline / perf) + low-risk LOC/perf fill wins + carry-forward closeout."*

| Issue | Title | Implementer | Merge-gate reviewer | Priority |
|-------|-------|-------------|--------------------|----------|
| `us#204` | BUG-01 JWT decode dedup (SSO→Bearer replay) | Nurul Hakim | Aino Virtanen | High (security) |
| `ip#140` | BUG-02 commit Kafka offsets + `earliest` | Jean-Claude Habimana | Nikolaos Papadopoulos | High (data-loss) |
| `da#492` + `ip#141` | BUG-03 align producer↔consumer + `parse_message` in DLQ + round-trip test | Nikolaos Papadopoulos (da) + Jean-Claude Habimana (ip) | Aino Virtanen + Oyunbileg Batbayar | High (pipeline-down) — **two PRs, land together** |
| `ig#1191` | BUG-04/D1 facets Cypher aggregation + Redis TTL | Weronika Zielinska | Lucas Ferreira | High (perf, user-facing) |
| `da#495` | F3 `lru_cache` normalize_arabic | Kavitha Sundaramurthy | Oyunbileg Batbayar | fill (XS) |
| `main#1115` | G3 throttle-check before transcript scan | Weronika Zielinska | Nino Kavtaradze | fill (XS) |
| `main#1113` | G1 memoize shell parse + commit prefilter | Nino Kavtaradze | Aino Virtanen | fill (S) |
| `main#1108` | C1 auto-close reusable + host cutover (host = noorinalabs-main) | Nino Kavtaradze | Aino Virtanen | infra |
| `da#489` | carry-forward: enrich leaderboard `name_arabic`→`name_en` (blank names) | TBA at kickoff | — | bug |
| `da#490` | carry-forward: `edge_load_conformance` false-positive + GRADED_BY never-loads | TBA at kickoff | — | tech-debt |

Every story carries ≥1 Opus merge-gate reviewer. Scope + theme are **decided** — execute the
lifecycle (`/wave-scope` → `/wave-kickoff`), do not re-litigate.

### Waves 29–32 (directional — scoped at each `/wave-scope`)

| Wave | Provisional theme | Candidate scope |
|------|-------------------|-----------------|
| **29** | Track C (workflow dedup) + Track G depth | C2–C12 reusable workflows & deploy dedup; G2/G4–G11 hooks/lib DRY & perf |
| **30** | Track D + Track E depth | D2–D10 isnad-graph; E1–E8 user-service (incl. BUG-07/E4 session unification) |
| **31** | Track F depth (measurement-gated) | F1 (A/B pair-set-delta gate), F2/F4–F9 pipeline runtime & memory; Track H (design-system/landing-page) |
| **32** *(final)* | Umbrella close-out + heavy TD floor | remaining Track-0 mediums, epic close-outs, **A/B tranche IFF `main#1099` ratified**, umbrella `main#1089` disposition |

> If the owner ratifies `main#1099` early, the A/B spine (A1 → A2/A3–A6 → B1/B2/B4/B5/B6, then
> B3 post-#978) slots into the earliest wave with capacity — A3 (model reconciliation) wants a
> low-load wave and a domain-aware review, per `CODE_AUDIT.md §12`.

## Tech-debt intake

Most of this phase's content *is* tech-debt/DRY/perf, so the +20% per-wave intake floor
(`feedback_td_intake_20pct_per_wave`, enforced at `/wave-scope` Step 8.5) is over-satisfied by
construction. The **feature-intake ceiling** (owner 2026-07-26) is the live constraint instead:
off-program feature work is triaged in deliberately, not assumed, so features don't crowd out
the program. The **final wave of the phase** treats the +20% as a **floor not a cap** — clear
the remaining debt chunk before phase exit.

## Phase exit (Phase 10 exits here)

- [ ] All 5 end-state criteria hold, each **applied-and-verified at origin** (charter
      `issues.md § End-State Criterion`).
- [ ] All 12 Track-0 defects closed with their named regression tests cited.
- [ ] Epics `main#1093–1098` (Tracks C–H) closed; `main#1090` (Track 0) closed.
- [ ] `main#1099` resolved (ratify / amend / decline) with a written disposition; Tracks
      A/B (`main#1091/1092`) either depleted or formally carried forward.
- [ ] Umbrella `main#1089` closed (or carried forward per criterion 4 with an explicit split).
- [ ] Per-wave TD-intake compliance verified; final wave ran a heavy TD floor.
- [ ] On confirmation, `/plan-phase 11` defines the next phase before any P11 wave kicks off.

## Deferred (not in P10)

- **Tracks A & B execution** while `main#1099` is unresolved — frozen by owner directive; the
  proposal review is a prerequisite, not P10 work. If it stays frozen, the A/B remainder
  carries forward (criterion 3/4).
- **`noorinalabs/.github` dedicated reusable-workflow repo migration** (`main#1124`) — C1
  publishes from `noorinalabs-main` this phase; the dedicated-repo migration is revisited
  alongside A1 in a later phase.
- **Any off-program feature work** beyond what the feature-intake ceiling admits per wave —
  triaged at each `/wave-scope`.
- **The `ontology/structural` / model-ops depth** and other post-audit architecture beyond the
  measured tracks — later phases.

## References

- Audit source of truth (tracks, tasks, baselines, verification methods): `CODE_AUDIT.md`
  (§3 Track 0, §4 Track A / decision, §5 Track B, §6 Track C, §7 D, §8 E, §9 F, §10 G, §11 H,
  §12 sequencing/deps/risks, §13 consolidated task index)
- Program on GitHub: umbrella `main#1089`; track epics `main#1090–1098`; A1 decision `main#1099`;
  C1 dedicated-repo follow-up `main#1124`
- Owner decisions + wave-28 settled scope + pickup steps: `.claude/memory/session_handoff.md`
  (2026-07-26)
- TD-intake policy: `feedback_td_intake_20pct_per_wave`; `/wave-scope` Step 8.5
- Prior phase for format + carry-forward precedent: `.claude/team/phases/phase-8.md`
