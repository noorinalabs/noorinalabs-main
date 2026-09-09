---
name: feedback_same_persona_resident_coordinator_double_gates
description: "A coordinator agent left resident under a persona that is ALSO the merge-gate reviewer on an in-flight PR will act on a re-anchor addressed to the gate agent and post a second counted verdict under the same name; the hook collapses same-persona verdicts, so a disagreement between the two would be invisible."
metadata:
  type: feedback
last_verified: 2026-09-08
---

**Observed 2026-09-08, wave-31 batch 2, PR #1512.** The Program Director agent (`nadia-pd-w31-batch2`, spawned for scoping and idle) and the spawned merge gate (`nadia-gate-1512`) both ran the Opus gate re-review under the single persona **Nadia Khoury** and both posted counted `Approved` verdicts 45 s apart — after the orchestrator sent ONE re-anchor addressed to the gate agent. Both approvals were independently reproduced and agreed, so the merge was sound (`resolve_review_verdicts` counts the latest verdict per *persona*). The two reviews nonetheless reached **different conclusions on a follow-up** (#1515's remedy), and under one Requestor name a reader cannot tell that is two reviewers disagreeing. Filed as [#1516](https://github.com/noorinalabs/noorinalabs-main/issues/1516).

**Why:** the ≥1-Opus safeguard and the hook both assume *persona == agent*. A resident coordinator that shares a persona with a gate reviewer is a second, unbooked reviewer on every PR that persona gates. Had the two disagreed, the hook would have counted whichever landed last and the extractor would never show the conflict — the #1193/#1197 shape (one persona, two agents) recurring on the orchestration side, and the mechanism that delivered the re-anchor to both is **not established** (recorded as observed, not diagnosed).

**How to apply:**
- Before a PR's merge gate runs, make sure no *other* live agent carries the gate persona. Either stand the coordinator down first (its final report is already in hand), or assign the gate to a persona no resident agent holds. The scope matrix's slate is a *persona* assignment; the orchestrator owns the *agent* bookkeeping.
- Address re-anchors to the gate agent's spawn name and verify in `ListAgents` that exactly one agent under that persona is `running` before and after.
- At merge time, when `resolve_review_verdicts` shows a persona with ≥2 counted verdicts in the same head window, read both comments before merging — agreement is not guaranteed.
- **Stop an agent only after its side effects have landed at origin, not after seeing them locally.** The same session stopped the Program Director agent (to clear the gate persona) right after seeing its "record batch 3" commit in the main checkout — but its push had not run yet. `origin/main` stayed one commit behind for ~40 minutes; an implementer branched from local `main` and its PR opened showing two commits, and a same-session `pull --ff-only` had silently reported the local tip as if it were origin's. Before `TaskStop` on an agent that commits: `git fetch origin && git status -sb` must show `main...origin/main` with no `[ahead N]`. If it is ahead, push the already-authored commit yourself, then stop the agent.
- Related: [[feedback_spawn_brief_protocol]] §8 (cite the verdict URL, never "your prior verdict"), [[feedback_agent_liveness_signals_are_unreliable]], [[feedback_no_head_sha_in_review_briefs]].
