#!/usr/bin/env python3
"""PreToolUse hook: Validate labels before gh issue create.

Extracts --label values from `gh issue create` commands and verifies each
label exists in the repository. Blocks execution if any label is missing.

Input Language:
  Fires on:      PreToolUse Bash
  Matches:       gh issue create [--repo {OWNER/REPO} | -R {OWNER/REPO}]
                                 [--label {NAME} | -l {NAME}]... [other flags]
  Does NOT match: gh issue list, gh issue view, gh issue edit, gh label create,
                  gh pr create. Also does NOT match `--label` substrings that
                  appear INSIDE the value of another flag (e.g. inside `--body`)
                  — see Bug 2 below.
  Flag pass-through:
    --repo / -R   → forwarded to `gh label list` so we query the same repo
                    the user is creating the issue in (Bug 1 fix). Without
                    this, cwd determines which repo's labels are checked,
                    which rejects valid labels when cwd != target repo.
    --label / -l  → only the actual flag values are extracted as labels;
                    comma-separated values inside one flag are split. Body
                    content is NEVER scanned for labels (Bug 2 fix).

Tokenization (main#1351 — the shared-finder rewrite):
  The command is normalized, tokenized, split into pipeline segments, and only
  the segments that ARE a `gh issue create` invocation are scanned for label
  flags. Everything is done through `_shell_parse`'s finders rather than a
  private grammar — the #663 / #1150 invariant this hook was named in the
  umbrella for violating.

  Three passes run before tokenization, each closing one measured defect:

    strip_data_heredocs           A `cat > file <<'BODY' … BODY` body is DATA
                                  fed to a sink, not an option list (#1174's
                                  code-vs-data class). Scanning it treated the
                                  `bash -lc` in a shell-parsing write-up as
                                  `-l c` and minted a label named `c` — twice
                                  in wave-29, both false blocks.
    normalize_command_substitutions
                                  `url=$(gh issue create … --label meta-issue)`
                                  glues the closing paren onto the last
                                  argument, so the hook demanded a label named
                                  `meta-issue)` and blocked the filing of
                                  #1150 itself.
    normalize_command_separators  Newlines / `;` / `|` become real separator
                                  tokens, without which a multi-line command
                                  collapses into one segment headed by `cd`
                                  and the gh invocation is never found.

  Segment scoping is what makes the label scan sound: a `-lc` (or a documented
  `--label ghost`) anywhere OUTSIDE the `gh issue create` segment — a heredoc
  body, a sibling command, a `--body` value — cannot contribute a label,
  because the scan never looks there.

Fail-open posture (deliberate — FIVE conditions, only one of them silent):
  A label-existence pre-flight is best-effort — `gh` itself rejects a genuinely
  missing label server-side — whereas a false block stops valid work. So the
  hook allows rather than blocks whenever the parse is not trustworthy:

    1. `gh label list` unavailable (network, or a `--repo` gh rejects)
                                                     -> allow + warning
    2. shlex cannot tokenize the command (#661)      -> allow, SILENT
    3. a label token carries a shell metacharacter   -> allow + systemMessage
    4. an unterminated heredoc                       -> allow + systemMessage
    5. label flags after an unquoted mid-argument `$( … )` are unreadable
                                                     -> note naming the count

  Keep this list, `_extract_labels`, and the Hook 5 entry in
  `.claude/team/charter/hooks/catalog-01-12.md` in step. It has drifted once
  already: the catalog said "three" while the code had four (main#1394 review
  round 2, MF2). Condition 2 is the only silent one, and deliberately so — its
  trigger is "this Bash command has quoting shlex cannot handle", which is
  common and usually unrelated to labels, so announcing it would mostly annoy
  commands that were never being validated.

Exit codes:
  0 — allow (not gh issue create, or all labels exist)
  2 — block (missing labels detected)
"""

import json
import os
import subprocess
import sys
from typing import NamedTuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hook_main import run_blocking
from _repo_flag_parse import extract_repo  # noqa: E402
from _shell_parse import (  # noqa: E402
    classify_heredocs,
    find_gh_subcommand,
    iter_command_segments,
    normalize_command_separators,
    normalize_command_substitutions,
    strip_data_heredocs,
    tokenize,
    walk_flag_values,
)
from annunaki_log import log_pretooluse_block  # noqa: E402

# Flags whose VALUE is a label list (comma-separated allowed by gh).
_LABEL_FLAGS = {"--label", "-l"}

# Characters that cannot appear in a correctly-parsed label token. A GitHub
# label may contain spaces, unicode, emoji and most punctuation — `good first
# issue` is a real default label — so this set is deliberately restricted to
# SHELL metacharacters, whose presence means the tokenizer, not the user, put
# them there. Both wave-29 defect families land here (`meta-issue)`, `` c` ``),
# which is why this stays as a backstop even though the parse fixes above
# remove the two known producers.
_SHELL_METACHARS = frozenset("()`$;|&<>\n\r\\")


def get_existing_labels(repo: str | None = None) -> set[str]:
    """Fetch all existing labels from the repository.

    When `repo` is provided (OWNER/REPO), forward it to `gh label list` so we
    query the same repo the user is creating the issue in (Bug 1 fix).
    """
    try:
        cmd = ["gh", "label", "list", "--limit", "500", "--json", "name"]
        if repo:
            cmd.extend(["--repo", repo])
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return set()
        labels_data = json.loads(result.stdout)
        return {label["name"] for label in labels_data}
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return set()


def issue_create_segments(command: str) -> list[list[str]] | None:
    """Post-verb tokens of every real `gh issue create` invocation in `command`.

    Returns None when the command cannot be tokenized (shlex failure — the
    #661 fail-open), and `[]` when it tokenizes but holds no `gh issue create`
    invocation. Each returned list is the segment's tokens AFTER the
    `issue create` verbs, ready for `walk_flag_values`.

    Normalization order matters and is not interchangeable:

      1. `strip_data_heredocs` FIRST, so an inert heredoc body is gone before
         anything tries to read shell structure out of prose. Bodies fed to an
         interpreter are deliberately kept — those really are code.
      2. `normalize_command_substitutions`, so `$( … )` / backtick / subshell
         boundaries become separators instead of being glued to the tokens on
         either side.
      3. `normalize_command_separators` LAST, because steps 1–2 can expose
         newlines and `;`/`|` that were previously inside a body or a
         substitution, and this pass is what turns them into standalone tokens
         `iter_command_segments` can split on.

    Two boundaries, both resolving toward the fail-open this hook already has:

      - **Unterminated heredoc → validate nothing.** `strip_data_heredocs`
        fails toward KEEPING an unterminated body (its callers are bypass
        matchers, for which keeping is the safe direction). For a
        false-positive-sensitive gate the safe direction is the opposite: the
        retained body's prose would be scanned as option tokens, which is
        defect B all over again. Such a command cannot run as written anyway,
        so there is nothing to pre-flight.
      - **An UNQUOTED `$( … )` in the middle of a `gh issue create`'s own
        arguments** ends the parseable run of arguments, so flags after it go
        unvalidated. A recall loss, never a false block — and it is REPORTED
        rather than silent; see `_extract_labels`.

        The word *unquoted* is load-bearing and the hole is much narrower than
        it sounds. A substitution inside double quotes — `--body "$(cat b.md)"`,
        the shape that actually occurs — is left untouched by the normalizer,
        arrives as one shlex token, and costs NO recall: labels after it are
        read normally. Measured for both, and pinned by
        `MidArgumentSubstitutionRecallTests`. Only the bare form
        (`--body $(cat b.md)`) truncates.

    Why not splice the substitution's words into the outer segment instead
    (main#1394 review round 2, Nino Kavtaradze — MF1)
    ================================================================

    An earlier revision of this docstring justified the truncation by claiming
    a splice "makes `--repo` resolve to `cat`" and would query the wrong repo.
    **That was false and is retracted.** `check` resolves the repo from the RAW
    command via `_repo_flag_parse.extract_repo`, never from these segments, so
    a splice here cannot affect repo resolution at all; and `extract_repo` on
    that shape returns `'$(cat'`, whose `gh label list` exits non-zero and
    lands in the existing allow-with-a-warning branch. Measured, both.

    The truncation stands anyway, on a hazard that IS present — one the
    retracted reason obscured. Splicing makes a substitution's first word look
    like the value of the flag preceding it, so a label flag whose value is
    computed:

        gh issue create --repo o/r --label $(cat labelfile)
          split (shipped) -> no labels        -> allow
          splice          -> label 'cat'      -> BLOCK, and `cat` is no label

    That is a false block manufactured by the parse — this hook's entire defect
    class — and it needs no other change to become live. Verified end-to-end
    through `check` against the real label set. `--label` values are exactly
    what this hook reads, so the splice is unsafe precisely where it matters.
    """
    # Cheap exact early-out. `find_gh_subcommand` matches only a literal `gh`
    # token, so a command with no `gh` substring cannot produce a segment —
    # this skips the normalization + shlex work for the overwhelming majority
    # of Bash calls without weakening the match by one command. (Indirection
    # like `g=gh; $g issue create` is not resolved either way: the finder needs
    # a literal `gh` in command position.)
    if "gh" not in command:
        return []
    text = strip_data_heredocs(command)
    text = normalize_command_substitutions(text)
    text = normalize_command_separators(text)
    tokens = tokenize(text)
    if tokens is None:
        return None

    found: list[list[str]] = []
    for segment in iter_command_segments(tokens):
        gh = find_gh_subcommand(segment)
        if gh is None:
            continue
        _gh_globals, rest = gh
        if rest[:2] == ["issue", "create"]:
            found.append(rest[2:])
    return found


def _labels_from_segments(segments: list[list[str]]) -> list[str]:
    """Flatten `--label`/`-l` values out of already-scoped segments."""
    labels: list[str] = []
    for rest in segments:
        for raw in walk_flag_values(rest, _LABEL_FLAGS):
            for value in raw.split(","):
                label = value.strip()
                if label:
                    labels.append(label)
    return labels


class LabelScan(NamedTuple):
    """What the parse could establish about a command's labels.

    `skip_reason` — set when NOTHING was validated and the caller should say so.
    `unvalidated` — how many label flags were swallowed by a mid-argument
    command substitution: validated nothing, blocked nothing, but the user
    should know the pre-flight did not cover them.
    """

    labels: list[str]
    skip_reason: str | None
    unvalidated: int


def _extract_labels(command: str) -> LabelScan:
    """The full scan result that `extract_labels` narrows to a label list.

    Every path that stops short of a complete answer reports WHY, so `check`
    can say it. A gate that quietly stops gating is the failure mode this
    hook's own history is made of, and shipping new silent fail-opens inside
    the fix for that would reproduce it (main#1394 review round 2, MF2).

    Three incomplete outcomes, all allow-shaped:

      - shlex could not tokenize the command (#661) — the one skip left
        deliberately SILENT. It is pre-existing behaviour, and its trigger is
        "this Bash command has quoting shlex cannot handle", which is common
        and usually has nothing to do with labels; a message here would fire
        on unrelated commands. Called out in the charter catalog as the
        remaining silent case rather than left implicit.
      - an unterminated heredoc — the body would be read as options.
      - a label token carrying a shell metacharacter — the right response to
        "the tokenizer produced `meta-issue)`" is to distrust the whole parse,
        not to demand the user create a label named `meta-issue)`.

    Plus one PARTIAL outcome: `unvalidated`, measured by differential rather
    than guessed. The split reading (safe, what we validate) is compared with
    the splice reading (unsafe, never validated — see
    `normalize_command_substitutions`); any labels the splice can see that the
    split cannot were swallowed by a mid-argument substitution. Using the
    splice ONLY to count what we missed keeps the false-block hazard out of the
    decision while still making the loss visible.
    """
    if any(not span.terminated for span in classify_heredocs(command)):
        return LabelScan(
            [],
            "the command contains an unterminated heredoc, so its body cannot be "
            "told apart from the option list",
            0,
        )

    segments = issue_create_segments(command)
    if segments is None:
        return LabelScan([], None, 0)

    labels = _labels_from_segments(segments)

    suspect = [label for label in labels if _SHELL_METACHARS.intersection(label)]
    if suspect:
        rendered = ", ".join(repr(label) for label in suspect)
        return LabelScan([], f"parsed label token(s) carrying a shell metacharacter: {rendered}", 0)

    return LabelScan(labels, None, _count_swallowed_labels(command, labels))


def _count_swallowed_labels(command: str, found: list[str]) -> int:
    """How many label flags a mid-argument `$( … )` hid from the split reading.

    Returns 0 for the overwhelming majority of commands — including
    `url=$(gh issue create … --label x)`, where the substitution wraps the
    whole invocation and both readings agree. Only a substitution INSIDE the
    argument list makes the counts differ.

    The spliced labels are counted and then discarded. They are never returned,
    validated, or named in a message: the splice reading manufactures a label
    out of the substituted command's name (`--label $(cat f)` -> `cat`), so
    surfacing those strings would put a parser artifact in front of the user
    as though it were their label.
    """
    if "$(" not in command and "`" not in command:
        return 0
    text = strip_data_heredocs(command)
    text = normalize_command_substitutions(text, separator=" ")
    text = normalize_command_separators(text)
    tokens = tokenize(text)
    if tokens is None:
        return 0
    spliced: list[list[str]] = []
    for segment in iter_command_segments(tokens):
        gh = find_gh_subcommand(segment)
        if gh is None:
            continue
        _gh_globals, rest = gh
        if rest[:2] == ["issue", "create"]:
            spliced.append(rest[2:])
    return max(0, len(_labels_from_segments(spliced)) - len(found))


def extract_labels(command: str) -> list[str]:
    """Label names passed via --label / -l to a `gh issue create` in `command`.

    Scoped to real `gh issue create` segments (main#1351): a `--label` inside
    another command in the same string, inside a data heredoc body, or inside
    another flag's value is NOT a label. Comma-separated values within one flag
    are split. Returns `[]` — the gate then ALLOWS — whenever the parse is not
    trustworthy; see the module docstring's fail-open posture.
    """
    return _extract_labels(command)[0]


def _partial_note(scan: LabelScan) -> dict:
    """Allow, but say that a command substitution hid some label flags.

    Reached only when nothing is being blocked. When the hook DOES block, the
    same fact is appended to the block reason instead — a user who is already
    being stopped should not get two separate messages about one command.
    """
    n = scan.unvalidated
    return {
        "decision": "allow",
        "systemMessage": (
            f"NOTE: validate_labels could not check {n} label flag(s) — they follow a "
            "command substitution inside the `gh issue create` arguments, which ends "
            "the parseable run of arguments. Nothing is blocked and the labels that "
            "WERE readable are fine. `gh` still rejects a genuinely missing label "
            "server-side; run `gh label list` if you want certainty (main#1410)."
        ),
    }


def check(input_data: dict) -> dict | None:
    """Check labels on gh issue create. Returns result dict if blocking/warning, None if allowed."""
    tool_name = input_data.get("tool_name", "")
    if tool_name != "Bash":
        return None

    command = input_data.get("tool_input", {}).get("command", "")

    scan = _extract_labels(command)
    if scan.skip_reason is not None:
        return {
            "decision": "allow",
            "systemMessage": (
                f"NOTE: validate_labels validated NO labels — {scan.skip_reason}. "
                "This is evidence the hook could not parse the command, not "
                "evidence of a missing label, so no block is raised. `gh` still "
                "rejects a genuinely missing label server-side. Please report the "
                "command shape (main#1351)."
            ),
        }
    if not scan.labels:
        return _partial_note(scan) if scan.unvalidated else None

    repo = extract_repo(command)
    existing = get_existing_labels(repo=repo)
    if not existing:
        return {
            "decision": "allow",
            "systemMessage": (
                "WARNING: Could not fetch existing labels to validate. "
                "Proceeding without validation. Run `gh label list` to verify."
            ),
        }

    missing = [label for label in scan.labels if label not in existing]
    if not missing:
        return _partial_note(scan) if scan.unvalidated else None

    create_repo_flag = f" --repo {repo}" if repo else ""
    suggestions = "\n".join(f'  gh label create "{label}"{create_repo_flag}' for label in missing)
    repo_note = f" in {repo}" if repo else ""
    partial = (
        f"\n\nNote: {scan.unvalidated} further label flag(s) follow a command "
        "substitution and were not checked either way (main#1410)."
        if scan.unvalidated
        else ""
    )
    result = {
        "decision": "block",
        "reason": (
            f"BLOCKED: The following label(s) do not exist{repo_note}: "
            f"{', '.join(missing)}\n"
            f"Create them first:\n{suggestions}{partial}\n\n"
            "See charter § GitHub Label Hygiene: verify labels exist before creating issues."
        ),
    }
    log_pretooluse_block("validate_labels", command, result["reason"])
    return result


def main() -> None:
    run_blocking(check, "validate_labels")


if __name__ == "__main__":
    main()
