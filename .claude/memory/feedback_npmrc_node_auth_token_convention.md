---
name: feedback_npmrc_node_auth_token_convention
description: "When a project-level .npmrc declares _authToken for npm.pkg.github.com, the env-var name MUST be NODE_AUTH_TOKEN — actions/setup-node@v4's generated $HOME/.npmrc uses that name, and project-level takes precedence on host-scoped auth"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 77e35de5-3b28-48a1-92f6-f413bc8debac
---

When committing a project-level `.npmrc` that authenticates a GitHub Packages scope, use:

```
@noorinalabs:registry=https://npm.pkg.github.com
//npm.pkg.github.com/:_authToken=${NODE_AUTH_TOKEN}
```

NOT `${NPM_TOKEN}` or any other custom name.

**Why:** `actions/setup-node@v4` (when configured with `registry-url:` + `scope:`) writes a temporary `$HOME/.npmrc` that authenticates via the `NODE_AUTH_TOKEN` env var. npm's precedence for `:_authToken` is **project-level `.npmrc` wins over `$HOME/.npmrc`** for the same `host:` key. If your project-level `.npmrc` references a different env var name (`${NPM_TOKEN}`), and CI only sets `NODE_AUTH_TOKEN`, then `${NPM_TOKEN}` resolves to empty string, npm sends `Authorization: Bearer` with an empty token, and you get 401 — *with no diagnostic clue that the env var is the mismatch*.

P3W11 isnad-graph PR #924 (2026-05-19): pinning `@noorinalabs/design-system` to `^0.0.4-wave10.0` moved the resolution path from `file:.tgz` to `https://npm.pkg.github.com/...`. My initial `.npmrc` used `${NPM_TOKEN}` (matched my local export); CI wired `NODE_AUTH_TOKEN` (matched setup-node convention); the `frontend/.npmrc` precedence masked setup-node's `$HOME/.npmrc` for that host. Result: persistent 401 until commit `51e8cf5` aligned both files on `NODE_AUTH_TOKEN`.

**How to apply:**
- Default to `${NODE_AUTH_TOKEN}` in any committed `.npmrc` that talks to GitHub Packages — match setup-node's canonical name.
- Local-dev callers: `export NODE_AUTH_TOKEN=$(gh auth token)` (requires `read:packages` scope on the token; `gh auth refresh -s read:packages` if missing).
- CI: `env: NODE_AUTH_TOKEN: ${{ secrets.GITHUB_TOKEN }}` on every `npm install` step that resolves the scope. Pair with job-level `permissions: packages: read, contents: read`.
- If you're tempted to set `NPM_TOKEN` instead, ask whether the project-level `.npmrc` references it identically — env-var-name divergence here is a silent 401, not a loud failure.
- **Reviewer check:** when reviewing any CI workflow that consumes a GH Packages dep (`@noorinalabs/*`), grep the project-level `.npmrc` for `_authToken=` and confirm the var name is `NODE_AUTH_TOKEN` before approving. The failure is a silent 401 with no log breadcrumb — looks like a permissions/scope problem, isn't. (Jelani caught isnad-graph#924's via `gh pr view --json statusCheckRollup` after-push polling.) Canonical step: `actions/setup-node@v4` (`registry-url: https://npm.pkg.github.com`, `scope: '@noorinalabs'`) + `env: NODE_AUTH_TOKEN: ${{ secrets.GITHUB_TOKEN }}`.

Related: [[feedback_security_guard_inline_not_followup]] (don't leave literal tokens; `${VAR}` is npm runtime substitution), [[feedback_statuscheckrollup_ci_clean]] (catching the 401 requires CI-state check), [[feedback_gh_pr_edit_silent_noop]] (same silent-401/no-op-with-no-log-breadcrumb shape — read-back-verify).
