---
name: feedback_owner_pivot_supersedes_protocol
description: Owner/PD/team-lead pivots reversing prior routing on in-flight tasks must carry explicit supersedes-as-of header; receiver must refresh state at origin before executing or surface convergent-state instead of reversing artifacts destructively. Charter-promotion candidate via /promotion-audit at end-of-wave.
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 80ad8eee-00ce-46cf-924e-13907f259631
---

When the team-lead, PD, or owner issues a "supersedes prior routing" SendMessage that reverses a previously-issued routing on an in-flight task, the message MUST carry an explicit supersedes-header AND the receiving manager MUST refresh state at origin before executing OR surface convergent-state if the prior routing has already produced an artifact.

**Why:** 8 converging-decision races observed in single P3W10 session at high coordination tempo. SendMessage latency (~1-3min) + execution latency (5-30sec) means pivot decisions made on stale state are inevitable. Without an explicit protocol, managers either (a) execute on stale routing and produce a convergent state that satisfies no one's intent cleanly, or (b) reverse already-produced artifacts destructively (re-open closed issues, churn audit-trails, send close-then-reopen notifications). The protocol forces (c) surface-and-confirm as the third path.

**How to apply** — three sub-rules:

**Sender protocol** (team-lead, PD, owner issuing the pivot):
1. First line of the SendMessage MUST be `supersedes <prior routing as of <ISO-8601 timestamp>>`.
2. Pivot SendMessage MUST be sent within 60 seconds of the reverse-decision being made (so the receiving manager can refresh state at origin and reach the same conclusions before executing).
3. Authority hierarchy: owner > PD > team-lead. Pivots from a higher authority supersede pivots from lower authorities. Lower-authority pivots that arrive AFTER a higher-authority supersedes-pivot are no-ops; ack but do not execute.

**Receiver protocol** (manager receiving the pivot):
1. Refresh state at origin (`gh issue view N`, `gh pr view N`, `git log` on relevant branch) BEFORE executing on the pivot. The 1-3min message latency means the state may have changed since the pivot was decided.
2. If the prior routing has already executed and produced an artifact (issue closed, comment posted, PR merged, branch deleted, etc.), surface as a **convergent-state problem** rather than reversing the artifact destructively. Provide three options (α accept-as-is / β destructive-reverse-with-explicit-re-authorize / γ alternative-routing-of-original-intent) and await explicit authorization before any destructive action.
3. Provide the original-routing's receiving subject (e.g., the persona who was supposed to execute the pedagogical-routing version) with a concrete alternative path if the original training/pedagogical/coordination intent can no longer be satisfied.

**Authority hierarchy clarification (Pivot authority sub-rule)**:
- Owner pivots: authoritative, supersede all lower; receiver MUST execute or surface convergent-state.
- PD pivots: supersede team-lead pivots but defer to owner; receiver MUST refresh state and execute unless owner pivot intervenes.
- Team-lead pivots: defer to PD and owner; receiver checks for prior PD/owner pivots before executing.
- Within same authority level, latest-timestamped supersedes-pivot wins (per the protocol's ISO-8601 header).

**Race counter for context** — P3W10 session (2026-05-13):
1. #67 routing race (PD original-message vs team-lead crossing)
2. PR #93 reviewer-slate "you're her r2" ambiguity (PD self-correcting)
3. #73 W11-slip-then-Z-ruling-revert (PD vs team-lead vs owner)
4. PR #94 1/2-Approved → Anika silence → team-lead-ping recovery (latency masking, not race)
5. Anika #62 dispatch sequencing (manager vs team-lead authority overlap)
6. PR #93 mergeable=UNKNOWN transient post-#93-merge (gh CLI cache, not race)
7. #64 a/b/c routing race (Marcia recommend (a) → team-lead approve (a) → owner pivot to Cédric → Marcia already closed → α accept-as-is)
8. Cross-persona-task-claim hazard via task-system mistyping (Marcia accidentally completing Marisol's task #56)

[[feedback_cwd_collision_cross_spawn]] is the sibling W10 charter-promotion-target memory (cwd-collision chain Nadia→Wanjiku→Aino + Nazia self-recovery). Both promote together at /promotion-audit alongside the stale-snapshot scope-pre-kickoff-audit pattern (#67 + #64) and [[feedback_cross_persona_task_claim_hazard]] (task-system mistyping, task #56 incident).

**Promotion path**: /promotion-audit at end-of-wave picks this up via memory→charter pipeline (PR #422 precedent). Split into 3 sub-rules at promotion-time (Sender / Receiver / Authority hierarchy) for citation clarity per team-lead's recommendation 2026-05-13.

Related memories: [[feedback_bundle_fixup_instructions]] (serial-send drop risk), [[feedback_refresh_before_status_claim]] (state-refresh discipline), [[feedback_stale_inbox_manager]] (artifact-vs-inbox truth-source), [[feedback_gh_cli_gotchas]] (read-back-verify post-write).
