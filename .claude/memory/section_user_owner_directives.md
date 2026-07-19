# Memory — User & owner directives

<!-- Tier 2 (loads on demand — see session-start Step 2.5). One line per
     memory; full detail in each linked note file in THIS directory.
     Do NOT auto-inject this file at session start (that re-adds the whole
     always-loaded index the #1016 two-tier split removed). -->

- [User profile](user_steven.md) — Steven French, owner; autonomous execution, charter compliance, hook enforcement, memory reliability.
- [IaC over one-offs](feedback_iac_over_oneoffs.md) — Owner 2026-07-07: repeatable data loads/transforms/infra behind GH Actions+IaC, not box one-offs; Neo4j graph ops need a NEW deploy workflow (cypher-shell in neo4j container; db-migrate.yml is PG-only, da has no image).
- [Prefer correct over expedient (no users)](feedback_prefer_correct_over_expedient.md) — Owner 2026-06-12: pre-launch, UI/visual regression not a hard constraint; do the right fix.
- [Full local⇄CI hook parity + no-force](feedback_local_ci_parity_no_force.md) — Owner 2026-06-14: pre-commit/push MUST mirror COMPLETE CI tooling; never push a failing check. main#684.
- [MVP prod-autonomy delegation](feedback_mvp_prod_autonomy_delegation.md) — Owner 2026-07-01: orchestrator MAY run OWNER-RUN prod reload + self-approve prod gates, backup waived, WHILE MVP; revert to owner-run+backup once data is satisfactory. stg-gate still binding.
- [stg is a validated gate before prod](feedback_stg_gate_before_prod.md) — Owner 2026-07-01: prod changes ONLY as promotion of a verified-good stg change; parity check after every prod change; stg may lead prod. Also: promote.yml VPS-trigger step BROKEN (run deploy-prod.yml manually); audit log lives in user-service Postgres since 06-30.
- [Brand is "Noorina Labs" (two words)](feedback_brand_noorina_labs.md) — camel-case "NoorinALabs" WRONG in prose; lowercase slug stays; cspell now enforces (dict entry removed). main#792.
