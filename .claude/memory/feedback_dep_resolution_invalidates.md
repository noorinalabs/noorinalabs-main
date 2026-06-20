---
name: feedback_dep_resolution_invalidates
description: "When a PR changes how a dependency resolves (file → registry, pin → range, lockfile re-gen), audit UNCHANGED workflow steps in the same touched files — pre-existing steps may have become dead weight or security-regressive without showing in the diff"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 77e35de5-3b28-48a1-92f6-f413bc8debac
---

When reviewing a PR that changes a dependency-resolution path — e.g., switching from local `file:../pkg.tgz` to registry-published `https://npm.pkg.github.com/...`, bumping a pin, regenerating a lockfile — the **unchanged** steps in the touched workflow/script files MUST also be audited. Their behavior may have silently invalidated even though they don't appear in the diff.

**Why:** Diff-only review (especially the security-review lens) reads only the `+`/`-` hunks. But CI workflow steps frequently make assumptions about the resolution state of nearby steps — "step A produces local tarball X; step B strips stale integrity hash from lockfile; step C runs install." When a PR changes how step C resolves the dependency, the implicit contract between A, B, and C breaks even though A, B, and C are textually unchanged. The PR's diff looks clean; the security posture regresses.

**How to apply:**

For reviewer-class agents (especially security reviewers) when the PR description mentions dep-resolution changes, lockfile regen, pin bumps, or registry switches:

1. Read the FULL workflow/script file at the PR head, not just the diff hunks. Use `gh api repos/.../contents/<path>?ref=<head_sha>`.
2. For every step that references the same dependency (by name, registry, lockfile section), ask: "is this step still doing something useful, dead weight, or actively wrong under the new resolution path?"
3. Specifically watch for: (a) checkout/build/pack steps producing artifacts the new lockfile no longer references → dead weight; (b) integrity-stripping or auth-bypassing steps that worked around the OLD resolution path's quirks → may regress security under the NEW path; (c) cache/restore steps keyed on the old resolution path's artifacts → cache miss every build.

Sibling to [[feedback_review_against_artifact]] (read the artifact at head, not the PR-body framing) and [[feedback_consumer_against_in_flight_upstream]] (dual-axis verification for cross-layer state).

**P3W11 isnad-graph PR #924 (2026-05-19):** Auth wiring to consume `@noorinalabs/design-system@0.0.4-wave10.0` from GH Packages flipped lockfile resolution from `file:../../noorinalabs-design-system-0.0.1.tgz` to a registry URL with a legitimate sha512 integrity hash. The PR diff was clean and Idris's security review approved it. Ingrid (engineer-class with frontend/dependency-management lens) caught that the workflow STILL contained three pre-existing step blocks per job:

- checkout design-system at `ref: v0.0.1` (now dead — produces a tarball nothing references)
- build + `npm pack` it (now dead — same)
- "Fix lockfile integrity" step that **strips** the integrity field from `lock.packages['node_modules/@noorinalabs/design-system']` (originally stripped a stale `file:` integrity; now strips the **legitimate registry sha512** → removes tampering protection on the very package the PR is meant to harden)

Idris's review was diff-correct; he missed the unchanged-steps interaction because his lens stopped at the diff hunk boundary. Engineer-class second reviewer was necessary to catch this.
