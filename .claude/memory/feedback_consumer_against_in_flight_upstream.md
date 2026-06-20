---
name: feedback_consumer_against_in_flight_upstream
description: "When reviewing a consumer-repo PR that depends on an in-flight (not-yet-merged) upstream PR, dual-axis co-verify the contract — one reviewer reads the upstream source, another reads the upstream's produced distribution/build output. Single-axis review can attest a contract the upstream will change before merge."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 78aadd89-1b9d-4784-9036-6648b56fc712
---

When a consumer-repo PR (e.g., landing-page) depends on an upstream PR (e.g., design-system) that has NOT yet merged, the reviewer-class workflow MUST split into two complementary surfaces:

- **Source-layer reviewer** — reads the upstream PR's source-of-truth (the human-edited tokens / API spec / component code) at its current `head_sha`, attesting that the consumer's expectations match what the upstream author intends.
- **Dist-output-layer reviewer** — reads the upstream PR's *produced artifact* (built package, generated dist, compiled bundle) at the same `head_sha`, attesting that what the consumer will actually import/link against is the same shape.

Both must verify against the upstream's CURRENT `head_sha`, not its PR-body framing or a prior commit. Co-credit both reviewers on the verdict.

**Why:** an in-flight upstream is a moving target — the author may rebase, force-push, or change build tooling before merge, and the consumer is racing on a contract that isn't final. Single-axis review can attest "the contract LGTM" while missing that the dist-output drifts from source (e.g., a tooling regression strips a token, a generator renames an export). Captured on P3W10 PR #96 (noorinalabs-landing-page Cédric OKLCH dark-mode tokens consuming an in-flight design-system change): Anika reviewed the design-system source layer; Nazia reviewed the design-system dist output. Both attestations were required for the verdict to land — single-layer would have missed the dist-source skew.

**How to apply:**

1. Detect the trigger: consumer-repo PR imports/references symbols, paths, or contracts defined in an upstream PR whose `state != MERGED`.
2. Spawn two reviewers in parallel with distinct briefs:
   - Reviewer A (source): "Read `<upstream-repo>/<source-path>` at `<upstream-head-sha>` and attest the contract shape the consumer expects."
   - Reviewer B (dist-output): "Fetch the upstream PR's built artifact (or run its build locally if dist isn't checked in) at the same `head_sha` and attest the symbols/tokens/exports the consumer will actually consume match."
3. Both verdict comments must name the upstream `head_sha` and the artifact path inspected — co-credit them on the consumer PR's merge.
4. If the upstream rebases between the two reviews, BOTH reviewers must re-attest at the new `head_sha`. Stale attestation at superseded SHA does not count.
5. This is sibling to [[feedback-review-against-artifact-not-framing]] (don't trust PR body) and [[feedback-origin-over-local-for-still-has-claims]] (refresh at origin) — both are about reviewer evidence discipline, but this rule covers a specific upstream/consumer race where one layer alone is insufficient.

**Co-credits / first instance:** Anika (source) + Nazia (dist-output) on PR #96 (noorinalabs-landing-page). Authored by Marcia (Project Lead, landing-page) per W10 retro authorization; written into memory by orchestrator under takeover after agent-mass-stall 2026-05-14.
