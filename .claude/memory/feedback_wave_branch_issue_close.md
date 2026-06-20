---
name: feedback_wave_branch_issue_close
description: GitHub's `Closes #N` PR-body linkage only auto-fires on merges into the repo's default branch. PRs into a wave branch (`deployments/phase-2/wave-N`) merge cleanly but leave the referenced issue OPEN. Always `gh issue view <N>` post-merge to verify; if open, `gh issue close <N> --comment "Resolved by PR #M (sha ...)"` explicitly.
type: feedback
originSessionId: 2e011116-89b1-4ac2-b2fc-1d5649d609c7
promotion_target: skill
promotion_threshold:
  retro_citations: 3
status: active
---
GitHub's `Closes #N` / `Fixes #N` / `Resolves #N` PR-body keywords only auto-close the referenced issue when the PR merges into the repo's **default branch**. PRs that merge into any other branch (feature branch, wave branch, release branch) close the PR but leave the issue OPEN, even with the closing keyword in the body.

**Why it matters for wave-flow:** Our standard pattern is feature branch → wave branch (`deployments/phase-2/wave-N`) → main during wave-wrapup. Each wave-secondary PR is merged into the wave branch FIRST. The `Closes #N` linkage is therefore inert at PR-merge time — issues only auto-close when the wave branch finally merges to main during wrap.

**Reproduction (Bereket, 2026-04-28)**:
- Merged 5 PRs into wave-10 (deploy#175 / #176 / #181 / #185 / #177), each with `Closes #N` in body
- Reported all 5 referenced issues "closed" to Nadia + owner + teammates multiple times during the day
- Honest-audit-before-concluded-claim pass discovered ALL 5 issues still OPEN (#122 / #93 / #87 / #96 / #184)
- Closed manually with `gh issue close <N> --comment "Resolved by PR #M (merged into deployments/phase-2/wave-10 at sha <SHA>). Closing manually because the Closes #N linkage in PR body only auto-fires on default-branch merges."`

**Important nuance — some repos have a custom `Auto-close issues` workflow that handles this**:

Idris confirmed (2026-04-28, post isnad-graph#847 merge) that `noorinalabs-isnad-graph` runs a `.github/workflows/auto-close-issues.yml` (run 25055487433 closed isnad-graph#846 at 13:24:43Z, ~6s after the wave-branch merge). The workflow parses `Closes #N` trailers itself and closes via `github-actions[bot]` — independent of GitHub's native default-branch-only behavior.

**Per-repo check before treating "explicit close required" as universal**:
```bash
gh workflow list --repo noorinalabs/<repo> | grep -i "auto.close"
# or
ls -la <repo>/.github/workflows/ | grep -iE "close|cleanup|wave"
```

Known state as of 2026-04-28:
- `noorinalabs-isnad-graph`: HAS auto-close workflow → explicit close is redundant (but harmless/idempotent)
- `noorinalabs-deploy`: **HAS auto-close workflow (confirmed 2026-05-25)** → `github-actions[bot]` closed deploy#346 ~10s after PR #353 merged into `deployments/phase-3/wave-12` ("Closed by PR #353 merged into ..."). So Bereket's 2026-04-28 5-issue miss was the workflow not-yet-existing-or-not-firing then; it works now. Explicit `gh issue close` on a deploy wave-branch-merged issue is now REDUNDANT (no-ops as "already closed") — but verify-it-fired is still wise. NOTE: a manual `gh issue close --comment` that loses the race to the bot will NO-OP the comment too (rationale must go in the PR body, not a post-merge close comment).
- `noorinalabs-user-service`, `noorinalabs-landing-page`, `noorinalabs-design-system`, `noorinalabs-data-acquisition`, `noorinalabs-isnad-ingest-platform`: STATUS UNKNOWN

**How to apply:**
- After merging any PR into a non-default branch, run `gh issue view <N>` for each `Closes #N` reference in the PR body.
- If the issue is still OPEN, close explicitly with a comment citing the merge sha and the wave-branch caveat.
- If you don't know whether the repo has an auto-close workflow, **explicit close is the safe default** — it's idempotent (the second close is a no-op).
- DO NOT report "deploy#X closed" without verification — even if the PR merged with `Closes #X` in body.
- Wave-wrapup automation should re-verify on wave→main merge that all referenced issues either auto-closed or were manually closed prior. Don't leave it to the cascade and assume it works.

**Open W11 audit candidate**: which of the 8 repos have an `Auto-close issues` workflow? Worth a one-shot survey + standardize on universal presence so the explicit-close discipline can be downgraded to "verify worked, don't re-do."

**Promotion candidate**: this is a fourth application site of the verify-against-the-artifact discipline thread surfaced today (alongside multi-layer-gap-filing, integrity-claim-verification, refresh-before-status-claim, origin-over-clone). Worth retro-promoting alongside the other three as a unified "verify state vs. assumed state at every transition" primitive.

**Cross-reference:**
- `feedback_refresh_before_status_claim.md` — top-level discipline
- `feedback_origin_over_local_for_still_has_claims.md` — file-content layer
- `feedback_verify_third_party_integrity_claims.md` — third-party tool integrity layer
- `feedback_multi_layer_gap_filing.md` — multi-issue separation discipline
- This memory — issue-close-state on wave-branch-merge specifically
