---
name: project_ontology_system
description: Three-role ontology system (tracker hook, resolver skill, librarian skill) with checksums.json tracking of the SEMANTIC OVERLAY only; structural layer is generated; Hook 15 is ADVISORY (since #857)
type: project
status: active
originSessionId: 607a8778-830e-4ba7-a5e3-de78682fa871
---
Ontology system has three roles:
- **Change Tracker**: PostToolUse hook on Edit/Write — auto-updates `ontology/checksums.json` for the hand-curated SEMANTIC OVERLAY only (skips generated `ontology/structural/`, #857)
- **Change Resolver**: `/ontology-rebuild` skill — processes dirty OVERLAY files, updates ontology + auto-updatable docs (never the structural layer)
- **Librarian**: `/ontology-librarian` skill — read-only reference, staleness check at session start

**#857 (P6W17, #820/C×T2):** the **structural** layer at `ontology/structural/` is now GENERATED (owned generator #855), always-current-by-regeneration — NOT checksum-tracked, NOT resolved by `/ontology-rebuild`. Tracker + resolver scope = the hand-curated overlay (`domain.yaml`/`services.yaml`/`conventions.md`/`repos/*.yaml`/`*.md`). Hook 15 softened from hard block → ADVISORY because structural context is current-by-regeneration, not stale.

**Why:** Structured knowledge base that stays current with code changes, readable by humans and Claude.

**How to apply**:
- **Hook 15 (`enforce_librarian_consulted`)**: ADVISORY since #857 — emits a `systemMessage` warning on Edit/Write/NotebookEdit when `/ontology-librarian` was not invoked earlier in the session, but DOES NOT block (exit 0 always). Still best practice; subagent prompts should still include "first action: run `/ontology-librarian {topic}`" so the agent loads the semantic overlay. The hook scans the agent's own session transcript; passing librarian output FROM the orchestrator is not sufficient to suppress the advisory (see charter `hooks.md` § Hook 15).
- **Worktree-subagent fallback**: Hook 15 also reads a sentinel file written by the librarian skill at `.claude/.consulted/ontology-librarian/<cwd-hash>.marker` to survive transcript-flush race (issue #169, namespaced per #176). Skill writes this automatically.
- **Session start**: `/session-start` runs `/ontology-rebuild` (step 2) — librarian staleness check is part of `/wave-retro` step 1.
- **Wave wrapup**: `/ontology-rebuild` runs as step 12.

## Current ontology structure (verified 2026-05-10)

```
ontology/
  checksums.json          # 176 tracked files, 0 dirty at audit time
  domain.yaml             # Org-wide entities & relationships
  services.yaml           # Org-wide service map
  conventions.md          # Org-wide conventions & patterns
  repos/
    isnad-graph.yaml
    user-service.yaml
    landing-page.yaml
    design-system.yaml
    deploy.yaml
    ingestion.yaml
    isnad-ingest-platform.yaml
```

Setup prompt was moved to the bootstrap repo (removed from noorinalabs-main at commit 84daed5).
