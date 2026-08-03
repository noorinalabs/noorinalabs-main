#!/usr/bin/env python3
"""Behavioral tests for block_squash_wave_merge hook.

The hook blocks `gh pr merge <N> --squash` when the PR's base is a wave branch
(`deployments/phase-{P}/wave-{M}`), because squash-merge re-authors the squash
commit to the bare gh principal and breaks the wave→main commit-author gate
(P7W19 #898/#222; memory feedback_wave_branch_merge_not_squash).

The base ref is resolved via a `gh pr view` network call isolated behind
`_resolve_base_ref(..., runner=)`, so tests inject a fake runner — never a real
gh call. Coverage pins: squash-into-wave blocks, squash-into-main allows,
non-squash merges allow, unresolvable PR tokens fail open, and the cheap
`--squash` pre-filter short-circuits before any parse.

Run: ENVIRONMENT=test python3 -m pytest .claude/hooks/tests/test_block_squash_wave_merge.py -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
sys.path.insert(0, str(_HOOKS_DIR))

import block_squash_wave_merge as hook  # noqa: E402


def _input(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


def _runner(base_by_pr: dict[str, str | None]):
    """Build a fake base-ref runner: (pr, repo) -> base name from a lookup."""

    def run(pr, repo):  # noqa: ANN001
        return base_by_pr.get(str(pr))

    return run


WAVE = "deployments/phase-7/wave-19"


class BlocksSquashIntoWaveBranch(unittest.TestCase):
    def test_literal_pr_squash_into_wave_blocks(self):
        result = hook.check(
            _input("gh pr merge 890 --squash"),
            base_runner=_runner({"890": WAVE}),
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["decision"], "block")
        self.assertIn("--merge", result["reason"])
        self.assertIn("890", result["reason"])

    def test_with_repo_flag_blocks_and_echoes_repo(self):
        result = hook.check(
            _input("gh pr merge 218 --squash --repo noorinalabs/noorinalabs-data-acquisition"),
            base_runner=_runner({"218": WAVE}),
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["decision"], "block")
        self.assertIn("--repo noorinalabs/noorinalabs-data-acquisition", result["reason"])

    def test_delete_branch_flag_order_irrelevant(self):
        result = hook.check(
            _input("gh pr merge 1133 --delete-branch --squash"),
            base_runner=_runner({"1133": WAVE}),
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["decision"], "block")

    def test_short_squash_flag_into_wave_blocks(self):
        # gh's documented short form `-s` == `--squash` must also block
        # (cover-all-syntactic-forms — caught in PR #900 review).
        result = hook.check(
            _input("gh pr merge 890 -s"),
            base_runner=_runner({"890": WAVE}),
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["decision"], "block")

    def test_short_squash_with_delete_branch_blocks(self):
        result = hook.check(
            _input("gh pr merge 218 -s -d"),
            base_runner=_runner({"218": WAVE}),
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["decision"], "block")


class RepeatedRepoFlagLastWins(unittest.TestCase):
    """main#1060 finding #3: real gh's `--repo`/`-R` is a single-value pflag,
    so a repeated flag resolves to its LAST occurrence — the resolved repo
    fed to `_resolve_base_ref` (and echoed in the block reason) must be the
    last one, not the first."""

    def test_repeated_repo_flag_echoes_last_value(self):
        result = hook.check(
            _input("gh pr merge 218 --squash --repo noorinalabs/repo-a --repo noorinalabs/repo-b"),
            base_runner=_runner({"218": WAVE}),
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["decision"], "block")
        self.assertIn("--repo noorinalabs/repo-b", result["reason"])
        self.assertNotIn("repo-a", result["reason"])


class AllowsLegitimateMerges(unittest.TestCase):
    def test_squash_into_main_allows(self):
        # The standard GitHub-flow squash for feature work targets main — untouched.
        result = hook.check(
            _input("gh pr merge 500 --squash"),
            base_runner=_runner({"500": "main"}),
        )
        self.assertIsNone(result)

    def test_merge_flag_into_wave_allows(self):
        # `--merge` is the correct method; never blocked even on a wave base.
        result = hook.check(
            _input("gh pr merge 890 --merge"),
            base_runner=_runner({"890": WAVE}),
        )
        self.assertIsNone(result)

    def test_non_merge_gh_command_allows(self):
        result = hook.check(
            _input("gh pr view 890 --json baseRefName"),
            base_runner=_runner({"890": WAVE}),
        )
        self.assertIsNone(result)

    def test_non_bash_tool_allows(self):
        data = {"tool_name": "Edit", "tool_input": {"command": "gh pr merge 890 --squash"}}
        self.assertIsNone(hook.check(data, base_runner=_runner({"890": WAVE})))


class FailsOpen(unittest.TestCase):
    def test_unresolvable_base_fails_open(self):
        # gh view returns None (offline / error) → allow rather than block.
        result = hook.check(
            _input("gh pr merge 890 --squash"),
            base_runner=_runner({"890": None}),
        )
        self.assertIsNone(result)

    def test_non_digit_pr_token_skipped(self):
        # A `$pr` loop variable can't be resolved; batch-loop shape is guarded
        # by validate_pr_review. The runner must never even be consulted.
        def explode(pr, repo):  # noqa: ANN001
            raise AssertionError("runner must not be called for non-digit PR token")

        result = hook.check(_input("gh pr merge $pr --squash"), base_runner=explode)
        self.assertIsNone(result)

    def test_prefilter_short_circuits_non_merge_command(self):
        # No `merge` substring → return before any parse/network. A runner that
        # explodes proves the network path is never reached for the common case.
        def explode(pr, repo):  # noqa: ANN001
            raise AssertionError("runner must not be called when 'merge' absent")

        result = hook.check(_input("ls -la && git status"), base_runner=explode)
        self.assertIsNone(result)

    def test_merge_flag_does_not_consult_runner(self):
        # `gh pr merge --merge` passes the `merge` pre-filter but yields no
        # squash segment, so the base-runner is never consulted → allow.
        def explode(pr, repo):  # noqa: ANN001
            raise AssertionError("runner must not be called for a --merge merge")

        result = hook.check(_input("gh pr merge 890 --merge"), base_runner=explode)
        self.assertIsNone(result)

    def test_short_squash_into_main_allows(self):
        # `-s` into main is the standard feature-work squash — untouched.
        result = hook.check(
            _input("gh pr merge 500 -s"),
            base_runner=_runner({"500": "main"}),
        )
        self.assertIsNone(result)


class HeredocAndSegmentSafety(unittest.TestCase):
    def test_squash_inside_heredoc_body_not_matched(self):
        # `gh pr merge ... --squash` mentioned inside a heredoc body is prose,
        # not a command — must not block.
        cmd = (
            "gh pr comment 5 --body-file - <<'EOF'\nDo not run gh pr merge 890 --squash here.\nEOF"
        )
        result = hook.check(_input(cmd), base_runner=_runner({"890": WAVE}))
        self.assertIsNone(result)

    def test_compound_command_second_segment_blocks(self):
        cmd = 'echo "merging" && gh pr merge 890 --squash'
        result = hook.check(_input(cmd), base_runner=_runner({"890": WAVE}))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["decision"], "block")


class SharedWaveBranchParsingTests(unittest.TestCase):
    """This hook and the merge gate must agree on what a wave branch IS (#1216).

    The hook used to carry its own `^deployments/phase-\\d+/wave-\\d+$`. The
    merge gate now keys a review-policy carve-out on the same charter shape, and
    two hand-maintained copies of one charter shape is exactly what cost the org
    four months of divergence on `extract_branch_author_lastname` (main#1175) —
    where #179 taught one copy the dash separator and the other never learned it.
    """

    def test_the_hook_binds_charter_trailers_predicate(self):
        """Identity, not equivalence. A re-declared local copy fails HERE."""
        sys.path.insert(0, str(_HOOKS_DIR.parent / "lib"))
        import charter_trailer

        self.assertIs(hook.is_wave_branch, charter_trailer.is_wave_branch)

    def test_the_hook_no_longer_declares_its_own_pattern(self):
        """A stale module-level `WAVE_BRANCH_RE` would be dead but readable, and
        the next editor would reasonably believe it is the live definition."""
        self.assertFalse(hasattr(hook, "WAVE_BRANCH_RE"))


class UndashedPhaseWaveBranchTests(unittest.TestCase):
    """The 32-PR blind spot the consolidation closes (#1216).

    `deployments/phase15/wave-1` is a real production base ref. Across the 202
    `deployments/**`-head PRs measured on 2026-08-03, 32 carry the undashed
    `phase{N}` form — in isnad-graph, design-system, data-acquisition and
    landing-page — and the hook's own pattern did not match any of them, so a
    `--squash` into those wave branches was allowed straight through.
    """

    UNDASHED = "deployments/phase15/wave-1"

    def test_squash_into_an_undashed_wave_branch_now_blocks(self):
        result = hook.check(
            _input("gh pr merge 890 --squash"),
            base_runner=_runner({"890": self.UNDASHED}),
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["decision"], "block")

    def test_merge_into_an_undashed_wave_branch_still_allows(self):
        """Anti-vacuity: the test above must not be satisfied by a hook that
        blocks every merge onto that base."""
        self.assertIsNone(
            hook.check(
                _input("gh pr merge 890 --merge"),
                base_runner=_runner({"890": self.UNDASHED}),
            )
        )

    def test_squash_into_a_non_wave_deployments_base_still_allows(self):
        """The widening was `phase-?`, not `deployments/**`. Real ref
        (isnad-graph#603/#612) — blocking here would be a new false positive."""
        self.assertIsNone(
            hook.check(
                _input("gh pr merge 890 --squash"),
                base_runner=_runner({"890": "deployments/phase12/cleanup"}),
            )
        )


if __name__ == "__main__":
    unittest.main()
