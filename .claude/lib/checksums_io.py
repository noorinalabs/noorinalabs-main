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
"""

from __future__ import annotations

import copy
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


@dataclass(frozen=True)
class ChecksumsStatus:
    """Reader-facing summary of a checksums ledger.

    ``dirty`` and ``malformed`` are sorted for stable output. ``malformed``
    carries ``(path, reason)`` pairs so the report says *why* an entry could
    not be classified rather than just how many there were.
    """

    total: int
    dirty: tuple[str, ...]
    malformed: tuple[tuple[str, str], ...]

    @property
    def clean(self) -> bool:
        """True only when nothing is dirty AND nothing is malformed.

        A malformed entry blocks "clean" deliberately: an entry the reader
        cannot classify is unknown state, and reporting unknown as fine is the
        bug this module exists to prevent.
        """
        return not self.dirty and not self.malformed


def compute_status(data: dict[str, Any]) -> ChecksumsStatus:
    """Summarize an already-parsed ledger. Raises on an unrecognized shape.

    ``data["files"]`` must be present and a mapping. A ledger without it is
    ``ChecksumsUnreadable`` rather than "0 tracked, 0 dirty": the legacy
    flat-map fallback some ad-hoc readers used (``data.get("files", data)``)
    turns a shape mismatch into a plausible zero, which is the #1142 failure.
    Every ledger this module writes has a ``files`` mapping, and ``_EMPTY``
    seeds one, so the strict reading costs nothing real.
    """
    files = data.get("files")
    if not isinstance(files, dict):
        kind = "missing" if files is None else f"a {type(files).__name__}"
        raise ChecksumsUnreadable(f"checksums document has no 'files' object ('files' is {kind})")
    dirty: list[str] = []
    malformed: list[tuple[str, str]] = []
    for rel in sorted(files):
        state, detail = classify_entry(files[rel])
        if state == ENTRY_DIRTY:
            dirty.append(rel)
        elif state == ENTRY_MALFORMED:
            malformed.append((rel, detail))
    return ChecksumsStatus(total=len(files), dirty=tuple(dirty), malformed=tuple(malformed))


def read_status(path: Path) -> ChecksumsStatus:
    """Strict read + summarize. The one call a reader needs (#1142).

    Raises ``ChecksumsUnreadable`` if the file is missing, unparseable, or not
    shaped like a checksums ledger.
    """
    return compute_status(read_checksums_strict(path))


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
        python3 .claude/lib/checksums_io.py status [--checksums <file>] [--json]
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

    Exit codes:
        0 — success (including "nothing to resolve/prune", still 0); for
            ``status``, additionally means the ledger is clean
        1 — ``status``: the ledger is dirty and/or has malformed entries.
            ``prune``: the sanity threshold refused the run
        2 — usage error
        3 — ``status``: the ledger could not be read (missing, unparseable,
            or not shaped like a checksums document). Deliberately distinct
            from 0 — "could not read" must never look like "clean"
    """
    if len(argv) < 2 or argv[1] not in ("mark-resolved", "prune", "status"):
        print(
            "usage: checksums_io.py status [--checksums PATH] [--json]\n"
            "       checksums_io.py mark-resolved [--checksums PATH] <rel-path> [<rel-path> ...]\n"
            "       checksums_io.py prune [--checksums PATH] [--repo-root DIR] "
            "[--apply] [--dry-run] [--force]",
            file=sys.stderr,
        )
        return EXIT_USAGE

    subcommand = argv[1]
    rest = argv[2:]
    checksums_path = _default_checksums_path()
    if "--checksums" in rest:
        i = rest.index("--checksums")
        if i + 1 >= len(rest):
            print("error: --checksums requires a PATH argument", file=sys.stderr)
            return EXIT_USAGE
        checksums_path = Path(rest[i + 1])
        rest = rest[:i] + rest[i + 2 :]

    if subcommand == "status":
        return _status_cli(checksums_path, rest)

    if subcommand == "prune":
        return _prune_cli(checksums_path, rest)

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

    Read-only. Prints ``total`` / ``dirty`` / ``malformed`` counts plus the
    offending paths, and returns an exit code that distinguishes the three
    outcomes a caller actually cares about: clean (0), needs attention (1),
    unreadable (3). The 0/3 split is the point — a reader that answers
    "0 dirty" for a file it failed to parse is the #1142 bug.

    ``--json`` emits the same summary as a machine-readable object, so a hook
    or a future wrap-time gate (#1086) consumes this instead of re-parsing
    prose or, worse, re-deriving the predicate from the raw JSON.
    """
    as_json = False
    while rest:
        if rest[0] == "--json":
            as_json = True
            rest = rest[1:]
        else:
            print(f"error: unexpected argument {rest[0]!r} for status", file=sys.stderr)
            return EXIT_USAGE

    try:
        status = read_status(checksums_path)
    except ChecksumsUnreadable as exc:
        # NOT exit 0 with a zero count — see the module's no-silent-zeros contract.
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_UNREADABLE

    if as_json:
        json.dump(
            {
                "checksums": str(checksums_path),
                "total": status.total,
                "dirty": list(status.dirty),
                "malformed": [{"path": rel, "reason": why} for rel, why in status.malformed],
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
            f"{len(status.malformed)} malformed"
        )
        if status.dirty:
            print("dirty (last_tracked != last_resolved):")
            for rel in status.dirty:
                print(f"  - {rel}")
        if status.malformed:
            print("malformed (unrecognized entry schema — NOT counted clean):")
            for rel, why in status.malformed:
                print(f"  - {rel}: {why}")

    return EXIT_CLEAN if status.clean else EXIT_NEEDS_ATTENTION


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
    repo_root = checksums_path.resolve().parent.parent
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
