#!/usr/bin/env python3
"""PreToolUse hook: intercept a GraphQL-backed `gh` call when GraphQL quota is low.

Promotes `feedback_gh_cli_gotchas` §12 from a memory note to enforcement
(#1224) — §12 documented the core/graphql split and the silent-zero failure
mode for ~2 weeks without preventing a recurrence (four concurrent agents
exhausted the quota again in the session that filed #1224). Mirrors
`block_bare_grep`'s shape: block the footgun, print the concrete rewrite.

Two-phase gate, cheapest check first
=====================================
1. **Command-pattern match** (free, in-process): does this Bash command
   invoke a `gh` subcommand this hook recognizes as GraphQL-backed? If not,
   return None immediately — no quota check, no network call. This is the
   dispatcher-ordering discipline (module docstring of `dispatcher.py`:
   "cheap/local checks first, network-calling last") applied inside a single
   hook: the network half only runs for the small slice of Bash calls that
   are even gh-shaped in the first place.
2. **Cached quota reading** (`gh_quota.resource_quota("graphql")`, TTL default
   30s) — only reached once a pattern actually matched. A hot loop of
   `gh issue view` calls therefore costs at most one live `rate_limit` fetch
   per TTL window, not one per call.

Block vs advise — the real design question (not a detail; see module for the
rationale sought by #1224's design-judgement section)
=====================================================
**BLOCK-with-rewrite** whenever this module (or `gh_rest.py`) has a verified,
derivable REST equivalent for the SPECIFIC invocation matched — covers every
pattern in `_BLOCK_PATTERNS` below, reads AND writes. This module found (and
verified LIVE, 2026-08-02, by actually using it) that `gh project item-add`
now HAS a REST equivalent for org-owned boards
(`orgs/{org}/projectsV2/{n}/items`, see `gh_rest.py` module docstring) —
correcting the #1224 issue body's assumption that board writes are
GraphQL-only. So writes are not categorically advise-only; the split is
"do we have a verified rewrite for THIS shape", not "is it a read or a
write."

**ADVISE-only** (allow, systemMessage naming the reset time) for exactly one
shape: a **raw `gh api graphql ...` call**. Any bespoke GraphQL mutation
built directly through `gh api graphql` (e.g. the ProjectV2 field-option
management `feedback_gh_cli_gotchas` §11 describes, or a query this module's
author never anticipated) carries an ARBITRARY payload the hook cannot
introspect into a rewrite — hard-blocking it would strand the agent with
literally no path forward, converting a slowdown into a dead end (the exact
failure #1224's issue body warns against). This is also the one place a
recognized-but-unmapped `gh <topic> <verb>` shape lands (e.g. `gh project
item-edit`, `gh project field-list` — no verified REST equivalent built
here): matched by `find_gh_subcommand` succeeding but no entry in
`_BLOCK_PATTERNS` fitting, which falls through to the same advise path via
`_looks_graphql_shaped`.

Degrade-to-ALLOW on a quota-check failure
==========================================
If `gh_quota.resource_quota("graphql")` returns None (offline, malformed
response, cache unwritable) this hook returns None (allow) — never blocks on
an unknown reading. See `gh_quota.py` module docstring § Degrade-to-ALLOW;
this hook is the one consumer that makes a decision from that sensor, so it
inherits the same safety direction.

Kill switch: `NOORIN_DISABLE_GH_QUOTA_GATE=1` disables the hook entirely
(mirrors `NOORIN_DISABLE_LABEL_SYNC_HOOK`). Threshold: `NOORIN_GH_QUOTA_MIN`
(default 25) — remaining GraphQL calls below this trip the gate.

Exit codes:
  0 — allow (no GraphQL-shaped match, quota unknown/sufficient, or advise-only)
  2 — block (a matched pattern with a verified rewrite, and quota is low)
"""

from __future__ import annotations

import json
import os
import sys
from typing import Callable

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _repo_flag_parse import extract_repo  # noqa: E402
from _shell_parse import (  # noqa: E402
    find_gh_subcommand,
    iter_command_segments,
    strip_heredocs,
    tokenize,
)
from annunaki_log import log_pretooluse_block  # noqa: E402

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib")
sys.path.insert(0, os.path.abspath(_LIB_DIR))
import gh_quota  # noqa: E402

DEFAULT_MIN_GRAPHQL = 25


def _min_graphql() -> int:
    raw = os.environ.get("NOORIN_GH_QUOTA_MIN", "")
    try:
        return int(raw) if raw else DEFAULT_MIN_GRAPHQL
    except ValueError:
        return DEFAULT_MIN_GRAPHQL


def _first_positional(rest: list[str]) -> str | None:
    """First non-flag token after the topic+verb — usually an issue/PR number."""
    for tok in rest:
        if not tok.startswith("-"):
            return tok
    return None


def _repo_hint(repo: str | None) -> str:
    return repo if repo else "OWNER/REPO"


def _rewrite_issue_view(rest: list[str], repo: str | None) -> str:
    number = _first_positional(rest) or "<N>"
    return f"python3 .claude/lib/gh_rest.py issue view {number} --repo {_repo_hint(repo)}"


def _rewrite_issue_list(rest: list[str], repo: str | None) -> str:
    repo_hint = _repo_hint(repo)
    return f"python3 .claude/lib/gh_rest.py issue list --repo {repo_hint} [--label L] [--state S]"


def _rewrite_issue_create(rest: list[str], repo: str | None) -> str:
    return (
        "gh issue create is GraphQL-backed (measured live, #1224 — modern gh needs GraphQL to "
        "resolve Issue-Type/board metadata even for a plain create); no wrapped helper exists "
        "yet, use the raw REST recipe:\n"
        "    jq -n --arg title 'TITLE' --arg body 'BODY' '{title:$title, body:$body, "
        'labels:["label1"]}\' > /tmp/issue.json\n'
        f"    gh api repos/{_repo_hint(repo)}/issues -X POST --input /tmp/issue.json"
    )


def _rewrite_pr_view(rest: list[str], repo: str | None) -> str:
    number = _first_positional(rest) or "<N>"
    return f"python3 .claude/lib/gh_rest.py pr view {number} --repo {_repo_hint(repo)}"


def _rewrite_pr_list(rest: list[str], repo: str | None) -> str:
    return f"python3 .claude/lib/gh_rest.py pr list --repo {_repo_hint(repo)}"


def _rewrite_pr_checks(rest: list[str], repo: str | None) -> str:
    number = _first_positional(rest) or "<N>"
    repo_hint = _repo_hint(repo)
    # Resolve headRefOid first, then query check-runs BY SHA
    # (feedback_gh_cli_gotchas §13 — check-runs is authoritative, and a
    # PR-number query can drift to the wrong commit; query by SHA).
    return (
        f"SHA=$(python3 .claude/lib/gh_rest.py pr view {number} --repo {repo_hint} | "
        "python3 -c 'import json,sys; print(json.load(sys.stdin)[\"headRefOid\"])')\n"
        f"    python3 .claude/lib/gh_rest.py pr checks $SHA --repo {repo_hint}"
    )


def _rewrite_pr_comment(rest: list[str], repo: str | None) -> str:
    number = _first_positional(rest) or "<N>"
    repo_hint = _repo_hint(repo)
    return (
        "gh pr comment is GraphQL-backed under exhaustion (feedback_gh_cli_gotchas §12). Write "
        "the payload in an EARLIER, separate call (validate_review_comment_format reads the "
        "file and false-blocks a same-call write-then-post):\n"
        "    python3 .claude/lib/gh_rest.py comment write-payload --file /tmp/comment.json "
        "--body 'YOUR BODY'\n"
        f"    python3 .claude/lib/gh_rest.py comment post {number} --file /tmp/comment.json "
        f"--repo {repo_hint}"
    )


def _rewrite_project_item_add(rest: list[str], repo: str | None) -> str:
    number = _first_positional(rest) or "<N>"
    repo_hint = _repo_hint(repo)
    return (
        "gh project item-add is GraphQL-backed and fails with a MISLEADING 'unknown owner "
        "type' error under exhaustion (not a quota message — feedback_gh_cli_gotchas §12). "
        "This DOES have a REST equivalent for an ORG-owned board (verified live, #1224 — "
        "corrects the earlier 'GraphQL-only' assumption):\n"
        f"    python3 .claude/lib/gh_rest.py project add {number} --org ORG --project N "
        f"--repo {repo_hint}\n"
        "(only verified for org-owned boards with the current token's scopes — if this also "
        "fails, fall back to waiting for GraphQL reset and file a gap report)."
    )


def _rewrite_project_item_list(rest: list[str], repo: str | None) -> str:
    return (
        "python3 .claude/lib/gh_rest.py project items --org ORG --project N   "
        "# pages the whole board over REST; see gh_rest.py project_items()"
    )


# (topic, verb) -> rewrite builder. Order does not matter (dict lookup).
_RewriteFn = Callable[[list[str], "str | None"], str]
_BLOCK_PATTERNS: dict[tuple[str, str], _RewriteFn] = {
    ("issue", "view"): _rewrite_issue_view,
    ("issue", "list"): _rewrite_issue_list,
    ("issue", "create"): _rewrite_issue_create,
    ("pr", "view"): _rewrite_pr_view,
    ("pr", "list"): _rewrite_pr_list,
    ("pr", "checks"): _rewrite_pr_checks,
    ("pr", "comment"): _rewrite_pr_comment,
    ("project", "item-add"): _rewrite_project_item_add,
    ("project", "item-list"): _rewrite_project_item_list,
}

# Shapes known to be GraphQL-backed that this module does NOT have a verified
# rewrite for (either genuinely unsupported, or just not built yet) — matched
# for the advise path so the agent gets a clear "no rewrite" message instead
# of silently sailing through hoping GraphQL isn't actually needed.
_ADVISE_ONLY_TOPICS: set[tuple[str, str]] = {
    ("project", "item-edit"),
    ("project", "field-list"),
    ("project", "field-create"),
}


def _match(command: str) -> tuple[str, tuple[str, str], list[str], str | None] | None:
    """Return (kind, (topic, verb), rest_tokens, repo) for a GraphQL-shaped gh call, else None.

    `kind` is "block" (a verified rewrite exists) or "advise" (recognized
    GraphQL shape, no verified rewrite — including a raw `gh api graphql` call).
    """
    body = strip_heredocs(command)
    tokens = tokenize(body)
    segments = list(iter_command_segments(tokens)) if tokens is not None else []

    for seg in segments:
        found = find_gh_subcommand(seg)
        if found is None:
            continue
        _global_opts, rest_all = found
        if not rest_all:
            continue
        # Raw `gh api graphql ...` — arbitrary payload, no rewrite derivable.
        if rest_all[0] == "api" and len(rest_all) > 1 and rest_all[1] == "graphql":
            repo = extract_repo(command)
            return ("advise", ("api", "graphql"), rest_all[2:], repo)
        if len(rest_all) < 2:
            continue
        topic, verb = rest_all[0], rest_all[1]
        rest = rest_all[2:]
        repo = extract_repo(command)
        if (topic, verb) in _BLOCK_PATTERNS:
            return ("block", (topic, verb), rest, repo)
        if (topic, verb) in _ADVISE_ONLY_TOPICS:
            return ("advise", (topic, verb), rest, repo)
    return None


def check(input_data: dict) -> dict | None:
    """Block/advise a GraphQL-shaped `gh` call when GraphQL quota is low."""
    if input_data.get("tool_name", "") != "Bash":
        return None
    if os.environ.get("NOORIN_DISABLE_GH_QUOTA_GATE", "") == "1":
        return None

    command = input_data.get("tool_input", {}).get("command", "")
    if not command or "gh" not in command:
        return None  # cheap prefilter — nothing gh-shaped at all

    matched = _match(command)
    if matched is None:
        return None  # not a GraphQL-shaped gh call — no quota check, no network

    kind, (topic, verb), rest, repo = matched

    # Only NOW do we touch the sensor — one cached call per TTL window.
    quota = gh_quota.resource_quota("graphql")
    if quota is None:
        # Unknown reading — degrade to ALLOW (gh_quota.py § Degrade-to-ALLOW).
        return None
    if quota.remaining >= _min_graphql():
        return None  # plenty of quota — let the ordinary gh command run

    reset_in = quota.seconds_to_reset()

    if kind == "advise":
        label = "gh api graphql" if (topic, verb) == ("api", "graphql") else f"gh {topic} {verb}"
        msg = (
            f"WARNING: GraphQL quota is low ({quota.remaining}/{quota.limit}, resets in "
            f"{reset_in}s) and `{label}` is GraphQL-backed with NO verified REST rewrite in "
            "gh_rest.py. Proceeding, but expect a possible "
            "'GraphQL: API rate limit already exceeded' failure — that is a silent-zero risk, "
            "not a real empty result (feedback_gh_cli_gotchas §12): do not pipe this to "
            "2>/dev/null and read an empty/failed result as a finding."
        )
        return {"decision": "allow", "systemMessage": msg}

    rewrite_fn = _BLOCK_PATTERNS[(topic, verb)]
    rewrite = rewrite_fn(rest, repo)
    result = {
        "decision": "block",
        "reason": (
            f"BLOCKED: `gh {topic} {verb}` is GraphQL-backed and GraphQL quota is low "
            f"({quota.remaining}/{quota.limit}, resets in {reset_in}s) — feedback_gh_cli_gotchas "
            "§12: this class of call fails as a SILENT ZERO (a bare "
            "'GraphQL: API rate limit already exceeded' string), not a raised error, so a "
            "customary 2>/dev/null masks quota exhaustion as an empty result.\n"
            f"Suggested REST rewrite:\n    {rewrite}\n"
            f"Or wait {reset_in}s for GraphQL quota to reset.\n"
            f"Override for a genuine need (rare): NOORIN_DISABLE_GH_QUOTA_GATE=1 {command[:80]}"
        ),
    }
    log_pretooluse_block("gh_quota_gate", command, result["reason"])
    return result


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    result = check(input_data)
    if result is None:
        sys.exit(0)
    print(json.dumps(result))
    if result.get("decision") == "block":
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
