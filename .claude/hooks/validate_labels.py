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

Tokenization (main#1351 — the shared-finder rewrite):
  The command is normalized, tokenized, split into pipeline segments, and only
  the segments that ARE a `gh issue create` invocation are scanned for label
  flags. Everything is done through `_shell_parse`'s finders rather than a
  private grammar — the #663 / #1150 invariant this hook was named in the
  umbrella for violating.

  Three passes run before tokenization, each closing one measured defect:

    strip_data_heredocs           A `cat > file <<'BODY' … BODY` body is DATA
                                  fed to a sink, not an option list (#1174's
                                  code-vs-data class). Scanning it treated the
                                  `bash -lc` in a shell-parsing write-up as
                                  `-l c` and minted a label named `c` — twice
                                  in wave-29, both false blocks.
    normalize_command_substitutions
                                  `url=$(gh issue create … --label meta-issue)`
                                  glues the closing paren onto the last
                                  argument, so the hook demanded a label named
                                  `meta-issue)` and blocked the filing of
                                  #1150 itself.
    normalize_command_separators  Newlines / `;` / `|` become real separator
                                  tokens, without which a multi-line command
                                  collapses into one segment headed by `cd`
                                  and the gh invocation is never found.

  Segment scoping is what makes the label scan sound: a `-lc` (or a documented
  `--label ghost`) anywhere OUTSIDE the `gh issue create` segment — a heredoc
  body, a sibling command, a `--body` value — cannot contribute a label,
  because the scan never looks there.

Fail-open posture (deliberate, and now three-layered):
  A label-existence pre-flight is best-effort — `gh` itself rejects a genuinely
  missing label server-side — whereas a false block stops valid work. So the
  hook skips validation rather than blocking whenever the parse is not
  trustworthy: on shlex failure (#661), when no `gh issue create` segment is
  found, and — main#1351 — when an extracted label carries a shell
  metacharacter, which is evidence of a mis-parse, not of a missing label. The
  last case surfaces a systemMessage rather than passing silently.

Exit codes:
  0 — allow (not gh issue create, or all labels exist)
  2 — block (missing labels detected)
"""

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hook_main import run_blocking
from _repo_flag_parse import extract_repo  # noqa: E402
from _shell_parse import (  # noqa: E402
    find_gh_subcommand,
    iter_command_segments,
    normalize_command_separators,
    normalize_command_substitutions,
    strip_data_heredocs,
    tokenize,
    walk_flag_values,
)
from annunaki_log import log_pretooluse_block  # noqa: E402

# Flags whose VALUE is a label list (comma-separated allowed by gh).
_LABEL_FLAGS = {"--label", "-l"}

# Characters that cannot appear in a correctly-parsed label token. A GitHub
# label may contain spaces, unicode, emoji and most punctuation — `good first
# issue` is a real default label — so this set is deliberately restricted to
# SHELL metacharacters, whose presence means the tokenizer, not the user, put
# them there. Both wave-29 defect families land here (`meta-issue)`, `` c` ``),
# which is why this stays as a backstop even though the parse fixes above
# remove the two known producers.
_SHELL_METACHARS = frozenset("()`$;|&<>\n\r\\")


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


def issue_create_segments(command: str) -> list[list[str]] | None:
    """Post-verb tokens of every real `gh issue create` invocation in `command`.

    Returns None when the command cannot be tokenized (shlex failure — the
    #661 fail-open), and `[]` when it tokenizes but holds no `gh issue create`
    invocation. Each returned list is the segment's tokens AFTER the
    `issue create` verbs, ready for `walk_flag_values`.

    Normalization order matters and is not interchangeable:

      1. `strip_data_heredocs` FIRST, so an inert heredoc body is gone before
         anything tries to read shell structure out of prose. Bodies fed to an
         interpreter are deliberately kept — those really are code.
      2. `normalize_command_substitutions`, so `$( … )` / backtick / subshell
         boundaries become separators instead of being glued to the tokens on
         either side.
      3. `normalize_command_separators` LAST, because steps 1–2 can expose
         newlines and `;`/`|` that were previously inside a body or a
         substitution, and this pass is what turns them into standalone tokens
         `iter_command_segments` can split on.
    """
    # Cheap exact early-out. `find_gh_subcommand` matches only a literal `gh`
    # token, so a command with no `gh` substring cannot produce a segment —
    # this skips the normalization + shlex work for the overwhelming majority
    # of Bash calls without weakening the match by one command. (Indirection
    # like `g=gh; $g issue create` is not resolved either way: the finder needs
    # a literal `gh` in command position.)
    if "gh" not in command:
        return []
    text = strip_data_heredocs(command)
    text = normalize_command_substitutions(text)
    text = normalize_command_separators(text)
    tokens = tokenize(text)
    if tokens is None:
        return None

    found: list[list[str]] = []
    for segment in iter_command_segments(tokens):
        gh = find_gh_subcommand(segment)
        if gh is None:
            continue
        _gh_globals, rest = gh
        if rest[:2] == ["issue", "create"]:
            found.append(rest[2:])
    return found


def _extract_labels(command: str) -> tuple[list[str], str | None]:
    """`(labels, skip_reason)` — the full result `extract_labels` narrows.

    `skip_reason` is None on a trustworthy parse. It is a human-readable
    explanation when a label token carried a shell metacharacter, in which
    case `labels` is emptied: the right response to "the tokenizer produced
    `meta-issue)`" is to distrust the whole parse, not to demand that the user
    create a label named `meta-issue)`. Returned separately from
    `extract_labels` so `check` can SAY it skipped instead of failing open in
    silence — a gate that quietly stops gating is the failure mode this hook's
    own history is made of.
    """
    segments = issue_create_segments(command)
    if segments is None:
        return [], None

    labels: list[str] = []
    for rest in segments:
        for raw in walk_flag_values(rest, _LABEL_FLAGS):
            for value in raw.split(","):
                label = value.strip()
                if label:
                    labels.append(label)

    suspect = [label for label in labels if _SHELL_METACHARS.intersection(label)]
    if suspect:
        rendered = ", ".join(repr(label) for label in suspect)
        return [], f"parsed label token(s) carrying a shell metacharacter: {rendered}"
    return labels, None


def extract_labels(command: str) -> list[str]:
    """Label names passed via --label / -l to a `gh issue create` in `command`.

    Scoped to real `gh issue create` segments (main#1351): a `--label` inside
    another command in the same string, inside a data heredoc body, or inside
    another flag's value is NOT a label. Comma-separated values within one flag
    are split. Returns `[]` — the gate then ALLOWS — whenever the parse is not
    trustworthy; see the module docstring's fail-open posture.
    """
    return _extract_labels(command)[0]


def check(input_data: dict) -> dict | None:
    """Check labels on gh issue create. Returns result dict if blocking/warning, None if allowed."""
    tool_name = input_data.get("tool_name", "")
    if tool_name != "Bash":
        return None

    command = input_data.get("tool_input", {}).get("command", "")

    labels, skip_reason = _extract_labels(command)
    if skip_reason is not None:
        return {
            "decision": "allow",
            "systemMessage": (
                f"NOTE: validate_labels skipped label validation — {skip_reason}. "
                "A shell metacharacter in a label token is evidence this hook "
                "mis-parsed the command, not evidence of a missing label, so no "
                "block is raised. `gh` still rejects a genuinely missing label "
                "server-side. Please report the command shape (main#1351)."
            ),
        }
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
    run_blocking(check, "validate_labels")


if __name__ == "__main__":
    main()
