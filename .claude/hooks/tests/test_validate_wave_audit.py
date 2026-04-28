#!/usr/bin/env python3
"""Tests for validate_wave_audit hook (Hook 17, issue #195).

Covers the W8 hook-authorship-spec requirement: NEGATIVE MATCH coverage.
Each test documents which negative-space case it guards against.

Run: python3 -m pytest .claude/hooks/tests/test_validate_wave_audit.py -v
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
sys.path.insert(0, str(_HOOKS_DIR))

import validate_wave_audit as hook  # noqa: E402


def _skill_input(skill_name: str, args: str = "") -> dict:
    """Build a hook input dict for a Skill call."""
    return {
        "tool_name": "Skill",
        "tool_input": {"skill": skill_name, "args": args},
    }


def _bash_input(command: str) -> dict:
    """Build a hook input dict for a Bash call (for matcher-scoping tests)."""
    return {
        "tool_name": "Bash",
        "tool_input": {"command": command},
    }


def _patch_audit(total: int | None, per_repo: dict[str, int] | None = None):
    """Context manager: patch hook._audit_open_count to return a fixed value."""
    if per_repo is None:
        per_repo = {}
    return mock.patch.object(hook, "_audit_open_count", return_value=(total, per_repo))


def _patch_label(label: str | None):
    """Context manager: patch hook._read_current_wave_label."""
    return mock.patch.object(hook, "_read_current_wave_label", return_value=label)


class GatedSkillBlocking(unittest.TestCase):
    """POS — gated skills with open items and no carry-forward → block."""

    def test_wave_wrapup_with_open_items_blocks(self) -> None:
        """POS: /wave-wrapup with open items, no carry-forward → block."""
        with _patch_label("p2-wave-10"), _patch_audit(5, {"noorinalabs-deploy": 5}):
            result = hook.check(_skill_input("wave-wrapup"))
        assert result is not None
        self.assertEqual(result["decision"], "block")
        self.assertIn("p2-wave-10", result["reason"])
        self.assertIn("5", result["reason"])
        self.assertIn("noorinalabs-deploy", result["reason"])

    def test_wave_retro_with_open_items_blocks(self) -> None:
        """POS: /wave-retro is also gated."""
        with _patch_label("p2-wave-10"), _patch_audit(3, {"noorinalabs-main": 3}):
            result = hook.check(_skill_input("wave-retro"))
        assert result is not None
        self.assertEqual(result["decision"], "block")

    def test_handoff_with_open_items_blocks(self) -> None:
        """POS: /handoff is also gated."""
        with _patch_label("p2-wave-10"), _patch_audit(1, {"noorinalabs-isnad-graph": 1}):
            result = hook.check(_skill_input("handoff"))
        assert result is not None
        self.assertEqual(result["decision"], "block")


class CarryForwardWarnsButAllows(unittest.TestCase):
    """POS — gated skills with open items but carry-forward in args → allow with warning."""

    def test_inline_marker_allows(self) -> None:
        """POS: 'Carry-forward: #N → next-wave' inline marker passes."""
        args = "Wave-10 wrapup. Carry-forward: #194 → wave-11, #845 → backlog"
        with _patch_label("p2-wave-10"), _patch_audit(2, {"noorinalabs-main": 2}):
            result = hook.check(_skill_input("wave-wrapup", args=args))
        assert result is not None
        self.assertEqual(result["decision"], "allow")
        self.assertIn("carry-forward marker detected", result["systemMessage"])

    def test_heading_marker_allows(self) -> None:
        """POS: '## Carry-forward' markdown heading passes."""
        args = "## Carry-forward\n\n- #194 → next wave\n- #845 → backlog"
        with _patch_label("p2-wave-10"), _patch_audit(2, {"noorinalabs-main": 2}):
            result = hook.check(_skill_input("wave-wrapup", args=args))
        assert result is not None
        self.assertEqual(result["decision"], "allow")

    def test_arrow_pattern_allows(self) -> None:
        """POS: bare '#N → destination' arrow pattern passes."""
        args = "Items: #194 → wave-11. #845 → backlog. Done."
        with _patch_label("p2-wave-10"), _patch_audit(2, {"noorinalabs-main": 2}):
            result = hook.check(_skill_input("wave-wrapup", args=args))
        assert result is not None
        self.assertEqual(result["decision"], "allow")


class NegativeMatchScoping(unittest.TestCase):
    """NEG — inputs that look like matches but are intentionally excluded."""

    def test_non_gated_skill_does_not_block(self) -> None:
        """NEG: /ontology-librarian is not gated — must allow without audit."""
        with _patch_label("p2-wave-10"), _patch_audit(99, {"noorinalabs-main": 99}):
            result = hook.check(_skill_input("ontology-librarian"))
        self.assertIsNone(result)

    def test_session_start_does_not_block(self) -> None:
        """NEG: /session-start is not gated."""
        with _patch_label("p2-wave-10"), _patch_audit(99, {"noorinalabs-main": 99}):
            result = hook.check(_skill_input("session-start"))
        self.assertIsNone(result)

    def test_bash_with_wave_wrapup_substring_does_not_block(self) -> None:
        """NEG: Bash containing 'wave-wrapup' as substring (substring-bug guard, kin of #216).

        The hook fires on `tool_name == "Skill"` only. A bash invocation
        like `echo "running wave-wrapup later"` MUST NOT trigger.
        """
        result = hook.check(_bash_input('echo "running wave-wrapup later"'))
        self.assertIsNone(result)

    def test_bash_with_handoff_substring_does_not_block(self) -> None:
        """NEG: Bash containing 'handoff' as substring."""
        result = hook.check(_bash_input("git log --grep handoff"))
        self.assertIsNone(result)

    def test_zero_open_items_allows(self) -> None:
        """NEG: gated skill with 0 open items → allow without warning."""
        with _patch_label("p2-wave-10"), _patch_audit(0, {}):
            result = hook.check(_skill_input("wave-wrapup"))
        self.assertIsNone(result)


class FailOpenInfrastructure(unittest.TestCase):
    """NEG — infrastructure failures fail OPEN with system warning, never block."""

    def test_no_active_wave_allows(self) -> None:
        """NEG: cross-repo-status.json has wave_active=false → allow with warning."""
        with _patch_label(None):
            result = hook.check(_skill_input("wave-wrapup"))
        assert result is not None
        self.assertEqual(result["decision"], "allow")
        self.assertIn("could not determine an active wave label", result["systemMessage"])

    def test_audit_total_failure_allows(self) -> None:
        """NEG: every gh call failed (gh missing / no auth) → allow with warning."""
        with _patch_label("p2-wave-10"), _patch_audit(None, {}):
            result = hook.check(_skill_input("wave-wrapup"))
        assert result is not None
        self.assertEqual(result["decision"], "allow")
        self.assertIn("could not query any of", result["systemMessage"])


class WaveLabelDerivation(unittest.TestCase):
    """Coverage on _read_current_wave_label."""

    def _write_status(self, payload: dict) -> Path:
        """Write a temp cross-repo-status.json and patch hook._STATUS_PATH at it."""
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(payload, tmp)
        tmp.close()
        return Path(tmp.name)

    def test_phase2_wave10_derives_correctly(self) -> None:
        path = self._write_status(
            {"wave_active": True, "current_wave": "wave-10", "phase": "phase-2"}
        )
        try:
            with mock.patch.object(hook, "_STATUS_PATH", path):
                self.assertEqual(hook._read_current_wave_label(), "p2-wave-10")
        finally:
            path.unlink()

    def test_inactive_wave_returns_none(self) -> None:
        path = self._write_status(
            {"wave_active": False, "current_wave": "wave-10", "phase": "phase-2"}
        )
        try:
            with mock.patch.object(hook, "_STATUS_PATH", path):
                self.assertIsNone(hook._read_current_wave_label())
        finally:
            path.unlink()

    def test_missing_file_returns_none(self) -> None:
        with mock.patch.object(hook, "_STATUS_PATH", Path("/tmp/nonexistent-no-thanks.json")):
            self.assertIsNone(hook._read_current_wave_label())

    def test_malformed_current_wave_returns_none(self) -> None:
        path = self._write_status(
            {"wave_active": True, "current_wave": "not-a-wave", "phase": "phase-2"}
        )
        try:
            with mock.patch.object(hook, "_STATUS_PATH", path):
                self.assertIsNone(hook._read_current_wave_label())
        finally:
            path.unlink()


class CarryForwardDetection(unittest.TestCase):
    """Coverage on _has_carry_forward — the bypass surface needs to be precise."""

    def test_inline_carry_forward_colon_matches(self) -> None:
        self.assertTrue(hook._has_carry_forward("foo Carry-forward: #1 → backlog"))

    def test_carry_space_forward_matches(self) -> None:
        self.assertTrue(hook._has_carry_forward("Carry forward: #1 → backlog"))

    def test_case_insensitive(self) -> None:
        self.assertTrue(hook._has_carry_forward("CARRY-FORWARD: items"))

    def test_heading_marker_matches(self) -> None:
        self.assertTrue(hook._has_carry_forward("# Wrapup\n\n## Carry-forward\n- #1"))

    def test_arrow_pattern_matches(self) -> None:
        self.assertTrue(hook._has_carry_forward("Items: #194 → wave-11"))

    def test_arrow_with_ascii_arrow_matches(self) -> None:
        self.assertTrue(hook._has_carry_forward("Items: #194 -> wave-11"))

    def test_no_marker_does_not_match(self) -> None:
        """NEG: prose mentioning carry-forward concept without the structured marker."""
        self.assertFalse(hook._has_carry_forward("we are going to carry these forward eventually"))

    def test_empty_args_does_not_match(self) -> None:
        self.assertFalse(hook._has_carry_forward(""))

    def test_unrelated_arrows_do_not_falsely_match(self) -> None:
        """NEG: '#123 -> 456' without word destination does not falsely match."""
        # The pattern requires \w after the arrow — bare numbers should not.
        # This guards against accidental matches in numeric diffs.
        self.assertFalse(hook._has_carry_forward("count: #123 -> 456"))


if __name__ == "__main__":
    unittest.main()
