#!/usr/bin/env python3
"""Tests for the review-comment format gate's fail-open surfaces (closes #932).

Three ways a real review comment carrying an explicit approval reached the
counting hook as *zero reviews*, indistinguishable from no review at all:

1. **Wrong field name.** `Requestor` + `Requestee` present, `RequestOrReplied`
   absent (the author wrote `Verdict:`), and `check()` returned None — allow.
2. **REST evasion.** `is_comment_command` matched only `gh pr comment`, so a
   verdict posted with `gh api -X POST .../issues/<N>/comments` never reached
   the hook. Matching the command is necessary but not sufficient: the body
   also has to be extractable from `--input` / `-f body=` / `-F body=@`.
3. **Outside the trailer block.** `validate_pr_review._trailer_block_substring`
   scopes field extraction to everything after the LAST sole `---` line, so
   charter fields above a later prose horizontal rule parse as None even when
   the literal `RequestOrReplied:` is on the page.

Fixture discipline (`feedback_fixture_makes_guard_assertion_inert`,
`feedback_passing_repro_masks_bug`): every body below is a **verbatim copy of a
real comment posted on 2026-07-09**, not a synthetic three-liner. A synthetic
fixture would not have reproduced defect 3 at all — the shape only appears in
bodies long enough to contain a prose `---`.

  fixtures/real_verdict_nearmiss_deploy567.txt
      Lucas Ferreira's deploy#567 verdict, pre-patch. `Verdict: Approved` on
      line 3, no sole `---` anywhere. The near-miss shape.
  fixtures/real_verdict_nearmiss_main930.txt
      Aino Virtanen's main#930 Changes-Requested verdict, never patched.
      `Verdict:` plus four prose `---` rules.
  fixtures/real_verdict_outside_trailer_main930.txt
      DERIVED, not observed. The main930 body with the label renamed in place
      to `RequestOrReplied:` — exactly what a well-intentioned label-only fix
      would have produced. Nobody posted this shape; it is the counterfactual
      that proves a rename alone does not rescue such a comment. It still
      parses as None, and `FixtureRealismTests` asserts precisely that.

Command realism (#934 review, Wanjiku Mwangi)
=============================================

Fixture realism is not enough. The first cut of this suite passed every REST
command as a bare unquoted literal (`/tmp/body.json`) while production posts
carry quotes and `$CLAUDE_JOB_DIR` — so four fail-open paths sat green,
including the charter-prescribed `--body-file` form (`agents.md:429`, 144
call sites). That is `feedback_passing_repro_masks_bug`: a green repro that
used a different invocation form than production.

The commands below are transcribed from the 2026-07-09 transcripts verbatim,
quotes and variables intact. `_TRANSCRIPT_*` names mark them.

Run: python3 -m unittest discover -s .claude/hooks/tests \
         -p "test_validate_review_comment_format_failopen.py"
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from typing import ClassVar
from unittest import mock

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
_LIB_DIR = _HOOKS_DIR.parent / "lib"
sys.path.insert(0, str(_HOOKS_DIR))
sys.path.insert(0, str(_LIB_DIR))

import validate_review_comment_format as hook  # noqa: E402

_FIXTURES = _HERE / "fixtures"


def _fixture(name: str) -> str:
    body = (_FIXTURES / name).read_text()
    if not body.strip():
        raise AssertionError(f"fixture {name} is empty — the instrument is dead")
    return body


def _bash_input(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


def _decision(result: dict | None) -> str:
    """Normalize check()'s return into a decision word."""
    if result is None:
        return "allow"
    return result.get("decision", "allow")


class FixtureRealismTests(unittest.TestCase):
    """The fixtures must carry the defect, or the tests below prove nothing.

    "Realism" here does not mean every fixture was observed in the wild. Two are
    verbatim posted comments; `real_verdict_outside_trailer_main930.txt` is a
    DERIVED counterfactual — the label-only fix nobody shipped — and
    `test_trailer_fixture_carries_the_field_yet_parses_as_none` is what makes it
    load-bearing rather than decorative (#934 review, Santiago Ferreira).
    """

    def test_nearmiss_fixtures_lack_the_charter_field(self) -> None:
        for name in (
            "real_verdict_nearmiss_deploy567.txt",
            "real_verdict_nearmiss_main930.txt",
        ):
            body = _fixture(name)
            self.assertIn("Requestor:", body)
            self.assertIn("Requestee:", body)
            self.assertIn("Verdict:", body)
            self.assertNotIn("RequestOrReplied:", body)

    def test_deploy567_fixture_has_no_separator(self) -> None:
        body = _fixture("real_verdict_nearmiss_deploy567.txt")
        self.assertEqual(
            [ln for ln in body.splitlines() if ln.strip() == "---"],
            [],
            "the near-miss fixture must isolate defect 1 from defect 3",
        )

    def test_trailer_fixture_carries_the_field_yet_parses_as_none(self) -> None:
        """The label-rename fixture is only meaningful if the rename is inert."""
        import validate_pr_review as counting_hook

        body = _fixture("real_verdict_outside_trailer_main930.txt")
        self.assertIn("RequestOrReplied:", body)
        self.assertIsNone(
            counting_hook._extract_charter_field("RequestOrReplied", body),
            "fixture must reproduce the outside-trailer hazard",
        )


class NearMissBlocksTests(unittest.TestCase):
    """Defect 1 — Requestor + Requestee present, RequestOrReplied absent."""

    def test_verdict_field_is_blocked(self) -> None:
        body = _fixture("real_verdict_nearmiss_deploy567.txt")
        cmd = f"gh pr comment 567 --repo noorinalabs/noorinalabs-deploy --body '{body}'"
        result = hook.check(_bash_input(cmd))
        self.assertEqual(_decision(result), "block")

    def test_diagnostic_names_the_charter_field_and_line(self) -> None:
        body = _fixture("real_verdict_nearmiss_deploy567.txt")
        cmd = f"gh pr comment 567 --body '{body}'"
        result = hook.check(_bash_input(cmd))
        assert result is not None
        reason = result["reason"]
        self.assertIn("RequestOrReplied:", reason)
        self.assertIn("pull-requests.md", reason)

    def test_diagnostic_names_verdict_when_verdict_was_used(self) -> None:
        body = _fixture("real_verdict_nearmiss_main930.txt")
        cmd = f"gh pr comment 930 --body '{body}'"
        result = hook.check(_bash_input(cmd))
        assert result is not None
        self.assertIn("Verdict:", result["reason"])

    def test_no_block_when_only_requestor_present(self) -> None:
        """A comment that is not a charter review comment stays out of scope."""
        cmd = "gh pr comment 930 --body 'Requestor: Aino Virtanen'"
        self.assertEqual(_decision(hook.check(_bash_input(cmd))), "allow")

    def test_conforming_request_comment_still_allowed(self) -> None:
        body = (
            "Requestor: Nadia Khoury\n"
            "Requestee: Aino Virtanen\n"
            "RequestOrReplied: Request\n"
            "TechDebt: None\n"
        )
        cmd = f"gh pr comment 930 --body '{body}'"
        self.assertEqual(_decision(hook.check(_bash_input(cmd))), "allow")


class OutsideTrailerBlocksTests(unittest.TestCase):
    """Defect 3 — fields present but outside the trailer-block scope."""

    def test_outside_trailer_is_blocked(self) -> None:
        body = _fixture("real_verdict_outside_trailer_main930.txt")
        cmd = f"gh pr comment 930 --body '{body}'"
        result = hook.check(_bash_input(cmd))
        self.assertEqual(_decision(result), "block")

    def test_diagnostic_explains_the_separator(self) -> None:
        body = _fixture("real_verdict_outside_trailer_main930.txt")
        cmd = f"gh pr comment 930 --body '{body}'"
        result = hook.check(_bash_input(cmd))
        assert result is not None
        self.assertIn("---", result["reason"])

    def test_fields_after_last_separator_are_allowed(self) -> None:
        """The shape Nadia REST-PATCHed on: prose, rule, then the trailer."""
        body = (
            "Some prose.\n\n---\n\nMore prose.\n\n---\n"
            "Requestor: Aino Virtanen\n"
            "Requestee: Nadia Khoury\n"
            "RequestOrReplied: Approved\n"
            "TechDebt: None\n"
        )
        cmd = f"gh pr comment 930 --repo noorinalabs/noorinalabs-main --body '{body}'"
        with mock.patch.object(hook, "get_branch_name", return_value="N.Khoury/0928-x"):
            self.assertEqual(_decision(hook.check(_bash_input(cmd))), "allow")


class RestCommentCommandTests(unittest.TestCase):
    """Defect 2 — REST comment-creation must be recognized."""

    def test_rest_post_is_a_comment_command(self) -> None:
        cmd = (
            "gh api -X POST repos/noorinalabs/noorinalabs-deploy/issues/567/comments "
            "--input /tmp/body.json"
        )
        self.assertTrue(hook.is_comment_command(cmd))

    def test_rest_field_form_is_a_comment_command(self) -> None:
        cmd = "gh api repos/o/r/issues/42/comments -f body='hello'"
        self.assertTrue(hook.is_comment_command(cmd))

    def test_rest_get_is_not_a_comment_command(self) -> None:
        """Reading comments must not be mistaken for posting one."""
        cmd = "gh api repos/o/r/issues/42/comments --jq '.[].body'"
        self.assertFalse(hook.is_comment_command(cmd))

    def test_unrelated_gh_api_is_not_a_comment_command(self) -> None:
        cmd = "gh api repos/o/r/pulls/42 --jq .head.sha"
        self.assertFalse(hook.is_comment_command(cmd))

    def test_rest_pr_number_extracted(self) -> None:
        cmd = "gh api -X POST repos/o/r/issues/567/comments --input b.json"
        self.assertEqual(hook.extract_pr_number(cmd), "567")

    def test_rest_input_file_body_is_blocked_on_near_miss(self) -> None:
        """End-to-end: the exact invocation that evaded the hook today."""
        body = _fixture("real_verdict_nearmiss_deploy567.txt")
        with tempfile.TemporaryDirectory() as td:
            payload = Path(td) / "body.json"
            payload.write_text(json.dumps({"body": body}))
            cmd = (
                "gh api -X POST repos/noorinalabs/noorinalabs-deploy/issues/567/comments "
                f"--input {payload}"
            )
            result = hook.check(_bash_input(cmd))
        self.assertEqual(_decision(result), "block")

    def test_rest_f_body_inline_is_blocked_on_near_miss(self) -> None:
        body = "Requestor: Lucas Ferreira\nRequestee: Nurul Hakim\nVerdict: Approved\n"
        cmd = f"gh api -X POST repos/o/r/issues/567/comments -f body='{body}'"
        self.assertEqual(_decision(hook.check(_bash_input(cmd))), "block")

    def test_rest_F_body_at_file_is_blocked_on_near_miss(self) -> None:
        body = _fixture("real_verdict_nearmiss_deploy567.txt")
        with tempfile.TemporaryDirectory() as td:
            raw = Path(td) / "body.md"
            raw.write_text(body)
            cmd = f"gh api -X POST repos/o/r/issues/567/comments -F body=@{raw}"
            result = hook.check(_bash_input(cmd))
        self.assertEqual(_decision(result), "block")

    def test_rest_unreadable_body_does_not_crash(self) -> None:
        """`--input -` (stdin) leaves no body on disk; must not raise."""
        cmd = "gh api -X POST repos/o/r/issues/567/comments --input -"
        try:
            result = hook.check(_bash_input(cmd))
        except Exception as exc:  # noqa: BLE001
            self.fail(f"hook raised on unreadable body: {exc!r}")
        self.assertIn(_decision(result), {"allow", "block"})


class BodyFileTests(unittest.TestCase):
    """The charter-prescribed form (`agents.md:429`) must be read, not skipped."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)
        self.addCleanup(self._td.cleanup)
        self.body_path = self.tmp / "aino_930_comment.md"
        self.body_path.write_text(_fixture("real_verdict_nearmiss_deploy567.txt"))

    def test_body_file_is_extracted(self) -> None:
        cmd = f"gh pr comment 567 --body-file {self.body_path}"
        self.assertIsNotNone(hook.extract_comment_body(cmd))

    def test_body_file_near_miss_is_blocked(self) -> None:
        cmd = (
            f"gh pr comment 567 --repo noorinalabs/noorinalabs-deploy --body-file {self.body_path}"
        )
        self.assertEqual(_decision(hook.check(_bash_input(cmd))), "block")

    def test_body_file_quoted_path_is_blocked(self) -> None:
        cmd = f'gh pr comment 567 --body-file "{self.body_path}"'
        self.assertEqual(_decision(hook.check(_bash_input(cmd))), "block")

    def test_body_file_envvar_path_is_blocked(self) -> None:
        """Transcript form: the hook process inherits the environment."""
        with mock.patch.dict(os.environ, {"CLAUDE_JOB_DIR": str(self.tmp)}):
            cmd = 'gh pr comment 567 --body-file "$CLAUDE_JOB_DIR/aino_930_comment.md"'
            self.assertEqual(_decision(hook.check(_bash_input(cmd))), "block")

    def test_body_file_tilde_path_is_blocked(self) -> None:
        with mock.patch.dict(os.environ, {"HOME": str(self.tmp)}):
            cmd = "gh pr comment 567 --body-file ~/aino_930_comment.md"
            self.assertEqual(_decision(hook.check(_bash_input(cmd))), "block")


class TranscriptCommandTests(unittest.TestCase):
    """Verbatim invocations from the 2026-07-09 transcripts. Copied, not retyped."""

    # Wanjiku Mwangi's main#930 verdicts — both posted exactly this way, and
    # both parsed as zero reviews.
    _TRANSCRIPT_WANJIKU = (
        "gh api -X POST repos/noorinalabs/noorinalabs-main/issues/930/comments "
        '-F body=@"$CLAUDE_JOB_DIR/tmp/wanjiku_930_comment.md"'
    )
    # Lucas Ferreira's deploy#567 verdict.
    _TRANSCRIPT_LUCAS = (
        "gh api -X POST repos/noorinalabs/noorinalabs-deploy/issues/567/comments "
        '--input "$CLAUDE_JOB_DIR/tmp/lucas_567.json"'
    )

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.job = Path(self._td.name)
        self.addCleanup(self._td.cleanup)
        (self.job / "tmp").mkdir()
        body = _fixture("real_verdict_nearmiss_deploy567.txt")
        (self.job / "tmp" / "wanjiku_930_comment.md").write_text(body)
        (self.job / "tmp" / "lucas_567.json").write_text(json.dumps({"body": body}))

    def test_wanjiku_transcript_command_is_blocked(self) -> None:
        """The command that produced the incident must not survive the fix."""
        with mock.patch.dict(os.environ, {"CLAUDE_JOB_DIR": str(self.job)}):
            result = hook.check(_bash_input(self._TRANSCRIPT_WANJIKU))
        self.assertEqual(_decision(result), "block")

    def test_lucas_transcript_command_is_blocked(self) -> None:
        with mock.patch.dict(os.environ, {"CLAUDE_JOB_DIR": str(self.job)}):
            result = hook.check(_bash_input(self._TRANSCRIPT_LUCAS))
        self.assertEqual(_decision(result), "block")

    def test_quoted_at_path_is_blocked(self) -> None:
        """`-F body=@"/abs/path"` — quotes were not stripped on this branch."""
        path = self.job / "tmp" / "wanjiku_930_comment.md"
        cmd = f'gh api -X POST repos/o/r/issues/930/comments -F body=@"{path}"'
        self.assertEqual(_decision(hook.check(_bash_input(cmd))), "block")


class UnreadableBodyBlocksTests(unittest.TestCase):
    """Once the observable forms are read, the residual must BLOCK, not advise.

    `feedback_safety_direction_over_ux_friction`: a recognized comment-create
    command whose body cannot be read is exactly the state with no clean
    auto-fix. `feedback_generic_prompt_hook_advisory_decay`: the stderr line
    this replaces said nothing across five PRs and nine verdicts.
    """

    def test_stdin_input_is_blocked(self) -> None:
        cmd = "gh api -X POST repos/o/r/issues/567/comments --input -"
        self.assertEqual(_decision(hook.check(_bash_input(cmd))), "block")

    def test_shell_variable_path_is_blocked(self) -> None:
        """`--input "$J"` — a shell var, not an env var; unresolvable by design."""
        cmd = 'gh api -X POST repos/o/r/issues/930/comments --input "$J"'
        self.assertEqual(_decision(hook.check(_bash_input(cmd))), "block")

    def test_missing_file_is_blocked(self) -> None:
        cmd = "gh pr comment 930 --body-file /nonexistent/nowhere.md"
        self.assertEqual(_decision(hook.check(_bash_input(cmd))), "block")

    def test_diagnostic_names_the_remedy(self) -> None:
        cmd = "gh api -X POST repos/o/r/issues/567/comments --input -"
        result = hook.check(_bash_input(cmd))
        assert result is not None
        self.assertIn("--body-file", result["reason"])

    def test_non_comment_command_still_allowed(self) -> None:
        """The block must not leak onto commands that post no comment."""
        self.assertEqual(_decision(hook.check(_bash_input("gh pr view 42"))), "allow")
        self.assertEqual(
            _decision(hook.check(_bash_input("gh api repos/o/r/issues/42/comments --jq ."))),
            "allow",
        )


class HarnessInvocationCorpusTests(unittest.TestCase):
    """Replay REAL harness payloads. The invocation comes from the caller.

    Oyunbileg Batbayar, on #934: repairing three specific holes closes one
    night's incident, not the class. A hook whose tests pass a bare
    `/tmp/body.json` where production passes a quoted `$CLAUDE_JOB_DIR` path
    "has not been tested against production; it has been tested against a
    fixture chosen to make it pass."

    So this class does not contain a single hand-written command. It replays
    `fixtures/real_comment_invocations.jsonl`, harvested by
    `.claude/lib/extract_comment_invocations.py` from the harness's own
    session transcripts — the exact `tool_use` payloads a PreToolUse hook
    receives.

    The invariant is recognition, not verdict: whatever a command's body turns
    out to be, `is_comment_command` MUST return True for every invocation that
    actually created a PR comment. A hook that does not recognize the command
    cannot validate it, and fails open before any body is read.

    Against the pre-fixup hook this corpus is RED at 72 of 121. It caught two
    fail-opens nobody had enumerated:

    * `_split_segments` split on `&&`, `||`, `|`, `;` but NOT on newlines, so
      the overwhelmingly common `cd /repo\\ngh pr comment ...` shape never
      reached the matcher (64 of the 72).
    * `URL=$(gh api -X POST ...)` executes, but the env-prefix stripper's
      `\\S*\\s+` swallowed `URL=$(gh ` whole, leaving a segment starting at
      `api` (24 of the 72).

    The second one is instructive twice over: the HARVESTER shared that exact
    blind spot, so it silently dropped those commands and the corpus first
    reported a clean zero. A corpus built with the parser it audits will agree
    with it. Both segmenters were fixed; the negative cases below exist so a
    recognizer cannot pass the invariant by matching everything.
    """

    CORPUS = _FIXTURES / "real_comment_invocations.jsonl"
    rows: ClassVar[list[dict]] = []

    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = [
            json.loads(line) for line in cls.CORPUS.read_text().splitlines() if line.strip()
        ]

    def test_corpus_is_not_empty(self) -> None:
        """A replay suite over zero invocations passes vacuously."""
        self.assertGreater(len(self.rows), 50, "corpus too small to be meaningful")

    def test_corpus_covers_every_body_form(self) -> None:
        """If a form is absent, this suite cannot speak to it. Verify the instrument."""
        forms = {row["form"] for row in self.rows}
        for required in ("body-file", "heredoc", "body-inline", "field-at-file", "input-file"):
            self.assertIn(required, forms, f"corpus lacks the {required!r} invocation form")

    def test_corpus_contains_multiline_invocations(self) -> None:
        """The `cd /repo\\ngh pr comment` shape must be present, or the newline
        regression this class caught could silently return."""
        multiline = [r for r in self.rows if "\n" in r["command"]]
        self.assertGreater(len(multiline), 10, "corpus lacks newline-separated commands")

    def test_every_real_invocation_is_recognized(self) -> None:
        """The class-closing invariant."""
        unrecognized = [r for r in self.rows if not hook.is_comment_command(r["command"])]
        if unrecognized:
            forms = sorted({r["form"] for r in unrecognized})
            sample = unrecognized[0]["command"][:160].replace("\n", "\\n")
            self.fail(
                f"{len(unrecognized)}/{len(self.rows)} real comment-creating "
                f"invocations are NOT recognized by is_comment_command. "
                f"Forms: {forms}. First: {sample!r}"
            )

    def test_recognizer_still_discriminates(self) -> None:
        """A recognizer that returns True for everything would pass the invariant.

        Both classes, per `feedback_silent_zero_is_not_a_measurement`.
        """
        negatives = [
            "gh pr view 42",
            "gh issue comment 42 --body x",
            "gh api repos/o/r/issues/42/comments --jq '.[].body'",
            "gh api repos/o/r/pulls/42 --jq .head.sha",
            "cd /repo\ngit commit -m 'gh pr comment 42'",
            "ls -la",
        ]
        for command in negatives:
            self.assertFalse(
                hook.is_comment_command(command),
                f"recognizer over-matched a non-comment-create command: {command!r}",
            )


class FieldScopingBothDirectionsTests(unittest.TestCase):
    """#934: the unscoped `Requestor` probe failed OPEN and CLOSED on one line.

    `has_requestor.group(1)` was not discarded — it fed `_extract_lastname`,
    which takes the FINAL token, which fed the Requestor/Requestee swap
    heuristic, which ends in `decision: block`. So the same `re.search`:

    * **fail-closed** — BLOCKED a correctly-formed, correctly-directed verdict
      whenever the reviewer explained the rule in prose and that prose's last
      token was the PR author's surname. The single most likely sentence anyone
      writes on a PR about this hook.
    * **fail-open** — PASSED a genuinely swapped trailer whenever an earlier
      prose match produced a non-author surname first.

    Which failure you got depended on the reviewer's sentence.

    Fixture discipline, learned the hard way inside this very fix: the first
    proposed repro ended its prose with a full stop, so `_extract_lastname`
    returned `''`, which matches no surname and blocks nothing. **A repro whose
    sentence ends in a period cannot go red.** The fail-closed fixture below
    therefore ends on the author's bare surname, and `test_plants_are_applied`
    asserts that the trigger is actually reachable — an unapplied plant and a
    passing hook are indistinguishable from the output alone.
    """

    BRANCH = "N.Khoury/0928-dynamic-gate-memory"  # author surname: Khoury
    TRAILER_OK = (
        "\n---\nRequestor: Wanjiku Mwangi\nRequestee: Nadia Khoury\n"
        "RequestOrReplied: Approved\nTechDebt: None\n"
    )
    TRAILER_SWAPPED = (
        "\n---\nRequestor: Nadia Khoury\nRequestee: Wanjiku Mwangi\n"
        "RequestOrReplied: Approved\nTechDebt: None\n"
    )
    # Ends on the bare surname — no trailing punctuation. See class docstring.
    PROSE_ENDING_IN_AUTHOR_SURNAME = (
        "the fields must read Requestor: Wanjiku Mwangi, Requestee: Khoury"
    )
    PROSE_BENIGN = "I reviewed this. Requestor: Wanjiku Mwangi is how it should read"

    def _check(self, body: str) -> str:
        cmd = f"gh pr comment 930 --repo noorinalabs/noorinalabs-main --body '{body}'"
        with mock.patch.object(hook, "get_branch_name", return_value=self.BRANCH):
            return _decision(hook.check(_bash_input(cmd)))

    def test_plants_are_applied(self) -> None:
        """Both fixtures must actually reach the trigger, or the tests are inert."""
        author = hook.extract_branch_author_lastname(self.BRANCH)
        self.assertEqual(author, "Khoury")

        # Fail-closed plant: the UNSCOPED first match must yield the author's
        # surname. If it does not, the old code path was never exercised.
        scan = hook.strip_code_regions(self.PROSE_ENDING_IN_AUTHOR_SURNAME + self.TRAILER_OK)
        first = re.search(r"\*{0,2}Requestor:\*{0,2}\s*(.+)", scan)
        assert first is not None
        self.assertEqual(
            hook._extract_lastname(first.group(1)),
            author,
            "fail-closed plant is inert: unscoped first match does not yield the author",
        )

        # And the fixture must not be the period-ending shape that cannot go red.
        self.assertFalse(self.PROSE_ENDING_IN_AUTHOR_SURNAME.rstrip().endswith("."))

        # Fail-open plant: the trailer must really be swapped, and the unscoped
        # first match must NOT yield the author (else the old code blocked by luck).
        swapped = self.PROSE_BENIGN + self.TRAILER_SWAPPED
        self.assertEqual(hook.extract_charter_field("Requestor", swapped), "Nadia Khoury")
        scan2 = hook.strip_code_regions(swapped)
        first2 = re.search(r"\*{0,2}Requestor:\*{0,2}\s*(.+)", scan2)
        assert first2 is not None
        self.assertNotEqual(hook._extract_lastname(first2.group(1)), author)

    def test_fail_closed_correct_verdict_is_allowed(self) -> None:
        body = self.PROSE_ENDING_IN_AUTHOR_SURNAME + self.TRAILER_OK
        self.assertEqual(self._check(body), "allow")

    def test_fail_open_swapped_trailer_is_blocked(self) -> None:
        body = self.PROSE_BENIGN + self.TRAILER_SWAPPED
        self.assertEqual(self._check(body), "block")

    def test_swapped_trailer_without_prose_still_blocked(self) -> None:
        self.assertEqual(self._check(self.TRAILER_SWAPPED.lstrip("\n")), "block")

    def test_period_ending_prose_is_allowed(self) -> None:
        """The inert shape: yields '', matches nothing. Allowed before and after."""
        body = "never write Requestor: Value shapes in prose." + self.TRAILER_OK
        self.assertEqual(self._check(body), "allow")

    def test_backticked_prose_is_allowed(self) -> None:
        body = f"the fields read `{self.PROSE_ENDING_IN_AUTHOR_SURNAME}`" + self.TRAILER_OK
        self.assertEqual(self._check(body), "allow")


class TrailerHelperSingularityTests(unittest.TestCase):
    """One definition of the charter trailer, or the rule drifts (#934).

    A second hand-maintained copy is what produced the false
    `feedback_pr_review_verdict_format` memory: the convention described
    in one place, implemented in another, nothing tying them together. These
    assertions make a second copy fail CI rather than rot quietly.
    """

    def test_both_hooks_share_one_function_object(self) -> None:
        import charter_trailer as ct
        import validate_pr_review as counting

        self.assertIs(counting._extract_charter_field, ct.extract_charter_field)
        self.assertIs(counting._trailer_block_substring, ct.trailer_block_substring)
        self.assertIs(counting._strip_code_regions, ct.strip_code_regions)
        self.assertIs(hook.extract_charter_field, ct.extract_charter_field)
        self.assertIs(hook.strip_code_regions, ct.strip_code_regions)

    def test_format_hook_does_not_import_the_counting_hook(self) -> None:
        """The cross-hook import was a stopgap; the shared module replaces it."""
        self.assertFalse(hasattr(hook, "_counting_hook"))

    def test_no_second_definition_anywhere(self) -> None:
        """Scan hooks AND lib. Scoping this to one directory would make the
        guard silently stop guarding the moment the module moved — which it
        just did (main#932)."""
        defs = {"strip_code_regions", "trailer_block_substring", "extract_charter_field"}
        searched = sorted(_HOOKS_DIR.glob("*.py")) + sorted(_LIB_DIR.glob("*.py"))
        self.assertGreater(len(searched), 20, "file sweep found almost nothing — verify the glob")

        canonical = _LIB_DIR / "charter_trailer.py"
        self.assertTrue(canonical.is_file(), "the one definition must exist where we think")

        offenders = [
            f"{path.relative_to(canonical.parent.parent)}:{name}"
            for path in searched
            if path != canonical
            for name in defs
            if re.search(rf"^def _?{name}\(", path.read_text(), re.MULTILINE)
        ]
        self.assertEqual(offenders, [], f"trailer convention redefined: {offenders}")

    def test_the_sweep_can_actually_find_a_definition(self) -> None:
        """Verify the instrument: the scan must match a known definition."""
        canonical = (_LIB_DIR / "charter_trailer.py").read_text()
        for name in ("strip_code_regions", "trailer_block_substring", "extract_charter_field"):
            self.assertRegex(canonical, rf"(?m)^def {name}\(")


def _reason(result: dict | None) -> str:
    """Return a block's reason text, narrowing `dict | None` for the type checker."""
    assert result is not None, "expected a block, got allow (None)"
    return str(result.get("reason", ""))


_CONFORMING_TRAILER = (
    "Review prose that says something.\n"
    "\n"
    "---\n"
    "Requestor: Wanjiku Mwangi\n"
    "Requestee: Aino Virtanen\n"
    "RequestOrReplied: Approved\n"
    "TechDebt: none\n"
)

_NEARMISS_TRAILER = (
    "Review prose that says something.\n"
    "\n"
    "---\n"
    "Requestor: Wanjiku Mwangi\n"
    "Requestee: Aino Virtanen\n"
    "Verdict: Approved\n"
)


class WriteThenPostTests(unittest.TestCase):
    """A heredoc writing the path that the same command then posts (#934 review).

    A PreToolUse hook runs BEFORE the command, so the file does not exist yet.
    The body is nonetheless in the command string. Reading disk and blocking on
    the miss told the author "the file does not exist" about a command whose own
    first line creates it — and `feedback_safety_direction_over_ux_friction`
    licenses a hard block only when the hook *cannot* auto-fix cleanly. Here it
    can: read the heredoc.
    """

    def test_heredoc_body_is_recovered_when_file_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "verdict.md")
            self.assertFalse(os.path.exists(path), "precondition: PreToolUse precedes the write")
            command = (
                f"cat > {path} <<'EOF'\n{_CONFORMING_TRAILER}EOF\n"
                f"gh pr comment 826 --body-file {path}"
            )
            self.assertEqual(hook.extract_comment_body(command), _CONFORMING_TRAILER)
            self.assertEqual(_decision(hook.check(_bash_input(command))), "allow")

    def test_heredoc_nearmiss_still_blocks(self) -> None:
        """Recovering the body must not become a way to skip validating it."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "verdict.md")
            command = (
                f"cat > {path} <<'EOF'\n{_NEARMISS_TRAILER}EOF\n"
                f"gh pr comment 826 --body-file {path}"
            )
            result = hook.check(_bash_input(command))
            self.assertEqual(_decision(result), "block")
            self.assertIn("RequestOrReplied", _reason(result))

    def test_heredoc_wins_over_a_stale_file_at_the_same_path(self) -> None:
        """The ordering that a naive disk-first fallback would have gotten wrong.

        A stale CONFORMING body sits at the path. The command overwrites it with
        a NEAR-MISS and posts that. Disk-first validates the stale body, allows,
        and the uncountable verdict is posted anyway.

        **One stale file is sufficient.** Disk-first is wrong by construction,
        not because some count of corpus rows currently have live paths — that
        count is a property of one machine at one minute, and citing it would
        hand the next reader a perishable premise for a permanent conclusion.
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "verdict.md")
            Path(path).write_text(_CONFORMING_TRAILER)
            command = (
                f"cat > {path} <<'EOF'\n{_NEARMISS_TRAILER}EOF\n"
                f"gh pr comment 826 --body-file {path}"
            )
            self.assertEqual(
                hook.extract_comment_body(command),
                _NEARMISS_TRAILER,
                "the heredoc is what will be posted; the file on disk is stale",
            )
            self.assertEqual(_decision(hook.check(_bash_input(command))), "block")

    def test_unexported_shell_variable_path_resolves_via_heredoc(self) -> None:
        """`T=$(mktemp -d); cat > $T/v.md <<EOF` — neither side can expand `$T`.

        Both sides resolve to the same unexpanded string, so the heredoc still
        matches its own path and the body is recovered without touching disk.
        """
        command = (
            f"cat > $T/verdict.md <<'EOF'\n{_CONFORMING_TRAILER}EOF\n"
            "gh pr comment 826 --body-file $T/verdict.md"
        )
        self.assertNotIn("T", os.environ.get("T", "") or "x")
        self.assertEqual(hook.extract_comment_body(command), _CONFORMING_TRAILER)

    def test_later_heredoc_write_wins(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "v.md")
            command = (
                f"cat > {path} <<'EOF'\nfirst\nEOF\n"
                f"cat > {path} <<'EOF'\n{_CONFORMING_TRAILER}EOF\n"
                f"gh pr comment 826 --body-file {path}"
            )
            self.assertEqual(hook.extract_comment_body(command), _CONFORMING_TRAILER)

    def test_heredoc_to_a_different_path_is_not_borrowed(self) -> None:
        """A heredoc writing some OTHER file must not be mistaken for the body."""
        with tempfile.TemporaryDirectory() as tmp:
            other = os.path.join(tmp, "msg.txt")
            target = os.path.join(tmp, "verdict.md")
            command = (
                f"cat > {other} <<'EOF'\n{_CONFORMING_TRAILER}EOF\n"
                f"gh pr comment 826 --body-file {target}"
            )
            self.assertIsNone(hook.extract_comment_body(command))
            self.assertEqual(_decision(hook.check(_bash_input(command))), "block")

    def test_rest_body_at_path_also_recovers_the_heredoc(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "v.md")
            command = (
                f"cat > {path} <<'EOF'\n{_NEARMISS_TRAILER}EOF\n"
                f'gh api repos/o/r/issues/826/comments -F body=@"{path}"'
            )
            self.assertEqual(hook.extract_rest_comment_body(command), _NEARMISS_TRAILER)
            self.assertEqual(_decision(hook.check(_bash_input(command))), "block")

    def test_rest_input_json_heredoc_is_decoded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "b.json")
            payload = json.dumps({"body": _NEARMISS_TRAILER})
            command = (
                f"cat > {path} <<'EOF'\n{payload}\nEOF\n"
                f"gh api repos/o/r/issues/826/comments --input {path}"
            )
            self.assertEqual(hook.extract_rest_comment_body(command), _NEARMISS_TRAILER)


class AppendComposesRatherThanReplacesTests(unittest.TestCase):
    """`>` truncates, `>>` appends (#934 review, Wanjiku Mwangi).

    `_heredoc_written_body` assigned on every match, so the LAST heredoc won
    regardless of its operator. Appending an innocuous footnote to a malformed
    verdict made the hook read only the footnote — a BLOCK became an ALLOW, in
    the hook whose entire subject is closing fail-opens. `>{1,2}` in the pattern
    put append in scope by design; only the composition was missing.

    The corpus cannot defend this. A zero in 121 rows harvested from one week of
    one team's transcripts is not a measurement of a shape's absence.
    """

    def _post(self, path: str) -> str:
        return f"gh pr comment 934 --body-file {path}"

    def test_appended_footnote_does_not_hide_a_near_miss(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "verdict.md")
            Path(path).write_text(_NEARMISS_TRAILER)
            command = f"cat >> {path} <<'EOF'\n(a footnote)\nEOF\n{self._post(path)}"

            self.assertEqual(
                hook.extract_comment_body(command),
                _NEARMISS_TRAILER + "(a footnote)\n",
                "the append must be composed onto the existing file, not replace it",
            )
            self.assertEqual(_decision(hook.check(_bash_input(command))), "block")

    def test_truncate_then_append_composes_both(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "v.md")
            Path(path).write_text("STALE — must be discarded by the `>`\n")
            command = (
                f"cat > {path} <<'EOF'\n{_NEARMISS_TRAILER}EOF\n"
                f"cat >> {path} <<'EOF'\n(a footnote)\nEOF\n{self._post(path)}"
            )
            self.assertEqual(
                hook.extract_comment_body(command),
                _NEARMISS_TRAILER + "(a footnote)\n",
                "`>` discards the stale file; `>>` then appends to the `>` output",
            )
            self.assertEqual(_decision(hook.check(_bash_input(command))), "block")

    def test_truncate_after_append_discards_the_append(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "v.md")
            command = (
                f"cat >> {path} <<'EOF'\nthrown away\nEOF\n"
                f"cat > {path} <<'EOF'\n{_CONFORMING_TRAILER}EOF\n{self._post(path)}"
            )
            self.assertEqual(hook.extract_comment_body(command), _CONFORMING_TRAILER)
            self.assertEqual(_decision(hook.check(_bash_input(command))), "allow")

    def test_append_to_a_nonexistent_path_has_an_empty_base(self) -> None:
        """`>>` creates the file. That base is empty, not unknowable."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "new.md")
            self.assertFalse(os.path.exists(path))
            command = f"cat >> {path} <<'EOF'\n{_CONFORMING_TRAILER}EOF\n{self._post(path)}"
            self.assertEqual(hook.extract_comment_body(command), _CONFORMING_TRAILER)
            self.assertEqual(_decision(hook.check(_bash_input(command))), "allow")

    def test_append_onto_an_unexpanded_variable_path_hard_blocks(self) -> None:
        """The hook cannot know what the append lands on, so it must not guess."""
        command = (
            "cat >> $NEVER_EXPORTED/v.md <<'EOF'\n(a footnote)\nEOF\n"
            "gh pr comment 934 --body-file $NEVER_EXPORTED/v.md"
        )
        self.assertIsInstance(
            hook._heredoc_written_body(command, "$NEVER_EXPORTED/v.md"),
            hook._Unreconstructable,
        )
        result = hook.check(_bash_input(command))
        self.assertEqual(_decision(result), "block")
        self.assertIn("APPENDS", _reason(result))

    def test_append_onto_an_unreadable_existing_file_hard_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "v.md")
            Path(path).write_bytes(b"\xff\xfe\x00 invalid utf-8")
            command = f"cat >> {path} <<'EOF'\n(a footnote)\nEOF\n{self._post(path)}"
            self.assertIsInstance(
                hook._heredoc_written_body(command, path), hook._Unreconstructable
            )
            self.assertEqual(_decision(hook.check(_bash_input(command))), "block")

    def test_a_conforming_append_still_allows(self) -> None:
        """Composition must not become a way to block every append."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "v.md")
            Path(path).write_text("Some review prose.\n")
            trailer = (
                "\n---\nRequestor: Wanjiku Mwangi\nRequestee: Aino Virtanen\n"
                "RequestOrReplied: Approved\nTechDebt: none"
            )
            command = f"cat >> {path} <<'EOF'\n{trailer}\nEOF\n{self._post(path)}"
            self.assertEqual(_decision(hook.check(_bash_input(command))), "allow")


class UnmodelledWritesHardBlockTests(unittest.TestCase):
    """Only heredoc redirects are composed; every other write must hard-block.

    #934 review, Santiago Ferreira. `_HEREDOC_WRITE_RE` models a redirect
    immediately followed by a heredoc, and nothing else. Every other way of
    writing the posted path was invisible to the composer, so `_body_for_path`
    fell back to disk — reinstating the stale-file fail-open that heredoc
    precedence exists to close. All six shapes below were ALLOW at `2743bbf`
    with a **conforming** file on disk and an uncountable body actually posted.

    Six of the 121 harvested rows carry such a write to their own posted path,
    mostly `jq -Rs '{body: .}' x.md > payload.json` feeding `--input`. That count
    is context. One stale file is sufficient, as for the ordering itself.

    This also subsumes #943 (`cat <<'EOF' > f`, `tee f <<'EOF'`).
    """

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "verdict.md")
        Path(self.path).write_text(_CONFORMING_TRAILER)
        self.post = f"gh pr comment 934 --body-file {self.path}"

    def _block_reason(self, write: str) -> str:
        result = hook.check(_bash_input(f"{write}\n{self.post}"))
        self.assertEqual(_decision(result), "block", f"must not fall back to disk: {write}")
        return _reason(result)

    def test_printf_append_blocks(self) -> None:
        self.assertIn("writes the body file", self._block_reason(f"printf 'x' >> {self.path}"))

    def test_echo_append_blocks(self) -> None:
        self._block_reason(f"echo '---' >> {self.path}")

    def test_cat_file_append_blocks(self) -> None:
        note = os.path.join(self.tmp, "note.md")
        Path(note).write_text("\n---\nPS\n")
        self._block_reason(f"cat {note} >> {self.path}")

    def test_jq_payload_redirect_blocks(self) -> None:
        """The corpus's most common shape: `jq … > payload.json` + `--input`."""
        payload = os.path.join(self.tmp, "payload.json")
        Path(payload).write_text('{"body": "stale but conforming"}')
        command = (
            f"jq -Rs '{{body: .}}' {self.path} > {payload}\n"
            f"gh api repos/o/r/issues/934/comments --input {payload}"
        )
        result = hook.check(_bash_input(command))
        self.assertEqual(_decision(result), "block")
        self.assertIn("writes the body file", _reason(result))

    def test_heredoc_redirected_after_the_heredoc_blocks(self) -> None:
        """`cat <<'EOF' > f` — the redirect follows the heredoc (#943)."""
        self._block_reason(f"cat <<'EOF' > {self.path}\n{_NEARMISS_TRAILER}EOF")

    def test_tee_blocks(self) -> None:
        """`tee f <<'EOF'` writes without any redirect at all (#943)."""
        self._block_reason(f"tee {self.path} <<'EOF'\n{_NEARMISS_TRAILER}EOF")

    def test_tee_append_blocks(self) -> None:
        self._block_reason(f"tee -a {self.path} <<'EOF'\n{_NEARMISS_TRAILER}EOF")

    # --- the guard must not fire on payload text -------------------------------

    # The decoy heredoc below writes a DIFFERENT file. That is load-bearing.
    #
    # An earlier version of these tests wrote the quoted redirect into the same
    # heredoc that writes the posted path. The quoted text then fell inside a
    # `modelled` span, and the clause *after* the payload skip discarded it
    # anyway — so the test passed with `_is_payload_text` deleted. It pinned the
    # `modelled` check while being named for the payload check
    # (`feedback_fixture_makes_guard_assertion_inert`, found by Santiago
    # Ferreira). A decoy target puts the quoted text outside every `modelled`
    # span, where only `_is_payload_text` can save it.
    #
    # The two tests quote DIFFERENT constructs so each skip reds on its own
    # removal: one quotes a redirect, one quotes a `tee`.

    def _decoy_command(self, quoted: str) -> str:
        decoy = os.path.join(self.tmp, "decoy.md")
        return (
            f"cat > {decoy} <<'DECOY'\nI reproduced it with:\n\n    {quoted}\nDECOY\n"
            f"cat > {self.path} <<'EOF'\n{_CONFORMING_TRAILER}EOF\n{self.post}"
        )

    def test_a_redirect_quoted_inside_a_heredoc_body_is_not_a_write(self) -> None:
        """A verdict whose prose quotes a redirect to its own path must still post.

        Most verdicts in this repo are *about* shell commands. Reds when the
        payload skip is removed from the redirect loop.
        """
        command = self._decoy_command(f"printf 'x' >> {self.path}")
        self.assertIsNone(
            hook._unmodelled_write(command, self.path),
            "a redirect inside a heredoc body is payload text, not a write",
        )
        self.assertEqual(hook.extract_comment_body(command), _CONFORMING_TRAILER)
        self.assertEqual(_decision(hook.check(_bash_input(command))), "allow")

    def test_a_tee_quoted_inside_a_heredoc_body_is_not_a_write(self) -> None:
        """Same, for the `tee` loop, which has no `modelled` fallback at all.

        Quotes only a `tee` — no redirect to the posted path — so it reds when
        the payload skip is removed from the `tee` loop and not otherwise.
        """
        command = self._decoy_command(f"tee {self.path} <<'X'")
        self.assertIsNone(
            hook._unmodelled_write(command, self.path),
            "a tee inside a heredoc body is payload text, not a write",
        )
        self.assertEqual(hook.extract_comment_body(command), _CONFORMING_TRAILER)
        self.assertEqual(_decision(hook.check(_bash_input(command))), "allow")

    def test_the_quoted_redirect_is_not_merely_masked_by_the_modelled_span(self) -> None:
        """Guard the guard: the decoy's quoted text must sit OUTSIDE `modelled`.

        If it fell inside, the two tests above would pass with `_is_payload_text`
        deleted — which is precisely how the previous fixture was inert.
        """
        command = self._decoy_command(f"printf 'x' >> {self.path}")
        modelled = [
            m.span()
            for m in hook._HEREDOC_WRITE_RE.finditer(command)
            if hook._resolve_body_path(m.group("target")) == self.path
        ]
        self.assertTrue(modelled, "the posted path must still be written by a heredoc")
        quoted_at = command.index(f">> {self.path}")
        self.assertFalse(
            any(start <= quoted_at < end for start, end in modelled),
            "the quoted redirect must NOT sit inside a modelled span, or the "
            "payload skip is not what this test exercises",
        )

    def test_the_modelled_heredoc_redirect_is_not_flagged_as_unmodelled(self) -> None:
        command = f"cat > {self.path} <<'EOF'\n{_CONFORMING_TRAILER}EOF\n{self.post}"
        self.assertIsNone(hook._unmodelled_write(command, self.path))
        self.assertEqual(_decision(hook.check(_bash_input(command))), "allow")

    def test_a_write_to_a_different_path_is_ignored(self) -> None:
        other = os.path.join(self.tmp, "scratch.txt")
        command = f"printf 'log' >> {other}\n{self.post}"
        self.assertIsNone(hook._unmodelled_write(command, self.path))
        self.assertEqual(_decision(hook.check(_bash_input(command))), "allow")

    def test_plain_body_file_with_no_writes_still_reads_disk(self) -> None:
        self.assertEqual(_decision(hook.check(_bash_input(self.post))), "allow")


class UnmodelledWriteCorpusTests(unittest.TestCase):
    """The shape is present in the harvested corpus — a command-string parse only."""

    CORPUS = _FIXTURES / "real_comment_invocations.jsonl"
    rows: ClassVar[list[dict]] = []

    _READ = re.compile(r"--body-file[=\s]+(\S+)|body=@(\S+)|--input\s+(\S+)")

    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = [
            json.loads(line) for line in cls.CORPUS.read_text().splitlines() if line.strip()
        ]

    @classmethod
    def _rows_with_unmodelled_writes(cls) -> list[int]:
        out = []
        for i, row in enumerate(cls.rows):
            command = row["command"]
            for match in cls._READ.finditer(command):
                for group in match.groups():
                    if not group:
                        continue
                    want = hook._resolve_body_path(group.lstrip("@"))
                    if hook._unmodelled_write(command, want) is not None:
                        out.append(i)
                        break
                else:
                    continue
                break
        return out

    def test_the_detector_fires_on_a_planted_row(self) -> None:
        """Verify the instrument before believing any count it produces."""
        planted = (
            "jq -Rs '{body: .}' x.md > /tmp/payload.json\n"
            "gh api repos/o/r/issues/1/comments --input /tmp/payload.json"
        )
        self.assertIsNotNone(
            hook._unmodelled_write(planted, hook._resolve_body_path("/tmp/payload.json"))
        )

    def test_the_corpus_carries_the_shape(self) -> None:
        rows = self._rows_with_unmodelled_writes()
        self.assertGreaterEqual(
            len(rows), 5, f"expected the jq-payload shape in the corpus, found {rows}"
        )


class WriteThenPostCorpusTests(unittest.TestCase):
    """Replay the write-then-post rows the harvested corpus actually contains.

    Purely a command-string parse — it never touches the filesystem, so ambient
    leftover files in a developer's tmp dir cannot contaminate the reading.
    """

    CORPUS = _FIXTURES / "real_comment_invocations.jsonl"
    rows: ClassVar[list[dict]] = []

    _WRITE = re.compile(r">{1,2}\s*(?P<t>'[^']*'|\"[^\"]*\"|\S+)\s*<<")
    _READ = re.compile(r"--body-file[=\s]+(\S+)|body=@(\S+)|--input\s+(\S+)")

    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = [
            json.loads(line) for line in cls.CORPUS.read_text().splitlines() if line.strip()
        ]

    @classmethod
    def _write_then_post_rows(cls) -> list[dict]:
        out = []
        for row in cls.rows:
            command = row["command"]
            writes = {m.group("t").strip("'\"") for m in cls._WRITE.finditer(command)}
            reads = {
                g.strip("'\"").lstrip("@")
                for m in cls._READ.finditer(command)
                for g in m.groups()
                if g
            }
            if writes & reads:
                out.append(row)
        return out

    def test_the_corpus_contains_this_shape(self) -> None:
        """Guard the guard: if this set is empty the assertion below is inert."""
        self.assertGreaterEqual(
            len(self._write_then_post_rows()),
            10,
            "no write-then-post rows — the replay below would prove nothing",
        )

    def test_every_write_then_post_row_recovers_its_body(self) -> None:
        unrecovered = []
        for row in self._write_then_post_rows():
            command = row["command"]
            reads = [
                g.strip("'\"").lstrip("@")
                for m in self._READ.finditer(command)
                for g in m.groups()
                if g
            ]
            writes = {m.group("t").strip("'\"") for m in self._WRITE.finditer(command)}
            for path in reads:
                if path in writes and hook._heredoc_written_body(command, path) is None:
                    unrecovered.append((row.get("form"), path))
        self.assertEqual(unrecovered, [], f"heredoc body not recovered: {unrecovered}")


class PathResolutionIsExercisedTests(unittest.TestCase):
    """Positive controls for `_resolve_body_path` (#934 review, Santiago Ferreira).

    Every pre-existing test named for path resolution asserted only
    `decision == "block"`, and BOTH branches block: gate 1 when the body is read
    and found malformed, the residual when the body is never read at all. So
    `_resolve_body_path` could be replaced by `return path` and all 97 tests
    still passed — the mutant survived, on the exact gate this PR exists to fix.

    A conforming body at a quoted / `$VAR` / `~` path must ALLOW. That can only
    happen if the file was actually opened, which is the assertion the block-only
    tests could not make (`feedback_fixture_makes_guard_assertion_inert`).
    """

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "verdict.md")
        Path(self.path).write_text(_CONFORMING_TRAILER)

    def test_bare_path_allows(self) -> None:
        command = f"gh pr comment 826 --body-file {self.path}"
        self.assertEqual(_decision(hook.check(_bash_input(command))), "allow")

    def test_quoted_path_allows(self) -> None:
        command = f'gh pr comment 826 --body-file "{self.path}"'
        self.assertEqual(_decision(hook.check(_bash_input(command))), "allow")

    def test_envvar_path_allows(self) -> None:
        with mock.patch.dict(os.environ, {"AINO_TMP": self.tmp}):
            command = 'gh pr comment 826 --body-file "$AINO_TMP/verdict.md"'
            self.assertEqual(_decision(hook.check(_bash_input(command))), "allow")

    def test_rest_quoted_at_path_allows(self) -> None:
        with mock.patch.dict(os.environ, {"AINO_TMP": self.tmp}):
            command = 'gh api repos/o/r/issues/826/comments -F body=@"$AINO_TMP/verdict.md"'
            self.assertEqual(_decision(hook.check(_bash_input(command))), "allow")

    def test_tilde_path_allows(self) -> None:
        with mock.patch.dict(os.environ, {"HOME": self.tmp}):
            command = "gh pr comment 826 --body-file ~/verdict.md"
            self.assertEqual(_decision(hook.check(_bash_input(command))), "allow")

    def test_quoted_path_containing_a_space_is_not_truncated(self) -> None:
        spaced = os.path.join(self.tmp, "my verdict.md")
        Path(spaced).write_text(_CONFORMING_TRAILER)
        command = f'gh pr comment 826 --body-file "{spaced}"'
        self.assertEqual(hook.extract_comment_body(command), _CONFORMING_TRAILER)
        self.assertEqual(_decision(hook.check(_bash_input(command))), "allow")

    def test_nearmiss_at_a_quoted_envvar_path_blocks_on_gate_one(self) -> None:
        """Blocks — and specifically NOT because the body was unreadable."""
        Path(self.path).write_text(_NEARMISS_TRAILER)
        with mock.patch.dict(os.environ, {"AINO_TMP": self.tmp}):
            command = 'gh pr comment 826 --body-file "$AINO_TMP/verdict.md"'
            result = hook.check(_bash_input(command))
            self.assertEqual(_decision(result), "block")
            self.assertNotIn("cannot be read", _reason(result))
            self.assertIn("RequestOrReplied", _reason(result))


class UnreadableCauseTests(unittest.TestCase):
    """The diagnostic must name the real cause (#934 review, Wanjiku Mwangi)."""

    def test_stdin_is_named(self) -> None:
        command = "gh api repos/o/r/issues/826/comments --input -"
        result = hook.check(_bash_input(command))
        self.assertEqual(_decision(result), "block")
        self.assertIn("stdin", _reason(result))

    def test_unexported_shell_variable_is_named_as_such(self) -> None:
        command = "gh pr comment 826 --body-file $NOT_EXPORTED_ANYWHERE/v.md"
        result = hook.check(_bash_input(command))
        self.assertEqual(_decision(result), "block")
        self.assertIn("SHELL variable", _reason(result))
        self.assertIn("NOT_EXPORTED_ANYWHERE", _reason(result))
        self.assertNotIn("does not exist", _reason(result))

    def test_absent_file_is_named_as_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "nope.md")
            command = f"gh pr comment 826 --body-file {path}"
            result = hook.check(_bash_input(command))
            self.assertEqual(_decision(result), "block")
            self.assertIn("does not exist", _reason(result))
            self.assertNotIn("SHELL variable", _reason(result))


class SwapGateReadsTheCountedValueTests(unittest.TestCase):
    """The swap heuristic must read the value the counting hook will count.

    `db12c5b` changed the code to `extract_charter_field("Requestor", body)` but
    shipped no test, so nothing would notice it reverting to the whole-body
    `re.search` first match. Both directions were reachable (Santiago Ferreira):
    a correct verdict false-BLOCKED by a prose line above the trailer, and a
    genuinely swapped trailer ALLOWED because an earlier prose match yielded a
    non-author surname first.
    """

    BRANCH = "A.Virtanen/0932-review-comment-format-gate"

    def _check(self, body: str) -> dict | None:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "v.md")
            Path(path).write_text(body)
            command = f"gh pr comment 934 --repo noorinalabs/noorinalabs-main --body-file {path}"
            with mock.patch.object(hook, "get_branch_name", return_value=self.BRANCH):
                return hook.check(_bash_input(command))

    def test_swapped_trailer_blocks(self) -> None:
        body = (
            "prose\n\n---\nRequestor: Aino Virtanen\n"
            "Requestee: Wanjiku Mwangi\nRequestOrReplied: Approved\nTechDebt: none\n"
        )
        result = self._check(body)
        self.assertEqual(_decision(result), "block")
        self.assertIn("swapped", _reason(result))

    def test_correct_trailer_with_prose_above_is_not_false_blocked(self) -> None:
        """Prose above the trailer that ENDS in the PR author's surname.

        The fixture must end there. `_extract_lastname` splits on `[\\s.]+` and
        takes the final token, so `…Requestor: Aino Virtanen would have written
        it.` yields `''`, never matches the branch author, and cannot reach the
        false block at all. An earlier version of this test used exactly that
        sentence: it asserted `allow`, passed under the pre-`db12c5b` gate too,
        and covered nothing (`feedback_fixture_makes_guard_assertion_inert`,
        found by Wanjiku Mwangi). Verified: this body reds under that gate.
        """
        body = (
            "The charter says the reviewer is Requestor: Aino Virtanen\n"
            "\n---\nRequestor: Wanjiku Mwangi\nRequestee: Aino Virtanen\n"
            "RequestOrReplied: Approved\nTechDebt: none\n"
        )
        self.assertEqual(_decision(self._check(body)), "allow")

    def test_swapped_trailer_is_not_disarmed_by_prose_above(self) -> None:
        """A prose sentence mentioning the field must not let a swap through."""
        body = (
            "The charter says the Requestor: is the reviewer, not the author.\n"
            "\n---\nRequestor: Aino Virtanen\nRequestee: Wanjiku Mwangi\n"
            "RequestOrReplied: Approved\nTechDebt: none\n"
        )
        result = self._check(body)
        self.assertEqual(_decision(result), "block")
        self.assertIn("swapped", _reason(result))


class OutOfScopeForEditsTests(unittest.TestCase):
    """This hook gates comment CREATION, never comment EDITS — deliberately.

    Retraction is currently expressible only by breaking a comment on purpose.
    `RequestOrReplied` has no value meaning "I withdraw this", and the counting
    hook's reviewer set is monotonic (main#940 defect 1), so a later comment
    saying so subtracts nothing. On 2026-07-10 a reviewer holding a stale
    `Approved` on `noorinalabs-data-acquisition` #359 retracted it by editing his
    own comment and mangling the trailer field names — the fixture below is that
    body, verbatim.

    Gate 1 blocks exactly that shape. It does not fire today only because the
    retraction was a `-X PATCH` edit, and edits are out of scope. A maintainer
    who widens the URL regex to cover the edit endpoint will forbid the only
    retraction mechanism reviewers have. These tests go red when that happens.
    """

    FIXTURE = "real_retraction_by_rename_da359.txt"

    def test_the_retraction_fixture_is_uncountable(self) -> None:
        """Guard the guard: if this parsed, the retraction never worked."""
        import validate_pr_review as counting_hook

        body = _fixture(self.FIXTURE)
        self.assertIn("RETRACTED", body)
        self.assertIsNone(counting_hook._extract_charter_field("RequestOrReplied", body))
        self.assertIsNone(counting_hook._extract_charter_field("Requestor", body))

    def test_the_trailer_mangle_is_what_defeats_the_counter(self) -> None:
        """Not the `Verdict:` rename in the banner — that sits above the last `---`.

        Restoring the banner's field name changes nothing; the trailer's
        `Requestor (retracted):` is the load-bearing edit.
        """
        import validate_pr_review as counting_hook

        body = _fixture(self.FIXTURE)
        banner_restored = body.replace("Verdict:", "RequestOrReplied:")
        self.assertIsNone(
            counting_hook._extract_charter_field("RequestOrReplied", banner_restored),
            "renaming the banner field must not resurrect the approval",
        )
        trailer_restored = body.replace(" (retracted):", ":")
        self.assertEqual(
            counting_hook._extract_charter_field("RequestOrReplied", trailer_restored),
            "Approved",
            "un-mangling the trailer MUST resurrect it — otherwise this test proves nothing",
        )

    def test_a_patch_edit_is_not_a_comment_command(self) -> None:
        edit = "gh api -X PATCH repos/o/r/issues/comments/4929379765 -F body=@/tmp/retraction.md"
        self.assertFalse(hook.is_comment_command(edit))

    def test_the_url_shape_not_the_method_is_the_discriminator(self) -> None:
        """A maintainer widening this must know which axis carries the boundary."""
        self.assertTrue(
            hook.is_comment_command(
                "gh api -X PATCH repos/o/r/issues/359/comments -F body=@/tmp/x.md"
            ),
            "PATCH at a CREATE url still matches — the method is not the guard",
        )
        self.assertFalse(
            hook.is_comment_command(
                "gh api -X POST repos/o/r/issues/comments/999 -F body=@/tmp/x.md"
            ),
            "POST at an EDIT url does not match — the url shape is the guard",
        )

    def test_gate_one_would_block_the_retraction_if_it_were_posted(self) -> None:
        """The collision is real; only the edit/post boundary keeps it latent."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "retraction.md")
            Path(path).write_text(_fixture(self.FIXTURE))
            command = (
                "gh pr comment 359 --repo noorinalabs/noorinalabs-data-acquisition "
                f"--body-file {path}"
            )
            result = hook.check(_bash_input(command))
            self.assertEqual(_decision(result), "block")
            self.assertIn("RequestOrReplied", _reason(result))


if __name__ == "__main__":
    unittest.main()
