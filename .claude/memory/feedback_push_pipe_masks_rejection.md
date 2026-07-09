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

Sibling of [[feedback_silent_zero_is_not_a_measurement]]: there the probe could not return nonzero; here the *status channel* is severed from the thing you are measuring. Same root — **verify the instrument before trusting the reading.**

**How to apply:**
- **Never pipe a command whose exit status you intend to read.** Not `git push`, not `gh`, not a gate script, not a linter. Redirect instead: `cmd > /tmp/out.txt 2>&1; echo "rc=$?"`, then `cat` the file.
- `set -o pipefail` helps in a script you control and **does not help in an ad-hoc agent Bash call**, where zsh is the shell and the option is not set. Do not rely on it.
- For any command with a side effect — a push, a comment, a label, a merge — **read the effect back from the origin**, not the exit code. `rc=0` from `gh` proves nothing about GitHub's state. Pairs with [[feedback_refresh_before_status_claim]] and [[feedback_gh_pr_edit_silent_noop]].
- Never pipe `git push` through a pager/filter. Run it bare so its exit code surfaces, or capture: `git push ... ; echo "rc=$?"` and assert rc==0.
- After any force-push, read-back-verify: `git ls-remote origin <branch>` (or `gh api .../git/refs/heads/<branch>`) == local HEAD before claiming the PR reflects your latest commit. Pairs with [[feedback_refresh_before_status_claim]].
- `set -o pipefail` does NOT fully save you here — `tail` still exits 0 after consuming git's stderr; the real fix is don't pipe the push.
