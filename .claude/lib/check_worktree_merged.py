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
     (`git log -p --first-parent merge_base..remote_ref` streamed directly
     into `git patch-id --stable` over an OS pipe — `_git_log_patch_id`,
     #1214 — rather than buffered into a Python string first; this is a
     memory-profile change only, the comparison result is unaffected). A
     match means some single commit on
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
     equivalent found) remain — see the two carve-outs below — every commit
     it examined has landed. This is what recognizes a rebase-merge replay
     or a cherry-pick of *several* original commits, none of which
     individually equals the (single-commit) net-content diff test 1 is
     comparing against. It is order-independent for a different reason than
     test 1: reordering `head`'s commits (the only reordering that preserves
     the same commit *set*, i.e. commutative changes touching disjoint
     content) does not change any individual commit's own diff against its
     immediate predecessor, and `git patch-id --stable` hashes each diff's
     content while ignoring line-number/context shifts — so the same set of
     per-commit patch-ids, and hence the same match/no-match verdicts, comes
     out regardless of the order those commits were made in.

     Only commits `git cherry` explicitly marks `+` count as unmatched
     candidates — NOT "everything git cherry didn't explicitly mark `-`".
     `git cherry` never lists **merge commits** in its output at all (verified
     directly: neither `+` nor `-`); an earlier version of this module
     treated "absent from cherry's matched list" as "unmatched", which
     reported a branch's own internal merge commit (routine — merging
     `remote_ref` in to resolve conflicts) as having "no patch-id-equivalent
     anywhere on `remote_ref`" — a statement `git cherry`'s own output
     contradicts, recreating #1212's exact "flagged every session, forever"
     symptom for a new population.

     A truly **empty** commit (`--allow-empty`, zero diff against its own
     immediate parent) is a separate case: unlike a merge commit, `git
     cherry` does NOT silently omit it — it IS marked `+` (verified directly
     against git 2.43), even though it introduces no content and can never
     be "unlanded". This module filters it out explicitly: any commit `git
     cherry` marks `+` is checked against its own immediate-parent diff, and
     dropped from the unmatched set if that diff is empty.

     A merge commit's OWN unique content is a **third, separate check**, not
     covered by anything above. An earlier version of this module argued
     that ignoring merge commits was safe because "test 1 still sees the
     true net content either way" — that argument does not hold: **test 2 is
     only reached when test 1 has already failed to match**, so on the
     exact path where a merge commit's content would matter, test 1 has
     already been ruled out as a source of cover. Concretely: an ordinary
     conflict resolution can add content present in **neither parent** (an
     "evil merge"), and `git cherry` never examines merge commits at all —
     GitHub's rebase-merge makes this a realistic, not contrived, shape: it
     flattens a branch and replays only the *non-merge* commits, dropping
     the merge (and its resolution) entirely. This module therefore
     enumerates `git rev-list --merges merge_base..head` and, for each merge
     commit, runs `git diff-tree --cc --no-commit-id <sha>` — the combined
     diff of the merge against both parents, with the leading commit-id line
     stripped. A **non-empty** result is resolution content unique to the
     merge; that commit is added to the unmatched set. `--no-commit-id`
     matters: bare `--cc` alone always prints the commit-id as its first
     line, so *every* merge (including a routine, content-free one) would
     show up as "non-empty" without it — silently reopening the exact
     over-strict bug (merge commits wrongly treated as unlanded) the earlier
     fix above exists to close.

Deliberately NOT special-cased by merge-strategy name — every test here
looks only at patch-id (diff content), `git cherry`'s own explicit
verdicts, or a merge's own combined diff, never at commit graph shape or a
fixed strategy label as such.

**Removal candidacy is a SECOND, ORTHOGONAL axis (#1341) — merged-ness is
not the removal decision.** Everything above answers *"is this branch's
content already on `remote_ref`?"*. Step 0 asks a different question:
*"is there anything here worth reclaiming?"*. Those came apart on a
**freshly-created worktree that has not committed yet**: its HEAD *is*
`origin/main`, so it is trivially an ancestor, the fast path answers
`merged` — **correctly**, since a branch with no commits of its own has, by
construction, no unlanded content — and Step 0 removed a clean, live
worktree out from under an active agent (observed on in-flight #1117 during
wave-29). The false verdict was never about merged-ness; it was about
reading merged-ness as a reclaim decision.

So the merged classification above is **unchanged and untraded** — a fresh
worktree still classifies `merged`/`ancestor`, exactly as the #1213
guarantee requires. What is added is a separate predicate that gates the
*removal* decision only:

    a branch whose HEAD is itself a commit on `remote_ref`'s own
    first-parent (mainline) history has produced **no commits of its own**,
    so there is nothing to reclaim -> `removal_block = "no-own-commits"`,
    `safe_to_remove` False, CLI exit 3 (not 0).

Why the first-parent chain rather than the `HEAD == remote_ref` equality
the issue proposed: equality only catches a worktree branched off the
*current* tip. Sessions here run long enough that `origin/main` advances
under an idle worktree, after which HEAD is an ancestor but no longer equal
— same zero-own-work branch, same live agent, and equality would have
missed it. Mainline membership covers both, and it does not touch the
population the sweep exists for (#526): a squash- or rebase-merged branch
tip is not an ancestor at all (it never reaches this guard), and a
merge-commit-merged tip is reachable only through the merge's **second**
parent, so it is an ancestor but *not* on the mainline chain — it stays a
removal candidate. The one shape this over-flags is a fast-forward-merged
branch (its tip literally becomes a mainline commit); GitHub's three merge
buttons never fast-forward, and over-flagging costs a stale directory,
which is the accepted-cheap direction.

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
  * The removal-candidacy probe (#1341) degrades in the same direction:
    if either of its two git calls fails, the result is
    ``removal_block = "mainline-check-failed"`` — a probe that could not be
    run is not evidence that the branch has work of its own, so removal is
    withheld and the worktree is flagged. Note the *classification* is left
    intact in that case (still `merged`); only removal candidacy degrades,
    because the two axes are independent and a failure on one is not
    evidence about the other.
  * **Step 0 no longer force-removes** (owner decision, PR #1213 round 3): a
    worktree that does not remove cleanly is FLAGGED for a manual decision.
    Since `git worktree remove` never deletes the branch ref either way,
    this means a misclassification by this module can cost, at worst, a
    stale worktree *directory* — never a commit, never a branch, and (with
    the force fallback gone) never even uncommitted content, since a dirty
    worktree that fails a plain `remove` is simply left alone. That bound
    holds for *committed* work; it never covered the #1341 case, where the
    worktree being destroyed was clean precisely because its agent had not
    written anything yet.

CLI: ``python3 check_worktree_merged.py <repo_root> <head> [remote_ref]``
(default ``remote_ref`` is ``origin/main``). Prints one line
``<status> (<reason>)[ [not-a-removal-candidate: <block>]]: <detail>``.
Exit codes — the exit code is the only thing a caller needs to decide
auto-remove vs FLAG:

  * ``0`` — merged **and** a removal candidate: safe to auto-remove.
  * ``1`` — not merged (``unmerged`` or ``error``).
  * ``2`` — usage error.
  * ``3`` — merged, but **not** a removal candidate (#1341: no commits of
    its own, or the candidacy probe failed). Non-zero, so a caller that
    only knows the old ``0 == remove`` contract still fails safe; a caller
    that distinguishes it can label the worktree FRESH rather than the
    misleading UNMERGED.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

GitRunner = Callable[[Sequence[str], Path], "subprocess.CompletedProcess[str]"]
# A second runner shape for the one command that needs to feed a diff stream
# to `git patch-id` on stdin (the branch's own, bounded-size diff).
PipeRunner = Callable[[Sequence[str], Path, str], "subprocess.CompletedProcess[str]"]
# A third runner shape for `git log -p ... | git patch-id --stable` (#1214):
# unlike PipeRunner, this one never receives the log text as a Python string
# at all — see `_git_log_patch_id`. Same call shape as GitRunner (a git
# argv + cwd in, a CompletedProcess-shaped result out) since the caller never
# needs to supply input text; only the *implementation* streams internally.
LogPatchIdRunner = Callable[[Sequence[str], Path], "subprocess.CompletedProcess[str]"]


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


def _git_log_patch_id(log_args: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run ``git <log_args>`` piped directly into ``git patch-id --stable``
    over an OS-level pipe, without ever materializing the (potentially large,
    O(worktree staleness)) patch text as a Python string (#1214).

    Behaviourally identical to::

        log = _git(log_args, cwd)
        return _git_pipe(["patch-id", "--stable"], cwd, log.stdout)

    — same combined exit-code/stdout/stderr contract from the caller's point
    of view — but `git log`'s stdout file descriptor is connected straight to
    `git patch-id`'s stdin via `Popen(stdin=<the other process's stdout
    pipe>)`, so this process never holds more than `git patch-id`'s own
    output resident (one short line per commit, not the full diff text).

    Only `git patch-id`'s stdout is meaningful on success (the same
    ``<patch-id> [<sha>]`` lines `_parse_patch_ids` expects); the combined
    ``returncode`` is 0 only if *both* stages exited 0, so a `git log`
    failure degrades exactly like a `git patch-id` failure did before this
    change — the caller does not need to know which stage failed.

    **Why `git log`'s stderr goes to a `tempfile`, not a pipe (#1249).**
    `patch_id_proc.communicate()` below drains `patch_id_proc`'s own
    stdout+stderr concurrently (that is what `communicate()` is for), but it
    knows nothing about `log_proc`'s stderr. If `log_proc`'s stderr were
    `subprocess.PIPE` (as it originally was), nobody drains that pipe until
    *after* `communicate()` returns — and `communicate()` doesn't return
    until `git log` finishes writing its stdout. A `git log` that writes more
    than one OS pipe-buffer's worth of stderr (~64KiB on Linux — plausible
    across a large `merge_base..remote_ref` range, e.g. a per-commit warning
    repeated many times) blocks mid-write on the full stderr pipe, which
    stalls its stdout too, which stalls `patch_id_proc` waiting on stdin —
    the classic "multiple pipes into one drain point, only one drained"
    deadlock `communicate()` exists to avoid for a *single* process, just
    relocated to the *other* process's stderr in a two-`Popen` pipeline.
    Routing it to an unbounded-capacity `tempfile.TemporaryFile` instead
    means a write there can never block on a reader, so this hazard cannot
    reoccur regardless of how much `git log` writes to stderr.
    """
    with tempfile.TemporaryFile() as log_stderr_file:
        log_proc = subprocess.Popen(
            ["git", *log_args],
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=log_stderr_file,
            text=True,
        )
        assert log_proc.stdout is not None  # guaranteed by stdout=PIPE above
        patch_id_proc = subprocess.Popen(
            ["git", "patch-id", "--stable"],
            cwd=str(cwd),
            stdin=log_proc.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        # Standard Popen -> Popen pipe idiom: release our copy of the read
        # end so patch_id_proc's own (already-duplicated) fd is what keeps it
        # open, and `git log` gets a normal EOF/SIGPIPE signal once patch-id
        # is done — dropping this leaves our copy open, so `git log` never
        # sees EOF/SIGPIPE if `patch-id` exits early (hang risk + fd leak).
        log_proc.stdout.close()

        patch_stdout, patch_stderr = patch_id_proc.communicate()
        log_proc.wait()
        log_stderr_file.seek(0)
        log_stderr = log_stderr_file.read().decode("utf-8", errors="replace")

    argv_desc = ["git", *log_args, "|", "git", "patch-id", "--stable"]
    if log_proc.returncode != 0:
        return subprocess.CompletedProcess(
            args=argv_desc, returncode=log_proc.returncode, stdout="", stderr=log_stderr
        )
    if patch_id_proc.returncode != 0:
        return subprocess.CompletedProcess(
            args=argv_desc, returncode=patch_id_proc.returncode, stdout="", stderr=patch_stderr
        )
    return subprocess.CompletedProcess(args=argv_desc, returncode=0, stdout=patch_stdout, stderr="")


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
    non-merge commit(s) `git cherry` explicitly marked `+` and which are not
    themselves empty commits, UNION any merge commit whose own combined diff
    (`git diff-tree --cc --no-commit-id`) is non-empty (unique conflict-
    resolution content `git cherry` never examines at all). Never includes a
    truly empty commit (explicitly filtered even though `git cherry` does
    mark it `+`) or a merge commit with no unique content of its own — see
    the module docstring's per-commit-corroboration section.

    ``removal_block`` — the SECOND, orthogonal axis (#1341). Empty means
    "nothing blocks reclaiming this worktree"; non-empty is a short machine-
    readable reason why it must not be auto-removed even though its content
    is fully landed:

      * ``no-own-commits``       — HEAD is a commit on ``remote_ref``'s own
        first-parent history, so the branch has produced nothing of its own
        (a fresh, not-yet-committed worktree — very likely live).
      * ``mainline-check-failed`` — the candidacy probe itself errored;
        withhold removal rather than assume there is work here.

    It never affects ``status``/``merged``: a fresh worktree is genuinely
    merged, it is just not a reclaim candidate. Callers deciding
    auto-remove-vs-FLAG must read :attr:`safe_to_remove`, not
    :attr:`merged`.
    """

    status: str
    reason: str
    detail: str = ""
    unmatched_commits: list[str] = field(default_factory=list)
    removal_block: str = ""

    @property
    def merged(self) -> bool:
        return self.status == "merged"

    @property
    def safe_to_remove(self) -> bool:
        """The auto-remove predicate: fully landed AND has work to reclaim."""
        return self.merged and not self.removal_block


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


def _removal_block(root: Path, head: str, remote_ref: str, runner: GitRunner) -> tuple[str, str]:
    """Removal-candidacy probe (#1341) — the axis orthogonal to merged-ness.

    Returns ``(block_reason, block_detail)``; ``("", "")`` means the branch
    has commits of its own and is a genuine reclaim candidate.

    Only meaningful once ``head`` is known to be an ancestor of
    ``remote_ref`` (mainline membership implies ancestry, so calling it off
    that path would always answer "not blocked" at the cost of two git
    invocations). The test: is ``head`` itself one of the commits on
    ``remote_ref``'s **first-parent** chain? If so the branch has never
    committed anything of its own — nothing to reclaim, and very likely a
    worktree an agent is about to write into.

    Both git calls degrade toward *withholding removal* (never toward
    removing): a probe we could not run is not evidence of work.
    """
    head_res = runner(["rev-parse", "--verify", f"{head}^{{commit}}"], root)
    head_sha = head_res.stdout.strip() if head_res.returncode == 0 else ""
    if not head_sha:
        return (
            "mainline-check-failed",
            f"could not resolve {head} to a commit "
            f"(exit {head_res.returncode}): {head_res.stderr.strip()} — "
            f"cannot confirm this worktree has commits of its own, so removal is withheld",
        )

    # First-parent chain of remote_ref. Membership is an exact SHA-set test:
    # every line is a full 40-char object name, so no prefix/substring
    # ambiguity is possible.
    chain = runner(["rev-list", "--first-parent", remote_ref], root)
    if chain.returncode != 0:
        return (
            "mainline-check-failed",
            f"git rev-list --first-parent {remote_ref} failed "
            f"(exit {chain.returncode}): {chain.stderr.strip()} — "
            f"cannot confirm this worktree has commits of its own, so removal is withheld",
        )
    mainline = set(chain.stdout.split())
    if not mainline:
        # `git rev-list` over a resolvable ref always lists at least that
        # ref's own commit, so a successful-but-empty result is an unknown
        # state — never read it as "head is not on the mainline, remove away"
        # (the same fail-open guard the patch-id path carries).
        return (
            "mainline-check-failed",
            f"git rev-list --first-parent {remote_ref} succeeded but listed no commits — "
            f"unexpected state, so removal is withheld",
        )
    if head_sha in mainline:
        return (
            "no-own-commits",
            f"{head_sha[:12]} is itself a commit on {remote_ref}'s first-parent history, "
            f"so this branch has no commits of its own — a fresh/unstarted worktree with "
            f"nothing to reclaim (very likely in active use), not a removal candidate",
        )
    return ("", "")


def classify_merged(
    repo_root: str | Path,
    head: str,
    remote_ref: str = "origin/main",
    *,
    runner: GitRunner = _git,
    pipe_runner: PipeRunner = _git_pipe,
    log_patch_id_runner: LogPatchIdRunner = _git_log_patch_id,
) -> MergeClassification:
    """Classify whether ``head`` is fully merged into ``remote_ref``. See module docs."""
    root = Path(repo_root)

    # ---- fast path: plain ancestry (covers the merge-commit majority) ------
    anc = runner(["merge-base", "--is-ancestor", head, remote_ref], root)
    if anc.returncode == 0:
        # Merged — but ancestry alone does not mean there is anything here to
        # reclaim. A worktree that has not committed yet sits ON remote_ref's
        # mainline, which is trivially an ancestor (#1341). Classification is
        # untouched; only removal candidacy is gated.
        block_reason, block_detail = _removal_block(root, head, remote_ref, runner)
        detail = f"{head} is an ancestor of {remote_ref}"
        if block_reason:
            detail = f"{detail}; {block_detail}"
        return MergeClassification("merged", "ancestor", detail, removal_block=block_reason)
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

    # Streamed (#1214): `git log -p ...` is piped straight into `git patch-id`
    # over an OS pipe rather than buffered into a Python string first — see
    # `_git_log_patch_id`. Same net effect as the old two-step
    # runner(["log", ...]) + pipe_runner(["patch-id", ...], log.stdout)
    # sequence, just without the O(patch size) resident string in between.
    main_pid_res = log_patch_id_runner(
        ["log", "-p", "--first-parent", f"{merge_base}..{remote_ref}"], root
    )
    if main_pid_res.returncode != 0:
        return _degrade(
            "content-check-failed",
            f"git log -p --first-parent {merge_base}..{remote_ref} | git patch-id --stable "
            f"failed (exit {main_pid_res.returncode}): {main_pid_res.stderr.strip()} "
            f"— degraded to ancestry-only result",
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

    # ---- merge commits: git cherry never examines them at all, so a merge's
    # OWN unique resolution content (an ordinary conflict resolution can add
    # content present in NEITHER parent) is invisible to everything above.
    # Test 1 provides no cover here either — this code is only reached when
    # test 1 has already failed to match, which is exactly the branch shape
    # (a multi-commit non-squash landing) where a merge's resolution content
    # would otherwise slip through undetected.
    merges_res = runner(["rev-list", "--merges", f"{merge_base}..{head}"], root)
    if merges_res.returncode != 0:
        return _degrade(
            "content-check-failed",
            f"git rev-list --merges {merge_base}..{head} failed "
            f"(exit {merges_res.returncode}): {merges_res.stderr.strip()} "
            f"— degraded to ancestry-only result",
        )
    merge_commits = [c for c in merges_res.stdout.splitlines() if c]
    evil_merges: list[str] = []
    for m in merge_commits:
        # `--cc` alone always prints the commit-id line first, so EVERY merge
        # (including a routine, content-free one) shows >=1 line — that would
        # false-flag every ordinary "merge remote_ref into head" and reopen
        # the exact over-strict bug the empty-commit/merge-commit fix above
        # exists to close. `--no-commit-id` strips that header, leaving
        # genuinely empty output for a clean merge and the actual combined
        # resolution diff for one that isn't.
        resolution = runner(["diff-tree", "--cc", "--no-commit-id", m], root)
        if resolution.returncode != 0:
            return _degrade(
                "content-check-failed",
                f"git diff-tree --cc --no-commit-id {m[:12]} failed "
                f"(exit {resolution.returncode}): {resolution.stderr.strip()} "
                f"— degraded to ancestry-only result",
            )
        if resolution.stdout.strip():
            evil_merges.append(m)
        # else: a clean merge — its content is the union of its parents',
        # nothing unique to check for.

    if not unmatched and not evil_merges:
        return MergeClassification(
            "merged",
            "content-equivalent",
            f"every commit git cherry examined for {head} has a patch-id-equivalent "
            f"commit already on {remote_ref} (no commit marked unmatched), and no "
            f"merge commit in range carries resolution content absent from "
            f"{remote_ref} — rebase-merge or cherry-pick landed the content",
        )

    detail_parts = []
    if unmatched:
        shown = ", ".join(c[:12] for c in unmatched[:5]) + (", ..." if len(unmatched) > 5 else "")
        detail_parts.append(
            f"{len(unmatched)} commit(s) unique to {head} have no patch-id-equivalent "
            f"on {remote_ref} (git cherry): {shown}"
        )
    if evil_merges:
        shown_m = ", ".join(m[:12] for m in evil_merges[:5]) + (
            ", ..." if len(evil_merges) > 5 else ""
        )
        detail_parts.append(
            f"{len(evil_merges)} merge commit(s) carry resolution content not present "
            f"on {remote_ref} (git diff-tree --cc), invisible to git cherry entirely: "
            f"{shown_m}"
        )
    detail_parts.append(f"and the cumulative diff does not match anything on {remote_ref} either")

    return MergeClassification(
        "unmerged",
        "unlanded-changes",
        "; ".join(detail_parts) + " — genuine unlanded content",
        unmatched_commits=[*unmatched, *evil_merges],
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
    prefix = f"{result.status} ({result.reason})"
    if result.removal_block:
        prefix = f"{prefix} [not-a-removal-candidate: {result.removal_block}]"
    print(f"{prefix}: {result.detail}")
    if result.safe_to_remove:
        return 0
    # Merged but not a reclaim candidate gets its own non-zero code (#1341)
    # so a caller can say FRESH instead of the misleading UNMERGED; a caller
    # that only knows `0 == remove` still fails safe on it.
    return 3 if result.merged else 1


if __name__ == "__main__":
    raise SystemExit(main())
