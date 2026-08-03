#!/usr/bin/env python3
"""Shared standalone-invocation ``main()`` bodies for hook scripts (main#1121,
audit item G9).

35+ of the hooks in this directory repeated the same ~12-line stdin-decode /
call-check() / emit boilerplate, and a file-by-file read of every one of them
(not an assumption) found the boilerplate was not actually identical: three
distinguishable exit-code shapes coexisted before this module:

  1. "print only when result is a block" — e.g. ``block_git_config.py`` pre-
     consolidation: ``if result and result.get("decision") == "block"``. For
     every hook using this shape, ``check()`` never actually returns a
     non-block, non-None dict, so it is behaviorally identical to (2) for
     every real caller — confirmed per-file, not assumed.
  2. "print whenever truthy, block only on decision==block" — the majority
     shape (``validate_vps_host.py``, most ``validate_*``/``block_*`` hooks).
  3. "block on ANY non-None result, no decision check" — ``enforce_ontology_
     context.py``'s pre-consolidation body. Its ``check()`` also only ever
     returns None or a block-dict, so again behaviorally identical to (2).

  A fourth, unguarded shape existed too: ``validate_wave_label_evidence.py``
  had no ``try/except`` around ``json.load(sys.stdin)`` at all — malformed or
  empty stdin raised ``json.decoder.JSONDecodeError`` straight out of
  ``__main__``, exit code 1 with a traceback on stderr, not the "exit 0"
  every other hook guaranteed. Converting it to :func:`run_blocking` closes
  that gap; see the PR body for the before/after smoke-test proof.

Canonical policy (this module is now the ONE dialect)
=======================================================
- Malformed stdin — empty (``EOFError``), invalid JSON
  (``json.JSONDecodeError``), or bytes that don't decode under the process
  locale (``UnicodeDecodeError``, not previously guarded ANYWHERE in this
  directory) — exits 0 silently. No converted hook can crash on bad stdin.
- ``check_fn(input_data)`` is called inside a ``try/except Exception``. A
  raised exception is treated exactly like a ``None`` result (allow / no
  advisory) — it can never surface as a traceback — but unlike the historic
  bare ``except Exception: continue`` in ``dispatcher.py``, the swallow is
  LOUD: it is logged to Annunaki's informational ``traces.jsonl`` via
  ``log_pretooluse_diagnostic`` (mirrors the ``post_dispatcher.py`` logged-
  swallow this issue also ports into ``dispatcher.py`` itself). "A hook must
  never crash" is a hard contract; "an exception is invisible" is not — this
  module keeps the first and drops the second.
- A truthy ``check_fn()`` result is always printed as JSON (dialect 2 above).
  :func:`run_blocking` additionally exits 2 iff ``result.get("decision") ==
  "block"``; :func:`run_advisory` always exits 0 regardless of what the
  result contains — PostToolUse hooks (and the few PreToolUse hooks that are
  advisory-only, e.g. ``validate_wave_context.py``) cannot block the tool
  call, so branching on ``decision`` there would be dead code, not a
  no-op — it's simply the wrong contract for that call site.

``check_fn`` may accept extra keyword-only args with defaults (e.g.
``block_squash_wave_merge.check(input_data, *, base_runner=None)``) — both
helpers call it with exactly one positional argument, so any keyword-only
default the module itself supplies is used unchanged.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from annunaki_log import log_pretooluse_diagnostic  # noqa: E402

CheckFn = Callable[[dict], "dict | None"]


def _read_stdin_json() -> Any:
    """Decode one JSON value from stdin.

    Returns ``None`` on ANY malformed input: empty stdin (``EOFError``),
    invalid JSON (``json.JSONDecodeError``), or bytes that don't decode
    under the process locale (``UnicodeDecodeError`` — not previously
    guarded by any hook in this directory; see module docstring). Note a
    syntactically valid but non-dict JSON value (e.g. ``42`` or ``[1]``) is
    passed through as-is — every existing hook already tolerates that case
    only by virtue of the swallow in :func:`run_blocking`/:func:`run_advisory`
    below, since ``check_fn`` calling ``.get()`` on it raises ``AttributeError``,
    which the caller now catches too.
    """
    try:
        return json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError, UnicodeDecodeError):
        return None


def _command_excerpt(input_data: Any) -> str:
    """Best-effort diagnostic excerpt — mirrors post_dispatcher.py's
    command / file_path / notebook_path fallback chain. Tolerates a
    non-dict ``input_data`` (see :func:`_read_stdin_json`)."""
    if not isinstance(input_data, dict):
        return str(input_data)[:500]
    tool_input = input_data.get("tool_input")
    if not isinstance(tool_input, dict):
        return str(tool_input)[:500]
    if "command" in tool_input:
        return str(tool_input.get("command", ""))[:500]
    return str(tool_input.get("file_path") or tool_input.get("notebook_path") or tool_input)[:500]


def _log_swallowed_exception(hook_name: str, input_data: Any, exc: Exception) -> None:
    """Loud swallow (main#1121): a ``check_fn`` exception never crashes the
    hook, and — unlike the pre-#1121 bare ``except: continue`` in
    ``dispatcher.py`` — it is no longer silent either. Written to the
    existing ``pretooluse_diagnostic`` trace channel (informational;
    ``traces.jsonl``, never counted as an ``/annunaki`` error)."""
    tool_name = input_data.get("tool_name", "") if isinstance(input_data, dict) else ""
    try:
        log_pretooluse_diagnostic(
            hook_name,
            _command_excerpt(input_data),
            {"swallowed_exception": f"{type(exc).__name__}: {exc}"},
            tool_name=str(tool_name),
        )
    except Exception:
        pass  # logging must never crash the hook it exists to protect


def run_blocking(check_fn: CheckFn, hook_name: str) -> None:
    """Standard ``main()`` body for a PreToolUse gate hook.

    Exit 0 = allow, 2 = block. Never raises past this call — see module
    docstring for the exact malformed-input and exception policy.
    """
    input_data = _read_stdin_json()
    if input_data is None:
        sys.exit(0)

    try:
        result = check_fn(input_data)
    except Exception as exc:  # noqa: BLE001 — deliberate, see module docstring
        _log_swallowed_exception(hook_name, input_data, exc)
        sys.exit(0)

    if not result:
        sys.exit(0)

    print(json.dumps(result))
    sys.exit(2 if result.get("decision") == "block" else 0)


def run_advisory(check_fn: CheckFn, hook_name: str) -> None:
    """Standard ``main()`` body for a hook that can never block the tool
    call (every PostToolUse hook, plus the few PreToolUse/SendMessage hooks
    that are advisory-only).

    Always exits 0. Never raises past this call.
    """
    input_data = _read_stdin_json()
    if input_data is None:
        sys.exit(0)

    try:
        result = check_fn(input_data)
    except Exception as exc:  # noqa: BLE001 — deliberate, see module docstring
        _log_swallowed_exception(hook_name, input_data, exc)
        sys.exit(0)

    if result:
        print(json.dumps(result))
    sys.exit(0)
