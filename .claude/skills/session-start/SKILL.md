---
name: session-start
description: "MANDATORY first action in every session — runs full startup protocol (worktree, team, handoff, ontology, annunaki, wave, charter)"
---

# Session Start Protocol

**This skill MUST be invoked as the FIRST action in every new session.** Do not respond to the user's message, do not read files, do not run any other tool — invoke `/session-start` first. The user's actual request is handled AFTER this completes.

> Note: all repo paths in bash blocks below are rooted at `$REPO_ROOT` to avoid cwd drift when the skill is invoked from a worktree or child-repo subdirectory (#149).

## Instructions

Execute all 7 steps below. Steps that are independent of each other SHOULD run in parallel. Present results in a single concise status table at the end.

### Step 0 — Worktree cleanup

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
git -C "$REPO_ROOT" worktree prune
git -C "$REPO_ROOT" worktree list
```

Verify only the main repo root is listed. Remove any stale worktrees.

### Step 1 — Team cleanup

Stale team state from prior sessions causes "does not exist" / "already leading" errors. Always start fresh:

1. Run `TeamDelete` (will succeed even if no team exists)
2. Run `TeamCreate` with `team_name: "noorinalabs"` and `description: "Org-level coordination team for noorinalabs-main"`

Never try to reuse an existing team. Never skip this step.

> **Single-leader constraint:** This `TeamCreate` call establishes THE session team. Additional `TeamCreate` calls in this session will fail with "Already leading team." All managers and implementers spawned during the session — regardless of which repo they work on — join this single `noorinalabs` team. See charter `agents.md` § Single-Leader Constraint for the delegation pattern (team lead is sole `Agent`-tool caller; managers `SendMessage` the team lead to request implementer spawns).

### Step 2 — Handoff check

Read the session handoff file from project memory:

```
Read: ~/.claude/projects/-home-parameterization-code-noorinalabs-main/memory/session_handoff.md
```

If it exists, extract:
- What was done last session
- What's next
- Current branch, open PRs, open issues
- Any user notes

Summarize in 2-3 sentences. If the file doesn't exist, note "No handoff from previous session."

### Step 3 — Ontology rebuild

Run `/ontology-rebuild` to resolve any dirty files from the previous session.

- If 0 dirty files, report "Ontology is current" and move on
- If dirty files exist, process them and commit the result
- This ensures the ontology reflects all changes before any new work begins

### Step 4 — Annunaki error check

Run `/annunaki` to check the error monitor.

- Report: hook active/inactive, error count, any new errors since last session
- If 5+ unprocessed errors, flag for `/annunaki-attack`
- If 0 errors or all are resolved PreToolUse blocks, report "No action needed"

### Step 5 — Wave/phase orientation

Read the current project state:

```bash
cat "$REPO_ROOT/cross-repo-status.json"
gh issue list --repo noorinalabs/noorinalabs-main --state open --limit 10 --json number,title,labels
```

Report:
- Active wave and phase
- Whether `cross-repo-status.json` is stale (check `last_updated` fields)
- Open issue count and any blockers
- Open PRs across repos

If the report surfaces unexpected gaps between board view and open-issue counts (e.g., wave-labeled issues missing from project 2, or Wave-field values out of sync with `p{N}-wave-{M}` labels), invoke `/board-audit` to detect and (with confirmation) repair the drift. Per main#199, labels are canonical and the project's Wave field is a derived projection synced by `/board-audit`.

### Step 6 — Charter freshness check

Read the tail of the feedback log:

```bash
tail -40 "$REPO_ROOT/.claude/team/feedback_log.md"
```

Check for:
- Unapplied retro proposals (action items without corresponding changes)
- New hooks or skills introduced since the last charter update
- Any pending fire/hire actions

Report findings or "Charter is current."

## Output format

After all steps complete, present a single status block:

```
**Session Start — Complete**

| Step | Status |
|------|--------|
| 0. Worktree | {clean / N stale removed} |
| 1. Team | {created fresh / error} |
| 2. Handoff | {summary} |
| 3. Ontology | {N dirty resolved / current} |
| 4. Annunaki | {N errors, action needed? / clear} |
| 5. Wave | {active wave, stale?, issues} |
| 6. Charter | {current / proposals pending} |

{Then address the user's actual message/request}
```

## What this skill does NOT do

- It does not begin any implementation work
- It does not create issues or PRs
- It does not modify the charter or team roster
- It only establishes situational awareness so the session starts informed
