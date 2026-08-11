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


class FenceOpenerMustStartALineTests(unittest.TestCase):
    """main#1359 merge-gate review (Aino Virtanen — MF4): a fence marker that
    does not open a line must NOT be treated as a fence at all, per
    CommonMark (a code-fence opener is defined as a leading sequence on its
    own line, optional indent aside — a marker occurring mid-sentence is
    just prose).

    Why this matters here specifically: before this fix, adding `~~~` to
    `_FENCE_MARKERS` (main#1359) gave a mid-prose, unpaired tilde run a
    SECOND path to the same failure mode the backtick marker already had —
    an odd/unpaired marker anywhere in prose above a trailer is read as an
    "unterminated fence" and strips to end-of-body, taking the real `---`
    separator and the whole trailer with it. Live trace: this exact PR's own
    review thread — a reviewer's comment discussing the fence marker being
    widened by this PR tripped the marker three times in prose, the third
    occurrence unpaired, and the reviewer's own verdict trailer was erased.

    EVERY assertion in `test_unpaired_fence_marker_in_prose_no_longer_erases_the_trailer`
    below FAILS at PR head `a4909f2` (verified directly — three fields
    resolved to `None` where they should have resolved to real values) and
    passes once the fence opener is line-anchored.
    """

    def test_unpaired_fence_marker_in_prose_no_longer_erases_the_trailer(self) -> None:
        body = (
            "Point A discusses the fence marker once.\n\n"
            "Point B discusses the fence marker a second time.\n\n"
            "Point C discusses the fence marker a third time (odd count).\n\n"
            "---\n"
            "Requestor: Nino Kavtaradze\n"
            "Requestee: Santiago Ferreira\n"
            "RequestOrReplied: Approved\n"
            "TechDebt: none\n"
        ).replace("the fence marker", "the ~~~ fence marker")
        self.assertEqual(extract_charter_field("Requestor", body), "Nino Kavtaradze")
        self.assertEqual(extract_charter_field("Requestee", body), "Santiago Ferreira")
        self.assertEqual(extract_charter_field("RequestOrReplied", body), "Approved")
        self.assertEqual(extract_charter_field("TechDebt", body), "none")

    def test_unpaired_backtick_run_in_prose_also_no_longer_erases_the_trailer(self) -> None:
        """The identical hazard already existed for the backtick marker
        before main#1359 (main#1413's root cause) — the line-anchoring fix
        closes it for BOTH markers, not just the one this PR added."""
        body = (
            "Discussing the marker once, mid-sentence: ``` looks like this.\n\n"
            "Discussing it again: ``` and a third time: ``` (odd count).\n\n"
            "---\n"
            "Requestor: Nino Kavtaradze\n"
            "RequestOrReplied: Approved\n"
        )
        self.assertEqual(extract_charter_field("Requestor", body), "Nino Kavtaradze")
        self.assertEqual(extract_charter_field("RequestOrReplied", body), "Approved")

    def test_line_start_fence_still_strips_a_genuine_block(self) -> None:
        """Regression guard: a REAL fence — marker at the start of a line —
        must still be recognized and stripped. Only mid-line occurrences
        stop counting as fence openers."""
        body = "before\n~~~\nRequestor: Ghost\n~~~\nafter"
        self.assertNotIn("Requestor", strip_code_regions(body))

    def test_fence_at_the_very_start_of_the_body_still_strips(self) -> None:
        """Position 0 has no preceding newline but IS the start of a line."""
        body = "~~~\nRequestor: Ghost\n~~~\nafter"
        self.assertNotIn("Requestor", strip_code_regions(body))

    def test_the_flagged_pre_existing_fixture_shape_is_now_prose(self) -> None:
        """`test_validate_pr_review.py::StripCodeRegionsTests
        ::test_unterminated_fenced_block_strips_rest` used a mid-line opener
        (`"intro ```\\nRequestor: foo"`) — CommonMark would not treat that as
        a fence either, so its old expectation (eats the rest) is no longer
        correct; it now passes the marker through as literal prose. That
        fixture is updated in the same change as this one."""
        body = "intro ```\nRequestor: foo"
        result = strip_code_regions(body)
        self.assertIn("Requestor: foo", result)


class FenceOpenerAllowsBlockquoteAndIndentTests(unittest.TestCase):
    """main#1359 merge-gate review round 3 (Aino Virtanen / coordinator —
    MF5): the MF4 fix (`i == 0 or body[i - 1] == "\\n"`) demanded column 0
    EXACTLY. CommonMark allows a code-fence opener up to 3 leading spaces of
    indentation, and (GFM) inside a blockquote container's `>` prefix. The
    over-strict anchor rejected BOTH real-world shapes as fence openers,
    which is a FAIL-OPEN, not the fail-closed direction MF4 fixed:

    A body with the real trailer FIRST, followed by a blockquoted or
    indented fenced block containing a FABRICATED `Requestor:` line, used to
    have that fabrication safely stripped (base, and PR head before MF4).
    After the MF4 fix alone, an indented or blockquoted fence opener is no
    longer recognised as a fence at all, so it is NOT stripped, and
    last-match-wins hands `extract_charter_field` the fabricated name
    instead of the real one — a spoofed reviewer identity reaching the
    merge gate.

    Every assertion below FAILS at head `975be2a` (verified directly before
    writing this fix: both the blockquoted and 2-space-indented shapes
    return the fabricated `"Fake Impostor"` instead of `"Real Reviewer"`)
    and passes once the fence-opener check accepts a blockquote/indent
    prefix.
    """

    @staticmethod
    def _spoofed_body(prefix: str) -> str:
        fence = f"{prefix}```"
        return (
            "---\n"
            "Requestor: Real Reviewer\n"
            "Requestee: Santiago Ferreira\n"
            "RequestOrReplied: Approved\n"
            "TechDebt: none\n\n"
            f"{fence}\n"
            "Requestor: Fake Impostor\n"
            f"{fence}\n"
        )

    def test_blockquoted_fence_below_the_trailer_is_still_stripped(self) -> None:
        """GitHub's "Quote reply" button emits exactly this shape — no
        adversary required, an ordinary reviewer quoting an earlier comment
        produces it by accident."""
        body = self._spoofed_body("> ")
        self.assertEqual(extract_charter_field("Requestor", body), "Real Reviewer")

    def test_two_space_indented_fence_below_the_trailer_is_still_stripped(self) -> None:
        body = self._spoofed_body("  ")
        self.assertEqual(extract_charter_field("Requestor", body), "Real Reviewer")

    def test_three_space_indented_fence_below_the_trailer_is_still_stripped(self) -> None:
        """CommonMark's indentation ceiling for a fence is 3 spaces — the
        boundary case."""
        body = self._spoofed_body("   ")
        self.assertEqual(extract_charter_field("Requestor", body), "Real Reviewer")

    def test_nested_blockquote_fence_below_the_trailer_is_still_stripped(self) -> None:
        body = self._spoofed_body("> > ")
        self.assertEqual(extract_charter_field("Requestor", body), "Real Reviewer")

    def test_tilde_marker_blockquoted_below_the_trailer_is_still_stripped(self) -> None:
        """Both markers, not just the backtick one — MF4's own fix applied
        to both, this must too."""
        body = (
            "---\n"
            "Requestor: Real Reviewer\n"
            "RequestOrReplied: Approved\n\n"
            "> ~~~\n"
            "Requestor: Fake Impostor\n"
            "> ~~~\n"
        )
        self.assertEqual(extract_charter_field("Requestor", body), "Real Reviewer")

    def test_mid_sentence_marker_is_still_prose_not_a_fence(self) -> None:
        """Regression guard for MF4: a marker prefixed by ordinary prose
        text (not blockquote markers or pure whitespace) must still fail to
        qualify as a fence opener."""
        body = (
            "Point A discusses the fence marker once.\n\n"
            "Point B discusses the fence marker a second time.\n\n"
            "Point C discusses the fence marker a third time (odd count).\n\n"
            "---\n"
            "Requestor: Nino Kavtaradze\n"
            "RequestOrReplied: Approved\n"
        ).replace("the fence marker", "the ~~~ fence marker")
        self.assertEqual(extract_charter_field("Requestor", body), "Nino Kavtaradze")


class FenceOpenerIndentationIsUnboundedTests(unittest.TestCase):
    """main#1359 merge-gate review round 4 (coordinator's fuller matrix —
    MF6): MF5's fix capped accepted indentation at 3 spaces, mirroring
    CommonMark's fence-vs-indented-code-block boundary. That boundary
    answers a DIFFERENT question than the one `strip_code_regions` needs
    answered.

    CommonMark cares whether a 4+-space-indented marker is a FENCE (a
    delimited code region) or an INDENTED CODE BLOCK (a different code
    construct, delimited by indentation alone). Both are still CODE. This
    stripper's only job is "is this a code region a reviewer deliberately
    marked off" — and once someone types a paired opening/closing marker on
    its own line, indented by any amount, that intent is unambiguous
    regardless of which CommonMark construct a renderer would call it.

    Capping at 3 broke that: a marker preceded ONLY by 4+ spaces of
    indentation (nothing else — still disqualified if preceded by real
    prose text, per MF4) failed the fence-opener check, so its contents
    fell through to being read as literal prose. A fabricated field inside
    a 4-space-indented, well-paired marker block placed BELOW a real
    trailer therefore won last-match-wins — a regression from BASE for the
    backtick marker specifically:

        BASE Requestor:  'Real Reviewer'   (any position was a valid opener)
        HEAD Requestor:  'Fake Impostor'   (4+ spaces disqualified, MF5 head)

    The identical shape with the tilde marker spoofs on BOTH base and the
    MF5 head — tilde was never a recognised marker at all pre-main#1359, so
    this is a PRE-EXISTING hole this fix additionally closes as a bonus,
    not a regression main#1359 introduced.

    Fix: the fence-opener prefix check no longer caps indentation at 3 —
    any amount of leading whitespace (plus optional blockquote nesting) in
    front of the marker still qualifies, as long as nothing else precedes
    it on the line. This is a deliberate, acknowledged DIVERGENCE from
    CommonMark's own fence-opener rule (which is capped at 3) — CommonMark
    would call a 4+-space marker an INDENTED CODE BLOCK rather than a
    FENCE, but this stripper does not implement that distinction and does
    not need to for its own purpose (stripping deliberately-marked-off code
    regions). What this fix does NOT do is give `strip_code_regions` general
    indented-code-block recognition — an indented block with NO triple
    marker at all (plain 4+-space-indented text, no `` ``` `` / `~~~` in
    sight) is still never stripped by this function, before or after this
    change. That broader, marker-independent gap is filed separately as
    main#1416, out of scope here — this fix closes only the marker-present
    case the regression above describes.

    Every assertion below FAILS at head `2b95706` (verified directly before
    writing this fix) and passes once the cap is removed.
    """

    @staticmethod
    def _spoofed_body(prefix: str, marker: str) -> str:
        fence = f"{prefix}{marker}"
        return (
            "---\n"
            "Requestor: Real Reviewer\n"
            "Requestee: Santiago Ferreira\n"
            "RequestOrReplied: Approved\n"
            "TechDebt: none\n\n"
            f"{fence}\n"
            "Requestor: Fake Impostor\n"
            f"{fence}\n"
        )

    def test_four_space_indented_backtick_fence_is_stripped(self) -> None:
        """The regression: safe on base, spoofable at the MF5 head."""
        body = self._spoofed_body("    ", "```")
        self.assertEqual(extract_charter_field("Requestor", body), "Real Reviewer")

    def test_four_space_indented_tilde_fence_is_stripped(self) -> None:
        """The pre-existing hole (unsafe on base too, tilde never recognized
        pre-main#1359) that this same fix additionally closes."""
        body = self._spoofed_body("    ", "~~~")
        self.assertEqual(extract_charter_field("Requestor", body), "Real Reviewer")

    def test_deeply_indented_backtick_fence_is_still_stripped(self) -> None:
        """Indentation is UNBOUNDED now, not merely raised to a new cap —
        8 spaces, well past any CommonMark construct's own ceiling."""
        body = self._spoofed_body(" " * 8, "```")
        self.assertEqual(extract_charter_field("Requestor", body), "Real Reviewer")

    def test_indented_blockquoted_fence_is_still_stripped(self) -> None:
        """Blockquote nesting composed with indentation past the old cap."""
        body = self._spoofed_body(">     ", "```")
        self.assertEqual(extract_charter_field("Requestor", body), "Real Reviewer")

    def test_mid_sentence_marker_is_still_not_a_fence_opener(self) -> None:
        """Regression guard: removing the indentation CAP must not also
        remove the requirement that NOTHING but whitespace/blockquote
        markers precede the opener — prose text still disqualifies it,
        regardless of how it is indented."""
        body = (
            "    Point A discusses the fence marker, indented as prose.\n\n"
            "---\n"
            "Requestor: Nino Kavtaradze\n"
            "RequestOrReplied: Approved\n"
        ).replace("the fence marker", "the ~~~ fence marker")
        self.assertEqual(extract_charter_field("Requestor", body), "Nino Kavtaradze")


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
