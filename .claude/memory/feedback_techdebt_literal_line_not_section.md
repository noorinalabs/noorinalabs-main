---
name: feedback_techdebt_literal_line_not_section
description: "Hook 4 parses verdict comments for a literal single-line \"TechDebt: none\" or \"TechDebt: #N, #M\" — a \"## Tech Debt\" markdown section with prose does NOT satisfy the gate, even if the prose says \"None added\". Place the literal line in the structured-fields block at the top of the verdict comment, alongside Requestor/Requestee/RequestOrReplied."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 7bef55d7-053c-4d9a-8b6c-969061a60e9c
---

Hook 4 (`validate_pr_review`) parses verdict comments for a literal single-line:

```
TechDebt: none
```

or

```
TechDebt: #15, #16
```

A `## Tech Debt` markdown section with prose (e.g., "**None added.**") does **NOT** satisfy the gate, even if substantively correct. Merge gets blocked with: `Reviewers without TechDebt line: <name>`.

**Why:** Hook 4 uses a regex anchored to `^TechDebt:` at line-start with no markdown decoration; it does not parse markdown sections. The literal-line discipline is the post-PR-422 charter convention (`agents.md § Orchestrator checklist when spawned a reviewer` item #4 verbatim template). Mateo's #912 verdict passed because his line 4 is literally `TechDebt: none`; mine on #918 failed because I had only the prose section.

**How to apply:** Every verdict comment's structured-fields block at the top MUST be:

```
**Requestor:** <reviewer name>
**Requestee:** <PR author name>
**RequestOrReplied:** Approved
TechDebt: none
```

(or `TechDebt: #N, #M` if items filed). The richer `## Tech Debt` markdown section with attestation prose is fine to include later in the body — but the literal line is the gate. Place it in the structured-fields block, not buried mid-body.

**Recovery shape per [[feedback_verdict_amendment_edit_not_append]]:** EDIT the original comment via REST PATCH (`gh api -X PATCH .../issues/comments/<id> --input <(jq ...)` per [[feedback_gh_pr_edit_silent_noop]]) — never append a new amendment comment. Hook 4 re-scans every Approved comment; a new amendment does NOT supersede.

P3W11 PR #918 instance 2026-05-17 — comment `4470174670` blocked Ingrid's merge of the urllib3 wave-blocker until literal line added.
