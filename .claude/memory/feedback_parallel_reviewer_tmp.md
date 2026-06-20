---
name: feedback_parallel_reviewer_tmp
description: Parallel reviewer agents writing to the same /tmp/review.md path overwrite each other; one reviewer ends up posting the other's body under their own identity, breaking the validate_pr_review distinct-Requestor gate
type: feedback
originSessionId: 52b75b4f-2d1e-4024-b6db-e384bc5f8904
---
When two reviewer-class agents are spawned in parallel on the same PR and the brief specifies `--body-file /tmp/review.md`, both agents write to the SAME path in a shared filesystem. The later writer overwrites the earlier writer's draft, so whichever agent posts second (or posts after a race-loss) ends up sending the OTHER reviewer's body under their own GitHub identity. Result: two comments with the same `Requestor:` line (both Santiago, or both Aino) → `validate_pr_review` hook counts 1 distinct Requestor, not 2 → 2-reviewer gate fails.

**Why:** Reviewer briefs that hardcode `/tmp/review.md` predate the parallel-spawn pattern. Both agents share the host filesystem; `/tmp` is not agent-scoped. P3W9 PR #382 dual-reviewer (Aino-382 + Santiago-382) instance 2026-05-11: Aino's draft was clobbered by Santiago's before posting; Aino posted Santiago's body verbatim under `user.login=parametrization` (the shared GitHub identity layer made it visually obvious only on `Requestor:` line read-back). Fixed in-place via PATCH per `verdict_amendment_edit_not_append` — comment URL preserved.

**How to apply:**
- When acting as a reviewer in a parallel-spawn scenario, write the verdict body to a UNIQUE filename: `/tmp/<reviewer-name>_review_<PR#>.md` (e.g., `/tmp/aino_review_382.md`), NOT the brief's default `/tmp/review.md`.
- ALWAYS read-back the posted comment immediately after `gh pr comment` and verify the `Requestor:` line matches YOUR identity, not the other reviewer's. The 4-literal-string verification in the brief catches this if you check the literals BEFORE assuming success.
- Recovery: if you discover post-hoc that you posted the wrong body, edit in place via `gh api -X PATCH .../issues/comments/<id> --input <json>` where the JSON is built with `python3 -c "import json; print(json.dumps({'body': open('file').read()}))"`. Do NOT post a new comment — the hook counts the most recent verdict per author and a corrected new comment leaves the bad one behind.
- Charter follow-up worth proposing in retro: brief template should specify per-reviewer filename, OR validate_pr_review hook should warn on identical bodies across distinct GitHub-identity authors as a likely collision signal.
