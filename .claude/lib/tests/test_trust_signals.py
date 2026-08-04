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
  * score_delta is bidirectional and clamped to [-2, +2].
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
        self.assertEqual(ts._verdict_kind(v.verdict), "approved")

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
        """`_normalize_verdict_token`'s alnum-stripping, not just casefold.

        A verdict field with no surrounding whitespace before the bold
        marker (`RequestOrReplied: **ChangesRequested**`) is captured with
        its LEADING `**` intact — only the trailing `**` is stripped by the
        field regex's `\\**\\s*$` tail, so the captured token is literally
        `"**ChangesRequested"`. Removing `_normalize_verdict_token`'s
        `re.sub(r"[^a-z0-9]", "", ...)` step (leaving only `.casefold()`)
        does not fail any other test in this file — `_normalize_verdict_token`
        needs its own direct assertion.
        """
        body = "Requestor: A\nRequestee: B\nRequestOrReplied: **ChangesRequested**\n"
        v = ts.parse_verdicts([body])[0]
        self.assertEqual(v.verdict, "**ChangesRequested")
        self.assertEqual(ts._verdict_kind(v.verdict), "changesrequested")
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


class DistributionDiscipline(unittest.TestCase):
    def test_five_reserved_for_top_performer(self) -> None:
        proposals = {
            "Top": (5, ts.Signals(prs_merged=5, must_fix_caught=3)),
            "AlsoFive": (5, ts.Signals(prs_merged=2)),
        }
        out = ts.apply_distribution_discipline(proposals)
        self.assertEqual(out["Top"], 5)
        self.assertEqual(out["AlsoFive"], 4)  # capped — not the top performer

    def test_four_passes_through(self) -> None:
        proposals = {"X": (4, ts.Signals(prs_merged=2))}
        self.assertEqual(ts.apply_distribution_discipline(proposals)["X"], 4)

    def test_no_five_when_top_is_not_positive(self) -> None:
        proposals = {"X": (5, ts.Signals())}
        self.assertEqual(ts.apply_distribution_discipline(proposals)["X"], 4)


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
