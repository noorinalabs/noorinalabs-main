---
name: feedback_passing_repro_masks_bug
description: "A local reproduction that PASSES can mask the real bug when the repro accidentally uses a different (correct) invocation form than production runs — reproduce the FAILING form, not just a passing one. Companion to test-mock-injection-masks-production-failure."
metadata:
  node_type: memory
  type: feedback
  originSessionId: 090bf6d5-0d19-47c9-9b85-67bfff1c5396
---

P4W3 deploy#423/#424/#425 (2026-06-12): the promote.yml v2 stg-verify gate had **never** been able to pass. Real cause: verify_digest extraction wrote `python3 -c "…os.environ['K']…" K="$key"` — `K="$key"` is a trailing **argv** to python3, NOT an env assignment, so `os.environ['K']` raised `KeyError`, swallowed by `2>/dev/null || echo ""` → verify_digest EMPTY for every service → false "N-of-N divergence." The first RCA (Aisha) blamed a trailing `\r` and #424 shipped a whitespace-strip — verified "working" by a local repro and approved by 2 reviewers — yet the post-merge promote still failed at the same gate. The "passing" repro had accidentally used the **env-prefix** form `K="api" python3 -c "…"` (which resolves correctly), masking the real bug. The 1-line real fix (#425) moved `K` to a prefix; #424's strip stayed as harmless defense-in-depth.

**Same class, security-guard variant (deploy PR#554, 2026-07-09):** the orchestrator briefed both reviewers to validate the new `RCLONE_*` scrub by setting `RCLONE_LOG_LEVEL=DEBUG` + `RCLONE_DUMP=auth` + `RCLONE_VERBOSE=2` **all at once**. rclone rejects that combination (`CRITICAL: Can't set -v and --log-level`) and exits before doing any work, so it reports **zero leak hits whether or not the guard is present** — a guard test that cannot fail. Aisha caught it, ran a **baseline first** to prove the harness could actually observe a leak, then exercised each vector separately (15 runs: `sh`/`bash`/`zsh` × clean + 4 pollution vectors, against the live B2 endpoint). Nino's per-vector table was sound; only his stated *end-to-end* validation was vacuous. Note the near-miss: the vacuous form was prescribed by the ORCHESTRATOR, in a brief, to two reviewers who had each already done sound per-vector work — a bad verification recipe can un-verify a correct finding.

**Why:** a reproduction is only evidence if it exercises the EXACT failing invocation. An accidentally-correct repro form produces a green result for the wrong reason and "confirms" a wrong RCA, costing a full file→review→merge→re-run round-trip (and would have waved a still-broken gate through to the owner's prod-approval if the post-merge promote hadn't been re-checked).

**How to apply:**
- When an RCA claims "I reproduced it and the fix works," verify the repro reproduces the **FAILING** state first (red), THEN that the fix flips it green. A repro that only ever shows green proves nothing.
- **Applies to security-guard tests too, and to briefs you write.** Before trusting a guard test, run it against the **unguarded** code and confirm it goes red. If it doesn't, the test is vacuous. Beware pollution vectors that are **mutually exclusive** (rclone `-v` vs `--log-level`) or that abort the tool early: setting them together tests nothing. Exercise one vector per run. When *prescribing* a verification in a spawn brief, prescribe the baseline-first step explicitly rather than only the final assertion.
- For shell/CI gate bugs especially: copy the **exact** command form from the workflow (argv vs env-prefix vs heredoc vs quoting), not a hand-retyped approximation — subtle invocation differences (env-prefix vs trailing-arg, `K="x" cmd` vs `cmd K="x"`) silently change semantics.
- Brief reviewers of a "fix verified locally" PR to independently run BOTH the broken and fixed forms themselves, not approve on the PR-body framing. (Lucas + Weronika did this on #425 and caught/confirmed the mechanism; they had approved #424 on the wrong RCA.)
- Inline workflow bash with no unit-test seam is the standing enabler — a small extracted python/script helper around extract+equality would have caught both the CR theory and the real bug. Companion: [[feedback_test_mock_masks_prod_failure]].
