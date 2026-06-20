---
name: feedback_sync_gate_build_kind_false_match
description: "pre_commit_ci_sync.py `build`-kind pattern false-matches `Set up Docker Buildx` / `docker build` step names — unsatisfiable drift in docker-publish repos"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: d8a5fc5c-6b55-468a-b0a0-23817f47074f
---

The vendored `.claude/lib/pre_commit_ci_sync.py` (#327 sync-drift gate) classifies a CI `build` kind via substring patterns incl. `"docker build"`. That substring FALSE-MATCHES `- name: Set up Docker Buildx` (the buildx SETUP step name) and any `docker buildx build` runtime publish line. Result: a repo whose only `build`-ish CI is a docker-image-publish workflow gets a `build` CI-kind that NO local pre-commit hook can mirror → permanent harmful-drift, gate never exits 0.

**Why it matters / how it hid:** isnad-graph #938 masked it — `ci.yml` also has a legit `- run: npm run build` (real frontend build-quality check, mirrored by a `frontend-build` pre-push hook), so the gate happened to exit 0 even though the ghcr-publish `Set up Docker Buildx` line was false-matching. A docker-ONLY repo (no npm build) would be stuck. Aisha (data-acquisition track) surfaced the general form 2026-05-31.

**How to apply:** TIGHTEN the gate's single `build` pattern so bare `docker build` / `docker buildx` / "Set up Docker Buildx" do NOT classify as build-quality, while keeping real detection (`build-and-validate`, `build-and-test`, `npm run build`). Do NOT scope the gate to dodge it. Every batch-2 repo with a docker/ghcr-publish workflow is exposed — pre-flight by tracing `kinds_from_ci` and checking whether any `build` hit comes from a step `name:` rather than a `run:` `docker build .` invocation. Context: sibling to [[feedback_test_mock_masks_prod_failure]] (a passing gate masking a real classification bug).

**RESOLVED (2026-05-31):** the canonical fix simply DROPS `"docker build"` from the `build` tuple → `("build-and-validate", "build-and-test", "npm run build")` (no run-step special-casing needed; a genuine docker-build-quality-gate should be NAMED `build-and-validate`/`build-and-test`). Landed in `noorinalabs-deploy#391` (Aisha, unit-tested both directions); applied to isnad-graph #938 (commit 3991004) aligned byte-for-byte on the pattern + comment. Parent-canonical re-vendor is `noorinalabs-main#576` — it will OVERWRITE all interim vendored copies org-wide, so exact byte-match across repos isn't required, only correct (resolved-not-masked) exit 0. Mark PR-body notes proposed-canonical referencing #576.
