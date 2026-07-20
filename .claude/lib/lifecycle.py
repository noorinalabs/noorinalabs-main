#!/usr/bin/env python3
"""Deterministic wave-lifecycle facade over noorina's cross-repo state (main#1019).

A single, deterministic entry point that drives one iteration ("wave") through
its phases:

    allocate → start → scope → kickoff → (work) → wrapup → retro

**Org-scale adaptation.** Unlike botfarm's single-repo ``lifecycle.py`` (which
owns a private ``.claude/state.json``), noorina is ORG-SCALE / CROSS-REPO: wave
state lives in the repo-root ``cross-repo-status.json`` and is already driven by
three deterministic modules —

  * :mod:`wave_seq`          — the monotonic wave-id allocator (``allocate`` /
                               ``peek``; ``global_wave_seq`` + phase stamps).
  * :mod:`wave_merge_model`  — one-merge-model-per-wave (``get`` / ``set``) plus
                               the mid-wave reachability classifier.
  * :mod:`wave_status`       — in-scope repos, the merged-PR set, the three wave
                               counters, and the session-start digest.

This module does **not** introduce a competing state file or re-implement any of
that. It is a THIN WRAPPER: for the transitions that already have deterministic
code it *delegates* to the owning module (so the keyspace and the counter can
never disagree), and for the transitions that until now lived only in the
``/wave-*`` skill prose — ``start`` / ``scope`` pointers / the ``kickoff``
timestamp / the ``wrapup`` pointers / ``retro`` — it performs the write through
the SAME ``upsert_status_keys`` helper every other tool uses, so the file's
compact-inline shape is preserved and the rewrite is JSON-validated before AND
after (main#332/#456).

Write ownership is respected, not duplicated:

  * ``wave_{W}_phase`` / ``wave_{W}_phase_ordinal`` / ``global_wave_seq`` — owned
    by :mod:`wave_seq` (``allocate`` delegates to it).
  * ``wave_{W}_merge_model`` — validated by :mod:`wave_merge_model` (its enum is
    the single validator; ``kickoff`` reuses it).
  * ``wave_{W}_final_pr_count`` / ``wave_{W}_changes_requested_cycles`` /
    ``wave_{W}_top_concentration_pct`` — owned by :mod:`wave_status` (``counters
    --write``). ``wrapup`` here writes only the lifecycle POINTERS
    (``active`` / ``completed_at`` / ``last_completed_wave``); it never writes a
    counter, matching the lifecycle-doc "Owner of writes" contract (wrapup is the
    authoritative counter writer *via* ``wave_status.py``, retro only verifies).

The genuinely-new deterministic writes this facade adds (previously prose-only in
``/wave-start`` / ``/wave-scope`` / ``/wave-kickoff`` / ``/wave-wrapup`` /
``/wave-retro``):

  * ``start``   → ``current_wave``, ``wave_{W}_active=true``, ``wave_{W}_started_at``
  * ``scope``   → ``wave_{W}_repos_in_scope``, ``wave_{W}_scope_reconciled_at`` (+
                  optional ``wave_{W}_phase``)
  * ``kickoff`` → ``wave_{W}_kicked_off_at``, ``wave_{W}_active=true``,
                  ``current_wave`` (+ optional validated ``wave_{W}_merge_model``)
  * ``wrapup``  → ``wave_{W}_active=false``, ``wave_{W}_completed_at``,
                  ``last_completed_wave``
  * ``retro``   → ``wave_{W}_retro_completed_at`` (the key ``/wave-kickoff`` Step
                  0a reads to gate the next wave)

Every one of those writes also stamps the top-level ``last_updated`` (main#1033)
— see :func:`_persist`. The key previously had no writer at all while
``/session-start`` Step 5 reported file staleness from it. It is wall-clock and
deliberately ignores ``--at``, so back-dating an *event* never back-dates the
*file*.

Wave ids are GLOBAL monotonic ids (``wave_25``), not per-phase ordinals — phase
is a derived display attribute (see :mod:`wave_seq`). ``--status`` defaults to the
repo-root ``cross-repo-status.json``, resolved from this file's location exactly
like the three modules above so it is correct from any cwd or worktree.

Stdlib only. The transition writers are I/O-thin (one ``upsert`` call each);
delegations forward to the owning module's ``main``.

CLI::

  lifecycle.py wave peek                 [--status PATH]
  lifecycle.py wave allocate --phase P   [--write] [--status PATH]
  lifecycle.py wave start    <W>         [--at TS] [--status PATH]
  lifecycle.py wave scope    <W> --repos a,b,c [--phase P] [--at TS] [--status PATH]
  lifecycle.py wave kickoff  <W>         [--merge-model M] [--at TS] [--status PATH]
  lifecycle.py wave wrapup   <W>         [--at TS] [--status PATH]
  lifecycle.py wave retro    <W>         [--at TS] [--status PATH]
  lifecycle.py merge-model get <W>       [--status PATH]           # → wave_merge_model
  lifecycle.py merge-model set <P> <W> <model> [--status PATH]     # → wave_merge_model
  lifecycle.py reachability  <P> <W>     [--json] [--status PATH]  # → wave_merge_model
  lifecycle.py counters      <P> <W>     [--write] [--expect N] [--status PATH]  # → wave_status
  lifecycle.py state show                [--status PATH]
  lifecycle.py state digest              [--status PATH]           # → wave_status
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# The deterministic modules this facade wraps all live alongside it in
# .claude/lib/. Put the lib dir on sys.path so the sibling imports resolve when
# lifecycle.py is imported as a module (run-as-script already has sys.path[0] =
# this dir; the tests add it explicitly). This mirrors the lib->lib import
# bridge wave_seq / wave_status use for upsert_status_keys.
_LIB_DIR = Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import upsert_status_keys  # noqa: E402
import wave_merge_model  # noqa: E402
import wave_seq  # noqa: E402
import wave_status  # noqa: E402

# Repo root = two parents above .claude/lib/ (lib -> .claude -> root). Same
# anchor as wave_seq / wave_merge_model / wave_status so the default status path
# is correct from any cwd or worktree with no `git rev-parse` subprocess.
_REPO_ROOT = _LIB_DIR.parents[1]
_DEFAULT_STATUS = _REPO_ROOT / "cross-repo-status.json"


# ============================================================================
# Shared helpers
# ============================================================================


def _now_iso(at: str | None = None) -> str:
    """An ISO-8601 UTC timestamp; ``at`` overrides for deterministic tests.

    Matches the ``...Z`` shape every existing key in cross-repo-status.json uses
    (e.g. ``wave_25_kicked_off_at``).
    """
    if at:
        return at
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _wave_label(wave: str) -> str:
    """The ``current_wave`` / ``last_completed_wave`` pointer form (``wave-25``)."""
    return f"wave-{wave}"


def _persist(
    status_path: Path,
    pairs: dict[str, object],
    *,
    now: str | None = None,
) -> int:
    """Upsert ``pairs`` (key → python value) into the status file.

    Delegates to :func:`upsert_status_keys.main` — the SAME helper wave_seq /
    wave_merge_model / wave_status write through — so the file's compact-inline
    shape is preserved and the rewrite is JSON-validated before AND after
    (main#332/#456). Each value is rendered as a self-contained JSON literal.
    A no-op returning 0 when ``pairs`` is empty.

    **``last_updated`` is stamped here, on every lifecycle write** (main#1033).
    Until then the key had no writer anywhere — no skill, hook, or lib maintained
    it — yet ``/session-start`` Step 5 reports file staleness from it, so it read
    as ~24 days stale while the file was being written continuously. That is the
    same vestigial-flat-key class as the ``phase`` / ``wave`` keys #683/#708
    taught the session-start and handoff readers to ignore; the fix here is to
    give it a writer rather than teach one more reader to distrust it.

    **It is deliberately wall-clock, NOT the transition's ``at`` override.**
    ``at`` back-dates the *event* ("wave 25 completed at 01:29Z"); ``last_updated``
    answers "how stale is this FILE", which is a property of the write, not of the
    event. Threading ``at`` into it would let a historical replay drag the key
    *backwards* — replaying an old wave would stamp a freshly-written file as
    months old, which is precisely the false-staleness signal this is fixing.
    ``now`` exists only so tests can pin the value; transitions never pass it.

    A ``last_updated`` supplied explicitly in ``pairs`` wins, so a caller that
    genuinely needs to set it (a backfill, a migration) still can.
    """
    if not pairs:
        return 0
    if "last_updated" not in pairs:
        pairs = {**pairs, "last_updated": now or _now_iso()}
    argv = ["lifecycle", str(status_path)]
    for key, value in pairs.items():
        argv.append(f"{key}={json.dumps(value)}")
    return upsert_status_keys.main(argv)


def _load_status(status_path: Path) -> dict:
    return json.loads(status_path.read_text())


# ============================================================================
# Lifecycle transitions
# ============================================================================


def peek(status_path: Path) -> int:
    """The next wave id ``allocate`` would claim (delegates to wave_seq).

    Reservation-aware — a ``wave_{N}_meta_issue`` reserved ahead of the committed
    counter is claimed, not skipped (see :func:`wave_seq.allocation_target`).
    """
    return wave_seq.allocation_target(_load_status(status_path))


def allocate(status_path: Path, phase: int, *, write: bool = False) -> int:
    """Allocate the next global wave id for ``phase`` (delegates to wave_seq).

    ``wave_seq`` is the authoritative allocator: with ``write`` it advances
    ``global_wave_seq`` and stamps ``wave_{W}_phase`` + ``wave_{W}_phase_ordinal``.
    This wrapper never re-implements the monotonic / reservation-aware math.
    """
    argv = ["allocate", str(status_path), "--phase", str(phase)]
    if write:
        argv.append("--write")
    return wave_seq.main(argv)


def start(status_path: Path, wave: str, *, at: str | None = None) -> int:
    """Mark a wave active and point ``current_wave`` at it.

    Deterministic form of ``/wave-start``'s active-state stamping. Writes
    ``current_wave``, ``wave_{W}_active=true``, ``wave_{W}_started_at``.
    """
    return _persist(
        status_path,
        {
            "current_wave": _wave_label(wave),
            f"wave_{wave}_active": True,
            f"wave_{wave}_started_at": _now_iso(at),
        },
    )


def scope(
    status_path: Path,
    wave: str,
    repos: list[str],
    *,
    phase: int | None = None,
    at: str | None = None,
) -> int:
    """Record the wave's in-scope repo list + a scope-reconciled timestamp.

    Writes the two keys ``wave_status.read_repos`` / the kickoff pre-flight read
    (``wave_{W}_repos_in_scope``, ``wave_{W}_scope_reconciled_at``) plus, when
    given, the display phase stamp ``wave_{W}_phase``. The richer
    ``wave_{W}_scope`` block (theme/shape) and the meta-issue reservation stay
    owned by the ``/wave-scope`` skill — this facade only writes the deterministic
    machine-readable subset.
    """
    pairs: dict[str, object] = {
        f"wave_{wave}_repos_in_scope": repos,
        f"wave_{wave}_scope_reconciled_at": _now_iso(at),
    }
    if phase is not None:
        pairs[f"wave_{wave}_phase"] = phase
    return _persist(status_path, pairs)


def kickoff(
    status_path: Path,
    wave: str,
    *,
    merge_model: str | None = None,
    at: str | None = None,
) -> int:
    """Record kickoff: timestamp, active+pointer, and (optionally) merge model.

    Writes ``wave_{W}_kicked_off_at`` (the #423 cross-window filter boundary
    wave_status reads), re-points ``current_wave``, and re-affirms
    ``wave_{W}_active``. When ``merge_model`` is given it is validated through
    :func:`wave_merge_model.validate_merge_model` (the single enum validator) and
    written as ``wave_{W}_merge_model`` in the same atomic upsert.
    """
    pairs: dict[str, object] = {
        "current_wave": _wave_label(wave),
        f"wave_{wave}_active": True,
        f"wave_{wave}_kicked_off_at": _now_iso(at),
    }
    if merge_model is not None:
        wave_merge_model.validate_merge_model(merge_model)
        pairs[f"wave_{wave}_merge_model"] = merge_model
    return _persist(status_path, pairs)


def wrapup(status_path: Path, wave: str, *, at: str | None = None) -> int:
    """Close a wave's lifecycle pointers.

    Writes ``wave_{W}_active=false``, ``wave_{W}_completed_at`` and advances
    ``last_completed_wave``. It deliberately writes NO counter: the three
    counters are owned by ``wave_status.py counters --write`` (the lifecycle-doc
    "Owner of writes" contract — ``/wave-wrapup`` is the authoritative counter
    writer *via* wave_status, ``/wave-retro`` only verifies). Run
    ``lifecycle.py counters {P} {W} --write`` (or ``wave_status.py`` directly)
    for the counter write.
    """
    return _persist(
        status_path,
        {
            f"wave_{wave}_active": False,
            f"wave_{wave}_completed_at": _now_iso(at),
            "last_completed_wave": _wave_label(wave),
        },
    )


def retro(status_path: Path, wave: str, *, at: str | None = None) -> int:
    """Stamp the wave's retro-complete pointer.

    Writes ``wave_{W}_retro_completed_at`` — the key ``/wave-kickoff`` Step 0a
    reads to gate the NEXT wave (the next kickoff's ``scope_reconciled_at`` must
    post-date this). Trust-matrix / feedback-log writes remain owned by the
    ``/wave-retro`` skill (they are narrative, not lifecycle pointers).
    """
    return _persist(
        status_path,
        {f"wave_{wave}_retro_completed_at": _now_iso(at)},
    )


# ============================================================================
# CLI
# ============================================================================


def _cmd_wave_peek(args: argparse.Namespace) -> int:
    print(peek(args.status))
    return 0


def _cmd_wave_allocate(args: argparse.Namespace) -> int:
    return allocate(args.status, args.phase, write=args.write)


def _cmd_wave_start(args: argparse.Namespace) -> int:
    return start(args.status, args.wave, at=args.at)


def _cmd_wave_scope(args: argparse.Namespace) -> int:
    repos = [r.strip() for r in args.repos.split(",") if r.strip()]
    return scope(args.status, args.wave, repos, phase=args.phase, at=args.at)


def _cmd_wave_kickoff(args: argparse.Namespace) -> int:
    return kickoff(args.status, args.wave, merge_model=args.merge_model, at=args.at)


def _cmd_wave_wrapup(args: argparse.Namespace) -> int:
    return wrapup(args.status, args.wave, at=args.at)


def _cmd_wave_retro(args: argparse.Namespace) -> int:
    return retro(args.status, args.wave, at=args.at)


# --- Delegations to the owning modules (thin passthroughs) ------------------


def _cmd_merge_model_get(args: argparse.Namespace) -> int:
    return wave_merge_model.main(["model", args.phase, args.wave, "--status", str(args.status)])


def _cmd_merge_model_set(args: argparse.Namespace) -> int:
    return wave_merge_model.main(
        ["set", args.phase, args.wave, args.model, "--status", str(args.status)]
    )


def _cmd_reachability(args: argparse.Namespace) -> int:
    argv = ["reachability", args.phase, args.wave, "--status", str(args.status)]
    if args.json:
        argv.append("--json")
    return wave_merge_model.main(argv)


def _cmd_counters(args: argparse.Namespace) -> int:
    argv = ["counters", args.phase, args.wave, "--status", str(args.status)]
    if args.write:
        argv.append("--write")
    if args.expect is not None:
        argv.extend(["--expect", str(args.expect)])
    return wave_status.main(argv)


def _cmd_state_show(args: argparse.Namespace) -> int:
    print(json.dumps(_load_status(args.status), indent=2))
    return 0


def _cmd_state_digest(args: argparse.Namespace) -> int:
    return wave_status.main(["digest", "--status", str(args.status)])


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    top = parser.add_subparsers(dest="group", required=True)

    def _status_opt(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--status",
            type=Path,
            default=_DEFAULT_STATUS,
            help="path to cross-repo-status.json (default: repo-root copy)",
        )

    # wave ...
    wave = top.add_parser("wave", help="wave allocator + lifecycle transitions")
    wsub = wave.add_subparsers(dest="command", required=True)

    p = wsub.add_parser("peek", help="print the next wave id (no write; → wave_seq)")
    _status_opt(p)
    p.set_defaults(func=_cmd_wave_peek)

    p = wsub.add_parser("allocate", help="allocate the next wave id for a phase (→ wave_seq)")
    p.add_argument("--phase", type=int, required=True)
    p.add_argument("--write", action="store_true", help="persist global_wave_seq + phase stamps")
    _status_opt(p)
    p.set_defaults(func=_cmd_wave_allocate)

    p = wsub.add_parser("start", help="mark a wave active + point current_wave at it")
    p.add_argument("wave")
    p.add_argument("--at", default=None, help="ISO timestamp override (deterministic)")
    _status_opt(p)
    p.set_defaults(func=_cmd_wave_start)

    p = wsub.add_parser("scope", help="record repos_in_scope + scope_reconciled_at (+phase)")
    p.add_argument("wave")
    p.add_argument("--repos", required=True, help="comma-separated repo list")
    p.add_argument("--phase", type=int, default=None)
    p.add_argument("--at", default=None)
    _status_opt(p)
    p.set_defaults(func=_cmd_wave_scope)

    p = wsub.add_parser("kickoff", help="record kicked_off_at (+ optional validated merge model)")
    p.add_argument("wave")
    p.add_argument(
        "--merge-model",
        dest="merge_model",
        default=None,
        choices=wave_merge_model.MERGE_MODELS,
    )
    p.add_argument("--at", default=None)
    _status_opt(p)
    p.set_defaults(func=_cmd_wave_kickoff)

    p = wsub.add_parser("wrapup", help="close a wave's lifecycle pointers (counters → wave_status)")
    p.add_argument("wave")
    p.add_argument("--at", default=None)
    _status_opt(p)
    p.set_defaults(func=_cmd_wave_wrapup)

    p = wsub.add_parser("retro", help="stamp wave_{W}_retro_completed_at")
    p.add_argument("wave")
    p.add_argument("--at", default=None)
    _status_opt(p)
    p.set_defaults(func=_cmd_wave_retro)

    # merge-model ... (delegates to wave_merge_model)
    mm = top.add_parser("merge-model", help="per-wave merge model get/set (→ wave_merge_model)")
    msub = mm.add_subparsers(dest="command", required=True)
    p = msub.add_parser("get", help="print the declared merge model")
    p.add_argument("phase", help="phase number (P)")
    p.add_argument("wave", help="wave number (W)")
    _status_opt(p)
    p.set_defaults(func=_cmd_merge_model_get)
    p = msub.add_parser("set", help="record the merge model")
    p.add_argument("phase", help="phase number (P)")
    p.add_argument("wave", help="wave number (W)")
    p.add_argument("model", choices=wave_merge_model.MERGE_MODELS)
    _status_opt(p)
    p.set_defaults(func=_cmd_merge_model_set)

    # reachability ... (delegates to wave_merge_model)
    p = top.add_parser("reachability", help="mid-wave reachability check (→ wave_merge_model)")
    p.add_argument("phase", help="phase number (P)")
    p.add_argument("wave", help="wave number (W)")
    p.add_argument("--json", action="store_true", help="emit results as JSON")
    _status_opt(p)
    p.set_defaults(func=_cmd_reachability)

    # counters ... (delegates to wave_status — the authoritative counter writer)
    p = top.add_parser(
        "counters", help="compute (and optionally write) wave counters (→ wave_status)"
    )
    p.add_argument("phase", help="phase number (P)")
    p.add_argument("wave", help="wave number (W)")
    p.add_argument("--write", action="store_true", help="upsert the three canonical counter keys")
    p.add_argument("--expect", type=int, default=None, help="loud-fail if final_pr_count != N")
    _status_opt(p)
    p.set_defaults(func=_cmd_counters)

    # state ...
    st = top.add_parser("state", help="inspect the status file")
    ssub = st.add_subparsers(dest="command", required=True)
    p = ssub.add_parser("show", help="dump the full status file")
    _status_opt(p)
    p.set_defaults(func=_cmd_state_show)
    p = ssub.add_parser("digest", help="emit the current-wave/phase digest (→ wave_status)")
    _status_opt(p)
    p.set_defaults(func=_cmd_state_digest)

    return parser


def main(argv: list[str]) -> int:
    args = _build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
