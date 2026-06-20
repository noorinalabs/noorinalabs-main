---
name: feedback_hook4_regex_prose_false_match
description: "Avoid literal `Field: Value` strings in review-comment prose — Hook 4's first-match regex grabs them as the verdict's structured-field, mis-classifying the verdict"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 02cdc334-fbe1-4680-8b6b-975c55fd3a44
---

In review-comment prose, NEVER reproduce the literal `Requestor: <name>` / `Requestee: <name>` / `RequestOrReplied: <value>` / `TechDebt: <value>` pattern, even inside an inline-code span or describing an absence. Hook 4's first-match regex scans the comment top-to-bottom and grabs the FIRST occurrence as the verdict's structured field, regardless of surrounding context.

**Why:** Hook 4 (validate_pr_review.py in the noorinalabs-main repo) parses verdict-comment structured fields with a first-match regex. When prose contains the literal `Requestor:` (e.g., "the PR body lacks the `Requestor: / Requestee: / RequestOrReplied: New / TechDebt: none` trailer"), the regex captures everything from `Requestor:` to the next newline as the Requestor field value — yielding `Requestor="/ Requestee: / RequestOrReplied: New / TechDebt: none"` instead of the intended `Requestor: Lucas Ferreira` from the trailer. The hook then mis-classifies the verdict's author, the 2-reviewer-approved gate doesn't register the approval, and merge blocks until the comment is PATCHed.

**Past incidents:** P3W11 PR #337 (my review) — orchestrator had to PATCH the comment to break the regex match. Same pattern bit Wanjiku on PR #509 earlier the same day. Both went to the orchestrator's manual fix-up cycle.

**How to apply:** In any text I author that may be parsed by Hook 4 (PR review comments, PR bodies, PR descriptions, follow-up comments), describe the structured-field block in non-literal form:

- INSTEAD OF: `lacks the \`Requestor: / Requestee: / RequestOrReplied: / TechDebt: none\` bare-line block`
- USE: `lacks the bare-line Requestor/Requestee/status/TechDebt block` (slash-separated, no colon-value pairs)
- OR: `lacks the trailer structured-fields block (the four bare lines for reviewer, author, status, and tech-debt status)`

Only the ACTUAL trailer at the bottom of the comment should contain the literal `Field: Value` form. If I need to quote the exact form for a teammate, do it in plain English description or wrap each field name without the colon (e.g., backtick the field name alone: ``the `Requestor` line``). Related: [[feedback_techdebt_literal_line_not_section]] (TechDebt placement); [[feedback_validate_pr_review_approved]] (RequestOrReplied value); [[feedback_spawn_brief_requestor]] (Requestor field assignment).

**Charter-promotion candidate:** the parallel incident with Wanjiku on #509 confirms this is a recurring shape, not a one-off. A hook-level fix (require structured-fields block as the LAST lines of the comment, or scan bottom-up, or require all four adjacent lines as a group) would prevent the whole class. Worth a follow-up issue on the noorinalabs-main hooks if not already filed — orchestrator may have it under their task #34.
