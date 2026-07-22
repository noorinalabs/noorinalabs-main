#!/usr/bin/env python3
"""Assert the committed ontology/checksums.json holds no `\\u` escape sequences.

Found during the merge-gate review of PR #1040 (#1044). #1040 fixed the
escaped/literal UTF-8 flip-flop on the committed `ontology/checksums.json`
in two halves:

- **Enforced:** `.claude/hooks/ontology_tracker.py` writes with
  `json.dump(..., ensure_ascii=False)`, covered by tests that fail if the
  flag is reverted.
- **Documented only:** the `/ontology-rebuild` resolver is agent-driven, so
  the same requirement lands as a `SKILL.md` instruction (#1042 gave it a
  real `checksums_io.py` CLI to call instead of hand-rolling the write, but
  a not-yet-migrated caller, a stray scratch script, or a future manual edit
  could still write the file with the `ensure_ascii=True` default).

Neither half of that story is a code path a *committed-file* gate can watch
except by inspecting the artifact itself. This module is that gate: a
committed `checksums.json` containing a `\\u` escape sequence means SOME
writer re-escaped it — regardless of which one — and the gate is a cheap
deterministic tripwire for that regardless of the cause.

Why this catches the whole class, not just the two known writers
==================================================================
`ensure_ascii=True` (Python's `json.dump` default) is the ONLY way a `\\u`
escape sequence enters this file: the checksums.json schema never contains a
literal backslash-u in a hash, timestamp, or path — those are hex digests,
ISO-8601 timestamps, and POSIX paths, none of which produce that four-hex-digit
escape shape. So `\\u` appearing anywhere in the committed bytes is
unambiguous evidence of an `ensure_ascii=True` write, from whatever source.

CLI
===
    python3 .claude/lib/check_checksums_ascii.py [<path-to-checksums.json>]

Defaults to `ontology/checksums.json` relative to the repo root (two levels
above this file) when no path is given, matching the reusable-template CLI
shape of `check_dockerfile_base_pin.py` / `check_fixture_realism.py`.

Exit codes:
    0 — no `\\u` escape sequence found (including "file does not exist yet")
    1 — a `\\u` escape sequence was found — the writer needs
        `ensure_ascii=False`
    2 — usage / unreadable-file error
"""

from __future__ import annotations

import sys
from pathlib import Path


def check_text(path: str, text: str) -> list[str]:
    """Return violation strings for one file's contents (empty = clean).

    A bare substring search for the two ASCII characters `\\u` is
    deliberately simpler than a JSON-escape-aware scanner: `ensure_ascii=True`
    never emits a literal backslash-u pair anywhere else in this schema (see
    module docstring), so the substring check is both sufficient and immune
    to a JSON parse failure on a file that is itself the thing being
    diagnosed.
    """
    if "\\u" in text:
        count = text.count("\\u")
        return [
            f"{path}: found {count} '\\u' escape sequence(s) — a writer used the "
            "json.dump default (ensure_ascii=True) instead of "
            "ensure_ascii=False, re-escaping literal UTF-8 (#1038/#1042)"
        ]
    return []


def check_file(path: Path) -> list[str]:
    """Check one checksums.json file. A missing file is not a violation.

    Nothing has been written yet, so there is nothing to have been
    mis-escaped — that is a distinct failure mode (a missing committed
    artifact) from this gate's concern (a *present* one holding escapes).
    """
    if not path.is_file():
        return []
    return check_text(str(path), path.read_text(encoding="utf-8"))


def _default_checksums_path() -> Path:
    """`ontology/checksums.json` relative to this file's repo root."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    return repo_root / "ontology" / "checksums.json"


def main(argv: list[str]) -> int:
    paths = [Path(p) for p in argv[1:]] if len(argv) > 1 else [_default_checksums_path()]

    all_violations: list[str] = []
    for path in paths:
        all_violations.extend(check_file(path))

    if all_violations:
        print("checksums.json re-escaped — ensure_ascii convention violated:")
        for v in all_violations:
            print(f"  {v}")
        print(
            "\nWhichever writer touched this file used the ensure_ascii=True default. "
            "Route the write through .claude/lib/checksums_io.py's write_checksums() "
            "(#1042), which always writes with ensure_ascii=False."
        )
        return 1

    print("OK: checksums.json holds no '\\u' escape sequences.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
