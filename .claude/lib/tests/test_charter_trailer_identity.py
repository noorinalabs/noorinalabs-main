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
