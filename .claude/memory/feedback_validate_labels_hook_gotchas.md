---
name: feedback_validate_labels_hook_gotchas
description: validate_labels PreToolUse hook has two false-block modes — body-text over-match + stale label cache; how to work around
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 44d2d904-df74-40d3-b13d-f18441e349aa
---

The `validate_labels` PreToolUse hook (label-existence gate on `gh issue create/edit`) has **two** false-block modes, both hit during P4W7 (2026-06-13/14):

1. **Body over-match** — it matches label-shaped tokens in the issue `--body`/`--body-file` content, not just `--label` flag values. A body documenting a wave-label pattern (`p{N}-wave-{M}` in backticks) false-blocked `gh issue create` even though `--label` named only `bug`. **Workaround:** reword the body to avoid label-shaped tokens (e.g. `p<N>-wave-<M>`). Filed as main#661.

2. **Stale label cache** — a label created earlier in the same session (e.g. `gh label create phase-5`) is NOT seen by the hook on a subsequent `gh issue create --label phase-5` → "label does not exist" block, even though `gh api repos/.../labels/phase-5` confirms it exists. **Workaround:** create the label, verify via `gh api .../labels/<name>` (NOT `gh label list --search`, which fuzzy-matches and won't surface an exact new label), then retry the issue create — the cache refreshes across tool calls.

**Why:** same parser-scoping class — #650 (EDIT path, fixed) → #659 (CREATE path) → #661 (validate_labels). Owner-adopted charter invariant main#663 governs the durable fix. **How to apply:** when a new-label issue-create blocks, don't assume the label is missing — `gh api` verify, then retry; and keep label-shaped tokens out of issue bodies.
