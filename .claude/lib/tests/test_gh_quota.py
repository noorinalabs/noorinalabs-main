"""Tests for gh_quota.py — the core/graphql rate-limit sensor (#1224).

Coverage:
  1. fetch_rate_limit parses a real rate_limit shape, and never raises on any
     failure mode (bad exit, malformed JSON, timeout, missing gh binary).
  2. fetch_rate_limit issues EXACTLY the free `gh api rate_limit` call — pins
     the "never itself consumes quota" claim at the command-args level.
  3. get_quota's caching: fresh-cache short-circuits the fetch; stale cache
     triggers exactly one refetch; a failed refetch falls back to a stale
     cache entry rather than nothing; no cache + failed fetch -> None.
  4. guard degrades to ALLOW (exit 0) when the reading is unknown — the
     load-bearing #1224 design requirement — and the >= boundary is exact.
"""

from __future__ import annotations

import contextlib
import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gh_quota  # noqa: E402


@contextlib.contextmanager
def _tmp_ctx():
    with tempfile.TemporaryDirectory() as d:
        yield d


def _rate_limit_stdout(
    core_remaining=4986, graphql_remaining=0, core_reset=9999999999, graphql_reset=8888888888
):
    return json.dumps(
        {
            "resources": {
                "core": {
                    "limit": 5000,
                    "remaining": core_remaining,
                    "reset": core_reset,
                    "used": 5000 - core_remaining,
                },
                "graphql": {
                    "limit": 5000,
                    "remaining": graphql_remaining,
                    "reset": graphql_reset,
                    "used": 5000 - graphql_remaining,
                },
                "search": {"limit": 30, "remaining": 30, "reset": 1, "used": 0},
            }
        }
    )


class _Result:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class FetchRateLimitTests(unittest.TestCase):
    def test_parses_success(self):
        with mock.patch.object(
            gh_quota.subprocess, "run", return_value=_Result(stdout=_rate_limit_stdout())
        ):
            quotas = gh_quota.fetch_rate_limit()
        self.assertIsNotNone(quotas)
        self.assertEqual(quotas["core"].remaining, 4986)
        self.assertEqual(quotas["graphql"].remaining, 0)
        self.assertEqual(quotas["core"].limit, 5000)

    def test_never_consumes_quota_itself(self):
        """Pins the EXACT command: `gh api rate_limit`, nothing more (module docstring)."""
        with mock.patch.object(
            gh_quota.subprocess, "run", return_value=_Result(stdout=_rate_limit_stdout())
        ) as run:
            gh_quota.fetch_rate_limit()
        args = run.call_args.args[0]
        self.assertEqual(args, ["gh", "api", "rate_limit"])

    def test_nonzero_exit_returns_none(self):
        with mock.patch.object(
            gh_quota.subprocess, "run", return_value=_Result(returncode=1, stderr="boom")
        ):
            self.assertIsNone(gh_quota.fetch_rate_limit())

    def test_malformed_json_returns_none(self):
        with mock.patch.object(gh_quota.subprocess, "run", return_value=_Result(stdout="not json")):
            self.assertIsNone(gh_quota.fetch_rate_limit())

    def test_missing_resources_key_returns_none(self):
        with mock.patch.object(
            gh_quota.subprocess, "run", return_value=_Result(stdout=json.dumps({"foo": 1}))
        ):
            self.assertIsNone(gh_quota.fetch_rate_limit())

    def test_timeout_returns_none_never_raises(self):
        with mock.patch.object(
            gh_quota.subprocess, "run", side_effect=subprocess.TimeoutExpired(cmd="gh", timeout=5)
        ):
            self.assertIsNone(gh_quota.fetch_rate_limit())

    def test_missing_gh_binary_returns_none_never_raises(self):
        with mock.patch.object(gh_quota.subprocess, "run", side_effect=FileNotFoundError("gh")):
            self.assertIsNone(gh_quota.fetch_rate_limit())

    def test_partial_entry_is_skipped_not_fatal(self):
        """A malformed single-resource entry doesn't kill the whole reading."""
        payload = json.dumps(
            {
                "resources": {
                    "core": {"limit": 5000, "remaining": 100, "reset": 1},
                    "graphql": {"limit": "not-a-number"},
                }
            }
        )
        with mock.patch.object(gh_quota.subprocess, "run", return_value=_Result(stdout=payload)):
            quotas = gh_quota.fetch_rate_limit()
        self.assertIsNotNone(quotas)
        self.assertIn("core", quotas)
        self.assertNotIn("graphql", quotas)


class GetQuotaCachingTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(self.enterContext(_tmp_ctx()))
        self.cache_file = self.tmpdir / "cache.json"

    def test_fresh_cache_short_circuits_fetch(self):
        now = time.time()
        gh_quota._write_cache(
            {"graphql": gh_quota.ResourceQuota("graphql", 10, 5000, 999)}, self.cache_file
        )
        with mock.patch.object(gh_quota, "fetch_rate_limit") as fetch:
            result = gh_quota.get_quota(ttl=30, cache_file=self.cache_file, now=now + 5)
        fetch.assert_not_called()
        self.assertEqual(result["graphql"].remaining, 10)

    def test_stale_cache_triggers_exactly_one_refetch(self):
        now = time.time()
        gh_quota._write_cache(
            {"graphql": gh_quota.ResourceQuota("graphql", 10, 5000, 999)}, self.cache_file
        )
        fresh = {"graphql": gh_quota.ResourceQuota("graphql", 4000, 5000, 1999)}
        with mock.patch.object(gh_quota, "fetch_rate_limit", return_value=fresh) as fetch:
            result = gh_quota.get_quota(ttl=30, cache_file=self.cache_file, now=now + 60)
        fetch.assert_called_once()
        self.assertEqual(result["graphql"].remaining, 4000)

    def test_failed_refetch_falls_back_to_stale_cache(self):
        now = time.time()
        gh_quota._write_cache(
            {"graphql": gh_quota.ResourceQuota("graphql", 10, 5000, 999)}, self.cache_file
        )
        with mock.patch.object(gh_quota, "fetch_rate_limit", return_value=None):
            result = gh_quota.get_quota(ttl=30, cache_file=self.cache_file, now=now + 9999)
        self.assertIsNotNone(result, "a stale cache is still better than nothing")
        self.assertEqual(result["graphql"].remaining, 10)

    def test_no_cache_and_failed_fetch_is_unknown(self):
        with mock.patch.object(gh_quota, "fetch_rate_limit", return_value=None):
            result = gh_quota.get_quota(ttl=30, cache_file=self.cache_file)
        self.assertIsNone(result)

    def test_corrupt_cache_file_is_treated_as_absent(self):
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        self.cache_file.write_text("{not valid json", encoding="utf-8")
        fresh = {"graphql": gh_quota.ResourceQuota("graphql", 4000, 5000, 1999)}
        with mock.patch.object(gh_quota, "fetch_rate_limit", return_value=fresh) as fetch:
            result = gh_quota.get_quota(ttl=30, cache_file=self.cache_file)
        fetch.assert_called_once()
        self.assertEqual(result["graphql"].remaining, 4000)

    def test_resource_quota_convenience_returns_single_entry(self):
        gh_quota._write_cache(
            {"graphql": gh_quota.ResourceQuota("graphql", 10, 5000, 999)}, self.cache_file
        )
        q = gh_quota.resource_quota("graphql", ttl=30, cache_file=self.cache_file, now=time.time())
        self.assertEqual(q.remaining, 10)


class GuardDegradeToAllowTests(unittest.TestCase):
    """The load-bearing #1224 design requirement: a quota-check failure never blocks."""

    def test_guard_allows_when_quota_unknown(self):
        with mock.patch.object(gh_quota, "resource_quota", return_value=None):
            rc = gh_quota.main(["guard", "--resource", "graphql", "--min", "50"])
        self.assertEqual(rc, 0, "unknown quota must degrade to ALLOW, never block")

    def test_guard_blocks_below_min(self):
        q = gh_quota.ResourceQuota("graphql", remaining=5, limit=5000, reset_epoch=999)
        with mock.patch.object(gh_quota, "resource_quota", return_value=q):
            rc = gh_quota.main(["guard", "--resource", "graphql", "--min", "50"])
        self.assertEqual(rc, 1)

    def test_guard_allows_above_min(self):
        q = gh_quota.ResourceQuota("graphql", remaining=4000, limit=5000, reset_epoch=999)
        with mock.patch.object(gh_quota, "resource_quota", return_value=q):
            rc = gh_quota.main(["guard", "--resource", "graphql", "--min", "50"])
        self.assertEqual(rc, 0)

    def test_guard_boundary_equal_to_min_allows(self):
        """remaining == min is the ALLOW side (>=, not >) — a mutation-test pin."""
        q = gh_quota.ResourceQuota("graphql", remaining=50, limit=5000, reset_epoch=999)
        with mock.patch.object(gh_quota, "resource_quota", return_value=q):
            rc = gh_quota.main(["guard", "--resource", "graphql", "--min", "50"])
        self.assertEqual(rc, 0)

    def test_guard_boundary_one_below_min_blocks(self):
        q = gh_quota.ResourceQuota("graphql", remaining=49, limit=5000, reset_epoch=999)
        with mock.patch.object(gh_quota, "resource_quota", return_value=q):
            rc = gh_quota.main(["guard", "--resource", "graphql", "--min", "50"])
        self.assertEqual(rc, 1)

    def test_check_command_never_fails_when_quota_unknown(self):
        with mock.patch.object(gh_quota, "get_quota", return_value=None):
            rc = gh_quota.main(["check"])
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
