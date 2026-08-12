"""Pin `/session-start` Step 0's *helper-missing* fallback (#1341).

Step 0 has two classification paths, and #1341 was present in BOTH:

  * the tested helper `.claude/lib/check_worktree_merged.py` (covered by
    `test_check_worktree_merged.py`), and
  * the inline shell fallback Step 0 uses when that helper is absent from a
    very old checkout — which was a bare
    ``git merge-base --is-ancestor "$head" origin/main``. A worktree that has
    not committed yet has ``HEAD == origin/main``, so that test passes
    trivially and Step 0 removed a clean, live worktree.

Fixing only the helper would leave the same false-MERGED reachable on the
degraded path, so the mainline guard is replicated there — and this test
**extracts that shell block from `SKILL.md` and executes it verbatim**
(between the ``BEGIN/END legacy-ancestry-fallback`` sentinels) rather than
restating the logic, which would pin a copy and prove nothing about the file
Step 0 actually runs.

The block is executed under **zsh**, the org's real agent/interactive shell
(CLAUDE.md § Shell environment) — bash-only idioms in a Step 0 edit would
silently misbehave in production, so testing it under `sh`/`bash` would be
testing a shell nobody runs it in.
"""

from __future__ import annotations

import shutil
import subprocess
import unittest
from collections.abc import Sequence
from pathlib import Path
from tempfile import TemporaryDirectory

SKILL_MD = Path(__file__).resolve().parents[3] / ".claude" / "skills" / "session-start" / "SKILL.md"
_BEGIN = "# BEGIN legacy-ancestry-fallback"
_END = "# END legacy-ancestry-fallback"

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
        ["git", *_IDENT, *args], cwd=str(cwd), capture_output=True, text=True, check=True
    )


def _commit(repo: Path, name: str, content: str, msg: str) -> str:
    (repo / name).write_text(content)
    _git(["add", name], repo)
    _git(["commit", "-m", msg], repo)
    return _git(["rev-parse", "HEAD"], repo).stdout.strip()


def _extract_fallback() -> str:
    """The Step 0 fallback block, straight out of SKILL.md."""
    text = SKILL_MD.read_text()
    if text.count(_BEGIN) != 1 or text.count(_END) != 1:
        raise AssertionError(
            f"expected exactly one {_BEGIN}/{_END} sentinel pair in {SKILL_MD} — "
            "Step 0's fallback block moved or was duplicated; this test pins it by sentinel"
        )
    # Take everything AFTER the sentinel's own line (a trailing remark on the
    # sentinel line itself is a comment in SKILL.md but bare words here).
    body = text.split(_BEGIN, 1)[1].split("\n", 1)[1].split(_END, 1)[0]
    lines = [line for line in body.splitlines() if line.strip()]
    if not lines:
        raise AssertionError("SKILL.md fallback block is empty between its sentinels")
    return "\n".join(lines)


@unittest.skipIf(shutil.which("zsh") is None, "zsh (the org's shell) not available")
class SessionStartStep0FallbackTest(unittest.TestCase):
    """The shell fallback must reach the same remove/FLAG decision as the
    helper: 0 = remove, 3 = FRESH (merged, nothing of its own), 1 = unmerged."""

    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.repo = Path(self._tmp.name) / "repo"
        self.repo.mkdir()
        _git(["init", "-b", "main"], self.repo)
        _commit(self.repo, "README.md", "hello\n", "initial commit")
        # Step 0 compares against origin/main; stand one up locally so the
        # block runs against the exact ref name it uses in production.
        self._sync_origin()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _sync_origin(self) -> None:
        _git(["update-ref", "refs/remotes/origin/main", "main"], self.repo)

    def _mrc(self, head: str) -> int:
        script = f'repo={self.repo!s}\nhead={head}\n{_extract_fallback()}\nprintf "%s" "$_mrc"\n'
        res = subprocess.run(["zsh", "-c", script], capture_output=True, text=True, check=False)
        self.assertEqual(res.returncode, 0, f"fallback block errored under zsh: {res.stderr}")
        return int(res.stdout.strip())

    def test_fresh_uncommitted_worktree_is_not_removed(self) -> None:
        """THE #1341 CASE on the degraded path: HEAD == origin/main, so the
        old bare ancestry test said "remove" (0). It must now say FRESH (3)."""
        fresh_head = _git(["rev-parse", "HEAD"], self.repo).stdout.strip()
        self.assertEqual(self._mrc(fresh_head), 3)

    def test_fresh_worktree_off_older_origin_main_is_not_removed(self) -> None:
        """Still zero commits of its own after origin/main moves on — the
        case a bare `HEAD == origin/main` equality guard would miss."""
        fresh_head = _git(["rev-parse", "HEAD"], self.repo).stdout.strip()
        _commit(self.repo, "later.txt", "main moved on\n", "unrelated main commit")
        self._sync_origin()
        self.assertEqual(self._mrc(fresh_head), 3)

    def test_merge_commit_merged_branch_is_still_removed(self) -> None:
        """No regression on #526's population: a merged feature tip is
        reachable only through the merge's SECOND parent, so it is an
        ancestor but not on origin/main's first-parent chain."""
        _git(["checkout", "-b", "feature"], self.repo)
        _commit(self.repo, "a.txt", "A\n", "feature commit")
        feature_tip = _git(["rev-parse", "HEAD"], self.repo).stdout.strip()
        _git(["checkout", "main"], self.repo)
        _git(["merge", "--no-ff", "-m", "merge feature", "feature"], self.repo)
        self._sync_origin()

        self.assertEqual(self._mrc(feature_tip), 0)

    def test_unmerged_branch_is_still_flagged(self) -> None:
        _git(["checkout", "-b", "feature"], self.repo)
        _commit(self.repo, "a.txt", "A\n", "never merged")
        feature_tip = _git(["rev-parse", "HEAD"], self.repo).stdout.strip()

        self.assertEqual(self._mrc(feature_tip), 1)


if __name__ == "__main__":
    unittest.main()
