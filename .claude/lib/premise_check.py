#!/usr/bin/env python3
r"""Scope-time premise-rot gate for /wave-scope (main#837).

The P6W16 retro found that two scoped issues reached *execution* on premises
that no longer held at origin HEAD: **#705** targeted ``wave_key_reset.py`` —
a file #804 had already deleted — and **#816**'s named root cause had been
inverted. ``/wave-scope`` reconciled labels-vs-meta-issue but never checked that
a scoped issue's named *file / path / symbol* still exists at the repo's origin
HEAD. This module is the deterministic check that closes that gap: it extends
``feedback_verify_diagnosis_before_delegating`` +
``feedback_spawn_brief_protocol`` from *spawn* time back to *scope* time.

Two-layer design (the pure core is the testable part; git I/O is injectable):

  * ``extract_path_candidates(text)`` — pure. Pulls path-like tokens out of an
    issue body (backtick code spans + a strict path regex over the full text),
    filtered by :func:`looks_like_path` so prose never produces a false STOP.
  * ``check_issue(issue, ref, path_checker, symbol_checker)`` — wires extraction
    to existence checks. The two checkers are injected (default: real git) so
    unit tests run with zero git, and the verdict logic is exercised in
    isolation.
  * ``git_path_status`` / ``git_symbol_status`` — the real checks:
    ``git -C <dir> cat-file -e <ref>:<path>`` for a path,
    ``git -C <dir> grep -q -e <symbol> <ref>`` for a symbol.

Verdict policy (deterministic):

  * a named path/symbol that the ref can read but does NOT contain -> ``MISSING``
    -> issue verdict ``STOP`` (premise rot — the headline #837 signal).
  * a ref or repo dir that cannot be read at all (child repo not cloned,
    origin not fetched, bad ref) -> ``UNVERIFIABLE`` -> verdict ``WARN``. This is
    deliberately NOT a STOP: a missing local checkout is an environment gap, not
    evidence the premise rotted — a false STOP there would block scope on
    tooling state, the opposite of the gate's purpose.
  * a ``.claude/``/``.github/``-rooted path that MISSES in one repo of an org
    pair (parent<->child) but resolves in the other -> ``CROSS_REPO`` ->
    verdict ``WARN`` (main#1047 da#427 child->parent; main#1138 wave-30
    extends this symmetrically to parent->child, e.g. a ``noorinalabs-main``
    issue naming a ``.github/workflows/`` file a Track-C story is hoisting
    FROM a child repo). On the parent->child direction ONLY, a bare
    (slash-free) filename also triggers this second chance (main#1138 MF1:
    the two issues class 1 was reported from, #1110/#1111, name the workflow
    by bare filename — ``ghcr-publish.yml`` — never the qualified
    ``.github/workflows/...`` path). Very often a legitimate cross-repo
    reference, worth a manual look rather than a hard block.
  * a relative fragment that misses at its literal location but is a real
    suffix of some tracked path elsewhere in the tree (a bare basename per
    main#1047 da#373, or a multi-segment fragment like
    ``lib/check_agent_liveness.py`` per main#1138's 4th FP class) ->
    ``EXISTS`` via the suffix fallback.
  * a path that MISSES but is matched by a ``.gitignore`` rule (main#1138:
    ``.claude/annunaki/errors.jsonl``) -> ``GITIGNORED`` -> verdict ``WARN``:
    git can never see a gitignored path tracked, by design, so that alone is
    not evidence of premise rot.
  * a path listed in the issue's own ``creates`` array (main#1138 class 2: an
    issue that PROPOSES to add a file names its own output, not an
    already-holding premise) -> ``CREATES``, never checked against git, never
    contributes to the verdict.
  * a path whose every occurrence in the body is *illustrative by position*
    (main#1484: a non-program operand on a fenced shell-transcript line, or a
    value inside a quoted string literal in a fenced code block) ->
    ``ILLUSTRATIVE``, likewise never checked and never part of the verdict —
    but always listed and counted in the report, because a candidate
    suppressed as illustration must not read like one that was never
    extracted.
  * everything present, or no concrete refs to check -> ``OK``.

Extraction also rejects three shapes that read as paths but never assert a
repo premise (main#1138): a filesystem-absolute token (``/tmp/.../*.md`` — no
``git cat-file`` target is ever absolute), a bare extension with nothing
before the dot (``.py``, ``.yaml``), and a doc-placeholder filename (``X.md``,
``foo.py``, ``example.py`` — the "insert your own name here" convention).

Two more extraction rules come from main#1484, both found live on the wave-31
scope run:

  * A literal ``\n``/``\t``/``\r`` written in a body (``'a.md\nb.md'``) is a
    token SEPARATOR. The backslash is not a path character and is not in
    ``_PATH_TOKEN_RE``'s class, so the old extractor ended the token at the
    ``\`` and began the next at the ``n``, inventing ``nb.md`` — a filename
    that has never existed at any ref in any repo, which made the resulting
    STOP unclearable by any of the gate's three documented remedies
    (re-point, re-scope, close).
  * Placeholder BY POSITION (the ``ILLUSTRATIVE`` status above), the
    positional twin of main#1138's placeholder-by-NAME rule. Suppression
    needs positive evidence — at least one illustrative occurrence — AND no
    premise-position occurrence anywhere in the body, where premise position
    is prose, a bare backtick span, a path on a non-transcript line inside a
    fence, or the program a command runs. An explicit ``paths`` entry always
    overrides it.

An issue may also declare explicit ``paths`` / ``symbols`` / ``creates``
arrays (deliberate named premises — or declared outputs — the orchestrator
wants asserted even if the body phrasing is too loose for auto-extraction); a
symbol may be scoped to a pathspec.

CLI:
  premise_check.py check --issues ISSUES.json [--ref origin/main]
                         [--repos-root DIR] [--warn-only] [--json]

  ISSUES.json is a JSON array; each element:
    {
      "ref": "main#705",            # human label for reporting (required)
      "repo": "noorinalabs-main",   # used to resolve repo_dir under repos-root
      "body": "... `wave_key_reset.py` ...",   # auto-extracted (optional)
      "paths": ["explicit/path.py"],           # optional explicit paths
      "symbols": [                              # optional explicit symbols
        {"name": "wave_key_reset", "pathspec": ".claude/lib/"}
      ],
      "creates": [".claude/lib/org_repos.py"],  # optional: this issue's own
                                                 # proposed output, exempt
                                                 # from existence checks
      "repo_dir": "/abs/path",      # optional; overrides repos-root resolution
      "git_ref": "origin/main"      # optional per-issue ref override
    }

Exit code: 1 if any issue verdict is STOP (unless ``--warn-only``), else 0.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from org_repos import ALL_REPOS, CHILD_REPOS, MAIN_REPO

# Repo root = two parents above .claude/lib/ (lib -> .claude -> root). Resolved
# from this file so the default repos-root is correct from any cwd or worktree.
_REPO_ROOT = Path(__file__).resolve().parents[2]

# Candidate existence states.
EXISTS = "exists"
MISSING = "missing"
UNVERIFIABLE = "unverifiable"
# A shared-root path (`.claude/`, `.github/`) that misses in one repo of an
# org pair but resolves in the other — very often a legitimate cross-repo
# reference (main#1047 da#427: child names a parent-owned org-wide config
# path; main#1138 wave-30: a `noorinalabs-main` issue names a
# `.github/workflows/` file a Track-C story is hoisting FROM a child repo,
# i.e. the parent side of the same reference). Treated as WARN, not STOP: the
# reference is real, but reading it against the wrong repo is worth a manual
# look, not a hard block.
CROSS_REPO = "cross_repo"
# A path that git can never see tracked because it is deliberately
# `.gitignore`d (main#1138 wave-30: `.claude/annunaki/errors.jsonl`) — cannot
# be confirmed present via `git cat-file`, by design, so a bare MISSING would
# read as premise rot on every single check forever. WARN, not STOP: the
# reference may well be legitimate, but git cannot verify it either way.
GITIGNORED = "gitignored"
# An issue's own declared *output* (its `creates` array — main#1138 class 2):
# a path this issue proposes to add, not a premise it asserts already holds.
# Never checked against git, never contributes to the verdict.
CREATES = "creates"
# A candidate that WAS extracted but is illustrative by position (main#1484):
# its only occurrences are a non-program operand on a fenced shell-transcript
# line, or a value inside a quoted string literal in a fenced code block.
# Never checked against git, never contributes to the verdict — but always
# reported and counted, because a token suppressed as illustration and a token
# that was never extracted at all must not read the same in the output.
ILLUSTRATIVE = "illustrative"

# Per-issue verdicts.
OK = "ok"
WARN = "warn"
STOP = "stop"

# File extensions that mark a bare (slash-less) token as a path rather than
# prose. Lower-cased; the token's suffix is compared case-insensitively.
_CODE_EXTENSIONS = frozenset(
    {
        "py",
        "pyi",
        "md",
        "json",
        "jsonl",
        "ndjson",
        "yaml",
        "yml",
        "toml",
        "ts",
        "tsx",
        "js",
        "jsx",
        "mjs",
        "cjs",
        "sh",
        "bash",
        "zsh",
        "cfg",
        "ini",
        "txt",
        "lock",
        "sql",
        "tf",
        "tfvars",
        "astro",
        "css",
        "scss",
        "html",
        "env",
        "mk",
        "rs",
        "go",
        "csv",
        "tsv",
    }
)

# A token that could be a path: only path-safe characters, no whitespace. The
# stricter looks_like_path() decides whether it actually is one.
#
# NOTE the backslash is deliberately NOT in this class — no repo-relative git
# path contains one. That also means a backslash acts as a token boundary, so
# a literal escape sequence written inside a quoted string in an issue body
# (`'a.md\nb.md'`) used to split into `a.md` and `nb.md`: the `\` ended the
# first token and the `n` began the next (main#1484 defect 1). Escape
# sequences are stripped to a separator BEFORE tokenizing — see
# _ESCAPE_SEQUENCE_RE.
_PATH_TOKEN_RE = re.compile(r"[\w./\-]+")

# A literal two-character escape sequence in an issue body — the text
# `\` + `n`, not a real newline. It is a token SEPARATOR: substituted with a
# single space so neither the escape letter glues onto the following name
# (`nb.md`) nor the two names merge into one (`a.mdb.md`). Restricted to the
# three whitespace escapes actually seen separating captured-output filenames
# (main#1484: `\n` observed live on main#1262; `\t`/`\r` share the shape).
# A backslash followed by anything else already tokenizes harmlessly.
_ESCAPE_SEQUENCE_RE = re.compile(r"\\[nrt]")

# Backtick code span: ``foo`` -> foo. Non-greedy, single line.
_BACKTICK_RE = re.compile(r"`([^`\n]+)`")

# Leading path components that are a positive signal a slash-containing token
# is a real repo path even without a recognized extension (main#1047: a slash
# alone is NOT evidence — "A/B", "recall/precision", "origin/main", "986/650"
# all contain "/" and are not paths). Covers this org's top-level source roots
# plus every repo name (a cross-repo mention like
# `noorinalabs-deploy/terraform/...` is a real path even mid-prose). The repo
# names come from org_repos.ALL_REPOS (main#1118 / audit G6, the org repo-list
# SSOT) rather than being hand-copied here.
_KNOWN_ROOT_COMPONENTS = frozenset(
    {
        "src",
        "docs",
        "doc",
        "tests",
        "test",
        ".claude",
        ".github",
        "data",
        "ontology",
        "scripts",
        "terraform",
        "alembic",
        "docker",
        "integration-tests",
    }
) | frozenset(ALL_REPOS)

# Root prefixes shared org-wide between the parent (`noorinalabs-main`) and
# every child repo — org-wide tooling config (`.claude/`) and CI workflow
# definitions (`.github/`, main#1138 wave-30: Track C hoists per-repo
# `.github/workflows/*.yml` into `noorinalabs-main`). A path under one of
# these that misses in one repo of an org pair but resolves in the other is
# the CROSS_REPO downgrade's trigger set, symmetric in both directions
# (child names a parent path: main#1047 da#427; parent names a child path:
# main#1138).
_CROSS_REPO_SHARED_PREFIXES = (".claude/", ".github/")

# Known git refs / ref prefixes: `origin/main`, `refs/heads/x`, `HEAD` are
# never file paths even though `origin/main` contains a slash (main#1047).
_GIT_REF_LITERALS = frozenset({"HEAD"})
_GIT_REF_PREFIXES = ("origin/", "refs/")

# Doc-placeholder filenames used purely for illustration across this org's own
# issues/docs (main#1138 wave-30 class: `X.md` is the exact stand-in main#1352
# used for "insert your body-file path here"; the rest are the generic
# prose convention). A token whose STEM (the part before the final dot,
# case-insensitively) is exactly one of these is never asserted as a real
# path, however plausible its extension looks. Deliberately narrow — a real
# short name like `gh.py` or `db.py` is untouched.
_PLACEHOLDER_STEMS = frozenset(
    {"foo", "bar", "baz", "example", "sample", "placeholder", "dummy", "lorem"}
)

# --- positional-placeholder classification (main#1484 defect 2) -------------
#
# #1138 excluded placeholders by NAME (`X.md`, `foo.py`). main#1484 is the
# same principle by POSITION: a path-shaped token that only ever appears as
# the *data* an example passes — a non-program operand on a fenced shell
# transcript line, or a value inside a quoted string literal in a fenced code
# block — is illustration, not a premise the issue asserts. Observed live:
# main#1285 STOPped on `b.txt`, the dummy operand of
# `mark-resolved --bogus b.txt` whose entire purpose is to demonstrate that an
# unknown flag gets eaten as a path.

# Opening/closing fence of a code block (``` or ~~~, >=3, optional info
# string). `^\s*` rather than CommonMark's `^\s{0,3}` because GitHub issue
# bodies routinely indent fences inside list items.
_FENCE_RE = re.compile(r"^\s*(?P<fence>`{3,}|~{3,})")

# A single-line quoted string literal. Only consulted INSIDE a fence — prose
# that quotes a filename ("the 'gone.py' helper") still asserts it.
_QUOTED_LITERAL_RE = re.compile(r"'[^'\n]*'|\"[^\"\n]*\"")

# An interactive shell prompt introducing a transcript line.
_PROMPT_RE = re.compile(r"^\s*[$%]\s+")

_WHITESPACE_TOKEN_RE = re.compile(r"\S+")

# A leading token that makes the NEXT token the script being run — a real file
# reference, never an operand (`python3 checksums_io.py ...`).
_INTERPRETER_RE = re.compile(r"(?:python|python3(?:\.\d+)?|bash|sh|zsh|node)")

# Occurrence classes for one path-shaped token at one position in a body.
#   PREMISE      — asserts the path: prose, a bare backtick span, a path on a
#                  non-command fenced line, or the program a command runs.
#   ILLUSTRATIVE — a fenced-transcript operand or a fenced string literal.
#   NEUTRAL      — an argument inside an INLINE multi-token code span: a
#                  command fragment quoted mid-sentence neither asserts the
#                  path nor demonstrates it as sample data.
# Suppression requires >=1 ILLUSTRATIVE and 0 PREMISE occurrences across the
# whole body: it needs positive evidence, never merely the absence of prose.
_POS_PREMISE = "premise"
_POS_ILLUSTRATIVE = "illustrative"
_POS_NEUTRAL = "neutral"


def _all_components_numeric(tok: str) -> bool:
    """True when every ``/``-separated component of ``tok`` is digits/commas.

    Catches counts written as a fraction, e.g. ``986/650`` (main#1047 wave-26:
    "650,986/650,986 rows") — never a path, whatever the extension heuristic
    below would otherwise decide (there is no extension to check anyway).
    """
    parts = tok.split("/")
    return all(part and re.fullmatch(r"[\d,]+", part) for part in parts)


def looks_like_path(token: str) -> bool:
    """True when ``token`` is plausibly a repo-relative file/dir path.

    Precision over recall: a false negative just means one fewer thing checked;
    a false positive turns prose into a spurious STOP. A slash is NOT itself
    evidence (main#1047: the wave-26 scope run flagged 12/12 issues as
    premise-rot purely because prose like ``A/B``, ``recall/precision``, or the
    git ref ``origin/main`` contains a ``/``). A token is accepted only when it
    is whitespace-free, path-character-only, not a bare git ref, not an
    all-numeric fraction, not an absolute filesystem path, not a doc
    placeholder, and EITHER:

      * it ends in a known code/doc extension AND has a non-empty stem before
        that extension (``foo.py``, ``bar/baz.md`` — but not a bare ``.py``
        with nothing before the dot), OR
      * it contains a ``/`` AND its leading component is a known repo-root
        directory (``src/``, ``docs/``, ``.claude/``, a child-repo name, …).

    A slash-containing token with neither signal (e.g. ``ism/kunya``,
    ``boundary/particle``) is prose, not a path. Every repo this gate checks
    resolves paths as ``git cat-file -e <ref>:<path>``, which is always
    repo-*relative* — a token starting with ``/`` is a filesystem-absolute
    path (main#1138 wave-30: an ephemeral ``/tmp/.../scratchpad/*.md`` quoted
    verbatim in an issue body) and can never be that kind of path, whatever
    extension it happens to carry.
    """
    tok = token.strip()
    if not tok or " " in tok or "\t" in tok:
        return False
    if "://" in tok:  # URL, not a path
        return False
    if not re.fullmatch(r"[\w./\-]+", tok):
        return False
    # A bare issue/anchor ref or a number is never a path.
    if tok.lstrip("#").isdigit():
        return False
    if tok == "/":
        return False
    # A filesystem-absolute path (main#1138: `/tmp/...`, `/var/...`) is never
    # a repo-relative git path, regardless of what extension it carries.
    if tok.startswith("/"):
        return False
    if tok in _GIT_REF_LITERALS or tok.startswith(_GIT_REF_PREFIXES):
        return False
    # Extension/stem/placeholder checks operate on the final path component
    # (basename) — NOT the raw token — so a leading dot-directory
    # (``.claude/lib/``) is never mistaken for a bare-extension token; only
    # `.claude` (no trailing `/`) IS the basename in that case, and it has no
    # dot to split on at all.
    basename = tok.rsplit("/", 1)[-1]
    stem, dot, ext_raw = basename.rpartition(".")
    ext = ext_raw.lower() if dot else ""
    # A bare extension with nothing before the dot (main#1138 class 3: a bare
    # `.py`/`.yaml` mentioned in prose) is never a path — reject regardless of
    # what follows.
    if dot and not stem:
        return False
    # A doc-placeholder filename (main#1138 wave-30 class): a whole-word
    # placeholder stem, or a single UPPERCASE-letter stem (`X.md`, `Y.py` —
    # the "insert your own name" convention this org's own docs use, e.g.
    # main#1352's `--body-file X.md`), reads as illustration, not a real
    # asserted path. Lowercase single-letter stems (`a.py`, `c.py`) are left
    # alone — this repo's own test fixtures use them as arbitrary real
    # filenames, and the placeholder convention is specifically uppercase.
    if stem and (stem.lower() in _PLACEHOLDER_STEMS or (len(stem) == 1 and stem.isupper())):
        return False
    if ext in _CODE_EXTENSIONS and stem:
        return True
    if "/" in tok and not _all_components_numeric(tok):
        first = tok.split("/", 1)[0]
        if first in _KNOWN_ROOT_COMPONENTS:
            return True
    return False


def normalize_path(token: str) -> str:
    """Strip decoration so a raw token becomes a git-addressable repo path.

    Removes a leading ``./``, surrounding quotes/backticks, trailing sentence
    punctuation, and a ``:line`` / ``#Lnn`` location suffix (``foo.py:42`` and
    ``foo.py#L42`` both address ``foo.py``).
    """
    tok = token.strip().lstrip("`'\"")
    # Drop a file:line / file#Lnn location suffix before trimming punctuation
    # (so the digits aren't mistaken for a path char and the colon is removed).
    tok = re.sub(r":\d+(-\d+)?$", "", tok)
    tok = re.sub(r"#L\d+$", "", tok)
    # Trailing decoration: backticks, quotes, sentence punctuation. NOT stripped
    # from the left, where a leading `.` is meaningful (`.claude/...`, `./a`).
    tok = tok.rstrip("`'\").,;:")
    if tok.startswith("./"):
        tok = tok[2:]
    return tok


def _within(start: int, end: int, regions: list[tuple[int, int]]) -> bool:
    """True when ``[start, end)`` lies wholly inside one of ``regions``."""
    return any(r0 <= start and end <= r1 for r0, r1 in regions)


def _enclosing(
    start: int, end: int, regions: list[tuple[int, int, str]]
) -> tuple[int, int, str] | None:
    """The first region wholly containing ``[start, end)``, or ``None``."""
    for region in regions:
        if region[0] <= start and end <= region[1]:
            return region
    return None


def _program_regions(
    fragment: str, offset: int, require_shell_shape: bool
) -> list[tuple[int, int]] | None:
    """Character regions of the *program* position(s) of one command fragment.

    The program a command runs is a real file reference; everything after it
    is an operand. Program position is the first whitespace token, plus the
    second when the first is an interpreter and the second is not a flag
    (``python3 checksums_io.py ...`` -> ``checksums_io.py`` is the script).

    ``require_shell_shape`` is set for a line inside a fence, where the line
    must actually look like a shell transcript (an interactive ``$``/``%``
    prompt, or a leading interpreter) before its operands may be called
    illustrative; ``None`` is returned when it does not, and the caller then
    treats the whole line as ordinary fenced content. It is unset for an
    inline code span, which the caller has already established is a
    multi-token command fragment.
    """
    prompt = _PROMPT_RE.match(fragment)
    base = prompt.end() if prompt else 0
    tokens = [
        (m.start() + offset + base, m.end() + offset + base, m.group(0))
        for m in _WHITESPACE_TOKEN_RE.finditer(fragment[base:])
    ]
    if not tokens:
        return None
    lead = tokens[0][2]
    is_interpreter = _INTERPRETER_RE.fullmatch(lead) is not None
    if require_shell_shape and prompt is None and not is_interpreter:
        return None
    regions = [(tokens[0][0], tokens[0][1])]
    if is_interpreter and len(tokens) > 1 and not tokens[1][2].startswith("-"):
        regions.append((tokens[1][0], tokens[1][1]))
    return regions


def _classify_occurrence(
    start: int,
    end: int,
    in_fence: bool,
    inline_spans: list[tuple[int, int, str]],
    quoted: list[tuple[int, int]],
    fenced_program: list[tuple[int, int]] | None,
) -> str:
    """Which occurrence class (:data:`_POS_PREMISE` etc.) a hit at
    ``[start, end)`` on one line belongs to."""
    if in_fence:
        if _within(start, end, quoted):
            return _POS_ILLUSTRATIVE
        if fenced_program is None:
            # Not a shell transcript line — a tree listing, a diff, an import,
            # a bare path line. Still a premise; a fence is not a suppression.
            return _POS_PREMISE
        return _POS_PREMISE if _within(start, end, fenced_program) else _POS_ILLUSTRATIVE
    span = _enclosing(start, end, inline_spans)
    if span is None:
        return _POS_PREMISE  # plain prose
    content = span[2]
    if not _WHITESPACE_TOKEN_RE.fullmatch(content.strip()):
        # A multi-token inline span is a command fragment quoted mid-sentence.
        program = _program_regions(content.strip(), span[0] + _leading_ws(content), False)
        if program is not None and _within(start, end, program):
            return _POS_PREMISE
        return _POS_NEUTRAL
    return _POS_PREMISE  # a bare `path/like/this.py` reference


def _leading_ws(text: str) -> int:
    return len(text) - len(text.lstrip())


def _line_occurrences(line: str, in_fence: bool) -> list[tuple[str, str]]:
    """``(normalized_candidate, occurrence_class)`` for one line."""
    if not line.strip():
        return []
    inline_spans = [(m.start(1), m.end(1), m.group(1)) for m in _BACKTICK_RE.finditer(line)]
    quoted = [(m.start(), m.end()) for m in _QUOTED_LITERAL_RE.finditer(line)] if in_fence else []
    fenced_program = _program_regions(line, 0, True) if in_fence else None

    out: list[tuple[str, str]] = []

    def _record(start: int, end: int, raw: str) -> None:
        norm = normalize_path(raw)
        if not looks_like_path(norm):
            return
        occurrence = _classify_occurrence(
            start, end, in_fence, inline_spans, quoted, fenced_program
        )
        if occurrence == _POS_ILLUSTRATIVE and "/" in norm:
            # The positional rule is conjunctive: position AND shape. A
            # QUALIFIED path is positive evidence in itself — the author typed
            # a repo location, not just a name — while a bare filename is the
            # shape placeholders and fixture names take (and the shape the
            # suffix fallback already treats leniently). So a slash-carrying
            # token keeps exactly its pre-main#1484 treatment, whatever
            # position it occupies: e.g. `.claude/annunaki/errors.jsonl` named
            # as an operand in a fenced pseudo-command still reaches the
            # checker and still earns its GITIGNORED -> WARN downgrade.
            occurrence = _POS_PREMISE
        out.append((norm, occurrence))

    # Backtick code spans first (preserving the original extraction order),
    # then the path-token regex over the whole line.
    for start, end, content in inline_spans:
        _record(start, end, content)
    for match in _PATH_TOKEN_RE.finditer(line):
        _record(match.start(), match.end(), match.group(0))
    return out


def scan_path_candidates(text: str) -> list[tuple[str, bool]]:
    """``(candidate, illustrative_only)`` pairs, de-duplicated, order-preserving.

    ``illustrative_only`` is True when the candidate has at least one
    illustrative occurrence (a fenced-transcript operand or a fenced string
    literal) and NO premise-position occurrence anywhere in ``text``
    (main#1484 defect 2). One prose mention, one bare backtick span, or one
    appearance as the program a transcript runs is enough to keep it checked.

    A literal ``\\n``/``\\t``/``\\r`` is substituted with a separator before
    tokenizing (main#1484 defect 1), so ``a.md\\nb.md`` yields ``a.md`` and
    ``b.md`` — never the invented ``nb.md``.
    """
    if not text:
        return []
    text = _ESCAPE_SEQUENCE_RE.sub(" ", text)

    order: list[str] = []
    classes: dict[str, set[str]] = {}
    in_fence = False
    fence_marker = ""
    for line in text.splitlines():
        fence = _FENCE_RE.match(line)
        if fence is not None:
            marker = fence.group("fence")[:3]
            if not in_fence:
                in_fence, fence_marker = True, marker
                continue
            if marker == fence_marker:
                in_fence, fence_marker = False, ""
                continue
        for value, occurrence in _line_occurrences(line, in_fence):
            if value not in classes:
                classes[value] = set()
                order.append(value)
            classes[value].add(occurrence)

    return [
        (
            value,
            _POS_ILLUSTRATIVE in classes[value] and _POS_PREMISE not in classes[value],
        )
        for value in order
    ]


def extract_path_candidates(text: str) -> list[str]:
    """Path-like tokens in ``text``, de-duplicated, order-preserving.

    Union of backtick code spans and a path-token regex over the full text,
    each normalized and filtered through :func:`looks_like_path`. Every
    candidate is returned, illustrative or not — :func:`scan_path_candidates`
    is the caller that also needs the positional classification.
    """
    return [value for value, _ in scan_path_candidates(text)]


# --- git I/O (the injectable, side-effecting layer) -------------------------


def _run_git(repo_dir: str, args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run ``git -C <repo_dir> <args>`` with an explicit arg list.

    Never a shell string and never ``shell=True`` — no shell means no
    word-splitting under zsh (main#688), the contract shared across the lib.
    """
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["git", "-C", repo_dir, *args],
        capture_output=True,
        text=True,
        check=False,
    )


def git_ref_exists(repo_dir: str, ref: str) -> bool:
    """True when ``ref`` resolves in the repo at ``repo_dir``."""
    if not Path(repo_dir).is_dir():
        return False
    proc = _run_git(repo_dir, ["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"])
    return proc.returncode == 0


def _suffix_resolves(repo_dir: str, ref: str, candidate: str) -> bool:
    """True when some tracked path at ``ref`` equals ``candidate`` or ends in
    ``/<candidate>``.

    Suffix fallback (main#1047 da#373 basename case, generalized by main#1138
    4th FP class): an issue naming a bare filename like ``composition.py``
    may not mean the repo root — the file can live at
    ``src/parse/composition.py``. main#1138 widened this from slash-free
    basenames to any relative fragment: a token like
    ``lib/check_agent_liveness.py`` misses at its literal (repo-root-relative)
    location but IS a real suffix of the tracked ``.claude/lib/
    check_agent_liveness.py`` — the original basename-only fallback never
    fired for it because the token was not slash-free. A candidate that
    matches no tracked path anywhere is still MISSING, never re-resolved by
    a coincidental partial match.
    """
    proc = _run_git(repo_dir, ["ls-tree", "-r", "--name-only", ref])
    if proc.returncode != 0:
        return False
    suffix = "/" + candidate
    return any(line == candidate or line.endswith(suffix) for line in proc.stdout.splitlines())


def git_path_is_ignored(repo_dir: str, path: str) -> bool:
    """True when ``path`` is matched by a ``.gitignore`` rule in ``repo_dir``.

    Checked against the *working tree's* current ``.gitignore`` (there is no
    "ignored at a historical ref" concept — ignore rules are a property of
    the tree, not of git history). ``git check-ignore`` exits 0 when the path
    is ignored, 1 when it is not, and 128 on certain error conditions (all
    folded into "not ignored" — this is a best-effort downgrade, never a
    reason to assert MISSING harder).
    """
    proc = _run_git(repo_dir, ["check-ignore", "-q", "--", path])
    return proc.returncode == 0


def git_path_status(repo_dir: str, ref: str, path: str) -> str:
    """Existence of ``path`` at ``ref`` via ``git cat-file -e``.

    Returns :data:`UNVERIFIABLE` when the repo dir or ref cannot be read (an
    environment gap, never treated as premise rot), otherwise :data:`EXISTS` /
    :data:`GITIGNORED` / :data:`MISSING`. A relative fragment that misses at
    its literal location gets one more chance via :func:`_suffix_resolves`
    before being declared MISSING (main#1047 da#373 / main#1138 suffix
    fallback). Failing that, a path deliberately excluded from tracking via
    ``.gitignore`` (main#1138: ``.claude/annunaki/errors.jsonl``) downgrades
    to :data:`GITIGNORED` rather than MISSING — git can never see it
    tracked, by design, so a bare MISSING there is not evidence of rot.
    """
    if not git_ref_exists(repo_dir, ref):
        return UNVERIFIABLE
    proc = _run_git(repo_dir, ["cat-file", "-e", f"{ref}:{path}"])
    if proc.returncode == 0:
        return EXISTS
    if _suffix_resolves(repo_dir, ref, path):
        return EXISTS
    if git_path_is_ignored(repo_dir, path):
        return GITIGNORED
    return MISSING


def git_symbol_status(repo_dir: str, ref: str, symbol: str, pathspec: str | None = None) -> str:
    """Presence of ``symbol`` at ``ref`` via ``git grep`` (optionally scoped).

    ``git grep`` exits 0 on a match, 1 on no match, and >1 on error. The error
    case (and an unreadable ref) degrades to :data:`UNVERIFIABLE`.
    """
    if not git_ref_exists(repo_dir, ref):
        return UNVERIFIABLE
    args = ["grep", "-I", "-q", "-F", "-e", symbol, ref]
    if pathspec:
        args += ["--", pathspec]
    proc = _run_git(repo_dir, args)
    if proc.returncode == 0:
        return EXISTS
    if proc.returncode == 1:
        return MISSING
    return UNVERIFIABLE


# --- verdict layer (pure given the injected checkers) -----------------------

# (repo_dir, ref, value) -> status
PathChecker = Callable[[str, str, str], str]
# (repo_dir, ref, symbol, pathspec) -> status
SymbolChecker = Callable[[str, str, str, "str | None"], str]


@dataclass(frozen=True)
class Premise:
    """One flattened named premise of an issue, before any existence check."""

    kind: str  # "path" | "symbol"
    value: str
    pathspec: str | None = None
    # main#1484: auto-extracted from the body in an illustrative position only.
    # Always False for an explicitly declared `paths` / `symbols` entry.
    illustrative: bool = False


@dataclass
class CandidateResult:
    kind: str  # "path" | "symbol"
    value: str
    # EXISTS | MISSING | UNVERIFIABLE | CROSS_REPO | GITIGNORED | CREATES |
    # ILLUSTRATIVE
    status: str
    pathspec: str | None = None
    note: str | None = None


@dataclass
class IssueResult:
    ref: str
    repo: str
    repo_dir: str
    git_ref: str
    verdict: str  # OK | WARN | STOP
    candidates: list[CandidateResult] = field(default_factory=list)

    @property
    def missing(self) -> list[CandidateResult]:
        return [c for c in self.candidates if c.status == MISSING]

    @property
    def unverifiable(self) -> list[CandidateResult]:
        return [c for c in self.candidates if c.status == UNVERIFIABLE]

    @property
    def cross_repo(self) -> list[CandidateResult]:
        return [c for c in self.candidates if c.status == CROSS_REPO]

    @property
    def gitignored(self) -> list[CandidateResult]:
        return [c for c in self.candidates if c.status == GITIGNORED]

    @property
    def illustrative(self) -> list[CandidateResult]:
        return [c for c in self.candidates if c.status == ILLUSTRATIVE]

    @property
    def checked(self) -> list[CandidateResult]:
        """Candidates that were actually asserted against the ref.

        Excludes the two statuses that route around the checker entirely —
        CREATES (the issue's own declared output) and ILLUSTRATIVE (a
        positional placeholder). This is the number that separates an OK
        reached by verifying real premises from an OK reached by checking
        nothing.
        """
        return [c for c in self.candidates if c.status not in (CREATES, ILLUSTRATIVE)]


def _verdict_for(candidates: list[CandidateResult]) -> str:
    if any(c.status == MISSING for c in candidates):
        return STOP
    if any(c.status in (UNVERIFIABLE, CROSS_REPO, GITIGNORED) for c in candidates):
        return WARN
    return OK


def resolve_repo_dir(issue: dict, repos_root: Path) -> str:
    """Filesystem dir for an issue's repo.

    Explicit ``repo_dir`` wins. Otherwise the parent org root *is*
    ``noorinalabs-main``; every child repo lives at ``<repos_root>/<repo>``.
    """
    explicit = issue.get("repo_dir")
    if explicit:
        return str(explicit)
    repo = issue.get("repo") or "noorinalabs-main"
    if repo == "noorinalabs-main":
        return str(repos_root)
    return str(repos_root / repo)


def collect_candidates(issue: dict) -> list[Premise]:
    """Flatten an issue's premises to :class:`Premise` records.

    Auto-extracted body paths + explicit ``paths`` (kind ``path``) and explicit
    ``symbols`` (kind ``symbol``). De-duplicated on ``(kind, value, pathspec)``.

    An explicitly declared ``paths`` entry is a deliberate assertion by the
    orchestrator, so it clears the illustrative flag the body scan may have
    set for the same value (main#1484): a positional heuristic never vetoes a
    declared premise.
    """
    premises: list[Premise] = []
    seen: set[tuple[str, str, str | None]] = set()
    declared = {normalize_path(str(p)) for p in issue.get("paths", []) or []}

    def _add(kind: str, value: str, pathspec: str | None, illustrative: bool = False) -> None:
        key = (kind, value, pathspec)
        if value and key not in seen:
            seen.add(key)
            premises.append(Premise(kind, value, pathspec, illustrative))

    for path, illustrative in scan_path_candidates(issue.get("body", "") or ""):
        _add("path", path, None, illustrative and path not in declared)
    for p in issue.get("paths", []) or []:
        _add("path", normalize_path(str(p)), None)
    for sym in issue.get("symbols", []) or []:
        if isinstance(sym, dict):
            _add("symbol", str(sym.get("name", "")), sym.get("pathspec"))
        else:
            _add("symbol", str(sym), None)
    return premises


def _cross_repo_downgrade(
    value: str,
    repo_name: str,
    repos_root: Path,
    git_ref: str,
    path_checker: PathChecker,
) -> tuple[str, str] | None:
    """Second-chance lookup for a MISSING shared-root path in the "other side"
    of the parent/child pair (main#1047 da#427, extended symmetrically by
    main#1138 wave-30). Returns ``(CROSS_REPO, note)`` on a hit, else ``None``.

    * child repo, path misses locally -> check the parent (`noorinalabs-main`).
    * parent repo (`noorinalabs-main`), path misses locally -> check every
      child repo in turn; the first hit wins.

    Fires for a path under one of ``_CROSS_REPO_SHARED_PREFIXES`` — a
    non-shared path missing in the wrong repo is not this class of reference
    — OR, on the parent->child direction only, for a bare (slash-free)
    filename (main#1138 MF1: the two issues class 1 was actually reported
    from, #1110 and #1111, name the workflow file by bare filename —
    ``ghcr-publish.yml``, ``structural-ontology.yml`` — never the qualified
    ``.github/workflows/...`` path, so the shared-prefix trigger alone never
    caught them). Restricted to the parent->child direction: a bare filename
    is a much weaker signal than a shared-root prefix, and widening it on the
    child->parent side too would risk downgrading a genuine child-repo STOP
    on the strength of an unrelated same-named file anywhere in the parent's
    `.claude/` tree — a risk the parent->child direction already accepts
    (the file genuinely needs to exist in some specific child, not just
    somewhere in a huge shared tree) but the reported defect does not
    require accepting on the other side.
    """
    shared_prefix = value.startswith(_CROSS_REPO_SHARED_PREFIXES)
    if repo_name != MAIN_REPO:
        if not shared_prefix:
            return None
        parent_status = path_checker(str(repos_root), git_ref, value)
        if parent_status == EXISTS:
            return (
                CROSS_REPO,
                f"resolves in parent repo {MAIN_REPO}, not child repo "
                f"{repo_name} — verify this is a deliberate cross-repo reference",
            )
        return None
    bare_filename = "/" not in value
    if not (shared_prefix or bare_filename):
        return None
    for child in CHILD_REPOS:
        child_status = path_checker(str(repos_root / child), git_ref, value)
        if child_status == EXISTS:
            return (
                CROSS_REPO,
                f"resolves in child repo {child}, not parent repo {MAIN_REPO} — "
                "verify this is a deliberate cross-repo reference",
            )
    return None


def check_issue(
    issue: dict,
    repos_root: Path,
    default_ref: str,
    path_checker: PathChecker = git_path_status,
    symbol_checker: SymbolChecker = git_symbol_status,
) -> IssueResult:
    """Verify every named premise of one scoped issue against its repo HEAD.

    A shared-root (`.claude/`, `.github/`) path that MISSES in one repo of an
    org pair gets one more check against the other side before being
    declared MISSING (main#1047 da#427, symmetric extension main#1138
    wave-30): a child-repo issue very often names a legitimate org-wide
    config path, and a parent-repo issue can equally name a per-repo
    workflow file a Track-C-shaped story is consolidating FROM a child. A
    hit on the other side downgrades that candidate to :data:`CROSS_REPO`
    (-> WARN), not a bare pass — the reference is real, but checking it
    against the wrong repo is still worth a manual look.

    An issue's own declared ``creates`` array (main#1138 class 2) exempts
    those exact paths from verification entirely — they are the issue's
    proposed output, not an asserted-to-already-exist premise, so a MISSING
    checker result for one is never even consulted.
    """
    repo_dir = resolve_repo_dir(issue, repos_root)
    git_ref = issue.get("git_ref") or default_ref
    repo_name = str(issue.get("repo") or MAIN_REPO)
    creates = {normalize_path(str(p)) for p in issue.get("creates", []) or []}
    candidates: list[CandidateResult] = []
    for premise in collect_candidates(issue):
        kind, value, pathspec = premise.kind, premise.value, premise.pathspec
        if kind == "path":
            if value in creates:
                candidates.append(CandidateResult(kind, value, CREATES, pathspec))
                continue
            if premise.illustrative:
                candidates.append(
                    CandidateResult(
                        kind,
                        value,
                        ILLUSTRATIVE,
                        pathspec,
                        "appears only as a fenced-transcript operand / fixture string "
                        "literal — illustration, not an asserted premise (main#1484)",
                    )
                )
                continue
            status = path_checker(repo_dir, git_ref, value)
            note: str | None = None
            if status == MISSING:
                downgrade = _cross_repo_downgrade(
                    value, repo_name, repos_root, git_ref, path_checker
                )
                if downgrade is not None:
                    status, note = downgrade
            candidates.append(CandidateResult(kind, value, status, pathspec, note))
        else:
            status = symbol_checker(repo_dir, git_ref, value, pathspec)
            candidates.append(CandidateResult(kind, value, status, pathspec))
    return IssueResult(
        ref=str(issue.get("ref", "?")),
        repo=repo_name,
        repo_dir=repo_dir,
        git_ref=git_ref,
        verdict=_verdict_for(candidates),
        candidates=candidates,
    )


def check_issues(
    issues: list[dict],
    repos_root: Path,
    default_ref: str,
    path_checker: PathChecker = git_path_status,
    symbol_checker: SymbolChecker = git_symbol_status,
) -> list[IssueResult]:
    return [check_issue(i, repos_root, default_ref, path_checker, symbol_checker) for i in issues]


# --- reporting + CLI --------------------------------------------------------

_STATUS_GLYPH = {
    EXISTS: "ok",
    MISSING: "MISSING",
    UNVERIFIABLE: "unverifiable",
    CROSS_REPO: "cross-repo (found in the other repo — see note)",
    GITIGNORED: "gitignored (never tracked by git — cannot verify)",
    CREATES: "declared creation (this issue's own output, not checked)",
    ILLUSTRATIVE: "illustrative (extracted, then NOT checked — see note)",
}


def render_report(results: list[IssueResult]) -> str:
    lines: list[str] = []
    stops = [r for r in results if r.verdict == STOP]
    warns = [r for r in results if r.verdict == WARN]

    for r in results:
        if r.verdict == OK and not r.candidates:
            lines.append(f"[ok]   {r.ref}: no concrete file/symbol refs to verify")
            continue
        tag = {OK: "ok", WARN: "WARN", STOP: "STOP"}[r.verdict]
        lines.append(f"[{tag}] {r.ref}  ({r.repo} @ {r.git_ref})")
        for c in r.candidates:
            scope = f" in {c.pathspec}" if c.pathspec else ""
            note = f" — {c.note}" if c.note else ""
            lines.append(f"    - {c.kind} `{c.value}`{scope}: {_STATUS_GLYPH[c.status]}{note}")

    lines.append("")
    if stops:
        lines.append(
            f"STOP: {len(stops)} issue(s) name a file/symbol absent at origin HEAD "
            "(premise rot). Re-scope, re-point, or close before /wave-kickoff:"
        )
        for r in stops:
            refs = ", ".join(f"{c.kind} {c.value}" for c in r.missing)
            lines.append(f"  - {r.ref}: {refs}")
    if warns:
        lines.append(
            f"WARN: {len(warns)} issue(s) could not be fully verified "
            "(repo not cloned / ref not fetched / unreadable, a cross-repo "
            "reference, or a gitignored path). Verify manually:"
        )
        for r in warns:
            refs = ", ".join(
                f"{c.kind} {c.value}" for c in r.unverifiable + r.cross_repo + r.gitignored
            )
            lines.append(f"  - {r.ref} ({r.repo_dir} @ {r.git_ref}): {refs}")

    # main#1484 acceptance bar: a candidate suppressed as illustrative must
    # never be silent — silence is exactly how it becomes indistinguishable
    # from a candidate that was never extracted at all.
    suppressed = [(r, c) for r in results for c in r.illustrative]
    if suppressed:
        issue_count = len({r.ref for r, _ in suppressed})
        lines.append(
            f"NOTE: {len(suppressed)} candidate(s) across {issue_count} issue(s) were "
            "extracted then NOT checked — illustrative by position (a fenced-transcript "
            "operand or a fixture string literal, main#1484). Confirm each really is "
            "illustration; declare it in the issue's `paths` array to force the check:"
        )
        for r, c in suppressed:
            lines.append(f"  - {r.ref}: {c.kind} {c.value}")

    if not stops and not warns:
        lines.append("All named files/symbols verified present at origin HEAD.")

    checked = sum(len(r.checked) for r in results)
    lines.append(
        f"Extraction tally: {checked} premise(s) checked across {len(results)} issue(s); "
        f"{sum(1 for r in results if not r.candidates)} issue(s) named none; "
        f"{len(suppressed)} suppressed as illustrative; "
        f"{sum(len([c for c in r.candidates if c.status == CREATES]) for r in results)} "
        "declared creation(s)."
    )
    return "\n".join(lines)


def _result_to_dict(r: IssueResult) -> dict:
    return {
        "ref": r.ref,
        "repo": r.repo,
        "repo_dir": r.repo_dir,
        "git_ref": r.git_ref,
        "verdict": r.verdict,
        "candidates": [
            {
                "kind": c.kind,
                "value": c.value,
                "status": c.status,
                "pathspec": c.pathspec,
                "note": c.note,
            }
            for c in r.candidates
        ],
    }


def _cmd_check(args: argparse.Namespace) -> int:
    issues = json.loads(Path(args.issues).read_text())
    if not isinstance(issues, list):
        print("ERROR: --issues must be a JSON array of issue objects", file=sys.stderr)
        return 2
    results = check_issues(issues, args.repos_root, args.ref)

    if args.json:
        print(json.dumps([_result_to_dict(r) for r in results], indent=2))
    else:
        print(render_report(results))

    has_stop = any(r.verdict == STOP for r in results)
    if has_stop and not args.warn_only:
        return 1
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser("check", help="verify scoped issues' named files/symbols")
    p_check.add_argument("--issues", required=True, help="path to the issues JSON array")
    p_check.add_argument(
        "--ref", default="origin/main", help="git ref to check against (default origin/main)"
    )
    p_check.add_argument(
        "--repos-root",
        type=Path,
        default=_REPO_ROOT,
        help="root dir holding the org repos (default: this repo's root)",
    )
    p_check.add_argument(
        "--warn-only",
        action="store_true",
        help="report STOPs but exit 0 (advisory mode)",
    )
    p_check.add_argument("--json", action="store_true", help="machine-readable output")
    p_check.set_defaults(func=_cmd_check)
    return parser


def main(argv: list[str]) -> int:
    args = _build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
