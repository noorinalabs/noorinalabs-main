---
name: feedback_passing_repro_masks_bug
description: "A local reproduction that PASSES can mask the real bug when the repro accidentally uses a different (correct) invocation form than production runs — reproduce the FAILING form, not just a passing one. Companion to test-mock-injection-masks-production-failure."
metadata:
  node_type: memory
  type: feedback
  originSessionId: 090bf6d5-0d19-47c9-9b85-67bfff1c5396
---

P4W3 deploy#423/#424/#425 (2026-06-12): the promote.yml v2 stg-verify gate had **never** been able to pass. Real cause: verify_digest extraction wrote `python3 -c "…os.environ['K']…" K="$key"` — `K="$key"` is a trailing **argv** to python3, NOT an env assignment, so `os.environ['K']` raised `KeyError`, swallowed by `2>/dev/null || echo ""` → verify_digest EMPTY for every service → false "N-of-N divergence." The first RCA (Aisha) blamed a trailing `\r` and #424 shipped a whitespace-strip — verified "working" by a local repro and approved by 2 reviewers — yet the post-merge promote still failed at the same gate. The "passing" repro had accidentally used the **env-prefix** form `K="api" python3 -c "…"` (which resolves correctly), masking the real bug. The 1-line real fix (#425) moved `K` to a prefix; #424's strip stayed as harmless defense-in-depth.

**Why:** a reproduction is only evidence if it exercises the EXACT failing invocation. An accidentally-correct repro form produces a green result for the wrong reason and "confirms" a wrong RCA, costing a full file→review→merge→re-run round-trip (and would have waved a still-broken gate through to the owner's prod-approval if the post-merge promote hadn't been re-checked).

**How to apply:**
- When an RCA claims "I reproduced it and the fix works," verify the repro reproduces the **FAILING** state first (red), THEN that the fix flips it green. A repro that only ever shows green proves nothing.
- For shell/CI gate bugs especially: copy the **exact** command form from the workflow (argv vs env-prefix vs heredoc vs quoting), not a hand-retyped approximation — subtle invocation differences (env-prefix vs trailing-arg, `K="x" cmd` vs `cmd K="x"`) silently change semantics.
- Brief reviewers of a "fix verified locally" PR to independently run BOTH the broken and fixed forms themselves, not approve on the PR-body framing. (Lucas + Weronika did this on #425 and caught/confirmed the mechanism; they had approved #424 on the wrong RCA.)
- Inline workflow bash with no unit-test seam is the standing enabler — a small extracted python/script helper around extract+equality would have caught both the CR theory and the real bug. Companion: [[feedback_test_mock_masks_prod_failure]].
