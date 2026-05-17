#!/usr/bin/env python3
"""PreToolUse hook: Require ontology context in Agent spawn prompts.

Blocks worktree-isolated Agent tool calls unless the prompt either contains
ontology context markers (indicating the orchestrator ran
`/ontology-librarian` before spawning) OR the prompt opens with a
coordinator-class role declaration (Manager, Program Director, TPM,
Release Coordinator).

Coordinator-class exemption (#466)
==================================

Coordinators communicate via SendMessage and rarely Edit/Write directly.
Hook 15 (`enforce_librarian_consulted`) covers the Edit/Write surface for
the few cases where a coordinator does edit. Requiring ontology context in
every coordinator spawn brief adds ceremony without preventive value — and
when orchestrators forget (as in the P3W11 wave-tail re-spawn burst that
captured 8 blocks 2026-05-17 03:54Z), the hook produces noise rather than
catching real risk.

Implementer-class roles (Engineer, Tech Lead, Standards & Quality Lead,
Security Engineer, etc.) are NOT exempt — they Edit/Write code as the
primary task.

Exit codes:
  0 — allow (not an Agent call, non-worktree isolation, coordinator-class
      spawn, or ontology context present)
  2 — block (implementer-class spawn without ontology context)
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from annunaki_log import log_pretooluse_block  # noqa: E402

ONTOLOGY_MARKERS = [
    "Ontology Status",
    "ontology is current",
    "files pending resolution",
    "ontology/domain.yaml",
    "ontology/services.yaml",
    "ontology/conventions.md",
    "## Ontology Context",
]

# Canonical coordinator-class opener: `You are **{Name}**, {Role}[ for {repo}]`
# where {Role} is one of the pure-coordination titles. Bold-markdown around
# the name is optional (some shorter briefs drop it). Anchored to start so
# only the opener matches — incidental mentions of "Manager" later in the
# prompt do not exempt the spawn.
COORDINATOR_ROLE_OPENER = re.compile(
    r"^\s*You are\s+\*{0,2}[^,\n]+?\*{0,2},\s*"
    r"(Manager|Program\s+Director|TPM|Technical\s+Program\s+Manager|Release\s+Coordinator)\b",
    re.IGNORECASE,
)


def check(input_data: dict) -> dict | None:
    """Pure decision function. Returns None to allow, or a block-dict."""
    if input_data.get("tool_name", "") != "Agent":
        return None

    tool_input = input_data.get("tool_input", {})
    isolation = tool_input.get("isolation", "")
    prompt = tool_input.get("prompt", "")

    if isolation != "worktree":
        return None

    if COORDINATOR_ROLE_OPENER.search(prompt):
        return None

    prompt_lower = prompt.lower()
    for marker in ONTOLOGY_MARKERS:
        if marker.lower() in prompt_lower:
            return None

    return {
        "decision": "block",
        "reason": (
            "BLOCKED: Implementation agent spawned without ontology context.\n"
            "The charter requires: 'Every agent MUST consult /ontology-librarian "
            "{topic} before making code changes.'\n\n"
            "Before spawning, run `/ontology-librarian {topic}` and include "
            "the output in the agent's prompt under a '## Ontology Context' heading."
        ),
    }


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    result = check(input_data)
    if result is None:
        sys.exit(0)

    print(json.dumps(result))
    prompt = input_data.get("tool_input", {}).get("prompt", "")
    log_pretooluse_block("enforce_ontology_context", prompt[:200], result["reason"])
    sys.exit(2)


if __name__ == "__main__":
    main()
