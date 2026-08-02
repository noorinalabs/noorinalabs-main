"""Tests for gh_quota_gate.py — the PreToolUse gate on GraphQL-backed gh calls (#1224).

Coverage maps to the module's own design-judgement sections:

  - Cheap prefilter: a non-gh / non-Bash command never touches gh_quota at all.
  - Degrade-to-ALLOW: an unknown quota reading never blocks (the load-bearing
    #1224 requirement).
  - Block-with-rewrite: every pattern in _BLOCK_PATTERNS, including the
    corrected `gh project item-add` (now block, not advise — #1224 finding).
  - Advise-only: a raw `gh api graphql` call and any recognized-but-unmapped
    project verb never block, even under exhausted quota.
  - Command-position discipline: a heredoc-embedded mention doesn't match.
  - Kill switch + configurable threshold, with an exact >= boundary pin
    (mutation-test target).
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gh_quota_gate as gate  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))
import gh_quota  # noqa: E402


def _quota(remaining, limit=5000, reset_epoch=99999999999):
    return gh_quota.ResourceQuota("graphql", remaining, limit, reset_epoch)


def _input(command: str, env: dict | None = None) -> dict:
    data = {"tool_name": "Bash", "tool_input": {"command": command}}
    if env:
        data["env"] = env
    return data


class CheapPrefilterTests(unittest.TestCase):
    def test_non_bash_tool_never_touches_quota(self):
        with mock.patch.object(gate.gh_quota, "resource_quota") as rq:
            result = gate.check({"tool_name": "Edit", "tool_input": {}})
        self.assertIsNone(result)
        rq.assert_not_called()

    def test_non_gh_command_never_touches_quota(self):
        with mock.patch.object(gate.gh_quota, "resource_quota") as rq:
            result = gate.check(_input("ls -la /tmp"))
        self.assertIsNone(result)
        rq.assert_not_called()

    def test_gh_command_not_in_pattern_table_never_touches_quota(self):
        """`gh pr diff` is measured OK under exhaustion — no pattern matches it,
        so it must not even trigger a quota check."""
        with mock.patch.object(gate.gh_quota, "resource_quota") as rq:
            result = gate.check(_input("gh pr diff 1207 --repo noorinalabs/noorinalabs-main"))
        self.assertIsNone(result)
        rq.assert_not_called()

    def test_command_position_discipline_heredoc_mention_not_matched(self):
        """A `gh issue view` string sitting inert in a heredoc body must not match
        (mirrors block_gh_pr_review's own command-position test)."""
        command = "cat <<'EOF' > notes.md\nrun: gh issue view 5\nEOF"
        with mock.patch.object(gate.gh_quota, "resource_quota") as rq:
            result = gate.check(_input(command))
        self.assertIsNone(result)
        rq.assert_not_called()


class AstSegmentDiscoveryTests(unittest.TestCase):
    """The shlex-only path only ever sees a `gh` call sitting at the TOP
    LEVEL of the command string — a `gh` invocation inside a `$(...)`/backtick
    command substitution, or inside a `for ... do ... done` loop body, never
    reached `find_gh_subcommand` at all (main#1225 review, the must-fix on
    Nadia Khoury's merge-gate verdict). These pin the AST-first `_segments()`
    fix: each must now match and block under low quota."""

    def test_command_substitution_dollar_paren_matches(self):
        command = (
            "SHA=$(gh pr view 1225 --repo noorinalabs/noorinalabs-main "
            "--json headRefOid --jq '.headRefOid')"
        )
        with mock.patch.object(gate.gh_quota, "resource_quota", return_value=_quota(0)):
            result = gate.check(_input(command))
        self.assertIsNotNone(result, "gh call inside $(...) must be seen by the gate")
        self.assertEqual(result["decision"], "block")
        self.assertIn("gh_rest.py pr view 1225", result["reason"])

    def test_backtick_command_substitution_matches(self):
        command = "SHA=`gh pr view 1225 --repo noorinalabs/noorinalabs-main --json headRefOid`"
        with mock.patch.object(gate.gh_quota, "resource_quota", return_value=_quota(0)):
            result = gate.check(_input(command))
        self.assertIsNotNone(result, "gh call inside backticks must be seen by the gate")
        self.assertEqual(result["decision"], "block")
        self.assertIn("gh_rest.py pr view 1225", result["reason"])

    def test_loop_body_matches(self):
        command = "for i in 1 2; do gh issue view $i --repo noorinalabs/noorinalabs-main; done"
        with mock.patch.object(gate.gh_quota, "resource_quota", return_value=_quota(0)):
            result = gate.check(_input(command))
        self.assertIsNotNone(result, "gh call inside a loop body must be seen by the gate")
        self.assertEqual(result["decision"], "block")
        self.assertIn("gh_rest.py issue view", result["reason"])


class DegradeToAllowTests(unittest.TestCase):
    """The load-bearing #1224 design requirement."""

    def test_unknown_quota_never_blocks_even_for_a_matched_pattern(self):
        with mock.patch.object(gate.gh_quota, "resource_quota", return_value=None):
            result = gate.check(_input("gh issue view 1224 --repo noorinalabs/noorinalabs-main"))
        self.assertIsNone(result, "an unknown quota reading must degrade to ALLOW, never block")


class BlockWithRewriteTests(unittest.TestCase):
    def test_blocks_issue_view_when_quota_low(self):
        with mock.patch.object(gate.gh_quota, "resource_quota", return_value=_quota(0)):
            result = gate.check(_input("gh issue view 1224 --repo noorinalabs/noorinalabs-main"))
        self.assertEqual(result["decision"], "block")
        self.assertIn("gh_rest.py issue view 1224", result["reason"])

    def test_allows_issue_view_when_quota_sufficient(self):
        with mock.patch.object(gate.gh_quota, "resource_quota", return_value=_quota(4000)):
            result = gate.check(_input("gh issue view 1224 --repo noorinalabs/noorinalabs-main"))
        self.assertIsNone(result)

    def test_blocks_issue_list(self):
        with mock.patch.object(gate.gh_quota, "resource_quota", return_value=_quota(0)):
            result = gate.check(_input("gh issue list --repo noorinalabs/noorinalabs-main"))
        self.assertEqual(result["decision"], "block")
        self.assertIn("gh_rest.py issue list", result["reason"])

    def test_blocks_pr_view(self):
        with mock.patch.object(gate.gh_quota, "resource_quota", return_value=_quota(0)):
            result = gate.check(_input("gh pr view 1207 --json number,state"))
        self.assertEqual(result["decision"], "block")
        self.assertIn("gh_rest.py pr view 1207", result["reason"])

    def test_blocks_pr_view_even_without_json_flag(self):
        """A single field/bare pr view was observed to succeed ONCE then fail on
        repeat — never rely on that; block unconditionally under low quota."""
        with mock.patch.object(gate.gh_quota, "resource_quota", return_value=_quota(0)):
            result = gate.check(_input("gh pr view 1207 --repo noorinalabs/noorinalabs-main"))
        self.assertEqual(result["decision"], "block")

    def test_blocks_pr_checks(self):
        with mock.patch.object(gate.gh_quota, "resource_quota", return_value=_quota(0)):
            result = gate.check(_input("gh pr checks 1207 --repo noorinalabs/noorinalabs-main"))
        self.assertEqual(result["decision"], "block")
        self.assertIn("headRefOid", result["reason"])

    def test_blocks_pr_comment(self):
        with mock.patch.object(gate.gh_quota, "resource_quota", return_value=_quota(0)):
            result = gate.check(
                _input("gh pr comment 1207 --body 'lgtm' --repo noorinalabs/noorinalabs-main")
            )
        self.assertEqual(result["decision"], "block")
        self.assertIn("write-payload", result["reason"])

    def test_blocks_issue_create(self):
        with mock.patch.object(gate.gh_quota, "resource_quota", return_value=_quota(0)):
            result = gate.check(
                _input("gh issue create --repo noorinalabs/noorinalabs-main --title x --body y")
            )
        self.assertEqual(result["decision"], "block")
        self.assertIn("repos/noorinalabs/noorinalabs-main/issues", result["reason"])

    def test_blocks_project_item_add_with_verified_rest_rewrite(self):
        """The corrected #1224 finding: item-add now has a verified REST path,
        so it BLOCKS (with a rewrite), it does not merely advise."""
        with mock.patch.object(gate.gh_quota, "resource_quota", return_value=_quota(0)):
            result = gate.check(
                _input(
                    "gh project item-add 2 --owner noorinalabs --url https://github.com/noorinalabs/noorinalabs-main/issues/1224"
                )
            )
        self.assertEqual(result["decision"], "block")
        self.assertIn("gh_rest.py project add", result["reason"])
        self.assertIn("org-owned", result["reason"])

    def test_blocks_project_item_list(self):
        with mock.patch.object(gate.gh_quota, "resource_quota", return_value=_quota(0)):
            result = gate.check(_input("gh project item-list 2 --owner noorinalabs --limit 2000"))
        self.assertEqual(result["decision"], "block")
        self.assertIn("gh_rest.py project items", result["reason"])

    def test_never_pipes_to_devnull_language_in_reason(self):
        """The rewrite/reason text must actively warn against the customary
        2>/dev/null-masks-exhaustion footgun (§12), not just fix the command."""
        with mock.patch.object(gate.gh_quota, "resource_quota", return_value=_quota(0)):
            result = gate.check(_input("gh issue view 1224 --repo noorinalabs/noorinalabs-main"))
        self.assertIn("SILENT ZERO", result["reason"])


class AdviseOnlyTests(unittest.TestCase):
    """Genuinely-unsupported / un-derivable shapes must ALLOW with a warning,
    never block — converting a slowdown into a hard stop is the exact failure
    the #1224 issue body warns against."""

    def test_raw_graphql_call_advises_not_blocks(self):
        with mock.patch.object(gate.gh_quota, "resource_quota", return_value=_quota(0)):
            result = gate.check(_input("gh api graphql -f query='query { viewer { login } }'"))
        self.assertEqual(result["decision"], "allow")
        self.assertIn("systemMessage", result)
        self.assertIn("NO verified REST rewrite", result["systemMessage"])

    def test_unmapped_project_verb_advises_not_blocks(self):
        with mock.patch.object(gate.gh_quota, "resource_quota", return_value=_quota(0)):
            result = gate.check(
                _input("gh project item-edit 2 --id ITEM --field-id F --text-value x")
            )
        self.assertEqual(result["decision"], "allow")
        self.assertIn("systemMessage", result)

    def test_raw_graphql_call_under_sufficient_quota_is_a_plain_allow(self):
        with mock.patch.object(gate.gh_quota, "resource_quota", return_value=_quota(4000)):
            result = gate.check(_input("gh api graphql -f query='query { viewer { login } }'"))
        self.assertIsNone(result)


class KillSwitchAndThresholdTests(unittest.TestCase):
    def test_kill_switch_disables_the_hook(self):
        import os

        old = os.environ.get("NOORIN_DISABLE_GH_QUOTA_GATE")
        os.environ["NOORIN_DISABLE_GH_QUOTA_GATE"] = "1"
        try:
            with mock.patch.object(gate.gh_quota, "resource_quota") as rq:
                result = gate.check(
                    _input("gh issue view 1224 --repo noorinalabs/noorinalabs-main")
                )
            self.assertIsNone(result)
            rq.assert_not_called()
        finally:
            if old is None:
                del os.environ["NOORIN_DISABLE_GH_QUOTA_GATE"]
            else:
                os.environ["NOORIN_DISABLE_GH_QUOTA_GATE"] = old

    def test_configurable_min_threshold(self):
        import os

        old = os.environ.get("NOORIN_GH_QUOTA_MIN")
        os.environ["NOORIN_GH_QUOTA_MIN"] = "100"
        try:
            with mock.patch.object(gate.gh_quota, "resource_quota", return_value=_quota(50)):
                result = gate.check(
                    _input("gh issue view 1224 --repo noorinalabs/noorinalabs-main")
                )
            self.assertEqual(result["decision"], "block", "50 < configured min 100 must block")
        finally:
            if old is None:
                os.environ.pop("NOORIN_GH_QUOTA_MIN", None)
            else:
                os.environ["NOORIN_GH_QUOTA_MIN"] = old

    def test_boundary_remaining_equals_default_min_allows(self):
        """remaining == min is the ALLOW side (>=) — mutation-test pin,
        mirrors the identical pin in test_gh_quota.py's guard boundary test."""
        with mock.patch.object(
            gate.gh_quota, "resource_quota", return_value=_quota(gate.DEFAULT_MIN_GRAPHQL)
        ):
            result = gate.check(_input("gh issue view 1224 --repo noorinalabs/noorinalabs-main"))
        self.assertIsNone(result)

    def test_boundary_one_below_min_blocks(self):
        with mock.patch.object(
            gate.gh_quota, "resource_quota", return_value=_quota(gate.DEFAULT_MIN_GRAPHQL - 1)
        ):
            result = gate.check(_input("gh issue view 1224 --repo noorinalabs/noorinalabs-main"))
        self.assertEqual(result["decision"], "block")


class MainEntrypointTests(unittest.TestCase):
    def test_main_exits_2_on_block(self):
        payload = json.dumps(_input("gh issue view 1224 --repo noorinalabs/noorinalabs-main"))
        with mock.patch.object(gate.gh_quota, "resource_quota", return_value=_quota(0)):
            with mock.patch.object(gate.sys, "stdin", _StdinStub(payload)):
                with self.assertRaises(SystemExit) as ctx:
                    gate.main()
        self.assertEqual(ctx.exception.code, 2)

    def test_main_exits_0_on_allow(self):
        payload = json.dumps(_input("ls -la"))
        with mock.patch.object(gate.sys, "stdin", _StdinStub(payload)):
            with self.assertRaises(SystemExit) as ctx:
                gate.main()
        self.assertEqual(ctx.exception.code, 0)

    def test_main_exits_0_on_bad_json_never_crashes(self):
        with mock.patch.object(gate.sys, "stdin", _StdinStub("not json")):
            with self.assertRaises(SystemExit) as ctx:
                gate.main()
        self.assertEqual(ctx.exception.code, 0)


class _StdinStub:
    def __init__(self, text: str) -> None:
        self._text = text

    def read(self) -> str:
        return self._text


if __name__ == "__main__":
    unittest.main()
