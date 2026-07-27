# Memory — CI / tooling / lint / gh-cli

<!-- Tier 2 (loads on demand — see session-start Step 2.5). One line per
     memory; full detail in each linked note file in THIS directory.
     Do NOT auto-inject this file at session start (that re-adds the whole
     always-loaded index the #1016 two-tier split removed). -->

- [pip-audit --strict advisory-DB drift](feedback_pip_audit_strict_advisory_db_drift.md) — red on branch / green on main, identical uv.lock, when a new advisory publishes; not your bug.
- [ruff parent-config bleed in worktree](feedback_ruff_parent_config_bleed.md) — child worktree under parent: ruff finds parent pyproject (100-col); CI uses child (88-col).
- [Org-wide artifact gate non-blocking](feedback_artifact_gate_non_blocking.md) — CI check over cross-repo-derived artifact must be continue-on-error, not a hard PR gate. deploy#363.
- [Lint gate cover all syntactic forms](feedback_lint_gate_cover_all_syntactic_forms.md) — regex/line-scan gate must match every access form (dotted + from-import). deploy#363.
- [Sync-gate build-kind false-fail on publish workflow](feedback_sync_gate_publish_build.md) — false-fails on repos w/ a publish/release workflow (docker build kind).
- [Cross-repo GHCR/npm registry-auth proof](feedback_cross_repo_ghcr_registry_auth_proof.md) — before claiming a cross-repo @noorinalabs/* registry-auth fix: check pkg visibility + witness.
- [zsh gotchas not covered by hook/docs](feedback_zsh_shell_environment.md) — `"$VAR:path"` history-modifier corruption INSIDE double quotes (the `git show $SHA:tests/…` trap → silent-zero greps); `$status` read-only; `path`/`fpath`/`cdpath` tied to $PATH so a `path=` assignment clobbers PATH → "command not found". General zsh-safety: docs/TOOLCHAIN.md + warn_zsh_wordsplit hook (main#879).
- [Commit msg via -F /tmp/msg.txt](feedback_heredoc_in_git_commit.md) — inline heredoc + git -c commit -m "$(cat<<EOF)" trips the identity-hook parser; use -F file.
- [gh-CLI gotchas (consolidated)](feedback_gh_cli_gotchas.md) — never trust exit 0 on a gh mutation; read-back via a query that cannot truncate. Surfaces: §1 `gh pr edit` no-op→REST PATCH; §2 `item-add` silent fail→per-issue projectItems check; §3 `item-list --limit` truncation (limit IS the bug); §4 `issue list` silent 30-cap; §5 `-f body=@file` literal paste (use `gh pr comment --body-file`/`-F`); §6 bare issue# resolves against cwd (always `-R owner/repo`); §7 update-branch 202 async; §8 formal APPROVE always 422s→issue comment; §9 closing keywords (default-branch-only auto-close; negation still closes; closingIssuesReferences empty on wave PRs); §10 validate_labels false-blocks (body over-match + stale cache); §11 ProjectV2 option-add is orchestrator-doable (mutation replaces whole list); §12 GraphQL quota drains independently of REST and fails as a SILENT ZERO (`item-list --limit 2000` ≈ 20 calls/run; REST `issues/{N}/comments` fallback keeps reviewers unblocked); §13 CI green — `check-runs` is authoritative, legacy `status` shows a false "pending".
- [git show over worktree for canonical source](feedback_canonical_source_via_git_show.md) — syncing "from sha X": local main may lag origin; fetch via git show <sha>:<path>.
- [Cross-repo wave-aware sibling checkout](feedback_cross_repo_wave_ref_resolution.md) — CI checking out sibling repos must resolve ref to wave branch (main fallback). deploy#159.
- [actionlint needs shellcheck on PATH](feedback_actionlint_needs_shellcheck.md) — actionlint silently skips shellcheck if binary absent; local "clean" diverges from CI.
- [Wikilink grep: bare slug, not [[slug]]](feedback_wikilink_md_suffix_grep.md) — removing a memory: grep bare slug to catch [[slug.md]] suffixed form a bracket grep misses. #758/#752.
- [Run ruff format --check before pushing hook tests](feedback_ruff_format_check_before_push.md) — uvx ruff@<pin> format --check .claude/hooks/ pre-push catches what hooks-lint CI blocks.
- [Safety direction > UX friction](feedback_safety_direction_over_ux_friction.md) — when a hook can't auto-fix cleanly, HARD BLOCK with diagnostic, never allow_with_log. PR#494.
- [.npmrc NODE_AUTH_TOKEN convention](feedback_npmrc_node_auth_token_convention.md) — project-level .npmrc for npm.pkg.github.com MUST use ${NODE_AUTH_TOKEN}; project-level wins.
- [sync-gate build-kind false-match](feedback_sync_gate_build_kind_false_match.md) — pre_commit_ci_sync.py build pattern false-matches "Docker Buildx"/"docker build" step names.
- [Trivy base-image CVE org-wide gate](feedback_trivy_base_image_cve_org_wide_gate.md) — ghcr Trivy fails on NEW debian base-image OS CVE, not your code; org-wide, not PR-caused.
- [Pipe masks command failure](feedback_push_pipe_masks_rejection.md) — ANY cmd | tail returns tail's 0. Redirect, don't pipe; pipefail over-reports.
- [GIT_DIR leak corrupted live repo config](feedback_git_dir_leak_repo_config.md) — pre-#720 leak wrote core.bare=true + [user] t@t into parent .git/config; fix=Edit it. #720.
- [Commit-author gate exclude merges](feedback_commit_author_gate_exclude_merges.md) — author/identity gate over a PR range MUST use git log --no-merges (merge commits = bare principal).
- [`rg -rn` is --replace, not recursive](feedback_rg_dash_r_is_replace_not_recursive.md) — grep muscle memory: `-r` eats the `n` and rewrites EVERY match to "n", killing line numbers. Output stays plausible (`deploy_n_path` looks like a real var), exit 0 — so wrong identifiers get transcribed as source and stamped `last_verified`. Falsify names with a hits-expected grep. #1139/PR#1153.
