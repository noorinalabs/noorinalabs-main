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
        """`None` vs `""` is a typed invariant this test pins.

        It is NOT a runtime discriminator: every non-test consumer normalises the
        two together (truthiness, or an explicit `or ""`), so returning `""` here
        changes no live control flow. The invariant is still worth holding — an
        unmatched ref and an author with an empty surname should not be the same
        value — but a future refactor should not assume a caller depends on it.
        Corrected from an earlier "load-bearing at both call sites" claim by the
        #1269 review, which measured it.
        """
        for ref in ("main", "", "deployments/phase-3/wave-29", "A.Virtanen_0179-x"):
            with self.subTest(ref=ref):
                self.assertIsNone(extract_branch_author_lastname(ref))

    def test_prefix_must_anchor_at_the_start_of_the_ref(self):
        """A charter-shaped prefix buried mid-ref does not name a branch author."""
        self.assertIsNone(extract_branch_author_lastname("feature/A.Virtanen/0001-x"))


class HyphenatedSurnameTests(unittest.TestCase):
    """The lastname charset, pinned in BOTH directions (main#1269 review).

    The suite that shipped the #1175 consolidation scored an identical
    `420 passed` under three different lastname charsets, because it contained no
    hyphenated-surname fixture at all. A regex this central was therefore free to
    be wrong in either direction. These tests exist so that the charset cannot be
    narrowed back to `([A-Za-z]+)` — which does not reject a hyphenated surname,
    it TRUNCATES it at the surname's own hyphen — without going red.

    Every surname below is a real current roster member
    (`.claude/team/roster.json`), and each had open branches org-wide when this
    was written.
    """

    # The 8 hyphenated roster surnames whose branches appear org-wide, plus the
    # ASCII transliteration the commit-identity emails (and every live branch)
    # use for Méndez-Ríos.
    HYPHENATED = (
        "Vega-Cruz",
        "Reyes-Fuentes",
        "Diop-Sarr",
        "Mendez-Rios",
        "Mensah-Williams",
        "Vasquez-Paredes",
        "Osei-Mensah",
        "Nakamura-Whitfield",
    )

    def test_hyphenated_surname_survives_the_slash_form(self):
        for surname in self.HYPHENATED:
            ref = f"X.{surname}/0001-some-slug"
            with self.subTest(ref=ref):
                self.assertEqual(extract_branch_author_lastname(ref), surname)

    def test_hyphenated_surname_survives_the_dash_form(self):
        """The dash form is the harder half: the separator and the surname's own
        hyphen are the same character, disambiguated only by the `{IIII}` digit."""
        for surname in self.HYPHENATED:
            ref = f"X.{surname}-0001-some-slug"
            with self.subTest(ref=ref):
                self.assertEqual(extract_branch_author_lastname(ref), surname)

    def test_the_initial_survives_alongside_the_hyphenated_surname(self):
        """Both readers of the shared prefix must agree on a hyphenated ref.

        The lastname half asserts the VALUE, not merely `is not None`. An
        `assertIsNotNone` here would pass under the truncating charset too —
        `Mensah` is not None — making this fixture pin nothing in the direction
        that matters. (It was written that way first; the mutation run against
        `([A-Za-z]+)` is what caught it, which is the same failure mode this
        whole class exists to close.)
        """
        for surname in self.HYPHENATED:
            for ref in (f"K.{surname}/0001-x", f"K.{surname}-0001-x"):
                with self.subTest(ref=ref):
                    self.assertEqual(branch_author_first_initial(ref), "k")
                    self.assertEqual(extract_branch_author_lastname(ref), surname)

    def test_a_truncating_charset_would_be_caught(self):
        """Anti-vacuity: assert the exact truncation the old charset produced.

        If a future edit reverts the charset to `([A-Za-z]+)`, the tests above go
        red — but only if they really depend on the hyphen. This one names the
        wrong answer explicitly so the intent survives a reader who is tempted to
        "simplify" the regex back.
        """
        self.assertNotEqual(extract_branch_author_lastname("K.Mensah-Williams/0001-x"), "Mensah")
        self.assertEqual(
            extract_branch_author_lastname("K.Mensah-Williams/0001-x"), "Mensah-Williams"
        )

    def test_apostrophe_surnames_parse(self):
        """No roster member has one today; the charset admits it deliberately so
        the next `O'Brien` is not a repeat of this defect."""
        self.assertEqual(extract_branch_author_lastname("O.O'Brien/0001-x"), "O'Brien")

    def test_dash_form_without_an_issue_number_fails_safe_to_none(self):
        """The cost of admitting `-` into the lastname charset, paid deliberately.

        `A.Virtanen-branch-name-with-no-number` is genuinely ambiguous — the
        surname could be `Virtanen` or `Virtanen-Branch-Name-…`. A greedy wide
        charset (`([A-Za-z][A-Za-z'-]*)[-/]`) answers it confidently and wrongly
        (`Virtanen-branch-name-with-no`). Requiring the charter's `{IIII}` digit
        returns None, which routes to the hooks' existing "cannot validate
        direction, allow with a warning" path instead of to a wrong author.
        """
        self.assertIsNone(extract_branch_author_lastname("A.Virtanen-branch-name-with-no-number"))
        self.assertIsNone(extract_branch_author_lastname("M.Vega-Cruz-rework"))
        # …while the charter-conformant dash form still parses.
        self.assertEqual(extract_branch_author_lastname("M.Vega-Cruz-1120-rework"), "Vega-Cruz")

    def test_non_ascii_surnames_are_out_of_scope_and_return_none(self):
        """An EXPLICIT decision, not an oversight — tracked on main#1271.

        `[A-Za-z]` excludes these regardless of the hyphen, so their behaviour is
        byte-for-byte unchanged by #1269 (None before, None after). Widening to
        Unicode letters would also widen `branch_author_first_initial`, which
        feeds `validate_pr_review`'s *counting* merge gate — a separate decision
        that must not ride along on a format-hook fix.

        None is the fail-safe direction here: the format hook warns rather than
        guessing an author. Live impact is nil because the roster's own
        commit-identity emails transliterate (`Carolina.Mendez-Rios@`) and every
        open branch uses the ASCII form, which `Mendez-Rios` above covers.
        """
        for ref in (
            "C.Méndez-Ríos/0055-x",
            "C.Méndez-Ríos-0055-x",
            "C.Novák/0001-x",
            "T.Wójcik-0001-x",
            "P.Vidović/0001-x",
        ):
            with self.subTest(ref=ref):
                self.assertIsNone(extract_branch_author_lastname(ref))
                self.assertEqual(branch_author_first_initial(ref), "")

    def test_a_digit_led_surname_component_still_truncates(self):
        """The one shape the digit lookahead does NOT solve — recorded, not fixed.

        `X.Smith-3rd/0001-x` -> `Smith`. No roster surname has a digit-leading
        component, and the plain wide charset truncates it identically, so the
        lookahead is not the cause. Pinned so the limit is a known one.
        """
        self.assertEqual(extract_branch_author_lastname("X.Smith-3rd/0001-x"), "Smith")


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
        # Hyphenated surnames, both separators (#1269) — the readers have to
        # agree here too, and this table is the only place that checks the
        # agreement property rather than the individual return values.
        "K.Mensah-Williams/0001-project-scaffolding",
        "M.Vega-Cruz-1120-integration-marker-leak",
        "A.Virtanen_1175-x",
        "A.Virtanen1175",
        "deployments/phase-3/wave-29",
        "dependabot/pip/urllib3-2.5.0",
        "feature/A.Virtanen/0001-x",
        "main",
        "",
        # Non-ASCII surname: both readers must reject it together (#1271).
        "C.Méndez-Ríos/0055-x",
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
        """Not just "both matched" — they must describe the SAME person.

        The agreement property alone is too weak to pin the lastname charset:
        under the truncating `([A-Za-z]+)`, `K.Mensah-Williams/…` still yields a
        non-None lastname and a valid initial, so both readers still "agree"
        while naming the wrong person. Hence the explicit values below.
        """
        self.assertEqual(extract_branch_author_lastname("S.Ferreira/0001-x"), "Ferreira")
        self.assertEqual(branch_author_first_initial("S.Ferreira/0001-x"), "s")
        self.assertEqual(extract_branch_author_lastname("L.Ferreira-0001-x"), "Ferreira")
        self.assertEqual(branch_author_first_initial("L.Ferreira-0001-x"), "l")
        # …and on the hyphenated refs added to REFS for #1269.
        self.assertEqual(
            extract_branch_author_lastname("K.Mensah-Williams/0001-project-scaffolding"),
            "Mensah-Williams",
        )
        self.assertEqual(
            branch_author_first_initial("K.Mensah-Williams/0001-project-scaffolding"), "k"
        )
        self.assertEqual(
            extract_branch_author_lastname("M.Vega-Cruz-1120-integration-marker-leak"),
            "Vega-Cruz",
        )
        self.assertEqual(
            branch_author_first_initial("M.Vega-Cruz-1120-integration-marker-leak"), "m"
        )


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
