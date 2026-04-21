#!/usr/bin/env python3
"""PreToolUse hook: Validate labels before gh issue create.

Extracts --label values from `gh issue create` commands and verifies each
label exists in the repository. Blocks execution if any label is missing.

Input Language:
  Fires on:      PreToolUse Bash
  Matches:       gh issue create [--repo {OWNER/REPO} | -R {OWNER/REPO}]
                                 [--label {NAME} | -l {NAME}]... [other flags]
  Does NOT match: gh issue list, gh issue view, gh issue edit, gh label create,
                  gh pr create. Also does NOT match `--label` substrings that
                  appear INSIDE the value of another flag (e.g. inside `--body`)
                  — see Bug 2 below.
  Flag pass-through:
    --repo / -R   → forwarded to `gh label list` so we query the same repo
                    the user is creating the issue in (Bug 1 fix). Without
                    this, cwd determines which repo's labels are checked,
                    which rejects valid labels when cwd != target repo.
    --label / -l  → only the actual flag values are extracted as labels;
                    comma-separated values inside one flag are split. Body
                    content is NEVER scanned for labels (Bug 2 fix).

Tokenization:
  The command is split with `shlex.split(..., posix=True)` so quoted argument
  values become single tokens. We then walk the token list and only treat a
  token as a label/repo if the PRECEDING token is the corresponding flag.
  This guarantees that text appearing inside a `--body "..."` heredoc/string
  cannot leak into label or repo extraction.

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

# Flags whose VALUE is a label list (comma-separated allowed by gh).
_LABEL_FLAGS = {"--label", "-l"}

# Flags whose VALUE is a repo specifier (OWNER/REPO).
_REPO_FLAGS = {"--repo", "-R"}


def _tokenize(command: str) -> list[str] | None:
    """Tokenize a shell command via shlex. Return None if it cannot be parsed."""
    try:
        return shlex.split(command, posix=True)
    except ValueError:
        return None


def _is_gh_issue_create(tokens: list[str]) -> bool:
    """Return True if tokens contain a `gh issue create` invocation."""
    for i in range(len(tokens) - 2):
        if tokens[i] == "gh" and tokens[i + 1] == "issue" and tokens[i + 2] == "create":
            return True
    return False


def _walk_flags(tokens: list[str], wanted: set[str]) -> list[str]:
    """Return values for wanted flag names, only when they appear as flags.

    A token is treated as a wanted-flag value only if the immediately
    preceding token is exactly one of `wanted` (e.g. `--label`). The
    `--flag=value` form is also handled. Values inside other flags
    (e.g. inside the value of `--body`) are ignored because they are a
    SINGLE shlex token, never preceded by a flag from `wanted`.
    """
    values: list[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in wanted:
            if i + 1 < len(tokens):
                values.append(tokens[i + 1])
                i += 2
                continue
            i += 1
            continue
        matched = False
        for flag in wanted:
            if flag.startswith("--") and tok.startswith(flag + "="):
                values.append(tok[len(flag) + 1 :])
                matched = True
                break
        if matched:
            i += 1
            continue
        i += 1
    return values


def get_existing_labels(repo: str | None = None) -> set[str]:
    """Fetch all existing labels from the repository.

    When `repo` is provided (OWNER/REPO), forward it to `gh label list` so we
    query the same repo the user is creating the issue in (Bug 1 fix).
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


def extract_labels(command: str) -> list[str]:
    """Extract label names from --label / -l flags ONLY.

    Uses `shlex.split` to tokenize, then walks tokens. Quoted body content,
    code blocks, and any text that is part of another flag's value are
    treated as opaque single tokens and cannot leak into the label set
    (Bug 2 fix). Comma-separated values within a single flag are split.

    Falls back to a conservative regex on shlex parse failure (e.g. command
    contains a malformed quote). The fallback still anchors on `--label`
    appearing at a shell-token boundary.
    """
    tokens = _tokenize(command)
    if tokens is None:
        labels: list[str] = []
        for match in re.finditer(
            r'(?:^|\s)(?:--label|-l)(?:=|\s+)["\']?([^"\'\s]+)["\']?',
            command,
        ):
            raw = match.group(1).strip()
            for label in raw.split(","):
                label = label.strip()
                if label:
                    labels.append(label)
        return labels

    labels = []
    for raw in _walk_flags(tokens, _LABEL_FLAGS):
        for label in raw.split(","):
            label = label.strip()
            if label:
                labels.append(label)
    return labels


def extract_repo(command: str) -> str | None:
    """Extract the --repo / -R OWNER/REPO value from the command, if any."""
    tokens = _tokenize(command)
    if tokens is None:
        match = re.search(r"(?:^|\s)(?:--repo|-R)(?:=|\s+)(\S+)", command)
        return match.group(1) if match else None
    values = _walk_flags(tokens, _REPO_FLAGS)
    return values[0] if values else None


def check(input_data: dict) -> dict | None:
    """Check labels on gh issue create. Returns result dict if blocking/warning, None if allowed."""
    tool_name = input_data.get("tool_name", "")
    if tool_name != "Bash":
        return None

    command = input_data.get("tool_input", {}).get("command", "")

    tokens = _tokenize(command)
    if tokens is not None:
        if not _is_gh_issue_create(tokens):
            return None
    else:
        if not re.search(r"\bgh\s+issue\s+create\b", command):
            return None

    labels = extract_labels(command)
    if not labels:
        return None

    repo = extract_repo(command)
    existing = get_existing_labels(repo=repo)
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

    create_repo_flag = f" --repo {repo}" if repo else ""
    suggestions = "\n".join(f'  gh label create "{label}"{create_repo_flag}' for label in missing)
    repo_note = f" in {repo}" if repo else ""
    result = {
        "decision": "block",
        "reason": (
            f"BLOCKED: The following label(s) do not exist{repo_note}: "
            f"{', '.join(missing)}\n"
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
