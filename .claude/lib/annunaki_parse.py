#!/usr/bin/env python3
"""Shared reader for the Annunaki error log — the genuine-error filter (#625).

`/annunaki` (status viewer) and `/annunaki-attack` (processor) both read
`.claude/annunaki/errors.jsonl`. Pre-#625 that file also carried benign
forensic traces (`posttooluse_dispatch`, `pretooluse_diagnostic`, and — since
main#1121 ported `post_dispatcher.py`'s logged-swallow into `dispatcher.py` —
`pretooluse_dispatch`) — 76% of the P4W1 log — and both skills counted them as
errors, wildly over-reporting.

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

#729 adds a second reader-side exclusion: records the monitor tagged
`confidence: "low"` — exit-0 stdout-only matches where the trigger word is in
echoed output (displayed source `except ImportError:`, a `gh pr view --json`
body), not a real failure. These are excluded from the genuine-error count but
retained in the log for forensics (pass `include_low_confidence=True`). The
genuine exit-0-failure carve-out (a `git push | tail` masking a REJECTED push)
is tagged `confidence: "high"` by the monitor and so is still counted.

#835 widens the low-confidence class (same reader machinery, no change here) to
include the `category: "pipe-mask-suspect"` records — exit-0 stdout-only matches
with no STRONG masked-failure signal that are NOT positively recognized as
echoed content (e.g. a pytest `FAILED` surfacing through `… | tail` rc-masking,
or benign demo output). The P6W16 retro measured that class at 85% false
positive, so the monitor now tags it `confidence: "low"`; it is excluded from
the count by the existing low-confidence filter and retained for forensics. The
`is_pipe_mask_suspect` helper lets callers triage that sub-class specifically.

#1465 adds a THIRD reader-side exclusion, independent of the confidence tag: a
record whose `error_lines` resolve entirely to this monitor's own log
artifacts (errors.jsonl / traces.jsonl / archive/**) — a `.claude/`-wide sweep
that matched its own history, not a live failure. Going forward the writer
tags these `confidence: "low"` + `category: "self-referential-log-read"`, so
the existing low-confidence filter already excludes NEW records. But records
written BEFORE this fix were mistagged `confidence: "high"` + `category:
"masked-failure"` — the self-referential text routinely contains the very
phrases (a stored "exit status 1", a stored "Traceback ...") the monitor's
STRONG_MASKED_FAILURE signal looks for. `is_self_referential` re-derives the
classification from `error_lines` at READ time so those HISTORICAL
mistagged-high records are excluded too, without rewriting the log.

Exit codes (CLI):
    0 — always (this is a read-only summarizer; it never fails the caller)
"""

from __future__ import annotations

import argparse
import json
import re
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
    TRACE_RECORD_TYPES = frozenset(
        {"posttooluse_dispatch", "pretooluse_diagnostic", "pretooluse_dispatch"}
    )

# Single source of truth for the #1465 self-referential-match predicate lives
# with the writer (annunaki_monitor.py under .claude/hooks/, same dir already
# added to sys.path above for TRACE_RECORD_TYPES). Import it so reader and
# writer classify identically; fall back to a local copy (same logic,
# duplicated deliberately — mirrors the TRACE_RECORD_TYPES fallback above) if
# the hooks dir isn't importable.
try:
    from annunaki_monitor import is_self_referential_match  # type: ignore[import-not-found]
except Exception:  # noqa: BLE001 — vendored-without-hooks fallback
    _SELF_LOG_FILENAMES = ("errors.jsonl", "traces.jsonl")
    _SELF_LOG_ARCHIVE_MARKER = "/annunaki/archive/"
    _RG_PATH_PREFIX = re.compile(r"^([^\s:]+):")

    def _self_referential_log_path(line: str) -> bool:
        match = _RG_PATH_PREFIX.match(line)
        if not match:
            return False
        path = match.group(1)
        if path.endswith(_SELF_LOG_FILENAMES):
            return True
        return _SELF_LOG_ARCHIVE_MARKER in path

    def is_self_referential_match(error_lines: list[str]) -> bool:
        if not error_lines:
            return False
        return all(_self_referential_log_path(line) for line in error_lines)


def iter_records(
    path: Path,
    *,
    include_traces: bool = False,
    include_low_confidence: bool = False,
    include_self_referential: bool = False,
) -> Iterator[dict]:
    """Yield parsed JSONL records from `path`, skipping blank/corrupt lines.

    By default three sub-classes are skipped so the caller sees only genuine
    errors:
      - records whose `type` is in `TRACE_RECORD_TYPES` (the #625 benign-trace
        filter) — pass `include_traces=True` to keep them;
      - records that are self-referential (#1465 — `error_lines` resolve
        entirely to this monitor's own log artifacts, and NOT a hard-failure
        category/nonzero exit_code — see `is_self_referential`) — pass
        `include_self_referential=True` to keep them for forensics. This flag
        is the SOLE gate for a self-referential record: once `is_self_
        referential` says True, `include_low_confidence` plays no further
        part, so `--include-self-referential` alone retrieves BOTH the
        post-fix `confidence="low"` vintage AND the historical mistagged
        `confidence="high"` vintage (a merge-gate finding on the earlier
        design, where the low-confidence vintage still needed
        `include_low_confidence=True` too — surprising and undocumented);
      - records whose `confidence` is "low" (the #729 exit-0 echoed-output
        false-positive class — a trigger word matched in displayed source/body
        at exit 0) — pass `include_low_confidence=True` to keep them for
        forensics. Only applies to a record `is_self_referential` says False;
        a self-referential record's confidence is governed entirely by
        `include_self_referential` above. Records with no `confidence` field
        (legacy logs written before #729) are treated as genuine and kept, so
        historical errors are never silently dropped.

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
            # Self-referential records get their OWN branch, not just an
            # earlier check, because they must NOT also fall through to the
            # low-confidence filter below (Nadia Khoury's #1498 merge-gate
            # BLOCKING finding): `--include-self-referential` alone used to
            # surface only the mistagged-high HISTORICAL vintage, since the
            # post-fix confidence="low" vintage would still be caught by the
            # low-confidence check immediately after. Once a record is
            # positively identified as self-referential, `include_self_
            # referential` is the ONLY flag that governs it -- both vintages,
            # regardless of their stored `confidence` field.
            if is_self_referential(rec):
                if include_self_referential:
                    yield rec
                continue
            if not include_low_confidence and rec.get("confidence") == "low":
                continue
            yield rec


def count_errors(path: Path) -> int:
    """Return the genuine-error count (benign traces, #1465 self-referential
    log-reads, AND #729 low-confidence echoed-output records excluded)."""
    return sum(1 for _ in iter_records(path))


def is_trace(record: dict) -> bool:
    """True iff `record` is a benign forensic trace, not a genuine error."""
    return record.get("type") in TRACE_RECORD_TYPES


# Nadia Khoury's #1498 merge-gate BLOCKING finding: the writer's own
# `_classify_confidence` docstring states the invariant "a real failure
# signal always outranks a log-read attribution" -- nonzero-exit and
# stderr-match are checked BEFORE the self-referential branch, precisely so a
# genuine hard failure is never downgraded just because its output also
# happens to carry self-log text (see `test_nonzero_exit_with_self_log_
# content_still_logged_high` in test_annunaki_monitor.py). `is_self_referential`
# re-derived its verdict from `error_lines` ALONE and ignored `exit_code`/
# `category` entirely -- so a record the writer correctly stamped
# `confidence="high"`/`category="nonzero-exit"` was reclassified
# self-referential at read time and silently dropped from the genuine count.
# That is the writer's precedence being undone one layer down: the two-
# boundary-drift shape #1465 itself exists to fix, recurring in the fix.
#
# The reader must CONSUME the writer's precedence, not re-derive it from a
# narrower signal. These are the two writer-side categories that already
# outrank self-reference in `_classify_confidence` (checked first, before
# STRONG_MASKED_FAILURE / self-referential / echoed-content / pipe-mask-
# suspect); a record carrying a category in HARD_FAILURE_CATEGORIES is never
# self-referential regardless of its `error_lines` shape, and a nonzero
# `exit_code` is the same signal for a record with no `category` field at
# all (defensive -- the writer always sets `category` for command-failure
# records, but the guard should not rely on that being universally true
# across every past/future record shape).
HARD_FAILURE_CATEGORIES = frozenset({"nonzero-exit", "stderr-match"})


def is_self_referential(record: dict) -> bool:
    """True iff `record`'s `error_lines` resolve entirely to this monitor's
    own log artifacts (#1465) — a `.claude/`-wide sweep re-matching text
    stored inside errors.jsonl/traces.jsonl/archive/**, not a live failure.

    Independent of the stored `confidence` field deliberately (see below for
    the exception): records written AFTER the writer-side #1465 fix are
    tagged `confidence: "low"` + `category: "self-referential-log-read"` and
    would already be caught by `is_low_confidence`, but records written
    BEFORE the fix were mistagged `confidence: "high"` + `category:
    "masked-failure"` (the self-referential text itself routinely contains
    the STRONG masked-failure phrases the monitor looks for). Re-deriving the
    classification from `error_lines` at read time excludes both vintages
    from the genuine count without rewriting the historical log.

    NOT independent of `category`/`exit_code`, however: a record in
    `HARD_FAILURE_CATEGORIES` (`nonzero-exit`, `stderr-match`) — or, as a
    defensive fallback for a record with no `category` at all, one with a
    nonzero `exit_code` — is never self-referential, full stop, regardless of
    what its `error_lines` contain. This consumes the writer's own
    precedence (`_classify_confidence` checks these two categories before
    the self-referential branch) instead of re-deriving a narrower judgement
    that could contradict it.
    """
    if record.get("category") in HARD_FAILURE_CATEGORIES:
        return False
    if (record.get("exit_code") or 0) != 0:
        return False
    error_lines = record.get("error_lines")
    if not isinstance(error_lines, list):
        return False
    return is_self_referential_match(error_lines)


def is_low_confidence(record: dict) -> bool:
    """True iff `record` is a low-confidence class (#729 echoed-output, #835
    pipe-mask-suspect, or a POST-#1465-fix self-referential-log-read record —
    the writer tags those `confidence: "low"` too).

    A record self-referential per `is_self_referential` but written BEFORE
    the #1465 fix is NOT caught here (it was mistagged `confidence: "high"`)
    — use `is_self_referential` for that vintage; `iter_records` checks both.

    These are retained in the log for forensics but excluded from the
    genuine-error count by `iter_records`/`count_errors`.
    """
    return record.get("confidence") == "low"


def is_pipe_mask_suspect(record: dict) -> bool:
    """True iff `record` is the #835 exit-0 pipe-mask-suspect class.

    A subset of the low-confidence records: an exit-0 stdout-only match with no
    STRONG masked-failure signal that the monitor could not positively classify
    as echoed content (e.g. a pytest `FAILED` surfacing through `… | tail`
    rc-masking, or benign demo output). Excluded from the genuine-error count
    like all low-confidence records; this helper lets `/annunaki-attack` triage
    the suspect sub-class specifically (e.g. batch-dismiss, or promote a true
    masked failure that slipped through).
    """
    return record.get("category") == "pipe-mask-suspect"


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
        "--include-low-confidence",
        action="store_true",
        help="include #729 low-confidence echoed-output records in the output",
    )
    parser.add_argument(
        "--include-self-referential",
        action="store_true",
        help="include #1465 self-referential-log-read records in the output",
    )
    parser.add_argument(
        "--count",
        action="store_true",
        help="print only the genuine-error count and exit",
    )
    parser.add_argument(
        "--count-self-referential",
        action="store_true",
        help=(
            "print only the count of records classified self-referential (#1465) "
            "-- both post-fix (confidence=low) and mistagged historical "
            "(confidence=high) vintages -- and exit"
        ),
    )
    args = parser.parse_args(argv)

    path = Path(args.path)
    if args.count:
        print(count_errors(path))
        return 0
    if args.count_self_referential:
        all_records = iter_records(
            path,
            include_traces=True,
            include_low_confidence=True,
            include_self_referential=True,
        )
        print(sum(1 for rec in all_records if is_self_referential(rec)))
        return 0

    for rec in iter_records(
        path,
        include_traces=args.include_traces,
        include_low_confidence=args.include_low_confidence,
        include_self_referential=args.include_self_referential,
    ):
        print(json.dumps(rec, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
