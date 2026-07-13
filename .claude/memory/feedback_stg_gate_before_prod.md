---
name: feedback_stg_gate_before_prod
description: "Owner 2026-07-01: staging is a validated GATE before prod. Prod only ever changes as the promotion of a stg change verified-good; after a prod change, check stg/prod parity. General course of all environment changes."
metadata:
  node_type: memory
  type: feedback
---

**Owner directive (2026-07-01, wave-22 prod-window authorization).** The general course of all environment changes:

1. **stg is a gate.** Every change lands on **staging first** and is **validated there** before it can go to prod.
2. **Prod change ⇐ verified stg change only.** A prod change is *only* the result of a stg change that has been verified good. Never make a prod change that is disconnected from a corresponding, validated stg change.
3. **stg may lead prod.** stg can change without prod changing (stg is allowed to be ahead). The asymmetry is one-directional: stg-ahead-of-prod is fine; prod-ahead-of-stg or prod-diverged-from-stg is not.
4. **Parity check on every prod change.** When prod *does* change, explicitly check stg and prod for **parity** afterward (same artifacts/images/data-state/config), and record the result.

**Why:** prod's #723 re-validation had previously FAILED with prod in a state disconnected from the validated stg state (matn-as-narrator pollution da#253, semantic search ig#1148, 50-result cap) — history in the retired `project_prod_loaded_quality_broken` memory (git history; #723 CLOSED 2026-07-05 with all 4 criteria prod-verified at exact stg parity). Treating stg as the authoritative pre-prod gate prevents shipping prod a state that was never proven good on stg.

**How to apply:** For any prod deploy / data reload / cutover (e.g. the deploy#470 embed cutover, corpus reloads): (a) apply + validate on stg first; (b) promote to prod only after stg validation passes; (c) run a stg⇄prod parity check post-promotion and record it. This supersedes any "reload prod directly" shortcut. Fold the parity check into the prod-window runbook. Relates to [[feedback_honest_audit_over_conclusion_claim]] (validate against artifact, not conclusion).

**Prod-rollout mechanics (from the 2026-06-30 audit-log relocation, retained):** `promote.yml`'s final "Trigger prod VPS rollout" step is **BROKEN — fails every time**; after promote retags the images, run `deploy-prod.yml` manually (`user_service_tag` / `api_frontend_tag` = `prod-<sha>`) and approve its production gate. Also for orientation: the audit log lives in **user-service Postgres** (`audit_log` table, `/api/v1/audit`, AdminUserDep RBAC) since 2026-06-30 — NOT in Neo4j (22 legacy graph nodes were migrated with id+created_at preserved, then deleted; isnad-graph is a pure consumer via `src/api/audit_client.py`).
