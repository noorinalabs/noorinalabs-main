"""Tests for upsert_status_keys.upsert_top_level_key.

Covers the main#332 fix: insertion point must skip past multi-line array /
object sibling values, not insert inside them.

Each test builds a small cross-repo-status.json-shaped fixture, calls
upsert_top_level_key, validates that the result:
  1. Parses as JSON.
  2. Contains the new key with the expected value.
  3. Preserves the sibling values unchanged (no truncation, no reorder).
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
