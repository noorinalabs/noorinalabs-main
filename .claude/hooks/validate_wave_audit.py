#!/usr/bin/env python3
"""PreToolUse hook: Block wave-lifecycle skills until cross-repo audit clears.

The charter mandates (skills.md § Wave Lifecycle — Open-Item Audit) that any
skill claiming a wave is "concluded" / "complete" / "done" must first prove
the cross-repo open-item count is zero OR enumerate an explicit carry-forward
list. P2W9 emitted a "wave-9 parent-repo workstream concluded" handoff with
~22 items still open across child repos; the owner had to prompt to surface
the truth. Per the enforcement-hierarchy principle (hook > skill > charter),
a charter rule that already failed once becomes a hook.

This hook fires on PreToolUse Skill calls for wave-wrapup, wave-retro, and
handoff. It runs the canonical cross-repo audit unconditionally and blocks
the skill's invocation when open items exist without a carry-forward marker
in the skill's `args` payload. The skill's own narrative cannot rationalize
its way past the gate — the args must encode the carry-forward decision
BEFORE the skill is allowed to render.

PostToolUse output-scan was rejected during design review (issue #195 design
comment): by the time PostToolUse fires, the false claim is already on
screen and in the conversation history, defeating the enforcement-hierarchy
point. PreToolUse with audit-execution is the load-bearing surface.

Input Language
==============

Fires on:
    PreToolUse Skill

Matches:
    {tool_name: "Skill", tool_input: {skill: "<name>", args: "..."}}
    where <name> ∈ {"wave-wrapup", "wave-retro", "handoff"}

Does NOT match:
    Skill calls for /ontology-librarian, /session-start, /annunaki, etc.
        (only wave-lifecycle skills are gated; matcher checks
         tool_input.skill exactly against the gated set)
    Bash commands containing "wave-wrapup" / "handoff" as substrings
        (matcher is Skill, not Bash — `tool_name != "Skill"` short-circuits;
         this is the substring-bug guard, sibling of #216)
    Skill calls when wave_active == false in cross-repo-status.json
        (no active wave → no audit possible → allow with system message)

Carry-forward bypass (warn-but-allow):
    The hook scans `tool_input.args` (case-insensitive) for any of:
      - "carry-forward:" or "carry forward:" inline marker
      - "## Carry-forward" / "## Carry forward" markdown heading
      - "#<N> →" / "#<N> -> " arrow patterns naming a destination
    If matched, the audit is informational only — allow with a system
    message summarizing what's being carried. It does NOT clear an
    incomplete-coverage block (#1226): the marker acknowledges items the
    operator has SEEN, and an unqueried repo was never read.

Block condition:
    Either:
      - matched_skill AND open_count > 0 AND args lacks carry-forward marker
      - matched_skill ∈ _COVERAGE_BLOCKING_SKILLS AND the audit did not query
        every org repo — PARTIAL coverage (1-of-8 through 7-of-8, #1226) OR
        TOTAL coverage failure (8-of-8, no repo queried at all, #1230)
    #1230 resolution (closing the all-vs-some asymmetry): total failure used to
    fail-open unconditionally, AHEAD of the _COVERAGE_BLOCKING_SKILLS check —
    making the bigger blind spot (8-of-8 unreadable) strictly MORE permissive
    than the smaller one (1-of-8) for the exact two skills (/wave-wrapup,
    /wave-retro) #1226 hardened specifically because "an unknown is never
    green" (/session-start Step 5a). That inversion is now closed: for
    _COVERAGE_BLOCKING_SKILLS, total failure blocks exactly as partial failure
    does, with its own message — an audit that never ran at all is a different,
    starker fact than one that ran short, so it earns different copy, not a
    different verdict. The counter-argument (every remedy needs a working `gh`,
    unavailable by definition at total failure, so blocking "deadlocks" except
    via the settings.json emergency removal) does not survive scrutiny: it
    proves too much, since it applies equally to 7-of-8, which this gate
    already blocks; a rate-limit/API outage that happens to hit all 8 calls at
    once resolves with the same "wait and re-run" remedy as a partial one; and
    only a genuinely broken `gh` install forces the emergency exit — which was
    already the only exit for an unfixable partial failure too. `/handoff`
    remains outside _COVERAGE_BLOCKING_SKILLS and is unaffected: it still
    allows, loudly, on both partial AND total failure.

Allow condition:
    Any of:
      - matched_skill is False (different skill, different tool entirely)
      - open_count == 0 AND every org repo was successfully queried
      - args contains a carry-forward marker AND coverage is complete
      - the audit could not run at all, or ran only partially, for a skill
        outside _COVERAGE_BLOCKING_SKILLS (fail-open — but always WITH a
        system message; no degraded path is silent, see § Failure modes)

Audit shell-out:
    Iterates the 8 org-known repos (charter skills.md § Audit command),
    running, for EACH accepted wave-label form (#810):
        gh issue list --repo "noorinalabs/<repo>" --state open \\
            --label "<wave-label>" --json number
    The wave id `<N>` is derived from `cross-repo-status.json` field
    `current_wave` (e.g. "wave-16" → "16"); the audit queries BOTH the legacy
    `p<P>-wave-<N>` and the new phase-agnostic `wave-<N>` form and UNIONS the
    issue numbers per repo (gh ANDs multiple `--label` flags, so the forms are
    queried separately). This grandfathers in-flight legacy-labeled issues
    while counting new-scheme issues. The total is the sum across the repos
    that could actually be queried; any repo whose query fails is recorded by
    name and makes the result non-authoritative (a lower bound — #1226).

Merge-ready-PR exemption (issue #664, owner-adopted P4W7 retro):
    The `/wave-wrapup` gate had a chicken-and-egg: the wave's own open
    work-issues only close as part of wrapup's merge steps, but the gate
    counted them and blocked wrapup from running — forcing a merge+close
    first then a re-run. Fix: an open wave-labeled issue does NOT count
    against the blocking total if it has a *merge-ready PR targeting the
    wave branch*. "Merge-ready" is defined narrowly to guard against
    false-exempt (acceptance criterion #3):
        - the PR is OPEN and not a draft,
        - its base branch is EXACTLY the active wave branch
          `deployments/phase-<P>/wave-<M>` (derived from the same
          cross-repo-status.json phase/wave that yields the label) — an
          arbitrary PR into main or another branch does NOT qualify,
        - `mergeable == "MERGEABLE"` (no conflicts; UNKNOWN is treated as
          not-ready — conservative),
        - every status check is green (all checks SUCCESS/NEUTRAL/SKIPPED;
          any FAILURE/ERROR/pending → not-ready), and
        - the PR *declares it closes the issue* via a closing keyword in its
          body/title (`Closes #N` / `Fixes #N` / `Resolves #N`, conjugations,
          case-insensitive) — NOT a bare `#N` mention.
    Linkage caveat — why body text and not `closingIssuesReferences`: GitHub
    only registers a closing reference when the PR's base is the repository
    *default* branch. Wave-branch PRs base on `deployments/phase-<P>/wave-<M>`,
    so the structured `closingIssuesReferences` API field is ALWAYS empty for
    exactly the PRs this exemption targets (same root cause as `Closes #N` not
    auto-closing on wave-branch merges — memory feedback_gh_cli_gotchas).
    So we parse the PR's body/title for GitHub's own closing-keyword grammar
    (the same grammar GitHub parses); restricting to closing keywords keeps a
    passing `#N` mention from false-exempting an unrelated issue.
    Implementation: per repo, list open PRs based on the wave branch
    (`gh pr list --base <wave-branch> --json ...,body,title`), keep the
    merge-ready ones, extract their declared-closes issue numbers, and subtract
    that set from the open-issue list before counting. If the wave branch can't
    be derived, or any of the PR queries fail, NO exemption is applied (fail
    toward the stricter count — never false-exempt).

Failure modes (never silent — every degraded path emits operator-visible text):
    - `gh` not installed / not authenticated, or EVERY repo query failed
      (TOTAL coverage failure, `_audit_open_count` returns `total is None`) →
      the verdict splits by skill, same split as the partial case below:
        * `_COVERAGE_BLOCKING_SKILLS` (/wave-wrapup, /wave-retro) BLOCK
          (#1230). There is no open-item count at all — not a zero, no count —
          which is a total UNKNOWN and an unknown is never green
          (/session-start Step 5a). A carry-forward marker does not clear it,
          same reasoning as the partial case: the marker can only vouch for
          what the operator has SEEN, and nothing was seen this time.
        * /handoff is ALLOWED with an explicit warning naming that no repo
          could be queried. It only records session state, its degraded
          outcome is recoverable, and stranding a session mid-outage would
          push operators toward the settings.json emergency removal — which
          would disable the gate for wrapup and retro too.
      History: before #1230 this path fail-opened UNCONDITIONALLY — even for
      _COVERAGE_BLOCKING_SKILLS — making the largest blind spot (8-of-8) more
      permissive than a 1-of-8 gap the same gate already blocked. See § Block
      condition for the full resolution.
    - Network/API/quota failure on SOME repos (PARTIAL coverage, #1226) → the
      failed repos are recorded by name (`_audit_open_count`'s third return
      value) and the surviving sum is treated as a LOWER BOUND, never as an
      authoritative zero. The verdict splits by skill exactly as above:
        * `_COVERAGE_BLOCKING_SKILLS` (/wave-wrapup, /wave-retro) BLOCK. They
          write the durable "wave concluded" record and mutate wave state, and
          neither is time-critical, so waiting for the API and re-running is a
          cheap and complete remedy. A carry-forward marker does not clear it.
        * /handoff is ALLOWED with an explicit warning naming the unseen repos.
      History: before #1226 this path summed the survivors and returned a bare
      allow with NO output at all. Because `noorinalabs-main` was the only repo
      carrying wave issues, ONE failed query flipped the gate from BLOCK to a
      silent ALLOW — quieter, and strictly more dangerous, than total failure
      was at the time (#1230 has since closed that remaining gap too).
    - cross-repo-status.json missing or malformed → cannot determine wave,
      allow with warning.
    - current_wave field missing / not a "wave-<N>" string → cannot derive
      label, allow with warning.
    - Wall-clock budget: 8 gh calls × ~1.5s ≈ 12s. settings.json timeout
      should be 30s.

Coverage contract (load-bearing — #1226):
    `_open_issue_numbers_for_label` MUST return None, never `[]`, on any query
    failure. `[]` means "queried this repo, it has no open wave issues"; None
    means "could not see this repo". The entire gate rests on that distinction,
    so any future change to the transport — a retry, a GraphQL→REST fallback
    (#1224), a cache — must preserve it. A fallback that swallows an error and
    returns an empty list would recreate this exact silent zero one layer down,
    where the aggregator can no longer detect it.

Bypass policy:
    No in-band override flag. The whole point of the hook is to break the
    "this one's fine, just say concluded" rationalization that put the
    P2W9 incident on owner's desk. If the gate fires, the only paths are
    (a) close the open items, (b) add a carry-forward block to args, or
    (c) emergency override by removing the hook entry from settings.json.
    This matches Hook 15's stance (no in-band override).

Exit codes (per Claude Code hook convention):
    0 — allow (not a matched skill; audit zero WITH full coverage; args has
        carry-forward WITH full coverage; infra failure fail-open for a skill
        outside _COVERAGE_BLOCKING_SKILLS, always accompanied by a system
        message)
    2 — block (matched skill AND open count > 0 without a carry-forward marker,
        OR any audit-coverage gap — PARTIAL (some org repos queried, some not,
        #1226) or TOTAL (no repo queried at all, #1230) — for a
        _COVERAGE_BLOCKING_SKILLS skill. See § Block condition for the
        all-vs-some history and why both now exit 2.)

Promotion provenance:
    memory feedback_honest_audit_over_conclusion_claim (2026-04-22) →
    charter skills.md § Wave Lifecycle — Open-Item Audit (PR #193) →
    this hook (issue #195). Second worked example of the
    memory→charter→hook promotion pipeline ratified 2026-04-19 (Hook 15
    was the first).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from annunaki_log import log_pretooluse_block  # noqa: E402

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib")
sys.path.insert(0, os.path.abspath(_LIB_DIR))
from org_repos import ALL_REPOS  # noqa: E402

# Skills gated by this hook. Exact match against tool_input.skill.
_GATED_SKILLS = frozenset({"wave-wrapup", "wave-retro", "handoff"})

# Subset of _GATED_SKILLS for which an INCOMPLETE audit — any org repo the
# hook could not query, whether PARTIAL (#1226) or TOTAL (#1230) — is itself a
# block, independent of the count it did manage to compute.
#
# `wave-wrapup` and `wave-retro` write the durable record that a wave is
# concluded: they merge the wave branch, close issues, advance the status file,
# and fix the retrospective history. Neither is time-critical, so "wait for the
# API and re-run" is a cheap and complete remedy, and an audit that could not
# see a repo is an UNKNOWN — never green (/session-start Step 5a). This applies
# whether ONE repo went unqueried or all EIGHT did: a bigger blind spot cannot
# be the more permissive outcome (#1230 closed the asymmetry where TOTAL
# failure used to fail-open unconditionally while PARTIAL failure blocked).
#
# `handoff` is deliberately EXCLUDED, from both the partial AND total case. It
# only *records* session state; its degraded outcome (a thinner pickup prompt)
# is recoverable, and the Stop hook writes a handoff automatically regardless.
# Hard-blocking it during exactly the kind of API outage that makes recording
# state valuable would strand a session — and the only escape is the
# settings.json emergency removal, which would disable the gate for wrapup and
# retro too. So /handoff degrades to a loud, explicit allow-with-warning naming
# the repos it could not see (or that none could be seen at all): not green,
# but not a dead end either.
_COVERAGE_BLOCKING_SKILLS = frozenset({"wave-wrapup", "wave-retro"})

# Org-known repos for cross-repo audit. Sourced from org_repos.py (main#1118
# / audit G6) — the single source of truth for the org repo list; the charter
# skills.md § Audit command example command should stay in sync with it too,
# but this constant itself no longer hand-copies the list.
_ORG_REPOS = ALL_REPOS

# Carry-forward detection patterns (case-insensitive). Any one suffices.
# Anchored loosely — looking for explicit author intent, not accidental phrasing.
_CARRY_FORWARD_PATTERNS = (
    re.compile(r"carry[\s-]forward\s*:", re.IGNORECASE),
    re.compile(r"^#{1,6}\s+carry[\s-]forward\b", re.IGNORECASE | re.MULTILINE),
    re.compile(r"#\d+\s*(?:->|→)\s*[A-Za-z_]", re.IGNORECASE),
)

# PR-body/title closing-keyword → issue linkage for the merge-ready-PR
# exemption (#664). GitHub's documented closing keywords (close/closes/closed,
# fix/fixes/fixed, resolve/resolves/resolved), optional colon, then `#<N>`.
# Requires the keyword (not a bare `#N` mention) so a passing reference can't
# false-exempt an unrelated issue. The mandatory `[\s:]+` separator before `#`
# also excludes cross-repo `owner/repo#N` refs (the `#` there is preceded by a
# repo-name char, not whitespace/colon).
_CLOSING_KEYWORD_RE = re.compile(
    r"\b(?:close[sd]?|fix(?:es|ed)?|resolve[sd]?)\b[\s:]+#(\d+)\b",
    re.IGNORECASE,
)

# Path to cross-repo-status.json relative to this hook file.
_STATUS_PATH = Path(__file__).resolve().parent.parent.parent / "cross-repo-status.json"

# gh subprocess timeout per repo (seconds). 8 repos × this = total budget.
_PER_REPO_TIMEOUT_SECONDS = 3


def _read_phase_num(data: dict) -> int | None:
    """Recover the active phase number from a loaded status dict, or None (#831).

    `current_phase` (the live integer) is the AUTHORITATIVE phase pointer. The
    legacy top-level `phase` ("phase-{N}") string was never advanced past
    phase-4 — deriving the wave branch/label from it yielded a wrong
    `deployments/phase-4/...` (#831), so it is retired from the status file. A
    defensive `phase`-string fallback is retained for robustness and to mirror
    the sibling readers `validate_wave_label_evidence._read_current_phase` and
    `post_wave_kickoff_comment._phase_from_status` (#810).
    """
    cp = data.get("current_phase")
    if cp is not None:
        try:
            return int(cp)
        except (TypeError, ValueError):
            pass
    m = re.fullmatch(r"phase-(\d+)", str(data.get("phase", "")))
    if m:
        return int(m.group(1))
    return None


def _read_phase_wave_nums() -> tuple[int, int] | None:
    """Return the active (phase_num, wave_num) from cross-repo-status.json or None.

    Reads `cross-repo-status.json`, requires `wave_active` truthy, and parses
    the authoritative `current_phase` integer (via `_read_phase_num`) and the
    `current_wave` ("wave-<M>") field. Returns None on any failure (missing
    file, malformed JSON, inactive wave, missing or unparseable fields). Single
    source of truth for both the wave *label* and the wave *branch* derivations
    below so they cannot drift apart.
    """
    try:
        data = json.loads(_STATUS_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None

    if not data.get("wave_active"):
        return None

    wave_match = re.fullmatch(r"wave-(\d+)", str(data.get("current_wave", "")))
    phase_num = _read_phase_num(data)
    if not wave_match or phase_num is None:
        return None

    return phase_num, int(wave_match.group(1))


def _read_current_wave_labels() -> list[str] | None:
    """Return the active wave's labels in ALL accepted forms, or None.

    Returns BOTH the legacy phase-prefixed `p{N}-wave-{M}` AND the new
    phase-agnostic `wave-{X}` form (#810). The audit must count issues under
    either label so the transition is seamless: in-flight issues labeled the
    legacy way (e.g. this very wave's `p6-wave-16`) and issues created under the
    new scheme (`wave-16`) both register against the active wave. The two share
    the same global wave id `X == M` (Design B #804). Returns None on any
    failure (missing file, malformed JSON, missing fields, unparseable wave).
    """
    nums = _read_phase_wave_nums()
    if nums is None:
        return None
    phase_num, wave_num = nums
    return [f"p{phase_num}-wave-{wave_num}", f"wave-{wave_num}"]


def _read_current_wave_branch() -> str | None:
    """Return the active wave branch (e.g. 'deployments/phase-2/wave-10') or None.

    Derives the branch from the same cross-repo-status.json phase/wave that
    yields the label (see `_read_phase_wave_nums`), so the merge-ready-PR
    exemption (#664) targets exactly the branch the wave's PRs base on.
    Returns None on any failure.
    """
    nums = _read_phase_wave_nums()
    if nums is None:
        return None
    phase_num, wave_num = nums
    return f"deployments/phase-{phase_num}/wave-{wave_num}"


def _open_issue_numbers_for_label(repo: str, label: str) -> list[int] | None:
    """Return open-issue numbers for `noorinalabs/<repo>` filtered by one `label`.

    Returns the list of issue numbers on success (possibly empty), None on
    subprocess failure (gh missing, network error, auth failure).

    The None-vs-`[]` distinction is load-bearing for the whole gate (#1226):
    `[]` asserts "this repo was queried and has no open wave issues", None
    asserts only "this repo could not be seen". Any future transport change
    here — retry, GraphQL→REST fallback (#1224), caching — MUST keep returning
    None on failure. Collapsing a failure to `[]` would recreate the silent
    zero one layer below `_audit_open_count`, where it can no longer be
    detected.
    """
    try:
        result = subprocess.run(
            [
                "gh",
                "issue",
                "list",
                "--repo",
                f"noorinalabs/{repo}",
                "--state",
                "open",
                "--label",
                label,
                "--json",
                "number",
            ],
            capture_output=True,
            text=True,
            timeout=_PER_REPO_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None

    if result.returncode != 0:
        return None

    out = result.stdout.strip()
    if not out:
        return []
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return None
    try:
        return [int(item["number"]) for item in data]
    except (TypeError, KeyError, ValueError):
        return None


def _open_issue_numbers_for_repo(repo: str, labels: list[str]) -> list[int] | None:
    """Return the UNION of open-issue numbers across each label form (#810).

    `gh issue list --label A --label B` ANDs the labels, so each accepted wave
    label (legacy `p{N}-wave-{M}` AND new `wave-{X}`) is queried separately and
    the results are unioned — an issue carrying EITHER form counts once. Returns
    None if ANY per-label query fails (so the caller fails open per-repo, the
    pre-existing conservative-toward-allow stance), the deduplicated number list
    otherwise.
    """
    union: set[int] = set()
    for label in labels:
        nums = _open_issue_numbers_for_label(repo, label)
        if nums is None:
            return None
        union.update(nums)
    return sorted(union)


def _checks_green(rollup: list | None) -> bool:
    """Return True iff every status check in `rollup` is passing (or none exist).

    `rollup` is the `statusCheckRollup` array from `gh pr list --json`. Each
    element is either a CheckRun (has `conclusion` once `status == COMPLETED`)
    or a StatusContext (has `state`). Green means:
        - CheckRun: status COMPLETED and conclusion in {SUCCESS, NEUTRAL, SKIPPED}
        - StatusContext: state == SUCCESS
    Any pending (non-COMPLETED / PENDING / EXPECTED) or failing check makes the
    whole rollup not-green. An empty/absent rollup is treated as green (no
    checks configured) — the base-branch + linkage guards carry the
    false-exempt protection in that case.
    """
    if not rollup:
        return True
    for check in rollup:
        if not isinstance(check, dict):
            return False
        if "conclusion" in check or "status" in check:
            # CheckRun shape.
            if str(check.get("status", "")).upper() != "COMPLETED":
                return False
            if str(check.get("conclusion", "")).upper() not in {
                "SUCCESS",
                "NEUTRAL",
                "SKIPPED",
            }:
                return False
        elif "state" in check:
            # StatusContext shape.
            if str(check.get("state", "")).upper() != "SUCCESS":
                return False
        else:
            # Unrecognized shape → conservatively not-green (never false-exempt).
            return False
    return True


def _pr_is_merge_ready(pr: dict, wave_branch: str) -> bool:
    """Return True iff `pr` is a merge-ready PR targeting `wave_branch`.

    Narrow definition to guard against false-exempt (issue #664 acceptance #3):
    open + not draft + base == wave_branch + mergeable (no conflicts, not
    UNKNOWN) + all status checks green. The `--base` filter on `gh pr list`
    already constrains the base; this re-checks `baseRefName` defensively so a
    mis-filtered or future call site can't slip an off-branch PR through.
    """
    if not isinstance(pr, dict):
        return False
    if pr.get("isDraft"):
        return False
    if str(pr.get("state", "OPEN")).upper() != "OPEN":
        return False
    if pr.get("baseRefName") != wave_branch:
        return False
    if str(pr.get("mergeable", "")).upper() != "MERGEABLE":
        return False
    return _checks_green(pr.get("statusCheckRollup"))


def _closing_refs_in_text(text: str) -> set[int]:
    """Return the issue numbers a PR's body/title declares it will close.

    Parses GitHub's documented closing-keyword syntax (`Closes #N`, `Fixes #N`,
    `Resolves #N`, and their conjugations, optional colon, case-insensitive).

    Why text and not the structured `closingIssuesReferences` API field:
    GitHub only *registers* a closing reference when the PR's base is the
    repository default branch. Wave-branch PRs base on
    `deployments/phase-<P>/wave-<M>`, so `closingIssuesReferences` is ALWAYS
    empty for exactly the PRs this exemption targets (the same reason
    `Closes #N` doesn't auto-close on wave-branch merges — see memory
    `feedback_gh_cli_gotchas`). The PR body's closing keyword is the
    actual linkage signal for wave PRs, and we parse the *same* keyword grammar
    GitHub itself parses — restricting to closing keywords (not a bare `#N`
    mention) keeps a passing reference from false-exempting an unrelated issue
    (#664 acceptance #3).

    Bare `owner/repo#N` cross-repo refs are intentionally not matched (a
    different repo's issue isn't in this repo's wave-label set anyway).
    """
    if not text:
        return set()
    # Don't treat `org/repo#N` (cross-repo) as a local close — require the `#`
    # to NOT be immediately preceded by a repo-name character.
    return {int(m.group(1)) for m in _CLOSING_KEYWORD_RE.finditer(text)}


def _mergeready_exempt_issues(repo: str, wave_branch: str) -> set[int]:
    """Return the set of issue numbers exempt via a merge-ready wave-branch PR.

    Lists open PRs based on `wave_branch`, keeps the merge-ready ones
    (`_pr_is_merge_ready`), and unions the issues each declares it closes (via
    `_closing_refs_in_text` over body+title). Returns an empty set on PR-list
    failure — failing toward NO exemption keeps the gate strict (never
    false-exempt; issue #664 acceptance #3).
    """
    try:
        result = subprocess.run(
            [
                "gh",
                "pr",
                "list",
                "--repo",
                f"noorinalabs/{repo}",
                "--state",
                "open",
                "--base",
                wave_branch,
                "--json",
                "number,isDraft,state,baseRefName,mergeable,statusCheckRollup,body,title",
            ],
            capture_output=True,
            text=True,
            timeout=_PER_REPO_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return set()

    if result.returncode != 0:
        return set()

    out = result.stdout.strip()
    if not out:
        return set()
    try:
        prs = json.loads(out)
    except json.JSONDecodeError:
        return set()
    if not isinstance(prs, list):
        return set()

    exempt: set[int] = set()
    for pr in prs:
        if not _pr_is_merge_ready(pr, wave_branch):
            continue
        text = f"{pr.get('body', '') or ''}\n{pr.get('title', '') or ''}"
        exempt |= _closing_refs_in_text(text)
    return exempt


def _count_open_for_repo(repo: str, labels: list[str], wave_branch: str | None) -> int | None:
    """Return the *blocking* open-issue count for `noorinalabs/<repo>`.

    Counts open issues carrying ANY accepted wave-label form in `labels` (#810),
    minus those exempted by a merge-ready PR targeting `wave_branch` (issue
    #664). Returns the integer count on success, None on issue-list subprocess
    failure (so the caller can fail-open on full infrastructure failure). When
    `wave_branch` is None, no exemption is applied (every open wave issue counts).
    """
    numbers = _open_issue_numbers_for_repo(repo, labels)
    if numbers is None:
        return None
    if not numbers:
        return 0
    if wave_branch is None:
        return len(numbers)

    exempt = _mergeready_exempt_issues(repo, wave_branch)
    return sum(1 for n in numbers if n not in exempt)


def _audit_open_count(
    labels: list[str], wave_branch: str | None
) -> tuple[int | None, dict[str, int], list[str]]:
    """Run the cross-repo audit. Returns (total_or_None, per_repo_counts, unqueried).

    `total_or_None` is None only if EVERY repo's audit failed (full
    infrastructure failure → fail-open). Otherwise it's the sum over the repos
    that were successfully queried.

    `unqueried` names every repo whose query failed, in `_ORG_REPOS` order. It
    is the audit's COVERAGE signal and the reason this function returns three
    values instead of two (#1226): when `unqueried` is non-empty the total is a
    **lower bound**, not a count, and callers MUST NOT read `total == 0` as
    "the wave is clean". Before #1226 the failed repos were dropped with a bare
    `continue`, conflating "queried, found zero" with "could not look" — and
    because `noorinalabs-main` was the only repo carrying wave issues, ONE
    failed query summed to a confident 0 and flipped the gate to a silent
    allow.

    Each repo's count excludes wave issues exempted by a merge-ready PR on
    `wave_branch` (issue #664). `per_repo_counts` maps repo name → blocking
    count for repos with a non-zero blocking count. Repos with zero blocking
    issues (none open, or all exempted) are omitted from `per_repo_counts`;
    repos that could not be queried appear in `unqueried` instead.
    """
    per_repo: dict[str, int] = {}
    unqueried: list[str] = []
    successes = 0

    for repo in _ORG_REPOS:
        count = _count_open_for_repo(repo, labels, wave_branch)
        if count is None:
            unqueried.append(repo)
            continue
        successes += 1
        if count > 0:
            per_repo[repo] = count

    if successes == 0:
        return None, per_repo, unqueried

    total = sum(per_repo.values())
    return total, per_repo, unqueried


def _has_carry_forward(args: str) -> bool:
    """Return True iff `args` contains an explicit carry-forward marker."""
    if not args:
        return False
    return any(pattern.search(args) for pattern in _CARRY_FORWARD_PATTERNS)


def _format_per_repo(per_repo: dict[str, int], unqueried: Sequence[str] = ()) -> str:
    """Format the per-repo open-item summary, including audit-coverage gaps.

    `unqueried` names the repos whose query failed; each is listed explicitly as
    NOT AUDITED so the summary can never imply the audit saw the whole org when
    it did not (#1226). The old unconditional "(no per-repo breakdown — all
    audited repos returned 0)" line was an actively false claim whenever a repo
    had been skipped: it read as a clean sweep of eight repos when it could
    describe a clean sweep of seven and a blind spot over the eighth.
    """
    lines = [f"  - noorinalabs/{repo}: {per_repo[repo]} open" for repo in sorted(per_repo)]
    if not lines:
        if unqueried:
            lines.append("  (no open items among the repos that COULD be queried)")
        else:
            lines.append(f"  (no per-repo breakdown — all {len(_ORG_REPOS)} repos returned 0)")
    for repo in sorted(unqueried):
        lines.append(f"  - noorinalabs/{repo}: NOT AUDITED (query failed — count unknown)")
    return "\n".join(lines)


def _block(skill_name: str, args: str, reason: str) -> dict:
    """Build a block result and record it to the annunaki log.

    Shared by the open-items block and the incomplete-coverage block (#1226) so
    a new blocking path cannot be added without also being logged.
    """
    result = {"decision": "block", "reason": reason}
    log_pretooluse_block(
        "validate_wave_audit",
        f"skill={skill_name} args={args[:200] if args else '<empty>'}",
        reason,
        tool_name="Skill",
    )
    return result


def check(input_data: dict) -> dict | None:
    """Check the wave-audit precondition. Returns result dict if blocking, None if allowed.

    Public API matches the dispatcher convention. Returns None to allow,
    a dict with `decision: "block"` to block, or a dict with
    `decision: "allow"` plus `systemMessage` to allow with a warning.
    """
    tool_name = input_data.get("tool_name", "")
    if tool_name != "Skill":
        return None

    tool_input = input_data.get("tool_input", {})
    skill_name = tool_input.get("skill", "")

    if skill_name not in _GATED_SKILLS:
        return None

    labels = _read_current_wave_labels()
    if labels is None:
        return {
            "decision": "allow",
            "systemMessage": (
                f"WARNING: Wave-audit hook could not determine an active wave label "
                f"from cross-repo-status.json. Allowing /{skill_name} to proceed without "
                "an audit. If you are claiming a wave is concluded, run the canonical "
                "audit manually (charter skills.md § Wave Lifecycle — Audit command)."
            ),
        }

    # Display form for messages: both accepted label forms (#810) are queried.
    label_display = " | ".join(f"`{lbl}`" for lbl in labels)

    # Wave branch drives the merge-ready-PR exemption (#664). Derived from the
    # same status fields as the label, so if the label resolved, the branch
    # does too; None only on a race that mutates the file mid-check, in which
    # case the audit simply applies no exemption (stricter, never false-exempt).
    wave_branch = _read_current_wave_branch()

    total, per_repo, unqueried = _audit_open_count(labels, wave_branch)
    args = tool_input.get("args", "")

    # TOTAL coverage failure — no repo queried at all. Resolved by #1230: this
    # branch used to fail-open UNCONDITIONALLY, ahead of every hard block below
    # (including the _COVERAGE_BLOCKING_SKILLS check further down), which made
    # the largest blind spot (8-of-8 unreadable) MORE permissive than a 1-of-8
    # gap the same gate already blocked. That inversion is exactly the shape
    # memory feedback_gate_early_allow_is_the_failopen warns about (#981: "a
    # verify-gate's hole is usually an allow-with-warning branch
    # short-circuiting AHEAD of the hard-blocks") — noted here, at the site, so
    # a future change to this branch doesn't reopen it.
    #
    # Now: for _COVERAGE_BLOCKING_SKILLS, total failure is treated exactly like
    # a PARTIAL coverage gap (§ `if unqueried:` below) — it BLOCKS, with its own
    # message ("could not run at all" vs "ran short" are different enough
    # facts to warrant different copy, per #1230's ask). A carry-forward marker
    # does not clear it, same as partial: the marker can only vouch for what
    # the operator has SEEN, and nothing was seen this time. For every other
    # gated skill (/handoff), the fail-open-with-warning behavior is unchanged.
    if total is None:
        if skill_name in _COVERAGE_BLOCKING_SKILLS:
            return _block(
                skill_name,
                args,
                reason=(
                    f"BLOCKED: /{skill_name} cannot claim wave conclusion — the open-item "
                    f"audit could not run AT ALL.\n\n"
                    f"Could not query any of the {len(_ORG_REPOS)} org repo(s) for label(s) "
                    f"{label_display} (gh CLI missing, unauthenticated, or every call "
                    "failed). There is NO open-item count for this wave — not a zero, no "
                    "count at all.\n\n"
                    "Charter § Wave Lifecycle — Open-Item Audit requires the audit to RUN, "
                    "not merely to return a number. A total outage is a total UNKNOWN, and "
                    "an unknown is never green (/session-start Step 5a) — the same "
                    "principle that already blocks a PARTIAL coverage gap (#1226) applies "
                    "with at least as much force to a complete one: a bigger blind spot "
                    "cannot be the more permissive outcome (#1230).\n\n"
                    "To proceed:\n"
                    "  1. Diagnose the failure — usually auth (`gh auth status`), a "
                    "missing/broken `gh` install, or a full API/quota outage (`gh api "
                    f"rate_limit`). Fix it or wait for the quota window, then re-run "
                    f"/{skill_name}, OR\n"
                    "  2. Run the canonical audit by hand once `gh` is working and close "
                    "or carry-forward whatever it finds, then re-run.\n\n"
                    "A carry-forward marker does NOT clear this block: the marker "
                    "acknowledges items the operator has SEEN, and NO repo was read this "
                    "time.\n\n"
                    "There is no in-band bypass flag — see charter/hooks/catalog-13-17.md "
                    "§ Hook 17 for emergency procedure."
                ),
            )
        # Not coverage-blocking (/handoff): allow, but never bare.
        return {
            "decision": "allow",
            "systemMessage": (
                f"WARNING: Wave-audit hook could not query any of the {len(_ORG_REPOS)} "
                f"org repos for label(s) {label_display} (gh CLI missing, unauthenticated, "
                f"or all calls failed). There is NO open-item count for this wave — not a "
                f"zero, no count at all.\n"
                f"Allowing /{skill_name} to proceed, because every remedy for this failure "
                "needs a working `gh` and blocking would leave no way out. Do NOT state or "
                "imply the wave is clean or concluded — run the canonical audit manually "
                "(charter skills.md § Wave Lifecycle — Audit command) first."
            ),
        }

    # `total` sums only the repos the audit could actually see. With any repo
    # unqueried it is a LOWER BOUND, and the coverage gap has to travel with
    # every message built from it (#1226).
    unqueried_display = ", ".join(f"noorinalabs/{repo}" for repo in sorted(unqueried))
    coverage_caveat = (
        (
            f"\n\nAUDIT COVERAGE: {len(unqueried)} of {len(_ORG_REPOS)} org repo(s) "
            f"could not be queried ({unqueried_display}). The count above is a "
            "LOWER BOUND over the repos that were reachable, not an org total."
        )
        if unqueried
        else ""
    )

    if total > 0 and not _has_carry_forward(args):
        return _block(
            skill_name,
            args,
            reason=(
                f"BLOCKED: /{skill_name} cannot claim wave conclusion. "
                f"Charter § Wave Lifecycle — Open-Item Audit requires zero open items "
                f"for the active wave OR an explicit carry-forward list in the skill's args.\n\n"
                f"Active wave label(s): {label_display}\n"
                f"Open items across the org: {total}\n"
                f"Per-repo breakdown:\n{_format_per_repo(per_repo, unqueried)}"
                f"{coverage_caveat}\n\n"
                "To proceed, either:\n"
                f"  1. Close the open items above, then re-run /{skill_name}, OR\n"
                f"  2. Pass an explicit carry-forward list in args. Recognized markers:\n"
                "     - 'Carry-forward: #N → next-wave, #M → backlog' inline\n"
                "     - '## Carry-forward' markdown heading followed by item list\n"
                "     - '#N → destination' arrow patterns naming items individually\n\n"
                "Note (#664): an open wave issue is already auto-exempt from this count "
                "if it has a merge-ready PR (open, not draft, mergeable, all checks green) "
                f"based on `{wave_branch or '<wave-branch>'}`. The items above are NOT "
                "exempt — their wave-branch PR is missing, conflicting, red, or still in "
                f"review. Get those PRs merge-ready and re-run /{skill_name}.\n\n"
                "There is no in-band bypass flag — see charter/hooks/catalog-13-17.md "
                "§ Hook 17 for emergency procedure."
            ),
        )

    # Below here the *visible* count alone would allow: it is zero, or a
    # carry-forward marker acknowledges it. Neither statement can be trusted
    # while a repo went unread, so an incomplete audit is decided on its own
    # terms rather than folded into the count (#1226).
    if unqueried:
        if skill_name in _COVERAGE_BLOCKING_SKILLS:
            return _block(
                skill_name,
                args,
                reason=(
                    f"BLOCKED: /{skill_name} cannot claim wave conclusion — the open-item "
                    f"audit was INCOMPLETE.\n\n"
                    f"Could not query {len(unqueried)} of {len(_ORG_REPOS)} org repo(s): "
                    f"{unqueried_display}\n"
                    f"Active wave label(s): {label_display}\n"
                    f"Open items among the repos that WERE queried: {total} "
                    "(a lower bound, not an org total)\n"
                    f"Per-repo breakdown:\n{_format_per_repo(per_repo, unqueried)}\n\n"
                    "Charter § Wave Lifecycle — Open-Item Audit requires the audit to RUN, "
                    "not merely to return a number. A repo that could not be queried is an "
                    "UNKNOWN, and an unknown is never green (/session-start Step 5a). One "
                    "failed query on the single repo carrying the wave's issues is enough "
                    "to turn a real backlog into an apparent zero (#1226).\n\n"
                    "To proceed:\n"
                    "  1. Diagnose the query failure — usually auth (`gh auth status`), a "
                    "network blip, or API rate/quota exhaustion (`gh api rate_limit`). Wait "
                    f"for the quota window to reset, then re-run /{skill_name}, OR\n"
                    "  2. Run the canonical audit by hand for the repo(s) above and close "
                    "or carry-forward whatever it finds, then re-run.\n\n"
                    "A carry-forward marker does NOT clear this block: the marker "
                    "acknowledges items the operator has SEEN, and these repos were never "
                    "read.\n\n"
                    "There is no in-band bypass flag — see charter/hooks/catalog-13-17.md "
                    "§ Hook 17 for emergency procedure."
                ),
            )
        # Not coverage-blocking (/handoff): allow, but never bare — see
        # _COVERAGE_BLOCKING_SKILLS for why this skill degrades instead of stopping.
        return {
            "decision": "allow",
            "systemMessage": (
                f"WARNING: the wave open-item audit for /{skill_name} was INCOMPLETE — "
                f"{len(unqueried)} of {len(_ORG_REPOS)} org repo(s) could not be queried "
                f"({unqueried_display}).\n"
                f"Active wave label(s): {label_display}\n"
                f"Open items among the repos that WERE queried: {total} — treat this as a "
                "LOWER BOUND, not an org total.\n"
                f"Per-repo breakdown:\n{_format_per_repo(per_repo, unqueried)}\n"
                f"Allowing /{skill_name} to proceed, because recording session state must "
                "never be strandable by a transient API failure. Do NOT state or imply the "
                "wave is clean or concluded — re-run the canonical audit first."
            ),
        }

    if total > 0:
        # Full coverage, open items, carry-forward marker present.
        return {
            "decision": "allow",
            "systemMessage": (
                f"NOTE: {total} open item(s) for {label_display} across {len(per_repo)} "
                f"repo(s); carry-forward marker detected in args, allowing /{skill_name} "
                f"to proceed.\nPer-repo open counts:\n{_format_per_repo(per_repo, unqueried)}\n"
                "Verify the carry-forward list in your output names every item above."
            ),
        }

    # Full coverage, genuinely zero open items — the only silent allow.
    return None


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
