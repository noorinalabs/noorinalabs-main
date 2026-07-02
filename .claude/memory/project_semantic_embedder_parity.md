---
name: project_semantic_embedder_parity
description: prod+stg semantic search API queries with HashingEmbedder while corpus embedded with MiniLM → 200-with-garbage; stg-gate implication.
metadata:
  type: project
---

Semantic search on prod (criterion 2 of Phase 8) has a silent embedder-parity gap co-verified during the ig#1148 review (PR #1164, Jun-Seo Park verdict):

- `noorinalabs-deploy/compose/docker-compose.prod.yml` `isnad-graph-api` sets **no `EMBEDDING_MODEL`** and runs the **torch-free** image → API embeds queries with the lexical `HashingEmbedder` (config default `hashing`).
- The corpus re-embed job bakes `EMBEDDING_MODEL=paraphrase-multilingual-MiniLM-L12-v2`.
- Both are `vector(384)`, so a hashing query cosine-compares against MiniLM corpus vectors with **no dimension error** → **HTTP 200 with a meaningless ranking**, not a visible failure. A plain "200 + non-empty" probe passes on garbage; the keyword-assertion smoke check added in PR #1164 is what surfaces it.
- The compose `api` block is **identical across both VPS boxes**, so **stg's API is also on hashing** — the mismatch bites any env whose corpus is re-embedded with MiniLM while the API stays torch-free.

**stg-gate implication:** an apparent stg "semantic search works" may be silently returning garbage-but-200, so it is **not** a validated gate for the semantic criterion until embedder parity is fixed. Directly qualifies [[feedback_stg_gate_before_prod]].

**Fix (promotion-window, owner-gated, apply in lockstep):** either give the API a model-capable image + matching `EMBEDDING_MODEL`, or re-embed the corpus with `hashing`. API image+model and corpus embedder MUST change together — flipping one regresses consistent-lexical → inconsistent-garbage. Tracked: **deploy#523** (bug/infra/wave-23, boarded). Distinct from the closed prod re-embed cutover deploy#470. Child-repo detail in isnad-graph memory `project_semantic_embedder_parity_prod.md`.
