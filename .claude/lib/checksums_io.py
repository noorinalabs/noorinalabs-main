#!/usr/bin/env python3
"""Shared read/write helpers for ``ontology/checksums.json`` (#1042).

PR #1040 (closes #1038) fixed `ensure_ascii=True` re-escaping churn on the
committed ``ontology/checksums.json`` for the one *programmatic, committed*
writer — ``.claude/hooks/ontology_tracker.py``. The other writer, the
``/ontology-rebuild`` resolver, is agent-driven (a ``SKILL.md`` prose
instruction, not a code module), so the fix there was documentation only:
nothing enforced that the agent executing the skill actually followed the
"use ``ensure_ascii=False``" instruction. A future resolver run — or an edit
to the skill that drops the reminder — reintroduces the exact flip-flop
diff-noise class #1038 fixed, just moved to the other writer instead of
closed.

This module closes the class rather than documenting around it: both the
tracker hook and the ``/ontology-rebuild`` resolver call the SAME
``read_checksums`` / ``write_checksums`` functions (the resolver via the
``mark-resolved`` CLI below, since it is agent-driven and has no Python
module of its own to import from). Neither caller needs to remember the
serialization convention — it is the only path either has to write the file.

Byte-stability contract
========================
``write_checksums`` always writes with ``json.dump(data, f, indent=2,
ensure_ascii=False)`` plus a trailing newline, via an atomic tmp-file
``rename``. ``ensure_ascii=False`` preserves literal UTF-8 in the top-level
``description`` field (``—``, ``×``); the ``ensure_ascii=True`` default
re-escapes it into ``\\uXXXX`` sequences on every write, producing a
permanent flip-flop diff on the committed file (#1038). The atomic
tmp-file-then-``Path.replace()`` write means a concurrent reader (e.g. the
librarian, or a second hook invocation) never observes a partially written
file.

No-silent-zeros contract (#1142)
================================
This module used to expose two WRITERS (``mark-resolved``, ``prune``) and no
reader, so every consumer that needed the dirty count hand-rolled a JSON read
against a schema it had to recall correctly. Two consecutive sessions got that
read wrong and **both wrong reads returned a plausible ``0``** — one compared a
``sha256`` key that does not exist in the entry schema, so the comparison was
skipped on all 277 entries and the loop counted nothing. ``0`` is also the
healthy value, so no shape of mistake failed loudly.

Three things close that class:

1. ``classify_entry`` is the ONE implementation of the canonical
   ``last_tracked != last_resolved`` predicate. ``session_start.py``'s
   ``_ontology_staleness`` consumes it instead of re-implementing it.
2. An entry that does not match the schema is ``ENTRY_MALFORMED`` — a third
   state, never folded into "clean". The two historical wrong reads both
   produced entries that a ``.get(...) != .get(...)`` comparison silently
   called clean; here they are counted and named.
3. The read path forks. ``read_checksums`` still fails OPEN (a PostToolUse
   hook must never raise) and is for WRITERS. ``read_checksums_strict`` /
   ``read_status`` raise ``ChecksumsUnreadable`` and are for READERS — a
   missing or unparseable ledger must never be reported as "0 dirty", which
   is exactly what a fail-open read would produce.
4. ``compute_status`` HASHES each tracked file and compares the result to the
   stored values (#1505). Closer (1) compares the ledger's two stored values
   **to each other**, never to the file, so it answers "has an agent edited
   this file through Edit/Write in this checkout since the last rebuild" —
   while every reader treats it as "the overlay is in sync with the tree".
   Those are different claims. A file changed by a pull, by a merge, by
   another session, or inside a worktree never moves ``last_tracked``, so the
   entry stays ``last_tracked == last_resolved`` and reports clean forever.
   When #1505 was filed, 158 of 314 tracked entries were in exactly that
   state while ``status`` printed ``0 dirty`` at exit 0.

Entry states, in the order ``classify_against_file`` decides them::

    malformed        the entry's shape is not one the reader understands
    dirty            last_tracked != last_resolved (an agent edited it)
    undeterminable   stored values agree, but the file could not be hashed
                     (absent from the tree, or unreadable) - NOT clean
    drifted          stored values agree, and the file matches NEITHER
    clean            stored values agree AND the file hashes to them

Only the last is clean. ``ChecksumsStatus.clean`` additionally requires
``verified`` — a status computed without a repo root hashed nothing, and a
measurement that was never taken must not read as a passing one.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# The empty-file default shape both callers fall back to when the checksums
# file is missing or unparseable — never raise from a read (the tracker hook
# must never fail the calling tool call; the resolver CLI degrades the same
# way for consistency). This is a TEMPLATE, not a shared return value: every
# fail-open branch returns a `copy.deepcopy(_EMPTY)` so callers that mutate the
# nested `"files"` dict (e.g. `ontology_tracker.check()` on a missing file)
# never pollute this module-global.
_EMPTY: dict[str, Any] = {"version": 1, "files": {}}

# Entry states returned by `classify_entry`. MALFORMED is deliberately a third
# state rather than a flavor of clean: the whole point of #1142 is that an
# entry the reader does not understand must not be silently counted as fine.
ENTRY_CLEAN = "clean"
ENTRY_DIRTY = "dirty"
ENTRY_MALFORMED = "malformed"
# Two more states, added by #1505, both deliberately outside "clean":
# DRIFTED is the file disagreeing with a ledger that agrees with itself, and
# UNDETERMINABLE is a tracked file the reader could not hash at all. The
# second is the load-bearing one — "I could not measure this entry" has to be
# distinguishable from "I measured it and it was fine", on every channel.
ENTRY_DRIFTED = "drifted"
ENTRY_UNDETERMINABLE = "undeterminable"

# The two fields the dirty predicate compares. `tracked_at` / `resolved_at` are
# timestamps, informational only — the predicate never looks at them.
_TRACKED_KEY = "last_tracked"
_RESOLVED_KEY = "last_resolved"

# `status` exit codes. Split so a caller can tell "clean" from "could not read"
# — conflating them is the #1142 failure itself.
EXIT_CLEAN = 0
EXIT_NEEDS_ATTENTION = 1
EXIT_USAGE = 2
EXIT_UNREADABLE = 3
# 4 is its own code, not a flavour of 1, because the REMEDIATIONS DIFFER and
# applying 1's remediation to a 4 manufactures a false clean: a dirty entry is
# fixed by `/ontology-rebuild` + `mark-resolved`, whereas `mark-resolved` on a
# DRIFTED entry stamps last_resolved = last_tracked — recording agreement
# between two values that BOTH already disagree with the file. The skill
# tables (`/session-start` 3a, `/ontology-librarian` 1a) prescribe different
# actions for the two, so the exit channel has to let a caller tell them
# apart; folding drift into 1 routes it into the action that hides it.
EXIT_DRIFTED = 4


class ChecksumsUnreadable(Exception):
    """The ledger could not be read or is not the shape a reader understands.

    Raised only by the STRICT read path (``read_checksums_strict`` /
    ``compute_status`` / ``read_status``). The writers' ``read_checksums``
    keeps failing open, because a PostToolUse hook that raises fails the tool
    call that triggered it. Readers get the opposite policy: refusing to answer
    is correct, answering ``0 dirty`` for a file that could not be parsed is
    not.
    """


def read_checksums_strict(path: Path) -> dict[str, Any]:
    """Read and parse ``checksums.json``, raising rather than defaulting.

    Same failure set ``read_checksums`` swallows — missing/unreadable file,
    invalid JSON, non-object top level — but surfaced as
    ``ChecksumsUnreadable`` with a message naming the cause. Use this (not
    ``read_checksums``) whenever the answer is going to be *reported* rather
    than written back.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except OSError as exc:
        raise ChecksumsUnreadable(f"cannot read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ChecksumsUnreadable(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ChecksumsUnreadable(
            f"{path} top level is {type(data).__name__}, expected a JSON object"
        )
    return data


def read_checksums(path: Path) -> dict[str, Any]:
    """Read and parse ``checksums.json``, defaulting to an empty structure.

    Returns a fresh ``{"version": 1, "files": {}}`` if the file is missing or
    is not valid JSON — matching the tracker hook's historical fail-open
    behavior (a PostToolUse hook must never raise).

    This is the WRITERS' read path. It cannot distinguish "clean" from
    "unreadable", so a reader must use ``read_checksums_strict`` /
    ``read_status`` instead (#1142).
    """
    try:
        return read_checksums_strict(path)
    except ChecksumsUnreadable:
        return copy.deepcopy(_EMPTY)


def compute_sha256(file_path: Path) -> str | None:
    """SHA-256 of a file's bytes, or ``None`` if it cannot be read.

    THE single hashing function for this ledger (#1505). It used to be
    ``ontology_tracker._compute_sha256`` — private to the WRITER, while the
    reader hashed nothing at all, so there was no second copy only because
    there was no second implementation. Adding the reader's hash check as a
    fresh copy would have created exactly the duplicate-copy-drift class this
    repo is closing elsewhere: a divergence in chunking is harmless, a
    divergence in how bytes are opened or normalized is not, and the symptom
    would be every entry reading as drifted forever. The tracker now imports
    this one.

    Returns ``None`` — never raises, never a partial digest — on any
    ``OSError``: a missing file, a directory, a permission error. Callers MUST
    treat ``None`` as "could not determine", never as "unchanged"
    (``classify_against_file`` maps it to ``ENTRY_UNDETERMINABLE``).
    """
    try:
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        # PermissionError, IsADirectoryError and FileNotFoundError are all
        # OSError subclasses; naming them separately adds nothing.
        return None


def classify_entry(entry: Any) -> tuple[str, str]:
    """Classify one ``files`` entry. THE single dirty predicate (#1142).

    Returns ``(state, detail)`` where state is ``ENTRY_CLEAN``,
    ``ENTRY_DIRTY``, or ``ENTRY_MALFORMED``. ``detail`` names the schema
    problem for a malformed entry and is ``""`` otherwise.

    The predicate is ``last_tracked != last_resolved``. Every caller that
    needs a dirty count must come through here rather than re-deriving it —
    the field names are not guessable (the historical wrong read compared a
    ``sha256`` key that has never existed in this schema) and every way of
    guessing wrong yields a comparison that quietly evaluates to "equal".

    An entry missing either field, or holding a non-string in either, is
    MALFORMED — not clean. ``last_resolved: ""`` is well-formed and DIRTY
    against any non-empty ``last_tracked``: that is the legitimate shape of a
    freshly (re-)tracked file, and the tracker writes it on purpose.

    SCOPE (#1505): this function only ever compares the ledger to ITSELF. Its
    ``ENTRY_CLEAN`` therefore means "no agent edited this file through
    Edit/Write in this checkout since the last rebuild" — NOT "the file
    matches what the ledger stores". ``classify_against_file`` is the one that
    opens the file; every reader that is going to report freshness must go
    through that one instead.
    """
    if not isinstance(entry, dict):
        return ENTRY_MALFORMED, f"entry is {type(entry).__name__}, expected an object"
    missing = [key for key in (_TRACKED_KEY, _RESOLVED_KEY) if key not in entry]
    if missing:
        return ENTRY_MALFORMED, f"missing {', '.join(missing)}"
    tracked = entry[_TRACKED_KEY]
    resolved = entry[_RESOLVED_KEY]
    for key, value in ((_TRACKED_KEY, tracked), (_RESOLVED_KEY, resolved)):
        if not isinstance(value, str):
            return ENTRY_MALFORMED, f"{key} is {type(value).__name__}, expected a string"
    return (ENTRY_DIRTY, "") if tracked != resolved else (ENTRY_CLEAN, "")


def classify_against_file(entry: Any, file_path: Path) -> tuple[str, str]:
    """Classify an entry against the FILE, not only against its own two hashes.

    ``classify_entry`` compares the ledger's two stored values to each other;
    this compares the agreed-upon value to the bytes on disk. Precedence, and
    why each step is where it is:

    * MALFORMED and DIRTY short-circuit before the file is touched. Both
      already block "clean" and both already carry a remediation, so hashing
      could only add a second reason for a verdict that will not change. This
      is also the non-regression #1505 asks for by name: a dirty entry stays
      DIRTY and is never reclassified as drifted.
    * UNDETERMINABLE when the stored values agree but the file cannot be
      hashed — absent from the tree, or unreadable. This is NOT clean, and
      that is the whole point: an entry the reader failed to measure must not
      be counted with the entries it measured and found fine. It is a
      different thing from ``prune``'s "the path is gone, drop the entry":
      ``prune`` is an explicit, guarded, preview-by-default WRITE, while
      ``status`` merely has to refuse to call an unmeasured entry measured.
    * DRIFTED when the file hashes to neither stored value. This is the 158.
    * CLEAN only when the stored values agree AND the file hashes to them.

    One consequence worth naming: ``mark_resolved`` sets ``last_resolved =
    last_tracked`` without re-reading the file, so resolving a dirty entry
    whose file changed after it was tracked yields an entry that is clean by
    the stored-values predicate and DRIFTED here. That false-clean is now
    visible on the very next ``status`` run instead of permanently invisible.
    """
    state, detail = classify_entry(entry)
    if state != ENTRY_CLEAN:
        return state, detail

    if not file_path.exists():
        return ENTRY_UNDETERMINABLE, "tracked path is absent from this tree — nothing to hash"

    actual = compute_sha256(file_path)
    if actual is None:
        return ENTRY_UNDETERMINABLE, "tracked path could not be read — hash not computed"

    stored = entry[_TRACKED_KEY]
    if actual != stored:
        return ENTRY_DRIFTED, f"file hashes to {actual[:12]}..., ledger stores {stored[:12]}..."
    return ENTRY_CLEAN, ""


@dataclass(frozen=True)
class ChecksumsStatus:
    """Reader-facing summary of a checksums ledger.

    Every list is sorted for stable output. ``malformed``, ``drifted`` and
    ``undeterminable`` carry ``(path, reason)`` pairs so the report says *why*
    an entry landed there rather than just how many did.

    ``verified`` records whether the files were actually hashed. It defaults
    to ``False`` on purpose: a ``ChecksumsStatus`` constructed without that
    evidence must not be able to claim ``clean`` (#1505).
    """

    total: int
    dirty: tuple[str, ...]
    malformed: tuple[tuple[str, str], ...]
    drifted: tuple[tuple[str, str], ...] = ()
    undeterminable: tuple[tuple[str, str], ...] = ()
    verified: bool = False

    @property
    def clean(self) -> bool:
        """True only when every tracked file was hashed and every one agreed.

        Four conditions block it, all for the same reason — a reader must not
        report a state it did not establish:

        * ``dirty`` — an agent edited the file since the last rebuild.
        * ``malformed`` — an entry the reader cannot classify is unknown
          state, and reporting unknown as fine is the bug (#1142) this module
          exists to prevent.
        * ``drifted`` — the file matches neither stored hash (#1505).
        * ``undeterminable`` — a tracked file that could not be hashed at all.
          "Could not evaluate" is not a pass.

        And ``verified`` gates all of it: with no repo root, no file was
        opened, so the three empty file-derived lists are the empty result of
        a check that never ran — indistinguishable, without this flag, from
        the empty result of a check that ran and found nothing.
        """
        return (
            self.verified
            and not self.dirty
            and not self.malformed
            and not self.drifted
            and not self.undeterminable
        )

    @property
    def not_current(self) -> tuple[str, ...]:
        """Every tracked path not known to be in sync — sorted, de-duplicated.

        The union the annotating readers want (``smart_grep_ontology``'s
        "[STALE]" marker): dirty, malformed, drifted and undeterminable all
        mean "not known to be current", which is exactly what those callers
        are asking. Keeping the union here stops each of them from picking a
        subset and quietly under-reporting.
        """
        paths = set(self.dirty)
        for group in (self.malformed, self.drifted, self.undeterminable):
            paths.update(rel for rel, _ in group)
        return tuple(sorted(paths))


def compute_status(data: dict[str, Any], repo_root: Path | None = None) -> ChecksumsStatus:
    """Summarize an already-parsed ledger. Raises on an unrecognized shape.

    ``data["files"]`` must be present and a mapping. A ledger without it is
    ``ChecksumsUnreadable`` rather than "0 tracked, 0 dirty": the legacy
    flat-map fallback some ad-hoc readers used (``data.get("files", data)``)
    turns a shape mismatch into a plausible zero, which is the #1142 failure.
    Every ledger this module writes has a ``files`` mapping, and ``_EMPTY``
    seeds one, so the strict reading costs nothing real.

    ``repo_root`` is the directory the entry keys are relative to (what
    ``ontology_tracker._relative_path`` writes them against). Given one, every
    entry that the stored-values predicate calls clean is additionally HASHED
    and compared to the file — the #1505 check. Given ``None``, no file is
    opened; the result is a shape-only summary with ``verified=False``, which
    can never be ``clean``. That asymmetry is the guard: the caller who omits
    the root gets an explicitly-unverified answer, not a quietly passing one.

    ``read_status`` supplies the root by default, so no in-repo reader has to
    remember to.
    """
    files = data.get("files")
    if not isinstance(files, dict):
        kind = "missing" if files is None else f"a {type(files).__name__}"
        raise ChecksumsUnreadable(f"checksums document has no 'files' object ('files' is {kind})")
    dirty: list[str] = []
    malformed: list[tuple[str, str]] = []
    drifted: list[tuple[str, str]] = []
    undeterminable: list[tuple[str, str]] = []
    for rel in sorted(files):
        entry = files[rel]
        if repo_root is None:
            state, detail = classify_entry(entry)
        else:
            state, detail = classify_against_file(entry, repo_root / rel)
        if state == ENTRY_DIRTY:
            dirty.append(rel)
        elif state == ENTRY_MALFORMED:
            malformed.append((rel, detail))
        elif state == ENTRY_DRIFTED:
            drifted.append((rel, detail))
        elif state == ENTRY_UNDETERMINABLE:
            undeterminable.append((rel, detail))
    return ChecksumsStatus(
        total=len(files),
        dirty=tuple(dirty),
        malformed=tuple(malformed),
        drifted=tuple(drifted),
        undeterminable=tuple(undeterminable),
        verified=repo_root is not None,
    )


def repo_root_for(checksums_path: Path) -> Path:
    """``<root>/ontology/checksums.json`` -> ``<root>``.

    The same derivation ``prune`` has always used for ``--repo-root``, hoisted
    so the reader and the pruner cannot disagree about which tree an entry key
    is relative to.
    """
    return checksums_path.resolve().parent.parent


def read_status(path: Path, repo_root: Path | None = None) -> ChecksumsStatus:
    """Strict read + summarize, WITH the on-disk hash check. The one call a
    reader needs (#1142, #1505).

    ``repo_root`` defaults to ``repo_root_for(path)``, so the three hook
    readers keep calling ``read_status(checksums_file)`` and get drift
    detection without changing their call. Pass it explicitly to check a
    ledger against a different tree (e.g. from a linked worktree, where the
    gitignored child-repo clones are structurally absent and would otherwise
    all report undeterminable).

    Raises ``ChecksumsUnreadable`` if the file is missing, unparseable, or not
    shaped like a checksums ledger.
    """
    root = repo_root_for(path) if repo_root is None else repo_root
    return compute_status(read_checksums_strict(path), root)


def write_checksums(path: Path, data: dict[str, Any]) -> None:
    """Atomically write ``checksums.json`` with the byte-stable serialization.

    See the module docstring's "Byte-stability contract" for why
    ``ensure_ascii=False`` and the atomic-replace write are both load-bearing.
    Creates the parent directory if needed (mirrors the tracker hook's prior
    inline behavior).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    tmp.replace(path)


def mark_resolved(data: dict[str, Any], rel_paths: list[str], now: str) -> list[str]:
    """Set ``last_resolved = last_tracked`` and ``resolved_at = now`` for each path.

    Mutates ``data["files"]`` in place and returns the subset of ``rel_paths``
    that were actually present and resolved (a path not yet in ``files`` is
    not an entry to resolve — silently skipped rather than raising, since the
    resolver may be handed a path list wider than what the tracker has ever
    seen).
    """
    files = data.setdefault("files", {})
    resolved: list[str] = []
    for rel in rel_paths:
        entry = files.get(rel)
        if entry is None:
            continue
        entry["last_resolved"] = entry.get("last_tracked", "")
        entry["resolved_at"] = now
        resolved.append(rel)
    return resolved


def is_linked_worktree_root(git_root: Path) -> bool:
    """True if ``git_root`` is a LINKED WORKTREE's root (not a plain checkout).

    A linked worktree's ``.git`` is a FILE holding ``gitdir: <admin-dir>``. So
    is a submodule's, and so is a ``clone --separate-git-dir`` checkout's — so
    the pointer's *existence* proves nothing, and testing it for a
    ``/worktrees/`` substring is wrong in both directions of specificity. Two
    real layouts defeat that substring (both verified against actual git, not
    fabricated pointers):

      * a submodule at a path containing a ``worktrees`` component, e.g.
        ``gitdir: …/.git/modules/worktrees/libbar``
      * ``git clone --separate-git-dir`` with the git dir parked under any
        directory named ``worktrees``

    Both hold real committed source, and skipping them silently blinds the
    tracker to a whole tree — the exact failure the caller's fail-open
    asymmetry exists to prevent.

    Discriminate on git's own invariant instead: a linked worktree's admin
    directory always contains BOTH a ``gitdir`` backlink file and a
    ``commondir`` file. A submodule's ``.git/modules/<name>`` never contains
    either, and a ``--separate-git-dir`` git dir contains neither. This also
    correctly accepts a worktree of a bare repo and a worktree *of* a
    submodule, which a path-component check would misclassify.

    Fails OPEN (returns False) on every error — an unreadable ``.git``, an
    unrecognized pointer, or an admin dir that cannot be stat'd. Callers use
    this to decide whether to SKIP, so False (do not skip) is the safe answer.
    """
    dot_git = git_root / ".git"
    if not dot_git.is_file():
        return False  # A plain checkout (.git is a directory) — not a worktree.

    try:
        pointer = dot_git.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return False  # Unreadable — fail open.

    if not pointer.startswith("gitdir:"):
        return False  # Not a layout we recognize — fail open.

    # `Path / <absolute>` yields the absolute path, so this handles git's
    # absolute pointers and the relative ones it writes for submodules alike.
    admin = git_root / pointer[len("gitdir:") :].strip()
    try:
        return (admin / "gitdir").is_file() and (admin / "commondir").is_file()
    except OSError:
        return False  # Cannot stat the admin dir — fail open.


def prune_missing(data: dict[str, Any], repo_root: Path) -> list[str]:
    """Drop entries whose tracked path no longer exists under ``repo_root``.

    Mutates ``data["files"]`` in place and returns the removed keys, sorted.

    Why this is needed: the tracker records a path relative to ``REPO_ROOT``,
    so an Edit inside an ephemeral tree that ``ontology_tracker._should_skip``
    fails to recognize lands a permanent entry keyed to a directory that later
    ceases to exist (the wave-28 ``da-wt-490/*`` case — a linked worktree
    parked at the repo root rather than under ``.worktrees/``, so the
    name-based worktree filter did not catch it). Such an entry can never be
    resolved by re-reading the file (there is no file), and it is not
    ``last_tracked == last_resolved``, so it reports as dirty forever and each
    ``/ontology-rebuild`` has to hand-``mark-resolved`` it back to quiet.

    ``ontology_tracker._is_linked_worktree`` is the *prevention* half of the
    fix; this is the *cleanup* half, for entries already in the file and for
    any future skip-filter leak. Deliberately conservative: it removes only
    entries whose path is genuinely absent from disk, never entries that are
    merely stale, dirty, or unreferenced by the ontology.

    CAVEAT — this is an on-disk existence test, not a git-history one. A file
    that exists on a child repo's ``main`` but not on the branch that repo
    happens to be checked out at right now reads as absent and would be
    pruned. That is why the ``prune`` CLI PREVIEWS by default and needs an
    explicit ``--apply`` to write (#1137), rather than being something a
    lifecycle skill runs unattended: confirm the candidate list is
    genuinely-deleted (``git cat-file -e origin/main:<path>``) before applying.
    Re-tracking is cheap if a prune does go wrong — the next Edit/Write of the
    file re-creates the entry — but it re-enters with an empty
    ``last_resolved`` and so reports dirty once.
    """
    files = data.setdefault("files", {})
    removed = sorted(rel for rel in files if not (repo_root / rel).exists())
    for rel in removed:
        del files[rel]
    return removed


def _default_checksums_path() -> Path:
    """``ontology/checksums.json`` relative to this file's repo root.

    Mirrors ``ontology_tracker.py``'s ``REPO_ROOT`` derivation
    (``.claude/lib/checksums_io.py`` is two levels below the repo root, same
    as ``.claude/hooks/ontology_tracker.py``).
    """
    repo_root = Path(__file__).resolve().parent.parent.parent
    return repo_root / "ontology" / "checksums.json"


def main(argv: list[str]) -> int:
    """CLI entry point for the ``/ontology-rebuild`` resolver (#1042).

    The resolver is agent-driven (a ``SKILL.md`` prose instruction), so it has
    no Python module of its own to import ``mark_resolved`` from directly.
    Exposing a ``mark-resolved`` subcommand here means the skill's step 4 can
    shell out to THIS module instead of hand-rolling a ``json.dump`` call —
    the resolver never needs to remember the ``ensure_ascii=False`` convention
    because it never writes the file itself.

    The ``prune`` subcommand is the cleanup half of the orphan-entry fix (see
    ``prune_missing``): it drops entries whose file no longer exists on disk,
    which the resolver otherwise has to hand-``mark-resolved`` every pass.

    The ``status`` subcommand is the READER (#1142) — the dirty count the
    ``/ontology-rebuild`` and ``/session-start`` skills need, so neither has
    to hand-roll a JSON read against a schema whose every mis-guess yields a
    plausible ``0``.

    Usage:
        python3 .claude/lib/checksums_io.py status
            [--checksums <file>] [--repo-root <dir>] [--json]
        python3 .claude/lib/checksums_io.py mark-resolved <path> [<path> ...]
        python3 .claude/lib/checksums_io.py mark-resolved --checksums <file> <path> ...
        python3 .claude/lib/checksums_io.py prune
            [--checksums <file>] [--repo-root <dir>] [--apply] [--dry-run] [--force]

    ``--checksums`` may appear at any position. This is hand-rolled parsing
    rather than argparse, and an earlier revision required it FIRST — so
    ``prune --dry-run --checksums X`` died with "unexpected argument
    '--checksums'". It failed safe, but an undocumented ordering rule in a
    destructive CLI is a trap, so the flag is now extracted positionally-
    agnostically instead.

    ``--checksums=PATH`` and ``--checksums PATH`` are BOTH accepted, for ALL
    THREE subcommands (#1285). Uniformly accepting the ``=`` spelling removes
    the class rather than erroring on it, and the class was not theoretical:
    the extraction used to match the flag by exact token, so
    ``mark-resolved --checksums=/tmp/x ontology/domain.yaml`` matched nothing,
    the ``=`` token fell through unfiltered into the path list, and the
    command wrote the DEFAULT committed ledger while printing
    ``Resolved 1 file(s)`` and exiting 0. ``status`` and ``prune`` rejected
    the same spelling with exit 2, so the one lax surface was the only one
    that WRITES. A second ``--checksums`` in either spelling is left in the
    argument list and rejected by the subcommand as an unknown flag rather
    than silently losing to a precedence rule.

    Every subcommand — ``mark-resolved`` included since #1285 — rejects an
    unrecognized leading-``-`` token with exit 2 instead of treating it as a
    path. ``mark-resolved`` used to swallow ``--bogus``/``--apply``/a
    mistyped flag as a ``<rel-path>``, where the only signal was a
    ``Skipped (not tracked):`` line that reads as ordinary output (the
    resolver legitimately passes path lists wider than what the tracker has
    seen). An entry key is a repo-relative path, so a path that genuinely
    begins with ``-`` is not a case this ledger has or can have.

    Exit codes:
        0 — success (including "nothing to resolve/prune", still 0); for
            ``status``, additionally means every tracked file was hashed and
            agrees with the ledger
        1 — ``status``: the ledger is dirty and/or has malformed entries —
            the ``/ontology-rebuild`` + ``mark-resolved`` path.
            ``prune``: the sanity threshold refused the run
        2 — usage error
        3 — ``status``: the ledger could not be read (missing, unparseable,
            or not shaped like a checksums document). Deliberately distinct
            from 0 — "could not read" must never look like "clean"
        4 — ``status``: at least one tracked file has DRIFTED (its content
            matches neither stored hash) or was UNDETERMINABLE (tracked, but
            could not be hashed). Distinct from 1 because the remediation
            differs and 1's remediation applied here manufactures a false
            clean; distinct from 0 because a file that could not be measured
            is not a file that was measured and found fine (#1505)
    """
    if len(argv) < 2 or argv[1] not in ("mark-resolved", "prune", "status"):
        print(
            "usage: checksums_io.py status [--checksums[=]PATH] [--repo-root DIR] [--json]\n"
            "       checksums_io.py mark-resolved [--checksums[=]PATH] <rel-path> "
            "[<rel-path> ...]\n"
            "       checksums_io.py prune [--checksums[=]PATH] [--repo-root DIR] "
            "[--apply] [--dry-run] [--force]",
            file=sys.stderr,
        )
        return EXIT_USAGE

    subcommand = argv[1]
    rest = argv[2:]
    checksums_path = _default_checksums_path()
    for i, token in enumerate(rest):
        if token == "--checksums":
            if i + 1 >= len(rest):
                print("error: --checksums requires a PATH argument", file=sys.stderr)
                return EXIT_USAGE
            checksums_path = Path(rest[i + 1])
            rest = rest[:i] + rest[i + 2 :]
            break
        if token.startswith("--checksums="):
            value = token[len("--checksums=") :]
            if not value:
                print("error: --checksums= requires a PATH argument", file=sys.stderr)
                return EXIT_USAGE
            checksums_path = Path(value)
            rest = rest[:i] + rest[i + 1 :]
            break

    if subcommand == "status":
        return _status_cli(checksums_path, rest)

    if subcommand == "prune":
        return _prune_cli(checksums_path, rest)

    # `mark-resolved` is the WRITER, and until #1285 it was the only
    # subcommand that treated anything it did not recognize as a <rel-path>.
    # An unknown flag therefore selected the DEFAULT committed ledger and
    # wrote it at exit 0. Reject instead — same contract `_status_cli` and
    # `_prune_cli` have had since #1283.
    for token in rest:
        if token.startswith("-") and token != "-":
            print(
                f"error: unexpected argument {token!r} for mark-resolved. Only "
                "--checksums PATH / --checksums=PATH is recognized; every other "
                "argument must be a repo-relative path, and entry keys never begin "
                "with '-'.",
                file=sys.stderr,
            )
            return EXIT_USAGE

    if not rest:
        print("error: at least one <rel-path> is required", file=sys.stderr)
        return EXIT_USAGE

    data = read_checksums(checksums_path)
    now = datetime.now(timezone.utc).isoformat()
    resolved = mark_resolved(data, rest, now)
    write_checksums(checksums_path, data)

    skipped = [p for p in rest if p not in resolved]
    print(f"Resolved {len(resolved)} file(s) in {checksums_path}.")
    if skipped:
        print(f"Skipped (not tracked): {', '.join(skipped)}")
    return 0


def _status_cli(checksums_path: Path, rest: list[str]) -> int:
    """``status`` subcommand body. ``--checksums`` is already consumed by ``main``.

    Read-only. Prints the five per-state counts plus the offending paths, and
    returns an exit code that distinguishes the outcomes a caller acts on
    differently: clean (0), dirty/malformed (1), usage (2), unreadable (3),
    drifted/undeterminable (4).

    Every channel this CLI's callers consume has to move together, or the
    correction is invisible to whichever one they actually branch on:

    * the printed summary — a human reads it, and it now names the drifted
      and undeterminable counts and ends in an explicit VERDICT line stating
      whether the files were hashed at all;
    * the exit code — the ``/session-start`` 3a and ``/ontology-librarian``
      1a tables branch on it, and 4 keeps drift out of the branch whose
      remediation would hide it;
    * ``--json`` — gains ``drifted``, ``undeterminable`` and ``verified``
      alongside the existing ``clean``.

    Printing honest counts while still returning 0, or returning 4 while
    still printing "0 dirty", would each leave one of those callers exactly
    as misinformed as before (#1500, wave-31 bar clause 2).
    """
    as_json = False
    repo_root = repo_root_for(checksums_path)
    while rest:
        if rest[0] == "--json":
            as_json = True
            rest = rest[1:]
        elif rest[0] == "--repo-root":
            if len(rest) < 2:
                print("error: --repo-root requires a DIR argument", file=sys.stderr)
                return EXIT_USAGE
            repo_root = Path(rest[1]).resolve()
            rest = rest[2:]
        else:
            print(f"error: unexpected argument {rest[0]!r} for status", file=sys.stderr)
            return EXIT_USAGE

    try:
        status = read_status(checksums_path, repo_root)
    except ChecksumsUnreadable as exc:
        # NOT exit 0 with a zero count — see the module's no-silent-zeros contract.
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_UNREADABLE

    if as_json:
        json.dump(
            {
                "checksums": str(checksums_path),
                "repo_root": str(repo_root),
                "total": status.total,
                "dirty": list(status.dirty),
                "drifted": [{"path": rel, "reason": why} for rel, why in status.drifted],
                "malformed": [{"path": rel, "reason": why} for rel, why in status.malformed],
                "undeterminable": [
                    {"path": rel, "reason": why} for rel, why in status.undeterminable
                ],
                "verified": status.verified,
                "clean": status.clean,
            },
            sys.stdout,
            indent=2,
            ensure_ascii=False,
        )
        sys.stdout.write("\n")
    else:
        print(
            f"{checksums_path}: {status.total} tracked, {len(status.dirty)} dirty, "
            f"{len(status.drifted)} drifted, {len(status.malformed)} malformed, "
            f"{len(status.undeterminable)} undeterminable"
        )
        if status.dirty:
            print("dirty (last_tracked != last_resolved — edited since the last rebuild):")
            for rel in status.dirty:
                print(f"  - {rel}")
        if status.drifted:
            print("drifted (stored hashes agree with each other, NOT with the file — #1505):")
            for rel, why in status.drifted:
                print(f"  - {rel}: {why}")
        if status.malformed:
            print("malformed (unrecognized entry schema — NOT counted clean):")
            for rel, why in status.malformed:
                print(f"  - {rel}: {why}")
        if status.undeterminable:
            print("undeterminable (tracked, but could NOT be hashed — NOT counted clean):")
            for rel, why in status.undeterminable:
                print(f"  - {rel}: {why}")
        _print_status_verdict(status, repo_root)

    if not status.verified or status.drifted or status.undeterminable:
        return EXIT_DRIFTED
    if status.dirty or status.malformed:
        return EXIT_NEEDS_ATTENTION
    return EXIT_CLEAN


def _print_status_verdict(status: ChecksumsStatus, repo_root: Path) -> None:
    """The rendered channel's answer to "was this actually measured?".

    A count line alone cannot say the difference between "0 drifted because
    every file was hashed and matched" and "0 drifted because nothing was
    hashed". The VERDICT line says which, in words, every time — the human
    channel's equivalent of the exit code's 0-vs-4 split.
    """
    if status.clean:
        print(
            f"VERDICT: CLEAN - all {status.total} tracked file(s) were hashed "
            f"against {repo_root} and match their stored values."
        )
        return

    if not status.verified:
        print(
            "VERDICT: NOT VERIFIED - no repo root was supplied, so no file was hashed. "
            "This is not a clean reading; it is an absent one."
        )
        return

    print(
        f"VERDICT: NOT CLEAN - {len(status.dirty)} dirty, {len(status.drifted)} drifted, "
        f"{len(status.malformed)} malformed, {len(status.undeterminable)} undeterminable "
        f"(all {status.total} entries were checked against {repo_root})."
    )
    if status.drifted:
        print(
            "  Drifted entries are NOT a `mark-resolved` job: stamping "
            "last_resolved = last_tracked records agreement between two values that both "
            "already disagree with the file, which is a false clean one layer along. "
            "Reconcile the overlay against the changed files first "
            "(/ontology-rebuild step 1; the standing backlog is tracked by #1513)."
        )
    if status.undeterminable:
        print(
            "  Undeterminable entries were not measured at all - they are neither clean "
            "nor dirty. `prune` (preview-by-default) is the tool for entries whose path is "
            "genuinely gone; verify each candidate before applying it."
        )
        if is_linked_worktree_root(repo_root):
            print(
                f"  NOTE: {repo_root} is a linked worktree. The gitignored child-repo "
                "clones do not exist there, so their entries cannot be hashed from here. "
                "Re-run from the main checkout, or pass --repo-root <main-checkout>."
            )


# Refuse a prune that would remove more than this fraction of the tracked
# entries unless --force. A legitimate steady-state prune is near zero (the
# real checkout reports 0/277 once clean); a run against the wrong root
# reports 50-100%. The threshold turns "wrong --repo-root" and "run from a
# worktree" from a silent success into a non-zero exit naming the cause.
PRUNE_SANITY_FRACTION = 0.25


def _prune_cli(checksums_path: Path, rest: list[str]) -> int:
    """``prune`` subcommand body. ``--checksums`` is already consumed by ``main``.

    ``--repo-root`` defaults to the checksums file's grandparent
    (``<root>/ontology/checksums.json`` -> ``<root>``), so the common case
    needs no flags. Entry keys are relative to that root, which is exactly
    what ``ontology_tracker._relative_path`` writes.

    PREVIEW BY DEFAULT (#1137). A bare ``prune`` lists what it would remove
    and writes nothing; ``--apply`` is required to mutate the file. The
    documented safe-usage pattern (``/ontology-rebuild`` SKILL.md step 4) was
    already "preview, verify each candidate against ``origin/main``, then
    write" — the old write-by-default merely left that pattern unenforced, so
    an invocation from muscle memory or a copy-paste that dropped the flag
    mutated a version-controlled artifact on the strength of an on-disk
    existence test this module's own docstring flags as unreliable in a
    documented scenario.

    ``--dry-run`` is still accepted and is now a no-op spelling of the
    default: every previously-safe invocation stays safe and keeps working.
    ``--dry-run --apply`` together is a usage error rather than a silent
    precedence rule — an undocumented precedence in a destructive CLI is the
    same trap as the ordering rule that already bit ``--checksums``.

    The asymmetry with ``mark-resolved`` (which writes unconditionally, no
    dry-run) is deliberate, not an oversight: ``mark-resolved`` is ADDITIVE
    and idempotent — it stamps ``last_resolved``/``resolved_at`` on entries
    that are already present, and its worst misfire quiets a file that should
    have stayed dirty, recoverable by the next Edit re-stamping
    ``last_tracked``. ``prune`` DELETES entries, and its inputs (the on-disk
    existence of ~280 paths, half of them in gitignored child clones) depend
    on which branch each child repo is checked out at. Same module, different
    blast radius.

    Three guards stand between a mistyped invocation and a mass delete of a
    committed artifact. Each turns a silent exit-0 "success" into a refusal:

    1. ``--repo-root`` must be an existing directory. A typo previously
       resolved fine and reported every entry as an orphan.
    2. ``repo_root`` must not itself be a linked worktree. Worktrees are this
       org's preferred agent isolation, and the gitignored child-repo clones
       (~50% of entries) do not exist inside one — so the documented
       ``REPO_ROOT="$(git rev-parse --show-toplevel)"`` invocation, run in the
       default working style, proposed wiping half the file.
    3. The prune set must stay under ``PRUNE_SANITY_FRACTION`` of all entries.

    ``--force`` overrides 2 and 3 (never 1), and is orthogonal to ``--apply``
    — forcing past a guard still previews unless you also ask to write. The
    guards apply to the preview too: a preview that reports a 141-entry wipe
    as normal output is exactly how the mistake gets rubber-stamped.
    """
    repo_root = repo_root_for(checksums_path)
    apply_changes = False
    explicit_dry_run = False
    force = False
    while rest:
        if rest[0] == "--repo-root":
            if len(rest) < 2:
                print("error: --repo-root requires a DIR argument", file=sys.stderr)
                return EXIT_USAGE
            repo_root = Path(rest[1]).resolve()
            rest = rest[2:]
        elif rest[0] == "--apply":
            apply_changes = True
            rest = rest[1:]
        elif rest[0] == "--dry-run":
            explicit_dry_run = True
            rest = rest[1:]
        elif rest[0] == "--force":
            force = True
            rest = rest[1:]
        else:
            print(f"error: unexpected argument {rest[0]!r} for prune", file=sys.stderr)
            return EXIT_USAGE

    # Contradictory intent — refuse rather than pick a silent winner (#1137).
    if apply_changes and explicit_dry_run:
        print(
            "error: --dry-run and --apply are contradictory. --dry-run is now the "
            "default (preview); drop it to apply.",
            file=sys.stderr,
        )
        return EXIT_USAGE

    # Guard 1 — a nonexistent root makes EVERY entry look orphaned.
    if not repo_root.is_dir():
        print(
            f"error: --repo-root {repo_root} is not an existing directory; refusing to "
            "prune (every entry would read as orphaned).",
            file=sys.stderr,
        )
        return EXIT_USAGE

    # Guard 2 — inside a linked worktree the gitignored child-repo clones are
    # structurally absent, so their entries all read as orphaned.
    if not force and is_linked_worktree_root(repo_root):
        print(
            f"error: --repo-root {repo_root} is a linked worktree. The gitignored "
            "child-repo clones do not exist there, so their entries would all read as "
            "orphaned. Re-run from the main checkout, or pass --force if you are certain.",
            file=sys.stderr,
        )
        return EXIT_USAGE

    data = read_checksums(checksums_path)
    total = len(data.get("files", {}))
    removed = prune_missing(data, repo_root)

    # Guard 3 — a plausible steady-state prune is a handful of entries.
    if not force and total and len(removed) > total * PRUNE_SANITY_FRACTION:
        pct = 100.0 * len(removed) / total
        print(
            f"error: prune would remove {len(removed)} of {total} entries ({pct:.0f}%), "
            f"over the {PRUNE_SANITY_FRACTION:.0%} sanity threshold. This almost always "
            f"means --repo-root is wrong (resolved to {repo_root}) rather than that the "
            "file is that stale. Re-check the root, or pass --force if it is genuinely "
            "correct.",
            file=sys.stderr,
        )
        return EXIT_NEEDS_ATTENTION

    if removed and apply_changes:
        write_checksums(checksums_path, data)

    verb = "Pruned" if apply_changes else "Would prune"
    print(
        f"{verb} {len(removed)} orphan entr{'y' if len(removed) == 1 else 'ies'} "
        f"in {checksums_path} (repo root {repo_root})."
    )
    for rel in removed:
        print(f"  - {rel}")
    if removed and not apply_changes:
        print("Preview only — nothing written. Verify each candidate is genuinely deleted")
        print("(git -C <repo> cat-file -e origin/main:<path>), then re-run with --apply.")
    return EXIT_CLEAN


if __name__ == "__main__":
    sys.exit(main(sys.argv))
