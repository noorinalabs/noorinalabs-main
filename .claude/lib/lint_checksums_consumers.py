#!/usr/bin/env python3
"""Make a hand-rolled read of ``ontology/checksums.json`` unwritable (#1284).

``checksums_io.classify_entry`` is the ONE implementation of the ledger's
dirty predicate (``last_tracked != last_resolved``), and
``checksums_io.read_status`` is the ONE way to ask the ledger a question.
#1142 consolidated three hand-rolled copies into it; #1283 converted three
prose instructions. Nothing stopped a seventh — this lint is that stop.

Why a structural gate rather than per-consumer tests
====================================================
This class has no loud failure. A wrong key name yields ``0`` dirty files, a
wrong nesting level yields ``0``, and ``0`` is also the healthy value — so a
broken reader is indistinguishable from a working one against a healthy
ledger. Behavioural tests can only pin the copies that already exist; the copy
written next month, from memory, against a schema whose field names are not
guessable, is covered by nothing. Two independent wrong reads in two
consecutive sessions (#1142) plus three further sites found by sweep (#1283)
are the evidence that "it will happen again" is not speculative.

What it flags
=============
``hand-rolled-dirty-predicate`` (Python)
    An ``==``/``!=`` comparison in which one side references ``last_tracked``
    and another references ``last_resolved``. Deliberately BOTH-field: the
    tracker's own ``existing.get("last_tracked") == sha`` (a current-hash-vs-
    tracked write decision in ``.claude/hooks/ontology_tracker.py``) asks a
    legitimately different question and must stay unflagged — which is why
    ``ontology_tracker.py`` is NOT on the allowlist. It is scanned in full and
    passes on the merits.

``direct-ledger-read`` (Python)
    ``open()`` / ``.read_text()`` / ``.read_bytes()`` / ``json.load[s]()``
    applied to an expression that resolves to the checksums ledger. Building
    the PATH is fine — every converted consumer does, then hands it to
    ``read_status``; reading the bytes yourself is the finding.

``skill-ledger-read`` (Markdown)
    A ``cat``/``jq``/``head``-style read of ``checksums.json`` inside a fenced
    shell block, a ``checksums.json | jq`` pipeline, an inline
    ``json.load(... checksums.json ...)``, or a ``Read``-tool instruction
    naming the ledger. The three prose sites #1283 converted were as
    load-bearing as the code ones — the librarian's WAS the staleness reporter
    — and this lint found a fourth, live at HEAD:
    ``.claude/skills/handoff/SKILL.md`` step 1 said "Read
    ``ontology/checksums.json`` — count dirty files" (fixed in the same PR).

``unreasoned-allow-pragma`` (both)
    An escape-hatch pragma with no stated reason. The hatch exists, but it
    cannot be a magic word you type to make the lint quiet.

Known not to flag (residual gap, #1537)
========================================
The ``skill-ledger-read`` rule looks for a READ VERB — a shell reader command,
a pipe into one, an inline ``json.load``, or the ``Read`` tool — next to the
ledger. It has no rule for bare English that *conditions on* the dirty count
without naming any of those verbs. The historical, pre-#1142/#1283 form of
``session-start/SKILL.md`` Step 3a read (verbatim, before ``2bf0353``)::

    If 0 dirty files in `checksums.json`, report "Semantic overlay: current"

This scans CLEAN today (no reader verb, no fenced shell block) and is the one
historical instance on record that reproduces cleanly against this lint —
``test_the_documented_residual_prose_gap_still_scans_clean`` below pins that
fact so a future change that starts catching it shows up as an intentional
test update, not silent drift either way.

This is deliberately NOT closed by widening the regex. The false-positive risk
is not hypothetical: `wave-wrapup/SKILL.md` step 12a reads "If no dirty files,
report \"Semantic overlay: up to date\" and skip" — lexically almost identical
to the historical violation above, `if`/`dirty files`/`report` and all — but it
is legitimate, because the count it conditions on was already obtained by the
correctly-delegating `/ontology-rebuild` call one line earlier in the same
step, not hand-derived on the spot. Telling those two apart is a question
about what produced the count elsewhere in the document, which a per-line
lexical pattern cannot answer; a pattern loose enough to catch the violation
also catches the legitimate delegation, which is exactly the trade this
module's own escape-hatch section warns against (a pragma cannot substitute
for a lint that fires on the wrong lines to begin with). See #1537 for the
tracked follow-up (also covering shell-variable ledger paths, `rg` as a de
facto reader, `pathlib.Path.open()`, and `.claude/skills/**/*.py` scope).

Name tainting is FUNCTION-SCOPED, not module-global, and that is load-bearing:
``smart_grep_ontology.py`` binds a local named ``path`` to
``structural/code-graph.json`` in one function and to ``checksums.json`` in
another, then legitimately ``read_text``s the first. A module-global taint set
flags that; a scoped one does not.

Escape hatch
============
Two, both explicit:

* the ``ALLOWLIST`` table below — a repo-relative path mapped to the exact
  RULES it is exempt from (never a blanket file exemption) plus a reason;
* a pragma on the offending line or the line above it::

      # checksums-consumers: allow - <reason of at least 8 characters>
      <!-- checksums-consumers: allow - <reason> -->    (markdown)

  A pragma whose reason is missing or too short suppresses nothing and is
  itself reported.

CLI
===
    python3 .claude/lib/lint_checksums_consumers.py <path> [<path> ...]

``.py`` paths get the two code rules, ``.md`` paths get the prose rule; any
other suffix is skipped as unsupported.

Exit codes:
    0 — CLEAN: at least one file was scanned and nothing was found
    1 — FINDINGS
    2 — usage: no paths given, or a path that is not a file
    3 — NOT EVALUATED: the lint could not determine its condition — a file it
        was told to scan could not be read or parsed, an ``ALLOWLIST`` entry
        names a path that no longer exists (its exemptions are stale, so every
        verdict below it is meaningless), or nothing scannable was passed at
        all. A lint that scanned nothing is not a clean lint, so this is never
        0 (wave-31 acceptance bar 2a: "CANNOT EVALUATE is not a pass").

Same CLI/exit-code shape as ``.claude/lib/lint_skill_bash_dialect.py`` so it
wires identically into pre-commit + CI, plus the 3 this lint adds.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from typing import Iterable, Iterator

TRACKED_FIELD = "last_tracked"
RESOLVED_FIELD = "last_resolved"
LEDGER_BASENAME = "checksums.json"

RULE_PREDICATE = "hand-rolled-dirty-predicate"
RULE_LEDGER_READ = "direct-ledger-read"
RULE_SKILL_READ = "skill-ledger-read"
RULE_BARE_PRAGMA = "unreasoned-allow-pragma"

EXIT_CLEAN = 0
EXIT_FINDINGS = 1
EXIT_USAGE = 2
EXIT_NOT_EVALUATED = 3

# Repo-relative path -> (rules it is exempt from, why). Rule-SCOPED on purpose:
# a blanket file exemption would make the tracker's negative test vacuous, and
# an entry whose file has been renamed away should fail loudly (NOT EVALUATED)
# rather than silently widen or narrow what is gated.
ALLOWLIST: dict[str, tuple[frozenset[str], str]] = {
    ".claude/lib/checksums_io.py": (
        frozenset({RULE_PREDICATE, RULE_LEDGER_READ}),
        "the sanctioned reader/writer itself - the one implementation this lint protects",
    ),
}

# A test module may READ a ledger it just seeded — that is asserting on the
# writer's output, not asking the live ledger a question, and the ~22 such
# reads in `test_checksums_io.py` / `test_ontology_tracker.py` /
# `test_smart_grep_ontology.py` are all of that shape. So `direct-ledger-read`
# — and ONLY it — is off under a `tests/` directory.
#
# `hand-rolled-dirty-predicate` stays ON in tests deliberately. A re-derived
# predicate in a test is worse than one in production, not better: it is how a
# wrong reader gets "confirmed" by a test that computes the same wrong answer
# twice. There are none at HEAD, and this keeps it that way.
_TEST_PATH_RE = re.compile(r"(?:^|/)tests?/")
_TEST_EXEMPT_RULES = frozenset({RULE_LEDGER_READ})

_MIN_PRAGMA_REASON = 8
_PRAGMA_RE = re.compile(r"checksums-consumers:\s*allow\b(?P<reason>[^\n]*)")
_LEDGER_PATTERN = r"(?:[\w./-]*/)?checksums\.json"
_FENCE_RE = re.compile(r"^\s*```(\S*)")
_SHELL_LANGS = {"", "bash", "sh", "shell", "zsh"}
# A reader command whose operand is the ledger. `git stash push -- …
# ontology/checksums.json` (wave-start/SKILL.md) is deliberately NOT matched:
# moving the file is not reading the predicate out of it.
_READER_CMD_RE = re.compile(
    r"(?:^|[|;&(`$]|\s)(?:cat|bat|nl|head|tail|less|more|jq|xxd|od)\s[^|;&]*" + _LEDGER_PATTERN
)
_PIPED_READ_RE = re.compile(_LEDGER_PATTERN + r"\s*\|\s*(?:jq|python3?|rg|awk|sed|head|tail)\b")
_INLINE_JSON_LOAD_RE = re.compile(r"json\.loads?\s*\([^)]*" + _LEDGER_PATTERN)
# The `Read` TOOL (capital R, a tool name) pointed at the ledger — prose, not a
# code fence, is where this one lives.
_READ_TOOL_RE = re.compile(r"\bRead\b[^\n]*" + _LEDGER_PATTERN)

_READ_METHODS = frozenset({"read_text", "read_bytes", "read"})
_SUGGESTION = (
    "route it through .claude/lib/checksums_io.py (read_status / classify_entry, or the "
    "`status` subcommand) - see #1142/#1284"
)


class Finding:
    """One violation, addressed to whoever has to fix it."""

    def __init__(self, path: str, lineno: int, rule: str, text: str, why: str) -> None:
        self.path = path
        self.lineno = lineno
        self.rule = rule
        self.text = text
        self.why = why

    def key(self) -> tuple[str, int, str]:
        return (self.path, self.lineno, self.rule)

    def __str__(self) -> str:
        return f"{self.path}:{self.lineno}: [{self.rule}] {self.text.strip()} — {self.why}"


class NotEvaluated(Exception):
    """The lint could not determine its condition for a file. Never a pass."""


def repo_root() -> Path:
    """``.claude/lib/lint_checksums_consumers.py`` is two levels below the root."""
    return Path(__file__).resolve().parent.parent.parent


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root()).as_posix()
    except ValueError:
        return path.as_posix()


def _exempt(rel: str, rule: str) -> bool:
    rules, _reason = ALLOWLIST.get(rel, (frozenset(), ""))
    if rule in rules:
        return True
    return rule in _TEST_EXEMPT_RULES and _TEST_PATH_RE.search(rel) is not None


def check_allowlist() -> list[str]:
    """Return ``ALLOWLIST`` keys that no longer exist on disk.

    A stale exemption is a silent hole: the file it named was renamed or
    deleted, so its replacement is now scanned or not scanned by accident.
    The caller turns a non-empty result into NOT EVALUATED.
    """
    root = repo_root()
    return sorted(key for key in ALLOWLIST if not (root / key).exists())


# --------------------------------------------------------------------------
# Pragma handling
# --------------------------------------------------------------------------


def _pragma_reason(line: str) -> str | None:
    """The stated reason on a pragma line, or None when the line has no pragma."""
    m = _PRAGMA_RE.search(line)
    if m is None:
        return None
    return m.group("reason").replace("-->", "").strip(" \t-:–—")


def _suppressed(lines: list[str], lineno: int) -> bool:
    """True when an adequately-reasoned pragma covers 1-based ``lineno``.

    The pragma may sit on the offending line or on the nearest line above it,
    skipping any intervening code FENCE — in markdown the natural place to put
    it is above the ```` ```bash ```` opener, not wedged inside the recipe.
    A pragma found but under-reasoned stops the search and suppresses nothing.
    """
    idx = lineno - 1
    if 0 <= idx < len(lines):
        reason = _pragma_reason(lines[idx])
        if reason is not None:
            return len(reason) >= _MIN_PRAGMA_REASON
    idx -= 1
    while idx >= 0 and _FENCE_RE.match(lines[idx]) is not None:
        idx -= 1
    if 0 <= idx < len(lines):
        reason = _pragma_reason(lines[idx])
        if reason is not None:
            return len(reason) >= _MIN_PRAGMA_REASON
    return False


def _bare_pragma_findings(path: str, lines: list[str]) -> list[Finding]:
    out: list[Finding] = []
    for idx, line in enumerate(lines):
        reason = _pragma_reason(line)
        if reason is not None and len(reason) < _MIN_PRAGMA_REASON:
            out.append(
                Finding(
                    path,
                    idx + 1,
                    RULE_BARE_PRAGMA,
                    line,
                    f"an allow pragma must state a reason of at least {_MIN_PRAGMA_REASON} "
                    "characters; a bare pragma suppresses nothing",
                )
            )
    return out


# --------------------------------------------------------------------------
# Python rules
# --------------------------------------------------------------------------


def _field_refs(node: ast.AST, taint: dict[str, set[str]]) -> set[str]:
    """Which ledger fields an expression references, directly or via a local."""
    refs: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            if sub.value in (TRACKED_FIELD, RESOLVED_FIELD):
                refs.add(sub.value)
        elif isinstance(sub, ast.Attribute) and sub.attr in (TRACKED_FIELD, RESOLVED_FIELD):
            refs.add(sub.attr)
        elif isinstance(sub, ast.Name):
            refs |= taint.get(sub.id, set())
    return refs


def _is_ledger_expr(node: ast.AST, ledger_names: set[str]) -> bool:
    """True when an expression resolves to the checksums ledger path."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            if LEDGER_BASENAME in sub.value:
                return True
        elif isinstance(sub, ast.Name) and sub.id in ledger_names:
            return True
        elif isinstance(sub, ast.Call):
            func = sub.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name.endswith("checksums_path"):
                return True
    return False


def _scope_nodes(scope: ast.AST) -> tuple[list[ast.AST], list[ast.AST]]:
    """DFS pre-order nodes of ONE scope, plus the nested scopes to recurse into.

    Function bodies are scope BOUNDARIES — see the module docstring's
    ``smart_grep_ontology`` note for why a module-global taint set is wrong.
    """
    nodes: list[ast.AST] = []
    nested: list[ast.AST] = []

    def walk(node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                nested.append(child)
                continue
            nodes.append(child)
            walk(child)

    walk(scope)
    return nodes, nested


def _scan_scope(
    path: str,
    scope: ast.AST,
    field_taint: dict[str, set[str]],
    ledger_names: set[str],
) -> Iterator[Finding]:
    field_taint = dict(field_taint)
    ledger_names = set(ledger_names)
    nodes, nested = _scope_nodes(scope)

    for node in nodes:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value = node.value
            if value is not None:
                refs = _field_refs(value, field_taint)
                is_ledger = _is_ledger_expr(value, ledger_names)
                for target in targets:
                    if isinstance(target, ast.Name):
                        if refs:
                            field_taint[target.id] = refs
                        if is_ledger:
                            ledger_names.add(target.id)

        elif isinstance(node, ast.Compare):
            if all(isinstance(op, (ast.Eq, ast.NotEq)) for op in node.ops):
                operands = [node.left, *node.comparators]
                per_operand = [_field_refs(o, field_taint) for o in operands]
                has_tracked = any(TRACKED_FIELD in r for r in per_operand)
                has_resolved = any(RESOLVED_FIELD in r for r in per_operand)
                # BOTH fields on one comparison is the dirty predicate. One
                # field alone (the tracker's `last_tracked == sha`) asks a
                # different question and is not this lint's business.
                if has_tracked and has_resolved:
                    yield Finding(
                        path,
                        node.lineno,
                        RULE_PREDICATE,
                        f"comparison of {TRACKED_FIELD} against {RESOLVED_FIELD}",
                        "the dirty predicate has exactly one implementation "
                        f"(checksums_io.classify_entry); {_SUGGESTION}",
                    )

        elif isinstance(node, ast.Call):
            func = node.func
            hit = False
            if isinstance(func, ast.Attribute) and func.attr in _READ_METHODS:
                hit = _is_ledger_expr(func.value, ledger_names)
            elif isinstance(func, ast.Name) and func.id == "open":
                hit = any(_is_ledger_expr(a, ledger_names) for a in node.args)
            elif (
                isinstance(func, ast.Attribute)
                and func.attr in ("load", "loads")
                and isinstance(func.value, ast.Name)
                and func.value.id == "json"
            ):
                hit = any(_is_ledger_expr(a, ledger_names) for a in node.args)
            if hit:
                yield Finding(
                    path,
                    node.lineno,
                    RULE_LEDGER_READ,
                    f"direct read of {LEDGER_BASENAME}",
                    "building the ledger PATH is fine, reading its bytes yourself is not; "
                    f"{_SUGGESTION}",
                )

    for child in nested:
        yield from _scan_scope(path, child, field_taint, ledger_names)


def check_python_text(path: str, text: str) -> list[Finding]:
    """Findings for one Python source. Raises ``NotEvaluated`` on a parse failure."""
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        raise NotEvaluated(f"{path}: could not parse as Python ({exc})") from exc

    lines = text.splitlines()
    found = [f for f in _scan_scope(path, tree, {}, set()) if not _exempt(path, f.rule)]
    found += _bare_pragma_findings(path, lines)
    return _dedupe(f for f in found if not _suppressed(lines, f.lineno))


# --------------------------------------------------------------------------
# Markdown rule
# --------------------------------------------------------------------------


def check_markdown_text(path: str, text: str) -> list[Finding]:
    """Findings for one markdown file (skill prose + fenced shell recipes)."""
    lines = text.splitlines()
    found: list[Finding] = []
    in_block = False
    block_lang = ""

    for idx, raw in enumerate(lines):
        fence = _FENCE_RE.match(raw)
        if fence is not None:
            if not in_block:
                in_block, block_lang = True, fence.group(1).lower()
            else:
                in_block, block_lang = False, ""
            continue

        stripped = raw.strip()
        shell = in_block and block_lang in _SHELL_LANGS
        if shell and not stripped.startswith("#"):
            if _READER_CMD_RE.search(raw) or _PIPED_READ_RE.search(raw):
                found.append(
                    Finding(
                        path,
                        idx + 1,
                        RULE_SKILL_READ,
                        raw,
                        f"a recipe that reads {LEDGER_BASENAME} by hand re-derives the "
                        f"predicate in prose; {_SUGGESTION}",
                    )
                )
                continue
        if _INLINE_JSON_LOAD_RE.search(raw) or _READ_TOOL_RE.search(raw):
            found.append(
                Finding(
                    path,
                    idx + 1,
                    RULE_SKILL_READ,
                    raw,
                    f"an instruction to read {LEDGER_BASENAME} directly; {_SUGGESTION}",
                )
            )

    found = [f for f in found if not _exempt(path, f.rule)]
    found += _bare_pragma_findings(path, lines)
    return _dedupe(f for f in found if not _suppressed(lines, f.lineno))


def _dedupe(findings: Iterable[Finding]) -> list[Finding]:
    seen: set[tuple[str, int, str]] = set()
    out: list[Finding] = []
    for f in sorted(findings, key=lambda f: (f.path, f.lineno, f.rule)):
        if f.key() not in seen:
            seen.add(f.key())
            out.append(f)
    return out


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def check_file(path: Path) -> list[Finding]:
    """Findings for one file. Raises ``NotEvaluated`` when it cannot be read/parsed."""
    rel = _rel(path)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise NotEvaluated(f"{rel}: could not read ({exc})") from exc
    if path.suffix == ".py":
        return check_python_text(rel, text)
    return check_markdown_text(rel, text)


def main(argv: list[str]) -> int:
    paths = argv[1:]
    if not paths:
        print(
            "usage: lint_checksums_consumers.py <file.py|file.md> [<file> ...]",
            file=sys.stderr,
        )
        print(
            "VERDICT: NOT EVALUATED — no paths given. A lint that scanned nothing is "
            "not a clean lint (#1284).",
            file=sys.stderr,
        )
        return EXIT_USAGE

    stale = check_allowlist()
    if stale:
        print(
            "VERDICT: NOT EVALUATED — ALLOWLIST names path(s) that no longer exist, so "
            "its exemptions are stale: " + ", ".join(stale),
            file=sys.stderr,
        )
        return EXIT_NOT_EVALUATED

    findings: list[Finding] = []
    scanned = 0
    skipped: list[str] = []
    for raw in paths:
        path = Path(raw)
        if not path.is_file():
            print(f"ERROR: not a file: {raw}", file=sys.stderr)
            print(f"VERDICT: NOT EVALUATED — {raw} could not be scanned.", file=sys.stderr)
            return EXIT_USAGE
        if path.suffix not in (".py", ".md"):
            skipped.append(raw)
            continue
        try:
            findings.extend(check_file(path))
        except NotEvaluated as exc:
            print(f"VERDICT: NOT EVALUATED — {exc}", file=sys.stderr)
            return EXIT_NOT_EVALUATED
        scanned += 1

    if scanned == 0:
        print(
            f"VERDICT: NOT EVALUATED — none of the {len(skipped)} path(s) given had a "
            "scannable (.py/.md) suffix; nothing was measured.",
            file=sys.stderr,
        )
        return EXIT_NOT_EVALUATED

    if findings:
        print(f"Hand-rolled {LEDGER_BASENAME} reads (noorinalabs-main#1284):")
        for f in findings:
            print(f"  {f}")
        print(f"VERDICT: FINDINGS — {len(findings)} in {scanned} file(s) scanned.")
        return EXIT_FINDINGS

    print(f"VERDICT: CLEAN — {scanned} file(s) scanned, no hand-rolled ledger reads.")
    return EXIT_CLEAN


if __name__ == "__main__":
    sys.exit(main(sys.argv))
