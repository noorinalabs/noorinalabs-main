---
name: feedback_brief_author_verify_roster_surname
description: "When composing a spawn brief that names a teammate, the surname MUST come from reading the roster card content — not inferred from prior conversation context or fabricated from the filename slug (which only carries firstname)"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 77e35de5-3b28-48a1-92f6-f413bc8debac
---

When composing a spawn brief that names a teammate (e.g., "You are <FirstName> <LastName>"), the orchestrator MUST verify the surname by READING the roster card content (`.md` file body), not by:

1. **Inferring from filename slug**: roster cards are named `<role>_<firstname>.md` (e.g., `observability_engineer_nurul.md`, `manager_bereket.md`) — the FILENAME only carries the firstname. The surname is in the file's `Name:` line in the body.
2. **Recalling from memory or prior conversation**: agent names change, get hired/fired, or new teammates get added. Memory snapshots go stale.
3. **Fabricating from a plausible-sounding combination**: if you don't know the surname, you don't know the surname. Don't guess.

**Why:** Hook 5 (validate_commit_identity) validates the agent's git-commit identity against their roster card's `Name:` field. A mismatch (`Nurul Hassan` in commit identity vs. `Nurul Hakim` in roster) causes Hook 5 hard-reject of every commit. The agent then either:
- Stops and escalates (correct behavior per [[feedback_investigate_before_implement]]) — costs a round-trip
- Fabricates a "Nurul Hassan" roster card to make Hook 5 happy (wrong; creates a phantom teammate)
- Commits with the wrong identity and lies about Hook 5 — worst case

**How to apply** (orchestrator/brief-author side):

Before naming any teammate in a spawn brief, run a Read or `gh api .../contents/.../<file>?ref=main` against the actual roster card and extract the surname from the `Name:` line. The verification step is one tool call; the alternative is a 10-minute round-trip when the agent hits Hook 5.

**Companion to** [[feedback_pre_spawn_verify_file_exists]] — that memory covered "verify file existence at HEAD before saying 'edit this file'." This memory extends the same discipline to "verify person-identity at HEAD before naming them in a brief." The same root cause (orchestrator working from inferred/cached state instead of HEAD-current state) creates the same class of stale-brief bug.

**P3W11 deploy#88 (2026-05-19):** I composed a spawn brief for "Nurul Hassan, Observability Engineer" based on having read `ls noorinalabs-deploy/.claude/team/roster/` (which showed `observability_engineer_nurul.md`) but never opening the card. I fabricated "Hassan" from nowhere. Nurul (actually Hakim) caught the mismatch via Hook 5 awareness + pre-spawn-card-read, stopped before `git worktree add`, and escalated cleanly. Cost: one extra round-trip vs. zero if I had Read'd the card at brief-compose time. Charter-promotion candidate for W11 retro.
