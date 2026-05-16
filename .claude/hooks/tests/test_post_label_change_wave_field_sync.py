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
                "organization": {
                    "projectV2": {
                        "items": {
                            "nodes": [
                                {
                                    "id": "ITEM_ID_123",
                                    "content": {
                                        "number": num,
                                        "repository": {"name": repo},
                                    },
                                }
                            ]
                        }
                    }
                }
            }
        }
    )


def _item_lookup_empty_response() -> str:
    return json.dumps({"data": {"organization": {"projectV2": {"items": {"nodes": []}}}}})


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
        if "items(first:" in query:
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


if __name__ == "__main__":
    unittest.main()
