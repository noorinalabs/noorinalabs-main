---
name: feedback_verify_diagnosis_before_delegating
description: Before spawning an agent on a fix, verify the diagnosis against git/file reality — not just API state. Subagents will (correctly) refuse fixes that contradict ground truth, wasting a spawn cycle.
type: feedback
originSessionId: d4c5c2e9-b16d-47b6-ae4f-1943f0b1b95f
promotion_target: charter
promotion_threshold:
  retro_citations: 3
status: active
---
When the diagnosis points at a "fix the broken thing" path, the orchestrator MUST verify the broken thing IS broken — not just that an external API surface (GH workflow state, response codes, log absence) suggests it might be. Subagents that find the orchestrator's diagnosis contradicts git history are RIGHT to refuse and report back, but it costs a spawn cycle and reviewer trust.

**Why:** On 2026-04-21, the orchestrator delegated #162 ("notify-deploy.yml stopped firing") to Jelani Mwangi with a diagnosis that the workflow had been silently de-registered by GH. Jelani checked git log and found the file was deliberately DELETED in #821 (folded into ghcr-publish.yml). Re-creating it would have re-introduced the race condition #821 closed. Jelani refused, reported back. Real bug was a one-line event-type name mismatch between sender and listener after a repo rename — a totally different fix. The wasted spawn cycle came from the orchestrator skipping `git log -- <file>` before concluding the workflow was orphaned.

**How to apply:**
- Before delegating any "the workflow/file/system is broken" fix: run `git log --oneline -- <path>` and read the most recent commit touching it. If recent activity contradicts the surface symptom, the diagnosis is wrong.
- Cross-repo dispatch chains: when sender reports success but listener doesn't fire, the failure mode is almost always a server-side filter (event-type names, branch filters, ref filters) — verify both ends' configs match BEFORE assuming PAT/secret/registration issues.
- For deploy-chain debugging specifically: check the LISTENER's run history with `--event=repository_dispatch` filter. Zero such runs while sender reports success = name mismatch or filter mismatch, not auth failure.
- **Upstream-channel disagreement (extends the same principle):** when two upstream sources (program director via teammate message, Contract owner via GitHub comment, two peer managers relaying) disagree about a decision you're about to relay or act on, treat the diff as a signal to check the canonical artifact — not to guess which upstream is fresher. On 2026-04-23 (W10 image-tag Contract), Marcia paused before accepting Boukhari's v3 message because Khoury's most recent direct message had endorsed an earlier shape; fetching the #815 comment (4301425114) directly confirmed v3 was ruled, and a third-revision relay was caught before it became a fourth-revision downstream scope correction. Khoury's diagnosis of the root cause: fan-out paraphrase-relay of a single-source artifact. Fix: cite the canonical artifact URL, don't paraphrase.
- General principle: API state and teammate paraphrases describe intermediated views; git history, GitHub-comment artifacts, and versioned `## Contract vN` posts are ground truth for what was intended/decided. When they disagree, the canonical artifact wins.
