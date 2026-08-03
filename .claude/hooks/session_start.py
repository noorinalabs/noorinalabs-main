#!/usr/bin/env python3
"""SessionStart hook: point at /session-start; print one-line state counts.

Fires at the beginning of every Claude Code session (startup and resume).

Slimmed per main#962: this hook used to print the full 7-step imperative
protocol AND the handoff file contents (~5 KB) — all of which
`.claude/skills/session-start/SKILL.md` (the skill this hook mandates) then
restated, and whose Step 2 re-read the handoff. The skill OWNS the step
detail; this hook owns only the mandatory-first-action contract plus cheap
one-line counts (handoff pointer, ontology dirty count, annunaki error count,
wave/phase) so a session that ignores the mandate still sees the vital signs.

Exit codes:
  0 — always (informational hook, never blocks)
"""

import json
import re
import sys
from pathlib import Path

_PROJECT = Path(__file__).resolve().parent.parent.parent

# The dirty predicate (`last_tracked != last_resolved`) lives in exactly one
# place — `checksums_io.classify_entry` (#1142). This hook used to re-implement
# it inline, which made it the only correct implementation in the repo and
# therefore the one every ad-hoc reader had to reproduce from memory. Two
# consecutive sessions reproduced it wrong and both got a plausible `0`.
_LIB = _PROJECT / ".claude" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))
import checksums_io  # noqa: E402

_CHECKSUMS = _PROJECT / "ontology" / "checksums.json"
_ERRORS_LOG = _PROJECT / ".claude" / "annunaki" / "errors.jsonl"
_CROSS_REPO_STATUS = _PROJECT / "cross-repo-status.json"
# Handoff lives in-repo alongside the version-controlled memory corpus
# (#732, #741) — same gitignored file the /session-start skill reads (Step 2),
# no split-brain with the user-space auto-memory dir.
_HANDOFF = _PROJECT / ".claude" / "memory" / "session_handoff.md"


def _ontology_staleness() -> checksums_io.ChecksumsStatus | None:
    """Return the shared reader's ledger status, or None if it is unreadable.

    Delegates to `checksums_io.read_status` rather than re-deriving the dirty
    predicate here (#1142). Two consequences beyond de-duplication:

    * A malformed entry now counts as malformed, not clean. The previous
      inline version skipped non-dict entries entirely and compared
      `.get(...) != .get(...)` on the rest, so an entry missing both keys
      compared `None != None` and read as clean.
    * An unreadable ledger returns None (reported as such) instead of being
      folded into a count. `read_status` raises rather than failing open, so
      "could not read" can never surface as "0 dirty".
    """
    try:
        return checksums_io.read_status(_CHECKSUMS)
    except checksums_io.ChecksumsUnreadable:
        return None


def _annunaki_error_count() -> int:
    """Return number of lines in errors.jsonl, or -1 if missing."""
    try:
        text = _ERRORS_LOG.read_text(encoding="utf-8").strip()
        if not text:
            return 0
        return len(text.splitlines())
    except OSError:
        return -1


def _handoff_exists() -> bool:
    """True when a non-empty handoff file is present (pointer only — the
    /session-start skill's Step 2 is the single reader of its contents, #962)."""
    try:
        return bool(_HANDOFF.read_text(encoding="utf-8").strip())
    except OSError:
        return False


def _wave_phase_started(data: dict) -> tuple[str, str, str]:
    """Resolve (phase, wave, started) from a cross-repo-status.json dict.

    Reads the canonical lifecycle keys maintained by the wave skills:
      - phase   ← ``current_phase``
      - wave    ← ``current_wave`` (e.g. "wave-5")
      - started ← ``wave_<N>_started_at`` for N parsed from ``current_wave``,
                  falling back to ``wave_<N>_kicked_off_at``, then "unknown".

    The flat ``phase``/``wave``/``last_updated`` keys are NOT used as the
    source of truth — ``phase`` lags a phase behind (cross-phase key
    collision, #683) and ``wave`` does not exist (#708).
    """
    phase = data.get("current_phase", "unknown")
    wave = data.get("current_wave", "unknown")
    started = "unknown"
    if isinstance(wave, str):
        match = re.search(r"(\d+)", wave)
        if match:
            n = match.group(1)
            # `or` chains past both missing keys AND present-but-null values.
            started = (
                data.get(f"wave_{n}_started_at") or data.get(f"wave_{n}_kicked_off_at") or "unknown"
            )
    return str(phase), str(wave), started


def _wave_status() -> str | None:
    """Return a brief phase/wave summary from cross-repo-status.json, or None."""
    try:
        data = json.loads(_CROSS_REPO_STATUS.read_text(encoding="utf-8"))
        phase, wave, started = _wave_phase_started(data)
        return f"Phase {phase}, Wave {wave} (started: {started})"
    except (OSError, json.JSONDecodeError):
        return None


def main() -> None:
    overlay = _ontology_staleness()
    if overlay is None:
        ontology = "checksums.json missing or unreadable — run /ontology-rebuild"
    elif overlay.clean:
        ontology = f"current (0/{overlay.total} dirty)"
    else:
        counts = f"{len(overlay.dirty)}/{overlay.total} dirty"
        if overlay.malformed:
            counts += f", {len(overlay.malformed)} malformed"
        ontology = f"{counts} — /session-start Step 3 resolves"

    errors = _annunaki_error_count()
    annunaki = (
        "log not found (monitoring passive)"
        if errors < 0
        else f"{errors} error(s) logged — count-only; /annunaki-attack runs on demand/wave-wrapup"
    )

    try:
        handoff_path = _HANDOFF.relative_to(_PROJECT).as_posix()
    except ValueError:
        handoff_path = _HANDOFF.as_posix()
    handoff = (
        f"exists at {handoff_path} (skill Step 2 reads it)"
        if _handoff_exists()
        else "none from previous session"
    )

    lines = [
        "SESSION START — MANDATORY FIRST ACTION",
        "Run the /session-start skill NOW, before reading the user's message,",
        "responding, or running any other tool. Do NOT respond to the user",
        "until it completes. Step detail is owned by the skill",
        "(.claude/skills/session-start/SKILL.md), not this hook.",
        f"Handoff: {handoff}",
        f"Ontology overlay: {ontology}",
        f"Annunaki: {annunaki}",
        f"Wave: {_wave_status() or 'cross-repo-status.json not found or unreadable'}",
    ]
    print("\n".join(lines))


if __name__ == "__main__":
    main()
