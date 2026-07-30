---
name: feedback_query_builder_test_needs_real_engine
description: A query-builder's unit tests prove the STRING, not that the engine accepts it; execute the built query against a real DB/engine or the guard is blind.
metadata:
  type: feedback
---

A unit test over a **query/command builder** that asserts the *generated string* (correct escaping, correct literal, right shape) proves the builder emits what you intended — it does **NOT** prove the target engine will accept and execute it. A string can be perfectly well-formed and still be invalid in the target language.

**Concrete failure (deploy#606 → #607, 2026-07-14, honest-leaderboard flag-now):** `flag_over_merged_narrators.py` built a Cypher precheck `UNWIND $rows AS r OPTIONAL MATCH (n:Narrator {id:r.id}) RETURN r.id + ' matched=' + toString(count(n))`. 32 behavioural unit tests (incl. adversarial injection payloads) passed; TWO reviewers (security + mechanics) approved; ALL CI green. The query is **invalid Cypher** — it mixes a grouping key (`r.id`) with an aggregate (`count(n)`) in one RETURN expression, which Neo4j rejects ("Aggregation column contains implicit grouping expressions. Illegal expression(s): r.id"). The ONLY instrument that caught it was the manual stg dry-run executing it against real Neo4j. Fix = `WITH r.id AS id, count(n) AS matched RETURN id + ...` + an integration test running all 3 phase queries against an ephemeral engine.

**Why:** the builder's unit tests and the engine's parser are two different instruments measuring two different things (string correctness vs language validity). Green on the first says nothing about the second. This is the same family as [[feedback_silent_zero_is_not_a_measurement]] (verify the instrument before the reading) and [[feedback_passing_repro_masks_bug]] (a green repro using the wrong invocation form proves nothing).

**How to apply:** when a builder emits a query/command/config for an external engine (Cypher, SQL, a shell invocation, a Terraform/promtool/amtool config), the acceptance guard MUST execute the built artifact against the real engine (an ephemeral service container / testcontainer / `--check`/`EXPLAIN` mode), not just assert the string. If a manual dispatch is currently the only thing exercising the real engine, that gap belongs in CI. For a reviewer: a query-builder PR whose tests only assert string output is NOT verified against its engine — say so, and require an execute-against-engine test before approving. Related: `feedback_calibrate_the_mutation_before_counting_it` (in the **noorinalabs-deploy** memory store, not this one), [[feedback_verify_posttooluse_firing]].
