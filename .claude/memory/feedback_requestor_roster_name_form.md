---
name: feedback_requestor_roster_name_form
description: "Hook 4 (#498) roster-validates the Requestor value — dotted `First.Last` verdicts count as NON-roster and block merge with 0/2 even when both reviewers Approved; spawn briefs must dictate the exact space-form roster name."
metadata:
  type: feedback
---

Hook 4 (`validate_pr_review.py`, #498) does not just count distinct `RequestOrReplied: Approved` Requestors — it **validates each Requestor string against `.claude/team/roster/` personas** (lowercased, space-separated `first last`). A verdict whose Requestor uses the branch-name-style dotted form (`Requestor: Nikolaos.Papadopoulos`) is counted as **non-roster** and contributes 0 toward the 2-reviewer threshold, producing a confusing "2 distinct Requestors but only 0 recognized" merge block even when both reviews are valid Approvals.

**Why:** reviewers naturally reuse the `{FirstInitial}.{LastName}` / `First.Last` convention from branch names and email identities; the roster match wants the human name form from the roster card (`Nikolaos Papadopoulos`).

**How to apply:**
1. Reviewer spawn briefs MUST dictate the literal verdict header, e.g. `Requestor: Nikolaos Papadopoulos` (exact roster-card name, spaces not dots) — don't leave the form to the agent. Same for `Requestee:`.
2. Pre-merge self-check: the hook's block message lists the valid roster forms — compare before re-spawning anything.
3. Remediation is a mechanical **orchestrator REST PATCH of the comment body** (fetch body → fix the `Requestor:`/`Requestee:` lines → `gh api --method PATCH .../issues/comments/<id> --input -` with a jq-built JSON payload → re-read to verify). Orchestrator-PATCH of verdict field shape has explicit precedent (pre-#511 fixes cited in the hook text). Beware [[feedback_gh_pr_edit_silent_noop]]: `-f body=@file` silently no-ops; use `--input`.
4. Related observed behavior (2026-07-03, da PR#269): editing an Approved-intent verdict in place from `RequestOrReplied: Request` → `Approved` DID register with the hook — the "cannot be edited in-place" caveat in the block text applies to `Reply`-form comments, not `Request`.

First instance: da PR#269 (2026-07-03) — both reviewers (Alejandra, Nikolaos) used dotted Requestor forms; merge blocked 0/2; fixed by orchestrator PATCH of both comments, merge then clean.

Sibling of [[feedback_verdict_count_hook_regex]] (bold/bare field-shape) and [[feedback_spawn_brief_requestor]] (Requestor/Requestee direction) — this one is about the NAME VALUE form.
