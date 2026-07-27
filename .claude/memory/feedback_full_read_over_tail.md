---
name: feedback_full_read_over_tail
description: "Memory-file state-claims (not-written / not-present) require full Read or targeted grep, not tail-only. Tail-read misses mid-file additive clarifications. Sibling to [[feedback_review_against_artifact]] applied to non-canonical storage."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 0be57897-3749-48b2-8850-f155e5434000
---

When a state-claim is about a **memory file** (under `~/.claude/projects/.../memory/`) — "the forward-pointer is/isn't written", "the citation is/isn't present", "the clarification is/isn't there" — verify via **full `Read` or `grep -n <token>`**, NOT via `tail -N`.

**Why:** Memory files are append-mostly but not append-only — additive clarifications are commonly inserted mid-file near the relevant heading, not at the file tail. A `tail -10` read sees only the historical "**Origin:**" paragraph (which sits at the file's actual tail) and produces a false-negative "not written" inference when the new line is at L13. Sibling to [[feedback_review_against_artifact]] (reviewer-class, applied to in-repo files via `gh api contents`); this is the same primitive applied to **non-canonical storage** — memory dir is outside the repo, not reachable via `gh api`, so the verifying read is filesystem `Read`/`grep`, not artifact-API.

The trap is double-layered: (1) memory dir is outside the repo so `gh api .../contents` doesn't apply, which correctly redirects the reader to filesystem, but (2) the reader then under-applies the filesystem read by tail'ing instead of grep'ing.

**How to apply:**
- For any state-claim of the form "X is/isn't in `<memory-file>`", run `grep -n "<token>" <memory-file>` or `Read` the full file before stating the claim. NEVER tail-only.
- If a PR body lists a memory file as a "changed" file, the verifying read is `grep -n "PR #<N>"` or `Read` the full file (memory dir is outside repo, no `gh api` route).
- In review comments, prefer stating presence with line-number evidence (`L13`) over stating absence — absence claims need exhaustive search to be sound.

**Origin:** P3W10 PR #444 review (Santiago, 2026-05-16). I `tail`-read `feedback_child_repo_implementer_rule.md`, saw the prior tail (`**Origin:** Clarified 2026-04-22...`), and inferred "forward-pointer not written" — but the additive clarification line was at L13 mid-file. Nadia caught it post-verdict via direct `Read`. Non-blocking (verdict was Approved either way), but had it been blocking, the framing-not-artifact inference would have triggered a needless round-trip. Edit-2 to PR #444 verdict comment retracted the claim. Sibling primitive to [[feedback_review_against_artifact]] (which is now also a charter section per `skills.md § Process-Doc Authorship: Derived-From-SKILL.md-At-HEAD` — the very rule PR #444 adopts). This memory documents the storage-location-specific variant the charter rule didn't enumerate.
