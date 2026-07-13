# Briefing Pack — Coordinator

Enumerated reading list for the **orchestrator / manager class** (Program Director, TPM, Release Coordinator, wave orchestration). Links only — the rules live in the linked sections; this pack copies nothing (#963). Read in order; load a section only when its trigger applies.

## Always read

1. [`agents/orchestration-model.md` § Single-Leader Constraint](../agents/orchestration-model.md#single-leader-constraint-one-team-per-orchestrator-session) — one implicit team per session; the orchestrator checklists for spawning implementers and reviewers live here.
2. [`agents/orchestration-model.md` § Hub-and-Spoke Orchestration Model](../agents/orchestration-model.md#hub-and-spoke-orchestration-model) — only the orchestrator spawns; managers request spawns via SendMessage.
3. [`agents/spawn-discipline.md`](../agents/spawn-discipline.md) — reuse idle teammates; pre-spawn state check + crossed-message race protocol; one aligned correction, never a serial toggle; child-repo implementer rule + spawn-brief verification at origin HEAD.
4. [`agents/lifecycle.md`](../agents/lifecycle.md) — shut agents down when work completes; liveness checkpoints; throttle-stall recovery thresholds.
5. [`agents/naming-and-teams.md`](../agents/naming-and-teams.md) — roster mapping, `{repo}-{firstname}` naming, team names.
6. [`issues.md`](../issues.md) — delegation, work gate, issue comment format, reply protocol.
7. [`state-claims.md`](../state-claims.md) — refresh PR/issue state at the artifact before status claims or corrections.

## Wave and merge management

8. [`pull-requests/wave-merge.md`](../pull-requests/wave-merge.md) — deployments-branch PR workflow, one merge model per wave, wave merge PR verification, staging-promotion gate, end-state live-env evidence, post-merge integration verification, retro body-vs-diff discipline.
9. [`pull-requests/reviews.md` § Two-Reviewer Assignment](../pull-requests/reviews.md#two-reviewer-assignment-at-wave-kickoff) and [§ Single-Reviewer Exception](../pull-requests/reviews.md#single-reviewer-exception-wave-bootstrap-only) — reviewer slates you assign at kickoff.
10. [`pull-requests/ci-gates.md` § Org-Wide Branch Protection + Admin-Merge Exceptions](../pull-requests/ci-gates.md#org-wide-branch-protection--admin-merge-exceptions-mandatory) — server-side gates and the narrow exception protocol.
11. [`pull-requests/ci-gates.md` § Load-Bearing Followups for Disabled CI Jobs](../pull-requests/ci-gates.md#load-bearing-followups-for-disabled-ci-jobs) — what a valid unblock-followup looks like.
12. [`branching.md`](../branching.md) — wave/feature branch shapes and worktree cleanup.

## Roster and governance

13. [`agents/headcount.md` § Governed Headcount](../agents/headcount.md#governed-headcount-roster-budget) — machine-enforced roster budget; growth is a deliberate budget change.
14. [`communication.md`](../communication.md) — cross-repo messaging, shared state, dependency contracts.
15. [`artifact-ownership.md`](../artifact-ownership.md) — which `.claude/` + ontology artifact class is owned/executes where.
16. [`emergency-mode.md`](../emergency-mode.md) — DR/security escape valve and `[EMERGENCY]` protocol.

## Hooks that gate coordination actions

17. [`hooks/catalog-13-17.md` § Hook 17](../hooks/catalog-13-17.md#hook-17-validate-wave-audit-validate_wave_auditpy) — wave-wrapup/retro/handoff blocked while open items are unaudited.
18. [`hooks/catalog-18-22.md`](../hooks/catalog-18-22.md) — workflow-paths coverage (19), wave-label evidence (20), wave-field sync (21), squash-merge block on wave branches (22).
19. [`hooks/catalog-01-12.md` § Hook 12](../hooks/catalog-01-12.md#hook-12-validate-wave-context-validate_wave_contextpy) — spawn warns without an active wave context.
20. [`skills.md`](../skills.md) — skill lifecycle + promotion pipeline marker convention (for retro/promotion decisions).
