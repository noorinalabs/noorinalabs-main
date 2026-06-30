---
name: project_implementor_label_convention
description: FIRSTNAME_LASTNAME implementor label reinstated + enforcement tool; branch-first/commit-author-fallback inference; bulk label-apply uses REST not GraphQL.
metadata:
  type: project
---

The `FIRSTNAME_LASTNAME` label is the assignee tag **and** the durable "who implemented" record (charter `issues.md` § Assignment → *Implementor label — reliably applied*). The practice lapsed for several waves; **reinstated 2026-06-30** (owner, main#907 / PR#908) with machine enforcement.

- **Tool:** `.claude/lib/apply_implementor_labels.py` — idempotent re-derive+apply (dry-run default; `--apply`; `--repo` to scope). Wired into `/wave-wrapup` **Step 6.5** so it can't lapse again.
- **Inference:** (1) branch prefix `{FInitial}.{Lastname}/{NNNN}-…` → persona label **when it already exists in the repo** (primary, high-confidence); (2) else the **commit-author identity** of the PR is consulted and authoritative in that fallback (branch vs author diverge on stale-branch/takeover — see [[feedback_throttle_takeover]]). One implementor per PR; an issue with multiple implementing PRs accrues each. New labels **ASCII-folded** (`MÉNDEZ`→`MENDEZ`); existing labels in any form (incl. legacy `First Last` space form in isnad-graph) **reused, never duplicated**.
- **Backfill done:** 949 issues labeled, 26 new persona labels, across all 8 repos.

**GOTCHA (reusable):** bulk `gh issue edit --add-label` runs over **GraphQL** and exhausts the **5000-pt/hr GraphQL primary limit** after a few hundred mutations (`API rate limit already exceeded`). The `core` REST budget is separate — apply labels in bulk via REST `gh api --method POST repos/<owner>/<repo>/issues/<n>/labels -f 'labels[]=<L>'` (core budget, 5000/hr) to sidestep the GraphQL ceiling. Same split applies to reads: `gh issue view`/`gh pr view` are GraphQL; `gh api repos/.../issues/N` is REST.
