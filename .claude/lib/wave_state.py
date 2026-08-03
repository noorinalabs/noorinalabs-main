#!/usr/bin/env python3
"""Shared READ access to cross-repo-status.json (main#1119, epic main#1019).

Seven modules independently derived the same ``_DEFAULT_STATUS`` path, four
defined the same ``_load_status``, two carried a verbatim ``read_repos``, and
six repeated the same ``--status`` argparse block. This is that surface, once.

READ ONLY — writes must NEVER be routed through this module
============================================================
`cross-repo-status.json` is deliberately mixed-style: top-level ``wave_{N}_*``
keys are compact single-liners while older ``wave_*_scope`` blocks are
pretty-indented. That shape is load-bearing for reviewability — a
``json.dumps`` round-trip reformats every compact line into jq's default
pretty form and turns a two-key update into a ~1755-line cosmetic diff.

So `upsert_status_keys.py` writes **text-surgically**: it reads the raw TEXT,
edits the specific lines, validates that the text-level result parses to the
same logical dict as the in-memory result, and writes the TEXT back. It parses
JSON only to *validate*, never to re-serialise, and it must keep doing so.

**To a future consolidator: do not "finish the job" by routing
`upsert_status_keys` through :func:`load_status`.** Two independent reasons:

1. It needs the raw text, not a parsed dict — a parsed dict cannot round-trip
   back to the original formatting.
2. Its validation parse must reflect the exact bytes it is about to edit. A
   cached dict is by definition not guaranteed to be those bytes, so feeding
   it one would make the before/after equality check compare the new text
   against a *stale* logical baseline — converting the file's strongest
   corruption guard into a rubber stamp.

`upsert_status_keys.py` is intentionally untouched by main#1119 and imports
nothing from here.

The cache, and why its key is what it is
=========================================
:func:`load_status` memoises the parse per process, keyed on the file's stat
identity. A cache over a file that the *same process* also rewrites is a
correctness change, not a perf change, so the invalidation rule is spelled out
rather than assumed.

**Key = (st_dev, st_ino, st_size, st_mtime_ns)**, recomputed by a fresh
``stat()`` on *every* call. A stat is microseconds against a ~1.5 ms parse of
this 343 KB file, so validating on every access costs nothing measurable and
buys the property that matters: **no caller, and no writer, ever has to
remember to invalidate.** Coupling the writer to the reader would be one more
thing to get wrong.

Each key component earns its place:

* ``st_mtime_ns`` — the primary signal; nanosecond field so a sub-second
  rewrite is visible on any filesystem that records one (measured here:
  ~0.6 ms granularity).
* ``st_size`` — catches a same-tick rewrite that changed length, which
  ``st_mtime_ns`` alone would miss on a coarse filesystem.
* ``st_ino`` + ``st_dev`` — catch atomic replacement by rename (write-temp +
  ``mv``), where the new file legitimately carries an *older* mtime than the
  one we cached. Without the inode, that write would be invisible.

**The racy-tick guard** (the part mtime-keyed caches usually get wrong):
``st_mtime_ns`` has a nanosecond *field*, not necessarily nanosecond
*resolution*. On a 1-second-granularity filesystem (ext3, HFS+, some network
mounts, some CI runners) two writes inside the same second produce an
identical timestamp; if they also produce an identical size, the key collides
and we would serve stale data. The size check makes that unlikely, not
impossible — flipping a counter from ``5`` to ``6`` preserves length exactly,
and this file is full of small integer counters.

So an entry is cached only once its timestamp tick is **settled** — i.e. no
future write can still land inside it:

    mtime_ns + granularity <= now_ns

``granularity`` is inferred from the timestamp itself rather than probed: a
value with sub-second bits proves the filesystem records them (granularity
~1 ns), while a value on an exact second is treated as possibly-truncated
(granularity 1 s). Landing on an exact second by chance on a nanosecond
filesystem costs one skipped cache entry and never costs correctness — the
inference is deliberately biased toward not caching.

This is the same hazard git handles for its index ("racily clean" entries) and
the same mitigation: refuse to trust a timestamp that is still current. The
practical effect is that a write-then-read within the same tick — exactly the
`/wave-kickoff` and `--write` shapes — is **always re-read from disk**, and
steady-state reads of a settled file are served from memory.

Consequence to state plainly: "one parse per process" holds for a file whose
mtime has settled. It deliberately does NOT hold for a file rewritten during
the same tick, and buying that last parse back would mean trusting a timestamp
that cannot be trusted.

The returned mapping is SHARED — treat it as read-only
=======================================================
:func:`load_status` returns the cached object itself, not a copy; copying a
490-key dict on every call would spend most of what the cache saves. No caller
in this package mutates it today (they build new dicts — see
``wave_status.build_digest``), and ``test_wave_state.py`` pins that invariant
by deep-comparing the loaded mapping before and after exercising every public
read API. A caller that needs to mutate must copy first.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any, NamedTuple

# Repo root = two parents above .claude/lib/ (lib -> .claude -> root). Resolved
# from this file so the default is correct from any cwd or worktree, with no
# `git rev-parse` subprocess (which would re-introduce a shell dependency).
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STATUS_PATH = REPO_ROOT / "cross-repo-status.json"

#: Help text for the shared ``--status`` option. Kept as a constant so the six
#: parsers that used to spell it out individually cannot drift apart again.
STATUS_ARG_HELP = "path to cross-repo-status.json (default: repo-root copy)"

#: One second in nanoseconds — the assumed granularity of a filesystem whose
#: mtime lands on an exact second. See module docstring § racy-tick guard.
_COARSE_GRANULARITY_NS = 1_000_000_000


class _StatKey(NamedTuple):
    """The identity of a particular version of a particular file."""

    dev: int
    ino: int
    size: int
    mtime_ns: int


class _Entry(NamedTuple):
    key: _StatKey
    data: dict


class CacheInfo(NamedTuple):
    """Observability for the cache, so tests can assert parse counts directly.

    ``parses`` is the number of times the file was actually read and decoded —
    the quantity main#1119 is about. ``hits`` counts cache-satisfied calls;
    ``uncacheable`` counts parses that were deliberately NOT cached because the
    file's timestamp tick had not settled (module docstring § racy-tick guard),
    which is the number that distinguishes "the cache is working" from "the
    cache is silently never engaging".
    """

    hits: int
    parses: int
    uncacheable: int


_CACHE: dict[str, _Entry] = {}
_HITS = 0
_PARSES = 0
_UNCACHEABLE = 0


def _now_ns() -> int:
    """Wall-clock nanoseconds, as an injectable seam.

    Must be the same clock family as ``st_mtime_ns`` (wall clock, not
    monotonic) — a monotonic clock cannot be compared against a file
    timestamp. Indirected through a function so the racy-tick tests can pin
    "now" instead of racing a real second boundary; the same test-injection
    pattern as ``_consultation_sentinel._now_seconds``.
    """
    return time.time_ns()


def _stat_key(st: os.stat_result) -> _StatKey:
    return _StatKey(st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns)


def _tick_has_settled(mtime_ns: int, now_ns: int) -> bool:
    """True when no future write can still produce ``mtime_ns``.

    Sub-second bits in the timestamp prove the filesystem records them, so the
    tick is one nanosecond wide and settles as soon as the clock passes it. An
    exact-second value may have been truncated, so it is treated as a
    one-second-wide tick that only settles a full second later.

    A future-dated file (``mtime_ns > now_ns``, clock skew on a network mount)
    fails this check too — a timestamp ahead of our clock is not one we can
    reason about, so it is never cached.
    """
    granularity = 1 if mtime_ns % _COARSE_GRANULARITY_NS else _COARSE_GRANULARITY_NS
    return mtime_ns + granularity <= now_ns


def load_status(status_path: Path | str) -> dict:
    """Parse `cross-repo-status.json` at ``status_path``, memoised per process.

    Behaviourally identical to the ``json.loads(path.read_text())`` one-liners
    it replaces, including the exceptions it raises: ``OSError`` if the file
    cannot be read, ``json.JSONDecodeError`` if it does not parse. A stale
    cache entry can never be returned — see module docstring § The cache.

    The returned mapping is shared; do not mutate it.
    """
    global _HITS, _PARSES, _UNCACHEABLE

    path = Path(status_path)
    try:
        st = path.stat()
    except OSError:
        # Cannot establish identity — fall through to an uncached read so the
        # caller sees the real OSError from the read itself, exactly as the
        # un-cached one-liners did.
        _PARSES += 1
        _UNCACHEABLE += 1
        return json.loads(path.read_text())

    cache_key = os.path.realpath(path)
    key = _stat_key(st)

    entry = _CACHE.get(cache_key)
    if entry is not None and entry.key == key:
        _HITS += 1
        return entry.data

    text = path.read_text()
    data = json.loads(text)
    _PARSES += 1

    # Re-stat AFTER the read: a write that landed mid-read would otherwise be
    # cached under the pre-read identity, pinning a torn parse for the rest of
    # the process. If anything moved, serve this result but cache nothing.
    try:
        key_after = _stat_key(path.stat())
    except OSError:
        _UNCACHEABLE += 1
        _CACHE.pop(cache_key, None)
        return data

    if key_after == key and _tick_has_settled(key.mtime_ns, _now_ns()):
        _CACHE[cache_key] = _Entry(key, data)
    else:
        _UNCACHEABLE += 1
        _CACHE.pop(cache_key, None)
    return data


def invalidate(status_path: Path | str | None = None) -> None:
    """Drop cached parses — for ``status_path``, or all of them when None.

    Not required for correctness: :func:`load_status` re-stats on every call,
    so a rewritten file is detected without anyone announcing it. This is an
    escape hatch for tests and for any future caller that has a reason to force
    a re-read. Callers must NOT come to depend on it — a writer that has to
    remember to invalidate is the failure mode the stat-on-every-call design
    exists to make impossible.
    """
    if status_path is None:
        _CACHE.clear()
        return
    _CACHE.pop(os.path.realpath(Path(status_path)), None)


def cache_info() -> CacheInfo:
    """Current hit / parse / uncacheable counters (see :class:`CacheInfo`)."""
    return CacheInfo(hits=_HITS, parses=_PARSES, uncacheable=_UNCACHEABLE)


def reset_cache_info() -> None:
    """Zero the counters. Test-only; does not touch cached data."""
    global _HITS, _PARSES, _UNCACHEABLE
    _HITS = _PARSES = _UNCACHEABLE = 0


def add_status_argument(parser: argparse.ArgumentParser, *, flag: str = "--status") -> None:
    """Add the shared ``--status PATH`` option to ``parser``.

    Identical option in six modules; ``flag`` exists only so a caller can spell
    it differently without re-deriving the type/default/help triple.
    """
    parser.add_argument(flag, type=Path, default=DEFAULT_STATUS_PATH, help=STATUS_ARG_HELP)


def read_repos(wave: str, status_path: Path) -> list[str]:
    """Return ``wave_{M}_repos_in_scope`` as a list of repo names.

    Raises KeyError if the key is absent — by the time any caller runs, the
    wave's scope must already be recorded, so a missing key is an operator
    error to surface rather than silently treat as the empty set. Raises
    TypeError if the value is present but not a list.
    """
    data = load_status(status_path)
    key = f"wave_{wave}_repos_in_scope"
    if key not in data:
        raise KeyError(key)
    repos: Any = data[key]
    if not isinstance(repos, list):
        raise TypeError(f"{key} is not a list: {repos!r}")
    return [str(r) for r in repos]
