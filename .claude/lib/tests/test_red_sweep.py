#!/usr/bin/env python3
"""Tests for red_sweep.py — the scheduled red default-branch sweep (main#962).

Covers the semantics carried over from /session-start Step 5a:
class-name filtering, latest-run-per-workflow selection, red-conclusion
detection, base-image-drift classification with degradation to code/other,
fetch-failure -> UNKNOWN (never false green), and the reader's 24h staleness
guard (missing/stale verdict -> WARNING, never all-green).

Run from the repo root:
    ENVIRONMENT=test python3 -m pytest .claude/lib/tests/test_red_sweep.py -v
"""

from __future__ import annotations

import base64
import json
import subprocess
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

import red_sweep  # noqa: E402

_NOW = datetime(2026, 7, 13, 12, 0, 0, tzinfo=timezone.utc)


def _run(name: str, *, wid: int, conclusion: str, started: str, run_id: int = 1) -> dict:
    return {
        "name": name,
        "display_title": name,
        "workflow_id": wid,
        "conclusion": conclusion,
        "run_started_at": started,
        "id": run_id,
        "html_url": f"https://github.com/noorinalabs/x/actions/runs/{run_id}",
    }


class FakeGh:
    """Injected runner: maps (kind of call) -> canned output or raises."""

    def __init__(
        self,
        runs_by_repo: dict[str, object] | None = None,
        logs_by_run: dict[str, object] | None = None,
        default_branch: str = "main",
    ) -> None:
        self.runs_by_repo = runs_by_repo or {}
        self.logs_by_run = logs_by_run or {}
        self.default_branch = default_branch
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str]) -> str:
        self.calls.append(args)
        joined = " ".join(args)
        if args[0] == "api" and args[-1] == ".default_branch":
            return self.default_branch + "\n"
        if args[0] == "api" and "/actions/runs?" in joined:
            repo = args[1].split("/")[2].split("?")[0]
            result = self.runs_by_repo.get(repo)
            if isinstance(result, Exception):
                raise result
            return json.dumps({"workflow_runs": result or []})
        if args[0] == "run" and args[1] == "view":
            result = self.logs_by_run.get(args[2])
            if isinstance(result, Exception):
                raise result
            return str(result or "")
        raise AssertionError(f"unexpected gh call: {args}")


def _gh_error() -> subprocess.CalledProcessError:
    return subprocess.CalledProcessError(1, ["gh"])


class LatestClassRunsTests(unittest.TestCase):
    def test_filters_to_publish_deploy_release_class(self) -> None:
        payload = {
            "workflow_runs": [
                _run("CI — Hooks & Scripts", wid=1, conclusion="failure", started="2026-07-13"),
                _run("Publish frontend (GHCR)", wid=2, conclusion="success", started="2026-07-13"),
                _run("Deploy staging", wid=3, conclusion="failure", started="2026-07-13"),
            ]
        }
        names = {r["name"] for r in red_sweep.latest_class_runs(payload)}
        self.assertEqual(names, {"Publish frontend (GHCR)", "Deploy staging"})

    def test_keeps_only_latest_run_per_workflow(self) -> None:
        payload = {
            "workflow_runs": [
                _run("Deploy", wid=7, conclusion="failure", started="2026-07-10T00:00:00Z"),
                _run("Deploy", wid=7, conclusion="success", started="2026-07-13T00:00:00Z"),
            ]
        }
        (latest,) = red_sweep.latest_class_runs(payload)
        self.assertEqual(latest["conclusion"], "success")


class ClassifyTests(unittest.TestCase):
    def test_base_image_signal(self) -> None:
        self.assertEqual(
            red_sweep.classify_log("Total: 3 (HIGH: 2)\ntrivy image scan failed"),
            "base-image-drift",
        )
        self.assertEqual(
            red_sweep.classify_log("openssl 3.0.1 has a known CVE advisory"),
            "base-image-drift",
        )

    def test_plain_failure_is_code_other(self) -> None:
        self.assertEqual(red_sweep.classify_log("npm ERR! build failed"), "code/other")

    def test_missing_log_degrades_to_code_other_not_green(self) -> None:
        self.assertEqual(red_sweep.classify_log(None), "code/other")


class SweepTests(unittest.TestCase):
    def test_red_latest_run_is_reported_with_class(self) -> None:
        gh = FakeGh(
            runs_by_repo={
                "repo-a": [
                    _run(
                        "Publish image",
                        wid=1,
                        conclusion="failure",
                        started="2026-07-13T00:00:00Z",
                        run_id=42,
                    )
                ]
            },
            logs_by_run={"42": "trivy found CVE-2026-45447 in base image"},
        )
        verdict = red_sweep.sweep(("repo-a",), run_gh=gh, now=_NOW)
        self.assertEqual(verdict["repos_checked"], ["repo-a"])
        self.assertEqual(verdict["errors"], [])
        (red,) = verdict["red"]
        self.assertEqual(red["repo"], "repo-a")
        self.assertEqual(red["conclusion"], "failure")
        self.assertEqual(red["class"], "base-image-drift")

    def test_green_latest_run_masks_older_red(self) -> None:
        gh = FakeGh(
            runs_by_repo={
                "repo-a": [
                    _run("Deploy", wid=1, conclusion="failure", started="2026-07-01T00:00:00Z"),
                    _run("Deploy", wid=1, conclusion="success", started="2026-07-13T00:00:00Z"),
                ]
            }
        )
        verdict = red_sweep.sweep(("repo-a",), run_gh=gh, now=_NOW)
        self.assertEqual(verdict["red"], [])

    def test_fetch_failure_lands_in_errors_not_green(self) -> None:
        gh = FakeGh(runs_by_repo={"repo-a": _gh_error(), "repo-b": []})
        verdict = red_sweep.sweep(("repo-a", "repo-b"), run_gh=gh, now=_NOW)
        self.assertEqual(verdict["errors"], ["repo-a"])
        self.assertEqual(verdict["repos_checked"], ["repo-b"])

    def test_log_fetch_failure_degrades_class_to_code_other(self) -> None:
        gh = FakeGh(
            runs_by_repo={
                "repo-a": [
                    _run(
                        "Release",
                        wid=1,
                        conclusion="timed_out",
                        started="2026-07-13T00:00:00Z",
                        run_id=9,
                    )
                ]
            },
            logs_by_run={"9": _gh_error()},
        )
        verdict = red_sweep.sweep(("repo-a",), run_gh=gh, now=_NOW)
        self.assertEqual(verdict["red"][0]["class"], "code/other")

    def test_verdict_carries_checked_at(self) -> None:
        gh = FakeGh(runs_by_repo={"repo-a": []})
        verdict = red_sweep.sweep(("repo-a",), run_gh=gh, now=_NOW)
        self.assertEqual(verdict["checked_at"], "2026-07-13T12:00:00Z")


class ReadVerdictTests(unittest.TestCase):
    def test_round_trip_base64_content(self) -> None:
        verdict = {"version": 1, "checked_at": "2026-07-13T06:00:00Z", "red": []}
        encoded = base64.b64encode(json.dumps(verdict).encode()).decode()
        # The contents API returns base64 with embedded newlines — must decode.
        wrapped = "\n".join(encoded[i : i + 60] for i in range(0, len(encoded), 60))

        def gh(args: list[str]) -> str:
            self.assertIn(red_sweep.META_REF, " ".join(args))
            return wrapped

        self.assertEqual(red_sweep.read_verdict(run_gh=gh), verdict)

    def test_missing_ref_returns_none(self) -> None:
        def gh(args: list[str]) -> str:
            raise _gh_error()

        self.assertIsNone(red_sweep.read_verdict(run_gh=gh))

    def test_corrupt_content_returns_none(self) -> None:
        self.assertIsNone(red_sweep.read_verdict(run_gh=lambda a: "not-base64-json!"))


class RenderCheckTests(unittest.TestCase):
    def _fresh(self, **overrides: object) -> dict:
        verdict: dict = {
            "version": 1,
            "checked_at": red_sweep._iso(_NOW - timedelta(hours=3)),
            "repos_checked": ["repo-a"],
            "errors": [],
            "red": [],
        }
        verdict.update(overrides)
        return verdict

    def test_missing_verdict_is_warning_never_green(self) -> None:
        out = red_sweep.render_check(None, now=_NOW)
        self.assertIn("WARNING", out)
        self.assertIn("UNKNOWN", out)
        self.assertNotIn("green", out.split("do NOT assume green")[0])

    def test_stale_verdict_is_warning_never_green(self) -> None:
        stale = self._fresh(checked_at=red_sweep._iso(_NOW - timedelta(hours=30)))
        out = red_sweep.render_check(stale, now=_NOW)
        self.assertIn("WARNING", out)
        self.assertIn("STALE", out)
        self.assertNotIn("All publish/deploy/release workflows green", out)

    def test_unparseable_timestamp_is_warning(self) -> None:
        out = red_sweep.render_check(self._fresh(checked_at="garbage"), now=_NOW)
        self.assertIn("WARNING", out)
        self.assertIn("STALE", out)

    def test_fresh_green_reports_all_green_with_timestamp(self) -> None:
        verdict = self._fresh()
        out = red_sweep.render_check(verdict, now=_NOW)
        self.assertIn("All publish/deploy/release workflows green", out)
        self.assertIn(verdict["checked_at"], out)

    def test_fresh_red_lists_runs_and_drift_note(self) -> None:
        verdict = self._fresh(
            red=[
                {
                    "repo": "repo-a",
                    "workflow": "Publish image",
                    "conclusion": "failure",
                    "class": "base-image-drift",
                    "url": "https://example.test/run/1",
                }
            ]
        )
        out = red_sweep.render_check(verdict, now=_NOW)
        self.assertIn("RED default-branch publish/deploy run(s)", out)
        self.assertIn("repo-a :: Publish image :: failure :: base-image-drift", out)
        self.assertIn("fix-forward the base image", out)

    def test_sweep_fetch_errors_reported_unknown_not_green(self) -> None:
        out = red_sweep.render_check(self._fresh(errors=["repo-b"]), now=_NOW)
        self.assertIn("repo-b", out)
        self.assertIn("UNKNOWN, not green", out)


class VerdictAgeTests(unittest.TestCase):
    def test_age_hours(self) -> None:
        verdict = {"checked_at": red_sweep._iso(_NOW - timedelta(hours=6))}
        age = red_sweep.verdict_age_hours(verdict, now=_NOW)
        assert age is not None
        self.assertAlmostEqual(age, 6.0, places=3)

    def test_unparseable_returns_none(self) -> None:
        self.assertIsNone(red_sweep.verdict_age_hours({"checked_at": "nope"}, now=_NOW))


if __name__ == "__main__":
    unittest.main()
