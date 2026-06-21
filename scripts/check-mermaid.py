#!/usr/bin/env python3
"""Validate every fenced ```mermaid block in the given docs by RENDERING it.

The #786 review surfaced that no CI job rendered mermaid diagrams, so a
syntactically-broken block (the L3 alertmanager `<unset>` case) shipped green —
markdown-lint, cspell, and lychee all pass a non-rendering diagram. This gate
closes that gap: it extracts each fenced mermaid block and renders it with
mermaid-cli (`mmdc`, headless Chromium), failing the build on any block that
does not render.

Scope (default): docs/*.md + ontology/*.md. Pass explicit file paths to override.

Detection: a block fails if `mmdc` exits non-zero (genuine syntax errors,
unknown diagram types, malformed structure) OR if the produced SVG carries a
mermaid error marker (defends against versions that emit an error-SVG with a
zero exit). KNOWN RESIDUAL (documented, not hidden): a literal `<` inside a
`[label]` is treated by mermaid as an HTML tag and renders DEGRADED with a clean
exit — render-gating cannot catch that via exit code. Authors must escape raw
angle brackets in labels (`#lt;`/`#gt;`), which is exactly the #786 fix. The
gate prints a warning when it sees a raw `<`/`>` inside a block so the footgun
is at least surfaced.

mmdc resolution order: $MMDC, then `mmdc` on PATH, then `npx -y
@mermaid-js/mermaid-cli`. Chromium is run with `--no-sandbox` (required in CI
containers) via a generated puppeteer config.

Exit codes:
    0 — every block rendered (gate green)
    1 — at least one block failed to render
    2 — no mmdc available / usage error
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_MERMAID_BLOCK = re.compile(r"^([ \t]*)```mermaid[ \t]*\n(.*?)^[ \t]*```", re.DOTALL | re.MULTILINE)
_ERROR_MARKERS = ("syntax error", "error in text", "aborted", "parse error")
# A raw `<` or `>` that is not part of a mermaid edge token (`-->`, `<--`,
# `<==`, `-.->`) and not a `<br>` line-break tag. Used only for an advisory
# footgun warning, never to fail the gate (heuristic; full render is the gate).
_RAW_ANGLE = re.compile(r"<(?!br\b|/|--|==|\.)|(?<![-=.])>")


def _default_files() -> list[Path]:
    files: list[Path] = []
    for d in ("docs", "ontology"):
        files.extend(sorted(Path(d).glob("*.md")))
    return files


def _resolve_mmdc() -> list[str] | None:
    env = os.environ.get("MMDC")
    if env:
        return [env]
    if shutil.which("mmdc"):
        return ["mmdc"]
    if shutil.which("npx"):
        return ["npx", "-y", "@mermaid-js/mermaid-cli"]
    return None


def _iter_blocks(text: str) -> list[tuple[int, str]]:
    """Return (1-based start line of the ```mermaid fence, block body)."""
    blocks: list[tuple[int, str]] = []
    for m in _MERMAID_BLOCK.finditer(text):
        line_no = text.count("\n", 0, m.start()) + 1
        blocks.append((line_no, m.group(2)))
    return blocks


def _render(mmdc: list[str], mmd: Path, out: Path, pp: Path) -> tuple[bool, str]:
    """Render one block. Return (ok, detail)."""
    try:
        proc = subprocess.run(
            [*mmdc, "-i", str(mmd), "-o", str(out), "-p", str(pp)],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return False, "mmdc timed out (>120s)"
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()
        return False, tail[0] if tail else f"mmdc exit {proc.returncode}"
    if out.is_file():
        svg = out.read_text(encoding="utf-8", errors="replace").lower()
        if any(mark in svg for mark in _ERROR_MARKERS):
            return False, "rendered SVG contains a mermaid error marker"
    return True, "ok"


def main(argv: list[str]) -> int:
    files = [Path(a) for a in argv[1:]] or _default_files()
    files = [f for f in files if f.is_file()]
    if not files:
        print("check-mermaid: no input files.", file=sys.stderr)
        return 0

    mmdc = _resolve_mmdc()
    if mmdc is None:
        print(
            "check-mermaid: mmdc not found. Install @mermaid-js/mermaid-cli "
            "(npm i -g @mermaid-js/mermaid-cli) or set $MMDC.",
            file=sys.stderr,
        )
        return 2

    # Temp dir under cwd so a snap-confined local mmdc can read it (snap cannot
    # access /tmp); CI's npm mmdc is unconfined and works either way.
    workdir = Path(tempfile.mkdtemp(prefix=".mmcheck-", dir="."))
    pp = workdir / "puppeteer.json"
    pp.write_text('{"args":["--no-sandbox"]}', encoding="utf-8")

    failures: list[str] = []
    total = 0
    try:
        for f in files:
            text = f.read_text(encoding="utf-8")
            for idx, (line_no, body) in enumerate(_iter_blocks(text)):
                total += 1
                if _RAW_ANGLE.search(body):
                    print(
                        f"  warning {f}:{line_no} — raw '<'/'>' in a mermaid block; "
                        "escape as #lt;/#gt; in labels (renders degraded otherwise, #786)."
                    )
                mmd = workdir / f"b{total}.mmd"
                mmd.write_text(body, encoding="utf-8")
                ok, detail = _render(mmdc, mmd, workdir / f"b{total}.svg", pp)
                where = f"{f}:{line_no} (block #{idx + 1})"
                if ok:
                    print(f"  ok   {where}")
                else:
                    failures.append(f"{where} — {detail}")
                    print(f"  FAIL {where} — {detail}")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    print(f"\nchecked {total} mermaid block(s) across {len(files)} file(s).")
    if failures:
        print(f"\n{len(failures)} mermaid block(s) failed to render:", file=sys.stderr)
        for fail in failures:
            print(f"  - {fail}", file=sys.stderr)
        return 1
    print("all mermaid blocks render cleanly.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
