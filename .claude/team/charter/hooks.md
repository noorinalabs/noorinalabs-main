# Automated Enforcement Hooks (Claude Code)

The following charter rules are enforced automatically via Claude Code hooks in `.claude/settings.json`. These are PreToolUse hooks that fire before Bash commands. Hook scripts live in `.claude/hooks/`.

## Hook 1: Validate Commit Identity (`validate_commit_identity.py`)

- **What it automates:** Commit Identity rules — validates that every `git commit` command includes `-c user.name=` and `-c user.email=` flags matching a roster member.
- **Parent+child roster merge (#112 part a):** When the target repo (either the repo hosting this hook, or the `cd <path>` target of a cross-repo commit) sits inside another git repo that itself has `.claude/team/roster.json`, the hook loads the parent roster and merges it under the child roster at load time. Child entries win on name collision. Walk-up is limited to ONE level to avoid false positives in nested `code/` trees. This lets org-level coordinators (e.g. Nadia.Khoury, Wanjiku, Santiago, Aino) commit in any child repo without duplicating their entries into every child `roster.json`.
- **Augments:** The [Commit Identity](commits.md) section. The manual rule still applies; this hook enforces it automatically.
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
- **P2W9 retro findings (2026-04-22):** Hook 14 is registered in noorinalabs-main but is NOT synced to child repos. `gh pr merge` on child-repo PRs (deploy#146 in particular) bypassed the CI check because the dispatcher in the child repo doesn't list this hook. **Action:** sync Hook 14 to all 7 child-repo dispatchers following the same pattern as #112 part (b) for `validate_commit_identity`. Additionally, the hook's behavior on **pending** checks may have been too permissive during P2W9 — the mid-CI-run merge window allowed main#178 to merge before FAILURE conclusions materialized. Tighten the pending-check semantics to block mid-run merges unless `--auto` is passed to hand off to GitHub's auto-merge. Tracking issues: noorinalabs-main#182 (main), noorinalabs-deploy#148 (cross-repo sync).
- **NEUTRAL allowlist (resolves #219, P3W4 T5):** GitHub's Checks API uses `NEUTRAL` to mean "the check has no opinion" — historically treated as pass. Chromatic (the dominant visual-regression service for Storybook-based component libraries) returns `NEUTRAL` on snapshots-pending-review, so a vanilla `NEUTRAL → pass` interpretation would let a PR merge while visual-regression review is still pending. The hook now consults a `_NEUTRAL_PENDING_CHECK_NAMES` allowlist (case-insensitive on the CheckRun's display name) to decide: names in the allowlist treat `NEUTRAL` as **pending**, all other names preserve the prior `NEUTRAL → pass` behavior. Initial allowlist: `{"chromatic"}`. Add new entries when a CI service uses `NEUTRAL` to mean "review pending" rather than "no opinion." Surfaced by Luciana Ferreyra (design-system QA) on design-system#61 review, comment-id 4335373566.

## Hook 15: Enforce Librarian Consulted (`enforce_librarian_consulted.py`)

- **What it automates:** Blocks `Edit`, `Write`, and `NotebookEdit` tool calls unless `/ontology-librarian` has been consulted earlier in the session. Reads the session transcript (`transcript_path` from the Claude Code hook input) and scans for either a user slash-command invocation of `/ontology-librarian` or an assistant `Skill` tool_use with `skill: "ontology-librarian"`. As of [#169](https://github.com/noorinalabs/noorinalabs-main/issues/169) the hook also accepts a cwd-keyed sentinel file at `<cwd>/.claude/.librarian-consulted/<sha1(cwd)>.marker` written by the librarian skill, with a 1-hour TTL. Either signal (transcript OR fresh sentinel) is sufficient; the sentinel fallback fixes a transcript-flush race that blocked worktree subagents from editing despite having invoked the librarian. Known limitation: a subagent sharing its parent's cwd (non-worktree, rare) would be covered by the parent's sentinel — worktree subagents, the dominant case, each have distinct cwds and distinct sentinels. If neither signal is present, the edit is blocked with instructions to run the librarian first.
- **Augments:** [CLAUDE.md § Ontology — "Before any code changes (mandatory)"](../../../CLAUDE.md). The charter rule "Every agent — orchestrator, team member, or one-off — MUST run `/ontology-librarian {topic}` before making code changes" was honored inconsistently across Phase 2 Wave 9 (3 of 4 code-change PRs skipped it — deploy#125 kafka GID, deploy#130 obs fix, user-service#67 OAuth GET). Per the enforcement-hierarchy principle (hook > skill > charter), a repeatedly violated charter rule becomes a hook. See issue [#150](https://github.com/noorinalabs/noorinalabs-main/issues/150).
- **Matcher:** `Edit`, `Write`, `NotebookEdit` (not `Bash`) — direct registration in `settings.json` since these are the first PreToolUse hooks on these matchers. When a 4th hook is added to any of these matchers, consolidate via the dispatcher pattern (see § Dispatcher Consolidation Policy).
- **Allowed bypasses:** `/tmp/**` (out-of-repo scratch), `~/.claude/**` (user config), `**/memory/*.md` and `MEMORY.md` (project memory), `.claude/annunaki/*` (hook-managed log). All other paths — including `.claude/team/feedback_log.md`, charter files, and source code — require librarian consultation. Stance documented in the hook docstring: meta-files are project-state artifacts the ontology tracks; treating them as free-edits replays the decay pattern #150 fixes.
- **Manual steps remaining:** Run `/ontology-librarian {topic}` once per session before any Edit/Write/NotebookEdit on non-allow-listed paths. One invocation unlocks the session.
- **Emergency override:** Remove the three `enforce_librarian_consulted.py` entries (Edit/Write/NotebookEdit matchers) from `.claude/settings.json`. Re-add after the emergency. There is no in-band override flag — the purpose of the hook is to break the "this one's small" rationalization, so an inline bypass would defeat the point.
- **Promotion provenance:** First end-to-end execution of the memory → charter → hook promotion pattern ratified by the owner on 2026-04-19. Rule lived in CLAUDE.md § Ontology (charter-equivalent location) since W7; this hook is the underlying enforcement layer. Worked example referenced by the future `/promotion-audit` skill design.

## Hook 16: Refuse Worktree Self-Delete (`no_worktree_self_delete.py`)

- **What it automates:** Blocks `git worktree remove <path>` when the caller's current directory (`input_data["cwd"]`, the shell's actual `$PWD` at tool-call time) equals `<path>` or is a descendant of it. Resolves both sides via `os.path.realpath` so symlinks do not defeat the check. Splits chained commands on `&&`, `||`, `;`, and `|` so `cd /safe && git worktree remove <cwd>` still blocks — the `cd` is a plan the shell has not yet executed when the hook fires. Strips leading `FOO=bar` env-var assignments and skips global `git -C <dir>` / `-c k=v` options plus `remove`-level flags (`-f`, `--force`) during parse so the `<path>` argument is extracted reliably. Prefix-confusion is avoided via `Path.relative_to` semantics rather than string `startswith`, so `/foo/wt-a-sibling` is not treated as descending from `/foo/wt-a`. The block message names a safe cwd to move to (best-guess via `git rev-parse --show-superproject-working-tree` / `--show-toplevel` run with the parent of the target worktree as cwd; generic fallback if those fail).
- **Augments:** Worktree hygiene. Wave-8 retro item 5 noted: "Worktree-self-delete is a real operator risk... Guard: prefix with explicit `cd <project-root>` to a known-existing path, or detect cwd ancestry before removing." The guard was noted but not implemented; the same footgun fired again and forced a session restart during cleanup. Per the enforcement-hierarchy principle (hook > skill > charter), a caller-side convention that decayed becomes a hook. See issue [#173](https://github.com/noorinalabs/noorinalabs-main/issues/173).
- **Matcher:** `Bash` via the dispatcher (`no_worktree_self_delete` entry in `dispatcher.py`'s `_BASH_HOOKS` list). Cheap filesystem-only check, ordered near the top of the list.
- **Manual steps remaining:** None — the hook fires automatically on every Bash call that contains a `git worktree remove` segment. Skills that remove worktrees (`/wave-wrapup`, cleanup flows) should still follow the safe-cd pattern (defense in depth) — the hook is the backstop, not the only line of defense.
- **Emergency override:** Remove the `no_worktree_self_delete` entry from `dispatcher.py`'s `_BASH_HOOKS` list. Re-add after the emergency. There is no in-band override flag — the purpose of the hook is to prevent a specific operator footgun, so an inline bypass would defeat the point.

## Hook 17: Validate Wave Audit (`validate_wave_audit.py`)

- **What it automates:** Blocks PreToolUse `Skill` calls for `wave-wrapup`, `wave-retro`, and `handoff` when the active wave has open items in any org repo AND the skill's `args` payload does not contain an explicit carry-forward marker. Reads the active wave label from `cross-repo-status.json` (`current_wave` + `phase` → e.g. `p2-wave-10`), runs `gh issue list --repo noorinalabs/<repo> --state open --label <label> --json number --jq length` across the 8 org repos (charter `skills.md` § Audit command), sums the result, and gates accordingly. Carry-forward markers recognized: `Carry-forward:` or `Carry forward:` inline (case-insensitive), `## Carry-forward` markdown heading, or `#<N> → <destination>` arrow patterns naming a non-numeric destination. All infrastructure failures (missing `gh`, network errors, malformed `cross-repo-status.json`, missing wave label) fail OPEN with a system warning so a transient infra hiccup never blocks legitimate work — the hook only blocks when it is *certain* the wave has open items the author hasn't acknowledged.
- **Augments:** [`charter/skills.md`](skills.md) § Wave Lifecycle — Open-Item Audit. The charter rule is the source of truth for *what* counts as a valid carry-forward acknowledgment; this hook is the enforcement layer. Promotion provenance: memory `feedback_honest_audit_over_conclusion_claim` (2026-04-22) → charter `skills.md` § Wave Lifecycle (PR #193) → this hook (issue [#195](https://github.com/noorinalabs/noorinalabs-main/issues/195)). Second worked example of the memory→charter→hook promotion pipeline ratified 2026-04-19 (Hook 15 was the first).
- **Matcher:** `Skill` (new matcher type — first hook of this kind in the codebase). Direct registration in `settings.json` per dispatcher consolidation policy (§ Dispatcher Consolidation Policy: consolidate at 4+ hooks of the same matcher; this is the only Skill-matcher hook).
- **Manual steps remaining:** None when the gate fires — the operator must either close the open items, OR add a carry-forward block to the skill `args`. The charter rule still mandates the same discipline for manually-authored handoffs and retros that don't go through skills (those are out of scope for the hook; a separate Stop-hook scan was considered and deferred per the design comment on #195).
- **Emergency override:** Remove the `Skill` matcher entry from `.claude/settings.json`. There is no in-band override flag — the purpose of the hook is to break the "this one's fine, just say concluded" rationalization that put the P2W9 incident on owner's desk. Matches Hook 15's stance.
- **Deliberate-non-implementation of `--ack-incomplete`:** A `--ack-incomplete '<reason>'` in-band override flag was proposed during design ratification on #195 alongside the `--carry-forward` marker path. Only `--carry-forward` was implemented in PR #218; `--ack-incomplete` was deliberately omitted. Rationale: any per-session bypass — even one that demands a logged reason — invites the same rationalization fail-mode the hook exists to prevent. Hook 15 precedent (no in-band override). Settings.json-removal is the right granularity for "I genuinely need to bypass" — annoying enough to be deliberate, visible in commit history. Adding a flag for a hypothetical need violates the pre-emptive-surface-area rule. Re-open conditions (file a comment on [#220](https://github.com/noorinalabs/noorinalabs-main/issues/220) with evidence if any surface): (1) real escape-hatch need during a security incident — capture the timeline; (2) repeat operator action of "edit settings.json to bypass + put back" within a 30-day window — vote-with-feet signal; (3) pattern of carry-forward markers added purely to silence the gate without genuine carry-forward intent — theater-marker rationalization. Issue [#220](https://github.com/noorinalabs/noorinalabs-main/issues/220) stays OPEN as the canonical watch-list anchor for these conditions (mirrors how phase-end-state meta-issues stay open while their dependencies close). PD ratification: 2026-04-28.

## Hook 18: Validate Edit Completion (`validate_edit_completion.py`)

- **What it automates:** Two-phase gate that closes the **tool-error-soft-accept** failure class. PostToolUse on Edit/Write/NotebookEdit records `is_error: true` responses to a session-scoped sentinel at `<repo_root>/.claude/.edit-error-sentinel/<session-id>.jsonl` (gitignored). PreToolUse on subsequent state-sensitive actions (Edit/Write/NotebookEdit on the same path, SendMessage, or Bash matching `git commit` / `gh pr comment` / `gh issue comment`) reads the sentinel and blocks unless the error has been acknowledged via one of: a `Read` of the errored path, a Bash `cat`/`head`/`tail`/`grep`/`less`/`ls`/`wc` of the path, OR a SendMessage / comment text containing both the path AND the literal string `edit-error acknowledged`. Acknowledged entries are pruned atomically.
- **Augments:** P2W10 retro-mandated discipline. Two independent W10 instances (Marcia walkback on prompt-drafting Edit error; Bereket Contract-revert false-status report despite 5 consecutive Edit `is_error: true`). Same tool, same failure class, same blast-radius. Per `feedback_enforcement_hierarchy.md`, charter rule "always verify edits landed" decays without enforcement; this is the hook-tier enforcement.
- **Matcher:** Multi-matcher — `Bash` via `dispatcher.py` (`_BASH_HOOKS` list); `Edit` / `Write` / `NotebookEdit` direct PreToolUse + PostToolUse registration in `settings.json`; `SendMessage` direct PreToolUse registration in `settings.json` (alongside `block_shutdown_without_retro.py`). The dispatcher routes Bash via the hook's `check(input_data)` function; the other matchers go through `main()` which dispatches on `hook_event_name` to either `_post_tool_use` (record-on-error) or `_pre_tool_use_blocks` (gate-if-unacked).
- **Manual steps remaining:** When a state-sensitive action blocks, the agent acknowledges via Read / Bash-verb / explicit-marker on the errored path. Charter `pull-requests.md` § Trust the Artifact, Not the Framing already prescribes verify-before-claim discipline; this hook is the enforcement layer for that prescription on the Edit-tool surface.
- **Emergency override:** Pass an explicit `edit-error acknowledged` marker in the next SendMessage / comment for the path (in-band escape hatch for recovery edits). Or remove the hook entry from `dispatcher.py`'s `_BASH_HOOKS` list AND the `settings.json` registrations. The marker path is the recommended emergency path because it preserves the audit trail.
- **Promotion provenance:** P2W10 retro (2026-04-23 — Khoury framing: "if it keeps surfacing, hook candidate — something that blocks next Write/Edit if prior Edit returned an error-that-wasn't-explicitly-handled"). Filed as [#198](https://github.com/noorinalabs/noorinalabs-main/issues/198), promoted to hook in P3W4 T5.

## Hook 19: Validate Workflow Paths Coverage (`validate_workflow_paths_coverage.py`)

- **What it automates:** Blocks `gh pr create` / `gh pr ready` when the PR diff modifies any `.github/workflows/*.yml` file that is NOT covered by any base-branch workflow's `on.pull_request.paths:` filter (or by a base workflow with `on.pull_request:` and no `paths:` filter). Closes the **workflow-file orphan** failure class — a PR can land workflow changes that GitHub silently skips CI on, producing `statusCheckRollup: []` + `mergeStateStatus: CLEAN` (which `validate_pr_ci_status` only blocks on FAILED, not EMPTY). Companion to Hook 9 / `validate_pr_ci_status` at the trigger-graph layer.
- **Coverage logic:** Builds the union of `on.pull_request.paths:` patterns across all base-branch workflows; tracks whether ANY base workflow has `on.pull_request:` without a `paths:` filter (covers everything). For each `.github/workflows/**` file in the PR diff, checks against the union. Path matching uses `fnmatch` with `**` glob expansion. Workflows with `paths-ignore:` only (no `paths:`) are conservatively treated as no-paths-filter coverage (over-allows slightly; safer side for the orphan-blocking goal).
- **Augments:** Charter `pull-requests.md § CI Workflow `pull_request` Triggers Must Cover Wave Branches` (sibling at the wave-branch coverage layer; this hook covers the workflow-file-orphan layer). Both rules together close the trigger-gap class surfaced in P2W10 via deploy#153 + user-service#80/#81.
- **Matcher:** `Bash` via `dispatcher.py` (`_BASH_HOOKS` list, ordered after `validate_branch_freshness` since both are PR-create gates and this one fetches base-branch workflow YAMLs — the network calls land late in the chain).
- **Manual steps remaining:** When the hook blocks, the PR author has three remediation paths (named in the block message): (a) precursor PR adds `'.github/workflows/**'` to a base workflow's paths filter — recommended; (b) add a workflow with `on.pull_request:` and no `paths:` filter (covers everything including future workflow files); (c) `--admin` at merge time if the change genuinely needs no CI (rare).
- **Emergency override:** Remove the `validate_workflow_paths_coverage` entry from `dispatcher.py`'s `_BASH_HOOKS` list. There is no in-band override flag — the purpose of the hook is to prevent silent CI skipping, so an inline bypass would defeat the point.
- **Out of scope for v1:** Net-zero infra-revert orphan detection (`statusCheckRollup: []` + non-base HEAD) — requires re-running GitHub's paths-filter evaluator at hook time. Filed as follow-up. Cross-repo reusable-workflow inheritance (`workflow_call`/`uses:`) — reviewer responsibility.
- **Promotion provenance:** P2W10 retro-candidate (2026-04-24, deploy#153 76d7d7f orphan). Filed as [#203](https://github.com/noorinalabs/noorinalabs-main/issues/203) sibling of [#200](https://github.com/noorinalabs/noorinalabs-main/issues/200) — different layer of the same trigger-gap class. Promoted to hook in P3W4 T5.

## Hook 20: Validate Wave-Label Evidence (`validate_wave_label_evidence.py`)

- **What it automates:** Blocks `gh issue create --label '...p<N>-wave-<M>...'` and `gh issue edit <NUM> --add-label '...p<N>-wave-<M>...'` when the issue body cites file paths that 404 at BOTH `origin/main` AND the corresponding `origin/deployments/phase-<N>/wave-<M>` branch. Closes the **stale-path wave-labeling** failure class — three independent W8 occurrences (deploy#276 already-resolved, isnad-graph#866-870 hook-files-don't-exist, PR#871 stale-worktree audit-re-framing) consumed implementer-spawn cycles before manual review caught the divergence.
- **Verification logic:** Tokenizes the command via shlex; identifies wave-label application; resolves issue body from `--body` / `--body-file` for create or via `gh issue view --json body` for edit. Regex-extracts cited Python file paths (`.claude/**/*.py` and `src/**/*.py` and `tests/**/*.py` shapes, with optional `noorinalabs-<repo>/` prefix for cross-repo refs). For each cited path, runs `gh api repos/<owner>/<repo>/contents/<path>?ref=<ref>` against `main` AND the wave branch. If EVERY cited path 404s at BOTH refs, blocks; if at least one verifies, allows.
- **Override mechanism:** Add `Origin-Verification: <reason>` to the issue body before applying the wave label. Three legitimate shapes: (a) `Origin-Verification: <path> exists at <ref>` (path exists at non-standard ref), (b) `Origin-Verification: not-applicable — <reason>` (pure-policy issue with no real file claim, e.g., proposed-new-hook), (c) `Origin-Verification: <other rationale>`. The override line is regex-matched (`^Origin-Verification:\s*\S`), so any substantive value after the prefix counts.
- **Augments:** Charter `pull-requests.md § Origin > Local Clone for "Still-Has-X" File-Content Claims` (the file-content discipline this hook gates at wave-label-application time). Three-strikes-in-one-wave argues for hook-tier per `feedback_enforcement_hierarchy.md`: not isolated incident, not edge case, recurring root-cause across distinct repos and roles.
- **Matcher:** `Bash` via `dispatcher.py` (`_BASH_HOOKS` list, ordered after `validate_labels` since both gate `gh issue create` and this one fetches contents via `gh api` — the network calls land late in the chain).
- **Manual steps remaining:** When the hook blocks, the operator has three remediation paths (named in the block message): (a) verify the path EXISTS at origin and update the body to cite a real path; (b) add `Origin-Verification: not-applicable` for legitimately path-less or proposed-new-artifact issues; (c) add `Origin-Verification: <path> exists at <ref>` if the path exists at a non-standard ref.
- **Emergency override:** Remove the `validate_wave_label_evidence` entry from `dispatcher.py`'s `_BASH_HOOKS` list. There is no in-band override flag beyond the `Origin-Verification:` body line, which is the discipline-preserving path.
- **Out of scope for v1:** `gh project item-add` matcher (W8 instances of stale-path issues hit the labeling surface before the project-add surface; covering label-time is the higher-leverage gate). Cited-issue freshness ("any cited issue # must be OPEN or noted as `closed-resolved-by-X`") — heavier hook surface; deferred to retro for now. Both filed as follow-ups against this hook.
- **Promotion provenance:** Three-occurrence W8 pattern (2026-05-09 audit, see [#337](https://github.com/noorinalabs/noorinalabs-main/issues/337) for full provenance chain). Source memory family: `feedback_origin_over_local_for_still_has_claims.md` (SUPERSEDED 2026-05-10 by charter `pull-requests.md`), `feedback_pre_spawn_brief_verified_at_head.md`, `feedback_verify_diagnosis_before_delegating.md`. Promoted to hook in P3W9.

## Shared Helpers <!-- promotion-target: none -->

Reusable primitives that multiple hooks (or hooks + skills) consume. Each helper has a single-source-of-truth implementation under `.claude/hooks/` with an underscore-prefix filename (`_<helper>.py`) marking it as internal, not a hook itself.

### `_shell_parse.py` — Tokenize Bash commands safely

Multiple PreToolUse hooks need to detect command shapes (`git commit`, `gh pr create`, etc.) without regex'ing the raw command string — a pattern that has repeatedly mis-fired on heredoc bodies, code-fence blocks, and `--body-file` argument values (issues #118, #134, #144, #188, #189, #216, #223, #226, #227). The helper exposes `tokenize`, `strip_heredocs`, `iter_command_segments`, `find_git_subcommand`, `find_gh_subcommand`, and `extract_dash_c_pairs`. Consumed by `validate_commit_identity`, `validate_branch_freshness`, `block_git_config`, `block_no_verify`, `block_shutdown_without_retro`, `block_stale_tmp_message_file`, `validate_review_comment_format`, `post_wave_kickoff_comment`. When a new transcript-or-command-reading hook needs to discriminate command shape, consume this helper rather than regex.

### `_consultation_sentinel.py` — Cwd-keyed consultation sentinel

Generalizes the Hook 15 sentinel pattern (introduction: [#169](https://github.com/noorinalabs/noorinalabs-main/issues/169); generalization: [#176](https://github.com/noorinalabs/noorinalabs-main/issues/176)) for any future transcript-reading enforcement hook. The pattern: a skill writes a marker file in the agent's cwd recording that it was invoked; the hook reads the marker as a second acceptance signal beside the transcript scan. Subagent worktree sessions repeatedly hit a transcript-flush race that left the marker absent from the file the hook reads — the sentinel survives that race because the skill writes it synchronously.

**Path scheme:** `<cwd>/.claude/.consulted/<skill_name>/<sha1(abspath(cwd)+"\n")[:16]>.marker`. Namespaced by skill name so multiple transcript-reading hooks don't collide. The trailing-newline hash matches the shell idiom `pwd | sha1sum | cut -c1-16` so skills can write the sentinel from shell and the Python helper computes the same path (parity gated by `test_consultation_sentinel.ShellPythonParityTests`).

**API:**
- `write_consultation_sentinel(skill_name, cwd=None) -> Path | None` — skill-side write. Returns None on OSError (fail-open).
- `consultation_sentinel_is_fresh(cwd, skill_name, ttl_seconds=3600) -> bool` — hook-side read. False on missing / stale / unreadable / future-dated marker.
- `consultation_sentinel_path(cwd, skill_name) -> Path` — pure path composition (tests use this to write sentinels manually).
- `cwd_sentinel_hash(cwd) -> str` — 16-char sha1 prefix, exported because Hook 15 tests pin the shell/Python parity property.

**Use this helper** when authoring a new transcript-reading enforcement hook. Do NOT reinvent path-keying, hashing, or TTL logic — every divergence becomes a sentinel-doesn't-match bug in worktree subagents.

**Promotion provenance:** Hook 15 (#150 + #169) original sentinel introduction. PR #174 added synchronous skill-side write. Issue #176 extracted the helper. Filed by Nadia Khoury during PR #174 review.

## Hook Sync Across Child Repos <!-- promotion-target: none -->

Shared hooks live in `noorinalabs-main/.claude/hooks/` (the parent repo's hooks tree). Child repos consume them via **parent-canonical paths** — their own `.claude/settings.json` registers each hook by absolute path into the parent's hooks tree, e.g.:

```jsonc
{
  "matcher": "Bash",
  "hooks": [{
    "type": "command",
    "command": "python3 /home/parameterization/code/noorinalabs-main/.claude/hooks/dispatcher.py",
    "timeout": 30
  }]
}
```

**The parent's `.claude/hooks/` is the single source of truth for shared hook code.** Child repos do NOT keep local `.py` copies of shared hooks; they reference the parent's files by path. This makes a new shared hook a configuration change in each child's `settings.json`, not a code-fan-out across child repos — eliminating the drift risk that surfaced in P2W9 (Hook 14 was registered in the parent for ~2 weeks before #194 surfaced no child had it).

### Required pattern

For every shared hook (i.e., a hook that exists at `noorinalabs-main/.claude/hooks/<name>.py` and applies to multiple repos):

1. Hook source code lives at `noorinalabs-main/.claude/hooks/<name>.py` ONLY. No copies in child repos.
2. Each child repo's `.claude/settings.json` registers the hook under the appropriate matcher with a `command` of `python3 /home/parameterization/code/noorinalabs-main/.claude/hooks/<name>.py` (or the dispatcher path for Bash hooks).
3. Child repos do NOT have their own `annunaki_log.py`, `_shell_parse.py`, `dispatcher.py`, or other shared support files. They reference the parent's copies.

### Anti-pattern: copy-resident hooks

Do NOT copy `.py` hook files into a child repo's `.claude/hooks/` and register them via relative paths. This is the **copy-resident anti-pattern**:

- Forces a per-repo PR to ship every shared-hook update (versus a single line in each child's `settings.json`).
- Two distinct mental models in flight whenever some children are copy-resident and others are symlink-style.
- Drift is permanent — no compile-time check that all copies are in sync with the parent's source of truth.

If you find a child repo using copy-resident hooks during routine work, file a tracking issue and align on the next hook-sync wave's plan rather than mixing the cleanup into an unrelated PR.

### Anti-pattern: empty child config

A child repo that participates in hook-gated workflows (commits, PRs, merges) MUST have a `.claude/settings.json` registering at least the parent dispatcher and matcher hooks relevant to that repo's surface (Edit/Write for sources, SendMessage for cross-repo coordination, etc.). An **empty child config** is a silent gap — hooks the parent enforces simply don't fire in that repo. Audit during wave-kickoff and file `tech-debt` if any in-scope repo is empty.

### Reviewer enforcement

When a PR adds or modifies a child repo's `.claude/settings.json`, reviewers verify:
- Each hook entry uses an absolute path into `noorinalabs-main/.claude/hooks/`, not a relative path.
- No new `.py` hook files are added to the child's `.claude/hooks/` (the dir should be empty or contain only child-local hooks specific to that repo's surface — none currently exist).
- Coverage matches the parent's matcher list for the equivalent surface (e.g., a child with code-editing tools should register PreToolUse Edit/Write hooks that the parent registers for the same purposes).

### Caveats acknowledged

- Symlink-style is fragile to parent-dir layout changes — but the org-canonical workstation layout (`/home/parameterization/code/noorinalabs-main/...`) has been stable since project inception.
- Symlink-style breaks when a child repo is cloned standalone OUTSIDE the parent. Hooks fail to invoke (no matching path); the harness gracefully falls through (no hook = allow). Document this in any per-child-repo CLAUDE.md that anticipates standalone cloning.
- Hook updates require a child-side `settings.json` edit when hook count changes (new hook added; matcher consolidation per § Dispatcher Consolidation Policy). This is one line per child — significantly cheaper than the per-repo PR cost the copy-resident pattern imposes.

### Promotion provenance

Surfaced during execution of [#194](https://github.com/noorinalabs/noorinalabs-main/issues/194) (Hook 14 sync to 7 child repos) — Aino's survey found 3 copy-resident, 3 symlink-style, 2 empty across the 7 child repos. Owner-greenlit the canonicalization 2026-04-27. Phase 1 (this section, charter codification) lands in P3W4. Phase 2 (per-child-repo sweep migrating the 3 copy-resident repos to symlink-style + scaffolding any empty repos) is tracked separately for P3W5. See [#214](https://github.com/noorinalabs/noorinalabs-main/issues/214).

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

### 5. Parser-Fixture Coverage Requirements

Every hook with input parsing MUST have test fixtures covering all known input shapes. New input shapes discovered in production (e.g., a `head_ref` shape the parser doesn't recognize, a quoting style that trips shlex, a YAML edge case) require fixture-add backport BEFORE the bug-fix PR can merge — the fixture pinning the new shape lands together with the parser fix in the same commit.

**Rationale:** P3W6 surfaced 4 hook parser bugs in a single wave (#285 /wave-kickoff Step 1 EXISTING_SHA captures 404 body; #287 validate_commit_identity false-blocks backslash-line-continuation; #289 validate_workflow_paths_coverage misparses bare `on.pull_request:`; #294 validate_pr_review skips reviewer counting on `deployments/*/wave-*` heads). All four are parser bugs in production hooks discovered AT runtime when an unanticipated input shape arrives. Fixture-with-fix discipline pins the new shape so future regressions surface in CI.

**Acceptance:** PR introducing a parser-bug fix MUST include the new fixture in the same commit. CI (or hook authors during review) flags PRs that change parser logic without an accompanying fixture addition.

**Dispatcher-style children (no committed `.claude/hooks/`):** Children that delegate all hook execution to the parent canonical via `settings.json` are exempt from per-child fixture requirements. Coverage obligations are fulfilled by the parent's test suite. A child is classified as dispatcher-style when `gh api repos/<owner>/<repo>/git/trees/<head_sha>?recursive=1` returns 0 entries under `.claude/hooks/`. Design-system and landing-page (post-W5) are the canonical exemplars.

### 6. Promotion Provenance Phrasing

Every hook's charter entry includes a provenance block describing where the hook came from. The `/promotion-audit` skill's `find_already_promoted` parser scans these blocks to decide which memories / charter rules / skill patterns have already landed as hooks. Ambiguous phrasing defeats the parser (false-negatives produce noisy AUTO classifications; false-positives produce noisy ALREADY-PROMOTED classifications). Three required parts:

**Backward claim (required):** a single sentence declaring backward provenance — what prior tier (memory / charter / skill / pattern) this hook was promoted from. Example:

> Promoted from memory `feedback_enforcement_hierarchy.md` via charter § Ontology Librarian Rule (PR #153).

Every hook MUST have exactly one backward-claim sentence. The parser's `_PROVENANCE_RE` and `_HTML_COMMENT_PROMOTED_RE` recognizers extract memory / charter / skill references from this sentence, so it MUST cite the source artifact by filename (memories: `feedback_X.md` or unsuffixed `feedback_X`; skills: `/skill-name`; charter rules: `CLAUDE.md § X` or `charter/X.md § Y`).

**Forward references (optional, must be in a separate paragraph):** if the hook's charter entry mentions sibling hooks, future artifacts, or design narrative, that narrative MUST live in its OWN paragraph — never co-located with the backward-claim sentence. Example forward reference:

> Worked example referenced by the future `/promotion-audit` skill design.

**Why separate paragraphs:** `find_already_promoted`'s `_FORWARD_REFERENCE_MARKERS` filter (`future`, `planned`, `design`, `upcoming`, `referenced by`, `will reference`, `proposed`, `TBD`) excludes slash-command hits that sit within ~60 chars of these markers. Forward-reference narrative mixed into the backward-claim sentence makes that filter trip on the backward citation too — turning a real promotion record invisible. Keeping the two concerns in separate paragraphs is the simplest discipline that preserves both meanings.

**Recognized parse keys:** the literal tokens `/promotion-audit` scans for. Author your provenance block with one of these as the opener so the parser finds it:

- `**Promotion provenance:**` — block-style header; the parser's `_PROVENANCE_RE` greedy-matches until the next blank line / heading. Used by hooks.md per-hook entries (e.g. Hook 15).
- `Promoted from` — opening token recognized inline; works inside either the block-style entry or a standalone sentence.
- `<!-- Promoted from memory: X -->` — HTML-comment marker form codified in #283 / #393. Used for charter-tier-only promotions (no corresponding hook). The parser's `_HTML_COMMENT_PROMOTED_RE` (DOTALL) captures the body up to `-->`, so trailing context (date, retro citation, rationale) is included in the regex sweep.

**Rationale:** PR #155 added the reactive `_FORWARD_REFERENCE_MARKERS` filter to handle Hook 15's own provenance block — which had narrative referencing a future skill mixed in with the backward citation. The filter is the runtime safety net; this guidance is the preempt-at-author-time fix that reduces future filter-edits. Sibling of #393 (HTML-marker convention) — this section catalogues the parse keys; the authoritative shape-selection rule (when to use HTML-comment vs. bold-prose) lives at [`charter/skills.md` § Promotion Pipeline Marker Convention](skills.md#promotion-pipeline-marker-convention).

**Enforcement:** The Standards & Quality Lead (Aino) verifies these requirements during hook PR review. A hook missing any of the six requirements must not be approved.

## Hook Audit Protocol

When auditing a repo's hook ownership status (hook-owning vs. dispatcher-style):

1. Fetch the committed tree:
   ```
   gh api repos/<owner>/<repo>/git/trees/<head_sha>?recursive=1 \
     --jq '[.tree[].path | select(startswith(".claude/hooks/"))]'
   ```
2. Classification: if the result is empty (`[]`), the repo is dispatcher-style. If non-empty, it is hook-owning.
3. Filesystem enumeration (SSH, `ls`, `find`) is NOT a valid substitute — it includes untracked files, worktree artifacts, and gitignored content that are invisible to git.

**Rationale:** P3W7 produced 3 repo misclassifications from a single root cause: auditors enumerated working-directory files instead of querying the committed git tree. Misclassified repos: design-system, user-service, data-acquisition — all initially called "stale-mirror hook-owning" but confirmed dispatcher-style via committed-tree inspection. The correct method is one API call away.

**Enforcement:** Any audit-finding comment that asserts a repo's classification must cite the `gh api .../git/trees` invocation it ran (or the equivalent `gh api .../contents/.claude/hooks?ref=<sha>` form). Reviewers reject classification claims sourced from `ls`, `find`, SSH, or local checkout.
