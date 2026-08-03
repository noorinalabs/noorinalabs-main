#!/usr/bin/env python3
"""Tests for post_wave_kickoff_comment PostToolUse hook.

Two test surfaces:

1. **Fixture-driven scenarios** — `.claude/hooks/fixtures/post_wave_kickoff_comment/`
   contains JSON test cases with this shape:

       {
           "description": "<human label>",
           "command": "<raw bash command string>",
           "status": <cross-repo-status.json dict>,
           "existing_comments": [<comment dicts>],
           "post_succeeds": <bool>,
           "expect_action": "post" | "skip_*" | null,
           "expect_body_contains": [<substrings>]   # only meaningful for "post"
       }

   The injectors in `post_wave_kickoff_comment.check()` (`status_loader`,
   `comment_fetcher`, `comment_poster`, `body_writer`) let each test mock
   the four external interactions (status JSON read, gh comments fetch,
   gh comment post, body file write) without monkeypatching subprocess.

2. **Direct unit tests** — `parse_label_apply_command`,
   `find_assignment_row`, `render_kickoff_comment`,
   `kickoff_already_posted`. These pin behaviors that don't fit cleanly
   into fixture form (regex shapes, table-driven row lookups).

Run:  python3 -m pytest .claude/hooks/tests/test_post_wave_kickoff_comment.py -v
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import __test_helpers  # noqa: E402,F401

_FIXTURES_DIR = __test_helpers.HOOKS_DIR / "fixtures" / "post_wave_kickoff_comment"


import post_wave_kickoff_comment as hook  # noqa: E402


def _load_fixtures() -> list[tuple[str, dict]]:
    fixtures = []
    for path in sorted(_FIXTURES_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        fixtures.append((path.stem, data))
    return fixtures


def _bash(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


class FixtureDrivenScenarioTests(unittest.TestCase):
    """One test per fixture file — generated dynamically."""


def _add_fixture_test(name: str, fixture: dict) -> None:
    description = fixture.get("description", name)
    command = fixture["command"]
    status = fixture.get("status")
    existing_comments = fixture.get("existing_comments", [])
    post_succeeds = fixture.get("post_succeeds", True)
    expect_action = fixture.get("expect_action")
    expect_body_contains = fixture.get("expect_body_contains", [])

    def test_method(self: unittest.TestCase) -> None:
        captured: dict = {}

        def fake_status():
            return status

        def fake_fetch(repo, num):
            return existing_comments

        def fake_post(repo, num, body_path):
            captured["repo"] = repo
            captured["num"] = num
            captured["body_path"] = body_path
            captured["body"] = Path(body_path).read_text(encoding="utf-8")
            return post_succeeds

        with tempfile.TemporaryDirectory() as td:

            def fake_writer(body, repo, num):
                path = Path(td) / f"body-{repo}-{num}.md"
                path.write_text(body, encoding="utf-8")
                return path

            result = hook.check(
                _bash(command),
                status_loader=fake_status,
                comment_fetcher=fake_fetch,
                comment_poster=fake_post,
                body_writer=fake_writer,
            )

            if expect_action is None:
                self.assertIsNone(
                    result,
                    f"{description!r}: expected hook to not apply (None), got: {result}",
                )
                return

            self.assertIsNotNone(
                result,
                f"{description!r}: expected action={expect_action!r}, got None",
            )
            assert result is not None
            self.assertEqual(
                result.get("action"),
                expect_action,
                f"{description!r}: action mismatch: {result}",
            )

            if expect_action == "post":
                for needle in expect_body_contains:
                    self.assertIn(
                        needle,
                        captured.get("body", ""),
                        f"{description!r}: missing expected substring {needle!r} in body:\n"
                        f"{captured.get('body', '(no body captured)')}",
                    )

    test_method.__name__ = f"test_{name}"
    test_method.__doc__ = description
    setattr(FixtureDrivenScenarioTests, test_method.__name__, test_method)


for _fixture_name, _fixture_data in _load_fixtures():
    _add_fixture_test(_fixture_name, _fixture_data)


class ParseLabelApplyCommandTests(unittest.TestCase):
    """Direct coverage of the bash-command parser."""

    def test_canonical_form(self):
        self.assertEqual(
            hook.parse_label_apply_command(
                'gh issue edit 123 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-9"'
            ),
            ("noorinalabs-main", "123", "p3-wave-9", True),
        )

    def test_flag_order_swapped(self):
        self.assertEqual(
            hook.parse_label_apply_command(
                'gh issue edit 456 --add-label "p3-wave-9" --repo noorinalabs/noorinalabs-deploy'
            ),
            ("noorinalabs-deploy", "456", "p3-wave-9", True),
        )

    def test_equals_form(self):
        self.assertEqual(
            hook.parse_label_apply_command(
                "gh issue edit 789 --repo=noorinalabs/noorinalabs-isnad-graph --add-label=p3-wave-8"
            ),
            ("noorinalabs-isnad-graph", "789", "p3-wave-8", True),
        )

    def test_multiple_add_label_picks_wave_label(self):
        """When the command applies BOTH a wave label and an implementer
        label, only the wave label matters for hook trigger."""
        self.assertEqual(
            hook.parse_label_apply_command(
                "gh issue edit 100 --repo noorinalabs/noorinalabs-main "
                '--add-label "Aino_Virtanen" --add-label "p3-wave-9"'
            ),
            ("noorinalabs-main", "100", "p3-wave-9", True),
        )

    def test_non_wave_label_returns_none(self):
        self.assertIsNone(
            hook.parse_label_apply_command(
                'gh issue edit 100 --repo noorinalabs/noorinalabs-main --add-label "tech-debt"'
            )
        )

    def test_non_issue_edit_command_returns_none(self):
        self.assertIsNone(
            hook.parse_label_apply_command(
                'gh pr edit 42 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-9"'
            )
        )

    def test_unrelated_command_returns_none(self):
        self.assertIsNone(hook.parse_label_apply_command("echo hello"))

    def test_empty_command_returns_none(self):
        self.assertIsNone(hook.parse_label_apply_command(""))

    def test_compound_command_picks_label_segment(self):
        """`true && gh issue edit ... --add-label "p3-wave-9"` still matches."""
        self.assertEqual(
            hook.parse_label_apply_command(
                "true && gh issue edit 999 --repo noorinalabs/noorinalabs-main "
                '--add-label "p3-wave-9"'
            ),
            ("noorinalabs-main", "999", "p3-wave-9", True),
        )

    # --- #467 between-wave relabel filter ---

    def test_between_wave_relabel_returns_none(self):
        """Issue #467: `--add-label "p3-wave-11" --remove-label "p3-wave-10"`
        is the carry-forward (between-wave relabel) shape. The kickoff hook
        must NOT fire on these commands — they were generating a 36-event
        annunaki noise burst in P3W11 (all `skip_no_scope`)."""
        self.assertIsNone(
            hook.parse_label_apply_command(
                "gh issue edit 262 --repo noorinalabs/noorinalabs-main "
                '--add-label "p3-wave-11" --remove-label "p3-wave-10"'
            )
        )

    def test_between_wave_relabel_flag_order_swapped_returns_none(self):
        """Same as above but `--remove-label` first → still skipped."""
        self.assertIsNone(
            hook.parse_label_apply_command(
                "gh issue edit 262 --repo noorinalabs/noorinalabs-main "
                '--remove-label "p3-wave-10" --add-label "p3-wave-11"'
            )
        )

    def test_between_wave_relabel_equals_form_returns_none(self):
        """Equals-form flags on a relabel also skip."""
        self.assertIsNone(
            hook.parse_label_apply_command(
                "gh issue edit 262 --repo=noorinalabs/noorinalabs-main "
                "--add-label=p3-wave-11 --remove-label=p3-wave-10"
            )
        )

    def test_add_with_non_wave_remove_still_matches(self):
        """`--add-label "p3-wave-11" --remove-label "tech-debt"` should still
        fire the hook — removing a non-wave label doesn't make this a
        between-wave relabel. The `parse_wave_label_change` helper only
        populates `remove_label` for canonical wave labels, so a non-wave
        remove leaves `remove_label=None` and the filter doesn't trigger."""
        self.assertEqual(
            hook.parse_label_apply_command(
                "gh issue edit 100 --repo noorinalabs/noorinalabs-main "
                '--add-label "p3-wave-11" --remove-label "tech-debt"'
            ),
            ("noorinalabs-main", "100", "p3-wave-11", True),
        )

    def test_initial_add_without_remove_still_matches(self):
        """Regression guard: the common initial-kickoff shape — bare
        `--add-label "p3-wave-11"` with no `--remove-label` — must still
        return the tuple so the hook proceeds to render + post the kickoff
        comment. This pins acceptance criterion #2 from issue #467."""
        self.assertEqual(
            hook.parse_label_apply_command(
                'gh issue edit 200 --repo noorinalabs/noorinalabs-main --add-label "p3-wave-11"'
            ),
            ("noorinalabs-main", "200", "p3-wave-11", True),
        )

    def test_no_repo_returns_none_repo_field(self):
        """#650: a label-apply run from inside the repo omits --repo; the pure
        parser returns repo=None with repo_flag_present=False (the caller
        resolves it from cwd)."""
        self.assertEqual(
            hook.parse_label_apply_command('gh issue edit 601 --add-label "p4-wave-7"'),
            (None, "601", "p4-wave-7", False),
        )

    # --- #985: -R/--repo flag is authoritative over cwd ---

    def test_short_flag_R_resolves_repo(self):
        """#985: the `-R owner/name` short flag (not just `--repo`) is parsed and
        authoritative. Before the fix the parser was blind to `-R`, so a
        child-repo `-R` op fell through to a cwd-based misroute."""
        self.assertEqual(
            hook.parse_label_apply_command(
                'gh issue edit 42 -R noorinalabs/noorinalabs-deploy --add-label "wave-26"'
            ),
            ("noorinalabs-deploy", "42", "wave-26", True),
        )

    def test_short_flag_R_attached_resolves_repo(self):
        """#985/#1057: the POSIX attached-short `-Rowner/name` form resolves too."""
        self.assertEqual(
            hook.parse_label_apply_command(
                'gh issue edit 42 -Rnoorinalabs/noorinalabs-deploy --add-label "wave-26"'
            ),
            ("noorinalabs-deploy", "42", "wave-26", True),
        )

    def test_short_flag_R_equals_resolves_repo(self):
        """#985: the `-R=owner/name` equals form resolves too."""
        self.assertEqual(
            hook.parse_label_apply_command(
                'gh issue edit 42 -R=noorinalabs/noorinalabs-deploy --add-label "wave-26"'
            ),
            ("noorinalabs-deploy", "42", "wave-26", True),
        )

    def test_unexpanded_var_repo_flag_present_but_unresolved(self):
        """#985/#981: `-R $VAR` (shlex leaves `$VAR` literal) is present-but-
        unresolvable → repo=None AND repo_flag_present=True. The True bit is
        what tells `check()` to fail closed instead of misrouting to cwd."""
        self.assertEqual(
            hook.parse_label_apply_command('gh issue edit 42 -R "$DA" --add-label "wave-26"'),
            (None, "42", "wave-26", True),
        )


class FindAssignmentRowTests(unittest.TestCase):
    """Direct coverage of tier-array row lookup with both shapes."""

    def test_explicit_issue_id_match(self):
        status = {
            "wave_9_scope": {
                "tier_1_x": [
                    {"id": "noorinalabs-main#123", "implementer": "A"},
                    {"id": "noorinalabs-deploy#9", "implementer": "B"},
                ]
            }
        }
        row = hook.find_assignment_row(status, "noorinalabs-main", "123", 9)
        self.assertEqual(row["implementer"], "A")

    def test_repo_backlog_match_when_no_explicit_id(self):
        """W6+W7 Tier-1 backlog shape: row has `repo`, no `id`."""
        status = {
            "wave_9_scope": {
                "tier_1_backlog": [
                    {"repo": "noorinalabs-deploy", "implementer": "Santiago Ferreira"}
                ]
            }
        }
        row = hook.find_assignment_row(status, "noorinalabs-deploy", "555", 9)
        self.assertEqual(row["implementer"], "Santiago Ferreira")

    def test_explicit_id_wins_over_repo_match(self):
        """If both shapes are present, the explicit-id row wins."""
        status = {
            "wave_9_scope": {
                "tier_1_backlog": [{"repo": "noorinalabs-main", "implementer": "BACKLOG"}],
                "tier_2_explicit": [{"id": "noorinalabs-main#42", "implementer": "EXPLICIT"}],
            }
        }
        row = hook.find_assignment_row(status, "noorinalabs-main", "42", 9)
        self.assertEqual(row["implementer"], "EXPLICIT")

    def test_no_match_returns_none(self):
        status = {"wave_9_scope": {"tier_1": [{"id": "other#999", "implementer": "X"}]}}
        self.assertIsNone(hook.find_assignment_row(status, "noorinalabs-main", "1", 9))

    def test_empty_scope_returns_none(self):
        self.assertIsNone(hook.find_assignment_row({}, "noorinalabs-main", "1", 9))

    def test_non_tier_keys_ignored(self):
        """Keys not starting with `tier_` (theme, declared_total, etc.) are skipped."""
        status = {
            "wave_9_scope": {
                "theme": "tech-debt",
                "tier_1": [{"id": "noorinalabs-main#1", "implementer": "Y"}],
            }
        }
        row = hook.find_assignment_row(status, "noorinalabs-main", "1", 9)
        self.assertEqual(row["implementer"], "Y")

    def test_dict_row_short_ref_match(self):
        """#586: dict row keyed by `ref` (short form) matches even without `id`."""
        status = {
            "wave_9_scope": {
                "tier_1_x": [
                    {"ref": "main#322", "implementer": "Wanjiku Mwangi"},
                ]
            }
        }
        row = hook.find_assignment_row(status, "noorinalabs-main", "322", 9)
        self.assertEqual(row["implementer"], "Wanjiku Mwangi")

    def test_dict_row_full_id_preferred_when_both_present(self):
        """A dict row with both `id` (full) and `ref` (short) is matched on either."""
        status = {
            "wave_9_scope": {
                "tier_1_x": [
                    {"id": "noorinalabs-deploy#393", "ref": "deploy#393", "implementer": "Lucas"},
                ]
            }
        }
        # Full-name caller resolves via id; the synthesized short-ref also resolves.
        row = hook.find_assignment_row(status, "noorinalabs-deploy", "393", 9)
        self.assertEqual(row["implementer"], "Lucas")

    def test_legacy_plain_string_short_ref_fallback(self):
        """#586: bare short-ref string entries (the pre-conversion /wave-scope
        shape) synthesize a placeholder row instead of silently skipping."""
        status = {
            "wave_14_scope": {
                "tier_1_end_state_rollout": ["main#322", "main#329"],
                "tier_4_remainder": ["main#560"],
            }
        }
        row = hook.find_assignment_row(status, "noorinalabs-main", "560", 14)
        self.assertIsNotNone(row)
        self.assertEqual(row["id"], "noorinalabs-main#560")
        self.assertEqual(row["ref"], "main#560")
        # No implementer/reviewer in the synthesized row → render shows placeholders.
        self.assertNotIn("implementer", row)

    def test_legacy_plain_string_no_match_returns_none(self):
        """A plain-string tier with no matching short-ref still returns None."""
        status = {"wave_14_scope": {"tier_1": ["main#322", "deploy#393"]}}
        self.assertIsNone(hook.find_assignment_row(status, "noorinalabs-main", "999", 14))

    def test_dict_row_wins_over_plain_string(self):
        """When both a dict row and a plain string could match, the dict (with
        real implementer data) is returned, not the placeholder synthesis."""
        status = {
            "wave_14_scope": {
                "tier_1_strings": ["main#322"],
                "tier_2_dicts": [{"id": "noorinalabs-main#322", "implementer": "REAL"}],
            }
        }
        row = hook.find_assignment_row(status, "noorinalabs-main", "322", 14)
        self.assertEqual(row["implementer"], "REAL")

    def test_synthesized_row_renders_with_unassigned_placeholders(self):
        """End-to-end #586: a plain-string match flows through render with
        `(unassigned)` slots rather than producing a silent skip."""
        status = {"wave_14_scope": {"tier_1": ["main#322"]}}
        row = hook.find_assignment_row(status, "noorinalabs-main", "322", 14)
        body = hook.render_kickoff_comment(row, wave_num=14, phase_num=3, repo="noorinalabs-main")
        self.assertIn("Requestee: (unassigned)", body)
        self.assertIn("- Peer reviewer: (unassigned)", body)
        self.assertIn("- Secondary reviewer: (unassigned)", body)


class RenderKickoffCommentTests(unittest.TestCase):
    """Direct coverage of comment body rendering."""

    def test_canonical_render(self):
        row = {
            "implementer": "Aino Virtanen",
            "reviewer": "Nadia Khoury",
            "reviewer_2": "Santiago Ferreira",
            "priority": "tech-debt",
        }
        # Explicit merge model: the wave-branch base is no longer the
        # unconditional default (#1141), so the canonical render pins it by
        # declaring the model the base belongs to.
        body = hook.render_kickoff_comment(
            row, wave_num=9, phase_num=3, repo="noorinalabs-main", merge_model="wave-branch"
        )
        self.assertIn("Requestor: Fatima Okonkwo", body)
        self.assertIn("Requestee: Aino Virtanen", body)
        self.assertIn("RequestOrReplied: Request", body)
        self.assertIn("**Wave 9 Kickoff — Phase 3**", body)
        self.assertIn("- Peer reviewer: Nadia Khoury", body)
        self.assertIn("- Secondary reviewer: Santiago Ferreira", body)
        self.assertIn("- Branch from: `deployments/phase-3/wave-9`", body)
        self.assertIn("- Priority: tech-debt", body)

    def test_missing_optional_fields_show_unassigned(self):
        """Missing reviewer/reviewer_2 render as `(unassigned)`, not blank."""
        row = {"implementer": "Aino Virtanen"}
        body = hook.render_kickoff_comment(row, wave_num=9, phase_num=3, repo="noorinalabs-main")
        self.assertIn("- Peer reviewer: (unassigned)", body)
        self.assertIn("- Secondary reviewer: (unassigned)", body)
        self.assertIn("- Priority: feature", body)  # default priority

    def test_implementer_missing_shows_unassigned(self):
        body = hook.render_kickoff_comment({}, wave_num=9, phase_num=3, repo="noorinalabs-main")
        self.assertIn("Requestee: (unassigned)", body)


class KickoffAlreadyPostedTests(unittest.TestCase):
    """Idempotency check across various comment shapes."""

    def test_returns_true_on_charter_heading(self):
        def fetch(r, n):
            return [{"body": "**Wave 9 Kickoff — Phase 3**\n\nbody"}]

        self.assertTrue(hook.kickoff_already_posted("x", "1", fetch_comments=fetch))

    def test_returns_true_on_hyphen_form(self):
        """Tolerate a hyphen-surrounded form in case the em-dash got dropped."""

        def fetch(r, n):
            return [{"body": "**Wave 9 Kickoff - Phase 3**"}]

        self.assertTrue(hook.kickoff_already_posted("x", "1", fetch_comments=fetch))

    def test_returns_false_on_no_kickoff_comment(self):
        def fetch(r, n):
            return [{"body": "Some other comment."}]

        self.assertFalse(hook.kickoff_already_posted("x", "1", fetch_comments=fetch))

    def test_returns_false_on_no_comments(self):
        def fetch(r, n):
            return []

        self.assertFalse(hook.kickoff_already_posted("x", "1", fetch_comments=fetch))

    def test_returns_false_on_fetch_failure(self):
        """fetch returning None (gh CLI failed) → don't suppress; let the
        downstream post attempt and annunaki-log on real failure."""

        def fetch(r, n):
            return None

        self.assertFalse(hook.kickoff_already_posted("x", "1", fetch_comments=fetch))

    def test_wave_specific_same_wave_still_idempotent(self):
        """#547: with wave_num=13, a Wave 13 comment still counts as posted."""

        def fetch(r, n):
            return [{"body": "**Wave 13 Kickoff — Phase 3**\n\nbody"}]

        self.assertTrue(hook.kickoff_already_posted("x", "1", wave_num=13, fetch_comments=fetch))

    def test_wave_specific_prior_wave_not_counted(self):
        """#547 core fix: with wave_num=13, a stale Wave 12 carry-forward
        kickoff comment does NOT count as the Wave 13 kickoff → not posted
        yet, so the hook will post a fresh one."""

        def fetch(r, n):
            return [{"body": "**Wave 12 Kickoff — Phase 3**\n\nprior-wave body"}]

        self.assertFalse(hook.kickoff_already_posted("x", "1", wave_num=13, fetch_comments=fetch))

    def test_wave_specific_multi_digit_wave_not_substring_matched(self):
        """#547 edge: wave_num=2 must not match a 'Wave 12 Kickoff' comment
        (the literal-digit interpolation is `\\bWave 2 ` via \\s, but the
        \\s+ boundary + the 'Kickoff' suffix prevent '12' from satisfying
        'Wave 2 Kickoff'). Guards against a naive substring regex."""

        def fetch(r, n):
            return [{"body": "**Wave 12 Kickoff — Phase 3**"}]

        self.assertFalse(hook.kickoff_already_posted("x", "1", wave_num=2, fetch_comments=fetch))

    def test_wave_none_falls_back_to_wave_agnostic(self):
        """#547: wave_num=None preserves legacy any-wave semantics — any
        kickoff heading counts."""

        def fetch(r, n):
            return [{"body": "**Wave 7 Kickoff — Phase 2**"}]

        self.assertTrue(hook.kickoff_already_posted("x", "1", wave_num=None, fetch_comments=fetch))


class NonBashToolTests(unittest.TestCase):
    """tool_name != Bash → early return None."""

    def test_edit_tool_not_matched(self):
        result = hook.check(
            {
                "tool_name": "Edit",
                "tool_input": {"command": 'gh issue edit 1 --repo r --add-label "p3-wave-9"'},
            }
        )
        self.assertIsNone(result)

    def test_empty_command_not_matched(self):
        result = hook.check({"tool_name": "Bash", "tool_input": {"command": ""}})
        self.assertIsNone(result)


class AmbientRepoResolutionTests(unittest.TestCase):
    """#650: a label-apply run from inside the repo omits --repo; the kickoff
    hook resolves the ambient repo from the invocation cwd before rendering
    and posting the kickoff comment."""

    _ORIGIN = "git@github.com:noorinalabs/noorinalabs-main.git\n"

    def _status(self):
        return {
            "wave_7_scope": {
                "tier_1_close_out": [
                    {
                        "id": "noorinalabs-main#601",
                        "implementer": "Aino Virtanen",
                        "reviewer": "Weronika Zielinska",
                        "reviewer_2": "Nino Kavtaradze",
                    }
                ]
            }
        }

    def test_no_repo_resolves_and_posts(self):
        captured = {}

        def fake_post(repo, num, body_path):
            captured["repo"] = repo
            captured["num"] = num
            return True

        with tempfile.TemporaryDirectory() as td:

            def fake_writer(body, repo, num):
                path = Path(td) / f"body-{repo}-{num}.md"
                path.write_text(body, encoding="utf-8")
                return path

            result = hook.check(
                _bash('gh issue edit 601 --add-label "p4-wave-7"'),
                status_loader=self._status,
                comment_fetcher=lambda repo, num: [],
                comment_poster=fake_post,
                body_writer=fake_writer,
                git_runner=lambda _cwd: self._ORIGIN,
            )
        self.assertEqual(result["action"], "post")
        self.assertEqual(result["repo"], "noorinalabs-main")
        self.assertEqual(captured["repo"], "noorinalabs-main")

    def test_no_repo_unresolvable_skips_no_repo_context(self):
        result = hook.check(
            _bash('gh issue edit 601 --add-label "p4-wave-7"'),
            status_loader=self._status,
            git_runner=lambda _cwd: None,
        )
        self.assertEqual(result["action"], "skip_no_repo_context")
        self.assertEqual(result["issue"], "601")

    def test_explicit_repo_does_not_invoke_git_runner(self):
        calls = [0]

        def runner(_cwd):
            calls[0] += 1
            return self._ORIGIN

        with tempfile.TemporaryDirectory() as td:

            def fake_writer(body, repo, num):
                path = Path(td) / f"body-{repo}-{num}.md"
                path.write_text(body, encoding="utf-8")
                return path

            result = hook.check(
                _bash(
                    'gh issue edit 601 --repo noorinalabs/noorinalabs-main --add-label "p4-wave-7"'
                ),
                status_loader=self._status,
                comment_fetcher=lambda repo, num: [],
                comment_poster=lambda repo, num, path: True,
                body_writer=fake_writer,
                git_runner=runner,
            )
        self.assertEqual(result["action"], "post")
        self.assertEqual(calls[0], 0, "explicit --repo must not trigger ambient resolution")


class RepoFlagAuthoritativeTests(unittest.TestCase):
    """#985: the -R/--repo flag is AUTHORITATIVE over the invocation cwd.

    A subagent running in a child-repo worktree issues `gh issue edit -R
    noorinalabs/<child> ...` whose cwd `origin` may still resolve to the PARENT
    org repo. The kickoff comment must route to the flag's repo, not cwd — the
    recurring misroute the W25 retro flagged. And an unexpanded `-R $VAR` must
    fail closed (#981), never silently misroute to cwd.
    """

    # cwd resolves to the PARENT repo — the misroute source when a child-repo
    # op runs from a worktree the hook reads as the parent.
    _PARENT_ORIGIN = "git@github.com:noorinalabs/noorinalabs-main.git\n"

    def _status(self):
        return {
            "current_phase": 9,
            "wave_26_scope": {
                "tier_1": [
                    {
                        "id": "noorinalabs-deploy#42",
                        "implementer": "Lucas Ferreira",
                        "reviewer": "Aino Virtanen",
                        "reviewer_2": "Nino Kavtaradze",
                    }
                ]
            },
        }

    def _writer(self, td):
        def fake_writer(body, repo, num):
            path = Path(td) / f"body-{repo}-{num}.md"
            path.write_text(body, encoding="utf-8")
            return path

        return fake_writer

    def test_R_flag_routes_to_flag_repo_not_cwd(self):
        """The bite: the deploy row is the ONLY row in scope. If the hook used
        cwd (main) instead of the `-R noorinalabs/noorinalabs-deploy` flag it
        would search for a `noorinalabs-main#42` row, find none, and return
        skip_no_row. Routing to the flag's repo is what makes it post."""
        captured = {}

        def fake_post(repo, num, body_path):
            captured["repo"] = repo
            return True

        with tempfile.TemporaryDirectory() as td:
            result = hook.check(
                _bash('gh issue edit 42 -R noorinalabs/noorinalabs-deploy --add-label "wave-26"'),
                status_loader=self._status,
                comment_fetcher=lambda repo, num: [],
                comment_poster=fake_post,
                body_writer=self._writer(td),
                git_runner=lambda _cwd: self._PARENT_ORIGIN,
            )
        self.assertEqual(result["action"], "post")
        self.assertEqual(result["repo"], "noorinalabs-deploy")
        self.assertEqual(captured["repo"], "noorinalabs-deploy")

    def test_R_flag_does_not_invoke_git_runner(self):
        calls = [0]

        def runner(_cwd):
            calls[0] += 1
            return self._PARENT_ORIGIN

        with tempfile.TemporaryDirectory() as td:
            hook.check(
                _bash('gh issue edit 42 -R noorinalabs/noorinalabs-deploy --add-label "wave-26"'),
                status_loader=self._status,
                comment_fetcher=lambda repo, num: [],
                comment_poster=lambda r, n, p: True,
                body_writer=self._writer(td),
                git_runner=runner,
            )
        self.assertEqual(calls[0], 0, "-R flag must not trigger ambient cwd resolution")

    def test_unexpanded_var_repo_fails_closed_no_cwd_fallback(self):
        """#985/#981: `-R $VAR` (shlex leaves `$DA` literal) → skip_unresolvable_repo.
        The hook must NOT fall back to cwd (which would misroute to the parent);
        git_runner is wired to a healthy parent origin to prove it is never
        consulted for a present-but-unresolvable repo flag."""
        calls = [0]

        def runner(_cwd):
            calls[0] += 1
            return self._PARENT_ORIGIN

        result = hook.check(
            _bash('gh issue edit 42 -R "$DA" --add-label "wave-26"'),
            status_loader=self._status,
            git_runner=runner,
        )
        self.assertEqual(result["action"], "skip_unresolvable_repo")
        self.assertEqual(result["issue"], "42")
        self.assertEqual(calls[0], 0, "unresolvable -R must NOT fall back to cwd")


class PhaseAgnosticLabelForm(unittest.TestCase):
    """#810: the kickoff hook fires on the new `wave-{X}` label form, recovering
    the (derived-display) phase from cross-repo-status.json, and skips the
    `wave-x` placeholder (not a per-issue kickoff)."""

    def _status(self):
        return {
            "current_phase": 4,
            "phase": "phase-4",
            "wave_7_scope": {
                "tier_1_close_out": [
                    {
                        "id": "noorinalabs-main#601",
                        "implementer": "Aino Virtanen",
                        "reviewer": "Weronika Zielinska",
                        "reviewer_2": "Nino Kavtaradze",
                    }
                ]
            },
        }

    def test_global_form_posts_with_phase_from_status(self):
        captured = {}

        def fake_post(repo, num, body_path):
            captured["body"] = Path(body_path).read_text(encoding="utf-8")
            return True

        with tempfile.TemporaryDirectory() as td:

            def fake_writer(body, repo, num):
                path = Path(td) / f"body-{repo}-{num}.md"
                path.write_text(body, encoding="utf-8")
                return path

            result = hook.check(
                _bash('gh issue edit 601 --repo noorinalabs/noorinalabs-main --add-label "wave-7"'),
                status_loader=self._status,
                comment_fetcher=lambda repo, num: [],
                comment_poster=fake_post,
                body_writer=fake_writer,
            )
        self.assertEqual(result["action"], "post")
        # Phase 4 was recovered from status (the new label carries no phase).
        self.assertIn("Phase 4", captured["body"])
        self.assertIn("Wave 7", captured["body"])

    def test_placeholder_form_is_not_a_kickoff(self):
        """`wave-x` carries no wave id → not a per-issue kickoff → None."""
        result = hook.check(
            _bash('gh issue edit 601 --repo noorinalabs/noorinalabs-main --add-label "wave-x"'),
            status_loader=self._status,
        )
        self.assertIsNone(result)

    def test_global_form_no_phase_in_status_skips(self):
        """New-form label but status has no resolvable phase → skip_no_phase."""

        def _status_no_phase():
            return {
                "wave_7_scope": {
                    "tier_1_close_out": [
                        {"id": "noorinalabs-main#601", "implementer": "Aino Virtanen"}
                    ]
                }
            }

        result = hook.check(
            _bash('gh issue edit 601 --repo noorinalabs/noorinalabs-main --add-label "wave-7"'),
            status_loader=_status_no_phase,
        )
        self.assertEqual(result["action"], "skip_no_phase")


_EDIT_REPO = "--repo noorinalabs/noorinalabs-main"


class MergeModelAwareBranchBase(unittest.TestCase):
    """main#1141 problem 1 — the branch base must follow the wave merge model.

    `render_kickoff_comment` hardcoded `deployments/phase-{P}/wave-{M}`. Since
    the 2026-06-09 every-wave-merges-to-main directive, `direct-to-main` is the
    COMMON case, so every kickoff comment on waves 28 and 29 pointed the
    implementer at a ref that will never exist.
    """

    ROW = {"implementer": "Nino Kavtaradze", "reviewer": "Aino Virtanen"}

    def test_direct_to_main_renders_main_base(self) -> None:
        body = hook.render_kickoff_comment(
            self.ROW,
            wave_num=29,
            phase_num=10,
            repo="noorinalabs-main",
            merge_model="direct-to-main",
        )
        self.assertIn("- Branch from: `main`", body)
        self.assertIn("- PR base: `main` (wave merge model: `direct-to-main`)", body)
        self.assertNotIn("deployments/phase-10/wave-29", body)

    def test_wave_branch_renders_wave_branch_base(self) -> None:
        body = hook.render_kickoff_comment(
            self.ROW,
            wave_num=29,
            phase_num=10,
            repo="noorinalabs-main",
            merge_model="wave-branch",
        )
        self.assertIn("- Branch from: `deployments/phase-10/wave-29`", body)
        self.assertIn("wave merge model: `wave-branch`", body)

    def test_absent_model_defaults_to_main(self) -> None:
        """The recoverable failure is preferred to the hard block.

        A nonexistent wave branch stops the implementer dead; branching from
        `main` on a wave-branch wave is a PR-base retarget.
        """
        body = hook.render_kickoff_comment(
            self.ROW, wave_num=29, phase_num=10, repo="noorinalabs-main", merge_model=None
        )
        self.assertIn("- Branch from: `main`", body)
        self.assertIn("NOT declared", body)
        self.assertNotIn("deployments/phase-10/wave-29", body)

    def test_unknown_model_defaults_to_main(self) -> None:
        body = hook.render_kickoff_comment(
            self.ROW, wave_num=29, phase_num=10, repo="noorinalabs-main", merge_model="typo-model"
        )
        self.assertIn("- Branch from: `main`", body)

    def test_default_argument_is_the_safe_base(self) -> None:
        """A caller that never heard of merge models cannot emit a dead ref."""
        body = hook.render_kickoff_comment(self.ROW, 29, 10, "noorinalabs-main")
        self.assertIn("- Branch from: `main`", body)

    def test_merge_model_constants_match_wave_merge_model(self) -> None:
        """The duplicated enum must not drift from `.claude/lib/wave_merge_model.py`."""
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
        import wave_merge_model  # noqa: PLC0415

        self.assertEqual(hook.DIRECT_TO_MAIN, wave_merge_model.DIRECT_TO_MAIN)
        self.assertEqual(hook.WAVE_BRANCH, wave_merge_model.WAVE_BRANCH)
        self.assertEqual(
            {hook.DIRECT_TO_MAIN, hook.WAVE_BRANCH}, set(wave_merge_model.MERGE_MODELS)
        )


class ReadMergeModel(unittest.TestCase):
    """Both recorded locations, and a fail-safe on anything unrecognized."""

    def test_top_level_key(self) -> None:
        self.assertEqual(
            hook.read_merge_model({"wave_29_merge_model": "direct-to-main"}, 29),
            "direct-to-main",
        )

    def test_scope_key(self) -> None:
        self.assertEqual(
            hook.read_merge_model({"wave_29_scope": {"merge_model": "wave-branch"}}, 29),
            "wave-branch",
        )

    def test_top_level_wins_over_scope(self) -> None:
        status = {
            "wave_29_merge_model": "direct-to-main",
            "wave_29_scope": {"merge_model": "wave-branch"},
        }
        self.assertEqual(hook.read_merge_model(status, 29), "direct-to-main")

    def test_scope_used_when_top_level_absent(self) -> None:
        status = {"wave_29_scope": {"merge_model": "direct-to-main"}}
        self.assertEqual(hook.read_merge_model(status, 29), "direct-to-main")

    def test_absent_is_none(self) -> None:
        self.assertIsNone(hook.read_merge_model({}, 29))

    def test_invalid_value_is_none_not_passthrough(self) -> None:
        self.assertIsNone(hook.read_merge_model({"wave_29_merge_model": "direct_to_main"}, 29))

    def test_non_string_value_is_none(self) -> None:
        self.assertIsNone(hook.read_merge_model({"wave_29_merge_model": 7}, 29))

    def test_non_dict_scope_is_tolerated(self) -> None:
        self.assertIsNone(hook.read_merge_model({"wave_29_scope": ["main#1"]}, 29))


class CheckAppliesMergeModelEndToEnd(unittest.TestCase):
    """The rendered body that actually gets POSTED must carry the right base."""

    def _run(self, status: dict) -> str:
        captured: dict = {}

        def body_writer(body, repo, num):
            captured["body"] = body
            return Path("/dev/null")

        result = hook.check(
            {
                "tool_name": "Bash",
                "tool_input": {"command": f'gh issue edit 1114 {_EDIT_REPO} --add-label "wave-29"'},
            },
            status_loader=lambda: status,
            comment_fetcher=lambda r, n: [],
            comment_poster=lambda r, n, p: True,
            body_writer=body_writer,
        )
        assert result is not None
        self.assertEqual(result["action"], "post")
        return captured["body"]

    def _status(self, **extra) -> dict:
        status = {
            "current_phase": 10,
            "wave_29_scope": {
                "tier_1": [{"id": "noorinalabs-main#1114", "implementer": "Nino Kavtaradze"}]
            },
        }
        status.update(extra)
        return status

    def test_direct_to_main_wave(self) -> None:
        body = self._run(self._status(wave_29_merge_model="direct-to-main"))
        self.assertIn("- Branch from: `main`", body)

    def test_wave_branch_wave(self) -> None:
        body = self._run(self._status(wave_29_merge_model="wave-branch"))
        self.assertIn("- Branch from: `deployments/phase-10/wave-29`", body)

    def test_undeclared_wave(self) -> None:
        body = self._run(self._status())
        self.assertIn("- Branch from: `main`", body)


class WrappedLabelApplyReachesTheHook(unittest.TestCase):
    """main#1141 problem 2 — the full repro table, at the hook's own entry point."""

    def test_repro_table(self) -> None:
        rows = [
            ("plain", f'gh issue edit 1114 {_EDIT_REPO} --add-label "wave-29"', True),
            (
                "redirect",
                f'gh issue edit 1114 {_EDIT_REPO} --add-label "wave-29" >/dev/null 2>&1',
                True,
            ),
            (
                "and-chain",
                f'gh issue edit 1114 {_EDIT_REPO} --add-label "wave-29" && echo ok',
                True,
            ),
            (
                "timeout-prefix",
                f'timeout 45 gh issue edit 1114 {_EDIT_REPO} --add-label "wave-29"',
                True,
            ),
            (
                "loop-literal-number",
                f'for x in a; do gh issue edit 1114 {_EDIT_REPO} --add-label "wave-29"; done',
                True,
            ),
            (
                # Unfixable at the command layer: the number is not in the
                # string. Covered by the state-based sweep instead.
                "loop-variable",
                f'for n in 1114 1116; do gh issue edit "$n" {_EDIT_REPO} '
                '--add-label "wave-29"; done',
                False,
            ),
        ]
        for name, command, should_parse in rows:
            with self.subTest(row=name):
                parsed = hook.parse_label_apply_command(command)
                if should_parse:
                    self.assertIsNotNone(parsed, f"{name} must parse after #1141")
                    assert parsed is not None
                    self.assertEqual(parsed[1], "1114")
                    self.assertEqual(parsed[2], "wave-29")
                else:
                    self.assertIsNone(parsed)


class SilentDeclineIsSurfaced(unittest.TestCase):
    """A label lands, the hook cannot act — it must SAY SO (main#1141).

    The primary bug class is the silent no-op, not the parse gap: 14 issues
    labeled, 0 comments posted, caught days later by an unrelated audit.
    """

    def _check(self, command: str, logs: list):
        original = hook.log_posttooluse_event
        hook.log_posttooluse_event = lambda *a: logs.append(a)
        try:
            return hook.check({"tool_name": "Bash", "tool_input": {"command": command}})
        finally:
            hook.log_posttooluse_event = original

    def test_loop_variable_apply_is_logged_and_reported(self) -> None:
        logs: list = []
        result = self._check(
            f'for n in 1114 1116; do gh issue edit "$n" {_EDIT_REPO} --add-label "wave-29"; done',
            logs,
        )
        self.assertEqual(result["action"], "skip_unresolved_issue_number")
        self.assertEqual(result["labels"], "wave-29")
        # Counts SHAPES, not issues: one loop == one unresolved edit, even
        # though it will touch two issues (main#1141 review nit — the key is
        # named for what it counts so the number cannot be misread).
        self.assertEqual(result["unresolved_edits"], 1)
        self.assertEqual(len(logs), 1)
        self.assertIn("kickoff_sweep", logs[0][2])

    def test_dispatcher_surfaces_the_decline(self) -> None:
        """`EMIT_DISPATCH_SUMMARY` turns the action dict into an operator message."""
        self.assertTrue(hook.EMIT_DISPATCH_SUMMARY)

    def test_unrelated_command_stays_silent(self) -> None:
        logs: list = []
        self.assertIsNone(self._check("git status", logs))
        self.assertEqual(logs, [])

    def test_non_wave_label_stays_silent(self) -> None:
        logs: list = []
        self.assertIsNone(
            self._check(
                f'for n in 1; do gh issue edit "$n" {_EDIT_REPO} --add-label "bug"; done', logs
            )
        )
        self.assertEqual(logs, [])

    def test_relabel_shape_stays_silent(self) -> None:
        """#467 carry-forward relabels are not kickoffs — logging them was a
        36-event annunaki noise burst in P3W11."""
        logs: list = []
        self.assertIsNone(
            self._check(
                f'for n in 1; do gh issue edit "$n" {_EDIT_REPO} --add-label "wave-29" '
                '--remove-label "wave-28"; done',
                logs,
            )
        )
        self.assertEqual(logs, [])


class KickoffCommentStateTriState(unittest.TestCase):
    """main#1145 — `unknown` must be its own state, not folded into `absent`."""

    HEADING = [{"body": "**Wave 29 Kickoff — Phase 10**\n\nbody"}]

    def test_present(self) -> None:
        self.assertEqual(
            hook.kickoff_comment_state("r", "1", 29, fetch_comments=lambda r, n: self.HEADING),
            hook.KICKOFF_PRESENT,
        )

    def test_absent(self) -> None:
        self.assertEqual(
            hook.kickoff_comment_state("r", "1", 29, fetch_comments=lambda r, n: []),
            hook.KICKOFF_ABSENT,
        )

    def test_unknown_on_fetch_failure(self) -> None:
        self.assertEqual(
            hook.kickoff_comment_state("r", "1", 29, fetch_comments=lambda r, n: None),
            hook.KICKOFF_UNKNOWN,
        )

    def test_three_states_are_distinct(self) -> None:
        self.assertEqual(len({hook.KICKOFF_PRESENT, hook.KICKOFF_ABSENT, hook.KICKOFF_UNKNOWN}), 3)

    def test_wave_specific_carry_forward_is_absent_not_present(self) -> None:
        """#547 semantics survive the tri-state refactor."""
        prior = [{"body": "**Wave 28 Kickoff — Phase 10**"}]
        self.assertEqual(
            hook.kickoff_comment_state("r", "1", 29, fetch_comments=lambda r, n: prior),
            hook.KICKOFF_ABSENT,
        )


class KickoffAlreadyPostedContractPreserved(unittest.TestCase):
    """The bool wrapper keeps its historical fail-open contract (main#1145).

    Failing open is correct for the HOOK — it posts at most one comment per
    label-apply, and the failure it guards against (#286) is a kickoff that
    never gets posted at all. It is wrong for the SWEEP, which is why the
    sweep uses the tri-state instead. Both behaviors are pinned so neither
    drifts into the other.
    """

    def test_false_on_fetch_failure(self) -> None:
        self.assertFalse(
            hook.kickoff_already_posted("r", "1", 29, fetch_comments=lambda r, n: None)
        )

    def test_false_when_absent(self) -> None:
        self.assertFalse(hook.kickoff_already_posted("r", "1", 29, fetch_comments=lambda r, n: []))

    def test_true_when_present(self) -> None:
        body = [{"body": "**Wave 29 Kickoff — Phase 10**"}]
        self.assertTrue(hook.kickoff_already_posted("r", "1", 29, fetch_comments=lambda r, n: body))

    def test_hook_still_posts_when_the_fetch_fails(self) -> None:
        """End-to-end: the PostToolUse path keeps posting on a broken fetch.

        But it reports `post_unverified`, not `post` — review round 3. The
        fail-open decision stands; collapsing it into a verified post was the
        last silent state-collapse in a PR about silent state-collapses.
        """
        status = {
            "current_phase": 10,
            "wave_29_merge_model": "direct-to-main",
            "wave_29_scope": {"tier_1": [{"id": "noorinalabs-main#1114", "implementer": "N"}]},
        }
        result = hook.check(
            _bash(f'gh issue edit 1114 {_EDIT_REPO} --add-label "wave-29"'),
            status_loader=lambda: status,
            comment_fetcher=lambda r, n: None,
            comment_poster=lambda r, n, p: True,
            body_writer=lambda b, r, n: Path("/dev/null"),
        )
        assert result is not None
        self.assertEqual(result["action"], "post_unverified")

    def test_unverified_post_is_logged(self) -> None:
        logs: list = []
        original = hook.log_posttooluse_event
        hook.log_posttooluse_event = lambda *a: logs.append(a)
        try:
            hook.check(
                _bash(f'gh issue edit 1114 {_EDIT_REPO} --add-label "wave-29"'),
                status_loader=lambda: {
                    "current_phase": 10,
                    "wave_29_scope": {
                        "tier_1": [{"id": "noorinalabs-main#1114", "implementer": "N"}]
                    },
                },
                comment_fetcher=lambda r, n: None,
                comment_poster=lambda r, n, p: True,
                body_writer=lambda b, r, n: Path("/dev/null"),
            )
        finally:
            hook.log_posttooluse_event = original
        self.assertEqual(len(logs), 1)
        self.assertIn("post_unverified", logs[0][2])

    def test_verified_post_is_not_logged_as_unverified(self) -> None:
        logs: list = []
        original = hook.log_posttooluse_event
        hook.log_posttooluse_event = lambda *a: logs.append(a)
        try:
            result = hook.check(
                _bash(f'gh issue edit 1114 {_EDIT_REPO} --add-label "wave-29"'),
                status_loader=lambda: {
                    "current_phase": 10,
                    "wave_29_scope": {
                        "tier_1": [{"id": "noorinalabs-main#1114", "implementer": "N"}]
                    },
                },
                comment_fetcher=lambda r, n: [],
                comment_poster=lambda r, n, p: True,
                body_writer=lambda b, r, n: Path("/dev/null"),
            )
        finally:
            hook.log_posttooluse_event = original
        assert result is not None
        self.assertEqual(result["action"], "post")
        self.assertEqual(logs, [])


if __name__ == "__main__":
    unittest.main()
