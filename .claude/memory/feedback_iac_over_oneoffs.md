---
name: feedback_iac_over_oneoffs
description: Owner 2026-07-07 — repeatable data loads/transforms/infra ops MUST sit behind GitHub Actions + IaC, not box one-offs.
metadata:
  type: feedback
---

Owner 2026-07-07: "One offs should not be the norm, data loads, transformations, infra should sit behind GitHub Actions and IaC if it needs to be repeated."

**Why:** box one-offs (`docker exec`/`cypher-shell` by hand, ad-hoc `psql`) are unreproducible, unaudited, and drift from the deployed state. Any op that runs more than once — stg then prod, or re-run after a future reload — is by definition repeatable and belongs in a versioned workflow. This is the same discipline the embed cutover followed (`reembed-corpus.yml` + `promote.yml`, all IaC; the only allowed box one-offs there were the deliberate orphan-kill + TRUNCATE before a clean load).

**How to apply:**
- Before running any data/graph/infra op against a box, ask: will this repeat (stg→prod, or again later)? If yes → build/extend a workflow in `noorinalabs-deploy`, don't `docker exec` it by hand.
- Neo4j graph ops (the da#325 TRANSMITTED_TO id migration, the da#326 GDS enrich/centrality) have **no** existing IaC vehicle — `db-migrate.yml` is user-service **alembic/Postgres only**; data-acquisition publishes **no image** (only local `Dockerfile.load`). Both ops are pure Neo4j-side (Cypher `UNWIND` / server-side GDS), so the clean vehicle is a new deploy workflow running versioned `.cypher` via `cypher-shell` in the deployed `neo4j` container (GDS 2.13.8 already installed) — not a new container image.
- Genuinely-single-shot, irreversible interventions (orphan-kill, one-time TRUNCATE) are the narrow exception and must be called out explicitly.

Relates to [[project_semantic_embedder_parity.md]] (embed cutover ran fully IaC), [[feedback_prefer_correct_over_expedient]].
