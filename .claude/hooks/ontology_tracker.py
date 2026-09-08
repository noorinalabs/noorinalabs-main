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
      during W11 close-out (#525). Skipping the worktree KEY is still the
      right call — it prevents accumulation of stale paths in
      ``checksums.json`` after worktrees are removed — but see "Catch-up
      after a worktree edit (#1219)" below for what does NOT follow from it.
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

Catch-up after a worktree edit (#1219):
  This docstring used to assert a catch-up that does not exist. The claim was
  that "the canonical entry for the underlying file is updated whenever the
  file is next Edit/Written directly on the main checkout", and that the
  resulting latency was "acceptable". Neither half survived measurement.

  CLAUDE.md makes worktrees the preferred isolation for every code-writing
  agent, so a subsequent DIRECT edit on the main checkout is now the
  exception, not the rule. The latency is therefore unbounded: on
  2026-09-08, 158 of 314 tracked entries disagree with the file on disk, and
  41 of the 48 tracked ``.claude/{hooks,lib,skills}`` paths — the files an
  agent edits in a worktree — are among them (``.claude/hooks/`` is 24 of
  24). A merge is not a tool call, so a squash-merge of a worktree-only PR
  does not update the tracker either.

  What the skip actually leaves behind, stated precisely:

    * An ALREADY-TRACKED file edited in a worktree keeps its pre-edit
      ``last_tracked``. Once the PR merges, the ledger's two stored values
      still agree with each other and no longer agree with the file, so
      ``checksums_io.classify_against_file`` calls it DRIFTED (#1505/#1514)
      — the reconcile remedy — when what happened was an ordinary edit whose
      honest state is DIRTY, the ``/ontology-rebuild`` remedy.
    * A file CREATED only in a worktree gets no entry at all. That is worse
      than drift: it is invisible on every channel, indistinguishable from a
      path the overlay was never meant to track.

  The remedy is the ``catch-up`` subcommand of this module (see
  :func:`plan_catch_up` and ``main``). It runs on a real checkout, advances
  ``last_tracked`` to the file's current hash for in-scope paths, CREATES an
  entry for an in-scope includable path that has none, and NEVER writes
  ``last_resolved`` — so the entries it touches land as DIRTY and route to
  ``/ontology-rebuild``, which is the honest destination for "an edit
  happened and the overlay has not read it yet". It is dry-run by default
  and refuses to run without an explicit scope selector; the wholesale pass
  over today's 158 drifted entries is #1513's decision, not this module's.

  This hook still does not write a worktree-keyed entry, and still returns
  no ledger write on the skip path — but as of #1219 it no longer returns a
  bare ``None`` there. See :func:`check` for the action vocabulary a caller
  can branch on.

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
  0 — always, in HOOK mode (advisory hook, never blocks)

  In CLI mode (``python3 .claude/hooks/ontology_tracker.py catch-up …``, i.e.
  argv is non-empty) the exit code is the catch-up verdict instead — 0 / 1 /
  2 / 3 / 4, documented on :func:`_catch_up_cli`. The two modes are
  discriminated by argv alone: the dispatcher imports this module and calls
  :func:`check` directly, and the standalone hook invocation passes no
  arguments, so neither can reach the CLI branch.
"""

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CHECKSUMS_FILE = REPO_ROOT / "ontology" / "checksums.json"

# The ledger's tracked-hash field name. MUST equal `checksums_io._TRACKED_KEY`
# — the writer and the classifier disagreeing about a field name is #1142's
# exact failure, and every way of getting it wrong yields a comparison that
# quietly evaluates to "no change". Not imported from there (it is private to
# that module); the coupling is pinned instead by
# `LedgerFieldNameCouplingTests` in the test module, which fails if the two
# ever drift apart.
_LAST_TRACKED = "last_tracked"

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

# Skip reasons (#1219). `_skip_reason` returns one of these instead of a bare
# True, so `check()` can name what happened on its return channel and
# `plan_catch_up` can report why an in-scope path was passed over. The two
# WORKTREE_SKIP_REASONS are the pair this hook is silently lossy about — an
# edit that WOULD have been tracked had it happened on the main checkout.
SKIP_PATTERN = "skip_pattern"
SKIP_WORKTREE_PATH = "worktree_path"
SKIP_UNRESOLVABLE = "unresolvable"
SKIP_TMP_PREFIX = "tmp_prefix"
SKIP_OUT_OF_REPO = "out_of_repo"
SKIP_LINKED_WORKTREE = "linked_worktree"
SKIP_GITIGNORED = "gitignored"

WORKTREE_SKIP_REASONS = frozenset({SKIP_WORKTREE_PATH, SKIP_LINKED_WORKTREE})

# `check()` action vocabulary (#1219). Every non-applicable-tool return is
# still None; every path that reached a decision about a real file now names
# that decision. See `check()` for the per-action contract.
ACTION_TRACKED = "tracked"
ACTION_SKIP_NOOP = "skip_noop"
ACTION_SKIPPED = "skipped"
ACTION_SKIPPED_WORKTREE = "skipped_worktree"
ACTION_UNREADABLE = "unreadable"

# Per-path outcomes of a `catch-up` plan. `caught_up` is the union the CLI
# reports as "would change / did change"; the plan keeps `advanced` and
# `created` apart because they mean different things about the ledger's prior
# knowledge of the path.
CATCH_UP_ADVANCED = "advanced"
CATCH_UP_CREATED = "created"
CATCH_UP_IN_SYNC = "in_sync"
CATCH_UP_UNMEASURABLE = "unmeasurable"
CATCH_UP_SKIPPED = "skipped"

_CATCH_UP_HINT = "python3 .claude/hooks/ontology_tracker.py catch-up --since <ref>"


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

    ``encoding="utf-8", errors="surrogateescape"`` rather than ``text=True``,
    and the reason is the FILENAME BYTES, not the locale (main#1263 review,
    Weronika Zielinska). An earlier version of this docstring blamed a
    ``LC_ALL=C`` runner raising ``UnicodeDecodeError``. That was false, and
    for a subtler reason than "coercion": ``LC_ALL=C python3`` auto-enables
    **UTF-8 Mode (PEP 540)** — ``sys.flags.utf8_mode == 1`` while ``LC_CTYPE``
    stays ``C`` — so PEP 538 C-locale *coercion* never runs at all. That is
    why ``PYTHONCOERCECLOCALE=0`` does not restore ASCII either; it defeats
    538, not 540. Only ``PYTHONUTF8=0 PYTHONCOERCECLOCALE=0`` yields
    ``ANSI_X3.4-1968``. Do not restore the locale rationale.

    Historical note on how that was caught, because it dates: when measured
    at ``2c113e7`` the suite was green under ``LC_ALL=C`` with ``text=True``,
    which is what falsified the claim. That is no longer reproducible —
    ``test_invalid_utf8_filename_is_detected`` below now catches ``text=True``
    at ANY locale, because the trigger is the filename bytes rather than the
    environment. The fixture, not the locale, is what pins this line.

    The real trigger: a POSIX filename is a byte string and need not be valid
    UTF-8. The caller's pathspec comes from ``os.fsdecode``, which maps
    undecodable bytes to lone surrogates (``b"\\xe9.log"`` -> ``"\\udce9.log"``).
    For set-membership below to work, git's echoed stdout must decode back to
    that SAME string. Only ``surrogateescape`` does:

    - ``text=True`` (strict) can raise ``UnicodeDecodeError``, which is not in
      the ``except`` clause and would escape ``check()``, breaking this hook's
      "exit 0 — always" contract.
    - ``errors="replace"`` cannot raise but is lossy — the byte decodes to
      U+FFFD, which does not equal the caller's surrogate, so a genuinely
      ignored file reads as NOT ignored. That is the same fail-open defect the
      ``core.quotePath`` pin above exists to fix, one level narrower, and it
      was shipped here briefly before review caught it.
    - ``surrogateescape`` is non-raising AND byte-exact round-trips, so it
      strictly dominates both.

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
            errors="surrogateescape",
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
    #
    # Why no `--no-index` (main#1263 review, Weronika Zielinska): git's
    # index-masking applies to the DIRECTORY pathspec too, not just to
    # files. `git check-ignore -- dist dist/manifest.json` exits 1 when
    # `dist` holds force-added tracked files, where `--no-index` would
    # report both as matched. The practical consequence is a useful
    # invariant rather than a bug: `dir_ignored` can only ever cache True
    # for a directory that holds ZERO tracked files, so the short-circuit
    # can never suppress tracking of a path git already knows about.
    dir_spec = dir_rel_str
    matched = _run_check_ignore(git_root, [dir_spec, rel_str])
    dir_ignored = dir_spec in matched
    file_ignored = rel_str in matched
    _DIR_CHECK_IGNORE_CACHE[dir_key] = dir_ignored
    _GIT_CHECK_IGNORE_CACHE[file_key] = file_ignored
    return file_ignored


def _skip_reason(file_path: str, repo_root: Path | None = None) -> str | None:
    """Name WHY this file is not tracked, or ``None`` if it should be.

    The single skip predicate (:func:`_should_skip` is now a thin
    ``is not None`` over it). Splitting the boolean into a named reason is
    what lets :func:`check` return an action a caller can branch on instead
    of a bare ``None`` that means five different things (#1219), and what
    lets :func:`plan_catch_up` report *why* an in-scope path was passed over.

    Filters in order — unchanged from the pre-#1219 boolean, reason names in
    parentheses: substring patterns (``skip_pattern``, the fast path),
    worktree path components (``worktree_path``), an unresolvable path
    (``unresolvable``), the /tmp/ prefix (``tmp_prefix``), out-of-repo paths
    (``out_of_repo``), the linked-worktree structural check
    (``linked_worktree``), then the owning-repo check-ignore backstop
    (``gitignored``, #1039). See module docstring for the rationale behind
    each rule.

    ``repo_root`` overrides the module-level :data:`REPO_ROOT` for the
    out-of-repo test. The ``catch-up`` CLI passes its ``--repo-root`` through
    here so the include policy is evaluated against the tree being caught up,
    rather than against whichever checkout this file was imported from.
    """
    root = REPO_ROOT if repo_root is None else repo_root

    for pattern in SKIP_PATTERNS:
        if pattern in file_path:
            return SKIP_PATTERN

    if _is_worktree_path(file_path):
        return SKIP_WORKTREE_PATH

    try:
        resolved = Path(file_path).resolve()
    except (OSError, RuntimeError):
        # Cannot resolve (e.g. broken symlink) — be conservative and skip.
        return SKIP_UNRESOLVABLE

    resolved_str = str(resolved)
    for prefix in SKIP_PREFIXES:
        if resolved_str.startswith(prefix):
            return SKIP_TMP_PREFIX

    try:
        resolved.relative_to(root)
    except ValueError:
        return SKIP_OUT_OF_REPO

    if _is_linked_worktree(resolved):
        return SKIP_LINKED_WORKTREE

    if _is_git_ignored(resolved):
        return SKIP_GITIGNORED

    return None


def _should_skip(file_path: str, repo_root: Path | None = None) -> bool:
    """Return True if this file should not be tracked.

    Preserved as the boolean face of :func:`_skip_reason` — every pre-#1219
    caller and test keeps working unchanged, and there is still exactly one
    place the ordering of the filters is written down.
    """
    return _skip_reason(file_path, repo_root) is not None


def _relative_path(file_path: str) -> str:
    """Convert absolute path to relative from repo root."""
    try:
        return str(Path(file_path).resolve().relative_to(REPO_ROOT))
    except ValueError:
        # File is outside repo root — use absolute path as key
        return file_path


def _canonical_key(resolved: Path) -> str | None:
    """The repo-relative key a worktree-resident file will have on ``main``.

    A linked worktree mirrors the repository layout, so the file's path
    relative to its OWN git root is the same key ``_relative_path`` would
    produce for that file on the main checkout. Returns ``None`` when the
    root cannot be determined (no ``.git`` ancestor, or the resolved path is
    somehow not under the root it was found from) — callers must treat that
    as "no breadcrumb available" rather than substituting a guess.

    This is a BREADCRUMB, not a key to write under. Recording a worktree
    file's hash against its canonical key in the MAIN checkout's ledger would
    claim that main's copy holds bytes it does not yet hold — manufacturing a
    drifted entry for a file that is perfectly in sync on main, which is the
    one outcome worse than the gap #1219 describes. The key is emitted so a
    reader (and `catch-up --paths`) knows which entry to look at later.
    """
    git_root = _find_git_root(resolved)
    if git_root is None:
        return None
    try:
        return resolved.relative_to(git_root).as_posix()
    except ValueError:
        return None


def _worktree_skip_result(file_path: str, reason: str) -> dict:
    """The ``skipped_worktree`` return, plus the render channel's share of it.

    Two channels, deliberately split (#1219, wave-31 bar clause 2):

    * The RETURN VALUE always carries ``action="skipped_worktree"`` and, when
      resolvable, the ``canonical_path`` breadcrumb. ``post_dispatcher``
      branches on ``isinstance(result, dict)`` to decide whether to write a
      ``posttooluse_dispatch`` annunaki trace record, so a dict here is the
      difference between a recorded event and no evidence at all. Pre-#1219
      this path returned ``None`` and was therefore indistinguishable, on
      that branch, from "the tool was not Edit/Write".
    * The RENDERED ``systemMessage`` is added only when the skip is losing
      something REAL: the canonical path already has a ledger entry and this
      file's bytes hash to something other than its ``last_tracked``. That is
      the #1219 case exactly — an overlay-described file changing without the
      overlay learning — and it is the one an agent can act on before the PR
      merges. Emitting on every worktree Edit instead would put a banner on
      essentially every edit this org makes (CLAUDE.md § worktrees), which is
      how ``EMIT_DISPATCH_SUMMARY`` came to be default-off in the first
      place; a warning nobody can avoid gets switched off, and then the
      channel is worse than silent.

    A brand-new worktree-only file has no entry to diverge from, so it takes
    the quiet branch here. It is not left unaddressed: ``catch-up --since``
    creates its entry once the merge makes a canonical file exist to hash.
    Before the merge there is nothing on ``main`` to record.

    Never raises: any failure reading or hashing degrades to the quiet
    branch, because a PostToolUse advisory must not become a source of
    errors on the path it is advising about.
    """
    result: dict = {"action": ACTION_SKIPPED_WORKTREE, "reason": reason, "path": file_path}
    try:
        resolved = Path(file_path).resolve()
    except (OSError, RuntimeError):
        return result

    canonical = _canonical_key(resolved)
    if canonical is None:
        return result
    result["canonical_path"] = canonical

    try:
        entry = checksums_io.read_checksums(CHECKSUMS_FILE).get("files", {}).get(canonical)
        if not isinstance(entry, dict):
            return result
        stored = entry.get("last_tracked")
        if not isinstance(stored, str) or not stored:
            return result
        sha = checksums_io.compute_sha256(resolved)
    except OSError:
        return result
    if sha is None or sha == stored:
        return result

    result["diverged_from_ledger"] = True
    result["systemMessage"] = (
        f"ontology_tracker: this worktree edit will NOT reach ontology/checksums.json. "
        f"`{canonical}` is tracked and now hashes to {sha[:12]}…, ledger stores "
        f"{stored[:12]}…. Worktree paths are skipped by design (#523/#525); the entry "
        f"catches up only when someone runs, on the main checkout after this merges:\n"
        f"  {_CATCH_UP_HINT}   (#1219)"
    )
    return result


def check(input_data: dict) -> dict | None:
    """Dispatcher-compatible entry point for PostToolUse Edit/Write.

    Returns ``None`` ONLY when the hook is genuinely not applicable — the
    tool is not Edit/Write, or the payload carries no ``file_path``. Every
    call that reached a decision about a real file returns a dict naming that
    decision in ``action`` (#1219):

    ==================== ==========================================
    ``action``           meaning
    ==================== ==========================================
    ``tracked``          an entry was written for this file
    ``skip_noop``        already tracked at this exact hash; no write
    ``skipped_worktree`` in a worktree — deliberately not tracked,
                         and the canonical entry is now behind
    ``skipped``          out of scope for another reason (``reason``
                         names which: gitignored, /tmp, out-of-repo…)
    ``unreadable``       in scope, but the file could not be hashed
    ==================== ==========================================

    Pre-#1219 the middle three all returned a bare ``None``, which
    ``post_dispatcher`` cannot tell apart from "this hook did not apply" —
    it only emits a dispatch-trace record for a dict. A worktree edit,
    a gitignored edit, an unhashable file and a NotebookEdit therefore all
    left exactly the same evidence: none. ``unreadable`` in particular was
    the "could not evaluate" case reporting as the "nothing to do" case.

    The dispatcher treats non-None as advisory only; it can never block.
    """
    tool_name = input_data.get("tool_name", "")
    if tool_name not in ("Edit", "Write"):
        return None

    file_path = input_data.get("tool_input", {}).get("file_path", "")
    if not file_path:
        return None

    reason = _skip_reason(file_path)
    if reason is not None:
        if reason in WORKTREE_SKIP_REASONS:
            return _worktree_skip_result(file_path, reason)
        return {"action": ACTION_SKIPPED, "reason": reason, "path": file_path}

    # THE shared hasher (#1505). It used to be a private `_compute_sha256`
    # here; the reader (`checksums_io.classify_against_file`) now compares the
    # value this writes against the file, so the two MUST hash identically —
    # a second copy free to drift would report every entry as drifted.
    sha = checksums_io.compute_sha256(Path(file_path))
    if sha is None:
        # In scope, but not measurable. "Could not evaluate" is not "nothing
        # to do" — returning None here made an unhashable tracked file look
        # exactly like a NotebookEdit (#1219, wave-31 bar clause 2a).
        return {"action": ACTION_UNREADABLE, "path": _relative_path(file_path)}

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
        return {"action": ACTION_SKIP_NOOP, "path": rel_path}

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

    return {"action": ACTION_TRACKED, "path": rel_path}


##############################################################################
# catch-up (#1219) — the writer's answer to the skip it cannot avoid.
##############################################################################

CATCH_UP_EXIT_OK = 0
CATCH_UP_EXIT_PENDING = 1
CATCH_UP_EXIT_USAGE = 2
CATCH_UP_EXIT_UNREADABLE = 3
CATCH_UP_EXIT_UNMEASURABLE = 4


@dataclass(frozen=True)
class CatchUpPlan:
    """What a ``catch-up`` run WOULD change, computed without writing anything.

    Every list holds ``(rel_path, detail)`` pairs and is sorted, so the dry-run
    render and the applied render are the same text and a caller diffing two
    runs sees a stable ordering.

    * ``advanced`` — tracked, present, and hashes to something other than
      ``last_tracked``. ``detail`` is the new hash.
    * ``created`` — NOT tracked, present, and passes the include policy.
      ``detail`` is the hash. This is case (b): the worktree-only new file.
    * ``in_sync`` — tracked and already hashes to ``last_tracked``.
    * ``unmeasurable`` — in scope but could not be hashed (absent from this
      tree, unreadable). NOT clean, NOT caught up, and never deleted here —
      dropping an entry is ``checksums_io.prune``'s guarded, preview-by-
      default job, not a side effect of catching up.
    * ``skipped`` — the include policy says this path is not the overlay's
      business. ``detail`` is the ``_skip_reason`` name.
    """

    advanced: tuple[tuple[str, str], ...]
    created: tuple[tuple[str, str], ...]
    in_sync: tuple[tuple[str, str], ...]
    unmeasurable: tuple[tuple[str, str], ...]
    skipped: tuple[tuple[str, str], ...]

    @property
    def pending(self) -> tuple[tuple[str, str], ...]:
        """Everything an ``--apply`` would write, advanced and created alike."""
        return tuple(sorted(self.advanced + self.created))


def plan_catch_up(data: dict, repo_root: Path, rel_paths: list[str]) -> CatchUpPlan:
    """Classify each in-scope path against the ledger. Pure: writes nothing.

    ``rel_paths`` are repo-relative keys in the same namespace
    :func:`_relative_path` writes. The include policy is :func:`_skip_reason`
    evaluated against ``repo_root`` — the same predicate the hook itself uses,
    not a second copy of it. That matters in both directions:

    * ``ontology/checksums.json`` is itself a tracked entry AND matches
      ``SKIP_PATTERNS``. Advancing its ``last_tracked`` would be a fixpoint
      chase — the write changes the file whose hash was just recorded — so it
      lands in ``skipped``, not ``advanced``.
    * A child-repo path is NOT skipped: ``_is_git_ignored`` asks the file's
      OWNING repo, and a child's committed source is not ignored by its own
      ``.gitignore`` (#1039). Child entries are caught up like any other when
      the clone is present, and land in ``unmeasurable`` when it is not.
    """
    files = data.get("files")
    if not isinstance(files, dict):
        files = {}
    advanced: list[tuple[str, str]] = []
    created: list[tuple[str, str]] = []
    in_sync: list[tuple[str, str]] = []
    unmeasurable: list[tuple[str, str]] = []
    skipped: list[tuple[str, str]] = []

    for rel in sorted(set(rel_paths)):
        abs_path = repo_root / rel
        entry = files.get(rel)
        reason = _skip_reason(str(abs_path), repo_root)
        if reason is not None:
            skipped.append((rel, reason))
            continue
        sha = checksums_io.compute_sha256(abs_path) if abs_path.exists() else None
        if sha is None:
            if entry is None:
                # Not tracked and not there — a deletion, or a path the
                # caller named speculatively. Nothing was lost; say nothing.
                continue
            unmeasurable.append((rel, "tracked path could not be hashed from this tree"))
            continue
        if entry is None:
            created.append((rel, sha))
            continue
        if not isinstance(entry, dict) or not isinstance(entry.get(_LAST_TRACKED), str):
            # Malformed is the reader's verdict to give and `/ontology-rebuild`
            # step 1's to repair. Overwriting it here would erase the evidence.
            unmeasurable.append((rel, "entry schema is unrecognized — see `status`"))
            continue
        if entry[_LAST_TRACKED] == sha:
            in_sync.append((rel, sha))
            continue
        advanced.append((rel, sha))

    return CatchUpPlan(
        advanced=tuple(advanced),
        created=tuple(created),
        in_sync=tuple(in_sync),
        unmeasurable=tuple(unmeasurable),
        skipped=tuple(skipped),
    )


def apply_catch_up(data: dict, plan: CatchUpPlan, now: str) -> int:
    """Write ``plan``'s advances and creations into ``data``. Returns the count.

    THE invariant, and the reason this is a separate function with its own
    test: ``last_resolved`` and ``resolved_at`` are never written. Catching up
    records that the file CHANGED, not that anyone read it. An entry this
    touches therefore satisfies ``last_tracked != last_resolved`` and is
    DIRTY — routed to ``/ontology-rebuild``, which is what "an edit happened"
    has always meant. Copying the new hash into ``last_resolved`` as well
    would take ``status`` to exit 0 on the strength of nobody having read
    anything, which is precisely the false clean #1505 fixed and #1513 exists
    to avoid manufacturing one layer along.
    """
    files = data.setdefault("files", {})
    for rel, sha in plan.advanced:
        entry = files[rel]
        entry[_LAST_TRACKED] = sha
        entry["tracked_at"] = now
    for rel, sha in plan.created:
        files[rel] = {
            _LAST_TRACKED: sha,
            "last_resolved": "",
            "tracked_at": now,
            "resolved_at": "",
        }
    return len(plan.advanced) + len(plan.created)


def _paths_changed_since(repo_root: Path, ref: str) -> list[str] | None:
    """Repo-relative paths differing between ``ref`` and the working tree.

    ``git diff --name-only <ref> --`` rather than a two-dot range, so a merge
    that landed the change AND anything still uncommitted are both in scope —
    the post-merge catch-up is exactly the case where both can be true.

    Returns ``None`` when the scope could not be established (not a git repo,
    unknown ref, git unavailable). The caller must exit non-zero on ``None``:
    an empty scope and an unevaluable scope both produce "0 paths caught up",
    and only one of them is good news (wave-31 bar clause 2a).
    """
    try:
        proc = subprocess.run(
            ["git", "-c", "core.quotePath=false", "diff", "--name-only", ref, "--"],
            cwd=str(repo_root),
            capture_output=True,
            encoding="utf-8",
            errors="surrogateescape",
            env=_hermetic_git_env(),
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return [line for line in proc.stdout.splitlines() if line]


def _normalize_scope_path(raw: str, repo_root: Path) -> str | None:
    """Accept an absolute or repo-relative path; return the repo-relative key."""
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = repo_root / candidate
    try:
        return candidate.resolve().relative_to(repo_root.resolve()).as_posix()
    except (ValueError, OSError, RuntimeError):
        return None


def _render_catch_up(plan: CatchUpPlan, applied: bool, repo_root: Path) -> None:
    """The human channel. Says which of the two zeroes a zero is."""
    verb = "caught up" if applied else "would catch up"
    print(
        f"catch-up ({'APPLIED' if applied else 'DRY RUN'}) against {repo_root}: "
        f"{len(plan.advanced)} advanced, {len(plan.created)} created, "
        f"{len(plan.in_sync)} already in sync, {len(plan.unmeasurable)} unmeasurable, "
        f"{len(plan.skipped)} out of scope"
    )
    for label, rows in (
        (f"advanced (last_tracked -> file hash; becomes DIRTY, {verb})", plan.advanced),
        (f"created (was untracked entirely; becomes DIRTY, {verb})", plan.created),
        ("unmeasurable (in scope, NOT hashed — neither clean nor caught up)", plan.unmeasurable),
    ):
        if rows:
            print(f"{label}:")
            for rel, detail in rows:
                print(f"  - {rel}: {detail}")
    if plan.skipped:
        print(f"out of scope ({len(plan.skipped)} path(s), by _skip_reason):")
        for rel, detail in plan.skipped:
            print(f"  - {rel}: {detail}")

    if not plan.pending and not plan.unmeasurable:
        if not plan.in_sync:
            # The zero that is NOT good news: nothing was hashed at all. Every
            # named path was filtered out by the include policy, or the scope
            # selector matched nothing. Saying "nothing to catch up" here would
            # be the same silent zero this whole row is about.
            print(
                f"VERDICT: NOTHING MEASURED - 0 in-scope tracked path(s) were hashed "
                f"({len(plan.skipped)} filtered out by the include policy). This is an "
                "EMPTY SCOPE, not a clean one; widen --since/--paths or check the "
                "reasons above."
            )
            return
        print(
            f"VERDICT: NOTHING TO CATCH UP - every one of the "
            f"{len(plan.in_sync)} in-scope tracked path(s) was hashed and already "
            f"matches its last_tracked. This is a measured zero, not an empty scope."
        )
        return
    if applied:
        print(
            f"VERDICT: APPLIED - {len(plan.pending)} entr(y/ies) now carry the file's "
            "current hash in last_tracked. last_resolved was NOT written, so they read "
            "DIRTY: run /ontology-rebuild to reconcile the overlay against them."
        )
    else:
        print(
            f"VERDICT: PENDING - {len(plan.pending)} entr(y/ies) are behind their file "
            "and nothing was written (dry run). Re-run with --apply to record them as "
            "DIRTY."
        )
    if plan.unmeasurable:
        print(
            f"  {len(plan.unmeasurable)} in-scope path(s) could NOT be measured and were "
            "left exactly as they were. Not caught up, not clean, not pruned."
        )
        if checksums_io.is_linked_worktree_root(repo_root):
            print(
                f"  NOTE: {repo_root} is a linked worktree. The gitignored child-repo "
                "clones do not exist there. Re-run from the main checkout."
            )


def _catch_up_cli(argv: list[str]) -> int:
    """``catch-up`` subcommand body (#1219).

    Usage::

        ontology_tracker.py catch-up --since <ref>  [--apply] [--json]
        ontology_tracker.py catch-up --paths <p>... [--apply] [--json]
        ontology_tracker.py catch-up --all          [--apply] [--json]
            [--repo-root <dir>] [--checksums <file>]

    Two safety properties are deliberate and tested, not incidental:

    * DRY RUN BY DEFAULT. ``--apply`` is the only way to write. A tool that
      rewrites half the ledger on a bare invocation is not one anybody should
      run to find out what it would do.
    * AN EXPLICIT SCOPE IS REQUIRED. There is no default scope, because the
      only sensible default would be "everything", and running this over
      everything today would convert all 158 drifted entries to dirty in one
      unreviewed step. THAT DECISION BELONGS TO #1513, not to whoever types
      the command; ``--all`` exists so #1513 has a mechanism to invoke, and
      says so on every run.

    Exit codes — a caller can branch on all four outcomes:
        0 — the scope was evaluated and nothing is behind (a MEASURED zero)
            or ``--apply`` completed with everything in scope measured
        1 — dry run, and there is pending work
        2 — usage error (including a missing scope selector)
        3 — nothing could be evaluated: the ledger is unreadable, or
            ``--since``'s ref did not resolve. Never 0 — "could not evaluate"
            is not "nothing to do" (wave-31 bar clause 2a)
        4 — some in-scope paths could not be measured. Outranks 1 and 0 for
            the same reason ``status``'s 4 outranks its 1: a scope that was
            only partly measured must not report as one that was measured.
    """
    apply_changes = False
    as_json = False
    scope_all = False
    since: str | None = None
    explicit_paths: list[str] = []
    checksums_path = CHECKSUMS_FILE
    repo_root_arg: Path | None = None

    rest = list(argv)
    while rest:
        arg = rest[0]
        if arg == "--apply":
            apply_changes, rest = True, rest[1:]
        elif arg == "--dry-run":
            apply_changes, rest = False, rest[1:]
        elif arg == "--json":
            as_json, rest = True, rest[1:]
        elif arg == "--all":
            scope_all, rest = True, rest[1:]
        elif arg in ("--since", "--repo-root", "--checksums"):
            if len(rest) < 2:
                print(f"error: {arg} requires an argument", file=sys.stderr)
                return CATCH_UP_EXIT_USAGE
            if arg == "--since":
                since = rest[1]
            elif arg == "--repo-root":
                repo_root_arg = Path(rest[1])
            else:
                checksums_path = Path(rest[1])
            rest = rest[2:]
        elif arg == "--paths":
            rest = rest[1:]
            while rest and not rest[0].startswith("--"):
                explicit_paths.append(rest[0])
                rest = rest[1:]
            if not explicit_paths:
                print("error: --paths requires at least one path", file=sys.stderr)
                return CATCH_UP_EXIT_USAGE
        else:
            print(f"error: unexpected argument {arg!r} for catch-up", file=sys.stderr)
            return CATCH_UP_EXIT_USAGE

    if not (scope_all or since or explicit_paths):
        print(
            "error: catch-up requires an explicit scope — one of --since <ref>, "
            "--paths <p>..., or --all.\n"
            "       There is no default scope on purpose: the only sensible default "
            "would be everything,\n"
            "       and the wholesale pass over the currently-drifted entries is "
            "#1513's decision, not this\n"
            "       command's. See --help on _catch_up_cli.",
            file=sys.stderr,
        )
        return CATCH_UP_EXIT_USAGE

    repo_root = (
        checksums_io.repo_root_for(checksums_path) if repo_root_arg is None else repo_root_arg
    ).resolve()

    if checksums_io.is_linked_worktree_root(repo_root):
        # Refuse rather than run. From a linked worktree EVERY path resolves
        # through `_is_linked_worktree` and is filtered out, so the run would
        # complete, write nothing, and report a large "out of scope" count —
        # a zero that reads like success. The premise of catch-up is a real
        # checkout; say so instead of producing an unusable clean run.
        print(
            f"error: {repo_root} is a linked worktree. Every path under it is filtered "
            "out by the same worktree skip catch-up exists to compensate for, so this "
            "run could only ever report an empty scope. Run from the main checkout, or "
            "pass --repo-root <main-checkout> --checksums <main-checkout>/ontology/"
            "checksums.json.",
            file=sys.stderr,
        )
        return CATCH_UP_EXIT_UNREADABLE

    try:
        data = checksums_io.read_checksums_strict(checksums_path)
    except checksums_io.ChecksumsUnreadable as exc:
        # NOT exit 0 with a zero count. Nothing was evaluated.
        print(f"error: {exc}", file=sys.stderr)
        return CATCH_UP_EXIT_UNREADABLE

    scope: set[str] = set()
    if scope_all:
        tracked = data.get("files")
        scope.update(tracked if isinstance(tracked, dict) else ())
    if since is not None:
        changed = _paths_changed_since(repo_root, since)
        if changed is None:
            print(
                f"error: could not evaluate --since {since!r} against {repo_root} "
                "(not a git repository, unknown ref, or git unavailable). "
                "Refusing to report an unevaluated scope as an empty one.",
                file=sys.stderr,
            )
            return CATCH_UP_EXIT_UNREADABLE
        scope.update(changed)
    for raw in explicit_paths:
        rel = _normalize_scope_path(raw, repo_root)
        if rel is None:
            print(f"error: {raw!r} does not resolve inside {repo_root}", file=sys.stderr)
            return CATCH_UP_EXIT_USAGE
        scope.add(rel)

    plan = plan_catch_up(data, repo_root, sorted(scope))

    written = 0
    if apply_changes and plan.pending:
        written = apply_catch_up(data, plan, datetime.now(timezone.utc).isoformat())
        checksums_io.write_checksums(checksums_path, data)

    if as_json:
        json.dump(
            {
                "checksums": str(checksums_path),
                "repo_root": str(repo_root),
                "applied": apply_changes,
                "written": written,
                "scope_size": len(scope),
                "advanced": [{"path": p, "hash": h} for p, h in plan.advanced],
                "created": [{"path": p, "hash": h} for p, h in plan.created],
                "in_sync": [p for p, _ in plan.in_sync],
                "unmeasurable": [{"path": p, "reason": r} for p, r in plan.unmeasurable],
                "skipped": [{"path": p, "reason": r} for p, r in plan.skipped],
            },
            sys.stdout,
            indent=2,
            ensure_ascii=False,
        )
        sys.stdout.write("\n")
    else:
        _render_catch_up(plan, applied=apply_changes, repo_root=repo_root)
        if scope_all:
            print(
                "  NOTE: --all was used. Advancing every drifted entry in one pass is "
                "the decision #1513 owns; this command is the mechanism, not the "
                "authorization."
            )

    if plan.unmeasurable:
        return CATCH_UP_EXIT_UNMEASURABLE
    if plan.pending and not apply_changes:
        return CATCH_UP_EXIT_PENDING
    return CATCH_UP_EXIT_OK


_CLI_USAGE = (
    "usage: ontology_tracker.py catch-up (--since REF | --paths P... | --all)\n"
    "                                    [--apply] [--dry-run] [--json]\n"
    "                                    [--repo-root DIR] [--checksums PATH]\n"
    "\n"
    "With no arguments this module is a PostToolUse hook and reads its payload\n"
    "from stdin. See the module docstring."
)


def main(argv: list[str] | None = None) -> None:
    """Hook mode (no argv) or CLI mode (argv), discriminated by argv alone.

    The PostToolUse dispatcher imports this module and calls :func:`check`
    directly, and the standalone hook invocation passes no arguments, so
    neither can reach the CLI branch. Hook mode keeps its unconditional exit
    0 — an advisory hook must never fail the tool call it observes.
    """
    args = sys.argv[1:] if argv is None else list(argv)
    if args:
        if args[0] != "catch-up":
            print(_CLI_USAGE, file=sys.stderr)
            sys.exit(CATCH_UP_EXIT_USAGE)
        sys.exit(_catch_up_cli(args[1:]))

    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)
    check(input_data)
    sys.exit(0)


if __name__ == "__main__":
    main()
