#!/usr/bin/env python3
"""Classify the /wave-scope Step 8.5 tech-debt-intake gate verdict (#1374).

`/wave-scope` Step 8.5 sizes the mandatory tech-debt intake as
``TARGET = ceil(0.20 * BASE)``, where ``BASE`` is the count of in-scope
issues that are NOT `tech-debt` and NOT `meta-issue` (the feature/bug/
security content the owner just kept for the wave), and ``POOL`` is the
un-scheduled `tech-debt`-labeled backlog available to top the wave up with.

Before this module existed, Step 3 ("Select + confirm") rendered the
verdict inline with a two-way branch:

    POOL <= TARGET -> "TD intake: <POOL> of <POOL> available — debt
                       backlog below the 20% target (healthy)"
    POOL >  TARGET -> surface the top TARGET candidates

That branch is silently wrong on a TD-saturated wave. When the wave's
in-scope content is ITSELF all tech-debt, BASE collapses to 0, so
TARGET is 0 too. If POOL also happens to be 0 at that moment (e.g. every
candidate the pool query would otherwise surface is already carrying a
wave label), `POOL <= TARGET` (0 <= 0) is true, and the gate prints
`TD intake: 0 of 0 available — debt backlog below the 20% target
(healthy)` — even though the *un-scheduled* debt backlog elsewhere may be
in the hundreds. "The ratio could not be measured" renders identically to
"the ratio was measured and is fine". That is the failure shape #1374
(and its sibling #1254) names: a mechanism reporting success/benign
inaction while incapable of the outcome it describes.

This module is the single source of truth for the verdict, replacing the
inline two-way branch with a three-way classification:

  1. ``BASE > 0``, ``POOL <= TARGET``  -> ``healthy``        (genuinely OK)
  2. ``BASE > 0``, ``POOL >  TARGET``  -> ``applies``        (intake fires)
  3. ``BASE == 0``                     -> ``not_applicable`` (ratio undefined
                                           — NEVER rendered as healthy)

State 3 is the one #1374 measured as having no representation: the ratio
is undefined when there is nothing to measure it against, and printing
"healthy" for an undefined ratio is indistinguishable from a genuinely
clean bill of health to a reader who only sees the one-line verdict.
"""

from __future__ import annotations

import argparse
import sys
from typing import TypedDict


class TdIntakeVerdict(TypedDict):
    state: str  # "healthy" | "applies" | "not_applicable"
    base: int
    target: int
    pool: int
    line: str


def compute_target(base: int) -> int:
    """``ceil(0.20 * base)`` — mirrors the SKILL.md Step 1 bash arithmetic."""
    if base < 0:
        raise ValueError(f"base must be >= 0, got {base}")
    return (base * 20 + 99) // 100


def td_intake_verdict(base: int, pool: int) -> TdIntakeVerdict:
    """Classify the Step 8.5 gate's state for a given ``base``/``pool``.

    ``base`` is the post-Step-7 in-scope feature/bug/security count (NOT
    `tech-debt`, NOT `meta-issue`). ``pool`` is the un-scheduled `tech-debt`
    candidate pool size. Returns the verdict state plus the exact line
    `/wave-scope` should print — callers must not reconstruct the string
    themselves, so there is exactly one place this renders (#1374).
    """
    if base < 0 or pool < 0:
        raise ValueError(f"base and pool must be >= 0, got base={base} pool={pool}")
    target = compute_target(base)
    if base == 0:
        return {
            "state": "not_applicable",
            "base": base,
            "target": target,
            "pool": pool,
            "line": (
                "TD intake: not applicable (TD-saturated wave, BASE=0) — "
                "the 20%-of-feature-scope ratio is undefined when there is no "
                f"non-debt content to measure against. {pool} un-scheduled "
                "tech-debt item(s) are pending in the candidate pool; this is "
                "NOT a clean bill of health — defer to the phase plan's "
                "declared TD posture."
            ),
        }
    if pool <= target:
        return {
            "state": "healthy",
            "base": base,
            "target": target,
            "pool": pool,
            "line": (
                f"TD intake: {pool} of {pool} available — debt backlog below "
                "the 20% target (healthy)"
            ),
        }
    return {
        "state": "applies",
        "base": base,
        "target": target,
        "pool": pool,
        "line": (
            f"TD intake: surfacing top {target} of {pool} un-scheduled "
            "tech-debt candidates for owner selection (#1374 § state 2)"
        ),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Classify the /wave-scope Step 8.5 tech-debt intake gate verdict."
    )
    parser.add_argument("--base", type=int, required=True, help="in-scope non-TD, non-meta count")
    parser.add_argument("--pool", type=int, required=True, help="un-scheduled tech-debt pool size")
    return parser


def main(argv: list[str]) -> int:
    args = _build_parser().parse_args(argv[1:])
    result = td_intake_verdict(args.base, args.pool)
    print(result["line"])
    print(
        f"[state={result['state']} base={result['base']} "
        f"target={result['target']} pool={result['pool']}]"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
