#!/usr/bin/env python3
"""The one `gh` subprocess shim for `.claude/lib/` (main#1119, epic main#1019).

Six modules had grown a byte-for-byte identical `_run_gh` whose docstrings
openly admitted the mirroring ("same contract as ``wave_status._run_gh``",
"mirrors :mod:`wave_status`"). This is that function, once.

The main#688 contract this preserves
====================================
Every `gh` invocation goes through :func:`run_gh`, which calls
``subprocess.run(["gh", *args], ...)`` with an explicit ARG LIST — never a
shell string, never ``shell=True``. That is the whole point: this org's shell
is zsh, which does NOT word-split an unquoted ``$var`` the way bash does, so
a newline-joined repo list passed through a shell collapsed into a single
bogus ``--repo`` value (merged-PR count 0 -> division by zero). No shell means
no word-splitting, under any shell, ever.

Error behaviour is deliberately UNCHANGED from the six functions it replaces
=============================================================================
:func:`run_gh` uses ``check=True`` and lets ``subprocess.CalledProcessError``
(and ``OSError``/``FileNotFoundError``) propagate RAW. It does **not** wrap
them in :class:`GhError`.

That is not an oversight, it is the consolidation's safety property. Callers
already catch the raw exception types and degrade gracefully on them —
`red_sweep.py` and `base_pin_drift_sweep.py` both define
``_GH_ERRORS = (subprocess.CalledProcessError, OSError)`` and use it to turn a
gh failure into "undetermined" rather than a crash. Had this shim started
raising a new exception class, those ``except`` clauses would silently stop
matching and a graceful degrade would become an unhandled traceback — a
fail-open gate turning into a crash, from a change advertised as a pure
DRY cleanup. If a future caller wants wrapped errors it should wrap at its
own call site (see `verify_deployable_merge._run_gh`, which does exactly
that and is the reason :class:`GhError` lives here).

Not consolidated here, on purpose
=================================
* ``gh_rest.py::_run_gh`` — different contract entirely: a ``timeout=``, no
  ``check=True``, and it raises ``GhRestError`` on non-zero exit precisely so
  a REST fallback never masquerades as an empty result (#1224). Folding it in
  would destroy that guarantee.
* ``verify_deployable_merge.py::_run_gh`` — keeps its own thin wrapper because
  wrapping failures into :class:`GhError` IS its distinct behaviour (readiness
  "cannot be determined", exit 2). It now builds that wrapper on
  :func:`run_gh` and imports :class:`GhError` from here, so the subprocess
  call and the exception type are still single-source.

Module name
===========
Deliberately the bare `gh`, joining the existing `gh_rest.py` / `gh_quota.py`
family. `.claude/lib` is inserted at ``sys.path[0]`` by its own modules, so
this name shadows any same-named third-party package for those importers;
there is none today, and the sibling naming makes the family obvious.
"""

from __future__ import annotations

import subprocess


class GhError(RuntimeError):
    """A gh/API call failed and the answer cannot be determined.

    The canonical wrapped-failure type for this package. :func:`run_gh` never
    raises it (see module docstring § Error behaviour); it exists for callers
    that deliberately convert a raw ``CalledProcessError`` into an
    "undetermined" verdict — `verify_deployable_merge` re-exports it so
    ``verify_deployable_merge.GhError`` and ``gh.GhError`` are the same class
    and an ``isinstance`` check works across both spellings.
    """


def run_gh(args: list[str]) -> str:
    """Run ``gh <args>`` with an explicit arg list and return stdout.

    Never a shell string and never ``shell=True`` — no shell means no
    word-splitting, so a multi-word value can never collapse into one bogus
    flag (main#688).

    Raises ``subprocess.CalledProcessError`` on a non-zero exit and
    ``FileNotFoundError`` when gh is not on PATH — both RAW and unwrapped, so
    existing ``except (subprocess.CalledProcessError, OSError)`` handlers keep
    matching. See module docstring § Error behaviour.
    """
    proc = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout
