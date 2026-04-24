# Org-Secrets Audit & Migration Runbook — 2026-04-24

**Issue:** [noorinalabs-main#148](https://github.com/noorinalabs/noorinalabs-main/issues/148) — *W10 precursor: migrate overlapping repo-level GH secrets to org-level scope*
**Author:** Aino Virtanen (Standards & Quality Lead)
**Phase / Wave:** P2W10 — Section B
**Branch root:** `origin/deployments/phase-2/wave-10` @ `6168422`
**Status:** Docs-only proposal. Owner executes migrations from § 3 runbook post-merge.

---

## 0. Constraints & methodology

- **No secret values were read.** Only secret *names* are accessible via `gh api repos/<repo>/actions/secrets`. All "shared identical?" judgements below are **inferred from naming convention + workflow consumers**, never verified against ciphertext. Any cell marked `inferred-not-verified` MUST be re-confirmed by the owner before the per-repo copy is deleted.
  - *Runbook-execution implication:* because GitHub never returns ciphertext, migrating a per-repo secret to org/env scope MUST source its value from the **canonical upstream** (Hetzner/Backblaze/OAuth consoles, VPS env files, keypair custody), NOT from a rehydration of the old per-repo ciphertext. This is codified as the mandatory § 3.0 value-preservation protocol — do not start § 3.1 without completing § 3.0.
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
| noorinalabs-isnad-ingest-platform | 0 | *(none — no CI yet; wave unscheduled)* |
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
| `B2_APP_KEY` | deploy, isnad-graph (2) | likely (same Backblaze account) | quarterly | **Org-scope to {deploy, isnad-graph}**. May expand to {data-acquisition, ingest-platform} once those gain CI (currently unscheduled). |
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
| `PIPELINE_B2_BUCKET` | deploy (1) | n/a | static | Repo-scope today; **expand to org-scope {deploy, data-acquisition, ingest-platform}** once those repos gain CI (currently unscheduled). |
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
| **E. Pending repo onboarding** | will become org/env scope when consumer repos ship CI | **5** | `PIPELINE_B2_BUCKET`, `PIPELINE_B2_ENDPOINT`, `PIPELINE_B2_KEY`, `PIPELINE_B2_KEY_ID`, `PIPELINE_B2_REGION` (revisit when `data-acquisition` + `ingest-platform` gain CI — currently unscheduled; track under main#141 successor meta) |

**Total recommended migrations (Tiers A + B + C):** 29 secret slots → 14 unique org-level secrets (A+B) + 15 env-scoped relocations (C).

---

## 3. Migration runbook (owner-runnable, in execution order)

> **Order:** `DEPLOY_REPO_PAT` is **first** because it atomically closes [US#84](https://github.com/noorinalabs/noorinalabs-user-service/issues/84). Subsequent migrations are ordered by drift-risk severity (high → low), then cadence (rotated more often → first).
>
> **Pre-flight:** run § 1.b. If any of the secrets below already exist at org-scope with the correct repo selection, **skip that step** and proceed to the per-repo `delete` calls.
>
> **Post-flight per migration:** trigger one workflow in each affected repo (push a no-op commit or `gh workflow run`) and verify the secret resolves. Note the verification result inline in the runbook before deleting the next batch.

### 3.0. Value-preservation protocol (MANDATORY — execute before any `gh secret set`)

**Why this exists.** The GitHub Actions Secrets API never returns ciphertext: once a per-repo secret is deleted, its value is unrecoverable. If the org-scoped replacement drifts from the original by a single character, post-delete workflows fail at runtime with no recovery path short of regenerating upstream credentials (JWT keypair reissue, OAuth app re-consent, Hetzner token rotation, etc.). Every step in § 3 that runs `gh secret set` MUST source its value from this staging tree, NOT from "what I think was in the old repo-scope secret."

#### 3.0.a. Identify canonical upstream source per secret class

Each secret's authoritative source lives OUTSIDE GitHub. Before any `set-org` / `set --env` call, fetch the current value from the upstream source into the staging tree (§ 3.0.b).

| Secret class | Canonical upstream source |
|---|---|
| `DEPLOY_REPO_PAT` | GitHub → Developer Settings → Personal access tokens (classic or fine-grained); if expired/unknown, regenerate and rotate downstream — do NOT attempt to recover. |
| `GITLEAKS_LICENSE` | Gitleaks vendor email / license portal for `noorinalabs` org seat. |
| `DEPLOY_SSH_PRIVATE_KEY` | VPS operator's local filesystem — `TODO(santiago):` confirm canonical path (owner's workstation at `~/.ssh/noorinalabs_deploy` vs. a keypair stored elsewhere). The public half lives on the Hetzner VPS under `~/.ssh/authorized_keys` for the `deploy` user. |
| `AUTH_GITHUB_CLIENT_ID` / `AUTH_GITHUB_CLIENT_SECRET` | GitHub → Organization settings → Developer settings → OAuth Apps → (the noorinalabs OAuth app). Client secret can be regenerated from that console; regenerating invalidates the current secret — rotate downstream immediately. |
| `AUTH_GOOGLE_CLIENT_ID` / `AUTH_GOOGLE_CLIENT_SECRET` | Google Cloud Console → APIs & Services → Credentials → (OAuth 2.0 Client IDs for noorinalabs). Same regenerate-and-rotate semantics as GitHub OAuth. |
| `B2_APP_KEY` / `B2_KEY_ID` | Backblaze B2 console → App Keys. Value is shown once at creation — if lost, create a new key and retire the old one. |
| `B2_BUCKET` / `B2_ENDPOINT` | Backblaze B2 console → Buckets (bucket name + S3-compatible endpoint URL; not secret per se, but staged alongside for runbook completeness). |
| `HCLOUD_TOKEN` | Hetzner Cloud Console → (noorinalabs project) → Security → API tokens. Value shown once at creation — regenerate if lost. |
| `GH_PACKAGES_TOKEN` | GitHub → Developer Settings → Personal access tokens with `read:packages` / `write:packages` for the `@noorinalabs` npm scope. Regenerate if unknown. |
| `JWT_PRIVATE_KEY` / `JWT_PUBLIC_KEY` | Keypair on owner's workstation / VPS — `TODO(santiago):` confirm canonical custodial path. If not recoverable, regenerate via `openssl` and re-issue all outstanding JWTs (breaking change — plan a user session-reset window). |
| `POSTGRES_*`, `USER_POSTGRES_*`, `REDIS_*`, `USER_REDIS_*`, `NEO4J_*` (passwords/users/dbs) | Current VPS filesystem — `TODO(santiago):` confirm canonical path for the rendered env files (e.g., `/opt/noorinalabs/stg/.env` on the staging VPS). These can be `ssh`-copied to the staging tree with a `cat` over the pipe — do NOT scp the whole env file into the staging tree. |
| `GRAFANA_ADMIN_PASSWORD` | Same as Postgres — rendered env file on the VPS. |
| `KAFKA_CLUSTER_ID` | Derived at cluster bootstrap — documented in `noorinalabs-deploy` Terraform state or VPS env file. `TODO(santiago):` confirm. |
| `KAFKA_UI_USER` / `KAFKA_UI_PASSWORD` | Rendered env file on VPS (Kafka-UI container config). |
| `DEPLOY_VPS_IP` | Hetzner Cloud Console — current VPS public IPv4. Not secret (public), but staged for consistency. |
| `TF_STATE_B2_APP_KEY` / `TF_STATE_B2_KEY_ID` | Backblaze B2 console → App Keys (dedicated key for Terraform state bucket). |
| `PIPELINE_B2_*` | Tier-E, deferred — see § 3.11. No staging needed this migration cycle. |

If any row above resolves to "unknown / unrecoverable," the correct move is **regenerate upstream first, complete the § 3 migration with the new value, and rotate downstream consumers in the same window** — never guess-and-paste into `gh secret set --org`.

#### 3.0.b. Stage values into a local-only tree

```bash
# One-time setup. All paths are on the owner's workstation, NOT committed anywhere.
STAGING="$HOME/.noorinalabs-secrets-migration-2026-04-24"
mkdir -p -m 700 "$STAGING"/{org,env/staging,env/production}

# Confirm the parent dir is gitignored (should resolve to a path OUTSIDE any repo).
case "$STAGING" in
  "$HOME/.noorinalabs-secrets-migration-"*) : ok ;;
  *) echo "ABORT: staging tree must live outside any repo worktree"; exit 1 ;;
esac

# File-per-secret layout:
#   $STAGING/org/DEPLOY_REPO_PAT          — org-scoped value (Tier A/B)
#   $STAGING/env/staging/POSTGRES_PASSWORD — env-scoped value (Tier C, staging)
#   $STAGING/env/production/POSTGRES_PASSWORD — env-scoped value (Tier C, production)
#
# For each secret named in § 3.0.a:
#   1. Fetch the value from its canonical upstream source (console, keypair file, VPS env file).
#   2. Write it to the appropriate $STAGING/... path with `chmod 600`.
#   3. Do NOT print the value to terminal history — use `pbpaste > file` (macOS) or
#      `wl-paste > file` (Linux/Wayland), or a console "copy to clipboard" → paste-into-editor flow.

# Example for one secret:
#   cat > "$STAGING/org/DEPLOY_REPO_PAT" <<'EOF'
#   <paste-pat-value-here>
#   EOF
#   chmod 600 "$STAGING/org/DEPLOY_REPO_PAT"
```

#### 3.0.c. Cleanup (MANDATORY — after § 3 runbook completes)

```bash
# Secure delete all staged secret files. Run ONLY after all § 3.x verifications pass.
find "$STAGING" -type f -exec shred -u -n 3 {} \;   # Linux
# find "$STAGING" -type f -exec rm -P {} \;        # macOS equivalent
rmdir "$STAGING"/org "$STAGING"/env/staging "$STAGING"/env/production "$STAGING"/env "$STAGING"
```

**Every `gh secret set` call in § 3.1–§ 3.9 below MUST source its value from this staging tree via `--body "$(cat ...)"` or stdin-pipe (`cat ... | gh secret set ... -`).** The literal `<value>` placeholders below are NOT to be typed into an interactive prompt.

### 3.1. `DEPLOY_REPO_PAT` — closes US#84 (HIGHEST priority)

> Value source: `$STAGING/org/DEPLOY_REPO_PAT` (staged per § 3.0.b from GitHub → Developer Settings → PATs).

```bash
# 1. Set at org-level, scoped to the 3 repos that need cross-repo dispatch
gh secret set DEPLOY_REPO_PAT --org noorinalabs --visibility selected \
  --repos noorinalabs-isnad-graph,noorinalabs-user-service,noorinalabs-landing-page \
  --body "$(cat "$STAGING/org/DEPLOY_REPO_PAT")"

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

> Value source: `$STAGING/org/GITLEAKS_LICENSE` (staged per § 3.0.b from the Gitleaks vendor license portal).

```bash
# Org-scope to ALL repos (visibility=all is correct here — license is org-wide)
gh secret set GITLEAKS_LICENSE --org noorinalabs --visibility all \
  --body "$(cat "$STAGING/org/GITLEAKS_LICENSE")"

# Delete per-repo copies
for repo in noorinalabs-main noorinalabs-deploy noorinalabs-landing-page noorinalabs-isnad-graph; do
  gh secret delete GITLEAKS_LICENSE --repo "noorinalabs/$repo"
done

# Verify
gh api orgs/noorinalabs/actions/secrets/GITLEAKS_LICENSE --jq '{name, visibility}'
```

### 3.3. OAuth credentials — `AUTH_{GITHUB,GOOGLE}_CLIENT_{ID,SECRET}` (4 secrets)

> Value sources: `$STAGING/org/AUTH_*` (staged per § 3.0.b from GitHub OAuth App console + Google Cloud Console → Credentials).

```bash
for SECRET in AUTH_GITHUB_CLIENT_ID AUTH_GITHUB_CLIENT_SECRET \
              AUTH_GOOGLE_CLIENT_ID AUTH_GOOGLE_CLIENT_SECRET; do
  gh secret set "$SECRET" --org noorinalabs --visibility selected \
    --repos noorinalabs-deploy,noorinalabs-isnad-graph,noorinalabs-user-service \
    --body "$(cat "$STAGING/org/$SECRET")"
done

# Trigger one workflow per consumer repo (`gh workflow run` + `gh run watch`),
# verify resolution, then:
for SECRET in AUTH_GITHUB_CLIENT_ID AUTH_GITHUB_CLIENT_SECRET \
              AUTH_GOOGLE_CLIENT_ID AUTH_GOOGLE_CLIENT_SECRET; do
  gh secret delete "$SECRET" --repo noorinalabs/noorinalabs-deploy
  gh secret delete "$SECRET" --repo noorinalabs/noorinalabs-isnad-graph
done
```

### 3.4. JWT keypair — `JWT_PRIVATE_KEY`, `JWT_PUBLIC_KEY`

> Value sources: `$STAGING/org/JWT_PRIVATE_KEY` and `$STAGING/org/JWT_PUBLIC_KEY` (staged per § 3.0.b from canonical keypair custody — see § 3.0.a `TODO(santiago):`). If either value is unrecoverable, regenerate the keypair upstream and plan the JWT re-issue window BEFORE running this section.

```bash
for SECRET in JWT_PRIVATE_KEY JWT_PUBLIC_KEY; do
  gh secret set "$SECRET" --org noorinalabs --visibility selected \
    --repos noorinalabs-deploy,noorinalabs-user-service,noorinalabs-isnad-graph \
    --body "$(cat "$STAGING/org/$SECRET")"
done

# Verify before deleting deploy's copy — deploy injects this into env files
gh api orgs/noorinalabs/actions/secrets/JWT_PRIVATE_KEY/repositories --jq '.repositories[].name'

for SECRET in JWT_PRIVATE_KEY JWT_PUBLIC_KEY; do
  gh secret delete "$SECRET" --repo noorinalabs/noorinalabs-deploy
done
```

### 3.5. Backblaze cluster creds — `B2_*` (4 secrets)

> Value sources: `$STAGING/org/B2_*` (staged per § 3.0.b from Backblaze B2 console → App Keys + Buckets). If `B2_APP_KEY` is unrecoverable, create a new app key and retire the old one.

```bash
for SECRET in B2_APP_KEY B2_BUCKET B2_ENDPOINT B2_KEY_ID; do
  gh secret set "$SECRET" --org noorinalabs --visibility selected \
    --repos noorinalabs-deploy,noorinalabs-isnad-graph \
    --body "$(cat "$STAGING/org/$SECRET")"
done

for SECRET in B2_APP_KEY B2_BUCKET B2_ENDPOINT B2_KEY_ID; do
  gh secret delete "$SECRET" --repo noorinalabs/noorinalabs-deploy
  gh secret delete "$SECRET" --repo noorinalabs/noorinalabs-isnad-graph
done
```

### 3.6. `HCLOUD_TOKEN` — Hetzner Cloud API token

> Value source: `$STAGING/org/HCLOUD_TOKEN` (staged per § 3.0.b from Hetzner Cloud Console → Security → API tokens). If unrecoverable, regenerate in-console and expect existing tokens to be revoked.

```bash
gh secret set HCLOUD_TOKEN --org noorinalabs --visibility selected \
  --repos noorinalabs-deploy,noorinalabs-isnad-graph \
  --body "$(cat "$STAGING/org/HCLOUD_TOKEN")"

gh secret delete HCLOUD_TOKEN --repo noorinalabs/noorinalabs-deploy
gh secret delete HCLOUD_TOKEN --repo noorinalabs/noorinalabs-isnad-graph
```

### 3.7. `GH_PACKAGES_TOKEN` — `@noorinalabs` npm registry

> Value source: `$STAGING/org/GH_PACKAGES_TOKEN` (staged per § 3.0.b from GitHub → Developer Settings → PATs with `read:packages` / `write:packages` scope).

```bash
gh secret set GH_PACKAGES_TOKEN --org noorinalabs --visibility selected \
  --repos noorinalabs-landing-page,noorinalabs-isnad-graph,noorinalabs-design-system,noorinalabs-user-service \
  --body "$(cat "$STAGING/org/GH_PACKAGES_TOKEN")"

gh secret delete GH_PACKAGES_TOKEN --repo noorinalabs/noorinalabs-landing-page
gh secret delete GH_PACKAGES_TOKEN --repo noorinalabs/noorinalabs-isnad-graph
```

### 3.8. `DEPLOY_SSH_PRIVATE_KEY` — TWO-STAGE migration

> Value sources:
> - Stage 1 (org-scope transitional): `$STAGING/org/DEPLOY_SSH_PRIVATE_KEY` — current shared keypair per § 3.0.a `TODO(santiago):`.
> - Stage 2 (env-scope): `$STAGING/env/staging/DEPLOY_SSH_PRIVATE_KEY` and `$STAGING/env/production/DEPLOY_SSH_PRIVATE_KEY` — generated at per-env Hetzner VPS cutover (main#141); new keypairs, each with its public half added to its env's VPS `authorized_keys`.

**Stage 1 — org-scope (transitional, restores parity with stg/prod split):**

```bash
gh secret set DEPLOY_SSH_PRIVATE_KEY --org noorinalabs --visibility selected \
  --repos noorinalabs-deploy,noorinalabs-landing-page,noorinalabs-isnad-graph \
  --body "$(cat "$STAGING/org/DEPLOY_SSH_PRIVATE_KEY")"

gh secret delete DEPLOY_SSH_PRIVATE_KEY --repo noorinalabs/noorinalabs-deploy
gh secret delete DEPLOY_SSH_PRIVATE_KEY --repo noorinalabs/noorinalabs-landing-page
gh secret delete DEPLOY_SSH_PRIVATE_KEY --repo noorinalabs/noorinalabs-isnad-graph
```

**Stage 2 — env-scope (after per-env Hetzner VPS exists per main#141):**

```bash
# Stage as separate keys per env, replace org-scoped above
gh secret set DEPLOY_SSH_PRIVATE_KEY \
  --repo noorinalabs/noorinalabs-deploy --env staging \
  --body "$(cat "$STAGING/env/staging/DEPLOY_SSH_PRIVATE_KEY")"
gh secret set DEPLOY_SSH_PRIVATE_KEY \
  --repo noorinalabs/noorinalabs-deploy --env production \
  --body "$(cat "$STAGING/env/production/DEPLOY_SSH_PRIVATE_KEY")"
# Then delete the org-scoped transitional secret
gh secret delete DEPLOY_SSH_PRIVATE_KEY --org noorinalabs
```

### 3.9. Env-scope migrations (Tier C, executed via deploy#155 envs)

For each Tier-C secret, set in **both** `staging` and `production` GH Environments on `noorinalabs-deploy`. Values are sourced from the staging tree per § 3.0.b — **no interactive prompts** (the bare `gh secret set … --env …` form prompts stdin, which loops non-deterministically and fails outright in non-TTY shells).

> Value sources: `$STAGING/env/staging/<SECRET>` and `$STAGING/env/production/<SECRET>` (staged per § 3.0.b from the canonical VPS env files — see § 3.0.a).

**Pre-flight — verify every required staging file exists before running the loop:**

```bash
TIER_C=(
  POSTGRES_DB POSTGRES_PASSWORD POSTGRES_USER
  USER_POSTGRES_DB USER_POSTGRES_PASSWORD USER_POSTGRES_USER
  REDIS_PASSWORD USER_REDIS_PASSWORD
  NEO4J_PASSWORD NEO4J_USER
  GRAFANA_ADMIN_PASSWORD
  KAFKA_CLUSTER_ID KAFKA_UI_USER KAFKA_UI_PASSWORD
  DEPLOY_VPS_IP
)

missing=0
for SECRET in "${TIER_C[@]}"; do
  for ENV in staging production; do
    if [ ! -s "$STAGING/env/$ENV/$SECRET" ]; then
      echo "MISSING: $STAGING/env/$ENV/$SECRET"
      missing=1
    fi
  done
done
[ "$missing" -eq 0 ] || { echo "ABORT: stage all Tier-C values per § 3.0 before running § 3.9"; exit 1; }
```

**Set — two-env write per secret, values from staging tree:**

```bash
for SECRET in "${TIER_C[@]}"; do
  gh secret set "$SECRET" --repo noorinalabs/noorinalabs-deploy --env staging \
    --body "$(cat "$STAGING/env/staging/$SECRET")"
  gh secret set "$SECRET" --repo noorinalabs/noorinalabs-deploy --env production \
    --body "$(cat "$STAGING/env/production/$SECRET")"
done
```

**Verify — each secret is readable at env scope:**

```bash
for SECRET in "${TIER_C[@]}"; do
  for ENV in staging production; do
    gh api "repos/noorinalabs/noorinalabs-deploy/environments/$ENV/secrets/$SECRET" \
      --jq '.name' || echo "MISSING at $ENV: $SECRET"
  done
done

# Then trigger one deploy-{stg,prod}.yml run and confirm env resolution before proceeding.
```

**Delete — repo-level copies (and isnad-graph copy if present):**

```bash
for SECRET in "${TIER_C[@]}"; do
  gh secret delete "$SECRET" --repo noorinalabs/noorinalabs-deploy 2>/dev/null || true
  gh secret delete "$SECRET" --repo noorinalabs/noorinalabs-isnad-graph 2>/dev/null || true
done
```

> **Note on seed-then-rotate:** Tier C assumes env values actually differ between `staging` and `production`. If they don't yet (single shared VPS pre-cutover), stage both `$STAGING/env/staging/<SECRET>` and `$STAGING/env/production/<SECRET>` with the SAME current value, complete this section, then rotate `production`-side values separately during the per-env Hetzner cutover (main#141). The staging tree gives you a single place to rewrite values between rotations — never re-type from memory.

### 3.10. Tier-D leave-as-is

`TF_STATE_B2_APP_KEY` and `TF_STATE_B2_KEY_ID` stay repo-scoped on `noorinalabs-deploy` — only consumed by `terraform.yml`.

### 3.11. Tier-E deferral

`PIPELINE_B2_*` (5 secrets) stay repo-scoped on `noorinalabs-deploy` until `noorinalabs-data-acquisition` and `noorinalabs-isnad-ingest-platform` gain CI (currently unscheduled; track under main#141 successor meta). Re-audit when either repo adds a `.github/workflows/*.yml` file.

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
