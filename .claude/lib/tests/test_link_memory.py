"""Tests for link_memory — relocate Claude Code project memory in-repo (#732).

Verifies:
  1. canonical_memory_path mirrors the harness cwd-dashing rule.
  2. link_memory creates the symlink when none exists.
  3. Idempotency — a second run is a no-op and reports already-linked.
  4. A pre-existing REAL dir at the canonical path is backed up, never deleted.
  5. A stale/wrong symlink is replaced (no backup needed).
  6. --check is non-mutating and exit-codes correctly.
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

# Helper lives at .claude/lib/link_memory.py; test is at .claude/lib/tests/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from link_memory import canonical_memory_path, link_memory  # noqa: E402


def _init_repo(path: Path) -> None:
    """Make ``path`` a minimal git work tree with an in-repo memory dir."""
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    (path / ".claude" / "memory").mkdir(parents=True)
    (path / ".claude" / "memory" / "MEMORY.md").write_text("- seed\n")


class CanonicalPathTest(unittest.TestCase):
    def test_dashing_rule(self) -> None:
        got = canonical_memory_path(Path("/home/u/code/repo"), home=Path("/home/u"))
        self.assertEqual(
            got,
            Path("/home/u/.claude/projects/-home-u-code-repo/memory"),
        )


class LinkMemoryTest(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        # Separate fake repo dir and fake HOME so the canonical path lands
        # under our temp tree, not the real ~/.claude.
        self.repo = self.root / "code" / "repo"
        self.repo.mkdir(parents=True)
        self.home = self.root / "home"
        self.home.mkdir()
        _init_repo(self.repo)
        self._orig_cwd = Path.cwd()

    def tearDown(self) -> None:
        import os

        os.chdir(self._orig_cwd)
        self._tmp.cleanup()

    def _run(self, **kw) -> int:
        import os

        os.chdir(self.repo)
        return link_memory(home=self.home, quiet=True, **kw)

    def _canonical(self) -> Path:
        return canonical_memory_path(self.repo.resolve(), home=self.home)

    def test_creates_symlink(self) -> None:
        rc = self._run()
        self.assertEqual(rc, 0)
        canon = self._canonical()
        self.assertTrue(canon.is_symlink())
        self.assertEqual(canon.resolve(), (self.repo / ".claude" / "memory").resolve())
        # Content readable through the canonical path.
        self.assertIn("seed", (canon / "MEMORY.md").read_text())

    def test_idempotent(self) -> None:
        self.assertEqual(self._run(), 0)
        self.assertEqual(self._run(), 0)  # second run: already-linked no-op
        self.assertTrue(self._canonical().is_symlink())

    def test_backs_up_real_dir(self) -> None:
        canon = self._canonical()
        canon.parent.mkdir(parents=True)
        canon.mkdir()
        (canon / "keep.md").write_text("precious\n")
        self.assertEqual(self._run(), 0)
        self.assertTrue(canon.is_symlink())
        backups = list(canon.parent.glob("memory.bak.*"))
        self.assertEqual(len(backups), 1, "real dir must be backed up, not lost")
        self.assertIn("precious", (backups[0] / "keep.md").read_text())

    def test_replaces_wrong_symlink(self) -> None:
        canon = self._canonical()
        canon.parent.mkdir(parents=True)
        wrong = self.root / "elsewhere"
        wrong.mkdir()
        canon.symlink_to(wrong)
        self.assertEqual(self._run(), 0)
        self.assertEqual(canon.resolve(), (self.repo / ".claude" / "memory").resolve())
        # A wrong symlink is replaced in place — no backup dir created.
        self.assertEqual(list(canon.parent.glob("memory.bak.*")), [])

    def test_check_is_non_mutating(self) -> None:
        # Not linked yet → --check reports missing (rc 1), creates nothing.
        self.assertEqual(self._run(check=True), 1)
        self.assertFalse(self._canonical().exists())
        # After linking, --check passes (rc 0).
        self.assertEqual(self._run(), 0)
        self.assertEqual(self._run(check=True), 0)


if __name__ == "__main__":
    unittest.main()
