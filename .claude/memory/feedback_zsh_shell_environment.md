---
name: feedback_zsh_shell_environment
description: "User's dev environment uses zsh — write zsh-safe Bash-tool commands, avoid bash-only syntax"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 15a12bf4-b5ee-402a-b58e-2d227e5b733b
---

The user's development environment uses **zsh** (the Bash tool's login shell is zsh). Write shell commands that run under zsh; do not assume bash.

**Why:** Owner explicitly asked me to remember this (2026-05-28), right after a `declare -A` / `${!arr[@]}` associative-array loop failed with `(eval):3: bad substitution` during the P3W12 branch cleanup. zsh's associative-array and array-index syntax differs from bash, so bash-only idioms silently break.

**How to apply:** Avoid bash-isms that zsh rejects or treats differently:
- No `declare -A name` associative arrays or `${!arr[@]}` key expansion → use paired strings + `while IFS=: read -r k v` loops, or plain newline-delimited lists.
- zsh arrays are 1-indexed and don't word-split unquoted vars by default; prefer explicit loops over relying on bash word-splitting.
- When a one-off needs bash specifically, invoke `bash -c '...'` explicitly rather than assuming the default shell is bash.
- POSIX-portable constructs (`for x in ...; do`, `case`, `[ ]`) work in both and are the safe default.
- **Unquoted-scalar word-splitting is the recurring footgun:** `set -- $spec` and `for x in $scalar` do NOT split on whitespace in zsh — `$spec` is treated as ONE field, so the loop/positional-set silently sees one value. zsh-safe: feed a newline-list into `while IFS= read -r x; do …; done` or use an explicit array `"${arr[@]}"`. (This is distinct from the safe `$VAR/path` / `$VAR/*.py` glob-prefix form, where the glob — not word-splitting — does the expansion.)
- **`$status` is a read-only special variable in zsh** (alias for `$?`); never use `status` as your own loop/temp variable name — assigning it errors `read-only variable: status`. Use `st`, `rc`, etc.

## `git show "$SHA:tests/..."` is SILENTLY CORRUPTED in zsh (2026-07-09)

zsh applies **history/parameter modifiers** after `$VAR:` — and it does so **inside double quotes**, where every other shell would leave the string alone. Measured:

```
HEAD_SHA=d96266f470e8...
print -r -- "$HEAD_SHA:tests/x"
  -> d96266f470e8...cests/x            # the `t` was eaten by the `:t` (tail) modifier
git show "$HEAD_SHA:tests/test_exit_codes.py"   ->  rc=128, "ambiguous argument"
```

`tests/` is the most common path prefix in any repo, and `:t`, `:h`, `:r`, `:e`, `:a`, `:l`, `:u`, `:q`, `:s`, `:g`, `:x` are all live. **The failure is not the `rc=128` — it is what follows it.** An engineer piped that `git show` into `grep -c`, which counted an empty stream and printed **`0`**: a silent zero, from a broken command, inside the check being run to prove a fix had reached origin. He nearly went looking for a lost push.

**How to apply:**
- Never write `git show "$VAR:path"`. Use `git show "${VAR}:path"` (braces terminate the parameter name before the colon), or better `git show "$VAR" --  path` / `git cat-file -p "$VAR:path"` with the path built separately.
- The same trap hits any `"$VAR:..."` string you build for a tool that takes `rev:path`, `host:path` (`scp`, `rsync`), or `repo:tag`.
- **Always instrument a `grep -c` over a command substitution**: assert the byte/line count is non-zero, or that a string you *know* is present is found, before believing a count of `0`. See [[feedback_silent_zero_is_not_a_measurement]] — a zero from a command that never ran is not a measurement.

Sibling of [[feedback_push_pipe_masks_rejection]] § *a tool silently transformed your input and reported success*. Four members now: the pipe (exit status), `re.sub` (replacement string), an unquoted heredoc (message body), and `$VAR:` modifiers (the argument itself). **A shell that rewrites your argument does not tell you.**

**Enforcement (memory→hook promotion, 2026-06-25, owner-requested, main#879/PR#880):** the unquoted-scalar word-split class is now caught by an **advisory** PreToolUse Bash hook `.claude/hooks/warn_zsh_wordsplit.py` (registered in `dispatcher.py`). It flags `set -- $scalar`, `for VAR in $scalar`, `${!indirect}`/`${!arr[@]}`, and `mapfile`/`readarray`, emitting a `systemMessage` with the zsh-safe rewrite. It is **advisory, not blocking** (word-split reliance is sometimes intentional; a hard block would create false-positive friction on hundreds of Bash calls), and is command-position + word-boundary aware so it does NOT fire on quoted forms, globs, command substitutions, or `$VAR/path` glob-prefixes. Per [[feedback_enforcement_hierarchy]] (hook > skill > charter), this is the durable enforcement of the prose guidance above.
