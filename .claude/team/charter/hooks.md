# Automated Enforcement Hooks (Claude Code)

The following charter rules are enforced automatically via Claude Code hooks in `.claude/settings.json`. These are PreToolUse hooks that fire before Bash commands. Hook scripts live in `.claude/hooks/`.

## Hook 1: Validate Commit Identity (`validate_commit_identity.py`)

- **What it automates:** Commit Identity rules — validates that every `git commit` command includes `-c user.name=` and `-c user.email=` flags matching a roster member.
- **Augments:** The [Commit Identity](commits.md) section. The manual rule still applies; this hook enforces it automatically.
- **Manual steps remaining:** When a new team member is hired, add their name and email to `.claude/team/roster.json` (the single source of truth for all hooks and skills).
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
- **Augments:** [Pull Requests](pull-requests.md) review requirements. Session 4 saw all PR reviews skipped across 3 waves.
- **Manual steps remaining:** None — the hook queries `gh pr view` for reviews automatically. Use `--admin` flag for emergency overrides.
- **Emergency override:** Pass `--admin` to `gh pr merge`, or remove the hook entry.

## Hook 8: Block `gh pr review` (`block_gh_pr_review.py`)

- **What it automates:** Blocks `gh pr review` commands (--approve, --request-changes, etc.) since all agents share one GitHub user and API-based reviews always fail with "cannot approve your own pull request".
- **Augments:** [Pull Requests](pull-requests.md) § Comment-Based Reviews. Redirects agents to use `gh pr comment` with the charter review format (Requestor/Requestee/RequestOrReplied fields).
- **Manual steps remaining:** None — the hook blocks and provides the correct format.
- **Emergency override:** Remove the hook entry from `.claude/settings.json`.

## Hook 9: Validate Branch Freshness (`validate_branch_freshness.py`)

- **What it automates:** Blocks `gh pr create` if the feature branch is behind the base branch. Prevents merge conflicts from stale branches. Honors the `--repo OWNER/REPO` flag (#118 fix): when present, the freshness check uses the GitHub `compare` API against the target repo instead of the cwd-based `git fetch`/`git merge-base`. Without `--repo`, falls back to cwd behavior. Cross-repo PRs without `--head` are skipped (we cannot infer head reliably from cwd).
- **Augments:** [Branching](branching.md) workflow. Session 4 had RBAC and session hardening PRs conflict because neither was rebased.
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
- **Augments:** [Agent Lifecycle](agents.md) wave management. Session 4 had the orchestrator bypass the team structure entirely.
- **Matcher:** `Agent` (not `Bash`) — fires on Agent tool calls.
- **Manual steps remaining:** Run `/wave-kickoff` to set the wave context. The hook is a warning, not a block.
- **Emergency override:** Not needed (warning only). Remove the hook entry to suppress.

## Bash Hook Dispatcher Architecture <!-- promotion-target: none -->
All Bash-matcher hooks are consolidated into a **single dispatcher** (`bash_dispatcher.py`) that dynamically loads individual hook modules via `importlib.util`. This reduces process spawns from N (one per hook) to 1 per Bash tool call.

**Key design decisions:**
- Individual hook files remain as standalone modules — testable independently, loaded dynamically by the dispatcher
- `bash_dispatcher.py` is the **only** Bash-matcher entry in `.claude/settings.json`
- Hook execution order is preserved (matches the order hooks are registered in the dispatcher)
- **Fail-open:** If an individual hook crashes, the dispatcher logs a warning and continues — it does not block the command
- **Short-circuit on block:** If any hook returns a blocking result, subsequent hooks are skipped
- `sys.exit` calls from individual hooks are intercepted via mock to prevent the dispatcher from terminating

**Adding a new Bash hook:**
1. Create the hook script in `.claude/hooks/` as a standalone Python module
2. Register it in `bash_dispatcher.py`'s hook list
3. Do NOT add a separate entry in `.claude/settings.json` — the dispatcher handles all Bash hooks

**Why:** Phase 2 Wave 1 PR #73 consolidated 12 individual Bash-matcher hooks into this pattern, reducing process spawns from 12 to 1 per Bash call.

## Dispatcher Consolidation Policy <!-- promotion-target: none -->
When hooks sharing the same matcher type (Bash, Agent, SendMessage, etc.) accumulate beyond **3**, they must be consolidated into a dispatcher immediately. Do not wait for hook sprawl to become a performance problem.

**Threshold:** >3 hooks of the same matcher type triggers mandatory consolidation.

**Pattern to follow:** The Bash hook dispatcher (`bash_dispatcher.py`) is the reference implementation. Key properties any new dispatcher must preserve:
- Dynamic module loading via `importlib.util` — individual hooks remain standalone and independently testable
- Single entry in `.claude/settings.json` per matcher type — the dispatcher is the only registered hook
- Fail-open on individual hook crashes — log a warning, continue to the next hook
- Short-circuit on block — if any hook returns a blocking result, skip subsequent hooks
- Intercept `sys.exit` calls from individual hooks to prevent dispatcher termination

**When to apply:**
- Before adding a 4th hook of the same matcher type, consolidate the existing hooks into a dispatcher first
- When reviewing PRs that add new hooks, verify the hook count and flag if consolidation is needed
- This applies to all matcher types: Bash, Agent, SendMessage, PreToolUse, PostToolUse

**Why:** Phase 2 Wave 1 accumulated 12 Bash-matcher hooks before consolidation (PR #73). Each hook spawned a separate Python process per Bash call — 12 process spawns for every command. Consolidation reduced this to 1. Apply the pattern proactively to avoid repeating this accumulation.

## Hook 13: Auto-Add Issues to Project Board (`auto_add_issue_to_board.py`)

- **What it automates:** After `gh issue create` runs, detects the new issue URL in stdout and runs `gh project item-add` to add it to the Cross-Repo Wave Plan board (project #2).
- **Type:** PostToolUse (advisory, non-blocking).
- **Augments:** Cross-Repo Wave Plan § Board Maintenance Rules — "New issues created during a wave must be added to the board immediately."
- **Manual steps remaining:** None — fully automated.
- **Emergency override:** Remove the hook entry from `.claude/settings.json`.

## Hook 14: Validate PR CI Status (`validate_pr_ci_status.py`)

- **What it automates:** Blocks `gh pr merge` when any CI check on the PR is failing, cancelled, timed out, or requires action. Pending checks also block unless the user passes `--auto` (let GitHub auto-merge on green). Queries `gh pr view --json statusCheckRollup`; supports the `--repo` flag.
- **Augments:** [Pull Requests](pull-requests.md) "green CI before merge" requirement. Phase 2 Wave 7 merged multiple PRs with red `security-audit`, `e2e`, and `test_migrate_users.py` checks despite the charter rule. Per the enforcement-hierarchy principle (hook > skill > charter), a repeatedly violated charter rule becomes a hook.
- **Manual steps remaining:** None — the hook queries `gh pr view` for the check rollup automatically.
- **Emergency override:** Pass `--admin` to `gh pr merge`, or remove the `validate_pr_ci_status` entry from the dispatcher hook list.

## Hook 15: Enforce Librarian Consulted (`enforce_librarian_consulted.py`)

- **What it automates:** Blocks `Edit`, `Write`, and `NotebookEdit` tool calls unless `/ontology-librarian` has been consulted earlier in the session. Reads the session transcript (`transcript_path` from the Claude Code hook input) and scans for either a user slash-command invocation of `/ontology-librarian` or an assistant `Skill` tool_use with `skill: "ontology-librarian"`. If neither is present, the edit is blocked with instructions to run the librarian first.
- **Augments:** [CLAUDE.md § Ontology — "Before any code changes (mandatory)"](../../../CLAUDE.md). The charter rule "Every agent — orchestrator, team member, or one-off — MUST run `/ontology-librarian {topic}` before making code changes" was honored inconsistently across Phase 2 Wave 9 (3 of 4 code-change PRs skipped it — deploy#125 kafka GID, deploy#130 obs fix, user-service#67 OAuth GET). Per the enforcement-hierarchy principle (hook > skill > charter), a repeatedly violated charter rule becomes a hook. See issue [#150](https://github.com/noorinalabs/noorinalabs-main/issues/150).
- **Matcher:** `Edit`, `Write`, `NotebookEdit` (not `Bash`) — direct registration in `settings.json` since these are the first PreToolUse hooks on these matchers. When a 4th hook is added to any of these matchers, consolidate via the dispatcher pattern (see § Dispatcher Consolidation Policy).
- **Allowed bypasses:** `/tmp/**` (out-of-repo scratch), `~/.claude/**` (user config), `**/memory/*.md` and `MEMORY.md` (project memory), `.claude/annunaki/*` (hook-managed log). All other paths — including `.claude/team/feedback_log.md`, charter files, and source code — require librarian consultation. Stance documented in the hook docstring: meta-files are project-state artifacts the ontology tracks; treating them as free-edits replays the decay pattern #150 fixes.
- **Manual steps remaining:** Run `/ontology-librarian {topic}` once per session before any Edit/Write/NotebookEdit on non-allow-listed paths. One invocation unlocks the session.
- **Emergency override:** Remove the three `enforce_librarian_consulted.py` entries (Edit/Write/NotebookEdit matchers) from `.claude/settings.json`. Re-add after the emergency. There is no in-band override flag — the purpose of the hook is to break the "this one's small" rationalization, so an inline bypass would defeat the point.
- **Promotion provenance:** First end-to-end execution of the memory → charter → hook promotion pattern ratified by the owner on 2026-04-19. Rule lived in CLAUDE.md § Ontology (charter-equivalent location) since W7; this hook is the underlying enforcement layer. Worked example referenced by the future `/promotion-audit` skill design.

---

## Hook Authorship Requirements <!-- promotion-target: none -->
Every new hook in `.claude/hooks/` must meet these requirements **at the time it is merged**. Partial compliance is a moderate feedback event.

### 1. Input-language specification

The hook's module docstring (top of file) must include an explicit **Input Language** section defining:

- **Fires on:** which PreToolUse event (Bash, Agent, Edit, Write, etc.)
- **Matches:** the exact command / input shape the hook acts on, expressed as a regex or grammar fragment
- **Does NOT match:** inputs that superficially look similar but are intentionally out of scope (with examples)
- **Flag pass-through:** which CLI flags (e.g., `--repo`, `--admin`) are extracted from the matched command and how

Example (from `validate_pr_ci_status.py`):
```python
"""
Input Language:
  Fires on:      PreToolUse Bash
  Matches:       gh pr merge {N} [--repo {OWNER/REPO}] [--squash|--merge|--rebase] [--admin] [--auto]
  Does NOT match: gh pr list, gh pr view, gh pr checks, gh pr create, git merge, git pull
  Flag pass-through:
    --repo   → overrides cwd-resolved repo when querying gh pr view
    --admin  → short-circuits (emergency override, allows merge)
    --auto   → allows pending checks (GitHub auto-merge)
"""
```

**Why:** Phase 2 Wave 8 surfaced six hook substring/regex bugs (#113 validate_labels cwd, #114 auto_set_env_test test-string false-positives, #118 validate_branch_freshness cwd, #123 validate_pr_review RequestOrReplied-Requested false-positive, ontology-tracker /tmp ghost entries, validate_labels default-limit). Root cause was hooks written liberally without an explicit spec of what they match vs. don't. An input-language docstring forces the author to enumerate the negative space before shipping.

### 2. Charter entry in `charter/hooks.md`

Every new hook must have a numbered entry in this file with: What it automates, Augments (which charter section), Manual steps remaining, Emergency override. No hook ships without a charter entry.

### 3. Test coverage for negative matches

The hook's test suite (or docstring-embedded manual verification) must include at least one input that **looks like a match but is intentionally excluded** — to guard against the substring-bug pattern. Example: a `validate_pr_merge` hook must verify it does NOT fire on `gh pr list`.

### 4. Dispatcher registration (not settings.json)

New Bash hooks must register in `dispatcher.py`'s `_BASH_HOOKS` list, not as a separate `settings.json` entry. See `charter/hooks.md` § Hook Dispatcher Consolidation (Hook 7 pattern).

**Enforcement:** The Standards & Quality Lead (Aino) verifies these requirements during hook PR review. A hook missing any of the four requirements must not be approved.
