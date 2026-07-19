# Memory — Reference

<!-- Tier 2 (loads on demand — see session-start Step 2.5). One line per
     memory; full detail in each linked note file in THIS directory.
     Do NOT auto-inject this file at session start (that re-adds the whole
     always-loaded index the #1016 two-tier split removed). -->

- [graph-ops cypher-shell gotchas](reference_graph_ops_cypher_shell.md) — cypher-shell 5.x removed `:auto`; migrate verify must sample a RESOLVING hadith_id; prune run-order guard (migrate raw→0 BEFORE prune); misspelled property = uniform NULL never error; load_all is MERGE-only (shrink needs companion prune); loader rc=1 = validation HARNESS not data (multi-statement Cypher da#319); Chain data lives in node PROPERTIES (connected_chains=0 by design).
- [B2 pipeline publish key](reference_pipeline_b2_publish_key.md) — **B2 cap CLEARED 07-09; full load ~$0.01.** PIPELINE_B2_* = 2 same-named keys (GH secret READ-ONLY, local ~/.zshenv WRITE); read-only-key write 401 misreads as "failed to create bucket"; "no objects found" is a lie; full-object-path rclone probe is VACUOUS; **RCLONE_DUMP=auth leaks creds past GH masking into a PUBLIC log**. deploy#555/#550/#556.
- [SSH topology](reference_ssh_topology.md) — mental model, key-to-user mapping, owner pitfalls; verify w/ whoami each session.
