# Spike — Ontology tooling bake-off (structural index + semantic overlay)

> **Status:** **RECOMMENDATION READY 2026-06-24 — STOP at owner checkpoint.** This document is a
> bake-off comparison + a single recommended tool per layer. It is a **RECOMMENDATION ONLY**; no
> implementation, generator wiring, `checksums.json` retirement, or Hook 15 softening is done here.
> Owner reviews and confirms the tooling + Task-3 scope before any implementation begins.
> **Issue:** noorinalabs-main#848 (Task 2) · child of #820 (ontology **C × T2** execution) · **Wave:** P6W17
> **Author:** Weronika Zielinska (Platform Architect) · **Reviewers:** Nurul Hakim (primary), Aino Virtanen (secondary)
> **Inputs:** Task 1 derivability re-measure `p6w17-derivability-remeasure.md` (#843, merged) · decision `phase-6.md` § Criterion #4 (**C × T2**) · predecessor `p6w2-ontology-vs-graphify.md` (#728)

---

## 0. TL;DR — recommendation per layer

| Layer | **Recommendation** | One-line rationale |
|-------|--------------------|--------------------|
| **Structural index** (per child repo, generated) | **`llms.txt` + code-graph** — stdlib `ast` (Python, zero-dep) + `ts-morph` (TS) + `python-hcl2` (HCL), emitting a text `llms.txt` + a JSON import/symbol graph | The **only** candidate that is fully **text-native and directly Claude-loadable** with **no backend, binary, or CLI** to stand up; zero-to-light deps; regenerates in each repo's own CI/pre-commit where the source is visible (fits **T2 distributed**); git-diffable; cheapest token cost for scoped queries. |
| **Semantic overlay** (central, hand-curated) | **Plain markdown/YAML authored with Obsidian-compatible `[[wikilinks]]`** | Git-native, CI-lintable, **loads directly into Claude with zero build**, and the *same* files open as an Obsidian vault (graph view + bidirectional backlinks) for humans. Already the repo's own habit — the memory system uses `[[wikilinks]]` today, so migration cost ≈ 0. MkDocs/Docusaurus is an optional read-only render *of* the markdown, not the source of truth. |

**Rejected (with reasons, below):** SCIP/LSIF as the *primary* index (binary protobuf, needs Sourcegraph/`scip` CLI not in env — wrong fit for "Claude loads + queries"; keep as a *future enhancement* if a code-intel backend is ever stood up); tree-sitter/ctags (don't beat the `ast`/`ts-morph` path already proven in Task 1); Neo4j-backed code graph (powerful for blast-radius but adds a running-DB dependency + a fresh-load coupling — over-engineered for a cheap, offline, per-repo index); NotebookLM as system-of-record (hosted Google product, non-versioned, data egress — fine only as an ad-hoc consumer of exported markdown).

**Both recommendations converge on the same property: the artifact is plain text in git, loadable by an agent with no external service, regenerable where the code lives.** That is the load-bearing fit for C × T2 (generated structural layer + hand-curated overlay, distributed to children with a central overlay).

---

## 1. Method — what was actually stood up vs reasoned

All structural candidates were exercised on **isnad-graph** (per the Task-1 hand-off: the only repo that
exercises Python + TS + Cypher together, so it stresses every per-language derivability boundary at once).
Token costs are estimated at **chars ÷ 4** (a conservative English/code proxy); they are for *relative*
comparison, not billing-exact. Each candidate is explicitly labelled **MEASURED** (stood up and numbers
are real) or **REASONED** (could not be fully stood up in-env; assessment is argued, not fabricated).

| Candidate | Layer | Disposition | Why |
|-----------|-------|-------------|-----|
| `llms.txt` + code-graph | structural | **MEASURED** — fully stood up (Python `ast` + TS `ts-morph`) | stdlib + on-demand `npm i ts-morph` both succeeded |
| SCIP / LSIF | structural | **MEASURED (index) / REASONED (query)** | `scip-typescript` installed + **produced a real `index.scip`**; but the `scip` Go CLI / Sourcegraph backend needed to *query* it is not in env |
| tree-sitter / ctags | structural | **REASONED** | neither binary preinstalled (confirmed Task 1); tree-sitter-as-library = building the same extractor `ast`/`ts-morph` already are |
| Neo4j-backed code graph | structural | **REASONED** | needs a running Neo4j; no DB stood up for a throwaway spike. Assessed on architecture. |
| plain markdown / YAML | overlay | **MEASURED** — it is the status quo (`ontology/*.yaml` + `conventions.md`) | sizes read directly from the repo |
| Obsidian vault | overlay | **MEASURED (format) / REASONED (GUI)** | built a 25-note vault with 104 `[[wikilinks]]`; the **format** is plain markdown (measurable), the **graph-view GUI** is a desktop app (assessed, not run) |
| MkDocs | overlay | **MEASURED** — `pip install mkdocs` + `mkdocs build` succeeded, 27-page site | real build |
| Docusaurus | overlay | **REASONED** | node/React static-site generator; same *category* as MkDocs (render-over-markdown) but heavier toolchain; not separately stood up |
| NotebookLM | overlay | **REASONED** | hosted Google product; cannot be git-versioned/CI-run in-env. Assessed on properties. |

Throwaway candidate-build branches and generated artifacts live only in a scratch dir; **nothing is
committed except this report** (per the owner spike-and-decide / no-teardown-before-checkpoint directive).

---

## 2. Structural candidates — measured results

### 2.1 `llms.txt` + code-graph  — **MEASURED, fully stood up**

A ~70-LOC generator (stdlib `ast`, zero-dependency) over isnad-graph's Python product source, plus the
Task-1 `ts-morph` extractor over its frontend, produced two artifacts per language: a human-readable
**`llms.txt`** (one section per module, module + symbol one-line docs) and a machine **`graph.json`**
(nodes = modules/files, `edges_internal` = resolved intra-repo import edges, symbols per node).

| Sub-artifact | Scope | Yield | Size | **Token cost to load whole** |
|--------------|-------|-------|------|------------------------------|
| Python `llms.txt` | 109 modules | 459 symbols | 41 KB | **~10.3k tok** |
| Python `graph.json` | 109 nodes | 132 internal edges (505 total) | 64 KB | ~16.1k tok |
| TS `llms.txt` | 85 files | 245 exports | 8 KB | **~2.0k tok** |
| TS `graph.json` | 85 nodes | 282 import edges | 33 KB | ~8.2k tok |

**Read:** the *human/agent-facing* `llms.txt` is the cheap load (Python **~10k tok**, TS **~2k tok**) and
is what an agent reads to answer "what's in module-Y"; the `graph.json` is the precise structure an agent
*greps* for "what-calls-X / blast-radius" without loading whole. Both are **plain text in git**, regen on
file save, no service. TS doc-coverage measured **8.6%** (confirms Task-1's 11–17% finding) — the TS
`llms.txt` is symbol-rich, description-thin, exactly as predicted; descriptions come from the overlay.
Critically, the artifact is **scope-addressable**: an agent loads only the module/section it needs, so the
*effective* query token cost is a small fraction of the full-load numbers above.

### 2.2 SCIP / LSIF  — **MEASURED index, REASONED query**

`@sourcegraph/scip-typescript` installed on-demand and **successfully indexed** isnad-graph's frontend,
producing a real **`index.scip` = 1.85 MB binary protobuf**.

- **Strength (real):** SCIP is *occurrence-level* — every definition, every reference/use-site, hover
  signatures, cross-file precise. Far richer than the import-edge graph of §2.1 for "find all references."
- **Blocker for *this* use (measured):** the artifact is **binary protobuf** (92%-"printable" only because
  symbol names dominate the bytes — it is **not** valid loadable text). Consuming it requires the **`scip`
  Go CLI** (`scip print`/`scip snapshot`) or a **Sourcegraph backend** to convert/serve — **neither is in
  the environment** (`which scip` → not found; confirmed Task 1: scip not preinstalled). An LLM cannot load
  `index.scip` directly, and at 1.85 MB *for the frontend alone* a text conversion would dwarf the §2.1
  cost.
- **Fit verdict:** SCIP optimises for a *code-intelligence service* (hover/go-to-def in an IDE or
  Sourcegraph), not for "an agent loads a text index from git." It is the right tool for a different
  problem. **Reject as primary; revisit as a future enhancement** if the org ever stands up Sourcegraph.

### 2.3 tree-sitter / ctags  — **REASONED**

Neither binary is preinstalled (Task 1). **ctags** emits a `tags` file of *definitions only* — no import
edges, no docstrings, no call graph; strictly weaker than §2.1 for the target questions. **tree-sitter** is
a *parser library*: adopting it means *writing* an extractor on top of it — i.e. rebuilding what stdlib
`ast` and `ts-morph` already give us for free, while adding a native-grammar build dependency per language.
It buys multi-language uniformity but no answer-quality the `ast`/`ts-morph` path lacks. **Reject** —
no advantage over the proven §2.1 path, strictly more setup.

### 2.4 Neo4j-backed code graph  — **REASONED**

Architecturally the most powerful for relationship queries ("transitive blast-radius of X", variable-depth
import paths) and it would **dogfood the product DB**. But: (a) it needs a **running Neo4j** to answer
*any* question — an agent can't query a graph that isn't up, so it fails the "offline, in-git, zero-service"
bar that both layers otherwise meet; (b) it re-introduces a **freshness-coupling** problem (the DB must be
re-loaded on source change) — the very staleness class C × T2 is trying to *retire*; (c) it is central
infra, which fights the **T2 distributed** topology (each child can't trivially own a graph DB in its own
CI). The same blast-radius questions are answerable by **grepping `graph.json`** (a transitive walk over
`edges_internal`) at a fraction of the operational cost. **Reject for the per-repo structural index;** if a
cross-repo relationship explorer is ever wanted, it is a *central, optional* read-model built *from* the
distributed `graph.json` files — a Task-3-or-later nice-to-have, not the index itself.

---

## 3. Overlay candidates — measured results

The overlay is the **hand-curated semantic layer** (domain meaning, cross-repo service topology, ADR
"why") that C × T2 keeps central. Current size: `ontology/domain.yaml` + `services.yaml` +
`conventions.md` + `repos/*.yaml` ≈ **102 KB**.

### 3.1 plain markdown / YAML  — **MEASURED (status quo)**

What the ontology uses today. **Pros:** git-native, CI-lintable (cspell/markdownlint/lychee already wired),
**loads directly into Claude with zero build**, diff-reviewable in PRs, zero new tooling. **Cons:**
cross-references are manual `[path](file)` links with no backlink/navigation affordance; no graph view for
humans. Token cost = the files themselves (and **scope-loadable** — an agent reads only `domain.yaml`, not
all 102 KB).

### 3.2 Obsidian vault  — **MEASURED format, REASONED GUI**

Built a 25-note vault from the structural graph + 2 hand-curated semantic notes (`_DOMAIN.md`,
`_SERVICES.md`): **~8.1k tok across 25 notes, 104 `[[wikilinks]]`** (bidirectional backlinks +
graph view). **The decisive insight: an Obsidian vault *is* a directory of plain markdown** — the
`[[wikilink]]` is the only syntax addition, and it is **already in use in this repo's memory system**
(`[[other-slug]]`). So adopting it is **not a new tool**: it is markdown (§3.1) that *additionally* opens
in Obsidian for humans who want backlinks + the graph view, at **zero cost to the agent path** (Claude
still just reads markdown). The GUI graph-view is assessed (desktop app, not run in-env) but is *optional* —
the value is the backlink syntax, which is text.

### 3.3 MkDocs  — **MEASURED**

`pip install mkdocs` + `mkdocs build` succeeded, producing a **2.6 MB / 27-page static HTML site** from the
*same* markdown. **Key finding:** the 2.6 MB HTML is a **human-presentation render** — an agent never loads
it (it loads the source markdown). So MkDocs (and, by the same logic, **Docusaurus** — heavier node/React
variant of the same category) is a **read-only browse layer *over* markdown, not a source format**. Useful
*optionally* for a polished human portal; it does not change the system-of-record decision and adds a build
step. **Not the overlay format; an optional downstream render.**

### 3.4 NotebookLM  — **REASONED**

Hosted Google product: upload markdown, get RAG-style conversational Q&A with citations. Genuinely pleasant
for a human asking fuzzy questions. But as a **system of record it fails the core C × T2 properties**: not
git-versioned, not CI-regenerable, manual upload to keep fresh, and **source data leaves the repo** to a
third party (a real concern for an org that gitleaks-scans every commit). **Reject as source-of-record;**
acceptable only as an *ad-hoc consumer* a human points at the exported markdown.

---

## 4. Scoring — the two lenses (skeleton and description scored separately)

Scores are 1–5 (5 = best), per the issue's two lenses. Per the Task-1 caveat, **skeleton** (can it produce
inventory/symbols/edges?) and **description** (does meaning ride along?) are scored separately so TS — and
any candidate — isn't penalised for the team's doc-culture gap that the overlay covers anyway.

### 4.1 Lens 1 — Agent / Claude consumption

| Structural candidate | Skeleton quality | Description quality | Token cost to load+query | Freshness / regen | Directly Claude-loadable? | **Σ** |
|----------------------|:---------------:|:------------------:|:------------------------:|:-----------------:|:-------------------------:|:-----:|
| **llms.txt + graph** | 4 (clean inventory+edges; not occurrence-level) | 4 Py / 2 TS (rides docstrings; TS thin) | **5** (scope-loadable, ~2–10k) | **5** (regen on save, no state) | **5** (plain text/JSON) | **★ 23** |
| SCIP / LSIF | **5** (occurrence-level, precise refs) | 3 (hover sigs, no prose intent) | 1 (1.85 MB binary; needs convert) | 4 (re-index per change) | **1** (binary; needs scip CLI/Sourcegraph) | 14 |
| tree-sitter / ctags | 3 (ctags defs-only; tree-sitter = DIY) | 1 (no docs/edges) | 3 | 4 | 3 (tags text; tree-sitter needs a built reader) | 14 |
| Neo4j code graph | **5** (transitive relationship queries) | 3 | 4 (query, not load) | 2 (DB reload on change) | **1** (needs running DB) | 15 |

| Overlay candidate | Backlink/nav for queries | Token cost to load | Freshness / regen | Directly Claude-loadable? | **Σ** |
|-------------------|:-----------------------:|:------------------:|:-----------------:|:-------------------------:|:-----:|
| **markdown/YAML + `[[wikilinks]]`** | 4 (wikilink graph, grep-able) | **5** (scope-loadable) | **5** (git, no build) | **5** | **★ 19** |
| plain markdown/YAML (no wikilinks) | 3 (manual links) | 5 | 5 | 5 | 18 |
| MkDocs / Docusaurus | 4 (nav+search render) | 3 (agent loads MD, render is waste) | 3 (build step) | 4 (loads underlying MD) | 14 |
| NotebookLM | 4 (RAG Q&A) | 2 (external; not loaded into context as text) | 1 (manual upload) | 1 (hosted; data egress) | 8 |

### 4.2 Lens 2 — Human as knowledge base

| Structural candidate | Browsability | Authoring ergonomics | Backlinks/nav | Maintainability | **Σ** |
|----------------------|:-----------:|:--------------------:|:-------------:|:---------------:|:-----:|
| **llms.txt + graph** | 4 (readable text; JSON less so) | **5** (generated — nothing to author) | 3 (import edges = a nav graph) | **5** (regen; no hand-upkeep) | **★ 17** |
| SCIP / LSIF | 2 (binary; need a UI) | 5 (generated) | 5 (in Sourcegraph UI) | 4 | 16 |
| tree-sitter / ctags | 2 (`tags` file) | 4 | 1 | 4 | 11 |
| Neo4j code graph | 4 (Neo4j Browser viz) | 5 (generated) | **5** | 2 (DB upkeep) | 16 |

| Overlay candidate | Browsability | Authoring ergonomics | Backlinks/nav | Maintainability | **Σ** |
|-------------------|:-----------:|:--------------------:|:-------------:|:---------------:|:-----:|
| **markdown/YAML + `[[wikilinks]]`** | 4 (great in Obsidian; fine in editor/GitHub) | **5** (plain markdown) | **5** (bidirectional + graph view) | **5** (git, lint, already our habit) | **★ 19** |
| plain markdown/YAML | 3 | 5 | 2 | 5 | 15 |
| MkDocs / Docusaurus | **5** (polished searchable site) | 4 | 4 | 3 (build/deploy) | 16 |
| NotebookLM | **5** (conversational) | 3 | 3 | 1 (manual, non-versioned) | 12 |

**Both lenses agree on both layers.** Structural: `llms.txt`+graph wins agent-lens decisively (23) and the
human-lens too (17, on "nothing to author + always fresh"); the precision tools (SCIP, Neo4j) lose on the
"loadable by an agent with no service" axis that is the whole point of C × T2. Overlay: markdown/YAML **with
`[[wikilinks]]`** wins both lenses (19/19) — it dominates plain markdown on navigation at zero added cost,
and beats MkDocs/NotebookLM because those are *renders/consumers*, not the source of record.

---

## 5. Recommendation (single, decisive — per layer)

### Structural layer → **`llms.txt` + code-graph** (generated per child repo)
- **Generator:** stdlib `ast` for Python (zero-dep, GO), `ts-morph` for TS (GO, skeleton-only — descriptions
  from overlay), `python-hcl2` / `terraform show -json` for HCL (STRONG GO). SQL rides the Python ORM path.
  Astro needs the small `@astrojs/compiler` frontmatter extractor (conditional). Cypher gets a **hand-curated
  stub** (NO-GO) — all exactly as Task 1 (#843) gated.
- **Emit two artifacts per repo:** `llms.txt` (the cheap, human/agent-readable index) + `graph.json` (the
  grep-able symbol/import graph for blast-radius). Built in each repo's **own** CI/pre-commit (T2: where the
  source is visible and language-native), committed to that repo, aggregated centrally on demand.
- **Why it wins:** only candidate that is text-native + directly Claude-loadable + zero-service + git-diffable
  + regenerable-where-the-code-lives. Cheapest scoped token cost. It is also the approach the P6W2 spike
  already prototyped (54/54 docstrings, ~60 LOC) — now validated polyglot in Task 1 — so it is the
  lowest-risk path to Task 3.

### Semantic overlay → **plain markdown/YAML authored with Obsidian `[[wikilinks]]`** (central)
- Keep the hand-curated `domain.yaml` / `services.yaml` / `conventions.md` / ADR prose as the source of
  record; **add `[[wikilink]]` cross-references** so the same tree opens as an Obsidian vault (graph view +
  backlinks) for humans, with **zero cost to the agent path** (Claude still just reads markdown).
- This is **already the repo's convention** (the memory system uses `[[wikilinks]]`), so adoption is
  formalising an existing habit, not importing a tool.
- **MkDocs/Docusaurus** = optional, read-only *render of* the markdown for a polished human portal — not the
  system of record, deferrable. **NotebookLM** = optional ad-hoc Q&A consumer of the exported markdown — never
  the source, given non-versioning + data egress.

### One unifying principle
Both choices are the **plain-text-in-git, agent-loadable-with-no-service, regenerable-where-it-lives** option
in their category. That is the exact shape C × T2 needs and the reason to reject the more powerful-but-heavier
alternatives (SCIP, Neo4j, NotebookLM) as *primary*.

---

## 6. STOP — owner checkpoint (Task-3 scope, for owner confirmation only)

This report ends here by design. **Task 3 (implementation) is NOT started.** For the owner's checkpoint
decision, the recommended Task-3 scope *would be* (pending confirmation): wire the `ast`/`ts-morph`/`hcl2`
generator into each child repo's pre-commit + CI to emit `llms.txt` + `graph.json`; stand up the central
markdown/YAML overlay with `[[wikilinks]]` + a thin cross-repo aggregator; retire `checksums.json` +
`/ontology-rebuild` for the *structural* layer; soften Hook 15 to advisory. **None of that is done or
implied-approved here** — the owner confirms tooling + scope first.

---

## Appendix A — reproduction (throwaway, not committed as tooling)

All runs were on isnad-graph product source (excluding `node_modules`, `.venv`, `.claude/worktrees`, caches).
Token estimates are chars ÷ 4.

- **S1 Python:** stdlib `ast` generator → `llms.txt` (one section/module, module+symbol one-line docstrings) +
  `graph.json` (modules as nodes, resolved intra-repo `import`/`from` edges, symbols per node). Yield: 109
  modules / 459 symbols / 132 internal edges; 41 KB + 64 KB.
- **S1 TS:** `ts-morph` (on-demand `npm i ts-morph`) over `frontend/` → 85 files / 245 exports / 282 import
  edges; export-doc 8.6%; 8 KB + 33 KB. (Extractor = Task-1 Appendix A.2.)
- **S2 SCIP:** `npm i @sourcegraph/scip-typescript` then `scip-typescript index` over `frontend/` → real
  `index.scip` = 1.85 MB binary protobuf. `which scip` (the Go reader) → not found, so not queryable in-env.
- **O2 Obsidian vault:** 25 markdown notes generated from `graph.json` (package-grouped, with `**Imported by:**
  [[backlinks]]`) + 2 hand-curated semantic notes → ~8.1k tok, 104 `[[wikilinks]]`.
- **O3 MkDocs:** `pip install mkdocs` + `mkdocs build` over the vault markdown → 2.6 MB / 27-page static site.
- **Reasoned (not stood up):** tree-sitter/ctags (not in env), Neo4j code graph (no running DB), Docusaurus
  (same category as MkDocs), NotebookLM (hosted Google product). Assessments in §2.3–2.4, §3.3–3.4 are argued
  from the tools' architecture, explicitly labelled REASONED, with no fabricated numbers.
