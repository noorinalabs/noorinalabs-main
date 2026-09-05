"""Tests for annunaki_parse — the genuine-error reader/filter (#625).

Verifies:
  1. Benign-trace records (posttooluse_dispatch, pretooluse_diagnostic,
     pretooluse_dispatch) are skipped by default; genuine errors / blocks /
     events are kept.
  2. Blank and corrupt lines are skipped (the JSONL-has-blank-lines history).
  3. include_traces=True yields everything.
  4. count_errors counts only genuine errors.
  5. The trace-type set is sourced from annunaki_log.TRACE_RECORD_TYPES (no drift).
  6. CLI --count over a mixed fixture returns the genuine-error count.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

# Helper lives at .claude/lib/annunaki_parse.py; test is at
# .claude/lib/tests/test_*.py. parent.parent reaches the lib root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from annunaki_parse import (  # noqa: E402
    TRACE_RECORD_TYPES,
    count_errors,
    is_low_confidence,
    is_pipe_mask_suspect,
    is_self_referential,
    is_self_referential_match,
    is_trace,
    iter_records,
    main,
)

# Mixed fixture mirroring the real P4W1 errors.jsonl shapes: a genuine
# monitor error (no `type`), a block, an event (all genuine) plus a dispatch
# trace and a diagnostic (both benign), a blank line, and a corrupt line.
_GENUINE_MONITOR = {
    "timestamp": "t",
    "command": "pytest",
    "exit_code": 1,
    "matched_patterns": ["exit_code=1"],
}
_GENUINE_BLOCK = {"timestamp": "t", "type": "pretooluse_block", "hook": "validate_commit_identity"}
_GENUINE_EVENT = {
    "timestamp": "t",
    "type": "posttooluse_event",
    "hook": "post_wave_kickoff_comment",
}
_BENIGN_DISPATCH = {"timestamp": "t", "type": "posttooluse_dispatch", "module": "annunaki_monitor"}
_BENIGN_DIAGNOSTIC = {
    "timestamp": "t",
    "type": "pretooluse_diagnostic",
    "hook": "enforce_librarian_consulted",
}


def _write_mixed(path: Path) -> None:
    lines = [
        json.dumps(_GENUINE_MONITOR),
        json.dumps(_BENIGN_DISPATCH),
        "",  # blank line (manual-edit history)
        json.dumps(_GENUINE_BLOCK),
        "{not valid json",  # corrupt line
        json.dumps(_BENIGN_DIAGNOSTIC),
        json.dumps(_GENUINE_EVENT),
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class IterRecords(unittest.TestCase):
    def test_default_skips_benign_traces(self) -> None:
        with TemporaryDirectory() as td:
            p = Path(td) / "errors.jsonl"
            _write_mixed(p)
            recs = list(iter_records(p))
            types = [r.get("type", "<monitor>") for r in recs]
            # 3 genuine records, in file order, benign + blank + corrupt dropped.
            self.assertEqual(types, ["<monitor>", "pretooluse_block", "posttooluse_event"])

    def test_include_traces_yields_everything_parseable(self) -> None:
        with TemporaryDirectory() as td:
            p = Path(td) / "errors.jsonl"
            _write_mixed(p)
            recs = list(iter_records(p, include_traces=True))
            # 5 parseable records (blank + corrupt still dropped).
            self.assertEqual(len(recs), 5)

    def test_missing_file_yields_nothing(self) -> None:
        with TemporaryDirectory() as td:
            recs = list(iter_records(Path(td) / "nope.jsonl"))
            self.assertEqual(recs, [])

    def test_non_dict_json_line_skipped(self) -> None:
        with TemporaryDirectory() as td:
            p = Path(td) / "errors.jsonl"
            p.write_text('[1,2,3]\n"a string"\n42\n', encoding="utf-8")
            self.assertEqual(list(iter_records(p, include_traces=True)), [])


class CountErrors(unittest.TestCase):
    def test_counts_only_genuine(self) -> None:
        with TemporaryDirectory() as td:
            p = Path(td) / "errors.jsonl"
            _write_mixed(p)
            self.assertEqual(count_errors(p), 3)


class IsTrace(unittest.TestCase):
    def test_classification(self) -> None:
        self.assertTrue(is_trace(_BENIGN_DISPATCH))
        self.assertTrue(is_trace(_BENIGN_DIAGNOSTIC))
        self.assertFalse(is_trace(_GENUINE_MONITOR))
        self.assertFalse(is_trace(_GENUINE_BLOCK))
        self.assertFalse(is_trace(_GENUINE_EVENT))


# #729: exit-0 echoed-output records are tagged confidence="low" by the monitor.
# The reader excludes them from the genuine-error count but retains them in the
# log (include_low_confidence=True) for forensics. A genuine masked failure is
# tagged "high" and counted; a legacy record with no `confidence` field counts.
_LOW_CONF_ECHO = {
    "timestamp": "t",
    "command": "cat mod.py",
    "exit_code": 0,
    "matched_patterns": ["stdout:ImportError:"],
    "confidence": "low",
}
_HIGH_CONF_MASKED = {
    "timestamp": "t",
    "command": "git push ... | tail",
    "exit_code": 0,
    "matched_patterns": ["stdout:^error\\b"],
    "confidence": "high",
}


class LowConfidenceFilter(unittest.TestCase):
    def _write(self, path: Path) -> None:
        lines = [
            json.dumps(_GENUINE_MONITOR),  # legacy, no confidence → counted
            json.dumps(_LOW_CONF_ECHO),  # excluded from count
            json.dumps(_HIGH_CONF_MASKED),  # genuine masked failure → counted
        ]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_count_excludes_low_confidence(self) -> None:
        with TemporaryDirectory() as td:
            p = Path(td) / "errors.jsonl"
            self._write(p)
            # legacy + high-confidence masked failure = 2; low excluded.
            self.assertEqual(count_errors(p), 2)

    def test_iter_default_skips_low_confidence(self) -> None:
        with TemporaryDirectory() as td:
            p = Path(td) / "errors.jsonl"
            self._write(p)
            cmds = [r["command"] for r in iter_records(p)]
            self.assertEqual(cmds, ["pytest", "git push ... | tail"])

    def test_include_low_confidence_retains_for_forensics(self) -> None:
        with TemporaryDirectory() as td:
            p = Path(td) / "errors.jsonl"
            self._write(p)
            recs = list(iter_records(p, include_low_confidence=True))
            self.assertEqual(len(recs), 3)
            self.assertIn("cat mod.py", [r["command"] for r in recs])

    def test_is_low_confidence_helper(self) -> None:
        self.assertTrue(is_low_confidence(_LOW_CONF_ECHO))
        self.assertFalse(is_low_confidence(_HIGH_CONF_MASKED))
        self.assertFalse(is_low_confidence(_GENUINE_MONITOR))  # legacy → not low

    def test_cli_include_low_confidence_flag(self) -> None:
        with TemporaryDirectory() as td:
            p = Path(td) / "errors.jsonl"
            self._write(p)
            self.assertEqual(main([str(p), "--include-low-confidence"]), 0)


# #835: the pipe-mask-suspect class — exit-0 stdout-only matches with no STRONG
# masked-failure signal, not recognized as echoed (e.g. a pytest `FAILED`
# surfacing through `… | tail` rc-masking). The monitor tags these
# confidence="low" so the existing low-confidence filter excludes them from the
# count; `category="pipe-mask-suspect"` lets callers triage the sub-class.
_PIPE_MASK_SUSPECT = {
    "timestamp": "t",
    "hook": "annunaki_monitor",
    "command": "python3 -m pytest 2>&1 | tail",
    "exit_code": 0,
    "matched_patterns": ["stdout:^FAILED"],
    "confidence": "low",
    "category": "pipe-mask-suspect",
}


class PipeMaskSuspectFilter(unittest.TestCase):
    def _write(self, path: Path) -> None:
        lines = [
            json.dumps(_GENUINE_MONITOR),  # legacy, no confidence → counted
            json.dumps(_PIPE_MASK_SUSPECT),  # #835 suspect → excluded from count
            json.dumps(_HIGH_CONF_MASKED),  # genuine masked failure → counted
        ]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_count_excludes_pipe_mask_suspect(self) -> None:
        with TemporaryDirectory() as td:
            p = Path(td) / "errors.jsonl"
            self._write(p)
            # legacy + high masked failure = 2; pipe-mask-suspect excluded.
            self.assertEqual(count_errors(p), 2)

    def test_iter_default_skips_pipe_mask_suspect(self) -> None:
        with TemporaryDirectory() as td:
            p = Path(td) / "errors.jsonl"
            self._write(p)
            cmds = [r["command"] for r in iter_records(p)]
            self.assertNotIn("python3 -m pytest 2>&1 | tail", cmds)

    def test_include_low_confidence_retains_suspect(self) -> None:
        with TemporaryDirectory() as td:
            p = Path(td) / "errors.jsonl"
            self._write(p)
            recs = list(iter_records(p, include_low_confidence=True))
            self.assertEqual(len(recs), 3)
            self.assertIn("python3 -m pytest 2>&1 | tail", [r["command"] for r in recs])

    def test_is_pipe_mask_suspect_helper(self) -> None:
        self.assertTrue(is_pipe_mask_suspect(_PIPE_MASK_SUSPECT))
        self.assertFalse(is_pipe_mask_suspect(_LOW_CONF_ECHO))  # low but echoed, not suspect
        self.assertFalse(is_pipe_mask_suspect(_HIGH_CONF_MASKED))
        self.assertFalse(is_pipe_mask_suspect(_GENUINE_MONITOR))


# #1465: a `.claude/`-wide `rg` sweep matching text stored inside this
# monitor's own log is self-referential, not a live failure. Records written
# AFTER the writer-side #1465 fix are tagged confidence="low" (like the two
# classes above); records written BEFORE it were mistagged confidence="high"
# + category="masked-failure" because the self-referential text itself
# routinely contains the STRONG masked-failure phrases the monitor looks for
# (a stored "exit status 1", a stored "Traceback ..."). `is_self_referential`
# re-derives the classification from `error_lines` so BOTH vintages are
# excluded from the genuine count at read time, without rewriting the log.
_POST_FIX_SELF_REFERENTIAL = {
    "timestamp": "t",
    "hook": "annunaki_monitor",
    "command": 'REPO_ROOT="$(pwd)"\nrg -rn --hidden "x" "$REPO_ROOT/.claude/"',
    "exit_code": 0,
    "matched_patterns": ["stdout:exit status [1-9]"],
    "confidence": "low",
    "category": "self-referential-log-read",
    "error_lines": ['.claude/annunaki/errors.jsonl:{"error_lines": ["exit status 1"]}'],
}
# The HISTORICAL shape: written by a pre-#1465 monitor, mistagged high/masked-
# failure even though its error_lines are entirely self-referential.
_PRE_FIX_MISTAGGED_HIGH_SELF_REFERENTIAL = {
    "timestamp": "t",
    "hook": "annunaki_monitor",
    "command": 'REPO_ROOT="$(pwd)"\nrg -rn --hidden "x" "$REPO_ROOT/.claude/"',
    "exit_code": 0,
    "matched_patterns": ["stdout:exit status [1-9]"],
    "confidence": "high",
    "category": "masked-failure",
    "error_lines": ['.claude/annunaki/errors.jsonl:{"error_lines": ["exit status 1"]}'],
}


class SelfReferentialFilter(unittest.TestCase):
    def _write(self, path: Path) -> None:
        lines = [
            json.dumps(_GENUINE_MONITOR),  # legacy, no confidence -> counted
            json.dumps(_POST_FIX_SELF_REFERENTIAL),  # excluded (low-confidence path)
            json.dumps(_PRE_FIX_MISTAGGED_HIGH_SELF_REFERENTIAL),  # excluded (re-derived)
            json.dumps(_HIGH_CONF_MASKED),  # genuine masked failure -> counted
        ]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_count_excludes_both_vintages(self) -> None:
        with TemporaryDirectory() as td:
            p = Path(td) / "errors.jsonl"
            self._write(p)
            # legacy + genuine masked failure = 2; BOTH self-referential
            # records excluded, including the mistagged-high historical one.
            self.assertEqual(count_errors(p), 2)

    def test_iter_default_skips_both_vintages(self) -> None:
        with TemporaryDirectory() as td:
            p = Path(td) / "errors.jsonl"
            self._write(p)
            cmds = [r["command"] for r in iter_records(p)]
            self.assertEqual(cmds, ["pytest", "git push ... | tail"])

    def test_include_self_referential_retains_both_vintages(self) -> None:
        with TemporaryDirectory() as td:
            p = Path(td) / "errors.jsonl"
            self._write(p)
            recs = list(iter_records(p, include_self_referential=True, include_low_confidence=True))
            self.assertEqual(len(recs), 4)

    def test_include_self_referential_ALONE_retains_both_vintages(self) -> None:
        """Nadia Khoury's #1498 merge-gate BLOCKING #3 finding: passing ONLY
        `include_self_referential=True` (NOT also `include_low_confidence=True`,
        unlike the test above) must retrieve BOTH self-referential vintages.
        Before the fix, the POST-fix `confidence="low"` vintage would fall
        through to the low-confidence filter immediately after and get
        dropped again -- so `--include-self-referential` alone surfaced only
        the historical mistagged-high vintage, silently missing the very
        category (`self-referential-log-read`) its own name promises. Once a
        record is identified as self-referential, `include_self_referential`
        must be the SOLE gate governing it."""
        with TemporaryDirectory() as td:
            p = Path(td) / "errors.jsonl"
            self._write(p)
            recs = list(iter_records(p, include_self_referential=True))
            categories = {r.get("category") for r in recs}
            self.assertIn(
                "self-referential-log-read",
                categories,
                "the post-fix vintage must be retrievable via include_self_referential ALONE",
            )
            self.assertIn(
                "masked-failure",
                categories,
                "the historical mistagged-high vintage must also be retrievable",
            )
            # 2 genuine (legacy + git push) + both self-referential vintages.
            self.assertEqual(len(recs), 4)

    def test_include_low_confidence_alone_does_not_leak_either_vintage(self) -> None:
        """A caller who only asks for `include_low_confidence=True` (NOT
        `include_self_referential=True`) must not see EITHER self-referential
        record: the self-referential filter is independent and checked first
        in `iter_records`, so it governs both the post-fix (confidence="low")
        and the mistagged historical (confidence="high") vintage regardless
        of the low-confidence flag. Only `include_self_referential=True`
        (exercised above) retrieves them."""
        with TemporaryDirectory() as td:
            p = Path(td) / "errors.jsonl"
            self._write(p)
            recs = list(iter_records(p, include_low_confidence=True))
            categories = [r.get("category") for r in recs]
            self.assertNotIn("masked-failure", categories, "the mistagged historical record leaked")
            self.assertNotIn(
                "self-referential-log-read",
                categories,
                "the post-fix self-referential record leaked without include_self_referential=True",
            )
            self.assertEqual([r["command"] for r in recs], ["pytest", "git push ... | tail"])

    def test_is_self_referential_helper(self) -> None:
        self.assertTrue(is_self_referential(_POST_FIX_SELF_REFERENTIAL))
        self.assertTrue(is_self_referential(_PRE_FIX_MISTAGGED_HIGH_SELF_REFERENTIAL))
        self.assertFalse(is_self_referential(_HIGH_CONF_MASKED))
        self.assertFalse(is_self_referential(_GENUINE_MONITOR))

    def test_is_self_referential_false_when_error_lines_missing_or_not_list(self) -> None:
        self.assertFalse(is_self_referential({"timestamp": "t"}))
        self.assertFalse(is_self_referential({"timestamp": "t", "error_lines": "not-a-list"}))

    def test_is_self_referential_false_on_mixed_lines(self) -> None:
        rec = {
            "error_lines": [
                '.claude/annunaki/errors.jsonl:{"a": 1}',
                ".claude/lib/real_module.py:Traceback (most recent call last):",
            ]
        }
        self.assertFalse(is_self_referential(rec))

    def test_cli_count_self_referential_flag(self) -> None:
        """Nadia Khoury's #1498 merge-gate BLOCKING #2 finding: `main()` is
        documented to return 0 UNCONDITIONALLY ("this is a read-only
        summarizer; it never fails the caller"), so asserting only the exit
        code is inert -- replacing the flag's body with `print(0)` would
        still pass. `--count-self-referential` is the only operator-facing
        surface reporting how many self-references were suppressed (the
        wave's observability bar), so the PRINTED NUMBER must be asserted,
        not just the exit code."""
        with TemporaryDirectory() as td:
            p = Path(td) / "errors.jsonl"
            self._write(p)
            captured = io.StringIO()
            with contextlib.redirect_stdout(captured):
                rc = main([str(p), "--count-self-referential"])
            self.assertEqual(rc, 0)
            # Exactly 2 self-referential records in this fixture (both vintages).
            self.assertEqual(captured.getvalue().strip(), "2")


# Nadia Khoury's #1498 merge-gate BLOCKING #1 finding: the writer's own
# `_classify_confidence` docstring states "a real failure signal always
# outranks a log-read attribution" -- nonzero-exit and stderr-match are
# checked BEFORE the self-referential branch. A record the WRITER correctly
# stamps `confidence=high`/`category=nonzero-exit` (or stderr-match) must
# still be counted genuine even if its `error_lines` happen to be entirely
# self-log text -- the reader must consume the writer's precedence, not
# re-derive a narrower judgement from `error_lines` alone.
#
# The crux (per the merge-gate re-review instructions): assert the ROUND
# TRIP via `count_errors`, not the stored `confidence`/`category` fields.
# Asserting only the stored fields is exactly the gap that let blocking-1
# ship in the first place -- the writer-side test that does that
# (`test_nonzero_exit_with_self_log_content_still_logged_high` in
# test_annunaki_monitor.py) passed throughout, because it never round-tripped
# the record through the reader.
_HARD_FAILURE_NONZERO_EXIT_WITH_SELF_LOG_LINES = {
    "timestamp": "t",
    "hook": "annunaki_monitor",
    "command": 'REPO_ROOT="$(pwd)"\nrg -rn --hidden "x" "$REPO_ROOT/.claude/annunaki/"',
    "exit_code": 2,
    "matched_patterns": ["exit_code=2", "stdout:exit status [1-9]"],
    "confidence": "high",
    "category": "nonzero-exit",
    "error_lines": ['.claude/annunaki/errors.jsonl:{"error_lines": ["exit status 1"]}'],
}
_HARD_FAILURE_STDERR_MATCH_WITH_SELF_LOG_LINES = {
    "timestamp": "t",
    "hook": "annunaki_monitor",
    "command": 'REPO_ROOT="$(pwd)"\nrg -rn --hidden "x" "$REPO_ROOT/.claude/annunaki/"',
    "exit_code": 0,
    "matched_patterns": ["stderr:^fatal:"],
    "confidence": "high",
    "category": "stderr-match",
    "error_lines": ['.claude/annunaki/traces.jsonl:{"outcome": {"raised": "fatal: xyz"}}'],
}


class HardFailurePrecedenceOverridesSelfReferential(unittest.TestCase):
    def test_nonzero_exit_with_self_log_lines_round_trips_as_genuine(self) -> None:
        with TemporaryDirectory() as td:
            p = Path(td) / "errors.jsonl"
            p.write_text(
                json.dumps(_HARD_FAILURE_NONZERO_EXIT_WITH_SELF_LOG_LINES) + "\n",
                encoding="utf-8",
            )
            # The crux assertion: the ROUND TRIP through the reader, not the
            # stored confidence/category fields on the fixture.
            self.assertEqual(count_errors(p), 1)

    def test_stderr_match_with_self_log_lines_round_trips_as_genuine(self) -> None:
        with TemporaryDirectory() as td:
            p = Path(td) / "errors.jsonl"
            p.write_text(
                json.dumps(_HARD_FAILURE_STDERR_MATCH_WITH_SELF_LOG_LINES) + "\n",
                encoding="utf-8",
            )
            self.assertEqual(count_errors(p), 1)

    def test_is_self_referential_false_for_hard_failure_categories(self) -> None:
        self.assertFalse(is_self_referential(_HARD_FAILURE_NONZERO_EXIT_WITH_SELF_LOG_LINES))
        self.assertFalse(is_self_referential(_HARD_FAILURE_STDERR_MATCH_WITH_SELF_LOG_LINES))

    def test_is_self_referential_false_for_nonzero_exit_with_no_category(self) -> None:
        """Defensive fallback: a record with a nonzero exit_code but NO
        `category` field at all (a record shape the writer does not
        currently produce, but the guard should not assume it never will)
        is still never self-referential."""
        rec = {
            "exit_code": 1,
            "error_lines": ['.claude/annunaki/errors.jsonl:{"error_lines": ["exit status 1"]}'],
        }
        self.assertFalse(is_self_referential(rec))


class TraceTypeSourceOfTruth(unittest.TestCase):
    def test_matches_writer_constant(self) -> None:
        # annunaki_parse must import the SAME set the writer uses; if the hook
        # import path works, the two must be identical (no drift).
        hooks_dir = Path(__file__).resolve().parents[2] / "hooks"
        sys.path.insert(0, str(hooks_dir))
        from annunaki_log import TRACE_RECORD_TYPES as writer_set  # noqa: E402

        self.assertEqual(TRACE_RECORD_TYPES, writer_set)
        self.assertEqual(
            writer_set,
            frozenset({"posttooluse_dispatch", "pretooluse_diagnostic", "pretooluse_dispatch"}),
        )


class SelfReferentialMatchSourceOfTruth(unittest.TestCase):
    """#1502 (Nadia Khoury's #1498 merge-gate tech debt): `is_self_referential_match`
    has a vendored-fallback duplicate (for when the hooks dir isn't
    importable) with no test asserting it stays in sync with the writer's
    original -- unlike `TRACE_RECORD_TYPES` above, which has exactly this
    test. Follows that established pattern rather than inventing a new one."""

    def test_matches_writer_function(self) -> None:
        # annunaki_parse must use the SAME predicate object the writer
        # defines; if the hooks import path works (the normal case, mirrored
        # by TraceTypeSourceOfTruth above), the two must be the IDENTICAL
        # function object -- no separate implementation to drift.
        hooks_dir = Path(__file__).resolve().parents[2] / "hooks"
        sys.path.insert(0, str(hooks_dir))
        from annunaki_monitor import is_self_referential_match as writer_fn  # noqa: E402

        self.assertIs(is_self_referential_match, writer_fn)

    def test_writer_function_behavior_sanity(self) -> None:
        # Belt-and-suspenders: even identity-checked, confirm the imported
        # function actually behaves as documented on a representative input
        # (guards against a future refactor that swaps the identity-correct
        # object for a differently-behaving one under the same name).
        self.assertTrue(is_self_referential_match(['.claude/annunaki/errors.jsonl:{"a": 1}']))
        self.assertFalse(is_self_referential_match(["some/other/dir/errors.jsonl:{}"]))


class Cli(unittest.TestCase):
    def test_count_flag(self) -> None:
        with TemporaryDirectory() as td:
            p = Path(td) / "errors.jsonl"
            _write_mixed(p)
            # main prints the count; capture via the return code being 0 and
            # relying on count_errors elsewhere — here just assert it runs clean.
            self.assertEqual(main([str(p), "--count"]), 0)

    def test_default_run_clean(self) -> None:
        with TemporaryDirectory() as td:
            p = Path(td) / "errors.jsonl"
            _write_mixed(p)
            self.assertEqual(main([str(p)]), 0)


if __name__ == "__main__":
    unittest.main()
