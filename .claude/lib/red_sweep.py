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

* Only publish/deploy/release-class workflows are considered — the ones whose
  redness silently rots (a red lint is loud at PR time; a red publish on main
  is not — the GHCR case, isnad-graph 5804476, sat red ~12 days).
* Best-effort cause classification (main#647): a failed-job log carrying a
  base-image-CVE signal (trivy/grype/CVE/apk/openssl-class) is tagged
  ``base-image-drift`` — fix-forward the base image, not a code regression.
  Any log-fetch failure degrades to ``code/other``, never a false all-green.
* Degradation is always toward WARNING, never toward green: a repo whose run
  list could not be fetched lands in ``errors`` (reported UNKNOWN by the
  reader), and a missing/stale verdict is a loud WARNING at session start.

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

from org_repos import ALL_REPOS as CANONICAL_REPOS
from org_repos import MAIN_REPO as _MAIN_REPO
from org_repos import ORG as _ORG

#: All canonical org repos (CLAUDE.md Repository Map) — the cron sweeps every
#: one. Sourced from org_repos.py (main#1118 / audit G6), the org repo-list SSOT.

#: Publish/deploy/release-class workflow names (same pattern the skill used).
_WORKFLOW_CLASS_RE = re.compile(r"publish|deploy|release|promote|ghcr|image", re.IGNORECASE)

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


def _run_gh(args: list[str]) -> str:
    """Run ``gh <args>`` (explicit arg list, never a shell string — main#688)."""
    proc = subprocess.run(["gh", *args], capture_output=True, text=True, check=True)
    return proc.stdout


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def latest_class_runs(payload: dict) -> list[dict]:
    """Latest run per workflow, filtered to publish/deploy/release-class names.

    Mirrors the jq the skill ran: filter by name/display_title against the
    class regex, group by ``workflow_id``, keep the max ``run_started_at``.
    """
    latest: dict[object, dict] = {}
    for run in payload.get("workflow_runs", []):
        if not isinstance(run, dict):
            continue
        name = str(run.get("name") or run.get("display_title") or "")
        if not _WORKFLOW_CLASS_RE.search(name):
            continue
        key = run.get("workflow_id")
        current = latest.get(key)
        if current is None or str(run.get("run_started_at") or "") > str(
            current.get("run_started_at") or ""
        ):
            latest[key] = run
    return list(latest.values())


def classify_log(log_text: str | None) -> str:
    """``base-image-drift`` when the failed log carries a base-image-CVE signal.

    ``None`` (log unavailable) degrades to the unclassified ``code/other`` tag —
    never to a false all-green (main#647).
    """
    if log_text is None:
        return "code/other"
    return "base-image-drift" if _BASE_IMAGE_RE.search(log_text) else "code/other"


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
    """Sweep the latest default-branch run of every publish/deploy/release-class
    workflow across ``repos`` and return the verdict dict.

    Verdict shape (version 1):
      ``checked_at``    — UTC ISO timestamp of this sweep
      ``repos_checked`` — repos whose run list was successfully fetched
      ``errors``        — repos whose run list could NOT be fetched (UNKNOWN,
                          never silently green)
      ``red``           — [{repo, workflow, conclusion, class, url}] for each
                          red latest run
    """
    checked: list[str] = []
    errors: list[str] = []
    red: list[dict] = []
    for repo in repos or CANONICAL_REPOS:
        try:
            branch = run_gh(["api", f"repos/{_ORG}/{repo}", "--jq", ".default_branch"]).strip()
        except _GH_ERRORS:
            branch = ""
        branch = branch or "main"
        try:
            out = run_gh(["api", f"repos/{_ORG}/{repo}/actions/runs?branch={branch}&per_page=50"])
            payload = json.loads(out or "{}")
        except (*_GH_ERRORS, json.JSONDecodeError):
            errors.append(repo)
            continue
        for run in latest_class_runs(payload):
            conclusion = str(run.get("conclusion") or "")
            if conclusion not in RED_CONCLUSIONS:
                continue
            red.append(
                {
                    "repo": repo,
                    "workflow": str(run.get("name") or run.get("display_title") or "?"),
                    "conclusion": conclusion,
                    "class": _classify_run(repo, run.get("id"), run_gh),
                    "url": str(run.get("html_url") or ""),
                }
            )
        checked.append(repo)
    return {
        "version": 1,
        "checked_at": _iso(now or _utcnow()),
        "repos_checked": checked,
        "errors": errors,
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

    Degradation stance (unchanged from the in-skill sweep): a missing, corrupt,
    or stale verdict — or repos the sweep itself could not fetch — is reported
    as a WARNING/UNKNOWN, never as a false all-green.
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
    if red:
        lines.append(
            f"RED default-branch publish/deploy run(s) as of {checked_at} — "
            "investigate before relying on staging:"
        )
        for item in red:
            lines.append(
                f"  {item.get('repo')} :: {item.get('workflow')} :: "
                f"{item.get('conclusion')} :: {item.get('class')} :: {item.get('url')}"
            )
        if any(item.get("class") == "base-image-drift" for item in red):
            lines.append(
                "  NOTE: base-image-drift = a base-image CVE advisory, not a code "
                "regression — fix-forward the base image, do not chase the wave diff."
            )
    else:
        lines.append(
            f"All publish/deploy/release workflows green on default branches (as of {checked_at})."
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
