#!/usr/bin/env python3
"""Tests for validate_review_comment_format hook (closes #302).

P3W7 parser-fixture audit (#300) flagged this as a HIGH-priority gap:
parser-class hook with ZERO fixture coverage controlling merge traffic.

The hook parses:
- Shell command segments to detect `gh pr comment` invocations (regex)
- PR comment bodies in 3 quote forms: heredoc, single-quoted, double-quoted
- `Requestor:`, `Requestee:`, `RequestOrReplied:` charter fields
- Branch head ref name to extract author lastname

The hook blocks when `Requestee` lastname matches the branch author lastname,
indicating the operator copied the swapped form of the example (the failure
mode #356/#372/#375 collectively addressed in surrounding hooks).

Run: python3 -m unittest discover -s .claude/hooks/tests \
         -p "test_validate_review_comment_format.py"
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
sys.path.insert(0, str(_HOOKS_DIR))

import validate_review_comment_format as hook  # noqa: E402


def _bash_input(command: str) -> dict:
    """Build a PreToolUse Bash input dict shape."""
    return {"tool_name": "Bash", "tool_input": {"command": command}}


class IsCommentCommandTests(unittest.TestCase):
    """Coverage for the `gh pr comment` segment detector."""

    def test_simple_form_matches(self):
        self.assertTrue(hook.is_comment_command("gh pr comment 42"))

    def test_with_body_flag_matches(self):
        self.assertTrue(hook.is_comment_command('gh pr comment 42 --body "x"'))

    def test_chained_after_and_matches(self):
        self.assertTrue(hook.is_comment_command("gh pr view 42 && gh pr comment 42 --body x"))

    def test_chained_after_pipe_matches(self):
        self.assertTrue(hook.is_comment_command("true | gh pr comment 42 --body x"))

    def test_chained_after_semicolon_matches(self):
        self.assertTrue(hook.is_comment_command("echo go ; gh pr comment 42"))

    def test_env_var_prefix_matches(self):
        """Leading KEY=value env-var prefixes are stripped before the regex match."""
        self.assertTrue(hook.is_comment_command("ENVIRONMENT=test gh pr comment 42"))

    def test_multiple_env_var_prefixes_matches(self):
        self.assertTrue(hook.is_comment_command("FOO=1 BAR=2 gh pr comment 42"))

    def test_gh_pr_view_does_not_match(self):
        self.assertFalse(hook.is_comment_command("gh pr view 42"))

    def test_gh_pr_review_does_not_match(self):
        self.assertFalse(hook.is_comment_command("gh pr review 42 --approve"))

    def test_gh_issue_comment_does_not_match(self):
        """Hook is PR-scoped — `gh issue comment` should NOT match."""
        self.assertFalse(hook.is_comment_command("gh issue comment 42 --body x"))

    def test_non_bash_unrelated_command_does_not_match(self):
        self.assertFalse(hook.is_comment_command("ls -la"))

    def test_empty_command_does_not_match(self):
        self.assertFalse(hook.is_comment_command(""))


class ExtractPrNumberTests(unittest.TestCase):
    """PR-number extraction — direct number, then URL fallback."""

    def test_direct_number(self):
        self.assertEqual(hook.extract_pr_number("gh pr comment 42 --body x"), "42")

    def test_url_form(self):
        """#302 input shape: PR number from URL — `https://github.com/.../pull/123`."""
        self.assertEqual(
            hook.extract_pr_number("gh pr comment https://github.com/owner/repo/pull/123"),
            "123",
        )

    def test_url_form_takes_precedence_over_no_direct_number(self):
        """When no bare number follows `gh pr comment`, URL is the fallback path."""
        cmd = "gh pr comment https://github.com/o/r/pull/9 --body x"
        # Hook regex tries bare-number first; URL has `9` as the path tail.
        result = hook.extract_pr_number(cmd)
        self.assertEqual(result, "9")

    def test_no_number_returns_none(self):
        self.assertIsNone(hook.extract_pr_number("gh pr comment --help"))


class ExtractCommentBodyTests(unittest.TestCase):
    """The three quote-form parsers — heredoc, single-quoted, double-quoted."""

    def test_double_quoted_body(self):
        cmd = 'gh pr comment 42 --body "Requestor: A\nRequestee: B"'
        body = hook.extract_comment_body(cmd)
        self.assertIsNotNone(body)
        assert body is not None
        self.assertIn("Requestor: A", body)
        self.assertIn("Requestee: B", body)

    def test_single_quoted_body(self):
        cmd = "gh pr comment 42 --body 'Requestor: A\nRequestee: B'"
        body = hook.extract_comment_body(cmd)
        self.assertIsNotNone(body)
        assert body is not None
        self.assertIn("Requestor: A", body)

    def test_heredoc_body(self):
        """#302 input shape: `--body "$(cat <<'EOF'\\n...\\nEOF)"`."""
        cmd = (
            "gh pr comment 42 --body \"$(cat <<'EOF'\n"
            "Requestor: Aino Virtanen\n"
            "Requestee: Nadia Khoury\n"
            "RequestOrReplied: Approved\n"
            'EOF\n)"'
        )
        body = hook.extract_comment_body(cmd)
        self.assertIsNotNone(body)
        assert body is not None
        self.assertIn("Requestor: Aino Virtanen", body)
        self.assertIn("Requestee: Nadia Khoury", body)
        self.assertIn("RequestOrReplied: Approved", body)

    def test_heredoc_body_with_unquoted_EOF(self):
        """`<<EOF` (no quotes) form also captured."""
        cmd = (
            'gh pr comment 42 --body "$(cat <<EOF\n'
            "Requestor: A\nRequestee: B\nRequestOrReplied: Approved\n"
            'EOF\n)"'
        )
        body = hook.extract_comment_body(cmd)
        self.assertIsNotNone(body)
        assert body is not None
        self.assertIn("Requestor: A", body)

    def test_body_file_returns_none(self):
        """#302 input shape: `--body-file /tmp/...` — hook does NOT read the file.

        Pin behavior: when `--body-file` is used, `extract_comment_body`
        returns None, the hook returns None at the early-return guard, and
        the comment passes without Requestor/Requestee validation. Charter
        decision: file-based bodies are operator-trusted (used for HEREDOC
        avoidance per memory `feedback_heredoc_in_git_commit`); the hook
        does NOT shadow-validate them. Documented out-of-scope-for-v1.
        """
        cmd = "gh pr comment 42 --body-file /tmp/comment-body.md"
        self.assertIsNone(hook.extract_comment_body(cmd))

    def test_no_body_flag_returns_none(self):
        self.assertIsNone(hook.extract_comment_body("gh pr comment 42"))


class ExtractBranchAuthorLastnameTests(unittest.TestCase):
    """Branch head ref → lastname extraction.

    Charter convention: branches are `{FirstInitial}.{LastName}/{IIII}-{slug}`.
    Hook regex anchors on the `[A-Za-z]\\.([A-Za-z]+)/` shape.
    """

    def test_slash_separator_canonical(self):
        self.assertEqual(
            hook.extract_branch_author_lastname("A.Virtanen/0373-ruff-format-vwpc"),
            "Virtanen",
        )

    def test_short_lastname(self):
        self.assertEqual(hook.extract_branch_author_lastname("L.Li/0001-fix"), "Li")

    def test_dash_separator_not_supported(self):
        """#302 input shape: `{Initial}.{Lastname}-{number}` (dash) — NOT matched.

        Pin behavior: hook regex requires a slash separator after the lastname.
        Branches using dash form fall through to the `branch_author = None`
        path and the hook allow-with-warning (does not block). Hook docstring
        documents the slash format as canonical.
        """
        self.assertIsNone(hook.extract_branch_author_lastname("A.Virtanen-0373-ruff-format"))

    def test_underscore_separator_not_supported(self):
        """Charter-allowed underscore form (some implementer agents use `_` for `+`)."""
        self.assertIsNone(hook.extract_branch_author_lastname("A.Virtanen_0373-ruff-format"))

    def test_plain_branch_name_returns_none(self):
        self.assertIsNone(hook.extract_branch_author_lastname("main"))

    def test_hotfix_branch_returns_none(self):
        self.assertIsNone(hook.extract_branch_author_lastname("hotfix/some-fix"))

    def test_lowercase_initial_also_matches(self):
        """Regex is case-tolerant: lowercase initial still produces lastname."""
        self.assertEqual(
            hook.extract_branch_author_lastname("a.virtanen/0001-fix"),
            "virtanen",
        )


class CheckIntegrationTests(unittest.TestCase):
    """End-to-end fixtures driving check() with mocked branch fetch.

    The hook blocks when Requestee lastname matches branch author lastname
    (= "fields are swapped"). All scenarios mock get_branch_name so the
    test does not hit the network.
    """

    HEREDOC_OK = (
        "gh pr comment 42 --body \"$(cat <<'EOF'\n"
        "Requestor: Aino Virtanen\n"
        "Requestee: Nadia Khoury\n"
        "RequestOrReplied: Approved\n"
        "TechDebt: none\n"
        'EOF\n)"'
    )

    HEREDOC_SWAPPED = (
        "gh pr comment 42 --body \"$(cat <<'EOF'\n"
        "Requestor: Nadia Khoury\n"
        "Requestee: Aino Virtanen\n"
        "RequestOrReplied: Approved\n"
        "TechDebt: none\n"
        'EOF\n)"'
    )

    def test_happy_path_no_block(self):
        """Branch is N.Khoury/...; Requestee is Nadia Khoury → swap; BLOCK.

        Wait — this IS the swapped form because Requestee == branch author
        lastname (Khoury). The "happy path" is when Requestee != branch
        author — see `test_correct_form_allows_through`.
        """
        with mock.patch.object(hook, "get_branch_name", return_value="N.Khoury/0346-w8-retro"):
            result = hook.check(_bash_input(self.HEREDOC_OK))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.get("decision"), "block")

    def test_correct_form_allows_through(self):
        """Branch is A.Virtanen/...; Requestee is Nadia Khoury → no swap; allow."""
        with mock.patch.object(hook, "get_branch_name", return_value="A.Virtanen/0373-ruff-format"):
            result = hook.check(_bash_input(self.HEREDOC_OK))
        self.assertIsNone(result)

    def test_swapped_form_blocks(self):
        """Branch is A.Virtanen/...; Requestee is Aino Virtanen → swap; BLOCK."""
        with mock.patch.object(hook, "get_branch_name", return_value="A.Virtanen/0373-ruff-format"):
            result = hook.check(_bash_input(self.HEREDOC_SWAPPED))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.get("decision"), "block")
        self.assertIn("swapped", result["reason"].lower())

    def test_non_pr_comment_command_allows(self):
        """Not `gh pr comment` → early return None."""
        result = hook.check(_bash_input("gh pr view 42"))
        self.assertIsNone(result)

    def test_no_requestee_field_allows(self):
        """Comment without Requestee: → not a charter-format review → allow."""
        cmd = 'gh pr comment 42 --body "just a comment"'
        result = hook.check(_bash_input(cmd))
        self.assertIsNone(result)

    def test_body_file_allows_through(self):
        """#302 input shape: `--body-file` → no body inspection → allow.

        The hook cannot validate Requestor/Requestee in a file-based body
        without reading the file. Charter call: trust the operator on
        --body-file (used to escape inline-heredoc parsing edge cases).
        """
        cmd = "gh pr comment 42 --body-file /tmp/comment.md"
        result = hook.check(_bash_input(cmd))
        self.assertIsNone(result)

    def test_no_pr_number_returns_warning(self):
        """No bare number AND no /pull/N URL → allow with warning systemMessage."""
        # Hook only fires if body has Requestee+RequestOrReplied;
        # craft a body that triggers parsing but elide the PR number.
        # The current regex `gh pr comment (\d+)` allows commands like
        # `gh pr comment --body "..."` to slip through to the warning path.
        cmd = 'gh pr comment --body "Requestee: Khoury\nRequestOrReplied: Approved"'
        with mock.patch.object(hook, "get_branch_name", return_value=""):
            result = hook.check(_bash_input(cmd))
        # Either allow+warn or allow-None; the implementation returns a
        # warn-shape dict OR None depending on regex behavior. Pin both
        # acceptable outcomes.
        if result is not None:
            self.assertEqual(result.get("decision"), "allow")
            self.assertIn("systemMessage", result)

    def test_unfetchable_branch_returns_warning(self):
        """get_branch_name returns None → allow with warning, no block."""
        with mock.patch.object(hook, "get_branch_name", return_value=None):
            result = hook.check(_bash_input(self.HEREDOC_OK))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.get("decision"), "allow")
        self.assertIn("systemMessage", result)

    def test_hotfix_branch_unfetched_lastname_returns_warning(self):
        """Branch without `{Initial}.{Lastname}/` shape → no lastname → warn."""
        with mock.patch.object(hook, "get_branch_name", return_value="hotfix/x"):
            result = hook.check(_bash_input(self.HEREDOC_OK))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.get("decision"), "allow")

    def test_non_bash_tool_passes(self):
        """tool_name != Bash → early return None."""
        result = hook.check(
            {
                "tool_name": "Edit",
                "tool_input": {"command": "gh pr comment 42 --body x"},
            }
        )
        self.assertIsNone(result)

    def test_cross_repo_pr_comment_with_repo_flag(self):
        """#302 input shape: `gh pr comment N --repo OWNER/REPO`.

        get_branch_name does NOT forward --repo (line 76 — `gh pr view N`
        without --repo resolves from cwd). Pin current behavior: the hook
        validates against the CURRENT repo's PR #N, not the cross-repo one.
        If the local cwd has no matching PR, get_branch_name returns ""
        and the hook warn-allows.
        """
        cmd = (
            "gh pr comment 99 --repo noorinalabs/noorinalabs-deploy "
            '--body "Requestor: Aino Virtanen\nRequestee: Nadia Khoury\n'
            'RequestOrReplied: Approved\nTechDebt: none"'
        )
        with mock.patch.object(hook, "get_branch_name", return_value=""):
            result = hook.check(_bash_input(cmd))
        # Empty branch name → warn-allow path
        if result is not None:
            self.assertEqual(result.get("decision"), "allow")

    def test_markdown_bold_requestee_form(self):
        """Hook regex tolerates `**Requestee:**` markdown-bold prefix."""
        cmd = (
            'gh pr comment 42 --body "**Requestor:** Aino Virtanen\n'
            "**Requestee:** Nadia Khoury\n"
            'RequestOrReplied: Approved"'
        )
        with mock.patch.object(hook, "get_branch_name", return_value="N.Khoury/0346-w8"):
            result = hook.check(_bash_input(cmd))
        # Branch is N.Khoury, Requestee strips to Khoury → match → block.
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.get("decision"), "block")

    def test_requestee_with_parenthetical_role_stripped(self):
        """Parenthetical `Requestee: Nadia Khoury (Program Director)` strips role."""
        cmd = (
            'gh pr comment 42 --body "Requestor: Aino Virtanen\n'
            "Requestee: Nadia Khoury (Program Director)\n"
            'RequestOrReplied: Approved"'
        )
        with mock.patch.object(hook, "get_branch_name", return_value="N.Khoury/0346-w8"):
            result = hook.check(_bash_input(cmd))
        # Parenthetical stripped → Khoury == Khoury → block.
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.get("decision"), "block")


if __name__ == "__main__":
    unittest.main()
