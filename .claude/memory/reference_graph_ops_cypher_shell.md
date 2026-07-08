---
name: reference_graph_ops_cypher_shell
description: graph-ops.yml Neo4j gotchas — cypher-shell 5.x removed `:auto` (piped stmts auto-commit by default); migrate verify must sample a RESOLVING hadith_id, not an arbitrary edge.
metadata:
  type: reference
---

Two gotchas hit while shipping the chain-id migrate + fawaz prune via `graph-ops.yml` (deploy), both caught fail-safe (no data harmed), both fixed in-workflow (IaC). See [[project_fawaz_lk_namespace_orphan_chains]].

**1. cypher-shell 5.x removed `:auto` (deploy#540/#541).** The deployed cypher-shell is **5.26.25**; its client commands are only `:begin` / `:commit` / `:param` / `:rollback` — **no `:auto`** (that was a 4.x construct). `CALL {} IN TRANSACTIONS` (and `USING PERIODIC COMMIT`) require an *implicit* (auto-commit) transaction. In 5.x, a **non-interactive cypher-shell auto-commits each statement fed on STDIN by default** — which IS the implicit-tx context those need. So feed the single statement on stdin (`printf '%s\n' "$Q" | docker compose exec -T neo4j sh -c '... cypher-shell --format plain'`) with **NO** client-command prefix. Prefixing `:auto` errors `Could not find command :auto, use :help`. Verify the box's version before assuming any `:`-command exists.

**2. Post-migrate "sample chain" verify must sample a RESOLVING id (deploy#542/#543).** A verify that picks an arbitrary edge (`MATCH ()-[t:TRANSMITTED_TO]->() ... WITH t.hadith_id AS hid LIMIT 1`) then asserts the chain reconstructs is **non-deterministic** and false-fails when the pick lands on a pre-existing dangling/orphan edge (e.g. the ~196k fawaz orphans = ~7.3% of edges): the intermediate `MATCH (:Hadith {id: hid})` empties the row and `count()` returns 0. Fix: constrain the sample to resolving edges — add `AND EXISTS { MATCH (:Hadith {id: t.hadith_id}) }` **before** `LIMIT 1`. This makes the check assert the migrate INVARIANT (a *resolving* chain reconstructs) independent of dangling orphans (completeness is `prune-orphans`' job) — the canonicalization-vs-completeness split. Still non-vacuous: a migration that canonicalizes to non-joining ids (0 resolving) yields no row → count 0 → correctly fails. Same conflation class as the migrate gate itself (absolute-dangling vs migration-invariant).

**General:** `graph-ops.yml` prune run-order guard refuses to prune while raw-form (non-`hdt:`) ids > 0 — pre-migrate EVERY edge id is raw-form so every edge is "dangling"; pruning first would wipe the graph. Always migrate (raw→0) THEN prune. Relates to [[feedback_iac_over_oneoffs]] (these are the repeatable ops that belong in the workflow), [[feedback_passing_repro_masks_bug]] (stg green ≠ prod green when the check is non-deterministic).
