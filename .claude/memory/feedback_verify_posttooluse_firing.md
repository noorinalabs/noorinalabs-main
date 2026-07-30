---
name: feedback_verify_posttooluse_firing
description: Verify PostToolUse hooks actually fire (annunaki entry / side-effect) before relying on Hook 21 / Hook 13 / annunaki_monitor signal in autonomous batch work
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 5b706bb7-9eef-4d28-a853-f891b79822cc
---

Before relying on a PostToolUse hook to do work for you (Hook 21 setting Wave field, Hook 13 adding to board, annunaki_monitor logging errors), **verify the hook is actually firing in the current session**.

**Why:** P3W11 resume session 2026-05-17 — Hook 21 hotfix #449 was merged, direct `check()` calls worked, dispatcher shell-invoked worked, but Claude Code's actual PostToolUse Bash hook did not fire on real `gh issue edit` calls. Result: 5+ ops fired with no Wave field set, manual GraphQL compensation required, batch paused. Session was running under `claude --dangerously-skip-permissions` with `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` on v2.1.143 — exact trigger condition still under investigation (tracked in main#453; the original pointer was to `session_handoff.md`, which is gitignored/machine-local and so never resolves for another reader).

**How to apply:**
- At session start, after `/session-start`, fire one disposable test that SHOULD log to annunaki (e.g., `ls /nonexistent/path`) and verify a new entry appears in `.claude/annunaki/errors.jsonl`
- If no entry appears → PostToolUse is broken in this session → switch to compensate-as-you-go pattern (manual GraphQL mutations directly, never trusting Hook 21 to fire) OR restart the session to see if it self-heals
- Same applies for ANY autonomous batch work that depends on PostToolUse side-effects: validate the surface before the batch, not during

**Pattern class:** This is the inverse of [[feedback_declarative_head_needs_action]] — instead of "merged code needs explicit action to take effect," it's "merged hook needs the harness to actually invoke it before you can trust its automation." Both share the orchestrator-trust-the-merge fallacy.

Companion to [[feedback_test_mock_masks_prod_failure]] — different vector but same outcome (unit tests passed for #449 hotfix, dispatcher direct-call passes, actual harness path silently no-ops).

See also: [[feedback_refresh_before_status_claim]] for the artifact-verification general case.
