---
name: project_restore_verify_manifest
description: stg backup PROVEN restorable 2026-07-15 (graph + isnad byte-identical to live); restore-verify rc=1 was a CONFIRMED instrument false-negative (mutable user-postgres tables compared vs live). Owner chose "fix instrument first" → deploy#687 (dump-time content manifest) blocks #609 before prod gate.
metadata:
  type: project
---

**2026-07-15 — the restore-verify instrument fix (deploy#684) unblocked, then surfaced a second, deeper defect.**

Chain of events this session:
- deploy#684 (invalid histogram Cypher, Neo4j 5.x implicit-grouping, same class as #606/#607) + deploy#685 (restore-verify.yml didn't self-sync the host checkout) fixed in **PR#686** (merged `afb53cc`). Red→green calibration proven in CI: self-test 4p/3f on broken queries → 8p/0f fixed, incl. a reltype-DIFFER case added at review. Reviewers Lucas Ferreira + Nurul Hakim, re-confirmed at green head 780eb12.
- With the histogram bug gone, the stg restore-verify ([run 29378240071](https://github.com/noorinalabs/noorinalabs-deploy/actions/runs/29378240071)) ran to completion for the FIRST time and **proved the stg backup is good**: graph (2,728,165 nodes / 13,528,869 rels / narrator fp / label+reltype hist) and isnad (hadiths 125,256 + md5) all byte-identical to live; users 3=3, oauth 3=3, audit_log 0=0, alembic 0043 all MATCH.
- It exited **rc=1** on `sessions` (89 vs 87) + `users md5` — a **CONFIRMED false-negative**, not a backup defect. Live query: backup dumped 2026-07-14 03:19:13Z; a single login at 05:58:28Z created ~2 sessions + updated that user's `last_login_at`/`updated_at` (row count stayed 3). Benign drift, zero data loss.

**Root cause / the durable lesson:** `restore_verify.sh compare()` exact-matches the restored artifact against **current live**. Valid for immutable/reconstructible stores (graph, isnad hadiths) but structurally WRONG for the mutable user-service store (`sessions`, `users.last_login`, append-only `audit_log`) — a point-in-time backup can never equal live once auth activity happens, so it can NEVER return VERIFIED for a real backup. Converges with pre-existing tech-debt **deploy#662** (user-postgres = weakest, uncalibrated comparator) — but #662's suggested "add full-row md5 vs live" would make the drift false-negative WORSE.

**Owner decision 2026-07-15:** "fix instrument first" (over proceeding straight to the graph cutover, even though #610 doesn't touch user-postgres). → **deploy#687** (Prod Cutover milestone, blocks #609): backup.sh records a per-table **content manifest at dump time**; restore_verify compares restored==manifest for the user store (keep live cross-check only for immutable graph/hadiths); mandatory red-first calibration for EVERY user-pg comparator + a benign-drift-must-PASS case; table-set check. Absorbs #662. Same bidirectional-calibration discipline as [[feedback_drop_gate_bidirectional_ab]] / [[feedback_silent_zero_is_not_a_measurement]] / [[feedback_query_builder_test_needs_real_engine]].

**#609 status after this:** item-1 (real backup both hosts) ✅; item-2 (B2 verified) ✅; item-3 (restore rehearsed green w/ content assertions) — graph/isnad ✅ PROVEN, user-postgres BLOCKED on #687's honest verdict; item-4 (comparator shown red-first) ✅ (self-test); item-5 (owner sign-off) ⏳. Prod restore-verify (owner's first prod approval, production env gate) comes AFTER #687 merges + stg re-verify green. See [[project_backup_restore_logrotate_gap]], [[project_narrator_chokepoints_enrich]].

---

**2026-07-16 UPDATE — instrument fix landed, a real-host race (#690) found+fixed, both hosts backed up, stg re-verified, prod restore-verify IN FLIGHT.**

- **#687 → PR#688 MERGED (`fc3219f`)**: backup.sh writes a dump-time content manifest (restore-derived per-table count+md5); restore_verify compares restored==manifest for user-pg, restored==live only for immutable graph/hadiths; bidirectional self-test (drop a table → red). Absorbed #662.
- **deploy#690 → PR#692 MERGED (`c77a7d4`)** — a **#613-class real-host race** surfaced ONLY on the real host under backup-time load: `generate_content_manifest()` restores the user-pg dump into a throwaway `postgres:16-alpine`, and the readiness gate used `pg_isready`, which reports ready against the entrypoint's **socket-only bootstrap server** (`listen_addresses=''`) BEFORE `CREATE DATABASE "$POSTGRES_DB"` runs → `pg_restore -d user_service` died `FATAL: database "user_service" does not exist`. **Fix:** deterministic TCP `SELECT 1` against the target DB (bootstrap server refuses TCP, so TCP-reachable ⟹ real server up ⟹ DB created). Stayed CI-green through the bug because the manifest step is fail-safe (never fails the backup) AND the end-to-end test asserts `rc==0` → "two correct decisions compose a blind spot" → durable catch is a **source guard** (`scripts/tests/test_content_manifest_readiness.py`, 4 tests incl. red-first calibration). Definitive proof is the real-host `Content manifest: OK`.
- **Both hosts now backed up with manifest OK.** prod fresh backup `Result=success`: users=10, oauth=9, sessions=52, audit_log=22, alembic=1; `_content_manifest-20260717-005725.txt`; neo4j offline-dump stop recovered 20s.
- **stg restore-verify [run 29545059570] = success** (both jobs) → item-3 GREEN on stg.
- **prod restore-verify [run 29546273189] IN FLIGHT** (environment=prod approved 2026-07-16; read-only, throwaway stack, guarded from live prod #640/#642). **RESUME ANCHOR: `gh run view 29546273189 -R noorinalabs/noorinalabs-deploy`.** success ⟹ item-3 green on prod ⟹ #609 ready for owner sign-off (item-5). Full state pinned as a comment on deploy#609.
- **Scope guard (owner):** #609 is the backup gate ONLY. #610 (prod graph cutover) + #611 (prod flag op) remain SEPARATE owner-approval gates — do NOT start without explicit go.
