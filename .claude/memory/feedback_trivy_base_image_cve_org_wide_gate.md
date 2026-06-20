---
name: feedback_trivy_base_image_cve_org_wide_gate
description: "user-service ghcr-publish build-and-push can fail on a NEW base-image OS CVE (Trivy), not your code — pre-existing/org-wide, not PR acceptance."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 080813cd-f3b8-434d-974c-badf58620c96
---

The user-service `ghcr-publish.yml` `build-and-push` job runs a **Trivy image scan that fails the build (exit 1) on HIGH/CRITICAL CVEs in the Debian base image** (`debian 13.x`). A CVE disclosed AFTER the last green run will fail EVERY PR opened that day against this repo, with zero relation to the PR's code. Example: P4W2 PR#156 (us#153/#154 OAuth guard) — `build-and-push` FAILURE on **CVE-2026-45447 (HIGH, `libssl-dev`, debian 13.5, fixed in next point release)**; the same job was GREEN on the base branch + main on 2026-06-09, CVE landed 06-10/06-11.

**Why:** It's an OS package gate keyed on base-image freshness, not code. Matches [[feedback_runtime_gate_scoping]] (env-state gate ≠ PR acceptance) and [[feedback_artifact_gate_non_blocking]].

**How to apply:** When `build-and-push`/Trivy fails, check the Trivy table Target column — if the vuln is in `(debian X.Y)` / an OS package (libssl, etc.) and python-pkgs show 0, it's the base image, NOT your change. Verify pre-existing: `gh run list --workflow ghcr-publish.yml` — was it green on base/main before the CVE date? The code gates that DO matter are `check` (ruff+mypy+pytest), `openapi-snapshot-drift`, and the sync-drift gate. Fix = Dockerfile base-image bump → separate deploy/infra issue, don't block the feature PR. Also: dev-only extras (e.g. `testcontainers`) stay OUT of the runtime image, so they don't add image CVEs (Trivy showed python-pkgs all 0). See [[feedback_runtime_gate_scoping]].
