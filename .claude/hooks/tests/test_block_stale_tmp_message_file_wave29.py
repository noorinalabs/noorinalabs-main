#!/usr/bin/env python3
"""Wave-29 harvested false-positive fixtures for block_stale_tmp_message_file (#1352).

`block_stale_tmp_message_file` scored 0/11 precision in wave-29 — every one
of the 11 blocks the hook fired was a false positive: a PR/review body the
invoking agent had just authored, in its OWN session-scoped scratchpad
(`/tmp/claude-<uid>/<repo-slug>/<session-uuid>/scratchpad/...`), simply
because the agent spent more than `STALE_TMP_THRESHOLD_SECONDS` (30s)
between writing the body and posting it (the write-then-verify-then-post
shape, not the same-command heredoc shape the threshold was calibrated
for). The literal scratchpad paths from wave-29 no longer exist on disk
(session-scoped, long since cleaned up) so these fixtures reconstruct the
REPORTED SHAPE from the issue #1352 table — command form, body-file
description, and (for the one row where it's known) the body filename —
using synthetic session UUIDs. What matters for this hook is the shape
(session-id embedded in the /tmp path + an mtime past the threshold), which
these fixtures reproduce exactly.

Each of the 11 must ALLOW post-fix. Pre-fix, every one of them BLOCKS —
see the PR body for the captured pre-fix pytest failure output.

Row 8 (`touch <file> && gh pr create ...`) gets its OWN dedicated test
class below (``TouchWorkaroundOrderingDefectTests``) with an extreme mtime
age specifically to demonstrate that a threshold-only fix (e.g. raising
30s to 15 minutes) could NOT close the ordering defect — only a
session-identity-based exemption can, because no finite threshold
distinguishes "the operator is still composing the body" from "this file
is a stale leftover" when both look like a large mtime gap. The hook stats
the file BEFORE the gated Bash command runs, so a `touch` embedded in the
very command being gated can never refresh the mtime the hook sees.
"""

from __future__ import annotations

import os
import tempfile
import time
import unittest
import uuid
from pathlib import Path

import _test_helpers  # noqa: E402,F401
import block_stale_tmp_message_file as hook  # noqa: E402


def _touch(path: str, age_seconds: float) -> None:
    """Create the file and stamp it with mtime = now - age_seconds."""
    Path(path).write_text("body", encoding="utf-8")
    target = time.time() - age_seconds
    os.utime(path, (target, target))


def _scratchpad_dir(session_id: str) -> str:
    """Build a synthetic session-scoped scratchpad dir matching the real
    Claude Code convention: /tmp/claude-<uid>/<repo-slug>/<session-id>/scratchpad.
    """
    base = tempfile.mkdtemp(dir="/tmp", prefix=f"claude-1000-noorinalabs-main-{session_id}-")
    scratch = os.path.join(base, session_id, "scratchpad")
    os.makedirs(scratch, exist_ok=True)
    return scratch


def _bash(command: str, session_id: str) -> dict:
    return {
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "session_id": session_id,
    }


class Wave29HarvestedFalsePositiveTests(unittest.TestCase):
    """The 11 wave-29 blocks from issue #1352 — all false positives.

    Every row is a body file under the AUTHORING agent's OWN
    session-scoped scratchpad, aged past the 30s threshold because the
    agent spent real time composing/verifying the body before posting.
    Post-fix, all 11 must ALLOW. Pre-fix, all 11 BLOCK (see PR body for
    the captured failure).
    """

    def _assert_allowed_pre_fix_blocked(self, command: str, session_id: str) -> None:
        result = hook.check(_bash(command, session_id))
        self.assertIsNone(
            result,
            f"wave-29 false positive not fixed: {command!r} still blocks: {result}",
        )

    def test_row1_gh_pr_comment_verdict_1153_nino(self):
        """07-28T00:11:52Z — gh pr comment 1153 --body-file verdict_1153_nino.md"""
        sid = str(uuid.uuid4())
        scratch = _scratchpad_dir(sid)
        body = f"{scratch}/verdict_1153_nino.md"
        _touch(body, age_seconds=180)
        self._assert_allowed_pre_fix_blocked(f"gh pr comment 1153 --body-file {body}", sid)

    def test_row2_gh_pr_create_sferreira_1131(self):
        """07-30T03:23:51Z — gh pr create (S.Ferreira/1131)"""
        sid = str(uuid.uuid4())
        scratch = _scratchpad_dir(sid)
        body = f"{scratch}/pr_body_1131.md"
        _touch(body, age_seconds=90)
        self._assert_allowed_pre_fix_blocked(f"gh pr create --title x --body-file {body}", sid)

    def test_row3_gh_pr_create_wmwangi_1140(self):
        """07-30T03:24:38Z — gh pr create (W.Mwangi/1140)"""
        sid = str(uuid.uuid4())
        scratch = _scratchpad_dir(sid)
        body = f"{scratch}/pr_body_1140.md"
        _touch(body, age_seconds=95)
        self._assert_allowed_pre_fix_blocked(f"gh pr create --title x --body-file {body}", sid)

    def test_row4_gh_pr_create_nhakim_1160(self):
        """07-30T03:30:59Z — gh pr create (N.Hakim/1160)"""
        sid = str(uuid.uuid4())
        scratch = _scratchpad_dir(sid)
        body = f"{scratch}/pr_body_1160.md"
        _touch(body, age_seconds=150)
        self._assert_allowed_pre_fix_blocked(f"gh pr create --title x --body-file {body}", sid)

    def test_row5_gh_pr_create_nkavtaradze_1149(self):
        """07-30T03:42:21Z — gh pr create (N.Kavtaradze/1149)"""
        sid = str(uuid.uuid4())
        scratch = _scratchpad_dir(sid)
        body = f"{scratch}/pr_body_1149.md"
        _touch(body, age_seconds=200)
        self._assert_allowed_pre_fix_blocked(f"gh pr create --title x --body-file {body}", sid)

    def test_row6_gh_pr_create_nkavtaradze_1204(self):
        """08-03T03:36:48Z — gh pr create (N.Kavtaradze/1204)"""
        sid = str(uuid.uuid4())
        scratch = _scratchpad_dir(sid)
        body = f"{scratch}/pr_body_1204.md"
        _touch(body, age_seconds=110)
        self._assert_allowed_pre_fix_blocked(f"gh pr create --title x --body-file {body}", sid)

    def test_row7_gh_pr_create_nkhoury_1180_first_attempt(self):
        """08-03T03:37:42Z — gh pr create (N.Khoury/1180), first attempt"""
        sid = str(uuid.uuid4())
        scratch = _scratchpad_dir(sid)
        body = f"{scratch}/pr_body_1180.md"
        _touch(body, age_seconds=60)
        self._assert_allowed_pre_fix_blocked(f"gh pr create --title x --body-file {body}", sid)

    # Row 8 (the touch-workaround retry of 1180) is its own dedicated test
    # class below — TouchWorkaroundOrderingDefectTests.

    def test_row9_gh_pr_create_avirtanen_1142(self):
        """08-03T03:50:59Z — gh pr create (A.Virtanen/1142)"""
        sid = str(uuid.uuid4())
        scratch = _scratchpad_dir(sid)
        body = f"{scratch}/pr_body_1142.md"
        _touch(body, age_seconds=125)
        self._assert_allowed_pre_fix_blocked(f"gh pr create --title x --body-file {body}", sid)

    def test_row10_gh_pr_create_wzielinska_1168(self):
        """08-03T17:25:59Z — gh pr create (W.Zielinska/1168)"""
        sid = str(uuid.uuid4())
        scratch = _scratchpad_dir(sid)
        body = f"{scratch}/pr_body_1168.md"
        _touch(body, age_seconds=140)
        self._assert_allowed_pre_fix_blocked(f"gh pr create --title x --body-file {body}", sid)

    def test_row11_gh_pr_create_avirtanen_1119(self):
        """08-03T18:27:57Z — gh pr create (A.Virtanen/1119)"""
        sid = str(uuid.uuid4())
        scratch = _scratchpad_dir(sid)
        body = f"{scratch}/pr_body_1119.md"
        _touch(body, age_seconds=300)
        self._assert_allowed_pre_fix_blocked(f"gh pr create --title x --body-file {body}", sid)


class TouchWorkaroundOrderingDefectTests(unittest.TestCase):
    """Row 8 — the touch-workaround from #1352, isolated as its own defect.

    08-03T03:37:46Z: N.Khoury's session retried `gh pr create` for #1180 as
    `touch <file> && gh pr create --title x --body-file <file>` after the
    first attempt (row 7 above) was blocked. It was STILL blocked. A
    PreToolUse hook stats the target file's mtime BEFORE the gated Bash
    command executes — the `touch` inside that same command has not run
    yet when the hook checks, so it cannot possibly refresh the mtime the
    hook sees. No amount of raising `STALE_TMP_THRESHOLD_SECONDS` fixes
    this: the file's mtime, AS THE HOOK SEES IT, never changes no matter
    how long the threshold is. Only recognizing that the path is under the
    invoking session's OWN scratchpad — independent of any mtime check at
    all — closes it.

    The mtime here is set to 2 hours, deliberately far beyond any
    plausible retuned threshold (the issue's own proposal #2 suggests
    10-15 minutes), to prove a threshold-only fix could not have closed
    this row even in principle.
    """

    def test_touch_workaround_defeated_by_pretooluse_ordering_still_needs_session_exemption(
        self,
    ):
        sid = str(uuid.uuid4())
        scratch = _scratchpad_dir(sid)
        body = f"{scratch}/pr_body_1180.md"
        _touch(body, age_seconds=2 * 3600)  # 2h — beyond any sane retuned threshold
        cmd = f"touch {body} && gh pr create --title x --body-file {body}"
        result = hook.check(_bash(cmd, sid))
        self.assertIsNone(
            result,
            "ordering defect not fixed: the touch-prefixed retry for the "
            f"agent's own session scratchpad file still blocks: {result}",
        )


class TruePositivePreservedTests(unittest.TestCase):
    """Acceptance criterion: exemption must NOT swallow genuine leftovers."""

    def test_different_session_scratchpad_stale_still_blocks(self):
        """A body file under a DIFFERENT session's scratchpad, stale, must
        still block — it is not (by construction) exempt just because it
        superficially looks like a scratchpad path."""
        my_session = str(uuid.uuid4())
        other_session = str(uuid.uuid4())
        scratch = _scratchpad_dir(other_session)
        body = f"{scratch}/leftover.md"
        _touch(body, age_seconds=3600)
        result = hook.check(_bash(f"gh pr create --title x --body-file {body}", my_session))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["decision"], "block")

    def test_bare_tmp_path_stale_still_blocks(self):
        """A bare /tmp/msg.txt (no session structure at all), stale, must
        still block — the true positive the hook exists for."""
        sid = str(uuid.uuid4())
        with tempfile.TemporaryDirectory(dir="/tmp") as td:
            msg = f"{td}/msg.txt"
            _touch(msg, age_seconds=120)
            result = hook.check(_bash(f"git commit -F {msg}", sid))
            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result["decision"], "block")


if __name__ == "__main__":
    unittest.main()
