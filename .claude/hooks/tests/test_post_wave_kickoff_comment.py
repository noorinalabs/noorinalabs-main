#!/usr/bin/env python3
"""Tests for post_wave_kickoff_comment PostToolUse hook.

Two test surfaces:

1. **Fixture-driven scenarios** — `.claude/hooks/fixtures/post_wave_kickoff_comment/`
   contains JSON test cases with this shape:

       {
           "description": "<human label>",
           "command": "<raw bash command string>",
           "status": <cross-repo-status.json dict>,
           "existing_comments": [<comment dicts>],
           "post_succeeds": <bool>,
           "expect_action": "post" | "skip_*" | null,
           "expect_body_contains": [<substrings>]   # only meaningful for "post"
       }

   The injectors in `post_wave_kickoff_comment.check()` (`status_loader`,
   `comment_fetcher`, `comment_poster`, `body_writer`) let each test mock
   the four external interactions (status JSON read, gh comments fetch,
   gh comment post, body file write) without monkeypatching subprocess.

2. **Direct unit tests** — `parse_label_apply_command`,
   `find_assignment_row`, `render_kickoff_comment`,
   `kickoff_already_posted`. These pin behaviors that don't fit cleanly
   into fixture form (regex shapes, table-driven row lookups).

Run:  python3 -m pytest .claude/hooks/tests/test_post_wave_kickoff_comment.py -v
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
_FIXTURES_DIR = _HOOKS_DIR / "fixtures" / "post_wave_kickoff_comment"

sys.path.insert(0, str(_HOOKS_DIR))

import post_wave_kickoff_comment as hook  # noqa: E402


def _load_fixtures() -> list[tuple[str, dict]]:
    fixtures = []
    for path in sorted(_FIXTURES_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        fixtures.append((path.stem, data))
    return fixtures


def _bash(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


class FixtureDrivenScenarioTests(unittest.TestCase):
    """One test per fixture file — generated dynamically."""


def _add_fixture_test(name: str, fixture: dict) -> None:
    description = fixture.get("description", name)
    command = fixture["command"]
    status = fixture.get("status")
    existing_comments = fixture.get("existing_comments", [])
    post_succeeds = fixture.get("post_succeeds", True)
    expect_action = fixture.get("expect_action")
    expect_body_contains = fixture.get("expect_body_contains", [])

    def test_method(self: unittest.TestCase) -> None:
        captured: dict = {}

        def fake_status():
            return status

        def fake_fetch(repo, num):
            return existing_comments

        def fake_post(repo, num, body_path):
            captured["repo"] = repo
            captured["num"] = num
            captured["body_path"] = body_path
            captured["body"] = Path(body_path).read_text(encoding="utf-8")
            return post_succeeds

        with tempfile.TemporaryDirectory() as td:

            def fake_writer(body, repo, num):
                path = Path(td) / f"body-{repo}-{num}.md"
                path.write_text(body, encoding="utf-8")
                return path

            result = hook.check(
                _bash(command),
                status_loader=fake_status,
                comment_fetcher=fake_fetch,
                comment_poster=fake_post,
                body_writer=fake_writer,
            )

            if expect_action is None:
                self.assertIsNone(
                    result,
                    f"{description!r}: expected hook to not apply (None), got: {result}",
                )
                return

            self.assertIsNotNone(
                result,
                f"{description!r}: expected action={expect_action!r}, got None",
            )
            assert result is not None
            self.assertEqual(
                result.get("action"),
                expect_action,
                f"{description!r}: action mismatch: {result}",
            )

            if expect_action == "post":
                for needle in expect_body_contains:
                    self.assertIn(
                        needle,
                        captured.get("body", ""),
                        f"{description!r}: missing expected substring {needle!r} in body:\n"
                        f"{captured.get('body', '(no body captured)')}",
                    )

    test_method.__name__ = f"test_{name}"
    test_method.__doc__ = description
    setattr(FixtureDrivenScenarioTests, test_method.__name__, test_method)


for _fixture_name, _fixture_data in _load_fixtures():
    _add_fixture_test(_fixture_name, _fixture_data)


class ParseLabelApplyCommandTests(unittest.TestCase):
    """Direct coverage of the bash-command parser."""

    def test_canonical_form(self):
        self.assertEqual(
            hook.parse_label_apply_command(
                'gh issue edit 123 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-9"'
            ),
            ("noorinalabs-main", "123", "p3-wave-9"),
        )

    def test_flag_order_swapped(self):
        self.assertEqual(
            hook.parse_label_apply_command(
                'gh issue edit 456 --add-label "p3-wave-9" --repo noorinalabs/noorinalabs-deploy'
            ),
            ("noorinalabs-deploy", "456", "p3-wave-9"),
        )

    def test_equals_form(self):
        self.assertEqual(
            hook.parse_label_apply_command(
                "gh issue edit 789 --repo=noorinalabs/noorinalabs-isnad-graph --add-label=p3-wave-8"
            ),
            ("noorinalabs-isnad-graph", "789", "p3-wave-8"),
        )

    def test_multiple_add_label_picks_wave_label(self):
        """When the command applies BOTH a wave label and an implementer
        label, only the wave label matters for hook trigger."""
        self.assertEqual(
            hook.parse_label_apply_command(
                "gh issue edit 100 --repo noorinalabs/noorinalabs-main "
                '--add-label "Aino_Virtanen" --add-label "p3-wave-9"'
            ),
            ("noorinalabs-main", "100", "p3-wave-9"),
        )

    def test_non_wave_label_returns_none(self):
        self.assertIsNone(
            hook.parse_label_apply_command(
                'gh issue edit 100 --repo noorinalabs/noorinalabs-main --add-label "tech-debt"'
            )
        )

    def test_non_issue_edit_command_returns_none(self):
        self.assertIsNone(
            hook.parse_label_apply_command(
                'gh pr edit 42 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-9"'
            )
        )

    def test_unrelated_command_returns_none(self):
        self.assertIsNone(hook.parse_label_apply_command("echo hello"))

    def test_empty_command_returns_none(self):
        self.assertIsNone(hook.parse_label_apply_command(""))

    def test_compound_command_picks_label_segment(self):
        """`true && gh issue edit ... --add-label "p3-wave-9"` still matches."""
        self.assertEqual(
            hook.parse_label_apply_command(
                "true && gh issue edit 999 --repo noorinalabs/noorinalabs-main "
                '--add-label "p3-wave-9"'
            ),
            ("noorinalabs-main", "999", "p3-wave-9"),
        )


class FindAssignmentRowTests(unittest.TestCase):
    """Direct coverage of tier-array row lookup with both shapes."""

    def test_explicit_issue_id_match(self):
        status = {
            "wave_9_scope": {
                "tier_1_x": [
                    {"id": "noorinalabs-main#123", "implementer": "A"},
                    {"id": "noorinalabs-deploy#9", "implementer": "B"},
                ]
            }
        }
        row = hook.find_assignment_row(status, "noorinalabs-main", "123", 9)
        self.assertEqual(row["implementer"], "A")

    def test_repo_backlog_match_when_no_explicit_id(self):
        """W6+W7 Tier-1 backlog shape: row has `repo`, no `id`."""
        status = {
            "wave_9_scope": {
                "tier_1_backlog": [
                    {"repo": "noorinalabs-deploy", "implementer": "Santiago Ferreira"}
                ]
            }
        }
        row = hook.find_assignment_row(status, "noorinalabs-deploy", "555", 9)
        self.assertEqual(row["implementer"], "Santiago Ferreira")

    def test_explicit_id_wins_over_repo_match(self):
        """If both shapes are present, the explicit-id row wins."""
        status = {
            "wave_9_scope": {
                "tier_1_backlog": [{"repo": "noorinalabs-main", "implementer": "BACKLOG"}],
                "tier_2_explicit": [{"id": "noorinalabs-main#42", "implementer": "EXPLICIT"}],
            }
        }
        row = hook.find_assignment_row(status, "noorinalabs-main", "42", 9)
        self.assertEqual(row["implementer"], "EXPLICIT")

    def test_no_match_returns_none(self):
        status = {"wave_9_scope": {"tier_1": [{"id": "other#999", "implementer": "X"}]}}
        self.assertIsNone(hook.find_assignment_row(status, "noorinalabs-main", "1", 9))

    def test_empty_scope_returns_none(self):
        self.assertIsNone(hook.find_assignment_row({}, "noorinalabs-main", "1", 9))

    def test_non_tier_keys_ignored(self):
        """Keys not starting with `tier_` (theme, declared_total, etc.) are skipped."""
        status = {
            "wave_9_scope": {
                "theme": "tech-debt",
                "tier_1": [{"id": "noorinalabs-main#1", "implementer": "Y"}],
            }
        }
        row = hook.find_assignment_row(status, "noorinalabs-main", "1", 9)
        self.assertEqual(row["implementer"], "Y")


class RenderKickoffCommentTests(unittest.TestCase):
    """Direct coverage of comment body rendering."""

    def test_canonical_render(self):
        row = {
            "implementer": "Aino Virtanen",
            "reviewer": "Nadia Khoury",
            "reviewer_2": "Santiago Ferreira",
            "priority": "tech-debt",
        }
        body = hook.render_kickoff_comment(row, wave_num=9, phase_num=3, repo="noorinalabs-main")
        self.assertIn("Requestor: Fatima Okonkwo", body)
        self.assertIn("Requestee: Aino Virtanen", body)
        self.assertIn("RequestOrReplied: Request", body)
        self.assertIn("**Wave 9 Kickoff — Phase 3**", body)
        self.assertIn("- Peer reviewer: Nadia Khoury", body)
        self.assertIn("- Secondary reviewer: Santiago Ferreira", body)
        self.assertIn("- Branch from: `deployments/phase-3/wave-9`", body)
        self.assertIn("- Priority: tech-debt", body)

    def test_missing_optional_fields_show_unassigned(self):
        """Missing reviewer/reviewer_2 render as `(unassigned)`, not blank."""
        row = {"implementer": "Aino Virtanen"}
        body = hook.render_kickoff_comment(row, wave_num=9, phase_num=3, repo="noorinalabs-main")
        self.assertIn("- Peer reviewer: (unassigned)", body)
        self.assertIn("- Secondary reviewer: (unassigned)", body)
        self.assertIn("- Priority: feature", body)  # default priority

    def test_implementer_missing_shows_unassigned(self):
        body = hook.render_kickoff_comment({}, wave_num=9, phase_num=3, repo="noorinalabs-main")
        self.assertIn("Requestee: (unassigned)", body)


class KickoffAlreadyPostedTests(unittest.TestCase):
    """Idempotency check across various comment shapes."""

    def test_returns_true_on_charter_heading(self):
        def fetch(r, n):
            return [{"body": "**Wave 9 Kickoff — Phase 3**\n\nbody"}]

        self.assertTrue(hook.kickoff_already_posted("x", "1", fetch_comments=fetch))

    def test_returns_true_on_hyphen_form(self):
        """Tolerate a hyphen-surrounded form in case the em-dash got dropped."""

        def fetch(r, n):
            return [{"body": "**Wave 9 Kickoff - Phase 3**"}]

        self.assertTrue(hook.kickoff_already_posted("x", "1", fetch_comments=fetch))

    def test_returns_false_on_no_kickoff_comment(self):
        def fetch(r, n):
            return [{"body": "Some other comment."}]

        self.assertFalse(hook.kickoff_already_posted("x", "1", fetch_comments=fetch))

    def test_returns_false_on_no_comments(self):
        def fetch(r, n):
            return []

        self.assertFalse(hook.kickoff_already_posted("x", "1", fetch_comments=fetch))

    def test_returns_false_on_fetch_failure(self):
        """fetch returning None (gh CLI failed) → don't suppress; let the
        downstream post attempt and annunaki-log on real failure."""

        def fetch(r, n):
            return None

        self.assertFalse(hook.kickoff_already_posted("x", "1", fetch_comments=fetch))


class NonBashToolTests(unittest.TestCase):
    """tool_name != Bash → early return None."""

    def test_edit_tool_not_matched(self):
        result = hook.check(
            {
                "tool_name": "Edit",
                "tool_input": {"command": 'gh issue edit 1 --repo r --add-label "p3-wave-9"'},
            }
        )
        self.assertIsNone(result)

    def test_empty_command_not_matched(self):
        result = hook.check({"tool_name": "Bash", "tool_input": {"command": ""}})
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
