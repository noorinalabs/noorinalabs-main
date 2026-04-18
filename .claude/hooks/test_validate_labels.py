#!/usr/bin/env python3
"""Tests for validate_labels.py.

Run with:  uv run python -m pytest .claude/hooks/test_validate_labels.py -v
or:        python -m pytest .claude/hooks/test_validate_labels.py -v

Covers positive extraction, --repo forwarding, and (critically) negative-match
cases where label-like strings appear inside --body argument values.
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import validate_labels as vl


class TestExtractLabels(unittest.TestCase):
    def test_single_label_space_form(self):
        self.assertEqual(
            vl.extract_labels('gh issue create --title "t" --label bug'),
            ["bug"],
        )

    def test_single_label_equals_form(self):
        self.assertEqual(
            vl.extract_labels("gh issue create --title t --label=bug"),
            ["bug"],
        )

    def test_short_flag(self):
        self.assertEqual(
            vl.extract_labels("gh issue create --title t -l bug"),
            ["bug"],
        )

    def test_comma_separated(self):
        self.assertEqual(
            vl.extract_labels('gh issue create --title t --label "bug,p2-wave-9,tech-debt"'),
            ["bug", "p2-wave-9", "tech-debt"],
        )

    def test_multiple_label_flags(self):
        self.assertEqual(
            vl.extract_labels("gh issue create --title t --label bug --label p2-wave-9"),
            ["bug", "p2-wave-9"],
        )

    def test_no_issue_create_subcommand(self):
        # list / view / edit should be ignored entirely.
        self.assertEqual(
            vl.extract_labels("gh issue list --label bug"),
            [],
        )
        self.assertEqual(
            vl.extract_labels("gh issue edit 42 --add-label bug"),
            [],
        )

    # --- Negative-match: body content must NOT be scanned for --label flags ---

    def test_negative_label_inside_body_single_quotes(self):
        """A --label fake-label inside a quoted --body must NOT be extracted."""
        cmd = (
            "gh issue create --title 'bug' "
            "--body 'This issue documents `gh issue create --label fake-label` usage' "
            "--label bug"
        )
        self.assertEqual(vl.extract_labels(cmd), ["bug"])

    def test_negative_label_inside_body_double_quotes(self):
        cmd = (
            'gh issue create --title "bug" '
            '--body "Example: gh issue create --label wrong-wave --label another-fake" '
            "--label p2-wave-9"
        )
        self.assertEqual(vl.extract_labels(cmd), ["p2-wave-9"])

    def test_negative_body_equals_form(self):
        cmd = (
            'gh issue create --title t --body="mentions --label prose-label" --label real'
        )
        self.assertEqual(vl.extract_labels(cmd), ["real"])

    def test_negative_body_file_flag(self):
        cmd = "gh issue create --title t -F body.md --label real"
        self.assertEqual(vl.extract_labels(cmd), ["real"])

    def test_negative_title_is_not_scanned(self):
        cmd = "gh issue create --title 'refactor --label handling' --label tech-debt"
        self.assertEqual(vl.extract_labels(cmd), ["tech-debt"])

    def test_malformed_command_returns_empty(self):
        # Unclosed quote — shlex will raise; hook must degrade silently.
        self.assertEqual(vl.extract_labels("gh issue create --label 'unclosed"), [])


class TestExtractRepo(unittest.TestCase):
    def test_repo_space_form(self):
        self.assertEqual(
            vl.extract_repo(
                "gh issue create --repo noorinalabs/noorinalabs-main --label bug"
            ),
            "noorinalabs/noorinalabs-main",
        )

    def test_repo_short_flag(self):
        self.assertEqual(
            vl.extract_repo("gh issue create -R owner/repo --label bug"),
            "owner/repo",
        )

    def test_repo_equals_form(self):
        self.assertEqual(
            vl.extract_repo("gh issue create --repo=owner/repo --label bug"),
            "owner/repo",
        )

    def test_repo_absent(self):
        self.assertIsNone(vl.extract_repo("gh issue create --title t --label bug"))

    def test_repo_inside_body_not_extracted(self):
        """--repo inside a body value must NOT be treated as the real repo flag."""
        cmd = (
            'gh issue create --title t '
            '--body "example: gh issue create --repo wrong/repo" '
            "--repo right/repo --label bug"
        )
        self.assertEqual(vl.extract_repo(cmd), "right/repo")


class TestGetExistingLabelsForwardsRepo(unittest.TestCase):
    def test_repo_flag_forwarded(self):
        captured = {}

        class Result:
            returncode = 0
            stdout = "[]"

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return Result()

        with patch.object(vl.subprocess, "run", side_effect=fake_run):
            vl.get_existing_labels(repo="noorinalabs/noorinalabs-main")

        self.assertIn("--repo", captured["cmd"])
        idx = captured["cmd"].index("--repo")
        self.assertEqual(captured["cmd"][idx + 1], "noorinalabs/noorinalabs-main")

    def test_no_repo_flag_when_absent(self):
        captured = {}

        class Result:
            returncode = 0
            stdout = "[]"

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return Result()

        with patch.object(vl.subprocess, "run", side_effect=fake_run):
            vl.get_existing_labels()

        self.assertNotIn("--repo", captured["cmd"])


class TestCheckIntegration(unittest.TestCase):
    def _input(self, command: str) -> dict:
        return {"tool_name": "Bash", "tool_input": {"command": command}}

    def test_body_false_positive_does_not_block(self):
        """Key regression: body-only label mention must not trigger validation."""
        # Existing labels in target repo include "bug" but NOT "fake-label".
        with patch.object(vl, "get_existing_labels", return_value={"bug"}):
            result = vl.check(
                self._input(
                    "gh issue create --title t "
                    "--body 'docs: mentions --label fake-label in prose' "
                    "--label bug"
                )
            )
        self.assertIsNone(result)

    def test_missing_label_blocks(self):
        with patch.object(vl, "get_existing_labels", return_value={"bug"}):
            result = vl.check(
                self._input("gh issue create --title t --label does-not-exist")
            )
        self.assertIsNotNone(result)
        self.assertEqual(result["decision"], "block")
        self.assertIn("does-not-exist", result["reason"])

    def test_repo_forwarded_to_label_lookup(self):
        captured = {}

        def fake_get(repo=None):
            captured["repo"] = repo
            return {"bug"}

        with patch.object(vl, "get_existing_labels", side_effect=fake_get):
            vl.check(
                self._input(
                    "gh issue create --repo noorinalabs/noorinalabs-main "
                    "--title t --label bug"
                )
            )
        self.assertEqual(captured["repo"], "noorinalabs/noorinalabs-main")


if __name__ == "__main__":
    unittest.main()
