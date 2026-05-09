#!/usr/bin/env python3
"""Tests for block_gh_pr_review — basic behavioral fixtures.

This is NOT parser-fixture coverage per the W7 audit
(`.claude/hooks/audit/parser_fixture_coverage.md` line 61), which classifies
`block_gh_pr_review` as non-parser-class (simple regex match + shell-separator
split, no structured parsing). This file closes a smaller gap: the hook had
zero test coverage at all. These fixtures pin the hook's documented behavior
and the regex's interaction with the `&&`, `||`, `|`, `;` segment-splitter.

Run: ENVIRONMENT=test python3 -m pytest .claude/hooks/tests/test_block_gh_pr_review.py -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
sys.path.insert(0, str(_HOOKS_DIR))

import block_gh_pr_review as hook  # noqa: E402


def _input(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


class PositiveMatchTests(unittest.TestCase):
    """Real `gh pr review` invocations MUST be blocked."""

    def test_bare_form(self):
        result = hook.check(_input("gh pr review 42"))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["decision"], "block")

    def test_with_approve_flag(self):
        result = hook.check(_input("gh pr review 42 --approve"))
        self.assertIsNotNone(result)

    def test_with_body_flag(self):
        result = hook.check(_input('gh pr review 42 --body "lgtm"'))
        self.assertIsNotNone(result)

    def test_chained_after_and_and(self):
        """Segment-split on `&&` must still flag a later `gh pr review`."""
        result = hook.check(_input("gh pr view 42 && gh pr review 42 --approve"))
        self.assertIsNotNone(result)

    def test_chained_after_semicolon(self):
        result = hook.check(_input("echo ready ; gh pr review 42"))
        self.assertIsNotNone(result)

    def test_chained_after_pipe(self):
        result = hook.check(_input("true | gh pr review 42"))
        self.assertIsNotNone(result)

    def test_chained_after_double_pipe(self):
        result = hook.check(_input("false || gh pr review 42"))
        self.assertIsNotNone(result)

    def test_block_reason_cites_charter(self):
        """Block message must redirect to `gh pr comment` (charter § Pull Requests)."""
        result = hook.check(_input("gh pr review 42"))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn("gh pr comment", result["reason"])


class NegativeMatchTests(unittest.TestCase):
    """Other `gh pr <subcommand>` shapes MUST NOT be blocked."""

    def test_gh_pr_comment(self):
        """Charter-required review path — explicit allow."""
        cmd = 'gh pr comment 42 --body "Requestor: A\nRequestee: B\nRequestOrReplied: Approved"'
        self.assertIsNone(hook.check(_input(cmd)))

    def test_gh_pr_edit(self):
        self.assertIsNone(hook.check(_input("gh pr edit 42 --body-file .claude/scratch/x.md")))

    def test_gh_pr_list(self):
        self.assertIsNone(hook.check(_input("gh pr list --state open")))

    def test_gh_pr_view(self):
        self.assertIsNone(hook.check(_input("gh pr view 42 --json state,mergedAt")))

    def test_gh_pr_create(self):
        self.assertIsNone(hook.check(_input("gh pr create --body-file .claude/scratch/x.md")))

    def test_gh_pr_ready(self):
        self.assertIsNone(hook.check(_input("gh pr ready 42")))

    def test_gh_issue_with_review_substring_in_body(self):
        """A `--body` literal mentioning the words is not a real invocation."""
        cmd = 'gh issue create --title x --body "see policy on gh pr review"'
        self.assertIsNone(hook.check(_input(cmd)))

    def test_non_bash_tool_passes(self):
        self.assertIsNone(
            hook.check(
                {
                    "tool_name": "Edit",
                    "tool_input": {"command": "gh pr review 42"},
                }
            )
        )

    def test_empty_command(self):
        self.assertIsNone(hook.check(_input("")))

    def test_unrelated_command(self):
        self.assertIsNone(hook.check(_input("ls -la")))

    def test_grep_for_phrase_does_not_match(self):
        """`grep 'gh pr review' file` is not an invocation — first token is grep."""
        self.assertIsNone(hook.check(_input("grep 'gh pr review' /tmp/log")))


class HeredocBoundaryTests(unittest.TestCase):
    """Document hook behavior on heredoc bodies.

    The hook splits on `&&`, `||`, `|`, `;` without heredoc-awareness. A
    heredoc body containing any of those separators will be split and each
    fragment treated as its own segment. This pins current behavior so any
    future change is intentional.
    """

    def test_heredoc_body_starting_with_phrase_no_separator(self):
        """No shell-separator inside the body → whole heredoc is one segment.

        First non-whitespace token is `cat`, so the regex does not match.
        """
        cmd = (
            "cat > /tmp/x.md <<'EOF'\n"
            "gh pr review is blocked by hook policy\n"
            "use gh pr comment instead\n"
            "EOF"
        )
        self.assertIsNone(hook.check(_input(cmd)))

    def test_heredoc_body_with_semicolon_splits_segments(self):
        """KNOWN LIMITATION: `;` inside a heredoc body splits the segment.

        If a literal `gh pr review` appears as the start of a segment after a
        `;`, even inside a heredoc body, the hook DOES block. This is
        intentional fail-closed: the hook errs on the side of blocking when
        shell-separator semantics are ambiguous. Documented for future tuning;
        no production occurrence to date.
        """
        cmd = "cat <<'EOF'\nstep 1; gh pr review is bad; step 2\nEOF"
        # Documents current behavior. If this changes, update the comment.
        result = hook.check(_input(cmd))
        self.assertIsNotNone(result)


if __name__ == "__main__":
    unittest.main()
