# Memory — Project state

<!-- Tier 2 (loads on demand — see session-start Step 2.5). One line per
     memory; full detail in each linked note file in THIS directory.
     Do NOT auto-inject this file at session start (that re-adds the whole
     always-loaded index the #1016 two-tier split removed). -->

<!-- ARCHIVED 2026-08-17 (#1466): [Narrator choke-points enrich] moved to
     archive/project_narrator_chokepoints_enrich.md — cold tier: still
     git-tracked and grep-able, no longer index-loaded or budget-counted.
     Rationale: the program it tracks COMPLETED on prod 2026-07-17
     (deploy#610 + #611 both closed) and Phase 10 is noorinalabs-main-only,
     so it is history rather than live state. At 52,024 B it was the largest
     note in the corpus (3.6x the soft ceiling) and had been decay-flagged
     for several waves. The still-live operational detail it carried is not
     orphaned: cypher-shell / graph-ops gotchas are in
     [[reference_graph_ops_cypher_shell]]. Read the archived file directly
     for the full cutover changelog. -->

- [Ontology system](project_ontology_system.md) — two-layer model: curate-semantic (/ontology-rebuild + checksums) + generate-structural (ontology_gen + aggregate); librarian surfaces both; lifecycle integrated by #862; Hook 15 ADVISORY since #857. Structural llms.txt now leads with a PageRank "Hub files" view (main#1002).
- [Vector index deferred](project_vector_index_deferred.md) — token-eff Move #10 (prose vector index) DEFERRED-by-design 2026-07-19; trigger unmet (grep=6ms, MEMORY.md 98/132 & shrinking; Anthropic dropped RAG; egress cost). Revisit only on named tripwires. main#986.
- [Bootstrap repo](project_bootstrap_repo.md) — separate repo to dogfood the team/workflow/ontology pattern for reuse across projects.
- [Backup/restore/logrotate gap](project_backup_restore_logrotate_gap.md) — backups NEVER ran (timer uninstalled stg+prod); user-postgres/audit_log uncovered; restore never rehearsed; docker logs unbounded. deploy#558/#559/#560/#561.
- [restore-verify manifest fix](project_restore_verify_manifest.md) — content-manifest instrument SHIPPED (#687/PR#688) + a #613-class real-host race FIXED (#690/PR#692); both hosts backed up, stg+prod restore-verify **VERIFIED (rc=0)**. #609 items 1–4 satisfied; item-5 owner sign-off + #610/#611 separate owner-approval gates remain. Detail (SHAs, run IDs, the pg_isready→TCP-probe fix) in-file.
- [bleach ReDoS standing item](project_bleach_redos_standing_item.md) — GHSA-g75f-g53v-794x no fix + bleach EOL 2026-06-05; per-repo --ignore-vuln stays; revisit each wave; close only when kaggle dropped. main#703.
- [Implementor-label convention](project_implementor_label_convention.md) — FIRSTNAME_LASTNAME reinstated #907/PR#908 + tool apply_implementor_labels.py (wave-wrapup 6.5); branch-first/commit-author-fallback; bulk label-apply via REST not GraphQL (5000-pt limit). 949 issues backfilled.
- [Semantic embedder parity gap](project_semantic_embedder_parity.md) — prod+stg API on hashing vs corpus on MiniLM → 200-with-garbage; stg-gate NOT valid for semantic until fixed. deploy#523.
- [Donor-readiness wave (deferred)](project_donor_readiness_wave.md) — narrator-centric demo polish; **MOVED to P10 opener** (was P9; demo better on the re-cut clean graph — see [[project_phase9_data_quality]]). Scope: da#317/ig#1166/deploy#523/da#318 + visual pass.
- [Phase 9 — Data Quality plan](project_phase9_data_quality.md) — **owner-approved 2026-07-17; NOT yet kicked off.** Tracker main#977, cutover milestone main#978. 22 issues → wave-25 (narrator disambig: da#248/346/347/352/431/439/444) + wave-26 (parse recovery+name quality: da#366/373/397/398/424/427/298/299/300/301/295/446/380) + re-run cutover milestone (owner-gated, precond=W25+W26 merged) + wave-27 (ig#1185 consumer, da#443 rijāl source-acq SPIKE). Upstream-before-expensive-stage ordering. Donor-readiness→P10.
- [Phase 9 close plan](project_phase9_close_plan.md) — **owner decisions 2026-07-22:** wave-27 (meta #1067) = pre-cutover data-quality gaters (da#397/#398/#454) + hardening ride-along (#940/#1047/#1050); the P9.2 cutover (#978) is a SEPARATE owner-gated session; downstream (ig#1185/da#443) + tooling debt → P10. Refines [[project_phase9_data_quality]] (W25/26 DONE).
