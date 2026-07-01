"""Tests for board_audit_drift — the /board-audit Step 4 drift classifier (main#902).

Core regression (main#902): a CLOSED issue that legitimately retains its wave label
falls out of the OPEN-only label map, so its expected option is ``(unset)``; without
the state guard it would be flagged ``<W..> -> (clear)`` and its correct historical
Wave attribution erased. These tests pin the guard AND prove the genuine drift signal
(open mismatch, stale field on open items) is preserved.
"""

from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from board_audit_drift import (  # noqa: E402
    CLEAR,
    UNSET,
    classify,
    classify_rows,
    is_open,
    is_valid_wave_option,
    main,
)


class ClosedItemGuard(unittest.TestCase):
    """main#902: closed items retaining a valid wave option are NOT drift."""

    def test_closed_issue_with_valid_new_form_label_not_drift(self) -> None:
        # Closed wave-19 issue: field=W19, expected=(unset) (open-only map miss).
        c = classify(current="W19", expected=UNSET, state="CLOSED")
        self.assertEqual(c.bucket, "skip")
        self.assertIsNone(c.target)

    def test_closed_issue_with_legacy_grandfathered_label_not_drift(self) -> None:
        # Closed p3-wave-10 issue: field=P3W10, expected=(unset).
        c = classify(current="P3W10", expected=UNSET, state="CLOSED")
        self.assertEqual(c.bucket, "skip")

    def test_merged_pr_with_valid_option_not_drift(self) -> None:
        # PRs report state MERGED — also protected from erasure.
        c = classify(current="W20", expected=UNSET, state="MERGED")
        self.assertEqual(c.bucket, "skip")

    def test_placeholder_wx_on_closed_item_protected(self) -> None:
        c = classify(current="WX", expected=UNSET, state="CLOSED")
        self.assertEqual(c.bucket, "skip")


class GenuineDriftPreserved(unittest.TestCase):
    """The state guard must NOT swallow real drift."""

    def test_open_issue_mismatch_is_drift(self) -> None:
        # Open issue whose label says W20 but board field is W19 → sync to W20.
        c = classify(current="W19", expected="W20", state="OPEN")
        self.assertEqual(c.bucket, "drift")
        self.assertEqual(c.target, "W20")

    def test_closed_issue_mismatch_still_synced_to_label(self) -> None:
        # A closed issue that IS in the label map (its expected is known) and
        # disagrees with the board is still real drift — expected!=unset path.
        c = classify(current="W18", expected="W19", state="CLOSED")
        self.assertEqual(c.bucket, "drift")
        self.assertEqual(c.target, "W19")

    def test_open_issue_no_label_populated_field_is_clear(self) -> None:
        # Open item, no wave label anywhere, but field populated → clear (as before).
        c = classify(current="W19", expected=UNSET, state="OPEN")
        self.assertEqual(c.bucket, "drift")
        self.assertEqual(c.target, CLEAR)

    def test_closed_item_with_non_option_field_value_is_clear(self) -> None:
        # Guard only protects *valid* wave options; a garbage field value on a
        # closed item is still cleared (not a real wave attribution).
        c = classify(current="garbage", expected=UNSET, state="CLOSED")
        self.assertEqual(c.bucket, "drift")
        self.assertEqual(c.target, CLEAR)


class NonActionableBuckets(unittest.TestCase):
    def test_no_label_and_unset_is_noop(self) -> None:
        c = classify(current=UNSET, expected=UNSET, state="OPEN")
        self.assertEqual(c.bucket, "noop")

    def test_label_matches_field_is_in_sync(self) -> None:
        c = classify(current="W19", expected="W19", state="OPEN")
        self.assertEqual(c.bucket, "in_sync")


class HelperPredicates(unittest.TestCase):
    def test_is_valid_wave_option(self) -> None:
        self.assertTrue(is_valid_wave_option("W19"))
        self.assertTrue(is_valid_wave_option("P3W10"))
        self.assertTrue(is_valid_wave_option("WX"))
        self.assertFalse(is_valid_wave_option("(unset)"))
        self.assertFalse(is_valid_wave_option("(clear)"))
        self.assertFalse(is_valid_wave_option(""))
        self.assertFalse(is_valid_wave_option("wave-19"))  # label form, not option

    def test_is_open(self) -> None:
        self.assertTrue(is_open("OPEN"))
        self.assertTrue(is_open("open"))
        self.assertFalse(is_open("CLOSED"))
        self.assertFalse(is_open("MERGED"))
        self.assertFalse(is_open(""))  # unknown state → treated non-open (protect)


class RowClassificationAndSummary(unittest.TestCase):
    def test_classify_rows_buckets_and_counts(self) -> None:
        lines = [
            "https://x/1\tW19\tW20\tOPEN\n",  # drift -> W20
            "https://x/2\tW19\t(unset)\tCLOSED\n",  # skip (protected, main#902)
            "https://x/3\tW19\t(unset)\tOPEN\n",  # drift -> (clear)
            "https://x/4\t(unset)\t(unset)\tOPEN\n",  # noop
            "https://x/5\tW19\tW19\tOPEN\n",  # in_sync
            "\n",  # blank ignored
        ]
        drift_rows, summary = classify_rows(lines)
        self.assertEqual(
            drift_rows,
            ["https://x/1\tW19\tW20", "https://x/3\tW19\t(clear)"],
        )
        self.assertEqual(summary.drift, 2)
        self.assertEqual(summary.protected, 1)
        self.assertEqual(summary.noop, 1)
        self.assertEqual(summary.in_sync, 1)
        self.assertEqual(summary.summary_line(), "noop=1 protected=1 in_sync=1 drift=2")

    def test_missing_state_column_treated_as_non_open(self) -> None:
        # A 3-column row (no state) on a valid option → protected, not cleared.
        drift_rows, summary = classify_rows(["https://x/9\tW19\t(unset)\n"])
        self.assertEqual(drift_rows, [])
        self.assertEqual(summary.protected, 1)


class CliBehaviour(unittest.TestCase):
    def test_main_reads_file_and_writes_streams(self) -> None:
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".tsv", delete=False) as fh:
            fh.write("https://x/1\tW19\tW20\tOPEN\n")
            fh.write("https://x/2\tW19\t(unset)\tCLOSED\n")
            path = fh.name

        out, err = io.StringIO(), io.StringIO()
        old_out, old_err = sys.stdout, sys.stderr
        try:
            sys.stdout, sys.stderr = out, err
            rc = main([path])
        finally:
            sys.stdout, sys.stderr = old_out, old_err

        self.assertEqual(rc, 0)
        self.assertEqual(out.getvalue().strip(), "https://x/1\tW19\tW20")
        self.assertIn("protected=1", err.getvalue())
        self.assertIn("drift=1", err.getvalue())


if __name__ == "__main__":
    unittest.main()
