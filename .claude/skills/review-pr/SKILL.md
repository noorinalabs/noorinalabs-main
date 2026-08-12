---
name: review-pr
description: Review a PR using charter format
args: PR number
---

Review a pull request following the team charter.

## Instructions
1. Fetch PR diff: `gh pr diff {number}`
2. Check CI status: `gh pr checks {number}` — report if failing
3. Query the review-state disclosure BEFORE posting a verdict:
   `PYTHONPATH=.claude/lib python3 .claude/lib/pr_review_state.py {number} [--repo OWNER/NAME]`
   — this replays the merge gate's own logic ahead of the merge decision, the
   only point where its NEAR-WINDOW disclosure (#1272) reaches a human before
   the outcome is fixed (the gate's own `check()` advisory fires only on the
   allow path, i.e. after the merge already happened — #1424). If the report
   names a NEAR-WINDOW verdict, a counted approval may have been cast against
   the PREVIOUS head; confirm with that reviewer that they read the head SHA
   the report names before relying on their verdict.
4. Review for: correctness, error handling, test coverage, ruff/mypy compliance
5. Post review comment using charter format (Requestor = PR author, Requestee = reviewer):
   ```
   Requestor: {PR author from charter — the person who requested the review}
   Requestee: {your name — the reviewer doing the review}
   RequestOrReplied: Request

   **Review: {LGTM or issues}**
   Must-fix: {list or "None"}
   Tech-debt: {list or "None"}
   ```
6. For each tech-debt item, create GitHub Issue (label: tech-debt + next phase + author)
7. Report: findings, CI status, merge readiness (name any NEAR-WINDOW verdict
   from step 3 and whether it was confirmed)
