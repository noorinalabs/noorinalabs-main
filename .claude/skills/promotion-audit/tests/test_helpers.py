#!/usr/bin/env python3
"""Unit tests for promotion-audit helpers.

Covers parsers, signal counters, and classifiers. Designed to run with
stdlib unittest (no pytest dependency). The smoke test lives in
`test_smoke.py` and exercises the full pipeline against current repo
state — this file keeps each unit isolated.
"""

from __future__ import annotations

import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

import helpers as h  # noqa: E402

# ---------------------------------------------------------------------------
# Frontmatter parsing
# ---------------------------------------------------------------------------


class ParseFrontmatterTests(unittest.TestCase):
    def test_basic_scalars(self) -> None:
        text = textwrap.dedent(
            """\
            ---
            name: Foo
            type: feedback
            status: active
            ---
            body here
            """
        )
        fm, body = h.parse_frontmatter(text)
        self.assertEqual(fm["name"], "Foo")
        self.assertEqual(fm["type"], "feedback")
        self.assertEqual(fm["status"], "active")
        self.assertIn("body here", body)

    def test_quoted_string(self) -> None:
        """NEG: quotes must be stripped; embedded colons preserved."""
        text = textwrap.dedent(
            """\
            ---
            superseded_by: "charter:hooks.md § Foo"
            ---
            """
        )
        fm, _ = h.parse_frontmatter(text)
        self.assertEqual(fm["superseded_by"], "charter:hooks.md § Foo")

    def test_inline_list(self) -> None:
        text = textwrap.dedent(
            """\
            ---
            referenced_in_retros: ['W7', 'W8', 'P2W9']
            ---
            """
        )
        fm, _ = h.parse_frontmatter(text)
        self.assertEqual(fm["referenced_in_retros"], ["W7", "W8", "P2W9"])

    def test_empty_list(self) -> None:
        text = "---\nreferenced_in_retros: []\n---\n"
        fm, _ = h.parse_frontmatter(text)
        self.assertEqual(fm["referenced_in_retros"], [])

    def test_nested_threshold(self) -> None:
        text = textwrap.dedent(
            """\
            ---
            promotion_threshold:
              retro_citations: 3
              skill_invocations: 5
            ---
            """
        )
        fm, _ = h.parse_frontmatter(text)
        self.assertEqual(fm["promotion_threshold"]["retro_citations"], 3)
        self.assertEqual(fm["promotion_threshold"]["skill_invocations"], 5)

    def test_no_frontmatter(self) -> None:
        """NEG: a doc without frontmatter returns ({}, whole-text)."""
        text = "# Just markdown\n\ncontent"
        fm, body = h.parse_frontmatter(text)
        self.assertEqual(fm, {})
        self.assertEqual(body, text)

    def test_bool_coercion(self) -> None:
        text = "---\nrequires_decision: true\n---\n"
        fm, _ = h.parse_frontmatter(text)
        self.assertIs(fm["requires_decision"], True)


# ---------------------------------------------------------------------------
# Memory reading
# ---------------------------------------------------------------------------


def _write_memory(dir_: str, name: str, content: str) -> str:
    path = os.path.join(dir_, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


class ReadMemoryTests(unittest.TestCase):
    def test_promotion_eligible_memory(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            _write_memory(
                d,
                "feedback_test.md",
                textwrap.dedent(
                    """\
                    ---
                    name: Test rule
                    description: Testing
                    type: feedback
                    promotion_target: charter
                    promotion_threshold:
                      retro_citations: 3
                    referenced_in_retros: ['W7', 'W8', 'W9']
                    status: active
                    ---
                    body
                    """
                ),
            )
            mems = h.read_all_memories(d)
            self.assertEqual(len(mems), 1)
            m = mems[0]
            self.assertEqual(m.promotion_target, "charter")
            self.assertEqual(m.promotion_threshold["retro_citations"], 3)
            self.assertEqual(len(m.referenced_in_retros), 3)
            self.assertEqual(m.status, "active")

    def test_memory_index_and_handoff_excluded(self) -> None:
        """NEG: MEMORY.md and session_handoff.md must be skipped."""
        with tempfile.TemporaryDirectory() as d:
            _write_memory(d, "MEMORY.md", "# index\n")
            _write_memory(d, "session_handoff.md", "---\nname: handoff\n---\n")
            _write_memory(
                d,
                "project_real.md",
                "---\nname: Real\npromotion_target: none\nstatus: active\n---\n",
            )
            mems = h.read_all_memories(d)
            self.assertEqual(len(mems), 1)
            self.assertEqual(mems[0].filename, "project_real.md")

    def test_deterministic_sort_order(self) -> None:
        """Memories must come back in sorted-filename order for determinism."""
        with tempfile.TemporaryDirectory() as d:
            for n in ("project_z.md", "project_a.md", "project_m.md"):
                _write_memory(d, n, f"---\nname: {n}\npromotion_target: none\n---\n")
            mems = h.read_all_memories(d)
            self.assertEqual(
                [m.filename for m in mems],
                ["project_a.md", "project_m.md", "project_z.md"],
            )


# ---------------------------------------------------------------------------
# Charter section reading
# ---------------------------------------------------------------------------


class ReadCharterSectionsTests(unittest.TestCase):
    def test_tagged_section_detected(self) -> None:
        text = textwrap.dedent(
            """\
            # Title

            ## Non-procedural intro

            No marker here.

            ## Procedural step-by-step <!-- promotion-target: skill -->

            1. Do A
            2. Do B
            3. Do C

            ## Declared none <!-- promotion-target: none -->

            nothing to promote.
            """
        )
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write(text)
            path = f.name
        try:
            sections = h.read_charter_sections(path)
            self.assertEqual(len(sections), 2)
            headings = [s.heading for s in sections]
            self.assertIn("Procedural step-by-step", headings)
            self.assertIn("Declared none", headings)
            proc = [s for s in sections if s.heading == "Procedural step-by-step"][0]
            self.assertEqual(proc.promotion_target, "skill")
            self.assertIn("Do A", proc.body)
        finally:
            os.unlink(path)

    def test_untagged_sections_skipped(self) -> None:
        """NEG: sections without a marker must not appear."""
        text = "## Untagged\n\nThis has steps\n1. step\n2. step\n3. step\n"
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write(text)
            path = f.name
        try:
            self.assertEqual(h.read_charter_sections(path), [])
        finally:
            os.unlink(path)

    def test_promoted_to_backref_detected(self) -> None:
        text = textwrap.dedent(
            """\
            ## Already done <!-- promotion-target: skill -->

            <!-- promoted-to: skills/my-skill -->

            body
            """
        )
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write(text)
            path = f.name
        try:
            sections = h.read_charter_sections(path)
            self.assertEqual(len(sections), 1)
            self.assertEqual(sections[0].promoted_to, "skills/my-skill")
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Retro citation counting
# ---------------------------------------------------------------------------


class CountRetroCitationsTests(unittest.TestCase):
    def _mem(self, name: str = "Some rule", filename: str = "feedback_x.md") -> h.Memory:
        return h.Memory(
            path=f"/fake/{filename}",
            name=name,
            description="",
            type_="feedback",
            promotion_target="charter",
            promotion_threshold={"retro_citations": 3, "skill_invocations": 5},
            referenced_in_retros=(),
            status="active",
            superseded_by="",
            supersedes="",
            requires_decision=False,
            body="",
        )

    def test_count_from_feedback_log(self) -> None:
        log = "we cited Some rule here\nand feedback_x.md there\nand Some rule again"
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write(log)
            path = f.name
        try:
            n = h.count_retro_citations(self._mem(), path)
            # by_title=2, by_file=1, frontmatter_floor=0 -> max = 2
            self.assertEqual(n, 2)
        finally:
            os.unlink(path)

    def test_counts_include_per_phase_archives(self) -> None:
        """Citations split across the live log and archive/ files are summed (#964).

        Closed-phase entries move byte-for-byte to archive/feedback_log_*.md at
        phase close; the count must scan live + archives or historical citations
        vanish from the promotion pipeline.
        """
        with tempfile.TemporaryDirectory() as d:
            live = os.path.join(d, "feedback_log.md")
            with open(live, "w", encoding="utf-8") as f:
                f.write("current phase cites Some rule once\n")
            arch = os.path.join(d, "archive")
            os.makedirs(arch)
            with open(os.path.join(arch, "feedback_log_phase-3.md"), "w", encoding="utf-8") as f:
                f.write("old retro cites Some rule and Some rule again\n")
            with open(os.path.join(arch, "trust_matrix_phase-3.md"), "w", encoding="utf-8") as f:
                f.write("Some rule mentioned here must NOT count (wrong file family)\n")
            # by_title = 1 (live) + 2 (feedback_log archive) = 3; trust_matrix archive ignored
            self.assertEqual(h.count_retro_citations(self._mem(), live), 3)

    def test_frontmatter_floor_applies(self) -> None:
        """NEG: if the log has zero hits but frontmatter lists retros, floor kicks in."""
        log = "no mentions"
        mem = h.Memory(
            path="/fake/feedback_x.md",
            name="Some rule",
            description="",
            type_="feedback",
            promotion_target="charter",
            promotion_threshold={"retro_citations": 3, "skill_invocations": 5},
            referenced_in_retros=("W7", "W8", "W9"),
            status="active",
            superseded_by="",
            supersedes="",
            requires_decision=False,
            body="",
        )
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write(log)
            path = f.name
        try:
            self.assertEqual(h.count_retro_citations(mem, path), 3)
        finally:
            os.unlink(path)

    def test_missing_log_falls_back_to_frontmatter(self) -> None:
        """NEG: nonexistent feedback log must not crash."""
        mem = self._mem()
        mem = h.Memory(
            path=mem.path,
            name=mem.name,
            description=mem.description,
            type_=mem.type_,
            promotion_target=mem.promotion_target,
            promotion_threshold=mem.promotion_threshold,
            referenced_in_retros=("W9",),
            status=mem.status,
            superseded_by=mem.superseded_by,
            supersedes=mem.supersedes,
            requires_decision=mem.requires_decision,
            body=mem.body,
        )
        self.assertEqual(h.count_retro_citations(mem, "/nonexistent"), 1)


# ---------------------------------------------------------------------------
# Already-promoted detection
# ---------------------------------------------------------------------------


class FindAlreadyPromotedTests(unittest.TestCase):
    def test_detects_hook15_provenance(self) -> None:
        """POS: the canonical worked example from PR #153."""
        charter = textwrap.dedent(
            """\
            ## Hook 15: Enforce Librarian Consulted

            - **What it automates:** blocks edits
            - **Promotion provenance:** First end-to-end execution of the
              memory -> charter -> hook promotion pattern. Rule lived in
              CLAUDE.md § Ontology; first instance cites
              feedback_enforcement_hierarchy.md. Skill wrapper was
              /ontology-librarian.
            """
        )
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write(charter)
            path = f.name
        try:
            refs = h.find_already_promoted(path)
            self.assertIn("CLAUDE.md § Ontology", refs)
            self.assertIn("feedback_enforcement_hierarchy.md", refs)
            self.assertIn("/ontology-librarian", refs)
        finally:
            os.unlink(path)

    def test_no_provenance_blocks_returns_empty(self) -> None:
        """NEG: charter without provenance blocks returns empty set."""
        charter = "## Hook 1: Foo\n\n- just a hook\n"
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write(charter)
            path = f.name
        try:
            self.assertEqual(h.find_already_promoted(path), set())
        finally:
            os.unlink(path)

    def test_forward_reference_excluded(self) -> None:
        """NEG: `/name` inside a forward-reference phrase must not be
        marked as already-promoted. This is the specific false-positive
        caught during the first real audit run: Hook 15's provenance
        block references \"the future /promotion-audit skill design\"
        as a cross-reference; that is NOT a promotion claim."""
        charter = (
            "## Hook 15: Foo\n\n"
            "- **Promotion provenance:** Rule lived in CLAUDE.md \u00a7 Ontology. "
            "Worked example referenced by the future `/promotion-audit` skill design.\n"
        )
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write(charter)
            path = f.name
        try:
            refs = h.find_already_promoted(path)
            self.assertIn("CLAUDE.md \u00a7 Ontology", refs)
            self.assertNotIn(
                "/promotion-audit",
                refs,
                msg="forward-referenced skill must not appear in already-promoted set",
            )
        finally:
            os.unlink(path)

    def test_backward_reference_still_counted(self) -> None:
        """POS: `/name` in a non-forward-reference context IS counted."""
        charter = (
            "## Hook 20: Foo\n\n"
            "- **Promotion provenance:** This hook enforces the "
            "`/thing-checker` skill which operators invoked 7x in W8.\n"
        )
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write(charter)
            path = f.name
        try:
            refs = h.find_already_promoted(path)
            self.assertIn("/thing-checker", refs)
        finally:
            os.unlink(path)

    def test_html_comment_charter_tier_marker_detected(self) -> None:
        """POS (#283 gap 1): the new `<!-- Promoted from memory: X -->` HTML-
        comment marker, used for charter-tier-only promotions (no
        corresponding hook), must be recognized. Pre-#283 only the
        `**Promotion provenance:**` block style was scanned, so charter-
        tier promotions in non-hooks.md sub-docs were invisible to the
        parser and produced false-positive AUTO classifications.
        """
        charter = (
            "## Some charter section\n\n"
            "<!-- Promoted from memory: feedback_review_against_artifact_not_framing.md "
            "(P3W5 retro 2026-05-06; reviewer-side). -->\n\n"
            "Body of the section.\n"
        )
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write(charter)
            path = f.name
        try:
            refs = h.find_already_promoted(path)
            self.assertIn("feedback_review_against_artifact_not_framing.md", refs)
        finally:
            os.unlink(path)

    def test_md_less_memory_name_matched_same_as_suffixed(self) -> None:
        """POS (#283 gap 2): a memory cited without the `.md` suffix (as in
        hooks.md L169's backticked cite of
        `feedback_honest_audit_over_conclusion_claim`) must be matched
        same as a `.md`-suffixed citation. Both forms land in the
        returned set so callers using `memory.filename in
        already_promoted` continue to match transparently.
        """
        charter = (
            "## Hook 17: Foo\n\n"
            "- **Promotion provenance:** memory "
            "`feedback_honest_audit_over_conclusion_claim` (2026-04-22) -> "
            "charter rule (PR #193) -> this hook (#195).\n"
        )
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write(charter)
            path = f.name
        try:
            refs = h.find_already_promoted(path)
            # Caller checks via `memory.filename`, which is always .md-suffixed.
            self.assertIn("feedback_honest_audit_over_conclusion_claim.md", refs)
            # The unsuffixed form is also in the set (for completeness /
            # callers that cite by raw name).
            self.assertIn("feedback_honest_audit_over_conclusion_claim", refs)
        finally:
            os.unlink(path)

    def test_hooks_md_provenance_no_regression(self) -> None:
        """REGRESSION: extending the parser must not break recognition of
        existing hooks.md `**Promotion provenance:**` blocks. This pins
        the Hook 15 worked example end-to-end after the #283 changes.
        """
        charter = (
            "## Hook 15: Foo\n\n"
            "- **Promotion provenance:** First end-to-end execution of "
            "the memory -> charter -> hook promotion pattern. Rule lived "
            "in CLAUDE.md § Ontology; first instance cites "
            "feedback_enforcement_hierarchy.md.\n"
        )
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write(charter)
            path = f.name
        try:
            refs = h.find_already_promoted(path)
            self.assertIn("feedback_enforcement_hierarchy.md", refs)
            self.assertIn("CLAUDE.md § Ontology", refs)
        finally:
            os.unlink(path)

    def test_aggregator_scans_all_charter_subdocs(self) -> None:
        """POS (#283): `find_already_promoted_in_charter()` must aggregate
        results across the full `<root>/charter/*.md` directory, picking
        up charter-tier HTML-comment markers in non-hooks.md sub-docs.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            charter_subdir = os.path.join(tmpdir, "charter")
            os.makedirs(charter_subdir)

            # File 1: hooks.md with a block-style provenance entry.
            with open(os.path.join(charter_subdir, "hooks.md"), "w") as f:
                f.write(
                    "## Hook 15: Foo\n\n"
                    "- **Promotion provenance:** Worked example cites "
                    "feedback_block_style.md.\n"
                )
            # File 2: pull-requests.md with an HTML-comment marker.
            with open(os.path.join(charter_subdir, "pull-requests.md"), "w") as f:
                f.write(
                    "## A promoted section\n\n"
                    "<!-- Promoted from memory: feedback_html_style.md (P3W5 retro) -->\n\n"
                    "Body.\n"
                )
            # File 3: skills.md with a `.md`-less citation inside a marker.
            with open(os.path.join(charter_subdir, "skills.md"), "w") as f:
                f.write(
                    "## Another promoted section\n\n"
                    "<!-- Promoted from memory: feedback_no_suffix -->\n"
                )

            refs = h.find_already_promoted_in_charter(tmpdir)
            self.assertIn("feedback_block_style.md", refs)
            self.assertIn("feedback_html_style.md", refs)
            self.assertIn("feedback_no_suffix.md", refs)
            self.assertIn("feedback_no_suffix", refs)

    def test_aggregator_handles_missing_charter_dir(self) -> None:
        """NEG: a non-existent charter root must return an empty set
        (not raise) — the smoke test runs against the live repo state
        where this should never trigger, but the contract is defensive."""
        refs = h.find_already_promoted_in_charter("/nonexistent/path/to/charter")
        self.assertEqual(refs, set())

    def test_aggregator_raises_on_charter_dir_itself(self) -> None:
        """NEG (#418): passing the charter directory itself (e.g.
        `.claude/team/charter`) instead of its parent must raise
        ValueError. Previously this silently returned set() because no
        `<root>/charter/charter/` subdir exists — the silent-zero failure
        mode that #418 was filed to fix.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            charter_subdir = os.path.join(tmpdir, "charter")
            os.makedirs(charter_subdir)
            # Correct form: parent of charter/ — returns set() (empty corpus).
            self.assertEqual(h.find_already_promoted_in_charter(tmpdir), set())
            # Wrong form: the charter dir itself — must raise loudly.
            with self.assertRaises(ValueError) as ctx:
                h.find_already_promoted_in_charter(charter_subdir)
            self.assertIn("#418", str(ctx.exception))

            # Trailing slash form must still raise — normpath strips it.
            with self.assertRaises(ValueError):
                h.find_already_promoted_in_charter(charter_subdir + "/")

    def test_aggregator_recurses_into_charter_subdirs(self) -> None:
        """POS (#963): the charter mega-files were re-shelved into per-concern
        section files under `charter/{agents,pull-requests,hooks}/`. The
        aggregator must pick up markers in those SUBDIRECTORY files — a
        non-recursive listdir scan would silently drop them (the #418
        silent-empty failure class, one level down).
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            nested = os.path.join(tmpdir, "charter", "pull-requests")
            os.makedirs(nested)
            with open(os.path.join(nested, "authoring.md"), "w") as f:
                f.write(
                    "## A re-shelved section\n\n"
                    "<!-- Promoted from memory: feedback_nested_style.md (P8W24) -->\n\n"
                    "Body.\n"
                )
            refs = h.find_already_promoted_in_charter(tmpdir)
            self.assertIn("feedback_nested_style.md", refs)

    def test_read_all_charter_sections_recurses_into_subdirs(self) -> None:
        """POS (#963): marked sections re-shelved into `charter/<concern>/`
        subdirectory files must appear in `read_all_charter_sections`
        output exactly like top-level `charter/*.md` sections."""
        with tempfile.TemporaryDirectory() as tmpdir:
            top = os.path.join(tmpdir, "charter")
            nested = os.path.join(top, "agents")
            os.makedirs(nested)
            with open(os.path.join(top, "issues.md"), "w") as f:
                f.write("## Top-level section <!-- promotion-target: none -->\n\nA.\n")
            with open(os.path.join(nested, "lifecycle.md"), "w") as f:
                f.write(
                    "## Nested section <!-- promotion-target: skill -->\n\nB.\n"
                    "<!-- promoted-to: skills/some-slug -->\n"
                )
            sections = h.read_all_charter_sections(tmpdir)
            headings = {s.heading for s in sections}
            self.assertEqual(headings, {"Top-level section", "Nested section"})
            nested_sec = next(s for s in sections if s.heading == "Nested section")
            self.assertEqual(nested_sec.promotion_target, "skill")
            self.assertEqual(nested_sec.promoted_to, "skills/some-slug")
            self.assertEqual(nested_sec.path, os.path.join(nested, "lifecycle.md"))

    def test_read_all_charter_sections_raises_on_charter_dir_itself(self) -> None:
        """NEG (#418, sibling): `read_all_charter_sections` has identical
        parent-of-charter semantics and the same silent-empty failure mode.
        Passing the charter dir itself must raise.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            charter_subdir = os.path.join(tmpdir, "charter")
            os.makedirs(charter_subdir)
            # Correct form: returns empty list (no marked sections in empty corpus).
            self.assertEqual(h.read_all_charter_sections(tmpdir), [])
            with self.assertRaises(ValueError):
                h.read_all_charter_sections(charter_subdir)


# ---------------------------------------------------------------------------
# Classification — memory
# ---------------------------------------------------------------------------


def _make_memory(**kwargs: object) -> h.Memory:
    defaults: dict[str, object] = {
        "path": "/fake/feedback_x.md",
        "name": "X",
        "description": "",
        "type_": "feedback",
        "promotion_target": "none",
        "promotion_threshold": {"retro_citations": 3, "skill_invocations": 5},
        "referenced_in_retros": (),
        "status": "active",
        "superseded_by": "",
        "supersedes": "",
        "requires_decision": False,
        "body": "",
    }
    defaults.update(kwargs)
    return h.Memory(**defaults)  # type: ignore[arg-type]


class ClassifyMemoryTests(unittest.TestCase):
    def test_none_target_yields_kept(self) -> None:
        m = _make_memory(promotion_target="none")
        d = h.classify_memory(m, {"retro_citations": 10}, set())
        self.assertEqual(d.kind, "KEPT")

    def test_superseded_status_yields_superseded(self) -> None:
        m = _make_memory(status="superseded", superseded_by="charter:foo")
        d = h.classify_memory(m, {"retro_citations": 10}, set())
        self.assertEqual(d.kind, "SUPERSEDED")

    def test_enforced_elsewhere_yields_superseded(self) -> None:
        """The feedback_enforcement_hierarchy case."""
        m = _make_memory(status="enforced-elsewhere", superseded_by="Hook 15")
        d = h.classify_memory(m, {"retro_citations": 5}, set())
        self.assertEqual(d.kind, "SUPERSEDED")

    def test_already_promoted_wins(self) -> None:
        """ALREADY-PROMOTED takes precedence even over active eligible memory."""
        m = _make_memory(promotion_target="charter", status="active")
        d = h.classify_memory(m, {"retro_citations": 10}, {"feedback_x.md"})
        self.assertEqual(d.kind, "ALREADY-PROMOTED")

    def test_threshold_not_met_kept(self) -> None:
        m = _make_memory(promotion_target="charter", status="active")
        d = h.classify_memory(m, {"retro_citations": 1}, set())
        self.assertEqual(d.kind, "KEPT")
        self.assertIn("1 < 3", d.signal)

    def test_threshold_met_auto(self) -> None:
        m = _make_memory(promotion_target="charter", status="active")
        d = h.classify_memory(m, {"retro_citations": 5}, set())
        self.assertEqual(d.kind, "AUTO")

    def test_requires_decision_forces_decide(self) -> None:
        m = _make_memory(promotion_target="charter", status="active", requires_decision=True)
        d = h.classify_memory(m, {"retro_citations": 10}, set())
        self.assertEqual(d.kind, "DECIDE")

    def test_hook_target_not_valid_for_memory(self) -> None:
        """NEG: memory -> hook is not a valid direct transition."""
        m = _make_memory(promotion_target="hook", status="active")
        d = h.classify_memory(m, {"retro_citations": 10}, set())
        self.assertEqual(d.kind, "KEPT")
        self.assertIn("not a valid memory transition", d.reason)


# ---------------------------------------------------------------------------
# Classification — STALE-OPT-OUT informational class (#158)
# ---------------------------------------------------------------------------


class StaleOptOutTests(unittest.TestCase):
    """A `promotion_target: none` memory whose retro_citations cross
    2× the threshold is flagged STALE-OPT-OUT — an informational
    callout under KEPT, not a new decision tier. The opt-out stays
    authoritative; nothing is overridden, no issue is filed.
    """

    def test_high_cite_none_is_flagged(self) -> None:
        """POS: `none` + citations >= 2 * threshold → KEPT with stale_opt_out flag."""
        m = _make_memory(promotion_target="none", status="active")
        d = h.classify_memory(m, {"retro_citations": 7}, set())
        self.assertEqual(d.kind, "KEPT")
        self.assertTrue(d.extra.get("stale_opt_out"))
        self.assertIn("cited 7x", d.reason)
        self.assertIn(">= 2 *", d.signal)

    def test_low_cite_none_not_flagged(self) -> None:
        """NEG: `none` + citations below 2 * threshold → plain KEPT, no flag."""
        m = _make_memory(promotion_target="none", status="active")
        # threshold default 3; below 2*3=6 must NOT trigger.
        d = h.classify_memory(m, {"retro_citations": 5}, set())
        self.assertEqual(d.kind, "KEPT")
        self.assertFalse(d.extra.get("stale_opt_out", False))
        self.assertIn("informational memory", d.reason)

    def test_exactly_double_threshold_is_flagged(self) -> None:
        """POS: edge case — citations == 2 * threshold triggers (>=, not >)."""
        m = _make_memory(promotion_target="none", status="active")
        d = h.classify_memory(m, {"retro_citations": 6}, set())  # 2 * 3
        self.assertEqual(d.kind, "KEPT")
        self.assertTrue(d.extra.get("stale_opt_out"))

    def test_charter_target_high_cite_unaffected(self) -> None:
        """NEG: `charter` target with high citations still flows AUTO/DECIDE.
        STALE-OPT-OUT only applies on the `promotion_target: none` path."""
        m = _make_memory(promotion_target="charter", status="active")
        d = h.classify_memory(m, {"retro_citations": 100}, set())
        self.assertEqual(d.kind, "AUTO")
        self.assertFalse(d.extra.get("stale_opt_out", False))

    def test_custom_threshold_respected(self) -> None:
        """NEG: a memory with a custom threshold uses that, not the default."""
        m = _make_memory(
            promotion_target="none",
            status="active",
            promotion_threshold={"retro_citations": 5, "skill_invocations": 5},
        )
        # 2 * 5 = 10; 9 must NOT trigger, 10 MUST.
        d_below = h.classify_memory(m, {"retro_citations": 9}, set())
        self.assertFalse(d_below.extra.get("stale_opt_out", False))
        d_at = h.classify_memory(m, {"retro_citations": 10}, set())
        self.assertTrue(d_at.extra.get("stale_opt_out"))

    def test_already_promoted_takes_precedence(self) -> None:
        """NEG: ALREADY-PROMOTED still wins over STALE-OPT-OUT."""
        m = _make_memory(promotion_target="none", status="active")
        d = h.classify_memory(m, {"retro_citations": 100}, {"feedback_x.md"})
        self.assertEqual(d.kind, "ALREADY-PROMOTED")


# ---------------------------------------------------------------------------
# Classification — charter section
# ---------------------------------------------------------------------------


def _make_section(**kwargs: object) -> h.CharterSection:
    defaults: dict[str, object] = {
        "path": "/fake/charter/issues.md",
        "heading": "Delegation Flow",
        "promotion_target": "skill",
        "body": "1. step\n2. step\n3. step",
        "promoted_to": "",
    }
    defaults.update(kwargs)
    return h.CharterSection(**defaults)  # type: ignore[arg-type]


class ClassifySectionTests(unittest.TestCase):
    def test_none_target_kept(self) -> None:
        d = h.classify_section(_make_section(promotion_target="none"), {})
        self.assertEqual(d.kind, "KEPT")

    def test_already_promoted_backref(self) -> None:
        d = h.classify_section(_make_section(promoted_to="skills/delegation-flow"), {})
        self.assertEqual(d.kind, "ALREADY-PROMOTED")

    def test_threshold_not_met(self) -> None:
        # #1355: the signal key is `section_citations` (source-section
        # evidence), not `skill_invocations` (destination-slug usage).
        d = h.classify_section(_make_section(), {"section_citations": 1, "threshold": 5})
        self.assertEqual(d.kind, "KEPT")

    def test_threshold_met(self) -> None:
        d = h.classify_section(_make_section(), {"section_citations": 7, "threshold": 5})
        self.assertEqual(d.kind, "AUTO")
        self.assertIn("section_citations=7 >= 5", d.signal)

    def test_legacy_skill_invocations_key_is_ignored_not_zero_workaround(self) -> None:
        """NEG: a caller still passing the pre-#1355 `skill_invocations` key
        (instead of `section_citations`) must NOT accidentally cross
        threshold — the key is simply absent from `classify_section`'s
        perspective and defaults to 0 citations, same as passing nothing."""
        d = h.classify_section(_make_section(), {"skill_invocations": 99, "threshold": 5})
        self.assertEqual(d.kind, "KEPT")

    def test_hook_target_not_valid_for_section(self) -> None:
        """NEG: charter sections only promote to skill."""
        d = h.classify_section(_make_section(promotion_target="hook"), {})
        self.assertEqual(d.kind, "KEPT")

    def test_threshold_not_met_unconfigured_target_names_the_gap(self) -> None:
        """#1355 acceptance criterion 1 (delivered by #1383, re-pinned here
        against the corrected signal): a section whose prospective skill
        does not exist yet on disk (`target_configured` false/absent)
        still renders distinctly as a configuration gap — NOT the
        "wait for more operator-invoked runs" message.

        Post-#1355, this is no longer because evidence "cannot accrue"
        without a target (it now demonstrably can — `section_citations`
        is computed from the SOURCE section, independent of whether the
        skill exists) — the message says so explicitly rather than
        repeating the now-inaccurate pre-#1355 claim."""
        d = h.classify_section(
            _make_section(), {"section_citations": 0, "threshold": 5, "target_configured": 0}
        )
        self.assertEqual(d.kind, "KEPT")
        self.assertNotIn("wait for more operator-invoked runs", d.reason)
        self.assertIn("not configured", d.reason.lower())
        # The corrected claim: evidence is NOT blocked by the missing target.
        self.assertIn("no longer blocks evidence", d.reason)

    def test_threshold_not_met_unconfigured_target_reports_actual_citations(self) -> None:
        """The config-gap message must surface the real citation count
        (not a placeholder) — proof the signal is genuinely wired through
        even when the target isn't configured yet."""
        d = h.classify_section(
            _make_section(), {"section_citations": 3, "threshold": 5, "target_configured": 0}
        )
        self.assertIn("3", d.reason)
        self.assertIn("3/5", d.reason)

    def test_threshold_not_met_configured_target_still_says_wait(self) -> None:
        """NEG: once the target skill actually exists on disk (configured,
        just below the citation threshold), 'wait for more
        operator-invoked runs' is retained verbatim (#1383 delivered
        wording, not redone here)."""
        d = h.classify_section(
            _make_section(), {"section_citations": 1, "threshold": 5, "target_configured": 1}
        )
        self.assertEqual(d.kind, "KEPT")
        self.assertIn("wait for more operator-invoked runs", d.reason)

    def test_threshold_not_met_target_configured_defaults_false(self) -> None:
        """Absent `target_configured` in signals defaults to unconfigured
        (the common case: prospective-only slug, skill never scaffolded) —
        callers that don't wire the new signal get the safe, accurate
        message rather than silently reverting to the misleading one."""
        d = h.classify_section(_make_section(), {"section_citations": 0, "threshold": 5})
        self.assertEqual(d.kind, "KEPT")
        self.assertIn("not configured", d.reason.lower())

    def test_threshold_met_regardless_of_target_configured(self) -> None:
        """#1355 acceptance criterion 2: crossing threshold produces AUTO
        even when the prospective skill has never been scaffolded — the
        source-section signal does not require the destination to exist
        first (the whole point of the fix)."""
        d = h.classify_section(
            _make_section(), {"section_citations": 5, "threshold": 5, "target_configured": 0}
        )
        self.assertEqual(d.kind, "AUTO")


# ---------------------------------------------------------------------------
# Source-section citation counting (#1355)
# ---------------------------------------------------------------------------


class CountSectionCitationsTests(unittest.TestCase):
    def _section(self, **kwargs: object) -> h.CharterSection:
        defaults: dict[str, object] = {
            "path": "/fake/charter/wave-merge.md",
            "heading": "Cross-Contract PRs",
            "promotion_target": "skill",
            "body": "body",
            "promoted_to": "",
        }
        defaults.update(kwargs)
        return h.CharterSection(**defaults)  # type: ignore[arg-type]

    def test_counts_heading_occurrences(self) -> None:
        log = (
            "See charter § Cross-Contract PRs for the rule.\n"
            "Cross-Contract PRs applies here too.\n"
            "Unrelated line.\n"
        )
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write(log)
            path = f.name
        try:
            self.assertEqual(h.count_section_citations(self._section(), path), 2)
        finally:
            os.unlink(path)

    def test_counts_include_per_phase_archives(self) -> None:
        """Same archive-scan mechanism as `count_retro_citations` (#964) —
        live log + archive/feedback_log_*.md are summed."""
        with tempfile.TemporaryDirectory() as d:
            live = os.path.join(d, "feedback_log.md")
            with open(live, "w", encoding="utf-8") as f:
                f.write("cites Cross-Contract PRs once\n")
            arch = os.path.join(d, "archive")
            os.makedirs(arch)
            with open(os.path.join(arch, "feedback_log_phase-2.md"), "w", encoding="utf-8") as f:
                f.write("old retro cites Cross-Contract PRs, then Cross-Contract PRs again\n")
            self.assertEqual(h.count_section_citations(self._section(), live), 3)

    def test_no_citations_returns_zero(self) -> None:
        log = "nothing relevant here\n"
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write(log)
            path = f.name
        try:
            self.assertEqual(h.count_section_citations(self._section(), path), 0)
        finally:
            os.unlink(path)

    def test_missing_log_returns_zero(self) -> None:
        self.assertEqual(h.count_section_citations(self._section(), "/nonexistent"), 0)

    def test_blank_heading_returns_zero_not_corpus_length(self) -> None:
        """Defensive guard mirroring main#690's blank-slug fix:
        `text.count("")` would otherwise return `len(text) + 1`, making a
        blank heading look like it crossed any threshold trivially."""
        log = "some reasonably long corpus text so the bug would be obvious\n" * 10
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write(log)
            path = f.name
        try:
            self.assertEqual(h.count_section_citations(self._section(heading=""), path), 0)
            self.assertEqual(h.count_section_citations(self._section(heading="   "), path), 0)
        finally:
            os.unlink(path)

    def test_independent_of_skill_slug_collision(self) -> None:
        """main#1389: the OLD destination-invocation signal could inherit
        an unrelated existing skill's real invocation count merely because
        a heading slugified onto that skill's directory name. This signal
        has no slug/skills-dir dependency at all — a heading that would
        collide with a real skill name still counts only its own literal
        citations, proving the collision path is closed for this number."""
        section = self._section(heading="Handoff")
        log = "no citation of that heading here, just unrelated retro prose\n"
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write(log)
            path = f.name
        try:
            # Regardless of how many times /handoff (the real skill) was
            # invoked in git history, this function never looks at git log
            # or any skills directory — only the feedback-log corpus.
            self.assertEqual(h.count_section_citations(section, path), 0)
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Classification — skill
# ---------------------------------------------------------------------------


def _make_skill(**kwargs: object) -> h.Skill:
    defaults: dict[str, object] = {
        "name": "thing-checker",
        "path": "/fake/.claude/skills/thing-checker/SKILL.md",
        "promotion_target": "hook",
        "description": "Check things",
        "body": "",
    }
    defaults.update(kwargs)
    return h.Skill(**defaults)  # type: ignore[arg-type]


class ClassifySkillTests(unittest.TestCase):
    def test_none_target_kept(self) -> None:
        d = h.classify_skill(_make_skill(promotion_target="none"), {}, set())
        self.assertEqual(d.kind, "KEPT")

    def test_threshold_met_is_decide_not_auto(self) -> None:
        """D6 locked: skill -> hook is ALWAYS DECIDE, never AUTO."""
        d = h.classify_skill(
            _make_skill(),
            {"skill_invocations": 100, "threshold": 5},
            set(),
        )
        self.assertEqual(d.kind, "DECIDE")

    def test_already_promoted_by_slash_name(self) -> None:
        d = h.classify_skill(
            _make_skill(name="ontology-librarian"),
            {"skill_invocations": 10, "threshold": 5},
            {"/ontology-librarian"},
        )
        self.assertEqual(d.kind, "ALREADY-PROMOTED")

    def test_threshold_not_met_kept(self) -> None:
        d = h.classify_skill(
            _make_skill(),
            {"skill_invocations": 1, "threshold": 5},
            set(),
        )
        self.assertEqual(d.kind, "KEPT")


# ---------------------------------------------------------------------------
# Render audit table — determinism
# ---------------------------------------------------------------------------


class RenderAuditTableTests(unittest.TestCase):
    def test_empty_decisions_renders_empty_state(self) -> None:
        out = h.render_audit_table([], "wave-9", "2026-04-19")
        self.assertIn("Promotion Audit — wave-9", out)
        self.assertIn("0 AUTO", out)
        self.assertIn("_None this run._", out)

    def test_same_input_yields_identical_output(self) -> None:
        """Core determinism guarantee: re-render must be byte-identical."""
        decisions = [
            h.Decision(
                kind="KEPT",
                item_id="feedback_x.md",
                from_tier="memory",
                to_tier="-",
                signal="retro_citations=0",
                reason="promotion_target=none",
            ),
            h.Decision(
                kind="SUPERSEDED",
                item_id="feedback_y.md",
                from_tier="memory",
                to_tier="-",
                signal="superseded_by: charter:foo",
                reason="Memory explicitly marked superseded",
            ),
        ]
        a = h.render_audit_table(decisions, "wave-9", "2026-04-19")
        b = h.render_audit_table(decisions, "wave-9", "2026-04-19")
        self.assertEqual(a, b)

    def test_stale_opt_out_sublist_rendered(self) -> None:
        """POS: KEPT entries with stale_opt_out=True render as a labeled sub-list."""
        decisions = [
            h.Decision(
                kind="KEPT",
                item_id="feedback_quiet.md",
                from_tier="memory",
                to_tier="-",
                signal="retro_citations=0",
                reason="promotion_target=none (informational memory)",
            ),
            h.Decision(
                kind="KEPT",
                item_id="feedback_loud.md",
                from_tier="memory",
                to_tier="-",
                signal="retro_citations=7 >= 2 * 3",
                reason="promotion_target=none, but cited 7x — consider reviewing the opt-out",
                extra={"stale_opt_out": True},
            ),
        ]
        out = h.render_audit_table(decisions, "wave-9", "2026-04-19")
        self.assertIn("STALE-OPT-OUT", out)
        # The plain KEPT entry must appear above the STALE-OPT-OUT header.
        quiet_idx = out.index("feedback_quiet.md")
        header_idx = out.index("STALE-OPT-OUT")
        loud_idx = out.index("feedback_loud.md")
        self.assertLess(quiet_idx, header_idx)
        self.assertLess(header_idx, loud_idx)

    def test_no_stale_opt_out_header_when_empty(self) -> None:
        """NEG: with no flagged entries, the STALE-OPT-OUT header must NOT appear."""
        decisions = [
            h.Decision(
                kind="KEPT",
                item_id="feedback_x.md",
                from_tier="memory",
                to_tier="-",
                signal="retro_citations=0",
                reason="promotion_target=none (informational memory)",
            ),
        ]
        out = h.render_audit_table(decisions, "wave-9", "2026-04-19")
        self.assertNotIn("STALE-OPT-OUT", out)

    def test_stale_only_renders_header(self) -> None:
        """POS: when ALL KEPT entries are stale-flagged, header still appears."""
        decisions = [
            h.Decision(
                kind="KEPT",
                item_id="feedback_loud.md",
                from_tier="memory",
                to_tier="-",
                signal="retro_citations=7 >= 2 * 3",
                reason="promotion_target=none, but cited 7x — consider reviewing the opt-out",
                extra={"stale_opt_out": True},
            ),
        ]
        out = h.render_audit_table(decisions, "wave-9", "2026-04-19")
        self.assertIn("STALE-OPT-OUT", out)
        self.assertIn("feedback_loud.md", out)

    def test_sorted_within_bucket(self) -> None:
        """NEG: unsorted input must still produce sorted output."""
        decisions = [
            h.Decision(
                kind="KEPT",
                item_id="zzz.md",
                from_tier="memory",
                to_tier="-",
                signal="",
                reason="r",
            ),
            h.Decision(
                kind="KEPT",
                item_id="aaa.md",
                from_tier="memory",
                to_tier="-",
                signal="",
                reason="r",
            ),
        ]
        out = h.render_audit_table(decisions, "wave-9", "2026-04-19")
        self.assertLess(out.index("aaa.md"), out.index("zzz.md"))


# ---------------------------------------------------------------------------
# Artifact generation
# ---------------------------------------------------------------------------


class GenerateArtifactsTests(unittest.TestCase):
    template_dir: str

    @classmethod
    def setUpClass(cls) -> None:
        cls.template_dir = str(_HERE.parent / "templates")

    def test_charter_section_renders_memory_body(self) -> None:
        m = _make_memory(name="Test rule", description="A test", body="This is the rule body.")
        out = h.generate_charter_section(m, self.template_dir)
        self.assertIn("## Test rule", out)
        self.assertIn("This is the rule body.", out)
        self.assertIn("promotion-target: skill", out)
        self.assertIn("feedback_x.md", out)

    def test_charter_section_emits_canonical_html_comment_marker(self) -> None:
        """The template MUST emit the canonical HTML-comment marker per
        charter/skills.md § Promotion Pipeline Marker Convention (#393).

        Italic-prose `_Promoted from memory_` and blockquote forms are
        banned because the parser does not recognize them; regressing to
        either form re-introduces the AUTO false-positive class #283 closed.
        """
        m = _make_memory(name="Test rule", description="A test", body="Rule body.")
        out = h.generate_charter_section(m, self.template_dir)
        self.assertIn("<!-- Promoted from memory: feedback_x.md", out)
        self.assertNotIn("_Promoted from memory", out)

    def test_skill_scaffold_slugifies_heading(self) -> None:
        s = _make_section(heading="Load-Bearing Followups for Disabled CI Jobs")
        out = h.generate_skill_scaffold(s, self.template_dir)
        self.assertIn("name: load-bearing-followups-for-disabled-ci-jobs", out)
        self.assertIn("Load-Bearing Followups for Disabled CI Jobs", out)
        self.assertIn("issues.md", out)

    def test_hook_draft_generates_title_and_body(self) -> None:
        s = _make_skill(name="retro-helper", description="Automates retros")
        out = h.generate_hook_draft_issue(s, self.template_dir)
        self.assertIn("/retro-helper", out["title"])
        self.assertIn("Automates retros", out["body"])
        self.assertIn("promote /retro-helper skill to hook", out["title"])


# ---------------------------------------------------------------------------
# Slugify
# ---------------------------------------------------------------------------


class SlugifyTests(unittest.TestCase):
    def test_basic(self) -> None:
        self.assertEqual(h._slugify("Hello World"), "hello-world")

    def test_strips_punctuation(self) -> None:
        self.assertEqual(h._slugify("Load-Bearing: Followups!"), "load-bearing-followups")

    def test_empty_fallback(self) -> None:
        self.assertEqual(h._slugify("   "), "section")


class SourceHintReTests(unittest.TestCase):
    """#419 regression — `_SOURCE_HINT_RE` MUST NOT match URL path
    fragments inside gh-issue link bodies, and MUST still match real
    kebab-case slash-commands at word boundaries.

    Exercises the regex directly (tightening) plus `_strip_url_bodies`
    (link-context elimination). Both layers are load-bearing; tests
    cover each independently and in combination via `find_already_promoted`.
    """

    def test_excludes_numeric_url_path_fragment(self) -> None:
        """NEG (#419 row 1): `/198` from gh-issue URL fragments is rejected
        purely by the regex shape — alpha-leading filter — even before
        URL-stripping runs."""
        matches = h._SOURCE_HINT_RE.findall("filed as /198 and /200 and /244")
        self.assertNotIn("/198", matches)
        self.assertNotIn("/200", matches)
        self.assertNotIn("/244", matches)

    def test_excludes_uppercase_url_path_fragment(self) -> None:
        """NEG (#419 row 2): `/Edit` from path fragments rejected by the
        alpha-LOWERCASE-leading filter."""
        matches = h._SOURCE_HINT_RE.findall("see /Edit or /GitHub")
        self.assertNotIn("/Edit", matches)
        self.assertNotIn("/GitHub", matches)

    def test_excludes_mid_token_slash(self) -> None:
        """NEG (12th case): `/supersedes` inside `augments/supersedes`
        prose (charter/skills.md:108) is rejected by the word-boundary
        lookbehind."""
        matches = h._SOURCE_HINT_RE.findall("augments/supersedes relationships")
        self.assertNotIn("/supersedes", matches)

    def test_matches_real_slash_command_at_word_boundary(self) -> None:
        """POS (#419 acceptance): real slash-commands at word boundaries
        (start, after whitespace, after punctuation) still match."""
        matches = set(
            h._SOURCE_HINT_RE.findall("see /promotion-audit and /wave-retro (/auto-promote)")
        )
        self.assertIn("/promotion-audit", matches)
        self.assertIn("/wave-retro", matches)
        self.assertIn("/auto-promote", matches)

    def test_matches_memory_filename_both_forms(self) -> None:
        """POS regression guard: memory-filename matching unaffected by
        the slash-branch tightening."""
        matches = set(
            h._SOURCE_HINT_RE.findall(
                "see feedback_foo.md and project_bar (suffixless), reference_baz.md"
            )
        )
        self.assertIn("feedback_foo.md", matches)
        self.assertIn("reference_baz.md", matches)
        # Suffix-less form is captured separately.
        self.assertIn("project_bar", matches)


class StripUrlBodiesTests(unittest.TestCase):
    """#419: `_strip_url_bodies` removes URL bodies (markdown links,
    autolinks, bare URLs) while preserving the surrounding prose so
    URL-path-fragment matches never reach `_SOURCE_HINT_RE`."""

    def test_markdown_link_url_stripped_text_preserved(self) -> None:
        """[text](url) → [text]() — URL gone, link text remains so any
        memory/slash-command reference inside the text is still hit."""
        s = h._strip_url_bodies(
            "[#198](https://github.com/noorinalabs/noorinalabs-main/issues/198)"
        )
        self.assertEqual(s, "[#198]()")
        # Downstream regex on the stripped form must NOT hit `/198`/`/issues`.
        self.assertNotIn("/198", h._SOURCE_HINT_RE.findall(s))
        self.assertNotIn("/issues", h._SOURCE_HINT_RE.findall(s))
        self.assertNotIn("/noorinalabs", h._SOURCE_HINT_RE.findall(s))

    def test_autolink_url_stripped(self) -> None:
        """<https://...> → empty (no link text to preserve)."""
        s = h._strip_url_bodies("see <https://github.com/foo/bar/issues/337>")
        self.assertNotIn("github", s)
        self.assertNotIn("337", s)

    def test_bare_url_stripped(self) -> None:
        """Bare `http(s)://...` in prose is stripped."""
        s = h._strip_url_bodies("docs at https://example.com/path/to/thing")
        self.assertNotIn("https://", s)
        self.assertNotIn("/path", s)
        self.assertNotIn("/thing", s)

    def test_non_url_prose_unchanged(self) -> None:
        """NEG: text without URLs is returned identically — no
        accidental damage to charter prose."""
        s = "see /promotion-audit and feedback_foo.md per retro"
        self.assertEqual(h._strip_url_bodies(s), s)

    def test_link_text_with_real_slash_command_preserved(self) -> None:
        """POS: a markdown link whose LABEL cites a real slash-command
        must still surface that slash-command after stripping."""
        s = h._strip_url_bodies("[/promotion-audit run output](https://example.com/log)")
        self.assertIn("/promotion-audit", h._SOURCE_HINT_RE.findall(s))

    def test_find_already_promoted_rejects_url_fragments_end_to_end(self) -> None:
        """POS end-to-end (#419 acceptance): a provenance block whose
        body contains an issue link does NOT pollute the returned set
        with URL-path-fragment noise.
        """
        charter = textwrap.dedent(
            """\
            ## Hook 99: Foo

            - **Promotion provenance:** Rule lived in feedback_foo.md.
              Filed as [#198](https://github.com/noorinalabs/noorinalabs-main/issues/198).
              Worked example used /promotion-audit run output.
            """
        )
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write(charter)
            path = f.name
        try:
            refs = h.find_already_promoted(path)
            # Real refs present.
            self.assertIn("feedback_foo.md", refs)
            self.assertIn("/promotion-audit", refs)
            # URL-fragment noise absent.
            for noise in ("/198", "/issues", "/noorinalabs", "/noorinalabs-main", "/github"):
                self.assertNotIn(
                    noise,
                    refs,
                    msg=f"URL-fragment {noise!r} leaked into already-promoted set",
                )
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Provenance-aware citation filtering (main#1469)
#
# `count_section_citations` and `count_retro_citations` used to be a bare
# `text.count(...)` over the feedback-log corpus. That corpus is WRITTEN BY
# the same instruments that read it — `/wave-retro` Step 7.5 reports every
# AUTO/DECIDE/KEPT verdict by heading or filename, Step 7.7 reports citation
# counts back into the log, and Step 7.8's size/age sweep prints a flagged
# file's bare name every wave regardless of whether anyone cited it. A fix
# that filters these self-generated shapes must be pinned against a FIXTURE
# corpus that reproduces the shape — the live feedback_log.md changes every
# wave and would make these tests non-deterministic.
# ---------------------------------------------------------------------------


class CountGenuineCitationsTests(unittest.TestCase):
    """Direct unit tests of the shared primitive, isolating each of the
    four excluded shapes plus the genuine-citation case."""

    def test_plain_genuine_citation_counts(self) -> None:
        text = (
            "Cross-Contract cited: per Charter § Cross-Contract PRs, alembic merge "
            "migration is now in main.\n"
        )
        self.assertEqual(h.count_genuine_citations(text, "Cross-Contract PRs"), 1)

    def test_forward_reference_excluded(self) -> None:
        """Single-clause fixture: only `_is_forward_reference` fires here.

        PR #1519 merge-gate review (Nadia Khoury, mutant b1): the original
        fixture for this test ("Proposed location: charter
        `pull-requests.md` § Cross-Contract PRs OR new § Design-Rationale
        Blocks.") is classified by THREE clauses at once
        (`_is_forward_reference` True via "Proposed", `_is_creation_record`
        True via "new §", `_is_wave_summary_listing` True via its two "§"
        marks), so disabling the forward-reference clause alone left the
        whole suite green -- the test never actually exercised it. This
        fixture has no "new §"/"Charter home:"/"per process-change" phrase
        and only one "§" mark, so only the forward-reference clause can
        classify it as non-genuine."""
        text = "Proposed location: charter `pull-requests.md` under Cross-Contract PRs.\n"
        self.assertEqual(h.count_genuine_citations(text, "Cross-Contract PRs"), 0)

    def test_forward_reference_still_excluded_alongside_other_clauses(self) -> None:
        """The original multi-clause fixture stays green as a second,
        non-load-bearing sanity check that multiple simultaneously-firing
        exclusion clauses don't conflict — but it is NOT what pins the
        forward-reference clause (see `test_forward_reference_excluded`
        above for the single-clause fixture that does)."""
        text = (
            "Proposed location: charter `pull-requests.md` § Cross-Contract PRs OR "
            "new § Design-Rationale Blocks.\n"
        )
        self.assertEqual(h.count_genuine_citations(text, "Cross-Contract PRs"), 0)

    def test_creation_record_excluded(self) -> None:
        text = (
            "   - Charter home: `charter/pull-requests.md` § Cross-Contract PRs.\n"
            '2. `charter/pull-requests.md`: new § "Cross-Contract PRs" per process-change #2.\n'
        )
        self.assertEqual(h.count_genuine_citations(text, "Cross-Contract PRs"), 0)

    def test_audit_self_report_signal_shape_excluded(self) -> None:
        text = (
            "#1355's promotion-gate fix produced the first AUTO promotion "
            "(`wave-merge.md § Cross-Contract PRs`, `section_citations=5 >= 5`) "
            "— a gate that was structurally 0-of-25-eligible now passes.\n"
        )
        self.assertEqual(h.count_genuine_citations(text, "Cross-Contract PRs"), 0)

    def test_audit_self_report_verdict_prose_excluded(self) -> None:
        text = (
            "### Call 1 — the AUTO promotion (`wave-merge.md` § Cross-Contract PRs) "
            "→ NOT promoted\n"
        )
        self.assertEqual(h.count_genuine_citations(text, "Cross-Contract PRs"), 0)

    def test_audit_self_report_cited_nx_shape_excluded(self) -> None:
        text = (
            "`feedback_fixture_makes_guard_assertion_inert` flagged by two "
            "orthogonal instruments — `promotion_target=none` while cited 6x "
            "(stale opt-out)\n"
        )
        self.assertEqual(
            h.count_genuine_citations(text, "feedback_fixture_makes_guard_assertion_inert"), 0
        )

    def test_audit_self_report_size_sweep_shape_excluded(self) -> None:
        text = (
            "3 files flagged (advisory, non-blocking): `project_x.md`, "
            "`feedback_fixture_makes_guard_assertion_inert.md`, `feedback_y.md`.\n"
            "| feedback_fixture_makes_guard_assertion_inert.md | 22,005 B | 1d | Keep |\n"
        )
        self.assertEqual(
            h.count_genuine_citations(text, "feedback_fixture_makes_guard_assertion_inert"), 0
        )

    def test_wave_summary_listing_excluded(self) -> None:
        text = (
            "- Ontology rebuilds across the wave; charter updates (agents.md, "
            "hooks.md, issues.md) for single-session-team delegation pattern + "
            "Cross-Contract PRs § + Load-Bearing Followups §.\n"
        )
        self.assertEqual(h.count_genuine_citations(text, "Cross-Contract PRs"), 0)

    def test_empty_needle_returns_zero_not_corpus_length(self) -> None:
        """Mirrors `count_section_citations`'s blank-heading guard: an empty
        needle must never fall through to `str.count`'s `len(text) + 1`
        behavior."""
        text = "some reasonably long corpus text so the bug would be obvious\n" * 10
        self.assertEqual(h.count_genuine_citations(text, ""), 0)

    def test_mixed_corpus_counts_only_the_genuine_occurrence(self) -> None:
        """The wave-30 `Cross-Contract PRs` shape, reproduced as a fixture
        (not the live feedback log, which changes every wave): 2 creation
        records, 1 genuine application, 1 wave-summary listing, 1 forward
        reference, 3 self-generated audit/retro report lines. Honest count
        per the issue's own tracing: 1."""
        text = "\n".join(
            [
                "   - Charter home: `charter/pull-requests.md` § Cross-Contract PRs.",
                '2. `charter/pull-requests.md`: new § "Cross-Contract PRs" per process-change #2.',
                "- Cross-Contract cited: per Charter § Cross-Contract PRs, alembic merge "
                "migration is now in main (was P2W10 critical-path).",
                "- Ontology rebuilds across the wave; charter updates (agents.md, hooks.md, "
                "issues.md) for single-session-team delegation pattern + Cross-Contract PRs "
                "§ + Load-Bearing Followups §.",
                "Proposed location: charter `pull-requests.md` § Cross-Contract PRs OR new "
                "§ Design-Rationale Blocks.",
                "#1355's promotion-gate fix produced the first AUTO promotion in ~20 recorded "
                "waves (`wave-merge.md § Cross-Contract PRs`, `section_citations=5 >= 5`) — a "
                "gate that was structurally 0-of-25-eligible now passes.",
                "**1 AUTO · 0 DECIDE · 255 KEPT · 22 SUPERSEDED.** The AUTO is `wave-merge.md "
                "§ Cross-Contract PRs` (charter → skill, `section_citations=5 >= 5`) — the "
                "first AUTO promotion in ~20 recorded waves.",
                "### Call 1 — the AUTO promotion (`wave-merge.md` § Cross-Contract PRs) "
                "→ NOT promoted",
            ]
        )
        self.assertEqual(h.count_genuine_citations(text, "Cross-Contract PRs"), 1)


class CountGenuineCitationsBoundaryTests(unittest.TestCase):
    """#1450: boundary-aware scan. Two fixtures below FAIL against the
    pre-fix `text.find` implementation (a bare substring scan with no
    boundary check at all counts every literal occurrence not otherwise
    excluded by `_is_self_generated_occurrence`); the rest pin edge-case
    behavior the fix must NOT break, and are separately used to kill
    plausible incorrect variants of the fix (see the PR body's mutant
    table)."""

    def test_short_heading_substring_of_longer_hyphenated_heading_excluded(
        self,
    ) -> None:
        """FAILS PRE-FIX (bare `text.find`, no boundary check): the needle
        "Contract PRs" is a literal substring of "Cross-Contract PRs" (the
        heading tail after the hyphen), so the pre-fix scan finds it TWICE
        -- once embedded in the longer, hyphen-joined heading, once as the
        genuine standalone citation -- and neither occurrence trips any of
        the four `_is_self_generated_occurrence` exclusions, so pre-fix
        returns 2. Post-fix, the embedded occurrence is preceded by `-`,
        which the heading-continuation class treats as NOT a boundary (a
        plain `\\b` would wrongly treat `-` as a boundary here and miss
        this case entirely -- see `_HEADING_CONTINUATION_RE`'s docstring),
        so only the standalone occurrence counts: 1."""
        text = (
            "Per Charter § Cross-Contract PRs, alembic merge migration "
            "landed successfully. Contract PRs was filed as a separate "
            "item today.\n"
        )
        self.assertEqual(h.count_genuine_citations(text, "Contract PRs"), 1)

    def test_heading_embedded_in_prose_word_excluded(self) -> None:
        """FAILS PRE-FIX: needle "PRs" is a literal substring of the prose
        word "PRsomething", so the pre-fix bare scan counts it as a
        citation alongside the genuine "Cross-Contract PRs" occurrence,
        returning 2. Post-fix, "PRsomething"'s embedded match is followed
        immediately by the letter "o" -- a heading-continuation char, not
        a boundary -- so it is excluded: 1."""
        text = (
            "The PRsomething flag toggles behavior. Cross-Contract PRs "
            "was cited separately today.\n"
        )
        self.assertEqual(h.count_genuine_citations(text, "PRs"), 1)

    def test_citation_followed_by_punctuation_still_counts(self) -> None:
        """Does not fail against the literal pre-fix scan (which never
        checked boundaries), but pins the correct edge behavior against an
        over-strict variant of the fix that requires literal whitespace
        (rather than "not a heading-continuation char") on both sides --
        that variant would wrongly exclude all three of these, since none
        of them are followed by whitespace."""
        for suffix in (":", ",", ")"):
            with self.subTest(suffix=suffix):
                text = f"See Charter § Cross-Contract PRs{suffix} for details.\n"
                self.assertEqual(h.count_genuine_citations(text, "Cross-Contract PRs"), 1)

    def test_citation_inside_backticks_still_counts(self) -> None:
        """A backtick is not a heading-continuation char, so a citation
        wrapped in inline-code backticks still counts on both sides."""
        text = "See `Cross-Contract PRs` in the charter file.\n"
        self.assertEqual(h.count_genuine_citations(text, "Cross-Contract PRs"), 1)

    def test_citation_at_start_of_text_counts(self) -> None:
        text = "Cross-Contract PRs was the first thing mentioned today.\n"
        self.assertEqual(h.count_genuine_citations(text, "Cross-Contract PRs"), 1)

    def test_citation_at_end_of_text_ending_exactly_on_needle_counts(self) -> None:
        text = "Today's topic was Cross-Contract PRs"
        self.assertEqual(h.count_genuine_citations(text, "Cross-Contract PRs"), 1)

    def test_underscore_and_digit_continuation_excluded(self) -> None:
        """PR #1529 review item 1 (Nadia Khoury, merge-gate): the
        underscore and digit members of `_HEADING_CONTINUATION_RE`'s
        character class were the only two with no pinning fixture, and
        mutation testing showed the underscore branch is the one carrying
        the entire live-corpus behaviour change this PR produces --
        dropping `_` from the class restores all four affected
        `.claude/memory/` rows to their exact base counts while the rest
        of the suite stays green.

        Needle "feedback_x" is a genuine standalone citation in
        "feedback_x.md" (the character after the match is `.`, a
        boundary), but is a substring of a longer, underscore-joined slug
        in "feedback_x_y.md" (next char `_`) and of a longer,
        digit-suffixed slug in "feedback_x2.md" (next char `2`) -- both
        excluded because `_` and `2` are heading-continuation characters.
        Folding the digit case into this same fixture per the review
        (it "survives identically" to the underscore case) kills both
        the underscore-removed and the digits-removed mutants with one
        test."""
        text = (
            "cites feedback_x.md directly, and separately mentions "
            "feedback_x_y.md and feedback_x2.md, which are different notes.\n"
        )
        self.assertEqual(h.count_genuine_citations(text, "feedback_x"), 1)

    def test_non_overlapping_match_semantics_pinned(self) -> None:
        """PR #1529 review item 4 (Nadia Khoury, merge-gate, optional):
        `count_genuine_citations`'s docstring explicitly guarantees
        `str.count`-style non-overlapping-match semantics (`pos = end`
        after each match, whether or not it was counted), but nothing
        pinned it before this test. Needle "Retro Retro" against text
        "Retro Retro Retro" has a second, overlapping candidate match
        starting at index 6 (sharing the middle "Retro"); non-overlapping
        semantics must skip it, since after the first match (ending at
        index 11) the remaining text " Retro" (6 chars) is too short to
        contain the 11-char needle again. An `pos = idx + 1` mutant
        re-scans from index 1 and finds the overlapping match, taking the
        count from 1 to 2 with the rest of the suite still green. This
        line is unchanged from base -- a pre-existing hole the new
        docstring merely promotes into a stated promise."""
        text = "Retro Retro Retro"
        self.assertEqual(h.count_genuine_citations(text, "Retro Retro"), 1)


class CountSectionCitationsProvenanceTests(unittest.TestCase):
    """`count_section_citations` wired through the provenance filter."""

    def _section(self, **kwargs: object) -> h.CharterSection:
        defaults: dict[str, object] = {
            "path": "/fake/charter/wave-merge.md",
            "heading": "Cross-Contract PRs",
            "promotion_target": "skill",
            "body": "body",
            "promoted_to": "",
        }
        defaults.update(kwargs)
        return h.CharterSection(**defaults)  # type: ignore[arg-type]

    def test_wave30_shape_falls_below_threshold(self) -> None:
        """PRE-FIX: `count_section_citations` was a bare `text.count(...)`
        and returned 8 for this fixture (every literal heading occurrence,
        including the audit's own reporting of the AUTO verdict it produced).
        POST-FIX: only the one genuine application counts."""
        log = "\n".join(
            [
                "   - Charter home: `charter/pull-requests.md` § Cross-Contract PRs.",
                '2. `charter/pull-requests.md`: new § "Cross-Contract PRs" per process-change #2.',
                "- Cross-Contract cited: per Charter § Cross-Contract PRs, alembic merge "
                "migration is now in main (was P2W10 critical-path).",
                "- Ontology rebuilds across the wave; charter updates (agents.md, hooks.md, "
                "issues.md) for single-session-team delegation pattern + Cross-Contract PRs "
                "§ + Load-Bearing Followups §.",
                "Proposed location: charter `pull-requests.md` § Cross-Contract PRs OR new "
                "§ Design-Rationale Blocks.",
                "#1355's promotion-gate fix produced the first AUTO promotion in ~20 recorded "
                "waves (`wave-merge.md § Cross-Contract PRs`, `section_citations=5 >= 5`) — a "
                "gate that was structurally 0-of-25-eligible now passes.",
                "**1 AUTO · 0 DECIDE · 255 KEPT · 22 SUPERSEDED.** The AUTO is `wave-merge.md "
                "§ Cross-Contract PRs` (charter → skill, `section_citations=5 >= 5`) — the "
                "first AUTO promotion in ~20 recorded waves.",
                "### Call 1 — the AUTO promotion (`wave-merge.md` § Cross-Contract PRs) "
                "→ NOT promoted",
            ]
        )
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write(log)
            path = f.name
        try:
            citations = h.count_section_citations(self._section(), path)
            self.assertEqual(citations, 1, f"expected the honest count of 1, got {citations}")
            self.assertLess(citations, 5, "must fall below the wave-31 threshold of 5")
        finally:
            os.unlink(path)


class CountRetroCitationsProvenanceTests(unittest.TestCase):
    """`count_retro_citations` wired through the provenance filter."""

    def _mem(self, **kwargs: object) -> h.Memory:
        defaults: dict[str, object] = {
            "path": "/fake/feedback_fixture_makes_guard_assertion_inert.md",
            "name": "feedback_fixture_makes_guard_assertion_inert",
            "description": "",
            "type_": "feedback",
            "promotion_target": "none",
            "promotion_threshold": {"retro_citations": 3, "skill_invocations": 5},
            "referenced_in_retros": (),
            "status": "active",
            "superseded_by": "",
            "supersedes": "",
            "requires_decision": False,
            "body": "",
        }
        defaults.update(kwargs)
        return h.Memory(**defaults)  # type: ignore[arg-type]

    def test_size_sweep_shape_returns_honest_count(self) -> None:
        """PRE-FIX: `count_retro_citations` returned 7 for this fixture (the
        real note's shape, per the #1469 filing comment) — 2 genuine
        engagements plus 5 bookkeeping occurrences (3 size-sweep listings, 1
        size-sweep table row, 1 Step 7.7 self-report of the citation count).
        POST-FIX: the honest count is 2, still below the `2 * threshold`
        stale-opt-out line (threshold 3 -> line at 6)."""
        log = "\n".join(
            [
                "The wave derived the lesson from "
                "feedback_fixture_makes_guard_assertion_inert.md — the strongest "
                "candidate for charter promotion out of this wave.",
                "Further analysis of feedback_fixture_makes_guard_assertion_inert.md's "
                "failure mode confirms the fixture-realism principle.",
                "3 files flagged (advisory, non-blocking): `project_x.md`, "
                "`feedback_fixture_makes_guard_assertion_inert.md`, `feedback_y.md`.",
                "4 files flagged (advisory, non-blocking): `project_x.md`, "
                "`feedback_fixture_makes_guard_assertion_inert.md`, `feedback_z.md`.",
                "5 files flagged (advisory, non-blocking): `project_x.md`, "
                "`feedback_fixture_makes_guard_assertion_inert.md`, `feedback_w.md`.",
                "| feedback_fixture_makes_guard_assertion_inert.md | 22,005 B | 1d | Keep |",
                "`feedback_fixture_makes_guard_assertion_inert` flagged by two orthogonal "
                "instruments — `promotion_target=none` while cited 6x (stale opt-out)",
            ]
        )
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write(log)
            path = f.name
        try:
            citations = h.count_retro_citations(self._mem(), path)
            self.assertEqual(citations, 2, f"expected the honest count of 2, got {citations}")
            threshold = self._mem().promotion_threshold["retro_citations"]
            self.assertLess(
                citations, 2 * threshold, "must fall below the stale-opt-out 2x threshold line"
            )
        finally:
            os.unlink(path)

    def test_genuine_citation_alone_still_counts(self) -> None:
        log = (
            "The wave derived the lesson from "
            "feedback_fixture_makes_guard_assertion_inert.md — the strongest "
            "candidate for charter promotion out of this wave.\n"
        )
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write(log)
            path = f.name
        try:
            self.assertEqual(h.count_retro_citations(self._mem(), path), 1)
        finally:
            os.unlink(path)


class CorpusHealthTests(unittest.TestCase):
    """`check_corpus_health` — the clause (2)/(2a) NOT-MEASURED gate."""

    def test_missing_feedback_log_reports_a_reason(self) -> None:
        self.assertIsNotNone(h.check_corpus_health("/definitely/does/not/exist.md"))

    def test_present_readable_log_no_archive_is_healthy(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write("hi\n")
            path = f.name
        try:
            self.assertIsNone(h.check_corpus_health(path))
        finally:
            os.unlink(path)

    def test_unreadable_archive_file_reports_a_reason(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            live = os.path.join(d, "feedback_log.md")
            with open(live, "w", encoding="utf-8") as f:
                f.write("hi\n")
            arch = os.path.join(d, "archive")
            os.makedirs(arch)
            bad = os.path.join(arch, "feedback_log_phase-9.md")
            with open(bad, "wb") as f:
                f.write(b"\xff\xfe not valid utf-8 \x80\x81")
            reason = h.check_corpus_health(live)
            self.assertIsNotNone(reason)
            self.assertIn("feedback_log_phase-9.md", reason or "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
