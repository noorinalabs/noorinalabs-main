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

import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
sys.path.insert(0, str(_HOOKS_DIR))

import validate_commit_identity as hook  # noqa: E402
from _shell_parse import (  # noqa: E402
    classify_heredocs,
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


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
