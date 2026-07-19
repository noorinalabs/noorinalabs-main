# Memory — Review / PR / merge mechanics

<!-- Tier 2 (loads on demand — see session-start Step 2.5). One line per
     memory; full detail in each linked note file in THIS directory.
     Do NOT auto-inject this file at session start (that re-adds the whole
     always-loaded index the #1016 two-tier split removed). -->

- [PR-review verdict format (consolidated)](feedback_pr_review_verdict_format.md) — hooks fail OPEN on near-misses. Surfaces: §1 trailer block after LAST sole `---`, field is RequestOrReplied (NEVER Verdict), bold/bare parse; §2 Approved-only counting (Reply=0; check issue comments not .reviews); §3 Requestor=YOU in space-form roster name (not dotted/author/paired); §4 TechDebt literal line, every verdict comment, file-findings-first; §5 amendment=EDIT via REST PATCH, never append; §6 prose Field:Value ban (validate_review_comment_format whole-body match); §7 count by importing the hook, approval predating head is not an approval; §8 spawn-brief template obligations.
- [Wave branch: every-wave merge + retain](feedback_wave_branch_merge_retain.md) — each wave merges to main at its /wave-wrapup; phase/wave branches RETAINED (--merge).
- [Consumer wave-merge ordering](feedback_consumer_wave_merge_ordering.md) — consumer repo's wave→main whose CI resolves a tool from producer's base branch must merge AFTER producer's; else tool-dep check false-reds. P6W17 #1130.
- [Security guard inline, not followup](feedback_security_guard_inline_not_followup.md) — Changes-Requested when threat model needs a runtime guard; followup issue is tracking, not a fix. #77.
- [Runtime gate scoping](feedback_runtime_gate_scoping.md) — operational gates needing prod-only state are NOT PR acceptance; deliver unit-mechanic correctness.
- [Review against artifact, not PR-body framing](feedback_review_against_artifact.md) — read diff/code at PR head via gh api contents, not PR body / commit msgs / line numbers.
- [Reviewer-correction-vs-merge race](feedback_reviewer_correction_vs_merge_race.md) — pause merge until reviewer's in-flight correction lands AND updated_at re-verified.
- [Parallel reviewer /tmp filename collision](feedback_parallel_reviewer_tmp.md) — parallel reviewers writing /tmp/review.md clobber each other; use /tmp/<reviewer>_<PR#>.md.
- [Consumer against in-flight upstream](feedback_consumer_against_in_flight_upstream.md) — reviewing a consumer PR on unmerged upstream needs dual-axis co-verify (read upstream source).
- [Reviewer must not branch-switch parent](feedback_reviewer_no_branch_switch.md) — reviewers read PR code via gh api contents?ref=<sha>; MUST NOT git checkout in parent.
- [Dep-resolution change invalidates unchanged steps](feedback_dep_resolution_invalidates.md) — dep-resolution PR: reviewers read FULL workflow at HEAD, not diff. #924.
- [statusCheckRollup before "CI clean"](feedback_statuscheckrollup_ci_clean.md) — local pass ≠ CI pass; run gh pr view --json statusCheckRollup before "ready" claims. EMPTY rollup = hard not-ready (main#802); oracle .claude/lib/pr_ci_state.py.
- [Batch-loop merge evades PR-review hook](feedback_batch_loop_merge_evades.md) — gh pr merge $pr in a shell loop fails open; standalone literal PR# is caught.
- [Stacked PR orphaned by base-branch delete](feedback_stacked_pr_base_delete_orphan.md) — PR-B stacked on PR-A's feature branch is auto-CLOSED (no reopen/retarget) when A merges w/ --delete-branch; retarget B to the wave branch first, or open a fresh superseding PR. P9W25 #457→#459.
- [Deployable-merge verification](feedback_deployable_merge_verification.md) — wave→main/push-to-main merge: verify post-merge-only workflows (publish/Trivy) via verify_deployable_merge.py; green PR ≠ proof. wave-wrapup Step 11.5a. main#864.
- [Wave-branch merge: --merge not --squash](feedback_wave_branch_merge_not_squash.md) — squash collapses persona authors to bare parametrization → commit-author gate red on wave→main; child structural staleness only gates PRs to main. P7W19 #898/#222.
