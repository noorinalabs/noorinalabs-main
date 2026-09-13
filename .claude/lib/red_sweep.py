#!/usr/bin/env python3
"""Red default-branch workflow sweep — shared by cron workflow and session-start (main#962).

Extracted from /session-start Step 5a (P3W14 retro Proposed Change #2), which
looped ``gh api`` + failed-log fetches across all 8 org repos in EVERY session.
The sweep now runs on a schedule (``.github/workflows/red-sweep.yml``, every 6h)
and persists a small JSON verdict to the dedicated lightweight ref
``refs/meta/red-sweep`` (single-file tree, parentless commit, force-updated —
O(1) storage, no branch/PR/workflow-trigger surface). Session-start reads the
latest verdict with ONE ``gh api`` contents call and applies a staleness guard.

Semantics preserved from the in-skill implementation:

* Scope is TRIGGER-based (main#1584): a workflow is swept when its redness is
  not surfaced by a PR check — schedule-triggered, or workflow_dispatch-only,
  on the default branch — UNION the historical publish/deploy/release name
  class (kept so push-triggered publishes stay covered). The rationale is
  unchanged from the original name-based scope (a red lint is loud at PR time;
  a red publish on main is not — the GHCR case, isnad-graph 5804476, sat red
  ~12 days); only the predicate is. The name-only predicate answered "is this
  called something deploy-ish?" when the question is "will anyone notice this
  going red?", and so structurally excluded `e2e-stg-smoke` (isnad-graph, daily
  cron). Measured 2026-09-13 over that workflow's COMPLETE run history on
  `main` — 94 runs, 93 ``failure`` + 1 ``cancelled``, 2026-06-13 to 2026-09-13,
  not one success ever — while the sweep reported all-green. Its sibling
  `e2e-stg-sweep`: 14 runs, 14 failures, likewise never green.
  Triggers are read from the workflow FILE's `on:` block, not from a run's
  `event` field: a run carries the one event that started it, never the
  workflow's full trigger set, and PR-event runs never appear in a
  default-branch-filtered run list at all.
* Best-effort cause classification (main#647): a failed-job log carrying a
  base-image-CVE signal (trivy/grype/CVE/apk/openssl-class) is tagged
  ``base-image-drift`` — fix-forward the base image, not a code regression.
  Any log-fetch failure degrades to ``code/other``, never a false all-green.
* Degradation is always toward WARNING, never toward green: a repo whose run
  list could not be fetched lands in ``errors`` (reported UNKNOWN by the
  reader), a workflow whose triggers could not be read is swept IN and tagged
  ``triggers-unreadable`` rather than silently dropped (main#1584 — a silent
  drop is precisely the failure mode this story fixed), a verdict covering
  zero repos is UNKNOWN rather than green, and a missing/stale verdict is a
  loud WARNING at session start.

Scope note: the sweep always covers ALL canonical org repos, not the current
wave's ``repos_in_scope`` — the cron has no wave context, and a red publish in
an out-of-wave repo rots just the same (strictly more coverage than Step 5a had).

CLI:
  red_sweep.py sweep [--out PATH] [--repos R1,R2,...]
  red_sweep.py check [--max-age-hours H] [--json]

``check`` always exits 0 (informational; session-start must never break on it).
``sweep`` exits 0 when at least one repo was checked, 2 when nothing was
(a fully-broken sweep must turn the cron run red, not persist quietly).
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import gh

try:  # PyYAML parses the workflow `on:` block (main#1584).
    import yaml as _yaml
except ImportError:  # pragma: no cover - degrades to triggers-unreadable, never a drop
    # Deliberately guarded, unlike the plain `import yaml` in sibling lib
    # modules: `red_sweep.py check` runs at every /session-start on a developer
    # machine and needs no YAML at all (it only reads the persisted verdict).
    # A hard import would turn "PyYAML not installed" into a session-start
    # crash for an unrelated reason. Absent PyYAML, every trigger read returns
    # None, which `run_scope` degrades to IN-scope/unclassified — noisier, never
    # silently narrower. red-sweep.yml pip-installs it so the cron takes the
    # deterministic path.
    _yaml = None  # type: ignore[assignment]

from org_repos import ALL_REPOS as CANONICAL_REPOS
from org_repos import MAIN_REPO as _MAIN_REPO
from org_repos import ORG as _ORG

#: All canonical org repos (CLAUDE.md Repository Map) — the cron sweeps every
#: one. Sourced from org_repos.py (main#1118 / audit G6), the org repo-list SSOT.

#: Publish/deploy/release-class workflow NAMES. Since main#1584 this is only
#: one term of the in-scope union (see :func:`run_scope`), not the whole
#: predicate: it keeps push-triggered publish/deploy workflows covered without
#: a trigger read. It must never again be the sole gate — a name substring is
#: a proxy for "will anyone notice this going red?", and six substrings is a
#: proxy that silently excludes every cron the org has not yet thought to name
#: `deploy`.
_WORKFLOW_CLASS_RE = re.compile(r"publish|deploy|release|promote|ghcr|image", re.IGNORECASE)

#: Why a workflow is in scope — recorded per red run as ``scope`` so a reader
#: can tell a cron nobody watches from a publish matched by name, and so a
#: degraded trigger read is visible rather than indistinguishable from a
#: confident classification.
SCOPE_SCHEDULE = "schedule"
SCOPE_DISPATCH_ONLY = "dispatch-only"
SCOPE_NAME_CLASS = "name-class"
SCOPE_UNREADABLE = "triggers-unreadable"

#: Verdict schema version. Bumped 1 -> 2 by main#1584 (red items gained
#: ``scope``; the verdict gained ``workflows_seen``). The reader still accepts
#: version-1 verdicts — the persisted ref holds one until the next cron run —
#: so every new field is read with a default, never indexed.
VERDICT_VERSION = 2

#: Non-success conclusions that count as red.
RED_CONCLUSIONS: frozenset[str] = frozenset(
    {"failure", "timed_out", "cancelled", "startup_failure"}
)

#: Base-image-CVE signals in a failed-job log (main#647) — same regex the skill used.
_BASE_IMAGE_RE = re.compile(
    r"trivy|grype|\bCVE-[0-9]{4}-[0-9]+|apk[ -].*(upgrade|CVE)"
    r"|openssl.*(vuln|CVE|advisor)|base[ -]image",
    re.IGNORECASE,
)

#: Where the cron persists the verdict, and how old it may be before the
#: session-start reader must WARN instead of trusting it.
META_REF = "refs/meta/red-sweep"
VERDICT_FILE = "red-sweep.json"
DEFAULT_MAX_AGE_HOURS = 24.0

_GH_ERRORS = (subprocess.CalledProcessError, OSError)


# Shared gh shim (main#1119). Still raises the raw CalledProcessError/OSError
# that `_GH_ERRORS` above catches — see gh.py § Error behaviour.
_run_gh = gh.run_gh


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def latest_runs_by_workflow(payload: dict) -> list[dict]:
    """Latest default-branch run per ``workflow_id`` — with NO scope filter.

    Group by ``workflow_id``, keep the max ``run_started_at``. Scope is applied
    later, per run, by :func:`run_scope`; this function deliberately filters
    nothing, because the main#1584 defect was a filter applied HERE that
    discarded candidates before anything could classify them.
    """
    latest: dict[object, dict] = {}
    for run in payload.get("workflow_runs", []):
        if not isinstance(run, dict):
            continue
        key = run.get("workflow_id")
        current = latest.get(key)
        if current is None or str(run.get("run_started_at") or "") > str(
            current.get("run_started_at") or ""
        ):
            latest[key] = run
    return list(latest.values())


def parse_workflow_triggers(text: str | None) -> frozenset[str] | None:
    """Top-level event names declared in a workflow file's ``on:`` block.

    Returns ``None`` when the trigger set cannot be determined — empty file,
    unparseable YAML, no PyYAML, an ``on:`` block of an unexpected shape, or an
    ``on:`` block that yields no events. ``None`` means UNKNOWN, and
    :func:`run_scope` degrades UNKNOWN to in-scope, never to a drop.
    """
    if not text or _yaml is None:
        return None
    try:
        doc = _yaml.safe_load(text)
    except Exception:  # yaml.YAMLError, and anything a malformed doc provokes
        return None
    if not isinstance(doc, dict):
        return None
    # PyYAML follows YAML 1.1, where a bare `on:` key resolves to the BOOLEAN
    # True — so the key in `doc` is `True`, not `"on"`. Reading only `doc["on"]`
    # finds nothing for essentially every real workflow file, which would make
    # every workflow look trigger-less. A quoted `"on":` does land under the
    # string key, so both spellings are checked.
    block = doc["on"] if "on" in doc else doc.get(True)
    if isinstance(block, str):
        events = {block}
    elif isinstance(block, list):
        events = {e for e in block if isinstance(e, str)}
    elif isinstance(block, dict):
        events = {str(k) for k in block}
    else:
        return None
    return frozenset(events) or None


def run_scope(name: str, triggers: frozenset[str] | None) -> str | None:
    """Why this workflow is in the sweep's scope, or ``None`` if it is not.

    The main#1584 predicate — *"a workflow whose redness is not surfaced by a
    PR check"*::

        in scope  <=>  schedule-triggered
                   or  workflow_dispatch-only
                   or  name matches the publish/deploy/release class
                   or  the trigger set could not be read (UNKNOWN)

    A ``schedule`` run is never a PR check by construction, and a
    dispatch-only workflow never runs on a PR at all. Anything else with a
    readable trigger set (a lint on ``pull_request``, a CI job on ``push``)
    is left out: that is the noise guard the original name filter existed for,
    now expressed against the property that actually matters.

    Known, deliberate residual: a workflow triggered only by ``push`` to the
    default branch, with no PR trigger and a non-matching name, is NOT swept.
    Widening to it means treating "has no pull_request trigger" as the test,
    which also pulls in every push+PR lint unless the PR trigger is read
    separately. Left out rather than widened silently — see main#1584.
    """
    name_class = bool(_WORKFLOW_CLASS_RE.search(name))
    if triggers is None:
        # UNKNOWN triggers: in scope either way, but say which is known.
        return SCOPE_NAME_CLASS if name_class else SCOPE_UNREADABLE
    if "schedule" in triggers:
        return SCOPE_SCHEDULE
    if triggers <= {"workflow_dispatch"}:
        return SCOPE_DISPATCH_ONLY
    return SCOPE_NAME_CLASS if name_class else None


def classify_log(log_text: str | None) -> str:
    """``base-image-drift`` when the failed log carries a base-image-CVE signal.

    ``None`` (log unavailable) degrades to the unclassified ``code/other`` tag —
    never to a false all-green (main#647).
    """
    if log_text is None:
        return "code/other"
    return "base-image-drift" if _BASE_IMAGE_RE.search(log_text) else "code/other"


def fetch_workflow_triggers(
    repo: str, path: str, ref: str, run_gh=_run_gh
) -> frozenset[str] | None:
    """Read ``path``'s ``on:`` block from ``repo`` at ``ref``; ``None`` on any failure.

    One contents-API call. ``None`` (fetch failed, not base64, bad UTF-8,
    unparseable) is UNKNOWN, which :func:`run_scope` degrades to in-scope.
    """
    if not path:
        return None
    try:
        content = run_gh(
            ["api", f"repos/{_ORG}/{repo}/contents/{path}?ref={ref}", "--jq", ".content"]
        )
        text = base64.b64decode(content).decode("utf-8")
    except (*_GH_ERRORS, ValueError):
        # ValueError covers binascii.Error and bad UTF-8, as in read_verdict.
        return None
    return parse_workflow_triggers(text)


def _classify_run(repo: str, run_id: object, run_gh) -> str:
    try:
        log = run_gh(["run", "view", str(run_id), "--repo", f"{_ORG}/{repo}", "--log-failed"])
    except _GH_ERRORS:
        return classify_log(None)
    return classify_log(log)


def sweep(
    repos: tuple[str, ...] | list[str] | None = None,
    run_gh=_run_gh,
    now: datetime | None = None,
) -> dict:
    """Sweep the latest default-branch run of every in-scope workflow across
    ``repos`` and return the verdict dict.

    In-scope is :func:`run_scope` — trigger-based since main#1584, no longer a
    workflow-name substring match.

    Verdict shape (version 2):
      ``checked_at``     — UTC ISO timestamp of this sweep
      ``repos_checked``  — repos whose run list was successfully fetched
      ``errors``         — repos whose run list could NOT be fetched (UNKNOWN,
                           never silently green)
      ``workflows_seen`` — distinct workflows whose latest default-branch run
                           was examined, in scope or not. A verdict with
                           ``red: []`` and ``workflows_seen: 0`` looked at
                           nothing and is not evidence of green.
      ``red``            — [{repo, workflow, conclusion, class, scope, url}]
                           for each red latest run of an in-scope workflow
    """
    checked: list[str] = []
    errors: list[str] = []
    red: list[dict] = []
    workflows_seen = 0
    # (repo, workflow path) -> triggers. A workflow file is read at most once
    # per sweep even when several repos share a path name.
    trigger_cache: dict[tuple[str, str], frozenset[str] | None] = {}
    for repo in repos or CANONICAL_REPOS:
        try:
            branch = run_gh(["api", f"repos/{_ORG}/{repo}", "--jq", ".default_branch"]).strip()
        except _GH_ERRORS:
            branch = ""
        branch = branch or "main"
        try:
            # per_page=100 is the API maximum. At 50, the default-branch run
            # window on a busy repo spans only a few days, so a weekly cron's
            # latest run can fall off the end and go unexamined — invisible in
            # exactly the same way the name filter made it. 100 is the same one
            # call. Runs older than this window remain a known blind spot.
            out = run_gh(["api", f"repos/{_ORG}/{repo}/actions/runs?branch={branch}&per_page=100"])
            payload = json.loads(out or "{}")
        except (*_GH_ERRORS, json.JSONDecodeError):
            errors.append(repo)
            continue
        for run in latest_runs_by_workflow(payload):
            workflows_seen += 1
            conclusion = str(run.get("conclusion") or "")
            # Redness is tested BEFORE scope purely for API economy: scope may
            # cost a contents call, and `red and in_scope` is the same set as
            # `in_scope and red`. Nothing is dropped by the ordering — a green
            # in-scope workflow produces no verdict entry either way.
            if conclusion not in RED_CONCLUSIONS:
                continue
            name = str(run.get("name") or run.get("display_title") or "?")
            path = str(run.get("path") or "")
            key = (repo, path)
            if key not in trigger_cache:
                trigger_cache[key] = fetch_workflow_triggers(repo, path, branch, run_gh)
            scope = run_scope(name, trigger_cache[key])
            if scope is None:
                continue
            red.append(
                {
                    "repo": repo,
                    "workflow": name,
                    "conclusion": conclusion,
                    "class": _classify_run(repo, run.get("id"), run_gh),
                    "scope": scope,
                    "url": str(run.get("html_url") or ""),
                }
            )
        checked.append(repo)
    return {
        "version": VERDICT_VERSION,
        "checked_at": _iso(now or _utcnow()),
        "repos_checked": checked,
        "errors": errors,
        "workflows_seen": workflows_seen,
        "red": red,
    }


def read_verdict(run_gh=_run_gh) -> dict | None:
    """Fetch the latest persisted verdict with ONE contents-API call, or None.

    Any failure (ref absent, network, corrupt content) returns None — the
    caller renders that as a WARNING, never as all-green.
    """
    try:
        content = run_gh(
            [
                "api",
                f"repos/{_ORG}/{_MAIN_REPO}/contents/{VERDICT_FILE}?ref={META_REF}",
                "--jq",
                ".content",
            ]
        )
        data = json.loads(base64.b64decode(content).decode("utf-8"))
    except (*_GH_ERRORS, ValueError):
        # ValueError covers json.JSONDecodeError, binascii.Error, and bad UTF-8 sizes.
        return None
    return data if isinstance(data, dict) else None


def verdict_age_hours(verdict: dict, now: datetime | None = None) -> float | None:
    """Age of the verdict in hours, or None when ``checked_at`` is unparseable."""
    raw = str(verdict.get("checked_at") or "")
    try:
        checked = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if checked.tzinfo is None:
        checked = checked.replace(tzinfo=timezone.utc)
    return ((now or _utcnow()) - checked).total_seconds() / 3600.0


def render_check(
    verdict: dict | None,
    now: datetime | None = None,
    max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
) -> str:
    """Human-readable one-shot report for session-start Step 5a.

    Degradation stance (unchanged from the in-skill sweep, extended by
    main#1584): a missing, corrupt, or stale verdict — or one covering zero
    repos, or repos the sweep itself could not fetch — is reported as a
    WARNING/UNKNOWN, never as a false all-green. Accepts version-1 verdicts:
    every field added since is read with a default.
    """
    refresh = (
        f"  Refresh: gh workflow run red-sweep.yml --repo {_ORG}/{_MAIN_REPO}  (cron runs every 6h)"
    )
    if verdict is None:
        return (
            "WARNING: red-sweep verdict missing/unreadable at "
            f"{META_REF} — red default-branch runs UNKNOWN, do NOT assume green.\n" + refresh
        )
    age = verdict_age_hours(verdict, now)
    if age is None or age > max_age_hours:
        age_txt = "unparseable checked_at" if age is None else f"{age:.1f}h old"
        return (
            f"WARNING: red-sweep verdict is STALE ({age_txt}, max {max_age_hours:.0f}h) — "
            "red default-branch runs UNKNOWN, do NOT assume green.\n" + refresh
        )

    lines: list[str] = []
    red = verdict.get("red") or []
    errors = verdict.get("errors") or []
    checked_at = verdict.get("checked_at", "?")
    repos_checked = verdict.get("repos_checked") or []
    if not repos_checked:
        # A sweep that fetched no repo has no evidence of anything. Without
        # this branch an empty verdict renders as the all-green line — the
        # same class of false green main#1584 fixed in the scope predicate.
        return (
            f"WARNING: red-sweep verdict (as of {checked_at}) covers ZERO repos — "
            "red default-branch runs UNKNOWN, do NOT assume green.\n" + refresh
        )
    if red:
        lines.append(
            f"RED default-branch run(s) as of {checked_at} — investigate before relying on staging:"
        )
        for item in red:
            # `scope` is absent from version-1 verdicts (the persisted ref
            # holds one until the next cron run) — render it as unknown rather
            # than raising or implying a classification that was never made.
            lines.append(
                f"  {item.get('repo')} :: {item.get('workflow')} :: "
                f"{item.get('conclusion')} :: {item.get('class')} :: "
                f"scope={item.get('scope') or '?'} :: {item.get('url')}"
            )
        if any(item.get("class") == "base-image-drift" for item in red):
            lines.append(
                "  NOTE: base-image-drift = a base-image CVE advisory, not a code "
                "regression — fix-forward the base image, do not chase the wave diff."
            )
        if any(item.get("scope") == SCOPE_UNREADABLE for item in red):
            lines.append(
                f"  NOTE: scope={SCOPE_UNREADABLE} = the workflow's triggers could not be "
                "read, so it was swept IN unclassified rather than dropped — it may be a "
                "PR-visible job you already knew about."
            )
    else:
        # Say what the green covers. The predecessor line claimed "All
        # publish/deploy/release workflows green", which was true and useless:
        # it was green over a set that excluded the red things (main#1584).
        seen = verdict.get("workflows_seen")
        seen_txt = f", {seen} workflow(s) examined" if isinstance(seen, int) else ""
        lines.append(
            "All in-scope default-branch workflows green — scope: schedule-triggered, "
            "workflow_dispatch-only, or publish/deploy/release-class "
            f"(as of {checked_at}, {len(repos_checked)} repo(s){seen_txt})."
        )
    if errors:
        lines.append(
            "WARNING: sweep could not fetch run lists for: "
            + ", ".join(str(e) for e in errors)
            + " — those repos are UNKNOWN, not green."
        )
    return "\n".join(lines)


def _cmd_sweep(args: argparse.Namespace) -> int:
    repos = tuple(r for r in (args.repos or "").split(",") if r) or CANONICAL_REPOS
    verdict = sweep(repos)
    text = json.dumps(verdict, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if verdict["repos_checked"] else 2


def _cmd_check(args: argparse.Namespace) -> int:
    verdict = read_verdict()
    if args.json:
        print(json.dumps(verdict, indent=2))
        return 0
    print(render_check(verdict, max_age_hours=args.max_age_hours))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_sweep = sub.add_parser("sweep", help="run the sweep and print/write the verdict JSON")
    p_sweep.add_argument("--out", default=None, help="also write the verdict JSON to this path")
    p_sweep.add_argument(
        "--repos", default=None, help="comma-separated repo names (default: all canonical repos)"
    )
    p_sweep.set_defaults(func=_cmd_sweep)

    p_check = sub.add_parser(
        "check", help="read the latest persisted verdict and report (always exits 0)"
    )
    p_check.add_argument(
        "--max-age-hours",
        type=float,
        default=DEFAULT_MAX_AGE_HOURS,
        help=f"staleness threshold (default {DEFAULT_MAX_AGE_HOURS:.0f}h)",
    )
    p_check.add_argument("--json", action="store_true", help="emit the raw verdict as JSON")
    p_check.set_defaults(func=_cmd_check)
    return parser


def main(argv: list[str]) -> int:
    args = _build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
