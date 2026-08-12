#!/usr/bin/env python3
"""Every consumer of the `RequestOrReplied:` direction must agree (main#1371).

Verdict-direction classification was implemented FOUR times after main#1359
extracted the vocabulary:

  * `validate_review_comment_format._VERDICT_DIRECTIONS` + `._direction_is_verdict`
        first-1-and-first-2-token join against a frozenset; EXCLUDED bare `Changes`.
  * `validate_review_comment_format._direction_is_changes_requested`
        first-token alnum normalisation; INCLUDED bare `Changes` (main#1363,
        deliberately, so the gate would share the grammar of the counter it
        guards).
  * `validate_pr_review._is_verdict` + `._VERDICT_REQUIRING_TECH_DEBT`
        whole-value lowercase + `rstrip("*")` + exact-set membership.
  * `validate_pr_review._is_approved`
        whole-value lowercase + `rstrip("*")` + `== "approved"`.

Four algorithms, three answers for bare `Changes`, and — the axis nobody had
written down — two different *extractions*: the two hook-local predicates read
the FIRST raw `re.search(r"RequestOrReplied:\\s*(.+)")` hit over the whole
un-stripped body, while the counter reads `charter_trailer
.extract_charter_field`'s code-stripped, trailer-scoped, last-match-wins value.
Agreeing on the vocabulary but not on WHICH TEXT is classified is half an
agreement; #934 fixed exactly this for the `Requestor` field in this same hook
and left `RequestOrReplied` on the raw first match.

THIS FILE IS THE PRE-FIX FAILURE. Against the parent of the main#1371 commit,
`AgreementMatrixTests` and `SwapGateReadsTheValueTheCounterReadsTests` fail;
`PredicateSingularityTests` fails at import (the shared predicates do not
exist yet). Run:

    python3 -m pytest .claude/hooks/tests/test_verdict_direction_agreement.py
"""

from __future__ import annotations

import unittest
from typing import ClassVar
from unittest import mock

import _test_helpers

# `_test_helpers`' import side effect puts the hooks dir and the lib dir on
# `sys.path`, so it MUST be imported before the four modules below. It is here
# on the strength of alphabetical ordering alone — a leading underscore sorts
# first, so ruff's isort keeps it there — plus this statement, which breaks the
# import block so the sort cannot move anything across it. See `_test_helpers`
# § docstring for the failure mode (an autofix silently relocating a bootstrap
# import after the import that needs it).
_LIB_DIR = _test_helpers.LIB_DIR

import charter_trailer as ct  # noqa: E402
import trust_signals as ts  # noqa: E402
import validate_pr_review as counting  # noqa: E402
import validate_review_comment_format as fmt  # noqa: E402


def _body(direction: str) -> str:
    """A minimal charter comment carrying `direction` in a real trailer block."""
    return (
        "Looks correct.\n\n"
        "---\n"
        "Requestor: Nadia Khoury\n"
        "Requestee: Aino Virtanen\n"
        f"RequestOrReplied: {direction}\n"
        "TechDebt: none\n"
    )


# The full spelling matrix. Every row is a `RequestOrReplied:` value that has
# been typed, or is one keystroke away from a value that has been typed, in
# this org's PR threads. `kind` is the answer `charter_trailer.verdict_kind`
# gives — the ONE classifier every consumer must now route through.
#
# The rows marked `# div` are where the four pre-main#1371 implementations
# disagreed with each other. They are not decoration: each one is a comment
# that the format gate blesses as a verdict and the counting gate scores as
# zero reviews, or vice versa.
SPELLINGS: tuple[tuple[str, str], ...] = (
    ("Approved", "approved"),
    ("approved", "approved"),
    ("APPROVED", "approved"),
    ("**Approved**", "approved"),
    ("Approved (post-merge)", "approved"),
    ("Approved!", "approved"),  # div: exact-set members rejected the `!`
    ("Approved with nits", "approved"),  # div: trailing words, no parens
    ("Approved - see below", "approved"),  # div
    ("ChangesRequested", "changesrequested"),
    ("changesrequested", "changesrequested"),
    ("**ChangesRequested**", "changesrequested"),
    ("ChangesRequested.", "changesrequested"),  # div: trailing period
    ("Changes Requested", "changesrequested"),
    ("Changes REQUESTED", "changesrequested"),
    ("Changes  Requested", "changesrequested"),  # div: double space
    ("**Changes** Requested", "changesrequested"),  # div: inner bolding
    ("Changes", "changesrequested"),  # div: THE crux row
    ("changes", "changesrequested"),  # div
    ("Changes needed", "changesrequested"),  # div
    ("Request", "request"),
    ("Reply", "reply"),
    ("Replied", "reply"),
    ("Pending", ""),
    ("Maybe", ""),
    ("Not Approved", ""),
)

_VERDICT_KINDS = frozenset({"approved", "changesrequested"})


class AgreementMatrixTests(unittest.TestCase):
    """One classifier, so every consumer gives the same answer on every row.

    A future divergence is a FAILURE here rather than a discovery in a merge
    thread six weeks later (main#1371 acceptance criterion 3).
    """

    def test_format_gate_verdict_scope_matches_the_counter(self) -> None:
        """`_direction_is_verdict` gates the Requestor/Requestee swap check;
        `_is_verdict` decides what the merge gate treats as a verdict. A gate
        narrower than the consumer it guards is the #1150 defect class — and
        pre-fix these two disagreed on 9 of the 25 rows below.
        """
        for value, kind in SPELLINGS:
            with self.subTest(value=value):
                self.assertEqual(
                    fmt._direction_is_verdict(_body(value)),
                    counting._is_verdict(value),
                    f"format gate and counting gate disagree on {value!r}",
                )
                self.assertEqual(
                    counting._is_verdict(value),
                    kind in _VERDICT_KINDS,
                    f"counting gate disagrees with the shared classifier on {value!r}",
                )

    def test_changes_requested_predicate_matches_trust_signals(self) -> None:
        """The blocking question, asked by the conditional-field gate
        (main#1363) and by `trust_signals`' retraction/attribution gating."""
        for value, kind in SPELLINGS:
            with self.subTest(value=value):
                self.assertEqual(
                    fmt._direction_is_changes_requested(_body(value)),
                    ts._is_changes_requested(value),
                    f"format gate and trust_signals disagree on {value!r}",
                )
                self.assertEqual(
                    ts._is_changes_requested(value),
                    kind == "changesrequested",
                    f"trust_signals disagrees with the shared classifier on {value!r}",
                )

    def test_approved_predicate_matches_the_shared_classifier(self) -> None:
        """`_is_approved` is the 2-reviewer threshold's whole input."""
        for value, kind in SPELLINGS:
            with self.subTest(value=value):
                self.assertEqual(
                    counting._is_approved(value),
                    kind == "approved",
                    f"approver set disagrees with the shared classifier on {value!r}",
                )

    def test_bare_changes_is_the_same_answer_everywhere(self) -> None:
        """The crux row, called out on its own so a regression names itself.

        Pre-fix: `_is_verdict("Changes")` True, `_direction_is_changes_requested`
        True, `_direction_is_verdict` False. A bare-`Changes` verdict was
        simultaneously a blocking ChangesRequested (so `Retracted:` was allowed
        on it) and not-a-verdict (so the swap check never ran on it).
        """
        for value in ("Changes", "changes", "**Changes**"):
            with self.subTest(value=value):
                self.assertTrue(counting._is_verdict(value))
                self.assertTrue(ts._is_changes_requested(value))
                self.assertTrue(fmt._direction_is_changes_requested(_body(value)))
                self.assertTrue(
                    fmt._direction_is_verdict(_body(value)),
                    "bare `Changes` is a ChangesRequested verdict to the counter, so the "
                    "swap gate must apply to it too",
                )
                self.assertFalse(counting._is_approved(value))


class SwapGateReadsTheValueTheCounterReadsTests(unittest.TestCase):
    """The extraction axis: same vocabulary, different text, opposite answers.

    `_direction_is_verdict` read the FIRST raw `RequestOrReplied:` hit anywhere
    in the body. A reviewer who quotes or narrates an earlier direction above
    their trailer therefore had the swap heuristic decided by their prose.
    #934 fixed precisely this for `Requestor:` in this hook ("the swap
    heuristic must read the Requestor the COUNTING hook reads — never the
    first `re.search` hit over the whole body") and left `RequestOrReplied:`
    on the raw first match.
    """

    BRANCH: ClassVar[str] = "L.Ferreira/1371-x"

    @staticmethod
    def _cmd(body: str) -> str:
        return "gh pr comment 42 --repo noorinalabs/noorinalabs-main --body '" + body + "'"

    def _check(self, body: str):
        with mock.patch.object(fmt, "get_branch_name", return_value=self.BRANCH):
            return fmt.check(_test_helpers.bash_input(self._cmd(body)))

    # -- fail-OPEN: prose above the trailer suppressed the swap check -------- #

    _PROSE_REPLY_ABOVE_APPROVED_TRAILER = (
        "Earlier in this thread I posted RequestOrReplied: Reply and never "
        "followed up. Doing so now.\n\n"
        "---\n"
        "Requestor: Lucas Ferreira\n"
        "Requestee: Santiago Ferreira\n"
        "RequestOrReplied: Approved\n"
        "TechDebt: none\n"
    )

    def test_prose_direction_no_longer_suppresses_the_swap_block(self) -> None:
        """Requestor IS the branch author — a genuine swap — and pre-fix it was
        ALLOWED, because the first `RequestOrReplied:` hit was the prose
        `Reply` and the verdict-scope gate returned early.

        The counter reads the trailer's `Approved`, counts the comment as a
        verdict, and self-review-excludes the swapped Requestor — so the real
        reviewer's approval lands under the author's name and evaporates. That
        is the #932 uncountable-verdict shape, reached through the one gate
        that exists to catch it.
        """
        result = self._check(self._PROSE_REPLY_ABOVE_APPROVED_TRAILER)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.get("decision"), "block")
        self.assertIn("swapped", result.get("reason", ""))

    # -- fail-CLOSED: prose above a genuinely out-of-scope trailer ----------- #

    _PROSE_APPROVED_ABOVE_REPLY_TRAILER = (
        "You asked whether I would post RequestOrReplied: Approved here — not "
        "yet, this is only a reply.\n\n"
        "---\n"
        "Requestor: Lucas Ferreira\n"
        "Requestee: Santiago Ferreira\n"
        "RequestOrReplied: Reply\n"
        "TechDebt: none\n"
    )

    def test_prose_verdict_no_longer_drags_a_reply_into_scope(self) -> None:
        """The mirror image: a Reply trailer whose prose mentions `Approved`.

        Request/Reply invert the Direction table's role bindings (#378), so the
        swap heuristic is unsound there — Requestor IS the PR author by
        definition. Pre-fix the prose hit dragged this into verdict scope and
        the hook BLOCKED a correctly-formed reply.
        """
        self.assertIsNone(self._check(self._PROSE_APPROVED_ABOVE_REPLY_TRAILER))

    def test_fenced_example_no_longer_decides_the_direction(self) -> None:
        """A reviewer documenting the charter template inside a fence.

        `extract_charter_field` strips code regions (main#1359/#1361); the raw
        `re.search` did not, so the fenced example's direction won.
        """
        body = (
            "The template is:\n\n"
            "```\n"
            "Requestor: <reviewer>\n"
            "RequestOrReplied: Reply\n"
            "```\n\n"
            "---\n"
            "Requestor: Lucas Ferreira\n"
            "Requestee: Santiago Ferreira\n"
            "RequestOrReplied: Approved\n"
            "TechDebt: none\n"
        )
        result = self._check(body)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.get("decision"), "block")


class ConditionalFieldGateFollowsTrustSignalsTests(unittest.TestCase):
    """The `Retracted:` / `OrchestratorCaused:` gate vs. the consumer it guards.

    main#1363 reconciled this gate's VOCABULARY with `trust_signals`. It did
    not reconcile the EXTRACTION, and the gate read the first raw
    `RequestOrReplied:` hit anywhere in the body while `trust_signals` reads a
    line-anchored (`^…$`) first match — so a reviewer merely MENTIONING a
    direction mid-sentence flipped the gate and not the consumer.
    """

    @staticmethod
    def _cmd(body: str) -> str:
        return "gh pr comment 42 --repo noorinalabs/noorinalabs-main --body '" + body + "'"

    def _check(self, body: str):
        with mock.patch.object(fmt, "get_branch_name", return_value="A.Virtanen/1371-x"):
            return fmt.check(_test_helpers.bash_input(self._cmd(body)))

    _PROSE_MENTION_ABOVE_A_RETRACTING_TRAILER = (
        "You asked whether I would post RequestOrReplied: Approved here — not "
        "yet; my must-fix was wrong and I am withdrawing it.\n\n"
        "---\n"
        "Requestor: Nadia Khoury\n"
        "Requestee: Aino Virtanen\n"
        "RequestOrReplied: ChangesRequested\n"
        "TechDebt: none\n"
        "Retracted: my finding was wrong.\n"
    )

    def test_prose_mention_no_longer_false_blocks_a_retraction(self) -> None:
        """Pre-fix this BLOCKED, saying `Retracted:` is "only meaningful on a
        ChangesRequested verdict" about a comment whose verdict IS
        ChangesRequested — and whose retraction `trust_signals` honours.

        `parse_verdicts` is unaffected by the prose (its regex is line-anchored,
        so a mid-sentence mention is not a field) and returns
        `false_positive=True`. The gate now agrees.
        """
        self.assertTrue(
            ts.parse_verdicts([self._PROSE_MENTION_ABOVE_A_RETRACTING_TRAILER])[0].false_positive,
            "instrument check: trust_signals must honour this retraction, or the "
            "assertion below proves nothing",
        )
        self.assertIsNone(self._check(self._PROSE_MENTION_ABOVE_A_RETRACTING_TRAILER))

    _LINE_ANCHORED_MENTION_ABOVE_A_RETRACTING_TRAILER = (
        "RequestOrReplied: Approved\n\nwas my earlier call; I am withdrawing "
        "the must-fix I raised after it.\n\n"
        "---\n"
        "Requestor: Nadia Khoury\n"
        "Requestee: Aino Virtanen\n"
        "RequestOrReplied: ChangesRequested\n"
        "TechDebt: none\n"
        "Retracted: my finding was wrong.\n"
    )

    def test_line_anchored_mention_is_the_known_residual_divergence(self) -> None:
        """The shape where the gate and its consumer still disagree — PINNED
        so it is a documented residual, not a latent surprise (main#1371).

        `trust_signals._FIELD_RE["verdict"]` is line-anchored over the RAW
        body and first-match, so it reads the stray line and silently drops
        the retraction. The gate reads the trailer and stays quiet. Nothing
        merges wrongly — the author simply is not warned that their
        `Retracted:` will be ignored.

        The repair is `trust_signals` routing through
        `charter_trailer.extract_charter_field` (#932/#934's declared single
        source of truth for field extraction), which is the same axis main#1372
        owns for the presence pair. When that lands, THIS TEST MUST FLIP: the
        `assertFalse` becomes `assertTrue` and the gate's silence becomes
        correct rather than merely harmless.
        """
        body = self._LINE_ANCHORED_MENTION_ABOVE_A_RETRACTING_TRAILER
        self.assertFalse(
            ts.parse_verdicts([body])[0].false_positive,
            "trust_signals now honours this retraction — the divergence is gone, "
            "so flip this test rather than deleting it",
        )
        self.assertIsNone(self._check(body))


class PredicateSingularityTests(unittest.TestCase):
    """No local pattern set, no local algorithm — the predicates ARE the shared ones."""

    def test_counting_hook_predicates_are_the_shared_objects(self) -> None:
        self.assertIs(counting._is_verdict, ct.is_verdict_direction)
        self.assertIs(counting._is_approved, ct.is_approved)

    def test_format_hook_has_no_private_direction_table(self) -> None:
        self.assertFalse(
            hasattr(fmt, "_VERDICT_DIRECTIONS"),
            "the frozenset was the fourth copy — it must not come back",
        )

    def test_counting_hook_has_no_private_verdict_table(self) -> None:
        self.assertFalse(
            hasattr(counting, "_VERDICT_REQUIRING_TECH_DEBT"),
            "the exact-match set was the third copy — it must not come back",
        )

    def test_trust_signals_uses_the_named_predicate(self) -> None:
        self.assertIs(ts._is_changes_requested, ct.is_changes_requested)

    def test_include_bare_changes_is_only_load_bearing_for_changesrequested(self) -> None:
        """`is_approved` takes no `include_bare_changes` knob, and provably
        needs none: bare `Changes` can never classify as approved either way.

        This is why the consolidation has TWO questions and not three.
        """
        for value, _kind in SPELLINGS:
            with self.subTest(value=value):
                self.assertEqual(
                    ct.verdict_kind(value, include_bare_changes=True) == "approved",
                    ct.verdict_kind(value, include_bare_changes=False) == "approved",
                )


if __name__ == "__main__":
    unittest.main()
