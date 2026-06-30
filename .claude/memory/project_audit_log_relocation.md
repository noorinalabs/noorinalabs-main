---
name: project_audit_log_relocation
description: Audit log moved out of Neo4j into user-service Postgres audit_log table — cross-repo, shipped to stg + prod 2026-06-30.
metadata:
  type: project
---

**Audit log relocated from the isnad-graph Neo4j graph into the relational DB** (owner call: it made no sense in the graph). Store = **user-service Postgres** (`audit_log` table), not isnad-graph Postgres. Cross-repo: user-service = producer/owner, isnad-graph = consumer.

- **user-service (producer, PR#201 / closes #200):** alembic `0043_add_audit_log.py` → `audit_log` (id UUID PK gen_random_uuid; action/actor_id NOT NULL; actor_name/details NOT NULL DEFAULT ''; target_user_id nullable; created_at TIMESTAMPTZ DEFAULT now(); indexes on created_at DESC + action; NO FK, append-only). Endpoints under `/api/v1/audit` (AdminUserDep RBAC): `POST` body `{action,actor_id,actor_name?,target_user_id?,details?}`→201; `GET ?page&limit&action`→`{items,total,page,limit}` DESC.
- **isnad-graph (consumer, PR#1145 / #1140):** `src/api/audit_client.py` (httpx → `{settings.auth.user_service_url}/api/v1/audit`, forwards bearer); `src/api/routes/admin/audit.py` rewritten — write path `create_audit_entry`→`audit_client.create_audit_log` POST, read path `list_audit_logs`→user-service GET. **Zero graph writes.** Frontend shape unchanged. Only live writer is the data-purge handler (`routes/admin/data.py`).
- **Prod rollout 2026-06-30 (build sha: user-service 6bb15da, isnad-graph 20e4034):** promote→approve prod gate(s)→retag→deploy-prod.yml per service. **The promote.yml final "Trigger prod VPS rollout" step is BROKEN — fails every time; work around by running `deploy-prod.yml` manually** (user_service_tag / api_frontend_tag = prod-<sha>) and approving its production gate. Migrated the 22 pre-existing `:AUDIT_LOG` graph nodes → Postgres preserving original `id`+`created_at` (idempotent ON CONFLICT, direct SQL — NOT the POST path, which regenerates both), verified 22 rows readable through the prod admin chain (HTTP 200, total=22), THEN deleted the 22 graph nodes (deploy new code first so no purge in the gap writes a fresh orphan). Graph now 0 `:AUDIT_LOG`.
- Follow-ups: isnad-graph#1146 (stg functional-smoke CI gap — missing STG_BASE_URL/STG_USER_SERVICE_URL vars + STG_TEST_* secrets + non-admin seed user). The dev-role spike main#909 is a first-class consumer of this audit store but is PARKED for a future wave.

See [[project_prod_loaded_quality_broken]] for the separate prod graph-data thread.
