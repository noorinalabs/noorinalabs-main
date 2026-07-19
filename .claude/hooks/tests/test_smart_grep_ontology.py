#!/usr/bin/env python3
"""Unit tests for smart_grep_ontology.py — issue #1017 (ported from botfarm #886).

The hook blocks an `rg`/`grep` call searching for a bare-identifier (or dotted
`Class.method`) pattern the structural ontology (`code-graph.json`) already
indexes, and returns the definition site(s) + call sites inline instead of
letting the brute-force search run. Coverage:

  _find_grep_segment / _extract_pattern — locating the grep-family invocation
    and its search pattern past value-taking flags (`-A 3`, `-e PATTERN`),
    a wrapper prefix (`sudo grep`), and `rg`. `_find_grep_segment` returns the
    tail AFTER the binary (noorina has no `strip_command_prefix`; the tail feeds
    `_extract_pattern` directly).
  _has_escape_hatch — the `# --graph-tried` bypass is unquoted-token-position
    only; a quoted copy of the same text (search DATA, not a shell comment)
    never trips it.
  check() — blocks + answers for a known func/class/method (with call sites
    and a truncation note past `_MAX_MATCHES`); allows a non-Bash tool, a
    non-grep command, a free-text/regex pattern, an unknown symbol, a missing
    ontology graph, the escape hatch, and an `rg` mention hidden inside a
    heredoc body; flags a STALE source file.
  THE BITE — neutering `_lookup_symbol` (the actual graph query) turns the
    baseline block into an allow, proving the block is produced by the
    ontology lookup and not some other path.

Hermetic: the ontology is a small synthetic `code-graph.json`/`checksums.json`
written under `tmp_path` and resolved by monkeypatching `mod.REPO_ROOT`; nothing
reads the real repo's ontology and `log_pretooluse_block` is stubbed out.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parents[1]
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

import smart_grep_ontology as mod  # noqa: E402

_GRAPH = {
    "nodes": [
        {
            "id": "pkg/mod.py",
            "kind": "module",
            "path": "pkg/mod.py",
            "line": 1,
            "lang": "python",
        },
        {
            "id": "pkg/mod.py::foo_bar",
            "kind": "func",
            "path": "pkg/mod.py",
            "line": 10,
            "lang": "python",
        },
        {
            "id": "pkg/mod.py::Widget",
            "kind": "class",
            "path": "pkg/mod.py",
            "line": 20,
            "lang": "python",
        },
        {
            "id": "pkg/mod.py::Widget.get",
            "kind": "method",
            "path": "pkg/mod.py",
            "line": 25,
            "lang": "python",
        },
        {
            "id": "pkg/caller.py::do_thing",
            "kind": "func",
            "path": "pkg/caller.py",
            "line": 5,
            "lang": "python",
        },
    ],
    "edges": [
        {
            "src": "pkg/caller.py::do_thing",
            "dst": "pkg/mod.py::foo_bar",
            "type": "calls",
        },
    ],
}


def _write_ontology(root: Path) -> None:
    structural = root / "ontology" / "structural"
    structural.mkdir(parents=True)
    (structural / "code-graph.json").write_text(json.dumps(_GRAPH), encoding="utf-8")
    checksums = {
        "files": {
            "pkg/mod.py": {"last_tracked": "aaa", "last_resolved": "aaa"},
            "pkg/caller.py": {"last_tracked": "bbb", "last_resolved": "bbb"},
        }
    }
    (root / "ontology" / "checksums.json").write_text(json.dumps(checksums), encoding="utf-8")


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A repo root with a synthetic ontology. Returns a factory building
    `input_data` for a Bash command; `mod.REPO_ROOT` is pinned to `tmp_path`."""
    monkeypatch.setattr(mod, "log_pretooluse_block", lambda *a, **k: None)
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    _write_ontology(tmp_path)

    def _build(command: str) -> dict:
        return {
            "tool_name": "Bash",
            "cwd": str(tmp_path),
            "tool_input": {"command": command},
        }

    return _build


def _mark_dirty(tmp_path: Path) -> None:
    checksums = json.loads((tmp_path / "ontology" / "checksums.json").read_text())
    checksums["files"]["pkg/mod.py"]["last_tracked"] = "changed"
    (tmp_path / "ontology" / "checksums.json").write_text(json.dumps(checksums), encoding="utf-8")


def _tok(command: str) -> list[str]:
    """`tokenize`, asserting a parse (it is `list[str] | None`) for the callers
    below that pass the result straight into a `list[str]`-typed helper."""
    tokens = mod.tokenize(command)
    assert tokens is not None
    return tokens


# ---------------------------------------------------------------- _extract_pattern


def test_extract_pattern_plain() -> None:
    assert mod._extract_pattern(["-rn", "foo_bar", "."]) == "foo_bar"


def test_extract_pattern_skips_value_flag() -> None:
    """`-A 3` must not leave `3` mistaken for the pattern."""
    assert mod._extract_pattern(["-A", "3", "-rn", "foo_bar", "."]) == "foo_bar"


def test_extract_pattern_dash_e() -> None:
    assert mod._extract_pattern(["-rn", "-e", "foo_bar", "."]) == "foo_bar"


def test_extract_pattern_none_when_only_flags() -> None:
    assert mod._extract_pattern(["-rn", "-l"]) is None


# ---------------------------------------------------------------- _find_grep_segment
#
# Returns the tail AFTER the grep-family binary (noorina lacks
# strip_command_prefix — the binary is peeled by _grep_tail itself).


def test_find_grep_segment_plain() -> None:
    tokens = _tok("grep -rn foo_bar .")
    assert mod._find_grep_segment(tokens) == ["-rn", "foo_bar", "."]


def test_find_grep_segment_ripgrep() -> None:
    tokens = _tok('rg "foo_bar" .')
    assert mod._find_grep_segment(tokens) == ["foo_bar", "."]


def test_find_grep_segment_wrapper_prefix() -> None:
    tokens = _tok("sudo grep -rn foo_bar .")
    assert mod._find_grep_segment(tokens) == ["-rn", "foo_bar", "."]


def test_find_grep_segment_none_for_other_commands() -> None:
    tokens = _tok("ls -la .")
    assert mod._find_grep_segment(tokens) is None


# ---------------------------------------------------------------- _has_escape_hatch


def test_escape_hatch_present() -> None:
    tokens = _tok('rg "foo_bar" . # --graph-tried')
    assert mod._has_escape_hatch(tokens) is True


def test_escape_hatch_absent() -> None:
    tokens = _tok("rg foo_bar .")
    assert mod._has_escape_hatch(tokens) is False


def test_escape_hatch_not_tripped_by_quoted_data() -> None:
    """A quoted `--graph-tried` search pattern is DATA, not a shell comment — it
    collapses to one token under `tokenize()`, so it must never be read as the
    bypass marker (Rule 2: quote-awareness, no false-match on the search's data)."""
    tokens = _tok('rg "# --graph-tried" file.py')
    assert mod._has_escape_hatch(tokens) is False


# ---------------------------------------------------------------- check(): allowing


def test_allows_non_bash_tool(repo) -> None:
    data = repo("rg foo_bar .")
    data["tool_name"] = "Read"
    assert mod.check(data) is None


def test_allows_non_grep_command(repo) -> None:
    assert mod.check(repo("ls -la .")) is None


def test_allows_free_text_pattern(repo) -> None:
    """A pattern with spaces / regex metacharacters is not a symbol shape — the
    graph was never going to answer it, so it's never even looked up."""
    assert mod.check(repo('rg "does not exist yet" .')) is None


def test_allows_regex_pattern(repo) -> None:
    assert mod.check(repo('rg "foo.*bar" .')) is None


def test_allows_unknown_symbol(repo) -> None:
    assert mod.check(repo("rg totally_unknown_symbol_xyz .")) is None


def test_allows_when_escape_hatch_present(repo) -> None:
    """Same command as the blocking test below, plus the bypass marker."""
    assert mod.check(repo("rg foo_bar . # --graph-tried")) is None


def test_allows_grep_mentioned_inside_heredoc(repo) -> None:
    command = "cat <<'EOF' > note.txt\nrg foo_bar .\nEOF\n"
    assert mod.check(repo(command)) is None


def test_allows_when_ontology_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(mod, "log_pretooluse_block", lambda *a, **k: None)
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)  # no ontology written
    data = {
        "tool_name": "Bash",
        "cwd": str(tmp_path),
        "tool_input": {"command": "rg foo_bar ."},
    }
    assert mod.check(data) is None


# ---------------------------------------------------------------- check(): blocking


def test_blocks_and_answers_known_function(repo) -> None:
    result = mod.check(repo("rg foo_bar ."))
    assert result is not None
    assert result["decision"] == "block"
    assert "pkg/mod.py:10" in result["reason"]
    assert "called from: pkg/caller.py:5" in result["reason"]
    assert "--graph-tried" in result["reason"]


def test_blocks_bare_grep_symbol_too(repo) -> None:
    """A symbol-shaped `grep` is answered here BEFORE block_bare_grep sees it."""
    result = mod.check(repo("grep -rn foo_bar ."))
    assert result is not None and result["decision"] == "block"
    assert "pkg/mod.py:10" in result["reason"]


def test_bare_method_name_matches_dotted_qualname(repo) -> None:
    result = mod.check(repo("rg get ."))
    assert result is not None
    assert "pkg/mod.py::Widget.get" in result["reason"]
    assert "pkg/mod.py:25" in result["reason"]


def test_exact_qualname_pattern_matches_only_that(repo) -> None:
    result = mod.check(repo('rg -e "Widget.get" .'))
    assert result is not None
    assert "Widget.get" in result["reason"]
    assert "foo_bar" not in result["reason"]


def test_class_name_match(repo) -> None:
    result = mod.check(repo("rg Widget ."))
    assert result is not None
    assert "pkg/mod.py::Widget " in result["reason"] or "pkg/mod.py::Widget\n" in result["reason"]


def test_ripgrep_invocation_blocks_too(repo) -> None:
    result = mod.check(repo('rg "foo_bar" .'))
    assert result is not None and result["decision"] == "block"


def test_stale_source_is_flagged(repo, tmp_path) -> None:
    _mark_dirty(tmp_path)
    result = mod.check(repo("rg foo_bar ."))
    assert result is not None
    assert "STALE" in result["reason"]


def test_truncates_past_max_matches(repo, tmp_path) -> None:
    graph = json.loads((tmp_path / "ontology" / "structural" / "code-graph.json").read_text())
    for i in range(mod._MAX_MATCHES + 1):
        graph["nodes"].append(
            {
                "id": f"pkg/extra{i}.py::shared_name",
                "kind": "func",
                "path": f"pkg/extra{i}.py",
                "line": 1,
                "lang": "python",
            }
        )
    (tmp_path / "ontology" / "structural" / "code-graph.json").write_text(
        json.dumps(graph), encoding="utf-8"
    )
    result = mod.check(repo("rg shared_name ."))
    assert result is not None
    assert "more match(es)" in result["reason"]


# ---------------------------------------------------------------- THE BITE


def test_the_guard_bites(repo, monkeypatch) -> None:
    """Mutation proof: with the graph query neutered, the same command that
    blocked at baseline now allows — the block is produced BY the ontology
    lookup, not incidentally by some other path (memory: gate-must-be-shown-to-bite)."""
    live = mod.check(repo("rg foo_bar ."))
    assert live is not None and live["decision"] == "block"  # baseline: bites

    monkeypatch.setattr(mod, "_lookup_symbol", lambda graph, pattern: [])
    neutered = mod.check(repo("rg foo_bar ."))
    assert neutered is None  # neutered: the block is gone -> the fires-test reds
