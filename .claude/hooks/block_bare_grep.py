#!/usr/bin/env python3
"""PreToolUse hook: Block a bare `grep` invocation — use `rg` (ripgrep) instead.

Org convention (owner-directed 2026-07-19, #1008): text search standardises on
`rg`, never plain `grep`. `rg` is faster, multiline-capable, and `.gitignore`-
aware, and on the dev box `grep` is actually `ugrep` — so relying on GNU-grep
behaviour is already unsafe. This hook is the enforcement backstop; the rule
itself lives in `docs/TOOLCHAIN.md § Text search: rg, not grep`,
`ontology/conventions.md`, and `CLAUDE.md`.

Input Language
==============

Fires on:      PreToolUse Bash
Matches (BLOCK):
    grep ...                          (direct, command position)
    ... | grep ...                    (piped — grep is a pipeline segment)
    egrep ... / fgrep ...             (grep family rg replaces)
    /usr/bin/grep ...                 (absolute / relative path — matched by basename)
    x=$(grep ...)                     (command substitution — via the bashlex AST path)
    sudo grep / env grep / time grep / xargs grep / ... (common command wrappers)

Does NOT match (ALLOW):
    rg ... / ripgrep ...              (the tool we want)
    ast-grep ...                      (structural search — a different tool)
    pgrep ... / zgrep ... / zegrep ...(process-grep / compressed-grep — not text grep)
    git grep ...                      (git's own tracked-file search — `git` is the command)
    echo "we forbid grep"             (data position — "grep" is an argument, not the command)
    cat <<EOF ... grep ... EOF        (heredoc body — stripped before matching)
    gh pr create --body "... grep ..."(flag value — a single shlex token, never command position)
    NOORINA_ALLOW_GREP=1 grep ...     (documented escape hatch for the rare grep-only need)

Design
======

Command-POSITION detection (not substring) is the whole game — the same
data-vs-command confusion that produced the #118…#227 bug trail. We reuse the
shared `_shell_parse` primitives: strip heredocs, then extract command-position
segments (bashlex AST when available, shlex fallback otherwise) and test the
*effective command* of each segment. A segment's effective command is its first
token, after peeling a small set of exec wrappers (`sudo`, `env`, `xargs`, …)
and their flags, matched by basename so `/bin/grep` is caught and `ast-grep`,
`pgrep`, `zgrep` are not.

Fail-open: this is a convention gate, not a security matcher, so an unparseable
command is allowed (mirrors `block_no_verify`). The escape hatch keeps it from
being a footgun for the rare case `rg` cannot express.

Exit codes:
  0 — allow (no bare grep in command position, or override present)
  2 — block (bare grep detected)
"""

from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _shell_parse import (  # noqa: E402
    iter_command_segments,
    iter_command_segments_ast,
    normalize_command_separators,
    strip_heredocs,
    tokenize,
)
from annunaki_log import log_pretooluse_block  # noqa: E402

# The grep family `rg` replaces. `zgrep`/`zegrep`/`bzgrep` (compressed input)
# and `pgrep` (process table) are deliberately excluded — `rg` is not a drop-in
# for those. `ast-grep` is structural search, a different tool entirely.
_GREP_CMDS = {"grep", "egrep", "fgrep"}

# Common exec wrappers: `<wrapper> [flags] grep ...` is still a grep invocation.
# We peel these (and their flags) to find the effective command word.
_WRAPPERS = {
    "sudo",
    "env",
    "time",
    "command",
    "nice",
    "nohup",
    "stdbuf",
    "ionice",
    "xargs",
    "watch",
}

# Value-taking flags across the wrappers above (consume the following token):
# xargs -I/-n/-P/-s/-L/-d/-a/-E, env -u, nice -n, ionice -c/-n, stdbuf -i/-o/-e.
# Skipping the value avoids mistaking `{}` in `xargs -I {} grep` for the command.
_WRAPPER_VALUE_FLAGS = {
    "-I",
    "-n",
    "-P",
    "-s",
    "-L",
    "-d",
    "-a",
    "-E",
    "-u",
    "-c",
    "-i",
    "-o",
    "-e",
    "--replace",
    "--max-procs",
    "--max-lines",
}

_ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_]\w*=")

# Truthy-enough override values. Anything not in the "off" set enables it.
_OVERRIDE_OFF = {"", "0", "false", "no", "off"}


def _has_override(command: str) -> bool:
    """True if the command carries `NOORINA_ALLOW_GREP=<truthy>` as an env prefix."""
    tokens = tokenize(strip_heredocs(command))
    if not tokens:
        return False
    for tok in tokens:
        if tok.startswith("NOORINA_ALLOW_GREP="):
            val = tok.split("=", 1)[1].strip().lower()
            if val not in _OVERRIDE_OFF:
                return True
    return False


def _effective_command(segment: list[str]) -> str | None:
    """Return the basename of the segment's effective command, peeling wrappers.

    Peels leading env-assignments and known exec wrappers (`sudo`, `env`,
    `xargs`, …) plus their flags, so `sudo grep`, `env X=1 grep`, and
    `xargs -I {} grep` all resolve to `grep`. Returns None on an empty segment.
    """
    i = 0
    n = len(segment)
    while i < n:
        tok = segment[i]
        # Leading one-shot env-var assignments (`FOO=bar grep ...`).
        if _ENV_ASSIGN_RE.match(tok):
            i += 1
            continue
        base = os.path.basename(tok)
        if base in _WRAPPERS:
            i += 1
            # Skip this wrapper's flags (and any value they consume).
            while i < n:
                nxt = segment[i]
                if nxt.startswith("-"):
                    # `--flag=value` is one token; `-I {}` / `--replace {}` is two.
                    consume_value = nxt in _WRAPPER_VALUE_FLAGS and "=" not in nxt
                    i += 1
                    if consume_value and i < n:
                        i += 1
                    continue
                if _ENV_ASSIGN_RE.match(nxt):  # `env FOO=bar grep`
                    i += 1
                    continue
                break
            continue
        # First non-wrapper, non-env token is the effective command.
        return base
    return None


def _segments(command: str) -> list[list[str]] | None:
    """Command-position segments via the AST path, falling back to shlex.

    Returns None only when BOTH parsers fail (caller fails open). The AST path
    additionally surfaces `grep` inside `$(...)` command substitutions.
    """
    cleaned = strip_heredocs(command)
    ast = iter_command_segments_ast(cleaned)
    if ast is not None:
        return ast
    tokens = tokenize(normalize_command_separators(cleaned))
    if tokens is None:
        return None
    return list(iter_command_segments(tokens))


def _suggest(command: str) -> str:
    """A best-effort `rg` rewrite hint for the common flag shapes."""
    # Only a light touch — the full flag map lives in TOOLCHAIN.md.
    hint = re.sub(r"\b(e|f)?grep\b", "rg", command).strip()
    if len(hint) > 200:
        hint = hint[:200] + " …"
    return hint


def check(input_data: dict) -> dict | None:
    """Block a bare grep invocation. None to allow, dict to block."""
    if input_data.get("tool_name", "") != "Bash":
        return None

    command = input_data.get("tool_input", {}).get("command", "")
    if not command or "grep" not in command:
        return None  # cheap prefilter — nothing grep-shaped at all

    if _has_override(command):
        return None

    segments = _segments(command)
    if segments is None:
        return None  # unparseable → fail open (convention gate, not security)

    if not any(_effective_command(seg) in _GREP_CMDS for seg in segments):
        return None

    result = {
        "decision": "block",
        "reason": (
            "BLOCKED: bare `grep` — this org uses `rg` (ripgrep) for text search, "
            "never plain `grep` (#1008; on this box `grep` is actually `ugrep`).\n"
            f"Suggested rewrite:\n    {_suggest(command)}\n"
            "grep→rg flags: `-r/-rn`→(default; `-n` for line numbers), `-E`→(default), "
            "`-F`→`-F`, `-o/-c/-l/-v/-i/-w`→same. "
            "GOTCHA: `rg` skips .gitignore'd paths by default — add `--no-ignore` "
            "(or `-uu`) when the target can be git-ignored (e.g. ontology/structural/) "
            "or you get a silent zero. "
            "Structural (AST) search → use `ast-grep`. "
            "Genuine grep-only need (rare): prefix with `NOORINA_ALLOW_GREP=1`. "
            "See docs/TOOLCHAIN.md § Text search: rg, not grep."
        ),
    }
    log_pretooluse_block("block_bare_grep", command, result["reason"])
    return result


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    result = check(input_data)
    if result and result.get("decision") == "block":
        print(json.dumps(result))
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
