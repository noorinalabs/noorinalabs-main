#!/usr/bin/env python3
"""Regression tests for main#1149 — interpreter option grammar in the commit-identity gate.

`validate_commit_identity` decided "is this `<shell> -c '<payload>'`?" with a
regex that required `-c` to be a BARE token immediately after the interpreter,
and "is this `<shell> <script>`?" with a regex that required the path to sit in
the same position. Real shells accept an arbitrary option run first, and accept
the command-string flag combined into a short-flag cluster. Eight of the nine
ordinary spellings in the issue therefore let an identity-less commit through,
and the whole `<shell> -x <script>` family did too.

The fix routes both shapes through `_shell_parse.parse_interpreter_invocation`,
which normalizes the interpreter's option tokens and then defers to the SHARED
`_consume_wrapper_options` primitive — one option-run implementation in the
module instead of two divergent regexes (main#1150's invariant).

What these tests pin, and why in this shape
===========================================

* `ShellTruthTests` is the load-bearing one. It runs a REAL shell and asks
  whether the payload actually executed, then requires the hook to block every
  form that did. The marker is assembled from random bytes at run time and the
  verdict is "did this file appear on disk", so a payload that is merely
  DISPLAYED (echoed, error-quoted) can never be scored as executed. Both #1151
  families survived the old suite precisely because the tests encoded the
  implementation instead of the shell.
* The remaining classes vary ONE dimension each — cluster spelling, option
  position, interpreter identity, payload quoting, segment role — because three
  consecutive review rounds on main#1155 each found a defect sitting in whatever
  the previous corpus had held constant.
* `MustStayAllowedTests` and `PreviouslyBlockedStillBlockTests` are the two
  no-regression directions. Widening a gate is only correct if nothing that
  blocked before now passes AND ordinary work is still allowed.

Run: python3 -m pytest .claude/hooks/tests/test_interpreter_option_grammar.py -v
"""

from __future__ import annotations

import os
import secrets
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
    SHELL_INTERPRETERS,
    _expand_shell_option_token,
    iter_interpreter_invocations,
    parse_interpreter_invocation,
)

# An identity-less commit: no `-c user.name=` / `-c user.email=` anywhere. Every
# shape below is a charter violation the gate exists to stop.
NAKED_COMMIT = "git commit -m x"


def verdict(command: str, *, cwd: str | None = None) -> str:
    """Run the hook over `command` and return "BLOCK" or "allow"."""
    payload: dict = {"tool_name": "Bash", "tool_input": {"command": command}}
    if cwd is not None:
        payload["cwd"] = cwd
    return "BLOCK" if hook.check(payload) else "allow"


class NineFormsFromTheIssueTests(unittest.TestCase):
    """The exact nine-row table from main#1149. Eight of these used to pass."""

    FORMS = [
        ("interpreter + bare -c", f"bash -c '{NAKED_COMMIT}'"),
        ("combined -lc", f"bash -lc '{NAKED_COMMIT}'"),
        ("combined -ic", f"bash -ic '{NAKED_COMMIT}'"),
        ("combined -xc", f"bash -xc '{NAKED_COMMIT}'"),
        ("combined -ec", f"bash -ec '{NAKED_COMMIT}'"),
        ("-l then separate -c", f"bash -l -c '{NAKED_COMMIT}'"),
        ("--login then separate -c", f"bash --login -c '{NAKED_COMMIT}'"),
        ("-o pipefail then separate -c", f"bash -o pipefail -c '{NAKED_COMMIT}'"),
        ("zsh with combined -lc", f"zsh -lc '{NAKED_COMMIT}'"),
    ]

    def test_all_nine_forms_block(self):
        for label, command in self.FORMS:
            with self.subTest(form=label):
                self.assertEqual(verdict(command), "BLOCK", command)

    def test_block_reason_names_the_shell_c_shape(self):
        result = hook.check(
            {"tool_name": "Bash", "tool_input": {"command": f"bash -lc '{NAKED_COMMIT}'"}}
        )
        assert result is not None
        self.assertIn("indirect-exec wrapper detected", result["reason"])
        self.assertIn("shell -c", result["reason"])


class ClusterSpellingTests(unittest.TestCase):
    """Vary the short-flag CLUSTER; hold interpreter and payload constant.

    `-cl` is the row that kills the "widen the regex to `-[a-z]*c`" shortcut the
    issue offered as a minimum-viable fix: the command-string letter does not
    have to be last in the cluster, and every shell measured runs the payload
    anyway.
    """

    CLUSTERS = ["-lc", "-cl", "-cx", "-ce", "-vc", "-uc", "-fc", "-lxc", "-abc", "-cabm"]

    def test_every_cluster_containing_c_blocks(self):
        for cluster in self.CLUSTERS:
            with self.subTest(cluster=cluster):
                self.assertEqual(verdict(f"bash {cluster} '{NAKED_COMMIT}'"), "BLOCK")

    def test_cluster_without_c_is_not_a_command_string(self):
        invocation = parse_interpreter_invocation(["bash", "-lx", NAKED_COMMIT])
        assert invocation is not None
        self.assertFalse(invocation.has_command_string)


class PrecedingOptionTests(unittest.TestCase):
    """Vary the option run BEFORE `-c`; hold cluster shape and payload constant."""

    OPTION_RUNS = [
        "-l",
        "-x",
        "-e",
        "-p",
        "-s",
        "+x",
        "--login",
        "--noprofile --norc",
        "-o pipefail",
        "+o histexpand",
        "-O extglob",
        "--rcfile /dev/null",
        "--init-file /dev/null",
        "-lo pipefail",
        "-l -x -o pipefail +o histexpand",
    ]

    def test_option_run_before_c_still_blocks(self):
        for run in self.OPTION_RUNS:
            with self.subTest(options=run):
                self.assertEqual(verdict(f"bash {run} -c '{NAKED_COMMIT}'"), "BLOCK")

    def test_value_letter_inside_cluster_does_not_shift_the_payload_away(self):
        """`bash -oc pipefail '<commit>'` — the clustered `o` eats `pipefail`.

        Measured under bash: the payload is the word AFTER the option value, so
        a walker that pairs the cluster naively resolves the payload to
        `pipefail`, finds no commit shape, and fails open.
        """
        self.assertEqual(verdict(f"bash -oc pipefail '{NAKED_COMMIT}'"), "BLOCK")

    def test_payload_consumed_as_an_option_value_is_still_scanned(self):
        """`zsh -cO '<commit>'` runs the payload, but the shared grammar pairs
        the clustered `-O` with it as a VALUE, leaving `operands` empty.

        Measured: `-cO`, `-Oc` and `-cOl` all execute under zsh (bash/sh/dash
        reject them). This is the shape that makes the gate scan
        `InterpreterInvocation.words` — the superset including option values —
        rather than `operands`. Scanning `operands` alone fails OPEN here.
        """
        for cluster in ("-cO", "-Oc", "-cOl"):
            with self.subTest(cluster=cluster):
                inv = parse_interpreter_invocation(["zsh", cluster, NAKED_COMMIT])
                assert inv is not None
                self.assertEqual(inv.operands, (), "precondition: operands must be empty")
                self.assertIn(NAKED_COMMIT, inv.words)
                self.assertEqual(verdict(f"zsh {cluster} '{NAKED_COMMIT}'"), "BLOCK")

    def test_plus_form_option_with_a_non_alpha_body(self):
        """`zsh +2 -c '<commit>'` executes; bash/sh/dash reject `+2` outright.

        This is the shape that justifies the `+`-with-non-alpha-body arm of
        `_expand_shell_option_token`. Without the `+` -> `-` rewrite, `+2` is
        not flag-shaped, the option run ends before `-c` is reached, and the
        gate fails open. `-2` (already flag-shaped) reaches the same place
        through the general path, so it does NOT cover the `+` arm.
        """
        self.assertEqual(_expand_shell_option_token("+2"), ["-2"])
        for pre in ("+2", "+1", "+0"):
            with self.subTest(option=pre):
                inv = parse_interpreter_invocation(["zsh", pre, "-c", NAKED_COMMIT])
                assert inv is not None
                self.assertTrue(inv.has_command_string)
                self.assertEqual(verdict(f"zsh {pre} -c '{NAKED_COMMIT}'"), "BLOCK")

    def test_double_dash_ends_the_option_run(self):
        """`bash -- -c '<commit>'` does NOT execute the payload under any shell.

        Pinned as an ALLOW so a future widening cannot quietly turn the option
        grammar into "does the text contain -c somewhere".
        """
        self.assertEqual(verdict(f"bash -- -c '{NAKED_COMMIT}'"), "allow")


class InterpreterIdentityTests(unittest.TestCase):
    """Vary the interpreter; hold flag shape and payload constant."""

    def test_every_recognised_interpreter_blocks(self):
        for name in sorted(SHELL_INTERPRETERS):
            with self.subTest(interpreter=name):
                self.assertEqual(verdict(f"{name} -lc '{NAKED_COMMIT}'"), "BLOCK")

    def test_absolute_path_interpreter_blocks(self):
        for path in ("/bin/bash", "/usr/bin/zsh", "/bin/sh", "/usr/local/bin/dash"):
            with self.subTest(path=path):
                self.assertEqual(verdict(f"{path} -lc '{NAKED_COMMIT}'"), "BLOCK")

    def test_non_interpreter_head_is_not_an_invocation(self):
        """`echo bash -lc '<commit>'` prints; it does not execute."""
        self.assertIsNone(parse_interpreter_invocation(["echo", "bash", "-lc", NAKED_COMMIT]))


class DashLeadingPayloadTests(unittest.TestCase):
    """Vary the payload's SURFACE SHAPE; hold interpreter and flag form constant.

    This dimension was missing from the first head of #1193 and it hid a live
    fail-open. Every other class here varies the *invocation*; none of them
    varied what the command string itself looks like, and the option-run walker
    is exactly the component whose answer depends on that.

    Two independent mechanisms swallow a `-`-leading command string:

      `bash -c -- '-x; <commit>'`  — `--` puts the payload in `operands`, but a
          whole-list flag filter dropped it again. `_DASH_C_RE` misses too: it
          captures the `--` itself as its payload group.
      `zsh -abc '-x; <commit>'`    — no `--` at all. `_consume_wrapper_options`
          treats every dash-leading token as an option, so the payload is
          swallowed INTO the option run and `operands` comes back empty.

    Both really execute (bash/sh/zsh/dash for the first, zsh for the second).
    """

    # The command string's leading characters, before the commit text.
    PREFIXES = ["-x; ", "--foo; ", "-", "--", "-x && ", "+x; ", "---; ", "-- "]

    def test_dash_leading_payload_after_double_dash_blocks(self):
        for prefix in self.PREFIXES:
            for interp in ("bash", "sh", "zsh", "dash"):
                with self.subTest(prefix=prefix, interpreter=interp):
                    command = f"{interp} -c -- '{prefix}{NAKED_COMMIT}'"
                    self.assertEqual(verdict(command), "BLOCK", command)

    def test_dash_leading_payload_swallowed_by_the_option_run_blocks(self):
        """No `--`: the payload is inside the option run, not in `operands`."""
        for cluster in ("-abc", "-cabm", "-lc", "-cl"):
            with self.subTest(cluster=cluster):
                inv = parse_interpreter_invocation(["zsh", cluster, "-x; " + NAKED_COMMIT])
                assert inv is not None
                self.assertEqual(inv.operands, (), "precondition: operands must be empty")
                self.assertIn("-x; " + NAKED_COMMIT, inv.words)
                self.assertEqual(verdict(f"zsh {cluster} '-x; {NAKED_COMMIT}'"), "BLOCK")

    def test_words_is_a_superset_of_operands(self):
        """The invariant that makes the gate immune to payload-index error."""
        cases = [
            ["bash", "-c", NAKED_COMMIT],
            ["bash", "-c", "--", "-x; " + NAKED_COMMIT],
            ["bash", "-oc", "pipefail", NAKED_COMMIT],
            ["zsh", "-cO", NAKED_COMMIT],
            ["zsh", "-abc", "-x; " + NAKED_COMMIT],
        ]
        for segment in cases:
            with self.subTest(segment=" ".join(segment)):
                inv = parse_interpreter_invocation(segment)
                assert inv is not None
                self.assertTrue(set(inv.operands).issubset(set(inv.words)))


class PayloadQuotingTests(unittest.TestCase):
    """Vary the payload QUOTING; hold interpreter and flag shape constant."""

    def test_quoting_variants_block(self):
        cases = {
            "single": f"bash -lc '{NAKED_COMMIT}'",
            "double": f'bash -lc "{NAKED_COMMIT}"',
            "backslash-escaped word": "bash -lc git\\ commit",
            "nested quotes": "bash -lc 'git commit -m \"a b\"'",
            "inner single in double": "bash -lc \"git commit -m 'a b'\"",
        }
        for label, command in cases.items():
            with self.subTest(quoting=label):
                self.assertEqual(verdict(command), "BLOCK", command)

    def test_unbalanced_quote_tail_does_not_restore_the_bypass(self):
        """One stray quote used to defeat the tokenizer and re-open every form.

        The invocation is well-formed; only the tail is broken. Quote repair in
        `iter_interpreter_invocations` recovers it.
        """
        cases = [
            f'bash -lc "{NAKED_COMMIT}" && echo "unclosed',
            f'bash -c "{NAKED_COMMIT}" && echo "unclosed',
            f"bash -lc '{NAKED_COMMIT}",
            f"bash -o pipefail -c '{NAKED_COMMIT}' ; echo 'unclosed",
        ]
        for command in cases:
            with self.subTest(command=command):
                self.assertEqual(verdict(command), "BLOCK", command)


class SegmentRoleTests(unittest.TestCase):
    """Vary the STRUCTURAL ROLE of the invocation; hold the invocation constant."""

    def test_invocation_in_any_segment_position_blocks(self):
        inner = f"bash -lc '{NAKED_COMMIT}'"
        cases = {
            "leading": inner,
            "after &&": f"cd /tmp && {inner}",
            "after ||": f"false || {inner}",
            "after ;": f"echo hi; {inner}",
            "after unspaced ;": f"echo hi;{inner}",
            "after newline": f"echo hi\n{inner}",
            "downstream of a pipe": f"echo hi | {inner}",
            "line continuation": "bash \\\n  -lc '%s'" % NAKED_COMMIT,
        }
        for label, command in cases.items():
            with self.subTest(position=label):
                self.assertEqual(verdict(command), "BLOCK", command)

    def test_transparent_wrappers_do_not_hide_the_invocation(self):
        inner = f"bash -lc '{NAKED_COMMIT}'"
        for wrapper in ("timeout 30", "env FOO=1", "nohup", "nice -n 5", "command", "sudo"):
            with self.subTest(wrapper=wrapper):
                self.assertEqual(verdict(f"{wrapper} {inner}"), "BLOCK")


class ScriptInvocationOptionTests(unittest.TestCase):
    """`<shell> [options] <script>` — the same too-narrow grammar, one matcher over.

    `_SCRIPT_INVOKE_RE` required the path to be the token immediately after the
    interpreter, so every option before it hid the script. All four forms below
    execute the script under bash / sh / zsh / dash.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="t1149-script-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.naked = os.path.join(self.tmp, "naked_script")
        Path(self.naked).write_text(NAKED_COMMIT + "\n", encoding="utf-8")
        self.innocent = os.path.join(self.tmp, "innocent_script")
        Path(self.innocent).write_text("echo hello\n", encoding="utf-8")

    def test_options_before_the_script_path_still_block(self):
        for pre in ("", "-x", "-l", "+x", "--", "-o pipefail", "-lx"):
            with self.subTest(options=pre or "(none)"):
                command = f"bash {pre} {self.naked}".replace("  ", " ")
                self.assertEqual(verdict(command), "BLOCK", command)

    def test_wrapped_script_invocation_blocks(self):
        self.assertEqual(verdict(f"timeout 9 bash -x {self.naked}"), "BLOCK")

    def test_innocent_script_is_still_allowed(self):
        for pre in ("", "-x", "-l"):
            with self.subTest(options=pre or "(none)"):
                self.assertEqual(verdict(f"bash {pre} {self.innocent}".replace("  ", " ")), "allow")


class MustStayAllowedTests(unittest.TestCase):
    """Ordinary work must not become collateral. Widening a gate has two failure
    directions and this is the one a bypass-only corpus never asks about."""

    ALLOWED = {
        "plain ls": "ls -la",
        "innocent -lc": "bash -lc 'echo hello'",
        "git status via -lc": "bash -lc 'git status'",
        "npm through a shell": "bash -lc 'npm run build'",
        "docker exec": "docker exec x sh -lc 'ls /'",
        "interpreter with no arguments": "bash -l",
        "prose in a gh body": 'gh issue comment 5 --body "never run bash -lc to commit"',
        "ripgrep for the phrase": "rg -n 'bash -lc' .claude/hooks",
        "commit-shaped path": "git log --oneline -- src/commit/mod.rs",
        "unrelated -c flag": "npm run build -- -c prod",
        "data heredoc naming the shape": (
            "cat > /tmp/notes.md <<'EOF'\nbash -lc 'git commit -m x' is forbidden\nEOF"
        ),
    }

    def test_ordinary_commands_are_untouched(self):
        for label, command in self.ALLOWED.items():
            with self.subTest(case=label):
                self.assertEqual(verdict(command), "allow", command)


class PreviouslyBlockedStillBlockTests(unittest.TestCase):
    """Every shape the gate caught before #1149 must still be caught.

    The only way to "fix" a fail-open wrongly is to stop blocking something real
    while widening something else.
    """

    BLOCKED = {
        "bare -c": f"bash -c '{NAKED_COMMIT}'",
        "printf piped to a shell": f"printf '{NAKED_COMMIT}' | bash",
        "echo piped to a shell": f"echo '{NAKED_COMMIT}' | sh",
        "process substitution": f"bash <(echo '{NAKED_COMMIT}')",
        "heredoc fed to a shell": f"bash <<'EOF'\n{NAKED_COMMIT}\nEOF",
        "here-string": f"bash <<<'{NAKED_COMMIT}'",
        "eval": f"eval '{NAKED_COMMIT}'",
        "cat heredoc piped to a shell": f"cat <<'EOF' | bash\n{NAKED_COMMIT}\nEOF",
        "tee process substitution": f"tee >(bash) <<'EOF'\n{NAKED_COMMIT}\nEOF",
        "direct commit, no identity": NAKED_COMMIT,
        "direct commit, unknown name": (
            'git -c user.name="Nobody Here" -c user.email="x@y.z" commit -m x'
        ),
    }

    def test_prior_shapes_still_block(self):
        for label, command in self.BLOCKED.items():
            with self.subTest(case=label):
                self.assertEqual(verdict(command), "BLOCK", command)


class OptionTokenExpansionTests(unittest.TestCase):
    """Unit-level pins on the normalization that feeds the shared grammar."""

    def test_clusters_split_with_value_letters_last(self):
        self.assertEqual(_expand_shell_option_token("-lc"), ["-l", "-c"])
        self.assertEqual(_expand_shell_option_token("-cl"), ["-c", "-l"])
        self.assertEqual(_expand_shell_option_token("-abc"), ["-a", "-b", "-c"])
        # `o` is value-taking, so it must land adjacent to the word it consumes.
        self.assertEqual(_expand_shell_option_token("-oc"), ["-c", "-o"])
        self.assertEqual(_expand_shell_option_token("-lo"), ["-l", "-o"])

    def test_plus_form_options_normalize_to_minus(self):
        self.assertEqual(_expand_shell_option_token("+x"), ["-x"])
        self.assertEqual(_expand_shell_option_token("+o"), ["-o"])

    def test_non_clusters_pass_through(self):
        for tok in ("--login", "--rcfile=F", "--", "-c", "-2", "-o=x", "script.sh"):
            with self.subTest(token=tok):
                self.assertEqual(_expand_shell_option_token(tok), [tok])


class InvocationParsingTests(unittest.TestCase):
    """Unit-level pins on `parse_interpreter_invocation` / the iterator."""

    def test_operands_and_words_for_a_clustered_value_option(self):
        inv = parse_interpreter_invocation(["bash", "-oc", "pipefail", NAKED_COMMIT])
        assert inv is not None
        self.assertEqual(inv.name, "bash")
        self.assertTrue(inv.has_command_string)
        self.assertEqual(inv.operands, (NAKED_COMMIT,))
        # `words` keeps every token but `--`, so the command string is in it no
        # matter how the cluster shifted the payload index.
        self.assertEqual(inv.words, ("-c", "-o", "pipefail", NAKED_COMMIT))

    def test_words_drops_only_the_double_dash_sentinel(self):
        """Pins a DESIGN DECISION, not a correctness result — read before editing.

        A bounded alternative (scan only the window between `-c` and the end of
        the option run) is equally correct on true positives: both score zero
        holes against the shell-truth oracle, and both produce byte-identical
        block sets over ~75k real recorded commands. The superset was chosen on
        DURABILITY, not on detection power (main#1193 merge-gate review):

          - the bounded window needs `rest.index("-c")`, which is only correct
            while cluster expansion is right for every shell — re-importing the
            per-shell option knowledge this module exists to delete;
          - its failure mode is a silent index error, i.e. fail-OPEN. The
            superset's failure mode is an over-block, which is noisy.

        So a future reader who finds `words` "too broad" is looking at a
        deliberate trade, not an oversight. Narrowing it to non-flag tokens is
        not a style change — it re-opens `zsh -abc '-x; git commit …'`.
        """
        inv = parse_interpreter_invocation(["bash", "-c", "--", "-x; " + NAKED_COMMIT])
        assert inv is not None
        self.assertNotIn("--", inv.words)
        self.assertEqual(inv.words, ("-c", "-x; " + NAKED_COMMIT))

    def test_double_dash_moves_c_out_of_the_option_run(self):
        inv = parse_interpreter_invocation(["bash", "--", "-c", NAKED_COMMIT])
        assert inv is not None
        self.assertFalse(inv.has_command_string)
        self.assertEqual(inv.operands, ("-c", NAKED_COMMIT))

    def test_wrapper_is_stripped_and_path_reduced_to_basename(self):
        inv = parse_interpreter_invocation(["timeout", "30", "/bin/zsh", "-cl", NAKED_COMMIT])
        assert inv is not None
        self.assertEqual(inv.name, "zsh")
        self.assertTrue(inv.has_command_string)

    def test_iterator_finds_one_invocation_per_segment(self):
        found = iter_interpreter_invocations("echo hi | bash -lc 'true' && sh -c 'false'")
        self.assertEqual([i.name for i in found], ["bash", "sh"])

    def test_iterator_skips_commands_with_no_interpreter(self):
        self.assertEqual(iter_interpreter_invocations("git status --porcelain"), [])

    def test_iterator_recovers_from_an_unbalanced_quote(self):
        found = iter_interpreter_invocations('bash -lc "true" && echo "unclosed')
        self.assertEqual([i.name for i in found], ["bash"])


def _which(name: str) -> str | None:
    return shutil.which(name)


class ShellTruthTests(unittest.TestCase):
    """Cross-check the gate against what a REAL shell does.

    For each form we hand a live shell a payload that writes a marker file whose
    name is generated at run time, then ask the filesystem whether it ran. The
    contract asserted is the security-relevant direction:

        the shell EXECUTED the payload  =>  the hook MUST block

    The converse is deliberately not asserted. Blocking a form the shell would
    not have run (`bash -n -c …` parses without executing) is the conservative
    error and this gate is allowed to make it.
    """

    shells: list[tuple[str, str]] = []
    work: str = ""

    FORMS = [
        ["-c"],
        ["-lc"],
        ["-cl"],
        ["-xc"],
        ["-ec"],
        ["-vc"],
        ["-abc"],
        ["-cabm"],
        ["-l", "-c"],
        ["-x", "-c"],
        ["+x", "-c"],
        ["--login", "-c"],
        ["-o", "pipefail", "-c"],
        ["-oc", "pipefail"],
        # zsh-only: the payload lands in an option-value slot, not an operand.
        ["-cO"],
        ["-Oc"],
        ["-cOl"],
        ["--"],
        ["--", "-c"],
        ["-l"],
        # `--` in the OPTION run (not before it) — puts the command string in
        # the operand region, where a `-`-leading payload used to be dropped.
        ["-c", "--"],
        ["-lc", "--"],
        ["-cl", "--"],
        ["-abc", "--"],
        ["-o", "pipefail", "-c", "--"],
        ["+2", "-c"],
    ]

    # PAYLOAD SHAPE is a first-class dimension, not a constant. Every other
    # class in this file varies the invocation and holds the command string's
    # surface fixed — which is exactly how the `-`-leading payload fail-open
    # survived the first head of #1193. The option-run walker's answer depends
    # on what the payload LOOKS like, so that has to be varied against the same
    # shell-truth contract as everything else.
    PAYLOAD_PREFIXES = ["", "-x; ", "--foo; ", "-", "--", "-x && ", "+x; ", "-- "]

    @classmethod
    def setUpClass(cls):
        found = [(n, _which(n)) for n in ("bash", "sh", "zsh", "dash")]
        cls.shells = [(n, p) for n, p in found if p is not None]
        if not cls.shells:
            raise unittest.SkipTest("no POSIX shell available to establish shell truth")
        cls.work = tempfile.mkdtemp(prefix="t1149-truth-")

    @classmethod
    def tearDownClass(cls):
        if cls.work:
            shutil.rmtree(cls.work, ignore_errors=True)

    def _executes(self, shell_path: str, pre: list[str], prefix: str = "") -> bool:
        """True iff the shell actually ran the payload as a command string."""
        marker = os.path.join(self.work, "m_" + secrets.token_hex(8))
        payload = prefix + "printf %s x > " + marker
        try:
            subprocess.run(
                [shell_path, *pre, payload],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=15,
                cwd=self.work,
                env={"PATH": os.environ.get("PATH", ""), "HOME": self.work},
            )
        except (subprocess.TimeoutExpired, OSError):
            return False
        return os.path.exists(marker)

    def test_hook_blocks_every_form_a_real_shell_executes(self):
        checked = 0
        for name, path in self.shells:
            for pre in self.FORMS:
                for prefix in self.PAYLOAD_PREFIXES:
                    if not self._executes(path, pre, prefix):
                        continue
                    checked += 1
                    body = prefix + NAKED_COMMIT
                    command = "{} {} '{}'".format(name, " ".join(pre), body)
                    with self.subTest(shell=name, form=" ".join(pre), payload=prefix + "..."):
                        self.assertEqual(
                            verdict(command),
                            "BLOCK",
                            f"{name} really executes this form but the gate allowed it: {command}",
                        )
        # Guard against the oracle silently degrading to "nothing executes",
        # which would make every assertion above vacuous.
        self.assertGreater(checked, 40, "shell-truth oracle found almost nothing executable")

    def test_oracle_distinguishes_executed_from_not_executed(self):
        """The oracle must be able to answer NO, or it proves nothing."""
        _name, path = self.shells[0]
        self.assertFalse(self._executes(path, ["--"]), "`--` must not run the payload")
        self.assertTrue(self._executes(path, ["-c"]), "bare `-c` must run the payload")

    def test_oracle_is_sensitive_to_the_payload_dimension(self):
        """A dash-leading payload must change at least one form's answer.

        If it never did, adding `PAYLOAD_PREFIXES` would be decoration rather
        than a dimension, and the class would be claiming coverage it lacks.
        """
        _name, path = self.shells[0]
        self.assertTrue(self._executes(path, ["-c", "--"], "-x; "))
        self.assertFalse(self._executes(path, ["-c"], "-x; "))


if __name__ == "__main__":
    unittest.main()
