"""Tests for sync_main — the deterministic, side-effect-guarded fast-forward of
the local default branch to its remote (main#713).

Each test drives REAL git against throwaway temp repos (a bare "remote" plus
working clones) so the plumbing is exercised end-to-end. Coverage:

  * behind + clean              -> fast-forwarded
  * already current             -> up-to-date (no-op)
  * not on the target branch    -> skipped-not-on-branch
  * local ahead only            -> refused-ahead (never force-pushes/rewrites)
  * local + remote diverged     -> refused-diverged
  * real tracked local change   -> refused-dirty (never discards work)
  * only generated-allowlist     -> stashed around ff and restored
  * _parse_dirty                -> excludes untracked/ignored, follows renames
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from collections.abc import Sequence
from pathlib import Path
from tempfile import TemporaryDirectory

# Helper lives at .claude/lib/sync_main.py; this test is at .claude/lib/tests/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sync_main import GENERATED_ALLOWLIST, _parse_dirty, sync_main  # noqa: E402

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


def _commit(repo: Path, name: str, content: str, msg: str) -> None:
    (repo / name).write_text(content)
    _git(["add", name], repo)
    _git(["commit", "-m", msg], repo)


class SyncMainTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        base = Path(self._tmp.name)
        self.remote = base / "remote.git"
        self.local = base / "local"
        self.other = base / "other"
        _git(["init", "--bare", "-b", "main", str(self.remote)], base)

        _git(["clone", str(self.remote), str(self.local)], base)
        _git(["checkout", "-b", "main"], self.local)
        _commit(self.local, "README.md", "v1\n", "init")
        _git(["push", "-u", "origin", "main"], self.local)

        _git(["clone", str(self.remote), str(self.other)], base)
        _git(["checkout", "main"], self.other)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _advance_remote(self) -> None:
        """Push a new commit to the remote via the 'other' clone."""
        _commit(self.other, "README.md", "v2\n", "remote advance")
        _git(["push", "origin", "main"], self.other)

    # ----- happy paths --------------------------------------------------

    def test_fast_forward_when_behind_and_clean(self) -> None:
        self._advance_remote()
        before = _git(["rev-parse", "HEAD"], self.local).stdout.strip()
        res = sync_main(self.local)
        self.assertTrue(res.ok)
        self.assertEqual(res.status, "fast-forwarded")
        self.assertEqual(res.behind, 1)
        self.assertEqual(res.ahead, 0)
        after = _git(["rev-parse", "HEAD"], self.local).stdout.strip()
        self.assertNotEqual(before, after)
        self.assertEqual((self.local / "README.md").read_text(), "v2\n")

    def test_up_to_date_noop(self) -> None:
        res = sync_main(self.local)
        self.assertTrue(res.ok)
        self.assertEqual(res.status, "up-to-date")
        self.assertEqual(res.behind, 0)

    def test_skipped_when_not_on_branch(self) -> None:
        _git(["checkout", "-b", "feature/x"], self.local)
        self._advance_remote()
        res = sync_main(self.local)
        self.assertTrue(res.ok)
        self.assertEqual(res.status, "skipped-not-on-branch")
        # Did NOT move the feature branch.
        self.assertEqual((self.local / "README.md").read_text(), "v1\n")

    # ----- refusals -----------------------------------------------------

    def test_refused_when_ahead(self) -> None:
        _commit(self.local, "local.txt", "local\n", "local-only commit")
        res = sync_main(self.local)
        self.assertTrue(res.ok)  # refusal is a safe outcome
        self.assertEqual(res.status, "refused-ahead")
        self.assertGreaterEqual(res.ahead, 1)

    def test_refused_when_diverged(self) -> None:
        self._advance_remote()
        _commit(self.local, "local.txt", "local\n", "local-only commit")
        res = sync_main(self.local)
        self.assertTrue(res.ok)
        self.assertEqual(res.status, "refused-diverged")
        self.assertGreaterEqual(res.ahead, 1)
        self.assertGreaterEqual(res.behind, 1)

    def test_refused_when_real_dirty(self) -> None:
        self._advance_remote()
        (self.local / "README.md").write_text("uncommitted edit\n")
        res = sync_main(self.local)
        self.assertTrue(res.ok)
        self.assertEqual(res.status, "refused-dirty")
        self.assertIn("README.md", res.dirty)
        # Fast-forward did NOT happen — local content preserved.
        self.assertEqual((self.local / "README.md").read_text(), "uncommitted edit\n")

    def test_generated_allowlist_stashed_and_restored(self) -> None:
        # Track an allowlisted generated file, then dirty it while behind.
        gen = next(iter(GENERATED_ALLOWLIST))
        gpath = self.local / gen
        gpath.parent.mkdir(parents=True, exist_ok=True)
        gpath.write_text("line1\n")
        _git(["add", gen], self.local)
        _git(["commit", "-m", "track generated log"], self.local)
        _git(["push", "origin", "main"], self.local)
        # other must catch up so a later remote advance is a clean ff for local.
        _git(["pull", "origin", "main"], self.other)

        self._advance_remote()
        gpath.write_text("line1\nlocal-append\n")  # dirty the generated file

        res = sync_main(self.local)
        self.assertTrue(res.ok)
        self.assertEqual(res.status, "fast-forwarded")
        # Remote change landed AND the local generated append was restored.
        self.assertEqual((self.local / "README.md").read_text(), "v2\n")
        self.assertEqual(gpath.read_text(), "line1\nlocal-append\n")

    # ----- _parse_dirty unit -------------------------------------------

    def test_parse_dirty_excludes_untracked_and_follows_rename(self) -> None:
        porcelain = (
            " M src/a.py\n?? new_untracked.py\n!! ignored.log\n"
            "R  old.py -> renamed.py\nA  added.py\n"
        )
        self.assertEqual(
            _parse_dirty(porcelain),
            ["src/a.py", "renamed.py", "added.py"],
        )


if __name__ == "__main__":
    unittest.main()
