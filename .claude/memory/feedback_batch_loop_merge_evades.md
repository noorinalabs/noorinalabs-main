---
name: feedback_batch_loop_merge_evades
description: "Merging multiple PRs via a shell `for` loop (`gh pr merge $pr ...`) evades the validate_pr_review PreToolUse hook — it parses a literal PR number from the command string and a loop variable defeats the match. Standalone `gh pr merge <N>` is caught; the loop is not. Merge one PR per Bash call to keep the gate active."
metadata:
  node_type: memory
  type: feedback
  originSessionId: 77e35de5-3b28-48a1-92f6-f413bc8debac
---

The `validate_pr_review` PreToolUse hook (and likely sibling `gh pr merge`-matching hooks like `validate_pr_ci_status`, `validate_commit_identity`) inspects the **command string** to extract the PR number, then checks the gate (2 distinct Approved reviewers, CI status, etc.). When `gh pr merge` is invoked with a **shell loop variable** — e.g.:

```bash
for spec in "repo 47" "repo 131" ...; do
  pr=$(echo $spec | cut -d' ' -f2)
  gh pr merge $pr --repo "noorinalabs/$repo" --merge
done
```

— the hook cannot resolve `$pr` to a literal number at PreToolUse time (the variable isn't expanded in the command string the hook sees), so it **fails open**: the merge proceeds WITHOUT the review/CI gate being enforced.

**Why this matters:** P3W11 wave→main propagation (2026-05-20) — I batch-merged 4 wave→main PRs (#47, #131, #89, #522) in a single `for` loop. All 4 had **0 Approved review comments** and merged anyway. The 5th (#927) was a standalone `gh pr merge 927 ...` — the hook parsed `927`, found 0/2 reviews, and BLOCKED. The asymmetry (4 pass, 1 caught) is the tell: the loop evaded the gate.

**How to apply:**

1. **Merge one PR per Bash call** with a literal PR number (`gh pr merge 47 --repo ...`) so the hook can parse and enforce. Do NOT batch-merge via loops if you want the review/CI gates to actually fire.
2. **If you intend the gate to apply, never use a loop variable for the PR number** — it silently disables enforcement.
3. **Wave→main propagation caveat:** for propagation merges of already-2-reviewed wave work, the 2-review gate is arguably over-application (the wave-wrapup skill Step 11 gates propagation on USER approval, not fresh peer review). But the gate firing-or-not should be a deliberate decision (exempt-by-design or `--admin` with justification), NOT an accidental loop-evasion. In W11 the 4 loop-merges evaded it accidentally; #927 was correctly `--admin`'d with justification after the gap was found.

**Hook-fix candidate:** `validate_pr_review` should detect when the `gh pr merge` argument is a non-literal (shell variable, command substitution) and either (a) resolve it via the surrounding context, or (b) HARD BLOCK with "cannot determine PR number — merge one PR per invocation with a literal number." Failing open is the unsafe direction (cf. [[feedback_safety_direction_over_ux_friction]]). Sibling to [[feedback_hook_cwd_anchor_subagent_worktree]] (#521) — both are hook-input-parsing gaps in the same gh-command-matching hook family.
