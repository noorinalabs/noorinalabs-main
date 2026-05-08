#!/usr/bin/env python3
"""Shared shell-arg-aware parser helper for PreToolUse Bash hooks.

Background
==========

Multiple PreToolUse hooks have repeatedly tripped on substring/regex matching
against the raw Bash command string (issues #118, #134, #144, #188, #189,
#216, #223, #226, #227). Root cause: the matcher cannot tell *command-position*
tokens (e.g. an actual `git config` invocation) from *data-position* text
(e.g. the phrase "git config" inside a heredoc body, a `--body-file` argument
value, or a documentation string).

This module is the unifying primitive: tokenize once with shlex, segment-split
on shell operators, then locate command-position tokens explicitly. Hooks call
the small public API instead of writing one-off regexes.

Public API
==========

    tokenize(cmd) -> list[str] | None
        shlex.split with posix semantics. Returns None on parse failure
        (unbalanced quotes, etc.) so callers can fall back to a regex path.

        Caller contract: callers MUST handle None explicitly. Never treat
        None as "allow" for security-relevant matchers like commit-identity
        validation — fall back to a regex check or a fail-closed decision.
        For warn-only matchers, fail-open on None is acceptable.

    strip_heredocs(cmd) -> str
        Removes <<DELIM .. DELIM, <<'DELIM' .. DELIM, <<"DELIM" .. DELIM and
        <<-DELIM .. DELIM heredoc bodies (delimiter is rfc-shell-style: any
        word). Handles repeated/nested heredocs by iterating until the regex
        is fixed.

    iter_command_segments(tokens) -> Iterator[list[str]]
        Splits a token list on the shell-control tokens `;`, `&&`, `||`, `|`
        (these survive shlex.split as their own tokens because they're not
        inside quotes), strips leading `KEY=value` env-var assignments from
        each segment, and yields the surviving tokens.

    find_git_subcommand(segment) -> tuple[list[str], list[str]] | None
        Given a single segment's tokens, returns (global_opts, [subcommand,
        ...rest]) if it's a `git ...` invocation, else None. Skips git
        global options (`-c k=v`, `-C dir`, `--git-dir=...`,
        `--work-tree=...`, etc.) so the returned subcommand is the actual
        git verb (`commit`, `config`, `worktree`, ...).

    find_gh_subcommand(segment) -> tuple[list[str], list[str]] | None
        Same shape for `gh ...`. Returns (gh_global_opts, [topic, action,
        ...rest]) — e.g. ([], ["pr", "create", "--repo", ...]).

    extract_dash_c_pairs(segment) -> list[tuple[str, str]]
        Walks a tokenized git segment and returns (key, value) pairs for
        every `-c key=value` global option, in source order. shlex has
        already unquoted values, so a simple `split('=', 1)` is correct.

        Repeated-key contract: `git -c user.name=A -c user.name=B commit`
        is legal (last wins per git semantics). This helper returns ALL
        pairs in source order; callers needing last-wins semantics can
        do `dict(extract_dash_c_pairs(...))` (later keys overwrite
        earlier in dict construction). Do not rely on first-occurrence
        unless you handle dedup yourself.

    resolve_tool_cwd(input_data) -> str
        Returns input_data["cwd"] if the harness supplied it, else
        os.getcwd(). The Claude Code harness sets `cwd` on the hook input
        for tool calls that run from a known cwd; subprocess calls that
        want to operate on the *user's* cwd (not the hook's parent process
        cwd) should use this to anchor `subprocess.run(..., cwd=...)`.

    is_shutdown_request_message(message) -> bool
        True only if `message` is a structured shutdown_request JSON
        (dict-form OR str-form parseable to a dict with type==
        "shutdown_request"). Plain prose containing the substring is NOT
        a shutdown request — that was the #189 false-positive root.

Why not eval / parse the full shell grammar?
============================================

shlex.split + segment + command-position lookup is the 95% solution. Hooks
that match against a known shape (`git commit`, `gh pr create`, `git config`)
need exactly this. Full POSIX shell parsing is overkill and would re-introduce
the parser-correctness debt the regexes had.

When shlex.split fails (malformed quotes), callers MUST fall back to a regex
or fail-open (return None to allow the command). Never crash on parse error.

Promotion provenance
====================

Sibling-bug cluster (P3W4 Tier-2): #226 #227 #223 #216 #188 #144 #189.
Tracking PR consolidates the parser into one tested helper and refactors
five hooks (validate_commit_identity, validate_branch_freshness,
block_git_config, block_no_verify, block_shutdown_without_retro).
"""

from __future__ import annotations

import json
import os
import re
import shlex
from typing import Iterator

# Shell control tokens that segment a compound command. Any of these,
# appearing as their OWN token after shlex.split, separates one pipeline
# segment from the next.
_SEGMENT_OPS = {";", "&&", "||", "|"}

# Match KEY=value env-var assignment at command position. Must start with a
# letter or underscore and contain only word chars before the '='. shlex has
# already de-quoted any quoted value, so the value half is just "everything
# after the first =".
_ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_]\w*=")

# Heredoc opener: <<-?\s*['"]?DELIM['"]? on a line, then any content, then
# the bare DELIM word terminating it. Supports the four shell variants
# (<<EOF, <<'EOF', <<"EOF", <<-EOF). The `<<-` tabs-stripping form allows
# leading tabs on the closing delimiter line, so we match optional `\t*`
# before \1 in the closer position.
_HEREDOC_RE = re.compile(
    r"<<-?\s*['\"]?(\w+)['\"]?.*?\n.*?\n\t*\1\b",
    re.DOTALL,
)

# git global options that consume a value (two-token form). Equals-form
# (e.g. `--git-dir=path`) is handled separately as a single token.
_GIT_VALUE_GLOBALS = {"-c", "-C", "--git-dir", "--work-tree", "--namespace", "--exec-path"}

# git global boolean options (no value).
_GIT_BOOL_GLOBALS = {
    "--no-pager",
    "-p",
    "--paginate",
    "--no-replace-objects",
    "--bare",
    "--no-optional-locks",
}

# Backslash + newline = POSIX line continuation. The Claude Code harness passes
# the raw bash command string including these sequences. shlex.split(posix=True)
# does NOT consume them as line continuations — instead it emits the trailing
# newline as a standalone token (issue #287), breaking command-position detection.
_LINE_CONTINUATION_RE = re.compile(r"\\\n[ \t]*")


def tokenize(cmd: str) -> list[str] | None:
    """shlex.split the command. Return None on parse error (unbalanced quote).

    Normalizes POSIX line-continuation sequences (backslash + newline) to a
    single space before tokenizing. Without this, shlex.split(posix=True)
    emits the trailing newline as a stray token that breaks command-position
    detection (issue #287).
    """
    try:
        return shlex.split(_LINE_CONTINUATION_RE.sub(" ", cmd), posix=True)
    except ValueError:
        return None


def strip_heredocs(cmd: str) -> str:
    """Remove all heredoc bodies. Iterates until no more matches (handles nested)."""
    prev = None
    cur = cmd
    while prev != cur:
        prev = cur
        cur = _HEREDOC_RE.sub("", cur)
    return cur


def iter_command_segments(tokens: list[str]) -> Iterator[list[str]]:
    """Split tokens on `;`, `&&`, `||`, `|` and strip leading KEY=val env vars.

    Each yielded segment is a non-empty list of tokens representing one
    command in the pipeline. Empty segments (e.g. trailing `;`) are skipped.
    """
    if not tokens:
        return

    cur: list[str] = []
    for tok in tokens:
        if tok in _SEGMENT_OPS:
            if cur:
                stripped = _strip_leading_env_assignments(cur)
                if stripped:
                    yield stripped
                cur = []
            continue
        cur.append(tok)
    if cur:
        stripped = _strip_leading_env_assignments(cur)
        if stripped:
            yield stripped


def _strip_leading_env_assignments(segment: list[str]) -> list[str]:
    """Drop leading KEY=value tokens from a segment (one-shot env vars)."""
    i = 0
    while i < len(segment) and _ENV_ASSIGN_RE.match(segment[i]):
        i += 1
    return segment[i:]


def _is_equals_form_global(tok: str) -> bool:
    """True if `tok` is the equals-form of a value-taking git global.

    Examples that return True: `-c=user.name=foo`, `--git-dir=.git`,
    `--work-tree=/path`. We only care about the prefix; the value half is
    irrelevant for the skip decision.
    """
    return (
        tok.startswith("-c=")
        or tok.startswith("-C=")
        or tok.startswith("--git-dir=")
        or tok.startswith("--work-tree=")
        or tok.startswith("--namespace=")
        or tok.startswith("--exec-path=")
    )


def find_git_subcommand(segment: list[str]) -> tuple[list[str], list[str]] | None:
    """If `segment` is a `git ...` invocation, return (global_opts, [subcmd, ...]).

    Skips git global options:
      -c key=value          (consumed as one shlex token, possibly quoted)
      -C path
      --git-dir=path / --git-dir path
      --work-tree=path / --work-tree path
      --no-pager / -p / --paginate / --no-replace-objects   (no value)

    Returns None if `segment` is empty, doesn't start with `git`, or doesn't
    have a subcommand after the global-option run.
    """
    if not segment or segment[0] != "git":
        return None

    globals_: list[str] = []
    i = 1
    n = len(segment)
    while i < n:
        tok = segment[i]
        if tok in _GIT_BOOL_GLOBALS:
            globals_.append(tok)
            i += 1
            continue
        if tok in _GIT_VALUE_GLOBALS:
            globals_.append(tok)
            if i + 1 < n:
                globals_.append(segment[i + 1])
                i += 2
            else:
                i += 1
            continue
        if _is_equals_form_global(tok):
            globals_.append(tok)
            i += 1
            continue
        # First non-option token is the subcommand.
        return globals_, segment[i:]
    return None


def find_gh_subcommand(segment: list[str]) -> tuple[list[str], list[str]] | None:
    """If `segment` is a `gh ...` invocation, return ([], [topic, action, ...]).

    `gh` has no pre-subcommand global options worth skipping for the matchers
    in this codebase, so this is a thin shape-mirror of `find_git_subcommand`.
    """
    if not segment or segment[0] != "gh":
        return None
    if len(segment) < 2:
        return None
    return [], segment[1:]


def extract_dash_c_pairs(segment: list[str]) -> list[tuple[str, str]]:
    """Walk a git segment and yield (key, value) for every `-c key=value`.

    Handles `-c k=v` (two tokens) and `-c=k=v` (one token, rare). shlex has
    already unquoted the value half, so `-c user.name="A B"` arrives here as
    `["-c", "user.name=A B"]` (two tokens; the inner `=` is the key/value
    separator handled by `split("=", 1)`).
    """
    pairs: list[tuple[str, str]] = []
    if not segment or segment[0] != "git":
        return pairs

    i = 1
    n = len(segment)
    while i < n:
        tok = segment[i]
        if tok == "-c" and i + 1 < n:
            kv = segment[i + 1]
            if "=" in kv:
                key, value = kv.split("=", 1)
                pairs.append((key, value))
            i += 2
            continue
        if tok.startswith("-c=") and "=" in tok[3:]:
            kv = tok[3:]
            key, value = kv.split("=", 1)
            pairs.append((key, value))
            i += 1
            continue
        # Other value-taking globals — skip the value too.
        if tok in _GIT_VALUE_GLOBALS:
            i += 2
            continue
        if _is_equals_form_global(tok):
            i += 1
            continue
        if tok in _GIT_BOOL_GLOBALS:
            i += 1
            continue
        # First non-option token is the subcommand — done collecting -c pairs.
        break
    return pairs


def resolve_tool_cwd(input_data: dict) -> str:
    """Return the cwd for the tool call.

    The Claude Code harness sets `cwd` on the hook input for tool calls. When
    present, it is the user's actual working directory at tool-call time —
    which is what hooks should reason about, NOT the hook's parent process
    cwd (which is whatever the agent was launched from, often the wrong repo
    for a worktree subagent — see #144).

    Falls back to os.getcwd() if the field is missing or empty (older
    harness versions, manual invocations).
    """
    cwd = input_data.get("cwd")
    if cwd and isinstance(cwd, str):
        return cwd
    return os.getcwd()


def is_shutdown_request_message(message) -> bool:
    """True iff `message` is a structured shutdown_request, NOT prose containing the phrase.

    Accepts either:
      - dict with `type: "shutdown_request"` (already-parsed JSON)
      - str whose JSON-parsed object has `type: "shutdown_request"`

    Plain text messages are NEVER treated as shutdown requests, even if they
    contain the literal substring. Issue #189: subagents writing
    "standing down" / "Acknowledge" prose were tripping the substring matcher.
    """
    if isinstance(message, dict):
        return message.get("type") == "shutdown_request"
    if not isinstance(message, str):
        return False
    s = message.strip()
    if not s.startswith("{"):
        return False
    try:
        obj = json.loads(s)
    except (json.JSONDecodeError, ValueError):
        return False
    return isinstance(obj, dict) and obj.get("type") == "shutdown_request"
