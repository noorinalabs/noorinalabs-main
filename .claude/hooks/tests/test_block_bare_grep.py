#!/usr/bin/env python3
"""Tests for block_bare_grep — rg-over-grep enforcement (#1008).

Covers every syntactic form a `grep` invocation can take (per
`feedback_lint_gate_cover_all_syntactic_forms`): direct, piped, wrapped
(sudo/env/xargs/…), path-qualified, command-substituted, plus the data-position
/ heredoc / flag-value NEGATIVES that must NOT trigger, and the documented
`NOORINA_ALLOW_GREP` override.

`PositiveMatchTests` and `NegativeMatchTests` are `pytest.mark.parametrize`
tables (#1117 — G5 clone-group parametrization): every member of each
originally-duplicated group was a single-statement `self.assertTrue(_blocks(cmd))`
/ `self.assertFalse(_blocks(cmd))` method differing only in `cmd`, so they are
NOT `unittest.TestCase` (parametrize is silently a no-op on `TestCase`
methods — verified empirically before converting: a probe class collected 1
test instead of N). `OverrideTests` and the two non-matching `NegativeMatchTests`
methods (`test_non_bash_tool`, `test_empty_command`) keep their own bodies:
they are AST-shape-identical to the parametrized tables (same
`self.assertFalse(_blocks(...))` call shape) but belong to a semantically
different scenario (the escape hatch, not "not a grep invocation" /
"a different tool entirely") — collapsing across that boundary is exactly the
"structurally identical, not safely mergeable" trap, so they stay separate.
Every `ids=` entry below is the original method's bare name (the `test_`
prefix stripped) so each parametrized case is traceable 1:1 back to the test
it replaces.

Run: ENVIRONMENT=test python3 -m pytest .claude/hooks/tests/test_block_bare_grep.py -v
"""

# This file's own hook-side import is an underscore-prefixed module
# whose name sorts alphabetically before `_test_helpers` — ruff's isort
# autofix would otherwise reorder it ahead of the sys.path bootstrap it
# depends on. See `_test_helpers.py`'s module docstring.
# isort: skip_file
from __future__ import annotations

import unittest

import pytest

import _test_helpers  # noqa: E402,F401
import _shell_parse  # noqa: E402
import block_bare_grep as hook  # noqa: E402

_input = _test_helpers.bash_input


def _blocks(command: str) -> bool:
    result = hook.check(_input(command))
    return result is not None and result.get("decision") == "block"


class TestPositiveMatch:
    """Real bare-grep invocations MUST be blocked."""

    @pytest.mark.parametrize(
        "command",
        [
            "grep foo file",
            'grep -rn "foo" src/',
            # grep as a downstream pipeline segment — the most common real form.
            "rg foo | grep bar",
            "cat file | grep foo",
            "egrep foo file",
            "fgrep foo file",
            "/usr/bin/grep foo file",
            "sudo grep foo /var/log/syslog",
            "env LC_ALL=C grep foo file",
            "time grep foo file",
            "echo file | xargs grep foo",
            # `-I {}` takes a value — the `{}` must not be mistaken for the command.
            "echo file | xargs -I {} grep foo {}",
            "command grep foo file",
            # #1008 review (Weronika): `-i` is BOOLEAN on sudo (login shell), not a
            # value flag — it must not eat the following `grep` token. Regression.
            "sudo -i grep foo file",
            "sudo -s grep foo file",
            # `-u root` consumes `root`; `-i` is boolean — grep still resolves.
            "sudo -u root -i grep foo file",
            # `-u root` (value flag) consumes `root`, leaving grep as the command.
            "sudo -u root grep foo file",
            # `-i` IS a value flag on stdbuf (buffer mode) — the per-wrapper dict
            # must keep that behavior while fixing sudo. `stdbuf -i L grep` still
            # resolves grep as the command (L is -i's value).
            "stdbuf -i L grep foo file",
            # `-s` is a value flag on xargs (max size) — must still consume its value.
            "echo f | xargs -s 1000 grep foo",
            "rg foo file && grep bar file2",
            "LC_ALL=C grep foo file",
            # An explicit falsey override does NOT open the gate.
            "NOORINA_ALLOW_GREP=0 grep foo file",
            pytest.param(
                "x=$(grep foo bar)",
                id="command_substitution",
                marks=pytest.mark.skipif(
                    not _shell_parse.bashlex_available(),
                    reason="command-substitution detection needs the bashlex AST path",
                ),
            ),
        ],
        ids=[
            "direct",
            "direct_with_flags",
            "piped",
            "piped_from_cat",
            "egrep",
            "fgrep",
            "absolute_path",
            "wrapper_sudo",
            "wrapper_env_with_assignment",
            "wrapper_time",
            "wrapper_xargs",
            "wrapper_xargs_replace_flag",
            "wrapper_command",
            "wrapper_sudo_login_flag",
            "wrapper_sudo_shell_flag",
            "wrapper_sudo_mixed_value_and_boolean_flags",
            "wrapper_sudo_value_flag_still_consumes",
            "wrapper_stdbuf_value_flag_preserved",
            "wrapper_xargs_s_value_flag_preserved",
            "second_segment_of_and_list",
            "leading_env_assignment",
            "override_off_value_still_blocks",
            None,  # the pytest.param above carries its own id
        ],
    )
    def test_blocks(self, command):
        assert _blocks(command)


class TestNegativeMatch:
    """The tools we want, and data-position 'grep', must NOT trigger."""

    @pytest.mark.parametrize(
        "command",
        [
            "rg foo file",
            "ripgrep foo file",
            "ast-grep -p 'foo(bar)' src/",
            "pgrep -f myproc",
            "zgrep foo file.gz",
            # git's own tracked-file search — `git` is the command, not `grep`.
            "git grep foo",
            'echo "use grep for this"',
            'gh pr create --body "we mention grep in prose"',
            "cat > /tmp/x.md <<'EOF'\nDo not use grep here.\nEOF",
            "cat grepped_output.txt",
            "echo pgrep",
            "rg foo src/",
        ],
        ids=[
            "rg",
            "ripgrep",
            "ast_grep",
            "pgrep",
            "zgrep",
            "git_grep",
            "echo_data_position",
            "gh_body_flag_value",
            "heredoc_body",
            "filename_containing_grep",
            "word_containing_grep",
            "no_grep_at_all",
        ],
    )
    def test_does_not_block(self, command):
        assert not _blocks(command)

    def test_non_bash_tool(self):
        assert hook.check({"tool_name": "Edit", "tool_input": {"command": "grep foo file"}}) is None

    def test_empty_command(self):
        assert hook.check(_input("")) is None


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
    # `unittest.main()` would silently skip TestPositiveMatch/TestNegativeMatch
    # (plain pytest classes, not unittest.TestCase — see module docstring) when
    # this file is run standalone. `pytest.main` discovers both styles.
    raise SystemExit(pytest.main([__file__, "-v"]))
