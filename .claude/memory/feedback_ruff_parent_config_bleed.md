---
name: feedback_ruff_parent_config_bleed
description: ruff/mypy local-validation in a child-repo worktree under noorinalabs-main false-passes because ruff discovers the PARENT pyproject.toml (line-length=100); CI checks out child only (bare 88-col default) and fails.
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 7e042acd-06d6-4813-a40c-4eac8f291ea2
---

When validating `ruff format --check` / `ruff check` locally for a CHILD repo whose worktree lives UNDER the parent (`noorinalabs-deploy/.claude/worktrees/...`), ruff walks parent directories and silently picks up `noorinalabs-main/pyproject.toml` (`[tool.ruff] line-length = 100`). CI checks out ONLY the child repo, finds NO ruff config there, and falls back to ruff's **default 88-col** — so a file authored to 100-col passes locally but CI says "would reformat". Same trap applies to any tool with upward config discovery.

**Why:** Local "clean" diverged from CI (sibling of [[feedback_actionlint_needs_shellcheck]] and [[feedback_test_mock_masks_prod_failure]] — environment makes local validation lie). Cost a CI cycle on deploy PR #400 (#326 python-gate) 2026-06-01.

**How to apply:**
- Before trusting a local ruff/mypy run in a nested worktree, run `ruff ... -v 2>&1 | rg -i config` to see WHICH config it found. If it names the parent pyproject, your result is contaminated.
- Reproduce CI's real condition with `ruff format --check --isolated` (ignores all config) OR `--config <child>/ruff.toml`.
- Org convention is `line-length = 100`, `select = ["E","F","W","I"]`, `extend-exclude = [".claude/worktrees"]` (parent pyproject + isnad-graph ruff.toml). A child repo adding a ruff gate needs its OWN `ruff.toml` pinning these so CI ≠ bare defaults — do NOT reformat working scripts down to 88-col.
- mypy `--ignore-missing-imports` does NOT suppress `import-untyped` for an installed-but-unstubbed lib (e.g. `import yaml`) — install the stub package (`types-PyYAML`) in the CI job instead.
