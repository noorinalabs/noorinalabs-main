"""Pin `/wave-kickoff` Step 0a's staleness-guard comparison (#1485).

Step 0a's original comparison was ``[ "$SCOPE_TS" \\< "$PRIOR_RETRO_TS" ]`` — a
**bash-only** string-comparison operator inside ``[ ]``. Under zsh (the org's
shell for both the interactive prompt and the agent Bash tool — CLAUDE.md §
Shell environment) that test does not evaluate to false, it **errors**
(``(eval):N: condition expected: <``). An errored test is non-zero, so the
``if`` never fired and a genuinely stale scope silently passed kickoff.

The compounding half: the second ``if`` re-tested nothing and printed
``post-dates last retro`` unconditionally whenever a prior timestamp existed —
so the operator was shown a line asserting the exact ordering property the
guard was supposed to verify, whether or not it held.

This test **extracts the real shell block from `SKILL.md`** (between the
``# BEGIN wave-kickoff-step0a-staleness`` / ``# END wave-kickoff-step0a-staleness``
sentinel comments) and executes it **verbatim under zsh** — the shell it
actually runs in production — following the exact precedent set by
`test_session_start_step0_fallback.py` for `/session-start` Step 0's fallback
block. Restating the comparison logic in Python would pin a copy and prove
nothing about the file the skill actually runs; testing under `sh`/`bash`
would test a shell nobody runs it in and would hide this exact bug.

Renders are pinned as text, not just exit code (per the #1478 review feedback
the issue cites: an absence-only assertion is vacuous). All three outcomes —
verified-in-order, no-prior-timestamp skip, and evaluation failure — must
render three *visibly different* strings, and ``post-dates last retro`` must
never appear unless the comparison actually ran and succeeded.
"""

from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path

SKILL_MD = Path(__file__).resolve().parents[3] / ".claude" / "skills" / "wave-kickoff" / "SKILL.md"
_BEGIN = "# BEGIN wave-kickoff-step0a-staleness"
_END = "# END wave-kickoff-step0a-staleness"

_HAS_ZSH = shutil.which("zsh") is not None


def _extract_block() -> str:
    """The Step 0a staleness-comparison block, straight out of SKILL.md."""
    text = SKILL_MD.read_text()
    if text.count(_BEGIN) != 1 or text.count(_END) != 1:
        raise AssertionError(
            f"expected exactly one {_BEGIN}/{_END} sentinel pair in {SKILL_MD} — "
            "Step 0a's staleness block moved or was duplicated; this test pins it by sentinel"
        )
    body = text.split(_BEGIN, 1)[1].split("\n", 1)[1].split(_END, 1)[0]
    lines = [line for line in body.splitlines() if line.strip()]
    if not lines:
        raise AssertionError("SKILL.md staleness block is empty between its sentinels")
    return "\n".join(lines)


@unittest.skipUnless(_HAS_ZSH, "zsh (the org's shell) not available")
class WaveKickoffStep0aStalenessTest(unittest.TestCase):
    """Execute the real Step 0a staleness block under zsh with $SCOPE_TS /
    $PRIOR_RETRO_TS set as fixture inputs, exactly as the skill's jq reads
    would set them in production."""

    def _run(
        self, scope_ts: str, prior_retro_ts: str, *, path_override: str | None = None
    ) -> subprocess.CompletedProcess[str]:
        script = _extract_block()
        env_lines = [
            f'SCOPE_TS="{scope_ts}"',
            f'PRIOR_RETRO_TS="{prior_retro_ts}"',
        ]
        if path_override is not None:
            env_lines.append(f'PATH="{path_override}"')
        full_script = "\n".join(env_lines) + "\n" + script
        return subprocess.run(
            ["zsh", "-c", full_script],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_stale_scope_predating_retro_fails(self) -> None:
        """THE #1485 CASE: SCOPE_TS genuinely predates PRIOR_RETRO_TS.

        Pre-fix, the errored `\\<` test made this pass through at exit 0.
        Post-fix it must exit 1 and print the ERROR line — and must NOT
        print `post-dates last retro`, since the ordering was never
        verified to hold."""
        res = self._run("2026-01-01T00:00:00Z", "2026-06-01T00:00:00Z")
        self.assertEqual(
            res.returncode,
            1,
            f"expected non-zero exit for a stale scope; "
            f"stdout={res.stdout!r} stderr={res.stderr!r}",
        )
        self.assertIn(
            "ERROR: wave_{M}_scope_reconciled_at (2026-01-01T00:00:00Z) predates last retro "
            "(2026-06-01T00:00:00Z).",
            res.stdout,
        )
        self.assertNotIn("post-dates last retro", res.stdout)

    def test_scope_postdating_retro_passes_and_renders_verified_text(self) -> None:
        """The real wave-31 values from #1485: SCOPE_TS genuinely post-dates
        PRIOR_RETRO_TS. Must exit 0 and render the positive `post-dates last
        retro` string — the comparison ran AND succeeded."""
        res = self._run("2026-08-23T17:09:43Z", "2026-08-13T22:41:19Z")
        self.assertEqual(
            res.returncode,
            0,
            f"expected exit 0 for an in-order scope; stdout={res.stdout!r} stderr={res.stderr!r}",
        )
        self.assertIn(
            "Scope reconciled at: 2026-08-23T17:09:43Z "
            "(post-dates last retro: 2026-08-13T22:41:19Z)",
            res.stdout,
        )
        self.assertNotIn("ERROR", res.stdout)
        self.assertNotIn("check skipped", res.stdout)
        self.assertNotIn("could not be evaluated", res.stdout)

    def test_equal_timestamps_are_not_flagged_as_predating(self) -> None:
        """Equal timestamps are not a *strict* predate — same polarity as
        the original bash `\\<` (strictly-less-than only)."""
        res = self._run("2026-08-23T17:09:43Z", "2026-08-23T17:09:43Z")
        self.assertEqual(res.returncode, 0)
        self.assertIn("post-dates last retro: 2026-08-23T17:09:43Z", res.stdout)

    def test_no_prior_timestamp_skips_check_and_renders_distinct_text(self) -> None:
        """Permissive fallback (unchanged policy, #1485 scope boundary):
        no prior-wave timestamp means the comparison is skipped outright —
        a third, visibly distinct render from both the verified-pass and
        the evaluation-failure cases."""
        res = self._run("2026-08-23T17:09:43Z", "")
        self.assertEqual(res.returncode, 0)
        self.assertIn(
            "Scope reconciled at: 2026-08-23T17:09:43Z "
            "(no prior-wave timestamp — first wave of phase or fresh project; "
            "staleness check skipped)",
            res.stdout,
        )
        self.assertNotIn("post-dates last retro", res.stdout)
        self.assertNotIn("could not be evaluated", res.stdout)

    def test_evaluation_failure_renders_a_third_distinct_string(self) -> None:
        """When `sort`/`head` are unavailable, the comparison cannot be
        evaluated at all. This must render as neither the verified-pass nor
        the skipped-check text — exactly the #1485 bug shape (an
        unevaluated comparison rendering the success text) must not
        recur for this failure mode either."""
        res = self._run("2026-08-23T17:09:43Z", "2026-08-13T22:41:19Z", path_override="")
        self.assertEqual(res.returncode, 0)
        self.assertIn("could not be evaluated", res.stdout)
        self.assertIn("ordering NOT verified", res.stdout)
        self.assertNotIn("post-dates last retro", res.stdout)
        self.assertNotIn("check skipped", res.stdout)
        self.assertNotIn("ERROR", res.stdout)


if __name__ == "__main__":
    unittest.main()
