#!/usr/bin/env python3
"""PreToolUse hook: Validate git commit identity flags.

Ensures every `git commit` command includes `-c user.name=` and `-c user.email=`
flags matching a roster member from the charter's Commit Identity table.

Parent+child roster merge (#112 part a):
  When the target repo (either the local repo or a `cd <path>` target) is a
  child of another git repo that itself has `.claude/team/roster.json`, the
  parent roster is loaded and merged with the child roster. Same-name entries
  in the child override the parent (child wins). Walk-up is limited to ONE
  level to avoid false positives in nested `code/` trees. This lets org-level
  coordinators commit in child repos without duplicating their entries into
  every child `roster.json`.

cwd-fallback for cross-repo detection (#475 fix 1):
  When the command has NO literal `cd <path>` prefix, the hook still needs
  to know which repo the commit will land in. The Claude Code harness passes
  the tool-call cwd via `input_data["cwd"]`; if that cwd has its own
  `.claude/team/roster.json`, the hook merges that roster instead of falling
  back to the parent ROSTER. This eliminates the brittleness of requiring
  every operator to compose a `cd` prefix when their shell cwd already names
  the right repo.

Indirect-exec bypass detection (#475 fix 2):
  PreToolUse hooks only see the literal Bash `command` parameter. Wrappers
  like `printf '<git-commit-cmd>' | bash`, `bash -c '<git-commit-cmd>'`,
  `bash <script-with-git-commit>`, and `bash <(echo '<git-commit-cmd>')`
  hide the actual `git commit` from the outer-command tokenizer. The hook
  now scans for these shapes and, if the payload looks like a git commit,
  BLOCKS with a message pointing operators to the canonical shape. This
  closes a silent bypass discovered in P3W11 PR #41 fixup.

Input Language
==============

Fires on:      PreToolUse Bash
Matches:       git [-c k=v ...] [-C path] [other globals] commit [args]
               (any segment in the compound command — split on ;, &&, ||, |;
               leading KEY=value env-vars are stripped)
               PLUS indirect-exec wrappers whose payload contains git commit
               (see "Indirect-exec bypass detection" above).
Does NOT match: prose containing the literal "git commit" inside heredoc
                bodies, --body / --body-file argument values, $(cat <<'EOF' …)
                command substitutions. Tokenized via shlex; the matcher only
                fires on actual command-position git invocations.

Flag pass-through:
    -c user.name=<value>   → required, validated against roster
    -c user.email=<value>  → required, validated against roster
    cd <path> && git ...   → loads <path>'s merged roster (cross-repo commit)
    no cd prefix           → loads cwd's merged roster (fix 1, #475)

Substring-bug history fixed by tokenization:
    #226 — unquoted -c user.email=val no longer slurps to EOL
    #188 — nested $(cat <<'EOF' ... EOF) no longer mangles the parser
    Both root in regex-against-raw-string parsing; switched to shlex tokens.

Exit codes:
  0 — allow (not a git commit, or identity is valid)
  2 — block (missing or invalid identity flags, OR indirect-exec wrapper
       hiding a git commit from outer-command inspection)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _shell_parse import (  # noqa: E402
    extract_dash_c_pairs,
    find_git_subcommand,
    iter_command_segments,
    resolve_tool_cwd,
    strip_heredocs,
    tokenize,
)
from annunaki_log import log_pretooluse_block  # noqa: E402


def _read_roster(roster_path: Path) -> dict[str, str]:
    """Read a roster.json file, returning {} on any failure (fail-open)."""
    try:
        data = json.loads(roster_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _load_merged_roster(repo_path: Path) -> dict[str, str]:
    """Load `repo_path`'s roster, merged with its parent repo's roster if any.

    Parent detection (ONE level up only):
      1. `repo_path/..` must be a directory containing `.git` (i.e. a git repo).
      2. `repo_path/../.claude/team/roster.json` must exist.
    If both hold, the parent roster is loaded and merged under the child roster
    — child keys override parent keys, so a same-name entry in the child wins.
    Any OSError / malformed JSON at any step is swallowed; a broken parent
    roster must never block a child repo's valid commit.
    """
    child_path = repo_path / ".claude" / "team" / "roster.json"
    child_roster = _read_roster(child_path)

    try:
        parent_dir = repo_path.parent
        if (
            parent_dir != repo_path
            and (parent_dir / ".git").exists()
            and (parent_dir / ".claude" / "team" / "roster.json").is_file()
        ):
            parent_roster = _read_roster(parent_dir / ".claude" / "team" / "roster.json")
        else:
            parent_roster = {}
    except OSError:
        parent_roster = {}

    # Child wins on key collision.
    return {**parent_roster, **child_roster}


# Module-level roster for the repo hosting this hook. `_load_merged_roster`
# walks up one level; at this repo (noorinalabs-main) there is no parent repo
# with a roster, so this collapses to the local roster only.
ROSTER: dict[str, str] = _load_merged_roster(Path(__file__).resolve().parent.parent.parent)


def _detect_target_roster(command: str, *, cwd: str | None = None) -> dict[str, str] | None:
    """Detect cross-repo commits and load the target repo's merged roster.

    Resolution order:
      1. Literal `cd /path/to/repo` prefix in the command → that path.
      2. Otherwise fall back to the tool-call `cwd` (#475 fix 1): when an
         operator is already in a child-repo worktree and runs a bare
         `git -c ... commit ...`, the cwd is the right anchor for roster
         lookup. Without this fallback the hook resolves names against the
         parent-only ROSTER and rejects valid child-repo personas.

    The resolved path must (a) be an existing directory and (b) host a
    `.claude/team/roster.json`. If either check fails the function returns
    None and the caller uses the module-level ROSTER.

    Returns the target merged roster dict, or None to use the local ROSTER.
    """
    cd_match = re.search(r"cd\s+([^\s;&|]+)", command)
    if cd_match:
        target_dir = Path(cd_match.group(1)).expanduser().resolve()
    elif cwd:
        target_dir = Path(cwd).expanduser().resolve()
    else:
        return None
    if not target_dir.is_dir():
        return None
    roster_path = target_dir / ".claude" / "team" / "roster.json"
    if not roster_path.is_file():
        return None
    merged = _load_merged_roster(target_dir)
    return merged or None


# ============================================================================
# Indirect-exec bypass detection (#475 fix 2)
# ============================================================================
#
# PreToolUse hooks see only the literal outer Bash command. The wrapper
# shapes below hide an inner `git commit` from the existing tokenizer:
#
#   printf '<git-commit>' | bash            (also sh / zsh; also echo)
#   bash -c '<git-commit>'                  (also sh / zsh)
#   bash <(echo '<git-commit>')             (process substitution)
#   bash <script-file>                      (also sh / zsh; reads file content)
#
# Each detector below returns the inferred inner payload string (or None
# if the shape doesn't match). The orchestrator `_detect_indirect_commit`
# tries each in turn; if any payload contains a git-commit-shape, the
# command is blocked.
#
# Design notes:
# - Single-pass regexes are used because shlex.split on the OUTER command
#   would lose the visual structure (e.g. `bash -c '<...>'` becomes
#   `['bash', '-c', '<...>']` with the quotes consumed — useful for the
#   `-c` case, but heredocs/process-substitutions don't survive shlex
#   cleanly). We grep first, then re-tokenize the inner payload through
#   the existing `_find_commit_segment` machinery for validation.
# - Detection is intentionally narrow: requires both `git` AND `commit`
#   in the inner payload. Innocent shapes like `printf 'echo hello' | bash`
#   or `bash -c 'ls -la'` pass through.
# - For `bash <script>` the script is read from disk; if unreadable the
#   shape is reported (`payload=""`) so the orchestrator can decide. We
#   only block when the readable content matches the git-commit shape;
#   bare `bash some-script.sh` whose content is innocent is allowed.

# Wrapper interpreters we recognise.
_INTERPRETERS = r"(?:bash|sh|zsh)"

# printf/echo … | <interpreter>. Captures the printf/echo argument body.
# Anchor on `printf` or `echo` at word boundary, allow any chars up to the
# pipe (so multi-arg printf works), then `| <interpreter>` followed by
# end-of-command or another separator.
_PIPE_TO_SHELL_RE = re.compile(
    r"\b(?:printf|echo)\b(?P<payload>.+?)\|\s*" + _INTERPRETERS + r"\b",
    re.DOTALL,
)

# <interpreter> -c '<payload>' or "<payload>" — captures the -c argument
# verbatim, including its surrounding quotes (we strip them before
# scanning).
_DASH_C_RE = re.compile(
    r"\b" + _INTERPRETERS + r"\s+-c\s+(?P<payload>(?P<q>['\"]).*?(?P=q)|\S+)",
    re.DOTALL,
)

# <interpreter> <(...) — process substitution. Captures the inner content
# of the parenthesised expression. Note: nested parens inside the
# substitution will trip this; we accept that as a known limitation
# because nested process-substitution-with-git-commit-inside is exotic
# enough that the surrounding context will almost certainly trigger one
# of the other detectors.
_PROCESS_SUB_RE = re.compile(
    r"\b" + _INTERPRETERS + r"\s+<\(\s*(?P<payload>[^)]+?)\s*\)",
    re.DOTALL,
)

# <interpreter> <scriptpath> — the script path is whatever non-flag
# non-redirect token follows. Restricted to tokens ending in `.sh` to
# avoid false-positives on `bash -c '...'` (handled above) and `bash`
# bare (interactive shell, no script). The path may be absolute or
# relative; if relative we resolve against the hook's cwd.
_SCRIPT_INVOKE_RE = re.compile(
    r"\b" + _INTERPRETERS + r"\s+(?P<path>[^\s|;&<>]+\.sh)\b",
)

# Inner-payload commit-shape: looser than the outer `_COMMIT_FALLBACK_RE`
# because the payload we're scanning is already known to be the inner
# argument of a printf/echo, shell -c, process substitution, or script
# file. It often starts inside quotes the extractor didn't strip, so
# requiring a shell-operator or whitespace anchor before `git` rejects
# legitimate matches (`'git ... commit ...'` payloads start with `'`).
#
# We use a simple `\bgit\b ... \bcommit\b` shape with a segment-boundary
# exclusion in the middle so a payload like
# `cd /repo; echo "not a real commit"` doesn't false-match: the `;` would
# break the bridge between `git` and `commit`. Path-suffix exclusion is
# preserved via the negative lookahead.
_INNER_COMMIT_RE = re.compile(
    r"\bgit\b[^;&|]*?\bcommit\b(?!\S*/)",
    re.DOTALL,
)


def _payload_looks_like_commit(payload: str) -> bool:
    """Return True if the (already-extracted) inner payload contains git commit."""
    if not payload:
        return False
    return bool(_INNER_COMMIT_RE.search(strip_heredocs(payload)))


def _strip_outer_quotes(s: str) -> str:
    """If `s` is wrapped in matching single or double quotes, strip one layer."""
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        return s[1:-1]
    return s


def _read_script_if_safe(script_path: str, cwd: str | None) -> str | None:
    """Read script content for inspection. Returns None on any error.

    The path is resolved against `cwd` if relative. We restrict reads to
    regular files under 256 KiB — if an operator is funnelling a multi-
    megabyte payload into `bash <script>` it isn't a normal commit shape
    and the safe answer is "don't inspect" (the caller treats that as
    "no payload extracted" → no block).
    """
    try:
        p = Path(script_path)
        if not p.is_absolute() and cwd:
            p = (Path(cwd) / p).resolve()
        else:
            p = p.resolve()
        if not p.is_file():
            return None
        if p.stat().st_size > 256 * 1024:
            return None
        return p.read_text(encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        return None


def _detect_indirect_commit(command: str, *, cwd: str | None = None) -> str | None:
    """Detect indirect-exec wrappers carrying a hidden git commit.

    Returns a short label describing the matched shape (used by the
    caller's block message) when the inner payload looks like a git
    commit, or None when no wrapper-with-commit shape is matched.

    Shapes checked, in order:
      1. printf/echo … | bash|sh|zsh
      2. bash|sh|zsh -c '<payload>'
      3. bash|sh|zsh <(…)  (process substitution)
      4. bash|sh|zsh <script.sh>  (reads the script content)
    """
    for m in _PIPE_TO_SHELL_RE.finditer(command):
        if _payload_looks_like_commit(m.group("payload")):
            return "printf/echo piped to shell"

    for m in _DASH_C_RE.finditer(command):
        payload = _strip_outer_quotes(m.group("payload"))
        if _payload_looks_like_commit(payload):
            return "shell -c"

    for m in _PROCESS_SUB_RE.finditer(command):
        if _payload_looks_like_commit(m.group("payload")):
            return "process substitution"

    for m in _SCRIPT_INVOKE_RE.finditer(command):
        content = _read_script_if_safe(m.group("path"), cwd)
        if content and _payload_looks_like_commit(content):
            return f"shell script ({m.group('path')})"

    return None


_PARSE_FAILURE = object()  # sentinel: tokenize returned None


def _find_commit_segment(command: str) -> list[str] | None | object:
    """Find the `git ... commit ...` segment in `command`.

    Returns:
      - list[str]      — the commit segment tokens (allow identity validation)
      - None           — tokenize succeeded but no commit subcommand found
      - _PARSE_FAILURE — tokenize failed (unbalanced quotes); caller must use
                         regex fallback

    Strips heredocs first so a heredoc body containing the literal phrase
    "git commit" cannot be confused with a real invocation.
    """
    cleaned = strip_heredocs(command)
    tokens = tokenize(cleaned)
    if tokens is None:
        return _PARSE_FAILURE
    for segment in iter_command_segments(tokens):
        decoded = find_git_subcommand(segment)
        if decoded is None:
            continue
        _globals, rest = decoded
        if rest and rest[0] == "commit":
            return segment
    return None


# Regex-only heuristic for the parse-failure fallback: did the command,
# after stripping heredocs, contain `git commit` as a standalone subcommand
# (not embedded in a path/branch-name)?  Anchored at start-of-line or after a
# shell operator. Requires `commit` to appear as a word-boundary token
# separated from options by whitespace (not inside a slash-separated path).
_COMMIT_FALLBACK_RE = re.compile(
    r"(?:^|[;&|]\s*|&&\s*|\|\|\s*)\s*git\b[^;&|]*?(?<!\S)\bcommit\b(?!\S*/)",
    re.MULTILINE,
)


def _looks_like_git_commit(command: str) -> bool:
    """Regex fallback used when shlex.split fails (unbalanced quotes etc.).

    Strips heredocs, then searches for `git ... commit` in command position.
    This is a deliberately broad heuristic: a parse-failure-and-no-commit-
    looking command falls through to allow, but a parse-failure-with-commit-
    looking command blocks (fail-closed for security-relevant validation,
    per the `_shell_parse.tokenize` caller contract).
    """
    cleaned = strip_heredocs(command)
    return bool(_COMMIT_FALLBACK_RE.search(cleaned))


def check(input_data: dict) -> dict | None:
    """Check commit identity. Returns result dict if blocking, None if allowed."""
    tool_name = input_data.get("tool_name", "")
    if tool_name != "Bash":
        return None

    command = input_data.get("tool_input", {}).get("command", "")
    cwd = resolve_tool_cwd(input_data)

    # #475 fix 2: indirect-exec bypass detection. Runs BEFORE the segment
    # tokenizer because wrappers like `printf '…git commit…' | bash` and
    # `bash <script>` hide the actual git invocation from the outer-command
    # parser — if we let `_find_commit_segment` decide first it would return
    # None and the command would slip through unvalidated.
    indirect_shape = _detect_indirect_commit(command, cwd=cwd)
    if indirect_shape is not None:
        result = {
            "decision": "block",
            "reason": (
                f"BLOCKED: indirect-exec wrapper detected ({indirect_shape}) "
                "carrying a hidden `git commit`. Commit-identity validation "
                "only sees the outer Bash command, so wrappers like "
                "`printf '...' | bash`, `bash -c '...'`, `bash <script>`, "
                "and `bash <(...)` would let an unvalidated commit through.\n\n"
                "Run the git command directly so the hook can inspect the "
                "identity flags:\n"
                '  git -c user.name="Your Name" -c user.email="..." \\\n'
                "      commit -F /tmp/msg.txt\n\n"
                "If you need a different working directory, prefix with "
                "`cd <path> && git -c ... commit ...` (canonical cross-repo "
                "shape).\n\n"
                "See issue #475 for the full bypass surface and rationale."
            ),
        }
        log_pretooluse_block("validate_commit_identity", command, result["reason"])
        return result

    commit_segment = _find_commit_segment(command)
    if commit_segment is _PARSE_FAILURE:
        # tokenize() returned None — shlex could not parse the command. Use
        # the regex fallback: if it looks like a git commit, block (fail-closed);
        # otherwise allow (fail-open for non-commit commands).
        if not _looks_like_git_commit(command):
            return None
        result = {
            "decision": "block",
            "reason": (
                "BLOCKED: git commit detected but command failed shlex parsing "
                "(likely unbalanced quotes — common when embedding heredocs "
                'inside `-m "$(cat <<EOF...EOF)"` next to `-c user.name=` flags). '
                "Cannot validate identity flags from a malformed command.\n\n"
                "Fix: write the message to a file and use `-F /path/to/msg.txt`:\n"
                "  printf '%s\\n' \"your commit message\" > /tmp/msg-issue-N.txt\n"
                '  git -c user.name="Foo Bar" -c user.email="..." \\\n'
                "      commit -F /tmp/msg-issue-N.txt\n"
                "(Or for multi-line: heredoc into the file FIRST, then -F.)\n\n"
                "See memory feedback_heredoc_in_git_commit.md for full context."
            ),
        }
        log_pretooluse_block("validate_commit_identity", command, result["reason"])
        return result
    if commit_segment is None:
        # Tokenize succeeded but no git commit subcommand was found.
        return None

    assert isinstance(commit_segment, list)  # _PARSE_FAILURE and None already handled above

    # Cross-repo support: if the command `cd`s into another repo OR the
    # tool-call cwd already names a child-repo worktree (#475 fix 1), load
    # that repo's merged roster instead of the local one.
    roster = _detect_target_roster(command, cwd=cwd) or ROSTER

    pairs = dict(extract_dash_c_pairs(commit_segment))
    name = pairs.get("user.name")
    email = pairs.get("user.email")

    if not name:
        result = {
            "decision": "block",
            "reason": (
                "BLOCKED: git commit missing `-c user.name=` flag. "
                "Charter § Commit Identity requires per-commit identity via -c flags. "
                'Example: git -c user.name="Kwame Asante" '
                '-c user.email="parametrization+Kwame.Asante@gmail.com" commit -m "..."'
            ),
        }
        log_pretooluse_block("validate_commit_identity", command, result["reason"])
        return result

    if not email:
        result = {
            "decision": "block",
            "reason": (
                "BLOCKED: git commit missing `-c user.email=` flag. "
                "Charter § Commit Identity requires per-commit identity via -c flags. "
                'Example: git -c user.name="Kwame Asante" '
                '-c user.email="parametrization+Kwame.Asante@gmail.com" commit -m "..."'
            ),
        }
        log_pretooluse_block("validate_commit_identity", command, result["reason"])
        return result

    if name not in roster:
        result = {
            "decision": "block",
            "reason": (
                f'BLOCKED: user.name="{name}" is not a recognized roster member. '
                f"Valid names: {', '.join(sorted(roster.keys()))}"
            ),
        }
        log_pretooluse_block("validate_commit_identity", command, result["reason"])
        return result

    expected_email = roster[name]
    if email != expected_email:
        result = {
            "decision": "block",
            "reason": (
                f'BLOCKED: user.email="{email}" does not match roster for {name}. '
                f"Expected: {expected_email}"
            ),
        }
        log_pretooluse_block("validate_commit_identity", command, result["reason"])
        return result

    return None


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
