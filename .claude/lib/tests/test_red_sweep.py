#!/usr/bin/env python3
"""Tests for red_sweep.py — the scheduled red default-branch sweep (main#962).

Covers the semantics carried over from /session-start Step 5a:
latest-run-per-workflow selection, red-conclusion detection, base-image-drift
classification with degradation to code/other, fetch-failure -> UNKNOWN (never
false green), and the reader's 24h staleness guard (missing/stale verdict ->
WARNING, never all-green).

Plus the main#1584 scope contract, which replaced the workflow-NAME substring
filter with a trigger-based predicate. `ScopePredicateTests` is the part that
distinguishes a real fix from adding `e2e` to the old regex: its cases assert
behaviour for workflows whose names match NONE of
`publish|deploy|release|promote|ghcr|image`, so no widening of that regex can
make them pass.

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


def _run(
    name: str,
    *,
    wid: int,
    conclusion: str,
    started: str,
    run_id: int = 1,
    path: str = "",
) -> dict:
    """A workflow_run payload entry. ``path`` is the field the sweep uses to
    read the workflow file's triggers; the default "" means "no file to read",
    which the sweep must degrade to UNKNOWN-triggers, not to a drop."""
    return {
        "name": name,
        "display_title": name,
        "workflow_id": wid,
        "conclusion": conclusion,
        "run_started_at": started,
        "id": run_id,
        "path": path,
        "html_url": f"https://github.com/noorinalabs/x/actions/runs/{run_id}",
    }


#: Workflow files whose `on:` block the scope tests feed to the sweep. None of
#: these names contains a publish/deploy/release-class substring.
_CRON_WF = 'name: e2e-stg-smoke\non:\n  schedule:\n    - cron: "17 6 * * *"\njobs: {}\n'
_PR_LINT_WF = "name: lint\non:\n  pull_request:\n  push:\n    branches: [main]\njobs: {}\n"
_DISPATCH_WF = "name: rollback\non:\n  workflow_dispatch:\njobs: {}\n"


class FakeGh:
    """Injected runner: maps (kind of call) -> canned output or raises."""

    def __init__(
        self,
        runs_by_repo: dict[str, object] | None = None,
        logs_by_run: dict[str, object] | None = None,
        default_branch: str = "main",
        workflow_files: dict[str, object] | None = None,
    ) -> None:
        self.runs_by_repo = runs_by_repo or {}
        self.logs_by_run = logs_by_run or {}
        self.default_branch = default_branch
        # path -> workflow YAML text, or an Exception to raise (a 404 for a
        # workflow file deleted since its last run, say). A path that is not
        # registered raises too: an unregistered file is "could not be read",
        # which the sweep must degrade to in-scope, never to a silent drop.
        self.workflow_files = workflow_files or {}
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str]) -> str:
        self.calls.append(args)
        joined = " ".join(args)
        if args[0] == "api" and args[-1] == ".default_branch":
            return self.default_branch + "\n"
        if args[0] == "api" and "/contents/" in joined:
            path = args[1].split("/contents/", 1)[1].split("?")[0]
            result = self.workflow_files.get(path)
            if isinstance(result, Exception):
                raise result
            if result is None:
                raise _gh_error()
            return base64.b64encode(str(result).encode()).decode()
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


class LatestRunsByWorkflowTests(unittest.TestCase):
    def test_does_not_filter_by_name(self) -> None:
        """main#1584: the grouping step must discard NOTHING.

        The predecessor `latest_class_runs` dropped any workflow whose name
        missed a six-substring regex, before anything could classify it. Scope
        now lives in `run_scope`, applied per run, so a non-matching name must
        survive this step.
        """
        payload = {
            "workflow_runs": [
                _run("CI — Hooks & Scripts", wid=1, conclusion="failure", started="2026-07-13"),
                _run("Publish frontend (GHCR)", wid=2, conclusion="success", started="2026-07-13"),
                _run("e2e-stg-smoke", wid=3, conclusion="failure", started="2026-07-13"),
            ]
        }
        names = {r["name"] for r in red_sweep.latest_runs_by_workflow(payload)}
        self.assertEqual(
            names, {"CI — Hooks & Scripts", "Publish frontend (GHCR)", "e2e-stg-smoke"}
        )

    def test_keeps_only_latest_run_per_workflow(self) -> None:
        payload = {
            "workflow_runs": [
                _run("Deploy", wid=7, conclusion="failure", started="2026-07-10T00:00:00Z"),
                _run("Deploy", wid=7, conclusion="success", started="2026-07-13T00:00:00Z"),
            ]
        }
        (latest,) = red_sweep.latest_runs_by_workflow(payload)
        self.assertEqual(latest["conclusion"], "success")


class ParseWorkflowTriggersTests(unittest.TestCase):
    def test_yaml_1_1_resolves_bare_on_to_boolean_true(self) -> None:
        """The single most common way a workflow parser reads zero triggers.

        PyYAML follows YAML 1.1, so the key of a bare `on:` is the BOOLEAN
        True. A parser that reads only doc["on"] finds nothing for essentially
        every real workflow file and would make everything look trigger-less.
        """
        self.assertEqual(red_sweep.parse_workflow_triggers(_CRON_WF), frozenset({"schedule"}))

    def test_quoted_on_key(self) -> None:
        text = 'name: x\n"on":\n  schedule:\n    - cron: "0 0 * * *"\n'
        self.assertEqual(red_sweep.parse_workflow_triggers(text), frozenset({"schedule"}))

    def test_scalar_and_list_forms(self) -> None:
        self.assertEqual(red_sweep.parse_workflow_triggers("on: push\n"), frozenset({"push"}))
        self.assertEqual(
            red_sweep.parse_workflow_triggers("on: [push, pull_request]\n"),
            frozenset({"push", "pull_request"}),
        )

    def test_unreadable_inputs_are_none_not_empty(self) -> None:
        """None means UNKNOWN. An empty set would read as "declares nothing",
        which `run_scope` would treat as dispatch-only and sweep in for the
        wrong reason."""
        for text in (None, "", "::: not yaml [", "name: x\njobs: {}\n", "just a string"):
            self.assertIsNone(red_sweep.parse_workflow_triggers(text), repr(text))


class ScopePredicateTests(unittest.TestCase):
    """The main#1584 contract, at the unit level.

    Every workflow name here matches NONE of
    `publish|deploy|release|promote|ghcr|image`, so widening that regex cannot
    make these pass.
    """

    def test_schedule_triggered_non_matching_name_is_in_scope(self) -> None:
        scope = red_sweep.run_scope("e2e-stg-smoke", frozenset({"schedule", "workflow_dispatch"}))
        self.assertEqual(scope, red_sweep.SCOPE_SCHEDULE)

    def test_dispatch_only_non_matching_name_is_in_scope(self) -> None:
        self.assertEqual(
            red_sweep.run_scope("rollback", frozenset({"workflow_dispatch"})),
            red_sweep.SCOPE_DISPATCH_ONLY,
        )

    def test_pull_request_lint_is_out_of_scope(self) -> None:
        """The noise guard the original name filter existed for."""
        self.assertIsNone(red_sweep.run_scope("lint", frozenset({"pull_request", "push"})))
        self.assertIsNone(red_sweep.run_scope("CI — Hooks & Scripts", frozenset({"pull_request"})))

    def test_unreadable_triggers_degrade_to_in_scope(self) -> None:
        self.assertEqual(
            red_sweep.run_scope("branch-protection-audit", None), red_sweep.SCOPE_UNREADABLE
        )

    def test_name_class_union_term_survives(self) -> None:
        """A push-triggered publish keeps its coverage without a trigger read."""
        self.assertEqual(
            red_sweep.run_scope("Publish to GHCR", frozenset({"push"})),
            red_sweep.SCOPE_NAME_CLASS,
        )
        self.assertEqual(red_sweep.run_scope("Deploy staging", None), red_sweep.SCOPE_NAME_CLASS)

    def test_trigger_terms_outrank_the_name_term(self) -> None:
        """A cron that also matches by name reports WHY it is watched — the
        schedule — not the incidental name match."""
        self.assertEqual(
            red_sweep.run_scope("Deploy staging", frozenset({"schedule"})),
            red_sweep.SCOPE_SCHEDULE,
        )


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

    def test_schedule_triggered_non_matching_name_is_swept(self) -> None:
        """THE main#1584 acceptance test — end to end, through `sweep()`.

        `e2e-stg-smoke` matches none of `publish|deploy|release|promote|ghcr|
        image`. Against the pre-#1584 module this assertion fails with
        `verdict["red"] == []`: the workflow was discarded by name inside
        `latest_class_runs` before any classification ran, which is exactly how
        the live sweep reported "All publish/deploy/release workflows green"
        while this workflow had failed 63 of its last 64 default-branch runs.
        A patch that only adds `e2e` to the regex leaves that contract broken
        and is caught by `ScopePredicateTests` above.
        """
        gh = FakeGh(
            runs_by_repo={
                "noorinalabs-isnad-graph": [
                    _run(
                        "e2e-stg-smoke",
                        wid=1,
                        conclusion="failure",
                        started="2026-09-13T06:17:00Z",
                        run_id=77,
                        path=".github/workflows/e2e-stg-smoke.yml",
                    )
                ]
            },
            logs_by_run={"77": "smoke assertion failed: /narrators returned 500"},
            workflow_files={".github/workflows/e2e-stg-smoke.yml": _CRON_WF},
        )
        verdict = red_sweep.sweep(("noorinalabs-isnad-graph",), run_gh=gh, now=_NOW)
        (red,) = verdict["red"]
        self.assertEqual(red["workflow"], "e2e-stg-smoke")
        self.assertEqual(red["scope"], red_sweep.SCOPE_SCHEDULE)
        self.assertEqual(red["conclusion"], "failure")
        # And it was swept for the right reason, not by a widened name regex.
        self.assertFalse(red_sweep._WORKFLOW_CLASS_RE.search("e2e-stg-smoke"))

    def test_pull_request_lint_workflow_is_not_swept(self) -> None:
        """The noise guard: a red lint is loud at PR time, so it stays out."""
        gh = FakeGh(
            runs_by_repo={
                "repo-a": [
                    _run(
                        "lint",
                        wid=1,
                        conclusion="failure",
                        started="2026-07-13T00:00:00Z",
                        path=".github/workflows/lint.yml",
                    )
                ]
            },
            workflow_files={".github/workflows/lint.yml": _PR_LINT_WF},
        )
        verdict = red_sweep.sweep(("repo-a",), run_gh=gh, now=_NOW)
        self.assertEqual(verdict["red"], [])
        self.assertEqual(verdict["workflows_seen"], 1)

    def test_unreadable_triggers_sweep_in_unclassified_never_dropped(self) -> None:
        """A workflow file that 404s (deleted since its last run, say) must not
        vanish from the sweep. Degradation is toward noise, never toward a
        silent drop — the drop IS the main#1584 defect."""
        gh = FakeGh(
            runs_by_repo={
                "repo-a": [
                    _run(
                        "branch-protection-audit",
                        wid=1,
                        conclusion="failure",
                        started="2026-07-13T00:00:00Z",
                        run_id=5,
                        path=".github/workflows/branch-protection-audit.yml",
                    )
                ]
            },
            logs_by_run={"5": "boom"},
            workflow_files={},  # unregistered -> the fetch raises
        )
        verdict = red_sweep.sweep(("repo-a",), run_gh=gh, now=_NOW)
        (red,) = verdict["red"]
        self.assertEqual(red["scope"], red_sweep.SCOPE_UNREADABLE)

    def test_dispatch_only_workflow_is_swept(self) -> None:
        gh = FakeGh(
            runs_by_repo={
                "repo-a": [
                    _run(
                        "rollback",
                        wid=1,
                        conclusion="failure",
                        started="2026-07-13T00:00:00Z",
                        run_id=3,
                        path=".github/workflows/rollback.yml",
                    )
                ]
            },
            logs_by_run={"3": "boom"},
            workflow_files={".github/workflows/rollback.yml": _DISPATCH_WF},
        )
        verdict = red_sweep.sweep(("repo-a",), run_gh=gh, now=_NOW)
        self.assertEqual(verdict["red"][0]["scope"], red_sweep.SCOPE_DISPATCH_ONLY)

    def test_triggers_are_read_once_per_workflow(self) -> None:
        """Two red runs of the same workflow cost one contents call, not two."""
        gh = FakeGh(
            runs_by_repo={
                "repo-a": [
                    _run(
                        "e2e-stg-smoke",
                        wid=1,
                        conclusion="failure",
                        started="2026-07-12T00:00:00Z",
                        path=".github/workflows/e2e-stg-smoke.yml",
                    ),
                    _run(
                        "e2e-stg-smoke",
                        wid=1,
                        conclusion="failure",
                        started="2026-07-13T00:00:00Z",
                        path=".github/workflows/e2e-stg-smoke.yml",
                    ),
                ]
            },
            logs_by_run={"1": "boom"},
            workflow_files={".github/workflows/e2e-stg-smoke.yml": _CRON_WF},
        )
        red_sweep.sweep(("repo-a",), run_gh=gh, now=_NOW)
        contents_calls = [c for c in gh.calls if "/contents/" in " ".join(c)]
        self.assertEqual(len(contents_calls), 1)

    def test_green_workflow_costs_no_trigger_read(self) -> None:
        """Scope is resolved only for red runs — a green one needs no call."""
        gh = FakeGh(
            runs_by_repo={
                "repo-a": [
                    _run(
                        "e2e-stg-smoke",
                        wid=1,
                        conclusion="success",
                        started="2026-07-13T00:00:00Z",
                        path=".github/workflows/e2e-stg-smoke.yml",
                    )
                ]
            },
            workflow_files={".github/workflows/e2e-stg-smoke.yml": _CRON_WF},
        )
        red_sweep.sweep(("repo-a",), run_gh=gh, now=_NOW)
        self.assertEqual([c for c in gh.calls if "/contents/" in " ".join(c)], [])

    def test_workflows_seen_counts_every_workflow_not_just_in_scope(self) -> None:
        gh = FakeGh(
            runs_by_repo={
                "repo-a": [
                    _run("lint", wid=1, conclusion="success", started="2026-07-13T00:00:00Z"),
                    _run("CI", wid=2, conclusion="success", started="2026-07-13T00:00:00Z"),
                ]
            }
        )
        verdict = red_sweep.sweep(("repo-a",), run_gh=gh, now=_NOW)
        self.assertEqual(verdict["workflows_seen"], 2)

    def test_verdict_version_is_2(self) -> None:
        gh = FakeGh(runs_by_repo={"repo-a": []})
        self.assertEqual(red_sweep.sweep(("repo-a",), run_gh=gh, now=_NOW)["version"], 2)

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
            "version": 2,
            "checked_at": red_sweep._iso(_NOW - timedelta(hours=3)),
            "repos_checked": ["repo-a"],
            "errors": [],
            "workflows_seen": 4,
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
        self.assertNotIn("All in-scope default-branch workflows green", out)

    def test_unparseable_timestamp_is_warning(self) -> None:
        out = red_sweep.render_check(self._fresh(checked_at="garbage"), now=_NOW)
        self.assertIn("WARNING", out)
        self.assertIn("STALE", out)

    def test_fresh_green_reports_all_green_with_timestamp(self) -> None:
        verdict = self._fresh(workflows_seen=12)
        out = red_sweep.render_check(verdict, now=_NOW)
        self.assertIn("All in-scope default-branch workflows green", out)
        self.assertIn(verdict["checked_at"], out)

    def test_green_line_states_the_scope_it_is_green_over(self) -> None:
        """main#1584: the old line read "All publish/deploy/release workflows
        green on default branches" — true, and useless, because the scope it
        was green over excluded the red things. A green claim has to say what
        it covers and how much it looked at."""
        out = red_sweep.render_check(self._fresh(workflows_seen=12), now=_NOW)
        self.assertIn("schedule-triggered", out)
        self.assertIn("workflow_dispatch-only", out)
        self.assertIn("publish/deploy/release-class", out)
        self.assertIn("12 workflow(s) examined", out)

    def test_version_1_green_is_not_described_with_the_new_scope(self) -> None:
        """A version-1 verdict was swept by the pre-#1584 name-only predicate.

        Describing it with the trigger-based scope would reproduce the exact
        over-claim this story fixed, one schema version later — during the
        up-to-6h window between the code landing and the next cron run
        overwriting the persisted ref.
        """
        out = red_sweep.render_check(self._fresh(version=1), now=_NOW)
        self.assertNotIn("All in-scope default-branch workflows green", out)
        self.assertIn("NAME-class", out)
        self.assertIn("schedule-only workflows were NOT checked", out)
        self.assertIn("UNKNOWN, not green", out)

    def test_missing_version_is_treated_as_1(self) -> None:
        verdict = self._fresh()
        del verdict["version"]
        self.assertIn("NAME-class", red_sweep.render_check(verdict, now=_NOW))

    def test_zero_repos_checked_is_warning_not_green(self) -> None:
        """A sweep that fetched nothing is UNKNOWN. Without this the empty
        verdict renders as the all-green line."""
        out = red_sweep.render_check(self._fresh(repos_checked=[]), now=_NOW)
        self.assertIn("WARNING", out)
        self.assertIn("ZERO repos", out)
        self.assertIn("UNKNOWN", out)
        self.assertNotIn("All in-scope default-branch workflows green", out)

    def test_version_1_verdict_without_scope_still_renders(self) -> None:
        """The persisted ref holds a version-1 verdict until the next cron run;
        reading it must not raise or invent a scope it never recorded."""
        verdict = {
            "version": 1,
            "checked_at": red_sweep._iso(_NOW - timedelta(hours=3)),
            "repos_checked": ["repo-a"],
            "errors": [],
            "red": [
                {
                    "repo": "repo-a",
                    "workflow": "Publish image",
                    "conclusion": "failure",
                    "class": "code/other",
                    "url": "https://example.test/run/1",
                }
            ],
        }
        out = red_sweep.render_check(verdict, now=_NOW)
        self.assertIn("scope=?", out)
        self.assertIn("repo-a :: Publish image :: failure :: code/other", out)

    def test_unreadable_scope_is_called_out(self) -> None:
        verdict = self._fresh(
            red=[
                {
                    "repo": "repo-a",
                    "workflow": "branch-protection-audit",
                    "conclusion": "failure",
                    "class": "code/other",
                    "scope": red_sweep.SCOPE_UNREADABLE,
                    "url": "https://example.test/run/1",
                }
            ]
        )
        out = red_sweep.render_check(verdict, now=_NOW)
        self.assertIn("triggers could not be read", out)
        self.assertIn("swept IN unclassified rather than dropped", out)

    def test_fresh_red_lists_runs_and_drift_note(self) -> None:
        verdict = self._fresh(
            red=[
                {
                    "repo": "repo-a",
                    "workflow": "Publish image",
                    "conclusion": "failure",
                    "class": "base-image-drift",
                    "scope": red_sweep.SCOPE_NAME_CLASS,
                    "url": "https://example.test/run/1",
                }
            ]
        )
        out = red_sweep.render_check(verdict, now=_NOW)
        self.assertIn("RED default-branch run(s)", out)
        self.assertIn(
            "repo-a :: Publish image :: failure :: base-image-drift :: scope=name-class", out
        )
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
