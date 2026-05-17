#!/usr/bin/env python3
"""Tests for enforce_ontology_context — covers #466 coordinator-class exemption.

Run: ENVIRONMENT=test python3 -m pytest .claude/hooks/tests/test_enforce_ontology_context.py -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
sys.path.insert(0, str(_HOOKS_DIR))

import enforce_ontology_context as hook  # noqa: E402


def _spawn(prompt: str, isolation: str = "worktree") -> dict:
    return {
        "tool_name": "Agent",
        "tool_input": {"isolation": isolation, "prompt": prompt},
    }


class NonAgentCallAllowed(unittest.TestCase):
    def test_bash_tool_pass_through(self):
        self.assertIsNone(hook.check({"tool_name": "Bash", "tool_input": {"command": "ls"}}))

    def test_edit_tool_pass_through(self):
        self.assertIsNone(hook.check({"tool_name": "Edit", "tool_input": {}}))


class NonWorktreeIsolationAllowed(unittest.TestCase):
    def test_no_isolation_allowed(self):
        self.assertIsNone(hook.check(_spawn("Random prompt without markers", isolation="")))

    def test_other_isolation_value_allowed(self):
        self.assertIsNone(hook.check(_spawn("Random prompt", isolation="container")))


class WorktreeImplementerWithoutContextBlocked(unittest.TestCase):
    def test_engineer_blocked(self):
        prompt = "You are **Mateo Salazar**, Engineer for noorinalabs-user-service. Implement #123."
        result = hook.check(_spawn(prompt))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["decision"], "block")

    def test_tech_lead_blocked(self):
        prompt = (
            "You are **Anya Kowalczyk**, Tech Lead for noorinalabs-isnad-graph. Implement #500."
        )
        result = hook.check(_spawn(prompt))
        self.assertIsNotNone(result)

    def test_security_engineer_blocked(self):
        prompt = "You are **Idris Yusuf**, Security Engineer. Review the auth code."
        result = hook.check(_spawn(prompt))
        self.assertIsNotNone(result)


class WorktreeImplementerWithContextAllowed(unittest.TestCase):
    def test_ontology_context_heading_allowed(self):
        prompt = (
            "## Ontology Context\nServices: user-service\n\n"
            "You are **Mateo**, Engineer. Implement #123."
        )
        self.assertIsNone(hook.check(_spawn(prompt)))

    def test_status_marker_allowed(self):
        prompt = "You are Mateo. Ontology Status: ontology is current. Implement #123."
        self.assertIsNone(hook.check(_spawn(prompt)))

    def test_yaml_path_marker_allowed(self):
        prompt = "You are Mateo. See ontology/services.yaml for context. Implement #123."
        self.assertIsNone(hook.check(_spawn(prompt)))


class CoordinatorClassExempt(unittest.TestCase):
    """Manager / Program Director / TPM / Release Coordinator spawn briefs are
    exempt from ontology-context enforcement even with worktree isolation.

    Reproduces the 8-block burst captured 2026-05-17 03:54Z (#466)."""

    def test_manager_for_deploy_exempt(self):
        prompt = "You are **Bereket Tadesse**, Manager for noorinalabs-deploy. Roster card: ..."
        self.assertIsNone(hook.check(_spawn(prompt)))

    def test_manager_for_isnad_graph_exempt(self):
        prompt = (
            "You are **Nadia Boukhari**, Manager for noorinalabs-isnad-graph "
            "(NOT Nadia Khoury the parent Program Director — different person)."
        )
        self.assertIsNone(hook.check(_spawn(prompt)))

    def test_manager_for_ingest_platform_exempt(self):
        prompt = (
            "You are **Adaeze Okonkwo**, Manager for noorinalabs-isnad-ingest-platform. "
            "Roster card: ..."
        )
        self.assertIsNone(hook.check(_spawn(prompt)))

    def test_program_director_exempt(self):
        prompt = "You are **Nadia Khoury**, Program Director for noorinalabs. Coordinate the wave."
        self.assertIsNone(hook.check(_spawn(prompt)))

    def test_tpm_exempt(self):
        prompt = "You are **Wanjiku Mwangi**, TPM for noorinalabs. Track timelines."
        self.assertIsNone(hook.check(_spawn(prompt)))

    def test_technical_program_manager_full_title_exempt(self):
        prompt = (
            "You are **Wanjiku Mwangi**, Technical Program Manager for noorinalabs. "
            "Track timelines."
        )
        self.assertIsNone(hook.check(_spawn(prompt)))

    def test_release_coordinator_exempt(self):
        prompt = (
            "You are **Santiago Ferreira**, Release Coordinator for noorinalabs. Sequence rollouts."
        )
        self.assertIsNone(hook.check(_spawn(prompt)))

    def test_manager_without_repo_suffix_exempt(self):
        prompt = "You are **Bereket Tadesse**, Manager. Coordinate the deploy wave."
        self.assertIsNone(hook.check(_spawn(prompt)))

    def test_manager_without_bold_markdown_exempt(self):
        prompt = "You are Bereket Tadesse, Manager for noorinalabs-deploy. Coordinate the wave."
        self.assertIsNone(hook.check(_spawn(prompt)))


class CoordinatorExemptIsBoundaryStrict(unittest.TestCase):
    """The exemption matches the canonical opener shape and NOT incidental
    mentions of coordinator role names later in the prompt."""

    def test_engineer_mentioning_manager_in_body_still_blocked(self):
        prompt = (
            "You are **Mateo Salazar**, Engineer. Your Manager Bereket asked for #123. "
            "Implement it."
        )
        result = hook.check(_spawn(prompt))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["decision"], "block")

    def test_tech_lead_not_exempted_by_lead_substring(self):
        prompt = "You are **Anya Kowalczyk**, Tech Lead. Implement #500."
        result = hook.check(_spawn(prompt))
        self.assertIsNotNone(result)

    def test_engineering_manager_role_does_not_match_simple_manager(self):
        # "Engineering Manager" (a doer-manager title) won't match because
        # the regex requires the coordinator word immediately after `, `.
        prompt = "You are **Sam**, Engineering Manager. Implement #200."
        result = hook.check(_spawn(prompt))
        self.assertIsNotNone(result)


if __name__ == "__main__":
    unittest.main()
