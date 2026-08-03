#!/usr/bin/env python3
"""Tests for validate_lockfile_paths.py's `run_git` wiring (main#1121).

The pre-#1121 hand-rolled `subprocess.run` calls inspected `.returncode` and
silently returned `[]`/no-offending on a non-zero exit or missing binary.
`run_git` raises instead (`check=True`) — this suite proves the fail-open
behavior survived the conversion (both `except` clauses now catch
`CalledProcessError` too).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
sys.path.insert(0, str(_HOOKS_DIR))

import validate_lockfile_paths as vlp  # noqa: E402


def test_get_staged_lockfiles_filters_to_package_lock_json():
    with mock.patch.object(
        vlp,
        "run_git",
        return_value="package-lock.json\nsrc/app.py\nnested/package-lock.json\n",
    ) as mock_run_git:
        result = vlp.get_staged_lockfiles()
    assert result == ["package-lock.json", "nested/package-lock.json"]
    mock_run_git.assert_called_once_with(
        ["diff", "--cached", "--name-only", "--diff-filter=ACM"], timeout=10
    )


def test_get_staged_lockfiles_fails_open_on_called_process_error():
    with mock.patch.object(
        vlp, "run_git", side_effect=subprocess.CalledProcessError(128, ["git", "diff"])
    ):
        assert vlp.get_staged_lockfiles() == []


def test_get_staged_lockfiles_fails_open_on_timeout():
    with mock.patch.object(
        vlp, "run_git", side_effect=subprocess.TimeoutExpired(cmd=["git", "diff"], timeout=10)
    ):
        assert vlp.get_staged_lockfiles() == []


def test_get_staged_lockfiles_fails_open_on_missing_git():
    with mock.patch.object(vlp, "run_git", side_effect=FileNotFoundError("no git")):
        assert vlp.get_staged_lockfiles() == []


def test_check_lockfile_flags_tmp_path():
    with mock.patch.object(vlp, "run_git", return_value='{"resolved": "file:/tmp/foo"}\n'):
        offending = vlp.check_lockfile("package-lock.json")
    assert len(offending) == 1
    assert "package-lock.json:1" in offending[0]


def test_check_lockfile_clean_file_returns_empty():
    with mock.patch.object(vlp, "run_git", return_value='{"resolved": "https://registry/x"}\n'):
        assert vlp.check_lockfile("package-lock.json") == []


def test_check_lockfile_fails_open_on_called_process_error():
    with mock.patch.object(
        vlp, "run_git", side_effect=subprocess.CalledProcessError(128, ["git", "show"])
    ):
        assert vlp.check_lockfile("package-lock.json") == []


def test_check_never_calls_gh():
    """Positive instrument pairing (#1318): this hook never shells out to
    `gh` — confirmed by asserting `run_git` (not some other binary) is the
    one and only subprocess seam it uses."""
    with mock.patch.object(vlp, "run_git", return_value="") as mock_run_git:
        vlp.check({"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}})
    assert mock_run_git.called


def test_check_end_to_end_block_on_local_path():
    with (
        mock.patch.object(vlp, "get_staged_lockfiles", return_value=["package-lock.json"]),
        mock.patch.object(
            vlp, "check_lockfile", return_value=["  package-lock.json:3: file:/tmp/x"]
        ),
        mock.patch.object(vlp, "log_pretooluse_block"),
    ):
        result = vlp.check({"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}})
    assert result["decision"] == "block"
    assert "package-lock.json:3" in result["reason"]
