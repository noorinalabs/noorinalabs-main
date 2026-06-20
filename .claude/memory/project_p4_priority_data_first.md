---
name: project_p4_priority_data_first
description: "P4 owner priority — get REAL DATA visible in the product this phase (pipeline E2E → loaded → viewable), THEN broader features + polish. Sequencing directive, not derivable from code."
metadata: 
  node_type: memory
  type: project
  originSessionId: 080813cd-f3b8-434d-974c-badf58620c96
---

**Owner directive (2026-06-10):** "I really want to see some data this phase and then we can work on broader features and polish."

Phase 4's through-line is **data visibility first**. Sequence work so real hadith data is flowing and *viewable in the running product* before investing in broader features or UI polish. This is the tie-breaker for scoping decisions: a wave/issue that gets data visible outranks a feature or polish item.

**How to apply:**
- W2 theme is **"Pipeline first light + auth account-linking"** (meta #628). Front-load the data path: main#139 (E2E run sunnah→MinIO→Kafka→graph) + actually loading to Neo4j/Postgres so it shows in the isnad-graph frontend on staging.
- P4 end-state order reflects this: #601 pipeline E2E → #602 product usable with real data → #603 admin → exit. Don't reorder polish ahead of #601/#602.
- **Fast-path option:** the keyless `sunnah_scraper` is verified producing real schema-valid data ([[feedback_stg_deploy_per_service_tag_routing]] sibling work, da#71 verification). A thin vertical slice — load the verified scraper sample into Neo4j and view it in the graph explorer — could put data on screen quickly, ahead of the full multi-source pipeline. Consider proposing this at /wave-scope 4 2.
- Sunnah API key is NOT required to start (scraper covers it); don't let the missing key (da#71) gate "seeing data."
- "Broader features + polish" = later waves (W3 product / W4 exit and beyond), not W2.
