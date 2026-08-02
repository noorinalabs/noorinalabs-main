#!/usr/bin/env python3
"""Sensor for `gh`'s two independent API quotas — `core` (REST) and `graphql` (#1224).

Promotes `feedback_gh_cli_gotchas` §12 (`.claude/memory/feedback_gh_cli_gotchas.md`)
from a memory note to enforcement tooling. §12's load-bearing facts, re-measured
live for this module (graphql=0/5000, core~4986/5000, 2026-08-02):

  - `core` and `graphql` drain INDEPENDENTLY — REST can sit near-full while
    GraphQL is flat zero, or vice versa.
  - GraphQL exhaustion is a SILENT ZERO, not a raised error: the failing `gh`
    call exits non-zero with the bare string
    `GraphQL: API rate limit already exceeded for user ID <n>`, which a
    customary `2>/dev/null` (or a `jq` parse over it) turns into an
    indistinguishable-from-empty result. This module exists so a caller asks
    the quota FIRST, instead of inferring exhaustion from a suspiciously empty
    read.
  - `gh api rate_limit` itself costs NO quota (measured: calling it in a loop
    does not move `.resources.core.remaining`) — the sensor is free to poll.

Degrade-to-ALLOW is the safety direction (design requirement, #1224 issue body)
======================================================================
A quota CHECK failing (network down, `gh` missing, a malformed/truncated
response) must never be interpreted as "0 remaining" — that would let a
sensor outage wedge every `gh` call in the session, trading a slowdown for a
hard stop nobody asked for. Every function in this module that can fail
returns `None` (Python's "unknown") rather than a zeroed reading, and the one
consumer that makes a block/allow decision (`gh_quota_gate.py`, the PreToolUse
hook) treats `None` as "assume available."

Caching (why, and why it's this shape)
=======================================
A PreToolUse hook fires on every Bash call in the session; hitting the
network on each one would be both slow and itself a (free, but non-zero
latency) quota-consuming round trip on the hot path. `get_quota()` caches the
last successful reading under `.claude/.consulted/gh_quota/cache.json`
(the existing gitignored `.claude/.consulted/<name>/` convention — see
`ontology-librarian`'s consultation sentinel) for `ttl` seconds (default 30).
A cache read that is fresh enough is returned without a subprocess call at
all; a stale-or-absent cache triggers exactly one fetch. If that fetch fails,
a stale cache entry is still preferred over nothing (staleness only ever
WIDENS the safety margin — a rate limit that has just reset earlier than the
stale entry knew is the FAIL-SAFE direction; a wider window that has since
tightened is the risk the hook's cheap-recheck-on-block path covers).

CLI
===
    python3 .claude/lib/gh_quota.py check [--json]
        Report remaining/limit/seconds-to-reset for both resources.

    python3 .claude/lib/gh_quota.py guard --resource {core,graphql} --min N [--json]
        Exit 0 (allow) when the resource has >= N remaining OR the reading is
        unknown (degrade-to-allow); exit 1 (deplete) when remaining < N.

Exit codes (guard):
    0 — allow (quota sufficient, or unknown — degrade to allow)
    1 — deplete (quota below --min)
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import subprocess
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CACHE_DIR = REPO_ROOT / ".claude" / ".consulted" / "gh_quota"
CACHE_FILE = CACHE_DIR / "cache.json"

DEFAULT_TTL_SECONDS = 30
RATE_LIMIT_TIMEOUT_SECONDS = 5

# The two resources this org's `gh` usage actually depends on. `rate_limit`
# reports more (search, code_search, ...); we only track what we gate on.
RESOURCES = ("core", "graphql")


@dataclasses.dataclass(frozen=True)
class ResourceQuota:
    """One resource's reading from `gh api rate_limit` at a point in time."""

    resource: str
    remaining: int
    limit: int
    reset_epoch: int

    def seconds_to_reset(self, now: float | None = None) -> int:
        now = time.time() if now is None else now
        return max(0, int(self.reset_epoch - now))

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def fetch_rate_limit(timeout: int = RATE_LIMIT_TIMEOUT_SECONDS) -> dict[str, ResourceQuota] | None:
    """Call `gh api rate_limit` fresh. Costs no quota (measured, module docstring).

    Returns None on ANY failure — missing `gh` binary, network error, timeout,
    non-zero exit, or a response that doesn't parse into the expected shape.
    Never raises: a sensor that can crash the caller is worse than one that
    reports "unknown." Callers MUST treat None as "unknown, assume available",
    never as "zero remaining."
    """
    try:
        result = subprocess.run(
            ["gh", "api", "rate_limit"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    if result.returncode != 0:
        return None
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    resources = data.get("resources")
    if not isinstance(resources, dict):
        return None

    out: dict[str, ResourceQuota] = {}
    for name in RESOURCES:
        entry = resources.get(name)
        if not isinstance(entry, dict):
            continue
        try:
            out[name] = ResourceQuota(
                resource=name,
                remaining=int(entry["remaining"]),
                limit=int(entry["limit"]),
                reset_epoch=int(entry["reset"]),
            )
        except (KeyError, TypeError, ValueError):
            continue
    return out or None


def _read_cache(cache_file: Path) -> tuple[float, dict[str, ResourceQuota]] | None:
    """Best-effort cache read. Any corruption/absence is a plain None, not an error."""
    try:
        raw = json.loads(cache_file.read_text(encoding="utf-8"))
        fetched_at = float(raw["fetched_at"])
        resources = {name: ResourceQuota(**entry) for name, entry in raw["resources"].items()}
        return fetched_at, resources
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _write_cache(resources: dict[str, ResourceQuota], cache_file: Path) -> None:
    """Best-effort cache write. The cache is an optimization — never load-bearing."""
    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "fetched_at": time.time(),
            "resources": {name: r.to_dict() for name, r in resources.items()},
        }
        cache_file.write_text(json.dumps(payload), encoding="utf-8")
    except OSError:
        pass


def get_quota(
    *,
    ttl: int = DEFAULT_TTL_SECONDS,
    cache_file: Path = CACHE_FILE,
    now: float | None = None,
) -> dict[str, ResourceQuota] | None:
    """Cached quota reading. Fresh fetch on a stale/absent/corrupt cache.

    Returns None only when there is NEITHER a fresh-enough cache entry NOR a
    successful live fetch NOR any usable stale cache — i.e. genuinely unknown
    (first run, `gh` unreachable, cache directory unwritable AND unreadable).
    Callers must treat None as "unknown, assume available" (module docstring
    § Degrade-to-ALLOW), never as a zeroed reading.
    """
    now = time.time() if now is None else now
    cached = _read_cache(cache_file)
    if cached is not None:
        fetched_at, resources = cached
        if now - fetched_at < ttl:
            return resources

    fresh = fetch_rate_limit()
    if fresh is not None:
        _write_cache(fresh, cache_file)
        return fresh

    # Fetch failed: prefer a stale cache entry over nothing. Staleness only
    # ever widens the safety margin here — see module docstring § Caching.
    if cached is not None:
        return cached[1]
    return None


def resource_quota(
    resource: str,
    *,
    ttl: int = DEFAULT_TTL_SECONDS,
    cache_file: Path = CACHE_FILE,
    now: float | None = None,
) -> ResourceQuota | None:
    """Convenience: the single named resource's reading, or None if unknown."""
    quotas = get_quota(ttl=ttl, cache_file=cache_file, now=now)
    if quotas is None:
        return None
    return quotas.get(resource)


# --------------------------------------------------------------------------- CLI


def _render_check_text(quotas: dict[str, ResourceQuota] | None) -> str:
    if quotas is None:
        return "gh_quota: UNKNOWN — could not read rate_limit (offline, gh missing, or malformed)."
    lines = []
    for name in RESOURCES:
        q = quotas.get(name)
        if q is None:
            lines.append(f"  {name}: UNKNOWN")
            continue
        lines.append(
            f"  {name}: {q.remaining}/{q.limit} remaining "
            f"(resets in {q.seconds_to_reset()}s, at epoch {q.reset_epoch})"
        )
    return "gh_quota check:\n" + "\n".join(lines)


def _render_check_json(quotas: dict[str, ResourceQuota] | None) -> str:
    if quotas is None:
        return json.dumps({"unknown": True}, indent=2, sort_keys=True)
    payload = {name: (q.to_dict() if q is not None else None) for name, q in quotas.items()}
    return json.dumps(payload, indent=2, sort_keys=True)


def _cmd_check(args: argparse.Namespace) -> int:
    quotas = get_quota(ttl=args.ttl)
    print(_render_check_json(quotas) if args.json else _render_check_text(quotas))
    return 0


def _cmd_guard(args: argparse.Namespace) -> int:
    q = resource_quota(args.resource, ttl=args.ttl)
    if q is None:
        msg = f"gh_quota guard: {args.resource} quota UNKNOWN — degrading to ALLOW."
        if args.json:
            print(json.dumps({"resource": args.resource, "known": False, "allow": True}))
        else:
            print(msg)
        return 0
    allow = q.remaining >= args.min
    if args.json:
        print(
            json.dumps(
                {
                    "resource": args.resource,
                    "known": True,
                    "remaining": q.remaining,
                    "limit": q.limit,
                    "min": args.min,
                    "allow": allow,
                    "seconds_to_reset": q.seconds_to_reset(),
                }
            )
        )
    else:
        verdict = "ALLOW" if allow else "DEPLETE"
        print(
            f"gh_quota guard: {args.resource} {q.remaining}/{q.limit} "
            f"(min {args.min}) -> {verdict} (resets in {q.seconds_to_reset()}s)"
        )
    return 0 if allow else 1


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="gh_quota",
        description="Sensor for gh's core/graphql rate-limit quotas (#1224). "
        "Never itself consumes quota; degrades to 'unknown' on any failure.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    p_check = sub.add_parser("check", help="report both resources' remaining/limit/reset")
    p_check.add_argument("--json", action="store_true")
    p_check.add_argument("--ttl", type=int, default=DEFAULT_TTL_SECONDS)
    p_check.set_defaults(func=_cmd_check)

    p_guard = sub.add_parser(
        "guard", help="exit 0 (allow) if remaining>=min or unknown; exit 1 (deplete) otherwise"
    )
    p_guard.add_argument("--resource", choices=RESOURCES, required=True)
    p_guard.add_argument("--min", type=int, required=True)
    p_guard.add_argument("--json", action="store_true")
    p_guard.add_argument("--ttl", type=int, default=DEFAULT_TTL_SECONDS)
    p_guard.set_defaults(func=_cmd_guard)

    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
