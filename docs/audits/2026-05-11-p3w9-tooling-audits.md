# P3W9 Tooling Audits — 2026-05-11

Three tooling-coverage audits filed during the P3W6-W9 backlog. Each produces concrete per-repo data and a recommendations summary; non-trivial recommendations are tracked in follow-up issues filed pre-merge.

**Auditor:** Wanjiku Mwangi (TPM)
**Date:** 2026-05-11
**Wave:** P3W9
**Closes:** #159, #221, #222
**Follow-ups filed:** #401 (skill protocol), #402 (auto-close propagation), #403 (branch protection enablement)

---

## Audit 1 — Auto-PR creation faithfulness to human PR protocol (closes #159)

### Question

Does `/promotion-audit`'s SKILL.md step 4 — and the broader auto-PR creation pattern used by the orchestrator — match the human PR protocol the team actually uses (commit identity, labels, project-board add, PR body template, reviewer assignment)?

### Methodology

1. Read `.claude/skills/promotion-audit/SKILL.md` step 4 ("Produce artifacts") prose at wave-9 HEAD via worktree file.
2. Surveyed 5 recently-merged auto-created PRs in `noorinalabs-main` via `gh pr view <N> --json author,labels,projectItems`.
3. Compared label sets and board membership to human-filed DECIDE-tier issues (#395, #393, #317, #292, #262).
4. Cross-referenced against charter requirements: `commits.md § Identity Table`, `pull-requests.md § PR Template`, CLAUDE.md § Bug Report Workflow (project-board pattern).

### Findings

**Auto-PR sample (5 PRs, all `author=parametrization`):**

| PR | Title (truncated) | Labels | Project items |
|----|------|--------|---------------|
| #400 | merge(wave-9→main): Batch B+C+D propagation | `[]` | `[]` |
| #389 | merge(wave-9→main): hook+charter+repo-hygiene batch | `[]` | `[]` |
| #382 | merge(wave-9→main): wave-skill polish batch | `[]` | `[]` |
| #379 | merge(wave-9→main): parser-fixture batch | `[]` | `[]` |
| #376 | merge(wave-9→main): hook-hygiene fixes | `[]` | `[]` |

**Human-filed comparison (DECIDE-style issues):** #395 and #393 both carry `[tech-debt, p3-wave-9]` and appear on Project 2.

**`/promotion-audit` SKILL.md step 4 at HEAD (line 65):**

> Apply `templates/hook-draft.md` to generate an issue title + body. Use `gh issue create --label "enhancement" --body-file` (NOT `--body` — avoids the `|` hook bug #146).

Confirmed gaps vs charter:

1. **Commit identity** — step 4 prose does NOT mention the charter-mandated `-c user.name="..." -c user.email="parametrization+FirstName.LastName@gmail.com"` flags. A bare `git commit` would fail the commit-identity hook.
2. **Wave label** — auto-PRs land with `labels=[]`. Human-filed equivalents carry the current wave label (`p3-wave-9`).
3. **Project board add** — auto-PRs land with `projectItems=[]`. Charter convention: `gh project item-add 2 --owner noorinalabs --url <pr_url>` after PR creation.
4. **PR body template** — step 4 prose does not reference the charter `pull-requests.md § PR Template` shape (Summary / Implementation / Test plan / Closes #N).
5. **DECIDE-tier issues** — step 4 only specifies `--label "enhancement"`. Human-filed equivalents carry `enhancement` (or `tech-debt`) AND the current wave label, AND appear on the board.

### Recommendations

Filed as **#401** (P3W10 candidate): add a thin helper `open_auto_promotion_pr()` (or extend SKILL.md step 4 prose) encoding the full protocol — commit-identity flags, wave label, project-board add, PR body template, DECIDE-tier label parity. Optional dry-run mode so the first real AUTO can be verified before landing.

---

## Audit 2 — Auto-close-issues workflow coverage across 8 org repos (closes #221)

### Question

Which of the 8 noorinalabs org repos have an `auto-close-issues` GitHub Actions workflow that fires on wave-branch PR merges?

### Methodology

For each repo: `gh api repos/noorinalabs/<repo>/contents/.github/workflows --jq '.[].name'` filtered to workflows matching `(?i)close|cleanup|wave|auto`.

For positive matches: fetched the workflow source via `gh api .../contents/.github/workflows/<file>` and inspected the trigger / regex / action.

### Findings

| Repo | Has auto-close workflow? | File | Evidence |
|------|-------------------------|------|----------|
| noorinalabs-main | NO | — | no matching workflows in `.github/workflows/` |
| noorinalabs-isnad-graph | **YES** | `auto-close-issues.yml` | confirmed file present |
| noorinalabs-user-service | NO | — | no matching workflows |
| noorinalabs-deploy | NO | — | no matching workflows |
| noorinalabs-design-system | NO | — | no matching workflows |
| noorinalabs-landing-page | NO | — | no matching workflows |
| noorinalabs-data-acquisition | NO | — | no matching workflows |
| noorinalabs-isnad-ingest-platform | NO | — | no matching workflows (and no `.github/` at all) |

**Coverage rate: 1 of 8 (12.5%).**

### isnad-graph workflow (canonical reference)

`noorinalabs-isnad-graph/.github/workflows/auto-close-issues.yml`:

- **Trigger:** `pull_request.types=[closed]` with `if: github.event.pull_request.merged == true`
- **Permissions:** `issues: write`
- **Body-parsing regex:** `/[Cc]loses?\s+#(\d+)/g` (matches `Closes #N`, `closes #N`, `Close #N`, `close #N` — does NOT match `Fixes #N`, `Resolves #N`, or `closes:` with colon)
- **Action:** `github.rest.issues.update({state: 'closed'})` + `github.rest.issues.createComment` with body `` `Closed by PR #${N} merged into \`${base.ref}\`.` ``

Parameter-free (uses `context.repo.*` exclusively) — a literal copy works without modification on any other repo.

### Coverage gaps in isnad-graph's workflow

- Does NOT match `Fixes #N` or `Resolves #N` trailers (only `[Cc]loses?`)
- Only parses PR BODY, not commit messages within the PR
- Closes the same issue idempotently if already closed (no-op, harmless)

### Recommendations

Filed as **#402** (P3W10 candidate): propagate `auto-close-issues.yml` to the other 7 org repos as-is (parameter-free workflow). After standardization, memory `feedback_wave_branch_issue_close.md` discipline downgrades from "explicit `gh issue close` required" to "verify worked, don't re-do" — wave-wrapup audit becomes a verify-step instead of a fix-step.

Optionally, in a separate follow-up: extend the regex to match `Fixes #N` and `Resolves #N` trailers for broader coverage.

---

## Audit 3 — Branch protection coverage across 8 org repos (closes #222)

### Question

Re-verify the issue body's claim that 7 of 8 org repos have no branch protection on `main`, and identify which one IS protected (per the issue, expected to be `noorinalabs-isnad-graph`).

### Methodology

For each repo: `gh api repos/noorinalabs/<repo>/branches/main/protection` — returns 404 if unprotected, full protection config object if protected. For the protected repo, also fetched `/rulesets` to identify ruleset coverage.

### Findings

| Repo | Branch protection | required_status_checks |
|------|-------------------|------------------------|
| noorinalabs-main | NONE (404) | — |
| noorinalabs-isnad-graph | **PRESENT** | `test`, `lint-and-typecheck`, `security-audit` (strict=true) |
| noorinalabs-user-service | NONE (404) | — |
| noorinalabs-deploy | NONE (404) | — |
| noorinalabs-design-system | NONE (404) | — |
| noorinalabs-landing-page | NONE (404) | — |
| noorinalabs-data-acquisition | NONE (404) | — |
| noorinalabs-isnad-ingest-platform | NONE (404) | — |

**Confirmed: 7 of 8 unprotected. The protected repo is `noorinalabs-isnad-graph`.**

### isnad-graph protection details

```json
{
  "required_status_checks": {
    "strict": true,
    "contexts": ["test", "lint-and-typecheck", "security-audit"]
  },
  "enforce_admins": false,
  "required_pull_request_reviews": null,
  "allow_force_pushes": false,
  "allow_deletions": false
}
```

Plus 1 ruleset: `Require review on deployments branches` (target=branch, enforcement=active).

### Gaps in isnad-graph's own coverage

The protected `contexts` list covers 3 of 8+ available CI lanes. Notably MISSING from the required-status-checks list:

- `frontend-lint-and-test`
- `hooks-lint`
- `scripts-lint`
- `lockfile-validation`

Per the issue body, the `Full stack end-to-end` failure that motivated `noorinalabs-deploy#148` would NOT be caught by isnad-graph's current required-status-checks list.

### Three currently-unguarded merge paths (per issue body, re-verified)

Hook 14 (`validate_pr_ci_status.py`) on the orchestrator side guards only the in-session `gh pr merge` path. All 8 repos remain unguarded against:

1. Manual `gh pr merge` from a human terminal outside Claude Code session
2. GitHub web UI merge button
3. `git push` direct to `main` (only blocked if `allow_force_pushes: false` — set NOWHERE except isnad-graph)

### Recommendations

Filed as **#403** (P3W10 candidate): apply per-repo branch protection config per #222 issue body. Common shape: `enforce_admins=false` (preserves Hook 14 `--admin` emergency-override semantics), `required_pull_request_reviews=null` (Hook 7 handles 2-reviewer rule with TechDebt-line semantics), `allow_force_pushes=false`, `allow_deletions=false`. Per-repo `contexts` lists need verification against each repo's actual workflow job names (mismatched contexts silently never satisfy).

For `noorinalabs-isnad-ingest-platform` (no CI workflows yet): defensive config only — 3 negative protections without required checks until CI lands.

---

## Cross-cutting observation

All three audits surface the same meta-pattern: **cross-cutting repo concerns drift to per-repo divergence absent an explicit propagation step**. The same `noorinalabs-isnad-graph` repo is the canonical exemplar for BOTH the auto-close workflow (#221) AND branch protection (#222) — and the gap in #159 is the auto-creation pattern not propagating charter conventions into the artifacts it produces.

This suggests a meta-skill or charter rule worth considering in P3W10 retro: **a periodic cross-repo consistency audit** that runs the SAME survey shape for every cross-cutting concern (CI workflows, hook registrations, label sets, branch protection, auto-close workflows, charter local copies, `.claude/team/` presence) and surfaces divergence as a single dashboard. Not filed as a follow-up yet — meta-call belongs in retro.
