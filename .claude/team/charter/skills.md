# Skills

This file defines the charter rules that govern skill invocation, composition, and wave-lifecycle discipline. For skill authorship itself, see individual skill directories under `.claude/skills/`.

## Wave Lifecycle — Open-Item Audit <!-- promotion-target: hook -->

Before any skill or agent claims a wave, workstream, or milestone is **"concluded"**, **"complete"**, or **"done"**, it MUST run a cross-repo open-item count for the active wave scope. The claim is only permitted if one of two conditions holds:

1. **Zero open items** for the wave label across every relevant repo, OR
2. An **explicit carry-forward list** naming every non-closed item with destination (next wave, backlog, deferred indefinitely).

### When this applies

- `/wave-wrapup` before emitting its summary.
- `/handoff` before any "concluded" narrative in the handoff body.
- `/wave-retro` before the "Wave Theme — complete" statement.
- Any skill that reports wave status.
- Manually-authored retros and wave summaries in feedback_log.md.

### Audit command

The canonical audit is:

```bash
for repo in noorinalabs-main noorinalabs-isnad-graph noorinalabs-user-service noorinalabs-deploy noorinalabs-design-system noorinalabs-landing-page noorinalabs-data-acquisition noorinalabs-isnad-ingest-platform; do
  COUNT=$(gh issue list --repo "noorinalabs/$repo" --state open --label "p2-wave-${N}" --json number --jq 'length' 2>/dev/null)
  [ -n "$COUNT" ] && [ "$COUNT" != "0" ] && echo "$repo: $COUNT open"
done
```

If any repo returns non-zero, either address those items before closing the wave or list them explicitly as carry-forward with destination.

### Rationale

During P2W9 wrapup, the orchestrator claimed "wave-9 parent-repo workstream concluded" in a handoff when ~22 items remained open across child repos (8 in deploy, 5 in isnad-graph, 3 in ingest-platform, plus others). The owner had to prompt "have we completed all PRs and open issues for wave 9?" to surface the truth. A narrative "concluded" claim carries forward as next-session assumption — the next orchestrator reads the handoff and assumes work is done that isn't.

Derived from Phase 2 Wave 9 retrospective, 2026-04-22.

## Promotion-target: hook

This rule is proposed for promotion to a hook-enforced check (hook > skill > charter per the enforcement-hierarchy principle). A wave-audit hook would scan handoff/retro/wrapup skill outputs for "concluded"/"done"/"complete" phrasing and block the skill's completion unless the open-item count is zero or an explicit carry-forward list is present. Tracked as a followup issue.
