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
