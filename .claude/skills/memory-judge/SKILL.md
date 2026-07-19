---
name: memory-judge
description: Read-only staleness judge for the in-repo project memory store — flags notes whose cited files/symbols/flags no longer resolve against the repo, for human-approved deletion
args: (none — operates on this repo's `.claude/memory/` store and greps this repo)
---

You are a read-only **staleness judge** for the project memory store
(`.claude/memory/*.md`, version-controlled in-repo — see CLAUDE.md § Project
Memory). Your job is to flag memory notes whose factual claims no longer hold
against the current codebase — **never** to delete anything yourself.

## Why this exists

Memory notes are point-in-time observations, not live state. A note that cites
a file, function, or flag that has since been renamed, moved, or deleted is
worse than no note — it actively misdirects. The `memory_budget.py --staleness`
sweep already run at `/wave-retro` Step 7.8 catches the **size/age** axis (an
oversized topic file, or one whose last commit is old); it says nothing about
whether a note's *content* still resolves. This skill is the complementary
**content-staleness** half: budget = size, judge = stale content. It finds
candidates; a human decides.

## Instructions

### 1. Resolve the memory directory

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
MEM_DIR="$REPO_ROOT/.claude/memory"
```

The store is in-repo and git-tracked, so it can be `git grep`-ed directly — no
external path resolution is needed (unlike an out-of-repo user-space store). If
`$MEM_DIR` is absent, **stop and report**.

### 2. Select notes due for review

A note is **due** if either is true:

- it has no `last_verified` frontmatter field at all, or
- `last_verified` is older than **60 days** from today.

List candidates (mirror the budget sweep's skip set — the index, the gitignored
per-session handoff, and the cold-archive subtree are not topic notes):

```bash
cd "$MEM_DIR" && for f in *.md; do
  case "$f" in MEMORY.md|session_handoff.md) continue ;; esac
  lv=$(awk -F': ' '/^last_verified:/{print $2; exit}' "$f")
  echo "$f|${lv:-NONE}"
done
```

Compare each date to today; anything `NONE` or >60 days old is in scope. Skip
`.claude/memory/archive/**` (the cold tier is deliberately parked, not live).
Skip notes already marked `superseded_by:` — those are already flagged and
awaiting a prune decision, not a fresh judgment.

### 3. Extract ground-truth references per note

For each due note, pull every backtick-quoted path/symbol/flag reference
(`` `app/module.py` ``, `` `some_function` ``, `` `--flag-name` ``, hook script
names, env var names). Prefer references the note treats as a durable fact ("X
lives at Y", "the hook is named Z") over prose mentioning an issue number or a
person's name — issue numbers and names are not verifiable via `git grep` and
are not the point.

### 4. Verify each reference against the codebase (ground truth)

From the repo root (the same repo the memory store lives in):

```bash
git -C "$REPO_ROOT" grep -n -- '<symbol_or_path>'
```

- A file path: check it exists (`git -C "$REPO_ROOT" ls-files -- '<path>'`)
  rather than grepping its contents.
- A function/class/constant name: `git grep -n '<name>'` across the repo; zero
  hits means it no longer exists under that name (renamed or removed).
- A flag/CLI option: `git grep -n -- '<flag>'`.

A single stale reference does not necessarily invalidate a whole note — some
notes are historical narrative (deliberately describing something now fixed or
superseded) rather than "this is how it works today." Read the note's own
framing before concluding it is dead weight.

### 5. Report findings — do not act

For each due note, report one of:

- **Still-current** — all references resolve; bump candidate for `last_verified`
  update (a human/implementer applies the frontmatter edit; this skill does not
  write to the store).
- **Partially-stale** — some references no longer resolve; quote the note's
  claim and the `git grep` result showing it is gone. Suggest either an edit (if
  the note is still worth keeping with a correction) or a `superseded_by`
  pointer if a newer note already covers it.
- **Fully-stale** — the note's central claim no longer resolves anywhere and no
  newer note supersedes it. Suggest deletion.

Present the full list to the orchestrator/user. **Deletes are PR-gated: they
require an explicit human-approved diff** (a commit the owner reviews), the same
way `close-stale-issues` never closes an issue without confirmation. Never
delete, edit, or commit anything in the memory directory yourself — this skill
only reads and reports.

## Fold-in point

Run this as a step in `/wave-retro` (Step 7.9, immediately after the Step 7.8
`memory_budget.py --staleness` size/age sweep — the two are complementary:
budget flags oversized/old files, the judge flags stale *content*) or as a
standalone periodic invocation. Either way, always with a human reviewing the
output before any delete/edit lands.
