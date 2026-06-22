---
name: feedback_statuscheckrollup_ci_clean
description: "Never claim \"CI clean\" from local-test-pass alone — `gh pr view <N> --json statusCheckRollup` is the single authoritative check before any PR-state report"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 77e35de5-3b28-48a1-92f6-f413bc8debac
---

Before reporting a PR as "all green" / "CI clean" / "ready for review", run:

```
gh pr view <N> --repo <repo> --json statusCheckRollup --jq '[.statusCheckRollup[]? | {name, conclusion}]'
```

Every conclusion must be `SUCCESS` or `SKIPPED`. Local `npm test`, `npm run build`, `pytest`, `ruff` etc. do NOT cover the CI surface (security-audit, secret-scan, registry-auth, snapshot-drift, lockfile-validation, integration-only jobs).

**Why:** P3W11 isnad-graph#840 PR #924 (2026-05-19) — I reported "all PR-time gates green" after local install+build+test+lint, but didn't check origin. CI was actually red on `security-audit` (idna CVE, orthogonal-deferred) AND `frontend-lint-and-test` (workflow auth 401 — directly caused by my pin bump moving the resolution path to GitHub Packages without consume-side auth wiring). Team-lead caught both. Same trap fired earlier the same day on us#127 (trivy surprise). Companion to `feedback_refresh_before_status_claim` but specifically for the local-tests-pass-but-CI-fails axis.

**How to apply:**
- Every "ready for review" or "CI clean" message → run the rollup query first and include the per-check status table in the message.
- Polling discipline for in-flight CI: use the Monitor tool with a poll-until-completed loop emitting each check's status transition, exit when all `status == completed`. Don't sleep-loop.
- After `gh pr create` → wait for CI checks to land before sending the "PR open" report; or open the PR with explicit "CI pending, will follow up" framing.
- Local-tests-only verifications belong in the PR body's Test Plan as `[x]` items; CI verification gets a separate `[ ]` line in a `CI acceptance` section that the reviewer flips after re-checking.

**Extension (main#802, P6W1 retro, owner-approved 2026-06-21):** an **empty** `statusCheckRollup` (`[]` — "no checks reported") is a HARD not-ready state, NEVER green — readiness requires the rollup be **non-empty AND all-success**. Origin: design-system #129's silently-dropped `synchronize` event produced zero runs that a "no failing checks" test would have passed. Codified in `charter/state-claims.md` § Empty `statusCheckRollup` Is Hard Not-Ready; the deterministic oracle is `.claude/lib/pr_ci_state.py` (exit 0=ready / 1=not-ready / 2=undeterminable; empty→not-ready unconditionally), reusing the merge gate's `validate_pr_ci_status.classify_rollup`. The merge gate itself blocks an empty rollup when a covering unfiltered-`paths` workflow exists (the #129 case) and warn-allows it on a fully path-filtered repo (no deadlock for `noorinalabs-main`/`deploy`).

Related: [[feedback_refresh_before_status_claim]] (state-claim refresh), [[feedback_refresh_before_status_claim]] (specific to PR state field set).
