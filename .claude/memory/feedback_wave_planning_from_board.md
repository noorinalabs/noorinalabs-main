---
name: feedback_wave_planning_from_board
description: The full project board (project 2) is the authoritative backlog for wave scoping. Labels and meta-issue bodies are post-scoping, not pre-scoping.
type: feedback
originSessionId: 7a9193be-f4d0-4434-a33c-2c9493287b57
promotion_target: skill
promotion_threshold:
  retro_citations: 3
status: enforced-elsewhere
superseded_by: ".claude/skills/wave-scope/SKILL.md (main#196 P3W1) + /wave-kickoff Step 0 reconciled-precondition (main#273 P3W5)"
---
When planning or scoping an upcoming wave:

1. **Project board is the source of truth.** Start every wave-planning pass with `gh project item-list 2 --owner noorinalabs`. That list is the candidate pool.
2. **`p{N}-wave-{M}` labels are post-scoping tags**, not pre-scoping filters. Labels document the decisions made during scoping; they do not bound which issues could have been considered.
3. **Meta-issue bodies document declared scope** (e.g., `noorinalabs-main#141` for P2W10), but they do not replace the board audit — the meta captures the narrative, the board captures the full candidate set.

**Why:** Discovered 2026-04-23 during P2W10 execution. An audit comparing `gh issue list` across all 8 repos against the project board revealed **72 of 193 open issues (37%) were missing from the board**. Those issues were invisible to any wave-planning pass that read labels or meta-issue bodies. Planning from labels alone systematically excludes work the team forgot to triage onto the board.

**How to apply:**

- `/wave-scope` skill (issue noorinalabs-main#196): step 0 reads project board items, filters to open, deduplicates. THAT is the wave's candidate pool. The scope-pass then asks which candidates fit the wave theme.
- `/plan-phase` skill: phase decomposition reads from the project board, not from `gh issue list --label tech-debt` alone.
- **Pre-wave drift audit:** before scoping, run the audit command below to catch issues that weren't auto-added by Hook 13 (e.g., manual-UI creation, bot-created issues, cross-repo-dispatch-triggered issues):

```bash
for repo in noorinalabs-main noorinalabs-isnad-graph noorinalabs-user-service \
           noorinalabs-deploy noorinalabs-design-system noorinalabs-landing-page \
           noorinalabs-data-acquisition noorinalabs-isnad-ingest-platform; do
  gh issue list --repo "noorinalabs/$repo" --state open --limit 500 --json url --jq '.[].url'
done | sort -u > /tmp/all_open.txt

gh project item-list 2 --owner noorinalabs --format json --limit 1000 \
  --jq '.items[] | select(.content.url) | .content.url' | sort -u > /tmp/board_urls.txt

comm -23 /tmp/all_open.txt /tmp/board_urls.txt
```

Any URL printed by the final `comm` is an open issue missing from the board — add it before scoping the wave. Hook 13 (`auto_add_issue_to_board.py`) catches in-session issue creation only; externally created issues slip through and need this periodic audit.
