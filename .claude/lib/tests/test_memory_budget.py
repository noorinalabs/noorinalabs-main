"""Tests for memory_budget -- the project-memory corpus size/count budget (#733).

Two-tier index (#1016): MEMORY.md is a compact ToC; per-note one-liners live in
TIER-2 section_*.md files. Index entries are summed across the section files;
section files are excluded from the note-file count; the ToC's section-row count
and its byte size are their own capped dimensions.

Verifies:
  1. Under budget on all four dimensions -> exit 0, "within budget".
  2. Exactly AT each cap -> exit 0 (the cap is inclusive; at-limit is allowed).
  3. One-over on EACH dimension independently -> exit 1, names that dimension.
  4. The over-budget diagnostic is a HARD BLOCK with actionable content
     (current/limit, "OVER by N", consolidate/retire guidance).
  5. MEMORY.md, session_handoff.md, and section_*.md are excluded from the file
     count; the handoff pointer is excluded from the index-entry count.
  6. Index entries are summed from section files; a stray ToC note row folds in.
  7. Missing memory dir / missing MEMORY.md -> exit 2 (cannot evaluate).
  8. The budget lives in ONE place: the four module constants drive the caps.
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import memory_budget  # noqa: E402
from memory_budget import (  # noqa: E402
    MAX_INDEX_ENTRIES,
    MAX_MEMORY_BYTES,
    MAX_MEMORY_FILES,
    MAX_TOC_SECTIONS,
    SOFT_FILE_BYTES,
    STALE_DAYS,
    count_index_entries,
    count_memory_files,
    count_toc_sections,
    evaluate,
    format_staleness_report,
    gather_file_signals,
    gather_metrics,
    main,
)


def _build_corpus(
    root: Path,
    *,
    entries: int,
    files: int,
    sections: int = 1,
    extra_md_bytes: int = 0,
    include_handoff: bool = False,
    stray_toc_notes: int = 0,
) -> Path:
    """Create a two-tier .claude/memory corpus with the requested shape (#1016).

    `entries` note pointer rows are spread across `sections` TIER-2 section_*.md
    files; MEMORY.md is written as a compact ToC linking each section file. `files`
    topic (note detail) *.md files are created beside them. `extra_md_bytes` pads
    the ToC (MEMORY.md) to exercise the always-loaded byte cap. `include_handoff`
    adds the gitignored session_handoff.md + its ToC pointer (must NOT count).
    `stray_toc_notes` leaves N un-folded note one-liners in the ToC (the re-tier
    degraded case — they DO count toward the index total).
    """
    memory_dir = root / ".claude" / "memory"
    memory_dir.mkdir(parents=True)

    toc = ["# Memory Index (two-tier)", "", "| Section | Notes | Detail |", "|---|---|---|"]
    base, rem = divmod(entries, sections) if sections > 0 else (0, 0)
    counts = [base + (1 if i < rem else 0) for i in range(sections)]
    entry_no = 0
    for si, cnt in enumerate(counts):
        rows = []
        for _ in range(cnt):
            rows.append(f"- [Entry {entry_no}](topic_{entry_no}.md) — hook line {entry_no}.")
            entry_no += 1
        sec_body = f"# Section {si}\n\n" + ("\n".join(rows) + "\n" if rows else "")
        (memory_dir / f"section_{si}.md").write_text(sec_body, encoding="utf-8")
        toc.append(f"| Section {si} | {cnt} | [section_{si}.md](section_{si}.md) |")
    toc.append("")
    for k in range(stray_toc_notes):
        toc.append(f"- [Stray {k}](stray_{k}.md) — not yet folded.")
    if include_handoff:
        toc.append("- [Session handoff](session_handoff.md) — machine-local.")
    body = "\n".join(toc) + "\n"
    if extra_md_bytes > 0:
        body += "x" * extra_md_bytes
    (memory_dir / "MEMORY.md").write_text(body, encoding="utf-8")

    for i in range(files):
        (memory_dir / f"topic_{i}.md").write_text(f"topic {i}\n", encoding="utf-8")
    if include_handoff:
        (memory_dir / "session_handoff.md").write_text("handoff\n", encoding="utf-8")
    return memory_dir


class CountingTests(unittest.TestCase):
    def test_index_entries_summed_from_section_files_only_list_rows(self) -> None:
        # Index entries come from TIER-2 section_*.md files; only top-level
        # `- [...]` rows count. The ToC's session_handoff pointer is infra, excluded.
        with TemporaryDirectory() as d:
            memory_dir = Path(d) / ".claude" / "memory"
            memory_dir.mkdir(parents=True)
            (memory_dir / "MEMORY.md").write_text(
                "# ToC\n"
                "| S | 2 | [section_a.md](section_a.md) |\n"
                "\n"
                "- [Session handoff](session_handoff.md) — infra, NOT counted.\n",
                encoding="utf-8",
            )
            (memory_dir / "section_a.md").write_text(
                "# heading (not an entry)\n"
                "- [A](a.md) — x\n"
                "- [B](b.md) — y\n"
                "  - nested (not top-level)\n"
                "plain line\n",
                encoding="utf-8",
            )
            self.assertEqual(count_index_entries(memory_dir), 2)

    def test_stray_toc_note_row_folds_into_index_count(self) -> None:
        # A note one-liner the auto-writer left in the ToC (outside a section)
        # still counts toward the index total (re-tier degraded case) — but the
        # handoff pointer never does.
        with TemporaryDirectory() as d:
            memory_dir = _build_corpus(
                Path(d), entries=3, files=3, stray_toc_notes=2, include_handoff=True
            )
            # 3 in the section file + 2 stray in the ToC; handoff excluded.
            self.assertEqual(count_index_entries(memory_dir), 5)

    def test_handoff_pointer_not_counted_as_index_entry(self) -> None:
        with TemporaryDirectory() as d:
            memory_dir = _build_corpus(Path(d), entries=4, files=4, include_handoff=True)
            self.assertEqual(count_index_entries(memory_dir), 4)

    def test_file_count_excludes_toc_handoff_and_section_files(self) -> None:
        with TemporaryDirectory() as d:
            memory_dir = _build_corpus(
                Path(d), entries=6, files=3, sections=2, include_handoff=True
            )
            # 3 topic files; MEMORY.md, session_handoff.md, section_0/1.md must NOT count.
            self.assertEqual(count_memory_files(memory_dir), 3)

    def test_count_toc_sections_counts_section_rows(self) -> None:
        with TemporaryDirectory() as d:
            memory_dir = _build_corpus(Path(d), entries=10, files=10, sections=3)
            self.assertEqual(count_toc_sections(memory_dir / "MEMORY.md"), 3)


class UnderAndAtBudgetTests(unittest.TestCase):
    def test_well_under_budget_exits_zero(self) -> None:
        with TemporaryDirectory() as d:
            memory_dir = _build_corpus(Path(d), entries=10, files=10)
            self.assertEqual(evaluate(memory_dir), 0)

    def test_exactly_at_caps_is_allowed(self) -> None:
        # At-limit on entries AND files simultaneously; size left well under.
        with TemporaryDirectory() as d:
            memory_dir = _build_corpus(Path(d), entries=MAX_INDEX_ENTRIES, files=MAX_MEMORY_FILES)
            metrics = gather_metrics(memory_dir)
            by_label = {m.label: m for m in metrics}
            self.assertEqual(by_label["index entries"].current, MAX_INDEX_ENTRIES)
            self.assertFalse(by_label["index entries"].over)
            self.assertFalse(by_label["memory files"].over)
            self.assertEqual(evaluate(memory_dir), 0)


class OverBudgetTests(unittest.TestCase):
    def test_one_over_entries_blocks(self) -> None:
        with TemporaryDirectory() as d:
            # Push files down so ONLY the entry dimension is over.
            memory_dir = _build_corpus(Path(d), entries=MAX_INDEX_ENTRIES + 1, files=5)
            self.assertEqual(evaluate(memory_dir), 1)

    def test_one_over_files_blocks(self) -> None:
        with TemporaryDirectory() as d:
            # Keep entries low so ONLY the file dimension is over.
            memory_dir = _build_corpus(Path(d), entries=5, files=MAX_MEMORY_FILES + 1)
            self.assertEqual(evaluate(memory_dir), 1)

    def test_one_over_bytes_blocks(self) -> None:
        with TemporaryDirectory() as d:
            # Few entries/files/sections, but pad MEMORY.md (the ToC) past the byte cap.
            memory_dir = _build_corpus(
                Path(d), entries=3, files=3, extra_md_bytes=MAX_MEMORY_BYTES + 1
            )
            metrics = gather_metrics(memory_dir)
            size = next(m for m in metrics if m.label == "MEMORY.md size")
            self.assertTrue(size.over)
            self.assertEqual(evaluate(memory_dir), 1)

    def test_one_over_toc_sections_blocks(self) -> None:
        with TemporaryDirectory() as d:
            # Keep entries/files low so ONLY the ToC-section dimension is over.
            memory_dir = _build_corpus(Path(d), entries=5, files=5, sections=MAX_TOC_SECTIONS + 1)
            metrics = gather_metrics(memory_dir)
            toc = next(m for m in metrics if m.label == "ToC sections")
            self.assertTrue(toc.over)
            self.assertFalse(next(m for m in metrics if m.label == "index entries").over)
            self.assertEqual(evaluate(memory_dir), 1)

    def test_over_budget_diagnostic_is_actionable(self) -> None:
        with TemporaryDirectory() as d:
            memory_dir = _build_corpus(Path(d), entries=MAX_INDEX_ENTRIES + 3, files=5)
            metrics = gather_metrics(memory_dir)
            msg = memory_budget.over_budget_message(metrics)
            self.assertIn("MEMORY BUDGET EXCEEDED", msg)
            self.assertIn("index entries", msg)
            self.assertIn("OVER by 3", msg)
            self.assertIn(str(MAX_INDEX_ENTRIES), msg)
            # Must tell the human the fix is consolidate/retire, not auto-fixable.
            self.assertIn("cannot be auto-fixed", msg)
            self.assertIn("CONSOLIDATE", msg)
            self.assertIn("RETIRE", msg)


class CliAndErrorTests(unittest.TestCase):
    def test_main_repo_root_arg_resolves_corpus(self) -> None:
        with TemporaryDirectory() as d:
            _build_corpus(Path(d), entries=4, files=4)
            self.assertEqual(main(["memory_budget.py", d]), 0)

    def test_main_memory_dir_override(self) -> None:
        with TemporaryDirectory() as d:
            memory_dir = _build_corpus(Path(d), entries=4, files=4)
            self.assertEqual(main(["memory_budget.py", "--memory-dir", str(memory_dir)]), 0)

    def test_missing_memory_dir_exits_two(self) -> None:
        with TemporaryDirectory() as d:
            # No .claude/memory created.
            self.assertEqual(main(["memory_budget.py", d]), 2)

    def test_missing_memory_md_exits_two(self) -> None:
        with TemporaryDirectory() as d:
            memory_dir = Path(d) / ".claude" / "memory"
            memory_dir.mkdir(parents=True)
            (memory_dir / "topic_0.md").write_text("x\n", encoding="utf-8")
            self.assertEqual(main(["memory_budget.py", d]), 2)


class RealCorpusWithinBudgetTests(unittest.TestCase):
    """The check must PASS on the very corpus that ships it — i.e. the caps sit
    above the current consolidated size with headroom (else the gate red-blocks
    the PR adding it)."""

    def test_parent_memory_corpus_is_within_budget(self) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        memory_dir = repo_root / ".claude" / "memory"
        if not (memory_dir / "MEMORY.md").is_file():
            self.skipTest("parent memory corpus not present in this checkout")
        self.assertEqual(evaluate(memory_dir), 0)


class StalenessAdvisoryTests(unittest.TestCase):
    """The advisory --staleness sweep (#995): per-file size + recency signal.

    It is NON-BLOCKING (always exits 0) and must NEVER change the hard gate. The
    git recency helper is monkeypatched so tests don't depend on a git checkout.
    """

    NOW = datetime(2026, 7, 19, tzinfo=timezone.utc)

    def _make_memory_dir(self, root: Path) -> Path:
        memory_dir = root / ".claude" / "memory"
        memory_dir.mkdir(parents=True)
        (memory_dir / "MEMORY.md").write_text("- [A](a.md) — x\n", encoding="utf-8")
        return memory_dir

    def _patch_recency(self, mapping: dict[str, datetime | None]) -> None:
        """Force _git_last_commit to return a per-file datetime from `mapping`."""

        def fake(path: Path, repo_root: Path) -> datetime | None:
            return mapping.get(path.name)

        self._orig = memory_budget._git_last_commit
        memory_budget._git_last_commit = fake  # type: ignore[assignment]
        self.addCleanup(lambda: setattr(memory_budget, "_git_last_commit", self._orig))

    def test_oversized_file_flagged_size_stale_not(self) -> None:
        with TemporaryDirectory() as d:
            memory_dir = self._make_memory_dir(Path(d))
            (memory_dir / "big.md").write_text("x" * (SOFT_FILE_BYTES + 1), encoding="utf-8")
            (memory_dir / "small.md").write_text("x" * 100, encoding="utf-8")
            self._patch_recency({"big.md": self.NOW, "small.md": self.NOW})
            signals = {s.name: s for s in gather_file_signals(memory_dir, now=self.NOW)}
            self.assertTrue(signals["big.md"].oversized)
            self.assertFalse(signals["big.md"].stale)
            self.assertTrue(signals["big.md"].flagged)
            self.assertFalse(signals["small.md"].flagged)

    def test_stale_file_flagged_by_age(self) -> None:
        with TemporaryDirectory() as d:
            memory_dir = self._make_memory_dir(Path(d))
            (memory_dir / "old.md").write_text("x" * 50, encoding="utf-8")
            old = self.NOW - timedelta(days=STALE_DAYS + 5)
            self._patch_recency({"old.md": old})
            signal = gather_file_signals(memory_dir, now=self.NOW)[0]
            self.assertEqual(signal.name, "old.md")
            self.assertFalse(signal.oversized)
            self.assertTrue(signal.stale)
            self.assertEqual(signal.days_stale, STALE_DAYS + 5)

    def test_recency_unavailable_is_not_stale(self) -> None:
        # git returns None (fresh clone / no history) -> days_stale None, never
        # flagged as stale on a missing signal.
        with TemporaryDirectory() as d:
            memory_dir = self._make_memory_dir(Path(d))
            (memory_dir / "x.md").write_text("x" * 50, encoding="utf-8")
            self._patch_recency({"x.md": None})
            signal = gather_file_signals(memory_dir, now=self.NOW)[0]
            self.assertIsNone(signal.days_stale)
            self.assertFalse(signal.stale)

    def test_signals_sorted_largest_first(self) -> None:
        with TemporaryDirectory() as d:
            memory_dir = self._make_memory_dir(Path(d))
            (memory_dir / "mid.md").write_text("x" * 300, encoding="utf-8")
            (memory_dir / "big.md").write_text("x" * 900, encoding="utf-8")
            (memory_dir / "tiny.md").write_text("x" * 10, encoding="utf-8")
            self._patch_recency({"mid.md": self.NOW, "big.md": self.NOW, "tiny.md": self.NOW})
            names = [s.name for s in gather_file_signals(memory_dir, now=self.NOW)]
            self.assertEqual(names, ["big.md", "mid.md", "tiny.md"])

    def test_non_topic_files_excluded_from_signals(self) -> None:
        with TemporaryDirectory() as d:
            memory_dir = self._make_memory_dir(Path(d))
            (memory_dir / "session_handoff.md").write_text("h\n", encoding="utf-8")
            (memory_dir / "section_x.md").write_text("- [A](a.md) — x\n", encoding="utf-8")
            (memory_dir / "topic.md").write_text("t\n", encoding="utf-8")
            self._patch_recency({"topic.md": self.NOW})
            names = {s.name for s in gather_file_signals(memory_dir, now=self.NOW)}
            # MEMORY.md + handoff + section_*.md (index infra) all excluded.
            self.assertEqual(names, {"topic.md"})

    def test_cli_staleness_is_non_blocking_even_when_flagged(self) -> None:
        # A flagged (oversized) file must NOT make the advisory exit non-zero —
        # the hard gate blocks, the advisory only surfaces.
        with TemporaryDirectory() as d:
            memory_dir = self._make_memory_dir(Path(d))
            (memory_dir / "big.md").write_text("x" * (SOFT_FILE_BYTES + 1), encoding="utf-8")
            self.assertEqual(main(["memory_budget.py", d, "--staleness"]), 0)

    def test_report_reports_nothing_to_sweep_when_clean(self) -> None:
        with TemporaryDirectory() as d:
            memory_dir = self._make_memory_dir(Path(d))
            (memory_dir / "ok.md").write_text("x" * 50, encoding="utf-8")
            self._patch_recency({"ok.md": self.NOW})
            report = format_staleness_report(gather_file_signals(memory_dir, now=self.NOW))
            self.assertIn("Nothing to sweep", report)

    def test_soft_ceiling_is_independent_of_toc_byte_cap(self) -> None:
        # Post-#1016 MAX_MEMORY_BYTES caps only the tiny always-loaded ToC, so it
        # is the WRONG anchor for a per-note-file ceiling. SOFT_FILE_BYTES is now an
        # independent constant at its long-standing value (14 KiB), decoupled.
        self.assertEqual(SOFT_FILE_BYTES, 14_336)
        self.assertNotEqual(SOFT_FILE_BYTES, MAX_MEMORY_BYTES // 2)


if __name__ == "__main__":
    unittest.main()
