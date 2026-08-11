---
name: feedback_shared_scratchpad_collides_across_agents
description: All agents in a session share ONE scratchpad dir. Concurrent agents dropping production-named files there caused a wrong PR body and a false-green mutation run. Namespace every scratch file.
metadata:
  type: feedback
last_verified: 2026-08-11
---

Every agent spawned in a session writes to the **same** scratchpad directory
(`/tmp/claude-1000/<repo-slug>/<session-uuid>/scratchpad/`). It is not per-agent.
During wave-30, ~20 concurrent agents dropped files there and collided **three
times**, each time producing a confidently wrong result rather than an error.

**1. Wrong PR body (PR #1393).** An implementer's `--body-file` read a path another
agent had just written, so the PR was created carrying a *different* story's
write-up, opening `Closes #1243` — an issue belonging to a different wave-30 PR
that was still in review. Merging would have auto-closed the wrong issue and left
its own unlinked. Nothing flagged it: the PR was well-formed and CI was green.

**2. False-green mutation testing (PR #1394).** A reviewer built a sandbox to
mutation-test `_SHELL_METACHARS`. `_test_helpers.py` computes `HOOKS_DIR` from
`__file__.parent.parent`; under a flattened sandbox layout that resolved **into the
shared scratchpad**, where a stale `validate_labels.py` left by another agent
reviewing the same PR was imported instead of the mutated copy. **Every test passed
with a metachar deleted** — a green board proving nothing. Caught only by diffing
`sys.path` / `sys.modules` mid-test rather than trusting the result.

**3. Confirmed by inspection**: the scratchpad accumulated many production-named
modules — `validate_labels.py`, `_shell_parse.py`, `annunaki_monitor_head.py`,
`api_hook.py` — any of which a path-resolution accident can pick up.

**How to apply:**

- **Namespace every scratch file** with the issue/PR number or the agent's own
  identifier: `pr1393_body.md`, not `body.md`; `mutant_1394_validate_labels.py`,
  not `validate_labels.py`. Never write a file whose basename matches a real
  module the repo imports.
- **Read the file back before consuming it.** For a PR body, assert the first line
  is the expected linkage; for a module copy, assert a known symbol or hash. Both
  incidents above were caught only by reading back.
- **In a test sandbox, reproduce the real directory nesting** (`.claude/hooks/` +
  `.claude/hooks/tests/`). Helpers resolve paths relatively; a flattened layout
  silently escapes the sandbox. Assert the module under test resolves to the path
  you intend — `print(module.__file__)` — before believing any pass/fail.
- **A mutation run whose baseline is not verified green is worthless.** In the same
  session another agent scored 12 import-time corpses as "caught" (its regex
  mutator truncated the literal), and a later run reported 12/12 off a baseline
  that was itself failing with 13 errors. Require: baseline green, each mutant
  `compile()`s, and each mutant kills a *named* test.

Related: [[feedback_gh_cli_gotchas]] §5 (the `--body @file` variant of incident 1),
[[feedback_agent_liveness_signals_are_unreliable]],
[[feedback_graphql_quota_ceiling_on_agent_fanout]] — all four are the same theme:
under high agent concurrency the failure mode is a confident wrong answer, not an
error.
