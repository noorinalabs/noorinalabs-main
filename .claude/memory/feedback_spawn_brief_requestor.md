---
name: feedback_spawn_brief_requestor
description: Reviewer-spawn briefs MUST instruct Requestor=reviewer-name, Requestee=PR-author-name. Hook counts distinct Requestor values; swapped briefs collapse to 1 distinct reviewer.
type: feedback
originSessionId: 607a8778-830e-4ba7-a5e3-de78682fa871
---
In every reviewer-spawn brief, the orchestrator MUST give the spawned reviewer their literal name to use as `Requestor`, with the PR author as `Requestee`. Do NOT default to `Requestor: <PR-author>` — that's the swap that bites.

**The hook-gated invariant:** `validate_pr_review` counts **distinct** `Requestor` values across `RequestOrReplied: Approved` comments. Two reviewers both posting `Requestor: <same-name>` = 1 distinct reviewer counted, regardless of comment count or comment-author identity.

**Why:** P3W9 PR #349 cascade (2026-05-10). Orchestrator spawn brief gave both Nadia and Bereket `Requestor: Aino Virtanen / Requestee: Aino Virtanen` (author on both lines). Both reviewers posted Approved with that header. Hook saw 1 distinct non-author Requestor (Aino doesn't count — she's the PR author). Merge blocked: "0/2 required peer reviews." Required re-posts from both reviewers with corrected headers (`Requestor: Nadia Khoury` and `Requestor: Bereket Tadesse` respectively). Cascade was contained — caught on first merge attempt, two re-posts cleared it — but the spawn-brief template error was load-bearing.

**How to apply:**

- Every reviewer-spawn brief block specifying the Approval comment format must include the reviewer's literal full name on the `Requestor:` line, e.g.:
  ```
  Requestor: Nadia Khoury
  Requestee: Aino Virtanen
  RequestOrReplied: Approved
  TechDebt: <none|#N>
  ```
- Never write a generic template with `Requestor: <PR author>` and expect the reviewer to mentally swap it. Past behavior shows reviewers copy-paste the brief verbatim.
- Same applies to Changes-Requested comments — `validate_pr_review` doesn't gate on those, but the paper trail is incoherent if a Changes-Requested comment names the PR author as Requestor (semantically nonsensical: the author isn't requesting changes from themselves).
- Pre-write check at orchestrator time: search the spawn brief for `Requestor:` lines; each must name the spawned reviewer, never the PR author.

**Reviewer-class application (P3W11 2026-05-17 dual-instance):** the same trap bites at *write-time* even when the spawn brief is correctly formatted. When a brief lists the charter fields as `Requestor: <author> / Requestee: <author>` (treating them as labels for the *PR's* author/requester semantics), the reviewer copy-pastes verbatim and ships a comment with Requestor=author. Hook 4 counts it as 0 distinct reviewers.

- **Reviewer-class rule:** before posting ANY verdict comment, mentally re-check: `Requestor:` is ME (the person posting); `Requestee:` is the PR author. The labels describe *the comment's* semantics ("who is requesting/replying"), NOT the PR's. If the brief gives a literal-line template that names the PR author as Requestor, OVERRIDE it — that's an upstream brief error, copying it perpetuates the bug.
- **Recovery:** EDIT the existing comment via REST PATCH on `repos/.../issues/comments/<id>` per `feedback_verdict_amendment_edit_not_append`. A new appended comment with corrected Requestor does NOT supersede; hook scans ALL Approved comments and the old wrong one still counts as 1 distinct Requestor=<author>=0-non-author.
- **Single-instance evidence:** PR #299 (Nino-spawn, my 2°) — Nino's brief listed `Requestor: Nino Kavtaradze / Requestee: Nino Kavtaradze` (both lines = PR author). I copied verbatim. Hook 4 blocked merge; Nino self-caught + asked for REST PATCH; recovered same comment id 4473837854 via `gh api -X PATCH .../issues/comments/<id>`. Compare with PR #296 same session: Weronika's brief gave the correct `Requestor: Lucas Ferreira / Requestee: Weronika Zielinska`, my copy was correct, no recovery needed. The difference was 100% upstream brief quality — but reviewer-class rule says I should have caught Nino's brief error at copy-time, not let it ship.

**Same family as W8 lesson `feedback_validate_pr_review_approved_not_reply.md`:** both are orchestrator-class spawn-brief errors about `validate_pr_review` hook-counted comment header fields. W8 was about the verdict literal (`Reply` doesn't register; only `Approved` does). W9 is about the Requestor field semantics. The hook gates on FOUR distinct properties of the header: literal `RequestOrReplied: Approved`, distinct `Requestor` values, presence of `TechDebt:` line, and (per `block_gh_pr_review`) use of `gh pr comment` not `gh pr review`.

**Tracked for charter promotion:** `validate_pr_review` BLOCKED message extension to call out the Requestor/Requestee swap is filed as `noorinalabs-main#356` (W9, Aisha-filed during PR #353 review). Same-cycle dogfooding — the hook that BLOCKED #349 will have its message improved to prevent the next recurrence.

**Severity if violated:**

- Single PR caught at merge attempt (both reviewers re-post): minor — 2 message round-trips, no work lost.
- Multiple PRs caught at merge attempt simultaneously: minor-to-moderate — coordination cost grows linearly with PR count in flight.
- Reviewer posts Approved with wrong Requestor and never corrects: moderate — paper-trail incoherence persists in git history.

**Reviewer-class application (P3W11 2026-05-18 batch-9 dual-instance — PAIRED-REVIEWER swap):** a *new variant* of this trap surfaced where the spawn brief was correctly formatted (literal `Requestor: <reviewer-name>` for each reviewer separately), yet both reviewers in a pair SWAPPED each other's names on their verdict comments.

- **Pattern:** main#504 review pair (Lucas + Nurul, doc-only PR). Lucas's brief said `Requestor: Lucas Ferreira` literally; Nurul's brief said `Requestor: Nurul Hakim` literally. Both posted verdicts within ~30s of each other. Lucas posted `Requestor: Nurul Hakim`; Nurul posted `Requestor: Lucas Ferreira`. Each used the OTHER reviewer's name. Hook 4 would have counted 2 distinct values (Lucas, Nurul) — but coincidentally still 2 because the swap is symmetric. Caught at orchestrator read-back of comment bodies, PATCHed both via REST before merge attempt.
- **Why this variant happens:** "Requestor" in English reads as "the one requesting the review." Reviewers may interpret it as "the paired reviewer who, alongside me, is requesting this PR be merged" — and then write the OTHER reviewer's name. Different mental model from the author-swap pattern but produces a similar incorrect-name outcome.
- **Asymmetric-swap risk:** if both reviewers in a pair swap the same way (both write reviewer-A's name), Hook 4 sees 1 distinct Requestor and blocks merge. Symmetric swap (A→B, B→A as in main#504) happens to be self-healing on the distinct-count axis but still incoherent for paper-trail and triggers an unnecessary PATCH round. Cannot rely on swap symmetry.
- **Pre-post mitigation that worked:** during the same batch, I sent urgent SendMessages to the 3 still-pending reviewers (Aino #505, Weronika + Aisha #333) reminding "Requestor: YOUR name, NOT the paired reviewer". All 3 then posted with correct Requestor. Aino was particularly at risk because she was paired with Santiago (similar role pairing as Lucas+Nurul deploy/main cross). The pre-post reminder cost ~3 SendMessage calls and prevented 3 more PATCH cycles.
- **Spawn-brief reinforcement:** the existing "Requestor: YOU (not the author)" parenthetical in briefs is insufficient against paired-reviewer swap. Extend to: `Requestor: <Your Name> (YOU — not the author and NOT the paired reviewer)`. Both negatives explicit.
- **Severity:** orchestrator-time PATCH costs ~5min per swapped comment + ~30s SendMessage per pre-post warning. Charter-promotion candidate if recurrence continues into W12.

**`TechDebt:` attestation — exact token, ALL comments, file-findings-first (P5W4 2026-06-15, 4-reviewer recurrence):** the `validate_pr_review` BLOCK on a missing `TechDebt:` line bit 4 reviewers across two PRs (ingest#88: Bjørn+Petra; ig#1085: Mei-Lin+Anya) in one session because my reviewer-spawn briefs specified the finding line as prose **`Tech-debt: <list or None>`** (hyphen) instead of the canonical header token. Three sharp facts:

1. **Exact token, no hyphen.** The hook matches literally `TechDebt:` — `Tech-debt:` / `Tech-Debt:` / a bolded `**Tech-debt:**` in prose do NOT satisfy it. The line must be its own line in the structured header block (alongside `Requestor:` / `Requestee:` / `RequestOrReplied:`), value either `TechDebt: none` or `TechDebt: #N, #M`.
2. **Hook scans EVERY verdict comment, not just the latest.** Latest-verdict-wins applies to Approved-vs-ChangesRequested counting, but NOT to the TechDebt attestation: after a re-review cycle, a reviewer's *superseded* `ChangesRequested` comment ALSO needs a `TechDebt:` line or the merge stays blocked (ig#1085 blocked a second time on the two stale ChangesRequested comments until both were PATCHed to `TechDebt: none`). Amend ALL of a reviewer's verdict comments on the PR.
3. **File findings BEFORE attesting.** Charter requires non-blocking findings be filed as `tech-debt`-labeled issues first, then referenced (`TechDebt: #91`). `none` is only valid when the reviewer genuinely found nothing. P5W4 follow-ups filed this way: ingest#91/#92/#93, ig#1087.

**Brief-template fix (apply going forward):** every reviewer-spawn brief's verdict template must show the canonical header line verbatim — `TechDebt: none` (or `TechDebt: #N` after filing) — and instruct: keep it in the header block, NOT prose; if you re-review after a ChangesRequested, amend that prior comment too; use REST PATCH (`-F`, never `-f`) + read-back. Companion to the `-f`/`-F` file-expansion gotcha in [[feedback_gh_pr_edit_silent_noop]] (gh CLI silent-no-op family — use REST + read-back verify; which also bit these same reviewers when posting via `-f body=@file`). Orchestrator: don't trust a reviewer's "Approved, posted" — re-derive distinct-Requestor + grep each comment for `TechDebt:` before attempting merge; the merge probe is a safe no-side-effect way to surface the block.

**Cross-references:**

- `feedback_validate_pr_review_approved_not_reply.md` (W8 sibling lesson)
- `charter/pull-requests.md § Comment-Based Reviews` (the hook's gate semantics)
- `noorinalabs-main#356` (W9 carry-forward — message expansion in `validate_pr_review` BLOCKED text)
- `feedback_verdict_amendment_edit_not_append.md` (recovery mechanism — REST PATCH the existing comment, never append)
