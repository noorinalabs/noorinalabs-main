---
name: feedback_commit_author_gate_exclude_merges
description: Any landed-commit author/identity gate over a PR range MUST use git log --no-merges; GitHub authors merge commits as the bare principal by design
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 080813cd-f3b8-434d-974c-badf58620c96
---

Any CI gate that enumerates a PR's commit authors over `base..head` (e.g. the main#627 commit-identity gate, `.claude/lib/verify_commit_identity.py`) MUST pass `git log --no-merges`. Otherwise it false-blocks legitimate PRs.

**Why:** under `allow_merge_commit: true`, every GitHub-side merge commit is authored by the bare gh principal `parametrization` BY GITHUB'S DESIGN — the merger has no roster identity to stamp. Counting merge commits flags every wave-branch→main PR (the every-wave-merges-to-main flow, [[feedback_wave_branch_merge_retain]]), every per-issue merge into a wave branch, and any feature PR updated via "Update with merge commit". Santiago reproduced it against wave-1→main PR #622 (3 `parametrization` merge commits in range). Caught at PR #630 review before merge.

**How to apply:** use `git log --no-merges base..head`. This does NOT reopen the security gap — the introduced CONTENT always lives in non-merge commits (a merge commit's tree is the only thing GitHub controls), so a content commit authored as the bare principal (the deploy#409 evasion the gate exists to catch) is still flagged. Regression test must assert BOTH: a principal-authored merge commit in range is excluded AND a principal-authored non-merge commit in the same range is still caught. Build the merge shape in tests with `git merge --no-ff` (forces a real 2-parent merge).

**Related latent issue (Wanjiku, #630):** `commit-identity.yml` does a single-repo checkout, so `load_known_names`' sibling-roster merge is INERT in CI — the effective CI name set is the parent roster alone, omitting all 11 ingest-platform personas. A future ingest-authored main PR would be false-blocked. Fix = fold ingest personas into the parent roster, or materialize sibling rosters in the workflow. **Filed as main#634, ASSIGNED TO AINO (gate author) as a fast-follow / next-wave item — NOT folded into PR #630.** Both fix options captured in the issue. Cf. [[feedback_child_repo_implementer_rule]].
