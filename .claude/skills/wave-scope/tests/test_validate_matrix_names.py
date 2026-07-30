"""Tests for /wave-scope validate_matrix_names roster check (#319).

The P3W7 retro surfaced an "Anya Volkov" alias in the scope matrix that
doesn't exist in any roster (canonical isnad-graph Tech Lead is "Anya
Kowalczyk"). Substitution worked in-flight but wasn't caught at scope time.
This test pins that the validator surfaces such aliases with a suggestion.

Tests use isolated tmpdir-based rosters to avoid coupling to the real
org-dir state (which changes wave-to-wave).
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from validate_matrix_names import (  # noqa: E402
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


if __name__ == "__main__":
    unittest.main()
