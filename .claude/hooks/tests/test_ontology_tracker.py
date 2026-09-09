#!/usr/bin/env python3
"""Tests for ontology_tracker hook path filtering.

Covers the W8 hook-authorship-spec requirement: NEGATIVE MATCH coverage for
the three noise patterns in issue #143 (/tmp, .claude/worktrees, out-of-repo)
plus a positive case (real source file inside the repo).

Run: python3 -m pytest .claude/hooks/tests/test_ontology_tracker.py -v
Or:  python3 .claude/hooks/tests/test_ontology_tracker.py
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import _test_helpers  # noqa: E402,F401
import ontology_tracker as hook  # noqa: E402
from ontology_tracker import checksums_io  # noqa: E402


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
            self.assertEqual(checksums.read_bytes(), before)
            # UPDATED for #1219: the load-bearing assertion is the untouched
            # ledger above. The return was `None` before; it now NAMES the
            # skip, because `None` is also what the hook returns for a tool it
            # was never registered for, and `post_dispatcher` only records a
            # trace for a dict. Asserting `None` here pinned that collision as
            # intended behaviour.
            self.assertEqual(result["action"], "skipped")
            self.assertEqual(result["reason"], "skip_pattern")
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


class WriterReaderHashAgreementTests(_FakeRepoRootMixin, unittest.TestCase):
    """#1505: the tracker WRITES a hash the reader then CHECKS. One function.

    Before #1505 nothing read `last_tracked` back against the file, so a
    second hashing implementation would have been silently harmless. Now the
    reader compares the two, and any divergence between writer and reader —
    a different chunk size is fine, a different encoding or normalization is
    not — would report every entry in the corpus as drifted forever. The
    tracker therefore calls `checksums_io.compute_sha256` rather than owning
    a copy, and this is the end-to-end pin on that.
    """

    def _track(self, rel: str, contents: str) -> tuple[Path, Path]:
        target = self._fake_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contents, encoding="utf-8")
        checksums = self._fake_root / "ontology" / "checksums.json"
        checksums.parent.mkdir(parents=True, exist_ok=True)
        checksums.write_text('{"version": 1, "files": {}}\n', encoding="utf-8")
        orig = hook.CHECKSUMS_FILE
        hook.CHECKSUMS_FILE = checksums
        try:
            hook.check({"tool_name": "Write", "tool_input": {"file_path": str(target)}})
        finally:
            hook.CHECKSUMS_FILE = orig
        return target, checksums

    def test_freshly_tracked_then_resolved_file_reads_back_as_clean(self) -> None:
        """Write -> track -> mark-resolved -> the reader agrees it is clean.

        If the two sides hashed differently this would come back DRIFTED,
        which is what makes it a real check rather than a tautology.
        """
        _, checksums = self._track("ontology/domain.yaml", "entities:\n  - narrator\n")

        status = checksums_io.read_status(checksums, self._fake_root)
        self.assertEqual(status.dirty, ("ontology/domain.yaml",))  # never resolved yet
        self.assertEqual(status.drifted, ())

        data = checksums_io.read_checksums(checksums)
        checksums_io.mark_resolved(data, ["ontology/domain.yaml"], "2026-09-08T00:00:00Z")
        checksums_io.write_checksums(checksums, data)

        resolved = checksums_io.read_status(checksums, self._fake_root)
        self.assertTrue(resolved.clean)
        self.assertTrue(resolved.verified)

    def test_a_change_the_tracker_never_saw_reads_back_as_drifted(self) -> None:
        """The #1505 route, end to end: the file moves without the hook firing.

        This is what a pull, a merge, another session's commit, or an edit
        made in a worktree looks like from here — the tracker is never
        invoked, so `last_tracked` cannot move, and the entry stays
        self-consistent while the file walks away from it.
        """
        target, checksums = self._track("ontology/domain.yaml", "entities:\n  - narrator\n")
        data = checksums_io.read_checksums(checksums)
        checksums_io.mark_resolved(data, ["ontology/domain.yaml"], "2026-09-08T00:00:00Z")
        checksums_io.write_checksums(checksums, data)
        self.assertTrue(checksums_io.read_status(checksums, self._fake_root).clean)

        target.write_text("entities:\n  - narrator\n  - transmitter\n", encoding="utf-8")

        status = checksums_io.read_status(checksums, self._fake_root)
        self.assertFalse(status.clean)
        self.assertEqual(status.dirty, ())
        self.assertEqual([rel for rel, _ in status.drifted], ["ontology/domain.yaml"])


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
            self.assertEqual(checksums.read_bytes(), before)
            # UPDATED for #1219, same reason as
            # `test_check_writes_no_entry_for_handoff`: "writes nothing" is the
            # claim this test is named for and it still holds; "returns
            # nothing" was a separate, weaker claim that made a gitignored
            # edit indistinguishable from a hook that did not run.
            self.assertEqual(result["action"], "skipped")
            self.assertEqual(result["reason"], "gitignored")
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
        """End-to-end: the hook writes NO LEDGER ENTRY for a worktree-resident edit.

        UPDATED for #1219, and the reason is the wave-31 bar's clause 2a. This
        test previously also asserted ``assertIsNone(hook.check(...))``. That
        half was pinning the fail-open value: ``None`` is what
        ``post_dispatcher`` reads as "this hook did not apply", so the
        assertion specified "a worktree edit leaves no evidence anywhere" as
        intended behaviour, which is the defect #1219 describes.

        The half that is still correct — and is what this test exists for —
        is that the LEDGER is untouched, byte for byte. Skipping the worktree
        KEY stays (#523/#525). What changes is only the return channel, now
        asserted positively: an explicit ``skipped_worktree`` action carrying
        the canonical key the edit will land under. See
        ``CheckReturnChannelTests`` for the full vocabulary.
        """
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
            result = hook.check({"tool_name": "Write", "tool_input": {"file_path": str(f)}})
            self.assertEqual(checksums.read_bytes(), before)
            self.assertEqual(result["action"], "skipped_worktree")
            self.assertEqual(result["reason"], "linked_worktree")
            self.assertEqual(result["canonical_path"], "src/graph/load_edges.py")
        finally:
            hook.CHECKSUMS_FILE = orig


##############################################################################
# #1219 — the worktree catch-up path.
#
# Every test below fails against the pre-#1219 implementation. The failures
# split into two shapes and the PR body states which is which, because they
# are not equally strong evidence:
#
#   VALUE-SHAPED  — the symbol existed before and returned the wrong value.
#                   `check()` returning None on the skip path; the dispatcher
#                   emitting no trace record for it. These are the ones that
#                   prove a behaviour changed.
#   SIGNATURE-SHAPED — the symbol did not exist before (`catch-up`,
#                   `plan_catch_up`, `_skip_reason`). A test of a new entry
#                   point can only fail pre-fix by AttributeError/exit 2. It
#                   proves the mechanism does what it claims, not that
#                   something used to be wrong; the ledger/status channels
#                   are unavoidably in this class, because no pre-existing
#                   entry point could ever have caught a worktree edit up.
##############################################################################


def _sha_of(text: str) -> str:
    """Hash via THE shared hasher, never a second implementation (#1505)."""
    base = Path.home() / ".cache" / "noorinalabs-test-ontology-tracker"
    base.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=str(base), suffix=".probe", delete=False) as fh:
        fh.write(text)
        probe = Path(fh.name)
    try:
        digest = checksums_io.compute_sha256(probe)
    finally:
        probe.unlink(missing_ok=True)
    assert digest is not None
    return digest


class _MergeScenarioMixin(_FakeRepoRootMixin):
    """A real main checkout, a real linked worktree, and a real merge.

    Not a simulation of git's layout — ``git init`` + ``git worktree add`` +
    ``git merge``, following the fixture style the ``da-wt-490`` regression
    tests established at the bottom of ``LinkedWorktreeTests``. The whole
    point of #1219 is a property of git's worktree layout, so a fabricated
    ``.git`` pointer would prove the predicate's shape rather than the
    scenario.

    Layout after ``setUp``:

      <root>/.claude/hooks/tracked_hook.py   — content "v1", CLEAN in the
                                               ledger (both hashes == sha(v1))
      <root>/ontology/checksums.json         — the ledger
      <root>/wt/                             — linked worktree on branch `wt`
    """

    TRACKED_REL = ".claude/hooks/tracked_hook.py"
    NEW_REL = ".claude/hooks/brand_new_hook.py"
    V1 = "# v1\nVALUE = 1\n"
    V2 = "# v2 — edited in a worktree\nVALUE = 2\nEXTRA = 'added'\n"
    NEW_BODY = "# created only in a worktree\nNEW = True\n"

    def _git(self, *args: str, cwd: Path) -> None:
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.com",
                *args,
            ],
            cwd=str(cwd),
            check=True,
            capture_output=True,
            env=hook._hermetic_git_env(),
        )

    def setUp(self):
        super().setUp()
        subprocess.run(
            ["git", "init", "-q", str(self._fake_root)],
            check=True,
            capture_output=True,
            env=hook._hermetic_git_env(),
        )
        tracked = self._fake_root / self.TRACKED_REL
        tracked.parent.mkdir(parents=True, exist_ok=True)
        tracked.write_text(self.V1, encoding="utf-8")

        self.sha_v1 = _sha_of(self.V1)
        self.sha_v2 = _sha_of(self.V2)
        self.sha_new = _sha_of(self.NEW_BODY)

        self.ledger = self._fake_root / "ontology" / "checksums.json"
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        self._write_ledger(
            {
                self.TRACKED_REL: {
                    "last_tracked": self.sha_v1,
                    "last_resolved": self.sha_v1,
                    "tracked_at": "2026-07-19T17:16:51+00:00",
                    "resolved_at": "2026-07-19T17:15:00+00:00",
                }
            }
        )
        self._git("add", "-A", cwd=self._fake_root)
        self._git("commit", "-qm", "seed", cwd=self._fake_root)

        self._orig_checksums = hook.CHECKSUMS_FILE
        hook.CHECKSUMS_FILE = self.ledger

        self.wt = self._fake_root / "wt"
        self._git("worktree", "add", "-q", "-b", "wt", str(self.wt), cwd=self._fake_root)

    def tearDown(self):
        hook.CHECKSUMS_FILE = self._orig_checksums
        super().tearDown()

    # -- helpers ---------------------------------------------------------

    def _write_ledger(self, files: dict) -> None:
        self.ledger.write_text(
            json.dumps({"version": 1, "files": files}, indent=2) + "\n", encoding="utf-8"
        )

    def _entries(self) -> dict:
        return json.loads(self.ledger.read_text(encoding="utf-8"))["files"]

    def _head_sha(self) -> str:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(self._fake_root),
            check=True,
            capture_output=True,
            text=True,
            env=hook._hermetic_git_env(),
        )
        return proc.stdout.strip()

    def _edit_in_worktree_and_merge(self) -> str:
        """The whole #1219 scenario. Returns the pre-merge SHA on the main branch.

        1. Edit a tracked file and create a new one, both inside the worktree.
        2. Fire the PostToolUse hook on each, exactly as the dispatcher would.
        3. Commit in the worktree and merge into the main branch.
        """
        (self.wt / self.TRACKED_REL).write_text(self.V2, encoding="utf-8")
        new_file = self.wt / self.NEW_REL
        new_file.write_text(self.NEW_BODY, encoding="utf-8")

        self.hook_results = [
            hook.check(
                {"tool_name": "Edit", "tool_input": {"file_path": str(self.wt / self.TRACKED_REL)}}
            ),
            hook.check({"tool_name": "Write", "tool_input": {"file_path": str(new_file)}}),
        ]

        self._git("add", "-A", cwd=self.wt)
        self._git("commit", "-qm", "worktree work", cwd=self.wt)
        pre_merge = self._head_sha()
        self._git("merge", "--no-ff", "-q", "-m", "merge wt", "wt", cwd=self._fake_root)
        return pre_merge

    def _run_cli(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", err):
            try:
                hook.main(list(args))
                code = 0
            except SystemExit as exc:
                code = int(exc.code) if exc.code is not None else 0
        return code, out.getvalue(), err.getvalue()

    def _catch_up(self, *args: str) -> tuple[int, str, str]:
        return self._run_cli(
            "catch-up",
            "--checksums",
            str(self.ledger),
            "--repo-root",
            str(self._fake_root),
            *args,
        )


class WorktreeCatchUpScenarioTests(_MergeScenarioMixin, unittest.TestCase):
    """The three channels of #1219, before and after the catch-up runs.

    The pre-catch-up assertions in each test are the PRE-FIX state verbatim:
    they are what the ledger, ``status`` and the hook's return said on
    2026-09-08 for every worktree-authored edit in this org, and they still
    say it immediately after the merge. The post-catch-up assertions are the
    ones that fail without this PR.
    """

    def test_channel_i_ledger_entry_is_frozen_at_the_pre_edit_hash_until_catch_up(self):
        """(i) The ledger. Pre: last_tracked still sha(v1). Post: sha(v2)."""
        pre_merge = self._edit_in_worktree_and_merge()

        # Pre-catch-up — the state this row exists to fix. The file on the
        # main checkout is v2; the ledger still remembers v1 and says so
        # nowhere, because both stored hashes agree with each other.
        entry = self._entries()[self.TRACKED_REL]
        self.assertEqual(entry["last_tracked"], self.sha_v1)
        self.assertEqual(entry["last_resolved"], self.sha_v1)
        self.assertEqual((self._fake_root / self.TRACKED_REL).read_text(encoding="utf-8"), self.V2)

        code, out, _ = self._catch_up("--since", pre_merge, "--apply")
        self.assertEqual(code, hook.CATCH_UP_EXIT_OK, out)

        entry = self._entries()[self.TRACKED_REL]
        self.assertEqual(entry["last_tracked"], self.sha_v2)
        # THE invariant: catching up records that the file changed, never
        # that anyone read it. Touching either of these two fields would
        # manufacture the false clean #1513 exists to prevent.
        self.assertEqual(entry["last_resolved"], self.sha_v1)
        self.assertEqual(entry["resolved_at"], "2026-07-19T17:15:00+00:00")

    def test_channel_ii_status_says_drifted_before_and_dirty_after(self):
        """(ii) ``status``: the WRONG remedy before, the right one after.

        Drifted routes to "reconcile the overlay against the file" (exit 4).
        Dirty routes to ``/ontology-rebuild`` (exit 1). An ordinary edit is
        the second thing, and before this PR it was reported as the first.
        """
        pre_merge = self._edit_in_worktree_and_merge()

        before = checksums_io.read_status(self.ledger, self._fake_root)
        self.assertEqual([p for p, _ in before.drifted], [self.TRACKED_REL])
        self.assertEqual(list(before.dirty), [])
        self.assertFalse(before.clean)

        self._catch_up("--since", pre_merge, "--apply")

        after = checksums_io.read_status(self.ledger, self._fake_root)
        self.assertEqual(list(after.drifted), [])
        self.assertIn(self.TRACKED_REL, after.dirty)
        self.assertFalse(after.clean)

    def test_channel_ii_a_worktree_only_new_file_is_absent_then_present_and_dirty(self):
        """(ii-b) The worse half of the gap: NO entry at all.

        A file created only in a worktree is not drifted, not dirty, not
        undeterminable — it is absent from ``status --json`` entirely, which
        is byte-identical to how the reader renders a path the overlay was
        never meant to describe. There is no channel on which those two
        differ, which is why case (b) is worse than drift.
        """
        pre_merge = self._edit_in_worktree_and_merge()

        self.assertNotIn(self.NEW_REL, self._entries())
        before = checksums_io.read_status(self.ledger, self._fake_root)
        self.assertNotIn(self.NEW_REL, before.not_current)

        self._catch_up("--since", pre_merge, "--apply")

        entry = self._entries()[self.NEW_REL]
        self.assertEqual(entry["last_tracked"], self.sha_new)
        self.assertEqual(entry["last_resolved"], "")
        after = checksums_io.read_status(self.ledger, self._fake_root)
        self.assertIn(self.NEW_REL, after.dirty)

    def test_channel_ii_json_payload_moves_the_path_from_drifted_to_dirty(self):
        """The ``--json`` channel specifically — a consumer that re-derives.

        ``status``'s JSON is its own channel: ``/session-start`` reads the
        exit code, but anything scripting the reader subsets these lists. Both
        have to move or the correction is invisible to one of them.
        """
        pre_merge = self._edit_in_worktree_and_merge()
        code, payload = self._status_json()
        # EXIT CODE is its own channel — /session-start 3a and
        # /ontology-librarian 1a branch on it, and 4 vs 1 is the difference
        # between "reconcile the overlay" and "run /ontology-rebuild".
        self.assertEqual(code, checksums_io.EXIT_DRIFTED)
        self.assertEqual([d["path"] for d in payload["drifted"]], [self.TRACKED_REL])
        self.assertEqual(payload["dirty"], [])
        self.assertNotIn(self.NEW_REL, json.dumps(payload))

        self._catch_up("--since", pre_merge, "--apply")

        code, payload = self._status_json()
        self.assertEqual(code, checksums_io.EXIT_NEEDS_ATTENTION)
        self.assertEqual(payload["drifted"], [])
        self.assertEqual(sorted(payload["dirty"]), sorted([self.NEW_REL, self.TRACKED_REL]))
        self.assertTrue(payload["verified"])
        self.assertFalse(payload["clean"])

    def _status_json(self) -> tuple[int, dict]:
        """Drive the reader as a SUBPROCESS, so the exit code is a real one."""
        proc = subprocess.run(
            [
                sys.executable,
                str(_test_helpers.HOOKS_DIR.parent / "lib" / "checksums_io.py"),
                "status",
                "--checksums",
                str(self.ledger),
                "--repo-root",
                str(self._fake_root),
                "--json",
            ],
            capture_output=True,
            text=True,
            env=hook._hermetic_git_env(),
        )
        return proc.returncode, json.loads(proc.stdout)

    def test_channel_iii_hook_return_names_the_skip_instead_of_returning_none(self):
        """(iii) The hook's own return — the VALUE-shaped pre-fix failure.

        Pre-#1219 both of these calls returned ``None``, the same value the
        hook returns for a NotebookEdit it was never registered for. A caller
        had to infer "an edit happened that I did not record" from the absence
        of any signal, which is not an inference anything downstream makes.
        """
        self._edit_in_worktree_and_merge()
        edited, created = self.hook_results

        self.assertEqual(edited["action"], "skipped_worktree")
        self.assertEqual(edited["canonical_path"], self.TRACKED_REL)
        self.assertEqual(created["action"], "skipped_worktree")
        self.assertEqual(created["canonical_path"], self.NEW_REL)

        # And it is distinguishable from the SUCCESS action, which is the
        # comparison clause 2 actually asks for.
        main_side = self._fake_root / "ontology" / "domain.yaml"
        main_side.write_text("entities: []\n", encoding="utf-8")
        tracked = hook.check({"tool_name": "Write", "tool_input": {"file_path": str(main_side)}})
        self.assertEqual(tracked["action"], "tracked")

    def test_channel_iii_render_fires_only_when_the_ledger_actually_diverges(self):
        """The rendered half of channel (iii), and its deliberate bound.

        An edit to a TRACKED file whose bytes no longer match ``last_tracked``
        is a real, silent loss — it gets a ``systemMessage``. A brand-new file
        has no entry to diverge from, so it stays quiet on the render channel
        and is carried on the return value alone; ``catch-up --since`` is what
        picks it up, once the merge makes a canonical file exist to hash.
        """
        self._edit_in_worktree_and_merge()
        edited, created = self.hook_results

        self.assertTrue(edited.get("diverged_from_ledger"))
        self.assertIn("will NOT reach ontology/checksums.json", edited["systemMessage"])
        self.assertIn(self.TRACKED_REL, edited["systemMessage"])
        self.assertIn("catch-up", edited["systemMessage"])

        self.assertNotIn("systemMessage", created)
        self.assertNotIn("diverged_from_ledger", created)

    def test_worktree_edit_still_writes_no_worktree_keyed_entry(self):
        """The deliberate skip semantics that STAY (#523/#525).

        The whole failure mode the skip was added for is a ``wt/…`` key
        outliving the tree it named. Nothing in this PR may re-admit one, and
        the ledger must be byte-identical across the worktree edits.
        """
        before = self.ledger.read_bytes()
        self._edit_in_worktree_and_merge()
        self.assertEqual(self.ledger.read_bytes(), before)
        self.assertEqual(set(self._entries()), {self.TRACKED_REL})

    def test_catch_up_never_creates_a_worktree_keyed_entry_either(self):
        """--all sweeps the ledger; the worktree copy must not become a key."""
        pre_merge = self._edit_in_worktree_and_merge()
        self._catch_up("--since", pre_merge, "--apply")
        for key in self._entries():
            self.assertFalse(key.startswith("wt/"), key)
            self.assertFalse(hook._is_worktree_path(key), key)


class CatchUpCliTests(_MergeScenarioMixin, unittest.TestCase):
    """The CLI's own contract: scope, dry-run, exit codes, refusals."""

    def test_dry_run_is_the_default_and_writes_nothing(self):
        pre_merge = self._edit_in_worktree_and_merge()
        before = self.ledger.read_bytes()

        code, out, _ = self._catch_up("--since", pre_merge)

        self.assertEqual(self.ledger.read_bytes(), before)
        self.assertEqual(code, hook.CATCH_UP_EXIT_PENDING)
        self.assertIn("DRY RUN", out)
        self.assertIn("VERDICT: PENDING", out)

    def test_pending_dry_run_exit_is_distinguishable_from_a_clean_one(self):
        """Exit 1 vs exit 0 — the channel a gate would branch on."""
        pre_merge = self._edit_in_worktree_and_merge()
        self.assertEqual(self._catch_up("--since", pre_merge)[0], hook.CATCH_UP_EXIT_PENDING)
        self._catch_up("--since", pre_merge, "--apply")
        code, out, _ = self._catch_up("--since", pre_merge)
        self.assertEqual(code, hook.CATCH_UP_EXIT_OK, out)
        self.assertIn("VERDICT: NOTHING TO CATCH UP", out)
        self.assertIn("measured zero", out)

    def test_an_empty_scope_is_not_reported_as_a_clean_one(self):
        """The silent-zero guard: 0 hashed != 0 behind.

        Naming only paths the include policy filters out hashes nothing. The
        pre-#1219 shape of this bug is exactly a count of zero that reads as
        health, so the verdict has to say which zero it is.
        """
        code, out, _ = self._catch_up("--paths", "ontology/checksums.json")
        self.assertEqual(code, hook.CATCH_UP_EXIT_OK)
        self.assertIn("VERDICT: NOTHING MEASURED", out)
        self.assertIn("EMPTY SCOPE, not a clean one", out)
        self.assertNotIn("NOTHING TO CATCH UP", out)

    def test_missing_scope_selector_is_a_usage_error_not_a_wholesale_run(self):
        code, _, err = self._catch_up()
        self.assertEqual(code, hook.CATCH_UP_EXIT_USAGE)
        self.assertIn("#1513", err)

    def test_unresolvable_since_ref_exits_3_rather_than_reporting_an_empty_scope(self):
        """ "Could not evaluate" is not a pass (bar clause 2a).

        A bad ref makes ``git diff`` fail. Treating its empty stdout as an
        empty scope would print "nothing to catch up" and exit 0 — the exact
        fail-open the amended clause was written for.
        """
        code, out, err = self._catch_up("--since", "no-such-ref-deadbeef")
        self.assertEqual(code, hook.CATCH_UP_EXIT_UNREADABLE)
        self.assertIn("could not evaluate", err)
        self.assertNotIn("NOTHING", out)

    def test_unreadable_ledger_exits_3(self):
        self.ledger.write_text("{ not json", encoding="utf-8")
        code, _, err = self._catch_up("--paths", self.TRACKED_REL)
        self.assertEqual(code, hook.CATCH_UP_EXIT_UNREADABLE)
        self.assertIn("error:", err)

    def test_a_tracked_path_absent_from_this_tree_is_unmeasurable_not_caught_up(self):
        """Exit 4, and the entry is left exactly as it was — never pruned."""
        entries = self._entries()
        entries["noorinalabs-deploy/terraform/main.tf"] = {
            "last_tracked": "a" * 64,
            "last_resolved": "a" * 64,
            "tracked_at": "2026-01-01T00:00:00+00:00",
            "resolved_at": "2026-01-01T00:00:00+00:00",
        }
        self._write_ledger(entries)

        code, out, _ = self._catch_up("--all", "--apply")

        self.assertEqual(code, hook.CATCH_UP_EXIT_UNMEASURABLE)
        self.assertIn("unmeasurable", out)
        self.assertIn("noorinalabs-deploy/terraform/main.tf", self._entries())
        self.assertEqual(
            self._entries()["noorinalabs-deploy/terraform/main.tf"]["last_tracked"], "a" * 64
        )

    def test_unmeasurable_outranks_pending_on_the_exit_code(self):
        """4 over 1, for the same reason ``status``'s 4 outranks its 1: a
        partly-measured scope must not report as a measured one."""
        pre_merge = self._edit_in_worktree_and_merge()
        entries = self._entries()
        entries["gone/file.py"] = {
            "last_tracked": "b" * 64,
            "last_resolved": "b" * 64,
            "tracked_at": "",
            "resolved_at": "",
        }
        self._write_ledger(entries)
        code, _, _ = self._catch_up("--since", pre_merge, "--paths", "gone/file.py")
        self.assertEqual(code, hook.CATCH_UP_EXIT_UNMEASURABLE)

    def test_self_entry_for_checksums_json_is_skipped_not_advanced(self):
        """The fixpoint hazard: advancing the ledger's own entry chases a
        hash that the write itself changes. ``SKIP_PATTERNS`` already says
        this file is not the overlay's business; catch-up honours the same
        predicate rather than a second copy of the policy."""
        entries = self._entries()
        entries["ontology/checksums.json"] = {
            "last_tracked": "c" * 64,
            "last_resolved": "c" * 64,
            "tracked_at": "",
            "resolved_at": "",
        }
        self._write_ledger(entries)

        _, out, _ = self._catch_up("--all")

        self.assertIn("ontology/checksums.json: skip_pattern", out)
        self.assertEqual(self._entries()["ontology/checksums.json"]["last_tracked"], "c" * 64)

    def test_all_says_out_loud_that_the_wholesale_pass_belongs_to_1513(self):
        _, out, _ = self._catch_up("--all")
        self.assertIn("#1513", out)

    def test_running_against_a_linked_worktree_root_is_refused(self):
        """From a worktree every path is filtered by the very skip catch-up
        compensates for, so the run could only report an empty scope."""
        code, out, err = self._run_cli(
            "catch-up", "--checksums", str(self.ledger), "--repo-root", str(self.wt), "--all"
        )
        self.assertEqual(code, hook.CATCH_UP_EXIT_UNREADABLE)
        self.assertIn("linked worktree", err)
        self.assertEqual(out, "")

    def test_json_channel_carries_the_same_verdict_as_the_render(self):
        pre_merge = self._edit_in_worktree_and_merge()
        code, out, _ = self._catch_up("--since", pre_merge, "--json")
        payload = json.loads(out)
        self.assertEqual(code, hook.CATCH_UP_EXIT_PENDING)
        self.assertFalse(payload["applied"])
        self.assertEqual(payload["written"], 0)
        self.assertEqual([a["path"] for a in payload["advanced"]], [self.TRACKED_REL])
        self.assertEqual([c["path"] for c in payload["created"]], [self.NEW_REL])

    def test_unknown_subcommand_is_a_usage_error(self):
        code, _, err = self._run_cli("mark-resolved", "x")
        self.assertEqual(code, hook.CATCH_UP_EXIT_USAGE)
        self.assertIn("usage:", err)

    def test_apply_catch_up_never_writes_the_resolved_fields(self):
        """Unit-level guard on the invariant the whole design rests on."""
        data = {"version": 1, "files": dict(self._entries())}
        plan = hook.plan_catch_up(data, self._fake_root, [self.TRACKED_REL])
        (self._fake_root / self.TRACKED_REL).write_text(self.V2, encoding="utf-8")
        plan = hook.plan_catch_up(data, self._fake_root, [self.TRACKED_REL])
        self.assertEqual([p for p, _ in plan.advanced], [self.TRACKED_REL])

        hook.apply_catch_up(data, plan, "2026-09-08T00:00:00+00:00")
        entry = data["files"][self.TRACKED_REL]
        self.assertEqual(entry["last_tracked"], self.sha_v2)
        self.assertEqual(entry["last_resolved"], self.sha_v1)
        self.assertEqual(entry["resolved_at"], "2026-07-19T17:15:00+00:00")
        self.assertEqual(entry["tracked_at"], "2026-09-08T00:00:00+00:00")


class CheckReturnChannelTests(_FakeRepoRootMixin, unittest.TestCase):
    """The full ``check()`` action vocabulary — every non-applicable return.

    Pre-#1219 every row below except ``tracked``/``skip_noop`` returned a bare
    ``None``. ``post_dispatcher`` writes a ``posttooluse_dispatch`` trace
    record iff ``isinstance(result, dict)``, so ``None`` meant no evidence
    survived the call at all.

    ``CHECKSUMS_FILE`` is redirected to a temp ledger for the whole class, not
    just the tests that expect a write. ``_is_git_ignored`` fails OPEN, so any
    fixture whose ``git check-ignore`` does not resolve takes the TRACKED
    branch instead of the skip branch under test — and with the real
    ``CHECKSUMS_FILE`` still in place that writes a fixture path into the
    repository's committed ledger. That is not hypothetical: it happened while
    writing these tests and put ``generated/out.md`` into
    ``ontology/checksums.json``.
    """

    def setUp(self):
        super().setUp()
        self._ledger = self._fake_root / "ontology" / "checksums.json"
        self._ledger.parent.mkdir(parents=True, exist_ok=True)
        self._ledger.write_text('{"version": 1, "files": {}}\n', encoding="utf-8")
        self._orig_checksums = hook.CHECKSUMS_FILE
        hook.CHECKSUMS_FILE = self._ledger

    def tearDown(self):
        hook.CHECKSUMS_FILE = self._orig_checksums
        super().tearDown()

    def test_non_edit_tool_is_still_none(self):
        """The one honest ``None``: this hook is registered for Edit/Write
        only, so a Bash payload genuinely did not apply to it."""
        self.assertIsNone(hook.check({"tool_name": "Bash", "tool_input": {"command": "ls"}}))

    def test_missing_file_path_is_still_none(self):
        self.assertIsNone(hook.check({"tool_name": "Edit", "tool_input": {}}))

    def test_gitignored_skip_names_its_reason(self):
        """A real ``git init`` — ``_is_git_ignored`` shells out to git and
        fails OPEN, so a fabricated ``.git`` directory would silently take the
        tracked branch and make this assertion about nothing."""
        subprocess.run(
            ["git", "init", "-q", str(self._fake_root)],
            check=True,
            capture_output=True,
            env=hook._hermetic_git_env(),
        )
        (self._fake_root / ".gitignore").write_text("generated/\n", encoding="utf-8")
        f = self._fake_root / "generated" / "out.md"
        f.parent.mkdir(parents=True)
        f.write_text("x\n", encoding="utf-8")

        result = hook.check({"tool_name": "Write", "tool_input": {"file_path": str(f)}})
        self.assertEqual(result["action"], "skipped")
        self.assertEqual(result["reason"], "gitignored")

    def test_tmp_skip_names_its_reason(self):
        result = hook.check(
            {"tool_name": "Write", "tool_input": {"file_path": "/tmp/issue-body-1219.md"}}
        )
        self.assertEqual(result["action"], "skipped")
        self.assertEqual(result["reason"], "tmp_prefix")

    def test_unhashable_in_scope_file_reports_unreadable_not_nothing(self):
        """ "Could not evaluate" is not "nothing to do" (bar clause 2a).

        Pre-#1219 a tracked file the hasher could not read returned ``None``,
        which is what the hook also returns for a tool it does not handle.
        """
        f = self._fake_root / "ontology" / "domain.yaml"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("entities: []\n", encoding="utf-8")
        with mock.patch.object(hook.checksums_io, "compute_sha256", return_value=None):
            result = hook.check({"tool_name": "Write", "tool_input": {"file_path": str(f)}})
        self.assertEqual(result["action"], "unreadable")
        self.assertEqual(result["path"], "ontology/domain.yaml")

    def test_every_action_string_is_distinct(self):
        """A vocabulary whose members collide distinguishes nothing."""
        actions = [
            hook.ACTION_TRACKED,
            hook.ACTION_SKIP_NOOP,
            hook.ACTION_SKIPPED,
            hook.ACTION_SKIPPED_WORKTREE,
            hook.ACTION_UNREADABLE,
        ]
        self.assertEqual(len(set(actions)), len(actions))


class DispatcherTraceChannelTests(_MergeScenarioMixin, unittest.TestCase):
    """(iv) The consumer's channel: ``post_dispatcher``'s trace branch.

    ``post_dispatcher.main`` computes
    ``should_trace = _TRACE_EVERY or raised or isinstance(result, dict)`` and
    only then writes a ``posttooluse_dispatch`` annunaki record. That is a
    genuine control-flow branch in a caller, not a rendering detail, so a
    worktree edit returning ``None`` left no record anywhere — the forensic
    channel `/annunaki` reads was as blind as the ledger.
    """

    def test_a_worktree_skip_now_produces_a_dispatch_trace_record(self):
        import post_dispatcher as pd

        f = self.wt / self.TRACKED_REL
        f.write_text(self.V2, encoding="utf-8")
        payload = {"tool_name": "Edit", "tool_input": {"file_path": str(f)}}

        recorded: list[dict] = []

        def _capture(module_name, command, outcome, tool_name="Bash"):
            recorded.append({"module": module_name, "outcome": outcome, "tool_name": tool_name})

        stdin, stdout = io.StringIO(json.dumps(payload)), io.StringIO()
        with (
            mock.patch.object(pd, "log_posttooluse_dispatch", _capture),
            mock.patch("suggest_generic_prompt.check", return_value=None),
            mock.patch("validate_edit_completion.check", return_value=None),
            mock.patch.object(sys, "stdin", stdin),
            mock.patch.object(sys, "stdout", stdout),
        ):
            with self.assertRaises(SystemExit) as ctx:
                pd.main()

        self.assertEqual(int(ctx.exception.code or 0), 0)
        tracker_records = [r for r in recorded if r["module"] == "ontology_tracker"]
        self.assertEqual(len(tracker_records), 1)
        self.assertIn("skipped_worktree", tracker_records[0]["outcome"]["returned"])
        # Pre-#1219 this was the literal string "None" — the same value the
        # dispatcher records for a hook that did not apply, when it records
        # anything at all.
        self.assertNotEqual(tracker_records[0]["outcome"]["returned"], "None")

    def test_the_render_channel_surfaces_the_divergence_advisory(self):
        """The dispatcher aggregates ``systemMessage`` into its stdout — the
        channel a human actually sees. A dict with no message reaches the
        trace channel only; a divergence reaches both."""
        import post_dispatcher as pd

        f = self.wt / self.TRACKED_REL
        f.write_text(self.V2, encoding="utf-8")
        payload = {"tool_name": "Edit", "tool_input": {"file_path": str(f)}}

        stdin, stdout = io.StringIO(json.dumps(payload)), io.StringIO()
        with (
            mock.patch.object(pd, "log_posttooluse_dispatch", lambda *a, **k: None),
            mock.patch("suggest_generic_prompt.check", return_value=None),
            mock.patch("validate_edit_completion.check", return_value=None),
            mock.patch.object(sys, "stdin", stdin),
            mock.patch.object(sys, "stdout", stdout),
        ):
            with self.assertRaises(SystemExit):
                pd.main()

        emitted = json.loads(stdout.getvalue())
        self.assertIn("will NOT reach ontology/checksums.json", emitted["systemMessage"])


class LedgerFieldNameCouplingTests(unittest.TestCase):
    """The writer and the classifier must name the same field.

    #1142's failure was a reader comparing a ``sha256`` key that has never
    existed in this schema and getting a plausible zero. ``catch-up`` writes
    ``last_tracked``; ``classify_entry`` reads it. This module does not import
    that private constant, so the coupling is pinned here instead of assumed.
    """

    def test_tracker_and_checksums_io_agree_on_last_tracked(self):
        self.assertEqual(hook._LAST_TRACKED, checksums_io._TRACKED_KEY)

    def test_apply_catch_up_writes_the_field_classify_entry_reads(self):
        data = {"version": 1, "files": {}}
        plan = hook.CatchUpPlan(
            advanced=(), created=(("a/b.py", "d" * 64),), in_sync=(), unmeasurable=(), skipped=()
        )
        hook.apply_catch_up(data, plan, "2026-09-08T00:00:00+00:00")
        state, _ = checksums_io.classify_entry(data["files"]["a/b.py"])
        self.assertEqual(state, checksums_io.ENTRY_DIRTY)


if __name__ == "__main__":
    unittest.main()
