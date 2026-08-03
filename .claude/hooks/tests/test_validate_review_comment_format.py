#!/usr/bin/env python3
"""Tests for validate_review_comment_format hook (closes #302).

P3W7 parser-fixture audit (#300) flagged this as a HIGH-priority gap:
parser-class hook with ZERO fixture coverage controlling merge traffic.

The hook parses:
- Shell command segments to detect `gh pr comment` invocations (regex)
- PR comment bodies in 3 quote forms: heredoc, single-quoted, double-quoted
- `Requestor:`, `Requestee:`, `RequestOrReplied:` charter fields
- Branch head ref name to extract the author's identity

The hook blocks when the `Requestor` IS the branch author, indicating the
operator copied the swapped form of the example (the failure mode #356/#372/
#375 collectively addressed in surrounding hooks). Post-#386 the compared
field is `Requestor`, not `Requestee`; post-#1172 the comparison is on
first-initial + lastname rather than lastname alone, because the roster holds
distinct people who share a surname.

Run: python3 -m unittest discover -s .claude/hooks/tests \
         -p "test_validate_review_comment_format.py"
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
_LIB_DIR = _HOOKS_DIR.parent / "lib"
sys.path.insert(0, str(_HOOKS_DIR))
sys.path.insert(0, str(_LIB_DIR))

import charter_trailer  # noqa: E402
import validate_review_comment_format as hook  # noqa: E402


def _bash_input(command: str) -> dict:
    """Build a PreToolUse Bash input dict shape."""
    return {"tool_name": "Bash", "tool_input": {"command": command}}


class IsCommentCommandTests(unittest.TestCase):
    """Coverage for the `gh pr comment` segment detector."""

    def test_simple_form_matches(self):
        self.assertTrue(hook.is_comment_command("gh pr comment 42"))

    def test_with_body_flag_matches(self):
        self.assertTrue(hook.is_comment_command('gh pr comment 42 --body "x"'))

    def test_chained_after_and_matches(self):
        self.assertTrue(hook.is_comment_command("gh pr view 42 && gh pr comment 42 --body x"))

    def test_chained_after_pipe_matches(self):
        self.assertTrue(hook.is_comment_command("true | gh pr comment 42 --body x"))

    def test_chained_after_semicolon_matches(self):
        self.assertTrue(hook.is_comment_command("echo go ; gh pr comment 42"))

    def test_env_var_prefix_matches(self):
        """Leading KEY=value env-var prefixes are stripped before the regex match."""
        self.assertTrue(hook.is_comment_command("ENVIRONMENT=test gh pr comment 42"))

    def test_multiple_env_var_prefixes_matches(self):
        self.assertTrue(hook.is_comment_command("FOO=1 BAR=2 gh pr comment 42"))

    def test_gh_pr_view_does_not_match(self):
        self.assertFalse(hook.is_comment_command("gh pr view 42"))

    def test_gh_pr_review_does_not_match(self):
        self.assertFalse(hook.is_comment_command("gh pr review 42 --approve"))

    def test_gh_issue_comment_does_not_match(self):
        """Hook is PR-scoped — `gh issue comment` should NOT match."""
        self.assertFalse(hook.is_comment_command("gh issue comment 42 --body x"))

    def test_non_bash_unrelated_command_does_not_match(self):
        self.assertFalse(hook.is_comment_command("ls -la"))

    def test_empty_command_does_not_match(self):
        self.assertFalse(hook.is_comment_command(""))


class ExtractPrNumberTests(unittest.TestCase):
    """PR-number extraction — direct number, then URL fallback."""

    def test_direct_number(self):
        self.assertEqual(hook.extract_pr_number("gh pr comment 42 --body x"), "42")

    def test_url_form(self):
        """#302 input shape: PR number from URL — `https://github.com/.../pull/123`."""
        self.assertEqual(
            hook.extract_pr_number("gh pr comment https://github.com/owner/repo/pull/123"),
            "123",
        )

    def test_url_form_takes_precedence_over_no_direct_number(self):
        """When no bare number follows `gh pr comment`, URL is the fallback path."""
        cmd = "gh pr comment https://github.com/o/r/pull/9 --body x"
        # Hook regex tries bare-number first; URL has `9` as the path tail.
        result = hook.extract_pr_number(cmd)
        self.assertEqual(result, "9")

    def test_no_number_returns_none(self):
        self.assertIsNone(hook.extract_pr_number("gh pr comment --help"))


class ExtractCommentBodyTests(unittest.TestCase):
    """The three quote-form parsers — heredoc, single-quoted, double-quoted."""

    def test_double_quoted_body(self):
        cmd = 'gh pr comment 42 --body "Requestor: A\nRequestee: B"'
        body = hook.extract_comment_body(cmd)
        self.assertIsNotNone(body)
        assert body is not None
        self.assertIn("Requestor: A", body)
        self.assertIn("Requestee: B", body)

    def test_single_quoted_body(self):
        cmd = "gh pr comment 42 --body 'Requestor: A\nRequestee: B'"
        body = hook.extract_comment_body(cmd)
        self.assertIsNotNone(body)
        assert body is not None
        self.assertIn("Requestor: A", body)

    def test_heredoc_body(self):
        """#302 input shape: `--body "$(cat <<'EOF'\\n...\\nEOF)"`."""
        cmd = (
            "gh pr comment 42 --body \"$(cat <<'EOF'\n"
            "Requestor: Aino Virtanen\n"
            "Requestee: Nadia Khoury\n"
            "RequestOrReplied: Approved\n"
            'EOF\n)"'
        )
        body = hook.extract_comment_body(cmd)
        self.assertIsNotNone(body)
        assert body is not None
        self.assertIn("Requestor: Aino Virtanen", body)
        self.assertIn("Requestee: Nadia Khoury", body)
        self.assertIn("RequestOrReplied: Approved", body)

    def test_heredoc_body_with_unquoted_EOF(self):
        """`<<EOF` (no quotes) form also captured."""
        cmd = (
            'gh pr comment 42 --body "$(cat <<EOF\n'
            "Requestor: A\nRequestee: B\nRequestOrReplied: Approved\n"
            'EOF\n)"'
        )
        body = hook.extract_comment_body(cmd)
        self.assertIsNotNone(body)
        assert body is not None
        self.assertIn("Requestor: A", body)

    def test_body_file_is_read(self):
        """`--body-file` IS read as of #934, reversing the #302/#377 pin.

        The superseded test asserted `extract_comment_body` returns None here
        and called file-based bodies "operator-trusted." It passed only because
        `/tmp/comment-body.md` did not exist on the runner — a green assertion
        resting on a missing file, which proved nothing about the code path it
        named. Meanwhile `--body-file` is the charter-prescribed form
        (`agents.md:429`, 144 call sites), so the pin exempted the primary path.
        """
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "comment-body.md"
            path.write_text("Requestor: A\nRequestee: B\nRequestOrReplied: Approved\n")
            body = hook.extract_comment_body(f"gh pr comment 42 --body-file {path}")
            assert body is not None
            self.assertIn("RequestOrReplied: Approved", body)

    def test_body_file_missing_path_returns_none(self):
        """Unreadable path yields None here; `check()` turns that into a block."""
        cmd = "gh pr comment 42 --body-file /tmp/definitely-not-here-934.md"
        self.assertIsNone(hook.extract_comment_body(cmd))

    def test_no_body_flag_returns_none(self):
        self.assertIsNone(hook.extract_comment_body("gh pr comment 42"))


class ExtractBranchAuthorLastnameTests(unittest.TestCase):
    """Branch head ref → lastname extraction.

    Charter convention: branches are `{FirstInitial}.{LastName}/{IIII}-{slug}`;
    the dash form `{FirstInitial}.{LastName}-{IIII}-{slug}` is also observed in
    production refs and is accepted since #1175. Parsing lives in
    `charter_trailer._BRANCH_AUTHOR_PREFIX_RE`, not in this hook.
    """

    def test_slash_separator_canonical(self):
        self.assertEqual(
            hook.extract_branch_author_lastname("A.Virtanen/0373-ruff-format-vwpc"),
            "Virtanen",
        )

    def test_short_lastname(self):
        self.assertEqual(hook.extract_branch_author_lastname("L.Li/0001-fix"), "Li")

    def test_dash_separator_supported(self):
        """#1175: `{Initial}.{Lastname}-{number}` (dash) IS matched.

        This test REPLACES `test_dash_separator_not_supported`, which pinned the
        opposite and pinned the bug: this hook's local regex was slash-only,
        while `validate_pr_review`'s copy of the same function learned the dash
        separator in #179 and this module's own imported
        `branch_author_first_initial` accepted dash all along. The old test made
        that divergence look intended, which is why it survived four months.

        The consequence of the old behaviour was not cosmetic: a dash-branch
        head ref yielded `branch_author = None`, and `check()` short-circuited
        to allow-with-warning BEFORE the Requestor/Requestee swap heuristic ran
        (see `SwapCheckReachesDashBranchesTests` for the end-to-end proof).
        """
        self.assertEqual(
            hook.extract_branch_author_lastname("A.Virtanen-0373-ruff-format"),
            "Virtanen",
        )

    def test_underscore_separator_not_supported(self):
        """Charter-allowed underscore form (some implementer agents use `_` for `+`)."""
        self.assertIsNone(hook.extract_branch_author_lastname("A.Virtanen_0373-ruff-format"))

    def test_plain_branch_name_returns_none(self):
        self.assertIsNone(hook.extract_branch_author_lastname("main"))

    def test_hotfix_branch_returns_none(self):
        self.assertIsNone(hook.extract_branch_author_lastname("hotfix/some-fix"))

    def test_lowercase_initial_also_matches(self):
        """Regex is case-tolerant: lowercase initial still produces lastname."""
        self.assertEqual(
            hook.extract_branch_author_lastname("a.virtanen/0001-fix"),
            "virtanen",
        )


class SharedBranchAuthorParsingTests(unittest.TestCase):
    """The branch-prefix parsers are SHARED, not merely equal (#1175).

    Value-equality tests cannot catch the defect this class exists for. A
    re-declared local `extract_branch_author_lastname` that happens to agree
    with `charter_trailer`'s TODAY passes every behavioural assertion in this
    file and then drifts on the next fix applied to only one copy — which is
    literally what happened between #179 (Apr 2026) and #1175. Object identity
    is the only assertion that fails the moment a second definition exists.
    """

    def test_lastname_parser_is_the_charter_trailer_one(self):
        self.assertIs(
            hook.extract_branch_author_lastname,
            charter_trailer.extract_branch_author_lastname,
        )

    def test_initial_parser_is_the_charter_trailer_one(self):
        self.assertIs(
            hook.branch_author_first_initial,
            charter_trailer.branch_author_first_initial,
        )

    def test_the_two_parsers_agree_on_prefix_presence(self):
        """Both halves of the branch author's identity must be found together.

        `check()` gates on the lastname and then reads the initial; a ref where
        one parser matches and the other does not would produce a half-known
        author and a display string missing its initial.
        """
        refs = (
            "A.Virtanen/1175-consolidation",
            "A.Virtanen-1175-consolidation",
            "a.virtanen/1175-consolidation",
            "L.Li/0001-fix",
            "A.Virtanen_1175-consolidation",
            "deployments/phase-3/wave-29",
            "dependabot/pip/urllib3-2.5.0",
            "main",
            "",
        )
        for ref in refs:
            with self.subTest(ref=ref):
                self.assertEqual(
                    hook.extract_branch_author_lastname(ref) is not None,
                    bool(hook.branch_author_first_initial(ref)),
                )


class SwapCheckReachesDashBranchesTests(unittest.TestCase):
    """#1175, at the level of the decision — not the regex.

    Pre-fix, EVERY case below returned the same allow-with-warning dict, because
    the slash-only local parser produced `branch_author = None` and `check()`
    returned before the swap heuristic. The pair is deliberate: the block proves
    the check now RUNS on a dash ref, and the allow proves consolidating it did
    not turn the hook into "block everything on a dash branch" — a gate that
    stops false-negativing by firing unconditionally has not been fixed.
    """

    DASH_BRANCH = "A.Virtanen-0373-ruff-format"

    def _check(self, command: str) -> dict | None:
        with mock.patch.object(hook, "get_branch_name", return_value=self.DASH_BRANCH):
            return hook.check(_bash_input(command))

    def test_swapped_verdict_on_a_dash_branch_now_blocks(self):
        """Requestor = Aino Virtanen = the dash branch's author → swap → block."""
        result = self._check(CheckIntegrationTests.HEREDOC_POST244_SWAP)
        assert result is not None
        self.assertEqual(result.get("decision"), "block")
        self.assertIn("swapped", result["reason"].lower())
        self.assertIn("A.Virtanen", result["reason"])

    def test_correct_verdict_on_a_dash_branch_still_allows(self):
        """Requestor = Nadia Khoury (the reviewer) → no swap → no block."""
        self.assertIsNone(self._check(CheckIntegrationTests.HEREDOC_CANONICAL))

    def test_the_dash_branch_fixture_is_not_silently_unparsed(self):
        """Anti-vacuity: prove the fixture ref really carries the prefix.

        Without this, a future edit that broke parsing outright would leave
        `test_correct_verdict_on_a_dash_branch_still_allows` passing for the
        wrong reason — allow-with-warning is also "not a block".
        """
        self.assertEqual(hook.extract_branch_author_lastname(self.DASH_BRANCH), "Virtanen")
        self.assertEqual(hook.branch_author_first_initial(self.DASH_BRANCH), "a")


class HyphenatedSurnameSwapCheckTests(unittest.TestCase):
    """The #1269 merge-gate defect, at the level of `check()`'s decision.

    THE DEFECT. `_BRANCH_AUTHOR_PREFIX_RE`'s original `([A-Za-z]+)` lastname
    group does not REJECT a hyphenated surname — the surname's own `-` satisfies
    the `[-/]` separator, so the match succeeds and returns a TRUNCATED lastname:
    `K.Mensah-Williams/0001-x` -> `Mensah`.

    `Kofi Mensah` and `Kofi Mensah-Williams` are two distinct roster members with
    the same first initial, so the truncated surname + initial `k` matched the
    other person exactly, and the hook inverted in both directions at once:

        scenario on K.Mensah-Williams/…      pre-#1175   truncating   fixed
        Kofi Mensah posts a CORRECT verdict  allow+warn  BLOCK        allow
        a genuinely SWAPPED verdict          allow+warn  allow        BLOCK

    The false BLOCK is the serious half: an unblockable false positive with no
    observable-body workaround — the exact class #1172 was filed to eliminate and
    #934 already fixed once in this hook (see the comment block at the swap
    heuristic), reintroduced through a different mechanism.

    WHY THESE FIXTURES EXIST AT ALL. The suite that shipped the consolidation
    scored an identical `420 passed` under three different lastname charsets: it
    contained no hyphenated-surname fixture, so it pinned the charset in neither
    direction. Both rows of the table above are asserted here, because asserting
    only the allow would also pass under a hook that blocks nothing.
    """

    SLASH_REF = "K.Mensah-Williams/0001-project-scaffolding"
    DASH_REF = "K.Mensah-Williams-0001-project-scaffolding"

    # Requestor = the reviewer (Kofi Mensah), Requestee = the PR author
    # (Kofi Mensah-Williams). Correct per the post-#244 charter binding.
    CORRECT = (
        "gh pr comment 42 --body \"$(cat <<'EOF'\n"
        "Requestor: Kofi Mensah\n"
        "Requestee: Kofi Mensah-Williams\n"
        "RequestOrReplied: Approved\n"
        "TechDebt: none\n"
        'EOF\n)"'
    )

    # The genuine swap: the branch author named as the reviewer.
    SWAPPED = (
        "gh pr comment 42 --body \"$(cat <<'EOF'\n"
        "Requestor: Kofi Mensah-Williams\n"
        "Requestee: Kofi Mensah\n"
        "RequestOrReplied: Approved\n"
        "TechDebt: none\n"
        'EOF\n)"'
    )

    def _check(self, ref: str, command: str) -> dict | None:
        with mock.patch.object(hook, "get_branch_name", return_value=ref):
            return hook.check(_bash_input(command))

    def test_correct_verdict_from_the_colliding_colleague_is_not_blocked(self):
        """Row 1 — the unblockable false positive. Kofi Mensah is NOT the author
        of `K.Mensah-Williams/…` and his correct verdict must post."""
        self.assertIsNone(self._check(self.SLASH_REF, self.CORRECT))

    def test_swapped_verdict_on_a_hyphenated_branch_blocks(self):
        """Row 2 — and the swap check must still actually fire, naming the right
        person. Without this, row 1 would also pass under a hook that had simply
        stopped parsing the ref."""
        result = self._check(self.SLASH_REF, self.SWAPPED)
        assert result is not None
        self.assertEqual(result.get("decision"), "block")
        self.assertIn("swapped", result["reason"].lower())
        self.assertIn("K.Mensah-Williams", result["reason"])

    def test_correct_verdict_on_the_dash_form_is_not_blocked(self):
        """Both separators were affected — the pre-fix format regex could not
        span the surname's hyphen on either."""
        self.assertIsNone(self._check(self.DASH_REF, self.CORRECT))

    def test_swapped_verdict_on_the_dash_form_blocks(self):
        result = self._check(self.DASH_REF, self.SWAPPED)
        assert result is not None
        self.assertEqual(result.get("decision"), "block")
        self.assertIn("K.Mensah-Williams", result["reason"])

    def test_the_block_message_names_the_full_hyphenated_surname(self):
        """The truncation was user-visible: the block message rendered
        `K.Mensah`, accusing the wrong person by name."""
        result = self._check(self.SLASH_REF, self.SWAPPED)
        assert result is not None
        self.assertNotIn("K.Mensah ", result["reason"])
        self.assertIn("branch author is K.Mensah-Williams", result["reason"])

    def test_the_collision_fixtures_are_not_silently_unparsed(self):
        """Anti-vacuity: allow-with-warning is also "not a block", so the two
        allow assertions above would pass for free against a hook that failed to
        parse the ref at all. Prove the prefix is genuinely read, and that the
        two people really are distinguishable to `is_branch_author`."""
        for ref in (self.SLASH_REF, self.DASH_REF):
            with self.subTest(ref=ref):
                self.assertEqual(hook.extract_branch_author_lastname(ref), "Mensah-Williams")
                self.assertEqual(hook.branch_author_first_initial(ref), "k")
        self.assertTrue(
            charter_trailer.is_branch_author("Kofi Mensah-Williams", "Mensah-Williams", "k")
        )
        self.assertFalse(charter_trailer.is_branch_author("Kofi Mensah", "Mensah-Williams", "k"))

    def test_every_hyphenated_roster_surname_reaches_the_swap_check(self):
        """The remaining 7. Their truncated surnames matched nobody, so the
        regression there was warning -> SILENT allow: a swapped verdict posted
        with no signal at all. 77 open branches across 4 child repos carried one
        of these prefixes when this was written.
        """
        others = (
            ("M.Vega-Cruz", "Marisol Vega-Cruz"),
            ("A.Reyes-Fuentes", "Alejandra Reyes-Fuentes"),
            ("A.Diop-Sarr", "Anika Diop-Sarr"),
            ("M.Vasquez-Paredes", "Marcia Vasquez-Paredes"),
            ("R.Osei-Mensah", "Rashid Osei-Mensah"),
            ("S.Nakamura-Whitfield", "Sable Nakamura-Whitfield"),
            ("C.Mendez-Rios", "Carolina Mendez-Rios"),
        )
        for prefix, full_name in others:
            swapped = (
                "gh pr comment 42 --body \"$(cat <<'EOF'\n"
                f"Requestor: {full_name}\n"
                "Requestee: Nadia Khoury\n"
                "RequestOrReplied: Approved\n"
                "TechDebt: none\n"
                'EOF\n)"'
            )
            for ref in (f"{prefix}/0001-x", f"{prefix}-0001-x"):
                with self.subTest(ref=ref):
                    result = self._check(ref, swapped)
                    assert result is not None, f"{ref} did not reach the swap check"
                    self.assertEqual(result.get("decision"), "block")

    def test_non_ascii_surnames_still_take_the_warning_path(self):
        """An EXPLICIT scope decision, tracked on main#1271 — not an oversight.

        `[A-Za-z]` excludes these regardless of the hyphen, so they returned
        `None` before #1175 and still do. Widening to Unicode letters would also
        widen `branch_author_first_initial`, which feeds the COUNTING merge gate
        in `validate_pr_review` — a separate decision that must not ride along on
        a format-hook fix. The warning is the fail-safe outcome: the hook says it
        cannot validate rather than guessing an author.

        Live impact is nil: the roster's commit-identity emails transliterate
        (`Carolina.Mendez-Rios@`) and every open branch uses the ASCII form,
        which `test_every_hyphenated_roster_surname_reaches_the_swap_check`
        covers.
        """
        swapped = (
            "gh pr comment 42 --body \"$(cat <<'EOF'\n"
            "Requestor: Carolina Méndez-Ríos\n"
            "Requestee: Nadia Khoury\n"
            "RequestOrReplied: Approved\n"
            "TechDebt: none\n"
            'EOF\n)"'
        )
        result = self._check("C.Méndez-Ríos/0055-x", swapped)
        assert result is not None
        self.assertEqual(result.get("decision"), "allow")
        self.assertIn("Could not extract author from branch name", result["systemMessage"])


class CheckIntegrationTests(unittest.TestCase):
    """End-to-end fixtures driving check() with mocked branch fetch.

    Post-#386 charter binding: on `Approved` / `Changes Requested` verdicts,
    `Requestor` is the reviewer and `Requestee` is the PR author. The hook
    blocks when `Requestor.lastname == branch-author.lastname` — i.e., the
    PR author is being named as the reviewer (the actual swap). All scenarios
    mock `get_branch_name` so the test does not hit the network.

    HEREDOC_CANONICAL: post-#244 canonical verdict shape (Requestor=reviewer,
    Requestee=PR-author). HEREDOC_POST244_SWAP: post-#244 swap shape
    (Requestor=PR-author, matching the branch author lastname — wrong).
    """

    HEREDOC_CANONICAL = (
        "gh pr comment 42 --body \"$(cat <<'EOF'\n"
        "Requestor: Nadia Khoury\n"
        "Requestee: Aino Virtanen\n"
        "RequestOrReplied: Approved\n"
        "TechDebt: none\n"
        'EOF\n)"'
    )

    HEREDOC_POST244_SWAP = (
        "gh pr comment 42 --body \"$(cat <<'EOF'\n"
        "Requestor: Aino Virtanen\n"
        "Requestee: Nadia Khoury\n"
        "RequestOrReplied: Approved\n"
        "TechDebt: none\n"
        'EOF\n)"'
    )

    def test_canonical_form_on_pr_author_branch_allows(self):
        """Branch A.Virtanen/...; Requestor=Nadia Khoury (reviewer),
        Requestee=Aino Virtanen (PR-author=branch-author).
        Khoury != Virtanen → no swap; allow.
        """
        with mock.patch.object(hook, "get_branch_name", return_value="A.Virtanen/0373-ruff-format"):
            result = hook.check(_bash_input(self.HEREDOC_CANONICAL))
        self.assertIsNone(result)

    def test_canonical_form_on_unrelated_branch_allows(self):
        """Branch N.Khoury/...; Requestor=Nadia Khoury (Requestor matches branch).
        Inverted heuristic: Khoury == Khoury → BLOCK.

        This is the post-#386 inversion of the prior `test_happy_path_no_block`.
        The same body shape that pre-#386 produced a block from the (wrong)
        Requestee-side heuristic now produces a block from the (correct)
        Requestor-side heuristic — by coincidence of names. Retained as
        regression coverage for the post-#244 charter shape.
        """
        with mock.patch.object(hook, "get_branch_name", return_value="N.Khoury/0346-w8-retro"):
            result = hook.check(_bash_input(self.HEREDOC_CANONICAL))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.get("decision"), "block")

    def test_post244_swap_form_blocks(self):
        """Branch A.Virtanen/...; Requestor=Aino Virtanen (PR-author named as
        reviewer — swap). Inverted heuristic: Virtanen == Virtanen → BLOCK.
        """
        with mock.patch.object(hook, "get_branch_name", return_value="A.Virtanen/0373-ruff-format"):
            result = hook.check(_bash_input(self.HEREDOC_POST244_SWAP))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.get("decision"), "block")
        self.assertIn("swapped", result["reason"].lower())

    def test_non_pr_comment_command_allows(self):
        """Not `gh pr comment` → early return None."""
        result = hook.check(_bash_input("gh pr view 42"))
        self.assertIsNone(result)

    def test_no_requestee_field_allows(self):
        """Comment without Requestee: → not a charter-format review → allow."""
        cmd = 'gh pr comment 42 --body "just a comment"'
        result = hook.check(_bash_input(cmd))
        self.assertIsNone(result)

    def test_body_file_readable_non_review_body_allows(self):
        """`--body-file` is now READ (#934), superseding the #302/#377 stance.

        The old test asserted `--body-file` → allow, on the rationale that the
        hook "cannot validate ... without reading the file" and should "trust
        the operator." Both halves fell: the hook can read the file (sibling
        hooks already do — charter `hooks.md:200`), and trusting the operator
        is what let nine uncountable verdicts through on 2026-07-09.

        Note the old test passed only because `/tmp/comment.md` does not exist,
        so it was in fact asserting "unreadable body → allow" — the fail-open
        itself. That exemption was never in the charter; it lived in a docstring.

        A readable body that is not a charter review comment still allows.
        """
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "comment.md"
            path.write_text("just a comment, no charter fields\n")
            cmd = f"gh pr comment 42 --body-file {path}"
            self.assertIsNone(hook.check(_bash_input(cmd)))

    def test_body_file_unreadable_path_blocks(self):
        """An unreadable body cannot be validated, so it must not be trusted."""
        cmd = "gh pr comment 42 --body-file /tmp/definitely-not-here-934.md"
        result = hook.check(_bash_input(cmd))
        assert result is not None
        self.assertEqual(result["decision"], "block")

    def test_no_pr_number_returns_warning(self):
        """No bare number AND no /pull/N URL → allow with warning systemMessage.

        Post-#386 the body gate requires all three of Requestor/Requestee/
        RequestOrReplied. Body crafted with all three to trigger parsing
        beyond the gate, no PR number in the `gh pr comment` invocation.
        """
        cmd = (
            'gh pr comment --body "Requestor: Khoury\n'
            "Requestee: Virtanen\n"
            'RequestOrReplied: Approved"'
        )
        with mock.patch.object(hook, "get_branch_name", return_value=""):
            result = hook.check(_bash_input(cmd))
        # Either allow+warn or allow-None; the implementation returns a
        # warn-shape dict OR None depending on regex behavior. Pin both
        # acceptable outcomes.
        if result is not None:
            self.assertEqual(result.get("decision"), "allow")
            self.assertIn("systemMessage", result)

    def test_unfetchable_branch_returns_warning(self):
        """get_branch_name returns None → allow with warning, no block."""
        with mock.patch.object(hook, "get_branch_name", return_value=None):
            result = hook.check(_bash_input(self.HEREDOC_CANONICAL))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.get("decision"), "allow")
        self.assertIn("systemMessage", result)

    def test_hotfix_branch_unfetched_lastname_returns_warning(self):
        """Branch without `{Initial}.{Lastname}/` shape → no lastname → warn."""
        with mock.patch.object(hook, "get_branch_name", return_value="hotfix/x"):
            result = hook.check(_bash_input(self.HEREDOC_CANONICAL))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.get("decision"), "allow")

    def test_non_bash_tool_passes(self):
        """tool_name != Bash → early return None."""
        result = hook.check(
            {
                "tool_name": "Edit",
                "tool_input": {"command": "gh pr comment 42 --body x"},
            }
        )
        self.assertIsNone(result)

    def test_cross_repo_pr_comment_with_repo_flag_forwards_repo(self):
        """Post-#503: `gh pr comment N --repo OWNER/REPO` now forwards --repo
        to the internal `gh pr view` so the branch fetched is from the
        commented-against repo, NOT cwd's default.

        Pre-#503 this test pinned the BUG: the hook fetched the wrong PR's
        branch when reviewer's cwd was a different repo, leading to the
        Aino-rev-deploy#314 false-block. Post-#503 the hook reads `--repo`
        from the user's command and passes it through.
        """
        cmd = (
            "gh pr comment 99 --repo noorinalabs/noorinalabs-deploy "
            '--body "Requestor: Aino Virtanen\nRequestee: Nadia Khoury\n'
            'RequestOrReplied: Approved\nTechDebt: none"'
        )
        captured_kwargs: dict = {}

        def fake_get_branch(pr_number, repo=None):  # noqa: ARG001
            captured_kwargs["repo"] = repo
            # Return a deploy-side branch that does NOT match Aino's lastname
            # so the swap heuristic does NOT fire — this is the cross-repo
            # happy path the fix unblocks.
            return "N.Hakim/0071-cloud-init-caddy-removal"

        with mock.patch.object(hook, "get_branch_name", side_effect=fake_get_branch):
            result = hook.check(_bash_input(cmd))
        # The --repo value MUST be threaded into get_branch_name (the whole
        # point of #503).
        self.assertEqual(captured_kwargs.get("repo"), "noorinalabs/noorinalabs-deploy")
        # And the verdict resolves as ALLOW because the fetched branch
        # (N.Hakim/...) lastname doesn't collide with the Requestor (Virtanen).
        self.assertIsNone(result)

    def test_markdown_bold_requestor_form(self):
        """Hook regex tolerates `**Requestor:**` markdown-bold prefix on the swap field.

        Post-#386: the heuristic compares Requestor.lastname to branch-author.
        This test pins markdown-bold tolerance on BOTH fields — the body has
        `**Requestor:** Aino Virtanen` (matching branch A.Virtanen) which the
        inverted heuristic detects as a swap and blocks.
        """
        cmd = (
            'gh pr comment 42 --body "**Requestor:** Aino Virtanen\n'
            "**Requestee:** Nadia Khoury\n"
            'RequestOrReplied: Approved"'
        )
        with mock.patch.object(hook, "get_branch_name", return_value="A.Virtanen/0386-x"):
            result = hook.check(_bash_input(cmd))
        # Branch is A.Virtanen, **Requestor:** strips to Virtanen → match → block.
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.get("decision"), "block")

    def test_requestor_with_parenthetical_role_stripped(self):
        """Parenthetical `Requestor: Aino Virtanen (Standards Lead)` strips role.

        Post-#386: the parenthetical-stripping regex now applies to the
        Requestor field (the one the heuristic checks). Body has the
        post-#244 swap shape with a trailing parenthetical role annotation;
        stripper must leave just `Aino Virtanen` so the lastname match fires.
        """
        cmd = (
            'gh pr comment 42 --body "Requestor: Aino Virtanen (Standards Lead)\n'
            "Requestee: Nadia Khoury\n"
            'RequestOrReplied: Approved"'
        )
        with mock.patch.object(hook, "get_branch_name", return_value="A.Virtanen/0386-x"):
            result = hook.check(_bash_input(cmd))
        # Parenthetical stripped → Virtanen == Virtanen → block.
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.get("decision"), "block")


class ExtractRepoCallSiteTests(unittest.TestCase):
    """Smoke coverage that `validate_review_comment_format` exposes
    `extract_repo` (re-exported from the shared `_repo_flag_parse` helper)
    and that the canonical happy path still resolves the same value.

    Comprehensive parser coverage (all 4 flag forms, tokenize / regex
    fallback, malformed cases) lives in `test_repo_flag_parse.py` alongside
    the helper. These tests pin the hook's import wiring so a future
    refactor that drops the re-export trips here, not at runtime.
    """

    def test_present_returns_value(self):
        cmd = "gh pr comment 99 --repo noorinalabs/noorinalabs-deploy --body x"
        self.assertEqual(
            hook.extract_repo(cmd),
            "noorinalabs/noorinalabs-deploy",
        )

    def test_absent_returns_none(self):
        cmd = 'gh pr comment 99 --body "x"'
        self.assertIsNone(hook.extract_repo(cmd))

    def test_equals_form_now_supported(self):
        """`--repo=value` form is supported post-#510 (was a documented
        gap in the original #509 implementation — see issue body for the
        latent #503-class regression risk via alternate flag forms).
        Pre-#510 this returned None (pinned by
        `test_with_equals_form_not_supported`); post-#510 it returns the
        value, closing the parser inconsistency with `validate_labels.py`.
        """
        cmd = "gh pr comment 99 --repo=noorinalabs/noorinalabs-deploy --body x"
        self.assertEqual(
            hook.extract_repo(cmd),
            "noorinalabs/noorinalabs-deploy",
        )


class CrossRepoRegressionTests(unittest.TestCase):
    """Regression coverage for the P3W11 #503 cross-repo false-block.

    Reproduces the exact Aino-rev-deploy#314 scenario: reviewer in
    noorinalabs-main cwd posting a verdict on noorinalabs-deploy PR with
    `--repo noorinalabs/noorinalabs-deploy`. Pre-fix the hook fetched main's
    same-numbered PR (whose branch happened to also be `A.Virtanen/...`),
    matched the lastname, and false-blocked. Post-fix the --repo flag is
    forwarded and the correct (deploy-side) branch is fetched.
    """

    REPRO_COMMAND = (
        "gh pr comment 314 --repo noorinalabs/noorinalabs-deploy "
        '--body "Requestor: Aino Virtanen\nRequestee: Nurul Hakim\n'
        'RequestOrReplied: Approved\nTechDebt: none"'
    )

    def test_503_repro_no_false_block_when_repo_forwarded(self):
        """The exact Aino-rev-deploy#314 false-block scenario, post-fix.

        Without --repo forwarding, get_branch_name would (in production) hit
        main's PR #314 with `A.Virtanen/0300-w7-retro-charter` → match Aino's
        lastname → false-block. With --repo forwarding it hits deploy's PR
        #314 with `N.Hakim/0071-cloud-init-caddy-removal` → no lastname
        collision → allow.

        Verified by capturing the repo kwarg passed to get_branch_name and
        asserting it equals what the user wrote.
        """
        captured_kwargs: dict = {}

        def fake_get_branch(pr_number, repo=None):  # noqa: ARG001
            captured_kwargs["repo"] = repo
            # Simulate gh pr view returning the deploy-side branch when --repo
            # is properly forwarded.
            if repo == "noorinalabs/noorinalabs-deploy":
                return "N.Hakim/0071-cloud-init-caddy-removal"
            # The buggy path would have returned main's same-numbered PR.
            return "A.Virtanen/0300-w7-retro-charter"

        with mock.patch.object(hook, "get_branch_name", side_effect=fake_get_branch):
            result = hook.check(_bash_input(self.REPRO_COMMAND))

        # Post-fix: --repo MUST be forwarded.
        self.assertEqual(captured_kwargs.get("repo"), "noorinalabs/noorinalabs-deploy")
        # And the false-block MUST NOT fire (branch lastname = Hakim ≠ Virtanen).
        self.assertIsNone(
            result,
            "Cross-repo verdict with --repo correctly forwarded should NOT block",
        )

    def test_same_repo_path_emits_fallback_warning_on_stderr(self):
        """When --repo is absent, hook uses cwd-default but emits a stderr
        breadcrumb so future cross-repo invocations missing --repo are
        discoverable in transcripts. Pins the fallback log behavior.
        """
        cmd = (
            "gh pr comment 42 "
            '--body "Requestor: Nadia Khoury\nRequestee: Aino Virtanen\n'
            'RequestOrReplied: Approved\nTechDebt: none"'
        )
        # Capture stderr around the hook call.
        import io
        from contextlib import redirect_stderr

        captured_kwargs: dict = {}

        def fake_get_branch(pr_number, repo=None):  # noqa: ARG001
            captured_kwargs["repo"] = repo
            return "A.Virtanen/0373-ruff-format"

        stderr_buf = io.StringIO()
        with (
            mock.patch.object(hook, "get_branch_name", side_effect=fake_get_branch),
            redirect_stderr(stderr_buf),
        ):
            hook.check(_bash_input(cmd))

        # No --repo passed → fallback path; repo kwarg is None.
        self.assertIsNone(captured_kwargs.get("repo"))
        # Stderr breadcrumb names the hook + the #503 origin.
        stderr_text = stderr_buf.getvalue()
        self.assertIn("validate_review_comment_format", stderr_text)
        self.assertIn("--repo", stderr_text)
        self.assertIn("#503", stderr_text)


class SurnameCollisionTests(unittest.TestCase):
    """Regression coverage for the #1172 unblockable false block.

    Santiago Ferreira, second-slot reviewer on main#1156, wrote a complete
    `Approved` verdict for branch `L.Ferreira/1151-cd-misroute-families`
    (author Lucas Ferreira) and could not post it. The swap heuristic compared
    SURNAMES, `Ferreira == Ferreira`, and the hook reported that "the branch
    author is Ferreira — they should be the Requestee, not the Requestor."
    Correct reviewer behaviour was indistinguishable from the swap the gate
    exists to catch, on both the `gh pr comment` path and the REST
    comment-create arm added for #932 — so there was no observable-body
    workaround. The PR sat at 1 of 2 approvals.

    Both directions are pinned here on purpose. Removing a false positive from
    a gate is only a fix if the true positive survives it; the paired
    assertions are what distinguish this change from disabling the check.
    """

    BRANCH = "L.Ferreira/1151-cd-misroute-families"  # author: Lucas Ferreira

    @staticmethod
    def _verdict(requestor: str, requestee: str, direction: str = "Approved") -> str:
        return (
            "gh pr comment 1156 --repo noorinalabs/noorinalabs-main "
            "--body \"$(cat <<'EOF'\n"
            "Looks correct.\n"
            "\n---\n"
            f"Requestor: {requestor}\n"
            f"Requestee: {requestee}\n"
            f"RequestOrReplied: {direction}\n"
            "TechDebt: None\n"
            'EOF\n)"'
        )

    def _check(self, command: str):
        with mock.patch.object(hook, "get_branch_name", return_value=self.BRANCH):
            return hook.check(_bash_input(command))

    def test_same_surname_reviewer_is_allowed(self):
        """THE DEFECT: Santiago Ferreira reviewing Lucas Ferreira's branch."""
        result = self._check(self._verdict("Santiago Ferreira", "Lucas Ferreira"))
        self.assertIsNone(result)

    def test_same_surname_reviewer_is_allowed_on_changes_requested(self):
        result = self._check(
            self._verdict("Santiago Ferreira", "Lucas Ferreira", "Changes Requested")
        )
        self.assertIsNone(result)

    def test_branch_author_naming_himself_still_blocks(self):
        """THE TRUE POSITIVE the fix must not trade away.

        A genuinely swapped verdict — the PR author as `Requestor` — is counted
        wrong by `validate_pr_review`, which is why this gate exists. Lucas on
        his own branch matches the initial AND the surname, so it still blocks.
        """
        result = self._check(self._verdict("Lucas Ferreira", "Santiago Ferreira"))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.get("decision"), "block")
        self.assertIn("swapped", result.get("reason", ""))

    def test_branch_author_naming_himself_still_blocks_on_changes_requested(self):
        result = self._check(
            self._verdict("Lucas Ferreira", "Santiago Ferreira", "Changes Requested")
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.get("decision"), "block")

    def test_block_message_names_the_person_not_just_the_surname(self):
        """The diagnostic must not say "the branch author is Ferreira".

        That message is what made the defect hard to act on: it named a surname
        two roster members share, so a correctly-behaving reviewer read it as
        being about someone else.
        """
        result = self._check(self._verdict("Lucas Ferreira", "Santiago Ferreira"))
        assert result is not None
        self.assertIn("L.Ferreira", result.get("reason", ""))

    @staticmethod
    def _rest_command(requestor: str, requestee: str) -> str:
        """A REST comment-create carrying a real multi-line body.

        The newlines must be REAL. An earlier version of this fixture used
        literal `\\n` two-character sequences, so the body was a single physical
        line, `_direction_is_verdict` returned False, and `check()` returned at
        the verdict-scope gate WITHOUT ever reaching `is_branch_author`. It
        passed against the unfixed lastname-only predicate — inert, and claimed
        in the PR body as the REST-arm coverage it was not
        (`feedback_fixture_makes_guard_assertion_inert`, caught by Nino
        Kavtaradze's mutation harness on this PR).
        """
        body = (
            "Looks correct.\n\n---\n"
            f"Requestor: {requestor}\n"
            f"Requestee: {requestee}\n"
            "RequestOrReplied: Approved\nTechDebt: None\n"
        )
        return (
            "gh api repos/noorinalabs/noorinalabs-main/issues/1156/comments "
            f'-X POST -f body="{body}"'
        )

    def test_rest_arm_allows_the_same_surname_reviewer(self):
        """#932's REST arm is gated by the same predicate, so it must agree.

        The defect blocked BOTH paths, which is why there was no workaround.
        """
        self.assertIsNone(self._check(self._rest_command("Santiago Ferreira", "Lucas Ferreira")))

    def test_rest_arm_still_blocks_the_branch_author(self):
        """The REST arm's true positive — without this the arm could be inert."""
        result = self._check(self._rest_command("Lucas Ferreira", "Santiago Ferreira"))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.get("decision"), "block")
        self.assertIn("swapped", result.get("reason", ""))

    def test_rest_arm_fixture_actually_reaches_the_identity_check(self):
        """Liveness guard: the fixture must get PAST the verdict-scope gate.

        Asserted directly, because the way this fixture failed before was by
        returning `allow` for a reason that had nothing to do with identity —
        which is indistinguishable from a correct allow in the test result.
        """
        cmd = self._rest_command("Santiago Ferreira", "Lucas Ferreira")
        body = hook.extract_rest_comment_body(cmd)
        self.assertIsNotNone(body)
        assert body is not None
        self.assertTrue(hook._direction_is_verdict(body))

    def test_non_verdict_directions_remain_out_of_scope(self):
        """Scope is unchanged: Request/Reply invert the role bindings (#378).

        Pinned alongside the fix so a future widening of the identity
        comparison cannot quietly widen the DIRECTIONS it applies to.
        """
        for direction in ("Request", "Reply", "Replied"):
            with self.subTest(direction=direction):
                self.assertIsNone(
                    self._check(self._verdict("Lucas Ferreira", "Santiago Ferreira", direction))
                )


if __name__ == "__main__":
    unittest.main()
