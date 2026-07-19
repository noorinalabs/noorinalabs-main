---
name: handoff
description: Generate a session pickup prompt — summarizes current state so the next session can resume seamlessly
args: notes
---

Generate a handoff summary for the next session. The optional `notes` argument lets the user add specific context (e.g., "was debugging the auth flow" or "next step is PR review").

> See [`.claude/team/lifecycle.md`](../../team/lifecycle.md) § Session Lifecycle for the canonical skill order and preconditions.

> Note: all repo paths in bash blocks below are rooted at `$REPO_ROOT` to avoid cwd drift when the skill is invoked from a worktree or child-repo subdirectory (#149).

## Instructions

### 1. Gather current state

Collect the following in parallel:

**Git state:**
```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
git -C "$REPO_ROOT" status
git -C "$REPO_ROOT" log --oneline -10
git -C "$REPO_ROOT" branch --show-current
```

**Open PRs across all repos:**
```bash
for repo in noorinalabs-main noorinalabs-isnad-graph noorinalabs-user-service noorinalabs-deploy noorinalabs-design-system noorinalabs-landing-page noorinalabs-data-acquisition; do
  echo "--- $repo ---"
  gh pr list --repo "noorinalabs/$repo" --state open --json number,title,author,headRefName --limit 5 2>/dev/null
done
```

**Wave/phase status:**
- Read `cross-repo-status.json` if it exists
- Check for active wave labels on open issues

**Ontology staleness:**
- Read `ontology/checksums.json` — count dirty files

**Recent issues:**
```bash
gh issue list --repo noorinalabs/noorinalabs-main --state open --limit 10 --json number,title,labels
```

### 2. Summarize the conversation

Review what was accomplished in this session:
- What tasks were completed
- What decisions were made
- What was discussed but not acted on
- Any blockers or open questions

### 3. Write the handoff

Write the handoff to **two locations** so it's available regardless of how the next session starts:

**Location 1: Project memory** (auto-loaded at session start)

Write to the project memory directory as `session_handoff.md`:

```markdown
---
name: Session handoff
description: Pickup prompt from previous session — read this first to resume work
type: project
---

## Last session: {date}

### What was done
- {bullet list of completed work}

### Decisions made
- {key decisions and their rationale}

### Current state
- **Branch:** {current branch}
- **Wave/phase:** {active wave and phase}
- **Open PRs:** {count and key PRs}
- **Ontology:** {current or N files behind}
- **Open issues:** {count, highlight any blockers}

### What's next
- {prioritized list of next steps}
- {any open questions for the user}

### User notes
{notes argument if provided, or "None"}
```

**Location 2: Console output**

Also print the full handoff summary to the conversation so the user can copy/paste it into a different session or machine if needed.

### 4. Ensure the (static) memory-index pointer exists

`MEMORY.md` carries exactly one pointer line for the handoff. It is **static** — a fixed one-liner that does NOT carry a per-session summary:
```
- [Session handoff](session_handoff.md) — read this first to resume; auto-generated each session, gitignored/machine-local.
```

**Do NOT rewrite this line with the session's summary.** The volatile per-session content belongs only in `session_handoff.md` (Location 1) and the console output (Location 2) — never in `MEMORY.md`. Rationale: `MEMORY.md` is `@import`-ed into `CLAUDE.md` and forms the always-loaded, prompt-cached context prefix; rewriting a line inside it every session invalidates that cache (write ≈ 12.5× read cost), duplicates `session_handoff.md`, and — because it is a hand-maintained mirror of a file that moves every session — reliably goes stale (#998, token-efficiency Move #6). If the static line is missing, add it once; if a previous handoff entry still carries a summary, replace it with the static form. There should only ever be one.

### 5. Confirm

Tell the user:
- The handoff is saved and will be auto-loaded in the next session on this machine
- If they're switching machines, they can paste the console output into the new session
- The handoff will be overwritten next time `/handoff` runs

## What remains manual

- The user must invoke `/handoff` before ending a session — it does not run automatically
- Cross-machine handoff requires copy/paste of the console output
