---
name: feedback_verdict_count_hook_regex
description: "The verdict field Hook 4 parses is `RequestOrReplied:`, never `Verdict:`, and it must sit after the LAST sole `---` line in the body. Orchestrator verdict-count queries must match the hook's real regex (bold `**Requestor:**` and bare both parse) — and the hooks fail OPEN on every near-miss, so a wrong field name costs zero reviews silently"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 4a42b118-bbc8-48d1-ba53-16b4689915f5
---

When auditing PR verdict comments to decide whether to spawn a second reviewer, the orchestrator MUST count verdicts using the **same regex Hook 4 (`validate_pr_review.py`) actually uses**, not a brittle prefix-string match.

## The field is `RequestOrReplied:`. It is never `Verdict:`. (2026-07-09, main#932)

Charter `pull-requests.md:14` names the field, and `_extract_charter_field` reads exactly that name. **`Verdict:` is not a field any hook knows.** A comment reading `Verdict: Approved` contributes **zero** to the two-reviewer threshold.

Two placement rules are as load-bearing as the name:

- `_trailer_block_substring` returns only the text **after the LAST line that is a sole `---`**. Correctly-spelled fields sitting *above* a later separator are invisible. Put the trailer block last.
- `_strip_code_regions` blanks fenced and inline code before matching, and `_extract_charter_field` is **last-match-wins** within the trailer. Never reproduce the `Field: Value` shape in review prose.

**The regression (2026-07-09, wave 24):** orchestrator spawn briefs dictated `Verdict:`. The whole team complied. **Nine `Approved` comments across five PRs parsed as nothing.** main#930 blocked as `0/2 required peer reviews` with three approvals sitting on it. PRs merged 07-06 used the correct field, so the drift was one session old and invisible for its whole life. Repaired by REST-PATCHing a canonical trailer onto each comment (append after a `---`, remove nothing) and re-verifying with `validate_pr_review.check_comment_reviews` **imported from the hook module**, not a hand-rolled regex — the same mistake one level up would have "confirmed" the fix.

**Why it was silent, which is the real defect:** `validate_review_comment_format.py` sees `Requestor:` + `Requestee:` present and `RequestOrReplied:` absent and **returns None — allow**. Its `is_comment_command` matches only `gh pr comment`, so REST-posted verdicts (the GraphQL-rate-limit fallback) never reach it at all; and `extract_comment_body` reads only `--body`/heredoc, so even a matched `gh api … --input body.json` yields an empty body and fails open a second time. Three fail-open paths, no signal to the reviewer, no signal to the orchestrator, and the shortfall surfaces hours later at merge time **attributed to the reviewers**. Fix tracked in main#932.

This is the measurement family one level up: not a probe that cannot return nonzero, but **a review that cannot be counted, which is indistinguishable from no review at all.** See [[feedback_silent_zero_is_not_a_measurement]].

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
