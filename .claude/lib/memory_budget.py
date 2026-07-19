#!/usr/bin/env python3
"""Enforce a size/count budget on the project-memory corpus (#733, P6 W1).

Second deliverable of P6 criterion #1 (memory leanness, epic #725): the
*enforcement* half. After the corpus was consolidated (sibling audit issue),
this check keeps it lean going forward — it caps how large the version-controlled
memory corpus (``.claude/memory/MEMORY.md`` + the topic files beside it) may grow
so that growth is a deliberate, surfaced decision rather than silent drift.

Per the enforcement hierarchy (``feedback_enforcement_hierarchy.md`` — hook >
skill > charter > memory), a budget expressed only as prose decays; it has to be
machine-enforced. This module is that machine: a CLI that exits non-zero when the
corpus is over budget, mirrored into ``.pre-commit-config.yaml`` and wired as a
CI job (``Memory budget gate``) so local and CI agree (the full local⇄CI parity
rule, ``feedback_local_ci_parity_no_force.md`` / #684).

Two-tier memory index (#1016)
=============================
``MEMORY.md`` is no longer the flat, always-loaded list of every note. It is a
compact **table of contents** (TIER 1, the only always-injected file via
CLAUDE.md's ``@.claude/memory/MEMORY.md`` import): a small table whose rows point
at ``section_<slug>.md`` **section files** (TIER 2). Each section file carries the
per-note ``- [Title](slug.md) — …`` one-liners and is read ON DEMAND, never
auto-injected. The note *detail* files (``feedback_*.md`` etc.) are unchanged.

The section files are **index infrastructure, not notes**: they are excluded
from the note-file count and from the always-loaded byte cap, and the ToC's own
size is capped by a new section-row dimension.

Four dimensions, one threshold each (single source of truth)
============================================================
The budget is the four module constants below — the ONLY place a limit is
defined. Each is enforced independently; the corpus is over budget if ANY one is
exceeded.

- ``MAX_INDEX_ENTRIES`` — total recallable-note pointer rows (``^- \\[`` lines)
  summed across the TIER-2 ``section_*.md`` files (plus any stray note row the
  auto-writer left in ``MEMORY.md`` outside the ToC — the ``session_handoff.md``
  pointer, which is always-loaded infra not a note, is NOT counted). This is the
  primary dimension: it counts the recallable memories, wherever they were filed.
- ``MAX_MEMORY_FILES`` — topic ``*.md`` files in ``.claude/memory/`` excluding
  ``MEMORY.md``, the gitignored machine-local ``session_handoff.md``, and the
  ``section_*.md`` ToC infrastructure (see below). Roughly tracks the note count
  and catches an orphaned note file added without an index row.
- ``MAX_MEMORY_BYTES`` — byte size of ``MEMORY.md``, i.e. the always-loaded ToC.
  Now that the ToC is the *only* auto-injected memory file, this cap directly
  guards the per-turn always-loaded cost the #1016 split exists to shrink; it is
  tightened accordingly (a flat index would blow past it, forcing the split).
- ``MAX_TOC_SECTIONS`` — ToC section rows (lines linking a ``section_*.md``) in
  ``MEMORY.md``. A backstop against the ToC itself re-bloating by sprouting
  ever-more sections instead of the corpus being consolidated.

session_handoff.md, sections, and the counts
=============================================
``MEMORY.md`` carries a committed pointer line for ``session_handoff.md``, but
that file is gitignored (per-session machine-local churn — see ``.gitignore``)
and is absent in a CI checkout. It is excluded from BOTH the note-file count and
the index-entry count so the readings are identical on a developer machine
(where the handoff exists) and in CI (where it does not). The ``section_*.md``
files are likewise excluded from the note-file count (they are index infra).

Threshold calibration (headroom rationale — owner directive 2026-06-19 "tighten")
=================================================================================
Measured against the *post-consolidation* corpus at #733 time:
    index entries = 102,  topic files = 101,  MEMORY.md = 17,989 bytes (~17.6 KiB).

    MAX_INDEX_ENTRIES = 120  → ~18 entries / ~18% headroom over 102.
    MAX_MEMORY_FILES  = 120  → ~19 files   / ~19% headroom over 101.
    MAX_MEMORY_BYTES  = 24576 (24 KiB)  → ~37% headroom over 17,989 bytes; sits
        just under the ~24.4 KB ceiling a prior retro cited for MEMORY.md before
        the consolidation (it had bloated to ~38 KB). The byte cap is the loosest
        of the three on purpose — the entry/file caps bind first in the common
        growth pattern (adding memories); the byte cap only catches the rare
        case of fewer-but-bloated index lines.

Raise 2026-07-11 (owner decision, P8W24) — 120 → 132, 24 KiB → 28 KiB
=====================================================================
The gate fired at index = 121 / files = 120 / MEMORY.md = 24,912 bytes and the
owner took the option this module documents below: raise the cap deliberately
rather than retire a memory. The corpus had grown past the #733 baseline through
a single unusually dense week (the "an instrument that cannot see what it exists
to catch" defect class — ~20 distinct instances, several load-bearing).

    MAX_INDEX_ENTRIES = 132  → ~11 entries / ~9% headroom over 121.
    MAX_MEMORY_FILES  = 132  → ~12 files   / ~10% headroom over 120.
    MAX_MEMORY_BYTES  = 28672 (28 KiB)  → ~15% headroom over 24,912 bytes.

The headroom is deliberately *tighter* than the original calibration: this raise
is an acknowledgement that the corpus genuinely grew, NOT a decision to let it
grow freely. The next overflow should be met with a consolidation pass, not
another bump — a cap that is raised on every overflow is not a forcing function,
it is a formality.

Two-tier recalibration 2026-07-19 (#1016) — MEMORY.md byte cap + ToC-section cap
================================================================================
The flat index was split into a ToC (``MEMORY.md``) + ``section_*.md`` files.
The dimensions were re-anchored to the new shape (measured at split time:
index entries = 98,  topic files = 98,  ToC MEMORY.md = 2,502 bytes,  sections = 8):

    MAX_INDEX_ENTRIES = 132  → unchanged; still the recallable-note count, now
        summed across the section files rather than read from the flat index.
    MAX_MEMORY_FILES  = 132  → unchanged; the section files are excluded so the
        note-file count is unaffected by the split.
    MAX_MEMORY_BYTES  = 6144 (6 KiB)  → TIGHTENED from 28 KiB. It now measures the
        always-loaded ToC, not the whole index; ~2.5x headroom over 2,502 bytes.
        This is the cap that actively keeps the per-turn always-loaded cost small.
    MAX_TOC_SECTIONS  = 12  → NEW; ~4 rows / 50% headroom over the 8 sections.

The headroom is deliberately modest: enough that a normal wave's memory intake
does not trip the gate, but tight enough that it forces a consolidate/retire
decision before the corpus drifts back toward its pre-audit bloat. Raising a cap
is a one-line, reviewed change here — which is exactly the "deliberate, surfaced
decision" #725 wants, rather than silent growth.

Block, not advisory (``feedback_safety_direction_over_ux_friction.md``)
=======================================================================
A budget overflow CANNOT be auto-fixed — it needs a human consolidate/retire
judgment about which memories to merge or drop. So the right posture is a HARD
BLOCK with an actionable diagnostic (current vs. budget, by how much it is over,
and that the fix is to consolidate/retire in ``.claude/memory/``), never a silent
advisory that scrolls past. Exit 1 on overflow; the pre-commit/CI gate then stops
the push.

Exit codes (CLI):
    0 — corpus is within budget on all four dimensions.
    1 — over budget on at least one dimension (HARD BLOCK).
    2 — usage / corpus directory or MEMORY.md not found (cannot evaluate).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

# --- Budget: the single source of truth. Edit a number here and nowhere else. ---
MAX_INDEX_ENTRIES = 132
MAX_MEMORY_FILES = 132
MAX_MEMORY_BYTES = 6_144  # 6 KiB — the always-loaded ToC only (#1016)
MAX_TOC_SECTIONS = 12  # ToC section rows in MEMORY.md (#1016)

# --- Advisory staleness/size signal (#995, P9W25) — NOT a gate ---------------
# The three budgets above are a HARD gate on the corpus *in aggregate* (index
# count, file count, MEMORY.md bytes). They say nothing about an individual
# topic file being oversized or long-untouched — the 52KB narrator file is the
# poster child: uncapped and unflagged. The `--staleness` mode below is the
# advisory that surfaces those per-file signals for the /wave-retro decay sweep
# (Step 7.8). It ALWAYS exits 0 — a large or old memory is a candidate for a
# human consolidate/archive decision, never an auto-block and never an
# auto-delete (a rare-but-critical memory must survive age alone; mirrors
# /promotion-audit in reverse).
#
# SOFT_FILE_BYTES caps an individual TIER-2 note detail file. It used to be
# derived as half of MAX_MEMORY_BYTES, back when that cap measured the whole flat
# index (~28 KiB). Post-#1016 the byte cap measures only the tiny always-loaded
# ToC (6 KiB), which is the wrong anchor for a per-note-file ceiling — half of it
# (3 KiB) would flag almost every legitimate note. So this is now an independent
# constant, kept at its long-standing effective value: a note file over 14 KiB is
# worth a "still all pulling its weight?" look.
SOFT_FILE_BYTES = 14_336  # 14 KiB (independent of the ToC byte cap since #1016)
# STALE_DAYS: a topic file whose last *commit* is older than this is a decay
# candidate. Edit-recency is a pragmatic proxy — a memory can stay recall-
# relevant without being edited — which is exactly why this is advisory-only.
STALE_DAYS = 90

# Files under .claude/memory/ that are NOT counted as topic (note) files: the ToC
# itself, and the gitignored per-session handoff (absent in CI — see module
# docstring). Compared case-sensitively against the file name. The TIER-2
# section_*.md files are also excluded, via _is_section_file below.
_NON_TOPIC_FILES = frozenset({"MEMORY.md", "session_handoff.md"})

# An index entry is a top-level list row linking a memory: `- [Title](file.md) …`.
_INDEX_ENTRY_RE = re.compile(r"^- \[")

# A ToC section row links a TIER-2 section file: `… [section_x.md](section_x.md) …`.
_TOC_SECTION_RE = re.compile(r"\]\(section[_-][^)]*\.md\)")

# A `- [ …](session_handoff.md) …` pointer in the ToC — always-loaded infra, not a
# recallable note, so it is not counted among the index entries.
_HANDOFF_LINK_RE = re.compile(r"\]\(session_handoff\.md\)")


def _is_section_file(name: str) -> bool:
    """True for a TIER-2 ToC section file (index infra, not a note)."""
    return name.startswith("section_") or name.startswith("section-")


class Metric(NamedTuple):
    """One budgeted dimension and its current reading."""

    label: str  # human label, e.g. "index entries"
    current: int
    limit: int
    unit: str  # "" for counts, "bytes" for the size metric

    @property
    def over(self) -> bool:
        return self.current > self.limit

    @property
    def overage(self) -> int:
        return max(0, self.current - self.limit)


def _entry_rows(text: str, *, skip_handoff: bool = False) -> int:
    """Count `- [...]` recallable-note rows in a block of text.

    With ``skip_handoff`` the always-loaded ``session_handoff.md`` pointer (infra,
    not a note) is not counted — used for stray rows left in the ToC.
    """
    n = 0
    for line in text.splitlines():
        if not _INDEX_ENTRY_RE.match(line):
            continue
        if skip_handoff and _HANDOFF_LINK_RE.search(line):
            continue
        n += 1
    return n


def count_index_entries(memory_dir: Path) -> int:
    """Total recallable-note pointer rows across the two-tier index (#1016).

    The one-liners live in the TIER-2 ``section_*.md`` files; sum those. Also fold
    in any stray note row the auto-writer left in the ToC (``MEMORY.md``) outside
    the section table — the re-tier maintenance surfaces those — excluding the
    always-loaded ``session_handoff.md`` pointer, which is infra, not a note.
    """
    total = 0
    for p in sorted(memory_dir.glob("*.md")):
        if _is_section_file(p.name):
            total += _entry_rows(p.read_text(encoding="utf-8"))
    memory_md = memory_dir / "MEMORY.md"
    if memory_md.is_file():
        total += _entry_rows(memory_md.read_text(encoding="utf-8"), skip_handoff=True)
    return total


def count_memory_files(memory_dir: Path) -> int:
    """Count topic (note) `*.md` files, excluding the ToC, handoff, and section files."""
    return sum(
        1
        for p in memory_dir.glob("*.md")
        if p.name not in _NON_TOPIC_FILES and not _is_section_file(p.name)
    )


def count_toc_sections(memory_md: Path) -> int:
    """Count ToC rows that link a TIER-2 section file (#1016)."""
    text = memory_md.read_text(encoding="utf-8")
    return sum(1 for line in text.splitlines() if _TOC_SECTION_RE.search(line))


def memory_md_bytes(memory_md: Path) -> int:
    """Byte size of MEMORY.md (the always-loaded ToC) on disk."""
    return memory_md.stat().st_size


def gather_metrics(memory_dir: Path) -> list[Metric]:
    """Read the corpus and return the three budgeted metrics.

    Raises FileNotFoundError if the memory dir or MEMORY.md is absent — the
    caller turns that into exit 2 (cannot evaluate), never a silent pass.
    """
    if not memory_dir.is_dir():
        raise FileNotFoundError(f"memory directory not found: {memory_dir}")
    memory_md = memory_dir / "MEMORY.md"
    if not memory_md.is_file():
        raise FileNotFoundError(f"MEMORY.md not found: {memory_md}")
    return [
        Metric("index entries", count_index_entries(memory_dir), MAX_INDEX_ENTRIES, ""),
        Metric("memory files", count_memory_files(memory_dir), MAX_MEMORY_FILES, ""),
        Metric("ToC sections", count_toc_sections(memory_md), MAX_TOC_SECTIONS, ""),
        Metric("MEMORY.md size", memory_md_bytes(memory_md), MAX_MEMORY_BYTES, "bytes"),
    ]


def _fmt(metric: Metric) -> str:
    unit = f" {metric.unit}" if metric.unit else ""
    status = f"OVER by {metric.overage}{unit}" if metric.over else "ok"
    return f"  {metric.label:<14}: {metric.current} / {metric.limit}{unit}  ({status})"


def format_report(metrics: list[Metric]) -> str:
    """Render the metric table; identical shape whether over or under budget."""
    return "\n".join(_fmt(m) for m in metrics)


def over_budget_message(metrics: list[Metric]) -> str:
    """The HARD-BLOCK diagnostic printed when over budget."""
    over = [m for m in metrics if m.over]
    dims = ", ".join(m.label for m in over)
    return (
        "MEMORY BUDGET EXCEEDED — the project-memory corpus is over budget "
        f"on: {dims}.\n\n"
        f"{format_report(metrics)}\n\n"
        "A budget overflow cannot be auto-fixed: it needs a human "
        "consolidate/retire decision about which memories to merge or drop.\n"
        "To get back under budget, CONSOLIDATE related entries or RETIRE stale "
        "ones under .claude/memory/ (delete the file AND its line in MEMORY.md), "
        "then re-run.\n"
        "See CLAUDE.md § Project Memory and the /wave-retro memory curation step. "
        "If the corpus has genuinely outgrown the budget, raise the cap "
        "deliberately in .claude/lib/memory_budget.py (one reviewed line) — that "
        "is the surfaced decision this gate exists to force."
    )


def evaluate(memory_dir: Path) -> int:
    """Evaluate the corpus and print a report. Return the process exit code."""
    metrics = gather_metrics(memory_dir)
    if any(m.over for m in metrics):
        print(over_budget_message(metrics), file=sys.stderr)
        return 1
    print("OK: project-memory corpus is within budget.")
    print(format_report(metrics))
    return 0


# --- Advisory staleness/size report (#995) -----------------------------------


class FileSignal(NamedTuple):
    """Per-file size + recency reading for the advisory sweep."""

    name: str
    size_bytes: int
    last_commit: datetime | None  # None when git recency is unavailable
    days_stale: int | None  # None when last_commit is None

    @property
    def oversized(self) -> bool:
        return self.size_bytes > SOFT_FILE_BYTES

    @property
    def stale(self) -> bool:
        return self.days_stale is not None and self.days_stale > STALE_DAYS

    @property
    def flagged(self) -> bool:
        return self.oversized or self.stale


def _git_last_commit(path: Path, repo_root: Path) -> datetime | None:
    """Last-commit datetime (UTC) for `path` via git, or None on any failure.

    Kept behind a tiny helper so the report degrades gracefully outside a git
    checkout (fresh clone with no history for the file, git absent, non-repo)
    and so tests can monkeypatch it without invoking git.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_root), "log", "-1", "--format=%cI", "--", str(path)],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    stamp = out.stdout.strip()
    if out.returncode != 0 or not stamp:
        return None
    try:
        return datetime.fromisoformat(stamp).astimezone(timezone.utc)
    except ValueError:
        return None


def gather_file_signals(memory_dir: Path, now: datetime | None = None) -> list[FileSignal]:
    """Size + recency for every topic file, sorted largest-first.

    `now` is injectable for deterministic tests; defaults to the current UTC time.
    Recency is resolved relative to the repo root (parent of `.claude/memory`).
    """
    now = now or datetime.now(timezone.utc)
    # repo_root = <...>/.claude/memory → up two levels. Falls back to memory_dir
    # itself if the layout is unexpected; git will simply return None there.
    repo_root = memory_dir.parent.parent if memory_dir.parent.name == ".claude" else memory_dir
    signals: list[FileSignal] = []
    for p in sorted(memory_dir.glob("*.md")):
        if p.name in _NON_TOPIC_FILES or _is_section_file(p.name):
            continue
        last = _git_last_commit(p, repo_root)
        days = (now - last).days if last is not None else None
        signals.append(FileSignal(p.name, p.stat().st_size, last, days))
    signals.sort(key=lambda s: s.size_bytes, reverse=True)
    return signals


def format_staleness_report(signals: list[FileSignal]) -> str:
    """Render the advisory table: flagged files first, with size + age columns."""
    flagged = [s for s in signals if s.flagged]
    lines = [
        "MEMORY STALENESS/SIZE ADVISORY (non-blocking — /wave-retro decay sweep, #995)",
        f"  soft per-file ceiling: {SOFT_FILE_BYTES} bytes   stale after: {STALE_DAYS} days",
        f"  topic files: {len(signals)}   flagged: {len(flagged)} "
        f"(size and/or age — candidates for a human consolidate/archive decision)",
        "",
    ]
    if not flagged:
        lines.append("  No files over the size ceiling or staleness threshold. Nothing to sweep.")
        return "\n".join(lines)
    for s in flagged:
        marks = []
        if s.oversized:
            marks.append("SIZE")
        if s.stale:
            marks.append("STALE")
        age = f"{s.days_stale}d" if s.days_stale is not None else "age?"
        lines.append(f"  [{'+'.join(marks):<10}] {s.size_bytes:>6}B  last-touch {age:>6}  {s.name}")
    lines.append("")
    lines.append(
        "  These are ADVISORY: a large or long-untouched memory is a candidate for "
        "consolidation or a move to .claude/memory/archive/ (a cold tier outside "
        "the always-loaded index), NEVER an auto-delete. Age is edit-recency, not "
        "reference-recency — decide per file."
    )
    return "\n".join(lines)


def evaluate_staleness(memory_dir: Path) -> int:
    """Print the advisory report. Always returns 0 (non-blocking)."""
    if not memory_dir.is_dir():
        raise FileNotFoundError(f"memory directory not found: {memory_dir}")
    print(format_staleness_report(gather_file_signals(memory_dir)))
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "repo_root",
        nargs="?",
        default=".",
        help="Repo root to check (default: cwd). The corpus is <repo_root>/.claude/memory.",
    )
    parser.add_argument(
        "--memory-dir",
        help="Path to the memory dir directly (overrides <repo_root>/.claude/memory).",
    )
    parser.add_argument(
        "--staleness",
        action="store_true",
        help="Advisory only: print the per-file size/staleness sweep (always exits 0) "
        "instead of the hard budget gate. Used by the /wave-retro decay sweep (#995).",
    )
    args = parser.parse_args(argv[1:])

    memory_dir = (
        Path(args.memory_dir)
        if args.memory_dir
        else Path(args.repo_root).resolve() / ".claude" / "memory"
    )

    try:
        if args.staleness:
            return evaluate_staleness(memory_dir)
        return evaluate(memory_dir)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
