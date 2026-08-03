"""Shared bootstrap + builders for `.claude/hooks/tests/` (#1116).

Deliberately NOT `conftest.py`: conftest fixtures are pytest-only and are
invisible to a bare `python3 .claude/hooks/tests/test_foo.py` invocation,
which 51/54 files in this suite still support (each carries its own
`if __name__ == "__main__":` block). This module lives beside the test
files instead, so its containing directory is already importable in both
modes — pytest's rootless import mode and the interpreter's implicit
script-directory entry for direct execution both put `tests/` on
`sys.path` before any test module runs, no bootstrap required to reach
*this* module.

Importing this module has the side effect of putting the hooks dir and
the lib dir on `sys.path`, replacing the ~3-5 line `_HERE`/`_HOOKS_DIR`/
`sys.path.insert(...)` preamble duplicated across the majority of files
in this suite. Callers reference everything through the module (`import
__test_helpers` + `__test_helpers.HOOKS_DIR` / `.bash_input(...)`)
rather than `from __test_helpers import X` — deliberately: a bare `import
__test_helpers` whose only job is its sys.path side effect is genuinely
unused by ruff's F401 reading (suppressed with `# noqa: F401`, never
autofix-deleted), whereas `from __test_helpers import X as Y` gets
resorted by ruff's isort autofix into the "from-import" group, which
sorts AFTER every `import hook_module` line — silently moving the
sys.path setup after the import that needs it. Caught in review via a
standalone per-file `--collect-only` sweep (running the whole suite
together masked it: an earlier-collected file had already put the dirs
on `sys.path`, so the broken ordering was invisible in a combined run).

The double leading underscore in this module's own name is also
load-bearing, not decorative: it makes `__test_helpers` sort
alphabetically before every underscore-prefixed hook-side import in this
suite (`_shell_parse`, `_repo_flag_parse`, `_consultation_sentinel`, …) —
a single leading underscore does not, since e.g. `_shell_parse` (`s`)
sorts before `_test_helpers` (`t`). Renaming a hook module is out of
scope; renaming this module is not.
"""

from __future__ import annotations

import sys
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent.parent
LIB_DIR = HOOKS_DIR.parent / "lib"

for _dir in (HOOKS_DIR, LIB_DIR):
    _dir_str = str(_dir)
    if _dir_str not in sys.path:
        sys.path.insert(0, _dir_str)


def bash_input(command: str, cwd: str | None = None) -> dict:
    """Build a Bash tool_input payload for a hook's `check()`/`main()`.

    Mirrors the `{"tool_name": "Bash", "tool_input": {"command": ...}}`
    shape that was duplicated — byte-for-byte, modulo a local variable
    name — across 30 `_input()` builders before #1116. `cwd` is omitted
    from the payload entirely when not given, matching every duplicate's
    behavior (callers that need `cwd` unconditionally present, or a
    non-None default, keep their own local `_input` — see the file-level
    docstrings in test_validate_branch_freshness.py for the two that do).
    """
    payload: dict = {"tool_name": "Bash", "tool_input": {"command": command}}
    if cwd is not None:
        payload["cwd"] = cwd
    return payload
