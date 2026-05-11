#!/usr/bin/env python3
"""Tests for validate_commit_identity hook.

Covers the W9 parent+child roster merge feature (issue #112 part a) plus
regression coverage for the pre-existing cross-repo `cd <path>` detection.

Run: python3 -m pytest .claude/hooks/tests/test_validate_commit_identity.py -v
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
sys.path.insert(0, str(_HOOKS_DIR))

import validate_commit_identity as hook  # noqa: E402


def _git_init(path: Path) -> None:
    """Init a bare git repo at `path` by creating `.git` as a dir stub.

    We don't need `git` to work — the hook only checks `(path / ".git").exists()`.
    Creating `.git` as a directory satisfies the check deterministically and
    without spawning subprocesses.
    """
    (path / ".git").mkdir(parents=True, exist_ok=True)


def _write_roster(repo_path: Path, roster: dict[str, str]) -> None:
    team_dir = repo_path / ".claude" / "team"
    team_dir.mkdir(parents=True, exist_ok=True)
    (team_dir / "roster.json").write_text(json.dumps(roster), encoding="utf-8")


class LoadMergedRosterTests(unittest.TestCase):
    """Unit tests for `_load_merged_roster` — parent+child merge semantics."""

    def test_child_only_no_parent(self):
        """Parent roster missing → returns child roster unchanged."""
        with tempfile.TemporaryDirectory() as td:
            outer = Path(td)
            _git_init(outer)  # parent IS a git repo, but has no roster
            child = outer / "child"
            child.mkdir()
            _git_init(child)
            _write_roster(child, {"Alice": "alice@example.com"})

            merged = hook._load_merged_roster(child)
            self.assertEqual(merged, {"Alice": "alice@example.com"})

    def test_parent_not_a_git_repo(self):
        """Parent dir exists but is NOT a git repo → parent ignored."""
        with tempfile.TemporaryDirectory() as td:
            outer = Path(td)
            # Intentionally do NOT `_git_init(outer)` — parent has no `.git`
            _write_roster(outer, {"ShouldNotAppear": "nope@example.com"})
            child = outer / "child"
            child.mkdir()
            _git_init(child)
            _write_roster(child, {"Alice": "alice@example.com"})

            merged = hook._load_merged_roster(child)
            self.assertEqual(merged, {"Alice": "alice@example.com"})
            self.assertNotIn("ShouldNotAppear", merged)

    def test_parent_is_git_repo_without_roster(self):
        """Parent is a git repo but has no `.claude/team/roster.json` → ignored."""
        with tempfile.TemporaryDirectory() as td:
            outer = Path(td)
            _git_init(outer)
            # no roster written for outer
            child = outer / "child"
            child.mkdir()
            _git_init(child)
            _write_roster(child, {"Alice": "alice@example.com"})

            merged = hook._load_merged_roster(child)
            self.assertEqual(merged, {"Alice": "alice@example.com"})

    def test_child_plus_parent_merge_union(self):
        """Parent + child with disjoint names → union of both."""
        with tempfile.TemporaryDirectory() as td:
            outer = Path(td)
            _git_init(outer)
            _write_roster(outer, {"Nadia": "nadia@example.com"})
            child = outer / "child"
            child.mkdir()
            _git_init(child)
            _write_roster(child, {"Alice": "alice@example.com"})

            merged = hook._load_merged_roster(child)
            self.assertEqual(
                merged,
                {
                    "Nadia": "nadia@example.com",
                    "Alice": "alice@example.com",
                },
            )

    def test_child_wins_on_name_collision(self):
        """Same name in both with different emails → child email wins."""
        with tempfile.TemporaryDirectory() as td:
            outer = Path(td)
            _git_init(outer)
            _write_roster(outer, {"Alice": "alice-parent@example.com"})
            child = outer / "child"
            child.mkdir()
            _git_init(child)
            _write_roster(child, {"Alice": "alice-child@example.com"})

            merged = hook._load_merged_roster(child)
            self.assertEqual(merged, {"Alice": "alice-child@example.com"})

    def test_walk_only_one_level_grandparent_ignored(self):
        """Grandparent has roster, parent does not → grandparent NOT loaded."""
        with tempfile.TemporaryDirectory() as td:
            grand = Path(td)
            _git_init(grand)
            _write_roster(grand, {"Grandparent": "gp@example.com"})
            parent = grand / "parent"
            parent.mkdir()
            # parent is NOT a git repo and has no roster
            child = parent / "child"
            child.mkdir()
            _git_init(child)
            _write_roster(child, {"Alice": "alice@example.com"})

            merged = hook._load_merged_roster(child)
            self.assertEqual(merged, {"Alice": "alice@example.com"})
            self.assertNotIn("Grandparent", merged)

    def test_malformed_parent_roster_does_not_block(self):
        """A broken parent roster.json must fail-open — child roster is returned."""
        with tempfile.TemporaryDirectory() as td:
            outer = Path(td)
            _git_init(outer)
            team_dir = outer / ".claude" / "team"
            team_dir.mkdir(parents=True)
            (team_dir / "roster.json").write_text("{ this is not valid json", encoding="utf-8")
            child = outer / "child"
            child.mkdir()
            _git_init(child)
            _write_roster(child, {"Alice": "alice@example.com"})

            merged = hook._load_merged_roster(child)
            self.assertEqual(merged, {"Alice": "alice@example.com"})


class DetectTargetRosterTests(unittest.TestCase):
    """Regression tests for `cd <path> && git commit` target-roster detection."""

    def test_cd_target_returns_merged_roster(self):
        """`cd <child> && git commit` loads child+parent merged roster."""
        with tempfile.TemporaryDirectory() as td:
            outer = Path(td)
            _git_init(outer)
            _write_roster(outer, {"Nadia": "nadia@example.com"})
            child = outer / "child"
            child.mkdir()
            _git_init(child)
            _write_roster(child, {"Alice": "alice@example.com"})

            command = f"cd {child} && git commit -m 'x'"
            detected = hook._detect_target_roster(command)
            self.assertIsNotNone(detected)
            assert detected is not None  # for type-narrowing
            self.assertEqual(
                detected,
                {
                    "Nadia": "nadia@example.com",
                    "Alice": "alice@example.com",
                },
            )

    def test_cd_target_with_no_roster_returns_none(self):
        """`cd <dir>` where dir has no roster → None (fall back to local)."""
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "nonroster"
            target.mkdir()
            # no .claude/team/roster.json

            command = f"cd {target} && git commit -m 'x'"
            self.assertIsNone(hook._detect_target_roster(command))

    def test_no_cd_returns_none(self):
        """Command without `cd` → None (use local ROSTER)."""
        self.assertIsNone(hook._detect_target_roster("git commit -m 'x'"))


class CheckIntegrationTests(unittest.TestCase):
    """Integration: `check()` accepts a name present only in the parent roster.

    Verifies the end-to-end merge path: an org-level coordinator defined ONLY
    in the parent repo's roster is accepted when committing in a child repo.
    """

    def test_parent_only_name_accepted_in_child_commit(self):
        with tempfile.TemporaryDirectory() as td:
            outer = Path(td)
            _git_init(outer)
            _write_roster(outer, {"Nadia": "nadia@example.com"})
            child = outer / "child"
            child.mkdir()
            _git_init(child)
            _write_roster(child, {"Alice": "alice@example.com"})

            command = (
                f'cd {child} && git -c user.name="Nadia" '
                f'-c user.email="nadia@example.com" commit -m "x"'
            )
            result = hook.check({"tool_name": "Bash", "tool_input": {"command": command}})
            self.assertIsNone(result, f"expected allow, got block: {result}")

    def test_child_email_override_blocks_parent_email(self):
        """When child overrides a name's email, the parent email is rejected."""
        with tempfile.TemporaryDirectory() as td:
            outer = Path(td)
            _git_init(outer)
            _write_roster(outer, {"Alice": "alice-parent@example.com"})
            child = outer / "child"
            child.mkdir()
            _git_init(child)
            _write_roster(child, {"Alice": "alice-child@example.com"})

            command = (
                f'cd {child} && git -c user.name="Alice" '
                f'-c user.email="alice-parent@example.com" commit -m "x"'
            )
            result = hook.check({"tool_name": "Bash", "tool_input": {"command": command}})
            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result.get("decision"), "block")


class MatcherRobustnessTests(unittest.TestCase):
    """Negative-match coverage for the substring-bug cluster (#226, #188, #216)."""

    @staticmethod
    def _input(command: str) -> dict:
        return {"tool_name": "Bash", "tool_input": {"command": command}}

    def test_unquoted_email_value_bounded_by_whitespace(self):
        """#226 repro: bare `-c user.email=val` does NOT slurp to EOL.

        Pre-fix: the regex `-c\\s+user\\.email=["']?([^"']+)["']?` slurped
        from `user.email=` to the next `"` or end-of-line. With a bare value
        and no closing quote, the entire rest of the command was captured
        into the email field. Tokenization via shlex bounds at whitespace.
        """
        # Use a name that exists in the local roster so we can verify the
        # email comparison hits the correct value, not the slurped one.
        valid_name = next(iter(hook.ROSTER), None)
        if not valid_name:
            self.skipTest("local roster is empty")
        valid_email = hook.ROSTER[valid_name]
        cmd = (
            f'git -c user.name="{valid_name}" -c user.email={valid_email} '
            f"commit -F /tmp/commit-msg.txt 2>&1 | tail -20"
        )
        result = hook.check(self._input(cmd))
        self.assertIsNone(
            result,
            "#226: unquoted bare email should be allowed, not slurp to EOL",
        )

    def test_nested_heredoc_in_command_substitution(self):
        """#188 repro: `git commit -m "$(cat <<'EOF' ... EOF)"` mangles the parser.

        Pre-fix: `_strip_heredocs` + `_strip_quoted_strings` interaction on
        nested `$(cat <<'EOF' ... EOF)` inside a double-quoted outer string
        broke the parser's view of `user.name=...`. shlex tokenization
        treats the entire `"$(cat <<'EOF' ... EOF)"` as one token (the outer
        quotes are absorbed; the heredoc body is part of the token's value).
        """
        valid_name = next(iter(hook.ROSTER), None)
        if not valid_name:
            self.skipTest("local roster is empty")
        valid_email = hook.ROSTER[valid_name]
        # The nested form: a heredoc inside a command-substitution inside a
        # double-quoted -m argument.
        cmd = (
            f'git -c user.name="{valid_name}" -c user.email="{valid_email}" '
            "commit -m \"$(cat <<'EOF'\nmulti\nline\nmessage\nEOF\n)\""
        )
        result = hook.check(self._input(cmd))
        self.assertIsNone(
            result,
            "#188: nested heredoc-in-command-sub-in-double-quote should not block",
        )

    def test_heredoc_body_with_git_commit_phrase_does_not_match(self):
        """#216 sibling: heredoc body containing 'git commit' is not a real commit."""
        cmd = (
            "cat > /tmp/x.md <<'EOF'\n"
            "Here is how to git commit with -c flags:\n"
            'git -c user.name="X" commit -m "..."\n'
            "EOF"
        )
        # Not a real commit invocation — should not require identity.
        self.assertIsNone(hook.check(self._input(cmd)))

    def test_alembic_heredoc_body_via_command_substitution(self):
        """user-service#99 claim 1: alembic-shape heredoc body via `-m "$(cat <<EOF...)"`.

        Defensive coverage on top of `test_nested_heredoc_in_command_substitution`
        (#188): the existing test pins the SHAPE; this test pins an alembic-
        specific BODY containing the literal strings the user-service `make
        migrate-new` workflow emits — `heads`, `head`, `revision = '<sha>'`,
        `down_revision`. None of those substrings are hook tokens, but the
        fixture exists so any future tightening of the parser cannot
        accidentally treat alembic-emitted strings as identity-flag keywords.

        Memory ref: `project_w10_user_service_alembic.md` (P2W10 #63 alembic
        heads→head discipline).
        """
        valid_name = next(iter(hook.ROSTER), None)
        if not valid_name:
            self.skipTest("local roster is empty")
        valid_email = hook.ROSTER[valid_name]
        # Alembic-emitted strings inside a heredoc body inside command-sub.
        cmd = (
            f'git -c user.name="{valid_name}" -c user.email="{valid_email}" '
            "commit -m \"$(cat <<'EOF'\n"
            "migrate(P3W8 user-service#63): merge alembic heads -> head\n"
            "\n"
            "revision = 'a1b2c3d4e5f6'\n"
            "down_revision = ('aaaa1111', 'bbbb2222')\n"
            "branch_labels = None\n"
            "depends_on = None\n"
            'EOF\n)"'
        )
        self.assertIsNone(
            hook.check(self._input(cmd)),
            "us#99 claim 1: alembic-shape heredoc body should not false-block",
        )

    def test_label_validator_filename_no_longer_blocks(self):
        """#226 meta-instance: --body-file path inside --label list.

        The label validator (separate hook) can mistake a file path that
        appears between `--body-file` and `--label` for a label value. This
        hook isn't directly affected — covered for adjacency only.
        """
        # validate_commit_identity is on git, not gh. Just confirm gh
        # invocations are not flagged here.
        cmd = 'gh issue create --body-file /tmp/issue-body.txt --label "tech-debt,infrastructure"'
        self.assertIsNone(hook.check(self._input(cmd)))


class ParseFailureFailClosedTests(unittest.TestCase):
    """`tokenize` returns None on shlex parse failure. For commit-identity
    validation this MUST fail-closed: a malformed-but-commit-shaped command
    should block, not silently allow. (Per `_shell_parse.tokenize` caller
    contract pinned with Linh.)
    """

    @staticmethod
    def _input(command: str) -> dict:
        return {"tool_name": "Bash", "tool_input": {"command": command}}

    def test_unbalanced_quote_with_commit_blocks(self):
        """Unterminated quote + git commit shape → block (don't silently allow)."""
        cmd = 'git -c user.name="Aino Virtanen -c user.email="a@b.c" commit -m "x"'
        # Above has an unbalanced quote (the `"Aino Virtanen ` opens and
        # is never closed before the next `"`, so shlex raises).
        result = hook.check(self._input(cmd))
        self.assertIsNotNone(
            result,
            "parse failure on a commit-shaped command must block, not allow",
        )
        assert result is not None
        self.assertEqual(result["decision"], "block")
        # Reason must indicate parse failure and actionable guidance
        # (message updated in #287 to be more precise than "shlex parsing").
        self.assertIn("unbalanced quotes", result["reason"])

    def test_block_message_points_at_F_file_fix(self):
        """Parse-failure block message MUST cite the -F file fix and the
        heredoc-as-cause framing. Codified by #345 after 8 occurrences in
        P3W7-W8 of agents repeating the heredoc pattern despite the memory
        pointer existing — the message itself must surface the fix.
        """
        cmd = 'git -c user.name="Aino Virtanen -c user.email="a@b.c" commit -m "x"'
        result = hook.check(self._input(cmd))
        assert result is not None
        reason = result["reason"]
        # Cause framing: the heredoc-inside--m pattern is named.
        self.assertIn("heredoc", reason.lower())
        self.assertIn('-m "$(cat <<EOF', reason)
        # Fix: -F file pattern is shown.
        self.assertIn("-F /path/to/msg.txt", reason)
        self.assertIn("/tmp/msg-issue-N.txt", reason)
        # Memory pointer: the canonical reference is named so the operator
        # can read full context after applying the fix.
        self.assertIn("feedback_heredoc_in_git_commit.md", reason)

    def test_unbalanced_quote_without_commit_allows(self):
        """Parse failure on a non-commit command → allow (no commit to validate)."""
        cmd = 'echo "unterminated'
        # Not a git commit; allow.
        self.assertIsNone(hook.check(self._input(cmd)))

    def test_repeated_dash_c_user_name_uses_last_value(self):
        """Repeated -c user.name → last value wins (matches git semantics).

        `dict(extract_dash_c_pairs(...))` overwrites earlier entries with
        later ones, mirroring how git itself resolves repeated -c flags.
        """
        valid_name = next(iter(hook.ROSTER), None)
        if not valid_name:
            self.skipTest("local roster is empty")
        valid_email = hook.ROSTER[valid_name]
        # First name is bogus, last is valid → must allow (last wins).
        cmd = (
            f'git -c user.name="NotInRoster" -c user.name="{valid_name}" '
            f'-c user.email="{valid_email}" commit -m "x"'
        )
        self.assertIsNone(
            hook.check(self._input(cmd)),
            "last-wins semantics: bogus earlier value should be overridden",
        )


if __name__ == "__main__":
    unittest.main()
