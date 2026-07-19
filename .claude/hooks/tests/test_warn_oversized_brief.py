#!/usr/bin/env python3
"""Unit tests for warn_oversized_brief.py — issue #1020.

The hook is an ADVISORY (never-blocking) lean-brief guard. Coverage:
  - a brief that pastes a whole context file's substantial lines → advisory,
    naming the file, never a block
  - a brief that extracts only a small section stays under threshold → no-op
  - short shared lines never accumulate a false positive (the _MIN_LINE_LEN
    substantial-line filter bites)
  - a charter SUB-document (charter/<subdir>/*.md) is covered too — noorina's
    charter is a directory tree, so the source glob must recurse
  - non-Agent tools and empty prompts are no-ops
  - the source set is resolved from CLAUDE_PROJECT_DIR, so tests are hermetic

The overlap threshold and the substantial-line floor are pinned directly, so a
future loosening (dropping the floor, or lowering the char threshold to zero)
reddens a test rather than silently changing the advisory's bite.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "warn_oversized_brief.py"
spec = importlib.util.spec_from_file_location("warn_oversized_brief", HOOK)
assert spec is not None and spec.loader is not None
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def _long_lines(n: int, width: int = 80) -> str:
    """n distinct lines, each `width` chars (>= _MIN_LINE_LEN)."""
    return "\n".join(f"line {i:03d} " + "x" * (width - 10) for i in range(n))


def _seed_charter(root: Path, name: str, body: str) -> Path:
    """Seed a top-level charter sub-document (charter/<name>)."""
    charter_dir = root / ".claude" / "team" / "charter"
    charter_dir.mkdir(parents=True, exist_ok=True)
    path = charter_dir / name
    path.write_text(body, encoding="utf-8")
    return path


def _seed_charter_subdir(root: Path, rel: str, body: str) -> Path:
    """Seed a nested charter sub-document (charter/<subdir>/<name>)."""
    path = root / ".claude" / "team" / "charter" / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _agent(prompt: str) -> dict:
    return {"tool_name": "Agent", "tool_input": {"prompt": prompt}}


# ---------------------------------------------------------------------------
# Fires: a whole-file paste
# ---------------------------------------------------------------------------


def test_whole_file_paste_returns_advisory(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    body = _long_lines(60)  # ~60*80 chars of substantial lines, well over 2000
    _seed_charter(tmp_path, "agents.md", body)

    result = mod.check(_agent(f"Here is the whole charter:\n{body}\nGo review."))
    assert result is not None
    assert result.get("decision") != "block"  # advisory only
    msg = result["systemMessage"]
    assert "agents.md" in msg
    assert "#1020" in msg


def test_claude_md_paste_is_detected(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    body = _long_lines(60)
    (tmp_path / "CLAUDE.md").write_text(body, encoding="utf-8")

    result = mod.check(_agent(body))
    assert result is not None
    assert "CLAUDE.md" in result["systemMessage"]


def test_top_level_charter_md_is_detected(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    body = _long_lines(60)
    charter = tmp_path / ".claude" / "team" / "charter.md"
    charter.parent.mkdir(parents=True, exist_ok=True)
    charter.write_text(body, encoding="utf-8")

    result = mod.check(_agent(body))
    assert result is not None
    assert result["systemMessage"].count("charter.md")


def test_charter_subdir_document_is_detected(tmp_path, monkeypatch):
    """A paste of a nested split charter file must be caught — the glob recurses."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    body = _long_lines(60)
    _seed_charter_subdir(tmp_path, "pull-requests/reviews.md", body)

    result = mod.check(_agent(f"Review per this:\n{body}"))
    assert result is not None
    assert "pull-requests/reviews.md" in result["systemMessage"]


# ---------------------------------------------------------------------------
# No-ops: lean extract, short lines, wrong tool, empty
# ---------------------------------------------------------------------------


def test_small_section_extract_is_noop(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    body = _long_lines(60)
    _seed_charter(tmp_path, "agents.md", body)

    # Paste only the first few lines — a lean section-extract, under threshold.
    excerpt = "\n".join(body.splitlines()[:5])
    assert mod.check(_agent(f"Relevant section:\n{excerpt}")) is None


def test_short_lines_do_not_accumulate(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    # Many SHORT lines (< _MIN_LINE_LEN) — even pasted whole, none count.
    short_body = "\n".join(f"item {i}" for i in range(400))
    _seed_charter(tmp_path, "agents.md", short_body)

    assert mod.check(_agent(short_body)) is None


def test_non_agent_tool_is_noop(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    body = _long_lines(60)
    _seed_charter(tmp_path, "agents.md", body)
    assert mod.check({"tool_name": "Bash", "tool_input": {"command": body}}) is None


def test_empty_prompt_is_noop(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    _seed_charter(tmp_path, "agents.md", _long_lines(60))
    assert mod.check(_agent("")) is None


# ---------------------------------------------------------------------------
# Threshold / floor bite
# ---------------------------------------------------------------------------


def test_overlap_threshold_is_the_bite(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    body = _long_lines(60)
    _seed_charter(tmp_path, "agents.md", body)
    lines = body.splitlines()

    # Accumulate whole lines until just under, then just over, the char cap.
    acc, under = 0, []
    for ln in lines:
        if acc + len(ln) >= mod._OVERLAP_WARN_CHARS:
            break
        under.append(ln)
        acc += len(ln)
    assert mod.check(_agent("\n".join(under))) is None, "under-threshold must not fire"

    over = under + [lines[len(under)], lines[len(under) + 1]]
    assert mod.check(_agent("\n".join(over))) is not None, "over-threshold must fire"
