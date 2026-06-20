---
name: feedback_bundle_fixup_instructions
description: "When sending fixup instructions to an implementer mid-PR, bundle ALL items into ONE message. Serial messages risk dropping items if the implementer starts the fixup between sends."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 774bef93-36af-4505-8130-2f6cfa5f5162
---

When the orchestrator sends fixup instructions to an in-flight implementer (e.g., after a reviewer surfaces nits or a new finding lands during review), bundle ALL fixup items into ONE message. Do NOT send serial messages with additional items after the first.

**Why:** Implementers process inbound messages as discrete units. Once they start applying fixup-message-1, message-2 will arrive but may not be merged-into the in-flight commit. The implementer-side discipline is the canonical-shape ack from charter `agents.md § Pre-Spawn State Check + Crossed-Message Race Protocol` — they verify-at-origin and ack rather than re-pushing. That protocol works perfectly, but it requires the orchestrator to re-send the missed item, costing a round-trip + a new commit.

**How to apply:**

- Before sending a fixup message, ask: "Could there be another reviewer / another item / another nit that should be in this same message?" If yes, wait until those land.
- When a new item surfaces AFTER you've sent fixup-message-1, send it as fixup-message-2 with the explicit framing "if your in-flight fixup already covers X you can ignore this — verify-at-origin first" rather than as a fresh demand.
- Acceptable case for serial messages: when the second item is genuinely orthogonal (different file, different reviewer angle, different verdict cycle) AND the first fixup is fully landed and CI-green.

**Companion to:**
- `[[feedback_throttle_takeover]]` — orchestrator-class spawn-discipline family (use the agent you have)
- charter `agents.md § Pre-Spawn State Check + Crossed-Message Race Protocol` — implementer-side response shape for when this discipline fails

**Origin:** PR #422 implementation 2026-05-13. Sent Aino "bundle bold+nits" message-1, then "bundle half-up rounding" message-2 after Wanjiku's verdict landed. Aino had already amended a8d5d28→db5fff7 with the half-up by the time message-2 reached her. She ack'd via canonical race-protocol shape rather than re-pushing. Charter Protocol worked — but message-2 was redundant + cost one round-trip. If I'd waited for Wanjiku before sending message-1, both items would have been in one bundle.
