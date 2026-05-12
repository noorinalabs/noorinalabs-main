---
name: promotion-audit
description: Deterministic audit of the memory → charter → skill → hook promotion pipeline. Auto-promotes AUTO-tier artifacts, files DECIDE-tier issues with drafts, writes a per-wave audit log.
args: wave_name (optional — defaults to the current wave from cross-repo-status.json)
---

Run a deterministic audit of the promotion pipeline. Every step below is backed by a pure function in `helpers.py` so the same input produces byte-identical output.

## Context

The project's enforcement hierarchy is **hook > skill > charter > memory** (see `.claude/team/charter.md` § Enforcement Hierarchy and memory `feedback_enforcement_hierarchy.md`). Rules migrate upward along that path as evidence accumulates.

| From | To | Trigger |
|---|---|---|
| memory | charter | `promotion_target: charter` AND `retro_citations >= threshold` AND `status: active` |
| charter | skill | Section marker `<!-- promotion-target: skill -->` AND skill-invocation signal >= threshold |
| skill | hook | `promotion-target: hook` in skill frontmatter AND invocation signal >= threshold |

Skill-to-hook **ALWAYS** produces a DECIDE-tier draft issue — never auto-applies (D6, hooks are security-sensitive).

## Instructions

### 1. Resolve wave name

If invoked with no argument, read `cross-repo-status.json` for `current_wave`. Use that slug (e.g., `wave-9`) as the audit wave name. If the arg is provided, trust it.

### 2. Gather inputs (all deterministic — helpers.py)

```python
from helpers import (
    read_all_memories,
    read_all_charter_sections,
    read_all_skills,
    find_already_promoted_in_charter,
    count_retro_citations,
    count_skill_invocations,
    classify,
    render_audit_table,
)

memories  = read_all_memories(memory_dir)              # list[Memory]
sections  = read_all_charter_sections(charter_dir)     # list[Section] — only sections with a promotion-target marker
skills    = read_all_skills(skills_dir)                # list[Skill]
already   = find_already_promoted_in_charter(charter_dir)  # set[str] — aggregates Promotion provenance: blocks AND <!-- Promoted from memory: X --> markers across all charter sub-docs (#283)
```

### 3. Classify each candidate (pure function)

For each memory, charter section, and skill, compute a `Decision` via `classify()`:

- **AUTO** — thresholds met, promotion target is charter or skill, NOT already promoted
- **DECIDE** — thresholds met, target is hook (always DECIDE), OR `requires_decision: true` override, OR signals ambiguous
- **KEPT** — promotion-target is `none`, thresholds not yet met, or status is `active` with no promotion intent
  - **STALE-OPT-OUT (informational sub-class)** — when a memory has `promotion_target: none` AND `retro_citations >= 2 * threshold`, the entry stays KEPT (the opt-out is authoritative) but is rendered in a separate sub-list so operators can spot drift during wave-retro. No auto-action, no issue filed, no override of the opt-out. (#158)
- **SUPERSEDED** — status is `superseded` or `enforced-elsewhere` with an explicit `superseded_by` reference
- **ALREADY-PROMOTED** — name appears in `find_already_promoted_in_charter()` set (recognized via `Promotion provenance:` blocks AND `<!-- Promoted from memory: X -->` HTML-comment markers across all charter sub-docs; #283)

### 4. Produce artifacts

For each AUTO decision:
- **memory → charter:** apply `templates/charter-section.md` to the memory, append to the appropriate charter file, mark memory `superseded_by: charter:{file} § {section}`. Stage the diff, commit on a new branch as Aino.
- **charter → skill:** apply `templates/skill-scaffold.md` to the section, write `.claude/skills/{slug}/SKILL.md`, add a back-reference comment `<!-- promoted-to: skills/{slug} -->` after the section's `promotion-target` marker. Stage, commit.

For each DECIDE decision:
- Apply `templates/hook-draft.md` to generate an issue title + body. Use `gh issue create --label "enhancement" --body-file` (NOT `--body` — avoids the `|` hook bug #146).

For AUTO artifacts, open a PR following the same 2-reviewer pattern as any charter-touching PR:
- Branch: `A.Virtanen/promotion-audit-{wave}-{timestamp}` (Aino as author)
- Reviewers: Wanjiku (TPM) for coordination; Nadia (PD) for charter additions, Aino for skill scaffolds. Q3 decision: auto-promote artifacts land via PR, not direct commit.

### 5. Render the audit table

Use `render_audit_table(decisions)` to produce deterministic markdown with four subsections:

```
## Promotion Audit — {wave_name}

### AUTO-PROMOTED (artifacts generated this run)
| Item | From → To | Signal | Artifact |
|---|---|---|---|
...

### REQUIRES DECISION (issues filed)
| Item | Candidate target | Signal | Issue |
|---|---|---|---|
...

### KEPT (no action — informational)
- {item}: {reason}

**STALE-OPT-OUT (review the opt-out — informational only):**
- {item}: {reason}    ← only rendered when at least one entry crosses 2× threshold

### SUPERSEDED / ALREADY-PROMOTED (no action — informational)
- {item}: {pointer}
```

### 6. Write outputs (Q4 — BOTH)

1. **Append to feedback_log.md** — if the audit runs inside a retro (detect by checking if the most recent `## Retrospective:` entry is on today's date), append under the current retro. Otherwise prepend a fresh `## Promotion Audit — {wave_name} ({DATE})` entry at the top of the log.
2. **Standalone log** — always write to `.claude/team/promotion_audit_log/{wave_name}.md`. Create the directory if it doesn't exist. Overwrite if re-run.

### 7. Report

Print a two-line summary to stdout: counts per decision category and a link to the standalone log:

```
Promotion audit wave-N complete: 0 AUTO · 0 DECIDE · 13 KEPT · 1 SUPERSEDED
Log: .claude/team/promotion_audit_log/wave-N.md
```

## Determinism

The audit MUST produce byte-identical output when re-run on unchanged repo state. To guarantee this:
- Sort every list by a stable key before iteration (memory name, charter path+heading, skill name).
- Use UTC dates pinned to the wave boundary (read from `cross-repo-status.json`), never `datetime.now()`.
- Never read transcript files (per D4(i)).
- Never invoke external tools with nondeterministic output (no `gh api` except for issue creation at the end).

Tests in `.claude/skills/promotion-audit/tests/` cover each helper and a smoke test that verifies the first-run expected outcome (zero AUTO, zero DECIDE on current repo state).

## Integration

- `wave-retro` (see `.claude/skills/wave-retro/SKILL.md`) invokes this skill right after step 7 "Charter change proposals".
- Standalone invocation is supported — operators can run `/promotion-audit` between retros if drift is suspected.
- The output log is greppable: `git log --follow .claude/team/promotion_audit_log/` gives the full promotion history.

## What this skill does NOT do

- It does not promote skill → hook automatically (Q6 locked: hooks are security-sensitive; always DECIDE).
- It does not mutate any memory file in user-level `~/.claude/projects/` — it only reads. If a memory is auto-promoted, the memory's `superseded_by` is updated by the skill (writing to the user-level memory file is allowed per feedback-settings-permission memory).
- It does not scan conversation transcripts — signal sources are charter files, feedback_log.md, and git history only (D4 lightweight).
