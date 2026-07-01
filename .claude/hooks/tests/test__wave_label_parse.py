#!/usr/bin/env python3
"""Tests for the shared wave-label parser `_wave_label_parse` (#810).

Covers the three accepted label forms across the public surface:
  - legacy phase-prefixed `p{N}-wave-{M}` (grandfathered)
  - phase-agnostic global `wave-{X}`
  - placeholder `wave-x`

Run: python3 -m pytest .claude/hooks/tests/test__wave_label_parse.py -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_HOOKS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HOOKS_DIR))

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


if __name__ == "__main__":
    unittest.main()
