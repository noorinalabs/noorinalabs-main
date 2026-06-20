---
name: feedback_no_head_in_surface_enumeration
description: Surface enumerations for pre-spawn briefs MUST count occurrences not files; truncation by `head` silently drops sites and produces under-counted briefs.
type: feedback
originSessionId: 3d519c58-11df-4e60-ba09-74c7024fc9f1
---
When enumerating a code-surface for a pre-spawn brief (e.g., "how many `actions/checkout@v` sites does this repo have?"), DO NOT pipe the per-file grep output through `head -N` before summing. Truncation silently drops occurrences and produces under-counted briefs that look complete because the visible output is plausible. Use `grep -c` per file and sum the counts, then read the un-truncated grep output only as a sanity check on the totals.

**Why:** P3W8 deploy#280 spawn-brief — enumerated `actions/checkout@v4` and reported 14 sites (1 occurrence per workflow file × 14 of 15 files). Actual count was 30 occurrences (terraform.yml has 8 alone, integration-tests/cold-rebuild/verify-deploy/promote/deploy-prod/compose-validate have 2-3 each). Brief shipped with `head -10` truncating the per-file grep before any tally happened. Under-count would have shipped as a 17-site scope leak into a follow-up PR if the implementer had used the brief as a checklist; Aisha's independent worktree-side scan (Hook 15 librarian + her own grep) hit all 37 sites and surfaced the gap. Wanjiku's #309 freshness-pass audit independently confirmed the 30+3+4 surface 2-3 hours earlier and was the canonical cross-reference. Same root cause as the github-script@v7 sample miss (saw lines 82, 130, stopped because `head` cut line 174).

**How to apply:** When writing a pre-spawn brief that enumerates a multi-file surface:

1. **Counting pass — never with `head`:**
   ```bash
   total=0
   for f in <file-set>; do
     count=$(grep -cE "<pattern>" "$f")
     [ "$count" -gt 0 ] && echo "  $f: $count" && total=$((total + count))
   done
   echo "TOTAL: $total"
   ```
2. **Sanity-check pass — read the full grep, no `head`, no `| head -N`:**
   ```bash
   grep -nE "<pattern>" <files>  # full output, scan for missed sites
   ```
3. **Cross-reference if a consolidated audit exists:** for org-wide surfaces, the dedicated audit (Wanjiku-style #309 (b) per-repo table) is authoritative; the manager brief is advisory. Cite the audit URL in the brief explicitly so reviewers compare against it (memory `feedback_review_against_artifact_not_framing.md`).
4. **Implementer-side override is the saving discipline:** Hook 15 + the implementer's own scan are designed precisely so a flawed manager brief does NOT cap the work-scope. Reinforce this in spawn briefs ("verify the surface yourself in the worktree, my count is advisory").

Companion to `feedback_pre_spawn_verify_at_origin.md` (verify *where*, this verifies *how*) and `feedback_pre_spawn_brief_verified_at_head.md` (per-caveat sweep). Together: pre-spawn discipline = origin head_sha + full enumeration + per-caveat applicability rule.

Promotion candidate filed for `charter/agents.md § Pre-Spawn State Check` extension — see noorinalabs-main issue (P3W8 retro-pickup).
