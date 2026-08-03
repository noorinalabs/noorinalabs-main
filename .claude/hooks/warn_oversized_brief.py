#!/usr/bin/env python3
"""PreToolUse hook: advisory when an Agent brief pastes a whole charter/CLAUDE.md file.

Background (issue #1020, the lean-brief tooling program)
========================================================

The single largest per-token waste is the orchestrator pasting large verbatim
context — full ``CLAUDE.md``, whole charter sub-documents — into every subagent
brief, re-paying on every Opus/Sonnet spawn for context the role will never use.
The standing rule (charter ``agents/spawn-discipline.md``, and the
Session-Hygiene Playbook at ``agents/session-hygiene.md``) is: quote only the
*section* a task needs, then point the agent at the file+anchor for the rest.

This hook is the advisory backstop for that rule. On an ``Agent`` spawn it
measures how much of the brief is a *verbatim* run of a tracked context file
(``CLAUDE.md`` at the project root, ``.claude/team/charter.md``, and every
``.claude/team/charter/**/*.md`` sub-document). When a single source file's
substantial lines reproduce in the brief past a generous threshold, it surfaces
a MODEL-VISIBLE advisory nudging toward a section-extract + pointer.

Why advisory-only (never blocks)
================================

An over-long brief is a **cost smell, not a correctness fault** — a spawn that
carries too much context still works. Blocking would risk stalling a wave over a
heuristic. So this hook fails OPEN in every direction: a non-Agent call, a small
brief, an unreadable source file, or any internal error all exit 0 with no
message. It can only ever ADD a ``systemMessage``; it never returns ``block``.

Detection (a heuristic, deliberately conservative)
==================================================
  * Only *substantial* source lines count (``>= _MIN_LINE_LEN`` chars after
    whitespace-normalisation), so short shared boilerplate (fences, ``---``,
    one-word headings) never accumulates a false positive.
  * A source file trips the advisory only when its matched substantial lines sum
    to ``>= _OVERLAP_WARN_CHARS`` characters — a single extracted section stays
    under; a whole-file (or multi-section) paste blows past.

Exit codes:
  0 — always (advisory; never blocks)
"""

from __future__ import annotations

import os
from pathlib import Path

from _hook_main import run_advisory

# A source line must be at least this long (post-normalisation) to count toward
# the overlap, so common short lines (```bash, ---, `## PR Template`) never
# accumulate a false positive.
_MIN_LINE_LEN = 40

# A single source file trips the advisory when its matched substantial lines sum
# to at least this many characters. Generous on purpose: a lean section-extract
# stays well under; pasting a whole charter file / CLAUDE.md sails past.
_OVERLAP_WARN_CHARS = 2000

# Cap how much of the brief we scan, so a pathological input can't make the hook
# slow. Well above any sane brief size.
_MAX_SCAN_CHARS = 400_000


def _project_root() -> Path:
    """Repo root: ``$CLAUDE_PROJECT_DIR`` if set, else two levels up from here
    (``.claude/hooks/`` → repo root)."""
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2]


def _source_files(root: Path) -> list[Path]:
    """The tracked context files a brief should point at rather than paste.

    Noorina's charter is BOTH a single top-level ``charter.md`` AND a directory
    tree of per-concern sub-documents (``charter/agents/*.md``,
    ``charter/pull-requests/*.md``, …), so the sub-document glob is recursive —
    a paste of any one split file (e.g. ``charter/pull-requests/reviews.md``) is
    caught, not only the top-level files.
    """
    files: list[Path] = []
    claude_md = root / "CLAUDE.md"
    if claude_md.is_file():
        files.append(claude_md)
    charter = root / ".claude" / "team" / "charter.md"
    if charter.is_file():
        files.append(charter)
    charter_dir = root / ".claude" / "team" / "charter"
    if charter_dir.is_dir():
        files.extend(sorted(charter_dir.rglob("*.md")))
    return files


def _norm(line: str) -> str:
    """Collapse internal whitespace and strip, so trivial reflow does not defeat
    the verbatim match."""
    return " ".join(line.split())


def _overlap_chars(brief_norm: str, source_text: str) -> int:
    """Sum of the lengths of ``source_text``'s substantial lines that appear
    verbatim (whitespace-normalised) inside ``brief_norm``."""
    total = 0
    seen: set[str] = set()
    for raw in source_text.splitlines():
        norm = _norm(raw)
        if len(norm) < _MIN_LINE_LEN or norm in seen:
            continue
        seen.add(norm)
        if norm in brief_norm:
            total += len(norm)
    return total


def _find_oversized_source(prompt: str) -> tuple[str, int] | None:
    """Return ``(filename, matched_chars)`` for the first source file whose
    verbatim overlap with the brief crosses the threshold, else None."""
    brief_norm = _norm(prompt[:_MAX_SCAN_CHARS])
    root = _project_root()
    for path in _source_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        overlap = _overlap_chars(brief_norm, text)
        if overlap >= _OVERLAP_WARN_CHARS:
            try:
                rel = path.relative_to(root).as_posix()
            except ValueError:
                rel = path.name
            return rel, overlap
    return None


def _build_message(rel: str, overlap: int) -> str:
    return (
        "LEAN-BRIEF ADVISORY (#1020): this Agent brief reproduces a large verbatim "
        f"run (~{overlap} chars) of a tracked context file:\n    {rel}\n\n"
        "Pasting a whole charter/CLAUDE.md file into a brief re-pays for context "
        "the role will not use — the single largest per-token waste across a wave. "
        "Prefer a section-extract + pointer:\n"
        "  - Quote only the SECTION the task needs, then cite the file+anchor for "
        "the rest (the agent can Read it on demand).\n"
        "  - The PR charter is pre-split for this: point a reviewer at "
        "charter/pull-requests/reviews.md, a merger at charter/pull-requests/wave-merge.md, "
        "an author at charter/pull-requests/authoring.md — not the whole PR charter.\n"
        "  - Identity/branching/commit rules live in the roster file "
        "(.claude/team/roster/<member>.md) + charter; point at them, do not re-transcribe.\n"
        "  - For a CODE subtree, pack a signatures-only skeleton instead of pasting "
        "whole files: `make skeleton DIR=<subtree> INCLUDE='<glob>'`.\n"
        "See charter/agents/session-hygiene.md § Lean Section-Extract Briefs (#1020). "
        "Advisory only — your spawn is not blocked."
    )


def check(input_data: dict) -> dict | None:
    """Return a non-blocking ``systemMessage`` advisory when an Agent brief pastes
    a whole context file, else None. Never returns a ``block`` decision.

    (Also usable by a dispatcher, though this hook is registered standalone in
    settings.json's ``Agent`` matcher — noorina has no Agent dispatcher.)"""
    if input_data.get("tool_name", "") != "Agent":
        return None
    prompt = input_data.get("tool_input", {}).get("prompt", "")
    if not prompt:
        return None
    hit = _find_oversized_source(prompt)
    if hit is None:
        return None
    rel, overlap = hit
    return {"systemMessage": _build_message(rel, overlap)}


def main() -> None:
    run_advisory(check, "warn_oversized_brief")


if __name__ == "__main__":
    main()
