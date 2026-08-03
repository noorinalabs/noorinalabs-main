---
name: feedback_rebase_boilerplate_in_rework_briefs
description: "\"Rebase on origin/main first\" is correct in a FIRST-implementation brief and a charter violation in a REWORK brief — mid-ChangesRequested the sanctioned base update is `git merge origin/main`. Two head-move rules pull opposite ways; pick by cycle state."
metadata:
  type: feedback
last_verified: 2026-08-03
---

Two rules about moving a PR branch's base pull in opposite directions, and which applies depends on **where in the review cycle you are** — not on which is tidier.

| situation | correct action | why |
|---|---|---|
| before any review, branch behind `main` | **rebase** is fine | no verdicts to invalidate, no reviewer anchor |
| mid-cycle, an open `ChangesRequested` | **`git merge origin/main`** | `pull-requests/reviews.md` § Additive Commits on ChangesRequested: a force-push resets the head-SHA anchor the reviewer's contents-API chain depends on |
| verdicts already Approved, branch conflicts | **`git merge origin/main`** | #950 excludes merge commits from staleness; a rebase moves `T_content` and drops every verdict |

**The failure is in orchestrator boilerplate, not in anyone's knowledge of the rule.** "Rebase on `origin/main` first" reads as harmless hygiene and gets copied into every brief. In a rework brief it instructs the implementer to violate the charter.

**Observed 2026-08-03, PR #1295.** The orchestrator wrote "rebase on `origin/main` first" into a rework brief issued during an open ChangesRequested. The implementer complied and force-pushed at 15:15:11Z. It cost nothing only because GitHub still served the orphaned blob to the reviewer's contents-API chain. **The same orchestrator had, an hour earlier on PR #1269, deliberately chosen merge over rebase to preserve two Approved verdicts — and explained why — then wrote the opposite instruction into the next brief.** Knowing the rule is not the control; the boilerplate is.

**How to apply:** make the base-update instruction a function of cycle state, and say the reason inline so a compliant implementer can catch a wrong instruction:
- first implementation → *"rebase on `origin/main` before opening the PR"*
- rework or post-approval → *"`git merge origin/main` if you need a base update; never rebase, never force-push — it resets the reviewer's head-SHA anchor (mid-cycle) and drops every verdict (post-approval)"*

Corollary worth keeping: when a conflicted PR already has its verdicts, **merging `main` in is strictly better than rebasing** — #1269 kept 2/2 through a real conflict resolution this way, confirmed by re-running the oracle and seeing `T_content` unchanged.

Related: [[feedback_pr_review_verdict_format]] (§9 — a head move drops every verdict), [[feedback_spawn_brief_protocol]] (briefs composed from HEAD-current artifacts).
