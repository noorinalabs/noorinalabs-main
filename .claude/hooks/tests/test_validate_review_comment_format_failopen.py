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
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
sys.path.insert(0, str(_HOOKS_DIR))

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
    """The fixtures must carry the defect, or the tests below prove nothing."""

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


if __name__ == "__main__":
    unittest.main()
