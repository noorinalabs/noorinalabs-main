#!/usr/bin/env python3
"""Scaffold a durable ``reference`` memory from a fetched web resource (main#1004).

Token/context-efficiency Move #9. ``WebSearch → WebFetch`` is already best
practice, but ``WebFetch``'s cache lives only ~15 minutes — so a fact worth
re-reading across sessions (an API/tool doc, a spec, an external decision
rationale) gets **re-fetched every session** instead of captured durably. The
``reference`` memory type already exists for exactly this; this CLI makes
capturing into it a one-command, convention-correct action (a prose-only
convention would decay — enforcement hierarchy prefers a tool).

It writes ``.claude/memory/reference_<slug>.md`` with the standard frontmatter
(flat ``type: reference`` + ``promotion_target``/``status`` — the shape the
promotion-audit code actually reads; see the ``_TEMPLATE`` note below), a body
that records the source URL + fetch date + the extracted fact, and prints the
one-line ``MEMORY.md`` pointer to add. It **refuses to clobber** an existing file (``--force`` to
overwrite) and does **not** auto-edit ``MEMORY.md`` — placing the index pointer
(and staying within the memory budget) is a deliberate curated write, kept a
human decision on purpose (see CLAUDE.md § Project Memory).

Exit codes:
    0 — reference memory written; pointer line printed to stdout.
    2 — usage / validation error (bad slug, empty fact, missing dir).
    3 — target file exists and ``--force`` was not given (no clobber).
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# A memory slug is snake_case: lowercase alnum words joined by single underscores.
# This matches the ACTUAL corpus — all existing .claude/memory/*.md basenames use
# underscores, none use hyphens (CLAUDE.md's "kebab-slug" wording is aspirational
# and unfollowed; a tool that writes files alongside the others must match reality).
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")

# Frontmatter uses FLAT top-level keys (``type``/``promotion_target``/``status``),
# not nested ``metadata.type``. This is the CODE-correct shape: the promotion-audit
# tooling that actually consumes memory frontmatter
# (``.claude/skills/promotion-audit/helpers.py`` — ``fm.get("type", "project")``,
# ``fm.get("promotion_target", "none")``, ``fm.get("status", "active")``) reads flat
# keys ONLY and never descends into ``metadata``. A memory written with nested
# ``metadata.type`` is silently miscategorized as ``type=project`` by that code —
# so although 71/98 files (and CLAUDE.md's prose) currently use the nested form,
# the enforcement code has drifted from the docs and the majority. This tool
# matches what is *wired up*, not the prose. The corpus-wide drift is tracked by
# #1006 (not in scope here). ``promotion_target: none`` is the correct opt-out for
# an informational reference memory.
_TEMPLATE = """\
---
name: reference_{slug}
description: {description}
type: reference
promotion_target: none
status: active
---
# {title} — reference (fetched {fetched})

**Source:** {url} (fetched {fetched})

{fact}
"""


def _today_iso() -> str:
    """Today's date as ``YYYY-MM-DD`` (UTC). Isolated for test injection."""
    return datetime.now(timezone.utc).date().isoformat()


def normalize_slug(slug: str) -> str:
    """Strip a leading ``reference_`` if the caller included it; validate snake_case.

    Raises ValueError if the (stripped) slug is not snake_case — the convention
    every existing memory file uses.
    """
    stripped = slug[len("reference_") :] if slug.startswith("reference_") else slug
    if not _SLUG_RE.match(stripped):
        raise ValueError(
            f"slug must be snake_case (lowercase alnum + single underscores), got {slug!r}"
        )
    return stripped


def build_reference(
    *, slug: str, title: str, description: str, url: str, fact: str, fetched: str
) -> str:
    """Render the reference-memory file body. Pure — no filesystem side effects."""
    return _TEMPLATE.format(
        slug=slug,
        title=title,
        description=description.replace("\n", " ").strip(),
        url=url,
        fetched=fetched,
        fact=fact.strip() + "\n",
    )


def pointer_line(slug: str, title: str, hook: str) -> str:
    """The one-line MEMORY.md index pointer the caller adds by hand."""
    return f"- [{title}](reference_{slug}.md) — {hook.strip()}"


def _fact_from(args_fact: str | None) -> str:
    """Fact text from ``--fact`` or, if absent, stdin."""
    if args_fact is not None:
        return args_fact
    if not sys.stdin.isatty():
        return sys.stdin.read()
    return ""


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--slug", required=True, help="snake_case slug (a leading 'reference_' is stripped)."
    )
    parser.add_argument(
        "--title", required=True, help="Human title for the memory heading + pointer."
    )
    parser.add_argument(
        "--description", required=True, help="One-line frontmatter description (recall hint)."
    )
    parser.add_argument("--url", required=True, help="Source URL that was fetched.")
    parser.add_argument(
        "--hook",
        help="Short MEMORY.md pointer hook (defaults to the description).",
    )
    parser.add_argument(
        "--fact",
        help="The durable fact/summary body. If omitted, read from stdin.",
    )
    parser.add_argument(
        "--fetched",
        default=None,
        help="Fetch date YYYY-MM-DD (default: today, UTC).",
    )
    parser.add_argument(
        "--memory-dir",
        default=None,
        help="Memory dir (default: <repo-root>/.claude/memory, resolved from this file).",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite an existing file.")
    args = parser.parse_args(argv[1:])

    try:
        slug = normalize_slug(args.slug)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    fact = _fact_from(args.fact).strip()
    if not fact:
        print("ERROR: no fact provided (pass --fact or pipe it on stdin).", file=sys.stderr)
        return 2

    fetched = args.fetched or _today_iso()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", fetched):
        print(f"ERROR: --fetched must be YYYY-MM-DD, got {fetched!r}", file=sys.stderr)
        return 2

    if args.memory_dir:
        memory_dir = Path(args.memory_dir)
    else:
        # This file lives at <repo>/.claude/lib/capture_reference.py.
        memory_dir = Path(__file__).resolve().parents[1] / "memory"
    if not memory_dir.is_dir():
        print(f"ERROR: memory dir not found: {memory_dir}", file=sys.stderr)
        return 2

    target = memory_dir / f"reference_{slug}.md"
    if target.exists() and not args.force:
        print(
            f"ERROR: {target.name} already exists (use --force to overwrite, "
            "or update it by hand).",
            file=sys.stderr,
        )
        return 3

    content = build_reference(
        slug=slug,
        title=args.title,
        description=args.description,
        url=args.url,
        fact=fact,
        fetched=fetched,
    )
    target.write_text(content, encoding="utf-8")

    hook = args.hook or args.description
    print(f"Wrote {target}")
    print("Add this line to .claude/memory/MEMORY.md (mind the budget gate):")
    print(f"  {pointer_line(slug, args.title, hook)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
