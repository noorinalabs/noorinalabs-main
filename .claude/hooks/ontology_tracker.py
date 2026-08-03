#!/usr/bin/env python3
"""PostToolUse hook: Ontology change tracker.

Input: PostToolUse JSON on Edit / Write (the matchers actually wired in
``.claude/settings.json``). Computes SHA256 of the modified file and
updates ``ontology/checksums.json`` with the new hash in
``last_tracked``. When ``last_tracked != last_resolved``, the file is
"dirty" and needs ontology resolution.

Handles files across all child repos under the main repo root.

Path filtering (issue #143):
  Some edits target paths that are out of scope for the ontology —
  recording them inflates the dirty-file count without representing real
  drift. The hook therefore skips:

    * Substring SKIP_PATTERNS (e.g. ``__pycache__/``, ``.git/``) — the fast
      path for the handful of well-known noise classes.
    * A file gitignored BY ITS OWN REPO (#1039) — the generalized backstop
      behind SKIP_PATTERNS. See "Owning-repo check-ignore (#1039)" below for
      why this must resolve each file's nearest ``.git`` ancestor rather than
      running ``git check-ignore`` from ``REPO_ROOT``.
    * Paths beginning with ``/tmp/`` — ephemeral scratch (e.g. issue-body
      staging files).
    * Paths under any ``.worktrees`` directory — ephemeral worktree copies.
      Two conventions are both gitignored (#523) and both skipped: the
      historical ``.claude/worktrees/`` path and the top-level
      ``.worktrees/`` path used by current wave/agent isolation. A worktree
      path enters this hook when an Edit/Write happens inside a worktree and
      the hook (anchored on the orchestrator cwd) records the worktree-
      relative path — e.g. ``.worktrees/deploy-0348-aisha/...`` or a
      child-repo file seen through a sibling worktree. These never resolve
      (``last_resolved: ""``) and once aborted a ``git merge --ff-only``
      during W11 close-out (#525). The canonical entry for the underlying
      file is updated whenever the file is next Edit/Written directly on the
      main checkout (this is a PostToolUse hook on tool calls, NOT a git
      post-merge hook, so a squash-merge of a worktree-only PR does not by
      itself update the tracker — the next direct Edit on main does).
      Skipping worktree paths is still the right call: it prevents
      accumulation of stale paths in ``checksums.json`` after worktrees are
      removed, and the slight latency in the canonical entry's
      ``last_tracked`` is acceptable noise-vs-signal trade.
    * Files inside a LINKED WORKTREE parked anywhere else — the structural
      generalization of the rule above, added after four ``da-wt-490/*``
      orphans survived it in wave-28 (a worktree at the repo root, so no
      ``.worktrees`` component to match). ``_is_linked_worktree`` reads the
      owning root's ``.git`` pointer file instead of guessing from the
      directory name. Entries the name-based filter already leaked are
      cleaned up by ``checksums_io.prune_missing`` / the ``prune`` CLI.
    * Paths outside the repo tree — anything not under ``REPO_ROOT`` after
      resolution (e.g. user auto-memory files at
      ``/home/.../.claude/projects/.../memory/*.md``). The ontology only
      describes this repo; out-of-tree files cannot be its source of
      truth. (Note: on macOS, ``/tmp`` is a symlink to ``/private/tmp``;
      the SKIP_PREFIXES check uses the resolved path so the filter still
      catches it.)

Owning-repo check-ignore (#1039):
  ``SKIP_PATTERNS`` is a hand-maintained substring denylist. It has leaked
  twice for the same class of file — gitignored, machine-local,
  frequently-rewritten artifacts (``.claude/annunaki/errors.jsonl``, then
  ``.claude/memory/session_handoff.md``, #1038) — each leak manufacturing
  permanent phantom drift in ``checksums.json`` until someone notices and
  hand-extends the list.

  The naive generalization — run ``git check-ignore`` from ``REPO_ROOT`` —
  is WRONG: this parent repo ``.gitignore``s every child repo wholesale, so
  that would report every child-repo file as ignored (147 of 284 tracked
  entries, 52%, including real committed source like
  ``noorinalabs-deploy/.github/workflows/deploy-prod.yml`` and every child
  ontology file). That would silently blind the tracker to over half the
  semantic overlay while ``/session-start`` kept reporting "0 dirty" —
  strictly worse than the nuisance it fixes, because the gate would look
  healthier while going blind.

  The correct generalization resolves each file's OWNING repo — walk up to
  the nearest ``.git`` ancestor of the file, not ``REPO_ROOT`` — and runs
  ``git check-ignore`` there, on the path relative to THAT repo. A
  child-repo file's gitignored-ness is a question for its own repo, never
  the parent's ``.gitignore``.

  This check-ignore call is a BACKSTOP behind ``SKIP_PATTERNS``, not a
  replacement: the substring list stays as the fast, no-subprocess path for
  the handful of well-known noise classes (``checksums.json`` self-skip,
  the generated structural layer, worktree paths — these are POLICY
  decisions, not gitignore facts, so check-ignore would not catch them even
  if it ran). ``_is_git_ignored`` only runs for paths ``SKIP_PATTERNS``
  didn't already catch.

  Fails OPEN on any error — no ``.git`` ancestor found, the file resolves
  outside its own repo, or the ``git check-ignore`` subprocess itself fails
  or times out: the file is tracked (NOT skipped). Under-tracking is a
  *silent* loss of drift detection (the gate looks green while blind);
  over-tracking is merely noise. The asymmetry is one-sided and is encoded
  deliberately here rather than left to whatever ``subprocess`` happens to
  raise.

  ``_GIT_CHECK_IGNORE_CACHE`` memoizes the per-(repo, relative-path) answer
  for the process's lifetime — a PostToolUse hook is a short-lived
  subprocess invoked once per Edit/Write, so this mainly benefits repeated
  calls within a single test run or a future batch invocation, not
  cross-invocation caching (there is no daemon to cache across).

  ``_DIR_CHECK_IGNORE_CACHE`` (#1122) additionally memoizes the *containing
  directory's* own check-ignore verdict, per (repo, relative-directory), same
  process lifetime. Per gitignore(5) — "It is not possible to re-include a
  file if a parent directory of that file is excluded" — a directory that
  ``git check-ignore`` reports as ignored makes EVERY file beneath it ignored
  too, no exceptions possible. So once a directory resolves to ignored, any
  later file under it is a cache hit with zero subprocess calls: real
  savings within a burst of edits/tests touching the same generated or
  vendored subtree (e.g. a child repo's own ``.venv/``/``dist/``/``coverage/``
  that ``SKIP_PATTERNS`` doesn't already substring-catch). A directory
  verdict of NOT-ignored is not similarly reusable — it says nothing about a
  specific file, since a filename pattern (``*.secret``) can still exclude
  one file inside an otherwise-untouched directory — so that case still
  falls through to a per-file check, same subprocess cost as before this
  cache existed.

  The directory verdict is resolved for free alongside the file's own
  verdict: ``git check-ignore`` (without ``-q``) accepts more than one
  pathspec and echoes back on stdout exactly which of the supplied
  pathspecs matched, so the FIRST file seen in a directory pays one
  subprocess call that answers "is this file ignored" AND "is its directory
  ignored" simultaneously — no additional subprocess versus the pre-#1122
  single-file check.

  The directory pathspec passed to ``git check-ignore`` is the BARE relative
  directory name, with NO trailing slash (main#1263 review finding, fixed
  before merge). A trailing slash turns the pathspec into a literal STRING
  that a contents-only pattern like ``data/raw/*`` matches directly (git
  echoes back the exact string ``"data/raw/"`` as a match), which is a
  different fact from the directory ITSELF being excluded — the bare
  ``"data/raw"`` does not match that same pattern. Using the slash version
  would cache a false "directory ignored" and silently mis-skip any file a
  ``!`` rule re-includes inside it (e.g. the ``dir/*`` + ``!dir/**/.gitkeep``
  idiom used by ``noorinalabs-isnad-ingest-platform``) — under-tracking,
  the one direction this function must never risk. The bare name still
  correctly answers "ignored" for a genuinely directory-excluding pattern
  (``build/`` matches ``"build"`` too) and for a NESTED directory swept up
  by a contents-only parent pattern (gitignore(5)'s no-re-include-under-an-
  excluded-parent rule then really does apply to everything beneath it), so
  the cache short-circuit stays sound in both directions — see
  ``GitCheckIgnoreDirectoryCacheTests`` in the test module for the exact
  fixtures.

  Invalidation: none needed — both caches are
  module-level dicts scoped to this one short-lived process (a fresh
  Edit/Write hook invocation starts with empty caches), and the on-disk
  ``.gitignore`` rules cannot change mid-invocation, so nothing can go stale
  within the cache's own lifetime.

Input Language:
  Fires on:      PostToolUse Edit, Write
  Matches:       Edit/Write whose `file_path` is non-empty AND resides inside
                 REPO_ROOT AND does NOT trip _should_skip (worktree-copy,
                 __pycache__, node_modules, /tmp/, etc.)
  Does NOT match: any other tool, missing file_path, paths under skip-
                  patterns, out-of-repo paths
  Flag pass-through: stdin JSON is forwarded verbatim to `check()` by the
                     PostToolUse dispatcher (`post_dispatcher.py`)

Exit codes:
  0 — always (advisory hook, never blocks)
"""

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CHECKSUMS_FILE = REPO_ROOT / "ontology" / "checksums.json"

# Memoizes (git_root, repo_relative_path) -> ignored? for the life of this
# process. See "Owning-repo check-ignore (#1039)" in the module docstring.
_GIT_CHECK_IGNORE_CACHE: dict[tuple[str, str], bool] = {}

# Memoizes (git_root, repo_relative_directory) -> ignored? for the life of
# this process (#1122). See "Owning-repo check-ignore (#1039)" in the module
# docstring for why a directory-ignored verdict is authoritative for every
# file beneath it, and why a not-ignored verdict is NOT similarly reusable.
_DIR_CHECK_IGNORE_CACHE: dict[tuple[str, str], bool] = {}

# Shared read/write helpers (#1042): both this hook and the /ontology-rebuild
# resolver's `mark-resolved` CLI go through checksums_io so neither has to
# remember the ensure_ascii=False + atomic-replace serialization convention —
# see .claude/lib/checksums_io.py's module docstring for the full rationale.
_LIB = Path(__file__).resolve().parent.parent / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))
import checksums_io  # noqa: E402

# Substring patterns: skip if any appears anywhere in the file path.
SKIP_PATTERNS = [
    "ontology/checksums.json",  # Don't track ourselves
    "ontology/structural/",  # GENERATED structural layer — see note below (#857)
    ".claude/annunaki/errors.jsonl",
    # Gitignored, machine-local, rewritten by the Stop hook after ~every
    # response — same class as annunaki/errors.jsonl. Tracking it dirtied the
    # COMMITTED checksums.json every session, so /session-start reported
    # phantom drift forever (#1038).
    ".claude/memory/session_handoff.md",
    "__pycache__/",
    ".pyc",
    "node_modules/",
    ".git/",
    ".DS_Store",
    ".claude/worktrees/",  # Ephemeral worktree copies — see module docstring
]

# Tracker/resolver scope = the hand-curated SEMANTIC OVERLAY only (#857, #820/C×T2).
#   The change-tracker hook + `/ontology-rebuild` resolver exist to keep
#   *hand-maintained* ontology files in sync on every edit. As of #857 the
#   **structural** layer at ``ontology/structural/`` is GENERATED by an owned
#   generator (#855), not hand-resolved — it is always-current-by-regeneration.
#   Checksum dirty-tracking it would be meaningless churn (the generator rewrites
#   it wholesale), and ``/ontology-rebuild`` has nothing to resolve there. So
#   ``ontology/structural/`` is skipped here, exactly like ``checksums.json``
#   skips itself. The semantic overlay (``ontology/domain.yaml``,
#   ``ontology/services.yaml``, ``ontology/conventions.md``,
#   ``ontology/repos/*.yaml``, and other hand-edited ``*.md``) IS still tracked.

# Path prefixes: skip if the resolved file path starts with any of these.
SKIP_PREFIXES = ("/tmp/",)

# Directory names that mark a worktree-isolation tree. Any path with one of
# these as a path COMPONENT is an ephemeral worktree copy and must not be
# tracked into the parent checksums (#523 gitignored both; #525). Segment
# matching (not substring) so a legitimate file like ``notes.worktrees.md``
# is not skipped, while ``.worktrees/deploy-0348/x`` and
# ``.claude/worktrees/foo/x`` both are.
WORKTREE_DIR_NAMES = frozenset({".worktrees", "worktrees"})


def _is_worktree_path(file_path: str) -> bool:
    """True if any path component marks a worktree-isolation tree.

    Checks the raw path components (both the as-given and, when it differs,
    the resolved form) so that a relative worktree path recorded under the
    orchestrator cwd (``.worktrees/...``) is caught even before resolution.
    The ``worktrees`` bare name is only treated as a marker when its parent
    component is ``.claude`` — i.e. the historical ``.claude/worktrees/``
    convention — to avoid skipping an unrelated dir merely named
    ``worktrees``.
    """
    parts = Path(file_path).parts
    for i, part in enumerate(parts):
        if part == ".worktrees":
            return True
        if part == "worktrees" and i > 0 and parts[i - 1] == ".claude":
            return True
    return False


def _is_linked_worktree(resolved_path: Path) -> bool:
    """True if ``resolved_path``'s owning git root is a LINKED WORKTREE.

    The structural generalization of ``_is_worktree_path`` (#523/#525), which
    matches on directory NAME (``.worktrees/``, ``.claude/worktrees/``). A
    worktree parked anywhere else slips straight through it — the wave-28
    ``da-wt-490/`` tree at the repo root did exactly that, landing four
    entries keyed to a directory that ceased to exist when the worktree was
    removed. Those entries can never resolve (there is no file to re-hash) and
    are not ``last_tracked == last_resolved``, so they report dirty forever.

    Detection is by git's own layout, not by naming — see
    ``checksums_io.is_linked_worktree_root`` for the discrimination rule and
    why a ``/worktrees/`` substring test on the pointer is NOT sufficient.
    Subprocess-free.

    Fails OPEN (returns False -> file is tracked) on every error: no ``.git``
    ancestor, an unreadable or unrecognized ``.git`` file, a pointer whose
    target is missing its admin files. Same asymmetry as ``_is_git_ignored`` —
    under-tracking is a silent loss of drift detection, over-tracking is
    merely noise.
    """
    git_root = _find_git_root(resolved_path)
    if git_root is None:
        return False
    return checksums_io.is_linked_worktree_root(git_root)


def _find_git_root(path: Path) -> Path | None:
    """Walk up from ``path`` to find the nearest ancestor with a ``.git`` entry.

    ``path`` is treated as a file whose *parent* directory is the starting
    point for the walk (a file is never itself a git root). Returns ``None``
    when no ``.git`` ancestor exists — e.g. the path is not inside any git
    working tree — which callers must treat as "cannot determine" and fail
    open (see ``_is_git_ignored``).
    """
    start = path.parent if not path.is_dir() else path
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _hermetic_git_env() -> dict[str, str]:
    """A copy of the process environment with any ``GIT_*`` vars stripped.

    git exports ``GIT_DIR``/``GIT_WORK_TREE``/``GIT_INDEX_FILE`` (and
    friends) into the subprocesses it spawns — including the pre-push
    ``pytest`` hook that runs this very module's test suite (main#719, see
    ``.claude/lib/tests/conftest.py``). A ``git check-ignore`` invoked with
    an inherited ``GIT_DIR`` targets THAT repo instead of the ``cwd`` we
    pass, silently ignoring the owning-repo resolution this function exists
    to do. Stripping ``GIT_*`` here makes every ``check-ignore`` call
    hermetic regardless of what process tree the hook itself was invoked
    from — a real correctness concern for the hook, not merely a test
    artifact, since a PostToolUse hook has no control over its parent's
    environment.
    """
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def _run_check_ignore(git_root: Path, pathspecs: list[str]) -> set[str]:
    """Run ``git check-ignore`` for one or more pathspecs against ``git_root``.

    Returns the subset of ``pathspecs`` that ARE ignored, as the exact
    strings passed in: git echoes back whichever supplied pathspec matched,
    one per line, and ``core.quotePath=false`` is pinned on the invocation
    so that echo is the caller's ORIGINAL string rather than a C-quoted
    rendering of it. That pin is load-bearing, not cosmetic (main#1265):
    under git's default ``core.quotePath=true`` any pathspec containing a
    non-ASCII byte comes back quoted and escaped (``سند.md`` echoes as
    ``"\\330\\263\\331\\206\\330\\257.md"``), which equals nothing the
    caller passed in, so set-membership below reports a genuinely-ignored
    path as NOT ignored. The pre-#1122 code read only ``-q``'s exit status
    and was encoding-independent by construction; matching on echoed text
    is what introduced the exposure, so the pin restores the property that
    change gave up. Do not remove it without replacing the matching scheme.

    ``encoding="utf-8", errors="replace"`` rather than ``text=True`` for the
    same reason: with the pin in place raw UTF-8 bytes now reach the decoder,
    and ``text=True`` would decode with the locale encoding under
    ``errors='strict'`` — so a ``LC_ALL=C`` runner would raise
    ``UnicodeDecodeError``, which is NOT in the ``except`` clause below and
    would escape ``check()``, breaking this hook's "exit 0 — always"
    contract. ``errors="replace"`` makes that unraisable.

    Deliberately omits ``-q`` (which would suppress that stdout) so a single
    call can answer more than one question at once (#1122) — the caller
    distinguishes "ignored" from "not ignored" by set-membership instead of
    by exit code alone.

    Fails OPEN — returns an empty set (nothing reported ignored) — on any
    subprocess error or timeout, or on any exit code other than 0 (at least
    one match) / 1 (no match, e.g. every pathspec is genuinely not ignored).
    Exit 128 is a fatal git error (e.g. not actually a git repo); folding it
    into "nothing ignored" fails open the same way a single-path check
    always has. See "Owning-repo check-ignore (#1039)" in the module
    docstring for why fail-open (never skip on doubt) is the deliberate,
    one-sided policy here.
    """
    try:
        result = subprocess.run(
            ["git", "-c", "core.quotePath=false", "check-ignore", "--", *pathspecs],
            cwd=str(git_root),
            capture_output=True,
            timeout=5,
            env=_hermetic_git_env(),
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired):
        return set()  # Subprocess failed — fail open.

    if result.returncode not in (0, 1):
        return set()  # Fatal git error — fail open.

    return {line for line in result.stdout.splitlines() if line}


def _is_git_ignored(resolved_path: Path) -> bool:
    """True if ``resolved_path`` is gitignored BY ITS OWN REPO.

    See "Owning-repo check-ignore (#1039)" in the module docstring for the
    full rationale. Summary: resolve the nearest ``.git`` ancestor of the
    file (its OWNING repo, which may be a child repo nested under
    ``REPO_ROOT``, not ``REPO_ROOT`` itself), then run ``git check-ignore``
    there against the path relative to that repo — checking the per-file AND
    per-directory caches first (#1122; see the module docstring's cache
    section for exactly what each caches and why both are sound).

    Fails OPEN (returns False -> file gets tracked) on every error case: no
    ``.git`` ancestor, a path that doesn't resolve relative to its own
    repo root, or a ``git`` subprocess failure/timeout. Under-tracking is a
    silent loss of drift detection; over-tracking is merely noise — this
    function never risks the former.
    """
    git_root = _find_git_root(resolved_path)
    if git_root is None:
        return False  # No owning repo found — can't determine; track it.

    try:
        rel = resolved_path.relative_to(git_root)
    except ValueError:
        return False  # Shouldn't happen (git_root is an ancestor), fail open anyway.

    rel_str = str(rel)
    file_key = (str(git_root), rel_str)
    cached = _GIT_CHECK_IGNORE_CACHE.get(file_key)
    if cached is not None:
        return cached

    dir_rel_str = str(rel.parent)
    dir_key = (str(git_root), dir_rel_str)
    dir_cached = _DIR_CHECK_IGNORE_CACHE.get(dir_key)

    if dir_cached is True:
        # gitignore(5): a file cannot be re-included once a parent directory
        # is excluded — authoritative without a subprocess call.
        _GIT_CHECK_IGNORE_CACHE[file_key] = True
        return True

    if dir_cached is False:
        # Directory itself isn't excluded — that says nothing about THIS
        # file (a filename pattern can still match inside it), so fall
        # through to a per-file check, same subprocess cost as before #1122.
        ignored = rel_str in _run_check_ignore(git_root, [rel_str])
        _GIT_CHECK_IGNORE_CACHE[file_key] = ignored
        return ignored

    # Neither the file nor its directory is cached yet: one subprocess call
    # answers both questions and seeds both caches, so every LATER file
    # under this same directory is a cache hit instead of a new subprocess.
    #
    # NO trailing slash on the directory pathspec (main#1263 review finding):
    # a pattern like `data/raw/*` matches the literal STRING "data/raw/" —
    # `git check-ignore -- data/raw/ ...` echoes it back as ignored even
    # though the directory itself is not excluded, only its immediate
    # contents are (minus whatever a later `!` re-include exempts). That
    # false "directory ignored" verdict would then be cached and wrongly
    # applied to every later file in the directory, INCLUDING one a `!`
    # rule legitimately re-includes — a silent under-tracking regression.
    # Querying the bare directory name instead asks git the real question
    # ("is `data/raw` itself excluded?"): a genuinely directory-excluding
    # pattern (`build/`) still matches the bare name, but a
    # contents-only pattern (`data/raw/*`) does not, so `dir_ignored` stays
    # False and each file is still checked on its own merits (same
    # subprocess cost as before this cache existed). A NESTED directory
    # whose own path is swept up by the contents-only pattern (e.g.
    # `data/raw/sub` under `data/raw/*`) still correctly comes back
    # ignored — gitignore(5)'s no-re-include-under-an-excluded-parent rule
    # then genuinely applies to everything beneath it, so the cached True
    # is not a false positive there.
    dir_spec = dir_rel_str
    matched = _run_check_ignore(git_root, [dir_spec, rel_str])
    dir_ignored = dir_spec in matched
    file_ignored = rel_str in matched
    _DIR_CHECK_IGNORE_CACHE[dir_key] = dir_ignored
    _GIT_CHECK_IGNORE_CACHE[file_key] = file_ignored
    return file_ignored


def _should_skip(file_path: str) -> bool:
    """Return True if this file should not be tracked.

    Filters in order: substring patterns (fast path), worktree path
    components, /tmp/ prefix, out-of-repo paths, the linked-worktree
    structural check, then the owning-repo check-ignore backstop (#1039).
    See module docstring for the rationale behind each rule.
    """
    for pattern in SKIP_PATTERNS:
        if pattern in file_path:
            return True

    if _is_worktree_path(file_path):
        return True

    try:
        resolved = Path(file_path).resolve()
    except (OSError, RuntimeError):
        # Cannot resolve (e.g. broken symlink) — be conservative and skip.
        return True

    resolved_str = str(resolved)
    for prefix in SKIP_PREFIXES:
        if resolved_str.startswith(prefix):
            return True

    try:
        resolved.relative_to(REPO_ROOT)
    except ValueError:
        return True

    if _is_linked_worktree(resolved):
        return True

    if _is_git_ignored(resolved):
        return True

    return False


def _compute_sha256(file_path: Path) -> str | None:
    """Compute SHA256 hash of a file. Returns None if file doesn't exist."""
    try:
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except (OSError, PermissionError):
        return None


def _relative_path(file_path: str) -> str:
    """Convert absolute path to relative from repo root."""
    try:
        return str(Path(file_path).resolve().relative_to(REPO_ROOT))
    except ValueError:
        # File is outside repo root — use absolute path as key
        return file_path


def check(input_data: dict) -> dict | None:
    """Dispatcher-compatible entry point for PostToolUse Edit/Write.

    Returns None when the hook is not applicable (wrong tool, skip-path,
    unreadable file); returns an advisory dict describing the checksum
    update when an entry is written. The dispatcher treats non-None as
    advisory only.
    """
    tool_name = input_data.get("tool_name", "")
    if tool_name not in ("Edit", "Write"):
        return None

    file_path = input_data.get("tool_input", {}).get("file_path", "")
    if not file_path:
        return None

    if _should_skip(file_path):
        return None

    sha = _compute_sha256(Path(file_path))
    if sha is None:
        return None

    rel_path = _relative_path(file_path)
    now = datetime.now(timezone.utc).isoformat()

    data = checksums_io.read_checksums(CHECKSUMS_FILE)
    files = data.setdefault("files", {})

    existing = files.get(rel_path, {})
    if existing.get("last_tracked") == sha:
        # No-op re-save (#1122): the file's content hash is byte-for-byte
        # what's already recorded — e.g. an edit that reverts to prior
        # content, or a Write that rewrites identical bytes. `sha` is always
        # a real 64-hex-char digest here (the `sha is None` case already
        # returned above), so this only matches an EXISTING entry whose
        # tracked hash is unchanged — never a brand-new path (`existing`
        # empty -> `.get("last_tracked")` is `None`, which can't equal a
        # real digest). Dirty-ness is driven by `last_tracked !=
        # last_resolved`, not by `tracked_at`, so re-writing the full 103 KB
        # file here would change zero meaningful state — skip the write
        # (the read above still had to happen, to learn this).
        return {"action": "skip_noop", "path": rel_path}

    files[rel_path] = {
        "last_tracked": sha,
        "last_resolved": existing.get("last_resolved", ""),
        "tracked_at": now,
        "resolved_at": existing.get("resolved_at", ""),
    }

    try:
        checksums_io.write_checksums(CHECKSUMS_FILE, data)
    except OSError:
        pass  # Never fail the hook

    return {"action": "tracked", "path": rel_path}


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)
    check(input_data)
    sys.exit(0)


if __name__ == "__main__":
    main()
