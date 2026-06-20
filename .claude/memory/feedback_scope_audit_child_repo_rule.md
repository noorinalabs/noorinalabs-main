---
name: feedback_scope_audit_child_repo_rule
description: "A board-assigned issue's owner label can be a stale pre-scoping tag; if a scope audit shows the work belongs in a child repo, scope-stop and report — the child-repo implementer rule reassigns it, don't silently retarget or implement."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: d8a5fc5c-6b55-468a-b0a0-23817f47074f
---

When handed an issue to implement, run a scope audit BEFORE creating any worktree/branch/PR: read the issue body (use `--json`; plain `gh issue view` can 422 on projects-classic), then verify against the actual repo structure where the code would live. A tracking/follow-up issue filed in the **parent** repo (e.g. `noorinalabs-main`) for work that targets a **child** repo's subsystem does NOT mean the code goes in the parent — confirm the true home from the body + the child repo's existing structure.

If the work belongs in a child repo, two things flip and BOTH are owner/lead calls, not implementer defaults:
1. **Implementer identity** — the [[feedback_child_repo_implementer_rule]] kicks in: child-repo PRs come from that child's own roster, so an audit that relocates the work to a child repo can re-route it away from you to a child-repo persona.
2. **The board's owner label may be stale** — it can be a pre-scoping tag set under the old (wrong-repo) assumption. Don't treat a `*_LASTNAME` label as canonical assignment once scope has moved.

**Why:** P3W13 main#136 (pipeline worker integration scenarios) 2026-05-31. Brief presumed it might be a main-repo item with me (Aisha) as implementer. Audit showed: main has no pipeline workers; the real harness lives in `noorinalabs-isnad-ingest-platform/tests/integration/`; blockers #105–#108 were all CLOSED (gate lifted); and substantial coverage already existed (don't double-build) with a precise gap (Kafka-topic-driven worker E2E + MinIO→dedup, vs. existing direct-loader/fake-store tests). I scope-stopped and reported A–D instead of retargeting. Lead confirmed: filed child issue ingest-platform#55, kept main#136 as the cross-repo meta-tracker, and routed implementation to a child-repo persona (Tomás) under the child-repo rule — the board's AINO label on #136 was a stale pre-scoping tag. The audit itself was the deliverable; it unblocked correct routing.

**How to apply:** On any implement brief, before touching code: (a) confirm the issue's true target repo from body + structure, not the repo it was filed in; (b) check whether blockers/dependencies named in the body have since closed (state goes stale — [[feedback_refresh_before_status_claim]]); (c) inventory existing coverage so you propose only the genuine gap, not a rebuild; (d) if the true home is a child repo, STOP and report to the lead with the child-repo-rule implications + a scope-cut proposal — let them file the child issue and route the implementer. Sibling to [[feedback_check_accepted_adr_before_spawn]] and [[feedback_verify_diagnosis_before_delegating]] (same verify-before-delegating family; this one's axis is repo-home + assignment-routing). Pairs with [[feedback_honest_audit_over_conclusion_claim]] for the carry-forward/inventory discipline.
