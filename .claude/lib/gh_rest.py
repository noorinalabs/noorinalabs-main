#!/usr/bin/env python3
"""REST fallbacks for the `gh` read/write surfaces that fail under GraphQL exhaustion (#1224).

Companion to `.claude/lib/gh_quota.py` (the sensor). Every function here is a
REST (`gh api`) equivalent of a GraphQL-backed `gh` ergonomic command
(`gh issue view --json`, `gh pr view --json`, `gh project item-add`, ...),
returning the SAME shape the `--json` form would so a call site needs no
reshaping when it switches over. Promotes `feedback_gh_cli_gotchas` §12.

Never masks a real failure as an empty result
==============================================
The whole point of this module is to replace a silent zero (§12: GraphQL
exhaustion returns a bare, unparseable error string that a `2>/dev/null` turns
into "empty") with something a caller can trust. So every function here
raises `GhRestError` on a genuine failure (non-zero `gh` exit, malformed
JSON) rather than returning `[]`/`{}` — an empty LIST return here means "the
API returned zero items," never "the call failed and we couldn't tell."

Two traps pinned by test (measured live, 2026-08-02, `feedback_gh_cli_gotchas.md` §12)
========================================================================================
1. **`repos/{o}/{r}/issues` returns pull requests too.** A PR is an issue as
   far as this endpoint is concerned; every list/view function here filters
   `pull_request is None` (or routes PR numbers to `pr_view`) — the exact bug
   that read 57 where the true issue count was 50.
2. **Pagination.** Every list-shaped fetch here uses `gh api ... --paginate`
   (verified live: `--paginate --jq '.[] | ...'` emits one compact JSON
   object per line across every page, not one big page-1-only array) so a
   >100-item result is never silently truncated — sibling of the
   `item-list --limit` trap already in §12.

Repo/owner resolution
======================
Every function takes an optional `repo="OWNER/NAME"`. When omitted, the REST
path is built with `gh`'s own `:owner`/`:repo` placeholder syntax
(`repos/:owner/:repo/...`), which `gh api` resolves from the invocation cwd's
git remote — the same resolution `gh issue view` (no `--repo`) does. Pass
`repo` explicitly for any cross-repo call (per the `feedback_gh_cli_gotchas`
§6 "bare numbers resolve against cwd" trap, which applies here too).

`gh project item-add` HAS a REST equivalent — this corrects the #1224 issue body
==================================================================================
The issue that requested this module states board writes are "GraphQL-only
with no REST equivalent." That was true when §12 was written but is NOT true
today: GitHub now documents (and this module verified LIVE, 2026-08-02, by
actually adding #1224 to project board 2 through it —
`docs.github.com/rest/projects/items#add-item-to-organization-owned-project`)
a REST endpoint for adding an item to an ORG-OWNED ProjectV2 board:

    POST orgs/{org}/projectsV2/{project_number}/items
    body: {"type": "Issue" | "PullRequest", "id": <content's REST database id>}

`id` is the ISSUE/PR's REST `id` field (a numeric database id — NOT the issue
`number`, NOT the GraphQL `node_id`). `project_item_add()` below resolves it
for the caller. `project_items()` / `issue_project_membership()` are the read
side (there is, separately, no REST endpoint to filter items server-side by
content — the read fallback still pages the whole board and filters client
-side, same O(n) shape as `gh project item-list`, just over REST instead of
GraphQL). `gh` the CLI tool has NOT been updated to use this endpoint (`gh
project item-add` is still GraphQL-backed and still fails under exhaustion,
per §12) — this module is the fallback for exactly that gap.

The one operation that remains genuinely unsupported over REST is querying a
*classic* Projects board — that API was fully removed (`gh api
orgs/{org}/projects` -> 404, verified live). `GhRestUnsupportedError` exists
for that shape and any future case with no working equivalent; callers that
hit it get a clear message rather than a silent failure.

CLI
===
    python3 .claude/lib/gh_rest.py issue view <N> [--repo O/R]
    python3 .claude/lib/gh_rest.py issue list [--repo O/R] [--label L] [--state open|closed|all]
    python3 .claude/lib/gh_rest.py pr view <N> [--repo O/R]
    python3 .claude/lib/gh_rest.py pr comments <N> [--repo O/R]
    python3 .claude/lib/gh_rest.py pr checks <SHA> [--repo O/R]
    python3 .claude/lib/gh_rest.py issue timeline <N> [--repo O/R]
    python3 .claude/lib/gh_rest.py comment write-payload --file F --body-file B
    python3 .claude/lib/gh_rest.py comment post <N> --file F [--repo O/R]
    python3 .claude/lib/gh_rest.py project add <N> --org ORG --project P [--repo O/R]
    python3 .claude/lib/gh_rest.py project items --org ORG --project P
    python3 .claude/lib/gh_rest.py project membership <N> --org ORG --project P [--repo O/R]

All subcommands print JSON and exit 0 on success. A `GhRestError` prints to
stderr and exits 1; a `GhRestUnsupportedError` prints to stderr and exits 3
(distinct from a plain failure, so a caller/hook can tell "no fallback
exists" from "the fallback itself broke").

The comment-post two-step split, and why it is two subcommands, not one
=========================================================================
`comment write-payload` and `comment post` are deliberately SEPARATE CLI
subcommands/functions, never combined into one "post this string" call. This
is not a style choice — it works around a live hook interaction (#1224 issue
body, trap 4): `validate_review_comment_format` (a PreToolUse gate on `gh api
.../comments --method POST --input <file>`) reads the payload FILE to
validate the charter review-comment format, and blocks when that file does
not exist yet. If an agent tries to write-then-post in one Bash call (e.g.
`jq -n ... > f.json && gh api ... --input f.json`), the hook inspects the
command BEFORE either half has run and sees a not-yet-existing file — a false
block. Writing the payload in its own earlier tool call (this module's
`comment write-payload`, or the caller's own file write) sidesteps it. Do not
"simplify" this back into one call.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

DEFAULT_TIMEOUT_SECONDS = 20
PAGINATE_TIMEOUT_SECONDS = 60

# gh's own placeholder syntax — resolved from the invocation cwd's git remote,
# same resolution `gh issue view` (no --repo) performs. See module docstring
# § Repo/owner resolution.
_DEFAULT_REPO_PATH = ":owner/:repo"


class GhRestError(Exception):
    """A REST call genuinely failed (bad exit, unparseable response).

    Never raised for "zero results" — an empty list/dict is a legitimate
    answer. Raised for anything that would otherwise silently masquerade as
    one (module docstring § Never masks a real failure as an empty result).
    """


class GhRestUnsupportedError(GhRestError):
    """The requested operation has no REST equivalent at all.

    Distinct from GhRestError so a caller (or the PreToolUse hook) can choose
    to ADVISE rather than treat this as an ordinary failure — see the module
    docstring's `gh project item-add` correction for the one case in this
    module that is genuinely still unsupported (classic Projects).
    """


def _repo_path(repo: str | None) -> str:
    return repo if repo else _DEFAULT_REPO_PATH


def _run_gh(args: list[str], *, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> str:
    """Run `gh <args>` and return stdout. Raises GhRestError on any failure.

    Deliberately does NOT swallow stderr or a non-zero exit — see module
    docstring § Never masks a real failure as an empty result.
    """
    try:
        result = subprocess.run(
            ["gh", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise GhRestError(f"gh {' '.join(args)} timed out after {timeout}s") from exc
    except (FileNotFoundError, OSError) as exc:
        raise GhRestError(f"could not run gh: {exc}") from exc
    if result.returncode != 0:
        raise GhRestError(
            f"gh {' '.join(args)} failed (exit {result.returncode}): {result.stderr.strip()}"
        )
    return result.stdout


def _api_json(endpoint: str, *, method: str = "GET", extra_args: list[str] | None = None) -> dict:
    """`gh api <endpoint>` -> parsed JSON object. Raises GhRestError on failure."""
    args = ["api", endpoint]
    if method != "GET":
        args += ["-X", method]
    if extra_args:
        args += extra_args
    stdout = _run_gh(args)
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise GhRestError(f"gh api {endpoint}: response did not parse as JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise GhRestError(f"gh api {endpoint}: expected a JSON object, got {type(data).__name__}")
    return data


def _api_paginate_jq(
    endpoint: str, jq_filter: str, *, extra_args: list[str] | None = None
) -> list[dict]:
    """`gh api <endpoint> --paginate --jq '<jq_filter>'` -> list of JSON objects.

    Every page's `--jq` output lands one compact JSON value per line (verified
    live, module docstring § trap 2), so parsing is a per-line `json.loads`.
    An empty stdout with exit 0 is a legitimate empty result; a non-zero exit
    or an unparseable line raises GhRestError — see § Never masks a real
    failure as an empty result.
    """
    args = ["api", endpoint, "--paginate", "--jq", jq_filter]
    if extra_args:
        args += extra_args
    stdout = _run_gh(args, timeout=PAGINATE_TIMEOUT_SECONDS)
    out: list[dict] = []
    for i, line in enumerate(stdout.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise GhRestError(
                f"gh api {endpoint} --paginate: line {i + 1} did not parse as JSON: {exc}"
            ) from exc
    return out


# --------------------------------------------------------------------------- issues


def issue_view(number: int | str, repo: str | None = None) -> dict:
    """REST equivalent of `gh issue view <N> --json number,state,title,labels,closedAt`.

    Raises GhRestError if `number` names a PULL REQUEST, not an issue — the
    `/issues/{number}` endpoint answers for PRs too (module docstring trap 1),
    and silently returning PR data under an "issue" name is exactly the kind
    of mislabel that produced the 57-vs-50 overcount. Use `pr_view` for a PR.
    """
    data = _api_json(f"repos/{_repo_path(repo)}/issues/{number}")
    if data.get("pull_request") is not None:
        raise GhRestError(
            f"#{number} is a pull request, not an issue (the REST issues endpoint answers for "
            "PRs too — feedback_gh_cli_gotchas §12 trap 1). Use pr_view() instead."
        )
    return {
        "number": data["number"],
        "state": data["state"],
        "title": data["title"],
        "labels": [label["name"] for label in data.get("labels", [])],
        "closedAt": data.get("closed_at"),
    }


def issue_list(
    repo: str | None = None,
    *,
    label: str | None = None,
    state: str = "open",
) -> list[dict]:
    """REST equivalent of `gh issue list --json number,state,title,labels,closedAt`.

    Filters out pull requests server-response-side (module docstring trap 1)
    and paginates (trap 2) — a >100-item repo never silently truncates.
    """
    params = [f"state={state}"]
    if label:
        params.append(f"labels={label}")
    endpoint = f"repos/{_repo_path(repo)}/issues?{'&'.join(params)}"
    jq_filter = (
        ".[] | select(.pull_request == null) | "
        "{number, state, title, labels: [.labels[].name], closedAt: .closed_at}"
    )
    return _api_paginate_jq(endpoint, jq_filter)


def issue_timeline(number: int | str, repo: str | None = None) -> list[dict]:
    """REST equivalent of a timeline-events read (e.g. `head_ref_force_pushed`).

    Works identically for issues and PRs — a PR IS an issue for this endpoint.
    Paginated (trap 2).
    """
    endpoint = f"repos/{_repo_path(repo)}/issues/{number}/timeline"
    jq_filter = ".[] | {event, createdAt: .created_at, actor: (.actor.login // null)}"
    return _api_paginate_jq(endpoint, jq_filter)


# --------------------------------------------------------------------------- PRs


def pr_view(number: int | str, repo: str | None = None) -> dict:
    """REST equivalent of `gh pr view <N> --json number,state,headRefOid,headRefName,
    baseRefName,mergedAt,mergeCommit`."""
    data = _api_json(f"repos/{_repo_path(repo)}/pulls/{number}")
    return {
        "number": data["number"],
        "state": data["state"],
        "headRefOid": data["head"]["sha"],
        "headRefName": data["head"]["ref"],
        "baseRefName": data["base"]["ref"],
        "mergedAt": data.get("merged_at"),
        "mergeCommit": data.get("merge_commit_sha"),
    }


def pr_list(repo: str | None = None, *, state: str = "open") -> list[dict]:
    """REST equivalent of `gh pr list --json number,state,headRefName,baseRefName`.

    The `/pulls` endpoint (unlike `/issues`) never mixes in issues, so no
    trap-1 filter is needed here. Paginated (trap 2).
    """
    endpoint = f"repos/{_repo_path(repo)}/pulls?state={state}"
    jq_filter = ".[] | {number, state, headRefName: .head.ref, baseRefName: .base.ref}"
    return _api_paginate_jq(endpoint, jq_filter)


def pr_comments(number: int | str, repo: str | None = None) -> list[dict]:
    """REST equivalent of a PR/issue comment read (`gh api .../comments`, already REST — §12).

    Kept here for shape-parity with the rest of the module (same return shape
    as the other functions) and so callers have one import for the whole
    surface. Paginated (trap 2).
    """
    endpoint = f"repos/{_repo_path(repo)}/issues/{number}/comments"
    jq_filter = ".[] | {id, author: .user.login, body, createdAt: .created_at}"
    return _api_paginate_jq(endpoint, jq_filter)


def pr_check_runs(sha: str, repo: str | None = None) -> list[dict]:
    """REST check-runs read for a commit SHA — `feedback_gh_cli_gotchas` §13:
    `check-runs` is authoritative, the legacy `status` endpoint is not.

    Query by SHA, never by PR number (§13: a PR-number query re-resolves the
    head and can answer about a different commit than the one you mean to
    certify). Paginated (trap 2).
    """
    endpoint = f"repos/{_repo_path(repo)}/commits/{sha}/check-runs"
    jq_filter = ".check_runs[] | {name, status, conclusion}"
    return _api_paginate_jq(endpoint, jq_filter)


# ----------------------------------------------------- comments (two-step; see module docstring)


def write_comment_payload(path: str | Path, body: str) -> None:
    """Write `{"body": body}` to `path` for a later `--input` POST.

    MUST run as its own, earlier tool call — see module docstring § The
    comment-post two-step split for why. Uses `ensure_ascii=False` so a
    literal Arabic/diacritic body round-trips as UTF-8, not `\\uXXXX` escapes
    (mirrors the ontology/checksums.json ASCII-escape trap this org already
    guards against elsewhere).
    """
    Path(path).write_text(json.dumps({"body": body}, ensure_ascii=False), encoding="utf-8")


def post_comment(number: int | str, payload_path: str | Path, repo: str | None = None) -> dict:
    """POST the payload written by `write_comment_payload` as an issue/PR comment.

    Raises GhRestError (not a bare FileNotFoundError) if `payload_path`
    doesn't exist yet — the exact shape `validate_review_comment_format`
    guards against; see module docstring § The comment-post two-step split.
    """
    path = Path(payload_path)
    if not path.is_file():
        raise GhRestError(
            f"comment payload file {path} does not exist — write it in an EARLIER, separate "
            "tool call via write_comment_payload() before calling post_comment() (module "
            "docstring § The comment-post two-step split; this mirrors the "
            "validate_review_comment_format hook's own file-must-exist read)."
        )
    endpoint = f"repos/{_repo_path(repo)}/issues/{number}/comments"
    data = _api_json(endpoint, method="POST", extra_args=["--input", str(path)])
    return {"id": data.get("id"), "body": data.get("body"), "createdAt": data.get("created_at")}


# ---------------------------------------------------------- ProjectV2 (org-owned boards)


def _issue_database_id(number: int | str, repo: str | None) -> int:
    """Resolve the REST database `id` for an issue/PR — required by `project_item_add`.

    NOT the issue `number` and NOT the GraphQL `node_id` — a distinct numeric
    field. `/issues/{number}` answers for both issues and PRs (trap 1's
    endpoint), so this single lookup covers both content types.
    """
    data = _api_json(f"repos/{_repo_path(repo)}/issues/{number}")
    return int(data["id"])


def project_item_add(
    project_number: int | str,
    org: str,
    number: int | str,
    repo: str | None = None,
    *,
    content_type: str | None = None,
) -> dict:
    """Add an issue/PR to an ORG-OWNED ProjectV2 board over REST.

    This IS supported over REST — see module docstring's correction of the
    #1224 issue body's "GraphQL-only, no REST equivalent" premise, verified
    live by actually adding #1224 to project board 2 through this exact call.
    `gh project item-add` (the CLI command) is still GraphQL-backed and still
    fails under exhaustion; this is the fallback for that gap specifically,
    NOT a claim that `gh`'s own command changed.

    `content_type` is inferred from whether the number carries a `pull_request`
    key (auto-detected via the same lookup that resolves the database id) when
    not given explicitly — pass it to skip that extra read if already known.
    """
    data = _api_json(f"repos/{_repo_path(repo)}/issues/{number}")
    resolved_type = content_type or (
        "PullRequest" if data.get("pull_request") is not None else "Issue"
    )
    if resolved_type not in ("Issue", "PullRequest"):
        raise GhRestError(f"content_type must be 'Issue' or 'PullRequest', got {resolved_type!r}")
    payload = json.dumps({"type": resolved_type, "id": int(data["id"])})
    endpoint = f"orgs/{org}/projectsV2/{project_number}/items"
    return _post_project_item(endpoint, payload)


def _post_project_item(endpoint: str, payload: str) -> dict:
    try:
        result = subprocess.run(
            ["gh", "api", endpoint, "-X", "POST", "--input", "-"],
            input=payload,
            capture_output=True,
            text=True,
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise GhRestError(f"gh api {endpoint} POST timed out") from exc
    if result.returncode != 0:
        raise GhRestError(f"gh api {endpoint} POST failed: {result.stderr.strip()}")
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise GhRestError(f"gh api {endpoint} POST: response did not parse as JSON: {exc}") from exc
    return {
        "itemId": data.get("id"),
        "contentType": data.get("content_type"),
        "number": (data.get("content") or {}).get("number"),
    }


def project_items(org: str, project_number: int | str) -> list[dict]:
    """Read every item on an org-owned ProjectV2 board over REST.

    The read-side counterpart of `project_item_add`. No server-side filter
    exists for "does this board contain issue N" — this pages the WHOLE
    board (same O(n) shape `gh project item-list` has, just over REST) and
    the caller (or `issue_project_membership`) filters client-side.
    Paginated (trap 2) — the board is documented at >1,690 items and rising
    (`feedback_gh_cli_gotchas` §3), so truncation here would recreate exactly
    that false-negative class at a new layer.
    """
    endpoint = f"orgs/{org}/projectsV2/{project_number}/items"
    jq_filter = (
        ".[] | {itemId: .id, contentType: .content_type, "
        "number: .content.number, title: .content.title, "
        "repository: (.content.repository.full_name // null)}"
    )
    return _api_paginate_jq(endpoint, jq_filter)


def issue_project_membership(
    number: int | str,
    org: str,
    project_number: int | str,
    repo: str | None = None,
) -> dict | None:
    """Is issue/PR `number` (in `repo`) on the board? Returns the item dict or None.

    REST equivalent of `gh issue view --json projectItems`. `repo` matters:
    this is an ORG-WIDE board spanning multiple repos, so issue numbers
    collide across repos (`feedback_gh_cli_gotchas` §3's multi-repo
    false-match trap) — filters on BOTH number and repository full_name, not
    number alone.
    """
    target_repo = repo
    if target_repo is None:
        # Resolve via the same issue lookup other functions use, so the
        # filter below compares like-for-like full_name strings.
        data = _api_json(f"repos/{_repo_path(repo)}/issues/{number}")
        target_repo = data["repository_url"].split("/repos/", 1)[-1]
    for item in project_items(org, project_number):
        if item.get("number") == int(number) and item.get("repository") == target_repo:
            return item
    return None


# ------------------------------------------------- classic Projects (genuinely unsupported)


def classic_project_lookup(org: str) -> list[dict]:
    """Classic Projects REST API — fully removed. Always raises.

    Verified live (2026-08-02): `gh api orgs/{org}/projects` -> 404 Not Found.
    Exists so a caller that reaches for the old classic-Projects shape gets a
    clear, explicit "no equivalent" instead of a confusing 404 surfacing raw.
    """
    raise GhRestUnsupportedError(
        f"classic Projects REST API is fully removed (gh api orgs/{org}/projects -> 404). "
        "This board is a ProjectV2 board — use project_items()/project_item_add() instead."
    )


# --------------------------------------------------------------------------- CLI


def _print(obj: object) -> None:
    print(json.dumps(obj, indent=2, sort_keys=True))


def _cmd_issue_view(args: argparse.Namespace) -> int:
    _print(issue_view(args.number, repo=args.repo))
    return 0


def _cmd_issue_list(args: argparse.Namespace) -> int:
    _print(issue_list(repo=args.repo, label=args.label, state=args.state))
    return 0


def _cmd_issue_timeline(args: argparse.Namespace) -> int:
    _print(issue_timeline(args.number, repo=args.repo))
    return 0


def _cmd_pr_view(args: argparse.Namespace) -> int:
    _print(pr_view(args.number, repo=args.repo))
    return 0


def _cmd_pr_list(args: argparse.Namespace) -> int:
    _print(pr_list(repo=args.repo, state=args.state))
    return 0


def _cmd_pr_comments(args: argparse.Namespace) -> int:
    _print(pr_comments(args.number, repo=args.repo))
    return 0


def _cmd_pr_checks(args: argparse.Namespace) -> int:
    _print(pr_check_runs(args.sha, repo=args.repo))
    return 0


def _cmd_comment_write_payload(args: argparse.Namespace) -> int:
    body = Path(args.body_file).read_text(encoding="utf-8") if args.body_file else args.body
    write_comment_payload(args.file, body or "")
    print(f"wrote payload to {args.file}")
    return 0


def _cmd_comment_post(args: argparse.Namespace) -> int:
    _print(post_comment(args.number, args.file, repo=args.repo))
    return 0


def _cmd_project_add(args: argparse.Namespace) -> int:
    _print(project_item_add(args.project, args.org, args.number, repo=args.repo))
    return 0


def _cmd_project_items(args: argparse.Namespace) -> int:
    _print(project_items(args.org, args.project))
    return 0


def _cmd_project_membership(args: argparse.Namespace) -> int:
    _print(issue_project_membership(args.number, args.org, args.project, repo=args.repo))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="gh_rest",
        description="REST fallbacks for gh's GraphQL-backed read/write surfaces (#1224).",
    )
    sub = p.add_subparsers(dest="group", required=True)

    issue = sub.add_parser("issue")
    issue_sub = issue.add_subparsers(dest="cmd", required=True)
    p_iv = issue_sub.add_parser("view")
    p_iv.add_argument("number")
    p_iv.add_argument("--repo")
    p_iv.set_defaults(func=_cmd_issue_view)
    p_il = issue_sub.add_parser("list")
    p_il.add_argument("--repo")
    p_il.add_argument("--label")
    p_il.add_argument("--state", default="open")
    p_il.set_defaults(func=_cmd_issue_list)
    p_it = issue_sub.add_parser("timeline")
    p_it.add_argument("number")
    p_it.add_argument("--repo")
    p_it.set_defaults(func=_cmd_issue_timeline)

    pr = sub.add_parser("pr")
    pr_sub = pr.add_subparsers(dest="cmd", required=True)
    p_pv = pr_sub.add_parser("view")
    p_pv.add_argument("number")
    p_pv.add_argument("--repo")
    p_pv.set_defaults(func=_cmd_pr_view)
    p_pl = pr_sub.add_parser("list")
    p_pl.add_argument("--repo")
    p_pl.add_argument("--state", default="open")
    p_pl.set_defaults(func=_cmd_pr_list)
    p_pc = pr_sub.add_parser("comments")
    p_pc.add_argument("number")
    p_pc.add_argument("--repo")
    p_pc.set_defaults(func=_cmd_pr_comments)
    p_pk = pr_sub.add_parser("checks")
    p_pk.add_argument("sha")
    p_pk.add_argument("--repo")
    p_pk.set_defaults(func=_cmd_pr_checks)

    comment = sub.add_parser("comment")
    comment_sub = comment.add_subparsers(dest="cmd", required=True)
    p_wp = comment_sub.add_parser("write-payload")
    p_wp.add_argument("--file", required=True)
    p_wp.add_argument("--body")
    p_wp.add_argument("--body-file")
    p_wp.set_defaults(func=_cmd_comment_write_payload)
    p_cp = comment_sub.add_parser("post")
    p_cp.add_argument("number")
    p_cp.add_argument("--file", required=True)
    p_cp.add_argument("--repo")
    p_cp.set_defaults(func=_cmd_comment_post)

    project = sub.add_parser("project")
    project_sub = project.add_subparsers(dest="cmd", required=True)
    p_pa = project_sub.add_parser("add")
    p_pa.add_argument("number")
    p_pa.add_argument("--org", required=True)
    p_pa.add_argument("--project", required=True)
    p_pa.add_argument("--repo")
    p_pa.set_defaults(func=_cmd_project_add)
    p_pi = project_sub.add_parser("items")
    p_pi.add_argument("--org", required=True)
    p_pi.add_argument("--project", required=True)
    p_pi.set_defaults(func=_cmd_project_items)
    p_pm = project_sub.add_parser("membership")
    p_pm.add_argument("number")
    p_pm.add_argument("--org", required=True)
    p_pm.add_argument("--project", required=True)
    p_pm.add_argument("--repo")
    p_pm.set_defaults(func=_cmd_project_membership)

    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except GhRestUnsupportedError as exc:
        print(f"gh_rest: UNSUPPORTED — {exc}", file=sys.stderr)
        return 3
    except GhRestError as exc:
        print(f"gh_rest: ERROR — {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
