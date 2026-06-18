#!/usr/bin/env python3
"""Detect + reset stale cross-phase ``wave_{M}_*`` keys in cross-repo-status.json.

Backs ``/wave-start`` § 5a. A wave number reused across phases (e.g. P4W4 ↔
P5W4) leaves the *prior* phase's ``wave_{M}_*`` operational keys in the file
under identical names (the bare-key "overwrite convention" — see
``upsert_status_keys`` docstring / main#611). Those values bleed into the new
phase's wave M unless explicitly cleared. This module is the mechanical,
test-backed form of that cleanup; it replaces the three defective hand-rolled
bash probes that § 5a used to inline (main#683):

Defect 1 — phase guard can never be true for a later same-number wave.
  The old guard inferred "wave_{M}_* is stale" from ``current_phase != {P}``.
  But ``current_phase`` tracks the *latest* phase, not the phase that wrote the
  stale ``wave_{M}_*`` keys — it was advanced to {P} back at this phase's W1
  kickoff, so for an intra-phase same-number reuse the guard is structurally
  always false. Fix: detect staleness from a **phase stamp carried INSIDE the
  wave's own keys** — ``wave_{M}_scope.phase`` (written by /wave-scope) and the
  ``phase-{X}`` segment of ``wave_{M}_branches.branch`` (written by
  /wave-kickoff). If any such stamp differs from the phase being started, the
  keys are stale. ``current_phase`` is never consulted.

Defect 2 — detection key-name mismatch.
  The old probe looked for ``wave_{M}_completed_at`` / ``wave_{M}_wrapped_up_at``
  while /wave-wrapup actually writes ``wave_{M}_wrapup_completed_at`` — so the
  probe found nothing and ``HAS_PRIOR`` was always ``no``. Moot here: detection
  no longer keys off any lifecycle-marker name; it keys off the phase stamps
  above, which exist regardless of how far the prior wave progressed.

Defect 3 — incomplete RESET_KEYS list.
  The old enumerated 12-key list missed ≥10 keys a wave actually writes
  (``wave_{M}_active``, ``_branches``, ``_carry_forward``, ``_scope``,
  ``_repos_in_scope``, ``_meta_issue``, …). ``wave_{M}_branches`` was the
  dangerous omission: a stale ``deployments/phase-4/wave-4`` ref misleads
  /wave-kickoff Step 1 into thinking the phase-5 branches already exist. Fix:
  reset is **prefix-complete by construction** — every top-level key matching
  ``wave_{M}_`` is cleared, so the surface can never drift out of sync with what
  the wave skills write.

Why REMOVE and not set-to-null: the bare-key overwrite convention (main#611)
removes the prior phase's ``wave_{M}_*`` keys before the new phase writes its
own; setting-to-null would leave a pile of ``null`` noise. Removal reuses
``upsert_status_keys.remove_top_level_key`` so the file's mixed compact-inline /
pretty-indented shape is preserved and the write is JSON-validated before AND
after (no 500-line cosmetic diff).

CLI:
  wave_key_reset.py <status_path> <wave> <phase>            # dry-run (detect)
  wave_key_reset.py <status_path> <wave> <phase> --apply    # remove stale keys

Dry-run prints the detection verdict and the keys that WOULD be reset, exit 0.
``--apply`` removes them (only when stale) and exits non-zero on any write
failure. Both are no-ops (exit 0, "not stale") when the wave's own phase stamps
match {P} — i.e. first wave of a phase, or /wave-start re-run within the same
phase (idempotent).
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

# `deployments/phase-{X}/wave-{M}` — the branch ref /wave-kickoff stamps into
# wave_{M}_branches.branch. The phase segment is a second, independent phase
# stamp (corroborates wave_{M}_scope.phase).
_BRANCH_PHASE_RE = re.compile(r"phase-(\d+)/wave-\d+")


def branch_phase(branch: str) -> int | None:
    """Parse the phase number out of a ``deployments/phase-{X}/wave-{M}`` ref.

    Returns ``None`` for any string that does not carry the phase-{X} segment.
    """
    if not isinstance(branch, str):
        return None
    m = _BRANCH_PHASE_RE.search(branch)
    return int(m.group(1)) if m else None


def stamped_phases(status: dict, wave: int) -> set[int]:
    """Collect every phase number stamped INSIDE this wave's own keys.

    Two independent stamps, both written by the wave skills for the phase that
    owns the keys (never the global ``current_phase``):

      * ``wave_{M}_scope.phase`` — written by /wave-scope.
      * the ``phase-{X}`` segment of ``wave_{M}_branches.branch`` — written by
        /wave-kickoff Step 1.

    Returns the set of distinct phase ints found (empty if the wave has no
    stamped keys yet — a never-before-used wave number, nothing to reset).
    """
    phases: set[int] = set()

    scope = status.get(f"wave_{wave}_scope")
    if isinstance(scope, dict):
        p = scope.get("phase")
        if isinstance(p, int):
            phases.add(p)

    branches = status.get(f"wave_{wave}_branches")
    if isinstance(branches, dict):
        bp = branch_phase(branches.get("branch", ""))
        if bp is not None:
            phases.add(bp)

    return phases


def is_stale_reuse(status: dict, wave: int, phase: int) -> tuple[bool, set[int]]:
    """Return ``(stale, prior_phases)`` for wave ``M`` about to start in ``P``.

    Stale iff the wave carries a phase stamp belonging to a DIFFERENT phase than
    the one starting. ``prior_phases`` is the set of stamped phases that differ
    from ``phase`` (the evidence). When no stamp exists, or every stamp already
    equals ``phase``, the result is ``(False, set())`` — nothing to reset.
    """
    stamps = stamped_phases(status, wave)
    prior = {p for p in stamps if p != phase}
    return (bool(prior), prior)


def stale_wave_keys(status: dict, wave: int) -> list[str]:
    """Every top-level key matching ``wave_{M}_`` — the complete reset surface.

    Prefix-complete by construction (Defect 3): the trailing underscore makes
    ``wave_4_`` match ``wave_4_active`` but never ``wave_42_active``. Returned in
    sorted order for a stable, auditable reset log.
    """
    prefix = f"wave_{wave}_"
    return sorted(k for k in status if k.startswith(prefix))


def _apply_reset(status_path: Path, keys: list[str]) -> int:
    """Remove ``keys`` from the file via the shared upsert helper.

    Reuses ``upsert_status_keys._run_remove`` so the compact-inline file shape
    is preserved and the rewrite is JSON-validated before AND after. Importing
    lazily keeps the detection-only (dry-run) path free of the dependency.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from upsert_status_keys import _run_remove

    return _run_remove(status_path, keys)


def _cmd(args: argparse.Namespace) -> int:
    status = json.loads(args.status.read_text())
    stale, prior = is_stale_reuse(status, args.wave, args.phase)

    if not stale:
        stamps = stamped_phases(status, args.wave)
        reason = (
            f"phase stamp(s) {sorted(stamps)} already match {args.phase}"
            if stamps
            else f"wave-{args.wave} carries no phase stamp (never used before)"
        )
        print(f"not stale: {reason}; nothing to reset.")
        return 0

    keys = stale_wave_keys(status, args.wave)
    print(
        f"stale cross-phase reuse: wave-{args.wave} carries phase stamp(s) "
        f"{sorted(prior)} but phase-{args.phase} is starting."
    )
    print(f"{len(keys)} stale wave_{args.wave}_* key(s) to reset:")
    for k in keys:
        print(f"  {k}")

    if not args.apply:
        print("(dry-run — pass --apply to remove these keys)")
        return 0

    return _apply_reset(args.status, keys)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "status",
        type=Path,
        nargs="?",
        default=_DEFAULT_STATUS,
        help="path to cross-repo-status.json (default: repo-root copy)",
    )
    parser.add_argument("wave", type=int, help="wave number (M) being started")
    parser.add_argument("phase", type=int, help="phase number (P) being started")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="remove the stale keys (default is a dry-run detection report)",
    )
    parser.set_defaults(func=_cmd)
    return parser


def main(argv: list[str]) -> int:
    args = _build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
