#!/usr/bin/env python3
"""PreToolUse hook: Warn when agents are spawned without wave context or ontology.

Two checks on Agent tool calls:
1. Active wave marker in cross-repo-status.json
2. Ontology context in the agent's prompt (keyword search)

Exit codes:
  0 — always allow (warning only)
"""

import json
import sys
from pathlib import Path

_STATUS_PATH = Path(__file__).resolve().parent.parent.parent / "cross-repo-status.json"

# Keywords that indicate ontology librarian output was included in the prompt
_ONTOLOGY_MARKERS = [
    "## Ontology Context",
    "**Ontology:",
    "ontology librarian",
    "/ontology-librarian",
    "**Entities:**",
    "**Services:**",
    "Ontology is current",
    "Ontology has",
    "ontology/",
]


def has_active_wave() -> bool:
    """Check if cross-repo-status.json indicates an active wave."""
    try:
        data = json.loads(_STATUS_PATH.read_text(encoding="utf-8"))
        if data.get("wave_active"):
            return True
        if data.get("current_wave"):
            return True
        return False
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return False


def has_ontology_context(prompt: str) -> bool:
    """Check if the agent prompt contains ontology context."""
    prompt_lower = prompt.lower()
    return any(marker.lower() in prompt_lower for marker in _ONTOLOGY_MARKERS)


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    if tool_name != "Agent":
        sys.exit(0)

    tool_input = input_data.get("tool_input", {})
    prompt = tool_input.get("prompt", "")

    warnings = []

    if not has_active_wave():
        warnings.append(
            "No active wave context detected in cross-repo-status.json. "
            "Run `/wave-kickoff` to set up wave context before spawning agents."
        )

    if prompt and not has_ontology_context(prompt):
        warnings.append(
            "Agent prompt does not contain ontology context. "
            "Per charter, the orchestrator MUST run `/ontology-librarian {topic}` "
            "and include the output in the agent's spawn prompt before any code changes. "
            "This prevents assigning stale issues and ensures domain context."
        )

    if warnings:
        result = {
            "decision": "allow",
            "systemMessage": "WARNING: " + " | ".join(warnings),
        }
        print(json.dumps(result))

    sys.exit(0)


if __name__ == "__main__":
    main()
