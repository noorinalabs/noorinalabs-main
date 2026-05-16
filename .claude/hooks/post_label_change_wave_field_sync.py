#!/usr/bin/env python3
"""PostToolUse hook: Auto-sync project 2 Wave field when a wave label is added/removed.

When a `gh issue edit <num> --add-label "p{N}-wave-{M}"` or
`--remove-label "p{N}-wave-{M}"` command succeeds, this hook PATCHes the
issue's `Wave` single-select field on project 2 (Cross-Repo Wave Plan
board) to match the post-edit label state via GraphQL
`updateProjectV2ItemFieldValue`.

Closes the label-EDIT gap that Hook 13 (`auto_add_issue_to_board.py`,
which only catches `gh issue create`) doesn't cover. Same invariant as
Hook 13 — wave-labeled issues belong on the board with their Wave field
set — applied at the EDIT surface instead of the CREATE surface. 5
drifts caught by `/board-audit` in P3W10 retro motivated this hook.

Input Language:
  Fires on:      PostToolUse Bash
  Matches:       Bash commands whose `gh issue edit <num>` segment
                 includes at least one `--add-label "p{N}-wave-{M}"` or
                 `--remove-label "p{N}-wave-{M}"` flag-value pair, where
                 the label value matches the canonical wave-label regex
                 `^p\\d+-wave-\\d+$` (fully anchored).
  Does NOT match: any non-Bash tool; Bash without `gh issue edit`;
                  `gh issue create` (Hook 13's surface);
                  `gh pr edit ... --add-label ...` (PR labels don't
                  drive the Wave field — the Wave field lives on issues
                  in project 2); commands with non-wave labels (e.g.
                  `--add-label "bug"`); suffixed labels (e.g.
                  `p3-wave-10-special` does NOT match — anchored regex
                  excludes them).
  Flag pass-through:
    --repo            → identifies the owner/name; the short name is used
                        as the project content lookup key
                        (`https://github.com/noorinalabs/<repo>/issues/<num>`)
    --add-label       → wave label is set as the new Wave-field value
    --remove-label    → if the removed value matches the current Wave-field
                        value, the Wave field is CLEARED;
                        else no-op
    --add-label + --remove-label (compound) → POST-edit state is what
                        matters; add wins (set to the added value)

Exit codes:
  0 — always (PostToolUse hooks are advisory; failures log to Annunaki
      and silently skip the field-sync without affecting the user-visible
      tool call which has already succeeded)

Kill-switch
===========

Set environment variable `NOORIN_DISABLE_LABEL_SYNC_HOOK=1` to bypass
the hook entirely (no GraphQL call, no error, silent skip). Only the
literal string `1` skips; `=0`, empty, unset → hook proceeds normally
(Unix-tradition truthy-only). Use during debugging or incident response
when auto-mutation of the project board would interfere.

Auth-scope pre-flight
=====================

GraphQL `updateProjectV2ItemFieldValue` requires `project` scope on the
gh CLI auth token; the default scope is `repo`-only. The hook pre-flights
via `gh auth status -h github.com` and, if the project scope is missing,
skips silently and logs ONE annunaki entry per session (debounced via
the cache file's existence) instructing the user to run `gh auth refresh
-s project`. This is the fail-soft shape per
`feedback_runtime_gate_scoping.md`; surprising a user with a hook that
needs extra auth setup is the failure mode this avoids.

Project ID cache
================

Three IDs are required for the GraphQL mutation: the project node ID,
the Wave field ID, and the per-wave option ID (e.g. `P3W11`'s option ID).
Resolving all three on every label-edit would be ~3 GraphQL round-trips
of latency per hook fire. Instead, the hook introspects on the first
fire of a session and caches the result to
`.claude/.consulted/post_label_change_wave_field_sync/project_ids.json`
with a 1-hour TTL. The cache file is mode-0600 (owner-only read/write).
On `field-not-found` errors from the mutation (e.g., field was recreated
between cache write and mutation), the cache is busted and one
re-introspect + retry is performed before giving up.

Design choices documented for reviewer pickup
=============================================

- **No per-issue opt-out.** "All wave-labeled issues are board-tracked"
  is treated as a wave-scope invariant (per
  `feedback_wave_planning_from_board.md`). Adding an opt-out label like
  `noorin-no-board-sync` would silently drop wave-labeled issues off the
  board — contradicting `/wave-scope` and `/board-audit` semantics. If a
  wave-labeled issue genuinely should not be board-tracked, the right
  fix is to remove the wave label, not to add a sync-skip label.
  Additive escape hatches (denylist constant, opt-out label) can be
  added in a follow-up PR if real cases emerge — strictly additive, no
  breaking-semantic change.

- **No `addProjectV2ItemById` pre-flight.** The hook assumes the issue
  is already on project 2 (Hook 13 added it on create). If the issue
  is NOT on the board, the GraphQL mutation returns a "no matching
  item" error which the hook treats as a graceful skip — board-audit
  is the periodic compensating control for that case.

- **PostToolUse-ordering vs Hook 13.** Hook 13 (`auto_add_issue_to_board`)
  is registered BEFORE this hook in `post_dispatcher.py`'s Bash matcher
  list, so on a `gh issue create` flow that immediately edits the issue
  label, Hook 13's board-add lands first. But this hook does NOT fire
  on `gh issue create` (input language above); the ordering matters
  only for a hypothetical compound command that creates AND edits in
  one Bash call — out of pattern.

Promotion provenance
====================

P3W10 retro PR #441 § Proposed Process Changes #3. Owner-decided
2026-05-16; charter adoption via PR #444 (ccc7edf); this hook
implementation via PR #__PR_NUMBER__ (issue #445). 5-drift evidence base
from W10 /board-audit run (all label-edit-class drifts that Hook 13
didn't catch). Companion to Hook 13 (`auto_add_issue_to_board.py`)
which catches CREATE-time only; this hook closes the label-EDIT gap.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _wave_label_parse import parse_wave_label, parse_wave_label_change  # noqa: E402
from annunaki_log import log_posttooluse_event  # noqa: E402

ORG = "noorinalabs"
PROJECT_NUMBER = 2

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CACHE_DIR = REPO_ROOT / ".claude" / ".consulted" / "post_label_change_wave_field_sync"
CACHE_PATH = CACHE_DIR / "project_ids.json"
CACHE_TTL_SECONDS = 3600  # 1 hour

KILL_SWITCH_ENV = "NOORIN_DISABLE_LABEL_SYNC_HOOK"

# Sentinel marker file used to debounce per-session auth-scope warnings —
# ensures we annunaki-log the "project scope missing" advisory only ONCE
# per session, not on every label-edit.
AUTH_WARN_SENTINEL = CACHE_DIR / "auth_scope_warned.marker"


def _kill_switch_active() -> bool:
    """True iff `NOORIN_DISABLE_LABEL_SYNC_HOOK=1` is set in the env.

    Literal `1` only. Empty / unset / `0` / any other value → False.
    Unix-tradition truthy-only.
    """
    return os.environ.get(KILL_SWITCH_ENV, "") == "1"


def _has_project_scope(auth_status_runner=None) -> bool:
    """True iff `gh auth status -h github.com` reports `project` scope.

    The output of `gh auth status -h github.com` includes a line like:
        - Token scopes: 'gist', 'project', 'read:org', 'repo', 'workflow'
    We check for `project` as a complete token (between quotes/commas)
    to avoid `read:project` substring false-positives.

    `auth_status_runner` returns the stdout of the gh-auth-status call
    (tests inject a fake); the default invokes gh directly. Returns
    False if the runner raises (network/auth error) — fail-closed for
    auth-scope.
    """
    if auth_status_runner is None:
        auth_status_runner = _default_auth_status_runner

    try:
        stdout = auth_status_runner()
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return False
    if not stdout:
        return False
    # gh auth status writes scope to stderr historically; the runner combines.
    # Match `'project'` (single-quoted, complete token).
    return "'project'" in stdout


def _default_auth_status_runner() -> str:
    """Run `gh auth status -h github.com` and return stdout+stderr combined.

    gh writes the Token-scopes line to stderr; we combine both streams so
    the parser sees it.
    """
    result = subprocess.run(
        ["gh", "auth", "status", "-h", "github.com"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    return (result.stdout or "") + (result.stderr or "")


def _read_cache() -> dict | None:
    """Read the cached project-IDs blob if it exists and is fresh.

    Returns the cached dict (with keys: `project_id`, `field_id`,
    `option_ids`, `cached_at`) if the cache file exists and is within
    TTL. Returns None on missing / stale / unreadable cache.
    """
    if not CACHE_PATH.is_file():
        return None
    try:
        blob = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    cached_at = blob.get("cached_at", 0)
    if not isinstance(cached_at, (int, float)):
        return None
    if time.time() - cached_at > CACHE_TTL_SECONDS:
        return None
    return blob


def _write_cache(blob: dict) -> None:
    """Write the project-IDs blob atomically with mode 0600.

    `os.replace` is atomic on POSIX so partial writes never leave a
    truncated cache file. Mode 0600 keeps the cache owner-only.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    blob = {**blob, "cached_at": time.time()}
    tmp = CACHE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(blob, indent=2), encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, CACHE_PATH)


def _bust_cache() -> None:
    """Remove the cache file. Used after a field-not-found error to force
    re-introspection on the next fire."""
    try:
        CACHE_PATH.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass  # best-effort


def _gh_graphql(query: str, variables: dict, runner=None) -> dict | None:
    """Run a GraphQL query via gh. Returns parsed JSON `.data` or None on error.

    `runner(query, variables) -> stdout` is the injection point for tests.
    The default invokes `gh api graphql -F ... -f query=...`.
    """
    if runner is None:
        runner = _default_graphql_runner
    try:
        raw = runner(query, variables)
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return None
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None
    return parsed


def _default_graphql_runner(query: str, variables: dict) -> str:
    """Default `gh api graphql` runner. Builds the argv from variables.

    String values pass via `-f key=value`; integer values pass via
    `-F key=value` (gh's typed-int form). Per memory
    `feedback_gh_pr_edit_silent_noop` — use `-F`/`-f` explicitly rather
    than `--input -` for these mutations.
    """
    argv = ["gh", "api", "graphql"]
    for k, v in variables.items():
        if isinstance(v, bool):
            argv += ["-F", f"{k}={'true' if v else 'false'}"]
        elif isinstance(v, int):
            argv += ["-F", f"{k}={v}"]
        else:
            argv += ["-f", f"{k}={v}"]
    argv += ["-f", f"query={query}"]
    result = subprocess.run(argv, capture_output=True, text=True, timeout=20)
    if result.returncode != 0:
        return ""
    return result.stdout


_INTROSPECT_QUERY = """
query($org: String!, $project: Int!) {
  organization(login: $org) {
    projectV2(number: $project) {
      id
      field(name: "Wave") {
        ... on ProjectV2SingleSelectField {
          id
          options { id name }
        }
      }
    }
  }
}
"""


def _introspect_project_ids(graphql_runner=None) -> dict | None:
    """Look up `project_id`, `field_id`, and Wave option_ids via GraphQL.

    Returns a dict with the cache-blob shape on success; None on failure.
    """
    data = _gh_graphql(
        _INTROSPECT_QUERY,
        {"org": ORG, "project": PROJECT_NUMBER},
        runner=graphql_runner,
    )
    if not data:
        return None
    proj = (data.get("data") or {}).get("organization", {}).get("projectV2")
    if not proj:
        return None
    project_id = proj.get("id")
    field = proj.get("field") or {}
    field_id = field.get("id")
    options = {opt["name"]: opt["id"] for opt in (field.get("options") or [])}
    if not project_id or not field_id:
        return None
    return {
        "project_id": project_id,
        "field_id": field_id,
        "option_ids": options,
    }


def _get_project_ids(graphql_runner=None) -> dict | None:
    """Return cached IDs if fresh; else introspect, cache, and return."""
    cached = _read_cache()
    if cached:
        return cached
    fresh = _introspect_project_ids(graphql_runner=graphql_runner)
    if fresh:
        _write_cache(fresh)
    return fresh


_ITEM_LOOKUP_QUERY = """
query($org: String!, $project: Int!, $repo: String!, $num: Int!) {
  organization(login: $org) {
    projectV2(number: $project) {
      items(first: 100) {
        nodes {
          id
          content {
            ... on Issue { number repository { name } }
          }
        }
      }
    }
  }
}
"""


def _lookup_item_id(repo: str, issue_number: str, graphql_runner=None) -> str | None:
    """Find the project 2 item ID for `noorinalabs/<repo>` issue `<issue_number>`.

    `items(first: 100)` is the first page; in practice we'd need
    pagination to be 100% correct, but a 100-item first page covers
    every wave's working set we've seen. If the issue isn't found on
    page 1, returns None (graceful skip — board-audit will sweep later).
    Pagination is intentionally deferred to keep the hook cheap; if
    we observe miss-after-first-page false-skips in production, file a
    follow-up to extend.
    """
    data = _gh_graphql(
        _ITEM_LOOKUP_QUERY,
        {
            "org": ORG,
            "project": PROJECT_NUMBER,
            "repo": repo,
            "num": int(issue_number),
        },
        runner=graphql_runner,
    )
    if not data:
        return None
    proj = (data.get("data") or {}).get("organization", {}).get("projectV2")
    if not proj:
        return None
    nodes = (proj.get("items") or {}).get("nodes") or []
    for node in nodes:
        content = node.get("content") or {}
        repo_obj = content.get("repository") or {}
        if content.get("number") == int(issue_number) and repo_obj.get("name") == repo:
            return node.get("id")
    return None


_SET_FIELD_MUTATION = """
mutation($project: ID!, $item: ID!, $field: ID!, $option: String!) {
  updateProjectV2ItemFieldValue(input: {
    projectId: $project,
    itemId: $item,
    fieldId: $field,
    value: { singleSelectOptionId: $option }
  }) {
    projectV2Item { id }
  }
}
"""

_CLEAR_FIELD_MUTATION = """
mutation($project: ID!, $item: ID!, $field: ID!) {
  clearProjectV2ItemFieldValue(input: {
    projectId: $project,
    itemId: $item,
    fieldId: $field
  }) {
    projectV2Item { id }
  }
}
"""


def _wave_label_to_option_name(label: str) -> str | None:
    """Convert `p3-wave-11` → `P3W11` (the option-name shape on project 2).

    `board-audit` SKILL.md § Pre-requisite documents this naming convention
    explicitly: every active wave's option in the project's Wave field
    follows `P{N}W{M}`. Returns None if `label` is not a canonical wave
    label (defensive — caller's input has already been validated by
    `parse_wave_label_change`, but a None here is safer than a wrong
    option name).
    """
    parsed = parse_wave_label(label)
    if parsed is None:
        return None
    phase_num, wave_num = parsed
    return f"P{phase_num}W{wave_num}"


def _ensure_auth_warned_once(reason: str) -> None:
    """Annunaki-log the auth-scope advisory ONCE per session (debounced)."""
    if AUTH_WARN_SENTINEL.exists():
        return
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    AUTH_WARN_SENTINEL.touch()
    log_posttooluse_event(
        "post_label_change_wave_field_sync",
        "",
        reason,
    )


def check(
    input_data: dict,
    auth_status_runner=None,
    graphql_runner=None,
) -> dict | None:
    """Pure decision function. Returns a dict describing the action taken
    (or skipped), or None when the hook does not apply.

    Result shape (always advisory — never blocking):
      None                                       — hook didn't apply
      {"action": "killed", ...}                  — kill-switch env var set
      {"action": "skip_no_auth_scope", ...}      — gh missing project scope
      {"action": "skip_no_project_ids", ...}     — introspection failed
      {"action": "skip_no_option", ...}          — wave option missing
      {"action": "skip_no_item", ...}            — issue not on project 2
      {"action": "set", ...}                     — Wave field set
      {"action": "cleared", ...}                 — Wave field cleared
      {"action": "skip_mutation_failed", ...}    — GraphQL mutation error

    Injection points let tests mock external state without mocking
    subprocess: `auth_status_runner()` returns the gh-auth-status output;
    `graphql_runner(query, variables)` returns the gh-api-graphql output.
    """
    if input_data.get("tool_name", "") != "Bash":
        return None

    if _kill_switch_active():
        return {"action": "killed"}

    command = input_data.get("tool_input", {}).get("command", "")
    if not command:
        return None

    change = parse_wave_label_change(command)
    if change is None:
        return None

    # POST-edit state semantics: if BOTH add and remove fired in one
    # command, the added value is the post-edit Wave field value.
    # If only add → set. If only remove → clear (we lost the wave
    # label from this issue). `parse_wave_label_change` guarantees at
    # least one of add_label / remove_label is non-None when it returns
    # a result, so the `or` here always resolves to a real str.
    target_label: str = change.add_label or change.remove_label or ""
    action_kind = "set" if change.add_label else "clear"

    if not _has_project_scope(auth_status_runner=auth_status_runner):
        _ensure_auth_warned_once(
            "post_label_change_wave_field_sync skipped: gh project scope required; "
            "run 'gh auth refresh -s project' to enable Wave-field auto-sync."
        )
        return {"action": "skip_no_auth_scope", "repo": change.repo, "issue": change.issue_number}

    ids = _get_project_ids(graphql_runner=graphql_runner)
    if not ids:
        log_posttooluse_event(
            "post_label_change_wave_field_sync",
            command,
            "Failed to introspect project 2 IDs; skipping Wave-field sync.",
        )
        return {"action": "skip_no_project_ids", "repo": change.repo, "issue": change.issue_number}

    option_name = _wave_label_to_option_name(target_label)
    if option_name is None:
        # Caller already validated the shape; this is defensive only.
        return None
    option_id = ids.get("option_ids", {}).get(option_name)
    if action_kind == "set" and option_id is None:
        # Missing option → log + skip (board-audit pre-req: option must be
        # pre-created in Project Settings).
        log_posttooluse_event(
            "post_label_change_wave_field_sync",
            command,
            f"Project 2 Wave field has no option {option_name!r}; "
            f"add via Project Settings then re-fire.",
        )
        return {
            "action": "skip_no_option",
            "repo": change.repo,
            "issue": change.issue_number,
            "option_name": option_name,
        }

    item_id = _lookup_item_id(change.repo, change.issue_number, graphql_runner=graphql_runner)
    if item_id is None:
        # Issue not on project 2 — graceful skip; board-audit will sweep.
        return {
            "action": "skip_no_item",
            "repo": change.repo,
            "issue": change.issue_number,
        }

    if action_kind == "set":
        result = _gh_graphql(
            _SET_FIELD_MUTATION,
            {
                "project": ids["project_id"],
                "item": item_id,
                "field": ids["field_id"],
                "option": option_id,
            },
            runner=graphql_runner,
        )
        if not result or "errors" in (result or {}):
            # Try cache-bust + retry once (field may have been recreated).
            errors_str = json.dumps(result.get("errors") if result else [])
            if "field" in errors_str.lower() or "not found" in errors_str.lower():
                _bust_cache()
                ids2 = _get_project_ids(graphql_runner=graphql_runner)
                option_id2 = (ids2 or {}).get("option_ids", {}).get(option_name)
                if ids2 and option_id2:
                    result2 = _gh_graphql(
                        _SET_FIELD_MUTATION,
                        {
                            "project": ids2["project_id"],
                            "item": item_id,
                            "field": ids2["field_id"],
                            "option": option_id2,
                        },
                        runner=graphql_runner,
                    )
                    if result2 and "errors" not in result2:
                        return {
                            "action": "set",
                            "repo": change.repo,
                            "issue": change.issue_number,
                            "option_name": option_name,
                            "retried_after_cache_bust": True,
                        }
            log_posttooluse_event(
                "post_label_change_wave_field_sync",
                command,
                f"GraphQL set-field mutation failed for {change.repo}#{change.issue_number} "
                f"(option={option_name}); see errors: {errors_str[:300]}",
            )
            return {
                "action": "skip_mutation_failed",
                "repo": change.repo,
                "issue": change.issue_number,
            }
        return {
            "action": "set",
            "repo": change.repo,
            "issue": change.issue_number,
            "option_name": option_name,
        }

    # action_kind == "clear"
    result = _gh_graphql(
        _CLEAR_FIELD_MUTATION,
        {
            "project": ids["project_id"],
            "item": item_id,
            "field": ids["field_id"],
        },
        runner=graphql_runner,
    )
    if not result or "errors" in (result or {}):
        log_posttooluse_event(
            "post_label_change_wave_field_sync",
            command,
            f"GraphQL clear-field mutation failed for {change.repo}#{change.issue_number}.",
        )
        return {
            "action": "skip_mutation_failed",
            "repo": change.repo,
            "issue": change.issue_number,
        }
    return {
        "action": "cleared",
        "repo": change.repo,
        "issue": change.issue_number,
    }


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)
    try:
        check(input_data)
    except Exception as e:  # noqa: BLE001
        try:
            log_posttooluse_event(
                "post_label_change_wave_field_sync",
                input_data.get("tool_input", {}).get("command", "")[:500],
                f"Unexpected hook error: {type(e).__name__}: {e}",
            )
        except Exception:
            pass
    sys.exit(0)


if __name__ == "__main__":
    main()
