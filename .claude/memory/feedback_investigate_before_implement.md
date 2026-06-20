---
name: feedback_investigate_before_implement
description: "When an implementer brief diagnoses a problem class but doesn't cite specific origin-state evidence, origin-audit before any Edit/Write — the diagnosis may be stale or wrong, and re-implementation on a stale brief creates divergent-fix churn."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 77e35de5-3b28-48a1-92f6-f413bc8debac
---

When an implementer brief asserts a problem-class diagnosis ("tag-trigger issue", "auth misconfiguration", "missing handler") but does NOT cite specific evidence at origin head (workflow content, run history, commit shas, comment URLs), the implementer MUST origin-audit BEFORE any Edit/Write. If the audit contradicts the brief, surface findings + a path-recommendation back to the brief author; do NOT silently re-implement on the stale brief.

**Why:** P3W11 ds#81 (publish pipeline) 2026-05-19. Team-lead's brief diagnosed the issue as "tag-trigger or auth" and recommended option 2 (add `on.push.tags: ['v*']`). Origin audit revealed: the fix was already shipped on wave-10 via Maeve's PRs #77 + #80 with a strictly broader shape (push on main + deployments/** + tags `v*` + idempotency guard), two successful push-trigger publish runs had ALREADY landed `0.0.4-wave10.0` on the registry, and the actual remaining gap was wave-10→main merge sequencing (not workflow code). Implementing the brief as written would have:
1. Duplicated wave-10's existing fix on wave-11 → divergent-fix history.
2. Created merge conflict on whichever wave-branch merged to main last.
3. Produced ~30min of PR-write + reviewer time + the merge-conflict risk for zero net work.

Escalation with full origin audit → team-lead pivoted to Path C (close ds#81 as already-resolved). Net: zero wasted implementer cycle, zero divergent-fix.

**How to apply:**
- **Cue: brief has a problem-class verb but no evidence URL/sha.** "fix the X gap", "investigate why Y stopped", "resolve the Z race" — without "verified at origin head <sha>" or a comment-URL — is the trigger to origin-audit FIRST.
- **What to audit:** the file/workflow/system the brief names, at the branches relevant to the fix (default branch + active wave branch + any branches the brief mentions). Compare states. Check run history if it's a workflow. Check git log for the named file across the recent window.
- **When the audit contradicts the brief, escalate — do not silently re-implement.** Format: "brief said X; origin shows Y; here are 2-3 paths forward; recommending P; standing by." NEVER proceed with destructive setup (worktree creation, commits) before getting acknowledgment that the path is still desired.
- **Crossed-messages guard:** if the brief arrives AFTER you sent an escalation message and doesn't acknowledge that escalation, send a one-line check-in citing the prior escalation before destructive setup. The brief may have been composed before your escalation was read.
- **Sibling rule:** [[feedback_verify_diagnosis_before_delegating]] covers the orchestrator-class version (verify before spawning); this is the implementer-class counterpart (verify before implementing what you were spawned to do). Both reduce to: API state and prose claims are intermediated views; origin head is ground truth.
