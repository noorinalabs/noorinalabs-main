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

**The guarantee, as revised by owner decision on 2026-08-02 (PR #1213 review
round 3, superseding acceptance criterion 2 as originally filed):** this
module classifies `merged` iff **the branch's cumulative diff since its
merge-base is fully present on `remote_ref`** — a *net-content* test, not a
per-commit one. Verdicts are **order-independent**: two branches with the
same commit set applied in a different order classify identically, because
the primary test depends only on the two tree states (`merge_base` and
`head`), never on the intermediate commit history that produced `head`.

Two rounds of prior review chased a *per-commit* guarantee ("every commit
unique to `head` must individually have a landed equivalent") and found it
unachievable: a squash merge is *definitionally* the case where a branch's
commits never landed individually, so `git cherry` reports every commit of a
genuinely squash-merged branch as unlanded — any rule demanding per-commit
landedness re-breaks the very fixtures this module exists to classify
correctly. Concretely reproduced: the same three commits (a real content
commit A, plus B/C — add a file, then remove it again) in order A,B,C versus
B,C,A. `git cherry` reports 2 unlanded commits in **both** orderings; the
branch's *net* content (which is what actually ends up in the working tree,
and what `git worktree remove` would discard) is identical in both — A's
content only, since B and C cancel. A per-commit round-2 design ("earliest
matching prefix, then per-commit-corroborate the residual") produced
*different* verdicts for the two orderings, which is the order-dependence
bug this design fixes.

**Two coordinated tests, either sufficient, neither depending on `head`'s
internal commit ordering:**

  1. **Net-content match (primary).** The combined diff `merge_base..head`
     (the branch's *entire* accumulated change, computed once, over the
     full range — never an intermediate prefix) is compared by patch-id
     against every commit `remote_ref` has gained since `merge_base`
     (`git log -p --first-parent merge_base..remote_ref` fed through
     `git patch-id --stable`). A match means some single commit on
     `remote_ref` — the squash, or a single-commit rebase/cherry-pick — *is*
     the landed form of `head`'s entire accumulated content. Because this
     only ever looks at `merge_base` and `head`'s final trees, it is
     order-independent by construction: two orderings of the same commit
     set produce the same tree at `head`, hence the same diff, hence the
     same patch-id, hence the same verdict.
  2. **Per-commit corroboration (fallback, for a multi-commit non-squash
     landing).** `git cherry remote_ref head` reports, for each commit
     `git cherry` examines, whether an equivalent patch-id already exists on
     `remote_ref`. If none of the commits `git cherry` marks `+` (no
     equivalent found) remain, every commit it examined has landed — this is
     what recognizes a rebase-merge replay or a cherry-pick of *several*
     original commits, none of which individually equals the (single-commit)
     net-content diff test A is comparing against.

     Only commits `git cherry` explicitly marks `+` count as unmatched
     candidates — NOT "everything git cherry didn't explicitly mark `-`".
     `git cherry` never lists **merge commits** in its output at all (verified
     directly: neither `+` nor `-`); an earlier version of this module
     treated "absent from cherry's matched list" as "unmatched", which
     reported a branch's own internal merge commit (routine — merging
     `remote_ref` in to resolve conflicts) as having "no patch-id-equivalent
     anywhere on `remote_ref`" — a statement `git cherry`'s own output
     contradicts, recreating #1212's exact "flagged every session, forever"
     symptom for a new population. Test 1 still sees the true net content
     either way (an internal merge's own resolution, if it introduces
     genuinely unique content, shows up in `merge_base..head` regardless of
     commit graph shape), so this narrowing does not create a silent-
     content-loss gap — it only stops treating "not examined by cherry" as
     evidence of "unlanded".

     A truly **empty** commit (`--allow-empty`, zero diff against its own
     immediate parent) is a separate case: unlike a merge commit, `git
     cherry` does NOT silently omit it — it IS marked `+` (verified directly
     against git 2.43), even though it introduces no content and can never
     be "unlanded". This module filters it out explicitly: any commit `git
     cherry` marks `+` is checked against its own immediate-parent diff, and
     dropped from the unmatched set if that diff is empty.

Deliberately NOT special-cased by merge-strategy name — both tests look only
at patch-id (diff content) and `git cherry`'s own explicit verdicts, never
at commit graph shape or a fixed strategy label.

**Safety stance (never relaxed):**

  * A branch whose net content since `merge_base` is not fully present on
    `remote_ref` — by either test — is classified `unmerged`, never
    auto-removed. Order-independence is itself a pinned property: both
    orderings of the cancelling-commit-pair fixture are asserted to produce
    the *same* verdict (`test_cancel_out_order_independence`), not merely
    each individually correct.
  * This guarantee is bounded by `git patch-id` itself, not by anything
    specific to this module's algorithm: `git patch-id --stable` normalizes
    whitespace by design (this is what makes it tolerate the real #1156
    fixture, whose diff is identical to its landed squash only once line-
    number *and* pure-whitespace variance are excluded — the reason
    `--verbatim` is deliberately NOT used here, since it would misclassify
    that real, already-merged branch as unmerged). The disclosed residual
    this implies: a genuinely unlanded change whose content, after `git
    patch-id`'s whitespace normalization, is indistinguishable from an
    already-landed change is treated as landed too (independently confirmed:
    two reindents of the same line differing only in whitespace amount
    produce identical patch-ids). This is a narrow, well-understood
    limitation of the underlying git primitive (the same one every
    patch-id-based tool inherits), not a defect specific to this module —
    reimplementing `git patch-id`'s normalization from scratch to close it
    would be a disproportionate response to a collision risk this small.
  * Every internal git-command failure, including a non-empty diff that
    unexpectedly yields no `git patch-id` output (an unknown state, never
    treated as "no changes"), degrades to `unmerged` (never `merged`) —
    "when in doubt, flag" (main#1212). A distinct `error` status is used
    only for the ancestry probe itself failing outright (a plumbing error,
    not a normal negative result); it is still treated as *not merged* by
    every caller (`.merged` is False, CLI exit is non-zero).
  * The whole test is 100% local git plumbing — no `gh`/network calls, so it
    works offline and never blocks the mandatory session-start step on
    network/auth availability.
  * **Step 0 no longer force-removes** (owner decision, PR #1213 round 3): a
    worktree that does not remove cleanly is FLAGGED for a manual decision.
    Since `git worktree remove` never deletes the branch ref either way,
    this means a misclassification by this module can cost, at worst, a
    stale worktree *directory* — never a commit, never a branch, and (with
    the force fallback gone) never even uncommitted content, since a dirty
    worktree that fails a plain `remove` is simply left alone.

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
        ``content-equivalent`` (net-content match, or per-commit `git
        cherry` corroboration for a multi-commit rebase-merge/cherry-pick).
      * ``unmerged`` — ``reason`` is ``unlanded-changes`` (neither test found
        a match — see ``unmatched_commits`` for the commits `git cherry`
        explicitly marked as having no equivalent), ``no-common-ancestor``
        (orphan/unrelated histories — definitionally not merged), or
        ``content-check-failed`` (a git command in the fallback errored, or
        produced an unexpected/unparseable result; degrades to "not merged"
        rather than guessing).
      * ``error`` — the ancestry probe itself failed as a plumbing error
        (not a normal negative result). Still not-merged for every caller.

    ``unmatched_commits`` — populated only for ``unlanded-changes``: the
    commit(s) `git cherry` explicitly marked `+` (no patch-id-equivalent
    found on ``remote_ref``) AND which are not themselves empty commits.
    Never includes a merge commit (`git cherry` never examines them at all)
    or a truly empty commit (explicitly filtered even though `git cherry`
    does mark it `+`) — see the module docstring's per-commit-corroboration
    section.
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
        # merge_base that introduces no tree change of its own. Trivially
        # order-independent: no commits, no ordering to depend on.
        return MergeClassification(
            "merged",
            "content-equivalent",
            f"{head} introduces no changes over its merge-base with {remote_ref}",
        )

    # ---- test 1: net-content match (order-independent primary test) -------
    # ONE diff over the FULL range, never an intermediate prefix — this is
    # what makes the result depend only on (merge_base, head)'s trees, never
    # on the order of the commits that produced head.
    own_pid_res = pipe_runner(["patch-id", "--stable"], root, own_diff.stdout)
    if own_pid_res.returncode != 0:
        return _degrade(
            "content-check-failed",
            f"git patch-id (own diff) failed (exit {own_pid_res.returncode}): "
            f"{own_pid_res.stderr.strip()} — degraded to ancestry-only result",
        )
    own_pairs = _parse_patch_ids(own_pid_res.stdout)
    if not own_pairs:
        # A non-empty diff that produced no patch-id output is an unknown
        # state, not evidence of "no changes" — never fail open here.
        return _degrade(
            "content-check-failed",
            "git patch-id (own diff) produced no output for a non-empty diff — "
            "unexpected state, degraded to ancestry-only result",
        )
    own_patch_id = own_pairs[0][0]

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

    if own_patch_id in main_pids:
        matched = main_pids[own_patch_id] or "<unknown>"
        return MergeClassification(
            "merged",
            "content-equivalent",
            f"branch's cumulative diff since merge-base {merge_base[:12]} matches "
            f"{remote_ref} commit {matched[:12]} by patch-id — net content fully "
            f"landed (squash or single-commit rebase/cherry-pick)",
        )

    # ---- test 2: per-commit corroboration (rebase-merge / multi cherry-pick) -
    cherry = runner(["cherry", remote_ref, head], root)
    if cherry.returncode != 0:
        return _degrade(
            "content-check-failed",
            f"git cherry {remote_ref} {head} failed (exit {cherry.returncode}): "
            f"{cherry.stderr.strip()} — degraded to ancestry-only result",
        )
    # Only a commit git cherry EXPLICITLY marks "+" counts as a candidate for
    # unmatched. git cherry never lists MERGE commits at all (neither "+" nor
    # "-") — treating "not seen as '-'" as "unmatched" (an earlier version of
    # this module did) misreported a branch's own internal merge commit
    # (routine — merging remote_ref in to resolve conflicts) as unlanded, a
    # statement git cherry's own output contradicts.
    candidates = [line.split()[1] for line in cherry.stdout.splitlines() if line.startswith("+ ")]

    # A truly EMPTY commit (--allow-empty, zero diff against its own
    # immediate parent) IS marked "+" by git cherry (verified: git does not
    # omit it the way it omits merge commits) even though it introduces no
    # content at all and can therefore never be "unlanded". Filter these out
    # explicitly rather than relying on git cherry's polarity for them.
    unmatched: list[str] = []
    for c in candidates:
        own_commit_diff = runner(["diff", f"{c}^..{c}"], root)
        if own_commit_diff.returncode != 0:
            return _degrade(
                "content-check-failed",
                f"git diff {c[:12]}^..{c[:12]} failed (exit {own_commit_diff.returncode}): "
                f"{own_commit_diff.stderr.strip()} — degraded to ancestry-only result",
            )
        if own_commit_diff.stdout.strip():
            unmatched.append(c)
        # else: c is an empty commit — contributes no content, not a residual.

    if not unmatched:
        return MergeClassification(
            "merged",
            "content-equivalent",
            f"every commit git cherry examined for {head} has a patch-id-equivalent "
            f"commit already on {remote_ref} (no commit marked unmatched) — "
            f"rebase-merge or cherry-pick landed the content",
        )

    shown = ", ".join(c[:12] for c in unmatched[:5]) + (", ..." if len(unmatched) > 5 else "")
    return MergeClassification(
        "unmerged",
        "unlanded-changes",
        f"{len(unmatched)} commit(s) unique to {head} have no patch-id-equivalent "
        f"on {remote_ref} (git cherry) and the cumulative diff does not match "
        f"anything on {remote_ref} either — genuine unlanded content: {shown}",
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
