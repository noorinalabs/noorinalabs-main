# Spike — Ontology-vs-graphify (P6 end-state #4)

> **Status:** **DECIDED 2026-06-22 — C × T2** (Hybrid representation on a Distributed + system-overlay
> topology). Tooling chosen by an isolated-branch bake-off (see OWNER DECISION). Teardown deferred to a
> later phase per the P6 spike-and-decide directive.
> **Issue:** noorinalabs-main#728 · **Wave:** P6W2 (Architectural revisits) · **Author:** Weronika Zielinska (Platform Architect)
> **Decision nature:** spike-and-decide, NOT pre-commit (owner 2026-06-20). No teardown this phase; teardown follows the recorded decision in a later phase, gated on a per-language derivability re-measurement on the actual product repos (§2a-i, §5).

## 1. The question

Phase 6 criterion #4 asks whether the current **three-role ontology stack** —
Change Tracker (PostToolUse hook → `ontology/checksums.json`), Resolver (`/ontology-rebuild`),
Librarian (`/ontology-librarian`), plus the **Hook 15** consult gate
(`enforce_librarian_consulted`) — should be replaced by a simpler
**Google LLM-doc-format (`llms.txt`) + graphify** approach: auto-derive an LLM-readable
index and a code graph from the source instead of hand-curating YAML kept in sync by a
dirty-tracking state machine.

Owner directive 2026-06-19: "explore Google LLM-doc format + graphify to potentially drop
the ontology stack."

## 2. What was actually spiked

Child product repos are gitignored out of this checkout, so the **representative slice is the
meta-repo's own `.claude/` Python machinery** (`.claude/hooks/` + `.claude/lib/`) — ~19k LOC,
the very subsystem the ontology + memory describe. A ~60-line generator
(`ast`-based, stdlib only) was run over the slice to produce both candidate artifacts:

- an **`llms.txt`-style index** (one curated line per module, from its docstring), and
- a **code graph** (modules as nodes, intra-slice imports as edges, symbols per node).

### Measured results (real run, not estimated)

| Metric | Value |
|--------|-------|
| Modules indexed (nodes) | **54** |
| Intra-slice import edges | **57** |
| Top-level def/class symbols extracted | **418** |
| Modules already carrying a 1-line docstring | **54 / 54 (100%)** |
| Generated graph artifact size | **24 KB** (whole slice) |
| Generator size | **~60 LOC, stdlib `ast` only** |
| Hand-authoring required to produce the index | **0 lines** |

The 100%-docstring result is the load-bearing finding: the index and graph are **fully
auto-derivable from code that already exists**, regenerable on demand, and therefore
**structurally always-fresh** — there is no "dirty" state to track and no human step to
remember.

## 2a. Scope correction — the product lives in the **child repos** (owner, 2026-06-22)

The ontology's real job is to describe **the product**, which lives in the child repos — not the
meta-repo's own `.claude/` machinery the spike slice measured. Two consequences reshape the decision:

**(i) The "100% auto-derivable" headline is parent-only and may not transfer.** The 54/54-docstring,
~60-LOC result ran over `noorinalabs-main/.claude/` Python with stdlib `ast`. The product repos are
**polyglot** — isnad-graph (Python FastAPI + **TypeScript/React** + **Neo4j/Cypher**), user-service
(Python), deploy (**Terraform/HCL** + compose), landing-page + design-system (TS). Python's docstring
rate and an `ast` generator will **not** transfer unchanged: TS needs `ts-morph`/`tsc`, Cypher/HCL/SQL
need their own extractors. Derivability must be **re-measured per language per repo** before any commit.
Treat the number as "proven for the parent slice, **unproven for the product**."

**(ii) Today's topology is already _centralized-in-parent_ — and that is the drift source.** Inventory
(2026-06-21):

| Layer | Where it lives today | How it's maintained |
|-------|---------------------|---------------------|
| System semantics — `domain.yaml`, `services.yaml`, `conventions.md` | `noorinalabs-main/ontology/` | hand-curated |
| Per-child **structural** layer — `ontology/repos/*.yaml` (7 files, 2–17 KB) | `noorinalabs-main/ontology/repos/` | **hand-curated in the parent**, "Updated by /ontology-rebuild" |
| Dirty-tracking — `checksums.json` (266 files) | parent | tracks child source **only when a child is checked out as a sibling/worktree** → accrues stale worktree-path entries |
| Child repos' own `.claude/` (rosters, consult sentinels) | each child repo | present, but **no `ontology/` of their own** |

The `repos/*.yaml` are **hand-maintained snapshots of source the parent cannot see** (children are
gitignored out of the parent checkout). That is exactly why they drift, why `checksums.json` accumulates
cross-repo **worktree-path churn** (the 73-entry stale-path prune at this wave's wrapup), and why a
child-repo agent editing the product has **no local ontology context** at all. The centralized model
fails precisely at the boundary where the code it describes is invisible to the place that curates it.

## 3. Comparison on the four axes (issue #728 acceptance)

| Axis | Current 3-role stack | `llms.txt` + graphify (spiked) |
|------|----------------------|-------------------------------|
| **Maintenance cost** | **1,347 LOC** of machinery (tracker 232 + Hook-15 475 + enforce_ontology_context 151 + sentinel helper + 2 skills) **plus 1,760 lines** of hand-curated YAML/MD payload that the Resolver must keep aligned. `checksums.json` is **88 KB** tracking **248 files**; **49** `ontology: rebuild` commits in history. | **~60 LOC** generator, **0** hand-authored payload for the code-derived layer. No checksums file, no resolver runs. |
| **Freshness / staleness** | *Eventual consistency.* Files go "dirty" (`last_tracked != last_resolved`) and stay stale until a human runs `/ontology-rebuild`. The whole tracker exists to **measure** drift; drift still happens. | *Structural freshness.* Regenerate = current, by construction. No drift window, no staleness metric needed. |
| **Query usefulness** | **High for semantics it captures by hand**: domain entities (`narrator`, `id_prefix: "nar:"`), service topology + integration intent, conventions/ADRs ("why"). These are **not** derivable from code structure. | **High for structure**: "what calls this", "what's in this module", import blast-radius, symbol lookup — the questions a graph answers natively and the curated YAML answers poorly. **Weak on domain semantics and intent** — a graph cannot invent the *meaning* of `narrator` or *why* a convention exists. |
| **Hook-15 friction** | A hard PreToolUse gate on **every** Edit/Write org-wide, justified by "freshness depends on a human consulting first." Has needed repeated fixes (transcript-flush race #169, cwd-keyed sentinel fallback, worktree-cwd edge cases). It is a standing tax on every edit. | If freshness is structural, the **premise for a blocking consult gate largely disappears** — consultation becomes "read the generated index," needing no per-edit enforcement. Friction → ~0. |

### What graphify genuinely **cannot** replace

The code graph and `llms.txt` index reproduce the **structural / repos-`*.yaml`** layer for free,
but they do **not** reproduce:

- **Domain semantics** — `domain.yaml` entity meanings, `id_prefix` conventions, cross-repo
  relationships (the hadith/narrator model). Hand-authored knowledge, low churn.
- **Service topology & integration intent** — `services.yaml` (who calls whom and *why*),
  prod/stg asymmetries.
- **The "why" prose** — `conventions.md`, ADRs. Rationale is not in the code.

These three are real, valuable, and **not** the part that rots — they change rarely and are not
mechanically derivable. The part that rots (and drives the 1,347 LOC of upkeep machinery) is the
**code-structural layer**, which is exactly the part graphify auto-derives.

## 3a. Where should the ontology live? — topology, on the owner's four axes (2026-06-22)

The representation question (keep / generate / hybrid, §4) is **orthogonal** to a topology question the
original spike never asked: should the ontology be **centralized in `noorinalabs-main`** (today's model),
or **distributed to each child repo with a thin system-level overlay on top**?

| Axis (owner-specified) | **Centralized** — all ontology in main (today) | **Distributed + system overlay** — per-repo structural ontology in each child; semantic/topology overlay in main |
|------|------|------|
| **Implementation complexity** | Cheap to *describe*, costly to keep *correct*: the parent must derive structure from N gitignored repos — done by hand today. | Medium: one shared generator runs in each repo's **own** CI/pre-commit (source visible, language-native); parent keeps only the overlay + a thin aggregator. More parts, each simple, each independently shippable. |
| **Token cost (per agent)** | A child-repo agent loads org-wide payload (~1,760 lines) to find its slice — most irrelevant to its repo. | A child agent loads **only its repo's scoped, generated index**; the overlay is pulled **only** for cross-repo work → materially lower per-spawn context. |
| **Right context for the implementing agent** | Context is **remote** from the code: the agent edits child source while the describing ontology sits in another repo, often stale. | Context is **co-located** with the code each agent edits and auto-fresh — the strongest fit for "appropriate context when implementing." |
| **Maintenance / update cost** | Hand-curated structural snapshots drift continuously; `checksums.json` carries cross-repo worktree-path churn. | Structural layer **auto-regenerates per repo where the source lives** → no drift, no cross-repo checksum churn. Only the small, low-churn semantic overlay is hand-maintained centrally. |
| **Cross-repo questions** | Native — one tree. | Needs an **aggregation step**: the parent overlay references each child's generated index (pull-on-demand or a periodic roll-up). This is the main cost of distributing. |

**Read:** centralized is "one place to look," but that single place is structurally **blind to the
product source**, which is the root cause of the very drift the 3-role stack exists to chase.
Distributing the **structural** layer to where the code actually lives — and keeping only the
**cross-repo semantic overlay** central — improves all four owner axes, at the cost of an aggregation
step for cross-repo queries.

## 3b. Tooling/representation options — broadened beyond Google `llms.txt` (2026-06-22)

The approach need not be Google's format or NotebookLM. Candidates, by layer:

**Structural layer (machine-generated, per repo):**
- **Per-repo `llms.txt` + code graph** (the spiked approach) — stdlib-cheap for Python; needs
  language-native extractors for TS/HCL/Cypher.
- **SCIP / LSIF code-intelligence indexes** (Sourcegraph's formats; multi-language) — richer
  defs/refs/callers than a hand-rolled graph, standardized and tool-supported across the polyglot stack.
- **`ctags` / tree-sitter symbol indexes** — lightweight, polyglot, fast; a low-ceiling fallback.
- **A real graph DB** — the platform already runs **Neo4j**; the code graph could live there and be
  queried in Cypher (dogfoods the product's own stack).

**Semantic / "why" overlay (human + LLM co-authored, low-churn):**
- **Obsidian-backed vault (user + LLM)** — markdown with `[[backlinks]]`, a strong fit for the curated
  domain/semantics/ADR layer: a human and an LLM co-edit, links express the cross-repo relationships
  `domain.yaml` encodes today, and it stays plain files in git. Good **authoring surface** for the overlay.
- **Google NotebookLM** — good for read-only Q&A over the curated corpus; weaker as a git-native
  source-of-truth authoring surface (hosted).
- **MkDocs / Docusaurus generated site** — if the overlay should also be human-browsable.

These compose. A concrete instantiation of "distributed + system overlay" that uses **neither** hand-rolled
YAML nor Google's format: **SCIP per child repo (structure) + an Obsidian/markdown overlay in the parent
(semantics)**. The survey is not exhaustive — other code-intelligence and knowledge-base tools exist and
should be weighed at implementation time.

## 4. Options & migration cost

### Option A — Keep (status quo)
- **Cost:** none now; ongoing 1,347-LOC machinery upkeep + the per-edit Hook-15 tax + recurring
  Hook-15 plumbing bugs.
- **When right:** if the structural YAML layer is considered high-value enough to justify hand-curation,
  or if churn is too low to bother changing.

### Option B — Replace (rip out the stack, go pure `llms.txt` + graph)
- **Migration:** delete tracker/resolver/librarian/Hook-15 + `checksums.json`; ship the generator +
  a regenerate-on-demand entry point; teach skills to read the generated index.
- **Cost:** medium (mostly deletion + a small generator already prototyped).
- **Risk:** **loses the domain/semantic/intent layer** that the graph cannot derive. Net regression
  on the "why" questions. **Not recommended as-is.**

### Option C — Hybrid (RECOMMENDED) — auto-derive structure, hand-curate semantics, drop the gate
- **Keep, as plain low-churn markdown/YAML (no dirty-tracking machinery):**
  `domain.yaml` semantics, `services.yaml` topology+intent, `conventions.md`/ADRs.
- **Replace with generated artifacts:** the `repos/*.yaml` structural layer + `api_surface` → an
  `llms.txt` index + code graph, regenerated on demand. Retire `checksums.json` and `/ontology-rebuild`
  for that layer.
- **Soften Hook 15:** since freshness becomes structural, downgrade the **blocking** consult gate to
  an advisory pointer (or scope it to edits that touch the hand-curated semantic layer). Removes the
  org-wide per-edit tax and the recurring transcript/cwd plumbing bugs.
- **Migration cost:** **low–medium**, and **incrementally shippable** — generator first, retire the
  structural-layer tracking second, soften Hook 15 last, each independently revertible.

### Topology axis (cross-cuts A/B/C) — added 2026-06-22

The representation choice above is **independent** of where the ontology lives (§3a). Two topologies:

- **T1 — Centralized** (today): all layers in `noorinalabs-main`. Keeps cross-repo queries native, but
  the parent stays blind to child source → structural drift + checksum worktree-churn persist **even
  under Hybrid**, because the parent still can't see the code it's generating *from*.
- **T2 — Distributed + system overlay** (recommended forward): each child repo owns its **generated
  structural index** (built in its own CI/pre-commit, where its source is visible and language-native);
  `noorinalabs-main` keeps only the **hand-curated system overlay** (`domain.yaml` semantics,
  `services.yaml` cross-repo topology/intent, `conventions.md`/ADRs) plus a thin aggregator that pulls
  each child's index for cross-repo questions. Wins all four owner axes (§3a) at the cost of an
  aggregation step.

## 5. Recommendation (for OWNER decision) — revised forward 2026-06-22

**Adopt Hybrid representation (Option C) on a Distributed + system-overlay topology (T2): "C × T2".**

Why the topology matters as much as the representation: the original spike recommended Hybrid but assumed
the **centralized** layout, in which the parent still generates structure from child code it **cannot
see**. That leaves the drift in place. Moving the generated structural layer **into each child repo**,
where its source is checked out and language-native tooling can run, is what actually makes freshness
structural for **the product** (not just for the parent's `.claude/`). The parent keeps the one thing it
*is* the right home for — the **cross-repo semantic overlay** — and nothing else.

Concretely, C × T2:
1. **Per child repo:** a regenerate-on-demand structural index (`llms.txt`/code-graph, or **SCIP/LSIF**
   for the polyglot repos) committed in-repo, built by that repo's CI/pre-commit. Always fresh, local,
   cheap for that repo's agents to load.
2. **Parent overlay:** `domain.yaml` + `services.yaml` + `conventions.md`/ADRs stay hand-curated as
   low-churn markdown/YAML (Obsidian-vault authoring is a good fit, §3b) — **no** dirty-tracking machinery.
3. **Aggregator:** a thin parent-side step that references each child's generated index for cross-repo work.
4. **Hook 15 → advisory**, scoped: a child edit consults its **local** generated index (cheap); only edits
   touching the parent semantic overlay consult centrally. Retires `checksums.json` + `/ontology-rebuild`
   for the structural layer and the org-wide per-edit blocking tax.

**Blocking precondition before any commit (from §2a-i):** re-measure derivability **per child repo per
language** (TS via `ts-morph`/`tsc`, Cypher, HCL, SQL — not just Python `ast`). The 54/54 docstring rate
is proven only for the parent; the generator and per-language extractors must clear a real bar on the
product repos first. If a repo's source is *not* cleanly derivable, that repo keeps a hand-curated
structural stub until it is.

Rejected / deferred:
- **Pure-Replace (B)** — still discards the semantic/intent layer the graph cannot reconstruct.
- **Keep (A)** — do-nothing baseline; keeps paying the upkeep + per-edit tax **and** the drift.
- **Hybrid on Centralized (C × T1)** — better than today, but leaves the parent generating from
  unseeable child source, so the structural drift the spike set out to kill **survives**. T2 is what
  closes it.

> **Per owner 2026-06-20 this spike does NOT tear anything out.** Implementation of the chosen
> option is deferred to a later phase, contingent on the decision recorded below and in
> `phase-6.md` §criterion #4 — and gated on the per-language derivability re-measurement above.

---

## OWNER DECISION — **DECIDED 2026-06-22: C × T2**

_Representation:_
- [ ] A — Keep · [x] **C — Hybrid** (generate structural layer, hand-curate semantics/intent, soften Hook 15 to advisory) · [ ] B — Replace

_Topology:_
- [ ] T1 — Centralized · [x] **T2 — Distributed + system overlay** (per-child generated structural index + central hand-curated semantic overlay + aggregator)

**Owner:** Steven French · **Date:** 2026-06-22 · **Notes:** tooling is **not** decided up front — chosen
by an isolated-branch **bake-off** (below). Teardown remains deferred to a later phase per the P6
spike-and-decide directive.

### Tooling bake-off — owner directive (2026-06-22)

Rather than pre-pick a structural-index tool or overlay format, **test-drive a few candidates on isolated
branches** (no merge → fully revertible, satisfies "no teardown this phase") and compare on **two lenses**:

1. **Agent / Claude consumption** — token cost to load + query, answer quality on real "what calls X / what
   lives in module Y / cross-repo impact" questions, freshness behavior, regeneration cost.
2. **Human-as-knowledge-base** — browsability, authoring ergonomics, backlink/navigation quality, whether
   it's pleasant to actually read and maintain.

**Candidate matrix (test on isolated branches):**

| Layer | Candidates to bake off |
|-------|------------------------|
| Structural (per child repo) | per-repo `llms.txt` + code-graph · **SCIP/LSIF** (Sourcegraph) · tree-sitter/ctags · **Neo4j-backed code graph** (dogfoods the product DB) |
| Semantic overlay (parent) | **Obsidian vault** (user+LLM, `[[backlinks]]`) · plain markdown/YAML · NotebookLM (read-only Q&A) · MkDocs/Docusaurus site |

**Method:** pick ≥2 structural candidates + ≥2 overlay candidates, stand each up on its own branch against a
real product repo (start with a polyglot one — isnad-graph: Python + TS + Cypher — to stress the
per-language derivability question from §2a-i), capture token-usage + behavior numbers and a short
human-usability read, then choose per layer. Each branch is throwaway; only the chosen approach graduates
to the implementation phase.

**Execution tracker:** [noorinalabs-main#820](https://github.com/noorinalabs/noorinalabs-main/issues/820) —
Task 1 (per-language derivability re-measurement, blocking) · Task 2 (this bake-off) · Task 3 (implement
chosen approach). Deferred to a later phase.
