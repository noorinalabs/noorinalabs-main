"""Tests for org_repos — the org repo-list SSOT (main#1118, audit item G6).

Covers the constant shapes (membership, no duplicates, main+children
composition) and the drift gate the issue explicitly asked for: a
prose→code test asserting `CHILD_REPOS` matches CLAUDE.md's
`## Repository Map` table, row for row.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

# Package lives at .claude/lib/org_repos.py; this test is at .claude/lib/tests/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from org_repos import ALL_REPOS, CHILD_REPOS, MAIN_REPO, ORG  # noqa: E402

# .claude/lib/tests/test_org_repos.py -> repo root is 3 parents up.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"

_TABLE_ROW_RE = re.compile(r"^\|\s*`(noorinalabs-[a-z-]+)`\s*\|", re.MULTILINE)


def _table_repos_from_claude_md(text: str) -> list[str]:
    """Backtick-quoted repo names from CLAUDE.md's Repository Map table, in row order.

    Isolates the section between the ``## Repository Map`` heading and the next
    ``## `` heading, then pulls the first (Repository) column of every data row.
    """
    match = re.search(r"## Repository Map\n(.*?)\n## ", text, re.S)
    if not match:
        return []
    return _TABLE_ROW_RE.findall(match.group(1))


class TestOrgReposConstants(unittest.TestCase):
    def test_main_repo(self) -> None:
        self.assertEqual(MAIN_REPO, "noorinalabs-main")

    def test_org(self) -> None:
        self.assertEqual(ORG, "noorinalabs")

    def test_child_repos_count(self) -> None:
        # main + 7 children per CLAUDE.md § Repository Map.
        self.assertEqual(len(CHILD_REPOS), 7)

    def test_all_repos_is_main_plus_children(self) -> None:
        self.assertEqual(ALL_REPOS, (MAIN_REPO, *CHILD_REPOS))
        self.assertEqual(len(ALL_REPOS), 8)

    def test_no_duplicates(self) -> None:
        self.assertEqual(len(set(ALL_REPOS)), len(ALL_REPOS))

    def test_all_names_prefixed(self) -> None:
        for repo in ALL_REPOS:
            self.assertTrue(repo.startswith("noorinalabs-"), repo)

    def test_main_not_in_child_repos(self) -> None:
        self.assertNotIn(MAIN_REPO, CHILD_REPOS)


class TestProseParserSelfTest(unittest.TestCase):
    """The parser helper must actually parse — not silently return [] on any
    input, which would make TestProseCodeParity below vacuously pass."""

    def test_parses_a_minimal_synthetic_table(self) -> None:
        synthetic = (
            "# Doc\n\n## Repository Map\n\n"
            "| Repository | Description | Path |\n"
            "|---|---|---|\n"
            "| `noorinalabs-foo` | Foo | `noorinalabs-foo/` |\n"
            "| `noorinalabs-bar` | Bar | `noorinalabs-bar/` |\n\n"
            "## Next Section\n\nmore text `noorinalabs-not-in-table` here\n"
        )
        self.assertEqual(
            _table_repos_from_claude_md(synthetic),
            ["noorinalabs-foo", "noorinalabs-bar"],
        )

    def test_missing_heading_returns_empty(self) -> None:
        self.assertEqual(_table_repos_from_claude_md("# Doc\n\nno such section\n"), [])


class TestProseCodeParity(unittest.TestCase):
    """G6's explicit ask: CHILD_REPOS must match CLAUDE.md's Repository Map."""

    def test_claude_md_repository_map_matches_child_repos(self) -> None:
        self.assertTrue(CLAUDE_MD.is_file(), f"CLAUDE.md not found at {CLAUDE_MD}")
        table_repos = _table_repos_from_claude_md(CLAUDE_MD.read_text(encoding="utf-8"))
        # Non-vacuous: a parse that silently found zero rows must fail loudly
        # rather than let the tuple-equality below pass on two empty sequences.
        self.assertTrue(
            table_repos,
            "parsed zero repos from CLAUDE.md's Repository Map table — "
            "has the heading or table shape moved?",
        )
        self.assertEqual(tuple(table_repos), CHILD_REPOS)


if __name__ == "__main__":
    unittest.main()
