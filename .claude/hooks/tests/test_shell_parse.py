#!/usr/bin/env python3
"""Tests for `_shell_parse` — the shared shell-arg-aware parser helper.

Covers the public API (tokenize, strip_heredocs, iter_command_segments,
find_git_subcommand, find_gh_subcommand, extract_dash_c_pairs,
resolve_tool_cwd, is_shutdown_request_message) and the negative-match
fixtures from the sibling-bug cluster (#226 #227 #223 #216 #188 #189 #144).

Shell-truth tests (main#1141 review; oracle widened to both shells in #1151)
===========================================================================

`CdRoutingAgainstShellTruth` does not compare the resolver to an expected
literal — it runs each shape in a REAL shell and takes the resulting cwd as
ground truth. Everything else in this module asserts against expected output,
which is fine for pure token functions but cannot catch a resolver whose model
of the shell is simply wrong (it can only catch one that disagrees with
someone's belief about it). Two families of main#1151 survived this suite for
exactly that reason, and the method caught a round-3 test of mine that pinned a
misroute as correct.

**The oracle is BOTH `bash` and `zsh` (`SHELLS`).** main#1141 ran bash only —
CI's shell — and documented the gap in prose. main#1151 closes it: every shape
is executed under both, and the safety property is

    resolved is None  OR  resolved == truth(bash) == truth(zsh)

so a shape whose behaviour is shell-DEPENDENT can no longer be adopted as a
resolver invariant by passing under bash alone. `command cd /x` is the known
divergence (bash moves the shell, zsh does not); the resolver claims nothing
for it, pinned by `test_shell_dependent_shape_is_not_relied_on`. The other
load-bearing facts — an exec-wrapper cannot carry the `cd` BUILTIN, and a
one-shot `FOO=1` prefix does NOT stop `cd` from moving the shell — are
asserted in both shells rather than trusted.

Run: ENVIRONMENT=test python3 -m pytest .claude/hooks/tests/test_shell_parse.py -v
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
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


class StripLockstepAcrossSegmentConsumers(unittest.TestCase):
    """main#1141 review MUST-FIX — every command-position keyer must strip.

    `find_git_subcommand` stripped and `extract_dash_c_pairs` did not, while
    `validate_commit_identity` calls BOTH on the SAME segment: the commit was
    recognized but its `-c` pairs came back empty, so a fully compliant
    `timeout 60 git -c user.name=… -c user.email=… commit` was BLOCKED for a
    missing flag the operator had passed. The suite was green with and
    without the fix, which is why 21/21 CI and a 25-shape adversarial pass
    both missed it — hence these tests.
    """

    IDENTITY = ["-c", "user.name=Nino Kavtaradze", "-c", "user.email=n@example.com"]
    EXPECTED = [("user.name", "Nino Kavtaradze"), ("user.email", "n@example.com")]

    def test_dash_c_pairs_bare(self) -> None:
        seg = ["git", *self.IDENTITY, "commit", "-m", "msg"]
        self.assertEqual(sp.extract_dash_c_pairs(seg), self.EXPECTED)

    def test_dash_c_pairs_behind_wrappers(self) -> None:
        """Whole `_COMMAND_PREFIX_WRAPPERS` table, not just `timeout`."""
        for prefix in (
            ["timeout", "60"],
            ["timeout", "-k", "5", "60"],
            ["env", "FOO=1"],
            ["nice", "-n", "5"],
            ["nohup"],
            ["command"],
            ["sudo", "-u", "ci"],
            ["do"],
            ["do", "timeout", "60"],
        ):
            with self.subTest(prefix=" ".join(prefix)):
                seg = [*prefix, "git", *self.IDENTITY, "commit", "-m", "msg"]
                self.assertEqual(sp.extract_dash_c_pairs(seg), self.EXPECTED)

    def test_dash_c_pairs_and_find_git_subcommand_agree(self) -> None:
        """The invariant itself: both helpers see the same command, or neither.

        A future segment-consuming helper that forgets the strip fails here.
        """
        for prefix in ([], ["timeout", "60"], ["env", "FOO=1"], ["do"], ["nice", "-n", "5"]):
            with self.subTest(prefix=" ".join(prefix) or "(bare)"):
                seg = [*prefix, "git", *self.IDENTITY, "commit", "-m", "msg"]
                found = sp.find_git_subcommand(seg)
                self.assertIsNotNone(found)
                assert found is not None
                self.assertEqual(found[1][0], "commit")
                # Recognized as a commit => its identity flags MUST be readable.
                self.assertEqual(sp.extract_dash_c_pairs(seg), self.EXPECTED)

    def test_wrapped_commit_without_identity_still_yields_nothing(self) -> None:
        """The strip must not invent pairs — an identity-less commit stays empty."""
        for prefix in (["timeout", "60"], ["env", "FOO=1"], ["do"]):
            with self.subTest(prefix=" ".join(prefix)):
                self.assertEqual(
                    sp.extract_dash_c_pairs([*prefix, "git", "commit", "-m", "msg"]), []
                )

    def test_non_wrapper_head_yields_no_pairs(self) -> None:
        """`echo git -c user.name=X commit` is data, not a commit."""
        self.assertEqual(sp.extract_dash_c_pairs(["echo", "git", *self.IDENTITY, "commit"]), [])

    def test_cd_target_behind_compound_leader_is_NOT_recovered(self) -> None:
        """RETRACTED in review round 3 — this test asserted the wrong thing.

        Round 2 argued that since `find_gh_subcommand` can see the `gh` inside
        a loop, the `cd` beside it should be recovered too. That reasoning was
        wrong: it treats a gate matcher and a routing resolver as the same
        kind of consumer. Recovering a `cd` from ANY compound body also
        recovers it from a never-taken `then` body, which misroutes — a live
        bug, on the #981/#985 path, versus a speculative loop-cd shape with no
        observed failure.

        `extract_leading_cd_target` therefore strips NOTHING — `cd` must be
        token 0 of its segment. Both prefix families are disqualified, for two
        different reasons: a compound LEADER guards a body that may not run,
        and a command-prefix WRAPPER cannot carry `cd` at all, because `cd` is
        a shell builtin (`env FOO=1 cd /x` leaves the shell where it was, in
        bash and zsh alike). The loop case staying unrecovered is the accepted
        cost — separating a loop body that runs from a `then` body that does
        not needs block-closure tracking, which is not worth it.

        Kept as an explicit non-goal rather than deleted, so the round-2
        argument is not re-derived by the next reader. See `GuardedCdMustNotRoute`.
        """
        self.assertIsNone(
            sp.extract_leading_cd_target(
                "for r in a ; do cd /tmp ; gh issue edit 1 --add-label x ; done"
            )
        )

    def test_cd_target_bare_still_works(self) -> None:
        self.assertEqual(sp.extract_leading_cd_target("cd /tmp && gh pr create"), "/tmp")

    def test_cd_target_relative_still_ignored(self) -> None:
        """Relative targets are ambiguous (they'd resolve against the wrong cwd)."""
        self.assertIsNone(sp.extract_leading_cd_target("cd relative && gh pr create"))


class CdRoutingAgainstShellTruth(unittest.TestCase):
    """`extract_leading_cd_target` vs what a REAL SHELL actually does.

    Method requirement from the main#1141 review, and it earned its keep
    immediately. These tests do not compare the resolver against its own
    expected output — each shape is run in a real `bash` with the `gh` node
    replaced by `pwd`, and the printed directory is ground truth. Testing a
    resolver against itself cannot find a resolver that is wrong, which is
    how two families of this bug survived the previous suite.

    It caught one of my own round-3 tests asserting a MISROUTE: I had pinned
    `env FOO=1 cd /tmp && gh pr create` -> `/tmp`. The shell disagrees. `cd`
    is a shell BUILTIN, so an exec-wrapper (`env`, `timeout`, `nice`,
    `nohup`) runs a subprocess and the calling shell never moves — asserted
    below. The resolver would have claimed a directory the command provably
    never entered.

    THE SAFETY PROPERTY, and why it is not plain equality:

        resolved is None  OR  resolved == shell_truth

    Under-recovery (None when the shell did move) is ACCEPTED — the caller
    falls back to the invocation cwd, which is the pre-main#1141 behaviour.
    Over-recovery, naming a directory the command never entered, is the bug:
    three hooks on this chain WRITE, so a misroute is an unrecoverable write
    into the wrong repository.
    """

    MARKER = "gh issue edit 5 --add-label wave-29"

    # Both shells are exercised for every shape (main#1151). `bash` is what CI
    # runs; `zsh` is the actual harness shell the hooks see commands from. A
    # shape whose truth DIFFERS between them has no single answer and the
    # resolver must claim nothing for it — see
    # `test_shell_dependent_shape_is_not_relied_on`.
    #
    # `zsh` is INSTALLED by the CI pytest job so both halves really run there;
    # the `which` filter exists only so a bare checkout without zsh degrades to
    # the bash-only oracle instead of erroring. It must never be the reason CI
    # is green — if the CI install step is dropped, this silently narrows.
    SHELLS = tuple(s for s in ("bash", "zsh") if shutil.which(s))

    _start: str
    _dest: str
    _nested: str
    _other: str
    _script: str

    @classmethod
    def setUpClass(cls) -> None:
        cls._start = tempfile.mkdtemp(prefix="cdroute-start-")
        cls._dest = tempfile.mkdtemp(prefix="cdroute-dest-")
        cls._other = tempfile.mkdtemp(prefix="cdroute-other-")
        # A real subdirectory of _start, standing in for the org's nested
        # child repos (`noorinalabs-main/noorinalabs-deploy/`): `cd START &&
        # cd NESTED` lands in a DIFFERENT repository than START.
        cls._nested = os.path.join(cls._start, "child-repo")
        os.makedirs(cls._nested, exist_ok=True)
        # A sourceable script that moves the shell without the command line
        # ever containing the token `cd`.
        cls._script = os.path.join(cls._start, "goto.sh")
        with open(cls._script, "w", encoding="utf-8") as fh:
            fh.write(f"cd {cls._other}\n")

    @classmethod
    def tearDownClass(cls) -> None:
        for d in (cls._start, cls._dest, cls._other):
            shutil.rmtree(d, ignore_errors=True)

    def _expand(self, template: str, marker: str) -> str:
        return (
            template.replace("DEST", self._dest)
            .replace("START", self._start)
            .replace("OTHER", self._other)
            .replace("SCRIPT", self._script)
            .replace("NESTED", "child-repo")
            .replace("MARKER", marker)
        )

    def _shell_truth(self, template: str, shell: str = "bash") -> str | None:
        """Directory the shell is actually in where the gh node sits.

        None means the gh node never executes at all in that shape.
        """
        cmd = self._expand(template, "pwd")
        out = subprocess.run(
            [shell, "-c", cmd], cwd=self._start, capture_output=True, text=True, timeout=30
        )
        printed = out.stdout.strip().splitlines()
        return printed[-1] if printed else None

    def _resolved(self, template: str) -> str | None:
        return sp.extract_leading_cd_target(self._expand(template, self.MARKER))

    def _assert_never_misroutes(self, template: str) -> None:
        """THE safety property, checked against BOTH shells.

            resolved is None  OR  resolved == shell_truth(bash) == shell_truth(zsh)

        Under-recovery is accepted; naming a directory the command never
        entered — in EITHER shell — is the bug.
        """
        resolved = self._resolved(template)
        if resolved is None:
            return  # under-recovery: caller falls back to the invocation cwd
        for shell in self.SHELLS:
            truth = self._shell_truth(template, shell)
            self.assertEqual(
                resolved,
                truth,
                f"resolver claims {resolved!r} but {shell} runs the gh node in "
                f"{truth!r} for: {template}",
            )

    # --- all seven leader shapes from the review, plus the brace group ---

    LEADER_SHAPES = [
        "if [ -f /nonexistent ] ; then cd DEST ; fi ; MARKER",
        "if false ; then cd DEST ; fi ; MARKER",
        "if false ; then true ; else cd DEST ; fi ; MARKER",
        "for r in a ; do cd DEST ; done ; MARKER",
        "for r in ; do cd DEST ; done ; MARKER",
        "while false ; do cd DEST ; done ; MARKER",
        "( cd DEST ) ; MARKER",
        "true || { cd DEST ; } ; MARKER",
        "false || { cd DEST ; } ; MARKER",
    ]

    def test_leader_shapes_never_misroute(self) -> None:
        for template in self.LEADER_SHAPES:
            with self.subTest(shape=template):
                self._assert_never_misroutes(template)

    def test_subshell_cd_does_not_escape(self) -> None:
        """`( cd DEST )` DOES run the cd — it just dies with the subshell."""
        template = "( cd DEST ) ; MARKER"
        self.assertEqual(self._shell_truth(template), self._start)
        self.assertIsNone(self._resolved(template))

    # --- wrappers: `cd` is a BUILTIN, so these never move the shell ---

    WRAPPER_SHAPES = [
        "env FOO=1 cd DEST ; MARKER",
        "timeout 5 cd DEST ; MARKER",
        "nice -n 5 cd DEST ; MARKER",
        "nohup cd DEST ; MARKER",
    ]

    def test_wrapped_cd_never_misroutes(self) -> None:
        for template in self.WRAPPER_SHAPES:
            with self.subTest(shape=template):
                self._assert_never_misroutes(template)

    def test_exec_wrapper_provably_cannot_carry_cd(self) -> None:
        """The fact the resolver must respect, asserted against the shell itself."""
        for template in self.WRAPPER_SHAPES:
            with self.subTest(shape=template):
                self.assertEqual(
                    self._shell_truth(template),
                    self._start,
                    "an exec-wrapper cannot carry the `cd` builtin — if this ever "
                    "changes, the resolver's no-strip rule needs revisiting",
                )
                self.assertIsNone(self._resolved(template))

    def test_shell_dependent_shape_is_not_relied_on(self) -> None:
        """`command cd /x` moves the shell in bash but NOT in zsh.

        The harness shell is zsh, so this shape has no single truth. The
        resolver must therefore claim nothing for it — which it does for free,
        since it strips no prefixes at all. Pinned so a future widening cannot
        quietly adopt a bash-only behaviour as an invariant (module docstring
        § Shell-truth tests).

        main#1151 asserts the DIVERGENCE itself rather than only asserting the
        resolver's silence: if the two shells ever converge, the reason this
        shape is excluded has changed and someone should re-decide it here.
        """
        template = "command cd DEST ; MARKER"
        self.assertIsNone(self._resolved(template))
        if "zsh" in self.SHELLS:
            self.assertEqual(self._shell_truth(template, "bash"), self._dest)
            self.assertEqual(self._shell_truth(template, "zsh"), self._start)

    # --- the shapes that MUST still resolve ---

    UNGUARDED_SHAPES = [
        "cd DEST && MARKER",
        "cd DEST ; MARKER",
        "cd /var && cd DEST && MARKER",
    ]

    def test_unguarded_cd_resolves_exactly(self) -> None:
        for template in self.UNGUARDED_SHAPES:
            with self.subTest(shape=template):
                self.assertEqual(self._resolved(template), self._shell_truth(template))
                self.assertEqual(self._resolved(template), self._dest)

    def test_relative_target_ignored(self) -> None:
        """Relative targets would resolve against the (wrong) stdin cwd."""
        self.assertIsNone(sp.extract_leading_cd_target("cd relative && gh pr create"))

    # --- gates keep their conservative reach; only routing opts out ---

    def test_gates_still_see_guarded_bodies(self) -> None:
        found = sp.find_gh_subcommand(["then", "gh", "pr", "review", "5"])
        self.assertEqual(found, ([], ["pr", "review", "5"]))
        self.assertEqual(
            sp.extract_dash_c_pairs(["do", "git", "-c", "user.name=A", "commit"]),
            [("user.name", "A")],
        )
        self.assertEqual(
            sp.extract_dash_c_pairs(["timeout", "60", "git", "-c", "user.name=A", "commit"]),
            [("user.name", "A")],
        )

    def test_compound_leaders_flag_is_honored(self) -> None:
        seg = ["then", "cd", "/tmp"]
        self.assertEqual(sp.strip_command_prefixes(seg), ["cd", "/tmp"])
        self.assertEqual(sp.strip_command_prefixes(seg, compound_leaders=False), seg)

    # --- main#1151: the two families, now CLOSED by the bashlex-AST scan ---
    #
    # These were `KNOWN_GAP_SHAPES` / `test_known_gap_main_1151_still_misroutes`,
    # a characterization test that PINNED the misroute so the gap stayed visible
    # in the suite. Its own instruction on closure was "delete this test and fold
    # the shape into test_leader_shapes_never_misroute" — done, with the
    # explicit-None assertions below kept so a regression names the family it
    # reopened rather than surfacing as a generic misroute.

    FAMILY_A_SHAPES = [
        # A `cd` guarded by a short-circuit operator. `iter_command_segments`
        # splits on `||`, so the `cd` is at token 0 of its own segment and NO
        # leader-stripping rule could ever reach it — the reason this needed the
        # AST rather than another entry in `_COMPOUND_LEADERS`.
        "true || cd DEST ; MARKER",
        "true || cd DEST && MARKER",
        # The braced variant never misrouted (the `{` made it a 3-token
        # segment). Kept adjacent so the two are not confused again: repairing
        # the braced shape proves nothing about family A.
        "true || { cd DEST ; } ; MARKER",
        # `&&` after a FAILING command is the same class in the other polarity.
        "false && cd DEST ; MARKER",
        # LEADING element is itself a `cd`, so phase 1's `prev_op` guard — not
        # phase 2 — is what closes these. Without such a shape that guard is
        # INERT: every other family-A fixture breaks out of phase 1 at `true`
        # before the guard is reached, so deleting it left the suite green
        # while `cd A || cd B && gh` reopened a real misroute to B (#1156
        # merge gate). `cd START` succeeds, so `cd DEST` never runs.
        "cd START || cd DEST && MARKER",
        "cd START || cd DEST ; MARKER",
    ]

    FAMILY_B_SHAPES = [
        # A `cd` positioned AFTER the gh node. Despite the resolver's name the
        # old scan took the LAST match with no positional relation to the work.
        "MARKER ; cd DEST",
        "MARKER && cd DEST",
        "cd START ; MARKER ; cd DEST",
        # A `cd` inside a brace GROUP after the run — not a subshell, so it
        # genuinely applies to the gh node beside it.
        "cd DEST && { cd START ; MARKER ; }",
    ]

    def test_family_a_short_circuit_cd_never_misroutes(self) -> None:
        for template in self.FAMILY_A_SHAPES:
            with self.subTest(shape=template):
                self._assert_never_misroutes(template)
                self.assertIsNone(
                    self._resolved(template),
                    "main#1151 family A: a short-circuit-guarded `cd` must never route",
                )

    def test_family_b_trailing_cd_never_misroutes(self) -> None:
        for template in self.FAMILY_B_SHAPES:
            with self.subTest(shape=template):
                self._assert_never_misroutes(template)
                self.assertIsNone(
                    self._resolved(template),
                    "main#1151 family B: a `cd` at/after the routed command must never route",
                )

    def test_family_a_and_b_shell_truth_is_the_start_dir(self) -> None:
        """The fact the fix rests on, asserted against BOTH shells directly.

        For every family-A shape the guarded `cd` does not run; for every
        family-B shape the `cd` runs only after the gh node. Either way the gh
        node executes in the ORIGINAL directory — so the old resolver's answer
        (`DEST`) named a directory the command had not entered.

        Every shape is asserted, with no skip list: the shapes whose leading
        element really is a `cd` all `cd START`, which IS the original
        directory, so they belong here rather than in an exemption.
        """
        for template in self.FAMILY_A_SHAPES + self.FAMILY_B_SHAPES:
            for shell in self.SHELLS:
                with self.subTest(shape=template, shell=shell):
                    self.assertEqual(self._shell_truth(template, shell), self._start)

    # --- main#1151 family C: a RELATIVE `cd` into a nested child repo ---

    def test_relative_cd_into_nested_repo_never_misroutes(self) -> None:
        """`cd /parent && cd child-repo` lands in a DIFFERENT repository.

        The old scan skipped the relative leg and kept `/parent`, which in this
        org's tree (child repos cloned beneath `noorinalabs-main/`) resolves
        `origin` to the PARENT repo — a cross-repo misroute on a shape that
        looks entirely innocent. The resolver now refuses the whole run rather
        than keeping a stale absolute prefix.
        """
        template = "cd START && cd NESTED && MARKER"
        for shell in self.SHELLS:
            with self.subTest(shell=shell):
                self.assertEqual(self._shell_truth(template, shell), self._nested)
        self._assert_never_misroutes(template)
        self.assertIsNone(self._resolved(template))

    # --- a cwd move that is not spelled `cd`, AFTER the leading run ---

    CWD_MOVING_BUILTIN_SHAPES = [
        "cd DEST && pushd OTHER > /dev/null && MARKER",
        "cd DEST ; pushd OTHER > /dev/null ; MARKER",
        "cd DEST && eval 'cd OTHER' && MARKER",
        "cd DEST && . SCRIPT && MARKER",
        "cd DEST && source SCRIPT && MARKER",
    ]

    def test_cwd_moving_builtin_after_the_run_never_misroutes(self) -> None:
        """`pushd`/`eval`/`source`/`.` move the shell without the token `cd`.

        Found at the #1156 merge gate. A leading `cd` is only evidence of where
        the work runs if nothing between it and the work moves the shell again;
        keying phase 2 on `words[0] == "cd"` alone missed every one of these and
        returned the stale leading target. `OTHER` is a real directory, so
        `resolve_invocation_cwd`'s `isdir` guard does not catch it either.

        This was not an open frontier — it was DRIFT. The degraded token scan
        already refused all of them, so the AST path was strictly weaker than
        its own co-primary fallback. `test_both_paths_agree_on_cwd_moving_builtins`
        is what stops that recurring.
        """
        for template in self.CWD_MOVING_BUILTIN_SHAPES:
            with self.subTest(shape=template):
                for shell in self.SHELLS:
                    self.assertEqual(
                        self._shell_truth(template, shell),
                        self._other,
                        f"{shell} should end up in OTHER for: {template}",
                    )
                self._assert_never_misroutes(template)
                self.assertIsNone(self._resolved(template))

    def test_popd_after_the_run_never_misroutes(self) -> None:
        """`popd` returns to DEST, so the truth here happens to match the stale
        answer — which is exactly why it must not be trusted. Refused anyway."""
        template = "cd DEST && pushd OTHER > /dev/null && popd > /dev/null && MARKER"
        for shell in self.SHELLS:
            self.assertEqual(self._shell_truth(template, shell), self._dest)
        self.assertIsNone(self._resolved(template))

    def test_exec_after_the_run_never_misroutes(self) -> None:
        """`exec` cannot carry a `cd`, but it REPLACES the shell — the routed
        command never runs at all, so claiming a directory for it is meaningless."""
        self.assertIsNone(self._resolved("cd DEST && exec -a x true ; MARKER"))

    def test_both_paths_agree_on_cwd_moving_builtins(self) -> None:
        """The anti-drift check: AST and degraded must refuse the SAME shapes.

        The #1156 defect was two mechanisms with independently maintained
        lists. Both now derive from `_CWD_MOVING_COMMANDS`, and this asserts
        the property rather than the shared constant, so a future split that
        re-introduces per-path lists fails here.
        """
        for template in self.CWD_MOVING_BUILTIN_SHAPES:
            with self.subTest(shape=template):
                self.assertEqual(
                    self._resolved(template),
                    self._resolved_degraded(template),
                    "the AST path must never be weaker than its own fallback",
                )

    def test_cwd_moving_commands_feeds_the_degraded_token_set(self) -> None:
        """One source of truth, asserted structurally as well as behaviourally."""
        self.assertTrue(sp._CWD_MOVING_COMMANDS <= sp._DEGRADED_CONTROL_FLOW_TOKENS)
        self.assertNotIn("cd", sp._DEGRADED_CONTROL_FLOW_TOKENS)

    # --- backgrounded / pipelined `cd` cannot move the calling shell ---

    SUBSHELL_SHAPES = [
        "cd DEST & MARKER",
        "cd DEST | cat ; MARKER",
    ]

    def test_backgrounded_or_pipelined_cd_never_misroutes(self) -> None:
        for template in self.SUBSHELL_SHAPES:
            with self.subTest(shape=template):
                self._assert_never_misroutes(template)
                self.assertIsNone(self._resolved(template))

    # --- shapes that MUST keep resolving, verified against both shells ---

    STILL_RESOLVING_SHAPES = [
        "cd DEST && MARKER",
        "cd DEST ; MARKER",
        "cd /var && cd DEST && MARKER",
        "cd DEST ; MARKER ; true",  # trailing work with no `cd` is harmless
        "cd DEST > /dev/null && MARKER",  # a redirect is not a wrapper
        "FOO=1 cd DEST && MARKER",  # one-shot assignment; `cd` is still a builtin
        "cd DEST && MARKER | cat",  # a pipeline cannot move the calling shell
    ]

    def test_unconditional_leading_cd_still_resolves_to_shell_truth(self) -> None:
        for template in self.STILL_RESOLVING_SHAPES:
            with self.subTest(shape=template):
                resolved = self._resolved(template)
                self.assertEqual(resolved, self._dest, f"lost the #521 recovery for: {template}")
                for shell in self.SHELLS:
                    self.assertEqual(resolved, self._shell_truth(template, shell))

    # --- degraded mode: no bashlex, so fail closed on control flow ---

    def _resolved_degraded(self, template: str) -> str | None:
        original = sp._BASHLEX_AVAILABLE
        sp._BASHLEX_AVAILABLE = False
        try:
            return sp.extract_leading_cd_target(self._expand(template, self.MARKER))
        finally:
            sp._BASHLEX_AVAILABLE = original

    def test_degraded_mode_fails_closed_on_both_families(self) -> None:
        """Without bashlex the fallback refuses anything carrying control flow.

        The availability gate sits OUTSIDE the memo, so monkeypatching it here
        cannot be served a cached AST answer.
        """
        for template in self.FAMILY_A_SHAPES + self.FAMILY_B_SHAPES + self.SUBSHELL_SHAPES:
            with self.subTest(shape=template):
                self.assertIsNone(self._resolved_degraded(template))

    def test_degraded_mode_keeps_the_521_recovery(self) -> None:
        """`&&`/`;` are the separators of the leading run itself, not control flow.

        Fail-closed must not mean "refuse every command with an `&&`" — that
        would delete `cd /worktree && gh pr create`, the shape this resolver
        exists for.
        """
        for template in ("cd DEST && MARKER", "cd DEST ; MARKER", "cd /var && cd DEST && MARKER"):
            with self.subTest(shape=template):
                self.assertEqual(self._resolved_degraded(template), self._dest)


class CdRoutingWhenBashlexCannotParse(unittest.TestCase):
    """The AST is NOT the sole mechanism — `<<'EOF'` does not parse at all.

    main#1152 (Weronika Zielinska) established, against the INSTALLED bashlex,
    that a QUOTED-delimiter heredoc raises `ParsingError`:

        bashlex.parse("cat <<'EOF'\\nx\\nEOF\\n")
        -> ParsingError: here-document ... delimited by end-of-file

    `<<'EOF'` / `<<"EOF"` fail; only the bare `<<EOF` / `<<-EOF` forms parse.
    That matters here more than anywhere else in the module, because the quoted
    form is the DOMINANT one in this repo (`python3 - <<'PY'`, `gh issue
    comment --body-file - <<'EOF'`) — so the commands most likely to carry a
    `cd` are exactly the ones the AST cannot see. `bashlex_available()` stays
    True (it only reports import success), and `iter_command_segments_ast`
    returns the same `None` it uses for "bashlex absent", so a caller that
    treats `None` as "fall back to the old shlex scan" degrades SILENTLY — an
    AST-only fix would have reported success and changed nothing on precisely
    these commands.

    It does not, and this class is the evidence. The fallback is not the old
    last-`cd`-wins scan; it is the issue's fix direction 2 (fail closed on
    control flow), which makes the two mechanisms CO-PRIMARY rather than
    primary-and-safety-net. Every shape below forces the ParsingError and is
    checked against real bash and zsh.
    """

    GH = "gh issue comment 5 --body-file -"
    SHELLS = tuple(s for s in ("bash", "zsh") if shutil.which(s))

    _start: str
    _dest: str
    _nested: str

    @classmethod
    def setUpClass(cls) -> None:
        cls._start = tempfile.mkdtemp(prefix="cdhd-start-")
        cls._dest = tempfile.mkdtemp(prefix="cdhd-dest-")
        cls._nested = os.path.join(cls._start, "child-repo")
        os.makedirs(cls._nested, exist_ok=True)

    @classmethod
    def tearDownClass(cls) -> None:
        for d in (cls._start, cls._dest):
            shutil.rmtree(d, ignore_errors=True)

    def _expand(self, template: str) -> str:
        return (
            template.replace("DEST", self._dest)
            .replace("START", self._start)
            .replace("NESTED", "child-repo")
            .replace("GH", self.GH)
        )

    def _assert_does_not_parse(self, template: str) -> None:
        """Every shape here must really exercise the fallback, not the AST."""
        parsed, _ = sp._ast_leading_cd_target(self._expand(template))
        self.assertFalse(
            parsed,
            f"shape no longer forces the bashlex ParsingError, so it stops "
            f"testing the fallback path: {template}",
        )

    def _resolved(self, template: str) -> str | None:
        return sp.extract_leading_cd_target(self._expand(template))

    def _shell_truth(self, template: str, shell: str) -> str | None:
        """cwd where the gh node sits. `pwd` goes to stderr so the heredoc
        body (which `cat` sends to stdout) cannot be mistaken for it."""
        cmd = self._expand(template).replace(self.GH, "pwd >&2 ; cat")
        out = subprocess.run(
            [shell, "-c", cmd], cwd=self._start, capture_output=True, text=True, timeout=30
        )
        printed = out.stderr.strip().splitlines()
        return printed[-1] if printed else None

    def _assert_never_misroutes(self, template: str) -> None:
        self._assert_does_not_parse(template)
        resolved = self._resolved(template)
        if resolved is None:
            return
        for shell in self.SHELLS:
            self.assertEqual(resolved, self._shell_truth(template, shell), f"for: {template}")

    def test_quoted_delimiter_heredoc_really_does_not_parse(self) -> None:
        """The premise, asserted against the installed bashlex, not from docs."""
        if not sp.bashlex_available():
            self.skipTest("bashlex not installed")
        for body in ("cat <<'EOF'\nx\nEOF\n", 'cat <<"EOF"\nx\nEOF\n'):
            with self.subTest(form=body.splitlines()[0]):
                with self.assertRaises(Exception):
                    sp.bashlex.parse(body)
        for body in ("cat <<EOF\nx\nEOF\n", "cat <<-EOF\nx\nEOF\n"):
            with self.subTest(form=body.splitlines()[0]):
                sp.bashlex.parse(body)  # bare forms DO parse

    def test_bashlex_available_is_not_evidence_the_command_parsed(self) -> None:
        """The trap: the flag reports IMPORT success, not per-command success."""
        if not sp.bashlex_available():
            self.skipTest("bashlex not installed")
        cmd = "cat <<'EOF'\nx\nEOF\n"
        self.assertTrue(sp.bashlex_available())
        self.assertIsNone(sp.iter_command_segments_ast(cmd))
        self.assertEqual(sp._ast_leading_cd_target(cmd), (False, None))

    FAMILY_SHAPES = [
        # A — short-circuit-guarded `cd`, alongside a quoted heredoc.
        "true || cd DEST ; GH <<'EOF'\nhello\nEOF\n",
        # B — `cd` positioned after the gh node.
        "GH <<'EOF'\nhello\nEOF\ncd DEST\n",
        # C — relative leg into a nested child repo.
        "cd START && cd NESTED && GH <<'EOF'\nhi\nEOF\n",
    ]

    def test_families_stay_closed_on_the_fallback_path(self) -> None:
        for template in self.FAMILY_SHAPES:
            with self.subTest(shape=template):
                self._assert_never_misroutes(template)
                self.assertIsNone(
                    self._resolved(template),
                    "a family shape must not route just because bashlex could "
                    "not parse the heredoc that came with it",
                )

    ADVERSARIAL_BODY_SHAPES = [
        # Can an UNSTRIPPED heredoc BODY inject a `cd` the token scan mistakes
        # for a leading, unconditional one? It cannot: a body always follows
        # its command, so its tokens are never in the leading position.
        "cat <<'EOF'\n; cd DEST\nEOF\nGH",
        "cd /var && cat <<'EOF'\n; cd DEST\nEOF\nGH",
        "GH <<'EOF'\ncd DEST\nEOF\n",
        "GH <<'EOF'\ntrue || cd DEST\nEOF\n",
        "cd DEST && GH <<'EOF'\n; cd /var\nEOF\n",
    ]

    def test_heredoc_body_cannot_inject_a_route(self) -> None:
        for template in self.ADVERSARIAL_BODY_SHAPES:
            with self.subTest(shape=template):
                self._assert_never_misroutes(template)

    def test_genuine_recovery_survives_the_fallback(self) -> None:
        """Fail-closed must not mean "refuse every command with a heredoc".

        `cd /worktree && gh issue comment … <<'EOF'` is an ordinary shape and
        still resolves — the fallback keeps `;`/`&&` as leading-run separators.
        """
        template = "cd DEST && GH <<'EOF'\nhello\nEOF\n"
        self._assert_does_not_parse(template)
        resolved = self._resolved(template)
        self.assertEqual(resolved, self._dest)
        for shell in self.SHELLS:
            self.assertEqual(resolved, self._shell_truth(template, shell))


class ResolveSimpleAssignmentsTests(unittest.TestCase):
    """Direct output-string tests for `resolve_simple_assignments` (main#1195
    review round 2).

    Every OTHER test that touches this pre-pass — in `test_validate_commit_
    identity.py` — only observes `check()`'s downstream block/allow verdict.
    That is the wrong level to catch a resolver that silently produces the
    WRONG substituted text but happens to still be rejected (or still
    happens to still be blocked) by whatever consumes it: main#1195's own
    review found that mutating `_VAR_REF_RE`'s bare-name capture to drop its
    trailing `\\b` boundary AND weaken its quantifier corrupts `$gone` into
    `gitone` — a downstream matcher rejects "gitone" as not `git` either, so
    a verdict-only test suite of 16 cases passed unchanged under that
    mutation. Asserting the resolver's RETURNED STRING directly, as this
    class does, is the only level at which that corruption is observable.
    `resolve_simple_assignments` had no direct unit test before this class.
    """

    def test_basic_bare_assignment_resolves(self) -> None:
        self.assertEqual(
            sp.resolve_simple_assignments("g=git; $g commit -m x"),
            "g=git; git commit -m x",
        )

    def test_braced_form_resolves(self) -> None:
        self.assertEqual(
            sp.resolve_simple_assignments("g=git; ${g} commit -m x"),
            "g=git; git commit -m x",
        )

    def test_no_qualifying_assignment_returns_input_unchanged(self) -> None:
        cmd = "echo hello world"
        self.assertEqual(sp.resolve_simple_assignments(cmd), cmd)

    def test_unassigned_reference_left_literal(self) -> None:
        cmd = "echo $NEVERASSIGNED"
        self.assertEqual(sp.resolve_simple_assignments(cmd), cmd)

    def test_unparseable_command_returned_unchanged(self) -> None:
        cmd = 'git commit -m "unterminated'
        self.assertEqual(sp.resolve_simple_assignments(cmd), cmd)

    # --- positional resolution (main#1195 review round 2: the resolver was
    # order-blind — one flat last-wins map across the whole command) --------

    def test_trailing_reassignment_via_semicolon_does_not_corrupt_earlier_use(self) -> None:
        """`g=git; $g commit -m x; g=echo` — the primary repro. A flat
        last-wins map resolves `$g` to `echo` (the LAST assignment anywhere
        in the command), turning this into `echo commit -m x` and hiding
        the git invocation entirely. Positional resolution must still read
        `$g` as `git` at the point it is actually used.
        """
        self.assertEqual(
            sp.resolve_simple_assignments("g=git; $g commit -m x; g=echo"),
            "g=git; git commit -m x; g=echo",
        )

    def test_trailing_reassignment_to_true_does_not_corrupt_earlier_use(self) -> None:
        self.assertEqual(
            sp.resolve_simple_assignments("g=git; $g commit -m x; g=true"),
            "g=git; git commit -m x; g=true",
        )

    def test_trailing_reassignment_via_or_operator_does_not_corrupt_earlier_use(self) -> None:
        self.assertEqual(
            sp.resolve_simple_assignments("g=git; $g commit -m x || g=x"),
            "g=git; git commit -m x || g=x",
        )

    def test_trailing_reassignment_via_and_operator_does_not_corrupt_earlier_use(self) -> None:
        self.assertEqual(
            sp.resolve_simple_assignments("g=git; $g commit -m x; false && g=nope"),
            "g=git; git commit -m x; false && g=nope",
        )

    def test_reassignment_that_has_not_happened_yet_is_not_used_early(self) -> None:
        """Mirror image of the trailing-reassignment shapes above — a naive
        "first assignment wins, globally" fix (rejected; see the module
        comment above `resolve_simple_assignments` in `_shell_parse.py`)
        would get THIS shape wrong. `$g` is used while `g` still holds
        `echo`; the LATER `g=git` must not retroactively resolve it.
        """
        self.assertEqual(
            sp.resolve_simple_assignments("g=echo; $g commit; g=git"),
            "g=echo; echo commit; g=git",
        )

    def test_same_segment_leading_assignment_not_visible_to_own_expansion(self) -> None:
        """`A=1 B=git $B commit -m z` — main#1195 review round 3,
        real-shell-verified with a printf/marker proxy: POSIX expands a
        command's words BEFORE applying that SAME command's own prefix
        assignments, so `$B` is NOT visible to a reference inside its own
        segment. A real shell never runs git here (`$B` is unset at
        expansion time; `B=git` only scopes the invoked command's
        environment). Supersedes the previous (wrong)
        `test_same_segment_multiple_leading_assignments_resolve_within_segment`,
        which encoded exactly this misreading of POSIX prefix-assignment
        scope as the expected behaviour.
        """
        cmd = "A=1 B=git $B commit -m z"
        self.assertEqual(sp.resolve_simple_assignments(cmd), cmd)

    def test_same_segment_leading_assignment_becomes_visible_in_later_segment(self) -> None:
        """The peeling loop must still consume BOTH leading assignment
        tokens (`A=1` then `B=git`) in one segment — the multi-assignment
        coverage the superseded test above was meant to pin, checked here
        where a real shell agrees: once `;` moves the reference into a
        LATER segment, `B`'s value from a two-assignment leading run is
        visible.
        """
        self.assertEqual(
            sp.resolve_simple_assignments("A=1 B=git; $B commit -m z"),
            "A=1 B=git; git commit -m z",
        )

    # --- name-prefix conflation guard (main#1195 review round 2, finding 2) -

    def test_shorter_assignment_not_conflated_with_longer_bare_name(self) -> None:
        """`$gone` is a DIFFERENT variable from `$g`. The greedy identifier
        match plus the trailing `\\b` boundary in `_VAR_REF_RE` must capture
        the FULL name "gone" (never assigned) and leave it untouched. A
        weakened boundary/quantifier would instead read this as `$g` +
        literal "one", corrupting the output to "gitone" — invisible to any
        test that only checks a downstream block/allow verdict.
        """
        cmd = "g=git; echo $gone"
        self.assertEqual(sp.resolve_simple_assignments(cmd), cmd)

    def test_shorter_assignment_not_conflated_with_underscore_suffixed_name(self) -> None:
        cmd = "g=git; echo $g_2"
        self.assertEqual(sp.resolve_simple_assignments(cmd), cmd)

    def test_shorter_assignment_not_conflated_with_bare_suffix(self) -> None:
        cmd = "g=git; echo $gx"
        self.assertEqual(sp.resolve_simple_assignments(cmd), cmd)

    # --- documented non-goals: must remain unresolved ------------------------

    def test_command_substitution_value_not_resolved(self) -> None:
        cmd = "d=$(date); echo $d"
        self.assertEqual(sp.resolve_simple_assignments(cmd), cmd)

    def test_multiword_value_not_resolved(self) -> None:
        cmd = 'msg="please git commit this later"; echo $msg'
        self.assertEqual(sp.resolve_simple_assignments(cmd), cmd)

    def test_value_containing_variable_reference_does_not_chain(self) -> None:
        """`g=$a` fails the literal-value check (contains `$`), so `g` is
        never added to the assignment map — a later `$g` stays literal even
        though `a` itself resolved earlier in the command. (The `a=git; g=$a`
        segment's own displayed text still shows `a`'s value substituted in
        — a pre-existing textual side effect of substituting every segment,
        not a resolution of `g`; the load-bearing assertion here is that the
        trailing `$g` is untouched.)
        """
        self.assertEqual(
            sp.resolve_simple_assignments("a=git; g=$a; $g commit -m x"),
            "a=git; g=git; $g commit -m x",
        )

    def test_local_keyword_prefix_is_out_of_scope(self) -> None:
        """Only `export`/`declare` are folded in (#1305); `local` and any
        other prefix keyword remain a non-goal.
        """
        cmd = "local g=git; $g commit -m x"
        self.assertEqual(sp.resolve_simple_assignments(cmd), cmd)

    # --- #1305: export/declare fold-in ---------------------------------------

    def test_export_prefixed_assignment_resolves(self) -> None:
        self.assertEqual(
            sp.resolve_simple_assignments("export g=git; $g commit -m x"),
            "export g=git; git commit -m x",
        )

    def test_declare_prefixed_assignment_resolves(self) -> None:
        self.assertEqual(
            sp.resolve_simple_assignments("declare g=git; $g commit -m x"),
            "declare g=git; git commit -m x",
        )

    # --- main#1195 round 4, finding 1: same-segment prefix DOES resolve
    # inside a single-quoted CHILD payload, real-shell-verified with a
    # marker proxy (`g=git bash -c '$g commit -m x'` genuinely runs
    # `git commit -m x`) -------------------------------------------------

    def test_same_segment_prefix_resolves_inside_single_quoted_child_payload(
        self,
    ) -> None:
        self.assertEqual(
            sp.resolve_simple_assignments("g=git bash -c '$g commit -m x'"),
            "g=git bash -c 'git commit -m x'",
        )

    def test_same_segment_prefix_resolves_inside_single_quoted_sh_dash_c(self) -> None:
        """Same shape, `sh -c` instead of `bash -c` — the fix lives in the
        assignment/quote resolver, not in anything interpreter-specific.
        """
        self.assertEqual(
            sp.resolve_simple_assignments("g=git sh -c '$g commit -m x'"),
            "g=git sh -c 'git commit -m x'",
        )

    def test_same_segment_prefix_resolves_inside_single_quoted_braced_payload(
        self,
    ) -> None:
        self.assertEqual(
            sp.resolve_simple_assignments("g=git bash -c '${g} commit -m x'"),
            "g=git bash -c 'git commit -m x'",
        )

    def test_same_segment_prefix_not_resolved_inside_double_quoted_payload(
        self,
    ) -> None:
        """Control for the above: `bash -c "$g commit -m x"` (double-quoted)
        is expanded by the OUTER shell at the same expansion point a bare
        same-segment reference is (`A=1 B=git $B commit -m z`) — BEFORE its
        own prefix assignment takes effect — so `$g` must stay unresolved,
        real-shell-verified with a marker proxy (no git run).
        """
        cmd = 'g=git bash -c "$g commit -m x"'
        self.assertEqual(sp.resolve_simple_assignments(cmd), cmd)

    # --- main#1195 round 4, finding 3: a compound-statement leader (`do`,
    # `then`, ...) at a segment's leading position must not hide the
    # assignment one token to the right, real-shell-verified with a marker
    # proxy (each row genuinely runs `git commit -m x`) -------------------

    def test_do_prefixed_segment_assignment_resolves_in_later_segment(self) -> None:
        self.assertEqual(
            sp.resolve_simple_assignments("for f in a; do g=git; $g commit -m x; done"),
            "for f in a; do g=git; git commit -m x; done",
        )

    def test_then_prefixed_segment_assignment_resolves_in_later_segment(self) -> None:
        self.assertEqual(
            sp.resolve_simple_assignments("if true; then g=git; $g commit -m x; fi"),
            "if true; then g=git; git commit -m x; fi",
        )

    def test_do_prefixed_segment_assignment_multichar_name_resolves(self) -> None:
        """Vary the incidental dimension a single-character-name fixture
        would hide (main#1195 finding 2's lesson, applied here too): `gg`,
        not `g`.
        """
        self.assertEqual(
            sp.resolve_simple_assignments("for f in a; do gg=git; $gg commit -m x; done"),
            "for f in a; do gg=git; git commit -m x; done",
        )

    def test_do_prefixed_segment_assignment_braced_reference_resolves(self) -> None:
        self.assertEqual(
            sp.resolve_simple_assignments("for f in a; do g=git; ${g} commit -m x; done"),
            "for f in a; do g=git; git commit -m x; done",
        )

    def test_do_prefixed_single_quoted_child_payload_resolves(self) -> None:
        """Finding 1 and finding 3 compose: a `do`-prefixed segment's own
        leading assignment feeding a single-quoted `bash -c` payload in the
        SAME segment must resolve, real-shell-verified (genuinely runs
        `git commit -m x`).
        """
        self.assertEqual(
            sp.resolve_simple_assignments("for f in a; do g=git bash -c '$g commit -m x'; done"),
            "for f in a; do g=git bash -c 'git commit -m x'; done",
        )


if __name__ == "__main__":
    unittest.main()
