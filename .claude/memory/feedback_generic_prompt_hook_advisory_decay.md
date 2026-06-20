---
name: feedback_generic_prompt_hook_advisory_decay
description: "suggest_generic_prompt fires per .claude/ edit but is never actioned — advisory systemMessage, no enforcement/state/throttle. Move to batched wave checkpoint (main#716)."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 76123576-c792-441f-9c53-bc0685c9c321
---

`suggest_generic_prompt.py` (PostToolUse Edit/Write) emits a `[Generic Prompt Suggestion]` `{"systemMessage"}` nudging the agent to genericize `.claude/` artifacts into `2real-team-framework/generic_prompts/`. It **exits 0 always, writes no state, has no throttle, and never creates the file**. Proven inert: `generic_prompts/` holds only 2 files from the Apr-11 manual bootstrap — zero added since across every wave. Owner flagged 2026-06-19.

**Why:** a soft model-nudge with no closing loop decays — the harness treats injected `systemMessage`s as non-binding background so mid-task it's correctly passed over; no state means it can't be enforced/audited; per-edit no-dedup firing trains tune-out. This is the [[feedback_enforcement_hierarchy]] pattern (suggestion without enforcement decays).

**How to apply:** don't rely on it to produce generic prompts. The real fix (main#716) = a batched, tracked checkpoint in `/wave-retro`/`/wave-wrapup` that lists changed `.claude/` artifacts lacking a generic counterpart, decided in one pass + recorded in a ledger; demote/remove the per-edit hook.
