---
name: feedback_role_class_specific_boundaries
description: When a person appears in multiple role contexts (PR reviewer vs escalation target vs advisor vs implementer), the boundary rule applies per-role-class, not per-person. Check which class you're operating in before correcting.
type: feedback
last_verified: 2026-07-27
originSessionId: 7a9193be-f4d0-4434-a33c-2c9493287b57
promotion_target: charter
promotion_threshold:
  retro_citations: 3
status: active
---
When a boundary rule is invoked ("X shouldn't be in Y"), the rule applies to a specific **role class**, not to the person's identity. Before acting on the correction, identify:

1. **Which role class is the artifact operating in?**
   - PR reviewer row → pre-merge, charter-review-boundary rules apply
   - Runbook escalation target → operational-incident, on-call-responsibility rules apply
   - Advisor/consult column in a plan → design-context, SME rules apply
   - Implementer in a PR header → code-authorship, implementer-team-roster rules apply

2. **Does the rule being invoked apply to THIS role class?**

Example (2026-04-23, W10, noorinalabs-deploy#153):
- Nadia.Boukhari flagged that she was in PR-reviewer role on #153's body — correct correction, managers-as-PR-reviewers crosses the implementer-boundary. Swapped to Anya.Kowalczyk.
- She was ALSO in the runbook escalation matrix (`docs/runbooks/user-service-alembic.md` row "alembic upgrade head fails on prod → Nadia.Boukhari (user-service manager)"). That row is operational-incident class, not PR-reviewer class — manager-as-escalation-target is the CORRECT population. Removing her from that row would have broken the actual escalation path.

The rule is not "Boukhari shouldn't appear in anything related to #153". The rule is "Boukhari shouldn't appear as PR-reviewer-of-record on an implementer's PR". Different role class → different boundary → different correct action.

Paired example from same session: Anya.Kowalczyk on the `heads`→`head` integration-test revert:
- Implementer role → Aisha.Idrissi (SRE-team ownership of deploy-side revert).
- Advisor role → Anya.Kowalczyk (alembic DAG author from US#80 — she consults Aisha but doesn't push).
- Same person (Anya) is implementer of US#80 but advisor on the dependent deploy-side PR.

**Why:** save future agents (implementer or manager) from the wrong-direction correction where they see "X flagged Y", assume Y-everywhere-means-remove, and blow away a critical operational-escalation row or advisor entry. Bereket.Tadesse flagged this as a retro primitive 2026-04-23.

**How to apply:**
1. When you receive a teammate "correct X out of Y" message, identify the role class of the current occurrence before acting.
2. If the role class matches the boundary rule, apply the correction.
3. If the role class is a different class that the rule doesn't cover, explicitly flag that you're leaving the second occurrence intact, with the role-class distinction named. Invite reviewer to push back if they want it swapped too.
4. This is the same discipline as "verify diagnosis before delegating" but applied to boundary corrections: verify role-class match before applying the boundary.

**Related memories:**
- `feedback_verify_diagnosis_before_delegating.md` — parallel discipline for delegating fixes.
- `feedback_stale_inbox_manager.md` — parallel discipline for state corrections.
- `feedback_refresh_before_status_claim.md` — parallel discipline for status assertions.

Common role-class axes observed so far:
- PR-reviewer vs runbook-escalation-target (prod incident)
- Implementer vs advisor/consult (design context)
- Manager vs implementer (role hierarchy)
- Primary vs secondary vs fallback (reviewer slate)
- Agent-session-local state vs GitHub-remote state (data authority)

If the same person-with-same-name shows up in two of these axes, apply boundary rules to each axis independently.
