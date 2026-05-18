# Promotion Audit — wave-5

**Wave end (pinned):** 2026-05-06T00:41:23Z
**Audit run at:** 2026-05-06T00:58:43.903789Z

**Summary:** 5 AUTO · 0 DECIDE · 52 KEPT · 11 SUPERSEDED · 1 ALREADY-PROMOTED

**Delta vs wave-4:** `0 AUTO / 0 DECIDE / 65 KEPT / 3 SUPERSEDED / 1 ALREADY-PROMOTED` → `5 AUTO / 0 DECIDE / 52 KEPT / 11 SUPERSEDED / 1 ALREADY-PROMOTED`. AUTO went from 0 → 5 because PR #277 (P3W5 T2) classified the 36 feedback memories with `promotion_target` frontmatter — this is the audit run that surfaces the result of that classification.

## AUTO-PROMOTED (artifacts to be generated)

| Item | From → To | Signal | Charter target |
|---|---|---|---|
| `feedback_canonical_source_via_git_show.md` | memory → charter | retro_citations=4 >= 3 | charter/git-discipline.md (canonical-source-via-git-show) |
| `feedback_child_repo_implementer_rule.md` | memory → charter | retro_citations=4 >= 3 | charter/agents.md (child-repo-implementer-rule) |
| `feedback_honest_audit_over_conclusion_claim.md` | memory → charter | retro_citations=4 >= 3 | charter/wave-wrapup.md (honest-audit-discipline) |
| `feedback_review_against_artifact_not_framing.md` | memory → charter | retro_citations=4 >= 3 | charter/pull-requests.md (review-against-artifact) |
| `feedback_security_guard_inline_not_followup.md` | memory → charter | retro_citations=4 >= 3 | charter/pull-requests.md (security-guard-inline) |

## REQUIRES DECISION (issues filed)

(none)

## KEPT (no action — informational)

_52 entries below threshold or with `promotion_target: none`._

## SUPERSEDED / ALREADY-PROMOTED (no action — informational)

- `feedback_enforcement_hierarchy.md` (already promoted; provenance in `charter/hooks.md`)
- `feedback_disable_followup_load_bearing.md` → superseded_by: charter:pull-requests.md § Load-Bearing Followups for Disabled CI Jobs
- `feedback_heredoc_in_git_commit.md` → enforced-elsewhere -> .claude/hooks/validate_commit_identity.py heredoc handling fix shipped via main#188 / PR#248 (P3W4)
- `feedback_pattern_e_emergency_process_collapse.md` → enforced-elsewhere -> .claude/team/charter/emergency-mode.md (P3W2 retro)
- `feedback_pr_review_comment_only.md` → enforced-elsewhere -> .claude/hooks/dispatcher.py block_gh_pr_review hook + charter/pull-requests.md § PR Review Format
- `feedback_repo_independence.md` → enforced-elsewhere -> cross-repo roster lookup hook
- `feedback_reviewer_techdebt_line_required.md` → enforced-elsewhere -> .claude/hooks/validate_pr_review.py — TechDebt line check on every reviewer-authored comment
- `feedback_settings_permission.md` → enforced-elsewhere -> settings.json permission rules
- `feedback_single_team_delegation.md` → enforced-elsewhere -> .claude/team/charter/agents.md § Single-Leader Constraint + CLAUDE.md § Session team architecture
- `feedback_tmp_msg_file_stale.md` → enforced-elsewhere -> .claude/hooks/block_stale_tmp_message_file.py shipped via main#237 / PR#242 (P3W4)
- `feedback_wave_kickoff_per_repo_branches.md` → enforced-elsewhere -> .claude/skills/wave-kickoff/SKILL.md per-child-repo branch creation shipped via main#238 / PR#245 (P3W4)
- `feedback_wave_planning_from_board.md` → enforced-elsewhere -> .claude/skills/wave-scope/SKILL.md (main#196 P3W1) + /wave-kickoff Step 0 reconciled-precondition (main#273 P3W5)

## Audit reproduction recipe

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
    ds.append(classify_memory(m, {'retro_citations': count_retro_citations(m, '.claude/team/feedback_log.md')}, already))
for s in read_all_charter_sections('.claude/team/charter'):
    ds.append(classify_section(s, {'skill_invocations': 0, 'threshold': 5}))
for sk in read_all_skills('.claude/skills'):
    ds.append(classify_skill(sk, {'skill_invocations': count_skill_invocations(sk.name, '.'), 'threshold': 5}, already))
c={}
for d in ds: c[d.kind]=c.get(d.kind,0)+1
for k in sorted(c): print(f'{k}: {c[k]}')
"
```

Expected (snapshot at audit run-time 2026-05-06T00:58:43Z):
```
ALREADY-PROMOTED: 1
AUTO: 5
KEPT: 52
SUPERSEDED: 11
```

**Re-run note:** This snapshot reflects state immediately before PR #282 (charter codification) landed. After #282 merges, the 5 AUTO memories acquire `superseded_by:` frontmatter and re-running this recipe will produce `0 AUTO / 16 SUPERSEDED` (the 5 AUTO transition to SUPERSEDED). That is expected post-promotion behavior — the audit is byte-deterministic given fixed input state, but the input state changes when promotions land. To reproduce the wave-5 audit exactly, run against the tree state at the audit timestamp (use `git show` on `.claude/team/charter/` and the memory directory at the wave-5 wrapup sha).