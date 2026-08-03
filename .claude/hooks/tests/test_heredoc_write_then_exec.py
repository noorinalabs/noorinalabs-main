#!/usr/bin/env python3
"""Regression tests for main#1167 — heredoc written to a file, executed later
in the SAME command, bypasses the commit-identity gate. Sibling of the
main#1150 under-matching umbrella (found by the PR #1155 merge-gate review,
Aino Virtanen, while constructing bypass shapes outside that PR's own corpus).

Shape
=====

    cat > /tmp/s.txt <<'DELIM'
    git -c user.name="X" -c user.email="Y" commit -m z
    DELIM
    bash /tmp/s.txt

Measured ALLOW at both `fea0dca` (main) and `e163320` (PR #1155 head) — a
pre-existing gap, not a #1155 regression. Every existing matcher misses it for
a distinct reason (see the #1167 issue body and the `main#1167` block comment
in `_shell_parse.py` above `_segment_write_targets` for the full account):

  - `_HEREDOC_RE` requires an interpreter textually BEFORE the `<<` — absent.
  - `_shell_parse.classify_heredocs` resolved the owner to `cat` (a data
    sink) and followed only `|` downstream; a `;`/newline-separated later
    command is not in the pipeline, so the body was classified DATA.
  - `_SCRIPT_INVOKE_RE` DOES match `bash /tmp/s.txt` and calls
    `_read_script_if_safe`, but the hook fires PreToolUse, so the file does
    not exist yet — the read fails and no content is inspected.

The fix (issue's preferred option 1) stays inside the classifier: when a
heredoc's owning segment redirects the body into a file (`cat > FILE`, or
`tee FILE` as a positional argument), and ANY segment elsewhere in the same
command later invokes a `SHELL_INTERPRETERS` member with that same file as its
script operand, the body is reclassified as CODE.

Run: python3 -m pytest .claude/hooks/tests/test_heredoc_write_then_exec.py -v
"""

from __future__ import annotations

import unittest

import _test_helpers  # noqa: E402,F401
import validate_commit_identity as hook  # noqa: E402
from _shell_parse import (  # noqa: E402
    classify_heredocs,
    parse_interpreter_invocation,
    strip_data_heredocs,
)

REAL_COMMIT = 'git -c user.name="X" -c user.email="Y" commit -m z'
DOC_LINE = "the bypass shape looks like: bash -c 'git commit -m x'"


def _bash(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


class WriteThenExecBypassBlocksTests(unittest.TestCase):
    """The bypass shapes the fix exists to close, through the real `check()`."""

    def _assert_blocked(self, cmd: str) -> None:
        result = hook.check(_bash(cmd))
        self.assertIsNotNone(result, f"write-then-exec must block: {cmd!r}")
        assert result is not None
        self.assertEqual(result["decision"], "block")
        self.assertIn("indirect-exec", result["reason"])

    def test_literal_issue_repro_newline_variant(self):
        """The exact reproduction from the #1167 issue body."""
        self._assert_blocked(f"cat > /tmp/s.txt <<'DELIM'\n{REAL_COMMIT}\nDELIM\nbash /tmp/s.txt")

    def test_semicolon_variant(self):
        """The issue's stated equivalent: `; bash FILE` chained onto the
        OPENER line itself, before the heredoc's first newline. This is the
        shape that defeats a naive fix built on `iter_interpreter_invocations`
        (its `strip_heredocs` call erases same-line trailing text after a
        heredoc opener) — see the module comment in `_shell_parse.py`."""
        self._assert_blocked(f"cat <<'DELIM' > /tmp/x; bash /tmp/x\n{REAL_COMMIT}\nDELIM")

    def test_append_redirect(self):
        """`>>` append, not just `>`."""
        self._assert_blocked(f"cat >> /tmp/s.txt <<'DELIM'\n{REAL_COMMIT}\nDELIM\nbash /tmp/s.txt")

    def test_tee_sink(self):
        """`tee` writes to its own positional argument, not via `>` redirect."""
        self._assert_blocked(f"tee /tmp/s.txt <<'DELIM'\n{REAL_COMMIT}\nDELIM\nsh /tmp/s.txt")

    def test_tee_sink_with_append_flag(self):
        self._assert_blocked(f"tee -a /tmp/s.txt <<'DELIM'\n{REAL_COMMIT}\nDELIM\nbash /tmp/s.txt")

    def test_zsh_interpreter(self):
        self._assert_blocked(f"cat > /tmp/s.txt <<'DELIM'\n{REAL_COMMIT}\nDELIM\nzsh /tmp/s.txt")

    def test_dash_interpreter(self):
        self._assert_blocked(f"cat > /tmp/s.txt <<'DELIM'\n{REAL_COMMIT}\nDELIM\ndash /tmp/s.txt")

    def test_env_prefixed_interpreter(self):
        """`env bash FILE` — already correlates via the pre-existing
        `strip_command_prefixes` wrapper-stripping, no new mechanism needed."""
        self._assert_blocked(
            f"cat > /tmp/s.txt <<'DELIM'\n{REAL_COMMIT}\nDELIM\nenv bash /tmp/s.txt"
        )

    def test_absolute_interpreter_path(self):
        self._assert_blocked(
            f"cat > /tmp/s.txt <<'DELIM'\n{REAL_COMMIT}\nDELIM\n/bin/bash /tmp/s.txt"
        )

    def test_dot_slash_prefix_normalization(self):
        """Write target spelled `./s.txt`, invocation spelled `s.txt` — the
        same file, different literal spelling. `_normalize_path_for_compare`
        (`os.path.normpath`) unifies them without resolving against a cwd."""
        self._assert_blocked(f"cat > ./s.txt <<'DELIM'\n{REAL_COMMIT}\nDELIM\nbash s.txt")

    def test_positionally_agnostic_invocation_before_write(self):
        """The correlation does not require the invocation to come AFTER the
        write — a conservative, deliberate choice (see module comment)."""
        self._assert_blocked(f"bash /tmp/s.txt\ncat > /tmp/s.txt <<'DELIM'\n{REAL_COMMIT}\nDELIM")

    def test_identical_literal_variable_target(self):
        """Not variable RESOLUTION — literal token equality. Both positions
        spell the identical token `$F`, so it still correlates even though
        the hook never evaluates what `$F` expands to."""
        self._assert_blocked(f'cat > "$F" <<\'DELIM\'\n{REAL_COMMIT}\nDELIM\nbash "$F"')

    def test_classifier_marks_the_span_code(self):
        """Pinned at the primitive too, so a failure localises to the
        classifier rather than only to the hook's verdict."""
        (span,) = classify_heredocs(
            f"cat > /tmp/s.txt <<'DELIM'\n{REAL_COMMIT}\nDELIM\nbash /tmp/s.txt"
        )
        self.assertTrue(span.is_code)

    def test_strip_data_heredocs_keeps_the_body(self):
        """The OTHER call site of the shared classification decision — pinned
        independently so a fix applied to only one of the two duplicate
        call sites (the main#1152 drift hazard) is caught here."""
        cmd = f"cat > /tmp/s.txt <<'DELIM'\n{REAL_COMMIT}\nDELIM\nbash /tmp/s.txt"
        out = strip_data_heredocs(cmd)
        self.assertIn("commit", out)


class WriteThenExecFalsePositiveTests(unittest.TestCase):
    """A legitimate `cat > FILE <<'EOF' ... EOF` with no later interpreter
    invocation on that file must still pass — the direction this fix must NOT
    regress."""

    def _assert_allowed(self, cmd: str) -> None:
        result = hook.check(_bash(cmd))
        self.assertIsNone(
            result,
            f"legitimate write with no later exec must not block: {cmd!r} "
            f"(got: {result['reason'].splitlines()[0] if result else ''})",
        )

    def test_plain_write_no_later_invocation(self):
        """The canonical legitimate shape named in the spawn brief."""
        self._assert_allowed("cat > README.md <<'EOF'\nSome documentation.\nEOF")

    def test_write_followed_by_unrelated_command(self):
        self._assert_allowed("cat > /tmp/n.md <<'EOF'\nnot a commit\nEOF\nls -la")

    def test_write_followed_by_invocation_of_a_different_file(self):
        """A real interpreter invocation elsewhere in the command must not
        make an UNRELATED heredoc's file target look executed — correlation
        is per-path, not "any interpreter invocation anywhere flips
        everything to code"."""
        self._assert_allowed(
            "cat > /tmp/s.txt <<'EOF'\nnot a commit\nEOF\nbash /tmp/other-script.sh"
        )

    def test_doc_line_written_then_unrelated_invocation(self):
        self._assert_allowed(f"cat > /tmp/n.md <<'EOF'\n{DOC_LINE}\nEOF\nbash /tmp/build.sh")

    def test_two_writes_only_one_later_invoked(self):
        """Multi-heredoc command: only the SECOND file is later invoked, and
        only its span must flip to code."""
        cmd = (
            "cat > /tmp/a.txt <<'E1'\njust prose, not code\nE1\n"
            f"cat > /tmp/b.txt <<'E2'\n{REAL_COMMIT}\nE2\n"
            "bash /tmp/b.txt"
        )
        first, second = classify_heredocs(cmd)
        self.assertFalse(first.is_code, "the unreferenced /tmp/a.txt heredoc must stay data")
        self.assertTrue(second.is_code, "the /tmp/b.txt heredoc, later invoked, must be code")

    def test_tee_write_no_later_invocation(self):
        self._assert_allowed("tee /tmp/n.md <<'EOF'\nnot a commit\nEOF")

    def test_write_target_never_invoked_even_with_other_interpreters_present(self):
        """A command that legitimately mentions/invokes bash for something
        else entirely (a different script) must not implicate an unrelated
        write."""
        self._assert_allowed("cat > /tmp/notes.md <<'EOF'\nsome notes\nEOF\nbash -c 'echo hello'")


class WriteThenExecMutationCoverageTests(unittest.TestCase):
    """Targeted assertions that pin the SPECIFIC branch each mutation test in
    the PR report exercises — see the report table for the paired
    weaken-and-observe-failure evidence."""

    def test_correlation_requires_write_AND_invocation_both(self):
        """Neither half alone is sufficient: a write with no invocation is
        data (already covered), and — pinned here — an invocation with no
        corresponding write must not retroactively make an unrelated data
        heredoc code."""
        cmd = "cat > /tmp/a.txt <<'EOF'\nnot code\nEOF\nbash /tmp/never-written.sh"
        (span,) = classify_heredocs(cmd)
        self.assertFalse(span.is_code)

    def test_append_and_plain_redirect_both_correlate(self):
        plain = classify_heredocs(f"cat > /tmp/x <<'D'\n{REAL_COMMIT}\nD\nbash /tmp/x")[0]
        append = classify_heredocs(f"cat >> /tmp/x <<'D'\n{REAL_COMMIT}\nD\nbash /tmp/x")[0]
        self.assertTrue(plain.is_code)
        self.assertTrue(append.is_code)


class StdinRedirectOperandTests(unittest.TestCase):
    """main#1170 — `bash < FILE` (script fed via stdin redirect, not a
    positional operand) escaped the write-then-exec correlation above because
    `parse_interpreter_invocation` folded the redirect into `operands` as the
    literal tokens `("<", FILE)` rather than resolving to `FILE` itself, so
    `_script_invocation_targets` collected the garbage path `"<"` and never
    saw `FILE`. This is also main#1287 shape 1, filed as an acknowledged gap
    in that same operand resolution; fixing it here closes both the FIFO
    relay (main#1170's own shape) and the plain-file form (main#1287 shape
    1) as the SAME fix — main#1287 shapes 2 (`$(...)`-produced path) and 3
    (`cp` copy indirection) are untouched and stay filed there, so main#1287
    itself stays open.

    Hand-verified against a real shell before writing these tests: a marker
    proxy `git` on PATH (never the real `git`) logs its own invocation to a
    file; both FIFO shapes below were confirmed to reach that marker under
    both `bash` and `zsh` (i.e. the body genuinely executes), matching the
    #1170 issue body's own claim.
    """

    def _assert_blocked(self, cmd: str) -> None:
        result = hook.check(_bash(cmd))
        self.assertIsNotNone(result, f"stdin-redirect relay must block: {cmd!r}")
        assert result is not None
        self.assertEqual(result["decision"], "block")
        self.assertIn("indirect-exec", result["reason"])

    def _assert_allowed(self, cmd: str) -> None:
        result = hook.check(_bash(cmd))
        self.assertIsNone(
            result,
            f"must allow: {cmd!r} (got: {result['reason'].splitlines()[0] if result else ''})",
        )

    # --- The issue's own shapes -------------------------------------------

    def test_issue_repro_mkfifo_bash_stdin(self):
        """The exact reproduction from the #1170 issue body."""
        self._assert_blocked(f"mkfifo p; bash < p & cat <<'D' > p\n{REAL_COMMIT}\nD")

    def test_issue_repro_mkfifo_sh_stdin_via_tee(self):
        """The issue's second measured shape: `sh` (not `bash`) reading via a
        FIFO written by `tee` (not `cat`)."""
        self._assert_blocked(f"mkfifo p2; sh < p2 & tee p2 <<'D' > /dev/null\n{REAL_COMMIT}\nD")

    # --- Same fix, main#1287 shape 1's plain-file (non-FIFO) form ----------

    def test_plain_file_stdin_redirect_no_fifo(self):
        """main#1287 shape 1 exactly: no `mkfifo`, no backgrounding — just an
        ordinary regular file written by a heredoc and later fed to `bash`
        via `< FILE`. Confirms the fix is the SAME correlation, not something
        FIFO-specific."""
        self._assert_blocked(f"cat > /tmp/s.txt <<'DELIM'\n{REAL_COMMIT}\nDELIM\nbash < /tmp/s.txt")

    def test_zsh_stdin_redirect(self):
        self._assert_blocked(f"cat > /tmp/s.txt <<'DELIM'\n{REAL_COMMIT}\nDELIM\nzsh < /tmp/s.txt")

    def test_dot_slash_prefix_normalization_applies_to_stdin_form_too(self):
        self._assert_blocked(f"cat > ./s.txt <<'DELIM'\n{REAL_COMMIT}\nDELIM\nbash < s.txt")

    def test_positionally_agnostic_stdin_form(self):
        """Correlation does not require the invocation to come after the
        write, matching the existing positional-operand form's behaviour."""
        self._assert_blocked(f"bash < /tmp/s.txt\ncat > /tmp/s.txt <<'DELIM'\n{REAL_COMMIT}\nDELIM")

    def test_flag_before_stdin_redirect(self):
        """`bash -x < FILE` — a leading option must not shift the redirect out
        of view; the option-run boundary always halts at a bare `<`."""
        self._assert_blocked(
            f"cat > /tmp/s.txt <<'DELIM'\n{REAL_COMMIT}\nDELIM\nbash -x < /tmp/s.txt"
        )

    def test_env_prefixed_stdin_redirect(self):
        self._assert_blocked(
            f"cat > /tmp/s.txt <<'DELIM'\n{REAL_COMMIT}\nDELIM\nenv bash < /tmp/s.txt"
        )

    def test_last_redirect_wins(self):
        """`bash < /tmp/other < /tmp/s.txt` — two stdin redirects on one
        invocation; a real shell honours only the LAST one, and so must this
        correlation. Written to correlate on the SECOND path only: if the
        implementation picked the first instead, this would wrongly ALLOW."""
        self._assert_blocked(
            f"cat > /tmp/s.txt <<'DELIM'\n{REAL_COMMIT}\nDELIM\nbash < /tmp/other < /tmp/s.txt"
        )

    def test_classifier_marks_the_span_code(self):
        (span,) = classify_heredocs(
            f"cat > /tmp/s.txt <<'DELIM'\n{REAL_COMMIT}\nDELIM\nbash < /tmp/s.txt"
        )
        self.assertTrue(span.is_code)

    def test_strip_data_heredocs_keeps_the_body(self):
        """The other call site of the shared classification decision (the
        main#1152 drift hazard) — pinned independently, matching the
        positional-operand form's own coverage above."""
        cmd = f"cat > /tmp/s.txt <<'DELIM'\n{REAL_COMMIT}\nDELIM\nbash < /tmp/s.txt"
        out = strip_data_heredocs(cmd)
        self.assertIn("commit", out)

    # --- False positives: must NOT newly block ------------------------------

    def test_stdin_redirect_to_an_unrelated_file_stays_allowed(self):
        """`bash < FILE` where FILE is never written by any heredoc in the
        same command — an everyday ops pattern (`bash < deploy.sh`,
        `mysql < backup.sql`) — must not be swept in by proximity alone."""
        self._assert_allowed("cat > /tmp/notes.md <<'EOF'\nsome notes\nEOF\nbash < /tmp/deploy.sh")

    def test_no_heredoc_at_all_stdin_redirect_stays_allowed(self):
        """The ordinary, extremely common shape this fix must not touch:
        feeding an EXISTING script to an interpreter via stdin, with no
        heredoc anywhere in the command."""
        self._assert_allowed("bash < /tmp/some-existing-deploy.sh")

    def test_non_interpreter_stdin_redirect_is_not_touched(self):
        """`mysql` is not a `SHELL_INTERPRETERS` member — a heredoc written to
        a file later fed to a non-shell program via `<` must stay data."""
        self._assert_allowed(
            "cat > /tmp/backup.sql <<'EOF'\nSELECT 1;\nEOF\nmysql < /tmp/backup.sql"
        )

    def test_process_substitution_is_not_mistaken_for_a_bare_redirect(self):
        """`bash <(cmd)` fuses into ONE shlex token (`<(cmd)`, no internal
        whitespace) and must not be parsed as a bare `<` redirect — a
        pre-existing, unrelated matcher (`_PROCESS_SUB_RE`) already handles
        process substitution; this fix must not double up or misfire on it."""
        self._assert_allowed("cat > /tmp/notes.md <<'EOF'\nsome notes\nEOF\nbash <(echo hi)")

    def test_process_substitution_followed_by_the_write_target_stays_allowed(self):
        """`bash <(true) /tmp/s.txt` — real-shell semantics: `/tmp/s.txt` is
        passed as `$1` to the process-substituted script, NOT executed as the
        interpreter's own script, so this must stay ALLOW even though
        `/tmp/s.txt` is also the heredoc's write target. Discriminates a
        `tok.startswith("<")` mutant from the correct `tok == "<"` exact
        match: a fused token like `<(true)` merely STARTS with `<` but is not
        a bare redirect, and a `startswith` mutant would misparse it as one,
        wrongly promoting `/tmp/s.txt` to `operands[0]` and over-blocking a
        legitimate command — the false-positive-corpus check this file's
        standards require."""
        self._assert_allowed(
            f"cat > /tmp/s.txt <<'DELIM'\n{REAL_COMMIT}\nDELIM\nbash <(true) /tmp/s.txt"
        )

    def test_command_string_form_with_a_stdin_redirect_is_unaffected(self):
        """`bash -c '...' < FILE` — `has_command_string` is True, so this
        invocation is skipped by the write-then-exec correlation entirely
        (as it already is for the positional-operand form); adding stdin-
        redirect resolution must not change that branch's behaviour."""
        self._assert_allowed(
            "cat > /tmp/s.txt <<'EOF'\nsome notes\nEOF\nbash -c 'echo hi' < /tmp/s.txt"
        )

    def test_1152_false_positive_still_allowed(self):
        """The over-broad-rule false positive this whole family of fixes must
        never resurrect: an interpreter word appearing earlier in a command
        that later starts an unrelated data heredoc."""
        self._assert_allowed("bash build.sh && cat > notes.md <<'EOF'\nsome docs\nEOF")

    # --- Unit-level pins on parse_interpreter_invocation --------------------

    def test_operand_resolves_to_the_redirect_target(self):
        inv = parse_interpreter_invocation(["bash", "<", "/tmp/s.txt"])
        self.assertEqual(inv.operands, ("/tmp/s.txt",))
        self.assertFalse(inv.has_command_string)

    def test_operand_last_redirect_wins_at_the_primitive(self):
        inv = parse_interpreter_invocation(["bash", "<", "/tmp/a", "<", "/tmp/b"])
        self.assertEqual(inv.operands[0], "/tmp/b")

    def test_trailing_bare_redirect_with_nothing_after_does_not_crash(self):
        """`bash <` with no following token — a malformed/truncated command a
        real shell would reject, but the parser must not raise."""
        inv = parse_interpreter_invocation(["bash", "<"])
        self.assertIsNotNone(inv)
        self.assertEqual(inv.operands, ("<",))

    def test_process_substitution_token_untouched_at_the_primitive(self):
        inv = parse_interpreter_invocation(["bash", "<(echo hi)"])
        self.assertEqual(inv.operands, ("<(echo hi)",))

    def test_process_substitution_with_a_following_operand_untouched(self):
        """A fused `<(...)` token followed by ANOTHER operand — the case that
        actually exercises the exact-match guard, since a single-token
        invocation never reaches the `j + 1 < n` bounds check at all."""
        inv = parse_interpreter_invocation(["bash", "<(true)", "x"])
        self.assertEqual(inv.operands, ("<(true)", "x"))

    def test_words_still_superset_of_operands_with_a_redirect(self):
        inv = parse_interpreter_invocation(["bash", "-x", "<", "/tmp/s.txt"])
        self.assertTrue(set(inv.operands).issubset(set(inv.words)))

    # --- Incidental side effect: the pre-existing shape-7 script-content
    # walker in validate_commit_identity.py also reads `operands[0]`
    # (`_read_script_if_safe(invocation.operands[0], cwd)`), so it silently
    # benefits from this same resolution for a script that already exists ON
    # DISK (unlike the write-then-exec case, where the file does not exist
    # yet when the PreToolUse hook fires). Pinned here as a regression guard,
    # not claimed as part of main#1170's own scope — it is the SAME operand
    # slot, read by a completely different, pre-existing consumer.

    def test_incidental_shape_7_now_reads_stdin_redirected_scripts_too(self):
        """Before this fix: `bash < FILE` left `operands[0] == "<"`, so
        `_read_script_if_safe` was handed a nonexistent path and the hidden
        commit in an ALREADY-ON-DISK script went undetected. After: the
        stdin form is symmetric with the pre-existing, already-trusted
        positional form (`bash FILE`)."""
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            script_path = f"{d}/existing_script.sh"
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(REAL_COMMIT + "\n")
            result = hook.check(
                {"tool_name": "Bash", "tool_input": {"command": f"bash < {script_path}", "cwd": d}}
            )
            self.assertIsNotNone(result, "on-disk script fed via stdin must still be inspected")
            assert result is not None
            self.assertEqual(result["decision"], "block")


class PositionalOperandPrecedenceTests(unittest.TestCase):
    """main#1325 review round 2 (Lucas Ferreira) / main#1325 merge gate (Nino
    Kavtaradze) — the corpus above varied redirect-presence and
    operand-presence ONE AT A TIME and never crossed them, which is exactly
    where the original fix's defect lived: `parse_interpreter_invocation`
    unconditionally promoted the LAST stdin-redirect target into
    `operands[0]`, even when a positional operand was ALSO present. Real bash
    and zsh never let a stdin redirect outrank a positional operand — a
    redirect is not counted as an argument slot at all, so it can never win
    against an ordinary word regardless of which side of the redirect token
    that word sits on. Verified with a real-shell marker proxy, both shells,
    every ordering below (see `parse_interpreter_invocation`'s docstring
    "Precedence" section for the full account).

    Crossed axes: {no operand, positional operand} x {no redirect, one
    redirect, two redirects} x {redirect spelling: `<`, `0<`, `<>`, `0<>`} x
    {redirect position: before/after/interleaved with the operand} x {-c
    present, absent} x {shell interpreter, non-shell interpreter}. Every row
    here is unit-level (`parse_interpreter_invocation` directly, verified
    against real-shell measurements above); the operationally-significant
    shapes are additionally pinned through the real `hook.check()` entry
    point in `WriteThenExecPositionalPrecedenceHookTests` below, each with a
    positive/negative pair sharing one instrument per #1318.
    """

    # --- Axis: no operand present --------------------------------------

    def test_no_operand_no_redirect(self):
        inv = parse_interpreter_invocation(["bash"])
        self.assertEqual(inv.operands, ())

    def test_no_operand_one_redirect_bare(self):
        inv = parse_interpreter_invocation(["bash", "<", "F"])
        self.assertEqual(inv.operands, ("F",))

    def test_no_operand_one_redirect_fd0(self):
        """main#1326: `0<` is the identical redirect as bare `<` (fd 0 is
        stdin's default) — real-shell-verified under bash and zsh."""
        inv = parse_interpreter_invocation(["bash", "0<", "F"])
        self.assertEqual(inv.operands, ("F",))

    def test_no_operand_one_redirect_readwrite(self):
        """main#1326: `<>` (read-write open on fd 0) — real-shell-verified."""
        inv = parse_interpreter_invocation(["bash", "<>", "F"])
        self.assertEqual(inv.operands, ("F",))

    def test_no_operand_one_redirect_fd0_readwrite(self):
        """main#1326: `0<>` — real-shell-verified."""
        inv = parse_interpreter_invocation(["bash", "0<>", "F"])
        self.assertEqual(inv.operands, ("F",))

    def test_non_stdin_fd_redirect_is_not_mistaken_for_a_stdin_source(self):
        """`2<` targets fd 2, not fd 0 — real-shell-verified NOT to feed the
        interpreter's script (the marker never fires). Must not match
        `_STDIN_REDIRECT_RE`; the widened #1326 pattern is deliberately
        `0?<>?`, not a bare `\\d*<` which would wrongly swallow this."""
        inv = parse_interpreter_invocation(["bash", "2<", "F"])
        self.assertEqual(inv.operands, ("2<", "F"))

    def test_no_operand_two_redirects_last_wins(self):
        inv = parse_interpreter_invocation(["bash", "<", "A", "<", "B"])
        self.assertEqual(inv.operands, ("B",))

    def test_no_operand_two_redirects_mixed_spellings_last_wins(self):
        """Last-wins must hold across spellings, not just within one."""
        inv = parse_interpreter_invocation(["bash", "<", "A", "0<", "B"])
        self.assertEqual(inv.operands, ("B",))

    # --- Axis: positional operand present -------------------------------

    def test_positional_no_redirect(self):
        inv = parse_interpreter_invocation(["bash", "S"])
        self.assertEqual(inv.operands, ("S",))

    def test_positional_before_one_redirect_bare(self):
        """The regression Lucas measured: `bash S < F` must run S, not F —
        confirmed with a real-shell marker proxy under bash and zsh."""
        inv = parse_interpreter_invocation(["bash", "S", "<", "F"])
        self.assertEqual(inv.operands, ("S",))

    def test_positional_before_one_redirect_fd0(self):
        inv = parse_interpreter_invocation(["bash", "S", "0<", "F"])
        self.assertEqual(inv.operands, ("S",))

    def test_positional_before_one_redirect_readwrite(self):
        inv = parse_interpreter_invocation(["bash", "S", "<>", "F"])
        self.assertEqual(inv.operands, ("S",))

    def test_positional_before_one_redirect_fd0_readwrite(self):
        inv = parse_interpreter_invocation(["bash", "S", "0<>", "F"])
        self.assertEqual(inv.operands, ("S",))

    def test_positional_after_one_redirect(self):
        """`bash < F S` — real bash/zsh: the redirect is consumed by the
        invoking shell before bash ever sees its own argv, so `S` (not `F`)
        is bash's sole operand and IS what executes — confirmed with a
        marker proxy (F's marker never fires; S, which doesn't exist as a
        file, makes the invocation error, exactly matching this resolution)."""
        inv = parse_interpreter_invocation(["bash", "<", "F", "S"])
        self.assertEqual(inv.operands, ("S",))

    def test_positional_between_two_redirects(self):
        inv = parse_interpreter_invocation(["bash", "<", "A", "S", "<", "B"])
        self.assertEqual(inv.operands, ("S",))

    def test_two_positionals_and_a_redirect_preserve_order(self):
        """Real shell: every non-redirect word survives, in order, as argv;
        argv[0] is what executes, argv[1:] are its arguments."""
        inv = parse_interpreter_invocation(["bash", "S1", "S2", "<", "F"])
        self.assertEqual(inv.operands, ("S1", "S2"))

    def test_interleaved_two_positionals(self):
        """`bash S1 < F S2` — confirmed against a real shell (marker proxy,
        both bash and zsh): S1 fires, F never does."""
        inv = parse_interpreter_invocation(["bash", "S1", "<", "F", "S2"])
        self.assertEqual(inv.operands, ("S1", "S2"))

    # --- Axis: -c present ------------------------------------------------

    def test_command_string_with_redirect_still_resolves_the_string_first(self):
        """`bash -c 'cmd' < F` — the command STRING is the sole non-redirect
        operand. `has_command_string` routes real callers to `.words`, not
        `.operands`, but `.operands` itself must still resolve correctly —
        no redirect leaking into slot 0."""
        inv = parse_interpreter_invocation(["bash", "-c", "cmd", "<", "F"])
        self.assertTrue(inv.has_command_string)
        self.assertEqual(inv.operands, ("cmd",))

    def test_command_string_flag_with_only_a_redirect_present(self):
        """`bash -c < F` — degenerate (a real shell would error on a missing
        command-string argument), but must not crash; the redirect target is
        the sole operand candidate once `-c` itself is consumed as a flag."""
        inv = parse_interpreter_invocation(["bash", "-c", "<", "F"])
        self.assertTrue(inv.has_command_string)
        self.assertEqual(inv.operands, ("F",))

    # --- Axis: non-shell interpreter (degenerate — always None) ---------

    def test_non_shell_interpreter_with_positional_and_redirect_returns_none(self):
        self.assertIsNone(parse_interpreter_invocation(["mysql", "S", "<", "F"]))

    def test_non_shell_interpreter_with_redirect_only_returns_none(self):
        self.assertIsNone(parse_interpreter_invocation(["mysql", "<", "F"]))


class WriteThenExecPositionalPrecedenceHookTests(unittest.TestCase):
    """Hook-level (`hook.check()`) confirmation of the crossed-axis cells
    that actually matter operationally — the two measured regressions from
    the main#1325 review (Lucas Ferreira: a BLOCK->ALLOW bypass and an
    ALLOW->BLOCK false positive, both from the same "positional operand +
    stdin redirect coexist" combination), the shape-7 on-disk-script-content
    walker regression, and the #1152-recurrence over-block (both found
    independently by Nino Kavtaradze at the merge gate). Every ALLOW row here
    has a BLOCK counterpart sharing the exact same command shape and the same
    `hook.check()`/`classify_heredocs()` instrument, per #1318.
    """

    def _assert_blocked(self, cmd: str) -> None:
        result = hook.check(_bash(cmd))
        self.assertIsNotNone(result, f"must block: {cmd!r}")
        assert result is not None
        self.assertEqual(result["decision"], "block")

    def _assert_allowed(self, cmd: str) -> None:
        result = hook.check(_bash(cmd))
        self.assertIsNone(
            result,
            f"must allow: {cmd!r} (got: {result['reason'].splitlines()[0] if result else ''})",
        )

    # --- Lucas's row 1: positional script wins, redirect target does not ---

    def test_positional_script_with_hidden_commit_still_blocks_despite_trailing_redirect(self):
        """The bypass: a heredoc writes a hidden commit into the POSITIONAL
        script; an unrelated trailing `< FILE` redirect must not distract the
        correlation away from the file that genuinely executes."""
        self._assert_blocked(
            f"cat > /tmp/wz1325a_s.sh <<'DELIM'\n{REAL_COMMIT}\nDELIM\n"
            "bash /tmp/wz1325a_s.sh < /tmp/wz1325a_unrelated.txt"
        )

    def test_redirect_target_with_hidden_commit_does_not_block_when_a_positional_script_is_present(
        self,
    ):
        """Sharing the same command shape as the row above — only the
        heredoc's target moves to the redirect file, which does NOT execute
        once a positional script is present, so this must ALLOW."""
        self._assert_allowed(
            f"cat > /tmp/wz1325a2_unrelated.txt <<'DELIM'\n{REAL_COMMIT}\nDELIM\n"
            "bash /tmp/wz1325a2_s.sh < /tmp/wz1325a2_unrelated.txt"
        )

    # --- Lucas's row 2: the false positive on the ordinary shape -----------

    def test_ordinary_data_heredoc_fed_to_an_unrelated_script_stays_allowed(self):
        """`bash migrate.sh < input.csv` — an everyday ops pattern. A heredoc
        writing benign data into input.csv (never executed as code — only
        migrate.sh's own stdin) must not falsely correlate."""
        self._assert_allowed(
            "cat > /tmp/wz1325b_data.txt <<'DELIM'\nordinary data, not code\nDELIM\n"
            "bash /tmp/wz1325b_migrate.sh < /tmp/wz1325b_data.txt"
        )

    def test_hidden_commit_in_the_positional_script_still_blocks_in_the_same_shape(self):
        """Sharing the exact same command shape as the row above — only the
        heredoc's target moves to the positional script itself."""
        self._assert_blocked(
            f"cat > /tmp/wz1325b_migrate.sh <<'DELIM'\n{REAL_COMMIT}\nDELIM\n"
            "bash /tmp/wz1325b_migrate.sh < /tmp/wz1325b_data.txt"
        )

    # --- Nino's shape-7 (on-disk script content walker) regression ---------

    def test_shape7_walker_still_detects_hidden_commit_with_dash_x_flag(self):
        """`bash -x s.sh < /dev/null` — before the guard, `operands[0]`
        resolved to `/dev/null` (wrong), so `_read_script_if_safe` inspected
        the wrong (empty) file and a hidden commit already sitting on disk in
        `s.sh` went undetected. `-x` breaks `_SCRIPT_INVOKE_RE`'s regex
        fallback (its `[^\\s\\-<>|;&(]` class rejects a leading `-`), so this
        shape depends entirely on the tokenized walker resolving
        `operands[0]` correctly."""
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            script_path = f"{d}/hidden.sh"
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(REAL_COMMIT + "\n")
            result = hook.check(
                {
                    "tool_name": "Bash",
                    "tool_input": {"command": f"bash -x {script_path} < /dev/null", "cwd": d},
                }
            )
            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result["decision"], "block")

    def test_shape7_walker_still_detects_hidden_commit_with_dashdash(self):
        """Same regression, the `--` spelling."""
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            script_path = f"{d}/hidden2.sh"
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(REAL_COMMIT + "\n")
            result = hook.check(
                {
                    "tool_name": "Bash",
                    "tool_input": {"command": f"bash -- {script_path} < /dev/null", "cwd": d},
                }
            )
            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result["decision"], "block")

    def test_shape7_unflagged_form_stays_blocked_as_before(self):
        """The unflagged form was never actually broken — it's caught by the
        `_SCRIPT_INVOKE_RE` regex fallback regardless of the walker's answer.
        Pinned here so a future change to that fallback can't silently
        regress it without a test noticing."""
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            script_path = f"{d}/hidden3.sh"
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(REAL_COMMIT + "\n")
            result = hook.check(
                {
                    "tool_name": "Bash",
                    "tool_input": {"command": f"bash {script_path} < /dev/null", "cwd": d},
                }
            )
            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result["decision"], "block")

    # --- Nino's over-block regression (#1152 through a new door) -----------

    def test_benign_stdin_data_fed_to_a_real_script_is_not_swept_into_code(self):
        """`bash deploy.sh < notes.txt` where notes.txt is ordinary benign
        data (never executed — only fed to deploy.sh's own stdin). Before the
        guard, `operands[0]` resolved to `notes.txt` (wrong), which falsely
        correlated the heredoc write with the interpreter invocation and
        flipped the DATA heredoc to CODE — main#1152's own failure mode
        recurring through this new slot."""
        (span,) = classify_heredocs(
            "cat > /tmp/wz1325c_notes.txt <<'DELIM'\n"
            "just some ordinary notes, not code\nDELIM\n"
            "bash /tmp/wz1325c_deploy.sh < /tmp/wz1325c_notes.txt"
        )
        self.assertFalse(span.is_code, "benign stdin data must stay classified as DATA")

    def test_real_commit_hidden_in_the_script_still_flips_to_code_in_the_same_shape(self):
        """Sharing the same command shape as the row above — only the
        heredoc's target moves to the executed script itself."""
        (span,) = classify_heredocs(
            f"cat > /tmp/wz1325c_deploy.sh <<'DELIM'\n{REAL_COMMIT}\nDELIM\n"
            "bash /tmp/wz1325c_deploy.sh < /tmp/wz1325c_notes.txt"
        )
        self.assertTrue(span.is_code, "a real hidden commit in the executed script must stay CODE")

    # --- Redirect + trailing words, no leading positional -------------------
    # Lucas's own sweep asserted `bash < FILE arg1 arg2` "correctly starts
    # blocking" against the UNGUARDED code — true of the VERDICT, but for the
    # wrong reason: the unguarded code correlated on FILE, which a real shell
    # never executes once trailing operands are present. Confirmed with a
    # real-shell marker proxy: `bash < FILE arg1 arg2` attempts to execute
    # `arg1` (erroring, since arg1 doesn't exist as a file) and FILE's marker
    # never fires. The corrected rule now correlates on `arg1` (the true
    # first operand) — what a real shell actually runs.

    def test_redirect_with_trailing_words_does_not_correlate_on_the_redirect_target(self):
        """A heredoc writing the hidden commit into the redirect TARGET
        (never actually executed, once trailing words are present) must not
        block."""
        self._assert_allowed(
            f"cat > /tmp/wz1325d_file.txt <<'DELIM'\n{REAL_COMMIT}\nDELIM\n"
            "bash < /tmp/wz1325d_file.txt /tmp/wz1325d_arg1 /tmp/wz1325d_arg2"
        )

    def test_redirect_with_trailing_words_blocks_when_commit_is_in_first_trailing_word(self):
        """Sharing the same command shape — only the heredoc's target moves
        to the first trailing word, which IS what a real shell attempts to
        execute in this shape."""
        self._assert_blocked(
            f"cat > /tmp/wz1325d_arg1 <<'DELIM'\n{REAL_COMMIT}\nDELIM\n"
            "bash < /tmp/wz1325d_file.txt /tmp/wz1325d_arg1 /tmp/wz1325d_arg2"
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
