# Pull Requests — Authoring

> Part of the [pull-requests charter index](../pull-requests.md) — re-shelved from `charter/pull-requests.md` for section-level loading (#963). Rules unchanged.

## PR Template <!-- promotion-target: none -->
```bash
git push -u origin <branch-name>
gh pr create --base deployments/phase-{N}/wave-{M} --title "<short title>" --body "$(cat <<'EOF'
## Summary <!-- promotion-target: none -->
<1-3 bullet points describing the change>

## Related Issues <!-- promotion-target: none -->
Closes #<issue-number>

## Review Checklist <!-- promotion-target: none -->
- [ ] Reviewed by another team member
- [ ] Must-fix items resolved
- [ ] Tech debt items filed as GitHub Issues (if any)
- [ ] Docs updated for the code change (README / docs/ / ontology), or a `Docs-N/A:` opt-out trailer is justified

Co-Authored-By: Firstname Lastname <parametrization+Firstname.Lastname@gmail.com>
Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

- PR title should be concise (under 70 characters).
- The body must reference the related GitHub Issue(s) with `Closes #N`.
- The submitting team member is responsible for creating the PR immediately upon branch completion.

### Documentation freshness (advisory gate — #768)

Code is the arbiter of truth for the docs: when a PR changes a **documented code surface**, the docs it implies (README / `docs/` / ontology / CLAUDE.md) are expected to move with it. The advisory `doc-freshness` gate (`.claude/lib/doc_freshness.py`, mirrored as the `Doc-freshness gate (advisory)` CI job and the `doc-freshness` pre-push hook) reports surfaces changed without a matching doc update. It is **advisory — never blocks** (it always exits 0; a heuristic freshness signal has unavoidable false-positives). When a change legitimately needs no doc update, declare it with a `Docs-N/A:` or `Skip-Doc-Check:` trailer line (the trailing colon is required) in a commit message or the PR body. Canonical rule: `ontology/conventions.md` § Ontology: code is the arbiter of truth.

## Closes-vs-Refs Disposition — Decided at Brief Time, Never Flipped <!-- promotion-target: none -->

<!-- Promoted from memory: feedback_owner_pivot_supersedes_protocol (P3W13 retro proposal #2 — #561 Closes/Refs flip-flop) -->

The `Closes #N` vs `Refs #N` disposition for an issue is determined **once, when the implementer brief is authored**, and is **not re-litigated after the PR opens or merges**.

- **`Closes #N`** — use only when the PR fully delivers the issue's entire acceptance surface. After merge to the default branch the issue auto-closes (and per `state-claims.md`, on a wave-branch merge it must be closed manually).
- **`Refs #N`** — use when the issue's acceptance includes **work beyond this PR** — most commonly an **end-state / org-wide criterion with remaining per-repo rollout**, a prod-gated runtime step, or a multi-PR sequence. The issue **stays open as the rollout tracker**; closing it is a separate, later decision.

**The rule:** if at brief-authoring time any part of the issue's acceptance will remain after this PR merges, the disposition is `Refs` from the **first** PR. Do not open with `Closes`, discover remaining rollout, and flip to `Refs` afterward — that flip is a routing change on an in-flight artifact and triggers the same supersede/re-verify churn as any other late pivot (see the Owner-Pivot-Supersedes protocol in `agents.md` and memory `feedback_owner_pivot_supersedes_protocol`).

**Origin (P3W13 #561):** the org-wide branch-protection criterion (#322) was opened with `Closes`, then flipped to `Refs` after the per-repo-rollout-remaining nature surfaced — costing the brief author multiple round-trips. Deciding `Refs` up front (because rollout to 7 repos plainly remained) would have avoided every one of them.

## Pre-Push Checklist <!-- promotion-target: none -->
Before pushing a branch and creating a PR, every engineer must:

1. **Run the repo's lint check** (`ruff check` / `npm run lint` / equivalent) — fix all errors.
2. **Run the repo's format check** (`ruff format --check` / `npx prettier --check` / equivalent) — fix any formatting issues.
3. **Run the repo's typecheck** (`mypy` / `npm run typecheck` / equivalent) — fix type errors.
4. **Run the full test suite** — `npm run test` / `make test` / equivalent. This includes unit tests AND E2E/Playwright if the repo has them. Do NOT skip tests — content changes can break test assertions.
5. **Verify branch name** — `git branch --show-current` must match `{FirstInitial}.{LastName}/{IIII}-{issue-name}`.

Pushing code that fails lint, formatting, or tests is a **minor feedback event**.

## Trivial Cross-Repo Doc Sweep

When a single doc-sync change must land identically in N>1 child repos (e.g., backslash→slash path corrections, broken-URL fixes, copyright-year updates, identical CLAUDE.md sentence sync), a **Single-Reviewer Exception** is granted per child PR provided ALL of the following hold:

1. **Byte-identical diff** — every child PR's diff is byte-identical to every other (verifiable via `git show <pr-head>:<path> | diff -`). Per-repo adaptations (different branding, different file paths) DO NOT qualify; those go through standard 2-reviewer review.
2. **No behavior change** — change is doc/comment-only OR a configuration sync that produces no runtime difference.
3. **Tracking-issue link** — every child PR references one parent tracking issue in `noorinalabs-main` that enumerates all child PRs.
4. **CI green on every repo** — no CI failures across the sweep; one red CI revokes the exception for the whole sweep.

A sweep PR uses the same charter-format comments and TechDebt line as standard PRs. When the exception is invoked, the PR body must include a "Sweep:" line citing the tracking issue and the byte-identical-diff verification command.

**See also:** § Single-Reviewer Exception (Wave-Bootstrap Only) — a separate single-reviewer exception class for tooling/CI/hook-rollout PRs that gate subsequent wave work. The two exceptions are **independent budgets** (the wave-bootstrap 1-per-wave cap does not consume, and is not consumed by, doc-sweep waivers) and are **not cumulative** — a single PR may invoke at most one.

**Why:** P3W4 ran 4 separate per-repo PRs for an identical 1-line CLAUDE.md slash sync (isnad-graph#857, user-service#94, design-system#63, data-acquisition#34) — 4 review pairs, 4 CI runs, ~12 charter-format comments for a no-decision change. The 2-reviewer requirement is load-bearing for behavior changes; for byte-identical doc sweeps, the verification value is concentrated at the parent tracking issue, not at each child PR.

**Severity if violated:** Invoking the sweep exception on a non-byte-identical change, or skipping the tracking issue, is moderate (review-bypass for changes that needed standard review). The 2nd reviewer is the load-bearing safeguard against silent behavior change.

<!-- Promoted from memory: feedback_security_guard_inline_not_followup.md (P3W5 retro 2026-05-06) -->

## `gh pr edit` projects-classic deprecation — use REST API for body/title updates (Mandatory) <!-- promotion-target: none -->

`gh pr edit <num> --body <text>` (and `--body-file <path>`, and `--title`) on gh-cli versions older than the one that migrated off the deprecated projects-classic GraphQL scope **silently fails** the body/title mutation. The command exits non-zero with a `GraphQL: Projects (classic) is being deprecated` error, but the error reads like a benign warning and the PR body appears unchanged on subsequent inspection — exactly the "silent-no-op" shape captured in memory `feedback_gh_pr_edit_silent_noop`.

Root cause: `gh pr edit` fetches `repository.pullRequest.projectCards` as a side-effect of the mutation; the classic-projects deprecation fails that sub-query, poisoning the whole call. Resolves main#185 (Linh.Pham hit 2026-04-22 — PR#844 body silently retained option-A through the entire v5 phase; reviewers never saw v5 content for ~30 minutes).

### Required workaround — use REST API directly

For any PR body or title update, prefer the REST API:

```bash
# Body update (single line)
gh api "repos/<owner>/<repo>/pulls/<num>" -X PATCH \
  -f body="$(cat /path/to/body.md)"

# Body update (multi-line, recommended — avoids quote-escape bugs)
gh api "repos/<owner>/<repo>/pulls/<num>" \
  --method PATCH \
  --input <(jq -nc --rawfile b /path/to/body.md '{body:$b}')

# Title update
gh api "repos/<owner>/<repo>/pulls/<num>" -X PATCH \
  -f title="new title"
```

`-f` is `--field` and treats the value as a string. For multi-line bodies, prefer `--input` with a `jq`-built JSON body to avoid `-f`'s newline-stripping behavior (see memory `feedback_gh_pr_edit_silent_noop` for the related `gh api -f body=@file` no-op trap — use `--input` or pipe through `jq --rawfile`).

### Eligibility

The REST path applies whenever the gh-cli version is older than the upstream fix release. As of this writing (May 2026) the locally-installed gh is `v2.45.0` (July 2025 build). The upstream fix landed in a later release (`cli/cli` migrated the projects-classic scope post-2025). To check locally:

```bash
gh --version
```

If `gh --version` reports `v2.45.0` or older, USE the REST path. If newer, the native `gh pr edit` may be safe — but the REST path always works regardless of version, so skill authors who want maximum portability should default to REST.

### Read-back verify

Per the silent-no-op shape: ALWAYS verify the body/title landed after an update, regardless of which path you used:

```bash
gh pr view <num> --repo <owner>/<repo> --json body --jq '.body | length'
# OR (head of body):
gh api "repos/<owner>/<repo>/pulls/<num>" --jq '.body[0:80]'
```

A 0-length body or a stale prefix is the signal the mutation didn't land.

### Severity if violated

- Skill or script uses `gh pr edit --body` and never reads back: **moderate** — silently produces wrong state visible to reviewers as "the body says X" when X is the prior version. Worked example: isnad-graph#844's 30-minute reviewer confusion window (Linh.Pham, P2W10).
- Skill author uses `gh pr edit` AND read-back-verifies: **minor**. The read-back catches the no-op even if the mutation surface stays risky.
- Manual one-off `gh pr edit` invocation by a human operator: **out of scope** for charter enforcement (humans can interactively re-run); the charter rule applies to skill/script paths where the no-op compounds across batched calls.

### Cross-references

- Memory `feedback_gh_pr_edit_silent_noop` — the broader silent-no-op family (`gh project item-add`, `gh project item-list --limit`, `gh api -X PATCH -f body=@file`) sharing this shape.
- Resolves main#185.
