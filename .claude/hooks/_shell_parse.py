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

    normalize_command_substitutions(cmd) -> str
        Quote/escape-aware rewrite of command-substitution and subshell edges
        (`$(`, `(`, the matching `)`, and backticks) into standalone ` ; `
        separators, so `url=$(gh issue create … --label meta-issue)` survives
        shlex with the closing paren OFF the last argument and the `gh` OFF the
        assignment. The shlex-path counterpart of what
        `iter_command_segments_ast` gets from a real grammar — needed because
        bashlex is optional AND cannot parse a `<<'EOF'` heredoc at all. A `)`
        at depth 0 (a `case` arm) is left alone; quoted/escaped parens and
        backticks are DATA and never touched. main#1351.

    strip_heredocs(cmd) -> str
        Removes <<DELIM .. DELIM, <<'DELIM' .. DELIM, <<"DELIM" .. DELIM and
        <<-DELIM .. DELIM heredoc bodies (delimiter is rfc-shell-style: any
        word). Handles repeated/nested heredocs by iterating until the regex
        is fixed.

    classify_heredocs(cmd) -> tuple[HeredocSpan, ...]
        Every heredoc in `cmd` with the verdict on what CONSUMES it: a body fed
        to `bash`/`sh`/`zsh`/`dash`/`ksh` (directly, or piped out of the opening
        command) is `is_code=True`; a body fed to `cat`/`tee`, with or without a
        file redirect, is `is_code=False` — inert text. Every ambiguity resolves
        to `is_code=True`, so a misparse preserves a caller's blocking behaviour
        rather than opening a hole (main#1152).

    strip_data_heredocs(cmd) -> str
        The complement of `strip_heredocs`: drops ONLY the `is_code=False`
        bodies, keeping the ones a shell will execute. This is what a
        bypass/gate matcher wants — scanning a `cat > notes.md <<'EOF' … EOF`
        body for shell-injection shapes finds only documentation, while a
        `bash <<'EOF' … EOF` body is genuinely executable and must stay visible.

    iter_command_segments(tokens) -> Iterator[list[str]]
        Splits a token list on the shell-control tokens `;`, `&&`, `||`, `|`
        (these survive shlex.split as their own tokens because they're not
        inside quotes), strips leading `KEY=value` env-var assignments from
        each segment, and yields the surviving tokens.

    resolve_simple_assignments(command) -> str
        Bounded assignment-aware pre-pass (main#1195): resolves a leading
        `NAME=value` assignment (bare literal value only — no `$`,
        backticks, parens, or whitespace; an optional single leading
        `export`/`declare` keyword is tolerated, #1305) and substitutes
        later `$NAME` / `${NAME}` references with that value, so
        `g=git; $g commit` normalizes to `git commit` before either the
        indirect-exec detector or the direct commit-segment finder sees it.
        Resolution is POSITIONAL, not a single flat last-wins map: each
        pipeline segment is substituted using only the assignment state
        accumulated from segments STRICTLY BEFORE it, in source order — the
        same rule a real shell applies. This closes the order-blind hole a
        flat map opens (main#1195 review round 2): `g=git; $g commit -m x;
        g=echo` must still resolve `$g` to `git` at the commit site even
        though `g` is reassigned afterward, and — the mirror image a naive
        "first assignment wins" flip would introduce — `g=echo; $g commit;
        g=git` must NOT resolve `$g` to `git`, because that reassignment
        hasn't happened yet at the point `$g` is used.
        Returns `command` unchanged when tokenize() fails or no qualifying
        assignment is found — can only ADD a detection, never remove one.
        Deliberately does not resolve command substitution (`d=$(date)`),
        positional/special parameters (`$1`, `$?`, ...), or multi-word/prose
        values — see the module comment above the implementation for the
        false-positive this excludes.

    iter_command_segments_ast(command) -> list[list[str]] | None
        Structural (bashlex) alternative to tokenize + iter_command_segments:
        parses `command` into a real Bash AST and returns every
        command-position token segment, walking `&&`/`;`/`||` lists, `|`
        pipelines, `$(...)`/backtick command substitutions, and compound
        bodies. Each segment is the command's word tokens (env-var
        AssignmentNode prefixes excluded) in the SAME shape the shlex path
        emits — so `find_git_subcommand` / `extract_dash_c_pairs` consume AST
        segments unchanged. Returns None when bashlex is unavailable (degraded
        mode) OR the command fails to parse; callers MUST fall back to the
        shlex/regex path and must never treat None as "allow" for a
        security-relevant matcher. A real grammar removes the regex/shlex
        confusion between a command-position `git commit` and the literal
        phrase inside a heredoc body, a quoted arg, or a `--body` value — the
        root of the #118/#134/#144/#188/#189/#216/#223/#226/#227 bug trail
        (#748 D3b).

    bashlex_available() -> bool
        True iff the optional `bashlex` dependency imported successfully at
        module load. The commit-identity hook checks this to decide whether
        the structural path is active or it must warn + run in degraded
        regex-fallback mode. bashlex is the ENFORCED parser in CI + pre-commit
        (where the dependency is declared); a bare checkout without it still
        works via the shlex/regex fallback (zero-setup-on-pull is preserved).

    strip_command_prefixes(segment, *, compound_leaders=True) -> list[str]
        Drops the leading run of transparent command-prefix wrappers
        (`timeout 45`, `env`, `nohup`, `sudo`, ...) and — when
        `compound_leaders=True` — compound-statement keywords (`do`, `then`,
        `if`, ...), returning the tokens of the command that runs (main#1141).

        **Lockstep invariant:** every function in this module that keys on a
        command-position token must apply this strip — `find_git_subcommand`,
        `find_gh_subcommand`, `extract_dash_c_pairs`,
        `extract_leading_cd_target`. A new segment-consuming helper that
        skips it re-opens the main#1141-review regression: two functions
        reading ONE segment with different views of where the command starts.
        That produced a FALSE POSITIVE (a compliant
        `timeout 60 git -c user.name=… commit` blocked for a missing flag it
        had passed), which is strictly worse than the evasion the strip was
        added to close.

        **…but the invariant binds MATCHERS, not every consumer.** Round 3 of
        the same review: applying it uniformly shipped a live misroute. Which
        rule a caller follows is decided by what it DOES with the answer:

          - **Gate matcher** (validates/blocks a command) — strip everything.
            Over-matching a guarded body is conservative: worst case you
            inspect a command that would not have run. `find_git_subcommand`,
            `find_gh_subcommand`, `extract_dash_c_pairs`.
          - **Routing resolver** (decides which repo/target an action hits) —
            strip NOTHING. Over-matching is destructive: it sends output where
            the command never went, and three hooks downstream WRITE.
            `extract_leading_cd_target` is the only one in this module, and it
            opts out entirely (a leader may not run; and an exec-wrapper
            cannot carry `cd` at all, since `cd` is a shell builtin). As of
            main#1151 it does not consume segments at all — it reads the AST,
            because the three properties that make a `cd` honourable are not
            recoverable from a flattened segment list at any strip setting.

        `compound_leaders=False` exists for a caller that wants wrappers but
        not leaders. Nothing needs it today — the one routing caller wants
        neither — but the flag keeps the two prefix families separable rather
        than welded together for whoever needs the middle position next.

        `test_strip_lockstep_across_segment_consumers` pins the invariant;
        `CdRoutingAgainstShellTruth` pins the carve-out against a real shell.

    find_git_subcommand(segment) -> tuple[list[str], list[str]] | None
        Given a single segment's tokens, returns (global_opts, [subcommand,
        ...rest]) if it's a `git ...` invocation, else None. Skips git
        global options (`-c k=v`, `-C dir`, `--git-dir=...`,
        `--work-tree=...`, etc.) so the returned subcommand is the actual
        git verb (`commit`, `config`, `worktree`, ...). Leading wrappers /
        compound keywords are stripped first (main#1141), so
        `timeout 60 git commit ...` and `do git commit ...` resolve.

    find_gh_subcommand(segment) -> tuple[list[str], list[str]] | None
        Same shape for `gh ...`. Returns (gh_global_opts, [topic, action,
        ...rest]) — e.g. ([], ["pr", "create", "--repo", ...]). Same
        leading-wrapper / compound-keyword tolerance (main#1141), so
        `timeout 45 gh issue edit ...` and the `do`-prefixed body of a
        `for … ; do gh issue edit … ; done` loop both resolve.

    is_gh_subcommand(tokens, *verbs) -> bool
        Yes/no convenience for "does this token list contain a `gh <verb1>
        <verb2> ...` invocation?". Walks the token stream allowing the
        match at any position. Use this when you only need the boolean,
        not the post-verb tail; use `find_gh_subcommand` when you need
        to inspect the tail.

    walk_flag_values(tokens, wanted) -> list[str]
        Walks `tokens` and returns the value of every flag in `wanted`,
        in source order. Handles the two-token form (`--flag value`), the
        equals form (`--flag=value`), and the attached-short form
        (`-Rvalue`, single-char short flags only — `--repofoo` is never
        split). Values inside another flag's value (e.g. inside
        `--body "...--flag X..."`) are correctly ignored because they
        arrive as a SINGLE shlex token, never preceded by a flag from
        `wanted`.

        gh/cobra semantics hardening (main#1060):
          - A value-less flag immediately followed by a flag-shaped token
            (starts with `-`) does NOT consume that token as its value —
            real gh/cobra errors ("flag needs an argument") rather than
            silently swallowing the next flag. The flag-shaped token is
            left for the scan to process in its own right.
          - A literal `--` token (POSIX end-of-options) stops the scan
            entirely — everything after it is positional, never a flag,
            matching real `gh`/cobra behavior.
          - Repeated occurrences of the same flag are returned in source
            order (first-to-last); this helper does NOT pick a winner.
            Callers that need real gh's last-flag-wins semantics for a
            single-value `StringVarP` flag (e.g. `--repo`/`-R`) must take
            `values[-1]`; callers accumulating a repeatable flag (e.g.
            `--add-label`) iterate all of `values` — see
            `_repo_flag_parse.extract_repo` for the former and
            `validate_labels.extract_labels` for the latter.

    first_flag_value(command, wanted, *, regex_fallback=True) -> str | None
        Convenience wrapper: tokenizes `command` via `tokenize()` and
        returns the first value from `walk_flag_values()`. If tokenize
        fails AND `regex_fallback=True` (the default), falls back to a
        boundary-anchored regex per the public tokenize contract.
        Security-critical matchers should pass `regex_fallback=False`
        to fail closed on parse failure.

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

    extract_leading_cd_target(command) -> str | None
        The ROUTING resolver: the directory the shell is in when the
        command's first real work runs, or None when that cannot be
        established with certainty. Honours only the UNCONDITIONAL LEADING
        RUN of `cd <absolute-dir>` commands — a `cd` must be (1)
        unconditional, (2) executed by the current shell, and (3) positioned
        before the work. Reads the bashlex AST (not the flattened segment
        list, which has already discarded the control flow that decides
        whether a `cd` runs), with a fail-closed token scan as a CO-PRIMARY
        for the commands bashlex cannot parse — notably any quoted-delimiter
        heredoc (`<<'EOF'`), which raises rather than yielding an AST.
        main#1151.

    resolve_invocation_cwd(input_data) -> str
        Like resolve_tool_cwd, but FIRST tries to recover the directory the
        command actually runs in via `extract_leading_cd_target`. This closes
        the #521 residual: for a worktree subagent the harness `cwd` field is
        captured at agent-spawn time (the orchestrator's dir), NOT the
        subagent's dir after it has `cd`'d into its worktree, and subsequent
        `cd` calls do not propagate back to the hook's view of `cwd`. When the
        triggering command is `cd /path/to/worktree && gh pr create ...`, the
        cd target is the only in-band signal that recovers the real repo.
        Falls back to resolve_tool_cwd (stdin cwd → os.getcwd()) when no
        honourable leading `cd` is present. Only absolute existing directories
        are honored.

    resolve_repo_short_name(input_data, *, git_runner=None) -> str | None
        Resolve the GitHub repository NAME (e.g. `noorinalabs-main`) from the
        invocation cwd's `origin` remote. This mirrors how `gh` itself
        resolves a `gh issue edit/create ...` invocation that OMITS `--repo`:
        it falls back to the ambient git context. Hooks that need the repo
        name to drive a GraphQL/REST call (e.g. the Wave-field sync and the
        kickoff-comment hooks) call this to recover the repo when the parsed
        command carried no `--repo` flag. Returns the last path segment of
        the `origin` URL with any trailing `.git` stripped, or None when the
        cwd is not a git repo / has no origin / the runner fails. The
        `git_runner(cwd) -> str | None` injection point lets tests avoid
        shelling out (#650).

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
import subprocess
from functools import lru_cache
from typing import Iterator, NamedTuple

# Optional structural dependency (#748 D3b). bashlex gives a real Bash-AST
# parse for the commit-identity matcher. It is imported defensively so a
# freshly-pulled checkout's hooks keep working with ZERO install step (the same
# zero-setup-on-pull guarantee as the git-transferable memory) — if bashlex is
# absent the parser silently degrades to the shlex/regex path and the consuming
# hook surfaces a single stderr warning. bashlex.* missing stubs are handled by
# the `[[tool.mypy.overrides]]` entry in pyproject.toml.
try:
    import bashlex
    from bashlex import ast as bashlex_ast

    _BASHLEX_AVAILABLE = True
except ImportError:  # pragma: no cover - degraded mode is exercised via monkeypatch
    bashlex = None
    bashlex_ast = None
    _BASHLEX_AVAILABLE = False

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


@lru_cache(maxsize=256)
def _tokenize_cached(cmd: str) -> tuple[str, ...] | None:
    """Memoized core of tokenize(). Returns an IMMUTABLE tuple (never a list).

    A single Bash tool call re-tokenizes the same command string many times
    (12 shlex.split passes across 11 PreToolUse hooks — #1113). shlex.split is
    pure in `cmd`, so the result is cached. The cache stores a tuple, never a
    list, so the shared cached object can never be mutated by a caller — the
    public tokenize() wrapper copies it into a fresh list at the boundary.
    """
    try:
        return tuple(shlex.split(_LINE_CONTINUATION_RE.sub(" ", cmd), posix=True))
    except ValueError:
        return None


def tokenize(cmd: str) -> list[str] | None:
    """shlex.split the command. Return None on parse error (unbalanced quote).

    Normalizes POSIX line-continuation sequences (backslash + newline) to a
    single space before tokenizing. Without this, shlex.split(posix=True)
    emits the trailing newline as a stray token that breaks command-position
    detection (issue #287).

    Memoized (#1113): the shlex work is cached via `_tokenize_cached`, but a
    FRESH list copy is returned on every call. Callers therefore keep the
    historical mutable-list contract (they may append/pop/slice-assign the
    result) with ZERO risk of corrupting the shared cache entry for the next
    caller. Never return the cached tuple directly.
    """
    cached = _tokenize_cached(cmd)
    return None if cached is None else list(cached)


@lru_cache(maxsize=256)
def normalize_command_separators(cmd: str) -> str:
    """Quote/escape-aware normalization of shell command separators.

    shlex.split treats a NEWLINE as ordinary whitespace and only recognizes
    `;`/`&&`/`||`/`|` as standalone tokens when they are ALREADY surrounded by
    whitespace. So two very common orchestrator idioms defeat
    `iter_command_segments`, which relies on those separators surviving
    tokenization as their own tokens:

        cd "$(git rev-parse --show-toplevel)"\\n gh issue edit N --add-label ...
        cd /some/dir; gh issue edit N --add-label ...

    In the first the newline vanishes into whitespace, so `cd`, the command
    substitution, and `gh` collapse into ONE segment whose first token is
    `cd` — `find_gh_subcommand` bails and the parser returns empty (issue
    #901: kickoff-comment + Wave-field-sync PostToolUse hooks silently skip).
    In the second the `;` sticks to `/some/dir` (`/some/dir;`), so again no
    separator token is produced.

    This helper rewrites the raw command so shlex WILL emit the separators as
    standalone tokens:
      - line-continuation `\\<newline>` -> a single space (a continued command
        is ONE command, not two — done first so a continuation newline is not
        misread as a command separator);
      - an unquoted, unescaped NEWLINE -> ` ; ` (newline is a command
        terminator in shell, equivalent to `;`);
      - an unquoted, unescaped `;` / `|` / `&&` / `||` -> the same operator
        space-padded on both sides.

    Quote/escape awareness is essential: a `|`/`;`/`&&`/newline INSIDE a single
    or double quoted string (e.g. `--body "x && y"`, a multi-line
    `--body "line1\\nline2"`) or preceded by a backslash is DATA, not a
    separator, and is left byte-for-byte untouched. The result is only ever
    fed back through `tokenize` (which re-applies line-continuation
    normalization harmlessly), so injecting extra spaces around genuine
    operators cannot change the parsed argument values.

    Memoized (#1113): pure in `cmd` and returns an immutable `str`, so the
    cached value is returned directly — no copy needed, no mutation hazard.
    """
    cmd = _LINE_CONTINUATION_RE.sub(" ", cmd)
    out: list[str] = []
    i = 0
    n = len(cmd)
    quote: str | None = None  # active quote char: "'" or '"', else None
    while i < n:
        c = cmd[i]
        if quote is not None:
            out.append(c)
            # Inside double quotes a backslash escapes the next char; inside
            # single quotes nothing is special (shell single-quote semantics).
            if c == "\\" and quote == '"' and i + 1 < n:
                out.append(cmd[i + 1])
                i += 2
                continue
            if c == quote:
                quote = None
            i += 1
            continue
        if c in ("'", '"'):
            quote = c
            out.append(c)
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            # Escaped char outside quotes — emit both, do not treat as separator.
            out.append(c)
            out.append(cmd[i + 1])
            i += 2
            continue
        if c == "\n":
            out.append(" ; ")
            i += 1
            continue
        if cmd[i : i + 2] in ("&&", "||"):
            out.append(" " + cmd[i : i + 2] + " ")
            i += 2
            continue
        if c in (";", "|"):
            out.append(" " + c + " ")
            i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


@lru_cache(maxsize=256)
def normalize_command_substitutions(cmd: str, *, separator: str = " ; ") -> str:
    """Quote/escape-aware normalization of command-substitution + subshell edges.

    `normalize_command_separators` teaches shlex where one command in a
    PIPELINE ends. It says nothing about the other boundary a shell has: the
    edge of a command SUBSTITUTION or a subshell. shlex.split treats `$(`,
    `` ` ``, `(` and `)` as ordinary word characters, so the single most common
    "file the issue, then use its URL" idiom —

        url=$(gh issue create --repo o/r --label tech-debt --label meta-issue)

    tokenizes with the closing paren GLUED to the last argument
    (`meta-issue)`), and with the first token of the substituted command glued
    to the assignment (`url=$(gh`). Both are live defects, not hypotheticals:
    the glued paren made `validate_labels` demand a label literally named
    `meta-issue)` and block the filing of main#1150 (main#1351), and the glued
    head hides the invocation from `is_gh_subcommand`/`find_gh_subcommand`
    entirely, so a matcher anchored on either silently does nothing for every
    `$(gh …)` / `$(git …)` command that has no wrapper word after the paren.

    This helper rewrites the raw command so those boundaries survive
    tokenization as their own separators:

      - an unquoted, unescaped `$(` or `(`  -> ` ; ` (and pushes a depth level)
      - the `)` that CLOSES one of those    -> ` ; `
      - an unquoted, unescaped backtick     -> ` ; `

    A `)` at depth 0 is left byte-for-byte alone: an unmatched closer is either
    a `case` pattern arm (`a) …;;`) or a syntax error, and neither is ours to
    rewrite. Quote characters themselves are never added or removed, so a
    command that tokenized before still tokenizes after, and one that failed
    still fails (the fail-open contract on `tokenize() is None` is unaffected).

    Quote handling is NOT the same rule as `normalize_command_separators`
    (main#1414 — read this before adopting this helper)
    =====================================================================

    That analogy is tempting and wrong, and the difference is one-sided:

        construct                     inside "double quotes", real sh   here
        ---------------------------   -------------------------------   ----
        `;`  `|`  `&`   separators     literal — data                    data
        `$( … )`, backticks            EXECUTED                          data

    A double-quoted command substitution really is a substitution in POSIX
    shell. This helper deliberately treats it as data anyway, and that choice
    has a DIRECTION:

      - For a false-positive-sensitive VALIDATOR (`validate_labels`, the only
        caller today) it is the safe direction, and load-bearing: leaving
        `--body "$(cat b.md)"` untouched is exactly what stops the common
        quoted-substitution shape from truncating the segment and costing label
        recall.
      - For a BYPASS MATCHER it points the other way. A hook that adopted this
        helper to find what a command really runs would read a double-quoted
        substitution handed to `sh -c` as inert text — fail OPEN in a
        fail-CLOSED context. `_shell_parse` is shared by commit-identity and
        other blocking matchers, so this is stated here rather than left for an
        adopter to discover: **do not use this helper as-is in a blocking
        matcher** without first extending it to double-quoted substitutions.

    Single quotes are not in that hazard — `'$(cat f)'` is genuinely literal in
    shell, so treating it as data agrees with the shell rather than diverging.
    `test_double_quoted_substitution_is_deliberately_treated_as_data` pins the
    divergence so a future change to it is a decision, not an accident.

    `separator` — the two readings of a substitution boundary
    ==========================================================

    The default ` ; ` SPLITS: the substituted command becomes its own segment,
    and any flags that followed the closing paren start a further segment. That
    is the safe reading for a matcher, and the one every caller should use.

    `separator=" "` SPLICES instead: the punctuation is dropped and the
    substituted command's words merge into the surrounding command's own
    argument list. That is measurably NOT safe to match on — it makes the
    substitution's first word look like the value of whatever flag preceded it:

        gh issue create --repo o/r --label $(cat labelfile)
          split  -> no labels          (the flag's value is not knowable)
          splice -> label named 'cat'  (the COMMAND NAME, read as a label)

    `cat` is not a label in any repo here, so a caller that validated the
    spliced reading would BLOCK that command — a false positive manufactured by
    the parse, which is the whole defect class main#1351 exists to remove. The
    splice reading is therefore offered for DIFFERENTIAL DIAGNOSIS only: compare
    it against the split reading to detect that a substitution swallowed some
    flags, then report that loss rather than acting on the spliced values.
    `validate_labels._extract_labels` is the reference use. Never validate,
    block on, or route from a spliced token.

    Segment CONTENT is deliberately preserved rather than deleted: the
    substituted command is real work that a gate matcher usually wants to see
    (`url=$(gh issue create …)` genuinely creates an issue). Splitting rather
    than stripping is what lets `iter_command_segments` hand it to
    `find_gh_subcommand` as an ordinary segment.

    This is the shlex-path counterpart of what `iter_command_segments_ast`
    gets for free from a real grammar. It exists because the AST path is not
    always available: bashlex is optional, and — measured, see
    `test_bashlex_cannot_parse_quoted_delimiter_heredoc` — it cannot parse a
    `<<'EOF'` heredoc at all, which is the dominant heredoc form here. A fix
    that lived only in the AST path would regress to the glued-paren bug on
    every command carrying a quoted-delimiter heredoc, and on any checkout
    without bashlex installed.

    Memoized (#1113): pure in `cmd` and returns an immutable `str`.
    """
    if not any(ch in cmd for ch in "()`"):
        return cmd
    out: list[str] = []
    i = 0
    n = len(cmd)
    quote: str | None = None  # active quote char: "'" or '"', else None
    depth = 0
    while i < n:
        c = cmd[i]
        if quote is not None:
            out.append(c)
            # Inside double quotes a backslash escapes the next char; inside
            # single quotes nothing is special (shell single-quote semantics).
            if c == "\\" and quote == '"' and i + 1 < n:
                out.append(cmd[i + 1])
                i += 2
                continue
            if c == quote:
                quote = None
            i += 1
            continue
        if c in ("'", '"'):
            quote = c
            out.append(c)
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            # Escaped char (incl. a line continuation) — emit both, verbatim.
            out.append(c)
            out.append(cmd[i + 1])
            i += 2
            continue
        if cmd[i : i + 2] == "$(":
            out.append(separator)
            depth += 1
            i += 2
            continue
        if c == "(":
            out.append(separator)
            depth += 1
            i += 1
            continue
        if c == ")" and depth > 0:
            out.append(separator)
            depth -= 1
            i += 1
            continue
        if c == "`":
            out.append(separator)
            i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


@lru_cache(maxsize=256)
def strip_heredocs(cmd: str) -> str:
    """Remove all heredoc bodies. Iterates until no more matches (handles nested).

    Memoized (#1113): the fix-point loop (up to 8 passes per Bash call across
    the hooks) is pure in `cmd` and returns an immutable `str`, so the cached
    value is returned directly — no copy needed, no mutation hazard.
    """
    prev = None
    cur = cmd
    while prev != cur:
        prev = cur
        cur = _HEREDOC_RE.sub("", cur)
    return cur


# ---------------------------------------------------------------------------
# Heredoc target classification (main#1152)
# ---------------------------------------------------------------------------
#
# `strip_heredocs` answers "where are the heredoc bodies?" but not "who eats
# them?", and every consumer that needs the second question has so far guessed.
# `validate_commit_identity._detect_indirect_commit` ran its indirect-exec
# matchers over the RAW command, so a heredoc body was scanned for bypass
# shapes regardless of what the heredoc was attached to — documenting the shape
#
#     cat > notes.md <<'EOF'
#     the bypass looks like: bash -c 'git commit …'
#     EOF
#
# was blocked as if it WERE that invocation, while the identical bytes written
# through the `Write` tool sailed through (main#1152).
#
# The distinction the matchers need is a property of the heredoc's TARGET:
#
#   - fed to `bash`/`sh`/`zsh`/`dash`/`ksh` (directly, or via a pipe out of the
#     opening command) -> the body is CODE the shell will execute. A real
#     bypass surface; must stay scannable.
#   - fed to `cat`/`tee`, with or without a `>`/`>>` file redirect -> the body
#     is DATA. Inert text; scanning it produces false positives only.
#
# Why not bashlex here, despite it being the structurally "right" tool and
# already a dependency of this module: **bashlex cannot parse a quoted-delimiter
# heredoc at all**. `bashlex.parse("cat <<'EOF'\nx\nEOF")` raises
# `ParsingError: here-document ... delimited by end-of-file (wanted "'EOF'")`,
# and the same for `<<"EOF"`. Only the bare `<<EOF` / `<<-EOF` forms parse.
# `<<'EOF'` is the dominant form in practice (it is the form in the #1152
# reproduction), so an AST-only classifier would not answer the question in the
# very case that motivated it. This is a measured property of the installed
# parser, not a style preference — see the regression test
# `test_bashlex_cannot_parse_quoted_delimiter_heredoc`, which pins it so that a
# future bashlex upgrade that fixes it will fail loudly and invite this comment
# to be revisited.
#
# The classifier is therefore a quote-aware line scanner. Every ambiguity
# resolves toward CODE (scan the body) so a misparse can only ever preserve
# today's blocking behaviour, never open a hole:
#
#   - owner command not recognised, or unresolvable  -> CODE
#   - heredoc never terminated                       -> CODE (and everything
#                                                       after it is left alone)
#   - delimiter not a bare `\w+` word                -> opener not recognised,
#                                                       body treated as ordinary
#                                                       command text (unstripped)

# The POSIX shells whose heredoc body is executed as shell code. Single source
# of truth: `validate_commit_identity` builds its `_INTERPRETERS` regex
# alternation from this set, so the "which heredocs are code?" answer used by
# the strip pass can never drift from the one used by the block pass. `mksh` /
# `pdksh` stay out for the same conservative reason as #482.
SHELL_INTERPRETERS = frozenset({"bash", "sh", "zsh", "dash", "ksh"})

# Commands whose heredoc body is inert data: they copy stdin to stdout and/or a
# file and never interpret it. Deliberately a tiny ALLOWLIST rather than a
# denylist of interpreters — an unknown command keeps today's scan-the-body
# behaviour, so growing this set is the only way to unblock anything and each
# addition is an explicit, reviewable decision.
HEREDOC_DATA_SINKS = frozenset({"cat", "tee"})

# ---------------------------------------------------------------------------
# Downstream-relay default (main#1168)
# ---------------------------------------------------------------------------
#
# `_opener_feeds_interpreter`'s pipe-follow walk (condition 3 below) used to
# resolve an unrecognised downstream segment head toward DATA ("not proven to
# be an interpreter, so keep walking; if nothing downstream matches, the body
# is inert"). That is backwards relative to every other ambiguity in this
# module, which resolves toward CODE (main#1152's own rule), and it is a
# measured live bypass: a RELAY command that is not itself a member of
# `SHELL_INTERPRETERS` but hands its stdin to one defeats the walk entirely —
#
#     cat <<'DELIM' | xargs -I{} bash -c "{}"
#     git -c user.name=X -c user.email=Y commit -m z
#     DELIM
#
# `xargs` is not an interpreter, so the old walk found nothing and returned
# DATA; the body — a real `git commit` — genuinely runs (real-shell-verified
# with a marker proxy: a marker command appended to a log file, confirmed to
# execute). The same family: `parallel`, `env -S`, and (for the OTHER
# classifier, main#1167's cross-segment write-then-exec correlation —
# out of scope for the fix here, see that module's comment) `find -exec`.
#
# The fix: an unrecognised downstream segment head now resolves to CODE,
# matching the rest of this module's posture. `HEREDOC_INERT_RELAY_FILTERS`
# below is the narrow escape hatch — the mirror image of `HEREDOC_DATA_SINKS`
# — for commands MEASURED to have no code-execution surface reachable from
# their own stdin content, so a legitimate documentation pipeline
# (`cat <<'EOF' | grep foo`) does not newly false-block. Same posture as
# `HEREDOC_DATA_SINKS`: a tiny, explicit, reviewed ALLOWLIST, never a
# denylist — an unlisted filter fails toward CODE, which is the entire point
# of inverting the default (an allowlist's safety property IS its default).
#
# Every entry here was verified with a real-shell marker probe — BOTH the
# plain invocation AND every exec-shaped flag the command exposes (a command
# appended to a log file inside the heredoc body / a marker script standing
# in for an external-program flag, checked for the log actually being
# written, in both bash and zsh) BEFORE being added, not reasoned from a man
# page and not measured on the bare invocation alone:
#
#   DID-NOT-RUN (genuinely inert — plain form AND every exec-shaped flag
#   probed — confirmed safe to allowlist):
#     grep, egrep, fgrep (incl. `-f -`), wc, uniq, head, tail, cut, tr,
#     column, nl, rev, fold, expand, unexpand, base64 (incl. `-d`),
#     md5sum (incl. `-c`), sha1sum, sha256sum, sha512sum, cksum, od,
#     xxd (incl. `-r`), hexdump (incl. `-e`), join, paste, comm, tac,
#     shuf (incl. `--random-source`), jq (incl. `env.PATH`, `$ENV.PATH`,
#     `input_filename`, `@sh` — no `system()` in mainline)
#
#   RAN (data-driven code-execution surface — DELIBERATELY EXCLUDED even
#   though they are common "genuinely inert filter" examples in casual
#   reasoning about this shape):
#     sed   — the GNU `e` flag/command executes the (input-derived) pattern
#             space as a shell command and substitutes its output; measured:
#             `cat <<'EOF' | sed 's/.*/&/e'` genuinely runs the body.
#     awk   — `system()` (and piped `print ... | "cmd"` / `getline < "cmd"`)
#             executes a command built from field/record data; measured:
#             `cat <<'EOF' | awk '{system($0)}'` genuinely runs the body.
#     sort  — `--compress-program=CMD` runs CMD with the heredoc's own data
#             on its stdin once the sort spills to a temp file (`-S` sets
#             the spill threshold; the padding needed to cross it is
#             attacker-controlled, same as any other input-size trigger);
#             measured: `cat <<'EOF' | sort -S 1 --compress-program=CMD`
#             genuinely runs CMD in both bash and zsh once enough body lines
#             are present to force a spill. The PLAIN invocation (no
#             `--compress-program`) is genuinely inert — this is why `sort`
#             shipped on this allowlist in the first place (main#1168's
#             original measurement covered only the bare form) — but a
#             plain invocation being inert is not sufficient, exactly as for
#             `sed`/`awk` below; the exec-shaped flag makes it unsafe as a
#             blanket allowlist member. Excluded per main#1316.
#     rg    — `--pre=COMMAND` runs COMMAND once "for each input PATH", and on
#             a heredoc-fed pipe a PATH is attacker-supplied: naming the pipe
#             itself (`/dev/stdin`, `/dev/fd/0`) gives `--pre` a PATH even
#             though the input is a pure stdin pipe, and `rg` runs
#             `COMMAND PATH` with that path opened on the child's own stdin
#             — so `sh /dev/stdin` genuinely executes the heredoc body;
#             measured: `cat <<'EOF' | rg --pre=/bin/sh pat /dev/stdin`
#             genuinely runs the body in both bash and zsh. `rg`'s ORIGINAL
#             addition to this allowlist (main#1316's first pass) measured
#             only the no-PATH stdin-pipe form — fixing the CONTEXT
#             (whether a PATH is present) instead of varying it, when that
#             context is exactly what an attacker controls. Separately, `rg`
#             also exposes `--hostname-bin=COMMAND`, a second exec-shaped
#             flag that spawns an arbitrary program even on a pure stdin
#             pipe with no PATH at all — but the spawned child gets no
#             arguments and does not inherit the pipe, so it never reaches
#             the heredoc body and is not a bypass on its own. Noted here
#             anyway because its existence falsifies any claim that every
#             `rg` flag is harmless on a heredoc-fed stdin pipe. Excluded
#             per main#1316 (second pass) — previously allowlisted in this
#             module's own first pass at the same PR, on a plain-form
#             measurement plus a #1008 policy argument (closing the
#             contradiction where this allowlist admitted forbidden `grep`
#             while omitting mandated `rg`); that policy argument is not a
#             safety argument, and the #1008 contradiction is left OPEN by
#             this exclusion — see the PR body.
#
# All four risks above are ARGUMENT-driven (visible in the segment's own
# tokens, not hidden in the heredoc body), so a narrower "allowlisted unless
# the script argument contains `e`/`system(`/`--compress-program`/`--pre`"
# rule is possible in principle — but that reintroduces a second,
# per-command detector inside what this set is meant to keep a flat,
# reviewable allowlist, and is deliberately left as a non-goal here:
# excluding `sed`/`awk`/`sort`/`rg` entirely accepts a real (if comparatively
# rare, in a documentation-pipeline context) false-positive cost in exchange
# for never having to get that per-command grammar right. `perl`, `python`,
# `ruby`, `php`, `xargs`, `parallel`, `find`, `env` and any other
# general-purpose interpreter or relay are excluded for the same reason, one
# level more obviously (they are not "filters" in the first place — some of
# them are exactly the relay family this fix targets).
HEREDOC_INERT_RELAY_FILTERS = frozenset(
    {
        "grep",
        "egrep",
        "fgrep",
        "wc",
        "uniq",
        "head",
        "tail",
        "cut",
        "tr",
        "column",
        "nl",
        "rev",
        "fold",
        "expand",
        "unexpand",
        "base64",
        "md5sum",
        "sha1sum",
        "sha256sum",
        "sha512sum",
        "cksum",
        "od",
        "xxd",
        "hexdump",
        "join",
        "paste",
        "comm",
        "tac",
        "shuf",
        "jq",
    }
)

# A heredoc opener: `<<EOF`, `<<'EOF'`, `<<"EOF"`, `<<-EOF`. Matched with
# `.match(line, i)` from a scanner that has already excluded `<<<` (here-string)
# and quoted regions, so no lookbehind is needed here.
_HEREDOC_OPENER_RE = re.compile(r"<<(?P<dash>-?)[ \t]*(?P<q>['\"]?)(?P<delim>\w+)(?P=q)")


class HeredocSpan(NamedTuple):
    """One heredoc found in a command, with the verdict on what consumes it.

    `body` excludes both the opener line and the terminator line. `is_code` is
    True when the body is fed to a shell interpreter (directly or through a
    pipe) — i.e. when scanning it for bypass shapes is correct. `terminated` is
    False when no delimiter line was found before end-of-input.
    """

    delim: str
    body: str
    is_code: bool
    terminated: bool


def _segment_head_command(seg_text: str) -> str | None:
    """Return the command name at the head of one pipeline segment, or None.

    Heredoc openers are removed first (they are redirects, not words), then the
    segment is tokenized and stripped of `KEY=value` prefixes and transparent
    wrappers (`env`, `timeout 30`, `sudo`, …) via the shared helpers, so
    `FOO=1 timeout 30 /bin/bash` resolves to `bash`. A leading path is reduced
    to its basename. Returns None when the segment does not tokenize or holds no
    word — callers must treat None as "unknown", never as "safe".
    """
    tokens = tokenize(_HEREDOC_OPENER_RE.sub(" ", seg_text))
    if tokens is None:
        return None
    tokens = strip_command_prefixes(_strip_leading_env_assignments(tokens))
    if not tokens:
        return None
    head = tokens[0]
    return head.rsplit("/", 1)[-1] if "/" in head else head


class _LineScan(NamedTuple):
    """Result of one quote-aware pass over a physical line."""

    segments: list[tuple[int, int, str]]  # (start, end, separator_before)
    openers: list[tuple[int, bool, str]]  # (position, is_dash_form, delimiter)
    procsubs: list[int]  # positions of unquoted `<(` / `>(`


def _scan_command_line(line: str) -> _LineScan:
    """Quote-aware single pass over one physical line.

    Separators (`;`, `|`, `&`, `&&`, `||`), heredoc openers and process
    substitutions inside single/double quotes or behind a backslash are DATA and
    are skipped, so `echo "a | b"` is one segment and `echo "<<EOF"` holds no
    opener.

    `|&` is ONE operator — bash/zsh shorthand for `2>&1 |` — and must be
    consumed as a pipe (main#1155 review round 2). Falling through to the
    single-character cases split it into `|` then `&`, leaving an empty segment
    between them and breaking the downstream walk on the `&`, so
    `cat <<'D' |& bash` walked around the pipe-to-shell block. That was strictly
    worse than either reading of the operator: treating it as a pipe catches the
    shape, treating it as backgrounding would at least be consistent.

    Two shapes must NOT be mistaken for control operators (main#1155 review, M2):

      - `2>&1`, `>&2`, `<&0` — the `&` is part of a redirect, not a separator.
        Splitting there resolved `cat 2>&1 > n.md <<'EOF'` to a head command of
        `1`, so #1152's own false positive survived for every redirect-carrying
        opener, and `cat <<'EOF' 2>&1 | bash` evaded the pipe-follow entirely.
      - `&>file`, `&>>file` — the same `&`, on the other side.

    Process-substitution positions are reported because `>(bash)` is a SECOND
    sink hanging off the same segment: `tee >(bash) <<'EOF'` executes the body
    even though the segment head is the inert `tee`. Recording them here (rather
    than substring-searching the segment text later) keeps the quote-awareness —
    a literal `>(` inside `cat > "weird>(name).md"` is not a process
    substitution and must not be treated as one.
    """
    segments: list[tuple[int, int, str]] = []
    openers: list[tuple[int, bool, str]] = []
    procsubs: list[int] = []
    quote: str | None = None
    seg_start = 0
    sep_before = ""
    i = 0
    n = len(line)
    while i < n:
        c = line[i]
        if quote is not None:
            if c == "\\" and quote == '"' and i + 1 < n:
                i += 2
                continue
            if c == quote:
                quote = None
            i += 1
            continue
        if c in ("'", '"'):
            quote = c
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            i += 2
            continue
        if line.startswith("<<<", i):
            # Here-string, not a heredoc: consumed inline, opens no body.
            i += 3
            continue
        if line.startswith("<<", i):
            m = _HEREDOC_OPENER_RE.match(line, i)
            if m is not None:
                openers.append((i, bool(m.group("dash")), m.group("delim")))
                i = m.end()
                continue
            i += 2
            continue
        two = line[i : i + 2]
        if two in ("<(", ">("):
            procsubs.append(i)
            i += 2
            continue
        if two == "|&":
            # bash/zsh shorthand for `2>&1 |` — ONE pipe operator, not `|`
            # followed by a backgrounding `&`. Splitting it in two left an empty
            # segment between them, and the downstream walk then broke on the
            # `&` before ever reaching the interpreter, so `cat <<'D' |& bash`
            # walked around the pipe-to-shell block this module adds. Emitting
            # it as a `|` is both correct and the conservative reading: it keeps
            # the pipeline connected, so the walk keeps looking for a sink.
            segments.append((seg_start, i, sep_before))
            sep_before = "|"
            i += 2
            seg_start = i
            continue
        if two in ("&&", "||"):
            segments.append((seg_start, i, sep_before))
            sep_before = two
            i += 2
            seg_start = i
            continue
        if c == "&" and (line[i - 1 : i] in ("<", ">") or line[i + 1 : i + 2] == ">"):
            # `2>&1` / `>&2` / `&>log` — a redirect, not a control operator.
            i += 1
            continue
        if c in (";", "|", "&"):
            segments.append((seg_start, i, sep_before))
            sep_before = c
            i += 1
            seg_start = i
            continue
        i += 1
    segments.append((seg_start, n, sep_before))
    return _LineScan(segments, openers, procsubs)


def _opener_feeds_interpreter(line: str, pos: int, scan: _LineScan) -> bool:
    """True if the heredoc opened at `pos` on `line` is consumed as shell code.

    A heredoc belongs to the pipeline segment it appears in. It is DATA only if
    EVERY sink that can reach its bytes is inert:

      1. the segment's head command is a known inert sink (`cat`, `tee`), AND
      2. that segment carries no process substitution, AND
      3. no segment downstream of it *in the same pipeline* is a shell
         interpreter, a RELAY that hands its stdin to one (main#1168), or
         itself carries a process substitution.

    Condition 2 is the one that is easy to miss, and missing it is a live
    bypass (main#1155 review, M1):

        tee >(bash) <<'DELIM'
        git -c user.name=X -c user.email=Y commit -m z
        DELIM

    The head word is the inert `tee`, but `>(bash)` is a SECOND sink hanging off
    the same segment, and the body really is executed — confirmed under both
    bash and zsh. Following only `|` never sees it, so the body was classified
    as data, stripped, and the commit sailed through. A process substitution
    anywhere in a reachable segment therefore forces CODE without trying to
    resolve what is inside it: an unresolvable sink resolves toward CODE, which
    is the rule the rest of this classifier already follows.

    Condition 3's downstream default is the OTHER historically-inverted case
    (main#1168): a downstream segment head that is not a known
    `SHELL_INTERPRETERS` member, a known `HEREDOC_DATA_SINKS` member (`cat`,
    `tee` — relaying to a FILE, not an interpreter, is exactly as inert
    downstream as it is in the owning-segment position), or a known-inert
    `HEREDOC_INERT_RELAY_FILTERS` member now resolves to CODE — not "keep
    walking, default to DATA" as before. A RELAY command (`xargs -I{} bash -c
    "{}"` and the same family via `parallel`/`env -S`) is not itself an
    interpreter, so the old walk found nothing downstream and returned DATA
    even though the body genuinely runs (real-shell-verified with a marker
    proxy). See the module comment above `HEREDOC_INERT_RELAY_FILTERS` for
    the full false-positive corpus that justifies the allowlist's contents.

    `&&`, `||`, `;` and `&` break the pipeline: what follows them does not
    receive this stdin. A `&` that is part of a redirect (`2>&1`) is not a
    separator at all — see `_scan_command_line`.
    """
    segments = scan.segments
    idx = next(
        (k for k, (start, end, _sep) in enumerate(segments) if start <= pos < end),
        None,
    )
    if idx is None:
        return True

    def _reachable_sink_is_code(k: int, *, head_must_be_inert_sink: bool) -> bool:
        start, end, _sep = segments[k]
        if any(start <= p < end for p in scan.procsubs):
            return True
        head = _segment_head_command(line[start:end])
        if head_must_be_inert_sink:
            return head not in HEREDOC_DATA_SINKS
        if head in SHELL_INTERPRETERS:
            return True
        # main#1168: an unresolved/unknown relay (including `head is None` —
        # the segment didn't tokenize) resolves to CODE. A downstream
        # `HEREDOC_DATA_SINKS` member (`cat`, `tee` — e.g. `| tee /tmp/a.md`
        # relaying to a FILE, not an interpreter) is just as inert here as it
        # is in the owning-segment position, so it joins
        # `HEREDOC_INERT_RELAY_FILTERS` as a reason to keep walking rather
        # than stop at CODE.
        return head not in HEREDOC_DATA_SINKS and head not in HEREDOC_INERT_RELAY_FILTERS

    if _reachable_sink_is_code(idx, head_must_be_inert_sink=True):
        return True
    for k in range(idx + 1, len(segments)):
        if segments[k][2] != "|":
            break
        if _reachable_sink_is_code(k, head_must_be_inert_sink=False):
            return True
    return False


# ---------------------------------------------------------------------------
# Cross-segment "write-then-exec" correlation (main#1167)
# ---------------------------------------------------------------------------
#
# `_opener_feeds_interpreter` answers "is this heredoc's body consumed by an
# interpreter reachable through a PIPE from the same physical line?" That is
# the wrong question for a heredoc whose owning segment redirects the body
# into a FILE (`cat > FILE <<'DELIM'`, or `tee FILE <<'DELIM'`) and a LATER
# segment — connected by `;`, a newline, or anything else, not a pipe —
# invokes an interpreter on that same file:
#
#     cat > /tmp/s.txt <<'DELIM'
#     git -c user.name=X -c user.email=Y commit -m z
#     DELIM
#     bash /tmp/s.txt
#
# `cat` is a recognised data sink and nothing downstream of it on the SAME
# line is a `|`-connected interpreter, so `_opener_feeds_interpreter` says
# DATA — correctly, for the question it answers. But the body reaches a real
# shell one command later. `_read_script_if_safe` (the OTHER existing defense,
# in validate_commit_identity) is structurally blind to this too: the hook
# fires PreToolUse, before `cat` has created the file, so reading it back
# fails and no content is inspected either — see the #1167 issue body for the
# full "why every matcher misses it" account. Belongs to the #1150 umbrella.
#
# The fix stays inside the classifier (the issue's preferred option 1):
# record the file path(s) a heredoc's owning segment writes the body to, and
# if ANY segment anywhere else in the same command later invokes a
# `SHELL_INTERPRETERS` member with that same path as its script operand,
# reclassify the body as CODE.
#
# Deliberately positionally-agnostic: a `bash /tmp/x` segment appearing
# BEFORE `cat > /tmp/x <<...` in the command still counts. A real shell would
# only execute meaningful content if the write happens first, but this is a
# security gate — main#1152's own rule ("every ambiguity resolves toward
# CODE") already commits this module to erring toward over-detection rather
# than depending on textual ordering to save a rare false positive.
#
# Deliberately NOT resolved through `iter_interpreter_invocations`: that
# helper's `strip_heredocs` call (the coarse, single-regex eraser — NOT the
# per-line `classify_heredocs`/`strip_data_heredocs` machinery) consumes
# everything from a heredoc opener through to its terminator in ONE pass,
# INCLUDING any command chained onto the OPENER's own line with `;` before
# the heredoc's first newline (`cat <<'DELIM' > /tmp/x; bash /tmp/x`, the
# issue's stated semicolon-equivalent shape). Measured:
# `_HEREDOC_RE.sub("", "cat <<'DELIM' > /tmp/x; bash /tmp/x\\n...")` erases
# "; bash /tmp/x" along with the heredoc syntax, so a target scan built on
# `iter_interpreter_invocations` would silently miss the semicolon variant
# even though `_opener_write_targets`/`_scan_command_line` (the mechanism the
# rest of this module already trusts) see it fine. This module's own per-line
# scan is reused instead — see `_iter_non_heredoc_segments` — which has no
# such erasure bug: it only ever skips a heredoc's OWN body lines, never
# trailing text on the opener's own line.
#
# Explicit scope boundary — NOT covered, by deliberate decision, not oversight:
#   - `source FILE` / `. FILE`: shell BUILTINS, not members of
#     `SHELL_INTERPRETERS`. Reading a file into the CURRENT shell is a
#     structurally different mechanism from spawning a new interpreter
#     process on it, and folding them in would widen `SHELL_INTERPRETERS`
#     itself — a set several OTHER matchers in this module and in
#     validate_commit_identity key on. That is a broader decision than this
#     fix and belongs in its own issue.
#   - `env bash FILE`: no new work needed here — `parse_interpreter_invocation`
#     already strips the `env` wrapper via `strip_command_prefixes` before
#     resolving the interpreter, so this shape already correlates correctly
#     through the same path as a bare `bash FILE`.
#   - A redirect target given via an unexpanded shell variable is not
#     RESOLVED — the hook cannot evaluate `$F` without running the shell, the
#     same documented punt this module already makes for `eval "$cmd"`. Note
#     the caveat: comparison here is by LITERAL TOKEN, not by value, so
#     `cat > "$F" <<'DELIM' ...; bash "$F"` is still caught — not because `$F`
#     was resolved, but because both sides spell the identical literal token
#     `$F`. A rename between the two positions (`cat > "$OUT" ...; F=$OUT;
#     bash "$F"`) or any other divergent spelling defeats it exactly as
#     variable resolution in general would.
#   - `bash < FILE` (script fed via stdin redirect rather than a positional
#     argument) IS now covered (main#1170): `parse_interpreter_invocation`
#     folds a bare `< FILE` redirect into `operands[0]`, the same slot this
#     correlation already reads via `_script_invocation_targets`, so a heredoc
#     written to FILE and later fed to an interpreter through `< FILE` (a
#     `mkfifo`-relayed FIFO, in main#1170's shape, or an ordinary regular
#     file) reclassifies as CODE without any new correlation machinery. This
#     resolves main#1287 shape 1 as a byproduct — its shapes 2 (`$(...)`
#     -produced path) and 3 (`cp` copy indirection) remain unresolved and stay
#     filed there. The pre-existing shape-7 walker in `validate_commit_identity`
#     (which reads a script's CONTENT off disk, not this module's path
#     correlation) is unaffected by this change either way: it fires
#     PreToolUse, before a same-command heredoc write has run, so the file it
#     would read never has the relevant content yet regardless of which
#     operand slot names it.
#   - The attached-operator redirect form with no surrounding whitespace
#     (`cat>/tmp/x`, as opposed to `cat > /tmp/x`) is not recognised by
#     `_segment_write_targets`'s tokenizer, which relies on shlex already
#     splitting `>`/`>>` into their own token — shlex only does that when
#     whitespace separates them. Every shape in the issue, and every heredoc
#     redirect in this codebase's own conventions, uses the spaced form.

# `tee`'s own value-less options. `tee` has no value-taking flags besides the
# attached-`=` long form `--output-error[=MODE]`, which never starts a new
# bare token and needs no entry here.
_TEE_BOOL_FLAGS = frozenset({"-a", "--append", "-i", "--ignore-interrupts", "-p", "--output-error"})


def _segment_write_targets(seg_text: str) -> list[str]:
    """File paths the DATA-SINK head of `seg_text` could write a heredoc body to.

    Two independent sources, both checked unconditionally:
      - a `>`/`>>` shell redirect (any command may carry one);
      - if the head command is `tee`, every non-flag positional argument
        (`tee` writes to each of its own file arguments, with or without an
        ADDITIONAL `>`/`>>` redirect).

    `cat` never contributes a positional target: `cat FILE` READS FILE, it
    does not write to it — only `cat`'s redirect (if any) is a write.
    """
    tokens = tokenize(_HEREDOC_OPENER_RE.sub(" ", seg_text))
    if not tokens:
        return []
    head = tokens[0].rsplit("/", 1)[-1]
    is_tee = head == "tee"
    targets: list[str] = []
    i = 1
    n = len(tokens)
    while i < n:
        tok = tokens[i]
        if tok in (">", ">>"):
            if i + 1 < n:
                targets.append(tokens[i + 1])
                i += 2
                continue
            i += 1
            continue
        if tok.startswith(">>") and len(tok) > 2:
            targets.append(tok[2:])
            i += 1
            continue
        if tok.startswith(">") and len(tok) > 1 and tok[1] not in ("(", "&", ">"):
            targets.append(tok[1:])
            i += 1
            continue
        if is_tee and tok not in _TEE_BOOL_FLAGS and not _looks_like_flag(tok):
            targets.append(tok)
        i += 1
    return targets


def _opener_write_targets(line: str, pos: int, scan: _LineScan) -> list[str]:
    """`_segment_write_targets` for the segment that OWNS the opener at `pos`."""
    idx = next(
        (k for k, (start, end, _sep) in enumerate(scan.segments) if start <= pos < end),
        None,
    )
    if idx is None:
        return []
    start, end, _sep = scan.segments[idx]
    return _segment_write_targets(line[start:end])


def _normalize_path_for_compare(path: str) -> str:
    """Loose normalization so `./x` and `x` — or a doubled slash — written two
    ways still compare equal. Deliberately narrow: `os.path.normpath` collapses
    redundant `.`/`//` segments only; it does NOT resolve against a cwd (the
    write and the invocation share the same shell cwd, so this is the right
    amount of normalization — resolving further would require knowing that
    cwd, which this module deliberately does not read) and does NOT expand a
    leading `~` (harmless either way here: `~/x` written identically on both
    sides already compares equal as a plain string, and there is no realistic
    same-command shape where the two sides spell a home-relative path
    differently — expanding `~` would add a branch with no distinguishing
    test, so it is left out).
    """
    try:
        return os.path.normpath(path)
    except (TypeError, ValueError):
        return path


def _iter_non_heredoc_segments(cmd: str) -> Iterator[str]:
    """Every pipeline segment in `cmd` that is NOT inside a heredoc body.

    Reuses the exact line-walk + terminator-search `_classify_heredocs_cached`
    and `strip_data_heredocs` already use, so a heredoc BODY line is never
    mistaken for a segment of the surrounding command (a body line containing
    the word `bash` must not itself look like an interpreter invocation).
    Deliberately NOT built on `iter_interpreter_invocations`/`strip_heredocs`
    — see the module comment above `_segment_write_targets` for the measured
    erasure bug that makes that helper unsuitable here.
    """
    lines = cmd.split("\n")
    n = len(lines)
    i = 0
    while i < n:
        line = lines[i]
        i += 1
        scan = _scan_command_line(line)
        for start, end, _sep in scan.segments:
            yield line[start:end]
        for _pos, dash_form, delim in scan.openers:
            j = i
            while j < n:
                candidate = lines[j].rstrip("\r")
                if (candidate.lstrip("\t") if dash_form else candidate) == delim:
                    i = j + 1
                    break
                j += 1
            else:
                i = n  # unterminated: nothing after this belongs to real command text


@lru_cache(maxsize=256)
def _script_invocation_targets(cmd: str) -> frozenset[str]:
    """Normalized script-path operands of every interpreter invocation in `cmd`.

    Used to correlate a heredoc's file-redirect target against a later (or
    earlier — see the positional-agnostic note above) interpreter invocation
    of that same file (main#1167). Memoized: pure in `cmd`, and both
    `_classify_heredocs_cached` and `strip_data_heredocs` call it on the same
    `cmd` within one hook invocation.
    """
    if not any(name in cmd for name in SHELL_INTERPRETERS):
        return frozenset()
    targets: set[str] = set()
    for seg_text in _iter_non_heredoc_segments(cmd):
        tokens = tokenize(_HEREDOC_OPENER_RE.sub(" ", seg_text))
        if not tokens:
            continue
        invocation = parse_interpreter_invocation(tokens)
        if invocation is None or invocation.has_command_string:
            continue
        if invocation.operands:
            targets.add(_normalize_path_for_compare(invocation.operands[0]))
    return frozenset(targets)


def _is_opener_code(cmd: str, line: str, pos: int, scan: _LineScan) -> bool:
    """Single source of truth: is the heredoc opened at `pos` on `line` (within
    the larger command `cmd`) executed as shell code?

    `classify_heredocs` and `strip_data_heredocs` MUST both call this rather
    than reimplementing the decision. main#1152 already flagged the drift
    hazard of two independent "is this body code" definitions; main#1167 is
    exactly that hazard realized once — extending only one of the two
    pre-existing call sites would silently leave the gap open in the other
    (in practice: `strip_data_heredocs` feeds `validate_commit_identity`'s
    `scanned` text, so a fix applied only to `classify_heredocs` would still
    let the body's `git commit` text get stripped as data before any matcher
    reading `scanned` ever saw it).
    """
    if _opener_feeds_interpreter(line, pos, scan):
        return True
    script_targets = _script_invocation_targets(cmd)
    if not script_targets:
        return False
    return any(
        _normalize_path_for_compare(target) in script_targets
        for target in _opener_write_targets(line, pos, scan)
    )


def classify_heredocs(cmd: str) -> tuple[HeredocSpan, ...]:
    """Find every heredoc in `cmd` and say whether its body is code or data.

    Bodies are located line-wise (the shell's own rule: openers are collected
    across the command line, bodies follow in opener order). Returns an empty
    tuple when the command holds no recognised heredoc.

    Memoized (#1113 discipline): pure in `cmd` and the result is a tuple of
    immutable NamedTuples, so the cached value is returned directly.
    """
    return _classify_heredocs_cached(cmd)


@lru_cache(maxsize=256)
def _classify_heredocs_cached(cmd: str) -> tuple[HeredocSpan, ...]:
    lines = cmd.split("\n")
    found: list[HeredocSpan] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        scan = _scan_command_line(line)
        for pos, dash_form, delim in scan.openers:
            is_code = _is_opener_code(cmd, line, pos, scan)
            body: list[str] = []
            term = None
            j = i
            while j < len(lines):
                candidate = lines[j].rstrip("\r")
                if (candidate.lstrip("\t") if dash_form else candidate) == delim:
                    term = j
                    break
                body.append(lines[j])
                j += 1
            if term is None:
                found.append(HeredocSpan(delim, "\n".join(body), True, False))
                return tuple(found)
            found.append(HeredocSpan(delim, "\n".join(body), is_code, True))
            i = term + 1
    return tuple(found)


@lru_cache(maxsize=256)
def strip_data_heredocs(cmd: str) -> str:
    """Remove the bodies of heredocs that are fed to a non-interpreter.

    The complement of `strip_heredocs`, which removes EVERY heredoc body: this
    keeps the bodies a shell will execute (so a bypass matcher still sees them)
    and drops only the ones that are inert text. Opener and terminator lines are
    left in place, so the surrounding command is unchanged and matchers anchored
    on `<interpreter> … <<DELIM` still work.

    Fails toward keeping the body: an unterminated heredoc, an unresolvable
    owner, or an unrecognised delimiter shape all leave the text untouched.

    Memoized (#1113): pure in `cmd`, returns an immutable `str`.
    """
    if "<<" not in cmd:
        return cmd
    lines = cmd.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        i += 1
        scan = _scan_command_line(line)
        for pos, dash_form, delim in scan.openers:
            is_code = _is_opener_code(cmd, line, pos, scan)
            term = None
            j = i
            while j < len(lines):
                candidate = lines[j].rstrip("\r")
                if (candidate.lstrip("\t") if dash_form else candidate) == delim:
                    term = j
                    break
                j += 1
            if term is None:
                out.extend(lines[i:])
                return "\n".join(out)
            out.extend(lines[i : term + 1] if is_code else [lines[term]])
            i = term + 1
    return "\n".join(out)


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


# ---------------------------------------------------------------------------
# Assignment-aware pre-pass (main#1195)
# ---------------------------------------------------------------------------
#
# `_payload_looks_like_commit` (validate_commit_identity) and the direct
# `git ... commit` finder (`find_git_subcommand`) both require the literal
# token `git` in command position. Holding the command word in a shell
# variable defeats BOTH with no interpreter wrapper at all:
#
#     g=git; $g commit -m x
#
# `$g` sits in command position exactly like a literal `git` would, and the
# shell resolves it at runtime; neither matcher can see through the
# indirection (measured on main#1193's head: `_payload_looks_like_commit`
# returns False on this exact string, and the direct-typed form with no
# wrapper at all is likewise allowed).
#
# This is a BOUNDED pre-pass, not general shell evaluation. It resolves only
# a LEADING run of `NAME=value` tokens at a segment's start (the same shape
# `_strip_leading_env_assignments` already recognises — one segment, one
# leading run) whose value is a bare literal, and substitutes later `$NAME`
# / `${NAME}` references anywhere in the command with that literal value.
# Deliberately does NOT resolve:
#   - command substitution (`d=$(date)`) — the value fails the
#     literal-charset check below, so `d` is never added to the map and a
#     later `$d` is left untouched. This is the guard against exactly the
#     false-positive shape the issue calls out: `d=$(date); echo $d` is an
#     ordinary shape and must not block.
#   - positional/special parameters (`$1`, `$?`, `$@`, `$$`, ...) — the
#     capture regex requires a name starting with a letter or underscore, so
#     these never match as an assignment NAME in the first place.
#   - multi-word / prose values (`msg="please git commit this later"`) — a
#     quoted value survives shlex de-quoting as ONE token, so a value
#     containing a space is caught and rejected by the literal-charset check
#     (values in this module's charset never contain whitespace). Without
#     this exclusion, resolving `$msg` inside an unrelated `echo $msg` would
#     manufacture a `git ... commit` bridge out of prose that was never
#     going to run a commit — a false positive of exactly the class the
#     issue warns a false positive here is an outage.
#   - `$1`-style arrays, `eval`-of-a-variable, and command substitution of
#     the COMMAND WORD itself (`$(printf git) commit`) — out of scope per
#     the issue; same family, strictly harder.
#
# Applied ONCE, on the raw command, before either the indirect-exec detector
# or the direct commit-segment finder run — a single pre-pass point rather
# than teaching two independent matchers the same resolution. main#1152's
# repeated lesson is exactly this: two places answering the same question
# independently drift. `resolve_simple_assignments` returns the command
# UNCHANGED whenever no qualifying assignment is found (the overwhelming
# majority of commands), so it can only ever ADD a detection, never remove
# one, and is a no-op for every pre-existing passing shape.
#
# ---------------------------------------------------------------------------
# Positional resolution, not a flat last-wins map (main#1195 review round 2)
# ---------------------------------------------------------------------------
#
# The first cut of this pre-pass built ONE flat `{name: value}` map across
# EVERY segment of the command (last assignment to a given name wins,
# regardless of where in the command it appears) and then substituted every
# `$NAME` reference in the whole command against that single map. That is
# order-blind, and a trailing reassignment reopens the exact bypass this
# pre-pass exists to close:
#
#     g=git; $g commit -m x; g=echo
#
# A real shell resolves `$g` at the point it is used — `git`, because that
# is the value `g` holds when the second segment runs; the later `g=echo`
# hasn't happened yet. The flat map instead sees `g`'s LAST assignment
# anywhere in the command (`echo`) and substitutes it everywhere, including
# at the earlier reference — turning `$g commit -m x` into `echo commit -m
# x`, which is not a `git` invocation at all. Neither the indirect-exec
# detector nor the direct commit-segment finder can then see the commit,
# and it sails through unvalidated. Confirmed against real shell behaviour
# (a printf/marker proxy shows the indirected command genuinely runs): this
# is a live bypass, not a cosmetic mismatch, and it reproduces the same way
# for `; g=true`, `|| g=x`, and `; false && g=nope` — any trailing
# reassignment, on any of the operators this module treats as a segment
# separator, erases the earlier resolution.
#
# The fix is POSITIONAL resolution: walk segments in the ORDER they appear
# in `command`, keep a running map of assignments seen so far, and resolve
# each segment's `$NAME` references against that running map BEFORE folding
# in that segment's own leading assignments (a segment's own assignment
# takes effect for segments that follow it, never for references inside
# itself — matching how a real shell evaluates one line before the next).
#
# A "first assignment wins, globally" flip was considered and rejected: it
# fixes the above shape but breaks its mirror image,
#
#     g=echo; $g commit; g=git
#
# where the FIRST assignment (`echo`) is genuinely what `$g` holds at the
# point of use, and the LATER `g=git` must NOT retroactively "resolve" the
# reference — that would manufacture a `git commit` detection out of a
# command that never runs one. Position-aware resolution (this
# implementation) gets both directions right, because it always asks "what
# does `g` hold at THIS point in the command", not "what is `g`'s first or
# last value anywhere in the command".
#
# Still not covered (measured, not a gap in the mechanism above — a
# different limitation entirely): `export g=git` / `declare g=git` are
# folded IN here (main#1195's own reviewer: same bare-literal shape one
# token to the right, arguably the most idiomatic spelling of the issue).
# `local`/`typeset`/`readonly`, any wrapper (`env g=git ...`), command
# substitution of the assigned value or the command word itself, and
# multi-word/prose values remain OUT of scope — same non-goal boundary as
# the rest of this module's exclusions, documented in the function
# docstring below.
#
# Round 3 correction (main#1195 review round 3): the paragraph above already
# stated the correct rule ("never for references inside itself"), but the
# implementation contradicted it — a segment's own leading assignments were
# ALSO folded into the map used to substitute that same segment's own
# references, which is not how a real shell resolves a prefix assignment
# (word expansion happens before the prefix takes effect). See
# `resolve_simple_assignments`'s docstring and the code comment at its
# `active = assignments` line for the corrected behaviour and the real-shell
# verification. `local`/`typeset`/`readonly` remain a documented non-goal
# here regardless of this correction; #1308 tracks that `typeset`/`readonly`
# (unlike `local`) are live at top level and may warrant a future widening.
_SIMPLE_LITERAL_VALUE_RE = re.compile(r"^[A-Za-z0-9_./:@%+-]+$")

# `$NAME` or `${NAME}` — a name starting with a letter/underscore, same
# identifier shape `_ENV_ASSIGN_RE` requires on the assignment side. Digits-
# leading references (`$1`, `$2`, ...) and single-punctuation specials
# (`$?`, `$@`, `$$`, `$*`, `$#`) never match this pattern, by construction.
# The trailing `\b` on the bare form is load-bearing, not decorative: it is
# what stops a shorter assigned name from being treated as a PREFIX of a
# longer, unrelated reference (`$gone`, `$g_2`, `$gx` must never be read as
# `$g` followed by literal `one`/`_2`/`x` — see the name-prefix-conflation
# tests in `ResolveSimpleAssignmentsTests`, test_shell_parse.py, which
# assert the resolver's OUTPUT STRING directly rather than a downstream
# verdict, precisely so that weakening this anchor is caught here rather
# than staying invisible behind a matcher that would reject the corrupted
# name anyway).
_VAR_REF_RE = re.compile(r"\$\{(?P<name_braced>[A-Za-z_]\w*)\}|\$(?P<name_bare>[A-Za-z_]\w*)\b")

# Shell keywords that may prefix a literal `NAME=value` assignment at a
# segment's leading position (#1305): `export FOO=bar` and `declare
# FOO=bar` are the same bare-literal shape one token to the right of a bare
# `FOO=bar`, not a harder family — folded in here rather than deferred.
# Recognised only as a SINGLE leading token (one keyword, not stacked or
# wrapped); `local`/`typeset`/`readonly` and any other wrapper stay out of
# scope, same as everything else this pre-pass declines to resolve.
_ASSIGNMENT_KEYWORDS = frozenset({"export", "declare"})


def _leading_literal_assignments(tokens: list[str]) -> dict[str, str]:
    """Literal `NAME=value` pairs from the LEADING run of assignment tokens
    in `tokens`, tolerating one optional `export`/`declare` prefix (#1305).

    `tokens` is first run through `strip_command_prefixes()` (main#1311) —
    the SAME helper `find_git_subcommand` / `find_gh_subcommand` already use
    to skip a compound-statement leader (`do`, `then`, `else`, `if`, `elif`,
    `while`, `until`, `{`, `(`) or a transparent wrapper (`timeout`, `env`,
    `nice`, ...) before looking for the command word. Without this, `for f
    in a; do g=git; $g commit -m x; done` tokenizes its `do`-segment to
    `["do", "g=git"]`; the leading-position check saw `"do"` (not an
    assignment, not `export`/`declare`) and stopped immediately, so the
    assignment one token to the right — at index 1, not 0 — was never
    captured, and the hook ALLOWed a command a real shell genuinely runs
    (confirmed with a marker proxy; same gap defeats `while`/`if` bodies and
    a wrapped `bash -c '...'` indirect-exec payload the same way). This is
    the module's own documented hazard
    (`extract_dash_c_pairs` vs `find_git_subcommand` holding different views
    of one segment) recurring one level up — `_leading_literal_assignments`
    had its own, narrower notion of "leading" than the rest of the module.
    Routing through `strip_command_prefixes()` here (default
    `compound_leaders=True`, the gate-matcher setting: over-matching can at
    worst capture an assignment from a body that may not run, which per this
    pre-pass's own invariant can only ADD a detection, never remove one) is
    the fix, rather than adding `do`/`then` to `_ASSIGNMENT_KEYWORDS` (a
    THIRD independent view of the same segment, reproducing the hazard
    again).

    Returns `{}` when `tokens` carries no qualifying leading assignment.
    """
    if not tokens:
        return {}
    tokens = strip_command_prefixes(tokens)
    if not tokens:
        return {}
    i = 1 if tokens[0] in _ASSIGNMENT_KEYWORDS else 0
    found: dict[str, str] = {}
    while i < len(tokens) and _ENV_ASSIGN_RE.match(tokens[i]):
        name, _eq, value = tokens[i].partition("=")
        if _SIMPLE_LITERAL_VALUE_RE.match(value):
            found[name] = value
        i += 1
    return found


def _iter_original_segment_spans(command: str) -> list[tuple[int, int]]:
    """Quote/escape-aware (start, end) span of each pipeline segment in
    `command`, as ORIGINAL-text character offsets (main#1195 review round 2).

    Mirrors `normalize_command_separators`'s operator/quote/escape rules
    exactly — the same `;` / `|` / `&&` / `||` operator set, plus a bare
    unescaped newline counting as a statement terminator — so segmentation
    can never drift from the rest of this module's notion of "one command".
    Unlike `normalize_command_separators`, this records spans into the
    ORIGINAL text rather than rewriting it: `resolve_simple_assignments`
    needs to substitute EACH segment using only the assignment state visible
    strictly BEFORE it (positional resolution), while every other byte of
    `command` — separators, whitespace, a backslash-newline continuation —
    must survive untouched in the final output (downstream heredoc handling
    depends on real newlines staying real newlines).

    A backslash-newline continuation is not special-cased separately: it
    falls out of the generic "backslash escapes the next character outside
    quotes" rule below, which consumes the backslash AND the following
    newline as one unit before the newline-terminator check ever sees it —
    the same outcome `normalize_command_separators` reaches via an explicit
    pre-pass, without needing one here.
    """
    spans: list[tuple[int, int]] = []
    quote: str | None = None
    seg_start = 0
    i = 0
    n = len(command)
    while i < n:
        c = command[i]
        if quote is not None:
            if c == "\\" and quote == '"' and i + 1 < n:
                i += 2
                continue
            if c == quote:
                quote = None
            i += 1
            continue
        if c in ("'", '"'):
            quote = c
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            i += 2
            continue
        if c == "\n":
            spans.append((seg_start, i))
            i += 1
            seg_start = i
            continue
        if command[i : i + 2] in ("&&", "||"):
            spans.append((seg_start, i))
            i += 2
            seg_start = i
            continue
        if c in (";", "|"):
            spans.append((seg_start, i))
            i += 1
            seg_start = i
            continue
        i += 1
    spans.append((seg_start, n))
    return spans


def _substitute_var_refs(text: str, assignments: dict[str, str]) -> str:
    """Replace every `$NAME` / `${NAME}` in `text` found in `assignments`."""

    def _sub(m: re.Match[str]) -> str:
        name = m.group("name_braced") or m.group("name_bare")
        return assignments.get(name, m.group(0))

    return _VAR_REF_RE.sub(_sub, text)


def _single_quoted_spans(text: str) -> list[tuple[int, int]]:
    """(start, end) spans of every single-quoted region's INSIDE text.

    Main#1195 finding 1 (round 4): a SAME-segment prefix assignment (`g=git
    bash -c '$g commit -m x'`) genuinely resolves inside a SINGLE-quoted
    argument, because that argument is opaque text handed to a CHILD
    interpreter (`bash -c '...'`) which does its OWN expansion, in its OWN
    environment — and a prefix assignment is placed into the invoked
    command's environment regardless of `export` (real-shell-verified with a
    marker proxy: this genuinely runs `git commit -m x`). That is a DIFFERENT
    evaluator, and a different visibility rule, than the bare/double-quoted
    reference `resolve_simple_assignments`'s docstring already covers (`A=1
    B=git $B commit -m z` — the OUTER shell expands `$B` itself, before its
    own prefix takes effect, so it stays unresolved; `bash -c "$g commit"`
    is the identical case one level down — the OUTER shell expands the
    double-quoted argument at that SAME expansion point, so `$g` is unset
    there too and must NOT resolve). Quotes are the only signal available
    post-tokenization for which evaluator will see a given `$NAME` — hence
    scanning for single-quoted spans specifically, rather than teaching
    `_substitute_var_refs` about "this is a child payload" some other way.

    Escape-aware the same way `_iter_original_segment_spans` is: a backslash
    escapes the next character when inside DOUBLE quotes or unquoted (POSIX:
    single quotes take no backslash-escaping at all, so none is honoured
    while scanning for the close of a `'...'` span — an escaped quote is not
    a thing single quotes support). Returned spans exclude the delimiting
    quote characters themselves, so callers can substitute inside them
    without disturbing the quoting.
    """
    spans: list[tuple[int, int]] = []
    quote: str | None = None
    inner_start = 0
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if quote is not None:
            if quote == '"' and c == "\\" and i + 1 < n:
                i += 2
                continue
            if c == quote:
                if quote == "'":
                    spans.append((inner_start, i))
                quote = None
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            i += 2
            continue
        if c in ("'", '"'):
            quote = c
            inner_start = i + 1
            i += 1
            continue
        i += 1
    return spans


def _substitute_within_single_quotes(text: str, assignments: dict[str, str]) -> str:
    """Apply `_substitute_var_refs` to `text`, restricted to single-quoted spans.

    Returns `text` unchanged (same object) when nothing inside any
    single-quoted span actually changes, matching the no-op contract the
    rest of `resolve_simple_assignments` relies on.
    """
    spans = _single_quoted_spans(text)
    if not spans:
        return text
    parts: list[str] = []
    prev_end = 0
    changed = False
    for start, end in spans:
        parts.append(text[prev_end:start])
        quoted = text[start:end]
        substituted = _substitute_var_refs(quoted, assignments)
        if substituted != quoted:
            changed = True
        parts.append(substituted)
        prev_end = end
    parts.append(text[prev_end:])
    return "".join(parts) if changed else text


def resolve_simple_assignments(command: str) -> str:
    """Resolve simple literal `NAME=value` assignments before matching (main#1195).

    Walks `command`'s pipeline segments (split on `;`, `&&`, `||`, `|` — the
    same `_SEGMENT_OPS` set `iter_command_segments` splits on, plus a bare
    newline as a statement terminator) IN SOURCE ORDER, maintaining a running
    map of literal `NAME=value` assignments seen in EARLIER segments. Each
    segment's `$NAME` / `${NAME}` references are substituted ONLY against
    that running (strictly-earlier) map — NEVER against the segment's own
    leading assignments (see `_leading_literal_assignments`; a bare literal
    value, optionally prefixed by `export`/`declare`, #1305). This mirrors
    real POSIX shell semantics: a command's words are expanded BEFORE its
    own prefix assignments take effect, so a same-line prefix like `A=1
    B=git $B commit -m z` must NOT resolve `$B` (real-shell-verified with a
    printf/marker proxy, main#1195 review round 3) — `$B` is unset at
    expansion time, and the prefix assignment only scopes the invoked
    command's environment, not the expansion of its own argument list. A
    reassignment in a LATER segment (`g=git; $g commit -m x; g=echo`) does
    NOT retroactively change what an EARLIER segment's reference resolved
    to, and a reassignment that hasn't happened YET (`g=echo; $g commit;
    g=git`) does not resolve early either. This is what makes resolution
    POSITIONAL rather than "last write anywhere wins" or "first write
    anywhere wins" — see the module comment above this section for the
    concrete cross-segment shapes that make the distinction observable, not
    just theoretical. After a segment is substituted, its own leading
    assignments are folded into the running map for segments that follow
    (so they become visible starting with the NEXT segment, never the
    current one).

    Round 4 exception (main#1195 finding 1): a segment's own leading
    assignments DO apply within a single-quoted span of that SAME segment —
    `g=git bash -c '$g commit -m x'` genuinely runs `git commit -m x`,
    real-shell-verified, because the quoted text is a CHILD interpreter's
    payload (expanded later, in an environment the prefix assignment already
    populated), not a reference the outer shell expands itself. See
    `_single_quoted_spans` for the full reasoning; `bash -c "$g commit"`
    (double-quoted) is unaffected and stays unresolved, same as a bare
    same-segment reference.

    Returns `command` unchanged when `tokenize()` fails (this pre-pass never
    manufactures a NEW parse failure — the existing `_PARSE_FAILURE`
    fail-closed path in the caller already handles unparseable input) or
    when no substitution actually changes the text (the overwhelming
    majority of commands) — so it can only ever ADD a detection, never
    remove one, and is a no-op for every pre-existing passing shape.
    """
    if tokenize(normalize_command_separators(command)) is None:
        return command

    spans = _iter_original_segment_spans(command)
    if not spans:
        return command

    assignments: dict[str, str] = {}
    out_parts: list[str] = []
    prev_end = 0
    changed = False
    for start, end in spans:
        out_parts.append(command[prev_end:start])
        orig_segment_text = command[start:end]

        # Assignments are extracted from the segment's ORIGINAL (pre-
        # substitution) text, never the substituted text: a value that is
        # itself a variable reference (`g=$a`) fails the literal-charset
        # check regardless, but resolving `$a` first and THEN re-checking
        # the substituted text would let a chained reference become newly
        # "literal" — reopening the `a=git; g=$a` non-goal this module
        # already, correctly, declines to resolve.
        seg_tokens = tokenize(orig_segment_text)
        own_assignments = _leading_literal_assignments(seg_tokens) if seg_tokens else {}

        # POSIX shells expand a command's words BEFORE applying that same
        # command's own prefix assignments (main#1195 review round 3, real-
        # shell verified with a printf/marker proxy). So a segment's OWN
        # leading assignments must NOT be visible to references inside that
        # SAME segment — only the running state accumulated from segments
        # STRICTLY BEFORE it (this already matches the module's own top-of-
        # file contract; merging `own_assignments` into `active` was the bug,
        # not a documented design choice). Concretely:
        #   - `A=1 B=git $B commit -m z` — `$B` is unset at expansion time
        #     (its own segment's `B=git` prefix hasn't taken effect yet); a
        #     real shell never runs git here, so `$B` must stay unresolved.
        #   - `g=git; g=echo $g commit -m x` — `$g` in the second segment
        #     must resolve against the RUNNING state (`git`, from segment 1),
        #     NOT `echo` (this segment's own prefix): a real shell expands
        #     `$g` to the OUTER shell's current value of `g` before the
        #     prefix assignment takes effect, so the invoked command is
        #     `git commit -m x` (with `g=echo` scoped only to that child's
        #     environment).
        #   - `g=git; g=echo $g commit -m x` reread the other way is the
        #     LIVE-BYPASS direction: the OLD code (merging `own_assignments`
        #     in) resolved `$g` to `echo` — this segment's own prefix — and
        #     so allowed the command outright, hiding a real `git commit`
        #     that the shell genuinely runs via the prior segment's `g=git`.
        # `active = assignments` (no merge) makes all four rows in the
        # main#1195 review-round-3 table shell-correct with one deletion.
        active = assignments
        segment_text = orig_segment_text
        if active:
            segment_text = _substitute_var_refs(orig_segment_text, active)
            if segment_text != orig_segment_text:
                changed = True

        # Round 4 (main#1195 finding 1): a segment's OWN leading assignments
        # — unlike the running `active` map above — apply ONLY inside a
        # single-quoted span of THIS SAME segment (see
        # `_single_quoted_spans`'s docstring for the real-shell reasoning:
        # that text is opaque to the outer shell and is expanded later by a
        # CHILD interpreter that inherits the prefix-assigned environment).
        # A bare or double-quoted reference in the same segment is expanded
        # by the OUTER shell instead, at the same point `active` (never
        # `own_assignments`) already governs — untouched by this pass.
        if own_assignments:
            quoted_text = _substitute_within_single_quotes(segment_text, own_assignments)
            if quoted_text != segment_text:
                segment_text = quoted_text
                changed = True

        out_parts.append(segment_text)
        prev_end = end

        if own_assignments:
            assignments.update(own_assignments)

    out_parts.append(command[prev_end:])
    return "".join(out_parts) if changed else command


def bashlex_available() -> bool:
    """True iff the optional bashlex Bash-AST parser imported successfully.

    Read at call time so tests can monkeypatch `_BASHLEX_AVAILABLE` to simulate
    a bare checkout. The commit-identity hook uses this to decide between the
    structural (bashlex) parse and the shlex/regex degraded fallback.
    """
    return _BASHLEX_AVAILABLE


def iter_command_segments_ast(command: str) -> list[list[str]] | None:
    """Structural (bashlex) extraction of command-position token segments.

    Parses `command` into a real Bash AST and walks every CommandNode —
    descending through `&&`/`;`/`||` lists, `|` pipelines, `$(...)`/backtick
    command substitutions, and compound (`{ }`, `( )`, if/while/for) bodies.
    Each yielded segment is the command's WordNode values in source order;
    `KEY=value` env-var prefixes arrive as AssignmentNodes and are naturally
    excluded because only `word`-kind parts are collected — matching the
    leading-env-strip behaviour of the shlex-based `iter_command_segments`.

    Token shape is identical to the shlex path: `-c user.name="A B"` yields
    `["-c", "user.name=A B"]`, so the existing `find_git_subcommand` /
    `extract_dash_c_pairs` consumers work unchanged on AST segments.

    Returns:
      list[list[str]] — the segments (an empty list when the input parsed but
                        held no command, e.g. a bare comment).
      None            — bashlex is unavailable (degraded mode) OR the command
                        failed to parse. The caller MUST fall back to the
                        shlex/regex path; per the tokenize() security contract
                        a None here is NEVER treated as "allow".

    Memoized (#1113): the bashlex parse is cached (`_iter_command_segments_ast_cached`)
    but a FRESH list-of-lists copy is returned each call, so callers keep the
    mutable-result contract without corrupting the shared cache. The
    `_BASHLEX_AVAILABLE` degraded-mode gate is intentionally OUTSIDE the cache.
    """
    if not _BASHLEX_AVAILABLE:
        return None
    cached = _iter_command_segments_ast_cached(command)
    # Deep-copy the immutable cached snapshot into fresh mutable lists so a
    # caller that mutates a segment (or the outer list) cannot corrupt the
    # shared cache entry — the naive-lru_cache aliasing hazard (#1113).
    return None if cached is None else [list(seg) for seg in cached]


@lru_cache(maxsize=256)
def _iter_command_segments_ast_cached(command: str) -> tuple[tuple[str, ...], ...] | None:
    """Memoized core of iter_command_segments_ast(). Returns IMMUTABLE tuples.

    Assumes bashlex availability is already checked by the caller — the
    `_BASHLEX_AVAILABLE` gate lives in the public wrapper (uncached) so that a
    test monkeypatching that flag to simulate degraded mode is NEVER served a
    stale cached AST result. The single bashlex parse per Bash call is pure in
    `command`, so its segments are cached as a tuple-of-tuples (no mutable list
    ever escapes into the cache).
    """
    try:
        trees = bashlex.parse(command)
    except Exception:
        # Any bashlex failure — unbalanced quotes, an unsupported construct,
        # etc. — signals the caller to fall back. Fallback is always safe, so a
        # broad catch matches the resilience posture of `tokenize` returning
        # None on a parse error (never crash the hook).
        return None

    segments: list[tuple[str, ...]] = []

    class _SegmentCollector(bashlex_ast.nodevisitor):
        def visitcommand(self, n, parts):
            tokens = tuple(p.word for p in parts if p.kind == "word")
            if tokens:
                segments.append(tokens)
            return True  # keep descending into command substitutions, compounds, ...

    collector = _SegmentCollector()
    for tree in trees:
        collector.visit(tree)
    return tuple(segments)


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


# ---------------------------------------------------------------------------
# Command-prefix wrappers + compound-statement leaders (main#1141)
# ---------------------------------------------------------------------------
#
# `find_git_subcommand` / `find_gh_subcommand` keyed on `segment[0]` being
# literally `git` / `gh`. Two ordinary shapes put something else there and made
# every consuming hook silently no-op:
#
#   timeout 45 gh issue edit 1114 --add-label "wave-29"    -> segment[0] == "timeout"
#   for n in …; do gh issue edit 1114 --add-label "wave-29"; done
#                                                          -> segment[0] == "do"
#
# For the kickoff hook that meant 14 issues labeled and ZERO kickoff comments
# posted (main#1141); for the BLOCKING hooks on the same primitive
# (`block_gh_pr_review`, `block_squash_wave_merge`, `validate_wave_label_evidence`,
# `validate_commit_identity` via the git twin) it is a gate-evasion class — a
# `timeout`/`nice`/loop prefix walked straight past the gate.
#
# The fix is an ALLOWLIST, never a "scan the segment for a `gh` token anywhere":
# loose scanning would re-introduce the data-position false-positive class this
# whole module exists to prevent (`echo gh issue edit 5 …` must NOT match). Only
# wrappers that transparently exec the following command, with their own option
# grammar spelled out, are skipped.
#
# Each entry maps a wrapper name to (flags that consume a following VALUE,
# number of bare POSITIONAL args consumed before the wrapped command). Boolean
# flags, `--flag=value` and attached-short forms need no table entry — any
# remaining `-`-prefixed token is skipped generically.
_COMMAND_PREFIX_WRAPPERS: dict[str, tuple[frozenset[str], int]] = {
    # `timeout DURATION cmd …` — the one positional is the duration.
    "timeout": (frozenset({"-k", "--kill-after", "-s", "--signal"}), 1),
    "nice": (frozenset({"-n", "--adjustment"}), 0),
    "ionice": (frozenset({"-c", "-n", "-p", "--class", "--classdata", "--pid"}), 0),
    "stdbuf": (frozenset({"-i", "-o", "-e", "--input", "--output", "--error"}), 0),
    # `env [-u NAME] [KEY=value …] cmd …` — the KEY=value run is skipped by the
    # generic env-assignment branch in `_consume_wrapper_options`.
    "env": (frozenset({"-u", "--unset", "-C", "--chdir", "-S", "--split-string"}), 0),
    "nohup": (frozenset(), 0),
    "setsid": (frozenset(), 0),
    "command": (frozenset(), 0),
    "builtin": (frozenset(), 0),
    "exec": (frozenset(), 0),
    "time": (frozenset({"-f", "--format", "-o", "--output"}), 0),
    "sudo": (
        frozenset(
            {"-u", "--user", "-g", "--group", "-p", "--prompt", "-U", "-C", "-h", "-T", "-R"}
        ),
        0,
    ),
    "doas": (frozenset({"-u", "-C", "-L"}), 0),
}

# Shell keywords that can occupy position 0 of a segment while the COMMAND
# follows them in the same segment. `for` / `case` / `select` are deliberately
# absent: what follows them is a variable name or a word list, not a command
# (`for n in 1114 …` must not resolve `n` as a command).
_COMPOUND_LEADERS = frozenset({"do", "then", "else", "if", "elif", "while", "until", "!", "{", "("})

# Bound on the wrapper/keyword unwrap loop. `do timeout 45 nohup gh …` is 3
# rounds; anything past this is pathological input, not a real command.
_MAX_PREFIX_STRIP_ROUNDS = 8


def _consume_wrapper_options(rest: list[str], value_flags: frozenset[str], positionals: int) -> int:
    """Return the index in `rest` where a wrapper's own arguments end.

    Walks the wrapper's option run: value-taking flags consume their value,
    any other flag-shaped token consumes itself, `KEY=value` env assignments
    are skipped (`env FOO=1 gh …`), and up to `positionals` bare words are
    consumed (the `timeout DURATION` slot). A literal `--` ends the option run
    immediately. The first token that is none of those is the wrapped command.
    """
    i = 0
    n = len(rest)
    while i < n:
        tok = rest[i]
        if tok == "--":
            return i + 1
        if tok in value_flags:
            # Mirror `walk_flag_values`: a value-less flag never eats the next
            # flag-shaped token.
            i += 2 if (i + 1 < n and not _looks_like_flag(rest[i + 1])) else 1
            continue
        if _looks_like_flag(tok):
            i += 1
            continue
        if _ENV_ASSIGN_RE.match(tok):
            i += 1
            continue
        if positionals > 0:
            positionals -= 1
            i += 1
            continue
        break
    return i


def strip_command_prefixes(segment: list[str], *, compound_leaders: bool = True) -> list[str]:
    """Strip leading command-prefix wrappers, and optionally compound keywords.

        ["timeout", "45", "gh", "issue", "edit", …] -> ["gh", "issue", "edit", …]
        ["do", "gh", "issue", "edit", …]            -> ["gh", "issue", "edit", …]
        ["echo", "gh", "issue", "edit", …]          -> unchanged (echo is not a
                                                       transparent wrapper — its
                                                       args are DATA, not a command)

    Only names in `_COMMAND_PREFIX_WRAPPERS` / `_COMPOUND_LEADERS` are stripped,
    so a segment whose head is any other command is returned untouched. The
    returned list is a fresh object or the original list — callers must not rely
    on identity (main#1141).

    `compound_leaders` — the distinction that decides which callers may say
    True (main#1141 review round 3)
    ======================================================================

    The two prefix kinds are NOT equivalent, and conflating them shipped a
    live misroute:

      - A **wrapper** (`timeout`, `env`, `nice`, `nohup`, `sudo`) ALWAYS execs
        what follows. Stripping it is unconditionally sound: the wrapped
        command runs.
      - A **compound leader** (`then`, `do`, `else`, `{`, `(`) guards a body
        that MAY NOT RUN. `if [ -f /nonexistent ]; then cd /other-repo; fi`
        contains a `cd` the shell never executes.

    Whether that matters depends on what the caller does with the answer:

      - A **gate matcher** (`find_git_subcommand`, `find_gh_subcommand`, and
        `extract_dash_c_pairs` reading a matched segment's flags) errs
        CONSERVATIVELY by over-matching: at worst it validates a command that
        would not have run. Harmless. These pass `compound_leaders=True`.
      - A **routing resolver** (`extract_leading_cd_target`, which decides
        WHICH REPO an action targets) errs DESTRUCTIVELY by over-matching: it
        sends output where the command never went. Under
        `compound_leaders=True` the example above resolved the repo to
        `noorinalabs-deploy` and would have posted a kickoff comment to
        `deploy#5` instead of `main#5` — on the #981/#985 misrouting path.
        Routing callers MUST pass `compound_leaders=False`.

    Non-goal, deliberately: `for r in …; do cd /wt; gh …; done` — a cd inside
    a loop body that DOES run — is not recovered under
    `compound_leaders=False`. Distinguishing it from the never-taken `then`
    body needs block-closure tracking, and the shape is speculative (no
    observed bug) while the misroute was live. Not worth the machinery.
    """
    tokens = segment
    for _ in range(_MAX_PREFIX_STRIP_ROUNDS):
        if not tokens:
            return tokens
        head = tokens[0]
        if compound_leaders and head in _COMPOUND_LEADERS:
            tokens = tokens[1:]
            continue
        spec = _COMMAND_PREFIX_WRAPPERS.get(head)
        if spec is None:
            return tokens
        value_flags, positionals = spec
        tokens = tokens[1 + _consume_wrapper_options(tokens[1:], value_flags, positionals) :]
    return tokens


# ---------------------------------------------------------------------------
# Shell-interpreter invocations (main#1149)
# ---------------------------------------------------------------------------
#
# `validate_commit_identity` matched `<shell> -c <payload>` with a regex that
# required `-c` to be a BARE token immediately after the interpreter. Real
# shells accept the command-string flag combined into a short-flag cluster and
# after an arbitrary option run, so 8 of 9 ordinary spellings walked straight
# past the gate and committed with whatever ambient identity git resolved.
#
# The grammar below is deliberately NOT a second regex. It normalizes the
# interpreter's own option tokens into the shape `_consume_wrapper_options`
# already understands and then defers to it, so there is exactly one option-run
# implementation in this module (main#1150's invariant).
#
# Every rule here was measured against bash / sh / zsh / dash with an execution
# oracle (does the candidate payload actually run?), not reasoned from man
# pages. The three findings that a from-first-principles fix would have missed:
#
#   `bash -cl CMD`  runs CMD — the command-string letter does NOT have to be
#                   last in the cluster, so a `-[a-z]*c$` regex is still wrong.
#   `bash +x -c CMD` runs CMD — `+`-form options are options, but
#                   `_looks_like_flag` only recognises a leading `-`.
#   `bash -oc pipefail CMD` runs CMD — a value-taking letter INSIDE a cluster
#                   still eats the next word, shifting the payload by one.
#   `bash -- -c CMD` does NOT run CMD — `--` ends the option run, which
#                   `_consume_wrapper_options` already models correctly.

# Interpreter options that consume a following word as their value. `-o`/`-O`
# name a `set`/`shopt` option; bash's two startup-file options take a path.
SHELL_VALUE_OPTIONS = frozenset({"-o", "-O", "--rcfile", "--init-file"})

# Cluster letters that consume a following word (the short forms of the above).
_SHELL_VALUE_LETTERS = frozenset("oO")

# The letter that introduces a command string: `sh -c '<cmd>'`.
_COMMAND_STRING_FLAG = "-c"

# A bare stdin-redirect operator, fd-0-targeting spellings only (main#1170,
# widened for main#1326): `<`, `0<`, `<>`, `0<>`. All four are the identical
# redirect as far as a shell's own script-source resolution is concerned — fd
# 0 is stdin's default, `<>` (read-write open) still opens the SAME fd, and
# the explicit `0` prefix is fused to the operator by shlex whenever no space
# separates them (`0< FILE` -> one token `"0<"`, never `"0"` + `"<"`). All
# four spellings were verified with a real-shell marker proxy (fake `git` on
# PATH) under both bash and zsh: `bash 0< s.sh`, `bash <> s.sh`, and
# `bash 0<> s.sh` all genuinely execute `s.sh`'s body, exactly like the bare
# `bash < s.sh` main#1170 already covers. A DIFFERENT fd number is a
# different redirect entirely and must NOT match — `bash 2< s.sh` does not
# feed `s.sh` to the interpreter as its script (confirmed: the marker never
# fires), so the leading digit run is restricted to the literal `0`, not
# `\d*` as #1326's own suggested pattern had it (that pattern would also
# wrongly swallow `2<`/`9<`/... as if they were stdin sources).
_STDIN_REDIRECT_RE = re.compile(r"^0?<>?$")


class InterpreterInvocation(NamedTuple):
    """A decoded `<shell> [options] [operands ...]` command.

    `name` is the interpreter basename (`/usr/bin/bash` -> `bash`).

    `has_command_string` is True when the option run carries `-c` in any
    spelling — bare, clustered (`-lc`, `-cl`, `-cabm`), or after other options.

    `operands` are the tokens after the option run, i.e. what the shell itself
    treats as `<command-string> [$0 $1 ...]` or `<script> [args]`. This is the
    shell-accurate answer and is what a consumer that must resolve a real path
    (the script-invocation check) should use. `operands[0]` also resolves a
    stdin-redirect script (`bash < FILE`, main#1170/main#1287 shape 1, widened
    to the `0<`/`<>`/`0<>` spellings by main#1326) to `FILE` — but ONLY when
    NO other (non-redirect) operand is present anywhere in the invocation. A
    real shell always prefers an ordinary positional operand over a stdin
    redirect as its script source, regardless of whether that operand sits
    before or after the redirect token in the invocation — a stdin redirect
    is not counted as an argument slot at all, so `bash script.sh < FILE` runs
    `script.sh` (FILE is just its stdin stream) and `bash < FILE arg1` runs
    `arg1` (FILE is again just stdin; `arg1` is the only real operand) — real
    bash and zsh confirmed via marker proxy for both orderings. Only the `-s`
    option (not currently modeled here — main#1325 review, filed as a
    follow-up) forces the stdin content itself to be the script even when a
    positional operand is also present. See `parse_interpreter_invocation`'s
    docstring for the resolution rule.

    `words` is every token of the invocation except the `--` sentinel — the set
    the command string is guaranteed to be a member of. It is deliberately a
    SUPERSET of `operands`, and consumers that are gates must use it, because
    `operands` alone fails OPEN in two measured ways:

      - a cluster mixing a value-letter with `c` shifts the payload index, and
        differently per shell: `zsh -cO '<cmd>'` runs `<cmd>`, but the shared
        grammar pairs the clustered `-O` with it as a VALUE, so `operands` is
        empty;
      - `end` is only a LOWER bound on where the option run stops.
        `_consume_wrapper_options` treats every dash-leading token as an option,
        so a command string that itself starts with `-` is swallowed into the
        run. Both `bash -c -- '-x; git commit …'` and `zsh -abc '-x; git
        commit …'` really execute, and both left `operands` empty.

    Rather than re-derive the exact boundary — reintroducing precisely the
    per-shell option knowledge this module exists to avoid — `words` keeps
    everything. The extra tokens are option spellings (`-l`, `--login`,
    `pipefail`); none can carry a `git … commit` bridge, and the cost was priced
    at zero verdict changes over 7.6k real recorded commands.
    """

    name: str
    has_command_string: bool
    operands: tuple[str, ...]
    words: tuple[str, ...]


def _expand_shell_option_token(tok: str) -> list[str]:
    """Rewrite one interpreter option token into `_consume_wrapper_options` form.

    Two normalizations, each closing a measured bypass:

      `+x` -> `-x`, `+o` -> `-o`
          `set`-style options may be turned off with a leading `+`, and
          `bash +x -c '<cmd>'` really does run `<cmd>`. `_looks_like_flag` keys
          on a leading `-` only, so without this the `+x` reads as the wrapped
          command and the option run ends before `-c` is ever seen.

      `-lc` -> `-l -c`
          De-clustering makes the command-string flag a plain token-equality
          test instead of a second regex over cluster spellings, and it lets
          the shared grammar pair a clustered value-letter with its value.

    Value-taking letters are emitted LAST within an expanded cluster. Within one
    cluster the letters' order does not change WHICH following words are
    consumed as values — only the order they are consumed in — so moving them to
    the end is semantics-preserving for our purpose, and it puts each value flag
    immediately before the word it consumes, which is the only arrangement
    `_consume_wrapper_options` can pair up (it refuses to let a value flag eat a
    flag-shaped token). Without the reorder, `bash -oc pipefail 'git commit …'`
    resolves the payload to `pipefail` and the gate fails open.

    Long options, `--`, `=`-forms and anything non-alphabetic are returned
    unchanged: only a `[-+][A-Za-z]{2,}` run is a short-flag cluster.
    """
    if len(tok) < 2 or tok[0] not in "-+":
        return [tok]
    body = tok[1:]
    if body.startswith("-") or not body.isalpha():
        # `--login`, `--rcfile=F`, `--`, `-2`, `-o=x` — not a short cluster.
        return ["-" + body] if tok[0] == "+" else [tok]
    if len(body) == 1:
        return ["-" + body]
    plain = ["-" + ch for ch in body if ch not in _SHELL_VALUE_LETTERS]
    valued = ["-" + ch for ch in body if ch in _SHELL_VALUE_LETTERS]
    return plain + valued


def parse_interpreter_invocation(segment: list[str]) -> InterpreterInvocation | None:
    """Decode `segment` as a shell-interpreter invocation, or return None.

    Transparent command-prefix wrappers are stripped first, so
    `timeout 30 env FOO=1 bash -lc '<cmd>'` decodes the same as `bash -lc
    '<cmd>'`. A leading path is reduced to its basename (`/bin/sh` -> `sh`).

    Returns None when the segment is empty or its head is not one of
    `SHELL_INTERPRETERS` — callers must treat None as "not an interpreter
    invocation", never as "safe".

    Stdin-redirect operand resolution (main#1170 / main#1287 shape 1, widened
    for main#1326): `bash < FILE` feeds FILE to the interpreter as its script
    through the process's own stdin rather than as a positional argument, but
    it answers the exact same question `operands[0]` exists to answer —
    "what file does this interpreter execute?" — so the redirect target CAN
    be folded into `operands` in the `[0]` slot.

    Precedence — a positional operand always wins, regardless of position
    relative to the redirect (main#1325 review round 2, corrected from this
    function's own first cut): a real shell does not count a stdin redirect
    as an argument slot at all, so it never competes with an ordinary word for
    the `[0]` position. Confirmed with a real-shell marker proxy under both
    bash and zsh, in both orderings:

      - `bash script.sh < FILE` runs `script.sh` — FILE is only script.sh's
        stdin stream, never a competing script. (This function's FIRST cut
        got this backwards: it unconditionally promoted the redirect target
        into `[0]` even when a positional operand was already present,
        which silently swapped which file gets read for content inspection
        and which file the write-then-exec correlation watches — a measured
        BLOCK->ALLOW bypass, a measured ALLOW->BLOCK false positive on the
        ordinary `bash migrate.sh < input.csv` shape, a BLOCK->ALLOW
        regression in the on-disk script-content walker for `bash -x s.sh <
        FILE` / `bash -- s.sh < FILE`, and an over-block reintroducing
        main#1152's own failure mode for a benign `bash deploy.sh < data.txt`
        stdin feed. All four were the SAME defect, not four separate ones.)
      - `bash < FILE arg1` runs `arg1` (which will typically fail to exist,
        exactly like a real shell) — FILE is still only stdin; `arg1` is the
        one true operand present, regardless of appearing textually AFTER the
        redirect token.
      - `bash < FILE` (no other operand at all) is the only shape where FILE
        genuinely becomes the executed script — this is the ONLY case the
        redirect target is promoted into `operands[0]`.

    Only the `-s` option (not modeled here — filed as a follow-up in the
    main#1325 review) can force the redirect target to be the script even
    when a positional operand is also present; this function does not special
    case it, matching its behaviour before this correction.

    Redirect spelling: only the spaced form (`< FILE`, not `<FILE`) is
    recognised — the same convention `_segment_write_targets` already applies
    to `>`/`>>`. The token itself must match `_STDIN_REDIRECT_RE` (`<`, `0<`,
    `<>`, `0<>` — all four verified to genuinely feed the interpreter's
    script under both bash and zsh; a different fd number, e.g. `2<`, does
    NOT and is deliberately excluded). `<<` (a heredoc opener) is never
    present here (callers strip it before tokenizing — see
    `_HEREDOC_OPENER_RE`), and `<(` (process substitution) arrives from shlex
    fused into one token (`<(cmd)`) whenever it isn't preceded by whitespace,
    so it can't be mistaken for a bare `<`. The LAST matching redirect token
    on the line wins for STDIN-TARGET tracking, mirroring a real shell's
    last-redirect-wins semantics — moot whenever a positional operand is also
    present, since the redirect target is dropped entirely in that case.
    """
    tokens = strip_command_prefixes(segment)
    if not tokens:
        return None
    name = tokens[0].rsplit("/", 1)[-1]
    if name not in SHELL_INTERPRETERS:
        return None

    rest: list[str] = []
    for tok in tokens[1:]:
        rest.extend(_expand_shell_option_token(tok))

    end = _consume_wrapper_options(rest, SHELL_VALUE_OPTIONS, 0)
    has_command_string = _COMMAND_STRING_FLAG in rest[:end]

    stdin_target: str | None = None
    other_operands: list[str] = []
    j = end
    n = len(rest)
    while j < n:
        tok = rest[j]
        if _STDIN_REDIRECT_RE.match(tok) and j + 1 < n:
            stdin_target = rest[j + 1]
            j += 2
            continue
        other_operands.append(tok)
        j += 1
    # A positional operand always wins over a stdin redirect — see the
    # docstring's "Precedence" section. The redirect target is only promoted
    # into operands[0] when it is the SOLE operand candidate; otherwise it is
    # dropped entirely (it names a stdin stream, not an argument or a script).
    operands = (
        tuple(other_operands)
        if other_operands
        else ((stdin_target,) if stdin_target is not None else ())
    )
    words = tuple(t for t in rest if t != "--")
    return InterpreterInvocation(name, has_command_string, operands, words)


def iter_interpreter_invocations(command: str) -> list[InterpreterInvocation]:
    """Decode every shell-interpreter invocation in a compound command.

    Heredoc bodies are removed before tokenizing: a body is not part of the
    invocation's own argument list, and leaving it in would let its words be
    read as segments. Callers that care about heredoc BODIES (they are executed
    when the heredoc is fed to a shell) must handle them separately —
    `classify_heredocs` is the primitive for that.

    Unbalanced-quote repair. A command that shlex cannot tokenize would
    otherwise yield nothing, and for a fail-closed gate that is a bypass an
    evader reaches by typing one extra quote character:

        bash -lc "git commit -m x" && echo "unclosed

    The invocation itself is well-formed; only the tail is broken. So on a parse
    failure we retry once per quote character with that character appended.
    Repairing the QUOTING (rather than splitting the text on separators, the
    other obvious recovery) is what keeps this safe: quoted prose stays a single
    token, so a malformed `gh issue comment --body '…bash -lc "git commit"…'`
    still resolves to a segment headed by `gh` and matches nothing. The
    head-anchored `parse_interpreter_invocation` does the rest — a repaired
    parse can only ever add segments, never move an interpreter into command
    position that was not already there.

    Returns an empty list when even the repaired text cannot be tokenized. A
    security gate must therefore still keep a text-level fallback rather than
    reading an empty list as "nothing here".

    Perf prefilter (#1113 discipline): an interpreter invocation cannot exist
    unless the interpreter's name appears literally somewhere in the command, so
    a substring test skips the tokenize for the overwhelming majority of Bash
    calls. The helpers below are individually memoized, so a command that does
    reach them is parsed once per process regardless of how many hooks ask.
    """
    if not any(name in command for name in SHELL_INTERPRETERS):
        return []
    text = strip_heredocs(command)
    tokens = tokenize(normalize_command_separators(text))
    if tokens is None:
        for repair in ("'", '"'):
            tokens = tokenize(normalize_command_separators(text + repair))
            if tokens is not None:
                break
    if tokens is None:
        return []
    found: list[InterpreterInvocation] = []
    for segment in iter_command_segments(tokens):
        invocation = parse_interpreter_invocation(segment)
        if invocation is not None:
            found.append(invocation)
    return found


def find_git_subcommand(segment: list[str]) -> tuple[list[str], list[str]] | None:
    """If `segment` is a `git ...` invocation, return (global_opts, [subcmd, ...]).

    Skips git global options:
      -c key=value          (consumed as one shlex token, possibly quoted)
      -C path
      --git-dir=path / --git-dir path
      --work-tree=path / --work-tree path
      --no-pager / -p / --paginate / --no-replace-objects   (no value)

    Leading compound-statement keywords and transparent command-prefix wrappers
    are stripped first (main#1141), so `timeout 60 git commit …` and the
    `do`-prefixed body of a loop resolve to the `commit` verb instead of
    silently bypassing every consuming gate.

    Returns None if `segment` is empty, doesn't start with `git` (after that
    strip), or doesn't have a subcommand after the global-option run.
    """
    segment = strip_command_prefixes(segment)
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

    Leading compound-statement keywords and transparent command-prefix wrappers
    are stripped first (main#1141): `timeout 45 gh issue edit …` and the
    `do`-prefixed body of `for n in …; do gh issue edit …; done` both resolve.
    Before that fix each returned None, and every consuming hook — the kickoff
    comment poster AND the blocking `gh pr review` / squash-merge gates —
    silently did nothing.
    """
    segment = strip_command_prefixes(segment)
    if not segment or segment[0] != "gh":
        return None
    if len(segment) < 2:
        return None
    return [], segment[1:]


def is_gh_subcommand(tokens: list[str], *verbs: str) -> bool:
    """Return True if `tokens` begins a `gh <verbs[0]> <verbs[1]> ...` invocation.

    Walks `tokens` looking for `gh` followed by the supplied verb sequence in
    order, allowing them to appear at any position (not just the start of the
    list). Used by hooks that want a yes/no "does this command invoke
    `gh issue create`?" check without needing the post-verb token tail.

    Example:
        is_gh_subcommand(tokens, "issue", "create")  # True for `gh issue create ...`
        is_gh_subcommand(tokens, "pr", "create")     # True for `gh pr create ...`
    """
    if not verbs:
        return False
    target = ("gh",) + verbs
    n = len(tokens)
    span = len(target)
    if n < span:
        return False
    for i in range(n - span + 1):
        if tuple(tokens[i : i + span]) == target:
            return True
    return False


def _looks_like_flag(tok: str) -> bool:
    """Return True if `tok` has the surface shape of a flag (`-x` / `--xxx`).

    A bare `-` (the conventional "read from stdin" positional sentinel used
    by many CLIs, including some `gh`/`git` subcommands) is deliberately
    NOT treated as a flag — only genuine `-`-prefixed multi-character
    tokens are (main#1060).
    """
    return len(tok) > 1 and tok[0] == "-"


def walk_flag_values(tokens: list[str], wanted: set[str]) -> list[str]:
    """Return values for `wanted` flag names, only when they appear as flags.

    A token is treated as a wanted-flag value only if the immediately
    preceding token is exactly one of `wanted` (e.g. `--label`). Three
    surface forms are recognized:

      - two-token form   `--flag value` / `-R value`
      - equals form      `--flag=value` / `-R=value`
      - attached-short   `-Rvalue`  (POSIX getopt / cobra shorthand:
                          `-Rvalue` == `-R value`)

    The attached form applies to SINGLE-CHARACTER SHORT flags ONLY (`-R`,
    `-l`, `-e`, ...). A long flag must use `=` or a space, so `--repofoo`
    must NEVER be split into `--repo` + `foo` — the `len(flag) == 2` guard
    below enforces that. This closes the `-R$DA` fail-open where an attached
    short-flag repo value was dropped to None, letting a `gh pr merge` skip
    the repo-confusion / 2-reviewer gate (main#1057, sibling of #981).

    Values inside other flags (e.g. inside the value of `--body`) are
    ignored because they are a SINGLE shlex token, never preceded by a flag
    from `wanted`.

    Order is preserved: values appear in the order they were encountered
    in the token stream.

    gh/cobra semantics hardening (main#1060):

      - **Value-less flag never eats the next flag.** `-R --add-label X`
        would have real `gh` error ("flag needs an argument: 'R'"); this
        helper can't raise, but it must not silently treat `--add-label` as
        `-R`'s value either (that previously made `repo_short_name_from_...`
        route on a bogus `repo='--add-label'`, main#1059's motivating case).
        A token immediately after a `wanted` flag is only consumed as its
        value when it does NOT itself look like a flag (`-`-prefixed,
        length > 1 — a bare `-` is the common stdin/positional sentinel,
        never a flag). When the next token looks like a flag, the current
        flag yields no value (same as the trailing-flag-with-no-successor
        case) and the flag-shaped token is left for the next loop
        iteration to scan on its own.
      - **`--` (POSIX end-of-options) stops the scan.** Everything after a
        literal `--` token is positional in real `gh`/cobra, never a flag —
        continuing to scan past it let `-- --repo X` resolve `--repo` as if
        it were still in flag position.
    """
    values: list[str] = []
    i = 0
    n = len(tokens)
    while i < n:
        tok = tokens[i]
        if tok == "--":
            break
        if tok in wanted:
            nxt = tokens[i + 1] if i + 1 < n else None
            if nxt is not None and not _looks_like_flag(nxt):
                values.append(nxt)
                i += 2
                continue
            i += 1
            continue
        matched = False
        for flag in wanted:
            # Equals form (long OR short). Checked BEFORE the attached-short
            # branch so `-R=value` yields `value`, not `=value`.
            if tok.startswith(flag + "="):
                values.append(tok[len(flag) + 1 :])
                matched = True
                break
            # Attached-short form `-Rvalue`. Scoped to single-character short
            # flags (`len(flag) == 2`, `-X`) so no long flag is ever split on a
            # bare prefix (`--repofoo` != `--repo` + `foo`). `len(tok) > 2`
            # excludes the bare `-R` (which the exact-match branch above already
            # handled) so a value-less short flag still yields nothing.
            if (
                len(flag) == 2
                and flag[0] == "-"
                and flag[1] != "-"
                and len(tok) > 2
                and tok.startswith(flag)
            ):
                values.append(tok[2:])
                matched = True
                break
        if matched:
            i += 1
            continue
        i += 1
    return values


def first_flag_value(command: str, wanted: set[str], *, regex_fallback: bool = True) -> str | None:
    """Tokenize `command` and return the FIRST value for any flag in `wanted`.

    Returns None if no wanted flag is present. If shlex tokenization fails
    (malformed quotes) and `regex_fallback=True` (default), falls back to a
    boundary-anchored regex search that tries longer flag names first so
    `--repo` is preferred over a hypothetical shorter prefix collision.
    With `regex_fallback=False`, returns None on tokenize failure (the
    fail-closed shape used by security-critical matchers).

    First-wins is this function's deliberate, pinned contract (see
    `test_returns_first_value`) — its only current callers
    (`validate_branch_freshness.extract_base`/`extract_head`) are an
    advisory freshness gate, not a fail-closed/fail-open routing decision,
    so a repeated `--base`/`--head` picking the first occurrence is not the
    main#1060 hazard class. main#1060 instead scoped the last-flag-wins fix
    to the DIRECT `walk_flag_values` callers that resolve `--repo`/`-R` for
    authoritative routing (`_repo_flag_parse.extract_repo`,
    `_wave_label_parse._parse_edit_segment`,
    `block_squash_wave_merge._iter_squash_merges`) — this function was left
    alone rather than repurposed for a use case it doesn't have today.
    """
    tokens = tokenize(command)
    if tokens is None:
        if not regex_fallback:
            return None
        for flag in sorted(wanted, key=len, reverse=True):
            pattern = rf"(?:^|\s){re.escape(flag)}(?:=|\s+)(\S+)"
            match = re.search(pattern, command)
            if match:
                return match.group(1)
        return None
    values = walk_flag_values(tokens, wanted)
    return values[0] if values else None


def extract_dash_c_pairs(segment: list[str]) -> list[tuple[str, str]]:
    """Walk a git segment and yield (key, value) for every `-c key=value`.

    Handles `-c k=v` (two tokens) and `-c=k=v` (one token, rare). shlex has
    already unquoted the value half, so `-c user.name="A B"` arrives here as
    `["-c", "user.name=A B"]` (two tokens; the inner `=` is the key/value
    separator handled by `split("=", 1)`).

    MUST strip command prefixes, in lockstep with `find_git_subcommand`
    (main#1141 review). `validate_commit_identity` calls BOTH on the SAME
    segment: `find_git_subcommand` to recognize the `commit` verb, then this
    to read the identity flags. When only the first stripped,
    `timeout 60 git -c user.name=… commit` was recognized as a commit but its
    `-c` pairs came back EMPTY, so the gate blocked a fully compliant commit
    with "missing `-c user.name=` flag" — naming the exact flag the operator
    had passed. Two functions holding different views of one segment is the
    hazard; keeping the strip symmetric is the invariant that prevents it.
    A false positive is strictly worse than the evasion it came from: an
    evasion costs one missed gate, a false positive blocks correct work for
    everyone with a message that reads as a lie.
    """
    pairs: list[tuple[str, str]] = []
    segment = strip_command_prefixes(segment)
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


# ---------------------------------------------------------------------------
# Unconditional-leading-`cd` routing resolution (main#1151)
# ---------------------------------------------------------------------------
#
# `extract_leading_cd_target` ROUTES — it decides which GitHub repo eight hooks
# read and three hooks WRITE to. Its old implementation took the LAST `cd /abs`
# pair anywhere in the flat segment list, which checks none of the three
# properties that actually make a `cd` honourable. A `cd` may only be honoured
# when it is
#
#   (1) UNCONDITIONAL      — not guarded by `||`, not inside if/while/for/case,
#   (2) IN THE CURRENT SHELL — not in a subshell, pipeline, `&` background job
#                              or command substitution, and
#   (3) BEFORE the work    — positioned ahead of the command being routed.
#
# Segment-level analysis provably cannot answer any of these: by the time
# `iter_command_segments` has split on `;`/`&&`/`||`/`|` the control flow that
# decides whether a `cd` runs is already gone, and a guarded `cd` lands at token
# 0 of its own segment with no leader left to withhold.
#
# TWO CO-PRIMARY MECHANISMS, not a primary and a safety net:
#
#   1. `_ast_leading_cd_target`  — the bashlex AST, where all three properties
#                                  are directly readable.
#   2. `_degraded_leading_cd_target` — a token scan that FAILS CLOSED on any
#                                  control flow, used whenever (1) cannot see
#                                  the command.
#
# (2) is NOT a rare degraded path. main#1152 established, against the installed
# bashlex, that a QUOTED-delimiter heredoc does not parse AT ALL:
#
#     bashlex.parse("cat <<'EOF'\nx\nEOF\n")  -> ParsingError
#
# `<<'EOF'` / `<<"EOF"` raise; only bare `<<EOF` / `<<-EOF` parse. The quoted
# form is the DOMINANT one in this repo (`python3 - <<'PY'`, `gh issue comment
# --body-file - <<'EOF'`), so the commands most likely to carry a `cd` are
# exactly the ones the AST cannot see. And the failure is SILENT: bashlex_available()
# stays True (it reports import success, not per-command success) and
# `iter_command_segments_ast` returns the same None it uses for "bashlex
# absent". An AST-ONLY fix here would therefore have reported success and
# changed nothing on precisely those commands — which is why (2) must close, on
# its own, every family (1) closes. Pinned by `CdRoutingWhenBashlexCannotParse`.
#
# The asymmetry is deliberate and is the same call main#1141 made: UNDER-
# detecting a `cd` degrades to the recoverable #650 invocation-cwd fallback;
# OVER-detecting writes into the wrong repository, which no retry undoes.

# Operators that may PRECEDE a `cd` in the leading run without making it
# conditional on something other than the run itself. `;` is plain sequencing.
# `&&` is admitted ONLY because the scan stops at the first non-`cd` element:
# every earlier element of the run is itself a `cd`, so if this `cd` executes at
# all it executes from the directory already recorded. `||` (runs only when the
# left side FAILED) and `&` (backgrounds the left side into a subshell) are both
# disqualifying, in either position.
_UNCONDITIONAL_LEADING_OPS = frozenset({";", "&&"})

# Commands that move (or replace) the CURRENT shell WITHOUT being spelled `cd`.
# A leading `cd` is only evidence of where the work runs if nothing between it
# and the work moves the shell again — and `pushd`/`popd`/`eval`/`source`/`.`
# all do, invisibly to a scan that keys on the literal token `cd`.
#
# ONE list, consumed by BOTH mechanisms. It started life inline in the degraded
# token set only, and the AST path keyed on `words[0] == "cd"` alone — so
# `cd /a && pushd /b && gh …` returned `/a` on the AST path while the degraded
# path correctly returned None, making the primary strictly weaker than the
# co-primary it is declared equal to (found at the #1156 merge gate, Aino
# Virtanen). Two mechanisms with independently maintained lists WILL drift
# again; deriving both from this frozenset is what makes that impossible, and
# is a stronger fix than patching the AST branch to match.
#
# `exec` is included for the same parity even though it cannot carry a `cd`
# (`exec cd /x` fails — exec needs an external command): it REPLACES the shell,
# so the routed command never runs at all. Refusing costs only recovery.
_CWD_MOVING_COMMANDS = frozenset({"pushd", "popd", "eval", "source", ".", "exec"})

# Fail-closed scan (bashlex absent, OR the command did not parse — most often
# a quoted-delimiter heredoc): any of these appearing as its OWN shlex token
# means the command carries control flow, a subshell, a pipeline or an opaque
# cwd change that the flat token stream cannot reason about -> return None and
# let the caller fall back to the invocation cwd. `&&` and `;` are deliberately
# ABSENT: they are the separators of the leading `cd` run itself, and dropping
# `cd /worktree && gh pr create` would destroy the #521 recovery signal this
# resolver exists for.
_DEGRADED_CONTROL_FLOW_TOKENS = (
    frozenset(
        {
            "if",
            "then",
            "else",
            "elif",
            "fi",
            "while",
            "until",
            "for",
            "do",
            "done",
            "case",
            "esac",
            "select",
            "function",
            "{",
            "}",
            "(",
            ")",
            "!",
            "|",
            "||",
            "&",
        }
    )
    | _CWD_MOVING_COMMANDS
)


def _ast_command_words(node) -> list[str]:
    """Word-kind tokens of a bashlex CommandNode, in source order.

    `KEY=value` prefixes arrive as AssignmentNodes and redirections as
    RedirectNodes; neither is word-kind, so both drop out naturally. That is
    correct for routing: `FOO=1 cd /dest` and `cd /dest > /dev/null` both move
    the calling shell (verified in bash and zsh — `cd` is a builtin, and a
    one-shot assignment prefix does not spawn a subprocess for a builtin).
    """
    return [p.word for p in node.parts if getattr(p, "kind", None) == "word"]


def _ast_top_level_elements(tree) -> list[tuple[object, str | None, str | None]]:
    """Flatten one parse tree's TOP-LEVEL list into (node, prev_op, next_op).

    Only the outermost list is flattened — nothing nested is descended into.
    That is the point: a node that is not a plain top-level CommandNode (an
    `if`, a `for`, a `{ }` group, a subshell, a pipeline) is exactly the case
    the caller must refuse to reason about.
    """
    if getattr(tree, "kind", None) != "list":
        return [(tree, None, None)]
    elements: list[tuple[object, str | None, str | None]] = []
    pending_prev: str | None = None
    for part in tree.parts:
        if getattr(part, "kind", None) == "operator":
            if elements:
                node, prev_op, _ = elements[-1]
                elements[-1] = (node, prev_op, part.op)
            pending_prev = part.op
            continue
        elements.append((part, pending_prev, None))
        pending_prev = None
    return elements


def _ast_subtree_moves_cwd(node) -> bool:
    """True if anything under `node` can move the shell's cwd.

    That means a command-position `cd` OR any of `_CWD_MOVING_COMMANDS`
    (`pushd`, `popd`, `eval`, `source`, `.`, `exec`) — the second half is the
    part a `words[0] == "cd"` check misses, and missing it left
    `cd /a && pushd /b && gh …` resolving to `/a` while both shells run the gh
    in `/b` (#1156 merge gate).

    Used on everything AFTER the leading `cd` run. A cwd move there makes the
    resolver's single answer ambiguous with respect to the command a consumer
    actually cares about (`gh issue edit 5 …; cd /elsewhere` — main#1151
    family B), or is a group whose `cd` applies to a later command in the same
    group (`cd /a && { cd /b ; gh x ; }`). Either way: refuse to answer.

    Only CommandNodes are inspected, so `gh pr create --body "cd /ghost"` —
    where the text is a WordNode value, not a command — does not trip it.
    """
    found = False

    class _CwdMoveFinder(bashlex_ast.nodevisitor):
        def visitcommand(self, n, parts):
            nonlocal found
            words = [p.word for p in parts if getattr(p, "kind", None) == "word"]
            if words and (words[0] == "cd" or words[0] in _CWD_MOVING_COMMANDS):
                found = True
            return True

    _CwdMoveFinder().visit(node)
    return found


def _ast_leading_cd_target(command: str) -> tuple[bool, str | None]:
    """AST answer to "which directory is the shell in when the work starts?".

    Returns `(parsed, target)`. `parsed is False` means bashlex is unavailable
    or the command did not parse, and the caller MUST fall back to the degraded
    token scan — it is never "no cd". `parsed is True` with `target is None`
    means the AST was read and the command has no honourable leading `cd`.

    The `_BASHLEX_AVAILABLE` gate lives HERE, outside the cache, for the same
    reason `iter_command_segments_ast` keeps it outside
    `_iter_command_segments_ast_cached`: a test monkeypatching the flag to
    simulate a bare checkout must never be served a stale cached AST answer.
    """
    if not _BASHLEX_AVAILABLE:
        return (False, None)
    return _ast_leading_cd_target_cached(command)


@lru_cache(maxsize=256)
def _ast_leading_cd_target_cached(command: str) -> tuple[bool, str | None]:
    """Memoized core of `_ast_leading_cd_target`. Assumes bashlex is available.

    Memoized (#1113): pure in `command`, and returns an immutable tuple of
    immutable values, so the cached object can be handed out directly — no
    copy needed, no mutation hazard.
    """
    try:
        trees = bashlex.parse(command)
    except Exception:
        # Same resilience posture as `_iter_command_segments_ast_cached`: any
        # bashlex failure signals the caller to fall back, never a crash.
        return (False, None)

    elements: list[tuple[object, str | None, str | None]] = []
    for tree in trees:
        elements.extend(_ast_top_level_elements(tree))

    target: str | None = None
    index = 0
    # Phase 1 — the unconditional leading run of simple `cd` commands.
    while index < len(elements):
        node, prev_op, next_op = elements[index]
        if getattr(node, "kind", None) != "command":
            break  # compound / pipeline / control flow: phase 2 decides
        words = _ast_command_words(node)
        if not words or words[0] != "cd":
            break  # first real work — the cwd is fixed from here
        if prev_op is not None and prev_op not in _UNCONDITIONAL_LEADING_OPS:
            return (True, None)  # `||`-guarded or `&`-preceded
        if next_op == "&":
            return (True, None)  # backgrounded: the calling shell never moves
        if len(words) != 2 or not words[1].startswith("/"):
            # Anything we cannot pin to one absolute directory — `cd` (HOME),
            # `cd -`, `cd -P /x`, `cd sub`, `cd "$(git rev-parse …)"`. A
            # RELATIVE target is the sharpest of these: `cd /parent && cd
            # child-repo` really does land in a DIFFERENT repository, so
            # silently keeping `/parent` was itself a misroute. Refuse.
            return (True, None)
        target = words[1]
        index += 1

    # Phase 2 — nothing after the leading run may move the cwd again. Starts AT
    # the breaking element, so a `pushd`/`eval`/`source` that ended phase 1 is
    # itself inspected; phase 1 needs no matching check of its own.
    for node, _prev_op, _next_op in elements[index:]:
        if _ast_subtree_moves_cwd(node):
            return (True, None)
    return (True, target)


def _degraded_leading_cd_target(command: str) -> str | None:
    """Fail-closed token scan — the issue's fix direction 2, as a CO-PRIMARY.

    Runs whenever the AST cannot see the command: bashlex absent, or (far more
    often) a command carrying a quoted-delimiter heredoc, which the installed
    bashlex cannot parse at all. `python3 - <<'PY'` and `gh issue comment
    --body-file - <<'EOF'` are the repo's dominant heredoc forms, so this path
    is ordinary traffic, not an edge case, and it must close every family the
    AST path closes rather than relaxing to the old last-`cd`-wins scan.

    Mirrors the AST phase model with the only tool left: reject outright any
    command whose shlex token stream shows control flow, a subshell, a pipeline
    or an opaque cwd change (`_DEGRADED_CONTROL_FLOW_TOKENS`), then accept only
    a leading run of `cd /abs` segments with no `cd` anywhere after it.

    Heredoc BODIES are deliberately not stripped here (`strip_heredocs` is not
    called): a body always follows its command, so its tokens can never occupy
    the leading position, and any `cd` they contribute lands in the non-leading
    phase and forces None. Unstripped bodies can therefore only cost recovery,
    never buy a route — verified in `test_heredoc_body_cannot_inject_a_route`.

    Deliberately does NOT call `normalize_command_separators` — see the
    main#1151 ordering constraint recorded in `wave_29_scope`. Without it an
    unspaced `cd /a;gh …` glues into one 3-token segment and is refused, which
    is the safe direction; adding normalization here would widen this path
    without the AST's control-flow knowledge behind it.
    """
    tokens = tokenize(command)
    if tokens is None:
        return None
    if any(tok in _DEGRADED_CONTROL_FLOW_TOKENS for tok in tokens):
        return None
    target: str | None = None
    leading = True
    for segment in iter_command_segments(tokens):
        is_cd = segment[0] == "cd"
        if not is_cd:
            leading = False
            continue
        if not leading:
            return None  # a `cd` after real work — ambiguous, refuse
        if len(segment) != 2 or not segment[1].startswith("/"):
            return None
        target = segment[1]
    return target


def extract_leading_cd_target(command: str) -> str | None:
    """Directory the shell is in when the command's first real work runs.

    Returns the target of the last `cd <absolute-dir>` in the command's
    UNCONDITIONAL LEADING RUN of `cd` commands, or None when there is no such
    run or the answer cannot be established with certainty. The caller is
    responsible for checking the path actually exists.

    This is the in-band recovery signal for the worktree-subagent cwd-anchor
    bug (#521): `cd /worktree && gh pr create` carries the real cwd in the
    command itself even though the harness `cwd` field points at the
    orchestrator's spawn-time directory.

    Why the contract is this narrow
    -------------------------------
    This function ROUTES: it decides which repo an action targets, and three
    hooks on its chain WRITE (`post_wave_kickoff_comment`,
    `auto_add_issue_to_board`, `post_label_change_wave_field_sync`), so a wrong
    answer is an unrecoverable write into the wrong repository. A `cd` is only
    evidence of where the work runs when it is (1) unconditional, (2) executed
    by the CURRENT shell, and (3) positioned before that work. main#1151 found
    two families where the old last-`cd`-wins scan honoured a `cd` that was
    none of those:

      A. `true || cd /sibling ; gh issue edit 5 …` — the `cd` never runs.
      B. `gh issue edit 5 … ; cd /sibling`        — the `cd` runs AFTER the gh.

    Both are answered structurally by `_ast_leading_cd_target`, which reads the
    bashlex AST rather than the flattened segment list. Segment-level analysis
    cannot answer them: `iter_command_segments` has already discarded the
    control flow, and a guarded `cd` sits at token 0 of its own segment with no
    leader left to withhold — which is why patching leader-by-leader kept
    producing new families.

    The AST is NOT the sole mechanism. A quoted-delimiter heredoc (`<<'EOF'`,
    the repo's dominant form) does not parse at all, so
    `_degraded_leading_cd_target` — a token scan that fails closed on any
    control flow — is a CO-PRIMARY that must close the same families on its
    own. See the module-level § Unconditional-leading-`cd` routing resolution.

    Strips NOTHING — `cd` must be word 0 of a top-level simple command
    (main#1141 review round 3). Both prefix families are unsafe here:

    1. **Compound leaders** (`then`, `do`, `else`, `{`, `(`) guard a body that
       may not run. `if [ -f /nonexistent ]; then cd /repo-b; fi; gh issue
       edit 5` never executes that `cd`; stripping `then` resolved it to
       repo-b and would have posted to `repo-b#5` instead of `repo-a#5`.
    2. **Command-prefix wrappers** (`timeout`, `env`, `nice`, `nohup`) cannot
       carry a `cd` AT ALL — `cd` is a shell builtin, so an exec-wrapper runs
       a subprocess (or nothing) and the calling shell's directory is
       unchanged. Verified in both bash and zsh: `env FOO=1 cd /dest; pwd`
       prints the ORIGINAL directory. Stripping the wrapper here would have
       claimed a `cd` that provably never happened. (`command cd` is worse
       than useless as a signal: bash honours it, zsh does not.)

    That is the asymmetry with the matchers, stated exactly: over-matching is
    conservative for a GATE (worst case, inspect a command that would not have
    run) and destructive for a RESOLVER (send output where the command never
    went). So `find_git_subcommand` / `find_gh_subcommand` /
    `extract_dash_c_pairs` strip everything and this function strips nothing.

    Accepted cost — UNDER-recovery, in every direction. None is returned for a
    `cd` in a taken `else` or a real loop iteration, for a `cd` reached through
    `mkdir -p /a && cd /a && gh …` (the run is no longer leading), for a
    RELATIVE `cd` (`cd /parent && cd child-repo` — refused outright now,
    because keeping `/parent` was itself a cross-repo misroute in a tree of
    nested child repos), for a pipeline sitting after the run, and for anything
    in `_CWD_MOVING_COMMANDS` after the run (`cd /a && pushd /b && gh …`,
    `… && eval 'cd /b' && …`, `… && source s.sh && …`) — including `exec`,
    which does not move the shell but replaces it, so the routed command never
    runs at all. Each of those falls back to the invocation cwd, which is the
    recoverable #650 behaviour. Claiming no knowledge is recoverable; claiming
    the wrong directory is not.

    That last group is NOT a frontier the design leaves open — it is a case
    where the two mechanisms had drifted. The degraded scan already refused
    `pushd`/`eval`/`source`, so the AST path keying on the literal token `cd`
    was strictly weaker than its own fallback (#1156 merge gate). Both now read
    the same `_CWD_MOVING_COMMANDS` frozenset. A shape whose cwd this function
    cannot compute must resolve to None on BOTH paths, and any new entry
    belongs in that one set, never in a per-path list.
    """
    parsed, target = _ast_leading_cd_target(command)
    if parsed:
        return target
    return _degraded_leading_cd_target(command)


def resolve_invocation_cwd(input_data: dict) -> str:
    """Resolve the directory the triggering command actually runs in.

    Priority:
      1. An absolute, existing `cd <dir>` target extracted from the command
         string (recovers a worktree subagent's real cwd — #521).
      2. resolve_tool_cwd(input_data) — stdin `cwd` then os.getcwd().

    Use this (rather than resolve_tool_cwd) for any hook that derives repo
    IDENTITY from cwd — i.e. anything that runs `git remote get-url origin`
    or `git rev-parse` to decide which GitHub repo a command targets. The
    plain resolve_tool_cwd is fine for hooks that only need *a* git context
    and don't care about cross-repo misattribution.
    """
    command = input_data.get("tool_input", {}).get("command", "")
    if isinstance(command, str) and command:
        cd_target = extract_leading_cd_target(command)
        if cd_target and os.path.isdir(cd_target):
            return cd_target
    return resolve_tool_cwd(input_data)


def _default_origin_url_runner(cwd: str) -> str | None:
    """Return the `origin` remote URL for the git repo at `cwd`, or None.

    Shells out to `git -C <cwd> remote get-url origin`. Any failure (not a
    git repo, no `origin` remote, git missing) yields None so the caller
    treats the repo as unresolvable rather than crashing.
    """
    try:
        result = subprocess.run(
            ["git", "-C", cwd, "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


# Markers that make a `--repo`/`-R` flag value UNRESOLVABLE as a repo reference:
# shlex leaves an unexpanded shell variable (`$VAR`, `${VAR}`) or command
# substitution (`` `...` ``, `$(...)`) as a LITERAL token, and any whitespace in
# the extracted value means we captured a non-flag fragment (e.g. an
# attached-short false positive off a `--body "-R x"` token). Treating any of
# these as a repo name would MISROUTE the downstream `gh` call to the wrong (or
# a nonexistent) repository — the fail-open #981 closed at the merge gate,
# applied here to the wave-label hooks' repo resolution.
_UNRESOLVABLE_REPO_VALUE_RE = re.compile(r"[$`\s]")


def repo_short_name_from_flag_value(value: str) -> str | None:
    """Extract the GitHub repo SHORT NAME from a `--repo`/`-R` flag value.

    The flag value is the pre-shell-expansion token gh would receive, e.g.
    `noorinalabs/noorinalabs-main`, `noorinalabs/noorinalabs-main.git`, or a
    full `https://github.com/owner/name` URL. Returns the last path segment
    with any trailing `.git` stripped:

        noorinalabs/noorinalabs-main                       -> noorinalabs-main
        https://github.com/noorinalabs/noorinalabs-deploy  -> noorinalabs-deploy

    Returns None when the value is UNRESOLVABLE — an unexpanded shell variable
    or command substitution (`$DA`, `${REPO}`, `` `...` ``, `$(...)`) that shlex
    left literal, a whitespace-bearing fragment, or empty. Per #981, an
    unresolvable repo token must be treated as "no known repo" by the caller
    (fail-closed: block/skip), NEVER coerced into a repo name — coercing it would
    misroute the gh call. This is the flag-value sibling of
    `resolve_repo_short_name` (which resolves the ambient repo from the
    invocation cwd's `origin` remote); the flag is authoritative over cwd (#985).
    """
    if not value or _UNRESOLVABLE_REPO_VALUE_RE.search(value):
        return None
    name = value.rstrip("/").split("/")[-1]
    if name.endswith(".git"):
        name = name[: -len(".git")]
    return name or None


def resolve_repo_short_name(input_data: dict, *, git_runner=None) -> str | None:
    """Resolve the GitHub repo NAME from the invocation cwd's `origin` remote.

    When a `gh issue edit/create` command omits `--repo`, gh resolves the
    target repository from the ambient git context (the cwd's `origin`
    remote). Hooks that need the repo name to drive a GraphQL/REST call must
    mirror that resolution. Returns the last path segment of the `origin`
    URL with any trailing `.git` stripped — for both scp-form and https-form
    URLs:

        git@github.com:noorinalabs/noorinalabs-main.git  -> noorinalabs-main
        https://github.com/noorinalabs/noorinalabs-main   -> noorinalabs-main

    Returns None when the cwd is not a git repo, has no `origin` remote, or
    the runner otherwise fails. The cwd is resolved via
    `resolve_invocation_cwd` so a worktree-subagent's real dir is used (the
    `cd <dir> && ...` recovery path, #521).

    `git_runner(cwd) -> str | None` is the injection point for tests; the
    default shells out to `git -C <cwd> remote get-url origin`.
    """
    cwd = resolve_invocation_cwd(input_data)
    runner = git_runner or _default_origin_url_runner
    url = runner(cwd)
    if not url:
        return None
    name = url.strip().rstrip("/").split("/")[-1]
    if name.endswith(".git"):
        name = name[: -len(".git")]
    return name or None


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
