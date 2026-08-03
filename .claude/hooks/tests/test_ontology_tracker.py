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
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import _test_helpers  # noqa: E402,F401
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


class GitCheckIgnoreGeneralizationTests(_FakeRepoRootMixin, unittest.TestCase):
    """#1039: generalize SKIP_PATTERNS via an owning-repo ``git check-ignore``.

    The naive fix (#1038's rejected proposal) runs ``check-ignore`` from
    ``REPO_ROOT``: since the parent repo ``.gitignore``s every child repo
    wholesale, that would report EVERY child-repo file as ignored — a 52%
    regression that blinds the tracker while looking green. The correct fix
    resolves each file's nearest ``.git`` ancestor and asks THAT repo. These
    tests use real ``git init`` repos (not mocks) so the regression guard is
    load-bearing against the actual git plumbing command, not an assumption
    about its behavior.
    """

    def setUp(self):
        super().setUp()
        hook._GIT_CHECK_IGNORE_CACHE.clear()
        hook._DIR_CHECK_IGNORE_CACHE.clear()
        # `env=hook._hermetic_git_env()` is load-bearing (main#719): the
        # pre-push pytest hook is itself invoked by `git push`, which exports
        # GIT_DIR/GIT_WORK_TREE for the real repo into every subprocess this
        # test spawns. Without stripping it, `git init` here silently
        # inits/no-ops against the REAL repo instead of the fake root, so the
        # fake root never gets a `.git` and every check-ignore call below
        # then legitimately (and misleadingly) reports "not a git repo".
        subprocess.run(
            ["git", "init", "-q", str(self._fake_root)],
            check=True,
            capture_output=True,
            env=hook._hermetic_git_env(),
        )

    def tearDown(self):
        hook._GIT_CHECK_IGNORE_CACHE.clear()
        hook._DIR_CHECK_IGNORE_CACHE.clear()
        super().tearDown()

    def test_child_repo_file_ignored_by_parent_is_still_tracked(self):
        """The 52% regression guard: a child repo's own tracked file.

        The parent ``.gitignore`` ignores the whole ``child-repo/`` directory
        (mirroring noorinalabs-main's real wholesale child-repo gitignore),
        but the file lives inside its OWN nested git repo, which does not
        ignore it. Resolving check-ignore against the owning repo (not
        REPO_ROOT) must still track this file.
        """
        (self._fake_root / ".gitignore").write_text("child-repo/\n", encoding="utf-8")

        child_repo = self._fake_root / "child-repo"
        child_repo.mkdir()
        subprocess.run(
            ["git", "init", "-q", str(child_repo)],
            check=True,
            capture_output=True,
            env=hook._hermetic_git_env(),
        )

        f = child_repo / "ontology" / "services.yaml"
        f.parent.mkdir(parents=True)
        f.write_text("services: []\n", encoding="utf-8")

        self.assertFalse(hook._should_skip(str(f)))

    def test_parent_gitignored_file_is_skipped(self):
        """A file genuinely gitignored by its own (owning) repo IS skipped."""
        (self._fake_root / ".gitignore").write_text("scratch/\n", encoding="utf-8")

        f = self._fake_root / "scratch" / "notes.md"
        f.parent.mkdir(parents=True)
        f.write_text("notes\n", encoding="utf-8")

        self.assertTrue(hook._should_skip(str(f)))

    def test_non_ignored_file_in_owning_repo_is_tracked(self):
        """A file not covered by any .gitignore rule is tracked as normal."""
        f = self._fake_root / "ontology" / "domain.yaml"
        f.parent.mkdir(parents=True)
        f.write_text("entities: []\n", encoding="utf-8")

        self.assertFalse(hook._should_skip(str(f)))

    def test_find_git_root_returns_none_without_git_ancestor(self):
        """No ``.git`` ancestor at all -> cannot determine -> caller fails open."""
        base = Path.home() / ".cache" / "noorinalabs-test-ontology-tracker"
        base.mkdir(parents=True, exist_ok=True)
        lonely = Path(tempfile.mkdtemp(prefix="no_git_", dir=str(base)))
        try:
            f = lonely / "file.md"
            f.write_text("x\n", encoding="utf-8")
            self.assertIsNone(hook._find_git_root(f))
            self.assertFalse(hook._is_git_ignored(f))
        finally:
            shutil.rmtree(lonely, ignore_errors=True)

    def test_check_ignore_subprocess_failure_fails_open(self):
        """A ``git`` subprocess error must not skip the file (fail open)."""
        f = self._fake_root / "ontology" / "services.yaml"
        f.parent.mkdir(parents=True)
        f.write_text("services: []\n", encoding="utf-8")

        orig_run = subprocess.run

        def _boom(*args, **kwargs):
            raise OSError("git not found")

        subprocess.run = _boom
        try:
            self.assertFalse(hook._is_git_ignored(f.resolve()))
        finally:
            subprocess.run = orig_run

    def test_check_ignore_timeout_fails_open(self):
        """A ``git`` subprocess timeout must not skip the file (fail open)."""
        f = self._fake_root / "ontology" / "services.yaml"
        f.parent.mkdir(parents=True)
        f.write_text("services: []\n", encoding="utf-8")

        orig_run = subprocess.run

        def _timeout(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd="git", timeout=5)

        subprocess.run = _timeout
        try:
            self.assertFalse(hook._is_git_ignored(f.resolve()))
        finally:
            subprocess.run = orig_run

    def test_result_is_cached_per_process(self):
        """A second call for the same path must not re-invoke ``git``."""
        (self._fake_root / ".gitignore").write_text("scratch/\n", encoding="utf-8")
        f = self._fake_root / "scratch" / "notes.md"
        f.parent.mkdir(parents=True)
        f.write_text("notes\n", encoding="utf-8")
        resolved = f.resolve()

        call_count = 0
        orig_run = subprocess.run

        def _counting_run(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return orig_run(*args, **kwargs)

        subprocess.run = _counting_run
        try:
            first = hook._is_git_ignored(resolved)
            second = hook._is_git_ignored(resolved)
        finally:
            subprocess.run = orig_run

        self.assertTrue(first)
        self.assertTrue(second)
        self.assertEqual(call_count, 1)

    def test_end_to_end_check_writes_no_entry_for_gitignored_file(self):
        """Full ``check()`` dispatcher path: a gitignored file writes nothing."""
        (self._fake_root / ".gitignore").write_text("scratch/\n", encoding="utf-8")
        f = self._fake_root / "scratch" / "notes.md"
        f.parent.mkdir(parents=True)
        f.write_text("notes\n", encoding="utf-8")

        checksums = self._fake_root / "ontology" / "checksums.json"
        checksums.parent.mkdir(parents=True, exist_ok=True)
        checksums.write_text('{"version": 1, "files": {}}\n', encoding="utf-8")
        orig_checksums_file = hook.CHECKSUMS_FILE
        hook.CHECKSUMS_FILE = checksums
        try:
            before = checksums.read_bytes()
            result = hook.check({"tool_name": "Write", "tool_input": {"file_path": str(f)}})
            self.assertIsNone(result)
            self.assertEqual(checksums.read_bytes(), before)
        finally:
            hook.CHECKSUMS_FILE = orig_checksums_file

    def _counting_run(self):
        """Wrap ``subprocess.run`` with a call counter, returning
        ``(wrapped_fn, get_count)``. Callers swap ``subprocess.run`` in and
        restore it in a ``finally``."""
        call_count = 0
        orig_run = subprocess.run

        def _wrapped(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return orig_run(*args, **kwargs)

        return _wrapped, (lambda: call_count)

    def test_first_file_in_a_directory_resolves_both_in_one_subprocess_call(self):
        """#1122: the directory verdict is resolved for free alongside the
        file's own verdict — no extra subprocess versus the pre-#1122
        single-file check."""
        (self._fake_root / ".gitignore").write_text("scratch/\n", encoding="utf-8")
        scratch = self._fake_root / "scratch"
        scratch.mkdir()
        f = scratch / "a.md"
        f.write_text("a\n", encoding="utf-8")

        wrapped, get_count = self._counting_run()
        orig_run = subprocess.run
        subprocess.run = wrapped
        try:
            ignored = hook._is_git_ignored(f.resolve())
        finally:
            subprocess.run = orig_run

        self.assertTrue(ignored)
        self.assertEqual(get_count(), 1)

    def test_second_file_in_same_ignored_directory_is_a_cache_hit(self):
        """#1122's actual win: a LATER, DIFFERENT file under an
        already-known-ignored directory costs zero subprocess calls."""
        (self._fake_root / ".gitignore").write_text("scratch/\n", encoding="utf-8")
        scratch = self._fake_root / "scratch"
        scratch.mkdir()
        a = scratch / "a.md"
        a.write_text("a\n", encoding="utf-8")
        b = scratch / "b.md"
        b.write_text("b\n", encoding="utf-8")

        self.assertTrue(hook._is_git_ignored(a.resolve()))  # seeds the dir cache

        wrapped, get_count = self._counting_run()
        orig_run = subprocess.run
        subprocess.run = wrapped
        try:
            ignored = hook._is_git_ignored(b.resolve())
        finally:
            subprocess.run = orig_run

        self.assertTrue(ignored)
        self.assertEqual(get_count(), 0)

    def test_second_file_in_a_not_ignored_directory_is_still_checked_individually(self):
        """Mutation guard for #1122's directory cache: a not-ignored
        DIRECTORY verdict must never be used to declare a DIFFERENT file
        not-ignored — a filename pattern can still exclude that one file.
        Without this guard (e.g. a broadened predicate that trusts a False
        directory-cache hit as "file not ignored"), this test fails because
        ``x.secret`` would wrongly come back as tracked.
        """
        (self._fake_root / ".gitignore").write_text("*.secret\n", encoding="utf-8")
        kept = self._fake_root / "kept"
        kept.mkdir()
        plain = kept / "plain.md"
        plain.write_text("plain\n", encoding="utf-8")
        secret = kept / "x.secret"
        secret.write_text("s\n", encoding="utf-8")

        # Directory resolves to NOT ignored (seeds `_DIR_CHECK_IGNORE_CACHE`
        # False for `kept`).
        self.assertFalse(hook._is_git_ignored(plain.resolve()))

        wrapped, get_count = self._counting_run()
        orig_run = subprocess.run
        subprocess.run = wrapped
        try:
            ignored = hook._is_git_ignored(secret.resolve())
        finally:
            subprocess.run = orig_run

        self.assertTrue(ignored)
        self.assertEqual(get_count(), 1)  # still had to ask, just for this one file


class GitCheckIgnoreExcludeThenReincludeTests(_FakeRepoRootMixin, unittest.TestCase):
    """main#1263 review finding: a trailing-slash directory pathspec is
    unsound for the `dir/*` + `!dir/**/keeper` idiom.

    ``git check-ignore`` treats a trailing-slash pathspec (``"data/raw/"``)
    as a literal STRING that a contents-only pattern like ``data/raw/*``
    matches directly — git echoes that exact string back as "ignored". That
    is a DIFFERENT fact from the directory itself being excluded, and it is
    NOT true that every file inside is unconditionally ignored the way a
    genuine directory-exclusion (``build/``) implies. Caching the
    trailing-slash answer as ``dir_ignored=True`` therefore silently
    mis-skips any file a ``!`` rule re-includes — this is the exact
    ``data/raw/*`` + ``!data/**/.gitkeep`` idiom used by
    ``noorinalabs-isnad-ingest-platform/.gitignore`` (four committed
    ``.gitkeep`` files use it).

    Reviewer correction that shaped these fixtures: a COMMITTED keeper is
    masked by git's index (``check-ignore`` never flags a tracked path
    regardless of pattern), so a test using an already-``git add``-ed
    keeper passes for an unrelated reason and proves nothing about the
    pattern-matching bug. The live bug surface is a keeper that is NOT YET
    tracked (a newly created ``.gitkeep``, exactly the moment the tracker
    hook would actually run on it) — that case is kept as its own,
    explicitly-labeled test alongside the (also explicitly-labeled) tracked
    case, per review, so nobody later mistakes the tracked test for
    covering the fix it does not exercise.
    """

    def setUp(self):
        super().setUp()
        hook._GIT_CHECK_IGNORE_CACHE.clear()
        hook._DIR_CHECK_IGNORE_CACHE.clear()
        subprocess.run(
            ["git", "init", "-q", str(self._fake_root)],
            check=True,
            capture_output=True,
            env=hook._hermetic_git_env(),
        )
        (self._fake_root / ".gitignore").write_text(
            "data/raw/*\n!data/**/.gitkeep\n", encoding="utf-8"
        )

    def tearDown(self):
        hook._GIT_CHECK_IGNORE_CACHE.clear()
        hook._DIR_CHECK_IGNORE_CACHE.clear()
        super().tearDown()

    def test_untracked_reincluded_keeper_is_not_skipped(self):
        """THE live-bug case (untracked keeper — see class docstring). Seeds
        the directory cache via the excluded sibling first, matching
        production call order (whichever file ``check()`` sees first in a
        directory), then proves the re-included keeper is still tracked."""
        raw = self._fake_root / "data" / "raw"
        raw.mkdir(parents=True)
        dump = raw / "dump.parquet"
        dump.write_text("binary-stand-in\n", encoding="utf-8")
        keeper = raw / ".gitkeep"
        keeper.write_text("", encoding="utf-8")

        self.assertTrue(hook._is_git_ignored(dump.resolve()))  # genuinely excluded
        self.assertFalse(hook._is_git_ignored(keeper.resolve()))  # re-included by `!`

    def test_tracked_reincluded_keeper_is_not_skipped_for_index_reasons(self):
        """The steady-state case once a keeper is committed. Passes for a
        DIFFERENT reason than the fix above (git's index masks a tracked
        path from check-ignore regardless of pattern matching) and would
        pass even against the buggy trailing-slash code — see class
        docstring. Kept only so the tracked case is covered too, and
        labeled so it is never mistaken for covering the pattern fix."""
        raw = self._fake_root / "data" / "raw"
        raw.mkdir(parents=True)
        dump = raw / "dump.parquet"
        dump.write_text("binary-stand-in\n", encoding="utf-8")
        keeper = raw / ".gitkeep"
        keeper.write_text("", encoding="utf-8")
        subprocess.run(
            ["git", "add", "data/raw/.gitkeep"],
            cwd=str(self._fake_root),
            check=True,
            capture_output=True,
            env=hook._hermetic_git_env(),
        )

        self.assertTrue(hook._is_git_ignored(dump.resolve()))
        self.assertFalse(hook._is_git_ignored(keeper.resolve()))

    def test_nested_directory_swept_up_by_contents_pattern_is_still_ignored(self):
        """A NESTED directory whose own bare name is itself matched by the
        contents-only pattern (``data/raw/sub`` matches ``data/raw/*``) IS
        genuinely excluded — gitignore(5)'s no-re-include-under-an-excluded-
        parent rule then really does apply to everything beneath it, so the
        directory-cache shortcut short-circuiting to True there is correct
        behavior, not a regression of the fix above."""
        sub = self._fake_root / "data" / "raw" / "sub"
        sub.mkdir(parents=True)
        nested_keeper = sub / ".gitkeep"
        nested_keeper.write_text("", encoding="utf-8")

        self.assertTrue(hook._is_git_ignored(nested_keeper.resolve()))
        self.assertTrue(hook._DIR_CHECK_IGNORE_CACHE[(str(self._fake_root), "data/raw/sub")])

    def test_trailing_slash_is_unsound_bare_name_is_not(self):
        """Characterization of GIT's behavior — the PREMISE the fix rests
        on — not a regression guard on our code.

        Read the scope carefully (main#1263 review, Weronika Zielinska).
        An earlier version of this docstring claimed a future
        re-introduction of the trailing slash would "fail immediately"
        here. **That is false**, and was measured false: this test calls
        ``_run_check_ignore`` with literal strings, so it never touches
        ``_is_git_ignored``'s ``dir_spec`` at all and passes unchanged when
        the trailing slash is reinstated. The test that actually catches
        that mutation is ``test_untracked_reincluded_keeper_is_not_skipped``
        in the class above — and only that one.

        What this DOES pin is worth keeping: that real git treats a
        trailing-slash pathspec as a literal string matched by a
        contents-only pattern while the bare name is not. If git ever
        changed that, the fix's rationale would evaporate silently and
        every other test here would still pass. Keeping it labeled
        honestly is the point — a test that overstates what it guards is
        how a suite comes to look stronger than it is (cf. main#1215)."""
        raw = self._fake_root / "data" / "raw"
        raw.mkdir(parents=True)
        (raw / "dump.parquet").write_text("x\n", encoding="utf-8")

        # The fix: the bare directory name is NOT reported as matched by a
        # contents-only pattern.
        matched_bare = hook._run_check_ignore(self._fake_root, ["data/raw"])
        self.assertNotIn("data/raw", matched_bare)

        # The trap this guards against: WITH a trailing slash, git DOES
        # echo the literal string back as matched, proving the slash
        # version is unsound for this idiom (not merely untested).
        matched_slash = hook._run_check_ignore(self._fake_root, ["data/raw/"])
        self.assertIn("data/raw/", matched_slash)


class GitCheckIgnoreNonAsciiTests(_FakeRepoRootMixin, unittest.TestCase):
    """main#1265: matching on git's ECHOED pathspec is encoding-sensitive.

    Under git's default ``core.quotePath=true`` a pathspec containing any
    non-ASCII byte is C-quoted on the way out (``عربي.log`` echoes as
    ``"\\330\\271\\330\\261\\330\\250\\331\\212.log"``), so exact-string
    membership against what we passed in never matches and a genuinely
    ignored file is reported NOT ignored. That is a behavioural regression
    versus the pre-#1122 code, which read only ``check-ignore -q``'s exit
    status and was encoding-independent by construction.

    The failure direction is the safe one (fail-open -> over-track, never
    under-track) and no repo currently holds a non-ASCII path, so it was
    latent. It is pinned here anyway because this org's domain is
    Arabic-language scholarly data and the over-tracked entries land in the
    COMMITTED ``ontology/checksums.json`` — the #1038 phantom-drift-forever
    shape.
    """

    def setUp(self):
        super().setUp()
        hook._GIT_CHECK_IGNORE_CACHE.clear()
        hook._DIR_CHECK_IGNORE_CACHE.clear()
        subprocess.run(
            ["git", "init", "-q", str(self._fake_root)],
            check=True,
            capture_output=True,
            env=hook._hermetic_git_env(),
        )
        (self._fake_root / ".gitignore").write_text("*.log\nبناء/\n", encoding="utf-8")

    def tearDown(self):
        hook._GIT_CHECK_IGNORE_CACHE.clear()
        hook._DIR_CHECK_IGNORE_CACHE.clear()
        super().tearDown()

    def test_non_ascii_ignored_file_is_detected(self):
        """The core case: removing the ``core.quotePath=false`` pin makes
        this return False."""
        target = self._fake_root / "عربي.log"
        target.write_text("x\n", encoding="utf-8")

        self.assertTrue(hook._is_git_ignored(target.resolve()))

    def test_ascii_sibling_still_detected(self):
        """Control: the ASCII path was never affected, so a passing
        non-ASCII test alone would not prove the pin is what fixed it."""
        target = self._fake_root / "plain.log"
        target.write_text("x\n", encoding="utf-8")

        self.assertTrue(hook._is_git_ignored(target.resolve()))

    def test_non_ascii_ignored_directory_is_detected(self):
        """The directory-cache half: a non-ASCII directory excluded by a
        genuine directory pattern must cache True, which it cannot do while
        the echo is quoted."""
        d = self._fake_root / "بناء"
        d.mkdir()
        target = d / "a.md"
        target.write_text("x\n", encoding="utf-8")

        self.assertTrue(hook._is_git_ignored(target.resolve()))

    def test_invalid_utf8_filename_is_detected(self):
        """main#1263 review, Weronika Zielinska: the decode setting was an
        UNTESTED guard — reverting it broke nothing, so it could regress
        silently.

        A POSIX filename is a byte string and need not be valid UTF-8.
        ``os.fsdecode`` maps undecodable bytes to lone surrogates
        (``b"\\xe9.log"`` -> ``"\\udce9.log"``), which is the pathspec
        ``_is_git_ignored`` passes; git echoes the raw bytes back. Only
        ``errors="surrogateescape"`` round-trips those byte-exact.

        This fixture fails against BOTH rejected alternatives, which is what
        makes it a real guard rather than a happy-path test:
        ``errors="replace"`` decodes to U+FFFD (silently not-matched,
        fail-open), and ``text=True`` decodes strict (raises, or likewise
        fails to match). Ground truth is ``check-ignore -q``'s exit code —
        the encoding-independent pre-#1122 method — which reports ignored.
        """
        raw_name = os.fsdecode(b"\xe9.log")
        target = self._fake_root / raw_name
        target.write_bytes(b"x\n")

        ground_truth = subprocess.run(
            ["git", "check-ignore", "-q", "--", raw_name],
            cwd=str(self._fake_root),
            capture_output=True,
            env=hook._hermetic_git_env(),
        ).returncode
        self.assertEqual(ground_truth, 0, "fixture is wrong: git does not ignore this")

        self.assertTrue(hook._is_git_ignored(target.resolve()))

    def test_echo_round_trips_the_caller_string(self):
        """Direct guard on the mechanism, independent of ``_is_git_ignored``:
        what git echoes back must be exactly what we passed in."""
        (self._fake_root / "عربي.log").write_text("x\n", encoding="utf-8")

        matched = hook._run_check_ignore(self._fake_root, ["عربي.log"])
        self.assertEqual(matched, {"عربي.log"})


class RunCheckIgnoreFailOpenTests(_FakeRepoRootMixin, unittest.TestCase):
    """main#1263 review: the ``returncode not in (0, 1)`` fail-open branch
    in ``_run_check_ignore`` had no test pinning it — a mutation deleting it
    survived the suite. Exit 128 is git's fatal-error code (e.g. an
    out-of-repo or otherwise invalid pathspec); folding it into "nothing
    ignored" must fail open (track the file), matching the single-path
    behavior this module has always had for a subprocess failure.
    """

    def setUp(self):
        super().setUp()
        subprocess.run(
            ["git", "init", "-q", str(self._fake_root)],
            check=True,
            capture_output=True,
            env=hook._hermetic_git_env(),
        )

    def test_mocked_fatal_returncode_fails_open(self):
        """The ``stdout`` here is deliberately NON-empty and formatted
        exactly like a real ignored-pathspec echo — if the ``returncode not
        in (0, 1)`` guard were deleted, the code would fall straight
        through to parsing ``stdout`` and (wrongly) report ``some/path`` as
        matched anyway, because an empty-stdout fatal error is
        indistinguishable from "nothing ignored" without this guard. An
        empty-``stdout`` version of this test would pass with or without
        the guard and prove nothing (this is exactly the gap the reviewer
        found survived undetected)."""
        real_run = subprocess.run

        def _fake_fatal(*args, **kwargs):
            return subprocess.CompletedProcess(
                args=args,
                returncode=128,
                stdout="some/path\n",
                stderr="fatal: not a git repository\n",
            )

        subprocess.run = _fake_fatal
        try:
            matched = hook._run_check_ignore(self._fake_root, ["some/path"])
        finally:
            subprocess.run = real_run

        self.assertEqual(matched, set())

    def test_real_fatal_returncode_also_fails_open(self):
        """Not mocked: a real ``git check-ignore`` with an out-of-repo
        pathspec genuinely exits 128 (real git prints ``fatal: ... is
        outside repository``) and must fail open end to end.

        **This test is vacuous with respect to the guard it appears to
        cover** (main#1263 review, Weronika Zielinska — measured, not
        assumed). A real fatal exit also produces EMPTY stdout, so the
        function returns an empty set with or without the
        ``returncode not in (0, 1)`` branch: deleting that branch leaves
        this test passing. ``test_mocked_fatal_returncode_fails_open`` is
        the only test that catches it, which is exactly why that one feeds
        deliberately NON-empty stdout.

        Kept because it pins the PREMISE the mocked test is built on — that
        128 is really what git returns here, rather than a return code we
        invented for a fixture. **That premise is now asserted directly**
        (main#1263 review, Weronika Zielinska, second pass): the earlier
        version claimed to pin it while asserting only ``matched == set()``,
        an observable identical for simulated exits 0, 1 and 128 with empty
        stdout — so a change to exit 1 would have evaporated the premise
        silently. Claiming to guard a premise while measuring something else
        is the same #1215 mode this docstring invokes, one level in.

        Not a flake risk despite naming a system path: any absolute
        out-of-repo pathspec exits 128 whether or not the file exists
        (verified against a nonexistent path)."""
        outside = "/etc/hostname"  # any absolute out-of-repo path works

        # The premise, measured rather than asserted about: real git treats
        # an out-of-repo pathspec as a FATAL error, not as "not ignored".
        probe = subprocess.run(
            ["git", "-c", "core.quotePath=false", "check-ignore", "--", outside],
            cwd=str(self._fake_root),
            capture_output=True,
            env=hook._hermetic_git_env(),
            encoding="utf-8",
            errors="surrogateescape",
        )
        self.assertEqual(probe.returncode, 128, "premise gone: git no longer exits 128 here")

        matched = hook._run_check_ignore(self._fake_root, [outside])
        self.assertEqual(matched, set())


class SkipNoopWriteTests(_FakeRepoRootMixin, unittest.TestCase):
    """#1122: skip the ``checksums.json`` write when the SHA is unchanged.

    Exercises the skip PREDICATE directly (by counting calls to
    ``checksums_io.write_checksums``), not just its byte-stability side
    effect (``ChecksumsSerializationTests`` already covers that) — these
    fail if the predicate is dropped, inverted, or broadened to compare the
    wrong field.
    """

    def setUp(self):
        super().setUp()
        checksums = self._fake_root / "ontology" / "checksums.json"
        checksums.parent.mkdir(parents=True, exist_ok=True)
        checksums.write_text('{"version": 1, "files": {}}\n', encoding="utf-8")
        self._checksums = checksums
        self._orig_checksums_file = hook.CHECKSUMS_FILE
        hook.CHECKSUMS_FILE = checksums

    def tearDown(self):
        hook.CHECKSUMS_FILE = self._orig_checksums_file
        super().tearDown()

    def test_first_track_of_a_new_path_always_writes(self):
        """A never-before-seen path has no `last_tracked` to compare against
        (`existing.get("last_tracked")` is `None`, never equal to a real
        64-hex-char digest) — must never be mistaken for a no-op."""
        f = self._fake_root / "ontology" / "domain.yaml"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("entities: []\n", encoding="utf-8")

        with mock.patch.object(hook.checksums_io, "write_checksums") as m:
            result = hook.check({"tool_name": "Write", "tool_input": {"file_path": str(f)}})

        self.assertEqual(result, {"action": "tracked", "path": "ontology/domain.yaml"})
        m.assert_called_once()

    def test_unchanged_content_reedit_skips_the_write(self):
        """The exact no-op case #1122 targets: an edit that re-saves
        byte-identical content must skip the 103 KB write entirely."""
        f = self._fake_root / "ontology" / "domain.yaml"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("entities: []\n", encoding="utf-8")
        payload = {"tool_name": "Write", "tool_input": {"file_path": str(f)}}
        hook.check(payload)  # real track — establishes last_tracked

        with mock.patch.object(hook.checksums_io, "write_checksums") as m:
            result = hook.check(payload)  # identical content re-saved

        self.assertEqual(result, {"action": "skip_noop", "path": "ontology/domain.yaml"})
        m.assert_not_called()

    def test_changed_content_after_a_noop_still_writes(self):
        """Mutation guard: the predicate must not be too broad. A genuine
        content change immediately after a no-op must still write — proves
        the skip isn't sticky/state-leaking and isn't comparing the wrong
        field (e.g. always True, or comparing `tracked_at`)."""
        f = self._fake_root / "ontology" / "domain.yaml"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("entities: []\n", encoding="utf-8")
        payload = {"tool_name": "Write", "tool_input": {"file_path": str(f)}}
        hook.check(payload)
        hook.check(payload)  # no-op — establishes the skip path was taken

        f.write_text("entities: [foo]\n", encoding="utf-8")
        with mock.patch.object(hook.checksums_io, "write_checksums") as m:
            result = hook.check(payload)

        self.assertEqual(result["action"], "tracked")
        m.assert_called_once()

    def test_skip_leaves_the_on_disk_entry_byte_identical(self):
        """A skipped no-op write must leave the committed entry untouched —
        not drop it, not corrupt it, not merely "similar"."""
        f = self._fake_root / "ontology" / "domain.yaml"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("entities: []\n", encoding="utf-8")
        payload = {"tool_name": "Write", "tool_input": {"file_path": str(f)}}
        hook.check(payload)
        before = self._checksums.read_bytes()

        hook.check(payload)  # no-op re-save, write skipped
        after = self._checksums.read_bytes()

        self.assertEqual(before, after)


class LinkedWorktreeTests(_FakeRepoRootMixin, unittest.TestCase):
    """Structural worktree detection — the ``da-wt-490/*`` orphan regression.

    ``_is_worktree_path`` matches on directory NAME, so a worktree parked
    outside ``.worktrees/`` slips through: wave-28 left four entries keyed to
    ``da-wt-490/…`` (a worktree at the repo root) that could never resolve
    once the tree was removed. ``_is_linked_worktree`` reads git's own
    ``.git`` pointer file instead, discriminating on the admin-dir invariant
    (see ``checksums_io.is_linked_worktree_root``).

    The positive worktree cases and the ``--separate-git-dir`` case drive real
    git plumbing. The two `.git/modules/` submodule cases FABRICATE the
    pointer — git will not create a submodule offline — so they prove the
    predicate's shape, not git's. That distinction matters: an earlier
    revision's single fabricated submodule fixture used a path with no
    ``worktrees`` component, which made it inert against the substring
    predicate it was meant to guard (the loosened mutant
    ``"worktrees" in gitdir`` passed the entire suite).
    ``test_submodule_whose_path_contains_worktrees_is_not_skipped`` is the
    fixture that actually kills that mutant.
    """

    def _git(self, *args: str, cwd: Path) -> None:
        subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            check=True,
            capture_output=True,
            env=hook._hermetic_git_env(),
        )

    def setUp(self):
        super().setUp()
        # `env=hook._hermetic_git_env()` is load-bearing here for the same
        # reason as GitCheckIgnoreGeneralizationTests (main#719).
        subprocess.run(
            ["git", "init", "-q", str(self._fake_root)],
            check=True,
            capture_output=True,
            env=hook._hermetic_git_env(),
        )
        seed = self._fake_root / "seed.txt"
        seed.write_text("seed\n", encoding="utf-8")
        self._git("add", "seed.txt", cwd=self._fake_root)
        self._git(
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-qm",
            "seed",
            cwd=self._fake_root,
        )

    def test_file_in_worktree_outside_dot_worktrees_is_skipped(self):
        """The exact ``da-wt-490/`` shape: a worktree at the repo root."""
        wt = self._fake_root / "da-wt-490"
        self._git("worktree", "add", "-q", "-b", "wt-branch", str(wt), cwd=self._fake_root)

        f = wt / "src" / "cli.py"
        f.parent.mkdir(parents=True)
        f.write_text("x = 1\n", encoding="utf-8")

        # The name-based filter does NOT catch it — that is the whole defect.
        self.assertFalse(hook._is_worktree_path(str(f)))
        self.assertTrue(hook._is_linked_worktree(f.resolve()))
        self.assertTrue(hook._should_skip(str(f)))

    def test_file_in_main_checkout_is_not_a_linked_worktree(self):
        """A real checkout's ``.git`` is a directory — must stay tracked."""
        f = self._fake_root / "ontology" / "domain.yaml"
        f.parent.mkdir(parents=True)
        f.write_text("entities: []\n", encoding="utf-8")

        self.assertFalse(hook._is_linked_worktree(f.resolve()))
        self.assertFalse(hook._should_skip(str(f)))

    def test_submodule_pointer_is_not_treated_as_a_worktree(self):
        """A submodule's ``.git`` is also a pointer file, but to ``.git/modules/``.

        Submodules hold real committed source; skipping them would silently
        blind the tracker to a whole repo.
        """
        sub = self._fake_root / "vendor" / "libfoo"
        sub.mkdir(parents=True)
        modules_dir = self._fake_root / ".git" / "modules" / "libfoo"
        modules_dir.mkdir(parents=True)
        (sub / ".git").write_text(f"gitdir: {modules_dir}\n", encoding="utf-8")

        f = sub / "src.py"
        f.write_text("x = 1\n", encoding="utf-8")

        self.assertFalse(hook._is_linked_worktree(f.resolve()))

    def test_submodule_whose_path_contains_worktrees_is_not_skipped(self):
        """Regression: the ``/worktrees/`` substring predicate got this WRONG.

        A submodule may legitimately live at a path containing a ``worktrees``
        component, e.g. ``gitdir: …/.git/modules/worktrees/libbar``. The
        original substring test skipped it, silently blinding the tracker to a
        whole committed source tree — the failure the fail-open asymmetry
        exists to prevent. The admin-dir invariant
        (``gitdir`` + ``commondir`` files) is what discriminates correctly.

        This fixture is the one that kills the loosened-predicate mutant: with
        the old `"worktrees" in gitdir` test the whole suite still passed.
        """
        sub = self._fake_root / "vendor" / "libbar"
        sub.mkdir(parents=True)
        modules_dir = self._fake_root / ".git" / "modules" / "worktrees" / "libbar"
        modules_dir.mkdir(parents=True)
        (sub / ".git").write_text(f"gitdir: {modules_dir}\n", encoding="utf-8")

        f = sub / "src.py"
        f.write_text("x = 1\n", encoding="utf-8")

        self.assertFalse(hook._is_linked_worktree(f.resolve()))
        self.assertFalse(hook._should_skip(str(f)))

    def test_separate_git_dir_under_a_worktrees_directory_is_not_skipped(self):
        """Second substring false-positive: ``clone --separate-git-dir``.

        Its ``.git`` is a pointer file too, and parking the git dir under any
        directory named ``worktrees`` used to trip the substring test. Driven
        through real ``git clone`` so the pointer is git's own, not fabricated.
        """
        sep_git = self._fake_root / "worktrees" / "sep.git"
        sep_git.parent.mkdir(parents=True, exist_ok=True)
        sep_wt = self._fake_root / "sepwt"
        subprocess.run(
            [
                "git",
                "clone",
                "-q",
                "--separate-git-dir",
                str(sep_git),
                str(self._fake_root),
                str(sep_wt),
            ],
            check=True,
            capture_output=True,
            env=hook._hermetic_git_env(),
        )

        f = sep_wt / "seed.txt"
        self.assertTrue(f.is_file())
        self.assertFalse(hook._is_linked_worktree(f.resolve()))

    def test_worktree_of_a_bare_repo_is_still_detected(self):
        """The admin-dir invariant must not lose coverage a path check had."""
        bare = self._fake_root / "bare.git"
        subprocess.run(
            ["git", "clone", "-q", "--bare", str(self._fake_root), str(bare)],
            check=True,
            capture_output=True,
            env=hook._hermetic_git_env(),
        )
        wt = self._fake_root / "bare-wt"
        self._git("worktree", "add", "-q", "-b", "bare-b", str(wt), cwd=bare)

        f = wt / "seed.txt"
        self.assertTrue(f.is_file())
        self.assertTrue(hook._is_linked_worktree(f.resolve()))

    def test_unrecognized_git_pointer_fails_open(self):
        """A ``.git`` file whose content is not a ``gitdir:`` pointer -> track."""
        odd = self._fake_root / "odd"
        odd.mkdir()
        (odd / ".git").write_text("this is not a gitdir pointer\n", encoding="utf-8")

        f = odd / "file.md"
        f.write_text("x\n", encoding="utf-8")

        self.assertFalse(hook._is_linked_worktree(f.resolve()))

    def test_unreadable_git_pointer_fails_open(self):
        """A ``.git`` file that actually RAISES on read -> track (fail open).

        The previously-named test for this wrote a *readable* file with
        unrecognized content, so it exercised the `startswith` branch and left
        the ``except OSError`` path with zero coverage — a fail-closed mutation
        there survived the whole suite. This one makes the read genuinely
        raise.
        """
        odd = self._fake_root / "unreadable"
        odd.mkdir()
        dot_git = odd / ".git"
        dot_git.write_text("gitdir: /somewhere\n", encoding="utf-8")
        f = odd / "file.md"
        f.write_text("x\n", encoding="utf-8")

        real_read_text = Path.read_text

        def _raising(self, *args, **kwargs):
            if self == dot_git:
                raise OSError("simulated unreadable .git")
            return real_read_text(self, *args, **kwargs)

        with mock.patch.object(Path, "read_text", _raising):
            self.assertFalse(hook._is_linked_worktree(f.resolve()))

    def test_no_git_ancestor_fails_open(self):
        base = Path.home() / ".cache" / "noorinalabs-test-ontology-tracker"
        base.mkdir(parents=True, exist_ok=True)
        lonely = Path(tempfile.mkdtemp(prefix="no_git_wt_", dir=str(base)))
        try:
            f = lonely / "file.md"
            f.write_text("x\n", encoding="utf-8")
            self.assertFalse(hook._is_linked_worktree(f.resolve()))
        finally:
            shutil.rmtree(lonely, ignore_errors=True)

    def test_check_does_not_write_an_entry_for_a_worktree_file(self):
        """End-to-end: the hook records nothing for a worktree-resident edit."""
        wt = self._fake_root / "da-wt-490"
        self._git("worktree", "add", "-q", "-b", "wt-branch2", str(wt), cwd=self._fake_root)

        f = wt / "src" / "graph" / "load_edges.py"
        f.parent.mkdir(parents=True)
        f.write_text("x = 1\n", encoding="utf-8")

        checksums = self._fake_root / "ontology" / "checksums.json"
        checksums.parent.mkdir(parents=True, exist_ok=True)
        checksums.write_text('{"version": 1, "files": {}}\n', encoding="utf-8")
        orig = hook.CHECKSUMS_FILE
        hook.CHECKSUMS_FILE = checksums
        try:
            before = checksums.read_bytes()
            self.assertIsNone(
                hook.check({"tool_name": "Write", "tool_input": {"file_path": str(f)}})
            )
            self.assertEqual(checksums.read_bytes(), before)
        finally:
            hook.CHECKSUMS_FILE = orig


if __name__ == "__main__":
    unittest.main()
