#!/usr/bin/env python3
"""Tests for `charter_trailer`'s code-region stripping and verdict-kind
vocabulary (main#1359, main#1361).

Two things this file exists to pin, both already-happened divergences, not
hypothetical ones:

1. `strip_code_regions` used to strip ```` ``` ```` fences but not `~~~`
   fences, while `trust_signals._strip_code_markup` (a private, now-deleted
   copy of the same concept) stripped both. Because `validate_pr_review`
   aliases `strip_code_regions` directly for its verdict-counting loop, the
   gap was reachable from the merge gate (main#1361): a `~~~`-fenced trailer
   *example*, with no real `---` trailer, parsed as a genuine verdict.
2. The verdict-kind classification (`RequestOrReplied:` value -> canonical
   kind) was implemented three times across `trust_signals.py`,
   `validate_pr_review.py`, and `validate_review_comment_format.py`, and the
   three implementations disagree with each other on the bare `Changes`
   spelling and on trailing-text tolerance (`Approved (post-merge)`) —
   verified directly against the pre-#1359 tree, see
   `VerdictKindMatchesPreExtractionTrustSignalsTests` below.

Run: python3 -m pytest .claude/lib/tests/test_charter_trailer.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_LIB_DIR))

from charter_trailer import (  # noqa: E402
    VERDICT_KIND,
    extract_charter_field,
    normalize_verdict_token,
    strip_code_regions,
    verdict_kind,
)


class StripCodeRegionsBacktickFenceTests(unittest.TestCase):
    """Pre-existing ```` ``` ```` behaviour — regression guard, not new."""

    def test_fenced_block_is_stripped(self) -> None:
        body = "before\n```\nRequestor: Ghost\n```\nafter"
        self.assertNotIn("Requestor", strip_code_regions(body))

    def test_inline_code_is_stripped(self) -> None:
        result = strip_code_regions("see `Requestor: foo` for context")
        self.assertNotIn("Requestor", result)

    def test_unterminated_fence_strips_rest_of_body(self) -> None:
        result = strip_code_regions("before\n```\nunterminated forever")
        self.assertNotIn("unterminated", result)

    def test_char_offsets_preserved(self) -> None:
        """Same total length, so content AFTER a fence keeps its original
        char offset (the docstring's "line/column arithmetic remains
        accurate" claim) — the fenced SPAN itself is flattened to one run of
        spaces, including its interior newlines, which is what stops a `---`
        that happens to sit inside a fence from surviving as its own line."""
        body = "line1\n```\ncode\n```\nline5"
        result = strip_code_regions(body)
        self.assertEqual(len(body), len(result))
        self.assertTrue(result.endswith("line5"))


class StripCodeRegionsTildeFenceTests(unittest.TestCase):
    """main#1359/#1361: the divergence, reproduced and closed.

    Every assertion below FAILS against the pre-#1359 `strip_code_regions`
    (verified directly — see the class docstring on
    `TildeFenceDivergenceTests` in `test_trust_signals.py` for the paired
    `git stash` verification of the trust_signals side of this same gap).
    """

    def test_fenced_block_is_stripped(self) -> None:
        body = "before\n~~~\nRequestor: Ghost\n~~~\nafter"
        self.assertNotIn("Requestor", strip_code_regions(body))

    def test_unterminated_fence_strips_rest_of_body(self) -> None:
        result = strip_code_regions("before\n~~~\nunterminated forever")
        self.assertNotIn("unterminated", result)

    def test_char_offsets_preserved(self) -> None:
        body = "line1\n~~~\ncode\n~~~\nline5"
        result = strip_code_regions(body)
        self.assertEqual(len(body), len(result))
        self.assertTrue(result.endswith("line5"))

    def test_mixed_fence_styles_both_stripped(self) -> None:
        body = "```\nbacktick Requestor: A\n```\ntext\n~~~\ntilde Requestor: B\n~~~\n"
        result = strip_code_regions(body)
        self.assertNotIn("Requestor", result)
        self.assertIn("text", result)

    def test_tilde_fenced_trailer_example_with_no_real_trailer_extracts_nothing(self) -> None:
        """main#1361's exact repro, run against the shared function directly."""
        body = (
            "Here is the format reviewers should use:\n\n"
            "~~~\n"
            "Requestor: Ghost Reviewer\n"
            "Requestee: PR Author\n"
            "RequestOrReplied: Approved\n"
            "TechDebt: none\n"
            "~~~\n\n"
            "I have not reviewed this yet.\n"
        )
        self.assertIsNone(extract_charter_field("Requestor", body))
        self.assertIsNone(extract_charter_field("RequestOrReplied", body))
        self.assertIsNone(extract_charter_field("TechDebt", body))


class NormalizeVerdictTokenTests(unittest.TestCase):
    def test_casefolds(self) -> None:
        self.assertEqual(normalize_verdict_token("ChangesRequested"), "changesrequested")

    def test_strips_non_alnum(self) -> None:
        self.assertEqual(normalize_verdict_token("**ChangesRequested"), "changesrequested")

    def test_strips_trailing_punctuation(self) -> None:
        self.assertEqual(normalize_verdict_token("Approved!"), "approved")


class VerdictKindTests(unittest.TestCase):
    def test_approved(self) -> None:
        self.assertEqual(verdict_kind("Approved"), "approved")

    def test_changesrequested_one_word(self) -> None:
        self.assertEqual(verdict_kind("ChangesRequested"), "changesrequested")

    def test_changes_requested_spaced(self) -> None:
        self.assertEqual(verdict_kind("Changes Requested"), "changesrequested")

    def test_request(self) -> None:
        self.assertEqual(verdict_kind("Request"), "request")

    def test_reply(self) -> None:
        self.assertEqual(verdict_kind("Reply"), "reply")

    def test_replied(self) -> None:
        self.assertEqual(verdict_kind("Replied"), "reply")

    def test_none_value(self) -> None:
        self.assertEqual(verdict_kind(None), "")

    def test_empty_value(self) -> None:
        self.assertEqual(verdict_kind(""), "")

    def test_unrecognized_value(self) -> None:
        self.assertEqual(verdict_kind("Pending"), "")

    def test_trailing_text_does_not_defeat_the_match(self) -> None:
        """`Approved (post-merge)` must still classify as approved — only the
        FIRST token is classified.

        NOTE (main#1359 merge-gate review, Aino Virtanen — MF1): an earlier
        draft of this docstring claimed `validate_pr_review._is_verdict`
        rejects this exact input. That claim was wrong and has been
        retracted (see main#1371): `_is_verdict` is only ever called on
        `extract_charter_field`'s output, which already strips the trailing
        parenthetical before `_is_verdict` ever sees it, so end-to-end there
        is no divergence on `"Approved (post-merge)"` specifically. The
        genuinely reachable divergences — `"Approved!"`,
        `"Approved with nits"`, `"Approved - see below"`,
        `"Changes  Requested"` (double space), `"Changes needed"` — are all
        `False` under `validate_pr_review._is_verdict`/`._is_approved` today
        and would become `True` under this function; see
        `main#1371` for the full table and the `_is_approved` /
        2-reviewer-approver-set consequence.
        """
        self.assertEqual(verdict_kind("Approved (post-merge)"), "approved")

    def test_bold_markers_do_not_defeat_the_match(self) -> None:
        self.assertEqual(verdict_kind("**ChangesRequested**"), "changesrequested")

    # -- The deliberate divergence (main#1371): bare "Changes" -- #

    def test_bare_changes_included_by_default(self) -> None:
        """Default matches `trust_signals`'s pre-migration behaviour and
        `validate_pr_review._VERDICT_REQUIRING_TECH_DEBT` (both include it)."""
        self.assertEqual(verdict_kind("Changes"), "changesrequested")

    def test_bare_changes_included_when_requested_explicitly(self) -> None:
        self.assertEqual(verdict_kind("Changes", include_bare_changes=True), "changesrequested")

    def test_bare_changes_excluded_when_requested(self) -> None:
        """Matches `validate_review_comment_format._VERDICT_DIRECTIONS`, which
        deliberately excludes the bare form ("not a verdict on its own")."""
        self.assertEqual(verdict_kind("Changes", include_bare_changes=False), "")

    def test_exclusion_does_not_affect_the_full_spelling(self) -> None:
        """`include_bare_changes=False` narrows ONLY the bare token — the
        one-word and spaced forms still classify either way."""
        self.assertEqual(
            verdict_kind("ChangesRequested", include_bare_changes=False), "changesrequested"
        )
        self.assertEqual(
            verdict_kind("Changes Requested", include_bare_changes=False), "changesrequested"
        )

    def test_vocabulary_table_is_the_public_api(self) -> None:
        self.assertEqual(
            VERDICT_KIND,
            {
                "approved": "approved",
                "changesrequested": "changesrequested",
                "changes": "changesrequested",
                "request": "request",
                "reply": "reply",
                "replied": "reply",
            },
        )


class VerdictKindMatchesPreExtractionTrustSignalsTests(unittest.TestCase):
    """`verdict_kind(..., include_bare_changes=True)` must reproduce every
    answer the pre-#1359 `trust_signals._verdict_kind` gave, on the exact
    inputs verified against that tree (`git stash` repro, see PR body) —
    a parity guard for the one call site (`trust_signals.py`) this issue
    fully migrates.
    """

    _PRE_FIX_TRUST_SIGNALS_ANSWERS = {
        "Changes": "changesrequested",
        "ChangesRequested": "changesrequested",
        "Changes Requested": "changesrequested",
        "Approved (post-merge)": "approved",
        "Approved": "approved",
        "Request": "request",
        "Reply": "reply",
        "Replied": "reply",
    }

    def test_matches_pre_fix_trust_signals_on_every_verified_input(self) -> None:
        for value, expected in self._PRE_FIX_TRUST_SIGNALS_ANSWERS.items():
            with self.subTest(value=value):
                self.assertEqual(verdict_kind(value, include_bare_changes=True), expected)


if __name__ == "__main__":
    unittest.main()
