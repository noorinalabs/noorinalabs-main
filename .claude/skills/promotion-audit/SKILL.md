---
name: promotion-audit
description: Deterministic audit of the memory → charter → skill → hook promotion pipeline. Auto-promotes AUTO-tier artifacts, files DECIDE-tier issues with drafts, writes a per-wave audit log.
args: wave_name (optional — defaults to the current wave from cross-repo-status.json)
---

Run a deterministic audit of the promotion pipeline. Every step below is backed by a pure function in `helpers.py` so the same input produces byte-identical output.

> See [`.claude/team/lifecycle.md`](../../team/lifecycle.md) § Wave Lifecycle for the canonical skill order and preconditions.

## Context

The project's enforcement hierarchy is **hook > skill > charter > memory** (see `.claude/team/charter.md` § Enforcement Hierarchy and memory `feedback_enforcement_hierarchy.md`). Rules migrate upward along that path as evidence accumulates.

| From | To | Trigger |
|---|---|---|
| memory | charter | `promotion_target: charter` AND `retro_citations >= threshold` AND `status: active` |
| charter | skill | Section marker `<!-- promotion-target: skill -->` AND skill-invocation signal >= threshold |
| skill | hook | `promotion-target: hook` in skill frontmatter AND invocation signal >= threshold |

Skill-to-hook **ALWAYS** produces a DECIDE-tier draft issue — never auto-applies (D6, hooks are security-sensitive).

**Marker convention:** The audit pipeline recognizes exactly two provenance marker shapes — `<!-- Promoted from memory: <filename> (<context>) -->` (Shape 1, charter-tier; parser regex `_HTML_COMMENT_PROMOTED_RE`) and `**Promotion provenance:** <body>` (Shape 2, hook-tier and multi-source; parser regex `_PROVENANCE_RE`). The authoritative source for the SHAPE selection rule is [`charter/skills.md` § Promotion Pipeline Marker Convention](../../team/charter/skills.md#promotion-pipeline-marker-convention). For per-hook authoring discipline (forward-reference filter, paragraph separation), see [`charter/hooks.md` § 6. Promotion Provenance Phrasing](../../team/charter/hooks.md#6-promotion-provenance-phrasing). Any future change to the recognized shapes MUST update the charter section first, then the parser, then this skill — in that order, in a single PR.

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
    classify_memory,
    classify_section,
    classify_skill,
    render_audit_table,
)

memories  = read_all_memories(memory_dir)                  # list[Memory]
sections  = read_all_charter_sections(charter_parent)      # list[Section] — only sections with a promotion-target marker
skills    = read_all_skills(skills_dir)                    # list[Skill]
already   = find_already_promoted_in_charter(charter_parent)  # set[str] — aggregates Promotion provenance: blocks AND <!-- Promoted from memory: X --> markers across all charter sub-docs (#283)
# NOTE: `charter_parent` is the directory CONTAINING `charter/` (e.g. `.claude/team`),
# NOT the `charter/` directory itself. Passing `.claude/team/charter` raises ValueError (#418).
```

### 3. Classify each candidate (pure function)

There is no single `classify()` entry point — each tier transition has its own classifier with a distinct signature, because the signal sources differ (retro citations for memory → charter; invocation counts for charter → skill and skill → hook) and `classify_section` has no `already_promoted` analogue (sections carry their own `promoted_to` back-reference instead).

| Function | Signature | `signals` keys consumed |
|---|---|---|
| `classify_memory(memory, signals, already_promoted)` | `(Memory, dict[str,int], set[str]) -> Decision` | `retro_citations` |
| `classify_section(section, signals)` | `(CharterSection, dict[str,int]) -> Decision` | `skill_invocations`, `threshold` |
| `classify_skill(skill, signals, already_promoted)` | `(Skill, dict[str,int], set[str]) -> Decision` | `skill_invocations`, `threshold` |

Worked example (one item per tier):

```python
mem_decision = classify_memory(
    memories[0],
    signals={"retro_citations": count_retro_citations(memories[0], feedback_log_path)},
    already_promoted=already,
)

sec_decision = classify_section(
    sections[0],
    signals={
        "skill_invocations": count_skill_invocations(sections[0].promoted_to_slug or "", repo_root),
        "threshold": 5,
    },
)

skill_decision = classify_skill(
    skills[0],
    signals={
        "skill_invocations": count_skill_invocations(skills[0].name, repo_root),
        "threshold": 5,
    },
    already_promoted=already,
)
```

Common failure mode: passing the citation/invocation count as a bare int (`classify_memory(mem, cite, already)`) rather than wrapping it in the `signals` dict (`classify_memory(mem, {"retro_citations": cite}, already)`). The classifiers all do `signals.get(...)` and will raise `AttributeError: 'int' object has no attribute 'get'` on a bare int. Always pass a dict.

Each call returns a `Decision` in one of these kinds:

- **AUTO** — thresholds met, promotion target is charter or skill, NOT already promoted
- **DECIDE** — thresholds met, target is hook (always DECIDE), OR `requires_decision: true` override, OR signals ambiguous
- **KEPT** — promotion-target is `none`, thresholds not yet met, or status is `active` with no promotion intent
  - **STALE-OPT-OUT (informational sub-class)** — when a memory has `promotion_target: none` AND `retro_citations >= 2 * threshold`, the entry stays KEPT (the opt-out is authoritative) but is rendered in a separate sub-list so operators can spot drift during wave-retro. No auto-action, no issue filed, no override of the opt-out. (#158)
- **SUPERSEDED** — status is `superseded` or `enforced-elsewhere` with an explicit `superseded_by` reference
- **ALREADY-PROMOTED** — name appears in `find_already_promoted_in_charter()` set (recognized via `Promotion provenance:` blocks AND `<!-- Promoted from memory: X -->` HTML-comment markers across all charter sub-docs; #283)

### 4. Produce artifacts

Resolve the **current wave label** once at the top of this step from `cross-repo-status.json` `current_wave` (e.g. `wave-9` → label `p3-wave-9`). Every artifact created below — AUTO PRs AND DECIDE issues — MUST carry this label so the GitHub Project board's Wave-field sync (see `/board-audit`) routes the artifact to the current wave column. Missing this label is the failure mode #401 was filed against — PRs/issues land off-board and off-wave.

#### AUTO artifacts

For each AUTO decision:
- **memory → charter:** apply `templates/charter-section.md` to the memory, append to the appropriate charter file, mark memory `superseded_by: charter:{file} § {section}`. Stage the diff.
- **charter → skill:** apply `templates/skill-scaffold.md` to the section, write `.claude/skills/{slug}/SKILL.md`, add a back-reference comment `<!-- promoted-to: skills/{slug} -->` after the section's `promotion-target` marker. Stage.

**Commit (Aino identity per `charter/commits.md` § Identity Table):**

```bash
git -c user.name="Aino Virtanen" \
    -c user.email="parametrization+Aino.Virtanen@gmail.com" \
    commit -F .claude/scratch/promotion-audit-{wave}-commit.txt
```

The commit-identity flags are **mandatory** (no shortcut to `git commit -m`) — they're the only way `validate_commit_identity` recognizes Aino as the author. Write the commit message to `.claude/scratch/promotion-audit-{wave}-commit.txt` and pass via `-F`, not heredoc — heredoc inside the parent `-c` line trips the identity-hook parser (memory `feedback_heredoc_in_git_commit.md`). Include two `Co-Authored-By` trailers (Aino + Claude).

**Branch + push:**

```bash
git checkout -b A.Virtanen/promotion-audit-{wave}-{timestamp}
git push -u origin A.Virtanen/promotion-audit-{wave}-{timestamp}
```

**Open the PR** following `charter/pull-requests.md § PR Template` body shape (Summary / Related Issues / Review Checklist + two `Co-Authored-By` trailers). Always include the literal three labels:

```bash
gh pr create \
  --base deployments/phase-{N}/wave-{M} \
  --title "promotion-audit: AUTO promotions for {wave} (closes #N)" \
  --body-file .claude/scratch/promotion-audit-{wave}-pr-body.md \
  --label tech-debt \
  --label enhancement \
  --label p3-{wave}
```

The label set is **non-negotiable**: `tech-debt` (this is process/quality work), `enhancement` (functional addition to charter/skills), AND the current wave label (`p3-{wave}`). Validate the labels actually stuck — `gh pr edit` silently no-ops on bad label names (memory `feedback_gh_pr_edit_silent_noop.md`):

```bash
gh pr view <PR#> --json labels --jq '.labels[].name'
# Expect: enhancement, p3-{wave}, tech-debt (any order)
```

If any label is missing, retry with `gh pr edit <PR#> --add-label <name>` and re-verify.

**Add to project board (Project 2):**

```bash
PR_URL=$(gh pr view <PR#> --json url --jq .url)
gh project item-add 2 --owner noorinalabs --url "$PR_URL"
```

`gh project item-add` is in the silent-no-op family (memory `feedback_gh_pr_edit_silent_noop.md`) — its "no output = success" output is misleading when the item-add fails. **Read-back-verify** the add stuck:

```bash
gh project item-list 2 --owner noorinalabs --format json --limit 200 \
  | jq -r '.items[] | select(.content.url == "'"$PR_URL"'") | .id'
```

A non-empty ID confirms the add succeeded. Empty output = the add silently no-op'd — retry once, then escalate to team-lead if still empty.

**Assign two reviewers** per `charter/agents.md` § Orchestrator checklist when spawning a reviewer. Use SendMessage to spawn each reviewer (do NOT use `gh pr review` — `block_gh_pr_review` enforces; memory `feedback_validate_pr_review_approved_not_reply.md`). The reviewer spawn brief MUST embed the verbatim verdict template with the literal `TechDebt: ` line shape (memory `feedback_techdebt_attestation_literal_line.md`) — `## TechDebt` headers are NOT recognized by `validate_pr_review.py`. Reviewer slate per scope:
- memory → charter promotions: Wanjiku (TPM) + Nadia (PD)
- charter → skill promotions: Wanjiku (TPM) + Aino (yourself ineligible — pick Santiago or Nadia)

Q3 decision: auto-promote artifacts land via PR (2-reviewer gate), not direct commit.

#### DECIDE artifacts

For each DECIDE decision:
- Apply `templates/hook-draft.md` to generate an issue title + body. Write the body to `.claude/scratch/promotion-audit-{wave}-decide-{slug}.md`.
- Create the issue with the **same three-label set** as AUTO PRs (`tech-debt` + `enhancement` + current-wave label) and the same project-board treatment:

```bash
gh issue create \
  --repo noorinalabs/noorinalabs-main \
  --title "<title from template>" \
  --body-file .claude/scratch/promotion-audit-{wave}-decide-{slug}.md \
  --label tech-debt \
  --label enhancement \
  --label p3-{wave}
```

Use `--body-file`, NOT `--body` — the `|` hook bug #146 surfaces on long-prose `--body` arguments.

**Add the issue to Project 2** with the same read-back-verify protocol as AUTO PRs:

```bash
ISSUE_URL=$(gh issue view <N> --json url --jq .url)
gh project item-add 2 --owner noorinalabs --url "$ISSUE_URL"
gh project item-list 2 --owner noorinalabs --format json --limit 200 \
  | jq -r '.items[] | select(.content.url == "'"$ISSUE_URL"'") | .id'
```

Empty output = retry; persistent empty after retry = escalate.

#### Determinism note

The `gh` calls in this step (PR/issue creation, project-board adds, label/board verification) are **the only nondeterministic external calls the skill makes** — they're isolated to artifact-emission, not to the classification logic (helpers.py). Re-running the audit on unchanged repo state still produces byte-identical classification output; the artifacts themselves carry timestamps in their branch names and bodies and are not expected to be byte-identical across runs.

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
