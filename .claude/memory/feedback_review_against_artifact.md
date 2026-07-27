---
name: feedback_review_against_artifact
description: Reviewer-class discipline — read diff/code at PR head directly (gh api contents), not through PR body claims, commit messages, or cited line numbers. Catches false-positives, drift, and silent obsolescence.
type: feedback
originSessionId: 0428d30b-2e2b-46d2-8837-1f3aa9705c5f
promotion_target: charter
promotion_threshold:
  retro_citations: 3
status: enforced-elsewhere
superseded_by: charter:pull-requests.md § Trust the Artifact, Not the Framing
superseded_at: 2026-05-06
---
When reviewing a PR, read the **artifact at PR head** as the source of truth — not the PR body's framing, the commit messages, or the line numbers the author cites.

**Why:** Bereket-named at P3W1 retro-prep 2026-04-30 as the load-bearing reviewer-class discipline. Three high-value catches in one wave came from this single shape:

1. **#206 USER_SERVICE_URL/SITE_URL false-positive (Aisha→Lucas review):** caught by reading `caddy/Caddyfile@PR-head` directly — line 88-89 (user-service rewrite) vs line 101 (`/health` → isnad-graph). PR body framed the dual-route fallback as safe; artifact showed `/health` on shared host hits isnad-graph, not user-service. Real false-positive bug, not theoretical.

2. **#210 runbook L161 + compose 614-621 drift (Lucas→Aisha review):** caught by reading the runbook + compose blocks themselves rather than following Bereket's "all five items addressed" claim from the v3 review. Two pre-cloud-init-bake-in leftover paragraphs survived through 3 review cycles before this catch.

3. **#210 cloud-init runcmd ordering:** verified `cc_users_groups → cc_runcmd` cloud-init phase semantics directly (not from Aisha-posted "ordering is correct" claim). That's how the bootstrap-perms loop closed end-to-end.

Distinct from Pattern B (verify-spec-against-ground-truth) at the implementer vantage — same shape, reviewer side.

**How to apply:**

- For every PR review, fetch the file at PR head via `gh api repos/<owner>/<repo>/contents/<path>?ref=<head_sha>` (NOT local clone — [[feedback_canonical_source_via_git_show]]: the worktree can be pre-merge while origin holds the canonical version). Read the actual lines.
- For "is X still there" claims, grep the artifact, don't trust the PR body's "removed in this PR" assertion.
- For ordering / sequencing claims (cloud-init runcmd, GH Actions step DAG, compose service depends_on), verify the actual semantics from upstream docs / standard conventions, not the author's "ordering is correct" prose.
- For env-var / config wiring claims, trace producer → consumer through the actual file references (e.g., compose env var → workflow `envs:` allowlist → script body), not through the PR body summary.
- The PR body is the author's **framing**, useful for orientation. The artifact is the **truth**, load-bearing for verdict.

Companion to:
- [[feedback_canonical_source_via_git_show]] (use gh api / `git show <sha>:<path>` at HEAD, not local clone)
- `feedback_refresh_before_status_claim` (refresh PR state before any "still at X" assertion)
- [[feedback_verify_3p_integrity]] (don't claim a tool verifies SHA without grepping its source)
- `feedback_verify_diagnosis_before_delegating` (Pattern B implementer-side equivalent)
