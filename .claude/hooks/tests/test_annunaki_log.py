#!/usr/bin/env python3
"""Tests for `annunaki_log` (#452 test-mode suppression).

Coverage focuses on the env-var-gated write suppression that prevents the
hook test suite from polluting production error log with ~293 fixture
entries per run.

Run from the repo root:
    ENVIRONMENT=test python3 -m pytest \\
        .claude/hooks/tests/test_annunaki_log.py -v
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
sys.path.insert(0, str(_HOOKS_DIR))

import annunaki_log as alog  # noqa: E402


class IsTestModeTests(unittest.TestCase):
    """Pure-function coverage for `_is_test_mode`."""

    def setUp(self):
        # Save and clear both env vars so each test starts clean.
        self._saved = {
            "ENVIRONMENT": os.environ.pop("ENVIRONMENT", None),
            "NOORIN_HOOK_TEST_MODE": os.environ.pop("NOORIN_HOOK_TEST_MODE", None),
        }

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_unset_returns_false(self):
        self.assertFalse(alog._is_test_mode())

    def test_environment_test_returns_true(self):
        os.environ["ENVIRONMENT"] = "test"
        self.assertTrue(alog._is_test_mode())

    def test_environment_production_returns_false(self):
        os.environ["ENVIRONMENT"] = "production"
        self.assertFalse(alog._is_test_mode())

    def test_environment_empty_returns_false(self):
        os.environ["ENVIRONMENT"] = ""
        self.assertFalse(alog._is_test_mode())

    def test_noorin_hook_test_mode_1_returns_true(self):
        os.environ["NOORIN_HOOK_TEST_MODE"] = "1"
        self.assertTrue(alog._is_test_mode())

    def test_noorin_hook_test_mode_0_returns_false(self):
        """Unix-tradition truthy-only — literal `1` is the only true value."""
        os.environ["NOORIN_HOOK_TEST_MODE"] = "0"
        self.assertFalse(alog._is_test_mode())

    def test_noorin_hook_test_mode_true_string_returns_false(self):
        """`true` does NOT activate — only literal `1`."""
        os.environ["NOORIN_HOOK_TEST_MODE"] = "true"
        self.assertFalse(alog._is_test_mode())

    def test_either_env_var_set_suffices(self):
        """The two env vars are OR-combined."""
        os.environ["NOORIN_HOOK_TEST_MODE"] = "1"
        os.environ["ENVIRONMENT"] = "production"  # ENVIRONMENT not test
        self.assertTrue(alog._is_test_mode())


class SuppressionTests(unittest.TestCase):
    """End-to-end: when test-mode is active, `append_jsonl_record` MUST NOT
    write to the file. When test-mode is inactive, it MUST write."""

    def setUp(self):
        self._saved = {
            "ENVIRONMENT": os.environ.pop("ENVIRONMENT", None),
            "NOORIN_HOOK_TEST_MODE": os.environ.pop("NOORIN_HOOK_TEST_MODE", None),
        }

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_environment_test_suppresses_write(self):
        os.environ["ENVIRONMENT"] = "test"
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "errors.jsonl"
            alog.append_jsonl_record(target, {"test": "fixture"})
            self.assertFalse(target.exists(), "ENVIRONMENT=test must suppress annunaki writes")

    def test_noorin_hook_test_mode_suppresses_write(self):
        os.environ["NOORIN_HOOK_TEST_MODE"] = "1"
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "errors.jsonl"
            alog.append_jsonl_record(target, {"test": "fixture"})
            self.assertFalse(target.exists(), "NOORIN_HOOK_TEST_MODE=1 must suppress writes")

    def test_production_env_does_not_suppress_write(self):
        """The whole point: when neither env var is set, writes go through."""
        # Both env vars cleared in setUp.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "errors.jsonl"
            alog.append_jsonl_record(target, {"production": "real_error"})
            self.assertTrue(
                target.exists(),
                "Production mode (no test-mode env vars) must allow writes",
            )
            content = target.read_text()
            self.assertIn("real_error", content)

    def test_log_pretooluse_block_respects_suppression(self):
        """The higher-level log_pretooluse_block helper also gets suppressed
        in test mode (it goes through append_jsonl_record)."""
        os.environ["ENVIRONMENT"] = "test"
        # The hook's ERRORS_FILE is hardcoded; we redirect by temporarily
        # patching the module attribute, which is the same shape the
        # _wipe_cache pattern uses elsewhere in the test suite.
        with tempfile.TemporaryDirectory() as tmp:
            orig = alog.ERRORS_FILE
            alog.ERRORS_FILE = Path(tmp) / "errors.jsonl"
            try:
                alog.log_pretooluse_block("some_hook", "gh issue create --label fake", "blocked")
                self.assertFalse(
                    alog.ERRORS_FILE.exists(),
                    "log_pretooluse_block must also be suppressed in test mode",
                )
            finally:
                alog.ERRORS_FILE = orig

    def test_log_posttooluse_event_respects_suppression(self):
        os.environ["ENVIRONMENT"] = "test"
        with tempfile.TemporaryDirectory() as tmp:
            orig = alog.ERRORS_FILE
            alog.ERRORS_FILE = Path(tmp) / "errors.jsonl"
            try:
                alog.log_posttooluse_event("some_hook", "gh issue create", "advisory")
                self.assertFalse(
                    alog.ERRORS_FILE.exists(),
                    "log_posttooluse_event must also be suppressed in test mode",
                )
            finally:
                alog.ERRORS_FILE = orig


if __name__ == "__main__":
    unittest.main(verbosity=2)
