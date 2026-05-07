---
name: wave-scope
description: Reconcile declared-vs-labeled wave scope between /wave-retro and /wave-kickoff — collect dispositions, fold in retro carry-forwards and memory must-includes, and refresh the meta-issue
args: Phase number, Wave number
---

Reconcile **declared scope** (next-wave meta-issue body) with **actual scope** (issues labeled `p{P}-wave-{M}` across all repos) before kickoff. Surfaces drift that accumulated during the prior wave, folds in retro carry-forwards and memory-tracked must-includes, and produces a clean meta-issue + label set for `/wave-kickoff` to act on.

> Note: all repo paths in bash blocks below are rooted at `$REPO_ROOT` to avoid cwd drift when the skill is invoked from a worktree or child-repo subdirectory (#149).

## When to use

- **Between `/wave-retro` (wave N done) and `/wave-kickoff` (wave N+1 launching).** Owner-confirmed cadence; running it inside an active wave is fine but lower-value.
- **Triggered by drift signal** — e.g. last-wave audit found multiple unscoped labels, or memory contains `W{N+1} must include` entries that weren't surfaced at retro.

## What this skill is NOT

- Not a branch-creation step — that's `/wave-start`.
- Not a kickoff-comment step — that's `/wave-kickoff`.
- Not an end-of-wave audit — that's `/wave-audit` (close orphans against merged PRs).

## Instructions

### 0. Inputs and prerequisites

Before invoking, the user provides:
- `{P}` — phase number for the next wave (e.g. `3`)
- `{M}` — wave number for the next wave (e.g. `5`)

The skill expects the next-wave **meta-issue** to already exist (drafted at the prior retro or before). If it does not, STOP and ask the user to create it first — `/wave-scope` reconciles a meta-issue, it does not author one.

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
WAVE_LABEL="p{P}-wave-{M}"
PRIOR_WAVE_LABEL="p{P}-wave-$(({M} - 1))"  # for retro carry-forward cross-ref
```

### 1. Read previous-wave retro carry-forward

`/wave-retro` writes carry-forward items to two places:
- `.claude/team/feedback_log.md` — most recent `## Retrospective: Phase {P} Wave {M-1}` section, "Deferred to next wave" / "Carry-forward" subsections.
- `cross-repo-status.json` — `phase_{P}_carry_forwards` array (canonical structured list, post-W10).

```bash
# Structured carry-forwards (preferred — survives feedback_log churn)
jq -r '.phase_{P}_carry_forwards[]? | "\(.id)\t\(.type)\t\(.note)"' "$REPO_ROOT/cross-repo-status.json"

# Free-text carry-forwards (fallback / supplement)
awk '/^## Retrospective: Phase {P} Wave '$((M-1))'/,/^## /' "$REPO_ROOT/.claude/team/feedback_log.md" \
    | sed -n '/[Cc]arry.forward\|[Dd]efer/,/^### \|^## /p'
```

Collect into a `CARRY_FORWARDS=[]` working list. Each entry: `{id, source: "retro", type, note}`.

### 2. Read memory must-includes

Project memory may carry must-include directives keyed to the next wave (e.g. `W{N+1} must include user-service#63`). Scan the project memory dir:

```bash
MEMORY_DIR="$HOME/.claude/projects/-home-parameterization-code-noorinalabs-main/memory"
# `|| true` because grep -l exits 1 when there are no matches, which is the
# normal case for waves with no filed must-includes — not an error.
MUST_INCLUDE_FILES=$(grep -l -i "W{M} must include\|wave-{M} must\|w{M}.must.include" "$MEMORY_DIR"/*.md 2>/dev/null || true)
[ -z "$MUST_INCLUDE_FILES" ] && echo "  (no must-includes filed for W{M})"
```

For each match, read the file and extract the issue references. Memory naming convention: `project_w{M}_*.md` (e.g. `project_w10_user_service_alembic.md` — the W10 example matched on the literal phrase `W10 must include` in MEMORY.md and the file body itself). Add to working list as `MUST_INCLUDES=[]`. Each entry: `{id, source: "memory", file, note}`.

If a referenced issue ID does not parse to a `repo#N` shape, surface to the user before proceeding — memories with vague references are a process gap that should be fixed at the source.

### 3. Read next-wave meta-issue → declared scope

The meta-issue body + comments are the canonical declared scope.

```bash
# Find the meta-issue. Canonical pattern: title contains "Phase {P} Wave {M}" and is in noorinalabs-main.
META_ISSUE=$(gh issue list --repo noorinalabs/noorinalabs-main \
    --search "Phase {P} Wave {M} in:title" \
    --json number,title --jq '.[0].number')

if [ -z "$META_ISSUE" ] || [ "$META_ISSUE" = "null" ]; then
    echo "ERROR: no meta-issue found for Phase {P} Wave {M}. Create one before running /wave-scope."
    exit 1
fi

# Pull body + every comment (declared scope can land in either)
gh issue view "$META_ISSUE" --repo noorinalabs/noorinalabs-main --json body,comments \
    --jq '.body, (.comments[] | .body)' > /tmp/wavescope-{M}-declared.txt
```

Extract every `repo#N` reference from the body and comments. Use a permissive regex to catch the common shapes:

```bash
grep -oE '\b(noorinalabs-[a-z-]+|main|deploy|isnad-graph|user-service|design-system|landing-page|data-acquisition|isnad-ingest-platform)#[0-9]+' \
    /tmp/wavescope-{M}-declared.txt | sort -u > /tmp/wavescope-{M}-declared-issues.txt
```

This is the `DECLARED=[]` set.

### 4. Query labeled scope across all repos

Use the canonical cross-repo audit primitive (charter `skills.md` § Wave Lifecycle — Open-Item Audit):

```bash
REPOS=(
    noorinalabs-main noorinalabs-isnad-graph noorinalabs-user-service
    noorinalabs-deploy noorinalabs-design-system noorinalabs-landing-page
    noorinalabs-data-acquisition noorinalabs-isnad-ingest-platform
)
> /tmp/wavescope-{M}-actual-issues.txt
for repo in "${REPOS[@]}"; do
    # 2>/dev/null suppresses "label not found" stderr — labels are per-repo so
    # not every repo will have $WAVE_LABEL until step 9 (or a prior /wave-start).
    # Non-zero exit on missing-label is normal and ignored.
    gh issue list --repo "noorinalabs/$repo" --state open --label "$WAVE_LABEL" \
        --json number,title,createdAt \
        --jq '.[] | "'"$repo"'#\(.number)\t\(.title)\t\(.createdAt)"' \
        2>/dev/null >> /tmp/wavescope-{M}-actual-issues.txt || true
done
echo "  Actual labeled: $(wc -l < /tmp/wavescope-{M}-actual-issues.txt) items across ${#REPOS[@]} repos"
```

This is the `ACTUAL=[]` set (with title and creation date).

### 5. Compute scope drift

The drift is `ACTUAL − DECLARED`. Two complementary deltas:

| Delta | Meaning | Default action |
|---|---|---|
| `ACTUAL − DECLARED` | Items labeled but not declared (silent label-drift) | Review per-item: keep, defer, strip-label, close |
| `DECLARED − ACTUAL` | Items declared but not labeled (forgot-to-tag) | Apply label after user confirms still-in-scope |
| `MUST_INCLUDES − ACTUAL` | Memory must-includes missing the wave label | Apply label (these are non-negotiable per their memory entries) |
| `CARRY_FORWARDS − ACTUAL` | Retro carry-forwards missing the wave label | Apply label after user confirms still applicable |

```bash
comm -23 <(cut -f1 /tmp/wavescope-{M}-actual-issues.txt | sort) \
         <(sort /tmp/wavescope-{M}-declared-issues.txt) > /tmp/wavescope-{M}-unscoped-drift.txt

comm -13 <(cut -f1 /tmp/wavescope-{M}-actual-issues.txt | sort) \
         <(sort /tmp/wavescope-{M}-declared-issues.txt) > /tmp/wavescope-{M}-unlabeled-declared.txt
```

### 6. Present unscoped items in repo-batched review

For each item in `ACTUAL − DECLARED`, group by repo and show:

```
**Unscoped Drift — `p{P}-wave-{M}` labeled but not in meta-issue**

### noorinalabs-deploy ({count} items)

| Issue | Title | Created | Body excerpt |
|---|---|---|---|
| #N | ...  | YYYY-MM-DD | First 80 chars of body... |
| #N | ...  | YYYY-MM-DD | ... |

### noorinalabs-isnad-graph ({count} items)
...
```

Per-item body excerpt:

```bash
gh issue view {N} --repo "noorinalabs/{repo}" --json body --jq '.body | .[0:80]'
```

### 7. Collect dispositions per item (manual — owner judgment)

For each unscoped item, the owner picks one of:

| Disposition | Mechanic |
|---|---|
| `keep-in-w{M}` | Add to declared scope (step 11 will fold it into the meta-issue body) |
| `defer-to-w{M+1}` | Strip `p{P}-wave-{M}` label, apply `p{P}-wave-{M+1}` (create label if needed in step 9) |
| `strip-label` | Strip `p{P}-wave-{M}` label, no other label change |
| `close-as-obsolete` | Close issue with a comment referencing the disposition |

Record dispositions in a working table. Do NOT apply any label changes until step 10. Do NOT close any issues until step 10.

This step is the orchestration's only blocking owner-judgment gate. Empty dispositions = STOP.

### 8. Verify must-includes and carry-forwards are labeled

For each entry in `MUST_INCLUDES` and `CARRY_FORWARDS`:

```bash
HAS_LABEL=$(gh issue view {N} --repo "noorinalabs/{repo}" --json labels \
    --jq '.labels[] | select(.name == "'"$WAVE_LABEL"'") | .name')
[ -z "$HAS_LABEL" ] && echo "MISSING LABEL: {repo}#{N}"
```

For each missing-label item, queue a label-apply for step 10.

If a `MUST_INCLUDES` entry is closed or non-existent, the source memory file is stale — surface to the user with a recommendation to remove or update the memory entry. Do NOT silently drop a must-include.

### 9. Create next-wave label (`p{P}-wave-{M+1}`) if any defer dispositions

If any disposition in step 7 was `defer-to-w{M+1}`, ensure the label exists in every relevant repo:

```bash
NEXT_LABEL="p{P}-wave-$(({M} + 1))"
# Match the color/description of the current wave label for consistency
CURRENT_COLOR=$(gh label list --repo noorinalabs/noorinalabs-main --search "$WAVE_LABEL" --json color --jq '.[0].color')

for repo in $REPOS_WITH_DEFER; do
    gh label list --repo "noorinalabs/$repo" --search "$NEXT_LABEL" --json name --jq '.[].name' | grep -q "$NEXT_LABEL" || \
        gh label create "$NEXT_LABEL" --repo "noorinalabs/$repo" \
            --description "Phase {P} Wave $(({M} + 1))" --color "$CURRENT_COLOR"
done
```

### 10. Apply label churn in one batch per repo

Group all label edits per repo and apply with explicit user confirmation:

```
**Label changes about to apply** ({total} edits across {repos} repos)

### noorinalabs-deploy
- Add `p{P}-wave-{M}` to: #A, #B
- Strip `p{P}-wave-{M}` from: #C
- Strip `p{P}-wave-{M}` AND add `p{P}-wave-{M+1}` to: #D, #E
- Close as obsolete (with comment): #F

### noorinalabs-isnad-graph
...

Confirm to apply, or send back individual reversals.
```

After confirmation:

```bash
# Add label
gh issue edit {N} --repo "noorinalabs/{repo}" --add-label "$WAVE_LABEL"
# Strip label
gh issue edit {N} --repo "noorinalabs/{repo}" --remove-label "$WAVE_LABEL"
# Defer (strip current, add next)
gh issue edit {N} --repo "noorinalabs/{repo}" --remove-label "$WAVE_LABEL" --add-label "$NEXT_LABEL"
# Close as obsolete
gh issue close {N} --repo "noorinalabs/{repo}" --comment "Closed via /wave-scope: out-of-scope for $WAVE_LABEL and not warranted on its own — see meta-issue #$META_ISSUE"
```

### 11. Refresh meta-issue body

Rewrite the meta-issue body with the post-disposition scope. Categorize kept items into sections (the categories are owner-proposable; the skill suggests but does not decide):

- **Promotion-pathway core** — issues that drive the wave's primary theme
- **Precursors** — must-merge-first dependencies for the core
- **Memory must-includes** — items from step 2
- **Retro-mandated work** — items from step 1
- **Direct blockers** — anything blocking promotion of the wave's theme

Append a `## Deferred to W{M+1}` section listing the deferred items + a one-line reason each.

```bash
# Build new body via heredoc, then PATCH via gh api (gh issue edit --body has the same
# silent-no-op risk as gh pr edit per memory feedback_gh_pr_edit_silent_noop.md — use
# gh api PATCH and read-back-verify)
NEW_BODY=$(cat <<'EOF'
{post-disposition body}
EOF
)
echo "{\"body\": $(printf '%s' "$NEW_BODY" | jq -Rs .)}" > /tmp/wavescope-{M}-meta-body.json
gh api -X PATCH "repos/noorinalabs/noorinalabs-main/issues/$META_ISSUE" \
    --input /tmp/wavescope-{M}-meta-body.json --silent

# Read-back verify
READBACK=$(gh api "repos/noorinalabs/noorinalabs-main/issues/$META_ISSUE" --jq '.body | .[0:120]')
echo "$READBACK" | grep -q "Phase {P} Wave {M}" || echo "WARN: meta-issue body update may not have landed"
```

Do NOT delete the original body — copy it (or post the pre-update version as a comment) so the audit trail survives.

### 12. Emit summary

```
**Wave Scope: Phase {P} Wave {M}**

| Metric | Count |
|---|---|
| Declared (pre-scope) | N |
| Labeled actual (pre-scope) | M |
| Drift (actual − declared) | M − N |
| Kept in scope | K |
| Deferred to W{M+1} | D |
| Stripped (no longer in any wave) | S |
| Closed as obsolete | C |
| Memory must-includes folded in | MI |
| Retro carry-forwards folded in | CF |

**Final declared scope:** {final count} items, ready for `/wave-kickoff`.

**Label edits applied:** {edit count} across {repo count} repos.
**Meta-issue refreshed:** noorinalabs-main#$META_ISSUE
```

If any step surfaced a process gap (stale memory, missing meta-issue, vague reference), include a `**Process gaps surfaced**` section so the next retro can address them.

### 13. Write reconciliation timestamp + structured bookkeeping keys to `cross-repo-status.json`

This is what `/wave-kickoff` Steps 0a and 0 read to confirm the wave's scope was reconciled before kickoff AND to derive the per-repo iteration list. Write only on full success — if the run aborted at step 7 (no dispositions) or step 10 (label-churn confirmation declined), do NOT write.

The helper writes **four** keys (added P3W5 #273; structured-keys triplet added P3W6 #278 after `/wave-kickoff 3 6` STOPped on the missing keys):

| Key | Source | Type |
|---|---|---|
| `wave_{M}_scope_reconciled_at` | `$TS` — UTC ISO timestamp captured at write time | string |
| `wave_{M}_repos_in_scope` | the canonical 8-repo `REPOS` array from Step 4, optionally overridden by `WAVE_SCOPE_REPOS` (space-separated repo names) when a wave deliberately excludes a repo | array of strings |
| `wave_{M}_meta_issue` | `$META_ISSUE` from Step 3 | integer |
| `wave_{M}_scope` | from `WAVE_SCOPE_STRUCTURED` env var (a JSON object the orchestrator built from the meta-issue body — tier_*_*, deliberately_not_in_w*, concentration metrics, etc.) — falls back to a minimal `{"declared_refs": [...], "carry_forwards": [...], "must_includes": [...]}` shape derived from steps 1-3 if the env var is unset | object |

**Why not raw jq:** `jq ... > tmp && mv` round-trips reformat the entire file from compact-inline (the deliberate shape used by `/wave-kickoff` and `/wave-start` for `wave_{N}_*` keys) to jq's default pretty form, doubling line count and producing a 500+ line cosmetic diff per run. P3W5 PR #276 review flagged this as load-bearing. The targeted upsert helper below preserves the existing shape — replace-in-place when the key exists (zero churn), insert-near-sibling when it doesn't (delta = 1 line per new key).

```bash
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)

# repos_in_scope: env-var override else canonical REPOS array from Step 4
if [ -n "${WAVE_SCOPE_REPOS:-}" ]; then
  REPOS_IN_SCOPE_JSON=$(printf '%s\n' $WAVE_SCOPE_REPOS | jq -Rnc '[inputs]')
else
  REPOS_IN_SCOPE_JSON=$(printf '%s\n' "${REPOS[@]}" | jq -Rnc '[inputs]')
fi

# wave_{M}_scope: WAVE_SCOPE_STRUCTURED if owner pre-built it, else minimal derived shape
if [ -n "${WAVE_SCOPE_STRUCTURED:-}" ]; then
  # Validate it is a JSON object before passing through
  echo "$WAVE_SCOPE_STRUCTURED" | jq -e 'type == "object"' > /dev/null || {
    echo "ERROR: WAVE_SCOPE_STRUCTURED is not a JSON object"; exit 1;
  }
  SCOPE_JSON="$WAVE_SCOPE_STRUCTURED"
else
  # Minimal deterministic shape from earlier steps
  DECLARED_JSON=$(jq -Rnc '[inputs]' < /tmp/wavescope-{M}-declared-issues.txt)
  CF_JSON=$(printf '%s\n' "${CARRY_FORWARDS[@]:-}" | jq -Rnc '[inputs | select(. != "")]')
  MI_JSON=$(printf '%s\n' "${MUST_INCLUDES[@]:-}" | jq -Rnc '[inputs | select(. != "")]')
  SCOPE_JSON=$(jq -nc \
    --argjson d "$DECLARED_JSON" \
    --argjson c "$CF_JSON" \
    --argjson m "$MI_JSON" \
    '{declared_refs: $d, carry_forwards: $c, must_includes: $m}')
fi

UPSERT_ARGS=(
  "wave_{M}_scope_reconciled_at=$(jq -nc --arg t "$TS" '$t')"
  "wave_{M}_repos_in_scope=$REPOS_IN_SCOPE_JSON"
  "wave_{M}_meta_issue=$META_ISSUE"
  "wave_{M}_scope=$SCOPE_JSON"
)

if [ -n "${SCOPE_RECONCILIATION_NOTE:-}" ]; then
  UPSERT_ARGS+=("wave_{M}_scope_reconciliation_note=$(jq -nc --arg n "$SCOPE_RECONCILIATION_NOTE" '$n')")
fi

python3 "$REPO_ROOT/.claude/skills/wave-scope/upsert_status_keys.py" \
  "$REPO_ROOT/cross-repo-status.json" \
  "${UPSERT_ARGS[@]}"

echo "  wave_{M}_scope_reconciled_at = $TS"
echo "  wave_{M}_repos_in_scope      = $REPOS_IN_SCOPE_JSON"
echo "  wave_{M}_meta_issue          = $META_ISSUE"
echo "  wave_{M}_scope               = $(echo "$SCOPE_JSON" | jq -c 'keys')"
```

The helper validates JSON pre- and post-write, replaces top-level keys in place when they already exist, and inserts new keys after the most-recent `wave_{N}_*` sibling line. Idempotent — re-running with identical values produces zero diff (re-confirmed via P3W6 #278 dry-run on a fictional `wave_99_*` shape).

**Why these four are the canonical bookkeeping shape.** `/wave-kickoff` Step 0 STOPs unconditionally without `wave_{M}_repos_in_scope` (it iterates the array for branch creation, label application, and kickoff comments). `wave_{M}_meta_issue` lets retro/wrapup skills find the meta-issue without re-querying GitHub. `wave_{M}_scope` is the structured payload retros and audits read for tier-by-tier breakdown. Writing all three at scope-reconciliation time eliminates the W5 silent-zero-write and W6 in-band-repair patterns observed before #278.

The optional `wave_{M}_scope_reconciliation_note` is for capturing edge cases (e.g., "no drift; no memory must-includes; manual run because skill not yet built"). Set `SCOPE_RECONCILIATION_NOTE` in the environment before invoking the helper if there is a non-trivial summary worth preserving for the next retro.

The companion read-side check is `/wave-kickoff` SKILL.md § 0a — it stops kickoff if this timestamp is missing or predates the prior wave's retro.

## Relationship to other wave skills

| Skill | Timing | Output |
|---|---|---|
| `/wave-retro` | End of wave N | Carry-forward list, deferred items, trust updates |
| **`/wave-scope`** | **Between waves** | **Declared-vs-labeled reconciled; meta-issue refreshed** |
| `/wave-start` | Start of wave N+1 | Branch creation, label setup |
| `/wave-kickoff` | Start of wave N+1 | Issue assignment, kickoff comments, execution plan |
| `/wave-wrapup` | Near end of wave N | PR merge sequencing |
| `/wave-audit` | End of wave N | Close orphans against merged PRs |

`/wave-kickoff` currently assumes the meta-issue reflects reality. This skill makes that assumption true.

## What remains manual

- **Step 7** — disposition per unscoped item is owner judgment. The skill cannot decide keep-vs-defer-vs-close; it can only present the items and apply the result.
- **Step 11** — section categories on the refreshed meta-issue are owner judgment. The skill proposes; owner confirms.
- **Process-gap escalation** — when a memory must-include points to a closed/non-existent issue, the skill surfaces but does not auto-clean the memory file (that's a follow-up the owner triages).

## Idempotency

Re-running `/wave-scope` after an initial pass should:
- Find drift = 0 if labels match the refreshed meta-issue.
- Re-fold any new must-includes added to memory since the prior pass (cheap re-check).
- Be safe to abort at any step before step 10 — only step 10 (label churn) and step 11 (meta-issue PATCH) mutate state.
- Step 13's four `wave_{M}_*` JSON-write keys are upserted via `upsert_status_keys.py`: identical values produce zero diff, novel values produce 1 line per new key (plus replace-in-place when already present). This is the load-bearing shape #278 closed — no full-file reformat, no churn.

## Promotion provenance

- **Origin:** Conversation during W10 planning (2026-04-23) — owner walked through the 10-step pattern manually after the W10 scope-pass found 30 drift items and a missing must-include (`user-service#63`).
- **Promotion target:** skill (orchestration with one human-judgment gate; not a hook).
- **Issue:** noorinalabs-main#196.
