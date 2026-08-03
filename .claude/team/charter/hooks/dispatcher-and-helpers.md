# Hooks — Dispatcher & Shared Helpers

> Part of the [hooks charter index](../hooks.md) — re-shelved from `charter/hooks.md` for section-level loading (#963). Rules unchanged.

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

## Shared Helpers <!-- promotion-target: none -->

Reusable primitives that multiple hooks (or hooks + skills) consume. Each helper has a single-source-of-truth implementation under `.claude/hooks/` with an underscore-prefix filename (`_<helper>.py`) marking it as internal, not a hook itself.

### `_shell_parse.py` — Tokenize Bash commands safely

Multiple PreToolUse hooks need to detect command shapes (`git commit`, `gh pr create`, etc.) without regex'ing the raw command string — a pattern that has repeatedly mis-fired on heredoc bodies, code-fence blocks, and `--body-file` argument values (issues #118, #134, #144, #188, #189, #216, #223, #226, #227). The helper exposes `tokenize`, `strip_heredocs`, `iter_command_segments`, `find_git_subcommand`, `find_gh_subcommand`, and `extract_dash_c_pairs`. Consumed directly by `validate_commit_identity`, `validate_branch_freshness`, `block_git_config`, `block_no_verify`, `block_shutdown_without_retro`, `block_stale_tmp_message_file`, `validate_review_comment_format`; and transitively by `post_wave_kickoff_comment` + `post_label_change_wave_field_sync` (both via the domain-shape `_wave_label_parse` helper below). When a new transcript-or-command-reading hook needs to discriminate command shape, consume this helper rather than regex.

### `_wave_label_parse.py` — Parse `gh issue edit ... --add-label|--remove-label "<wave-label>"`

Two PostToolUse Bash hooks need to detect when a wave label is being added or removed on a GitHub issue: `post_wave_kickoff_comment` (posts a charter-format kickoff comment on label-APPLY) and `post_label_change_wave_field_sync` (syncs the project 2 Wave field on label-ADD or -REMOVE). The shape they each match — `gh issue edit <num> --add-label|--remove-label "p{N}-wave-{M}"` with arbitrary flag ordering, both two-token and equals forms, compound pipelines, and tolerated extra non-wave-label flags — is the same; duplicating the parser would re-introduce the regression class the `_shell_parse` consolidation closed in P3W4 (#226 #227 #223 #216 #188 #189 #144).

The helper exposes `parse_wave_label_change(command) -> WaveLabelChange | None` (returning a frozen dataclass with `repo`, `issue_number`, `add_label`, `remove_label`), `is_wave_label(value) -> bool`, `parse_wave_label_spec(value) -> WaveLabelSpec | None`, `wave_label_to_option_name(value) -> str | None`, and `parse_wave_label(value) -> (phase_num, wave_num) | None`.

**Wave-label grammar (main#810, completing Design B #804).** Three forms are accepted everywhere: legacy `p{N}-wave-{M}` (anchored `^p\d+-wave-\d+$`, grandfathered), phase-agnostic global `wave-{X}` (`^wave-\d+$`, the going-forward form), and the `wave-x` placeholder. All are fully anchored, so suffixed values like `p3-wave-10-special` or `wave-10-frozen` are out-of-pattern. `is_wave_label` / `parse_wave_label_spec` / `wave_label_to_option_name` accept all three; `parse_wave_label` is **legacy-form-only** (its `(phase, wave)` tuple cannot express a missing phase — new forms return `None`). `WaveLabelSpec` carries `(raw, phase|None, wave|None, is_placeholder)`. Option-name mapping: `p{N}-wave-{M}`→`P{N}W{M}`, `wave-{X}`→`W{X}`, `wave-x`→`WX`.

**Promotion provenance:** Extracted from `post_wave_kickoff_comment.py`'s pre-#445 `parse_label_apply_command` during Hook 21 implementation (PR #446, issue #445). The extraction is behavior-preserving for `post_wave_kickoff_comment` (verified by running its existing 30-test suite both pre- and post-refactor — identical pass/fail counts and test names). Follows the `_shell_parse.py` consolidation precedent from P3W4 #226/#227/#223/#216/#188/#189/#144 — when ≥2 hooks need the same input shape, extract a shared helper rather than duplicate.

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

### `_hook_main.py` — Standalone-invocation `main()` bodies (`run_blocking` / `run_advisory`)

Every hook script is also invoked STANDALONE (`python3 <hook>.py`) — by the CI smoke-test step, by an author testing manually, and by any hook that is registered directly in `.claude/settings.json` rather than dispatched — independent of whether the same `check()` function is ALSO reached in-process via `dispatcher.py`/`post_dispatcher.py`. Before main#1121, 35+ hooks each hand-rolled the ~12-line stdin-decode / call-`check()` / emit boilerplate for that standalone path, and a file-by-file read found the boilerplate was not actually identical — three distinguishable exit-code shapes coexisted (see `_hook_main.py`'s own module docstring for the full audit). One hook (`validate_wave_label_evidence.py`) had no malformed-stdin guard at all and crashed (exit 1, traceback on stderr) on empty/invalid stdin instead of the exit-0 every other hook guaranteed — closed by the consolidation.

**API:**
- `run_blocking(check_fn, hook_name)` — standard `main()` body for a PreToolUse gate hook that can block. Exit 0 = allow, 2 = block (iff `check_fn(input_data)` returns a dict with `result.get("decision") == "block"`); any truthy result is printed as JSON regardless of decision.
- `run_advisory(check_fn, hook_name)` — standard `main()` body for a hook that can never block the tool call (every PostToolUse hook, plus the few PreToolUse/SendMessage hooks that are advisory-only, e.g. `validate_wave_context.py`). Always exits 0, even if `check_fn` returns a `decision: "block"`-shaped dict — branching on `decision` there would be dead code for the wrong contract, not a no-op.

**Malformed-stdin and exception policy (identical for both helpers):** empty stdin (`EOFError`), invalid JSON (`json.JSONDecodeError`), or stdin bytes that don't decode under the process locale (`UnicodeDecodeError` — not previously guarded by any hook; real defense on a strict-errors or non-UTF-8 locale, though inert under this org's default `surrogateescape` stdin error mode) all exit 0 silently. A `check_fn` exception is caught and treated exactly like a `None` result (allow / no advisory) — it can never surface as a traceback, matching the hard "a hook must never crash" contract — and is **recorded** (not silently dropped) to Annunaki's `traces.jsonl` via `log_pretooluse_diagnostic`. Recorded is not the same as surfaced: `traces.jsonl` is excluded from `annunaki_parse`'s default read and both `/annunaki` and `/annunaki-attack` are documented to skip it during routine sweeps (deliberate — folding it into the counted-error stream would re-create the #625 over-count) — a swallowed `check_fn` exception is retrievable evidence for someone already debugging a specific hook, not something that appears in a routine error count. Surfacing it there is tracked separately (#1331).

**Use this helper** when authoring a new standalone-invocable hook. Do NOT hand-roll `json.load(sys.stdin)` / `sys.exit(2)` — every hand-rolled instance is one more chance at the exit-code drift main#1121 collapsed.

**Not every hook fits this helper.** Excluded and why (see the current `_UNCONVERTED` mapping in `test_hook_registration_coverage.py` for the enforced, up-to-date list): a `main()` whose standalone-invocation path genuinely differs from its `check()` (e.g. `validate_edit_completion.py`, whose `SendMessage`-matcher registration calls its block-check unconditionally while `check()` filters by `tool_name` for the dispatcher); a `main()` with its own stronger exception-reporting contract (`auto_add_issue_to_board.py` and siblings log a `check_fn` exception to the **counted** `errors.jsonl` via `log_posttooluse_event`, not the informational `traces.jsonl` this helper uses); or a `main()` that deliberately discards `check_fn`'s return value (`annunaki_monitor.py`, `ontology_tracker.py` — side-effect-only, the return value is meaningful only to the dispatcher's own aggregation). Converting one of these requires either accepting its behavior change explicitly or adding a helper variant (e.g. an injectable exception-log callback, or an explicit tool-name allowlist) — never a silent `run_blocking(check, ...)` swap.

**Promotion provenance:** main#1121 (code-audit item G9, epic main#1097). `test_hook_registration_coverage.py`'s `_UNCONVERTED` mapping (added in the same track) is the enforced source of truth for which hooks are NOT yet on this helper and why — this section is the discoverability half, the test is the enforcement half.

