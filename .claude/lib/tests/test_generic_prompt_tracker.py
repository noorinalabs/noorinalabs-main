"""Tests for generic_prompt_tracker — the state backbone for the batched
wave-lifecycle genericize checkpoint (main#716).

Coverage maps to the issue's three acceptance criteria:

  AC1 (checkpoint enumerates changed .claude/ artifacts lacking a counterpart)
      → undecided_candidates returns undecided genericizable artifacts, and
        classify/normalize_rel_path feed it the right shape.
  AC2 (per-edit systemMessage no longer fires; demoted to silent tracking)
      → exercised in test_suggest_generic_prompt.py; here we verify the
        record_candidate feeder writes pending state silently.
  AC3 (decisions recorded so the same artifact isn't re-surfaced every wave)
      → record_decision settles an artifact; undecided_candidates excludes
        both skipped and genericized paths thereafter.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

# Helper lives at .claude/lib/generic_prompt_tracker.py; this test is at
# .claude/lib/tests/test_*.py. parent.parent reaches the lib root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import generic_prompt_tracker as gpt  # noqa: E402


class NormalizeRelPathTest(unittest.TestCase):
    def test_absolute_path_under_claude(self) -> None:
        self.assertEqual(
            gpt.normalize_rel_path("/home/u/repo/.claude/hooks/foo.py"),
            "hooks/foo.py",
        )

    def test_worktree_nested_splits_on_last_marker(self) -> None:
        # A worktree lives under .claude/worktrees/<wt>/.claude/... — the LAST
        # /.claude/ yields the artifact path inside the worktree's own repo.
        p = "/home/u/repo/.claude/worktrees/0716-x/.claude/skills/wave-wrapup/SKILL.md"
        self.assertEqual(gpt.normalize_rel_path(p), "skills/wave-wrapup/SKILL.md")

    def test_bare_claude_relative(self) -> None:
        self.assertEqual(gpt.normalize_rel_path(".claude/settings.json"), "settings.json")

    def test_outside_claude_returns_none(self) -> None:
        self.assertIsNone(gpt.normalize_rel_path("/home/u/repo/src/app.py"))
        self.assertIsNone(gpt.normalize_rel_path(""))

    def test_skip_listed_tracker_churn_returns_none(self) -> None:
        self.assertIsNone(gpt.normalize_rel_path("/r/.claude/ontology/checksums.json"))
        self.assertIsNone(gpt.normalize_rel_path("/r/.claude/annunaki/errors.jsonl"))

    def test_noise_subtree_rel_prefixes_return_none(self) -> None:
        # worktrees/ memory/ scratch are whole-subtree noise — a path that
        # NORMALIZES to one of these rel prefixes is not a genericize candidate.
        self.assertIsNone(gpt.normalize_rel_path("/r/.claude/worktrees/agent-x/foo.txt"))
        self.assertIsNone(gpt.normalize_rel_path(".claude/memory/feedback_x.md"))
        self.assertIsNone(gpt.normalize_rel_path("/r/.claude/scratch/tmp.md"))
        self.assertIsNone(gpt.normalize_rel_path(".claude/scratch_pr_768.md"))

    def test_consulted_session_marker_returns_none(self) -> None:
        # main#1140: Hook-15 consultation sentinel markers (e.g. ontology-
        # librarian's per-cwd .marker file) are the largest ONGOING noise
        # class (13 of a live 267-entry ledger, by first_seen recency) —
        # never a genericize candidate.
        self.assertIsNone(
            gpt.normalize_rel_path("/r/.claude/.consulted/ontology-librarian/abc123.marker")
        )
        self.assertIsNone(gpt.normalize_rel_path(".claude/.consulted/session-start/x.marker"))

    def test_user_space_jobs_and_projects_return_none(self) -> None:
        # main#1140 PR #1186 merge-gate review: user-space ~/.claude/jobs/ and
        # ~/.claude/projects/ paths dominated a live 267-entry ledger's raw
        # VOLUME (178 + 6 of 267) because normalize_rel_path splits on the
        # LAST /.claude/ with no REPO_ROOT containment check — it can't tell
        # the user-space Claude home from the repo's (the containment fix is
        # #1191; this prefix is the interim intake mitigation).
        self.assertIsNone(gpt.normalize_rel_path("/home/u/.claude/jobs/a36d08f0/tmp/foo.py"))
        self.assertIsNone(
            gpt.normalize_rel_path("/home/u/.claude/projects/-home-u-main/memory/note.md")
        )

    def test_real_artifact_edited_inside_worktree_still_tracked(self) -> None:
        # The rel-prefix skip is checked against the NORMALIZED rel, not the raw
        # path, so a real artifact edited in a worktree (collapses to its inner
        # rel) is still tracked — the worktrees/ prefix must not over-match it.
        p = "/home/u/repo/.claude/worktrees/0716-x/.claude/hooks/foo.py"
        self.assertEqual(gpt.normalize_rel_path(p), "hooks/foo.py")

    def test_tracker_own_state_files_not_tracked(self) -> None:
        self.assertIsNone(gpt.normalize_rel_path("/r/.claude/generic_prompt_pending.json"))
        self.assertIsNone(gpt.normalize_rel_path("/r/.claude/generic_prompt_ledger.json"))


class ClassifyTest(unittest.TestCase):
    def test_categories(self) -> None:
        self.assertEqual(gpt.classify("hooks/foo.py")["category"], "hook")
        self.assertEqual(gpt.classify("skills/wave-wrapup/SKILL.md")["category"], "skill")
        self.assertEqual(gpt.classify("team/charter/agents.md")["category"], "charter")
        self.assertEqual(gpt.classify("settings.json")["category"], "settings")

    def test_fallback_category(self) -> None:
        info = gpt.classify("ontology/domain.yaml")
        self.assertEqual(info["category"], "configuration")
        self.assertIn("suggestion", info)


class _TmpStateMixin(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        root = Path(self._tmp.name)
        self.pending = root / "pending.json"
        self.ledger = root / "ledger.json"
        self.framework = root / "generic_prompts"
        self.framework.mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()


class RecordCandidateTest(_TmpStateMixin):
    def test_new_candidate_creates_entry(self) -> None:
        ok = gpt.record_candidate(
            "/r/.claude/hooks/foo.py", pending_path=self.pending, ledger_path=self.ledger, now="T1"
        )
        self.assertTrue(ok)
        data = json.loads(self.pending.read_text())
        entry = data["candidates"]["hooks/foo.py"]
        self.assertEqual(entry["category"], "hook")
        self.assertEqual(entry["count"], 1)
        self.assertEqual(entry["first_seen"], "T1")

    def test_repeat_increments_count_and_updates_last_seen(self) -> None:
        for t in ("T1", "T2", "T3"):
            gpt.record_candidate(
                "/r/.claude/hooks/foo.py", pending_path=self.pending, ledger_path=self.ledger, now=t
            )
        entry = json.loads(self.pending.read_text())["candidates"]["hooks/foo.py"]
        self.assertEqual(entry["count"], 3)
        self.assertEqual(entry["first_seen"], "T1")
        self.assertEqual(entry["last_seen"], "T3")

    def test_skip_listed_not_recorded(self) -> None:
        ok = gpt.record_candidate(
            "/r/.claude/ontology/checksums.json", pending_path=self.pending, ledger_path=self.ledger
        )
        self.assertFalse(ok)
        self.assertFalse(self.pending.exists())

    def test_already_decided_not_readded(self) -> None:
        gpt.record_decision(
            "hooks/foo.py",
            "skipped",
            detail="too project-specific",
            ledger_path=self.ledger,
            pending_path=self.pending,
        )
        ok = gpt.record_candidate(
            "/r/.claude/hooks/foo.py", pending_path=self.pending, ledger_path=self.ledger
        )
        self.assertFalse(ok)


class RecordDecisionTest(_TmpStateMixin):
    def test_writes_ledger_and_removes_from_pending(self) -> None:
        gpt.record_candidate(
            "/r/.claude/hooks/foo.py", pending_path=self.pending, ledger_path=self.ledger
        )
        rec = gpt.record_decision(
            "hooks/foo.py",
            "genericized",
            detail="GENERIC_HOOK.md",
            wave="P5W5",
            ledger_path=self.ledger,
            pending_path=self.pending,
            now="TD",
        )
        self.assertEqual(rec["decision"], "genericized")
        ledger = json.loads(self.ledger.read_text())
        self.assertEqual(ledger["decisions"]["hooks/foo.py"]["wave"], "P5W5")
        self.assertEqual(ledger["decisions"]["hooks/foo.py"]["decided_at"], "TD")
        pending = json.loads(self.pending.read_text())
        self.assertNotIn("hooks/foo.py", pending["candidates"])

    def test_invalid_decision_raises(self) -> None:
        with self.assertRaises(ValueError):
            gpt.record_decision(
                "hooks/foo.py", "maybe", ledger_path=self.ledger, pending_path=self.pending
            )


class UndecidedCandidatesTest(_TmpStateMixin):
    def _seed(self, *rel_paths: str) -> None:
        for rp in rel_paths:
            gpt.record_candidate(
                f"/r/.claude/{rp}", pending_path=self.pending, ledger_path=self.ledger
            )

    def test_returns_undecided_sorted(self) -> None:
        self._seed("skills/wave-wrapup/SKILL.md", "hooks/foo.py", "team/charter/agents.md")
        out = gpt.undecided_candidates(
            pending_path=self.pending, ledger_path=self.ledger, framework_dir=self.framework
        )
        cats = [(c["category"], c["rel_path"]) for c in out]
        # sorted by (category, rel_path): charter < hook < skill
        self.assertEqual(
            cats,
            [
                ("charter", "team/charter/agents.md"),
                ("hook", "hooks/foo.py"),
                ("skill", "skills/wave-wrapup/SKILL.md"),
            ],
        )

    def test_skipped_decision_excludes_from_worklist(self) -> None:
        self._seed("hooks/foo.py", "hooks/bar.py")
        gpt.record_decision(
            "hooks/foo.py",
            "skipped",
            detail="project-coupled",
            ledger_path=self.ledger,
            pending_path=self.pending,
        )
        rels = [
            c["rel_path"]
            for c in gpt.undecided_candidates(
                pending_path=self.pending, ledger_path=self.ledger, framework_dir=self.framework
            )
        ]
        self.assertEqual(rels, ["hooks/bar.py"])

    def test_genericized_with_existing_counterpart_excluded(self) -> None:
        # Re-seed pending directly (record_candidate would refuse a decided path)
        # to prove undecided_candidates ALSO filters on a live counterpart file.
        (self.framework / "GENERIC_HOOK.md").write_text("generic\n")
        gpt.save_pending(
            {"version": 1, "candidates": {"hooks/foo.py": {"category": "hook", "count": 1}}},
            self.pending,
        )
        gpt.save_ledger(
            {
                "version": 1,
                "decisions": {
                    "hooks/foo.py": {
                        "decision": "genericized",
                        "detail": "GENERIC_HOOK.md",
                        "wave": "P5W5",
                        "decided_at": "TD",
                    }
                },
            },
            self.ledger,
        )
        out = gpt.undecided_candidates(
            pending_path=self.pending, ledger_path=self.ledger, framework_dir=self.framework
        )
        self.assertEqual(out, [])

    def test_empty_pending_returns_empty(self) -> None:
        self.assertEqual(
            gpt.undecided_candidates(
                pending_path=self.pending, ledger_path=self.ledger, framework_dir=self.framework
            ),
            [],
        )


class HasLiveCounterpartTest(_TmpStateMixin):
    def test_missing_counterpart_file_is_not_live(self) -> None:
        ledger = {"decisions": {"hooks/foo.py": {"decision": "genericized", "detail": "NOPE.md"}}}
        self.assertFalse(gpt._has_live_counterpart("hooks/foo.py", ledger, self.framework))

    def test_skipped_is_never_a_counterpart(self) -> None:
        ledger = {"decisions": {"hooks/foo.py": {"decision": "skipped", "detail": ""}}}
        self.assertFalse(gpt._has_live_counterpart("hooks/foo.py", ledger, self.framework))


class CorruptStateTest(_TmpStateMixin):
    def test_corrupt_pending_heals_to_default(self) -> None:
        self.pending.write_text("{ not json")
        # Should not raise; record starts fresh.
        ok = gpt.record_candidate(
            "/r/.claude/hooks/foo.py", pending_path=self.pending, ledger_path=self.ledger
        )
        self.assertTrue(ok)
        self.assertIn("hooks/foo.py", json.loads(self.pending.read_text())["candidates"])


class ArchiveWavePendingTest(_TmpStateMixin):
    """Coverage for main#1140 — archive + reset the pending ledger per wave.

    Maps to the issue's acceptance criteria:
      - safe on missing/empty/malformed pending (no crash, no fabricated
        wave boundary)
      - noise classes (session markers) are dropped from the LIVE ledger but
        never silently lost — they land in the archive
      - a genuine undecided candidate is retained in the archive (recoverable)
        even though it is cleared from the live worklist
    """

    def setUp(self) -> None:
        super().setUp()
        self.archive_dir = Path(self._tmp.name) / "archive"

    def _seed_raw(self, candidates: dict) -> None:
        # Bypass record_candidate's intake filter to simulate entries recorded
        # under an OLDER, more permissive filter (pre-main#1140 .consulted/
        # entries, or long-undecided genuine artifacts from prior waves).
        gpt.save_pending({"version": 1, "candidates": candidates}, self.pending)

    def test_missing_pending_file_is_a_safe_noop(self) -> None:
        result = gpt.archive_wave_pending(
            "P10W29", pending_path=self.pending, archive_dir=self.archive_dir
        )
        self.assertEqual(
            result,
            {
                "archived": False,
                "wave": "P10W29",
                "noise_dropped": 0,
                "genuine_reset": 0,
                "archive_path": None,
            },
        )
        self.assertFalse(self.archive_dir.exists())

    def test_empty_candidates_is_a_safe_noop(self) -> None:
        self._seed_raw({})
        result = gpt.archive_wave_pending(
            "P10W29", pending_path=self.pending, archive_dir=self.archive_dir
        )
        self.assertFalse(result["archived"])
        self.assertFalse(self.archive_dir.exists())

    def test_malformed_pending_heals_and_is_a_safe_noop(self) -> None:
        self.pending.write_text("{ not json")
        result = gpt.archive_wave_pending(
            "P10W29", pending_path=self.pending, archive_dir=self.archive_dir
        )
        self.assertFalse(result["archived"])
        self.assertFalse(self.archive_dir.exists())

    def test_noise_class_dropped_from_live_but_archived(self) -> None:
        self._seed_raw(
            {
                ".consulted/ontology-librarian/abc.marker": {
                    "category": "configuration",
                    "first_seen": "T0",
                    "last_seen": "T1",
                    "count": 9,
                },
            }
        )
        result = gpt.archive_wave_pending(
            "P10W29", pending_path=self.pending, archive_dir=self.archive_dir, now="TA"
        )
        self.assertTrue(result["archived"])
        self.assertEqual(result["noise_dropped"], 1)
        self.assertEqual(result["genuine_reset"], 0)

        # Live ledger reset to empty.
        live = json.loads(self.pending.read_text())
        self.assertEqual(live["candidates"], {})

        # Never silently lost — recoverable from the archive.
        archive_path = self.archive_dir / "wave-P10W29.json"
        self.assertEqual(Path(result["archive_path"]), archive_path)
        archived = json.loads(archive_path.read_text())
        snapshot = archived["waves"][0]
        self.assertIn(".consulted/ontology-librarian/abc.marker", snapshot["noise_dropped"])
        self.assertEqual(snapshot["genuine_reset"], {})

    def test_genuine_candidate_retained_in_archive_not_silently_dropped(self) -> None:
        self._seed_raw(
            {
                "hooks/foo.py": {
                    "category": "hook",
                    "first_seen": "T0",
                    "last_seen": "T0",
                    "count": 1,
                },
            }
        )
        result = gpt.archive_wave_pending(
            "P10W29", pending_path=self.pending, archive_dir=self.archive_dir, now="TA"
        )
        self.assertTrue(result["archived"])
        self.assertEqual(result["noise_dropped"], 0)
        self.assertEqual(result["genuine_reset"], 1)

        # Cleared from the live worklist...
        live = json.loads(self.pending.read_text())
        self.assertEqual(live["candidates"], {})

        # ...but fully recoverable from the archive — this is the "never
        # silently drop a genuine undecided candidate" guarantee.
        archive_path = self.archive_dir / "wave-P10W29.json"
        archived = json.loads(archive_path.read_text())
        genuine = archived["waves"][0]["genuine_reset"]
        self.assertIn("hooks/foo.py", genuine)
        self.assertEqual(genuine["hooks/foo.py"]["category"], "hook")

    def test_mixed_noise_and_genuine_partitioned_correctly(self) -> None:
        self._seed_raw(
            {
                ".consulted/session-start/x.marker": {"category": "configuration", "count": 3},
                "hooks/foo.py": {"category": "hook", "count": 1},
                "team/charter/agents.md": {"category": "charter", "count": 2},
            }
        )
        result = gpt.archive_wave_pending(
            "P10W29", pending_path=self.pending, archive_dir=self.archive_dir
        )
        self.assertEqual(result["noise_dropped"], 1)
        self.assertEqual(result["genuine_reset"], 2)

    def test_missing_wave_label_does_not_fabricate_a_wave_boundary(self) -> None:
        self._seed_raw({"hooks/foo.py": {"category": "hook", "count": 1}})
        result = gpt.archive_wave_pending(
            "", pending_path=self.pending, archive_dir=self.archive_dir, now="2026-07-29T00:00:00Z"
        )
        self.assertTrue(result["archived"])
        # No specific wave number is invented — the filename falls back to a
        # timestamp, clearly distinguishable from a real wave label.
        self.assertIn("wave-unknown-", result["archive_path"])
        self.assertNotRegex(Path(result["archive_path"]).name, r"wave-P\d+W\d+\.json")

    def test_rerun_within_same_wave_accretes_not_clobbers(self) -> None:
        self._seed_raw({"hooks/foo.py": {"category": "hook", "count": 1}})
        gpt.archive_wave_pending(
            "P10W29", pending_path=self.pending, archive_dir=self.archive_dir, now="T1"
        )
        # New pending activity recorded after the first archive-wave run.
        self._seed_raw({"hooks/bar.py": {"category": "hook", "count": 1}})
        gpt.archive_wave_pending(
            "P10W29", pending_path=self.pending, archive_dir=self.archive_dir, now="T2"
        )
        archive_path = self.archive_dir / "wave-P10W29.json"
        archived = json.loads(archive_path.read_text())
        self.assertEqual(len(archived["waves"]), 2)
        self.assertIn("hooks/foo.py", archived["waves"][0]["genuine_reset"])
        self.assertIn("hooks/bar.py", archived["waves"][1]["genuine_reset"])

    def test_failed_archive_write_does_not_clear_live_ledger(self) -> None:
        # Pins archive-before-clear (main#1140 PR #1186 merge-gate review):
        # nothing asserted this ordering, so a future refactor could silently
        # reorder to clear-then-archive and still pass every OTHER test. This
        # occupies `archive_dir` with a plain file so `archive_dir.mkdir(...)`
        # raises before the live ledger is ever touched.
        seed = {"hooks/foo.py": {"category": "hook", "count": 1}}
        gpt.save_pending({"version": 1, "candidates": dict(seed)}, self.pending)
        blocked = Path(self._tmp.name) / "blocked"
        blocked.write_text("not a directory")  # archive_dir occupied -> mkdir raises
        with self.assertRaises(OSError):
            gpt.archive_wave_pending("P10W29", pending_path=self.pending, archive_dir=blocked)
        live = json.loads(self.pending.read_text())["candidates"]
        self.assertEqual(live, seed)

    def test_user_space_jobs_and_projects_are_noise_not_genuine(self) -> None:
        # main#1140 PR #1186 merge-gate review: a live 267-entry ledger was
        # dominated (178/267) by user-space ~/.claude/jobs/<id>/tmp/* harness
        # scratch (normalize_rel_path has no REPO_ROOT containment check, so
        # it can't distinguish the user-space Claude home from the repo's —
        # root-caused separately at #1191) plus 6 `projects/` user-space
        # auto-memory paths. Both must partition as noise, not genuine, or
        # the very first archive-wave run mislabels historical/user-space
        # scratch as "a real candidate that fell off the end of a wave".
        self._seed_raw(
            {
                "jobs/a36d08f0/tmp/foo.py": {"category": "configuration", "count": 1},
                "projects/-home-x-main/memory/note.md": {"category": "configuration", "count": 1},
                "hooks/foo.py": {"category": "hook", "count": 1},
            }
        )
        result = gpt.archive_wave_pending(
            "P10W29", pending_path=self.pending, archive_dir=self.archive_dir
        )
        self.assertEqual(result["noise_dropped"], 2)
        self.assertEqual(result["genuine_reset"], 1)


class CliTest(_TmpStateMixin):
    def test_main_requires_subcommand(self) -> None:
        with self.assertRaises(SystemExit):
            gpt.main([])

    def test_record_rejects_bad_decision_via_argparse(self) -> None:
        with self.assertRaises(SystemExit):
            gpt.main(["record", "hooks/foo.py", "bogus"])


if __name__ == "__main__":
    unittest.main()
