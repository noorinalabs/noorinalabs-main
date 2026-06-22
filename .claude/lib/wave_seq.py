#!/usr/bin/env python3
"""Global monotonic wave-id allocator for cross-repo-status.json (main#804).

Durable fix for the cross-phase wave-key collision. The operational keys in
``cross-repo-status.json`` are bare ``wave_{X}_*`` (e.g. ``wave_2_scope``,
``wave_2_final_pr_count``). Pre-#804 the ``X`` was a **per-phase** wave number
that RESET to 1 at every phase boundary, so a same-numbered wave in a later
phase (P5W2 ↔ P6W2) wrote to the SAME key — a prior phase's values masquerading
as the current wave's. ``/wave-start`` § 5a tried to paper over this with a
per-phase *reset* of the stale keys (main#683/#699), but that only cleaned up
after the fact and the collision recurred (P6W1).

Design B (owner-directed, 2026-06-21) removes the collision *class* instead of
resetting after it bites: a wave id is a single **never-resetting monotonic
counter**. P6's first wave is global ``wave_16``, not ``wave_1``. A number is
never reused, so two same-ordinal waves in different phases get DISTINCT ids and
therefore DISTINCT keys — collisions are impossible by construction, and the
§ 5a reset is retired entirely (nothing to reset).

The **phase** becomes a *derived display attribute* of the wave, never part of
the key:
  * ``wave_{X}_phase``         — the phase this global wave belongs to.
  * ``wave_{X}_phase_ordinal`` — its 1-based position within that phase (the
                                 human-friendly "Phase 6, Wave 2" framing).

The counter itself is the top-level scalar ``global_wave_seq`` = the highest
global id ever allocated. ``next = global_wave_seq + 1``.

Migration (grandfather — see main#804 PR)
-----------------------------------------
In-flight P6 waves keep their existing bare keys (``wave_1_*`` = P6W1,
``wave_2_*`` = P6W2) so an active wrapup is not disrupted by a rename. The
counter is seeded above ALL historical per-phase wave numbers (``HISTORICAL_FLOOR
= 15``) so the FIRST newly-allocated global wave is ``wave_16`` — which can never
collide with any historical ``wave_1``..``wave_9``. Prior-phase graveyard keys
are preserved (git history + the phase docs hold them; they are inert because no
future wave is ever numbered ≤ 15).

CLI:
  wave_seq.py peek     <status_path>
      Print the next global wave id that WOULD be allocated (no write).
  wave_seq.py allocate <status_path> --phase P [--write]
      Allocate the next global wave id for phase P. ``--write`` persists the
      incremented ``global_wave_seq`` AND stamps ``wave_{X}_phase`` +
      ``wave_{X}_phase_ordinal`` (auto-computed: 1 + waves already in phase P).
      Without ``--write`` it is a dry-run that only prints the id + ordinal.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Repo root = two parents above .claude/lib/ (lib -> .claude -> root). Resolved
# from this file so the default status path is correct from any cwd or worktree.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_STATUS = _REPO_ROOT / "cross-repo-status.json"

# The counter is seeded at least this high at first allocation, so the first
# global wave (HISTORICAL_FLOOR + 1 = 16) sits ABOVE every per-phase wave number
# the project ever used (the historical max was 9). This guarantees the first
# allocated global id can never textually collide with a grandfathered key.
HISTORICAL_FLOOR = 15

# Top-level `wave_{X}_...` key (bare, never phase-prefixed). The trailing `_`
# makes `wave_4_` match `wave_4_active` but never `wave_42_active`.
_WAVE_KEY_RE = re.compile(r"^wave_(\d+)_")


def existing_wave_numbers(status: dict) -> set[int]:
    """Every wave id that appears in a top-level ``wave_{X}_*`` key name."""
    out: set[int] = set()
    for key in status:
        m = _WAVE_KEY_RE.match(key)
        if m:
            out.add(int(m.group(1)))
    return out


def seed_value(status: dict) -> int:
    """The counter's seed when ``global_wave_seq`` is absent.

    ``max(HISTORICAL_FLOOR, highest existing wave id)`` — so the first allocated
    id clears both the historical floor AND any wave already recorded (e.g. a
    grandfathered ``wave_2`` or a hand-set ``wave_20``).
    """
    return max([HISTORICAL_FLOOR, *existing_wave_numbers(status)])


def current_seq(status: dict) -> int:
    """The highest global id allocated so far.

    Reads the explicit ``global_wave_seq`` scalar when present; otherwise
    derives the seed (self-seeding migration — no pre-edit of the live file is
    required for the counter to come online).
    """
    val = status.get("global_wave_seq")
    if isinstance(val, int):
        return max(val, seed_value(status))
    return seed_value(status)


def next_global_wave(status: dict) -> int:
    """The next global wave id to allocate (monotonic; never reused)."""
    return current_seq(status) + 1


def phase_of(status: dict, wave: int) -> int | None:
    """The phase a recorded global wave belongs to, or None if unstamped.

    Reads the derived display stamp ``wave_{X}_phase``; falls back to
    ``wave_{X}_scope.phase`` (the in-scope copy /wave-scope writes).
    """
    direct = status.get(f"wave_{wave}_phase")
    if isinstance(direct, int):
        return direct
    scope = status.get(f"wave_{wave}_scope")
    if isinstance(scope, dict) and isinstance(scope.get("phase"), int):
        return scope["phase"]
    return None


def phase_ordinal(status: dict, phase: int) -> int:
    """1-based position of the wave being allocated WITHIN ``phase``.

    Counts the global waves already stamped to ``phase`` and adds one. So the
    first wave of phase 6 is ordinal 1 regardless of its global id (16).
    """
    count = sum(1 for w in existing_wave_numbers(status) if phase_of(status, w) == phase)
    return count + 1


def _load(status_path: Path) -> dict:
    return json.loads(status_path.read_text())


def _cmd_peek(args: argparse.Namespace) -> int:
    status = _load(args.status)
    print(next_global_wave(status))
    return 0


def _cmd_allocate(args: argparse.Namespace) -> int:
    status = _load(args.status)
    wave_id = next_global_wave(status)
    ordinal = phase_ordinal(status, args.phase)

    print(f"global wave id: {wave_id}")
    print(f"phase: {args.phase}")
    print(f"phase ordinal: {ordinal}  (display: Phase {args.phase}, Wave {ordinal})")

    if not args.write:
        print("(dry-run — pass --write to persist global_wave_seq + phase stamps)")
        return 0

    # Persist via the shared upsert helper so the file's compact-inline shape is
    # preserved and the rewrite is JSON-validated before AND after (main#332/#456).
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from upsert_status_keys import main as upsert_main

    return upsert_main(
        [
            "wave_seq",
            str(args.status),
            f"global_wave_seq={wave_id}",
            f"wave_{wave_id}_phase={args.phase}",
            f"wave_{wave_id}_phase_ordinal={ordinal}",
        ]
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_peek = sub.add_parser("peek", help="print the next global wave id (no write)")
    p_peek.add_argument("status", type=Path, nargs="?", default=_DEFAULT_STATUS)
    p_peek.set_defaults(func=_cmd_peek)

    p_alloc = sub.add_parser("allocate", help="allocate the next global wave id for a phase")
    p_alloc.add_argument("status", type=Path, nargs="?", default=_DEFAULT_STATUS)
    p_alloc.add_argument("--phase", type=int, required=True, help="phase the new wave belongs to")
    p_alloc.add_argument(
        "--write",
        action="store_true",
        help="persist global_wave_seq + wave_{X}_phase + wave_{X}_phase_ordinal",
    )
    p_alloc.set_defaults(func=_cmd_allocate)
    return parser


def main(argv: list[str]) -> int:
    args = _build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
