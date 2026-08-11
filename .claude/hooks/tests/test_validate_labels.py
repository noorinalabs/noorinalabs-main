#!/usr/bin/env python3
"""Tests for validate_labels hook.

Covers the W8 hook-authorship-spec requirement: NEGATIVE MATCH coverage for
the two W9 bugs (issue #113) plus regression coverage for positive cases.

Run: python3 -m pytest .claude/hooks/tests/test_validate_labels.py -v
Or:  python3 .claude/hooks/tests/test_validate_labels.py
"""

from __future__ import annotations

import shlex
import unittest
from pathlib import Path
from unittest import mock

import _test_helpers  # noqa: E402,F401
import validate_labels as hook  # noqa: E402


class ExtractLabelsTests(unittest.TestCase):
    """Positive regression tests — labels appearing on the actual flag."""

    def test_long_flag_quoted(self):
        self.assertEqual(
            hook.extract_labels('gh issue create --label "bug"'),
            ["bug"],
        )

    def test_long_flag_unquoted(self):
        self.assertEqual(
            hook.extract_labels("gh issue create --label bug"),
            ["bug"],
        )

    def test_short_flag(self):
        self.assertEqual(
            hook.extract_labels('gh issue create -l "tech-debt"'),
            ["tech-debt"],
        )

    def test_equals_form(self):
        self.assertEqual(
            hook.extract_labels("gh issue create --label=bug"),
            ["bug"],
        )

    def test_short_equals_form(self):
        """Short-flag equals form `-l=value` — #304 fix (silent-skip pre-fix)."""
        self.assertEqual(
            hook.extract_labels("gh issue create -l=tech-debt"),
            ["tech-debt"],
        )

    def test_long_equals_comma_form(self):
        """`--label=a,b,c` — equals + comma-split combined (#304 coverage)."""
        self.assertEqual(
            hook.extract_labels("gh issue create --label=bug,tech-debt,p3-wave-9"),
            ["bug", "tech-debt", "p3-wave-9"],
        )

    def test_short_equals_comma_form(self):
        """`-l=a,b,c` — short equals + comma-split combined (#304 coverage)."""
        self.assertEqual(
            hook.extract_labels("gh issue create -l=bug,tech-debt"),
            ["bug", "tech-debt"],
        )

    def test_mixed_long_equals_and_short_equals(self):
        """`--label=a -l=b` — both equals-forms in one command (#304 coverage)."""
        self.assertEqual(
            hook.extract_labels("gh issue create --label=bug -l=tech-debt"),
            ["bug", "tech-debt"],
        )

    def test_multiple_flags(self):
        self.assertEqual(
            hook.extract_labels('gh issue create --label "bug" --label "tech-debt"'),
            ["bug", "tech-debt"],
        )

    def test_comma_separated_in_one_flag(self):
        self.assertEqual(
            hook.extract_labels('gh issue create --label "bug,tech-debt,p2-wave-9"'),
            ["bug", "tech-debt", "p2-wave-9"],
        )

    def test_mixed_short_and_long(self):
        self.assertEqual(
            hook.extract_labels('gh issue create -l bug --label "tech-debt"'),
            ["bug", "tech-debt"],
        )


class NegativeMatchLabelsTests(unittest.TestCase):
    """NEGATIVE-MATCH coverage for Bug 2 (#113) — label extraction false positives.

    Each test documents which negative-space case it guards against. The hook
    MUST NOT extract labels from text that appears inside the value of
    another flag (e.g. --body).
    """

    def test_body_containing_example_label_flag_is_ignored(self):
        """Body documents an example gh command — its --label must NOT leak."""
        cmd = (
            'gh issue create --title "real title" '
            '--body "Example: gh issue create --label fake-label-xyz" '
            "--label real-label"
        )
        labels = hook.extract_labels(cmd)
        self.assertIn("real-label", labels)
        self.assertNotIn("fake-label-xyz", labels)

    def test_body_with_code_block_label_flag_is_ignored(self):
        """Body includes a fenced code block with --label; still must not leak."""
        cmd = (
            "gh issue create --body '```bash\\ngh issue create --label ghost\\n```' --label actual"
        )
        labels = hook.extract_labels(cmd)
        self.assertIn("actual", labels)
        self.assertNotIn("ghost", labels)

    def test_body_with_short_flag_variant_is_ignored(self):
        cmd = 'gh issue create --body "see: gh issue create -l phantom" -l real'
        labels = hook.extract_labels(cmd)
        self.assertIn("real", labels)
        self.assertNotIn("phantom", labels)

    def test_title_with_label_flag_text_is_ignored(self):
        """Prose in --title that contains `--label X` must not be extracted."""
        cmd = 'gh issue create --title "use --label flag correctly" --label documentation'
        labels = hook.extract_labels(cmd)
        self.assertEqual(labels, ["documentation"])

    def test_no_label_flag_returns_empty(self):
        self.assertEqual(
            hook.extract_labels('gh issue create --title "x" --body "y"'),
            [],
        )

    def test_label_flag_on_a_non_gh_command_is_not_a_label(self):
        """`echo … --label world` contributes nothing (contract change, main#1351).

        This assertion is inverted from its original form, deliberately. It
        used to read `["world"]` with the comment "extract_labels is pure; the
        gate in check() filters" — i.e. extraction matched a `--label` flag
        ANYWHERE in the command string and relied on a separate `check()`
        guard to decide whether the command was even a `gh issue create`.

        That split is the defect. The `check()` guard is whole-command
        (`is_gh_subcommand` over the raw token stream), so it says yes when the
        words `gh issue create` appear ANYWHERE — including a heredoc body —
        and then extraction, also whole-command, harvests `-l`-shaped tokens
        from wherever they happen to sit. Two of the three wave-29 false
        blocks are exactly that composition: a `bash -lc` in an issue BODY
        became a label named `c` on a command whose real gh invocation was
        three lines further down.

        Extraction is now scoped to the `gh issue create` SEGMENT, so a
        `--label` outside it is not a label, and purity now means "a pure
        function of the command" rather than "unaware of which command it is".
        """
        self.assertEqual(hook.extract_labels("echo hello --label world"), [])

    def test_label_flag_on_a_sibling_command_in_the_same_string(self):
        """A real `--label` on a DIFFERENT gh subcommand must not leak in."""
        cmd = "gh issue edit 7 --add-label stale && gh issue create --label bug"
        self.assertEqual(hook.extract_labels(cmd), ["bug"])


class TokenizeFailureFallbackTests(unittest.TestCase):
    """#661 — when shlex tokenization FAILS, label extraction must NOT scoop
    label-shaped tokens out of `--body`/`--title` prose.

    The prior fallback ran a `(?:--label|-l)`-anchored regex over the WHOLE
    command on shlex failure, which over-matched documented label patterns in
    the issue body and false-blocked a legitimate `gh issue create`. The fix
    fails OPEN (returns []) instead of over-matching.
    """

    def test_exact_issue_661_reproducer_does_not_leak_body_label(self):
        """The live P4W7 repro: body documents ``--label `p{N}-wave-{M}` `` and
        contains an apostrophe ("gh's") that breaks shlex. The real flag is
        `--label bug`; the documented pattern MUST NOT be extracted."""
        body = "This hook validates --label `p{N}-wave-{M}` tokens. Note gh's resolution."
        cmd = f"gh issue create --repo noorinalabs/noorinalabs-main --label bug --body '{body}'"
        from _shell_parse import tokenize

        self.assertIsNone(tokenize(cmd), "precondition: this command must break shlex")
        labels = hook.extract_labels(cmd)
        self.assertNotIn("`p{N}-wave-{M}`", labels)
        self.assertNotIn("p{N}-wave-{M}", labels)

    def test_tokenize_failure_returns_empty_not_body_tokens(self):
        """A `-l`/`--label` substring inside a quote-broken body must not leak."""
        body = "see -l phantom and --label ghost; can't parse this"
        cmd = f"gh issue create --label real --body '{body}'"
        from _shell_parse import tokenize

        self.assertIsNone(tokenize(cmd))
        self.assertEqual(hook.extract_labels(cmd), [])

    def test_check_does_not_block_on_malformed_quote_body(self):
        """End-to-end: the #661 reproducer must ALLOW (no spurious block)."""
        body = "Documents --label `p{N}-wave-{M}`. Mentions gh's ambient repo."
        cmd = f"gh issue create --repo noorinalabs/noorinalabs-main --label bug --body '{body}'"
        with mock.patch.object(hook, "get_existing_labels", return_value={"bug"}):
            result = hook.check({"tool_name": "Bash", "tool_input": {"command": cmd}})
        self.assertIsNone(result, f"unexpected block on malformed-quote body: {result}")


class ExtractRepoTests(unittest.TestCase):
    """Coverage for Bug 1 (#113) — --repo flag pass-through."""

    def test_long_flag(self):
        self.assertEqual(
            hook.extract_repo(
                "gh issue create --repo noorinalabs/noorinalabs-isnad-graph --label bug"
            ),
            "noorinalabs/noorinalabs-isnad-graph",
        )

    def test_short_flag(self):
        self.assertEqual(
            hook.extract_repo("gh issue create -R owner/repo --label bug"),
            "owner/repo",
        )

    def test_equals_form(self):
        self.assertEqual(
            hook.extract_repo("gh issue create --repo=owner/repo --label bug"),
            "owner/repo",
        )

    def test_no_repo_flag(self):
        self.assertIsNone(
            hook.extract_repo("gh issue create --label bug"),
        )

    def test_repo_token_in_body_is_ignored(self):
        """`--repo ghost/ghost` inside --body must not leak as the target repo."""
        cmd = (
            "gh issue create "
            '--body "sample: gh issue create --repo ghost/ghost" '
            "--repo real/real --label bug"
        )
        self.assertEqual(hook.extract_repo(cmd), "real/real")


class GateMatchingTests(unittest.TestCase):
    """The `check()` gate fires ONLY on gh issue create, not siblings."""

    _input = staticmethod(_test_helpers.bash_input)

    def test_gh_issue_list_is_ignored(self):
        self.assertIsNone(hook.check(self._input("gh issue list --label bug")))

    def test_gh_issue_view_is_ignored(self):
        self.assertIsNone(hook.check(self._input("gh issue view 1 --label bug")))

    def test_gh_pr_create_is_ignored(self):
        self.assertIsNone(hook.check(self._input("gh pr create --label bug")))

    def test_non_bash_tool_is_ignored(self):
        self.assertIsNone(
            hook.check(
                {
                    "tool_name": "Edit",
                    "tool_input": {"command": "gh issue create --label bug"},
                }
            )
        )

    def test_command_without_label_flag_is_allowed(self):
        self.assertIsNone(hook.check(self._input('gh issue create --title "x" --body "y"')))


class CheckEndToEndTests(unittest.TestCase):
    """End-to-end `check()` with get_existing_labels mocked.

    These verify that Bug 1 is fixed: when the user passes --repo OWNER/REPO,
    we forward it to get_existing_labels() so label validation hits the
    correct repo.
    """

    _input = staticmethod(_test_helpers.bash_input)

    def test_repo_is_forwarded_to_get_existing_labels(self):
        """Bug 1: --repo must be passed through to the label fetch."""
        with mock.patch.object(
            hook, "get_existing_labels", return_value={"frontend", "bug"}
        ) as mocked:
            result = hook.check(
                self._input(
                    "gh issue create --repo noorinalabs/noorinalabs-isnad-graph "
                    '--title "t" --body "b" --label frontend'
                )
            )
        self.assertIsNone(result)
        mocked.assert_called_once_with(repo="noorinalabs/noorinalabs-isnad-graph")

    def test_missing_label_blocks(self):
        with mock.patch.object(hook, "get_existing_labels", return_value={"bug"}):
            result = hook.check(self._input("gh issue create --label does-not-exist"))
        self.assertIsNotNone(result)
        self.assertEqual(result["decision"], "block")
        self.assertIn("does-not-exist", result["reason"])

    def test_body_containing_fake_label_does_not_block(self):
        """Bug 2: a body-quoted --label must NOT cause a spurious block."""
        with mock.patch.object(hook, "get_existing_labels", return_value={"bug"}):
            result = hook.check(
                self._input(
                    'gh issue create --body "example: gh issue create --label fake" --label bug'
                )
            )
        self.assertIsNone(result, f"unexpected block: {result}")

    def test_body_plus_wrong_repo_would_block_without_bug1_fix(self):
        """Combined scenario from issue #113: body-leak + cross-repo label.

        The user creates an issue in repo A with a real label that exists in
        repo A. Body documents an example command referencing repo B and a
        non-existent label. Neither the body's --repo nor --label may leak.
        """

        def fake_get_existing_labels(repo=None):
            if repo == "noorinalabs/noorinalabs-isnad-graph":
                return {"frontend"}
            return {"other-label"}  # would be returned if cwd-resolved

        with mock.patch.object(hook, "get_existing_labels", side_effect=fake_get_existing_labels):
            result = hook.check(
                self._input(
                    "gh issue create --repo noorinalabs/noorinalabs-isnad-graph "
                    '--body "example: gh issue create --repo ghost/ghost --label nope" '
                    "--label frontend"
                )
            )
        self.assertIsNone(result, f"unexpected block: {result}")

    def test_no_labels_to_validate_is_allowed(self):
        with mock.patch.object(hook, "get_existing_labels", return_value={"bug"}) as mocked:
            result = hook.check(self._input('gh issue create --title "t" --body "b"'))
        self.assertIsNone(result)
        mocked.assert_not_called()

    def test_label_fetch_failure_warns_not_blocks(self):
        with mock.patch.object(hook, "get_existing_labels", return_value=set()):
            result = hook.check(self._input("gh issue create --label any"))
        self.assertIsNotNone(result)
        self.assertEqual(result["decision"], "allow")


# ---------------------------------------------------------------------------
# Wave-29 live false-positive corpus (main#1351)
# ---------------------------------------------------------------------------
#
# These are not invented shapes. They are the THREE `validate_labels` blocks
# recorded in `.claude/annunaki/errors.jsonl` during wave 29 — the hook's
# entire block population for the wave. All three were false positives: every
# label the commands actually passed (`bug`, `security`, `tech-debt`,
# `process`, `meta-issue`, `phase-10`) existed in the repo at the time
# (verified 2026-08-10 via `gh label list`). Precision was 0/3.
#
# The first one blocked the filing of #1150 — the umbrella issue about hooks
# hand-rolling command parsing, which names THIS hook as un-audited. A gate at
# zero precision that also blocks the report of its own defect class is the
# cleanest possible statement of the problem, so it is pinned here rather than
# paraphrased.
#
# PROVENANCE, precisely. `annunaki_log` truncates the `command` it records at
# 500 characters. The leading bytes of each fixture below are VERBATIM from
# that record. Where the record is cut off, the continuation is reconstructed
# from two independent recorded sources, not from imagination:
#
#   - the SUCCESSFUL RETRY of the same filing, captured in
#     `.claude/annunaki/traces.jsonl` roughly a minute after each block, which
#     supplies the exact `gh issue create` flag tail and label set;
#   - the recorded BLOCK MESSAGE itself, which pins how many `-lc` occurrences
#     the elided heredoc body contained and in what shape — `c, c, c` means
#     three bare `bash -lc`; `c, c, c\`` means the third was inside a markdown
#     code span, so shlex handed the tokenizer `-lc\``.
#
# Each fixture is asserted to reproduce its recorded block message under the
# PRE-FIX implementation (that check is what makes them regression tests
# rather than decoration; see the PR body for the captured pre-fix output) and
# to be allowed under the current one.

# The three commands live as VERBATIM BYTES in `tests/fixtures/`, matching the
# `real_*` harvested-fixture convention this suite already uses. They are files
# rather than string literals for two reasons: a recorded command must not be
# reflowed to satisfy a line-length linter, and a reader comparing a fixture
# against the log is comparing bytes, not an escaped Python literal.
#
#   real_label_block_w29a_dollar_paren.txt        recorded block: meta-issue)
#   real_label_block_w29b_heredoc_lc_backtick.txt recorded block: c, c, c`
#   real_label_block_w29c_heredoc_lc.txt          recorded block: c, c, c

_FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _wave29(name: str) -> str:
    """Load a harvested command, refusing to run against a dead instrument."""
    body = (_FIXTURES / f"real_label_block_{name}.txt").read_text()
    if "gh issue create" not in body:
        raise AssertionError(f"fixture {name} lost its gh invocation — the instrument is dead")
    return body


# Capturing the new issue's URL into a variable is the ordinary "create it,
# then add it to the board" idiom, so W29-A fires on a routine shape.
W29_A_DOLLAR_PAREN = _wave29("w29a_dollar_paren")

# W29-B's heredoc body is a write-up ABOUT shell parsing, so it quotes
# `bash -lc` — twice bare and once inside a code span, which is why its third
# minted label was `` c` ``. The gate is hardest on the work that hardens the
# gates.
W29_B_HEREDOC_DASH_LC_BACKTICK = _wave29("w29b_heredoc_lc_backtick")

W29_C_HEREDOC_DASH_LC = _wave29("w29c_heredoc_lc")

# W30-A — 2026-08-11T03:06:00Z, recorded block: `definitely-not-a-real-label`.
# The only fixture in this corpus with ZERO reconstruction: the log record is
# 242 bytes, below the 500-byte truncation point, so the file is the complete
# command exactly as issued. It was produced by Nino Kavtaradze's merge-gate
# review OF THIS PR — a reduced repro he built while verifying the fix, whose
# heredoc body quotes a `--label definitely-not-a-real-label` example. The
# installed PRE-FIX hook blocked him from filing it. Its real labels
# (`tech-debt`, `bug`) both exist, so this is a fourth false positive, in the
# wild, in wave 30, on the reviewer, while reviewing the fix for it.
W30_A_REVIEW_HEREDOC = _wave29("w30a_review_heredoc")

# Every label the four commands really passed. All existed at block time.
RECORDED_REAL_LABELS = {"bug", "security", "tech-debt", "process", "meta-issue", "phase-10"}

# Retained under the old name: `WAVE29_REAL_LABELS` is referenced widely below
# and the rename is cosmetic, so both point at one object rather than drifting.
WAVE29_REAL_LABELS = RECORDED_REAL_LABELS


class RecordedFalsePositiveCorpusTests(unittest.TestCase):
    """Every `validate_labels` block on record, across two waves. All false.

    Four commands, all harvested from `.claude/annunaki/errors.jsonl`:

      - **Wave 29** — W29-A/B/C, the hook's ENTIRE block population for that
        wave. Precision before 0/3, after 3/3.
      - **Wave 30** — W30-A, produced during the merge-gate review of the very
        PR that fixes this, when the pre-fix hook blocked the reviewer's own
        filing. Not a wave-29 figure, which is why this class is no longer
        named for wave 29 (main#1394 review round 3).

    Combined recorded population: 4 blocks, 0 correct, before -> 0 blocks
    after. The true-positive guard rails live in `PrecisionRetainedTests` — a
    gate that stops false-blocking by stopping blocking has not been fixed, it
    has been removed.
    """

    _input = staticmethod(_test_helpers.bash_input)

    def _assert_allowed(self, command):
        with mock.patch.object(hook, "get_existing_labels", return_value=WAVE29_REAL_LABELS):
            result = hook.check(self._input(command))
        self.assertIsNone(result, f"unexpected block: {result}")

    def test_w29a_dollar_paren_extracts_meta_issue_without_the_paren(self):
        """Recorded block demanded a label named `meta-issue)`."""
        labels = hook.extract_labels(W29_A_DOLLAR_PAREN)
        self.assertEqual(labels, ["tech-debt", "process", "meta-issue"])
        self.assertNotIn("meta-issue)", labels)

    def test_w29a_does_not_block_the_filing_of_1150(self):
        self._assert_allowed(W29_A_DOLLAR_PAREN)

    def test_w29b_heredoc_dash_lc_contributes_no_labels(self):
        """Recorded block demanded labels `c`, `c`, `c\\``."""
        labels = hook.extract_labels(W29_B_HEREDOC_DASH_LC_BACKTICK)
        self.assertEqual(labels, ["bug", "security", "tech-debt"])
        self.assertNotIn("c", labels)
        self.assertNotIn("c`", labels)

    def test_w29b_does_not_block(self):
        self._assert_allowed(W29_B_HEREDOC_DASH_LC_BACKTICK)

    def test_w29c_heredoc_dash_lc_contributes_no_labels(self):
        """Recorded block demanded labels `c`, `c`, `c`."""
        labels = hook.extract_labels(W29_C_HEREDOC_DASH_LC)
        self.assertEqual(labels, ["tech-debt", "process", "phase-10"])
        self.assertNotIn("c", labels)

    def test_w29c_does_not_block(self):
        self._assert_allowed(W29_C_HEREDOC_DASH_LC)

    def test_w30a_review_heredoc_extracts_only_the_real_labels(self):
        """The wave-30 instance the review itself produced.

        Its body carries BOTH defect families at once — a `--label` example in
        heredoc prose AND a mid-argument `$( … )` — so it also pins that the
        two fixes compose rather than merely coexist.
        """
        self.assertEqual(hook.extract_labels(W30_A_REVIEW_HEREDOC), ["tech-debt", "bug"])

    def test_w30a_does_not_block(self):
        with mock.patch.object(hook, "get_existing_labels", return_value=WAVE29_REAL_LABELS):
            result = hook.check(self._input(W30_A_REVIEW_HEREDOC))
        self.assertIsNone(result, f"unexpected block: {result}")

    def test_w30a_substitution_inside_the_data_body_is_not_counted_as_lost(self):
        """The `$( … )` sits in the heredoc BODY, not in the real invocation.

        Its argument-swallowing does not apply, so the partial-coverage note
        must stay quiet — otherwise every issue body that quotes a command
        substitution would carry a spurious "could not check N flags" warning.
        """
        self.assertEqual(hook._extract_labels(W30_A_REVIEW_HEREDOC).unvalidated, 0)

    def test_no_extracted_label_carries_a_shell_metacharacter(self):
        """Acceptance criterion 4, across the whole corpus.

        A label token holding a shell metacharacter can never reach the
        `gh label create "<token>"` remediation line — the message that, in
        W29-A, would have had the user mint a junk label named `meta-issue)`.
        """
        for name, command in (
            ("W29-A", W29_A_DOLLAR_PAREN),
            ("W29-B", W29_B_HEREDOC_DASH_LC_BACKTICK),
            ("W29-C", W29_C_HEREDOC_DASH_LC),
            ("W30-A", W30_A_REVIEW_HEREDOC),
        ):
            with self.subTest(case=name):
                for label in hook.extract_labels(command):
                    self.assertFalse(
                        hook._SHELL_METACHARS.intersection(label),
                        f"{name}: metacharacter survived into label {label!r}",
                    )


class DataHeredocBodyIsNotAnOptionListTests(unittest.TestCase):
    """#1174's code-vs-data class, arriving in this hook (main#1351 defect B).

    A heredoc body fed to `cat`/`tee` is DATA. It routinely contains prose
    about gh commands — that is what a tech-debt write-up IS — and none of it
    is an option list for the command that follows.
    """

    _input = staticmethod(_test_helpers.bash_input)

    def test_documented_gh_issue_create_in_a_data_body_does_not_leak(self):
        cmd = (
            "cat > /tmp/note.md <<'EOF'\n"
            "Reproduce with:\n"
            "\n"
            "    gh issue create --label ghost-label --title x\n"
            "EOF\n"
            "gh issue create --repo o/r --body-file /tmp/note.md --label bug"
        )
        self.assertEqual(hook.extract_labels(cmd), ["bug"])

    def test_documented_gh_issue_create_in_a_data_body_does_not_block(self):
        cmd = (
            "cat > /tmp/note.md <<'EOF'\n"
            "    gh issue create --label ghost-label\n"
            "EOF\n"
            "gh issue create --repo o/r --body-file /tmp/note.md --label bug"
        )
        with mock.patch.object(hook, "get_existing_labels", return_value={"bug"}):
            result = hook.check(self._input(cmd))
        self.assertIsNone(result, f"unexpected block: {result}")

    def test_unterminated_heredoc_validates_nothing(self):
        """`strip_data_heredocs` keeps an unterminated body; we must not scan it.

        Its own callers are bypass matchers, for which retaining the body is
        the safe direction. For a false-positive-sensitive gate it is the
        unsafe one — the retained prose becomes option tokens, which is
        defect B again. The command cannot run as written, so there is
        nothing to pre-flight.
        """
        cmd = (
            "cat > /tmp/x <<'EOF'\n"
            "gh issue create --label ghost\n"
            "gh issue create --repo o/r --label bug"
        )
        self.assertEqual(hook.extract_labels(cmd), [])

    def test_unterminated_heredoc_skip_is_not_silent(self):
        """MF2: a fail-open added by the fix must announce itself like the rest."""
        cmd = "cat > /tmp/x <<'EOF'\ngh issue create --repo o/r --label bug"
        with mock.patch.object(hook, "get_existing_labels", return_value={"bug"}):
            result = hook.check(self._input(cmd))
        self.assertIsNotNone(result, "silent fail-open")
        self.assertEqual(result["decision"], "allow")
        self.assertIn("unterminated heredoc", result["systemMessage"])

    def test_an_interpreter_heredoc_body_is_still_scanned(self):
        """`bash <<'EOF'` is CODE — its `gh issue create` genuinely runs.

        The complement of the test above, and the reason this uses
        `strip_DATA_heredocs` rather than `strip_heredocs`: dropping every
        body would blind the gate to a real invocation.
        """
        cmd = "bash <<'EOF'\ngh issue create --repo o/r --label really-not-a-label\nEOF"
        self.assertEqual(hook.extract_labels(cmd), ["really-not-a-label"])


# The characters `validate_labels._SHELL_METACHARS` is expected to hold, written
# out INDEPENDENTLY of the implementation. A test that derives its expectation
# from the code under test cannot detect a change to that code — see the history
# in `test_every_character_in_the_metachar_set_is_load_bearing`.
EXPECTED_METACHARS = ("(", ")", "`", "$", ";", "|", "&", "<", ">", "\n", "\r", "\\")


class ShellMetacharGuardTests(unittest.TestCase):
    """Layer 3: a metacharacter in a label means WE mis-parsed, not that the
    label is missing. Skip validation, and say so — a gate that quietly stops
    gating is this hook's own history."""

    _input = staticmethod(_test_helpers.bash_input)

    def test_metachar_label_allows_with_a_visible_note(self):
        cmd = "gh issue create --repo o/r --label 'meta-issue)'"
        with mock.patch.object(hook, "get_existing_labels", return_value={"meta-issue"}):
            result = hook.check(self._input(cmd))
        self.assertIsNotNone(result)
        self.assertEqual(result["decision"], "allow")
        self.assertIn("validated NO labels", result["systemMessage"])
        self.assertIn("meta-issue)", result["systemMessage"])

    def test_metachar_label_never_reaches_a_create_remediation(self):
        cmd = "gh issue create --repo o/r --label 'meta-issue)'"
        with mock.patch.object(hook, "get_existing_labels", return_value={"meta-issue"}):
            result = hook.check(self._input(cmd))
        self.assertNotIn("gh label create", result.get("systemMessage", ""))
        self.assertNotIn("reason", result)

    def test_guard_empties_the_whole_batch_not_just_the_bad_token(self):
        """One garbage token discredits the parse, not merely itself."""
        self.assertEqual(hook.extract_labels("gh issue create --label bug --label 'x)'"), [])

    def test_metachar_set_membership_matches_the_pinned_literal(self):
        """The set must equal `EXPECTED_METACHARS`, member for member.

        This assertion is what makes the loop below mean anything, and it is
        the whole point of keeping the expectation in a LITERAL (main#1394
        review round 3). Removing a character from `_SHELL_METACHARS` fails
        here; adding one also fails here, so growing the set is a deliberate
        act with a matching test edit rather than a silent widening.
        """
        self.assertEqual(hook._SHELL_METACHARS, frozenset(EXPECTED_METACHARS))

    def test_every_character_in_the_metachar_set_is_load_bearing(self):
        """Each member of `EXPECTED_METACHARS` must be pinned, not just `)`.

        HISTORY — this test was itself the defect twice (main#1394).

        Round 2 found the guard's coverage claim half-unpinned (#1411): every
        `ShellMetacharGuardTests` case used a `)`-bearing token, so dropping
        any other member was caught by nothing. The fix I wrote then iterated
        `sorted(hook._SHELL_METACHARS)` — **the very set it claims to pin**.
        Deleting a member deleted its own test case, so the loop shrank in
        silence and the file still reported all-green. Re-measured under
        per-character mutation of the head tree, against the FULL hooks suite:
        11 of 12 members survived deletion, and only `)` was caught — by the
        wave-29 corpus, not by this test. The docstring meanwhile promised
        "each member must be pinned": a stated guarantee the mechanism
        structurally could not deliver, which is precisely the round-1 MF1
        shape reproduced inside the fix for a round-2 finding.

        The mechanism now: iterate a LITERAL tuple, and assert separately that
        the set equals it. A deleted member no longer removes its own case —
        it fails `test_metachar_set_membership_matches_the_pinned_literal`.
        Verified by re-running the same mutation: 12 of 12 caught, 0 survivors.

        Do not "simplify" this back to iterating `hook._SHELL_METACHARS`.
        """
        for char in EXPECTED_METACHARS:
            with self.subTest(char=repr(char)):
                # INTERIOR placement is required, not incidental: label values
                # are `.strip()`ed before the guard runs, so a TRAILING `\n` or
                # `\r` is gone before it can be judged. Appending the character
                # would make those two subTests fail for a reason that has
                # nothing to do with the guard.
                cmd = f"gh issue create --repo o/r --label {shlex.quote('bug' + char + 'x')}"
                self.assertEqual(
                    hook.extract_labels(cmd),
                    [],
                    f"a label token containing {char!r} was not treated as a mis-parse",
                )

    def test_a_label_with_spaces_is_not_suspect(self):
        """GitHub ships `good first issue`; spaces are legal, metachars are not."""
        self.assertEqual(
            hook.extract_labels("gh issue create --label 'good first issue'"),
            ["good first issue"],
        )


class IssueCreateSegmentsContractTests(unittest.TestCase):
    """`None` (could not parse) and `[]` (parsed, no such command) differ.

    The docstring states the distinction; nothing asserted it, so swapping the
    early-out's `return []` for `return None` was a surviving mutant
    (main#1394 review round 3). Both currently lead `check` to allow, which is
    exactly why this needs a direct test: the contract is for the NEXT reader,
    and a difference nothing observes is a difference that will be broken.
    """

    def test_no_gh_in_command_is_an_empty_list_not_none(self):
        """Parsed fine; there is simply no `gh issue create` here."""
        result = hook.issue_create_segments("echo hello --label world")
        self.assertIsNotNone(result, "a parseable command must not report a parse failure")
        self.assertEqual(result, [])

    def test_gh_present_but_not_issue_create_is_an_empty_list(self):
        self.assertEqual(hook.issue_create_segments("gh pr create --label bug"), [])

    def test_untokenizable_command_is_none(self):
        """Genuinely unparseable — the #661 fail-open, distinct from `[]`."""
        cmd = "gh issue create --label bug --body 'gh's ambient repo'"
        from _shell_parse import tokenize

        self.assertIsNone(tokenize(cmd), "precondition: this must break shlex")
        self.assertIsNone(hook.issue_create_segments(cmd))

    def test_a_real_invocation_returns_its_post_verb_tokens(self):
        self.assertEqual(
            hook.issue_create_segments("gh issue create --repo o/r --label bug"),
            [["--repo", "o/r", "--label", "bug"]],
        )


class MidArgumentSubstitutionRecallTests(unittest.TestCase):
    """Exactly how wide the one recall loss is (main#1394 review round 2).

    The reviewer's second pass established that the loss bites only on an
    UNQUOTED mid-argument substitution, and that the common double-quoted
    shape keeps full recall. That distinction was missing from the first
    write-up, which would have led a reader to over-estimate the hole — so it
    is pinned here rather than only asserted in prose.
    """

    def test_double_quoted_substitution_costs_no_recall(self):
        for cmd in (
            'gh issue create --repo o/r --body "$(cat b.md)" --label bug',
            'gh issue create --repo o/r --title "$(date)" --label bug --label tech-debt',
        ):
            with self.subTest(cmd=cmd):
                scan = hook._extract_labels(cmd)
                self.assertIn("bug", scan.labels)
                self.assertEqual(scan.unvalidated, 0, "no loss should be reported")

    def test_single_quoted_substitution_costs_no_recall(self):
        cmd = "gh issue create --repo o/r --body '$(cat b.md)' --label bug"
        scan = hook._extract_labels(cmd)
        self.assertEqual(scan.labels, ["bug"])
        self.assertEqual(scan.unvalidated, 0)

    def test_unquoted_substitution_is_the_only_losing_shape(self):
        for cmd in (
            "gh issue create --repo o/r --body $(cat b.md) --label bug",
            "gh issue create --repo o/r --body `cat b.md` --label bug",
        ):
            with self.subTest(cmd=cmd):
                scan = hook._extract_labels(cmd)
                self.assertEqual(scan.labels, [])
                self.assertEqual(scan.unvalidated, 1, "the loss must be counted, not silent")


class PrecisionRetainedTests(unittest.TestCase):
    """The gate must keep doing its job. Every false positive removed above is
    only a fix if a genuinely missing label still blocks."""

    _input = staticmethod(_test_helpers.bash_input)

    def test_genuinely_missing_label_still_blocks(self):
        with mock.patch.object(hook, "get_existing_labels", return_value=WAVE29_REAL_LABELS):
            result = hook.check(
                self._input(
                    "gh issue create --repo noorinalabs/noorinalabs-main "
                    '--title "t" --body "b" --label definitely-not-a-real-label'
                )
            )
        self.assertIsNotNone(result, "the gate stopped gating")
        self.assertEqual(result["decision"], "block")
        self.assertIn("definitely-not-a-real-label", result["reason"])

    def test_missing_label_alongside_real_ones_still_blocks(self):
        with mock.patch.object(hook, "get_existing_labels", return_value=WAVE29_REAL_LABELS):
            result = hook.check(
                self._input("gh issue create --label bug --label nope --label tech-debt")
            )
        self.assertIsNotNone(result)
        self.assertEqual(result["decision"], "block")
        self.assertIn("nope", result["reason"])

    def test_missing_label_inside_dollar_paren_now_blocks(self):
        """A true positive the PRE-FIX gate silently missed.

        `url=$(gh issue create …)` with no wrapper word after the paren
        tokenizes with the head glued (`url=$(gh`), so the old whole-command
        `is_gh_subcommand` guard never matched and `check()` returned early —
        no validation at all. Scoping fixes precision in BOTH directions:
        the $( ) shape is now gated for the first time.
        """
        with mock.patch.object(hook, "get_existing_labels", return_value=WAVE29_REAL_LABELS):
            result = hook.check(self._input("url=$(gh issue create --label not-a-real-label)"))
        self.assertIsNotNone(result, "the $( ) shape is still ungated")
        self.assertEqual(result["decision"], "block")
        self.assertIn("not-a-real-label", result["reason"])

    def test_mid_argument_substitution_loses_coverage_but_never_false_blocks(self):
        """Pinning the deliberate recall/precision trade, so it stays a decision.

        A `$( … )` inside the gh invocation's OWN arguments ends the parseable
        run of arguments, so later label flags go unvalidated: an allow, never
        a block — and, since main#1394 review round 2, an allow that SAYS so.

        RETRACTED RATIONALE (main#1394 review round 2, MF1). This test used to
        justify the trade by claiming the alternative "makes `--repo` resolve
        to `cat` and would query the wrong repo's label list". That is false.
        `check` resolves the repo from the RAW command via `extract_repo`,
        never from these segments, so a splice cannot touch repo resolution;
        and `extract_repo` on this shape returns `'$(cat'`, which fails the
        `gh label list` call into the existing allow-with-a-warning branch.
        The reason is corrected rather than the pin deleted, because the pin
        is still right — see the sibling test for the hazard that IS real.
        """
        cmd = "gh issue create --repo $(cat /tmp/r) --label not-a-real-label"
        self.assertEqual(hook.extract_labels(cmd), [])
        with mock.patch.object(hook, "get_existing_labels", return_value=WAVE29_REAL_LABELS):
            result = hook.check(self._input(cmd))
        self.assertIsNotNone(result, "the coverage loss must not be silent")
        self.assertEqual(result["decision"], "allow")
        self.assertIn("could not check 1 label flag", result["systemMessage"])

    def test_the_rejected_splice_repair_would_mint_a_label_from_a_command_name(self):
        """The hazard that actually justifies truncating (MF1, corrected).

        Splicing a substitution's words into the surrounding argument list
        makes its FIRST WORD look like the value of the preceding flag. For a
        label flag that is fatal, because a label value is exactly what this
        hook validates and blocks on:

            gh issue create --repo o/r --label $(cat labelfile)
              split (shipped) -> no labels     -> allow
              splice          -> label 'cat'   -> block on a command name

        No other change is needed for that to be live, so the trade is decided
        on a present hazard rather than on one conditional on #1409. Asserted
        against the real `_shell_parse` splice reading, not a hand-built list.
        """
        from _shell_parse import normalize_command_substitutions, tokenize, walk_flag_values

        cmd = "gh issue create --repo o/r --label $(cat labelfile)"

        # Precondition, read off the real splice reading: under a splice the
        # label flag's value resolves to the substituted COMMAND's name.
        spliced_tokens = tokenize(normalize_command_substitutions(cmd, separator=" "))
        self.assertIsNotNone(spliced_tokens)
        self.assertEqual(walk_flag_values(spliced_tokens, {"--label", "-l"}), ["cat"])

        # Shipped reading: the flag's value is unknowable, so nothing is claimed.
        self.assertEqual(hook.extract_labels(cmd), [])
        with mock.patch.object(hook, "get_existing_labels", return_value=WAVE29_REAL_LABELS):
            self.assertNotEqual(
                (hook.check(self._input(cmd)) or {}).get("decision"),
                "block",
                "the shipped reading must never block on a computed label value",
            )
        self.assertNotIn("cat", hook.extract_labels(cmd))

    def test_missing_label_in_a_heredoc_carrying_command_still_blocks(self):
        """The heredoc fix must not blanket-disable the gate for such commands."""
        cmd = (
            "cat > /tmp/note.md <<'EOF'\n"
            "prose mentioning bash -lc and --label ghost\n"
            "EOF\n"
            "gh issue create --repo o/r --body-file /tmp/note.md --label not-a-real-label"
        )
        with mock.patch.object(hook, "get_existing_labels", return_value=WAVE29_REAL_LABELS):
            result = hook.check(self._input(cmd))
        self.assertIsNotNone(result, "the gate stopped gating on heredoc commands")
        self.assertEqual(result["decision"], "block")
        self.assertIn("not-a-real-label", result["reason"])
        self.assertNotIn("ghost", result["reason"])


if __name__ == "__main__":
    unittest.main()
