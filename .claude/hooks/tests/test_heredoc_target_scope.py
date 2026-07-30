#!/usr/bin/env python3
"""Regression tests for main#1152 — heredoc TARGET scoping in the commit-identity gate.

`validate_commit_identity._detect_indirect_commit` ran its indirect-exec
matchers over the raw command string. None of those matchers asks what a
heredoc is fed to, so a heredoc body was scanned for bypass shapes regardless
of whether a shell would ever execute it: documenting the shape

    cat > notes.md <<'EOF'
    the bypass looks like: bash -c 'git commit -m x'
    EOF

was blocked as if it *were* that invocation, while the identical bytes written
through the `Write` tool were allowed.

The fix classifies each heredoc by its target — interpreter-fed bodies are code
and stay scannable, `cat`/`tee`-fed bodies are data and are stripped before the
matchers run — and these tests pin BOTH directions:

  * `FiveRowReproductionTests` is the table from the issue, verbatim, including
    the `Write`-vs-heredoc consistency pair.
  * `GenuineBypassStillBlocksTests` re-asserts every shape the gate is supposed
    to catch, because the only way to "fix" a false positive wrongly is to stop
    blocking something real.
  * `HeredocClassifierTests` / `StripDataHeredocsTests` pin the `_shell_parse`
    primitive, including its fail-toward-CODE behaviour on every ambiguity.

Run: python3 -m pytest .claude/hooks/tests/test_heredoc_target_scope.py -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
sys.path.insert(0, str(_HOOKS_DIR))

import validate_commit_identity as hook  # noqa: E402
from _shell_parse import (  # noqa: E402
    HEREDOC_DATA_SINKS,
    SHELL_INTERPRETERS,
    _scan_command_line,
    classify_heredocs,
    strip_data_heredocs,
)

# The payload used throughout: a line of PROSE that names an interpreter `-c`
# invocation carrying a commit. Inert as data, executable as code — which is
# exactly the distinction under test.
DOC_LINE = "the bypass shape looks like: bash -c 'git commit -m x'"

# A real commit invocation, for the heredoc bodies that a shell will execute.
REAL_COMMIT = 'git -c user.name="X" -c user.email="Y" commit -m z'


def _bash(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


def _write(content: str) -> dict:
    return {
        "tool_name": "Write",
        "tool_input": {"file_path": "/tmp/notes.md", "content": content},
    }


class FiveRowReproductionTests(unittest.TestCase):
    """The reproduction table from main#1152, row for row.

    Rows 1, 2, 4 and 5 already held before the fix; row 3 is the defect. They
    are all kept because the value of the table is the CONTRAST — row 3 differs
    from row 2 only in whether the documented invocation mentions a commit, and
    from row 4 only in what the heredoc is fed to. A future change that fixes
    row 3 by loosening rows 1/2/4 would pass a row-3-only test.
    """

    def test_row1_heredoc_body_with_bare_commit_phrase_allowed(self):
        """Row 1: prose naming `git commit`, fed to `cat` → data. Allowed."""
        cmd = "cat > /tmp/notes.md <<'EOF'\nrun git commit with identity flags\nEOF"
        self.assertIsNone(hook.check(_bash(cmd)))

    def test_row2_heredoc_body_with_interpreter_dash_c_no_commit_allowed(self):
        """Row 2: prose naming `bash -c` with no commit in it → data. Allowed."""
        cmd = "cat > /tmp/notes.md <<'EOF'\nshape: bash -c 'ls -la'\nEOF"
        self.assertIsNone(hook.check(_bash(cmd)))

    def test_row3_heredoc_body_documenting_dash_c_commit_via_cat_allowed(self):
        """Row 3 — THE DEFECT. Prose naming `bash -c '…git commit…'`, fed to
        `cat` and redirected to a file. `cat` does not execute its stdin, so the
        body is inert text; before the fix `_DASH_C_RE` matched it in the raw
        string and the command was blocked."""
        cmd = f"cat > /tmp/notes.md <<'EOF'\n{DOC_LINE}\nEOF"
        result = hook.check(_bash(cmd))
        self.assertIsNone(
            result,
            "a heredoc fed to `cat` is data, not code — must not block "
            f"(got: {result['reason'].splitlines()[0] if result else ''})",
        )

    def test_row4_heredoc_fed_directly_to_interpreter_blocks(self):
        """Row 4: the same class of body, but fed to `bash`. A genuine bypass —
        the shell executes it — and it must stay blocked."""
        cmd = f"bash <<'EOF'\n{REAL_COMMIT}\nEOF"
        result = hook.check(_bash(cmd))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["decision"], "block")
        self.assertIn("heredoc", result["reason"])

    def test_row5_write_tool_and_cat_heredoc_agree(self):
        """Row 5 — the consistency pair. The SAME bytes, delivered through the
        `Write` tool and through a `cat` heredoc, must reach the same verdict.
        Before the fix `Write` was allowed and the heredoc was blocked, which is
        what made the false positive visible: the workaround was to stop using
        the shell."""
        content = DOC_LINE + "\n"
        via_write = hook.check(_write(content))
        via_heredoc = hook.check(_bash(f"cat > /tmp/notes.md <<'EOF'\n{DOC_LINE}\nEOF"))
        self.assertIsNone(via_write, "Write of inert content must be allowed")
        self.assertIsNone(via_heredoc, "the identical bytes via heredoc must also be allowed")
        self.assertEqual(
            via_write is None,
            via_heredoc is None,
            "Write and `cat` heredoc must agree on identical content",
        )


class DataHeredocVariantsTests(unittest.TestCase):
    """Row 3 generalised across delimiter forms, sinks and payload shapes.

    Row 3 used `<<'EOF'`; the other opener forms and the other four bypass
    matchers reach the same body through different code, so each is pinned.
    """

    def _assert_allowed(self, cmd: str) -> None:
        result = hook.check(_bash(cmd))
        self.assertIsNone(
            result,
            f"data heredoc must not block: {cmd!r} "
            f"(got: {result['reason'].splitlines()[0] if result else ''})",
        )

    def test_unquoted_delimiter(self):
        self._assert_allowed(f"cat > /tmp/n.md <<EOF\n{DOC_LINE}\nEOF")

    def test_double_quoted_delimiter(self):
        self._assert_allowed(f'cat > /tmp/n.md <<"EOF"\n{DOC_LINE}\nEOF')

    def test_dash_form_delimiter(self):
        self._assert_allowed(f"cat > /tmp/n.md <<-EOF\n\t{DOC_LINE}\nEOF")

    def test_append_redirect(self):
        self._assert_allowed(f"cat >> /tmp/n.md <<'EOF'\n{DOC_LINE}\nEOF")

    def test_no_redirect_at_all(self):
        self._assert_allowed(f"cat <<'EOF'\n{DOC_LINE}\nEOF")

    def test_tee_sink(self):
        self._assert_allowed(f"tee /tmp/n.md <<'EOF'\n{DOC_LINE}\nEOF")

    def test_tee_append_sink(self):
        self._assert_allowed(f"tee -a /tmp/n.md <<'EOF'\n{DOC_LINE}\nEOF")

    def test_body_documents_pipe_to_shell(self):
        self._assert_allowed("cat > /tmp/n.md <<'EOF'\nprintf 'git commit -m x' | bash\nEOF")

    def test_body_documents_process_substitution(self):
        self._assert_allowed("cat > /tmp/n.md <<'EOF'\nbash <(printf 'git commit -m x')\nEOF")

    def test_body_documents_eval(self):
        self._assert_allowed("cat > /tmp/n.md <<'EOF'\neval 'git commit -m x'\nEOF")

    def test_body_documents_here_string(self):
        self._assert_allowed("cat > /tmp/n.md <<'EOF'\nbash <<<'git commit -m x'\nEOF")

    def test_body_documents_script_invocation(self):
        """The `bash <script>` matcher reads from DISK and is not gated on the
        word `commit`, so it too must scan the stripped text — otherwise merely
        writing `bash deploy.sh` into a file could trigger a disk read and a
        block on that script's contents."""
        self._assert_allowed("cat > /tmp/n.md <<'EOF'\nbash deploy.sh\nEOF")

    def test_body_documents_a_nested_interpreter_heredoc(self):
        """A `bash <<'INNER'` shown INSIDE a `cat` heredoc is still just text —
        the outer `cat` consumes the whole thing."""
        self._assert_allowed(
            "cat > /tmp/n.md <<'OUTER'\nbash <<'INNER'\ngit commit -m x\nINNER\nOUTER"
        )

    def test_data_heredoc_after_a_leading_command(self):
        self._assert_allowed(f"mkdir -p /tmp/d && cat > /tmp/d/n.md <<'EOF'\n{DOC_LINE}\nEOF")

    def test_data_heredoc_after_a_cd(self):
        self._assert_allowed(f"cd /tmp && cat > n.md <<'EOF'\n{DOC_LINE}\nEOF")

    def test_two_data_heredocs_in_one_command(self):
        self._assert_allowed(
            "cat > /tmp/a <<'E1'\nbash -c 'git commit'\nE1\n"
            "cat > /tmp/b <<'E2'\neval 'git commit'\nE2"
        )

    def test_data_heredoc_followed_by_innocent_command(self):
        """Body-consumption must resume correctly after the terminator: the
        trailing `ls -la` is a real command line, not more body."""
        self._assert_allowed(f"cat > /tmp/n.md <<'EOF'\n{DOC_LINE}\nEOF\nls -la")


class GenuineBypassStillBlocksTests(unittest.TestCase):
    """Every shape the gate exists to catch, re-asserted after the change.

    A false-positive fix is only correct if it is provably one-directional.
    These are the negative-space tests: if a future narrowing of the classifier
    starts treating an interpreter-fed body as data, one of these fails.
    """

    def _assert_blocked(self, cmd: str, shape: str) -> None:
        result = hook.check(_bash(cmd))
        self.assertIsNotNone(result, f"genuine bypass must block: {cmd!r}")
        assert result is not None
        self.assertEqual(result["decision"], "block")
        self.assertIn("indirect-exec", result["reason"])
        self.assertIn(shape, result["reason"])

    def test_interpreter_heredoc_quoted_delimiter(self):
        self._assert_blocked(f"bash <<'EOF'\n{REAL_COMMIT}\nEOF", "heredoc")

    def test_interpreter_heredoc_unquoted_delimiter(self):
        self._assert_blocked(f"bash <<EOF\n{REAL_COMMIT}\nEOF", "heredoc")

    def test_interpreter_heredoc_dash_form(self):
        self._assert_blocked(f"bash <<-EOF\n\t{REAL_COMMIT}\nEOF", "heredoc")

    def test_every_interpreter_name_blocks(self):
        """The classifier's `SHELL_INTERPRETERS` and the matcher's
        `_INTERPRETERS` regex are now built from one set; this walks the whole
        set so adding a name to it can never silently reach only one side."""
        for interp in sorted(SHELL_INTERPRETERS):
            with self.subTest(interpreter=interp):
                self._assert_blocked(f"{interp} <<'EOF'\n{REAL_COMMIT}\nEOF", "heredoc")

    def test_interpreter_regex_matches_exactly_the_shared_set(self):
        """Pin the derived alternation against the shared set — a drift here is
        the failure mode the derivation exists to prevent."""
        import re

        pattern = re.compile(r"^\(\?:(.+)\)$")
        m = pattern.match(hook._INTERPRETERS)
        self.assertIsNotNone(m, f"unexpected _INTERPRETERS shape: {hook._INTERPRETERS!r}")
        assert m is not None
        self.assertEqual(set(m.group(1).split("|")), set(SHELL_INTERPRETERS))

    def test_interpreter_heredoc_body_containing_dash_c(self):
        """Label is `shell -c`, not `heredoc`: the matchers run in a fixed
        order and `_DASH_C_RE` reaches the surviving body first. Which matcher
        claims it is not the contract — that it BLOCKS is. Asserted against the
        measured label rather than the expected one."""
        self._assert_blocked(f"bash <<'EOF'\nbash -c '{REAL_COMMIT}'\nEOF", "shell -c")

    def test_interpreter_heredoc_with_output_redirect(self):
        """`bash <<'EOF' > /tmp/out.log` — a redirect on the interpreter line
        must not be mistaken for a `cat > file` data sink."""
        self._assert_blocked(f"bash <<'EOF' > /tmp/out.log\n{REAL_COMMIT}\nEOF", "heredoc")

    def test_absolute_path_interpreter(self):
        self._assert_blocked(f"/bin/bash <<'EOF'\n{REAL_COMMIT}\nEOF", "heredoc")

    def test_env_prefixed_interpreter(self):
        self._assert_blocked(f"env bash <<'EOF'\n{REAL_COMMIT}\nEOF", "heredoc")

    def test_timeout_prefixed_interpreter(self):
        self._assert_blocked(f"timeout 30 bash <<'EOF'\n{REAL_COMMIT}\nEOF", "heredoc")

    def test_sudo_prefixed_interpreter(self):
        self._assert_blocked(f"sudo bash <<'EOF'\n{REAL_COMMIT}\nEOF", "heredoc")

    def test_env_assignment_prefixed_interpreter(self):
        self._assert_blocked(f"FOO=1 bash <<'EOF'\n{REAL_COMMIT}\nEOF", "heredoc")

    def test_data_heredoc_does_not_shadow_a_later_real_bypass(self):
        """The stripped body must not swallow the command lines that follow it.
        A `cat` heredoc first, a real `bash` heredoc second."""
        self._assert_blocked(
            f"cat > /tmp/a <<'E1'\njust prose\nE1\nbash <<'E2'\n{REAL_COMMIT}\nE2",
            "heredoc",
        )

    def test_data_heredoc_does_not_shadow_a_later_dash_c(self):
        self._assert_blocked(
            f"cat > /tmp/a <<'E1'\njust prose\nE1\nbash -c '{REAL_COMMIT}'",
            "shell -c",
        )

    def test_real_bypass_before_a_data_heredoc(self):
        self._assert_blocked(
            f"bash -c '{REAL_COMMIT}'\ncat > /tmp/a <<'E1'\njust prose\nE1",
            "shell -c",
        )

    def test_pipe_to_shell(self):
        self._assert_blocked(
            f"printf '%s\\n' \"{REAL_COMMIT}\" | bash", "printf/echo piped to shell"
        )

    def test_dash_c(self):
        self._assert_blocked(f"bash -c '{REAL_COMMIT}'", "shell -c")

    def test_process_substitution(self):
        self._assert_blocked(f"bash <(printf '{REAL_COMMIT}')", "process substitution")

    def test_here_string(self):
        self._assert_blocked(f"bash <<<'{REAL_COMMIT}'", "here-string")

    def test_eval(self):
        self._assert_blocked(f"eval '{REAL_COMMIT}'", "eval")

    def test_unterminated_data_heredoc_still_scanned(self):
        """No terminator → the classifier cannot tell where the body ends, so it
        keeps everything. Fail-closed: this stays blocked."""
        self._assert_blocked(f"cat > /tmp/n.md <<'EOF'\nbash -c '{REAL_COMMIT}'", "shell -c")

    def test_unrecognised_sink_still_scanned(self):
        """`myrunner` is not in the data-sink allowlist, so its body keeps
        today's scan-the-body behaviour. The allowlist is the only thing that
        can unblock anything."""
        self._assert_blocked(f"myrunner <<'EOF'\nbash -c '{REAL_COMMIT}'\nEOF", "shell -c")

    def test_non_shell_interpreter_sink_still_scanned(self):
        """`python3` is neither a shell interpreter nor a data sink. It keeps
        the pre-existing (conservative) behaviour rather than being quietly
        unblocked by this change."""
        self._assert_blocked(
            f"python3 <<'EOF'\nsubprocess.run(\"bash -c '{REAL_COMMIT}'\", shell=True)\nEOF",
            "shell -c",
        )


class CatPipedToShellTests(unittest.TestCase):
    """`cat <<'EOF' | bash` — a hole this change CLOSES.

    `_HEREDOC_RE` requires the interpreter to appear textually BEFORE the `<<`,
    so it never matched this shape, and no other matcher covers it either: a
    heredoc body piped into a shell was measurably ALLOWED before this change,
    despite being executed verbatim. The classifier already has to answer "is
    this body fed to an interpreter?" — including through a pipe — to decide
    what to strip, so the answer is used to block as well as to allow.
    """

    def _assert_blocked(self, cmd: str) -> None:
        result = hook.check(_bash(cmd))
        self.assertIsNotNone(result, f"heredoc piped into a shell must block: {cmd!r}")
        assert result is not None
        self.assertEqual(result["decision"], "block")
        self.assertIn("heredoc", result["reason"])

    def test_cat_heredoc_piped_to_bash(self):
        self._assert_blocked(f"cat <<'EOF' | bash\n{REAL_COMMIT}\nEOF")

    def test_cat_heredoc_piped_to_sh_with_spacing(self):
        self._assert_blocked(f"cat <<'EOF'   |   sh\n{REAL_COMMIT}\nEOF")

    def test_cat_heredoc_piped_through_tee_into_bash(self):
        self._assert_blocked(f"cat <<'EOF' | tee /tmp/a.sh | bash\n{REAL_COMMIT}\nEOF")

    def test_cat_heredoc_piped_only_to_tee_is_still_data(self):
        """The pipeline walk must stop at non-interpreters, not treat any pipe
        as executable."""
        self.assertIsNone(hook.check(_bash(f"cat <<'EOF' | tee /tmp/a.md\n{DOC_LINE}\nEOF")))

    def test_semicolon_does_not_make_a_following_shell_the_target(self):
        """`;` is not a pipe — the following `bash` does not receive this stdin,
        so the body stays data."""
        self.assertIsNone(hook.check(_bash(f"cat > /tmp/n.md <<'EOF'\n{DOC_LINE}\nEOF\nls")))


class ProcessSubstitutionSinkTests(unittest.TestCase):
    """A process substitution is a SECOND sink on the heredoc's own segment.

    Regression for the merge-gate finding on PR #1155 (Aino Virtanen). The
    first version of this classifier resolved the segment head to `tee`, found
    it in `HEREDOC_DATA_SINKS`, and then followed only `|` downstream. A
    process substitution hangs off the SAME segment, so the walk never saw it:

        tee >(bash) <<'DELIM'
        git -c user.name=X -c user.email=Y commit -m z
        DELIM

    BLOCK at `fea0dca` -> ALLOW at `e163320`. A genuine block -> allow
    regression on an identity-carrying commit, verified to really execute under
    both bash and zsh:

        $ bash procsub.sh  ->  PROCSUB-BODY-EXECUTED
        $ zsh  procsub.sh  ->  PROCSUB-BODY-EXECUTED

    The stated guarantee ("unknown owner -> CODE") held for the HEAD WORD only.
    A known-inert head carrying an unrecognised second sink fell through it.
    The classifier now forces CODE on any reachable segment carrying `>(`/`<(`,
    without trying to resolve what is inside — an unresolvable sink resolves
    toward CODE, the rule the rest of the classifier already follows.
    """

    def _assert_blocked(self, cmd: str) -> None:
        result = hook.check(_bash(cmd))
        self.assertIsNotNone(result, f"process-substitution sink must block: {cmd!r}")
        assert result is not None
        self.assertEqual(result["decision"], "block")

    def test_tee_procsub_bash(self):
        self._assert_blocked(f"tee >(bash) <<'EOF'\n{REAL_COMMIT}\nEOF")

    def test_tee_procsub_sh(self):
        self._assert_blocked(f"tee >(sh) <<'EOF'\n{REAL_COMMIT}\nEOF")

    def test_tee_procsub_with_additional_redirect(self):
        self._assert_blocked(f"tee >(bash) > /dev/null <<'EOF'\n{REAL_COMMIT}\nEOF")

    def test_cat_redirected_into_procsub(self):
        self._assert_blocked(f"cat > >(bash) <<'EOF'\n{REAL_COMMIT}\nEOF")

    def test_input_form_procsub_also_forces_code(self):
        """`<(...)` too. We do not try to decide whether the substitution's
        contents are inert — an unresolvable sink is CODE."""
        self._assert_blocked(f"tee <(cat /etc/hosts) <<'EOF'\n{REAL_COMMIT}\nEOF")

    def test_procsub_downstream_of_a_pipe(self):
        """The pipe-follow must apply the same rule to downstream segments —
        `| tee >(bash)` reaches the body just as `tee >(bash)` does."""
        self._assert_blocked(f"cat <<'EOF' | tee >(bash)\n{REAL_COMMIT}\nEOF")

    def test_procsub_containing_a_pipeline(self):
        """A `|` INSIDE the substitution splits the scanner's segments, but the
        `>(` position still falls in the owning segment, so the rule fires."""
        self._assert_blocked(f"tee >(grep x | bash) <<'EOF'\n{REAL_COMMIT}\nEOF")

    def test_quoted_procsub_is_not_a_procsub(self):
        """The detection is quote-aware: a literal `>(` inside a quoted filename
        is not a process substitution and must not re-introduce #1152's false
        positive by the back door."""
        cmd = f"cat > 'weird>(name).md' <<'EOF'\n{DOC_LINE}\nEOF"
        self.assertIsNone(hook.check(_bash(cmd)))

    def test_classifier_marks_procsub_segment_as_code(self):
        """Pinned at the primitive too, so a failure localises to the
        classifier rather than only to the hook's verdict."""
        (span,) = classify_heredocs("tee >(bash) <<'EOF'\nbody\nEOF")
        self.assertTrue(span.is_code)


class RedirectAmpersandTests(unittest.TestCase):
    """`2>&1` is a redirect, not a control operator.

    Second merge-gate finding on PR #1155. `_scan_command_line` split the
    segment on the `&` in `2>&1`, with two measured consequences:

      * `cat <<'DELIM' 2>&1 | bash` — the downstream walk broke on a non-`|`
        separator, so the new pipe-to-shell block was evaded by three
        characters. (ALLOW at base and at the first head; not a regression, but
        it made the new protection trivially bypassable.)
      * `cat 2>&1 > notes.md <<'DELIM'` — the head command resolved to `1`
        rather than `cat`, so #1152's own false positive survived for every
        redirect-carrying opener. The bug this PR closes was not fully closed.

    `&>file` is the same `&` from the other side. A genuine backgrounding `&`
    must still separate.
    """

    def test_stderr_redirect_does_not_evade_the_pipe_block(self):
        result = hook.check(_bash(f"cat <<'EOF' 2>&1 | bash\n{REAL_COMMIT}\nEOF"))
        self.assertIsNotNone(result, "`2>&1` must not break the pipe-follow")
        assert result is not None
        self.assertEqual(result["decision"], "block")

    def test_stdout_to_stderr_form(self):
        result = hook.check(_bash(f"cat <<'EOF' >&2 | bash\n{REAL_COMMIT}\nEOF"))
        self.assertIsNotNone(result)

    def test_ampersand_redirect_both_form(self):
        result = hook.check(_bash(f"cat <<'EOF' &> /tmp/l | bash\n{REAL_COMMIT}\nEOF"))
        self.assertIsNotNone(result)

    def test_false_positive_fixed_for_leading_redirect(self):
        """The #1152 fix must reach redirect-carrying openers too."""
        self.assertIsNone(hook.check(_bash(f"cat 2>&1 > /tmp/n.md <<'EOF'\n{DOC_LINE}\nEOF")))

    def test_false_positive_fixed_for_trailing_redirect(self):
        self.assertIsNone(hook.check(_bash(f"cat > /tmp/n.md 2>&1 <<'EOF'\n{DOC_LINE}\nEOF")))

    def test_false_positive_fixed_for_stderr_to_devnull(self):
        self.assertIsNone(hook.check(_bash(f"tee /tmp/n.md 2>/dev/null <<'EOF'\n{DOC_LINE}\nEOF")))

    def test_backgrounding_ampersand_still_separates(self):
        """Only a `&` adjacent to a redirect is exempt — a real control `&`
        must keep its meaning."""
        segments = _scan_command_line("sleep 1 & wait").segments
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[1][2], "&")

    def test_redirect_ampersand_does_not_split(self):
        segments = _scan_command_line("cat <<'EOF' 2>&1 | bash").segments
        self.assertEqual([s[2] for s in segments], ["", "|"])

    def test_and_operator_still_splits(self):
        segments = _scan_command_line("mkdir -p /a && cat <<'EOF'").segments
        self.assertEqual([s[2] for s in segments], ["", "&&"])


class PipeAmpersandOperatorTests(unittest.TestCase):
    """`|&` is ONE operator — bash/zsh shorthand for `2>&1 |`.

    Second-slot merge-gate finding on PR #1155 (Nino Kavtaradze, security lens).
    Falling through to the single-character cases split it into `|` then `&`,
    which is strictly worse than either reading of the operator:

        sep=''  seg="cat <<'D' "   head='cat'
        sep='|' seg=''             head=None    <- empty segment
        sep='&' seg=' bash'        head='bash'  <- never reached: walk broke on `&`

    So `cat <<'D' |& bash` walked around the pipe-to-shell block that this PR
    itself introduces — the gate is real and was evaded by one character. Not a
    regression (base allowed it too), but a gap in new protection, and the same
    class as the `2>&1` finding from round 1.

    Body execution confirmed in both shells with a marker assembled AT RUNTIME,
    so a shell that merely PRINTS the body cannot forge it:

        cat <<'D' |& bash
        printf 'WZ-%s-MARKER\\n' EXEC
        D

        $ bash -> WZ-EXEC-MARKER      $ zsh -> WZ-EXEC-MARKER
    """

    def _assert_blocked(self, cmd: str) -> None:
        result = hook.check(_bash(cmd))
        self.assertIsNotNone(result, f"`|&` feeds a shell — must block: {cmd!r}")
        assert result is not None
        self.assertEqual(result["decision"], "block")

    def test_cat_pipe_ampersand_bash(self):
        self._assert_blocked(f"cat <<'EOF' |& bash\n{REAL_COMMIT}\nEOF")

    def test_tee_pipe_ampersand_sh(self):
        self._assert_blocked(f"tee /dev/null <<'EOF' |& sh\n{REAL_COMMIT}\nEOF")

    def test_pipe_ampersand_unspaced(self):
        self._assert_blocked(f"cat <<'EOF' |&bash\n{REAL_COMMIT}\nEOF")

    def test_pipe_ampersand_then_further_pipe(self):
        """The walk must keep going past a `|&` relay, not just handle it in
        terminal position."""
        self._assert_blocked(f"cat <<'EOF' |& tee /tmp/a | bash\n{REAL_COMMIT}\nEOF")

    def test_pipe_ampersand_to_a_data_sink_stays_data(self):
        """`|&` connects the pipeline; it does not by itself mean `code`. A
        `|& tee` relay with no interpreter anywhere must stay ALLOW, or the fix
        would have re-introduced #1152's false positive for this shape."""
        self.assertIsNone(hook.check(_bash(f"cat <<'EOF' |& tee /tmp/a\n{DOC_LINE}\nEOF")))

    def test_scanner_emits_one_pipe_separator(self):
        """Pinned at the scanner, so a failure localises here rather than only
        in the hook verdict. Two segments, one `|` — not three with an empty."""
        segments = _scan_command_line("cat <<'D' |& bash").segments
        self.assertEqual([s[2] for s in segments], ["", "|"])
        self.assertEqual(len(segments), 2)

    def test_backgrounding_ampersand_is_untouched_by_the_pipe_amp_case(self):
        """A bare `&` still backgrounds and still breaks the pipeline."""
        segments = _scan_command_line("sleep 1 & bash").segments
        self.assertEqual([s[2] for s in segments], ["", "&"])

    def test_or_operator_is_untouched_by_the_pipe_amp_case(self):
        """`||` must not be mis-consumed as `|` + `|`, and is not `|&`."""
        segments = _scan_command_line("false || bash").segments
        self.assertEqual([s[2] for s in segments], ["", "||"])

    def test_or_still_breaks_the_pipeline(self):
        self.assertIsNone(hook.check(_bash(f"cat > /tmp/n <<'EOF'\n{DOC_LINE}\nEOF\nfalse || ls")))


class BashlexHeredocLimitationTests(unittest.TestCase):
    """Why the classifier is a scanner and not a bashlex AST walk.

    The structurally obvious tool is `iter_command_segments_ast` — the AST
    carries redirect nodes, and `validate_commit_identity` already depends on
    it. It cannot be used here: the installed bashlex FAILS TO PARSE a
    quoted-delimiter heredoc at all, and `<<'EOF'` is the dominant form (it is
    the form in the #1152 reproduction). This test pins that measurement so a
    future bashlex that fixes it fails loudly and invites the classifier to be
    revisited, rather than the limitation being re-derived from scratch.
    """

    def test_bashlex_cannot_parse_quoted_delimiter_heredoc(self):
        """Pinned to `ParsingError` specifically, not bare `Exception` — a
        broad `assertRaises` would also be satisfied by an unrelated failure
        (an import error, a TypeError from a signature change) and would keep
        passing while the measurement it encodes had quietly stopped being
        true."""
        try:
            import bashlex
            import bashlex.errors
        except ImportError:  # pragma: no cover - degraded mode
            self.skipTest("bashlex not installed")
        for cmd in ("cat <<'EOF'\nx\nEOF\n", 'cat <<"EOF"\nx\nEOF\n'):
            with self.subTest(command=cmd):
                with self.assertRaises(bashlex.errors.ParsingError):
                    bashlex.parse(cmd)

    def test_bashlex_does_parse_the_bare_delimiter_form(self):
        """The contrast that makes the point precise: it is the QUOTING of the
        delimiter that defeats the parser, not heredocs in general."""
        try:
            import bashlex
        except ImportError:  # pragma: no cover - degraded mode
            self.skipTest("bashlex not installed")
        self.assertTrue(bashlex.parse("cat <<EOF\nx\nEOF\n"))

    def test_classifier_handles_what_bashlex_cannot(self):
        spans = classify_heredocs("cat > /tmp/n.md <<'EOF'\nbody\nEOF")
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].delim, "EOF")
        self.assertEqual(spans[0].body, "body")
        self.assertFalse(spans[0].is_code)
        self.assertTrue(spans[0].terminated)


class HeredocClassifierTests(unittest.TestCase):
    """`classify_heredocs` — the primitive, tested directly."""

    def test_no_heredoc_returns_empty(self):
        self.assertEqual(classify_heredocs("ls -la"), ())

    def test_here_string_is_not_a_heredoc(self):
        self.assertEqual(classify_heredocs("bash <<<'git commit -m x'"), ())

    def test_interpreter_body_is_code(self):
        (span,) = classify_heredocs("bash <<'EOF'\ngit commit\nEOF")
        self.assertTrue(span.is_code)
        self.assertEqual(span.body, "git commit")

    def test_data_sink_body_is_not_code(self):
        (span,) = classify_heredocs("tee /tmp/a <<'EOF'\ngit commit\nEOF")
        self.assertFalse(span.is_code)

    def test_unterminated_marks_terminated_false_and_code_true(self):
        (span,) = classify_heredocs("cat <<'EOF'\ngit commit")
        self.assertFalse(span.terminated)
        self.assertTrue(span.is_code, "an unterminated heredoc must fail toward CODE")

    def test_two_heredocs_classified_independently(self):
        first, second = classify_heredocs(
            "cat > /tmp/a <<'E1'\nprose\nE1\nbash <<'E2'\ngit commit\nE2"
        )
        self.assertFalse(first.is_code)
        self.assertTrue(second.is_code)
        self.assertEqual(second.body, "git commit")

    def test_multiline_body_preserved(self):
        (span,) = classify_heredocs("cat <<'EOF'\nline one\nline two\nEOF")
        self.assertEqual(span.body, "line one\nline two")

    def test_dash_form_terminator_may_be_tab_indented(self):
        (span,) = classify_heredocs("cat <<-EOF\n\tbody\n\tEOF")
        self.assertTrue(span.terminated)
        self.assertEqual(span.body, "\tbody")

    def test_plain_form_terminator_may_not_be_tab_indented(self):
        """Without `-`, a tab-indented delimiter does NOT terminate the heredoc
        (real shell behaviour). The result is an unterminated heredoc, which
        fails toward CODE."""
        (span,) = classify_heredocs("cat <<EOF\nbody\n\tEOF")
        self.assertFalse(span.terminated)

    def test_opener_inside_quotes_is_not_an_opener(self):
        self.assertEqual(classify_heredocs('echo "<<EOF" > /tmp/a'), ())

    def test_non_word_delimiter_is_not_recognised(self):
        """`<<'END-OF-FILE'` has a non-`\\w` delimiter; the opener is not
        recognised at all, so nothing is stripped — the conservative outcome."""
        self.assertEqual(classify_heredocs("cat <<'END-OF-FILE'\nx\nEND-OF-FILE"), ())

    def test_cached_result_is_a_stable_immutable_tuple(self):
        cmd = "cat <<'EOF'\nbody\nEOF"
        first = classify_heredocs(cmd)
        second = classify_heredocs(cmd)
        self.assertEqual(first, second)
        self.assertIsInstance(first, tuple)


class StripDataHeredocsTests(unittest.TestCase):
    """`strip_data_heredocs` — the complement of `strip_heredocs`."""

    def test_no_heredoc_is_returned_unchanged(self):
        cmd = "git -c user.name=X commit -m z"
        self.assertEqual(strip_data_heredocs(cmd), cmd)

    def test_interpreter_body_survives_verbatim(self):
        cmd = "bash <<'EOF'\ngit commit -m x\nEOF"
        self.assertEqual(strip_data_heredocs(cmd), cmd)

    def test_data_body_is_removed_but_the_command_line_is_kept(self):
        cmd = "cat > /tmp/n.md <<'EOF'\ngit commit -m x\nEOF"
        out = strip_data_heredocs(cmd)
        self.assertNotIn("git commit", out)
        self.assertIn("cat > /tmp/n.md <<'EOF'", out)
        self.assertIn("EOF", out)

    def test_mixed_command_keeps_only_the_code_body(self):
        cmd = "cat > /tmp/a <<'E1'\ndata line\nE1\nbash <<'E2'\ncode line\nE2"
        out = strip_data_heredocs(cmd)
        self.assertNotIn("data line", out)
        self.assertIn("code line", out)

    def test_trailing_command_line_survives(self):
        out = strip_data_heredocs("cat <<'EOF'\ndata line\nEOF\nls -la")
        self.assertNotIn("data line", out)
        self.assertIn("ls -la", out)

    def test_unterminated_heredoc_is_left_untouched(self):
        cmd = "cat <<'EOF'\ngit commit -m x"
        self.assertEqual(strip_data_heredocs(cmd), cmd)

    def test_piped_to_interpreter_body_survives(self):
        cmd = "cat <<'EOF' | bash\ngit commit -m x\nEOF"
        self.assertEqual(strip_data_heredocs(cmd), cmd)

    def test_data_sink_allowlist_is_the_only_unblocking_lever(self):
        """Anything outside `HEREDOC_DATA_SINKS` keeps its body. Pinned so that
        growing the allowlist stays an explicit, reviewable act."""
        self.assertEqual(HEREDOC_DATA_SINKS, frozenset({"cat", "tee"}))
        cmd = "sponge /tmp/n.md <<'EOF'\ngit commit -m x\nEOF"
        self.assertEqual(strip_data_heredocs(cmd), cmd)

    def test_repeated_calls_are_stable(self):
        cmd = "cat <<'EOF'\ndata\nEOF"
        self.assertEqual(strip_data_heredocs(cmd), strip_data_heredocs(cmd))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
