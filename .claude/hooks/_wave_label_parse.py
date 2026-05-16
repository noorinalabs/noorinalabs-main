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

    parse_wave_label_change(command: str) -> WaveLabelChange | None
        Parse a bash command. Returns a `WaveLabelChange` describing the
        first wave-label add/remove operation found, or None if the command
        doesn't apply (not `gh issue edit`, no `p{N}-wave-{M}` label, etc.).

        Result fields:
          repo          — `noorinalabs-<name>` short form (last path segment
                          of `--repo owner/name` or `--repo=owner/name`).
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
    """

    repo: str
    issue_number: str
    add_label: str | None
    remove_label: str | None


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


def parse_wave_label_change(command: str) -> WaveLabelChange | None:
    """Parse `gh issue edit <num> --repo <r> [--add-label W] [--remove-label W]`.

    W is the wave-label shape `p{N}-wave-{M}`.

    Returns a `WaveLabelChange` describing the FIRST `gh issue edit`
    segment that includes at least one `--add-label`/`--remove-label`
    with a canonical wave-label value, or None.

    Tolerates additional non-wave-label flags (extra `--add-label
    "Aino_Virtanen"` etc.). Tolerates arbitrary flag ordering and both
    flag forms (`--repo X` and `--repo=X`; `--add-label X` and
    `--add-label=X`). Tolerates compound pipelines (`true && gh issue
    edit ...`).

    Returns None when:
      - The command doesn't tokenize cleanly (unbalanced quotes).
      - No segment contains `gh issue edit`.
      - The matched `gh issue edit` segment has no canonical wave label
        in any `--add-label` or `--remove-label` flag.
      - The matched segment is missing one of: issue number, repo.

    Reads only the FIRST `gh issue edit` segment with a wave label; later
    pipeline segments with `gh issue edit` are ignored (rare in practice;
    if it becomes a real shape, extend here).
    """
    cleaned = strip_heredocs(command)
    tokens = tokenize(cleaned)
    if tokens is None:
        return None

    for segment in iter_command_segments(tokens):
        gh = find_gh_subcommand(segment)
        if gh is None:
            continue
        _globals, rest = gh
        if len(rest) < 3 or rest[0] != "issue" or rest[1] != "edit":
            continue

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

        if issue_number and repo and (add_label or remove_label):
            return WaveLabelChange(
                repo=repo,
                issue_number=issue_number,
                add_label=add_label,
                remove_label=remove_label,
            )

    return None
