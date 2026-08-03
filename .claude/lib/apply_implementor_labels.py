#!/usr/bin/env python3
"""Apply implementor (assignee) persona labels to issues from their merged PRs.

The `FIRSTNAME_LASTNAME` label (charter `issues.md` § Assignment) is both the
assignment tag and the durable record of *who implemented* an issue. This tool
(re)derives it from each merged PR and applies it idempotently — the enforcement
that keeps the convention from lapsing again (reinstated 2026-06-30, main#906-era
backfill of 949 issues across 8 repos).

Inference (in priority order):
  1. Branch prefix `{FirstInitial}.{LastName}/{NNNN}-…` -> persona label that
     already exists in that repo. High confidence: a branch key that matches an
     existing repo persona label means the convention was followed.
  2. When the branch key has no matching repo label, the COMMIT AUTHOR identity
     of the PR is authoritative (per-commit `-c user.name`, charter `commits.md`).
     Branch prefix and commit author can disagree (stale branch / takeover, see
     memory `feedback_throttle_takeover`); the commit author wins.
New labels are created in `FIRSTNAME_LASTNAME` form, ASCII-folded so accented
commit-author names reconcile to the established ASCII canonical (an
acute-accented surname folds to its plain-ASCII label, e.g. `MENDEZ-RIOS`).
Existing labels in any form (incl. legacy `First Last`) are reused, never
duplicated.

Apply uses the REST labels endpoint (core budget), not `gh issue edit` (GraphQL),
because a few hundred mutations exhaust the 5000-pt/hr GraphQL primary limit.

Usage:
  python3 .claude/lib/apply_implementor_labels.py                 # dry-run, all repos
  python3 .claude/lib/apply_implementor_labels.py --repo noorinalabs-deploy
  python3 .claude/lib/apply_implementor_labels.py --apply         # actually apply
  python3 .claude/lib/apply_implementor_labels.py --repo R --apply
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
import unicodedata
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from org_repos import ALL_REPOS as _ALL_REPOS_TUPLE

# main#1118 / audit G6: sourced from org_repos.py, the org repo-list SSOT.
# Kept as a list (not the imported tuple) since callers mutate/slice it.
ALL_REPOS = list(_ALL_REPOS_TUPLE)
PERSONA_RE = re.compile(r"^[A-Z][A-Z.-]*_[A-Z][A-Z.-]*$")
PERSONA_SPACE_RE = re.compile(r"^[A-Z][a-z][A-Za-z'’-]* [A-Z][A-Za-z'’-]+$")
BRANCH_RE = re.compile(r"^([A-Za-z])\.([A-Za-z][A-Za-z'-]*)/0*([0-9]+)-")
NEW_LABEL_COLOR = "bfd4f2"


def ascii_fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def gh_json(args: list[str]) -> Any:
    out = subprocess.run(["gh"] + args, capture_output=True, text=True)
    if out.returncode != 0:
        return None
    try:
        return json.loads(out.stdout)
    except Exception:
        return None


def label_key(label: str) -> str:
    first, last = label.split("_", 1) if "_" in label else label.split(" ", 1)
    return first[0].lower() + "." + last.lower()


def name_key(name: str) -> str | None:
    p = name.split()
    return None if len(p) < 2 else p[0][0].lower() + "." + p[-1].lower()


def name_to_label(name: str) -> str:
    p = name.split()
    first, last = p[0], ("-".join(p[1:]) if len(p) > 2 else p[-1])
    return ascii_fold((first + "_" + last).upper())


def full_name_of(label: str) -> str:
    first, last = label.split("_", 1)

    def tc(tok: str) -> str:
        return "-".join(w.capitalize() for w in tok.split("-"))

    return tc(first) + " " + tc(last)


def is_persona(label: str) -> bool:
    return bool(PERSONA_RE.match(label) or PERSONA_SPACE_RE.match(label))


def build_global_canon(repos: list[str]) -> dict[str, str]:
    """Map persona key -> canonical ASCII underscore label across all repos."""
    canon: dict[str, str] = {}
    for r in repos:
        labels = (
            gh_json(
                ["label", "list", "--repo", f"noorinalabs/{r}", "--limit", "300", "--json", "name"]
            )
            or []
        )
        for lab in labels:
            name = lab["name"]
            if is_persona(name):
                canon.setdefault(label_key(name), ascii_fold(name.replace(" ", "_").upper()))
    return canon


def plan_repo(repo: str, global_canon: dict[str, str]) -> tuple[list[tuple[int, str]], list[str]]:
    """Return (applications, labels_to_create) for one repo."""
    labels = (
        gh_json(
            ["label", "list", "--repo", f"noorinalabs/{repo}", "--limit", "300", "--json", "name"]
        )
        or []
    )
    existing = {lab["name"] for lab in labels}
    personas = {lab["name"] for lab in labels if is_persona(lab["name"])}
    keymap = {label_key(L): L for L in personas}
    issues: dict[int, set[str]] = {}
    for st in ("closed", "open"):
        for it in (
            gh_json(
                [
                    "issue",
                    "list",
                    "--repo",
                    f"noorinalabs/{repo}",
                    "--state",
                    st,
                    "--limit",
                    "3000",
                    "--json",
                    "number,labels",
                ]
            )
            or []
        ):
            issues[it["number"]] = {x["name"] for x in it.get("labels", [])}
    prs = (
        gh_json(
            [
                "pr",
                "list",
                "--repo",
                f"noorinalabs/{repo}",
                "--state",
                "merged",
                "--limit",
                "3000",
                "--json",
                "number,headRefName",
            ]
        )
        or []
    )
    apps: list[tuple[int, str]] = []
    create: set[str] = set()
    for pr in prs:
        m = BRANCH_RE.match(pr.get("headRefName") or "")
        if not m:
            continue
        bkey = (m.group(1) + "." + m.group(2)).lower()
        num = int(m.group(3))
        if num == 0 or num not in issues:
            continue
        if bkey in keymap:  # (1) branch prefix -> existing label
            label = keymap[bkey]
        else:  # (2) commit author authoritative
            commits = gh_json(
                [
                    "pr",
                    "view",
                    str(pr["number"]),
                    "--repo",
                    f"noorinalabs/{repo}",
                    "--json",
                    "commits",
                ]
            )
            authors = [
                a["name"]
                for c in (commits or {}).get("commits", [])
                for a in c.get("authors", [])
                if a.get("name") and "Claude" not in a["name"] and a["name"] != "GitHub"
            ]
            if not authors:
                continue
            chosen = (
                next((a for a in authors if name_key(a) == bkey), None)
                or (Counter(authors).most_common(1)[0][0])
            )
            akey = name_key(chosen)
            if akey is None:
                label = name_to_label(chosen)
            else:
                label = keymap.get(akey) or global_canon.get(akey) or name_to_label(chosen)
            if label not in existing:
                create.add(label)
        if label not in issues[num]:
            apps.append((num, label))
    return sorted(set(apps)), sorted(create)


def apply_label(repo: str, num: int, labels: set[str]) -> tuple[bool, str | None]:
    args = ["api", "--method", "POST", f"repos/noorinalabs/{repo}/issues/{num}/labels"]
    for L in labels:
        args += ["-f", f"labels[]={L}"]
    for attempt in range(4):
        r = subprocess.run(["gh"] + args, capture_output=True, text=True)
        if r.returncode == 0:
            return True, None
        err = r.stderr + r.stdout
        if "rate limit" in err.lower() or "secondary" in err.lower():
            time.sleep(8 * (attempt + 1))
            continue
        if attempt == 3:
            return False, err.strip()[:160]
        time.sleep(2)
    return False, "retry-exhausted"


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--repo", action="append", help="repo(s) to process (default: all 8)")
    ap.add_argument("--apply", action="store_true", help="apply (default: dry-run)")
    args = ap.parse_args()
    repos: list[str] = args.repo or ALL_REPOS

    global_canon = build_global_canon(ALL_REPOS)  # canon resolved across all repos
    grand_apps = 0
    grand_new = 0
    for repo in repos:
        apps, create = plan_repo(repo, global_canon)
        grand_apps += len(apps)
        grand_new += len(create)
        print(
            f"{repo}: {len(apps)} label-applications, {len(create)} new labels"
            + (f" -> {', '.join(create)}" if create else "")
        )
        if not args.apply:
            continue
        for L in create:
            subprocess.run(
                [
                    "gh",
                    "label",
                    "create",
                    L,
                    "--repo",
                    f"noorinalabs/{repo}",
                    "--color",
                    NEW_LABEL_COLOR,
                    "--description",
                    f"Implementor: {full_name_of(L)}",
                ],
                capture_output=True,
                text=True,
            )
        byissue: dict[int, set[str]] = defaultdict(set)
        for num, label in apps:
            byissue[num].add(label)
        ok = 0
        fails: list[tuple[int, str | None]] = []
        with ThreadPoolExecutor(max_workers=4) as ex:
            futs = {ex.submit(apply_label, repo, n, ls): n for n, ls in byissue.items()}
            for f in as_completed(futs):
                good, err = f.result()
                if good:
                    ok += 1
                else:
                    fails.append((futs[f], err))
        print(f"  applied: {ok}/{len(byissue)} issues" + (f"; FAILURES: {fails}" if fails else ""))
    mode = "APPLIED" if args.apply else "DRY-RUN (use --apply to write)"
    print(
        f"\n{mode}: {grand_apps} applications, {grand_new} new labels across {len(repos)} repo(s)"
    )


if __name__ == "__main__":
    main()
