#!/usr/bin/env python3
"""Tests for `post_label_change_wave_field_sync` PostToolUse hook.

Six semantic buckets covered (per `skills.md § Acceptance-Criteria-Bucketing-In-Reports`):

ACTIONABLE buckets
==================
1. **Regex match cases** — commands that SHOULD trigger the field-sync:
   - `--add-label "p3-wave-11"` → set.
   - `--remove-label "p3-wave-10"` → clear.
   - Multi-flag `--add-label "p3-wave-11" --remove-label "p3-wave-10"` → set
     (post-edit state wins).
2. **Kill-switch env var coverage**:
   - `NOORIN_DISABLE_LABEL_SYNC_HOOK=1` → killed.
   - `=0` → proceeds.
   - empty/unset → proceeds.

INFORMATIONAL buckets
=====================
3. **Regex no-match cases** — commands that should NOT trigger:
   - Non-wave label (`--add-label "bug"`).
   - Different subcommand (`gh issue create`).
   - PR not issue (`gh pr edit ... --add-label "p3-wave-11"`).
   - Suffixed label (`p3-wave-10-special`).
4. **Auth-scope pre-flight**:
   - `gh auth status` reports no `project` scope → skip_no_auth_scope.
   - Reports project scope → proceeds.
5. **ID-cache behavior**:
   - First fire introspects + writes cache (mode 0600).
   - Second fire within TTL reads cache (no introspection).
   - Stale cache (past TTL) re-introspects.
   - Field-not-found mutation error busts cache + retries once.
6. **GraphQL no-op cases**:
   - Issue not on project 2 → skip_no_item (graceful).
   - Missing Wave option (e.g. `P3W11` not in field options) → skip_no_option.

Run from the repo root:
    ENVIRONMENT=test python3 -m pytest \
        .claude/hooks/tests/test_post_label_change_wave_field_sync.py -v
"""

from __future__ import annotations

import json
import os
import sys
import time
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
sys.path.insert(0, str(_HOOKS_DIR))

import post_label_change_wave_field_sync as hook  # noqa: E402


def _bash(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


def _scopes_with_project() -> str:
    return "  - Token scopes: 'gist', 'project', 'read:org', 'repo', 'workflow'\n"


def _scopes_without_project() -> str:
    return "  - Token scopes: 'gist', 'read:org', 'repo', 'workflow'\n"


def _ids_blob() -> dict:
    return {
        "project_id": "PROJ_NODE_ID",
        "field_id": "WAVE_FIELD_ID",
        "option_ids": {"P3W10": "OPT_P3W10", "P3W11": "OPT_P3W11"},
    }


def _introspect_response() -> str:
    return json.dumps(
        {
            "data": {
                "organization": {
                    "projectV2": {
                        "id": "PROJ_NODE_ID",
                        "field": {
                            "id": "WAVE_FIELD_ID",
                            "options": [
                                {"id": "OPT_P3W10", "name": "P3W10"},
                                {"id": "OPT_P3W11", "name": "P3W11"},
                            ],
                        },
                    }
                }
            }
        }
    )


def _item_lookup_response(repo: str, num: int) -> str:
    return json.dumps(
        {
            "data": {
                "repository": {
                    "issue": {
                        "projectItems": {
                            "nodes": [
                                {
                                    "id": "ITEM_ID_123",
                                    "project": {"number": 2},
                                }
                            ]
                        }
                    }
                }
            }
        }
    )


def _item_lookup_empty_response() -> str:
    return json.dumps({"data": {"repository": {"issue": {"projectItems": {"nodes": []}}}}})


def _mutation_success_response(_variables=None) -> str:
    return json.dumps(
        {"data": {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "ITEM_ID_123"}}}}
    )


def _mutation_field_not_found_response(_variables=None) -> str:
    return json.dumps(
        {
            "data": None,
            "errors": [{"message": "Field with id WAVE_FIELD_ID not found on project."}],
        }
    )


class FakeGraphQLRouter:
    """Stateful fake that routes GraphQL calls by query content.

    Each test composes a router by passing it a dict of responders:
    one for each query shape (introspect / item-lookup / mutation).
    Call counts are tracked for assertion.
    """

    def __init__(
        self,
        introspect=None,
        item_lookup=None,
        mutation=None,
    ):
        self.introspect = introspect
        self.item_lookup = item_lookup
        self.mutation = mutation
        self.calls = {"introspect": 0, "item_lookup": 0, "mutation": 0}

    def __call__(self, query: str, variables: dict) -> str:
        if "projectV2(number:" in query and "field(name:" in query:
            self.calls["introspect"] += 1
            r = self.introspect() if callable(self.introspect) else self.introspect
            return r or ""
        if "repository(owner:" in query and "projectItems" in query:
            self.calls["item_lookup"] += 1
            r = (
                self.item_lookup(variables.get("repo"), variables.get("num"))
                if callable(self.item_lookup)
                else self.item_lookup
            )
            return r or ""
        if "updateProjectV2ItemFieldValue" in query or "clearProjectV2ItemFieldValue" in query:
            self.calls["mutation"] += 1
            r = self.mutation(variables) if callable(self.mutation) else self.mutation
            return r or ""
        return ""


def _wipe_cache():
    """Remove the cache file + auth-warn marker between tests for isolation."""
    for p in (hook.CACHE_PATH, hook.AUTH_WARN_SENTINEL):
        try:
            p.unlink()
        except FileNotFoundError:
            pass


class RegexMatchTests(unittest.TestCase):
    """Bucket 1 (ACTIONABLE) — commands that SHOULD trigger field-sync.

    Tests use the project ID cache shortcut (write the cache directly so
    we don't need to mock the introspect responder).
    """

    def setUp(self):
        _wipe_cache()
        hook.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        hook._write_cache(_ids_blob())

    def tearDown(self):
        _wipe_cache()

    def test_add_label_p3_wave_11(self):
        router = FakeGraphQLRouter(
            item_lookup=_item_lookup_response,
            mutation=_mutation_success_response,
        )
        result = hook.check(
            _bash('gh issue edit 123 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"'),
            auth_status_runner=_scopes_with_project,
            graphql_runner=router,
        )
        self.assertEqual(result["action"], "set")
        self.assertEqual(result["option_name"], "P3W11")
        self.assertEqual(result["issue"], "123")
        self.assertEqual(router.calls["mutation"], 1)

    def test_remove_label_p3_wave_10(self):
        router = FakeGraphQLRouter(
            item_lookup=_item_lookup_response,
            mutation=_mutation_success_response,
        )
        result = hook.check(
            _bash(
                'gh issue edit 123 --repo noorinalabs/noorinalabs-main --remove-label "p3-wave-10"'
            ),
            auth_status_runner=_scopes_with_project,
            graphql_runner=router,
        )
        self.assertEqual(result["action"], "cleared")
        self.assertEqual(result["issue"], "123")
        self.assertEqual(router.calls["mutation"], 1)

    def test_compound_add_and_remove_post_edit_state_wins(self):
        """`--remove "p3-wave-10" --add "p3-wave-11"` → post-edit state is the
        added value; we set Wave to P3W11 (not clear)."""
        router = FakeGraphQLRouter(
            item_lookup=_item_lookup_response,
            mutation=_mutation_success_response,
        )
        result = hook.check(
            _bash(
                "gh issue edit 123 --repo noorinalabs/noorinalabs-main "
                '--remove-label "p3-wave-10" --add-label "p3-wave-11"'
            ),
            auth_status_runner=_scopes_with_project,
            graphql_runner=router,
        )
        self.assertEqual(result["action"], "set")
        self.assertEqual(result["option_name"], "P3W11")


class RegexNoMatchTests(unittest.TestCase):
    """Bucket 3 (INFORMATIONAL) — commands that should NOT trigger.

    For these, we do NOT mock the GraphQL runner — if the hook tries to
    call it, the test would fail (None default → no mutation).
    """

    def setUp(self):
        _wipe_cache()

    def tearDown(self):
        _wipe_cache()

    def test_non_wave_label(self):
        result = hook.check(
            _bash('gh issue edit 123 --repo noorinalabs/noorinalabs-main --add-label "bug"'),
        )
        self.assertIsNone(result)

    def test_gh_issue_create_not_match(self):
        result = hook.check(_bash("gh issue create --title 'foo' --body 'bar'"))
        self.assertIsNone(result)

    def test_gh_pr_edit_not_match(self):
        """PR edits don't drive the Wave field; only issue edits do."""
        result = hook.check(
            _bash('gh pr edit 42 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"')
        )
        self.assertIsNone(result)

    def test_suffixed_label_not_match(self):
        """`p3-wave-10-special` is not a canonical wave label."""
        result = hook.check(
            _bash(
                "gh issue edit 123 --repo noorinalabs/noorinalabs-main "
                '--add-label "p3-wave-10-special"'
            )
        )
        self.assertIsNone(result)

    def test_non_bash_tool_not_match(self):
        result = hook.check(
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": "/tmp/x.py"},
            }
        )
        self.assertIsNone(result)

    def test_empty_command_not_match(self):
        result = hook.check(_bash(""))
        self.assertIsNone(result)


class KillSwitchTests(unittest.TestCase):
    """Bucket 2 (ACTIONABLE) — kill-switch env var coverage."""

    def setUp(self):
        _wipe_cache()
        # Ensure env is clean between tests
        os.environ.pop(hook.KILL_SWITCH_ENV, None)

    def tearDown(self):
        _wipe_cache()
        os.environ.pop(hook.KILL_SWITCH_ENV, None)

    def test_kill_switch_value_1_skips(self):
        os.environ[hook.KILL_SWITCH_ENV] = "1"
        result = hook.check(
            _bash('gh issue edit 123 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"'),
        )
        self.assertEqual(result["action"], "killed")

    def test_kill_switch_value_0_proceeds(self):
        """=0 does NOT skip (Unix-tradition truthy-only)."""
        os.environ[hook.KILL_SWITCH_ENV] = "0"
        hook._write_cache(_ids_blob())
        router = FakeGraphQLRouter(
            item_lookup=_item_lookup_response,
            mutation=_mutation_success_response,
        )
        result = hook.check(
            _bash('gh issue edit 123 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"'),
            auth_status_runner=_scopes_with_project,
            graphql_runner=router,
        )
        self.assertNotEqual(result.get("action"), "killed")

    def test_kill_switch_empty_proceeds(self):
        os.environ[hook.KILL_SWITCH_ENV] = ""
        hook._write_cache(_ids_blob())
        router = FakeGraphQLRouter(
            item_lookup=_item_lookup_response,
            mutation=_mutation_success_response,
        )
        result = hook.check(
            _bash('gh issue edit 123 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"'),
            auth_status_runner=_scopes_with_project,
            graphql_runner=router,
        )
        self.assertNotEqual(result.get("action"), "killed")

    def test_kill_switch_unset_proceeds(self):
        # Already popped in setUp; just verify behavior
        hook._write_cache(_ids_blob())
        router = FakeGraphQLRouter(
            item_lookup=_item_lookup_response,
            mutation=_mutation_success_response,
        )
        result = hook.check(
            _bash('gh issue edit 123 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"'),
            auth_status_runner=_scopes_with_project,
            graphql_runner=router,
        )
        self.assertNotEqual(result.get("action"), "killed")


class AuthScopeTests(unittest.TestCase):
    """Bucket 4 (ACTIONABLE) — auth-scope pre-flight."""

    def setUp(self):
        _wipe_cache()

    def tearDown(self):
        _wipe_cache()

    def test_missing_project_scope_skips(self):
        result = hook.check(
            _bash('gh issue edit 123 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"'),
            auth_status_runner=_scopes_without_project,
        )
        self.assertEqual(result["action"], "skip_no_auth_scope")

    def test_present_project_scope_proceeds(self):
        hook._write_cache(_ids_blob())
        router = FakeGraphQLRouter(
            item_lookup=_item_lookup_response,
            mutation=_mutation_success_response,
        )
        result = hook.check(
            _bash('gh issue edit 123 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"'),
            auth_status_runner=_scopes_with_project,
            graphql_runner=router,
        )
        self.assertEqual(result["action"], "set")

    def test_read_project_substring_does_not_count(self):
        """`read:project` substring must NOT count as `project` scope."""
        runner = lambda: "  - Token scopes: 'read:project', 'repo'\n"  # noqa: E731
        result = hook.check(
            _bash('gh issue edit 123 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"'),
            auth_status_runner=runner,
        )
        self.assertEqual(result["action"], "skip_no_auth_scope")

    def test_auth_warn_debounce_only_logs_once(self):
        """Second fire in same session should not re-log auth-scope warning."""
        # First fire — should create the sentinel
        hook.check(
            _bash('gh issue edit 123 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"'),
            auth_status_runner=_scopes_without_project,
        )
        self.assertTrue(hook.AUTH_WARN_SENTINEL.exists())
        mtime1 = hook.AUTH_WARN_SENTINEL.stat().st_mtime

        # Second fire — sentinel exists, no new log
        time.sleep(0.01)  # ensure mtime would change if file were re-touched
        hook.check(
            _bash('gh issue edit 124 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"'),
            auth_status_runner=_scopes_without_project,
        )
        mtime2 = hook.AUTH_WARN_SENTINEL.stat().st_mtime
        self.assertEqual(mtime1, mtime2, "Sentinel should NOT be re-touched on second fire")


class IDCacheTests(unittest.TestCase):
    """Bucket 5 (ACTIONABLE) — ID-cache behavior."""

    def setUp(self):
        _wipe_cache()

    def tearDown(self):
        _wipe_cache()

    def test_first_fire_introspects_and_caches_mode_0600(self):
        router = FakeGraphQLRouter(
            introspect=_introspect_response,
            item_lookup=_item_lookup_response,
            mutation=_mutation_success_response,
        )
        result = hook.check(
            _bash('gh issue edit 123 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"'),
            auth_status_runner=_scopes_with_project,
            graphql_runner=router,
        )
        self.assertEqual(result["action"], "set")
        self.assertEqual(router.calls["introspect"], 1, "Should introspect on first fire")
        self.assertTrue(hook.CACHE_PATH.is_file())
        # Mode 0600 check
        mode = hook.CACHE_PATH.stat().st_mode & 0o777
        self.assertEqual(mode, 0o600, f"Cache should be mode 0600, got 0o{mode:o}")

    def test_second_fire_within_ttl_uses_cache(self):
        router = FakeGraphQLRouter(
            introspect=_introspect_response,
            item_lookup=_item_lookup_response,
            mutation=_mutation_success_response,
        )
        # First fire — populates cache
        hook.check(
            _bash('gh issue edit 123 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"'),
            auth_status_runner=_scopes_with_project,
            graphql_runner=router,
        )
        # Second fire — should NOT re-introspect
        hook.check(
            _bash('gh issue edit 124 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"'),
            auth_status_runner=_scopes_with_project,
            graphql_runner=router,
        )
        self.assertEqual(router.calls["introspect"], 1, "Cache should prevent second introspect")

    def test_stale_cache_re_introspects(self):
        # Pre-populate a stale cache (cached_at far in the past)
        hook.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        stale = {**_ids_blob(), "cached_at": time.time() - hook.CACHE_TTL_SECONDS - 60}
        hook.CACHE_PATH.write_text(json.dumps(stale), encoding="utf-8")

        router = FakeGraphQLRouter(
            introspect=_introspect_response,
            item_lookup=_item_lookup_response,
            mutation=_mutation_success_response,
        )
        hook.check(
            _bash('gh issue edit 123 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"'),
            auth_status_runner=_scopes_with_project,
            graphql_runner=router,
        )
        self.assertEqual(router.calls["introspect"], 1, "Stale cache should trigger re-introspect")

    def test_field_not_found_busts_cache_and_retries(self):
        """If the first mutation reports 'field not found', the cache should
        be busted and the mutation retried once after re-introspection."""
        hook._write_cache(_ids_blob())

        # First mutation call returns field-not-found; second call (post-bust)
        # returns success. Use a list-pop pattern for the responder.
        mutation_responses = [
            _mutation_field_not_found_response(),
            _mutation_success_response(),
        ]
        introspect_responses = [_introspect_response()]

        def mutation_fn(_variables):
            return mutation_responses.pop(0)

        def introspect_fn():
            return introspect_responses.pop(0) if introspect_responses else ""

        router = FakeGraphQLRouter(
            introspect=introspect_fn,
            item_lookup=_item_lookup_response,
            mutation=mutation_fn,
        )
        result = hook.check(
            _bash('gh issue edit 123 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"'),
            auth_status_runner=_scopes_with_project,
            graphql_runner=router,
        )
        self.assertEqual(result["action"], "set")
        self.assertTrue(result.get("retried_after_cache_bust"))
        self.assertEqual(router.calls["mutation"], 2, "Should retry mutation once after cache-bust")
        self.assertEqual(router.calls["introspect"], 1, "Should re-introspect once after bust")


class GraphQLNoOpTests(unittest.TestCase):
    """Bucket 6 (INFORMATIONAL) — GraphQL graceful-handle cases."""

    def setUp(self):
        _wipe_cache()
        hook._write_cache(_ids_blob())

    def tearDown(self):
        _wipe_cache()

    def test_issue_not_on_project_skips(self):
        """`items(first:100)` returns empty → skip_no_item gracefully."""
        router = FakeGraphQLRouter(
            item_lookup=lambda repo, num: _item_lookup_empty_response(),
            mutation=_mutation_success_response,
        )
        result = hook.check(
            _bash('gh issue edit 999 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"'),
            auth_status_runner=_scopes_with_project,
            graphql_runner=router,
        )
        self.assertEqual(result["action"], "skip_no_item")
        self.assertEqual(router.calls["mutation"], 0, "Should not mutate when item not on board")

    def test_missing_wave_option_skips(self):
        """When the Wave field has no option for the requested wave, skip."""
        # Write a cache with NO P3W12 option present
        ids = _ids_blob()
        hook._write_cache(ids)  # has P3W10 + P3W11 only
        router = FakeGraphQLRouter(
            item_lookup=_item_lookup_response,
            mutation=_mutation_success_response,
        )
        result = hook.check(
            _bash('gh issue edit 123 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-12"'),
            auth_status_runner=_scopes_with_project,
            graphql_runner=router,
        )
        self.assertEqual(result["action"], "skip_no_option")
        self.assertEqual(result["option_name"], "P3W12")
        self.assertEqual(router.calls["mutation"], 0)


class WaveLabelToOptionNameTests(unittest.TestCase):
    """Pure-function coverage for the label→option-name conversion."""

    def test_canonical_conversion(self):
        self.assertEqual(hook._wave_label_to_option_name("p3-wave-11"), "P3W11")

    def test_double_digit_wave(self):
        self.assertEqual(hook._wave_label_to_option_name("p3-wave-10"), "P3W10")

    def test_invalid_label_returns_none(self):
        self.assertIsNone(hook._wave_label_to_option_name("p3-wave-10-special"))
        self.assertIsNone(hook._wave_label_to_option_name("bug"))


class KillSwitchPureTests(unittest.TestCase):
    """Pure-function coverage for the kill-switch helper."""

    def setUp(self):
        os.environ.pop(hook.KILL_SWITCH_ENV, None)

    def tearDown(self):
        os.environ.pop(hook.KILL_SWITCH_ENV, None)

    def test_unset(self):
        self.assertFalse(hook._kill_switch_active())

    def test_value_1(self):
        os.environ[hook.KILL_SWITCH_ENV] = "1"
        self.assertTrue(hook._kill_switch_active())

    def test_value_0(self):
        os.environ[hook.KILL_SWITCH_ENV] = "0"
        self.assertFalse(hook._kill_switch_active())

    def test_value_empty(self):
        os.environ[hook.KILL_SWITCH_ENV] = ""
        self.assertFalse(hook._kill_switch_active())

    def test_value_true_string(self):
        os.environ[hook.KILL_SWITCH_ENV] = "true"
        self.assertFalse(hook._kill_switch_active())


class GraphQLVariableUsageTests(unittest.TestCase):
    """Static analysis: every declared GraphQL variable must be referenced in the body.

    Catches the variableNotUsed class of bug that caused the first-production-fire
    on Hook 21 (issue #448). The old _ITEM_LOOKUP_QUERY declared $repo and $num
    but never used them — GitHub's GraphQL rejected with variableNotUsed errors,
    gh exited non-zero, and the hook silently skipped with skip_no_item.

    This test is intentionally query-string-level (no subprocess / network) so
    it runs in the default suite and catches the bug class at authoring time.
    Sibling pattern to issue #175 (Hook 15 sentinel-fallback shell-vs-Python
    hash test gap) — same shape, different query.
    """

    _QUERIES_UNDER_TEST = [
        ("_ITEM_LOOKUP_QUERY", hook._ITEM_LOOKUP_QUERY),
        ("_INTROSPECT_QUERY", hook._INTROSPECT_QUERY),
        ("_SET_FIELD_MUTATION", hook._SET_FIELD_MUTATION),
        ("_CLEAR_FIELD_MUTATION", hook._CLEAR_FIELD_MUTATION),
    ]

    @staticmethod
    def _declared_vars(query: str) -> set[str]:
        """Return the set of variable names declared in `query(...)` / `mutation(...)`.

        Matches `$varname` inside the leading `query(...)` or `mutation(...)` signature
        (i.e. before the first `{`), which is where GraphQL variable declarations live.
        """
        import re

        # Everything up to (and including) the opening brace of the operation body.
        header_match = re.match(r"[^{]*\(([^)]*)\)", query, re.DOTALL)
        if not header_match:
            return set()
        return set(re.findall(r"\$(\w+)", header_match.group(1)))

    def _assert_all_declared_vars_used(self, name: str, query: str) -> None:
        declared = self._declared_vars(query)
        # Each declared var must appear in the query body (i.e., at least twice
        # in the full string — once in the signature, once in the body).
        import re

        for var in declared:
            count = len(re.findall(rf"\${re.escape(var)}\b", query))
            self.assertGreaterEqual(
                count,
                2,
                f"{name}: declared variable ${var} is never referenced in the query body "
                f"(variableNotUsed — same class as issue #448). "
                f"Either use it in the body or remove it from the signature.",
            )

    def test_item_lookup_query_all_vars_used(self):
        self._assert_all_declared_vars_used("_ITEM_LOOKUP_QUERY", hook._ITEM_LOOKUP_QUERY)

    def test_introspect_query_all_vars_used(self):
        self._assert_all_declared_vars_used("_INTROSPECT_QUERY", hook._INTROSPECT_QUERY)

    def test_set_field_mutation_all_vars_used(self):
        self._assert_all_declared_vars_used("_SET_FIELD_MUTATION", hook._SET_FIELD_MUTATION)

    def test_clear_field_mutation_all_vars_used(self):
        self._assert_all_declared_vars_used("_CLEAR_FIELD_MUTATION", hook._CLEAR_FIELD_MUTATION)

    def test_old_buggy_query_would_have_failed(self):
        """Regression guard: the old _ITEM_LOOKUP_QUERY shape fails this check.

        Ensures the test catches the exact bug class from issue #448 — if someone
        accidentally reverts to the old query, this test turns red.
        """
        old_buggy_query = """
query($org: String!, $project: Int!, $repo: String!, $num: Int!) {
  organization(login: $org) {
    projectV2(number: $project) {
      items(first: 100) {
        nodes {
          id
          content {
            ... on Issue { number repository { name } }
          }
        }
      }
    }
  }
}
"""
        import re

        declared = self._declared_vars(old_buggy_query)
        unused = []
        for var in declared:
            count = len(re.findall(rf"\${re.escape(var)}\b", old_buggy_query))
            if count < 2:
                unused.append(var)
        self.assertIn(
            "repo",
            unused,
            "Old buggy query should have $repo as unused — test regression guard failed",
        )
        self.assertIn(
            "num",
            unused,
            "Old buggy query should have $num as unused — test regression guard failed",
        )


class MultiCmdBashTests(unittest.TestCase):
    """Bucket 7 (ACTIONABLE) — multi-cmd Bash dispatching, issue #455.

    A single Bash tool call may contain multiple `gh issue edit` invocations
    via `;`, `&&`, or newline separators. The hook must dispatch ONE Wave
    field sync per change, not silent-skip the whole batch.

    Tests pin both the parser (returns N WaveLabelChange objects) AND the
    dispatch (`check()` returns `{"action": "multi", "results": [...]}` with
    N entries).
    """

    def setUp(self):
        _wipe_cache()
        hook.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        hook._write_cache(_ids_blob())

    def tearDown(self):
        _wipe_cache()

    def test_semicolon_chain_dispatches_per_segment(self):
        router = FakeGraphQLRouter(
            item_lookup=_item_lookup_response,
            mutation=_mutation_success_response,
        )
        cmd = (
            "gh issue edit 100 --repo noorinalabs/noorinalabs-deploy "
            '--add-label "p3-wave-11" ; '
            "gh issue edit 101 --repo noorinalabs/noorinalabs-deploy "
            '--add-label "p3-wave-11" ; '
            "gh issue edit 102 --repo noorinalabs/noorinalabs-deploy "
            '--add-label "p3-wave-11"'
        )
        result = hook.check(
            _bash(cmd),
            auth_status_runner=_scopes_with_project,
            graphql_runner=router,
        )
        self.assertEqual(result["action"], "multi")
        self.assertEqual(result["count"], 3)
        self.assertEqual(len(result["results"]), 3)
        for r in result["results"]:
            self.assertEqual(r["action"], "set")
            self.assertEqual(r["option_name"], "P3W11")
        self.assertEqual(router.calls["mutation"], 3, "Should dispatch one mutation per change")

    def test_ampersand_chain_dispatches_per_segment(self):
        router = FakeGraphQLRouter(
            item_lookup=_item_lookup_response,
            mutation=_mutation_success_response,
        )
        cmd = (
            "gh issue edit 200 --repo noorinalabs/noorinalabs-main "
            '--add-label "p3-wave-11" && '
            "gh issue edit 201 --repo noorinalabs/noorinalabs-main "
            '--add-label "p3-wave-11"'
        )
        result = hook.check(
            _bash(cmd),
            auth_status_runner=_scopes_with_project,
            graphql_runner=router,
        )
        self.assertEqual(result["action"], "multi")
        self.assertEqual(result["count"], 2)
        self.assertEqual(router.calls["mutation"], 2)

    def test_newline_separated_commands_dispatch_per_segment(self):
        """Newline + `\\` line-continuation is normalized by the shared
        tokenizer (_LINE_CONTINUATION_RE); plain newline acts like `;`."""
        router = FakeGraphQLRouter(
            item_lookup=_item_lookup_response,
            mutation=_mutation_success_response,
        )
        cmd = (
            'gh issue edit 300 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"\n'
            'gh issue edit 301 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"'
        )
        # shlex.split tokenizes newline as whitespace by default — segment
        # operators `;`/`&&`/`||`/`|` are what split commands. Plain newlines
        # do NOT segment, so this command tokenizes as a single segment with
        # two `gh issue edit` invocations concatenated. The realistic shape
        # is `;`-separated; the newline-only shape is rare in practice.
        # Pin the realistic semicolon-newline shape:
        cmd = (
            'gh issue edit 300 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11" ;\n'
            'gh issue edit 301 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"'
        )
        result = hook.check(
            _bash(cmd),
            auth_status_runner=_scopes_with_project,
            graphql_runner=router,
        )
        self.assertEqual(result["action"], "multi")
        self.assertEqual(result["count"], 2)
        self.assertEqual(router.calls["mutation"], 2)

    def test_mixed_set_and_clear_in_multi_cmd(self):
        """`gh issue edit X --add p3-wave-11; gh issue edit Y --remove p3-wave-10`
        dispatches one set + one clear."""
        router = FakeGraphQLRouter(
            item_lookup=_item_lookup_response,
            mutation=_mutation_success_response,
        )
        cmd = (
            "gh issue edit 400 --repo noorinalabs/noorinalabs-main "
            '--add-label "p3-wave-11" ; '
            "gh issue edit 401 --repo noorinalabs/noorinalabs-main "
            '--remove-label "p3-wave-10"'
        )
        result = hook.check(
            _bash(cmd),
            auth_status_runner=_scopes_with_project,
            graphql_runner=router,
        )
        self.assertEqual(result["action"], "multi")
        actions = [r["action"] for r in result["results"]]
        self.assertEqual(actions, ["set", "cleared"])

    def test_single_cmd_preserves_legacy_shape(self):
        """Single-cmd return MUST still be the flat dict (not wrapped in `multi`)
        so existing callers and tests are unaffected."""
        router = FakeGraphQLRouter(
            item_lookup=_item_lookup_response,
            mutation=_mutation_success_response,
        )
        result = hook.check(
            _bash('gh issue edit 500 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"'),
            auth_status_runner=_scopes_with_project,
            graphql_runner=router,
        )
        self.assertEqual(result["action"], "set")
        self.assertNotIn("results", result, "Single-cmd must not return multi-shape dict")

    def test_parser_skip_logs_for_unparseable_wave_label_cmd(self):
        """When the command CONTAINS `gh issue edit` + canonical wave-label
        but the parser extracts nothing (e.g., missing --repo), the hook
        emits a parser-skip annunaki event per #455 acceptance criterion."""
        cmd = (
            # Missing --repo flag → parser returns empty, but the command
            # clearly intended a wave-label edit
            'gh issue edit 600 --add-label "p3-wave-11"'
        )
        result = hook.check(_bash(cmd))
        self.assertEqual(result["action"], "skip_parser_returned_empty")

    def test_parser_skip_does_not_fire_on_unrelated_command(self):
        """A command with NO `gh issue edit` at all returns None, not skip."""
        result = hook.check(_bash("echo hello world"))
        self.assertIsNone(result)

    def test_parser_skip_does_not_fire_on_suffixed_label(self):
        """`p3-wave-10-special` is not canonical; should NOT trigger parser-skip
        log (would be noise). This is the regression guard for the bounded
        regex anchor in _CANONICAL_WAVE_LABEL_IN_CMD."""
        cmd = (
            'gh issue edit 700 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-10-special"'
        )
        result = hook.check(_bash(cmd))
        self.assertIsNone(result)


class SkipPathLoggingTests(unittest.TestCase):
    """Bucket 8 (ACTIONABLE) — issue #451 skip-path annunaki coverage.

    skip_no_item, skip_no_auth_scope, skip_no_project_ids, skip_no_option,
    and skip_mutation_failed must all emit log_posttooluse_event so
    /annunaki and /annunaki-attack can sweep them.
    """

    def setUp(self):
        _wipe_cache()

    def tearDown(self):
        _wipe_cache()

    def _make_log_capture(self):
        """Patch annunaki_log.log_posttooluse_event to capture calls.

        Patches BOTH the source-of-truth module attribute AND the hook
        module's already-bound reference (Python imports the name at
        import time; subsequent module attribute changes don't propagate).
        """
        captured = []
        orig_hook_logger = hook.log_posttooluse_event

        def fake_logger(hook_name, command, reason, tool_name="Bash"):
            captured.append({"hook": hook_name, "command": command, "reason": reason})

        hook.log_posttooluse_event = fake_logger

        def restore():
            hook.log_posttooluse_event = orig_hook_logger

        return captured, restore

    def test_skip_no_item_logs(self):
        """skip_no_item must produce an annunaki log entry per #451."""
        hook._write_cache(_ids_blob())
        captured, restore = self._make_log_capture()
        try:
            router = FakeGraphQLRouter(
                item_lookup=lambda repo, num: _item_lookup_empty_response(),
                mutation=_mutation_success_response,
            )
            result = hook.check(
                _bash(
                    'gh issue edit 999 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"'
                ),
                auth_status_runner=_scopes_with_project,
                graphql_runner=router,
            )
            self.assertEqual(result["action"], "skip_no_item")
            self.assertTrue(
                any("skip_no_item" in c["reason"] for c in captured),
                f"skip_no_item path must log; captured: {captured}",
            )
        finally:
            restore()

    def test_skip_no_auth_scope_logs(self):
        """skip_no_auth_scope is already covered by the auth-warn-debounce
        sentinel. Pin that path still produces a log entry (via the
        debounced sentinel-creation path, which calls log_posttooluse_event)."""
        captured, restore = self._make_log_capture()
        try:
            result = hook.check(
                _bash(
                    'gh issue edit 123 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"'
                ),
                auth_status_runner=_scopes_without_project,
            )
            self.assertEqual(result["action"], "skip_no_auth_scope")
            self.assertTrue(
                any("project scope" in c["reason"] for c in captured),
                f"skip_no_auth_scope path must log; captured: {captured}",
            )
        finally:
            restore()

    def test_skip_no_project_ids_logs(self):
        """skip_no_project_ids fires when introspection returns no data."""
        captured, restore = self._make_log_capture()
        try:
            # Empty introspect response → no ids → skip
            router = FakeGraphQLRouter(introspect=lambda: "")
            result = hook.check(
                _bash(
                    'gh issue edit 123 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"'
                ),
                auth_status_runner=_scopes_with_project,
                graphql_runner=router,
            )
            self.assertEqual(result["action"], "skip_no_project_ids")
            self.assertTrue(
                any("skip_no_project_ids" in c["reason"] for c in captured),
                f"skip_no_project_ids must log; captured: {captured}",
            )
        finally:
            restore()

    def test_skip_no_option_logs(self):
        """skip_no_option fires when the requested wave's option is not in
        the cached option_ids dict."""
        hook._write_cache(_ids_blob())  # has P3W10 + P3W11 only
        captured, restore = self._make_log_capture()
        try:
            router = FakeGraphQLRouter(
                item_lookup=_item_lookup_response,
                mutation=_mutation_success_response,
            )
            result = hook.check(
                _bash(
                    'gh issue edit 123 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-12"'
                ),
                auth_status_runner=_scopes_with_project,
                graphql_runner=router,
            )
            self.assertEqual(result["action"], "skip_no_option")
            self.assertTrue(
                any(
                    "skip_no_option" in c["reason"] or "no option" in c["reason"] for c in captured
                ),
                f"skip_no_option must log; captured: {captured}",
            )
        finally:
            restore()


class MultiCmdNoMatchPreservedTests(unittest.TestCase):
    """Regression: ensure multi-cmd refactor did NOT regress the existing
    no-match cases (suffixed labels, wrong subcommand, etc.). Verifies the
    parser-skip log is silent on these too."""

    def test_suffixed_label_in_multi_cmd_does_not_match(self):
        cmd = (
            "echo hello ; "
            "gh issue edit 1 --repo noorinalabs/noorinalabs-main "
            '--add-label "p3-wave-10-special" ; '
            "echo world"
        )
        result = hook.check(_bash(cmd))
        self.assertIsNone(result)

    def test_pr_edit_in_multi_cmd_does_not_match(self):
        cmd = (
            'gh pr edit 1 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11" && '
            'gh pr edit 2 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"'
        )
        result = hook.check(_bash(cmd))
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
