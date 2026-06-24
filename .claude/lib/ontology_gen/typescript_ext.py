#!/usr/bin/env python3
"""TypeScript / React structural extractor — zero-dependency, regex/line based (#855).

Toolchain choice (flagged to the #855 owner as a contract-adjacent decision):
``ts-morph`` (a Node/npm runtime) and ``tree-sitter-typescript`` (a compiled pip dep)
were both considered per the issue. This module uses neither — a self-contained,
stdlib-only line scanner — because:

* **Zero runtime dep** is the lightest possible toolchain (the issue's stated
  preference) and matches the eval's control / supply-chain argument against taking a
  third-party graph tool (#854). The parent repo's CI installs no JS/TS toolchain, so a
  pip/npm dep would have to be added org-wide just to index a layer the parent doesn't
  even have.
* The contract granularity is **module/file + class/func/method**, not per-call-
  expression precision — well within reach of a line scanner over export declarations.

A ``tree_sitter_typescript`` backend can be slotted behind :func:`extract_typescript`
later (the function signature is the seam) if/when richer call-graph fidelity is wanted;
that is explicitly out of scope for #855's pilot.

Captured: imports (incl. relative re-exports → ``references``), exported & top-level
classes, functions, arrow-function consts, and React components (PascalCase consts).
Block comments / strings are not fully tokenized — this is a pragmatic scanner, not a
parser — so exotic constructs may be missed; that is an accepted fidelity trade for
zero deps and is documented for #856/#1128.
"""

from __future__ import annotations

import re

from .model import FileInfo, ImportInfo, SymbolInfo

_JS_EXTS = (".js", ".jsx", ".mjs", ".cjs")

# import ... from '...'  /  import '...'
_RE_IMPORT_FROM = re.compile(r"""^\s*import\b[^;'"]*?\bfrom\s*['"]([^'"]+)['"]""", re.MULTILINE)
_RE_IMPORT_BARE = re.compile(r"""^\s*import\s*['"]([^'"]+)['"]""", re.MULTILINE)
# export ... from '...'  (re-export → references edge target)
_RE_REEXPORT = re.compile(r"""^\s*export\b[^;'"]*?\bfrom\s*['"]([^'"]+)['"]""", re.MULTILINE)

_RE_CLASS = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+([A-Za-z_$][\w$]*)"
    r"(?:\s+extends\s+([A-Za-z_$][\w$.]*))?",
    re.MULTILINE,
)
_RE_FUNCTION = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*"
    r"([A-Za-z_$][\w$]*)\s*\(([^)]*)\)",
    re.MULTILINE,
)
# const Foo = (...) =>   /   const Foo = async (...) =>   /   const Foo = function
_RE_ARROW_CONST = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?const\s+([A-Za-z_$][\w$]*)\s*"
    r"(?::\s*[^=]+)?=\s*(?:async\s*)?(?:\(([^)]*)\)|[A-Za-z_$][\w$]*)\s*=>",
    re.MULTILINE,
)


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _split_params(raw: str) -> list[str]:
    raw = raw.strip()
    if not raw:
        return []
    params: list[str] = []
    depth = 0
    current = ""
    # Split on top-level commas only (object/array/generic destructuring may nest).
    for ch in raw:
        if ch in "([{<":
            depth += 1
        elif ch in ")]}>":
            depth -= 1
        if ch == "," and depth == 0:
            params.append(current)
            current = ""
        else:
            current += ch
    if current.strip():
        params.append(current)
    out: list[str] = []
    for part in params:
        # Keep just the parameter name (drop type annotations / defaults).
        name = part.strip().split(":")[0].split("=")[0].strip()
        name = name.lstrip(".")  # rest params ...args
        if name:
            out.append(name)
    return out


def _summary(source: str) -> str:
    """First line of a leading ``/** ... */`` or ``//`` banner comment, if any."""
    for line in source.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("/**") or stripped.startswith("/*"):
            body = stripped.lstrip("/*").strip()
            return body if body else ""
        if stripped.startswith("//"):
            return stripped.lstrip("/").strip()
        return ""
    return ""


def extract_typescript(rel_path: str, source: str) -> FileInfo:
    lang = "javascript" if rel_path.endswith(_JS_EXTS) else "typescript"

    imports: list[ImportInfo] = []
    seen_imports: set[str] = set()
    for m in _RE_IMPORT_FROM.finditer(source):
        mod = m.group(1)
        if mod not in seen_imports:
            seen_imports.add(mod)
            imports.append(ImportInfo(kind="imports", module=mod, line=_line_of(source, m.start())))
    for m in _RE_IMPORT_BARE.finditer(source):
        mod = m.group(1)
        if mod not in seen_imports:
            seen_imports.add(mod)
            imports.append(ImportInfo(kind="imports", module=mod, line=_line_of(source, m.start())))

    reexports: list[str] = []
    for m in _RE_REEXPORT.finditer(source):
        target = m.group(1)
        if target not in reexports:
            reexports.append(target)

    symbols: list[SymbolInfo] = []
    seen_symbols: set[str] = set()

    def _add(kind: str, name: str, line: int, params: list[str], bases: list[str]) -> None:
        if name in seen_symbols:
            return
        seen_symbols.add(name)
        symbols.append(
            SymbolInfo(kind=kind, name=name, qualname=name, line=line, params=params, bases=bases)
        )

    for m in _RE_CLASS.finditer(source):
        name = m.group(1)
        base = m.group(2)
        _add("class", name, _line_of(source, m.start()), [], [base] if base else [])
    for m in _RE_FUNCTION.finditer(source):
        name = m.group(1)
        _add("func", name, _line_of(source, m.start()), _split_params(m.group(2)), [])
    for m in _RE_ARROW_CONST.finditer(source):
        name = m.group(1)
        params = _split_params(m.group(2) or "")
        _add("func", name, _line_of(source, m.start()), params, [])

    return FileInfo(
        path=rel_path,
        lang=lang,
        kind="file",
        summary=_summary(source),
        imports=imports,
        symbols=symbols,
        reexports=reexports,
    )
