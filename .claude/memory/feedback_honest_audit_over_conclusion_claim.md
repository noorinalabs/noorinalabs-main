---
name: feedback_honest_audit_over_conclusion_claim
description: Never claim a wave or workstream is "concluded" without first running a cross-repo open-item count; zero items open OR an explicit carry-forward list is required
type: feedback
originSessionId: 43b60daf-62e0-4fa1-b083-aef94bac4edf
promotion_target: charter
promotion_threshold:
  retro_citations: 3
status: enforced-elsewhere
superseded_by: charter:skills.md § Wave Lifecycle — Open-Item Audit (also enforced via charter:hooks.md § Hook 17 validate_wave_audit)
superseded_at: 2026-05-06
---
Before asserting that a wave, workstream, or milestone is "concluded", "complete", or "done", run a cross-repo open-item count. Either:

1. The count is **zero** for the relevant label/scope, OR
2. Provide an **explicit carry-forward list** naming every non-closed item and where it's going (wave-N+1, backlog, deferred indefinitely).

**Why:** I claimed "wave-9 parent-repo workstream fully concluded" in a handoff when in fact ~22 items remained open across child repos (8 in deploy, 5 in isnad-graph, 3 in ingest-platform, plus others). Owner had to prompt "have we completed all PRs and open issues for wave 9?" to surface the truth. The handoff entry would have been the record of the session; the false "concluded" claim would have been the pickup assumption next session.

**How to apply:**

- Before writing a handoff section or retro conclusion, run cross-repo gh queries for open items under the scope:
  ```bash
  for repo in noorinalabs-main <children>; do
    gh issue list --repo "noorinalabs/$repo" --state open --label "p2-wave-N" --json number --jq 'length'
    gh pr list --repo "noorinalabs/$repo" --state open --json number --jq 'length'
  done
  ```
- If ANY non-zero, the handoff/retro must name the specific items as carry-forward, not bury them in narrative.
- Distinguish clearly between:
  - **Workstream concluded** (everything that was planned shipped).
  - **Scope concluded** (the specific chunk driven tonight shipped; broader wave may still have items).
  - **Session concluded** (this session's active work parked; others' sessions may still have work).
- Err toward conservative phrasing. "Parent-repo tooling sweep concluded; 22 items carry forward to wave-10" is honest. "Wave-9 concluded" is not honest if that's false.

**Related memories:**
- `feedback_verify_diagnosis_before_delegating.md` — ground-truth check before action.
- `.claude/skills/file-bug/SKILL.md` § "Pass A — search-before-filing" — survey existing state before adding. (Was the `feedback_search_before_filing` memory; promoted into the skill, which lists it as one of its 3 consolidated sources.)

**Origin:** Surfaced 2026-04-22 during wave-9 wrapup. Added after owner correction.
