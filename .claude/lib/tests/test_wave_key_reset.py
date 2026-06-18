"""Tests for wave_key_reset — the mechanical /wave-start § 5a per-phase
wave-key reset that replaces three defective hand-rolled bash probes (main#683).

Each defect from the issue has a dedicated regression test:

  Defect 1 — detection must fire for a SAME-PHASE re-use even when
             ``current_phase`` already equals the phase being started (the case
             the old ``current_phase != {P}`` guard could never catch), and must
             key off the wave's own phase stamps, never ``current_phase``.
  Defect 2 — detection must not depend on any lifecycle-marker key name
             (``wave_{M}_completed_at`` etc.); a wave that never wrapped up but
             carries a prior-phase scope stamp is still detected as stale.
  Defect 3 — the reset surface is prefix-complete: EVERY ``wave_{M}_*`` key is
             removed (incl. ``wave_{M}_branches`` — the dangerous omission),
             and ``wave_{M2}_*`` siblings are never touched (no ``wave_4`` vs
             ``wave_42`` prefix bleed).
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

# Helper lives at .claude/lib/wave_key_reset.py; this test is at
# .claude/lib/tests/test_*.py. parent.parent reaches the lib root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import wave_key_reset  # noqa: E402


def _p4w4_status() -> dict:
    """A file that has advanced to phase 5 (``current_phase`` == 5) but whose
    bare ``wave_4_*`` keys were all written by P4W4 — the exact collision state
    from the issue. The phase stamps inside the keys say 4."""
    return {
        "current_phase": 5,
        "wave_4_active": True,
        "wave_4_scope": {"phase": 4, "wave": 4, "theme": "P4W4 theme"},
        "wave_4_repos_in_scope": ["noorinalabs-isnad-graph"],
        "wave_4_branches": {"branch": "deployments/phase-4/wave-4", "created_at": "x"},
        "wave_4_meta_issue": "noorinalabs-main#400",
        "wave_4_final_pr_count": 19,
        "wave_4_wrapup_completed_at": "2026-05-01T00:00:00Z",
        # An unrelated sibling wave that must never be touched by a wave-4 reset.
        "wave_42_active": True,
        "last_updated": "2026-06-16T00:00:00Z",
    }


class TestBranchPhase(unittest.TestCase):
    def test_parses_phase_segment(self) -> None:
        self.assertEqual(wave_key_reset.branch_phase("deployments/phase-4/wave-4"), 4)
        self.assertEqual(wave_key_reset.branch_phase("deployments/phase-12/wave-3"), 12)

    def test_none_for_unstamped_or_non_string(self) -> None:
        self.assertIsNone(wave_key_reset.branch_phase("main"))
        self.assertIsNone(wave_key_reset.branch_phase(""))
        self.assertIsNone(wave_key_reset.branch_phase(None))  # type: ignore[arg-type]


class TestStampedPhases(unittest.TestCase):
    def test_collects_scope_and_branch_stamps(self) -> None:
        status = _p4w4_status()
        self.assertEqual(wave_key_reset.stamped_phases(status, 4), {4})

    def test_scope_and_branch_can_disagree(self) -> None:
        status = _p4w4_status()
        status["wave_4_branches"]["branch"] = "deployments/phase-3/wave-4"
        self.assertEqual(wave_key_reset.stamped_phases(status, 4), {3, 4})

    def test_empty_when_no_stamped_keys(self) -> None:
        self.assertEqual(wave_key_reset.stamped_phases({"current_phase": 5}, 4), set())

    def test_ignores_current_phase(self) -> None:
        # current_phase=5 must NOT leak into the stamp set (Defect 1 root cause).
        self.assertEqual(wave_key_reset.stamped_phases(_p4w4_status(), 4), {4})


class TestIsStaleReuse(unittest.TestCase):
    def test_defect1_detects_reuse_when_current_phase_already_matches(self) -> None:
        # current_phase == 5 == phase being started; the OLD guard
        # (current_phase != P) would be FALSE → miss it. The stamp says 4.
        status = _p4w4_status()
        stale, prior = wave_key_reset.is_stale_reuse(status, wave=4, phase=5)
        self.assertTrue(stale)
        self.assertEqual(prior, {4})

    def test_defect2_detected_without_lifecycle_marker(self) -> None:
        # No wave_4_completed_at / wave_4_wrapped_up_at at all — only the scope
        # stamp. Old probe found nothing; stamp-based detection still fires.
        status = _p4w4_status()
        del status["wave_4_wrapup_completed_at"]
        del status["wave_4_branches"]  # leave ONLY the scope stamp
        stale, prior = wave_key_reset.is_stale_reuse(status, wave=4, phase=5)
        self.assertTrue(stale)
        self.assertEqual(prior, {4})

    def test_not_stale_when_stamp_matches(self) -> None:
        # /wave-start re-run within the same phase (scope already phase 5).
        status = _p4w4_status()
        status["wave_4_scope"]["phase"] = 5
        status["wave_4_branches"]["branch"] = "deployments/phase-5/wave-4"
        stale, prior = wave_key_reset.is_stale_reuse(status, wave=4, phase=5)
        self.assertFalse(stale)
        self.assertEqual(prior, set())

    def test_not_stale_when_no_stamps(self) -> None:
        stale, prior = wave_key_reset.is_stale_reuse({"current_phase": 5}, wave=4, phase=5)
        self.assertFalse(stale)
        self.assertEqual(prior, set())


class TestStaleWaveKeys(unittest.TestCase):
    def test_defect3_surface_is_prefix_complete(self) -> None:
        keys = wave_key_reset.stale_wave_keys(_p4w4_status(), 4)
        # Every wave_4_* key — including the dangerous wave_4_branches.
        self.assertIn("wave_4_branches", keys)
        self.assertIn("wave_4_active", keys)
        self.assertIn("wave_4_scope", keys)
        self.assertIn("wave_4_meta_issue", keys)
        self.assertEqual(
            set(keys),
            {
                "wave_4_active",
                "wave_4_scope",
                "wave_4_repos_in_scope",
                "wave_4_branches",
                "wave_4_meta_issue",
                "wave_4_final_pr_count",
                "wave_4_wrapup_completed_at",
            },
        )

    def test_no_prefix_bleed_into_sibling_wave(self) -> None:
        keys = wave_key_reset.stale_wave_keys(_p4w4_status(), 4)
        self.assertNotIn("wave_42_active", keys)
        self.assertNotIn("current_phase", keys)
        self.assertNotIn("last_updated", keys)


class TestApplyEndToEnd(unittest.TestCase):
    def _write(self, status: dict) -> Path:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = Path(self.tmp.name) / "cross-repo-status.json"
        p.write_text(json.dumps(status, indent=2) + "\n")
        return p

    def test_apply_removes_only_stale_wave_keys(self) -> None:
        p = self._write(_p4w4_status())
        rc = wave_key_reset.main([str(p), "4", "5", "--apply"])
        self.assertEqual(rc, 0)

        result = json.loads(p.read_text())
        # All wave_4_* removed …
        self.assertFalse(any(k.startswith("wave_4_") for k in result))
        # … siblings + scalars preserved.
        self.assertEqual(result["wave_42_active"], True)
        self.assertEqual(result["current_phase"], 5)
        self.assertEqual(result["last_updated"], "2026-06-16T00:00:00Z")

    def test_apply_is_noop_when_not_stale(self) -> None:
        status = _p4w4_status()
        status["wave_4_scope"]["phase"] = 5
        status["wave_4_branches"]["branch"] = "deployments/phase-5/wave-4"
        p = self._write(status)
        before = p.read_text()

        rc = wave_key_reset.main([str(p), "4", "5", "--apply"])
        self.assertEqual(rc, 0)
        self.assertEqual(p.read_text(), before)  # untouched

    def test_dry_run_does_not_modify_file(self) -> None:
        p = self._write(_p4w4_status())
        before = p.read_text()
        rc = wave_key_reset.main([str(p), "4", "5"])  # no --apply
        self.assertEqual(rc, 0)
        self.assertEqual(p.read_text(), before)


if __name__ == "__main__":
    unittest.main()
