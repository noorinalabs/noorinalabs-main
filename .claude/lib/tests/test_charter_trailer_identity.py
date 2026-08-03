#!/usr/bin/env python3
"""Tests for `charter_trailer`'s person-identity helpers (closes #1172).

The org roster holds 78 names and it contains surname collisions. Both
review hooks answered "is this person the branch author?" by comparing
SURNAMES, so `Lucas Ferreira` and `Santiago Ferreira` were one person to
every gate that mattered, and the two hooks failed in opposite directions
off that one wrong answer:

  * `validate_review_comment_format` BLOCKED Santiago's correct verdict on
    `L.Ferreira/1151-…` as a swap — with no observable-body workaround, so
    the verdict could not be posted at all.
  * `validate_pr_review` discarded the same verdict as a self-review, leaving
    the PR one approval short.

These tests pin the discriminator itself. The hook-level tests
(`test_validate_review_comment_format.py::SurnameCollisionTests`,
`test_validate_pr_review.py::SurnameCollisionSelfReviewTests`) pin the
behaviour at each call site.

The load-bearing property is that this is a NARROWING, not a widening: every
assertion that a same-surname colleague is admitted is paired with one that a
genuine self-review is still refused. A gate that stops false-positiving by
stopping firing has not been fixed.

Run: python3 -m pytest .claude/lib/tests/test_charter_trailer_identity.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_LIB_DIR))

from charter_trailer import (  # noqa: E402
    branch_author_first_initial,
    extract_branch_author_lastname,
    is_branch_author,
    name_first_initial,
    name_lastname,
)


class NameLastnameTests(unittest.TestCase):
    def test_two_token_name(self):
        self.assertEqual(name_lastname("Santiago Ferreira"), "Ferreira")

    def test_branch_style_abbreviation(self):
        self.assertEqual(name_lastname("S.Ferreira"), "Ferreira")

    def test_markdown_bold_is_stripped(self):
        self.assertEqual(name_lastname("**Santiago Ferreira**"), "Ferreira")

    def test_parenthetical_role_is_stripped(self):
        self.assertEqual(name_lastname("Nadia Khoury (Program Director)"), "Khoury")

    def test_single_token_falls_back_to_the_whole_value(self):
        self.assertEqual(name_lastname("Ferreira"), "Ferreira")

    def test_empty_value(self):
        self.assertEqual(name_lastname(""), "")

    def test_trailing_separator_does_not_yield_an_empty_lastname(self):
        """`Santiago Ferreira.` must not parse as lastname `''`.

        The pre-#1172 splitter kept empty tokens and returned `''` here, which
        matches no branch author — a silent hole on any value that happened to
        end in the separator. Empty tokens are now dropped.
        """
        self.assertEqual(name_lastname("Santiago Ferreira."), "Ferreira")


class NameFirstInitialTests(unittest.TestCase):
    def test_spelled_out_first_name(self):
        self.assertEqual(name_first_initial("Santiago Ferreira"), "s")

    def test_branch_style_abbreviation(self):
        self.assertEqual(name_first_initial("L.Ferreira"), "l")

    def test_case_is_normalised(self):
        self.assertEqual(name_first_initial("LUCAS FERREIRA"), "l")

    def test_single_token_has_no_derivable_initial(self):
        """A bare surname yields `''` — unknown, never a distinguishing value."""
        self.assertEqual(name_first_initial("Ferreira"), "")

    def test_empty_value_has_no_derivable_initial(self):
        self.assertEqual(name_first_initial(""), "")

    def test_middle_name_does_not_shift_the_initial(self):
        self.assertEqual(name_first_initial("Lucas Miguel Ferreira"), "l")


class BranchAuthorFirstInitialTests(unittest.TestCase):
    def test_slash_separator(self):
        self.assertEqual(branch_author_first_initial("L.Ferreira/1151-cd-misroute"), "l")

    def test_dash_separator(self):
        self.assertEqual(branch_author_first_initial("A.Virtanen-0179-branch-regex-fix"), "a")

    def test_wave_merge_branch_has_no_prefix(self):
        self.assertEqual(branch_author_first_initial("deployments/phase-3/wave-29"), "")

    def test_plain_branch_name_has_no_prefix(self):
        self.assertEqual(branch_author_first_initial("main"), "")


class ExtractBranchAuthorLastnameTests(unittest.TestCase):
    """The lastname half of the branch prefix, consolidated here by #1175.

    It was two hook-local copies before: `validate_pr_review`'s accepted both
    separators after #179, `validate_review_comment_format`'s accepted only the
    slash, and nothing tied them together. The hook suites assert the shared
    binding (`SharedBranchAuthorParsingTests` in each); these tests own the
    behaviour.
    """

    def test_slash_separator(self):
        self.assertEqual(extract_branch_author_lastname("L.Ferreira/1151-cd-misroute"), "Ferreira")

    def test_dash_separator(self):
        self.assertEqual(
            extract_branch_author_lastname("A.Virtanen-0179-branch-regex-fix"), "Virtanen"
        )

    def test_two_letter_lastname(self):
        self.assertEqual(extract_branch_author_lastname("L.Li/0001-fix"), "Li")

    def test_case_is_preserved_not_normalised(self):
        """Callers compare through `is_branch_author`, which lowercases both sides.

        Normalising here would silently change the block message's rendering of
        the author's surname, so the raw ref casing is returned unchanged.
        """
        self.assertEqual(extract_branch_author_lastname("a.virtanen/0001-fix"), "virtanen")

    def test_underscore_separator_is_rejected(self):
        """The worktree-directory form is not a ref form — accepting it would
        widen who counts as a branch author."""
        self.assertIsNone(extract_branch_author_lastname("A.Virtanen_0179-x"))

    def test_no_separator_is_rejected(self):
        self.assertIsNone(extract_branch_author_lastname("A.Virtanen0179"))

    def test_wave_merge_branch_is_rejected(self):
        self.assertIsNone(extract_branch_author_lastname("deployments/phase-3/wave-29"))

    def test_plain_branch_name_is_rejected(self):
        self.assertIsNone(extract_branch_author_lastname("main"))

    def test_empty_ref_is_rejected(self):
        self.assertIsNone(extract_branch_author_lastname(""))

    def test_absence_is_none_never_the_empty_string(self):
        """`None` vs `""` is load-bearing at both call sites.

        `validate_pr_review` passes the value into the `""` wave-merge sentinel
        path, and `is_branch_author` treats `""` as "nobody is the author". A
        parser that returned `""` for an unmatched ref would be indistinguishable
        from one that matched an author with an empty surname.
        """
        for ref in ("main", "", "deployments/phase-3/wave-29", "A.Virtanen_0179-x"):
            with self.subTest(ref=ref):
                self.assertIsNone(extract_branch_author_lastname(ref))

    def test_prefix_must_anchor_at_the_start_of_the_ref(self):
        """A charter-shaped prefix buried mid-ref does not name a branch author."""
        self.assertIsNone(extract_branch_author_lastname("feature/A.Virtanen/0001-x"))


class BranchPrefixReadersAgreeTests(unittest.TestCase):
    """The two readers of the branch prefix must agree that it IS one (#1175).

    They share `_BRANCH_AUTHOR_PREFIX_RE`, so this is structural rather than a
    coincidence to be maintained — but the property is what the call sites rely
    on (`validate_pr_review.resolve_review_verdicts` derives lastname and
    initial from the same ref and would otherwise build a half-known author),
    so it is pinned at the level of the property and not of the regex.
    """

    REFS = (
        "A.Virtanen/1175-consolidation",
        "A.Virtanen-1175-consolidation",
        "a.virtanen/1175-x",
        "L.Li/0001-fix",
        "A.Virtanen_1175-x",
        "A.Virtanen1175",
        "deployments/phase-3/wave-29",
        "dependabot/pip/urllib3-2.5.0",
        "feature/A.Virtanen/0001-x",
        "main",
        "",
    )

    def test_both_readers_match_the_same_refs(self):
        for ref in self.REFS:
            with self.subTest(ref=ref):
                self.assertEqual(
                    extract_branch_author_lastname(ref) is not None,
                    bool(branch_author_first_initial(ref)),
                )

    def test_the_ref_table_covers_both_outcomes(self):
        """Anti-vacuity: an all-matching or all-rejecting table proves nothing."""
        matched = [r for r in self.REFS if extract_branch_author_lastname(r) is not None]
        self.assertGreaterEqual(len(matched), 4)
        self.assertGreaterEqual(len(self.REFS) - len(matched), 4)

    def test_the_initial_and_lastname_come_from_the_same_prefix(self):
        """Not just "both matched" — they must describe the SAME person."""
        self.assertEqual(extract_branch_author_lastname("S.Ferreira/0001-x"), "Ferreira")
        self.assertEqual(branch_author_first_initial("S.Ferreira/0001-x"), "s")
        self.assertEqual(extract_branch_author_lastname("L.Ferreira-0001-x"), "Ferreira")
        self.assertEqual(branch_author_first_initial("L.Ferreira-0001-x"), "l")


class IsBranchAuthorTests(unittest.TestCase):
    """The #1172 defect and its true-positive twin, at the level of the predicate."""

    def test_same_surname_different_person_is_not_the_author(self):
        """THE DEFECT: Santiago Ferreira reviewing `L.Ferreira/1151-…`."""
        self.assertFalse(is_branch_author("Santiago Ferreira", "Ferreira", "l"))

    def test_the_author_themselves_is_still_the_author(self):
        """THE TRUE POSITIVE: Lucas Ferreira named on his own branch."""
        self.assertTrue(is_branch_author("Lucas Ferreira", "Ferreira", "l"))

    def test_different_surname_is_not_the_author(self):
        self.assertFalse(is_branch_author("Aino Virtanen", "Ferreira", "l"))

    def test_match_is_case_insensitive_on_both_halves(self):
        self.assertTrue(is_branch_author("lucas ferreira", "FERREIRA", "L"))

    def test_role_annotation_does_not_defeat_the_match(self):
        self.assertTrue(is_branch_author("Lucas Ferreira (Backend Engineer)", "Ferreira", "l"))

    def test_unknown_field_initial_falls_back_to_surname_and_still_blocks(self):
        """A bare `Ferreira` keeps the stricter pre-#1172 answer.

        No initial is derivable from one token, so the surname decides. That
        over-matches (it calls Santiago the author), which is the fail-CLOSED
        direction at both call sites: refuse the comment / do not count the
        reviewer. A gate may err toward refusing, never toward admitting.
        """
        self.assertTrue(is_branch_author("Ferreira", "Ferreira", "l"))

    def test_unknown_branch_initial_falls_back_to_surname(self):
        """Head refs with no `{Initial}.{Lastname}` prefix keep surname-only."""
        self.assertTrue(is_branch_author("Santiago Ferreira", "Ferreira", ""))

    def test_empty_branch_lastname_never_matches(self):
        """The wave-merge sentinel (`""`, main#294) means "no implementer author"."""
        self.assertFalse(is_branch_author("Santiago Ferreira", "", ""))
        self.assertFalse(is_branch_author("", "", ""))

    def test_branch_initial_defaults_to_unknown(self):
        """Omitting the initial degrades to surname-only, not to "no match"."""
        self.assertTrue(is_branch_author("Santiago Ferreira", "Ferreira"))


if __name__ == "__main__":
    unittest.main()
