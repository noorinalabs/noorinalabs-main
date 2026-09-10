#!/usr/bin/env python3
"""Deterministic helpers for the /promotion-audit skill.

Every function in this module is a pure function: same inputs -> same
outputs. No clocks, no randomness, no transcript reads, no network.

The skill's SKILL.md drives these helpers in order. Tests live in
`.claude/skills/promotion-audit/tests/` and cover each helper plus a
smoke test on the current repo state.

Glossary
========
Memory
    A file under `~/.claude/projects/<proj>/memory/*.md` (the project's
    auto-memory area). Carries YAML frontmatter (schema in issue #152).

Section
    A level-2 heading (`## ...`) inside a charter file. Procedural
    sections are tagged with an HTML comment marker:
        ## Some procedural section <!-- promotion-target: skill -->
    Non-procedural sections MAY be tagged `<!-- promotion-target: none -->`
    for explicit opt-out. Untagged sections are treated as `none`.

Skill
    A subdirectory under `.claude/skills/{name}/` with `SKILL.md`. The
    SKILL.md may declare `promotion-target: hook` in its frontmatter to
    opt into hook-promotion audit.

Already-promoted
    A source (memory name or skill name) whose content has already been
    codified via the pipeline. Recognized by scanning charter/hooks.md
    for `Promotion provenance:` blocks (the format established by
    Hook 15 in PR #153, the worked example).
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import Any, Literal

# ---------------------------------------------------------------------------
# Frontmatter parsing (no PyYAML dependency — do it by hand for portability)
# ---------------------------------------------------------------------------

_FM_DELIM = "---"


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split a markdown doc into (frontmatter_dict, body).

    Returns ({}, text) if there is no frontmatter block. Parses a small
    subset of YAML: scalars, quoted strings, simple lists `['a', 'b']`,
    and nested one-level maps (indented two-space `key: value`).

    This is intentionally minimal — memory frontmatter schema is stable
    and well-defined in issue #152.
    """
    if not text.startswith(_FM_DELIM + "\n") and not text.startswith(_FM_DELIM + "\r\n"):
        return {}, text

    lines = text.splitlines(keepends=False)
    if not lines or lines[0].strip() != _FM_DELIM:
        return {}, text

    # Find the closing `---`
    close_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == _FM_DELIM:
            close_idx = i
            break
    if close_idx is None:
        return {}, text

    fm_lines = lines[1:close_idx]
    body = "\n".join(lines[close_idx + 1 :])

    return _parse_simple_yaml(fm_lines), body


def _parse_simple_yaml(lines: list[str]) -> dict[str, Any]:
    """Parse a minimal YAML subset sufficient for memory/skill frontmatter."""
    result: dict[str, Any] = {}
    current_map: dict[str, Any] | None = None

    for raw in lines:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue

        # Detect indentation — a two-space indent under a "key:" (no value)
        # means we are in a sub-map.
        stripped = raw.lstrip()
        indent = len(raw) - len(stripped)

        if indent >= 2 and current_map is not None:
            # Sub-map entry
            if ":" in stripped:
                k, _, v = stripped.partition(":")
                current_map[k.strip()] = _coerce_scalar(v.strip())
            continue

        # Top-level entry
        current_map = None
        if ":" not in stripped:
            continue
        k, _, v = stripped.partition(":")
        k = k.strip()
        v = v.strip()

        if not v:
            # Either a sub-map or an empty list placeholder.
            current_map = {}
            result[k] = current_map
            continue

        result[k] = _coerce_scalar(v)

    return result


_LIST_RE = re.compile(r"^\[(.*)\]$")


def _coerce_scalar(v: str) -> Any:
    """Turn a YAML scalar string into its Python value."""
    if not v:
        return ""
    # Quoted string
    if (v[0], v[-1]) in (('"', '"'), ("'", "'")):
        return v[1:-1]
    # Inline list
    m = _LIST_RE.match(v)
    if m:
        inner = m.group(1).strip()
        if not inner:
            return []
        parts = [p.strip() for p in inner.split(",")]
        return [_coerce_scalar(p) for p in parts]
    # Bool
    if v.lower() in ("true", "yes"):
        return True
    if v.lower() in ("false", "no"):
        return False
    # Int
    try:
        return int(v)
    except ValueError:
        return v


# ---------------------------------------------------------------------------
# Memory reading
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Memory:
    path: str
    name: str
    description: str
    type_: str
    promotion_target: Literal["charter", "skill", "hook", "none"]
    promotion_threshold: dict[str, int]
    referenced_in_retros: tuple[str, ...]
    status: Literal["active", "enforced-elsewhere", "superseded"]
    superseded_by: str
    supersedes: str
    requires_decision: bool
    body: str

    @property
    def filename(self) -> str:
        return os.path.basename(self.path)


def read_memory(path: str) -> Memory:
    """Parse a single memory file into a Memory record."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    fm, body = parse_frontmatter(text)

    thresh = fm.get("promotion_threshold")
    if not isinstance(thresh, dict):
        thresh = {}
    # Normalize threshold subkeys.
    thresh_norm = {
        "retro_citations": int(thresh.get("retro_citations", 3) or 3),
        "skill_invocations": int(thresh.get("skill_invocations", 5) or 5),
    }

    refs = fm.get("referenced_in_retros", ())
    if isinstance(refs, str):
        # Tolerate a single-string shape.
        refs = (refs,) if refs else ()
    else:
        refs = tuple(refs or ())

    status = fm.get("status", "active")
    if status not in ("active", "enforced-elsewhere", "superseded"):
        status = "active"

    pt = fm.get("promotion_target", "none")
    if pt not in ("charter", "skill", "hook", "none"):
        pt = "none"

    return Memory(
        path=path,
        name=str(fm.get("name", os.path.basename(path))),
        description=str(fm.get("description", "")),
        type_=str(fm.get("type", "project")),
        promotion_target=pt,  # type: ignore[arg-type]
        promotion_threshold=thresh_norm,
        referenced_in_retros=refs,
        status=status,  # type: ignore[arg-type]
        superseded_by=str(fm.get("superseded_by", "")),
        supersedes=str(fm.get("supersedes", "")),
        requires_decision=bool(fm.get("requires_decision", False)),
        body=body,
    )


def read_all_memories(memory_dir: str) -> list[Memory]:
    """Read every `*.md` memory except the `MEMORY.md` index and `session_handoff.md`.

    Sorted deterministically by filename.
    """
    results: list[Memory] = []
    if not os.path.isdir(memory_dir):
        return results
    for name in sorted(os.listdir(memory_dir)):
        if not name.endswith(".md"):
            continue
        if name == "MEMORY.md":
            continue
        if name == "session_handoff.md":
            # Auto-generated; never promoted.
            continue
        path = os.path.join(memory_dir, name)
        if os.path.isfile(path):
            results.append(read_memory(path))
    return results


# ---------------------------------------------------------------------------
# Charter section reading
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CharterSection:
    path: str
    heading: str
    # Marker value: "skill", "hook", "none", or "" if no marker.
    promotion_target: str
    body: str
    # Any `<!-- promoted-to: skills/{slug} -->` back-reference found.
    promoted_to: str = ""


_SECTION_MARKER_RE = re.compile(
    r"^##\s+(?P<heading>.+?)\s*<!--\s*promotion-target:\s*(?P<target>skill|hook|none)\s*-->\s*$",
    re.MULTILINE,
)
_PROMOTED_TO_RE = re.compile(r"<!--\s*promoted-to:\s*(?P<dest>[^\s]+)\s*-->")


def read_charter_sections(charter_path: str) -> list[CharterSection]:
    """Extract level-2 sections that carry a promotion-target marker."""
    if not os.path.isfile(charter_path):
        return []
    with open(charter_path, encoding="utf-8") as f:
        src = f.read()

    # Find all level-2 headings (whether tagged or not) so we can slice bodies.
    headings = list(re.finditer(r"^(## .+)$", src, re.MULTILINE))

    results: list[CharterSection] = []
    for i, m in enumerate(headings):
        line = m.group(1)
        tag = _SECTION_MARKER_RE.match(line)
        if not tag:
            continue
        start = m.end()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(src)
        body = src[start:end].strip()
        promoted = _PROMOTED_TO_RE.search(body)
        results.append(
            CharterSection(
                path=charter_path,
                heading=tag.group("heading").strip(),
                promotion_target=tag.group("target"),
                body=body,
                promoted_to=promoted.group("dest") if promoted else "",
            )
        )
    return results


def _charter_md_files(subdir: str) -> list[str]:
    """All `*.md` files under the charter dir, RECURSIVE and sorted.

    Recursion added by #963: the charter mega-files (agents / pull-requests /
    hooks) were re-shelved into per-concern section files under
    `charter/{agents,pull-requests,hooks}/`, with the old paths kept as thin
    forwarding indexes. A non-recursive `os.listdir` scan would silently see
    only the (marker-free) indexes and drop every re-shelved section — the
    same silent-empty failure class as #418.
    """
    found: list[str] = []
    for root, dirs, files in os.walk(subdir):
        dirs.sort()
        for name in sorted(files):
            if name.endswith(".md"):
                found.append(os.path.join(root, name))
    return found


def read_all_charter_sections(charter_parent: str) -> list[CharterSection]:
    """Scan charter.md + charter/**/*.md (recursive, #963) for marked sections.

    `charter_parent` is the directory **containing** the `charter/` subdir
    (typically `.claude/team`), NOT the `charter/` directory itself. Sibling
    of `find_already_promoted_in_charter` — same parameter semantics, same
    silent-empty failure mode if the caller passes the charter dir instead
    of its parent (issue #418).

    Sorted by (path, heading) for determinism.

    Raises:
        ValueError: if `charter_parent` is itself named `charter` — see #418.
    """
    if os.path.isdir(charter_parent) and (
        os.path.basename(os.path.normpath(charter_parent)) == "charter"
    ):
        raise ValueError(
            f"read_all_charter_sections({charter_parent!r}): "
            "argument is the charter directory itself — pass its parent "
            "(e.g. '.claude/team', not '.claude/team/charter'). "
            "See issue #418."
        )

    candidates: list[str] = []
    root_file = os.path.join(charter_parent, "charter.md")
    if os.path.isfile(root_file):
        candidates.append(root_file)

    subdir = os.path.join(charter_parent, "charter")
    if os.path.isdir(subdir):
        candidates.extend(_charter_md_files(subdir))

    results: list[CharterSection] = []
    for p in candidates:
        results.extend(read_charter_sections(p))

    results.sort(key=lambda s: (s.path, s.heading))
    return results


# ---------------------------------------------------------------------------
# Skill reading
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Skill:
    name: str
    path: str  # path to SKILL.md
    promotion_target: Literal["hook", "none"]
    description: str
    body: str


def read_all_skills(skills_dir: str) -> list[Skill]:
    """Discover skills in `.claude/skills/`. Sorted by name."""
    results: list[Skill] = []
    if not os.path.isdir(skills_dir):
        return results
    for name in sorted(os.listdir(skills_dir)):
        skill_md = os.path.join(skills_dir, name, "SKILL.md")
        if not os.path.isfile(skill_md):
            continue
        with open(skill_md, encoding="utf-8") as f:
            text = f.read()
        fm, body = parse_frontmatter(text)
        pt = fm.get("promotion_target", "none")
        if pt not in ("hook", "none"):
            pt = "none"
        results.append(
            Skill(
                name=name,
                path=skill_md,
                promotion_target=pt,  # type: ignore[arg-type]
                description=str(fm.get("description", "")),
                body=body,
            )
        )
    return results


# ---------------------------------------------------------------------------
# Signal counting
# ---------------------------------------------------------------------------


def _feedback_log_corpus(feedback_log_path: str) -> str:
    """Return the live feedback log plus any per-phase archives, concatenated.

    Closed-phase retro entries move byte-for-byte to
    `.claude/team/archive/feedback_log_*.md` at phase close (#964 / meta #960),
    so citation counts must scan live + archive together or historical
    citations silently vanish from the promotion pipeline. Archives are read
    in sorted-name order for determinism; a missing archive dir is fine
    (pre-archival layout).
    """
    parts: list[str] = []
    if os.path.isfile(feedback_log_path):
        with open(feedback_log_path, encoding="utf-8") as f:
            parts.append(f.read())
    archive_dir = os.path.join(os.path.dirname(feedback_log_path), "archive")
    if os.path.isdir(archive_dir):
        for name in sorted(os.listdir(archive_dir)):
            if name.startswith("feedback_log_") and name.endswith(".md"):
                with open(os.path.join(archive_dir, name), encoding="utf-8") as f:
                    parts.append(f.read())
    return "\n".join(parts)


def check_corpus_health(feedback_log_path: str) -> str | None:
    """Return `None` if the citation corpus can be read, else a reason it can't.

    `_feedback_log_corpus` treats a missing feedback log as a valid empty
    corpus (`""`), which every caller downstream of it — `count_retro_citations`,
    `count_section_citations` — then reads as "genuinely zero citations".
    Those two things are NOT the same: a missing or unreadable corpus means
    the entire citation-based signal is undeterminable, not zero, and an
    undeterminable signal must not render as a clean KEPT/AUTO verdict (wave-31
    acceptance bar, clause 2a — "CANNOT EVALUATE is not a pass"). This check is
    the gate `run.py`'s `main()` runs BEFORE classification so it can render a
    distinct NOT-MEASURED outcome and return non-zero instead.

    Checks, in order:
      1. the feedback log file exists and is readable as UTF-8;
      2. every `archive/feedback_log_*.md` file beside it (if the archive
         directory exists) is also readable as UTF-8.

    The single-memory/single-section helpers above intentionally keep their
    existing "missing log -> 0 / frontmatter floor" contract for isolated
    unit use (e.g. a caller testing one memory against a scratch path) —
    this function is the whole-corpus precondition the CLI driver checks
    once per run, not a replacement for that per-item contract.
    """
    if not os.path.isfile(feedback_log_path):
        return f"feedback log not found: {feedback_log_path}"
    try:
        with open(feedback_log_path, encoding="utf-8") as f:
            f.read()
    except OSError as exc:
        return f"feedback log unreadable: {feedback_log_path} ({exc})"
    except UnicodeDecodeError as exc:
        return f"feedback log is not valid UTF-8: {feedback_log_path} ({exc})"

    archive_dir = os.path.join(os.path.dirname(feedback_log_path), "archive")
    if os.path.isdir(archive_dir):
        for name in sorted(os.listdir(archive_dir)):
            if not (name.startswith("feedback_log_") and name.endswith(".md")):
                continue
            path = os.path.join(archive_dir, name)
            try:
                with open(path, encoding="utf-8") as f:
                    f.read()
            except OSError as exc:
                return f"archive file unreadable: {path} ({exc})"
            except UnicodeDecodeError as exc:
                return f"archive file is not valid UTF-8: {path} ({exc})"
    return None


# ---------------------------------------------------------------------------
# Provenance-aware citation filtering (#1469)
#
# `count_section_citations` and `count_retro_citations` used to be a bare
# `text.count(needle)` over `_feedback_log_corpus`. That corpus is WRITTEN BY
# the same instruments that read it: `/wave-retro` Step 7.5 reports every
# AUTO/DECIDE/KEPT verdict by heading or filename, Step 7.7 reports citation
# counts back into the log, and Step 7.8's size/age sweep prints a flagged
# file's bare name every wave regardless of whether anyone cited it. A bare
# substring count cannot tell "an operator invoked this rule during real
# work" from "an automated report printed this name" -- so once a section or
# memory crosses threshold once, the audit's own bookkeeping (and the
# retro's bookkeeping OF the audit) keeps it above threshold forever,
# independent of real use. Measured live: `wave-merge.md § Cross-Contract
# PRs` went from an honest 1 operator citation to a reported 7, then 8,
# purely from two retros documenting the number (main#1469).
#
# `_is_self_generated_occurrence` classifies a single substring match by
# inspecting a window of surrounding text for four non-evidence shapes,
# using the same windowed-marker technique `_is_forward_reference` already
# uses for the already-promoted scan:
#
#   1. forward reference    -- delegates to the existing `_is_forward_reference`.
#      A proposal to house a DIFFERENT rule at this heading/name is not a
#      citation of this one.
#   2. creation record      -- the log entry that announces a section's or
#      rule's *addition* ("Charter home: ...", "new § ... per
#      process-change #N").
#   3. audit self-report    -- this module's own vocabulary
#      (`section_citations=`, `retro_citations=`, an "AUTO"/"DECIDE"/"KEPT"
#      verdict-count line, "flagged (advisory", a byte-size cell from the
#      Step 7.8 sweep table, "cited Nx"). A verdict or a citation COUNT is
#      not itself a citation.
#   4. wave-summary listing -- a bullet enumerating several charter
#      sections touched in one wave reads as a listing, not a citation of
#      any one of them; recognized by >= 2 "§" marks sharing the match's line.
#
# This is a heuristic over known shapes, not a formal proof of intent --
# documented in SKILL.md alongside its limitations.
# ---------------------------------------------------------------------------

_CREATION_RECORD_MARKERS = (
    "charter home:",
    "new §",
    "per process-change",
    "proposed charter change",
)

_AUDIT_SELF_REPORT_MARKERS = (
    "_citations=",  # section_citations=, retro_citations=
    "skill_invocations=",
    "the auto is",
    "auto promotion",
    "→ not promoted",
    "auto ·",
    "decide ·",
    "kept ·",
    "stale-opt-out",
    "stale opt-out",
    "orthogonal instruments",
    "flagged (advisory",
    "topic files flagged",
    "size sweep",
    "size/age sweep",
    "soft ceiling",
    "promotion audit",
)

_CITED_N_TIMES_RE = re.compile(r"cited\s+\d+x", re.IGNORECASE)
_SIZE_UNIT_CELL_RE = re.compile(r"\b\d[\d,]*\s*(KB|B)\b")

_SELF_REPORT_WINDOW = 100
_CREATION_RECORD_WINDOW = 80


def _window(text: str, start: int, end: int, back: int, forward: int) -> str:
    """A `back`/`forward`-char window around `text[start:end]`, clipped to
    the containing LINE.

    Clipping to the line matters: these markers (`_CREATION_RECORD_MARKERS`,
    `_AUDIT_SELF_REPORT_MARKERS`) are short strings that can appear on an
    UNRELATED neighboring bullet in a dense retro corpus. An unclipped
    character-distance window leaks the previous or next line's vocabulary
    into the current match's classification — e.g. a genuine citation on a
    short line, immediately followed by a Step 7.8 sweep bullet starting
    "N files flagged (advisory...", would otherwise inherit that neighbor's
    "flagged (advisory" marker and be wrongly excluded.
    """
    line_start, line_end = _line_span(text, start)
    lo = max(line_start, start - back)
    hi = min(line_end, end + forward)
    return text[lo:hi]


def _line_span(text: str, pos: int) -> tuple[int, int]:
    """Return the (start, end) offsets of the line in `text` containing `pos`."""
    line_start = text.rfind("\n", 0, pos) + 1
    line_end = text.find("\n", pos)
    if line_end == -1:
        line_end = len(text)
    return line_start, line_end


def _is_creation_record(text: str, start: int, end: int) -> bool:
    window = _window(text, start, end, _CREATION_RECORD_WINDOW, 20).lower()
    return any(marker in window for marker in _CREATION_RECORD_MARKERS)


def _is_audit_self_report(text: str, start: int, end: int) -> bool:
    window = _window(text, start, end, _SELF_REPORT_WINDOW, _SELF_REPORT_WINDOW)
    lower = window.lower()
    if any(marker in lower for marker in _AUDIT_SELF_REPORT_MARKERS):
        return True
    if _CITED_N_TIMES_RE.search(window):
        return True
    return bool(_SIZE_UNIT_CELL_RE.search(window))


def _is_wave_summary_listing(text: str, start: int, end: int) -> bool:
    line_start, line_end = _line_span(text, start)
    return text.count("§", line_start, line_end) >= 2


def _is_self_generated_occurrence(text: str, start: int, end: int) -> bool:
    """Return True if `text[start:end]` is not an operator citation.

    See the module-level note above for the four excluded shapes.
    """
    if _is_forward_reference(text, start):
        return True
    if _is_creation_record(text, start, end):
        return True
    if _is_audit_self_report(text, start, end):
        return True
    return _is_wave_summary_listing(text, start, end)


# #1450: a heading-run continuation character. Charter headings routinely
# join words with a hyphen ("Cross-Contract", "Load-Bearing"), so a plain
# regex `\b` is the WRONG boundary primitive here -- `\b`'s `\w` class
# treats `-` as a non-word char, i.e. as a boundary, which would let a
# short heading match as "genuine" when it is really the tail of a longer
# hyphen-joined heading run (e.g. needle "Contract PRs" sitting inside
# "Cross-Contract PRs"). Extending the continuation class to include `-`
# closes that gap. Everything else that can flank a citation in practice --
# whitespace, `§`, backticks, and sentence punctuation (`.`, `,`, `:`,
# `)`) -- is deliberately left OUT of this class, so a legitimate citation
# immediately followed by punctuation, or wrapped in backticks, still
# counts (see `CountGenuineCitationsTests` boundary-edge fixtures).
_HEADING_CONTINUATION_RE = re.compile(r"[A-Za-z0-9_-]")


def _is_citation_boundary(text: str, idx: int) -> bool:
    """Return True if position `idx` in `text` is a citation boundary --
    i.e. NOT a continuation of a heading-like identifier run.

    Out-of-bounds (before the start / at-or-past the end of `text`) is
    always a boundary: a needle flush against either edge of the corpus
    has nothing to be embedded in.
    """
    if idx < 0 or idx >= len(text):
        return True
    return _HEADING_CONTINUATION_RE.match(text[idx]) is None


def count_genuine_citations(text: str, needle: str) -> int:
    """Count non-overlapping occurrences of `needle` in `text`, excluding
    self-generated provenance (see `_is_self_generated_occurrence`) AND
    occurrences that are merely a substring of a longer heading-like run
    (see `_is_citation_boundary`, #1450).

    The shared primitive both `count_section_citations` (charter tier) and
    `count_retro_citations` (memory tier) call instead of `text.count(...)`
    (#1469). Mirrors `str.count`'s non-overlapping-match semantics, and its
    own blank-needle guard: `text.count("")` returns `len(text) + 1`, which
    would make an empty needle look like it trivially crossed any
    threshold -- the same defensive shape as the main#690 blank-slug guard
    and `count_section_citations`'s blank-heading guard.

    #1450: a bare substring scan double-counts a short heading that is
    embedded in a longer one (a false "genuine" citation of the short
    heading when the operator actually cited the longer one) and counts a
    heading embedded in an unrelated prose word (e.g. "PRs" inside
    "PRsomething"). Both are closed by requiring a `_is_citation_boundary`
    on BOTH sides of the match, in addition to the existing
    `_is_self_generated_occurrence` classification -- the two defects are
    independent and compose at this call site. Non-overlapping-match
    semantics are preserved by always advancing `pos` to the end of a
    found match, whether or not it was counted (mirrors the prior
    `text.find` loop's advance).
    """
    if not needle:
        return 0
    count = 0
    pos = 0
    pattern = re.compile(re.escape(needle))
    while True:
        match = pattern.search(text, pos)
        if match is None:
            break
        idx, end = match.start(), match.end()
        if (
            _is_citation_boundary(text, idx - 1)
            and _is_citation_boundary(text, end)
            and not _is_self_generated_occurrence(text, idx, end)
        ):
            count += 1
        pos = end
    return count


def count_retro_citations(memory: Memory, feedback_log_path: str) -> int:
    """Count occurrences of the memory name or filename in the feedback log.

    Scans the live log AND the per-phase archives beside it (see
    `_feedback_log_corpus`). Counts the larger of:
      - occurrences of `memory.name` (title string)
      - occurrences of `memory.filename` (e.g., feedback_enforcement_hierarchy.md)

    Both counts go through `count_genuine_citations` (#1469), which excludes
    occurrences originating from `/wave-retro`'s own bookkeeping — the
    Step 7.8 size/age sweep prints a flagged file's bare name every wave
    purely because it is large, and Step 7.7 reports the citation count
    itself back into the log. Neither is an operator invoking the memory's
    lesson. See the module-level note above `count_genuine_citations` for
    the full discrimination.

    Also adds `len(memory.referenced_in_retros)` as a floor — authors can
    manually record retro citations in frontmatter for cases where the log
    doesn't spell out the filename. This floor is NOT provenance-filtered:
    it is a deliberate, hand-entered claim, not a corpus scan.
    """
    text = _feedback_log_corpus(feedback_log_path)
    if not text:
        return len(memory.referenced_in_retros)
    by_title = count_genuine_citations(text, memory.name) if memory.name else 0
    by_file = count_genuine_citations(text, memory.filename)
    return max(by_title, by_file, len(memory.referenced_in_retros))


def count_section_citations(section: CharterSection, feedback_log_path: str) -> int:
    """Count occurrences of a charter section's heading in the feedback log.

    #1355: the charter -> skill transition's actual evidence for promotion
    is how heavily the SOURCE section is exercised -- not usage of the
    PROSPECTIVE destination skill slug. A not-yet-created skill can never
    accrue invocations of itself (`count_skill_invocations` on an
    empty/prospective slug is structurally 0 forever, by definition, for
    every not-yet-promoted section -- see `run.py`'s `_section_signal_slug`
    docstring for the full history of that inversion). This mirrors
    `count_retro_citations`'s mechanism for memories -- scanning the live
    feedback log AND its per-phase archives (`_feedback_log_corpus`, #964)
    for literal occurrences of the heading text -- which genuinely
    accumulates: operators cite a charter section by its heading when they
    reference it during a retro, and that citation count grows over time
    independent of whether the destination skill has been scaffolded yet.

    Deliberately independent of any skill slug or `.claude/skills/` lookup:
    unlike the old destination-invocation signal, this count cannot inherit
    an unrelated skill's invocation history just because a heading happens
    to slugify onto an existing skill directory name (main#1389's
    collision risk) -- there is no slug in this computation at all.

    An empty or whitespace-only heading returns 0 -- never the corpus
    length. `text.count("")` returns `len(text) + 1`, which would make a
    blank heading look like it trivially crossed any threshold. This
    should never occur in practice (`read_charter_sections` requires
    non-empty heading text to match `_SECTION_MARKER_RE`), but the guard
    is the same defensive shape as the main#690 blank-slug guard below.

    The count goes through `count_genuine_citations` (#1469), which
    excludes occurrences originating from the promotion-audit's own
    reporting of this section's verdict, `/wave-retro`'s bookkeeping of
    that report, creation records, and multi-section wave-summary
    listings -- see the module-level note above `count_genuine_citations`.
    """
    if not section.heading or not section.heading.strip():
        return 0
    text = _feedback_log_corpus(feedback_log_path)
    if not text:
        return 0
    return count_genuine_citations(text, section.heading)


def count_skill_invocations(skill_name: str, repo_root: str) -> int:
    """Count git log commits that reference the skill by slash-name.

    D4 lightweight: we do NOT scan transcripts. `git log --grep="/{skill}"`
    finds commit messages that reference the skill, which is a stable and
    durable signal for "this skill got invoked during real work."

    An empty or whitespace-only `skill_name` returns 0 — never the full
    commit count. `git log --grep=/` matches (nearly) every commit because
    almost all commit messages contain a slash, so a blank slug would
    report a huge invocation count and spuriously cross any threshold.
    This guard is the root-cause fix for the P5W4 24-spurious-AUTO mis-fire
    (main#690): hand-rolled callers passed an empty `section.promoted_to`
    slug straight through to this counter.
    """
    if not skill_name or not skill_name.strip():
        return 0
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                repo_root,
                "log",
                "--oneline",
                f"--grep=/{skill_name}",
                "--all",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return 0
    if result.returncode != 0:
        return 0
    lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
    return len(lines)


# ---------------------------------------------------------------------------
# Already-promoted detection (Q5)
# ---------------------------------------------------------------------------

_PROVENANCE_RE = re.compile(
    r"\*\*Promotion provenance:\*\*\s*(?P<body>.+?)(?:\n\n|\Z)",
    re.DOTALL,
)

# `<!-- Promoted from memory: <name>[.md] (optional trailing context) -->`
# The new charter-tier promotion marker (issue #283), used inline after a
# charter section heading instead of a `Promotion provenance:` block. The
# captured body runs until the closing `-->` so trailing context (date,
# rationale, retro reference) is included in the regex sweep that
# follows.
_HTML_COMMENT_PROMOTED_RE = re.compile(
    r"<!--\s*Promoted from memory:\s*(?P<body>.+?)\s*-->",
    re.DOTALL,
)

# Memory filenames can be cited with or without the `.md` suffix in
# charter prose (e.g. hooks.md L169 cites `feedback_honest_audit_over_conclusion_claim`
# unsuffixed inside a backticked span). The regex makes the `.md` optional
# and the caller backfills the suffix into the returned set so both forms
# are recognized in membership checks.
#
# Slash-command branch shape (#419): `(?<![\w/])/[a-z][a-z0-9-]{2,}` —
# kebab-case slash-commands, alpha-leading, length >= 3, AND preceded by
# a non-word/non-slash boundary. The alpha-leading filter rejects
# URL-path-fragment hits like `/198` (numeric issue IDs from gh URLs);
# the length-3 minimum rejects `/a`, `/b1`; and the lookbehind rejects
# mid-token slashes like `/supersedes` inside the prose `augments/supersedes`
# in charter/skills.md. Combined with `_strip_url_bodies` (applied to the
# block body BEFORE the regex runs), this rejects the 11 URL-fragment
# false positives documented in #419 plus the `augments/supersedes` 12th.
_SOURCE_HINT_RE = re.compile(
    r"""
    (?:
        (?:feedback|project|reference)_[a-z0-9_]+(?:\.md)?  # memory filenames (with or without .md)
        |
        (?<![\w/])/[a-z][a-z0-9-]{2,}                       # slash-commands at word boundary
    )
    """,
    re.VERBOSE,
)


# URL-stripping regexes (#419). Applied to provenance-block bodies BEFORE
# `_SOURCE_HINT_RE.finditer` so URL path fragments never reach the slash-
# command branch. Three forms:
#   - markdown link bodies: `[text](url)` → `[text]()` (preserves link text)
#   - autolinks: `<url>` → ``
#   - bare URLs: `https://...` → ``
# The link-text preservation matters because some link labels themselves
# contain a memory filename or slash-command reference that IS load-bearing.
_MD_LINK_URL_RE = re.compile(r"\]\(\s*<?(?:https?|ftp)://[^\s)>]+>?\s*\)")
_AUTOLINK_URL_RE = re.compile(r"<(?:https?|ftp)://[^>\s]+>")
_BARE_URL_RE = re.compile(r"(?<![\[\(])(?:https?|ftp)://[^\s)>]+")


def _strip_url_bodies(text: str) -> str:
    """Remove URL bodies from `text` while preserving non-URL prose.

    Applied to provenance-block bodies before `_SOURCE_HINT_RE.finditer`
    so URL path fragments (`/198`, `/issues`, `/noorinalabs-main`, etc.)
    never reach the slash-command branch as false positives (#419).
    Markdown link text is preserved by replacing `(url)` with `()`,
    leaving `[text]` intact — if a link label cites a real memory
    filename or slash-command, that reference still surfaces in the
    downstream regex sweep.
    """
    text = _MD_LINK_URL_RE.sub("]()", text)
    text = _AUTOLINK_URL_RE.sub("", text)
    text = _BARE_URL_RE.sub("", text)
    return text


# Memory-filename prefixes the parser recognizes. Used by
# `_normalize_memory_hit` to decide whether a no-suffix hit should be
# backfilled with `.md`.
_MEMORY_PREFIXES = ("feedback_", "project_", "reference_")


# Narrative words that indicate a forward-reference rather than a
# backward-looking promotion claim. A slash-command within a few words of
# any of these is excluded from the already-promoted set.
_FORWARD_REFERENCE_MARKERS = (
    "future",
    "planned",
    "design",
    "upcoming",
    "referenced by",
    "will reference",
    "proposed",
    "TBD",
)


def _is_forward_reference(body: str, match_start: int) -> bool:
    """Return True if `body[match_start:]` sits inside a forward-reference phrase.

    Looks backward up to 60 chars from the match position and forward up to
    20 chars; if any marker appears in that window, this is NOT a promotion
    claim — the hook author is just citing the future artifact by name.
    """
    start = max(0, match_start - 60)
    end = min(len(body), match_start + 20)
    window = body[start:end].lower()
    return any(marker in window for marker in _FORWARD_REFERENCE_MARKERS)


def _normalize_memory_hit(hit: str) -> tuple[str, ...]:
    """Return both forms (with and without `.md`) of a memory filename hit.

    The caller adds all returned strings to the already-promoted set so
    membership checks via `memory.filename` (always `.md`-suffixed) and
    via raw-name citation work transparently.

    For non-memory hits (slash-commands, anything else), returns a single-
    element tuple containing the hit unchanged.
    """
    if hit.startswith(_MEMORY_PREFIXES):
        if hit.endswith(".md"):
            return (hit, hit[:-3])
        return (hit, hit + ".md")
    return (hit,)


def find_already_promoted(charter_path: str) -> set[str]:
    """Return the set of source identifiers already promoted in `charter_path`.

    Recognizes BOTH provenance formats used across the charter:

    1. **Block style** (charter/hooks.md, the format Hook 15 established
       in PR #153):

           **Promotion provenance:** First end-to-end execution of the
           memory -> charter -> hook promotion pattern ratified by the
           owner on 2026-04-19. Rule lived in CLAUDE.md § Ontology ...

    2. **HTML-comment marker** (newer charter-tier-only promotions, per
       issue #283):

           <!-- Promoted from memory: feedback_X.md (P3W5 retro 2026-05-06) -->

       Used inline after a charter section heading when a memory is
       promoted into the charter without a corresponding hook.

    Slash-commands that appear inside forward-reference phrases (e.g.
    "referenced by the future `/promotion-audit` skill design") are
    EXCLUDED — those are narrative cross-references, not promotion claims.
    See `_FORWARD_REFERENCE_MARKERS`.

    Memory-filename citations are recognized in BOTH `.md`-suffixed and
    suffix-less forms (the latter appears in hooks.md L169's backticked
    cite of `feedback_honest_audit_over_conclusion_claim`). Both forms
    land in the returned set so callers using `memory.filename in
    already_promoted` continue to match transparently.

    For the aggregating scan across the full charter directory, use
    `find_already_promoted_in_charter()` — this single-path entry point
    is retained for the smoke test and for callers that want to scope
    the scan to a specific file.

    The returned set contains strings like:
        - "feedback_enforcement_hierarchy.md" / "feedback_enforcement_hierarchy"
        - "/ontology-librarian" (skill slash-commands with backward semantics)
        - "CLAUDE.md § Ontology" (rule references, when the Ontology
          section is cited in any provenance block)
    """
    refs: set[str] = set()
    if not os.path.isfile(charter_path):
        return refs
    with open(charter_path, encoding="utf-8") as f:
        text = f.read()

    # Block-style `**Promotion provenance:**` entries (hooks.md format).
    # URL bodies stripped first (#419) so gh-issue-link path fragments
    # never reach the slash-command branch.
    for block in _PROVENANCE_RE.finditer(text):
        body = _strip_url_bodies(block.group("body"))
        for hit in _SOURCE_HINT_RE.finditer(body):
            if _is_forward_reference(body, hit.start()):
                continue
            refs.update(_normalize_memory_hit(hit.group(0)))

    # HTML-comment style `<!-- Promoted from memory: X -->` (charter-tier
    # promotion marker, issue #283). Forward-reference filtering is
    # unnecessary for this format — the marker is by definition a
    # backward-looking promotion claim.
    for block in _HTML_COMMENT_PROMOTED_RE.finditer(text):
        body = _strip_url_bodies(block.group("body"))
        for hit in _SOURCE_HINT_RE.finditer(body):
            refs.update(_normalize_memory_hit(hit.group(0)))

    # The librarian rule's provenance cites CLAUDE.md § Ontology; capture
    # it as a synonym for the enforcement-hierarchy memory.
    if "CLAUDE.md § Ontology" in text:
        refs.add("CLAUDE.md § Ontology")
        refs.add("feedback_enforcement_hierarchy.md")
    return refs


def find_already_promoted_in_charter(charter_parent: str) -> set[str]:
    """Aggregate already-promoted refs across the full charter directory.

    `charter_parent` is the directory **containing** the `charter/` subdir
    (typically `.claude/team`), NOT the `charter/` directory itself.

    Scans `<charter_parent>/charter/**/*.md` (recursive, #963) (and the optional
    `<charter_parent>/charter.md` top-level file, if present) using the same
    recognition rules as `find_already_promoted()`. Returns the union of
    all per-file results.

    This is the entry point the /promotion-audit skill should use — single-
    file scope (charter/hooks.md only) misses charter-tier-only promotions
    that land via the HTML-comment marker in other sub-docs (issue #283).

    Raises:
        ValueError: if `charter_parent` is itself a directory named `charter`
            — a strong hint the caller passed the charter dir instead of its
            parent (issue #418 silent-zero bug). Returns set() for any other
            non-existent path (defensive contract preserved).
    """
    refs: set[str] = set()
    if not os.path.isdir(charter_parent):
        return refs

    if os.path.basename(os.path.normpath(charter_parent)) == "charter":
        raise ValueError(
            f"find_already_promoted_in_charter({charter_parent!r}): "
            "argument is the charter directory itself — pass its parent "
            "(e.g. '.claude/team', not '.claude/team/charter'). "
            "See issue #418."
        )

    candidates: list[str] = []
    root_file = os.path.join(charter_parent, "charter.md")
    if os.path.isfile(root_file):
        candidates.append(root_file)

    subdir = os.path.join(charter_parent, "charter")
    if os.path.isdir(subdir):
        candidates.extend(_charter_md_files(subdir))

    for path in candidates:
        refs.update(find_already_promoted(path))

    return refs


# ---------------------------------------------------------------------------
# Classification (Q1–Q5 locked)
# ---------------------------------------------------------------------------


DecisionKind = Literal["AUTO", "DECIDE", "KEPT", "SUPERSEDED", "ALREADY-PROMOTED"]


@dataclass(frozen=True)
class Decision:
    kind: DecisionKind
    item_id: str  # display identifier (memory filename, section heading, skill name)
    from_tier: str  # "memory" | "charter" | "skill"
    to_tier: str  # "charter" | "skill" | "hook" | "-"
    signal: str
    reason: str
    # For AUTO: path to the source; for DECIDE: set by the caller to the
    # issue URL after creation.
    artifact_ref: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


def classify_memory(
    memory: Memory,
    signals: dict[str, int],
    already_promoted: set[str],
) -> Decision:
    """Classify a memory for the memory → charter transition."""
    # ALREADY-PROMOTED always wins.
    if memory.filename in already_promoted or memory.name in already_promoted:
        return Decision(
            kind="ALREADY-PROMOTED",
            item_id=memory.filename,
            from_tier="memory",
            to_tier="charter",
            signal="provenance block in charter/hooks.md",
            reason="Source codified via Promotion provenance entry",
        )

    if memory.status == "superseded":
        return Decision(
            kind="SUPERSEDED",
            item_id=memory.filename,
            from_tier="memory",
            to_tier="-",
            signal=f"superseded_by: {memory.superseded_by or '(unset)'}",
            reason="Memory explicitly marked superseded",
        )

    if memory.status == "enforced-elsewhere":
        return Decision(
            kind="SUPERSEDED",
            item_id=memory.filename,
            from_tier="memory",
            to_tier="-",
            signal=f"enforced-elsewhere -> {memory.superseded_by or '(unset)'}",
            reason="Memory enforced via another artifact (charter / hook)",
        )

    citations = signals.get("retro_citations", 0)
    threshold = memory.promotion_threshold.get("retro_citations", 3)

    if memory.promotion_target == "none":
        # STALE-OPT-OUT informational class (#158): a memory marked
        # `promotion_target: none` is authoritative — the opt-out stands.
        # But when citations reach 2× the threshold, surface the entry in
        # an informational sub-list so operators can reconsider during
        # wave-retro. No auto-action, no issue filed; the kind stays KEPT.
        if citations >= 2 * threshold:
            return Decision(
                kind="KEPT",
                item_id=memory.filename,
                from_tier="memory",
                to_tier="-",
                signal=f"retro_citations={citations} >= 2 * {threshold}",
                reason=(
                    f"promotion_target=none, but cited {citations}x — "
                    "consider reviewing the opt-out"
                ),
                extra={"stale_opt_out": True},
            )
        return Decision(
            kind="KEPT",
            item_id=memory.filename,
            from_tier="memory",
            to_tier="-",
            signal=f"retro_citations={citations}",
            reason="promotion_target=none (informational memory)",
        )

    if memory.promotion_target != "charter":
        # Memories only promote to charter (skills promote to hook).
        return Decision(
            kind="KEPT",
            item_id=memory.filename,
            from_tier="memory",
            to_tier=memory.promotion_target,
            signal=f"retro_citations={citations}",
            reason=f"promotion_target={memory.promotion_target} is not a valid memory transition",
        )

    if citations < threshold:
        return Decision(
            kind="KEPT",
            item_id=memory.filename,
            from_tier="memory",
            to_tier="charter",
            signal=f"retro_citations={citations} < {threshold}",
            reason="Threshold not met",
        )

    if memory.requires_decision:
        return Decision(
            kind="DECIDE",
            item_id=memory.filename,
            from_tier="memory",
            to_tier="charter",
            signal=f"retro_citations={citations} >= {threshold}",
            reason="requires_decision=true escape hatch set",
        )

    return Decision(
        kind="AUTO",
        item_id=memory.filename,
        from_tier="memory",
        to_tier="charter",
        signal=f"retro_citations={citations} >= {threshold}",
        reason="Thresholds met; charter additions are safe to auto-apply",
    )


def classify_section(
    section: CharterSection,
    signals: dict[str, int],
) -> Decision:
    """Classify a charter section for the charter → skill transition.

    #1355: `signals["section_citations"]` is expected to come from
    `count_section_citations` (retro citations of THIS section's heading) —
    the actual evidence for promotion — not from `count_skill_invocations`
    against the prospective destination slug, which is structurally 0
    forever for every not-yet-promoted section (see `count_section_citations`
    docstring for the full rationale). Callers passing the legacy
    `skill_invocations` key are silently treated as 0 citations; see
    `run.py`'s `run_audit` for the canonical wiring.
    """
    if section.promoted_to:
        return Decision(
            kind="ALREADY-PROMOTED",
            item_id=f"{os.path.basename(section.path)} § {section.heading}",
            from_tier="charter",
            to_tier="skill",
            signal=f"promoted-to: {section.promoted_to}",
            reason="Section has a promoted-to back-reference",
        )

    if section.promotion_target == "none":
        return Decision(
            kind="KEPT",
            item_id=f"{os.path.basename(section.path)} § {section.heading}",
            from_tier="charter",
            to_tier="-",
            signal="promotion-target: none",
            reason="Section explicitly opted out of promotion",
        )

    if section.promotion_target != "skill":
        return Decision(
            kind="KEPT",
            item_id=f"{os.path.basename(section.path)} § {section.heading}",
            from_tier="charter",
            to_tier=section.promotion_target,
            signal=f"promotion-target: {section.promotion_target}",
            reason="Charter sections only promote to skill",
        )

    citations = signals.get("section_citations", 0)
    threshold = signals.get("threshold", 5)

    if citations < threshold:
        # #1383's target_configured distinction is preserved as informational
        # context (does a skill already exist on disk at the prospective
        # slug?), but it no longer gates *whether* evidence can accrue —
        # `section_citations` is computed from the SOURCE section and
        # genuinely accumulates regardless of scaffold status (#1355 fixes
        # the prior inversion where the destination-invocation signal really
        # was structurally 0 without a target). The unconfigured message is
        # corrected accordingly: it no longer claims evidence "cannot
        # accrue" without scaffolding — it can, and does.
        target_configured = bool(signals.get("target_configured", 0))
        if target_configured:
            reason = "Invocation threshold not met; wait for more operator-invoked runs"
        else:
            reason = (
                "Promotion target not configured — no skill exists at this slug yet, "
                f"but that no longer blocks evidence from accruing: {citations} retro "
                f"citation(s) of this section are already recorded ({citations}/{threshold} "
                "toward threshold). Scaffolding the skill remains a deliberate human "
                "act, but it is not a precondition for the signal itself"
            )
        return Decision(
            kind="KEPT",
            item_id=f"{os.path.basename(section.path)} § {section.heading}",
            from_tier="charter",
            to_tier="skill",
            signal=f"section_citations={citations} < {threshold}",
            reason=reason,
            extra={"target_configured": target_configured},
        )

    return Decision(
        kind="AUTO",
        item_id=f"{os.path.basename(section.path)} § {section.heading}",
        from_tier="charter",
        to_tier="skill",
        signal=f"section_citations={citations} >= {threshold}",
        reason="Thresholds met; skill scaffold is safe to auto-generate",
    )


def classify_skill(
    skill: Skill,
    signals: dict[str, int],
    already_promoted: set[str],
) -> Decision:
    """Classify a skill for the skill → hook transition.

    Skill → hook is ALWAYS DECIDE per D6 (hooks are security-sensitive).
    """
    slash_name = f"/{skill.name}"
    if slash_name in already_promoted:
        return Decision(
            kind="ALREADY-PROMOTED",
            item_id=skill.name,
            from_tier="skill",
            to_tier="hook",
            signal=f"provenance block references {slash_name}",
            reason="Skill already enforced via a registered hook",
        )

    if skill.promotion_target != "hook":
        return Decision(
            kind="KEPT",
            item_id=skill.name,
            from_tier="skill",
            to_tier="-",
            signal="promotion-target != hook",
            reason="Skill not opted into hook promotion",
        )

    invocations = signals.get("skill_invocations", 0)
    threshold = signals.get("threshold", 5)

    if invocations < threshold:
        return Decision(
            kind="KEPT",
            item_id=skill.name,
            from_tier="skill",
            to_tier="hook",
            signal=f"skill_invocations={invocations} < {threshold}",
            reason="Invocation threshold not met",
        )

    # Always DECIDE — D6 locked.
    return Decision(
        kind="DECIDE",
        item_id=skill.name,
        from_tier="skill",
        to_tier="hook",
        signal=f"skill_invocations={invocations} >= {threshold}",
        reason="Skill → hook is always DECIDE (security-sensitive, D6)",
    )


# ---------------------------------------------------------------------------
# Audit table rendering
# ---------------------------------------------------------------------------


_KIND_ORDER = {
    "AUTO": 0,
    "DECIDE": 1,
    "KEPT": 2,
    "SUPERSEDED": 3,
    "ALREADY-PROMOTED": 4,
}


def render_audit_table(decisions: list[Decision], wave_name: str, audit_date: str) -> str:
    """Deterministic markdown rendering of the audit outcome.

    `audit_date` is passed in (not read from the clock) to preserve
    re-run determinism. Callers pin it to the wave boundary date from
    `cross-repo-status.json`.
    """
    auto = [d for d in decisions if d.kind == "AUTO"]
    decide = [d for d in decisions if d.kind == "DECIDE"]
    kept = [d for d in decisions if d.kind == "KEPT"]
    supers = [d for d in decisions if d.kind in ("SUPERSEDED", "ALREADY-PROMOTED")]

    # Deterministic sort within each bucket.
    for bucket in (auto, decide, kept, supers):
        bucket.sort(key=lambda d: (d.from_tier, d.item_id))

    out: list[str] = []
    out.append(f"## Promotion Audit — {wave_name} ({audit_date})")
    out.append("")
    out.append(
        f"**Summary:** {len(auto)} AUTO · {len(decide)} DECIDE · "
        f"{len(kept)} KEPT · {len(supers)} SUPERSEDED/ALREADY-PROMOTED"
    )
    out.append("")

    out.append("### AUTO-PROMOTED (artifacts generated this run)")
    if auto:
        out.append("| Item | From → To | Signal | Artifact |")
        out.append("|---|---|---|---|")
        for d in auto:
            artifact = d.artifact_ref or "-"
            row = f"| {d.item_id} | {d.from_tier} → {d.to_tier} | {d.signal} | {artifact} |"
            out.append(row)
    else:
        out.append("_None this run._")
    out.append("")

    out.append("### REQUIRES DECISION (issues filed)")
    if decide:
        out.append("| Item | Candidate target | Signal | Issue |")
        out.append("|---|---|---|---|")
        for d in decide:
            issue_ref = d.artifact_ref or "(pending)"
            row = f"| {d.item_id} | {d.from_tier} → {d.to_tier} | {d.signal} | {issue_ref} |"
            out.append(row)
    else:
        out.append("_None this run._")
    out.append("")

    out.append("### KEPT (no action — informational)")
    # Split KEPT into stale-opt-out flagged vs the rest. STALE-OPT-OUT
    # entries (#158) are informational callouts — high-citation memories
    # whose `promotion_target: none` opt-out has crossed 2× the threshold.
    # They render as a separate sub-list so operators can spot drift
    # without changing how the rest of KEPT is presented.
    stale = [d for d in kept if d.extra.get("stale_opt_out")]
    others = [d for d in kept if not d.extra.get("stale_opt_out")]

    if not kept:
        out.append("_None._")
    else:
        if others:
            for d in others:
                out.append(f"- `{d.item_id}` ({d.from_tier}): {d.reason} [{d.signal}]")
        if stale:
            if others:
                out.append("")
            out.append("**STALE-OPT-OUT (review the opt-out — informational only):**")
            for d in stale:
                out.append(f"- `{d.item_id}` ({d.from_tier}): {d.reason} [{d.signal}]")
    out.append("")

    out.append("### SUPERSEDED / ALREADY-PROMOTED (no action — informational)")
    if supers:
        for d in supers:
            out.append(f"- `{d.item_id}` ({d.from_tier}): {d.reason} [{d.signal}]")
    else:
        out.append("_None._")
    out.append("")

    return "\n".join(out)


# ---------------------------------------------------------------------------
# Artifact generation (templated)
# ---------------------------------------------------------------------------


def _read_template(template_dir: str, name: str) -> str:
    with open(os.path.join(template_dir, name), encoding="utf-8") as f:
        return f.read()


def generate_charter_section(memory: Memory, template_dir: str) -> str:
    """Render a charter-section artifact from a memory using the template.

    The template emits the canonical HTML-comment provenance marker per
    charter/skills.md § Promotion Pipeline Marker Convention (#393); the
    italic-prose `_Promoted from memory ..._` line that this template used
    pre-#393 was not parser-recognized and is now banned.
    """
    tpl = _read_template(template_dir, "charter-section.md")
    return (
        tpl.replace("{{MEMORY_NAME}}", memory.name)
        .replace("{{MEMORY_FILENAME}}", memory.filename)
        .replace("{{BODY}}", memory.body.strip())
    )


def generate_skill_scaffold(section: CharterSection, template_dir: str) -> str:
    """Render a SKILL.md scaffold from a charter section using the template."""
    tpl = _read_template(template_dir, "skill-scaffold.md")
    slug = _slugify(section.heading)
    return (
        tpl.replace("{{SECTION_HEADING}}", section.heading)
        .replace("{{SECTION_BODY}}", section.body.strip())
        .replace("{{SOURCE_CHARTER}}", os.path.basename(section.path))
        .replace("{{SKILL_SLUG}}", slug)
    )


def generate_hook_draft_issue(skill: Skill, template_dir: str) -> dict[str, str]:
    """Render a hook-draft issue body; returns {'title': ..., 'body': ...}."""
    tpl = _read_template(template_dir, "hook-draft.md")
    body = (
        tpl.replace("{{SKILL_NAME}}", skill.name)
        .replace("{{SKILL_DESCRIPTION}}", skill.description)
        .replace("{{SKILL_BODY}}", skill.body.strip())
    )
    title = f"feat(hooks): draft — promote /{skill.name} skill to hook (promotion-audit)"
    return {"title": title, "body": body}


def _slugify(text: str) -> str:
    """Turn a heading like 'Load-Bearing Followups' into 'load-bearing-followups'."""
    t = text.lower().strip()
    t = re.sub(r"[^a-z0-9]+", "-", t)
    t = t.strip("-")
    return t or "section"
