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

    def test_attached_short_flag_value(self):
        """POSIX getopt / cobra `-Rvalue` == `-R value` (main#1057).

        A single-char short flag takes an attached value. Before the fix
        `-R$DA` matched neither the exact-token nor the equals branch, so the
        value was silently dropped to `[]` — the fail-open that let a
        `gh pr merge -R$DA` skip the repo-confusion gate (sibling of #981).
        """
        self.assertEqual(sp.walk_flag_values(["gh", "-Rowner/repo"], {"-R"}), ["owner/repo"])
        self.assertEqual(sp.walk_flag_values(["gh", "-R$DA"], {"-R"}), ["$DA"])

    def test_attached_short_equals_precedes_attached_branch(self):
        """`-R=value` stays the equals form (`value`, not `=value`): the
        equals branch is evaluated before the attached-short branch."""
        self.assertEqual(sp.walk_flag_values(["gh", "-R=owner/repo"], {"-R"}), ["owner/repo"])

    def test_long_flag_never_split_on_bare_prefix(self):
        """A LONG flag must never take an attached value: `--repofoo` is NOT
        `--repo` + `foo` (attached values are single-char short flags only).
        The `len(flag) == 2` guard pins this — the security-relevant negative."""
        self.assertEqual(sp.walk_flag_values(["gh", "--repofoo"], {"--repo", "-R"}), [])
        self.assertEqual(sp.walk_flag_values(["gh", "--reponsense", "v"], {"--repo", "-R"}), [])

    def test_bare_short_flag_not_treated_as_attached(self):
        """A lone `-R` (len == 2) has no attached value → nothing captured
        via the attached branch (the exact-token branch handles two-token /
        trailing forms)."""
        self.assertEqual(sp.walk_flag_values(["gh", "-R"], {"-R"}), [])

    # -- main#1060: gh/cobra semantics hardening -----------------------------

    def test_value_less_flag_does_not_eat_next_long_flag(self):
        """A value-less `-R` immediately followed by `--add-label` must NOT
        yield `repo='--add-label'` (main#1060's motivating reproducer, filed
        during #1059 review). Real gh would error ("flag needs an argument:
        'R'"); this helper can't raise, but must not silently misroute
        either — `-R` yields nothing, and `--add-label` is still scanned as
        its own flag."""
        tokens = [
            "gh",
            "issue",
            "edit",
            "42",
            "-R",
            "--add-label",
            "wave-26",
            "--add-label",
            "p3-wave-9",
        ]
        self.assertEqual(sp.walk_flag_values(tokens, {"-R", "--repo"}), [])
        self.assertEqual(
            sp.walk_flag_values(tokens, {"--add-label"}),
            ["wave-26", "p3-wave-9"],
        )

    def test_value_less_flag_does_not_eat_next_short_flag(self):
        """Same hazard, short-flag-shaped successor."""
        self.assertEqual(sp.walk_flag_values(["gh", "-R", "-l", "bug"], {"-R"}), [])
        self.assertEqual(sp.walk_flag_values(["gh", "-R", "-l", "bug"], {"-l"}), ["bug"])

    def test_value_looking_like_negative_number_still_rejected(self):
        """A flag-shaped successor is rejected even when it isn't itself in
        `wanted` — the guard is "does this token look like a flag", not "is
        this token itself a wanted flag"."""
        self.assertEqual(sp.walk_flag_values(["gh", "-R", "--unknown-flag"], {"-R"}), [])

    def test_bare_dash_after_flag_is_still_a_valid_value(self):
        """A LONE `-` (the conventional stdin/positional sentinel) is NOT
        flag-shaped, so it is still accepted as a value — only genuine
        multi-character `-`-prefixed tokens are rejected."""
        self.assertEqual(sp.walk_flag_values(["gh", "-F", "-"], {"-F"}), ["-"])

    def test_double_dash_terminator_stops_scan(self):
        """A literal `--` (POSIX end-of-options) stops the scan entirely —
        a `--repo`/`-R` appearing after it is positional in real gh/cobra,
        never a flag (main#1060 reproducer #2)."""
        tokens = ["gh", "issue", "edit", "42", "--add-label", "wave-26", "--", "--repo", "x/y"]
        self.assertEqual(sp.walk_flag_values(tokens, {"--repo", "-R"}), [])
        # Flags BEFORE the terminator are unaffected.
        self.assertEqual(sp.walk_flag_values(tokens, {"--add-label"}), ["wave-26"])

    def test_double_dash_terminator_with_no_flags_after_is_a_noop(self):
        tokens = ["gh", "issue", "edit", "42", "--repo", "x/y", "--"]
        self.assertEqual(sp.walk_flag_values(tokens, {"--repo"}), ["x/y"])

    def test_repeated_flag_returns_both_in_source_order(self):
        """`walk_flag_values` itself does not pick a winner for a repeated
        flag — it returns every value in source order (main#1060 finding
        #3). Callers needing gh's real last-flag-wins semantics for a
        single-value flag take `values[-1]` themselves (see
        `_repo_flag_parse.extract_repo`)."""
        tokens = ["gh", "issue", "edit", "42", "-R", "a/b", "-R", "c/d"]
        self.assertEqual(sp.walk_flag_values(tokens, {"-R", "--repo"}), ["a/b", "c/d"])


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


class ExtractLeadingCdTargetTests(unittest.TestCase):
    """#521: recover a worktree subagent's real cwd from a leading `cd`."""

    def test_simple_cd_and_gh(self):
        self.assertEqual(
            sp.extract_leading_cd_target("cd /home/u/wt && gh pr create"),
            "/home/u/wt",
        )

    def test_no_cd_returns_none(self):
        self.assertIsNone(sp.extract_leading_cd_target("gh pr create --title t"))

    def test_relative_cd_ignored(self):
        """Relative cd targets are ambiguous (relative to the wrong stdin cwd)."""
        self.assertIsNone(sp.extract_leading_cd_target("cd subdir && gh pr create"))

    def test_last_absolute_cd_wins(self):
        self.assertEqual(
            sp.extract_leading_cd_target("cd /a && cd /b && gh pr create"),
            "/b",
        )

    def test_cd_inside_quoted_body_is_not_a_segment(self):
        """A `cd` mention inside a flag value must not be treated as a real cd."""
        cmd = 'gh pr create --body "first cd /ghost then build"'
        self.assertIsNone(sp.extract_leading_cd_target(cmd))

    def test_multi_arg_cd_ignored(self):
        """`cd -P /x` is a 3-token segment — skipped rather than mis-parsed."""
        self.assertIsNone(sp.extract_leading_cd_target("cd -P /x && gh pr create"))

    def test_unparseable_command_returns_none(self):
        self.assertIsNone(sp.extract_leading_cd_target('cd /x && echo "unbalanced'))


class ResolveInvocationCwdTests(unittest.TestCase):
    """#521: invocation-cwd resolution prefers an existing `cd` target."""

    def test_existing_cd_target_wins_over_stdin_cwd(self):
        # The cwd field is the (wrong) orchestrator dir; the cd target is the
        # subagent's real worktree. An existing absolute cd target wins.
        real_dir = str(Path(__file__).resolve().parent)  # guaranteed to exist
        input_data = {
            "tool_input": {"command": f"cd {real_dir} && gh pr create"},
            "cwd": "/some/orchestrator/dir",
        }
        self.assertEqual(sp.resolve_invocation_cwd(input_data), real_dir)

    def test_nonexistent_cd_target_falls_back_to_stdin_cwd(self):
        input_data = {
            "tool_input": {"command": "cd /no/such/dir/here && gh pr create"},
            "cwd": "/orchestrator",
        }
        self.assertEqual(sp.resolve_invocation_cwd(input_data), "/orchestrator")

    def test_no_cd_falls_back_to_stdin_cwd(self):
        input_data = {
            "tool_input": {"command": "gh pr create"},
            "cwd": "/orchestrator",
        }
        self.assertEqual(sp.resolve_invocation_cwd(input_data), "/orchestrator")

    def test_no_cd_no_cwd_falls_back_to_getcwd(self):
        input_data = {"tool_input": {"command": "gh pr create"}}
        self.assertEqual(sp.resolve_invocation_cwd(input_data), os.getcwd())

    def test_missing_command_falls_back_to_stdin_cwd(self):
        input_data = {"tool_input": {}, "cwd": "/orchestrator"}
        self.assertEqual(sp.resolve_invocation_cwd(input_data), "/orchestrator")


class ResolveRepoShortNameTests(unittest.TestCase):
    """#650: resolve the ambient repo NAME from the invocation cwd's origin."""

    _INPUT = {"tool_input": {"command": "gh issue edit 1 --remove-label p4-wave-5"}, "cwd": "/x"}

    def test_scp_form_url(self):
        self.assertEqual(
            sp.resolve_repo_short_name(
                self._INPUT, git_runner=lambda _c: "git@github.com:noorinalabs/noorinalabs-main.git"
            ),
            "noorinalabs-main",
        )

    def test_https_form_url_no_dotgit(self):
        self.assertEqual(
            sp.resolve_repo_short_name(
                self._INPUT,
                git_runner=lambda _c: "https://github.com/noorinalabs/noorinalabs-deploy\n",
            ),
            "noorinalabs-deploy",
        )

    def test_https_form_url_with_dotgit(self):
        self.assertEqual(
            sp.resolve_repo_short_name(
                self._INPUT,
                git_runner=lambda _c: (
                    "https://github.com/noorinalabs/noorinalabs-design-system.git"
                ),
            ),
            "noorinalabs-design-system",
        )

    def test_trailing_slash_tolerated(self):
        self.assertEqual(
            sp.resolve_repo_short_name(
                self._INPUT,
                git_runner=lambda _c: "https://github.com/noorinalabs/noorinalabs-main/\n",
            ),
            "noorinalabs-main",
        )

    def test_runner_returns_none_yields_none(self):
        self.assertIsNone(sp.resolve_repo_short_name(self._INPUT, git_runner=lambda _c: None))

    def test_runner_returns_empty_yields_none(self):
        self.assertIsNone(sp.resolve_repo_short_name(self._INPUT, git_runner=lambda _c: ""))

    def test_runner_receives_invocation_cwd(self):
        """The runner must be called with the resolved invocation cwd (the
        `cd <dir>` recovery path, #521), not a hardcoded dir."""
        real_dir = str(Path(__file__).resolve().parent)
        seen = {}

        def runner(cwd):
            seen["cwd"] = cwd
            return "git@github.com:noorinalabs/noorinalabs-main.git"

        input_data = {
            "tool_input": {"command": f"cd {real_dir} && gh issue edit 1 --remove-label p4-wave-5"},
            "cwd": "/some/orchestrator/dir",
        }
        sp.resolve_repo_short_name(input_data, git_runner=runner)
        self.assertEqual(seen["cwd"], real_dir)


class RepoShortNameFromFlagValueTests(unittest.TestCase):
    """#985: extract the repo SHORT NAME from a `-R`/`--repo` flag value, and
    fail closed (None) on an unexpanded `$VAR` / command substitution (#981)."""

    def test_owner_name_returns_name(self):
        self.assertEqual(
            sp.repo_short_name_from_flag_value("noorinalabs/noorinalabs-main"),
            "noorinalabs-main",
        )

    def test_owner_name_dotgit_stripped(self):
        self.assertEqual(
            sp.repo_short_name_from_flag_value("noorinalabs/noorinalabs-deploy.git"),
            "noorinalabs-deploy",
        )

    def test_https_url_returns_name(self):
        self.assertEqual(
            sp.repo_short_name_from_flag_value(
                "https://github.com/noorinalabs/noorinalabs-design-system"
            ),
            "noorinalabs-design-system",
        )

    def test_trailing_slash_tolerated(self):
        self.assertEqual(
            sp.repo_short_name_from_flag_value("noorinalabs/noorinalabs-main/"),
            "noorinalabs-main",
        )

    def test_unexpanded_variable_returns_none(self):
        """The #981 caveat: shlex leaves `$DA` / `${REPO}` literal. Coercing it
        into a repo name would misroute the gh call — so return None (the caller
        fails closed)."""
        for v in ("$DA", "${REPO}", "noorinalabs/$REPO", "noorinalabs/${R}"):
            with self.subTest(v=v):
                self.assertIsNone(sp.repo_short_name_from_flag_value(v))

    def test_command_substitution_returns_none(self):
        for v in ("$(echo noorinalabs/x)", "`echo noorinalabs/x`"):
            with self.subTest(v=v):
                self.assertIsNone(sp.repo_short_name_from_flag_value(v))

    def test_whitespace_bearing_value_returns_none(self):
        """A value with internal whitespace is a captured non-flag fragment
        (e.g. an attached-short false positive), never a valid repo ref."""
        self.assertIsNone(sp.repo_short_name_from_flag_value(" foo"))
        self.assertIsNone(sp.repo_short_name_from_flag_value("owner/na me"))

    def test_empty_returns_none(self):
        self.assertIsNone(sp.repo_short_name_from_flag_value(""))


class MemoizedParseMutationSafetyTests(unittest.TestCase):
    """#1113: the parse primitives are memoized with `functools.lru_cache`.

    The critical hazard is a naive cache that hands every caller the SAME
    mutable list object: one caller mutating it (append/pop/index-assign)
    would silently corrupt the value every OTHER hook then reads for the same
    command. These tests pin the copy-at-boundary contract — mutating a
    returned value must never change what the next identical call returns —
    and that repeated calls are still value-equal (memoization is correct).
    """

    def test_tokenize_result_is_fresh_list_each_call(self):
        cmd = "git -c user.name=A commit -m msg"
        a = sp.tokenize(cmd)
        b = sp.tokenize(cmd)
        self.assertEqual(a, b)
        # Distinct objects — a shared cached list would be the SAME object.
        self.assertIsNot(a, b)

    def test_tokenize_mutation_does_not_leak_into_cache(self):
        cmd = "git commit -m first"
        first = sp.tokenize(cmd)
        expected = ["git", "commit", "-m", "first"]
        self.assertEqual(first, expected)
        # Mutate the returned list every which way.
        first.append("--injected")
        first[0] = "CLOBBERED"
        del first[1]
        # A fresh call must be pristine — the cache was not corrupted.
        self.assertEqual(sp.tokenize(cmd), expected)

    def test_tokenize_none_result_still_memoized_and_safe(self):
        # Unbalanced quote → None; cached None must stay None (no crash on copy).
        bad = 'git commit -m "unterminated'
        self.assertIsNone(sp.tokenize(bad))
        self.assertIsNone(sp.tokenize(bad))

    def test_strip_heredocs_memoized_value_stable(self):
        cmd = "cat <<EOF\nbody git commit\nEOF\necho done"
        first = sp.strip_heredocs(cmd)
        self.assertNotIn("body git commit", first)
        # str is immutable — repeated calls return an equal value.
        self.assertEqual(sp.strip_heredocs(cmd), first)

    def test_normalize_command_separators_memoized_value_stable(self):
        cmd = "cd /x && gh issue edit 1 --add-label foo"
        first = sp.normalize_command_separators(cmd)
        self.assertEqual(sp.normalize_command_separators(cmd), first)
        # Quoted separators stay data, even through the cache.
        self.assertEqual(
            sp.normalize_command_separators('gh pr create --body "a && b"'),
            sp.normalize_command_separators('gh pr create --body "a && b"'),
        )

    @unittest.skipUnless(sp.bashlex_available(), "bashlex not installed — AST path inactive")
    def test_iter_command_segments_ast_result_is_fresh_each_call(self):
        cmd = "git commit -m x && echo done"
        a = sp.iter_command_segments_ast(cmd)
        b = sp.iter_command_segments_ast(cmd)
        self.assertEqual(a, b)
        self.assertIsNot(a, b)  # fresh outer list
        if a:
            self.assertIsNot(a[0], b[0])  # fresh inner segment lists

    @unittest.skipUnless(sp.bashlex_available(), "bashlex not installed — AST path inactive")
    def test_iter_command_segments_ast_mutation_does_not_leak_into_cache(self):
        cmd = "git commit -m first && echo two"
        first = sp.iter_command_segments_ast(cmd)
        expected = sp.iter_command_segments_ast(cmd)  # pristine snapshot to compare against
        self.assertEqual(first, expected)
        # Mutate the outer list AND an inner segment.
        first.append(["INJECTED"])
        first[0].append("--clobber")
        first[0][0] = "CLOBBERED"
        # A fresh call must be pristine — neither the outer list nor any inner
        # segment leaked a mutable alias into the cache.
        self.assertEqual(sp.iter_command_segments_ast(cmd), expected)


class StripCommandPrefixes(unittest.TestCase):
    """main#1141 — leading wrappers / compound keywords must not hide a command.

    `find_git_subcommand` / `find_gh_subcommand` keyed on token 0 being
    literally `git` / `gh`, so `timeout 45 gh …` and the `do`-prefixed body of
    a `for … ; do … ; done` loop resolved to None and every consuming hook —
    the kickoff-comment poster AND the blocking gates on the same primitive —
    silently did nothing.
    """

    def test_bare_command_unchanged(self) -> None:
        self.assertEqual(
            sp.strip_command_prefixes(["gh", "issue", "edit"]), ["gh", "issue", "edit"]
        )

    def test_empty_segment(self) -> None:
        self.assertEqual(sp.strip_command_prefixes([]), [])

    def test_timeout_duration_positional(self) -> None:
        self.assertEqual(
            sp.strip_command_prefixes(["timeout", "45", "gh", "pr", "list"]), ["gh", "pr", "list"]
        )

    def test_timeout_with_flags(self) -> None:
        self.assertEqual(
            sp.strip_command_prefixes(["timeout", "-k", "5", "--foreground", "2m", "gh", "pr"]),
            ["gh", "pr"],
        )

    def test_timeout_equals_form_flag(self) -> None:
        self.assertEqual(
            sp.strip_command_prefixes(["timeout", "--kill-after=5", "45", "gh", "pr"]),
            ["gh", "pr"],
        )

    def test_compound_leaders(self) -> None:
        for leader in ("do", "then", "else", "if", "elif", "while", "until", "!", "{", "("):
            with self.subTest(leader=leader):
                self.assertEqual(sp.strip_command_prefixes([leader, "gh", "pr"]), ["gh", "pr"])

    def test_nested_wrappers(self) -> None:
        self.assertEqual(
            sp.strip_command_prefixes(["do", "timeout", "45", "nohup", "gh", "pr"]),
            ["gh", "pr"],
        )

    def test_env_assignments_and_flags(self) -> None:
        self.assertEqual(
            sp.strip_command_prefixes(["env", "-u", "PAGER", "GH_PAGER=cat", "gh", "pr"]),
            ["gh", "pr"],
        )

    def test_sudo_user_flag(self) -> None:
        self.assertEqual(
            sp.strip_command_prefixes(["sudo", "-u", "ci", "git", "commit"]), ["git", "commit"]
        )

    def test_double_dash_ends_wrapper_options(self) -> None:
        self.assertEqual(sp.strip_command_prefixes(["env", "--", "gh", "pr"]), ["gh", "pr"])

    def test_non_wrapper_head_is_not_stripped(self) -> None:
        """The allowlist is the whole safety property.

        A loose "find `gh` anywhere in the segment" scan would re-introduce the
        data-position false-positive class this module exists to prevent — the
        #118/#134/#144/#188/#189/#216/#223/#226/#227 bug trail. `echo`, `printf`
        and friends take DATA, not a command, so they are never stripped.
        """
        for head in ("echo", "printf", "cat", "grep", "python3"):
            with self.subTest(head=head):
                seg = [head, "gh", "issue", "edit", "5"]
                self.assertEqual(sp.strip_command_prefixes(seg), seg)

    def test_for_keyword_is_not_a_leader(self) -> None:
        """`for` is followed by a VARIABLE NAME, not a command."""
        seg = ["for", "n", "in", "1114", "1116"]
        self.assertEqual(sp.strip_command_prefixes(seg), seg)

    def test_does_not_mutate_input(self) -> None:
        seg = ["timeout", "45", "gh", "pr"]
        sp.strip_command_prefixes(seg)
        self.assertEqual(seg, ["timeout", "45", "gh", "pr"])


class FindSubcommandThroughPrefixes(unittest.TestCase):
    """The wrapper tolerance must reach the two public finders (main#1141)."""

    def test_gh_behind_timeout(self) -> None:
        found = sp.find_gh_subcommand(["timeout", "45", "gh", "issue", "edit", "1114"])
        self.assertEqual(found, ([], ["issue", "edit", "1114"]))

    def test_gh_in_loop_body(self) -> None:
        found = sp.find_gh_subcommand(["do", "gh", "issue", "edit", "1114"])
        self.assertEqual(found, ([], ["issue", "edit", "1114"]))

    def test_git_behind_timeout_reaches_the_identity_gate(self) -> None:
        """`timeout 60 git commit` previously walked past commit-identity validation."""
        found = sp.find_git_subcommand(["timeout", "60", "git", "-c", "user.name=A", "commit"])
        self.assertEqual(found, (["-c", "user.name=A"], ["commit"]))

    def test_gh_as_data_still_not_found(self) -> None:
        self.assertIsNone(sp.find_gh_subcommand(["echo", "gh", "issue", "edit", "1114"]))


if __name__ == "__main__":
    unittest.main()
