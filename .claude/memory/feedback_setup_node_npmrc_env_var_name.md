---
name: feedback_setup_node_npmrc_env_var_name
description: "Project-level frontend/.npmrc must use ${NODE_AUTH_TOKEN}, not ${NPM_TOKEN}, when paired with actions/setup-node + GH Packages auth — divergence silently 401s"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 77e35de5-3b28-48a1-92f6-f413bc8debac
---

When wiring `actions/setup-node@v4` for GitHub Packages consumption in a CI workflow, the project-level `frontend/.npmrc` must reference the same env-var name that `setup-node` injects: **`${NODE_AUTH_TOKEN}`**, NOT `${NPM_TOKEN}` (or any other custom name).

**Why:** `setup-node` writes its own `.npmrc` to `$HOME/.npmrc` with `//npm.pkg.github.com/:_authToken=${NODE_AUTH_TOKEN}`. If the project-level `frontend/.npmrc` (which takes precedence over `$HOME/.npmrc` for that project tree) references `${NPM_TOKEN}` instead, npm substitutes it with the empty string at install time → server returns **401 Unauthorized** with no obvious "auth failed" message in the log. Looks like a permissions/scope problem; isn't.

**How to apply:**
- When reviewing or authoring any CI workflow that consumes a GH Packages dep (`@noorinalabs/*`), grep the project-level `.npmrc` for `_authToken=` and confirm the var name is `NODE_AUTH_TOKEN`.
- The workflow step itself should look like:
  ```yaml
  - uses: actions/setup-node@v4
    with:
      registry-url: 'https://npm.pkg.github.com'
      scope: '@noorinalabs'
  - run: npm ci
    env:
      NODE_AUTH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
  ```
- Use `${{ secrets.GITHUB_TOKEN }}` (auto-provided, scope-limited, auto-rotated) over custom NPM_TOKEN PATs for same-org package consumption. Declare `permissions: packages: read` at job level for least privilege.
- This is sibling to [[feedback_gh_pr_edit_silent_noop]] — another "silent 401-or-no-op with no log breadcrumb" failure mode. Same shape: read-back-verify (in this case, `gh pr view <N> --json statusCheckRollup` before claiming CI clean).

P3W11 isnad-graph PR #924 (2026-05-19): frontend-lint-and-test job 401'd on first auth-wiring push because `frontend/.npmrc` had `${NPM_TOKEN}` but `setup-node` was injecting `NODE_AUTH_TOKEN`. Jelani caught it via `gh pr view --json statusCheckRollup` after-push polling and corrected the var name; CI then went green.
