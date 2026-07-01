---
name: feedback_mvp_prod_autonomy_delegation
description: "Owner 2026-07-01 (MVP phase): orchestrator MAY run the OWNER-RUN prod data reload + self-approve prod GH Environment gates without owner involvement; backup waived until data is 'satisfactory'. Revert to owner-run + mandatory backup once data matters."
metadata:
  node_type: memory
  type: feedback
---

**Owner directive (2026-07-01, wave-22 prod window).** For the current **MVP phase**, the owner is removing themselves from the prod-operation loop to increase velocity:

1. **Prod data reload delegated to the orchestrator.** The `prod-data-reload-723.md` runbook is marked `[OWNER-RUN / DESTRUCTIVE]`, but the owner has explicitly authorized the orchestrator to **run the reload itself** (re-run → load stg → validate → load prod). This overrides the runbook's "do not let automation run them" header **for now**.
2. **Backup waived until data is satisfactory.** "We really don't need to back anything up until we have some satisfactory data, and I don't think we are close to that at this moment." So the runbook's "non-negotiable backup FIRST" step may be **skipped** while the corpus is still being fixed (prod data is currently broken/polluted anyway — nothing worth preserving). Re-instate mandatory backup once a validated-good corpus exists.
3. **Self-approve prod gates.** The orchestrator MAY approve the `production` GH Environment gate on `promote.yml` (and equivalent prod-deploy approvals) **without owner involvement**, "until I say otherwise."

**Sunset condition (explicit).** "One day when our project is no longer just an MVP and the data is important, I would want it to be owner-run." So when the corpus reaches satisfactory/validated quality (≈ #723 criteria genuinely pass and data is treated as important), **revert**: prod reload becomes owner-run again, backup becomes mandatory again, and prod gates require owner approval again. Watch for the owner signaling this transition (or proactively flag it once data is good).

**Still binding even under this delegation:** the stg-gate discipline ([[feedback_stg_gate_before_prod]]) — changes land + validate on **stg first**, prod changes only as promotion of a verified-good stg change, and a stg⇄prod parity check follows every prod change. Delegation removes the owner from *executing/approving*, NOT the requirement to validate on stg before prod. Prod SSH target must still verify as prod (178.156.214.225), never stg. Relates to [[project_prod_loaded_quality_broken]], [[project_p7_narrator_pollution_resolve_fixes]].
