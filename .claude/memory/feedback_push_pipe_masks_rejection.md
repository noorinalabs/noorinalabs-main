---
name: feedback_push_pipe_masks_rejection
description: "Piping ANY command whose exit status you intend to read through tail/head/grep masks its failure — the pipeline's status is the LAST command's. Named for `git push | tail` (rejected push reads as success); the same trap hit `gh issue comment | tail` and `structural_ontology.py check | tail` the same day. `; echo rc=$?` after a pipe measures the pager."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: b923c0f4-c87a-4bed-b4b8-91a79287509b
---

`git push ... --force-with-lease | tail` (or `| head`, `| grep`) **hides a rejected push**: the shell pipeline's exit status is the LAST command's (tail = 0), so a non-fast-forward / stale-lease rejection from git reads as success. The agent then believes the branch is updated when the remote still has the old head — and a downstream "PR is green" claim is made against an unpushed tree.

**Why:** P5W4 ig#1044 (Ingrid Lindqvist) — `git push --force-with-lease | tail` returned 0 while the push was actually rejected; only caught because the head didn't move on re-check. Same family as [[feedback_gh_pr_edit_silent_noop]] (silent no-op tooling).

## This is not about `git push`. It is about the pipe. (generalized 2026-07-09)

The memory was filed naming one command, so it was read as a `git push` rule and three people re-derived it on other commands the same evening:

| command | what the pipe hid |
|---|---|
| `git push --force-with-lease \| tail` | a **rejected** push read as `rc=0` (ig#1044) |
| `gh issue comment … \| tail -1; echo rc=$?` | the comment **never posted**; `rc=0` was `tail`'s. Caught only by re-reading the issue at origin — by the same person who had cited this rule to three others ninety minutes earlier |
| `structural_ontology.py check \| tail` | printed **"out of date"** while reporting `CHECK_RC=0`; unpiped it was `rc=1` |

**The rule is: `; echo rc=$?` after a pipe measures the pager, not the command.** `$?` is the pipeline's status, which is the *last* stage's. Anything upstream can fail silently, and the failure text usually still prints — so the output looks like a diagnosis while the status says success. That is what makes it survive review: **you read the words and believe them, and the number you checked was about `tail`.**

This is a POSIX property of the shell, not a frequency observed in the wild. One instance licenses the rule; three merely made it embarrassing.

### `set -o pipefail` WOULD have caught all three. Do not tell people otherwise. (corrected 2026-07-09)

An earlier draft of this memory claimed `pipefail` "does not help." **That is false**, and it is false in the one place a reader will test it. Measured in this environment (`zsh 5.9`, one ad-hoc agent Bash call):

```
false | tail -1                      ; echo rc=$?   ->  rc=0
( set -o pipefail; false | tail -1 ) ; echo rc=$?   ->  rc=1
```

All three rows of the table above are a command that *did* exit non-zero, so `pipefail` recovers every one. A reader who types `set -o pipefail; false | tail`, watches it print `1`, and concludes this memory is wrong will stop trusting the rest of it. **A correct rule resting on a false premise is the least durable kind.**

**The honest case for "redirect, don't pipe" is stronger than the false one**, and it has two legs:

1. **`pipefail` over-reports** on the pipes an agent reaches for most — measured, same shell:
   ```
   ( set -o pipefail; seq 200000 | head -1 >/dev/null ) -> rc=141   # SIGPIPE. head succeeded.
                      echo hi | grep -q nomatch | cat   -> rc=0     # grep's 1 is discarded
   ( set -o pipefail; echo hi | grep -q nomatch | cat ) -> rc=1     # echo succeeded; no-match isn't failure.
   ```
   The `| cat` is load-bearing. With `grep -q` as the **last** stage, `rc=1` in every shell mode, and `pipefail` changes nothing — an earlier draft of this file cited that form as an over-report, which a reader running it would have found false. Aino Virtanen caught it. **The section warning that false evidence destroys the file was the section carrying it.**
2. **`pipefail` cannot catch a command that exits `0` while doing nothing.** `( set -o pipefail; true | tail )` is `rc=0`. That is the entire [[feedback_gh_pr_edit_silent_noop]] family — a `pipefail` pipeline over `gh pr edit` still reports success on a no-op. **This is why "read the effect back from the origin" is the load-bearing bullet, not the exit code.**

And if you genuinely need a pipe with a truthful status, zsh exposes the whole vector: `false | true | false` leaves `pipestatus=(1 0 1)`.

Sibling of [[feedback_silent_zero_is_not_a_measurement]]: there the probe could not return nonzero; here the *status channel* is severed from the thing you are measuring. Same root — **verify the instrument before trusting the reading.**

## The wider family: a tool silently transformed your input and reported success (2026-07-09)

The pipe is one member. Three landed on one engineer in one evening, each reporting `rc=0`:

| tool | what it silently transformed |
|---|---|
| `git push … \| tail` | the **exit status** — a rejected push read as `0` |
| `re.sub(…, replacement)` | the **replacement string** — `\n` escapes eaten, producing unterminated string literals. Recovering with `git checkout HEAD -- file` then destroyed the *uncommitted* work the recovery was for |
| `git commit -F- <<EOF` (**unquoted** heredoc) | the **message body** — zsh executed the backticks. `` `arg.id in registry.__all__` `` ran as a command, `command not found` scrolled past mid-push, and the commit landed with the subject replaced by its empty output |

> **Any layer between you and the thing you meant — a pipe, a regex replacement, an unquoted heredoc, a shell expansion — may rewrite your input and still report success.** The status channel describes the *last* transformation, never the fidelity of the earlier ones.

**Quote the heredoc delimiter** (`<<'EOF'`) unless you specifically want interpolation; if you do want it, keep backticks, `$(...)`, and `$` out of the body. Prefer `-F <msgfile>` written by a tool that does no expansion. For `re.sub`, use a function replacement or `re.escape`, never a raw string carrying backslashes. And **read the artifact back** — `git log -1 --format=%B`, the written file, the pushed ref — because in every one of these the *command* succeeded and the *content* did not survive.

Sibling of [[feedback_gh_pr_edit_silent_noop]]: there the tool did nothing and said so cheerfully; here it did something other than what you wrote.

**How to apply:**
- **Never pipe a command whose exit status you intend to read.** Not `git push`, not `gh`, not a gate script, not a linter. Redirect instead: `cmd > "$CLAUDE_JOB_DIR/tmp/<cmd>_<id>.txt" 2>&1; echo "rc=$?"`, then read the file. **Use a unique path, never a shared `/tmp/out.txt`** — parallel agents clobber each other, per [[feedback_parallel_reviewer_tmp]].
- `set -o pipefail` is **off by default under zsh** and must be set explicitly in the same call: `( set -o pipefail; cmd | tail )`. It then catches an upstream non-zero — but it **over-reports** on `| head` (SIGPIPE `141`) and `| grep -q` (no-match `1`), and it **cannot** catch a command that exits `0` while doing nothing. Prefer redirect.
- For any command with a side effect — a push, a comment, a label, a merge — **read the effect back from the origin**, not the exit code. `rc=0` from `gh` proves nothing about GitHub's state, with or without `pipefail`. Pairs with [[feedback_refresh_before_status_claim]] and [[feedback_gh_pr_edit_silent_noop]].
- After any force-push, read-back-verify: `git ls-remote origin <branch>` (or `gh api .../git/refs/heads/<branch>`) == local HEAD before claiming the PR reflects your latest commit.
