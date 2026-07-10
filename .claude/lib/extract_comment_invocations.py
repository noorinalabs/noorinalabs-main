#!/usr/bin/env python3
"""Harvest real PreToolUse Bash payloads that create PR/issue comments.

Why this exists (#934, Oyunbileg Batbayar's reframing)
======================================================

Repairing three specific fail-open paths (quoted paths, `~`, `$VAR`) closes
one night's incident. It does not close the class. The class is:

    A hook's tests pass a bare `/tmp/body.json` where production passes a
    quoted `$CLAUDE_JOB_DIR` path. That hook has not been tested against
    production; it has been tested against a fixture chosen to make it pass.

The extractable rule is therefore NOT "use the production path in the
fixture." It is:

    The test must call the hook the way the harness calls it — with an
    invocation form derived from the CALLER, not hand-written beside it.

So this script reads the harness's own session transcripts, pulls out the
`tool_use` payloads for `Bash` whose command creates a comment, and emits
them verbatim as a JSONL corpus. The test suite replays that corpus through
`validate_review_comment_format.check()` and asserts an invariant. Nobody
retypes a command; the commands come off the wire.

The corpus is a committed snapshot, so CI does not depend on machine-local
transcripts. Refresh it by re-running this script when new invocation shapes
appear:

    python3 .claude/lib/extract_comment_invocations.py \\
        --out .claude/hooks/tests/fixtures/real_comment_invocations.jsonl

Residual, stated plainly: a snapshot closes every axis present in the
transcripts it was cut from. An invocation shape nobody has used yet
(a fifo, a relative `--body-file`, a tab-indented heredoc) enters the corpus
only on the next refresh. This narrows the class; it does not eliminate it.
Widening it further means running the hook against live payloads in the
harness rather than in a unit test, which is a different change.

What is captured: the verbatim command string and the tool name. Note that a
heredoc invocation carries its body *inside* the command, so those bodies do
land in the corpus. Anything token-shaped is redacted before writing.

Sampling is capped per SHAPE SIGNATURE (`_signature`), not per body-form. A
per-form cap taking the shortest N drops rare shapes, and a rare shape is
precisely the one a parser fails on: `URL=$(gh api -X POST ...)` was discarded
that way, and its absence read as "0 unrecognized." Within a signature the cap
takes shortest-first, which sheds multi-kilobyte review bodies while keeping
the invocation shape — shape is what this corpus exercises. Body content is
covered by the verbatim `real_verdict_*.txt` fixtures.

One more trap, learned here: this harvester must not reuse the hook's
segmenter uncritically. It first did, inherited the same `URL=$(` bug, and
therefore agreed with the hook it was auditing. A corpus assembled by the
parser under test cannot falsify that parser.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Iterator

# A command that creates a PR comment. Deliberately broader than the hook's own
# `is_comment_command` — the corpus must be able to catch invocations the hook
# currently fails to recognize, or it would only ever confirm what the hook
# already believes. Do not narrow this to match the hook.
#
# `gh issue comment` is excluded on purpose: the hook is PR-scoped and asserts
# that shape does NOT match. `gh api .../issues/<N>/comments` is included —
# that is the REST endpoint for PR comments (a PR is an issue).
_PR_COMMENT_CLI = re.compile(r"^gh\s+pr\s+comment\b")
_GH_API = re.compile(r"^gh\s+api\b")
_CREATE_ENDPOINT = re.compile(r"issues/\d+/comments\b")
# `issues/comments/<id>` is the EDIT endpoint. A PATCH to it amends an existing
# comment; it never creates one, so it is not this hook's business.
_EDIT_ENDPOINT = re.compile(r"issues/comments/\d+")
_MUTATES = re.compile(r"-X\s+(POST|PATCH)|--method\s+(POST|PATCH)")
_WRITE_MARKER = re.compile(
    r"--input\b|--raw-field\b|--field\b|(?<!\w)-f\b|(?<!\w)-F\b|-X\s+POST|--method\s+POST"
)
# Segment separators, matching the hook's own splitter.
_SEPARATORS = re.compile(r"\s*(?:&&|\|\||\||;|\n)\s*")
# `VAR=$(cmd)` and `$(cmd)` execute. `VAR="cmd"` does not — it builds a string.
_SUBSTITUTION = re.compile(r"^(?:[A-Za-z_][A-Za-z0-9_]*=)?\$\(\s*")
# `(?!\$\()` matters: a naive `\S*\s+` eats `URL=$(gh ` whole and leaves a
# segment beginning at `api`, so the harvester would silently DROP the very
# command the hook fails to recognize. The harvester and the hook shared that
# blind spot, and the corpus reported a clean zero as a result — a detector
# agreeing with the thing it was auditing. Keep the two segmenters honest.
_ENV_PREFIX = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=(?!\$\()\S*\s+")


def _segments(command: str) -> Iterator[str]:
    for raw in _SEPARATORS.split(command):
        segment = _SUBSTITUTION.sub("", raw.lstrip())
        while _ENV_PREFIX.match(segment):
            segment = _ENV_PREFIX.sub("", segment)
        yield segment


def creates_pr_comment(command: str) -> bool:
    """True only if some SEGMENT actually creates a PR comment.

    Segment-anchored on purpose. A `gh api ...` sitting inside a quoted string
    (`CMD="gh api -X POST .../comments"`, as test scaffolding does) never runs,
    and a corpus that captured it would demand the hook recognize a command
    that was never issued — pushing the recognizer to over-match.
    """
    for segment in _segments(command):
        if _PR_COMMENT_CLI.match(segment):
            return True
        if not _GH_API.match(segment):
            continue
        if _EDIT_ENDPOINT.search(segment):
            continue
        if not _CREATE_ENDPOINT.search(segment):
            continue
        if _MUTATES.search(segment) and not re.search(r"-X\s+POST|--method\s+POST", segment):
            continue  # PATCH/DELETE against the create endpoint: not a create
        if _WRITE_MARKER.search(segment):
            return True
    return False


# Redact anything that looks like a token before a command string is committed.
_SECRET = re.compile(
    r"\b(gh[pousr]_[A-Za-z0-9]{16,}|ghs_[A-Za-z0-9]{16,}|[A-Za-z0-9_-]{40,}\.[A-Za-z0-9_-]{20,})\b"
)


def _default_transcript_root() -> Path:
    return Path.home() / ".claude" / "projects"


def iter_bash_commands(transcript: Path) -> Iterator[str]:
    """Yield every Bash `tool_use` command string in one transcript."""
    try:
        text = transcript.read_text(errors="replace")
    except OSError:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        message = entry.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "tool_use" or block.get("name") != "Bash":
                continue
            tool_input = block.get("input")
            if not isinstance(tool_input, dict):
                continue
            command = tool_input.get("command")
            if isinstance(command, str) and command:
                yield command


def harvest(root: Path, project_filter: str | None = None) -> list[str]:
    """Collect deduplicated PR-comment-creating commands across all transcripts.

    `project_filter` restricts to transcript directories whose name contains it,
    keeping the committed corpus to this org's own invocations.
    """
    seen: dict[str, None] = {}
    for transcript in sorted(root.rglob("*.jsonl")):
        if project_filter and project_filter not in str(transcript.parent):
            continue
        for command in iter_bash_commands(transcript):
            if creates_pr_comment(command):
                seen.setdefault(_SECRET.sub("<REDACTED>", command), None)
    return list(seen)


def _classify(command: str) -> str:
    """Label the body-passing form, so the corpus can be checked for coverage."""
    if re.search(r"--body-file[=\s]", command):
        return "body-file"
    if re.search(r"--input\s+-\B|--input\s+['\"]?-['\"]?(\s|$)", command):
        return "stdin"
    if re.search(r"--input\s", command):
        return "input-file"
    if re.search(r"(?:--raw-field|--field|-f|-F)\s+body=@", command):
        return "field-at-file"
    if re.search(r"(?:--raw-field|--field|-f|-F)\s+body=", command):
        return "field-inline"
    if re.search(r"<<'?EOF", command):
        return "heredoc"
    if re.search(r"--body\s", command):
        return "body-inline"
    return "other"


def _signature(command: str) -> tuple[str, ...]:
    """Structural axes that have historically broken command parsers.

    Keeping at least one exemplar per signature is what stops the per-form cap
    from discarding the rare shape a hook actually mishandles.
    """
    return (
        _classify(command),
        "multiline" if "\n" in command else "oneline",
        "substitution" if re.search(r"\w+=\$\(|(?<!\w)\$\(", command) else "direct",
        "quoted-path" if re.search(r"(?:--body-file|--input|body=@)\s*['\"]", command) else "bare",
        "envvar" if re.search(r"\$[A-Z_]{2,}", command) else "literal",
        "tilde" if re.search(r"(?:--body-file|--input|body=@)\s*~", command) else "abs",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=_default_transcript_root())
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--max-per-form", type=int, default=4, help="max exemplars per SHAPE SIGNATURE"
    )
    parser.add_argument(
        "--project",
        default="noorinalabs",
        help="restrict to transcript dirs containing this substring",
    )
    args = parser.parse_args()

    if not args.root.exists():
        print(f"transcript root not found: {args.root}", file=sys.stderr)
        return 1

    commands = harvest(args.root, args.project)
    if not commands:
        # A silent zero here would write an empty corpus and every replay test
        # would pass vacuously. Fail loudly instead.
        print(
            f"NO comment-creating commands found under {args.root}. "
            "Refusing to write an empty corpus — a replay suite over zero "
            "invocations proves nothing.",
            file=sys.stderr,
        )
        return 1

    # Cap per SHAPE SIGNATURE, not per form. A plain per-form cap taking the
    # shortest N silently drops rare shapes — and a rare shape is exactly the
    # one a hook fails on. (`URL=$(gh api -X POST ...)` was dropped that way,
    # and its absence read as "0 unrecognized".) Signature = form × the
    # structural axes that have historically broken parsers.
    #
    # Within a signature, shortest-first: it drops multi-kilobyte heredoc
    # REVIEW BODIES while keeping the invocation SHAPE, which is what this
    # corpus exists to exercise. Body content is covered by the verbatim
    # `real_verdict_*.txt` fixtures instead.
    by_signature: dict[tuple[str, ...], list[str]] = {}
    for command in commands:
        by_signature.setdefault(_signature(command), []).append(command)

    selected: list[tuple[str, str]] = []
    for signature, cmds in sorted(by_signature.items()):
        for command in sorted(cmds, key=lambda c: (len(c), c))[: args.max_per_form]:
            selected.append((signature[0], command))

    by_form: dict[str, list[str]] = {}
    for command in commands:
        by_form.setdefault(_classify(command), []).append(command)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w") as handle:
        for form, command in selected:
            record = {"tool_name": "Bash", "form": form, "command": command}
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"wrote {len(selected)} of {len(commands)} harvested invocations to {args.out}")
    for form, cmds in sorted(by_form.items(), key=lambda kv: -len(kv[1])):
        kept = min(len(cmds), args.max_per_form)
        print(f"  {form:<14} kept {kept:>3} of {len(cmds)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
