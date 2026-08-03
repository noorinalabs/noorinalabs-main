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

main#1316 (PR #1316 rework, merge-gate finding): `sort` shipped on this
allowlist measured only on its PLAIN invocation; `sort --compress-program=CMD`
genuinely runs CMD with the heredoc's own data on its stdin once the sort
spills to a temp file (attacker-controlled padding crosses the `-S` spill
threshold). Dropped from the allowlist for the same reason `sed`/`awk` are
excluded — a plain invocation being inert does not make the command safe to
allowlist wholesale, and a per-flag detector for `--compress-program` would
reintroduce exactly the per-command grammar this set is designed to avoid.
main#1316 (second pass — merge-gate finding on the SAME PR): `rg` was folded
INTO the allowlist by this fix's first pass, on the reasoning that `grep`
(forbidden org-wide by main#1008) was on the list while its mandated
replacement `rg` was not. That measurement covered only the no-PATH stdin-pipe
form of `rg --pre=COMMAND`; ripgrep's own docs say `--pre` runs "for each input
PATH", and a PATH is attacker-supplied — naming the pipe itself (`/dev/stdin`,
`/dev/fd/0`) gives `--pre` a PATH even on a pure stdin pipe, and `rg` runs
`COMMAND PATH` with that path opened on the child's own stdin, so
`sh /dev/stdin` genuinely executes the heredoc body (measured, both bash and
zsh). `rg` is now EXCLUDED from the allowlist entirely, same posture as
`sed`/`awk`/`sort` below — a plain-form measurement is not sufficient, and a
per-flag gate for `--pre` would reintroduce the per-command grammar this set
avoids. `rg` also exposes `--hostname-bin=COMMAND`, a second exec-shaped flag
that spawns an arbitrary program on a pure stdin pipe (no PATH needed) but
does not itself reach the heredoc body. The #1008 contradiction (this
allowlist admits forbidden `grep` while excluding mandated `rg`) is left OPEN
by this exclusion — see the PR body.

main#1316 (third pass — CI-only red, #1318): the `rg` ground-truth rows above
passed locally but failed on the CI runner. Root cause: `ci.yml` never
installed ripgrep, so `rg` was simply absent on `ubuntu-latest` — the
`--pre`/`--hostname-bin` rows either genuinely failed (an `expect_runs=True`
assertion, loud) or, worse, would have passed VACUOUSLY had they asserted
`expect_runs=False` (the shell never even attempts a missing binary, which is
indistinguishable from a real inertness result). That means the FIRST-pass
measurement that got `rg` allowlisted in error was never actually exercised
against `rg` on CI at all — a vacuous pass, not a green light. Fixed by
installing ripgrep in the pytest job (same "install it so it RUNS in CI
rather than skipping" pattern already used for bashlex/zsh above), with a
`skipUnless(shutil.which("rg"))` guard kept alongside — not instead — as a
documented fallback for a runner that genuinely lacks it (a guard with no
install would just convert the vacuous pass back into a silent skip, which is
the state that let this happen in the first place).

Test organisation
==================

  * `RelayBypassBlocksTests` — the primary shape and its variants, through the
    real `check()`.
  * `RelayFalsePositiveCorpusTests` — every `HEREDOC_INERT_RELAY_FILTERS`
    member, individually and chained, must stay ALLOW.
  * `RelayExcludedFiltersBlockTests` — `sed`/`awk`/`sort`/`rg` are
    DELIBERATELY excluded from the allowlist (each has a data-driven
    code-execution surface reachable through an exec-shaped flag — `sed`'s
    `e` flag, `awk`'s `system()`, `sort`'s `--compress-program`, `rg`'s
    `--pre=COMMAND` with an attacker-supplied `/dev/stdin` PATH); this pins
    that they now resolve to CODE, and that the adversarial shapes which
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

# main#1316/#1318: `rg` is not part of the base ubuntu-latest image (unlike
# grep/sed/awk/sort/coreutils, which ship on every runner). A missing binary
# is directional poison for a ground-truth row: an `expect_runs=False`
# assertion passes VACUOUSLY when the shell never even attempts `rg` (measures
# nothing, looks identical to a real inertness result), while an
# `expect_runs=True` assertion fails loudly (the real bug signal that
# surfaced this). `ci.yml` now installs ripgrep for the pytest job so these
# rows normally RUN rather than skip; this guard is the documented fallback
# for a runner that genuinely lacks it, not a substitute for the install —
# per main#1318's finding, a guard alone would just convert the vacuous pass
# back into a silent skip, which is the state that let `rg` reach the
# allowlist in the first place.
_RG_INSTALLED = shutil.which("rg") is not None
_RG_SKIP_REASON = (
    "rg not installed on this runner — see main#1316/#1318: without it this "
    "row cannot measure real rg behaviour (an expect_runs=False assertion "
    "would pass vacuously); ci.yml installs ripgrep for the pytest job so "
    "this should normally run here, not skip"
)


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
        """A realistic documentation pipeline chaining several filters.
        Uses `cut`/`uniq` rather than `sort` — `sort` is no longer
        allowlisted as of main#1316 (see `RelayExcludedFiltersBlockTests`)."""
        _assert_allowed(
            self, f"cat <<'DELIM' | grep -v '^#' | cut -d, -f1 | uniq -c\n{REAL_COMMIT}\nDELIM"
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
    """`sed`/`awk`/`sort`/`rg` are common "obviously inert filter" examples but
    each carries a data-driven code-execution surface (real-shell-verified —
    see `RealShellGroundTruthTests`), so they are DELIBERATELY excluded from
    `HEREDOC_INERT_RELAY_FILTERS`. This costs a false positive on ordinary
    `sed`/`awk`/`sort`/`rg` documentation pipelines, accepted per the module
    comment. `sort` was excluded in main#1316 (first pass), after having
    shipped on the allowlist measured only on its plain (no
    `--compress-program`) form. `rg` was excluded in main#1316's SECOND pass
    (this rework) after having been ADDED in the same PR's first pass on a
    measurement that covered only the no-PATH stdin-pipe form of `--pre` —
    the same "measure the plain/context-fixed form only" mistake `sort` had
    just been dropped for."""

    def test_sed_not_in_allowlist(self):
        self.assertNotIn("sed", HEREDOC_INERT_RELAY_FILTERS)

    def test_awk_not_in_allowlist(self):
        self.assertNotIn("awk", HEREDOC_INERT_RELAY_FILTERS)

    def test_sort_not_in_allowlist(self):
        self.assertNotIn("sort", HEREDOC_INERT_RELAY_FILTERS)

    def test_rg_not_in_allowlist(self):
        self.assertNotIn("rg", HEREDOC_INERT_RELAY_FILTERS)

    def test_plain_sed_now_blocks_accepted_false_positive(self):
        """An ORDINARY, harmless `sed` substitution — the false-positive cost
        this exclusion accepts."""
        _assert_blocked(self, f"cat <<'DELIM' | sed 's/x/y/'\n{REAL_COMMIT}\nDELIM")

    def test_plain_awk_now_blocks_accepted_false_positive(self):
        _assert_blocked(self, f"cat <<'DELIM' | awk '{{print}}'\n{REAL_COMMIT}\nDELIM")

    def test_plain_sort_now_blocks_accepted_false_positive(self):
        """An ORDINARY, harmless bare `sort` — genuinely inert (see
        `RealShellGroundTruthTests`), but no longer allowlisted; the
        false-positive cost this exclusion accepts, same posture as
        `sed`/`awk` above."""
        _assert_blocked(self, f"cat <<'DELIM' | sort\n{REAL_COMMIT}\nDELIM")

    def test_plain_rg_now_blocks_accepted_false_positive(self):
        """An ORDINARY, harmless bare `rg` search — genuinely inert (see
        `RealShellGroundTruthTests`), but no longer allowlisted; the
        false-positive cost this exclusion accepts, same posture as
        `sed`/`awk`/`sort` above."""
        _assert_blocked(self, f"cat <<'DELIM' | rg foo\n{REAL_COMMIT}\nDELIM")

    def test_sed_e_flag_would_be_a_real_bypass_if_allowlisted(self):
        """The adversarial shape that justifies excluding `sed`: the GNU `e`
        flag executes the (input-derived) pattern space as a shell command.
        Confirmed BLOCKED under the current (exclude) policy; `sed` must
        never be added to the allowlist without also gating this flag."""
        _assert_blocked(self, f"cat <<'DELIM' | sed 's/.*/&/e'\n{REAL_COMMIT}\nDELIM")

    def test_awk_system_would_be_a_real_bypass_if_allowlisted(self):
        _assert_blocked(self, f"cat <<'DELIM' | awk '{{system($0)}}'\n{REAL_COMMIT}\nDELIM")

    def test_sort_compress_program_would_be_a_real_bypass_if_allowlisted(self):
        """The adversarial shape that justifies excluding `sort`:
        `--compress-program=CMD` runs CMD with the heredoc's own data on its
        stdin once the sort spills to a temp file. Confirmed BLOCKED under
        the current (exclude) policy; `sort` must never be re-added to the
        allowlist without also gating this flag."""
        _assert_blocked(
            self,
            "cat <<'DELIM' | sort --compress-program=/tmp/marker.sh\n" + REAL_COMMIT + "\nDELIM",
        )

    def test_rg_pre_dev_stdin_would_be_a_real_bypass_if_allowlisted(self):
        """The adversarial shape that justifies excluding `rg`: `--pre=COMMAND`
        runs `COMMAND PATH` once for each input PATH, and the PATH is
        attacker-supplied — naming the pipe itself (`/dev/stdin`) gives
        `--pre` a PATH even though the input is a pure stdin pipe, and `rg`
        runs `COMMAND PATH` with that path opened on the child's own stdin,
        so `sh /dev/stdin` genuinely executes the heredoc body. Confirmed
        BLOCKED under the current (exclude) policy; `rg` must never be
        re-added to the allowlist without also gating this flag (and
        `--hostname-bin`, a second exec-shaped flag — see the module
        comment). Deliberately varies the PATH (`/dev/stdin`) rather than
        fixing it at none, unlike this same allowlist's own first-pass
        `rg --pre` measurement, which is exactly why that pass missed this."""
        _assert_blocked(
            self,
            "cat <<'DELIM' | rg --pre=/bin/sh pat /dev/stdin\n" + REAL_COMMIT + "\nDELIM",
        )


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

    def _write_marker_passthrough_script(self) -> str:
        """Write an executable that appends to `self._log` (proof of
        execution) then passes stdin to stdout unchanged. Some exec-shaped
        flags (`sort --compress-program=CMD`, `rg --pre COMMAND`) name an
        external PROGRAM rather than accepting an inline shell fragment, so
        the MARKER-substitution used elsewhere in this class does not apply
        — a real file is required."""
        script = Path(self._tmpdir) / "marker_passthrough.sh"
        script.write_text(f"#!/bin/sh\necho RAN >> {self._log}\nexec cat\n")
        script.chmod(0o755)
        return str(script)

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

    def test_sort_plain_genuinely_inert_but_excluded_anyway(self):
        """Ground truth: a bare `sort` (no `--compress-program`) does NOT
        execute the body (confirms the false-positive cost `sort`'s
        exclusion accepts is real, not imagined) — same posture as the
        `sed` case above. This is why `sort` shipped on the allowlist in the
        first place before main#1316: its plain form really is inert."""
        template = "cat <<'DELIM' | sort\nMARKER\nDELIM"
        for shell in self.SHELLS:
            with self.subTest(shell=shell):
                self.assertFalse(
                    self._shell_actually_runs(template, shell),
                    f"{shell} unexpectedly ran a plain sort",
                )
        self.assertTrue(
            self._hook_blocks(template),
            "sort is excluded from the allowlist, so this accepted false positive must still block",
        )

    def test_sort_compress_program_genuinely_runs(self):
        """The adversarial case that justifies excluding `sort` (main#1316):
        `--compress-program=CMD` genuinely runs CMD with the heredoc's own
        (padded) data on its stdin once the sort spills to a temp file.
        `-S 1` sets a 1024-byte in-memory buffer; enough padded body lines
        cross that threshold and force the spill — the padding is exactly
        the attacker-controlled lever the module comment describes. Uses a
        real marker script (see `_write_marker_passthrough_script`), not an
        inline MARKER substitution, since `--compress-program` names an
        external program."""
        marker = self._write_marker_passthrough_script()
        padded_lines = "\n".join(f"line{i}-padding-padding-padding-padding" for i in range(500))
        template = (
            f"cat <<'DELIM' | sort -S 1 --compress-program={marker}\n{padded_lines}\nMARKER\nDELIM"
        )
        for shell in self.SHELLS:
            with self.subTest(shell=shell):
                self.assertTrue(
                    self._shell_actually_runs(template, shell),
                    f"{shell} did not invoke the `sort --compress-program` marker script",
                )
        self.assertTrue(
            self._hook_blocks(f"cat <<'DELIM' | sort --compress-program={marker}\nMARKER\nDELIM"),
            "sort is excluded from the allowlist, so this must still block",
        )

    @unittest.skipUnless(_RG_INSTALLED, _RG_SKIP_REASON)
    def test_rg_plain_genuinely_inert_but_excluded_anyway(self):
        """Ground truth: a bare `rg` search over stdin (no PATH argument, no
        exec-shaped flag) does NOT execute the body — confirms the
        false-positive cost `rg`'s exclusion accepts is real, not imagined,
        same posture as `sed`/`sort` above."""
        template = "cat <<'DELIM' | rg MARKERPATTERN_ABSENT\nMARKER\nDELIM"
        for shell in self.SHELLS:
            with self.subTest(shell=shell):
                self.assertFalse(
                    self._shell_actually_runs(template, shell),
                    f"{shell} unexpectedly ran a plain rg search",
                )
        self.assertTrue(
            self._hook_blocks(template),
            "rg is excluded from the allowlist, so this accepted false positive must still block",
        )

    @unittest.skipUnless(_RG_INSTALLED, _RG_SKIP_REASON)
    def test_rg_pre_flag_inert_without_a_path(self):
        """The CONTEXT-FIXED measurement from main#1316's FIRST pass (the one
        that got `rg` added to the allowlist in error): with no PATH argument
        at all, `--pre` really is a no-op — rg reads stdin directly and never
        invokes `--pre`'s COMMAND. Kept as a documented contrast with
        `test_rg_pre_dev_stdin_path_genuinely_runs` immediately below: the
        PATH is the variable that matters, and it is the ATTACKER'S to
        supply, not a fixed property of the shape — measuring only this cell
        is exactly the mistake that let `rg` onto the allowlist the first
        time. `rg` is fully excluded regardless (second pass), so the hook
        blocks here too, same as any other excluded-filter accepted false
        positive; this test's job is only to confirm the shell-side no-op,
        not the hook's verdict."""
        marker = self._write_marker_passthrough_script()
        template = f"cat <<'DELIM' | rg --pre={marker} commit\nMARKER\nDELIM"
        for shell in self.SHELLS:
            with self.subTest(shell=shell):
                self.assertFalse(
                    self._shell_actually_runs(template, shell),
                    f"{shell} invoked `rg --pre` with no PATH — should still be a no-op",
                )
        self.assertTrue(
            self._hook_blocks(f"cat <<'DELIM' | rg --pre={marker} commit\nMARKER\nDELIM"),
            "rg is excluded from the allowlist entirely, so this must block "
            "regardless of whether --pre happens to be a no-op in this particular cell",
        )

    @unittest.skipUnless(_RG_INSTALLED, _RG_SKIP_REASON)
    def test_rg_pre_dev_stdin_path_genuinely_runs(self):
        """The adversarial case that justifies excluding `rg` (main#1316
        second pass): `--pre=COMMAND` runs `COMMAND PATH` once for each input
        PATH, and the PATH is attacker-supplied. Naming the pipe itself
        (`/dev/stdin`) gives `--pre` a PATH even though the input is a pure
        stdin pipe, and rg runs `COMMAND PATH` with that path opened on the
        child's own stdin — so `sh /dev/stdin` genuinely executes the
        heredoc body. Deliberately VARIES the PATH (unlike the no-PATH test
        immediately above) — this is the row this fix's own first-pass test
        (`test_rg_pre_flag_genuinely_inert_on_stdin`, since removed/replaced)
        was missing, and the whole reason that test alone was not sufficient
        to allowlist `rg` safely."""
        self._assert_ground_truth_matches_verdict(
            "cat <<'DELIM' | rg --pre=/bin/sh pat /dev/stdin\nMARKER\nDELIM",
            expect_runs=True,
        )

    @unittest.skipUnless(_RG_INSTALLED, _RG_SKIP_REASON)
    def test_rg_hostname_bin_spawns_a_program_but_does_not_reach_the_body(self):
        """`rg` exposes a SECOND exec-shaped flag, `--hostname-bin=COMMAND`,
        found by the same systematic per-flag sweep that caught `--pre`.
        Ground truth: it spawns COMMAND even on a pure stdin pipe with no
        PATH at all — but the spawned child receives no arguments and does
        not inherit the heredoc's stdin, so it never reaches the heredoc
        body itself. Pinned here (rather than left as prose only) because
        its existence falsifies any claim that every `rg` flag is harmless
        on a heredoc-fed stdin pipe — the module comment names it explicitly
        for exactly this reason, and this test guards against that comment
        going stale if a future ripgrep version changes the behaviour.

        Uses TWO independent logs, not one: `_write_marker_passthrough_script`
        (used elsewhere in this class) writes its "I was invoked" marker to
        the SAME log the body-execution check reads, which cannot
        distinguish "the flag's program was spawned" from "the spawned
        program then read the heredoc body" — exactly the two outcomes this
        test needs to tell apart. `spawn_log` proves the flag's COMMAND ran
        at all; `body_log` proves the heredoc body's own marker command ran;
        the claim being pinned is spawn=True, body=False."""
        spawn_log = str(Path(self._tmpdir) / "hostname_bin_spawn.log")
        body_log = str(Path(self._tmpdir) / "hostname_bin_body.log")
        script = Path(self._tmpdir) / "hostname_bin.sh"
        script.write_text(f"#!/bin/sh\necho SPAWNED >> {spawn_log}\ncat\n")
        script.chmod(0o755)
        template = f"cat <<'DELIM' | rg --hostname-bin={script} --json pat\nMARKER\nDELIM"
        for shell in self.SHELLS:
            with self.subTest(shell=shell):
                Path(spawn_log).unlink(missing_ok=True)
                Path(body_log).unlink(missing_ok=True)
                marker_cmd = f"echo BODYRAN >> {body_log}"
                cmd = template.replace("MARKER", marker_cmd)
                subprocess.run(
                    [shell, "-c", cmd],
                    cwd=self._tmpdir,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                self.assertTrue(
                    Path(spawn_log).exists(),
                    f"{shell}: --hostname-bin never spawned its COMMAND — the flag "
                    "may no longer be exec-shaped in this ripgrep version",
                )
                self.assertFalse(
                    Path(body_log).exists(),
                    f"{shell}: --hostname-bin unexpectedly reached the heredoc body "
                    "— this would make it a real bypass, not just a spawn",
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
        the last segment. Uses `cut` rather than `sort` — `sort` is no
        longer allowlisted as of main#1316."""
        (span,) = classify_heredocs(
            f"cat <<'DELIM' | grep foo | cut -d, -f1 | uniq\n{REAL_COMMIT}\nDELIM"
        )
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

    # test_1170_fifo_relay_measured_still_open removed: main#1170 landed its
    # own fix (stdin-redirect operand resolution in
    # `parse_interpreter_invocation`/`_script_invocation_targets`, see
    # `_shell_parse.py`'s "Explicit scope boundary" comment above
    # `_segment_write_targets`). Both FIFO shapes from that issue now BLOCK;
    # coverage moved to `test_heredoc_write_then_exec.py`'s
    # `StdinRedirectOperandTests` (main#1170 reuses that same write-then-exec
    # correlation, just with the interpreter's script fed via `< FILE` rather
    # than a positional operand), per this test's own docstring instruction
    # to delete rather than flip the assertion here.


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
