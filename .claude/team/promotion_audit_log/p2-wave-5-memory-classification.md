## Promotion Audit — wave-5 memory-classification (2026-05-05)

This is a **mid-wave classification audit** addressing main#269 (the W4-wrapup
audit follow-on). It documents the systematic frontmatter classification of all
39 `feedback_*.md` memories so future `/promotion-audit` runs surface real
AUTO/DECIDE candidates instead of returning 0/0 because every memory had
`promotion_target: none`.

The wave-5 wrapup will produce its own per-wave promotion audit log
(`wave-5.md`) at wave close. This log is the issue-269 deliverable.

## Before / after audit deltas

Re-running the deterministic classifier in `helpers.py` against
`/home/parameterization/.claude/projects/-home-parameterization-code-noorinalabs-main/memory`
+ `.claude/team/feedback_log.md`:

| Bucket | Before (W4 wrapup) | After (this PR) | Delta |
|---|---|---|---|
| AUTO | 0 | **5** | +5 |
| DECIDE | 0 | 0 | 0 |
| KEPT | 65 | 52 | -13 |
| SUPERSEDED + ALREADY-PROMOTED | 4 | **12** | +8 |
| Total candidates | 69 | 69 | unchanged |

The +8 SUPERSEDED reflects 8 memories newly tagged `status: enforced-elsewhere`
with explicit `superseded_by` references (4 hook-shipped, 3 charter-shipped, 1
skill-shipped). The +5 AUTO are charter-target memories that have already
crossed the `retro_citations >= 3` threshold and are now eligible for
auto-promotion at the next wave-retro `/promotion-audit` run.

## AUTO-PROMOTED candidates surfaced (5)

These memories are all classified `promotion_target: charter` AND have
`retro_citations >= 3` in `feedback_log.md`. They will auto-promote on the
next `/promotion-audit` run unless the wave-5 retro proposes a different shape.

| Memory | retro_citations | Charter family |
|---|---|---|
| `feedback_canonical_source_via_git_show.md` | 4 | git-discipline / canonical-source |
| `feedback_child_repo_implementer_rule.md` | 4 | spawn-discipline / roster |
| `feedback_honest_audit_over_conclusion_claim.md` | 4 | wave-wrapup discipline |
| `feedback_review_against_artifact_not_framing.md` | 4 | reviewer discipline (Pattern B) |
| `feedback_security_guard_inline_not_followup.md` | 4 | reviewer discipline / security |

## Classification summary (per-bucket)

### ALREADY-PROMOTED (4 hooks + 4 charter + 1 skill = 9)

`promotion_target` set to the actual destination tier; `status: enforced-elsewhere`
or `status: superseded` plus an explicit `superseded_by` field naming the
shipped artifact. The classifier renders these as SUPERSEDED in the audit
table.

**Hook-shipped (4):**
- `feedback_heredoc_in_git_commit.md` → `validate_commit_identity.py` (PR#248, P3W4)
- `feedback_tmp_msg_file_stale.md` → `block_stale_tmp_message_file.py` (PR#242, P3W4)
- `feedback_pr_review_comment_only.md` → `dispatcher.py` `block_gh_pr_review` + charter pull-requests
- `feedback_reviewer_techdebt_line_required.md` → `validate_pr_review.py`

**Charter-shipped (4):**
- `feedback_disable_followup_load_bearing.md` (already had frontmatter — `charter/pull-requests.md § Load-Bearing Followups`)
- `feedback_enforcement_hierarchy.md` (already had frontmatter — implicit in CLAUDE.md § Ontology + first concrete case Hook 15)
- `feedback_pattern_e_emergency_process_collapse.md` → `charter/emergency-mode.md` (P3W2 retro)
- `feedback_single_team_delegation.md` → `charter/agents.md § Single-Leader Constraint` + CLAUDE.md § Session team architecture

**Skill-shipped (1):**
- `feedback_wave_kickoff_per_repo_branches.md` → `/wave-kickoff` per-child-repo branch creation (PR#245, P3W4)

### KEEP-AS-MEMORY (4)

`promotion_target: none` — informational memories with no enforcement angle.

- `feedback_settings_permission.md` (already tagged) — user permission preference
- `feedback_repo_independence.md` (already tagged) — project context
- `feedback_self_loop_task_replay_glitch.md` — harness-level bug, no enforcement
- `feedback_agent_color_render_quirk.md` — UI quirk, no enforcement (P3W4-late)

### HOOK-CANDIDATE (4)

`promotion_target: hook` — rules that should ultimately be hook-enforced. The
classifier currently routes these to KEPT ("promotion_target=hook is not a valid
memory transition" — memories only auto-promote to charter; hook promotion is
the skill→hook step). They become eligible after a charter section + skill
scaffold are introduced for them, OR they can be lifted directly to hooks via a
DECIDE-tier issue at the wave-5 retro.

- `feedback_cross_repo_wave_ref_resolution.md` — workflow ref-resolution validator
- `feedback_gh_pr_edit_silent_noop.md` — body-after-edit verification via REST PATCH read-back
- `feedback_ruff_format_check_before_push.md` — pre-push `ruff format --check` gate
- `feedback_actionlint_needs_shellcheck.md` — pre-push shellcheck-on-PATH precondition

### SKILL-CANDIDATE (4)

`promotion_target: skill` — repeatable workflows that should fold into existing
skills (or spawn new ones).

- `feedback_pr_state_in_refresh.md` — `state` field in JSON query → fold into `/review-pr`
- `feedback_search_before_filing.md` — pre-search before file → bug-filing skill
- `feedback_wave_branch_issue_close.md` — explicit `gh issue close` → fold into `/wave-wrapup`
- `feedback_wave_planning_from_board.md` (already tagged superseded) — already shipped as `/wave-scope` (#196)

### CHARTER-CANDIDATE (16)

`promotion_target: charter` — review/spawn/audit discipline rules. 5 of these
have already crossed the `retro_citations >= 3` AUTO threshold and will land at
the next `/promotion-audit` run (see "AUTO-PROMOTED candidates surfaced" above).
The remaining 11 are at threshold-not-met and will accrue citations through
W5/W6 retros.

- `feedback_canonical_source_via_git_show.md` (4 cites — AUTO)
- `feedback_child_repo_implementer_rule.md` (4 cites — AUTO)
- `feedback_honest_audit_over_conclusion_claim.md` (4 cites — AUTO)
- `feedback_review_against_artifact_not_framing.md` (4 cites — AUTO)
- `feedback_security_guard_inline_not_followup.md` (4 cites — AUTO)
- `feedback_drift_evidence_to_existing_rationalization_issue.md` (1 cite)
- `feedback_live_trace_over_synthetic_acceptance.md` (1 cite)
- `feedback_multi_layer_gap_filing.md` (1 cite)
- `feedback_origin_over_local_for_still_has_claims.md` (2 cites)
- `feedback_pr_vs_runtime_acceptance_criteria.md` (1 cite)
- `feedback_refresh_before_acting.md` (0 cites — P3W4-late)
- `feedback_refresh_before_status_claim.md` (2 cites)
- `feedback_role_class_specific_boundaries.md` (1 cite)
- `feedback_runtime_gate_scoping.md` (1 cite)
- `feedback_stale_inbox_manager.md` (1 cite)
- `feedback_throttle_takeover.md` (0 cites — P3W4-late)
- `feedback_verify_diagnosis_before_delegating.md` (2 cites)
- `feedback_verify_third_party_integrity_claims.md` (2 cites)

(That's 18 listed; the 4 P3W4-late additions to memory after issue#269 was
filed — `agent_color_render_quirk`, `refresh_before_acting`, `throttle_takeover`,
plus the additional `wave_planning_from_board` entry — were classified
following the same heuristics.)

## Frontmatter shape applied

For every feedback memory, the frontmatter now carries:

```yaml
promotion_target: <charter|skill|hook|none>
promotion_threshold:
  retro_citations: 3
status: <active|enforced-elsewhere|superseded>
superseded_by: "<artifact reference>"   # only when status != active
```

Memory bodies were NOT modified — only frontmatter, per #269 acceptance criteria.

## Verification

Run from repo root:

```bash
python3 -c "
import sys; sys.path.insert(0, '.claude/skills/promotion-audit')
from helpers import (
    read_all_memories, read_all_charter_sections, read_all_skills,
    find_already_promoted, count_retro_citations, count_skill_invocations,
    classify_memory, classify_section, classify_skill,
)
mem='/home/parameterization/.claude/projects/-home-parameterization-code-noorinalabs-main/memory'
already=find_already_promoted('.claude/team/charter/hooks.md')
ds=[]
for m in read_all_memories(mem):
    ds.append(classify_memory(m,{'retro_citations':count_retro_citations(m,'.claude/team/feedback_log.md')},already))
for s in read_all_charter_sections('.claude/team/charter'):
    ds.append(classify_section(s,{'skill_invocations':0,'threshold':5}))
for sk in read_all_skills('.claude/skills'):
    ds.append(classify_skill(sk,{'skill_invocations':count_skill_invocations(sk.name,'.'),'threshold':5},already))
c={}
for d in ds: c[d.kind]=c.get(d.kind,0)+1
for k in sorted(c): print(f'{k}: {c[k]}')
"
```

Expected output:
```
ALREADY-PROMOTED: 1
AUTO: 5
KEPT: 52
SUPERSEDED: 11
```

## Next-wave action items

1. **Wave-5 retro** — when `/promotion-audit` runs at retro time, the 5 AUTO-tier
   memories will auto-generate charter sections via `templates/charter-section.md`
   under Aino's branch, with Wanjiku + Nadia as reviewers. Pre-flight expected.

2. **HOOK-candidate lift** — the 4 hook-target memories may need a charter-section
   bridge (memory→charter→skill→hook is the full pipeline) OR can be lifted
   directly via DECIDE-tier issues at the wave-5 retro. Decision deferred to
   retro time.

3. **STALE-OPT-OUT watch** — no memory has crossed `2 * threshold = 6` retro
   citations yet, so the STALE-OPT-OUT informational class (#158) is not firing
   this audit. Highest opt-out citation count is 3 (`feedback_disable_followup_load_bearing`,
   superseded). Continue tracking.

## Cross-references

- main#269 — this PR closes
- main#266 — STALE-OPT-OUT class (P3W4)
- charter `feedback_enforcement_hierarchy.md` — promotion-target tier rules
- `.claude/skills/promotion-audit/SKILL.md` — audit invocation
- `.claude/team/promotion_audit_log/p2-wave-4.md` — prior audit (0 AUTO / 0 DECIDE baseline)
