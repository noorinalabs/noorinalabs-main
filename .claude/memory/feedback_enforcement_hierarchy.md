---
name: feedback_enforcement_hierarchy
description: For any new behavior the team should follow, prefer automated enforcement (hook) over invokable tooling (skill) over written rule (charter). Charter-only rules decay.
type: feedback
originSessionId: bfc8466f-74c1-4625-bdb4-26a9cc1f0262
promotion_target: none
promotion_threshold:
  retro_citations: 3
referenced_in_retros: ['W7', 'W8', 'P2W9']
status: enforced-elsewhere
superseded_by: "implicit in CLAUDE.md § Ontology + .claude/team/charter/hooks.md § Hook Authorship Requirements; first concrete enforcement instance is Hook 15 (enforce_librarian_consulted, 2026-04-19)"
---
When introducing a new team behavior, evaluate enforcement options in this order:

1. **Hook** — automatic, fires every time, no discipline required
2. **Skill** — invokable tool that does the right thing for you
3. **Charter update** — written rule, requires team discipline

Use the **first** option that's technically feasible. Do not skip to a lower tier just because it's easier to author.

**Why:** Charter rules without enforcement decay. P2W7 retro caught 5 PRs merged with zero reviews despite the charter requiring 2 reviewers — the rule existed for waves before the `validate_pr_review.py` hook was written. Same pattern with CI: "CI must be green before merge" has been in the charter since Phase 2 Wave 1, but waves keep merging with red pre-existing CI (security-audit CVE in isnad-graph, test_migrate_users ModuleNotFoundError in user-service). Steven's quality bar is being eroded by drift.

---

## STATE THE SHAPE, NOT THE STORY — a rule written as a war story does not fire (2026-07-11, deploy#584)

**A tier-3 rule can fail even when it is correct, written down, and actively in the reader's working set. This is a failure mode of the memory system itself, not of the engineer reading it.**

The `errexit` lesson was recorded as: *"a guard reading an rc."* True, and the engineer **quoted it in her own comments an hour before walking into it in a sibling script** — because the new instance **had no rc in it.** It was a bare `VAR="$(… | grep …)"` that matched nothing, crashing under `-e` + `pipefail`.

> **The rule was stated as its INSTANCE, so it did not pattern-match a new instance.**

Restated as the **shape** — *"any `VAR="$(grep …)"` that can legitimately match nothing is a **crash** under `-e`+`pipefail`, not an empty string"* — it fires on sight.

> ### ⛔ CORRECTION 2026-07-11 (Nino Kavtaradze, deploy#591) — the restatement above was itself OVER-GENERALISED
>
> It originally read `$(grep/sed/find …)`. **That lumps three commands with three different no-match contracts**, and it is wrong for two of them. Measured, not reasoned:
>
> | command | exit on **no match** | under `set -e` |
> |---|---|---|
> | `grep` | **1** | **CRASHES** ✅ the rule holds |
> | `sed -n '/x/p'` | **0** | survives — **the rule is FALSE** |
> | `find` | **0** | survives — **the rule is FALSE** |
> | `find` over an **unreadable** dir | **1** | **CRASHES — but on an ERROR, never on a no-match** |
>
> **The over-generalised rule fails in BOTH directions.** It produces guards against crashes that cannot happen (`sed`, `find`), *and* it points at the wrong trigger for `find` — so an engineer who removes a `find` guard on learning "find doesn't crash on empty" is then bitten by the permission case. A rule that is wrong in both directions is worse than no rule.
>
> **The correct instruction is not a list of commands. It is: LOOK UP THE COMMAND'S ACTUAL NO-MATCH EXIT CODE. Do not generalise across commands that merely *feel* similar.** `grep`'s "no match is exit 1" is a deliberate and unusual contract, not a Unix convention — most filters exit 0 on empty output.
>
> **And the way this correction was nearly missed is the lesson underneath it.** My first check ran `find /etc -name zzz` as a non-root user, which exits **1** — on permission-denied subdirectories, *not* on the empty result. **It CONFIRMED the wrong rule, for a reason that had nothing to do with the rule.** A contaminated control that happens to agree with you is the hardest kind to catch, because nothing prompts you to look again. See [[feedback_silent_zero_is_not_a_measurement]]: *a number that lands in your favour deserves MORE scrutiny than one that doesn't.*
>
> ⚠ The same over-generalised sentence exists in **`noorinalabs-deploy`'s repo-level memory** and in a code comment at `scripts/restore.sh:331-334`. Both need the same correction.

> **Knowing a rule does not help if you cannot recognise that you are inside it. Recognition is the scarce thing, not knowledge.** (Same finding as main#957: an experienced author wrote `until [pending == 0]` on the day he was teaching that exact defect class, with the correct oracle already in the repo.)

**How to apply, and it applies to this whole corpus:**
- **Write the invariant, not the anecdote.** *"X is a crash, not an empty string"* beats *"that time we lost an rc in the backup script."*
- **Lead with the syntactic shape a reader will actually be looking at** when they are about to commit the error — the code they are typing, not the incident that produced it.
- Keep the story **underneath** the rule as evidence, never **as** the rule.
- **Any memory phrased as *"when you do X and then Y…"* probably needs restating as the invariant it protects.** Worth a sweep of the corpus.

*(Aisha Idrissi, who rewrote her own repo-level memory after it failed to save her: "That will silently repeat across the whole corpus wherever a rule is written as a war story.")*

---

**How to apply:**
- When proposing a new rule, ask "can a hook do this?" before writing charter prose
- When the user reports a recurring quality issue, default to building a hook unless impossible
- Skill is the right tier when the action requires judgment (e.g., `/wave-retro` writes a retro — can't be a hook)
- Charter is the right tier when the rule is about *intent* or *structure* that no automation can verify (e.g., "Program Director coordinates across teams")
- If you fall back to a lower tier, state the technical reason in the proposal so the user can challenge it
