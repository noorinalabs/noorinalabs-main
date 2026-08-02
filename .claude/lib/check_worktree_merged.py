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
merge-base — NOT a snapshot comparison against `origin/main`'s current tip.

Why history search rather than a current-tree content diff: an earlier
version of this module compared `head`'s files, byte for byte, against their
CURRENT content on `remote_ref`. That decays — real unrelated commits keep
touching the same files after a squash lands, and days later the "same
file" comparison starts failing even though the branch's original content is
still fully present in `remote_ref`'s history. Validated directly against
the five real fixtures cited in main#1212: every one of them already showed
this decay (e.g. `.claude/hooks/_shell_parse.py` had 600+ further lines
changed by unrelated commits within days of the squash landing), so a
current-tree comparison would have "fixed" the false positive today only to
reintroduce it a few sessions later. Patch-id equivalence against history
does not have this problem — the patch-id of a diff is stable regardless of
what happens to the file afterwards.

Two patch-id tests, either of which is sufficient:

  1. **Aggregate match** (catches squash — single- or multi-commit): the
     combined diff `merge_base..head` (i.e. everything the branch ever added,
     collapsed into one patch, exactly what a squash commit's own diff would
     be) is compared by patch-id against every commit `remote_ref` has gained
     since `merge_base` (`git log -p --first-parent merge_base..remote_ref`
     fed through `git patch-id --stable`). If some commit's own diff has the
     same patch-id as the branch's aggregate diff, that commit *is* the
     landed squash (or single-commit rebase/cherry-pick) — merged. This is
     the case a **per-commit** patch-id test (`git cherry`) cannot catch on
     its own: a multi-commit squash produces exactly one new commit on
     `remote_ref`, so no single ORIGINAL commit's own patch-id will ever
     match it.
  2. **Per-commit match** (catches rebase-merge replay and a plain
     cherry-pick of possibly-many original commits): ``git cherry
     remote_ref head`` reports, for every commit unique to `head`, whether an
     equivalent patch-id already exists on `remote_ref`. If every commit has
     an equivalent (no `+` lines), the branch's entire history individually
     replayed onto `remote_ref` — merged.

Deliberately NOT special-cased by merge-strategy name — both tests look only
at patch-id (diff content), never at commit graph shape or a fixed strategy
label.

**Safety stance (never relaxed):**

  * A branch with any genuinely unlanded change fails both tests (at least
    one commit surfaces in `git cherry`'s `+` list AND the aggregate diff's
    patch-id matches nothing) and is classified ``unmerged``. This is exactly
    what happens for a tip carrying one extra, never-landed commit on top of
    an otherwise fully-squashed history (main#1212 acceptance criterion).
  * Every internal git-command failure degrades to ``unmerged`` (never
    ``merged``) — "when in doubt, flag" (main#1212). A distinct ``error``
    status is used only for the ancestry probe itself failing outright (a
    plumbing error, not a normal "not an ancestor" result); it is still
    treated as *not merged* by every caller (`.merged` is False, CLI exit is
    non-zero).
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
        cherry-pick).
      * ``unmerged`` — ``reason`` is ``unlanded-changes`` (the normal,
        expected case: genuine unlanded content — see ``unmatched_commits``),
        ``no-common-ancestor`` (orphan/unrelated histories — definitionally
        not merged), or ``content-check-failed`` (a git command in the
        fallback errored; degrades to the pre-fix ancestry-only conclusion
        rather than guessing merged).
      * ``error`` — the ancestry probe itself failed as a plumbing error
        (not a normal negative result). Still not-merged for every caller.

    ``unmatched_commits`` — populated only for ``unlanded-changes``: the
    commit(s) unique to ``head`` for which `git cherry` found no
    patch-id-equivalent on ``remote_ref``.
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

    # ---- test A: aggregate patch-id match (squash, single- or multi-commit) ---
    own_diff = runner(["diff", f"{merge_base}..{head}"], root)
    if own_diff.returncode != 0:
        return MergeClassification(
            "unmerged",
            "content-check-failed",
            f"git diff {merge_base}..{head} failed (exit {own_diff.returncode}): "
            f"{own_diff.stderr.strip()} — degraded to ancestry-only result",
        )

    if not own_diff.stdout.strip():
        # head introduces literally nothing over its merge-base with
        # remote_ref — trivially fully landed (typically the ancestry test
        # above would already have caught this; defensive fallback).
        return MergeClassification(
            "merged",
            "content-equivalent",
            f"{head} introduces no changes over its merge-base with {remote_ref}",
        )

    own_pid_res = pipe_runner(["patch-id", "--stable"], root, own_diff.stdout)
    if own_pid_res.returncode != 0:
        return MergeClassification(
            "unmerged",
            "content-check-failed",
            f"git patch-id (own diff) failed (exit {own_pid_res.returncode}): "
            f"{own_pid_res.stderr.strip()} — degraded to ancestry-only result",
        )
    own_pairs = _parse_patch_ids(own_pid_res.stdout)
    if not own_pairs:
        return MergeClassification(
            "merged",
            "content-equivalent",
            f"{head} introduces no changes over its merge-base with {remote_ref}",
        )
    own_patch_id = own_pairs[0][0]

    main_log = runner(["log", "-p", "--first-parent", f"{merge_base}..{remote_ref}"], root)
    if main_log.returncode != 0:
        return MergeClassification(
            "unmerged",
            "content-check-failed",
            f"git log -p --first-parent {merge_base}..{remote_ref} failed "
            f"(exit {main_log.returncode}): {main_log.stderr.strip()} "
            f"— degraded to ancestry-only result",
        )
    main_pid_res = pipe_runner(["patch-id", "--stable"], root, main_log.stdout)
    if main_pid_res.returncode != 0:
        return MergeClassification(
            "unmerged",
            "content-check-failed",
            f"git patch-id (main range) failed (exit {main_pid_res.returncode}): "
            f"{main_pid_res.stderr.strip()} — degraded to ancestry-only result",
        )
    main_pids = dict(_parse_patch_ids(main_pid_res.stdout))

    if own_patch_id in main_pids:
        matched = main_pids[own_patch_id] or "<unknown>"
        return MergeClassification(
            "merged",
            "content-equivalent",
            f"branch's combined diff since merge-base {merge_base[:12]} matches "
            f"{remote_ref} commit {matched[:12]} by patch-id "
            f"(squash/single-commit rebase landed the content)",
        )

    # ---- test B: per-commit patch-id match (rebase-merge replay, cherry-pick) -
    cherry = runner(["cherry", remote_ref, head], root)
    if cherry.returncode != 0:
        return MergeClassification(
            "unmerged",
            "content-check-failed",
            f"git cherry {remote_ref} {head} failed (exit {cherry.returncode}): "
            f"{cherry.stderr.strip()} — degraded to ancestry-only result",
        )
    unmatched = [line.split()[1] for line in cherry.stdout.splitlines() if line.startswith("+ ")]
    if not unmatched:
        return MergeClassification(
            "merged",
            "content-equivalent",
            f"every commit unique to {head} has a patch-id-equivalent commit "
            f"already on {remote_ref} (git cherry found no unmatched commits) "
            f"— rebase-merge or cherry-pick landed the content",
        )

    shown = ", ".join(c[:12] for c in unmatched[:5]) + (", ..." if len(unmatched) > 5 else "")
    return MergeClassification(
        "unmerged",
        "unlanded-changes",
        f"{len(unmatched)} commit(s) unique to {head} have no patch-id-equivalent "
        f"on {remote_ref} — genuine unlanded content: {shown}",
        unmatched_commits=unmatched,
    )


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
