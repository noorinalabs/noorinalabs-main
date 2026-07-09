---
name: feedback_hook4_regex_prose_false_match
description: "Avoid literal `Field: Value` strings in review-comment prose. The hook that bites is `validate_review_comment_format` (unanchored whole-body FIRST-match `re.search`), NOT Hook 4 — Hook 4 was scoped by #511 to the trailer block with last-match-wins. The rule is right; the mechanism in this file's title is wrong."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 02cdc334-fbe1-4680-8b6b-975c55fd3a44
---

In review-comment prose, NEVER reproduce the literal `Requestor: <name>` / `Requestee: <name>` / `RequestOrReplied: <value>` / `TechDebt: <value>` pattern. **The rule stands. The mechanism this file's title gives for it is wrong, and was corrected 2026-07-09 (main#933 review, Wanjiku Mwangi).**

## Which hook actually bites (verified against source, 2026-07-09)

**Not Hook 4.** `validate_pr_review._extract_charter_field` was scoped by **#511**: it calls `_strip_code_regions` (blanking fenced *and* inline code), then `_trailer_block_substring` (keeping only text after the **last** sole `---` line), then matches **last-match-wins** within that scope. Its own docstring names the incidents below as the patterns #511 fixed. **When a sole `---` exists, Hook 4 cannot see prose above it at all.** It remains prose-sensitive only for the shape appearing *inside* the trailer, and in the legacy no-separator fallback.

**`validate_review_comment_format` is the one that bites.** Its probe is a bare `re.search(r"\*{0,2}Requestor:\*{0,2}\s*(.+)", body)` over the **whole body** — first match, no `^`, no `MULTILINE`, no code-stripping, no trailer narrowing. A sentence four screens above your trailer is what blocks the `gh pr comment`.

**Two hooks, opposite scoping disciplines, one rule.** Writing the rule down against the forgiving hook is how it nearly became superstition: the orchestrator repeated *"Hook 4 first-matches your prose"* to four reviewers on 2026-07-09, each of whom could have read `validate_pr_review.py` and found it false. **A rule with a false mechanism gets applied in the wrong place, or dropped as folklore the first time someone checks.**

**Past incidents (all PRE-#511, all against the then-unscoped Hook 4):** P3W11 PR #337 — orchestrator had to PATCH the comment to break the regex match. Same pattern bit Wanjiku on PR #509 earlier the same day. This file's own closing paragraph proposed the fix — *"require the structured-fields block as the LAST lines of the comment, or scan bottom-up"* — and **#511 shipped exactly that.** The memory was never updated. **The proposal landing is what made the memory wrong**, and nothing in the file could tell you so.

**How to apply:** In any text I author that may be parsed by Hook 4 (PR review comments, PR bodies, PR descriptions, follow-up comments), describe the structured-field block in non-literal form:

- INSTEAD OF: `lacks the \`Requestor: / Requestee: / RequestOrReplied: / TechDebt: none\` bare-line block`
- USE: `lacks the bare-line Requestor/Requestee/status/TechDebt block` (slash-separated, no colon-value pairs)
- OR: `lacks the trailer structured-fields block (the four bare lines for reviewer, author, status, and tech-debt status)`

Only the ACTUAL trailer at the bottom of the comment should contain the literal `Field: Value` form. If I need to quote the exact form for a teammate, do it in plain English description or wrap each field name without the colon (e.g., backtick the field name alone: ``the `Requestor` line``). Related: [[feedback_techdebt_literal_line_not_section]] (TechDebt placement); [[feedback_validate_pr_review_approved]] (RequestOrReplied value); [[feedback_spawn_brief_requestor]] (Requestor field assignment).

**The charter-promotion candidate this file used to propose has SHIPPED.** "Require the structured-fields block as the LAST lines of the comment, or scan bottom-up" is `#511`, live in `validate_pr_review` as `_trailer_block_substring` + last-match-wins + `_strip_code_regions`. The open half is `validate_review_comment_format`'s unanchored whole-body `re.search`, tracked in main#932/#934.

**Standing lesson, larger than this file:** a memory that records a defect *and proposes its fix* becomes false the day the fix lands, and it will not tell you. Nothing in a memory file observes the code it describes. **When you land a fix, grep the memory corpus for the defect and amend it in the same PR** — otherwise the memory outlives the bug and starts teaching a mechanism that no longer exists. This file taught one for roughly two months. Sibling: [[feedback_dep_resolution_invalidates]].
