"""Tests for check_worktree_merged — patch-id-based merged classification
(main#1212, sibling of #1177).

Every test drives REAL git against a throwaway temp repo so the plumbing is
exercised end-to-end (ancestry probe, merge-base, `git log -p`/`git diff`
piped through `git patch-id --stable`, and `git cherry`). Coverage matches
the issue's acceptance criteria:

  * merge-commit merged            -> merged / ancestor (fast path)
  * squash merged, single commit   -> merged / content-equivalent (aggregate
                                       patch-id match)
  * squash merged, multi-commit    -> merged / content-equivalent (no single
                                       original commit's patch-id would match
                                       the squash commit — this is the case a
                                       per-commit `git cherry` alone cannot
                                       catch; the aggregate whole-branch-diff
                                       patch-id test is what catches it)
  * rebase-merge (replayed commits, new hashes, same content)  -> merged /
                                       content-equivalent (per-commit
                                       `git cherry` match — the aggregate
                                       test does NOT match here because two
                                       separate main commits, not one, each
                                       account for one original commit)
  * cherry-pick (new commit, same diff)                        -> merged /
                                       content-equivalent
  * partially-landed: squashed history PLUS one extra unlanded commit on the
    tip -> unmerged / unlanded-changes (must stay FLAGGED)
  * never-merged (no relation to remote_ref content at all)    -> unmerged /
                                       unlanded-changes
  * orphan branch (no common ancestor at all)                  -> unmerged /
                                       no-common-ancestor
  * ancestry probe itself errors (bad rev)                     -> error /
                                       ancestor-check-failed, never "merged"
  * content-check machinery errors (injected failing pipe_runner) -> unmerged
                                       / content-check-failed (degrades
                                       safely, never "merged")
  * CLI exit code mirrors `.merged` (0 iff merged, 1 otherwise)
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from collections.abc import Sequence
from pathlib import Path
from tempfile import TemporaryDirectory

# Helper lives at .claude/lib/check_worktree_merged.py; this test is at
# .claude/lib/tests/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from check_worktree_merged import (  # noqa: E402
    PipeRunner,
    classify_merged,
)
from check_worktree_merged import (
    main as cli_main,
)

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
    """Like _git but does not raise on non-zero (for probing commands)."""
    return subprocess.run(
        ["git", *_IDENT, *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def _git_pipe_real(
    args: Sequence[str], cwd: Path, input_text: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *_IDENT, *args],
        cwd=str(cwd),
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
    )


def _write(repo: Path, name: str, content: str) -> None:
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _commit(repo: Path, name: str, content: str, msg: str) -> str:
    _write(repo, name, content)
    _git(["add", name], repo)
    _git(["commit", "-m", msg], repo)
    return _git(["rev-parse", "HEAD"], repo).stdout.strip()


def _head(repo: Path) -> str:
    return _git(["rev-parse", "HEAD"], repo).stdout.strip()


class CheckWorktreeMergedTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.repo = Path(self._tmp.name) / "repo"
        self.repo.mkdir()
        _git(["init", "-b", "main"], self.repo)
        _commit(self.repo, "README.md", "hello\n", "initial commit")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _classify(self, head: str, remote_ref: str = "main", **kwargs: object):
        # Route through the identity-scoped git wrappers so temp-repo commits
        # never fall back to an ambient (unset) user.name/email.
        return classify_merged(
            self.repo,
            head,
            remote_ref,
            runner=_git_ok,
            pipe_runner=_git_pipe_real,
            **kwargs,  # type: ignore[arg-type]
        )

    # ---- fast path: ancestry ------------------------------------------------

    def test_merge_commit_merged_is_ancestor(self) -> None:
        _git(["checkout", "-b", "feature"], self.repo)
        _commit(self.repo, "a.txt", "A\n", "feature commit")
        feature_tip = _head(self.repo)

        _git(["checkout", "main"], self.repo)
        _git(["merge", "--no-ff", "-m", "merge feature", "feature"], self.repo)

        result = self._classify(feature_tip)
        self.assertEqual(result.status, "merged")
        self.assertEqual(result.reason, "ancestor")
        self.assertTrue(result.merged)

    # ---- patch-id content-equivalence fallback ------------------------------

    def test_squash_merged_single_commit(self) -> None:
        _git(["checkout", "-b", "feature"], self.repo)
        _commit(self.repo, "a.txt", "A\n", "feature commit")
        feature_tip = _head(self.repo)

        _git(["checkout", "main"], self.repo)
        _git(["merge", "--squash", "feature"], self.repo)
        _git(["commit", "-m", "squash feature"], self.repo)

        # Ancestry must fail first (squash commit is single-parent onto main).
        anc = _git_ok(["merge-base", "--is-ancestor", feature_tip, "main"], self.repo)
        self.assertNotEqual(anc.returncode, 0)

        result = self._classify(feature_tip)
        self.assertEqual(result.status, "merged")
        self.assertEqual(result.reason, "content-equivalent")
        self.assertIn("patch-id", result.detail)

    def test_squash_merged_multi_commit(self) -> None:
        """No single commit's patch-id matches the squash — must still classify
        merged, via the AGGREGATE (whole-branch-diff) patch-id test."""
        _git(["checkout", "-b", "feature"], self.repo)
        _commit(self.repo, "a.txt", "A\n", "feature commit 1")
        _commit(self.repo, "b.txt", "B\n", "feature commit 2")
        feature_tip = _head(self.repo)

        _git(["checkout", "main"], self.repo)
        _git(["merge", "--squash", "feature"], self.repo)
        _git(["commit", "-m", "squash feature (2 commits)"], self.repo)

        # Confirm the premise: per-commit git cherry alone would NOT find an
        # equivalent (this is exactly the gap the aggregate test closes).
        cherry = _git_ok(["cherry", "main", feature_tip], self.repo)
        self.assertTrue(
            all(line.startswith("+ ") for line in cherry.stdout.splitlines() if line),
            "premise check: expected git cherry to find no per-commit equivalents",
        )

        result = self._classify(feature_tip)
        self.assertEqual(result.status, "merged")
        self.assertEqual(result.reason, "content-equivalent")
        self.assertIn("patch-id", result.detail)

    def test_rebase_merged_replayed_commits(self) -> None:
        """Rebase-merge: commits replayed onto main with new hashes, same diffs.

        The aggregate test does NOT match here (two separate main commits,
        not one, each carry one original commit's diff) — this exercises the
        per-commit `git cherry` fallback."""
        _git(["checkout", "-b", "feature"], self.repo)
        c1 = _commit(self.repo, "a.txt", "A\n", "feature commit 1")
        c2 = _commit(self.repo, "b.txt", "B\n", "feature commit 2")
        feature_tip = _head(self.repo)

        # main must diverge from feature's base first, otherwise a cherry-pick
        # onto an unmoved main reproduces the identical commit hash (same
        # parent/tree/author-date/committer-date) rather than a new one — this
        # is what a real rebase-merge looks like: other work landed on main
        # in between, so the replayed commits get new parents/hashes.
        _git(["checkout", "main"], self.repo)
        _commit(self.repo, "unrelated.txt", "other work landed on main\n", "unrelated main commit")

        # Simulate GitHub's rebase-merge: replay each original commit onto the
        # current main tip via cherry-pick, producing new commit hashes with
        # identical content deltas.
        _git(["cherry-pick", c1], self.repo)
        _git(["cherry-pick", c2], self.repo)

        anc = _git_ok(["merge-base", "--is-ancestor", feature_tip, "main"], self.repo)
        self.assertNotEqual(anc.returncode, 0)

        result = self._classify(feature_tip)
        self.assertEqual(result.status, "merged")
        self.assertEqual(result.reason, "content-equivalent")
        self.assertIn("git cherry", result.detail)

    def test_cherry_picked_single_commit(self) -> None:
        _git(["checkout", "-b", "feature"], self.repo)
        c1 = _commit(self.repo, "a.txt", "A\n", "feature commit")
        feature_tip = _head(self.repo)

        # See test_rebase_merged_replayed_commits: main must diverge first or
        # the cherry-pick reproduces the identical commit hash.
        _git(["checkout", "main"], self.repo)
        _commit(self.repo, "unrelated.txt", "other work landed on main\n", "unrelated main commit")
        _git(["cherry-pick", c1], self.repo)

        result = self._classify(feature_tip)
        self.assertEqual(result.status, "merged")
        self.assertEqual(result.reason, "content-equivalent")

    # ---- safety guard: must stay FLAGGED -----------------------------------

    def test_partially_landed_tip_has_one_extra_unlanded_commit(self) -> None:
        """Squashed history landed, but the branch tip has grown one more
        commit since — must still classify unmerged (never auto-removed)."""
        _git(["checkout", "-b", "feature"], self.repo)
        _commit(self.repo, "a.txt", "A\n", "feature commit 1")
        _commit(self.repo, "b.txt", "B\n", "feature commit 2")

        _git(["checkout", "main"], self.repo)
        _git(["merge", "--squash", "feature"], self.repo)
        _git(["commit", "-m", "squash feature (2 commits)"], self.repo)

        # Back on feature, add a third, never-landed commit.
        _git(["checkout", "feature"], self.repo)
        c3 = _commit(self.repo, "c.txt", "C (unlanded)\n", "feature commit 3 (not merged)")
        feature_tip = _head(self.repo)

        result = self._classify(feature_tip)
        self.assertEqual(result.status, "unmerged")
        self.assertEqual(result.reason, "unlanded-changes")
        self.assertFalse(result.merged)
        self.assertIn(c3, result.unmatched_commits)

    def test_never_merged(self) -> None:
        _git(["checkout", "-b", "feature"], self.repo)
        c1 = _commit(self.repo, "a.txt", "A\n", "feature commit, never merged")
        feature_tip = _head(self.repo)

        result = self._classify(feature_tip)
        self.assertEqual(result.status, "unmerged")
        self.assertEqual(result.reason, "unlanded-changes")
        self.assertFalse(result.merged)
        self.assertIn(c1, result.unmatched_commits)

    def test_orphan_branch_no_common_ancestor(self) -> None:
        _git(["checkout", "--orphan", "orphan-feature"], self.repo)
        _git(["rm", "-rf", "--cached", "."], self.repo)
        _commit(self.repo, "z.txt", "Z\n", "unrelated history")
        orphan_tip = _head(self.repo)

        result = self._classify(orphan_tip)
        self.assertEqual(result.status, "unmerged")
        self.assertEqual(result.reason, "no-common-ancestor")
        self.assertFalse(result.merged)

    def test_bad_head_ref_is_error_not_merged(self) -> None:
        bogus = "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"
        result = self._classify(bogus)
        self.assertEqual(result.status, "error")
        self.assertEqual(result.reason, "ancestor-check-failed")
        self.assertFalse(result.merged)

    def test_content_check_failure_degrades_to_unmerged(self) -> None:
        """A git-command failure mid content-check must degrade to the
        pre-fix (ancestry-only) conclusion — never guess merged."""
        _git(["checkout", "-b", "feature"], self.repo)
        _commit(self.repo, "a.txt", "A\n", "feature commit")
        feature_tip = _head(self.repo)
        _git(["checkout", "main"], self.repo)
        _git(["merge", "--squash", "feature"], self.repo)
        _git(["commit", "-m", "squash feature"], self.repo)

        calls = {"n": 0}

        def flaky_pipe(
            args: Sequence[str], cwd: Path, input_text: str
        ) -> subprocess.CompletedProcess[str]:
            calls["n"] += 1
            return subprocess.CompletedProcess(
                args=["git", *args], returncode=128, stdout="", stderr="simulated failure"
            )

        pipe_runner: PipeRunner = flaky_pipe
        result = classify_merged(
            self.repo, feature_tip, "main", runner=_git_ok, pipe_runner=pipe_runner
        )
        self.assertEqual(result.status, "unmerged")
        self.assertEqual(result.reason, "content-check-failed")
        self.assertFalse(result.merged)
        self.assertGreaterEqual(calls["n"], 1)

    def test_trivial_no_diff_over_merge_base(self) -> None:
        """head == merge_base with remote_ref (no unique commits at all)."""
        _git(["checkout", "-b", "feature"], self.repo)
        feature_tip = _head(self.repo)  # same commit as main, no new commits

        result = self._classify(feature_tip)
        # Ancestor test already covers this (feature_tip IS main's tip here),
        # so the fast path fires — still "merged", just via ancestor.
        self.assertTrue(result.merged)

    # ---- CLI ----------------------------------------------------------------

    def test_cli_exit_code_matches_merged(self) -> None:
        _git(["checkout", "-b", "feature"], self.repo)
        _commit(self.repo, "a.txt", "A\n", "feature commit")
        feature_tip = _head(self.repo)
        _git(["checkout", "main"], self.repo)
        _git(["merge", "--squash", "feature"], self.repo)
        _git(["commit", "-m", "squash feature"], self.repo)

        rc = cli_main([str(self.repo), feature_tip, "main"])
        self.assertEqual(rc, 0)

    def test_cli_exit_code_nonzero_when_unmerged(self) -> None:
        _git(["checkout", "-b", "feature"], self.repo)
        _commit(self.repo, "a.txt", "A\n", "never merged")
        feature_tip = _head(self.repo)

        rc = cli_main([str(self.repo), feature_tip, "main"])
        self.assertEqual(rc, 1)

    def test_cli_usage_error(self) -> None:
        rc = cli_main([str(self.repo)])
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
