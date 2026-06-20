---
name: feedback_pip_audit_strict_advisory_db_drift
description: "pip-audit --strict CI gate fails on a pre-existing locked dep when a new advisory publishes AFTER main's last green run; not the PR's bug — bump the dep in the shared lockfile, don't fold into a scoped PR."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 080813cd-f3b8-434d-974c-badf58620c96
---

A `pip-audit --strict` CI job (e.g. ingest-platform `ci.yml` `security-audit`) audits the EXPORTED frozen lockfile against the **live** advisory DB. It can go red on a feature branch while still green on `main` even when `uv.lock` is byte-identical — because a new advisory published between main's last CI run and the branch's run. The failing package is often a build/dev-tool transitive (e.g. `pip` itself enters via `pip-audit`'s own deps), NOT a runtime dependency.

P4W2 main#139 / ingest-platform PR #62 (2026-06-10): `security-audit` red on `pip` 26.1.1 PYSEC-2026-196 (console_scripts path-sanitization); green on main (lock last touched 2026-05-31, predates the advisory). `uv.lock` unchanged by the PR. Verified `uv lock --upgrade-package pip` → 26.1.2 → "No known vulnerabilities found".

**Why:** A scoped PR (test-only, docs-only) must not silently absorb an unrelated shared-lockfile bump — it muddies the diff, and the bump hits EVERY open PR in the repo, so it's a release-coordinator/owner-class dependency-hygiene call, not implementer scope. Same family as [[feedback_artifact_gate_non_blocking]] and [[feedback_runtime_gate_scoping]].

**How to apply:**
1. Before claiming a `security-audit`/`pip-audit` failure is "your bug", check `git diff origin/main...HEAD -- uv.lock` (empty ⇒ not introduced by you) AND `gh api .../commits/main/check-runs` (green-on-main ⇒ advisory-DB drift, pre-existing).
2. Reproduce: `uv export --no-hashes --frozen --no-emit-project > /tmp/req.txt && uv run pip-audit --strict --desc -r /tmp/req.txt`.
3. Confirm the fix without keeping it: `uv lock --upgrade-package <pkg>`, re-audit, then `git checkout uv.lock` to restore.
4. Surface on the PR + to the lead with the exact pkg/version/advisory and the verified one-line lockfile bump; let the dep-bump land as its own PR (TD-intake candidate) so all sibling PRs unblock together.
