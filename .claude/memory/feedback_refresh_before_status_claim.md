---
name: feedback_refresh_before_status_claim
description: Agent-local snapshot of PR state goes stale across turns; refresh via gh api before any "still at 1/2 / still blocked / status is X" claim
type: feedback
originSessionId: 7a9193be-f4d0-4434-a33c-2c9493287b57
promotion_target: charter
promotion_threshold:
  retro_citations: 3
status: enforced-elsewhere
superseded_by: charter:state-claims.md § Refresh State Before Claim
---
Before stating PR status, merge state, approval counts, or CI state in a teammate message or end-of-turn summary, refresh via `gh pr view <N>` or `gh api .../pulls/<N>` for any PR mentioned. Agent-local state is a snapshot from the last turn the PR was touched; by the time the next message fires, reviewers have posted, PRs have merged, and comments have flipped headers. Stating a stale snapshot as current truth burns coordinator cycles on "actually merged 10 minutes ago" re-sync messages.

**Why:** Bereket.Tadesse flagged this twice in one session (2026-04-23): once on deploy#154 approval count (claimed "1/2 awaiting Aisha" when it had merged), once on deploy#153 reviewer-slate edit (claimed done three times when `gh pr edit` had silently no-op'd). Same class as `feedback_stale_inbox_manager.md` but applied at the implementer layer, and paired with `feedback_gh_cli_gotchas.md` on PR-body edits specifically.

**How to apply:**
- Before any teammate message summarizing PR state: `gh pr view <N> --json state,isDraft,statusCheckRollup,mergedAt,updatedAt` for each PR referenced.
- Before any "already done"/"already X" assertion: `gh api .../pulls/<N> --jq .<field> | rg <expected>` to confirm the mutation actually took.
- Before any "this PR needs X reviewer/approval/gate": re-read review comments via `gh api /repos/:o/:r/issues/<N>/comments` to count current `Approved` headers.
- **Reviewer extension (Bereket-flagged 2026-04-28, deploy#181):** before any "first reviewer" / "no prior review to align against" / "I'm the first eyeballer" claim in your own review post, refresh `gh pr view <N> --json reviews,comments` *immediately before* the `gh pr comment` call — not at the start of the diff dive. PR-comments lag inbox flush; a fresh fetch at review-start can return empty `reviews`/`comments` arrays even when a sibling reviewer's comment landed minutes earlier. Same retro lesson (W10 stale-inbox manager mode), extended from coordinator to reviewer.

Heuristic: if a PR number appears in the message being composed, it gets a refresh. Cheap (one API call), catches silent-mutation-fail (`gh pr edit` bug), timing-drift (reviewers posted between turns), AND parallel-reviewer collision (sibling review landed during your diff dive).

The symmetric discipline on the coordinator side is `feedback_stale_inbox_manager.md`; this is the implementer/reviewer equivalent.
