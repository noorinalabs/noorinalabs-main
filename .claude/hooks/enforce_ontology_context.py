#!/usr/bin/env python3
"""PreToolUse hook: Require ontology context in Agent spawn prompts.

Blocks Agent tool calls for implementation agents (worktree isolation)
unless the prompt contains ontology context markers, indicating the
orchestrator ran /ontology-librarian before spawning.

Exit codes:
  0 — allow (not an Agent call, or ontology context present)
  2 — block (implementation agent spawned without ontology context)
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from annunaki_log import log_pretooluse_block

# Markers that indicate ontology context was included in the prompt.
ONTOLOGY_MARKERS = [
    "Ontology Status",
    "ontology is current",
    "files pending resolution",
    "ontology/domain.yaml",
    "ontology/services.yaml",
    "ontology/conventions.md",
    "## Ontology Context",
]


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    if tool_name != "Agent":
        sys.exit(0)

    tool_input = input_data.get("tool_input", {})
    isolation = tool_input.get("isolation", "")
    prompt = tool_input.get("prompt", "")

    # Only enforce for worktree-isolated agents (implementation agents).
    # Non-isolated agents (research, exploration) don't need ontology context.
    if isolation != "worktree":
        sys.exit(0)

    # Check if any ontology marker is present in the prompt
    prompt_lower = prompt.lower()
    for marker in ONTOLOGY_MARKERS:
        if marker.lower() in prompt_lower:
            sys.exit(0)

    result = {
        "decision": "block",
        "reason": (
            "BLOCKED: Implementation agent spawned without ontology context.\n"
            "The charter requires: 'Every agent MUST consult /ontology-librarian "
            "{topic} before making code changes.'\n\n"
            "Before spawning, run `/ontology-librarian {topic}` and include "
            "the output in the agent's prompt under a '## Ontology Context' heading."
        ),
    }
    print(json.dumps(result))
    log_pretooluse_block("enforce_ontology_context", prompt[:200], result["reason"])
    sys.exit(2)


if __name__ == "__main__":
    main()
