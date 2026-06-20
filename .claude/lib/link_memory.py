#!/usr/bin/env python3
"""Link the cwd-derived Claude Code memory path to an in-repo, version-controlled
``.claude/memory/`` directory.

## Why

Claude Code stores project memory at ``~/.claude/projects/<cwd-with-slashes-as-
dashes>/memory/``. That location has three problems this script fixes:

1. **User-space, not version-controlled** — the curated memory corpus (MEMORY.md
   + topic files) lived outside any repo, so it was never shared across machines
   and never reviewable in a PR.
2. **cwd-keyed → fragments** — because the path derives from cwd, every git
   worktree and every child-repo cwd resolves to a *different, empty* memory
   dir. A worktree-isolated subagent therefore cannot see or curate the real
   corpus (the concrete blocker that made noorinalabs-main#732 un-spawnable in a
   worktree).
3. **No enforcement surface** — leanness rules (#725) cannot run against a corpus
   that isn't in the tree.

The Claude Code path is fixed, but it is an ordinary directory, so we make it a
**symlink** to ``<repo>/.claude/memory/``. The harness then reads/writes the
in-repo, version-controlled corpus transparently.

## Scoping (matches the org's CLAUDE.md hierarchy)

- **Plain repo** (noorinalabs-main, or a child clone like noorinalabs-deploy):
  the canonical path for that repo's cwd → ``<toplevel>/.claude/memory``. This is
  how each repo gets its *own* version-controlled memory ("all the individual
  ones").
- **Linked worktree**: the worktree's canonical path → the **main working
  tree's** ``.claude/memory`` (resolved via ``--git-common-dir``), so a
  worktree subagent shares the parent repo's org memory rather than a private
  empty dir.

## Usage

    python3 .claude/lib/link_memory.py [--check] [--quiet]

Idempotent — safe to run every session (wire into ``/session-start``). With no
flags it ensures the link exists, backing up any pre-existing real directory to
``memory.bak.<UTC-timestamp>`` first (never destructive). ``--check`` reports
status and exits non-zero if the link is missing/wrong without mutating
anything. Exit codes: 0 = linked (or, with --check, already correct),
1 = error / (with --check) not linked.
"""

from __future__ import annotations

import argparse
import datetime
import shutil
import subprocess
import sys
from pathlib import Path


def _git(args: list[str]) -> str:
    """Run a git command, returning stripped stdout ('' on failure)."""
    res = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
    return res.stdout.strip()


def canonical_memory_path(cwd_root: Path, home: Path | None = None) -> Path:
    """The Claude Code memory dir for a session whose cwd is ``cwd_root``.

    Mirrors the harness rule: absolute cwd with every ``/`` replaced by ``-``,
    nested under ``~/.claude/projects/<dashed>/memory``.
    """
    home = home or Path.home()
    dashed = str(cwd_root).replace("/", "-")
    return home / ".claude" / "projects" / dashed / "memory"


def resolve_target(home: Path | None = None) -> tuple[Path, Path]:
    """Return ``(canonical_path, in_repo_target)`` for the current git context.

    Raises ``RuntimeError`` if not in a git work tree or the target dir is absent.
    """
    toplevel = _git(["rev-parse", "--show-toplevel"])
    if not toplevel:
        raise RuntimeError("not inside a git work tree")
    toplevel_p = Path(toplevel)

    git_dir = _git(["rev-parse", "--absolute-git-dir"])
    common_dir = _git(["rev-parse", "--path-format=absolute", "--git-common-dir"])
    is_worktree = (
        bool(git_dir and common_dir) and Path(git_dir).resolve() != Path(common_dir).resolve()
    )

    # Linked worktree → org memory lives in the MAIN working tree (parent of the
    # shared .git common dir). Plain repo → this repo's own .claude/memory.
    main_root = Path(common_dir).parent if is_worktree else toplevel_p
    target = main_root / ".claude" / "memory"
    if not target.is_dir():
        raise RuntimeError(
            f"in-repo memory dir does not exist: {target} "
            "(create .claude/memory/ and commit it before linking)"
        )
    canonical = canonical_memory_path(toplevel_p, home=home)
    return canonical, target


def link_memory(check: bool = False, quiet: bool = False, home: Path | None = None) -> int:
    def say(msg: str) -> None:
        if not quiet:
            print(msg)

    try:
        canonical, target = resolve_target(home=home)
    except RuntimeError as exc:
        say(f"ERROR: {exc}")
        return 1

    already_linked = canonical.is_symlink() and canonical.resolve() == target.resolve()

    if check:
        if already_linked:
            say(f"OK: {canonical} -> {target}")
            return 0
        say(f"NOT LINKED: {canonical} (expected -> {target})")
        return 1

    if already_linked:
        say(f"OK: {canonical} -> {target} (already linked)")
        return 0

    canonical.parent.mkdir(parents=True, exist_ok=True)

    # Replace a wrong/stale symlink, or back up a real pre-existing dir.
    if canonical.is_symlink():
        canonical.unlink()
    elif canonical.exists():
        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = canonical.with_name(f"memory.bak.{ts}")
        shutil.move(str(canonical), str(backup))
        say(f"backed up existing dir -> {backup}")

    canonical.symlink_to(target)
    say(f"linked: {canonical} -> {target}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="report link status without mutating; exit 1 if not linked",
    )
    parser.add_argument("--quiet", action="store_true", help="suppress output")
    args = parser.parse_args(argv)
    return link_memory(check=args.check, quiet=args.quiet)


if __name__ == "__main__":
    sys.exit(main())
