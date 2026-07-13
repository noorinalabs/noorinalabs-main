# Agents — Orchestration Model

> Part of the [agents charter index](../agents.md) — re-shelved from `charter/agents.md` for section-level loading (#963). Rules unchanged.

## Hub-and-Spoke Orchestration Model <!-- promotion-target: none -->
The orchestrator is the **single point that can create agents**. The Program Director coordinates and plans; the orchestrator executes the spawning. This is a hub-and-spoke model, not recursive delegation.

**Workflow:**

1. **Orchestrator spawns the Program Director** — who investigates, plans, creates GitHub issues, and coordinates across repos.
2. **Program Director does NOT do implementation work inline.** When the Program Director needs team members (for audits, releases, or standards work), they send a **spawn request** back to the orchestrator via SendMessage. The spawn request must include full context: task description, target files, acceptance criteria, git identity, and any dependencies.
3. **Orchestrator spawns team members** on behalf of the Program Director, routing results back via SendMessage.
4. **Team members report completion** to the orchestrator, who relays to the Program Director or acts on the results.

### Spawn Request Delegation

**When any team member requests that another agent be spawned, the orchestrator MUST honor the request immediately.** Do not redirect the requesting agent to "do it yourself" — spawned agents do not have access to the Agent tool.

**Protocol:**
1. The requesting agent names the person to spawn and provides the task context
2. The orchestrator reads the named person's roster card to load identity and personality
3. The orchestrator spawns the agent with the context provided by the requester
4. The orchestrator confirms the spawn back to the requesting agent

**Rationale:** Sub-agents cannot spawn other agents (Agent tool limitation). Telling them to "do it yourself" wastes round-trips and stalls execution. This was identified in Wave C when Santiago requested Nadia Boukhari 3 times before the orchestrator acted.

Failing to honor a spawn request within the same response is a **minor feedback event** for the orchestrator.

### Spawn Isolation Default

**All implementer-class spawns from the orchestrator MUST be invoked with `isolation: "worktree"`,** even when the parent-side worktree is cosmetic (e.g., the agent's actual code work lives in a child-repo clone).

**Rationale:** the harness uses worktree-isolation as the signal for workspace-presented team-member surfaces. Non-isolated subagents render as generic "background tasks" — incorrect for implementer-class agents that the operator needs to monitor as team members.

**Cost:** a temporary parent-repo worktree per agent (auto-cleaned if no changes — see Agent tool docs).

**Benefit:** correct workspace presentation; Hook 14 (`enforce_ontology_context`) fires consistently across all implementer spawns; manager-class agents (per-repo PD/manager) and implementer-class agents (per-repo engineers) both render under their team membership rather than as anonymous background tasks.

**Exception:** research-only forks (e.g., `Agent` calls that omit `subagent_type` to inherit context) need NOT use isolation, since they're explicitly context-inheriting forks rather than fresh implementer workspaces.

**Origin:** owner-named at P3W6 wave-kickoff (2026-05-06) after observing 18 implementer spawns rendered as "background tasks" in the harness UI rather than as workspace-presented team members. The orchestrator weighed the trade-off explicitly during spawn ("17 of 18 implementers do code work in child repos which are `.gitignore`d from the parent — orchestrator-side worktree is cosmetic") and picked "no parent worktree" — that turned out to be the wrong call because the UI presentation cost wasn't surfaced in the trade-off analysis. Codified by noorinalabs-main#290.

Failing to set `isolation: "worktree"` on an implementer spawn is a **minor feedback event** for the orchestrator.

### No Direct-to-Engineer Spawns

**The orchestrator MUST NOT spawn engineers directly without first spawning the Program Director.** Even for "simple" or "mechanical" fixes, the team hierarchy must be followed:

1. Spawn the Program Director
2. PD coordinates with the relevant repo manager(s)
3. Repo managers request engineer spawns via the PD
4. Orchestrator spawns engineers on behalf of the PD

**Rationale:** Bypassing the hierarchy loses manager visibility, skips peer review coordination, and undermines accountability. This was identified as a recurring pattern in Waves 1/A/B ("lead layer bypassed entirely") and repeated in Wave C Phase 1. The only exception is if the user explicitly authorizes a direct spawn.

Spawning engineers without the PD is a **moderate feedback event** for the orchestrator.

## Single-Leader Constraint: One Team Per Orchestrator Session <!-- promotion-target: none -->

The harness provides a **single implicit team per orchestrator session** — there are no `TeamCreate`/`TeamDelete` tools (an earlier harness exposed them and enforced "one team per session" by failing a second `TeamCreate` with "Already leading team"; the current harness simply has one implicit team and nothing to create). Combined with the Agent-tool limitation above, this shapes how waves run:

### What this means in practice

- **The `Team Names` table above is only operative when you open a session dedicated to one repo.** When a session is opened in `noorinalabs-main` to run a cross-repo wave, all spawning uses `team_name: "noorinalabs"` and there is only the one implicit team. Agents for deploy, isnad-graph, user-service, landing-page, etc. are all spawned as members of the single `noorinalabs` team.
- **Cross-repo waves always use `team_name: "noorinalabs"`** for every agent — managers AND implementers — because the single-team constraint makes anything else technically impossible.
- **Per-repo team names** (`noorinalabs-isnad-graph`, `noorinalabs-deploy`, etc.) only apply when a session is run in isolation in that repo — not the common case for wave-kickoff work orchestrated from `noorinalabs-main`.

### Delegation mechanics (reinforcement of § Hub-and-Spoke)

1. **Orchestrator** spawns managers (Program Director + per-repo managers) via the `Agent` tool with `team_name: "noorinalabs"` — the single implicit team (no `TeamCreate` call exists in the current harness).
2. **Managers** do NOT have the Agent tool. When they need implementers, they `SendMessage` the orchestrator (team-lead) with a spawn request: "please spawn {Name} from {repo}/{roster-card} for {issue}, branch {X}, reviewers {Y, Z}."
3. **Orchestrator spawns implementers** with the context the manager provided PLUS the Ontology Context bake (per `enforce_ontology_context.py` hook — see § Orchestrator checklist below) PLUS the expected `/ontology-librarian` first-action instruction (per Hook 15 in `hooks.md` — advisory since #857; still best practice in every spawn brief).
4. **Implementers report** back to their assigning manager via `SendMessage`. Cross-manager coordination is in-band (`SendMessage`) plus on-GitHub (meta-issue comments + Cross-Contract PRs).
5. **Per-repo rosters remain canonical** for commit identity, domain ownership, and reviewer pairing — the session team is a logical overlay on top of them.

### Reviewer slate discipline (FIRST-LINE in every spawn prompt)

> **Position-first rule (resolves [main#201](https://github.com/noorinalabs/noorinalabs-main/issues/201)).** The reviewer slate is the first decision the spawn prompt forces the orchestrator (or PD-via-spawn-request) to make — not buried mid-checklist where it gets back-filled after scope/branch/sequencing have already framed the assignment. Every spawn prompt template MUST place this section immediately after the identity / git-identity preamble and BEFORE the `## Ontology Context` section (when that section is present — see coordinator-class exemption note below).
>
> **Coordinator-class exemption (#468):** the `## Ontology Context` section is MANDATORY for implementer-class spawns and OPTIONAL for coordinator-class spawns (Manager, Pipeline Manager, Project Lead, Program Director, TPM / Technical Program Manager, Release Coordinator). Coordinators communicate primarily via SendMessage and rarely Edit/Write directly; `enforce_ontology_context.py` matches the canonical `You are **{Name}**, {Role}[ for {repo}]` opener and exempts these roles from the spawn-time Agent block. Hook 15 (`enforce_librarian_consulted.py`) still fires (advisory, non-blocking since #857) at the Edit/Write surface for the few coordinators that do edit. When a coordinator brief DOES include `## Ontology Context`, the position-first rule above continues to apply — the section retains its required location.
>
> **You MUST NOT name as reviewer:**
> - The **manager of the implementer's repo** (manager-boundary rule — see `pull-requests.md` § Two-Reviewer Assignment, observed-and-corrected ≥4× across three managers in P2W10).
> - The **author of the upstream PR being reviewed** (self-review boundary — `block_gh_pr_review.py` enforces, but spawn-time prevention is cheaper than merge-time block).
> - An agent currently **owning a gating issue** for this PR (independence — the gating-issue owner needs to drive resolution, not bless the implementation).
> - An **Advisor-only role** on a cross-team consultation (per task-framework Statement A/B distinction — Advisor reviews shape decisions, not PR diffs).
>
> **Valid reviewer sources:**
> - **Same-team technical peers** — primary slot (e.g., user-service tech-lead reviewing user-service implementer).
> - **Cross-team technical peers with substantive domain overlap** — secondary slot (e.g., deploy SRE reviewing user-service CI workflow change).
> - **Standards & Quality Lead (Aino Virtanen)** for charter-convention questions only — not as a generic peer-review slot.
>
> **Name BOTH reviewers explicitly in the spawn prompt** AND in the kickoff comment AND in the meta-issue execution-plan table BEFORE any branches are created. If the PD's execution-plan table is missing a 2nd reviewer for any expected PR, the orchestrator pauses spawning and asks the PD to fill the gap (see `pull-requests.md` § Two-Reviewer Assignment at Wave Kickoff).
>
> **Why position-first:** P2W10 surfaced four+ instances across three managers' spawn prompts where the manager-as-reviewer anti-pattern slipped through despite charter rule existing. Pattern: reviewer-naming had already happened mentally during the early-drafting pass (scope/branch/sequencing first, reviewers as a back-fill). The charter rule was correctly applied in isolated contexts but missed when embedded in a multi-section spawn prompt. Moving the rule to first-line position makes "who reviews this" a first-order architectural decision the template forces the agent to make before advancing. Discipline becomes architectural, not memorial. Co-signed by Bereket (deploy manager), Nadia Boukhari (isnad-graph + user-service manager), Marcia (landing-page manager) — each had a concrete instance during W10.

### Reviewer spawn brief — throughline-watch (default, #320) <!-- promotion-target: none -->

> **Every reviewer-class spawn brief MUST include a "Throughline-watch" instruction.** Reviewers are PR-scoped by primary task, but they often see cross-PR patterns that only become visible when looking at the wave from a reviewer position. Asking explicitly for throughline observations turns this latent signal into a structured surface for the wave retro's ★ summary.
>
> **The section MUST appear in every reviewer-class spawn brief**, regardless of whether the wave is expected to have a wave-level thesis. Single-PR waves can produce "no throughline observed, this is a standalone fix" and that is itself a useful retro signal.
>
> **Required template block (copy-paste verbatim into reviewer-class spawn briefs):**
>
> ```
> ## Throughline-watch (in addition to PR-level review)
>
> As you review this PR, note any pattern that recurs across multiple PRs in
> the wave or any wave-level structural finding that emerges from your
> PR-level review. Surface findings explicitly at the end of your review
> comment under a `## Throughline observations` section — do NOT bury them
> inside TechDebt or per-line inline review.
>
> Typical throughline shapes (illustrative, not exhaustive):
> - "Same root cause appears in {N} PRs across {M} repos" — convergent class
> - "Boundary X (parent→child / hook→skill / detection→strategy) breaks
>   repeatedly" — boundary-class
> - "Charter rule Y is technically followed but operationally undermined
>   by Z" — rule-vs-practice gap
> - "Memory M would prevent class C but isn't promoted to charter/hook
>   yet" — promotion candidate
>
> If you observe no throughline (single-PR wave, or finding is fully
> PR-scoped), write: `## Throughline observations\n\nNo wave-level pattern
> observed — this PR is a standalone fix.` The explicit no-pattern record
> is useful retro-signal too.
>
> The next wave-retro `*` summary pass synthesizes throughline observations
> across all reviewers into the wave thesis (per P3W7 demonstration:
> 5 reviewers + 4 implementers independently arrived at the two-tier wave
> thesis BEFORE the * spawn fired).
> ```
>
> **Why default, not per-wave addition:** P3W7 added the throughline-watch instruction ad-hoc to that wave's reviewer briefs and produced a complete pre-loaded retro thesis (Idris-coined "fixture-first discipline broke at the parent→child update boundary" confirmed by 5 subsequent reviewers; Nadia's ★ spawn synthesized rather than discovered). Making this default — not memorial discipline that the orchestrator must remember to add — propagates the P3W7 win to every wave.
>
> **Origin:** P3W7 retro feedback log § Proposed process changes #5 (orchestrator-class). Promoted via #320.

### Reviewer spawn brief — producer-parity watch (data/graph integrity invariants, #672) <!-- promotion-target: none -->

> **Every reviewer-class spawn brief for a data/graph PR that adds or changes an integrity / load invariant MUST include a "Producer-parity watch" instruction.** Integrity invariants — a normalized field, a dedup/identity key, a node/edge constraint, a grading or validation rule — are produced on TWO paths that must stay in sync:
> - the **batch** load path — noorinalabs-data-acquisition `src/graph/load_*`, and
> - the **streaming** Kafka worker — noorinalabs-isnad-ingest-platform.
>
> A fix landed on one path silently diverges the other. This check makes the batch-vs-streaming parity question **default reviewer discipline** rather than a memorial catch that depends on a reviewer happening to remember it.
>
> **Required template block (copy-paste verbatim into reviewer-class spawn briefs for data/graph integrity/load PRs):**
>
> ```
> ## Producer-parity watch (data/graph integrity/load invariant PRs)
>
> This PR adds or changes an integrity / load invariant (e.g. a normalized
> field, a dedup/identity key, a node or edge constraint, a grading or
> validation rule). Such invariants are produced on TWO paths that must stay
> in sync:
>   - the BATCH load path  — noorinalabs-data-acquisition `src/graph/load_*`
>   - the STREAMING worker — noorinalabs-isnad-ingest-platform (Kafka)
>
> Ask explicitly, and answer in your review: did the producer (the
> implementer) apply the SAME invariant on the OTHER path? If this PR
> changes only one path, the sibling path's parity work MUST be tracked by a
> linked follow-up issue, or the PR MUST state why the other path is exempt.
> Surface your answer under a `## Producer-parity` section in your review
> comment — do not let batch-vs-streaming parity stay memorial.
>
> If the PR does not touch a data/graph integrity/load invariant, record
> under a `## Producer-parity` section: "N/A — not an integrity/load
> invariant change." The explicit no-op record is useful signal, same
> rationale as throughline-watch.
> ```
>
> **When it applies:** PRs in noorinalabs-data-acquisition `src/graph/load_*`, noorinalabs-isnad-ingest-platform workers, or any PR that adds/alters a node/edge/field invariant consumed by the graph. The reviewer always records the `## Producer-parity` answer — N/A included.
>
> **Format discipline (Hook 4):** emit the producer-parity answer under the `## Producer-parity` markdown header as prose — NOT as a `Field: value` trailer line. The verdict-trailer field names parsed by `validate_pr_review.py` (`Requestor` / `Requestee` / `RequestOrReplied` / `TechDebt`) are reserved; a stray `Field:`-shaped line in prose risks Hook 4 first-match capture (per memory `feedback_pr_review_verdict_format`).
>
> **Origin:** P5W1 retro Proposed Change #3, owner-adopted 2026-06-14 ("Both → file as P5 issues"). Reviewer-surfaced by Alejandra Reyes-Fuentes on da#148 (PR #150 added `grade_normalized` on the batch path only; the streaming mirror is tracked in da#153 #4). Promoted via #672.

### Orchestrator checklist when spawning an implementer

Every implementer spawn prompt MUST include, **in order**:

1. **Reviewer slate** (first-line per § Reviewer slate discipline above) — both reviewers named, manager-boundary verified, valid-source check applied.
2. **`## Ontology Context`** section (literal heading) with librarian output baked in — `enforce_ontology_context.py` scans for this heading and blocks the spawn if absent. **Coordinator-class spawns are exempt** (Manager, Pipeline Manager, Project Lead, Program Director, TPM / Technical Program Manager, Release Coordinator) per the carveout above and #468; the hook's `COORDINATOR_ROLE_OPENER` regex matches the canonical `You are **{Name}**, {Role}[ for {repo}]` opener and skips the block. This item remains MANDATORY for implementer-class spawns (any role not matched by `COORDINATOR_ROLE_OPENER`). Note: spawn-brief composers must canonicalize role titles to the exempt enumeration — e.g., `"Infrastructure Manager"` → `, Manager` for the regex match.
3. **Expected first-action** instruction to run `/ontology-librarian {topic}` in the spawned agent's own session — Hook 15 scans the agent's transcript independently and emits an advisory `systemMessage` on Edit/Write otherwise (non-blocking since #857). The consult remains best practice for loading the semantic overlay.
4. **Git identity** flags (`git -c user.name="..." -c user.email="parametrization+FirstName.LastName@gmail.com"`).
5. **Branch name** matching `{FirstInitial}.{LastName}/{IIII}-{slug}` and **PR target** (typically `deployments/phase-{N}/wave-{M}`).
6. **Cross-Contract rule** reference if the PR is part of a cross-contract cluster (charter `pull-requests.md`).
7. **Charter enforcement reminders** (2 reviewers, CI green before merge, no `--no-verify`, no global/repo git config, `/ontology-librarian` per agent).
8. **Reporting pattern** — who they report to (usually their manager) and when (draft open, CI green, blocker, merge).
9. **/tmp file-race discipline:** When using `--body-file` with `gh issue/pr comment` or `git commit -F`, write the file to an issue#-keyed path (e.g., `/tmp/{issue#}-{purpose}.md`) IMMEDIATELY before the gh/git call — no other tool calls between the Write and the consuming Bash. Hook `block_stale_tmp_message_file` blocks files older than 30s. P3W6 surfaced 3 such blocks in spawned-agent gh-comment flows; this discipline prevents them.
10. **Green-before-push CI parity** — the brief MUST instruct the agent to run the repo's **actual CI check-set over the full tree inside its worktree before opening the PR**, NOT to rely on commit/push hooks firing. A fresh `git worktree` has **no** pre-commit hooks installed, so "it committed clean" proves nothing about CI. Require: `pre-commit install && pre-commit install --hook-type pre-push && pre-commit run --all-files`, PLUS the bare CI commands the repo's `.github/workflows/` runs over the whole tree (e.g. `uv run ruff check .`, `uv run mypy <pkg>`, the cspell invocation, `pytest` / `npm test`). A PR may not open with a red check; a pre-existing red gate is surfaced to the orchestrator/owner, never merged through (per `pull-requests.md` § Full Local⇄CI Tooling Parity + No Force-Merging Failing Checks). Owner directive 2026-06-14 (`noorinalabs-main#684`).

### Orchestrator checklist when spawning a reviewer

Every reviewer-class spawn prompt MUST include, **in order**:

1. **PR + author identity** — the specific PR# and head-SHA being reviewed, the author's name (NOT the reviewer's), and the angle the reviewer is being asked to take (TPM angle, charter/QA angle, domain angle, release coordinator angle, etc.).
2. **Expected first-action** instruction to run `/ontology-librarian {topic}` — Hook 15 scans the reviewer's own transcript and emits an advisory `systemMessage` on Edit/Write otherwise (non-blocking since #857). Reviewer-class spawns don't typically Edit/Write (they post comments), but the librarian is also load-bearing for understanding what the PR touches.
3. **Throughline-watch block** (per § Reviewer spawn brief — throughline-watch above) — copy-paste the verbatim template block. Default, not per-wave addition (#320).
4. **Producer-parity block** (per § Reviewer spawn brief — producer-parity watch above) — for any data/graph PR that adds or changes an integrity/load invariant, copy-paste the verbatim Producer-parity-watch template block so the reviewer asks whether the producer applied the SAME invariant on the sibling path (batch ↔ streaming). Conditional on the PR class (data-acquisition `src/graph/load_*` / isnad-ingest-platform / graph-invariant PRs); for non-data/graph PRs the block is omitted (#672).
5. **`Requestor: <reviewer name>` / `Requestee: <PR author name>` / `RequestOrReplied: Approved | ChangesRequested` / `TechDebt:` format** — explicit reminder using the canonical Direction-table form (per `pull-requests.md` § Comment-Based Reviews, post-#372 / PR #375 fix). **Every reviewer spawn brief MUST embed the verbatim verdict-comment template block below — copy-pasted into the brief, not paraphrased, summarized, or referenced by pointer — so the verdict trailer carries all four lines (`Requestor:` / `Requestee:` / `RequestOrReplied:` / `TechDebt:`) together in one block.** The `TechDebt:` line is mandatory on **every** verdict even when there is no debt (`TechDebt: none`), Approved and ChangesRequested alike — never optional, never deferred. A brief that does not paste the block verbatim is non-conformant. Embedding the block verbatim prevents W9 PR#349-style cascades from re-emerging (per memory `feedback_pr_review_verdict_format`).
   - TechDebt MUST be in the SAME comment as the verdict — edit-appending after the fact gets the verdict-comment dropped from hook counting (per memory `feedback_pr_review_verdict_format`).
   - **P4W6 incident (why this is MUST, not "should"):** the orchestrator authored that wave's reviewer briefs WITHOUT embedding this template; the first wave→main merge was blocked because 7 verdict comments lacked the `TechDebt:` line, and all 7 had to be retrofitted via REST `PATCH` after the fact before the merge could proceed. The template already lived in this very section — the failure was non-use, not absence. This is exactly the cascade the MUST above exists to prevent.

<!-- Promoted from memory: feedback_pr_review_verdict_format.md (P3W9 retro 2026-05-12, owner-approved 2026-05-13) -->

   **Verbatim verdict-comment template (copy-paste into reviewer spawn briefs):**

   > **Canonical source:** see `pull-requests.md § Review Prompt Template (Mandatory)` for the underlying spec. This block is the spawn-brief view; the `pull-requests.md` template is the verbatim source-of-truth reviewers must follow — plain form, no bold markers, no parenthetical descriptions, no extra fields.

   ```bash
   # Use `gh pr comment <PR#> --body-file <path>` — NOT `gh pr review` (block_gh_pr_review enforces).
   # Write the body to a /tmp file FIRST, then comment in the very next tool call
   # (block_stale_tmp_message_file enforces 30s freshness):

   cat > /tmp/<PR#>-review-<reviewer-firstname>.md <<'BODYEOF'
   Requestor: <reviewer-firstname> <reviewer-lastname>
   Requestee: <PR-author-firstname> <PR-author-lastname>
   RequestOrReplied: Approved
   TechDebt: none

   <verdict body — prose, line comments, throughline observations…>

   ## Throughline observations

   <per § Reviewer spawn brief — throughline-watch>
   BODYEOF

   gh pr comment <PR#> --body-file /tmp/<PR#>-review-<reviewer-firstname>.md
   ```

   > Inline `gh pr comment <PR#> --body "..."` is also valid when no /tmp file is involved; `--body-file <path>` is the required form when the body is written to /tmp first (`block_stale_tmp_message_file` 30s freshness rule applies only when a /tmp file is the source). This reconciles the new block above with `pull-requests.md § Review Prompt Template (Mandatory)` lines 47–53 which use inline `--body "..."` — both are legitimate; flag form follows write-path.

   **Required literal forms (hook-enforced):**
   - The line MUST literally start with `TechDebt:` (plain form; `pull-requests.md § Review Prompt Template` forbids bold markers — `validate_pr_review.py` regex tolerates optional `**` for backward-compat with pre-#420 verdicts, but new briefs MUST use plain form). `## TechDebt` section headers + prose do NOT satisfy the regex.
   - Valid values:
     - `TechDebt: none`
     - `TechDebt: none — addressed inline by fixup commit <sha>`
     - `TechDebt: #15, #16` (when issues were filed pre-verdict)
   - `RequestOrReplied: Approved` (NOT `Reply` — `validate_pr_review` counts Approved-only).

   For a ChangesRequested verdict, swap to:
   ```
   RequestOrReplied: ChangesRequested
   TechDebt: none
   ```
   (TechDebt still required even on ChangesRequested — the regex is unconditional.)

   **Why literal:** P3W9 PR #409 cascade — both reviewers followed the prior prose template that prescribed `## TechDebt\n\n…` section header; `gh pr merge` blocked with `BLOCKED: PR #409 has review(s) missing the mandatory TechDebt: attestation line` at merge time, requiring per-comment PATCH amendments. Sibling pattern to P3W8 Approved-vs-Reply cascade — both fixable by spawning-brief template fixed-literal rewrite.

6. **`gh pr review` vs `gh pr comment` discipline** — explicit reminder NOT to use `gh pr review` (`block_gh_pr_review` enforces; spawn-brief mention prevents the trip).
7. **Read-the-diff-at-HEAD discipline** — `gh api repos/.../contents/<path>?ref=<head_sha>` not local clone (per `pull-requests.md` § Origin > Local Clone for "Still-Has-X" File-Content Claims).
8. **Pre-enumeration discipline** — `grep -c` per file then sum, never `| head -N` (per memory `feedback_no_head_in_surface_enumeration`).
9. **Verdict literal-string requirements** — `RequestOrReplied: Approved` (or `ChangesRequested`), NOT `Reply`. `validate_pr_review` counts Approved-verdict comments only; Reply doesn't gate-count (per memory `feedback_pr_review_verdict_format`).
10. **Reporting pattern** — who to report verdict + literal-strings-confirmation to (typically team-lead or the manager who requested the review).

### Origin

Documented during P2W10 kickoff 2026-04-23. Prior charter already had the spawn-delegation mechanics (§ Hub-and-Spoke Orchestration Model), but not the explicit single-leader constraint that eliminates multi-team orchestration as an option. The § Team Names table was ambiguous on whether "Work in noorinalabs-isnad-graph" meant a dedicated isnad-graph-only session or any session touching that repo — this section resolves it in favor of the single-session-team pattern for cross-repo work.


