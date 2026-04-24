# Org-Secrets Audit & Migration Runbook — 2026-04-24

**Issue:** [noorinalabs-main#148](https://github.com/noorinalabs/noorinalabs-main/issues/148) — *W10 precursor: migrate overlapping repo-level GH secrets to org-level scope*
**Author:** Aino Virtanen (Standards & Quality Lead)
**Phase / Wave:** P2W10 — Section B
**Branch root:** `origin/deployments/phase-2/wave-10` @ `6168422`
**Status:** Docs-only proposal. Owner executes migrations from § 3 runbook post-merge.

---

## 0. Constraints & methodology

- **No secret values were read.** Only secret *names* are accessible via `gh api repos/<repo>/actions/secrets`. All "shared identical?" judgements below are **inferred from naming convention + workflow consumers**, never verified against ciphertext. Any cell marked `inferred-not-verified` MUST be re-confirmed by the owner before the per-repo copy is deleted.
- **Org-level secret enumeration was unavailable** — `gh api orgs/noorinalabs/actions/secrets` returns HTTP 403 (`admin:org` scope not granted to the audit account). Owner SHOULD run that command from an org-admin shell and append the result to § 1.b before executing § 3.
- All commands in § 3 are dry-run-safe to reason about but **mutating**. They were generated, never executed, by the audit pass.
- Per-environment secrets (`stg`/`prod` split) refer to GH Environments already provisioned by [noorinalabs-deploy#155](https://github.com/noorinalabs/noorinalabs-deploy/pull/155) (`promote.yml` precedent).

---

## 1. Audit table

### 1.a Per-repo secret inventory (raw)

Captured 2026-04-24 via `gh api repos/noorinalabs/<repo>/actions/secrets --paginate --jq '.secrets[].name'`.

| Repo | Secret count | Secrets |
|------|--------------|---------|
| noorinalabs-main | 1 | `GITLEAKS_LICENSE` |
| noorinalabs-deploy | 32 | `AUTH_GITHUB_CLIENT_ID`, `AUTH_GITHUB_CLIENT_SECRET`, `AUTH_GOOGLE_CLIENT_ID`, `AUTH_GOOGLE_CLIENT_SECRET`, `B2_APP_KEY`, `B2_BUCKET`, `B2_ENDPOINT`, `B2_KEY_ID`, `DEPLOY_SSH_PRIVATE_KEY`, `GITLEAKS_LICENSE`, `GRAFANA_ADMIN_PASSWORD`, `HCLOUD_TOKEN`, `JWT_PRIVATE_KEY`, `JWT_PUBLIC_KEY`, `KAFKA_CLUSTER_ID`, `KAFKA_UI_PASSWORD`, `KAFKA_UI_USER`, `NEO4J_PASSWORD`, `PIPELINE_B2_BUCKET`, `PIPELINE_B2_ENDPOINT`, `PIPELINE_B2_KEY`, `PIPELINE_B2_KEY_ID`, `PIPELINE_B2_REGION`, `POSTGRES_DB`, `POSTGRES_PASSWORD`, `POSTGRES_USER`, `REDIS_PASSWORD`, `TF_STATE_B2_APP_KEY`, `TF_STATE_B2_KEY_ID`, `USER_POSTGRES_DB`, `USER_POSTGRES_PASSWORD`, `USER_POSTGRES_USER`, `USER_REDIS_PASSWORD` |
| noorinalabs-user-service | 0 | *(none — this is the gap that creates US#84)* |
| noorinalabs-landing-page | 3 | `DEPLOY_SSH_PRIVATE_KEY`, `GH_PACKAGES_TOKEN`, `GITLEAKS_LICENSE` |
| noorinalabs-isnad-graph | 21 | `AUTH_GITHUB_CLIENT_ID`, `AUTH_GITHUB_CLIENT_SECRET`, `AUTH_GOOGLE_CLIENT_ID`, `AUTH_GOOGLE_CLIENT_SECRET`, `B2_APP_KEY`, `B2_BUCKET`, `B2_ENDPOINT`, `B2_KEY_ID`, `DEPLOY_REPO_PAT`, `DEPLOY_SSH_PRIVATE_KEY`, `DEPLOY_VPS_IP`, `GH_PACKAGES_TOKEN`, `GITLEAKS_LICENSE`, `GRAFANA_ADMIN_PASSWORD`, `HCLOUD_TOKEN`, `NEO4J_PASSWORD`, `NEO4J_USER`, `POSTGRES_DB`, `POSTGRES_PASSWORD`, `POSTGRES_USER`, `REDIS_PASSWORD` |
| noorinalabs-data-acquisition | 0 | *(none — pre-CI)* |
| noorinalabs-isnad-ingest-platform | 0 | *(none — planned P2W8, no CI yet)* |
| noorinalabs-design-system | 0 | *(none — uses `secrets.GITHUB_TOKEN` for npm publish)* |

**Totals:** 8 repos, 57 secret-slots populated, 35 unique secret names.

### 1.b Org-level secrets (TO FILL — owner action)

```bash
# Run from an account with admin:org scope.
gh api orgs/noorinalabs/actions/secrets --paginate \
  --jq '.secrets[] | {name, visibility, selected_repositories_url}'
```

> Append output here before § 3 execution. If org-secrets table is non-empty, cross-check against the migration recommendations in § 1.c — anything already org-scoped should be removed from the runbook.

### 1.c Master overlap table

For each unique secret name: where it currently lives, whether the value is likely identical across copies, rotation cadence guess, and migration recommendation. **All "likely shared identical" cells are `inferred-not-verified` unless explicitly noted.**

| Secret name | Repos that set it (count) | Likely shared identical? | Rotation cadence guess | Migration recommendation |
|---|---|---|---|---|
| `DEPLOY_REPO_PAT` | isnad-graph (1) | n/a (single setter today) | annual (PAT lifetime) | **Org-scope to {isnad-graph, user-service, landing-page}** — closes [US#84](https://github.com/noorinalabs/noorinalabs-user-service/issues/84). Single-source-of-truth for cross-repo `repository_dispatch` to noorinalabs-deploy. |
| `GITLEAKS_LICENSE` | main, deploy, landing-page, isnad-graph (4) | **Yes** — single org-issued license, no per-repo variation possible (license is keyed to org) | only on license renewal (~yearly) | **Org-scope to ALL repos** (visibility `all`) — vendor license, must match across org. Highest-confidence migration. |
| `DEPLOY_SSH_PRIVATE_KEY` | deploy, landing-page, isnad-graph (3) | likely (single VPS pool today; will diverge once stg/prod split lands per env-scope below) | quarterly | **Org-scope to {deploy, landing-page, isnad-graph}** as a transitional step; **then move to env-scope** (stg/prod) once deploy#155 envs are populated. Plan migration in two stages. |
| `AUTH_GITHUB_CLIENT_ID` | deploy, isnad-graph (2) | **Yes** (same OAuth GitHub App) | rare | **Org-scope to {deploy, isnad-graph, user-service}** — user-service will need it once it's the JWT issuer (see ontology user-service.yaml § ci.notify_deploy). |
| `AUTH_GITHUB_CLIENT_SECRET` | deploy, isnad-graph (2) | **Yes** (paired with above) | rare | Same as above. |
| `AUTH_GOOGLE_CLIENT_ID` | deploy, isnad-graph (2) | **Yes** (same OAuth Google App) | rare | Same scope as `AUTH_GITHUB_CLIENT_ID`. |
| `AUTH_GOOGLE_CLIENT_SECRET` | deploy, isnad-graph (2) | **Yes** (paired) | rare | Same as above. |
| `B2_APP_KEY` | deploy, isnad-graph (2) | likely (same Backblaze account) | quarterly | **Org-scope to {deploy, isnad-graph}**. May expand to {data-acquisition, ingest-platform} once those gain CI (P2W8). |
| `B2_BUCKET` | deploy, isnad-graph (2) | likely | static | Same as above. |
| `B2_ENDPOINT` | deploy, isnad-graph (2) | likely | static | Same as above. |
| `B2_KEY_ID` | deploy, isnad-graph (2) | likely | quarterly | Same as above. |
| `HCLOUD_TOKEN` | deploy, isnad-graph (2) | likely (single Hetzner project) | quarterly | **Org-scope to {deploy, isnad-graph}**. |
| `GH_PACKAGES_TOKEN` | landing-page, isnad-graph (2) | likely (same GH Packages registry) | annual (PAT) | **Org-scope to {landing-page, isnad-graph, design-system, user-service}** — `@noorinalabs` scoped npm packages (per ontology conventions § Shared tooling line 135). |
| `JWT_PRIVATE_KEY` | deploy (1) — needed by user-service (sign), isnad-graph (verify) | n/a (single setter; routed through deploy's env-injection) | semi-annual | **Org-scope to {deploy, user-service, isnad-graph}** — eliminates the deploy-mediated injection. user-service signs, isnad-graph verifies, deploy still gets it for env-file generation. |
| `JWT_PUBLIC_KEY` | deploy (1) | same | semi-annual | Same scope as `JWT_PRIVATE_KEY`. |
| `POSTGRES_DB` | deploy, isnad-graph (2) | likely (isnad-graph DB) | static | **Env-scope (stg/prod)** in noorinalabs-deploy via GH Environments per [deploy#155](https://github.com/noorinalabs/noorinalabs-deploy/pull/155). Then delete repo-level copy in isnad-graph. |
| `POSTGRES_PASSWORD` | deploy, isnad-graph (2) | likely | quarterly | Env-scope per deploy#155. |
| `POSTGRES_USER` | deploy, isnad-graph (2) | likely | static | Env-scope per deploy#155. |
| `USER_POSTGRES_DB` | deploy (1) | n/a | static | Env-scope (user-service DB). |
| `USER_POSTGRES_PASSWORD` | deploy (1) | n/a | quarterly | Env-scope. |
| `USER_POSTGRES_USER` | deploy (1) | n/a | static | Env-scope. |
| `REDIS_PASSWORD` | deploy, isnad-graph (2) | likely | quarterly | Env-scope. |
| `USER_REDIS_PASSWORD` | deploy (1) | n/a | quarterly | Env-scope. |
| `NEO4J_PASSWORD` | deploy, isnad-graph (2) | likely | quarterly | Env-scope. |
| `NEO4J_USER` | isnad-graph (1) | n/a | static | Env-scope (move to deploy under env-scope, delete from isnad-graph). |
| `GRAFANA_ADMIN_PASSWORD` | deploy, isnad-graph (2) | likely | quarterly | Env-scope. |
| `KAFKA_CLUSTER_ID` | deploy (1) | n/a | static | Env-scope. |
| `KAFKA_UI_USER` | deploy (1) | n/a | static | Env-scope. |
| `KAFKA_UI_PASSWORD` | deploy (1) | n/a | quarterly | Env-scope. |
| `DEPLOY_VPS_IP` | isnad-graph (1) | n/a | per-rebuild | **Env-scope (stg/prod)** — different VPS per env per [P2W10 per-env Hetzner](https://github.com/noorinalabs/noorinalabs-main/issues/141). Move to deploy under env-scope; delete from isnad-graph. |
| `TF_STATE_B2_APP_KEY` | deploy (1) | n/a | quarterly | Repo-scope (Terraform state credentials only consumed by deploy's `terraform.yml`). |
| `TF_STATE_B2_KEY_ID` | deploy (1) | n/a | quarterly | Repo-scope. |
| `PIPELINE_B2_BUCKET` | deploy (1) | n/a | static | Repo-scope today; **expand to org-scope {deploy, data-acquisition, ingest-platform}** once those repos gain CI (P2W8). |
| `PIPELINE_B2_ENDPOINT` | deploy (1) | n/a | static | Same. |
| `PIPELINE_B2_KEY` | deploy (1) | n/a | quarterly | Same. |
| `PIPELINE_B2_KEY_ID` | deploy (1) | n/a | quarterly | Same. |
| `PIPELINE_B2_REGION` | deploy (1) | n/a | static | Same. |

---

## 2. Categorization summary

| Tier | Definition | Count | Secrets |
|------|-----------|-------|---------|
| **A. Org-scope, all repos** | every repo needs it | **1** | `GITLEAKS_LICENSE` |
| **B. Org-scope, selected repos** | 2+ repos clearly need same value | **13** | `DEPLOY_REPO_PAT`, `DEPLOY_SSH_PRIVATE_KEY` (transitional), `AUTH_GITHUB_CLIENT_ID`, `AUTH_GITHUB_CLIENT_SECRET`, `AUTH_GOOGLE_CLIENT_ID`, `AUTH_GOOGLE_CLIENT_SECRET`, `B2_APP_KEY`, `B2_BUCKET`, `B2_ENDPOINT`, `B2_KEY_ID`, `HCLOUD_TOKEN`, `GH_PACKAGES_TOKEN`, `JWT_PRIVATE_KEY`, `JWT_PUBLIC_KEY` (14 incl. transitional SSH key) |
| **C. Environment-scope** | differs per env → use existing GH Environments `staging`/`production` (deploy#155) | **15** | `POSTGRES_DB`, `POSTGRES_PASSWORD`, `POSTGRES_USER`, `USER_POSTGRES_DB`, `USER_POSTGRES_PASSWORD`, `USER_POSTGRES_USER`, `REDIS_PASSWORD`, `USER_REDIS_PASSWORD`, `NEO4J_PASSWORD`, `NEO4J_USER`, `GRAFANA_ADMIN_PASSWORD`, `KAFKA_CLUSTER_ID`, `KAFKA_UI_USER`, `KAFKA_UI_PASSWORD`, `DEPLOY_VPS_IP`, `DEPLOY_SSH_PRIVATE_KEY` (post-transitional, see Tier B) |
| **D. Repo-scope only** | single consumer, no overlap, no env-split | **2** | `TF_STATE_B2_APP_KEY`, `TF_STATE_B2_KEY_ID` (deploy-only) |
| **E. Pending repo onboarding** | will become org/env scope when consumer repos ship CI | **5** | `PIPELINE_B2_BUCKET`, `PIPELINE_B2_ENDPOINT`, `PIPELINE_B2_KEY`, `PIPELINE_B2_KEY_ID`, `PIPELINE_B2_REGION` (revisit P2W8 when data-acquisition + ingest-platform gain CI) |

**Total recommended migrations (Tiers A + B + C):** 29 secret slots → 14 unique org-level secrets (A+B) + 15 env-scoped relocations (C).

---

## 3. Migration runbook (owner-runnable, in execution order)

> **Order:** `DEPLOY_REPO_PAT` is **first** because it atomically closes [US#84](https://github.com/noorinalabs/noorinalabs-user-service/issues/84). Subsequent migrations are ordered by drift-risk severity (high → low), then cadence (rotated more often → first).
>
> **Pre-flight:** run § 1.b. If any of the secrets below already exist at org-scope with the correct repo selection, **skip that step** and proceed to the per-repo `delete` calls.
>
> **Post-flight per migration:** trigger one workflow in each affected repo (push a no-op commit or `gh workflow run`) and verify the secret resolves. Note the verification result inline in the runbook before deleting the next batch.

### 3.1. `DEPLOY_REPO_PAT` — closes US#84 (HIGHEST priority)

```bash
# 1. Set at org-level, scoped to the 3 repos that need cross-repo dispatch
gh secret set DEPLOY_REPO_PAT --org noorinalabs --visibility selected \
  --repos noorinalabs-isnad-graph,noorinalabs-user-service,noorinalabs-landing-page

# 2. Verify org-level placement
gh api orgs/noorinalabs/actions/secrets/DEPLOY_REPO_PAT \
  --jq '{name, visibility, selected_repositories_url}'

# 3. Verify each repo can resolve it
gh api orgs/noorinalabs/actions/secrets/DEPLOY_REPO_PAT/repositories \
  --jq '.repositories[] | .name'
# Expected: noorinalabs-isnad-graph, noorinalabs-user-service, noorinalabs-landing-page

# 4. Trigger user-service ghcr-publish to confirm notify-deploy job no longer 401s
gh workflow run ghcr-publish.yml --repo noorinalabs/noorinalabs-user-service \
  --ref deployments/phase-2/wave-10
gh run watch --repo noorinalabs/noorinalabs-user-service

# 5. Delete the per-repo copy in isnad-graph (now redundant)
gh secret delete DEPLOY_REPO_PAT --repo noorinalabs/noorinalabs-isnad-graph

# 6. Close US#84
gh issue close 84 --repo noorinalabs/noorinalabs-user-service \
  --comment "Closed by org-scoped DEPLOY_REPO_PAT migration per noorinalabs-main#148. Verified notify-deploy job succeeds."
```

### 3.2. `GITLEAKS_LICENSE` — vendor license, all-org

```bash
# Org-scope to ALL repos (visibility=all is correct here — license is org-wide)
gh secret set GITLEAKS_LICENSE --org noorinalabs --visibility all

# Delete per-repo copies
for repo in noorinalabs-main noorinalabs-deploy noorinalabs-landing-page noorinalabs-isnad-graph; do
  gh secret delete GITLEAKS_LICENSE --repo "noorinalabs/$repo"
done

# Verify
gh api orgs/noorinalabs/actions/secrets/GITLEAKS_LICENSE --jq '{name, visibility}'
```

### 3.3. OAuth credentials — `AUTH_{GITHUB,GOOGLE}_CLIENT_{ID,SECRET}` (4 secrets)

```bash
for SECRET in AUTH_GITHUB_CLIENT_ID AUTH_GITHUB_CLIENT_SECRET \
              AUTH_GOOGLE_CLIENT_ID AUTH_GOOGLE_CLIENT_SECRET; do
  gh secret set "$SECRET" --org noorinalabs --visibility selected \
    --repos noorinalabs-deploy,noorinalabs-isnad-graph,noorinalabs-user-service
done

# Trigger one workflow per consumer repo, verify resolution, then:
for SECRET in AUTH_GITHUB_CLIENT_ID AUTH_GITHUB_CLIENT_SECRET \
              AUTH_GOOGLE_CLIENT_ID AUTH_GOOGLE_CLIENT_SECRET; do
  gh secret delete "$SECRET" --repo noorinalabs/noorinalabs-deploy
  gh secret delete "$SECRET" --repo noorinalabs/noorinalabs-isnad-graph
done
```

### 3.4. JWT keypair — `JWT_PRIVATE_KEY`, `JWT_PUBLIC_KEY`

```bash
for SECRET in JWT_PRIVATE_KEY JWT_PUBLIC_KEY; do
  gh secret set "$SECRET" --org noorinalabs --visibility selected \
    --repos noorinalabs-deploy,noorinalabs-user-service,noorinalabs-isnad-graph
done

# Verify before deleting deploy's copy — deploy injects this into env files
gh api orgs/noorinalabs/actions/secrets/JWT_PRIVATE_KEY/repositories --jq '.repositories[].name'

for SECRET in JWT_PRIVATE_KEY JWT_PUBLIC_KEY; do
  gh secret delete "$SECRET" --repo noorinalabs/noorinalabs-deploy
done
```

### 3.5. Backblaze cluster creds — `B2_*` (4 secrets)

```bash
for SECRET in B2_APP_KEY B2_BUCKET B2_ENDPOINT B2_KEY_ID; do
  gh secret set "$SECRET" --org noorinalabs --visibility selected \
    --repos noorinalabs-deploy,noorinalabs-isnad-graph
done

for SECRET in B2_APP_KEY B2_BUCKET B2_ENDPOINT B2_KEY_ID; do
  gh secret delete "$SECRET" --repo noorinalabs/noorinalabs-deploy
  gh secret delete "$SECRET" --repo noorinalabs/noorinalabs-isnad-graph
done
```

### 3.6. `HCLOUD_TOKEN` — Hetzner Cloud API token

```bash
gh secret set HCLOUD_TOKEN --org noorinalabs --visibility selected \
  --repos noorinalabs-deploy,noorinalabs-isnad-graph

gh secret delete HCLOUD_TOKEN --repo noorinalabs/noorinalabs-deploy
gh secret delete HCLOUD_TOKEN --repo noorinalabs/noorinalabs-isnad-graph
```

### 3.7. `GH_PACKAGES_TOKEN` — `@noorinalabs` npm registry

```bash
gh secret set GH_PACKAGES_TOKEN --org noorinalabs --visibility selected \
  --repos noorinalabs-landing-page,noorinalabs-isnad-graph,noorinalabs-design-system,noorinalabs-user-service

gh secret delete GH_PACKAGES_TOKEN --repo noorinalabs/noorinalabs-landing-page
gh secret delete GH_PACKAGES_TOKEN --repo noorinalabs/noorinalabs-isnad-graph
```

### 3.8. `DEPLOY_SSH_PRIVATE_KEY` — TWO-STAGE migration

**Stage 1 — org-scope (transitional, restores parity with stg/prod split):**

```bash
gh secret set DEPLOY_SSH_PRIVATE_KEY --org noorinalabs --visibility selected \
  --repos noorinalabs-deploy,noorinalabs-landing-page,noorinalabs-isnad-graph

gh secret delete DEPLOY_SSH_PRIVATE_KEY --repo noorinalabs/noorinalabs-deploy
gh secret delete DEPLOY_SSH_PRIVATE_KEY --repo noorinalabs/noorinalabs-landing-page
gh secret delete DEPLOY_SSH_PRIVATE_KEY --repo noorinalabs/noorinalabs-isnad-graph
```

**Stage 2 — env-scope (after per-env Hetzner VPS exists per main#141):**

```bash
# Stage as separate keys per env, replace org-scoped above
gh secret set DEPLOY_SSH_PRIVATE_KEY \
  --repo noorinalabs/noorinalabs-deploy --env staging
gh secret set DEPLOY_SSH_PRIVATE_KEY \
  --repo noorinalabs/noorinalabs-deploy --env production
# Then delete the org-scoped transitional secret
gh secret delete DEPLOY_SSH_PRIVATE_KEY --org noorinalabs
```

### 3.9. Env-scope migrations (Tier C, executed via deploy#155 envs)

For each Tier-C secret, set in **both** `staging` and `production` GH Environments on `noorinalabs-deploy`:

```bash
# Pattern (repeat per secret with appropriate value):
gh secret set <SECRET_NAME> --repo noorinalabs/noorinalabs-deploy --env staging
gh secret set <SECRET_NAME> --repo noorinalabs/noorinalabs-deploy --env production

# Then delete the repo-level copy (and the isnad-graph copy if it exists):
gh secret delete <SECRET_NAME> --repo noorinalabs/noorinalabs-deploy
gh secret delete <SECRET_NAME> --repo noorinalabs/noorinalabs-isnad-graph 2>/dev/null || true
```

Apply to: `POSTGRES_DB`, `POSTGRES_PASSWORD`, `POSTGRES_USER`, `USER_POSTGRES_DB`, `USER_POSTGRES_PASSWORD`, `USER_POSTGRES_USER`, `REDIS_PASSWORD`, `USER_REDIS_PASSWORD`, `NEO4J_PASSWORD`, `NEO4J_USER`, `GRAFANA_ADMIN_PASSWORD`, `KAFKA_CLUSTER_ID`, `KAFKA_UI_USER`, `KAFKA_UI_PASSWORD`, `DEPLOY_VPS_IP`.

> **Note:** Tier C steps require the env values to actually differ between `staging` and `production`. If they don't yet (single shared VPS), seed both envs with the current value and rotate `production` separately during the per-env Hetzner cutover (main#141).

### 3.10. Tier-D leave-as-is

`TF_STATE_B2_APP_KEY` and `TF_STATE_B2_KEY_ID` stay repo-scoped on `noorinalabs-deploy` — only consumed by `terraform.yml`.

### 3.11. Tier-E deferral

`PIPELINE_B2_*` (5 secrets) stay repo-scoped on `noorinalabs-deploy` until P2W8 brings `noorinalabs-data-acquisition` and `noorinalabs-isnad-ingest-platform` onto CI. Re-audit at that wave.

---

## 4. Policy proposal — `.claude/team/charter/secrets.md` (snippet for next charter touch)

> The charter file `secrets.md` does not exist today. The snippet below is **promotion-ready content** for owner to drop into a new file or merge into `pull-requests.md` § Infrastructure at next charter touch. This is a proposal — not a charter edit in this PR.

```markdown
# Secrets policy

## Default scope

When introducing a new secret, default to **per-repo scope**.

## Promote to org-scope when

- 2+ repos consume the same logical value (e.g., shared OAuth app, shared
  vendor license, shared cluster credential).
- The secret is rotated as a single unit across all consumers (rotation
  cadence is identical).
- The value is identical across consumers — not "similar" or "derived from."

Use `--visibility selected --repos a,b,c` unless every repo in the org needs
it (rare — `GITLEAKS_LICENSE` is the only current example warranting
`--visibility all`).

## Promote to env-scope when

- The value differs per deployment environment (`staging` vs `production`).
- Use the GH Environments precedent from
  [noorinalabs-deploy#155](https://github.com/noorinalabs/noorinalabs-deploy/pull/155):
  `gh secret set <NAME> --repo <repo> --env staging|production`.
- Env-scope takes precedence over org-scope when both apply (env-scoped
  values shadow org-scoped values at workflow runtime).

## Rotation

- Per-repo: rotate in each repo independently.
- Org-scope: one `gh secret set --org noorinalabs --visibility selected
  --repos <list>` rotates all consumers atomically.
- Env-scope: rotate `staging` and `production` independently; verify staging
  workflow before rotating production.

## Audit cadence

- Re-run the secrets audit (`docs/secrets-audit-YYYY-MM-DD.md` template) at
  each wave that adds a new repo to the org or a new external integration
  (OAuth provider, cloud account, message broker, etc.).
- Track audit completion in the wave wrap-up checklist.

## Hook-enforceable invariants (future work)

- A pre-commit hook in `noorinalabs-main` could parse all
  `.github/workflows/*.yml` across child repos and flag references to
  `secrets.X` where `X` is not declared at any reachable scope (per-repo,
  org, or env). Tracked as future automation under
  [feedback enforcement hierarchy](memory:feedback_enforcement_hierarchy.md).
```

---

## 5. Cross-references

- **[noorinalabs-user-service#84](https://github.com/noorinalabs/noorinalabs-user-service/issues/84)** — `DEPLOY_REPO_PAT` first-migration target. § 3.1 closes this issue.
- **[noorinalabs-deploy#155](https://github.com/noorinalabs/noorinalabs-deploy/pull/155)** — GH Environments `staging`/`production` precedent. Tier-C migrations (§ 3.9) consume this infrastructure.
- **[noorinalabs-main#141](https://github.com/noorinalabs/noorinalabs-main/issues/141)** — P2W10 meta. Per-env Hetzner VPS work informs § 3.8 stage 2 + § 3.9 `DEPLOY_VPS_IP` env-scope.
- **[noorinalabs-main#148](https://github.com/noorinalabs/noorinalabs-main/issues/148)** — this issue.
- **Ontology `repos/user-service.yaml` line 104** — `DEPLOY_REPO_PAT` not-yet-provisioned annotation. After § 3.1 executes, the ontology resolver should re-emit this entry to drop the "(NOT yet provisioned)" caveat.
- **Ontology `conventions.md` line 148** — `gitleaks` is the only current org-wide tooling secret rationale. § 3.2 codifies this.

---

## 6. Open questions for owner

1. **Org-secrets enumeration** — § 1.b needs an `admin:org`-scope run before the runbook is executed. Without it, § 3 may attempt to set secrets that already exist at org-level under different scoping.
2. **JWT key custody** — currently `deploy` injects JWT keys into env files at provision time. Migrating to org-scope means user-service and isnad-graph can read them directly. Confirm the env-file injection path can be removed (or whether deploy still needs the secret for legacy provisioning).
3. **`DEPLOY_SSH_PRIVATE_KEY` two-stage** — § 3.8 assumes the per-env Hetzner cutover (main#141) lands within the same wave. If it slips to W11+, leave the org-scoped transitional in place and revisit.
4. **Inferred-not-verified cells** — § 1.c "Likely shared identical?" column. Owner should sample-verify (e.g., via the values UI in the GH Settings page) before deleting any per-repo copy. Recommend verifying at least `JWT_PRIVATE_KEY`, `AUTH_*_CLIENT_SECRET`, and `B2_APP_KEY` since those are the highest-risk if they actually differ.
