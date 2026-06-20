---
name: feedback_gh_review_self_approve_422
description: "Spawned reviewer agents using `gh api .../reviews POST` with `event: APPROVE` get 422 \"Can not approve your own pull request\" because gh auth principal matches PR author (all our PRs are authored by `parametrization`); fall back to issue comment with Hook 4 literal-fields block"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 77e35de5-3b28-48a1-92f6-f413bc8debac
---

When a spawned reviewer agent tries to post a formal PR review with `event: APPROVE` (or `REQUEST_CHANGES`) via `gh api repos/.../pulls/N/reviews -X POST --input <payload>.json`, GitHub returns **422 Unprocessable Entity: "Can not approve your own pull request"** if the `gh` CLI auth principal is the same GitHub login as the PR author.

**Why:** All our PRs are pushed via `gh` (auth principal = `parametrization`, the human owner's GH account). Agent commit identities (`Jelani Mwangi <parametrization+Jelani.Mwangi@gmail.com>`, `Ingrid Lindqvist <...>`, etc.) only affect commit author/committer fields — NOT the GH API auth principal. So the GH API sees ALL reviews coming from `parametrization`, and ALL PRs as authored by `parametrization`. GitHub's self-approve protection then 422s every formal-review event.

**How to apply:**

1. **Don't bother with `event: APPROVE` / `REQUEST_CHANGES` API path** for agent verdict posting. It will always 422.
2. **Use issue-comment fallback** — `gh api repos/.../issues/N/comments -X POST --input <payload>.json` (or `gh pr comment <N> --body-file <path>`) — with Hook 4 literal-fields block at end of comment body. Hook 4 parses comment bodies, not formal-review state, so this satisfies the 2-distinct-Approved-Requestors gate.
3. **No branch protection on wave-branches** (verified 2026-05-19 for `noorinalabs/noorinalabs-isnad-graph` wave-11 — 404 on `/branches/wave-11/protection`), so the absence of formal-review-state doesn't gate merge. If a wave branch ever gets protection requiring formal reviews, the agent-as-self-reviewer model breaks and we'd need either: (a) per-agent GH App tokens, (b) re-evaluating the human-as-auth-principal pattern, or (c) granting `parametrization` review-bypass via branch protection allowlist.
4. **Brief reviewer agents to skip the `event: APPROVE` attempt** and post as issue comment directly — saves a 422-roundtrip and the agent's "what happened" diagnosis cycle.

P3W11 isnad-graph PR #924 (2026-05-19): Idris attempted `event: APPROVE`, 422'd, pivoted to issue comment, self-diagnosed correctly (cited "throttle-takeover precedent" loosely but mechanically arrived at the right fallback). His Hook 4 literal lines landed clean. Ingrid posted directly as issue comment. Hook 4 gate satisfied as long as 2 distinct `Requestor:` line-start matches with `RequestOrReplied: Approved` are present in any comment bodies.
