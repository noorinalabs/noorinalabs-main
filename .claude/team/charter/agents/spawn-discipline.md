# Agents — Spawn Discipline

> Part of the [agents charter index](../agents.md) — re-shelved from `charter/agents.md` for section-level loading (#963). Rules unchanged.

## Orchestrator Spawn Discipline — Reuse Idle Teammates, Don't Clone <!-- promotion-target: none -->

When the orchestrator needs to assign new work to a teammate whose persona already exists in the session team, `SendMessage` the idle existing instance — do NOT spawn a fresh `Agent` with a numeric-suffix name (`aino2`, `nadia2`, `wanjiku3`).

### Why

Idle teammates can receive messages — `SendMessage` wakes them up. Spawning a clone creates:

- **Roster clutter.** `aino` and `aino2` side-by-side for the same persona confuses both the operator (which one has the PR context?) and `SendMessage` routing.
- **No shared session memory.** Each fresh `Agent` is a blank slate; the original's accumulated context (PR #409 review history, scratch-file paths, mid-task partial work) is lost.
- **Duplicated Hook 15 librarian overhead.** Every clone must re-invoke `/ontology-librarian` from scratch.
- **Identity-hygiene drift.** Over a multi-PR session the roster grows linearly with PR count instead of staying at the canonical N team members.

### How to apply

- After a teammate sends a "PR ready" or "review complete" idle notification, they are AVAILABLE for the next task. `SendMessage` them with the new spawn-brief content; idle teammates wake on message receipt.
- Only spawn a fresh `Agent` when (a) the persona doesn't yet exist in the session team, OR (b) the existing instance is mid-task and the new work must run truly concurrently with theirs.
- `wanjiku2` (P3W9) is a legitimate parallel-collision precedent: Wanjiku reviewed PR #409 AND PR #410 in the same window; #410 was assigned to `wanjiku2` to keep `/tmp/<reviewer>_review_<PR#>.md` namespaces separate per the [[parallel-reviewer-tmp-filename-collision]] discipline. That precedent does NOT generalize to "always clone for the next task."
- If unsure whether to reuse or clone, default to reuse — clones are recoverable (`SendMessage` shutdown_request, respawn fresh), but the wasted spawn cost is not.

### Severity if violated

- One unnecessary clone in a session: **minor** (roster clutter; ~5min context loss when the clone has to rebuild what the original already knew).
- Pattern across a session (3+ clones in a single wave, as observed in P3W9 with `aino2`/`nadia2`/`wanjiku3`): **moderate** — pre-emptive promotion to charter on first-occurrence rather than waiting for second instance, since the cost (~15min per clone) and the recovery friction justify codifying immediately.

### Origin

P3W9 instances 2026-05-12: orchestrator spawned `aino2` for issue #401 work, `wanjiku3` for issue #163 work, `nadia2` for issue #126 work despite `aino`, `wanjiku2`, `nadia` being idle from prior W9 tasks. Owner flagged the pattern mid-session; this section codifies the correction. Companion to `feedback_throttle_takeover` (orchestrator-class spawn-discipline family — both are "use the agent you have, not a fresh one").

## Pre-Spawn State Check + Crossed-Message Race Protocol <!-- promotion-target: none -->

Phase 3 Wave 1 surfaced a recurring failure shape: implementer ships work + status report → orchestrator's task_assignment for that same work was already in flight in the message bus → implementer receives "do X" message AFTER having shipped X. This is **architecturally distinct from `feedback_refresh_before_status_claim`** — no individual discipline fix prevents the race; verification-before-claim doesn't help when the message bus delivers messages in the order they were *queued*, not the order events resolved.

### Default protocol — accept as cost-of-throughput

The implementer-anticipates-context discipline (implementers reading upstream charter/brief aggressively and starting work before the formal `task_assignment` lands) is high-leverage for wave throughput. P3W1 delivered 8/8 PRs in ~2.5 hours partly because Lucas + Aisha both anticipated Round-2/3 charters from coordinator briefs and started implementing during the team-lead's compose window.

Killing that anticipation to eliminate the race would cost more than the race costs. So the default is to ACCEPT the race and standardize the implementer's response shape:

```
ack — task #N — already shipped at PR #M at YYYY-MM-DDTHH:MM:SSZ; no action needed
```

The implementer who finds themselves in this race posts the canonical-shape ack and idles. No retraction of the orchestrator's task_assignment is needed — it is informationally redundant with the implementer's status report, not contradictory.

### Narrow trigger — orchestrator poll before SPAWN assignments

When the orchestrator is about to send an assignment that **spawns a new implementer instance** OR **changes branch/worktree paths** (i.e., assignments where the consequences of duplicate work are non-trivial), the orchestrator MUST first verify the work is not already done:

```bash
gh pr list --repo <repo> --search "in:title <issue-keyword>" --state all --json number,state,mergedAt --limit 5
gh issue view <N> --repo <repo> --json state,closedAt
```

If the work is already shipped (PR open or merged, issue closed), the orchestrator no-ops the assignment + sends a "noted, work already done" acknowledgment instead of spawning a new instance.

Assignments to **already-active implementers in known-active scope** (e.g., follow-on tasks within an existing worktree) skip the poll — the throughput cost on those is not justified by the small noise cost.

### Severity

- Crossed-in-flight race on already-active implementer (covered by default protocol): minor noise, no feedback log entry.
- Spawn duplication (orchestrator spawns a new implementer for work already shipped): moderate — the duplicate spawn wastes context and may produce conflicting PRs. Pre-spawn poll prevents this.
- Implementer who fails to use canonical-shape ack and produces ambiguous duplicate-work messages: minor; correct-the-shape feedback in retro.

### Adoption signal

Track instance count at each retro. If the count grows materially (e.g., crossed-in-flight races trigger downstream coordination overhead that consumes >5% of wave time), revisit and consider Option 1 (full orchestrator-poll-before-every-assignment) or Option 2 (implementer-blocks-on-task-assignment) at that point.

### Why

P3W1 saw ~4 Lucas-side message-ordering races plus ≥1 analogous Aisha-side instance, all professionally handled but each costing ~30s of attention overhead. None caused duplicate work or wrong-direction shipping. The narrow trigger captures the high-consequence variant (spawn duplication) without sacrificing the wave-throughput-positive implementer-anticipates-context discipline.

<!-- Promoted from memories: feedback_no_head_in_surface_enumeration.md + feedback_spawn_brief_protocol.md (x2 consolidated sources, #944) (P3W8 retro-pickup #341, 2026-05-10) -->

### Surface enumeration

Pre-spawn briefs that enumerate a multi-file code surface (e.g., "all `actions/checkout@v` sites in this repo", "every place we read `B2_APPLICATION_KEY_ID`", "all workflows that reference `secrets.TARGET_HOST`") MUST count **occurrences, not files**. Three companion disciplines apply.

#### Where to verify — origin head_sha, not local checkout

Run `gh api repos/<owner>/<repo>/git/trees/<head_sha>?recursive=1` (or `gh api .../contents/<path>?ref=<head_sha>`) against the **wave-branch HEAD** before scoping the brief. Local main, local feature branches, and stale clones can all diverge from origin during a multi-implementer wave. Audit-deliverable issue bodies framed as "remove X / sync Y / augment Z / clean up dead-code N" routinely reference paths that don't survive the most recent migration; verifying premises at origin head_sha BEFORE spawning lets the manager scope-block + bounce to TPM rather than spend an implementer cycle discovering the gap.

If premises hold at head_sha: proceed with spawn. If premises fail (target file/path/state doesn't exist as the issue body assumes): scope-block with a comment on the issue (sha + verification command + observed result), tag TPM/scope owner, escalate via `SendMessage`. If premises *over-deliver* (issue body assumes a block that's already cleared, e.g., parent audit table already populated): proceed AND note the unblock in the spawn-request message body so the implementer doesn't redo the look-up.

#### How to count — `rg -c` per file + sum; never `| head -N` the per-file output

```bash
total=0
for f in <file-set>; do
  count=$(rg -c "<pattern>" "$f" || echo 0)  # rg -c prints nothing on no-match — keep the 0 fallback
  [ "$count" -gt 0 ] && echo "  $f: $count" && total=$((total + count))
done
echo "TOTAL: $total"
```

Then a sanity-check pass that reads the un-truncated rg output:

```bash
rg -n "<pattern>" <files>  # full output, scan for missed sites
```

**Do NOT pipe per-file rg output through `head -N` before tallying.** Truncation silently drops sites and produces an under-counted brief that looks complete because the visible output is plausible. The under-count would ship as a scope leak into a follow-up PR if the implementer used the brief as a checklist.

When a consolidated cross-repo audit deliverable exists (TPM-style per-repo target-version table at a parent meta-issue), **cite the audit URL in the spawn brief and treat the audit as authoritative; the manager brief is advisory**. Implementers consult the audit + run their own worktree-side scan via the Hook 15 librarian invocation. The manager-brief enumeration figure is explicitly NOT a checklist cap; if both manager-brief and audit surface counts disagree, the implementer's own worktree scan resolves the conflict and the manager re-runs the enumeration before the next spawn.

#### What caveats apply — per-named-caveat applicability sweep

For every named caveat in the parent audit / charter / kickoff (e.g., `upload-artifact@v4` same-name failure, `actions/github-script@v7` breaking-change, deprecated-flag warnings, version-pin requirements), the manager explicitly rules **applicable vs. non-applicable for THIS repo's surface** before sending the brief. Do not pass caveats through as "be careful" — verify them against the enumerated surface and resolve the ruling in the brief body. Implementer's PR body should mirror the manager's verification table + caveat ruling so reviewers can audit the chain.

#### Severity if violated

- Pre-spawn brief enumerates by file count instead of occurrence count, or pipes per-file grep through `head` before tallying: **moderate** (the under-count ships as scope leak if implementer treats the brief as a checklist; saved only by implementer-side discipline overriding flawed manager input).
- Manager spawns an implementer to "discover the gap" on an audit-deliverable issue whose premises don't hold at head_sha: **moderate** (wastes implementer context; correct response was scope-block + TPM bounce).
- Caveat passed through as "be careful" without applicability ruling: **minor**, **moderate** if the unapplied caveat masks a real breaking-change site.
- Implementer-side override catches a flawed manager brief (positive event): logged in retro as discipline working as designed, no penalty.

#### Worked examples (P3W8)

- **deploy#280 spawn-brief** — Bereket's initial enumeration counted files (14 of 15 workflow files contain `actions/checkout@v4`) instead of occurrences (30 actual sites — `terraform.yml` has 8 alone). `actions/github-script@v7` sample also miscounted (saw lines 82, 130; missed line 174 because `head -10` truncated the per-file output). Aisha's independent worktree-side scan via Hook 15 librarian + `grep -nE` hit all 37 sites and surfaced the gap; Wanjiku's #309 freshness-pass audit independently confirmed `30 + 3 + 4 = 37` across 15 files 2-3 hours earlier and was the canonical cross-reference.
- **Marcia / landing-page#88** — verified 6 call sites at wave-branch HEAD, ruled `upload-artifact` same-name caveat non-applicable (single call site `playwright-report` in single job). Per-named-caveat applicability sweep delivered as designed.
- **data-acquisition#43 + #44 (Dilara)** — issue body said "remove dead-code child hook copies" / "augment stale child copy"; origin verification at head_sha returned 0 entries under `.claude/hooks/`. Pre-spawn head_sha check let the manager re-scope to ADR + parent-side fixture instead of spawning an implementer to discover the gap.
- **isnad-graph hook surface (Anya, W8)** — 4 of 5 hook files 404 at origin; 4 W8 issues scope-blocked pre-spawn instead of consuming implementer time.
- **Maeve / parent#309 unblock** — pre-spawn read of parent#309's existing audit table revealed the block had already cleared; spawned with the unblock noted in the brief body. Positive expression of the same head_sha discipline (catch the *unblock* signal too, not just the *block*).

#### Cross-references

- Companion to `pull-requests.md § Origin > Local Clone for "Still-Has-X" File-Content Claims` — reviewer-class artifact-truth principle; this section is the manager-class pre-spawn analogue.
- Companion to `pull-requests.md § Trust the Artifact, Not the Framing` — same primitive at the PR review layer ("read the diff at HEAD, not the PR-body framing"); this section is the spawn-brief layer ("enumerate the surface at HEAD, not the issue-body framing").
- Source memories: `feedback_no_head_in_surface_enumeration.md` (how to count), `feedback_spawn_brief_protocol.md` (where to verify), `feedback_spawn_brief_protocol.md` (per-caveat applicability).

## Orchestrator State-Correction Discipline — One Aligned Instruction, Never a Serial Toggle <!-- promotion-target: none -->

When correcting a spawned agent's course mid-task (close vs keep-open a PR, reopen, change a branch/label disposition), the orchestrator MUST first re-read the agent's **current** state at the artifact, then issue **one** instruction that is internally consistent with that state and requires no further reversal — explicitly voiding any prior contradictory instruction. NEVER issue serial, contradictory course-corrections (close → keep-open → reopen) that cross the agent's in-flight actions.

### Why

This is **architecturally distinct** from § Pre-Spawn State Check + Crossed-Message Race Protocol (which governs the *message-bus* delivery-order race — an implementer receives "do X" after already shipping X). Here the thrash is **orchestrator-self-generated**: the orchestrator emits a stream of contradictory instructions faster than the agent can act on any one, and each new instruction crosses the agent's in-flight response to the previous one. The remedy is not the canonical-ack shape (that resolves the bus race); it is **don't generate the contradictory stream in the first place**.

### How to apply

1. Before sending a course-correction, re-read the agent's current artifact state (`gh pr view`, `gh issue view`, branch state) — per `state-claims.md § Refresh State Before Acting`.
2. Decide the **single** end-state you want, then send **one** instruction that reaches it from where the agent actually is now — not from where you last remembered it.
3. Explicitly void priors in that one message: "Disregard my earlier close/reopen messages — current desired end state is X; do only X."
4. If the agent has actions in flight, wait for them to land and re-read before instructing — do not pipeline corrections.

### Severity if violated

- One contradictory pair, quickly reconciled: **minor** — round-trip noise.
- A serial toggle stream that crosses multiple in-flight actions (3+ round-trips of churn): **moderate** — wastes the agent's context, risks leaving the artifact in an unintended state, and is hard for the agent to disentangle.

### Origin

P4W4 #1001↔#1003 vehicle thrash (2026-06-12): the orchestrator issued contradictory serial close/keep-open/reopen instructions on #1001 that crossed Ingrid's in-flight actions (~6 round-trips), resolved only by reading the actual current state and issuing one aligned instruction voiding priors. Owner-approved at the P4W4 retro.

### Cross-references

- `state-claims.md § Refresh State Before Acting` — the read-current-state-before-acting primitive this rule builds on (action-class).
- § Pre-Spawn State Check + Crossed-Message Race Protocol — the *bus-race* sibling (distinct cause; distinct remedy).

<!-- Promoted from memory: feedback_child_repo_implementer_rule.md (P3W5 retro 2026-05-06) -->

## Child-Repo Implementer Rule + Spawn-Brief Verification (Mandatory) <!-- promotion-target: hook -->

When spawning an implementer for a PR or feature in a child repo, the implementer's identity (`user.name` + `user.email`) MUST come from **that child repo's** team roster (`<child>/.claude/team/roster/` and `<child>/.claude/team/roster.json`) — NOT from the parent's org-level coordination team and NOT from a sibling repo's roster.

### Why

Hook 5 (`validate_commit_identity`) scans the working repo's `roster.json` and BLOCKS commits whose `user.name` isn't a roster member. Per the enforcement-hierarchy principle (hook > skill > charter), the hook is the binding source of truth — a wrong-roster spawn will fail at first commit, costing a respawn cycle. Each child repo has its own simulated team with its own role fit; cross-roster authorship is a category error the hook catches.

### Orchestrator-side spawn-brief checklist

Before authoring an implementer spawn brief for a child-repo issue:

1. **Determine working repo for the change.** Read the issue body. Note that **issue location ≠ working repo** (e.g., a `noorinalabs-deploy` issue body may say the changes go in `noorinalabs-landing-page`). The repo that hosts the FILES the implementer will edit is the working repo.
2. **Read that repo's roster.** `cat <working-repo>/.claude/team/roster.json` or list `<working-repo>/.claude/team/roster/`.
3. **Pick a roster member with role fit** for the change class (frontend Dockerfile → frontend engineer; CI workflow → devops/platform engineer; security/CVE → security engineer; observability config → observability engineer; etc.).
4. **In the spawn brief, set the implementer's identity to that roster member's `user.name` + `user.email`.**
5. **Reviewer assignment is a separate decision.** Cross-team reviewer is OK (e.g., parent / sibling-team reviewer reading a child-repo PR). Don't conflate REVIEWER class with IMPLEMENTER class — see § Role-Class-Specific Boundaries elsewhere in charter for the distinction.

### Per-repo implementer pools (verify at spawn time — these snapshots may drift)

- `noorinalabs-deploy`: Lucas Ferreira, Aisha Idrissi, Bereket Tadesse, Weronika Zielinska, Nino Kavtaradze, others
- `noorinalabs-isnad-graph`: Idris Yusuf, Linh Pham, Anya Kowalczyk, Mateo Salazar, others
- `noorinalabs-user-service`: Mateo Salazar, Anya Kowalczyk, others
- `noorinalabs-landing-page`: Anika Diop-Sarr, Cédric Novák, Kofi Mensah-Williams, Marcia Vasquez-Paredes, Nazia Rahman
- `noorinalabs-main` (parent): Wanjiku Mwangi (TPM), Aino Virtanen (Standards), Santiago Ferreira (RC), Nadia Khoury (PD)
- `noorinalabs-design-system`, `noorinalabs-data-acquisition`, `noorinalabs-isnad-ingest-platform`: per-repo rosters

The verbatim canonical roster lives in each child repo's `.claude/team/roster.json` — read that at spawn time, not this snapshot.

### Exceptions

- **User explicitly directs otherwise** in a given session ("have Lucas do the landing-page work" overrides). Hook would still block; user would need to register the agent in the target roster first or accept the block.
- **Child repo has no `.claude/team/` defined yet** — check recent git history for de-facto implementer (`git log --format='%an' -- <path>`) and match, or ask the user before defaulting.

### Severity if violated

Wrong-roster spawn (hook-blocked at first commit, respawn required): minor — auto-corrected by Hook 5; cost is one wasted Aino-spawn. Wrong-roster spawn that bypasses Hook 5 (e.g., committed via a different mechanism that escapes the hook): moderate — the child-repo's role-fit signal is corrupted in git history.

### Failure modes seen and what blocked them

| Date | Surface | What went wrong | What blocked it |
|---|---|---|---|
| 2026-04-22 | child-repo#139 prereqs | Deferred-under-misread of user intent | Owner correction next turn |
| 2026-05-03 | P3W3 deploy#242 spawn brief | Spawned Lucas Ferreira (deploy roster) for landing-page work; conflated reviewer-class permission with implementer-class | Hook 5 blocked Lucas-242's first commit; Lucas-242 surfaced charter Pattern B catch (verify-vs-artifact: roster.json) and recommended Kofi from landing-page roster |

<!-- Promoted from memory: (none — this section codifies retro proposal #4 sub-section under existing parent rule, ratified at P3W10 retro via PR #441 owner-decided 2026-05-16) -->

### Parent-Orchestrator Implementer Declarations Are Advisory

When a cross-repo meta-issue authored by the parent orchestrator declares **per-child-issue implementers** (e.g., "Linh implements isnad-graph#812, Lucas implements deploy#159"), those declarations are **ADVISORY**. The child-repo manager is the canonical authority for who actually implements a child-repo PR.

#### Why

22 substitutions across 65 W10 PRs (**34%**) showed that parent-declared implementers were systematically overridden downstream. The substitution wasn't an error — child managers correctly applied local roster knowledge (current workload, recent role fit, in-flight cluster cohesion) that the parent orchestrator does not have at meta-issue authoring time. The cost of declaring anyway was twofold:

1. **Retro-time trust-matrix-misattribution risk** — a retro that reads declared-vs-actual without the bulk-acknowledgment context would credit the wrong agent.
2. **Wasted orchestrator effort** — composing per-issue declarations that get swapped out 34% of the time is signal-to-noise loss.

#### How to apply

- At **meta-issue authoring time**, parent orchestrators MAY state SUGGESTED implementers as advisory hints OR omit per-issue implementer names entirely. Both are acceptable.
- **Child managers** assign canonical implementers via spawn briefs in their own child-repo session, applying local roster + workload + role-fit knowledge.
- **Trust-matrix attribution at retro time** follows the **commit identity** (who actually authored the merged commits per `git log --format='%an' <merge-base>..<wave-tip>`), NOT the meta-issue declaration. Retros that compare declared-vs-actual without the bulk-acknowledgment of this rule will misattribute.

#### Relationship to the parent § Child-Repo Implementer Rule

The parent section above governs **WHICH ROSTER** an implementer must come from: the working-repo's roster, Hook 5 enforced. This sub-section governs **WHO HAS AUTHORITY** to make the per-issue assignment within that roster: the child manager, not the parent orchestrator.

The two rules are complementary:
- Parent rule (hook-enforced): implementer's `user.name` must be in working-repo `roster.json`.
- This sub-section (advisory): WHICH specific roster member the child manager picks is the child manager's call, not the parent orchestrator's.

#### Severity if violated

- **Parent orchestrator over-specifying** (declaring per-issue implementers in a meta-issue): **minor** — wasted effort, no hook block, no downstream coupling.
- **Parent orchestrator demanding child manager honor advisory declarations** (e.g., re-spawning the child agent to "use the declared implementer instead"): **moderate** — couples teams across the parent/child boundary, defeats the local-knowledge advantage that produced the 34% substitution rate, and corrupts the working-repo's role-fit signal.

#### Provenance

P3W10 retro PR #441 § Proposed Process Changes #4. 22-substitution evidence (34% of 65 W10 PRs). Owner-adopted 2026-05-16 (PR #444). Sibling memory: `feedback_child_repo_implementer_rule.md` (which the parent § Child-Repo Implementer Rule + Spawn-Brief Verification already supersedes for roster-source rules; this sub-section adds the authority-source clarification).

