"""Tests for lint_checksums_consumers — the structural gate for #1284.

The lint exists because this defect class has no loud failure: a hand-rolled
read of `ontology/checksums.json` that gets the schema wrong returns `0` dirty
files, and `0` is also the healthy value. So the tests here are mostly about
DISCRIMINATION — that the lint separates the four real production consumers
(which delegate and must stay silent) from a re-derived read (which must not),
and that every outcome it cannot determine leaves by a non-zero door.

Fixtures are written to temp files rather than asserted as strings wherever
the path itself is part of what is under test (the `tests/` rule-scoping, the
allowlist), because the path is an input to the lint, not decoration.
"""

from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import lint_checksums_consumers as lint  # noqa: E402

# The pragma token is assembled at runtime, never written as one literal in
# this file. A literal would be a real pragma in a real scanned file — this
# module is inside the lint's own scan set — and the `unreasoned-allow-pragma`
# rule would fire on the fixture. Building it here keeps the lint honest about
# its own source.
_ALLOW = "checksums-consumers:" + " allow"


@contextmanager
def _tmp_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@contextmanager
def _capture():
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        yield out, err


def _rules(findings) -> list[str]:
    return [f.rule for f in findings]


class DirtyPredicateRuleTests(unittest.TestCase):
    """The predicate is `last_tracked != last_resolved` and it has ONE home."""

    def test_direct_subscript_comparison_is_flagged(self) -> None:
        src = 'def dirty(e):\n    return e["last_tracked"] != e["last_resolved"]\n'
        findings = lint.check_python_text("hooks/new_reader.py", src)
        self.assertEqual(_rules(findings), [lint.RULE_PREDICATE])
        self.assertEqual(findings[0].lineno, 2)

    def test_get_form_is_flagged(self) -> None:
        src = 'def dirty(e):\n    return e.get("last_tracked", "") == e.get("last_resolved", "")\n'
        self.assertEqual(_rules(lint.check_python_text("h.py", src)), [lint.RULE_PREDICATE])

    def test_attribute_form_is_flagged(self) -> None:
        src = "def dirty(e):\n    return e.last_tracked != e.last_resolved\n"
        self.assertEqual(_rules(lint.check_python_text("h.py", src)), [lint.RULE_PREDICATE])

    def test_comparison_through_locals_is_flagged(self) -> None:
        """The indirected shape — the one a naive re-implementation actually writes."""
        src = (
            "def dirty(e):\n"
            '    tracked = e["last_tracked"]\n'
            '    resolved = e.get("last_resolved", "")\n'
            "    return tracked != resolved\n"
        )
        findings = lint.check_python_text("h.py", src)
        self.assertEqual(_rules(findings), [lint.RULE_PREDICATE])
        self.assertEqual(findings[0].lineno, 4)

    def test_single_field_comparison_is_not_flagged(self) -> None:
        """The tracker's own write decision: current hash vs the tracked one.

        `existing.get("last_tracked") == sha` asks whether the FILE changed,
        not whether the entry is resolved. It is a legitimately different
        comparison, it must keep working, and it is NOT suppressed by an
        allowlist — the rule simply requires both fields.
        """
        src = 'def changed(existing, sha):\n    return existing.get("last_tracked") == sha\n'
        self.assertEqual(lint.check_python_text("hooks/ontology_tracker.py", src), [])

    def test_resolved_alone_is_not_flagged(self) -> None:
        src = 'def done(e):\n    return e.get("last_resolved") == ""\n'
        self.assertEqual(lint.check_python_text("h.py", src), [])

    def test_membership_and_ordering_comparisons_are_not_flagged(self) -> None:
        """Only equality/inequality is the predicate; `in` / `<` are other questions."""
        src = (
            "def f(e, keys):\n"
            '    a = "last_tracked" in keys and "last_resolved" in keys\n'
            '    b = e["last_tracked"] < e["last_resolved"]\n'
            "    return a, b\n"
        )
        self.assertEqual(lint.check_python_text("h.py", src), [])

    def test_dict_literals_are_not_comparisons(self) -> None:
        """Test fixtures build entries constantly; building one is not asking a question."""
        src = 'ENTRY = {"last_tracked": "a", "last_resolved": "a"}\n'
        self.assertEqual(lint.check_python_text("h.py", src), [])


class LedgerReadRuleTests(unittest.TestCase):
    def test_read_text_of_the_ledger_is_flagged(self) -> None:
        src = (
            "import json\n"
            "def load(root):\n"
            '    path = root / "ontology" / "checksums.json"\n'
            '    return json.loads(path.read_text(encoding="utf-8"))\n'
        )
        findings = lint.check_python_text("hooks/new_reader.py", src)
        self.assertEqual(_rules(findings), [lint.RULE_LEDGER_READ])

    def test_open_of_the_ledger_is_flagged(self) -> None:
        src = 'import json\ndef load():\n    return json.load(open("ontology/checksums.json"))\n'
        self.assertEqual(_rules(lint.check_python_text("h.py", src)), [lint.RULE_LEDGER_READ])

    def test_building_the_path_and_delegating_is_not_flagged(self) -> None:
        """What all four converted consumers do — and must keep doing."""
        src = (
            "import checksums_io\n"
            "def staleness(root):\n"
            '    path = root / "ontology" / "checksums.json"\n'
            "    return checksums_io.read_status(path)\n"
        )
        self.assertEqual(lint.check_python_text("hooks/session_start.py", src), [])

    def test_taint_does_not_leak_across_functions(self) -> None:
        """`smart_grep_ontology.py`'s shape: one local name, two different files.

        That module binds a local called `path` to the ledger in
        `_dirty_files` and to `structural/code-graph.json` in `_load_graph`,
        then legitimately reads the second. A module-global taint set makes
        the second read look like a ledger read — a false positive on a real,
        correct consumer, which is how a lint gets switched off.

        The ledger-binding function is deliberately placed FIRST here. Source
        order is incidental to the property (a name must not escape its
        scope in EITHER direction), but it is not incidental to the test: with
        the reads in the other order a module-global taint set has not yet
        seen the ledger binding when it reaches the code-graph read, so the
        bug hides. The real module happens to be in that forgiving order
        today — which is exactly why the fixture is not.
        """
        src = (
            "import json\n"
            "import checksums_io\n"
            "def _dirty_files(d):\n"
            '    path = d / "checksums.json"\n'
            "    return checksums_io.read_status(path)\n"
            "def _load_graph(d):\n"
            '    path = d / "structural" / "code-graph.json"\n'
            '    return json.loads(path.read_text(encoding="utf-8"))\n'
        )
        self.assertEqual(lint.check_python_text("hooks/smart_grep_ontology.py", src), [])

    def test_a_read_under_tests_is_exempt_but_the_predicate_is_not(self) -> None:
        """The rule-scoped asymmetry, stated as one test.

        A test that seeds a ledger and reads it back is asserting on the
        writer's output. A test that RE-DERIVES the predicate is how a wrong
        reader gets confirmed by a test computing the same wrong answer twice.
        """
        read_src = (
            "import json\n"
            "def check(tmp):\n"
            '    path = tmp / "checksums.json"\n'
            '    return json.loads(path.read_text(encoding="utf-8"))\n'
        )
        predicate_src = 'def dirty(e):\n    return e["last_tracked"] != e["last_resolved"]\n'
        self.assertEqual(lint.check_python_text("lib/tests/test_thing.py", read_src), [])
        self.assertEqual(
            _rules(lint.check_python_text("lib/tests/test_thing.py", predicate_src)),
            [lint.RULE_PREDICATE],
        )

    def test_the_tests_exemption_does_not_match_a_lookalike_directory(self) -> None:
        src = (
            "import json\n"
            "def check(tmp):\n"
            '    path = tmp / "checksums.json"\n'
            '    return json.loads(path.read_text(encoding="utf-8"))\n'
        )
        self.assertEqual(
            _rules(lint.check_python_text("lib/latest/thing.py", src)), [lint.RULE_LEDGER_READ]
        )


class SkillProseRuleTests(unittest.TestCase):
    def test_cat_of_the_ledger_in_a_bash_block_is_flagged(self) -> None:
        md = "Step 1:\n\n```bash\ncat ontology/checksums.json\n```\n"
        findings = lint.check_markdown_text("SKILL.md", md)
        self.assertEqual(_rules(findings), [lint.RULE_SKILL_READ])
        self.assertEqual(findings[0].lineno, 4)

    def test_jq_pipeline_is_flagged(self) -> None:
        md = '```bash\ncat ontology/checksums.json | jq ".files"\n```\n'
        self.assertEqual(_rules(lint.check_markdown_text("SKILL.md", md)), [lint.RULE_SKILL_READ])

    def test_read_tool_instruction_in_prose_is_flagged(self) -> None:
        """The live one this lint found: `/handoff` step 1, unconverted at HEAD."""
        md = "**Ontology staleness:**\n- Read `ontology/checksums.json` - count dirty files\n"
        findings = lint.check_markdown_text("SKILL.md", md)
        self.assertEqual(_rules(findings), [lint.RULE_SKILL_READ])
        self.assertEqual(findings[0].lineno, 2)

    def test_inline_json_load_is_flagged(self) -> None:
        recipe = "python3 -c 'import json; json.load(open(\"ontology/checksums.json\"))'"
        md = f"```bash\n{recipe}\n```\n"
        self.assertEqual(_rules(lint.check_markdown_text("SKILL.md", md)), [lint.RULE_SKILL_READ])

    def test_moving_the_file_is_not_reading_it(self) -> None:
        """`wave-start/SKILL.md` stashes the ledger — that is not a predicate read."""
        md = "```bash\ngit stash push -- cross-repo-status.json ontology/checksums.json\n```\n"
        self.assertEqual(lint.check_markdown_text("SKILL.md", md), [])

    def test_invoking_the_sanctioned_reader_is_not_flagged(self) -> None:
        recipe = "python3 .claude/lib/checksums_io.py status --checksums ontology/checksums.json"
        md = f"```bash\n{recipe}\n```\n"
        self.assertEqual(lint.check_markdown_text("SKILL.md", md), [])

    def test_a_comment_explaining_the_bug_does_not_self_trigger(self) -> None:
        md = "```bash\n# never: cat ontology/checksums.json — see #1142\npwd\n```\n"
        self.assertEqual(lint.check_markdown_text("SKILL.md", md), [])

    def test_prose_naming_the_ledger_without_reading_it_is_not_flagged(self) -> None:
        md = "A file is dirty when `last_tracked != last_resolved` in `checksums.json`.\n"
        self.assertEqual(lint.check_markdown_text("SKILL.md", md), [])


class PragmaEscapeHatchTests(unittest.TestCase):
    def test_a_reasoned_pragma_suppresses_the_finding(self) -> None:
        src = (
            "def dirty(e):\n"
            f"    # {_ALLOW} - migration shim, removed by #9999\n"
            '    return e["last_tracked"] != e["last_resolved"]\n'
        )
        self.assertEqual(lint.check_python_text("h.py", src), [])

    def test_a_same_line_pragma_suppresses(self) -> None:
        src = (
            "def dirty(e):\n"
            '    return e["last_tracked"] != e["last_resolved"]  '
            f"# {_ALLOW} - migration shim, removed by #9999\n"
        )
        self.assertEqual(lint.check_python_text("h.py", src), [])

    def test_a_bare_pragma_suppresses_nothing_and_is_itself_reported(self) -> None:
        """The hatch cannot be a magic word you type to make the lint quiet."""
        src = f'def dirty(e):\n    # {_ALLOW}\n    return e["last_tracked"] != e["last_resolved"]\n'
        rules = _rules(lint.check_python_text("h.py", src))
        self.assertIn(lint.RULE_PREDICATE, rules)
        self.assertIn(lint.RULE_BARE_PRAGMA, rules)

    def test_a_markdown_pragma_suppresses(self) -> None:
        md = (
            f"<!-- {_ALLOW} - documented counter-example for the lint itself -->\n"
            "```bash\n"
            "cat ontology/checksums.json\n"
            "```\n"
        )
        self.assertEqual(lint.check_markdown_text("SKILL.md", md), [])


class AllowlistTests(unittest.TestCase):
    def test_the_sanctioned_module_is_exempt_by_the_allowlist_not_by_luck(self) -> None:
        """`checksums_io.py` contains the predicate — the allowlist is what excuses it.

        Read at its real path: silent. Read at any other path: flagged. If
        this were passing because the rule cannot see the predicate, both
        halves would be silent.
        """
        source = (lint.repo_root() / ".claude/lib/checksums_io.py").read_text(encoding="utf-8")
        self.assertEqual(lint.check_python_text(".claude/lib/checksums_io.py", source), [])
        moved = _rules(lint.check_python_text(".claude/lib/copied_reader.py", source))
        self.assertIn(lint.RULE_PREDICATE, moved)

    def test_allowlist_entries_are_rule_scoped_not_blanket(self) -> None:
        rules, reason = lint.ALLOWLIST[".claude/lib/checksums_io.py"]
        self.assertEqual(rules, frozenset({lint.RULE_PREDICATE, lint.RULE_LEDGER_READ}))
        self.assertTrue(reason.strip())
        self.assertNotIn(".claude/hooks/ontology_tracker.py", lint.ALLOWLIST)

    def test_every_allowlist_entry_exists_on_disk(self) -> None:
        self.assertEqual(lint.check_allowlist(), [])


class RealConsumerTests(unittest.TestCase):
    """The production sites, scanned as they actually are — no fixture stand-ins.

    These four are the entire code consumer-set at HEAD, plus the writer. A
    lint that flags any of them is unusable and would be turned off; a lint
    that flags none of them for the wrong reason is not measuring anything,
    which is what `AllowlistTests` and the mutation table guard against.
    """

    REAL = [
        ".claude/hooks/session_start.py",
        ".claude/hooks/session_handoff.py",
        ".claude/hooks/smart_grep_ontology.py",
        ".claude/hooks/ontology_tracker.py",
        ".claude/lib/checksums_io.py",
        ".claude/lib/check_checksums_ascii.py",
        ".claude/skills/session-start/SKILL.md",
        ".claude/skills/ontology-rebuild/SKILL.md",
        ".claude/skills/ontology-librarian/SKILL.md",
        ".claude/skills/handoff/SKILL.md",
        ".claude/skills/wave-start/SKILL.md",
    ]

    def test_every_real_consumer_is_clean(self) -> None:
        for rel in self.REAL:
            path = lint.repo_root() / rel
            with self.subTest(path=rel):
                self.assertTrue(path.is_file(), f"{rel} moved — this test is now vacuous")
                self.assertEqual([str(f) for f in lint.check_file(path)], [])

    def test_the_tracker_is_scanned_by_the_predicate_rule(self) -> None:
        """Its silence is a verdict, not an exemption (#1284 acceptance criterion).

        `ontology_tracker.py` is the writer and it does hold a
        `last_tracked` comparison. It passes because that comparison names
        ONE field. Pinning its absence from the allowlist is what makes the
        negative test above mean something.
        """
        self.assertNotIn(".claude/hooks/ontology_tracker.py", lint.ALLOWLIST)
        source = (lint.repo_root() / ".claude/hooks/ontology_tracker.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("last_tracked", source, "the fixture premise: the file does compare it")
        self.assertEqual(lint.check_python_text(".claude/hooks/ontology_tracker.py", source), [])


class CliChannelTests(unittest.TestCase):
    """Both channels a caller consumes: the rendered verdict and the exit code.

    Wave-31 bar clause 2/2a — the could-not-evaluate outcomes must be
    non-zero AND rendered as NOT EVALUATED. A lint that scanned nothing is
    not a clean lint.
    """

    def test_clean_scan_exits_zero_and_says_so(self) -> None:
        with _tmp_dir() as tmp:
            good = tmp / "good.py"
            good.write_text("x = 1\n", encoding="utf-8")
            with _capture() as (out, _err):
                rc = lint.main(["lint", str(good)])
            self.assertEqual(rc, lint.EXIT_CLEAN)
            self.assertIn("VERDICT: CLEAN", out.getvalue())
            self.assertIn("1 file(s) scanned", out.getvalue())

    def test_findings_exit_one_and_name_the_site(self) -> None:
        with _tmp_dir() as tmp:
            bad = tmp / "bad.py"
            bad.write_text(
                'def dirty(e):\n    return e["last_tracked"] != e["last_resolved"]\n',
                encoding="utf-8",
            )
            with _capture() as (out, _err):
                rc = lint.main(["lint", str(bad)])
            self.assertEqual(rc, lint.EXIT_FINDINGS)
            self.assertIn("VERDICT: FINDINGS", out.getvalue())
            self.assertIn(lint.RULE_PREDICATE, out.getvalue())

    def test_no_paths_is_non_zero_and_rendered_as_not_evaluated(self) -> None:
        with _capture() as (_out, err):
            rc = lint.main(["lint"])
        self.assertNotEqual(rc, lint.EXIT_CLEAN)
        self.assertEqual(rc, lint.EXIT_USAGE)
        self.assertIn("NOT EVALUATED", err.getvalue())

    def test_an_unparseable_file_is_not_evaluated_not_clean(self) -> None:
        """A file the lint cannot parse is the "cannot evaluate" case, and 0 is wrong."""
        with _tmp_dir() as tmp:
            broken = tmp / "broken.py"
            broken.write_text("def (:\n", encoding="utf-8")
            with _capture() as (_out, err):
                rc = lint.main(["lint", str(broken)])
            self.assertEqual(rc, lint.EXIT_NOT_EVALUATED)
            self.assertIn("NOT EVALUATED", err.getvalue())
            self.assertIn("could not parse", err.getvalue())

    def test_nothing_scannable_is_not_evaluated(self) -> None:
        """`find` matching only unsupported suffixes must not read as a clean run."""
        with _tmp_dir() as tmp:
            other = tmp / "config.yaml"
            other.write_text("a: 1\n", encoding="utf-8")
            with _capture() as (_out, err):
                rc = lint.main(["lint", str(other)])
            self.assertEqual(rc, lint.EXIT_NOT_EVALUATED)
            self.assertIn("NOT EVALUATED", err.getvalue())

    def test_a_stale_allowlist_entry_is_not_evaluated(self) -> None:
        """If an exempted file has been renamed away, every verdict below it is guesswork."""
        original = dict(lint.ALLOWLIST)
        lint.ALLOWLIST[".claude/lib/renamed_away.py"] = (frozenset({lint.RULE_PREDICATE}), "gone")
        try:
            with _tmp_dir() as tmp:
                good = tmp / "good.py"
                good.write_text("x = 1\n", encoding="utf-8")
                with _capture() as (_out, err):
                    rc = lint.main(["lint", str(good)])
        finally:
            lint.ALLOWLIST.clear()
            lint.ALLOWLIST.update(original)
        self.assertEqual(rc, lint.EXIT_NOT_EVALUATED)
        self.assertIn("NOT EVALUATED", err.getvalue())
        self.assertIn("renamed_away.py", err.getvalue())

    def test_a_missing_path_is_non_zero(self) -> None:
        with _capture() as (_out, err):
            rc = lint.main(["lint", "/nonexistent/nope.py"])
        self.assertEqual(rc, lint.EXIT_USAGE)
        self.assertIn("NOT EVALUATED", err.getvalue())

    def test_the_four_exit_codes_are_distinct(self) -> None:
        codes = {
            lint.EXIT_CLEAN,
            lint.EXIT_FINDINGS,
            lint.EXIT_USAGE,
            lint.EXIT_NOT_EVALUATED,
        }
        self.assertEqual(len(codes), 4)


if __name__ == "__main__":
    unittest.main()
