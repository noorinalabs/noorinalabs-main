---
name: feedback_verdict_count_hook_regex
description: "Orchestrator pre-spawn verdict-count queries must match Hook 4's actual parser regex (accepts `**Requestor:**` bold-markdown AND bare `Requestor:`) — a brittle jq `startswith(\"Requestor:\")` misses bold-form verdicts and triggers stale-state respawns"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 4a42b118-bbc8-48d1-ba53-16b4689915f5
---

When auditing PR verdict comments to decide whether to spawn a second reviewer, the orchestrator MUST count verdicts using the **same regex Hook 4 (`validate_pr_review.py`) actually uses**, not a brittle prefix-string match.

Hook 4's `_extract_charter_field` regex (per `.claude/hooks/validate_pr_review.py:254-268`):

```python
r"\*{0,2}" + field_name + r":\*{0,2}"
```

That accepts BOTH:
- Bare: `Requestor: Wanjiku Mwangi`
- Bold-markdown: `**Requestor:** Wanjiku Mwangi`
- Single-asterisk: `*Requestor:* Wanjiku Mwangi`

A jq query like `select(.body | startswith("Requestor:"))` matches only the bare form. Reviewers who use the bold-markdown convention get silently uncounted by the orchestrator's audit, even though Hook 4 itself counts them correctly.

**Failure mode:** Orchestrator concludes "1-of-2, need second reviewer," respawns a second-reviewer task. The reviewer then refreshes at origin and reports "stop, already 2-of-2." Round-trip cost: ~5-8 min of agent work, plus the cognitive overhead of recovery.

P3W11 instance (2026-05-18 ~01:00Z): Wanjiku had posted Approved on PR #459 at 04:12:50Z (prior session) using `**Requestor:** Wanjiku Mwangi` bold-markdown. My orchestrator jq query skipped it. Re-spawned a Wanjiku review task; she refreshed at origin, surfaced the stale state, did NOT post a duplicate. Clean recovery thanks to her `feedback_stale_inbox_manager` + `feedback_refresh_before_status_claim` discipline — but the round-trip was avoidable at the orchestrator side.

**How to apply:**

1. When counting verdicts, use a regex that matches Hook 4's acceptance:
   ```bash
   gh api repos/.../issues/<N>/comments \
     --jq '[.[] | select(.body | test("^\\*{0,2}Requestor:\\*{0,2}\\s")) | (.body | capture("^\\*{0,2}Requestor:\\*{0,2}\\s+(?<r>[^\\n]+)") | .r)] | unique | length'
   ```
   This counts distinct Requestor names regardless of bold/bare formatting.

2. Or, even simpler: read each "Requestor:"-bearing comment fully and let the reviewer logic itself decide — don't try to pre-filter.

3. Pre-spawn checklist for reviewer tasks: BEFORE composing the brief, run the Hook 4-equivalent count. If already at 2-of-2 Approved (distinct Requestors), skip the spawn — the gate is clear.

Sibling rule to [[feedback_refresh_before_status_claim]] (which is the reviewer-side discipline). This is the orchestrator-side mirror.
