"""Tests for the /wave-scope Step 8.5 tech-debt intake gate verdict (#1374).

Pins the failure `/wave-scope 10 30` measured 2026-08-09: a wave whose
entire in-scope set is `tech-debt`-labeled collapses BASE to 0, and the
pre-#1374 selection branch (`POOL <= TARGET -> healthy`) printed
`TD intake: 0 of 0 available — debt backlog below the 20% target
(healthy)` for that input — an undefined ratio rendering identically to a
genuinely clean one, over a 174-item real backlog.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from td_intake_gate import compute_target, td_intake_verdict  # noqa: E402


def test_all_scope_issues_tech_debt_does_not_report_healthy():
    """#1374 core acceptance case: N in-scope issues, all `tech-debt`-labeled.

    BASE (non-TD, non-meta in-scope count) is 0 for this input. The
    pre-fix branch only ever compared POOL to TARGET, so a POOL that also
    happens to be 0 (every pool candidate already wave-labeled elsewhere)
    satisfied `POOL <= TARGET` (0 <= 0) and rendered the `healthy` verdict.
    That is the exact string measured live: "TD intake: 0 of 0 available —
    debt backlog below the 20% target (healthy)".
    """
    result = td_intake_verdict(base=0, pool=0)
    assert result["state"] != "healthy", (
        f"BASE=0 must never classify as healthy — an undefined ratio is not "
        f"a measured clean bill of health. Got state={result['state']!r}."
    )
    assert "healthy" not in result["line"].lower(), (
        f"BASE=0 line must not contain the word 'healthy': {result['line']!r}"
    )
    assert result["state"] == "not_applicable"
    assert "not applicable" in result["line"].lower()


def test_base_zero_nonzero_pool_still_not_applicable_not_healthy():
    """BASE=0 with a real un-scheduled backlog (the live #1374 measurement:
    174 un-scheduled tech-debt items) must surface the pool size, not hide
    it behind a healthy-looking 0-of-0.
    """
    result = td_intake_verdict(base=0, pool=174)
    assert result["state"] == "not_applicable"
    assert "healthy" not in result["line"].lower()
    assert "174" in result["line"]


def test_base_positive_pool_below_target_is_genuinely_healthy():
    """State 1: BASE > 0, POOL <= TARGET is the one legitimate 'healthy'."""
    result = td_intake_verdict(base=10, pool=1)  # target = ceil(0.2*10) = 2
    assert result["state"] == "healthy"
    assert "healthy" in result["line"].lower()
    assert result["target"] == 2


def test_base_positive_pool_above_target_applies_intake():
    """State 2: BASE > 0, POOL > TARGET — intake fires, selects TARGET items."""
    result = td_intake_verdict(base=10, pool=5)  # target = 2
    assert result["state"] == "applies"
    assert "healthy" not in result["line"].lower()
    assert result["target"] == 2


def test_pool_equals_target_boundary_is_healthy():
    """Boundary pin (merge-gate fold-in, PR #1419): POOL == TARGET is the
    inclusive edge of the `<=` comparison at `td_intake_gate.py`'s state-1/
    state-2 branch. State 1 and state 2's existing tests use pool=1 and
    pool=5 against target=2, so neither one exercises `pool == target`
    itself — the exact boundary the branch is written to distinguish.
    Un-pinned, `if pool <= target` -> `if pool < target` survives the
    suite: an at-target wave would silently reclassify healthy -> applies.
    """
    result = td_intake_verdict(base=10, pool=2)  # target = 2, POOL == TARGET
    assert result["state"] == "healthy"


def test_pool_one_over_target_boundary_applies_intake():
    """Boundary pin (merge-gate fold-in, PR #1419): POOL == TARGET + 1 is
    the first value on the `applies` side of the same branch. Un-pinned,
    `if pool <= target` -> `if pool <= target + 1` survives the suite: an
    over-target wave would render `healthy` — #1374's exact failure shape
    one boundary over, inside the fix for that same defect class.
    """
    result = td_intake_verdict(base=10, pool=3)  # target = 2, POOL == TARGET + 1
    assert result["state"] == "applies"


def test_compute_target_matches_skill_md_ceil_arithmetic():
    """Mirrors the SKILL.md bash: `(BASE * 20 + 99) / 100` == ceil(0.20*base)."""
    assert compute_target(0) == 0
    assert compute_target(1) == 1
    assert compute_target(5) == 1
    assert compute_target(6) == 2
    assert compute_target(10) == 2
    assert compute_target(95) == 19


def test_negative_inputs_rejected():
    import pytest

    with pytest.raises(ValueError):
        td_intake_verdict(base=-1, pool=0)
    with pytest.raises(ValueError):
        td_intake_verdict(base=0, pool=-1)
