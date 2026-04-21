#!/usr/bin/env python3
"""PostToolUse hook: Ontology change tracker.

Input: PostToolUse JSON on Edit / Write (the matchers actually wired in
``.claude/settings.json``). Computes SHA256 of the modified file and
updates ``ontology/checksums.json`` with the new hash in
``last_tracked``. When ``last_tracked != last_resolved``, the file is
"dirty" and needs ontology resolution.

Handles files across all child repos under the main repo root.

Path filtering (issue #143):
  Some edits target paths that are out of scope for the ontology —
  recording them inflates the dirty-file count without representing real
  drift. The hook therefore skips:

    * Substring SKIP_PATTERNS (e.g. ``__pycache__/``, ``.git/``).
    * Paths beginning with ``/tmp/`` — ephemeral scratch (e.g. issue-body
      staging files).
    * Paths containing ``.claude/worktrees/`` — ephemeral worktree copies.
      The canonical entry for the underlying file is updated whenever the
      file is next Edit/Written directly on the main checkout (this is a
      PostToolUse hook on tool calls, NOT a git post-merge hook, so a
      squash-merge of a worktree-only PR does not by itself update the
      tracker — the next direct Edit on main does). Skipping worktree
      paths is still the right call: it prevents accumulation of stale
      paths in ``checksums.json`` after worktrees are removed, and the
      slight latency in the canonical entry's ``last_tracked`` is
      acceptable noise-vs-signal trade.
    * Paths outside the repo tree — anything not under ``REPO_ROOT`` after
      resolution (e.g. user auto-memory files at
      ``/home/.../.claude/projects/.../memory/*.md``). The ontology only
      describes this repo; out-of-tree files cannot be its source of
      truth. (Note: on macOS, ``/tmp`` is a symlink to ``/private/tmp``;
      the SKIP_PREFIXES check uses the resolved path so the filter still
      catches it.)

Exit codes:
  0 — always (advisory hook, never blocks)
"""

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CHECKSUMS_FILE = REPO_ROOT / "ontology" / "checksums.json"

# Substring patterns: skip if any appears anywhere in the file path.
SKIP_PATTERNS = [
    "ontology/checksums.json",  # Don't track ourselves
    ".claude/annunaki/errors.jsonl",
    "__pycache__/",
    ".pyc",
    "node_modules/",
    ".git/",
    ".DS_Store",
    ".claude/worktrees/",  # Ephemeral worktree copies — see module docstring
]

# Path prefixes: skip if the resolved file path starts with any of these.
SKIP_PREFIXES = ("/tmp/",)


def _should_skip(file_path: str) -> bool:
    """Return True if this file should not be tracked.

    Filters in order: substring patterns, /tmp/ prefix, then out-of-repo
    paths. See module docstring for the rationale behind each rule.
    """
    for pattern in SKIP_PATTERNS:
        if pattern in file_path:
            return True

    try:
        resolved = Path(file_path).resolve()
    except (OSError, RuntimeError):
        # Cannot resolve (e.g. broken symlink) — be conservative and skip.
        return True

    resolved_str = str(resolved)
    for prefix in SKIP_PREFIXES:
        if resolved_str.startswith(prefix):
            return True

    try:
        resolved.relative_to(REPO_ROOT)
    except ValueError:
        return True

    return False


def _compute_sha256(file_path: Path) -> str | None:
    """Compute SHA256 hash of a file. Returns None if file doesn't exist."""
    try:
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except (OSError, PermissionError):
        return None


def _relative_path(file_path: str) -> str:
    """Convert absolute path to relative from repo root."""
    try:
        return str(Path(file_path).resolve().relative_to(REPO_ROOT))
    except ValueError:
        # File is outside repo root — use absolute path as key
        return file_path


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    if tool_name not in ("Edit", "Write"):
        sys.exit(0)

    # Extract file path from tool input
    file_path = input_data.get("tool_input", {}).get("file_path", "")
    if not file_path:
        sys.exit(0)

    # Skip files that aren't relevant to ontology
    if _should_skip(file_path):
        sys.exit(0)

    # Compute hash
    sha = _compute_sha256(Path(file_path))
    if sha is None:
        sys.exit(0)

    rel_path = _relative_path(file_path)
    now = datetime.now(timezone.utc).isoformat()

    # Load existing checksums
    try:
        with open(CHECKSUMS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        data = {"version": 1, "files": {}}

    files = data.setdefault("files", {})

    # Update or create entry — preserve last_resolved from previous state
    existing = files.get(rel_path, {})
    files[rel_path] = {
        "last_tracked": sha,
        "last_resolved": existing.get("last_resolved", ""),
        "tracked_at": now,
        "resolved_at": existing.get("resolved_at", ""),
    }

    # Write back atomically-ish
    try:
        CHECKSUMS_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = CHECKSUMS_FILE.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        tmp.replace(CHECKSUMS_FILE)
    except OSError:
        pass  # Never fail the hook

    sys.exit(0)


if __name__ == "__main__":
    main()
