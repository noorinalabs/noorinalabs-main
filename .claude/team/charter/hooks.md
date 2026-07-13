# Automated Enforcement Hooks (Claude Code)

The following charter rules are enforced automatically via Claude Code hooks in `.claude/settings.json`. These are PreToolUse hooks that fire before Bash commands. Hook scripts live in `.claude/hooks/`.

> **Section index (#963).** This file's sections now live as per-concern files under [`charter/hooks/`](hooks/). Every heading below is preserved so existing `hooks.md#anchor` deep-links keep resolving — each entry forwards to the section's new location. The promotion markers (`promotion-target` / `promoted-to`) moved with the section bodies; this index is not a promotion-audit input.

## Hook 1: Validate Commit Identity (`validate_commit_identity.py`)
Every `git commit` must carry roster-matching `-c user.name/user.email` flags. → [hooks/catalog-01-12.md](hooks/catalog-01-12.md#hook-1-validate-commit-identity-validate_commit_identitypy)

## Hook 2: Block `--no-verify` (`block_no_verify.py`)
Blocks `--no-verify` on git commit — pre-commit hooks cannot be bypassed. → [hooks/catalog-01-12.md](hooks/catalog-01-12.md#hook-2-block---no-verify-block_no_verifypy)

## Hook 3: Block `git config` (`block_git_config.py`)
Blocks `git config` writes; read-only operations allowed. → [hooks/catalog-01-12.md](hooks/catalog-01-12.md#hook-3-block-git-config-block_git_configpy)

## Hook 4: Auto-set `ENVIRONMENT=test` (`auto_set_env_test.py`)
Ensures `ENVIRONMENT=test` before pytest/make-test commands. → [hooks/catalog-01-12.md](hooks/catalog-01-12.md#hook-4-auto-set-environmenttest-auto_set_env_testpy)

## Hook 5: Validate Labels Before `gh issue create` (`validate_labels.py`)
Validates `--label` values exist in the repo before issue creation. → [hooks/catalog-01-12.md](hooks/catalog-01-12.md#hook-5-validate-labels-before-gh-issue-create-validate_labelspy)

## Hook 6: Validate Lockfile Paths (`validate_lockfile_paths.py`)
Blocks commits of lockfiles containing `/tmp/` or `file:/` local paths. → [hooks/catalog-01-12.md](hooks/catalog-01-12.md#hook-6-validate-lockfile-paths-validate_lockfile_pathspy)

## Hook 7: Validate PR Review (`validate_pr_review.py`)
Blocks `gh pr merge` without the required non-author review evidence. → [hooks/catalog-01-12.md](hooks/catalog-01-12.md#hook-7-validate-pr-review-validate_pr_reviewpy)

## Hook 8: Block `gh pr review` (`block_gh_pr_review.py`)
Blocks API-based `gh pr review` (shared account); redirects to comment-based reviews. → [hooks/catalog-01-12.md](hooks/catalog-01-12.md#hook-8-block-gh-pr-review-block_gh_pr_reviewpy)

## Hook 9: Validate Branch Freshness (`validate_branch_freshness.py`)
Blocks `gh pr create` from a branch that is behind its base. → [hooks/catalog-01-12.md](hooks/catalog-01-12.md#hook-9-validate-branch-freshness-validate_branch_freshnesspy)

## Hook 10: Validate VPS_HOST (`validate_vps_host.py`)
Blocks `gh variable set VPS_HOST` pointing at a Cloudflare IP range. → [hooks/catalog-01-12.md](hooks/catalog-01-12.md#hook-10-validate-vps_host-validate_vps_hostpy)

## Hook 11: Warn GHCR Image (`warn_ghcr_image.py`)
Warns when a deploy workflow run may reference a missing GHCR image. → [hooks/catalog-01-12.md](hooks/catalog-01-12.md#hook-11-warn-ghcr-image-warn_ghcr_imagepy)

## Hook 12: Validate Wave Context (`validate_wave_context.py`)
Warns when agents are spawned without an active wave context. → [hooks/catalog-01-12.md](hooks/catalog-01-12.md#hook-12-validate-wave-context-validate_wave_contextpy)

## Bash Hook Dispatcher Architecture
All Bash-matcher hooks run through a single `bash_dispatcher.py` module loader. → [hooks/dispatcher-and-helpers.md](hooks/dispatcher-and-helpers.md#bash-hook-dispatcher-architecture)

## Dispatcher Consolidation Policy
More than 3 hooks on one matcher type must consolidate into a dispatcher immediately. → [hooks/dispatcher-and-helpers.md](hooks/dispatcher-and-helpers.md#dispatcher-consolidation-policy)

## Hook 13: Auto-Add Issues to Project Board (`auto_add_issue_to_board.py`)
Auto-adds newly created issues to the Cross-Repo Wave Plan board. → [hooks/catalog-13-17.md](hooks/catalog-13-17.md#hook-13-auto-add-issues-to-project-board-auto_add_issue_to_boardpy)

## Hook 14: Validate PR CI Status (`validate_pr_ci_status.py`)
Blocks `gh pr merge` while any CI check is failing, cancelled, or pending. → [hooks/catalog-13-17.md](hooks/catalog-13-17.md#hook-14-validate-pr-ci-status-validate_pr_ci_statuspy)

## Hook 15: Enforce Librarian Consulted (`enforce_librarian_consulted.py`)
Advisory (since #857) nudge to consult `/ontology-librarian` before edits. → [hooks/catalog-13-17.md](hooks/catalog-13-17.md#hook-15-enforce-librarian-consulted-enforce_librarian_consultedpy)

## Hook 16: Refuse Worktree Self-Delete (`no_worktree_self_delete.py`)
Blocks `git worktree remove` of the caller's own current directory. → [hooks/catalog-13-17.md](hooks/catalog-13-17.md#hook-16-refuse-worktree-self-delete-no_worktree_self_deletepy)

## Hook 17: Validate Wave Audit (`validate_wave_audit.py`)
Blocks wave-wrapup/retro/handoff skills while the wave has unaudited open items. → [hooks/catalog-13-17.md](hooks/catalog-13-17.md#hook-17-validate-wave-audit-validate_wave_auditpy)

## Hook 18: Validate Edit Completion (`validate_edit_completion.py`)
Two-phase gate closing the tool-error-soft-accept failure class on edits. → [hooks/catalog-18-22.md](hooks/catalog-18-22.md#hook-18-validate-edit-completion-validate_edit_completionpy)

## Hook 19: Validate Workflow Paths Coverage (`validate_workflow_paths_coverage.py`)
Blocks PRs whose workflow-file changes escape all `on.pull_request.paths` filters. → [hooks/catalog-18-22.md](hooks/catalog-18-22.md#hook-19-validate-workflow-paths-coverage-validate_workflow_paths_coveragepy)

## Hook 20: Validate Wave-Label Evidence (`validate_wave_label_evidence.py`)
Blocks wave-labeling of issues whose cited file paths 404 at origin. → [hooks/catalog-18-22.md](hooks/catalog-18-22.md#hook-20-validate-wave-label-evidence-validate_wave_label_evidencepy)

## Hook 21: Post-Label-Change Wave Field Sync (`post_label_change_wave_field_sync.py`)
Syncs the project-board Wave field after wave-label add/remove. → [hooks/catalog-18-22.md](hooks/catalog-18-22.md#hook-21-post-label-change-wave-field-sync-post_label_change_wave_field_syncpy)

## Hook 22: Block Squash-Merge Into a Wave Branch (`block_squash_wave_merge.py`)
Blocks `--squash` into wave branches (squash re-authors to the bare principal). → [hooks/catalog-18-22.md](hooks/catalog-18-22.md#hook-22-block-squash-merge-into-a-wave-branch-block_squash_wave_mergepy)

## Shared Helpers
Single-source `_<helper>.py` primitives shared by hooks and skills. → [hooks/dispatcher-and-helpers.md](hooks/dispatcher-and-helpers.md#shared-helpers)

## Hook Sync Across Child Repos
How org-owned hooks propagate to child repos; ownership matrix pointer. → [hooks/authorship-and-audit.md](hooks/authorship-and-audit.md#hook-sync-across-child-repos)

## Hook Authorship Requirements
The merge-time requirements every new hook must meet (docstring, tests, charter entry, dispatcher registration, provenance phrasing). → [hooks/authorship-and-audit.md](hooks/authorship-and-audit.md#hook-authorship-requirements)

## Hook Audit Protocol
Protocol for auditing a repo's hook-ownership status. → [hooks/authorship-and-audit.md](hooks/authorship-and-audit.md#hook-audit-protocol)
