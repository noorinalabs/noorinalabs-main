#!/usr/bin/env python3
"""The one `git` subprocess shim for `.claude/lib/` + `.claude/hooks/` (main#1121,
sibling to `gh.py`, main#1119).

18 hooks hand-rolled `subprocess.run(["git", ...], ...)` with inconsistent
timeouts (10/15/20 seconds, or none at all) and inconsistent exception
handling. This is that call, once — mirroring `gh.py::run_gh`'s shape and,
deliberately, its error-propagation stance (see below).

Explicit arg list, never a shell string
========================================
Like `run_gh`, :func:`run_git` calls ``subprocess.run(["git", *args], ...)``
with an explicit ARG LIST — never a shell string, never ``shell=True``. This
org's shell is zsh, which does not word-split an unquoted ``$var`` the way
bash does (main#688) — no shell means no word-splitting, under any shell,
ever.

Error behaviour mirrors `gh.run_gh` — RAW, not wrapped
========================================================
:func:`run_git` uses ``check=True`` and lets ``subprocess.CalledProcessError``
(non-zero exit), ``subprocess.TimeoutExpired`` (see the ``timeout=`` note
below), and ``OSError``/``FileNotFoundError`` (git not on PATH) propagate
RAW — it does not wrap them in a new exception class.

`gh.py`'s docstring documents why this matters for `gh`: `red_sweep.py` and
`base_pin_drift_sweep.py` both catch the raw exception types to degrade
gracefully, and a wrapper would silently break that. The hooks converted in
this PR follow the identical pattern — every hand-rolled `subprocess.run`
call site being replaced here already caught `subprocess.CalledProcessError`,
`subprocess.TimeoutExpired`, and/or `OSError` directly, never a bespoke
exception type, so :func:`run_git` matches `run_gh`'s "propagate raw" stance
rather than introducing a `GitError` no caller asked for.

Timeout is a REQUIRED keyword, with no shared default
=======================================================
Unlike `run_gh` (which has none), :func:`run_git` takes a *required*
``timeout`` keyword rather than a shared default. The 18 hand-rolled call
sites disagreed on 10s/15s/20s (and a couple had no timeout at all) — picking
one number as "the" default would silently change behaviour for whichever
sites didn't already use it. Making the caller state its own timeout
preserves every site's existing value through the conversion and makes a
missing timeout impossible to introduce by omission (git operations that
hang do so instead of a hook script hanging until the harness's own
30s process timeout kills it uninformatively).

Not consolidated here, on purpose
==================================
* `_shell_parse.py` — a totally different concern (tokenizing an untrusted
  Bash command string for a PreToolUse gate to inspect), not a `git`
  subprocess call. Explicitly held (see the manager brief for main#1121):
  PR #1325 holds this file.
* Any call site that needs `git`'s stdout as bytes (none found in this
  directory) — `run_git` always decodes with ``text=True``, matching every
  converted call site.
"""

from __future__ import annotations

import subprocess


def run_git(args: list[str], *, timeout: float) -> str:
    """Run ``git <args>`` with an explicit arg list and return stdout.

    Never a shell string and never ``shell=True`` (main#688 — see module
    docstring).

    Raises ``subprocess.CalledProcessError`` on a non-zero exit,
    ``subprocess.TimeoutExpired`` if ``timeout`` elapses, and
    ``FileNotFoundError`` when git is not on PATH — all RAW and unwrapped,
    so existing ``except (subprocess.CalledProcessError, OSError)``-shaped
    handlers keep matching. See module docstring § Error behaviour.
    """
    proc = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=True,
    )
    return proc.stdout
