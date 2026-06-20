---
name: feedback_projectv2_field_option
description: Adding an option to a Projects v2 single-select field (e.g. the Wave field) is orchestrator-doable via GraphQL updateProjectV2Field — do NOT file it as an owner-only action.
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 7e042acd-06d6-4813-a40c-4eac8f291ea2
---

Adding a new option to a GitHub Projects v2 **single-select field** (e.g. adding a `P4W1` option to the board's `Wave` field on project 2) is **orchestrator-doable**, not an owner-only action. I have the `project` scope (confirmed by the wave-kickoff Step 3 auth audit), and the change is mechanical.

Mechanism: GraphQL `updateProjectV2Field` mutation with `singleSelectOptions`. **Gotcha:** the mutation REPLACES the full option list — you must pass every existing option (name/color/description) PLUS the new one in the same call, or the existing options are wiped. Read the current options first (`gh project field-list 2 --owner noorinalabs`), then re-send them all + the addition.

**Why:** P4W1 wrapup, I filed "add P4W1 Wave option" as an owner-action item purely because the replace-whole-list gotcha made it feel risky. The owner pushed back ("I'm sure you've been able to do this in the past") — correct. Risk of a mechanical-but-fiddly API call is not a reason to route work to the owner; it's a reason to handle the full-list-preserve carefully.

**How to apply:** Board field-schema edits (single-select option adds, field renames) go on the orchestrator's plate. Only the board-schema operations the `project` scope genuinely can't do — or that need an owner policy call — should land on an owner-action list. Read-back-verify the option stuck (`gh project field-list`) per the [[feedback_gh_pr_edit_silent_noop]] silent-no-op family.
