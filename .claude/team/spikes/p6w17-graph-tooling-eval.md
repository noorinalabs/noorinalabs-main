# Spike addendum — Graph-tooling evaluation: **Graphiti** + **graphify** vs the bake-off recommendation

> **Status:** **RECOMMENDATION READY 2026-06-24 — STOP at owner checkpoint.** This is an **addendum** to the
> #853 bake-off (`p6w17-tooling-bakeoff.md`), adding the two graph tools the owner specifically asked to see
> evaluated as first-class candidates. **RECOMMENDATION ONLY** — no implementation, generator wiring,
> `checksums.json` retirement, Hook 15 change, or Task-3 work is done or implied here. **This GATES the #820
> Task-3 tooling decision.**
> **Issue:** noorinalabs-main#820 (ontology **C × T2** execution) · extends #848/#853 (bake-off) · **Wave:** P6W17
> **Author:** Weronika Zielinska (Platform Architect) · **Reviewers:** Nurul Hakim (primary), Aino Virtanen (secondary)
> **Inputs:** `p6w17-tooling-bakeoff.md` (#853, merged) · `p6w17-derivability-remeasure.md` (#843) · `p6w2-ontology-vs-graphify.md` (#728) · decision `phase-6.md` § Criterion #4 (**C × T2**)

---

## 0. TL;DR — updated recommendation

| Question | Verdict |
|----------|---------|
| Do Graphiti or graphify **displace** the bake-off recommendation (`llms.txt`+code-graph / markdown+`[[wikilinks]]`)? | **No — primary recommendation UNCHANGED.** |
| **Graphiti** (getzep/graphiti) | **REJECT for C × T2.** Category mismatch (runtime/episodic *agent-memory* KG, not a codebase structural indexer) **and** hard-fails the two load-bearing C × T2 criteria: it **requires a running graph DB** (Neo4j/FalkorDB/Neptune) and an **LLM API at every ingest**. Same grounds the bake-off already used to reject a generic Neo4j code-graph — now confirmed against the specific named tool. Excellent at what it is *for*; that is not this job. |
| **graphify** (safishamsi/graphify) | **DOES NOT DISPLACE, but is a genuinely strong, fair contender** — it is a *packaged, more-featured* implementation of the **exact** C × T2 shape the bake-off recommended hand-assembling (offline AST code-graph + Obsidian-vault export + cross-repo merge). It **passes** the C × T2 fit criteria. It loses the primary slot on: **~6× token heft** (2.5 MB / ~630k-tok `graph.json` vs the incumbent's ~97 KB), the **same HCL/Terraform + Cypher coverage gap** the bake-off flagged (it does **not** solve polyglot derivability either), and an **LLM-API dependency for its nicest human outputs** + a **pre-1.0 third-party dep**. → **Recorded as the explicit build-vs-buy alternative for Task 3**, with patterns worth borrowing (git merge-driver for `graph.json`, Obsidian/wiki export) and a re-evaluate-at-1.0 trigger. |

**Why this is not a dismissal:** the predecessor spike (#728) was *titled* "ontology-vs-graphify" but actually
measured a hand-rolled ~60-LOC `ast` generator — the **real graphify tool was never run**. This addendum
**actually stood graphify up and ran it on real product source** (isnad-graph + user-service), so the owner gets
measured numbers, not a paper rejection. Graphiti could not be stood up in-env (no DB / no API key) and is
assessed REASONED from its docs, with **no fabricated numbers**.

---

## 1. Method — measured vs reasoned

| Tool | Disposition | What was actually done |
|------|-------------|------------------------|
| **graphify** | **MEASURED — fully stood up** | `uv pip install graphifyy` (v0.8.47) into a clean venv; ran `graphify update --no-cluster` (offline, no LLM, no DB) over isnad-graph product source (261 files) and user-service (69 `.py`); exercised the offline `explain` / `path` / `query` CLIs; ran `merge-graphs` cross-repo. Numbers below are real. |
| **Graphiti** | **REASONED** | Read repo + docs. Standing it up needs a running Neo4j/FalkorDB **and** an LLM API key (OpenAI default) — neither provisioned for a throwaway spike, exactly as the bake-off declined to stand up Neo4j. Assessed on architecture; no numbers fabricated. |

All graphify runs were in the scratch dir; **nothing is committed except this report** (no-teardown-before-checkpoint).
Token estimates are bytes ÷ 4 (same proxy as the bake-off), for relative comparison only.

---

## 2. graphify — MEASURED

### 2.1 What it is
A Python tool (tree-sitter AST for code + optional LLM semantic extraction for docs/PDF/images) that turns a
folder into a queryable knowledge graph stored as a **local `graph.json`** — *"Code files processed locally via
tree-sitter. Nothing leaves your machine."* Code-only extraction needs **no API key and no database**. Optional
`--neo4j` push, `--mcp` server, Obsidian/wiki/HTML exports, a git **merge-driver** for `graph.json`, and
`merge-graphs` for cross-repo roll-up. PyPI package is temporarily `graphifyy` (the `graphify` name is being
reclaimed). Code grammars (README): `py .ts .js .go .rs .java .c .cpp .rb .cs .kt .scala .php`.

### 2.2 Stood-up numbers (isnad-graph, the polyglot stress repo)

| Metric | Value |
|--------|-------|
| Files extracted | **261** (offline AST, 20 workers) |
| Nodes / edges | **3,105 / 5,596** |
| Wall time | **4.06 s** (125% CPU, 102 MB peak RSS) |
| Backend / API needed | **none** — `--no-cluster`, fully offline |
| `graph.json` size | **2.5 MB ≈ ~630k tok** to whole-load |
| Other outputs (offline) | `manifest.json` (42 KB), `cache/` (SHA256 per-file) |
| Incremental | `graphify update`/`watch` re-extract changed files only (no LLM) |

**Granularity is per-symbol, not per-module** — that is why 3,105 nodes vs the bake-off generator's 194
(109 Py modules + 85 TS files). Richer edge vocabulary than the incumbent's import-only graph:
`contains, imports, imports_from, references, calls, method, uses, inherits, re_exports, depends_on, extends`,
plus a `rationale_for` edge that attaches docstring/comment **intent** to symbols (572 "rationale" nodes) and
**1,052 `.md` doc-structure nodes**. So graphify captures more "skeleton" *and* some description/intent the
incumbent leaves to the overlay — offline.

### 2.3 Offline scoped queries (no LLM, no DB) — all work

| CLI | Behaviour (measured) | Token shape |
|-----|----------------------|-------------|
| `graphify explain "main()"` | node + neighbours (id, source loc, degree, typed edges) | ~15 lines — **cheap** |
| `graphify path "A" "B"` | shortest path with typed hops | small |
| `graphify query "…"` | **keyword-seeded BFS depth-2** over the graph (~23 nodes) | small |

**Honest caveat:** in offline mode `query` is **keyword-seeded BFS, not semantic retrieval** — the
natural-language phrasing is cosmetic without an LLM/embeddings backend. The scoped CLIs keep query token cost
low, but they are a **CLI interface**, not the "agent just reads a small `llms.txt` section" affordance — and the
**whole-graph load is ~6× the incumbent** (630k vs ~24k tok), so an agent must use the CLI, not slurp the file.

### 2.4 Cross-repo (the T2 aggregator story) — MEASURED
`graphify merge-graphs <ig> <us>` produced a combined **4,299-node / 8,256-edge / 4 MB** graph **offline**.
There is also a git **merge-driver** that union-merges `graph.json` across branches — directly relevant to the
known "parallel panels appending a shared file conflict" hazard (`feedback_parallel_panels_shared_file`).

### 2.5 The honest limitations

1. **Polyglot gap is NOT solved.** Node source-file extensions captured: `.py 1562, .md 1052, .tsx 205, .ts 135,
   .json 87, .sh 21, .js 2, .toml 1` — **zero `.tf`, zero `.cypher`, zero `.sql`**. graphify has the **same**
   HCL/Terraform + Cypher blind spots the bake-off (#843/#853) flagged for the deploy/isnad-graph stacks. Adopting
   it would still require us to bolt on HCL/Cypher extractors ourselves.
2. **Token heft.** 2.5 MB / ~630k-tok `graph.json` per repo (per-symbol + doc + rationale nodes) → heavier git
   diffs and no cheap whole-load. The merge-driver mitigates conflict, not size.
3. **The best human outputs need an LLM key.** `obsidian/` vault, `wiki/`, `GRAPH_REPORT.md`, named communities
   (`graphify .` full run) require a Gemini/Claude/OpenAI key for semantic extraction + community naming
   (Leiden clustering itself is offline; *naming* is not). The offline run yields `graph.json` + `manifest.json`
   only. So graphify's headline "human knowledge base" value reintroduces an external API dependency for that layer.
4. **Third-party, pre-1.0.** v0.8.47, PyPI name in flux (`graphifyy`). Against the org's full-parity / no-surprise
   posture this is a real supply-chain + pinning + stability consideration vs the ~70 LOC stdlib generator we own.

---

## 3. Graphiti — REASONED

**What it is:** an open-source framework for **temporal context graphs for AI agents** — it ingests *episodes*
(conversational/business/JSON data), uses an LLM to extract entities + relationships with **bi-temporal validity
windows** (when a fact became true / was superseded), does LLM-driven entity resolution/dedup, and serves
**hybrid retrieval** (semantic embeddings + BM25 + graph traversal) at query time. It is purpose-built for
**agent long-term memory over changing real-world data**.

**Hard requirements (from docs):**
- **A running graph database** — Neo4j 5.26+ **or** FalkorDB **or** Amazon Neptune (+ OpenSearch for Neptune).
  Must be up before Graphiti initialises.
- **An LLM provider** at ingest (OpenAI default; Anthropic/Gemini/Groq), needing **structured-output** support;
  embeddings provider too.

**Assessment against C × T2:**
- **(a) no required running service → FAIL (hard).** Every query needs the DB up; nothing is a loadable
  plain artifact. This is the *exact* axis on which the bake-off rejected a generic Neo4j code-graph.
- **(b) regenerable in each child's CI as a plain artifact → FAIL.** State lives in the DB; CI would need to
  stand up a DB **and** spend LLM tokens on every build. Not a per-repo committable index.
- **(c) git-diffable/versioned → FAIL.** Graph state is in the database, not git.
- **(d) low scoped token cost → N/A under (a).** Sub-second retrieval, but only against a running service.
- **(e) human knowledge base → MEDIUM**, via Neo4j Browser, but behind the same infra + API cost.
- **Category mismatch:** Graphiti has **no AST/code parsing** — it is not a codebase structural indexer. To use
  it for the ontology you'd feed code/docs as "episodes" and pay LLM extraction for what tree-sitter does for
  free offline. Its genuine strengths — bi-temporal fact invalidation, entity resolution, semantic+graph
  hybrid recall — are **runtime agent-memory** features, not what a regenerable, in-git, per-repo structural
  index + hand-curated overlay needs.

**Verdict: REJECT for the ontology C × T2 job.** Right tool, wrong problem. (If the org ever wants a *runtime*
agent memory over the product's *data* — not its code/ontology — Graphiti is a strong candidate for that
separate problem, and notably can dogfood the platform's existing Neo4j.)

---

## 4. Scoring — same two lenses + the five C × T2 fit criteria

Scores 1–5 (5 = best); columns identical to the bake-off so this slots into the same comparison.

### 4.1 Lens 1 — Agent / Claude consumption

| Candidate | Skeleton | Description | Token cost (load+query) | Freshness/regen | Directly Claude-loadable | **Σ** |
|-----------|:--------:|:-----------:|:-----------------------:|:---------------:|:------------------------:|:-----:|
| **llms.txt + code-graph** (incumbent) | 4 | 4 Py / 2 TS | **5** (scope-loadable ~2–10k) | **5** | **5** (plain text/JSON) | **★ 23** |
| **graphify** | **5** (per-symbol calls/uses/inherits) | 4 (`rationale_for` + doc nodes, offline) | 3 (whole=630k; scoped via CLI cheap) | **5** (4 s offline, `--update`) | 4 (plain JSON, but heavy; CLI for cheap scope) | **21** |
| Graphiti | 2 (no code skeleton) | 4 (LLM semantics) | 2 (service-only) | 4 (real-time, DB state) | **1** (running DB + API) | 13 |

### 4.2 Lens 2 — Human as knowledge base

| Candidate | Browsability | Authoring | Backlinks/nav | Maintainability | **Σ** |
|-----------|:-----------:|:---------:|:-------------:|:---------------:|:-----:|
| markdown/YAML + `[[wikilinks]]` (incumbent overlay) | 4 | **5** | **5** | **5** | **19** |
| **graphify** | **5** (html + obsidian vault + wiki + report) | **5** (generated) | **5** (vault backlinks + path/explain) | 4 (offline structure; nice outputs need LLM key; 2.5 MB diffs, merge-driver helps) | **★ 19** |
| Graphiti | 3 (Neo4j Browser) | 5 (generated) | 4 | 2 (DB + API upkeep, non-versioned) | 14 |

> **Read:** graphify **wins the human lens (ties the incumbent overlay at 19)** — it bundles, off the shelf,
> exactly the Obsidian-vault + browsable-site the bake-off recommended assembling by hand. On the **agent lens
> it trails (21 vs 23)** purely on token heft + the CLI-vs-direct-read affordance. Graphiti loses both lenses on
> the running-service / API axis — the same axis SCIP and Neo4j lost on in the bake-off.

### 4.3 The five C × T2 fit criteria

| Criterion | incumbent | **graphify** | Graphiti |
|-----------|:---------:|:------------:|:--------:|
| (a) plain artifact, **no required running service** | ✅ | ✅ (offline `graph.json` + offline CLIs) | ❌ **hard fail** (DB required) |
| (b) regenerable in each child's **own CI** (distributed) | ✅ | ✅ (one pip tool, 4 s, `--update`) | ❌ (DB+API per build) |
| (c) git-diffable / versioned | ✅ | ✅\* (JSON in git; \*2.5 MB, noisy diffs; merge-driver mitigates) | ❌ (state in DB) |
| (d) low token cost for scoped queries | ✅ (read a section) | ✅\* (offline `explain`/`path`/`query`; \*whole-load 6× heavier; needs CLI) | ❌ (service-gated) |
| (e) human-as-knowledge-base usability | ✅ (Obsidian vault) | ✅✅ (vault+wiki+html+report — but full outputs need LLM key) | ~ (infra-gated) |

graphify **clears all five**; Graphiti **fails (a)–(d)**.

---

## 5. Head-to-head vs the current recommendation — and the decision

**Primary recommendation is UNCHANGED:** per-repo **`llms.txt` + code-graph** (owned ~70-LOC `ast` / `ts-morph`
/ `hcl2` generators) for the structural layer, **markdown/YAML + `[[wikilinks]]`** for the central overlay.

**Why graphify does not take the primary slot (despite passing the criteria):**
1. **Token economy** is the load-bearing C × T2 property and the incumbent wins it ~6× (24k vs 630k whole-load;
   and the incumbent's cheap path is "read a small text section," not "run a CLI").
2. **graphify does not solve the actual hard problem** — HCL/Terraform + Cypher derivability — which is the only
   thing #843 flagged as not-clean. We'd *still* hand-build those extractors, so we'd be taking a 3rd-party
   pre-1.0 dep **and** doing the hard part ourselves.
3. **Control + supply chain:** the incumbent is ~70 LOC of stdlib we own and pin trivially; graphify is an
   external, pre-1.0, renaming package whose best human features need an external LLM API.

**Why graphify is nonetheless recorded as a real, fair alternative for Task 3 (not dismissed):**
- It is the **strongest off-the-shelf realization of the chosen C × T2 shape** and ties the incumbent on the
  human lens. If, at Task-3 build-vs-buy time, the owner values the bundled Obsidian-vault/wiki/HTML + the
  cross-repo `merge-graphs` aggregator + the `graph.json` git **merge-driver** more than token economy and
  full control, graphify is a defensible "buy."
- **Patterns to borrow regardless of build/buy:** (i) the **git merge-driver / union-merge** for a committed
  graph artifact (solves the parallel-shared-file conflict hazard cleanly); (ii) the **Obsidian-vault export**
  as the human render of the structural graph; (iii) `merge-graphs` as the **T2 cross-repo aggregator** design.
- **Re-evaluate trigger:** revisit graphify for the primary slot if it reaches **1.0**, **shrinks the
  per-symbol token footprint** (or ships a compact `llms.txt`-style export), and **adds HCL/Cypher** grammars.

**Graphiti: REJECT** for C × T2 (category mismatch + hard service/API dependency). Re-file as a candidate only if
a *runtime agent-memory-over-product-data* need (distinct from the ontology) is ever scoped.

---

## 6. STOP — owner checkpoint (gates #820 Task-3 tooling decision)

This report ends here by design. **Task 3 is NOT started** — no generator wiring, no `checksums.json` retirement,
no Hook 15 change. The owner's decision is the **build-vs-buy** call for the structural generator:
- **Build (recommended):** owned `ast`/`ts-morph`/`hcl2` generators (lowest token cost, full control, no pre-1.0
  dep) + central markdown/`[[wikilinks]]` overlay + a thin aggregator (borrowing graphify's merge pattern).
- **Buy:** adopt graphify as the per-repo generator (gains vault/wiki/merge ergonomics; accepts token heft +
  pre-1.0 dep + still must add HCL/Cypher).

Either way, **Graphiti is out** for this job. Owner confirms tooling + Task-3 scope before any implementation.

---

## Appendix A — reproduction (throwaway, not committed as tooling)

- **Install:** `uv venv --python 3.12`; `uv pip install graphifyy` → graphify **v0.8.47** + ~25 tree-sitter grammars.
- **graphify structural (offline):** `graphify update <isnad-graph-src> --no-cluster` (data/ + node_modules/ +
  .venv/ + .terraform/ + .git/ excluded) → 261 files, **3,105 nodes / 5,596 edges**, 4.06 s, no LLM/DB;
  `graph.json` 2.5 MB; node exts `.py 1562 / .md 1052 / .tsx 205 / .ts 135 / .json 87 / .sh 21 / .js 2 / .toml 1`,
  **0 `.tf` / 0 `.cypher` / 0 `.sql`**.
- **Offline CLIs:** `explain "main()"`, `path "A" "B"`, `query "…"` (keyword-BFS depth-2) — all ran with no LLM/DB.
- **Cross-repo:** user-service (69 `.py`) → 915/2815; `merge-graphs ig us` → **4,299 nodes / 8,256 edges / 4 MB**, offline.
- **Reasoned (not stood up):** Graphiti — requires a running Neo4j/FalkorDB/Neptune + an LLM API key (OpenAI
  default); not provisioned for a throwaway spike. Assessment in §3 is argued from its docs, no fabricated numbers.
