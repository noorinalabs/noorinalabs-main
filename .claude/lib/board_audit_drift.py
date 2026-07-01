#!/usr/bin/env python3
"""Wave-field drift classification for ``/board-audit`` Step 4 (main#902).

Given the in-memory join of one board item per row —

    url  \t  current-Wave-field-value  \t  expected-Wave-option  \t  content-state

— classify each row into exactly one bucket:

    drift      Actionable: a mutation WILL change board state (sync to the
               expected option, or ``(clear)`` a stale field). Emitted to stdout.
    noop       No wave label AND the Wave field is already ``(unset)`` — the
               apply step's clear mutation would be a no-op. Counted, not emitted.
    in_sync     Wave label present AND the Wave field already matches it — nothing
               to do. Counted, not emitted.
    skip       PROTECTED (main#902): a CLOSED/MERGED item that still carries a
               valid Wave option which the OPEN-only label map (Step 1 fetches
               ``--state open``) cannot re-derive. Clearing it would erase correct
               historical Wave attribution. Counted, not emitted.

Why the guard exists (main#902)
===============================
``/board-audit`` Step 1 fetches labels for OPEN issues only, then Step 4 joins
that open-only ``url -> expected-option`` map against ALL project-board items
(open AND closed). A CLOSED issue that legitimately retains its wave label falls
out of the open-only map, so its expected option resolves to ``(unset)`` and the
naive rule (``field populated but expected unset -> clear``) falsely flags it as
drift-to-clear. Observed P7W20: 6 closed issues with correct Wave attribution (a
closed ``p3-wave-10``, several closed ``wave-19``) flagged ``<W..> -> (clear)``.
Clearing them erases correct history.

The guard uses the ``content.state`` already present in the Step-2 board
response — no extra network fetch, and no dependency on completeness of a
(potentially truncated) closed-issue label fetch. The genuine drift signal is
fully preserved: an OPEN item whose Wave field mismatches its label is always
flagged (the guard only shields the ``(clear)`` branch, and only for non-OPEN
items whose current field value is a valid wave option).

Wave-option grammar (#810)
==========================
    wave-{X}       ->  W{X}       (e.g. wave-19    -> W19)
    p{N}-wave-{M}  ->  P{N}W{M}   (e.g. p3-wave-10 -> P3W10)
    wave-x         ->  WX

CLI
===
::

    python3 board_audit_drift.py [JOIN_TSV]

Reads the 4-column join TSV from ``JOIN_TSV`` (or stdin when omitted). Writes
actionable DRIFT rows (``url \t current \t target``) to stdout and a summary
line ``noop=<n> protected=<n> in_sync=<n> drift=<n>`` to stderr.

Provenance: issue main#902 (Option 1 — the state guard). P7W22.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass

UNSET = "(unset)"
CLEAR = "(clear)"

# A valid project-2 Wave single-select option name (#810 grammar):
#   W{X}  (global) | P{N}W{M} (legacy grandfathered) | WX (placeholder "Wave (TBD)")
_WAVE_OPTION_RE = re.compile(r"^(?:W\d+|P\d+W\d+|WX)$")


def is_valid_wave_option(value: str) -> bool:
    """True iff *value* is a valid Wave single-select option name (#810).

    Recognises both the new phase-agnostic ``W{X}`` form and the grandfathered
    ``P{N}W{M}`` form, plus the ``WX`` placeholder. ``(unset)``/``(clear)``
    sentinels and empty strings are not valid options.
    """
    return _WAVE_OPTION_RE.match(value) is not None


def is_open(state: str) -> bool:
    """True iff *state* denotes an OPEN issue/PR (case-insensitive).

    Anything else — ``CLOSED`` (issues + PRs), ``MERGED`` (PRs), or a missing
    state — is treated as non-open and thus eligible for the main#902 protection
    of a valid retained Wave option.
    """
    return state.strip().upper() == "OPEN"


@dataclass(frozen=True)
class Classification:
    """Bucket + optional target for one join row.

    ``bucket`` is one of ``drift`` | ``noop`` | ``in_sync`` | ``skip``. ``target``
    is the Wave option to sync to (or ``(clear)``) and is set only for ``drift``.
    """

    bucket: str
    target: str | None = None


def classify(current: str, expected: str, state: str) -> Classification:
    """Classify one board item into its drift bucket.

    Args:
        current:  the board's current Wave-field value, or ``(unset)``.
        expected: the expected Wave option from the OPEN-issue label map, or
                  ``(unset)`` when the issue is absent from that map (no wave
                  label, or a closed issue whose label wasn't fetched).
        state:    the board item's ``content.state`` (``OPEN``/``CLOSED``/
                  ``MERGED``); may be empty when unknown.

    Returns:
        A ``Classification``. Only the ``drift`` bucket carries a ``target``.
    """
    if expected != UNSET:
        # Issue carries a (fetched, i.e. open) wave label — the field must match.
        # State is irrelevant here: an OPEN mismatch is always genuine drift.
        if current != expected:
            return Classification("drift", expected)
        return Classification("in_sync")

    # expected == (unset): the item is not in the OPEN-issue wave-label map.
    if current == UNSET:
        # No wave label AND field already clear — desired state already holds.
        return Classification("noop")

    # Field is populated but no wave label was found in the open-issue map.
    if not is_open(state) and is_valid_wave_option(current):
        # main#902: a CLOSED/MERGED item retaining a valid Wave option. The
        # open-only map can't confirm its label, so clearing would risk erasing
        # correct historical attribution — protect it instead of flagging drift.
        return Classification("skip")

    # OPEN item (or a non-open item with a non-option field value): a populated
    # field with no wave label is stale and should be cleared — genuine drift.
    return Classification("drift", CLEAR)


@dataclass
class Summary:
    """Aggregate bucket counts across all classified rows."""

    drift: int = 0
    noop: int = 0
    in_sync: int = 0
    protected: int = 0  # the "skip" bucket, named for the operator-facing report

    def summary_line(self) -> str:
        """The stderr summary line the skill's Step 4 parses for its counts."""
        return (
            f"noop={self.noop} protected={self.protected} in_sync={self.in_sync} drift={self.drift}"
        )


def classify_rows(lines: list[str]) -> tuple[list[str], Summary]:
    """Classify TSV *lines* into (emitted DRIFT rows, aggregate Summary).

    Each input line is ``url \t current \t expected \t state`` (a missing 4th
    ``state`` column is tolerated and treated as empty → non-open). Blank lines
    are skipped. Returned DRIFT rows are ``url \t current \t target`` strings.
    """
    drift_rows: list[str] = []
    summary = Summary()
    for raw in lines:
        line = raw.rstrip("\n")
        if not line.strip():
            continue
        parts = line.split("\t")
        url = parts[0] if len(parts) > 0 else ""
        current = parts[1] if len(parts) > 1 else UNSET
        expected = parts[2] if len(parts) > 2 else UNSET
        state = parts[3] if len(parts) > 3 else ""
        if not url:
            continue
        result = classify(current, expected, state)
        if result.bucket == "drift":
            summary.drift += 1
            drift_rows.append(f"{url}\t{current}\t{result.target}")
        elif result.bucket == "noop":
            summary.noop += 1
        elif result.bucket == "in_sync":
            summary.in_sync += 1
        elif result.bucket == "skip":
            summary.protected += 1
    return drift_rows, summary


def main(argv: list[str] | None = None) -> int:
    """CLI: read the join TSV (file arg or stdin), emit DRIFT rows + summary.

    Exit code is always 0 (this is a pure classifier — the caller decides what
    to do with the drift). DRIFT rows go to stdout; the ``noop=.. protected=..
    in_sync=.. drift=..`` summary goes to stderr.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] not in ("-", "/dev/stdin"):
        with open(args[0], encoding="utf-8") as fh:
            lines = fh.readlines()
    else:
        lines = sys.stdin.readlines()

    drift_rows, summary = classify_rows(lines)
    for row in drift_rows:
        print(row)
    print(summary.summary_line(), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
