---
name: feedback_pr_review_verdict_format
description: "Consolidated PR-review verdict-format family — the exact trailer fields Hook 4 counts (RequestOrReplied never Verdict, Approved-only, roster-form Requestor, literal TechDebt line, after the LAST sole ---), which hook bites on prose, EDIT-not-append amendment, hook-imported counting, and the spawn-brief obligations that prevent each failure. Hooks fail OPEN on every near-miss."
metadata:
  type: feedback
---

Consolidates (2026-07-13, #944/#931): feedback_hook4_regex_prose_false_match, feedback_validate_pr_review_approved, feedback_techdebt_literal_line_not_section, feedback_verdict_amendment_edit_not_append, feedback_verdict_count_hook_regex, feedback_requestor_roster_name_form, feedback_spawn_brief_requestor, feedback_reviewer_brief_techdebt. Every rule survives; history in git.

## Surfaces
1. [The canonical trailer block — fields, values, placement](#1-the-canonical-trailer-block)
2. [Approved-only counting; comments, not `.reviews`](#2-approved-only-counting)
3. [Requestor semantics — YOU, space-form roster name](#3-requestor-semantics)
4. [TechDebt attestation — exact token, every verdict comment, file-first](#4-techdebt-attestation)
5. [Amendment = EDIT in place, never append](#5-amendment--edit-in-place)
6. [Which hook bites on prose (and the Field:Value prose ban)](#6-prose-false-match)
7. [Counting discipline — import the hook; freshness](#7-counting-discipline)
8. [Spawn-brief obligations (the upstream fix for all of the above)](#8-spawn-brief-obligations)

**The failure mode everywhere: the hooks fail OPEN on near-misses.** A wrong field name, a dotted Requestor, a missing TechDebt line, a mis-placed trailer — each parses as *nothing*, silently, and the shortfall surfaces hours later at merge time attributed to the reviewers. Nine Approved comments across five PRs once parsed as zero (main#930/#932, the `Verdict:` regression).

## 1. The canonical trailer block
`validate_pr_review` (Hook 4) reads verdict fields only from the **trailer block** — text after the **LAST line that is a sole `---`** — with fenced/inline code blanked first and **last-match-wins** within the trailer (#511). The block, verbatim, as the last lines of the comment:
```
Requestor: <reviewer's exact roster name>
Requestee: <PR author's exact roster name>
RequestOrReplied: Approved
TechDebt: none
```
- The field is **`RequestOrReplied:`** — `Verdict:` is not a field any hook asks for; `_extract_charter_field` reads whatever name the CALL SITE passes, so probing a comment for `Verdict` "works" and proves nothing (main#932).
- Bold (`**Requestor:**`), single-asterisk, and bare forms all parse: `\*{0,2}Field:\*{0,2}\s*(.+)`. Cite the symbol, never a line range — line ranges rot.
- Correct fields **above** a later `---` are invisible — a long review using `---` as a horizontal rule got its verdict silently skipped while a bare one-liner counted (main#940). Any parenthetical touching the field name (`Requestor (retracted):`) un-matches it — that, not a banner rename, is what actually un-counts a verdict.

## 2. Approved-only counting
The 2-reviewer merge gate counts **distinct Requestor values across `RequestOrReplied: Approved` comments only**. `Reply`/`Replied`/`Request`/`ChangesRequested` contribute zero, whatever the prose says (P3W8: ~17 addenda across 11 PRs because briefs said `Reply`). `wave-bootstrap`-labeled PRs need one Approved. And check **issue comments**, not `gh pr view --json reviews` — comment verdicts never appear in `.reviews` (a PR can read "0 reviews" while carrying 2 valid Approveds; P5W5 lp#140 got redundant reviewers spawned). Editing a `Request`-form comment in place to `Approved` DOES register (da PR#269); the "cannot be edited" caveat applies to `Reply`-form comments.

## 3. Requestor semantics
`Requestor:` = the reviewer posting (YOU); `Requestee:` = the PR author. Three recurring corruptions, all counted as 0-of-2 at merge:
- **Author-swap** (PR#349): brief templates naming the PR author on both lines get copy-pasted verbatim. Never write `Requestor: <PR author>` anywhere.
- **Paired-reviewer swap** (main#504): two reviewers each writing the OTHER's name. Symmetric swap coincidentally still counts 2 but is incoherent; asymmetric blocks. Briefs: `Requestor: <Your Name> (YOU — not the author and NOT the paired reviewer)`.
- **Dotted form** (da PR#269): Hook 4 (#498) roster-validates the value against `.claude/team/roster/` in lowercased space form. `Nikolaos.Papadopoulos` counts as NON-roster → "2 distinct Requestors but 0 recognized." Dictate the exact space-form roster-card name.
Reviewer-class rule: before posting, re-check the two lines against yourself and the author — a brief that gets them wrong is an upstream error to override, not copy.

## 4. TechDebt attestation
Hook 4 requires a literal line-start `TechDebt: none` or `TechDebt: #N, #M` in **every** verdict comment (Approved AND ChangesRequested, including superseded ones — the hook scans ALL of a reviewer's verdicts; ig#1085 blocked twice on stale ChangesRequested comments). A `## Tech Debt` markdown section with prose does NOT register (PR#918); `Tech-debt:`/`Tech-Debt:` hyphen forms do NOT match (P5W4, 4 reviewers). **File findings first**, then reference (`TechDebt: #91`); `none` only when genuinely nothing — and read the prose before filing: keyword flags ("non-blocking", "follow-up") massively over-count; already-tracked refs and explicitly-accepted observations attest `none`. Omitting the instruction from reviewer briefs once blocked ~38 verdicts / ~19 PRs wave-wide (P5W5).

## 5. Amendment = EDIT in place
To retrofit a missing/wrong field onto a posted verdict, **EDIT the original comment via REST PATCH** — a new corrected comment does NOT supersede: the hook scans every verdict comment, so the old one still flags (missing TechDebt) or still counts (wrong Requestor). Fetch body → fix → `gh api -X PATCH .../issues/comments/<id> --input <(jq -n --rawfile ...)` (never `-f body=@file` — [[feedback_gh_cli_gotchas]] §5) → re-read to verify. Same rule when the PR head moves after your approval: edit your original Approved to state it covers the new head; if you posted a second one, neutralize the redundant comment so exactly one carries the Approved. All comments share the `parametrization` principal, so the orchestrator can PATCH mechanically — preserve reviewer text verbatim.

## 6. Prose false-match
Never reproduce the literal `Field: Value` shape in review prose, PR bodies, or issue comments. **The hook that bites is `validate_review_comment_format`** — an unanchored whole-body first-match `re.search` for the Requestor shape (no `^`, no code-stripping, no trailer scope): a sentence four screens above your trailer blocks the `gh pr comment`. Hook 4 itself was scoped by #511 (trailer-only, last-match-wins) and cannot see prose above a sole `---` — the old "Hook 4 first-matches your prose" mechanism is FALSE (corrected main#933; its fail-closed/fail-open double life is tracked in main#932/#934). **EXCEPT for `TechDebt:`, where it is still TRUE — the #511 trailer-scoping covers `Requestor`/`RequestOrReplied` (via `_extract_charter_field`) but NOT the attestation.** `validate_pr_review.py:1116` runs `re.search(r"\*{0,2}TechDebt:\*{0,2}\s*(.+)", body)` against `body = comment.get("body", "")` (line 1066, the WHOLE comment) — so **first prose occurrence wins and shadows your trailer**. Tripped live 2026-08-02 (Nino Kavtaradze, PR #1215): prose describing the attestation degraded his verdict to `TechDebt present but UNPARSEABLE`. That case is loud; **the dangerous shape is silent** — prose reading `TechDebt: #999` registers #999 as the attested debt while the trailer says `none` (or vice versa), i.e. wrong data in an attestation gate with no warning. Until fixed, treat §6's "never write `Field: Value` in prose" as **strictest for `TechDebt:`**, and note that a memory saying Hook 4 is prose-immune is the exact belief that makes this bite. Safe forms: slash-separated ("the bare-line Requestor/Requestee/status/TechDebt block") or backtick the field name without its colon. Meta-lesson (Oyunbileg, 2026-07-09): a memory that proposes a fix pre-declares its own falsification — name the artifact that will falsify it, or the memory teaches a dead mechanism forever.

## 7. Counting discipline
Before spawning a second reviewer or claiming the gate is clear, **count by importing the hook, never by re-implementing it**:
```python
import sys; sys.path.insert(0, ".claude/hooks")
from validate_pr_review import _extract_charter_field, _is_approved
approvers = {r for c in comments
             if (r := _extract_charter_field("Requestor", c["body"]))
             and _is_approved(_extract_charter_field("RequestOrReplied", c["body"]) or "")}
```
A hand-rolled `jq`/`grep` must reproduce code-stripping, trailer-narrowing, last-match-wins AND the Approved-only filter — four chances to be silently wrong, and the observed failure was in the UNSAFE direction: a jq count of "2" built from unfiltered Requestor lines nearly waved through PRs carrying zero approvals (main#933 review; `jq`'s `^` is string-anchored, not line-anchored). Oracle CLI: `.claude/lib/pr_review_state.py` (main#707). **Freshness is yours**: the hook counts comments, not shas — an approval predating the head is not an approval.

**The merge command MUST name the repo LITERALLY — `--repo owner/name`, NEVER `-R $VAR` (P9W25, main#981).** Hook 4 parses the `gh pr merge` command string **pre-shell-expansion**, so an unexpanded `$DA` is not a resolvable `owner/repo`; `_resolve_owner_repo` returns None and the hook **FAILS OPEN (allows the merge)** instead of blocking — silently bypassing the 2-reviewer gate. Verified: `gh pr merge 451 -R $DA …` → allow; `gh pr merge 451 --repo noorinalabs/noorinalabs-data-acquisition …` → block. In W25 this compounded with the brief-format error below: 4 feature→wave PRs merged with 0 counted approvals AND no gate block. Two independent orchestrator errors, each individually catchable, that only bit because they co-occurred. Always merge with a literal `--repo`; the gate can only guard a target it can resolve.

## 8. Spawn-brief obligations
Every reviewer brief must dictate, verbatim: the 4-line trailer as the LAST lines after a sole `---`; `RequestOrReplied: Approved` for gating posts; the reviewer's exact space-form roster name on `Requestor:` (author on `Requestee:`); the literal `TechDebt:` token with file-findings-first instruction; posting via `gh pr comment --body-file`; and read-back before reporting "posted." Orchestrator, pre-merge: re-derive the distinct-Approved set from comment bodies (§7) — never trust "Approved, posted." **COPY the canonical block from §1 verbatim — do NOT paraphrase it (P9W25).** The orchestrator briefed reviewers with an invented `**Review: Approved**` line + `RequestOrReplied: Request` — a paraphrase that reads like an approval but the hook has no `Review:` parser and `Request` counts zero, so 6 PRs' verdicts parsed as 0 approvals. Having this memory loaded is not enough; the failure was paraphrasing a block whose exact tokens are load-bearing. One reviewer (Alejandra) ignored the wrong brief, used `RequestOrReplied: Approved`, and was the only counted approval — trust the enforcer over a brief, and when correcting a reviewer, run the actual hook (§7) before asserting their verdict is wrong.

### §9 — a head move drops EVERY verdict, including the ones the change "obviously" doesn't affect

§7 says an approval predating the head is not an approval. The corollary that gets missed: **when a head moves, re-request from *every* reviewer, not just the one who asked for the change.**

Failure, 2026-07-30, PR #1178. Reviewer A blocked on a two-line documentation fix; reviewer B had Approved. The orchestrator told the author to re-request from A only, reasoning that a doc-only additive commit could not disturb what B had measured. That reasoning is defensible on the merits and **irrelevant to the gate** — `compute_review_state()` excludes any verdict cast before the head moved, full stop. The instrument returned `distinct_reviewer_count=0, passes=False`: both verdicts gone, and the PR would have sat at 0/2 while everyone believed it was at 1/2. Caught only because the head move prompted a gate re-run; a report of "A re-approved, we're 2/2" would have been believed.

**Materiality is not an input to the gate. Do not reason about it — run the instrument after every head move.**

Re-anchoring is cheap when the delta really is inert: prove it with [[feedback_ast_strip_docstrings_carries_review]] (AST comparison with docstrings stripped + ancestry check) and the prior reviewer can post a short re-affirmation instead of redoing the pass.

Cross-references: [[feedback_gh_cli_gotchas]] (§5 `-f body=@file`, §8 formal-review 422), [[feedback_reviewer_correction_vs_merge_race]], [[feedback_silent_zero_is_not_a_measurement]] (a review that cannot be counted is indistinguishable from no review), [[feedback_ast_strip_docstrings_carries_review]].
