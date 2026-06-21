---
name: project_hadith_id_double_prefix
description: "Streaming normalize worker double-prefixes source_corpus into the Hadith node id (hdt:sunnah:sunnah:...) vs the batch loader's single-prefix (hdt:sunnah:...) — same hadith → two Neo4j nodes across the two ingest paths. Found P4W2 main#139."
metadata: 
  node_type: memory
  type: project
  originSessionId: 080813cd-f3b8-434d-974c-badf58620c96
---

ingest-platform has TWO Parquet→Neo4j ingest paths that key the SAME hadith differently:

- Parsers emit a corpus-prefixed `source_id`, e.g. `sunnah:bukhari:1:1` (`src/parse/base.py::generate_source_id(corpus, collection, *parts)`).
- **Batch loader** `src/graph/load_nodes.py:192` (Kwesi's da#73 path): `hid = f"hdt:{sid}" if not sid.startswith("hdt:") else sid` → `hdt:sunnah:bukhari:1:1` (single corpus). Same idiom in `load_edges.py`.
- **Streaming normalize worker** `workers/normalize/processor.py:182 _hadith_id`: `key = f"{source_corpus}:{source_id}"; "hdt:"+key` → `hdt:sunnah:sunnah:bukhari:1:1` (corpus DOUBLED, because source_id already carries it).

=> If both paths ever load the same data, one hadith becomes two Hadith nodes (no MERGE convergence). `Grading` id `grd:<hadith_id>` inherits the doubling. Confirmed in a real `neo4j:5-community` container (P4W2 main#139, 2026-06-10): Hadith ids landed as `hdt:sunnah:sunnah:bukhari:1:1`.

**Why it hid:** the existing Kafka E2E `tests/integration/test_kafka_worker_e2e.py:287` asserts `hdt:{source}:h-1` but its fixture sets `source_id="h-1"` (NOT corpus-prefixed), so normalize single-prefixes and it passes. main#139's harness uses realistic corpus-prefixed source_ids and exposed it. Lesson: pipeline test fixtures MUST use realistic `generate_source_id`-shaped ids, not toy `h-1`, or id-scheme bugs slip through. See [[feedback_test_mock_masks_prod_failure]] (test-shape masking prod behavior).

**Fix side:** normalize `_hadith_id` is the bug — batch/single-prefix matches `src/models/hadith.py` ("hdt:bukhari-001-001") canonical convention. Fix = don't re-prepend corpus when source_id is already corpus-prefixed (or strip/normalize). NOT folded into the main#139 test PR (worker-logic change, out of a test-only PR's scope) — the harness reproduces current behavior as an honest baseline. Related: data-pipeline arch (relocated to the noorinalabs-isnad-ingest-platform repo memory, #740).

**Status 2026-06-11:** FILED as **ig#63** and routed to Tomás Carvalho (ingest persona, child-repo rule) to fix in normalize, guarded by his #136 chain test. Don't re-file. A SECOND, sibling bug came out of the same contract-coordination — **da#77**: the BATCH loader `src/graph/load_edges.py _APPEARS_IN_QUERY` puts `hadith_number_in_book` INSIDE the MERGE pattern, so Neo4j aborts the load on a null hadith_number (every scraped hadith pre-da#72). The STREAMING path is already null-safe (ingest `_build_edge_cypher`: MERGE-on-(hadith,collection)-pair + `SET … = coalesce(...)`, property never in the MERGE key) — verified by running the main#139 harness with a null-hadith_number row (DLQ 0, edge created, null prop unset). So da#77's batch fix CONVERGES TO the streaming contract; main#139's assertion needs no change. Routed to Kwesi.
