---
name: feedback_reviewer_brief_techdebt
description: "Reviewer spawn briefs MUST instruct the mandatory TechDebt: attestation line, or the merge gate blocks every PR wave-wide."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: d8acc7c0-91ac-412b-b312-da38817b1614
---

Every reviewer spawn brief MUST tell the reviewer to put a literal `TechDebt:` attestation line in the verdict comment header (right after `RequestOrReplied:`): `TechDebt: none` when no untracked non-blocking debt, or `TechDebt: #N, #N` after FILING tech-debt-labeled issues for genuine findings. The merge gate (Hook 4 / charter § Comment-Based Reviews) blocks `gh pr merge` on ANY verdict missing this line — "BLOCKED: PR #N has review(s) missing the mandatory TechDebt: attestation line."

**Why:** In P5W5 the pre-compaction reviewer briefs omitted this instruction, so all ~38 Approved verdicts across ~19 ready PRs lacked the line → the entire merge pass was blocked. Root cause was the orchestrator brief, not reviewer negligence (the same omission appeared in my own first Kavitha/Kwesi briefs until corrected).

**How to apply:**
- Bake the four-line header into every reviewer brief: `Requestor:`/`Requestee:`/`RequestOrReplied:`/`TechDebt:` (see the spawn-brief template fields). Pair with [[feedback_techdebt_literal_line_not_section]] (line-start literal, not a `## Tech Debt` section) and [[feedback_hook4_regex_prose_false_match]] (don't repeat the `Field: Value` shape in prose).
- Remediation when verdicts already lack it: EDIT each verdict comment in place (PATCH, not a new comment — [[feedback_verdict_amendment_edit_not_append]]), inserting the line after `RequestOrReplied:`. Read the prose first: file issues only for genuine deferrable findings; attest `none` for praise / already-tracked refs (e.g. ig#1034) / observations the reviewer explicitly judged "acceptable as-is / degrades safely / documented." Heuristic keyword flags ("non-blocking", "follow-up", "risk") massively over-count — read before filing.
- All review comments are authored by the same gh principal, so the orchestrator can PATCH them; preserve the reviewer's text verbatim and only insert the attestation line.
