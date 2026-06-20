---
name: feedback_prefer_correct_over_expedient
description: "Owner 2026-06-12: no users yet → UI/visual 'regression' is NOT a hard constraint; prefer the RIGHT, more complex fix now over an expedient inline/keep-as-is workaround. Don't auto-defer the architecturally-correct change just because it has app-wide visual blast radius."
metadata:
  node_type: memory
  type: feedback
  originSessionId: 090bf6d5-0d19-47c9-9b85-67bfff1c5396
---

**Owner directive (2026-06-12, P4W4).** When a task's "no visual regression" acceptance criterion collides with doing the architecturally-correct thing, the owner's standing preference is: **do the right, more complex thing now — the product has no users yet, so a visual change is acceptable** (it must still be *intentional and correct*, not an accidental break). Expedient workarounds that keep a known-wrong pattern in place to avoid touching more files are the wrong call.

**Why:** triggered by [[project_ds_theme_color_utilities_noop]] — ig#981 inline-style migration. The app's Tailwind build emits ZERO atomic color utility rules because the DS ships color tokens to `:root` (DS#104), not into Tailwind `@theme`, so `bg-card`/`text-foreground`/`border-border` are silent no-ops. I'd scoped #981 conservatively (keep color inline, defer the `@theme` bridge as a follow-up) precisely to honor no-regression. Owner overrode: "no UI regression is probably the untenable part, but we don't have users yet, so that's fine! I would prefer to do the right, more complex thing now instead of something expedient." → we implemented the `@theme` bridge in-wave (activating ~30 inert files, fixing latent no-ops) then migrated on top.

**How to apply:**
- Don't reflexively defer/shrink a change because it has cross-file visual blast radius or trips a no-regression AC. Weigh correctness first; surface the right-but-bigger option to the owner rather than silently picking the expedient one.
- Visual changes are acceptable **while pre-launch** — but still verify they're the *intended* render (light + dark), not accidental breakage. This is a pre-launch posture; revisit once there ARE users (then regression-avoidance reasserts).
- Companion to [[feedback_security_guard_inline_not_followup]] (don't punt a real fix to a follow-up issue when it should be inline) and [[feedback_runtime_gate_scoping]] (what genuinely can't be done at PR-time).
