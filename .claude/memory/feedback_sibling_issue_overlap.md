---
name: feedback_sibling_issue_overlap
description: "When PR for issue #A generalizes its scope to also satisfy sibling/overlapping issue #B, GH `Closes #A` + auto-close hooks do NOT cross-close #B. Pre-spawn audit MUST check for overlapping-already-resolved sibling issues at HEAD before composing implementer briefs"
metadata:
  node_type: memory
  type: feedback
  originSessionId: 77e35de5-3b28-48a1-92f6-f413bc8debac
---

When a PR (#X) is filed against issue #A but the implementation scope generalizes to also substantively resolve a sibling/overlapping issue #B, GitHub's `Closes #A` mechanism and our auto-close-on-wave-merge hooks **do not** cross-close #B. #B remains open even though its acceptance criteria are satisfied at HEAD.

**Why:** GH only closes issues explicitly named in PR body keywords (Closes / Fixes / Resolves), and our auto-close hooks key off branch-merge events to specific named-issue close. Neither has any mechanism to detect "this PR's diff substantively addresses the acceptance criteria of issue #B even though #B isn't named." So #B stays open as a phantom-open backlog item.

**How to apply (orchestrator-side, pre-spawn):**

Before composing an implementer brief for an issue #N, do a 2-minute scope-overlap audit at HEAD:

1. Grep the touched file surface (the one your brief assumes will be edited) for keywords from #N's acceptance criteria.
2. Check if any of those keywords already appear at HEAD: `gh api 'repos/.../contents/<path>?ref=<wave-branch>' --jq '.content' | base64 -d | grep -i '<keyword>'`
3. If yes, look at git log for that file to find the PR that introduced the keyword. Check if that PR's body or title cites #N or a closely-related sibling.
4. If the surface already exists and seems to address #N's acceptance criteria, **STOP the spawn** — instead, file a "verify and close #N" task with the per-criterion mapping, and route that to a reviewer-class agent (not implementer). They confirm and close.

**Sibling pattern:** [[feedback_gh_cli_gotchas]] is about default-branch-only `Closes #N` keyword behavior (wave-branch merges don't fire it). This memory is about **sibling-scope-overlap** — even when `Closes #A` fires for the named issue, sibling issue #B silently stays open.

**Detection at retro time:**
- Run `gh issue list --label p3-wave-N --state open --json number,title,createdAt` against each child repo + main
- For each open W-N issue, run `gh search prs --repo <repo> "<issue-title-keyword>" --state merged --json number,title,closedAt` — if any merged PR titled with overlap-keywords exists, audit the surface.
- This catches the phantom-open population that "issue count" metrics over-report.

**P3W11 deploy#200 (2026-05-19):** I spawned Lucas Ferreira to implement deploy#200 (durable break-glass audit trail for `skip_stg_verify`). He hard-stopped — found that deploy#251 / PR #261 (merged 2026-05-04) had shipped a strict superset: `validate-break-glass-reason` job + `.github/actions/break-glass-audit/` composite + Prometheus textfile-collector metric, covering all three break-glass inputs (`skip_stg_verify`, `skip_alembic_gate`, `allow_stg_tags`), not just #200's `skip_stg_verify`. Composite even posts to a `break-glass-audit-log` labeled tracking issue with actor / run URL / source_sha / reason / timestamp — every acceptance criterion satisfied. #251 was titled "alert/audit on `skip_alembic_gate / allow_stg_tags`" so cross-close didn't fire on PR #261's `Closes #251`. #200 sat phantom-open for 2 weeks. Cost: one spawn round-trip (Lucas's pre-flight + hard-stop) where the orchestrator pre-audit should have caught it.

**Two instances this session** of stale-brief implementer hard-stop catches: (1) kofi-lp on deploy#242 step 1 (already-shipped via landing-page PR #75) — surface-existence at HEAD; (2) Lucas-200 on deploy#200 (already-shipped via #251/#261) — sibling-issue-overlap. Sibling to [[feedback_investigate_before_implement]] but moves the discipline UPSTREAM to the orchestrator's pre-spawn audit. Charter-promotion candidate for W11 retro: "Pre-spawn scope-overlap audit" as a hard step in the orchestrator spawn discipline checklist.
