# Pull Requests — Evidence Standards

> Part of the [pull-requests charter index](../pull-requests.md) — re-shelved from `charter/pull-requests.md` for section-level loading (#963). Rules unchanged.

## Trust the Artifact, Not the Framing (Mandatory) <!-- promotion-target: skill -->

Both implementer and reviewer disciplines on the same axis: verify spec assumptions and PR-body framing against ground truth before action.

### Implementer side

Before implementing per a spec, issue body, or upstream brief, verify the spec's load-bearing claims against the actual artifact:

- Issue body says "alert exists at X / read it, don't re-implement" → check `git log -- X` and `grep` the file before assuming.
- Spec says "extend Y to add Z" → check Y's current shape (post-prior-merges) before drafting; the spec may predate later changes.
- Brief from manager says "use convention K" → check `git branch -a` / `git grep` for K-shaped artifacts before encoding it as truth.

If the spec's load-bearing claims diverge from ground truth, surface the gap to the manager BEFORE implementing — do not silently absorb the divergence.

**Authoritative example:** `noorinalabs-deploy#161` 3-x scope catch (issue body said alert exists at `#153`, alert had been deferred and never landed; verified via `git log` + `grep` before pushing dead code).

### Reviewer side

Read the diff against the actual artifact (Caddyfile, compose env-vars, terraform state, alert YAML, runbook, etc.), not against the PR body's framing of what the diff does. PR-body framing is a useful navigation aid; the diff against the artifact is the ground truth.

**Authoritative example:** `noorinalabs-deploy#206` review caught a false-positive bug by walking `caddy/Caddyfile` lines 88-89 + 101 against the PR's section 3b dual-route logic. The PR-body framing said "user-service /health probe via Caddy rewrite + post-#156 subdomain fallback"; the artifact showed the fallback would route to isnad-graph instead of user-service, producing a silent false positive on user-service availability if user-service goes down.

#### Confirm the PR head SHA before posting any verdict

Reading the diff against the artifact only proves anything if you read the artifact at the SHA you are about to certify. Before posting Approved or ChangesRequested, the reviewer MUST record and confirm the PR head SHA they reviewed:

```bash
gh pr view <N> --repo <owner>/<repo> --json headRefOid --jq .headRefOid
```

State that SHA (or the short form) in the verdict so the certification is anchored to a concrete head, not to "the PR" as a moving target. Then:

- **If the PR is rebased or force-pushed after your verdict**, the prior verdict is **stale** — it certified a head that no longer exists. It must be re-confirmed against the new head before it counts toward merge; a materially-changed diff requires a fresh read of the changed surface, not a carry-over of the old Approved. (This is the reviewer-facing companion to § Additive-Commits-Only on ChangesRequested Cycles, which keeps the head anchor stable so this re-confirmation is rarely needed.)
- **Before posting ChangesRequested**, confirm the line(s) you are blocking on exist at the head SHA — not in a stale local checkout. A "still has X" block sourced from a local working tree that lags the head is a false positive (per § Origin > Local Clone for "Still-Has-X" File-Content Claims).

**Authoritative examples (P4W6):** `noorinalabs-isnad-graph#1020` was rebased *after* approval — the head SHA changed and the diff changed materially; the author proactively flagged it and the approval was correctly re-verified against the new head rather than carried over. Conversely, `noorinalabs-ingest-platform#85` drew a ChangesRequested that turned out to be a stale-tree misread (the reviewer judged a phase-3/wave-11 working tree, not the PR head), costing a critical-path re-verify cycle — a head-SHA confirmation step at verdict time would have caught it before the block was posted.

### How to apply

- **Implementer:** before any Edit/Write inside a worktree, run `gh issue view`, `git log -- <load-bearing-path>`, and `grep` for any spec claim about existing artifacts.
- **Reviewer:** confirm the PR head SHA (`gh pr view <N> --json headRefOid`) and state it in the verdict, then walk at least one load-bearing claim in the PR body against the actual artifact at that SHA via `gh api .../contents/<path>?ref=<head_sha>` or `git show <head_sha>:<path>`. If the head moves after your verdict (rebase/force-push), re-confirm before it counts toward merge.

### Severity if violated

- Implementer: silent absorption of a spec-vs-reality gap that produces dead code or wrong defaults is minor; producing a security regression (route mismatch, env-var leak, etc.) is severe.
- Reviewer: rubber-stamping based on PR-body framing alone is minor; missing a false-positive bug because reviewer read the framing but not the artifact is moderate. Posting a verdict with no head-SHA anchor that then goes stale on a post-verdict rebase and is carried over to merge, or blocking on a line that does not exist at the head (stale-local-tree misread), is moderate.

### Why

Phase 3 Wave 1 produced 4 corroborating data points across two roles. Implementer side: `#161` scope catch + `#206` Reality-post-#87 mapping table. Reviewer side: `#206` Caddyfile evidence-receipts. Both halves of the same discipline.


## Live-Trace Evidence > Synthetic-Test Acceptance (Mandatory) <!-- promotion-target: skill -->

When validating a new gate (CI hook, security check, alert rule, validation logic), prefer **live-trace evidence** — the gate firing on a real, in-the-wild triggering artifact — over **synthetic-test acceptance** — the gate passing on test cases authored alongside the gate.

### Why

Synthetic tests prove the gate handles the cases the author *imagined*. Live-trace proves the gate handles the cases the *world produces* — which routinely diverge from the author's mental model. Synthetic tests can be written to pass; live-trace evidence can't be retroactively shaped to fit. The gate either fires correctly on the wild artifact or it doesn't.

### How to apply

- **For PR-time gates (CI hooks, validators, lint rules):** identify the most-recent failed real PR (not a synthetic one) and demonstrate the gate's verdict on that PR. Reference the failed run by URL or sha in the PR body. If you cannot find a recent in-the-wild failure, that is itself a signal — the gate may need a longer observation window before high-confidence acceptance, or its scope may be too narrow to be worth shipping.
- **For runtime gates (alerts, monitors, startup assertions):** capture the gate firing on a real production event (alert firing, monitor crossing threshold, boot-time assertion tripping). Reference the firing artifact (alert ID, run ID, log entry, sha range) in the PR body or evidence package.
- **Document the live-trace explicitly** in PR review evidence — reviewers can verify the artifact independently. Synthetic tests remain valuable as a regression floor; they just don't substitute for live-trace.

### Reviewer enforcement

When reviewing a new gate, ask "what wild artifact did this fire on?" If the only acceptance evidence is the gate's own test fixtures, request a live-trace before approving (Changes Requested if no live-trace exists; tech-debt followup if a live-trace is achievable but deferred to next wave).

### Severity if violated

- Implementer ships a gate with synthetic-only acceptance: **minor** (the gate may still be correct; the discipline gap is in evidence quality).
- Reviewer rubber-stamps a gate without asking for live-trace: **minor**, **moderate** if recurring across a wave.
- Gate ships with synthetic-only acceptance and silently misclassifies a wild artifact post-merge: **moderate** (the missed live-trace would have caught the misclassification before merge).

### Worked example

`noorinalabs-main#194` Hook 14 (`validate_pr_ci_status.py`) fan-out, 2026-04-28. Marisol's PR landed the strongest acceptance signal across the entire fan-out series by **live-tracing `classify_check` against an actual in-flight failed security-audit CI run** at the time — not against a fabricated failure. The live-trace caught a behavior pattern that synthetic tests would have missed because the author didn't think to test for it. Aino flagged this as the strongest acceptance proof in the entire fan-out — distinct enough that it materially changed Hook 14's confidence floor.

## Origin > Local Clone for "Still-Has-X" File-Content Claims (Mandatory) <!-- promotion-target: none -->

When asserting a "still has X" / "still at Y" / "still missing Z" property about a PR's file content, query origin directly via `gh api repos/<owner>/<repo>/contents/<path>?ref=<head_sha>` (or `gh api .../pulls/<N>/files`). Do NOT grep a local checkout, worktree, or `/tmp/` clone of the PR branch.

### Why

Local clones are point-in-time snapshots — frozen the moment they're created and stale the next push that lands. In high-churn cycles (active multi-implementer wave work), a clone made N minutes ago can be N commits behind origin. Asserting "still has X" against the local snapshot generates a false-positive Changes-Requested that confuses the implementer and forces a counter-correction.

This is the file-content-assertion specialization of the umbrella state-verification discipline encoded in `state-claims.md § Refresh State Before Claim`. That section governs top-line PR/issue state via `gh pr view --json state,...`. This rule extends the same discipline to per-path file content via `gh api .../contents`.

### How to apply

- For any "PR still has bug Y" / "file <path> still does Z" / "removal didn't land" assertion, fetch the file at the PR head:
  ```bash
  HEAD_SHA=$(gh pr view <N> --repo <owner>/<repo> --json headRefOid --jq .headRefOid)
  gh api "repos/<owner>/<repo>/contents/<path>?ref=$HEAD_SHA" --jq '.content' | base64 -d
  ```
- Refreshing a local checkout via `git fetch && git checkout <head_sha>` before grep is acceptable but takes more steps; direct `gh api repos/.../contents/<path>?ref=<head_sha>` is one call.
- Most acute in **high-churn cycles** where commits land in the few-minute window between cloning and asserting.

### Reviewer enforcement

When a reviewer's review-comment cites "still has X" / "still missing Y", the comment must either include the `?ref=<head_sha>` query or be re-verifiable by another reviewer via that query. Local-checkout-grep claims that produce a false-positive Changes-Requested are correctable on the next refresh; if the implementer counter-verifies via `gh api ... contents` and demonstrates the change has landed, the original review-comment must be revised (not silently abandoned) — paper trail matters.

### Severity if violated

- Single false-positive Changes-Requested from local-checkout staleness: **minor**, paper-trail correction required.
- Recurring across a wave: **moderate** (signals the discipline isn't being applied; consumes implementer cycles on counter-corrections).
- Local-checkout-grep used to assert a security-relevant claim ("PR still missing the auth guard") that turns out to be wrong: **moderate-to-severe** depending on whether the false-positive blocks a real fix from landing.

### Worked example

`noorinalabs-deploy#181` / Bereket → Lucas-87, 2026-04-28. Lucas pushed `c0b65e2` addressing Weronika's 3 blockers. Bereket cloned PR #181 branch to `/tmp/pr181-v2/` at HEAD `c0b65e2`. Lucas then pushed `3c7ee55` adding Nurul's 2 nits (junit-dup + schema_version). Bereket's "ready for re-review" message arrived AFTER `c0b65e2`, BEFORE `3c7ee55`. Bereket grep'd `/tmp/pr181-v2/` (still at `c0b65e2`) and reported "still has the duplicate junit-xml" — false positive. Lucas had to counter-verify via `gh api ... contents/...?ref=3c7ee55` and demonstrate the fixes were already there. Local clone was correct *at the time it was cloned*, but stale by the time the assertion was made.

### Cross-references

- `state-claims.md § Refresh State Before Claim` — top-line state-verification umbrella; this rule is the file-content specialization.
- `pull-requests.md § Trust the Artifact, Not the Framing` — companion: read the artifact at HEAD, not the PR-body framing. Both rules converge on the same access primitive (`gh api ... contents/?ref=<head_sha>`).

<!-- Promoted from memory: (none — this section codifies retro-PR-diff discipline; sourced from #126 + W8 PR #124 incident) -->

## Sandbox Test-Verification Pattern — Unit-Construct + Cite-CI When the Suite Hangs (Mandatory) <!-- promotion-target: none -->

The dev sandbox has **no local backing services** (Neo4j/Postgres/Redis bolt + frontend resolve only inside the cluster — see memory `project_staging_neo4j_frontend_unreachable_from_sandbox`). A test whose fixture spins up the app (FastAPI `TestClient` lifespan, DB-connected `client` fixture) will **block on a connection attempt that never completes** — it presents as "still running," not as a failure, so it silently burns wall-clock.

### How to apply

- **If the full suite hangs**, do NOT keep waiting on it. Verify the changed logic via a **targeted unit check that needs no app/DB startup** — construct the model/function directly and assert behavior — then **cite the green CI job** (which runs with real services) as the suite-pass evidence in the PR / review.
- **Reviewers:** a verdict may rest on "direct unit verification + green CI `test` job" when a local full-suite run is environmentally infeasible; say so explicitly. Do not demand a completed local suite run that the sandbox cannot produce (companion to § PR-Time Acceptance vs Runtime Acceptance — environmental infeasibility, not deferral).
- **`uv run` gotcha:** prefer invoking the tool through the resolved venv (`.venv/bin/pytest`, `.venv/bin/ruff`, `.venv/bin/mypy`) over `uv run <tool>` — `uv run` can stall on venv lock-contention behind a hung sibling process, compounding the hang.

### Severity if violated

- Burning a long wait on a hung full-suite run instead of unit-constructing + citing CI: **minor** (wasted wall-clock).
- Claiming "tests pass" from a run that actually hung (never reached a terminal state): **moderate** — that is an unverified claim; cite the CI job or the direct unit check, not a hung local run.

### Worked example

P5W2 (#1024 / PR #1045, #1048 diagnosis): `pytest tests/test_api/test_narrators.py` ran 14 min at 0.4% CPU / 163 MB RSS — hung on the `client` fixture's app-startup DB connect, not computing. Resolution: constructed `NarratorResponse` directly from a sparse `{id, name_ar}` dict to prove the fix (+ ran `ruff`/`mypy` via `.venv/bin`), and cited the green CI `test` job. Marisol independently hit the same ~9-min stall and correctly cited CI rather than a completed local run.

## Text-Processing / NER / Graph Fixtures Must Use Production-Realistic Input (Mandatory) <!-- promotion-target: hook -->

Fixtures for **Arabic text processing, NER / segmentation, and graph-load invariants** MUST be derived from **real upstream samples** — never hand-authored from a schema that matches the parser's own assumptions, and never simplified into toy strings. A fixture that is *greener than real data* is masking a bug.

### The rule

- **Voweled (vocalized) Arabic** matching real corpus text — never un-voweled toy strings. Text-processing and segmentation logic behaves differently on vocalized input; a fixture stripped of diacritics exercises a code path the production corpus never takes.
- **Real high-frequency structures.** An isnad-chain fixture MUST contain the high-frequency transmission particle عن (ʿan) AND at least one narrator name carrying an عن / قال substring — e.g. عنبسة (ʿAnbasa), معن (Maʿn), مقالة (maqāla). These are exactly the strings a naive segmenter over-splits; omitting them lets an over-segmentation bug pass.
- **Real-shape rows.** Use the actual upstream column set / schema (a captured sample row), not a minimal hand-built dict. A fixture authored from the parser's assumed schema validates the assumption, not the data.
- **Parse-path tests run against real-upstream fixtures.** The test that exercises the parse / NER / graph-load path asserts against a sample lifted from the real source, so the test fails when the parser's model of the source is wrong.

### Why (the recurring class)

The **fixture-masks-bug** class has recurred 5+ times, most damningly *inside its own fix*: da#146 (PR #151) replaced an un-voweled toy blob — but its Bukhari-h1 replacement fixture contained no عن, masking a new over-segmentation surfaced only later as da#155. The same shape recurred again in P5W5: da#175's thaqalayn (al-Kafi) parser shipped a fixture matching an *assumed* schema rather than the real upstream, so 0% extracted Arabic text went undetected. Earlier instances: `MockNeo4jClient` masking the APPEARS_IN null-property loader bug; toy h-1 fixtures masking the double-prefix hadith-id bug; local-only staging edges. The defect is always the same — the fixture encodes the author's mental model of the source instead of the source itself, so the test is green and the parser is wrong.

This is the **input-side companion** to § Live-Trace Evidence > Synthetic-Test Acceptance: that rule says a gate's *acceptance* must be proven on a wild artifact; this rule says a parser's *fixture* must be lifted from one.

### How to apply

- When adding or changing a text-processing / NER / graph-load fixture, **lift the bytes from a real upstream sample** (a real hadith / isnad / rijāl row from the actual source) and commit that, not a minimal reconstruction. Note the provenance (source + identifier) in a comment or the test docstring.
- If the real sample is large, trim it to a representative slice — but preserve vocalization, the عن particle, and at least one عن/قال-substring narrator name. Trimming MUST NOT make the fixture greener than the source.
- Never author a fixture from the schema you *expect* the parser to consume; capture what the source actually emits and let the test prove the parser matches it.

### Reviewer enforcement

When reviewing a PR that adds or edits one of these fixtures, ask: **"was this lifted from real upstream, or authored to match the parser?"** If the Arabic is un-voweled, if the chain lacks عن, or if the row is a minimal hand-built dict, request the real-sample fixture before approving (Changes Requested). A fixture whose only virtue is that it passes the new code is not acceptance evidence.

### Enforcement opportunity

A lint / review-lens can flag Arabic-text fixtures that lack vocalization marks (no Arabic diacritic codepoints `ً–ْ`) or whose isnad strings lack عن — a cheap static signal that a fixture is a toy. Tracked as the optional half of #671; the charter rule is the floor, the lens is a plus.

### Severity if violated

- Shipping a text-processing / NER / graph fixture that is hand-authored from the parser's assumed schema or stripped of vocalization: **moderate** (it actively masks the next bug in that path — the failure mode that recurred 5+ times).
- Reviewer approving such a fixture without asking for the real-upstream sample: **minor**, **moderate** if it lets a masked bug merge.

### Worked example

da#146 / PR #151 (fix), da#155 (the bug it masked), 2026-06: the fix for an un-voweled-toy-fixture bug shipped a replacement Bukhari-h1 e2e fixture with no عن, masking a fresh over-segmentation. Surfaced independently by Alejandra Reyes-Fuentes and Jean-Claude Habimana on PR #151. The class recurred in P5W5 on da#175 (thaqalayn / al-Kafi), where a schema-assumed fixture hid 0% extracted Arabic — the recurrence that motivated codifying this rule (owner-adopted P5W1 retro, main#671).

<!-- Promoted from memory: feedback_pr_vs_runtime_acceptance_criteria.md (P3W9 #346 memory audit, 2026-05-10) -->

