#!/usr/bin/env python3
"""Shared parser for wave-label `gh issue edit/create` commands.

Wave-label grammar (#810, completing Design B #804)
===================================================

Three forms are accepted everywhere a wave label is recognized:

  - legacy `p{N}-wave-{M}` (e.g. `p6-wave-16`) — grandfathered; in-flight
    issues labeled this way keep working.
  - global `wave-{X}` (e.g. `wave-16`) — phase-agnostic; the owner-preferred
    going-forward form. `X` is the global monotonic wave id (#804); the phase
    is a derived display carried by branches/status, not the label.
  - placeholder `wave-x` — the literal label for phase/scope-undecided work.

`is_wave_label` / `parse_wave_label_spec` / `wave_label_to_option_name` accept
all three. `parse_wave_label` is legacy-form-only (its `(phase, wave)` tuple
cannot express a missing phase) — see its docstring.

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
          repo          — `noorinalabs-<name>` short form from the AUTHORITATIVE
                          `-R`/`--repo owner/name` flag (all five surface forms,
                          #985/#1057), or None. `repo_flag_present` disambiguates
                          the two None cases (flag omitted vs present-but-
                          unresolvable — see below).
          repo_flag_present — True iff a `-R`/`--repo` flag was present in the
                          command (regardless of whether its value resolved).
                          When `repo` is None: `repo_flag_present=False` means
                          the flag was OMITTED (in-repo ambient gh resolution,
                          #650 — consumer resolves from cwd); `repo_flag_present
                          =True` means the flag was present but unresolvable (an
                          unexpanded `$VAR`, #981 — consumer fails closed, never
                          falls back to cwd).
          issue_number  — the bare positional issue number after `edit`.
          add_label     — the FIRST `--add-label "p{N}-wave-{M}"` value, or
                          None if no add operation present.
          remove_label  — the FIRST `--remove-label "p{N}-wave-{M}"` value,
                          or None if no remove operation present.

        At least one of `add_label` / `remove_label` is non-None when the
        function returns a result; otherwise it returns None.

    parse_unresolved_wave_label_edits(command) -> list[UnresolvedWaveLabelEdit]
        The visibility companion (main#1141): every `gh issue edit …
        --add-label "<wave label>"` segment whose ISSUE NUMBER could not be
        resolved — the `for n in 1114 1116; do gh issue edit "$n" …; done`
        shape, where shlex leaves the literal `$n` and no digit run exists in
        the command at all. Those segments are invisible to
        `parse_wave_label_changes` by construction; this function lets a
        consumer LOG the decline instead of silently doing nothing (the
        main#1141 failure mode: 14 issues labeled, 0 kickoff comments, caught
        only by an unrelated audit days later).

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
    normalize_command_separators,
    repo_short_name_from_flag_value,
    strip_heredocs,
    tokenize,
    walk_flag_values,
)

# Legacy phase-prefixed form: `p6-wave-16` (grandfathered, still accepted).
_LEGACY_WAVE_LABEL_RE = re.compile(r"^p(\d+)-wave-(\d+)$")
# Phase-agnostic global form (#810, completes Design B #804): `wave-16`.
_GLOBAL_WAVE_LABEL_RE = re.compile(r"^wave-(\d+)$")
# Phase/scope-undecided placeholder (#810): the literal label `wave-x`.
_PLACEHOLDER_WAVE_LABEL = "wave-x"

# Back-compat alias: some external readers referenced `_WAVE_LABEL_RE` as the
# canonical legacy matcher. It remains the *legacy-form* matcher only.
_WAVE_LABEL_RE = _LEGACY_WAVE_LABEL_RE


@dataclass(frozen=True)
class WaveLabelSpec:
    """Parsed wave label spanning all three accepted forms (#810).

    Forms and the fields they populate:
      - legacy `p{N}-wave-{M}`  → phase=N, wave=M, is_placeholder=False
      - global `wave-{X}`        → phase=None, wave=X, is_placeholder=False
      - placeholder `wave-x`     → phase=None, wave=None, is_placeholder=True

    `phase` is None for every phase-agnostic form (Design B #804 made the wave
    id global/monotonic and the phase a derived display, so the label no longer
    carries it). `wave` is None only for the `wave-x` placeholder. `raw` is the
    original label string.
    """

    raw: str
    phase: int | None
    wave: int | None
    is_placeholder: bool


@dataclass(frozen=True)
class WaveLabelChange:
    """Result of parsing a `gh issue edit ... --add-label|--remove-label` command.

    At least one of `add_label` / `remove_label` is non-None.

    `repo` is the short repo name from the AUTHORITATIVE `-R`/`--repo owner/name`
    flag (e.g. `noorinalabs-main`), extracted via the #1057-hardened
    `walk_flag_values` so all five surface forms resolve (`--repo X`, `--repo=X`,
    `-R X`, `-R=X`, `-RX`). It is None in TWO distinct cases, disambiguated by
    `repo_flag_present` (#985):

      - `repo_flag_present=False` → the command OMITS the repo flag entirely and
        relies on gh's ambient-git-context resolution. Consumers resolve the None
        case from the invocation cwd via `_shell_parse.resolve_repo_short_name`
        (#650).
      - `repo_flag_present=True` → the flag WAS present but its value was
        unresolvable (an unexpanded `$VAR` / command substitution, per #981).
        Consumers MUST fail closed (skip/block) — NEVER fall back to cwd, which
        would misroute a child-repo op to the parent.
    """

    repo: str | None
    issue_number: str
    add_label: str | None
    remove_label: str | None
    repo_flag_present: bool = False


@dataclass(frozen=True)
class WaveLabelCreate:
    """Result of parsing a `gh issue create --label "p{N}-wave-{M}"` segment.

    Issue NUMBER is not present at parse-time (the create has not yet
    landed); the caller extracts it from PostToolUse stdout.

    `repo` is the short repo name from `--repo owner/name` (e.g.
    `noorinalabs-main`), or None when the command OMITS `--repo` and relies
    on gh's ambient-git-context resolution (#659 — the create-surface sibling
    of the EDIT-path #650 fix). Requiring `--repo` here silently dropped every
    in-repo `gh issue create` (the create never reached the Wave-field sync →
    the board Wave field went unset). When `--repo` is absent the consumer
    resolves the concrete repo from the created-issue URL in PostToolUse
    stdout, which is the authoritative repo the issue actually landed in.
    """

    repo: str | None
    add_label: str


def is_wave_label(value: str) -> bool:
    """True if `value` is a canonical wave label in ANY accepted form (#810).

    Accepts the legacy phase-prefixed `p{N}-wave-{M}` (grandfathered), the
    phase-agnostic global `wave-{X}`, and the `wave-x` placeholder. Anchored
    fullmatch: suffixed labels like `p3-wave-10-special` or `wave-10-frozen`
    return False (the trailing segment defeats the end anchor); `p3-wave-10`,
    `wave-10`, and `wave-x` return True.
    """
    return parse_wave_label_spec(value) is not None


def parse_wave_label_spec(value: str) -> WaveLabelSpec | None:
    """Parse a label string into a `WaveLabelSpec` spanning all forms, or None.

    Single source of truth for the wave-label grammar (#810). Returns None for
    any string that is not one of the three accepted forms.
    """
    if value == _PLACEHOLDER_WAVE_LABEL:
        return WaveLabelSpec(raw=value, phase=None, wave=None, is_placeholder=True)
    m = _LEGACY_WAVE_LABEL_RE.match(value)
    if m is not None:
        return WaveLabelSpec(
            raw=value, phase=int(m.group(1)), wave=int(m.group(2)), is_placeholder=False
        )
    m = _GLOBAL_WAVE_LABEL_RE.match(value)
    if m is not None:
        return WaveLabelSpec(raw=value, phase=None, wave=int(m.group(1)), is_placeholder=False)
    return None


def parse_wave_label(value: str) -> tuple[int, int] | None:
    """Parse a LEGACY `p{N}-wave-{M}` label into `(phase_num, wave_num)` or None.

    Legacy-form only by contract: the return type cannot express a missing
    phase, so phase-agnostic forms (`wave-{X}`, `wave-x`) return None here.
    Callers that must handle the new forms use `parse_wave_label_spec` instead
    (e.g. `wave_label_to_option_name`). Retained unchanged for the grandfathered
    callers and their tests.
    """
    m = _LEGACY_WAVE_LABEL_RE.match(value)
    if m is None:
        return None
    return int(m.group(1)), int(m.group(2))


def wave_label_to_option_name(value: str) -> str | None:
    """Convert a wave label to the project-2 Wave single-select option name.

    Mapping (#810), board option-name grammar:
      - legacy `p{N}-wave-{M}` → `P{N}W{M}`  (e.g. `p6-wave-16` → `P6W16`)
      - global `wave-{X}`       → `W{X}`       (e.g. `wave-16`    → `W16`)
      - placeholder `wave-x`    → `WX`         ("Wave (TBD)")

    Returns None when `value` is not a recognized wave label. Single source of
    truth so the EDIT-path and CREATE-path field-sync hooks (and `/board-audit`)
    agree on the option name for every form.
    """
    spec = parse_wave_label_spec(value)
    if spec is None:
        return None
    if spec.is_placeholder:
        return "WX"
    if spec.phase is None:
        return f"W{spec.wave}"
    return f"P{spec.phase}W{spec.wave}"


@dataclass(frozen=True)
class UnresolvedWaveLabelEdit:
    """A wave-label `gh issue edit` whose ISSUE NUMBER did not resolve (main#1141).

    Emitted by `parse_unresolved_wave_label_edits` for the shape

        for n in 1114 1116; do gh issue edit "$n" --add-label "wave-29"; done

    where shlex leaves `$n` literal and the command carries no digit run to
    key on. `parse_wave_label_changes` cannot return anything useful here —
    there is genuinely no issue number in the string — but a consumer that
    silently returns None is the main#1141 bug (labels land, nobody is told
    they own anything). Consumers use this to LOG the decline.

    `issue_token` is the offending token when it looks like an unexpanded
    shell expansion (`$n`, `${n}`, `` `…` ``), else None (e.g. an issue URL
    or a genuinely missing positional).
    """

    repo: str | None
    issue_token: str | None
    add_label: str | None
    remove_label: str | None
    repo_flag_present: bool = False


# A positional token that shlex left as an unexpanded shell expansion. Same
# marker set as `_shell_parse._UNRESOLVABLE_REPO_VALUE_RE` minus whitespace
# (a whitespace-bearing token is never a positional issue ref).
_UNEXPANDED_TOKEN_RE = re.compile(r"[$`]")


def _scan_edit_segment(
    rest: list[str],
) -> tuple[str | None, bool, str | None, str | None, str | None, str | None] | None:
    """Low-level scan of a `gh issue edit …` segment's tokens.

    Returns `(repo, repo_flag_present, issue_number, issue_token, add_label,
    remove_label)` for any `issue edit` segment, or None when `rest` is not
    one. `issue_number` is the first bare digit-run positional; `issue_token`
    is the first positional that looks like an unexpanded shell expansion.
    Both may be None. Shared by `_parse_edit_segment` (which requires a
    resolved number) and `parse_unresolved_wave_label_edits` (which reports
    the segments that lack one) so the two agree by construction.
    """
    if len(rest) < 3 or rest[0] != "issue" or rest[1] != "edit":
        return None

    repo_values = walk_flag_values(rest, {"--repo", "-R"})
    repo_flag_present = len(repo_values) > 0
    repo: str | None = (
        repo_short_name_from_flag_value(repo_values[-1]) if repo_flag_present else None
    )

    issue_number: str | None = None
    issue_token: str | None = None
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
        # An unexpanded positional (`gh issue edit "$n"`). Guarded on the
        # PREVIOUS token not being flag-shaped so a `--repo "$REPO"` /
        # `--body "$MSG"` VALUE is never mistaken for the issue ref — only a
        # true positional slot is reported.
        if (
            issue_token is None
            and _UNEXPANDED_TOKEN_RE.search(tok)
            and not rest[i - 1].startswith("-")
        ):
            issue_token = tok
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

    return repo, repo_flag_present, issue_number, issue_token, add_label, remove_label


def _parse_edit_segment(rest: list[str]) -> WaveLabelChange | None:
    """Parse the rest of a tokenized `gh issue edit <num> ...` segment.

    Returns the WaveLabelChange if the segment has an issue_number AND at
    least one canonical wave-label `--add-label`/`--remove-label`. Otherwise
    returns None — see `parse_unresolved_wave_label_edits` for the
    "wave label present but no resolvable issue number" case, which a
    consumer should log rather than swallow (main#1141).

    The repo is resolved from the AUTHORITATIVE `-R`/`--repo owner/name` flag
    (#985), extracted up front via the #1057-hardened `walk_flag_values` so all
    five surface forms resolve: `--repo X`, `--repo=X`, `-R X`, `-R=X`, `-RX`.
    The flag is GROUND TRUTH for "which repo"; the consuming hook's cwd fallback
    applies ONLY when no repo flag is present. Three states are surfaced:

      - flag present + resolvable  → `repo=<name>`, `repo_flag_present=True`.
      - flag absent (#650)         → `repo=None`,   `repo_flag_present=False`
        (in-repo invocation; consumer resolves the ambient repo from cwd).
      - flag present + unresolvable → `repo=None`, `repo_flag_present=True`
        (an unexpanded `$VAR` / command substitution; per #981 the consumer
        MUST fail closed and NOT fall back to cwd, which would misroute).

    Requiring `--repo` here would silently drop every in-repo label edit (#650);
    blindly `.split("/")`-ing an unexpanded `$VAR` would misroute it (#981). The
    tri-state threads both needles.

    The token walk itself lives in `_scan_edit_segment` (the repo tri-state
    included); this function is the narrowing layer that requires a resolved
    issue number.
    """
    scanned = _scan_edit_segment(rest)
    if scanned is None:
        return None
    repo, repo_flag_present, issue_number, _issue_token, add_label, remove_label = scanned

    if issue_number and (add_label or remove_label):
        return WaveLabelChange(
            repo=repo,
            issue_number=issue_number,
            add_label=add_label,
            remove_label=remove_label,
            repo_flag_present=repo_flag_present,
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

    Wrapper / compound-statement shapes (main#1141): a `timeout 45 gh …`
    prefix and the `do`-prefixed body of a `for … ; do gh … ; done` loop
    BOTH used to return nothing, because `find_gh_subcommand` required `gh`
    at token 0 of the segment. `_shell_parse.strip_command_prefixes` now
    strips the leading wrapper/keyword run, so those forms parse. The
    correction main#1141 records: the loop CONSTRUCT was the defeater, not
    variable expansion — a loop carrying a literal issue number failed
    identically, and it parses now.

    For-loop VARIABLE note (the residual, and it is not fixable here):
    `for n in 1114 1116; do gh issue edit "$n" …; done` tokenizes the
    LITERAL `$n` (shlex does not expand variables), so no issue number
    exists in the command string at all and the `re.fullmatch(r"\\d+", tok)`
    filter correctly rejects it. Do NOT paper over this by accepting `$n` as
    an issue ref — it would post to a nonexistent issue. Instead the shape is
    reported by `parse_unresolved_wave_label_edits` so the consumer LOGS the
    decline, and `/wave-kickoff`'s state-based reconciliation sweep
    (`.claude/lib/kickoff_sweep.py`) closes it for real by keying on the
    labels that actually landed rather than on the command string.
    """
    # Strip heredocs FIRST (its regex needs the raw newlines to find the body),
    # THEN normalize command separators so a leading `cd "$(...)"`-newline or a
    # non-space-padded `;` prefix still segments the `gh issue edit/create`
    # invocation into its own command segment (#901).
    cleaned = normalize_command_separators(strip_heredocs(command))
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


def parse_unresolved_wave_label_edits(command: str) -> list[UnresolvedWaveLabelEdit]:
    """Report wave-label edits whose issue number did NOT resolve (main#1141).

    Returns one `UnresolvedWaveLabelEdit` per `gh issue edit …` segment that
    carries a canonical wave-label `--add-label`/`--remove-label` but no bare
    digit-run issue number. The dominant real case is the loop-variable shape
    (`do gh issue edit "$n" --add-label "wave-29"`); an issue-URL positional or
    an outright missing positional land here too.

    This is deliberately a SEPARATE function rather than a widened
    `WaveLabelChange`: consumers that act on a change (post a comment, mutate a
    board field) must never be handed a row they could mistake for actionable.
    The only correct use of this result is to LOG that the hook declined —
    silence in the unsafe direction is the main#1141 bug itself.

    Segments that ALSO remove a wave label are still reported (the caller
    applies its own between-wave-relabel policy, per the #467 filter).
    """
    cleaned = normalize_command_separators(strip_heredocs(command))
    tokens = tokenize(cleaned)
    if tokens is None:
        return []

    out: list[UnresolvedWaveLabelEdit] = []
    for segment in iter_command_segments(tokens):
        gh = find_gh_subcommand(segment)
        if gh is None:
            continue
        _globals, rest = gh
        scanned = _scan_edit_segment(rest)
        if scanned is None:
            continue
        repo, repo_flag_present, issue_number, issue_token, add_label, remove_label = scanned
        if issue_number is not None:
            continue  # resolvable — `parse_wave_label_changes` already covers it
        if not (add_label or remove_label):
            continue  # not a wave-label edit at all
        out.append(
            UnresolvedWaveLabelEdit(
                repo=repo,
                issue_token=issue_token,
                add_label=add_label,
                remove_label=remove_label,
                repo_flag_present=repo_flag_present,
            )
        )
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

    `--repo` is OPTIONAL (#659): an in-repo `gh issue create --label
    "p{N}-wave-{M}"` run without `--repo` relies on gh's ambient-git-context
    resolution and carries no `--repo` token. Such a create still yields a
    `WaveLabelCreate` (with `repo=None`); the consumer resolves the concrete
    repo from the created-issue URL. Before this fix the `if wave_label and
    repo:` gate dropped every in-repo create, leaving the board Wave field
    unset — the create-surface sibling of the EDIT-path #650 silent-drop.

    Issue #450 use case: Hook 13 (`auto_add_issue_to_board`) needs to
    know the wave label at create-time so it can set the project board's
    Wave single-select field after adding the issue. The issue NUMBER
    is not known at parse-time (Bash hasn't run yet from PreToolUse
    perspective; for PostToolUse the number is in the command output,
    not the command tokens). The caller extracts the number from the
    PostToolUse `tool_response.stdout` URL.
    """
    # Strip heredocs FIRST (its regex needs the raw newlines to find the body),
    # THEN normalize command separators so a leading `cd "$(...)"`-newline or a
    # non-space-padded `;` prefix still segments the `gh issue edit/create`
    # invocation into its own command segment (#901).
    cleaned = normalize_command_separators(strip_heredocs(command))
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

        if wave_label:
            # `repo` may be None (in-repo `gh issue create` without `--repo`,
            # #659). Emit the create anyway; the consumer recovers the concrete
            # repo from the created-issue URL. Gating on `repo` here silently
            # dropped every in-repo wave-labeled create — the create-surface
            # twin of the EDIT-path #650 drop.
            out.append(WaveLabelCreate(repo=repo, add_label=wave_label))
    return out
