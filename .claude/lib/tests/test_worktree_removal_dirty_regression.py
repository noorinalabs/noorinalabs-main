"""Regression test pinning session-start Step 0's worktree-removal blast
radius (PR #1213 review; owner decision 2026-08-02, round 3).

`/session-start` Step 0's removal path (`.claude/skills/session-start/
SKILL.md`) used to be:

    git -C "$repo" worktree remove "$wt" 2>/dev/null \\
      || git -C "$repo" worktree remove --force "$wt" 2>/dev/null \\
      || FLAGGED+=("REMOVE-FAILED  $repo :: $wt")

Verified end to end (round 2): plain `git worktree remove` refuses on a
worktree with uncommitted (tracked-modified or untracked) content; the
`--force` fallback then succeeded and permanently deleted that uncommitted
content from disk.

**Round 3, owner decision: the `--force` fallback is REMOVED.** A worktree
that does not remove cleanly is now FLAGGED for a manual decision, never
force-removed:

    if git -C "$repo" worktree remove "$wt" 2>/dev/null; then
      echo "removed merged worktree: $wt ($_mreason)"
    else
      FLAGGED+=("DIRTY  $repo :: $wt (merged but remove refused ...)")
    fi

This file now pins the NEW behaviour: a dirty worktree survives entirely —
both its uncommitted content AND (as before) its committed content/branch —
because Step 0 simply never attempts the destructive fallback. With
`--force` gone, the only cost of a `check_worktree_merged.py`
misclassification is a stale worktree *directory* sitting FLAGGED until a
human looks at it; no data of any kind (committed or not) is at risk.
"""

from __future__ import annotations

import subprocess
import unittest
from collections.abc import Sequence
from pathlib import Path
from tempfile import TemporaryDirectory

_IDENT = [
    "-c",
    "user.name=Test",
    "-c",
    "user.email=test@example.com",
    "-c",
    "commit.gpgsign=false",
]


def _git(args: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *_IDENT, *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
    )


def _git_ok(args: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *_IDENT, *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


class WorktreeRemovalDirtyRegressionTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        base = Path(self._tmp.name)
        self.repo = base / "repo"
        self.repo.mkdir()
        _git(["init", "-b", "main"], self.repo)
        (self.repo / "README.md").write_text("hello\n")
        _git(["add", "README.md"], self.repo)
        _git(["commit", "-m", "initial commit"], self.repo)

        self.worktree_path = base / "wt-feature"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_plain_remove_refuses_on_dirty_worktree(self) -> None:
        """Premise fact Step 0's FLAGGED path depends on: a plain
        `git worktree remove` genuinely refuses when the worktree has
        uncommitted/untracked content in the way."""
        _git(
            ["worktree", "add", str(self.worktree_path), "-b", "feat-dirty"],
            self.repo,
        )
        (self.worktree_path / "PRECIOUS-uncommitted.txt").write_text("never committed\n")

        result = _git_ok(["worktree", "remove", str(self.worktree_path)], self.repo)
        self.assertNotEqual(
            result.returncode,
            0,
            "premise: plain `git worktree remove` must refuse on a dirty worktree",
        )
        self.assertIn("contains modified or untracked files", result.stderr + result.stdout)
        # Refused, so nothing was touched.
        self.assertTrue(self.worktree_path.exists())
        self.assertTrue((self.worktree_path / "PRECIOUS-uncommitted.txt").exists())

    def test_no_force_means_all_content_survives_a_refused_remove(self) -> None:
        """Step 0 (post-owner-decision, round 3) no longer calls
        `git worktree remove --force` at all -- a worktree that cannot be
        removed cleanly is FLAGGED and left completely untouched. Pin that
        "left untouched" really does mean everything survives: not just the
        branch and its commits (which `worktree remove` never threatened
        anyway), but now the uncommitted content too, since the destructive
        fallback that used to reach it is simply never invoked."""
        _git(
            ["worktree", "add", str(self.worktree_path), "-b", "feat-dirty"],
            self.repo,
        )
        # Committed content on the branch.
        (self.worktree_path / "landed.txt").write_text("this IS committed\n")
        _git(["add", "landed.txt"], self.worktree_path)
        _git(["commit", "-m", "a real commit on feat-dirty"], self.worktree_path)
        branch_tip = _git(["rev-parse", "HEAD"], self.worktree_path).stdout.strip()

        # Uncommitted content -- what a misclassification used to cost.
        precious = self.worktree_path / "PRECIOUS-uncommitted.txt"
        precious.write_text("never committed -- must survive a refused remove\n")

        # Step 0's ENTIRE removal attempt, post-round-3: a single plain
        # `git worktree remove`, nothing else, no --force fallback.
        result = _git_ok(["worktree", "remove", str(self.worktree_path)], self.repo)
        self.assertNotEqual(result.returncode, 0, "premise: plain remove refuses (dirty)")

        # Because there is no second, forcing attempt, EVERYTHING survives:
        # the worktree directory, the uncommitted file, and (as always) the
        # branch and its commit.
        self.assertTrue(self.worktree_path.exists())
        self.assertTrue(precious.exists())
        self.assertEqual(precious.read_text(), "never committed -- must survive a refused remove\n")

        branch_check = _git_ok(["rev-parse", "--verify", "feat-dirty"], self.repo)
        self.assertEqual(branch_check.returncode, 0)
        self.assertEqual(branch_check.stdout.strip(), branch_tip)

        show = _git_ok(["show", f"{branch_tip}:landed.txt"], self.repo)
        self.assertEqual(show.returncode, 0)
        self.assertEqual(show.stdout, "this IS committed\n")


if __name__ == "__main__":
    unittest.main()
