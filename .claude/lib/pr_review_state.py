#!/usr/bin/env python3
"""Deterministic PR review-state query over the merge gate's own logic (#707).

`validate_pr_review.py` (Hook 4) is the canonical authority on whether a PR
satisfies the 2-reviewer / TechDebt / wave-bootstrap-exception requirements
before `gh pr merge`. But that authority only runs AT merge time, as a
PreToolUse block. There was no way to ASK the same question ahead of time:

  - before spawning reviewers — is this PR already reviewed, and by whom?
  - before `gh pr merge`   — will the gate pass, or who is missing TechDebt?

This CLI answers that question by REUSING the hook's functions verbatim —
`get_pr_data`, `extract_branch_author_lastname`, `get_latest_content_commit`,
`partition_formal_reviewers`, `check_comment_reviews`, `_load_roster_names`,
and `is_single_reviewer_exception`. It deliberately does NOT reimplement the
charter-comment parsing: a fork would silently drift from the gate, and that
drift is the exact failure #707 exists to prevent. The PASS/FAIL verdict
computed here mirrors `validate_pr_review.check()` step for step (T_content
verdict staleness, formal + roster-filtered comment reviewers, the wave-merge
head-ref sentinel, the single-reviewer exception, and the missing-TechDebt
block).

Reusing the gate's functions is necessary but NOT sufficient for parity — the
ARGUMENTS matter as much as the callee. #1046: this driver called
`check_comment_reviews` without the `content_ts` keyword, so `T_content` was
never computed, `stale_verdicts` stayed empty, and the tool reported PASS on
approvals the gate would reject as stale (observed live on main#1040). When
adding a parameter to a shared gate function, audit THIS file's call sites —
`.claude/lib/tests/test_pr_review_state.py::ContentStalenessTests` is the
regression guard and is mutation-verified against exactly that omission.

Usage:
    python3 .claude/lib/pr_review_state.py <pr_number> --repo <owner/repo>
    python3 .claude/lib/pr_review_state.py <pr_number> --repo <owner/repo> --json

Exit codes:
    0 — the merge gate would PASS (>=2 distinct CURRENT Approved reviewers, or
        exactly one with the wave-bootstrap exception, and no verdict missing
        TechDebt)
    1 — the merge gate would BLOCK (too few current reviewers, or a verdict
        missing the TechDebt line)
    2 — review state could not be determined (PR fetch failed, the PR's commit
        list could not be fetched so no verdict's freshness is knowable, or a
        named child repo's roster could not be resolved — each mirrors a hook
        hard-block)
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

# Reuse the merge gate's canonical logic. The hook lives at
# .claude/hooks/validate_pr_review.py; this driver lives at .claude/lib/. Put
# the hooks dir on sys.path and import the gate functions directly (same
# reader/writer-share-one-module pattern annunaki_parse.py uses for
# annunaki_log). There is intentionally NO local fallback copy: a vendored fork
# of check_comment_reviews would drift from the gate, which is the whole bug
# #707 closes. If the import fails the tool should fail loudly, not guess.
_HOOKS_DIR = Path(__file__).resolve().parent.parent / "hooks"
sys.path.insert(0, str(_HOOKS_DIR))

import validate_pr_review as gate  # noqa: E402

# The two-distinct-reviewer threshold the gate enforces (charter line 36).
REVIEW_THRESHOLD = 2


@dataclasses.dataclass
class ReviewState:
    """Computed review state for a single PR — the gate's verdict, surfaced."""

    pr_number: str
    repo: str | None
    head_ref: str
    branch_author_lastname: str | None
    # Distinct Approved reviewers (full names, lowercased — the gate's dedup key).
    formal_reviewers: list[str]
    comment_reviewers: list[str]  # roster-valid comment-based Approved reviewers
    non_roster_requestors: list[str]  # Approved Requestors filtered out as non-roster
    distinct_reviewer_count: int  # formal | roster comment, the gate's count
    wave_bootstrap_exception: bool
    reviews_missing_tech_debt: list[str]
    tech_debt_issue_numbers: list[str]
    # Content binding (#950/#1046). `content_sha` / `content_ts` describe
    # T_content — the branch's latest NON-MERGE commit, the line a verdict must
    # sit at or after to count. Empty/None means the PR has no non-merge commits,
    # so nothing can be stale against it.
    content_sha: str = ""
    content_ts: str | None = None
    # Verdicts EXCLUDED as stale — dicts of reviewer/verdict/created_at/source.
    # Kept as plain dicts so `dataclasses.asdict` serializes them for --json.
    # These are already subtracted from `distinct_reviewer_count`; they are
    # carried so the report can NAME them. A stale verdict that is silently
    # subtracted reads to an operator as a broken tool (#950 diagnostic lesson).
    stale_verdicts: list[dict] = dataclasses.field(default_factory=list)

    def passes(self) -> bool:
        """True iff `validate_pr_review` would ALLOW the merge.

        Mirrors `check()`: pass when there are >=2 distinct CURRENT reviewers,
        OR exactly one reviewer who qualifies for the wave-bootstrap single-
        reviewer exception — AND no verdict is missing its TechDebt line.

        Stale verdicts (#950) are already excluded from
        `distinct_reviewer_count` upstream in `compute_review_state`, exactly as
        the gate excludes them, so this method needs no separate staleness term.
        """
        if self.reviews_missing_tech_debt:
            return False
        if self.distinct_reviewer_count >= REVIEW_THRESHOLD:
            return True
        return self.distinct_reviewer_count == 1 and self.wave_bootstrap_exception


class ReviewStateError(Exception):
    """Review state could not be determined (maps to CLI exit code 2)."""


def compute_review_state(pr_number: str, repo: str | None = None) -> ReviewState:
    """Compute a PR's review state by replaying the merge gate's own logic.

    Reuses `gate.get_pr_data`, `gate.extract_branch_author_lastname`,
    `gate.get_latest_content_commit`, `gate.partition_formal_reviewers`,
    `gate.check_comment_reviews`, `gate._load_roster_names`, and
    `gate.is_single_reviewer_exception`, forwarding `content_ts` to every
    staleness-aware call so this driver and Hook 4 cannot drift (#1046).

    Raises `ReviewStateError` when the PR cannot be fetched, the PR's commit
    list cannot be fetched (T_content unknown ⇒ no verdict's freshness is
    knowable), or a named child repo's roster cannot be resolved — the
    determinate-failure cases the gate hard-blocks on (exit code 2), distinct
    from a gate FAIL (exit code 1).
    """
    # An unresolvable `--repo` is deterministic, not transient, so name it
    # specifically instead of sending the operator to re-check `gh auth status`
    # (#981). Uses the gate's own classifier so the two surfaces give the same
    # diagnosis for the same input.
    defect = gate.repo_argument_defect(repo)
    if defect is not None:
        raise ReviewStateError(
            f"cannot determine the target repository for PR #{pr_number}: "
            f"{gate.describe_repo_defect(repo, defect)}\n"
            "Pass a literal --repo OWNER/NAME."
        )

    pr_data = gate.get_pr_data(pr_number, repo=repo)
    if pr_data is None:
        raise ReviewStateError(
            f"could not fetch PR #{pr_number}"
            + (f" in {repo}" if repo else "")
            + " — check the PR number, --repo value, and `gh auth status`."
        )

    author = pr_data["author"]
    reviews = pr_data["reviews"]
    head_ref = pr_data["headRefName"]
    number = pr_data["number"]
    labels = pr_data["labels"]

    # Content binding (#950), mirroring check(): establish T_content — the
    # committer timestamp of the branch's latest NON-MERGE commit — BEFORE
    # counting any verdict. A commit-fetch failure means NO verdict's freshness
    # can be established, so it is a determinate failure (exit 2), NOT a
    # fallback to `content_ts=None`. Defaulting to None here would count every
    # verdict regardless of age — reinstating precisely the #1046 fail-open this
    # function is being fixed for.
    try:
        latest_content = gate.get_latest_content_commit(number, repo=repo)
    except gate.CommitFetchError as exc:
        raise ReviewStateError(
            f"could not fetch the commit list for PR #{number}"
            + (f" in {repo}" if repo else "")
            + f": {exc}\nWithout it there is no T_content, so no verdict's freshness is "
            "knowable and the gate's own verdict cannot be replayed. Hook 4 hard-blocks "
            "here rather than counting verdicts of unknown freshness (#950)."
        ) from exc

    content_ts = latest_content[1] if latest_content else None
    content_sha = latest_content[0] if latest_content else ""

    # Formal GitHub reviews from non-authors (not roster-filtered — these are
    # platform-authenticated identities, exactly as the gate treats them), bound
    # to T_content by the gate's own shared helper rather than a local copy.
    formal_reviewers, stale_formal = gate.partition_formal_reviewers(reviews, author, content_ts)

    # Resolve head ref -> branch-author lastname, then fetch comment reviews.
    # Mirrors check(): a normal feature branch yields a lastname; a wave-merge
    # head (deployments/phase-N/wave-M) has no implementer author, so the gate
    # passes an empty sentinel that admits any non-empty reviewer. `content_ts`
    # MUST be forwarded on both call sites — omitting it silently disables
    # staleness filtering and reports PASS on stale approvals (#1046).
    comment_result = gate.CommentReviewResult()
    branch_author_lastname = None
    if head_ref:
        branch_author_lastname = gate.extract_branch_author_lastname(head_ref)
        if branch_author_lastname:
            comment_result = gate.check_comment_reviews(
                number, branch_author_lastname, repo=repo, content_ts=content_ts
            )
        elif head_ref.startswith("deployments/") and "/wave-" in head_ref:
            comment_result = gate.check_comment_reviews(
                number, "", repo=repo, content_ts=content_ts
            )

    # An INCOMPLETE comment scan is a determinate failure, not a zero-approval
    # result (#981). Mirrors the gate's hard-block: reporting an unreadable
    # comment thread as an empty one would make this driver answer FAIL (exit 1,
    # "this PR lacks approvals") when the honest answer is "could not determine"
    # (exit 2) — and would drift from Hook 4, which is what #1046 was.
    if comment_result.undetermined:
        raise ReviewStateError(
            f"comment reviews for PR #{number} could not be read: "
            f"{comment_result.undetermined}\nWithout them the gate's verdict cannot be "
            "replayed, so this is a determinate failure rather than a zero-approval result."
        )

    # Filter comment-based Approved reviewers against the roster (gate #498):
    # only real roster personas count toward the threshold. A missing child
    # roster is a hard-block in the gate, surfaced here as ReviewStateError.
    try:
        roster_names = gate._load_roster_names(repo=repo)
    except gate.RosterResolutionError as exc:
        raise ReviewStateError(
            f"child-repo roster could not be resolved for --repo '{repo}': {exc}"
        ) from exc

    non_roster = {r for r in comment_result.reviewers if r not in roster_names}
    roster_comment_reviewers = comment_result.reviewers - non_roster

    distinct = formal_reviewers | roster_comment_reviewers

    wave_bootstrap = gate.is_single_reviewer_exception(labels, distinct, repo=repo)

    # Stale verdicts from BOTH sources, in the gate's own order (comment, then
    # formal), flattened to dicts so the dataclass stays JSON-serializable.
    stale_verdicts = [
        {
            "reviewer": sv.reviewer,
            "verdict": sv.verdict,
            "created_at": sv.created_at,
            "source": source,
        }
        for source, verdicts in (
            ("comment", comment_result.stale_verdicts),
            ("formal", stale_formal),
        )
        for sv in verdicts
    ]

    return ReviewState(
        pr_number=str(number),
        repo=repo,
        head_ref=head_ref,
        branch_author_lastname=branch_author_lastname,
        formal_reviewers=sorted(formal_reviewers),
        comment_reviewers=sorted(roster_comment_reviewers),
        non_roster_requestors=sorted(non_roster),
        distinct_reviewer_count=len(distinct),
        wave_bootstrap_exception=wave_bootstrap,
        reviews_missing_tech_debt=list(comment_result.reviews_missing_tech_debt),
        tech_debt_issue_numbers=list(comment_result.tech_debt_issue_numbers),
        content_sha=content_sha,
        content_ts=content_ts.isoformat() if content_ts else None,
        stale_verdicts=stale_verdicts,
    )


def _render_text(state: ReviewState) -> str:
    """Human-readable review-state report."""
    lines: list[str] = []
    pr_label = f"PR #{state.pr_number}" + (f" ({state.repo})" if state.repo else "")
    verdict = "PASS" if state.passes() else "BLOCK"
    lines.append(f"{pr_label} — merge gate would {verdict}")
    lines.append(f"  head ref: {state.head_ref or '(unknown)'}")
    lastname = state.branch_author_lastname or "(none — wave-merge / unmatched)"
    lines.append(f"  branch-author lastname: {lastname}")

    approved = state.comment_reviewers + state.formal_reviewers
    lines.append(
        f"  distinct Approved reviewers: {state.distinct_reviewer_count}/{REVIEW_THRESHOLD}"
        f" required — {', '.join(approved) if approved else '(none)'}"
    )
    if state.comment_reviewers:
        lines.append(f"    comment-based: {', '.join(state.comment_reviewers)}")
    if state.formal_reviewers:
        lines.append(f"    formal GitHub: {', '.join(state.formal_reviewers)}")
    if state.non_roster_requestors:
        lines.append(
            "    excluded (non-roster Approved Requestors): "
            + ", ".join(state.non_roster_requestors)
        )

    # Content binding (#950/#1046). Name every stale verdict: an operator seeing
    # a low count on a PR with visible `Approved` comments will conclude the tool
    # is broken unless it says WHICH verdict went stale and WHAT invalidated it.
    content_line = (
        f"  content commit (T_content): {state.content_sha or '(none — no non-merge commits)'}"
    )
    if state.content_ts:
        content_line += f" @ {state.content_ts}"
    lines.append(content_line)

    if state.stale_verdicts:
        lines.append(f"  STALE verdicts EXCLUDED from the count: {len(state.stale_verdicts)}")
        for sv in sorted(state.stale_verdicts, key=lambda v: v.get("created_at") or ""):
            cast_at = sv.get("created_at") or "<no timestamp>"
            lines.append(
                f"    {sv.get('reviewer', '?')} — {sv.get('verdict', '?')}"
                f" [{sv.get('source', '?')}] cast {cast_at}"
                f" x STALE (before {state.content_sha or 'T_content'})"
            )
        lines.append(
            "    A verdict cast BEFORE the branch's latest non-merge commit reviewed code "
            "that has since been rewritten, so it does not count. Branch updates from "
            "`main` (merge commits) do NOT invalidate a verdict; only new authored "
            "commits do. Fix: ask the reviewer to re-review at the current head."
        )
    else:
        lines.append("  stale verdicts: none")

    lines.append(
        "  wave-bootstrap single-reviewer exception: "
        + ("APPLIES" if state.wave_bootstrap_exception else "no")
    )

    if state.reviews_missing_tech_debt:
        lines.append(
            "  verdicts MISSING the TechDebt line: " + ", ".join(state.reviews_missing_tech_debt)
        )
    else:
        lines.append("  verdicts missing TechDebt line: none")

    if state.tech_debt_issue_numbers:
        lines.append(
            "  TechDebt issue numbers: " + ", ".join(f"#{n}" for n in state.tech_debt_issue_numbers)
        )
    else:
        lines.append("  TechDebt issue numbers: none")

    return "\n".join(lines)


def _render_json(state: ReviewState) -> str:
    # `asdict` carries content_sha / content_ts / stale_verdicts through, so the
    # JSON consumer sees the staleness evidence, not just its arithmetic effect.
    payload = dataclasses.asdict(state)
    payload["passes"] = state.passes()
    payload["threshold"] = REVIEW_THRESHOLD
    payload["stale_verdict_count"] = len(state.stale_verdicts)
    return json.dumps(payload, indent=2, sort_keys=True)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pr_review_state",
        description=(
            "Query a PR's review state using the merge gate's own logic "
            "(validate_pr_review.check_comment_reviews). Exit 0 if the gate "
            "would pass, 1 if it would block, 2 if undeterminable."
        ),
    )
    p.add_argument("pr_number", help="PR number to query")
    p.add_argument(
        "--repo",
        default=None,
        help="target repo as OWNER/NAME (e.g. noorinalabs/noorinalabs-main); "
        "default uses the cwd-resolved repo",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="emit machine-readable JSON instead of the text report",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        state = compute_review_state(args.pr_number, repo=args.repo)
    except ReviewStateError as exc:
        print(f"pr_review_state: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(_render_json(state))
    else:
        print(_render_text(state))
    return 0 if state.passes() else 1


if __name__ == "__main__":
    raise SystemExit(main())
