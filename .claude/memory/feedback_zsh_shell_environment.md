---
name: feedback_zsh_shell_environment
description: "zsh gotchas NOT covered by the hook/docs: `\"$VAR:path\"` history-modifier corruption inside double quotes (the `git show $SHA:tests/…` trap), and `$status` being read-only. General zsh-safety is owned by docs/TOOLCHAIN.md § Shell environment + the warn_zsh_wordsplit hook (main#879)."
metadata:
  type: feedback
---

The dev environment's shell (interactive AND the Bash tool) is **zsh**. The general do/don't list (no `declare -A`/`${!arr[@]}`, quote URLs/globs, POSIX-portable default, explicit `bash -c` when needed) is owned by `docs/TOOLCHAIN.md` § Shell environment + `ontology/conventions.md`, and the unquoted-scalar word-split class is hook-enforced by `.claude/hooks/warn_zsh_wordsplit.py` (advisory PreToolUse, main#879/PR#880). This memory keeps only the gotchas NOT covered there:

## `git show "$SHA:tests/…"` is SILENTLY CORRUPTED (2026-07-09)

zsh applies **history/parameter modifiers** after `$VAR:` — **inside double quotes**, where every other shell leaves the string alone. `"$HEAD_SHA:tests/x"` eats the `t` via the `:t` (tail) modifier → `git show` rc=128 "ambiguous argument". `:t :h :r :e :a :l :u :q :s :g :x` are all live, and `tests/` is the most common path prefix in any repo. The real damage: the broken `git show` was piped into `grep -c`, which counted an empty stream and printed **0** — a silent zero inside a push-verification check; the engineer nearly went hunting a lost push.

- Never write `cmd "$VAR:path"`. Use `"${VAR}:path"` (braces terminate the name), or `git show "$VAR" -- path` / `git cat-file -p` with the path built separately.
- Same trap for any `rev:path`, `host:path` (`scp`, `rsync`), `repo:tag` argument.
- Instrument any `grep -c` over a command substitution: assert non-zero bytes or a known-present string before believing a `0` — [[feedback_silent_zero_is_not_a_measurement]].

## `$status` is read-only

`$status` is zsh's alias for `$?`; assigning to it errors `read-only variable: status`. Never use `status` as a loop/temp variable — use `st`, `rc`.

**In a long-running Monitor this fails at the worst possible moment (da#488, 2026-07-25).** A Monitor watching a ~6.5h resolve re-run polled cleanly for hours, because the assignment `status="$(rg -o run_status …)"` lived in the **terminal-classification branch** — the branch that runs exactly once, when the watched process finally exits. At that moment the monitor died with `read-only variable: status` and exit 1 **instead of emitting the ✅ COMPLETE line**, failing precisely at the finish line it existed to catch.

The general shape: **a bug on a rarely-taken branch survives every test of the happy path.** Where a Monitor's entire value is a single terminal event, the terminal-detection branch is the one piece that never gets exercised in routine iterations — read it line by line, or force it once against a already-finished process, before trusting a long watch. Sibling of [[feedback_silent_zero_is_not_a_measurement]]: both are failures that report success (or report nothing) rather than erroring where you are looking.

## `path` is TIED to `$PATH` — assigning to it clobbers your PATH (2026-07-19)

zsh ties the lowercase array `path` ↔ the scalar `PATH` (like `fpath`, `cdpath`, `manpath`). A plain `path="$dir/$sub"` in a loop **overwrites `$PATH`** with that one string → every subsequent bare command in the shell dies with `command not found: git` (etc.), while the *same* command run standalone (fresh shell) still works. The failure looks like a flaky/sandbox PATH glitch, not a variable-name collision. Cost this session: a `/wave-wrapup` worktree-cleanup loop using `path="$base/$wt"` made `git worktree remove` fail 8× with "command not found" before the tie was spotted; renaming to `wtp` fixed it instantly. Never use `path` (or `cdpath`/`fpath`/`manpath`) as an ordinary variable — use `wtp`, `p`, `dir`. Sibling of `$status` above; both are zsh special-parameter collisions the `warn_zsh_wordsplit` hook does not catch.

Sibling of [[feedback_push_pipe_masks_rejection]] § *a tool silently transformed your input and reported success* — the pipe (exit status), `re.sub` (replacement string), an unquoted heredoc (message body), and `$VAR:` modifiers (the argument itself). **A shell that rewrites your argument does not tell you.**
