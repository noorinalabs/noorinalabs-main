#!/usr/bin/env python3
"""PreToolUse hook: Require TWO PR review comments before merge.

Blocks `gh pr merge` unless the PR has at least two reviews from distinct
non-authors, using either formal GitHub reviews or charter-format
comment-based reviews from different team members. Honors the
Single-Reviewer Exception for wave-bootstrap PRs reviewed by a charter-
enforcer role.

Input Language:
  Fires on:      PreToolUse Bash
  Matches:       gh pr merge [{N}] [--repo {OWNER/REPO}] [--squash|--merge|--rebase]
                             [--admin] [--auto]   — including when chained via
                             && / || / | / ; after env-var assignments.
  Does NOT match: gh pr list, gh pr view, gh pr checks, gh pr create,
                  git merge, git pull.
  Flag pass-through:
    --repo   → forwarded to `gh pr view` and comment fetch so the hook checks
               the PR in the repo the user named, not the cwd-resolved repo.
               A `--repo`/`-R` value the gate CANNOT resolve to an OWNER/NAME —
               an unexpanded shell variable (`-R $DA`, which the hook sees
               pre-expansion) or a value with no `/` — HARD BLOCKS (#981): a
               merge whose target repo is unknown cannot be verified, so it
               fails CLOSED with a diagnostic that distinguishes the
               unexpanded-variable case (fix: pass a literal `--repo
               owner/name`) from a generic fetch failure (fix: retry / check
               auth). Pre-#981 this branch returned allow-with-warning and let
               four P9W25 da merges bypass the 2-reviewer gate.
    --admin  → short-circuits (emergency override — allows merge).

  Batch-loop guard (#567, narrowed #886, broadened #894/#897): a `gh pr merge`
  with NO resolvable literal PR number located INSIDE a for/while/until loop body
  (e.g. `for pr in 48 49; do gh pr merge "$pr" …; done`) is HARD BLOCKED. The
  literal-PR parse cannot resolve a non-integer OR absent argument, so the gate
  would fail-open and merge every iteration unverified (observed P3W11 + P3W13).
  The
  operator is told to run one literal merge per call so each PR is gate-checked.
  The merge must sit between a `do` and its matching `done` to trip the guard —
  an unrelated loop in the same block (e.g. a `gh run rerun "$r" --failed`
  staleness recheck) alongside a non-loop variable merge does NOT (#886). #894
  extended the matched argument forms from `$pr`/`${pr}` to ANY non-literal
  argument — also `${prs[$i]}`, `$(get_pr)`, and a subshell-wrapped
  `(gh pr merge $pr)`. #897 further covers a NO-positional-argument merge — the
  current-branch form `for b in …; do git checkout $b && gh pr merge; done`,
  which with `pr_number=None` sweeps each checked-out branch's PR unverified. A
  BARE `gh pr merge` OUTSIDE any loop still PASSES (legitimate current-branch
  merge, #886). `--admin` still overrides; a literal `gh pr merge 54` is
  unaffected. Conservative DECIDE-tier shape (no conditional-allow) per
  `feedback_safety_direction_over_ux_friction`.

Charter-format review comments (canonical per `pull-requests.md` § Comment-Based Reviews,
resolves #233):

  Requestor: <comment author>     # always the team member POSTING the comment
  Requestee: <comment target>     # always the team member ADDRESSED by the comment
  RequestOrReplied: <Request|Reply|Approved|ChangesRequested>
  TechDebt: none | #15, #16, ...

  Direction by RequestOrReplied:
    - Request          — Requestor=PR author,  Requestee=reviewer (NOT a verdict)
    - Reply / Replied  — Requestor=replier,    Requestee=person-being-replied-to (NOT a verdict)
    - Approved         — Requestor=reviewer,   Requestee=PR author (verdict)
    - ChangesRequested — Requestor=reviewer,   Requestee=PR author (verdict)

  The reviewer for a verdict comment is the comment AUTHOR — i.e. the
  Requestor. The prior hook counted distinct Requestee values across
  Approved/ChangesRequested comments, which on verdicts is always the PR
  author and so collapsed to a single value (resolves #244).

Reviewer counting rule (resolves #244):
  - Verdict comments (Approved / ChangesRequested) → Requestor is the reviewer
  - Request / Reply comments → not reviews; do not contribute to reviewer count
  - Two-reviewer rule satisfied when there are TWO DISTINCT REVIEWER NAMES across
    Approved comments, neither of which is the PR author.

Verdict staleness — content binding (resolves #950):
  A verdict is only evidence that someone reviewed THE CODE BEING MERGED if it
  was cast at or after that code arrived. Pre-#950 the gate never compared the
  two: it counted every `Approved` trailer regardless of when it was posted, so
  an approval cast against commit `A` still counted after the author force-pushed
  `B`, `C`, `D`. Observed three times on 2026-07-11 (da#423, ip#130 x2); on
  da#423 the gate would have called the PR merge-ready on two `Approved`
  trailers, one of which approved the revision that deleted the Prophet's
  daughter and had since been rewritten precisely because it was wrong.

  The binding is to AUTHORED CONTENT, not to the head sha:

    T_content = committer timestamp of the latest NON-MERGE commit on the branch
    a verdict is STALE  iff  comment.created_at < T_content

  Binding to the head sha instead would invalidate every approval in the org the
  moment a branch is updated from `main` (`gh api -X PUT .../update-branch`, the
  routine BEHIND → CLEAN step before any merge): a merge commit moves the head
  WITHOUT changing what the reviewer read. Merge commits (>= 2 parents) are
  therefore excluded from T_content — the same lesson as
  `feedback_commit_author_gate_exclude_merges`: a gate over a commit range that
  does not exclude merge commits is corrupted by routine mechanics. This is the
  distinction GitHub's own "dismiss stale reviews when new commits are pushed"
  makes; we reimplemented the reviewer gate and omitted the staleness half.

  A stale verdict is not hidden or deleted — it is simply not counted, and the
  block message names it, its timestamp, and the commit that invalidated it.
  Staleness applies to comment verdicts AND formal GitHub reviews alike.

  Fail-closed (`feedback_safety_direction_over_ux_friction`): if the commit list
  cannot be fetched, T_content is unknown, so NO verdict's freshness can be
  established — the hook HARD BLOCKS with a diagnostic rather than reverting to
  counting everything. A verdict whose own timestamp is missing/unparseable is
  likewise treated as stale, not as fresh.

  LIMITATION — necessary, NOT sufficient. Read this before trusting the gate.

  Timestamp binding proves a verdict was CAST AFTER the newest authored commit.
  It CANNOT prove the reviewer READ that commit. A reviewer who reads `A`, then
  posts a verdict after `B` has landed — because they were slow, or were replying
  to an earlier thread, or simply did not refetch — produces a verdict this hook
  scores as CURRENT even though its findings pertain to code that no longer
  exists. This was observed on da#423 itself: a `ChangesRequested` at 04:25:31
  postdates the 04:09:36 head and therefore counts as current, but its findings
  were against the PREVIOUS head and had already been fixed.

  No timestamp can close that gap. Closing it requires binding a verdict to the
  sha the reviewer actually read — which is exactly what GitHub's native review
  API does and what our comment-trailer convention does not. This hook removes a
  whole class of false-positive approvals (a verdict that PROVABLY predates the
  code); it does not, and cannot, certify that a counted verdict was informed.

  State this honestly wherever the gate is described. An overstated guard is how
  people come to trust a gate that cannot see the thing it exists to catch —
  which is the same defect class (`a gate derived from an artifact it does not
  bind to`) that produced #950 in the first place.

Reviewer dedup key:
  The reviewer set is keyed on the FULL reviewer name (lowercased), not on
  the lastname. Two distinct reviewers with the same lastname (e.g.,
  "Lucas Ferreira" and "Santiago Ferreira") are counted as TWO reviewers
  toward the two-peer-review requirement (issue #164).

  The author-equality check — which Requestor is the PR author and is
  therefore NOT a peer reviewer — used to compare lastnames alone, on the
  reasoning that the branch `{Initial}.{Lastname}/...` gave us nothing else.
  It gave us the initial. So the #164 collision reappeared here in a second
  form (main#1172): on `L.Ferreira/1151-…`, Santiago Ferreira's Approved was
  discarded as a self-review and the PR sat at 1 of 2 approvals, while the
  same collision made `validate_review_comment_format` refuse to let him post
  the verdict at all. Both now compare first-initial + lastname through the
  one shared `charter_trailer.is_branch_author`, so a fix to who-counts-as-
  whom cannot land in one hook and not the other. A true self-review still
  excludes: the author's own initial and surname both match their branch.

Single-Reviewer Exception (resolves #228):
  When the PR is labeled `wave-bootstrap` AND there is exactly ONE distinct
  reviewer who is a charter-enforcer role in the local roster, the hook
  permits merge with one Approved comment instead of two. Charter
  `pull-requests.md` § Single-Reviewer Exception (Wave-Bootstrap Only)
  defines the policy; this is its hook-side enforcement.

  Charter-enforcer roles are derived from the local repo's
  `.claude/team/roster/` filenames matching the prefix allowlist:
    standards_lead_*    (parent: Aino)
    program_director_*  (parent: Nadia)
    manager_*           (children: e.g. Maeve, Dilara, Bereket)
    project_lead_*      (children: e.g. Marcia)
    tech_lead_*         (children: e.g. Anya)
  Each file's `**Name:** <Full Name>` line is parsed for the canonical name.

Exit codes:
  0 — allow (not a merge command, two CURRENT reviews, or single-reviewer
      exception)
  2 — block (fewer than two current reviews and exception does not apply, a
      verdict is missing TechDebt, or the PR's commit list could not be fetched
      so verdict freshness cannot be established)
"""

import dataclasses
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
from _repo_flag_parse import extract_repo
from annunaki_log import log_pretooluse_block
from charter_trailer import (
    branch_author_first_initial,
    extract_charter_field,
    is_branch_author,
    name_lastname,
    strip_code_regions,
    trailer_block_substring,
)

# Charter-enforcer role prefixes for the Single-Reviewer Exception. Derived
# from `pull-requests.md § Single-Reviewer Exception (Wave-Bootstrap Only)`
# "Standards & Quality Lead (Aino) or a comparable charter enforcer". The
# prefix list captures the equivalent roles across parent + child rosters
# observed in the org: standards_lead, program_director (parent), manager,
# project_lead, tech_lead (children).
_CHARTER_ENFORCER_ROLE_PREFIXES = (
    "standards_lead_",
    "program_director_",
    "manager_",
    "project_lead_",
    "tech_lead_",
)


def is_merge_command(command: str) -> bool:
    """Check if the command is a gh pr merge invocation, including chained commands.

    Handles direct invocations and commands chained with &&, ||, ;, or |.
    """
    # Split on shell chaining operators to check each sub-command
    for segment in re.split(r"\s*(?:&&|\|\||\||;)\s*", command):
        stripped = segment.lstrip()
        # Skip past any leading env variable assignments (VAR=value ...)
        while re.match(r"[A-Za-z_][A-Za-z0-9_]*=\S*\s+", stripped):
            stripped = re.sub(r"^[A-Za-z_][A-Za-z0-9_]*=\S*\s+", "", stripped)
        if re.match(r"gh\s+pr\s+merge\b", stripped):
            return True
    return False


def extract_pr_number(command: str) -> str | None:
    """Extract PR number from gh pr merge command."""
    # gh pr merge 123 or gh pr merge <url>
    match = re.search(r"\bgh\s+pr\s+merge\s+(\d+)", command)
    if match:
        return match.group(1)
    # gh pr merge <url containing /pull/123>
    match = re.search(r"/pull/(\d+)", command)
    if match:
        return match.group(1)
    # gh pr merge with no number (current branch PR)
    return None


# A `gh pr merge` whose positional PR argument is NOT a resolvable bare-integer
# literal — i.e. the positional is EITHER non-literal (`$pr`, `${prs[$i]}`,
# `$(get_pr)`, a subshell-wrapped `(gh pr merge $pr)`, a URL) OR ABSENT entirely
# (a flags-only / current-branch `gh pr merge`). In a loop body EITHER form
# fail-opens the 2-reviewer gate: the literal-PR parse returns None, so
# `get_pr_data(None)` resolves the cwd branch's PR (moved by the loop's per-
# iteration `git checkout $b`) instead of a per-iteration literal, silently
# disabling the gate every iteration. The only in-loop-safe form is a bare
# integer, which the gate resolves and checks.
#
# The matcher fires on `gh pr merge` UNLESS immediately followed (after
# separating whitespace) by a bare integer. The single negative lookahead
# `(?!\s+\d)` expresses exactly that in one pass, subsuming the earlier
# first-non-flag/non-digit-argument-character matcher. It keeps everything #894
# closed AND catches the no-positional-argument evasion #896 left open (#897):
#
#   1. Subshell-wrapped merge — `(gh pr merge $pr)`. `merge` is followed by
#      ` $pr)`; `\s+\d` fails on the leading `$`, so the lookahead admits it.
#   2. Subscripted / compound / command-substitution arg — `"${prs[$i]}"`,
#      `"$(get_pr)"`. Quote-normalization (`_strip_quoted_runs_keep_var_args`)
#      unwraps any single-word expansion to its bare `${…}` / `$(…)` form, whose
#      leading `$` is not a digit → matched.
#   3. Absent positional / flags-only — `gh pr merge`, `gh pr merge --merge`,
#      `gh pr merge;` (#897). `merge` is followed by end-of-string, a terminator,
#      or ` --flag`; none is `\s+\d`, so the lookahead admits them.
#
# `(?!\s+\d)` admits every form EXCEPT a bare-integer literal: a non-literal
# positional (`$pr`, `${prs[$i]}`, `$(get_pr)`, a subshell `(gh pr merge $pr)`,
# a URL) OR an ABSENT positional (`gh pr merge`, `gh pr merge --merge`,
# `gh pr merge;`) both match, because none is followed by `\s+\d`. Only a bare
# integer (`gh pr merge 54`) is rejected — that PR number resolves and the gate
# runs. Matching the ABSENT form (not only the non-literal one) is what closes
# the #897 no-positional-argument evasion #896 left open; co-location inside a
# `do … done` body (see `is_variable_pr_merge_in_loop`) keeps a bare
# current-branch `gh pr merge` OUTSIDE any loop legitimately passing (#886).
_GH_MERGE_NO_LITERAL_PR = re.compile(
    r"\bgh\s+pr\s+merge\b"  # the merge verb (word-bounded — not `merged`, etc.)
    r"(?!\s+\d)"  # NOT immediately followed by a bare-integer literal PR number
)

# `do` / `done` loop keywords as standalone tokens (delimited by start-of-string,
# whitespace, or `;`). `do`/`done` are loop-only keywords in shell, so every
# balanced `do … done` pair delimits a loop BODY. The alternation lists `done`
# first so the longer keyword wins (otherwise `do` would match the `do` prefix
# of `done`). The keyword span is captured via the lookahead so the surrounding
# delimiters are not consumed and adjacent tokens are not swallowed (#886).
_LOOP_DO_DONE = re.compile(r"(?:^|[\s;])(done|do)(?=[\s;]|$)")


def _loop_body_spans(view: str) -> list[tuple[int, int]]:
    """Return the (start, end) character spans of each shell loop BODY in `view`.

    A loop body is the text between a `do` keyword and its matching `done`.
    `do`/`done` are loop-only keywords in shell, so every balanced `do … done`
    pair delimits one body; nested loops are paired via a stack (each `done`
    closes the most recent unmatched `do`). Unbalanced tokens are ignored.

    `view` is expected to be the quote-normalized command produced by
    `_strip_quoted_runs_keep_var_args`, so `do`/`done` mentioned inside a quoted
    `--body "…"` payload have already been stripped and do not create spans.
    """
    spans: list[tuple[int, int]] = []
    do_stack: list[int] = []  # end-offsets of open `do` keywords (body starts here)
    for m in _LOOP_DO_DONE.finditer(view):
        keyword = m.group(1)
        if keyword == "do":
            do_stack.append(m.end(1))
        elif do_stack:  # `done` — close the most recent `do`
            body_start = do_stack.pop()
            spans.append((body_start, m.start(1)))
    return spans


def _strip_expansions(text: str) -> str:
    """Return `text` with balanced `${…}` and `$(…)` expansion groups removed.

    Used by `_is_single_expansion_word` to decide whether a double-quoted run is
    a single shell WORD argument: a run like `"$(get_pr $i)"` or `"${prs[$i]}"`
    is one argument even though it contains whitespace INSIDE the expansion,
    whereas a prose run like `"do gh pr merge $pr"` carries whitespace OUTSIDE
    any expansion. Nested groups are paired with a depth counter over the group's
    own `(`/`)` or `{`/`}`. A bare `$pr` (no brace/paren) is left intact — it has
    no internal whitespace to hide, so the surrounding-whitespace test handles it.
    """
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] == "$" and i + 1 < n and text[i + 1] in "({":
            opener = text[i + 1]
            closer = ")" if opener == "(" else "}"
            depth = 0
            j = i + 1
            while j < n:
                if text[j] == opener:
                    depth += 1
                elif text[j] == closer:
                    depth -= 1
                    if depth == 0:
                        j += 1
                        break
                j += 1
            i = j  # skip the whole (possibly unbalanced) expansion group
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


def _is_single_expansion_word(text: str) -> bool:
    """True if `text` is a single shell-word argument carrying an expansion.

    `text` qualifies when it (a) contains a `$` expansion and (b) has no
    whitespace OUTSIDE any `${…}`/`$(…)` group. This admits the real merge-arg
    forms a loop can carry — `$pr`, `${pr}`, `${prs[$i]}`, `$(get_pr)`,
    `$(get_pr $i)` — while rejecting a `--body "for … do gh pr merge $pr; done"`
    prose payload (whitespace outside the expansion) and a quoted literal word
    like `"done"` (no `$`, so it is not unwrapped into a stray loop keyword).
    """
    if "$" not in text:
        return False
    return not any(ch.isspace() for ch in _strip_expansions(text))


def _strip_quoted_runs_keep_var_args(command: str) -> str:
    """Return `command` with quoted regions removed, EXCEPT a double-quoted
    region that is a single-word expansion argument (`"$pr"`, `"${pr}"`,
    `"${prs[$i]}"`, `"$(get_pr)"`), which is unwrapped to its bare inner form.

    Why: the loop-merge detector must (a) NOT see a `gh pr merge $pr` that
    lives inside a `--body "..."` payload (quoted argument data — strip it),
    yet (b) STILL see the real arg in `gh pr merge "$pr"` where only the
    argument itself is quoted (unwrap it). Shell semantics agree: double
    quotes around a single expansion word are removed and the word remains the
    program's argument, whereas a quoted run of prose is one opaque arg.

    The unwrap predicate is `_is_single_expansion_word` (#894): the earlier
    matcher only unwrapped a LONE simple variable (`\\$\\{?name\\}?`), so a
    subscripted / compound / command-substitution arg failed that fullmatch and
    was stripped as opaque prose — making the real merge arg vanish and the
    guard fail-open. Keying on "single expansion word" keeps every such arg.

    Single-quoted runs are always opaque data (no expansion) and are removed
    wholesale. Double-quoted runs are unwrapped only when the inner text is a
    single expansion word; otherwise removed.
    """
    out: list[str] = []
    i = 0
    n = len(command)
    while i < n:
        ch = command[i]
        if ch == "'":
            # Single-quoted run: opaque, drop through the closing quote.
            j = command.find("'", i + 1)
            if j == -1:
                break  # unbalanced — stop; raw-string fallback handles it
            i = j + 1
            continue
        if ch == '"':
            j = command.find('"', i + 1)
            if j == -1:
                break  # unbalanced
            inner = command[i + 1 : j]
            # Keep a single-word expansion double-quoted arg as its bare form.
            if _is_single_expansion_word(inner):
                out.append(inner)
            i = j + 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def is_variable_pr_merge_in_loop(command: str) -> bool:
    """True if `command` runs a `gh pr merge` with NO resolvable literal PR
    number inside a for/while/until loop — the batch-loop merge shape that
    fail-opens the 2-reviewer gate (#567/#886/#894/#897, memory
    `feedback_batch_loop_merge_evades`).

    The gate parses a LITERAL PR number from `gh pr merge <N>` to fetch that
    PR's reviews. When the argument is not a bare integer — non-literal (`$pr`,
    `${pr}`, `${prs[$i]}`, `$(get_pr)`, a subshell-wrapped `(gh pr merge $pr)`)
    OR ABSENT entirely (a bare `gh pr merge` / `gh pr merge --merge`, #897) — the
    literal parse returns None, `get_pr_data(None)` resolves the cwd branch's PR
    (moved by the loop's per-iteration `git checkout $b`), and the merge
    fail-opens — the gate is silently disabled for every iteration. The three
    originally-observed instances (P3W11 wave→main 4-merge loop, P3W13 ingest
    6-PR loop, both non-literal; #897 no-arg `git checkout $b && gh pr merge`)
    all swept other branches' PRs with the gate effectively off.

    Conservative DECIDE-tier design (per #567 + `feedback_safety_direction_
    over_ux_friction`): we HARD BLOCK the no-resolvable-literal-PR-in-loop shape
    outright. We do NOT attempt to enumerate loop values and gate-verify each —
    that is the explicitly-deferred conditional-allow path. A literal
    `gh pr merge 54` is untouched (its PR number parses, the gate runs).

    Mechanic (#894/#897 broadening). Detection runs on a quote-normalized view of
    the command (quoted prose stripped, a single-word expansion arg such as
    `"$pr"` or `"${prs[$i]}"` unwrapped — see `_strip_quoted_runs_keep_var_args`)
    so a `--body "... for … do gh pr merge $pr … done"` payload that merely
    MENTIONS the shape is not matched. On that view, `_GH_MERGE_NO_LITERAL_PR`
    matches a `gh pr merge` UNLESS it is immediately followed by a bare integer —
    so a non-literal positional AND an absent positional both match, closing:
      - subshell `(gh pr merge $pr)` — old terminator lookahead omitted `)` (#894);
      - compound `${prs[$i]}` / `$(get_pr)` — old unwrap dropped it as prose (#894);
      - no positional at all — `git checkout $b && gh pr merge` (#897).

    Co-location is preserved (#886/#897). The match must sit INSIDE a `do … done`
    loop body. A one-off `gh pr merge "$PR"` — or a bare current-branch
    `gh pr merge` — OUTSIDE any loop, co-occurring with an unrelated
    `for r in …; do gh run rerun "$r" --failed; done`, does NOT fail-open (the
    merge resolves its own current PR) and so MUST NOT block — the co-location
    requirement leaves it alone, while the real batch-loop shapes
    (`for pr in …; do gh pr merge "$pr"; done`,
    `for b in …; do git checkout $b && gh pr merge; done`) still trip.
    """
    view = _strip_quoted_runs_keep_var_args(command)
    merge_matches = list(_GH_MERGE_NO_LITERAL_PR.finditer(view))
    if not merge_matches:
        return False
    spans = _loop_body_spans(view)
    if not spans:
        return False
    return any(
        body_start <= mm.start() < body_end
        for mm in merge_matches
        for (body_start, body_end) in spans
    )


def get_pr_data(pr_number: str | None, repo: str | None = None) -> dict | None:
    """Fetch all needed PR data in a single gh pr view call.

    Returns dict with keys: author (login str), number, reviews, headRefName,
    labels (list of label-name strings).
    Returns None if the fetch fails.
    """
    try:
        cmd = ["gh", "pr", "view"]
        if pr_number:
            cmd.append(pr_number)
        if repo:
            cmd.extend(["--repo", repo])
        cmd.extend(["--json", "author,number,reviews,headRefName,labels"])
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            return None

        data = json.loads(result.stdout)
        labels = [label.get("name", "") for label in data.get("labels", [])]
        return {
            "author": data.get("author", {}).get("login", ""),
            "number": data.get("number", pr_number),
            "reviews": data.get("reviews", []),
            "headRefName": data.get("headRefName", ""),
            "labels": labels,
        }

    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return None


class CommitFetchError(Exception):
    """Raised when the PR's commit list cannot be fetched or parsed (#950).

    Signals the caller to fail in the SAFE direction (HARD BLOCK with a
    diagnostic). Without the commit list there is no `T_content`, so NO verdict's
    freshness can be established — and an unknown-freshness verdict must not be
    counted, or the staleness gate silently degrades back to the pre-#950
    fail-open it exists to close (`feedback_safety_direction_over_ux_friction`:
    when a hook cannot decide cleanly, hard-block with a diagnostic, never
    allow-with-log).
    """


def _parse_iso8601(value: str | None) -> datetime | None:
    """Parse a GitHub ISO-8601 timestamp (`2026-07-11T03:42:58Z`) to a datetime.

    Returns None when `value` is absent or unparseable. Callers treat None as
    UNKNOWN and fail closed — never as "fresh". The trailing `Z` is normalized to
    `+00:00` so every returned datetime is timezone-aware and therefore safely
    comparable with every other (a naive/aware mix would raise at comparison).
    """
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def _resolve_owner_repo(repo: str | None) -> tuple[str, str] | None:
    """Resolve `OWNER`, `NAME` for API calls — from `--repo` if given, else cwd.

    Returns None when the repo cannot be resolved (a failed / unparseable
    `gh repo view`). Callers fail closed on None.
    """
    if repo and "/" in repo:
        owner, _, repo_name = repo.partition("/")
        if owner and repo_name:
            return owner, repo_name
        return None
    try:
        repo_result = subprocess.run(
            ["gh", "repo", "view", "--json", "owner,name"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if repo_result.returncode != 0:
            return None
        repo_data = json.loads(repo_result.stdout)
        owner = repo_data.get("owner", {}).get("login", "")
        repo_name = repo_data.get("name", "")
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return None
    if not (owner and repo_name):
        return None
    return owner, repo_name


#: Defect kinds returned by `repo_argument_defect` (#981).
REPO_DEFECT_UNEXPANDED = "unexpanded"
REPO_DEFECT_MALFORMED = "malformed"


def repo_argument_defect(repo: str | None) -> str | None:
    """Classify a `--repo`/`-R` VALUE that can NEVER resolve to `OWNER/NAME` (#981).

    Returns `REPO_DEFECT_UNEXPANDED`, `REPO_DEFECT_MALFORMED`, or None when the
    value is absent (no flag given — cwd resolution legitimately applies) or is a
    well-formed literal.

    Why this exists. The hook parses the command string PRE-expansion, so a
    `gh pr merge 451 -R $DA` hands the gate the literal four characters `$DA`.
    That is not a repo, and no amount of retrying will make it one — every
    downstream fetch against it fails, and before #981 that failure landed on the
    `pr_data is None` branch, which ALLOWED the merge with a warning. Four
    da PRs (#449/#450/#451/#456) merged through that hole in P9W25 with the
    2-reviewer gate effectively off.

    The unexpanded case must be distinguished from a generic fetch failure
    because the two need OPPOSITE operator responses: an unexpanded variable is
    deterministic and is fixed by passing a literal `--repo owner/name`, whereas
    an auth/network failure is transient and is fixed by retrying. Telling an
    operator to "retry" a `$DA` would loop forever; telling them to "pass a
    literal repo" after a network blip would send them editing a correct command.

    Detection reuses `_is_single_expansion_word` — the SAME predicate the
    batch-loop guard (#894) uses to recognize an unexpanded argument — rather
    than a second hand-rolled regex. A duplicated matcher that drifts from its
    twin is exactly the defect class #1046 was, and `conventions.md` records the
    recurring regex-blindness lesson: one matcher, reused.

    `extract_repo` yields a single shell word, so `_is_single_expansion_word`
    reduces to "carries a `$`" here and covers every form: `$DA`, `${DA}`,
    `$(get_repo)`, and the partially-expanded `noorinalabs/$REPO` (which is
    especially dangerous — it HAS a slash, so `_resolve_owner_repo` would happily
    return `("noorinalabs", "$REPO")` and report a resolved repo that does not
    exist). A pathological whitespace-bearing value fails the predicate but then
    fails the slash test, so it is still classified as a defect — no hole.
    """
    if repo is None:
        return None
    if _is_single_expansion_word(repo) or "$" in repo:
        return REPO_DEFECT_UNEXPANDED
    owner, sep, name = repo.partition("/")
    if not (sep and owner and name):
        return REPO_DEFECT_MALFORMED
    return None


def describe_repo_defect(repo: str | None, defect: str) -> str:
    """One-line human description of a `repo_argument_defect` classification.

    Shared by Hook 4's block message and `pr_review_state`'s `ReviewStateError`
    so the two surfaces cannot drift in what they tell an operator (#1046).
    """
    if defect == REPO_DEFECT_UNEXPANDED:
        return (
            f"the `--repo`/`-R` value {repo!r} contains an UNEXPANDED shell "
            "variable. The hook sees the command before the shell expands it, so "
            "this is the literal text — not a repository."
        )
    return (
        f"the `--repo`/`-R` value {repo!r} is not of the form OWNER/NAME "
        "(no `/` separating a non-empty owner from a non-empty repo name)."
    )


def get_latest_content_commit(
    pr_number: str | int,
    repo: str | None = None,
) -> tuple[str, datetime] | None:
    """Return `(short_sha, committed_at)` of the PR's latest NON-MERGE commit (#950).

    This is `T_content` — the moment the newest AUTHORED content arrived on the
    branch, and the line a verdict must sit at or after to count.

    Merge commits are excluded by parent count (a merge has >= 2 parents; a
    normal commit has 1 and a root commit has 0, so `< 2` is the non-merge test).
    Excluding them is what lets an approval SURVIVE a routine branch update from
    `main` — that merge commit moves the head without changing what the reviewer
    read. Including them would invalidate every approval in the org at the moment
    of merge (see `feedback_commit_author_gate_exclude_merges`).

    The COMMITTER date is used, not the author date: a rebase or amend preserves
    the original author date while rewriting the commit object, so only the
    committer date tracks when the content actually landed on the branch.

    `--paginate` is mandatory: without it a PR with >100 commits silently
    truncates and T_content is computed from a stale prefix (the same trap #303
    fixed for the comment fetch).

    Returns None when the PR has NO non-merge commits — a degenerate branch that
    contributes no authored content, so nothing can be stale against it.

    Raises:
        CommitFetchError: the commit list could not be fetched or parsed. There
            is no safe default here — see the class docstring.
    """
    owner_repo = _resolve_owner_repo(repo)
    if owner_repo is None:
        raise CommitFetchError(
            f"could not resolve the target repository (--repo={repo!r}, and "
            "`gh repo view` in the current directory did not return owner/name)"
        )
    owner, repo_name = owner_repo

    try:
        commits_result = subprocess.run(
            [
                "gh",
                "api",
                "--paginate",
                f"repos/{owner}/{repo_name}/pulls/{pr_number}/commits?per_page=100",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        raise CommitFetchError(f"`gh api .../pulls/{pr_number}/commits` failed: {exc}") from exc

    if commits_result.returncode != 0:
        stderr = (commits_result.stderr or "").strip()
        raise CommitFetchError(
            f"`gh api .../pulls/{pr_number}/commits` exited "
            f"{commits_result.returncode}: {stderr or '<no stderr>'}"
        )

    try:
        commits = json.loads(commits_result.stdout)
    except json.JSONDecodeError as exc:
        raise CommitFetchError(
            f"`gh api .../pulls/{pr_number}/commits` returned unparseable JSON: {exc}"
        ) from exc

    if not isinstance(commits, list):
        raise CommitFetchError(
            f"`gh api .../pulls/{pr_number}/commits` returned "
            f"{type(commits).__name__}, expected a list"
        )

    latest: tuple[str, datetime] | None = None
    for commit in commits:
        if not isinstance(commit, dict):
            continue
        if len(commit.get("parents") or []) >= 2:
            continue  # merge commit — moves the head without changing content
        committed_at = _parse_iso8601(
            (commit.get("commit", {}).get("committer", {}) or {}).get("date")
        )
        if committed_at is None:
            # A non-merge commit with no usable timestamp makes T_content
            # unknowable. Fail closed rather than silently computing T_content
            # from the commits that DID parse — that would understate it and
            # wave stale verdicts through.
            raise CommitFetchError(
                f"non-merge commit {str(commit.get('sha', '?'))[:8]} has no parseable "
                "committer date, so T_content cannot be established"
            )
        if latest is None or committed_at > latest[1]:
            latest = (str(commit.get("sha", "?"))[:8], committed_at)

    return latest


def extract_branch_author_lastname(head_ref: str) -> str | None:
    """Extract the last name from branch format '{FirstInitial}.{LastName}[-/]...'.

    Accepts both separator styles seen in practice:
    - slash: `A.Virtanen/0179-branch-regex-fix` (legacy/charter spec)
    - dash:  `A.Virtanen-0179-branch-regex-fix` (observed on recent branches)

    Returns None if the head_ref does not match the `{Initial}.{LastName}` prefix
    followed by one of the accepted separators.
    """
    match = re.match(r"[A-Za-z]\.([A-Za-z]+)[-/]", head_ref)
    if match:
        return match.group(1)
    return None


# How the PR-comment verdict scan was dispatched for a given PR (#1206).
#
# These exist because an empty `comment_reviewers` set cannot say WHY it is
# empty, and the two reasons are not remotely equivalent: "the thread was read
# and nobody has approved" is a measurement, "the thread was never read" is the
# absence of one. Before #1206 the resolver silently produced the second and
# every surface rendered it as the first — the `feedback_silent_zero_is_not_a_
# measurement` shape, and the sibling of the `CommentReviewResult.undetermined`
# field that exists for the same reason one level down.
#
# NOT_RUN is deliberately the DEFAULT on both `ReviewVerdicts` and
# `pr_review_state.ReviewState`: a construction that forgets to set the scope
# must degrade to the honest "not measured" rendering, never to a false claim
# that the scan ran. `comment_scan_scope` below never returns it, and
# `resolve_review_verdicts` hard-blocks if it ever sees it — so in production it
# marks a regression, not a state.
COMMENT_SCAN_NOT_RUN = "not-run"
COMMENT_SCAN_AUTHOR_EXCLUDED = "author-excluded"
COMMENT_SCAN_NO_BRANCH_AUTHOR = "no-branch-author"


def comment_scan_scope(head_ref: str) -> str:
    """Return which self-review-exclusion mode the comment verdict scan runs in.

    The head ref's ONLY role in the comment scan is naming the branch author for
    the self-review exclusion, so there are exactly two modes and **no third
    "don't scan" mode**:

      - `COMMENT_SCAN_AUTHOR_EXCLUDED` — the ref carries the charter
        `{Initial}.{Lastname}[-/]…` prefix, so the branch author is identifiable
        and is excluded from the reviewer set.
      - `COMMENT_SCAN_NO_BRANCH_AUTHOR` — the ref names no persona (a
        `deployments/phase-N/wave-M` wave-merge branch, a `dependabot/**` bot
        branch, a hand-made `feature/x`, or an empty `headRefName`). The scan
        still runs, under the `""` sentinel the wave-merge path has used since
        main#294, which `charter_trailer.is_branch_author` reads as "nobody is
        the branch author".

    This function is TOTAL: it returns a scanning mode for every possible head
    ref, including `""`. That totality IS the #1206 fix — the pre-fix resolver
    branched on the ref shape and fell through to no scan at all for anything
    that was neither a persona branch nor `deployments/**`, which made a
    `dependabot/**` PR carrying two valid Approveds report `0/2 — (none)`
    (noorinalabs-deploy#691). `.claude/hooks/tests/test_validate_pr_review.py::
    CommentScanScopeTotalityTests` pins the totality directly.

    Widening the sentinel does NOT relax the gate: the threshold is still two
    distinct roster-valid current Approveds and roster filtering is untouched.
    Losing author-exclusion on a bot branch is the correct outcome — a bot is
    never a roster persona, so it could never have been in the reviewer set. On
    a ref that DOES name a persona, exclusion is unchanged.
    """
    return (
        COMMENT_SCAN_AUTHOR_EXCLUDED
        if extract_branch_author_lastname(head_ref)
        else COMMENT_SCAN_NO_BRANCH_AUTHOR
    )


PROJECT_NUMBER = 2
ORG = "noorinalabs"

# Path to the PARENT repo's roster directory. Resolved relative to the hook
# file: /<repo_root>/.claude/hooks/validate_pr_review.py → /<repo_root>/.claude/team/roster.
_ROSTER_DIR = Path(__file__).resolve().parent.parent / "team" / "roster"

# Parent repo root — the directory that holds `.claude/` AND under which the
# org's child repos are checked out as siblings (per CLAUDE.md § Repository
# Map: `noorinalabs-isnad-graph/`, `noorinalabs-deploy/`, …). Used to locate a
# child repo's own `.claude/team/roster/` when a `gh pr merge --repo
# noorinalabs/<child>` command targets that repo (#552).
_PARENT_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class RosterResolutionError(Exception):
    """Raised when a child repo is named but its roster dir cannot be read.

    Signals the caller to fail in the SAFE direction (HARD BLOCK with a
    diagnostic) rather than silently falling back to the parent-only roster,
    which would re-introduce the #552 false-block / fail-open behavior under a
    different guise (per `feedback_safety_direction_over_ux_friction`).
    """


def _child_roster_dir(repo: str | None) -> Path | None:
    """Resolve the child repo's roster dir from a `--repo OWNER/NAME` value.

    Child repos are checked out as siblings under `_PARENT_REPO_ROOT` (the
    directory holding the parent's `.claude/`), so `noorinalabs/<child>`
    resolves to `_PARENT_REPO_ROOT/<child>/.claude/team/roster` (#552).

    Returns None when:
      - `repo` is absent / malformed (no `OWNER/NAME` shape), or
      - `repo` names the PARENT repo itself (`noorinalabs-main`) — the parent
        roster is already `_ROSTER_DIR`, so there is no distinct child dir.

    A non-None return is a path that the caller is expected to find on disk;
    if it does not exist, that is a hard-block condition (RosterResolutionError),
    NOT a silent parent-only fallback.
    """
    if not repo or "/" not in repo:
        return None
    _owner, _, name = repo.partition("/")
    if not name or name == _PARENT_REPO_ROOT.name:
        return None
    return _PARENT_REPO_ROOT / name / ".claude" / "team" / "roster"


class StaleVerdict:
    """A verdict comment cast BEFORE the branch's latest authored content (#950).

    Carried purely for the block diagnostic. An operator who sees `0/2 approvals`
    on a PR with two visible `Approved` comments will conclude the hook is broken
    unless it names which verdict went stale and why — so the block message is as
    load-bearing as the block itself.
    """

    def __init__(self, reviewer: str, verdict: str, created_at: str) -> None:
        self.reviewer = reviewer  # Requestor, as written (display form)
        self.verdict = verdict  # the RequestOrReplied value, as written
        self.created_at = created_at  # raw ISO timestamp, or "" if absent


class CommentReviewResult:
    """Result of checking PR comments for charter-format reviews.

    `undetermined` carries the reason the comment scan could not be COMPLETED
    (#981 defense-in-depth). It is the difference between "this PR has no
    charter-format approvals" and "the hook never got to look", which an empty
    `reviewers` set alone cannot express — every early `return result` in
    `check_comment_reviews` used to be indistinguishable from a genuine
    zero-approval PR. Callers must fail CLOSED when it is non-empty
    (`feedback_safety_direction_over_ux_friction`).

    Deliberately an ADDITIVE field with a falsy default rather than a raised
    exception: `pr_review_state.compute_review_state` and a large body of unit
    tests construct and consume this object directly, and a new exception type
    escaping `check_comment_reviews` would turn that driver's clean exit-2 path
    into an uncaught traceback. A default-empty attribute leaves every existing
    construction and read working untouched.
    """

    def __init__(self) -> None:
        self.reviewers: set[str] = set()
        self.reviews_missing_tech_debt: list[str] = []  # reviewer names missing TechDebt line
        self.tech_debt_issue_numbers: list[str] = []  # issue numbers from TechDebt: lines
        # (requestor, raw td_value) pairs where TechDebt: was present, non-"none",
        # and yielded ZERO parsed issue numbers (main#1055) — e.g. free text like
        # "filed later" or "TBD". Distinct from `reviews_missing_tech_debt` (the
        # line was present) — this is "present but uncaptured," which used to be
        # silently indistinguishable from "no tech debt" (`TechDebt: none`).
        self.tech_debt_unparseable: list[tuple[str, str]] = []
        self.stale_verdicts: list[StaleVerdict] = []  # verdicts predating T_content (#950)
        self.undetermined: str = ""  # non-empty ⇒ scan incomplete, caller must fail closed


# Only these RequestOrReplied values represent actual review verdicts that
# REQUIRE the TechDebt attestation line. Request / Reply comments are
# process metadata (review requests, author replies) and do NOT require it.
# Issue #147: the prior implementation flagged any Requestee+RequestOrReplied
# comment, which over-enforced TechDebt on Request/Replied traffic.
#
# Includes both the canonical `ChangesRequested` (one word, charter-line-14)
# and the spaced/short variants observed in practice.
_VERDICT_REQUIRING_TECH_DEBT = {
    "approved",
    "changes requested",
    "changesrequested",
    "changes",
}


def _is_verdict(value: str) -> bool:
    """Return True if a RequestOrReplied value is an actual review verdict.

    Comparison is case-insensitive and whitespace-trimmed. Accepts the
    canonical `ChangesRequested` (per charter line 14), the spaced
    `Changes Requested` form, and the shorter `Changes` variant noted in
    charter discussion as seen in practice. Does NOT accept Request (a
    review request) or Reply / Replied (an author's reply).
    """
    normalized = value.strip().lower()
    # Strip trailing markdown markers and stray punctuation
    normalized = normalized.rstrip("*").strip()
    return normalized in _VERDICT_REQUIRING_TECH_DEBT


def _is_approved(value: str) -> bool:
    """Return True if a RequestOrReplied value is specifically Approved.

    The 2-reviewer rule (charter line 36) counts distinct Requestor values
    across `Approved` comments only — NOT ChangesRequested. A
    ChangesRequested comment is a verdict (TechDebt required) but does not
    contribute to the 2-reviewer threshold.
    """
    normalized = value.strip().lower().rstrip("*").strip()
    return normalized == "approved"


# The charter trailer convention has ONE definition, shared with
# `validate_review_comment_format` (#932/#934). These module-level aliases keep
# the historical private names — and their existing test surface — while making
# a second, drifting copy impossible. Do not reimplement them here.
_strip_code_regions = strip_code_regions
_trailer_block_substring = trailer_block_substring
_extract_charter_field = extract_charter_field


# Name parsing lives in `charter_trailer` alongside the trailer convention, so
# this hook and `validate_review_comment_format` cannot disagree about who a
# person is (#1172). Historical private name kept for the existing test surface.
_name_lastname = name_lastname


def check_comment_reviews(
    pr_number: str | int,
    branch_author_lastname: str,
    *,
    repo: str | None = None,
    content_ts: datetime | None,
    branch_author_initial: str = "",
) -> CommentReviewResult:
    """Check PR comments for charter-format review comments from different authors.

    Returns a CommentReviewResult with distinct reviewer names (keyed on full
    name, lowercased) and any reviews missing the mandatory TechDebt line.

    Reviewer identification per charter (resolves #244):
      - Approved / ChangesRequested → reviewer is the Requestor (comment author)
      - Request / Reply → not a review; does not contribute to reviewer set
      - 2-reviewer threshold counts distinct Requestor values whose LATEST
        verdict comment is Approved (#940). An approval is a statement about
        a moment, not a permanent grant: a reviewer's later ChangesRequested
        withdraws an earlier Approved and drops them from the reviewer set,
        and a reviewer's later Approved supersedes an earlier ChangesRequested
        and adds them. Only the reviewer's most recent CURRENT (non-stale, see
        below) verdict is consulted — earlier verdicts from the same reviewer
        do not additionally count or block.

    `content_ts` is `T_content` (#950) — the committer timestamp of the branch's
    latest non-merge commit, from `get_latest_content_commit`. When supplied, a
    verdict comment created BEFORE it is STALE: it reviewed code that has since
    been rewritten, so it is excluded from the reviewer set and recorded in
    `result.stale_verdicts` for the block diagnostic. A stale verdict is also
    exempt from the TechDebt attestation requirement — a verdict that carries no
    weight toward the threshold must not be able to block the merge on a
    secondary attestation either. A verdict whose own `created_at` is missing or
    unparseable is treated as STALE, not fresh (fail closed).

    `branch_author_initial` (#1172) is the branch prefix's first initial,
    lowercased — the second half of the branch author's identity. Together with
    `branch_author_lastname` it decides which Requestor is the PR author and is
    therefore excluded from the reviewer set. It is keyword-only with a `""`
    default because `""` is the honest value whenever the head ref carries no
    `{Initial}.{Lastname}` prefix (wave-merge branches), and because omitting it
    degrades to the pre-#1172 surname-only comparison — which OVER-excludes
    (a same-surname colleague is mistaken for the author, the reviewer count
    drops, the merge blocks). That is the fail-CLOSED direction, so unlike the
    `content_ts` case below an omission cannot silently admit a merge.

    `content_ts` is a REQUIRED keyword-only argument (#1050) — it must be
    passed explicitly on every call, though `None` remains a legitimate
    VALUE meaning "no content binding" (either the PR has no non-merge
    commits, or a caller intentionally wants every verdict counted
    unconditionally). Making it required converts an omitted argument from a
    silent fail-open (the #1046 shape: staleness-filtering silently OFF) into
    a loud `TypeError` at call time. `check()` never passes `None` on a real
    merge: a commit-fetch failure raises `CommitFetchError` and hard-blocks
    upstream of this call.
    """
    result = CommentReviewResult()
    # Reviewer -> most recent (chronologically-last) CURRENT RequestOrReplied
    # value, keyed on lowercased full name (#940). An Approved comment is a
    # statement about a MOMENT, not a permanent grant: a reviewer who approves
    # and later requests changes must have that later verdict supersede the
    # earlier one, and a reviewer who requests changes and later approves must
    # likewise have the approval win. `comments` is already chronological, so
    # the last write for a given key IS that reviewer's latest verdict.
    latest_verdict: dict[str, str] = {}
    try:
        owner_repo = _resolve_owner_repo(repo)
        if owner_repo is None:
            result.undetermined = (
                f"could not resolve the target repository (--repo={repo!r}, and "
                "`gh repo view` in the current directory did not return owner/name)"
            )
            return result
        owner, repo_name = owner_repo

        # Fetch ALL PR comments via the issues API. `--paginate` concatenates
        # each page's JSON array into one combined response; without it, the
        # hook silently misses reviews appearing after comment #100 (#303).
        # Bumped the subprocess timeout to 30s to give pagination room — most
        # PRs have <100 comments and complete in <5s; the few high-traffic
        # PRs that need multiple pages take longer.
        comments_result = subprocess.run(
            [
                "gh",
                "api",
                "--paginate",
                f"repos/{owner}/{repo_name}/issues/{pr_number}/comments?per_page=100",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if comments_result.returncode != 0:
            stderr = (comments_result.stderr or "").strip().splitlines()
            result.undetermined = "the PR comments API call failed" + (
                f": {stderr[-1]}" if stderr else " (no stderr)"
            )
            return result

        comments = json.loads(comments_result.stdout)
        for comment in comments:
            body = comment.get("body", "")
            requestor = _extract_charter_field("Requestor", body)
            ror_value = _extract_charter_field("RequestOrReplied", body)

            # A charter-format comment must have BOTH Requestor and
            # RequestOrReplied. Comments missing either are not parsed.
            if not (requestor and ror_value):
                continue

            is_verdict_comment = _is_verdict(ror_value)

            # Content binding (#950): a verdict cast before the branch's latest
            # AUTHORED commit reviewed code that has since been rewritten. It is
            # not evidence about the code being merged, so it neither counts
            # toward the threshold nor carries a TechDebt obligation — but it IS
            # recorded, so the block message can name it. An unparseable /
            # missing comment timestamp is stale, not fresh (fail closed).
            if is_verdict_comment and content_ts is not None:
                created_raw = comment.get("created_at", "") or ""
                created_at = _parse_iso8601(created_raw)
                if created_at is None or created_at < content_ts:
                    result.stale_verdicts.append(
                        StaleVerdict(
                            reviewer=requestor,
                            verdict=ror_value.strip(),
                            created_at=created_raw,
                        )
                    )
                    continue

            # Record this reviewer's latest CURRENT verdict (#940). The
            # reviewer set toward the 2-reviewer threshold (charter line 36,
            # resolves #244) is derived from `latest_verdict` AFTER the loop —
            # not accumulated here — so a later ChangesRequested can withdraw
            # an earlier Approved (and vice versa) instead of only ever adding.
            if is_verdict_comment:
                # Self-review exclusion (#1172): "is this reviewer the branch
                # author?" is a question about a PERSON, not a surname. Keyed on
                # surname alone, Santiago Ferreira's verdict on Lucas Ferreira's
                # `L.Ferreira/…` branch was discarded as a self-review and the PR
                # sat one approval short. `is_branch_author` compares
                # first-initial + lastname — the full discriminator the branch
                # prefix carries — and still excludes a real self-review, whose
                # initial and surname both match.
                if not is_branch_author(requestor, branch_author_lastname, branch_author_initial):
                    latest_verdict[requestor.lower()] = ror_value

            # TechDebt attestation is required on every verdict
            # (Approved + ChangesRequested) — issue #147 fix.
            if is_verdict_comment:
                has_tech_debt = re.search(r"\*{0,2}TechDebt:\*{0,2}\s*(.+)", body)
                if not has_tech_debt:
                    # Reviewer name = Requestor on verdicts (charter line 30).
                    result.reviews_missing_tech_debt.append(requestor)
                else:
                    td_value = has_tech_debt.group(1).strip().strip("*").strip()
                    if td_value.lower() != "none":
                        # Extract issue numbers. `#?` accepts BOTH the canonical
                        # `#15, #16` form and a bare `15, 16` (main#1055: a bare
                        # number previously matched nothing here — present but
                        # zero captured refs, silently). A value that is neither
                        # "none" nor yields any number (free text like "filed
                        # later") is recorded in `tech_debt_unparseable` instead
                        # of vanishing — the residual case must be observable,
                        # not just less likely.
                        issue_nums = re.findall(r"#?(\d+)", td_value)
                        if issue_nums:
                            result.tech_debt_issue_numbers.extend(issue_nums)
                        else:
                            result.tech_debt_unparseable.append((requestor, td_value))

        # A reviewer counts toward the threshold only if their LATEST verdict
        # is Approved (#940) — a reviewer whose latest verdict is
        # ChangesRequested is currently blocking and must not count, even
        # though they approved at some earlier point in the thread.
        result.reviewers = {
            reviewer for reviewer, verdict in latest_verdict.items() if _is_approved(verdict)
        }
        return result

    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError) as exc:
        # A timeout on a heavily-paginated PR, unparseable JSON, or a missing
        # `gh` binary all leave the comment scan INCOMPLETE. Reporting that as an
        # empty reviewer set would read as "no approvals" — wrong in a way that
        # also silently skips the TechDebt attestation check. Record it and let
        # the caller hard-block (#981).
        result.undetermined = f"the PR comments could not be read ({type(exc).__name__}: {exc})"
        return result


def partition_formal_reviewers(
    reviews: list[dict],
    author: str,
    content_ts: datetime | None,
) -> tuple[set[str], list[StaleVerdict]]:
    """Split formal GitHub reviews into CURRENT reviewers and STALE verdicts (#950).

    Formal GitHub reviews are bound to `T_content` by the SAME rule as comment
    verdicts: a review submitted before the branch's latest authored commit
    reviewed code that has since been rewritten. Leaving formal reviews unbound
    would be a hole straight through the #950 fix.

    Returns `(formal_reviewers, stale_formal)` where `formal_reviewers` holds
    lowercased logins of non-author reviewers whose review is CURRENT, and
    `stale_formal` holds a `StaleVerdict` per excluded review (for the
    diagnostic). Self-reviews (login == `author`) and reviews with no login are
    dropped entirely — they are not evidence and not staleness.

    `submittedAt` missing or unparseable while `content_ts` is known ⇒ STALE,
    not fresh (fail closed). `content_ts` is a REQUIRED positional argument
    (#1050) — every caller must pass it explicitly, though `None` remains a
    legitimate VALUE meaning "no content binding" (every non-author review
    counts, as before the content binding existed). Requiring it converts an
    omitted argument from a silent fail-open (the #1046 shape) into a loud
    `TypeError` at call time.

    This function is the SHARED implementation for `check()` (Hook 4) and
    `.claude/lib/pr_review_state.py` (the #707 ahead-of-time driver). Both must
    partition formal reviews identically; a second hand-rolled copy in the
    driver is exactly the drift that let #1046 ship, where the driver reported
    PASS on verdicts the gate would have rejected as stale. Do not inline it
    back into either caller.
    """
    formal_reviewers: set[str] = set()
    stale_formal: list[StaleVerdict] = []
    for review in reviews:
        login = review.get("author", {}).get("login", "")
        if not login or login == author:
            continue
        if content_ts is not None:
            submitted_raw = review.get("submittedAt", "") or ""
            submitted_at = _parse_iso8601(submitted_raw)
            if submitted_at is None or submitted_at < content_ts:
                stale_formal.append(
                    StaleVerdict(
                        reviewer=login,
                        verdict=str(review.get("state", "REVIEW")),
                        created_at=submitted_raw,
                    )
                )
                continue
        formal_reviewers.add(login.lower())
    return formal_reviewers, stale_formal


def _iter_roster_entries(
    role_prefix_filter: tuple[str, ...] | None = None,
    roster_dir: Path | None = None,
) -> set[str]:
    """Walk a roster dir and return canonical names from `**Name:** <Full Name>`.

    Shared parser for `load_charter_enforcer_names` (role-filtered) and
    `_load_roster_names` (all members). When `role_prefix_filter` is supplied,
    only filenames starting with one of the listed prefixes are read; when
    `None`, every `*.md` in the roster dir contributes.

    `roster_dir` defaults to `_ROSTER_DIR` (the parent repo's roster). Callers
    pass a child repo's roster dir to union child reviewers into the gate (#552).

    Names are returned in lowercase to match `CommentReviewResult.reviewers`'
    dedup key (full name, lowercased). Returns an empty set on any I/O failure
    (fail-closed — see callers for safe-direction semantics).
    """
    roster_dir = roster_dir if roster_dir is not None else _ROSTER_DIR
    names: set[str] = set()
    try:
        if not roster_dir.is_dir():
            return names
        for entry in roster_dir.iterdir():
            if entry.suffix != ".md":
                continue
            if role_prefix_filter is not None and not any(
                entry.name.startswith(p) for p in role_prefix_filter
            ):
                continue
            try:
                content = entry.read_text(encoding="utf-8")
            except OSError:
                continue
            # Old verbose card: "- **Name:** <Full Name>". New slim card (#1010):
            # H1 "# <Full Name> — <Role>". Try the explicit field first, then
            # fall back to the H1 name so both formats resolve during the
            # org-wide card-slim transition.
            match = re.search(r"\*\*Name:\*\*\s*([^\n]+)", content)
            if match:
                names.add(match.group(1).strip().lower())
            else:
                h1 = re.search(r"^#\s+(.+?)\s+[—–-]\s+.+$", content, re.MULTILINE)
                if h1:
                    names.add(h1.group(1).strip().lower())
    except OSError:
        return set()
    return names


def _resolve_roster_dirs(repo: str | None) -> list[Path]:
    """Return the roster dirs to union for a merge targeting `repo` (#552).

    Always includes the parent `_ROSTER_DIR` (org-level reviewers — Nadia,
    Wanjiku, Santiago, Aino — may review any repo's PR). When `--repo` names a
    distinct child repo, its `.claude/team/roster/` is appended so legitimate
    child-repo reviewers (per CLAUDE.md: child rosters are canonical for
    reviewer pairing) pass the gate.

    Raises `RosterResolutionError` when a child repo IS named but its roster
    dir does not exist — fail in the safe direction (HARD BLOCK) rather than
    silently degrading to parent-only, which would re-block legitimate child
    reviewers exactly as #552 did.
    """
    dirs = [_ROSTER_DIR]
    child_dir = _child_roster_dir(repo)
    if child_dir is not None:
        if not child_dir.is_dir():
            raise RosterResolutionError(
                f"child roster dir not found for --repo '{repo}': {child_dir}"
            )
        dirs.append(child_dir)
    return dirs


def load_charter_enforcer_names(repo: str | None = None) -> set[str]:
    """Read the relevant roster dirs and return canonical charter-enforcer names.

    Charter enforcers are roster files matching the
    `_CHARTER_ENFORCER_ROLE_PREFIXES` allowlist. Each file's
    `**Name:** <Full Name>` line is parsed for the canonical name.

    When `repo` names a child repo, the parent roster is unioned with that
    child's roster (#552) so a child-repo enforcer (e.g. a child Manager /
    Tech Lead / Project Lead) is recognized for the Single-Reviewer Exception.
    Returns an empty set on any I/O failure (fail-closed for the exception
    path: if we can't read the roster, we don't grant the exception).

    Names are returned in lowercase to match `CommentReviewResult.reviewers`'
    dedup key (full name, lowercased).
    """
    names: set[str] = set()
    for roster_dir in _resolve_roster_dirs(repo):
        names |= _iter_roster_entries(
            role_prefix_filter=_CHARTER_ENFORCER_ROLE_PREFIXES, roster_dir=roster_dir
        )
    return names


# A manifest entry is a PERSONA only if its address is a charter-conformant
# per-persona commit identity: `<principal>+<First>.<Last>@<domain>` (CLAUDE.md
# § Key Rules / charter `pull-requests.md` § Commit Identity). The `+`-tag with
# an internal `.` separator is what makes an entry spawnable and commit-capable,
# so it is the org's own definition of "a person" — not a hand-maintained
# blocklist that a new tool entry would silently slip past.
#
# Measured against `.claude/team/roster.json` (78 entries, 2026-07-30) this
# excludes exactly the two entries #1181 identifies as non-persona:
#   - `Annunaki` → `parametrization+Annunaki@gmail.com` (tool identity; no
#     `First.Last` tag) — the error monitor, which posts real comments on real
#     PRs, so admitting it as a Requestor is the live risk, not a hypothetical.
#   - `Steven French` → `parametrization@gmail.com` (bare principal, no `+`tag).
_PERSONA_ALIAS_RE = re.compile(r"^[^\s@+]+\+[^\s@+]+\.[^\s@+]+@[^\s@]+\.[^\s@]+$")


def _load_org_manifest_names(manifest_path: Path | None = None) -> set[str]:
    """Parse PERSONA names from the org-union manifest `.claude/team/roster.json`.

    Mirrors `.claude/skills/wave-scope/validate_matrix_names._load_org_manifest_names`
    (#1162) so scope-time and merge-time resolve the same review-class authority.
    That module's docstring already argues WHY the manifest is acceptable for a
    review-class set and must not widen a commit-capable one; this is the
    merge-time half of the same decision (#1179) and inherits that reasoning
    verbatim rather than re-deriving it.

    The manifest is a flat `{"<name>": "<email>"}` object covering every persona
    across the org — a strict superset of the parent's own card directory, and
    the only place a persona whose card lives in a repo that is NOT the target
    repo can be recognised without cloning that repo. That is exactly the
    charter-permitted "third-child reviewer" (`charter/agents/spawn-discipline.md`
    § Child-Repo Implementer Rule step 5) whose `Approved` Hook 4 counted as zero
    before #1179.

    **Persona filter (#1179 acceptance 3).** Only entries whose address matches
    `_PERSONA_ALIAS_RE` are returned. The manifest is the LOOSER authority — it
    can carry an entry that corresponds to no spawnable person, and #1181 shows
    18 such manifest-only names of which `Annunaki` is definitionally not a
    reviewer. Filtering on identity SHAPE keeps this gate correct today without
    waiting on #1181's classification work, and stays correct if #1181 adds more
    tool entries. #1181 may narrow the set further (manifest-orphan reconciliation);
    it will not need to widen it.

    Fails OPEN (empty set) when the file is missing or malformed — same posture
    as the scope-time twin, and safe here for the same reason: the manifest only
    ever WIDENS a review-class set, so an unreadable manifest degrades to exactly
    the pre-#1179 behaviour (a loud BLOCK) rather than admitting anyone.

    A non-string value is treated as non-persona. If `roster.json` ever grows a
    richer per-entry schema (one of #1181's options), this parser narrows rather
    than guessing — narrowing re-blocks, which is the recoverable direction.

    Names are returned in lowercase to match `CommentReviewResult.reviewers`'
    dedup key, as `_iter_roster_entries` does.
    """
    path = manifest_path if manifest_path is not None else _ROSTER_DIR.parent / "roster.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    if not isinstance(data, dict):
        return set()
    return {
        name.strip().lower()
        for name, address in data.items()
        if isinstance(name, str)
        and name.strip()
        and isinstance(address, str)
        and _PERSONA_ALIAS_RE.match(address.strip())
    }


def _load_roster_names(repo: str | None = None) -> set[str]:
    """Read the relevant roster dirs and return ALL canonical persona names.

    Unlike `load_charter_enforcer_names`, this set is not role-filtered — it
    is the full membership used by the 2-reviewer gate to reject Approved
    verdicts whose Requestor string does not name a real roster persona (#498).

    When `repo` names a child repo, the parent roster is UNIONED with that
    child's `.claude/team/roster/` (#552), so a reviewer valid in EITHER the
    org-level team or the target child repo passes the gate. Without this,
    legitimate child-repo reviewers were filtered as non-roster and child PRs
    could not reach the real 2-reviewer threshold — forcing `--admin`.

    The org-union manifest is unioned on top (#1179). Cards alone cover only
    parent ∪ target-child, so a reviewer drawn from a THIRD child repo — which
    `/wave-scope` § 12.5 and `/wave-kickoff` § 0b have accepted since #1162 —
    was still filtered as non-roster here, counted zero, and left `--admin` as
    the only exit (a moderate feedback event). This is review-class ONLY:
    `load_charter_enforcer_names` stays card-only and fail-closed, because it is
    role-filtered on card FILENAME prefixes the flat manifest cannot supply and
    it gates the Single-Reviewer Exception. Do not union the manifest there.

    Two invariants the ordering below preserves deliberately:

    1. **The manifest WIDENS a card set; it never SUBSTITUTES for one.** It is
       unioned only when the card dirs yielded at least one name, so the
       documented "empty set ⇒ roster unreadable ⇒ caller fails closed" contract
       still holds. A readable manifest beside an unreadable card tree must not
       quietly re-enable the gate.
    2. **`RosterResolutionError` still hard-blocks.** `_resolve_roster_dirs`
       raises BEFORE the manifest is consulted, so a `--repo`-named child whose
       roster dir is missing keeps failing closed (#552) instead of being papered
       over by a manifest hit.

    Names are returned in lowercase. Empty set indicates the roster could not
    be read (missing dir or I/O failure); the caller is responsible for
    failing closed. Propagates `RosterResolutionError` when a named child
    roster dir is missing so the caller hard-blocks (safe direction).
    """
    names: set[str] = set()
    for roster_dir in _resolve_roster_dirs(repo):
        names |= _iter_roster_entries(role_prefix_filter=None, roster_dir=roster_dir)
    if not names:
        return names
    return names | _load_org_manifest_names()


def is_single_reviewer_exception(
    pr_labels: list[str],
    reviewers: set[str],
    repo: str | None = None,
) -> bool:
    """Return True if the PR qualifies for the Single-Reviewer Exception.

    Strict conditions per charter `pull-requests.md` § Single-Reviewer Exception
    (Wave-Bootstrap Only):
      1. PR is labeled `wave-bootstrap`
      2. There is EXACTLY ONE distinct reviewer in `reviewers`
      3. That reviewer is a charter-enforcer role in the local roster

    When `repo` names a child repo, the enforcer set unions the parent and
    child rosters (#552) so a child-repo enforcer qualifies for the exception
    on that child's PRs.

    Resolves #228 — hook-side enforcement of the charter exception that was
    previously not honored.
    """
    if "wave-bootstrap" not in pr_labels:
        return False
    if len(reviewers) != 1:
        return False
    sole_reviewer = next(iter(reviewers))
    enforcers = load_charter_enforcer_names(repo=repo)
    return sole_reviewer in enforcers


def ensure_issues_on_board(repo: str, issue_numbers: list[str]) -> None:
    """Best-effort add tech-debt issues to the project board."""
    for num in issue_numbers:
        url = f"https://github.com/{ORG}/{repo}/issues/{num}"
        try:
            subprocess.run(
                [
                    "gh",
                    "project",
                    "item-add",
                    str(PROJECT_NUMBER),
                    "--owner",
                    ORG,
                    "--url",
                    url,
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass  # Best-effort — don't block merge on board failures


class CommentScanUndeterminedError(Exception):
    """Raised by `resolve_review_verdicts` when the comment scan could not
    complete (#981 defense-in-depth).

    An empty reviewer set that came from a FAILED scan is not evidence of
    anything — it is the absence of evidence, and treating it as "no
    approvals found" is the same category of error as counting an
    unverifiable merge as approved. Carries `.reason` (the underlying
    `CommentReviewResult.undetermined` string) so callers can render their
    OWN block/error message without re-deriving why the scan failed.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclasses.dataclass
class ReviewVerdicts:
    """The full review-verdict set for a PR (#1048) — content binding,
    formal + comment reviewer partitioning, roster filtering, and the
    union/threshold inputs.

    This is the SINGLE shared entry point `check()` and
    `pr_review_state.compute_review_state` both consume via
    `resolve_review_verdicts`; neither re-derives this pipeline with its own
    argument list. That re-derivation was exactly the #1046 defect class —
    the driver called `check_comment_reviews` without `content_ts` and
    silently drifted from the gate. A single shared computation cannot drift
    from itself.

    Deliberately carries every intermediate value BOTH callers need for
    their OWN rendering (`check()`'s block message; the driver's text/JSON
    report) — this dataclass is the shared PIPELINE OUTPUT, not a merge
    decision. `check()` still owns its message construction; the driver
    still owns `ReviewState.passes()` and its report rendering.
    """

    number: str | int
    head_ref: str
    labels: list[str]
    branch_author_lastname: str | None
    content_sha: str
    content_ts: datetime | None
    formal_reviewers: set[str]
    # ALL Approved comment Requestors (full names, lowercased) BEFORE roster
    # filtering — needed for the roster-mismatch diagnostic (#498).
    comment_reviewers: set[str]
    non_roster_requestors: set[str]
    roster_comment_reviewers: set[str]
    roster_names: set[str]
    distinct_reviewers: set[str]  # formal_reviewers | roster_comment_reviewers
    # Kept as TWO separate lists rather than pre-concatenated, so a caller that
    # needs to tag each verdict's SOURCE for its own report (the driver's
    # `stale_verdicts[].source` field) doesn't have to reconstruct which
    # sub-list a given entry came from. `stale_verdicts` combines them, in
    # that order, for a caller (check()'s block message) that just needs one
    # unified list.
    stale_verdicts_comment: list[StaleVerdict]
    stale_verdicts_formal: list[StaleVerdict]
    reviews_missing_tech_debt: list[str]
    tech_debt_issue_numbers: list[str]
    # (requestor, raw td_value) pairs where TechDebt: was present, non-"none",
    # but parsed to ZERO issue numbers (main#1055) — carried on the shared
    # pipeline output so BOTH callers (check()'s advisory systemMessage and the
    # driver's report) see the same "present but uncaptured" set instead of it
    # vanishing between "missing" and "filed". Non-blocking: never an input to
    # a merge decision, only surfaced.
    tech_debt_unparseable: list[tuple[str, str]]
    wave_bootstrap_exception: bool
    # WHICH comment-scan mode produced `comment_reviewers` (#1206) — see the
    # COMMENT_SCAN_* constants. Carried on the shared pipeline output so BOTH
    # callers can distinguish "scanned, nobody approved" from "never scanned",
    # which an empty `comment_reviewers` alone cannot express. Defaulted to
    # NOT_RUN so a construction that omits it renders as not-measured rather
    # than falsely claiming a measurement.
    comment_scan: str = COMMENT_SCAN_NOT_RUN

    @property
    def comment_scan_ran(self) -> bool:
        """True iff the PR-comment verdict scan actually read the thread."""
        return self.comment_scan != COMMENT_SCAN_NOT_RUN

    @property
    def stale_verdicts(self) -> list[StaleVerdict]:
        """Combined stale verdicts, comment-based then formal."""
        return self.stale_verdicts_comment + self.stale_verdicts_formal

    @property
    def total_distinct(self) -> int:
        """Count toward the 2-reviewer threshold (charter line 36)."""
        return len(self.distinct_reviewers)


def resolve_review_verdicts(pr_data: dict, repo: str | None = None) -> ReviewVerdicts:
    """Compute a PR's full review-verdict set (#1048) — the shared pipeline
    previously re-assembled independently by `check()` and
    `pr_review_state.compute_review_state`:

      1. `get_latest_content_commit` → T_content (`content_ts`/`content_sha`, #950).
      2. `partition_formal_reviewers` + `check_comment_reviews`, both bound to
         T_content. The comment scan runs for EVERY head ref (#1206); the ref
         selects only which self-review exclusion applies (`comment_scan_scope`),
         and the chosen mode is reported on `ReviewVerdicts.comment_scan`.
      3. `_load_roster_names` and non-roster Requestor filtering (#498).
      4. Union formal + roster-filtered comment reviewers into the distinct
         reviewer set, plus the wave-bootstrap single-reviewer exception (#228).

    `pr_data` is the dict `get_pr_data` returns (author, reviews, headRefName,
    number, labels) — fetching and validating the PR itself stays the
    caller's responsibility, matching how both callers already fetch it
    before doing anything else.

    Raises:
        CommitFetchError: T_content could not be established (#950) —
            propagated verbatim from `get_latest_content_commit`.
        CommentScanUndeterminedError: the comment thread could not be
            completely scanned (#981), or the scan was never dispatched at all
            (#1206 defense-in-depth) — carries `.reason`.
        RosterResolutionError: a named child repo's roster could not be
            resolved (#552) — propagated verbatim from `_load_roster_names`.

    Callers translate each exception into their OWN block/error
    presentation; this function never renders a message, only computes.
    """
    author = pr_data["author"]
    reviews = pr_data["reviews"]
    # `or ""` because a missing/None `headRefName` must degrade to "no
    # identifiable branch author" (a scannable state), never to a skipped scan
    # or a `re.match(None)` crash (#1206). `get_pr_data` already defaults it to
    # `""`; this covers hand-built `pr_data` from other callers and tests.
    head_ref = pr_data["headRefName"] or ""
    number = pr_data["number"]
    labels = pr_data["labels"]

    latest_content = get_latest_content_commit(number, repo=repo)
    content_ts = latest_content[1] if latest_content else None
    content_sha = latest_content[0] if latest_content else ""

    formal_reviewers, stale_formal = partition_formal_reviewers(reviews, author, content_ts)

    # The comment verdict scan runs UNCONDITIONALLY (#1206). It used to be
    # dispatched only for two head-ref shapes — a `{Initial}.{Lastname}[-/]…`
    # persona branch, or a `deployments/**` wave-merge branch. EVERY other shape
    # (`dependabot/**`, any hand-made branch off the charter naming convention,
    # an empty `headRefName`) fell through with the empty `CommentReviewResult()`
    # default and returned zero comment reviewers with no error and no
    # diagnostic — indistinguishable from "scanned the thread and nobody
    # approved". On noorinalabs-deploy#691 that reported two correctly-formed,
    # roster-valid, non-stale Approved verdicts as `0/2 required — (none)`, and
    # blamed the reviewers for it.
    #
    # `comment_scan_scope` is total over head refs, so there is no longer a
    # shape that skips the scan; the ref only selects WHICH self-review
    # exclusion applies. This does not relax the gate — the threshold is
    # unchanged and roster filtering below is untouched; it only makes the
    # verdicts that already exist countable.
    #
    # `branch_author_first_initial` returns `""` on exactly the refs
    # `extract_branch_author_lastname` returns None for (the two regexes have
    # the same shape), so the two halves of the branch author's identity cannot
    # disagree about whether an author was found.
    scan_scope = comment_scan_scope(head_ref)
    if scan_scope == COMMENT_SCAN_NOT_RUN:
        # Defense in depth (#1206): unreachable today, because
        # `comment_scan_scope` is total. Reaching it means a future edit
        # reintroduced a head-ref shape that skips the scan — and an unscanned
        # thread is NOT a zero-approval thread. Fail CLOSED with a named reason
        # (the #981 stance) rather than returning the silent zero this issue
        # exists to kill.
        raise CommentScanUndeterminedError(
            f"the PR-comment verdict scan was not dispatched for head ref {head_ref!r}. "
            "An unscanned comment thread is not evidence of zero approvals, so this is a "
            "determinate failure rather than a 0-reviewer result (#1206)."
        )

    branch_author_lastname = extract_branch_author_lastname(head_ref)
    comment_result = check_comment_reviews(
        number,
        # The `""` sentinel means "no identifiable branch author, so no reviewer
        # is the author" (`charter_trailer.is_branch_author`, main#294). Losing
        # author-exclusion on a bot branch is correct: a bot is never a roster
        # persona, so it could never have been in the reviewer set anyway.
        branch_author_lastname or "",
        repo=repo,
        content_ts=content_ts,
        branch_author_initial=branch_author_first_initial(head_ref),
    )

    if comment_result.undetermined:
        raise CommentScanUndeterminedError(comment_result.undetermined)

    roster_names = _load_roster_names(repo=repo)

    non_roster_requestors = {r for r in comment_result.reviewers if r not in roster_names}
    roster_comment_reviewers = comment_result.reviewers - non_roster_requestors

    distinct_reviewers = formal_reviewers | roster_comment_reviewers

    wave_bootstrap_exception = is_single_reviewer_exception(labels, distinct_reviewers, repo=repo)

    return ReviewVerdicts(
        number=number,
        head_ref=head_ref,
        labels=labels,
        branch_author_lastname=branch_author_lastname,
        content_sha=content_sha,
        content_ts=content_ts,
        formal_reviewers=formal_reviewers,
        comment_reviewers=set(comment_result.reviewers),
        non_roster_requestors=non_roster_requestors,
        roster_comment_reviewers=roster_comment_reviewers,
        roster_names=roster_names,
        distinct_reviewers=distinct_reviewers,
        stale_verdicts_comment=list(comment_result.stale_verdicts),
        stale_verdicts_formal=list(stale_formal),
        reviews_missing_tech_debt=list(comment_result.reviews_missing_tech_debt),
        tech_debt_issue_numbers=list(comment_result.tech_debt_issue_numbers),
        tech_debt_unparseable=list(comment_result.tech_debt_unparseable),
        wave_bootstrap_exception=wave_bootstrap_exception,
        comment_scan=scan_scope,
    )


def check(input_data: dict) -> dict | None:
    """Check PR review requirements. Returns result dict if blocking/warning, None if allowed."""
    tool_name = input_data.get("tool_name", "")
    if tool_name != "Bash":
        return None

    command = input_data.get("tool_input", {}).get("command", "")

    # `--admin` is the emergency override — it bypasses the whole gate
    # (including the batch-loop guard below), matching the existing
    # short-circuit semantics. Checked first so an explicit admin override
    # is honored even for the loop shape.
    if "--admin" in command:
        return None

    # Batch-loop merge guard (#567/#894/#897): a `gh pr merge` with no resolvable
    # literal PR number inside a for/while loop fail-opens the 2-reviewer gate.
    # That covers a loop-variable arg (`$pr`, `${prs[$i]}`, `$(get_pr)`) AND a
    # NO-positional-argument current-branch merge (`git checkout $b && gh pr
    # merge`, #897): in both cases the literal-PR parse returns None, get_pr_data
    # falls back to the cwd branch, and the gate is silently disabled per
    # iteration. HARD BLOCK and instruct one-literal-merge-per-call so the gate
    # stays active — fail in the safe direction
    # (`feedback_safety_direction_over_ux_friction`).
    #
    # This runs BEFORE the `is_merge_command` early-return below ON PURPOSE:
    # `is_merge_command` splits on `&&`/`;`/`|` and checks each segment's
    # FIRST token for `gh pr merge`. In a loop the merge segment leads with
    # the `do` keyword (`do gh pr merge "$pr"`), so `is_merge_command`
    # returns False and `check()` would early-exit — re-opening the exact
    # fail-open hole this guard closes. Detecting the loop shape here is the
    # only placement that fires on it.
    if is_variable_pr_merge_in_loop(command):
        result = {
            "decision": "block",
            "reason": (
                "Batch-loop `gh pr merge` with no resolvable literal PR number "
                '(e.g. `for pr in 48 49 50; do gh pr merge "$pr" ...; done`, or a '
                "no-argument current-branch merge "
                "`for b in a b; do git checkout $b && gh pr merge; done`) is "
                "BLOCKED. The 2-reviewer gate parses a LITERAL PR number to fetch "
                "that PR's reviews; a loop variable — or an absent positional, "
                "which resolves to the per-iteration checked-out branch — cannot "
                "be gate-verified at parse time, so the gate fail-opens and the "
                "merge proceeds UNVERIFIED (this happened twice — P3W11 and "
                "P3W13). Merge one PR per call "
                "with a literal number so the gate verifies each PR:\n"
                "  gh pr merge 48 --repo <owner/repo> --merge\n"
                "  gh pr merge 49 --repo <owner/repo> --merge\n"
                "Run them as separate commands (not a loop). Each literal merge "
                "is checked for two distinct Approved reviewers individually."
            ),
        }
        log_pretooluse_block("validate_pr_review", command, result["reason"])
        return result

    # Not the loop shape — only a plain `gh pr merge <N>` invocation is gated
    # below. Anything else (gh pr list/view/create, git merge, …) is allowed.
    if not is_merge_command(command):
        return None

    pr_number = extract_pr_number(command)
    repo = extract_repo(command)
    pr_display = f"#{pr_number}" if pr_number else "(current branch)"

    # Unresolvable `--repo` (#981). A `-R` value the gate cannot resolve to an
    # OWNER/NAME — an unexpanded `$DA`, or a value with no `/` — is checked
    # BEFORE any fetch, because no fetch can succeed against it and the failure
    # is deterministic rather than transient. Blocking here (a) gives the
    # operator the ONE fix that actually works instead of a misleading "retry",
    # and (b) keeps the guard independent of the network, so it holds when the
    # API is reachable and when it is not.
    #
    # This is the #981 fail-open. Pre-fix, `gh pr merge 451 -R $DA --merge` ran
    # `gh pr view 451 --repo '$DA'`, which exited non-zero, so `get_pr_data`
    # returned None and the branch below ALLOWED the merge with a warning. That
    # short-circuited ahead of every real check — `get_latest_content_commit`'s
    # `CommitFetchError` hard-block never ran and `check_comment_reviews` was
    # never reached — so the 2-reviewer gate was silently off for four P9W25 da
    # merges. Note the issue body pins this on `_resolve_owner_repo` inside
    # `check_comment_reviews`; that path is NOT reachable on the merge path.
    defect = repo_argument_defect(repo)
    if defect is not None:
        result = {
            "decision": "block",
            "reason": (
                f"BLOCKED: PR {pr_display} — the hook cannot determine WHICH REPOSITORY "
                "you are merging in, so it cannot check that this PR has two approving "
                "reviewers.\n"
                f"Detail: {describe_repo_defect(repo, defect)}\n\n"
                "This blocks rather than waving the merge through: a merge whose target "
                "repo the gate cannot identify is precisely a merge the gate cannot "
                "verify, and allowing it silently disables the 2-reviewer rule. Four "
                "PRs merged through this hole in P9W25 (#981).\n"
                "Fix:\n"
                "  - Pass a LITERAL repo, not a shell variable:\n"
                "      gh pr merge 451 --repo noorinalabs/noorinalabs-data-acquisition --merge\n"
                "  - Or drop `--repo` entirely and run the merge from a checkout of the "
                "target repo, letting the hook resolve it from the working directory.\n"
                "Pass `--admin` for emergency overrides only."
            ),
        }
        log_pretooluse_block("validate_pr_review", command, result["reason"])
        return result

    pr_data = get_pr_data(pr_number, repo=repo)

    # Generic fetch failure (#981). The repo argument is well-formed (or absent),
    # so this is an auth / network / wrong-PR-number problem — a DIFFERENT
    # condition from the unresolvable-repo block above, and one a retry may well
    # fix. It still fails CLOSED: an unverifiable merge is blocked, never
    # allowed-with-a-warning (`feedback_safety_direction_over_ux_friction` — when
    # a hook cannot verify, HARD BLOCK with a diagnostic).
    if pr_data is None:
        result = {
            "decision": "block",
            "reason": (
                f"BLOCKED: PR {pr_display} — could not fetch the PR, so the hook cannot "
                "check that it has two approving reviewers.\n"
                f"Detail: `gh pr view` failed for PR {pr_display}"
                + (f" in {repo}" if repo else " (repo resolved from the current directory)")
                + ". The repo argument itself is well-formed, so this is an "
                "authentication, network, or wrong-PR-number failure rather than a "
                "malformed command.\n\n"
                "This blocks rather than allowing with a warning: pre-#981 this branch "
                "returned `allow`, which is how four P9W25 merges bypassed the "
                "2-reviewer gate entirely.\n"
                "Fix one of:\n"
                "  - Re-run the merge (a transient `gh` / network failure).\n"
                "  - Check `gh auth status` — and that the token can read this repo.\n"
                "  - Check the PR number exists in the target repo "
                "(`gh pr view <N> --repo OWNER/NAME`).\n"
                "Pass `--admin` for emergency overrides only."
            ),
        }
        log_pretooluse_block("validate_pr_review", command, result["reason"])
        return result

    # Resolve the full review-verdict set through the ONE shared pipeline
    # (#1048) — content binding, formal + comment reviewer partitioning,
    # roster filtering, and the union/threshold inputs. `check()` and
    # `pr_review_state.compute_review_state` both call `resolve_review_verdicts`
    # rather than each re-assembling this pipeline with their own argument
    # list; that re-derivation was the #1046 defect class.
    try:
        verdicts = resolve_review_verdicts(pr_data, repo=repo)
    except CommitFetchError as exc:
        # Content binding (#950): T_content — the committer timestamp of the
        # branch's latest NON-MERGE commit — could not be established. Without
        # it NO verdict's freshness is knowable: HARD BLOCK rather than fall
        # back to counting everything, which is precisely the pre-#950
        # fail-open (`feedback_safety_direction_over_ux_friction`).
        result = {
            "decision": "block",
            "reason": (
                f"BLOCKED: PR {pr_display} — could not fetch the PR's commit list, so the "
                "hook cannot tell whether the existing approvals reviewed the code you are "
                "about to merge.\n"
                f"Detail: {exc}\n\n"
                "Hook 4 (#950) binds every verdict to the branch's latest NON-MERGE commit: "
                "an approval cast before that commit reviewed code that has since been "
                "rewritten and does not count. Without the commit list there is no such "
                "timestamp, so every verdict's freshness is UNKNOWN.\n"
                "This blocks rather than waving the merge through, because counting "
                "verdicts of unknown freshness is exactly the fail-open #950 closes: on "
                "da#423 the gate counted an approval of the revision that deleted the "
                "Prophet's daughter, after that revision had been rewritten.\n"
                "Fix one of:\n"
                "  - Re-run the merge (a transient `gh api` / network failure).\n"
                "  - Check `gh auth status` and that the `--repo OWNER/NAME` value is correct.\n"
                "Pass `--admin` for emergency overrides only."
            ),
        }
        log_pretooluse_block("validate_pr_review", command, result["reason"])
        return result
    except CommentScanUndeterminedError as exc:
        # Incomplete comment scan (#981 defense-in-depth). An empty reviewer
        # set that came from a FAILED scan is not evidence of anything — it is
        # the absence of evidence, and counting it as "0 approvals found" is
        # the same category of error as counting an unverifiable merge as
        # approved. Hard-block with the underlying reason.
        result = {
            "decision": "block",
            "reason": (
                f"BLOCKED: PR {pr_display} — the charter-format review comments could not "
                "be read, so the hook cannot tell whether this PR has two approving "
                "reviewers.\n"
                f"Detail: {exc.reason}\n\n"
                "This blocks rather than treating an unreadable comment thread as an "
                "empty one: a failed scan and a genuinely unreviewed PR are "
                "indistinguishable from the reviewer set alone, and silently reporting "
                "the former as the latter also skips the TechDebt attestation check "
                "(#981).\n"
                "Fix one of:\n"
                "  - Re-run the merge (a transient `gh api` / network failure, or a "
                "pagination timeout on a very long comment thread).\n"
                "  - Check `gh auth status` and that the token can read this repo's issues.\n"
                "Pass `--admin` for emergency overrides only."
            ),
        }
        log_pretooluse_block("validate_pr_review", command, result["reason"])
        return result
    except RosterResolutionError as exc:
        # Roster resolved relative to the PR's TARGET repo (#552): the parent
        # roster is unioned with the named child repo's `.claude/team/roster/`.
        # If a child repo is named but its roster dir is unreadable, fail in
        # the SAFE direction (HARD BLOCK with diagnostic — never silent
        # parent-only fallback, which would re-block legitimate child
        # reviewers as #552 did).
        result = {
            "decision": "block",
            "reason": (
                f"BLOCKED: PR {pr_display} targets a child repo whose roster directory "
                "could not be resolved, so the 2-reviewer gate cannot validate reviewer "
                "names.\n"
                f"Detail: {exc}\n"
                "Hook 4 resolves the reviewer roster relative to the PR's target repo "
                "(#552): the parent `.claude/team/roster/` is unioned with the named child "
                "repo's `.claude/team/roster/`. The child roster dir was named via "
                "`--repo` but does not exist on disk.\n"
                "Fix one of:\n"
                "  - Ensure the child repo is checked out as a sibling of the parent repo "
                "with a populated `.claude/team/roster/`.\n"
                "  - Correct the `--repo OWNER/NAME` value if the repo name is wrong.\n"
                "Pass `--admin` for emergency overrides only."
            ),
        }
        log_pretooluse_block("validate_pr_review", command, result["reason"])
        return result

    content_ts = verdicts.content_ts
    content_sha = verdicts.content_sha
    stale_verdicts = verdicts.stale_verdicts
    roster_names = verdicts.roster_names
    non_roster_requestors = verdicts.non_roster_requestors
    roster_comment_reviewers = verdicts.roster_comment_reviewers
    total_distinct = verdicts.total_distinct

    # Single-Reviewer Exception (resolves #228) — wave-bootstrap PRs reviewed
    # by a charter enforcer may merge with one Approved comment instead of
    # two. Charter-enforcer role check uses the target-repo-resolved roster.
    if total_distinct == 1 and verdicts.wave_bootstrap_exception:
        # Exception applies — fall through to TechDebt check, then allow.
        pass
    elif total_distinct < 2:
        # If the shortfall is wholly or partly caused by STALE verdicts, lead with
        # a diagnostic that names each one (#950). Without this an operator seeing
        # `0/2 approvals` on a PR with two visible `Approved` comments concludes
        # the hook is broken — so the message must say WHICH verdict went stale,
        # WHEN it was cast, and WHICH commit invalidated it, and must pre-empt the
        # natural next fear ("did a branch update just invalidate my approvals?").
        stale_diagnostic = ""
        if stale_verdicts:
            lines = [
                f"BLOCKED: PR {pr_display} has {total_distinct}/2 CURRENT approvals — "
                f"{len(stale_verdicts)} verdict(s) went STALE.\n"
            ]
            for sv in sorted(stale_verdicts, key=lambda v: v.created_at):
                cast_at = sv.created_at or "<no timestamp>"
                lines.append(
                    f"  {sv.reviewer:<18} {sv.verdict:<17} {cast_at}  "
                    f"x STALE — cast before {content_sha} "
                    f"({content_ts.isoformat() if content_ts else '?'})\n"
                )
            lines.append(
                "\nA verdict cast BEFORE the branch's latest non-merge commit reviewed code "
                "that has since been rewritten, so it does not count toward the 2-reviewer "
                "threshold. It has not been deleted or dismissed — only not counted.\n"
                "Branch updates from `main` (merge commits) do NOT invalidate a verdict; "
                "only NEW AUTHORED commits do. If you just ran `update-branch`, that is not "
                "what happened here.\n"
                "Fix: ask the reviewer to re-review at the current head and post a fresh "
                f"`RequestOrReplied: Approved` comment (head content commit: {content_sha}).\n"
                "Rationale (#950): on da#423 this gate counted an approval of the revision "
                "that deleted the Prophet's daughter — after that revision had been rewritten "
                "precisely because it was wrong.\n\n"
            )
            stale_diagnostic = "".join(lines)

        # If the shortfall is wholly or partly caused by non-roster Requestor
        # strings, prepend a dedicated diagnostic that names them (#498). The
        # general 2-reviewer guidance still follows below.
        roster_diagnostic = ""
        if non_roster_requestors:
            sample_roster = sorted(roster_names)[:20]
            sample_label = (
                f"Valid roster ({len(roster_names)} total, first 20): {', '.join(sample_roster)}"
                if roster_names
                else "Valid roster: <empty — local roster dir could not be read>"
            )
            raw_total = len(verdicts.comment_reviewers)
            roster_count = len(roster_comment_reviewers)
            roster_diagnostic = (
                f"BLOCKED: PR {pr_display} has {raw_total} distinct Requestor string(s) "
                f"on Approved verdicts but only {roster_count} are recognized roster "
                "members.\n"
                f"Non-roster: {', '.join(sorted(non_roster_requestors))}\n"
                f"{sample_label}\n"
                "Hook 4 (#498) requires every Approved verdict's Requestor to match a "
                "persona in `.claude/team/roster/` — non-roster Requestor strings do "
                "NOT count toward the 2-reviewer threshold. Re-post the verdict under a "
                "roster persona, or amend the roster if this is a new member.\n\n"
            )
        # State the comment scan's OWN status alongside the count (#1206). A
        # shortfall reported without it is ambiguous between "the thread was
        # read and the approvals are not there" and "the thread was never
        # read" — and for every non-persona head ref the answer used to be the
        # second one, silently. Naming the mode makes the count self-describing
        # on the surface an operator actually sees at merge time.
        scan_diagnostic = ""
        if not verdicts.comment_scan_ran:
            scan_diagnostic = (
                f"BLOCKED: PR {pr_display} — the PR-comment verdict scan DID NOT RUN, so the "
                f"{total_distinct}/2 count below is NOT a measurement of this PR's approvals.\n"
                "Any comment-based Approved verdicts on this PR were never read (#1206). This "
                "is a hook defect, not a review shortfall — report it rather than asking "
                "reviewers to re-approve.\n\n"
            )
        elif verdicts.comment_scan == COMMENT_SCAN_NO_BRANCH_AUTHOR:
            scan_diagnostic = (
                f"NOTE: head ref `{verdicts.head_ref or '(unknown)'}` carries no "
                "`{Initial}.{Lastname}` branch-author prefix (a bot branch, a wave-merge "
                "branch, or a branch off the charter naming convention), so the comment "
                "verdict scan ran WITHOUT self-review exclusion — every roster-valid "
                "Approved Requestor counts. The scan DID run; the count below is a real "
                "measurement (#1206).\n\n"
            )

        result = {
            "decision": "block",
            "reason": (
                scan_diagnostic
                + stale_diagnostic
                + roster_diagnostic
                + f"BLOCKED: PR {pr_display} has {total_distinct}/2 required peer reviews. "
                "At least TWO Approved reviews from distinct non-authors are required before "
                "merge.\n"
                "Charter § Comment-Based Reviews counts distinct Requestor values across "
                "Approved comments (resolves main#244).\n"
                "Use `gh pr comment <PR#> --body '...'` with charter format:\n"
                "  Requestor: <reviewer>  Requestee: <PR author>  "
                "RequestOrReplied: Approved  TechDebt: none | #issue, ...\n\n"
                "Common failure mode — Reply vs Approved:\n"
                "  RequestOrReplied: Reply / Replied / Request / ChangesRequested do NOT\n"
                "  count toward the 2-reviewer threshold, EVEN IF the body prose says\n"
                '  "Approved" or "looks good." The hook parses the RequestOrReplied:\n'
                "  field directly — body prose is not inspected for verdict signals.\n"
                "  If a reviewer's intent was to approve, they must post a NEW comment\n"
                "  with `RequestOrReplied: Approved` (Reply comments cannot be edited\n"
                "  in-place to change the field).\n\n"
                "Common failure mode — Requestor / Requestee swap:\n"
                "  Requestor is the REVIEWER (the team member POSTING the comment).\n"
                "  Requestee is the PR AUTHOR (the team member ADDRESSED by the\n"
                "  comment). The hook counts distinct Requestor values across Approved\n"
                "  comments. If two reviewers BOTH set `Requestor:` to the PR author\n"
                "  (treating Requestor as 'addressed-to'), the hook sees 1 distinct\n"
                "  reviewer (the author's name, twice) even though two people approved.\n"
                "  This is the W9 PR#349 cascade root cause — orchestrator spawn brief\n"
                "  template had the fields swapped; 7 reviewer comments posted before\n"
                "  the hook surfaced the count mismatch.\n"
                "  Diagnose the swap directly:\n"
                "    gh api repos/<owner>/<repo>/issues/<PR>/comments \\\n"
                "      --jq '[.[] | select(.body | "
                'contains("RequestOrReplied: Approved"))\n'
                "             | .body "
                '| capture("Requestor: *(?<r>[^\\\\n]+)") '
                "| .r] | unique'\n"
                "  Expected: distinct reviewer names. Seen: PR author's name repeated\n"
                "  → swap. Charter `pull-requests.md § Comment-Based Reviews` Direction\n"
                "  table (Approved row): Requestor=reviewer, Requestee=PR author.\n\n"
                "Diagnose the count yourself before retrying merge:\n"
                "  gh api repos/<owner>/<repo>/issues/<PR>/comments \\\n"
                "    --jq '[.[] | select(.body | "
                'contains("RequestOrReplied: Approved"))] | length\'\n\n'
                "Common failure mode — prose-mention of fields outside the trailer block:\n"
                "  As of #511 the hook ONLY extracts Requestor/RequestOrReplied from the\n"
                "  trailer-block substring (after the LAST `---` separator line) and ignores\n"
                "  matches inside backticks/code fences. If your verdict comment quotes\n"
                "  field syntax in prose (e.g., describing the PR body's trailer), make\n"
                "  sure the actual structured-fields block follows a `---` separator AND\n"
                "  is the very last block. Inline-code fences (`Requestor: foo`) and fenced\n"
                "  code (``` ... ```) are stripped before matching.\n"
                "  Historical instances driving this enforcement (P3W11 batch 11, 2026-05-19):\n"
                "    - main#509 — Wanjiku's prose described the bare-line block; captured\n"
                "      Requestor as rest-of-line garbage; 1/2 false-block.\n"
                "    - deploy#337 — Lucas noted PR body lacked the trailer; captured\n"
                "      garbage Requestor; 1/2 false-block.\n"
                "    - deploy#339 — Bereket quoted `Requestor: (TBD — orchestrator will\n"
                "      assign)`; captured TBD as Requestor; 1/2 false-block.\n"
                "  All three required orchestrator REST PATCH pre-#511 fix.\n\n"
                "Single-Reviewer Exception (charter § Single-Reviewer Exception (Wave-Bootstrap "
                "Only)): label PR `wave-bootstrap` AND have a charter-enforcer review (Standards "
                "Lead, Manager, Tech Lead, Project Lead, or Program Director).\n"
                "Pass `--admin` for emergency overrides only.\n"
                "See memory feedback_pr_review_verdict_format.md for full context."
            ),
        }
        log_pretooluse_block("validate_pr_review", command, result["reason"])
        return result

    missing = verdicts.reviews_missing_tech_debt
    if missing:
        names = ", ".join(missing)
        result = {
            "decision": "block",
            "reason": (
                f"BLOCKED: PR {pr_display} has review(s) missing the mandatory "
                f"TechDebt: attestation line.\n"
                f"Reviewers without TechDebt line: {names}\n"
                "Charter § Comment-Based Reviews requires every Approved/ChangesRequested "
                "comment to include:\n"
                "  TechDebt: none        (if no tech-debt found)\n"
                "  TechDebt: #15, #16    (if issues were filed)\n"
                "Reviewer must create tech-debt labeled issues for all non-blocking "
                "findings BEFORE posting the verdict.\n"
                "Pass `--admin` for emergency overrides only."
            ),
        }
        log_pretooluse_block("validate_pr_review", command, result["reason"])
        return result

    # All checks passed — ensure any referenced tech-debt issues are on the board
    td_issues = verdicts.tech_debt_issue_numbers
    if td_issues:
        board_repo_name = ""
        if repo and "/" in repo:
            board_repo_name = repo.split("/", 1)[1]
        else:
            try:
                repo_result = subprocess.run(
                    ["gh", "repo", "view", "--json", "name"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if repo_result.returncode == 0:
                    board_repo_name = json.loads(repo_result.stdout).get("name", "")
            except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
                pass
        if board_repo_name:
            ensure_issues_on_board(board_repo_name, td_issues)

    # Non-blocking observability (main#1055): a TechDebt line that is present,
    # not "none", but parsed to ZERO issue numbers used to vanish silently —
    # neither flagged as missing nor recorded as filed. Surface it as an
    # advisory `systemMessage` so the gap is visible without blocking merge.
    unparseable = verdicts.tech_debt_unparseable
    if unparseable:
        detail = "; ".join(f"{name}: {value!r}" for name, value in unparseable)
        return {
            "decision": "allow",
            "systemMessage": (
                f"NOTE: PR {pr_display} has {len(unparseable)} verdict(s) with a "
                "TechDebt line present but not parseable as issue reference(s) — "
                f"recorded as ZERO tech-debt refs, not blocked: {detail}. Charter "
                "format: `TechDebt: none` or `TechDebt: #15, #16` (a bare `15, 16` "
                "is also accepted); free text is not."
            ),
        }

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
