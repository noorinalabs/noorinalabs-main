#!/usr/bin/env python3
"""Tests for base_pin_drift_sweep.py — the cross-repo base-pin drift sweep (#1205).

Covers: `parse_image_ref` (docker-hub official/namespaced, ghcr.io, gcr.io,
unpinned/exempt refs), cross-repo Dockerfile collection over an injected `gh`
double, the generic WWW-Authenticate bearer-token flow, `resolve_created`'s
full degradation stance (network error, 429 rate-limit, 404, malformed
manifest/config, no-amd64-platform, and the happy paths for both a manifest
list and a bare single-arch manifest), the pure `compute_drift` grouping
logic, an end-to-end `sweep()` over injected `gh`+`http` doubles, and the
`read_verdict`/`render_check`/`verdict_age_hours` staleness-guard trio
(mirrors `test_red_sweep.py`'s coverage shape for that trio).

Run from the repo root:
    ENVIRONMENT=test python3 -m pytest .claude/lib/tests/test_base_pin_drift_sweep.py -v
"""

from __future__ import annotations

import base64
import json
import subprocess
import sys
import unittest
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

import base_pin_drift_sweep as bpd  # noqa: E402

_NOW = datetime(2026, 8, 3, 12, 0, 0, tzinfo=timezone.utc)


def _gh_error() -> subprocess.CalledProcessError:
    return subprocess.CalledProcessError(1, ["gh"])


class FakeGh:
    """Injected `gh` runner: dispatches on substrings of the joined args."""

    def __init__(
        self, table: dict[str, object] | None = None, default_branch: str = "main"
    ) -> None:
        self.table = table or {}
        self.default_branch = default_branch
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str]) -> str:
        self.calls.append(args)
        joined = " ".join(args)
        if joined.endswith(".default_branch"):
            return self.default_branch + "\n"
        for needle, result in self.table.items():
            if needle in joined:
                if isinstance(result, Exception):
                    raise result
                return result  # type: ignore[return-value]
        raise AssertionError(f"unexpected gh call: {args}")


def _tree_json(paths: list[str]) -> str:
    return json.dumps({"tree": [{"path": p, "type": "blob"} for p in paths]})


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


class FakeHttp:
    """Injected HTTP GET double: dispatches by exact URL, raising or returning
    a canned `HttpResponse`."""

    def __init__(self, table: dict[str, object]) -> None:
        self.table = table
        self.calls: list[str] = []

    def __call__(self, url: str, headers: dict[str, str] | None = None) -> bpd.HttpResponse:
        self.calls.append(url)
        if url not in self.table:
            raise AssertionError(f"unexpected URL: {url}")
        result = self.table[url]
        if isinstance(result, Exception):
            raise result
        return result  # type: ignore[return-value]


def _resp(status: int, body: object, headers: dict[str, str] | None = None) -> bpd.HttpResponse:
    payload = json.dumps(body).encode("utf-8") if not isinstance(body, (bytes, str)) else body
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    return bpd.HttpResponse(status=status, headers=headers or {}, body=payload)


# --- parse_image_ref ---------------------------------------------------------


class ParseImageRefTests(unittest.TestCase):
    def test_docker_hub_official_image(self) -> None:
        ref = bpd.parse_image_ref("python:3.14-slim@sha256:" + "a" * 64)
        self.assertEqual(ref, ("docker.io", "library/python", "3.14-slim"))

    def test_docker_hub_no_tag_defaults_latest(self) -> None:
        ref = bpd.parse_image_ref("python@sha256:" + "a" * 64)
        self.assertEqual(ref, ("docker.io", "library/python", "latest"))

    def test_ghcr_namespaced_image(self) -> None:
        ref = bpd.parse_image_ref("ghcr.io/noorinalabs/foo:bar@sha256:" + "b" * 64)
        self.assertEqual(ref, ("ghcr.io", "noorinalabs/foo", "bar"))

    def test_gcr_distroless(self) -> None:
        ref = bpd.parse_image_ref("gcr.io/distroless/python3-debian12@sha256:" + "c" * 64)
        self.assertEqual(ref, ("gcr.io", "distroless/python3-debian12", "latest"))

    def test_unpinned_ref_returns_none(self) -> None:
        self.assertIsNone(bpd.parse_image_ref("python:3.14-slim"))

    def test_stage_reference_has_no_digest_returns_none(self) -> None:
        # A `FROM builder` stage reference never carries a digest.
        self.assertIsNone(bpd.parse_image_ref("builder"))

    def test_scratch_has_no_digest_returns_none(self) -> None:
        self.assertIsNone(bpd.parse_image_ref("scratch"))


# --- Dockerfile collection ----------------------------------------------------


class ListDockerfilePathsTests(unittest.TestCase):
    def test_filters_to_dockerfile_basenames(self) -> None:
        gh = FakeGh(
            table={
                "git/trees/main": _tree_json(
                    ["Dockerfile", "src/app.py", "integration-tests/Dockerfile.runner", "README.md"]
                )
            }
        )
        paths = bpd.list_repo_dockerfile_paths("noorinalabs", "repo-a", "main", run_gh=gh)
        self.assertEqual(paths, ["Dockerfile", "integration-tests/Dockerfile.runner"])

    def test_tree_fetch_failure_returns_none(self) -> None:
        gh = FakeGh(table={"git/trees/main": _gh_error()})
        self.assertIsNone(
            bpd.list_repo_dockerfile_paths("noorinalabs", "repo-a", "main", run_gh=gh)
        )

    def test_malformed_json_returns_none(self) -> None:
        gh = FakeGh(table={"git/trees/main": "not json"})
        self.assertIsNone(
            bpd.list_repo_dockerfile_paths("noorinalabs", "repo-a", "main", run_gh=gh)
        )

    def test_tree_not_a_list_returns_none(self) -> None:
        gh = FakeGh(table={"git/trees/main": json.dumps({"tree": "nope"})})
        self.assertIsNone(
            bpd.list_repo_dockerfile_paths("noorinalabs", "repo-a", "main", run_gh=gh)
        )


class FetchFileTextTests(unittest.TestCase):
    def test_decodes_base64_content(self) -> None:
        gh = FakeGh(table={"contents/Dockerfile": _b64("FROM python:3.14-slim\n")})
        text = bpd.fetch_file_text("noorinalabs", "repo-a", "Dockerfile", run_gh=gh)
        self.assertEqual(text, "FROM python:3.14-slim\n")

    def test_fetch_error_returns_none(self) -> None:
        gh = FakeGh(table={"contents/Dockerfile": _gh_error()})
        self.assertIsNone(bpd.fetch_file_text("noorinalabs", "repo-a", "Dockerfile", run_gh=gh))

    def test_bad_base64_returns_none(self) -> None:
        gh = FakeGh(table={"contents/Dockerfile": "!!!not-base64!!!"})
        self.assertIsNone(bpd.fetch_file_text("noorinalabs", "repo-a", "Dockerfile", run_gh=gh))


_DIGEST_A = "a" * 64
_DIGEST_B = "b" * 64


class CollectRepoPinsTests(unittest.TestCase):
    def test_collects_digest_pins_skips_unpinned_and_stage_refs(self) -> None:
        dockerfile = (
            f"FROM python:3.14-slim@sha256:{_DIGEST_A} AS builder\n"
            "RUN apt-get update && apt-get -y upgrade && apt-get clean\n"
            "FROM builder\n"
            f"FROM node:20-alpine@sha256:{_DIGEST_B}\n"
            "RUN apk upgrade --no-cache\n"
        )
        gh = FakeGh(
            table={
                "git/trees/main": _tree_json(["Dockerfile"]),
                "contents/Dockerfile": _b64(dockerfile),
            }
        )
        result = bpd.collect_repo_pins("noorinalabs", "repo-a", "main", run_gh=gh)
        assert result is not None
        self.assertEqual(len(result.pins), 2)
        self.assertEqual(result.pins[0].registry, "docker.io")
        self.assertEqual(result.pins[0].repository, "library/python")
        self.assertEqual(result.pins[1].repository, "library/node")
        self.assertEqual(result.fetch_failures, [])

    def test_tree_error_returns_none(self) -> None:
        gh = FakeGh(table={"git/trees/main": _gh_error()})
        self.assertIsNone(bpd.collect_repo_pins("noorinalabs", "repo-a", "main", run_gh=gh))

    def test_file_fetch_failure_recorded_not_dropped(self) -> None:
        gh = FakeGh(
            table={
                "git/trees/main": _tree_json(["Dockerfile"]),
                "contents/Dockerfile": _gh_error(),
            }
        )
        result = bpd.collect_repo_pins("noorinalabs", "repo-a", "main", run_gh=gh)
        assert result is not None
        self.assertEqual(result.pins, [])
        self.assertEqual(result.fetch_failures, ["Dockerfile"])


# --- WWW-Authenticate / bearer token -----------------------------------------


class WwwAuthenticateTests(unittest.TestCase):
    def test_parses_bearer_challenge(self) -> None:
        header = 'Bearer realm="https://auth.example/token",service="registry.example",scope="repository:x:pull"'
        self.assertEqual(
            bpd.parse_www_authenticate(header),
            {
                "realm": "https://auth.example/token",
                "service": "registry.example",
                "scope": "repository:x:pull",
            },
        )

    def test_non_bearer_scheme_returns_none(self) -> None:
        self.assertIsNone(bpd.parse_www_authenticate('Basic realm="x"'))

    def test_empty_header_returns_none(self) -> None:
        self.assertIsNone(bpd.parse_www_authenticate(""))


class GetBearerTokenTests(unittest.TestCase):
    def test_successful_token_exchange(self) -> None:
        http = FakeHttp({"https://auth.example/token?service=x": _resp(200, {"token": "tok123"})})
        token = bpd.get_bearer_token({"realm": "https://auth.example/token", "service": "x"}, http)
        self.assertEqual(token, "tok123")

    def test_missing_realm_returns_none(self) -> None:
        self.assertIsNone(bpd.get_bearer_token({"service": "x"}, FakeHttp({})))

    def test_non_200_returns_none(self) -> None:
        http = FakeHttp({"https://auth.example/token": _resp(500, {})})
        self.assertIsNone(bpd.get_bearer_token({"realm": "https://auth.example/token"}, http))

    def test_network_error_returns_none(self) -> None:
        http = FakeHttp({"https://auth.example/token": urllib.error.URLError("timeout")})
        self.assertIsNone(bpd.get_bearer_token({"realm": "https://auth.example/token"}, http))

    def test_malformed_json_returns_none(self) -> None:
        http = FakeHttp({"https://auth.example/token": _resp(200, "not-json-object", headers={})})
        # Force a non-JSON body.
        http.table["https://auth.example/token"] = bpd.HttpResponse(
            status=200, headers={}, body=b"not json at all"
        )
        self.assertIsNone(bpd.get_bearer_token({"realm": "https://auth.example/token"}, http))


class GetWithAuthTests(unittest.TestCase):
    def test_completes_challenge_and_retries_with_bearer(self) -> None:
        manifest_url = "https://registry-1.docker.io/v2/library/python/manifests/x"
        calls: list[dict[str, str]] = []

        def http(url: str, headers: dict[str, str] | None = None) -> bpd.HttpResponse:
            headers = headers or {}
            calls.append({"url": url, **headers})
            if url == manifest_url and "Authorization" not in headers:
                return bpd.HttpResponse(
                    status=401,
                    headers={
                        "Www-Authenticate": 'Bearer realm="https://auth.example/token",service="x"'
                    },
                    body=b"{}",
                )
            if url == "https://auth.example/token?service=x":
                return _resp(200, {"token": "tok123"})
            if url == manifest_url and headers.get("Authorization") == "Bearer tok123":
                return _resp(200, {"ok": True})
            raise AssertionError(f"unexpected call: {url} {headers}")

        resp = bpd._get_with_auth(manifest_url, "application/json", http)
        self.assertEqual(resp.status, 200)
        self.assertEqual(json.loads(resp.body), {"ok": True})

    def test_401_with_unparseable_challenge_returns_401_unchanged(self) -> None:
        http = FakeHttp({"https://reg/x": _resp(401, {}, headers={"Www-Authenticate": "Weird"})})
        resp = bpd._get_with_auth("https://reg/x", "application/json", http)
        self.assertEqual(resp.status, 401)

    def test_non_401_passes_through(self) -> None:
        http = FakeHttp({"https://reg/x": _resp(200, {"a": 1})})
        resp = bpd._get_with_auth("https://reg/x", "application/json", http)
        self.assertEqual(resp.status, 200)

    def test_lowercase_www_authenticate_header_still_completes_challenge(self) -> None:
        # Regression: Docker Hub's real 401 response (verified live against
        # registry-1.docker.io) sends an all-lowercase `www-authenticate`
        # header, not the `WWW-Authenticate` casing most examples show. A
        # case-SENSITIVE lookup here silently treats every Docker Hub pin as
        # an unauthenticated 401 `unknown` — this must not regress.
        manifest_url = "https://registry-1.docker.io/v2/library/python/manifests/x"

        def http(url: str, headers: dict[str, str] | None = None) -> bpd.HttpResponse:
            headers = headers or {}
            if url == manifest_url and "Authorization" not in headers:
                return bpd.HttpResponse(
                    status=401,
                    headers={
                        "www-authenticate": (
                            'Bearer realm="https://auth.example/token",service="x"'
                        )
                    },
                    body=b"{}",
                )
            if url == "https://auth.example/token?service=x":
                return _resp(200, {"token": "tok123"})
            if url == manifest_url and headers.get("Authorization") == "Bearer tok123":
                return _resp(200, {"ok": True})
            raise AssertionError(f"unexpected call: {url} {headers}")

        resp = bpd._get_with_auth(manifest_url, "application/json", http)
        self.assertEqual(resp.status, 200)


class FindHeaderTests(unittest.TestCase):
    def test_matches_regardless_of_case(self) -> None:
        self.assertEqual(
            bpd._find_header({"www-authenticate": "Bearer x"}, "WWW-Authenticate"), "Bearer x"
        )
        self.assertEqual(
            bpd._find_header({"WWW-AUTHENTICATE": "Bearer x"}, "www-authenticate"), "Bearer x"
        )

    def test_missing_header_returns_none(self) -> None:
        self.assertIsNone(bpd._find_header({}, "WWW-Authenticate"))


# --- resolve_created: degradation stance + happy paths -----------------------

_MANIFEST_URL = "https://registry-1.docker.io/v2/library/python/manifests/sha256:" + _DIGEST_A
_ARCH_URL = "https://registry-1.docker.io/v2/library/python/manifests/sha256:" + _DIGEST_B
_BLOB_URL = "https://registry-1.docker.io/v2/library/python/blobs/sha256:" + "c" * 64


class ResolveCreatedNetworkFailureTests(unittest.TestCase):
    def test_network_error_is_unknown(self) -> None:
        http = FakeHttp({_MANIFEST_URL: urllib.error.URLError("timeout")})
        outcome = bpd.resolve_created("docker.io", "library/python", "sha256:" + _DIGEST_A, http)
        self.assertEqual(outcome.status, "unknown")
        self.assertEqual(outcome.reason, "network_error")
        self.assertIsNone(outcome.created)

    def test_rate_limited_429_is_unknown_distinct_from_not_found(self) -> None:
        http = FakeHttp({_MANIFEST_URL: _resp(429, {})})
        outcome = bpd.resolve_created("docker.io", "library/python", "sha256:" + _DIGEST_A, http)
        self.assertEqual(outcome.status, "unknown")
        self.assertEqual(outcome.reason, "rate_limited")

    def test_not_found_404_is_unknown(self) -> None:
        http = FakeHttp({_MANIFEST_URL: _resp(404, {})})
        outcome = bpd.resolve_created("docker.io", "library/python", "sha256:" + _DIGEST_A, http)
        self.assertEqual(outcome.status, "unknown")
        self.assertEqual(outcome.reason, "not_found")

    def test_other_http_status_is_unknown_with_code(self) -> None:
        http = FakeHttp({_MANIFEST_URL: _resp(503, {})})
        outcome = bpd.resolve_created("docker.io", "library/python", "sha256:" + _DIGEST_A, http)
        self.assertEqual(outcome.status, "unknown")
        self.assertEqual(outcome.reason, "http_503")

    def test_malformed_manifest_json_is_unknown(self) -> None:
        http = FakeHttp({_MANIFEST_URL: bpd.HttpResponse(status=200, headers={}, body=b"not json")})
        outcome = bpd.resolve_created("docker.io", "library/python", "sha256:" + _DIGEST_A, http)
        self.assertEqual(outcome.status, "unknown")
        self.assertEqual(outcome.reason, "malformed")

    def test_manifest_not_a_json_object_is_unknown(self) -> None:
        http = FakeHttp({_MANIFEST_URL: _resp(200, [1, 2, 3])})
        outcome = bpd.resolve_created("docker.io", "library/python", "sha256:" + _DIGEST_A, http)
        self.assertEqual(outcome.status, "unknown")
        self.assertEqual(outcome.reason, "malformed")

    def test_manifest_list_missing_amd64_platform_is_unknown(self) -> None:
        http = FakeHttp(
            {
                _MANIFEST_URL: _resp(
                    200,
                    {
                        "manifests": [
                            {"platform": {"architecture": "arm64", "os": "linux"}, "digest": "x"}
                        ]
                    },
                )
            }
        )
        outcome = bpd.resolve_created("docker.io", "library/python", "sha256:" + _DIGEST_A, http)
        self.assertEqual(outcome.status, "unknown")
        self.assertEqual(outcome.reason, "no_amd64_platform")

    def test_arch_manifest_missing_config_is_malformed(self) -> None:
        http = FakeHttp(
            {
                _MANIFEST_URL: _resp(
                    200,
                    {
                        "manifests": [
                            {
                                "platform": {"architecture": "amd64", "os": "linux"},
                                "digest": "sha256:" + _DIGEST_B,
                            }
                        ]
                    },
                ),
                _ARCH_URL: _resp(200, {"no_config_key": True}),
            }
        )
        outcome = bpd.resolve_created("docker.io", "library/python", "sha256:" + _DIGEST_A, http)
        self.assertEqual(outcome.status, "unknown")
        self.assertEqual(outcome.reason, "malformed")

    def test_nested_manifest_list_is_malformed(self) -> None:
        # A "resolved" arch-specific manifest that is ITSELF still a list is
        # not a real single-arch manifest — must not be treated as one.
        http = FakeHttp(
            {
                _MANIFEST_URL: _resp(
                    200,
                    {
                        "manifests": [
                            {
                                "platform": {"architecture": "amd64", "os": "linux"},
                                "digest": "sha256:" + _DIGEST_B,
                            }
                        ]
                    },
                ),
                _ARCH_URL: _resp(200, {"manifests": []}),
            }
        )
        outcome = bpd.resolve_created("docker.io", "library/python", "sha256:" + _DIGEST_A, http)
        self.assertEqual(outcome.status, "unknown")
        self.assertEqual(outcome.reason, "malformed")

    def test_config_blob_fetch_failure_propagates_reason(self) -> None:
        http = FakeHttp(
            {
                _MANIFEST_URL: _resp(
                    200,
                    {
                        "manifests": [
                            {
                                "platform": {"architecture": "amd64", "os": "linux"},
                                "digest": "sha256:" + _DIGEST_B,
                            }
                        ]
                    },
                ),
                _ARCH_URL: _resp(200, {"config": {"digest": "sha256:" + "c" * 64}}),
                _BLOB_URL: _resp(429, {}),
            }
        )
        outcome = bpd.resolve_created("docker.io", "library/python", "sha256:" + _DIGEST_A, http)
        self.assertEqual(outcome.status, "unknown")
        self.assertEqual(outcome.reason, "rate_limited")

    def test_config_blob_missing_created_is_malformed(self) -> None:
        http = FakeHttp(
            {
                _MANIFEST_URL: _resp(
                    200,
                    {
                        "manifests": [
                            {
                                "platform": {"architecture": "amd64", "os": "linux"},
                                "digest": "sha256:" + _DIGEST_B,
                            }
                        ]
                    },
                ),
                _ARCH_URL: _resp(200, {"config": {"digest": "sha256:" + "c" * 64}}),
                _BLOB_URL: _resp(200, {"no_created": True}),
            }
        )
        outcome = bpd.resolve_created("docker.io", "library/python", "sha256:" + _DIGEST_A, http)
        self.assertEqual(outcome.status, "unknown")
        self.assertEqual(outcome.reason, "malformed")


class ResolveCreatedHappyPathTests(unittest.TestCase):
    def test_manifest_list_resolves_amd64_config_created(self) -> None:
        http = FakeHttp(
            {
                _MANIFEST_URL: _resp(
                    200,
                    {
                        "manifests": [
                            {
                                "platform": {"architecture": "arm64", "os": "linux"},
                                "digest": "sha256:" + "d" * 64,
                            },
                            {
                                "platform": {"architecture": "amd64", "os": "linux"},
                                "digest": "sha256:" + _DIGEST_B,
                            },
                        ]
                    },
                ),
                _ARCH_URL: _resp(200, {"config": {"digest": "sha256:" + "c" * 64}}),
                _BLOB_URL: _resp(200, {"created": "2026-07-14T02:07:16Z"}),
            }
        )
        outcome = bpd.resolve_created("docker.io", "library/python", "sha256:" + _DIGEST_A, http)
        self.assertEqual(outcome.status, "ok")
        self.assertEqual(outcome.created, "2026-07-14T02:07:16Z")
        self.assertIsNone(outcome.reason)

    def test_single_arch_manifest_resolves_directly(self) -> None:
        # No manifest-list hop at all — the pinned digest already IS the
        # single-arch manifest (e.g. a `docker pull --platform` pin).
        http = FakeHttp(
            {
                _MANIFEST_URL: _resp(200, {"config": {"digest": "sha256:" + "c" * 64}}),
                _BLOB_URL: _resp(200, {"created": "2026-06-11T00:00:00Z"}),
            }
        )
        outcome = bpd.resolve_created("docker.io", "library/python", "sha256:" + _DIGEST_A, http)
        self.assertEqual(outcome.status, "ok")
        self.assertEqual(outcome.created, "2026-06-11T00:00:00Z")

    def test_ghcr_uses_its_own_host_not_docker_hub(self) -> None:
        url = "https://ghcr.io/v2/noorinalabs/foo/manifests/sha256:" + _DIGEST_A
        blob_url = "https://ghcr.io/v2/noorinalabs/foo/blobs/sha256:" + "c" * 64
        http = FakeHttp(
            {
                url: _resp(200, {"config": {"digest": "sha256:" + "c" * 64}}),
                blob_url: _resp(200, {"created": "2026-07-01T00:00:00Z"}),
            }
        )
        outcome = bpd.resolve_created("ghcr.io", "noorinalabs/foo", "sha256:" + _DIGEST_A, http)
        self.assertEqual(outcome.status, "ok")
        self.assertEqual(outcome.created, "2026-07-01T00:00:00Z")


# --- compute_drift (pure) -----------------------------------------------------


def _pin(
    repo: str,
    path: str,
    lineno: int,
    key: tuple[str, str, str],
    digest: str,
    outcome: bpd.ResolveOutcome,
) -> bpd.ResolvedPin:
    registry, repository, tag = key
    return bpd.ResolvedPin(
        repo=repo,
        path=path,
        lineno=lineno,
        registry=registry,
        repository=repository,
        tag=tag,
        digest=digest,
        outcome=outcome,
    )


_KEY = ("docker.io", "library/python", "3.14-slim")


class ComputeDriftTests(unittest.TestCase):
    def test_cross_repo_drift_over_threshold_is_flagged(self) -> None:
        pins = [
            _pin(
                "repo-a",
                "Dockerfile",
                1,
                _KEY,
                "d1",
                bpd.ResolveOutcome("ok", "2026-06-11T00:00:00Z"),
            ),
            _pin(
                "repo-b",
                "Dockerfile",
                3,
                _KEY,
                "d2",
                bpd.ResolveOutcome("ok", "2026-07-14T00:00:00Z"),
            ),
        ]
        findings, unknown = bpd.compute_drift(pins, {}, cross_repo_threshold_days=30.0)
        self.assertEqual(unknown, [])
        (finding,) = findings
        self.assertEqual(finding.kind, "cross_repo")
        self.assertGreater(finding.days, 30.0)

    def test_cross_repo_drift_under_threshold_is_not_flagged(self) -> None:
        pins = [
            _pin(
                "repo-a",
                "Dockerfile",
                1,
                _KEY,
                "d1",
                bpd.ResolveOutcome("ok", "2026-07-01T00:00:00Z"),
            ),
            _pin(
                "repo-b",
                "Dockerfile",
                3,
                _KEY,
                "d2",
                bpd.ResolveOutcome("ok", "2026-07-10T00:00:00Z"),
            ),
        ]
        findings, unknown = bpd.compute_drift(pins, {}, cross_repo_threshold_days=30.0)
        self.assertEqual(findings, [])
        self.assertEqual(unknown, [])

    def test_cross_repo_drift_exactly_at_threshold_is_not_flagged(self) -> None:
        # Boundary: the comparison is strictly "> threshold", so a span EQUAL
        # to the threshold must NOT flag (pins `>=` here would be a
        # off-by-one that silently over-flags every exactly-at-policy pin).
        pins = [
            _pin(
                "repo-a",
                "Dockerfile",
                1,
                _KEY,
                "d1",
                bpd.ResolveOutcome("ok", "2026-06-01T00:00:00Z"),
            ),
            _pin(
                "repo-b",
                "Dockerfile",
                3,
                _KEY,
                "d2",
                bpd.ResolveOutcome("ok", "2026-07-01T00:00:00Z"),
            ),
        ]
        findings, unknown = bpd.compute_drift(pins, {}, cross_repo_threshold_days=30.0)
        self.assertEqual(findings, [])
        self.assertEqual(unknown, [])

    def test_single_pin_group_cannot_cross_repo_drift(self) -> None:
        pins = [
            _pin(
                "repo-a",
                "Dockerfile",
                1,
                _KEY,
                "d1",
                bpd.ResolveOutcome("ok", "2026-01-01T00:00:00Z"),
            )
        ]
        findings, unknown = bpd.compute_drift(pins, {}, cross_repo_threshold_days=30.0)
        self.assertEqual(findings, [])
        self.assertEqual(unknown, [])

    def test_behind_current_tag_over_threshold_is_flagged(self) -> None:
        pins = [
            _pin(
                "repo-a",
                "Dockerfile",
                1,
                _KEY,
                "d1",
                bpd.ResolveOutcome("ok", "2026-05-01T00:00:00Z"),
            )
        ]
        current = {bpd.image_key(*_KEY): bpd.ResolveOutcome("ok", "2026-07-18T00:00:00Z")}
        findings, unknown = bpd.compute_drift(pins, current, behind_tag_threshold_days=30.0)
        (finding,) = findings
        self.assertEqual(finding.kind, "behind_current_tag")
        self.assertEqual(unknown, [])

    def test_behind_current_tag_under_threshold_is_not_flagged(self) -> None:
        pins = [
            _pin(
                "repo-a",
                "Dockerfile",
                1,
                _KEY,
                "d1",
                bpd.ResolveOutcome("ok", "2026-07-10T00:00:00Z"),
            )
        ]
        current = {bpd.image_key(*_KEY): bpd.ResolveOutcome("ok", "2026-07-18T00:00:00Z")}
        findings, unknown = bpd.compute_drift(pins, current, behind_tag_threshold_days=30.0)
        self.assertEqual(findings, [])

    def test_behind_current_tag_exactly_at_threshold_is_not_flagged(self) -> None:
        # Boundary: same strict "> threshold" semantics as the cross-repo
        # comparison above — exactly-at-policy must not flag.
        pins = [
            _pin(
                "repo-a",
                "Dockerfile",
                1,
                _KEY,
                "d1",
                bpd.ResolveOutcome("ok", "2026-06-01T00:00:00Z"),
            )
        ]
        current = {bpd.image_key(*_KEY): bpd.ResolveOutcome("ok", "2026-07-01T00:00:00Z")}
        findings, unknown = bpd.compute_drift(pins, current, behind_tag_threshold_days=30.0)
        self.assertEqual(findings, [])

    def test_unresolved_pin_lands_in_unknown_not_silently_dropped(self) -> None:
        pins = [
            _pin(
                "repo-a",
                "Dockerfile",
                1,
                _KEY,
                "d1",
                bpd.ResolveOutcome("unknown", reason="rate_limited"),
            )
        ]
        findings, unknown = bpd.compute_drift(pins, {})
        self.assertEqual(findings, [])
        self.assertEqual(len(unknown), 1)
        self.assertEqual(unknown[0]["kind"], "pin")
        self.assertEqual(unknown[0]["reason"], "rate_limited")

    def test_unresolved_current_tag_lands_in_unknown(self) -> None:
        pins = [
            _pin(
                "repo-a",
                "Dockerfile",
                1,
                _KEY,
                "d1",
                bpd.ResolveOutcome("ok", "2026-07-01T00:00:00Z"),
            )
        ]
        current = {bpd.image_key(*_KEY): bpd.ResolveOutcome("unknown", reason="not_found")}
        findings, unknown = bpd.compute_drift(pins, current)
        self.assertEqual(findings, [])
        current_unknowns = [u for u in unknown if u["kind"] == "current_tag"]
        self.assertEqual(len(current_unknowns), 1)
        self.assertEqual(current_unknowns[0]["reason"], "not_found")

    def test_malformed_created_timestamp_is_excluded_from_dating_not_crashed(self) -> None:
        pins = [
            _pin(
                "repo-a", "Dockerfile", 1, _KEY, "d1", bpd.ResolveOutcome("ok", "garbage-timestamp")
            ),
            _pin(
                "repo-b",
                "Dockerfile",
                2,
                _KEY,
                "d2",
                bpd.ResolveOutcome("ok", "2026-07-01T00:00:00Z"),
            ),
        ]
        findings, unknown = bpd.compute_drift(pins, {})
        # Only one dateable pin remains -> no cross-repo comparison possible.
        self.assertEqual(findings, [])


# --- sweep() integration -------------------------------------------------------


class SweepIntegrationTests(unittest.TestCase):
    def test_default_branch_fetch_failure_falls_back_to_main(self) -> None:
        # The `.default_branch` gh call itself can fail (repo API hiccup,
        # distinct from the Dockerfile-tree call) — sweep() must still fall
        # back to "main" and proceed, not treat the whole repo as an error.
        def gh(args: list[str]) -> str:
            joined = " ".join(args)
            if joined.endswith(".default_branch"):
                raise _gh_error()
            if "git/trees/main" in joined:
                return _tree_json([])
            raise AssertionError(f"unexpected gh call: {args}")

        verdict = bpd.sweep(("repo-a",), run_gh=gh, http_get=FakeHttp({}), now=_NOW)
        self.assertEqual(verdict["repos_checked"], ["repo-a"])
        self.assertEqual(verdict["repos_errors"], [])

    def test_repo_collection_failure_lands_in_repos_errors(self) -> None:
        gh = FakeGh(table={"git/trees/main": _gh_error()})
        verdict = bpd.sweep(("repo-a",), run_gh=gh, http_get=FakeHttp({}), now=_NOW)
        self.assertEqual(verdict["repos_errors"], ["repo-a"])
        self.assertEqual(verdict["repos_checked"], [])
        self.assertEqual(verdict["findings"], [])

    def test_same_digest_across_two_repos_resolved_once(self) -> None:
        dockerfile = (
            f"FROM python:3.14-slim@sha256:{_DIGEST_A}\nRUN apt-get update && apt-get -y upgrade\n"
        )
        gh = FakeGh(
            table={
                "git/trees/main": _tree_json(["Dockerfile"]),
                "contents/Dockerfile": _b64(dockerfile),
            }
        )
        manifest_url = (
            f"https://registry-1.docker.io/v2/library/python/manifests/sha256:{_DIGEST_A}"
        )
        tag_url = "https://registry-1.docker.io/v2/library/python/manifests/3.14-slim"
        blob_url = "https://registry-1.docker.io/v2/library/python/blobs/sha256:" + "c" * 64
        http = FakeHttp(
            {
                manifest_url: _resp(200, {"config": {"digest": "sha256:" + "c" * 64}}),
                tag_url: _resp(200, {"config": {"digest": "sha256:" + "c" * 64}}),
                blob_url: _resp(200, {"created": "2026-07-01T00:00:00Z"}),
            }
        )
        verdict = bpd.sweep(("repo-a", "repo-b"), run_gh=gh, http_get=http, now=_NOW)
        self.assertEqual(verdict["pins_checked"], 2)
        # One resolve_created for the shared digest (manifest + blob = 2 calls)
        # and one resolve_created for the tag's current digest (manifest + blob
        # = 2 more) = 4 calls total, NOT 8 (one full pair per repo) — the
        # per-run memoization on (registry, repository, digest)/image_key is
        # doing its job across the two repos that pin the identical digest.
        self.assertEqual(len(http.calls), 4)

    def test_file_fetch_failure_surfaces_as_unknown(self) -> None:
        gh = FakeGh(
            table={
                "git/trees/main": _tree_json(["Dockerfile"]),
                "contents/Dockerfile": _gh_error(),
            }
        )
        verdict = bpd.sweep(("repo-a",), run_gh=gh, http_get=FakeHttp({}), now=_NOW)
        self.assertEqual(verdict["repos_checked"], ["repo-a"])
        file_unknowns = [u for u in verdict["unknown"] if u["kind"] == "file"]
        self.assertEqual(len(file_unknowns), 1)

    def test_registry_resolution_failure_reaches_persisted_verdict_and_render_check_warns(
        self,
    ) -> None:
        # The seam: compute_drift's `unknown` (registry-resolution failures)
        # is produced separately from sweep()'s own per-file `unknown`
        # entries and only reaches the persisted verdict via
        # `unknown.extend(drift_unknown)`. The existing
        # `test_file_fetch_failure_surfaces_as_unknown` only drives the
        # `kind=="file"` case, which is appended directly in sweep() and
        # never touches that join — it cannot catch the join being dropped.
        # Drive a REAL registry-resolution failure (both the pin's digest
        # manifest fetch and its tag's current-digest fetch 404) through
        # sweep() end-to-end, and confirm the resulting unknowns survive
        # into the persisted verdict AND into render_check's rendering.
        dockerfile = (
            f"FROM python:3.14-slim@sha256:{_DIGEST_A}\nRUN apt-get update && apt-get -y upgrade\n"
        )
        gh = FakeGh(
            table={
                "git/trees/main": _tree_json(["Dockerfile"]),
                "contents/Dockerfile": _b64(dockerfile),
            }
        )
        manifest_url = (
            f"https://registry-1.docker.io/v2/library/python/manifests/sha256:{_DIGEST_A}"
        )
        tag_url = "https://registry-1.docker.io/v2/library/python/manifests/3.14-slim"
        http = FakeHttp(
            {
                manifest_url: _resp(404, {}),
                tag_url: _resp(404, {}),
            }
        )
        verdict = bpd.sweep(("repo-a",), run_gh=gh, http_get=http, now=_NOW)
        self.assertEqual(verdict["repos_checked"], ["repo-a"])
        self.assertEqual(verdict["findings"], [])
        # compute_drift's registry-resolution-failure unknowns (kind "pin"
        # and "current_tag") must be present in the persisted verdict, not
        # just produced by compute_drift and then dropped on the floor.
        kinds = {u["kind"] for u in verdict["unknown"]}
        self.assertIn("pin", kinds)
        self.assertIn("current_tag", kinds)

        out = bpd.render_check(verdict, now=_NOW)
        self.assertIn("UNKNOWN, not clean", out)
        self.assertIn("not_found", out)

    def test_findings_join_reaches_verdict_with_custom_thresholds_and_renders(self) -> None:
        # The `findings` seam (flagged, deliberately left out of scope, by
        # the commit immediately above this one): `findings` reaches
        # sweep()'s returned verdict via a plain list comprehension in the
        # SAME return statement — not a separate append/extend like
        # `unknown` — and nothing previously drove a REAL finding through
        # sweep() end-to-end. That leaves three things unverified:
        #   1. the comprehension itself actually runs (a hardcoded
        #      `"findings": []` would look identical to a clean sweep),
        #   2. sweep()'s caller-supplied `*_threshold_days=` kwargs actually
        #      reach the compute_drift(...) call (rather than silently
        #      falling back to the module defaults), and
        #   3. compute_drift's producer dict shape (`detail`) matches what
        #      render_check's consumer side reads — compute_drift is unit
        #      tested against `DriftFinding` objects and render_check
        #      against hand-built dicts, so nothing previously compared the
        #      two directly.
        #
        # Two repos pin the SAME tag to differently-dated digests (15 days
        # apart -> a cross_repo finding), and the tag's current digest is
        # dated later still, 23 days past the OLDER pin but only 8 days past
        # the NEWER one -> exactly one behind_current_tag finding (for the
        # older pin only). Both dates clear a threshold of 10 but NEITHER
        # clears the module default of 30 — so a mutant that drops both
        # `*_threshold_days=` kwargs from the compute_drift(...) call would
        # silently fall back to the 30-day defaults and this test would see
        # an EMPTY findings list.
        pin_digest_a = "1" * 64
        pin_digest_b = "2" * 64
        config_digest_a = "a1" * 32
        config_digest_b = "b2" * 32
        config_digest_tag = "c3" * 32

        dockerfile_a = (
            f"FROM python:3.14-slim@sha256:{pin_digest_a}\n"
            "RUN apt-get update && apt-get -y upgrade\n"
        )
        dockerfile_b = (
            f"FROM python:3.14-slim@sha256:{pin_digest_b}\n"
            "RUN apt-get update && apt-get -y upgrade\n"
        )

        def gh(args: list[str]) -> str:
            joined = " ".join(args)
            if joined.endswith(".default_branch"):
                return "main\n"
            if "repo-a/git/trees/main" in joined:
                return _tree_json(["Dockerfile"])
            if "repo-b/git/trees/main" in joined:
                return _tree_json(["Dockerfile"])
            if "repo-a/contents/Dockerfile" in joined:
                return _b64(dockerfile_a)
            if "repo-b/contents/Dockerfile" in joined:
                return _b64(dockerfile_b)
            raise AssertionError(f"unexpected gh call: {args}")

        manifest_url_a = (
            f"https://registry-1.docker.io/v2/library/python/manifests/sha256:{pin_digest_a}"
        )
        manifest_url_b = (
            f"https://registry-1.docker.io/v2/library/python/manifests/sha256:{pin_digest_b}"
        )
        tag_url = "https://registry-1.docker.io/v2/library/python/manifests/3.14-slim"
        blob_url_a = (
            f"https://registry-1.docker.io/v2/library/python/blobs/sha256:{config_digest_a}"
        )
        blob_url_b = (
            f"https://registry-1.docker.io/v2/library/python/blobs/sha256:{config_digest_b}"
        )
        blob_url_tag = (
            f"https://registry-1.docker.io/v2/library/python/blobs/sha256:{config_digest_tag}"
        )

        http = FakeHttp(
            {
                manifest_url_a: _resp(200, {"config": {"digest": "sha256:" + config_digest_a}}),
                manifest_url_b: _resp(200, {"config": {"digest": "sha256:" + config_digest_b}}),
                tag_url: _resp(200, {"config": {"digest": "sha256:" + config_digest_tag}}),
                blob_url_a: _resp(200, {"created": "2026-06-01T00:00:00Z"}),
                blob_url_b: _resp(200, {"created": "2026-06-16T00:00:00Z"}),  # +15d vs A
                blob_url_tag: _resp(200, {"created": "2026-06-24T00:00:00Z"}),  # +23d/+8d
            }
        )

        verdict = bpd.sweep(
            ("repo-a", "repo-b"),
            run_gh=gh,
            http_get=http,
            now=_NOW,
            cross_repo_threshold_days=10.0,
            behind_tag_threshold_days=10.0,
        )

        findings = verdict["findings"]
        self.assertEqual(len(findings), 2)
        kinds = {f["kind"] for f in findings}
        self.assertEqual(kinds, {"cross_repo", "behind_current_tag"})

        by_kind = {f["kind"]: f for f in findings}
        cross_repo_detail = by_kind["cross_repo"]["detail"]
        behind_detail = by_kind["behind_current_tag"]["detail"]
        self.assertTrue(cross_repo_detail)
        self.assertTrue(behind_detail)

        # Feed the SAME verdict sweep() actually produced into render_check —
        # a mutant that renames the producer's `detail` key to `details`
        # would leave `findings` non-empty (so the assertions above would
        # still pass) while render_check's `item.get("detail")` silently
        # resolves to None: drift found, evidence lost. Asserting the real
        # detail text appears in the rendered report is what catches that.
        rendered = bpd.render_check(verdict, now=_NOW)
        self.assertIn(cross_repo_detail, rendered)
        self.assertIn(behind_detail, rendered)

    def test_checked_at_carries_injected_now(self) -> None:
        gh = FakeGh(table={"git/trees/main": _tree_json([])})
        verdict = bpd.sweep(("repo-a",), run_gh=gh, http_get=FakeHttp({}), now=_NOW)
        self.assertEqual(verdict["checked_at"], "2026-08-03T12:00:00Z")

    def test_cmd_sweep_exit_2_when_no_repos_checked(self) -> None:
        # sweep() itself is exit-code-agnostic; _cmd_sweep is what maps an
        # empty repos_checked to exit 2 (a fully-broken sweep must not persist
        # a quiet, misleadingly-empty-but-"successful" verdict).
        #
        # Patches `bpd.sweep` itself (a name `_cmd_sweep` looks up fresh at
        # CALL time, since it's an ordinary function call in its body) rather
        # than `bpd._run_gh`/`bpd.default_http_get` — those are captured as
        # bound DEFAULT ARGUMENT VALUES on `sweep`'s own signature at module
        # load time, so patching the module attributes after import does NOT
        # change what an unqualified `sweep(...)` call already resolved to;
        # a naive patch-and-call there would silently fall through to the
        # REAL `gh`/network path instead of the intended double.
        import argparse
        from unittest import mock

        args = argparse.Namespace(
            repos="repo-a",
            out=None,
            cross_repo_threshold_days=30.0,
            behind_tag_threshold_days=30.0,
        )
        empty_verdict = {
            "version": 1,
            "checked_at": "2026-08-03T00:00:00Z",
            "repos_checked": [],
            "repos_errors": ["repo-a"],
            "pins_checked": 0,
            "findings": [],
            "unknown": [],
        }
        with mock.patch.object(bpd, "sweep", return_value=empty_verdict) as mocked:
            code = bpd._cmd_sweep(args)
        mocked.assert_called_once()
        self.assertEqual(code, 2)

    def test_cmd_sweep_exit_0_when_a_repo_was_checked(self) -> None:
        import argparse
        from unittest import mock

        args = argparse.Namespace(
            repos="repo-a",
            out=None,
            cross_repo_threshold_days=30.0,
            behind_tag_threshold_days=30.0,
        )
        nonempty_verdict = {
            "version": 1,
            "checked_at": "2026-08-03T00:00:00Z",
            "repos_checked": ["repo-a"],
            "repos_errors": [],
            "pins_checked": 0,
            "findings": [],
            "unknown": [],
        }
        with mock.patch.object(bpd, "sweep", return_value=nonempty_verdict):
            code = bpd._cmd_sweep(args)
        self.assertEqual(code, 0)


# --- read_verdict / render_check / verdict_age_hours -------------------------


class ReadVerdictTests(unittest.TestCase):
    def test_round_trip_base64_content(self) -> None:
        verdict = {"version": 1, "checked_at": "2026-08-03T06:00:00Z", "findings": []}
        encoded = base64.b64encode(json.dumps(verdict).encode()).decode()
        wrapped = "\n".join(encoded[i : i + 60] for i in range(0, len(encoded), 60))

        def gh(args: list[str]) -> str:
            self.assertIn(bpd.META_REF, " ".join(args))
            return wrapped

        self.assertEqual(bpd.read_verdict(run_gh=gh), verdict)

    def test_missing_ref_returns_none(self) -> None:
        def gh(args: list[str]) -> str:
            raise _gh_error()

        self.assertIsNone(bpd.read_verdict(run_gh=gh))

    def test_corrupt_content_returns_none(self) -> None:
        self.assertIsNone(bpd.read_verdict(run_gh=lambda a: "not-base64-json!"))


class RenderCheckTests(unittest.TestCase):
    def _fresh(self, **overrides: object) -> dict:
        verdict: dict = {
            "version": 1,
            "checked_at": bpd._iso(_NOW - timedelta(hours=3)),
            "repos_checked": ["repo-a"],
            "repos_errors": [],
            "pins_checked": 1,
            "findings": [],
            "unknown": [],
        }
        verdict.update(overrides)
        return verdict

    def test_missing_verdict_is_warning_never_clean(self) -> None:
        out = bpd.render_check(None, now=_NOW)
        self.assertIn("WARNING", out)
        self.assertIn("UNKNOWN", out)
        self.assertNotIn("No base-image pin drift", out)

    def test_stale_verdict_is_warning_never_clean(self) -> None:
        stale = self._fresh(checked_at=bpd._iso(_NOW - timedelta(hours=60)))
        out = bpd.render_check(stale, now=_NOW)
        self.assertIn("WARNING", out)
        self.assertIn("STALE", out)
        self.assertNotIn("No base-image pin drift", out)

    def test_unparseable_timestamp_is_warning(self) -> None:
        out = bpd.render_check(self._fresh(checked_at="garbage"), now=_NOW)
        self.assertIn("WARNING", out)
        self.assertIn("STALE", out)

    def test_verdict_exactly_at_max_age_is_not_stale(self) -> None:
        # Boundary: staleness is strictly "age > max_age_hours" (mirrors
        # red_sweep's own strict-greater-than staleness comparison) — a
        # verdict exactly `max_age_hours` old must still be trusted.
        verdict = self._fresh(checked_at=bpd._iso(_NOW - timedelta(hours=48)))
        out = bpd.render_check(verdict, now=_NOW, max_age_hours=48.0)
        self.assertNotIn("STALE", out)
        self.assertIn("No base-image pin drift over threshold", out)

    def test_fresh_clean_reports_no_drift_with_timestamp(self) -> None:
        verdict = self._fresh()
        out = bpd.render_check(verdict, now=_NOW)
        self.assertIn("No base-image pin drift over threshold", out)
        self.assertIn(verdict["checked_at"], out)

    def test_fresh_with_findings_lists_them(self) -> None:
        verdict = self._fresh(
            findings=[
                {
                    "kind": "cross_repo",
                    "image_key": "docker.io/library/python:3.14-slim",
                    "detail": "repo-a pinned 2026-06-11 vs repo-b pinned 2026-07-14",
                    "days": 33.0,
                }
            ]
        )
        out = bpd.render_check(verdict, now=_NOW)
        self.assertIn("Base-image pin DRIFT found", out)
        self.assertIn("docker.io/library/python:3.14-slim", out)

    def test_unknown_entries_never_read_as_clean(self) -> None:
        verdict = self._fresh(unknown=[{"kind": "pin", "reason": "rate_limited"}])
        out = bpd.render_check(verdict, now=_NOW)
        self.assertIn("No base-image pin drift over threshold", out)  # findings empty
        self.assertIn("UNKNOWN, not clean", out)  # but NOT reported as all-clean

    def test_repos_errors_reported_as_unknown(self) -> None:
        out = bpd.render_check(self._fresh(repos_errors=["repo-b"]), now=_NOW)
        self.assertIn("repo-b", out)
        self.assertIn("UNKNOWN, not clean", out)


class VerdictAgeTests(unittest.TestCase):
    def test_age_hours(self) -> None:
        verdict = {"checked_at": bpd._iso(_NOW - timedelta(hours=6))}
        age = bpd.verdict_age_hours(verdict, now=_NOW)
        assert age is not None
        self.assertAlmostEqual(age, 6.0, places=3)

    def test_unparseable_returns_none(self) -> None:
        self.assertIsNone(bpd.verdict_age_hours({"checked_at": "nope"}, now=_NOW))


if __name__ == "__main__":
    unittest.main()
