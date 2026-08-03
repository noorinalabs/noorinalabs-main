#!/usr/bin/env python3
"""Single source of truth for the org repo list (main#1118, audit item G6).

Before this module, the canonical repo set was retyped as a literal list in
~9 places across `.claude/lib` and `.claude/hooks` (plus assorted single-repo
mentions), each hand-copied from CLAUDE.md's `## Repository Map` table with
no shared source. One of those copies drifted — `.claude/hooks/
session_handoff.py`'s `_get_open_prs()` list omitted
`noorinalabs-isnad-ingest-platform` after the repo was added to CLAUDE.md,
so `/handoff` silently queried only 7 of 8 repos with nothing announcing the
gap (BUG-08). This module is the one place the canonical membership and
canonical order live; every other module imports from here instead of
retyping the list.

Canonical order matches CLAUDE.md's `## Repository Map` table exactly (main
first, then children in table row order), so a drift check against that
table is a pure sequence comparison — see
`.claude/lib/tests/test_org_repos.py`, which parses the table and asserts
`CHILD_REPOS` matches it row-for-row (the issue's explicit "prose→code test"
ask).

Not every consumer wants the full membership — importing this module does
NOT mean "use `ALL_REPOS`/`CHILD_REPOS` verbatim everywhere":

  * `roster_union_sync.py` deliberately EXCLUDES `noorinalabs-deploy` (it
    keeps no aggregated `roster.json`, so there is nothing to cross-check) —
    filter `CHILD_REPOS`, don't hand-list a replacement.
  * `warn_ghcr_image.py` deliberately covers ONLY the GHCR-image-publishing
    subset of children — a different axis (build/publish topology) than
    "which repos exist in the org" — so it keeps its own explicit dict
    rather than importing a list from here.

Import convention: this module has no dependencies and lives flat in
`.claude/lib/`, so `import org_repos` resolves for any caller that already
has `.claude/lib` on `sys.path` (either via `PYTHONPATH=.claude/lib`, or via
the `sys.path.insert(0, str(Path(__file__).resolve().parent.parent))`
pattern every `.claude/lib/tests/test_*.py` module uses, or via the
`.claude/hooks/*.py` two-insert pattern — own dir, then `../lib` — e.g.
`gh_quota_gate.py`).
"""

from __future__ import annotations

# GitHub org/owner every repo below lives under.
ORG = "noorinalabs"

# The parent repo this file lives in. `.gitignore`s the children below and
# clones them as independent git repos beneath it (CLAUDE.md § Architecture).
MAIN_REPO = "noorinalabs-main"

# The 7 child repos, in CLAUDE.md's `## Repository Map` table order.
CHILD_REPOS: tuple[str, ...] = (
    "noorinalabs-isnad-graph",
    "noorinalabs-user-service",
    "noorinalabs-deploy",
    "noorinalabs-design-system",
    "noorinalabs-data-acquisition",
    "noorinalabs-isnad-ingest-platform",
    "noorinalabs-landing-page",
)

# main + all 7 children: main first, then CHILD_REPOS in table order.
ALL_REPOS: tuple[str, ...] = (MAIN_REPO, *CHILD_REPOS)
