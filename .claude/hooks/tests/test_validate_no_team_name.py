#!/usr/bin/env python3
"""Tests for validate_no_team_name — the #1375 team_name retirement.

Wave-30 acceptance bar: a fix lands only with a test that FAILS against the
pre-fix implementation. That is satisfied structurally here — before #1375
there is no `validate_no_team_name` module at all, so every case below fails
at import. The bar is met trivially rather than vacuously: the point of
stating it is that the blocking behaviour, not merely the module's existence,
is what the cases pin.

Run: ENVIRONMENT=test python3 -m pytest .claude/hooks/tests/test_validate_no_team_name.py -v
"""

from __future__ import annotations

import unittest

import _test_helpers  # noqa: E402,F401
import pytest
import validate_no_team_name as hook  # noqa: E402


def _spawn(tool_input: dict, tool_name: str = "Agent") -> dict:
    return {"tool_name": tool_name, "tool_input": tool_input}


class NonAgentCallAllowed(unittest.TestCase):
    """Only the Agent tool carries team_name; everything else passes through
    untouched even when it happens to have a same-named key."""

    def test_bash_pass_through(self):
        self.assertIsNone(hook.check(_spawn({"command": "ls"}, tool_name="Bash")))

    def test_bash_with_team_name_key_still_allowed(self):
        # Guards against a matcher widened past `Agent`: a Bash call whose
        # payload happens to contain team_name must NOT be blocked.
        self.assertIsNone(
            hook.check(_spawn({"command": "ls", "team_name": "noorinalabs"}, tool_name="Bash"))
        )


@pytest.mark.parametrize(
    "tool_input",
    [
        {"prompt": "You are Aino Virtanen, Standards & Quality Lead"},
        {"prompt": "spawn", "isolation": "worktree"},
        {"prompt": "spawn", "team_name": ""},
        {"prompt": "spawn", "team_name": "   "},
    ],
    ids=[
        "no_team_name_key",
        "worktree_spawn_without_team_name",
        "empty_team_name_treated_as_absent",
        "whitespace_only_team_name_treated_as_absent",
    ],
)
def test_spawn_without_team_name_is_allowed(tool_input):
    """The expected path. An empty/whitespace value names no team, so there is
    nothing to correct and blocking it would be pure friction."""
    assert hook.check(_spawn(tool_input)) is None


@pytest.mark.parametrize(
    "team_name",
    ["noorinalabs", "noorinalabs-isnad-graph", "noorinalabs-deploy", "reddit-bot"],
    ids=["org_default", "per_repo_isnad_graph", "per_repo_deploy", "foreign_team"],
)
def test_spawn_with_team_name_is_blocked(team_name):
    """Every value the retired charter table used to prescribe is now blocked —
    including `noorinalabs`, which was the mandated cross-repo default at 14
    charter sites before #1375."""
    result = hook.check(_spawn({"prompt": "spawn", "team_name": team_name}))
    assert result is not None
    assert result["decision"] == "block"
    assert team_name in result["reason"]


class BlockReasonIsActionable(unittest.TestCase):
    """A block that does not say what to do instead just relocates the
    problem — the reason must name the remedy and the routing that replaces
    team_name."""

    def setUp(self):
        result = hook.check(_spawn({"prompt": "spawn", "team_name": "noorinalabs"}))
        # Narrow for the type-checker AND fail loudly here rather than with an
        # opaque TypeError inside each test if the block ever stops firing.
        self.assertIsNotNone(result, "expected a block for a team_name-carrying spawn")
        assert result is not None
        self.reason = result["reason"]

    def test_states_the_remedy(self):
        self.assertIn("Remove `team_name`", self.reason)

    def test_names_the_surviving_routing_mechanism(self):
        self.assertIn("SendMessage", self.reason)

    def test_cites_the_issue(self):
        self.assertIn("1375", self.reason)


class MalformedInputFailsOpen(unittest.TestCase):
    """A PreToolUse hook that raises surfaces as block-with-error, which is
    worse than allowing a malformed shape the tool itself will reject. Mirrors
    enforce_ontology_context's stance."""

    def test_non_dict_tool_input(self):
        self.assertIsNone(hook.check({"tool_name": "Agent", "tool_input": "not-a-dict"}))

    def test_missing_tool_input(self):
        self.assertIsNone(hook.check({"tool_name": "Agent"}))

    def test_non_string_team_name(self):
        self.assertIsNone(hook.check(_spawn({"team_name": {"nested": "dict"}})))

    def test_empty_input(self):
        self.assertIsNone(hook.check({}))


if __name__ == "__main__":
    unittest.main()
