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

import json
import subprocess
import sys
import unittest

import _test_helpers  # noqa: E402,F401
import pytest
import validate_no_team_name as hook  # noqa: E402

_HOOKS_DIR = _test_helpers.HOOKS_DIR


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
    including `noorinalabs`, the mandated cross-repo default across 10 files /
    18 references before #1375."""
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


class MainEntrypointExitCode(unittest.TestCase):
    """The registered entry point must exit **2** to block. MF1 of the #1376
    merge-gate review (Nino Kavtaradze).

    Why the `check()` tests above are not enough — and why this class is the
    load-bearing one. Mutating `run_blocking` -> `run_advisory` in `main()`
    leaves all 17 `check()` cases green AND still prints the byte-identical
    `{"decision": "block", ...}` payload to stdout, while exiting **0**: the
    gate announces "BLOCKED" and silently allows. Reproduced live before
    writing this class. Nothing outside the exit code distinguishes the
    working hook from the broken one, so nothing but an exit-code assertion
    can pin it.

    This is #1243's shape (a BLOCK gate that exits non-2 fails open, because
    a PreToolUse non-2 non-zero does not block) and the wave-30 theme's
    definition of an untestable gate: passing and broken states that are
    observationally identical from outside.
    """

    def _run(self, payload: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(_HOOKS_DIR / "validate_no_team_name.py")],
            input=payload,
            capture_output=True,
            text=True,
        )

    def _agent(self, tool_input: dict) -> str:
        return json.dumps({"tool_name": "Agent", "tool_input": tool_input})

    def test_team_name_spawn_exits_2(self):
        """The assertion that kills the run_advisory mutant."""
        proc = self._run(self._agent({"prompt": "spawn", "team_name": "noorinalabs"}))
        self.assertEqual(
            proc.returncode, 2, "a blocking gate MUST exit 2; non-2 fails open (#1243)"
        )

    def test_team_name_spawn_emits_block_decision(self):
        proc = self._run(self._agent({"prompt": "spawn", "team_name": "noorinalabs"}))
        self.assertEqual(json.loads(proc.stdout)["decision"], "block")

    def test_padded_team_name_still_exits_2(self):
        proc = self._run(self._agent({"prompt": "spawn", "team_name": "  noorinalabs  "}))
        self.assertEqual(proc.returncode, 2)

    def test_clean_spawn_exits_0(self):
        proc = self._run(self._agent({"prompt": "spawn"}))
        self.assertEqual(proc.returncode, 0)

    def test_bash_call_exits_0(self):
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}})
        self.assertEqual(self._run(payload).returncode, 0)

    def test_non_dict_tool_input_exits_0(self):
        payload = json.dumps({"tool_name": "Agent", "tool_input": "not-a-dict"})
        self.assertEqual(self._run(payload).returncode, 0)

    def test_empty_stdin_exits_0(self):
        self.assertEqual(self._run("").returncode, 0)

    def test_non_json_stdin_exits_0(self):
        self.assertEqual(self._run("not json at all").returncode, 0)


if __name__ == "__main__":
    unittest.main()
