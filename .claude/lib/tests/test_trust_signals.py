"""Tests for trust_signals — per-engineer mechanical trust signals + the
evidence-anchored scoring model (main#842, persona Option B §4b / Finding D).

Covers:
  * Extraction maps author identity (commit author) → prs_merged / ci_red /
    rework, and reviewer identity (Requestor field) → must_fix_caught, reusing
    wave_status.merged_prs with its no-shell list-arg-vector contract.
  * Verdict parsing accepts bare AND bold Requestor/RequestOrReplied forms,
    tolerates all three ChangesRequested spellings (main#1347), and detects
    self-marked false-positives via the explicit `Retracted:` field, never
    free-text substring matching (main#1348).
  * score_delta is bidirectional and clamped to [-2, +2], and its rework
    signal is the two-band, rate-relative rule of main#1349 (clean bar at
    1 must-fix/PR, penalty bar at 2/PR, neutral band between) rather than the
    pre-#1349 absolute thresholds.
  * decay drifts unsignalled scores one step toward NEUTRAL after N waves.
  * distribution discipline reserves 5 for the top relative performer.
  * the forced negative-signal pass bans bare "None".
  * the performance-triggered retirement trigger fires on sustained bottom-tier
    or repeated CI-red merges, and not before K waves of evidence.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock

# Helper lives at .claude/lib/trust_signals.py; this test is at
# .claude/lib/tests/test_*.py. parent.parent reaches the lib root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import charter_trailer as ct  # noqa: E402
import trust_signals as ts  # noqa: E402
import wave_status  # noqa: E402

_REPOS = ["noorinalabs-isnad-graph", "noorinalabs-user-service"]


def _verdict(requestor: str, requestee: str, verdict: str, *, bold: bool = False) -> str:
    if bold:
        return (
            f"**Requestor:** {requestor}\n"
            f"**Requestee:** {requestee}\n"
            f"**RequestOrReplied:** {verdict}\n"
        )
    return f"Requestor: {requestor}\nRequestee: {requestee}\nRequestOrReplied: {verdict}\n"


class _FakeGh:
    """subprocess.run side_effect emulating the gh calls trust_signals makes,
    driven by a flat PR fixture. Each PR dict carries: repo, number, sha,
    mergedAt, commit_author, comments (list of bodies), ci_red (bool)."""

    def __init__(self, prs: list[dict]) -> None:
        self.prs = prs
        self.calls: list[list[str]] = []

    def __call__(self, cmd, *args, **kwargs):  # noqa: ANN001
        assert isinstance(cmd, list), f"gh called with non-list cmd: {cmd!r}"
        assert cmd[0] == "gh"
        assert kwargs.get("shell") is not True
        self.calls.append(cmd)

        if cmd[1:3] == ["pr", "list"]:
            repo = cmd[cmd.index("--repo") + 1].removeprefix("noorinalabs/")
            listed = [
                {
                    "number": p["number"],
                    "headRefOid": p["sha"],
                    "mergedAt": p["mergedAt"],
                    "author": {"login": "octocat"},
                }
                for p in self.prs
                if p["repo"] == repo
            ]
            return SimpleNamespace(stdout=json.dumps(listed), returncode=0, stderr="")

        if cmd[1:3] == ["pr", "view"]:
            number = int(cmd[3])
            p = next(x for x in self.prs if x["number"] == number)
            rollup = [{"conclusion": "FAILURE"}] if p.get("ci_red") else [{"conclusion": "SUCCESS"}]
            return SimpleNamespace(stdout=json.dumps(rollup), returncode=0, stderr="")

        if cmd[1] == "api":
            path = cmd[2]
            parts = path.split("/")
            if "/commits/" in path:
                sha = parts[4]
                name = next(p["commit_author"] for p in self.prs if p["sha"] == sha)
                return SimpleNamespace(stdout=name + "\n", returncode=0, stderr="")
            if path.endswith("/comments"):
                number = int(parts[4])
                bodies = next(p.get("comments", []) for p in self.prs if p["number"] == number)
                return SimpleNamespace(stdout=json.dumps(bodies), returncode=0, stderr="")

        raise AssertionError(f"unexpected gh call: {cmd!r}")


def _write_status(path: Path, *, repos: list[str], wave: str) -> None:
    path.write_text(
        json.dumps({"current_wave": int(wave), f"wave_{wave}_repos_in_scope": repos}) + "\n",
        encoding="utf-8",
    )


# --------------------------------------------------------------------------- #
# Verdict parsing (pure)
# --------------------------------------------------------------------------- #
class ParseVerdicts(unittest.TestCase):
    def test_bare_and_bold_forms(self) -> None:
        bodies = [
            _verdict("Aino Virtanen", "Nadia Khoury", "ChangesRequested"),
            _verdict("Santiago Ferreira", "Nadia Khoury", "Approved", bold=True),
            "just a normal comment, no verdict here",
        ]
        verdicts = ts.parse_verdicts(bodies)
        self.assertEqual(len(verdicts), 2)
        self.assertEqual(verdicts[0].requestor, "Aino Virtanen")
        self.assertEqual(verdicts[0].requestee, "Nadia Khoury")
        self.assertEqual(verdicts[0].verdict, "ChangesRequested")
        self.assertEqual(verdicts[1].requestor, "Santiago Ferreira")
        self.assertEqual(verdicts[1].verdict, "Approved")

    # -- Regression: main#1347 -- all three ChangesRequested spellings must
    # classify identically. `(\w+)` used to stop at the first space, so the
    # spaced form captured only "Changes" and silently fell out of every
    # counter (real evidence: main PR #1173, #1153).

    def test_three_changes_requested_spellings_classify_identically(self) -> None:
        for spelling in ("ChangesRequested", "Changes Requested", "Changes"):
            with self.subTest(spelling=spelling):
                self.assertTrue(ts._is_changes_requested(spelling))

    def test_spaced_changes_requested_verdict_field_captured_in_full(self) -> None:
        """The regex capture itself must not truncate at the first space."""
        body = _verdict("Nino Kavtaradze", "Aino Virtanen", "Changes Requested")
        v = ts.parse_verdicts([body])[0]
        self.assertEqual(v.verdict, "Changes Requested")
        self.assertTrue(ts._is_changes_requested(v.verdict))

    def test_trailing_text_after_approved_still_classifies_as_approved(self) -> None:
        """Widening the capture to a full line must not defeat the approved match."""
        body = _verdict("Aino Virtanen", "Nadia Khoury", "Approved (post-merge)")
        v = ts.parse_verdicts([body])[0]
        self.assertEqual(ct.verdict_kind(v.verdict, include_bare_changes=True), "approved")

    # -- Regression: main#1348 -- `review_false_positives` is gated on an
    # explicit `Retracted:` field, never free-text substring matching. A word
    # match cannot distinguish a genuine self-retraction from a reviewer
    # merely discussing false positives as the wave's technical topic.

    def test_retracted_field_on_changes_requested_is_a_false_positive(self) -> None:
        """Positive control: an explicit self-mark is still detected."""
        body = (
            _verdict("Idris Yusuf", "Mateo Salazar", "ChangesRequested")
            + "\nRetracted: on reflection this finding was invalid, my mistake."
        )
        v = ts.parse_verdicts([body])[0]
        self.assertTrue(v.false_positive)

    def test_bold_retracted_field_is_detected(self) -> None:
        body = (
            _verdict("Idris Yusuf", "Mateo Salazar", "ChangesRequested")
            + "\n**Retracted:** superseded by the comment above."
        )
        v = ts.parse_verdicts([body])[0]
        self.assertTrue(v.false_positive)

    # -- Regression: main#1358 -- three mutants of the #1347/#1348 code
    # survived the suite above (production behavior was already correct in
    # all three; only the test coverage was missing). Each test target is
    # named after the specific line the mutant strips.

    def test_bold_only_verdict_value_still_classifies(self) -> None:
        """`charter_trailer.normalize_verdict_token`'s alnum-stripping, not just casefold.

        A verdict field with no surrounding whitespace before the bold
        marker (`RequestOrReplied: **ChangesRequested**`) is captured with
        its LEADING `**` intact — only the trailing `**` is stripped by the
        field regex's `\\**\\s*$` tail, so the captured token is literally
        `"**ChangesRequested"`. Removing `charter_trailer.normalize_verdict_token`'s
        `re.sub(r"[^a-z0-9]", "", ...)` step (leaving only `.casefold()`)
        does not fail any other test in this file —
        `charter_trailer.normalize_verdict_token` needs its own direct
        assertion (see `test_charter_trailer.py`, main#1359).
        """
        body = "Requestor: A\nRequestee: B\nRequestOrReplied: **ChangesRequested**\n"
        v = ts.parse_verdicts([body])[0]
        self.assertEqual(v.verdict, "**ChangesRequested")
        self.assertEqual(ct.verdict_kind(v.verdict, include_bare_changes=True), "changesrequested")
        self.assertTrue(ts._is_changes_requested(v.verdict))

    def test_retracted_mentioned_mid_prose_never_counts(self) -> None:
        """`_RETRACTION_RE`'s leading `^` line-start anchor.

        A comment merely discussing the field-format convention in prose
        (e.g. quoting `Retracted: <reason>` as an example, not posting it as
        an actual field) must never count — this is the identical
        false-positive class main#1348 exists to eliminate, now unguarded
        on the *replacement* mechanism if the anchor is dropped.
        """
        body = (
            _verdict("Aino Virtanen", "Nadia Khoury", "ChangesRequested")
            + "\nSee the field format convention: Retracted: <reason> for self-marks."
        )
        v = ts.parse_verdicts([body])[0]
        self.assertFalse(v.false_positive)

    def test_bare_retracted_field_with_no_value_never_counts(self) -> None:
        """`_RETRACTION_RE`'s trailing `\\S` (non-empty-value) requirement.

        An unfilled `Retracted:` placeholder/template line, with nothing
        after the colon, must never count as a genuine self-mark.
        """
        body = _verdict("Aino Virtanen", "Nadia Khoury", "ChangesRequested") + "\nRetracted:\n"
        v = ts.parse_verdicts([body])[0]
        self.assertFalse(v.false_positive)

    def test_plain_prose_without_the_marker_never_counts(self) -> None:
        """'false-positive'/'withdrawn'/'retracted' in prose, with no explicit
        `Retracted:` field, must never count — even on a ChangesRequested verdict."""
        body = (
            _verdict("Aino Virtanen", "Nadia Khoury", "ChangesRequested")
            + "\nOn reflection this was invalid — withdrawn, my mistake, false-positive."
        )
        v = ts.parse_verdicts([body])[0]
        self.assertFalse(v.false_positive)

    def test_request_verdict_never_counts_even_with_the_marker(self) -> None:
        """main#1348 non-negotiable: Request/Reply are process metadata, not
        verdicts — they can never contribute a false positive, even if the
        comment happens to contain the `Retracted:` field text."""
        body = (
            _verdict("Nurul Hakim", "Weronika Zielinska", "Request")
            + "\nRetracted: n/a, just re-requesting review."
        )
        v = ts.parse_verdicts([body])[0]
        self.assertFalse(v.false_positive)

    def test_reply_verdict_never_counts_even_with_the_marker(self) -> None:
        body = (
            _verdict("Wanjiku Mwangi", "Nadia Khoury", "Reply")
            + "\nRetracted: my earlier finding after re-reading the spec."
        )
        v = ts.parse_verdicts([body])[0]
        self.assertFalse(v.false_positive)

    def test_approved_verdict_with_marker_never_counts(self) -> None:
        """Approved never raised a finding, so there is nothing to retract,
        even if the field is present."""
        body = _verdict("Aino Virtanen", "Nadia Khoury", "Approved") + "\nRetracted: n/a."
        v = ts.parse_verdicts([body])[0]
        self.assertFalse(v.false_positive)

    # -- Regression: #881 -- Approving verdicts must never score as FP even when
    # the prose mentions "false-positive" (real evidence from PR #873).

    def test_approved_verdict_with_fp_prose_is_not_a_fp(self) -> None:
        """Aino's #873 body: approval praising a false-positive test — must score 0."""
        body = (
            _verdict("Aino Virtanen", "Santiago Ferreira", "Approved")
            + "\nThe false-positive test (`type` keyword inside a function param list…)"
            " validates the anchor correctly rejects it."
        )
        v = ts.parse_verdicts([body])[0]
        self.assertFalse(v.false_positive)

    def test_approved_verdict_with_fp_in_identifier_is_not_a_fp(self) -> None:
        """Bereket's #873 body: 'No false-positive on type in non-declaration contexts'."""
        body = (
            _verdict("Bereket Tadesse", "Santiago Ferreira", "Approved")
            + "\nNo false-positive on `type` in non-declaration contexts."
            " test_no_false_positive_type_in_non_decl_context passes cleanly."
        )
        v = ts.parse_verdicts([body])[0]
        self.assertFalse(v.false_positive)

    def test_fp_in_code_span_is_not_a_fp(self) -> None:
        """FP keyword inside an inline code span in a non-approving verdict is ignored."""
        body = (
            _verdict("Idris Yusuf", "Nadia Khoury", "Reply")
            + "\nSee `test_no_false_positive_case` for coverage."
        )
        v = ts.parse_verdicts([body])[0]
        self.assertFalse(v.false_positive)

    def test_fp_in_fenced_block_is_not_a_fp(self) -> None:
        """A `Retracted:` field quoted inside a fenced code block is ignored."""
        body = (
            _verdict("Aino Virtanen", "Nadia Khoury", "ChangesRequested")
            + "\n```\n# example comment shape\nRetracted: true\n```\n"
            "Looks good otherwise."
        )
        v = ts.parse_verdicts([body])[0]
        self.assertFalse(v.false_positive)

    # -- main#1366: `OrchestratorCaused:` is a sibling of `Retracted:` and is
    # gated identically — structured field, ChangesRequested only, code
    # regions stripped. These mirror the `Retracted:` cases above.

    def test_orchestrator_caused_field_on_changes_requested_is_detected(self) -> None:
        body = (
            _verdict("Nino Kavtaradze", "Lucas Ferreira", "ChangesRequested")
            + "\nOrchestratorCaused: stale brief — dispatched against a pre-#1333 head."
        )
        v = ts.parse_verdicts([body])[0]
        self.assertTrue(v.orchestrator_caused)
        self.assertFalse(v.false_positive)  # independent markers

    def test_bold_orchestrator_caused_field_is_detected(self) -> None:
        body = (
            _verdict("Nino Kavtaradze", "Lucas Ferreira", "Changes Requested")
            + "\n**OrchestratorCaused:** unbatched dispatch staled this verdict."
        )
        self.assertTrue(ts.parse_verdicts([body])[0].orchestrator_caused)

    def test_orchestrator_caused_on_approved_is_ignored(self) -> None:
        """No block was raised, so there is no rework round to reattribute."""
        body = (
            _verdict("Nino Kavtaradze", "Lucas Ferreira", "Approved") + "\nOrchestratorCaused: n/a."
        )
        self.assertFalse(ts.parse_verdicts([body])[0].orchestrator_caused)

    def test_orchestrator_caused_on_reply_is_ignored(self) -> None:
        body = (
            _verdict("Lucas Ferreira", "Nino Kavtaradze", "Reply")
            + "\nOrchestratorCaused: the brief was stale."
        )
        self.assertFalse(ts.parse_verdicts([body])[0].orchestrator_caused)

    def test_orchestrator_caused_empty_value_does_not_count(self) -> None:
        body = (
            _verdict("Nino Kavtaradze", "Lucas Ferreira", "ChangesRequested")
            + "\nOrchestratorCaused:\n"
        )
        self.assertFalse(ts.parse_verdicts([body])[0].orchestrator_caused)

    def test_orchestrator_caused_mid_line_prose_does_not_count(self) -> None:
        body = (
            _verdict("Nino Kavtaradze", "Lucas Ferreira", "ChangesRequested")
            + "\nSee the field convention: OrchestratorCaused: <reason> marks dispatch errors."
        )
        self.assertFalse(ts.parse_verdicts([body])[0].orchestrator_caused)

    def test_orchestrator_caused_in_fenced_block_is_ignored(self) -> None:
        body = (
            _verdict("Nino Kavtaradze", "Lucas Ferreira", "ChangesRequested")
            + "\n```\nOrchestratorCaused: example only\n```\n"
        )
        self.assertFalse(ts.parse_verdicts([body])[0].orchestrator_caused)

    # -- Regression: main#1348 wave-29 corpus. All 17 real wave-29 hits under
    # the old free-text regex were wrong — reviewers discussing their own
    # false-positive test corpus, naming the defect class in prose, or
    # retracting an unrelated note. These five are representative shapes;
    # none carries the explicit `Retracted:` field, so none may count.

    _WAVE_29_COMMENT_SHAPES = (
        "## False-positive corpus I extended rather than re-ran",
        "my 20-case false-positive corpus byte-identical to this head's output",
        "retracted my earlier 'yq is an obvious win' note",
        "the false-positive removal itself is sound and well-guarded",
        "this is #1152's false positive, so 'base BLOCK -> head ALLOW' is the intended change",
    )

    def test_wave_29_comment_corpus_yields_zero_false_positives(self) -> None:
        for shape in self._WAVE_29_COMMENT_SHAPES:
            with self.subTest(shape=shape):
                body = (
                    _verdict("Nino Kavtaradze", "Nadia Khoury", "ChangesRequested") + f"\n{shape}"
                )
                v = ts.parse_verdicts([body])[0]
                self.assertFalse(v.false_positive)


# --------------------------------------------------------------------------- #
# Verdict-vocabulary extraction (main#1359) — singularity + the divergence
# the extraction was filed to close.
# --------------------------------------------------------------------------- #
class VerdictVocabularySingularityTests(unittest.TestCase):
    """One definition of the verdict-kind vocabulary, not a private copy here.

    `trust_signals.py` used to carry `_VERDICT_KIND` / `_normalize_verdict_token`
    / `_verdict_kind` / `_strip_code_markup` as private copies of concepts
    `charter_trailer` (main#932/#934's declared single source of truth for the
    trailer convention) now also owns. These assertions make a reintroduced
    copy fail CI rather than rot quietly, mirroring
    `TrailerHelperSingularityTests` in
    `test_validate_review_comment_format_failopen.py`.
    """

    def test_module_has_no_private_vocabulary_symbols(self) -> None:
        for name in ("_VERDICT_KIND", "_normalize_verdict_token", "_verdict_kind"):
            self.assertFalse(hasattr(ts, name), f"trust_signals.{name} should not exist")

    def test_module_has_no_private_stripper(self) -> None:
        self.assertFalse(
            hasattr(ts, "_strip_code_markup"), "trust_signals._strip_code_markup should not exist"
        )

    def test_trust_signals_imports_the_shared_module(self) -> None:
        self.assertIs(ts.charter_trailer, ct)


class TildeFenceDivergenceTests(unittest.TestCase):
    """The divergence main#1359/main#1361 report: pre-fix, `charter_trailer
    .strip_code_regions` left `~~~` fences intact while `trust_signals`'
    now-deleted private `_strip_code_markup` stripped them — same input,
    different answer, depending on which copy handled it.

    Verified against the pre-#1359 tree (`git stash` over this same
    reproduction): ``trust_signals._strip_code_markup`` stripped the ``~~~``
    block (``false_positive=False``, correct) while feeding the identical
    body through ``charter_trailer.strip_code_regions`` instead left the
    ``Retracted:`` line visible (``false_positive=True`` — wrong: it is a
    quoted example, not a real self-mark). Post-fix there is exactly one
    stripper and both call sites necessarily agree.
    """

    _TILDE_FENCED_RETRACTED_EXAMPLE = (
        "RequestOrReplied: ChangesRequested\n\n~~~\nRetracted: quoted example\n~~~\n"
    )

    def test_charter_trailer_strip_code_regions_strips_tilde_fences(self) -> None:
        # Pre-#1359/#1361: FAILS — `strip_code_regions` only recognized
        # ```` ``` ```` and left the `~~~`-fenced `Retracted:` line intact, so
        # `"Retracted"` remained in the output.
        result = ct.strip_code_regions(self._TILDE_FENCED_RETRACTED_EXAMPLE)
        self.assertNotIn("Retracted", result)

    def test_quoted_retracted_inside_tilde_fence_is_not_a_false_positive(self) -> None:
        # Pre-#1359: this specific assertion already passed, because
        # `trust_signals` routed through its OWN private `_strip_code_markup`,
        # not the shared (then-buggy) `charter_trailer.strip_code_regions`.
        # It is a regression guard for the migration, not the divergence
        # proof itself — see `test_charter_trailer_strip_code_regions_strips_tilde_fences`
        # and `ConsolidatedStripCodeRegionsAlsoFixesTheHookAlias` below for that.
        v = ts.parse_verdicts([self._TILDE_FENCED_RETRACTED_EXAMPLE])[0]
        self.assertFalse(v.false_positive)


class ConsolidatedStripCodeRegionsAlsoFixesTheHookAlias(unittest.TestCase):
    """main#1361's exact repro, run against the shared definition directly.

    `validate_pr_review.py` aliases `charter_trailer.strip_code_regions`
    (`_strip_code_regions = strip_code_regions`) and `charter_trailer
    .extract_charter_field` calls it internally — so main#1359's fence fix,
    made once in `charter_trailer.py`, closes main#1361 for every consumer
    without a second change. Pre-#1359/#1361 this test FAILS: both fields
    resolve out of the `~~~`-fenced example even though there is no real
    `---` trailer anywhere in the body.
    """

    def test_tilde_fenced_trailer_example_with_no_real_trailer_extracts_nothing(self) -> None:
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
        self.assertIsNone(ct.extract_charter_field("Requestor", body))
        self.assertIsNone(ct.extract_charter_field("RequestOrReplied", body))
        self.assertIsNone(ct.extract_charter_field("TechDebt", body))

    def test_tilde_fenced_example_above_a_real_trailer_still_resolves_the_real_one(self) -> None:
        """Regression guard (main#1361 acceptance): a real `---` trailer AFTER
        a `~~~`-fenced example still wins — unaffected by the fence fix
        because `trailer_block_substring` already scoped to the last `---`."""
        body = (
            "Here is the format reviewers should use:\n\n"
            "~~~\n"
            "Requestor: Ghost Reviewer\n"
            "RequestOrReplied: Approved\n"
            "~~~\n\n"
            "---\n"
            "Requestor: Nadia Khoury\n"
            "RequestOrReplied: ChangesRequested\n"
        )
        self.assertEqual(ct.extract_charter_field("Requestor", body), "Nadia Khoury")
        self.assertEqual(ct.extract_charter_field("RequestOrReplied", body), "ChangesRequested")


class UnterminatedFenceDirectionChangeTests(unittest.TestCase):
    """main#1359 merge-gate review (Aino Virtanen, MF2): the stripper swap is
    NOT parity-preserving on an unterminated fence, in the direction that
    costs a reviewer their false-positive credit.

    The deleted `trust_signals._strip_code_markup` required a CLOSING fence
    marker to match, so an opened-but-never-closed fence was left alone and
    anything after it — including a genuine `Retracted:` self-mark — still
    counted. `charter_trailer.strip_code_regions` strips an unterminated
    fence to end-of-body instead (the CommonMark-correct answer), which
    silently swallows a genuine self-mark written below one. This is a
    deliberate, documented trade (see the migration comment in
    `parse_verdicts`), not something this PR is asked to change — the point
    is that it is now STATED and PINNED rather than merely true.
    """

    def test_genuine_self_mark_below_an_unterminated_fence_is_now_swallowed(self) -> None:
        body = (
            "RequestOrReplied: ChangesRequested\n\n"
            "```\n"
            "snippet opened but never closed\n"
            "Retracted: on reflection this finding was invalid, my mistake.\n"
        )
        v = ts.parse_verdicts([body])[0]
        # Pre-#1359 (deleted `_strip_code_markup`): this was True — the
        # reviewer's self-mark survived because the old stripper left an
        # unterminated fence untouched. Post-#1359: False.
        self.assertFalse(v.false_positive)

    def test_same_shape_with_a_closed_fence_still_detects_the_self_mark(self) -> None:
        """Regression guard: only the UNTERMINATED case changed. A closed
        fence still correctly hides a quoted example, and a real self-mark
        OUTSIDE any fence is still detected."""
        body = (
            "RequestOrReplied: ChangesRequested\n\n"
            "```\n"
            "quoted example, not a real self-mark\n"
            "```\n"
            "Retracted: on reflection this finding was invalid, my mistake.\n"
        )
        v = ts.parse_verdicts([body])[0]
        self.assertTrue(v.false_positive)


# --------------------------------------------------------------------------- #
# Extraction (gh-mocked)
# --------------------------------------------------------------------------- #
class Extract(unittest.TestCase):
    def _run(self, prs: list[dict]) -> dict[str, ts.Signals]:
        fake = _FakeGh(prs)
        with TemporaryDirectory() as td:
            status = Path(td) / "cross-repo-status.json"
            _write_status(status, repos=_REPOS, wave="17")
            with mock.patch.object(wave_status.subprocess, "run", fake):
                sigs = ts.extract_signals("6", "17", status)
        self.fake = fake
        return sigs

    def test_author_and_reviewer_attribution(self) -> None:
        prs = [
            {
                "repo": _REPOS[0],
                "number": 901,
                "sha": "s901",
                "mergedAt": "2026-06-24T02:00:00Z",
                "commit_author": "Nadia Khoury",
                "comments": [_verdict("Aino Virtanen", "Nadia Khoury", "ChangesRequested")],
                "ci_red": False,
            },
            {
                "repo": _REPOS[1],
                "number": 902,
                "sha": "s902",
                "mergedAt": "2026-06-24T03:00:00Z",
                "commit_author": "Nadia Khoury",
                "comments": [_verdict("Aino Virtanen", "Nadia Khoury", "Approved")],
                "ci_red": True,
            },
        ]
        sigs = self._run(prs)
        nadia = sigs["Nadia Khoury"]
        self.assertEqual(nadia.prs_merged, 2)
        self.assertEqual(nadia.authored_prs, [901, 902])
        self.assertEqual(nadia.must_fix_received, 1)
        self.assertEqual(nadia.rework_cycles, 1)  # one PR needed a rework round
        self.assertEqual(nadia.ci_red_merges, 1)  # PR 902 merged red
        # Reviewer credit lands on the Requestor, not the gh principal.
        self.assertEqual(sigs["Aino Virtanen"].must_fix_caught, 1)

    def test_false_positive_dings_reviewer(self) -> None:
        prs = [
            {
                "repo": _REPOS[0],
                "number": 903,
                "sha": "s903",
                "mergedAt": "2026-06-24T02:00:00Z",
                "commit_author": "Mateo Salazar",
                "comments": [
                    _verdict("Idris Yusuf", "Mateo Salazar", "ChangesRequested")
                    + "\nRetracted: on reflection this finding was invalid."
                ],
                "ci_red": False,
            },
        ]
        sigs = self._run(prs)
        self.assertEqual(sigs["Idris Yusuf"].review_false_positives, 1)
        self.assertEqual(sigs["Idris Yusuf"].must_fix_caught, 1)

    # -- Regression: main#1347 -- all three ChangesRequested spellings must
    # flow through extraction identically (real evidence: main PR #1173,
    # #1153, both dropped by the old `(\w+)` capture).

    def test_spaced_changes_requested_counted_same_as_unspaced(self) -> None:
        prs = [
            {
                "repo": _REPOS[0],
                "number": 1173,
                "sha": "s1173",
                "mergedAt": "2026-06-24T02:00:00Z",
                "commit_author": "Aino Virtanen",
                "comments": [_verdict("Nino Kavtaradze", "Aino Virtanen", "Changes Requested")],
                "ci_red": False,
            },
            {
                "repo": _REPOS[1],
                "number": 1153,
                "sha": "s1153",
                "mergedAt": "2026-06-24T03:00:00Z",
                "commit_author": "Nurul Hakim",
                "comments": [_verdict("Weronika Zielinska", "Nurul Hakim", "Changes Requested")],
                "ci_red": False,
            },
        ]
        sigs = self._run(prs)
        self.assertEqual(sigs["Aino Virtanen"].must_fix_received, 1)
        self.assertEqual(sigs["Aino Virtanen"].rework_cycles, 1)
        self.assertEqual(sigs["Nurul Hakim"].must_fix_received, 1)
        self.assertEqual(sigs["Nino Kavtaradze"].must_fix_caught, 1)
        self.assertEqual(sigs["Weronika Zielinska"].must_fix_caught, 1)

    # -- Regression: main#1348 defect 2 -- Request/Reply comments can never
    # contribute to review_false_positives, end to end (real evidence: main
    # PR #1310 verdict=Reply, #1153 verdict=Request).

    def test_reply_comment_never_dings_reviewer_even_with_marker(self) -> None:
        prs = [
            {
                "repo": _REPOS[0],
                "number": 1310,
                "sha": "s1310",
                "mergedAt": "2026-06-24T02:00:00Z",
                "commit_author": "Nadia Khoury",
                "comments": [
                    _verdict("Aino Virtanen", "Nadia Khoury", "Reply")
                    + "\nRetracted: claim retracted, issue stays open."
                ],
                "ci_red": False,
            },
        ]
        sigs = self._run(prs)
        aino_sig = sigs.get("Aino Virtanen", ts.Signals())
        self.assertEqual(aino_sig.review_false_positives, 0)

    def test_request_comment_never_dings_reviewer_even_with_marker(self) -> None:
        prs = [
            {
                "repo": _REPOS[0],
                "number": 1153,
                "sha": "s1153b",
                "mergedAt": "2026-06-24T02:00:00Z",
                "commit_author": "Weronika Zielinska",
                "comments": [
                    _verdict("Nurul Hakim", "Weronika Zielinska", "Request")
                    + "\nRetracted: n/a, re-requesting review."
                ],
                "ci_red": False,
            },
        ]
        sigs = self._run(prs)
        nurul_sig = sigs.get("Nurul Hakim", ts.Signals())
        self.assertEqual(nurul_sig.review_false_positives, 0)

    def test_gh_calls_are_list_vectors_no_shell(self) -> None:
        prs = [
            {
                "repo": _REPOS[0],
                "number": 904,
                "sha": "s904",
                "mergedAt": "2026-06-24T02:00:00Z",
                "commit_author": "Nadia Khoury",
                "comments": [],
                "ci_red": False,
            }
        ]
        self._run(prs)
        self.assertTrue(self.fake.calls)
        self.assertTrue(all(isinstance(c, list) and c[0] == "gh" for c in self.fake.calls))

    def test_approved_with_fp_prose_does_not_ding_reviewer(self) -> None:
        """Regression #881: Aino + Bereket both Approved on PR #873 with FP prose.

        Both bodies mention 'false-positive' but in the context of praising the
        PR's own test coverage — neither is a retraction.  review_false_positives
        must remain 0 for both reviewers.
        """
        aino_body = (
            _verdict("Aino Virtanen", "Santiago Ferreira", "Approved")
            + "\nThe false-positive test (`type` keyword inside a function param list…)"
            " validates the … anchor correctly rejects it."
        )
        bereket_body = (
            _verdict("Bereket Tadesse", "Santiago Ferreira", "Approved")
            + "\nNo false-positive on `type` in non-declaration contexts."
            " test_no_false_positive_type_in_non_decl_context passes."
        )
        prs = [
            {
                "repo": _REPOS[0],
                "number": 873,
                "sha": "s873",
                "mergedAt": "2026-06-24T02:00:00Z",
                "commit_author": "Santiago Ferreira",
                "comments": [aino_body, bereket_body],
                "ci_red": False,
            },
        ]
        sigs = self._run(prs)
        aino_sig = sigs.get("Aino Virtanen", ts.Signals())
        bereket_sig = sigs.get("Bereket Tadesse", ts.Signals())
        self.assertEqual(aino_sig.review_false_positives, 0)
        self.assertEqual(bereket_sig.review_false_positives, 0)


# --------------------------------------------------------------------------- #
# Scoring (pure)
# --------------------------------------------------------------------------- #
class ScoreDelta(unittest.TestCase):
    def test_clean_multi_pr_plus_one(self) -> None:
        s = ts.Signals(prs_merged=3)
        self.assertEqual(ts.score_delta(s), 1)

    def test_strong_reviewer_and_author_capped_at_two(self) -> None:
        s = ts.Signals(prs_merged=3, must_fix_caught=4)
        self.assertEqual(ts.score_delta(s), 2)

    def test_ci_red_is_negative(self) -> None:
        s = ts.Signals(prs_merged=2, ci_red_merges=1)
        self.assertEqual(ts.score_delta(s), -1)

    def test_false_positive_is_negative(self) -> None:
        s = ts.Signals(prs_merged=1, must_fix_caught=3, review_false_positives=1)
        self.assertEqual(ts.score_delta(s), -1)

    def test_clamped_to_minus_two(self) -> None:
        s = ts.Signals(prs_merged=1, ci_red_merges=5)
        self.assertEqual(ts.score_delta(s), -2)

    def test_no_signal_zero_delta(self) -> None:
        self.assertEqual(ts.score_delta(ts.Signals()), 0)

    def test_one_clean_pr_no_increase(self) -> None:
        # A single clean PR is not "exceptional" — no bump.
        self.assertEqual(ts.score_delta(ts.Signals(prs_merged=1)), 0)


# --------------------------------------------------------------------------- #
# Two-band, rate-relative rework rule (main#1349, owner ruling 2026-08-07)
# --------------------------------------------------------------------------- #
class ReworkBandPredicates(unittest.TestCase):
    """The band boundaries themselves, independent of score_delta.

    Both bars are multiplications of ``prs_merged`` — no ratio, no float, no
    zero-guard — so these pin the exact integer boundaries rather than a
    rounded rate.
    """

    def test_band_coefficients_match_the_charter(self) -> None:
        """Pin the coefficient VALUES to the charter, and each predicate's
        boundary to its own coefficient — from **both** sides.

        `trust_matrix.md` § The two rework bands states 1/PR and 2/PR as the
        owner-ruled values (#1349), so changing either constant is a charter
        change rather than a code change. This test proves exactly two things:

        1. the constants still hold the charter's values; and
        2. each predicate flips at the point its constant names — asserted at
           the boundary AND one step past it, so a predicate that is *looser*
           than its constant fails here and not merely in a neighbouring test.

        **What it cannot prove (main#1367).** It does not prove the predicates
        reference the constants rather than equal-valued literals. Replacing
        ``CLEAN_BAR_MUST_FIX_PER_PR *`` with ``1 *`` is an *equivalent mutant*
        — identical behaviour on every input — so no test can discriminate it,
        and the earlier version of this docstring claimed otherwise. Keeping
        the constants referenced is a review concern, not a testable one.
        """
        self.assertEqual(ts.CLEAN_BAR_MUST_FIX_PER_PR, 1)
        self.assertEqual(ts.PENALTY_BAR_MUST_FIX_PER_PR, 2)

        prs = 4
        clean_bar = ts.CLEAN_BAR_MUST_FIX_PER_PR * prs
        penalty_bar = ts.PENALTY_BAR_MUST_FIX_PER_PR * prs

        # Clean bar is inclusive: true AT the bar, false one past it. The
        # second assertion is what a loosened predicate (e.g. an inline `2 *`
        # where the constant says 1) trips on.
        self.assertTrue(
            ts.Signals(prs_merged=prs, must_fix_received=clean_bar).rework_within_clean_bar()
        )
        self.assertFalse(
            ts.Signals(prs_merged=prs, must_fix_received=clean_bar + 1).rework_within_clean_bar()
        )

        # Penalty bar is exclusive: false AT the bar, true one past it.
        self.assertFalse(
            ts.Signals(prs_merged=prs, must_fix_received=penalty_bar).rework_above_penalty_bar()
        )
        self.assertTrue(
            ts.Signals(prs_merged=prs, must_fix_received=penalty_bar + 1).rework_above_penalty_bar()
        )

    def test_recv_equal_to_prs_is_within_clean_bar(self) -> None:
        s = ts.Signals(prs_merged=4, must_fix_received=4)  # exactly 1.0/PR
        self.assertTrue(s.rework_within_clean_bar())
        self.assertFalse(s.rework_above_penalty_bar())

    def test_one_over_clean_bar_enters_neutral_band(self) -> None:
        s = ts.Signals(prs_merged=4, must_fix_received=5)
        self.assertFalse(s.rework_within_clean_bar())
        self.assertFalse(s.rework_above_penalty_bar())  # neutral: no bump, no ding

    def test_exactly_double_is_still_neutral_band(self) -> None:
        s = ts.Signals(prs_merged=4, must_fix_received=8)  # exactly 2.0/PR
        self.assertFalse(s.rework_within_clean_bar())
        self.assertFalse(s.rework_above_penalty_bar())

    def test_one_over_double_crosses_the_penalty_bar(self) -> None:
        s = ts.Signals(prs_merged=4, must_fix_received=9)
        self.assertFalse(s.rework_within_clean_bar())
        self.assertTrue(s.rework_above_penalty_bar())

    def test_non_authoring_engineer_is_clean_without_a_zero_guard(self) -> None:
        # prs_merged == 0 implies must_fix_received == 0, so 0 <= 0 classifies
        # a non-author as clean naturally — the reason the bars are a
        # multiplication and not a ratio.
        s = ts.Signals(must_fix_caught=3)
        self.assertTrue(s.rework_within_clean_bar())
        self.assertFalse(s.rework_above_penalty_bar())
        self.assertTrue(s.qualifies_for_bump())

    def test_hard_dings_still_disqualify_the_bump_absolutely(self) -> None:
        # Rework is rate-relative; CI-red and review false-positives are not.
        # Both engineers below are within the clean bar on rework alone.
        self.assertTrue(ts.Signals(prs_merged=3, ci_red_merges=1).rework_within_clean_bar())
        self.assertFalse(ts.Signals(prs_merged=3, ci_red_merges=1).qualifies_for_bump())
        self.assertFalse(ts.Signals(prs_merged=3, review_false_positives=1).qualifies_for_bump())

    def test_has_negative_and_qualifies_for_bump_are_different_predicates(self) -> None:
        """The #1349 predicate split, asserted directly.

        Aino's wave-29 record: four blocking verdicts over nine PRs. There IS a
        negative to report (``negative_signal_line`` must cite it), and the wave
        IS bump-eligible. Before #1349 one predicate answered both questions,
        which is what made the positive branch unreachable.
        """
        s = ts.Signals(prs_merged=9, must_fix_caught=12, must_fix_received=4)
        self.assertTrue(s.has_negative())
        self.assertTrue(s.qualifies_for_bump())
        # And the reporting line still cites the gap rather than claiming clean.
        line = ts.negative_signal_line("Aino Virtanen", s)
        self.assertIn("4 must-fix received", line)
        self.assertNotIn("metrics clean", line)


class ScoreDeltaReworkBands(unittest.TestCase):
    """score_delta over the two-band rule — boundaries and the acceptance case."""

    def test_strong_reviewer_with_normal_authoring_record_scores_positive(self) -> None:
        """main#1349 acceptance criterion 1.

        ``must_fix_caught >= 2`` plus a normal authoring record must be able to
        reach a positive delta. Pre-#1349 this returned -1.
        """
        s = ts.Signals(prs_merged=9, must_fix_caught=12, must_fix_received=4)
        self.assertEqual(ts.score_delta(s), 2)

    def test_clean_bar_boundary_recv_equals_prs_earns_the_bump(self) -> None:
        s = ts.Signals(prs_merged=4, must_fix_caught=1, must_fix_received=4)
        self.assertEqual(ts.score_delta(s), 1)

    def test_one_over_clean_bar_forfeits_the_bump_but_takes_no_ding(self) -> None:
        # A wave-leading review record does not rescue the bump once the clean
        # bar is crossed — but it is not punished either.
        s = ts.Signals(prs_merged=6, must_fix_caught=17, must_fix_received=12)
        self.assertEqual(ts.score_delta(s), 0)

    def test_penalty_bar_boundary_exactly_double_is_neutral(self) -> None:
        s = ts.Signals(prs_merged=3, must_fix_received=6)
        self.assertEqual(ts.score_delta(s), 0)

    def test_penalty_bar_boundary_one_over_double_dings(self) -> None:
        s = ts.Signals(prs_merged=3, must_fix_received=7)
        self.assertEqual(ts.score_delta(s), -1)

    def test_genuine_rate_outlier_still_takes_minus_one(self) -> None:
        # Lucas's wave-29 record (2.14/PR) — the one -1 the ruling says must
        # survive the change on its merits.
        s = ts.Signals(prs_merged=7, must_fix_caught=3, must_fix_received=15)
        self.assertEqual(ts.score_delta(s), -1)

    def test_old_absolute_three_threshold_no_longer_fires(self) -> None:
        # Pre-#1349, `must_fix_received >= 3` was an absolute -1, so a single
        # defect found independently by three review heads tripped it. Three
        # verdicts over nine PRs is now well within the clean bar.
        s = ts.Signals(prs_merged=9, must_fix_received=3)
        self.assertEqual(ts.score_delta(s), 1)

    def test_wave_29_distribution_is_not_uniformly_non_positive(self) -> None:
        """main#1349 acceptance criterion 2, pinned end-to-end.

        The ten corrected wave-29 signal sets, verified against a live
        ``extract_signals`` run at 69c2e08. Under the pre-#1349 rubric every
        one of these returned <= 0 (7 negative, 3 zero, 0 positive), which is
        the defect #1349 reports.
        """
        wave_29 = {
            # name: (prs_merged, must_fix_caught, must_fix_received)
            "Aino Virtanen": (9, 12, 4),
            "Nino Kavtaradze": (8, 11, 4),
            "Lucas Ferreira": (7, 3, 15),
            "Weronika Zielinska": (6, 17, 12),
            "Nadia Khoury": (4, 5, 1),
            "Santiago Ferreira": (4, 1, 4),
            "Wanjiku Mwangi": (3, 1, 6),
            "Nurul Hakim": (2, 0, 2),
            "Bereket Tadesse": (1, 1, 3),
            "Yusuke Inoue": (1, 0, 0),
        }
        expected = {
            "Aino Virtanen": 2,
            "Nino Kavtaradze": 2,
            "Lucas Ferreira": -1,
            "Weronika Zielinska": 0,
            "Nadia Khoury": 2,
            "Santiago Ferreira": 1,
            "Wanjiku Mwangi": 0,
            "Nurul Hakim": 1,
            "Bereket Tadesse": -1,
            "Yusuke Inoue": 0,
        }
        actual = {
            name: ts.score_delta(ts.Signals(prs_merged=p, must_fix_caught=c, must_fix_received=r))
            for name, (p, c, r) in wave_29.items()
        }
        self.assertEqual(actual, expected)
        deltas = list(actual.values())
        self.assertEqual(sum(1 for d in deltas if d > 0), 5)
        self.assertEqual(sum(1 for d in deltas if d < 0), 2)
        self.assertEqual(sum(1 for d in deltas if d == 0), 3)


# --------------------------------------------------------------------------- #
# Orchestrator-caused rework attribution (main#1366)
# --------------------------------------------------------------------------- #
class AttributableRework(unittest.TestCase):
    def test_defaults_to_the_raw_count(self) -> None:
        s = ts.Signals(prs_merged=7, must_fix_received=15)
        self.assertEqual(s.attributable_rework(), 15)

    def test_marked_rounds_are_subtracted(self) -> None:
        s = ts.Signals(prs_merged=7, must_fix_received=15, orchestrator_caused_rework=2)
        self.assertEqual(s.attributable_rework(), 13)

    def test_never_negative(self) -> None:
        s = ts.Signals(prs_merged=1, must_fix_received=1, orchestrator_caused_rework=9)
        self.assertEqual(s.attributable_rework(), 0)

    def test_raw_count_is_untouched_and_still_reported(self) -> None:
        """The forced negative-signal pass must still show every round.

        Attribution changes what the rate bars score, not what happened.
        """
        s = ts.Signals(prs_merged=7, must_fix_received=15, orchestrator_caused_rework=2)
        self.assertEqual(s.must_fix_received, 15)
        self.assertTrue(s.has_negative())
        line = ts.negative_signal_line("Lucas Ferreira", s)
        self.assertIn("15 must-fix received", line)
        self.assertIn("2 orchestrator-caused", line)
        self.assertIn("13 attributable", line)

    def test_attribution_can_move_a_delta_across_the_penalty_bar(self) -> None:
        """The mechanism has teeth — one marked round is the whole margin.

        Lucas's wave-29 shape: 15 received over 7 PRs, penalty bar at 14. One
        round reattributed puts him in the neutral band instead of at -1.
        """
        unmarked = ts.Signals(prs_merged=7, must_fix_caught=3, must_fix_received=15)
        marked = ts.Signals(
            prs_merged=7, must_fix_caught=3, must_fix_received=15, orchestrator_caused_rework=1
        )
        self.assertEqual(ts.score_delta(unmarked), -1)
        self.assertEqual(ts.score_delta(marked), 0)

    def test_attribution_can_restore_the_clean_bar_and_the_bump(self) -> None:
        base = ts.Signals(prs_merged=4, must_fix_caught=3, must_fix_received=5)
        self.assertEqual(ts.score_delta(base), 0)  # one over the clean bar
        marked = ts.Signals(
            prs_merged=4, must_fix_caught=3, must_fix_received=5, orchestrator_caused_rework=1
        )
        self.assertEqual(ts.score_delta(marked), 2)

    def test_wave_29_deltas_are_unchanged_because_no_round_was_marked(self) -> None:
        """#1366 acceptance: state the effect on Lucas's -1 explicitly.

        The mechanism is prospective, not retroactive — no wave-29 comment
        carries `OrchestratorCaused:` (the field did not exist), so every
        engineer extracts `orchestrator_caused_rework=0` and every applied
        delta is untouched. Marking wave-29 rounds after the fact is exactly
        the appeal mechanism the issue forbids.
        """
        wave_29 = {
            "Aino Virtanen": (9, 12, 4, 2),
            "Nino Kavtaradze": (8, 11, 4, 2),
            "Lucas Ferreira": (7, 3, 15, -1),
            "Weronika Zielinska": (6, 17, 12, 0),
            "Nadia Khoury": (4, 5, 1, 2),
            "Santiago Ferreira": (4, 1, 4, 1),
            "Wanjiku Mwangi": (3, 1, 6, 0),
            "Nurul Hakim": (2, 0, 2, 1),
            "Bereket Tadesse": (1, 1, 3, -1),
            "Yusuke Inoue": (1, 0, 0, 0),
        }
        for name, (prs, caught, recv, expected) in wave_29.items():
            with self.subTest(engineer=name):
                sig = ts.Signals(prs_merged=prs, must_fix_caught=caught, must_fix_received=recv)
                self.assertEqual(sig.orchestrator_caused_rework, 0)
                self.assertEqual(sig.attributable_rework(), recv)
                self.assertEqual(ts.score_delta(sig), expected)


# --------------------------------------------------------------------------- #
# Rate-band calibration + revisit trigger (main#1368)
# --------------------------------------------------------------------------- #
def _authors(*rates: tuple[int, int]) -> dict[str, ts.Signals]:
    """Build a signal map from (prs_merged, must_fix_received) pairs."""
    return {
        f"E{i}": ts.Signals(prs_merged=p, must_fix_received=r) for i, (p, r) in enumerate(rates)
    }


class CalibrationDrift(unittest.TestCase):
    def test_wave_29_median_is_the_recorded_calibration_point(self) -> None:
        """The calibration basis is a fact about P10W29, not an assertion.

        Recomputed from the corrected signal set the bars were derived
        against. If this fails, the constants' calibration comment is wrong.
        """
        wave_29 = _authors(
            (9, 4), (8, 4), (7, 15), (6, 12), (4, 1), (4, 4), (3, 6), (2, 2), (1, 3), (1, 0)
        )
        self.assertEqual(ts.rework_rate_median(wave_29), ts.CALIBRATION_MEDIAN_RATE)
        drifted, reason = ts.calibration_drift(wave_29)
        self.assertFalse(drifted)
        self.assertIn("calibration OK", reason)

    def test_median_excludes_non_authors_and_handles_even_counts(self) -> None:
        # Non-authors have no denominator and must not be counted as rate 0.
        sigs = _authors((2, 0), (2, 4))  # rates 0.0 and 2.0 -> median 1.0
        sigs["Reviewer"] = ts.Signals(must_fix_caught=9)  # prs_merged == 0
        self.assertEqual(ts.rework_rate_median(sigs), 1.0)

    def test_median_is_none_when_nobody_authored(self) -> None:
        self.assertIsNone(ts.rework_rate_median({"R": ts.Signals(must_fix_caught=3)}))
        self.assertIsNone(ts.rework_rate_median({}))

    def test_drift_fires_when_rework_rate_climbs(self) -> None:
        # Every author at 2.0/PR — the clean bar now sits below the typical
        # author, so the bars no longer mean what they were set to mean.
        sigs = _authors(*[(3, 6)] * 6)
        drifted, reason = ts.calibration_drift(sigs)
        self.assertTrue(drifted)
        self.assertIn("CALIBRATION DRIFT", reason)
        self.assertIn("2.00", reason)

    def test_drift_fires_when_rework_rate_collapses(self) -> None:
        sigs = _authors(*[(4, 0)] * 6)
        drifted, reason = ts.calibration_drift(sigs)
        self.assertTrue(drifted)
        self.assertIn("CALIBRATION DRIFT", reason)

    def test_silent_inside_the_tolerance_band_on_both_edges(self) -> None:
        # Exactly at each edge of [0.5, 1.5] is still OK — the trigger is
        # strictly-greater-than, so an edge wave is not flagged.
        for prs, recv in ((2, 1), (2, 3)):  # rates 0.5 and 1.5
            sigs = _authors(*[(prs, recv)] * 6)
            drifted, _ = ts.calibration_drift(sigs)
            self.assertFalse(drifted, f"{recv}/{prs} should be inside the band")

    def test_thin_sample_reports_insufficient_never_drifted(self) -> None:
        # A wildly drifted rate over too few authors must NOT fire — a median
        # this thin is noise (the #1349 ruling's own objection to Option 2).
        sigs = _authors(*[(1, 9)] * (ts.CALIBRATION_MIN_AUTHORS - 1))
        drifted, reason = ts.calibration_drift(sigs)
        self.assertFalse(drifted)
        self.assertIn("insufficient sample", reason)

    def test_calibration_never_touches_a_score(self) -> None:
        """The float median is diagnostic only — score_delta stays integer."""
        drifted_wave = _authors(*[(3, 6)] * 6)
        self.assertTrue(ts.calibration_drift(drifted_wave)[0])
        # Same signals, scored: the neutral-band answer, unaffected by drift.
        self.assertEqual(ts.score_delta(ts.Signals(prs_merged=3, must_fix_received=6)), 0)

    def test_cli_exit_code_is_the_loud_part(self) -> None:
        """`calibration` exits 1 on drift, 0 otherwise — verified both ways.

        The exit code is the whole point of shipping this as a subcommand
        rather than a field in `score`'s JSON (main#1368): /wave-retro runs it
        as a mandatory step, so a drifted wave stops the retro.
        """
        drifted = _authors(*[(3, 6)] * 6)
        ok = _authors(*[(2, 2)] * 6)
        for sigs, expected in ((drifted, 1), (ok, 0)):
            with mock.patch.object(ts, "extract_signals", return_value=sigs):
                self.assertEqual(ts.main(["calibration", "10", "29"]), expected)


class Decay(unittest.TestCase):
    def test_no_decay_before_threshold(self) -> None:
        self.assertEqual(ts.decay(5, 2), 5)
        self.assertEqual(ts.decay(1, 2), 1)

    def test_decays_high_down(self) -> None:
        self.assertEqual(ts.decay(5, 3), 4)

    def test_decays_low_up(self) -> None:
        self.assertEqual(ts.decay(2, 3), 3)

    def test_neutral_stays(self) -> None:
        self.assertEqual(ts.decay(3, 9), 3)


def _entrant(proposed: int, signals: ts.Signals, *, old: int = ts.NEUTRAL) -> ts.Proposal:
    """A proposal from below the ceiling — the case the cap exists for."""
    return ts.Proposal(old_score=old, proposed_score=proposed, signals=signals)


def _holder(proposed: int, signals: ts.Signals) -> ts.Proposal:
    """A proposal from an engineer already at the ceiling."""
    return ts.Proposal(old_score=ts.MAX_SCORE, proposed_score=proposed, signals=signals)


class DistributionDiscipline(unittest.TestCase):
    def test_five_reserved_for_top_performer(self) -> None:
        proposals = {
            "Top": _entrant(5, ts.Signals(prs_merged=5, must_fix_caught=3)),
            "AlsoFive": _entrant(5, ts.Signals(prs_merged=2)),
        }
        out = ts.apply_distribution_discipline(proposals)
        self.assertEqual(out["Top"], 5)
        self.assertEqual(out["AlsoFive"], 4)  # capped — not the top performer

    def test_four_passes_through(self) -> None:
        proposals = {"X": _entrant(4, ts.Signals(prs_merged=2))}
        self.assertEqual(ts.apply_distribution_discipline(proposals)["X"], 4)

    def test_no_five_when_top_is_not_positive(self) -> None:
        proposals = {"X": _entrant(5, ts.Signals())}
        self.assertEqual(ts.apply_distribution_discipline(proposals)["X"], 4)

    # ---- Entry gate, not eviction rule (main#1365) ----------------------- #
    # The ceiling-HOLDER path had no coverage at all before this.

    def test_ceiling_holder_with_a_positive_delta_is_not_capped(self) -> None:
        """#1365 acceptance 1 — the regression that motivated the signature.

        Nino's wave-29 record: already at 5, earns +2, composite 15 against a
        wave maximum of 17. Under the old bare-tuple signature this returned 4,
        turning a +2 delta into a net -1.
        """
        proposals = {
            "Aino": _holder(5, ts.Signals(prs_merged=9, must_fix_caught=12, must_fix_received=4)),
            "Nino": _holder(5, ts.Signals(prs_merged=8, must_fix_caught=11, must_fix_received=4)),
        }
        out = ts.apply_distribution_discipline(proposals)
        self.assertEqual(out["Nino"], 5)  # holder — exempt despite composite 15 < 17
        self.assertEqual(out["Aino"], 5)  # top composite anyway

    def test_ceiling_entrant_below_the_wave_max_is_capped(self) -> None:
        """#1365 acceptance 2 — the entrant path still caps."""
        proposals = {
            "Aino": _holder(5, ts.Signals(prs_merged=9, must_fix_caught=12, must_fix_received=4)),
            "Nurul": _entrant(5, ts.Signals(prs_merged=2, must_fix_received=2), old=4),
        }
        self.assertEqual(ts.apply_distribution_discipline(proposals)["Nurul"], 4)

    def test_holder_exemption_does_not_rescue_a_dropping_score(self) -> None:
        # Exemption is from the CAP, not from the delta. A holder proposed
        # below the ceiling passes through at the proposed value.
        proposals = {"Held": _holder(3, ts.Signals(prs_merged=1, must_fix_received=9))}
        self.assertEqual(ts.apply_distribution_discipline(proposals)["Held"], 3)

    def test_top_is_batch_relative_so_feed_the_whole_roster(self) -> None:
        """The one caller obligation the signature cannot enforce.

        `top` is the maximum composite *within the batch*. Restricted to the
        two wave-29 ceiling entrants, Nadia (composite 8) becomes her own
        maximum and keeps a 5 that the full-roster run caps to 4. Pinned as
        known behaviour so the next reader meets it here rather than in a
        trust score.
        """
        aino = ts.Signals(prs_merged=9, must_fix_caught=12, must_fix_received=4)  # composite 17
        nadia = ts.Signals(prs_merged=4, must_fix_caught=5, must_fix_received=1)  # composite 8
        nurul = ts.Signals(prs_merged=2, must_fix_received=2)  # composite 0

        entrants_only = {
            "Nadia": _entrant(5, nadia),
            "Nurul": _entrant(5, nurul, old=4),
        }
        self.assertEqual(ts.apply_distribution_discipline(entrants_only)["Nadia"], 5)

        whole_roster = dict(entrants_only, Aino=_holder(5, aino))
        self.assertEqual(ts.apply_distribution_discipline(whole_roster)["Nadia"], 4)
        self.assertEqual(ts.apply_distribution_discipline(whole_roster)["Nurul"], 4)

    def test_wave_29_applied_scores_are_unchanged_by_the_entry_gate(self) -> None:
        """The signature change must not move any applied wave-29 score.

        Every row below is the score currently recorded in `trust_matrix.md`
        § Phase 10 Wave 29. Re-derived here through the new signature; a
        mismatch is an owner decision, not something to reconcile (main#1365).
        """
        # name: (old, prs, caught, recv, applied)
        wave_29 = {
            "Aino Virtanen": (5, 9, 12, 4, 5),
            "Nino Kavtaradze": (5, 8, 11, 4, 5),
            "Lucas Ferreira": (4, 7, 3, 15, 3),
            "Weronika Zielinska": (3, 6, 17, 12, 3),
            "Nadia Khoury": (3, 4, 5, 1, 4),
            "Santiago Ferreira": (3, 4, 1, 4, 4),
            "Wanjiku Mwangi": (3, 3, 1, 6, 3),
            "Nurul Hakim": (4, 2, 0, 2, 4),
            "Bereket Tadesse": (3, 1, 1, 3, 2),
            "Yusuke Inoue": (3, 1, 0, 0, 3),
        }
        proposals = {}
        for name, (old, prs, caught, recv, _) in wave_29.items():
            sig = ts.Signals(prs_merged=prs, must_fix_caught=caught, must_fix_received=recv)
            proposed = max(ts.MIN_SCORE, min(ts.MAX_SCORE, old + ts.score_delta(sig)))
            proposals[name] = ts.Proposal(old_score=old, proposed_score=proposed, signals=sig)
        out = ts.apply_distribution_discipline(proposals)
        self.assertEqual(out, {n: v[4] for n, v in wave_29.items()})


class NegativeSignalPass(unittest.TestCase):
    def test_clean_line_shows_numbers_not_none(self) -> None:
        line = ts.negative_signal_line("Nadia Khoury", ts.Signals(prs_merged=2, must_fix_caught=3))
        self.assertIn("metrics clean", line)
        self.assertNotEqual(line.strip().lower(), "none")
        self.assertIn("prs_merged=2", line)

    def test_negative_line_cites_gap(self) -> None:
        line = ts.negative_signal_line("X", ts.Signals(prs_merged=1, ci_red_merges=2))
        self.assertIn("2 CI-red merge", line)

    def test_validate_flags_bare_none(self) -> None:
        lines = ["None", "- none", "N/A", "Aino: metrics clean: prs_merged=1"]
        offenders = ts.validate_negative_signal_pass(lines)
        self.assertEqual(len(offenders), 3)

    def test_validate_clean_pass_returns_empty(self) -> None:
        lines = ["Aino: metrics clean: prs_merged=1", "X: 1 CI-red merge(s)"]
        self.assertEqual(ts.validate_negative_signal_pass(lines), [])


class RetirementTrigger(unittest.TestCase):
    def test_sustained_bottom_tier_fires(self) -> None:
        fired, reason = ts.retirement_trigger([3, 2, 2, 1], [0, 0, 0, 0])
        self.assertTrue(fired)
        self.assertIn("bottom-tier", reason)

    def test_repeated_ci_red_fires(self) -> None:
        fired, reason = ts.retirement_trigger([3, 3, 3], [1, 2, 1])
        self.assertTrue(fired)
        self.assertIn("CI-red", reason)

    def test_not_enough_history_never_fires(self) -> None:
        fired, _ = ts.retirement_trigger([1, 1], [1, 1])
        self.assertFalse(fired)

    def test_healthy_does_not_fire(self) -> None:
        fired, _ = ts.retirement_trigger([4, 4, 5], [0, 0, 0])
        self.assertFalse(fired)


if __name__ == "__main__":
    unittest.main()
