"""Tests for /wave-scope validate_matrix_names roster check (#319).

The P3W7 retro surfaced an "Anya Volkov" alias in the scope matrix that
doesn't exist in any roster (canonical isnad-graph Tech Lead is "Anya
Kowalczyk"). Substitution worked in-flight but wasn't caught at scope time.
This test pins that the validator surfaces such aliases with a suggestion.

Tests use isolated tmpdir-based rosters to avoid coupling to the real
org-dir state (which changes wave-to-wave).
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import validate_matrix_names  # noqa: E402
from validate_matrix_names import (  # noqa: E402
    COMMIT_CAPABLE_ROLES,
    KNOWN_ROLE_SLOTS,
    REVIEW_CLASS_ROLES,
    _load_org_manifest_names,
    _override_rationale,
    _print_report_to_stderr,
    is_role_slot_key,
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


def _report_stderr(report: dict) -> tuple[int, str]:
    """Run `_print_report_to_stderr` capturing its output (#1182).

    Returns `(exit_code, captured_stderr)` so a test can assert on the exit
    code AND on the operator-facing text in one call, instead of asserting on
    report internals and merely hoping they reach the terminal.
    """
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        code = _print_report_to_stderr(report)
    return code, buf.getvalue()


def _finding_row(err: str, role: str) -> str:
    """Return the single per-finding line for `role` from captured stderr (#1182).

    Whole-stream `assertIn` is not enough here: the remediation TRAILERS repeat
    the same phrases the per-row line uses, so a stream-level assertion stays
    green with the row line deleted. Tests that care about what the row says
    must assert against the row.
    """
    rows = [ln for ln in err.splitlines() if ln.strip().startswith(f"- {role}:")]
    if len(rows) != 1:
        raise AssertionError(f"expected exactly 1 {role!r} finding row, got {len(rows)}:\n{err}")
    return rows[0]


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


class UnclassifiedRoleSlotTests(unittest.TestCase):
    """#1180: an unclassified slot key takes the STRICT path and fails loudly.

    Pre-#1180 the seam was `combined if role in COMMIT_CAPABLE_ROLES else
    review_combined` — an allowlist of the NARROW side, so an unclassified role
    inherited BOTH review-class loosenings: the org-union manifest widened its
    resolution set, and the #1134 membership check was skipped. Measured on the
    pre-fix code, a matrix of `co_implementer` / `pair_implementer` / `fixer`
    reported "all 3 names resolved", exit 0.

    Every test here goes RED against the pre-#1180 module.
    """

    THIRD_CHILD_REVIEWER = "Nikolaos Papadopoulos"
    # A commit-capable-by-meaning slot key nobody has classified — the #1180
    # example. It would have to COMMIT in the target repo.
    UNCLASSIFIED_SLOT = "co_implementer"

    def _build_org(self, tmp: Path) -> Path:
        """Fake org: parent cards, two child rosters, a third-child reviewer, a manifest."""
        org = _build_fake_org_dir(tmp)
        _write_roster_card(
            org / "noorinalabs-data-acquisition" / ".claude" / "team" / "roster",
            "data_engineer_nikolaos",
            self.THIRD_CHILD_REVIEWER,
        )
        manifest = {
            name: f"parametrization+{name.replace(' ', '.')}@gmail.com"
            for name in (
                "Nadia Khoury",
                "Wanjiku Mwangi",
                "Aino Virtanen",
                "Anya Kowalczyk",
                self.THIRD_CHILD_REVIEWER,
            )
        }
        (org / ".claude" / "team" / "roster.json").write_text(json.dumps(manifest, indent=2))
        return org

    # ---- the seam itself -------------------------------------------------

    def test_unclassified_slot_resolves_against_the_narrow_set(self):
        """The literal acceptance criterion: manifest-only name in an unclassified slot → exit 1.

        `Nikolaos Papadopoulos` is manifest-resolvable and is a real persona in a
        THIRD child repo, so he resolves in a `reviewer` slot (#1162). In an
        unclassified slot he must NOT — the manifest widens review-class only.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            org = self._build_org(Path(tmpdir))
            matrix = {
                "noorinalabs-isnad-graph": {self.UNCLASSIFIED_SLOT: self.THIRD_CHILD_REVIEWER}
            }
            report = validate(matrix, org)
            finding = report["noorinalabs-isnad-graph"][0]
            self.assertFalse(
                finding["resolved"],
                "manifest must not widen an unclassified slot's resolution set",
            )
            self.assertEqual(_print_report_to_stderr(report), 1)

    def test_same_name_still_resolves_in_a_review_slot(self):
        """The paired control: only the SLOT CLASS differs between this and the test above.

        Without this pair, `test_unclassified_slot_resolves_against_the_narrow_set`
        would also pass if the manifest had simply stopped being loaded at all.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            org = self._build_org(Path(tmpdir))
            report = validate(
                {"noorinalabs-isnad-graph": {"reviewer": self.THIRD_CHILD_REVIEWER}}, org
            )
            self.assertTrue(report["noorinalabs-isnad-graph"][0]["resolved"])

    def test_unclassified_slot_gets_the_membership_check(self):
        """The second loosening: #1134 membership must apply to an unclassified slot.

        `Nadia Khoury` is on the parent cards, so she RESOLVES on the narrow set
        too — the resolution seam alone would let this pass. She is not on the
        isnad-graph roster, and a `co_implementer` commits there.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            org = self._build_org(Path(tmpdir))
            report = validate(
                {"noorinalabs-isnad-graph": {self.UNCLASSIFIED_SLOT: "Nadia Khoury"}}, org
            )
            finding = report["noorinalabs-isnad-graph"][0]
            self.assertTrue(finding["resolved"], "parent-card name resolves on the narrow set")
            self.assertEqual(finding["membership"], "cross-repo")
            self.assertEqual(_print_report_to_stderr(report), 1)

    def test_unclassified_slot_fails_even_when_fully_valid(self):
        """A resolvable, repo-member name in an unclassified slot is STILL exit 1.

        Neither the #319 nor the #1134 class fires here — only the #1180 slot
        class does. This is the test that pins the classification failure as its
        own signal rather than a side effect of a name miss.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            org = self._build_org(Path(tmpdir))
            report = validate(
                {"noorinalabs-isnad-graph": {self.UNCLASSIFIED_SLOT: "Anya Kowalczyk"}}, org
            )
            finding = report["noorinalabs-isnad-graph"][0]
            self.assertTrue(finding["resolved"])
            self.assertEqual(finding["membership"], "member")
            self.assertEqual(finding["slot_class"], "unclassified")
            self.assertEqual(_print_report_to_stderr(report), 1)

    def test_known_slots_are_marked_known(self):
        """All four live slots stay `slot_class="known"` — no false unclassified."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org = self._build_org(Path(tmpdir))
            matrix = {
                "noorinalabs-isnad-graph": {
                    "implementer": "Anya Kowalczyk",
                    "reviewer": "Aino Virtanen",
                    "reviewer_2": "Nadia Khoury",
                    "merge_gate_reviewer": "Wanjiku Mwangi",
                }
            }
            report = validate(matrix, org)
            for f in report["noorinalabs-isnad-graph"]:
                self.assertEqual(f["slot_class"], "known", f"{f['role']} must be classified")
            self.assertEqual(_print_report_to_stderr(report), 0)

    def test_every_review_class_role_keeps_the_wide_set(self):
        """Regression anchor for the inversion: drop a name from REVIEW_CLASS_ROLES and this reds.

        Each review slot is checked INDEPENDENTLY with a manifest-only name, so
        losing any single member of the frozenset is caught, not just losing all
        three (which a combined-matrix assertion would also catch).
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            org = self._build_org(Path(tmpdir))
            for role in ("reviewer", "reviewer_2", "merge_gate_reviewer"):
                with self.subTest(role=role):
                    report = validate(
                        {"noorinalabs-isnad-graph": {role: self.THIRD_CHILD_REVIEWER}}, org
                    )
                    finding = report["noorinalabs-isnad-graph"][0]
                    self.assertTrue(finding["resolved"], f"{role} must keep the manifest union")
                    self.assertEqual(finding["membership"], "n/a", f"{role} must not be gated")
                    self.assertEqual(finding["slot_class"], "known")
                    self.assertEqual(_print_report_to_stderr(report), 0)

    def test_role_classes_are_disjoint(self):
        """A slot cannot be both commit-capable and review-class — the seam would be ambiguous."""
        self.assertEqual(COMMIT_CAPABLE_ROLES & REVIEW_CLASS_ROLES, frozenset())
        self.assertEqual(KNOWN_ROLE_SLOTS, COMMIT_CAPABLE_ROLES | REVIEW_CLASS_ROLES)


class SlotKeyRecognitionTests(unittest.TestCase):
    """#1180: `is_role_slot_key` — which scope-row keys name a PERSON.

    Scope rows mix role slots with free-form metadata, so scope mode cannot
    treat every string key as a person. The recogniser admits the known slots
    plus any agentive-shaped key not explicitly denied.
    """

    # Every non-role key measured across all 293 rows of every `wave_*_scope`
    # in cross-repo-status.json (2026-08-02). Snapshotted rather than read from
    # the live file so the guard cannot rot when the wave data changes.
    LIVE_METADATA_KEYS = (
        "batch",
        "blocked_by",
        "blocked_on",
        "blocks",
        "blocks_next_wave_scope",
        "bundle",
        "coupled_with",
        "follow_on_to",
        "found_by",
        "id",
        "merged_sha",
        "note",
        "open_risk",
        "pair_with",
        "pr",
        "pre_kickoff_blocker",
        "priority",
        "reassigned_from",
        "ref",
        "role",
        "scope_note",
        "sequence",
        "slate_note",
        "spawn",
        "status",
    )

    def test_known_slots_are_recognised(self):
        for key in sorted(KNOWN_ROLE_SLOTS):
            with self.subTest(key=key):
                self.assertTrue(is_role_slot_key(key))

    def test_no_live_metadata_key_is_mistaken_for_a_slot(self):
        """Zero false positives over the measured live key census.

        `pre_kickoff_blocker` IS agentive-shaped (`_blocker`) and is caught only
        by the `NON_ROLE_ROW_KEYS` denylist — delete that branch and this reds.
        """
        for key in self.LIVE_METADATA_KEYS:
            with self.subTest(key=key):
                self.assertFalse(is_role_slot_key(key), f"{key} is metadata, not a person slot")

    def test_unclassified_agentive_keys_are_recognised(self):
        """The #1180 examples plus plausible neighbours — all must be SEEN, then flagged."""
        for key in ("co_implementer", "pair_implementer", "fixer", "author", "owner", "reviewer_3"):
            with self.subTest(key=key):
                self.assertTrue(is_role_slot_key(key))

    def test_override_key_is_not_a_slot(self):
        """`roster_union_override` is the #1134 escape hatch, not a person's name."""
        self.assertFalse(is_role_slot_key("roster_union_override"))

    def test_recognition_is_case_and_whitespace_insensitive(self):
        self.assertTrue(is_role_slot_key("  Implementer  "))
        self.assertFalse(is_role_slot_key("  Pre_Kickoff_Blocker  "))


class ScopeModeSlotDiscoveryTests(unittest.TestCase):
    """#1180: scope mode must not silently SKIP an unrecognised slot key.

    Pre-fix, `validate_scope` iterated a hardcoded
    `("implementer", "reviewer", "reviewer_2", "merge_gate_reviewer")` tuple —
    a third place a role had to be listed. Measured on the pre-fix code, the
    3-slot row below reported "all 2 names resolved", exit 0: the third slot was
    never looked at, so neither the resolution seam nor the membership check
    could have caught it.
    """

    def _build_org(self, tmp: Path) -> Path:
        return _build_fake_org_dir(tmp)

    def _row(self, **extra: object) -> dict[str, object]:
        row: dict[str, object] = {
            "id": "noorinalabs-isnad-graph#9999",
            "ref": "isnad-graph#9999",
            "priority": "P1",
            "implementer": "Anya Kowalczyk",
            "reviewer": "Aino Virtanen",
        }
        row.update(extra)
        return row

    def test_unrecognised_slot_key_is_not_skipped(self):
        """The reproducer: 3 slots in, 3 findings out, exit 1 (was 2 findings, exit 0)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org = self._build_org(Path(tmpdir))
            scope = {"tier_1_core": [self._row(co_implementer="Nadia Khoury")]}
            report = validate_scope(scope, org)
            findings = report["noorinalabs-isnad-graph (isnad-graph#9999)"]
            roles = sorted(f["role"] for f in findings)
            self.assertEqual(roles, ["co_implementer", "implementer", "reviewer"])
            extra = next(f for f in findings if f["role"] == "co_implementer")
            self.assertEqual(extra["slot_class"], "unclassified")
            self.assertEqual(_print_report_to_stderr(report), 1)

    def test_metadata_keys_are_still_ignored_in_scope_mode(self):
        """Walking the row must not start validating `note` / `found_by` as names.

        Weaken `is_role_slot_key` to `return True` and this reds — the guard that
        the widened discovery did not become "every string key is a person".
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            org = self._build_org(Path(tmpdir))
            row = self._row(
                note="a long prose annotation about sequencing",
                found_by="Weronika Zielinska (PR #1143 adversarial pass)",
                reassigned_from="Jean-Claude Habimana (da-roster)",
                blocked_on="noorinalabs-main#870",
                status="completed",
                pre_kickoff_blocker="yes",
            )
            report = validate_scope({"tier_1_core": [row]}, org)
            findings = report["noorinalabs-isnad-graph (isnad-graph#9999)"]
            self.assertEqual(sorted(f["role"] for f in findings), ["implementer", "reviewer"])
            self.assertEqual(_print_report_to_stderr(report), 0)

    def test_scope_mode_covers_every_known_slot(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            org = self._build_org(Path(tmpdir))
            row = self._row(reviewer_2="Nadia Khoury", merge_gate_reviewer="Wanjiku Mwangi")
            report = validate_scope({"tier_1_core": [row]}, org)
            findings = report["noorinalabs-isnad-graph (isnad-graph#9999)"]
            self.assertEqual(sorted(f["role"] for f in findings), sorted(KNOWN_ROLE_SLOTS))
            self.assertEqual(_print_report_to_stderr(report), 0)

    def test_scope_mode_slot_list_is_driven_by_the_frozensets(self):
        """Single source of truth: classifying a role reaches scope mode with no second edit.

        `co_lead` is deliberately NOT agentive-shaped, so the only way scope mode
        can see it is via `KNOWN_ROLE_SLOTS`. Under the old hardcoded tuple this
        row's third slot stayed invisible no matter what the frozensets said.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            org = self._build_org(Path(tmpdir))
            self.assertFalse(is_role_slot_key("co_lead"), "fixture premise: not agentive-shaped")
            scope = {"tier_1_core": [self._row(co_lead="Aino Virtanen")]}

            before = validate_scope(scope, org)["noorinalabs-isnad-graph (isnad-graph#9999)"]
            self.assertNotIn("co_lead", [f["role"] for f in before])

            widened = REVIEW_CLASS_ROLES | {"co_lead"}
            with unittest.mock.patch.multiple(
                validate_matrix_names,
                REVIEW_CLASS_ROLES=widened,
                KNOWN_ROLE_SLOTS=COMMIT_CAPABLE_ROLES | widened,
            ):
                after = validate_scope(scope, org)["noorinalabs-isnad-graph (isnad-graph#9999)"]
                entry = next(f for f in after if f["role"] == "co_lead")
                self.assertEqual(entry["slot_class"], "known")
                self.assertTrue(entry["resolved"])

    def test_override_key_still_applies_in_scope_mode(self):
        """The widened row walk must not swallow or re-validate the override key."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org = self._build_org(Path(tmpdir))
            row = self._row(
                implementer="Nadia Khoury",  # parent-only → cross-repo without the override
                roster_union_override={"rationale": "intended, owner-approved"},
            )
            report = validate_scope({"tier_1_core": [row]}, org)
            findings = report["noorinalabs-isnad-graph (isnad-graph#9999)"]
            self.assertNotIn("roster_union_override", [f["role"] for f in findings])
            impl = next(f for f in findings if f["role"] == "implementer")
            self.assertEqual(impl["membership"], "overridden")
            self.assertEqual(_print_report_to_stderr(report), 0)


class ManifestSourcedSuggestionTests(unittest.TestCase):
    """#1182: never claim "(no close matches)" about a name held in the same frame.

    Symptom, measured against the real org roster with
    `noorinalabs-user-service` deliberately not cloned:

        - implementer: 'Anya Kowalczyk'  ->  suggestions: (no close matches)
          reviewer     resolved=True

    `Anya Kowalczyk` is an exact key of the `org_manifest` set `validate()` had
    already loaded, so the assertion was disprovable from a local; and the same
    name resolved one slot away, leaving the operator unable to tell whether the
    persona exists. The trailer then pointed at recording an
    `implementer_substitution` — changing a CORRECT assignment — when the real
    remedy is `--fetch-missing` or cloning the repo.

    The fix is MESSAGE-ONLY. `test_1182_message_change_is_semantically_inert`
    is the load-bearing guard: widening the RESOLUTION set instead of the
    SUGGESTION set flips this exact row to `resolved=True membership=unverified`,
    exit 0 — the silent pass #1134 exists to stop.
    """

    # In the manifest and on a THIRD child's roster; on neither the parent cards
    # nor the target repo's, so unresolved for a commit-capable slot.
    ORG_PERSONA = "Nikolaos Papadopoulos"
    # `_build_fake_org_dir` creates no design-system dir at all → roster
    # unreadable → membership undecidable. This is the "not cloned" case.
    UNCLONED_REPO = "noorinalabs-design-system"
    # Created WITH a roster by `_build_fake_org_dir` (Bereket Tadesse, Lucas
    # Ferreira) → membership decidable. The discriminator for the second conjunct.
    CLONED_REPO = "noorinalabs-deploy"

    def _build_org(self, tmp: Path) -> Path:
        org = _build_fake_org_dir(tmp)
        _write_roster_card(
            org / "noorinalabs-data-acquisition" / ".claude" / "team" / "roster",
            "data_engineer_nikolaos",
            self.ORG_PERSONA,
        )
        manifest = {
            name: f"parametrization+{name.replace(' ', '.')}@gmail.com"
            for name in ("Nadia Khoury", "Anya Kowalczyk", self.ORG_PERSONA)
        }
        (org / ".claude" / "team" / "roster.json").write_text(json.dumps(manifest, indent=2))
        return org

    def test_no_close_matches_is_not_claimed_about_a_manifest_name(self):
        """Bullet 1: the report may not deny holding a name it holds.

        Also pins problem 2 — the SAME name in the SAME run resolves in the
        review-class slot, which is what made the old output unreadable.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            org = self._build_org(Path(tmpdir))
            self.assertIn(self.ORG_PERSONA, _load_org_manifest_names(org), "fixture premise")
            report = validate(
                {
                    self.UNCLONED_REPO: {
                        "implementer": self.ORG_PERSONA,
                        "reviewer": self.ORG_PERSONA,
                    }
                },
                org,
            )
            by_role = {f["role"]: f for f in report[self.UNCLONED_REPO]}
            self.assertFalse(by_role["implementer"]["resolved"])
            self.assertTrue(by_role["reviewer"]["resolved"], "the asymmetry being explained")
            # Sourced from `review_combined`: the manifest is now visible here.
            self.assertIn(self.ORG_PERSONA, by_role["implementer"]["suggestions"])
            code, err = _report_stderr(report)
            self.assertEqual(code, 1)
            self.assertNotIn("(no close matches)", err)
            # Assert on the ROW, not on the whole stream: the trailer paragraph
            # also contains "KNOWN org persona", so a whole-stream assertion
            # passes even with the per-row line deleted (measured — that
            # mutation SURVIVED the first draft of this test).
            row = _finding_row(err, "implementer")
            self.assertIn("KNOWN org persona", row)
            # And it must not echo the declared name back as its own suggestion.
            self.assertNotIn("suggestions:", row)

    def test_uncloned_org_persona_is_steered_to_fetch_missing_not_substitution(self):
        """Bullet 2: the remediation must not point at changing a correct assignment."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org = self._build_org(Path(tmpdir))
            report = validate({self.UNCLONED_REPO: {"implementer": self.ORG_PERSONA}}, org)
            finding = report[self.UNCLONED_REPO][0]
            self.assertEqual(finding["unresolved_reason"], "org-persona-unreadable-roster")
            code, err = _report_stderr(report)
            self.assertEqual(code, 1)
            self.assertIn("--fetch-missing", err)
            self.assertIn("clone the repo", err)
            self.assertNotIn("implementer_substitutions", err)

    def test_1182_message_change_is_semantically_inert(self):
        """THE guard: #1182 added advisory keys and nothing else.

        Strips the two advisory keys and asserts the remaining entry is
        byte-identical to the pre-#1182 shape, with exit 1. A future
        "improvement" that widens the RESOLUTION set to fix the message reds
        here on `resolved`, on `membership`, and on the exit code at once.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            org = self._build_org(Path(tmpdir))
            report = validate({self.UNCLONED_REPO: {"implementer": self.ORG_PERSONA}}, org)
            finding = dict(report[self.UNCLONED_REPO][0])
            for advisory_key in ("suggestions", "unresolved_reason"):
                self.assertIn(advisory_key, finding, "fixture premise: advisory key present")
                finding.pop(advisory_key)
            self.assertEqual(
                finding,
                {
                    "role": "implementer",
                    "declared": self.ORG_PERSONA,
                    "resolved": False,
                    "membership": "n/a",
                    "slot_class": "known",
                },
            )
            self.assertEqual(_report_stderr(report)[0], 1)

    def test_manifest_persona_on_a_CLONED_repo_still_gets_substitution_guidance(self):
        """The `not membership_decidable` conjunct is load-bearing.

        Same name, same manifest — but the target roster IS readable, so this is
        a genuine wrong-assignment and the substitution guidance is correct.
        Drop the conjunct and this reds on the `--fetch-missing` assertion.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            org = self._build_org(Path(tmpdir))
            report = validate({self.CLONED_REPO: {"implementer": self.ORG_PERSONA}}, org)
            finding = report[self.CLONED_REPO][0]
            self.assertFalse(finding["resolved"])
            self.assertEqual(finding["unresolved_reason"], "unknown-name")
            code, err = _report_stderr(report)
            self.assertEqual(code, 1)
            self.assertIn("implementer_substitutions", err)
            self.assertNotIn("--fetch-missing", err)

    def test_genuine_typo_on_an_uncloned_repo_still_reports_unknown_name(self):
        """A misspelling is NOT the environment gap — but it still gets a real suggestion.

        This is the case where widening the SUGGESTION source pays off without
        the new diagnostic: `combined` had nothing close, so the operator was
        told "(no close matches)" for a one-character typo of a real persona.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            org = self._build_org(Path(tmpdir))
            report = validate({self.UNCLONED_REPO: {"implementer": "Nikolas Papadopolous"}}, org)
            finding = report[self.UNCLONED_REPO][0]
            self.assertEqual(finding["unresolved_reason"], "unknown-name")
            self.assertIn(self.ORG_PERSONA, finding["suggestions"])
            code, err = _report_stderr(report)
            self.assertEqual(code, 1)
            self.assertIn(f"suggestions: {self.ORG_PERSONA}", err)
            self.assertIn("implementer_substitutions", err)

    def test_both_remediations_print_when_both_classes_are_present(self):
        """The two trailers are independent, not mutually exclusive."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org = self._build_org(Path(tmpdir))
            report = validate(
                {
                    self.UNCLONED_REPO: {"implementer": self.ORG_PERSONA},
                    self.CLONED_REPO: {"implementer": "Totally Unknown"},
                },
                org,
            )
            code, err = _report_stderr(report)
            self.assertEqual(code, 1)
            self.assertIn("--fetch-missing", err)
            self.assertIn("implementer_substitutions", err)
            self.assertIn("2/2 names UNRESOLVED", err)

    def test_scope_mode_carries_the_diagnostic_end_to_end(self):
        """The path /wave-scope § 12.5 and /wave-kickoff § 0b actually run."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org = self._build_org(Path(tmpdir))
            scope = {
                "tier_1_core": [
                    {
                        "id": f"{self.UNCLONED_REPO}#77",
                        "ref": "design-system#77",
                        "implementer": self.ORG_PERSONA,
                        "reviewer": "Nadia Khoury",
                    }
                ]
            }
            report = validate_scope(scope, org)
            findings = report[f"{self.UNCLONED_REPO} (design-system#77)"]
            impl = next(f for f in findings if f["role"] == "implementer")
            self.assertFalse(impl["resolved"])
            self.assertEqual(impl["unresolved_reason"], "org-persona-unreadable-roster")
            code, err = _report_stderr(report)
            self.assertEqual(code, 1)
            self.assertIn("--fetch-missing", err)

    def test_resolved_rows_carry_no_unresolved_reason(self):
        """The key exists only where it means something."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org = self._build_org(Path(tmpdir))
            report = validate({"noorinalabs-isnad-graph": {"implementer": "Anya Kowalczyk"}}, org)
            finding = report["noorinalabs-isnad-graph"][0]
            self.assertTrue(finding["resolved"])
            self.assertNotIn("unresolved_reason", finding)
            self.assertEqual(_report_stderr(report)[0], 0)


if __name__ == "__main__":
    unittest.main()
