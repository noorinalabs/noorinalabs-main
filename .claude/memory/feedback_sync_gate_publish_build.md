---
name: feedback_sync_gate_publish_build
description: "pre_commit_ci_sync.py bare-`.` false-fails on repos with a publish/release workflow (docker `build` kind); scope to quality-gate workflows until trigger-aware fix lands"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: d8a5fc5c-6b55-468a-b0a0-23817f47074f
---

`pre_commit_ci_sync.py .` (bare, default all-workflows discovery) **false-fails** on any repo that has a **publish/release workflow** (e.g. `ghcr-publish.yml`, `deploy.yml`) whose `docker build` / `build-and-push` step classifies as the gate's `build` kind. The gate then demands pre-commit mirror a `build` hook — but a release-time container build is NOT a local fast-feedback check, so mirroring it is nonsensical.

**Why:** The canonical org direction (parent #571/#572) is "unscoped gate + actionlint pre-commit mirror keeps it green." That holds for repos whose ONLY workflows are quality gates (parent, landing-page — landing's `build` kind comes from a PR-gate `npm run build` which it legitimately mirrors). It breaks on repos that ALSO carry a publish workflow whose `build` kind has no PR-gate counterpart.

**How to apply:** For a repo with a publish/release workflow, scope the gate to the **quality-gate workflows only**: `python3 .../pre_commit_ci_sync.py . --ci .github/workflows/ci.yml --ci .github/workflows/docs.yml` (exclude `ghcr-publish.yml`/`deploy.yml`). This preserves the "scan docs.yml too, actionlint mirror keeps it green" intent (actionlint mirrored both sides) without forcing a docker-build pre-commit hook. Do NOT (a) add a no-op `build` hook or (b) tighten patterns.

**Canonical fix in flight:** upstream tracker **#576** folds in the BETTER fix — make `pre_commit_ci_sync.py` **trigger-aware** (skip publish/release-only workflows by their `on:` triggers). Once #576 lands + re-vendors into child repos, they can drop the `--ci` scoping and go fully unscoped. Until then, the ci.yml+docs.yml scoping is the approved interim (team-lead approved on user-service us#142 2026-05-31; same root issue Aisha hit on deploy).

**Batch-2 rollout note:** any child repo with a GHCR/publish workflow (ingest-platform, design-system likely) hits this same false-positive under bare-`.` — apply the same interim scoping. First-occurrence repos: user-service (`ghcr-publish.yml`), deploy. Relates to [[feedback_enforcement_hierarchy]] (hook>skill>charter — the gate IS the hook-tier enforcement) and the W14 docs-CI rollout template.
