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
from pathlib import Path

_PROJECT = Path(__file__).resolve().parent.parent.parent
_CHECKSUMS = _PROJECT / "ontology" / "checksums.json"
_ERRORS_LOG = _PROJECT / ".claude" / "annunaki" / "errors.jsonl"
_CROSS_REPO_STATUS = _PROJECT / "cross-repo-status.json"
# Handoff lives in-repo alongside the version-controlled memory corpus
# (#732, #741) — same gitignored file the /session-start skill reads (Step 2),
# no split-brain with the user-space auto-memory dir.
_HANDOFF = _PROJECT / ".claude" / "memory" / "session_handoff.md"


def _ontology_staleness() -> tuple[int, int]:
    """Return (dirty_count, total_count) from checksums.json."""
    try:
        data = json.loads(_CHECKSUMS.read_text(encoding="utf-8"))
        # Nested format: {version, description, files: {...}}
        data = data.get("files", data)
        dirty = sum(
            1
            for v in data.values()
            if isinstance(v, dict) and v.get("last_tracked") != v.get("last_resolved")
        )
        return dirty, len(data)
    except (OSError, json.JSONDecodeError):
        return -1, 0


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
    dirty, total = _ontology_staleness()
    if dirty < 0:
        ontology = "checksums.json missing — run /ontology-rebuild"
    elif dirty == 0:
        ontology = f"current (0/{total} dirty)"
    else:
        ontology = f"{dirty}/{total} dirty — /session-start Step 3 resolves"

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
