# Hooks — Catalog 1–12

> Part of the [hooks charter index](../hooks.md) — re-shelved from `charter/hooks.md` for section-level loading (#963). Rules unchanged.

## Hook 1: Validate Commit Identity (`validate_commit_identity.py`)

- **What it automates:** Commit Identity rules — validates that every `git commit` command includes `-c user.name=` and `-c user.email=` flags matching a roster member.
- **Parent+child roster merge (#112 part a):** When the target repo (either the repo hosting this hook, or the `cd <path>` target of a cross-repo commit) sits inside another git repo that itself has `.claude/team/roster.json`, the hook loads the parent roster and merges it under the child roster at load time. Child entries win on name collision. Walk-up is limited to ONE level to avoid false positives in nested `code/` trees. This lets org-level coordinators (e.g. Nadia.Khoury, Wanjiku, Santiago, Aino) commit in any child repo without duplicating their entries into every child `roster.json`.
- **Augments:** The [Commit Identity](../commits.md) section. The manual rule still applies; this hook enforces it automatically.
- **Manual steps remaining:** When a new team member is hired, add their name and email to the appropriate `.claude/team/roster.json` — org-level coordinators go in `noorinalabs-main`'s roster, per-repo members go in that repo's roster.
- **Emergency override:** Remove or comment out the hook entry in `.claude/settings.json`. Re-add after the emergency.

## Hook 2: Block `--no-verify` (`block_no_verify.py`)

- **What it automates:** Prevents team members from using `--no-verify` on git commit, which bypasses pre-commit hooks.
- **Augments:** General code quality and CI enforcement rules. Pre-commit hooks are a required gate.
- **Manual steps remaining:** None — the hook is fully automated.
- **Emergency override:** Remove the hook entry from `.claude/settings.json`. The user can also run git commands directly outside Claude Code.

## Hook 3: Block `git config` (`block_git_config.py`)

- **What it automates:** Commit Identity rules — blocks `git config` write commands to prevent modification of global/repo-level git config. Read-only operations (`--get`, `--list`, `-l`, etc.) are allowed for tooling compatibility.
- **Augments:** The charter rule "do NOT modify the global or repo-level git config."
- **Manual steps remaining:** None.
- **Emergency override:** Remove the hook entry from `.claude/settings.json`.

## Hook 4: Auto-set `ENVIRONMENT=test` (`auto_set_env_test.py`)

- **What it automates:** Ensures `ENVIRONMENT=test` is set before any `pytest`, `uv run pytest`, or `make test` command. Prevents CI breaks caused by missing environment variable.
- **Augments:** Testing workflow. This is an automated safeguard, not replacing a prior manual rule.
- **Manual steps remaining:** None — the hook blocks and instructs the user to prepend `ENVIRONMENT=test`.
- **Skip conditions (#114):** Two short-circuits run before the pytest/make-test regex to prevent substring false-positives in GitHub API calls and body content:
  1. **`gh` subcommands** — if the effective argv[0] (after stripping leading `VAR=value` assignments) is `gh`, the hook skips. `gh` is a GitHub API client, never a test runner.
  2. **`--body` / `--body-file` flags** — if the command contains either flag, the hook skips. Structured bodies almost always contain user-supplied text mentioning `pytest` or `make test`. This skip is intentionally broad — a rare false negative on an exotic `--body`-using tool is cheaper than blocking every review/issue/comment that references pytest.
- **Emergency override:** Remove the hook entry from `.claude/settings.json`.

## Hook 5: Validate Labels Before `gh issue create` (`validate_labels.py`)

- **What it automates:** GitHub Label Hygiene — validates that all `--label` values exist in the repository before `gh issue create` runs.
- **Augments:** The label hygiene section. The manual rule to run `gh label list` first is now enforced automatically.
- **Manual steps remaining:** None — the hook fetches labels and validates automatically.
- **Emergency override:** Remove the hook entry from `.claude/settings.json`. If `gh label list` is unavailable (network issue), the hook allows the command with a warning.

## Hook 6: Validate Lockfile Paths (`validate_lockfile_paths.py`)

- **What it automates:** Blocks `git commit` if any staged `package-lock.json` contains `/tmp/` or `file:/` paths — local worktree artifacts that break CI.
- **Augments:** CI reliability. Session 4 had a Playwright PR with `/tmp/noorinalabs-design-system-0.0.1.tgz` baked into the lockfile.
- **Manual steps remaining:** None — the hook scans staged lockfiles automatically.
- **Emergency override:** Remove the hook entry from `.claude/settings.json`.

## Hook 7: Validate PR Review (`validate_pr_review.py`)

- **What it automates:** Blocks `gh pr merge` unless the PR has at least one review from a non-author. Enforces the charter's peer review requirement.
- **Augments:** [Pull Requests](../pull-requests.md) review requirements. Session 4 saw all PR reviews skipped across 3 waves.
- **Manual steps remaining:** None — the hook queries `gh pr view` for reviews automatically. Use `--admin` flag for emergency overrides.
- **Emergency override:** Pass `--admin` to `gh pr merge`, or remove the hook entry.

## Hook 8: Block `gh pr review` (`block_gh_pr_review.py`)

- **What it automates:** Blocks `gh pr review` commands (--approve, --request-changes, etc.) since all agents share one GitHub user and API-based reviews always fail with "cannot approve your own pull request".
- **Augments:** [Pull Requests](../pull-requests.md) § Comment-Based Reviews. Redirects agents to use `gh pr comment` with the charter review format (Requestor/Requestee/RequestOrReplied fields).
- **Manual steps remaining:** None — the hook blocks and provides the correct format.
- **Emergency override:** Remove the hook entry from `.claude/settings.json`.

## Hook 9: Validate Branch Freshness (`validate_branch_freshness.py`)

- **What it automates:** Blocks `gh pr create` if the feature branch is behind the base branch. Prevents merge conflicts from stale branches. Honors the `--repo OWNER/REPO` flag (#118 fix): when present, the freshness check uses the GitHub `compare` API against the target repo instead of the cwd-based `git fetch`/`git merge-base`. Without `--repo`, falls back to cwd behavior. Cross-repo PRs without `--head` are skipped (we cannot infer head reliably from cwd).
- **Augments:** [Branching](../branching.md) workflow. Session 4 had RBAC and session hardening PRs conflict because neither was rebased.
- **Manual steps remaining:** None — the hook runs `git fetch` and `git merge-base --is-ancestor` (cwd path) or `gh api repos/.../compare/{base}...{head}` (cross-repo path) automatically.
- **Emergency override:** Remove the hook entry from `.claude/settings.json`.

## Hook 10: Validate VPS_HOST (`validate_vps_host.py`)

- **What it automates:** Blocks `gh variable set VPS_HOST` if the value resolves to a Cloudflare IP range. Also warns if a hostname is used instead of a direct IP.
- **Augments:** Deployment safety. Session 4 had VPS_HOST set to a Cloudflare-proxied domain, causing SSH timeout on deploy.
- **Manual steps remaining:** None — the hook resolves the hostname and checks against known Cloudflare ranges.
- **Emergency override:** Remove the hook entry from `.claude/settings.json`.

## Hook 11: Warn GHCR Image (`warn_ghcr_image.py`)

- **What it automates:** Warns (does not block) when `gh workflow run` triggers a deploy-related workflow and the expected GHCR image may not exist.
- **Augments:** Deployment safety. Session 4 had deploy-all triggered before the landing page GHCR image was built.
- **Manual steps remaining:** None — the hook checks `gh api` for the image. This is a warning only since deploy workflows sometimes build the image.
- **Emergency override:** Not needed (warning only). Remove the hook entry to suppress.

## Hook 12: Validate Wave Context (`validate_wave_context.py`)

- **What it automates:** Warns when agents are spawned without an active wave context in `cross-repo-status.json`. Ensures `/wave-kickoff` is run before agent work begins.
- **Augments:** [Agent Lifecycle](../agents.md) wave management. Session 4 had the orchestrator bypass the team structure entirely.
- **Matcher:** `Agent` (not `Bash`) — fires on Agent tool calls.
- **Manual steps remaining:** Run `/wave-kickoff` to set the wave context. The hook is a warning, not a block.
- **Emergency override:** Not needed (warning only). Remove the hook entry to suppress.

