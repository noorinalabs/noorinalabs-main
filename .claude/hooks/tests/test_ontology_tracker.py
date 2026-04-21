#!/usr/bin/env python3
"""Tests for ontology_tracker hook path filtering.

Covers the W8 hook-authorship-spec requirement: NEGATIVE MATCH coverage for
the three noise patterns in issue #143 (/tmp, .claude/worktrees, out-of-repo)
plus a positive case (real source file inside the repo).

Run: python3 -m pytest .claude/hooks/tests/test_ontology_tracker.py -v
Or:  python3 .claude/hooks/tests/test_ontology_tracker.py
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

import ontology_tracker as hook  # noqa: E402


class ShouldSkipNegativeTests(unittest.TestCase):
    """Negative-match coverage for the three issue-#143 noise patterns."""

    def test_tmp_prefix_is_skipped(self):
        """/tmp/* — ephemeral scratch (issue-body staging files)."""
        self.assertTrue(hook._should_skip("/tmp/issue-body-1234.md"))

    def test_tmp_nested_is_skipped(self):
        """/tmp/<dir>/<file> — also ephemeral."""
        self.assertTrue(hook._should_skip("/tmp/staging/notes.md"))

    def test_worktree_inside_repo_is_skipped(self):
        """.claude/worktrees/** — in-flight copies of tracked files.

        The eventual merge-to-main triggers a separate Edit on the canonical
        repo path; double-tracking the worktree copy pollutes checksums with
        stale paths once the worktree is removed.
        """
        wt_path = str(
            hook.REPO_ROOT
            / ".claude"
            / "worktrees"
            / "A.Virtanen-0143-tracker"
            / "ontology"
            / "services.yaml"
        )
        self.assertTrue(hook._should_skip(wt_path))

    def test_worktree_substring_anywhere_is_skipped(self):
        """The worktrees marker need only appear as a substring in the path."""
        self.assertTrue(hook._should_skip("/some/other/root/.claude/worktrees/foo/bar.md"))

    def test_out_of_repo_absolute_path_is_skipped(self):
        """Files outside REPO_ROOT (e.g. user auto-memory) — out of scope."""
        # Use a real existing path that is guaranteed outside REPO_ROOT
        # so resolve() does not fail. /etc/hostname is universally readable
        # on Linux test runners.
        self.assertTrue(hook._should_skip("/etc/hostname"))

    def test_home_memory_path_is_skipped(self):
        """The exact pattern reported in #143: user auto-memory files.

        Out-of-repo absolute paths (e.g. ``/home/.../.claude/projects/.../
        memory/MEMORY.md``) must be skipped because they are outside
        REPO_ROOT.
        """
        self.assertTrue(
            hook._should_skip("/home/parameterization/.claude/projects/foo/memory/MEMORY.md")
        )


class ShouldSkipPositiveTests(unittest.TestCase):
    """Positive regression — real in-repo source files MUST still track.

    These tests construct paths inside a temporary fake "repo root" with
    REPO_ROOT monkey-patched so they pass identically whether the test
    runner is checked out in the main repo or a worktree (worktree paths
    contain the ``.claude/worktrees/`` substring which is — correctly —
    skipped by the new filter).
    """

    def setUp(self):
        # Fake repo root must be outside both "/tmp/" (skipped by SKIP_PREFIXES)
        # and any "/.claude/worktrees/" (skipped by SKIP_PATTERNS). Place it
        # under the user's home directory.
        base = Path.home() / ".cache" / "noorinalabs-test-ontology-tracker"
        base.mkdir(parents=True, exist_ok=True)
        self._tmp = tempfile.TemporaryDirectory(prefix="ont_track_pos_", dir=str(base))
        self._fake_root = Path(self._tmp.name).resolve()
        self._orig_root = hook.REPO_ROOT
        hook.REPO_ROOT = self._fake_root

    def tearDown(self):
        hook.REPO_ROOT = self._orig_root
        self._tmp.cleanup()

    def test_in_repo_ontology_yaml_is_tracked(self):
        """ontology/services.yaml under REPO_ROOT — the canonical positive case."""
        path = str(self._fake_root / "ontology" / "services.yaml")
        self.assertFalse(hook._should_skip(path))

    def test_in_repo_relative_path_is_tracked(self):
        """A relative in-repo path resolves under REPO_ROOT and is tracked."""
        cwd = os.getcwd()
        try:
            os.chdir(self._fake_root)
            self.assertFalse(hook._should_skip("ontology/conventions.md"))
        finally:
            os.chdir(cwd)

    def test_in_repo_hook_file_is_tracked(self):
        """A source file inside .claude/hooks/ should be tracked."""
        path = str(self._fake_root / ".claude" / "hooks" / "ontology_tracker.py")
        self.assertFalse(hook._should_skip(path))


class ShouldSkipExistingFiltersTests(unittest.TestCase):
    """Regression — pre-existing SKIP_PATTERNS keep working."""

    def test_checksums_file_is_skipped(self):
        self.assertTrue(hook._should_skip("ontology/checksums.json"))

    def test_pycache_is_skipped(self):
        self.assertTrue(hook._should_skip("foo/__pycache__/bar.cpython-312.pyc"))

    def test_git_dir_is_skipped(self):
        self.assertTrue(hook._should_skip(".git/HEAD"))

    def test_annunaki_log_is_skipped(self):
        self.assertTrue(hook._should_skip(".claude/annunaki/errors.jsonl"))


if __name__ == "__main__":
    unittest.main()
