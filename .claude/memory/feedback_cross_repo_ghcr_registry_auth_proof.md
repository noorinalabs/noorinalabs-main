---
name: feedback_cross_repo_ghcr_registry_auth_proof
description: "Before claiming a cross-repo GHCR/npm-registry auth fix will work (or is blocked), prove the read path with package-visibility + an existing-green-CI-job witness"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: d8a5fc5c-6b55-468a-b0a0-23817f47074f
---

When a Docker/CI build fails fetching a `@noorinalabs/*` package from `npm.pkg.github.com` cross-repo (published from a *different* repo than the one building), the blocker question is **"can this repo's token read that package?"** — and a 401 can mask either a real auth gap OR a never-published 404. Do NOT thrash trying tokens. Prove the path deterministically, in this order, before editing:

1. **Is the version actually published?** `gh api /orgs/noorinalabs/packages/npm/<pkg> --jq '{visibility, repository: .repository.full_name}'` and `.../versions --jq '.[].name'`. Confirms publish + reveals visibility.
2. **Cross-repo read auth:** if `visibility == "public"`, **no per-repo read grant is needed** — any valid token reads it; the default Actions `GITHUB_TOKEN` works cross-repo. If `private`, the package must explicitly grant the consuming repo read access (package settings) OR you need a PAT with `read:packages` — that's an owner/org-settings call, so STOP and report rather than thrashing.
3. **Witness an existing green job:** the strongest proof the post-merge build will pass is an *already-green* CI job that performs the identical read. For isnad-graph frontend, `ci.yml`'s `frontend-lint-and-test` already does `npm ci` resolving the registry version with `NODE_AUTH_TOKEN=${{ secrets.GITHUB_TOKEN }}`; its SUCCESS on the same PR proves the token reads the cross-repo package. Quote that as the de-risk.
4. **Token-is-load-bearing check:** `curl -so /dev/null -w '%{http_code}' https://npm.pkg.github.com/@noorinalabs/<pkg>` → 401 tokenless / 200 with `-H "Authorization: Bearer $(gh auth token)"`. Confirms the build needs the token even for a public package (which is why a daemon-clean Docker build with no `.npmrc`-token 401s).

**Why:** ig#940 (direction A: file:-tgz → GitHub Packages registry) had a re-issued brief with an explicit STOP-gate on cross-repo auth. The public-visibility + existing-green-ci.yml-job evidence cleared it on the first try and predicted the post-merge `Publish to GHCR` workflow_dispatch SUCCESS (run 26731357105, both api+frontend green). Investigation-first turned a "might be blocked at org layer" into a proven-safe merge.

**How to apply:** Token goes into the Docker build as a **BuildKit secret** (`RUN --mount=type=secret,id=node_auth_token NODE_AUTH_TOKEN="$(cat /run/secrets/node_auth_token)" npm ci`), never a build-arg/ENV/layer; source it in the workflow via `build-push-action`'s `secrets: node_auth_token=${{ secrets.GITHUB_TOKEN }}`. Committed `.npmrc` uses canonical `${NODE_AUTH_TOKEN}` (NOT `NPM_TOKEN` — silent 401, the #924 lesson). When Docker daemon is unavailable locally (this WSL distro), the npm-resolution half is provable via a temp-dir `npm ci`; the full image build + the real publish gate are CI-only — `ghcr-publish.yml` triggers on push-to-main/tags, not PRs, so validate via `workflow_dispatch` on the wave branch (notify-deploy correctly skips). Related: [[feedback_npmrc_node_auth_token_convention]], [[feedback_setup_node_npmrc_env_var_name]], [[feedback_dep_resolution_invalidates]], [[feedback_runtime_gate_scoping]].
