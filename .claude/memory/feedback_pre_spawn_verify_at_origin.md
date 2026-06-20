---
name: feedback_pre_spawn_verify_at_origin
description: Manager/orchestrator-class discipline — verify audit-deliverable issue premises against origin head_sha BEFORE spawning an implementer; if premises fail, scope-block and re-scope with TPM rather than spawn-and-discover.
type: feedback
originSessionId: 3d519c58-11df-4e60-ba09-74c7024fc9f1
---
Before spawning an implementer for any audit-deliverable issue (issue body framed as "remove X / sync Y / augment Z / clean up dead-code N"), the manager runs `gh api repos/<owner>/<repo>/git/trees/<head_sha>?recursive=1` (or `gh api .../contents/<path>?ref=<head_sha>`) to verify the deliverable's premises hold at the wave branch head. If premises fail (target file/path/state doesn't exist as the issue body assumes), scope-block with a comment on the issue + bounce to TPM/scope owner for re-scope. Do NOT spawn the implementer to "discover the gap."

**Why:** P3W8 surfaced three independent instances of the same shape — issue bodies / audit deliverables written against tree state that didn't survive migration, prior wave, or manual cleanup:

- data-acquisition#43+#44 (Dilara) — body said "remove dead-code child hook copies" / "augment stale child copy"; origin verification at head returned 0 entries under `.claude/hooks/`. Re-scoped to ADR + parent-side fixture.
- isnad-graph hook surface (Anya) — 4 of 5 hook files 404 at origin; 4 W8 issues scope-blocked pre-spawn instead of consuming implementer time.
- deploy#276 (Bereket) — issue already-resolved at origin; close-as-resolved instead of re-fix.

The reviewer-class memories `feedback_origin_over_local_for_still_has_claims.md` and `feedback_review_against_artifact_not_framing.md` cover post-PR verification; the manager-class pre-spawn version is the gap. Maeve's pre-spawn read of parent#309's existing audit table to unblock #46 is the positive expression of the same discipline (catch the *unblock* signal, not just the block).

**How to apply:**
- Trigger: spawning an implementer for any issue whose acceptance criteria reference a specific file/path/state at origin (most "remove/sync/augment/clean up" framings, all backport audits, all dispatcher / migration follow-up tickets).
- Action: before `SendMessage team-lead` with the spawn request, run the head-sha verification command. Commit the verification (sha + command + observed result) to the spawn-request message body so reviewers can trace.
- If premises hold: proceed with spawn as planned.
- If premises fail: scope-block — comment on issue with verification evidence (sha, command, output), tag TPM/scope owner, escalate via `SendMessage` rather than spawning. Add to retro carry-forward if scope-shift required.
- If premises *over-deliver* (issue body assumes a block that's already cleared, e.g., parent audit table already populated): proceed with spawn AND note the unblock in spawn-request message — saves the implementer the same look-up.
- Hook-promotion ceiling: manager actions are message-sends, not Bash/Edit, so charter+`/wave-kickoff` skill instrumentation is the realistic enforcement tier per `feedback_enforcement_hierarchy.md`. Hook attachment point if pursued: GH-API surface (`gh issue create / edit --add-label / project item-add`).
- Cross-reference: companion to reviewer-class `feedback_origin_over_local_for_still_has_claims.md` and `feedback_review_against_artifact_not_framing.md`. Same artifact-truth principle, different lifecycle stage.
