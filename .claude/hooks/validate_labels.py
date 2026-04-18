#!/usr/bin/env python3
"""PreToolUse hook: Validate labels before gh issue create.

Extracts --label values from `gh issue create` commands and verifies each
label exists in the target repository. Blocks execution if any label is missing.

Input Language:
  Fires on:      PreToolUse Bash
  Matches:       gh issue create [--repo {OWNER/REPO}] [--label {L} | -l {L} | --label={L}]... [--body {TEXT}] [...]
  Does NOT match:
    - gh issue list / view / edit / close
    - Commands where `--label foo` appears only inside a `--body "..."` argument value
      (e.g., documentation bodies referencing gh commands as prose)
    - Non-`gh issue create` subcommands
  Flag pass-through:
    --repo {OWNER/REPO}  → forwarded to `gh label list --repo ...` so labels are
                           resolved against the TARGET repo, not the cwd repo
    --label / -l         → extracted as label values (comma-split supported)
    --body / -b / -F     → values are NOT scanned for nested flags (tokenized
                           via shlex so body content is a single token)

Exit codes:
  0 — allow (not gh issue create, or all labels exist)
  2 — block (missing labels detected)
"""

import json
import os
import re
import shlex
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from annunaki_log import log_pretooluse_block


def _tokenize(command: str) -> list[str] | None:
    """Shell-tokenize a command. Returns None if the command is malformed."""
    try:
        return shlex.split(command, posix=True)
    except ValueError:
        return None


def _find_issue_create_tokens(tokens: list[str]) -> list[str] | None:
    """Return the argv slice for the `gh issue create` invocation, or None.

    Handles pipelines/chains by scanning for the `gh issue create` triplet and
    returning tokens from that point until the next shell separator. Separators
    that shlex.split will emit as their own tokens: ``|``, ``||``, ``&&``, ``;``,
    ``&``. (shlex in posix mode keeps these as single tokens when unquoted.)
    """
    separators = {"|", "||", "&&", ";", "&"}
    n = len(tokens)
    for i in range(n - 2):
        if tokens[i] == "gh" and tokens[i + 1] == "issue" and tokens[i + 2] == "create":
            end = i + 3
            while end < n and tokens[end] not in separators:
                end += 1
            return tokens[i + 3 : end]
    return None


# Flags whose immediate next token is a value that must NOT be scanned for
# nested label flags. Body text is the primary source of false-positives.
_VALUE_FLAGS_TO_SKIP = {"--body", "-b", "--body-file", "-F", "--title", "-t"}

# Label flag names (space-separated form).
_LABEL_FLAGS = {"--label", "-l"}


def extract_labels(command: str) -> list[str]:
    """Extract --label / -l values from a gh issue create command.

    Uses shell tokenization so values inside quoted arguments (notably `--body`)
    are not scanned for flags. Supports ``--label foo``, ``-l foo``,
    ``--label=foo``, and comma-separated lists (``--label a,b,c``).
    """
    tokens = _tokenize(command)
    if tokens is None:
        return []

    create_tokens = _find_issue_create_tokens(tokens)
    if create_tokens is None:
        return []

    labels: list[str] = []
    i = 0
    n = len(create_tokens)
    while i < n:
        tok = create_tokens[i]

        # --label=value / -l=value (attached form)
        if tok.startswith("--label=") or tok.startswith("-l="):
            _, _, value = tok.partition("=")
            labels.extend(_split_label_value(value))
            i += 1
            continue

        # --label value / -l value (separate form)
        if tok in _LABEL_FLAGS:
            if i + 1 < n:
                labels.extend(_split_label_value(create_tokens[i + 1]))
            i += 2
            continue

        # Skip value of flags whose arguments must not be scanned.
        if tok in _VALUE_FLAGS_TO_SKIP:
            i += 2
            continue
        if any(tok.startswith(f + "=") for f in _VALUE_FLAGS_TO_SKIP):
            i += 1
            continue

        i += 1

    return labels


def _split_label_value(raw: str) -> list[str]:
    """Split a raw --label argument on commas, stripping whitespace and empties."""
    return [part.strip() for part in raw.split(",") if part.strip()]


def extract_repo(command: str) -> str | None:
    """Extract --repo / -R value from a gh issue create command.

    Returns ``OWNER/REPO`` (or a URL that gh accepts) or None if absent. Only
    reads the flag from the `gh issue create` argv slice — never from body text.
    """
    tokens = _tokenize(command)
    if tokens is None:
        return None
    create_tokens = _find_issue_create_tokens(tokens)
    if create_tokens is None:
        return None

    n = len(create_tokens)
    for i, tok in enumerate(create_tokens):
        if tok == "--repo" or tok == "-R":
            if i + 1 < n:
                return create_tokens[i + 1]
            return None
        if tok.startswith("--repo="):
            return tok.split("=", 1)[1]
        if tok.startswith("-R="):
            return tok.split("=", 1)[1]
    return None


def get_existing_labels(repo: str | None = None) -> set[str]:
    """Fetch all existing labels from the repository.

    When ``repo`` is provided, forwards ``--repo`` to ``gh label list`` so the
    labels are resolved against the target repo instead of the cwd-resolved one.
    """
    try:
        cmd = ["gh", "label", "list", "--limit", "500", "--json", "name"]
        if repo:
            cmd.extend(["--repo", repo])
        result = subprocess.run(
            cmd,
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


def check(input_data: dict) -> dict | None:
    """Check labels on gh issue create. Returns result dict if blocking/warning, None if allowed."""
    tool_name = input_data.get("tool_name", "")
    if tool_name != "Bash":
        return None

    command = input_data.get("tool_input", {}).get("command", "")

    if not re.search(r"\bgh\s+issue\s+create\b", command):
        return None

    labels = extract_labels(command)
    if not labels:
        return None

    repo = extract_repo(command)
    existing = get_existing_labels(repo)
    if not existing:
        return {
            "decision": "allow",
            "systemMessage": (
                "WARNING: Could not fetch existing labels to validate. "
                "Proceeding without validation. Run `gh label list` to verify."
            ),
        }

    missing = [label for label in labels if label not in existing]
    if not missing:
        return None

    repo_hint = f" --repo {repo}" if repo else ""
    suggestions = "\n".join(f'  gh label create "{label}"{repo_hint}' for label in missing)
    result = {
        "decision": "block",
        "reason": (
            f"BLOCKED: The following label(s) do not exist: {', '.join(missing)}\n"
            f"Create them first:\n{suggestions}\n\n"
            "See charter § GitHub Label Hygiene: verify labels exist before creating issues."
        ),
    }
    log_pretooluse_block("validate_labels", command, result["reason"])
    return result


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    result = check(input_data)
    if result is None:
        sys.exit(0)
    print(json.dumps(result))
    if result.get("decision") == "block":
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
