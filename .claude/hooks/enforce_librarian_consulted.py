#!/usr/bin/env python3
"""PreToolUse hook: Block Edit/Write/NotebookEdit unless /ontology-librarian was consulted.

Per CLAUDE.md § Ontology:
  "Every agent — orchestrator, team member, or one-off — MUST run
   /ontology-librarian {topic} before making code changes."

This hook enforces that charter rule. It fires before Edit/Write/NotebookEdit
and scans the current session's transcript for evidence of a librarian
consultation. If none is found, the edit is blocked with guidance.

Input Language
==============

Fires on:
    PreToolUse Edit
    PreToolUse Write
    PreToolUse NotebookEdit

Matches (tool_input.file_path or tool_input.notebook_path):
    Any file path in the parameters of the above tools, EXCEPT paths
    matching one of the allow-list rules below. The hook reads the
    transcript file whose path is passed as `input_data["transcript_path"]`
    (Claude Code agent SDK convention).

Does NOT match (allow-listed paths — no librarian required):
    /tmp/**                — out-of-repo scratch (issue body drafts, etc.)
    **/memory/*.md         — project memory files written by handoff/retro
    **/MEMORY.md           — auto-memory index
    ~/.claude/**           — user-level config, not source code
    .claude/annunaki/*     — error log (hook-managed, not hand-edited code)

Stance on meta-files (.claude/team/feedback_log.md, trust_matrix.md, etc.):
    REQUIRES librarian. These ARE project-state artifacts that the ontology
    tracks and conventions describe. Treating them as "free edits" replays
    the very decay pattern #150 is fixing. If false-positives accumulate,
    add a sentinel-comment bypass — do not broaden the path allow-list.

Transcript shape expected (JSONL, one object per line):
    Form A (string content):
        {"type": "user",
         "message": {"role": "user",
                     "content": "<command-name>/ontology-librarian</command-name>..."}}
    Form B (list content with text block):
        {"type": "user",
         "message": {"role": "user",
                     "content": [{"type": "text",
                                  "text": "/ontology-librarian ..."}]}}
    Form C (assistant Skill tool_use):
        {"type": "assistant",
         "message": {"role": "assistant",
                     "content": [{"type": "tool_use",
                                  "name": "Skill",
                                  "input": {"skill": "ontology-librarian",
                                            "args": "..."}}]}}

Detection signals (any ONE is sufficient):
    1. A `user` line whose text contains the literal substring
       "/ontology-librarian" OR "<command-name>/ontology-librarian".
    2. An `assistant` `tool_use` block with name == "Skill" and
       input.skill == "ontology-librarian".
    3. A fresh cwd-keyed sentinel file (see below) — fallback for the
       transcript-flush race in subagent worktree sessions.

Sentinel fallback (second acceptance signal, added for #169):
    The librarian skill writes a sentinel file on invocation at:
        <cwd>/.claude/.consulted/ontology-librarian/<hash>.marker
    where <hash> is the first 16 hex chars of sha1(abspath(cwd)). The hook
    accepts the marker if its mtime is within SENTINEL_TTL_SECONDS (1 hour)
    of now AND the cwd reported in `input_data["cwd"]` matches the hashed
    cwd. Either the transcript scan OR a fresh matching sentinel is
    sufficient to allow the edit.

    Rationale (#169): subagents in worktree sessions repeatedly had
    /ontology-librarian Skill tool_use entries ignored by the transcript
    scan — the transcript path the hook reads either lagged the flush or
    pointed at the parent orchestrator's file. The sentinel is written
    synchronously by the skill and doesn't depend on transcript plumbing.

    Cwd-keyed design: each worktree has a distinct cwd, hence a distinct
    sentinel. This preserves the charter requirement that each agent invoke
    the librarian ITSELF — the orchestrator in the main repo cwd and a
    subagent in a worktree cwd do not share a sentinel.

    Known limitation: a subagent operating in the SAME cwd as its parent
    (non-worktree — rare) would be covered by the parent's sentinel. This
    is an accepted trade-off; the dominant failure mode (#169) is worktree
    subagents, which this fix addresses.

Scope of scan:
    Entire transcript file (a Claude Code session == one transcript). Each
    new session starts a fresh transcript, so a previous session's
    invocation cannot carry over. This matches the issue body's
    "since the last /clear or session start" requirement. Sentinel TTL of
    1 hour bounds cross-session carryover on the sentinel path.

Exit codes (per Claude Code hook convention):
    0 — allow (not a matched tool, allow-listed path, librarian found in
        transcript, or fresh sentinel matches cwd)
    2 — block (writable path AND no librarian signal from either source)

Enforcement artifact for: noorinalabs/noorinalabs-main#150
Sentinel fallback for:   noorinalabs/noorinalabs-main#169
Promotion pattern example: memory -> charter (CLAUDE.md § Ontology) -> hook.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _consultation_sentinel import (  # noqa: E402
    DEFAULT_TTL_SECONDS,
    SENTINEL_PARENT_DIR,
    consultation_sentinel_path,
    cwd_sentinel_hash,
    find_attesting_sentinel,
)
from annunaki_log import log_pretooluse_block, log_pretooluse_diagnostic  # noqa: E402

# Sentinel-fallback config — delegated to `_consultation_sentinel` per #176.
# These module-level names are preserved as back-compat shims for tests that
# pre-#176 referenced `hook.SENTINEL_DIR_NAME` / `hook._cwd_sentinel_hash` /
# `hook.SENTINEL_TTL_SECONDS` directly. The values are now derived from the
# shared helper so behavior cannot drift between the two.
_SKILL_KEY = "ontology-librarian"
SENTINEL_DIR_NAME = f"{SENTINEL_PARENT_DIR}/{_SKILL_KEY}"
SENTINEL_TTL_SECONDS = DEFAULT_TTL_SECONDS  # 1 hour, inherits from helper

# Tool matchers this hook enforces on.
_MATCHED_TOOLS = {"Edit", "Write", "NotebookEdit"}

# Detection signals in transcript.
_SLASH_CMD_MARKERS = (
    "<command-name>/ontology-librarian",
    "/ontology-librarian",
)
_SKILL_NAME = "ontology-librarian"

# Allow-listed path prefixes / suffix patterns (no librarian required).
# Absolute-path globs; matched against the resolved, absolute path.
_ALLOW_ABS_PREFIXES = (
    "/tmp/",
    os.path.expanduser("~/.claude/"),
)

_ALLOW_PATH_SUFFIXES = ("MEMORY.md",)

# Directory segments that mark "not source code".
_ALLOW_PATH_CONTAINS = (
    "/memory/",
    "/.claude/annunaki/",
)


def _is_allowlisted(file_path: str) -> bool:
    """Return True if the path is exempt from the librarian requirement."""
    if not file_path:
        # No file_path means we cannot evaluate; default to enforcing.
        return False

    try:
        abspath = os.path.abspath(os.path.expanduser(file_path))
    except (OSError, ValueError):
        abspath = file_path

    # Absolute-prefix allow-list.
    for prefix in _ALLOW_ABS_PREFIXES:
        if abspath.startswith(prefix):
            return True

    # Suffix allow-list (exact filename, e.g. MEMORY.md).
    basename = os.path.basename(abspath)
    for suffix in _ALLOW_PATH_SUFFIXES:
        if basename == suffix:
            return True

    # Directory-segment allow-list.
    for seg in _ALLOW_PATH_CONTAINS:
        if seg in abspath:
            return True

    return False


def _content_has_librarian_signal(content) -> bool:
    """Scan a single `message.content` value for librarian signals.

    Content may be:
      - str: look for slash-command markers.
      - list[dict]: iterate blocks; check text blocks and tool_use blocks.
    """
    if isinstance(content, str):
        for marker in _SLASH_CMD_MARKERS:
            if marker in content:
                return True
        return False

    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type", "")
            if btype == "text":
                text = block.get("text", "")
                for marker in _SLASH_CMD_MARKERS:
                    if marker in text:
                        return True
            elif btype == "tool_use":
                if block.get("name") == "Skill":
                    skill = (block.get("input") or {}).get("skill", "")
                    if skill == _SKILL_NAME:
                        return True

    return False


def _transcript_has_librarian(transcript_path: str) -> bool:
    """Return True if the transcript shows a librarian consultation."""
    if not transcript_path:
        return False

    try:
        p = Path(transcript_path)
        if not p.exists():
            return False
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                t = obj.get("type", "")
                if t not in ("user", "assistant"):
                    continue
                msg = obj.get("message") or {}
                content = msg.get("content", "")
                if _content_has_librarian_signal(content):
                    return True
    except OSError:
        # If we cannot read the transcript, FAIL OPEN — do not block on our
        # own inability to read state. Parent dispatcher fail-open convention.
        return True

    return False


def _cwd_sentinel_hash(cwd: str) -> str:
    """Return the first 16 hex chars of sha1(abspath(cwd) + "\\n").

    Back-compat shim: delegates to `_consultation_sentinel.cwd_sentinel_hash`.
    The trailing-newline hash matches the shell idiom
    `pwd | sha1sum | cut -c1-16` so the librarian skill (which writes the
    sentinel from shell) and the hook (which reads it from Python) compute
    the same path.
    """
    return cwd_sentinel_hash(cwd)


def _sentinel_attests_librarian(cwd: str) -> bool:
    """Return True if a fresh cwd-keyed sentinel exists for this cwd.

    Fresh = mtime within SENTINEL_TTL_SECONDS of now. Absent, stale, or
    unreadable sentinels return False (do not attest). OSError paths fail
    open (return True) to match the transcript-scan fail-open stance.

    Per #176: the path is `.claude/.consulted/ontology-librarian/<hash>.marker`
    (was `.claude/.librarian-consulted/<hash>.marker`); the path move
    namespaces by skill so future transcript-reading hooks can reuse the
    same sentinel directory without colliding. The helper computes the
    canonical path; this function wraps it with Hook 15's specific
    fail-OPEN-on-OSError semantics.

    Per #429: when the canonical-hash marker is absent, falls back to a
    tolerant-read scan (`find_attesting_sentinel`) that accepts any fresh
    marker whose BODY records this same realpath cwd. Rescues markers
    written by ad-hoc one-liners that picked a non-canonical hash
    formula (live evidence in cedric-0066-dark-mode-tokens worktree).
    """
    if not cwd:
        return False

    import time

    try:
        sentinel = consultation_sentinel_path(cwd, _SKILL_KEY)
        if sentinel.exists():
            age = time.time() - sentinel.stat().st_mtime
            if 0 <= age <= SENTINEL_TTL_SECONDS:
                return True
        # Canonical-path miss → tolerant body-cwd scan (#429).
        if find_attesting_sentinel(cwd, _SKILL_KEY, SENTINEL_TTL_SECONDS) is not None:
            return True
        return False
    except OSError:
        # Fail open — do not block on our own inability to stat. (Preserved
        # from pre-#176 behavior; the shared helper fails CLOSED on OSError
        # for cleaner generic semantics — Hook 15 wraps it here to keep the
        # legacy fail-open stance that its tests pin.)
        return True


def _build_block_diagnostic(input_data: dict) -> dict:
    """Build a structured forensic record for a block decision.

    Captures what the hook saw at decision time so #429-class "why did
    it block?" questions are answerable from logs without rerunning the
    failing session. Every field is JSON-safe and bounded in size; OSError
    on any field-build falls back to a sentinel string rather than raising.

    Recorded fields:
      cwd, cwd_realpath, expected_sentinel_path, sentinel_exists,
      sentinel_age_s, sentinel_skill_dir, sentinel_dir_marker_count,
      transcript_path, transcript_exists, transcript_size_bytes,
      transcript_line_count, errors (list of stringified OSError per field).
    """
    import time

    diag: dict = {}
    errors: list[str] = []
    cwd = input_data.get("cwd", "") or ""
    diag["cwd"] = cwd
    try:
        diag["cwd_realpath"] = os.path.realpath(os.path.expanduser(cwd)) if cwd else ""
    except (OSError, ValueError) as e:
        diag["cwd_realpath"] = ""
        errors.append(f"realpath:{e}")

    sentinel: Path | None = None
    try:
        sentinel = consultation_sentinel_path(cwd, _SKILL_KEY) if cwd else None
    except (OSError, ValueError) as e:
        errors.append(f"sentinel_path:{e}")

    if sentinel is not None:
        diag["expected_sentinel_path"] = str(sentinel)
        diag["sentinel_skill_dir"] = str(sentinel.parent)
        try:
            exists = sentinel.exists()
            diag["sentinel_exists"] = exists
            if exists:
                age = time.time() - sentinel.stat().st_mtime
                diag["sentinel_age_s"] = round(age, 2)
                diag["sentinel_within_ttl"] = bool(0 <= age <= SENTINEL_TTL_SECONDS)
            else:
                diag["sentinel_age_s"] = None
                diag["sentinel_within_ttl"] = False
        except OSError as e:
            diag["sentinel_exists"] = None
            errors.append(f"sentinel_stat:{e}")
        try:
            if sentinel.parent.is_dir():
                diag["sentinel_dir_marker_count"] = sum(1 for _ in sentinel.parent.glob("*.marker"))
            else:
                diag["sentinel_dir_marker_count"] = 0
        except OSError as e:
            diag["sentinel_dir_marker_count"] = None
            errors.append(f"sentinel_dir_scan:{e}")

    transcript_path = input_data.get("transcript_path", "") or ""
    diag["transcript_path"] = transcript_path
    if transcript_path:
        try:
            tp = Path(transcript_path)
            t_exists = tp.exists()
            diag["transcript_exists"] = t_exists
            if t_exists:
                diag["transcript_size_bytes"] = tp.stat().st_size
                # Bounded line-count: stop at 50k to avoid runaway scan
                # cost on pathological transcripts.
                line_count = 0
                with tp.open("r", encoding="utf-8", errors="replace") as f:
                    for line_count, _ in enumerate(f, start=1):
                        if line_count >= 50000:
                            break
                diag["transcript_line_count"] = line_count
            else:
                diag["transcript_size_bytes"] = None
                diag["transcript_line_count"] = 0
        except OSError as e:
            diag["transcript_exists"] = None
            errors.append(f"transcript_read:{e}")

    if errors:
        diag["errors"] = errors[:10]
    return diag


_BLOCK_MESSAGE = (
    "BLOCKED: /ontology-librarian must be consulted before code edits in this session.\n"
    'Per CLAUDE.md § Ontology: "Every agent — orchestrator, team member, or one-off —\n'
    'MUST run /ontology-librarian {topic} before making code changes."\n'
    "Run /ontology-librarian {topic} first, then retry the edit."
)


def check(input_data: dict) -> dict | None:
    """Dispatcher-compatible entry point.

    Returns None to allow; returns a block-dict to block.
    """
    tool_name = input_data.get("tool_name", "")
    if tool_name not in _MATCHED_TOOLS:
        return None

    tool_input = input_data.get("tool_input") or {}
    # Edit/Write use file_path; NotebookEdit uses notebook_path.
    file_path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""

    if _is_allowlisted(file_path):
        return None

    # Primary signal: transcript scan.
    transcript_path = input_data.get("transcript_path", "")
    if _transcript_has_librarian(transcript_path):
        return None

    # Fallback signal: cwd-keyed sentinel (see docstring § "Sentinel fallback").
    # Survives the transcript-flush race that blocks subagents in worktrees (#169).
    cwd = input_data.get("cwd", "")
    if _sentinel_attests_librarian(cwd):
        return None

    return {
        "decision": "block",
        "reason": _BLOCK_MESSAGE,
    }


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    result = check(input_data)
    if result is None:
        sys.exit(0)

    print(json.dumps(result))
    if result.get("decision") == "block":
        # Log to Annunaki so the block shows up in /annunaki reports.
        tool_name = input_data.get("tool_name", "")
        tool_input = input_data.get("tool_input") or {}
        file_path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
        log_pretooluse_block(
            "enforce_librarian_consulted",
            f"{tool_name} {file_path}",
            result["reason"],
            tool_name=tool_name,
        )
        # Per #429: emit structured forensics on the block path so future
        # regressions show WHY the hook returned block, not just THAT it
        # did. Best-effort — never let logging crash the hook.
        try:
            log_pretooluse_diagnostic(
                "enforce_librarian_consulted",
                f"{tool_name} {file_path}",
                _build_block_diagnostic(input_data),
                tool_name=tool_name,
            )
        except Exception:  # noqa: BLE001
            pass
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
