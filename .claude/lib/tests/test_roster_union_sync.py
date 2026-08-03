"""Tests for roster_union_sync — the parent-roster <-> child-union sync gate.

Verifies:
  1. The pure drift computation (#634): a child persona absent from the parent
     roster is reported (with the child repos that carry it); a covered union
     is clean.
  2. parent_roster_names / parent_roster_map read the committed parent roster.
  3. local_card_names parses this repo's own roster cards (#1181).
  4. compute_manifest_orphans (#1181): the reverse assertion — a persona-shaped
     manifest entry with no backing card/child-roster anywhere is
     "unreconciled"; a non-persona-shaped one (Annunaki/Steven-French shape)
     is "non_persona" and never actionable.
  5. CLI wiring with an injected (monkeypatched) fetcher so tests never touch
     the network: clean union → exit 0, forward DRIFT → exit 1, all-skipped →
     exit 0, missing parent roster → exit 2, orphan check skipped when any
     child fetch failed.
  6. A non-vacuous regression pinned to the ACTUAL #1181 measurement: the
     exact 18 manifest-only names, real emails, real "18 unbacked" count are
     reproduced verbatim from the issue as a frozen fixture (not a live
     filesystem read against the org dir — this file's own docstring
     convention, matched by `test_validate_matrix_names.py`, is to avoid
     coupling tests to the real org-dir state, which changes wave-to-wave).
     This proves `compute_manifest_orphans` classifies the REAL, filed defect
     correctly (2 non_persona + 16 unreconciled) rather than only ever
     exercising a contrived example (#1181 acceptance: "a test that passes
     today proves nothing").
  7. The exit-code contract correction (owner review, PR #1240): the #1181
     reverse (orphan) check is advisory in EXIT STATUS, not merely in CI
     workflow config — it reports unreconciled/non-persona orphans loudly but
     NEVER moves `exit_code`. Only the pre-existing forward direction (#634:
     a child persona entirely missing from the parent) can fail the job. A
     dedicated test pins both halves of that distinction together — advisory
     orphan drift alongside a genuine forward violation still exits 1, driven
     by the forward finding alone.
"""

from __future__ import annotations

import base64
import io
import json
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import roster_union_sync  # noqa: E402
from roster_union_sync import (  # noqa: E402
    compute_drift,
    compute_manifest_orphans,
    fetch_child_card_names,
    local_card_names,
    main,
    parent_roster_map,
    parent_roster_names,
)


def _write_parent_roster(repo_root: Path, roster: dict[str, str]) -> None:
    path = repo_root / ".claude" / "team" / "roster.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(roster), encoding="utf-8")


def _write_roster_card(roster_dir: Path, filename: str, name: str) -> None:
    """Verbose-template card — mirrors the shape `local_card_names` parses."""
    roster_dir.mkdir(parents=True, exist_ok=True)
    (roster_dir / filename).write_text(
        f"# Team Member Roster Card\n\n## Identity\n- **Name:** {name}\n- **Status:** Active\n"
    )


class ComputeDrift(unittest.TestCase):
    def test_covered_union_has_no_drift(self) -> None:
        parent = {"Aino Virtanen", "Imelda Santos"}
        children = {"noorinalabs-isnad-ingest-platform": {"Imelda Santos": "i@x"}}
        self.assertEqual(compute_drift(parent, children), {})

    def test_missing_persona_is_reported_with_owning_repos(self) -> None:
        parent = {"Aino Virtanen"}
        children = {
            "noorinalabs-isnad-ingest-platform": {"Imelda Santos": "i@x"},
            "noorinalabs-user-service": {"Imelda Santos": "i@x", "Aino Virtanen": "a@x"},
        }
        drift = compute_drift(parent, children)
        # Imelda is missing and appears in BOTH child repos (sorted); Aino is
        # covered by the parent so it is not reported.
        self.assertEqual(
            drift,
            {"Imelda Santos": ["noorinalabs-isnad-ingest-platform", "noorinalabs-user-service"]},
        )

    def test_empty_children_no_drift(self) -> None:
        self.assertEqual(compute_drift({"Aino Virtanen"}, {}), {})


class ParentRosterNames(unittest.TestCase):
    def test_reads_committed_parent_keys(self) -> None:
        with TemporaryDirectory() as td:
            repo = Path(td)
            _write_parent_roster(repo, {"Aino Virtanen": "a@x", "Imelda Santos": "i@x"})
            self.assertEqual(parent_roster_names(repo), {"Aino Virtanen", "Imelda Santos"})

    def test_missing_roster_returns_empty(self) -> None:
        with TemporaryDirectory() as td:
            self.assertEqual(parent_roster_names(Path(td)), set())


class CliWithInjectedFetcher(unittest.TestCase):
    """Drive main() with fetch_child_roster/fetch_child_card_names monkeypatched — no network.

    BOTH fetchers must be patched for every test that reaches the child-repo
    loop: `main` unconditionally attempts the #1181 card fetch once the
    roster.json pass is clean, so leaving `fetch_child_card_names`
    unpatched makes a real `gh api` subprocess call per card repo — slow, and
    a hard requirement violation (tests must be hermetic / no network).
    `card_fetched` defaults to `{}`, meaning every card repo — including the
    always-added `noorinalabs-deploy` — reads as SKIPPED (`None`), which
    fails the orphan check safely closed (never a surprise exit change) for
    every test that does not care about the orphan path.
    """

    def _run(
        self,
        parent: dict[str, str],
        fetched: dict[str, dict | None],
        repos: str,
        card_fetched: dict[str, set[str] | None] | None = None,
    ) -> int:
        with TemporaryDirectory() as td:
            repo = Path(td)
            _write_parent_roster(repo, parent)
            orig_roster = roster_union_sync.fetch_child_roster
            orig_cards = roster_union_sync.fetch_child_card_names
            roster_union_sync.fetch_child_roster = lambda owner, r: fetched.get(r)  # type: ignore[assignment]
            roster_union_sync.fetch_child_card_names = lambda owner, r: (  # type: ignore[assignment]
                card_fetched or {}
            ).get(r)
            try:
                return main(["--repo-root", str(repo), "--repos", repos])
            finally:
                roster_union_sync.fetch_child_roster = orig_roster
                roster_union_sync.fetch_child_card_names = orig_cards

    def test_clean_union_exit_0(self) -> None:
        rc = self._run(
            {"Aino Virtanen": "a@x", "Imelda Santos": "i@x"},
            {"noorinalabs-isnad-ingest-platform": {"Imelda Santos": "i@x"}},
            "noorinalabs-isnad-ingest-platform",
        )
        self.assertEqual(rc, 0)

    def test_drift_exit_1(self) -> None:
        rc = self._run(
            {"Aino Virtanen": "a@x"},
            {"noorinalabs-isnad-ingest-platform": {"Imelda Santos": "i@x"}},
            "noorinalabs-isnad-ingest-platform",
        )
        self.assertEqual(rc, 1)

    def test_all_children_skipped_exit_0(self) -> None:
        # Fail-open: every child unreadable (fetch returns None) → nothing to
        # cross-check → pass (advisory), never a drift failure on its own.
        rc = self._run(
            {"Aino Virtanen": "a@x"},
            {"noorinalabs-deploy": None},
            "noorinalabs-deploy",
        )
        self.assertEqual(rc, 0)

    def test_missing_parent_roster_exit_2(self) -> None:
        with TemporaryDirectory() as td:
            empty = Path(td) / "no-roster"
            empty.mkdir()
            rc = main(["--repo-root", str(empty), "--repos", "noorinalabs-isnad-graph"])
            self.assertEqual(rc, 2)

    def test_orphan_drift_is_advisory_and_exits_0(self) -> None:
        """#1181 orphan drift alone (owner correction, PR #1240 review): reported

        loudly, but NEVER fails the job on its own — only a genuine forward
        (#634) violation may do that. See the `_combined_pin` test below for
        both halves of that distinction pinned together.
        """
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            rc = self._run(
                {"Persona X": "parametrization+Persona.X@gmail.com"},
                {"noorinalabs-isnad-graph": {}},
                "noorinalabs-isnad-graph",
                card_fetched={"noorinalabs-isnad-graph": set(), "noorinalabs-deploy": set()},
            )
        self.assertEqual(rc, 0)
        self.assertIn("Persona X", stderr.getvalue())
        self.assertIn("MANIFEST ORPHAN", stderr.getvalue())

    def test_forward_drift_exits_1_even_with_advisory_orphan_drift(self) -> None:
        """Pins the exact distinction the owner asked for in one test:

        advisory orphan drift (persona-shaped, uncarded manifest entry) present
        AND a genuine forward (#634) violation (a child persona missing from
        the parent) present, in the SAME run — exit 1, driven by the forward
        finding alone, not the orphan one.
        """
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            rc = self._run(
                {"Persona X": "parametrization+Persona.X@gmail.com"},  # orphan: uncarded
                {"noorinalabs-isnad-graph": {"Imelda Santos": "i@x"}},  # missing from parent
                "noorinalabs-isnad-graph",
                card_fetched={"noorinalabs-isnad-graph": set(), "noorinalabs-deploy": set()},
            )
        self.assertEqual(rc, 1)
        out = stderr.getvalue()
        self.assertIn("DRIFT", out)
        self.assertIn("Imelda Santos", out)
        self.assertIn("MANIFEST ORPHAN", out)
        self.assertIn("Persona X", out)

    def test_card_only_child_persona_is_not_a_false_positive_orphan(self) -> None:
        """#1181: a card whose OWN repo's roster.json aggregate lags it is not an orphan.

        Real instance measured live: `noorinalabs-isnad-graph` carries
        `data_scientist_mei.md` (Mei-Lin Chang) but her name is absent from
        that repo's OWN `roster.json` — fetching only roster.json would
        false-positive her as unbacked.

        Stream assertions (owner review, PR #1240): `rc` alone cannot pin
        this — the orphan check is advisory in EVERY outcome, so `rc == 0`
        whether or not the card union actually ran. Only the emitted report
        text distinguishes "correctly recognized as backed" from "the card
        union silently stopped running."
        """
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            rc = self._run(
                {"Mei-Lin Chang": "parametrization+Mei-Lin.Chang@gmail.com"},
                {"noorinalabs-isnad-graph": {}},  # absent from the repo's own aggregate
                "noorinalabs-isnad-graph",
                card_fetched={
                    "noorinalabs-isnad-graph": {"Mei-Lin Chang"},  # but her CARD exists
                    "noorinalabs-deploy": set(),
                },
            )
        self.assertEqual(rc, 0)
        self.assertNotIn("Mei-Lin Chang", stderr.getvalue())
        self.assertIn("No unreconciled orphans", stdout.getvalue())

    def test_deploy_cards_seen_even_though_deploy_has_no_roster_json(self) -> None:
        """`noorinalabs-deploy` is excluded from --repos (no roster.json to fetch,
        DEFAULT_CHILD_REPOS comment) but the #1181 orphan check must still see
        its card directory — it is always added for the card-fetch pass.

        Stream assertions for the same reason as the Mei-Lin Chang test above.
        """
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            rc = self._run(
                {"Aisha Idrissi": "parametrization+Aisha.Idrissi@gmail.com"},
                {"noorinalabs-isnad-graph": {}},
                "noorinalabs-isnad-graph",
                card_fetched={
                    "noorinalabs-isnad-graph": set(),
                    "noorinalabs-deploy": {"Aisha Idrissi"},
                },
            )
        self.assertEqual(rc, 0)
        self.assertNotIn("Aisha Idrissi", stderr.getvalue())
        self.assertIn("No unreconciled orphans", stdout.getvalue())

    def test_orphan_check_skipped_when_card_fetch_incomplete(self) -> None:
        """A card-fetch skip (here: `noorinalabs-deploy` unreadable) also suppresses
        the orphan check, same as a roster.json skip — never a false positive.

        Stream assertions (owner review, PR #1240): `rc == 0` is also what an
        UN-skipped, cleanly-passing run would report, so `rc` alone cannot
        distinguish "the skip guard fired" from "the skip guard was removed
        and the check just happened to find nothing." Assert the SKIPPED
        notice printed and `Persona X` — who WOULD be unreconciled if the
        check had actually run — never appears anywhere.
        """
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            rc = self._run(
                {"Persona X": "parametrization+Persona.X@gmail.com"},
                {"noorinalabs-isnad-graph": {}},
                "noorinalabs-isnad-graph",
                card_fetched={"noorinalabs-isnad-graph": set()},  # deploy missing -> None -> skip
            )
        self.assertEqual(rc, 0)
        self.assertIn("Manifest-orphan check (#1181) SKIPPED", stdout.getvalue())
        self.assertNotIn("Persona X", stdout.getvalue() + stderr.getvalue())

    def test_orphan_check_skipped_when_any_child_fetch_fails(self) -> None:
        """#1181: an incomplete fetch must not produce a false-positive orphan report.

        `Amara Diallo` would be "unreconciled" if the orphan check ran — but
        `noorinalabs-user-service` is unreadable, so the check does not run at
        all (fail-open, same posture as the forward direction) and the run
        stays exit 0 (forward drift is separately clean).

        Stream assertions for the same reason as the card-fetch-incomplete
        test above — `rc` alone does not distinguish "skipped" from "ran and
        happened to pass."
        """
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            rc = self._run(
                {"Amara Diallo": "parametrization+Amara.Diallo@gmail.com"},
                {"noorinalabs-isnad-graph": {}, "noorinalabs-user-service": None},
                "noorinalabs-isnad-graph,noorinalabs-user-service",
            )
        self.assertEqual(rc, 0)
        self.assertIn("Manifest-orphan check (#1181) SKIPPED", stdout.getvalue())
        self.assertNotIn("Amara Diallo", stdout.getvalue() + stderr.getvalue())


class FetchChildCardNamesTests(unittest.TestCase):
    """#1181: unit coverage of the (list dir, then fetch each file) parse logic,
    with `subprocess.run` mocked — no network."""

    def test_parses_names_from_two_card_files_and_skips_non_md(self) -> None:
        card_1 = base64.b64encode(b"## Identity\n- **Name:** Alpha One\n").decode()
        card_2 = base64.b64encode(
            "# Beta Two — Engineer\n\n- **Status:** Active\n".encode()
        ).decode()

        def fake_run(cmd, **kwargs):
            result = subprocess.CompletedProcess(cmd, 0)
            if cmd[-1] == ".[].name":
                result.stdout = "alpha.md\nbeta.md\nNOTES.txt\n"
            elif cmd[2].endswith("/alpha.md"):
                result.stdout = card_1
            elif cmd[2].endswith("/beta.md"):
                result.stdout = card_2
            else:
                raise AssertionError(f"unexpected command {cmd}")
            return result

        with patch("subprocess.run", side_effect=fake_run):
            names = fetch_child_card_names("noorinalabs", "noorinalabs-deploy")
        self.assertEqual(names, {"Alpha One", "Beta Two"})

    def test_missing_directory_returns_none(self) -> None:
        def fake_run(cmd, **kwargs):
            raise subprocess.CalledProcessError(1, cmd)

        with patch("subprocess.run", side_effect=fake_run):
            self.assertIsNone(fetch_child_card_names("noorinalabs", "noorinalabs-does-not-exist"))

    def test_empty_directory_returns_none(self) -> None:
        def fake_run(cmd, **kwargs):
            result = subprocess.CompletedProcess(cmd, 0)
            result.stdout = ""
            return result

        with patch("subprocess.run", side_effect=fake_run):
            self.assertIsNone(fetch_child_card_names("noorinalabs", "noorinalabs-empty"))

    def test_one_file_fetch_failure_does_not_abort_the_others(self) -> None:
        card_2 = base64.b64encode(
            "# Beta Two — Engineer\n\n- **Status:** Active\n".encode()
        ).decode()

        def fake_run(cmd, **kwargs):
            if cmd[-1] == ".[].name":
                result = subprocess.CompletedProcess(cmd, 0)
                result.stdout = "alpha.md\nbeta.md\n"
                return result
            if cmd[2].endswith("/alpha.md"):
                raise subprocess.CalledProcessError(1, cmd)
            result = subprocess.CompletedProcess(cmd, 0)
            result.stdout = card_2
            return result

        with patch("subprocess.run", side_effect=fake_run):
            names = fetch_child_card_names("noorinalabs", "noorinalabs-deploy")
        self.assertEqual(names, {"Beta Two"})


class ParentRosterMapTests(unittest.TestCase):
    def test_reads_raw_map(self) -> None:
        with TemporaryDirectory() as td:
            repo = Path(td)
            _write_parent_roster(repo, {"Aino Virtanen": "a@x"})
            self.assertEqual(parent_roster_map(repo), {"Aino Virtanen": "a@x"})

    def test_missing_roster_returns_empty_dict(self) -> None:
        with TemporaryDirectory() as td:
            self.assertEqual(parent_roster_map(Path(td)), {})


class LocalCardNamesTests(unittest.TestCase):
    """#1181: parses THIS repo's own roster cards — never a child repo's."""

    def test_reads_verbose_cards(self) -> None:
        with TemporaryDirectory() as td:
            repo = Path(td)
            roster_dir = repo / ".claude" / "team" / "roster"
            _write_roster_card(roster_dir, "tpm_wanjiku.md", "Wanjiku Mwangi")
            _write_roster_card(roster_dir, "pd_nadia.md", "Nadia Khoury")
            self.assertEqual(local_card_names(repo), {"Wanjiku Mwangi", "Nadia Khoury"})

    def test_reads_slim_h1_cards(self) -> None:
        """#1010 slim template: H1 `# Name — Role`, no `**Name:**` field."""
        with TemporaryDirectory() as td:
            repo = Path(td)
            roster_dir = repo / ".claude" / "team" / "roster"
            roster_dir.mkdir(parents=True)
            (roster_dir / "eng_aino.md").write_text(
                "# Aino Virtanen — Standards Lead\n\n- **Status:** Active\n"
            )
            self.assertEqual(local_card_names(repo), {"Aino Virtanen"})

    def test_no_roster_dir_returns_empty(self) -> None:
        with TemporaryDirectory() as td:
            self.assertEqual(local_card_names(Path(td)), set())


class ComputeManifestOrphansTests(unittest.TestCase):
    """#1181: the reverse assertion — manifest ⊆ cards ∪ child rosters."""

    def test_card_backed_name_is_not_an_orphan(self) -> None:
        parent = {"Wanjiku Mwangi": "parametrization+Wanjiku.Mwangi@gmail.com"}
        orphans = compute_manifest_orphans(parent, {"Wanjiku Mwangi"}, {})
        self.assertEqual(orphans, {"unreconciled": [], "non_persona": []})

    def test_child_roster_backed_name_is_not_an_orphan(self) -> None:
        parent = {"Imelda Santos": "parametrization+Imelda.Santos@gmail.com"}
        children = {"noorinalabs-isnad-ingest-platform": {"Imelda Santos": "i@x"}}
        orphans = compute_manifest_orphans(parent, set(), children)
        self.assertEqual(orphans, {"unreconciled": [], "non_persona": []})

    def test_persona_shaped_unbacked_name_is_unreconciled(self) -> None:
        parent = {"Amara Diallo": "parametrization+Amara.Diallo@gmail.com"}
        orphans = compute_manifest_orphans(parent, set(), {})
        self.assertEqual(orphans, {"unreconciled": ["Amara Diallo"], "non_persona": []})

    def test_non_persona_shaped_unbacked_name_is_non_persona(self) -> None:
        """Annunaki-shape (no `.` after the `+`): flagged, never actionable."""
        parent = {"Annunaki": "parametrization+Annunaki@gmail.com"}
        orphans = compute_manifest_orphans(parent, set(), {})
        self.assertEqual(orphans, {"unreconciled": [], "non_persona": ["Annunaki"]})

    def test_bare_principal_unbacked_is_non_persona(self) -> None:
        """Steven-French-shape (no `+` at all): flagged, never actionable."""
        parent = {"Steven French": "parametrization@gmail.com"}
        orphans = compute_manifest_orphans(parent, set(), {})
        self.assertEqual(orphans, {"unreconciled": [], "non_persona": ["Steven French"]})

    def test_results_sorted(self) -> None:
        parent = {
            "Zeta Persona": "parametrization+Zeta.Persona@gmail.com",
            "Alpha Persona": "parametrization+Alpha.Persona@gmail.com",
        }
        orphans = compute_manifest_orphans(parent, set(), {})
        self.assertEqual(orphans["unreconciled"], ["Alpha Persona", "Zeta Persona"])


class RealMeasuredDriftRegressionTests(unittest.TestCase):
    """Pinned to the ACTUAL #1181/#1183 measurement (2026-07-29, main checkout).

    Real names + the real `.claude/team/roster.json` email values for the
    exact 18 manifest-only entries #1181 found, copied verbatim from the issue
    body, plus a couple of genuinely BACKED real names (present on an actual
    parent roster card) to prove the classification isn't accidentally
    over-broad. This is a frozen snapshot rather than a live read of the org
    dir — this module's other tests already avoid coupling to the real
    org-dir state, which changes wave-to-wave — but the VALUES are the real
    ones, so a regression on the actual filed defect fails this test, which a
    purely synthetic example cannot demonstrate (#1181 acceptance: "a test
    that passes today proves nothing").
    """

    REAL_UNBACKED_18: dict[str, str] = {
        "Amara Diallo": "parametrization+Amara.Diallo@gmail.com",
        "Annunaki": "parametrization+Annunaki@gmail.com",
        "Carolina Méndez-Ríos": "parametrization+Carolina.Mendez-Rios@gmail.com",
        "Cedric Novak": "parametrization+Cedric.Novak@gmail.com",
        "Dmitri Volkov": "parametrization+Dmitri.Volkov@gmail.com",
        "Elena Petrova": "parametrization+Elena.Petrova@gmail.com",
        "Fatima Okonkwo": "parametrization+Fatima.Okonkwo@gmail.com",
        "Hiro Tanaka": "parametrization+Hiro.Tanaka@gmail.com",
        "Kwame Asante": "parametrization+Kwame.Asante@gmail.com",
        "Mei Chen": "parametrization+Mei.Chen@gmail.com",
        "Priya Nair": "parametrization+Priya.Nair@gmail.com",
        "Rashid Osei-Mensah": "parametrization+Rashid.Osei-Mensah@gmail.com",
        "Renaud Tremblay": "parametrization+Renaud.Tremblay@gmail.com",
        "Sable Nakamura-Whitfield": "parametrization+Sable.Nakamura-Whitfield@gmail.com",
        "Steven French": "parametrization@gmail.com",
        "Sunita Krishnamurthy": "parametrization+Sunita.Krishnamurthy@gmail.com",
        "Tomasz Wójcik": "parametrization+Tomasz.Wojcik@gmail.com",
        "Yara Hadid": "parametrization+Yara.Hadid@gmail.com",
    }

    # Real personas, real parent-repo roster cards (main#634 onboarding).
    REAL_BACKED: dict[str, str] = {
        "Wanjiku Mwangi": "parametrization+Wanjiku.Mwangi@gmail.com",
        "Nadia Khoury": "parametrization+Nadia.Khoury@gmail.com",
    }

    def test_reproduces_the_exact_filed_18(self) -> None:
        parent_map = {**self.REAL_UNBACKED_18, **self.REAL_BACKED}
        card_names = set(self.REAL_BACKED)
        orphans = compute_manifest_orphans(parent_map, card_names, {})

        self.assertEqual(orphans["non_persona"], ["Annunaki", "Steven French"])
        expected_unreconciled = sorted(set(self.REAL_UNBACKED_18) - {"Annunaki", "Steven French"})
        self.assertEqual(orphans["unreconciled"], expected_unreconciled)
        self.assertEqual(len(orphans["unreconciled"]), 16)
        for name in self.REAL_BACKED:
            self.assertNotIn(name, orphans["unreconciled"])
            self.assertNotIn(name, orphans["non_persona"])

    def test_cli_reports_the_real_unreconciled_16_but_exits_0(self) -> None:
        """End-to-end against the real #1181 data: advisory, so exit 0.

        Owner correction (PR #1240 review): `continue-on-error: true` on the
        CI job protects the WORKFLOW run's conclusion, but `pr_ci_state.py` /
        `validate_pr_ci_status.py` (the org's actual merge-readiness oracle)
        read the JOB's own conclusion from the PR's `statusCheckRollup` — a
        non-zero exit here would mark every future PR in the repo "failing"
        until the (explicitly out-of-scope-for-#1181) disposition of these 16
        names is resolved. So this must exit 0 while still naming all 16.
        """
        with TemporaryDirectory() as td:
            repo = Path(td)
            _write_parent_roster(repo, {**self.REAL_UNBACKED_18, **self.REAL_BACKED})
            roster_dir = repo / ".claude" / "team" / "roster"
            for name in self.REAL_BACKED:
                _write_roster_card(roster_dir, f"{name.replace(' ', '_').lower()}.md", name)
            orig_roster = roster_union_sync.fetch_child_roster
            orig_cards = roster_union_sync.fetch_child_card_names
            roster_union_sync.fetch_child_roster = lambda owner, r: {}  # type: ignore[assignment]
            roster_union_sync.fetch_child_card_names = lambda owner, r: set()  # type: ignore[assignment]
            stderr = io.StringIO()
            try:
                with redirect_stderr(stderr):
                    rc = main(["--repo-root", str(repo), "--repos", "noorinalabs-isnad-graph"])
            finally:
                roster_union_sync.fetch_child_roster = orig_roster
                roster_union_sync.fetch_child_card_names = orig_cards
            self.assertEqual(rc, 0)
            out = stderr.getvalue()
            for name in set(self.REAL_UNBACKED_18) - {"Annunaki", "Steven French"}:
                self.assertIn(name, out)


if __name__ == "__main__":
    unittest.main()
