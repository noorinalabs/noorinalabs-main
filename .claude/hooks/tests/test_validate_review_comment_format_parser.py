#!/usr/bin/env python3
"""Fixture-driven Direction-table tests for validate_review_comment_format hook.

Each JSON file in fixtures/validate_review_comment_format/ is one test case:

    {
        "description": "<human label>",
        "command": "<raw bash command string>",
        "branch_ref": "<head ref name returned by get_branch_name() mock>",
        "expect": "allow" | "block:<reason-keyword>"
    }

The `branch_ref` field is mocked into `validate_review_comment_format.get_branch_name`
so tests do not hit the network. The `expect` field:
  - "allow"      → check() must return None
  - "block:<kw>" → check() must return a block decision; <kw> is a
                   substring of the reason (case-insensitive) for
                   self-documenting test output, not strict matching.

Fixtures cover the four `RequestOrReplied` Direction-table values
(charter pull-requests.md § Comment-Based Reviews):
  - Approved / ChangesRequested — verdict directions, swap heuristic in
    scope (block on Requestee.lastname == branch-author).
  - Request / Reply — role bindings inverted, hook narrows OOS (allow).
  - Unrecognized value — fail-open (allow); the hook does not validate
    the verdict word itself, that is `validate_pr_review`'s scope.

Run:  python3 -m pytest .claude/hooks/tests/test_validate_review_comment_format_parser.py -v
      (or the full suite: python3 -m pytest .claude/hooks/tests/ -v)
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
_FIXTURES_DIR = _HOOKS_DIR / "fixtures" / "validate_review_comment_format"

sys.path.insert(0, str(_HOOKS_DIR))

import validate_review_comment_format as hook  # noqa: E402


def _load_fixtures() -> list[tuple[str, dict]]:
    """Return (fixture_name, fixture_data) pairs for every JSON in the fixture dir."""
    fixtures = []
    for path in sorted(_FIXTURES_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        fixtures.append((path.stem, data))
    return fixtures


def _make_input(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


class FixtureDrivenDirectionTableTests(unittest.TestCase):
    """One test method per fixture file — generated dynamically."""


def _add_fixture_test(name: str, fixture: dict) -> None:
    """Attach a test method to FixtureDrivenDirectionTableTests for `fixture`."""
    description = fixture.get("description", name)
    command = fixture["command"]
    branch_ref = fixture.get("branch_ref", "")
    expect = fixture["expect"]

    def test_method(self: unittest.TestCase) -> None:
        with mock.patch.object(hook, "get_branch_name", return_value=branch_ref):
            result = hook.check(_make_input(command))
        if expect == "allow":
            self.assertIsNone(
                result,
                f"{description!r}: expected allow (None) but got: {result}",
            )
        elif expect.startswith("block:"):
            self.assertIsNotNone(
                result,
                f"{description!r}: expected block but got allow (None)",
            )
            assert result is not None  # for mypy
            self.assertEqual(
                result.get("decision"),
                "block",
                f"{description!r}: result decision is not 'block': {result}",
            )
        else:
            raise ValueError(f"Unknown expect value {expect!r} in fixture {name!r}")

    test_method.__name__ = f"test_{name}"
    test_method.__doc__ = description
    setattr(FixtureDrivenDirectionTableTests, test_method.__name__, test_method)


for _fixture_name, _fixture_data in _load_fixtures():
    _add_fixture_test(_fixture_name, _fixture_data)


class DirectionVerdictHelperTests(unittest.TestCase):
    """Direct coverage of `_direction_is_verdict` shape."""

    def _body(self, direction: str) -> str:
        return f"Requestor: A\nRequestee: B\nRequestOrReplied: {direction}"

    def test_approved_verdict(self):
        self.assertTrue(hook._direction_is_verdict(self._body("Approved")))

    def test_changes_requested_camelcase_verdict(self):
        self.assertTrue(hook._direction_is_verdict(self._body("ChangesRequested")))

    def test_changes_requested_two_word_verdict(self):
        """`Changes Requested` (space-separated) — the form validate_pr_review counts.

        Per feedback_validate_pr_review_approved_not_reply.md, the literal
        two-word form is the one the sibling hook counts. Both forms must
        be recognized here.
        """
        self.assertTrue(hook._direction_is_verdict(self._body("Changes Requested")))

    def test_approved_lowercase_verdict(self):
        self.assertTrue(hook._direction_is_verdict(self._body("approved")))

    def test_approved_markdown_bold_verdict(self):
        """`**Approved**` markdown bolding is stripped before comparison."""
        self.assertTrue(hook._direction_is_verdict(self._body("**Approved**")))

    def test_approved_with_trailing_token_verdict(self):
        """Trailing parenthetical / explanatory text after the verdict word allowed."""
        self.assertTrue(hook._direction_is_verdict(self._body("Approved (post-merge)")))

    def test_request_not_verdict(self):
        self.assertFalse(hook._direction_is_verdict(self._body("Request")))

    def test_reply_not_verdict(self):
        self.assertFalse(hook._direction_is_verdict(self._body("Reply")))

    def test_unknown_not_verdict(self):
        self.assertFalse(hook._direction_is_verdict(self._body("Asdf")))

    def test_bare_changes_not_verdict(self):
        """`Changes` alone (without `Requested`) is NOT a verdict — must NOT match.

        Defensive guard: tolerating the bare prefix would over-narrow and
        leave legitimate non-verdict comments mis-classified as verdicts.
        """
        self.assertFalse(hook._direction_is_verdict(self._body("Changes")))

    def test_empty_value_not_verdict(self):
        self.assertFalse(hook._direction_is_verdict("Requestor: A\nRequestOrReplied: "))

    def test_missing_label_not_verdict(self):
        self.assertFalse(hook._direction_is_verdict("Requestor: A\nRequestee: B"))


if __name__ == "__main__":
    unittest.main()
