## Promotion Audit — p3-wave-15 (2026-06-02)

0 AUTO · 0 DECIDE · 105 KEPT · 16 SUPERSEDED (none newly superseded this wave)

No memory, charter section, or skill crossed a promotion threshold during P3W15.

- **100 memories scanned**; every `promotion_target: charter` memory at/over its retro-citation threshold is already `status: superseded` (codified in charter or a skill in a prior wave) — they classify SUPERSEDED, not AUTO.
- **0 charter sections** carry a `promotion-target` marker (no charter→skill candidates).
- **21 skills scanned**; none with `promotion-target: hook` met the invocation threshold.

### Approaching threshold (informational)

| Memory | Citations | Threshold | Note |
|---|---|---|---|
| `feedback_refresh_before_status_claim.md` | 2 | 3 | One more retro citation crosses it. Implementer-layer counterpart of the (already-promoted) stale-inbox rule. |
| `feedback_verify_diagnosis_before_delegating.md` | 2 | 3 | The W15 ig#943 phantom-dup incident is conceptually adjacent (verify premise at origin before acting) but cites the issue-filing class, not the delegation class — not counted. |

### Memories added during P3W15 (all KEEP-tier at creation)

- `feedback_ruff_parent_config_bleed_in_worktree.md` (feedback) — child-repo worktree ruff config bleed
- `feedback_org_wide_artifact_gate_non_blocking.md` (feedback) — cross-repo-derived artifact gates must be continue-on-error
- `feedback_lint_gate_cover_all_syntactic_forms.md` (feedback) — regex code-gates must cover all import forms
- `feedback_ruleset_empty_required_status_checks_422.md` (feedback) — GitHub rulesets API empty-array 422
- `project_deploy245_already_shipped_ig943_phantom.md` (project) — deploy#245/ig#943 ground truth
- `project_branch_protection_org_wide.md` (project, updated) — 8/8 rulesets applied+verified

### Stale opt-outs

None (no `promotion_target: none` memory has reached 2× its threshold).
