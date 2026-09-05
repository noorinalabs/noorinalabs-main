#!/usr/bin/env python3
"""Lint skill markdown for bash-only `[ "$A" \\< "$B" ]` string-comparison operators.

`\\<` / `\\>` inside a POSIX `[ ]` test are a **bash-only** extension (borrowed
from `[[ ]]`'s `<`/`>` string comparison, escaped so `[ ]` doesn't parse them as
redirection). Under `zsh` — this org's shell for both the interactive prompt
and the agent Bash tool (CLAUDE.md § Shell environment) — the test does not
evaluate to true or false; it **errors**: ``condition expected: <``. An errored
test is non-zero, so an `if` guarding on it silently takes the "false" branch
instead of failing loudly (noorinalabs-main#1485 — `/wave-kickoff` Step 0a's
staleness guard was fail-open in exactly this shape: the gate had never been
able to fail under zsh).

This is the same root class as #1479 (skill bash blocks authored in bash
dialect, executed under zsh) but for the `[ ]` test-builtin operator set
specifically, rather than process substitution.

What it flags
=============
Inside any fenced code block tagged `bash`, `sh`, `shell` or `zsh` (or
untagged — a bare ``` fence with no info string still commonly holds a shell
recipe in these skills), any line containing a POSIX `[ ... ]` test with an
escaped `\\<` or `\\>` inside it. Prose outside code fences is never scanned
(a sentence explaining the bug, like this docstring, would otherwise
self-trigger).

CLI
===
    python3 .claude/lib/lint_skill_bash_dialect.py <file.md> [<file.md> ...]

Glob over the skills tree (zsh recursive glob; bash needs `shopt -s globstar`):

    python3 .claude/lib/lint_skill_bash_dialect.py .claude/skills/**/*.md

Exit codes:
    0 — no bash-only `[ \\< ]` / `[ \\> ]` operator found in any file
    1 — at least one violation (each printed as `path:line: <text> — <why>`)
    2 — usage / file-not-found error

Same CLI/exit-code shape as `.claude/lib/lint_skill_graphql_pagination.py` so
it wires identically into pre-commit + CI (#888/#893 precedent).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# A fenced code block opens/closes on a line that is only a ``` (optionally
# with an info string like ```bash). We track open/close to scope the scan to
# code, not prose — a docstring or issue body explaining this exact bug must
# not self-trigger.
_FENCE_RE = re.compile(r"^\s*```(\S*)")
# Languages worth scanning. An untagged fence (empty info string) is included
# because several skills in this repo write bash recipes in bare ``` fences.
_SHELL_LANGS = {"", "bash", "sh", "shell", "zsh"}
# A POSIX `[ ... ]` test containing an escaped `\<` or `\>` — the bash-only
# string-comparison operator this lint exists to catch. Matched per-line
# (the operator and its brackets are always on one physical line in the
# skills authored so far); `.*?` keeps it non-greedy so `[ a ] ... [ \< ]`
# on one line still isolates the offending bracket pair.
_BASH_ONLY_OP_RE = re.compile(r"\[[^][]*?\\[<>][^][]*?\]")


class Violation:
    """One bash-only `[ \\< ]` / `[ \\> ]` occurrence."""

    def __init__(self, path: str, lineno: int, text: str) -> None:
        self.path = path
        self.lineno = lineno
        self.text = text

    def __str__(self) -> str:
        return (
            f"{self.path}:{self.lineno}: {self.text} — bash-only `\\<`/`\\>` inside "
            f'`[ ]` errors under zsh ("condition expected: <"), which an `if` reads '
            f"as false rather than failing loudly (noorinalabs-main#1485). Use "
            f'`[ "$(printf \'%s\\n%s\\n\' "$A" "$B" | sort | head -1)" = "$A" ]` '
            f"(or a `python3 -c` comparison) instead — correct under POSIX sh, bash "
            f"and zsh alike."
        )


def check_markdown_text(path: str, text: str) -> list[Violation]:
    """Return bash-only `[ \\< ]` / `[ \\> ]` violations inside shell code blocks."""
    violations: list[Violation] = []
    lines = text.splitlines()

    in_block = False
    block_lang = ""
    block_start = 0  # 0-based index of the first content line of the open block
    for idx, raw in enumerate(lines):
        m = _FENCE_RE.match(raw)
        if m is not None:
            if not in_block:
                in_block = True
                block_lang = m.group(1).lower()
                block_start = idx + 1
            else:
                block_lines = lines[block_start:idx]
                violations.extend(_scan_block(path, block_start, block_lang, block_lines))
                in_block = False
    # An unterminated block (no closing fence) still gets scanned to EOF.
    if in_block:
        block_lines = lines[block_start:]
        violations.extend(_scan_block(path, block_start, block_lang, block_lines))

    return violations


def _scan_block(path: str, start_idx: int, lang: str, block_lines: list[str]) -> list[Violation]:
    """Scan one fenced block for the bash-only operator, if it's a shell block.

    A shell-comment line (stripped text starting with `#`) is skipped — a
    code comment *explaining* the operator (exactly like this lint's own
    fix commentary in `wave-kickoff/SKILL.md`) must not self-trigger. Same
    exclusion `pre_commit_ci_sync.py`'s `_classify_run` uses for `run:`
    block scalars.
    """
    if lang not in _SHELL_LANGS:
        return []
    found: list[Violation] = []
    for offset, line in enumerate(block_lines):
        if line.strip().startswith("#"):
            continue
        if _BASH_ONLY_OP_RE.search(line):
            # start_idx is 0-based content start; +offset for the line, +1 to 1-base.
            found.append(Violation(path, start_idx + offset + 1, line.strip()))
    return found


def check_file(path: Path) -> list[Violation]:
    return check_markdown_text(str(path), path.read_text(encoding="utf-8"))


def main(argv: list[str]) -> int:
    paths = argv[1:]
    if not paths:
        print(
            "usage: lint_skill_bash_dialect.py <file.md> [<file.md> ...]",
            file=sys.stderr,
        )
        return 2

    all_violations: list[Violation] = []
    for p in paths:
        path = Path(p)
        if not path.is_file():
            print(f"ERROR: not a file: {p}", file=sys.stderr)
            return 2
        all_violations.extend(check_file(path))

    if all_violations:
        print("Bash-only `[ \\< ]` / `[ \\> ]` operator violations (noorinalabs-main#1485):")
        for v in all_violations:
            print(f"  {v}")
        return 1

    print("OK: no bash-only `[ \\< ]` / `[ \\> ]` operator found.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
