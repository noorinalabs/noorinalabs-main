---
name: feedback_pre_spawn_brief_verified_at_head
description: Manager-class pre-spawn discipline — enumerate the surface from the wave-branch HEAD and rule on each named caveat as applicable/non-applicable BEFORE sending the implementer brief
type: feedback
originSessionId: 3d519c58-11df-4e60-ba09-74c7024fc9f1
---
Before sending an implementer-spawn brief for a multi-call-site mechanical change (action upgrades, dependency bumps, API rewrites), the manager MUST:

1. **Enumerate the full surface from the wave-branch HEAD** (not local main, not the issue body's audit table — both can be stale). Use `grep -rn` / `gh api contents/...?ref=<wave_branch>` to produce a per-call-site table: file, line, current version, target version.
2. **For every named caveat in the parent audit / charter / kickoff** (e.g., upload-artifact@v4 same-name failure, breaking-change docs, deprecated-flag warnings), explicitly rule applicable vs. non-applicable for THIS repo's surface. Don't pass the caveat through as "be careful" — verify and resolve it.
3. **Include both in the spawn brief body** and require the implementer's PR body to note that verification was done (so reviewers see the caveat addressed, not skipped).

**Why:** team-lead flagged this as the bar after two independent P3W8 instances:
- Marcia / landing-page#88 — verified 6 call sites at wave-branch HEAD, ruled `upload-artifact` same-name caveat non-applicable (single call site `playwright-report` in single job)
- Bereket / deploy#280 — 20-site enumeration + consumer-side `promote.yml` REST-not-download-action confirmation

Two role-class-distinct instances in a single wave → load-bearing. Validated against `feedback_origin_over_local_for_still_has_claims.md` (origin > local for "still has X" claims) — same primitive applied at the spawn-brief layer instead of the review layer.

**How to apply:**
- Whenever a manager prepares an implementer brief for a mechanical multi-site change driven by a parent audit/meta-issue
- Skip if the surface is single-site obvious (e.g., a 1-line config flip) — the discipline scales with surface size and caveat count
- Implementer's PR body should mirror the manager's verification table + caveat ruling so reviewers can audit the chain

**Promotion target:** if a third role-class instance lands (e.g., a frontend-engineer-class manager doing the same on a different wave), promote to charter `pull-requests.md` § Pre-Spawn Manager Briefing.
