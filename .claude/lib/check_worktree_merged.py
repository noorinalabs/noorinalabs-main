#!/usr/bin/env python3
"""Classify whether a worktree's HEAD is fully merged into a remote ref.

`/session-start` Step 0 (main#1212, sibling of #1177) used to classify a
worktree as merged with a single test:

    git merge-base --is-ancestor "$head" origin/main

That is correct ONLY for a plain merge commit. A **squash** merge writes a
brand-new, single-parent commit onto the target branch, so the original
branch tip is never made an ancestor of it — the ancestry test returns false
*forever*, no matter how completely the branch's content landed. The same is
true of a **rebase-merge** (replayed commits get new hashes) and a
**cherry-pick** (a new commit object with the same diff). Five real
worktrees were flagged `UNMERGED` this way despite being 100% merged on
2026-07-30 (PRs #1153/#1154/#1155/#1156/#1173) — 0% precision on that
population.

This module keeps ancestry as the cheap fast path (it covers the merge-commit
majority with a single git call) and adds a **patch-id equivalence**
fallback, searched over `origin/main`'s *own history* since the branch's
merge-base — NOT a snapshot comparison against `origin/main`'s current tip
(an earlier version of this module compared `head`'s files, byte for byte,
against their CURRENT content on `remote_ref`; that decays, since unrelated
later commits keep touching the same files — validated directly against the
five real fixtures cited in main#1212, all five of which already showed this
decay days after landing). Patch-id equivalence against history does not
have this problem — the patch-id of a diff is stable regardless of what
happens to the file afterwards.

**The residual-history problem (PR #1213 review round).** An initial version
of this fallback compared ONLY the branch's full aggregate diff
(`merge_base..head`, collapsed into one patch) against `remote_ref`'s
history, and returned `merged` on any match. That is unsound: a branch can
carry genuinely unlanded commits whose *net* effect on the aggregate diff is
invisible — either because they cancel out (add a file, then remove it: two
real, never-landed commits, net tree change zero) or because `git patch-id`
is whitespace-insensitive (an unlanded reindent-only commit contributes
nothing to the aggregate's patch-id). Both were reproduced against the
initial version and both are ordinary development patterns, not contrived
edge cases.

The fix distinguishes *"commits already accounted for by a matched content
prefix"* from *"commits carrying content beyond it"*, via two coordinated
tests:

  1. **Earliest-matching-prefix search.** Walk `head`'s own commits
     oldest-to-newest (`git rev-list --reverse merge_base..head`). At each
     step, test whether the *cumulative* diff so far (`merge_base..commit_i`)
     has a patch-id matching some commit `remote_ref` has gained since
     `merge_base` (`git log -p --first-parent merge_base..remote_ref` fed
     through `git patch-id --stable`). Stop at the FIRST match — not the
     last. This is what catches the residual: whatever a later, cancelling
     or whitespace-only commit does to the *full-range* aggregate, it cannot
     hide a match found earlier by a strictly smaller prefix, because the
     search never advances past the earliest one it finds.
  2. **Per-commit corroboration for the residual.** Whatever commits are
     left after the matched prefix (all of them, if no prefix matched at
     all) must each, individually, have a patch-id-equivalent commit on
     `remote_ref` per `git cherry remote_ref head` — this is what correctly
     recognizes a rebase-merge replay or cherry-pick of the commits *after*
     an incidental early prefix match (e.g. the branch's first commit
     happens to match some `remote_ref` commit on its own, and the rest were
     legitimately replayed individually afterward — a real, verified case,
     not just theoretical). If every residual commit has an equivalent, the
     whole branch is merged; if any doesn't, that commit is genuinely
     unlanded and the branch is flagged, never auto-removed — REGARDLESS of
     whether the discarded full-range aggregate would have matched.

`git cherry` is only invoked when there is a non-empty residual to check
(an exact, no-residual prefix match skips it entirely — the common
single/multi-commit-squash case pays no extra cost over the original
design).

Deliberately NOT special-cased by merge-strategy name — every test here
looks only at patch-id (diff content) and commit-level residency, never at
commit graph shape or a fixed strategy label.

**Safety stance (never relaxed):**

  * A branch with any genuinely unlanded commit — including one whose net
    effect cancels against another unlanded commit (a file added then
    removed again), or that only reindents/reformats a file — surfaces in
    the residual and is classified ``unmerged``, never auto-removed. Both
    cases are covered by dedicated regression tests
    (``test_cancel_out_unlanded_commits_stay_flagged``,
    ``test_whitespace_only_unlanded_commit_stays_flagged``) and both pass:
    the earliest-matching-prefix search never advances past whatever it
    finds first, and `git cherry` evaluates each residual commit's own
    diff against its own immediate parent — not the misleading full-range
    aggregate — so a later cancellation or reindent cannot hide behind an
    earlier, genuine match.
  * This guarantee is bounded by `git patch-id` itself, not by anything
    specific to this module's algorithm: `git patch-id --stable` normalizes
    whitespace by design (this is what makes it tolerate the real #1156
    fixture, whose diff is identical to its landed squash only once line-
    number *and* pure-whitespace variance are excluded — the reason
    `--verbatim` is deliberately NOT used here, since it would misclassify
    that real, already-merged branch as unmerged). The one residual this
    implies: a genuinely unlanded commit whose content, after `git
    patch-id`'s whitespace normalization, is indistinguishable from some
    commit already on `remote_ref` would be misclassified as merged. This
    is a narrow, well-understood limitation of the underlying git primitive
    (the same one every patch-id-based tool inherits), not a defect
    introduced by the earliest-matching-prefix design — reimplementing
    `git patch-id`'s normalization from scratch to close it would be a
    disproportionate response to a collision risk this small.
  * Every internal git-command failure, including a non-empty diff that
    unexpectedly yields no `git patch-id` output (an unknown state, never
    treated as "no changes"), degrades to ``unmerged`` (never ``merged``) —
    "when in doubt, flag" (main#1212). A distinct ``error`` status is used
    only for the ancestry probe itself failing outright (a plumbing error,
    not a normal negative result); it is still treated as *not merged* by
    every caller (`.merged` is False, CLI exit is non-zero).
  * The whole test is 100% local git plumbing — no `gh`/network calls, so it
    works offline and never blocks the mandatory session-start step on
    network/auth availability. (A `gh`-based `mergedAt` corroboration was
    considered, per the issue's proposed fix, as an optional *reported
    reason* only; it is intentionally left out of this module to keep the
    decision path network-free and to avoid adding a `gh` round-trip — with
    its auth and rate-limit failure modes — to every worktree check in a step
    that already runs at the top of every session.)

CLI: ``python3 check_worktree_merged.py <repo_root> <head> [remote_ref]``
(default ``remote_ref`` is ``origin/main``). Prints one line
``<status> (<reason>): <detail>`` and exits 0 iff merged, 1 otherwise — the
exit code is the only thing a caller needs to decide auto-remove vs FLAG.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

GitRunner = Callable[[Sequence[str], Path], "subprocess.CompletedProcess[str]"]
# A second runner shape for the two commands that need to feed a diff/log
# stream to `git patch-id` on stdin rather than take a rev-range argument.
PipeRunner = Callable[[Sequence[str], Path, str], "subprocess.CompletedProcess[str]"]


def _git(args: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def _git_pipe(args: Sequence[str], cwd: Path, input_text: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
    )


@dataclass
class MergeClassification:
    """Outcome of :func:`classify_merged`.

    ``status`` is machine-readable and is the only field a caller needs to
    make the auto-remove-vs-flag decision (via :attr:`merged`):

      * ``merged``   — ``reason`` is ``ancestor`` (fast path) or
        ``content-equivalent`` (patch-id fallback; squash/rebase-merge/
        cherry-pick, possibly a matched prefix plus a per-commit-corroborated
        residual).
      * ``unmerged`` — ``reason`` is ``unlanded-changes`` (no content prefix
        matched at all — the plain never-merged case), ``content-matched-
        with-unlanded-history`` (a prefix DID match, but one or more commits
        after it have no patch-id-equivalent anywhere on `remote_ref` — see
        ``unmatched_commits``), ``no-common-ancestor`` (orphan/unrelated
        histories — definitionally not merged), or ``content-check-failed``
        (a git command in the fallback errored, or produced an unexpected/
        unparseable result; degrades to "not merged" rather than guessing).
      * ``error`` — the ancestry probe itself failed as a plumbing error
        (not a normal negative result). Still not-merged for every caller.

    ``unmatched_commits`` — populated only for the two "genuinely unlanded"
    reasons: the commit(s) with no patch-id-equivalent on ``remote_ref``.
    """

    status: str
    reason: str
    detail: str = ""
    unmatched_commits: list[str] = field(default_factory=list)

    @property
    def merged(self) -> bool:
        return self.status == "merged"


def _parse_patch_ids(text: str) -> list[tuple[str, str]]:
    """Parse `git patch-id` output: lines of ``<patch-id> [<commit-sha>]``."""
    pairs: list[tuple[str, str]] = []
    for line in text.splitlines():
        parts = line.split()
        if not parts:
            continue
        pid = parts[0]
        sha = parts[1] if len(parts) > 1 else ""
        pairs.append((pid, sha))
    return pairs


def _degrade(reason: str, detail: str) -> MergeClassification:
    """A git-command failure or unparseable result — never guess ``merged``."""
    return MergeClassification("unmerged", reason, detail)


def classify_merged(
    repo_root: str | Path,
    head: str,
    remote_ref: str = "origin/main",
    *,
    runner: GitRunner = _git,
    pipe_runner: PipeRunner = _git_pipe,
) -> MergeClassification:
    """Classify whether ``head`` is fully merged into ``remote_ref``. See module docs."""
    root = Path(repo_root)

    # ---- fast path: plain ancestry (covers the merge-commit majority) ------
    anc = runner(["merge-base", "--is-ancestor", head, remote_ref], root)
    if anc.returncode == 0:
        return MergeClassification("merged", "ancestor", f"{head} is an ancestor of {remote_ref}")
    if anc.returncode != 1:
        # `--is-ancestor` signals a true negative with exit 1; anything else
        # (bad rev, corrupt repo, ...) is a plumbing error, not "not merged".
        return MergeClassification(
            "error",
            "ancestor-check-failed",
            f"git merge-base --is-ancestor errored (exit {anc.returncode}): {anc.stderr.strip()}",
        )

    mb = runner(["merge-base", head, remote_ref], root)
    merge_base = mb.stdout.strip() if mb.returncode == 0 else ""
    if not merge_base:
        # No shared history at all (orphan branch / unrelated histories) —
        # this is a definite "not merged", not an unknown-error state.
        return MergeClassification(
            "unmerged",
            "no-common-ancestor",
            f"no common ancestor between {head} and {remote_ref} — cannot be merged",
        )

    # ---- trivial case: head introduces nothing at all over merge_base -----
    own_diff = runner(["diff", f"{merge_base}..{head}"], root)
    if own_diff.returncode != 0:
        return _degrade(
            "content-check-failed",
            f"git diff {merge_base}..{head} failed (exit {own_diff.returncode}): "
            f"{own_diff.stderr.strip()} — degraded to ancestry-only result",
        )
    if not own_diff.stdout.strip():
        # Typically the ancestry test above would already have caught this;
        # defensive fallback for e.g. an `--allow-empty` commit on top of
        # merge_base that introduces no tree change of its own.
        return MergeClassification(
            "merged",
            "content-equivalent",
            f"{head} introduces no changes over its merge-base with {remote_ref}",
        )

    # ---- enumerate head's own commits (oldest first) -----------------------
    commits_res = runner(["rev-list", "--reverse", f"{merge_base}..{head}"], root)
    if commits_res.returncode != 0:
        return _degrade(
            "content-check-failed",
            f"git rev-list --reverse {merge_base}..{head} failed "
            f"(exit {commits_res.returncode}): {commits_res.stderr.strip()} "
            f"— degraded to ancestry-only result",
        )
    commits = [c for c in commits_res.stdout.splitlines() if c]
    if not commits:
        # Defensive: a non-empty diff over a non-empty rev range should always
        # list at least one commit. Never fail open on an unexpected state.
        return _degrade(
            "content-check-failed",
            f"git rev-list --reverse {merge_base}..{head} returned no commits despite "
            f"a non-empty diff — unexpected state, degraded to ancestry-only result",
        )

    # ---- build the patch-id table for everything remote_ref gained --------
    main_log = runner(["log", "-p", "--first-parent", f"{merge_base}..{remote_ref}"], root)
    if main_log.returncode != 0:
        return _degrade(
            "content-check-failed",
            f"git log -p --first-parent {merge_base}..{remote_ref} failed "
            f"(exit {main_log.returncode}): {main_log.stderr.strip()} "
            f"— degraded to ancestry-only result",
        )
    main_pid_res = pipe_runner(["patch-id", "--stable"], root, main_log.stdout)
    if main_pid_res.returncode != 0:
        return _degrade(
            "content-check-failed",
            f"git patch-id (main range) failed (exit {main_pid_res.returncode}): "
            f"{main_pid_res.stderr.strip()} — degraded to ancestry-only result",
        )
    main_pids = dict(_parse_patch_ids(main_pid_res.stdout))

    # ---- earliest-matching-prefix search ------------------------------------
    # Stop at the FIRST commit whose cumulative diff since merge_base matches
    # something remote_ref already has — not the last — so a later commit
    # that cancels out or is whitespace-only in the full-range aggregate can
    # never hide behind an earlier, smaller, genuine match.
    match_index: int | None = None
    matched_sha = ""
    for i, commit in enumerate(commits):
        prefix_diff = runner(["diff", f"{merge_base}..{commit}"], root)
        if prefix_diff.returncode != 0:
            return _degrade(
                "content-check-failed",
                f"git diff {merge_base}..{commit} failed (exit {prefix_diff.returncode}): "
                f"{prefix_diff.stderr.strip()} — degraded to ancestry-only result",
            )
        if not prefix_diff.stdout.strip():
            continue  # no unique change yet at this prefix (e.g. an empty commit)
        prefix_pid_res = pipe_runner(["patch-id", "--stable"], root, prefix_diff.stdout)
        if prefix_pid_res.returncode != 0:
            return _degrade(
                "content-check-failed",
                f"git patch-id (prefix {commit[:12]}) failed "
                f"(exit {prefix_pid_res.returncode}): {prefix_pid_res.stderr.strip()} "
                f"— degraded to ancestry-only result",
            )
        prefix_pairs = _parse_patch_ids(prefix_pid_res.stdout)
        if not prefix_pairs:
            # A non-empty diff that produced no patch-id output is an unknown
            # state, not evidence of "no changes" — never fail open here.
            return _degrade(
                "content-check-failed",
                f"git patch-id (prefix {commit[:12]}) produced no output for a "
                f"non-empty diff — unexpected state, degraded to ancestry-only result",
            )
        prefix_pid = prefix_pairs[0][0]
        if prefix_pid in main_pids:
            match_index = i
            matched_sha = main_pids[prefix_pid] or "<unknown>"
            break

    residual = commits[match_index + 1 :] if match_index is not None else commits

    if not residual:
        # match_index must be the last commit here (nothing left over).
        return MergeClassification(
            "merged",
            "content-equivalent",
            f"branch's combined diff since merge-base {merge_base[:12]} matches "
            f"{remote_ref} commit {matched_sha[:12]} by patch-id "
            f"(squash/rebase-single-commit/cherry-pick landed the content)",
        )

    # ---- per-commit corroboration for the residual (git cherry) -----------
    cherry = runner(["cherry", remote_ref, head], root)
    if cherry.returncode != 0:
        return _degrade(
            "content-check-failed",
            f"git cherry {remote_ref} {head} failed (exit {cherry.returncode}): "
            f"{cherry.stderr.strip()} — degraded to ancestry-only result",
        )
    matched_by_cherry: set[str] = set()
    for line in cherry.stdout.splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2 and parts[0] == "-":
            matched_by_cherry.add(parts[1].strip())

    unmatched = [c for c in residual if c not in matched_by_cherry]

    if not unmatched:
        if match_index is None:
            # Defensive / message-selection only, not a classification-safety
            # branch: for a linear branch (the normal case), commits[0]'s
            # parent is always merge_base, so the prefix test's check at i=0
            # (diff merge_base..commits[0]) and git cherry's own per-commit
            # check for commits[0] (diff commits[0]^..commits[0]) are the
            # IDENTICAL comparison. If that comparison fails to match at i=0,
            # commits[0] is therefore ALSO unmatched by cherry, which would
            # make `unmatched` non-empty — so reaching this branch with
            # `match_index is None` requires a non-linear branch history
            # (e.g. an internal merge commit inside the feature branch
            # itself). Kept as a defensive fallback; not independently
            # covered by a test for that reason (mirrors the two dead
            # empty-diff branches the PR #1213 review accepted as low-
            # priority awareness-only, not a safety gap).
            detail = (
                f"every commit unique to {head} has a patch-id-equivalent commit "
                f"already on {remote_ref} (git cherry found no unmatched commits) "
                f"— rebase-merge or cherry-pick landed the content"
            )
        else:
            detail = (
                f"commits up to {commits[match_index][:12]} match {remote_ref} commit "
                f"{matched_sha[:12]} by patch-id (squash landed that prefix), and the "
                f"remaining {len(residual)} commit(s) each have their own patch-id-"
                f"equivalent on {remote_ref} via git cherry — rebase-merge or "
                f"cherry-pick landed the rest"
            )
        return MergeClassification("merged", "content-equivalent", detail)

    shown = ", ".join(c[:12] for c in unmatched[:5]) + (", ..." if len(unmatched) > 5 else "")
    if match_index is None:
        reason = "unlanded-changes"
        detail = (
            f"{len(unmatched)} commit(s) unique to {head} have no patch-id-equivalent "
            f"on {remote_ref} — genuine unlanded content: {shown}"
        )
    else:
        reason = "content-matched-with-unlanded-history"
        detail = (
            f"an initial content prefix (up to {commits[match_index][:12]}) matches "
            f"{remote_ref} commit {matched_sha[:12]} by patch-id, but {len(unmatched)} "
            f"further commit(s) have no patch-id-equivalent anywhere on {remote_ref} — "
            f"genuine unlanded content despite the earlier match: {shown}"
        )
    return MergeClassification("unmerged", reason, detail, unmatched_commits=unmatched)


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 2:
        print(
            "usage: check_worktree_merged.py <repo_root> <head> [remote_ref]",
            file=sys.stderr,
        )
        return 2
    repo_root, head = args[0], args[1]
    remote_ref = args[2] if len(args) > 2 else "origin/main"

    result = classify_merged(repo_root, head, remote_ref)
    print(f"{result.status} ({result.reason}): {result.detail}")
    return 0 if result.merged else 1


if __name__ == "__main__":
    raise SystemExit(main())
