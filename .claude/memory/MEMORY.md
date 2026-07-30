# Memory Index (two-tier — #1016)

<!-- TIER 1 — this file is the always-injected table of contents (~400t),
     imported by CLAUDE.md via `@.claude/memory/MEMORY.md` (the cache-prefix
     anchor — do NOT rename or move it). Per-note one-liners live in
     section_<slug>.md and load ON DEMAND (session-start Step 2.5). Keep THIS
     file to the ToC table below; do NOT paste note one-liners back here.
     Load a section:  Read .claude/memory/section_<slug>.md

     If the auto-memory writer appends new `- [ ]` one-liners below the table,
     fold each into its section_<slug>.md and bump the count here (re-tier).
     Never delete a note — only relocate it. -->

| Section | Notes | Detail (load on demand) |
|---|---|---|
| User & owner directives — Who the owner is + standing owner policy calls (correctness over expediency, IaC, full CI parity, stg→prod, MVP autonomy, brand). | 7 | [section_user_owner_directives.md](section_user_owner_directives.md) |
| Review / PR / merge mechanics — PR-review verdict format, reviewer rules, CI-readiness, merge ordering & wave-branch merge mechanics. | 17 | [section_review_pr_merge.md](section_review_pr_merge.md) |
| Spawn / delegation / agent coordination — Spawning implementers: brief protocol, child-repo & worktree rules, agent coordination and the shared task system. | 19 | [section_spawn_delegation.md](section_spawn_delegation.md) |
| Wave / issue / enforcement process — Wave & issue planning, TD intake, enforcement hierarchy, issue relocation and PR-number hygiene. | 6 | [section_wave_process.md](section_wave_process.md) |
| CI / tooling / lint / gh-cli — CI gates, linters (ruff/actionlint/cspell), gh-cli gotchas, commit-identity and zsh/git tooling traps. | 22 | [section_ci_tooling.md](section_ci_tooling.md) |
| Verification discipline — Verify-before-claim: run the instrument, full-read state, mocks mask prod, refresh before a status claim, re-verify stale trees. | 17 | [section_verification_discipline.md](section_verification_discipline.md) |
| Project state — Live project state: narrator cutover, Phase 9 data quality, ontology, backup/restore, deploys. | 12 | [section_project_state.md](section_project_state.md) |
| Reference — Durable reference facts: cypher-shell / graph-ops, B2 pipeline keys, SSH topology. | 3 | [section_reference.md](section_reference.md) |

- [Session handoff](session_handoff.md) — read this first to resume; auto-generated each session, gitignored/machine-local.
