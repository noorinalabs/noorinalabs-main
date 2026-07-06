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

**Fix (promotion-window, owner-gated, apply in lockstep):** either give the API a model-capable image + matching `EMBEDDING_MODEL`, or re-embed the corpus with `hashing`. API image+model and corpus embedder MUST change together — flipping one regresses consistent-lexical → inconsistent-garbage. Tracked: **deploy#523** (bug/infra, boarded). Distinct from the closed prod re-embed cutover deploy#470. Child-repo detail in isnad-graph memory `project_semantic_embedder_parity_prod.md`.

**RESOLUTION (2026-07-06) — Option 1 chosen (model-capable API image), stg DONE, prod GATED on ig#1174.**
- **deploy#523 CLOSED / PR #525 MERGED** (`ae758d7`): compose `api` repointed to the model-capable **`-embed`** image via a durable IaC seam — `image: ${API_IMAGE:-…-isnad-graph-embed}:${IMAGE_TAG:-latest}` (fixed state IS the compose default; survives `write-deploy-env` `.env` truncation), `EMBEDDING_MODEL=MiniLM`, `--workers 4→2`, `mem_limit 2G→4G`, healthcheck `start_period 60s`. Reviewers Aisha Idrissi + Nino Kavtaradze approved. Rollback is IaC-only (git revert / one-line default flip / `rollback.yml`); box `.env` edits are ephemeral.
- **stg VERIFIED-GOOD**: api container = `embed:stg-latest` + `EMBEDDING_MODEL=MiniLM`; in-container prod `PgClient` cosine query returns topically-correct top-5 for patience/prayer/charity (embedder=`SentenceTransformerEmbedder`, corpus=33,958 embeddings). **Memory gate PASS**: measured **~1.5G/worker** (peak RSS 1,549 MB incl. forward pass) → projected container peak **~3.2G < 4G cap**. So stg IS now a valid semantic gate.
- **prod NOT yet cut over** — owner decision 2026-07-06: **scan embed first, then promote** (safety over speed; prod semantic search stays broken meanwhile). Blocking prereq = **ig#1174** (wire Trivy CVE-scan into `build-and-push-embed`; Linh Pham implementing). After ig#1174 merges → embed rebuilds+scans → promote to prod **with embed explicitly included** (`images=…,embed`, else no `embed:prod-<sha>` exists — deploy#470 opt-in promotion). ig#1174 detail: embed shares the scanned api image's pinned base; gap is the torch/ML layer's scan gate only.
- **Follow-up filed: deploy#527** — smoke check 8 (the parity CI guard, ig#1148) hits the auth-gated `/api/v1/search/semantic` unauthenticated → always 401, so it can't actually verify ranking; needs token-minting or a DB-side check. The guard is currently non-functional (had to verify ranking out-of-band).
