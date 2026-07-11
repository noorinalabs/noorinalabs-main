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

## The orchestrator's own unverified assertion is the most dangerous input in the room (2026-07-11, deploy PR #594)

The rule above is about verifying a diagnosis *before* delegating a fix. This is the sibling failure: **stating as fact, inside a spawn brief, something you merely expected to be true.**

I told an implementer to fold a second defect into a push. He didn't. I then told **both reviewers**, in writing, that he had — without ever looking. Nino re-derived from the shipped code instead of believing me, found the `fresh` row untouched, and blocked. **Had he trusted the brief, a runbook telling an operator "nothing to do" over a corrupt backup dump ships to production.**

Why this asymmetry matters: a reviewer discounts the PR author's claims by default — that is the job. **Nobody is calibrated to discount the orchestrator's.** A false premise from the person assigning the review is laundered into the review's starting assumptions and disappears. My statement was, functionally, a Changes-Requested item marked resolved by fiat.

Compounding it, in the same ten minutes:

1. **The `|| echo` false-confirm.** My verification one-liner was `gh api … | base64 -d | grep -n undersized || echo ">>> ZERO matches"`. The `gh api` call **errored**; jq emitted nothing; `grep` matched nothing *because it was handed nothing*; and the `||` branch printed a confident **">>> ZERO matches — the fix is NOT in this head."** It was right by accident. A failed fetch and a genuine absence produce **the identical line.** Same defect class as the `--limit` board query, the void mutation run, and the mention-weighted A/B — *a check that cannot distinguish "I looked and found nothing" from "I never looked."* Fix: fetch to a file, gate on the fetch's own rc, and run a **positive control** (grep a term that MUST be present) before believing a zero.
2. **A grep for the right word in the wrong place would have "confirmed" my claim anyway.** `undersized` *does* appear in the runbook — in the `absent` and `incomplete` rows. It was missing only from the `fresh` row, which is the entire defect. **A keyword search is not a check for semantic presence.** The word being there proved nothing.
3. **I invented a teammate's surname** ("Nurul Rahman"; he is **Nurul Hakim**) and put it in two briefs as the Requestee — violating [[feedback_brief_author_verify_roster_surname]], which exists *because I did this before*. Hook 4 roster-validates the name; it would have bounced.

**How to apply:**
- Any factual claim about the state of a PR/branch/file that you put in a brief must be **verified at origin at the sha you are naming**, or explicitly marked as unverified: *"I asked him to fold X in — check whether he did; I have not."* Uncertainty stated is free. Uncertainty concealed is a defect with your signature on it.
- Instruct reviewers to **derive, not transcribe** — and mean it about your own claims too. Nino's block exists only because the brief said "derive it rather than take my word," and he took that literally. Keep that sentence in every brief.
- When you are wrong, **send the correction before anything else** — a reviewer acting on a superseded premise is worse than one with no premise. Reverse it explicitly ("supersedes my previous message"), name what you failed to do, and do not soften it into "turns out."
- Never write a `cmd || echo "not found"` verification. The `||` fires on *error* as readily as on *absence*.
