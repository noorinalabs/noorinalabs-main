#!/usr/bin/env python3
"""Tests for the `session_handoff` Stop hook's wave/phase reader (#708).

Regression coverage: `_get_wave_status()` used to read the top-level keys
`wave` / `started`, neither of which exists in cross-repo-status.json, so it
always reported "unknown". The fix reads the canonical lifecycle keys
`current_phase` / `current_wave` / `wave_<N>_started_at`.

Run from the repo root:
    ENVIRONMENT=test python3 -m pytest \\
        .claude/hooks/tests/test_session_handoff.py -v
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import __test_helpers  # noqa: E402,F401
import session_handoff as hook  # noqa: E402


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
        "started": None,
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
        # The stale flat keys must NOT leak through.
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


class GetWaveStatusTests(unittest.TestCase):
    def _write_status(self, tmp: Path, data: dict) -> None:
        (tmp / "cross-repo-status.json").write_text(json.dumps(data), encoding="utf-8")

    def test_wrapper_reports_phase_and_wave(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            self._write_status(tmp, _live_shaped())
            original = hook.REPO_ROOT
            try:
                hook.REPO_ROOT = tmp
                result = hook._get_wave_status()
            finally:
                hook.REPO_ROOT = original
        self.assertEqual(result, "Phase 5, Wave wave-5 (started 2026-06-16T22:51:14Z)")
        self.assertNotIn("unknown", result)
        self.assertNotIn("phase-4", result)

    def test_wrapper_missing_file(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            original = hook.REPO_ROOT
            try:
                hook.REPO_ROOT = Path(d)
                result = hook._get_wave_status()
            finally:
                hook.REPO_ROOT = original
        self.assertEqual(result, "No cross-repo-status.json found")


class GetOpenPrsSingleSearchCallTests(unittest.TestCase):
    """main#1120 / audit G8: `_get_open_prs()` used to iterate ALL_REPOS with
    one `gh pr list` subprocess per repo (7 serial pre-#1238, 8 post-#1238) —
    worst case ~120s against a 30s Stop-hook timeout. It now issues exactly
    ONE `gh search prs --owner noorinalabs` call spanning the whole org."""

    def test_issues_exactly_one_search_call(self) -> None:
        from unittest.mock import patch

        calls: list[str] = []

        def _fake_run(cmd: str, cwd: str | None = None, timeout: int = 10) -> str:
            calls.append(cmd)
            return "[]"

        with patch.object(hook, "_run", side_effect=_fake_run):
            hook._get_open_prs()

        # Non-vacuous shape assertion (the issue's own "Verify" ask): exactly
        # one subprocess, and it's a single org-scoped search — not a
        # per-repo `gh pr list`.
        self.assertEqual(len(calls), 1)
        self.assertIn("gh search prs", calls[0])
        self.assertIn("--owner noorinalabs", calls[0])
        self.assertNotIn("gh pr list", calls[0])

    def test_parses_items_across_repos(self) -> None:
        from unittest.mock import patch

        raw = json.dumps(
            [
                {"number": 42, "title": "Fix thing", "repository": {"name": "noorinalabs-main"}},
                {
                    "number": 7,
                    "title": "Add feature",
                    "repository": {"name": "noorinalabs-isnad-ingest-platform"},
                },
            ]
        )
        with patch.object(hook, "_run", return_value=raw):
            result = hook._get_open_prs()

        self.assertFalse(result.failed)
        self.assertFalse(result.truncated)
        self.assertEqual(result.unknown_repos, ())
        self.assertEqual(
            result.lines,
            [
                "  - noorinalabs-main#42: Fix thing",
                "  - noorinalabs-isnad-ingest-platform#7: Add feature",
            ],
        )

    def test_failed_query_is_distinct_from_empty_result(self) -> None:
        """A failed command (`_run` returns "") must NOT collapse into the same
        state as a genuinely empty PR list ("[]") — that would misreport an
        unknown PR state as "the org has zero open PRs" (main#1120)."""
        from unittest.mock import patch

        with patch.object(hook, "_run", return_value=""):
            failed_result = hook._get_open_prs()
        with patch.object(hook, "_run", return_value="[]"):
            empty_result = hook._get_open_prs()

        self.assertTrue(failed_result.failed)
        self.assertFalse(empty_result.failed)
        self.assertEqual(failed_result.lines, [])
        self.assertEqual(empty_result.lines, [])
        # The two must render differently even though `lines` is identical.
        self.assertNotEqual(
            hook._render_prs_section(failed_result),
            hook._render_prs_section(empty_result),
        )
        self.assertIn("QUERY FAILED", "\n".join(hook._render_prs_section(failed_result)))

    def test_malformed_json_treated_as_failure(self) -> None:
        from unittest.mock import patch

        with patch.object(hook, "_run", return_value="not json"):
            result = hook._get_open_prs()

        self.assertTrue(result.failed)

    def test_truncation_detected_at_cap(self) -> None:
        from unittest.mock import patch

        items = [
            {"number": i, "title": f"PR {i}", "repository": {"name": "noorinalabs-main"}}
            for i in range(hook.PR_SEARCH_LIMIT)
        ]
        with patch.object(hook, "_run", return_value=json.dumps(items)):
            result = hook._get_open_prs()

        self.assertTrue(result.truncated)
        rendered = "\n".join(hook._render_prs_section(result))
        self.assertIn(f"{hook.PR_SEARCH_LIMIT}-result search cap", rendered)

    def test_no_truncation_below_cap(self) -> None:
        from unittest.mock import patch

        items = [
            {"number": 1, "title": "Only one", "repository": {"name": "noorinalabs-main"}},
        ]
        with patch.object(hook, "_run", return_value=json.dumps(items)):
            result = hook._get_open_prs()

        self.assertFalse(result.truncated)

    def test_unknown_repo_flagged(self) -> None:
        from unittest.mock import patch

        raw = json.dumps(
            [
                {
                    "number": 1,
                    "title": "New repo PR",
                    "repository": {"name": "noorinalabs-not-in-ssot"},
                },
            ]
        )
        with patch.object(hook, "_run", return_value=raw):
            result = hook._get_open_prs()

        self.assertEqual(result.unknown_repos, ("noorinalabs-not-in-ssot",))
        rendered = "\n".join(hook._render_prs_section(result))
        self.assertIn("noorinalabs-not-in-ssot", rendered)
        self.assertIn("SSOT list may be stale", rendered)

    def test_all_repos_is_org_repos_ssot(self) -> None:
        # session_handoff.ALL_REPOS must BE org_repos.ALL_REPOS (imported, not
        # re-derived) so the two can never drift apart again (kept intact
        # across main#1120 — #1243 flags the sibling validate_wave_audit.py
        # module for lacking this same guard, not this one).
        import org_repos

        self.assertIs(hook.ALL_REPOS, org_repos.ALL_REPOS)


class HandoffPathLocationTests(unittest.TestCase):
    """#741: the Stop hook must write the handoff into the in-repo,
    version-controlled .claude/memory/ — NOT the user-space auto-memory dir —
    so it and the /session-start skill agree on one file (no split-brain).
    """

    def test_handoff_file_is_in_repo_memory(self) -> None:
        expected = hook.REPO_ROOT / ".claude" / "memory" / "session_handoff.md"
        self.assertEqual(hook.HANDOFF_FILE, expected)

    def test_handoff_not_in_user_space(self) -> None:
        self.assertNotIn("/.claude/projects/", hook.HANDOFF_FILE.as_posix())
        self.assertFalse(hook.HANDOFF_FILE.is_relative_to(Path.home() / ".claude" / "projects"))

    def test_tracked_memory_index_autochurn_removed(self) -> None:
        # The Stop hook no longer auto-rewrites the tracked MEMORY.md index line
        # (#741); ensure the constant is gone so the churn can't silently return.
        self.assertFalse(hasattr(hook, "MEMORY_INDEX"))


class OntologyStalenessTests(unittest.TestCase):
    """#1142: the handoff's ontology line consumes the shared predicate.

    This line is what the NEXT session reads first, so a wrong "0 dirty files"
    here is a wrong belief carried across a session boundary — which is how the
    original miscount propagated into a handoff and was then re-litigated as a
    suspected "instrument disagreement".
    """

    def _with_checksums(self, payload: str) -> str:
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "ontology").mkdir()
            (root / "ontology" / "checksums.json").write_text(payload, encoding="utf-8")
            original = hook.REPO_ROOT
            try:
                hook.REPO_ROOT = root
                return hook._get_ontology_staleness()
            finally:
                hook.REPO_ROOT = original

    def test_clean_ledger_reports_current(self) -> None:
        payload = json.dumps(
            {"version": 1, "files": {"a.md": {"last_tracked": "1", "last_resolved": "1"}}}
        )
        self.assertEqual(self._with_checksums(payload), "Ontology is current (0 dirty files)")

    def test_dirty_entry_is_named(self) -> None:
        payload = json.dumps(
            {"version": 1, "files": {"a.md": {"last_tracked": "1", "last_resolved": "2"}}}
        )
        result = self._with_checksums(payload)
        self.assertIn("1 dirty files", result)
        self.assertIn("a.md", result)

    def test_malformed_entry_is_not_reported_as_current(self) -> None:
        """The exact committed shape that stayed invisible: `last_resolved: null`."""
        payload = json.dumps(
            {
                "version": 1,
                "files": {
                    "a.md": {"last_tracked": "1", "last_resolved": "1"},
                    "b.md": {"last_resolved": None, "resolved_at": "2026-06-14T00:16:00Z"},
                },
            }
        )
        result = self._with_checksums(payload)
        self.assertNotIn("current", result)
        self.assertIn("1 malformed entries", result)
        self.assertIn("b.md", result)

    def test_unparseable_ledger_is_not_reported_as_current(self) -> None:
        result = self._with_checksums("{not json")
        self.assertEqual(result, "Could not read checksums")


if __name__ == "__main__":
    unittest.main()
