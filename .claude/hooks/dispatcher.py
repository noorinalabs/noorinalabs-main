#!/usr/bin/env python3
"""PreToolUse dispatcher: Single entry point for all Bash/Edit/Write/NotebookEdit
PreToolUse hooks.

Instead of one subprocess invocation per hook per tool call, this dispatcher
runs all hook checks in-process by importing each hook module and calling its
`check()` function.

Each hook module exposes:
    check(input_data: dict) -> dict | None
        Returns None to allow, or a dict with "decision" and "reason"/"systemMessage".

Matcher → the framework-config ``hooks.<event>`` key whose ordered module list
runs for that tool (mirrors `post_dispatcher.py`'s `_MATCHER_CFG_KEY`, the
PostToolUse sibling):

    Bash          -> hooks.pre_bash
    Edit          -> hooks.pre_file
    Write         -> hooks.pre_file   (shares the list with Edit)
    NotebookEdit  -> hooks.pre_notebook

The active module list + order per matcher is read from the framework config
(``.claude/framework.config.json``), so enabling, disabling, or reordering a
check is a config edit rather than a code change. The loader fails open to the
full default list, so a missing/corrupt config still dispatches every gate.
Order matters within ``pre_bash``: cheap/local checks first (e.g.
smart_grep_ontology routes a symbol search before the block_bare_grep backstop,
#1017), network-calling checks last (block_squash_wave_merge resolves a PR base
via `gh pr view`).

A tool_name with no entry in the matcher table (e.g. `Read`) dispatches
nothing and exits 0 immediately — same "no matcher, no-op" contract as
`post_dispatcher.py`.

Exit codes:
  0 — allow (all hooks passed, or aggregated warnings)
  2 — block (first blocking hook wins)
"""

import importlib
import json
import sys
from pathlib import Path

# Ensure the hooks directory is on sys.path for imports
_HOOKS_DIR = Path(__file__).resolve().parent
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

from _framework_config import config  # noqa: E402

# Matcher -> the framework-config ``hooks.<event>`` key whose ordered module list
# runs for that tool. See the module docstring for the mapping and rationale.
_MATCHER_CFG_KEY: dict[str, str] = {
    "Bash": "hooks.pre_bash",
    "Edit": "hooks.pre_file",
    "Write": "hooks.pre_file",
    "NotebookEdit": "hooks.pre_notebook",
}


def _modules_for(tool_name: str, input_data: dict | None = None) -> list[str]:
    """Resolve the ordered hook-module list for ``tool_name`` from the framework
    config. Returns ``[]`` for a tool with no registered matcher."""
    cfg_key = _MATCHER_CFG_KEY.get(tool_name)
    if cfg_key is None:
        return []
    return list(config(input_data).get(cfg_key, []))


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    modules = _modules_for(tool_name, input_data)
    if not modules:
        sys.exit(0)

    warnings: list[str] = []

    for module_name in modules:
        try:
            mod = importlib.import_module(module_name)
        except ImportError:
            continue  # Skip missing modules gracefully

        check_fn = getattr(mod, "check", None)
        if check_fn is None:
            continue

        try:
            result = check_fn(input_data)
        except Exception:
            continue  # Never let a hook crash block everything

        if result is None:
            continue

        decision = result.get("decision", "allow")

        if decision == "block":
            # First blocker wins — print and exit immediately
            print(json.dumps(result))
            sys.exit(2)

        # Collect warnings/systemMessages from allow decisions
        msg = result.get("systemMessage", "")
        if msg:
            warnings.append(msg)

    # No blockers — emit aggregated warnings if any
    if warnings:
        result = {
            "decision": "allow",
            "systemMessage": "\n\n".join(warnings),
        }
        print(json.dumps(result))

    sys.exit(0)


if __name__ == "__main__":
    main()
