---
name: feedback_spawn_brief_protocol
description: "Consolidated spawn-brief protocol family — pre-spawn premise verification at origin HEAD, surface enumeration + caveat rulings, git cat-file for file-existence, declarative fields are advisory vs the direct-instruction carveout, roster-card surname reads, and hook-tier parser-precedent grep. Root cause everywhere: a brief composed from inferred/cached state instead of HEAD-current artifacts."
metadata:
  type: feedback
---

Consolidates (2026-07-13, #944/#931): feedback_pre_spawn_verify_at_origin, feedback_pre_spawn_brief_verified_at_head, feedback_pre_spawn_verify_file_exists, feedback_spawn_brief_field_advisory_pattern, feedback_spawn_brief_direct_instruction, feedback_brief_author_verify_roster_surname, feedback_hook_brief_grep_precedent_preflight. (Requestor/Requestee field rules live in [[feedback_pr_review_verdict_format]].) Every rule survives; history in git.

## Surfaces
1. [Verify issue premises at origin HEAD before spawning](#1-premises-at-origin-head)
2. [Enumerate the surface from wave-branch HEAD + rule every caveat](#2-surface-enumeration--caveat-rulings)
3. [File existence via `git cat-file -e`, never working tree](#3-file-existence-at-head)
4. [Declarative brief fields are ADVISORY — orchestrator must act](#4-declarative-fields-are-advisory)
5. […but a numbered imperative step IS the action (carveout)](#5-direct-instruction-carveout)
6. [Teammate surnames come from the roster card body](#6-roster-surname-from-card-content)
7. [Hook-tier briefs: grep for parser precedent first](#7-hook-tier-parser-precedent)

**Root cause across the family:** the brief-author worked from inferred, cached, or working-tree state instead of the artifact at origin HEAD. The brief-author class is the third corner of the trust-the-artifact triangle (implementer: `skills.md` § Process-Doc Authorship; reviewer: [[feedback_review_against_artifact]]).

## 1. Premises at origin HEAD
Before spawning an implementer for any audit-deliverable issue ("remove X / sync Y / clean up N"), verify the premises hold at the wave-branch head: `gh api repos/<o>/<r>/git/trees/<head_sha>?recursive=1` or `.../contents/<path>?ref=<head_sha>`. If premises fail (target doesn't exist as the body assumes), **scope-block** — comment the evidence (sha, command, output) on the issue and bounce to the scope owner; do NOT spawn the implementer to "discover the gap." Three P3W8 instances: da#43/#44 (0 entries where the issue said "remove copies"), 4-of-5 isnad-graph hook files 404 at origin, deploy#276 already resolved. If premises *over*-deliver (an assumed blocker already cleared), spawn AND note the unblock. Commit the verification line into the spawn request so reviewers can trace it.

## 2. Surface enumeration + caveat rulings
For a multi-call-site mechanical change (action upgrades, dep bumps, API rewrites), the brief-author MUST: (a) enumerate the full surface **from the wave-branch HEAD** (not local main, not the issue's audit table) into a per-call-site table — file, line, current, target; count via `rg -c` per file then sum, never `| head -N` ([[feedback_no_head_in_surface_enumeration]]); (b) for **every named caveat** in the parent audit/charter/kickoff (e.g. upload-artifact@v4 same-name), explicitly rule applicable vs non-applicable for THIS repo — never pass a caveat through as "be careful"; (c) put both in the brief and require the PR body to mirror them so reviewers audit the chain. Skip only for single-site obvious flips. (P3W8: lp#88 6-site ruling; deploy#280 20-site enumeration.)

## 3. File existence at HEAD
Per-file claims in a brief ("ruff finds 1 error in <path>") MUST be verified with `git cat-file -e origin/<branch>:<path>`, never `ls`/glob/a linter run from cwd — the working tree can lag deletions by months, and a lint finding against a stale on-disk copy encodes a working-tree fact as a branch-HEAD fact (P3W11: brief cited a file deleted two waves earlier; the live ruff run "confirmed" it). `git show`'s `fatal: path … exists on disk, but not in '<ref>'` is the SAME signal — treat it as a HARD STOP (the finding is stale → close the issue, don't spawn), never as "needs rebase."

## 4. Declarative fields are advisory
Brief fields like `isolation: "worktree"`, `implementer: <name>`, `cwd: <path>` are declarative intent, **not contracts the harness enforces**. The orchestrator must take the imperative action (run `git worktree add`, re-spawn via the child manager, cd-then-verify) AND verify the effect at canonical source (`git worktree list`, roster.json, filesystem). Three worktree-field no-ops in 72h (P3W10); 34% of W10 declared implementers overridden by child-repo managers (codified as `agents.md` § Parent-Orchestrator Implementer Declarations Are Advisory, PR#444). When a spawned agent reports the declared state doesn't match reality: agent pauses and surfaces; orchestrator takes the imperative recovery action. Severity scales from caught-pre-Edit to wrong-branch commits others build on ([[feedback_cwd_collision_cross_spawn]]).

## 5. Direct-instruction carveout
A **numbered imperative step in the brief body** ("2. Run `git worktree add …`") is fundamentally different from a declarative field: the spawned agent executing the step IS the imperative action — just do it; don't bounce it back citing §4 (us#103: a worktree-add step needlessly escalated). Test: "Did the brief tell me explicitly to run THIS command?" → run it. "Did it state a property and expect the environment to already be that way?" → bounce. Sibling: [[feedback_declarative_head_needs_action]] (landed-at-HEAD artifacts need orchestrator action or a session restart).

## 6. Roster surname from card content
When a brief names a teammate ("You are <First> <Last>"), the surname MUST come from **reading the roster card body** (`Name:` line) — filenames only carry the firstname (`observability_engineer_nurul.md`), memory goes stale, and a plausible-sounding guess is a fabrication. Hook 5 validates commit identity against the card, so a fabricated surname hard-rejects every commit; the agent's best case is a wasted escalation round-trip, worst case a phantom roster card (deploy#88: "Nurul Hassan" invented; card says Hakim). One Read at compose time beats a 10-minute recovery.

## 7. Hook-tier parser precedent
Before composing a brief that specifies hook parser/regex/dispatcher behavior: `rg -l "<trigger shape>" .claude/hooks/*.py` (and `_shell_parse` users). If an existing hook already parses the trigger-command shape, the brief MUST specify extend-it or extract-a-shared-helper — never a from-scratch duplicate. And verify every cited precedent **in the cited file**: P3W10 #445's brief cited a "GraphQL precedent" in a hook that actually uses the CLI (the real GraphQL precedent lived in a skill). Cost of the pre-flight: ~1 minute; cost of skipping: a surface-and-pause round-trip or a duplicate parser. The same grep-precedent discipline applies to any command template a brief dictates — verdict-posting commands included ([[feedback_pr_review_verdict_format]] §8).

Cross-references: [[feedback_verify_diagnosis_before_delegating]] (verify via artifact before delegating at all), [[feedback_stale_inbox_manager]] (re-verify before correcting a teammate), [[feedback_refresh_before_status_claim]], [[feedback_investigate_before_implement]] (implementer-side mirror: origin-audit an unevidenced brief before Edit/Write).

### §8 — a re-review request MUST cite the verdict's comment URL, never "your prior verdict"

When re-anchoring a reviewer after a head move, **cite the comment ID or URL of the verdict being superseded**:

```
Re-anchor your verdict at <new-sha>.
Your prior verdict: <comment URL>     <-- cite it
```

**Never** write *"your ChangesRequested"* / *"your Approved"* and leave the reviewer to locate it.

**Why (wave-29, PR #1193).** Two agents reviewed one PR under the single roster persona `Weronika Zielinska` (an orchestrator spawn error — one persona assigned to one PR twice). A re-request said *"your ChangesRequested verdict was against the old head"* and pointed at a comment signed with that persona. **From inside a session, a persona-signed comment you did not write is indistinguishable from a summarized-away turn of your own.** The reviewer adopted it and then wrote "my one-liner" and "my previous sweep (17,252 commands)" about another agent's measurements — into a PR comment and, via the orchestrator, into a memory note that had to be corrected (`d17305b`).

The orchestrator's own briefs carried the identical shape all wave (*"Your Approved on #1178 needs re-affirming"*), so this is a **template defect, not an individual lapse**. Citing the URL lets the reviewer check authorship before adopting the framing — it would have caught the collision before a word was written.

Costs one line. Independent of, and available before, the underlying gate fix (#1197 — `validate_pr_review` counts distinct **personas** while the ≥1-Opus safeguard assumes distinct **agents**).

Corollary: **do not assert a reviewer's own findings back to them as established fact.** State what the record shows and let them confirm — an orchestrator summarising a reviewer's prior work to that reviewer is a second path to the same mis-adoption. Raised by the reviewer who made the slip, in its own postmortem.
