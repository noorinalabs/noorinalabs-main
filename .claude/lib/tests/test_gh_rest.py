"""Tests for gh_rest.py — REST fallbacks for GraphQL-backed gh surfaces (#1224).

Test names map to the four measured traps in the #1224 brief:

  1. issue_view / issue_list REJECT or FILTER pull requests — the
     `repos/{o}/{r}/issues` endpoint answers for PRs too (57-vs-50 overcount).
  2. Pagination — a >100-item paginated read is not silently truncated
     (`--paginate` + one-JSON-object-per-line parsing across pages).
  3. `project_item_add` / `classic_project_lookup` — the "say so explicitly,
     never fail silently" contract for board operations, PLUS the corrected
     finding that org-owned ProjectV2 item-add DOES have a REST equivalent.
  4. The comment write-then-post two-step split, and why combining them
     defeats `validate_review_comment_format`.

Every subprocess call is mocked — no live network dependency, hermetic and
deterministic regardless of the real GraphQL quota state at CI time.
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gh_rest  # noqa: E402


class _Result:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _issue_payload(number=1224, *, is_pr=False, rest_id=5044008973):
    payload = {
        "number": number,
        "state": "open",
        "title": "some issue",
        "labels": [{"name": "tech-debt"}, {"name": "wave-29"}],
        "closed_at": None,
        "id": rest_id,
        "repository_url": "https://api.github.com/repos/noorinalabs/noorinalabs-main",
    }
    if is_pr:
        payload["pull_request"] = {"url": "https://api.github.com/..."}
    return payload


class RunGhTests(unittest.TestCase):
    def test_run_gh_raises_on_nonzero_exit(self):
        with mock.patch.object(
            gh_rest.subprocess, "run", return_value=_Result(returncode=1, stderr="boom")
        ):
            with self.assertRaises(gh_rest.GhRestError):
                gh_rest._run_gh(["api", "whatever"])

    def test_run_gh_raises_on_timeout_never_silent(self):
        with mock.patch.object(
            gh_rest.subprocess, "run", side_effect=subprocess.TimeoutExpired(cmd="gh", timeout=5)
        ):
            with self.assertRaises(gh_rest.GhRestError):
                gh_rest._run_gh(["api", "whatever"])

    def test_run_gh_raises_on_missing_binary(self):
        with mock.patch.object(gh_rest.subprocess, "run", side_effect=FileNotFoundError("gh")):
            with self.assertRaises(gh_rest.GhRestError):
                gh_rest._run_gh(["api", "whatever"])


# --- Trap 1: `/issues` returns pull requests too ---------------------------


class Trap1PullRequestFilterTests(unittest.TestCase):
    def test_issue_view_rejects_a_pull_request(self):
        with mock.patch.object(
            gh_rest.subprocess,
            "run",
            return_value=_Result(stdout=json.dumps(_issue_payload(1207, is_pr=True))),
        ):
            with self.assertRaises(gh_rest.GhRestError) as ctx:
                gh_rest.issue_view(1207, repo="noorinalabs/noorinalabs-main")
        self.assertIn("pull request", str(ctx.exception))

    def test_issue_view_accepts_a_genuine_issue(self):
        with mock.patch.object(
            gh_rest.subprocess, "run", return_value=_Result(stdout=json.dumps(_issue_payload(1224)))
        ):
            result = gh_rest.issue_view(1224, repo="noorinalabs/noorinalabs-main")
        self.assertEqual(result["number"], 1224)
        self.assertEqual(result["labels"], ["tech-debt", "wave-29"])

    def test_issue_list_jq_filter_excludes_pull_requests(self):
        """Pins the exact jq shape — `.[] | select(.pull_request == null) | ...` —
        so a future edit can't silently drop the filter and reintroduce the
        57-vs-50 overcount (#1224 issue body)."""
        with mock.patch.object(gh_rest.subprocess, "run", return_value=_Result(stdout="")) as run:
            gh_rest.issue_list(repo="noorinalabs/noorinalabs-main")
        args = run.call_args.args[0]
        jq_index = args.index("--jq")
        jq_expr = args[jq_index + 1]
        self.assertIn("select(.pull_request == null)", jq_expr)
        self.assertTrue(jq_expr.startswith(".[] |"), "must flatten the page array with .[] first")

    def test_issue_list_simulated_end_to_end_filters_prs(self):
        """Simulate what real `--jq` output looks like (one compact object per
        line, PRs already filtered server-side by the real jq expression) and
        confirm the Python side parses it without re-introducing the overcount."""
        lines = [
            json.dumps(
                {"number": n, "state": "open", "title": "x", "labels": [], "closed_at": None}
            )
            for n in range(1, 51)  # the TRUE issue count from the #1224 incident
        ]
        with mock.patch.object(
            gh_rest.subprocess, "run", return_value=_Result(stdout="\n".join(lines))
        ):
            result = gh_rest.issue_list(repo="noorinalabs/noorinalabs-main")
        self.assertEqual(len(result), 50, "must read 50, not the PR-inflated 57")


# --- Trap 2: pagination — a >100-item result must not truncate -------------


class Trap2PaginationTests(unittest.TestCase):
    def test_paginate_flag_is_always_passed(self):
        with mock.patch.object(gh_rest.subprocess, "run", return_value=_Result(stdout="")) as run:
            gh_rest.issue_list(repo="noorinalabs/noorinalabs-main")
        args = run.call_args.args[0]
        self.assertIn("--paginate", args)

    def test_more_than_100_items_are_not_truncated(self):
        """Simulates 3 concatenated pages (gh's real --paginate behavior) totalling
        250 items — the item-list --limit-truncation sibling trap."""
        lines = [
            json.dumps(
                {
                    "itemId": i,
                    "contentType": "Issue",
                    "number": i,
                    "title": "x",
                    "repository": "o/r",
                }
            )
            for i in range(250)
        ]
        with mock.patch.object(
            gh_rest.subprocess, "run", return_value=_Result(stdout="\n".join(lines))
        ):
            result = gh_rest.project_items("noorinalabs", 2)
        self.assertEqual(len(result), 250, "a >100-item paginated read must not be truncated")

    def test_paginate_parse_failure_raises_not_silently_empty(self):
        """An unparseable line must raise, not resolve to a quietly-short list —
        the module's own § Never masks a real failure as an empty result."""
        with mock.patch.object(
            gh_rest.subprocess, "run", return_value=_Result(stdout="{valid}\nnot json at all")
        ):
            with self.assertRaises(gh_rest.GhRestError):
                gh_rest.project_items("noorinalabs", 2)

    def test_paginate_nonzero_exit_raises_not_empty_list(self):
        with mock.patch.object(
            gh_rest.subprocess, "run", return_value=_Result(returncode=1, stderr="rate limit")
        ):
            with self.assertRaises(gh_rest.GhRestError):
                gh_rest.issue_list(repo="noorinalabs/noorinalabs-main")

    def test_empty_but_successful_result_is_a_legitimate_empty_list(self):
        with mock.patch.object(
            gh_rest.subprocess, "run", return_value=_Result(returncode=0, stdout="")
        ):
            result = gh_rest.issue_list(repo="noorinalabs/noorinalabs-main")
        self.assertEqual(result, [])


# --- Trap 3: project board operations ---------------------------------------


class Trap3ProjectBoardTests(unittest.TestCase):
    def test_project_item_add_resolves_database_id_and_posts(self):
        """`id` in the POST payload must be the REST database id (5044008973),
        NEVER the issue `number` (1224) or the GraphQL node_id — a silent mixup
        here would add the wrong content to the board."""
        lookup = _Result(stdout=json.dumps(_issue_payload(1224, rest_id=5044008973)))
        post = _Result(
            stdout=json.dumps(
                {"id": 222265230, "content_type": "Issue", "content": {"number": 1224}}
            )
        )
        with mock.patch.object(gh_rest.subprocess, "run", side_effect=[lookup, post]) as run:
            result = gh_rest.project_item_add(
                2, "noorinalabs", 1224, repo="noorinalabs/noorinalabs-main"
            )
        self.assertEqual(result["itemId"], 222265230)
        post_call = run.call_args_list[1]
        self.assertEqual(
            post_call.kwargs.get("input"), json.dumps({"type": "Issue", "id": 5044008973})
        )

    def test_project_item_add_infers_pull_request_type(self):
        lookup = _Result(stdout=json.dumps(_issue_payload(1207, is_pr=True, rest_id=999)))
        post = _Result(
            stdout=json.dumps({"id": 1, "content_type": "PullRequest", "content": {"number": 1207}})
        )
        with mock.patch.object(gh_rest.subprocess, "run", side_effect=[lookup, post]) as run:
            gh_rest.project_item_add(2, "noorinalabs", 1207, repo="noorinalabs/noorinalabs-main")
        post_call = run.call_args_list[1]
        self.assertEqual(json.loads(post_call.kwargs["input"])["type"], "PullRequest")

    def test_project_item_add_raises_not_silent_on_post_failure(self):
        lookup = _Result(stdout=json.dumps(_issue_payload(1224)))
        post = _Result(returncode=1, stderr="422 Invalid request")
        with mock.patch.object(gh_rest.subprocess, "run", side_effect=[lookup, post]):
            with self.assertRaises(gh_rest.GhRestError):
                gh_rest.project_item_add(
                    2, "noorinalabs", 1224, repo="noorinalabs/noorinalabs-main"
                )

    def test_classic_project_lookup_says_so_explicitly(self):
        """The one operation that IS genuinely unsupported must raise a clear,
        typed error — never fail silently (module docstring's explicit
        requirement, and the #1224 brief's trap 3)."""
        with self.assertRaises(gh_rest.GhRestUnsupportedError) as ctx:
            gh_rest.classic_project_lookup("noorinalabs")
        self.assertIn("removed", str(ctx.exception))

    def test_classic_project_lookup_is_a_ghrest_error_subclass(self):
        """So a generic `except GhRestError` still catches it — callers that
        haven't special-cased "unsupported" still fail loudly, not silently."""
        self.assertTrue(issubclass(gh_rest.GhRestUnsupportedError, gh_rest.GhRestError))

    def test_issue_project_membership_filters_by_repo_not_number_alone(self):
        """Cross-repo number collision (feedback_gh_cli_gotchas §3) — an item
        with a matching number in the WRONG repo must not read as a match."""
        items_stdout = "\n".join(
            [
                json.dumps(
                    {
                        "itemId": 1,
                        "contentType": "Issue",
                        "number": 1224,
                        "title": "wrong repo",
                        "repository": "noorinalabs/noorinalabs-deploy",
                    }
                ),
                json.dumps(
                    {
                        "itemId": 2,
                        "contentType": "Issue",
                        "number": 1224,
                        "title": "right repo",
                        "repository": "noorinalabs/noorinalabs-main",
                    }
                ),
            ]
        )
        with mock.patch.object(
            gh_rest.subprocess, "run", return_value=_Result(stdout=items_stdout)
        ):
            result = gh_rest.issue_project_membership(
                1224, "noorinalabs", 2, repo="noorinalabs/noorinalabs-main"
            )
        self.assertIsNotNone(result)
        self.assertEqual(result["itemId"], 2)


# --- Trap 4: comment write-then-post two-step -------------------------------


class Trap4CommentTwoStepTests(unittest.TestCase):
    def test_post_comment_raises_if_payload_missing(self):
        """The exact shape `validate_review_comment_format` guards against:
        posting before the payload file exists. Must raise a clear GhRestError,
        not a bare FileNotFoundError, and must NOT attempt the gh call at all."""
        with mock.patch.object(gh_rest.subprocess, "run") as run:
            with self.assertRaises(gh_rest.GhRestError) as ctx:
                gh_rest.post_comment(
                    1224, "/nonexistent/payload.json", repo="noorinalabs/noorinalabs-main"
                )
        run.assert_not_called()
        self.assertIn("EARLIER, separate", str(ctx.exception))

    def test_write_then_post_succeeds_as_two_steps(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            payload_path = Path(tmpdir) / "comment.json"
            gh_rest.write_comment_payload(payload_path, "hello world")
            self.assertTrue(
                payload_path.is_file(), "payload must exist after step 1, before step 2 runs"
            )

            written = json.loads(payload_path.read_text(encoding="utf-8"))
            self.assertEqual(written["body"], "hello world")

            with mock.patch.object(
                gh_rest.subprocess,
                "run",
                return_value=_Result(
                    stdout=json.dumps({"id": 1, "body": "hello world", "created_at": "now"})
                ),
            ) as run:
                result = gh_rest.post_comment(
                    1224, payload_path, repo="noorinalabs/noorinalabs-main"
                )
            self.assertEqual(result["id"], 1)
            args = run.call_args.args[0]
            self.assertIn("--input", args)
            self.assertEqual(args[args.index("--input") + 1], str(payload_path))

    def test_write_comment_payload_is_utf8_not_ascii_escaped(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            payload_path = Path(tmpdir) / "comment.json"
            gh_rest.write_comment_payload(payload_path, "نص عربي")
            raw = payload_path.read_bytes()
            self.assertNotIn(b"\\u", raw, "body must round-trip as UTF-8, not \\uXXXX escapes")


# --- pr_view / pr_check_runs / pr_list shape parity -------------------------


class PrShapeTests(unittest.TestCase):
    def test_pr_view_shape(self):
        payload = {
            "number": 1207,
            "state": "closed",
            "head": {"sha": "abc123", "ref": "feature-branch"},
            "base": {"ref": "main"},
            "merged_at": "2026-08-01T19:29:29Z",
            "merge_commit_sha": "def456",
        }
        with mock.patch.object(
            gh_rest.subprocess, "run", return_value=_Result(stdout=json.dumps(payload))
        ):
            result = gh_rest.pr_view(1207, repo="noorinalabs/noorinalabs-main")
        self.assertEqual(result["headRefOid"], "abc123")
        self.assertEqual(result["headRefName"], "feature-branch")
        self.assertEqual(result["baseRefName"], "main")

    def test_pr_check_runs_uses_check_runs_endpoint_not_legacy_status(self):
        """feedback_gh_cli_gotchas §13: check-runs is authoritative, status is not."""
        with mock.patch.object(gh_rest.subprocess, "run", return_value=_Result(stdout="")) as run:
            gh_rest.pr_check_runs("abc123", repo="noorinalabs/noorinalabs-main")
        args = run.call_args.args[0]
        self.assertIn("commits/abc123/check-runs", args[2])
        self.assertNotIn("status", args[2])

    def test_pr_list_does_not_need_the_pull_request_filter(self):
        with mock.patch.object(gh_rest.subprocess, "run", return_value=_Result(stdout="")) as run:
            gh_rest.pr_list(repo="noorinalabs/noorinalabs-main")
        args = run.call_args.args[0]
        jq_expr = args[args.index("--jq") + 1]
        self.assertNotIn("pull_request", jq_expr, "the /pulls endpoint never mixes in issues")


if __name__ == "__main__":
    unittest.main()
