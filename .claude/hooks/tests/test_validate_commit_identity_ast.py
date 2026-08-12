#!/usr/bin/env python3
"""bashlex Bash-AST parse path for validate_commit_identity (#748 D3b).

Splits into three concerns:

1. AST extraction (`_shell_parse.iter_command_segments_ast`) — structural
   segment extraction across quoting, backslash continuation, `$(...)`,
   `&&`/`;`/`|` chains, and env-var prefixes. These assert the AST path
   specifically, so they are skipped when bashlex is not installed.

2. AST-superiority over the shlex fallback — a `git commit` hidden inside a
   `$(...)` command substitution is a REAL invocation the shlex path cannot see
   (the substitution is one quoted token) but the AST surfaces. Skipped without
   bashlex.

3. Degraded-mode safety (ALWAYS runs) — with bashlex forced unavailable (or its
   parse forced to fail), the hook must not crash and must return the SAME
   verdict via the shlex/regex fallback.

Run: ENVIRONMENT=test python3 -m pytest \
        .claude/hooks/tests/test_validate_commit_identity_ast.py -v
"""

# This file's own hook-side import is an underscore-prefixed module
# whose name sorts alphabetically before `_test_helpers` — ruff's isort
# autofix would otherwise reorder it ahead of the sys.path bootstrap it
# depends on. See `_test_helpers.py`'s module docstring.
# isort: skip_file
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stderr
from unittest import mock

import _test_helpers  # noqa: E402,F401
import _shell_parse as sp  # noqa: E402
import validate_commit_identity as hook  # noqa: E402

_AINO = "Aino Virtanen"
_AINO_EMAIL = "parametrization+Aino.Virtanen@gmail.com"
_VALID = f'git -c user.name="{_AINO}" -c user.email="{_AINO_EMAIL}"'


_input = _test_helpers.bash_input


def _find_git_commit(segments: list[list[str]]) -> list[str] | None:
    """Return the first `git ... commit ...` segment from AST output, else None."""
    for segment in segments:
        decoded = sp.find_git_subcommand(segment)
        if decoded is None:
            continue
        _globals, rest = decoded
        if rest and rest[0] == "commit":
            return segment
    return None


@unittest.skipUnless(sp.bashlex_available(), "bashlex not installed — AST path inactive")
class AstExtractionTests(unittest.TestCase):
    """`iter_command_segments_ast` structural extraction (bashlex present)."""

    def test_quoted_value_kept_whole(self):
        segs = sp.iter_command_segments_ast(f'{_VALID} commit -m "multi word msg"')
        self.assertIsNotNone(segs)
        commit = _find_git_commit(segs)
        self.assertIsNotNone(commit)
        self.assertIn("user.name=Aino Virtanen", commit)
        self.assertIn("multi word msg", commit)

    def test_backslash_line_continuation(self):
        """#287: backslash-newline continuation resolves to one git commit."""
        cmd = (
            f'git -c user.name="{_AINO}" \\\n'
            f'    -c user.email="{_AINO_EMAIL}" \\\n'
            f'    commit -m "continued"'
        )
        segs = sp.iter_command_segments_ast(cmd)
        self.assertIsNotNone(segs)
        self.assertIsNotNone(_find_git_commit(segs))

    def test_env_prefix_stripped(self):
        """A leading KEY=value AssignmentNode is excluded from the segment."""
        segs = sp.iter_command_segments_ast(f"FOO=bar {_VALID} commit -m x")
        self.assertIsNotNone(segs)
        commit = _find_git_commit(segs)
        self.assertIsNotNone(commit)
        self.assertEqual(commit[0], "git")
        self.assertNotIn("FOO=bar", commit)

    def test_chains_and_pipes_split(self):
        for cmd in (
            f"{_VALID} commit -m a ; ls",
            f"{_VALID} commit -m a && ls",
            f"{_VALID} commit -m a | cat",
        ):
            with self.subTest(cmd=cmd):
                segs = sp.iter_command_segments_ast(cmd)
                self.assertIsNotNone(segs)
                self.assertIsNotNone(_find_git_commit(segs))

    def test_heredoc_body_is_not_a_command(self):
        """`cat <<EOF ... git commit ... EOF` — body is data, not a command."""
        cmd = "cat <<EOF\ngit commit -m sneaky\nEOF"
        segs = sp.iter_command_segments_ast(cmd)
        self.assertIsNotNone(segs)
        self.assertIsNone(_find_git_commit(segs))

    def test_commit_in_branch_name_not_a_subcommand(self):
        cmd = "git worktree add /tmp/wt -b feature/commit-identity origin/main"
        segs = sp.iter_command_segments_ast(cmd)
        self.assertIsNotNone(segs)
        self.assertIsNone(_find_git_commit(segs))

    def test_parse_error_returns_none(self):
        """Unbalanced quote → None so the caller falls back."""
        self.assertIsNone(sp.iter_command_segments_ast('git commit -m "unbalanced'))


@unittest.skipUnless(sp.bashlex_available(), "bashlex not installed — AST path inactive")
class AstSupersedesShlexTests(unittest.TestCase):
    """Cases the AST handles that the shlex fallback cannot."""

    def test_command_sub_with_valid_identity_allowed(self):
        result = hook.check(_input(f'{_VALID} commit -m "$(echo done)"'))
        self.assertIsNone(result)

    def test_commit_hidden_in_substitution_is_blocked(self):
        """A real `git commit` inside $(...) is surfaced by the AST and blocked.

        The shlex fallback keeps the whole `$(...)` as one quoted token and so
        cannot see this commit — this is the AST-superiority case, hence the
        skipUnless guard.
        """
        result = hook.check(_input('echo "$(git commit -m sneaky)"'))
        self.assertIsNotNone(result)
        assert result is not None  # for mypy
        self.assertEqual(result.get("decision"), "block")


class DegradedModeTests(unittest.TestCase):
    """bashlex forced unavailable — fallback must give the same verdict, no crash.

    Always runs (independent of whether bashlex is actually installed) by
    monkeypatching `_shell_parse._BASHLEX_AVAILABLE`, since both
    `bashlex_available()` and `iter_command_segments_ast()` read that module
    global at call time.
    """

    def setUp(self):
        # Reset the once-per-process warning latch so the warning test is
        # deterministic regardless of test ordering.
        hook._DEGRADED_WARNED = False

    def test_valid_commit_allowed_in_degraded_mode(self):
        with mock.patch.object(sp, "_BASHLEX_AVAILABLE", False):
            with redirect_stderr(io.StringIO()):
                result = hook.check(_input(f'{_VALID} commit -m "fallback ok"'))
        self.assertIsNone(result)

    def test_missing_identity_blocked_in_degraded_mode(self):
        with mock.patch.object(sp, "_BASHLEX_AVAILABLE", False):
            with redirect_stderr(io.StringIO()):
                result = hook.check(_input('git commit -m "no identity"'))
        self.assertIsNotNone(result)
        assert result is not None  # for mypy
        self.assertEqual(result.get("decision"), "block")

    def test_degraded_mode_emits_single_warning(self):
        with mock.patch.object(sp, "_BASHLEX_AVAILABLE", False):
            buf = io.StringIO()
            with redirect_stderr(buf):
                hook.check(_input(f'{_VALID} commit -m "one"'))
                hook.check(_input(f'{_VALID} commit -m "two"'))
            stderr = buf.getvalue()
        self.assertEqual(stderr.count("degraded regex mode"), 1, stderr)
        self.assertIn("bashlex not installed", stderr)

    def test_no_crash_on_messy_command_in_degraded_mode(self):
        """A heredoc-in-$() shape must not crash the fallback path."""
        cmd = f"{_VALID} commit -m \"$(cat <<'EOF'\nmulti\nline\nEOF\n)\""
        with mock.patch.object(sp, "_BASHLEX_AVAILABLE", False):
            with redirect_stderr(io.StringIO()):
                result = hook.check(_input(cmd))
        self.assertIsNone(result)


class EvalPayloadParserPathTests(unittest.TestCase):
    """#1399: `_eval_payloads` must give the same verdict on BOTH parser paths.

    The walker prefers the bashlex AST and falls back to shlex + segment split.
    The two disagree on detail — shlex leaves `x;` glued into one token, so the
    `eval` segment of `eval git commit -m x; echo done` swallows the trailing
    `echo done` — and the verdict must survive that: `_INNER_COMMIT_RE` bounds
    the `git` → `commit` bridge at `;`, so the bridge inside the eval body is
    what matches either way.

    The third path is deliberate too, and it is NOT fail-closed: when NEITHER
    parser can read the command, `_eval_payloads` returns [] and `_EVAL_RE`'s
    sweep backstops the QUOTED spelling only — its bare branch is still the
    `\\S+` that #1399 exists to fix, so the UNQUOTED spelling is ALLOWED there.
    Both halves of that matrix are asserted below so the residual is pinned
    rather than implied; #1444 tracks the fix.
    """

    _BYPASS = "eval git commit -m x"

    def _blocked(self, cmd: str) -> bool:
        with redirect_stderr(io.StringIO()):
            return hook.check(_input(cmd)) is not None

    def test_ast_path_resolves_eval_payload(self):
        self.assertEqual(hook._eval_payloads(self._BYPASS), ["git commit -m x"])
        self.assertTrue(self._blocked(self._BYPASS))

    def test_shlex_path_resolves_eval_payload(self):
        """bashlex forced off — the shlex segment split must still find it."""
        with mock.patch.object(sp, "_BASHLEX_AVAILABLE", False):
            with redirect_stderr(io.StringIO()):
                self.assertEqual(hook._eval_payloads(self._BYPASS), ["git commit -m x"])
            self.assertTrue(self._blocked(self._BYPASS))
            self.assertTrue(self._blocked(f"{self._BYPASS}; echo done"))
            self.assertFalse(self._blocked("eval echo hello"))
            self.assertFalse(self._blocked("eval $cmd"))

    def test_bashlex_parse_failure_falls_back_to_shlex(self):
        """bashlex present but returning None (the #748 fallthrough path)."""
        with mock.patch.object(hook, "iter_command_segments_ast", return_value=None):
            self.assertEqual(hook._eval_payloads(self._BYPASS), ["git commit -m x"])
            self.assertTrue(self._blocked(self._BYPASS))

    def test_both_parsers_failing_yields_no_payload_but_regex_backstops(self):
        """Unparseable input → [] from the walker; `_EVAL_RE` backstops the
        QUOTED spelling and NOT the unquoted one.

        Both halves are asserted. The `assertFalse` is the important one: it
        pins #1444's residual as a measured fact instead of leaving the
        narrowing to a docstring. Shaping this test only around the passing
        half is what made the hole survive the first review round — an
        assertion that never exercises the failing cell is inert against the
        failure it is named for. When #1444 lands, this flips to assertTrue.
        """
        with mock.patch.object(hook, "iter_command_segments_ast", return_value=None):
            with mock.patch.object(hook, "tokenize", return_value=None):
                self.assertEqual(hook._eval_payloads(self._BYPASS), [])
                self.assertTrue(self._blocked("eval 'git commit -m x'"))
                self.assertFalse(self._blocked(self._BYPASS))

    def test_unparseable_unquoted_eval_is_allowed_unmocked(self):
        """The same residual with NO mocks, on input that really commits.

        A single trailing backslash defeats both parsers for real: bashlex
        raises on unexpected EOF and shlex raises "No escaped character", so
        there are no segments to filter. Verified against real `zsh -c` in a
        fresh repo — the string below creates a commit. #1444.
        """
        cmd = f"eval {_VALID} commit -m x\\"
        self.assertEqual(hook._eval_payloads(cmd), [])
        self.assertFalse(self._blocked(cmd))

    def test_eval_not_at_segment_head_is_allowed(self):
        """#1443's mechanism, kept distinct from #1444's — a DIFFERENT bug.

        These parse fine; `eval` just is not `seg[0]`, so the filter in
        `_eval_payloads` skips the segment. They therefore never reach the
        `_EVAL_RE` fallback, and widening that regex on the parse-failure path
        would not close them. Both shapes create a real commit under `zsh -c`.
        This is here so that fixing #1444 alone cannot be mistaken for closing
        the residual.
        """
        for cmd in ("{ eval git commit -m x }", "builtin eval git commit -m x"):
            with self.subTest(cmd=cmd):
                self.assertEqual(hook._eval_payloads(cmd), [])
                self.assertFalse(self._blocked(cmd))
        # CONTROL: the same brace group WITHOUT `eval` blocks, which is what
        # attributes the miss to the wrapper rather than to the braces.
        self.assertTrue(self._blocked("{ git commit -m x }"))


class EvalDegradedModeOverBlockTests(unittest.TestCase):
    """#1445: with bashlex ABSENT, an `eval` segment swallows a later commit.

    The shlex fallback does not split `zsh);` or `hi;` into a standalone `;`
    token, so the `eval` segment never ends and the real `git … commit` behind
    it lands inside the eval payload. `_INNER_COMMIT_RE`'s `[^;&|]` bridge is
    satisfied because the `;` sits before `git`, not between `git` and the
    verb — and an indirect-exec match blocks UNCONDITIONALLY, so each of these
    is a hard stop on a correctly-identified, identity-carrying commit.

    This is a REGRESSION against `main`, not a pre-existing hole, and bashlex
    absent is a mode `_shell_parse.py` explicitly supports. It is the cell the
    two existing classes each covered half of: `EvalDetectionFalsePositiveTests`
    measures false positives on the bashlex path only, and
    `test_shlex_path_resolves_eval_payload` covers the shlex path but only with
    innocent payloads (`eval echo hello`, `eval $cmd`) that carry no following
    commit. When #1445 lands, these assertions flip to `assertIsNone`.
    """

    def _blocked_degraded(self, cmd: str) -> bool:
        with mock.patch.object(sp, "_BASHLEX_AVAILABLE", False):
            with redirect_stderr(io.StringIO()):
                return hook.check(_input(cmd)) is not None

    def _blocked_normal(self, cmd: str) -> bool:
        with redirect_stderr(io.StringIO()):
            return hook.check(_input(cmd)) is not None

    def test_eval_segment_swallows_following_commit_without_bashlex(self):
        for cmd in (
            f"eval $(direnv hook zsh); {_VALID} commit -m x",
            f"eval echo hi; {_VALID} commit -m x",
        ):
            with self.subTest(cmd=cmd):
                # Correct on the bashlex path — which is what makes the
                # degraded-mode result a regression rather than a constant.
                self.assertFalse(self._blocked_normal(cmd), "bashlex path")
                self.assertTrue(self._blocked_degraded(cmd), "#1445 residual")

    def test_innocent_eval_alone_is_unaffected_degraded(self):
        """CONTROL: with no commit behind it, the swallowed segment is inert —
        the over-block needs a following `git … commit`, not just an `eval`."""
        self.assertFalse(self._blocked_degraded("eval $(direnv hook zsh)"))
        self.assertFalse(self._blocked_degraded("eval echo hi"))


class BashlexParseFailureFallthroughTests(unittest.TestCase):
    """bashlex present but its parse returns None → fall through to shlex path."""

    def test_parse_failure_falls_through_to_shlex(self):
        # Patch the name in the HOOK module namespace (it `from _shell_parse
        # import iter_command_segments_ast`s a bound reference), not in sp.
        with mock.patch.object(hook, "iter_command_segments_ast", return_value=None):
            # bashlex_available() stays True, so no degraded warning; the hook
            # must still validate via the shlex tokenizer.
            valid = hook.check(_input(f'{_VALID} commit -m "shlex path"'))
            self.assertIsNone(valid)
            blocked = hook.check(_input('git commit -m "no id"'))
            self.assertIsNotNone(blocked)


if __name__ == "__main__":
    unittest.main()
