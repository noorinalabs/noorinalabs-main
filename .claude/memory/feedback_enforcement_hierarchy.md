---
name: feedback_enforcement_hierarchy
description: For any new behavior the team should follow, prefer automated enforcement (hook) over invokable tooling (skill) over written rule (charter). Charter-only rules decay.
type: feedback
originSessionId: bfc8466f-74c1-4625-bdb4-26a9cc1f0262
promotion_target: none
promotion_threshold:
  retro_citations: 3
referenced_in_retros: ['W7', 'W8', 'P2W9']
status: enforced-elsewhere
superseded_by: "implicit in CLAUDE.md § Ontology + .claude/team/charter/hooks.md § Hook Authorship Requirements; first concrete enforcement instance is Hook 15 (enforce_librarian_consulted, 2026-04-19)"
---
When introducing a new team behavior, evaluate enforcement options in this order:

1. **Hook** — automatic, fires every time, no discipline required
2. **Skill** — invokable tool that does the right thing for you
3. **Charter update** — written rule, requires team discipline

Use the **first** option that's technically feasible. Do not skip to a lower tier just because it's easier to author.

**Why:** Charter rules without enforcement decay. P2W7 retro caught 5 PRs merged with zero reviews despite the charter requiring 2 reviewers — the rule existed for waves before the `validate_pr_review.py` hook was written. Same pattern with CI: "CI must be green before merge" has been in the charter since Phase 2 Wave 1, but waves keep merging with red pre-existing CI (security-audit CVE in isnad-graph, test_migrate_users ModuleNotFoundError in user-service). Steven's quality bar is being eroded by drift.

**How to apply:**
- When proposing a new rule, ask "can a hook do this?" before writing charter prose
- When the user reports a recurring quality issue, default to building a hook unless impossible
- Skill is the right tier when the action requires judgment (e.g., `/wave-retro` writes a retro — can't be a hook)
- Charter is the right tier when the rule is about *intent* or *structure* that no automation can verify (e.g., "Program Director coordinates across teams")
- If you fall back to a lower tier, state the technical reason in the proposal so the user can challenge it
