---
name: project_ontology_system
description: Three-role ontology system (tracker hook, resolver skill, librarian skill) with checksums.json tracking; Hook 15 enforces librarian consultation before Edit/Write
type: project
status: active
originSessionId: 607a8778-830e-4ba7-a5e3-de78682fa871
---
Ontology system has three roles:
- **Change Tracker**: PostToolUse hook on Edit/Write — auto-updates `ontology/checksums.json`
- **Change Resolver**: `/ontology-rebuild` skill — processes dirty files, updates ontology + auto-updatable docs
- **Librarian**: `/ontology-librarian` skill — read-only reference, staleness check at session start

**Why:** Structured knowledge base that stays current with code changes, readable by humans and Claude.

**How to apply**:
- **Hook 15 (`enforce_librarian_consulted`)**: BLOCKS Edit/Write/NotebookEdit unless `/ontology-librarian` was invoked earlier in the same session — applies to orchestrator AND every spawned subagent. Subagent prompts must include "MANDATORY first action: run `/ontology-librarian {topic}`". The hook scans the agent's own session transcript; passing librarian output FROM the orchestrator is not sufficient. There is no in-band override (see charter `hooks.md` § Hook 15).
- **Worktree-subagent fallback**: Hook 15 also reads a sentinel file written by the librarian skill at `.claude/.librarian-consulted/<cwd-hash>.marker` to survive transcript-flush race (issue #169). Skill writes this automatically.
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
