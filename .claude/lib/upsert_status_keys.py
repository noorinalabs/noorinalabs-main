#!/usr/bin/env python3
"""Upsert top-level keys in cross-repo-status.json preserving compact-inline shape.

The skill ecosystem (/wave-kickoff, /wave-start) writes that file with deliberate
mixed style: top-level wave_{N}_* keys are compact single-liners, older
wave_*_scope blocks are pretty-indented. A naive `jq ... > tmp && mv` round-trip
reformats every compact line to jq's default pretty form, doubling the file
length and producing a 500+ line cosmetic diff per wave.

This helper does targeted text-level upsert:
  - If the key exists at top level → replace its line in place.
  - If the key does not exist → insert a new compact-inline line right after
    the most-recent wave_{N}_* sibling (or before the closing `}`).

Validates JSON before AND after the rewrite so a malformed write is caught.

Invocation:
  upsert_status_keys.py <path> <key>=<json-encoded-value> [<key>=<json-encoded-value> ...]

Example:
  upsert_status_keys.py cross-repo-status.json \
    wave_5_scope_reconciled_at='"2026-05-05T22:31:00Z"' \
    wave_5_scope_reconciliation_note='"manual run"'

Each VALUE must be a self-contained JSON literal (string/number/bool/array/object).
Strings include their quotes — pass `'"foo"'` from the shell.
"""

import json
import re
import sys
from pathlib import Path


def _is_top_level_position(text: str, position: int) -> bool:
    """Return True iff `position` in `text` is at JSON top-level depth.

    Walks the text from the start tracking bracket depth and JSON string
    state. Depth-1 (i.e., directly inside the outermost `{...}`) is what
    "top-level sibling" means for cross-repo-status.json. Positions inside
    nested objects/arrays or inside string values return False.

    This is the structural check that catches the bug class where the
    regex sibling-finder happens to match a key NAME that's nested inside
    a multi-line value (e.g., `wave_11_inner_key` at 2-space indent inside
    `wave_11_scope: {...}`). Without this check the helper would insert a
    new top-level key in the middle of a value, producing either invalid
    JSON or a logical/text divergence caught only by the post-write
    validation (which then aborts the entire upsert batch).

    Performance: O(position) per call — for cross-repo-status.json
    (~2700 lines, ~108KB) a single check is ~108K char-iterations, well
    under 10ms even on slow hardware. Called once per sibling-finder
    candidate, so worst case is ~108K × N candidates; N is typically 1–5
    so the total per-upsert cost remains negligible.
    """
    depth = 0
    in_string = False
    escape = False
    i = 0
    while i < position and i < len(text):
        c = text[i]
        if escape:
            escape = False
        elif c == "\\" and in_string:
            escape = True
        elif c == '"':
            in_string = not in_string
        elif not in_string:
            if c in "{[":
                depth += 1
            elif c in "}]":
                depth -= 1
        i += 1
    # Depth 1 means we're directly inside the outermost object's body.
    return depth == 1 and not in_string


def _find_value_end(text: str, opener_match_end: int) -> int:
    """Given the regex-match end of a top-level key:value opener line,
    return the position immediately AFTER that key's value terminates
    (including trailing `,` if present).

    For a single-line value (line ends with `,` or `]` or `}` inline),
    `opener_match_end` is already past the value — returned as-is.

    For a multi-line value (line ends with `{` or `[`), scans forward
    tracking bracket depth and JSON string-escape state until depth
    returns to 0, then optionally consumes a trailing `,`.

    This is the fix for main#332: the prior implementation treated
    every wave_N_* sibling-finder match as the value's end position,
    which inserted INSIDE multi-line arrays/objects (e.g., wave_8_work
    or wave_8_carry_forward in the P3W8 reproducer).
    """
    line_start = text.rfind("\n", 0, opener_match_end) + 1
    line_text = text[line_start:opener_match_end].rstrip()
    if not line_text.endswith(("[", "{")):
        return opener_match_end

    depth = 1
    in_string = False
    escape = False
    pos = opener_match_end
    while pos < len(text):
        c = text[pos]
        if escape:
            escape = False
        elif c == "\\" and in_string:
            escape = True
        elif c == '"':
            in_string = not in_string
        elif not in_string:
            if c in "{[":
                depth += 1
            elif c in "}]":
                depth -= 1
                if depth == 0:
                    end = pos + 1
                    if end < len(text) and text[end] == ",":
                        end += 1
                    return end
        pos += 1
    raise ValueError(f"unterminated multi-line value starting at position {opener_match_end}")


def upsert_top_level_key(text: str, key: str, json_value: str) -> str:
    """Replace `"<key>": ...,` line in place, or insert a new line if absent.

    Insertion point: after the last existing key whose top-level name matches
    `wave_<N>_*` for the same wave number embedded in `key` (best-effort sibling
    grouping). Handles multi-line array/object siblings correctly — insertion
    is placed AFTER the sibling's structural close, not after the opening
    line (main#332 fix).

    Both the existing-key match AND the sibling-finder match are filtered
    by `_is_top_level_position` — a regex match whose position is nested
    inside a multi-line value (e.g., `wave_11_inner_key` at 2-space indent
    inside `wave_11_scope: {...}`) is rejected so insertions never land
    mid-value. This is the fix for main#456 — the regex sibling-finder
    pre-#456 would match nested keys and insert ON TOP of them, producing
    either invalid JSON or a logical/text divergence aborted by the
    post-write validation.

    Falls back to inserting right after the opening `{` line if no sibling
    exists.
    """
    line_re = re.compile(r'^(  )"' + re.escape(key) + r'":\s.*?,?\s*$', re.MULTILINE)
    new_line = f'  "{key}": {json_value},'
    # Replace-in-place: walk every match and pick the first one that's at
    # top-level depth. The pre-#456 code took the first regex match
    # unconditionally; that mis-matched nested keys whose NAME happened to
    # equal `key` (e.g., a top-level `wave_11_meta_issue` upsert mis-matching
    # a nested `wave_11_meta_issue` inside a wave_11_scope dict).
    for m in line_re.finditer(text):
        if not _is_top_level_position(text, m.start()):
            continue
        existing = m.group(0)
        last_existing = existing.rstrip()
        if last_existing.endswith(","):
            replacement = new_line
        else:
            replacement = new_line.rstrip(",")
        return text[: m.start()] + replacement + text[m.end() :]

    wave_num_match = re.match(r"wave_(\d+)_", key)
    if wave_num_match:
        sibling_re = re.compile(
            r'^(  )"wave_' + re.escape(wave_num_match.group(1)) + r'_[^"]+":.*$',
            re.MULTILINE,
        )
        # Filter to top-level matches only; the pre-#456 code took ALL
        # matches including nested wave_N_* names inside value dicts.
        siblings = [m for m in sibling_re.finditer(text) if _is_top_level_position(text, m.start())]
        if siblings:
            last = siblings[-1]
            value_end = _find_value_end(text, last.end())
            # If the previous sibling was the JSON-final key (no trailing
            # comma after its value), we must add a comma to it AND drop
            # the trailing comma from our new line so the new key becomes
            # the new last. Otherwise we'd emit `prev_key: prev_value\n
            # new_key: new_value,\n}` which is missing the comma between
            # the two existing pairs.
            prev_has_trailing_comma = value_end > 0 and text[value_end - 1] == ","
            if prev_has_trailing_comma:
                return text[:value_end] + "\n" + new_line + text[value_end:]
            return text[:value_end] + "," + "\n" + new_line.rstrip(",") + text[value_end:]

    open_brace = text.find("{\n")
    if open_brace < 0:
        raise ValueError("could not locate opening `{` line for insertion")
    insertion_point = open_brace + 2
    return text[:insertion_point] + new_line + "\n" + text[insertion_point:]


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2

    path = Path(argv[1])
    pairs = []
    for arg in argv[2:]:
        if "=" not in arg:
            print(f"ERROR: argument {arg!r} is not key=value", file=sys.stderr)
            return 2
        k, _, raw = arg.partition("=")
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError as exc:
            print(f"ERROR: value for {k} is not valid JSON: {exc}", file=sys.stderr)
            return 2
        pairs.append((k, raw, decoded))

    text = path.read_text()
    parsed = json.loads(text)

    for key, json_value, decoded in pairs:
        text = upsert_top_level_key(text, key, json_value)
        parsed[key] = decoded

    try:
        reparsed = json.loads(text)
    except json.JSONDecodeError as exc:
        # Surface the offending key=value pairs so the issue filer can
        # paste them straight into a reproducer (main#456 follow-up).
        key_repr = ", ".join(f"{k}={raw[:80]}" for k, raw, _ in pairs)
        print(
            f"ERROR: text-level upsert produced invalid JSON: {exc}\n"
            f"  This usually means the helper's sibling-finder mis-located\n"
            f"  the insertion point inside a multi-line array/object value\n"
            f"  (main#332/#456 reproducer class). File the failing input as\n"
            f"  an issue with the offending key=value upsert command.\n"
            f"  Offending pairs: {key_repr}",
            file=sys.stderr,
        )
        return 1

    if reparsed != parsed:
        # Pinpoint which key diverged so reviewers can read the bug without
        # diffing the full file (main#456 follow-up).
        diverged_keys = sorted(set(reparsed.keys()) ^ set(parsed.keys()))
        # Also catch same-key different-value divergence.
        for k in set(reparsed.keys()) & set(parsed.keys()):
            if reparsed[k] != parsed[k]:
                diverged_keys.append(k)
        key_repr = ", ".join(f"{k}={raw[:80]}" for k, raw, _ in pairs)
        print(
            f"ERROR: text-level upsert diverged from logical upsert; aborting write.\n"
            f"  Diverged keys: {sorted(set(diverged_keys))}\n"
            f"  Offending pairs (this call): {key_repr}\n"
            f"  This usually means a previous key in the same call was\n"
            f"  inserted at the wrong position (main#456 sibling-finder bug).",
            file=sys.stderr,
        )
        return 1

    path.write_text(text)
    for key, _, _ in pairs:
        print(f"  upserted: {key}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
