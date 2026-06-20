---
name: feedback_safety_direction_over_ux_friction
description: "When a hook/gate can't produce a clean fix, prefer HARD BLOCK with manual-edit diagnostic over allow-with-log. Block-with-broken-suggestion is bad in the safe direction (operator doesn't run); allow-with-log is bad in the unsafe direction (silent gate bypass)."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 4a42b118-bbc8-48d1-ba53-16b4689915f5
---

When the protection a hook exists to provide cannot be cleanly automated for an edge case, default to HARD BLOCK with operator-readable diagnostic. Never `allow_with_log` (or "we detected it but can't fix it so we'll let it through"). The directional asymmetry:

- **Block with broken/no suggestion**: bad in SAFE direction. Operator doesn't run the dangerous command, sees the diagnostic, edits manually or asks for help. Worst case: UX friction + maintainer support load.
- **Allow with log**: bad in UNSAFE direction. Operator runs the command and the protected failure mode fires (silent prod write, data wipe, etc.). The log message is post-hoc evidence of the bypass — it doesn't prevent it.

The hook's purpose is "prevent <bad thing>." Allow-with-log says "we know it's about to happen, but we can't stop it cleanly, so we won't" — which is the gate failing closed against itself.

**Why:** P3W11 PR #494 (#478 follow-up) — I initially built control-flow case to `allow_with_log` because the splice would produce invalid shell ("error on the side of NOT mangling"). User correction: that's the wrong axis — the broken-suggestion side IS bad but in the safe direction (operator doesn't run), allow-with-log is bad in the unsafe direction (silent bypass of the very protection, #420 prod-data-wipe class). Failure direction > UX friction for this class of hook.

**How to apply:**
- When implementing a hook that protects against a specific dangerous behavior, ask: "if my rewriter/fixer can't handle this edge case cleanly, which direction does the operator end up in?"
  - Block path: operator stops, reads diagnostic, asks for help or edits manually. Annoying but safe.
  - Allow path: operator's command runs as-is, including the dangerous behavior the hook was meant to catch. Convenient but unsafe.
- Choose block. The diagnostic should name what was detected, why it can't be auto-fixed, and concrete alternatives (e.g. inline-env form + pull-out form).
- This is sibling to [[feedback_runtime_gate_scoping]] (PR-time correctness ≠ runtime correctness) and [[feedback_security_guard_inline_not_followup]] (runtime guard needs to be inline, not a followup issue) — all three are "safety failure-direction > developer convenience" patterns.
- Counter-case: pure UX hints (e.g. style suggestions) where there's no underlying safety failure mode — those CAN be allow-with-log because the worst case is just "ugly code shipped." Reserve block-on-can't-fix for hooks that protect against material harm.
