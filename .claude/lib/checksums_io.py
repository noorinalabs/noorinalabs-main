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
"""

from __future__ import annotations

import copy
import json
import sys
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


def read_checksums(path: Path) -> dict[str, Any]:
    """Read and parse ``checksums.json``, defaulting to an empty structure.

    Returns a fresh ``{"version": 1, "files": {}}`` if the file is missing or
    is not valid JSON — matching the tracker hook's historical fail-open
    behavior (a PostToolUse hook must never raise).
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return copy.deepcopy(_EMPTY)
    if not isinstance(data, dict):
        return copy.deepcopy(_EMPTY)
    return data


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
    pruned. That is why the ``prune`` CLI is opt-in with a ``--dry-run``
    rather than something a lifecycle skill runs unattended: confirm the
    candidate list is genuinely-deleted (``git cat-file -e origin/main:<path>``)
    before writing. Re-tracking is cheap if a prune does go wrong — the next
    Edit/Write of the file re-creates the entry — but it re-enters with an
    empty ``last_resolved`` and so reports dirty once.
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

    Usage:
        python3 .claude/lib/checksums_io.py mark-resolved <path> [<path> ...]
        python3 .claude/lib/checksums_io.py mark-resolved --checksums <file> <path> ...
        python3 .claude/lib/checksums_io.py prune
            [--checksums <file>] [--repo-root <dir>] [--dry-run] [--force]

    ``--checksums`` may appear at any position. This is hand-rolled parsing
    rather than argparse, and an earlier revision required it FIRST — so
    ``prune --dry-run --checksums X`` died with "unexpected argument
    '--checksums'". It failed safe, but an undocumented ordering rule in a
    destructive CLI is a trap, so the flag is now extracted positionally-
    agnostically instead.

    Exit codes:
        0 — success (including "nothing to resolve/prune", still 0)
        2 — usage error
    """
    if len(argv) < 2 or argv[1] not in ("mark-resolved", "prune"):
        print(
            "usage: checksums_io.py mark-resolved [--checksums PATH] <rel-path> [<rel-path> ...]\n"
            "       checksums_io.py prune [--checksums PATH] [--repo-root DIR] "
            "[--dry-run] [--force]",
            file=sys.stderr,
        )
        return 2

    subcommand = argv[1]
    rest = argv[2:]
    checksums_path = _default_checksums_path()
    if "--checksums" in rest:
        i = rest.index("--checksums")
        if i + 1 >= len(rest):
            print("error: --checksums requires a PATH argument", file=sys.stderr)
            return 2
        checksums_path = Path(rest[i + 1])
        rest = rest[:i] + rest[i + 2 :]

    if subcommand == "prune":
        return _prune_cli(checksums_path, rest)

    if not rest:
        print("error: at least one <rel-path> is required", file=sys.stderr)
        return 2

    data = read_checksums(checksums_path)
    now = datetime.now(timezone.utc).isoformat()
    resolved = mark_resolved(data, rest, now)
    write_checksums(checksums_path, data)

    skipped = [p for p in rest if p not in resolved]
    print(f"Resolved {len(resolved)} file(s) in {checksums_path}.")
    if skipped:
        print(f"Skipped (not tracked): {', '.join(skipped)}")
    return 0


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

    ``--force`` overrides 2 and 3 (never 1). The guards apply to ``--dry-run``
    too: a preview that reports a 141-entry wipe as normal output is exactly
    how the mistake gets rubber-stamped.
    """
    repo_root = checksums_path.resolve().parent.parent
    dry_run = False
    force = False
    while rest:
        if rest[0] == "--repo-root":
            if len(rest) < 2:
                print("error: --repo-root requires a DIR argument", file=sys.stderr)
                return 2
            repo_root = Path(rest[1]).resolve()
            rest = rest[2:]
        elif rest[0] == "--dry-run":
            dry_run = True
            rest = rest[1:]
        elif rest[0] == "--force":
            force = True
            rest = rest[1:]
        else:
            print(f"error: unexpected argument {rest[0]!r} for prune", file=sys.stderr)
            return 2

    # Guard 1 — a nonexistent root makes EVERY entry look orphaned.
    if not repo_root.is_dir():
        print(
            f"error: --repo-root {repo_root} is not an existing directory; refusing to "
            "prune (every entry would read as orphaned).",
            file=sys.stderr,
        )
        return 2

    # Guard 2 — inside a linked worktree the gitignored child-repo clones are
    # structurally absent, so their entries all read as orphaned.
    if not force and is_linked_worktree_root(repo_root):
        print(
            f"error: --repo-root {repo_root} is a linked worktree. The gitignored "
            "child-repo clones do not exist there, so their entries would all read as "
            "orphaned. Re-run from the main checkout, or pass --force if you are certain.",
            file=sys.stderr,
        )
        return 2

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
        return 1

    if removed and not dry_run:
        write_checksums(checksums_path, data)

    verb = "Would prune" if dry_run else "Pruned"
    print(
        f"{verb} {len(removed)} orphan entr{'y' if len(removed) == 1 else 'ies'} "
        f"in {checksums_path} (repo root {repo_root})."
    )
    for rel in removed:
        print(f"  - {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
