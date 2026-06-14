# Historical Timeline / Date Data — Design Note

**Status:** Research / design for owner decision (not implementation)
**Author:** TimelineResearch (noorinalabs session team)
**Date:** 2026-06-14
**Scope:** How to source, normalize, store, and relate narrator life-dates and
era data to narrators and hadith in the isnad-graph platform.

---

## 0. What exists today (verified against the repos, not assumed)

The platform already has a **partial temporal skeleton**. The gap is not "build
from zero" — it is "populate, formalize uncertainty, and wire validation."

### Data-acquisition (`noorinalabs-data-acquisition`)

| Artifact | File | What it has |
|---|---|---|
| `Narrator` model | `src/models/narrator.py` | `birth_year_ah: int \| None`, `death_year_ah: int \| None`, `generation: NarratorGeneration` (required), `tabaqat_class: str \| None`, `birth_location_id` / `death_location_id` |
| `NarratorGeneration` enum | `src/models/enums.py` | `sahabi, tabii, taba_tabii, atba_taba_tabiin, later, unknown` |
| `HistoricalEvent` / `Location` | `src/models/historical.py` | Event: `year_start_ah`, `year_end_ah`, `year_start_ce`, `year_end_ce`, `event_type` enum, `caliphate`, `region`, `source_url`. Location: `lat`, `lon`, `political_entity_period: dict[str,str]` (e.g. `{'622-661': 'Rashidun'}`) |
| Canonical staging schema | `src/resolve/schemas.py` (`NARRATORS_CANONICAL_SCHEMA`) | carries `birth_year_ah`/`death_year_ah` (int32, nullable), `generation` (string), `source_ids: list[str]`, `confidence: float32`, `external_id`, `mention_count` |
| Temporal disambiguation filter | `src/resolve/disambiguate.py` (`_temporal_filter`) | Soft teacher↔student plausibility: keeps a candidate if `abs(death_year - adjacent_death_year)` is within **15–80 years**; **passes through** when dates are missing |
| Edge period fields | `src/models/edges.py` | `StudiedUnder.period_ah: str \| None` (free-text), `BasedIn.period_ah`, `ActiveDuring(narrator_id, event_id, role?, affiliation?)` |

### Isnad-graph (`noorinalabs-isnad-graph`)

| Artifact | File | What it has |
|---|---|---|
| Historical overlay enricher | `src/enrich/historical.py` | Loads `HistoricalEvent` nodes from curated YAML; computes `ACTIVE_DURING` edges by **lifespan overlap** (pure, DB-free `compute_active_during`). `DEFAULT_ASSUMED_LIFESPAN_AH = 80`, `MAX_NARRATOR_LIFETIME_AH = 120`. `_active_window` already encodes the **death-attested / birth-estimated** asymmetry: death-only → `[death-80, death]`; birth-only → `[birth, birth+80]` |
| Curated events | `data/curated/historical_events.yaml` | ~13 events (Rashidun, fitnas, Umayyad/Abbasid transitions, Karbala, …) with AH+CE bounds, hand-entered |
| Timeline API | `src/api/routes/timeline.py` | `GET /timeline` (events + `narrator_count` via `ACTIVE_DURING`, paginated, year-filtered) and `GET /timeline/range` (min/max `year_ah`) |
| Frontend | `frontend/src/pages/TimelinePage.tsx` | d3 timeline rendering **collection compilation years** + historical events |
| Graph property bridge | `event_to_graph_props` in `enrich/historical.py` | Single mapping from model field names (`name_en`/`year_start_ah`/`type`) to graph/API names (`name`/`year_ah`/`event_type`). **One place to change** if API property names change |

### The gaps (what is NOT there)

1. **Dates are essentially unpopulated.** `src/parse/narrator_extraction.py` does
   **not** extract birth/death/generation; no Itqan/rijāl date-parsing exists on
   the inspected branch. The model fields and staging columns exist but are fed
   `None` in practice. So `ACTIVE_DURING`/`/timeline` work mechanically but have
   almost no narrator coverage today.
2. **No uncertainty model.** Dates are bare `int` AH years. No representation for
   ranges, "died after X", "circa", "lived ~80 years", or "only ṭabaqa known."
3. **No calendar normalization.** Narrator nodes carry only AH; CE exists only on
   curated events and was hand-entered. No AH↔CE conversion library in deps.
4. **No isnad chronological validation surface.** The 15–80yr gap heuristic is
   buried in disambiguation as a soft filter; there is no endpoint/query that
   flags chronologically **impossible** `TRANSMITTED_TO` edges as a data-quality
   or authenticity signal.
5. **No ṭabaqa-layering query/endpoint.** `generation`/`tabaqat_class` exist as
   fields but are not used to layer isnad trees or order timelines.

**Design principle:** extend the existing skeleton, do not replace it. The
`_active_window` death-asymmetry, `event_to_graph_props` bridge, and the
`MERGE`-bare-edge null-property discipline (main#139 lesson) are all correct and
should be preserved.

---

## 1. SOURCING

### Where narrator life-dates come from

Death-dates (`wafāt`) are the spine of the rijāl/ṭabaqāt genre and are recorded
far more reliably than birth-dates. Realistic sources, in rough order of
yield/effort:

| Source | Type | Realistic yield | Licensing posture |
|---|---|---|---|
| **Itqan dataset** (already accepted, da#92a) | structured rijāl/biographical | Primary near-term source; rijāl DBs typically carry `wafāt` for the bulk of canonical narrators | Proceed — owner already decided (`[[project_itqan_license_proceed]]`): non-profit, facts re-expressed in our own schema, cleanly removable via provenance |
| **Taqrīb al-Tahdhīb** (Ibn Ḥajar) | ṭabaqāt digest | High — one-line entries with ṭabaqa + death year for ~8k Tahdhīb narrators; the single best structured fit | Classical text (public domain); digital editions vary — prefer a facts-extraction posture identical to Itqan |
| **Tahdhīb al-Kamāl** (al-Mizzī), **Siyar Aʿlām al-Nubalāʾ** (al-Dhahabī) | full ṭabaqāt/biographical | Medium — richer prose, lower structured-extraction yield; good for high-value/disputed narrators | Classical (public domain) |
| **Kaggle / open narrator datasets** | structured | Variable quality; useful as a cross-check / gap-filler, not authority | Check per-dataset license |
| **Generation (ṭabaqa) layering** | derived proxy | ~Universal — every narrator has a `generation`; can bound dates even when no year is attested | Derived, no licensing |

### Realistic field coverage (planning estimate, to validate empirically)

For the corrected ~canonical narrator set (post-segmentation):

- **`generation` / ṭabaqa:** ~90–100% (it is the cheapest, most universal signal
  and the disambiguator already needs it).
- **`death_year_ah`:** plausibly ~50–80% from Taqrīb + Itqan for the *canonical*
  rijāl set; much lower in the long tail of obscure narrators.
- **`birth_year_ah`:** ~10–25% — birth is genuinely rare in the sources. Design
  must treat birth as the exception, death as the rule (the existing
  `_active_window` already does).
- **`floruit` / "active circa":** derivable for many via ṭabaqa midpoint when no
  year is attested.

**Recommendation:** Treat **Taqrīb al-Tahdhīb + Itqan as the two primary
date sources**, with ṭabaqa as the universal fallback that bounds an estimated
window. Tag every date with its source corpus and a precision/confidence enum
(see §2) so a curated/derived date is never confused with an attested one.

---

## 2. NORMALIZATION

### AH ↔ CE conversion

Use a **tabular/arithmetic** Hijri calendar (the standard astronomical-tabular
algorithm), not observational. At year granularity, observational variance
(±1 day on month start) is irrelevant; we only ever convert *years*.

- **Recommended library:** `convertdate` (Hijri ↔ Gregorian, pure-Python, MIT,
  already a common transitive dep) or `hijri-converter`/`ummalqura` if a
  Saudi-tabular variant is preferred. Pin it in data-acquisition deps.
- **Conversion formula sanity anchor:** `CE ≈ AH + 622 − (AH/33)` (the ~3% drift
  from the shorter lunar year). Use the library, not the formula, but keep the
  formula as a test oracle.
- **Where conversion lives:** a single helper in
  `src/utils/hijri.py` (data-acquisition), e.g. `ah_to_ce(year_ah) -> int` and a
  range variant. Compute CE **once at resolve time** and store both, so the API
  and frontend never convert. This mirrors how `historical_events.yaml` already
  carries both AH and CE.

### Representing pervasive uncertainty

Bare `int` years cannot express the real data. Recommended representation —
**bounds + precision + calendar-of-record**, attached per date (birth and death
modeled symmetrically):

```
death_year_ah_earliest: int | None   # lower bound (inclusive)
death_year_ah_latest:   int | None   # upper bound (inclusive)
death_year_ah:          int | None   # point estimate / "best single value"
death_date_precision:   DatePrecision
death_date_source:      str | None   # source corpus / citation id
```

`DatePrecision` enum (new):

| value | meaning |
|---|---|
| `exact` | single attested year (`earliest == latest == point`) |
| `range` | attested bounds, e.g. "between 130 and 135" |
| `circa` | "~X" — point ± small window |
| `after` | "died after X" → `earliest = X`, `latest = None` |
| `before` | "died before X" → `latest = X`, `earliest = None` |
| `tabaqa_estimate` | no year attested; window derived from ṭabaqa |
| `unknown` | nothing |

The **point estimate** is what the existing `birth_year_ah`/`death_year_ah`
fields already are — so we keep them for backward compatibility and *add* the
`_earliest`/`_latest`/`_precision` siblings. `_active_window` in
`enrich/historical.py` gets upgraded to consume the bounds when present and fall
back to its current 80-year-span estimate otherwise (no behavior change when
bounds are absent).

**Death-attested asymmetry:** keep it. Birth precision will usually be
`tabaqa_estimate`/`unknown`; death will usually be `exact`/`circa`. The active
window for plausibility checks (§4) should be **death-anchored**:
`[death − assumed_lifespan, death]` widened by precision bounds.

**Confidence vs precision:** these are orthogonal. `precision` = how tightly the
*source* dates the event; `confidence` (already a staging column) = how sure we
are the *date attaches to this canonical narrator* (disambiguation strength).
Keep both.

---

## 3. STORAGE

### Options considered

**(a) Flat properties on `Narrator`.** Add `death_year_ah_earliest/latest`,
`death_date_precision`, CE mirrors, `floruit_year_ah`, `region` directly on the
node. Pro: trivial queries, matches current model, fast range scans, no joins.
Con: a narrator with multiple conflicting source-dates can't keep provenance per
date.

**(b) Reified temporal/`DateAssertion` nodes.** `(Narrator)-[:HAS_DATE]->(DateAssertion {kind, earliest, latest, precision, source})`.
Pro: full provenance, multiple competing assertions, audit trail. Con: heavy —
every plausibility query becomes a multi-hop traversal; overkill given dates are
1–2 per narrator and we already have a provenance idiom (`source_ids`).

**(c) Hybrid.** Flat **resolved** properties on `Narrator` (the single
best-estimate the pipeline picked) **plus** provenance retained upstream in the
PyArrow staging layer (which already has `source_ids`/`confidence`), and a
reified `Era`/`HistoricalEvent` layer (already exists) for the period dimension.

### Recommendation: **(c) Hybrid** — flat on the node, provenance in staging, eras reified

Rationale: the graph is read-optimized for traversal and visualization; flat
year properties keep `_active_window`, `/timeline`, and chronological-validation
queries cheap. Multi-source reconciliation is a **resolve-stage** concern
(PyArrow, where `source_ids`/`confidence` already live and where
`narrators_canonical` is produced) — not a graph concern. The period/era
dimension is genuinely a separate entity and is *already* reified as
`HistoricalEvent`; we keep that and optionally add lightweight `Era`/ṭabaqa
nodes only if §4(d) layering needs them.

### Concrete graph model

`Narrator` node gains (all nullable, additive):

```
birth_year_ah_earliest, birth_year_ah_latest, birth_year_ce, birth_date_precision
death_year_ah_earliest, death_year_ah_latest, death_year_ce, death_date_precision
floruit_year_ah        # ṭabaqa-derived midpoint when no year attested
region                 # coarse geographic anchor (string; promote to Location FK later)
```

Keep existing `birth_year_ah` / `death_year_ah` as the **point estimate**;
keep `generation` and `tabaqat_class`.

### Pipeline changes (data-acquisition)

1. **`src/models/narrator.py`** — add the bounds/precision/CE fields above +
   `DatePrecision` enum in `src/models/enums.py`.
2. **`src/resolve/schemas.py`** — extend `NARRATORS_CANONICAL_SCHEMA` with the
   new columns (int32 + string).
3. **Date extraction** — new `src/parse/narrator_dates.py` (or extend the Itqan
   adapter / `bio_promote`) that parses `wafāt`/birth/ṭabaqa from the source and
   emits `(value, earliest, latest, precision, source)`. This is where Arabic
   numeral / phrase parsing (`توفي سنة ١٥٠`, "died after 200") lives — reuse
   `src/utils/arabic.py`.
4. **Reconciliation** — in `src/resolve/disambiguate.py` / `bio_promote`, when
   multiple sources date the same canonical id, pick the highest-confidence /
   tightest-precision value, widen bounds to cover disagreement, and record all
   contributing `source_ids`. Respect the existing **disambiguate-before-promote
   ordering** (`[[project_narrators_canonical_two_producers_ordering]]`) so
   bio-derived dates don't clobber disambiguated ones.
5. **CE computation** — `src/utils/hijri.py`, applied once at resolve.
6. **Provenance** — every date carries its source corpus consistent with the
   existing `source_ids` + uuid5 canonical-id conventions; a curated/derived date
   is `tabaqa_estimate` precision and tagged so it is cleanly removable (same
   removability posture as Itqan).

### Loader changes (isnad-graph)

- `src/enrich/historical.py` `_active_window` consumes bounds when present.
- Node loader writes the new properties (additive; existing `MERGE`-on-`id` +
  `SET +=` pattern already tolerates new keys — preserve the
  null-property-in-MERGE discipline).

---

## 4. RELATING TO HADITH (the payoffs)

### (a) Temporal plausibility validation of isnad chains — highest value

A teacher must predate/overlap a student. Today this exists only as a *soft
disambiguation filter*. Promote it to a **first-class data-quality / authenticity
signal**:

- **Rule:** for each `(:Narrator)-[t:TRANSMITTED_TO]->(:Narrator)` (teacher→student),
  flag the edge when their **active windows cannot overlap** — i.e. the teacher's
  latest plausible activity is before the student's earliest plausible activity,
  using death-anchored windows widened by precision bounds. Tier the verdict:
  `impossible` (windows provably disjoint with `exact` dates), `implausible`
  (disjoint only under estimates), `unknown` (insufficient dates).
- **Query/endpoint:** `GET /validate/chains` (or `/data-quality/temporal`)
  returning flagged edges with both narrators' windows + a verdict tier. A
  per-hadith variant validates one isnad. This naturally lands next to the
  existing admin reports (`src/api/routes/admin/reports.py` already queries
  `TRANSMITTED_TO` for orphans) and analytics.
- **Payoff:** surfaces both (i) residual **segmentation/disambiguation errors**
  (the known ~80% blob issue will produce many impossibilities — a useful
  regression signal as that fix lands) and (ii) genuine **isnad criticism**
  signals (munqaṭiʿ / mursal-like breaks).

### (b) Timeline / era visualization (frontend)

`TimelinePage.tsx` already renders collection years + events. Extend with:
- A **narrator lifespan lane** (Gantt-style bars from active-window bounds,
  shaded by `precision` so estimates read as fuzzy).
- ṭabaqa **swimlanes** (group narrators by `generation`).
- Backend: `GET /timeline/narrators?start&end` returning narrators with resolved
  windows + precision, mirroring the existing `/timeline` shape.

### (c) Dating a hadith's terminus via its chain

A hadith's earliest plausible compilation is bounded by its **latest narrator's
death** (the collector) and its transmission by the chain's date span. Endpoint:
`GET /hadith/{id}/dating` → `{terminus_ante_quem, chain_span_ah, confidence}`
computed from the chain's narrator windows + the collection's
`compilation_year_ah` (already on `Collection`). Useful for "show me hadith whose
chains resolve to the 2nd century."

### (d) ṭabaqa-based generation layering of isnad trees

Use `generation`/`tabaqat_class` to **layer** the graph-explorer isnad tree (sahabi
at top, descending). This is largely a graph-query ordering + frontend layout
change over the existing `src/api/routes/graph.py` neighborhood/tree queries; no
new nodes strictly required, though a small reified `Era`/ṭabaqa lookup could
back a legend. Pairs well with (a): impossible edges that *cross* generations the
wrong way (a sahabi narrating *from* a tabaʿ-tābiʿī) are the clearest red flags.

---

## Recommended approach — summary

- **Sourcing:** Taqrīb al-Tahdhīb + Itqan as primary date sources (death-anchored),
  ṭabaqa/`generation` as the universal fallback window; facts re-expressed in our
  schema with per-date provenance, removable like Itqan.
- **Normalization:** `convertdate`-style tabular AH↔CE computed once at resolve;
  uncertainty modeled as `earliest/latest` bounds + a `DatePrecision` enum +
  point estimate, with death modeled as the attested norm and birth as the
  exception.
- **Storage:** Hybrid — flat resolved date properties on `Narrator`
  (additive to the existing fields), multi-source reconciliation kept in the
  PyArrow resolve layer (`source_ids`/`confidence`), eras stay reified as the
  existing `HistoricalEvent` nodes.
- **Relating:** Promote the temporal-overlap check from a soft disambiguation
  filter to a first-class `/validate/chains` data-quality + authenticity endpoint;
  add narrator-lifespan/ṭabaqa lanes to `TimelinePage`; add hadith-dating and
  ṭabaqa-layering endpoints.

---

## Proposed GitHub issues (sequenced; do NOT create yet)

**Foundation (parallelizable):**

1. **da** — *Add `DatePrecision` enum + bounds/CE date fields to `Narrator` model* — extend `src/models/narrator.py` + `src/models/enums.py` with `{birth,death}_year_ah_{earliest,latest}`, `_ce`, `_precision`, `floruit_year_ah`, `region`.
2. **da** — *Extend `NARRATORS_CANONICAL_SCHEMA` for date bounds/precision* — mirror (1) in `src/resolve/schemas.py`.
3. **da** — *Add `src/utils/hijri.py` AH↔CE conversion + pin `convertdate`* — pure helper + tests against the `AH+622−AH/33` oracle.

**Sourcing (depends on 1–3):**

4. **da** — *Parse narrator death/birth/ṭabaqa dates from Itqan rijāl source* — new `src/parse/narrator_dates.py`, Arabic numeral/phrase parsing via `src/utils/arabic.py`, emit value+bounds+precision+source.
5. **da** — *Reconcile multi-source narrator dates in resolve (disambiguate-before-promote)* — pick best/tightest, widen bounds on disagreement, retain `source_ids`; honor existing producer ordering.
6. **da** — *ṭabaqa→date-window fallback* — derive `floruit`/estimated bounds from `generation` when no year attested (`precision=tabaqa_estimate`).

**Loader/graph (depends on 1, 4–6):**

7. **ig** — *Write new date properties in node loader; upgrade `_active_window` to consume bounds* — additive, preserve null-property-in-MERGE discipline.

**Payoffs (parallelizable after 7):**

8. **ig** — *`GET /validate/chains` temporal-plausibility endpoint* — flag impossible/implausible `TRANSMITTED_TO` edges with tiered verdicts + both windows.
9. **ig** — *`GET /timeline/narrators` + narrator-lifespan & ṭabaqa lanes in `TimelinePage.tsx`* — Gantt bars shaded by precision.
10. **ig** — *`GET /hadith/{id}/dating` terminus + chain-span endpoint* — uses chain windows + `Collection.compilation_year_ah`.
11. **ig** — *ṭabaqa-based generation layering in graph explorer isnad tree* — query ordering + frontend layout over `src/api/routes/graph.py`.

**Cross-repo coordination:** a meta-issue in `noorinalabs-main` tying da#(1–6) →
ig#(7–11), sequenced backend-before-frontend per charter cross-repo rules.

---

## Open questions for the owner

1. **Sourcing licensing/effort for Taqrīb al-Tahdhīb:** confirm we extend the
   accepted Itqan "facts-in-our-own-schema, cleanly removable" posture to a
   Taqrīb/ṭabaqāt extraction, and whether a usable structured digital edition is
   in reach — or whether near-term coverage should rely on **Itqan alone** with
   ṭabaqa fallback.
2. **How aggressive should chronological validation be?** Should `impossible`
   `TRANSMITTED_TO` edges be (a) merely flagged for review, (b) surfaced as an
   authenticity signal in the UI, or (c) auto-quarantined as data-quality defects?
   This interacts with the in-flight segmentation fix, which will initially
   produce many false impossibilities.
3. **Estimate posture:** is a ṭabaqa-derived `tabaqa_estimate` window acceptable
   to *display* (clearly marked as estimated) in the public timeline, or should
   estimated dates be computed-but-hidden, with only attested dates shown to users?
