"""Single source of truth for the charter trailer-block convention.

Why this module exists (main#932/#934, Oyunbileg Batbayar)
==========================================================

The charter defines a review comment as prose followed by a **trailer block**:
the structured fields, last, after a sole `---` line. Two hooks must agree on
what that means:

* ``validate_pr_review`` — counts verdicts (the two-reviewer gate).
* ``validate_review_comment_format`` — validates the field shape and the
  Requestor/Requestee direction.

Before this module, the scoping rules lived only in ``validate_pr_review``.
``validate_review_comment_format`` matched fields with a bare, unscoped
``re.search`` over the whole body. That single line produced **two opposite
failures**, and which one fired depended on the reviewer's sentence:

* **fail-closed** — a correctly-formed, correctly-directed verdict was BLOCKED
  when the reviewer explained the rule in prose and the prose's final token
  happened to be the PR author's surname. ``_extract_lastname`` takes the last
  token, so ``"... Requestor: Wanjiku Mwangi, Requestee: Khoury"`` yielded
  ``Khoury``, matched the branch author, and tripped the swap heuristic.
* **fail-open** — a genuinely swapped trailer PASSED whenever some earlier
  prose match produced a non-author surname first.

The obvious repair — give the format hook its own trailer scan — would leave
the charter's trailer convention defined in two hand-maintained copies. That
is precisely the rot that produced the false "Hook 4 first-matches your prose"
memory (retired; now ``feedback_pr_review_verdict_format`` §6): the rule
described in one place, implemented in another, with nothing
tying them together. So the definition is lifted here and **both hooks scope
through the one function**. A second definition should be impossible, not
kept in sync.

Placement
---------

``.claude/lib/`` by orchestrator decision (main#932). Both hooks add the lib
directory to ``sys.path`` and import from here; nothing else defines these
functions. The requirement is **singularity** — one definition, no drifting
copy — and the location makes it reachable from ``.claude/lib/`` tooling as
well as from the two hooks.

The three functions move together on purpose: ``strip_code_regions`` replaces
code spans with **spaces** rather than deleting them, precisely so that
``trailer_block_substring``'s sole-``---`` line detection still sees the same
line structure. Splitting them would silently break that invariant.
"""

from __future__ import annotations

import re

__all__ = [
    "extract_charter_field",
    "strip_code_regions",
    "trailer_block_substring",
]


def strip_code_regions(body: str) -> str:
    """Strip fenced code blocks (```…```) and inline code (`…`) from `body`.

    Returns a body where every char inside a code region is replaced with a
    space (preserving line indices for downstream regex). This prevents
    reviewer prose like `` `Requestor: (TBD)` `` from being captured as the
    actual Requestor value (#511 — Bereket-on-deploy#339 pattern).

    The replacement char is space (not empty) so any `re.search` line/column
    arithmetic remains accurate against the original `body`'s line offsets,
    making `trailer_block_substring`'s `---`-line detection unaffected.
    """
    out: list[str] = []
    i = 0
    n = len(body)
    while i < n:
        # Fenced code: ```...``` (triple-backtick on its own or with lang tag).
        if body.startswith("```", i):
            end = body.find("```", i + 3)
            if end == -1:
                # Unterminated fence — strip rest of body.
                out.append(" " * (n - i))
                break
            out.append(" " * (end + 3 - i))
            i = end + 3
            continue
        # Inline code: `...` on a single span (no newlines inside the run).
        if body[i] == "`":
            end = body.find("`", i + 1)
            if end == -1 or "\n" in body[i + 1 : end]:
                # Not a closed inline span — pass through as literal.
                out.append(body[i])
                i += 1
                continue
            out.append(" " * (end + 1 - i))
            i = end + 1
            continue
        out.append(body[i])
        i += 1
    return "".join(out)


def trailer_block_substring(body: str) -> str:
    """Return the trailer-block substring of `body` for field extraction.

    Trailer-block definition (#511):
      - If `body` contains one or more lines that are a sole `---` separator
        (charter convention for delimiting the structured-fields block), the
        trailer is everything AFTER the LAST such separator line.
      - Otherwise (legacy comments without separator), fall back to the full
        body — `extract_charter_field` then uses last-match-wins to remain
        forgiving while still avoiding most prose-above-trailer false-matches.

    The `---` must be on a line by itself (with optional leading/trailing
    whitespace) to count. Embedded `---` within a sentence does not count.
    """
    lines = body.splitlines(keepends=True)
    last_sep_idx = -1
    for idx, line in enumerate(lines):
        if line.strip() == "---":
            last_sep_idx = idx
    if last_sep_idx == -1:
        return body
    return "".join(lines[last_sep_idx + 1 :])


def extract_charter_field(field_name: str, body: str) -> str | None:
    """Extract a charter-format field value from a comment body.

    Handles markdown bold (`**Field:**`) and plain (`Field:`) variants.
    Returns the value with markdown markers and parenthetical role
    descriptions stripped. Returns None if the field is not present.

    Match-scope discipline (#511):
      - First, strip fenced (``` ... ```) and inline (`...`) code regions to
        prevent reviewer prose-quoting from being captured as a verdict field
        (Bereket-on-deploy#339 pattern).
      - Then narrow to the trailer-block substring per charter convention
        (text after the last `---` separator line). If no separator is
        present, fall back to the full body to remain backward-compatible
        with legacy verdict comments.
      - Within that scope, use LAST-MATCH-WINS so a prose mention of the
        field above the trailer block (without a separator) does not
        outscore the actual trailer line (Wanjiku-on-main#509 / Lucas-on-
        deploy#337 pattern).

    `field_name` is a parameter, so this helper answers for whatever label you
    hand it: `extract_charter_field("Verdict", body)` will happily return
    `"Approved"`. The binding to the charter's field name lives at the call
    site, never here.
    """
    scope = trailer_block_substring(strip_code_regions(body))
    pattern = rf"\*{{0,2}}{re.escape(field_name)}:\*{{0,2}}\s*(.+)"
    matches = list(re.finditer(pattern, scope))
    if not matches:
        return None
    match = matches[-1]
    value = match.group(1).strip()
    # Drop trailing content after first newline (single-line field).
    value = value.split("\n", 1)[0].strip()
    # Strip markdown bold and parenthetical role descriptions.
    value = value.strip("*").strip()
    value = re.sub(r"\s*\(.*?\)\s*$", "", value).strip()
    return value or None
