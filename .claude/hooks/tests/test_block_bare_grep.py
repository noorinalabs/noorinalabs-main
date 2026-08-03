#!/usr/bin/env python3
"""Tests for block_bare_grep — rg-over-grep enforcement (#1008).

Covers every syntactic form a `grep` invocation can take (per
`feedback_lint_gate_cover_all_syntactic_forms`): direct, piped, wrapped
(sudo/env/xargs/…), path-qualified, command-substituted, plus the data-position
/ heredoc / flag-value NEGATIVES that must NOT trigger, and the documented
`NOORINA_ALLOW_GREP` override.

Run: ENVIRONMENT=test python3 -m pytest .claude/hooks/tests/test_block_bare_grep.py -v
"""

from __future__ import annotations

import unittest

import __test_helpers  # noqa: E402,F401
import _shell_parse  # noqa: E402
import block_bare_grep as hook  # noqa: E402

_input = __test_helpers.bash_input


def _blocks(command: str) -> bool:
    result = hook.check(_input(command))
    return result is not None and result.get("decision") == "block"


class PositiveMatchTests(unittest.TestCase):
    """Real bare-grep invocations MUST be blocked."""

    def test_direct(self):
        self.assertTrue(_blocks("grep foo file"))

    def test_direct_with_flags(self):
        self.assertTrue(_blocks('grep -rn "foo" src/'))

    def test_piped(self):
        # grep as a downstream pipeline segment — the most common real form.
        self.assertTrue(_blocks("rg foo | grep bar"))

    def test_piped_from_cat(self):
        self.assertTrue(_blocks("cat file | grep foo"))

    def test_egrep(self):
        self.assertTrue(_blocks("egrep foo file"))

    def test_fgrep(self):
        self.assertTrue(_blocks("fgrep foo file"))

    def test_absolute_path(self):
        self.assertTrue(_blocks("/usr/bin/grep foo file"))

    def test_wrapper_sudo(self):
        self.assertTrue(_blocks("sudo grep foo /var/log/syslog"))

    def test_wrapper_env_with_assignment(self):
        self.assertTrue(_blocks("env LC_ALL=C grep foo file"))

    def test_wrapper_time(self):
        self.assertTrue(_blocks("time grep foo file"))

    def test_wrapper_xargs(self):
        self.assertTrue(_blocks("echo file | xargs grep foo"))

    def test_wrapper_xargs_replace_flag(self):
        # `-I {}` takes a value — the `{}` must not be mistaken for the command.
        self.assertTrue(_blocks("echo file | xargs -I {} grep foo {}"))

    def test_wrapper_command(self):
        self.assertTrue(_blocks("command grep foo file"))

    def test_wrapper_sudo_login_flag(self):
        # #1008 review (Weronika): `-i` is BOOLEAN on sudo (login shell), not a
        # value flag — it must not eat the following `grep` token. Regression.
        self.assertTrue(_blocks("sudo -i grep foo file"))

    def test_wrapper_sudo_shell_flag(self):
        self.assertTrue(_blocks("sudo -s grep foo file"))

    def test_wrapper_sudo_mixed_value_and_boolean_flags(self):
        # `-u root` consumes `root`; `-i` is boolean — grep still resolves.
        self.assertTrue(_blocks("sudo -u root -i grep foo file"))

    def test_wrapper_sudo_value_flag_still_consumes(self):
        # `-u root` (value flag) consumes `root`, leaving grep as the command.
        self.assertTrue(_blocks("sudo -u root grep foo file"))

    def test_wrapper_stdbuf_value_flag_preserved(self):
        # `-i` IS a value flag on stdbuf (buffer mode) — the per-wrapper dict
        # must keep that behavior while fixing sudo. `stdbuf -i L grep` still
        # resolves grep as the command (L is -i's value).
        self.assertTrue(_blocks("stdbuf -i L grep foo file"))

    def test_wrapper_xargs_s_value_flag_preserved(self):
        # `-s` is a value flag on xargs (max size) — must still consume its value.
        self.assertTrue(_blocks("echo f | xargs -s 1000 grep foo"))

    def test_second_segment_of_and_list(self):
        self.assertTrue(_blocks("rg foo file && grep bar file2"))

    def test_leading_env_assignment(self):
        self.assertTrue(_blocks("LC_ALL=C grep foo file"))

    def test_override_off_value_still_blocks(self):
        # An explicit falsey override does NOT open the gate.
        self.assertTrue(_blocks("NOORINA_ALLOW_GREP=0 grep foo file"))

    @unittest.skipUnless(
        _shell_parse.bashlex_available(),
        "command-substitution detection needs the bashlex AST path",
    )
    def test_command_substitution(self):
        self.assertTrue(_blocks("x=$(grep foo bar)"))


class NegativeMatchTests(unittest.TestCase):
    """The tools we want, and data-position 'grep', must NOT trigger."""

    def test_rg(self):
        self.assertFalse(_blocks("rg foo file"))

    def test_ripgrep(self):
        self.assertFalse(_blocks("ripgrep foo file"))

    def test_ast_grep(self):
        self.assertFalse(_blocks("ast-grep -p 'foo(bar)' src/"))

    def test_pgrep(self):
        self.assertFalse(_blocks("pgrep -f myproc"))

    def test_zgrep(self):
        self.assertFalse(_blocks("zgrep foo file.gz"))

    def test_git_grep(self):
        # git's own tracked-file search — `git` is the command, not `grep`.
        self.assertFalse(_blocks("git grep foo"))

    def test_echo_data_position(self):
        self.assertFalse(_blocks('echo "use grep for this"'))

    def test_gh_body_flag_value(self):
        self.assertFalse(_blocks('gh pr create --body "we mention grep in prose"'))

    def test_heredoc_body(self):
        cmd = "cat > /tmp/x.md <<'EOF'\nDo not use grep here.\nEOF"
        self.assertFalse(_blocks(cmd))

    def test_filename_containing_grep(self):
        self.assertFalse(_blocks("cat grepped_output.txt"))

    def test_word_containing_grep(self):
        self.assertFalse(_blocks("echo pgrep"))

    def test_no_grep_at_all(self):
        self.assertFalse(_blocks("rg foo src/"))

    def test_non_bash_tool(self):
        self.assertIsNone(
            hook.check({"tool_name": "Edit", "tool_input": {"command": "grep foo file"}})
        )

    def test_empty_command(self):
        self.assertIsNone(hook.check(_input("")))


class OverrideTests(unittest.TestCase):
    """The documented escape hatch."""

    def test_override_truthy(self):
        self.assertFalse(_blocks("NOORINA_ALLOW_GREP=1 grep foo file"))

    def test_override_arbitrary_truthy(self):
        self.assertFalse(_blocks("NOORINA_ALLOW_GREP=yes grep foo file"))

    def test_override_in_heredoc_does_not_count(self):
        # The override must be a real env prefix, not text inside a body.
        cmd = "cat <<'EOF'\nNOORINA_ALLOW_GREP=1\nEOF\ngrep foo file"
        self.assertTrue(_blocks(cmd))


class BlockMessageTests(unittest.TestCase):
    """The block reason must be actionable."""

    def test_reason_mentions_rg_and_override(self):
        result = hook.check(_input("grep foo file"))
        assert result is not None
        reason = result["reason"]
        self.assertIn("rg", reason)
        self.assertIn("NOORINA_ALLOW_GREP", reason)
        self.assertIn("--no-ignore", reason)


if __name__ == "__main__":
    unittest.main()
