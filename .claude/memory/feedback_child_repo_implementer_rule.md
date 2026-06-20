---
name: feedback_child_repo_implementer_rule
description: Implementers for child-repo work come from that child's own roster (not parent / not sibling-repo); orchestrator MUST verify roster membership at spawn-brief authoring time
type: feedback
originSessionId: 33831276-0bd2-46e7-8ddd-345abb927046
promotion_target: charter
promotion_threshold:
  retro_citations: 3
status: superseded
superseded_by: charter:agents.md § Child-Repo Implementer Rule + Spawn-Brief Verification
superseded_at: 2026-05-06
---
**Additive clarification (2026-05-16):** see also `agents.md § Parent-Orchestrator Implementer Declarations Are Advisory` (P3W10 retro proposal #4, PR #444) — codifies that parent-orchestrator per-issue declarations for child repos are advisory; child manager is canonical authority.

When spawning implementers for a PR or feature in a child repo (`noorinalabs-isnad-graph`, `noorinalabs-user-service`, `noorinalabs-deploy`, `noorinalabs-design-system`, `noorinalabs-data-acquisition`, `noorinalabs-isnad-ingest-platform`, `noorinalabs-landing-page`), pick the agent from **that child repo's** team roster (`<child>/.claude/team/roster/` and `<child>/.claude/team/roster.json`) — NOT from the parent's org-level coordination team and NOT from a sibling repo's roster.

**Why:** Hook 5 (`validate_commit_identity`) scans the working repo's `roster.json` and BLOCKS commits whose `user.name` isn't a roster member. Per CLAUDE.md § Team Workflow + memory `feedback_enforcement_hierarchy.md` (hook > skill > charter), the hook is the binding source of truth. Each child repo has its own simulated team with its own role fit; cross-roster authorship is a category error the hook catches.

**How to apply (orchestrator-side spawn-brief checklist):**

Before authoring an implementer spawn brief for a child-repo issue:

1. **Determine working repo for the change**: read the issue body. Note that issue location ≠ working repo (e.g., `noorinalabs-deploy#242` issue body says the changes go in `noorinalabs-landing-page`). The repo that hosts the FILES the implementer will edit is the working repo.
2. **Read that repo's roster**: `cat <working-repo>/.claude/team/roster.json` or list `<working-repo>/.claude/team/roster/`.
3. **Pick a roster member with role fit** for the change class (frontend Dockerfile → frontend engineer; CI workflow → devops/platform engineer; security/CVE → security engineer; observability config → observability engineer; etc.).
4. **In the spawn brief, set the implementer's identity to that roster member's `user.name` + `user.email`**.
5. **Reviewer assignment is a separate decision**: cross-team reviewer is OK (e.g., parent / sibling-team reviewer reading a child-repo PR). Don't conflate REVIEWER class with IMPLEMENTER class — `feedback_role_class_specific_boundaries.md` covers this distinction.

**Per-repo implementer pools (verify at spawn time — these snapshots may drift):**

- `noorinalabs-deploy`: Lucas Ferreira, Aisha Idrissi, Bereket Tadesse, Weronika Zielinska, Nino Kavtaradze, others (deploy roster)
- `noorinalabs-isnad-graph`: Idris Yusuf, Linh Pham, Anya Kowalczyk, Mateo Salazar, etc.
- `noorinalabs-user-service`: Mateo Salazar, Anya Kowalczyk, etc.
- `noorinalabs-landing-page`: Anika Diop-Sarr, Cédric Novák, **Kofi Mensah-Williams** (frontend), Marcia Vasquez-Paredes (lead), Nazia Rahman (QA)
- `noorinalabs-main` (parent): Wanjiku Mwangi (TPM), Aino Virtanen (Standards), Santiago Ferreira (Release Coordinator), Nadia Khoury (Program Director)
- `noorinalabs-design-system`, `noorinalabs-data-acquisition`, `noorinalabs-isnad-ingest-platform`: per-repo rosters

**Exceptions:**

- User explicitly directs otherwise in a given session ("have Lucas do the landing-page work" overrides). Hook would still block; user would need to register the agent in the target roster first or accept the block.
- Child repo has NO `.claude/team/` defined yet — check recent git history for de-facto implementer (`git log --format='%an' -- <path>`) and match, or ask user before defaulting.

**Failure modes seen and what blocked them:**

| Date | Surface | What I did wrong | What blocked it |
|---|---|---|---|
| 2026-04-22 | child-repo#139 prereqs | Deferred-under-misread of user intent | Owner correction in next turn |
| 2026-05-03 | P3W3 deploy#242 spawn brief | Spawned Lucas Ferreira (deploy roster) for landing-page work; conflated reviewer-class permission with implementer-class | Hook 5 blocked Lucas-242's first commit; Lucas-242 surfaced charter Pattern B catch (verify-vs-artifact: roster.json) and recommended Kofi from landing-page roster |

**Origin:** Clarified 2026-04-22 after #112-b. Strengthened 2026-05-03 after P3W3 #242 spawn-brief error — third orchestration mistake of that wave, all caught by implementer-class state-claim discipline. Spawn-brief checklist added.
