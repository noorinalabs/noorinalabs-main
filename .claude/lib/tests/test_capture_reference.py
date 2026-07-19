"""Tests for capture_reference — the durable web-fetch → reference memory CLI (#1004).

Covers slug normalization/validation, the rendered frontmatter+body contract,
the MEMORY.md pointer line, the no-clobber guard (+ --force), fact-from-stdin
vs --fact, and the date default/validation.
"""

from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from capture_reference import (  # noqa: E402
    build_reference,
    main,
    normalize_slug,
    pointer_line,
)


class SlugTests(unittest.TestCase):
    def test_valid_snake_case(self) -> None:
        # snake_case is the actual corpus convention (all 98 files use underscores).
        self.assertEqual(normalize_slug("anthropic_lsp_docs"), "anthropic_lsp_docs")
        self.assertEqual(normalize_slug("ssh_topology"), "ssh_topology")

    def test_strips_reference_prefix(self) -> None:
        self.assertEqual(normalize_slug("reference_foo_bar"), "foo_bar")

    def test_rejects_invalid(self) -> None:
        # Uppercase, hyphens (not the corpus convention), doubled/edge underscores,
        # and spaces are all rejected.
        for bad in ["Foo", "foo-bar", "foo__bar", "_foo", "foo_", "foo bar"]:
            with self.assertRaises(ValueError):
                normalize_slug(bad)


class RenderTests(unittest.TestCase):
    def test_frontmatter_and_body_contract(self) -> None:
        text = build_reference(
            slug="x_api",
            title="X API",
            description="How X API auth works",
            url="https://example.com/docs",
            fact="Use a Bearer token in the Authorization header.",
            fetched="2026-07-19",
        )
        self.assertIn("name: reference_x_api", text)
        # FLAT top-level type/promotion_target/status — the shape the promotion-audit
        # code reads (helpers.py: fm.get("type"/...)); NOT nested metadata.type (#1006).
        self.assertIn("\ntype: reference\n", text)
        self.assertIn("promotion_target: none", text)
        self.assertIn("status: active", text)
        self.assertNotIn("metadata:", text)
        self.assertIn("# X API — reference (fetched 2026-07-19)", text)
        self.assertIn("**Source:** https://example.com/docs (fetched 2026-07-19)", text)
        self.assertIn("Bearer token", text)

    def test_description_newlines_flattened(self) -> None:
        text = build_reference(
            slug="s",
            title="T",
            description="line one\nline two",
            url="u",
            fact="f",
            fetched="2026-07-19",
        )
        # The frontmatter description must stay a single line (valid YAML scalar).
        desc_line = next(ln for ln in text.splitlines() if ln.startswith("description:"))
        self.assertEqual(desc_line, "description: line one line two")

    def test_pointer_line(self) -> None:
        self.assertEqual(
            pointer_line("x_api", "X API", "auth via bearer token"),
            "- [X API](reference_x_api.md) — auth via bearer token",
        )


class CliTests(unittest.TestCase):
    def _args(self, memory_dir: Path, **over: str) -> list[str]:
        base = {
            "--slug": "x_api",
            "--title": "X API",
            "--description": "How X API auth works",
            "--url": "https://example.com/docs",
            "--fact": "Bearer token in the Authorization header.",
            "--fetched": "2026-07-19",
            "--memory-dir": str(memory_dir),
        }
        base.update(over)
        argv = ["capture_reference.py"]
        for k, v in base.items():
            argv.extend([k, v])
        return argv

    def test_writes_file_and_prints_pointer(self) -> None:
        with TemporaryDirectory() as d:
            mem = Path(d)
            out = io.StringIO()
            old = sys.stdout
            sys.stdout = out
            try:
                rc = main(self._args(mem))
            finally:
                sys.stdout = old
            self.assertEqual(rc, 0)
            written = (mem / "reference_x_api.md").read_text(encoding="utf-8")
            self.assertIn("name: reference_x_api", written)
            self.assertIn("- [X API](reference_x_api.md) —", out.getvalue())

    def test_no_clobber_without_force(self) -> None:
        with TemporaryDirectory() as d:
            mem = Path(d)
            (mem / "reference_x_api.md").write_text("existing\n", encoding="utf-8")
            rc = main(self._args(mem))
            self.assertEqual(rc, 3)
            # Untouched.
            self.assertEqual((mem / "reference_x_api.md").read_text(), "existing\n")

    def test_force_flag_overwrites(self) -> None:
        with TemporaryDirectory() as d:
            mem = Path(d)
            (mem / "reference_x_api.md").write_text("existing\n", encoding="utf-8")
            argv = self._args(mem)
            argv.append("--force")
            out = io.StringIO()
            old = sys.stdout
            sys.stdout = out
            try:
                rc = main(argv)
            finally:
                sys.stdout = old
            self.assertEqual(rc, 0)
            self.assertIn("type: reference", (mem / "reference_x_api.md").read_text())

    def test_bad_slug_exits_2(self) -> None:
        with TemporaryDirectory() as d:
            rc = main(self._args(Path(d), **{"--slug": "Bad_Slug"}))
            self.assertEqual(rc, 2)

    def test_bad_date_exits_2(self) -> None:
        with TemporaryDirectory() as d:
            rc = main(self._args(Path(d), **{"--fetched": "07-19-2026"}))
            self.assertEqual(rc, 2)

    def test_missing_memory_dir_exits_2(self) -> None:
        rc = main(self._args(Path("/nonexistent/xyz-dir")))
        self.assertEqual(rc, 2)

    def test_fact_from_stdin(self) -> None:
        with TemporaryDirectory() as d:
            mem = Path(d)
            argv = [
                "capture_reference.py",
                "--slug",
                "s",
                "--title",
                "T",
                "--description",
                "desc",
                "--url",
                "u",
                "--fetched",
                "2026-07-19",
                "--memory-dir",
                str(mem),
            ]
            old_in, old_out = sys.stdin, sys.stdout
            sys.stdin = io.StringIO("fact from stdin")
            sys.stdout = io.StringIO()
            try:
                rc = main(argv)
            finally:
                sys.stdin, sys.stdout = old_in, old_out
            self.assertEqual(rc, 0)
            self.assertIn("fact from stdin", (mem / "reference_s.md").read_text())


if __name__ == "__main__":
    unittest.main()
