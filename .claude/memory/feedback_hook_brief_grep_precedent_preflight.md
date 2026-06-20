---
name: feedback_hook_brief_grep_precedent_preflight
description: "Before composing a hook-tier spawn brief, grep for existing hooks that already parse the trigger-command shape. If a precedent exists, brief specifies extend-or-extract, never from-scratch duplicate. Brief-author-class application of skills.md § Process-Doc Authorship."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 0be57897-3749-48b2-8850-f155e5434000
---

When composing a spawn brief for hook-tier work, before specifying parser/regex/dispatcher behavior, run a pre-flight grep against `.claude/hooks/*.py` for any existing hook that already parses the same trigger-command shape. If a precedent exists, the brief MUST specify either (a) extend that hook, or (b) extract a shared helper that both hooks call — NEVER specify a from-scratch duplicate.

**Why:** P3W10 2026-05-16 — Brief for issue #445 (Hook 21 `post_label_change_wave_field_sync`) specified "PostToolUse hook on Bash with regex match against `gh issue edit ... --add-label "p{N}-wave-{M}"`" without checking that `.claude/hooks/post_wave_kickoff_comment.py` already parses that exact command shape via `_shell_parse.tokenize` + `iter_command_segments`. The brief also cited `.claude/hooks/auto_add_issue_to_board.py` as "GraphQL `addProjectV2ItemById` precedent" without reading it — that hook actually uses `gh project item-add` (CLI), not GraphQL. The real GraphQL `updateProjectV2ItemFieldValue` precedent lives in `.claude/skills/board-audit/SKILL.md` § 7.

Both errors are framing-vs-artifact violations at the brief-author layer — the exact failure mode that `skills.md § Process-Doc Authorship: Derived-From-SKILL.md-At-HEAD` (merged to main at 22:02:26Z) is designed to prevent. The brief was composed at ~22:15Z, less than 15 minutes after the rule landed. The implementer (Wanjiku-2) caught both via the surface-and-pause discipline at ~22:23Z. Less than 30 minutes from rule-promotion to first self-applied catch-and-correct cycle.

The lesson generalizes the Process-Doc Authorship rule to a layer the rule's #444 codification did not explicitly enumerate: the **brief-author class** (orchestrator-class agents composing spawn briefs for implementers). The implementer-class process-doc-author and the reviewer-class artifact-verifier are already covered by `skills.md § Process-Doc Authorship` + `pull-requests.md § Trust the Artifact, Not the Framing`. The brief-author-class extension closes the third corner.

**How to apply (pre-flight checklist for hook-tier brief composition):**

1. **Identify the trigger-command shape** in the brief (e.g., `gh issue edit ... --add-label "<pattern>"`, `gh issue create ...`, `git commit ...`).
2. **Grep existing hooks for the trigger shape**:
   ```bash
   grep -l "gh issue edit" .claude/hooks/*.py
   grep -l "gh issue create" .claude/hooks/*.py
   grep -l "_shell_parse" .claude/hooks/*.py  # any hook using the shared parser
   ```
3. **Read each match at HEAD** via the local file or `gh api repos/.../contents/<path>?ref=main`. Verify whether the existing hook parses the same trigger shape (not just any `gh issue edit`, but the same flag/argument pattern).
4. **Decide brief shape based on the read**:
   - **No existing hook parses the shape** → brief specifies a new hook with from-scratch parser. Safe.
   - **Existing hook parses the same shape** → brief MUST specify (a) extend the existing hook to do both actions, OR (b) extract a shared helper into `.claude/hooks/_*_parse.py` that both hooks call. Specifying a from-scratch duplicate parser in the new hook is a brief-author-class violation of the Process-Doc Authorship rule.
5. **Identify the dispatch precedent** in the brief (e.g., "GraphQL X", "CLI Y", "REST PATCH Z"). Grep for the precedent **in the file the brief cites** to verify the cited file actually uses that mechanism:
   ```bash
   grep -nE 'gh api graphql|gh project|gh issue|gh pr|gh api repos' .claude/hooks/<cited-file>.py
   ```
   If the cited file uses a different mechanism than the brief claims, find the actual precedent (often in a skill — `grep -lE '<mechanism>' .claude/skills/*/SKILL.md`) and update the brief before sending.

**Cost of the pre-flight**: ~30-60 seconds (2-3 grep commands + 1-2 file reads). Cost of skipping: implementer-class surface-and-pause + round-trip + ~30 minutes of decision-bundling delay (the P3W10 #445 case).

**Sibling rules:**
- [[spawn-brief-field-advisory-pattern]] — same class of brief-author-discipline issue applied to declarative fields (`isolation: "worktree"`, `implementer: <name>`, `cwd: <path>`).
- [[review-against-artifact-not-framing]] — reviewer-class application of the same primitive.
- [[verify-diagnosis-before-delegating]] — generalized verify-via-artifact-before-action that this pre-flight extends to brief composition.

**Charter promotion candidate (W11 retro):** If this recurs in W11 hook-tier work, promote to `skills.md` as a sub-section under the new `§ Process-Doc Authorship: Derived-From-SKILL.md-At-HEAD` — would land as `§ Process-Doc Authorship Applies at Brief-Author Layer: Grep Precedents Before Specifying Parsers` (or similar). Currently single-instance; memory-tier only until cross-wave recurrence confirms.

**Severity:**
- Minor when caught by implementer-class surface-and-pause pre-Edit (P3W10 #445 case — caught + corrected with no wasted implementation work, just decision-bundling round-trip).
- Moderate if the implementer silently follows the duplicate-parser spec to a merge (parser duplication, extra dispatch overhead, future-rename pain).
- Severe if the cited-mechanism error (e.g., "GraphQL precedent in X" when X is CLI) leads to implementation against the wrong API surface (could produce a hook that doesn't actually mutate the intended state).

**Origin:** Nadia Khoury (main-nadia), P3W10 #445 brief composition 2026-05-16. Wanjiku-2 (main-wanjiku-2) surfaced both errors in her checkpoint-1 investigation pass. Less than 30-minute recognition→action loop from rule-promotion (#444 merge 22:02:26Z) to first self-applied catch (22:23Z) to correction landed (22:24Z).
