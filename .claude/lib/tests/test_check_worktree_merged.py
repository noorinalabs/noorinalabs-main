"""Tests for check_worktree_merged — patch-id-based merged classification
(main#1212, sibling of #1177; residual-history fix from the PR #1213 review
round).

Every test drives REAL git against a throwaway temp repo so the plumbing is
exercised end-to-end (ancestry probe, merge-base, `git rev-list --reverse`,
`git diff`/`git log -p` piped through `git patch-id --stable`, and
`git cherry`). Coverage matches both the issue's original acceptance
criteria and the review round's must-fix list:

  * merge-commit merged                    -> merged / ancestor (fast path)
  * squash merged, single commit           -> merged / content-equivalent
  * squash merged, multi-commit            -> merged / content-equivalent
    (no single original commit's patch-id would match the squash commit —
    this is the case a per-commit `git cherry` alone cannot catch)
  * rebase-merge (replayed commits, new hashes, same content), where the
    FIRST replayed commit incidentally matches a prefix on its own and the
    rest are corroborated via `git cherry`                -> merged /
    content-equivalent
  * cherry-pick (new commit, same diff)                    -> merged /
    content-equivalent
  * partially-landed: squashed history PLUS one extra unlanded commit on the
    tip -> unmerged / content-matched-with-unlanded-history (must stay
    FLAGGED — the residual, not the matched prefix, decides)
  * cancel-out residual: a landed commit, then an unlanded add + unlanded
    remove whose NET diff is zero -> unmerged / content-matched-with-
    unlanded-history (PR #1213 review must-fix 1 — the earliest-matching-
    prefix search never lets a later cancellation hide an earlier residual)
  * whitespace-only residual: a landed commit, then an unlanded reindent-only
    commit (patch-id is whitespace-insensitive at the aggregate level, but
    the per-commit `git cherry` corroboration still sees it as unmatched)
    -> unmerged / content-matched-with-unlanded-history (must-fix 2)
  * never-merged (no relation to remote_ref content at all)   -> unmerged /
    unlanded-changes
  * orphan branch (no common ancestor at all)                 -> unmerged /
    no-common-ancestor
  * ancestry probe itself errors (bad rev)                    -> error /
    ancestor-check-failed, never "merged"
  * trivial no-op tip (`--allow-empty` commit off main's tip, reaching the
    empty-diff branch for real rather than via the ancestor fast path)
    -> merged / content-equivalent
  * every internal git-command failure/unexpected-result site degrades to
    unmerged, never merged: own diff, rev-list, rev-list-empty-despite-diff
    (defensive), main log, main patch-id, prefix diff, prefix patch-id,
    prefix patch-id producing no output for a non-empty diff (must-fix 6 —
    fail-open guard), and git cherry
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
    GitRunner,
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


def _fail(args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["git", *args], returncode=128, stdout="", stderr="simulated failure"
    )


def _empty_ok(args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["git", *args], returncode=0, stdout="", stderr="")


def _runner_intercepting(subcommand: str, occurrence: int, *, mode: str = "fail") -> GitRunner:
    """A GitRunner that delegates every call to real git, EXCEPT the
    `occurrence`-th call whose `args[0] == subcommand`, which it fails
    (`mode="fail"`) or answers with an empty-but-successful result
    (`mode="empty"`) instead of actually running it.

    Precisely targeting one call site (rather than failing every call, as an
    earlier version of this test file's fake did) is what lets each of
    classify_merged's several degrade-to-unmerged sites be pinned
    independently — a fake that fails everything can only ever prove the
    FIRST site is safe (PR #1213 review, must-fix 2)."""
    seen = {"n": 0}

    def wrapper(args: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        if args and args[0] == subcommand:
            seen["n"] += 1
            if seen["n"] == occurrence:
                return _fail(args) if mode == "fail" else _empty_ok(args)
        return _git_ok(list(args), cwd)

    return wrapper


def _pipe_intercepting(occurrence: int, *, mode: str = "fail") -> PipeRunner:
    """Like `_runner_intercepting`, but for the pipe_runner (`git patch-id`
    calls) — every call is the same subcommand, so occurrence-counting is
    unconditional rather than subcommand-filtered."""
    seen = {"n": 0}

    def wrapper(
        args: Sequence[str], cwd: Path, input_text: str
    ) -> subprocess.CompletedProcess[str]:
        seen["n"] += 1
        if seen["n"] == occurrence:
            return _fail(args) if mode == "fail" else _empty_ok(args)
        return _git_pipe_real(list(args), cwd, input_text)

    return wrapper


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
        return classify_merged(
            self.repo,
            head,
            remote_ref,
            runner=_git_ok,
            pipe_runner=_git_pipe_real,
            **kwargs,  # type: ignore[arg-type]
        )

    # ---- shared fixture builders --------------------------------------------

    def _multi_commit_squash(self) -> str:
        """feature = C1 (a.txt), C2 (b.txt); main squashes BOTH -> fully
        landed, no residual. Returns feature's tip sha. Used for the failure-
        injection tests too, since its call sequence (diff x3, patch-id x3,
        rev-list x1, log x1, NO cherry) is fully deterministic."""
        _git(["checkout", "-b", "feature"], self.repo)
        _commit(self.repo, "a.txt", "A\n", "feature commit 1")
        _commit(self.repo, "b.txt", "B\n", "feature commit 2")
        feature_tip = _head(self.repo)
        _git(["checkout", "main"], self.repo)
        _git(["merge", "--squash", "feature"], self.repo)
        _git(["commit", "-m", "squash feature (2 commits)"], self.repo)
        return feature_tip

    def _partially_landed(self) -> tuple[str, str]:
        """feature = C1+C2 (squashed onto main), then C3 (never landed).
        Returns (feature_tip, c3_sha). Has a non-empty residual -> reaches
        the `git cherry` corroboration call (unlike `_multi_commit_squash`)."""
        _git(["checkout", "-b", "feature"], self.repo)
        _commit(self.repo, "a.txt", "A\n", "feature commit 1")
        _commit(self.repo, "b.txt", "B\n", "feature commit 2")
        _git(["checkout", "main"], self.repo)
        _git(["merge", "--squash", "feature"], self.repo)
        _git(["commit", "-m", "squash feature (2 commits)"], self.repo)
        _git(["checkout", "feature"], self.repo)
        c3 = _commit(self.repo, "c.txt", "C (unlanded)\n", "feature commit 3 (not merged)")
        feature_tip = _head(self.repo)
        return feature_tip, c3

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
        self.assertEqual(result.unmatched_commits, [])

    def test_squash_merged_multi_commit(self) -> None:
        """No single commit's patch-id matches the squash — must still classify
        merged, via the earliest-matching-prefix test finding its match at the
        LAST commit (full coverage, no residual)."""
        feature_tip = self._multi_commit_squash()

        # Premise check: per-commit git cherry alone would NOT find an
        # equivalent for either original commit (this is exactly the gap the
        # prefix-aggregate test closes; classify_merged itself never calls
        # cherry here, because the prefix match covers every commit).
        cherry = _git_ok(["cherry", "main", feature_tip], self.repo)
        self.assertTrue(
            all(line.startswith("+ ") for line in cherry.stdout.splitlines() if line),
            "premise check: expected git cherry to find no per-commit equivalents",
        )

        result = self._classify(feature_tip)
        self.assertEqual(result.status, "merged")
        self.assertEqual(result.reason, "content-equivalent")
        self.assertIn("patch-id", result.detail)
        self.assertEqual(result.unmatched_commits, [])

    def test_rebase_merged_replayed_commits(self) -> None:
        """Rebase-merge: commits replayed onto main with new hashes, same
        diffs. The first replayed commit incidentally matches a prefix on its
        own (aggregate test finds match_index=0); the second is corroborated
        via the per-commit `git cherry` residual check, not the prefix test."""
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

    def test_prefix_scan_skips_empty_commit_mid_branch(self) -> None:
        """An `--allow-empty` commit BEFORE the commit that actually matches
        must be skipped (its cumulative diff-so-far is empty) rather than
        mistaken for a match or an error — the scan continues to the next
        commit and finds the real match there."""
        _git(["checkout", "-b", "feature"], self.repo)
        _git(["commit", "--allow-empty", "-m", "empty commit (no tree change)"], self.repo)
        _commit(self.repo, "a.txt", "A\n", "feature commit: add a.txt")
        feature_tip = _head(self.repo)

        _git(["checkout", "main"], self.repo)
        _git(["merge", "--squash", "feature"], self.repo)
        _git(["commit", "-m", "squash feature"], self.repo)

        result = self._classify(feature_tip)
        self.assertEqual(result.status, "merged")
        self.assertEqual(result.reason, "content-equivalent")
        self.assertEqual(result.unmatched_commits, [])

    # ---- safety guard: must stay FLAGGED -----------------------------------

    def test_partially_landed_tip_has_one_extra_unlanded_commit(self) -> None:
        """Squashed history landed, but the branch tip has grown one more
        commit since — must still classify unmerged (never auto-removed)."""
        feature_tip, c3 = self._partially_landed()

        result = self._classify(feature_tip)
        self.assertEqual(result.status, "unmerged")
        self.assertEqual(result.reason, "content-matched-with-unlanded-history")
        self.assertFalse(result.merged)
        self.assertEqual(result.unmatched_commits, [c3])

    def test_cancel_out_unlanded_commits_stay_flagged(self) -> None:
        """PR #1213 review, must-fix 1: a landed commit, then an unlanded
        ADD and an unlanded REMOVE of the same file. Their net effect on the
        full-range aggregate diff is zero, so a full-range-only aggregate
        test would falsely match — the earliest-matching-prefix search must
        stop at the landed commit and flag the two residual commits."""
        _git(["checkout", "-b", "feature"], self.repo)
        c1 = _commit(self.repo, "a.txt", "A\n", "feature commit 1 (landed)")

        _git(["checkout", "main"], self.repo)
        _git(["merge", "--squash", "feature"], self.repo)
        _git(["commit", "-m", "squash feature (commit 1 only)"], self.repo)

        _git(["checkout", "feature"], self.repo)
        c2 = _commit(self.repo, "f2.txt", "f2 content\n", "commit 2: add f2 (unlanded)")
        _git(["rm", "f2.txt"], self.repo)
        _git(["commit", "-m", "commit 3: remove f2 (unlanded)"], self.repo)
        c3 = _head(self.repo)
        feature_tip = c3

        # Ground truth: the FULL aggregate diff (merge_base..feature_tip) is
        # empty for f2.txt (added then removed) -- confirms this is a genuine
        # net-zero cancellation, not a fixture mistake.
        full_diff = _git_ok(["diff", f"{c1}..{feature_tip}", "--", "f2.txt"], self.repo)
        self.assertEqual(full_diff.stdout.strip(), "")

        cherry = _git_ok(["cherry", "main", feature_tip], self.repo)
        unmatched_ground_truth = [
            line.split()[1] for line in cherry.stdout.splitlines() if line.startswith("+ ")
        ]
        self.assertEqual(sorted(unmatched_ground_truth), sorted([c2, c3]))

        result = self._classify(feature_tip)
        self.assertEqual(result.status, "unmerged")
        self.assertEqual(result.reason, "content-matched-with-unlanded-history")
        self.assertFalse(result.merged)
        self.assertEqual(sorted(result.unmatched_commits), sorted([c2, c3]))

    def test_whitespace_only_unlanded_commit_stays_flagged(self) -> None:
        """PR #1213 review, must-fix 2: a landed commit, then an unlanded
        whitespace-only reindent. `git patch-id` is whitespace-insensitive at
        the aggregate level (an earlier version of this fix classified this
        `merged`), but the per-commit `git cherry` residual check still sees
        the reindent commit as unmatched, since no equivalent reindent
        commit exists on main."""
        _git(["checkout", "-b", "feature"], self.repo)
        _write(self.repo, "ws.txt", "def f():\n    x = 1\n")
        _git(["add", "ws.txt"], self.repo)
        _git(["commit", "-m", "feature commit: add ws.txt"], self.repo)

        _git(["checkout", "main"], self.repo)
        _git(["merge", "--squash", "feature"], self.repo)
        _git(["commit", "-m", "squash feature"], self.repo)

        _git(["checkout", "feature"], self.repo)
        d = _commit(self.repo, "ws.txt", "def f():\n        x = 1\n", "reindent (unlanded)")
        feature_tip = _head(self.repo)

        # Ground truth: the tree genuinely differs from main (this is not a
        # purely cosmetic non-difference).
        differs = _git_ok(["diff", "--quiet", "main", feature_tip, "--", "ws.txt"], self.repo)
        self.assertNotEqual(differs.returncode, 0)

        result = self._classify(feature_tip)
        self.assertEqual(result.status, "unmerged")
        self.assertEqual(result.reason, "content-matched-with-unlanded-history")
        self.assertFalse(result.merged)
        self.assertEqual(result.unmatched_commits, [d])

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

    def test_trivial_empty_tip_commit_reaches_empty_diff_branch(self) -> None:
        """#1203 pattern: the fixture must actually REACH the branch it is
        named for, not merely happen to satisfy `.merged` via a different
        code path (an earlier version of this test used a branch with zero
        unique commits, which the ANCESTOR fast path already covers, making
        it inert -- flipping the empty-diff branch's return left the suite
        green). This one is a branch AHEAD of main by one `--allow-empty`
        commit, so ancestry genuinely fails (main lacks this commit) and the
        empty-diff branch is what actually classifies it merged."""
        _git(["checkout", "-b", "feature"], self.repo)
        _git(["commit", "--allow-empty", "-m", "empty commit, no tree change"], self.repo)
        feature_tip = _head(self.repo)

        anc = _git_ok(["merge-base", "--is-ancestor", feature_tip, "main"], self.repo)
        self.assertNotEqual(anc.returncode, 0, "premise: ancestry must genuinely fail here")

        result = self._classify(feature_tip)
        self.assertTrue(result.merged)
        self.assertEqual(result.reason, "content-equivalent")
        self.assertIn("introduces no changes", result.detail)

    # ---- degrade-to-unmerged: every internal failure/unexpected-result site ---

    def test_own_diff_failure_degrades(self) -> None:
        feature_tip = self._multi_commit_squash()
        runner = _runner_intercepting("diff", occurrence=1, mode="fail")
        result = classify_merged(
            self.repo, feature_tip, "main", runner=runner, pipe_runner=_git_pipe_real
        )
        self.assertEqual(result.status, "unmerged")
        self.assertEqual(result.reason, "content-check-failed")
        self.assertFalse(result.merged)

    def test_rev_list_failure_degrades(self) -> None:
        feature_tip = self._multi_commit_squash()
        runner = _runner_intercepting("rev-list", occurrence=1, mode="fail")
        result = classify_merged(
            self.repo, feature_tip, "main", runner=runner, pipe_runner=_git_pipe_real
        )
        self.assertEqual(result.status, "unmerged")
        self.assertEqual(result.reason, "content-check-failed")
        self.assertFalse(result.merged)

    def test_rev_list_empty_despite_nonempty_diff_degrades(self) -> None:
        """Defensive branch: a non-empty diff should always list at least one
        commit over the same range. Force the "should never happen" state via
        dependency injection and confirm it fails closed rather than crashing
        or (worse) treating "no commits" as "no changes"."""
        feature_tip = self._multi_commit_squash()
        runner = _runner_intercepting("rev-list", occurrence=1, mode="empty")
        result = classify_merged(
            self.repo, feature_tip, "main", runner=runner, pipe_runner=_git_pipe_real
        )
        self.assertEqual(result.status, "unmerged")
        self.assertEqual(result.reason, "content-check-failed")
        self.assertFalse(result.merged)

    def test_main_log_failure_degrades(self) -> None:
        feature_tip = self._multi_commit_squash()
        runner = _runner_intercepting("log", occurrence=1, mode="fail")
        result = classify_merged(
            self.repo, feature_tip, "main", runner=runner, pipe_runner=_git_pipe_real
        )
        self.assertEqual(result.status, "unmerged")
        self.assertEqual(result.reason, "content-check-failed")
        self.assertFalse(result.merged)

    def test_main_patch_id_failure_degrades(self) -> None:
        feature_tip = self._multi_commit_squash()
        pipe_runner = _pipe_intercepting(occurrence=1, mode="fail")
        result = classify_merged(
            self.repo, feature_tip, "main", runner=_git_ok, pipe_runner=pipe_runner
        )
        self.assertEqual(result.status, "unmerged")
        self.assertEqual(result.reason, "content-check-failed")
        self.assertFalse(result.merged)

    def test_prefix_diff_failure_degrades(self) -> None:
        """Targets the loop's OWN diff call (the 2nd "diff" invocation
        overall — the 1st is the whole-range trivial-check diff)."""
        feature_tip = self._multi_commit_squash()
        runner = _runner_intercepting("diff", occurrence=2, mode="fail")
        result = classify_merged(
            self.repo, feature_tip, "main", runner=runner, pipe_runner=_git_pipe_real
        )
        self.assertEqual(result.status, "unmerged")
        self.assertEqual(result.reason, "content-check-failed")
        self.assertFalse(result.merged)

    def test_prefix_patch_id_failure_degrades(self) -> None:
        """Targets the loop's patch-id call (the 2nd pipe invocation overall
        — the 1st is the main-range table build)."""
        feature_tip = self._multi_commit_squash()
        pipe_runner = _pipe_intercepting(occurrence=2, mode="fail")
        result = classify_merged(
            self.repo, feature_tip, "main", runner=_git_ok, pipe_runner=pipe_runner
        )
        self.assertEqual(result.status, "unmerged")
        self.assertEqual(result.reason, "content-check-failed")
        self.assertFalse(result.merged)

    def test_prefix_patch_id_empty_output_degrades(self) -> None:
        """Must-fix 6 (PR #1213 review): a non-empty diff whose `git
        patch-id` call succeeds but produces no output is an UNKNOWN state,
        not evidence of "no changes" -- must degrade to unmerged, not fail
        open to merged."""
        feature_tip = self._multi_commit_squash()
        pipe_runner = _pipe_intercepting(occurrence=2, mode="empty")
        result = classify_merged(
            self.repo, feature_tip, "main", runner=_git_ok, pipe_runner=pipe_runner
        )
        self.assertEqual(result.status, "unmerged")
        self.assertEqual(result.reason, "content-check-failed")
        self.assertFalse(result.merged)
        self.assertIn("produced no output", result.detail)

    def test_cherry_failure_degrades(self) -> None:
        """Cherry is only invoked when there is a non-empty residual, so this
        needs the partially-landed fixture rather than the fully-covered
        multi-commit-squash one (which never reaches the cherry call)."""
        feature_tip, _c3 = self._partially_landed()
        runner = _runner_intercepting("cherry", occurrence=1, mode="fail")
        result = classify_merged(
            self.repo, feature_tip, "main", runner=runner, pipe_runner=_git_pipe_real
        )
        self.assertEqual(result.status, "unmerged")
        self.assertEqual(result.reason, "content-check-failed")
        self.assertFalse(result.merged)

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
