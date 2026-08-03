"""Tests for check_worktree_merged — net-content, order-independent merged
classification (main#1212, sibling of #1177; owner decision 2026-08-02 on
PR #1213 round 3 superseding acceptance criterion 2 as originally filed;
round 4 closes the evil-merge gap round 3 left open).

Every test drives REAL git against a throwaway temp repo so the plumbing is
exercised end-to-end (ancestry probe, merge-base, `git diff`/`git log -p`
piped through `git patch-id --stable`, and `git cherry`). Coverage:

  * merge-commit merged                     -> merged / ancestor (fast path)
  * squash merged, single commit            -> merged / content-equivalent
    (test 1: net-content match)
  * squash merged, multi-commit             -> merged / content-equivalent
    (test 1: no single original commit's patch-id would match the squash
    commit, but the FULL aggregate does)
  * rebase-merge (replayed commits, new hashes, same content)  -> merged /
    content-equivalent (test 2: git cherry per-commit corroboration — test 1
    can't match here, since main has TWO separate commits, neither of which
    alone equals the combined diff)
  * cherry-pick (new commit, same diff)                        -> merged /
    content-equivalent (test 1)
  * order independence (owner decision, round 3): the SAME commit set (a
    landed content commit + an add-then-remove pair that cancels to zero net
    content) in two different orderings MUST classify identically — both
    `merged`, since the net content is fully landed in both, regardless of
    which order the two "unlanded" commits keep git cherry from matching
    individually. This is the property a per-commit ("earliest matching
    prefix") design could not provide.
  * whitespace residual is DISCLOSED, not prevented: a landed commit,
    then an unlanded reindent-only commit, classifies `merged` (patch-id is
    whitespace-insensitive at the net-content level) — this is the accepted,
    documented residual, not a bug.
  * git-cherry-invisible/misleading commits (round 3, finding 2): a routine
    internal merge commit (merging `main` into the feature branch to resolve
    conflicts) must NOT be reported as unlanded just because `git cherry`
    never lists it at all (verified: neither `+` nor `-`); a trailing
    `--allow-empty` commit must ALSO not be reported as unlanded even though
    `git cherry` DOES mark it `+` (verified — it is not silently omitted the
    way a merge commit is), because it is explicitly filtered by checking
    its own diff against its immediate parent is empty.
  * evil-merge discriminator pair (round 4): a CLEAN internal merge (no
    unique resolution content) stays `merged` -> `git diff-tree --cc
    --no-commit-id <merge-sha>` is genuinely empty; an EVIL merge (resolution
    adds content present in neither parent, the population `git cherry`
    structurally cannot examine) classifies `unmerged` -> the same command
    is non-empty. Mutation-paired: dropping `--cc` breaks the evil case
    (bare `git diff-tree` shows nothing for a merge without it); dropping
    `--no-commit-id` breaks the clean case (bare `--cc` always prints the
    commit-id line first, so every merge — even a content-free one — would
    show up as "non-empty").
  * partially-landed: squashed history PLUS one extra unlanded commit on the
    tip -> unmerged / unlanded-changes (must stay FLAGGED; per-commit
    precision in `unmatched_commits` is not guaranteed under net-content
    semantics — see the test's docstring)
  * never-merged (no relation to remote_ref content at all)     -> unmerged /
    unlanded-changes
  * orphan branch (no common ancestor at all)                   -> unmerged /
    no-common-ancestor
  * ancestry probe itself errors (bad rev)                      -> error /
    ancestor-check-failed, never "merged"
  * trivial no-op tip (`--allow-empty` commit off main's tip, reaching the
    empty-diff branch for real rather than via the ancestor fast path)
    -> merged / content-equivalent
  * every internal git-command failure/unexpected-result site degrades to
    unmerged, never merged: own diff, own diff patch-id, own diff patch-id
    producing no output for a non-empty diff (fail-open guard), the
    streamed main-range log|patch-id pipeline (either stage), git cherry,
    the per-"+"-candidate empty-commit diff check, the merges rev-list
    enumeration, and the evil-merge diff-tree --cc check
  * streaming (#1214): `_git_log_patch_id` connects `git log -p`'s stdout
    directly to `git patch-id`'s stdin over an OS pipe instead of buffering
    the full patch text into a Python string first — pinned structurally
    (no `subprocess.run`/`input=` call site, `stdin` is a pipe object) and
    for output-equivalence against the old buffer-then-pipe two-step, with
    a dedicated failure case for the `git log` stage itself
  * CLI exit code mirrors `.merged` (0 iff merged, 1 otherwise)
"""

from __future__ import annotations

import subprocess
import sys
import unittest
import unittest.mock
from collections.abc import Sequence
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

# Helper lives at .claude/lib/check_worktree_merged.py; this test is at
# .claude/lib/tests/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from check_worktree_merged import (  # noqa: E402
    GitRunner,
    LogPatchIdRunner,
    PipeRunner,
    _git_log_patch_id,
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

    Precisely targeting one call site (rather than failing every call) is
    what lets each of classify_merged's several degrade-to-unmerged sites be
    pinned independently — a fake that fails everything can only ever prove
    the FIRST site is safe (PR #1213 review round 2, must-fix 2)."""
    seen = {"n": 0}

    def wrapper(args: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        if args and args[0] == subcommand:
            seen["n"] += 1
            if seen["n"] == occurrence:
                return _fail(args) if mode == "fail" else _empty_ok(args)
        return _git_ok(list(args), cwd)

    return wrapper


def _log_patch_id_failing(
    returncode: int = 128, stderr: str = "simulated failure"
) -> LogPatchIdRunner:
    """A LogPatchIdRunner fake that fails unconditionally — stands in for
    EITHER of the two stages `_git_log_patch_id` pipes together (`git log`
    or `git patch-id`) failing, since #1214 merged both into one seam that
    classify_merged only ever sees a single combined pass/fail result from."""

    def wrapper(log_args: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=["git", *log_args, "|", "git", "patch-id", "--stable"],
            returncode=returncode,
            stdout="",
            stderr=stderr,
        )

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


def _cherry_unmatched(repo: Path, base: str, tip: str) -> list[str]:
    """Ground-truth helper: the commits `git cherry` itself marks `+`."""
    res = _git_ok(["cherry", base, tip], repo)
    return [line.split()[1] for line in res.stdout.splitlines() if line.startswith("+ ")]


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
        landed via test 1 (net-content match). Used for the failure-
        injection tests too, since its call sequence is fully deterministic
        and test 1 matches without ever reaching `git cherry`."""
        _git(["checkout", "-b", "feature"], self.repo)
        _commit(self.repo, "a.txt", "A\n", "feature commit 1")
        _commit(self.repo, "b.txt", "B\n", "feature commit 2")
        feature_tip = _head(self.repo)
        _git(["checkout", "main"], self.repo)
        _git(["merge", "--squash", "feature"], self.repo)
        _git(["commit", "-m", "squash feature (2 commits)"], self.repo)
        return feature_tip

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

    # ---- test 1: net-content match ------------------------------------------

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
        """No single commit's patch-id matches the squash — must still
        classify merged, via test 1's FULL aggregate diff."""
        feature_tip = self._multi_commit_squash()

        # Premise check: per-commit git cherry alone would NOT find an
        # equivalent for either original commit — this is exactly the gap
        # test 1 (the aggregate net-content match) closes.
        unmatched = _cherry_unmatched(self.repo, "main", feature_tip)
        self.assertEqual(len(unmatched), 2)

        result = self._classify(feature_tip)
        self.assertEqual(result.status, "merged")
        self.assertEqual(result.reason, "content-equivalent")
        self.assertIn("patch-id", result.detail)
        self.assertEqual(result.unmatched_commits, [])

    def test_rebase_merged_replayed_commits(self) -> None:
        """Rebase-merge: commits replayed onto main with new hashes, same
        diffs, as TWO SEPARATE commits — test 1 cannot match here (no single
        main commit equals the combined diff), so this exercises test 2
        (`git cherry` per-commit corroboration)."""
        _git(["checkout", "-b", "feature"], self.repo)
        c1 = _commit(self.repo, "a.txt", "A\n", "feature commit 1")
        c2 = _commit(self.repo, "b.txt", "B\n", "feature commit 2")
        feature_tip = _head(self.repo)

        _git(["checkout", "main"], self.repo)
        _commit(self.repo, "unrelated.txt", "other work landed on main\n", "unrelated main commit")
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

        _git(["checkout", "main"], self.repo)
        _commit(self.repo, "unrelated.txt", "other work landed on main\n", "unrelated main commit")
        _git(["cherry-pick", c1], self.repo)

        result = self._classify(feature_tip)
        self.assertEqual(result.status, "merged")
        self.assertEqual(result.reason, "content-equivalent")

    # ---- order independence (owner decision, round 3) -----------------------

    def test_cancel_out_order_independence(self) -> None:
        """The SAME commit set — a real content commit (A) plus a
        cancelling pair (B: add f2, C: remove f2) — in two different
        orderings MUST classify identically. Both orderings' final tree is
        byte-identical (A's content only; B/C touch a disjoint file and net
        to nothing), so both are `merged`. A per-commit ("earliest matching
        prefix") design gave DIFFERENT verdicts for the two orderings —
        this is the bug the net-content redesign exists to fix."""
        merge_base = _head(self.repo)

        # Ordering 1: A, B, C.
        _git(["checkout", "-b", "feature-abc", merge_base], self.repo)
        a_commit_abc = _commit(self.repo, "a.txt", "real content\n", "A: real content")
        _commit(self.repo, "f2.txt", "f2 content\n", "B: add f2 (unlanded)")
        _git(["rm", "f2.txt"], self.repo)
        _git(["commit", "-m", "C: remove f2 (unlanded)"], self.repo)
        abc_tip = _head(self.repo)

        # Land ONLY commit A onto main via squash — main has exactly A's
        # content, nothing from the cancelling pair.
        _git(["checkout", "main"], self.repo)
        _git(["merge", "--squash", a_commit_abc], self.repo)
        _git(["commit", "-m", "squash: land A only"], self.repo)

        # Ordering 2: B, C, A — same merge-base, same final tree (the two
        # groups of changes touch disjoint files, so order doesn't affect
        # the result), but entirely different actual commit objects.
        _git(["checkout", "-b", "feature-bca", merge_base], self.repo)
        _commit(self.repo, "f2.txt", "f2 content\n", "B: add f2 (unlanded)")
        _git(["rm", "f2.txt"], self.repo)
        _git(["commit", "-m", "C: remove f2 (unlanded)"], self.repo)
        _commit(self.repo, "a.txt", "real content\n", "A: real content")
        bca_tip = _head(self.repo)

        # Ground truth: identical final tree in both orderings.
        tree_abc = _git(["rev-parse", f"{abc_tip}^{{tree}}"], self.repo).stdout
        tree_bca = _git(["rev-parse", f"{bca_tip}^{{tree}}"], self.repo).stdout
        self.assertEqual(tree_abc, tree_bca)

        # Ground truth: git cherry reports 2 unlanded commits in BOTH
        # orderings (just different specific commits) — a naive per-commit
        # rule would flag both; net-content correctly merges both.
        self.assertEqual(len(_cherry_unmatched(self.repo, "main", abc_tip)), 2)
        self.assertEqual(len(_cherry_unmatched(self.repo, "main", bca_tip)), 2)

        result_abc = self._classify(abc_tip)
        result_bca = self._classify(bca_tip)

        self.assertEqual(result_abc.status, "merged")
        self.assertEqual(result_bca.status, "merged")
        self.assertEqual(result_abc.status, result_bca.status)
        self.assertEqual(result_abc.reason, result_bca.reason)

    # ---- disclosed residual: whitespace ------------------------------------

    def test_whitespace_residual_is_disclosed_not_prevented(self) -> None:
        """A landed commit, then an unlanded reindent-only commit, classifies
        `merged` — this is the DISCLOSED `git patch-id` whitespace-
        normalization residual (owner decision, round 3), not a bug. It is
        pinned here so the residual stays a documented, deliberate choice
        rather than an accidental regression nobody notices."""
        _git(["checkout", "-b", "feature"], self.repo)
        _write(self.repo, "ws.txt", "def f():\n    x = 1\n")
        _git(["add", "ws.txt"], self.repo)
        _git(["commit", "-m", "feature commit: add ws.txt"], self.repo)

        _git(["checkout", "main"], self.repo)
        _git(["merge", "--squash", "feature"], self.repo)
        _git(["commit", "-m", "squash feature"], self.repo)

        _git(["checkout", "feature"], self.repo)
        _commit(self.repo, "ws.txt", "def f():\n        x = 1\n", "reindent (unlanded)")
        feature_tip = _head(self.repo)

        # Ground truth: the tree genuinely differs from main (not a purely
        # cosmetic non-difference) -- yet patch-id equivalence still merges
        # it, because patch-id itself is whitespace-insensitive.
        differs = _git_ok(["diff", "--quiet", "main", feature_tip, "--", "ws.txt"], self.repo)
        self.assertNotEqual(differs.returncode, 0)

        result = self._classify(feature_tip)
        self.assertEqual(result.status, "merged")

    # ---- git-cherry-invisible commits (round 3, finding 2; round 4 evil-merge) -

    def test_internal_merge_commit_not_treated_as_unlanded(self) -> None:
        """`git cherry` never lists merge commits — routine on a feature
        branch that merges `main` in to resolve conflicts. An earlier
        version of this module treated "not explicitly matched by cherry"
        as "unmatched", which reported the merge commit as having no
        equivalent — a statement `git cherry`'s own output contradicts.

        This is the CLEAN half of the round-4 evil-merge discriminator pair
        (see test_evil_merge_flags_unmerged for the other half): a routine,
        content-free merge must stay `merged`. `git diff-tree --cc
        --no-commit-id <merge-sha>` on a clean merge is genuinely EMPTY —
        bare `--cc` (no `--no-commit-id`) would print the commit-id line
        even for a clean merge, which is why dropping `--no-commit-id` is
        exactly the mutation that must fail THIS test (see the module for
        why: it would false-flag every routine internal merge, reopening
        the over-strict round-2 bug)."""
        _git(["checkout", "-b", "feature"], self.repo)
        c1 = _commit(self.repo, "a.txt", "A\n", "feature commit 1")

        _git(["checkout", "main"], self.repo)
        _commit(self.repo, "unrelated.txt", "unrelated main work\n", "unrelated main commit")

        _git(["checkout", "feature"], self.repo)
        _git(["merge", "main", "-m", "merge main into feature to resolve conflicts"], self.repo)
        merge_commit = _head(self.repo)
        c2 = _commit(self.repo, "b.txt", "B\n", "feature commit 2 (after the merge)")
        feature_tip = _head(self.repo)

        # Land c1 and c2 individually onto main (rebase-merge / separate
        # cherry-picks) — the merge commit itself never lands and never
        # needs to; it carries no unique content of its own.
        _git(["checkout", "main"], self.repo)
        _git(["cherry-pick", c1], self.repo)
        _git(["cherry-pick", c2], self.repo)

        # Ground truth: git cherry shows 0 unlanded commits — the merge
        # commit is simply absent from its output, neither "+" nor "-".
        self.assertEqual(_cherry_unmatched(self.repo, "main", feature_tip), [])

        # Ground truth: the discriminator is genuinely empty for this clean
        # merge with --no-commit-id, but NOT with bare --cc (which always
        # prints the commit-id line first).
        cc_no_id = _git_ok(["diff-tree", "--cc", "--no-commit-id", merge_commit], self.repo)
        self.assertEqual(cc_no_id.stdout.strip(), "")
        cc_with_id = _git_ok(["diff-tree", "--cc", merge_commit], self.repo)
        self.assertEqual(cc_with_id.stdout.strip(), merge_commit)

        result = self._classify(feature_tip)
        self.assertEqual(result.status, "merged")
        self.assertEqual(result.unmatched_commits, [])

    def test_evil_merge_flags_unmerged(self) -> None:
        """The EVIL half of the round-4 discriminator pair: a merge commit
        whose conflict resolution adds content present in NEITHER parent
        (an ordinary, if unusual, thing to do while resolving a merge) must
        be classified `unmerged` -- `git cherry` never examines merge
        commits at all, and test 1 (net-content match) cannot cover this
        path either, since test 2 is only reached once test 1 has already
        failed to match anything.

        Mirrors GitHub's rebase-merge behavior: it flattens a branch and
        replays only the non-merge commits, dropping the merge (and
        therefore its resolution content) entirely -- exactly what landing
        c1/c2 individually via separate cherry-picks below simulates."""
        _git(["checkout", "-b", "feature"], self.repo)
        c1 = _commit(self.repo, "x.txt", "x content\n", "X: add x.txt")

        _git(["checkout", "main"], self.repo)
        _commit(self.repo, "m.txt", "m content\n", "unrelated main work")

        _git(["checkout", "feature"], self.repo)
        _git(["merge", "--no-commit", "main"], self.repo)
        _write(self.repo, "evil.txt", "evil resolution content\n")
        _git(["add", "evil.txt"], self.repo)
        _git(["commit", "-m", "merge main into feature (resolution adds evil.txt)"], self.repo)
        merge_commit = _head(self.repo)
        c2 = _commit(self.repo, "y.txt", "y content\n", "Y: add y.txt")
        feature_tip = _head(self.repo)

        # Land ONLY the non-merge commits individually onto main -- the
        # merge (and evil.txt with it) never lands, matching a real
        # rebase-merge's flatten-and-replay behavior.
        _git(["checkout", "main"], self.repo)
        _git(["cherry-pick", c1], self.repo)
        _git(["cherry-pick", c2], self.repo)

        # Ground truth: git cherry shows 0 unlanded commits (X and Y both
        # matched; the merge commit is simply absent from its output) --
        # this is exactly why cherry alone cannot catch it.
        self.assertEqual(_cherry_unmatched(self.repo, "main", feature_tip), [])
        # Ground truth: evil.txt is genuinely absent from main.
        missing = _git_ok(["show", "main:evil.txt"], self.repo)
        self.assertNotEqual(missing.returncode, 0)
        # Ground truth: the discriminator is non-empty for this merge.
        cc_no_id = _git_ok(["diff-tree", "--cc", "--no-commit-id", merge_commit], self.repo)
        self.assertNotEqual(cc_no_id.stdout.strip(), "")
        self.assertIn("evil.txt", cc_no_id.stdout)

        result = self._classify(feature_tip)
        self.assertEqual(result.status, "unmerged")
        self.assertEqual(result.reason, "unlanded-changes")
        self.assertFalse(result.merged)
        self.assertIn(merge_commit, result.unmatched_commits)

    def test_empty_commit_not_treated_as_unlanded(self) -> None:
        """Unlike a merge commit, `git cherry` does NOT silently omit a
        truly empty (`--allow-empty`) commit from its output -- verified
        directly, it marks one `+` (unmatched) even though it introduces no
        content at all. `classify_merged` must filter this out itself
        (checking whether the "+"-marked commit's own diff against its
        immediate parent is empty), rather than trusting git cherry's raw
        polarity for this population the way it safely can for merge
        commits.

        Uses TWO real commits landed individually (like
        test_rebase_merged_replayed_commits), not one -- with only one real
        commit, test 1 (net-content match, which ignores the empty commit
        entirely since it contributes nothing to the aggregate diff) already
        classifies `merged` on its own, making the fixture inert with
        respect to test 2's empty-commit filter specifically (the #1203
        pattern: a fixture that happens to satisfy the assertion via a
        different code path than the one it's named for) -- confirmed by
        mutation: with only one commit, deleting the empty-commit filter
        entirely left this test green."""
        _git(["checkout", "-b", "feature"], self.repo)
        c1 = _commit(self.repo, "a.txt", "A\n", "feature commit 1")
        c2 = _commit(self.repo, "b.txt", "B\n", "feature commit 2")
        _git(["commit", "--allow-empty", "-m", "empty commit (no tree change)"], self.repo)
        feature_tip = _head(self.repo)

        _git(["checkout", "main"], self.repo)
        _commit(self.repo, "unrelated.txt", "unrelated main work\n", "unrelated main commit")
        _git(["cherry-pick", c1], self.repo)
        _git(["cherry-pick", c2], self.repo)

        # Premise: test 1 cannot match here (main has c1 and c2 as two
        # SEPARATE commits, neither of which alone equals the 3-commit
        # combined diff) -- so this genuinely reaches test 2.
        own_diff = _git_ok(["diff", f"{c1}^..{feature_tip}"], self.repo)
        self.assertTrue(own_diff.stdout.strip())  # sanity: non-trivial diff

        # Ground truth: git cherry's RAW output marks the empty commit "+"
        # (unmatched) -- it does not omit it the way it omits a merge commit
        # -- while c1 and c2 are correctly marked "-" (matched).
        raw_unmatched = _cherry_unmatched(self.repo, "main", feature_tip)
        self.assertEqual(raw_unmatched, [feature_tip])
        # And its own diff against its immediate parent is genuinely empty.
        empty_own_diff = _git_ok(["diff", f"{feature_tip}^..{feature_tip}"], self.repo)
        self.assertEqual(empty_own_diff.stdout.strip(), "")

        result = self._classify(feature_tip)
        self.assertEqual(result.status, "merged")
        self.assertEqual(result.unmatched_commits, [])

    # ---- safety guard: must stay FLAGGED -----------------------------------

    def test_partially_landed_tip_has_one_extra_unlanded_commit(self) -> None:
        """Squashed history landed, but the branch tip has grown one more
        commit since — must still classify unmerged (never auto-removed).
        Under net-content semantics, `unmatched_commits` may include the
        legitimately-squashed commits too (git cherry can't distinguish "was
        part of a squash" from "never landed" per-commit) — this test pins
        the overall verdict, not per-commit precision, per the owner's
        round-3 decision that per-commit precision is not a guarantee this
        design provides."""
        _git(["checkout", "-b", "feature"], self.repo)
        _commit(self.repo, "a.txt", "A\n", "feature commit 1")
        _commit(self.repo, "b.txt", "B\n", "feature commit 2")

        _git(["checkout", "main"], self.repo)
        _git(["merge", "--squash", "feature"], self.repo)
        _git(["commit", "-m", "squash feature (2 commits)"], self.repo)

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

    def test_trivial_empty_tip_commit_reaches_empty_diff_branch(self) -> None:
        """#1203 pattern: the fixture must actually REACH the branch it is
        named for. A branch AHEAD of main by one `--allow-empty` commit
        genuinely fails ancestry, so the empty-diff branch is what actually
        classifies it merged (not the ancestor fast path)."""
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

    def test_own_patch_id_failure_degrades(self) -> None:
        feature_tip = self._multi_commit_squash()
        pipe_runner = _pipe_intercepting(occurrence=1, mode="fail")
        result = classify_merged(
            self.repo, feature_tip, "main", runner=_git_ok, pipe_runner=pipe_runner
        )
        self.assertEqual(result.status, "unmerged")
        self.assertEqual(result.reason, "content-check-failed")
        self.assertFalse(result.merged)

    def test_own_patch_id_empty_output_degrades(self) -> None:
        """Fail-open guard: a non-empty diff whose `git patch-id` call
        succeeds but produces no output is an UNKNOWN state, not evidence of
        "no changes" -- must degrade to unmerged, not fail open to merged."""
        feature_tip = self._multi_commit_squash()
        pipe_runner = _pipe_intercepting(occurrence=1, mode="empty")
        result = classify_merged(
            self.repo, feature_tip, "main", runner=_git_ok, pipe_runner=pipe_runner
        )
        self.assertEqual(result.status, "unmerged")
        self.assertEqual(result.reason, "content-check-failed")
        self.assertFalse(result.merged)
        self.assertIn("produced no output", result.detail)

    def test_main_log_patch_id_failure_degrades(self) -> None:
        """Covers BOTH failure surfaces `_git_log_patch_id` pipes together
        (`git log` itself failing, or `git patch-id` itself failing) — #1214
        merged the two into one streamed seam, so classify_merged only ever
        sees a single combined pass/fail result from `log_patch_id_runner`
        regardless of which internal stage actually failed."""
        feature_tip = self._multi_commit_squash()
        result = classify_merged(
            self.repo,
            feature_tip,
            "main",
            runner=_git_ok,
            pipe_runner=_git_pipe_real,
            log_patch_id_runner=_log_patch_id_failing(),
        )
        self.assertEqual(result.status, "unmerged")
        self.assertEqual(result.reason, "content-check-failed")
        self.assertFalse(result.merged)

    # ---- streaming (#1214): no full patch-text buffering ---------------------

    def test_git_log_patch_id_streams_without_buffering_full_text(self) -> None:
        """The actual point of #1214: `git log`'s stdout must be connected
        directly to `git patch-id`'s stdin via an OS pipe, never fully
        materialized as a Python string first. Proven structurally: every
        OTHER helper in this module (`_git`, `_git_pipe`) goes through
        `subprocess.run` (`capture_output=True` / `input=<str>`, which
        necessarily buffers); `_git_log_patch_id` must never call
        `subprocess.run` at all, only `Popen`.

        Strengthened per #1251 finding 2: the ORIGINAL version of this test
        (checking only `stdin is not None` and `not isinstance(stdin, str)`)
        passed for a mutant that fully buffers `log_proc`'s output via
        `log_proc.communicate()` and then feeds the buffered string to
        `patch_id_proc.communicate(input=...)` with `stdin=subprocess.PIPE`
        — `subprocess.PIPE` is an `int`, not a `str`, so the old assertions
        were blind to it. The second `Popen`'s `stdin` must therefore be
        checked to be neither `None` NOR the `subprocess.PIPE` sentinel, AND
        must expose `fileno()` (a real OS-level pipe/file object, not the
        "please give me a pipe" request constant) — verified to be exactly
        the first `Popen`'s own `stdout` pipe object by identity, and that
        object must end up closed (the fd-release idiom, #1251 finding 3)."""
        self._multi_commit_squash()

        popen_calls: list[dict[str, object]] = []
        created_procs: list[subprocess.Popen[str]] = []
        real_popen = subprocess.Popen

        def recording_popen(*args: Any, **kwargs: Any) -> subprocess.Popen[str]:
            popen_calls.append(kwargs)
            proc = real_popen(*args, **kwargs)
            created_procs.append(proc)
            return proc

        with (
            unittest.mock.patch("subprocess.run") as mock_run,
            unittest.mock.patch("subprocess.Popen", recording_popen),
        ):
            result = _git_log_patch_id(["log", "-p", "--first-parent", "main"], self.repo)

        mock_run.assert_not_called()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(len(popen_calls), 2)
        self.assertEqual(len(created_procs), 2)
        log_kwargs, patch_kwargs = popen_calls
        log_proc, _patch_id_proc = created_procs
        self.assertEqual(log_kwargs["stdout"], subprocess.PIPE)
        self.assertNotIn("input", patch_kwargs)
        self.assertIsNotNone(patch_kwargs.get("stdin"))
        self.assertNotIsInstance(patch_kwargs["stdin"], str)
        # #1251 finding 2: PIPE is an int sentinel meaning "give me a new
        # pipe" -- a mutant that fully buffers and re-feeds via
        # `communicate(input=...)` would set stdin=subprocess.PIPE here, not
        # an actual stream object. Must be a real pipe/file-like object AND
        # the exact one log_proc itself produced (identity, not just shape).
        self.assertNotEqual(patch_kwargs["stdin"], subprocess.PIPE)
        self.assertTrue(hasattr(patch_kwargs["stdin"], "fileno"))
        self.assertIs(patch_kwargs["stdin"], log_proc.stdout)
        # #1251 finding 3: our copy of the read end must be released (closed)
        # so `git log` gets a normal EOF/SIGPIPE once patch-id is done.
        assert log_proc.stdout is not None
        self.assertTrue(log_proc.stdout.closed)

    def test_git_log_patch_id_output_matches_manual_buffer_then_pipe(self) -> None:
        """Correctness pin (#1214): the streamed helper's output must be
        byte-identical to the old buffer-then-pipe two-step it replaces —
        proving the memory-profile change did not alter WHAT is computed,
        only how much text is held resident in this process at once."""
        self._multi_commit_squash()
        merge_base = _git(["merge-base", "feature", "main"], self.repo).stdout.strip()
        log_args = ["log", "-p", "--first-parent", f"{merge_base}..main"]

        streamed = _git_log_patch_id(log_args, self.repo)
        manual_log = _git_ok(log_args, self.repo)
        manual = _git_pipe_real(["patch-id", "--stable"], self.repo, manual_log.stdout)

        self.assertEqual(streamed.returncode, 0)
        self.assertEqual(manual.returncode, 0)
        self.assertEqual(streamed.stdout, manual.stdout)

    def test_git_log_patch_id_log_stage_failure_returns_nonzero(self) -> None:
        """When the `git log` stage itself fails (bad range), the combined
        helper must report failure, not silently succeed with empty patch-id
        output — which `classify_merged` would otherwise misread as "no
        commits on the range" rather than "the command failed"."""
        result = _git_log_patch_id(
            ["log", "-p", "--first-parent", "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef..main"],
            self.repo,
        )
        self.assertNotEqual(result.returncode, 0)

    def test_git_log_patch_id_patch_id_stage_failure_returns_nonzero(self) -> None:
        """#1251 finding 1: the `git patch-id`-stage failure branch
        (`if patch_id_proc.returncode != 0: ...`) was the only uncovered
        line in the helper — the consolidated `test_main_log_patch_id_
        failure_degrades` injects a fake at the whole `log_patch_id_runner`
        seam (covers `classify_merged`'s degrade path, not this helper's own
        two internal branches), and the log-stage-failure test above only
        exercises the OTHER branch. Real `git patch-id --stable` essentially
        never fails on well-formed stdin, so this exercises the branch by
        substituting a failing command for the second `Popen` call only,
        while the first (`git log`) call runs for real and unmodified.

        Must DRAIN stdin before exiting, not just exit immediately: a
        command that exits without reading stdin (the original `["false"]`
        here) makes `git log` take SIGPIPE while still writing, which sends
        `log_proc.returncode` negative — and `_git_log_patch_id` checks
        `log_proc.returncode != 0` FIRST, so the test would silently pass
        through the OTHER (log-stage) branch instead of the one it names
        and claims to isolate (caught in merge-gate review of PR #1247:
        `log_proc.returncode` went to -13, line 290 — the target branch —
        was never reached, yet the assertions still passed on the wrong
        branch). `sh -c "cat >/dev/null; exit 1"` reads stdin to EOF (so
        `git log` finishes writing and exits 0 normally) before failing."""
        self._multi_commit_squash()
        real_popen = subprocess.Popen

        def failing_patch_id_popen(*args: Any, **kwargs: Any) -> subprocess.Popen[str]:
            argv = args[0] if args else kwargs.pop("args", None)
            if isinstance(argv, list) and "patch-id" in argv:
                argv = ["sh", "-c", "cat >/dev/null; exit 1"]
            return real_popen(argv, **kwargs)

        with unittest.mock.patch("subprocess.Popen", failing_patch_id_popen):
            result = _git_log_patch_id(["log", "-p", "--first-parent", "main"], self.repo)

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    # ---- streaming (#1249): log-stage stderr must never deadlock the pipe ----

    def test_git_log_patch_id_log_stderr_routed_off_bounded_pipe(self) -> None:
        """#1249, fast structural pin: `_git_log_patch_id`'s FIRST `Popen`
        call (`git log`) must not set `stderr=subprocess.PIPE` — a bounded OS
        pipe that nobody drains until AFTER `patch_id_proc.communicate()`
        returns, which cannot happen until `git log` itself finishes (see
        the real-process reproduction below and the module docstring). A
        real file object (has `fileno()`, unbounded by pipe-buffer size) is
        required instead."""
        self._multi_commit_squash()
        popen_calls: list[dict[str, object]] = []
        real_popen = subprocess.Popen

        def recording_popen(*args: Any, **kwargs: Any) -> subprocess.Popen[str]:
            popen_calls.append(kwargs)
            return real_popen(*args, **kwargs)

        with unittest.mock.patch("subprocess.Popen", recording_popen):
            _git_log_patch_id(["log", "-p", "--first-parent", "main"], self.repo)

        log_kwargs, _patch_kwargs = popen_calls
        self.assertNotEqual(log_kwargs["stderr"], subprocess.PIPE)
        self.assertTrue(hasattr(log_kwargs["stderr"], "fileno"))

    def test_git_log_patch_id_large_log_stderr_does_not_deadlock(self) -> None:
        """#1249, real-process reproduction: a `git log -p` whose diff driver
        (`.gitattributes` `textconv`) writes well over one OS pipe-buffer's
        worth (~64KiB on Linux) of STDERR across the range must not hang the
        pipeline. Run in a genuinely separate process with a hard wall-clock
        timeout so an actual regression fails this test FAST (seconds)
        rather than hanging the whole suite indefinitely."""
        noisy = self.repo / "noisy_textconv.sh"
        noisy.write_text('#!/usr/bin/env bash\nyes x | head -c 20000 >&2\ncat "$1"\n')
        noisy.chmod(0o755)
        _git(["config", "diff.noisy.textconv", str(noisy)], self.repo)
        _write(self.repo, ".gitattributes", "noisy.dat diff=noisy\n")
        _git(["add", ".gitattributes"], self.repo)
        _git(["commit", "-m", "add noisy.dat textconv driver"], self.repo)
        for i in range(4):
            _commit(self.repo, "noisy.dat", f"payload {i}\n" * 50, f"noisy commit {i}")

        script = (
            "import sys\n"
            f"sys.path.insert(0, {str(Path(__file__).resolve().parent.parent)!r})\n"
            "from pathlib import Path\n"
            "from check_worktree_merged import _git_log_patch_id\n"
            "result = _git_log_patch_id(\n"
            "    ['log', '-p', '--first-parent', 'main'],\n"
            f"    Path({str(self.repo)!r}),\n"
            ")\n"
            "print(result.returncode)\n"
        )
        try:
            proc = subprocess.run(
                [sys.executable, "-c", script],
                capture_output=True,
                text=True,
                timeout=20,
            )
        except subprocess.TimeoutExpired:
            self.fail(
                "_git_log_patch_id deadlocked on a large git-log stderr stream "
                "(#1249 regression) -- did not return within 20s"
            )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "0")

    def test_cherry_failure_degrades(self) -> None:
        """Cherry is only reached when test 1 (net-content) does not match —
        the never-merged fixture guarantees that."""
        _git(["checkout", "-b", "feature"], self.repo)
        _commit(self.repo, "a.txt", "A\n", "never merged")
        feature_tip = _head(self.repo)

        runner = _runner_intercepting("cherry", occurrence=1, mode="fail")
        result = classify_merged(
            self.repo, feature_tip, "main", runner=runner, pipe_runner=_git_pipe_real
        )
        self.assertEqual(result.status, "unmerged")
        self.assertEqual(result.reason, "content-check-failed")
        self.assertFalse(result.merged)

    def test_cherry_candidate_empty_check_failure_degrades(self) -> None:
        """The per-"+"-candidate empty-commit filter (finding 2's fix) does
        its own `git diff <c>^..<c>` call — that call failing must degrade
        too, not silently treat the candidate as genuinely unmatched or as
        harmlessly empty."""
        _git(["checkout", "-b", "feature"], self.repo)
        _commit(self.repo, "a.txt", "A\n", "never merged")
        feature_tip = _head(self.repo)

        # 1st "diff" call is the own (full-range) diff; the 2nd is the
        # per-candidate empty-commit check this test targets.
        runner = _runner_intercepting("diff", occurrence=2, mode="fail")
        result = classify_merged(
            self.repo, feature_tip, "main", runner=runner, pipe_runner=_git_pipe_real
        )
        self.assertEqual(result.status, "unmerged")
        self.assertEqual(result.reason, "content-check-failed")
        self.assertFalse(result.merged)

    def test_merges_rev_list_failure_degrades(self) -> None:
        """The `git rev-list --merges` enumeration (evil-merge detection)
        failing must degrade, not silently skip the check (which would
        fail open exactly on the population it exists to catch)."""
        _git(["checkout", "-b", "feature"], self.repo)
        _commit(self.repo, "a.txt", "A\n", "never merged")
        feature_tip = _head(self.repo)

        runner = _runner_intercepting("rev-list", occurrence=1, mode="fail")
        result = classify_merged(
            self.repo, feature_tip, "main", runner=runner, pipe_runner=_git_pipe_real
        )
        self.assertEqual(result.status, "unmerged")
        self.assertEqual(result.reason, "content-check-failed")
        self.assertFalse(result.merged)

    def test_evil_merge_diff_tree_failure_degrades(self) -> None:
        """`git diff-tree --cc --no-commit-id` (the evil-merge discriminator
        itself) failing must degrade, never silently treat the merge as
        clean."""
        _git(["checkout", "-b", "feature"], self.repo)
        c1 = _commit(self.repo, "x.txt", "x content\n", "X: add x.txt")

        _git(["checkout", "main"], self.repo)
        _commit(self.repo, "m.txt", "m content\n", "unrelated main work")

        _git(["checkout", "feature"], self.repo)
        _git(["merge", "--no-commit", "main"], self.repo)
        _write(self.repo, "evil.txt", "evil resolution content\n")
        _git(["add", "evil.txt"], self.repo)
        _git(["commit", "-m", "merge main into feature (resolution adds evil.txt)"], self.repo)
        c2 = _commit(self.repo, "y.txt", "y content\n", "Y: add y.txt")
        feature_tip = _head(self.repo)

        _git(["checkout", "main"], self.repo)
        _git(["cherry-pick", c1], self.repo)
        _git(["cherry-pick", c2], self.repo)

        runner = _runner_intercepting("diff-tree", occurrence=1, mode="fail")
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
