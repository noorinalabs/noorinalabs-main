---
name: reference_closing_refs_empty_wave_prs
description: "closingIssuesReferences is empty for non-default-base (wave-branch) PRs and isn't a gh pr view --json field; parse body keywords instead"
metadata: 
  node_type: memory
  type: reference
  originSessionId: d8acc7c0-91ac-412b-b312-da38817b1614
---

GitHub's structured `closingIssuesReferences` is the wrong signal for issue↔PR
linkage on wave-branch PRs, two ways:

1. `gh pr view --json closingIssuesReferences` / `gh pr list --json
   closingIssuesReferences` → "Unknown JSON field" in the installed gh (not in
   the field list for either subcommand).
2. Even via `gh api graphql` (`repository.pullRequest.closingIssuesReferences`),
   the field is ALWAYS EMPTY when the PR's base is NOT the repo default branch.
   GitHub only registers closing references for default-branch PRs — same root
   cause as `Closes #N` not auto-closing on wave-branch merges
   ([[feedback_wave_branch_issue_close]]). Verified live: PR#700 with "Closes
   #664" in body, base=deployments/phase-5/wave-5 → graphql returned 0 nodes.

So any hook/tool deciding "which issue does this wave-branch PR close" must
parse the PR **body+title** for GitHub's closing-keyword grammar
(`(?:close[sd]?|fix(?:es|ed)?|resolve[sd]?)\b[\s:]+#(\d+)`), requiring the
keyword (not a bare `#N`) to avoid false links. This is what
`validate_wave_audit._closing_refs_in_text` does (main#664/PR#700).

Lesson reinforced ([[feedback_passing_repro_masks_bug]]):
unit tests mocking subprocess passed with the broken closingIssuesReferences
form — only a real `gh` call against a live wave-branch PR surfaced both
breakages. Verify gh-shape hooks against real gh before claiming they work.
