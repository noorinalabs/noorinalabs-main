---
name: feedback_actionlint_needs_shellcheck
description: actionlint silently skips its shellcheck integration if the binary isn't on PATH locally — local "clean" claim can be wrong vs CI
type: feedback
originSessionId: 2e011116-89b1-4ac2-b2fc-1d5649d609c7
promotion_target: charter
promotion_threshold:
  retro_citations: 3
status: active
---
When validating workflows locally with `actionlint` before pushing CI changes, the binary **silently skips** its `shellcheck` integration if `shellcheck` isn't on PATH. Result: local dry-run reports clean, CI catches `SC2129`/`SC2086`/etc. on the same files.

**Why:** Bereket caught this on deploy#176 — claimed "clean against all 13 workflows" but CI flagged 4 SC2129 violations. The local actionlint binary on this machine had no shellcheck installed, so `run:` block linting was a silent no-op. Public-facing "validated locally" claim was therefore false.

**How to apply:** Before running `actionlint` locally for any CI gate work, verify shellcheck is on PATH:

```sh
which shellcheck || {
  cd /tmp && curl -sL https://github.com/koalaman/shellcheck/releases/download/v0.10.0/shellcheck-v0.10.0.linux.x86_64.tar.xz | tar -xJ && cp shellcheck-v0.10.0/shellcheck /tmp/shellcheck
}
PATH="/tmp:$PATH" actionlint -color
```

`sudo apt-get install shellcheck` won't work without a TTY in this env — use the static binary download.

Generalizes: any linter that opportunistically integrates with another tool (eslint→prettier, ruff→mypy, etc.) needs the dependency verified before claiming "local pass = CI pass."

**Second-order limit (P3W11 deploy#336 2026-05-18):** even with shellcheck on PATH, actionlint does NOT validate the *internal CLI-flag syntax of programs invoked inside `run:` blocks*. Lucas's PR #336 passed local actionlint + shellcheck but failed CI on all 5 tflint jobs because the run-payload `tflint --recursive=false` is invalid tflint syntax (`--recursive` is a bare bool, can't accept `=value`). Actionlint validated YAML + shell syntax fine; the bug was in the meaning of the tool-specific flag, which is out-of-scope for any linter that doesn't know tflint's flag taxonomy. Mitigation: when bumping a pinned 3rd-party tool inside CI, run `<tool> --help` of the pinned version locally before push, and add a workflow comment naming the actionlint-can't-validate-this surface so future bumps remember.
