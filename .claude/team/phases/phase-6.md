---
name: Phase 6 plan — Claude Efficiency
description: Phase definition, end-state criteria, exit gate, wave plan
phase: 6
status: exited
created: 2026-06-20
last_updated: 2026-06-25
---

# Phase 6 — Claude Efficiency

## Theme

A **framework phase**: the "product" under improvement is the `.claude/` machinery and how Claude/the simulated team operate — **not** the hadith platform. Phase 5 cut over real data to prod; Phase 7 will make that data demo-grade. Phase 6 sits between them to pay down the *operational* cost that accreted across Phases 1–5: an oversized memory corpus, prose rules that drifted because nothing enforced them, a 28-persona roster whose value-vs-overhead was never re-examined, and a three-role ontology stack that may be replaceable by a simpler graph/LLM-doc approach.

Owner directive (2026-06-19): audit the interaction model — **tighten memories, bias toward code over `.md`/memories, revisit the persona model, explore the Google LLM-doc format + graphify (potentially dropping the ontology stack), and absorb tech-debt + Claude fixes including non-phase-tied ones.**

Owner directive (2026-06-20, `/plan-phase 6`): the two architectural revisits (persona model, ontology stack) are **spike-and-decide, not pre-commit** — Phase 6 produces evaluations and owner decisions, and does not commit to ripping either subsystem out within the phase. Any teardown/replacement follows the recorded decision in a later phase.

> **Backlog note:** unlike product phases, the project board (a product/data backlog) is **not** the P6 candidate pool — most P6 work is net-new framework issues created at plan time. The board's product/data backlog belongs to Phase 7.

## End-state criteria — Phase 6 exits when ALL hold

| # | Criterion | Tracker | Nature |
|---|-----------|---------|--------|
| 1 | **Memory leanness** — memory corpus audited (stale retired, duplicates merged); MEMORY.md size/count budget enforced by a hook | noorinalabs-main#TBD | mostly new |
| 2 | **Code-over-prose** — a pass converting deterministic-able charter prose into hooks/lib checks; remaining prose rules documented as intentionally-prose with rationale | noorinalabs-main#TBD | new |
| 3 | **Persona-model decision** — the simulated roster (≈28 personas) evaluated for value-vs-overhead; owner decision recorded (keep / slim / restructure) | noorinalabs-main#TBD | spike + decision |
| 4 | **Ontology-vs-graphify decision** — spike the Google LLM-doc format + graph approach against the current 3-role ontology stack; owner decision recorded (keep / replace / hybrid) | noorinalabs-main#TBD | spike + decision |
| 5 | **Framework debt burn-down** — non-phase-tied framework tech-debt + the P5W5 retro process changes absorbed | noorinalabs-main#TBD | existing + new |

(Tracker numbers filled in at issue-creation; the W1 meta-issue links them.)

## Wave plan (proposed at /plan-phase 6, owner-approved 2026-06-20)

| Wave | Theme | Scope summary | Serves |
|------|-------|---------------|--------|
| **W1** | **Memory & code-over-prose** | The core efficiency thesis: memory audit + consolidation (retire stale, merge duplicates) + a MEMORY.md size/count-budget hook; a charter-prose→code conversion pass (identify prose rules that can be deterministic hooks/lib checks; document what stays prose). + framework TD intake (main#684 cspell parity, #706 cspell regex, #704 classifier nits). | #1, #2, #5 |
| **W2** | **Architectural revisits** | Spike-and-decide: persona-model evaluation (value-vs-overhead of the 28-persona roster → owner decision) + ontology-vs-graphify spike (Google LLM-doc + graph approach vs the 3-role stack → owner decision). + P5W5 retro process changes: annunaki exit-0 precision pass, wrap-on-last-merge trigger. | #3, #4, #5 |
| **W3** (global 16) | **Framework / gate hardening** | Absorb remaining framework/Claude tech-debt: main#718 README hook-install, #705 wave_key_reset CLI test, #672 reviewer-brief producer-parity, #663 gh-parser invariant, #810 phase-agnostic wave-label scheme, #744 validators→child CI, #745 liveness/throttle mechanization, #816/#817/#822 toolchain pre-push/ff fixes + whatever W1/W2 audits surface. **Heavy TD floor.** | #5 |
| **W4** (global 17, FINAL) | **Architectural execution + phase exit** | Execute the recorded architectural decisions: #819 persona-model **Option B** (governed headcount + slim/self-improving cards + mechanical trust scoring) + #820 ontology **C×T2** (per-language derivability re-measure → tooling bake-off → distributed structural index + central semantic overlay). Close #725/#726 epics; phase-exit verification of all 5 criteria. | #1, #2, #3, #4, #5 |

Wave themes are confirmed (not re-chosen) at each `/wave-scope`; scope reconciliation may move issues between waves.

> **Plan revision (owner, 2026-06-22):** the original single final "W3 — framework burn-down + phase exit" was split into **W3 (global 16) framework/gate hardening** and a new **W4 (global 17) architectural execution** (#819/#820 carry the criteria #3/#4 *execution* — the *decisions* are already recorded and #727/#728 closed). Phase exit moves from W3 to W4. Later-wave work advanced by +1.

## Tech-debt intake (standing policy)

Every wave takes its **+20%** TD intake (`/wave-scope` Step 8.5) — `ceil(20% of feature/bug/security scope)`, all available if fewer. The pooled TD ratio is **informational only** (cumulative-ratio gate superseded 2026-06-09). Because Phase 6 *is itself* a framework/quality phase, much of its "feature" content is indistinguishable from tech-debt; the intake policy still applies to any net-new tooling work.

On the **framework-hardening wave (W3, global 16)** the +20% becomes a **floor, not a cap** (owner 2026-06-16 standing rule): deliberately pull in a large chunk of framework debt to clear, sized by the owner at `/wave-scope`. The **final wave (W4, global 17)** is the architectural-execution + phase-exit wave.

## Criterion #4 — Ontology-vs-graphify decision — **DECIDED: C × T2 (owner, 2026-06-22)**

Spike complete (main#728, P6W2): [`.claude/team/spikes/p6w2-ontology-vs-graphify.md`](../spikes/p6w2-ontology-vs-graphify.md).

Measured on the meta-repo `.claude/` machinery slice (54 modules, 54/54 already docstring'd):
the code-structural layer of the ontology is **100% auto-derivable** by a ~60-LOC generator,
versus **1,347 LOC** of freshness machinery + **1,760 lines** of hand-curated payload +
an 88 KB / 248-file `checksums.json` + a per-edit Hook-15 tax in the current stack.

**Revised forward (owner, 2026-06-22) — the product lives in the child repos.** The spike measured
only the parent's `.claude/` Python; the ontology's real job is to describe the **polyglot product**
(TS/React, Neo4j/Cypher, Terraform/HCL) in the child repos. Two corrections fold in:
- **Topology now a first-class axis.** Today's model is **centralized-in-parent**, and the parent
  hand-curates structural snapshots of child source it **cannot see** (children gitignored) → that is
  the drift source and the `checksums.json` worktree-churn. Alternative: **distribute** the generated
  structural layer into each child repo (built where its source is visible) + keep only a **central
  system overlay** (semantics, cross-repo topology, ADRs) in main + a thin aggregator. Evaluated on the
  owner's four axes (implementation complexity, per-agent token cost, context-locality for implementing
  agents, maintenance cost), distributed wins all four at the cost of a cross-repo aggregation step.
- **Tooling broadened** beyond Google `llms.txt`/NotebookLM: SCIP/LSIF code-intelligence, tree-sitter,
  a Neo4j-backed code graph (dogfoods the stack) for structure; an **Obsidian (user+LLM) vault** or
  markdown for the curated overlay. Survey is non-exhaustive.

**Spike recommendation (revised): C × T2** — **Hybrid representation** (generate structural layer,
hand-curate semantics/intent, soften Hook 15 to advisory) on a **Distributed + system-overlay topology**
(per-child generated index, central overlay, aggregator). **Gated** on a per-language derivability
re-measurement on the actual product repos before any commit (Python's 54/54 docstring rate is unproven
for TS/Cypher/HCL). Pure-Replace rejected (loses the semantic layer); Keep is the do-nothing tax;
Hybrid-on-Centralized (C × T1) leaves the parent generating from unseeable child source, so the drift
survives.

**Owner decision (2026-06-22): C × T2** — representation ☑ **Hybrid**, topology ☑ **Distributed + overlay**.
Tooling is **not** pre-picked: chosen via an isolated-branch **bake-off** comparing candidates (structural:
`llms.txt`+graph / SCIP-LSIF / tree-sitter / Neo4j code graph; overlay: Obsidian vault / markdown /
NotebookLM) on two lenses — agent/Claude token-cost + query behavior, and human knowledge-base usability —
starting on a polyglot repo (isnad-graph) to stress per-language derivability. Per owner 2026-06-20, no
teardown in P6; implementation is a later-phase follow-up whose first tasks are the per-language
derivability re-measurement and the tooling bake-off. Execution tracker: [#820](https://github.com/noorinalabs/noorinalabs-main/issues/820).

> **Revision (owner, 2026-06-23, at `/wave-scope 6 17`):** the "no teardown in P6 / later-phase follow-up"
> deferral above is **superseded** — W17 (global 17) executes #820 **in full, including Task 3**
> (implement the distributed per-repo structural index + central semantic overlay, retire `checksums.json` +
> `/ontology-rebuild` for the structural layer, soften Hook 15 to advisory). Teardown of the current
> ontology stack now happens **within P6** as part of the phase-exit wave, not in a later phase.

## Out of scope for P6 (deferred)

- **All product/data-quality/ML work** — that is **Phase 7** (Data Quality / ML / demo): the 15 issues relabeled `phase-6`→`phase-7` at this plan time (main#673, ig#1039–1043, da#161–166, da#136/139/178), plus the prod data-quality cluster under meta #723 (sanadset orphans, sparse linkage, broken search, narrator pollution), ig#1110/#1111.
- **Streaming pipeline repeatable** (#667) — Phase 7.
- **Actively ripping out the persona or ontology subsystems** — P6 decides; teardown (if chosen) is a later phase.
  **Superseded for the ontology stack (owner, 2026-06-23):** the ontology teardown (#820 Task 3) is pulled **into**
  the P6 phase-exit wave W17 — see the criterion #4 revision note above. The persona-model execution (#819) likewise
  runs in W17 in full (all three Option-B components). Only Option C (persona role-class restructure) remains deferred.

## Architectural-revisit decisions (criteria #3, #4)

The two spike-and-decide criteria record their owner decisions here. A decision is "keep / slim /
restructure" (#3) or "keep / replace / hybrid" (#4); teardown of either subsystem is **deferred to a later
phase** regardless of the decision.

### #3 — Persona-model decision — **DECIDED: B (owner, 2026-06-22)**

- **Spike:** `.claude/team/spikes/p6w2-persona-model-evaluation.md` (Nadia Khoury, P6W2, [#727](https://github.com/noorinalabs/noorinalabs-main/issues/727)).
- **Quantified:** roster is **78 named identities / 70 canonical cards** across 8 rosters — ~2.5× the
  "≈28" the issue assumed (drift, ungoverned); 279/349 on-disk card copies are worktree duplicates.
  Per-spawn persona tax = card-read + per-commit identity plumbing + reviewer-naming (the worktree +
  librarian costs are isolation/ontology costs, not persona costs, and survive any restructuring).
- **Options:** A keep · B slim (governed headcount + budget hook) · C restructure to role-classes.
- **Owner decision (2026-06-22): B**, with two execution components folded in by the owner and now
  proven-out by measurement:
  - **§4a / Finding C — personality bloat → self-improving cards.** 0/12 personality tokens (origin,
    religion, sex, music, hobbies) appear in *any* assessment across the 1,639-line trust matrix + all
    retros — the block is ~⅓ of every card, read on every spawn, referenced by nothing. Slim it out; promote
    the already-present `Tech Preferences (Evolves)` / `Performance History` fields into a structured,
    **retro-fed `Learned Adjustments`** section so personas self-improve on feedback instead of carrying
    static fiction.
  - **§4b / Finding D — inflationary scoring → mechanical, bidirectional metrics + exit path.** Trust matrix
    shows **35 ↑ vs 3 ↓** (~12:1), 33 "Already at max," **139** "None this wave" in Needs-Improvement, 0
    ever rated 1 — everyone ratchets to a ceiling and no one is ever retired for performance. Replace
    narrative self-grading with evidence-anchored deltas (per-engineer mechanical wave metrics),
    decay-toward-neutral, distribution discipline, a forced negative-signal pass, and a
    performance-triggered retirement trigger.
- **Option C (role-classes):** deferred future-phase ADR candidate, only if governed-slim B still shows
  named-individual overhead dominating.
- **Execution:** deferred to a later wave/phase per P6 spike-and-decide; this wave records the decision +
  scope. Follow-up tracker: [#819](https://github.com/noorinalabs/noorinalabs-main/issues/819) (B + §4a
  self-improving cards + §4b mechanical scoring).

### #4 — Ontology-vs-graphify decision — _(spike in progress, [#728](https://github.com/noorinalabs/noorinalabs-main/issues/728))_

## Phase exit gate

Owner runs `/phase-review 6` and verifies the **5 end-state rows** are `Done` (their trackers closed), including the standing per-wave TD-intake compliance. The two decision criteria (#3 persona, #4 ontology) are satisfied by a **recorded owner decision** (keep/slim/restructure; keep/replace/hybrid), not by a teardown. On confirmation, `/plan-phase 7` defines the Data-Quality / ML phase before any P7 wave kicks off.

## References

- `.claude/team/lifecycle.md` — canonical phase/wave/session skill order
- `.claude/team/phases/phase-5.md` — prior phase (EXITED 2026-06-20; cutover delivered, queryability/data-quality carried to P7)
- `cross-repo-status.json` — live counters (`phase_6_*` keys)
- meta #723 — P7 data-quality nucleus (prod loaded-but-quality-broken)
- memory `project_p5w5_prodcutover_p6_dataquality` — roadmap revision provenance
- P5W5 retro (`feedback_log.md`) — process changes feeding W1/W2 (annunaki precision, wrap-on-last-merge)
