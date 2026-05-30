#!/usr/bin/env python3
"""Tests for auto_set_env_test hook.

Covers hook-authorship-spec requirement: NEGATIVE MATCH coverage.
Each test documents which negative-space case it guards against.

Run: python3 -m pytest .claude/hooks/tests/test_auto_set_env_test.py -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
sys.path.insert(0, str(_HOOKS_DIR))

import auto_set_env_test as hook  # noqa: E402


def _bash(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


class NonMatchedToolTests(unittest.TestCase):
    """Tools OTHER than Bash must never block."""

    def test_edit_does_not_block(self) -> None:
        """NEG: Edit is not in the matcher set."""
        result = hook.check({"tool_name": "Edit", "tool_input": {"file_path": "x.py"}})
        self.assertIsNone(result)

    def test_write_does_not_block(self) -> None:
        """NEG: Write is not in the matcher set."""
        result = hook.check({"tool_name": "Write", "tool_input": {"file_path": "x.py"}})
        self.assertIsNone(result)


class GhSubcommandSkipTests(unittest.TestCase):
    """Short-circuit #1: any command whose argv[0] is `gh` is exempt (#114)."""

    def test_gh_pr_comment_with_pytest_in_body(self) -> None:
        """NEG: `gh pr comment ... --body "...pytest..."` — repro case from #114."""
        result = hook.check(
            _bash('gh pr comment 808 --repo noorinalabs/x --body "fixing pytest CVE"')
        )
        self.assertIsNone(result, "gh pr comment mentioning pytest in body must be allowed")

    def test_gh_issue_create_with_make_test_in_body(self) -> None:
        """NEG: `gh issue create --body "make test broke"` — substring false-positive."""
        result = hook.check(_bash('gh issue create --title "x" --body "make test broke"'))
        self.assertIsNone(result, "gh issue create mentioning make test in body must be allowed")

    def test_gh_pr_create_runs_pytest_mention(self) -> None:
        """NEG: `gh pr create --body "runs pytest in CI"` — PR description text."""
        result = hook.check(_bash('gh pr create --body "runs pytest in CI"'))
        self.assertIsNone(result, "gh pr create mentioning pytest must be allowed")

    def test_gh_skip_beats_env_prefix(self) -> None:
        """NEG: `ENVIRONMENT=test gh pr comment ... --body "pytest"` — gh skip
        takes precedence; we don't want to accidentally encourage the env prefix
        on gh commands by only allowing them if ENVIRONMENT=test is present."""
        result = hook.check(_bash('ENVIRONMENT=test gh pr comment 1 --body "pytest"'))
        self.assertIsNone(
            result,
            "gh after env-assignment prefix is still a gh invocation, not a test",
        )

    def test_gh_with_multiple_env_prefixes(self) -> None:
        """NEG: multiple leading env assignments still resolve to `gh` argv[0]."""
        result = hook.check(_bash('FOO=1 BAR=2 gh pr comment 1 --body "pytest note"'))
        self.assertIsNone(result)


class EnvWrapperGhSkipTests(unittest.TestCase):
    """Issue #181: extend gh-skip to recognise the literal `env` wrapper:
        env FOO=bar gh pr comment ...
        env FOO=1 BAR=2 gh pr ...
        FOO=1 env BAR=2 gh pr ...   (shell VAR prefix BEFORE env)
    The bare `env` form (no flags) is a transparent wrapper — it sets env
    vars then exec's gh. The hook must treat the inner gh as argv[0] for
    short-circuit purposes."""

    def test_env_wrapper_gh_invocation_skipped(self) -> None:
        """NEG: `env FOO=bar gh pr comment ...` — env wrapper, gh skip fires."""
        result = hook.check(_bash('env FOO=bar gh pr comment 1 --body "pytest"'))
        self.assertIsNone(result, "env wrapper before gh must allow")

    def test_env_wrapper_with_multiple_assignments_gh_skipped(self) -> None:
        """NEG: `env FOO=1 BAR=2 gh pr ...` — multiple env's own assignments."""
        result = hook.check(_bash('env FOO=1 BAR=2 gh pr comment 1 --body "pytest"'))
        self.assertIsNone(result)

    def test_env_wrapper_bare_gh_skipped(self) -> None:
        """NEG: `env gh pr ...` — env with no assignments, just the gh exec."""
        result = hook.check(_bash('env gh pr comment 1 --body "pytest"'))
        self.assertIsNone(result)

    def test_shell_prefix_then_env_wrapper_gh_skipped(self) -> None:
        """NEG: `FOO=1 env BAR=2 gh pr ...` — shell env prefix, THEN `env`
        wrapper, THEN gh. _strip_leading_env eats `FOO=1`, then we see
        `env BAR=2 gh ...` and recurse one step."""
        result = hook.check(_bash('FOO=1 env BAR=2 gh pr comment 1 --body "pytest"'))
        self.assertIsNone(result)

    def test_env_wrapper_non_gh_does_not_skip(self) -> None:
        """POS: `env FOO=1 pytest tests/` — env wrapper around pytest is
        STILL a test command (env doesn't change the fact that the eventual
        argv[0] passed to exec is pytest). Must block."""
        result = hook.check(_bash("env FOO=1 pytest tests/"))
        assert result is not None, "env-wrapped pytest must still block"
        self.assertEqual(result.get("decision"), "block")

    def test_env_dash_i_flag_not_recursed(self) -> None:
        """POS: `env -i gh pr ...` — the `-i` flag form is OUT OF SCOPE per
        #181. `env -i` clears the inherited environment (operator-explicit
        signal); we don't pretend the inner gh is argv[0]. With pytest
        absent here this is allowed via the "not a test command" path, but
        we assert the recursion didn't happen by checking the next case."""
        result = hook.check(_bash("env -i gh pr comment 1"))
        # No pytest, no make test → allowed regardless of skip path. The
        # important assertion is the next test: env -i with pytest must still
        # block (i.e., we did NOT silently treat it as a gh invocation).
        self.assertIsNone(result)

    def test_env_dash_i_does_not_mask_pytest(self) -> None:
        """POS: `env -i gh pr comment --title 'pytest tests/'` is a contrived
        case but illustrates the safety: because the `-i` flag form is not
        recognised as a gh wrapper, the `--body`/`--body-file` skip is the
        only thing protecting us — and there's no `--body` here. But because
        `pytest` only appears inside `--title` (no `pytest` token outside it)
        the test-runner regex needs that text. Use a more direct example:
        `env -i pytest tests/` — the `-i` flag form is not a gh skip path,
        and pytest is the effective program. Must block."""
        result = hook.check(_bash("env -i pytest tests/"))
        assert result is not None, "env -i around pytest must still block"
        self.assertEqual(result.get("decision"), "block")

    def test_env_wrapper_does_not_match_envar_prefix_word(self) -> None:
        """POS: `environment_check pytest tests/` — leading token `environment_check`
        starts with `env` but is NOT the `env` builtin. Must not be confused
        for the wrapper; pytest is still the effective program → block."""
        result = hook.check(_bash("environment_check pytest tests/"))
        assert result is not None, "env-prefix lookalike token must not match `env`"
        self.assertEqual(result.get("decision"), "block")


class BodyFlagSkipTests(unittest.TestCase):
    """Short-circuit #2: --body / --body-file flags exempt the whole command."""

    def test_body_flag_in_non_gh_command(self) -> None:
        """NEG: `some-tool --body "$(cat pytest.txt)"` — intentionally broad skip
        per hook docstring. False-negatives on exotic tools are acceptable."""
        result = hook.check(_bash('some-tool --body "$(cat pytest.txt)"'))
        self.assertIsNone(result)

    def test_body_file_flag(self) -> None:
        """NEG: --body-file also triggers the skip (same rationale)."""
        result = hook.check(_bash("gh pr create --body-file /tmp/body.md"))
        self.assertIsNone(result)

    def test_body_equals_form(self) -> None:
        """NEG: --body=value (no space) also triggers the skip."""
        result = hook.check(_bash('gh pr comment 1 --body="pytest CVE"'))
        self.assertIsNone(result)

    def test_body_flag_false_friend_not_matched(self) -> None:
        """POS: `--body-foo` should NOT count as a body flag. With pytest present
        and no ENVIRONMENT=test, this should block (not gh, no real --body)."""
        result = hook.check(_bash("custom-tool --body-foo pytest"))
        assert result is not None, "--body-foo is not --body or --body-file"
        self.assertEqual(result.get("decision"), "block")


class PositiveMatchTests(unittest.TestCase):
    """Real test-runner commands must still block without ENVIRONMENT=test."""

    def test_bare_pytest_blocks(self) -> None:
        """POS: `pytest` alone — classic invocation."""
        result = hook.check(_bash("pytest"))
        assert result is not None
        self.assertEqual(result.get("decision"), "block")

    def test_pytest_with_path_blocks(self) -> None:
        """POS: `pytest tests/` — typical invocation."""
        result = hook.check(_bash("pytest tests/"))
        assert result is not None
        self.assertEqual(result.get("decision"), "block")

    def test_make_test_blocks(self) -> None:
        """POS: `make test` — make target."""
        result = hook.check(_bash("make test"))
        self.assertIsNotNone(result)

    def test_python_m_pytest_blocks(self) -> None:
        """POS: `python -m pytest` — module invocation."""
        result = hook.check(_bash("python -m pytest"))
        self.assertIsNotNone(result)

    def test_uv_run_pytest_blocks(self) -> None:
        """POS: `uv run pytest` — uv tool runner."""
        result = hook.check(_bash("uv run pytest"))
        self.assertIsNotNone(result)

    def test_env_prefix_with_real_pytest_still_blocks(self) -> None:
        """POS regression: leading env prefix with real test command must still
        block. `DEBUG=1 pytest tests/` has `pytest` as effective argv[0]."""
        result = hook.check(_bash("DEBUG=1 pytest tests/"))
        assert result is not None
        self.assertEqual(result.get("decision"), "block")


class EnvAlreadySetTests(unittest.TestCase):
    """ENVIRONMENT=test already present — must allow."""

    def test_env_set_on_pytest(self) -> None:
        """NEG: ENVIRONMENT=test already prepended — allow."""
        result = hook.check(_bash("ENVIRONMENT=test pytest tests/"))
        self.assertIsNone(result)

    def test_env_set_on_make_test(self) -> None:
        """NEG: ENVIRONMENT=test on make test — allow."""
        result = hook.check(_bash("ENVIRONMENT=test make test"))
        self.assertIsNone(result)


class NonTestCommandTests(unittest.TestCase):
    """Commands that don't match pytest/make-test regex must allow."""

    def test_ls_allowed(self) -> None:
        """NEG: `ls` — not a test command."""
        result = hook.check(_bash("ls -la"))
        self.assertIsNone(result)

    def test_empty_command_allowed(self) -> None:
        """NEG: empty command."""
        result = hook.check(_bash(""))
        self.assertIsNone(result)

    def test_make_other_target_allowed(self) -> None:
        """NEG: `make build` — not `make test`."""
        result = hook.check(_bash("make build"))
        self.assertIsNone(result)


class ChainedCommandTests(unittest.TestCase):
    """Issue #476: chains like `cd /path && pytest tests/` need env on the
    pytest segment, not on the leading `cd`. Pre-fix the hook (a) suggested
    a broken command and (b) accepted the broken command as valid (silent
    gate bypass). These tests pin the corrected per-segment behavior."""

    def test_cd_then_pytest_blocks_with_corrected_suggestion(self) -> None:
        """POS: `cd /path && pytest tests/` — block, suggestion places env
        on the pytest segment."""
        result = hook.check(_bash("cd /path && pytest tests/"))
        assert result is not None
        self.assertEqual(result.get("decision"), "block")
        self.assertIn("cd /path && ENVIRONMENT=test pytest tests/", result["reason"])

    def test_cd_then_env_pytest_allowed(self) -> None:
        """NEG: `cd /path && ENVIRONMENT=test pytest tests/` — allow; env
        is on the correct (pytest) segment."""
        result = hook.check(_bash("cd /path && ENVIRONMENT=test pytest tests/"))
        self.assertIsNone(result)

    def test_misplaced_env_before_cd_blocks(self) -> None:
        """POS: `ENVIRONMENT=test cd /path && pytest tests/` — BLOCK.

        This is the silent-bypass case from #476. The pre-fix hook
        accepted this command because `ENVIRONMENT=test` appeared
        anywhere in the string, even though shell semantics apply the
        env only to `cd` (where it has no effect) and pytest runs
        without it. The fix requires the env to be in the leading
        env-block of the pytest-bearing segment.
        """
        result = hook.check(_bash("ENVIRONMENT=test cd /path && pytest tests/"))
        assert result is not None, "misplaced env must not pass — that's the #476 bug"
        self.assertEqual(result.get("decision"), "block")
        self.assertIn("ENVIRONMENT=test pytest tests/", result["reason"])

    def test_two_pytest_segments_both_get_env(self) -> None:
        """POS: `pytest tests/ && pytest tests-other/` — block, suggestion
        prepends env to BOTH segments."""
        result = hook.check(_bash("pytest tests/ && pytest tests-other/"))
        assert result is not None
        self.assertEqual(result.get("decision"), "block")
        self.assertIn(
            "ENVIRONMENT=test pytest tests/ && ENVIRONMENT=test pytest tests-other/",
            result["reason"],
        )

    def test_two_pytest_segments_one_correct_still_blocks(self) -> None:
        """POS: `ENVIRONMENT=test pytest tests/ && pytest tests-other/` —
        block; second segment is missing env. Suggestion fixes the missing
        one and leaves the correct one alone."""
        result = hook.check(_bash("ENVIRONMENT=test pytest tests/ && pytest tests-other/"))
        assert result is not None
        self.assertEqual(result.get("decision"), "block")
        self.assertIn(
            "ENVIRONMENT=test pytest tests/ && ENVIRONMENT=test pytest tests-other/",
            result["reason"],
        )

    def test_two_pytest_segments_both_correct_allowed(self) -> None:
        """NEG: env on both pytest segments — allow."""
        result = hook.check(
            _bash("ENVIRONMENT=test pytest tests/ && ENVIRONMENT=test pytest tests-other/")
        )
        self.assertIsNone(result)

    def test_cd_then_make_test_blocks(self) -> None:
        """POS: `cd /path && make test` — chain form of make test."""
        result = hook.check(_bash("cd /path && make test"))
        assert result is not None
        self.assertEqual(result.get("decision"), "block")
        self.assertIn("cd /path && ENVIRONMENT=test make test", result["reason"])

    def test_cd_then_env_make_test_allowed(self) -> None:
        """NEG: `cd /path && ENVIRONMENT=test make test` — allow."""
        result = hook.check(_bash("cd /path && ENVIRONMENT=test make test"))
        self.assertIsNone(result)

    def test_misplaced_env_before_cd_with_make_test_blocks(self) -> None:
        """POS: `ENVIRONMENT=test cd /path && make test` — BLOCK, same
        silent-bypass shape as the pytest case."""
        result = hook.check(_bash("ENVIRONMENT=test cd /path && make test"))
        assert result is not None
        self.assertEqual(result.get("decision"), "block")
        self.assertIn("ENVIRONMENT=test make test", result["reason"])

    def test_cd_then_uv_run_pytest_preserves_form(self) -> None:
        """POS: realistic repro shape from #476 — `cd /worktree && uv run pytest …`.
        Suggestion preserves the `uv run pytest` tokens and only prepends env."""
        result = hook.check(
            _bash(
                "cd /home/x/worktree && uv run pytest "
                "tests/test_pipeline/test_reset.py --tb=line -q"
            )
        )
        assert result is not None
        self.assertEqual(result.get("decision"), "block")
        self.assertIn(
            "cd /home/x/worktree && ENVIRONMENT=test uv run pytest "
            "tests/test_pipeline/test_reset.py --tb=line -q",
            result["reason"],
        )

    def test_semicolon_separator_chain(self) -> None:
        """POS: `;` separator behaves like `&&` for segment splitting."""
        result = hook.check(_bash("cd /path ; pytest tests/"))
        assert result is not None
        self.assertEqual(result.get("decision"), "block")
        self.assertIn("ENVIRONMENT=test pytest tests/", result["reason"])

    def test_or_separator_chain(self) -> None:
        """POS: `||` separator also splits — even though running pytest
        only-if-cd-fails is unusual, treat it identically."""
        result = hook.check(_bash("cd /path || pytest tests/"))
        assert result is not None
        self.assertEqual(result.get("decision"), "block")

    def test_pipe_separator_chain(self) -> None:
        """POS: `|` (pipe) splits too. `pytest tests/ | tee out.log` —
        pytest must get the env."""
        result = hook.check(_bash("pytest tests/ | tee out.log"))
        assert result is not None
        self.assertEqual(result.get("decision"), "block")
        self.assertIn("ENVIRONMENT=test pytest tests/", result["reason"])

    def test_env_on_pipe_target_does_not_satisfy_pytest_segment(self) -> None:
        """POS: `pytest tests/ | ENVIRONMENT=test tee out.log` — the env is
        in the WRONG segment (on tee, not pytest). Must still block."""
        result = hook.check(_bash("pytest tests/ | ENVIRONMENT=test tee out.log"))
        assert result is not None
        self.assertEqual(result.get("decision"), "block")

    def test_no_chain_suggestion_format_unchanged(self) -> None:
        """POS: bare `pytest tests/` — single-segment suggestion is just
        `ENVIRONMENT=test pytest tests/` (no chain glue)."""
        result = hook.check(_bash("pytest tests/"))
        assert result is not None
        self.assertEqual(result.get("decision"), "block")
        self.assertIn("ENVIRONMENT=test pytest tests/", result["reason"])

    def test_extra_env_prefix_preserved_in_suggestion(self) -> None:
        """POS: `cd /path && DEBUG=1 pytest tests/` — env-block already has
        DEBUG=1; suggestion inserts ENVIRONMENT=test alongside, not
        replacing the existing assignment."""
        result = hook.check(_bash("cd /path && DEBUG=1 pytest tests/"))
        assert result is not None
        self.assertEqual(result.get("decision"), "block")
        self.assertIn(
            "cd /path && DEBUG=1 ENVIRONMENT=test pytest tests/",
            result["reason"],
        )


class ShortCircuitWithChainsTests(unittest.TestCase):
    """Verify gh/--body short-circuits remain whole-command (NOT per-segment)
    — i.e., a `gh` command at argv[0] exempts the entire chain even if a
    later segment mentions pytest."""

    def test_gh_at_argv0_with_pytest_in_later_segment(self) -> None:
        """NEG: `gh pr comment ... && echo "ran pytest"` — gh skip covers
        the whole command. (Contrived; documents the boundary.)"""
        result = hook.check(_bash('gh pr comment 1 --body "x" && echo "ran pytest"'))
        self.assertIsNone(result)

    def test_body_flag_covers_chain(self) -> None:
        """NEG: any command with --body anywhere exempts the whole chain."""
        result = hook.check(_bash('some-tool --body "pytest in body" && pytest tests/'))
        self.assertIsNone(result)


class QuoteAwareSplittingTests(unittest.TestCase):
    """Issue #478 case 1: quoted `&&`/`||`/`;`/`|` and quoted `pytest`
    tokens must NOT trigger segment-splitting or test-runner detection.

    Pre-fix: the regex split treated quoted separators as real and
    quoted pytest substrings as real invocations, producing both
    false-positive blocks and mangled suggestions that inserted env
    into the middle of a quoted string."""

    def test_quoted_amp_amp_inside_grep_pattern(self) -> None:
        """NEG: `git log --grep='fix && pytest' && echo done` — the
        inner `&&` is inside a single-quoted grep pattern; the `pytest`
        inside it is argument data, not a runner invocation. The OUTER
        `&& echo done` is the only real separator, and the only segment
        is `git log --grep=...` (no real pytest) + `echo done`. Allow.

        This is the case 1 repro from #478 — pre-fix the hook blocked
        with a mangled suggestion that inserted env inside the grep
        pattern."""
        result = hook.check(_bash("git log --grep='fix && pytest' && echo done"))
        self.assertIsNone(
            result,
            "quoted && inside grep pattern must not split, "
            "quoted pytest must not trigger test-runner detection",
        )

    def test_quoted_double_quoted_pytest_alone(self) -> None:
        """NEG: `echo "running pytest"` — pytest entirely inside double
        quotes is a string literal, not a runner invocation."""
        result = hook.check(_bash('echo "running pytest"'))
        self.assertIsNone(result)

    def test_quoted_separator_does_not_split(self) -> None:
        """NEG: `printf '%s' 'a;b|c&&d' ; pytest tests/` — quoted
        separators inside printf args must not split; the trailing
        real `;` does split, and the trailing real pytest segment
        triggers a block. Confirms the quote-state machine correctly
        re-enters unquoted state after the closing quote."""
        result = hook.check(_bash("printf '%s' 'a;b|c&&d' ; pytest tests/"))
        assert result is not None
        self.assertEqual(result.get("decision"), "block")
        # Splice should land on the trailing pytest segment, not inside
        # the quoted printf arg.
        self.assertIn("ENVIRONMENT=test pytest tests/", result["reason"])
        self.assertNotIn("ENVIRONMENT=testa;b", result["reason"])

    def test_backslash_escape_outside_quotes_protects_separator(self) -> None:
        """POS: `echo a \\&\\& pytest` — the escape protects the `&`
        from being recognised as part of `&&` (verifying the state
        machine's `in_escape` branch). So the whole string is ONE
        segment containing both `echo` and the literal `pytest` token.
        Because `pytest` IS in the segment (not inside quotes), it's
        flagged as a test invocation and blocked. This is the
        safe-direction over-block — operator can manually quote the
        `pytest` if it's data. Test pins the splice destination: env
        goes at the segment start (before `echo`), not somewhere
        absurd inside the escaped sequence."""
        result = hook.check(_bash(r"echo a \&\& pytest"))
        assert result is not None
        self.assertEqual(result.get("decision"), "block")
        # Splice prepends env to the single-segment command.
        self.assertIn(r"ENVIRONMENT=test echo a \&\& pytest", result["reason"])

    def test_quoted_pytest_with_real_pytest_in_other_segment(self) -> None:
        """POS: `echo "pytest is great" && pytest tests/` — the quoted
        pytest is data, the unquoted one is a real invocation. Block,
        suggestion places env on the real pytest segment ONLY."""
        result = hook.check(_bash('echo "pytest is great" && pytest tests/'))
        assert result is not None
        self.assertEqual(result.get("decision"), "block")
        self.assertIn(
            'echo "pytest is great" && ENVIRONMENT=test pytest tests/',
            result["reason"],
        )


class SubshellAwareTests(unittest.TestCase):
    """Issue #478 case 2: `(ENVIRONMENT=test pytest tests/)` — the env
    block is inside a subshell. Pre-fix the detector looked at the
    segment's leading tokens (which started with `(`) and missed the
    interior env-block, false-positive-blocking."""

    def test_subshell_with_env_inside_allowed(self) -> None:
        """NEG: `(ENVIRONMENT=test pytest tests/)` — env is on the
        correct (sub-)segment's program. Allow."""
        result = hook.check(_bash("(ENVIRONMENT=test pytest tests/)"))
        self.assertIsNone(result, "env inside subshell must be recognised")

    def test_subshell_without_env_blocks_with_inside_splice(self) -> None:
        """POS: `(pytest tests/)` — env missing inside subshell. Block,
        suggestion places env INSIDE the parens (not before them)."""
        result = hook.check(_bash("(pytest tests/)"))
        assert result is not None
        self.assertEqual(result.get("decision"), "block")
        self.assertIn("(ENVIRONMENT=test pytest tests/)", result["reason"])

    def test_subshell_with_debug_prefix_inside_allowed(self) -> None:
        """NEG: `(DEBUG=1 ENVIRONMENT=test pytest tests/)` — env-block
        inside subshell still allowed when ENVIRONMENT=test is one of
        the leading assignments."""
        result = hook.check(_bash("(DEBUG=1 ENVIRONMENT=test pytest tests/)"))
        self.assertIsNone(result)

    def test_subshell_splice_preserves_debug_prefix(self) -> None:
        """POS: `(DEBUG=1 pytest tests/)` — env missing, splice inside
        subshell preserves existing DEBUG=1."""
        result = hook.check(_bash("(DEBUG=1 pytest tests/)"))
        assert result is not None
        self.assertEqual(result.get("decision"), "block")
        self.assertIn("(DEBUG=1 ENVIRONMENT=test pytest tests/)", result["reason"])

    def test_chained_subshell_segment(self) -> None:
        """POS: `cd /path && (pytest tests/)` — chain with subshell as
        the test segment; splice into subshell, leave cd alone."""
        result = hook.check(_bash("cd /path && (pytest tests/)"))
        assert result is not None
        self.assertEqual(result.get("decision"), "block")
        self.assertIn("cd /path && (ENVIRONMENT=test pytest tests/)", result["reason"])

    def test_chained_subshell_with_env_inside_allowed(self) -> None:
        """NEG: `cd /path && (ENVIRONMENT=test pytest tests/)` — env on
        the correct (sub-)segment's program. Allow."""
        result = hook.check(_bash("cd /path && (ENVIRONMENT=test pytest tests/)"))
        self.assertIsNone(result)


class ControlFlowHardBlockTests(unittest.TestCase):
    """Issue #478 case 3: `for/while/until/if ... ; do pytest ; done` —
    the test segment is inside a control-flow construct where splicing
    `ENVIRONMENT=test` between the separator and the control-flow
    keyword would produce invalid shell.

    Per design decision (#478): HARD BLOCK with operator-readable
    diagnostic — never allow-with-log. Allow-with-log would silently
    bypass the very protection this hook exists for (the #420 prod-
    data-wipe class of failure). The diagnostic names the construct
    family and offers both inline-env (`do ENVIRONMENT=test pytest`)
    and pull-out (`ENVIRONMENT=test pytest a b`) alternatives so the
    operator picks the right shape and re-issues."""

    def test_for_do_pytest_done_hard_blocks_with_diagnostic(self) -> None:
        """POS: `for f in a b; do pytest $f; done` — splice between `;`
        and `do` would produce invalid shell. HARD BLOCK with manual-
        edit diagnostic; operator picks inline-env or pull-out."""
        result = hook.check(_bash("for f in a b; do pytest $f; done"))
        assert result is not None
        self.assertEqual(result.get("decision"), "block")
        # Diagnostic must name the construct family.
        self.assertIn("control-flow", result["reason"].lower())
        # Diagnostic must show both alternatives.
        self.assertIn("for f in a b; do ENVIRONMENT=test pytest", result["reason"])
        self.assertIn("ENVIRONMENT=test pytest a b", result["reason"])
        # Diagnostic must include the original command for operator review.
        self.assertIn("for f in a b; do pytest $f; done", result["reason"])

    def test_while_pytest_condition_hard_blocks(self) -> None:
        """POS: `while pytest --quick; do echo ok; done` — segment-
        leading token is `while` (a control-flow opener). Env
        assignments can only precede SIMPLE commands, not compound
        commands, so splicing `ENVIRONMENT=test while pytest ...` would
        be invalid shell. HARD BLOCK with diagnostic."""
        result = hook.check(_bash("while pytest --quick; do echo ok; done"))
        assert result is not None
        self.assertEqual(result.get("decision"), "block")
        self.assertIn("control-flow", result["reason"].lower())

    def test_if_pytest_condition_hard_blocks(self) -> None:
        """POS: `if pytest --smoke; then echo go; fi` — same shape as
        the while-condition: segment-leading token is `if` (opener
        keyword). Splice would be invalid. HARD BLOCK with diagnostic."""
        result = hook.check(_bash("if pytest --smoke; then echo go; fi"))
        assert result is not None
        self.assertEqual(result.get("decision"), "block")
        self.assertIn("control-flow", result["reason"].lower())

    def test_for_with_env_inside_do_body_hard_blocks(self) -> None:
        """POS-fall-through: `for f in a b; do ENVIRONMENT=test pytest $f; done`
        — env IS correctly placed in the body, but body-segment leading
        token is `do` (not the env assignment), so the env-block check
        misses it and the control-flow detector fires. Treated as HARD
        BLOCK to preserve the safety invariant: any test segment we
        can't analyze cleanly gets blocked, not allowed.

        Known false-positive — operator can work around by moving env
        outside the loop (`ENVIRONMENT=test pytest a b`). Documented
        in PR body caveats; future refinement could strip control-flow
        keywords before re-checking the env-block."""
        result = hook.check(_bash("for f in a b; do ENVIRONMENT=test pytest $f; done"))
        assert result is not None
        self.assertEqual(result.get("decision"), "block")

    def test_normal_pytest_after_control_flow_close_still_blocks(self) -> None:
        """POS: `for f in a b; do echo $f; done; pytest tests/` —
        control-flow construct closes with `done`, then a normal
        pytest segment follows. The trailing pytest is NOT inside the
        control-flow body and the splice IS safe there."""
        result = hook.check(_bash("for f in a b; do echo $f; done; pytest tests/"))
        assert result is not None
        self.assertEqual(result.get("decision"), "block")
        self.assertIn("done; ENVIRONMENT=test pytest tests/", result["reason"])

    def test_mixed_control_flow_and_real_block_combined_message(self) -> None:
        """POS: `for f in a b; do pytest $f; done && pytest other/` —
        first pytest is inside control-flow, second is a normal chain
        segment. Both block; the suggestion fixes the splice-able
        segment AND appends a note that the control-flow segment
        needs manual edit. Splice does NOT mangle the for-body
        (no broken `; ENVIRONMENT=test do`)."""
        result = hook.check(_bash("for f in a b; do pytest $f; done && pytest other/"))
        assert result is not None
        self.assertEqual(result.get("decision"), "block")
        # Splice-able segment gets the fix.
        self.assertIn("&& ENVIRONMENT=test pytest other/", result["reason"])
        # Control-flow segment is preserved verbatim (no mangle).
        self.assertNotIn("; ENVIRONMENT=test do", result["reason"])
        # Combined-message note alerts the operator to the control-flow segment.
        self.assertIn("control-flow", result["reason"].lower())
        self.assertIn("manually", result["reason"].lower())
        self.assertNotIn("; ENVIRONMENT=test do", result["reason"])


class NewlineSeparatorTests(unittest.TestCase):
    """Issue #537: an unescaped `\\n` between bash statements acts as a
    statement terminator (equivalent to `;`). Pre-fix the separator
    scanner only recognised `&&`/`||`/`;`/`|`, so multi-line scripts
    where pytest is on its own line had the prior line glued onto the
    pytest segment via `|`, producing mangled suggestions that prepended
    ENVIRONMENT=test to the wrong token (e.g. `head -3` instead of
    `pytest`)."""

    def test_newline_separator_allows_when_env_on_pytest_line(self) -> None:
        """NEG: multi-line script; env is in the pytest line's leading
        env-block. The prior-line pipe (`awk ... | head -3`) does NOT
        bleed into the pytest segment because `\\n` now splits. Allow."""
        command = (
            "cd /tmp\n"
            "awk '/foo/' some.txt | head -3\n"
            'echo "marker"\n'
            "ENVIRONMENT=test uv run pytest -q"
        )
        result = hook.check(_bash(command))
        self.assertIsNone(
            result,
            "newline must split segments so env on pytest line is recognised",
        )

    def test_newline_separator_blocks_when_env_missing_on_pytest_line(self) -> None:
        """POS: multi-line script with pytest on its own line and no env.
        Block, suggestion must prepend ENVIRONMENT=test IMMEDIATELY before
        `uv run pytest` — NOT before `echo` or `cd` or `head`."""
        command = 'cd /tmp\necho "marker"\nuv run pytest -q'
        result = hook.check(_bash(command))
        assert result is not None
        self.assertEqual(result.get("decision"), "block")
        self.assertIn("ENVIRONMENT=test uv run pytest -q", result["reason"])
        # The splice must not land on the prior segments.
        self.assertNotIn("ENVIRONMENT=test cd /tmp", result["reason"])
        self.assertNotIn('ENVIRONMENT=test echo "marker"', result["reason"])

    def test_newline_inside_single_quotes_not_a_separator(self) -> None:
        """NEG: a literal newline character inside `'...'` must NOT be
        recognised as a separator (quote-aware state machine stays
        in-quote). `awk '/foo\\nbar/' file | pytest tests/` — the `\\n`
        inside the awk pattern is data; the only real separator is the
        `|`, splitting awk-segment | pytest-segment. Pytest segment
        lacks env → block, splice on the pytest segment, NOT inside
        the awk pattern.

        Regression-guard so future refactors don't break the quote-
        aware split."""
        command = "awk '/foo\nbar/' file | pytest tests/"
        result = hook.check(_bash(command))
        assert result is not None
        self.assertEqual(result.get("decision"), "block")
        # Splice on pytest segment.
        self.assertIn("ENVIRONMENT=test pytest tests/", result["reason"])
        # Awk pattern must be preserved verbatim — no env inside the quoted region.
        self.assertNotIn("ENVIRONMENT=testbar", result["reason"])
        self.assertNotIn("'/fooENVIRONMENT=test", result["reason"])

    def test_backslash_line_continuation_not_a_separator(self) -> None:
        """POS: `ENVIRONMENT=test pytest a \\\n  b` — bash line-
        continuation; the backslash escapes the newline so it does NOT
        terminate the statement. The whole thing is one logical segment
        with env+pytest+both args. Existing `in_escape` flag in
        `_split_segments` handles this; the new newline-as-separator
        branch must not bypass it.

        Verifies: with env present on the (sole) segment, allow."""
        command = "ENVIRONMENT=test pytest a \\\n  b"
        result = hook.check(_bash(command))
        self.assertIsNone(
            result,
            "backslash-newline line-continuation must not be treated as separator",
        )


if __name__ == "__main__":
    unittest.main()
