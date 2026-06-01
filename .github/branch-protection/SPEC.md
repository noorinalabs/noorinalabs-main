# Branch Protection — noorinalabs-main (P3 end-state #4, #322)

Phase-3 end-state criterion #4 (`noorinalabs-main#322`): **CI failures block all
merges** on every repo's default branch, org-wide — enforced server-side by
GitHub, not only by the Hook 4 comment-gate. This directory carries the
canonical ruleset for **this parent repo's** `main`.

| File | Purpose |
|------|---------|
| `ruleset-main.json` | The repository ruleset payload (GitHub REST `/rulesets`). |
| `apply-ruleset.sh`  | Owner/admin-gated apply + read-back-verify. Idempotent (create-or-update). |
| `SPEC.md`           | This document — the shape and the why. |

This is `noorinalabs-main`'s own adoption of the parent-canonical spec
(charter `pull-requests.md` § *Org-Wide Branch Protection + Admin-Merge
Exceptions*), modeled on the W13 live pilot
(`noorinalabs-data-acquisition`, ruleset id `17091263`) and the W14 canonical
pilot (`noorinalabs-user-service`).

## The ruleset shape (and why)

A **repository ruleset** targeting `~DEFAULT_BRANCH`, `enforcement: active`:

- **`pull_request` with `required_approving_review_count: 0`** — the load-bearing
  decision. GitHub's "require approvals" counts **formal** GitHub PR reviews,
  which our team structurally cannot produce: the `gh` auth principal IS the PR
  author (`parametrization`), so a formal self-approval **422s**, and our review
  discipline runs on **issue-comment verdicts** validated by Hook 4
  (`validate_pr_review`), not formal reviews. A naive "require 1 approval" rule
  would **deadlock every merge**. Reviewer-count enforcement stays with Hook 4.
- **`required_status_checks` (strict) — EMPTY required set on this repo.**
  `noorinalabs-main`'s `ci.yml` is **path-filtered** (it triggers only on
  changes under `.claude/hooks/**`, `.claude/lib/**`, `.claude/skills/**`,
  `.github/workflows/ci.yml`, `.pre-commit-config.yaml`, `pyproject.toml`). Its
  gate jobs (`Ruff lint`, `Ruff format check`, `Mypy type check`, `Smoke test …`,
  `Pytest …`, `Pre-commit ⇄ CI sync-drift gate`) therefore **do not run** on a
  PR/push that touches only other paths — e.g. the orchestrator's routine
  `cross-repo-status.json` and `ontology/` updates. Hard-requiring those job
  contexts would **deadlock** any non-matching PR forever waiting on a check
  that never reports. So the required set is **EMPTY**, the same canonical choice
  as `noorinalabs-deploy` (whose CI is also path-filtered). The ruleset still
  enforces **PR-only + no force-push / branch-delete** on `main`; the per-PR
  green-CI gate is carried by **Hook 14** (`validate_pr_ci_status`), which blocks
  merge-on-red for the checks that **did** run.

  If `noorinalabs-main`'s CI ever becomes unconditional (no `paths:` filter), add
  the job-**name** contexts to `ruleset-main.json` and **re-confirm at apply
  time** against live check-runs:
  `gh api repos/<repo>/commits/<default-sha>/check-runs --jq '.check_runs[].name'`.
- **`deletion` + `non_fast_forward`** — no force-push / branch-delete on `main`.
- **`bypass_actors`: Repository-admin (`actor_id: 5`, `bypass_mode: always`)** —
  this repo is special: the orchestrator pushes `cross-repo-status.json` and
  `ontology/` updates **directly to `main` via the contents API**, and runs
  `--admin` wave→main wrapup merges. The admin always-bypass keeps both working
  (the `parametrization` principal holds repo-admin). The GitHub-side bypass is
  mirrored on the operator side by the hook-validated `ADMIN_MERGE_EXCEPTION`
  gate (`validate_pr_ci_status`), which **audits** every `--admin` merge to the
  Annunaki trail — defense in depth: the ruleset covers UI/external/batch-loop
  merges, the hook covers `gh pr merge` and names the exceptions.

## How to apply (owner)

```bash
# From a window with NO in-flight default-branch merge (post-wave-wrapup):
.github/branch-protection/apply-ruleset.sh            # create or update
DRY_RUN=1 .github/branch-protection/apply-ruleset.sh  # preview only

# Then read-back-verify the detail (contexts + bypass actor):
gh api repos/noorinalabs/noorinalabs-main/rulesets \
  --jq '.[] | select(.name|startswith("Protect main")) | .id'
gh api repos/noorinalabs/noorinalabs-main/rulesets/<id>
```

`#322` stays **OPEN** as the org-wide rollout tracker until all 8 default
branches carry the protection and the phase review closes the criterion.
