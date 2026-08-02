"""Regression test pinning session-start Step 0's worktree-removal blast
radius (PR #1213 review, "also add" item 7).

`/session-start` Step 0's removal path (`.claude/skills/session-start/
SKILL.md`) is:

    git -C "$repo" worktree remove "$wt" 2>/dev/null \\
      || git -C "$repo" worktree remove --force "$wt" 2>/dev/null \\
      || FLAGGED+=("REMOVE-FAILED  $repo :: $wt")

This test does NOT change that behaviour (the review explicitly asked that
it not be changed here) — it exists only to make the cost of a `merged`
misclassification visible in the suite, so a future change to this fallback
is a deliberate, reviewed decision rather than a silent regression.

Verified end to end: plain `git worktree remove` refuses on a worktree with
uncommitted (tracked-modified or untracked) content; the `--force` fallback
then succeeds and permanently deletes that uncommitted content from disk.
Anything actually COMMITTED on the worktree's branch is unaffected — the
branch ref is not touched by `worktree remove` at all (with or without
`--force`), only the *worktree checkout directory* is. So a false `merged`
verdict from `check_worktree_merged.py` costs, at most, whatever was
uncommitted in that worktree at the time — never a committed commit, and
never the branch itself (still recoverable via `git checkout <branch>` or
the reflog after the fact).
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

    def test_force_fallback_destroys_uncommitted_content_but_preserves_branch(self) -> None:
        """This is the exact two-step sequence Step 0 runs: plain remove,
        then `--force` on refusal. Committed content (the branch, its
        commits) survives; uncommitted content does not."""
        _git(
            ["worktree", "add", str(self.worktree_path), "-b", "feat-dirty"],
            self.repo,
        )
        # Committed content on the branch, to prove it survives.
        (self.worktree_path / "landed.txt").write_text("this IS committed\n")
        _git(["add", "landed.txt"], self.worktree_path)
        _git(["commit", "-m", "a real commit on feat-dirty"], self.worktree_path)
        branch_tip = _git(["rev-parse", "HEAD"], self.worktree_path).stdout.strip()

        # Uncommitted content, to prove it does NOT survive a misclassification.
        precious = self.worktree_path / "PRECIOUS-uncommitted.txt"
        precious.write_text("never committed — this is what a false `merged` costs\n")

        plain = _git_ok(["worktree", "remove", str(self.worktree_path)], self.repo)
        self.assertNotEqual(plain.returncode, 0)

        forced = _git_ok(["worktree", "remove", "--force", str(self.worktree_path)], self.repo)
        self.assertEqual(
            forced.returncode,
            0,
            f"premise: --force must succeed where plain remove refused: {forced.stderr}",
        )

        # The uncommitted file is gone — this is the actual blast radius of a
        # false `merged` verdict feeding this removal path.
        self.assertFalse(precious.exists())
        self.assertFalse(self.worktree_path.exists())

        # But the branch — and every commit on it, including the one made
        # inside the now-deleted worktree — is untouched. `worktree remove`
        # (with or without --force) never deletes the branch ref.
        branch_check = _git_ok(["rev-parse", "--verify", "feat-dirty"], self.repo)
        self.assertEqual(branch_check.returncode, 0)
        self.assertEqual(branch_check.stdout.strip(), branch_tip)

        show = _git_ok(["show", f"{branch_tip}:landed.txt"], self.repo)
        self.assertEqual(show.returncode, 0)
        self.assertEqual(show.stdout, "this IS committed\n")


if __name__ == "__main__":
    unittest.main()
