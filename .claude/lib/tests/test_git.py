#!/usr/bin/env python3
"""Tests for git.py::run_git — the shared `git` subprocess shim (main#1121).

Mirrors the shape of gh.py's usage tests. Mutation-focused: both the
"success" and "raw-propagation" ends of the contract are exercised.
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve().parent
_LIB_DIR = _HERE.parent
sys.path.insert(0, str(_LIB_DIR))

import git as g  # noqa: E402


class RunGitArgListTests(unittest.TestCase):
    """No shell string, ever — an explicit arg list only (main#688)."""

    def test_builds_explicit_arg_list_never_a_shell_string(self) -> None:
        fake = mock.MagicMock(
            return_value=subprocess.CompletedProcess(
                args=["git", "status"], returncode=0, stdout="clean\n", stderr=""
            )
        )
        with mock.patch.object(subprocess, "run", fake):
            out = g.run_git(["status", "--short"], timeout=5)
        self.assertEqual(out, "clean\n")
        called_args, called_kwargs = fake.call_args
        self.assertEqual(called_args[0], ["git", "status", "--short"])
        self.assertNotIn("shell", called_kwargs)  # never shell=True
        self.assertTrue(called_kwargs.get("check"))
        self.assertTrue(called_kwargs.get("capture_output"))
        self.assertTrue(called_kwargs.get("text"))
        self.assertEqual(called_kwargs.get("timeout"), 5)

    def test_timeout_is_required_not_defaulted(self) -> None:
        """No shared default — every hand-rolled site disagreed (10/15/20s);
        picking one silently changes behavior for whoever didn't use it."""
        with self.assertRaises(TypeError):
            g.run_git(["status"])  # type: ignore[call-arg]


class RunGitRawPropagationTests(unittest.TestCase):
    """Errors propagate RAW — never wrapped — matching gh.run_gh's stance
    (see module docstring § Error behaviour mirrors gh.run_gh)."""

    def test_nonzero_exit_raises_called_process_error_raw(self) -> None:
        with mock.patch.object(
            subprocess,
            "run",
            side_effect=subprocess.CalledProcessError(128, ["git", "status"]),
        ):
            with self.assertRaises(subprocess.CalledProcessError):
                g.run_git(["status"], timeout=5)

    def test_timeout_raises_timeout_expired_raw(self) -> None:
        with mock.patch.object(
            subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(cmd=["git", "fetch"], timeout=5),
        ):
            with self.assertRaises(subprocess.TimeoutExpired):
                g.run_git(["fetch"], timeout=5)

    def test_missing_binary_raises_file_not_found_raw(self) -> None:
        with mock.patch.object(subprocess, "run", side_effect=FileNotFoundError("no git")):
            with self.assertRaises(FileNotFoundError):
                g.run_git(["status"], timeout=5)

    def test_no_ge_error_wrapper_class_exists_on_the_module(self) -> None:
        """Deliberate absence: gh.py needed GhError for verify_deployable_merge's
        wrapper; no converted git call site needs an analogous wrapper (all of
        them already caught the raw stdlib exception types) — so this module
        must NOT grow one that no caller asked for."""
        self.assertFalse(hasattr(g, "GitError"))


if __name__ == "__main__":
    unittest.main()
