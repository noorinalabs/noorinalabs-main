"""Tests for upsert_status_keys.upsert_top_level_key.

Covers the main#332 fix: insertion point must skip past multi-line array /
object sibling values, not insert inside them.

Each test builds a small cross-repo-status.json-shaped fixture, calls
upsert_top_level_key, validates that the result:
  1. Parses as JSON.
  2. Contains the new key with the expected value.
  3. Preserves the sibling values unchanged (no truncation, no reorder).

Helper promoted to `.claude/lib/` per main#292 — the test moved with it
(same `parent.parent` import shape as the prior wave-scope/tests/ home).
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

# Helper lives at .claude/lib/upsert_status_keys.py; test is at
# .claude/lib/tests/test_*.py. parent.parent reaches the lib root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from upsert_status_keys import upsert_top_level_key  # noqa: E402


class UpsertSinglelineSiblingTests(unittest.TestCase):
    """Baseline — single-line sibling values (the case that always worked)."""

    def test_inserts_after_singleline_sibling(self):
        text = (
            "{\n"
            '  "phase": "phase-3",\n'
            '  "wave_8_active": true,\n'
            '  "wave_8_kicked_off_at": "2026-05-08T00:00:00Z"\n'
            "}\n"
        )
        out = upsert_top_level_key(text, "wave_8_scope", '"narrow"')
        parsed = json.loads(out)
        self.assertEqual(parsed["wave_8_scope"], "narrow")
        # Sibling values intact
        self.assertTrue(parsed["wave_8_active"])
        self.assertEqual(parsed["wave_8_kicked_off_at"], "2026-05-08T00:00:00Z")


class UpsertMultilineArraySiblingTests(unittest.TestCase):
    """main#332 reproducer — multi-line array sibling (wave_8_carry_forward)."""

    def test_inserts_after_multiline_array(self):
        text = (
            "{\n"
            '  "phase": "phase-3",\n'
            '  "wave_8_active": true,\n'
            '  "wave_8_carry_forward": [\n'
            '    "#341",\n'
            '    "#342"\n'
            "  ]\n"
            "}\n"
        )
        out = upsert_top_level_key(text, "wave_8_scope", '"narrow"')
        parsed = json.loads(out)
        self.assertEqual(parsed["wave_8_scope"], "narrow")
        # The array sibling is intact and not truncated/reordered
        self.assertEqual(parsed["wave_8_carry_forward"], ["#341", "#342"])
        # New key appears AFTER the array close in source text
        scope_pos = out.find('"wave_8_scope"')
        array_close_pos = out.find("  ]")
        self.assertGreater(scope_pos, array_close_pos)


class UpsertMultilineObjectSiblingTests(unittest.TestCase):
    """main#332 reproducer — multi-line object sibling (wave_8_work)."""

    def test_inserts_after_multiline_object(self):
        text = (
            "{\n"
            '  "phase": "phase-3",\n'
            '  "wave_8_work": {\n'
            '    "isnad-graph": ["#868", "#869"],\n'
            '    "deploy": ["#280"]\n'
            "  }\n"
            "}\n"
        )
        out = upsert_top_level_key(text, "wave_8_scope", '"narrow"')
        parsed = json.loads(out)
        self.assertEqual(parsed["wave_8_scope"], "narrow")
        # Object sibling is intact (both nested keys present, both arrays preserved)
        self.assertEqual(parsed["wave_8_work"]["isnad-graph"], ["#868", "#869"])
        self.assertEqual(parsed["wave_8_work"]["deploy"], ["#280"])


class UpsertNestedStructuresTests(unittest.TestCase):
    """Sibling has deeply nested object/array — depth tracking is correct."""

    def test_inserts_after_deeply_nested_sibling(self):
        text = (
            "{\n"
            '  "wave_8_work": {\n'
            '    "tiers": {\n'
            '      "tier_1": ["#86", "#88"],\n'
            '      "tier_2": {\n'
            '        "isnad-graph": ["#90"],\n'
            '        "deploy": ["#92", "#94"]\n'
            "      }\n"
            "    },\n"
            '    "meta": "ok"\n'
            "  }\n"
            "}\n"
        )
        out = upsert_top_level_key(text, "wave_8_scope", '"narrow"')
        parsed = json.loads(out)
        self.assertEqual(parsed["wave_8_scope"], "narrow")
        # The deeply nested structure round-trips intact
        self.assertEqual(parsed["wave_8_work"]["tiers"]["tier_2"]["deploy"], ["#92", "#94"])
        self.assertEqual(parsed["wave_8_work"]["meta"], "ok")


class UpsertStringsContainingBracketsTests(unittest.TestCase):
    """Sibling string values containing `[`, `]`, `{`, `}` must not confuse
    bracket-depth tracking. JSON string-escape state must be honored."""

    def test_bracket_chars_inside_strings(self):
        text = (
            "{\n"
            '  "wave_8_note": "scope is {tight, narrow} and [bounded]",\n'
            '  "wave_8_work": {\n'
            '    "label": "with {literal} braces and [brackets]",\n'
            '    "deploy": ["#280"]\n'
            "  }\n"
            "}\n"
        )
        out = upsert_top_level_key(text, "wave_8_scope", '"narrow"')
        parsed = json.loads(out)
        self.assertEqual(parsed["wave_8_scope"], "narrow")
        # String values with bracket chars are unchanged
        self.assertEqual(parsed["wave_8_note"], "scope is {tight, narrow} and [bounded]")
        self.assertEqual(parsed["wave_8_work"]["label"], "with {literal} braces and [brackets]")


class UpsertEscapedQuotesTests(unittest.TestCase):
    """Strings with escaped quotes inside multi-line values must not flip
    bracket-depth tracking's in_string state incorrectly."""

    def test_escaped_quotes_in_string_value(self):
        text = (
            "{\n"
            '  "wave_8_work": {\n'
            '    "note": "He said \\"yes\\" and {then}",\n'
            '    "deploy": ["#280"]\n'
            "  }\n"
            "}\n"
        )
        out = upsert_top_level_key(text, "wave_8_scope", '"narrow"')
        parsed = json.loads(out)
        self.assertEqual(parsed["wave_8_scope"], "narrow")
        self.assertEqual(parsed["wave_8_work"]["note"], 'He said "yes" and {then}')


class UpsertIdempotenceTests(unittest.TestCase):
    """Re-running upsert on a file that already has the new key should
    replace in place (single-line) — not append, not corrupt."""

    def test_rerun_replaces_in_place(self):
        text = (
            "{\n"
            '  "wave_8_active": true,\n'
            '  "wave_8_carry_forward": [\n'
            '    "#341"\n'
            "  ],\n"
            '  "wave_8_scope": "narrow"\n'
            "}\n"
        )
        out = upsert_top_level_key(text, "wave_8_scope", '"broad"')
        parsed = json.loads(out)
        self.assertEqual(parsed["wave_8_scope"], "broad")
        self.assertEqual(parsed["wave_8_carry_forward"], ["#341"])
        # File should NOT have duplicated the key
        self.assertEqual(out.count('"wave_8_scope"'), 1)


class UpsertFinalKeyNoTrailingCommaTests(unittest.TestCase):
    """When inserting after the LAST top-level key (no trailing comma on
    the sibling), the result must still be valid JSON."""

    def test_final_key_handling(self):
        text = '{\n  "phase": "phase-3",\n  "wave_8_active": true\n}\n'
        out = upsert_top_level_key(text, "wave_8_scope", '"narrow"')
        parsed = json.loads(out)
        self.assertEqual(parsed["wave_8_scope"], "narrow")
        self.assertTrue(parsed["wave_8_active"])


class UpsertMultiLineFinalKeyTests(unittest.TestCase):
    """Sibling is multi-line AND is the final top-level key (no trailing
    comma after the closing `]` or `}`)."""

    def test_multiline_final_array(self):
        text = '{\n  "phase": "phase-3",\n  "wave_8_carry_forward": [\n    "#341"\n  ]\n}\n'
        out = upsert_top_level_key(text, "wave_8_scope", '"narrow"')
        parsed = json.loads(out)
        self.assertEqual(parsed["wave_8_scope"], "narrow")
        self.assertEqual(parsed["wave_8_carry_forward"], ["#341"])


class UpsertNestedSiblingFalseMatchTests(unittest.TestCase):
    """main#456 regression — the sibling-finder must NOT match keys whose
    name happens to look like a wave_N_* sibling but is actually nested
    inside a multi-line value at the same indent level.

    Reproducer: pretty-printed JSON where the outer wave_N_scope dict has
    inner keys at 2-space indent (which happens when the user wrote a
    multi-line value with `json.dumps(value, indent=2)` or hand-formatted
    pretty JSON without re-indenting). The pre-#456 regex would match
    those nested keys and treat them as wave_N_* siblings, then call
    _find_value_end on the wrong position and insert IN THE MIDDLE of the
    wave_N_scope dict.

    These tests pin the structural-top-level filter so the insertion
    always lands at the genuine top level.
    """

    def test_nested_wave_key_at_2_space_indent_does_not_confuse_sibling_finder(self):
        """The reproducer that motivated #456. Nested `wave_11_inner_*` keys
        at the same 2-space indent as the outer `wave_11_scope` opener must
        NOT count as wave_11_* siblings — they're inside wave_11_scope's
        value, not at the top level."""
        text = (
            "{\n"
            '  "phase": "phase-3",\n'
            '  "wave_11_scope": {\n'
            '  "wave_11_inner_a": 1,\n'
            '  "wave_11_inner_b": 2\n'
            "  }\n"
            "}\n"
        )
        out = upsert_top_level_key(text, "wave_11_meta_issue", "447")
        parsed = json.loads(out)
        # The new key must land at TOP LEVEL, not inside wave_11_scope.
        self.assertEqual(parsed.get("wave_11_meta_issue"), 447)
        # wave_11_scope's nested keys must remain unchanged.
        self.assertEqual(
            parsed.get("wave_11_scope"),
            {"wave_11_inner_a": 1, "wave_11_inner_b": 2},
        )

    def test_nested_wave_key_replace_does_not_target_nested_match(self):
        """When upserting `wave_11_inner_a` at top level (with no top-level
        key by that name), the regex MUST NOT match the nested `wave_11_inner_a`
        inside `wave_11_scope`. The insertion should add a NEW top-level key."""
        text = '{\n  "phase": "phase-3",\n  "wave_11_scope": {\n  "wave_11_inner_a": 1\n  }\n}\n'
        out = upsert_top_level_key(text, "wave_11_inner_a", "999")
        parsed = json.loads(out)
        # Top-level wave_11_inner_a should be 999.
        self.assertEqual(parsed["wave_11_inner_a"], 999)
        # Nested wave_11_inner_a inside wave_11_scope should STILL be 1.
        self.assertEqual(parsed["wave_11_scope"]["wave_11_inner_a"], 1)

    def test_nested_wave_key_at_4_space_indent_still_ignored(self):
        """Already worked pre-#456 (indent mismatch) but pinned as a guard."""
        text = (
            "{\n"
            '  "phase": "phase-3",\n'
            '  "wave_11_scope": {\n'
            '    "wave_11_inner_a": 1,\n'
            '    "wave_11_inner_b": 2\n'
            "  }\n"
            "}\n"
        )
        out = upsert_top_level_key(text, "wave_11_meta_issue", "447")
        parsed = json.loads(out)
        self.assertEqual(parsed["wave_11_meta_issue"], 447)
        self.assertEqual(
            parsed["wave_11_scope"],
            {"wave_11_inner_a": 1, "wave_11_inner_b": 2},
        )

    def test_sequenced_upsert_after_inserting_multiline_dict(self):
        """The 5-key call shape from the #456 issue body. Sequence:
        1. start with compact-inline wave_11_* keys
        2. upsert a multi-line dict for wave_11_scope
        3. upsert another wave_11_* key

        The multi-line dict insertion must not leave the text in a state
        where the next upsert's sibling-finder mis-matches a nested key.
        """
        text = '{\n  "phase": "phase-3",\n  "wave_11_active": true\n}\n'
        # Step 1: insert a multi-line dict value (as the helper produces
        # when the json_value arg is pretty-printed).
        ml_dict = '{\n    "wave_11_inner_a": 1,\n    "wave_11_inner_b": 2\n  }'
        text2 = upsert_top_level_key(text, "wave_11_scope", ml_dict)
        json.loads(text2)  # must parse
        # Step 2: insert another wave_11_* key
        text3 = upsert_top_level_key(text2, "wave_11_meta_issue", "447")
        parsed = json.loads(text3)
        self.assertEqual(parsed["wave_11_meta_issue"], 447)
        self.assertEqual(
            parsed["wave_11_scope"],
            {"wave_11_inner_a": 1, "wave_11_inner_b": 2},
        )


class IsTopLevelPositionTests(unittest.TestCase):
    """Pure-function coverage for `_is_top_level_position` — the depth
    walker that powers the #456 fix."""

    def test_inside_outer_object_is_top_level(self):
        from upsert_status_keys import _is_top_level_position

        text = '{\n  "a": 1\n}\n'
        # Position of `"a"` is at depth 1 (inside the outer `{`).
        pos = text.index('"a"')
        self.assertTrue(_is_top_level_position(text, pos))

    def test_inside_nested_object_is_not_top_level(self):
        from upsert_status_keys import _is_top_level_position

        text = '{\n  "outer": {\n    "inner": 1\n  }\n}\n'
        pos = text.index('"inner"')
        self.assertFalse(_is_top_level_position(text, pos))

    def test_inside_nested_array_is_not_top_level(self):
        from upsert_status_keys import _is_top_level_position

        text = '{\n  "list": [\n    "item"\n  ]\n}\n'
        pos = text.index('"item"')
        self.assertFalse(_is_top_level_position(text, pos))

    def test_inside_string_value_is_not_top_level(self):
        from upsert_status_keys import _is_top_level_position

        text = '{\n  "note": "contains { brace } chars"\n}\n'
        # Position INSIDE the string value
        pos = text.index("brace")
        self.assertFalse(_is_top_level_position(text, pos))

    def test_brace_chars_inside_strings_dont_change_depth(self):
        from upsert_status_keys import _is_top_level_position

        text = '{\n  "a": "before {b} brace",\n  "real_top": 1\n}\n'
        pos = text.index('"real_top"')
        self.assertTrue(_is_top_level_position(text, pos))


if __name__ == "__main__":
    unittest.main()
