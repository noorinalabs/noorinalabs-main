# Promotion Audit — p5-wave-5 (2026-06-19, marker-reconciliation run)

**Trigger:** pre-push `pytest-skills` steady-state failure on `main` — 2 memories classified AUTO, blocking all main pushes.

**Outcome:** 0 AUTO · 0 DECIDE · 248 KEPT · 1 SUPERSEDED · 18 ALREADY-PROMOTED.

## Reconciled (no new charter content — already encoded)
Both AUTO candidates were already fully encoded in the charter; they were flagged only because the existing sections referenced them inline (backticks) rather than via the recognized `<!-- Promoted from memory: X -->` provenance marker. Fix = add the marker + set memory `status: enforced-elsewhere`. No duplicate sections authored.

| Memory | Already encoded in | Action |
|--------|--------------------|--------|
| `feedback_refresh_before_status_claim.md` | `state-claims.md § Refresh State Before Claim` (line 170 already names it as the claim-direction primitive) | provenance marker added; memory → `enforced-elsewhere`, superseded_by that section |
| `feedback_throttle_takeover.md` | `agents.md § Throttle-Stall Recovery — Trigger Thresholds` (section opens by describing the takeover mechanic) | provenance marker added; memory → `enforced-elsewhere`, superseded_by that section |

**Note:** this is the marker-convention blind spot, not genuine missing rules — the audit's AUTO was a false-positive in substance (content present, marker absent). Verified: driver re-run = 0 AUTO; `test_smoke.py` + `test_run.py` = 25 passed.

---

# Promotion Audit — p5-wave-5 (2026-06-20, /wave-retro Step 7.5 run)

**Trigger:** P5W5 wave-retro promotion audit (canonical driver `run.py`).

**Outcome:** 0 AUTO · 0 DECIDE · 248 KEPT · 19 SUPERSEDED.

No promotions cross threshold this wave. The 19 SUPERSEDED include the two memories marker-reconciled above (`feedback_refresh_before_status_claim`, `feedback_throttle_takeover`), now correctly classified via their `<!-- Promoted from memory: X -->` markers + `enforced-elsewhere` status. All 16 skill candidates are KEPT (`promotion-target != hook`); 3 skills (board-audit, promotion-audit, wave-wrapup) already enforced via registered hooks. No charter/skill/hook artifacts emitted.
