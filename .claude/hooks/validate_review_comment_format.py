#!/usr/bin/env python3
"""PreToolUse hook: Validate Requestor/Requestee format in PR review comments.

Blocks `gh pr comment` if the Requestor matches the branch author, which
indicates the Requestor and Requestee fields are swapped on a verdict
comment (charter post-#244: on `Approved` / `Changes Requested`,
Requestor must be the reviewer, Requestee the PR author).

Scope (closes #378)
===================

This hook enforces Requestor/Requestee non-swap detection ONLY for
`Approved` and `ChangesRequested` verdict comments — i.e., the rows of
the charter `pull-requests.md` § Comment-Based Reviews Direction table
where the canonical binding is `Requestor = reviewer, Requestee = PR-author`.
For `Request` and `Reply` comments — where the Direction-table role
bindings invert (`Requestor = PR-author, Requestee = reviewer`) — the
swap heuristic does not apply and the hook returns None. Author/reviewer
discipline for Request/Reply traffic is operator-trusted and not
hook-gated.

Unrecognized `RequestOrReplied` values (typos, future verdict types
the hook doesn't know about) fail OPEN — the hook returns None and
lets the comment through. Validating the verdict word itself is
covered by a sibling hook (`validate_pr_review`); duplicating that
logic here would couple two hooks that should remain independent.

Uncountable-verdict gates (closes #932)
=======================================

A verdict comment that `validate_pr_review` cannot parse counts as ZERO
reviews and is indistinguishable from no review at all. The reviewer gets
no signal, and the shortfall surfaces hours later at merge time. Two
shapes did exactly that on 2026-07-09, across nine `Approved` comments:

1. **Wrong field name.** `Requestor` + `Requestee` present with
   `RequestOrReplied` absent (the author wrote `Verdict:`) previously
   returned None — allow. It now HARD BLOCKS. Per
   `feedback_safety_direction_over_ux_friction` this cannot be an
   advisory: the hook has no clean auto-fix, and a warning would decay
   exactly like `feedback_generic_prompt_hook_advisory_decay`.

2. **Fields outside the trailer block.** `validate_pr_review`
   scopes field extraction to everything after the LAST sole `---`
   line (#511), so charter fields sitting above a later prose
   horizontal rule parse as None even though the literal
   `RequestOrReplied:` is on the page. Renaming the label alone does
   not fix such a comment. This now HARD BLOCKS too.

The predicate for gate 2 is `validate_pr_review._extract_charter_field`
itself rather than a reimplementation, so the two hooks cannot drift
about what "parseable" means. This is a deliberate exception to the
independence note above: coupling on the *verdict vocabulary* would be
duplication, but coupling on *what the counting hook can actually see*
is the single source of truth the gate exists to enforce.

REST comment-creation (closes #932)
===================================

`gh pr comment` routes through GraphQL. When GraphQL is rate-limited it
fails, and reviewers fall back to
`gh api -X POST .../issues/<N>/comments --input body.json`, which the
old `is_comment_command` never matched (same family as
`feedback_batch_loop_merge_evades`). Matching the command is necessary
but not sufficient: the body must also be recoverable, or the hook fails
open a second time having "seen" the command.

Body extraction (hardened #934)
===============================

`extract_comment_body` reads `--body-file` (the charter-prescribed form,
`agents.md:429`), heredocs, and quoted `--body`. `extract_rest_comment_body`
reads `--input <path>`, `-f body=`, and `-F body=@<path>`.

Every path goes through `_resolve_body_path`, which strips surrounding
quotes and expands `~` and `$VAR`. The first cut of #932 stripped quotes on
one branch and not the other, expanded nothing, and never read `--body-file`
at all — so the exact commands used to post the incident's verdicts
(`-F body=@"$CLAUDE_JOB_DIR/tmp/x.md"`) still sailed through the gate built
to catch them. The tests missed it by passing bare unquoted literals: fixture
realism without *command* realism (`feedback_passing_repro_masks_bug`).

Each path resolves through `_body_for_path`: a heredoc in the SAME command
that writes that path wins over whatever is on disk, because a PreToolUse
hook runs before the command and the command is about to overwrite the file.
Disk-first would validate a stale body while the command posts the heredoc's
— the hook approves one comment and the author posts another. **One stale
file is sufficient; the ordering is wrong by construction, not by frequency.**
A census of how many harvested rows happen to have a live path today is a
property of one machine at one minute and is not the argument.

Multiple HEREDOC writes to the same path are COMPOSED, not overwritten: `>`
truncates, `>>` appends. Treating `>>` as `>` let an appended footnote hide a
malformed verdict, turning a BLOCK into an ALLOW.

Only heredoc redirects are modelled. Any other write to the posted path — a
`printf`/`echo`/`cat file` redirect, a `tee`, `cat <<'EOF' > f`, or the common
`jq -Rs '{body: .}' x.md > payload.json` feeding `--input payload.json` — yields
a body the hook cannot derive. Rather than fall back to disk (which reinstates
the stale-file fail-open) it HARD BLOCKS, naming the write. A redirect appearing
inside a heredoc *body* is payload text, not a command, and does not trigger it.

If the body still cannot be read — stdin (`--input -`), a shell variable
that never entered the environment, or a missing file — the hook now BLOCKS
rather than warning. That branch was an advisory, and advisories decay
(`feedback_generic_prompt_hook_advisory_decay`); this one said nothing across
five PRs and nine uncountable verdicts. The diagnostic names the remedy:
write the body to a file and pass a literal `--body-file` path.

Scope boundary: this hook gates comment *creation*, never comment *edits*
========================================================================

`is_comment_command` matches `gh pr comment` and `gh api ... issues/<N>/comments`
with a write marker. The load-bearing discriminator for the REST arm is the
**URL shape** — `issues/\\d+/comments` — and NOT the HTTP method: `-X PATCH` at a
create URL still matches, while `-X POST` at `issues/comments/<comment_id>` (the
edit endpoint) does not. Editing an existing comment therefore never reaches
these gates.

**That is a deliberate scope choice, and it is load-bearing.** Retraction is
currently expressible only by breaking a comment on purpose. `RequestOrReplied`
has no value meaning "I withdraw this", and `validate_pr_review`'s reviewer set
is monotonic — a later comment saying "I withdraw my approval" subtracts nothing
(main#940 defect 1). So on 2026-07-10 a reviewer holding a stale `Approved` on
`noorinalabs-data-acquisition` #359 retracted it by editing his own comment and
mangling its trailer field names (`Requestor (retracted):`), which makes
`_extract_charter_field` return None and drops the approval from the count.

Gate 1 blocks precisely that shape: `Requestor` and `Requestee` present with no
readable `RequestOrReplied`. It does not fire today only because the retraction
was a PATCH edit, and edits are out of scope.

**Do not widen this hook to comment edits without first giving reviewers a
supported way to retract** — otherwise the gate forbids the only mechanism they
have for changing their mind, in the name of parseability.

    A gate that enforces a vocabulary must first contain a word for every
    thing reviewers need to say.

The right repair is `latest-verdict-wins` in the counting hook, with a
first-class `RequestOrReplied: Retracted` value — one vocabulary entry, one
branch in the counter, comment stays parseable, audit trail stays honest, and
it does not depend on comment ordering (main#940 defect 3 is that the hook has
no concept of ordering). Proposed there, not implemented here.

`OutOfScopeForEditsTests` pins this boundary so a future maintainer widening the
URL regex sees the retraction case go red rather than reading it in a docstring.

Semantic realignment (closes #386)
==================================

Pre-#386 the swap heuristic checked `Requestee.lastname == branch-author.lastname`,
which encoded the pre-#244 reading of the Direction table (Requestor=PR-author,
Requestee=reviewer). Post-#244, the charter inverts the role bindings on
verdict comments: Requestor IS the reviewer (because the reviewer is the
comment author) and Requestee IS the PR author. The post-#244 swap-detection
condition is therefore `Requestor.lastname == branch-author.lastname` — a
verdict whose Requestor matches the branch author indicates the PR author
is being named as the reviewer (the actual swap).

The path-2 narrowing from #378 (verdict-only scope) is preserved unchanged;
this hook only swaps which field is compared inside that scope.

Identity comparison — surname is not a person (closes #1172)
============================================================

The swap condition above was implemented as a comparison of SURNAMES, and the
roster contains distinct people who share one. On `L.Ferreira/1151-…` (author
Lucas Ferreira) a verdict correctly authored by **Santiago Ferreira** put
`Ferreira` on both sides of the test and was BLOCKED as a swap — on the
`gh pr comment` path AND on the REST comment-create arm from #932, so there was
no observable-body workaround and the verdict simply could not be posted.
Correct reviewer behaviour was indistinguishable from the thing the gate exists
to catch.

The branch prefix `{FirstInitial}.{LastName}` already carries more signal than
the surname, so the comparison is now first-initial + lastname, via the shared
`charter_trailer.is_branch_author` — the same module that already owns the
trailer convention, so this hook and `validate_pr_review` cannot drift on who a
person is. `validate_pr_review` fixed the sibling defect for its reviewer-dedup
key in #164 (key on the full name); this is that principle applied to the one
comparison where the full name is not available on both sides.

The check is NOT widened or disabled: a genuinely swapped verdict — the PR
author naming themselves as `Requestor` — still blocks, because their initial
and surname both match the branch. Gutting the heuristic would trade a false
positive for a false negative in a gate, and `validate_pr_review` counts a
swapped verdict wrong. When an initial is underivable on either side the
comparison falls back to surname-only, i.e. to the stricter pre-#1172 answer.

Exit codes:
  0 — allow (not a comment command, not a review comment, fields correct,
       or RequestOrReplied is not Approved/ChangesRequested)
  2 — block (Requestor IS the branch author on an Approved /
       ChangesRequested verdict — fields are swapped; OR the comment is a
       charter review comment the counting hook cannot parse — #932)
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
from _hook_main import run_blocking

# The charter trailer convention has ONE definition, shared with
# `validate_pr_review` (#932/#934). Both hooks scope through these functions, so
# a second, drifting copy of the rule is impossible rather than merely tested.
from _repo_flag_parse import extract_repo
from annunaki_log import log_pretooluse_block
from charter_trailer import (
    branch_author_first_initial,
    extract_branch_author_lastname,
    extract_charter_field,
    is_branch_author,
    name_lastname,
    strip_code_regions,
)

CHARTER_FIELD = "RequestOrReplied"
CHARTER_REF = ".claude/team/charter/pull-requests/reviews.md:9"

# Markers that turn a `gh api .../issues/<N>/comments` call into a *creation*.
# A bare GET (e.g. `--jq '.[].body'`) reads comments and must not be gated.
_REST_WRITE_MARKERS = (
    r"-X\s+POST",
    r"--method\s+POST",
    r"--input\b",
    r"--raw-field\b",
    r"--field\b",
    r"(?<!\w)-f\b",
    r"(?<!\w)-F\b",
)


def _split_segments(command: str) -> list[str]:
    """Split a command into segments that may each begin an invocation.

    NEWLINE is a separator (#934). It was not, and `cd /repo\\ngh pr comment ...`
    — the single most common shape in the harness transcripts — never reached
    the matcher, so 43 of 191 real comment-creating invocations were invisible
    to this hook. That hole was found by replaying the harvested corpus, not by
    enumerating shapes: see `HarnessInvocationCorpusTests`.
    """
    segments = []
    for segment in re.split(r"\s*(?:&&|\|\||\||;|\n)\s*", command):
        stripped = segment.lstrip()
        # Command substitution EXECUTES: `URL=$(gh api -X POST ...)` posts a
        # comment. A quoted assignment (`CMD="gh api ..."`) does not — it makes
        # a string — so only `$(` is unwrapped, never `"`. This must run BEFORE
        # the env-prefix loop, whose `\S*` would otherwise swallow `URL=$(gh `
        # whole and leave a segment starting at `api`. The env-prefix pattern
        # therefore also refuses to match an assignment opening a substitution.
        stripped = re.sub(r"^(?:[A-Za-z_][A-Za-z0-9_]*=)?\$\(\s*", "", stripped)
        while re.match(r"[A-Za-z_][A-Za-z0-9_]*=(?!\$\()\S*\s+", stripped):
            stripped = re.sub(r"^[A-Za-z_][A-Za-z0-9_]*=(?!\$\()\S*\s+", "", stripped)
        segments.append(stripped)
    return segments


def _is_rest_comment_create(segment: str) -> bool:
    """True for `gh api ... issues/<N>/comments` invocations that POST a body."""
    if not re.match(r"gh\s+api\b", segment):
        return False
    if not re.search(r"issues/\d+/comments\b", segment):
        return False
    return any(re.search(marker, segment) for marker in _REST_WRITE_MARKERS)


def is_comment_command(command: str) -> bool:
    """Check if the command posts a PR comment, via `gh pr comment` or REST.

    The REST arm closes the #932 evasion: `gh pr comment` goes through GraphQL,
    so a rate-limited reviewer falls back to `gh api -X POST` and the format
    gate never fires.
    """
    for segment in _split_segments(command):
        if re.match(r"gh\s+pr\s+comment\b", segment):
            return True
        if _is_rest_comment_create(segment):
            return True
    return False


def extract_pr_number(command: str) -> str | None:
    """Extract PR number from a `gh pr comment` or REST comment-create command."""
    match = re.search(r"\bgh\s+pr\s+comment\s+(\d+)", command)
    if match:
        return match.group(1)
    match = re.search(r"/pull/(\d+)", command)
    if match:
        return match.group(1)
    match = re.search(r"issues/(\d+)/comments\b", command)
    if match:
        return match.group(1)
    return None


# A path as written on a command line: single-quoted, double-quoted, or bare.
# The quoted alternatives come first so a quoted path containing a space is not
# truncated at the space by the bare `\S+` branch (#934 review, Wanjiku Mwangi).
_PATH_TOKEN = r"'[^']*'|\"[^\"]*\"|\S+"


def _resolve_body_path(path: str) -> str:
    """Normalize a path as written on the command line.

    Production invocations quote their paths and interpolate the environment:
    `-F body=@"$CLAUDE_JOB_DIR/tmp/x.md"`. Stripping quotes on one branch and
    not the other left three fail-open holes (#934 review). One resolver, used
    everywhere a path is read.

    Environment variables resolve because the hook process inherits the
    environment of the shell that is about to run the command. A *shell*
    variable (`--input "$J"`) does not, by construction — it never entered the
    environment. Such a path stays unresolved, the read fails, and `check()`
    blocks rather than allowing an unvalidated verdict through.
    """
    return os.path.expandvars(os.path.expanduser(path.strip("'\"")))


def _decode_body(raw: str) -> str | None:
    """Interpret a raw body payload.

    `--input x.json` carries a JSON object whose `body` key is the comment.
    `-F body=@x.md` carries the raw markdown. Distinguish by leading brace.
    """
    if raw.lstrip().startswith("{"):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return raw
        if isinstance(data, dict):
            value = data.get("body")
            return value if isinstance(value, str) else None
    return raw


def _read_body_file(path: str) -> str | None:
    """Read a comment body from disk."""
    try:
        raw = Path(_resolve_body_path(path)).read_text()
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    return _decode_body(raw)


# A heredoc redirected into a file: `cat > path <<'EOF' … EOF`, `cat >> p <<EOF`,
# `<<-EOF`. The delimiter is backreferenced so the body ends at its own terminator.
# `op` distinguishes truncate (`>`) from append (`>>`) — see `_heredoc_written_body`.
_HEREDOC_WRITE_RE = re.compile(
    r"(?P<op>>{1,2})\s*(?P<target>'[^']*'|\"[^\"]*\"|\S+)"
    r"\s*<<-?\s*(?P<quote>['\"]?)(?P<delim>[A-Za-z_][A-Za-z0-9_]*)(?P=quote)[ \t]*\n"
    r"(?P<body>.*?)"
    r"\n(?P=delim)[ \t]*(?:\n|$)",
    re.DOTALL,
)


# Any redirect (`> p`, `>> p`) and any `tee [-a] p`. Used to find writes to the
# posted path that `_HEREDOC_WRITE_RE` does NOT model — `printf … >> f`,
# `echo … >> f`, `cat note.md >> f`, `jq … > payload.json`, `cat <<'EOF' > f`
# (redirect after the heredoc), `tee f <<'EOF'`. See `_unmodelled_write`.
_REDIRECT_WRITE_RE = re.compile(r">>?\s*('[^']*'|\"[^\"]*\"|\S+)")
_TEE_WRITE_RE = re.compile(r"\btee\s+(?:-a\s+)?('[^']*'|\"[^\"]*\"|\S+)")


class _Unreconstructable:
    """The command writes this path, but the resulting body cannot be derived.

    Distinct from `None`, which means "no heredoc writes this path" and licenses
    falling back to disk. This value means the hook KNOWS it cannot know, and
    `check()` must hard-block (`feedback_safety_direction_over_ux_friction`).
    """

    __slots__ = ()


UNRECONSTRUCTABLE = _Unreconstructable()


def _read_raw(resolved_path: str) -> str | None:
    """Read a resolved path as text, without interpreting it as a body."""
    try:
        return Path(resolved_path).read_text()
    except (OSError, UnicodeDecodeError, ValueError):
        return None


def _heredoc_written_body(command: str, path: str) -> str | _Unreconstructable | None:
    """Return the body the heredocs in THIS command leave at `path`.

    A PreToolUse hook runs *before* the command, so for the write-then-post
    shape — `cat > v.md <<'EOF' … EOF; gh pr comment N --body-file v.md` — the
    file does not exist yet. The body is nonetheless fully observable: it is
    sitting in the command string.

    This takes precedence over reading `path` from disk. **The ordering is
    correct by construction, not by frequency**: if any file already sits at
    `path`, reading it validates a body the command is about to overwrite, and
    the comment that actually gets posted is the heredoc's. The hook would
    approve one comment while the author posts another. One stale file is
    sufficient for that; a census of how often it happens today is a property
    of one machine at one minute and must not be the argument.

    **Heredoc** writes are composed in order (#934 review, Wanjiku Mwangi):

      * `>`  truncates — it discards everything written before it.
      * `>>` appends — it must be concatenated onto what is already there.

    Any write to the path that is NOT a heredoc redirect — `printf … >> f`,
    `tee f <<'EOF'`, `cat <<'EOF' > f`, `jq … > payload.json` — is a body the
    hook cannot derive, and `_unmodelled_write` makes it a hard block. An earlier
    docstring here claimed writes were "composed in order, following the shell
    rather than a summary of it." Only one shape was. Saying so out loud, in the
    file whose subject is unverified claims, is how it survived a round of review
    (#934, Santiago Ferreira).

    The previous implementation assigned on every match, so `>>` behaved like
    `>`. Appending an innocuous footnote to a malformed verdict made the hook
    read only the footnote, converting a BLOCK into an ALLOW — a fail-open in
    the hook whose subject is closing fail-opens.

    When the first write to `path` is an append, the base is whatever is on
    disk. If that base cannot be established — the path is unexpanded, or it
    exists and cannot be read — the body is genuinely underivable and this
    returns `UNRECONSTRUCTABLE` so `check()` hard-blocks. A `>>` onto a path
    that does not exist is not ambiguous: the shell creates it, so the base is
    empty.

    Paths are compared after `_resolve_body_path`, so an unexported shell
    variable (`$T/x.md`) matches itself on both sides and resolves even though
    neither side can be expanded.
    """
    want = _resolve_body_path(path)

    if _unmodelled_write(command, want) is not None:
        return UNRECONSTRUCTABLE

    body: str | None = None

    for match in _HEREDOC_WRITE_RE.finditer(command):
        if _resolve_body_path(match.group("target")) != want:
            continue
        # `cat > f <<'EOF'\nA\nEOF` writes "A\n": every heredoc line is
        # newline-terminated, the last one included. The capture stops before
        # that newline, so restore it — otherwise the recovered body differs by
        # one byte from the file the command is about to write.
        chunk = match.group("body") + "\n"

        if match.group("op") == ">":
            body = chunk
            continue

        if body is None:
            base = _append_base(want)
            if base is None:
                return UNRECONSTRUCTABLE
            body = base
        body += chunk

    return body


def _unmodelled_write(command: str, want: str) -> str | None:
    """Return a write to `want` that the composer does not model, if any.

    `_HEREDOC_WRITE_RE` models exactly one shape: a redirect immediately followed
    by a heredoc. Every other way of writing the posted path is invisible to the
    composer, and `_body_for_path` would then fall back to reading disk —
    reinstating the very stale-file fail-open that heredoc precedence exists to
    close (#934 review, Santiago Ferreira). All of these were ALLOW at `2743bbf`
    with a conforming file on disk and an uncountable body actually posted:

        printf '\\n---\\nPS\\n' >> f     echo … >> f        cat note.md >> f
        cat <<'EOF' > f  (#943)       tee f <<'EOF'      jq … > payload.json

    The body is genuinely underivable in each — the hook cannot run `jq`. So it
    hard-blocks rather than guessing, reusing `UNRECONSTRUCTABLE`.

    **Redirects inside a heredoc *body* are not writes.** A verdict comment whose
    prose quotes `cat > verdict.md` would otherwise hard-block itself: the text
    is a payload, not a command. The naive scan over the whole command string
    fires on it. Skipping any match inside a heredoc body span is what makes this
    guard safe to apply to comments about shell commands — which, in this repo,
    is most of them.

    Counted over the 121-row harvested corpus: **6 rows** carry such a write to
    their own posted path, mostly `jq -Rs '{body: .}' x.md > payload.json` feeding
    `--input payload.json`. A stale `payload.json` gets validated while the
    command overwrites it. That count is context, not the argument: one stale
    file is sufficient, exactly as for disk-first ordering.
    """
    heredoc_bodies = [m.span("body") for m in _HEREDOC_WRITE_RE.finditer(command)]
    modelled = [
        m.span()
        for m in _HEREDOC_WRITE_RE.finditer(command)
        if _resolve_body_path(m.group("target")) == want
    ]

    def _is_payload_text(pos: int) -> bool:
        return any(start <= pos < end for start, end in heredoc_bodies)

    for match in _REDIRECT_WRITE_RE.finditer(command):
        if _is_payload_text(match.start()):
            continue
        if _resolve_body_path(match.group(1)) != want:
            continue
        if any(start <= match.start() < end for start, end in modelled):
            continue  # this redirect IS the modelled heredoc write
        return match.group(0)

    for match in _TEE_WRITE_RE.finditer(command):
        if _is_payload_text(match.start()):
            continue
        if _resolve_body_path(match.group(1)) == want:
            return match.group(0)

    return None


def _append_base(resolved_path: str) -> str | None:
    """What `>>` appends onto: existing file content, or "" if it does not exist.

    Returns None when the base cannot be established, which is a hard block
    rather than a guess.
    """
    if "$" in resolved_path:
        # An unexpanded shell variable: the hook cannot know which file this is,
        # so it cannot know what the append lands on top of.
        return None
    if not os.path.exists(resolved_path):
        return ""  # `>>` creates the file; the base is empty.
    return _read_raw(resolved_path)


def _body_for_path(command: str, path: str) -> str | None:
    """Resolve the body a command will post from `path` — heredoc first, then disk."""
    heredoc = _heredoc_written_body(command, path)
    if isinstance(heredoc, _Unreconstructable):
        return None  # `check()` blocks on an unreadable body.
    if heredoc is not None:
        return _decode_body(heredoc)
    return _read_body_file(path)


def extract_rest_comment_body(command: str) -> str | None:
    """Extract the comment body from a REST `gh api` comment-create command.

    Covers `--input <path>`, `-f/--field body=...`, and `-F/--raw-field
    body=@<path>`. Returns None for `--input -` (body arrives on stdin, which
    a PreToolUse hook cannot observe).
    """
    input_match = re.search(r"--input\s+(" + _PATH_TOKEN + r")", command)
    if input_match:
        path = input_match.group(1)
        if path.strip("'\"") != "-":
            return _body_for_path(command, path)

    field_match = re.search(
        r"(?:--raw-field|--field|-f|-F)\s+body=(?:'((?:[^'\\]|\\.)*)'"
        r"|\"((?:[^\"\\]|\\.)*)\"|(\S+))",
        command,
        re.DOTALL,
    )
    if field_match:
        value = next(g for g in field_match.groups() if g is not None)
        if value.startswith("@"):
            return _body_for_path(command, value[1:])
        return value

    return None


def extract_comment_body(command: str) -> str | None:
    """Extract the comment body from the gh pr comment command.

    Handles heredoc format: --body "$(cat <<'EOF' ... EOF)"
    and simple quoted strings: --body '...' or --body "..."
    """
    # `--body-file <path>` is the charter-prescribed form (`agents.md:429`) and
    # by far the most common: 144 call sites under `.claude/`. It was unread
    # until #934, so every charter-conforming verdict fell through to the
    # unreadable-body branch and was allowed unvalidated.
    body_file_match = re.search(r"--body-file[=\s]+(" + _PATH_TOKEN + r")", command)
    if body_file_match:
        return _body_for_path(command, body_file_match.group(1))

    # Heredoc: capture everything between <<'EOF' (or <<EOF) and the closing EOF
    heredoc_match = re.search(
        r"<<'?EOF'?\s*\n(.*?)\nEOF",
        command,
        re.DOTALL,
    )
    if heredoc_match:
        return heredoc_match.group(1)

    # --body with single-quoted string
    sq_match = re.search(r"--body\s+'((?:[^'\\]|\\.)*)'", command, re.DOTALL)
    if sq_match:
        return sq_match.group(1)

    # --body with double-quoted string
    dq_match = re.search(r'--body\s+"((?:[^"\\]|\\.)*)"', command, re.DOTALL)
    if dq_match:
        return dq_match.group(1)

    return None


def get_branch_name(pr_number: str, repo: str | None = None) -> str | None:
    """Fetch the head branch name for a PR.

    When `repo` (a `<owner>/<name>` string parsed from the user's `gh pr comment
    --repo` flag) is supplied, it is forwarded as `--repo <repo>` so the gh
    invocation targets the SAME repo the user is commenting against. Without
    that pass-through, gh's default repo resolution is cwd-based and a
    cross-repo invocation (reviewer in repo A's cwd posting on repo B's PR)
    silently returns the wrong PR's branch — the #503 cross-repo false-block.
    """
    cmd = ["gh", "pr", "view", pr_number, "--json", "headRefName"]
    if repo:
        cmd.extend(["--repo", repo])
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        return data.get("headRefName", "")
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return None


# `extract_branch_author_lastname` is imported from `charter_trailer` (#1175) —
# do NOT reimplement it here. The local copy this replaces was slash-only, while
# `validate_pr_review`'s copy learned the dash separator in #179 and
# `branch_author_first_initial` (imported into this very module) accepted dash
# all along. On `A.Virtanen-1175-x` the local parser returned None first and
# short-circuited `check()` to allow-with-warning, so the Requestor/Requestee
# swap check never ran — two parsers over one `head_ref`, and the wrong one won.
# `test_validate_review_comment_format.py::SharedBranchAuthorParsingTests`
# asserts this module's binding IS `charter_trailer`'s.


# Verdict direction values from charter `pull-requests.md` § Comment-Based
# Reviews Direction table. These are the rows where the swap heuristic is
# sound (Requestee = PR-author).
#
# Tolerated form variants: validate_pr_review counts the literal
# "Changes Requested" (with space) per `feedback_pr_review_verdict_format`,
# while some templates and older fixtures use the camelCase "ChangesRequested".
# Both are accepted here. Comparison is case-insensitive on the canonical token
# match. The bare "Changes" prefix is NOT a verdict on its own — we require
# the full token (with or without internal space) to avoid false-narrowing.
_VERDICT_DIRECTIONS = frozenset(
    {
        "approved",
        "changesrequested",
        "changes requested",
    }
)


# main#1364 / main#1366: two OPTIONAL trailer fields that `trust_signals.py`
# reads, both meaningful ONLY on a ChangesRequested verdict:
#
#   Retracted:          the reviewer withdraws the must-fix raised in THIS
#                       comment (feeds `review_false_positives` — the only
#                       accountability term on the reviewing side).
#   OrchestratorCaused: this block stems from a dispatch/brief error rather
#                       than the author's work (feeds
#                       `Signals.orchestrator_caused_rework`, excluded from the
#                       rate bars).
#
# A hook cannot REQUIRE either one — nothing can tell it that a given comment
# is retracting something, or that a block was the orchestrator's fault. So
# these are validated **when present**, never demanded by their absence. The
# failure they close is narrow and real: a field placed on an Approved /
# Request / Reply comment is silently ignored by `parse_verdicts` (both are
# gated on ChangesRequested), so the author believes they recorded something
# and the counter never sees it.
#
# PRESENCE MUST BE DETECTED EXACTLY AS THE COUNTER DETECTS IT (main#1363 MF1).
# The first cut asked `extract_charter_field`, whose pattern is NOT
# line-anchored and which narrows to the trailer block, while
# `trust_signals._RETRACTION_RE` / `._ORCHESTRATOR_CAUSED_RE` are
# line-anchored (`^`, MULTILINE) over the whole code-stripped body. Three
# axes disagreed, two of them producing a BLOCK on a field nobody wrote:
#
#   1. anchoring — `TechDebt: adoption of Retracted: is tracked by #1364`
#      is a field to the hook and prose to the counter. #1364 makes this the
#      likely case, not a contrived one: the field is now a documented
#      obligation, so reviewers will write *about* it in trailers.
#   2. code fences — RESOLVED by main#1359/#1361: `charter_trailer
#      .strip_code_regions` now strips `~~~` blocks the same as the (now
#      deleted) private `trust_signals._strip_code_markup` did, so this
#      predicate uses the shared stripper directly (see
#      `_strip_code_for_field_scan` below) instead of mirroring it.
#   3. scope — trailer-block only vs whole body. STILL OPEN: `_CONDITIONAL_FIELD_RE`
#      below is still a hook-local mirror of `trust_signals._RETRACTION_RE` /
#      `._ORCHESTRATOR_CAUSED_RE`, because `charter_trailer.extract_charter_field`
#      narrows to the trailer block and this predicate deliberately does not
#      (main#1359 extracted the STRIPPER and the verdict-KIND vocabulary, not
#      this presence-detection pair — tracked separately, main#1371/#1372).
#
# The field-presence definitions below still mirror the counter's regexes
# (axis 1 + axis 3 remain open) and are pinned against it by
# `ConditionalFieldGrammarAgreementTests`, which drives both implementations
# over one corpus so a future divergence reds rather than silently
# false-blocks. Full consolidation of this remaining pair is main#1371/#1372.
_CONDITIONAL_VERDICT_FIELDS = ("Retracted", "OrchestratorCaused")

# Mirrors trust_signals._RETRACTION_RE / ._ORCHESTRATOR_CAUSED_RE.
_CONDITIONAL_FIELD_RE = {
    name: re.compile(rf"^\**{name}\**:\**\s*\S", re.MULTILINE)
    for name in _CONDITIONAL_VERDICT_FIELDS
}


# The code-stripping step for the conditional-field presence scan is the
# SAME function object as the shared stripper — a direct alias, not a
# wrapper, and not a local mirror (main#1359/#1361, hardened per SF1 below).
#
# Before main#1359 this name bound a private `re.sub`-based copy of
# `trust_signals._strip_code_markup` (kept apart from
# `charter_trailer.strip_code_regions` specifically because that one left
# `~~~` fences intact); now that the shared stripper handles `~~~` too,
# there is nothing left for a second copy to diverge on.
#
# main#1359 merge-gate review (Aino Virtanen, SF1): reverting this name to a
# local `def _strip_code_for_field_scan(text): return re.sub(...)` mirror
# left the ENTIRE suite green — `test_no_second_definition_anywhere` greps
# `^def _?{name}\(` against a fixed name set, so a copy bound under a
# DIFFERENT function name (this one) is invisible to it, and the only
# existing identity check (`test_both_hooks_share_one_function_object`)
# asserted the module-level `strip_code_regions` import binding, never this
# name. A plain assignment (mirroring `validate_pr_review._strip_code_regions
# = strip_code_regions`) closes that hole: any future `def
# _strip_code_for_field_scan(...)` here immediately fails
# `test_code_stripper_is_the_shared_function_object`
# (`test_validate_review_comment_format.py`), which asserts identity, not
# merely equal output, and — because a `def` also constitutes a
# reintroduced local implementation — no longer needs its own name added to
# the singularity sweep's fixed set to be caught.
_strip_code_for_field_scan = strip_code_regions


def _conditional_fields_present(body: str) -> list[str]:
    """Which conditional fields the COUNTER would see in *body*, in field order.

    Whole body, not the trailer block: `trust_signals.parse_verdicts` scans the
    entire comment, and the point of this predicate is to agree with it.
    """
    scan = _strip_code_for_field_scan(body)
    return [
        name for name in _CONDITIONAL_VERDICT_FIELDS if _CONDITIONAL_FIELD_RE[name].search(scan)
    ]


def _direction_is_changes_requested(body: str) -> bool:
    """True if the `RequestOrReplied:` value is specifically ChangesRequested.

    Narrower than :func:`_direction_is_verdict`, which also accepts Approved.
    Accepts the bare ``Changes`` spelling that `_VERDICT_DIRECTIONS`
    deliberately excludes, because `trust_signals.parse_verdicts` (via
    `charter_trailer.verdict_kind(..., include_bare_changes=True)`, main#1359)
    DOES count it as ChangesRequested — this predicate must agree with the
    consumer whose behaviour it is protecting, not with the sibling
    verdict-set.

    That makes **two** verdict-direction classifiers left in this file
    (`_VERDICT_DIRECTIONS` here and this function), disagreeing on bare
    ``Changes`` *by design* — `trust_signals`'s own former third copy was
    deleted in main#1359, which also added `charter_trailer.verdict_kind(...,
    include_bare_changes=...)` as the shared classifier these two migrate
    onto. Consolidating them is tracked as **main#1371**; it is not a change
    to make incidentally, because the divergence is intentional per-consumer
    and collapsing it wrongly would silently re-scope two hooks.
    """
    match = re.search(r"RequestOrReplied:\s*(.+)", body)
    if not match:
        return False
    raw = match.group(1).strip().strip("*").strip().lower()
    if not raw:
        return False
    parts = raw.split()
    if not parts:
        return False
    return re.sub(r"[^a-z0-9]", "", parts[0]) in {"changesrequested", "changes"}


def _direction_is_verdict(body: str) -> bool:
    """True if the comment body's `RequestOrReplied:` value is a verdict direction.

    Matches the value on the same line as the `RequestOrReplied:` label. The
    value is stripped of trailing markdown bolding / whitespace and lowercased
    before comparison against `_VERDICT_DIRECTIONS`. If no value is captured
    (label present but value empty), returns False (fail-out-of-scope —
    consistent with the path-2 stance of narrowing rather than blocking on
    ambiguous shapes).
    """
    match = re.search(r"RequestOrReplied:\s*(.+)", body)
    if not match:
        return False
    raw = match.group(1).strip()
    raw = raw.strip("*").strip()
    if not raw:
        return False
    # Take the leading verdict word(s). The value may be followed by additional
    # text on the same line in some custom shapes; we only look at what comes
    # before a newline (already handled by `.+` group consuming up to EOL).
    # Lowercase for case-insensitive match against the canonical set.
    canonical = raw.lower()
    # Direct match against the canonical set covers both "approved",
    # "changesrequested", and "changes requested" forms.
    if canonical in _VERDICT_DIRECTIONS:
        return True
    # Tolerate trailing-token noise: e.g. "Approved (post-merge)" should still
    # be treated as Approved. Split on whitespace and join the first 1-2 tokens
    # to attempt the camelCase / two-word verdict match.
    parts = canonical.split()
    if not parts:
        return False
    if parts[0] in _VERDICT_DIRECTIONS:
        return True
    if len(parts) >= 2 and " ".join(parts[:2]) in _VERDICT_DIRECTIONS:
        return True
    return False


def _unreadable_cause(command: str) -> str:
    """Name the specific reason a body could not be read.

    The generic three-cause list told an author "the file does not exist" about a
    command whose own first line creates it (#934 review, Wanjiku Mwangi). A gate
    that says something false about your command is a gate you learn to route
    around — and routing around the verdict gate is the mechanism of #932.
    """
    if re.search(r"--input\s+['\"]?-['\"]?(?:\s|$)", command):
        return (
            "Cause: the body arrives on stdin (`--input -`), which a PreToolUse "
            "hook cannot observe. Write the body to a file and pass its path."
        )

    path_match = re.search(
        r"(?:--body-file[=\s]+|--input\s+|body=@)(" + _PATH_TOKEN + r")", command
    )
    if path_match:
        raw = path_match.group(1)
        resolved = _resolve_body_path(raw.lstrip("@"))
        if isinstance(_heredoc_written_body(command, raw.lstrip("@")), _Unreconstructable):
            write = _unmodelled_write(command, resolved)
            if write is not None:
                return (
                    f"Cause: this command writes the body file with `{write.strip()}`, "
                    f"which the hook cannot reproduce (it will not run `jq`, `printf`, "
                    f"or `tee`). Whatever is on disk now is NOT what will be posted, so "
                    f"validating it would approve one comment while you post another.\n\n"
                    f"Write the body with a heredoc — `cat > <path> <<'EOF' … EOF` or "
                    f"`cat >> <path> <<'EOF' … EOF` — which the hook can read, or write "
                    f"it in a separate Bash call before the one that posts."
                )
            return (
                "Cause: this command APPENDS to the body file (`>>`) but the hook "
                "cannot establish what it appends onto — the path is unexpanded, or "
                "it exists and cannot be read. The posted comment would be the "
                "existing content plus your addition, which the hook cannot see, so "
                "it will not guess."
            )
        if "$" in resolved:
            unexpanded = re.findall(r"\$\{?(\w+)", resolved)
            names = ", ".join(f"`${name}`" for name in unexpanded) or "the variable"
            return (
                f"Cause: {names} is a SHELL variable, not an exported environment "
                f"variable, so the hook cannot expand `{raw}`. Only variables in the "
                f"environment resolve. Export it, or pass a literal path."
            )
        return (
            f"Cause: `{resolved}` does not exist and no heredoc in this command "
            f"writes it. (If the command *does* create the file, the hook reads "
            f"that heredoc directly — so this means the paths do not match.)"
        )

    return (
        "Cause: no readable body path was found on this command. Pass the body "
        "with `--body-file <path>`."
    )


def check(input_data: dict) -> dict | None:
    """Check review comment format. Returns result dict if blocking/warning, None if allowed."""
    tool_name = input_data.get("tool_name", "")
    if tool_name != "Bash":
        return None

    command = input_data.get("tool_input", {}).get("command", "")

    if not is_comment_command(command):
        return None

    body = extract_comment_body(command) or extract_rest_comment_body(command)
    if not body:
        # #934: this branch used to warn and allow. It was built for `--input -`
        # (body on stdin, genuinely unobservable) but in practice it swallowed
        # `--body-file`, quoted `@paths`, and every `$VAR` — all observable, and
        # simply unimplemented. The escape hatch for the one unreadable case had
        # become the exit door for the three most common readable ones.
        #
        # Now that those are read, a recognized comment-create command whose body
        # cannot be recovered is exactly the state with no clean auto-fix, so it
        # blocks (`feedback_safety_direction_over_ux_friction`). A stderr line
        # here would decay like any advisory: the one this replaces said nothing
        # across five PRs and nine uncountable verdicts.
        result = {
            "decision": "block",
            "reason": (
                "BLOCKED: this command posts a PR comment, but its body cannot be "
                "read, so the charter review format cannot be validated. An "
                "unvalidatable verdict may count as zero reviews without anyone "
                "noticing.\n\n"
                f"{_unreadable_cause(command)}\n\n"
                "Fix: write the body to a file and pass a literal path:\n"
                "    gh pr comment <PR#> --repo <owner/repo> --body-file <path>\n\n"
                f"Charter: {CHARTER_REF}"
            ),
        }
        log_pretooluse_block("validate_review_comment_format", command, result["reason"])
        return result

    # Scan a code-stripped copy so a comment that *documents* the charter
    # template inside a fenced block is not mistaken for a malformed verdict.
    scan = strip_code_regions(body)

    has_requestor = re.search(r"\*{0,2}Requestor:\*{0,2}\s*(.+)", scan)
    has_requestee = re.search(r"\*{0,2}Requestee:\*{0,2}\s*(.+)", scan)
    has_request_or_replied = re.search(rf"\*{{0,2}}{CHARTER_FIELD}:\*{{0,2}}", scan)

    if has_requestor and has_requestee and not has_request_or_replied:
        # #932 gate 1: the near-miss shape. This IS a charter review comment —
        # it names a Requestor and a Requestee — but it carries no field the
        # counting hook can read, so it would contribute zero reviews while
        # looking, to its author, like a posted verdict.
        wrong_field = re.search(r"^\s*\*{0,2}(\w+):\*{0,2}\s*\S", scan, re.MULTILINE)
        used = ""
        verdict_label = re.search(r"^\s*\*{0,2}Verdict:\*{0,2}", scan, re.MULTILINE)
        if verdict_label:
            used = (
                "\n\n`Verdict:` is NOT a charter field. No hook reads it. "
                "A comment using it counts as zero reviews."
            )
        elif wrong_field:
            used = f"\n\nFound `{wrong_field.group(1)}:` where `{CHARTER_FIELD}:` was expected."
        result = {
            "decision": "block",
            "reason": (
                f"BLOCKED: charter review comment is missing the `{CHARTER_FIELD}:` "
                f"field. `Requestor:` and `Requestee:` are present, so this is a "
                f"review comment — but `validate_pr_review` counts verdicts by "
                f"`{CHARTER_FIELD}:` and would count this one as NOTHING.{used}\n\n"
                f"Add a line reading exactly:\n"
                f"    {CHARTER_FIELD}: Request | Reply | Approved | ChangesRequested\n\n"
                f"Charter: {CHARTER_REF}"
            ),
        }
        log_pretooluse_block("validate_review_comment_format", command, result["reason"])
        return result

    if not (has_requestor and has_requestee and has_request_or_replied):
        # A charter-format review comment carries all three headers. Missing
        # any one of them means this is not the comment shape the hook
        # validates — return None (allow) and let downstream/operator
        # discipline cover non-conforming bodies.
        return None

    # #932 gate 2: all three fields are on the page, but the counting hook
    # scopes extraction to the text after the LAST sole `---` line. Ask it
    # directly rather than reimplementing the rule.
    unreadable = [
        field
        for field in ("Requestor", CHARTER_FIELD)
        if extract_charter_field(field, body) is None
    ]
    if unreadable:
        result = {
            "decision": "block",
            "reason": (
                f"BLOCKED: charter fields are present but sit OUTSIDE the trailer "
                f"block, so `validate_pr_review` cannot read them "
                f"({', '.join(unreadable)} parse as None) and this verdict would "
                f"count as zero reviews.\n\n"
                f"Field extraction is scoped to everything AFTER the LAST line that "
                f"is a sole `---`. Your body has a later `---` (a prose horizontal "
                f"rule), which moved the scope past your fields.\n\n"
                f"Fix: put the four charter fields in a trailer block at the very "
                f"END of the comment, after a final `---` line. Renaming the field "
                f"alone will NOT fix this.\n\n"
                f"Charter: {CHARTER_REF}"
            ),
        }
        log_pretooluse_block("validate_review_comment_format", command, result["reason"])
        return result

    # main#1364/#1366: validate the two conditional fields WHEN PRESENT. Both
    # are gated on ChangesRequested by `trust_signals.parse_verdicts`, so one
    # placed on any other direction is read by nobody — the author thinks they
    # recorded a retraction or an attribution and the counter never sees it.
    # This runs BEFORE the `_direction_is_verdict` early-return below,
    # deliberately: Request/Reply exit there, and Request/Reply is exactly one
    # of the misplacements worth catching.
    misplaced = _conditional_fields_present(body)
    if misplaced and not _direction_is_changes_requested(body):
        direction = extract_charter_field(CHARTER_FIELD, body) or "(unreadable)"
        result = {
            "decision": "block",
            "reason": (
                f"BLOCKED: `{'`, `'.join(misplaced)}:` "
                f"{'is' if len(misplaced) == 1 else 'are'} only meaningful on a "
                f"`ChangesRequested` verdict, but this comment's "
                f"`{CHARTER_FIELD}:` is `{direction}`.\n\n"
                "`trust_signals.parse_verdicts` gates both fields on "
                "ChangesRequested — there is no must-fix to retract, and no "
                "rework round to reattribute, unless THIS comment raised a "
                "block. As written the field is silently ignored: the trust "
                "signal it feeds will read zero and nothing will report that "
                "it was dropped.\n\n"
                "Fix: put the field on the `ChangesRequested` comment that "
                "raised the finding. To withdraw a must-fix raised in an "
                "EARLIER comment, amend that comment rather than marking a "
                "later one — cross-comment retraction is not implemented "
                "(see § Scope boundary above).\n\n"
                f"Charter: {CHARTER_REF}"
            ),
        }
        log_pretooluse_block("validate_review_comment_format", command, result["reason"])
        return result

    if not _direction_is_verdict(body):
        # Scope-narrowing per #378 / path 2: the Requestee == branch-author
        # swap heuristic is only sound for verdict directions (Approved /
        # ChangesRequested), where the charter Direction table binds
        # Requestee = PR-author. For Request / Reply (or unrecognized
        # directions) the role bindings invert or are unknown — we cannot
        # safely block on the swap signal. Allow through and let
        # operator/orchestrator discipline cover those surfaces.
        return None

    pr_number = extract_pr_number(command)
    if not pr_number:
        return {
            "decision": "allow",
            "systemMessage": (
                "WARNING: Could not extract PR number from comment command. "
                "Unable to validate Requestor/Requestee format."
            ),
        }

    # Forward the user's --repo flag to the internal gh pr view so the branch
    # we fetch is from the SAME repo the user is commenting against. Closes
    # the #503 cross-repo skew: reviewer in repo-A cwd posting on repo-B PR.
    repo = extract_repo(command)
    if not repo:
        # Same-repo path — gh's cwd-based default resolution is used. Emit a
        # stderr breadcrumb so a future cross-repo invocation that omits
        # --repo is discoverable in transcripts, and the brittle cwd-dependence
        # of the same-repo path is not silent.
        print(
            "validate_review_comment_format: --repo flag absent on gh pr comment; "
            "falling back to cwd-default repo resolution for internal gh pr view. "
            "Cross-repo invocations MUST pass --repo to avoid the #503 swap-block.",
            file=sys.stderr,
        )
    branch_name = get_branch_name(pr_number, repo=repo)
    if not branch_name:
        return {
            "decision": "allow",
            "systemMessage": (
                "WARNING: Could not fetch branch name for PR. "
                "Unable to validate Requestor/Requestee format."
            ),
        }

    branch_author = extract_branch_author_lastname(branch_name)
    if not branch_author:
        return {
            "decision": "allow",
            "systemMessage": (
                "WARNING: Could not extract author from branch name. "
                "Unable to validate Requestor/Requestee format."
            ),
        }

    # #934: the swap heuristic must read the Requestor the COUNTING hook reads —
    # the trailer-scoped, last-match-wins value — never the first `re.search` hit
    # over the whole body. `has_requestor` above answers only "is this a charter
    # review comment"; its captured group is prose-contaminated and using it made
    # this hook fail in both directions at once:
    #
    #   fail-closed: prose "…Requestor: Wanjiku Mwangi, Requestee: Khoury" ends in
    #                the PR author's surname, so a correct verdict was BLOCKED.
    #   fail-open:   a genuinely swapped trailer PASSED whenever some earlier prose
    #                match yielded a non-author surname first.
    #
    # Gate 2 above has already established that this field parses inside the
    # trailer, so the value is non-None here.
    requestor_value = extract_charter_field("Requestor", body)

    # #1172: compare the PERSON, not the surname. The roster holds distinct
    # people who share a lastname (Lucas Ferreira / Santiago Ferreira), and a
    # lastname-only test made Santiago's correct verdict on `L.Ferreira/...`
    # indistinguishable from Lucas reviewing himself — an unblockable false
    # positive, since there is no observable-body workaround. The branch prefix
    # already carries the first initial, so `is_branch_author` uses
    # initial + lastname and only falls back to lastname when an initial is
    # genuinely underivable. See `charter_trailer` § Person identity.
    branch_initial = branch_author_first_initial(branch_name)

    if is_branch_author(requestor_value or "", branch_author, branch_initial):
        display = f"{branch_initial.upper()}.{branch_author}" if branch_initial else branch_author
        result = {
            "decision": "block",
            "reason": (
                f"BLOCKED: Requestor/Requestee appears swapped. "
                f"Requestor should be the reviewer (who is doing the review). "
                f"Requestee should be the PR author (who is receiving the review). "
                f"The branch author is {display} — they should be the "
                f"Requestee, not the Requestor."
            ),
        }
        log_pretooluse_block("validate_review_comment_format", command, result["reason"])
        return result

    return None


# Name parsing now lives in `charter_trailer` alongside the trailer convention,
# so this hook and `validate_pr_review` cannot disagree about who a person is
# (#1172). The historical private name is kept as an alias for the existing test
# surface — do not reimplement it here.
_extract_lastname = name_lastname


def main() -> None:
    run_blocking(check, "validate_review_comment_format")


if __name__ == "__main__":
    main()
