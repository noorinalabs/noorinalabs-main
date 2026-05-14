#!/usr/bin/env python3
"""Apply branch-protection settings to noorinalabs org repos.

Driven by `.claude/scripts/branch_protection_config.json`. The manifest's
`_common` block holds the protections that apply to every repo; each entry in
`repos` adds the per-repo `required_status_checks` (or null to skip required
checks for that repo). PUT requests are issued via `gh api` so the caller's
existing GitHub auth is reused — no PAT plumbing.

The PUT body for the GitHub REST API requires EVERY top-level key (see
https://docs.github.com/rest/branches/branch-protection#update-branch-protection).
Omitting a key is treated by the API as "clear that setting". This script
always sends the full schema so applying twice is idempotent.

Modes:
    --check     read-only. Compare manifest to live state, print a diff. Exit 0
                if everything matches, exit 1 if drift is found, exit 2 on
                hard error (network, auth, manifest schema). Suitable for CI.
    --apply     PUT the manifest to each repo, then GET to verify. Exit 0 only
                if every repo's post-state matches the desired state.
    --repo NAME limit operation to a single repo (matches manifest key).
    --owner OWN override the default `noorinalabs` org.

Acceptance evidence: every repo's POST-state JSON is captured in
`/tmp/apply_branch_protection_post_{repo}.json` and diffed against the
manifest. The script exits non-zero on ANY drift, so CI can gate.

PR-time vs runtime testing
==========================

This script's unit-mechanic correctness — diff computation, request body
shape, idempotency — is covered by tests in `test_apply_branch_protection.py`
(no network). The actual `gh api PUT` calls can ONLY be exercised against
real org repos, so the post-merge Test Plan applies the manifest in real life
and reads back the state. PR reviewers should NOT block on "did this run on
real repos?" — that is the runtime acceptance, separately tracked.

Issue: noorinalabs/noorinalabs-main#403
Anchors: #182 (single-repo case), #222 (org-wide audit)
"""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
from pathlib import Path

DEFAULT_OWNER = "noorinalabs"
DEFAULT_MANIFEST = Path(__file__).parent / "branch_protection_config.json"
DEFAULT_BRANCH = "main"

# Keys we send in every PUT body. The GitHub API requires the full schema —
# omitting a key clears it. We render `null` for fields that should be cleared
# explicitly (required_pull_request_reviews=null, restrictions=null).
_REQUIRED_PUT_KEYS = (
    "required_status_checks",
    "enforce_admins",
    "required_pull_request_reviews",
    "restrictions",
    "allow_force_pushes",
    "allow_deletions",
    "required_linear_history",
    "required_conversation_resolution",
)


class BranchProtectionError(Exception):
    """Raised for manifest schema errors or unrecoverable API failures."""


def load_manifest(path: Path) -> dict:
    if not path.exists():
        raise BranchProtectionError(f"Manifest not found: {path}")
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise BranchProtectionError(f"Manifest is not valid JSON: {e}") from e

    if "_common" not in data or "repos" not in data:
        raise BranchProtectionError("Manifest must have '_common' and 'repos' keys")
    if not isinstance(data["repos"], dict) or not data["repos"]:
        raise BranchProtectionError("Manifest 'repos' must be a non-empty object")
    return data


def build_desired_for_repo(manifest: dict, repo: str) -> dict:
    """Return the PUT body that should be applied to `repo`.

    Merges `_common` defaults with per-repo override. Strips comment keys
    (those starting with `_`) so they don't get sent to GitHub.
    """
    if repo not in manifest["repos"]:
        raise BranchProtectionError(f"Repo {repo!r} not in manifest")

    desired = copy.deepcopy(manifest["_common"])
    per_repo = manifest["repos"][repo]
    for k, v in per_repo.items():
        if k.startswith("_"):
            continue
        desired[k] = v

    # Strip leftover comment keys from _common defensively.
    for k in list(desired.keys()):
        if k.startswith("_"):
            del desired[k]

    # Validate every required PUT key is present (avoid implicit clears).
    missing = [k for k in _REQUIRED_PUT_KEYS if k not in desired]
    if missing:
        raise BranchProtectionError(
            f"Manifest for {repo!r} is missing required PUT keys: {missing}"
        )
    return desired


def fetch_actual(owner: str, repo: str, branch: str = DEFAULT_BRANCH) -> dict | None:
    """Return the live protection state, or None if the branch is unprotected."""
    proc = subprocess.run(
        ["gh", "api", f"repos/{owner}/{repo}/branches/{branch}/protection"],
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0:
        return json.loads(proc.stdout)
    # 404 = unprotected, treat as None. Distinguish from other failures.
    if "Branch not protected" in proc.stderr or "404" in proc.stderr:
        return None
    raise BranchProtectionError(
        f"GET {owner}/{repo}/branches/{branch}/protection failed:\n{proc.stderr.strip()}"
    )


def normalize_actual(actual: dict | None) -> dict:
    """Reduce the GET response to the same shape as the PUT body.

    The GET response wraps booleans in `{"enabled": bool, ...}` and adds URL
    fields and `checks` for status checks; the PUT body is flat. This function
    normalizes the GET to the PUT shape so a structural diff makes sense.
    """
    if actual is None:
        return {k: None for k in _REQUIRED_PUT_KEYS}

    norm: dict = {}

    rsc = actual.get("required_status_checks")
    if rsc is None:
        norm["required_status_checks"] = None
    else:
        norm["required_status_checks"] = {
            "strict": bool(rsc.get("strict", False)),
            "contexts": list(rsc.get("contexts", [])),
        }

    def _enabled(key: str) -> bool:
        node = actual.get(key)
        if isinstance(node, dict):
            return bool(node.get("enabled", False))
        return bool(node)

    norm["enforce_admins"] = _enabled("enforce_admins")
    norm["allow_force_pushes"] = _enabled("allow_force_pushes")
    norm["allow_deletions"] = _enabled("allow_deletions")
    norm["required_linear_history"] = _enabled("required_linear_history")
    norm["required_conversation_resolution"] = _enabled("required_conversation_resolution")

    rpr = actual.get("required_pull_request_reviews")
    if rpr:
        norm["required_pull_request_reviews"] = {
            "required_approving_review_count": int(rpr.get("required_approving_review_count", 0)),
            "dismiss_stale_reviews": bool(rpr.get("dismiss_stale_reviews", False)),
            "require_code_owner_reviews": bool(rpr.get("require_code_owner_reviews", False)),
            "require_last_push_approval": bool(rpr.get("require_last_push_approval", False)),
        }
    else:
        norm["required_pull_request_reviews"] = None

    restrictions = actual.get("restrictions")
    norm["restrictions"] = restrictions if restrictions else None

    return norm


def diff_state(desired: dict, actual_norm: dict) -> list[str]:
    """Return a list of human-readable drift lines (empty == in sync)."""
    drift = []
    for key in _REQUIRED_PUT_KEYS:
        d = desired.get(key)
        a = actual_norm.get(key)
        if d != a:
            drift.append(f"  {key}:\n    desired={d!r}\n    actual ={a!r}")
    return drift


def put_protection(owner: str, repo: str, body: dict, branch: str = DEFAULT_BRANCH) -> dict:
    """PUT the desired protection state and return the parsed response."""
    body_json = json.dumps(body)
    proc = subprocess.run(
        [
            "gh",
            "api",
            "-X",
            "PUT",
            f"repos/{owner}/{repo}/branches/{branch}/protection",
            "--input",
            "-",
        ],
        input=body_json,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise BranchProtectionError(
            f"PUT {owner}/{repo}/branches/{branch}/protection failed:\n{proc.stderr.strip()}"
        )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise BranchProtectionError(
            f"PUT {owner}/{repo}/branches/{branch}/protection returned non-JSON: {e}"
        ) from e


def run_check(owner: str, manifest: dict, repos: list[str]) -> int:
    """Read-only drift check. Exit 0 if in sync, 1 if drift, 2 on hard error."""
    any_drift = False
    for repo in repos:
        desired = build_desired_for_repo(manifest, repo)
        try:
            actual = fetch_actual(owner, repo)
        except BranchProtectionError as e:
            print(f"[{repo}] ERROR: {e}", file=sys.stderr)
            return 2
        actual_norm = normalize_actual(actual)
        drift = diff_state(desired, actual_norm)
        if drift:
            any_drift = True
            print(f"[{repo}] DRIFT:")
            print("\n".join(drift))
        else:
            print(f"[{repo}] in sync")
    return 1 if any_drift else 0


def run_apply(owner: str, manifest: dict, repos: list[str]) -> int:
    """Apply manifest + read back for verification. Exit 0 only on full success."""
    any_failure = False
    for repo in repos:
        desired = build_desired_for_repo(manifest, repo)
        print(f"[{repo}] applying ...")
        try:
            put_protection(owner, repo, desired)
            actual = fetch_actual(owner, repo)
        except BranchProtectionError as e:
            print(f"[{repo}] ERROR: {e}", file=sys.stderr)
            any_failure = True
            continue
        actual_norm = normalize_actual(actual)
        post_path = Path(f"/tmp/apply_branch_protection_post_{repo}.json")
        post_path.write_text(json.dumps(actual_norm, indent=2, sort_keys=True))
        drift = diff_state(desired, actual_norm)
        if drift:
            any_failure = True
            print(f"[{repo}] POST-STATE DRIFT (manifest != GitHub after PUT):")
            print("\n".join(drift))
        else:
            print(f"[{repo}] applied + verified")
    return 1 if any_failure else 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Read-only drift check.")
    mode.add_argument("--apply", action="store_true", help="PUT manifest + verify.")
    p.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    p.add_argument("--owner", default=DEFAULT_OWNER)
    p.add_argument("--repo", help="Limit to one repo (manifest key).")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    try:
        manifest = load_manifest(args.manifest)
    except BranchProtectionError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    if args.repo:
        if args.repo not in manifest["repos"]:
            print(f"ERROR: repo {args.repo!r} not in manifest", file=sys.stderr)
            return 2
        repos = [args.repo]
    else:
        repos = list(manifest["repos"].keys())

    if args.check:
        return run_check(args.owner, manifest, repos)
    return run_apply(args.owner, manifest, repos)


if __name__ == "__main__":
    sys.exit(main())
