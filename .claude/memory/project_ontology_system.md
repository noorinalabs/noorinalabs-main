---
name: project_ontology_system
description: Two-layer ontology — generate-structural (ontology_gen + aggregate) + curate-semantic (/ontology-rebuild + checksums); /ontology-librarian surfaces both; Hook 15 ADVISORY since #857; lifecycle integrated by #862
type: project
status: active
originSessionId: 607a8778-830e-4ba7-a5e3-de78682fa871
---
The ontology is a **two-layer, two-update-path** system (C×T2, #820/#856, lifecycle integrated by #862):

## Layer 1 — Semantic overlay (hand-curated)

- **Files:** `ontology/domain.yaml`, `ontology/services.yaml`, `ontology/conventions.md`, `ontology/repos/*.yaml`, other hand-edited `*.md`
- **Tracker:** PostToolUse hook (`ontology_tracker.py`) — auto-updates `ontology/checksums.json` on every Edit/Write to overlay files. Skips `ontology/structural/` (`SKIP_PATTERNS`, #857).
- **Resolver:** `/ontology-rebuild` skill — reads `checksums.json` dirty entries, reconciles overlay files + auto-updatable docs, marks `last_resolved` = `last_tracked`. NEVER touches the structural layer.

## Layer 2 — Structural index (generated)

- **Files:** `ontology/structural/llms.txt` (section-loadable per-module index), `code-graph.json` (machine-readable graph), `cross-repo-graph.json` (central aggregated index, repo-namespaced)
- **Generator:** `.claude/lib/ontology_gen/` (#855) — `PYTHONPATH=.claude/lib python3 -m ontology_gen . --out ontology/structural/` regenerates the per-repo index wholesale from source code (Python/TS/Cypher).
- **Aggregator:** `ontology_gen.aggregate` (#856) — `PYTHONPATH=.claude/lib python3 -m ontology_gen.aggregate .` rolls each in-scope repo's `code-graph.json` into the central `cross-repo-graph.json`.
- NOT checksum-tracked (always-current-by-regeneration). `/ontology-rebuild` NEVER resolves it.

## Librarian (#862)

`/ontology-librarian` skill — read-only reference for **both layers**:
- Step 1a: semantic overlay staleness (checksums.json dirty count)
- Step 1b: structural index staleness (source files changed since last `llms.txt` commit)
- Step 2b: structural index lookup (grep `ontology/structural/llms.txt` by section for modules/symbols/edges relevant to query)
- Hook 15 (`enforce_librarian_consulted`): ADVISORY since #857 — emits systemMessage on Edit/Write/NotebookEdit if not consulted; does NOT block.
- Sentinel fallback: skill writes `.claude/.consulted/ontology-librarian/<cwd-hash>.marker` (worktree-flush race guard, #169/#176).

## Lifecycle integration (#862)

- **Session start Step 3** — (3a) `/ontology-rebuild` for semantic overlay; (3b) structural staleness check + regenerate + commit if source files changed
- **Wave wrapup Step 12** — (12a) `/ontology-rebuild` for semantic overlay; (12b) regenerate structural index + aggregate + commit
- **Wave retro Step 1** — `/ontology-librarian` staleness check for both layers

## Hook 15 (advisory, #857)

`enforce_librarian_consulted` is advisory since #857 — the structural layer is always-current-by-regeneration, so the staleness risk it guarded against no longer exists for that layer. Still best practice; subagent prompts should include "first action: run `/ontology-librarian {topic}`".

## Current structure (P6W17, updated P7W18 #862)

```
ontology/
  checksums.json          # Semantic overlay tracker (176+ files, version-controlled)
  structural/             # GENERATED — NOT checksum-tracked
    llms.txt              # Per-repo structural index (4,229 lines, 3760 nodes, 5762 edges at P6W17)
    code-graph.json       # Machine-readable graph
    cross-repo-graph.json # Central cross-repo aggregation
  domain.yaml / services.yaml / conventions.md
  repos/{isnad-graph,user-service,landing-page,design-system,deploy,ingestion,isnad-ingest-platform}.yaml
```
