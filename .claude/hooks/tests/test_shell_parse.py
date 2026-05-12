#!/usr/bin/env python3
"""Tests for `_shell_parse` — the shared shell-arg-aware parser helper.

Covers the public API (tokenize, strip_heredocs, iter_command_segments,
find_git_subcommand, find_gh_subcommand, extract_dash_c_pairs,
resolve_tool_cwd, is_shutdown_request_message) and the negative-match
fixtures from the sibling-bug cluster (#226 #227 #223 #216 #188 #189 #144).

Run: ENVIRONMENT=test python3 -m pytest .claude/hooks/tests/test_shell_parse.py -v
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
sys.path.insert(0, str(_HOOKS_DIR))

import _shell_parse as sp  # noqa: E402


class TokenizeTests(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(sp.tokenize("git commit -m foo"), ["git", "commit", "-m", "foo"])

    def test_quoted_value_kept_whole(self):
        # shlex absorbs the surrounding quotes; "A B" becomes one token "A B".
        self.assertEqual(
            sp.tokenize('git -c user.name="A B" commit'),
            ["git", "-c", "user.name=A B", "commit"],
        )

    def test_unquoted_value_bounded_by_whitespace(self):
        """#226 repro: bare email value does NOT slurp to EOL."""
        cmd = "git -c user.email=a@b.c commit -F /tmp/m.txt 2>&1 | tail -20"
        toks = sp.tokenize(cmd)
        # The email arrives as ONE shlex token; not slurped through the rest.
        self.assertIn("user.email=a@b.c", toks)

    def test_malformed_quote_returns_none(self):
        self.assertIsNone(sp.tokenize('git commit -m "unterminated'))


class StripHeredocsTests(unittest.TestCase):
    def test_simple_heredoc(self):
        cmd = "cat <<EOF\nbody\nEOF\necho done"
        self.assertNotIn("body", sp.strip_heredocs(cmd))

    def test_quoted_delimiter(self):
        cmd = "cat <<'EOF'\nbody --no-verify\nEOF\necho done"
        self.assertNotIn("body --no-verify", sp.strip_heredocs(cmd))

    def test_double_quoted_delimiter(self):
        cmd = 'cat <<"EOF"\ngit config foo bar\nEOF\necho done'
        self.assertNotIn("git config foo bar", sp.strip_heredocs(cmd))

    def test_dash_form(self):
        cmd = "cat <<-EOF\n\tinside\n\tEOF\necho done"
        self.assertNotIn("inside", sp.strip_heredocs(cmd))

    def test_repeated_heredocs(self):
        cmd = "cat <<EOF\nbody1 git config foo\nEOF\ncat <<EOF\nbody2 --no-verify\nEOF\necho done"
        out = sp.strip_heredocs(cmd)
        self.assertNotIn("body1", out)
        self.assertNotIn("body2", out)


class IterCommandSegmentsTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(list(sp.iter_command_segments([])), [])

    def test_single_segment(self):
        toks = ["git", "commit", "-m", "x"]
        self.assertEqual(list(sp.iter_command_segments(toks)), [toks])

    def test_split_on_amp_amp(self):
        toks = ["cd", "/foo", "&&", "git", "commit"]
        self.assertEqual(
            list(sp.iter_command_segments(toks)),
            [["cd", "/foo"], ["git", "commit"]],
        )

    def test_split_on_pipe(self):
        toks = ["echo", "x", "|", "tail"]
        self.assertEqual(
            list(sp.iter_command_segments(toks)),
            [["echo", "x"], ["tail"]],
        )

    def test_strips_leading_env_assignments(self):
        toks = ["FOO=bar", "BAR=baz", "git", "commit"]
        self.assertEqual(
            list(sp.iter_command_segments(toks)),
            [["git", "commit"]],
        )

    def test_env_only_segment_is_skipped(self):
        toks = ["FOO=bar", ";", "git", "commit"]
        self.assertEqual(
            list(sp.iter_command_segments(toks)),
            [["git", "commit"]],
        )


class FindGitSubcommandTests(unittest.TestCase):
    def test_plain_git_commit(self):
        out = sp.find_git_subcommand(["git", "commit", "-m", "x"])
        self.assertIsNotNone(out)
        assert out is not None
        globals_, rest = out
        self.assertEqual(globals_, [])
        self.assertEqual(rest, ["commit", "-m", "x"])

    def test_dash_c_globals_skipped(self):
        out = sp.find_git_subcommand(
            ["git", "-c", "user.name=A", "-c", "user.email=a@b.c", "commit"]
        )
        self.assertIsNotNone(out)
        assert out is not None
        globals_, rest = out
        self.assertEqual(globals_, ["-c", "user.name=A", "-c", "user.email=a@b.c"])
        self.assertEqual(rest, ["commit"])

    def test_dash_C_globals_skipped(self):
        out = sp.find_git_subcommand(["git", "-C", "/repo", "config", "--list"])
        self.assertIsNotNone(out)
        assert out is not None
        _globals, rest = out
        self.assertEqual(rest[0], "config")

    def test_not_git(self):
        self.assertIsNone(sp.find_git_subcommand(["echo", "git", "commit"]))

    def test_only_git_without_subcommand(self):
        self.assertIsNone(sp.find_git_subcommand(["git"]))

    def test_only_globals_no_subcommand(self):
        self.assertIsNone(sp.find_git_subcommand(["git", "-c", "user.name=A"]))


class FindGhSubcommandTests(unittest.TestCase):
    def test_gh_pr_create(self):
        out = sp.find_gh_subcommand(["gh", "pr", "create", "--repo", "x/y"])
        self.assertIsNotNone(out)
        assert out is not None
        _globals, rest = out
        self.assertEqual(rest, ["pr", "create", "--repo", "x/y"])

    def test_not_gh(self):
        self.assertIsNone(sp.find_gh_subcommand(["git", "commit"]))


class IsGhSubcommandTests(unittest.TestCase):
    """Yes/no convenience wrapper introduced for the #170 helper extraction.

    Replaces local `_is_gh_issue_create` / `_is_gh_pr_create` duplicates
    that previously lived in validate_labels and validate_branch_freshness.
    """

    def test_positive_gh_issue_create(self):
        tokens = ["gh", "issue", "create", "--title", "x"]
        self.assertTrue(sp.is_gh_subcommand(tokens, "issue", "create"))

    def test_positive_gh_pr_create(self):
        tokens = ["gh", "pr", "create", "--base", "main"]
        self.assertTrue(sp.is_gh_subcommand(tokens, "pr", "create"))

    def test_positive_at_non_start_position(self):
        """`cd x && gh issue create ...` — gh appears after segment tokens."""
        tokens = ["cd", "x", "&&", "gh", "issue", "create"]
        self.assertTrue(sp.is_gh_subcommand(tokens, "issue", "create"))

    def test_negative_wrong_verb(self):
        tokens = ["gh", "issue", "view", "42"]
        self.assertFalse(sp.is_gh_subcommand(tokens, "issue", "create"))

    def test_negative_not_gh(self):
        tokens = ["git", "commit"]
        self.assertFalse(sp.is_gh_subcommand(tokens, "issue", "create"))

    def test_negative_no_verbs_supplied(self):
        """Defensive: zero-verb call returns False (no match shape)."""
        tokens = ["gh", "issue", "create"]
        self.assertFalse(sp.is_gh_subcommand(tokens))

    def test_negative_empty_tokens(self):
        self.assertFalse(sp.is_gh_subcommand([], "issue", "create"))


class WalkFlagValuesTests(unittest.TestCase):
    """Generalized flag-walker that replaces local `_walk_flags` duplicates."""

    def test_two_token_form(self):
        tokens = ["gh", "issue", "create", "--label", "bug"]
        self.assertEqual(sp.walk_flag_values(tokens, {"--label"}), ["bug"])

    def test_equals_form(self):
        tokens = ["gh", "issue", "create", "--label=bug"]
        self.assertEqual(sp.walk_flag_values(tokens, {"--label"}), ["bug"])

    def test_short_flag_two_token(self):
        tokens = ["gh", "issue", "create", "-l", "bug"]
        self.assertEqual(sp.walk_flag_values(tokens, {"-l"}), ["bug"])

    def test_multiple_values_preserve_order(self):
        tokens = ["gh", "issue", "create", "--label", "a", "--label", "b"]
        self.assertEqual(sp.walk_flag_values(tokens, {"--label"}), ["a", "b"])

    def test_mixed_equals_and_two_token(self):
        tokens = ["gh", "issue", "create", "--label=a", "--label", "b"]
        self.assertEqual(sp.walk_flag_values(tokens, {"--label"}), ["a", "b"])

    def test_value_inside_other_flag_ignored(self):
        """A `--label` substring INSIDE the value of `--body` must NOT match.

        Critical correctness property: shlex.split has already collapsed
        `--body "...contains --label X..."` into a SINGLE token whose
        content includes `--label`, but that token is never PRECEDED by
        `--label` itself, so the walker correctly ignores it.
        """
        tokens = ["gh", "issue", "create", "--body", "see --label X for context", "--label", "real"]
        self.assertEqual(sp.walk_flag_values(tokens, {"--label"}), ["real"])

    def test_no_match_returns_empty(self):
        tokens = ["gh", "issue", "create", "--title", "no labels here"]
        self.assertEqual(sp.walk_flag_values(tokens, {"--label"}), [])

    def test_empty_tokens(self):
        self.assertEqual(sp.walk_flag_values([], {"--label"}), [])

    def test_trailing_flag_without_value(self):
        """`--label` at end of token list with no following value is ignored."""
        tokens = ["gh", "issue", "create", "--label"]
        self.assertEqual(sp.walk_flag_values(tokens, {"--label"}), [])


class FirstFlagValueTests(unittest.TestCase):
    """Convenience wrapper combining tokenize + walk_flag_values + regex fallback."""

    def test_returns_first_value(self):
        cmd = "gh pr create --base main --base develop"
        self.assertEqual(sp.first_flag_value(cmd, {"--base"}), "main")

    def test_returns_none_when_absent(self):
        cmd = "gh pr create --title foo"
        self.assertIsNone(sp.first_flag_value(cmd, {"--base"}))

    def test_equals_form(self):
        cmd = "gh pr create --base=main"
        self.assertEqual(sp.first_flag_value(cmd, {"--base"}), "main")

    def test_either_alias_matched(self):
        """`{--repo, -R}` — both aliases recognized at the first occurrence."""
        cmd = "gh pr create -R noorinalabs/main --base main"
        self.assertEqual(sp.first_flag_value(cmd, {"--repo", "-R"}), "noorinalabs/main")

    def test_regex_fallback_on_tokenize_failure(self):
        """Unbalanced quote breaks shlex; the regex fallback still picks up the flag."""
        # The trailing `"` is unbalanced — shlex.split raises ValueError, tokenize -> None.
        cmd = 'gh pr create --base main --title "broken'
        self.assertEqual(sp.first_flag_value(cmd, {"--base"}), "main")

    def test_regex_fallback_disabled_returns_none_on_failure(self):
        """Security-critical callers pass regex_fallback=False to fail closed."""
        cmd = 'gh pr create --base main --title "broken'
        self.assertIsNone(sp.first_flag_value(cmd, {"--base"}, regex_fallback=False))

    def test_longer_flag_preferred_in_regex_fallback(self):
        """Regex fallback sorts wanted by length DESC so `--repo` beats `-R` prefix collision."""
        # Construct an unbalanced-quote command (forces regex path) where
        # both --repo and -R appear; --repo wins because it's tried first.
        cmd = 'gh pr create -R short/x --repo long/y --title "unclosed'
        # Both flags are in the wanted set; the regex tries longer first.
        # The result is whichever flag's regex matches first in the string,
        # so we assert the longer-flag preference shape via direct check.
        out = sp.first_flag_value(cmd, {"--repo", "-R"})
        self.assertEqual(out, "long/y")


class ExtractDashCPairsTests(unittest.TestCase):
    def test_simple(self):
        pairs = sp.extract_dash_c_pairs(
            ["git", "-c", "user.name=Alice", "-c", "user.email=a@b.c", "commit"]
        )
        self.assertEqual(pairs, [("user.name", "Alice"), ("user.email", "a@b.c")])

    def test_quoted_value_unquoted_by_shlex(self):
        """shlex preserves spaces inside quotes as one token."""
        # Simulates the post-tokenize state of: -c user.name="Alice Bob"
        pairs = sp.extract_dash_c_pairs(["git", "-c", "user.name=Alice Bob", "commit"])
        self.assertEqual(pairs, [("user.name", "Alice Bob")])

    def test_unquoted_email_is_clean_pair(self):
        """#226 repro: unquoted bare email is correctly bounded."""
        pairs = sp.extract_dash_c_pairs(
            ["git", "-c", "user.email=parametrization+Idris.Yusuf@gmail.com", "commit"]
        )
        self.assertEqual(
            pairs,
            [("user.email", "parametrization+Idris.Yusuf@gmail.com")],
        )

    def test_no_pairs_when_no_dash_c(self):
        pairs = sp.extract_dash_c_pairs(["git", "commit", "-m", "x"])
        self.assertEqual(pairs, [])

    def test_skips_other_globals(self):
        pairs = sp.extract_dash_c_pairs(["git", "-C", "/repo", "-c", "user.name=Alice", "commit"])
        self.assertEqual(pairs, [("user.name", "Alice")])

    def test_repeated_key_returns_all_pairs_in_source_order(self):
        """API contract pin: repeated keys returned in source order; callers dedup.

        `git -c user.name=A -c user.name=B commit` is legal git (last wins).
        Helper returns ALL pairs in source order; callers needing last-wins
        do `dict(extract_dash_c_pairs(...))` (later-key overwrite-earlier in
        dict construction).
        """
        pairs = sp.extract_dash_c_pairs(["git", "-c", "user.name=A", "-c", "user.name=B", "commit"])
        self.assertEqual(pairs, [("user.name", "A"), ("user.name", "B")])
        # dict-cast gives last-wins, matching git semantics.
        self.assertEqual(dict(pairs), {"user.name": "B"})


class ResolveToolCwdTests(unittest.TestCase):
    def test_uses_input_cwd(self):
        self.assertEqual(sp.resolve_tool_cwd({"cwd": "/foo/bar"}), "/foo/bar")

    def test_falls_back_to_getcwd(self):
        result = sp.resolve_tool_cwd({})
        self.assertEqual(result, os.getcwd())

    def test_empty_string_falls_back(self):
        result = sp.resolve_tool_cwd({"cwd": ""})
        self.assertEqual(result, os.getcwd())

    def test_non_string_falls_back(self):
        result = sp.resolve_tool_cwd({"cwd": 123})
        self.assertEqual(result, os.getcwd())


class IsShutdownRequestMessageTests(unittest.TestCase):
    """#189: only structured shutdown_request JSON, not prose."""

    def test_dict_form(self):
        self.assertTrue(sp.is_shutdown_request_message({"type": "shutdown_request"}))

    def test_dict_with_other_type(self):
        self.assertFalse(sp.is_shutdown_request_message({"type": "task_complete"}))

    def test_json_string_form(self):
        self.assertTrue(
            sp.is_shutdown_request_message('{"type": "shutdown_request", "reason": "done"}')
        )

    def test_prose_with_substring(self):
        """The exact #189 false-positive: prose containing the phrase."""
        self.assertFalse(
            sp.is_shutdown_request_message(
                "Standing down. Acknowledged the shutdown_request from the lead."
            )
        )

    def test_prose_with_only_keyword(self):
        self.assertFalse(sp.is_shutdown_request_message("shutdown_request"))

    def test_empty_string(self):
        self.assertFalse(sp.is_shutdown_request_message(""))

    def test_malformed_json(self):
        self.assertFalse(sp.is_shutdown_request_message("{ not json"))

    def test_non_string_non_dict(self):
        self.assertFalse(sp.is_shutdown_request_message(123))
        self.assertFalse(sp.is_shutdown_request_message(None))


if __name__ == "__main__":
    unittest.main()
