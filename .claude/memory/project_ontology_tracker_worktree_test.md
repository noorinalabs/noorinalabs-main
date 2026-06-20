---
name: project_ontology_tracker_worktree_test
description: pre-push pytest false-fails in .claude/worktrees/ because REPO_ROOT inherits a .worktrees segment
metadata: 
  node_type: memory
  type: project
  originSessionId: b923c0f4-c87a-4bed-b4b8-91a79287509b
---

`.claude/hooks/tests/test_ontology_tracker.py::ShouldSkipTopLevelWorktreesTests::test_worktrees_segment_not_substring_false_match` **false-fails when run from a worktree under `.claude/worktrees/`**. `ontology_tracker.REPO_ROOT = Path(__file__).resolve().parent.parent.parent` resolves to the worktree root (e.g. `.../.claude/worktrees/0684-charter`), which itself contains a `.claude/worktrees` path segment, so `_is_worktree_path(REPO_ROOT/"docs"/"notes.worktrees.md")` returns True from REPO_ROOT's own location — not the fixture. Asserts False → fails.

**Green everywhere else:** passes on a normal checkout (`REPO_ROOT=/home/parameterization/code/noorinalabs-main`) and in CI (checks out off `.worktrees`). This repo's path-filtered hooks-CI (ruff/mypy/pytest over `.claude/hooks`+`.claude/lib`) only triggers when those dirs change, so markdown-only PRs never hit it as a CI gate — but ANY agent who manually `pre-commit install --hook-type pre-push` in the parent worktree and pushes WILL be blocked locally.

**Implication:** the green-before-push rule ([[feedback_prefer_correct_over_expedient]] family) is satisfied by verifying green on a normal checkout + CI; do NOT `--no-verify` past it. Durable fix = make the test build its fixture path under a non-worktree base (monkeypatch REPO_ROOT or use a tmp dir outside `.worktrees`). Sibling of [[feedback_ruff_parent_config_bleed]] (worktree-location config/path artifacts). Surfaced on main PR #685 (#684 charter parity) — note PR#685 only SURFACED it; the durable fix is NOT yet landed and is tracked by **open main#686** (`tech-debt`+`test`, on project 2). Recurred 2026-06-15 on PR #689 (main#688 wave-counter helper) — second agent encounter, evidence commented on #686. Until #686 lands, push worktree branches from the main checkout root (cwd without a `.worktrees` segment) so the pre-push suite runs genuinely green; never `--no-verify`.

**SIBLING (same class, /tmp instead of .worktrees), found 2026-06-16 on PR#702 (main#663):** `test_block_stale_tmp_message_file.py::NonMatchingTests::test_non_tmp_path_not_matched` false-fails when the checkout lives under `/tmp` (e.g. a `git worktree add /tmp/...`) because the "non-tmp" fixture path resolves under the repo root which IS in `/tmp` → matched → asserts False, fails. So a verification checkout must avoid BOTH a `.worktrees` AND a `/tmp` path component. Confirmed clean run from a neutral base (`/home/parameterization/ci_main663`, detached worktree): 1384 passed / 49 subtests / 0 fail. Practical recipe: `git worktree add --detach /home/<user>/<scratch>` (NOT under `.claude/worktrees/` and NOT `/tmp`) to get a CI-equivalent green run.
