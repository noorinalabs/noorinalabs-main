#!/usr/bin/env python3
"""PreToolUse dispatcher: Single entry point for all Bash PreToolUse hooks.

Instead of 12 separate subprocess invocations per Bash tool call, this
dispatcher runs all hook checks in-process by importing each hook module
and calling its `check()` function.

Each hook module exposes:
    check(input_data: dict) -> dict | None
        Returns None to allow, or a dict with "decision" and "reason"/"systemMessage".

The active module list + order is read from the framework config
(``hooks.pre_bash`` in ``.claude/framework.config.json``), so enabling,
disabling, or reordering a check is a config edit rather than a code change.
The loader fails open to the full default list, so a missing/corrupt config
still dispatches every gate. Order matters: cheap/local checks first (e.g.
smart_grep_ontology routes a symbol search before the block_bare_grep backstop,
#1017), network-calling checks last (block_squash_wave_merge resolves a PR base
via `gh pr view`).

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


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    if tool_name != "Bash":
        sys.exit(0)

    warnings: list[str] = []

    for module_name in config(input_data).get("hooks.pre_bash", []):
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
