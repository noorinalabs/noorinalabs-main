#!/usr/bin/env python3
"""State-based kickoff-comment reconciliation for `/wave-kickoff` (main#1141).

Why a sweep exists at all
=========================

`post_wave_kickoff_comment.py` posts the charter-format kickoff comment as a
PostToolUse reaction to the label-apply COMMAND. That is the right primary
mechanism (it fires at the moment of the apply), but it inherits a structural
limit: it can only act on what it can parse out of a shell string. main#1141
found two ordinary shapes it could not — a `timeout 45 gh …` prefix and a
`for … ; do gh issue edit … ; done` loop — and the consequence was silent in
the unsafe direction: during `/wave-scope 10 29` on 2026-07-27, **14 issues
were labeled and zero kickoff comments were posted**, undetected until an
unrelated audit. The parser side of that is fixed (`_shell_parse.
strip_command_prefixes`), but the loop-VARIABLE shape

    for n in 1114 1116; do gh issue edit "$n" --add-label "wave-29"; done

is genuinely unfixable at the command layer: the issue number never appears in
the string. No parser closes that class.

This module closes it from the other side. It reads the state that actually
landed — the wave label on the issue — and posts a kickoff comment to every
in-scope issue that carries the label but has no kickoff comment for that wave.
It is the same discipline as main#981/#985 ("parsing a command string is weaker
evidence than observing the resulting state") applied to the kickoff surface.

Safety properties
=================

* **Idempotent WHEN THE COMMENT FETCH SUCCEEDS.** Every candidate is screened
  through the hook's own `kickoff_comment_state(repo, issue, wave_num=…)`, so
  re-running the sweep posts nothing the second time. That check is
  wave-specific (#547), so a carry-forward issue's PRIOR-wave kickoff does not
  suppress this wave's.

  The qualifier is load-bearing (main#1145). If the fetch itself fails, the
  probe returns `unknown`, not `absent`, and the candidate resolves to
  `skip_fetch_unknown` — no post, in either mode. Without that state a
  sustained fetch failure appended a duplicate on every `--apply` pass and
  reported `posted`, so the sweep never reached the zero-`would_post` that
  Step 7b defines as done: an operator following the documented procedure into
  an unbounded loop. A fetch is likeliest to fail during a GitHub incident,
  which is exactly when kickoff gets re-run.
* **One renderer.** The comment body comes from the hook's
  `render_kickoff_comment` with the hook's `read_merge_model` — the sweep can
  never drift from the hook's template or emit a different branch base.
* **Dry-run by default.** Posting a comment is an outward-facing, effectively
  irreversible action across up to ~20 issues, so `--apply` is required to
  actually post. Without it the sweep prints exactly what it WOULD post.
* **Open issues only.** A closed issue is not kicked off; posting there is
  noise.

CLI
===

  kickoff_sweep.py <phase> <wave> [--status PATH] [--repo NAME ...]
                                  [--apply] [--json]

Exit codes: 0 = the sweep saw every candidate and did its job; 1 = it did NOT
(a post failed, or an issue could not be probed at all). Step 7b keys
completion on exit 0, so an un-probeable issue blocks completion exactly like a
failed post — the operator is never handed a quiet zero that means "I could not
look". Mirrors `wave_merge_model.py reachability`.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_LIB_DIR))
import gh  # noqa: E402
import wave_state  # noqa: E402

_REPO_ROOT = wave_state.REPO_ROOT
_HOOKS_DIR = _REPO_ROOT / ".claude" / "hooks"
_DEFAULT_STATUS = wave_state.DEFAULT_STATUS_PATH

# The kickoff hook is the single source of truth for the comment body, the
# assignment-row lookup, the merge-model read and the idempotency check. The
# sweep is a different TRIGGER for the same logic, never a second copy of it
# (the `pr_ci_state.py` / `pr_review_state.py` precedent for lib importing a
# hook module).
sys.path.insert(0, str(_HOOKS_DIR))
from post_wave_kickoff_comment import (  # noqa: E402
    KICKOFF_PRESENT,
    KICKOFF_UNKNOWN,
    _gh_post_comment,
    _phase_from_status,
    _write_fresh_body_file,
    find_assignment_row,
    kickoff_comment_state,
    read_merge_model,
    render_kickoff_comment,
)

# Actions a candidate issue can resolve to. `posted` / `would_post` are the
# reconciliation outcome; the rest are the reasons a candidate was skipped and
# exist so a dry run explains itself rather than printing an empty list.
POSTED = "posted"
WOULD_POST = "would_post"
SKIP_IDEMPOTENT = "skip_idempotent"
SKIP_META_ISSUE = "skip_meta_issue"
SKIP_NO_ROW = "skip_no_row"
POST_FAILED = "post_failed"
# main#1145: the comment fetch failed, so we CANNOT tell whether a kickoff
# comment already exists. Never posts, in either mode.
SKIP_FETCH_UNKNOWN = "skip_fetch_unknown"

# Outcomes that mean the sweep did not finish its job. `/wave-kickoff` Step 7b
# treats a non-zero exit as "Step 7 is NOT complete" — so an un-probeable issue
# blocks completion exactly like a failed post does, rather than passing as a
# quiet zero.
_INCOMPLETE_ACTIONS = frozenset({POST_FAILED, SKIP_FETCH_UNKNOWN})


# Shared gh shim (main#1119). Stays a module-level name because it is the
# default for this module's injected `run_gh=` parameters.
_run_gh = gh.run_gh


def wave_labels(phase: str | int, wave: str | int) -> list[str]:
    """Return every label form that marks an issue as belonging to this wave.

    Both the phase-agnostic global form (`wave-29`, the owner-preferred form
    per #810) and the grandfathered legacy form (`p10-wave-29`) are swept —
    an in-flight issue labeled either way still owns work in this wave.
    """
    return [f"wave-{wave}", f"p{phase}-wave-{wave}"]


def list_labeled_issues(repo: str, labels: list[str], run_gh=None) -> list[str]:
    """Return the OPEN issue numbers in `repo` carrying any of `labels`.

    One `gh issue list` call per label (multiple `--label` flags on a single
    call are ANDed by gh, which is the opposite of what a form-union needs),
    de-duplicated and returned in ascending numeric order.

    `--limit 500` exceeds any plausible wave scope by an order of magnitude,
    but there is NO assertion that the result stayed under it: a wave that
    somehow exceeded 500 labeled issues in one repo would silently
    under-sweep. Known gap, not a guarantee — tracked by main#1145.
    """
    run_gh = run_gh or _run_gh
    seen: set[str] = set()
    for label in labels:
        raw = run_gh(
            [
                "issue",
                "list",
                "--repo",
                f"noorinalabs/{repo}",
                "--label",
                label,
                "--state",
                "open",
                "--limit",
                "500",
                "--json",
                "number",
            ]
        )
        for entry in json.loads(raw or "[]"):
            number = entry.get("number")
            if number is not None:
                seen.add(str(number))
    return sorted(seen, key=int)


def _meta_issue_number(status: dict, wave: str | int) -> str | None:
    """Return the wave meta-issue's bare number, tolerating both shapes.

    `wave_{M}_meta_issue` is written either as a bare int (`1133`) or as a
    qualified string (`"noorinalabs-main#821"`) — main#1053. Both carry the
    number as their trailing digit run.
    """
    meta = status.get(f"wave_{wave}_meta_issue")
    if meta is None:
        return None
    digits = "".join(ch for ch in str(meta) if ch.isdigit())
    return digits or None


def sweep(
    phase: str | int,
    wave: str | int,
    status: dict,
    repos: list[str],
    *,
    apply: bool = False,
    list_issues=None,
    fetch_comments=None,
    post_comment=None,
    body_writer=None,
) -> list[dict]:
    """Reconcile kickoff comments for every labeled, in-scope issue.

    Returns one result dict per candidate issue: `{repo, issue, action}` plus
    `body` for the post/would-post cases. All I/O is injectable so the whole
    decision path is unit-testable without a network call, mirroring
    `wave_merge_model.check_reachability`.

    `apply=False` (the default) resolves every posting candidate to
    `would_post` and performs NO write.
    """
    list_issues = list_issues or list_labeled_issues
    post_comment = post_comment or _gh_post_comment
    body_writer = body_writer or _write_fresh_body_file

    wave_num = int(wave)
    phase_num = _phase_from_status(status)
    if phase_num is None:
        phase_num = int(phase)
    merge_model = read_merge_model(status, wave_num)
    meta_issue = _meta_issue_number(status, wave)
    labels = wave_labels(phase, wave)

    results: list[dict] = []
    for repo in repos:
        for issue_number in list_issues(repo, labels):
            if meta_issue is not None and issue_number == meta_issue and repo == "noorinalabs-main":
                # The meta-issue gets the all-hands kickoff comment from
                # /wave-kickoff Step 8, not the per-issue template.
                results.append({"repo": repo, "issue": issue_number, "action": SKIP_META_ISSUE})
                continue

            row = find_assignment_row(status, repo, issue_number, wave_num)
            if row is None:
                # The issue carries the wave label but /wave-scope never wrote
                # it into a tier. Surfacing it is the point: that is a scope
                # bug, and it is exactly the drift a label-keyed sweep can see
                # and a command-keyed hook cannot.
                results.append({"repo": repo, "issue": issue_number, "action": SKIP_NO_ROW})
                continue

            state = kickoff_comment_state(
                repo, issue_number, wave_num=wave_num, fetch_comments=fetch_comments
            )
            if state == KICKOFF_PRESENT:
                results.append({"repo": repo, "issue": issue_number, "action": SKIP_IDEMPOTENT})
                continue
            if state == KICKOFF_UNKNOWN:
                # main#1145 fail-open guard. We could not read the comments, so
                # "already posted?" is unanswered — and unanswered is not "no".
                # Posting here is what made a sustained fetch failure append a
                # duplicate on every `--apply` pass while reporting `posted`,
                # so the sweep never converged to the zero-`would_post` that
                # Step 7b defines as done. Report the uncertainty and post
                # nothing; the operator re-runs once the fetch is healthy.
                results.append({"repo": repo, "issue": issue_number, "action": SKIP_FETCH_UNKNOWN})
                continue

            body = render_kickoff_comment(row, wave_num, phase_num, repo, merge_model=merge_model)
            if not apply:
                results.append(
                    {"repo": repo, "issue": issue_number, "action": WOULD_POST, "body": body}
                )
                continue

            body_path = body_writer(body, repo, issue_number)
            ok = post_comment(repo, issue_number, body_path)
            results.append(
                {
                    "repo": repo,
                    "issue": issue_number,
                    "action": POSTED if ok else POST_FAILED,
                    "body": body,
                }
            )
    return results


def format_report(wave: str | int, results: list[dict], *, apply: bool) -> str:
    """Human-readable sweep report — one line per candidate plus a summary.

    The `skip_fetch_unknown` count is called out separately rather than left to
    be spotted in the summary line (main#1145): "nothing to do" and "could not
    tell" must not look alike to an operator deciding whether Step 7 is done.
    """
    counts: dict[str, int] = {}
    for r in results:
        counts[r["action"]] = counts.get(r["action"], 0) + 1

    mode = "APPLY" if apply else "DRY RUN (re-run with --apply to post)"
    lines = [f"Kickoff sweep — wave {wave} [{mode}]"]
    for r in results:
        lines.append(f"  [{r['action']}] {r['repo']}#{r['issue']}")
    if not results:
        lines.append(f"  (no open issue carries a wave-{wave} label in the swept repos)")
    summary = ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "nothing to reconcile"
    lines.append(f"Summary: {summary}")

    unknown = counts.get(SKIP_FETCH_UNKNOWN, 0)
    if unknown:
        lines.append(
            f"INCOMPLETE: {unknown} issue(s) could not be checked — the comment fetch failed, "
            "so it is unknown whether they already have a kickoff comment. NOTHING was posted "
            "for them. Do NOT treat this sweep as complete; re-run once gh is healthy (#1145)."
        )
    if counts.get(POST_FAILED):
        lines.append(
            f"INCOMPLETE: {counts[POST_FAILED]} post(s) failed — re-run to retry (idempotent)."
        )
    return "\n".join(lines)


def _cmd_sweep(args: argparse.Namespace) -> int:
    status = json.loads(Path(args.status).read_text(encoding="utf-8"))
    repos = args.repo or status.get(f"wave_{args.wave}_repos_in_scope")
    if not repos:
        print(
            f"ERROR: no repos to sweep — wave_{args.wave}_repos_in_scope is missing from "
            f"{args.status} and no --repo was given.",
            file=sys.stderr,
        )
        return 1

    results = sweep(args.phase, args.wave, status, list(repos), apply=args.apply)
    if args.json:
        print(json.dumps({"wave": args.wave, "apply": args.apply, "results": results}, indent=2))
    else:
        print(format_report(args.wave, results, apply=args.apply))
    return 1 if any(r["action"] in _INCOMPLETE_ACTIONS for r in results) else 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", help="phase number (P)")
    parser.add_argument("wave", help="wave number (M)")
    wave_state.add_status_argument(parser)
    parser.add_argument(
        "--repo",
        action="append",
        help="repo to sweep (repeatable); defaults to wave_{M}_repos_in_scope",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually post the missing kickoff comments (default: dry run)",
    )
    parser.add_argument("--json", action="store_true", help="emit results as JSON")
    return parser


def main(argv: list[str]) -> int:
    args = _build_parser().parse_args(argv)
    try:
        return _cmd_sweep(args)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: could not read status file {args.status}: {exc}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        print(
            f"ERROR: gh call failed (exit {exc.returncode}): {' '.join(exc.cmd)}\n{exc.stderr}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
