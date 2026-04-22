---
name: ontology-librarian
description: Read-only ontology reference — staleness check, context lookup, and knowledge retrieval
args: query
---

The ontology librarian provides read-only access to the project ontology. It checks for staleness, retrieves relevant context, and reports which references may be out of date. It never modifies the ontology — that's the resolver's job.

The `query` argument is optional. If provided, it's a natural language question or entity/service name to look up. If omitted, runs a staleness check and provides a summary.

## When to use

- **Session start** — run automatically to report ontology health
- **Starting work on a GH issue** — look up relevant entities, services, and patterns before coding
- **One-off changes** — check what the ontology knows about the area you're about to modify
- **Manual invocation** — answer questions about the domain, architecture, or conventions

## Instructions

### 0. Write Hook 15 consultation sentinel

Before anything else, write a cwd-keyed sentinel file that Hook 15 (`enforce_librarian_consulted`) reads as a second acceptance signal. This is required because in worktree-subagent sessions the transcript JSONL the hook scans may not yet contain this Skill `tool_use` entry (race on transcript flush — see issue #169). The sentinel is a robust fallback that survives the flush race.

```bash
mkdir -p .claude/.librarian-consulted
HASH=$(pwd | sha1sum | cut -c1-16)
printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(pwd)" > .claude/.librarian-consulted/"$HASH".marker
```

**Do not remove this step.** It is the Hook 15 consultation marker for the current cwd; deleting it re-introduces the #169 regression for subagents working in worktrees. The directory is gitignored.

### 1. Staleness check

Read `ontology/checksums.json` and count dirty files (where `last_tracked != last_resolved`):

```bash
cat ontology/checksums.json
```

Report staleness status:
- **0 dirty files**: "Ontology is current."
- **1–5 dirty files**: "{N} files pending — ontology is slightly behind."
- **6–15 dirty files**: "{N} files pending — consider running `/ontology-rebuild`."
- **16+ dirty files**: "{N} files pending — strongly recommend `/ontology-rebuild` before starting work."

**Important:** The librarian does NOT trigger the resolver. It reports staleness so the user can decide. If the user asks you to update, tell them to run `/ontology-rebuild`.

### 2. Context retrieval (if query provided)

If a `query` argument was given, search the ontology for relevant information:

1. **Entity lookup** — search `ontology/domain.yaml` for matching entities, relationships
2. **Service lookup** — search `ontology/services.yaml` for matching services, APIs, data stores
3. **Convention lookup** — search `ontology/conventions.md` for relevant patterns
4. **Repo lookup** — search `ontology/repos/*.yaml` for repo-specific details

Present findings in a concise format:

```
**Ontology: {query}**

**Entities:** {matching entities and their relationships}
**Services:** {matching services and their integrations}
**Conventions:** {relevant patterns or rules}
**Repo details:** {repo-specific information}

**Staleness warning:** {list any source files for these entries that are dirty}
```

### 3. Summary (if no query)

If no query was provided, give a brief ontology health summary:

```
**Ontology Status**

**Health:** {current | {N} files behind}
**Domain:** {count} entities, {count} relationships
**Services:** {count} services, {count} data stores
**Repos covered:** {list}
**Last full rebuild:** {most recent resolved_at timestamp}

{staleness details if any}
```

### 4. Stale reference warnings

When reporting query results, check if any of the source files that contributed to those ontology entries are dirty. If so, append a warning:

```
⚠ The following source files have changed since the ontology was last updated.
  Information from these files may be outdated:
  - {file_path} (changed {tracked_at}, last resolved {resolved_at})
```

This lets the user know which specific pieces of information to treat with caution.

## What remains manual

- The librarian never modifies ontology files — use `/ontology-rebuild` for that
- The librarian never triggers the resolver — it reports, the user decides
- Structural questions about the ontology design should go to the project owner
