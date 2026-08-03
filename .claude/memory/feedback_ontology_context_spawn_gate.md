---
name: feedback_ontology_context_spawn_gate
description: "Worktree-isolated Agent spawns are BLOCKED (exit 2) unless the prompt carries a '## Ontology Context' heading — but the gate exempts any brief whose opener names a coordinator TITLE, so persona choice silently decides whether the requirement applies."
metadata:
  type: feedback
last_verified: 2026-08-03
---

`.claude/hooks/enforce_ontology_context.py` (PreToolUse on `Agent`) blocks a spawn with **exit 2** when `isolation == "worktree"` and the prompt contains none of its `ONTOLOGY_MARKERS` — the practical one being the literal heading **`## Ontology Context`**. Telling the agent to "run `/ontology-librarian` as your first action" does **not** satisfy it: the hook reads the *prompt you are sending*, not what the agent will later do. Both obligations are real and separate — the heading unblocks the spawn, and the agent's own `/ontology-librarian` invocation satisfies Hook 15, which scans the agent's own transcript.

**Non-worktree spawns are never gated** (`isolation != "worktree"` returns allow immediately). So reviewer spawns, which run non-isolated, need no heading.

## The trap: the exemption is keyed on the persona TITLE, not the task

`COORDINATOR_ROLE_OPENER` matches `You are <name>, <title>` at an exact line start, where `<title>` ∈ {`Pipeline Manager`, `Project Lead`, `Program Director`, `Technical Program Manager`, `TPM`, `Release Coordinator`, `Manager`}, and returns allow **before** any marker check.

Measured 2026-08-03, one batch, three implementer briefs, all `isolation: worktree`, all instructing code edits + a PR, none carrying the heading:

| opener | result |
|---|---|
| `You are **Nino Kavtaradze**, Security Engineer (Senior), implementing…` | BLOCKED |
| `You are **Weronika Zielinska**, Platform Architect (Staff), implementing…` | BLOCKED |
| `You are **Nadia Khoury**, Program Director, implementing…` | **ALLOWED** |

Nadia then did the same class of work as the two that were blocked. `Standards & Quality Lead` is **not** in the list — Aino briefs are gated like any implementer.

**How to apply:** put a real `## Ontology Context` block (actual `ontology/structural/llms.txt` section content, not a placeholder) in every worktree-isolated implementer brief, regardless of persona. Do not rely on the coordinator exemption — when it fires it is silent, so a coordinator-titled implementer ships with no ontology context and nothing signals it. Filed as [#1264](https://github.com/noorinalabs/noorinalabs-main/issues/1264).

**Why:** the exemption's premise — coordinator-class spawns don't write code — is an unenforced assumption. In this org the Program Director is a normal implementer on parent-repo tech-debt rows. Same defect shape as [[feedback_silent_zero_is_not_a_measurement]] and #1180: a classifier whose permissive branch is the default, keyed on the wrong attribute.

Related: [[feedback_spawn_brief_ontology_first]], [[feedback_child_repo_spawn_no_isolation]] (the other spawn-time isolation trap — child-repo work must be non-isolated, which also incidentally skips this gate).
