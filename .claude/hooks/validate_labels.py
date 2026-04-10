#!/usr/bin/env python3
"""PreToolUse hook: Validate labels for gh issue create and gh label create.

1. For `gh issue create` — verifies each --label exists in the repository.
2. For `gh label create` — enforces naming convention:
   - Assignee labels (all uppercase): must match ^[A-Z][A-Z0-9_-]+$
   - All other labels: must match ^[a-z][a-z0-9-]+$ (kebab-case)
   - Wave/phase labels (e.g., p2-wave-1): allowed as kebab-case

Exit codes:
  0 — allow (not a label command, or all checks pass)
  2 — block (missing labels or naming convention violation)
"""

import json
import re
import subprocess
import sys

# Patterns for label naming convention
ASSIGNEE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_-]+$")
KEBAB_CASE_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")


def get_existing_labels() -> set[str]:
    """Fetch all existing labels from the repository."""
    try:
        result = subprocess.run(
            ["gh", "label", "list", "--limit", "500", "--json", "name"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return set()
        labels_data = json.loads(result.stdout)
        return {label["name"] for label in labels_data}
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return set()


def extract_labels(command: str) -> list[str]:
    """Extract all --label and -l values from a gh issue create command."""
    labels = []

    # Match --label "value" or --label value or -l "value" or -l value
    # Also handles comma-separated labels in a single --label flag
    for match in re.finditer(r'(?:--label|-l)\s+["\']?([^"\']+?)["\']?(?:\s|$)', command):
        raw = match.group(1).strip()
        # gh CLI accepts comma-separated labels
        for label in raw.split(","):
            label = label.strip()
            if label:
                labels.append(label)

    return labels


def extract_label_create_name(command: str) -> str | None:
    """Extract the label name from a gh label create command.

    Handles: gh label create "name", gh label create 'name', gh label create name
    """
    match = re.search(
        r"\bgh\s+label\s+create\s+[\"']([^\"']+)[\"']",
        command,
    )
    if match:
        return match.group(1).strip()
    match = re.search(
        r"\bgh\s+label\s+create\s+(\S+)",
        command,
    )
    if match:
        name = match.group(1).strip()
        # Exclude flags like --color, --description
        if name.startswith("-"):
            return None
        return name
    return None


def validate_label_convention(label_name: str) -> str | None:
    """Validate label name against naming convention.

    Returns None if valid, or an error message if invalid.
    """
    # Check if it looks like an assignee label (starts with uppercase)
    if label_name[0].isupper():
        if ASSIGNEE_PATTERN.match(label_name):
            return None
        return (
            f"Assignee label '{label_name}' must be UPPER_SNAKE_CASE "
            f"(pattern: ^[A-Z][A-Z0-9_-]+$). "
            f"Example: WANJIKU_MWANGI, SANTIAGO_FERREIRA"
        )

    # All other labels must be kebab-case
    if KEBAB_CASE_PATTERN.match(label_name):
        return None
    return (
        f"Label '{label_name}' must be kebab-case "
        f"(pattern: ^[a-z][a-z0-9-]*$). "
        f"Example: tech-debt, p2-wave-1, bug"
    )


def handle_issue_create(command: str) -> None:
    """Validate labels exist before gh issue create."""
    labels = extract_labels(command)
    if not labels:
        sys.exit(0)

    existing = get_existing_labels()
    if not existing:
        result = {
            "decision": "allow",
            "systemMessage": (
                "WARNING: Could not fetch existing labels to validate. "
                "Proceeding without validation. Run `gh label list` to verify."
            ),
        }
        print(json.dumps(result))
        sys.exit(0)

    missing = [label for label in labels if label not in existing]
    if not missing:
        sys.exit(0)

    suggestions = "\n".join(
        f'  gh label create "{label}"' for label in missing
    )
    result = {
        "decision": "block",
        "reason": (
            f"BLOCKED: The following label(s) do not exist: {', '.join(missing)}\n"
            f"Create them first:\n{suggestions}\n\n"
            "See charter § GitHub Label Hygiene: verify labels exist before creating issues."
        ),
    }
    print(json.dumps(result))
    sys.exit(2)


def handle_label_create(command: str) -> None:
    """Validate naming convention for gh label create."""
    label_name = extract_label_create_name(command)
    if not label_name:
        sys.exit(0)

    error = validate_label_convention(label_name)
    if error is None:
        sys.exit(0)

    result = {
        "decision": "block",
        "reason": (
            f"BLOCKED: Label naming convention violation.\n{error}\n\n"
            "Convention: assignee labels use UPPER_SNAKE_CASE, "
            "all other labels use kebab-case.\n"
            "See charter § Label Naming Convention."
        ),
    }
    print(json.dumps(result))
    sys.exit(2)


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    if tool_name != "Bash":
        sys.exit(0)

    command = input_data.get("tool_input", {}).get("command", "")

    # Check for gh label create (naming convention enforcement)
    if re.search(r"\bgh\s+label\s+create\b", command):
        handle_label_create(command)

    # Check for gh issue create (label existence validation)
    if re.search(r"\bgh\s+issue\s+create\b", command):
        handle_issue_create(command)

    sys.exit(0)


if __name__ == "__main__":
    main()
