#!/usr/bin/env python3
"""Tests for ontology_tracker hook path filtering.

Covers the W8 hook-authorship-spec requirement: NEGATIVE MATCH coverage for
the three noise patterns in issue #143 (/tmp, .claude/worktrees, out-of-repo)
plus a positive case (real source file inside the repo).

Run: python3 -m pytest .claude/hooks/tests/test_ontology_tracker.py -v
Or:  python3 .claude/hooks/tests/test_ontology_tracker.py
"""

from __future__ import annotations

import json
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


class _FakeRepoRootMixin:
    """Monkeypatch ``hook.REPO_ROOT`` to a fresh non-worktree temp dir.

    Any test that builds a fixture path under ``hook.REPO_ROOT`` must be
    independent of *where pytest is invoked from*. The real ``REPO_ROOT`` is
    derived from ``__file__`` (``…/parent/parent/parent``), so when the suite
    runs from a linked worktree under ``.claude/worktrees/`` it itself
    contains a ``.worktrees`` path component. A fixture like
    ``REPO_ROOT / "docs" / "notes.worktrees.md"`` would then spuriously match
    ``_is_worktree_path`` and the negative-case assertion would FALSE-fail
    (#686) — even though the same test is green on a normal checkout and in
    CI. Anchoring fixtures under a temp dir that is outside both ``/tmp/``
    (skipped by ``SKIP_PREFIXES``) and any ``*/.worktrees/`` tree (skipped by
    the segment check) keeps them invocation-location independent.
    """

    def setUp(self):
        super().setUp()
        # Place the fake root under the user's home cache directory so it is
        # outside /tmp/ and outside any worktree tree (see class docstring).
        base = Path.home() / ".cache" / "noorinalabs-test-ontology-tracker"
        base.mkdir(parents=True, exist_ok=True)
        self._tmp = tempfile.TemporaryDirectory(prefix="ont_track_", dir=str(base))
        self._fake_root = Path(self._tmp.name).resolve()
        self._orig_root = hook.REPO_ROOT
        hook.REPO_ROOT = self._fake_root

    def tearDown(self):
        hook.REPO_ROOT = self._orig_root
        self._tmp.cleanup()
        super().tearDown()


class ShouldSkipPositiveTests(_FakeRepoRootMixin, unittest.TestCase):
    """Positive regression — real in-repo source files MUST still track.

    These tests construct paths inside a temporary fake "repo root" (see
    ``_FakeRepoRootMixin``) so they pass identically whether the test runner
    is checked out in the main repo or a worktree.
    """

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

    def test_semantic_overlay_repo_yaml_is_tracked(self):
        """#857: the hand-curated overlay (ontology/repos/*.yaml) IS still tracked.

        Only the GENERATED structural layer is dropped from tracking; the
        semantic overlay remains under the tracker/resolver.
        """
        path = str(self._fake_root / "ontology" / "repos" / "isnad-graph.yaml")
        self.assertFalse(hook._should_skip(path))


class ShouldSkipStructuralLayerTests(_FakeRepoRootMixin, unittest.TestCase):
    """#857: the GENERATED structural layer must NOT be checksum-tracked.

    ``ontology/structural/`` is regenerated wholesale by an owned generator
    (#855); it is always-current-by-regeneration, so dirty-tracking it would be
    meaningless churn and ``/ontology-rebuild`` has nothing to resolve there.
    The tracker skips it exactly like it skips ``checksums.json`` itself.
    """

    def test_structural_yaml_is_skipped_absolute(self):
        path = str(self._fake_root / "ontology" / "structural" / "modules.yaml")
        self.assertTrue(hook._should_skip(path))

    def test_structural_nested_is_skipped(self):
        path = str(self._fake_root / "ontology" / "structural" / "isnad-graph" / "index.json")
        self.assertTrue(hook._should_skip(path))

    def test_structural_relative_path_is_skipped(self):
        self.assertTrue(hook._should_skip("ontology/structural/services.yaml"))


class ShouldSkipTopLevelWorktreesTests(_FakeRepoRootMixin, unittest.TestCase):
    """#525: top-level `.worktrees/` paths must be skipped.

    The change-tracker anchors on the orchestrator cwd; an Edit inside a
    worktree gets recorded as a worktree-relative path like
    ``.worktrees/deploy-0348-aisha/...``. Pre-#525 only ``.claude/worktrees/``
    was skipped, so the top-level convention (gitignored as of #523) polluted
    the parent ``checksums.json`` with entries that never resolve and once
    aborted a ``git merge --ff-only``.

    Uses ``_FakeRepoRootMixin`` so the ``REPO_ROOT``-anchored fixtures below
    are independent of whether pytest runs from the main checkout or a linked
    worktree (#686).
    """

    def test_relative_top_level_worktrees_path_is_skipped(self):
        """The exact #525 evidence shape — a worktree-relative path."""
        self.assertTrue(
            hook._should_skip(".worktrees/deploy-0348-aisha/terraform/cloudflare/variables.tf")
        )

    def test_relative_top_level_worktrees_status_file_is_skipped(self):
        self.assertTrue(hook._should_skip(".worktrees/main-w11-unblock/cross-repo-status.json"))

    def test_absolute_top_level_worktrees_path_is_skipped(self):
        wt = str(hook.REPO_ROOT / ".worktrees" / "0528-cwd-anchor" / "ontology" / "domain.yaml")
        self.assertTrue(hook._should_skip(wt))

    def test_worktrees_segment_not_substring_false_match(self):
        """A file merely NAMED with a worktrees substring is NOT skipped.

        Segment-matching (not substring) guards against skipping a real
        source file like ``notes.worktrees.md`` — only a path COMPONENT of
        ``.worktrees`` triggers the skip.
        """
        # Place it under REPO_ROOT so the out-of-repo filter doesn't fire.
        legit = str(hook.REPO_ROOT / "docs" / "notes.worktrees.md")
        self.assertFalse(hook._is_worktree_path(legit))

    def test_claude_worktrees_still_skipped_via_segment(self):
        """The historical convention is also caught by the segment check."""
        self.assertTrue(
            hook._is_worktree_path(".claude/worktrees/A.Virtanen-0143/ontology/services.yaml")
        )

    def test_bare_worktrees_dir_without_claude_parent_not_skipped(self):
        """A dir literally named ``worktrees`` but NOT under ``.claude`` is fine."""
        self.assertFalse(hook._is_worktree_path("src/worktrees/helper.py"))


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


class ShouldSkipSessionHandoffTests(_FakeRepoRootMixin, unittest.TestCase):
    """#1038: the gitignored, machine-local session handoff must NOT be tracked.

    ``.claude/memory/session_handoff.md`` is gitignored and untracked in git,
    yet the ``Stop`` hook rewrites it after ~every response. Tracking it dirtied
    the COMMITTED ``ontology/checksums.json`` every session, so ``/session-start``
    Step 3a reported phantom drift and ``/ontology-rebuild`` had a phantom entry
    to resolve, forever — eroding a gate whose only value is that "0 dirty"
    means something. Same class as ``.claude/annunaki/errors.jsonl``.
    """

    def test_relative_handoff_path_is_skipped(self):
        """A repo-relative handoff path is skipped BY THE PATTERN, not by luck.

        The ``os.chdir`` here is load-bearing — do not remove it (#1043).
        ``_should_skip`` resolves a relative path against the *process cwd*, not
        against the patched ``REPO_ROOT``. Without the chdir this path resolves
        somewhere outside the fake root and is caught by the pre-existing
        out-of-repo rule, so the assertion passes even when the
        ``SKIP_PATTERNS`` entry under test is deleted — an inert test that
        reports green while covering nothing. Anchoring cwd to the fake root
        puts the path *inside* the repo, so the pattern is the only thing that
        can produce the skip and the test genuinely dies if it is removed.

        Relative paths are worth covering: the tracker is anchored on the
        orchestrator cwd and records relative paths in real flows (see the
        module docstring on worktree-relative paths).
        """
        cwd = os.getcwd()
        try:
            os.chdir(self._fake_root)
            self.assertTrue(hook._should_skip(".claude/memory/session_handoff.md"))
        finally:
            os.chdir(cwd)

    def test_absolute_handoff_path_is_skipped(self):
        path = str(self._fake_root / ".claude" / "memory" / "session_handoff.md")
        self.assertTrue(hook._should_skip(path))

    def test_skip_is_scoped_to_the_claude_memory_directory(self):
        """The pattern must stay DIRECTORY-scoped, not a bare filename (#1043).

        Narrowing the entry to ``"session_handoff.md"`` left the whole suite
        green, so nothing pinned the scoping. A substring denylist matches
        anywhere in the path, so a bare filename would silently stop tracking
        any committed file that happens to share the name — e.g. a real
        ``docs/session_handoff.md``. Only the gitignored machine-local file at
        ``.claude/memory/`` is exempt; a same-named file elsewhere in the repo
        is ordinary tracked content.
        """
        elsewhere = str(self._fake_root / "docs" / "session_handoff.md")
        self.assertFalse(hook._should_skip(elsewhere))

    def test_skip_does_not_extend_to_sibling_memory_notes_by_prefix(self):
        """A path merely *starting* with the handoff name is not exempt (#1043).

        Guards the other narrowing direction — the pattern must match the whole
        handoff path, so a distinct committed note is unaffected.
        """
        sibling = str(self._fake_root / ".claude" / "memory" / "session_handoff_notes.md")
        self.assertFalse(hook._should_skip(sibling))

    def test_check_writes_no_entry_for_handoff(self):
        """End-to-end: a Write to the handoff produces no checksums entry.

        ``_should_skip`` is the mechanism, but the defect users saw was a
        checksums *write*. Drive the dispatcher entry point against a real file
        and assert the tracker reports "not applicable" and leaves the
        checksums file untouched.
        """
        handoff = self._fake_root / ".claude" / "memory" / "session_handoff.md"
        handoff.parent.mkdir(parents=True, exist_ok=True)
        handoff.write_text("# handoff\n", encoding="utf-8")

        checksums = self._fake_root / "ontology" / "checksums.json"
        checksums.parent.mkdir(parents=True, exist_ok=True)
        checksums.write_text('{"version": 1, "files": {}}\n', encoding="utf-8")
        orig_checksums_file = hook.CHECKSUMS_FILE
        hook.CHECKSUMS_FILE = checksums
        try:
            before = checksums.read_bytes()
            result = hook.check({"tool_name": "Write", "tool_input": {"file_path": str(handoff)}})
            self.assertIsNone(result)
            self.assertEqual(checksums.read_bytes(), before)
        finally:
            hook.CHECKSUMS_FILE = orig_checksums_file

    def test_other_memory_notes_are_still_tracked(self):
        """The skip is scoped to the handoff — real project memory still tracks.

        ``.claude/memory/`` is committed, semantic, hand-curated content; only
        the single gitignored handoff file is exempt. A broader
        ``.claude/memory/`` skip would silently drop the whole memory store
        from drift detection.
        """
        path = str(self._fake_root / ".claude" / "memory" / "section_ci_tooling.md")
        self.assertFalse(hook._should_skip(path))

    def test_skip_does_not_widen_to_bare_memory_prefix(self):
        """#1045: pin the last unkilled widening direction on the handoff pattern.

        Mutation testing at ``ac8bcfa`` (PR #1040 merge-gate re-confirm) found
        four of five string-truncation directions on the
        ``".claude/memory/session_handoff.md"`` entry already killed by the
        tests above, but widening it on the LEFT — dropping the ``.claude/``
        anchor down to ``"memory/session_handoff.md"`` — survived all 31
        tests. A path like ``docs/memory/session_handoff.md`` has no
        ``.claude/`` component, so it must NOT be skipped; if the pattern is
        ever mutated to drop that anchor, this is the only assertion that
        dies.
        """
        anchored = str(self._fake_root / "docs" / "memory" / "session_handoff.md")
        self.assertFalse(hook._should_skip(anchored))


class ChecksumsSerializationTests(_FakeRepoRootMixin, unittest.TestCase):
    """#1038: the tracker must not re-escape literal UTF-8 on every write.

    ``checksums.json``'s top-level ``description`` contains literal ``—``/``×``.
    Writing with the ``ensure_ascii=True`` default re-escaped them, so the file
    flip-flopped between escaped and literal depending on which writer touched
    it last — pure recurring diff noise on a committed file.
    """

    def test_non_ascii_description_survives_a_write_unescaped(self):
        checksums = self._fake_root / "ontology" / "checksums.json"
        checksums.parent.mkdir(parents=True, exist_ok=True)
        description = "SCOPE (#857, #820/C×T2): semantic overlay — not structural"
        checksums.write_text(
            json.dumps({"version": 1, "description": description, "files": {}}, indent=2) + "\n",
            encoding="utf-8",
        )

        tracked = self._fake_root / "ontology" / "domain.yaml"
        tracked.write_text("entities: []\n", encoding="utf-8")

        orig_checksums_file = hook.CHECKSUMS_FILE
        hook.CHECKSUMS_FILE = checksums
        try:
            hook.check({"tool_name": "Write", "tool_input": {"file_path": str(tracked)}})
        finally:
            hook.CHECKSUMS_FILE = orig_checksums_file

        raw = checksums.read_text(encoding="utf-8")
        self.assertIn(description, raw)
        self.assertNotIn("\\u", raw)
        self.assertEqual(json.loads(raw)["description"], description)

    def test_write_is_byte_stable_across_repeated_tracking(self):
        """Tracking the same unchanged file twice must not change the bytes.

        This is the property the defect violated: a no-op touch produced a diff.
        """
        checksums = self._fake_root / "ontology" / "checksums.json"
        checksums.parent.mkdir(parents=True, exist_ok=True)
        checksums.write_text(
            json.dumps(
                {"version": 1, "description": "overlay — × scope", "files": {}},
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        tracked = self._fake_root / "ontology" / "conventions.md"
        tracked.write_text("# conventions\n", encoding="utf-8")

        orig_checksums_file = hook.CHECKSUMS_FILE
        hook.CHECKSUMS_FILE = checksums
        try:
            payload = {"tool_name": "Edit", "tool_input": {"file_path": str(tracked)}}
            hook.check(payload)
            first = checksums.read_bytes()
            hook.check(payload)
            second = checksums.read_bytes()
        finally:
            hook.CHECKSUMS_FILE = orig_checksums_file

        # ``tracked_at`` is a timestamp and legitimately moves; everything else
        # (notably the description encoding and the hashes) must be identical.
        first_data = json.loads(first)
        second_data = json.loads(second)
        for data in (first_data, second_data):
            for entry in data["files"].values():
                entry.pop("tracked_at", None)
        self.assertEqual(first_data, second_data)
        self.assertNotIn("\\u", second.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
