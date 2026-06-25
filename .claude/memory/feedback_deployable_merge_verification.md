---
name: feedback_deployable_merge_verification
description: a wave→main / push-to-main merge is a DEPLOYABLE merge; verify its post-merge-only workflows (publish/Trivy) went green with verify_deployable_merge.py — a green PR is not proof, those gates never run on the PR.
metadata:
  type: feedback
---

A **deployable merge** (any wave→main or push-to-main merge) triggers workflows
that **never ran on the per-issue PRs** — container publish + its Trivy image
scan, schema-drift, structural-ontology, etc. They trigger on
`push: branches: [main]` (and/or tags) but **not** `pull_request`, so they give
**zero pre-merge signal**. A fully-green PR can therefore redden `main` the
moment it merges.

**Why:** Owner directive 2026-06-24 — "check deployable merges complete
successfully as a matter of regular practice." Surfaced by **isnad-graph#1131**:
`#1130`'s PR was green, but the post-merge GHCR publish failed on a
freshly-published base-image CVE (`libexpat` CVE-2026-45186 in the alpine
runtime base). `gh pr merge` returns 0 the instant the merge commit exists —
long before these workflows even start — so the merge's own exit status proves
nothing. Eyeballing `gh run list` is the manual step that rots
([[feedback_enforcement_hierarchy]]).

**How to apply:**
- After any deployable merge, run the deterministic oracle
  `python3 .claude/lib/verify_deployable_merge.py <owner/repo> <merge-sha> --require-deployable`
  (exit 0 verified / 1 not-verified / 2 gh-error). It polls the Actions runs for
  the exact `head_sha`, requires the post-merge-only workflows to be present AND
  green, and a **no-red safety net** fails on ANY run that executed and went red.
  A required workflow that produced **no** run is a hard not-verified (empty ==
  not-ready, [[feedback_statuscheckrollup_ci_clean]]). "Nothing required" (a meta
  repo with no post-merge-only workflow) → exit 0 via the net alone.
- It is wired into `/wave-wrapup` **Step 11.5a** (after the reachability gate,
  before the staging gate): a red/dropped post-merge workflow blocks wave close.
- A merge a is a **branch** push: tag-only workflows (e.g. isnad-graph's
  `Pipeline`, `push: tags: [data-v*]`) and path-filtered push workflows are
  excluded from the required set (the net still covers them if they fire).
- **Fix forward, don't override**, when the red is the wave's own fault. The
  Step 11.5a override (`DEPLOYABLE_VERIFY_OVERRIDE_RATIONALE`) is ONLY for a
  documented external/standing red — advisory-DB-vs-mirror drift
  ([[feedback_pip_audit_strict_advisory_db_drift]]) or a no-fix base-image CVE
  under an active `--ignore-vuln` ([[feedback_trivy_base_image_cve_org_wide_gate]],
  [[project_bleach_redos_standing_item]]) — and it MUST name a tracking issue.

Base-image OS CVEs whose fix exists upstream are re-pinned (newer digest), not
ignored: isnad-graph#1132 re-pinned `nginx:stable-alpine3.23` 3.23.4→3.23.5 to
pull `libexpat 2.8.1-r0`. Tracking: main#864 (tool), isnad-graph#1131 (the CVE).
Related: [[feedback_local_ci_parity_no_force]], [[feedback_cross_repo_wave_ref_resolution]].
