---
name: project_vector_index_deferred
description: Move #10 (prose vector index over memory + closed issues/PRs) DEFERRED-by-design 2026-07-19 — trigger unmet; don't re-propose without the tripwires below.
type: project
promotion_target: none
status: active
---
# Prose vector index — deferred by design (token-efficiency Move #10)

The token/context-efficiency initiative (tracker main#986) ranked a **prose vector index over memory + closed issues/PRs** as Move #10, explicitly **conditional**: build it *only if `MEMORY.md` + grep stops scaling*. Owner reviewed the evidence 2026-07-19 and chose **defer with a decision record** (this file). Moves #1–9 shipped; #10 is deferred-by-design, not dropped.

## Why deferred (the trigger is unmet)
- **MEMORY.md is not near its limit** — 98/132 index entries, 22,668/28,672 bytes at deferral time, and it *shrank* during the initiative (Moves #4 + #6 took it from ~24.8 KB). ~21–26% headroom.
- **Grep over all 98 memory files is ~6 ms** — the retrieval it would replace is not a bottleneck.
- **Against the industry direction the survey found:** Anthropic *removed* vector RAG from Claude Code ("agentic search generally works better… outperformed everything, by a lot"); AAAI-2026 found agentic keyword search ~94.5% of RAG faithfulness with no embeddings. Windsurf/Cline/Sourcegraph followed.
- **Real costs a vector index would add:** embedding **staleness** (index drifts from source), **egress** (content leaves the box to an embedding API — against the org's zero-egress preference), and ongoing maintenance.

## Tripwires — revisit #10 only if one of these fires
1. **MEMORY.md entry count approaches the cap** — sustained ≥ ~120/132 index entries *after* a consolidation/decay sweep (i.e. genuine growth, not un-swept bloat — the [[feedback_enforcement_hierarchy]] memory-budget gate + the /wave-retro Step 7.8 decay sweep should bind first).
2. **Grep-over-memory recall visibly fails** — a "have we solved this before?" lookup that a keyword grep misses because the answer is phrased differently (semantic recall gap), recurring often enough to cost real time.
3. **Corpus scale changes kind** — if "memory + *closed issues/PRs*" is genuinely wanted as a searchable store (thousands of items), keyword search over a local export should be tried *first*; only if that fails does a **local, zero-egress** embedder (e.g. sqlite-vec over an export) get prototyped — never a remote embedding API.

If revisiting: prototype **local + zero-egress + behind a flag** first; do not wire a remote-embedding index into the session path.

Related: [[project_ontology_system]] (the structural repo-map + PageRank hub view, main#1002, already covers code navigation); the durable web-fetch capture helper (main#1004, `capture_reference.py`) covers the other durable-recall gap the survey found.
