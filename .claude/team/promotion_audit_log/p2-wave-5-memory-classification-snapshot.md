# Memory frontmatter snapshot — wave-5 memory-classification (2026-05-05)

Snapshot of every `feedback_*.md` memory frontmatter post-classification.
Ground truth: `~/.claude/projects/-home-parameterization-code-noorinalabs-main/memory/feedback_*.md`

## `feedback_actionlint_needs_shellcheck.md`

```yaml
name: actionlint local dry-run requires shellcheck on PATH
description: actionlint silently skips its shellcheck integration if the binary isn't on PATH locally — local "clean" claim can be wrong vs CI
type: feedback
originSessionId: 2e011116-89b1-4ac2-b2fc-1d5649d609c7
promotion_target: hook
promotion_threshold:
  retro_citations: 3
status: active
```

## `feedback_agent_color_render_quirk.md`

```yaml
name: Agent color drift in teammate-message tags is UI quirk, not multi-instance
description: Color variance for the same agent across user-side teammate-message tags doesn't mean two agent instances exist; verify via SendMessage routing color before claiming duality.
type: feedback
originSessionId: 7deaa69a-9ef8-44e6-9ca9-39e5a23f368c
promotion_target: none
promotion_threshold:
  retro_citations: 3
status: active
```

## `feedback_canonical_source_via_git_show.md`

```yaml
name: Use git show <sha>:<path> for canonical source when local main lags origin
description: Worktree files can be pre-merge even when origin/main has the canonical merged version. Always retrieve canonical source via git show <sha>:<path>, not from the working tree.
type: feedback
originSessionId: 43b60daf-62e0-4fa1-b083-aef94bac4edf
promotion_target: charter
promotion_threshold:
  retro_citations: 3
status: active
```

## `feedback_child_repo_implementer_rule.md`

```yaml
name: Child-repo implementer rule + spawn-brief verification
description: Implementers for child-repo work come from that child's own roster (not parent / not sibling-repo); orchestrator MUST verify roster membership at spawn-brief authoring time
type: feedback
originSessionId: 33831276-0bd2-46e7-8ddd-345abb927046
promotion_target: charter
promotion_threshold:
  retro_citations: 3
status: active
```

## `feedback_cross_repo_wave_ref_resolution.md`

```yaml
name: Cross-repo wave-aware sibling-repo checkout
description: Workflows that check out sibling repos for cross-repo tests must resolve refs to the wave branch (with main fallback) when running against wave-PR base
type: feedback
originSessionId: af6f52a7-e25c-41f4-9365-06539062b665
promotion_target: hook
promotion_threshold:
  retro_citations: 3
status: active
```

## `feedback_disable_followup_load_bearing.md`

```yaml
name: Disable-with-followup must be load-bearing
description: When a CI job or workflow is disabled to ship a PR (with a tech-debt followup issue), the followup must include re-enable as a hard acceptance criterion and must abide by the re-enablement outcome.
type: feedback
originSessionId: bfc8466f-74c1-4625-bdb4-26a9cc1f0262
promotion_target: none
status: superseded
superseded_by: charter:pull-requests.md § Load-Bearing Followups for Disabled CI Jobs
```

## `feedback_drift_evidence_to_existing_rationalization_issue.md`

```yaml
name: Drift evidence belongs as a comment on the existing rationalization issue, not a new ticket
description: When a code review surfaces a single concrete instance of drift that's already covered by an open rationalization/cleanup issue, comment evidence on that issue rather than filing a new one.
type: feedback
originSessionId: 2e011116-89b1-4ac2-b2fc-1d5649d609c7
promotion_target: charter
promotion_threshold:
  retro_citations: 3
status: active
```

## `feedback_enforcement_hierarchy.md`

```yaml
name: Enforcement hierarchy — hook > skill > charter
description: For any new behavior the team should follow, prefer automated enforcement (hook) over invokable tooling (skill) over written rule (charter). Charter-only rules decay.
type: feedback
originSessionId: bfc8466f-74c1-4625-bdb4-26a9cc1f0262
promotion_target: none
promotion_threshold:
  retro_citations: 3
referenced_in_retros: ['W7', 'W8', 'P2W9']
status: enforced-elsewhere
superseded_by: "implicit in CLAUDE.md § Ontology + .claude/team/charter/hooks.md § Hook Authorship Requirements; first concrete enforcement instance is Hook 15 (enforce_librarian_consulted, 2026-04-19)"
```

## `feedback_gh_pr_edit_silent_noop.md`

```yaml
name: gh pr edit silently no-ops on multiple flags — use REST PATCH
description: `gh pr edit --body-file` / `--base` / `--add-label` may return success but not mutate; REST PATCH via `gh api` is the reliable path. Now confirmed across 3 surfaces.
type: feedback
originSessionId: 33831276-0bd2-46e7-8ddd-345abb927046
promotion_target: hook
promotion_threshold:
  retro_citations: 3
status: active
```

## `feedback_heredoc_in_git_commit.md`

```yaml
name: Avoid inline heredocs when piping a commit message into git commit
description: The parent repo's validate_commit_identity hook's heredoc-stripping regex fails on nested escapes in chained bash scripts, causing spurious block of valid commits. Use git commit -F /tmp/msg.txt instead.
type: feedback
originSessionId: 43b60daf-62e0-4fa1-b083-aef94bac4edf
promotion_target: hook
promotion_threshold:
  retro_citations: 3
status: enforced-elsewhere
superseded_by: ".claude/hooks/validate_commit_identity.py heredoc handling fix shipped via main#188 / PR#248 (P3W4)"
```

## `feedback_honest_audit_over_conclusion_claim.md`

```yaml
name: Honest audit before "concluded" claims
description: Never claim a wave or workstream is "concluded" without first running a cross-repo open-item count; zero items open OR an explicit carry-forward list is required
type: feedback
originSessionId: 43b60daf-62e0-4fa1-b083-aef94bac4edf
promotion_target: charter
promotion_threshold:
  retro_citations: 3
status: active
```

## `feedback_live_trace_over_synthetic_acceptance.md`

```yaml
name: Live-trace evidence > synthetic-test acceptance
description: When validating a gate (CI hook / alert / validation rule), the strongest acceptance evidence is the gate firing on a real triggering artifact in the wild, not on synthetic test cases authored alongside the gate. Live-trace lets you verify behavior under conditions you didn't anticipate.
type: feedback
originSessionId: 2e011116-89b1-4ac2-b2fc-1d5649d609c7
promotion_target: charter
promotion_threshold:
  retro_citations: 3
status: active
```

## `feedback_multi_layer_gap_filing.md`

```yaml
name: Multi-layer gap → multi-issue, don't collapse
description: When a single root-cause incident surfaces gaps at multiple layers (detection / strategy / docs), file separately at each layer rather than collapsing into one comprehensive issue.
type: feedback
originSessionId: 2e011116-89b1-4ac2-b2fc-1d5649d609c7
promotion_target: charter
promotion_threshold:
  retro_citations: 3
status: active
```

## `feedback_origin_over_local_for_still_has_claims.md`

```yaml
name: For "still-has-X" claims, query origin not local clone
description: When asserting "PR still has bug Y" / "branch still at sha Z" / "file still missing Q", query origin directly via gh api, not a local clone. Local clones are point-in-time stale the moment the next push lands.
type: feedback
originSessionId: 2e011116-89b1-4ac2-b2fc-1d5649d609c7
promotion_target: charter
promotion_threshold:
  retro_citations: 3
status: active
```

## `feedback_pattern_e_emergency_process_collapse.md`

```yaml
name: Pattern E — process discipline degrades as fire escalates
description: Recognize the silent-collapse signature of charter compliance during emergencies; transition to documented Emergency Mode rather than letting discipline erode unmonitored
type: feedback
originSessionId: 79eed846-8264-4ced-aadb-54c0e36566bf
promotion_target: charter
promotion_threshold:
  retro_citations: 3
status: enforced-elsewhere
superseded_by: ".claude/team/charter/emergency-mode.md (P3W2 retro)"
```

## `feedback_pr_review_comment_only.md`

```yaml
name: PR reviews must be comment-based, never gh pr review
description: Charter § Pull Requests + PreToolUse hook block `gh pr review --approve/--request-changes/--comment` because all simulated team members share one GitHub user
type: feedback
originSessionId: d4c5c2e9-b16d-47b6-ae4f-1943f0b1b95f
promotion_target: hook
promotion_threshold:
  retro_citations: 3
status: enforced-elsewhere
superseded_by: ".claude/hooks/dispatcher.py block_gh_pr_review hook + charter/pull-requests.md § PR Review Format"
```

## `feedback_pr_state_in_refresh.md`

```yaml
name: PR state in refresh-before-status-claim
description: When refreshing PR state before posting a review, include `state` in the JSON query (not just reviews/comments/checks) — catches MERGED/CLOSED PRs.
type: feedback
originSessionId: 2e011116-89b1-4ac2-b2fc-1d5649d609c7
promotion_target: skill
promotion_threshold:
  retro_citations: 3
status: active
```

## `feedback_pr_vs_runtime_acceptance_criteria.md`

```yaml
name: Distinguish PR-acceptance criteria from runtime-acceptance criteria
description: Don't conflate gates that fire at different lifecycle positions. PR review validates code-correctness; runtime gates validate operational events. Bundling them either blocks PRs on infrastructure that doesn't exist yet, or forces synthetic-evidence fakery.
type: feedback
originSessionId: 2e011116-89b1-4ac2-b2fc-1d5649d609c7
promotion_target: charter
promotion_threshold:
  retro_citations: 3
status: active
```

## `feedback_refresh_before_acting.md`

```yaml
name: Refresh artifact state before acting, not just before claiming
description: Pre-action discipline — re-check artifact state immediately before taking parallel/competing action, not based on N-minute-old snapshots.
type: feedback
originSessionId: 7deaa69a-9ef8-44e6-9ca9-39e5a23f368c
promotion_target: charter
promotion_threshold:
  retro_citations: 3
status: active
```

## `feedback_refresh_before_status_claim.md`

```yaml
name: refresh PR state before status claims in long sessions
description: Agent-local snapshot of PR state goes stale across turns; refresh via gh api before any "still at 1/2 / still blocked / status is X" claim
type: feedback
originSessionId: 7a9193be-f4d0-4434-a33c-2c9493287b57
promotion_target: charter
promotion_threshold:
  retro_citations: 3
status: active
```

## `feedback_repo_independence.md`

```yaml
name: Repo independence and cross-repo commits
description: Each repo has its own roster for commit identity; Steven French is owner everywhere; commit identity hook supports cross-repo work. See also feedback_single_team_delegation.md for the distinct session-team architecture.
type: feedback
originSessionId: 103e6665-a60e-43d1-ba4e-1f415b61a04a
promotion_target: none
status: enforced-elsewhere
superseded_by: cross-repo roster lookup hook
```

## `feedback_review_against_artifact_not_framing.md`

```yaml
name: Review against the artifact, not the PR body's framing
description: Reviewer-class discipline — read diff/code at PR head directly (gh api contents), not through PR body claims, commit messages, or cited line numbers. Catches false-positives, drift, and silent obsolescence.
type: feedback
originSessionId: 0428d30b-2e2b-46d2-8837-1f3aa9705c5f
promotion_target: charter
promotion_threshold:
  retro_citations: 3
status: active
```

## `feedback_reviewer_techdebt_line_required.md`

```yaml
name: Reviewer comments must include TechDebt line on EVERY post in the chain (not just the first)
description: validate_pr_review hook checks every comment from a reviewer; the `TechDebt:` line is required on the approval post too, not only the initial review reply.
type: feedback
originSessionId: d4c5c2e9-b16d-47b6-ae4f-1943f0b1b95f
promotion_target: hook
promotion_threshold:
  retro_citations: 3
status: enforced-elsewhere
superseded_by: ".claude/hooks/validate_pr_review.py — TechDebt line check on every reviewer-authored comment"
```

## `feedback_role_class_specific_boundaries.md`

```yaml
name: role-class-specific boundaries — same person, different rules
description: When a person appears in multiple role contexts (PR reviewer vs escalation target vs advisor vs implementer), the boundary rule applies per-role-class, not per-person. Check which class you're operating in before correcting.
type: feedback
originSessionId: 7a9193be-f4d0-4434-a33c-2c9493287b57
promotion_target: charter
promotion_threshold:
  retro_citations: 3
status: active
```

## `feedback_ruff_format_check_before_push.md`

```yaml
name: Run ruff format --check before pushing hook test files
description: Pre-push muscle memory — `uvx ruff@<pinned> format --check .claude/hooks/` catches what hooks-lint CI will block on, avoiding additive format-fix commits
type: feedback
originSessionId: 327bdb0e-5fea-4971-8f0f-e1e28b937e1c
promotion_target: hook
promotion_threshold:
  retro_citations: 3
status: active
```

## `feedback_runtime_gate_scoping.md`

```yaml
name: Runtime/operational gates are NOT PR acceptance criteria — fix-lands-now / gate-fires-later scoping
description: When an infra fix's validation requires production-only state (compose stack, real creds, target env), don't conflate the runtime gate with the PR acceptance criterion. Deliver unit-mechanic correctness in the PR, document what CANNOT be validated pre-prod, add a post-merge Test Plan step naming the gate.
type: feedback
originSessionId: 2e011116-89b1-4ac2-b2fc-1d5649d609c7
promotion_target: charter
promotion_threshold:
  retro_citations: 3
status: active
```

## `feedback_search_before_filing.md`

```yaml
name: Search existing issues before filing — bugs surface from multiple angles and dups are easy to file
description: Before filing a new bug, run `gh issue list --search "<keyword>"` across the relevant repo. Same root cause often gets reported multiple times under different framings.
type: feedback
originSessionId: d4c5c2e9-b16d-47b6-ae4f-1943f0b1b95f
promotion_target: skill
promotion_threshold:
  retro_citations: 3
status: active
```

## `feedback_security_guard_inline_not_followup.md`

```yaml
name: Security guards belong inline, not in a followup
description: When reviewing a PR whose security model depends on a runtime guard (env check, scheme restriction, startup assertion), require the guard in the PR itself — do not accept "we'll file a TechDebt followup for it." Offering the followup is fine; relying on it is wrong.
type: feedback
originSessionId: 43b60daf-62e0-4fa1-b083-aef94bac4edf
promotion_target: charter
promotion_threshold:
  retro_citations: 3
status: active
```

## `feedback_self_loop_task_replay_glitch.md`

```yaml
name: Self-loop task_assignment replays — harness glitch, do not re-execute
description: Implementer agents may receive their own completed TaskCreate entries replayed back as fresh task_assignment messages; verify against TaskGet + ignore self-loops
type: feedback
originSessionId: 33831276-0bd2-46e7-8ddd-345abb927046
promotion_target: none
promotion_threshold:
  retro_citations: 3
status: active
```

## `feedback_settings_permission.md`

```yaml
name: Settings changes don't need permission
description: Claude should modify .claude/settings.json (project and user level) without asking — user has pre-authorized all .claude/ file operations.
type: feedback
originSessionId: 9e57aa54-98ef-4593-8ca0-4310d8ee9f0d
promotion_target: none
status: enforced-elsewhere
superseded_by: settings.json permission rules
```

## `feedback_single_team_delegation.md`

```yaml
name: Single-session-team delegation pattern
description: One team per orchestrator session. Team-lead is sole Agent-tool caller; managers SendMessage the team-lead to request implementer spawns.
type: feedback
originSessionId: 7a9193be-f4d0-4434-a33c-2c9493287b57
promotion_target: charter
promotion_threshold:
  retro_citations: 3
status: enforced-elsewhere
superseded_by: ".claude/team/charter/agents.md § Single-Leader Constraint + CLAUDE.md § Session team architecture"
```

## `feedback_stale_inbox_manager.md`

```yaml
name: Stale-inbox manager failure mode
description: When message propagation lags state change, a manager's view of downstream teammates can trail reality; correcting on stale view creates false churn
type: feedback
originSessionId: 7a9193be-f4d0-4434-a33c-2c9493287b57
promotion_target: charter
promotion_threshold:
  retro_citations: 3
status: active
```

## `feedback_throttle_takeover.md`

```yaml
name: Throttle takeover by orchestrator
description: When a spawned implementer throttle-stalls mid-task, finish their work directly as orchestrator — faster recovery than respawning.
type: feedback
originSessionId: 7deaa69a-9ef8-44e6-9ca9-39e5a23f368c
promotion_target: charter
promotion_threshold:
  retro_citations: 3
status: active
```

## `feedback_tmp_msg_file_stale.md`

```yaml
name: /tmp/* file race — Write blocks silently, downstream Bash consumes stale content
description: Write tool refuses to overwrite a /tmp/file unless Read this session; paired Bash (git commit -F, gh pr create --body-file) ships prior task's stale content. Hook block_stale_tmp_message_file.py is now primary mitigation (mtime > 30s → block).
type: feedback
originSessionId: 2e011116-89b1-4ac2-b2fc-1d5649d609c7
promotion_target: hook
promotion_threshold:
  retro_citations: 3
status: enforced-elsewhere
superseded_by: ".claude/hooks/block_stale_tmp_message_file.py shipped via main#237 / PR#242 (P3W4)"
```

## `feedback_verify_diagnosis_before_delegating.md`

```yaml
name: Verify diagnosis before delegating fixes to subagents
description: Before spawning an agent on a fix, verify the diagnosis against git/file reality — not just API state. Subagents will (correctly) refuse fixes that contradict ground truth, wasting a spawn cycle.
type: feedback
originSessionId: d4c5c2e9-b16d-47b6-ae4f-1943f0b1b95f
promotion_target: charter
promotion_threshold:
  retro_citations: 3
status: active
```

## `feedback_verify_third_party_integrity_claims.md`

```yaml
name: Verify third-party tool integrity claims against source
description: Don't claim a third-party tool's integrity property (verifies SHA, signs commits, etc.) without grepping the actual source — convention isn't proof
type: feedback
originSessionId: 2e011116-89b1-4ac2-b2fc-1d5649d609c7
promotion_target: charter
promotion_threshold:
  retro_citations: 3
status: active
```

## `feedback_wave_branch_issue_close.md`

```yaml
name: Wave-branch merges don't auto-close issues — explicit gh issue close required
description: GitHub's `Closes #N` PR-body linkage only auto-fires on merges into the repo's default branch. PRs into a wave branch (`deployments/phase-2/wave-N`) merge cleanly but leave the referenced issue OPEN. Always `gh issue view <N>` post-merge to verify; if open, `gh issue close <N> --comment "Resolved by PR #M (sha ...)"` explicitly.
type: feedback
originSessionId: 2e011116-89b1-4ac2-b2fc-1d5649d609c7
promotion_target: skill
promotion_threshold:
  retro_citations: 3
status: active
```

## `feedback_wave_kickoff_per_repo_branches.md`

```yaml
name: /wave-kickoff misses per-child-repo wave branches
description: Skill step 1 creates deployments/phase-{N}/wave-{M} in orchestrator repo only; multi-repo waves need same branch in every child repo with PRs in scope
type: feedback
originSessionId: 33831276-0bd2-46e7-8ddd-345abb927046
promotion_target: skill
promotion_threshold:
  retro_citations: 3
status: enforced-elsewhere
superseded_by: ".claude/skills/wave-kickoff/SKILL.md per-child-repo branch creation shipped via main#238 / PR#245 (P3W4)"
```

## `feedback_wave_planning_from_board.md`

```yaml
name: Wave planning starts from the project board
description: The full project board (project 2) is the authoritative backlog for wave scoping. Labels and meta-issue bodies are post-scoping, not pre-scoping.
type: feedback
originSessionId: 7a9193be-f4d0-4434-a33c-2c9493287b57
promotion_target: skill
promotion_threshold:
  retro_citations: 3
status: enforced-elsewhere
superseded_by: ".claude/skills/wave-scope/SKILL.md (main#196 P3W1) + /wave-kickoff Step 0 reconciled-precondition (main#273 P3W5)"
```

