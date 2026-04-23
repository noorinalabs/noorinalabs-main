# Work Delegation & Issue Management

## Delegation Flow <!-- promotion-target: skill -->
1. **Program Director decomposes cross-repo requirements** and delegates each to the appropriate team member (TPM, Release Coordinator, or Standards & Quality Lead) based on domain.
2. **The assigned team member creates GitHub Issues** in the appropriate repository with clear acceptance criteria.
3. For cross-repo work, the Program Director creates **meta-issues** in `noorinalabs-main` that link to per-repo issues.

## Issue Review Process <!-- promotion-target: none -->
Every newly created cross-repo issue receives a review pass from each of the following roles. **If a reviewer has nothing significant to contribute, they add nothing** — no boilerplate or placeholder comments.

| Reviewer | Applies to |
|----------|-----------|
| Technical Program Manager (Wanjiku) | All cross-repo issues — dependency and timeline review |
| Release Coordinator (Santiago) | Issues affecting releases, versioning, or deployment sequencing |
| Standards & Quality Lead (Aino) | Issues affecting org-wide conventions, hooks, or charter rules |

Reviews may include: dependency concerns, timeline conflicts, release impact, standards compliance, or cross-team blockers. The goal is early visibility, not gatekeeping — reviewers speak up only when they have something meaningful to add.

## Work Gate: Issues Before Implementation <!-- promotion-target: none -->
**No team member may begin implementation work or delegate it to repo teams until ALL GitHub Issues for the current initiative have been:**

1. **Created** — the full set of issues covering the initiative's requirements exists.
2. **Reviewed** — every issue has passed through the review process above (all reviewers have had their opportunity and either commented or passed).

Only after both conditions are met does the Program Director signal that implementation may begin. This ensures the entire initiative is planned, visible, and vetted before any work starts.

## Wave Planning — Project Board Is Authoritative <!-- promotion-target: skill -->

Wave and phase planning MUST begin with the full project board as the candidate pool, not with the subset of issues carrying a `p{N}-wave-{M}` label or listed in a meta-issue body.

1. **Source of truth:** project 2 (`gh project item-list 2 --owner noorinalabs`). Every open issue across all repos should appear there.
2. **Labels are post-scoping tags**, not pre-scoping filters. When a wave is planned, in-scope issues get labeled; the labels document decisions but do not bound which issues could have been considered.
3. **Meta-issue bodies document declared scope** and carry the wave narrative, but they do not replace the board audit.

**Pre-wave drift audit:** before a wave-scoping pass, verify every repo's open issues are on the board. Hook 13 (`auto_add_issue_to_board.py`) auto-adds issues created via our in-session `gh issue create` calls, but externally created issues (manual UI creation, bot PRs, cross-repo-dispatch-triggered issues) slip past. Run:

```bash
for repo in noorinalabs-main noorinalabs-isnad-graph noorinalabs-user-service \
           noorinalabs-deploy noorinalabs-design-system noorinalabs-landing-page \
           noorinalabs-data-acquisition noorinalabs-isnad-ingest-platform; do
  gh issue list --repo "noorinalabs/$repo" --state open --limit 500 --json url --jq '.[].url'
done | sort -u > /tmp/all_open.txt

gh project item-list 2 --owner noorinalabs --format json --limit 1000 \
  --jq '.items[] | select(.content.url) | .content.url' | sort -u > /tmp/board_urls.txt

comm -23 /tmp/all_open.txt /tmp/board_urls.txt
```

Any URL printed by the final `comm` is an open issue missing from the board — add it via `gh project item-add 2 --owner noorinalabs --url <url>` before scoping.

**Why:** On 2026-04-23, running this check during P2W10 execution revealed **72 of 193 open issues (37%) were missing from the board**. Those issues were invisible to any wave-planning pass that read labels or meta-issue bodies. Planning from labels alone systematically excludes work the team forgot to triage.

## Pre-Wave Checklist <!-- promotion-target: skill -->
Before any wave begins, the Manager must verify:

1. **Roster validation** — all assigned engineers exist in the org-level `roster.json`. If missing, add them before work begins. This prevents commit identity blockers.
2. **CI workflow exists** — the repo has a working CI workflow that triggers on `deployments/**` branches. If this is Wave 1 of a new repo/phase, the scaffolding issue MUST include a CI workflow. No Wave 2 work starts without CI running.
3. **Critical-path work identified** — if a task blocks others, that engineer is spawned first with priority.

## Implementation Kickoff & Issue Assignment <!-- promotion-target: none -->
Once the work gate is cleared, the Program Director delegates to the appropriate repo teams via their respective managers.

### Assignment

- Issues are assigned via a GitHub label: **`FIRSTNAME_LASTNAME`** (e.g., `NADIA_KHOURY`).
- Each team member works only on issues labeled with their name.
- **No branch may be created without an existing ticket.** The branch name must reference the issue number (per [Branching Rules](branching.md)).

### Reassignment on Termination

When a team member is fired:
1. Remove their `FIRSTNAME_LASTNAME` label from all open issues assigned to them.
2. The Program Director reassigns each issue to an appropriate person — an existing team member or a new hire.
3. The new assignee's label is applied.

### Manual Issues

Issues that require a human to complete (e.g., configuring a third-party dashboard, signing up for a service, uploading credentials) MUST have their title prefixed with `[MANUAL]`. Example: `[MANUAL] Enable GitHub Pages in design-system repo settings`.

- A `[MANUAL]` issue does **not** require a PR (though one may accompany it)
- It is closed when the human confirms the action is done (via issue comment)
- Agents may create `[MANUAL]` issues when they identify work they cannot perform

### Issue Hygiene

Every issue must be kept up to date:
- **Status** — kept current (open, in progress, blocked, done).
- **Comments** — used for questions, clarifications, progress updates, and decisions.
- **Close condition** — issues are closed **only** when the corresponding work is complete and verified. Do not close prematurely. For `[MANUAL]` issues, the human confirms completion via comment.

## Comment Format <!-- promotion-target: none -->
All issue comments MUST follow this format:

```
Requestor: Firstname.Lastname
Requestee: Firstname.Lastname
RequestOrReplied: Request

<actual comment body>
```

- **Requestor** = the person writing the comment.
- **Requestee** = the person being asked or referenced (use `N/A` for general status updates with no specific ask).
- **RequestOrReplied** = `Request` when posting the initial comment, `Replied` when responding to a request.

## Reply Protocol <!-- promotion-target: none -->
When a team member is tagged as **Requestee** on a comment with `RequestOrReplied: Request`, they **must** respond with a new comment on the same issue using this format:

```
Requestor: Firstname.Lastname   <- (was the original Requestee)
Requestee: Firstname.Lastname   <- (was the original Requestor)
RequestOrReplied: Replied

<reply body>
```

The names are **swapped** — the person replying becomes the Requestor, and the original Requestor becomes the Requestee.

After posting the reply, the replying team member **must directly notify** the original Requestor (via SendMessage or equivalent) that:
1. A reply has been posted on the issue.
2. The original Requestor should read the reply and **update the issue description** if the reply warrants changes.

## Ticket Update Rules Based on Ownership <!-- promotion-target: none -->
The **ticket owner** is the team member whose `FIRSTNAME_LASTNAME` label is on the issue.

- **Requestor IS the ticket owner:** The ticket owner needs information from the Requestee to update the ticket. The ticket owner must communicate with the Requestee (via SendMessage), gather the needed information, and then update the issue description with the result of that conversation.

- **Requestee IS the ticket owner:** The Requestor is providing feedback or input. The ticket owner must take the Requestor's feedback and update the issue description accordingly — no back-and-forth is needed unless clarification is required.

## Escalation & Cross-Team Clarification <!-- promotion-target: skill -->
When a ticket needs clarification or feedback from another team member:
1. Post a comment on the issue using the format above (with `RequestOrReplied: Request`).
2. Notify the Program Director if needed.
3. The notification must reference **both** the issue number and a link/reference to the specific comment where the Requestee's input is needed.
