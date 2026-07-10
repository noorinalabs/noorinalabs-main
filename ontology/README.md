# Ontology

The `ontology/` directory is the project-wide knowledge base for Noorina Labs.
It records domain entities, service topology, and cross-repo conventions so
that agents, reviewers, and contributors share a common vocabulary before
touching code.

This file is the canonical entry point. Start here.

---

## Purpose

The ontology exists to solve a concrete problem: code across seven repos shares
concepts (narrators, hadith chains, isnad graphs, services, conventions) but
has no single place that names and relates them. Without a shared vocabulary,
agents and contributors re-derive the same structure from scratch, introduce
inconsistent terminology, and miss cross-repo dependencies.

The ontology captures two distinct kinds of knowledge and keeps them in
two separate layers so neither contaminates the other:

- **Structure** — which files, modules, classes, and functions exist, and how
  they relate (`imports`, `calls`, `inherits`, etc.). This is derived from the
  code and generated automatically.
- **Meaning** — what a narrator *is*, what the isnad graph *represents*, how
  services depend on each other, what the coding conventions *require*. This
  requires human authorship and stays hand-curated.

---

## The C×T2 two-layer model

The ontology is two cooperating layers (the C×T2 topology, main#820, main#856):

### Layer 1: Structural (generated)

Location: `ontology/structural/`

| File | What it contains |
|------|-----------------|
| `code-graph.json` | Per-repo node/edge graph — files, modules, classes, functions and the typed edges between them (`contains`, `imports`, `imports_from`, `calls`, `inherits`, `references`). One file per repo, rebuilt from that repo's source. |
| `llms.txt` | Human-readable summary of the structural index; consumed by `/ontology-librarian` as a quick-reference digest. |
| `cross-repo-graph.json` | Central aggregated graph: the union of every in-scope repo's `code-graph.json`, with all node ids namespaced by repo (e.g. `isnad-graph/src/api/app.py`, `main/.claude/lib/ontology_gen/aggregate.py::aggregate`). Lives in `noorinalabs-main`. |

The structural layer is produced by the generator at `.claude/lib/ontology_gen/`
(main#855). It is **never hand-edited**, **not checksum-tracked**, and — since
main#939 — **not committed**: it is a **gitignored build product**, rebuilt on
demand rather than stored in git. Committing it made every concurrent PR conflict
on a generated whole-file artifact (the only correct resolution being "discard both
sides and regenerate"), and the union merge-driver that tried to absorb that could
never run on GitHub's server-side merge. To (re)build it, run the aggregator — it
regenerates **every in-scope repo's** per-repo index from source and writes the
cross-repo graph, so nothing depends on a committed copy:

```bash
PYTHONPATH=.claude/lib python3 -m ontology_gen.aggregate .
```

`/session-start` Step 3b and `/wave-wrapup` Step 12b do this automatically. Do not
resolve the structural layer with `/ontology-rebuild`.

### Layer 2: Semantic overlay (curated)

Location: root of `ontology/`

| File | What it contains |
|------|-----------------|
| `domain.yaml` | Org-wide entities and relationships: narrators, hadiths, isnad chains, collections, locations, and how they relate. |
| `services.yaml` | Org-wide service map: APIs, data stores, message queues, and integration points. |
| `conventions.md` | Cross-repo coding conventions, patterns, and architectural decisions — languages, linting, data modeling, API shape, shell environment. |
| `repos/*.yaml` | Per-repo detail: internal modules, pipeline stages, ownership, and `structural_ref` pointers into the generated index. |
| `checksums.json` | Dirty-tracking index for the semantic overlay only. Updated automatically by the ontology tracker hook on every Edit/Write. |

The semantic overlay requires human judgment and changes intentionally. It is
dirty-tracked and resolved via `/ontology-rebuild`.

### Referencing structural nodes from the overlay

The overlay references generated structural nodes rather than re-describing
structure. Two forms:

- YAML: `structural_ref: <id>` or `structural_refs: [<id1>, <id2>]`
- Markdown: `[[structural:<id>]]`

Node ids follow the pattern `<repo-relative-path>` for files and
`<path>::<qualname>` for symbols. In the cross-repo graph every id is
prefixed by repo name: `<repo>/<id>`.

---

## Three roles

| Role | Mechanism | What it does |
|------|-----------|-------------|
| **Change Tracker** | PostToolUse hook (`ontology_tracker.py`) | On every Edit/Write, hashes the modified file and records `last_tracked` in `checksums.json`. Scope: semantic overlay only — skips `ontology/structural/` (main#857). |
| **Change Resolver** | Skill `/ontology-rebuild` | Reads dirty entries (`last_tracked != last_resolved`), updates semantic overlay files and auto-updatable docs, marks `last_resolved`. Never touches the structural layer. |
| **Librarian** | Skill `/ontology-librarian` | Read-only reference: staleness check, context retrieval, and structural index lookup. Never modifies any file. |

The tracker and resolver are scoped to the **semantic overlay only** (main#857).
The structural layer is regenerated by its owned generator — the tracker skips
it so it never appears as a dirty entry, and the resolver never resolves it.

Hook 15 (`enforce_librarian_consulted.py`) emits an advisory warning on
Edit/Write when `/ontology-librarian` was not consulted in the current session.
It was a hard block before main#857; it was softened to advisory once the
structural layer became always-current-by-regeneration (so the staleness it
guarded against no longer applies to that layer).

---

## Directory layout

```
ontology/
  README.md               # This file — canonical entry point
  checksums.json          # Dirty-tracking for the SEMANTIC OVERLAY only
  domain.yaml             # Org-wide entities and relationships
  services.yaml           # Org-wide service map
  conventions.md          # Cross-repo coding conventions and patterns
  lifecycle.md            # Phase/wave lifecycle as an ordered slash-command flow
  repos/
    isnad-graph.yaml
    user-service.yaml
    design-system.yaml
    deploy.yaml
    ingestion.yaml
    isnad-ingest-platform.yaml
    landing-page.yaml
  structural/             # GENERATED build product — gitignored (main#939), never hand-edit
    code-graph.json       # Per-repo structural index (noorinalabs-main's own)
    llms.txt              # Human-readable structural digest
    cross-repo-graph.json # Aggregated cross-repo graph (noorinalabs-main only)
```

Generator and skills:

```
.claude/lib/ontology_gen/   # Generator package (main#855, main#856)
.claude/skills/ontology-librarian/
.claude/skills/ontology-rebuild/
```

---

## Setup

### Prerequisites

- Python 3.12+ with the `ontology_gen` package importable (run from `.claude/lib/`
  or with that directory on `PYTHONPATH`).

### No merge-driver setup (main#939)

The structural index used to be committed and needed a per-clone union merge
driver to absorb spurious conflicts. That is gone: the index is now a **gitignored
build product**, so there is nothing in git to merge and **no setup step**. (The
merge driver could never have worked on GitHub anyway — custom `merge=` drivers
live in per-clone `git config` and GitHub's server-side merge never runs them,
which is exactly why committing the index made every concurrent PR conflict.)

### Build the structural layer (one command)

The aggregator is the primary entry point: it regenerates **every in-scope repo's**
per-repo index from source and writes the cross-repo graph. Run from `.claude/lib/`
(or with that directory on `PYTHONPATH`):

```bash
cd /path/to/noorinalabs-main/.claude/lib
python3 -m ontology_gen.aggregate ../..
```

The aggregator degrades gracefully — repos not cloned beneath the root are skipped
and reported. Pass `--no-regenerate` to roll up whatever indices are already on
disk instead of rebuilding.

### Generate a single repo's index (without aggregating)

```bash
cd /path/to/noorinalabs-main/.claude/lib
python3 -m ontology_gen /path/to/repo --out /path/to/repo/ontology/structural/
```

Optional flags:

- `--repo-name <name>` — display name used in the index header (defaults to
  the basename of the repo root).
- `--out <dir>` — output directory for `code-graph.json` and `llms.txt`.

---

## Getting started: first-run walkthrough

1. **Build the structural layer** (no setup step needed — it is a gitignored build
   product, main#939):

   ```bash
   cd .claude/lib
   python3 -m ontology_gen.aggregate ../..
   ```

2. **Read the structural digest** to get a quick feel for the codebase shape:

   ```bash
   cat ontology/structural/llms.txt
   ```

3. **Run the librarian** to check semantic overlay health and retrieve context:

   ```
   /ontology-librarian
   ```

   With a topic:

   ```
   /ontology-librarian narrator isnad graph
   ```

4. **Read the semantic overlay** for the area you are about to work on —
   `domain.yaml` for domain entities, `services.yaml` for service topology,
   `conventions.md` for coding conventions, `repos/<name>.yaml` for
   repo-specific details.

---

## Day-to-day usage

### Before making code changes

Run `/ontology-librarian <topic>` to load relevant context. Hook 15 emits an
advisory warning if you skip this step and proceed to Edit/Write without it.

Example queries:

- `/ontology-librarian narrator API endpoints`
- `/ontology-librarian isnad graph Neo4j`
- `/ontology-librarian design system tokens`

The librarian checks `checksums.json` for dirty semantic overlay entries,
queries `domain.yaml`, `services.yaml`, `conventions.md`, and `repos/*.yaml`
for relevant content, and surfaces `ontology/structural/llms.txt` as the
structural digest.

### After editing semantic overlay files

The ontology tracker hook runs automatically and records the new hash in
`checksums.json`. No manual step is required to mark files dirty.

To resolve dirty entries (update the ontology to reflect the changes):

```
/ontology-rebuild
```

The resolver reads dirty entries, updates the semantic overlay, marks
`last_resolved`, and reports what changed. It never touches the structural
layer.

### Regenerating the structural layer

The structural layer (`ontology/structural/`) is not dirty-tracked, not resolved
by `/ontology-rebuild`, and — since main#939 — not committed (a gitignored build
product). To rebuild it after code changes, run the aggregator; it regenerates
every in-scope repo's per-repo index and the cross-repo graph in one pass:

```bash
cd .claude/lib
python3 -m ontology_gen.aggregate ../..
```

You never commit `code-graph.json` / `llms.txt` / `cross-repo-graph.json` — they
are build products, rebuilt on demand and gitignored. `/session-start` Step 3b and
`/wave-wrapup` Step 12b rebuild them automatically, so in normal flow you rarely
run this by hand.

### Wave integration points

- `/wave-wrapup` runs `/ontology-rebuild` before closing a wave (step 12).
- `/wave-retro` runs `/ontology-librarian` as a staleness check (step 1).
- `/session-start` runs `/ontology-rebuild` at step 2 of the startup protocol.

---

## Code is the arbiter of truth

When code and an ontology entry disagree, **the code wins**. The resolver
derives the semantic overlay and auto-updatable docs *from* the code — it never
edits code to match a stale doc. The resolution order (code first, then docs,
then high-level-docs) ensures that code is resolved before anything derived from
it. Recommend-only docs (architecture diagrams, high-level summaries) are
flagged for human review rather than auto-rewritten, but the conflict is
reported with code as the reference.

This principle is codified in `conventions.md` § "Ontology: code is the arbiter
of truth" (main#768) and enforced PR-side by the advisory `doc-freshness` gate
(`.claude/lib/doc_freshness.py`).

---

## Further reading

- `conventions.md` § "Overlay → structural references" — full C×T2 topology
  spec, reference forms, and resolution rules (main#820, main#856).
- `.claude/skills/ontology-librarian/SKILL.md` — librarian usage, sentinel
  pattern, and staleness-reporting thresholds.
- `.claude/skills/ontology-rebuild/SKILL.md` — resolver steps and scope rules.
- `CLAUDE.md` § Ontology — harness-level setup, Hook 15, session-start
  integration, and the three-role table.
- `ontology/lifecycle.md` — the full phase/wave lifecycle as an ordered
  slash-command flow.
