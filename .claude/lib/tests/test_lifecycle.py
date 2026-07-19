"""Tests for lifecycle.py — the deterministic wave-lifecycle facade (main#1019).

The facade is a THIN WRAPPER over noorina's existing cross-repo state: it writes
through the shared ``upsert_status_keys`` helper (so the file's compact-inline
shape and JSON validity are preserved) and delegates the transitions that already
have deterministic modules (``allocate`` → wave_seq, ``merge-model`` /
``reachability`` → wave_merge_model, ``counters`` → wave_status).

These tests exercise the genuinely-new transition writes end-to-end against a
real (temp) status file — no network, no mocks for the write path — plus the key
invariants the facade must hold:

  * every write round-trips through the file as valid JSON (upsert contract);
  * the file's compact-inline shape survives (no whole-file reflow);
  * ownership boundaries hold — ``wrapup`` writes NO counter; ``kickoff`` with a
    bad merge model raises before writing anything;
  * the read-only delegations forward to the owning module.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

# Helper lives at .claude/lib/lifecycle.py; this test is at
# .claude/lib/tests/test_*.py. parent.parent reaches the lib root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import lifecycle  # noqa: E402
import wave_merge_model  # noqa: E402


def _seed_status() -> dict:
    """A minimal but realistic mid-lifecycle status file.

    Global-wave numbering (main#804): the committed counter is 25 (wave 25 is
    scoped/kicked-off), and wave 26's meta-issue is reserved one above the
    committed counter (the /wave-retro Step 9 reservation) so the allocator's
    reservation-awareness is exercised through the facade.
    """
    return {
        "current_phase": 9,
        "current_wave": "wave-25",
        "last_completed_wave": "wave-24",
        "global_wave_seq": 25,
        "wave_24_phase": 8,
        "wave_24_active": False,
        "wave_24_completed_at": "2026-07-05T00:00:00Z",
        "wave_25_phase": 9,
        "wave_25_phase_ordinal": 1,
        "wave_25_active": True,
        "wave_25_repos_in_scope": ["noorinalabs-data-acquisition"],
        "wave_25_kicked_off_at": "2026-07-18T21:11:08Z",
        "wave_25_merge_model": "wave-branch",
        "wave_26_meta_issue": "noorinalabs-main#983",
    }


class _StatusFileTest(unittest.TestCase):
    """Base: write the seed dict to a temp file in the compact-inline shape."""

    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "cross-repo-status.json"
        # json.dumps(indent=2) yields the `{\n  "k": v,\n}` shape upsert extends.
        self.path.write_text(json.dumps(_seed_status(), indent=2) + "\n")

    def _reload(self) -> dict:
        return json.loads(self.path.read_text())


class TestStart(_StatusFileTest):
    def test_start_stamps_active_and_pointer(self) -> None:
        rc = lifecycle.start(self.path, "27", at="2026-07-19T10:00:00Z")
        self.assertEqual(rc, 0)
        data = self._reload()
        self.assertEqual(data["current_wave"], "wave-27")
        self.assertIs(data["wave_27_active"], True)
        self.assertEqual(data["wave_27_started_at"], "2026-07-19T10:00:00Z")

    def test_start_leaves_file_valid_and_other_keys_intact(self) -> None:
        lifecycle.start(self.path, "27", at="2026-07-19T10:00:00Z")
        data = self._reload()
        # Untouched keys survive the targeted upsert.
        self.assertEqual(data["wave_25_repos_in_scope"], ["noorinalabs-data-acquisition"])
        self.assertEqual(data["global_wave_seq"], 25)


class TestScope(_StatusFileTest):
    def test_scope_writes_repos_and_reconciled_at(self) -> None:
        rc = lifecycle.scope(
            self.path,
            "27",
            ["noorinalabs-isnad-graph", "noorinalabs-user-service"],
            phase=9,
            at="2026-07-19T11:00:00Z",
        )
        self.assertEqual(rc, 0)
        data = self._reload()
        self.assertEqual(
            data["wave_27_repos_in_scope"],
            ["noorinalabs-isnad-graph", "noorinalabs-user-service"],
        )
        self.assertEqual(data["wave_27_scope_reconciled_at"], "2026-07-19T11:00:00Z")
        self.assertEqual(data["wave_27_phase"], 9)

    def test_scope_phase_optional(self) -> None:
        lifecycle.scope(self.path, "27", ["noorinalabs-landing-page"], at="2026-07-19T11:00:00Z")
        data = self._reload()
        self.assertNotIn("wave_27_phase", data)
        self.assertEqual(data["wave_27_repos_in_scope"], ["noorinalabs-landing-page"])

    def test_scoped_repos_readable_by_wave_status(self) -> None:
        # The facade's scope write must satisfy wave_status.read_repos — the
        # cross-module contract kickoff/wrapup depend on.
        import wave_status

        lifecycle.scope(self.path, "27", ["repo-a", "repo-b"], at="2026-07-19T11:00:00Z")
        self.assertEqual(wave_status.read_repos("27", self.path), ["repo-a", "repo-b"])


class TestKickoff(_StatusFileTest):
    def test_kickoff_stamps_timestamp_pointer_and_merge_model(self) -> None:
        rc = lifecycle.kickoff(
            self.path, "27", merge_model="wave-branch", at="2026-07-19T12:00:00Z"
        )
        self.assertEqual(rc, 0)
        data = self._reload()
        self.assertEqual(data["wave_27_kicked_off_at"], "2026-07-19T12:00:00Z")
        self.assertEqual(data["current_wave"], "wave-27")
        self.assertIs(data["wave_27_active"], True)
        self.assertEqual(data["wave_27_merge_model"], "wave-branch")

    def test_kickoff_merge_model_optional(self) -> None:
        lifecycle.kickoff(self.path, "27", at="2026-07-19T12:00:00Z")
        data = self._reload()
        self.assertNotIn("wave_27_merge_model", data)

    def test_kickoff_rejects_bad_merge_model_without_writing(self) -> None:
        before = self.path.read_text()
        with self.assertRaises(ValueError):
            lifecycle.kickoff(self.path, "27", merge_model="squash-and-pray")
        # Validation happens before the upsert, so nothing was written.
        self.assertEqual(self.path.read_text(), before)

    def test_kickoff_merge_model_readable_by_owning_module(self) -> None:
        lifecycle.kickoff(self.path, "27", merge_model="direct-to-main", at="2026-07-19T12:00:00Z")
        self.assertEqual(wave_merge_model.read_merge_model("27", self.path), "direct-to-main")


class TestWrapup(_StatusFileTest):
    def test_wrapup_closes_pointers(self) -> None:
        rc = lifecycle.wrapup(self.path, "25", at="2026-07-19T13:00:00Z")
        self.assertEqual(rc, 0)
        data = self._reload()
        self.assertIs(data["wave_25_active"], False)
        self.assertEqual(data["wave_25_completed_at"], "2026-07-19T13:00:00Z")
        self.assertEqual(data["last_completed_wave"], "wave-25")

    def test_wrapup_writes_no_counter(self) -> None:
        # Counter ownership stays with wave_status.py; wrapup must not write one.
        lifecycle.wrapup(self.path, "25", at="2026-07-19T13:00:00Z")
        data = self._reload()
        for counter in (
            "wave_25_final_pr_count",
            "wave_25_changes_requested_cycles",
            "wave_25_top_concentration_pct",
        ):
            self.assertNotIn(counter, data)


class TestRetro(_StatusFileTest):
    def test_retro_stamps_completed_at(self) -> None:
        rc = lifecycle.retro(self.path, "25", at="2026-07-19T14:00:00Z")
        self.assertEqual(rc, 0)
        self.assertEqual(self._reload()["wave_25_retro_completed_at"], "2026-07-19T14:00:00Z")


class TestPeekAndAllocateDelegation(_StatusFileTest):
    def test_peek_honours_reservation(self) -> None:
        # committed counter 24 + reserved wave_26_meta_issue → peek claims 26.
        self.assertEqual(lifecycle.peek(self.path), 26)

    def test_allocate_dry_run_does_not_write(self) -> None:
        before = self.path.read_text()
        rc = lifecycle.allocate(self.path, 9, write=False)
        self.assertEqual(rc, 0)
        self.assertEqual(self.path.read_text(), before)

    def test_allocate_write_persists_via_wave_seq(self) -> None:
        rc = lifecycle.allocate(self.path, 9, write=True)
        self.assertEqual(rc, 0)
        data = self._reload()
        # The reserved id 26 is claimed and its phase stamps written by wave_seq.
        self.assertEqual(data["global_wave_seq"], 26)
        self.assertEqual(data["wave_26_phase"], 9)
        self.assertIn("wave_26_phase_ordinal", data)


class TestFileShapePreserved(_StatusFileTest):
    def test_compact_inline_shape_not_reflowed(self) -> None:
        # A representative multi-transition sequence, then assert the file is
        # still line-oriented compact-inline (one top-level key per line) — the
        # whole reason the facade routes through upsert_status_keys.
        lifecycle.start(self.path, "27", at="2026-07-19T10:00:00Z")
        lifecycle.scope(self.path, "27", ["repo-a"], phase=9, at="2026-07-19T11:00:00Z")
        lifecycle.kickoff(self.path, "27", merge_model="wave-branch", at="2026-07-19T12:00:00Z")
        text = self.path.read_text()
        # Still valid JSON.
        json.loads(text)
        # The newly written keys are each a single physical line (compact-inline),
        # not pretty-expanded across lines.
        for key in ("wave_27_active", "wave_27_repos_in_scope", "wave_27_kicked_off_at"):
            matches = [ln for ln in text.splitlines() if f'"{key}":' in ln]
            self.assertEqual(len(matches), 1, f"{key} should be exactly one line")

    def test_idempotent_re_write(self) -> None:
        # Re-running a transition with the same timestamp is a no-op on content.
        lifecycle.start(self.path, "27", at="2026-07-19T10:00:00Z")
        once = self.path.read_text()
        lifecycle.start(self.path, "27", at="2026-07-19T10:00:00Z")
        self.assertEqual(self.path.read_text(), once)


class TestCliSmoke(_StatusFileTest):
    def test_cli_wave_start(self) -> None:
        rc = lifecycle.main(
            ["wave", "start", "27", "--at", "2026-07-19T10:00:00Z", "--status", str(self.path)]
        )
        self.assertEqual(rc, 0)
        self.assertEqual(self._reload()["current_wave"], "wave-27")

    def test_cli_wave_peek(self) -> None:
        rc = lifecycle.main(["wave", "peek", "--status", str(self.path)])
        self.assertEqual(rc, 0)

    def test_cli_merge_model_get_delegates(self) -> None:
        # wave 25's model is recorded in the seed; the delegation must surface it.
        rc = lifecycle.main(["merge-model", "get", "9", "25", "--status", str(self.path)])
        self.assertEqual(rc, 0)

    def test_cli_state_show(self) -> None:
        rc = lifecycle.main(["state", "show", "--status", str(self.path)])
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
