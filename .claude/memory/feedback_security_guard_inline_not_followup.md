---
name: feedback_security_guard_inline_not_followup
description: When reviewing a PR whose security model depends on a runtime guard (env check, scheme restriction, startup assertion), require the guard in the PR itself — do not accept "we'll file a TechDebt followup for it." Offering the followup is fine; relying on it is wrong.
type: feedback
originSessionId: 43b60daf-62e0-4fa1-b083-aef94bac4edf
promotion_target: charter
promotion_threshold:
  retro_citations: 3
status: superseded
superseded_by: charter:pull-requests.md § Security Guards Belong Inline, Not in a Followup
superseded_at: 2026-05-06
---
When a PR introduces a config knob, override, or flag whose misuse path leads to credential theft, data exfil, or silent protocol downgrade, the safeguard must ship in the same PR. Filing a TechDebt followup is a legitimate review artifact — but it is not a substitute for the guard; it is a paper trail in case the guard ever regresses.

**Why:** Confirmed 2026-04-21 on user-service PR #77 (`OAUTH_PROVIDER_BASE_URL_OVERRIDE`). I filed followup #78 proposing a prod-environment guard + HTTPS-outside-test requirement, and requested Changes. Mateo landed both inline in fixup `1104104`; #78 closed same day. Team-lead's verdict: "shipping the env-gate + HTTPS requirement inline rather than deferring to #78 was the right call." Deferring would have left a window where a prod misconfig could exfil client_secret via `/token` POSTs with no backstop.

**How to apply:**
- On a security review, when the threat model requires a runtime guard, post **Changes Requested** and ask for the guard inline, even if a followup issue exists. The followup is a tracking artifact, not a fix.
- File the followup *before* the review comment (so `TechDebt: #N` can reference it) — but frame the ask as "resolve inline, close the followup with the fixup SHA."
- Applies especially to: environment gates (prod/staging refuse-to-boot), scheme whitelists (`{http,https}`), HTTPS-required-outside-test, startup assertions, URL rewriters, auth bypass flags. Docstring warnings are never sufficient for these.
- Does NOT apply to: defense-in-depth hardening, log-level tuning, doc updates, refactors that don't change the threat surface — those are legitimate followups.
