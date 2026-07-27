#!/usr/bin/env python3
"""Tests for `kickoff_sweep` — the state-based kickoff reconciliation (main#1141).

The sweep is the layer that closes the class the command parser cannot: a
`for n in …; do gh issue edit "$n" --add-label "wave-29"; done` loop carries no
issue number in the command string, so no hook can react to it. The sweep keys
on the label that LANDED instead.

Every external interaction (issue list, comment fetch, comment post, body file
write) is injected, so the whole decision path runs with no network.

Run: python3 -m pytest .claude/lib/tests/test_kickoff_sweep.py -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_LIB_DIR))

import kickoff_sweep as ks  # noqa: E402


def _status(**extra) -> dict:
    status = {
        "current_phase": 10,
        "wave_29_meta_issue": 1133,
        "wave_29_merge_model": "direct-to-main",
        "wave_29_repos_in_scope": ["noorinalabs-main"],
        "wave_29_scope": {
            "tier_1_track_g": [
                {
                    "id": "noorinalabs-main#1114",
                    "ref": "main#1114",
                    "implementer": "Nino Kavtaradze",
                    "reviewer": "Aino Virtanen",
                },
                {
                    "id": "noorinalabs-main#1116",
                    "ref": "main#1116",
                    "implementer": "Lucas Ferreira",
                    "reviewer": "Aino Virtanen",
                },
            ]
        },
    }
    status.update(extra)
    return status


class _Recorder:
    """Injectable I/O doubles + a record of what the sweep tried to do."""

    def __init__(self, issues: list[str], commented: set[str] | None = None, ok: bool = True):
        self.issues = issues
        self.commented = commented or set()
        self.ok = ok
        self.posted: list[tuple[str, str]] = []
        self.bodies: dict[str, str] = {}

    def list_issues(self, repo, labels):
        return list(self.issues)

    def fetch_comments(self, repo, number):
        if number in self.commented:
            return [{"body": "**Wave 29 Kickoff — Phase 10**\n\nbody"}]
        return []

    def write_body(self, body, repo, number):
        self.bodies[number] = body
        return Path("/dev/null")

    def post(self, repo, number, path):
        self.posted.append((repo, number))
        return self.ok


class WaveLabels(unittest.TestCase):
    def test_both_label_forms_are_swept(self) -> None:
        """The global form AND the grandfathered phase-prefixed form (#810)."""
        self.assertEqual(ks.wave_labels(10, 29), ["wave-29", "p10-wave-29"])


class SweepReconciliation(unittest.TestCase):
    def _sweep(self, rec: _Recorder, status: dict | None = None, apply: bool = True):
        return ks.sweep(
            10,
            29,
            status or _status(),
            ["noorinalabs-main"],
            apply=apply,
            list_issues=rec.list_issues,
            fetch_comments=rec.fetch_comments,
            post_comment=rec.post,
            body_writer=rec.write_body,
        )

    def test_posts_to_labeled_issue_missing_a_kickoff(self) -> None:
        """The loop-applied label case: the label landed, no comment exists."""
        rec = _Recorder(["1114", "1116"])
        results = self._sweep(rec)
        self.assertEqual([r["action"] for r in results], [ks.POSTED, ks.POSTED])
        self.assertEqual(rec.posted, [("noorinalabs-main", "1114"), ("noorinalabs-main", "1116")])

    def test_idempotent_second_run_posts_nothing(self) -> None:
        """Safe to re-run — the hook's wave-specific idempotency check screens."""
        rec = _Recorder(["1114", "1116"], commented={"1114", "1116"})
        results = self._sweep(rec)
        self.assertEqual([r["action"] for r in results], [ks.SKIP_IDEMPOTENT] * 2)
        self.assertEqual(rec.posted, [])

    def test_partial_backfill(self) -> None:
        """Exactly the post-#1141 recovery shape: some got a comment, some didn't."""
        rec = _Recorder(["1114", "1116"], commented={"1114"})
        results = self._sweep(rec)
        self.assertEqual([r["action"] for r in results], [ks.SKIP_IDEMPOTENT, ks.POSTED])
        self.assertEqual(rec.posted, [("noorinalabs-main", "1116")])

    def test_meta_issue_skipped(self) -> None:
        """The meta-issue gets /wave-kickoff Step 8's all-hands comment instead."""
        rec = _Recorder(["1133"])
        results = self._sweep(rec)
        self.assertEqual([r["action"] for r in results], [ks.SKIP_META_ISSUE])
        self.assertEqual(rec.posted, [])

    def test_labeled_but_unscoped_issue_is_surfaced_not_posted(self) -> None:
        """A label with no tier row is /wave-scope drift — report, don't guess."""
        rec = _Recorder(["9999"])
        results = self._sweep(rec)
        self.assertEqual([r["action"] for r in results], [ks.SKIP_NO_ROW])
        self.assertEqual(rec.posted, [])

    def test_dry_run_writes_nothing(self) -> None:
        rec = _Recorder(["1114"])
        results = self._sweep(rec, apply=False)
        self.assertEqual([r["action"] for r in results], [ks.WOULD_POST])
        self.assertEqual(rec.posted, [])
        self.assertIn("Requestee: Nino Kavtaradze", results[0]["body"])

    def test_failed_post_is_recorded(self) -> None:
        rec = _Recorder(["1114"], ok=False)
        results = self._sweep(rec)
        self.assertEqual([r["action"] for r in results], [ks.POST_FAILED])

    def test_body_follows_the_wave_merge_model(self) -> None:
        """One renderer: the sweep can never drift from the hook's template."""
        rec = _Recorder(["1114"])
        self._sweep(rec)
        self.assertIn("- Branch from: `main`", rec.bodies["1114"])

        rec = _Recorder(["1114"])
        self._sweep(rec, status=_status(wave_29_merge_model="wave-branch"))
        self.assertIn("- Branch from: `deployments/phase-10/wave-29`", rec.bodies["1114"])

    def test_phase_recovered_from_status(self) -> None:
        rec = _Recorder(["1114"])
        self._sweep(rec)
        self.assertIn("**Wave 29 Kickoff — Phase 10**", rec.bodies["1114"])

    def test_phase_argument_used_when_status_has_none(self) -> None:
        status = _status()
        del status["current_phase"]
        rec = _Recorder(["1114"])
        self._sweep(rec, status=status)
        self.assertIn("**Wave 29 Kickoff — Phase 10**", rec.bodies["1114"])

    def test_no_candidates_is_an_empty_report(self) -> None:
        self.assertEqual(self._sweep(_Recorder([])), [])


class MetaIssueNumber(unittest.TestCase):
    def test_bare_int_form(self) -> None:
        self.assertEqual(ks._meta_issue_number({"wave_29_meta_issue": 1133}, 29), "1133")

    def test_qualified_string_form(self) -> None:
        """main#1053: /wave-retro writes `noorinalabs-main#821`."""
        self.assertEqual(
            ks._meta_issue_number({"wave_29_meta_issue": "noorinalabs-main#821"}, 29), "821"
        )

    def test_absent(self) -> None:
        self.assertIsNone(ks._meta_issue_number({}, 29))


class ListLabeledIssues(unittest.TestCase):
    def test_unions_both_label_forms_and_dedups(self) -> None:
        calls: list[list[str]] = []

        def run_gh(args):
            calls.append(args)
            label = args[args.index("--label") + 1]
            if label == "wave-29":
                return '[{"number": 1116}, {"number": 1114}]'
            return '[{"number": 1114}, {"number": 1120}]'

        self.assertEqual(
            ks.list_labeled_issues("noorinalabs-main", ks.wave_labels(10, 29), run_gh=run_gh),
            ["1114", "1116", "1120"],
        )
        self.assertEqual(len(calls), 2)

    def test_only_open_issues_are_swept(self) -> None:
        """A closed issue is not kicked off; a comment there is noise."""
        seen: list[str] = []

        def run_gh(args):
            seen.append(args[args.index("--state") + 1])
            return "[]"

        ks.list_labeled_issues("noorinalabs-main", ["wave-29"], run_gh=run_gh)
        self.assertEqual(seen, ["open"])

    def test_empty_output_tolerated(self) -> None:
        self.assertEqual(ks.list_labeled_issues("r", ["wave-29"], run_gh=lambda a: ""), [])


class FormatReport(unittest.TestCase):
    def test_dry_run_labels_itself(self) -> None:
        out = ks.format_report(
            29,
            [{"repo": "noorinalabs-main", "issue": "1114", "action": ks.WOULD_POST}],
            apply=False,
        )
        self.assertIn("DRY RUN", out)
        self.assertIn("[would_post] noorinalabs-main#1114", out)
        self.assertIn("would_post=1", out)

    def test_empty_is_explicit(self) -> None:
        out = ks.format_report(29, [], apply=True)
        self.assertIn("no open issue carries a wave-29 label", out)


if __name__ == "__main__":
    unittest.main()
