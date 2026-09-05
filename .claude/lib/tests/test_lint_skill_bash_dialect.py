"""Tests for lint_skill_bash_dialect — the bash-only `[ \\< ]` / `[ \\> ]` guard
(noorinalabs-main#1485).

Verifies the lint flags `[ "$A" \\< "$B" ]` inside a shell-tagged (or
untagged) fenced code block, ignores the same text in prose outside a code
fence (so a docstring or issue body explaining the bug cannot self-trigger),
and passes clean on the actual `wave-kickoff` skill after the #1485 fix.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lint_skill_bash_dialect import (  # noqa: E402
    check_markdown_text,
    main,
)

_BASH_BLOCK = """### Step 0a

```bash
if [ -n "$PRIOR_RETRO_TS" ] && [ "$SCOPE_TS" \\< "$PRIOR_RETRO_TS" ]; then
  echo "stale"
fi
```
"""


class BashOnlyOperatorIsFlagged(unittest.TestCase):
    def test_lt_operator_in_bash_block_flagged(self) -> None:
        v = check_markdown_text("SKILL.md", _BASH_BLOCK)
        self.assertEqual(len(v), 1)
        self.assertEqual(v[0].lineno, 4)

    def test_gt_operator_in_bash_block_flagged(self) -> None:
        md = """```bash
if [ "$A" \\> "$B" ]; then echo hi; fi
```
"""
        v = check_markdown_text("SKILL.md", md)
        self.assertEqual(len(v), 1)

    def test_untagged_fence_is_scanned(self) -> None:
        # Several skills in this repo write bash recipes in a bare ``` fence.
        md = """```
if [ "$A" \\< "$B" ]; then echo hi; fi
```
"""
        v = check_markdown_text("SKILL.md", md)
        self.assertEqual(len(v), 1)

    def test_sh_and_zsh_tagged_fences_are_scanned(self) -> None:
        for lang in ("sh", "zsh", "shell"):
            md = f"""```{lang}
if [ "$A" \\< "$B" ]; then echo hi; fi
```
"""
            v = check_markdown_text("SKILL.md", md)
            self.assertEqual(len(v), 1, f"expected a hit for lang={lang!r}")

    def test_two_violations_in_one_block(self) -> None:
        md = """```bash
if [ "$A" \\< "$B" ]; then echo one; fi
if [ "$C" \\> "$D" ]; then echo two; fi
```
"""
        v = check_markdown_text("SKILL.md", md)
        self.assertEqual(len(v), 2)


class CompliantIsNotFlagged(unittest.TestCase):
    def test_correct_sort_based_comparison_not_flagged(self) -> None:
        md = """```bash
if [ "$(printf '%s\\n%s\\n' "$A" "$B" | sort | head -1)" = "$A" ]; then
  echo "A is earlier"
fi
```
"""
        self.assertEqual(check_markdown_text("SKILL.md", md), [])

    def test_prose_outside_code_block_ignored(self) -> None:
        # A sentence *explaining* the bug (e.g. this docstring, or an issue
        # body) must not self-trigger — only fenced code is in scope.
        md = 'The bug is `[ "$A" \\< "$B" ]`, which errors under zsh.\n'
        self.assertEqual(check_markdown_text("SKILL.md", md), [])

    def test_non_shell_fenced_block_ignored(self) -> None:
        md = """```json
{"note": "[ \\"$A\\" \\\\< \\"$B\\" ]"}
```
"""
        self.assertEqual(check_markdown_text("SKILL.md", md), [])

    def test_python_comparison_operators_not_flagged(self) -> None:
        # Plain `<`/`>` (unescaped, outside `[ ]`) is ordinary shell/python
        # and must never be flagged — only the escaped form inside `[ ]`.
        md = """```bash
if [ "$A" -lt "$B" ]; then echo hi; fi
python3 -c 'print(1 < 2)'
```
"""
        self.assertEqual(check_markdown_text("SKILL.md", md), [])

    def test_shell_comment_explaining_the_bug_not_flagged(self) -> None:
        # A code comment *explaining* the operator (exactly the shape of the
        # #1485 fix's own commentary in wave-kickoff/SKILL.md) must not
        # self-trigger — only executable lines are in scope.
        md = """```bash
# `[ "$A" \\< "$B" ]` is a bash-only string-comparison operator inside `[ ]`.
echo "fixed"
```
"""
        self.assertEqual(check_markdown_text("SKILL.md", md), [])


class CliExitCodes(unittest.TestCase):
    def test_usage_error_no_args(self) -> None:
        self.assertEqual(main(["lint_skill_bash_dialect.py"]), 2)

    def test_missing_file_errors(self) -> None:
        self.assertEqual(main(["lint_skill_bash_dialect.py", "/no/such/file.md"]), 2)

    def test_clean_file_passes(self) -> None:
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as fh:
            fh.write("```bash\necho hi\n```\n")
            name = fh.name
        try:
            self.assertEqual(main(["lint_skill_bash_dialect.py", name]), 0)
        finally:
            Path(name).unlink()

    def test_violating_file_returns_1(self) -> None:
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as fh:
            fh.write(_BASH_BLOCK)
            name = fh.name
        try:
            self.assertEqual(main(["lint_skill_bash_dialect.py", name]), 1)
        finally:
            Path(name).unlink()

    def test_real_wave_kickoff_skill_is_clean_after_1485_fix(self) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        skill = repo_root / ".claude" / "skills" / "wave-kickoff" / "SKILL.md"
        if skill.is_file():
            self.assertEqual(main(["lint_skill_bash_dialect.py", str(skill)]), 0)

    def test_all_skill_files_are_clean(self) -> None:
        # Repo-wide guard: every skill markdown file, not just wave-kickoff.
        repo_root = Path(__file__).resolve().parents[3]
        skills_dir = repo_root / ".claude" / "skills"
        if not skills_dir.is_dir():
            return
        files = sorted(str(p) for p in skills_dir.rglob("*.md"))
        if files:
            self.assertEqual(main(["lint_skill_bash_dialect.py", *files]), 0)


if __name__ == "__main__":
    unittest.main()
