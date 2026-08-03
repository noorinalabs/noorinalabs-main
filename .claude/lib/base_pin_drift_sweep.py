#!/usr/bin/env python3
"""Cross-repo base-image digest-pin drift sweep (#1205).

Motivation
==========
`.claude/lib/check_dockerfile_base_pin.py` enforces, per-Dockerfile, that
every `FROM` is digest-pinned (`image:tag@sha256:<digest>`). That gate is
deliberately per-file and per-repo: it has no view across repos. #1205 was
filed after `python:3.14-slim` turned up pinned to THREE different digests —
months apart — across `noorinalabs-deploy` and `noorinalabs-isnad-graph`,
with nothing reconciling them. Digest pinning trades automatic freshness for
reproducibility; Dependabot buys the freshness back per-repo, but there is no
org-level view of "this tag is pinned in N places, at M different ages."

This module is that view: a periodic **reporting** sweep (explicitly NOT a
merge-blocking gate — the remediation is always "merge the open Dependabot
PR", a human/merge-queue decision, same posture the issue asks for) that:

  1. collects every digest-pinned `FROM` across all org repos, reusing
     `check_dockerfile_base_pin.parse_froms` (do not hand-roll a second `FROM`
     parser — #1271 tracks three such regressions already in this repo),
  2. groups pins by the upstream `registry/repository:tag` they share,
  3. resolves each pinned digest's (and each tag's CURRENT digest's) `created`
     timestamp from the registry,
  4. flags a tag where two repos' pins differ by more than a threshold (cross-
     repo drift), or where a pin is more than N days behind the tag's current
     digest (behind-current-tag drift).

Degradation stance (the single most important property here, per the org's
standing lesson that a helper's failure mode must not read as a healthy
zero): ANY registry-resolution failure — network error, HTTP 429 (Docker
Hub's anonymous rate limit), 404, a manifest/config blob that doesn't parse,
or a manifest list with no linux/amd64 entry — reports `status="unknown"`
with a `reason`, NEVER "no drift". `render_check` below treats a non-empty
`unknown` list, a missing verdict, or a stale verdict exactly like
`red_sweep.py` treats them: a loud WARNING, never a false all-clean. A repo
whose Dockerfile listing itself could not be fetched lands in `repos_errors`,
mirroring `red_sweep.sweep`'s `errors` list.

Multi-arch stance (#1205's own evidence table was built by "resolving each
pin's amd64 config blob"): a tag's manifest is very often a manifest
list/OCI index with several platform entries. This module always resolves
the **linux/amd64** platform specifically — the one every consuming
Dockerfile in this org actually builds FROM in CI (GitHub-hosted amd64
runners) — and reports `no_amd64_platform` explicitly rather than silently
picking an arbitrary platform when amd64 is absent.

Auth: registry manifest/blob reads use the standard OCI distribution
`WWW-Authenticate: Bearer realm=...,service=...,scope=...` challenge/token
flow (`_get_with_auth`/`get_bearer_token`) — registry-agnostic, so it works
unmodified against Docker Hub, `ghcr.io`, and `gcr.io` without a per-registry
special case. Docker Hub anonymous pulls are rate-limited; a 429 is its own
distinct `unknown` reason (`rate_limited`), never conflated with "not found"
or a clean/no-drift result. Each unique `(registry, repository, digest)` is
resolved at most ONCE per sweep run (memoized) specifically to keep pull
volume low against that budget.

Scope note (explicitly not oversold, per the issue): this is skew and
audit-surface, not a live CVE — the in-image `apt-get -y upgrade` /
`apk upgrade` limb of the base-pin convention already re-freshens packages at
build time on top of whatever base a Dockerfile pins. This sweep exists so
the pin AGES are visible together, which nothing did before.

Home (#1205 "pick one and justify it"): this is wired as its OWN scheduled
workflow (`.github/workflows/base-pin-drift-sweep.yml`), modeled directly on
`red_sweep.py` + `red-sweep.yml`'s pattern (persist a small JSON verdict to a
dedicated lightweight `refs/meta/*` ref; read cheaply with a staleness
guard) rather than folded into `red-sweep.yml` itself or a `/wave-wrapup`
step:

  * `red-sweep.yml` polls GitHub Actions run state via `gh api` only, on a 6h
    cadence tuned to catch a red publish/deploy run before it rots silently
    for days. Base-image pin AGE moves on the order of days-to-weeks (a
    Dependabot PR sitting unmerged) — 6-hourly resolution buys nothing and
    needlessly spends anonymous registry-pull budget shared with actual image
    builds.
  * Registry-API auth/rate-limit failure modes (429, WWW-Authenticate token
    exchange) are a different surface than the GH Actions API `red_sweep.py`
    already handles; conflating them in one workflow would mean a Docker Hub
    rate-limit only degrades PART of that workflow's verdict, which is a
    subtler failure shape than two small, independently-readable verdicts.
  * `/wave-wrapup` runs only when a wave wraps — this sweep should surface
    drift on a standing cadence independent of wave cadence.

CLI
===
    base_pin_drift_sweep.py sweep [--out PATH] [--repos R1,R2,...]
                                   [--cross-repo-threshold-days N]
                                   [--behind-tag-threshold-days N]
    base_pin_drift_sweep.py check [--max-age-hours H] [--json]

``check`` always exits 0 (informational, mirrors `red_sweep.py check`).
``sweep`` exits 0 when at least one repo's Dockerfiles were enumerated, 2
when NONE were (a fully-broken sweep must turn its own cron run red, not
persist a quiet, misleadingly-clean verdict).
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from check_dockerfile_base_pin import digest_of, parse_froms, registry_host
from org_repos import ALL_REPOS as CANONICAL_REPOS
from org_repos import MAIN_REPO as _MAIN_REPO
from org_repos import ORG as _ORG

#: Where the sweep persists its verdict, and how old it may be before the
#: reader must WARN instead of trusting it. Modeled directly on
#: `red_sweep.py`'s `META_REF`/`VERDICT_FILE`/`DEFAULT_MAX_AGE_HOURS`, but a
#: longer default staleness window (this sweep runs daily, not every 6h).
META_REF = "refs/meta/base-pin-drift"
VERDICT_FILE = "base-pin-drift.json"
DEFAULT_MAX_AGE_HOURS = 48.0

#: Default drift thresholds (issue #1205's own "e.g. 30 days" example,
#: applied symmetrically to both drift dimensions; both are CLI-overridable).
DEFAULT_CROSS_REPO_THRESHOLD_DAYS = 30.0
DEFAULT_BEHIND_TAG_THRESHOLD_DAYS = 30.0

_GH_ERRORS = (subprocess.CalledProcessError, OSError)


def _run_gh(args: list[str]) -> str:
    """Run ``gh <args>`` (explicit arg list, never a shell string — main#688)."""
    proc = subprocess.run(["gh", *args], capture_output=True, text=True, check=True)
    return proc.stdout


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(ts: str) -> datetime | None:
    """Parse an ISO-8601 timestamp (``Z`` or offset form), or None if malformed."""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# --- Cross-repo Dockerfile collection (gh api only — no child-repo checkout,
# same posture as red_sweep.py) ---------------------------------------------


def list_repo_dockerfile_paths(
    owner: str, repo: str, ref: str, run_gh: Callable[[list[str]], str] = _run_gh
) -> list[str] | None:
    """Every `Dockerfile`/`Dockerfile.*` path in `repo` at `ref`, or None on failure.

    Uses one recursive git-tree call (mirrors `roster_union_sync.fetch_child_*`'s
    "gh api, no checkout" pattern). The basename filter matches the `find`
    invocation `dockerfile-base-pin.yml` already runs per-repo
    (`-name 'Dockerfile' -o -name 'Dockerfile.*'`), so this collects exactly the
    same file set the per-repo gate lints.
    """
    try:
        out = run_gh(["api", f"repos/{owner}/{repo}/git/trees/{ref}?recursive=1"])
        data = json.loads(out)
    except (*_GH_ERRORS, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    tree = data.get("tree")
    if not isinstance(tree, list):
        return None
    paths: list[str] = []
    for item in tree:
        if not isinstance(item, dict) or item.get("type") != "blob":
            continue
        path = item.get("path")
        if not isinstance(path, str) or not path:
            continue
        name = path.rsplit("/", 1)[-1]
        if name == "Dockerfile" or name.startswith("Dockerfile."):
            paths.append(path)
    return paths


def fetch_file_text(
    owner: str, repo: str, path: str, run_gh: Callable[[list[str]], str] = _run_gh
) -> str | None:
    """Fetch one file's text content via the contents API, or None on failure."""
    try:
        out = run_gh(["api", f"repos/{owner}/{repo}/contents/{path}", "--jq", ".content"])
    except _GH_ERRORS:
        return None
    raw = out.strip()
    if not raw:
        return None
    try:
        return base64.b64decode(raw).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None


@dataclass(frozen=True)
class Pin:
    """One digest-pinned `FROM` found in a Dockerfile."""

    repo: str
    path: str
    lineno: int
    image: str
    registry: str
    repository: str
    tag: str
    digest: str


@dataclass(frozen=True)
class RepoCollectResult:
    dockerfile_paths: list[str]
    pins: list[Pin]
    fetch_failures: list[str]


def parse_image_ref(image: str) -> tuple[str, str, str] | None:
    """(registry_host, repository_path, tag) for a digest-pinned ref, else None.

    Reuses `digest_of`/`registry_host` from `check_dockerfile_base_pin.py`
    (#1271 — one `FROM`/ref parser, not a second hand-rolled one). Returns
    None for anything that is not digest-pinned at all (an unpinned `FROM`,
    a stage reference, `scratch`) — this sweep only ever looks at pins that
    are ALREADY compliant with the per-repo gate; a non-compliant `FROM` is
    that gate's problem, not this one's.
    """
    digest = digest_of(image)
    if digest is None:
        return None
    ref = image.split("@", 1)[0]
    host = registry_host(image)
    if host is not None:
        remainder = ref.split("/", 1)[1] if "/" in ref else ""
    else:
        host = "docker.io"
        remainder = ref
    if not remainder:
        return None
    last_segment = remainder.rsplit("/", 1)[-1]
    if ":" in last_segment:
        repository, tag = remainder.rsplit(":", 1)
    else:
        repository, tag = remainder, "latest"
    if "/" not in repository:
        repository = f"library/{repository}"
    return host, repository, tag


def collect_repo_pins(
    owner: str, repo: str, ref: str, run_gh: Callable[[list[str]], str] = _run_gh
) -> RepoCollectResult | None:
    """Collect every digest-pinned `FROM` in `repo`, or None if the repo's
    Dockerfile listing itself could not be fetched (whole-repo UNKNOWN)."""
    paths = list_repo_dockerfile_paths(owner, repo, ref, run_gh)
    if paths is None:
        return None
    pins: list[Pin] = []
    fetch_failures: list[str] = []
    for path in paths:
        text = fetch_file_text(owner, repo, path, run_gh)
        if text is None:
            fetch_failures.append(path)
            continue
        for stmt in parse_froms(text):
            parsed = parse_image_ref(stmt.image)
            if parsed is None:
                continue
            registry, repository, tag = parsed
            digest = digest_of(stmt.image)
            if digest is None:  # pragma: no cover — parse_image_ref already gated this
                continue
            pins.append(
                Pin(
                    repo=repo,
                    path=path,
                    lineno=stmt.lineno,
                    image=stmt.image,
                    registry=registry,
                    repository=repository,
                    tag=tag,
                    digest=digest,
                )
            )
    return RepoCollectResult(dockerfile_paths=paths, pins=pins, fetch_failures=fetch_failures)


def image_key(registry: str, repository: str, tag: str) -> str:
    return f"{registry}/{repository}:{tag}"


# --- Registry resolution (network I/O, injectable) --------------------------


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: dict[str, str]
    body: bytes


def default_http_get(
    url: str, headers: dict[str, str] | None = None, timeout: float = 10.0
) -> HttpResponse:
    """Real network GET. An HTTP-level error response (401/404/429/5xx) is
    returned as a normal `HttpResponse` (status carries the code); only a
    genuine transport failure (timeout, DNS, connection refused — a bare
    `urllib.error.URLError` with no `.code`) propagates as an exception.
    """
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return HttpResponse(
                status=resp.status, headers=dict(resp.headers.items()), body=resp.read()
            )
    except urllib.error.HTTPError as exc:
        body = exc.read() if hasattr(exc, "read") else b""
        return HttpResponse(status=exc.code, headers=dict(exc.headers or {}), body=body)


HttpGet = Callable[..., HttpResponse]


def _find_header(headers: dict[str, str], name: str) -> str | None:
    """Case-insensitive header lookup.

    `urllib.error.HTTPError.headers` (the path a 401 response takes) preserves
    whatever casing the server sent — Docker Hub sends a lowercase
    `www-authenticate`, not the `WWW-Authenticate` most examples show — so a
    plain `dict.get("WWW-Authenticate")` silently misses it and the sweep would
    treat every registry pin as unauthenticated 401 `unknown`, never actually
    completing the bearer exchange. Scan case-insensitively instead of guessing
    a fixed casing.
    """
    name_l = name.lower()
    for key, value in headers.items():
        if key.lower() == name_l:
            return value
    return None


_WWW_AUTH_RE = re.compile(r'(\w+)="([^"]*)"')


def parse_www_authenticate(header: str) -> dict[str, str] | None:
    """Parse a `WWW-Authenticate: Bearer realm=...,service=...,scope=...`
    challenge into its key/value params, or None if it isn't a Bearer challenge.
    """
    if not header or not header.strip().lower().startswith("bearer"):
        return None
    return dict(_WWW_AUTH_RE.findall(header))


def get_bearer_token(challenge: dict[str, str], http_get: HttpGet) -> str | None:
    """Exchange a parsed Bearer challenge for a token, or None on any failure.

    Generic OCI distribution auth flow — works unmodified against Docker Hub,
    `ghcr.io`, and `gcr.io`, since all three speak the same
    `WWW-Authenticate` challenge shape; no per-registry special case.
    """
    realm = challenge.get("realm")
    if not realm:
        return None
    params = {k: v for k, v in challenge.items() if k != "realm"}
    url = f"{realm}?{urllib.parse.urlencode(params)}" if params else realm
    try:
        resp = http_get(url, headers={"Accept": "application/json"})
    except urllib.error.URLError:
        return None
    if resp.status != 200:
        return None
    try:
        data = json.loads(resp.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    token = data.get("token") or data.get("access_token")
    return token if isinstance(token, str) and token else None


def _get_with_auth(url: str, accept: str, http_get: HttpGet) -> HttpResponse:
    """GET `url`, transparently completing the Bearer challenge/token exchange
    on a 401. If the 401 carries no parseable challenge, or the token exchange
    itself fails, the original 401 response is returned unchanged (the caller
    maps any non-200 to its own `unknown` reason)."""
    headers = {"Accept": accept}
    resp = http_get(url, headers=headers)
    if resp.status != 401:
        return resp
    www_auth = _find_header(resp.headers, "WWW-Authenticate")
    challenge = parse_www_authenticate(www_auth) if www_auth else None
    if challenge is None:
        return resp
    token = get_bearer_token(challenge, http_get)
    if token is None:
        return resp
    headers["Authorization"] = f"Bearer {token}"
    return http_get(url, headers=headers)


#: registry host -> the actual API host to hit. Docker Hub's `/v2/` API lives
#: on `registry-1.docker.io`, not `docker.io` itself; every other registry in
#: `DEFAULT_ALLOWED_REGISTRIES` (`ghcr.io`, `gcr.io`) serves its own `/v2/` API
#: at its own hostname.
_REGISTRY_API_HOST: dict[str, str] = {"docker.io": "registry-1.docker.io"}

_MANIFEST_ACCEPT = ", ".join(
    [
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.v2+json",
    ]
)
_CONFIG_ACCEPT = "application/vnd.oci.image.config.v1+json, application/json"


def _api_host(registry: str) -> str:
    return _REGISTRY_API_HOST.get(registry, registry)


@dataclass(frozen=True)
class ResolveOutcome:
    """Result of resolving one manifest reference's amd64 config `created` date.

    `status` is `"ok"` (with `created` set) or `"unknown"` (with `reason`
    set). There is no third state — a failure is ALWAYS `"unknown"`, never a
    default/placeholder `created` value standing in for "couldn't tell".
    """

    status: str
    created: str | None = None
    reason: str | None = None


def _unknown(reason: str) -> ResolveOutcome:
    return ResolveOutcome(status="unknown", reason=reason)


def _fetch_json(
    url: str, accept: str, http_get: HttpGet
) -> tuple[dict | None, ResolveOutcome | None]:
    """GET `url` and parse it as a JSON object, or return a `ResolveOutcome`
    describing exactly why it could not be resolved. The three explicit HTTP
    failure modes (429 / 404 / other non-200) are distinguished so a caller —
    and this sweep's report — never conflates "rate limited" with "not found"
    or a genuine parse failure."""
    try:
        resp = _get_with_auth(url, accept, http_get)
    except urllib.error.URLError:
        return None, _unknown("network_error")
    if resp.status == 429:
        return None, _unknown("rate_limited")
    if resp.status == 404:
        return None, _unknown("not_found")
    if resp.status != 200:
        return None, _unknown(f"http_{resp.status}")
    try:
        data = json.loads(resp.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None, _unknown("malformed")
    if not isinstance(data, dict):
        return None, _unknown("malformed")
    return data, None


def _select_amd64_manifest_digest(index: dict) -> str | None:
    """The `linux/amd64` entry's digest from a manifest list/OCI index, or
    None if no such platform entry exists (`no_amd64_platform` — see the
    module docstring's "Multi-arch stance")."""
    manifests = index.get("manifests")
    if not isinstance(manifests, list):
        return None
    for entry in manifests:
        if not isinstance(entry, dict):
            continue
        platform = entry.get("platform")
        if not isinstance(platform, dict):
            continue
        if platform.get("architecture") == "amd64" and platform.get("os") == "linux":
            digest = entry.get("digest")
            if isinstance(digest, str) and digest:
                return digest
    return None


def resolve_created(
    registry: str,
    repository: str,
    reference: str,
    http_get: HttpGet = default_http_get,
) -> ResolveOutcome:
    """Resolve the `created` timestamp of `reference`'s linux/amd64 image
    config. `reference` may be a digest (a specific pin) or a mutable tag
    (to resolve the tag's CURRENT digest). See the module docstring for the
    full degradation stance and multi-arch stance.
    """
    api_host = _api_host(registry)
    manifest_url = f"https://{api_host}/v2/{repository}/manifests/{reference}"
    manifest, failure = _fetch_json(manifest_url, _MANIFEST_ACCEPT, http_get)
    if failure is not None or manifest is None:
        return failure or _unknown("malformed")

    if "manifests" in manifest:
        amd64_digest = _select_amd64_manifest_digest(manifest)
        if amd64_digest is None:
            return _unknown("no_amd64_platform")
        arch_url = f"https://{api_host}/v2/{repository}/manifests/{amd64_digest}"
        manifest, failure = _fetch_json(arch_url, _MANIFEST_ACCEPT, http_get)
        if failure is not None or manifest is None:
            return failure or _unknown("malformed")
        if "manifests" in manifest:
            return _unknown("malformed")

    config = manifest.get("config")
    if not isinstance(config, dict):
        return _unknown("malformed")
    config_digest = config.get("digest")
    if not isinstance(config_digest, str) or not config_digest:
        return _unknown("malformed")

    blob_url = f"https://{api_host}/v2/{repository}/blobs/{config_digest}"
    blob, failure = _fetch_json(blob_url, _CONFIG_ACCEPT, http_get)
    if failure is not None or blob is None:
        return failure or _unknown("malformed")
    created = blob.get("created")
    if not isinstance(created, str) or not created:
        return _unknown("malformed")
    return ResolveOutcome(status="ok", created=created)


# --- Pure drift computation (no I/O) -----------------------------------------


@dataclass(frozen=True)
class ResolvedPin:
    repo: str
    path: str
    lineno: int
    registry: str
    repository: str
    tag: str
    digest: str
    outcome: ResolveOutcome

    @property
    def key(self) -> str:
        return image_key(self.registry, self.repository, self.tag)


@dataclass(frozen=True)
class DriftFinding:
    kind: str  # "cross_repo" | "behind_current_tag"
    image_key: str
    detail: str
    days: float


def compute_drift(
    resolved_pins: list[ResolvedPin],
    current_tag_outcomes: dict[str, ResolveOutcome],
    cross_repo_threshold_days: float = DEFAULT_CROSS_REPO_THRESHOLD_DAYS,
    behind_tag_threshold_days: float = DEFAULT_BEHIND_TAG_THRESHOLD_DAYS,
) -> tuple[list[DriftFinding], list[dict]]:
    """Pure grouping/drift logic — no network I/O, fully unit-testable.

    Returns `(findings, unknown)`. `unknown` covers every pin AND every
    tag-resolution whose `ResolveOutcome.status != "ok"` — surfaced
    ALONGSIDE `findings`, never silently dropped, so a sweep that resolved
    nothing (e.g. every request rate-limited) reports an empty `findings`
    list PLUS a populated `unknown` list, not a quiet all-clean.
    """
    unknown: list[dict] = []
    by_key: dict[str, list[ResolvedPin]] = {}
    for pin in resolved_pins:
        by_key.setdefault(pin.key, []).append(pin)
        if pin.outcome.status != "ok":
            unknown.append(
                {
                    "kind": "pin",
                    "repo": pin.repo,
                    "path": pin.path,
                    "lineno": pin.lineno,
                    "image_key": pin.key,
                    "digest": pin.digest,
                    "reason": pin.outcome.reason,
                }
            )

    findings: list[DriftFinding] = []
    for key in sorted(by_key):
        pins = by_key[key]
        dated: list[tuple[ResolvedPin, datetime]] = []
        for pin in pins:
            if pin.outcome.status != "ok" or pin.outcome.created is None:
                continue
            parsed = _parse_iso(pin.outcome.created)
            if parsed is not None:
                dated.append((pin, parsed))

        if len(dated) >= 2:
            oldest_pin, oldest_dt = min(dated, key=lambda pd: pd[1])
            newest_pin, newest_dt = max(dated, key=lambda pd: pd[1])
            span_days = (newest_dt - oldest_dt).total_seconds() / 86400.0
            if span_days > cross_repo_threshold_days:
                findings.append(
                    DriftFinding(
                        kind="cross_repo",
                        image_key=key,
                        detail=(
                            f"{oldest_pin.repo}:{oldest_pin.path}:{oldest_pin.lineno} pinned "
                            f"{oldest_dt.date().isoformat()} vs "
                            f"{newest_pin.repo}:{newest_pin.path}:{newest_pin.lineno} pinned "
                            f"{newest_dt.date().isoformat()}"
                        ),
                        days=span_days,
                    )
                )

        current_outcome = current_tag_outcomes.get(key)
        if current_outcome is None:
            continue
        if current_outcome.status != "ok" or current_outcome.created is None:
            unknown.append(
                {
                    "kind": "current_tag",
                    "image_key": key,
                    "reason": current_outcome.reason or "malformed",
                }
            )
            continue
        current_dt = _parse_iso(current_outcome.created)
        if current_dt is None:
            unknown.append({"kind": "current_tag", "image_key": key, "reason": "malformed"})
            continue
        for pin, dt in dated:
            behind_days = (current_dt - dt).total_seconds() / 86400.0
            if behind_days > behind_tag_threshold_days:
                findings.append(
                    DriftFinding(
                        kind="behind_current_tag",
                        image_key=key,
                        detail=(
                            f"{pin.repo}:{pin.path}:{pin.lineno} pinned "
                            f"{dt.date().isoformat()} is {behind_days:.0f}d behind the "
                            f"tag's current digest ({current_dt.date().isoformat()})"
                        ),
                        days=behind_days,
                    )
                )
    return findings, unknown


# --- Orchestration ------------------------------------------------------------


def sweep(
    repos: tuple[str, ...] | list[str] | None = None,
    run_gh: Callable[[list[str]], str] = _run_gh,
    http_get: HttpGet = default_http_get,
    now: datetime | None = None,
    cross_repo_threshold_days: float = DEFAULT_CROSS_REPO_THRESHOLD_DAYS,
    behind_tag_threshold_days: float = DEFAULT_BEHIND_TAG_THRESHOLD_DAYS,
) -> dict:
    """Sweep every digest-pinned `FROM` across `repos` (default: all canonical
    org repos) and return the verdict dict.

    Verdict shape (version 1):
      ``checked_at``    — UTC ISO timestamp of this sweep
      ``repos_checked`` — repos whose Dockerfile listing was fetched
      ``repos_errors``  — repos whose listing could NOT be fetched (UNKNOWN,
                          never silently clean)
      ``pins_checked``  — count of digest-pinned FROMs found
      ``findings``      — [{kind, image_key, detail, days}] drift over threshold
      ``unknown``       — [{...}] every pin/tag/file whose resolution failed —
                          reported alongside `findings`, never instead of it
    """
    repo_list = tuple(repos) if repos else CANONICAL_REPOS
    repos_checked: list[str] = []
    repos_errors: list[str] = []
    all_pins: list[Pin] = []
    unknown: list[dict] = []

    for repo in repo_list:
        try:
            branch = run_gh(["api", f"repos/{_ORG}/{repo}", "--jq", ".default_branch"]).strip()
        except _GH_ERRORS:
            branch = ""
        branch = branch or "main"

        result = collect_repo_pins(_ORG, repo, branch, run_gh)
        if result is None:
            repos_errors.append(repo)
            continue
        repos_checked.append(repo)
        all_pins.extend(result.pins)
        for path in result.fetch_failures:
            unknown.append(
                {"kind": "file", "repo": repo, "path": path, "reason": "file_fetch_failed"}
            )

    digest_cache: dict[tuple[str, str, str], ResolveOutcome] = {}
    resolved: list[ResolvedPin] = []
    for pin in all_pins:
        cache_key = (pin.registry, pin.repository, pin.digest)
        if cache_key not in digest_cache:
            digest_cache[cache_key] = resolve_created(
                pin.registry, pin.repository, pin.digest, http_get
            )
        resolved.append(
            ResolvedPin(
                repo=pin.repo,
                path=pin.path,
                lineno=pin.lineno,
                registry=pin.registry,
                repository=pin.repository,
                tag=pin.tag,
                digest=pin.digest,
                outcome=digest_cache[cache_key],
            )
        )

    tag_cache: dict[str, ResolveOutcome] = {}
    for rp in resolved:
        key = rp.key
        if key not in tag_cache:
            tag_cache[key] = resolve_created(rp.registry, rp.repository, rp.tag, http_get)

    findings, drift_unknown = compute_drift(
        resolved,
        tag_cache,
        cross_repo_threshold_days=cross_repo_threshold_days,
        behind_tag_threshold_days=behind_tag_threshold_days,
    )
    unknown.extend(drift_unknown)

    return {
        "version": 1,
        "checked_at": _iso(now or _utcnow()),
        "repos_checked": repos_checked,
        "repos_errors": repos_errors,
        "pins_checked": len(resolved),
        "findings": [
            {"kind": f.kind, "image_key": f.image_key, "detail": f.detail, "days": round(f.days, 1)}
            for f in findings
        ],
        "unknown": unknown,
    }


def read_verdict(run_gh: Callable[[list[str]], str] = _run_gh) -> dict | None:
    """Fetch the latest persisted verdict with ONE contents-API call, or None.

    Any failure (ref absent, network, corrupt content) returns None — the
    caller renders that as a WARNING, never as all-clean (mirrors
    `red_sweep.read_verdict` exactly).
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
        return None
    return data if isinstance(data, dict) else None


def verdict_age_hours(verdict: dict, now: datetime | None = None) -> float | None:
    """Age of the verdict in hours, or None when `checked_at` is unparseable."""
    raw = str(verdict.get("checked_at") or "")
    checked = _parse_iso(raw)
    if checked is None:
        return None
    return ((now or _utcnow()) - checked).total_seconds() / 3600.0


def render_check(
    verdict: dict | None,
    now: datetime | None = None,
    max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
) -> str:
    """Human-readable one-shot report.

    Degradation stance: a missing, corrupt, or stale verdict is a WARNING,
    never a false all-clean (same stance as `red_sweep.render_check`). A
    present-and-fresh verdict that nonetheless carries `unknown` entries or
    `repos_errors` is reported as clean-WHERE-KNOWN plus an explicit
    UNKNOWN warning for the rest — it is never allowed to read as a plain
    all-clean.
    """
    refresh = (
        "  Refresh: gh workflow run base-pin-drift-sweep.yml "
        f"--repo {_ORG}/{_MAIN_REPO}  (cron runs daily)"
    )
    if verdict is None:
        return (
            "WARNING: base-pin-drift verdict missing/unreadable at "
            f"{META_REF} — base-image pin drift UNKNOWN, do NOT assume clean.\n" + refresh
        )
    age = verdict_age_hours(verdict, now)
    if age is None or age > max_age_hours:
        age_txt = "unparseable checked_at" if age is None else f"{age:.1f}h old"
        return (
            f"WARNING: base-pin-drift verdict is STALE ({age_txt}, max {max_age_hours:.0f}h) — "
            "base-image pin drift UNKNOWN, do NOT assume clean.\n" + refresh
        )

    lines: list[str] = []
    findings = verdict.get("findings") or []
    unknown = verdict.get("unknown") or []
    repos_errors = verdict.get("repos_errors") or []
    checked_at = verdict.get("checked_at", "?")
    if findings:
        lines.append(f"Base-image pin DRIFT found as of {checked_at}:")
        for item in findings:
            lines.append(f"  [{item.get('kind')}] {item.get('image_key')} :: {item.get('detail')}")
    else:
        lines.append(f"No base-image pin drift over threshold as of {checked_at}.")
    if unknown:
        lines.append(
            f"WARNING: {len(unknown)} pin(s)/tag(s)/file(s) could not be resolved against the "
            "registry (network error, rate limit, not-found, or malformed response) — those are "
            "UNKNOWN, not clean."
        )
        for item in unknown[:10]:
            lines.append(f"  UNKNOWN :: {item}")
    if repos_errors:
        lines.append(
            "WARNING: sweep could not enumerate Dockerfiles for: "
            + ", ".join(repos_errors)
            + " — those repos are UNKNOWN, not clean."
        )
    return "\n".join(lines)


def _cmd_sweep(args: argparse.Namespace) -> int:
    repos = tuple(r for r in (args.repos or "").split(",") if r) or CANONICAL_REPOS
    verdict = sweep(
        repos,
        cross_repo_threshold_days=args.cross_repo_threshold_days,
        behind_tag_threshold_days=args.behind_tag_threshold_days,
    )
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
    p_sweep.add_argument(
        "--cross-repo-threshold-days",
        type=float,
        default=DEFAULT_CROSS_REPO_THRESHOLD_DAYS,
        help=f"flag when two repos' pins of the same tag differ by more than this many days "
        f"(default {DEFAULT_CROSS_REPO_THRESHOLD_DAYS:.0f})",
    )
    p_sweep.add_argument(
        "--behind-tag-threshold-days",
        type=float,
        default=DEFAULT_BEHIND_TAG_THRESHOLD_DAYS,
        help=f"flag a pin more than this many days behind the tag's current digest "
        f"(default {DEFAULT_BEHIND_TAG_THRESHOLD_DAYS:.0f})",
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
