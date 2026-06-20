---
name: feedback_runtime_gate_scoping
description: When an infra fix's validation requires production-only state (compose stack, real creds, target env), don't conflate the runtime gate with the PR acceptance criterion. Deliver unit-mechanic correctness in the PR, document what CANNOT be validated pre-prod, add a post-merge Test Plan step naming the gate.
type: feedback
originSessionId: 2e011116-89b1-4ac2-b2fc-1d5649d609c7
promotion_target: charter
promotion_threshold:
  retro_citations: 3
status: active
---
When an infra/SRE fix has a validation gate that requires production-only state — a running compose stack, real B2/AWS/etc. credentials, the target box itself — **the runtime gate is NOT the PR acceptance criterion.** Conflating the two leads to one of three failure modes, all bad:

- **Hold the PR until prod is provisioned** → blocks wave wrap on downstream cutover work; fix sits on the shelf rotting while drift accumulates
- **Fake the proof with synthetic data** → masks the real cutover-gate signal; future "did it work?" question is unanswerable; reviewer trust degrades
- **Merge without naming the gap** → operator hits the gate at cutover with no warning; cutover-gate budget gets burned on rediscovery

**Correct shape (canonical per Bereket 2026-04-28 endorsement of deploy#121 PR #187):**

1. **Deliver unit-mechanic correctness in the PR.** Validate everything that CAN be tested at the unit/script/integration layer in stg or local — bug fixes, env-var loading, namespace setup, OnFailure hooks, idempotent install steps, etc. Provide concrete journal/log/file evidence in the PR body.
2. **Document what CANNOT be validated pre-prod, explicitly.** Name the gate, name the missing prerequisite, name the operational event that will fire it. A "What I CANNOT validate" section in the PR body works.
3. **Add a post-merge Test Plan step naming the gate.** Item should be checkable by whoever runs the cutover (operator, or another agent post-cutover), citing the gating doc (e.g. "Per main#212: one successful end-to-end backup within 24h of first compose-up before DNS-flip → confirm artifact at `b2://<bucket>/daily/<date>/`").

**Why:** Holds the PR-merge bar at "is the code correct?" (verifiable now) and the cutover-gate bar at "did it produce the operational outcome?" (verifiable post-cutover, by someone with prod-side access). Two distinct judgments, two distinct moments, both clearly scoped.

**How to apply:**

- Recognize the pattern early: any fix where the issue body references a cutover-gate, DR posture, "first successful X within Y hours", or any criterion with the word "production" in it.
- In the PR body, structure as: Bug table → New artifacts → Live validation evidence (what you DID test) → "What I CANNOT validate from this PR" → Test plan with explicit post-merge gate item.
- In your team-lead notification, lead with "cutover-gate proof DEFERRED" and explain why with one sentence — don't bury it. Frame as "PR delivers unit-mechanic correctness needed for that gate to be reachable; gate itself fires post-merge as part of cutover."
- This is reusable across: backup services, DR rehearsals, secret rotations against live services, DNS-cutover PRs, any infra change where prod-side state is the proof point.

**Counter-signals that the pattern doesn't apply:**

- If the validation only needs a running compose stack (NOT prod-specific creds or DNS), spin one up in stg and validate end-to-end. Don't punt to operational gates if a fuller test environment is available.
- If the missing prerequisite is something YOU can stand up (test bucket, ephemeral VPS, mock service), do that first. Punting should be the last resort, not the first.
- If the gate is "first 24h" and prod cutover is more than 24h away, the punt is fine. If cutover is tonight, hold the PR open with a "blocked on stg compose stack standing up" comment instead of merging blind.
