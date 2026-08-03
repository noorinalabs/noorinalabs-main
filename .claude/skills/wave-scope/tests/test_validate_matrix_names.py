"""Tests for /wave-scope validate_matrix_names roster check (#319).

The P3W7 retro surfaced an "Anya Volkov" alias in the scope matrix that
doesn't exist in any roster (canonical isnad-graph Tech Lead is "Anya
Kowalczyk"). Substitution worked in-flight but wasn't caught at scope time.
This test pins that the validator surfaces such aliases with a suggestion.

Tests use isolated tmpdir-based rosters to avoid coupling to the real
org-dir state (which changes wave-to-wave).
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from validate_matrix_names import (  # noqa: E402
    _load_org_manifest_names,
    _override_rationale,
    _print_report_to_stderr,
    repo_of_row,
    validate,
    validate_scope,
)


def _write_roster_card(roster_dir: Path, role_slug: str, name: str) -> None:
    """Mimic the in-repo roster card shape: `**Name:** <name>` field."""
    roster_dir.mkdir(parents=True, exist_ok=True)
    (roster_dir / f"{role_slug}.md").write_text(
        "# Team Member Roster Card\n\n"
        "## Identity\n"
        f"- **Name:** {name}\n"
        "- **Role:** Engineer\n"
        "- **Status:** Active\n"
    )


def _build_fake_org_dir(tmp: Path) -> Path:
    """Build a fake org-dir with parent + 2 child rosters for testing."""
    # Parent roster — org-level coordinators.
    parent_roster = tmp / ".claude" / "team" / "roster"
    _write_roster_card(parent_roster, "pd_nadia", "Nadia Khoury")
    _write_roster_card(parent_roster, "tpm_wanjiku", "Wanjiku Mwangi")
    _write_roster_card(parent_roster, "sql_aino", "Aino Virtanen")
    # Child: noorinalabs-deploy
    deploy_roster = tmp / "noorinalabs-deploy" / ".claude" / "team" / "roster"
    _write_roster_card(deploy_roster, "lead_bereket", "Bereket Tadesse")
    _write_roster_card(deploy_roster, "eng_lucas", "Lucas Ferreira")
    # Child: noorinalabs-isnad-graph
    graph_roster = tmp / "noorinalabs-isnad-graph" / ".claude" / "team" / "roster"
    _write_roster_card(graph_roster, "tl_anya", "Anya Kowalczyk")
    _write_roster_card(graph_roster, "eng_idris", "Idris Yusuf")
    _write_roster_card(graph_roster, "eng_marisol", "Marisol Vega-Cruz")
    return tmp


def _write_slim_roster_card(roster_dir: Path, role_slug: str, name: str) -> None:
    """Mimic the NEW slim card shape (#1010): H1 `# <Name> — <Role>`, no
    `**Name:**` field. Verbatim to the shipped template so the fixture can't
    pass while the real cards fail (feedback_fixture_makes_guard_assertion_inert).
    """
    roster_dir.mkdir(parents=True, exist_ok=True)
    (roster_dir / f"{role_slug}.md").write_text(
        f"# {name} — Engineer\n\n"
        "- **Level:** Senior · **Status:** Active\n"
        f"- **Git:** {name} <parametrization+{name.replace(' ', '.')}@gmail.com>\n\n"
        "**Style:** Terse.\n"
    )


class SlimCardFormatTests(unittest.TestCase):
    """#1010: slim H1 cards (no `**Name:**` field) must still resolve.

    Regression guard — the pre-#1010 parser only matched `**Name:**` and
    silently extracted ZERO names from a slimmed roster dir, fail-closing
    every name in that repo's matrix slot.
    """

    def test_slim_parent_and_child_names_resolve(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            org = Path(tmpdir)
            _write_slim_roster_card(
                org / ".claude" / "team" / "roster", "sql_aino", "Aino Virtanen"
            )
            # Hyphenated child name — the `\\s+[—–-]\\s+` separator must NOT
            # split "Jun-Seo Park" at its internal hyphen.
            _write_slim_roster_card(
                org / "noorinalabs-isnad-graph" / ".claude" / "team" / "roster",
                "tl_junseo",
                "Jun-Seo Park",
            )
            matrix = {
                "noorinalabs-isnad-graph": {
                    "implementer": "Jun-Seo Park",
                    "reviewer": "Aino Virtanen",  # parent-org-level, slim card
                }
            }
            report = validate(matrix, org)
            for f in report["noorinalabs-isnad-graph"]:
                self.assertTrue(f["resolved"], f"{f['declared']} should resolve")

    def test_mixed_format_roster_dir_resolves_both(self):
        """A roster dir mid-transition (one slim card + one old card) resolves both."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org = Path(tmpdir)
            roster = org / ".claude" / "team" / "roster"
            _write_slim_roster_card(roster, "sql_aino", "Aino Virtanen")
            _write_roster_card(roster, "pd_nadia", "Nadia Khoury")  # old format
            matrix = {"noorinalabs-main": {"a": "Aino Virtanen", "b": "Nadia Khoury"}}
            report = validate(matrix, org)
            for f in report["noorinalabs-main"]:
                self.assertTrue(f["resolved"], f"{f['declared']} should resolve")


class HappyPathTests(unittest.TestCase):
    """All declared names resolve to canonical roster entries."""

    def test_all_resolved_returns_no_unresolved(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            org = _build_fake_org_dir(Path(tmpdir))
            matrix = {
                "noorinalabs-isnad-graph": {
                    "implementer": "Anya Kowalczyk",
                    "reviewer": "Idris Yusuf",
                },
            }
            report = validate(matrix, org)
            findings = report["noorinalabs-isnad-graph"]
            self.assertEqual(len(findings), 2)
            for f in findings:
                self.assertTrue(f["resolved"], f"{f['declared']} should be resolved")

    def test_org_level_coordinator_resolves_in_child_slot(self):
        """Parent-roster coordinators (Aino, Nadia, etc.) can fill child-repo slots."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org = _build_fake_org_dir(Path(tmpdir))
            matrix = {
                "noorinalabs-isnad-graph": {
                    "implementer": "Anya Kowalczyk",
                    "reviewer": "Aino Virtanen",  # parent-org-level
                }
            }
            report = validate(matrix, org)
            findings = report["noorinalabs-isnad-graph"]
            for f in findings:
                self.assertTrue(f["resolved"], f"{f['declared']} should be resolved")

    def test_parenthetical_role_stripped_for_match(self):
        """`Aino Virtanen (Standards Lead)` should resolve to `Aino Virtanen`."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org = _build_fake_org_dir(Path(tmpdir))
            matrix = {
                "noorinalabs-isnad-graph": {
                    "reviewer": "Aino Virtanen (Standards & Quality Lead)",
                }
            }
            report = validate(matrix, org)
            self.assertTrue(report["noorinalabs-isnad-graph"][0]["resolved"])


class UnresolvedNameTests(unittest.TestCase):
    """Names that don't match any roster — must surface + suggest."""

    def test_anya_volkov_alias_surfaces_with_suggestion(self):
        """P3W7 reproducer: Anya Volkov is a stale alias; canonical = Anya Kowalczyk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org = _build_fake_org_dir(Path(tmpdir))
            matrix = {
                "noorinalabs-isnad-graph": {
                    "implementer": "Anya Volkov",
                }
            }
            report = validate(matrix, org)
            finding = report["noorinalabs-isnad-graph"][0]
            self.assertFalse(finding["resolved"])
            self.assertIn("Anya Kowalczyk", finding["suggestions"])

    def test_completely_unknown_name_surfaces_with_best_guess(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            org = _build_fake_org_dir(Path(tmpdir))
            matrix = {
                "noorinalabs-deploy": {
                    "implementer": "Nonexistent Person",
                }
            }
            report = validate(matrix, org)
            finding = report["noorinalabs-deploy"][0]
            self.assertFalse(finding["resolved"])
            # Suggestions list may be empty for very-distant names — that's fine.
            self.assertIn("suggestions", finding)

    def test_case_insensitive_resolution(self):
        """`anya kowalczyk` (lowercase) must resolve to `Anya Kowalczyk`."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org = _build_fake_org_dir(Path(tmpdir))
            matrix = {
                "noorinalabs-isnad-graph": {
                    "implementer": "anya kowalczyk",
                }
            }
            report = validate(matrix, org)
            self.assertTrue(report["noorinalabs-isnad-graph"][0]["resolved"])

    def test_empty_slot_skipped(self):
        """An empty string slot is ignored (TBD-pending placeholder)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org = _build_fake_org_dir(Path(tmpdir))
            matrix = {
                "noorinalabs-deploy": {
                    "implementer": "Bereket Tadesse",
                    "reviewer_2": "",
                }
            }
            report = validate(matrix, org)
            # Only 1 finding (reviewer_2 empty was skipped)
            self.assertEqual(len(report["noorinalabs-deploy"]), 1)


class ParentRosterFallbackTests(unittest.TestCase):
    """`noorinalabs-main` (parent) repo entries resolve via parent roster only."""

    def test_parent_repo_entry_resolves_against_parent_roster(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            org = _build_fake_org_dir(Path(tmpdir))
            matrix = {
                "noorinalabs-main": {
                    "implementer": "Nadia Khoury",
                    "reviewer": "Wanjiku Mwangi",
                }
            }
            report = validate(matrix, org)
            for f in report["noorinalabs-main"]:
                self.assertTrue(f["resolved"], f"{f['declared']} should be resolved")

    def test_empty_repo_string_treated_as_parent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            org = _build_fake_org_dir(Path(tmpdir))
            matrix = {
                "": {
                    "implementer": "Nadia Khoury",
                }
            }
            report = validate(matrix, org)
            self.assertTrue(report[""][0]["resolved"])


class MissingRosterTests(unittest.TestCase):
    """Repos with no roster dir → fall back to parent-only lookup."""

    def test_missing_repo_roster_still_resolves_org_level_names(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            org = _build_fake_org_dir(Path(tmpdir))
            matrix = {
                "noorinalabs-design-system": {  # No roster created for this repo.
                    "reviewer": "Aino Virtanen",  # Parent-org-level — should resolve.
                }
            }
            report = validate(matrix, org)
            self.assertTrue(report["noorinalabs-design-system"][0]["resolved"])

    def test_missing_repo_roster_with_only_per_repo_name_unresolved(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            org = _build_fake_org_dir(Path(tmpdir))
            matrix = {
                "noorinalabs-design-system": {
                    "implementer": "Bereket Tadesse",  # Lives in deploy roster, not DS.
                }
            }
            report = validate(matrix, org)
            # Bereket only exists in deploy roster — design-system lookup
            # combines parent + design-system rosters, not deploy.
            self.assertFalse(report["noorinalabs-design-system"][0]["resolved"])


class CrossRepoImplementerTests(unittest.TestCase):
    """#1134: a child-repo story's implementer must be on THAT repo's roster.

    Every test here FAILS against the pre-#1134 validator, which unioned the
    parent roster into every child lookup and so reported the live W27/W28
    Nurul-on-user-service pairing as fully resolved (exit 0).
    """

    def test_parent_persona_as_child_implementer_is_flagged(self):
        """The live reproducer: parent-org persona scoped to implement child work."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org = _build_fake_org_dir(Path(tmpdir))
            # "Nadia Khoury" is parent-roster-only, mirroring Nurul Hakim's
            # relationship to the user-service roster in W27/W28.
            matrix = {"noorinalabs-isnad-graph": {"implementer": "Nadia Khoury"}}
            report = validate(matrix, org)
            finding = report["noorinalabs-isnad-graph"][0]
            # Name RESOLVES (she is a real persona) — that is why the #319
            # check alone shipped this green for three waves.
            self.assertTrue(finding["resolved"])
            self.assertEqual(finding["membership"], "cross-repo")
            self.assertEqual(_print_report_to_stderr(report), 1)

    def test_repo_member_implementer_passes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            org = _build_fake_org_dir(Path(tmpdir))
            matrix = {"noorinalabs-isnad-graph": {"implementer": "Anya Kowalczyk"}}
            report = validate(matrix, org)
            finding = report["noorinalabs-isnad-graph"][0]
            self.assertEqual(finding["membership"], "member")
            self.assertEqual(_print_report_to_stderr(report), 0)

    def test_reviewer_slots_keep_parent_union(self):
        """Charter § Child-Repo Implementer Rule step 5: reviewers may be cross-team.

        Regression guard against over-applying the membership check — if this
        starts failing, the gate has broken a rule the org deliberately holds.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            org = _build_fake_org_dir(Path(tmpdir))
            matrix = {
                "noorinalabs-isnad-graph": {
                    "implementer": "Anya Kowalczyk",
                    "reviewer": "Aino Virtanen",  # parent-only
                    "reviewer_2": "Nadia Khoury",  # parent-only
                    "merge_gate_reviewer": "Wanjiku Mwangi",  # parent-only
                }
            }
            report = validate(matrix, org)
            for f in report["noorinalabs-isnad-graph"]:
                self.assertTrue(f["resolved"])
                if f["role"] != "implementer":
                    self.assertEqual(f["membership"], "n/a", f"{f['role']} must not be gated")
            self.assertEqual(_print_report_to_stderr(report), 0)

    def test_parent_repo_implementer_not_gated(self):
        """A noorinalabs-main story's implementer is a parent persona by definition."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org = _build_fake_org_dir(Path(tmpdir))
            report = validate({"noorinalabs-main": {"implementer": "Nadia Khoury"}}, org)
            self.assertEqual(report["noorinalabs-main"][0]["membership"], "n/a")
            self.assertEqual(_print_report_to_stderr(report), 0)

    def test_unresolved_name_is_not_also_reported_cross_repo(self):
        """An unknown name is a #319 failure only — not double-counted as #1134."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org = _build_fake_org_dir(Path(tmpdir))
            report = validate({"noorinalabs-isnad-graph": {"implementer": "Ghost Person"}}, org)
            finding = report["noorinalabs-isnad-graph"][0]
            self.assertFalse(finding["resolved"])
            self.assertEqual(finding["membership"], "n/a")


class UnverifiableRepoTests(unittest.TestCase):
    """A repo whose roster cannot be read must FAIL OPEN, never fail closed.

    An absent roster dir means "not cloned" (the CI case), not "nobody is a
    member". Failing closed here would red-flag every child-repo implementer
    in any environment without sibling checkouts.
    """

    def test_missing_child_roster_marks_implementer_unverified(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            org = _build_fake_org_dir(Path(tmpdir))
            # noorinalabs-design-system has no roster dir in the fixture.
            report = validate({"noorinalabs-design-system": {"implementer": "Aino Virtanen"}}, org)
            finding = report["noorinalabs-design-system"][0]
            self.assertTrue(finding["resolved"])
            self.assertEqual(finding["membership"], "unverified")
            self.assertEqual(_print_report_to_stderr(report), 0)


class OverrideTests(unittest.TestCase):
    """The escape hatch: an explicit, RECORDED roster-union override."""

    def test_override_with_rationale_passes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            org = _build_fake_org_dir(Path(tmpdir))
            matrix = {
                "noorinalabs-isnad-graph": {
                    "implementer": "Nadia Khoury",
                    "roster_union_override": {
                        "rationale": "Parent-owned drift gate wired into ig CI; "
                        "Nadia is onboarded to the ig roster in the same PR."
                    },
                }
            }
            report = validate(matrix, org)
            finding = report["noorinalabs-isnad-graph"][0]
            self.assertEqual(finding["membership"], "overridden")
            self.assertIn("drift gate", str(finding["override_rationale"]))
            self.assertEqual(_print_report_to_stderr(report), 0)

    def test_bare_true_override_is_rejected(self):
        """`true` records no reason — indistinguishable from the silent workaround."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org = _build_fake_org_dir(Path(tmpdir))
            matrix = {
                "noorinalabs-isnad-graph": {
                    "implementer": "Nadia Khoury",
                    "roster_union_override": True,
                }
            }
            report = validate(matrix, org)
            self.assertEqual(report["noorinalabs-isnad-graph"][0]["membership"], "cross-repo")
            self.assertEqual(_print_report_to_stderr(report), 1)

    def test_empty_rationale_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            org = _build_fake_org_dir(Path(tmpdir))
            matrix = {
                "noorinalabs-isnad-graph": {
                    "implementer": "Nadia Khoury",
                    "roster_union_override": {"rationale": "   "},
                }
            }
            report = validate(matrix, org)
            self.assertEqual(report["noorinalabs-isnad-graph"][0]["membership"], "cross-repo")

    def test_override_does_not_leak_into_name_findings(self):
        """The override key must not be validated as if it were a person's name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org = _build_fake_org_dir(Path(tmpdir))
            matrix = {
                "noorinalabs-isnad-graph": {
                    "implementer": "Anya Kowalczyk",
                    "roster_union_override": {"rationale": "n/a"},
                }
            }
            report = validate(matrix, org)
            roles = [f["role"] for f in report["noorinalabs-isnad-graph"]]
            self.assertEqual(roles, ["implementer"])

    def test_bare_string_override_accepted_as_rationale(self):
        self.assertEqual(_override_rationale("intended cross-repo"), "intended cross-repo")
        self.assertIsNone(_override_rationale(True))
        self.assertIsNone(_override_rationale(None))
        self.assertIsNone(_override_rationale({"approved_by": "owner"}))


class RepoOfRowTests(unittest.TestCase):
    """Scope rows carry `id` (authoritative) and a short `ref`."""

    def test_full_id_wins(self):
        self.assertEqual(
            repo_of_row({"id": "noorinalabs-user-service#204", "ref": "user-service#204"}),
            "noorinalabs-user-service",
        )

    def test_short_ref_is_expanded(self):
        self.assertEqual(repo_of_row({"ref": "user-service#204"}), "noorinalabs-user-service")

    def test_bare_main_maps_to_parent_repo(self):
        self.assertEqual(repo_of_row({"ref": "main#1134"}), "noorinalabs-main")
        self.assertEqual(repo_of_row({"id": "noorinalabs-main#1134"}), "noorinalabs-main")

    def test_unparsable_row_returns_empty(self):
        self.assertEqual(repo_of_row({"id": "not-a-ref"}), "")
        self.assertEqual(repo_of_row({}), "")


class ScopeModeTests(unittest.TestCase):
    """#1134 scope mode — read wave_{M}_scope.tier_*[] rows directly.

    Scope mode exists because the matrix is hand-transcribed: a row omitted
    from the matrix is a row the gate never sees. Reading the canonical rows
    removes that bypass.
    """

    def test_cross_repo_implementer_in_tier_row_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            org = _build_fake_org_dir(Path(tmpdir))
            scope = {
                "theme": "irrelevant",
                "tier_1_core": [
                    {
                        "id": "noorinalabs-isnad-graph#1191",
                        "ref": "isnad-graph#1191",
                        "implementer": "Nadia Khoury",  # parent-only
                        "reviewer": "Aino Virtanen",
                    }
                ],
            }
            report = validate_scope(scope, org)
            findings = report["noorinalabs-isnad-graph (isnad-graph#1191)"]
            impl = next(f for f in findings if f["role"] == "implementer")
            self.assertEqual(impl["membership"], "cross-repo")
            self.assertEqual(_print_report_to_stderr(report), 1)

    def test_per_row_override_is_scoped_to_its_own_row(self):
        """Two rows in the SAME repo: only the row carrying the override passes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org = _build_fake_org_dir(Path(tmpdir))
            scope = {
                "tier_1_core": [
                    {
                        "id": "noorinalabs-isnad-graph#1",
                        "ref": "isnad-graph#1",
                        "implementer": "Nadia Khoury",
                        "roster_union_override": {"rationale": "intended, owner-approved"},
                    },
                    {
                        "id": "noorinalabs-isnad-graph#2",
                        "ref": "isnad-graph#2",
                        "implementer": "Wanjiku Mwangi",  # no override
                    },
                ]
            }
            report = validate_scope(scope, org)
            overridden = report["noorinalabs-isnad-graph (isnad-graph#1)"][0]
            bare = report["noorinalabs-isnad-graph (isnad-graph#2)"][0]
            self.assertEqual(overridden["membership"], "overridden")
            self.assertEqual(bare["membership"], "cross-repo")
            self.assertEqual(_print_report_to_stderr(report), 1)

    def test_all_tier_arrays_are_walked(self):
        """A story hidden in tier_3 must be checked exactly like tier_1."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org = _build_fake_org_dir(Path(tmpdir))
            scope = {
                "tier_1_core": [
                    {"id": "noorinalabs-main#1", "ref": "main#1", "implementer": "Nadia Khoury"}
                ],
                "tier_3_tech_debt": [
                    {
                        "id": "noorinalabs-deploy#9",
                        "ref": "deploy#9",
                        "implementer": "Wanjiku Mwangi",  # parent-only, deploy story
                    }
                ],
            }
            report = validate_scope(scope, org)
            self.assertIn("noorinalabs-deploy (deploy#9)", report)
            self.assertEqual(report["noorinalabs-deploy (deploy#9)"][0]["membership"], "cross-repo")
            self.assertEqual(_print_report_to_stderr(report), 1)

    def test_non_tier_keys_and_null_slots_ignored(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            org = _build_fake_org_dir(Path(tmpdir))
            scope = {
                "theme": "a string, not a tier",
                "phase": 10,
                "repos_in_scope": ["noorinalabs-main"],
                "tier_1_core": [
                    {
                        "id": "noorinalabs-deploy#9",
                        "ref": "deploy#9",
                        "implementer": "Bereket Tadesse",  # deploy roster member
                        "reviewer_2": None,
                    }
                ],
            }
            report = validate_scope(scope, org)
            self.assertEqual(len(report), 1)
            findings = report["noorinalabs-deploy (deploy#9)"]
            self.assertEqual([f["role"] for f in findings], ["implementer"])
            self.assertEqual(findings[0]["membership"], "member")
            self.assertEqual(_print_report_to_stderr(report), 0)

    def test_empty_scope_produces_empty_report(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            org = _build_fake_org_dir(Path(tmpdir))
            self.assertEqual(validate_scope({"theme": "x"}, org), {})


class OrgUnionManifestTests(unittest.TestCase):
    """#1162: a reviewer drawn from a THIRD child repo must resolve.

    The parent side of the #319 union is the parent's CARD DIRECTORY (9 names),
    not the org-union MANIFEST (78 names). A reviewer who is a real persona in
    some other child repo is on neither the parent's cards nor the target
    repo's, so it was reported UNRESOLVED "(no close matches)" — hard-blocking
    /wave-scope § 12.5 and /wave-kickoff § 0b on an assignment the charter
    explicitly permits (spawn-discipline.md § Child-Repo Implementer Rule
    step 5). Live W28 instance: Nikolaos Papadopoulos / Oyunbileg Batbayar
    (cards in noorinalabs-data-acquisition) reviewing isnad-ingest-platform.

    Every test here that turns on the reviewer half FAILS against the
    pre-#1162 validator. The implementer-half guards additionally pin that the
    OBVIOUS over-broad fix — unioning the manifest into every slot — is not
    what landed: they go red under that mutation.
    """

    THIRD_CHILD_REVIEWER = "Nikolaos Papadopoulos"

    def _build_org(self, tmp: Path, *, manifest: object | None = None) -> Path:
        """Fake org dir + a third child repo + the target repo + a manifest.

        `manifest=None` writes the realistic manifest (parent cards + both
        children + the third-child reviewer). Pass an explicit value to write
        something else, or `_build_org(..., manifest=False)` for no file.
        """
        org = _build_fake_org_dir(tmp)
        # Third child repo — where the reviewer's card actually lives.
        _write_roster_card(
            org / "noorinalabs-data-acquisition" / ".claude" / "team" / "roster",
            "data_engineer_nikolaos",
            self.THIRD_CHILD_REVIEWER,
        )
        # Target child repo — cloned, so membership is decidable.
        _write_roster_card(
            org / "noorinalabs-isnad-ingest-platform" / ".claude" / "team" / "roster",
            "eng_farhan",
            "Farhan Malik",
        )
        if manifest is None:
            manifest = {
                name: f"parametrization+{name.replace(' ', '.')}@gmail.com"
                for name in (
                    "Nadia Khoury",
                    "Wanjiku Mwangi",
                    "Aino Virtanen",
                    "Anya Kowalczyk",
                    "Farhan Malik",
                    self.THIRD_CHILD_REVIEWER,
                )
            }
        if manifest is not False:
            path = org / ".claude" / "team" / "roster.json"
            path.write_text(json.dumps(manifest, indent=2))
        return org

    def test_third_child_reviewer_resolves_and_implementer_stays_gated(self):
        """The live reproducer, both halves — this is the #1162 acceptance test.

        Half 1 (the fix): the third-child reviewer resolves and is NOT
        membership-gated. Half 2 (the carve-out): the same name in the
        `implementer` slot still does not resolve, because the manifest
        deliberately does not widen the commit-capable resolution set.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            org = self._build_org(Path(tmpdir))
            reviewed = {
                "noorinalabs-isnad-ingest-platform": {
                    "implementer": "Farhan Malik",  # target-repo member
                    "reviewer": self.THIRD_CHILD_REVIEWER,
                    "merge_gate_reviewer": self.THIRD_CHILD_REVIEWER,
                }
            }
            report = validate(reviewed, org)
            findings = report["noorinalabs-isnad-ingest-platform"]
            for f in findings:
                self.assertTrue(f["resolved"], f"{f['declared']} should resolve")
            by_role = {f["role"]: f for f in findings}
            self.assertEqual(by_role["reviewer"]["membership"], "n/a")
            self.assertEqual(by_role["merge_gate_reviewer"]["membership"], "n/a")
            self.assertEqual(by_role["implementer"]["membership"], "member")
            self.assertEqual(_print_report_to_stderr(report), 0)

            # Half 2 — same org, same name, commit-capable slot.
            implemented = {
                "noorinalabs-isnad-ingest-platform": {
                    "implementer": self.THIRD_CHILD_REVIEWER,
                }
            }
            impl_report = validate(implemented, org)
            impl = impl_report["noorinalabs-isnad-ingest-platform"][0]
            self.assertFalse(impl["resolved"], "manifest must not widen the implementer slot")
            self.assertEqual(impl["membership"], "n/a")
            self.assertEqual(_print_report_to_stderr(impl_report), 1)

    def test_manifest_does_not_pass_implementer_on_uncloned_repo(self):
        """The precise loosening the carve-out prevents.

        Membership fails OPEN when the target repo's roster is unreadable (the
        CI case). If the manifest widened the implementer resolution set too, a
        manifest-only implementer on a not-cloned repo would resolve, be marked
        `unverified`, and exit 0 — silently passing exactly the assignment
        class #1134 exists to stop. It must stay an unresolved name (exit 1).
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            org = self._build_org(Path(tmpdir))
            # noorinalabs-design-system has no roster dir in the fixture.
            report = validate(
                {"noorinalabs-design-system": {"implementer": self.THIRD_CHILD_REVIEWER}}, org
            )
            finding = report["noorinalabs-design-system"][0]
            self.assertFalse(finding["resolved"])
            self.assertNotEqual(finding["membership"], "unverified")
            self.assertEqual(_print_report_to_stderr(report), 1)

    def test_manifest_widening_does_not_excuse_a_parent_only_implementer(self):
        """#1134's headline finding survives: a parent persona is still cross-repo.

        Nadia Khoury is on the parent cards AND the manifest; neither makes her
        a member of the target repo. This is the wave-28 `Nurul Hakim` /
        `Weronika Zielinska` shape, which must keep failing after #1162.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            org = self._build_org(Path(tmpdir))
            report = validate(
                {"noorinalabs-isnad-ingest-platform": {"implementer": "Nadia Khoury"}}, org
            )
            finding = report["noorinalabs-isnad-ingest-platform"][0]
            self.assertTrue(finding["resolved"])
            self.assertEqual(finding["membership"], "cross-repo")
            self.assertEqual(_print_report_to_stderr(report), 1)

    def test_scope_mode_third_child_reviewer_row_passes(self):
        """End-to-end through the path /wave-scope § 12.5 and /wave-kickoff § 0b run."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org = self._build_org(Path(tmpdir))
            scope = {
                "tier_1_core": [
                    {
                        "id": "noorinalabs-isnad-ingest-platform#140",
                        "ref": "isnad-ingest-platform#140",
                        "implementer": "Farhan Malik",
                        "reviewer": self.THIRD_CHILD_REVIEWER,
                        "merge_gate_reviewer": self.THIRD_CHILD_REVIEWER,
                    }
                ]
            }
            report = validate_scope(scope, org)
            findings = report["noorinalabs-isnad-ingest-platform (isnad-ingest-platform#140)"]
            self.assertTrue(all(f["resolved"] for f in findings))
            self.assertEqual(_print_report_to_stderr(report), 0)

    def test_unresolved_reviewer_gets_manifest_sourced_suggestion(self):
        """A typo'd reviewer name now suggests against the manifest, not "(no close matches)"."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org = self._build_org(Path(tmpdir))
            report = validate(
                {"noorinalabs-isnad-ingest-platform": {"reviewer": "Nikolas Papadopolous"}}, org
            )
            finding = report["noorinalabs-isnad-ingest-platform"][0]
            self.assertFalse(finding["resolved"])
            self.assertIn(self.THIRD_CHILD_REVIEWER, finding["suggestions"])

    def test_missing_manifest_degrades_to_the_card_union(self):
        """Fail OPEN, never closed: the manifest only ever WIDENS the review set.

        With no roster.json the validator must behave exactly as pre-#1162 —
        parent-card reviewers still resolve, the third-child reviewer does not.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            org = self._build_org(Path(tmpdir), manifest=False)
            self.assertEqual(_load_org_manifest_names(org), set())
            report = validate(
                {
                    "noorinalabs-isnad-ingest-platform": {
                        "reviewer": "Aino Virtanen",  # parent card
                        "reviewer_2": self.THIRD_CHILD_REVIEWER,  # third child only
                    }
                },
                org,
            )
            by_role = {f["role"]: f for f in report["noorinalabs-isnad-ingest-platform"]}
            self.assertTrue(by_role["reviewer"]["resolved"])
            self.assertFalse(by_role["reviewer_2"]["resolved"])

    def test_malformed_manifest_is_ignored_not_fatal(self):
        """A truncated or wrong-shaped roster.json must not crash or fail closed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org = _build_fake_org_dir(Path(tmpdir))
            manifest_path = org / ".claude" / "team" / "roster.json"
            for bad in ('{"Nadia Khoury": ', '["Nadia Khoury"]', "null"):
                manifest_path.write_text(bad)
                self.assertEqual(_load_org_manifest_names(org), set(), f"for {bad!r}")
                report = validate({"noorinalabs-isnad-graph": {"reviewer": "Aino Virtanen"}}, org)
                self.assertTrue(report["noorinalabs-isnad-graph"][0]["resolved"])

    def test_manifest_names_are_trimmed_and_non_strings_skipped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            org = self._build_org(
                Path(tmpdir),
                manifest={
                    # Persona-shaped so this test exercises TRIMMING, not the
                    # #1181 shape filter (covered separately below).
                    "  Padded Persona  ": "parametrization+Padded.Persona@gmail.com",
                    "": "parametrization+Empty.Name@gmail.com",
                },
            )
            self.assertEqual(_load_org_manifest_names(org), {"Padded Persona"})
            report = validate(
                {"noorinalabs-isnad-ingest-platform": {"reviewer": "padded persona"}}, org
            )
            self.assertTrue(report["noorinalabs-isnad-ingest-platform"][0]["resolved"])


class PersonaShapeFilterTests(unittest.TestCase):
    """#1181: manifest entries with no charter-conformant `+alias` do not resolve.

    Mirrors `OrgUnionManifestTests` fixture style. The two cases here are the
    literal acceptance criterion (`reviewer: "Annunaki"` must not resolve) and
    its sibling (the bare-principal `Steven French` mapping), plus a guard that
    the filter does NOT over-correct: a persona-shaped manifest-only name (one
    of the other 16 #1181 measured) must keep resolving.
    """

    def _build_org_with_manifest(self, tmp: Path, manifest: dict[str, str]) -> Path:
        org = _build_fake_org_dir(tmp)
        path = org / ".claude" / "team" / "roster.json"
        path.write_text(json.dumps(manifest, indent=2))
        return org

    def test_annunaki_tool_identity_does_not_resolve(self):
        """The literal #1181 acceptance criterion."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org = self._build_org_with_manifest(
                Path(tmpdir),
                {
                    "Aino Virtanen": "parametrization+Aino.Virtanen@gmail.com",
                    "Annunaki": "parametrization+Annunaki@gmail.com",
                },
            )
            self.assertNotIn("Annunaki", _load_org_manifest_names(org))
            report = validate({"noorinalabs-isnad-ingest-platform": {"reviewer": "Annunaki"}}, org)
            finding = report["noorinalabs-isnad-ingest-platform"][0]
            self.assertFalse(finding["resolved"], "Annunaki (tool identity) must not resolve")
            self.assertEqual(_print_report_to_stderr(report), 1)

    def test_bare_principal_does_not_resolve(self):
        """`Steven French` maps to the bare `parametrization@gmail.com` (no `+alias`)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org = self._build_org_with_manifest(
                Path(tmpdir),
                {
                    "Aino Virtanen": "parametrization+Aino.Virtanen@gmail.com",
                    "Steven French": "parametrization@gmail.com",
                },
            )
            self.assertNotIn("Steven French", _load_org_manifest_names(org))
            report = validate(
                {"noorinalabs-isnad-ingest-platform": {"reviewer": "Steven French"}}, org
            )
            self.assertFalse(report["noorinalabs-isnad-ingest-platform"][0]["resolved"])

    def test_persona_shaped_manifest_only_name_still_resolves(self):
        """The filter narrows exactly the non-persona entries, not every uncarded one.

        A manifest-only name that IS persona-shaped (one of #1181's other 16,
        real-looking but still uncarded anywhere) must keep resolving as a
        reviewer — #1181 does not reconcile that disposition, only the two
        definitionally-wrong entries.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            org = self._build_org_with_manifest(
                Path(tmpdir),
                {"Amara Diallo": "parametrization+Amara.Diallo@gmail.com"},
            )
            self.assertIn("Amara Diallo", _load_org_manifest_names(org))
            report = validate(
                {"noorinalabs-isnad-ingest-platform": {"reviewer": "Amara Diallo"}}, org
            )
            self.assertTrue(report["noorinalabs-isnad-ingest-platform"][0]["resolved"])

    def test_non_persona_shape_variants_excluded(self):
        """Pure unit coverage of the regex boundary, independent of `validate()`."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org = self._build_org_with_manifest(
                Path(tmpdir),
                {
                    "No Alias": "parametrization@gmail.com",
                    "No Dot": "parametrization+NoDot@gmail.com",
                    "Bot Login": "12345+octocat@users.noreply.github.com",
                    "Real Persona": "parametrization+Real.Persona@gmail.com",
                },
            )
            self.assertEqual(_load_org_manifest_names(org), {"Real Persona"})


if __name__ == "__main__":
    unittest.main()
