---
name: feedback_no_head_in_surface_enumeration
description: Surface enumerations for pre-spawn briefs MUST count occurrences not files; truncation by `head` silently drops sites and produces under-counted briefs.
type: feedback
last_verified: 2026-07-27
originSessionId: 3d519c58-11df-4e60-ba09-74c7024fc9f1
---
When enumerating a code-surface for a pre-spawn brief (e.g., "how many `actions/checkout@v` sites does this repo have?"), DO NOT pipe the per-file search output through `head -N` before summing. Truncation silently drops occurrences and produces under-counted briefs that look complete because the visible output is plausible. Use `rg -c` per file and sum the counts, then read the un-truncated output only as a sanity check on the totals.

> **Instrument note (corrected 2026-07-27):** this memory originally prescribed `grep -c` / `grep -nE`. Bare `grep` is now **hard-blocked** org-wide by `.claude/hooks/block_bare_grep.py` (main#1008) — it exits 2 with "BLOCKED: bare `grep` — this org uses `rg` (ripgrep) for text search". The counting *rule* below is unchanged; only the tool is. Add `--no-ignore` when the surface may be gitignored, or `rg` returns a silent zero — which is this memory's own failure mode by another route.

**Why:** P3W8 deploy#280 spawn-brief — enumerated `actions/checkout@v4` and reported 14 sites (1 occurrence per workflow file × 14 of 15 files). Actual count was 30 occurrences (terraform.yml has 8 alone, integration-tests/cold-rebuild/verify-deploy/promote/deploy-prod/compose-validate have 2-3 each). Brief shipped with `head -10` truncating the per-file grep before any tally happened. Under-count would have shipped as a 17-site scope leak into a follow-up PR if the implementer had used the brief as a checklist; Aisha's independent worktree-side scan (Hook 15 librarian + her own grep) hit all 37 sites and surfaced the gap. Wanjiku's #309 freshness-pass audit independently confirmed the 30+3+4 surface 2-3 hours earlier and was the canonical cross-reference. Same root cause as the github-script@v7 sample miss (saw lines 82, 130, stopped because `head` cut line 174).

**How to apply:** When writing a pre-spawn brief that enumerates a multi-file surface:

1. **Counting pass — never with `head`:**
   ```sh
   total=0
   for f in <file-set>; do
     count=$(rg -c --no-ignore "<pattern>" "$f" || echo 0)
     [ "$count" -gt 0 ] && echo "  $f: $count" && total=$((total + count))
   done
   echo "TOTAL: $total"
   ```
   (`rg -c` exits 1 with no output on zero matches, hence the `|| echo 0` — without it the
   loop inherits an empty string and the arithmetic silently mis-sums.)
2. **Sanity-check pass — read the full output, no `head`, no `| head -N`:**
   ```sh
   rg -n --no-ignore "<pattern>" <files>  # full output, scan for missed sites
   ```
3. **Cross-reference if a consolidated audit exists:** for org-wide surfaces, the dedicated audit (Wanjiku-style #309 (b) per-repo table) is authoritative; the manager brief is advisory. Cite the audit URL in the brief explicitly so reviewers compare against it (memory `feedback_review_against_artifact.md`).
4. **Implementer-side override is the saving discipline:** Hook 15 + the implementer's own scan are designed precisely so a flawed manager brief does NOT cap the work-scope. Reinforce this in spawn briefs ("verify the surface yourself in the worktree, my count is advisory").

Companion to [[feedback_spawn_brief_protocol]] — its §1 verifies *where* (origin head_sha) and its §2 the per-caveat sweep, while this memory verifies *how* the surface is counted. Together: pre-spawn discipline = origin head_sha + full enumeration + per-caveat applicability rule.

Promotion candidate filed for `charter/agents.md § Pre-Spawn State Check` extension — see noorinalabs-main issue (P3W8 retro-pickup).
