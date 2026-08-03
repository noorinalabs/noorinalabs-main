#!/usr/bin/env python3
"""Regression tests for main#1168 — a non-interpreter RELAY downstream of a
heredoc's data-sink defeats the pipe-follow classifier.

Shape
=====

    cat <<'DELIM' | xargs -I{} bash -c "{}"
    git -c user.name="X" -c user.email="Y" commit -m z
    DELIM

`_opener_feeds_interpreter` (`_shell_parse.py`) walks the `|`-connected
segments downstream of a heredoc's owning data-sink segment, looking for a
`SHELL_INTERPRETERS` member. `xargs` is not one, so the OLD walk found nothing
and resolved the ambiguity to DATA — backwards relative to every other
ambiguity in this classifier, which resolves toward CODE (main#1152's rule).
Real-shell-verified (marker proxy: a command appended to a log file inside the
heredoc body, confirmed to run) at both `fea0dca` and PR #1155's head
`e163320`: pre-existing, not a #1155 regression.

The fix flips the downstream default: an unresolved/unknown relay head now
resolves to CODE. `HEREDOC_INERT_RELAY_FILTERS` is the narrow, explicit,
real-shell-measured allowlist of commands proven to have no code-execution
surface reachable from their own stdin — the false-positive escape hatch so
`cat <<'EOF' | grep foo` (a genuinely inert documentation pipeline) does not
newly false-block.

Test organisation
==================

  * `RelayBypassBlocksTests` — the primary shape and its variants, through the
    real `check()`.
  * `RelayFalsePositiveCorpusTests` — every `HEREDOC_INERT_RELAY_FILTERS`
    member, individually and chained, must stay ALLOW.
  * `RelayExcludedFiltersBlockTests` — `sed`/`awk` are DELIBERATELY excluded
    from the allowlist (both have a data-driven code-execution surface); this
    pins that they now resolve to CODE, and that the adversarial shapes which
    justify the exclusion are real bypasses if they were ever allowlisted.
  * `RealShellGroundTruthTests` — marker-proxy verification against an actual
    `bash`/`zsh`, per shape, so a verdict is checked against what the shell
    really does rather than against expectations.
  * `RelayClassifierUnitTests` — pins the `_shell_parse` primitives directly
    (constants, `_opener_feeds_interpreter`), including the regression this
    fix's first draft introduced (`tee`/`cat` downstream must stay inert).
  * `SiblingIssueMeasurementTests` — main#1170 (FIFO relay) and main#1171
    (backslash-continuation relay) measurements: #1171 shares this fix's exact
    root cause and closes incidentally; #1170 is a structurally different gap
    (dataflow through a named pipe across `&`) and stays open. Both are
    explicitly noted per the #1168 spawn brief rather than left implied.

Run: ENVIRONMENT=test python3 -m pytest .claude/hooks/tests/test_heredoc_relay_downstream.py -v
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
sys.path.insert(0, str(_HOOKS_DIR))

import validate_commit_identity as hook  # noqa: E402
from _shell_parse import (  # noqa: E402
    HEREDOC_DATA_SINKS,
    HEREDOC_INERT_RELAY_FILTERS,
    SHELL_INTERPRETERS,
    classify_heredocs,
    strip_data_heredocs,
)

REAL_COMMIT = 'git -c user.name="X" -c user.email="Y" commit -m z'


def _bash(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


def _assert_blocked(test: unittest.TestCase, cmd: str) -> None:
    result = hook.check(_bash(cmd))
    test.assertIsNotNone(result, f"must block: {cmd!r}")
    assert result is not None
    test.assertEqual(result["decision"], "block")
    test.assertIn("indirect-exec", result["reason"])


def _assert_allowed(test: unittest.TestCase, cmd: str) -> None:
    result = hook.check(_bash(cmd))
    test.assertIsNone(
        result,
        f"must allow: {cmd!r} (got: {result['reason'].splitlines()[0] if result else ''})",
    )


class RelayBypassBlocksTests(unittest.TestCase):
    """The primary shape from the issue, and the stated same-family variants."""

    def test_xargs_dash_i_bash_dash_c_literal_repro(self):
        """The exact reproduction from the #1168 issue body."""
        _assert_blocked(
            self, f"cat <<'DELIM' | xargs -I{{}} bash -c \"{{}}\"\n{REAL_COMMIT}\nDELIM"
        )

    def test_xargs_bash_c_single_quoted(self):
        _assert_blocked(self, f"cat <<'DELIM' | xargs -I{{}} bash -c '{{}}'\n{REAL_COMMIT}\nDELIM")

    def test_xargs_relay_via_tee_sink(self):
        """`tee` (the other known data sink) as the OWNING segment, relayed
        through `xargs` — both halves of the classifier exercised together."""
        _assert_blocked(
            self, f"tee <<'DELIM' | xargs -I{{}} bash -c \"{{}}\"\n{REAL_COMMIT}\nDELIM"
        )

    def test_xargs_relay_to_sh(self):
        _assert_blocked(self, f"cat <<'DELIM' | xargs -I{{}} sh -c \"{{}}\"\n{REAL_COMMIT}\nDELIM")

    def test_relay_chained_through_an_allowlisted_filter_first(self):
        """A filter chain: `cat | wc` alone would stay data, but the same
        pipeline continuing on to `xargs bash -c` must still resolve to CODE
        — the walk must not stop early just because an early hop is inert."""
        _assert_blocked(
            self,
            "cat <<'DELIM' | grep . | xargs -I{} bash -c \"{}\"\n" + REAL_COMMIT + "\nDELIM",
        )

    def test_unknown_relay_with_no_recognised_binary_at_all(self):
        """A completely unrecognised relay name (not `xargs`, not anything
        named in this module) must ALSO resolve to CODE — the fix is a
        default-direction flip, not a `xargs`-specific special case."""
        _assert_blocked(self, f"cat <<'DELIM' | some-custom-relay-tool -c\n{REAL_COMMIT}\nDELIM")

    def test_pipe_ampersand_relay_variant(self):
        """`|&` (main#1155's `2>&1 |` shorthand) reaching an unknown relay
        must resolve the same way plain `|` does."""
        _assert_blocked(
            self, f"cat <<'DELIM' |& xargs -I{{}} bash -c \"{{}}\"\n{REAL_COMMIT}\nDELIM"
        )


class RelayFalsePositiveCorpusTests(unittest.TestCase):
    """Every `HEREDOC_INERT_RELAY_FILTERS` member must stay ALLOW, individually
    and in common combinations — the false-positive corpus the design
    decision is measured against (see `RealShellGroundTruthTests` for the
    real-shell ground truth backing each one)."""

    # A representative, commonly-typed invocation per filter (not just the
    # bare name) — the corpus must hold under ordinary flags, not just the
    # zero-flag form.
    REPRESENTATIVE_INVOCATIONS = {
        "grep": "grep foo",
        "egrep": "egrep foo",
        "fgrep": "fgrep foo",
        "wc": "wc -l",
        "sort": "sort -u",
        "uniq": "uniq -c",
        "head": "head -n 5",
        "tail": "tail -n 5",
        "cut": "cut -d, -f1",
        "tr": "tr a-z A-Z",
        "column": "column -t",
        "nl": "nl -ba",
        "rev": "rev",
        "fold": "fold -w 40",
        "expand": "expand -t4",
        "unexpand": "unexpand",
        "base64": "base64",
        "md5sum": "md5sum",
        "sha1sum": "sha1sum",
        "sha256sum": "sha256sum",
        "sha512sum": "sha512sum",
        "cksum": "cksum",
        "od": "od -c",
        "xxd": "xxd",
        "hexdump": "hexdump -C",
        "join": "join -j1 /dev/null -",
        "paste": "paste -",
        "comm": "comm -12 /dev/null -",
        "tac": "tac",
        "shuf": "shuf",
        "jq": "jq -R .",
    }

    def test_every_allowlisted_filter_has_a_representative_case(self):
        """The corpus table above must cover the WHOLE allowlist — a filter
        added to `HEREDOC_INERT_RELAY_FILTERS` without a paired FP-corpus row
        is exactly the kind of silent widening this fix must not do."""
        self.assertEqual(set(self.REPRESENTATIVE_INVOCATIONS), set(HEREDOC_INERT_RELAY_FILTERS))

    def test_each_allowlisted_filter_stays_allowed(self):
        for name, invocation in self.REPRESENTATIVE_INVOCATIONS.items():
            with self.subTest(filter=name):
                _assert_allowed(self, f"cat <<'DELIM' | {invocation}\n{REAL_COMMIT}\nDELIM")

    def test_chained_allowlisted_filters_stay_allowed(self):
        """A realistic documentation pipeline chaining several filters."""
        _assert_allowed(
            self, f"cat <<'DELIM' | grep -v '^#' | sort | uniq -c\n{REAL_COMMIT}\nDELIM"
        )

    def test_tee_downstream_of_a_relay_chain_stays_allowed(self):
        """`HEREDOC_DATA_SINKS` members (`cat`/`tee`) are exactly as inert
        reached DOWNSTREAM of a filter as they are at the owning position —
        this is the regression the first draft of this fix introduced and
        that `RelayClassifierUnitTests` also pins directly."""
        _assert_allowed(self, f"cat <<'DELIM' | grep foo | tee /tmp/out.txt\n{REAL_COMMIT}\nDELIM")

    def test_plain_tee_sink_still_allowed_unpiped(self):
        _assert_allowed(self, f"cat <<'DELIM' | tee /tmp/a.md\n{REAL_COMMIT}\nDELIM")

    def test_pipe_ampersand_to_data_sink_still_allowed(self):
        _assert_allowed(self, f"cat <<'DELIM' |& tee /tmp/a\n{REAL_COMMIT}\nDELIM")


class RelayExcludedFiltersBlockTests(unittest.TestCase):
    """`sed`/`awk` are common "obviously inert filter" examples but carry a
    data-driven code-execution surface (real-shell-verified — see
    `RealShellGroundTruthTests`), so they are DELIBERATELY excluded from
    `HEREDOC_INERT_RELAY_FILTERS`. This costs a false positive on ordinary
    `sed`/`awk` documentation pipelines, accepted per the module comment."""

    def test_sed_not_in_allowlist(self):
        self.assertNotIn("sed", HEREDOC_INERT_RELAY_FILTERS)

    def test_awk_not_in_allowlist(self):
        self.assertNotIn("awk", HEREDOC_INERT_RELAY_FILTERS)

    def test_plain_sed_now_blocks_accepted_false_positive(self):
        """An ORDINARY, harmless `sed` substitution — the false-positive cost
        this exclusion accepts."""
        _assert_blocked(self, f"cat <<'DELIM' | sed 's/x/y/'\n{REAL_COMMIT}\nDELIM")

    def test_plain_awk_now_blocks_accepted_false_positive(self):
        _assert_blocked(self, f"cat <<'DELIM' | awk '{{print}}'\n{REAL_COMMIT}\nDELIM")

    def test_sed_e_flag_would_be_a_real_bypass_if_allowlisted(self):
        """The adversarial shape that justifies excluding `sed`: the GNU `e`
        flag executes the (input-derived) pattern space as a shell command.
        Confirmed BLOCKED under the current (exclude) policy; `sed` must
        never be added to the allowlist without also gating this flag."""
        _assert_blocked(self, f"cat <<'DELIM' | sed 's/.*/&/e'\n{REAL_COMMIT}\nDELIM")

    def test_awk_system_would_be_a_real_bypass_if_allowlisted(self):
        _assert_blocked(self, f"cat <<'DELIM' | awk '{{system($0)}}'\n{REAL_COMMIT}\nDELIM")


@unittest.skipUnless(shutil.which("bash"), "bash not installed")
class RealShellGroundTruthTests(unittest.TestCase):
    """Marker-proxy verification against a REAL shell: a marker command is
    appended to a log file inside the heredoc body, and the test checks
    whether the log was actually written — not whether the verdict "looks
    safe". Every shape here is checked BOTH ways: the hook's verdict AND the
    real-shell ground truth, and the test fails if they disagree in the
    dangerous direction (shell runs it, hook allows it).
    """

    SHELLS = tuple(s for s in ("bash", "zsh") if shutil.which(s))

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp(prefix="relay-ground-truth-")
        self.addCleanup(shutil.rmtree, self._tmpdir, ignore_errors=True)
        self._log = str(Path(self._tmpdir) / "marker.log")

    def _shell_actually_runs(self, template: str, shell: str) -> bool:
        """True if `template` (with MARKER substituted) genuinely executes
        the marker command under `shell`. Uses a marker echo rather than a
        literal `git commit` string so the probe script itself is not what
        it is testing (an actual `git commit` line would also be scanned by
        this repo's OWN commit-identity hook when this test file is committed
        — the marker keeps the fixture inert to that unrelated concern)."""
        marker_cmd = f"echo RAN >> {self._log}"
        cmd = template.replace("MARKER", marker_cmd)
        Path(self._log).unlink(missing_ok=True)
        subprocess.run(
            [shell, "-c", cmd],
            cwd=self._tmpdir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return Path(self._log).exists() and Path(self._log).stat().st_size > 0

    def _hook_blocks(self, template: str) -> bool:
        cmd = template.replace("MARKER", REAL_COMMIT)
        result = hook.check(_bash(cmd))
        return result is not None and result.get("decision") == "block"

    def _assert_ground_truth_matches_verdict(self, template: str, *, expect_runs: bool) -> None:
        for shell in self.SHELLS:
            with self.subTest(shell=shell, template=template):
                runs = self._shell_actually_runs(template, shell)
                self.assertEqual(
                    runs,
                    expect_runs,
                    f"{shell} {'did not run' if expect_runs else 'ran'} the marker for: {template}",
                )
        blocked = self._hook_blocks(template)
        if expect_runs:
            self.assertTrue(
                blocked, f"shell genuinely runs this body but hook allows it: {template}"
            )
        else:
            self.assertFalse(blocked, f"shell never runs this body but hook blocks it: {template}")

    # --- relay shapes: shell genuinely runs the body -----------------------

    def test_xargs_bash_dash_c_relay_genuinely_runs(self):
        self._assert_ground_truth_matches_verdict(
            "cat <<'DELIM' | xargs -I{} bash -c \"{}\"\nMARKER\nDELIM",
            expect_runs=True,
        )

    def test_xargs_sh_dash_c_relay_genuinely_runs(self):
        self._assert_ground_truth_matches_verdict(
            "cat <<'DELIM' | xargs -I{} sh -c \"{}\"\nMARKER\nDELIM",
            expect_runs=True,
        )

    # --- allowlisted filters: shell genuinely does NOT run the body --------

    def test_grep_relay_genuinely_inert(self):
        self._assert_ground_truth_matches_verdict(
            "cat <<'DELIM' | grep MARKERPATTERN_ABSENT\nMARKER\nDELIM",
            expect_runs=False,
        )

    def test_wc_relay_genuinely_inert(self):
        self._assert_ground_truth_matches_verdict(
            "cat <<'DELIM' | wc -l\nMARKER\nDELIM",
            expect_runs=False,
        )

    def test_sort_relay_genuinely_inert(self):
        self._assert_ground_truth_matches_verdict(
            "cat <<'DELIM' | sort\nMARKER\nDELIM",
            expect_runs=False,
        )

    def test_column_relay_genuinely_inert(self):
        self._assert_ground_truth_matches_verdict(
            "cat <<'DELIM' | column -t\nMARKER\nDELIM",
            expect_runs=False,
        )

    def test_base64_relay_genuinely_inert(self):
        self._assert_ground_truth_matches_verdict(
            "cat <<'DELIM' | base64\nMARKER\nDELIM",
            expect_runs=False,
        )

    def test_tee_downstream_of_a_filter_genuinely_inert(self):
        self._assert_ground_truth_matches_verdict(
            "cat <<'DELIM' | grep -v NOPE | tee /dev/null\nMARKER\nDELIM",
            expect_runs=False,
        )

    # --- excluded filters: the adversarial flag genuinely runs the body ----

    def test_sed_plain_genuinely_inert_but_excluded_anyway(self):
        """Ground truth: plain `sed` substitution does NOT execute the body
        (confirms the false-positive cost is real, not imagined). Deliberately
        NOT run through `_assert_ground_truth_matches_verdict` — that helper
        asserts the hook verdict MATCHES shell reality, which is the wrong
        check here: this is the ACCEPTED false positive (hook blocks even
        though the shell would not run it), not a bug to catch."""
        template = "cat <<'DELIM' | sed 's/x/y/'\nMARKER\nDELIM"
        for shell in self.SHELLS:
            with self.subTest(shell=shell):
                self.assertFalse(
                    self._shell_actually_runs(template, shell),
                    f"{shell} unexpectedly ran a plain sed substitution",
                )
        self.assertTrue(
            self._hook_blocks(template),
            "sed is excluded from the allowlist, so this accepted false positive must still block",
        )

    def test_sed_e_flag_genuinely_runs(self):
        """The adversarial case: ground truth confirms `sed`'s `e` flag really
        does execute input-derived text as a shell command — this is why
        `sed` stays off the allowlist entirely, not gated per-invocation."""
        self._assert_ground_truth_matches_verdict(
            "cat <<'DELIM' | sed 's/.*/&/e'\nMARKER\nDELIM",
            expect_runs=True,
        )

    def test_awk_system_genuinely_runs(self):
        self._assert_ground_truth_matches_verdict(
            "cat <<'DELIM' | awk '{system($0)}'\nMARKER\nDELIM",
            expect_runs=True,
        )


class RelayClassifierUnitTests(unittest.TestCase):
    """Pins the `_shell_parse` primitives directly, so a failure localises to
    the classifier rather than only to the hook's aggregate verdict."""

    def test_xargs_not_in_either_allowlist(self):
        """`xargs` — the primary relay named in the issue — must be neither a
        known data sink nor a known-inert filter: it is the unresolved case
        the fix's new default exists to catch."""
        self.assertNotIn("xargs", HEREDOC_DATA_SINKS)
        self.assertNotIn("xargs", HEREDOC_INERT_RELAY_FILTERS)

    def test_allowlists_are_disjoint(self):
        """`HEREDOC_DATA_SINKS` and `HEREDOC_INERT_RELAY_FILTERS` answer
        different questions (write-to-file vs. filter-in-place); a name
        should not need to live in both."""
        self.assertEqual(set(), HEREDOC_DATA_SINKS & HEREDOC_INERT_RELAY_FILTERS)

    def test_interpreters_and_inert_filters_are_disjoint(self):
        self.assertEqual(set(), SHELL_INTERPRETERS & HEREDOC_INERT_RELAY_FILTERS)

    def test_classify_heredocs_marks_relay_span_code(self):
        (span,) = classify_heredocs(
            f"cat <<'DELIM' | xargs -I{{}} bash -c \"{{}}\"\n{REAL_COMMIT}\nDELIM"
        )
        self.assertTrue(span.is_code)

    def test_classify_heredocs_marks_allowlisted_filter_span_data(self):
        (span,) = classify_heredocs(f"cat <<'DELIM' | grep foo\n{REAL_COMMIT}\nDELIM")
        self.assertFalse(span.is_code)

    def test_strip_data_heredocs_erases_allowlisted_filter_body(self):
        cmd = f"cat <<'DELIM' | wc -l\n{REAL_COMMIT}\nDELIM"
        out = strip_data_heredocs(cmd)
        self.assertNotIn("commit", out)

    def test_strip_data_heredocs_keeps_relay_body(self):
        cmd = f"cat <<'DELIM' | xargs -I{{}} bash -c \"{{}}\"\n{REAL_COMMIT}\nDELIM"
        out = strip_data_heredocs(cmd)
        self.assertIn("commit", out)

    def test_multi_hop_pipeline_stops_walk_correctly_at_end_of_segments(self):
        """A pipeline ending in an allowlisted filter (nothing after it) must
        resolve overall to DATA — the loop must not spuriously continue past
        the last segment."""
        (span,) = classify_heredocs(f"cat <<'DELIM' | grep foo | sort | uniq\n{REAL_COMMIT}\nDELIM")
        self.assertFalse(span.is_code)

    def test_unresolvable_downstream_segment_resolves_to_code(self):
        """A downstream segment that does not even TOKENIZE (an unbalanced
        quote — `_segment_head_command` returns `None`) must resolve to CODE,
        independent of any specific relay name. Pinned directly rather than
        only through the main#1171 coincidence in
        `SiblingIssueMeasurementTests`, so a future change to that sibling
        shape cannot silently stop exercising this branch."""
        cmd = "cat <<'DELIM' | \"unterminated\n" + REAL_COMMIT + "\nDELIM"
        (span,) = classify_heredocs(cmd)
        self.assertTrue(span.is_code)


class SiblingIssueMeasurementTests(unittest.TestCase):
    """main#1170 / main#1171 measurements, per the #1168 spawn brief's
    explicit instruction to report (not silently leave implied) whether this
    fix incidentally closes either sibling. Both touch the SAME file and are
    held as separate PRs; these tests only MEASURE the current state, they do
    not claim ownership of either issue.
    """

    def test_1171_backslash_continuation_relay_closes_incidentally(self):
        """main#1171: `cat <<'D' | \\` + newline + `bash` — the issue's own
        root-cause diagnosis names this classifier's downstream branch
        explicitly ("the same fail-open downstream branch as main#1168"), so
        this fix's default-flip closes it as a side effect, not by folding
        physical lines into logical ones (#1171's own suggested proper fix,
        still undone)."""
        cmd = "cat <<'D' | \\\nbash\n" + REAL_COMMIT + "\nD"
        _assert_blocked(self, cmd)

    def test_1171_continued_prose_opener_false_positive_still_allowed(self):
        """#1171's own acceptance bullet: a continuation INSIDE a data
        heredoc's opener line, with no interpreter at all, must stay ALLOW."""
        cmd = "cat > \\\nnotes.md <<'EOF'\nsome prose about bash -c 'foo'\nEOF"
        _assert_allowed(self, cmd)

    def test_1170_fifo_relay_measured_still_open(self):
        """main#1170: `mkfifo p; bash < p & cat <<'D' > p` — a structurally
        different gap (dataflow through a named pipe across a `&`
        background-job boundary, not a `|`-connected pipeline segment this
        fix's walk ever reaches). Measured to remain ALLOW after this fix;
        NOT folded in per the spawn brief's explicit scope boundary. This
        test pins today's measurement and is expected to start FAILING (in
        the good direction) once #1170 lands its own fix — at which point it
        should be deleted, not "fixed" to assert BLOCK, since that fix
        belongs to #1170's own PR.
        """
        cmd = "mkfifo p; bash < p & cat <<'D' > p\n" + REAL_COMMIT + "\nD"
        _assert_allowed(self, cmd)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
