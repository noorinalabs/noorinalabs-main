#!/usr/bin/env python3
"""PostToolUse dispatcher: Single entry point for all PostToolUse hooks.

Mirrors `dispatcher.py` (the PreToolUse Bash dispatcher) for the
PostToolUse phase. Routes by matcher (Bash, Edit, Write, NotebookEdit) so
all PostToolUse hooks run in-process per tool call instead of via N
separate `python3` subprocess invocations.

Each PostToolUse hook module exposes:
    check(input_data: dict) -> dict | None
        Returns None for no-op (hook didn't apply or had no advisory to
        emit). Returns a dict with `systemMessage` to surface an advisory
        message through the harness. Other keys (`action`, etc.) are
        recorded for diagnostics but not surfaced.

Unlike PreToolUse, PostToolUse hooks CANNOT block the tool — it already
ran. The dispatcher runs every registered module for the matcher and
aggregates any `systemMessage` fields into a single advisory output.
Exit code is always 0; the dispatcher never blocks. If an individual hook
raises an unhandled exception, the dispatcher swallows it (fail-open,
mirroring `dispatcher.py`).

Input Language:
  Fires on:      PostToolUse Bash | Edit | Write | NotebookEdit
  Matches:       any tool invocation whose `tool_name` is a key in
                 `_REGISTRY` (Bash, Edit, Write, NotebookEdit)
  Does NOT match: tool invocations whose matcher has no registered modules
  Flag pass-through: stdin JSON is read once and passed verbatim to each
                     registered module's `check()` function

Exit codes:
  0 — always (PostToolUse hooks are advisory; aggregated systemMessages
      are emitted as JSON on stdout but the exit code stays 0)
"""

import importlib
import json
import sys
from pathlib import Path

# Ensure the hooks directory is on sys.path for imports
_HOOKS_DIR = Path(__file__).resolve().parent
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

# Edit and Write share the same module set today (every module that runs on
# Edit also runs on Write). Defining it once keeps the two matcher entries
# in lock-step.
_EDIT_WRITE_MODULES = [
    "ontology_tracker",
    "suggest_generic_prompt",
    "validate_edit_completion",
]

# Matcher → ordered list of hook-module import names.
# Order matters: cheap/local checks first, network-calling checks last
# (mirroring `dispatcher.py`'s ordering convention).
_REGISTRY: dict[str, list[str]] = {
    "Bash": [
        "annunaki_monitor",  # local: regex over stdout/stderr, JSONL append
        "auto_add_issue_to_board",  # network: runs `gh project item-add`
        "post_wave_kickoff_comment",  # network: gh fetch + post comment
        "post_label_change_wave_field_sync",  # network: GraphQL updateProjectV2ItemFieldValue
    ],
    "Edit": _EDIT_WRITE_MODULES,
    "Write": _EDIT_WRITE_MODULES,
    "NotebookEdit": [
        "validate_edit_completion",  # PostToolUse sentinel write only
    ],
}


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    modules = _REGISTRY.get(tool_name)
    if not modules:
        sys.exit(0)

    messages: list[str] = []

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
            continue  # Never let a hook crash propagate — advisory only

        if not isinstance(result, dict):
            continue

        msg = result.get("systemMessage")
        if msg:
            messages.append(str(msg))

    if messages:
        output = {"systemMessage": "\n\n".join(messages)}
        print(json.dumps(output))

    sys.exit(0)


if __name__ == "__main__":
    main()
