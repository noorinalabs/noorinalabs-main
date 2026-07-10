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

Charter `pull-requests.md` names the field, and **`check_comment_reviews` asks `_extract_charter_field` for `RequestOrReplied` — nothing else does.** `_extract_charter_field` itself reads *whatever name you pass it*: the name is a parameter, `re.escape(field_name)`. So `_extract_charter_field("Verdict", body)` happily returns `'Approved'` and tells you nothing. **The binding to the charter field lives at the call site, not in the helper** — which matters because the natural way to "confirm" a repaired near-miss comment is to call the helper with whatever label the comment carries, and it will answer.

**`Verdict:` is not a field any hook asks for.** A comment reading `Verdict: Approved` contributes **zero** to the two-reviewer threshold.

Two placement rules are as load-bearing as the name:

- `_trailer_block_substring` returns only the text **after the LAST line that is a sole `---`**. Correctly-spelled fields sitting *above* a later separator are invisible. Put the trailer block last.
- `_strip_code_regions` blanks fenced and inline code before matching, and `_extract_charter_field` is **last-match-wins** within the trailer.

**Never reproduce the `Field: Value` shape in review prose — but know which hook bites.** The *counting* hook (`validate_pr_review`) cannot see prose above the trailer at all: when a sole `---` exists, everything before it is sliced away, and within the trailer it is last-match-wins. It is prose-sensitive only for a shape appearing *inside* the trailer, or in the legacy no-separator fallback. The hook that actually blocks you for a sentence written four screens above the trailer is **`validate_review_comment_format`**, whose `Requestor` probe is an unanchored, unscoped, whole-body `re.search` — **first** match, no `^`, no `MULTILINE`, no trailer narrowing. Two hooks, opposite scoping disciplines. See [[feedback_hook4_regex_prose_false_match]], whose title names the wrong one.

**The regression (2026-07-09, wave 24):** orchestrator spawn briefs dictated `Verdict:`. The whole team complied. **Nine `Approved` comments across five PRs parsed as nothing.** main#930 blocked as `0/2 required peer reviews` with three approvals sitting on it. PRs merged 07-06 used the correct field, so the drift was one session old and invisible for its whole life. Repaired by REST-PATCHing a canonical trailer onto each comment (append after a `---`, remove nothing) and re-verifying with `validate_pr_review.check_comment_reviews` **imported from the hook module**, not a hand-rolled regex — the same mistake one level up would have "confirmed" the fix.

**Why it was silent, which is the real defect:** `validate_review_comment_format.py` sees `Requestor:` + `Requestee:` present and `RequestOrReplied:` absent and **returns None — allow**. Its `is_comment_command` matches only `gh pr comment`, so REST-posted verdicts (the GraphQL-rate-limit fallback) never reach it at all; and `extract_comment_body` does not read `--body-file` — **the form charter `agents.md` mandates**, and the one used ~438 times across `.claude/` — nor a quoted `-F body=@"…"`, nor any `$VAR` in a path, so a matched command yields an empty body and fails open again.

**Do not quote a count of these paths.** It was "three" when written; reviewing main#934 turned up `--body-file`, quoted `@path`, and unexpanded `$VAR`; the corpus replay then turned up two more (the segment splitter never split on newlines; `URL=$(gh api -X POST …)` was swallowed by the env-prefix stripper). **A count restated in a second artifact drifts from the artifact that owns it.** Say "several, enumerated in main#932/#934" and let those issues own the number.

No signal to the reviewer, no signal to the orchestrator, and the shortfall surfaces hours later at merge time **attributed to the reviewers**.

This is the measurement family one level up: not a probe that cannot return nonzero, but **a review that cannot be counted, which is indistinguishable from no review at all.** See [[feedback_silent_zero_is_not_a_measurement]].

Hook 4's `_extract_charter_field` regex (cite the **symbol**, never a line range — the range in the first draft of this memory pointed at `:254-268`, which is a shell-word scanner; the function had moved to `:604` before the memory was even reviewed. **The rot is the argument.**):

```python
rf"\*{{0,2}}{re.escape(field_name)}:\*{{0,2}}\s*(.+)"
```

That accepts BOTH:
- Bare: `Requestor: Wanjiku Mwangi`
- Bold-markdown: `**Requestor:** Wanjiku Mwangi`
- Single-asterisk: `*Requestor:* Wanjiku Mwangi`

A jq query like `select(.body | startswith("Requestor:"))` matches only the bare form. Reviewers who use the bold-markdown convention get silently uncounted by the orchestrator's audit, even though Hook 4 itself counts them correctly.

**Failure mode:** Orchestrator concludes "1-of-2, need second reviewer," respawns a second-reviewer task. The reviewer then refreshes at origin and reports "stop, already 2-of-2." Round-trip cost: ~5-8 min of agent work, plus the cognitive overhead of recovery.

P3W11 instance (2026-05-18 ~01:00Z): Wanjiku had posted Approved on PR #459 at 04:12:50Z (prior session) using `**Requestor:** Wanjiku Mwangi` bold-markdown. My orchestrator jq query skipped it. Re-spawned a Wanjiku review task; she refreshed at origin, surfaced the stale state, did NOT post a duplicate. Clean recovery thanks to her `feedback_stale_inbox_manager` + `feedback_refresh_before_status_claim` discipline — but the round-trip was avoidable at the orchestrator side.

## The `jq` remedy this memory used to prescribe was wrong, in the unsafe direction (corrected 2026-07-09, main#933 review)

The first draft's step 1 was a hand-rolled `jq` count. **Aino Virtanen ran it and it fails two independent ways**, both found by executing it rather than reading it:

- **`jq`'s `^` is string-anchored, not line-anchored** (`jq`'s `m` flag is dotall, not multiline). Against a comment shaped the way *this very memory mandates* — prose first, trailer last after a sole `---` — it returns **0** where the hook module returns **1**. It only ever appeared to work because the trailers it was tested on happened to sit at the top of the body.
- **It never filters on the verdict value at all.** It counts distinct authors of any comment carrying a `Requestor` line — requests, replies and blocking verdicts alike. On one `ChangesRequested` plus one `Reply`, with **zero** approvals, it prints **`2`**.

It also skips all three of the hook's scoping steps: no code-region stripping, no trailer-block narrowing, no `Approved`-only filter.

**The direction of the error is what makes this a rule and not a nit.** The memory's stated failure mode was over-spawning a redundant reviewer — a five-minute round trip. The remedy's actual failure mode is **over-counting**: read "2", conclude the gate is clear, skip the second reviewer, merge with fewer reviews than the charter requires *believing you have them*. On 2026-07-09 the orchestrator held exactly that belief about main#933 and main#936; both carried **zero** review comments, and only Hook 4's refusal at merge time surfaced it.

**The memory contained its own correct answer and declined to use it.** Its own regression paragraph records that the repair was verified by importing `check_comment_reviews` **from the hook module**, "not a hand-rolled regex — the same mistake one level up would have confirmed the fix." Step 1 *was* that hand-rolled regex.

**How to apply:**

1. **Count by importing the hook, never by re-implementing it.** It is the only count that cannot drift from what the hook does, because it *is* what the hook does:
   ```python
   import sys; sys.path.insert(0, ".claude/hooks")
   from validate_pr_review import _extract_charter_field, _is_approved
   approvers = {
       r for c in comments
       if (r := _extract_charter_field("Requestor", c["body"]))
       and _is_approved(_extract_charter_field("RequestOrReplied", c["body"]) or "")
   }
   ```
   Any `jq`/`grep` reimplementation must reproduce code-stripping, trailer-narrowing, last-match-wins **and** the `Approved`-only filter. Four chances to be silently wrong. Do not take them.

2. Or, even simpler: read each `Requestor`-bearing comment fully and let the reviewer logic itself decide — don't try to pre-filter.

3. Pre-spawn checklist for reviewer tasks: BEFORE composing the brief, run the hook-imported count. If already at 2-of-2 Approved (distinct Requestors), skip the spawn — the gate is clear. **A count you cannot trace to the hook is not evidence the gate is clear.**

4. **An approval that predates the head is not an approval.** The hook counts *comments*, not shas — it will happily count a verdict written against code that no longer exists. Freshness is the orchestrator's job, and no hook does it for you.

Sibling rule to [[feedback_refresh_before_status_claim]] (which is the reviewer-side discipline). This is the orchestrator-side mirror.
