#!/usr/bin/env python3
"""Tests for the shared wave-label parser `_wave_label_parse` (#810).

Covers the three accepted label forms across the public surface:
  - legacy phase-prefixed `p{N}-wave-{M}` (grandfathered)
  - phase-agnostic global `wave-{X}`
  - placeholder `wave-x`

Run: python3 -m pytest .claude/hooks/tests/test__wave_label_parse.py -v
"""

from __future__ import annotations

import unittest

import _test_helpers  # noqa: E402,F401
import _wave_label_parse as p  # noqa: E402


class IsWaveLabel(unittest.TestCase):
    def test_legacy_form_true(self) -> None:
        self.assertTrue(p.is_wave_label("p6-wave-16"))
        self.assertTrue(p.is_wave_label("p3-wave-10"))

    def test_global_form_true(self) -> None:
        self.assertTrue(p.is_wave_label("wave-16"))
        self.assertTrue(p.is_wave_label("wave-1"))

    def test_placeholder_true(self) -> None:
        self.assertTrue(p.is_wave_label("wave-x"))

    def test_suffixed_false(self) -> None:
        """Anchored: a trailing segment defeats the match for every form."""
        self.assertFalse(p.is_wave_label("p3-wave-10-special"))
        self.assertFalse(p.is_wave_label("wave-10-frozen"))
        self.assertFalse(p.is_wave_label("wave-x-tbd"))

    def test_junk_false(self) -> None:
        for v in (
            "",
            "wave-",
            "wave",
            "wave-X",
            "Wave-16",
            "WAVE-16",
            "p6-wave-",
            "bug",
            "wave-1x",
        ):
            with self.subTest(v=v):
                self.assertFalse(p.is_wave_label(v))


class ParseWaveLabelSpec(unittest.TestCase):
    def test_legacy(self) -> None:
        spec = p.parse_wave_label_spec("p6-wave-16")
        assert spec is not None
        self.assertEqual((spec.phase, spec.wave, spec.is_placeholder), (6, 16, False))
        self.assertEqual(spec.raw, "p6-wave-16")

    def test_global(self) -> None:
        spec = p.parse_wave_label_spec("wave-16")
        assert spec is not None
        self.assertEqual((spec.phase, spec.wave, spec.is_placeholder), (None, 16, False))

    def test_placeholder(self) -> None:
        spec = p.parse_wave_label_spec("wave-x")
        assert spec is not None
        self.assertEqual((spec.phase, spec.wave, spec.is_placeholder), (None, None, True))

    def test_invalid_returns_none(self) -> None:
        for v in ("", "wave-X", "p6-wave-16-x", "bug"):
            with self.subTest(v=v):
                self.assertIsNone(p.parse_wave_label_spec(v))


class ParseWaveLabelLegacyOnly(unittest.TestCase):
    """parse_wave_label is legacy-form-only by contract (its tuple has no None phase)."""

    def test_legacy_returns_tuple(self) -> None:
        self.assertEqual(p.parse_wave_label("p6-wave-16"), (6, 16))

    def test_new_forms_return_none(self) -> None:
        self.assertIsNone(p.parse_wave_label("wave-16"))
        self.assertIsNone(p.parse_wave_label("wave-x"))


class WaveLabelToOptionName(unittest.TestCase):
    def test_legacy_maps_to_PNWM(self) -> None:
        self.assertEqual(p.wave_label_to_option_name("p6-wave-16"), "P6W16")
        self.assertEqual(p.wave_label_to_option_name("p3-wave-10"), "P3W10")

    def test_global_maps_to_WX(self) -> None:
        self.assertEqual(p.wave_label_to_option_name("wave-16"), "W16")

    def test_placeholder_maps_to_WX_literal(self) -> None:
        self.assertEqual(p.wave_label_to_option_name("wave-x"), "WX")

    def test_invalid_returns_none(self) -> None:
        self.assertIsNone(p.wave_label_to_option_name("bug"))
        self.assertIsNone(p.wave_label_to_option_name("wave-10-frozen"))


class ParseChangesAcceptsNewForms(unittest.TestCase):
    """The gh-command parsers accept new label forms via the shared grammar."""

    def test_edit_add_global_form(self) -> None:
        changes = p.parse_wave_label_changes(
            'gh issue edit 42 --repo noorinalabs/noorinalabs-main --add-label "wave-16"'
        )
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].add_label, "wave-16")
        self.assertEqual(changes[0].issue_number, "42")

    def test_edit_remove_placeholder(self) -> None:
        changes = p.parse_wave_label_changes(
            'gh issue edit 42 --repo noorinalabs/noorinalabs-main --remove-label "wave-x"'
        )
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].remove_label, "wave-x")

    def test_relabel_both_new_forms(self) -> None:
        change = p.parse_wave_label_change(
            "gh issue edit 42 --repo noorinalabs/noorinalabs-main "
            '--add-label "wave-16" --remove-label "wave-15"'
        )
        assert change is not None
        self.assertEqual(change.add_label, "wave-16")
        self.assertEqual(change.remove_label, "wave-15")

    def test_create_global_form(self) -> None:
        creates = p.parse_wave_label_create(
            'gh issue create --repo noorinalabs/noorinalabs-main --title t --label "wave-16"'
        )
        self.assertEqual(len(creates), 1)
        self.assertEqual(creates[0].add_label, "wave-16")

    def test_create_placeholder_form(self) -> None:
        creates = p.parse_wave_label_create(
            'gh issue create --repo noorinalabs/noorinalabs-main --title t --label "wave-x"'
        )
        self.assertEqual(len(creates), 1)
        self.assertEqual(creates[0].add_label, "wave-x")

    def test_legacy_still_parses(self) -> None:
        """Grandfather: legacy form still parses unchanged."""
        changes = p.parse_wave_label_changes(
            'gh issue edit 42 --repo noorinalabs/noorinalabs-main --add-label "p6-wave-16"'
        )
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].add_label, "p6-wave-16")


class CdPrefixedCommand(unittest.TestCase):
    """#901: a `cd ...`-prefixed `gh issue edit/create` must still parse.

    Before the `normalize_command_separators` fix, a leading `cd` joined to the
    `gh` invocation by a NEWLINE (shlex eats newlines as whitespace) or by a
    non-space-padded `;` (`/dir;` sticks together) collapsed `cd` and `gh` into
    one command segment whose first token was `cd`. `find_gh_subcommand` bailed
    and the parser returned an empty list — so both PostToolUse hooks
    (`post_wave_kickoff_comment`, `post_label_change_wave_field_sync`) silently
    skipped (`skip_parser_returned_empty`). These are the regression cases.
    """

    # The exact P7W20-kickoff shape from the issue repro: `cd "$(...)"` then a
    # newline then the label-apply. This is the case that FAILS pre-fix.
    _NEWLINE_CD = (
        'cd "$(git rev-parse --show-toplevel)"\n'
        'gh issue edit 901 --repo noorinalabs/noorinalabs-main --add-label "wave-20"'
    )

    def test_edit_newline_cd_subst_prefix(self) -> None:
        changes = p.parse_wave_label_changes(self._NEWLINE_CD)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].issue_number, "901")
        self.assertEqual(changes[0].add_label, "wave-20")
        self.assertEqual(changes[0].repo, "noorinalabs-main")

    def test_edit_newline_cd_subst_prefix_singular(self) -> None:
        change = p.parse_wave_label_change(self._NEWLINE_CD)
        assert change is not None  # the kickoff-comment hook's entry point
        self.assertEqual(change.add_label, "wave-20")

    def test_edit_andand_cd_prefix(self) -> None:
        changes = p.parse_wave_label_changes(
            'cd "$(git rev-parse --show-toplevel)" && '
            'gh issue edit 901 --repo noorinalabs/noorinalabs-main --add-label "wave-20"'
        )
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].add_label, "wave-20")

    def test_edit_semicolon_nospace_cd_prefix(self) -> None:
        """`cd /dir; gh ...` — the `;` is not space-padded, so shlex keeps it
        attached to `/dir` pre-fix; the normalizer splits it out."""
        changes = p.parse_wave_label_changes(
            'cd /some/dir; gh issue edit 5 --add-label "p6-wave-16"'
        )
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].issue_number, "5")
        self.assertEqual(changes[0].add_label, "p6-wave-16")

    def test_create_newline_cd_prefix(self) -> None:
        creates = p.parse_wave_label_create(
            'cd "$(git rev-parse --show-toplevel)"\n'
            "gh issue create --repo noorinalabs/noorinalabs-main "
            '--title t --label "wave-20"'
        )
        self.assertEqual(len(creates), 1)
        self.assertEqual(creates[0].add_label, "wave-20")
        self.assertEqual(creates[0].repo, "noorinalabs-main")

    def test_bare_command_unchanged(self) -> None:
        """Regression guard: an un-prefixed command still parses identically."""
        changes = p.parse_wave_label_changes(
            'gh issue edit 42 --repo noorinalabs/noorinalabs-main --add-label "wave-16"'
        )
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].add_label, "wave-16")

    def test_operators_inside_quoted_arg_not_split(self) -> None:
        """A `;`/`&&`/`|` INSIDE a quoted `--body` is data, not a separator:
        the edit still parses and no spurious segment is introduced."""
        changes = p.parse_wave_label_changes(
            'cd /repo && gh issue edit 7 --add-label "wave-20" --body "run x && y; then z | w"'
        )
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].issue_number, "7")
        self.assertEqual(changes[0].add_label, "wave-20")


class RepoFlagResolution(unittest.TestCase):
    """#985: the `-R`/`--repo` flag is authoritative and all five surface forms
    resolve; the `repo_flag_present` bit disambiguates the two repo=None cases
    (flag omitted #650 vs present-but-unresolvable #981)."""

    def _change(self, cmd: str):
        change = p.parse_wave_label_change(cmd)
        assert change is not None
        return change

    def test_long_repo_flag(self) -> None:
        c = self._change(
            'gh issue edit 42 --repo noorinalabs/noorinalabs-deploy --add-label "wave-26"'
        )
        self.assertEqual(c.repo, "noorinalabs-deploy")
        self.assertTrue(c.repo_flag_present)

    def test_short_R_flag_spaced(self) -> None:
        c = self._change('gh issue edit 42 -R noorinalabs/noorinalabs-deploy --add-label "wave-26"')
        self.assertEqual(c.repo, "noorinalabs-deploy")
        self.assertTrue(c.repo_flag_present)

    def test_short_R_flag_attached(self) -> None:
        c = self._change('gh issue edit 42 -Rnoorinalabs/noorinalabs-deploy --add-label "wave-26"')
        self.assertEqual(c.repo, "noorinalabs-deploy")
        self.assertTrue(c.repo_flag_present)

    def test_short_R_flag_equals(self) -> None:
        c = self._change('gh issue edit 42 -R=noorinalabs/noorinalabs-deploy --add-label "wave-26"')
        self.assertEqual(c.repo, "noorinalabs-deploy")
        self.assertTrue(c.repo_flag_present)

    def test_no_repo_flag_absent(self) -> None:
        c = self._change('gh issue edit 42 --add-label "wave-26"')
        self.assertIsNone(c.repo)
        self.assertFalse(c.repo_flag_present)

    def test_unexpanded_var_present_but_unresolvable(self) -> None:
        """`-R $VAR` → repo=None (shlex left `$DA` literal) AND
        repo_flag_present=True. The True bit is the #981 fail-closed signal."""
        c = self._change('gh issue edit 42 -R "$DA" --add-label "wave-26"')
        self.assertIsNone(c.repo)
        self.assertTrue(c.repo_flag_present)

    def test_unexpanded_var_long_form_unresolvable(self) -> None:
        c = self._change('gh issue edit 42 --repo "noorinalabs/$REPO" --add-label "wave-26"')
        self.assertIsNone(c.repo)
        self.assertTrue(c.repo_flag_present)

    def test_repeated_repo_flag_last_wins(self) -> None:
        """main#1060 finding #3: gh's `--repo`/`-R` is a single-value pflag,
        so a repeated flag resolves to its LAST occurrence."""
        c = self._change(
            'gh issue edit 42 -R noorinalabs/repo-a --repo noorinalabs/repo-b --add-label "wave-26"'
        )
        self.assertEqual(c.repo, "repo-b")
        self.assertTrue(c.repo_flag_present)

    def test_value_less_short_flag_does_not_misroute_to_add_label(self) -> None:
        """main#1060 finding #1 — the #1059 motivating reproducer: a
        value-less `-R` immediately followed by `--add-label` must not
        resolve `repo='--add-label'`. Real gh would error here; this parser
        must yield `repo=None, repo_flag_present=False` (no capturable
        value), not misroute onto the neighboring flag's own text."""
        c = self._change('gh issue edit 42 -R --add-label "wave-26"')
        self.assertIsNone(c.repo)
        self.assertFalse(c.repo_flag_present)
        # The neighboring flag is still parsed correctly as its own flag,
        # not swallowed as `-R`'s bogus value.
        self.assertEqual(c.add_label, "wave-26")

    def test_repo_after_double_dash_terminator_not_resolved(self) -> None:
        """main#1060 finding #2: `--repo` appearing after a literal `--`
        (POSIX end-of-options) is positional in real gh, never a flag."""
        c = self._change('gh issue edit 42 --add-label "wave-26" -- --repo noorinalabs/repo-c')
        self.assertIsNone(c.repo)
        self.assertFalse(c.repo_flag_present)


class NormalizeCommandSeparators(unittest.TestCase):
    """Direct tests for the shared `_shell_parse.normalize_command_separators`.

    Assertions are whitespace-insensitive on purpose: the contract is that
    after normalization + `tokenize`, the separator survives as its own token
    so `iter_command_segments` splits correctly (exact space padding is an
    implementation detail shlex collapses)."""

    def setUp(self) -> None:
        import _shell_parse as sp  # noqa: PLC0415

        self.sp = sp

    def _segments(self, cmd: str) -> list[list[str]]:
        normalized = self.sp.normalize_command_separators(cmd)
        tokens = self.sp.tokenize(normalized)
        assert tokens is not None
        return list(self.sp.iter_command_segments(tokens))

    def test_unquoted_newline_becomes_separator(self) -> None:
        self.assertEqual(self._segments("cmd1 a\ncmd2 b"), [["cmd1", "a"], ["cmd2", "b"]])

    def test_nonspaced_semicolon_becomes_separator(self) -> None:
        self.assertEqual(self._segments("cd /x; gh"), [["cd", "/x"], ["gh"]])

    def test_andand_and_pipe_split(self) -> None:
        self.assertEqual(self._segments("cd /x&&gh|jq"), [["cd", "/x"], ["gh"], ["jq"]])

    def test_quoted_newline_preserved_as_single_token(self) -> None:
        self.assertEqual(self._segments('echo "a\nb"'), [["echo", "a\nb"]])

    def test_quoted_operators_not_split(self) -> None:
        self.assertEqual(self._segments('echo "a && b; c | d"'), [["echo", "a && b; c | d"]])

    def test_single_quote_operators_not_split(self) -> None:
        self.assertEqual(self._segments("echo 'a; b'"), [["echo", "a; b"]])

    def test_line_continuation_joined_not_split(self) -> None:
        self.assertEqual(self._segments("echo a \\\n  b"), [["echo", "a", "b"]])


_REPO = "--repo noorinalabs/noorinalabs-main"


class WrappedAndCompoundEditForms(unittest.TestCase):
    """main#1141 — every row of the issue's verified repro table.

    The two rows that already passed (redirect, `&&`) are pinned here too so
    the wrapper fix cannot regress them.
    """

    def _first(self, command: str):
        return p.parse_wave_label_change(command)

    def test_plain(self) -> None:
        c = self._first(f'gh issue edit 1114 {_REPO} --add-label "wave-29"')
        self.assertIsNotNone(c)
        self.assertEqual(
            (c.repo, c.issue_number, c.add_label), ("noorinalabs-main", "1114", "wave-29")
        )

    def test_redirect_still_parses(self) -> None:
        c = self._first(f'gh issue edit 1114 {_REPO} --add-label "wave-29" >/dev/null 2>&1')
        self.assertIsNotNone(c)
        self.assertEqual(c.issue_number, "1114")

    def test_and_chain_still_parses(self) -> None:
        c = self._first(f'gh issue edit 1114 {_REPO} --add-label "wave-29" && echo ok')
        self.assertIsNotNone(c)
        self.assertEqual(c.issue_number, "1114")

    def test_timeout_prefix(self) -> None:
        """A `timeout N gh …` prefix returned None before main#1141."""
        c = self._first(f'timeout 45 gh issue edit 1114 {_REPO} --add-label "wave-29"')
        self.assertIsNotNone(c)
        self.assertEqual(
            (c.repo, c.issue_number, c.add_label), ("noorinalabs-main", "1114", "wave-29")
        )

    def test_loop_with_literal_issue_number(self) -> None:
        """THE row that disproves the variable-expansion theory.

        An earlier revision of main#1141 blamed the unexpanded `"$n"`. A loop
        carrying a fully LITERAL issue number failed identically, so the loop
        CONSTRUCT was the defeater — `do` sat at token 0 of the segment. It
        must parse now.
        """
        c = self._first(f'for x in a; do gh issue edit 1114 {_REPO} --add-label "wave-29"; done')
        self.assertIsNotNone(c)
        self.assertEqual(
            (c.repo, c.issue_number, c.add_label), ("noorinalabs-main", "1114", "wave-29")
        )

    def test_loop_with_variable_stays_unparsed(self) -> None:
        """The residual, and it must stay unparsed.

        The issue number is genuinely absent from the command string; treating
        `$n` as a ref would post to a nonexistent issue. It is surfaced via
        `parse_unresolved_wave_label_edits` and fixed for real by the
        state-based sweep, not by loosening this parser.
        """
        self.assertIsNone(
            self._first(
                f'for n in 1114 1116; do gh issue edit "$n" {_REPO} --add-label "wave-29"; done'
            )
        )

    def test_loop_plus_timeout_both_stripped(self) -> None:
        c = self._first(
            f'for x in a; do timeout 45 gh issue edit 1114 {_REPO} --add-label "wave-29"; done'
        )
        self.assertIsNotNone(c)
        self.assertEqual(c.issue_number, "1114")

    def test_multi_iteration_loop_body_expanded(self) -> None:
        """Two literal-number invocations in one loop body yield two changes."""
        changes = p.parse_wave_label_changes(
            f'for x in a; do gh issue edit 1114 {_REPO} --add-label "wave-29"; '
            f'gh issue edit 1116 {_REPO} --add-label "wave-29"; done'
        )
        self.assertEqual([c.issue_number for c in changes], ["1114", "1116"])

    def test_label_inside_echo_is_not_a_change(self) -> None:
        """Data position stays data: the allowlist never strips `echo`."""
        self.assertIsNone(self._first(f'echo gh issue edit 1114 {_REPO} --add-label "wave-29"'))


class ParseUnresolvedWaveLabelEdits(unittest.TestCase):
    """main#1141 — the hook must be able to say "I declined", not go silent."""

    def test_loop_variable_is_reported(self) -> None:
        found = p.parse_unresolved_wave_label_edits(
            f'for n in 1114 1116; do gh issue edit "$n" {_REPO} --add-label "wave-29"; done'
        )
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].add_label, "wave-29")
        self.assertEqual(found[0].issue_token, "$n")
        self.assertEqual(found[0].repo, "noorinalabs-main")

    def test_timeout_wrapped_loop_variable_is_reported(self) -> None:
        found = p.parse_unresolved_wave_label_edits(
            f'for n in 1114; do timeout 45 gh issue edit "$n" {_REPO} --add-label "wave-29"; done'
        )
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].issue_token, "$n")

    def test_resolvable_command_is_not_reported(self) -> None:
        self.assertEqual(
            p.parse_unresolved_wave_label_edits(
                f'gh issue edit 1114 {_REPO} --add-label "wave-29"'
            ),
            [],
        )

    def test_non_wave_label_is_not_reported(self) -> None:
        self.assertEqual(
            p.parse_unresolved_wave_label_edits(
                f'for n in 1; do gh issue edit "$n" {_REPO} --add-label "bug"; done'
            ),
            [],
        )

    def test_unexpanded_repo_value_is_not_mistaken_for_the_issue_ref(self) -> None:
        """`--repo "$R"` is a FLAG VALUE, never the issue positional."""
        found = p.parse_unresolved_wave_label_edits(
            'for n in 1; do gh issue edit --repo "$R" --add-label "wave-29"; done'
        )
        self.assertEqual(len(found), 1)
        self.assertIsNone(found[0].issue_token)

    def test_relabel_shape_is_reported_for_the_caller_to_filter(self) -> None:
        found = p.parse_unresolved_wave_label_edits(
            f'for n in 1; do gh issue edit "$n" {_REPO} --add-label "wave-29" '
            '--remove-label "wave-28"; done'
        )
        self.assertEqual(len(found), 1)
        self.assertEqual((found[0].add_label, found[0].remove_label), ("wave-29", "wave-28"))

    def test_unparseable_command_yields_empty(self) -> None:
        self.assertEqual(p.parse_unresolved_wave_label_edits('gh issue edit "unbalanced'), [])


if __name__ == "__main__":
    unittest.main()
