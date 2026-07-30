"""Tests for wave_status — the deterministic wave repo-iteration + counter
helper that replaces the zsh-word-split-fragile bash loops (main#688).

Verifies:
  1. `repos` emits wave_{M}_repos_in_scope one-per-line.
  2. EVERY gh call goes through subprocess.run with a LIST arg vector and
     never `shell=True` — the regression guard that makes word-splitting
     structurally impossible.
  3. merged-prs applies the wave_{M}_kicked_off_at cross-window filter (#423).
  4. Counter math reproduces the P5W4 actuals 19 / 4 / 16.
  5. `--expect N` exits 1 on a count mismatch.
  6. An empty wave yields zeros (no division-by-zero — the original crash).
  7. `--write` upserts the three canonical top-level keys through the shared
     upsert_status_keys helper, preserving the file.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock

# Helper lives at .claude/lib/wave_status.py; this test is at
# .claude/lib/tests/test_*.py. parent.parent reaches the lib root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import wave_status  # noqa: E402

_REPOS = [
    "noorinalabs-isnad-graph",
    "noorinalabs-user-service",
    "noorinalabs-deploy",
    "noorinalabs-isnad-ingest-platform",
]


def _p5w4_prs() -> list[dict]:
    """19 PRs whose top commit-author owns 3 (3/19 = 15.78 → 16%) and whose
    ChangesRequested comments sum to 4 — the canonical P5W4 shape."""
    authors = (
        ["Aino Virtanen"] * 3
        + ["Wanjiku Mwangi"] * 3
        + ["Santiago Ferreira"] * 3
        + ["Nadia Khoury"] * 3
        + ["Imelda Okoro"] * 3
        + ["Aisling Brennan"] * 3
        + ["Tariq Mansour"] * 1
    )
    assert len(authors) == 19
    cr_by_index = {0: 2, 5: 1, 10: 1}  # sums to 4
    prs = []
    for i, author in enumerate(authors):
        prs.append(
            {
                "repo": _REPOS[i % len(_REPOS)],
                "number": 100 + i,
                "sha": f"sha{i:02d}",
                "mergedAt": "2026-06-15T02:00:00Z",
                "login": "octocat",
                "commit_author": author,
                "cr": cr_by_index.get(i, 0),
            }
        )
    return prs


class _FakeGh:
    """A subprocess.run side_effect that emulates the gh calls wave_status
    makes, driven by a flat PR fixture. Records every command vector so the
    test can assert the list-args / no-shell contract."""

    def __init__(self, prs: list[dict]) -> None:
        self.prs = prs
        self.calls: list[list[str]] = []

    def __call__(self, cmd, *args, **kwargs):  # noqa: ANN001
        # Contract guard: gh is always invoked with an explicit list vector and
        # NEVER through a shell. This is the structural fix for main#688.
        assert isinstance(cmd, list), f"gh called with non-list cmd: {cmd!r}"
        assert cmd[0] == "gh"
        assert kwargs.get("shell") is not True
        self.calls.append(cmd)

        if cmd[1:3] == ["pr", "list"]:
            repo = cmd[cmd.index("--repo") + 1].removeprefix("noorinalabs/")
            listed = [
                {
                    "number": p["number"],
                    "headRefOid": p["sha"],
                    "mergedAt": p["mergedAt"],
                    "author": {"login": p["login"]},
                }
                for p in self.prs
                if p["repo"] == repo
            ]
            return SimpleNamespace(stdout=json.dumps(listed), returncode=0, stderr="")

        if cmd[1] == "api":
            path = cmd[2]
            parts = path.split("/")
            if "/commits/" in path:
                sha = parts[4]
                name = next(p["commit_author"] for p in self.prs if p["sha"] == sha)
                return SimpleNamespace(stdout=name + "\n", returncode=0, stderr="")
            if path.endswith("/comments"):
                number = int(parts[4])
                cr = next(p["cr"] for p in self.prs if p["number"] == number)
                return SimpleNamespace(stdout=f"{cr}\n", returncode=0, stderr="")

        raise AssertionError(f"unexpected gh call: {cmd!r}")


def _write_status(path: Path, *, repos: list[str], wave: str, kickoff: str | None) -> None:
    data: dict = {"current_wave": int(wave), f"wave_{wave}_repos_in_scope": repos}
    if kickoff is not None:
        data[f"wave_{wave}_kicked_off_at"] = kickoff
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


class Repos(unittest.TestCase):
    def test_emits_one_per_line(self) -> None:
        with TemporaryDirectory() as td:
            status = Path(td) / "cross-repo-status.json"
            _write_status(status, repos=_REPOS, wave="4", kickoff=None)
            self.assertEqual(wave_status.read_repos("4", status), _REPOS)

    def test_missing_key_raises(self) -> None:
        with TemporaryDirectory() as td:
            status = Path(td) / "cross-repo-status.json"
            status.write_text('{"current_wave": 4}\n', encoding="utf-8")
            with self.assertRaises(KeyError):
                wave_status.read_repos("4", status)


class MergedPrs(unittest.TestCase):
    def test_kickoff_window_filter(self) -> None:
        prs = [
            {
                "repo": _REPOS[0],
                "number": 1,
                "sha": "old",
                "mergedAt": "2026-06-14T00:00:00Z",  # before kickoff → dropped
                "login": "octocat",
                "commit_author": "Aino Virtanen",
                "cr": 0,
            },
            {
                "repo": _REPOS[0],
                "number": 2,
                "sha": "new",
                "mergedAt": "2026-06-15T03:00:00Z",  # after kickoff → kept
                "login": "octocat",
                "commit_author": "Aino Virtanen",
                "cr": 0,
            },
        ]
        with TemporaryDirectory() as td:
            status = Path(td) / "cross-repo-status.json"
            _write_status(status, repos=[_REPOS[0]], wave="4", kickoff="2026-06-15T01:52:55Z")
            with mock.patch.object(wave_status.subprocess, "run", _FakeGh(prs)):
                got = wave_status.merged_prs("5", "4", status)
        self.assertEqual([p["number"] for p in got], [2])
        self.assertEqual(got[0]["commit_author_name"], "Aino Virtanen")

    def test_no_kickoff_key_means_no_filter(self) -> None:
        prs = [
            {
                "repo": _REPOS[0],
                "number": 1,
                "sha": "a",
                "mergedAt": "2026-01-01T00:00:00Z",
                "login": "octocat",
                "commit_author": "Aino Virtanen",
                "cr": 0,
            }
        ]
        with TemporaryDirectory() as td:
            status = Path(td) / "cross-repo-status.json"
            _write_status(status, repos=[_REPOS[0]], wave="4", kickoff=None)
            with mock.patch.object(wave_status.subprocess, "run", _FakeGh(prs)):
                got = wave_status.merged_prs("5", "4", status)
        self.assertEqual(len(got), 1)


class Counters(unittest.TestCase):
    def test_reproduces_p5w4_19_4_16(self) -> None:
        prs = _p5w4_prs()
        fake = _FakeGh(prs)
        with TemporaryDirectory() as td:
            status = Path(td) / "cross-repo-status.json"
            _write_status(status, repos=_REPOS, wave="4", kickoff="2026-06-15T01:52:55Z")
            with mock.patch.object(wave_status.subprocess, "run", fake):
                counters = wave_status.compute_counters("5", "4", status)
        self.assertEqual(
            counters,
            {
                "final_pr_count": 19,
                "changes_requested_cycles": 4,
                "top_concentration_pct": 16,
            },
        )
        # Contract: every recorded gh call was a list vector starting with "gh".
        self.assertTrue(all(c[0] == "gh" and isinstance(c, list) for c in fake.calls))

    def test_changes_requested_jq_filter_double_escapes_backslash(self) -> None:
        # The comments call's --jq arg must carry a DOUBLED backslash (\\s) so
        # jq's string parser yields the regex \s. A single backslash is an
        # "invalid escape sequence" jq error — the mocked fake can't see jq, so
        # assert the literal sequence the helper builds.
        prs = _p5w4_prs()[:1]
        fake = _FakeGh(prs)
        with TemporaryDirectory() as td:
            status = Path(td) / "cross-repo-status.json"
            _write_status(status, repos=_REPOS, wave="4", kickoff=None)
            with mock.patch.object(wave_status.subprocess, "run", fake):
                wave_status.compute_counters("5", "4", status)
        comments_calls = [c for c in fake.calls if c[1] == "api" and c[2].endswith("/comments")]
        self.assertTrue(comments_calls)
        self.assertIn("\\\\s", comments_calls[0][-1])

    def test_empty_wave_is_zeros_no_div_by_zero(self) -> None:
        with TemporaryDirectory() as td:
            status = Path(td) / "cross-repo-status.json"
            _write_status(status, repos=_REPOS, wave="4", kickoff=None)
            with mock.patch.object(wave_status.subprocess, "run", _FakeGh([])):
                counters = wave_status.compute_counters("5", "4", status)
        self.assertEqual(
            counters,
            {"final_pr_count": 0, "changes_requested_cycles": 0, "top_concentration_pct": 0},
        )

    def test_expect_mismatch_exits_1(self) -> None:
        with TemporaryDirectory() as td:
            status = Path(td) / "cross-repo-status.json"
            _write_status(status, repos=_REPOS, wave="4", kickoff="2026-06-15T01:52:55Z")
            with mock.patch.object(wave_status.subprocess, "run", _FakeGh(_p5w4_prs())):
                rc = wave_status.main(
                    ["counters", "5", "4", "--status", str(status), "--expect", "20"]
                )
        self.assertEqual(rc, 1)

    def test_expect_match_exits_0(self) -> None:
        with TemporaryDirectory() as td:
            status = Path(td) / "cross-repo-status.json"
            _write_status(status, repos=_REPOS, wave="4", kickoff="2026-06-15T01:52:55Z")
            with mock.patch.object(wave_status.subprocess, "run", _FakeGh(_p5w4_prs())):
                rc = wave_status.main(
                    ["counters", "5", "4", "--status", str(status), "--expect", "19"]
                )
        self.assertEqual(rc, 0)


class Write(unittest.TestCase):
    def test_write_upserts_three_canonical_keys(self) -> None:
        with TemporaryDirectory() as td:
            status = Path(td) / "cross-repo-status.json"
            _write_status(status, repos=_REPOS, wave="4", kickoff="2026-06-15T01:52:55Z")
            with mock.patch.object(wave_status.subprocess, "run", _FakeGh(_p5w4_prs())):
                rc = wave_status.main(["counters", "5", "4", "--status", str(status), "--write"])
            self.assertEqual(rc, 0)
            data = json.loads(status.read_text())
            self.assertEqual(data["wave_4_final_pr_count"], 19)
            self.assertEqual(data["wave_4_changes_requested_cycles"], 4)
            self.assertEqual(data["wave_4_top_concentration_pct"], 16)
            # The pre-existing keys must survive the targeted upsert.
            self.assertEqual(data["wave_4_repos_in_scope"], _REPOS)


class Digest(unittest.TestCase):
    """`digest` projects the status file to the current-wave/phase slice (#987)."""

    def _status(self, **overrides: object) -> dict:
        data: dict = {
            # lifecycle pointers
            "current_phase": 9,
            "current_wave": "wave-25",
            "next_wave": "wave-26",
            "last_completed_wave": "wave-24",
            "global_wave_seq": 25,
            "wave_active": False,
            "last_updated": "2026-07-19T00:00:00Z",
            "open_prs_total": 0,
            # current + next wave keys (kept)
            "wave_25_scope": {"theme": "current"},
            "wave_25_meta_issue": "noorinalabs-main#980",
            "wave_26_meta_issue": "noorinalabs-main#983",
            # current phase key (kept)
            "phase_9_status": "ACTIVE",
            # HISTORICAL — must be dropped
            "wave_24_scope": {"theme": "old"},
            "wave_2_active": False,
            "phase_3_status": "COMPLETE",
            # blockers: live one kept, resolved audit key dropped
            "owner_decision_gated": ["deploy#999 — needs an owner call"],
            "owner_decision_gated_resolved_2026_04_29": ["main#211 — RESOLVED"],
        }
        data.update(overrides)
        return data

    def _digest(self, data: dict) -> dict:
        with TemporaryDirectory() as td:
            status = Path(td) / "cross-repo-status.json"
            status.write_text(json.dumps(data))
            return wave_status.build_digest(status)

    def test_keeps_pointers_current_and_next_wave_and_phase(self) -> None:
        d = self._digest(self._status())
        for key in wave_status._DIGEST_POINTER_KEYS:
            self.assertIn(key, d)
        self.assertIn("wave_25_scope", d)
        self.assertIn("wave_25_meta_issue", d)
        self.assertIn("wave_26_meta_issue", d)
        self.assertIn("phase_9_status", d)

    def test_drops_historical_wave_and_phase_keys(self) -> None:
        d = self._digest(self._status())
        self.assertNotIn("wave_24_scope", d)
        # wave_2_active must NOT be swept in by the wave_25 prefix — the trailing
        # underscore in `wave_2_` vs `wave_25_` is the guard.
        self.assertNotIn("wave_2_active", d)
        self.assertNotIn("phase_3_status", d)

    def test_live_blocker_kept_resolved_audit_key_dropped(self) -> None:
        d = self._digest(self._status())
        self.assertIn("owner_decision_gated", d)
        self.assertNotIn("owner_decision_gated_resolved_2026_04_29", d)

    def test_empty_live_blocker_is_omitted(self) -> None:
        d = self._digest(self._status(owner_decision_gated=[]))
        self.assertNotIn("owner_decision_gated", d)

    def test_is_a_large_reduction(self) -> None:
        data = self._status()
        # pad with a lot of historical noise the digest must shed
        for w in range(1, 24):
            data[f"wave_{w}_scope"] = {"junk": "x" * 500}
        d = self._digest(data)
        full = len(json.dumps(data))
        proj = len(json.dumps(d))
        self.assertLess(proj, full // 4)

    def test_malformed_current_wave_degrades_gracefully(self) -> None:
        # No wave pointers at all → still emit pointers-that-exist + phase + blocker
        # without raising; wave-scoped keys simply drop out.
        d = self._digest(self._status(current_wave=None, next_wave=None))
        self.assertIn("current_phase", d)
        self.assertIn("phase_9_status", d)
        self.assertIn("owner_decision_gated", d)
        self.assertNotIn("wave_25_scope", d)

    def test_cli_prints_valid_json(self) -> None:
        with TemporaryDirectory() as td:
            status = Path(td) / "cross-repo-status.json"
            status.write_text(json.dumps(self._status()))
            import io
            from contextlib import redirect_stdout

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = wave_status.main(["digest", "--status", str(status)])
            self.assertEqual(rc, 0)
            parsed = json.loads(buf.getvalue())
            self.assertEqual(parsed["current_wave"], "wave-25")


# --------------------------------------------------------------------------- #
# direct-to-main (main#1131): merged_prs()/compute_counters() silently
# returned 0/{} on a direct-to-main wave because the base was hardcoded to a
# wave branch that never exists under that model. The fix routes through the
# wave's canonical scope set (wave_{M}_scope's tier_* rows) rather than
# base+timestamp alone, per the wave-28 retro finding that base+timestamp
# over-counts (the recorded false positive: `us#213` was in-window but
# out-of-scope).
# --------------------------------------------------------------------------- #


def _kv_flags(cmd: list[str]) -> dict[str, str]:
    """Extract every ``-f``/``-F key=value`` pair from a gh argv list."""
    out: dict[str, str] = {}
    i = 0
    while i < len(cmd):
        if cmd[i] in ("-f", "-F") and i + 1 < len(cmd):
            k, _, v = cmd[i + 1].partition("=")
            out[k] = v
        i += 1
    return out


class _FakeGhDirectToMain:
    """subprocess.run side_effect for the direct-to-main path.

    Each PR fixture dict carries: repo, number, sha, mergedAt, login,
    commit_author, closes (the issue numbers GitHub records this PR as
    closing — NOT assumed to equal the PR number, mirroring main#1172 being
    delivered by PR #1173).
    """

    def __init__(self, prs: list[dict]) -> None:
        self.prs = prs
        self.calls: list[list[str]] = []

    def __call__(self, cmd, *args, **kwargs):  # noqa: ANN001
        assert isinstance(cmd, list), f"gh called with non-list cmd: {cmd!r}"
        assert cmd[0] == "gh"
        assert kwargs.get("shell") is not True
        self.calls.append(cmd)

        if cmd[1:3] == ["pr", "list"]:
            repo = cmd[cmd.index("--repo") + 1].removeprefix("noorinalabs/")
            # direct-to-main must query base=main -- never a wave branch.
            self_base = cmd[cmd.index("--base") + 1]
            assert self_base == "main", f"expected --base main, got {self_base!r}"
            listed = [
                {
                    "number": p["number"],
                    "headRefOid": p["sha"],
                    "mergedAt": p["mergedAt"],
                    "author": {"login": p["login"]},
                }
                for p in self.prs
                if p["repo"] == repo
            ]
            return SimpleNamespace(stdout=json.dumps(listed), returncode=0, stderr="")

        if cmd[1:3] == ["api", "graphql"]:
            flags = _kv_flags(cmd)
            repo = flags["name"]
            number = int(flags["number"])
            closes = next(
                p["closes"] for p in self.prs if p["repo"] == repo and p["number"] == number
            )
            return SimpleNamespace(stdout=json.dumps(closes), returncode=0, stderr="")

        if cmd[1] == "api":
            path = cmd[2]
            parts = path.split("/")
            if "/commits/" in path:
                sha = parts[4]
                name = next(p["commit_author"] for p in self.prs if p["sha"] == sha)
                return SimpleNamespace(stdout=name + "\n", returncode=0, stderr="")
            if path.endswith("/comments"):
                number = int(parts[4])
                cr = next((p.get("cr", 0) for p in self.prs if p["number"] == number), 0)
                return SimpleNamespace(stdout=f"{cr}\n", returncode=0, stderr="")

        raise AssertionError(f"unexpected gh call: {cmd!r}")


def _scope_row(issue_number: int) -> dict:
    return {"id": f"noorinalabs-main#{issue_number}", "ref": f"main#{issue_number}"}


def _write_direct_to_main_status(
    path: Path,
    *,
    wave: str,
    repos: list[str],
    kickoff: str,
    tiers: dict[str, list[int]],
) -> None:
    """Write a cross-repo-status.json shaped like wave-29's real record:
    `wave_{M}_merge_model="direct-to-main"` + a `wave_{M}_scope` dict whose
    tier keys are NOT the fixed set from any prior wave (arbitrary tier names
    below prove the `tier_*` iteration is generic, per main#1131)."""
    scope: dict = {"theme": "test fixture", "merge_model": "direct-to-main"}
    for tier_name, issue_numbers in tiers.items():
        scope[tier_name] = [_scope_row(n) for n in issue_numbers]
    data = {
        "current_wave": int(wave),
        f"wave_{wave}_repos_in_scope": repos,
        f"wave_{wave}_kicked_off_at": kickoff,
        f"wave_{wave}_merge_model": "direct-to-main",
        f"wave_{wave}_scope": scope,
    }
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


class CanonicalIssueNumbers(unittest.TestCase):
    def test_generic_tier_iteration_not_hardcoded(self) -> None:
        """Tier names are wave-specific (main#1131: wave-29 introduced
        `tier_4_in_wave_findings`, absent from earlier waves) -- the helper
        must not hardcode any tier name."""
        with TemporaryDirectory() as td:
            status = Path(td) / "cross-repo-status.json"
            _write_direct_to_main_status(
                status,
                wave="29",
                repos=["noorinalabs-main"],
                kickoff="2026-07-27T22:56:17Z",
                tiers={
                    "tier_1_track_g": [1114],
                    "tier_4_in_wave_findings": [1160, 1162],
                    "tier_99_never_seen_before": [9999],
                },
            )
            by_repo = wave_status._canonical_issue_numbers_by_repo("29", status)
        self.assertEqual(by_repo["noorinalabs-main"], {1114, 1160, 1162, 9999})

    def test_legacy_string_tier_rows_skipped_not_raised(self) -> None:
        with TemporaryDirectory() as td:
            status = Path(td) / "cross-repo-status.json"
            data = {
                "wave_29_scope": {
                    "tier_1_backlog": ["main#322", {"id": "noorinalabs-main#1114"}],
                }
            }
            status.write_text(json.dumps(data))
            by_repo = wave_status._canonical_issue_numbers_by_repo("29", status)
        self.assertEqual(by_repo, {"noorinalabs-main": {1114}})


class MergedPrsDirectToMain(unittest.TestCase):
    """merged_prs() for a direct-to-main wave, driven by the canonical scope
    set rather than base+timestamp alone."""

    def test_base_and_timestamp_alone_would_overcount_but_scope_excludes(self) -> None:
        """The wave-28 retro false positive, reproduced: a PR in-window on
        `main` that closes an issue NEVER recorded in the wave's scope
        (`us#213`-shaped) must be excluded even though base+timestamp alone
        would have included it."""
        prs = [
            {
                "repo": "noorinalabs-main",
                "number": 1173,
                "sha": "sha1173",
                "mergedAt": "2026-07-30T02:16:40Z",
                "login": "octocat",
                "commit_author": "Nino Kavtaradze",
                "closes": [1172],  # canonical scope row
            },
            {
                "repo": "noorinalabs-main",
                "number": 9001,
                "sha": "sha9001",
                "mergedAt": "2026-07-30T02:20:00Z",  # in-window
                "login": "octocat",
                "commit_author": "Someone Else",
                "closes": [213],  # NOT in scope -- the us#213 false positive
            },
        ]
        fake = _FakeGhDirectToMain(prs)
        with TemporaryDirectory() as td:
            status = Path(td) / "cross-repo-status.json"
            _write_direct_to_main_status(
                status,
                wave="29",
                repos=["noorinalabs-main"],
                kickoff="2026-07-27T22:56:17Z",
                tiers={"tier_4_in_wave_findings": [1172]},
            )
            with mock.patch.object(wave_status.subprocess, "run", fake):
                got = wave_status.merged_prs("10", "29", status)
        self.assertEqual([p["number"] for p in got], [1173])

    def test_issue_number_need_not_equal_pr_number(self) -> None:
        """main#1172 was delivered by PR #1173 -- a different number. The PR
        must still be found via its closing-issue reference."""
        prs = [
            {
                "repo": "noorinalabs-main",
                "number": 1173,
                "sha": "sha1173",
                "mergedAt": "2026-07-30T02:16:40Z",
                "login": "octocat",
                "commit_author": "Nino Kavtaradze",
                "closes": [1172],
            }
        ]
        fake = _FakeGhDirectToMain(prs)
        with TemporaryDirectory() as td:
            status = Path(td) / "cross-repo-status.json"
            _write_direct_to_main_status(
                status,
                wave="29",
                repos=["noorinalabs-main"],
                kickoff="2026-07-27T22:56:17Z",
                tiers={"tier_4_in_wave_findings": [1172]},
            )
            with mock.patch.object(wave_status.subprocess, "run", fake):
                got = wave_status.merged_prs("10", "29", status)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["number"], 1173)
        self.assertEqual(got[0]["commit_author_name"], "Nino Kavtaradze")

    def test_bundled_pr_counted_once_across_multiple_scope_rows(self) -> None:
        """#1167/#1168/#1170/#1171 were bundled into ONE PR -- rows != PRs,
        so the same merged PR must not be double-counted across the four
        scope rows it satisfies."""
        prs = [
            {
                "repo": "noorinalabs-main",
                "number": 1174,
                "sha": "sha1174",
                "mergedAt": "2026-07-29T12:00:00Z",
                "login": "octocat",
                "commit_author": "Weronika Zielinska",
                "closes": [1167, 1168, 1170, 1171],
            }
        ]
        fake = _FakeGhDirectToMain(prs)
        with TemporaryDirectory() as td:
            status = Path(td) / "cross-repo-status.json"
            _write_direct_to_main_status(
                status,
                wave="29",
                repos=["noorinalabs-main"],
                kickoff="2026-07-27T22:56:17Z",
                tiers={"tier_4_in_wave_findings": [1167, 1168, 1170, 1171]},
            )
            with mock.patch.object(wave_status.subprocess, "run", fake):
                got = wave_status.merged_prs("10", "29", status)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["number"], 1174)

    def test_real_wave_29_five_pr_set(self) -> None:
        """Verification fixture pinned to the real wave-29 data in main#1131's
        acceptance criteria: PRs #1173/#1153/#1154/#1155/#1156, closing
        canonical issues #1172/#1139/#1134/#1152/#1151 respectively, with an
        out-of-scope in-window PR (#1178, still OPEN in reality -- modeled
        here as an unrelated closed number to prove exclusion) filtered out."""
        real = [
            (1173, "sha056a", "2026-07-30T02:16:40Z", 1172),
            (1153, "shab708", "2026-07-30T02:17:04Z", 1139),
            (1154, "shafbb5", "2026-07-30T02:17:26Z", 1134),
            (1155, "sha1207", "2026-07-30T02:17:46Z", 1152),
            (1156, "sha999d", "2026-07-30T02:40:16Z", 1151),
        ]
        prs = [
            {
                "repo": "noorinalabs-main",
                "number": number,
                "sha": sha,
                "mergedAt": merged_at,
                "login": "octocat",
                "commit_author": f"author-{number}",
                "closes": [closes],
            }
            for number, sha, merged_at, closes in real
        ] + [
            {
                "repo": "noorinalabs-main",
                "number": 9999,
                "sha": "shaoutofscope",
                "mergedAt": "2026-07-30T02:41:00Z",
                "login": "octocat",
                "commit_author": "Out Of Scope",
                "closes": [4242],  # not a canonical row anywhere
            }
        ]
        fake = _FakeGhDirectToMain(prs)
        with TemporaryDirectory() as td:
            status = Path(td) / "cross-repo-status.json"
            _write_direct_to_main_status(
                status,
                wave="29",
                repos=["noorinalabs-main"],
                kickoff="2026-07-27T22:56:17Z",
                tiers={
                    "tier_2_process_carry_forward": [1139, 1134, 1152, 1151],
                    "tier_4_in_wave_findings": [1172],
                },
            )
            with mock.patch.object(wave_status.subprocess, "run", fake):
                got = wave_status.merged_prs("10", "29", status)
        self.assertEqual(sorted(p["number"] for p in got), [1153, 1154, 1155, 1156, 1173])
        self.assertEqual(len(got), 5)

    def test_repo_with_no_canonical_rows_is_skipped(self) -> None:
        """A repo in `repos_in_scope` with no scope rows at all is skipped
        entirely -- not queried, not silently zeroed."""
        fake = _FakeGhDirectToMain([])
        with TemporaryDirectory() as td:
            status = Path(td) / "cross-repo-status.json"
            _write_direct_to_main_status(
                status,
                wave="29",
                repos=["noorinalabs-main", "noorinalabs-isnad-ingest-platform"],
                kickoff="2026-07-27T22:56:17Z",
                tiers={"tier_1_track_g": [1114]},
            )
            with mock.patch.object(wave_status.subprocess, "run", fake):
                got = wave_status.merged_prs("10", "29", status)
        self.assertEqual(got, [])
        # No "pr list" call was ever made for the scopeless repo.
        pr_list_repos = {c[c.index("--repo") + 1] for c in fake.calls if c[1:3] == ["pr", "list"]}
        self.assertNotIn("noorinalabs/noorinalabs-isnad-ingest-platform", pr_list_repos)

    def test_counters_nonzero_and_nonempty_trust_signals_for_direct_to_main(self) -> None:
        """The whole point of main#1131: compute_counters()/trust_signals must
        NOT silently return 0/{} for a direct-to-main wave."""
        prs = [
            {
                "repo": "noorinalabs-main",
                "number": 1173,
                "sha": "sha1173",
                "mergedAt": "2026-07-30T02:16:40Z",
                "login": "octocat",
                "commit_author": "Nino Kavtaradze",
                "closes": [1172],
            }
        ]
        fake = _FakeGhDirectToMain(prs)
        with TemporaryDirectory() as td:
            status = Path(td) / "cross-repo-status.json"
            _write_direct_to_main_status(
                status,
                wave="29",
                repos=["noorinalabs-main"],
                kickoff="2026-07-27T22:56:17Z",
                tiers={"tier_4_in_wave_findings": [1172]},
            )
            with mock.patch.object(wave_status.subprocess, "run", fake):
                counters = wave_status.compute_counters("10", "29", status)
        self.assertEqual(counters["final_pr_count"], 1)
        self.assertNotEqual(
            counters,
            {"final_pr_count": 0, "changes_requested_cycles": 0, "top_concentration_pct": 0},
        )


class WaveBranchPathUnchanged(unittest.TestCase):
    """Regression fixture proving BOTH merge models: an explicit
    `wave_{M}_merge_model="wave-branch"` record still routes through the
    pre-existing wave-branch base -- dispatch does not accidentally flip a
    declared wave-branch wave onto the canonical-scope path."""

    def test_explicit_wave_branch_model_keeps_wave_branch_base(self) -> None:
        prs = _p5w4_prs()
        fake = _FakeGh(prs)
        with TemporaryDirectory() as td:
            status = Path(td) / "cross-repo-status.json"
            data = {
                "wave_4_repos_in_scope": _REPOS,
                "wave_4_kicked_off_at": "2026-06-15T01:52:55Z",
                "wave_4_merge_model": "wave-branch",
            }
            status.write_text(json.dumps(data))
            with mock.patch.object(wave_status.subprocess, "run", fake):
                counters = wave_status.compute_counters("5", "4", status)
        self.assertEqual(
            counters,
            {
                "final_pr_count": 19,
                "changes_requested_cycles": 4,
                "top_concentration_pct": 16,
            },
        )
        # Every "pr list" call based on the wave branch, never "main".
        pr_list_calls = [c for c in fake.calls if c[1:3] == ["pr", "list"]]
        self.assertTrue(pr_list_calls)
        for c in pr_list_calls:
            self.assertEqual(c[c.index("--base") + 1], "deployments/phase-5/wave-4")


class BaseVsHeadDifferential(unittest.TestCase):
    """Proves the wave-branch path is BYTE-FOR-BYTE unchanged (main#1131):
    executes the pre-fix `merged_prs` straight out of the base commit's
    `.claude/lib/wave_status.py` via `git show`, runs it against the same
    fixture and the same fake gh as HEAD's `_merged_prs_wave_branch`, and
    diffs the two JSON outputs. Not a want/got table -- an actual base-vs-head
    runtime comparison of the two implementations."""

    # The commit this fix branch forked from -- main tip immediately
    # pre-#1131, so `git show <sha>:path` reads the exact pre-fix source.
    _BASE_SHA = "b290d611e9e6c59db0bf921ef6a9315090dc2eae"

    @classmethod
    def _load_base_module(cls):
        import subprocess
        import types

        repo_root = Path(__file__).resolve().parents[3]
        src = subprocess.run(
            ["git", "show", f"{cls._BASE_SHA}:.claude/lib/wave_status.py"],
            capture_output=True,
            text=True,
            check=True,
            cwd=repo_root,
        ).stdout
        mod = types.ModuleType("wave_status_base_pre_1131")
        mod.__file__ = f"<git show {cls._BASE_SHA}:.claude/lib/wave_status.py>"
        exec(compile(src, mod.__file__, "exec"), mod.__dict__)  # noqa: S102
        return mod

    def test_base_and_head_agree_on_wave_branch_output(self) -> None:
        base_mod = self._load_base_module()
        prs = _p5w4_prs()

        with TemporaryDirectory() as td:
            status = Path(td) / "cross-repo-status.json"
            _write_status(status, repos=_REPOS, wave="4", kickoff="2026-06-15T01:52:55Z")

            with mock.patch.object(base_mod.subprocess, "run", _FakeGh(prs)):
                base_out = base_mod.merged_prs("5", "4", status)
            with mock.patch.object(wave_status.subprocess, "run", _FakeGh(prs)):
                head_out = wave_status._merged_prs_wave_branch("5", "4", status)

        self.assertEqual(base_out, head_out)
        # Also prove the public dispatcher reaches the identical path when no
        # merge_model key is recorded (legacy / absent -- the common shape of
        # every pre-#1131 status file, including the one above).
        with TemporaryDirectory() as td:
            status = Path(td) / "cross-repo-status.json"
            _write_status(status, repos=_REPOS, wave="4", kickoff="2026-06-15T01:52:55Z")
            with mock.patch.object(wave_status.subprocess, "run", _FakeGh(prs)):
                dispatch_out = wave_status.merged_prs("5", "4", status)
        self.assertEqual(base_out, dispatch_out)


if __name__ == "__main__":
    unittest.main()
