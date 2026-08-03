#!/usr/bin/env python3
"""Tests for validate_wave_audit hook (Hook 17, issue #195).

Covers the W8 hook-authorship-spec requirement: NEGATIVE MATCH coverage.
Each test documents which negative-space case it guards against.

Run: python3 -m pytest .claude/hooks/tests/test_validate_wave_audit.py -v
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import _test_helpers  # noqa: E402,F401
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


def _patch_audit(
    total: int | None,
    per_repo: dict[str, int] | None = None,
    unqueried: list[str] | None = None,
):
    """Context manager: patch hook._audit_open_count to return a fixed value.

    `unqueried` defaults to `[]` — full audit coverage (#1226). Note that every
    test using this helper is, by construction, blind to the aggregation loop
    it replaces; the loop's own behaviour is covered by
    `PartialAuditFailureCoverage` and `AuditOpenCountReportsCoverage`, which
    stub the subprocess boundary instead.
    """
    if per_repo is None:
        per_repo = {}
    return mock.patch.object(
        hook, "_audit_open_count", return_value=(total, per_repo, unqueried or [])
    )


def _patch_label(label: str | None):
    """Context manager: patch hook._read_current_wave_labels.

    Accepts a single label for call-site brevity and wraps it in the
    list the hook now returns (#810 dual-form). `None` passes through to
    model the no-active-wave / underivable case.
    """
    labels = None if label is None else [label]
    return mock.patch.object(hook, "_read_current_wave_labels", return_value=labels)


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
    """NEG — infra failures the audit never runs against fail OPEN with a warning.

    Total AUDIT coverage failure (every org-repo query failed, but the audit
    itself ran) is deliberately NOT covered here since #1230: it now BLOCKS for
    _COVERAGE_BLOCKING_SKILLS (`PartialAuditFailureCoverage`) and only fail-opens
    for skills outside that set (`test_audit_total_failure_allows_for_noncoverage_skill`
    below). What stays unconditionally fail-open regardless of skill is failure
    to even determine the active wave (no `cross-repo-status.json` / no active
    wave) — there the audit cannot run for ANY skill, coverage-blocking or not.
    """

    def test_no_active_wave_allows(self) -> None:
        """NEG: cross-repo-status.json has wave_active=false → allow with warning."""
        with _patch_label(None):
            result = hook.check(_skill_input("wave-wrapup"))
        assert result is not None
        self.assertEqual(result["decision"], "allow")
        self.assertIn("could not determine an active wave label", result["systemMessage"])

    def test_audit_total_failure_allows_for_noncoverage_skill(self) -> None:
        """NEG: every gh call failed (gh missing / no auth), /handoff → allow with warning.

        #1230: total failure only fail-opens for skills OUTSIDE
        _COVERAGE_BLOCKING_SKILLS. Pre-#1230 this test exercised "wave-wrapup"
        and asserted allow unconditionally — see
        `PartialAuditFailureCoverage.test_total_failure_blocks_coverage_blocking_skill`
        for the (now different) wave-wrapup/wave-retro behavior on the same input.
        """
        with _patch_label("p2-wave-10"), _patch_audit(None, {}):
            result = hook.check(_skill_input("handoff"))
        assert result is not None
        self.assertEqual(result["decision"], "allow")
        self.assertIn("could not query any of", result["systemMessage"])


class WaveLabelDerivation(unittest.TestCase):
    """Coverage on _read_current_wave_labels (#810 dual-form)."""

    def _write_status(self, payload: dict) -> Path:
        """Write a temp cross-repo-status.json and patch hook._STATUS_PATH at it."""
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(payload, tmp)
        tmp.close()
        return Path(tmp.name)

    def test_phase2_wave10_derives_both_forms(self) -> None:
        """Returns BOTH the legacy p{N}-wave-{M} AND the new wave-{X} form (#810).

        Phase comes from the authoritative `current_phase` integer (#831).
        """
        path = self._write_status(
            {"wave_active": True, "current_wave": "wave-10", "current_phase": 2}
        )
        try:
            with mock.patch.object(hook, "_STATUS_PATH", path):
                self.assertEqual(hook._read_current_wave_labels(), ["p2-wave-10", "wave-10"])
        finally:
            path.unlink()

    def test_current_phase_wins_over_stale_phase_string(self) -> None:
        """#831 regression: the live `current_phase` integer is authoritative;
        a stale top-level `phase` string (the never-advanced phase-4 legacy
        field) must be IGNORED for label derivation."""
        path = self._write_status(
            {
                "wave_active": True,
                "current_wave": "wave-17",
                "current_phase": 6,
                "phase": "phase-4",  # stale legacy field — must not win
            }
        )
        try:
            with mock.patch.object(hook, "_STATUS_PATH", path):
                self.assertEqual(hook._read_current_wave_labels(), ["p6-wave-17", "wave-17"])
        finally:
            path.unlink()

    def test_legacy_phase_string_fallback(self) -> None:
        """Defensive fallback: when `current_phase` is absent, the legacy
        `phase` ("phase-{N}") string still resolves (robustness)."""
        path = self._write_status(
            {"wave_active": True, "current_wave": "wave-10", "phase": "phase-2"}
        )
        try:
            with mock.patch.object(hook, "_STATUS_PATH", path):
                self.assertEqual(hook._read_current_wave_labels(), ["p2-wave-10", "wave-10"])
        finally:
            path.unlink()

    def test_inactive_wave_returns_none(self) -> None:
        path = self._write_status(
            {"wave_active": False, "current_wave": "wave-10", "current_phase": 2}
        )
        try:
            with mock.patch.object(hook, "_STATUS_PATH", path):
                self.assertIsNone(hook._read_current_wave_labels())
        finally:
            path.unlink()

    def test_missing_file_returns_none(self) -> None:
        with mock.patch.object(hook, "_STATUS_PATH", Path("/tmp/nonexistent-no-thanks.json")):
            self.assertIsNone(hook._read_current_wave_labels())

    def test_malformed_current_wave_returns_none(self) -> None:
        path = self._write_status(
            {"wave_active": True, "current_wave": "not-a-wave", "current_phase": 2}
        )
        try:
            with mock.patch.object(hook, "_STATUS_PATH", path):
                self.assertIsNone(hook._read_current_wave_labels())
        finally:
            path.unlink()

    def test_missing_both_phase_fields_returns_none(self) -> None:
        """No `current_phase` AND no `phase` → phase unresolvable → None."""
        path = self._write_status({"wave_active": True, "current_wave": "wave-10"})
        try:
            with mock.patch.object(hook, "_STATUS_PATH", path):
                self.assertIsNone(hook._read_current_wave_labels())
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


class WaveBranchDerivation(unittest.TestCase):
    """Coverage on _read_current_wave_branch (#664 exemption target)."""

    def _write_status(self, payload: dict) -> Path:
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(payload, tmp)
        tmp.close()
        return Path(tmp.name)

    def test_phase5_wave5_derives_branch(self) -> None:
        path = self._write_status(
            {"wave_active": True, "current_wave": "wave-5", "current_phase": 5}
        )
        try:
            with mock.patch.object(hook, "_STATUS_PATH", path):
                self.assertEqual(hook._read_current_wave_branch(), "deployments/phase-5/wave-5")
        finally:
            path.unlink()

    def test_branch_uses_current_phase_not_stale_phase_string(self) -> None:
        """#831 core regression: branch derivation must read the authoritative
        `current_phase` (6), NOT the stale top-level `phase` ("phase-4"). The
        bug derived `deployments/phase-4/...`; the fix derives phase-6."""
        path = self._write_status(
            {
                "wave_active": True,
                "current_wave": "wave-17",
                "current_phase": 6,
                "phase": "phase-4",  # stale legacy field — must not win
            }
        )
        try:
            with mock.patch.object(hook, "_STATUS_PATH", path):
                self.assertEqual(hook._read_current_wave_branch(), "deployments/phase-6/wave-17")
        finally:
            path.unlink()

    def test_inactive_wave_returns_none(self) -> None:
        path = self._write_status(
            {"wave_active": False, "current_wave": "wave-5", "current_phase": 5}
        )
        try:
            with mock.patch.object(hook, "_STATUS_PATH", path):
                self.assertIsNone(hook._read_current_wave_branch())
        finally:
            path.unlink()

    def test_missing_file_returns_none(self) -> None:
        with mock.patch.object(hook, "_STATUS_PATH", Path("/tmp/nope-664.json")):
            self.assertIsNone(hook._read_current_wave_branch())

    def test_label_and_branch_share_phase_wave(self) -> None:
        """Label and branch must derive from the SAME phase/wave (no drift)."""
        path = self._write_status(
            {"wave_active": True, "current_wave": "wave-12", "current_phase": 3}
        )
        try:
            with mock.patch.object(hook, "_STATUS_PATH", path):
                self.assertEqual(hook._read_current_wave_labels(), ["p3-wave-12", "wave-12"])
                self.assertEqual(hook._read_current_wave_branch(), "deployments/phase-3/wave-12")
        finally:
            path.unlink()


class PhaseNumDerivation(unittest.TestCase):
    """Direct coverage on _read_phase_num — the authoritative phase reader (#831)."""

    def test_current_phase_int_preferred(self) -> None:
        self.assertEqual(hook._read_phase_num({"current_phase": 6, "phase": "phase-4"}), 6)

    def test_current_phase_string_coerced(self) -> None:
        """A stringified `current_phase` ("6") still coerces to int."""
        self.assertEqual(hook._read_phase_num({"current_phase": "6"}), 6)

    def test_falls_back_to_phase_string(self) -> None:
        self.assertEqual(hook._read_phase_num({"phase": "phase-2"}), 2)

    def test_unparseable_current_phase_falls_back_to_phase_string(self) -> None:
        self.assertEqual(hook._read_phase_num({"current_phase": "n/a", "phase": "phase-7"}), 7)

    def test_neither_field_returns_none(self) -> None:
        self.assertIsNone(hook._read_phase_num({}))

    def test_malformed_phase_string_returns_none(self) -> None:
        self.assertIsNone(hook._read_phase_num({"phase": "phase-x"}))


class ChecksGreen(unittest.TestCase):
    """Coverage on _checks_green — the green-CI half of merge-ready (#664)."""

    def test_empty_rollup_is_green(self) -> None:
        """No checks configured → green (linkage + base guards carry safety)."""
        self.assertTrue(hook._checks_green([]))
        self.assertTrue(hook._checks_green(None))

    def test_all_success_checkruns_green(self) -> None:
        rollup = [
            {"status": "COMPLETED", "conclusion": "SUCCESS"},
            {"status": "COMPLETED", "conclusion": "SKIPPED"},
            {"status": "COMPLETED", "conclusion": "NEUTRAL"},
        ]
        self.assertTrue(hook._checks_green(rollup))

    def test_failing_checkrun_not_green(self) -> None:
        rollup = [
            {"status": "COMPLETED", "conclusion": "SUCCESS"},
            {"status": "COMPLETED", "conclusion": "FAILURE"},
        ]
        self.assertFalse(hook._checks_green(rollup))

    def test_pending_checkrun_not_green(self) -> None:
        """NEG: an in-progress check is NOT green (conservative — no false-exempt)."""
        rollup = [{"status": "IN_PROGRESS", "conclusion": ""}]
        self.assertFalse(hook._checks_green(rollup))

    def test_statuscontext_success_green(self) -> None:
        self.assertTrue(hook._checks_green([{"state": "SUCCESS"}]))

    def test_statuscontext_pending_not_green(self) -> None:
        self.assertFalse(hook._checks_green([{"state": "PENDING"}]))

    def test_statuscontext_failure_not_green(self) -> None:
        self.assertFalse(hook._checks_green([{"state": "ERROR"}]))

    def test_unrecognized_shape_not_green(self) -> None:
        """NEG: a shape with neither conclusion/status nor state → not green."""
        self.assertFalse(hook._checks_green([{"weird": "value"}]))

    def test_non_dict_element_not_green(self) -> None:
        self.assertFalse(hook._checks_green(["not-a-dict"]))


class PrIsMergeReady(unittest.TestCase):
    """Coverage on _pr_is_merge_ready — the false-exempt guard (#664 acc. #3)."""

    _WAVE = "deployments/phase-5/wave-5"

    def _pr(self, **overrides) -> dict:
        pr = {
            "number": 700,
            "isDraft": False,
            "state": "OPEN",
            "baseRefName": self._WAVE,
            "mergeable": "MERGEABLE",
            "statusCheckRollup": [{"status": "COMPLETED", "conclusion": "SUCCESS"}],
        }
        pr.update(overrides)
        return pr

    def test_ready_pr_is_ready(self) -> None:
        self.assertTrue(hook._pr_is_merge_ready(self._pr(), self._WAVE))

    def test_draft_not_ready(self) -> None:
        self.assertFalse(hook._pr_is_merge_ready(self._pr(isDraft=True), self._WAVE))

    def test_wrong_base_not_ready(self) -> None:
        """NEG: a PR into main (not the wave branch) must NOT exempt — acc. #3."""
        self.assertFalse(hook._pr_is_merge_ready(self._pr(baseRefName="main"), self._WAVE))

    def test_conflicting_not_ready(self) -> None:
        self.assertFalse(hook._pr_is_merge_ready(self._pr(mergeable="CONFLICTING"), self._WAVE))

    def test_unknown_mergeable_not_ready(self) -> None:
        """NEG: UNKNOWN (GitHub still computing) is conservatively not-ready."""
        self.assertFalse(hook._pr_is_merge_ready(self._pr(mergeable="UNKNOWN"), self._WAVE))

    def test_red_checks_not_ready(self) -> None:
        self.assertFalse(
            hook._pr_is_merge_ready(
                self._pr(statusCheckRollup=[{"status": "COMPLETED", "conclusion": "FAILURE"}]),
                self._WAVE,
            )
        )

    def test_closed_state_not_ready(self) -> None:
        self.assertFalse(hook._pr_is_merge_ready(self._pr(state="MERGED"), self._WAVE))


class CountOpenWithExemption(unittest.TestCase):
    """Coverage on _count_open_for_repo merge-ready-PR exemption (#664)."""

    _LABELS = ["p5-wave-5", "wave-5"]

    def test_no_open_issues_returns_zero(self) -> None:
        with mock.patch.object(hook, "_open_issue_numbers_for_repo", return_value=[]):
            self.assertEqual(
                hook._count_open_for_repo(
                    "noorinalabs-main", self._LABELS, "deployments/phase-5/wave-5"
                ),
                0,
            )

    def test_issue_list_failure_returns_none(self) -> None:
        """NEG: issue-list subprocess failure → None (caller fails open)."""
        with mock.patch.object(hook, "_open_issue_numbers_for_repo", return_value=None):
            self.assertIsNone(
                hook._count_open_for_repo(
                    "noorinalabs-main", self._LABELS, "deployments/phase-5/wave-5"
                )
            )

    def test_no_wave_branch_counts_all(self) -> None:
        """NEG: branch underivable → no exemption applied, every issue counts."""
        with mock.patch.object(hook, "_open_issue_numbers_for_repo", return_value=[1, 2, 3]):
            self.assertEqual(hook._count_open_for_repo("noorinalabs-main", self._LABELS, None), 3)

    def test_exempt_issues_subtracted(self) -> None:
        """POS: issues with a merge-ready wave-branch PR are subtracted."""
        with (
            mock.patch.object(hook, "_open_issue_numbers_for_repo", return_value=[10, 11, 12]),
            mock.patch.object(hook, "_mergeready_exempt_issues", return_value={11, 12}),
        ):
            self.assertEqual(
                hook._count_open_for_repo(
                    "noorinalabs-main", self._LABELS, "deployments/phase-5/wave-5"
                ),
                1,
            )

    def test_all_exempt_returns_zero(self) -> None:
        """POS: every open issue exempt → 0 (the wrapup chicken-and-egg fix)."""
        with (
            mock.patch.object(hook, "_open_issue_numbers_for_repo", return_value=[10, 11]),
            mock.patch.object(hook, "_mergeready_exempt_issues", return_value={10, 11}),
        ):
            self.assertEqual(
                hook._count_open_for_repo(
                    "noorinalabs-main", self._LABELS, "deployments/phase-5/wave-5"
                ),
                0,
            )

    def test_exempt_set_failure_counts_all(self) -> None:
        """NEG: PR-list failure → empty exempt set → all issues count (fail strict)."""
        with (
            mock.patch.object(hook, "_open_issue_numbers_for_repo", return_value=[10, 11]),
            mock.patch.object(hook, "_mergeready_exempt_issues", return_value=set()),
        ):
            self.assertEqual(
                hook._count_open_for_repo(
                    "noorinalabs-main", self._LABELS, "deployments/phase-5/wave-5"
                ),
                2,
            )


class ClosingRefsInText(unittest.TestCase):
    """Coverage on _closing_refs_in_text — PR-body/title linkage parse (#664).

    Linkage is parsed from body/title because GitHub's structured
    closingIssuesReferences is always empty for wave-branch-based PRs (it only
    populates for default-branch PRs).
    """

    def test_closes_matches(self) -> None:
        self.assertEqual(hook._closing_refs_in_text("Closes #664."), {664})

    def test_keyword_conjugations_match(self) -> None:
        for text in (
            "close #1",
            "closed #1",
            "Fixes #1",
            "fix #1",
            "fixed #1",
            "Resolves #1",
            "resolved #1",
        ):
            with self.subTest(text=text):
                self.assertEqual(hook._closing_refs_in_text(text), {1})

    def test_colon_separator_matches(self) -> None:
        self.assertEqual(hook._closing_refs_in_text("Closes: #5"), {5})

    def test_multiple_refs_collected(self) -> None:
        text = "Closes #1\nbody\nFixes #2 and resolves #3"
        self.assertEqual(hook._closing_refs_in_text(text), {1, 2, 3})

    def test_bare_mention_does_not_match(self) -> None:
        """NEG: a passing '#664' mention without a keyword must NOT exempt (acc. #3)."""
        self.assertEqual(hook._closing_refs_in_text("see #664 for context"), set())

    def test_cross_repo_ref_not_matched(self) -> None:
        """NEG: 'Closes octo/repo#5' is a different repo's issue — not local."""
        self.assertEqual(hook._closing_refs_in_text("Closes octo/repo#5"), set())

    def test_prefix_word_not_matched(self) -> None:
        """NEG: 'prefix #5' must not match the 'fix' substring."""
        self.assertEqual(hook._closing_refs_in_text("prefix #5"), set())

    def test_no_separator_not_matched(self) -> None:
        """NEG: GitHub requires whitespace/colon; 'Closes#5' does not link."""
        self.assertEqual(hook._closing_refs_in_text("Closes#5"), set())

    def test_empty_text(self) -> None:
        self.assertEqual(hook._closing_refs_in_text(""), set())


class MergereadyExemptIssuesSubprocess(unittest.TestCase):
    """Coverage on _mergeready_exempt_issues gh shell-out + body-linkage parse."""

    _WAVE = "deployments/phase-5/wave-5"

    def _completed(self, stdout: str, returncode: int = 0):
        m = mock.Mock()
        m.stdout = stdout
        m.returncode = returncode
        return m

    def _ready_pr(self, number: int, body: str = "", title: str = "") -> dict:
        return {
            "number": number,
            "isDraft": False,
            "state": "OPEN",
            "baseRefName": self._WAVE,
            "mergeable": "MERGEABLE",
            "statusCheckRollup": [{"status": "COMPLETED", "conclusion": "SUCCESS"}],
            "body": body,
            "title": title,
        }

    def test_collects_declared_closes_of_ready_prs(self) -> None:
        """POS: a ready PR's body closing-keyword refs become the exempt set."""
        prs = json.dumps([self._ready_pr(700, body="Fix.\n\nCloses #42\nFixes #43")])
        with mock.patch.object(hook.subprocess, "run", return_value=self._completed(prs)):
            result = hook._mergeready_exempt_issues("noorinalabs-main", self._WAVE)
        self.assertEqual(result, {42, 43})

    def test_title_ref_also_collected(self) -> None:
        """POS: a closing keyword in the title also links."""
        prs = json.dumps([self._ready_pr(700, body="no refs", title="thing (resolves #44)")])
        with mock.patch.object(hook.subprocess, "run", return_value=self._completed(prs)):
            result = hook._mergeready_exempt_issues("noorinalabs-main", self._WAVE)
        self.assertEqual(result, {44})

    def test_not_ready_pr_links_ignored(self) -> None:
        """NEG: a draft PR's closing refs never become exempt."""
        draft = self._ready_pr(701, body="Closes #50")
        draft["isDraft"] = True
        prs = json.dumps([draft])
        with mock.patch.object(hook.subprocess, "run", return_value=self._completed(prs)):
            result = hook._mergeready_exempt_issues("noorinalabs-main", self._WAVE)
        self.assertEqual(result, set())

    def test_bare_mention_in_ready_pr_not_exempt(self) -> None:
        """NEG: a ready PR that only *mentions* #50 (no keyword) does not exempt it."""
        prs = json.dumps([self._ready_pr(700, body="related to #50 but does other work")])
        with mock.patch.object(hook.subprocess, "run", return_value=self._completed(prs)):
            result = hook._mergeready_exempt_issues("noorinalabs-main", self._WAVE)
        self.assertEqual(result, set())

    def test_pr_list_failure_returns_empty_set(self) -> None:
        """NEG: gh pr list nonzero exit → empty set (fail strict, no false-exempt)."""
        with mock.patch.object(
            hook.subprocess, "run", return_value=self._completed("", returncode=1)
        ):
            self.assertEqual(hook._mergeready_exempt_issues("noorinalabs-main", self._WAVE), set())

    def test_pr_list_filenotfound_returns_empty_set(self) -> None:
        with mock.patch.object(hook.subprocess, "run", side_effect=FileNotFoundError):
            self.assertEqual(hook._mergeready_exempt_issues("noorinalabs-main", self._WAVE), set())

    def test_pr_list_malformed_json_returns_empty_set(self) -> None:
        with mock.patch.object(hook.subprocess, "run", return_value=self._completed("not json")):
            self.assertEqual(hook._mergeready_exempt_issues("noorinalabs-main", self._WAVE), set())


class OpenIssueNumbersForLabelSubprocess(unittest.TestCase):
    """Coverage on _open_issue_numbers_for_label gh shell-out (per single label)."""

    def _completed(self, stdout: str, returncode: int = 0):
        m = mock.Mock()
        m.stdout = stdout
        m.returncode = returncode
        return m

    def test_parses_numbers(self) -> None:
        payload = json.dumps([{"number": 1}, {"number": 2}, {"number": 3}])
        with mock.patch.object(hook.subprocess, "run", return_value=self._completed(payload)):
            self.assertEqual(
                hook._open_issue_numbers_for_label("noorinalabs-main", "p5-wave-5"),
                [1, 2, 3],
            )

    def test_empty_output_is_empty_list(self) -> None:
        with mock.patch.object(hook.subprocess, "run", return_value=self._completed("")):
            self.assertEqual(
                hook._open_issue_numbers_for_label("noorinalabs-main", "p5-wave-5"), []
            )

    def test_failure_returns_none(self) -> None:
        with mock.patch.object(
            hook.subprocess, "run", return_value=self._completed("", returncode=1)
        ):
            self.assertIsNone(hook._open_issue_numbers_for_label("noorinalabs-main", "p5-wave-5"))

    def test_malformed_json_returns_none(self) -> None:
        with mock.patch.object(hook.subprocess, "run", return_value=self._completed("nope")):
            self.assertIsNone(hook._open_issue_numbers_for_label("noorinalabs-main", "p5-wave-5"))


class OpenIssueNumbersUnion(unittest.TestCase):
    """Coverage on _open_issue_numbers_for_repo dual-form UNION (#810)."""

    def test_unions_across_label_forms_dedup(self) -> None:
        """POS: legacy + new label results are unioned and deduplicated."""

        def _per_label(repo, label):
            return {"p5-wave-5": [10, 11], "wave-5": [11, 12]}[label]

        with mock.patch.object(hook, "_open_issue_numbers_for_label", side_effect=_per_label):
            self.assertEqual(
                hook._open_issue_numbers_for_repo("noorinalabs-main", ["p5-wave-5", "wave-5"]),
                [10, 11, 12],
            )

    def test_any_label_query_failure_returns_none(self) -> None:
        """NEG: if ANY per-label query fails → None (caller fails open per-repo)."""

        def _per_label(repo, label):
            return [10] if label == "p5-wave-5" else None

        with mock.patch.object(hook, "_open_issue_numbers_for_label", side_effect=_per_label):
            self.assertIsNone(
                hook._open_issue_numbers_for_repo("noorinalabs-main", ["p5-wave-5", "wave-5"])
            )

    def test_new_form_only_issue_counts(self) -> None:
        """POS: an issue carrying ONLY the new wave-{X} form still registers."""

        def _per_label(repo, label):
            return [] if label == "p5-wave-5" else [42]

        with mock.patch.object(hook, "_open_issue_numbers_for_label", side_effect=_per_label):
            self.assertEqual(
                hook._open_issue_numbers_for_repo("noorinalabs-main", ["p5-wave-5", "wave-5"]),
                [42],
            )


class PartialAuditFailureCoverage(unittest.TestCase):
    """#1226 — a PARTIAL per-repo query failure must never produce a bare allow.

    Why these tests stub `_open_issue_numbers_for_label` and not `_audit_open_count`:
    every pre-existing test in this file injects `_audit_open_count`'s *return
    value* (`_patch_audit`), so no test in the suite has ever executed the
    aggregation loop — which is precisely why this defect survived. Stubbing at
    the subprocess boundary (the leaf that shells out to `gh`) makes the real
    `_audit_open_count` → `_count_open_for_repo` → `_open_issue_numbers_for_repo`
    chain run for all 8 org repos, exactly as it does in production.

    Ground truth is the live distribution measured 2026-08-02: `noorinalabs-main`
    carries 30 open `wave-29` issues and the other 7 repos carry 0. That skew is
    the whole danger — ONE failed query, on main, used to sum to a confident 0.
    """

    _LABELS = ["p10-wave-29", "wave-29"]
    # repo → open wave-issue numbers. Absent repo == queried, found nothing.
    _TRUTH = {"noorinalabs-main": list(range(1, 31))}

    def _run(
        self,
        failing_repos: set[str],
        skill: str = "wave-wrapup",
        args: str = "",
        wave_branch: str | None = None,
        exempt: set[int] | None = None,
    ):
        """Drive the real aggregation loop with `failing_repos` failing to query.

        Returns `(result, queried_repos)`. `queried_repos` is the inertness
        guard: it proves the loop actually ran over every org repo rather than
        short-circuiting before the assertions could mean anything.
        """
        queried: list[str] = []

        def _stub(repo: str, label: str):
            queried.append(repo)
            if repo in failing_repos:
                # Exactly what a non-zero `gh` exit / timeout yields.
                return None
            return list(self._TRUTH.get(repo, []))

        patches = [
            mock.patch.object(hook, "_read_current_wave_labels", return_value=self._LABELS),
            mock.patch.object(hook, "_read_current_wave_branch", return_value=wave_branch),
            mock.patch.object(hook, "_open_issue_numbers_for_label", side_effect=_stub),
            mock.patch.object(hook, "_mergeready_exempt_issues", return_value=exempt or set()),
        ]
        with patches[0], patches[1], patches[2], patches[3]:
            result = hook.check(_skill_input(skill, args=args))
        return result, set(queried)

    def _assert_loop_ran(self, queried: set[str]) -> None:
        """Guard against an inert test: every org repo must have been attempted."""
        self.assertEqual(
            queried,
            set(hook._ORG_REPOS),
            "aggregation loop did not attempt every org repo — this test would be inert",
        )

    # -- the reproduction matrix from issue #1226 ------------------------------

    def test_baseline_all_repos_queried_blocks(self) -> None:
        """CONTROL: full coverage, 30 open in main → block. (Passes pre-fix.)"""
        result, queried = self._run(set())
        self._assert_loop_ran(queried)
        assert result is not None
        self.assertEqual(result["decision"], "block")
        self.assertIn("Open items across the org: 30", result["reason"])

    def test_only_main_fails_is_not_a_bare_allow(self) -> None:
        """1-of-8, the dangerous case: main unqueried → MUST NOT be a bare allow.

        Pre-fix this returns None (exit 0, no output) — indistinguishable from
        a genuinely clean wave.
        """
        result, queried = self._run({"noorinalabs-main"})
        self._assert_loop_ran(queried)
        self.assertIsNotNone(
            result,
            "partial audit failure returned a BARE ALLOW (no decision, no message) — #1226",
        )

    def test_only_main_fails_blocks_wave_wrapup(self) -> None:
        """1-of-8 → /wave-wrapup blocks, naming the repo it could not see."""
        result, queried = self._run({"noorinalabs-main"})
        self._assert_loop_ran(queried)
        assert result is not None
        self.assertEqual(result["decision"], "block")
        self.assertIn("noorinalabs-main", result["reason"])
        self.assertIn("could not be queried", result["reason"])

    def test_two_repos_fail_names_both(self) -> None:
        """2-of-8 → block, both unqueried repos named."""
        result, queried = self._run({"noorinalabs-main", "noorinalabs-deploy"})
        self._assert_loop_ran(queried)
        assert result is not None
        self.assertEqual(result["decision"], "block")
        self.assertIn("noorinalabs-main", result["reason"])
        self.assertIn("noorinalabs-deploy", result["reason"])

    def test_zero_issue_repo_failure_still_reports_the_gap(self) -> None:
        """1-of-8 on a repo that has no issues: the total is unchanged (30) and
        the gate still blocks on open items — but the incomplete coverage MUST
        still be surfaced, because the audit cannot know that repo was empty."""
        result, queried = self._run({"noorinalabs-isnad-graph"})
        self._assert_loop_ran(queried)
        assert result is not None
        self.assertEqual(result["decision"], "block")
        self.assertIn("noorinalabs-isnad-graph", result["reason"])
        self.assertIn("NOT AUDITED", result["reason"])

    def test_total_failure_blocks_coverage_blocking_skill(self) -> None:
        """#1230: all 8 fail, /wave-wrapup → BLOCK, not allow.

        Pre-#1230 this was `test_total_failure_still_allows_with_warning`, a
        CONTROL pinning the old (buggy) contract that total failure fail-opens
        UNCONDITIONALLY — even for _COVERAGE_BLOCKING_SKILLS. That was the
        asymmetry itself: an 8-of-8 blind spot was MORE permissive than the
        1-of-8 gap `test_only_main_fails_blocks_wave_wrapup` already blocks.
        Renamed and re-asserted rather than deleted, since the input (all 8
        org repos failing) is still exactly the scenario worth a named test.
        """
        result, queried = self._run(set(hook._ORG_REPOS))
        self._assert_loop_ran(queried)
        assert result is not None
        self.assertEqual(result["decision"], "block")
        self.assertIn("could not run AT ALL", result["reason"])
        self.assertIn("any of the 8 org repo(s)", result["reason"])

    def test_total_failure_blocks_wave_retro(self) -> None:
        """#1230: total failure blocks /wave-retro too, not just /wave-wrapup."""
        result, queried = self._run(set(hook._ORG_REPOS), skill="wave-retro")
        self._assert_loop_ran(queried)
        assert result is not None
        self.assertEqual(result["decision"], "block")

    def test_total_failure_carry_forward_does_not_clear_the_block(self) -> None:
        """#1230: a carry-forward marker cannot vouch for a wave nothing was
        read from — same reasoning as `test_carry_forward_does_not_clear_a_coverage_block`
        for the partial case, now extended to total failure."""
        args = "Wrapup. Carry-forward: #194 → wave-30, #845 → backlog"
        result, queried = self._run(set(hook._ORG_REPOS), args=args)
        self._assert_loop_ran(queried)
        assert result is not None
        self.assertEqual(result["decision"], "block")

    def test_total_failure_still_allows_handoff_with_warning(self) -> None:
        """CONTROL: all 8 fail, /handoff → unchanged fail-open WITH warning.
        `/handoff` sits outside _COVERAGE_BLOCKING_SKILLS on both the partial
        AND total path — #1230 only closed the gap for wave-wrapup/wave-retro."""
        result, queried = self._run(set(hook._ORG_REPOS), skill="handoff")
        self._assert_loop_ran(queried)
        assert result is not None
        self.assertEqual(result["decision"], "allow")
        self.assertIn("could not query any of", result["systemMessage"])

    def test_partial_failure_is_never_quieter_than_total_failure(self) -> None:
        """The acceptance criterion stated directly: the partial path must carry
        at least as much operator signal as the total path it sits beside.

        Re-expressed per #1234 (which flagged the original version of this test
        for pinning total failure to an *absolute* allow-shaped verdict, when
        the property in its own name is *relative* signal strength, not verdict
        kind). #1234 was right that the old assertion pre-decided #1230 by
        accident; #1230 has now RULED — total failure blocks alongside partial
        failure for a coverage-blocking skill — so this test compares signal
        presence on both sides rather than asserting either verdict is "allow".
        It still holds, and now for a stronger reason: both sides are BLOCK.
        """
        partial, q1 = self._run({"noorinalabs-main"})
        total, q2 = self._run(set(hook._ORG_REPOS))
        self._assert_loop_ran(q1)
        self._assert_loop_ran(q2)
        assert total is not None, "total failure was SILENT — must carry operator signal"
        total_signal = total.get("reason") or total.get("systemMessage")
        self.assertTrue(total_signal, "total failure produced no operator-visible text")
        assert partial is not None, "partial failure was SILENT while total failure warned"
        partial_signal = partial.get("reason") or partial.get("systemMessage")
        self.assertTrue(partial_signal, "partial failure produced no operator-visible text")
        # The actual "never quieter" property: block (a `reason`, logged and
        # non-bypassable-by-carry-forward) is never a quieter signal than an
        # allow-with-warning `systemMessage`. Both are BLOCK here post-#1230.
        self.assertEqual(partial["decision"], "block")
        self.assertEqual(total["decision"], "block")

    # -- per-skill policy -----------------------------------------------------

    def test_wave_retro_partial_failure_blocks(self) -> None:
        """/wave-retro writes the durable wave record → coverage-blocking."""
        result, queried = self._run({"noorinalabs-main"}, skill="wave-retro")
        self._assert_loop_ran(queried)
        assert result is not None
        self.assertEqual(result["decision"], "block")

    def test_handoff_partial_failure_allows_with_explicit_warning(self) -> None:
        """/handoff is deliberately NOT coverage-blocked — hard-blocking it on a
        transient API failure would strand a session with no way to record
        state. It allows, but LOUDLY and never bare."""
        result, queried = self._run({"noorinalabs-main"}, skill="handoff")
        self._assert_loop_ran(queried)
        assert result is not None
        self.assertEqual(result["decision"], "allow")
        self.assertIn("noorinalabs-main", result["systemMessage"])
        self.assertIn("LOWER BOUND", result["systemMessage"])

    def test_coverage_blocking_skills_are_a_subset_of_gated_skills(self) -> None:
        """Drift guard: a coverage-blocking skill the hook never fires on is dead
        policy, and would silently narrow the gate."""
        self.assertTrue(hook._COVERAGE_BLOCKING_SKILLS <= hook._GATED_SKILLS)
        self.assertNotIn("handoff", hook._COVERAGE_BLOCKING_SKILLS)

    def test_carry_forward_does_not_clear_a_coverage_block(self) -> None:
        """A carry-forward marker acknowledges items the operator has SEEN. An
        unqueried repo was never read, so the marker cannot speak for it."""
        args = "Wrapup. Carry-forward: #194 → wave-30, #845 → backlog"
        result, queried = self._run({"noorinalabs-main"}, args=args)
        self._assert_loop_ran(queried)
        assert result is not None
        self.assertEqual(result["decision"], "block")
        self.assertIn("carry-forward", result["reason"].lower())

    def test_coverage_block_survives_the_mergeready_exemption(self) -> None:
        """#664's exemption cannot paper over a coverage gap: even with every
        *visible* issue exempted, an unqueried repo still blocks."""
        result, queried = self._run(
            {"noorinalabs-main"},
            wave_branch="deployments/phase-10/wave-29",
            exempt=set(range(1, 31)),
        )
        self._assert_loop_ran(queried)
        assert result is not None
        self.assertEqual(result["decision"], "block")

    def test_full_coverage_genuine_zero_still_allows_silently(self) -> None:
        """NEG: the fix must not make a genuinely clean wave noisy. Full
        coverage + zero open → bare allow, as before."""
        with mock.patch.dict(self._TRUTH, {}, clear=True):
            result, queried = self._run(set())
        self._assert_loop_ran(queried)
        self.assertIsNone(result)


class AuditOpenCountReportsCoverage(unittest.TestCase):
    """#1226 — the aggregator must record failed repos, not discard them."""

    _LABELS = ["p10-wave-29", "wave-29"]

    def _audit(self, failing_repos: set[str], truth: dict[str, list[int]]):
        def _stub(repo: str, label: str):
            return None if repo in failing_repos else list(truth.get(repo, []))

        with mock.patch.object(hook, "_open_issue_numbers_for_label", side_effect=_stub):
            return hook._audit_open_count(self._LABELS, None)

    def test_returns_unqueried_repo_names(self) -> None:
        out = self._audit({"noorinalabs-main"}, {"noorinalabs-main": [1, 2, 3]})
        self.assertEqual(
            len(out), 3, "aggregator must report which repos it could not query (#1226)"
        )
        total, per_repo, unqueried = out
        self.assertEqual(unqueried, ["noorinalabs-main"])
        self.assertEqual(per_repo, {})
        self.assertEqual(total, 0)  # a LOWER BOUND — check() must not trust it alone

    def test_full_coverage_reports_no_gaps(self) -> None:
        out = self._audit(set(), {"noorinalabs-deploy": [7, 8]})
        self.assertEqual(len(out), 3)
        total, per_repo, unqueried = out
        self.assertEqual(unqueried, [])
        self.assertEqual(per_repo, {"noorinalabs-deploy": 2})
        self.assertEqual(total, 2)

    def test_total_failure_lists_every_repo_as_unqueried(self) -> None:
        out = self._audit(set(hook._ORG_REPOS), {})
        self.assertEqual(len(out), 3)
        total, _per_repo, unqueried = out
        self.assertIsNone(total)
        self.assertEqual(sorted(unqueried), sorted(hook._ORG_REPOS))


class FormatPerRepoCoverage(unittest.TestCase):
    """#1226 — the summary must never imply the audit saw repos it did not."""

    def test_no_false_all_returned_zero_claim_when_repos_skipped(self) -> None:
        out = hook._format_per_repo({}, ["noorinalabs-main"])
        self.assertNotIn("all audited repos returned 0", out)
        self.assertIn("noorinalabs-main", out)
        self.assertIn("NOT AUDITED", out)

    def test_skipped_repos_listed_alongside_counts(self) -> None:
        out = hook._format_per_repo({"noorinalabs-deploy": 4}, ["noorinalabs-main"])
        self.assertIn("noorinalabs/noorinalabs-deploy: 4 open", out)
        self.assertIn("noorinalabs-main", out)
        self.assertIn("NOT AUDITED", out)

    def test_full_coverage_zero_keeps_the_all_zero_line(self) -> None:
        out = hook._format_per_repo({}, [])
        self.assertIn("returned 0", out)
        self.assertNotIn("NOT AUDITED", out)


class CheckEndToEndExemption(unittest.TestCase):
    """check() integration: a fully-exempt wave allows /wave-wrapup (#664)."""

    def test_all_issues_exempt_allows_wrapup(self) -> None:
        """POS: the only open wave issues have merge-ready wave-branch PRs → allow.

        Exercises the real _audit_open_count → _count_open_for_repo exemption
        path, mocking only the subprocess-touching leaves.
        """

        def _issues(repo, labels):
            return [664] if repo == "noorinalabs-main" else []

        with (
            mock.patch.object(
                hook, "_read_current_wave_labels", return_value=["p5-wave-5", "wave-5"]
            ),
            mock.patch.object(
                hook, "_read_current_wave_branch", return_value="deployments/phase-5/wave-5"
            ),
            mock.patch.object(hook, "_open_issue_numbers_for_repo", side_effect=_issues),
            mock.patch.object(hook, "_mergeready_exempt_issues", return_value={664}),
        ):
            result = hook.check(_skill_input("wave-wrapup"))
        self.assertIsNone(result)

    def test_non_exempt_issue_still_blocks(self) -> None:
        """NEG: an open wave issue WITHOUT a merge-ready PR still blocks wrapup."""

        def _issues(repo, labels):
            return [664] if repo == "noorinalabs-main" else []

        with (
            mock.patch.object(
                hook, "_read_current_wave_labels", return_value=["p5-wave-5", "wave-5"]
            ),
            mock.patch.object(
                hook, "_read_current_wave_branch", return_value="deployments/phase-5/wave-5"
            ),
            mock.patch.object(hook, "_open_issue_numbers_for_repo", side_effect=_issues),
            mock.patch.object(hook, "_mergeready_exempt_issues", return_value=set()),
        ):
            result = hook.check(_skill_input("wave-wrapup"))
        assert result is not None
        self.assertEqual(result["decision"], "block")
        self.assertIn("noorinalabs-main", result["reason"])
        self.assertIn("Open items across the org: 1", result["reason"])


if __name__ == "__main__":
    unittest.main()
