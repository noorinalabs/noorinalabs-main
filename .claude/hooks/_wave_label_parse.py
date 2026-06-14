#!/usr/bin/env python3
"""Shared parser for `gh issue edit <num> --add-label|--remove-label "p{N}-wave-{M}"`.

Background
==========

Two PostToolUse hooks need to recognize the wave-label-change command shape:

- `post_wave_kickoff_comment.py` — posts a charter-format kickoff comment when
  a `p{N}-wave-{M}` label is APPLIED.
- `post_label_change_wave_field_sync.py` — syncs the project 2 Wave field
  whenever a `p{N}-wave-{M}` label is added OR removed.

Both hooks tokenize the bash command via `_shell_parse` and walk pipeline
segments looking for `gh issue edit ... --add-label|--remove-label "p{N}-wave-{M}"`.
Duplicating that parser in each hook would re-introduce the regression class
the `_shell_parse` consolidation closed in P3W4 (#226 #227 #223 #216 #188
#189 #144). This helper consolidates the wave-label-specific shape on top of
the general `_shell_parse` primitives.

Public API
==========

    parse_wave_label_changes(command: str) -> list[WaveLabelChange]
        Parse a bash command. Returns a list of `WaveLabelChange` objects,
        one per `gh issue edit ... --add-label|--remove-label "p{N}-wave-{M}"`
        invocation found across ALL pipeline segments (handles for-loops,
        `&&`-chains, `;`-separated and newline-separated multi-command Bash).
        Returns an empty list if no wave-label change is present.

        This is the multi-cmd-aware shape required by issue #455: a single
        Bash tool call may contain multiple `gh issue edit` invocations
        (commonly via for-loops in batch operations), and ALL of them
        should drive Wave-field syncs.

    parse_wave_label_change(command: str) -> WaveLabelChange | None
        Back-compat singular form: returns the FIRST `WaveLabelChange`
        found, or None. Used by `post_wave_kickoff_comment.py` which
        treats multi-cmd as out-of-pattern (kickoff is single-cmd only).

        Result fields (shared with the plural form):
          repo          — `noorinalabs-<name>` short form (last path segment
                          of `--repo owner/name` or `--repo=owner/name`), or
                          None when `--repo` is OMITTED (in-repo invocation,
                          ambient gh resolution — #650). The consuming hook
                          resolves the None case from the invocation cwd.
          issue_number  — the bare positional issue number after `edit`.
          add_label     — the FIRST `--add-label "p{N}-wave-{M}"` value, or
                          None if no add operation present.
          remove_label  — the FIRST `--remove-label "p{N}-wave-{M}"` value,
                          or None if no remove operation present.

        At least one of `add_label` / `remove_label` is non-None when the
        function returns a result; otherwise it returns None.

    is_wave_label(value: str) -> bool
        True if `value` matches the canonical wave-label shape
        `p{N}-wave-{M}` exactly (anchored). Used by callers that already
        have a string and want a yes/no check without re-parsing.

    parse_wave_label(value: str) -> tuple[int, int] | None
        Parse a wave-label string into (phase_num, wave_num). Returns None
        if `value` is not a canonical wave label.

Anchoring decision
==================

`p3-wave-10` matches; `p3-wave-10-special` does NOT match. The regex is
fully-anchored (`^p(\\d+)-wave-(\\d+)$`) so suffixed labels like
`p3-wave-10-special` or `p3-wave-10-frozen` are out of scope for the
field-sync trigger. Rationale: only canonical wave labels drive the Wave
field; arbitrary `-suffix` variants are out-of-pattern for the project 2
Wave single-select field and should not auto-mutate it.

Why a separate helper, not a method on `_shell_parse`
=====================================================

`_shell_parse` is the general bash-tokenizer primitive (segment split,
heredoc strip, flag-value walk). `_wave_label_parse` is the
wave-label-specific shape: it knows about `gh issue edit`, `--add-label`,
`--remove-label`, the `p{N}-wave-{M}` label grammar, and the `--repo`
short-name extraction. Mixing the two concerns into `_shell_parse` would
couple the general primitive to a domain shape that only two hooks need.

Promotion provenance
====================

Extracted from `post_wave_kickoff_comment.py` `parse_label_apply_command`
during Hook 21 (`post_label_change_wave_field_sync`) implementation
(P3W10 retro proposal #3, issue #445). The extraction is
behavior-preserving for `post_wave_kickoff_comment` (the kickoff hook
ignores the `remove_label` field and only acts on `add_label`); the new
field-sync hook uses both `add_label` and `remove_label` to drive the
Wave-field mutation.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _shell_parse import (  # noqa: E402
    find_gh_subcommand,
    iter_command_segments,
    strip_heredocs,
    tokenize,
)

_WAVE_LABEL_RE = re.compile(r"^p(\d+)-wave-(\d+)$")


@dataclass(frozen=True)
class WaveLabelChange:
    """Result of parsing a `gh issue edit ... --add-label|--remove-label` command.

    At least one of `add_label` / `remove_label` is non-None.

    `repo` is the short repo name from `--repo owner/name` (e.g.
    `noorinalabs-main`), or None when the command OMITS `--repo` and relies
    on gh's ambient-git-context resolution. Consumers that need a concrete
    repo (for a GraphQL/REST call) resolve the None case from the invocation
    cwd via `_shell_parse.resolve_repo_short_name` (#650).
    """

    repo: str | None
    issue_number: str
    add_label: str | None
    remove_label: str | None


@dataclass(frozen=True)
class WaveLabelCreate:
    """Result of parsing a `gh issue create --label "p{N}-wave-{M}"` segment.

    Issue NUMBER is not present at parse-time (the create has not yet
    landed); the caller extracts it from PostToolUse stdout.
    """

    repo: str
    add_label: str


def is_wave_label(value: str) -> bool:
    """True if `value` is exactly a `p{N}-wave{M}` canonical wave label.

    Anchored fullmatch: `p3-wave-10-special` returns False (the trailing
    `-special` defeats the end anchor); `p3-wave-10` returns True.
    """
    return bool(_WAVE_LABEL_RE.match(value))


def parse_wave_label(value: str) -> tuple[int, int] | None:
    """Parse a wave-label string into `(phase_num, wave_num)` or None."""
    m = _WAVE_LABEL_RE.match(value)
    if m is None:
        return None
    return int(m.group(1)), int(m.group(2))


def _parse_edit_segment(rest: list[str]) -> WaveLabelChange | None:
    """Parse the rest of a tokenized `gh issue edit <num> ...` segment.

    Returns the WaveLabelChange if the segment has an issue_number AND at
    least one canonical wave-label `--add-label`/`--remove-label`. Otherwise
    returns None.

    `--repo` is OPTIONAL (#650): a `gh issue edit <num> --remove-label
    "p4-wave-5"` run from inside the target repo carries no `--repo` and
    relies on gh's ambient-git-context resolution. Requiring `--repo` here
    silently dropped every such in-repo label edit (the change never reached
    the field-sync hook → board Wave field went unsynced). When `--repo` is
    absent the returned `repo` is None; the consuming hook resolves the
    ambient repo from the invocation cwd.
    """
    if len(rest) < 3 or rest[0] != "issue" or rest[1] != "edit":
        return None

    issue_number: str | None = None
    repo: str | None = None
    add_label: str | None = None
    remove_label: str | None = None

    i = 2
    n = len(rest)
    while i < n:
        tok = rest[i]
        if issue_number is None and re.fullmatch(r"\d+", tok):
            issue_number = tok
            i += 1
            continue
        if tok == "--repo" and i + 1 < n:
            repo = rest[i + 1].split("/")[-1]
            i += 2
            continue
        if tok.startswith("--repo="):
            repo = tok[len("--repo=") :].split("/")[-1]
            i += 1
            continue
        if tok == "--add-label" and i + 1 < n:
            value = rest[i + 1]
            if add_label is None and is_wave_label(value):
                add_label = value
            i += 2
            continue
        if tok.startswith("--add-label="):
            value = tok[len("--add-label=") :]
            if add_label is None and is_wave_label(value):
                add_label = value
            i += 1
            continue
        if tok == "--remove-label" and i + 1 < n:
            value = rest[i + 1]
            if remove_label is None and is_wave_label(value):
                remove_label = value
            i += 2
            continue
        if tok.startswith("--remove-label="):
            value = tok[len("--remove-label=") :]
            if remove_label is None and is_wave_label(value):
                remove_label = value
            i += 1
            continue
        i += 1

    if issue_number and (add_label or remove_label):
        return WaveLabelChange(
            repo=repo,
            issue_number=issue_number,
            add_label=add_label,
            remove_label=remove_label,
        )
    return None


def parse_wave_label_changes(command: str) -> list[WaveLabelChange]:
    """Parse a Bash command and return ALL wave-label changes within it.

    Issue #455 multi-cmd fix. A single Bash tool call may contain MANY
    `gh issue edit` invocations (for-loops, `&&`-chains, `;`-separated
    or newline-separated). Each that has a canonical wave-label
    `--add-label`/`--remove-label` becomes one `WaveLabelChange` in the
    returned list.

    Tolerates:
      - shell pipeline operators (`;`, `&&`, `||`, `|`)
      - newline-separated commands (POSIX line continuation also handled
        by the shared `tokenize` primitive)
      - heredoc bodies (stripped before tokenization)
      - leading `KEY=value` env assignments per segment
      - `--repo X` / `--repo=X` / `--add-label X` / `--add-label=X` forms

    Returns an empty list when:
      - The command doesn't tokenize cleanly (unbalanced quotes).
      - No segment contains a `gh issue edit` with a wave-label flag.

    For-loop shape note: `for N in 1 2 3; do gh issue edit $N ...; done`
    tokenizes the LITERAL `$N` token (shlex does not expand variables),
    so the parsed `issue_number` would be `$N` and the change would be
    rejected by the `re.fullmatch(r"\\d+", tok)` issue-number filter.
    For-loops are handled by the harness expanding them BEFORE the hook
    sees the command — in practice the harness passes either the
    expanded form or each iteration as a separate Bash call. The
    multi-cmd fix covers `gh issue edit 1 ... ; gh issue edit 2 ...` and
    `gh issue edit 1 ... && gh issue edit 2 ...` shapes which is the
    dominant batch shape.
    """
    cleaned = strip_heredocs(command)
    tokens = tokenize(cleaned)
    if tokens is None:
        return []

    out: list[WaveLabelChange] = []
    for segment in iter_command_segments(tokens):
        gh = find_gh_subcommand(segment)
        if gh is None:
            continue
        _globals, rest = gh
        change = _parse_edit_segment(rest)
        if change is not None:
            out.append(change)
    return out


def parse_wave_label_change(command: str) -> WaveLabelChange | None:
    """Back-compat singular form: returns the FIRST `WaveLabelChange` or None.

    Preserved for `post_wave_kickoff_comment.py` which treats multi-cmd
    as out-of-pattern (a single kickoff comment per label-apply event).
    New callers should use `parse_wave_label_changes` (plural) to handle
    multi-cmd Bash correctly per #455.
    """
    changes = parse_wave_label_changes(command)
    return changes[0] if changes else None


def parse_wave_label_create(command: str) -> list[WaveLabelCreate]:
    """Parse `gh issue create [--repo r] --label "p{N}-wave-{M}"` shapes.

    Returns a list of `WaveLabelCreate` objects, one per `gh issue create`
    segment with at least one canonical wave-label `--label` value. The
    list is empty when no segment matches. Multi-cmd Bash is supported
    (same iteration shape as `parse_wave_label_changes`).

    `--repo` and `--label` accept both spaced (`--flag X`) and
    equals (`--flag=X`) forms. Multiple `--label` flags are tolerated;
    only the FIRST wave-label value is captured (Hook 13's existing
    invariant — one wave label per issue).

    Issue #450 use case: Hook 13 (`auto_add_issue_to_board`) needs to
    know the wave label at create-time so it can set the project board's
    Wave single-select field after adding the issue. The issue NUMBER
    is not known at parse-time (Bash hasn't run yet from PreToolUse
    perspective; for PostToolUse the number is in the command output,
    not the command tokens). The caller extracts the number from the
    PostToolUse `tool_response.stdout` URL.
    """
    cleaned = strip_heredocs(command)
    tokens = tokenize(cleaned)
    if tokens is None:
        return []

    out: list[WaveLabelCreate] = []
    for segment in iter_command_segments(tokens):
        gh = find_gh_subcommand(segment)
        if gh is None:
            continue
        _globals, rest = gh
        if len(rest) < 2 or rest[0] != "issue" or rest[1] != "create":
            continue

        repo: str | None = None
        wave_label: str | None = None

        i = 2
        n = len(rest)
        while i < n:
            tok = rest[i]
            if tok == "--repo" and i + 1 < n:
                repo = rest[i + 1].split("/")[-1]
                i += 2
                continue
            if tok.startswith("--repo="):
                repo = tok[len("--repo=") :].split("/")[-1]
                i += 1
                continue
            if tok == "--label" and i + 1 < n:
                value = rest[i + 1]
                if wave_label is None and is_wave_label(value):
                    wave_label = value
                i += 2
                continue
            if tok.startswith("--label="):
                value = tok[len("--label=") :]
                if wave_label is None and is_wave_label(value):
                    wave_label = value
                i += 1
                continue
            i += 1

        if wave_label and repo:
            out.append(WaveLabelCreate(repo=repo, add_label=wave_label))
    return out
