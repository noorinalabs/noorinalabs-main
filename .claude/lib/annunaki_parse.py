#!/usr/bin/env python3
"""Shared reader for the Annunaki error log — the genuine-error filter (#625).

`/annunaki` (status viewer) and `/annunaki-attack` (processor) both read
`.claude/annunaki/errors.jsonl`. Pre-#625 that file also carried benign
forensic traces (`posttooluse_dispatch`, `pretooluse_diagnostic`) — 76% of the
P4W1 log — and both skills counted them as errors, wildly over-reporting.

The #625 writer-side fix routes those benign traces to a separate
`traces.jsonl`, so a freshly-written `errors.jsonl` is already clean. This
reader is the READER-side guard: it skips blank/corrupt lines AND any record
whose `type` is a benign-trace type, so HISTORICAL logs (mixed pre-#625
content, the `.bak` rotations, a not-yet-cleared live log) are also counted
correctly. Both effects compose: new logs are clean by construction, old logs
are cleaned at read time.

The benign-trace type set is owned by `annunaki_log.TRACE_RECORD_TYPES`; this
module imports it so the writer and reader never drift. If that import fails
(e.g. the lib is vendored without the hook), a local fallback copy keeps the
reader working.

Exit codes (CLI):
    0 — always (this is a read-only summarizer; it never fails the caller)
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterator
from pathlib import Path

# Single source of truth for benign-trace record types lives with the writer
# (annunaki_log.py under .claude/hooks/). Import it so reader and writer stay
# in lock-step; fall back to a local copy if the hooks dir isn't importable.
try:
    _HOOKS_DIR = Path(__file__).resolve().parent.parent / "hooks"
    sys.path.insert(0, str(_HOOKS_DIR))
    from annunaki_log import TRACE_RECORD_TYPES  # type: ignore[import-not-found]
except Exception:  # noqa: BLE001 — vendored-without-hooks fallback
    TRACE_RECORD_TYPES = frozenset({"posttooluse_dispatch", "pretooluse_diagnostic"})


def iter_records(path: Path, *, include_traces: bool = False) -> Iterator[dict]:
    """Yield parsed JSONL records from `path`, skipping blank/corrupt lines.

    By default, records whose `type` is in `TRACE_RECORD_TYPES` are skipped
    (the #625 genuine-error filter). Pass `include_traces=True` to yield every
    parseable record (used by a trace-specific viewer or by tests).

    A missing file yields nothing. Each line is `.strip()`-ed before parsing,
    because the log has historically contained blank lines from manual edits;
    `json.loads("")` would otherwise raise.
    """
    try:
        handle = path.open("r", encoding="utf-8")
    except (FileNotFoundError, OSError):
        return
    with handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue  # skip corrupt lines
            if not isinstance(rec, dict):
                continue
            if not include_traces and rec.get("type") in TRACE_RECORD_TYPES:
                continue
            yield rec


def count_errors(path: Path) -> int:
    """Return the number of genuine error records (benign traces excluded)."""
    return sum(1 for _ in iter_records(path))


def is_trace(record: dict) -> bool:
    """True iff `record` is a benign forensic trace, not a genuine error."""
    return record.get("type") in TRACE_RECORD_TYPES


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "path",
        nargs="?",
        default=".claude/annunaki/errors.jsonl",
        help="path to errors.jsonl (default: .claude/annunaki/errors.jsonl)",
    )
    parser.add_argument(
        "--include-traces",
        action="store_true",
        help="include benign-trace records in the output/count",
    )
    parser.add_argument(
        "--count",
        action="store_true",
        help="print only the genuine-error count and exit",
    )
    args = parser.parse_args(argv)

    path = Path(args.path)
    if args.count:
        print(count_errors(path))
        return 0

    for rec in iter_records(path, include_traces=args.include_traces):
        print(json.dumps(rec, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
