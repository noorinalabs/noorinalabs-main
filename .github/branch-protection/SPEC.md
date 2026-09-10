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
- **`required_status_checks` rule — OMITTED on this repo.**
  `noorinalabs-main`'s `ci.yml` is **path-filtered** (it triggers only on
  changes under `.claude/hooks/**`, `.claude/lib/**`, `.claude/skills/**`,
  `.github/workflows/ci.yml`, `.pre-commit-config.yaml`, `pyproject.toml`). Its
  gate jobs (`Ruff lint`, `Ruff format check`, `Mypy type check`, `Smoke test …`,
  `Pytest …`, `Pre-commit ⇄ CI sync-drift gate`) therefore **do not run** on a
  PR/push that touches only other paths — e.g. the orchestrator's routine
  `cross-repo-status.json` and `ontology/` updates. Hard-requiring those job
  contexts would **deadlock** any non-matching PR forever waiting on a check
  that never reports. So no status check is required at the ruleset layer. Note
  the GitHub REST API **rejects** a `required_status_checks` rule carrying an
  empty `required_status_checks` array (HTTP 422: "Expected at least 1 elements,
  got 0"), so the rule is **omitted entirely** rather than included-with-`[]`.
  This is the same canonical choice as `noorinalabs-deploy` (whose CI is also
  path-filtered). The ruleset still enforces **PR-only + no force-push /
  branch-delete** on `main`; the per-PR
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

**Rename guard:** `apply-ruleset.sh` looks up an existing ruleset **by `name`**
(`select(.name == "$RULESET_NAME")`). If `ruleset-main.json`'s `name` is ever
changed (as it was on `#1464`, to drop the "green CI" claim this repo's ruleset
does not enforce), the **live** ruleset must be renamed to match FIRST — via a
direct `gh api -X PUT repos/<repo>/rulesets/<id>` carrying only the name change
— before running this script for real. Renaming the payload first and running
the (non-dry) script second makes the by-name lookup find nothing and **POST a
duplicate ruleset** rather than updating the existing one. `DRY_RUN=1` is safe
either way (it never writes) but will itself report "would CREATE" until the
live rename lands, which is a stale-name artifact, not a sign the script is
broken.

**Status:** this repo's live rename landed 2026-09-10T10:34:52-04:00
(ruleset `17139856`, owner-executed); `DRY_RUN=1` now correctly reports
"would UPDATE ruleset 17139856". `noorinalabs-deploy`'s matching rename
(ruleset `17139848`) is still outstanding, tracked on `#1464`.

```bash
# From a window with NO in-flight default-branch merge (post-wave-wrapup):
.github/branch-protection/apply-ruleset.sh            # create or update
DRY_RUN=1 .github/branch-protection/apply-ruleset.sh  # preview only

# Then read-back-verify the detail (contexts + bypass actor):
gh api repos/noorinalabs/noorinalabs-main/rulesets \
  --jq '.[] | select(.name|startswith("Protect main")) | .id'
gh api repos/noorinalabs/noorinalabs-main/rulesets/<id>
```

`#322` closed 2026-06-02 — the rollout is complete; all 8 default branches
carry a ruleset (`ci-gates.md` § Application status has the per-repo id
table). The remaining items — the push-side bypass-count gap and the
`noorinalabs-deploy` ruleset rename that mirrors this repo's — are tracked on
**`#1464`**, not `#322`.
