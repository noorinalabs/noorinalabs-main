# Skills

This file defines the charter rules that govern skill invocation, composition, and wave-lifecycle discipline. For skill authorship itself, see individual skill directories under `.claude/skills/`.

<!-- Promoted from memory: feedback_honest_audit_over_conclusion_claim.md (P3W5 retro 2026-05-06). Already enforced via Hook 17 (validate_wave_audit) per hooks.md L169 — the dedicated provenance entry there is now mirrored to the source memory's superseded_by. -->

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

## Cross-repo-status.json upsert pattern <!-- promotion-target: hook -->

Any skill that writes top-level `wave_{N}_*` keys to `cross-repo-status.json` MUST use the shared upsert helper at `.claude/lib/upsert_status_keys.py`. Raw `jq ... > tmp && mv` (and equivalent full-file rewrites — `jq | sponge`, `python -c 'json.dump(...)'` round-trips, etc.) are **banned** for top-level `wave_{N}_*` key writes.

### Why

The file mixes shapes deliberately: top-level `wave_{N}_*` bookkeeping keys are compact single-liners (zero-churn diffs), while older `wave_{N}_scope` blocks are pretty-indented (human-readable). A naive jq round-trip reformats every compact line to jq's default pretty form, doubling file length and producing a 500+ line cosmetic diff per wave. PR #270 (W4 retro) and PR #276 (W5) both flagged this, and #278 closed the acute symptom by writing the helper. #332 closed a follow-up bug where the helper inserted new keys inside multi-line array values; the post-fix helper is multi-line-aware.

### Contract

`upsert_top_level_key(text, key, value)`:
- **Replace-in-place** when `key` exists at top level → zero churn (identical input produces identical output).
- **Insert-near-sibling** when `key` does not exist → +1 line per new key, placed after the most-recent `wave_{N}_*` sibling (or before the closing `}`).
- **JSON-validates** the input before the rewrite AND the output after the rewrite. Malformed input or output raises rather than silently writing corrupted state.
- **Multi-line-aware** (post-#332): skips past multi-line array / object sibling values, never inserts inside them.

### Canonical invocation

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
python3 "$REPO_ROOT/.claude/lib/upsert_status_keys.py" \
  "$REPO_ROOT/cross-repo-status.json" \
  "wave_{N}_scope_reconciled_at=\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"" \
  "wave_{N}_active=true"
```

Each `key=value` argument's VALUE must be a self-contained JSON literal (string with quotes / number / bool / array / object). The helper's own docstring documents the full invocation surface.

### Current consumers

- `/wave-scope` Step 13 — writes `wave_{M}_scope_reconciled_at`, `wave_{M}_repos_in_scope`, `wave_{M}_meta_issue`, `wave_{M}_scope`, optional `wave_{M}_scope_reconciliation_note`.
- `/wave-wrapup` Step 10.5 — writes `wave_{M}_final_pr_count`, `wave_{M}_changes_requested_cycles`, `wave_{M}_top_concentration_pct`.
- Future skills writing top-level `wave_{N}_*` keys → MUST use the helper; do NOT reinvent.

### Promotion provenance

Memory `feedback_enforcement_hierarchy.md` (hook > skill > charter). Acute fix landed in PR #288 closing #278; broader codification carried forward as #292 → this charter section + the helper promotion from `.claude/skills/wave-scope/` to `.claude/lib/` (multi-consumer triggered the shared-lib promotion per the issue body's item 3 decision rule).

### Hook-class enforcement decision

Per #292 item 4 — should a `validate_cross_repo_status_format` PostToolUse hook fire on Edit/Write of `cross-repo-status.json` and block writes that expand line count >N% relative to additions OR reformat compact-inline to pretty? **Decision: DEFER.** Rationale: zero charter-rule violations observed across W6–W9 since the helper landed. The two current consumers (`/wave-scope`, `/wave-wrapup`) both invoke the helper correctly. Per `feedback_enforcement_hierarchy.md`, charter-only-without-violations does NOT require hook promotion; promote-on-first-violation is the established trigger. Re-evaluate if any future skill OR manual edit produces a non-helper-mediated write that expands the file >2x its prior line count.
