#!/usr/bin/env python3
"""PreToolUse hook: route a symbol-shaped `rg`/`grep` to the structural ontology.

Problem (#1017, ported from botfarm #886): a brute-force `rg some_func` (or the
`grep` block_bare_grep already discourages) re-discovers structure the generated
ontology (`ontology/structural/code-graph.json`) already holds — every symbol's
definition site, plus its callers/callees as graph edges — and pays for it in
tokens (the search dumps every matching line across the tree; the agent then
re-reads whole files to get the surrounding context anyway).

What this hook does: when the Bash command is an `rg`/`grep`/`egrep`/`fgrep`
invocation searching for a single bare-identifier pattern (or a dotted
`Class.method` qualname) that the graph actually indexes, it BLOCKS the raw
search and returns the answer inline instead — definition site(s) plus a few
call-site pointers, all as `path:line`, straight from `code-graph.json` (the
fixed node/edge contract `ontology_gen.model` documents, not a re-derived
index). The agent reads exactly those lines instead of searching the tree.

Relationship to `block_bare_grep`: this hook runs BEFORE that backstop in the
dispatcher, so a symbol-shaped `grep`/`rg` is answered from the ontology first.
Everything block_bare_grep still owns is untouched: a free-text `grep` falls
through to its "use `rg`" message, and a free-text `rg` is allowed as before.

Escape hatch — `# --graph-tried`: a free-text search (a log message, an error
string, a regex with metacharacters) has nothing for the graph to match, so it
is never intercepted in the first place. For the narrower case — the pattern
IS a real symbol name but the ontology answer is stale, incomplete, or the
agent has already used it and genuinely needs the raw search (e.g. to see every
call site, not just the first few) — append a trailing shell comment to the
SAME command: `rg foo_bar . # --graph-tried`. `#` opens a real shell comment
there (preceded by whitespace), so the shell runs the search UNCHANGED; this
hook independently tokenizes the same string (shlex does not strip `#`) and
recognizes the literal `#` `--graph-tried` token pair as the bypass. A quoted
occurrence of the same text (`rg "--graph-tried" .`) collapses to one data
token under `tokenize()` and does NOT match — only the unquoted, comment-
position marker counts (Rule 2). (For a `grep` invocation the marker bypasses
THIS hook, but block_bare_grep still applies — pair it with `rg`, or with
`NOORINA_ALLOW_GREP=1` if a raw `grep` is truly needed.)

Context-guard convention (charter/hooks.md):
- Rule 1 — N/A: this hook only inspects/blocks a command; it never mutates git.
- Rule 2 — command-text matching goes through the shared `_shell_parse` helpers
  (`strip_heredocs` + `tokenize` + `iter_command_segments`), never a raw regex
  over the untouched command. An `rg`/`grep` mention inside a heredoc body or a
  quoted argument collapses to a single data token and is not matched as a
  command-position invocation.

Fail-safe posture: a tokenization failure, a missing/unparseable ontology graph,
or zero graph matches ALL allow (return None) — this hook only ever prevents a
search it can genuinely answer better; it never blocks a query the ontology has
nothing for.

Exit codes:
  0 — allow (not a Bash call, not rg/grep, escape hatch present, pattern isn't
      a bare identifier, ontology missing/unparseable, or no graph match)
  2 — block (a symbol the graph indexes was found; the answer is inline)
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _shell_parse import (  # noqa: E402
    iter_command_segments,
    strip_heredocs,
    tokenize,
    walk_flag_values,
)
from annunaki_log import log_pretooluse_block  # noqa: E402

# Shared checksums reader — the ONE implementation of the dirty predicate (#1142).
_LIB = Path(__file__).resolve().parent.parent / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))
import checksums_io  # noqa: E402

# Repo root, resolved module-relative exactly like ontology_tracker.py: the hook
# lives at ``<repo>/.claude/hooks/smart_grep_ontology.py``, so three parents up
# is the repo root that owns ``ontology/structural/code-graph.json``. This is
# the worktree root in production (the structural layer is generated per-tree),
# and is monkeypatched in tests to point at a synthetic ontology.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# The grep family plus ripgrep — matched on basename, so `/usr/bin/grep` and a
# wrapper-prefixed `sudo grep` both resolve. `rg` is noorina's standard text
# search (block_bare_grep steers `grep` to it); a symbol-shaped `rg` is exactly
# what this hook answers from the ontology.
_GREP_BINARIES = frozenset({"grep", "egrep", "fgrep", "rg"})

# Common exec wrappers peeled to find the effective command word, mirroring
# block_bare_grep. We over-peel a wrapper's value tokens rather than track them
# per-wrapper: mis-peeling only ever makes us fail OPEN (return None), and a
# genuinely bare grep we miss is still caught by block_bare_grep downstream.
_WRAPPERS = frozenset(
    {"sudo", "env", "time", "command", "nice", "nohup", "stdbuf", "ionice", "xargs", "watch"}
)

_ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_]\w*=")

# Flags (grep + ripgrep, short and long form) that consume a SEPARATE following
# token as their value. Getting this list right matters: a value like the "3"
# in `-A 3` must never be mistaken for the search pattern. `-e`/`--regexp` is
# handled separately (its value IS the pattern, not something to skip past).
_VALUE_FLAGS = frozenset(
    {
        "-A",
        "-B",
        "-C",
        "-m",
        "-f",
        "--file",
        "-g",
        "--glob",
        "-t",
        "--type",
        "-T",
        "--type-not",
        "--include",
        "--exclude",
        "--after-context",
        "--before-context",
        "--context",
        "--max-count",
        "--max-columns",
        "--max-columns-preview",
        "-M",
        "--threads",
        "-j",
    }
)

# A bare identifier or a dotted qualname (`Class.method`) — the only shapes the
# graph indexes as a symbol id. Anything else (spaces, quotes, regex
# metacharacters) is free text the graph was never going to answer, so it is
# never even looked up.
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")

# Skip a pattern this short even if it parses as an identifier — a 1-2 char
# token ("id", "ok") is too generic to be worth an ontology round-trip and
# would surface a wall of unrelated hits.
_MIN_PATTERN_LEN = 3

# Cap how many definition sites the answer lists, and how many call sites per
# definition — keeps the block message a scan, not a second search dump.
_MAX_MATCHES = 8
_MAX_CALLERS = 5


def _ontology_dir() -> Path:
    return REPO_ROOT / "ontology"


def _grep_tail(segment: list[str]) -> list[str] | None:
    """The tokens AFTER an `rg`/`grep`-family binary in a command segment, or None.

    Peels leading one-shot env-assignments (`FOO=bar rg ...`) and known exec
    wrappers with their flags (`sudo grep`, `env X=1 rg`), then returns the tail
    when the effective command's basename is a grep-family binary. Wrapper value
    tokens are over-peeled (see `_WRAPPERS`) — safe because a miss fails open.
    """
    i = 0
    n = len(segment)
    while i < n and _ENV_ASSIGN_RE.match(segment[i]):
        i += 1
    while i < n and os.path.basename(segment[i]) in _WRAPPERS:
        i += 1
        while i < n and (segment[i].startswith("-") or _ENV_ASSIGN_RE.match(segment[i])):
            i += 1
    if i < n and os.path.basename(segment[i]) in _GREP_BINARIES:
        return segment[i + 1 :]
    return None


def _find_grep_segment(tokens: list[str]) -> list[str] | None:
    """The grep/rg-family invocation's tail tokens (binary + prefix stripped)."""
    for segment in iter_command_segments(tokens):
        tail = _grep_tail(segment)
        if tail is not None:
            return tail
    return None


def _has_escape_hatch(tokens: list[str]) -> bool:
    """True iff a literal, unquoted `# --graph-tried` token pair is present.

    Both are separate shlex tokens only when unquoted (a quoted copy collapses
    to one data token — see module docstring), so this cannot be tripped by a
    search pattern that merely contains the same text.
    """
    return any(
        tokens[i] == "#" and tokens[i + 1] == "--graph-tried" for i in range(len(tokens) - 1)
    )


def _extract_pattern(rest: list[str]) -> str | None:
    """The search pattern from a grep/rg tail (binary already dropped), or None.

    `-e`/`--regexp`'s value wins when present; otherwise the first token that
    isn't a flag or a flag's value.
    """
    explicit = walk_flag_values(rest, {"-e", "--regexp"})
    if explicit:
        return explicit[0]
    i = 0
    n = len(rest)
    while i < n:
        tok = rest[i]
        if tok in _VALUE_FLAGS:
            i += 2
            continue
        if tok.startswith("-"):
            i += 1
            continue
        return tok
    return None


def _looks_like_symbol(pattern: str) -> bool:
    return bool(_IDENTIFIER_RE.match(pattern)) and len(pattern.replace(".", "")) >= _MIN_PATTERN_LEN


def _load_graph() -> dict | None:
    path = _ontology_dir() / "structural" / "code-graph.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _dirty_files() -> set[str]:
    """Paths NOT known to be resolved — same staleness signal the librarian reports.

    Delegates the predicate to ``checksums_io`` (#1142) rather than
    re-deriving ``last_tracked != last_resolved`` here; that comparison used to
    be hand-rolled in four places, and every wrong hand-rolling of it returns a
    plausible empty set rather than an error.

    Malformed entries join the dirty set on purpose: this drives a "[STALE]"
    annotation, and an entry whose shape the reader cannot classify is
    not-known-current, which is what the annotation says. Empty on any read
    error (advisory only; never blocks the hook itself).
    """
    path = _ontology_dir() / "checksums.json"
    try:
        status = checksums_io.read_status(path)
    except checksums_io.ChecksumsUnreadable:
        return set()
    return set(status.dirty) | {rel for rel, _ in status.malformed}


def _lookup_symbol(graph: dict, pattern: str) -> list[dict]:
    """Nodes whose qualname (the part of the id after ``::``) IS ``pattern``, or
    whose last dotted component is — so a bare method search (``get``) also
    surfaces ``_Config.get``, and an exact qualname search (``_Config.get``)
    matches only that. File/module nodes (no ``::``) are never returned — a
    bare filename is a `find` job, not a symbol lookup."""
    matches = []
    for node in graph.get("nodes", []):
        node_id = node.get("id", "")
        if "::" not in node_id:
            continue
        symbol = node_id.split("::", 1)[1]
        if symbol == pattern or symbol.rsplit(".", 1)[-1] == pattern:
            matches.append(node)
    return matches


def _callers(graph: dict, node_id: str, nodes_by_id: dict[str, dict]) -> list[str]:
    """Up to `_MAX_CALLERS` ``path:line`` pointers for edges that call `node_id`."""
    out: list[str] = []
    for edge in graph.get("edges", []):
        if edge.get("type") != "calls" or edge.get("dst") != node_id:
            continue
        src = nodes_by_id.get(edge.get("src", ""))
        if src is not None:
            out.append(f"{src['path']}:{src['line']}")
        if len(out) >= _MAX_CALLERS:
            break
    return out


def _build_answer(pattern: str, matches: list[dict], graph: dict) -> str:
    nodes_by_id = {n["id"]: n for n in graph.get("nodes", []) if "id" in n}
    dirty = _dirty_files()
    shown = matches[:_MAX_MATCHES]

    lines = [
        f"ONTOLOGY HIT for `{pattern}` — routed to the structural ontology instead "
        f"of a brute-force search ({len(matches)} definition site(s)):",
        "",
    ]
    for node in shown:
        node_id = node["id"]
        stale = (
            "  [STALE: source changed since ontology was last resolved]"
            if node.get("path") in dirty
            else ""
        )
        lines.append(f"  - {node.get('kind')} {node_id} -> {node['path']}:{node['line']}{stale}")
        callers = _callers(graph, node_id, nodes_by_id)
        if callers:
            lines.append(f"      called from: {', '.join(callers)}")
    if len(matches) > _MAX_MATCHES:
        lines.append(
            f"  ... and {len(matches) - _MAX_MATCHES} more match(es) — refine the "
            "query (e.g. the full `Class.method` qualname) if you need a different one."
        )

    lines += [
        "",
        "Read the file(s) at the line(s) above directly instead of searching the tree.",
        "Escape hatch: if this is stale/insufficient or you need the raw search for "
        "another reason, append ` # --graph-tried` to the SAME command (use `rg`, not "
        "`grep` — block_bare_grep still applies) — the shell treats it as a comment "
        "and runs the search unchanged.",
    ]
    return "\n".join(lines)


def check(input_data: dict) -> dict | None:
    """Dispatcher-compatible entry point. None to allow, dict to block."""
    if input_data.get("tool_name", "") != "Bash":
        return None

    command = input_data.get("tool_input", {}).get("command", "")
    if not isinstance(command, str) or not command:
        return None

    tokens = tokenize(strip_heredocs(command))
    if tokens is None:
        return None  # unparseable → fail open (not a security gate)

    if _has_escape_hatch(tokens):
        return None

    grep_tail = _find_grep_segment(tokens)
    if grep_tail is None:
        return None

    pattern = _extract_pattern(grep_tail)
    if pattern is None or not _looks_like_symbol(pattern):
        return None

    graph = _load_graph()
    if graph is None:
        return None

    matches = _lookup_symbol(graph, pattern)
    if not matches:
        return None

    reason = _build_answer(pattern, matches, graph)
    log_pretooluse_block("smart_grep_ontology", command, reason)
    return {"decision": "block", "reason": reason}


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    result = check(input_data)
    if result and result.get("decision") == "block":
        print(json.dumps(result))
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
