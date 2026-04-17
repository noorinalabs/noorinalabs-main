---
name: wave-kickoff
description: Automated wave planning — branch creation, label management, issue labeling, kickoff comments, and execution plan
args: team_name, Phase number, Wave number
---

Automate the wave kickoff process for the `{team_name}` team.

## Instructions

### 1. Create the deployments branch

```bash
git fetch origin
git checkout main && git pull origin main
git checkout -b deployments/phase{N}/wave-{M}
git push -u origin deployments/phase{N}/wave-{M}
```

If the branch already exists, check it out and pull latest instead.

### 2. Create wave label

Check if label `p{N}-wave-{M}` exists:

```bash
gh label list --search "p{N}-wave-{M}"
```

If missing, create it:

```bash
gh label create "p{N}-wave-{M}" --description "Phase {N} Wave {M}" --color "8B5CF6"
```

### 3. Pre-wave auth/scope audit

Verify the gh token has the scopes needed for this wave's operations. GitHub periodically hardens scope enforcement (e.g., Projects v2 requires the explicit `project` write scope; classic-Projects API deprecation). A missing scope mid-wave consumes orchestrator + user time chasing OAuth flows.

```bash
gh api -i user 2>&1 | grep -i "x-oauth-scopes"
```

Required scopes (baseline for all waves):
- `repo` — issues, PRs, comments, code
- `read:org` — roster / label lookups
- `project` — adding issues/PRs to the board (`gh project item-add`)
- `workflow` — editing `.github/workflows/*` files
- `gist`, `admin:public_key` — retained from prior grants

If any required scope is missing, instruct the user:
```
gh auth refresh -h github.com -s {missing_scope}
```
Wait for confirmation that scopes are updated before proceeding. Do NOT begin wave assignment with known-missing scopes.

**Why:** Phase 2 Wave 8 surfaced the Projects v2 scope gap mid-retro while trying to add PR #122 to the board. Fixing it interactively consumed ~30 minutes. Catching this at wave-kickoff prevents mid-wave interruptions.

### 4. Pre-wave CI triage

Before assigning issues, verify CI health across all repos in the wave scope:

```bash
gh run list --repo noorinalabs/{repo} --branch main --limit 1 --json conclusion
```

For each repo:
- If `conclusion` is `"success"`, mark it green.
- If `conclusion` is `"failure"` or missing, create a GitHub issue in that repo:
  ```bash
  gh issue create --repo noorinalabs/{repo} --title "CI red on main — triage before p{N}-wave-{M}" \
    --label "bug" --label "p{N}-wave-{M}" \
    --body "CI is failing on main. This must be triaged before wave work begins on this repo."
  ```
- Present a summary table to the user:
  | Repo | CI Status | Issue |
  |------|-----------|-------|
  | `noorinalabs-isnad-graph` | pass / **FAIL** | — / #NNN |

Flag repos with known-red CI so engineers are not confused by pre-existing failures.

### 5. Cross-reference wave issues against recent merges

Before posting kickoff comments, check if any wave issues were already resolved:

```bash
gh pr list --repo noorinalabs/{repo} --state merged --limit 20 --json number,title,body
```

For each merged PR:
1. Extract `Closes #N`, `Fixes #N`, or `Resolves #N` references from the PR body and title.
2. Compare those issue numbers against the wave issue list.
3. If a match is found, flag it to the user:
   ```
   ⚠ Issue #{N} ("{title}") may already be resolved by PR #{M} ("{pr_title}").
   Verify before assigning — remove from wave if confirmed fixed.
   ```

Wait for user confirmation before proceeding with assignment. Remove any confirmed-resolved issues from the wave list.

### 6. Collect issue list and assignments

Prompt the user for:
- List of issue numbers for this wave
- Assignee for each issue (FIRSTNAME_LASTNAME label)
- Peer review pairings (reviewer for each engineer)

Validate all assignee labels exist before proceeding:

```bash
gh label list --search "FIRSTNAME"
```

Create any missing labels before applying.

### 7. Label all issues

For each issue, apply the wave label and assignee label:

```bash
gh issue edit {NUMBER} --add-label "p{N}-wave-{M}" --add-label "{FIRSTNAME_LASTNAME}"
```

### 8. Post kickoff comments

Post a kickoff comment on each issue using charter format:

```
Requestor: Fatima.Okonkwo
Requestee: {Assignee.Name}
RequestOrReplied: Request

**Wave {M} Kickoff — Phase {N}**

This issue is assigned to you for p{N}-wave-{M}.
- Peer reviewer: {reviewer name}
- Branch from: `deployments/phase{N}/wave-{M}`
- Branch naming: `{FirstInitial}.{LastName}/{IIII}-{issue-slug}`
- Priority: {hotfix|security|bug|feature} (per charter § Wave Planning & Priority)

Please begin implementation.
```

### 9. Ontology librarian lookup per agent (MANDATORY)

**Before spawning any agent**, the orchestrator MUST run `/ontology-librarian {topic}` for each agent's work area and **include the output in the agent's spawn prompt**. Do NOT tell agents to "run it themselves" — the orchestrator runs it and bakes the context in.

For each agent in the wave:
1. Identify the repos and code areas they'll modify
2. Run the librarian with a descriptive query:
   ```
   /ontology-librarian {repo} {area being modified}
   ```
   Examples:
   - `/ontology-librarian isnad-graph frontend auth and verification`
   - `/ontology-librarian user-service Dockerfile and dependencies`
   - `/ontology-librarian main hooks and CI`
3. Include the librarian's output (entities, services, conventions, stale warnings) in the agent's spawn prompt under a `## Ontology Context` section
4. If the librarian flags stale references, note them so the agent treats that information with caution

**Why:** In P2W3, running the librarian before spawning agents identified 10 stale issues (middleware extracted to user-service) — saving significant wasted effort. In P2W2, skipping this step led to 3 already-resolved issues being assigned.

**Enforcement:** The `validate_wave_context.py` PreToolUse hook fires on Agent spawns. Agents spawned without ontology context in their prompt will trigger a warning.

### 10. Output execution plan

Generate and display a structured execution plan with:
- **Priority ordering:** hotfixes first, then security fixes, then bugs, then features (per charter § Wave Planning & Priority)
- **Issue table:** number, title, assignee, reviewer, priority tier
- **Dependencies:** any cross-PR dependencies identified
- **Estimated parallelism:** which issues can run concurrently

### 11. Report

Present the full plan to the user. Do NOT begin implementation until the user approves.

## What remains manual

- User must approve the execution plan before implementation starts
- User decides which issues to include in the wave
- Cross-team dependency resolution still requires lead coordination
