---
name: feedback_stale_inbox_manager
description: When message propagation lags state change, a manager's view of downstream teammates can trail reality; correcting on stale view creates false churn
type: feedback
originSessionId: 7a9193be-f4d0-4434-a33c-2c9493287b57
promotion_target: charter
promotion_threshold:
  retro_citations: 3
status: active
---
**The rule:** before "correcting" a downstream teammate's state based on their latest message in your inbox, verify whether their state has moved since that message. If state is artifact-backed (PR body, issue comment, file on disk), read the artifact directly — don't infer state from message sequence alone.

**Why:** In a multi-iteration coordination cycle (W10 Contract thrash, 2026-04-23, 6 Contract revisions in ~50 min), the manager's inbox runs behind the team's actual state by 1–2 message-propagation intervals. A correcting message sent against a stale view lands at the teammate as "your manager didn't see the verification work you already did" — it costs trust, re-triggers defensive re-explanation, and creates false churn that looks like manager-driven thrash but is actually just inbox lag.

Marcia verified v5 on #815 first-pass via direct GitHub API fetch, rolled brief + memory + #68 public comment to v5, reported done. Two hours later, from stale reads of her earlier "I'm at v4" message (which predated her v5 verification), I sent her a "stop propagating v4, roll back to v5" correction. Correction was wrong — she was already at v5. She (correctly) flagged it.

**How to apply:**
- Before sending a "you're in wrong state X, move to Y" correction, re-verify the teammate's actual current state via artifact: `gh api` for comments/PRs, `Read` for files on disk, grep for version strings.
- Trust the teammate's self-reported state when they've cited a canonical URL/commit they verified — they're operating on fresher evidence than your inbox.
- When in doubt, ask "what's your current state?" rather than "roll back from X to Y."
- The verification burden shifts to the manager in high-churn cycles. "Don't paraphrase" applies to your own reads of the team, not just to relays.

**Two subtypes, same root cause** (Khoury refinement 2026-04-23):
- (a) Misreading a teammate's artifact state from a stale inbox message — the Marcia case above.
- (b) Misreading the history of directive execution from stale memory — Khoury diagnosed in herself: she routed four rounds of "post v5" directives based on a mental-model summary ("v3 stands, Boukhari needs to post v5") instead of `gh api`-verifying each time that v5 was already posted. Every "v5 is already there" reply was correct; each "please post v5" re-issuance was coordinator-side stale-state failure. Same failure class, opposite direction on the hierarchy.

State-of-execution is just another kind of state that can drift. Any time you're routing an action based on *what-has-happened*, that's a state read and needs canonical verification — not just paraphrase-of-content reads.

**Companion to** `feedback_canonical_source_via_git_show`, `feedback_verify_diagnosis_before_delegating`, and the v5/option-C Contract retro cluster. Codifies a specific manager/coordinator failure mode that existing disciplines (cite-canonical, verify-before-delegating) imply but don't explicitly name.
