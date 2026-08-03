#!/usr/bin/env python3
"""Tests for the `session_start` SessionStart hook.

Regression coverage:
* #708 — `_wave_status()` used to read the flat keys `phase` (which lags a
  phase behind — #683 cross-phase collision), `wave` (which does not exist),
  and `last_updated`. The fix reads the canonical lifecycle keys
  `current_phase` / `current_wave` / `wave_<N>_started_at`.
* #962 — the hook stdout is a slim pointer (~10 lines): it mandates
  /session-start, prints one-line counts, and NEVER dumps the handoff file
  contents or an auto `/annunaki-attack` directive (attack is on-demand /
  wave-wrapup, re #925). The skill owns the step detail.
* #1142 — `_ontology_staleness` no longer re-implements the
  `last_tracked != last_resolved` predicate. It delegates to
  `checksums_io.read_status`, so a malformed entry counts as malformed
  (not clean) and an unreadable ledger reports as unreadable (not `0 dirty`).

Run from the repo root:
    ENVIRONMENT=test python3 -m pytest \\
        .claude/hooks/tests/test_session_start.py -v
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from collections.abc import Iterator
from pathlib import Path

import __test_helpers  # noqa: E402,F401
import session_start as hook  # noqa: E402


def _live_shaped(**overrides: object) -> dict:
    """A dict shaped like the real cross-repo-status.json, incl. stale keys."""
    data: dict = {
        "current_phase": 5,
        "current_wave": "wave-5",
        "wave_5_started_at": "2026-06-16T22:51:14Z",
        "wave_5_kicked_off_at": None,
        # Stale flat keys that the buggy reader trusted:
        "phase": "phase-4",
        "wave": None,
        "last_updated": "2026-06-15T01:52:55Z",
    }
    data.update(overrides)
    return data


class WavePhaseStartedTests(unittest.TestCase):
    def test_reads_canonical_keys_not_stale_flat_keys(self) -> None:
        phase, wave, started = hook._wave_phase_started(_live_shaped())
        self.assertEqual(phase, "5")
        self.assertEqual(wave, "wave-5")
        self.assertEqual(started, "2026-06-16T22:51:14Z")
        self.assertNotEqual(phase, "phase-4")
        self.assertNotEqual(wave, "unknown")

    def test_falls_back_to_kicked_off_at_when_started_missing(self) -> None:
        data = _live_shaped()
        del data["wave_5_started_at"]
        data["wave_5_kicked_off_at"] = "2026-06-16T20:00:00Z"
        _, _, started = hook._wave_phase_started(data)
        self.assertEqual(started, "2026-06-16T20:00:00Z")

    def test_falls_back_when_started_present_but_null(self) -> None:
        data = _live_shaped(wave_5_started_at=None, wave_5_kicked_off_at="2026-06-16T20:00:00Z")
        _, _, started = hook._wave_phase_started(data)
        self.assertEqual(started, "2026-06-16T20:00:00Z")

    def test_started_unknown_when_no_timestamps(self) -> None:
        data = _live_shaped(wave_5_started_at=None, wave_5_kicked_off_at=None)
        _, _, started = hook._wave_phase_started(data)
        self.assertEqual(started, "unknown")

    def test_missing_canonical_keys_graceful(self) -> None:
        phase, wave, started = hook._wave_phase_started({"last_updated": "x"})
        self.assertEqual(phase, "unknown")
        self.assertEqual(wave, "unknown")
        self.assertEqual(started, "unknown")


class WaveStatusWrapperTests(unittest.TestCase):
    def test_wrapper_reports_phase_and_wave(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            status = Path(d) / "cross-repo-status.json"
            status.write_text(json.dumps(_live_shaped()), encoding="utf-8")
            original = hook._CROSS_REPO_STATUS
            try:
                hook._CROSS_REPO_STATUS = status
                result = hook._wave_status()
            finally:
                hook._CROSS_REPO_STATUS = original
        self.assertEqual(result, "Phase 5, Wave wave-5 (started: 2026-06-16T22:51:14Z)")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertNotIn("unknown", result)
        self.assertNotIn("phase-4", result)

    def test_wrapper_returns_none_on_missing_file(self) -> None:
        original = hook._CROSS_REPO_STATUS
        try:
            hook._CROSS_REPO_STATUS = Path("/nonexistent/cross-repo-status.json")
            result = hook._wave_status()
        finally:
            hook._CROSS_REPO_STATUS = original
        self.assertIsNone(result)


class HandoffPathLocationTests(unittest.TestCase):
    """#741: the SessionStart hook must read the handoff from the in-repo,
    version-controlled .claude/memory/ — NOT the user-space
    ~/.claude/projects/<encoded>/memory/ auto-memory dir. Reading user-space
    while the /session-start skill reads in-repo is the split-brain this fixes.
    """

    def test_handoff_is_in_repo_memory(self) -> None:
        expected = hook._PROJECT / ".claude" / "memory" / "session_handoff.md"
        self.assertEqual(hook._HANDOFF, expected)

    def test_handoff_not_in_user_space(self) -> None:
        self.assertNotIn("/.claude/projects/", hook._HANDOFF.as_posix())
        self.assertFalse(hook._HANDOFF.is_relative_to(Path.home() / ".claude" / "projects"))


class OntologyStalenessTests(unittest.TestCase):
    """#1142: the hook consumes the shared predicate, it does not re-derive it.

    The inline version this replaced was the ONLY correct implementation of
    `last_tracked != last_resolved` in the repo, and it lived in a private hook
    function nothing could import — so every other reader reproduced it from
    memory, and two consecutive sessions reproduced it wrong.
    """

    @contextlib.contextmanager
    def _checksums(self, payload: str) -> Iterator[Path]:
        """Point the hook at a temporary ledger for the duration of the block."""
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "checksums.json"
            path.write_text(payload, encoding="utf-8")
            original = hook._CHECKSUMS
            try:
                hook._CHECKSUMS = path
                yield path
            finally:
                hook._CHECKSUMS = original

    def _capture_main(self) -> str:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            hook.main()
        return buf.getvalue()

    def test_delegates_to_the_shared_reader(self) -> None:
        """Not an isinstance ceremony — the point is that the hook returns the
        shared module's type, so there is nothing left here to drift."""
        payload = json.dumps(
            {"version": 1, "files": {"a.md": {"last_tracked": "1", "last_resolved": "1"}}}
        )
        with self._checksums(payload):
            status = hook._ontology_staleness()
        self.assertIsInstance(status, hook.checksums_io.ChecksumsStatus)
        assert status is not None
        self.assertTrue(status.clean)

    def test_dirty_entry_is_counted(self) -> None:
        payload = json.dumps(
            {
                "version": 1,
                "files": {
                    "a.md": {"last_tracked": "1", "last_resolved": "1"},
                    "b.md": {"last_tracked": "1", "last_resolved": "2"},
                },
            }
        )
        with self._checksums(payload):
            status = hook._ontology_staleness()
            out = self._capture_main()
        assert status is not None
        self.assertEqual(status.dirty, ("b.md",))
        self.assertIn("1/2 dirty", out)

    def test_malformed_entry_is_not_reported_as_current(self) -> None:
        """The real committed shape: `{"last_resolved": null, "resolved_at": ...}`.

        The previous inline reader compared `.get("last_tracked")` (None)
        against `.get("last_resolved")` (None), found them equal, and reported
        "current (0/N dirty)" — which it did, every session, for seven weeks.
        """
        payload = json.dumps(
            {
                "version": 1,
                "files": {
                    "a.md": {"last_tracked": "1", "last_resolved": "1"},
                    "b.md": {"last_resolved": None, "resolved_at": "2026-06-14T00:16:00Z"},
                },
            }
        )
        with self._checksums(payload):
            status = hook._ontology_staleness()
            out = self._capture_main()
        assert status is not None
        self.assertFalse(status.clean)
        self.assertEqual(len(status.malformed), 1)
        self.assertNotIn("current (", out)
        self.assertIn("1 malformed", out)

    def test_unreadable_ledger_is_reported_not_counted_as_clean(self) -> None:
        with self._checksums("{not json"):
            status = hook._ontology_staleness()
            out = self._capture_main()
        self.assertIsNone(status)
        self.assertIn("unreadable", out)
        self.assertNotIn("0/0 dirty", out)


class SlimStdoutTests(unittest.TestCase):
    """#962: the hook prints a ~10-line pointer, not the full protocol."""

    def _capture(self) -> str:
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            hook.main()
        return buf.getvalue()

    def test_output_is_slim_and_mandates_the_skill(self) -> None:
        out = self._capture()
        self.assertLessEqual(len(out.strip().splitlines()), 12)
        self.assertIn("/session-start", out)
        self.assertIn("MANDATORY FIRST ACTION", out)
        # The step detail lives in the skill, not here.
        self.assertNotIn("STEP 5", out)
        self.assertNotIn("ACTIONS REQUIRED", out)

    def test_handoff_contents_never_dumped_only_pointed_at(self) -> None:
        import tempfile

        sentinel = "HANDOFF-BODY-SENTINEL-962"
        with tempfile.TemporaryDirectory() as d:
            handoff = Path(d) / "session_handoff.md"
            handoff.write_text(f"---\nname: x\n---\n{sentinel}\n", encoding="utf-8")
            original = hook._HANDOFF
            try:
                hook._HANDOFF = handoff
                out = self._capture()
            finally:
                hook._HANDOFF = original
        self.assertNotIn(sentinel, out)
        self.assertIn("session_handoff.md", out)
        self.assertIn("exists", out)

    def test_annunaki_line_is_count_only_no_auto_attack(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "errors.jsonl"
            log.write_text("{}\n" * 10, encoding="utf-8")
            original = hook._ERRORS_LOG
            try:
                hook._ERRORS_LOG = log
                out = self._capture()
            finally:
                hook._ERRORS_LOG = original
        self.assertIn("10 error(s) logged", out)
        # No imperative attack directive even at 10 errors (>= old threshold 5).
        self.assertNotIn("ACTION: Run /annunaki-attack", out)
        self.assertIn("on demand", out)


if __name__ == "__main__":
    unittest.main()
