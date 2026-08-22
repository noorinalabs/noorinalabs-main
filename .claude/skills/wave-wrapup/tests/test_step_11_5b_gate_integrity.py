#!/usr/bin/env python3
"""Tests for /wave-wrapup Step 11.5b's bash wrapper (main#1477, review of #1478).

The Python classifier (`.claude/lib/gate_integrity.py`) is covered by
`.claude/lib/tests/test_gate_integrity.py`. THIS module covers the shell block
that drives it, because the merge-gate review of PR #1478 found three paths
through that wrapper which exit 0 **and persist**
`wave_{M}_gate_integrity = "verified"` over an audit that examined nothing:

  1. `wave_{M}_repos_in_scope` absent — `jq` fails, the variable is empty, the
     `while` loop body never runs, zero repos are audited.
  2. `wave_{M}_repos_in_scope` is `[]` — identical, and indistinguishable.
  3. the audit binary exits outside {0,1,2} — the `case` had no `*)` arm, so a
     killed/crashed run silently counted as clean (reproduced with exit 137).

Each is the exact fail-open shape this whole gate exists to detect, sitting in
the gate's own entry point — and unlike Step 11.5a, 11.5b PERSISTS its verdict
and `/wave-retro`'s carry-forward reads it back, so a false clean outlives the
run.

These tests run the block **as it is written in SKILL.md** — extracted from the
file, not paraphrased into a Python mirror — against a sandbox status file and a
stub audit binary whose exit code the test chooses. A mirror would let SKILL.md
drift away from the thing under test, which is how a gate becomes decorative.

Run:
    cd .claude/skills/wave-wrapup && ENVIRONMENT=test python3 -m pytest tests/ -q
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SKILL = _HERE.parent / "SKILL.md"
# .claude/skills/wave-wrapup/tests -> .claude
_CLAUDE_ROOT = _HERE.parent.parent.parent
_REAL_UPSERT = _CLAUDE_ROOT / "lib" / "upsert_status_keys.py"

_WAVE = "30"
_SINCE = "2026-08-10T23:47:54Z"

_SHELL = shutil.which("zsh") or shutil.which("bash")

#: A stub standing in for `.claude/lib/gate_integrity.py`. The real audit is
#: unit-tested elsewhere; what these tests need is deterministic control of the
#: EXIT CODE the wrapper has to interpret, including codes the wrapper was never
#: written to expect.
_STUB_AUDIT = """#!/usr/bin/env python3
import os, sys

sys.stdout.write("stub audit: " + " ".join(sys.argv[1:]) + "\\n")
with open(os.environ["STUB_CALL_LOG"], "a", encoding="utf-8") as fh:
    fh.write(" ".join(sys.argv[1:]) + "\\n")
raise SystemExit(int(os.environ.get("STUB_EXIT", "0")))
"""


def extract_step_11_5b_block() -> str:
    """Return the FIRST bash block of SKILL.md § 11.5b, verbatim.

    Anchored on the section headings rather than a line number so an edit
    elsewhere in the skill cannot silently retarget these tests at the wrong
    block — they raise here instead of quietly passing over § 11.6.
    """
    text = _SKILL.read_text(encoding="utf-8")
    start = text.index("### 11.5b.")
    end = text.index("### 11.6.", start)
    blocks = re.findall(r"```bash\n(.*?)```", text[start:end], re.S)
    if not blocks:
        raise AssertionError("no bash block found in /wave-wrapup section 11.5b")
    return blocks[0]


class _WrapperHarness(unittest.TestCase):
    """Runs the extracted block against a throwaway repo-shaped sandbox."""

    def _sandbox(self, status: dict) -> Path:
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        # The block's preflight requires the root's basename to be the parent
        # repo's name (child-roster resolution is path-relative to it), so the
        # sandbox has to be shaped like a real checkout.
        root = tmp / "noorinalabs-main"
        (root / ".claude" / "lib").mkdir(parents=True)
        (root / "cross-repo-status.json").write_text(json.dumps(status, indent=1))
        # The REAL upsert helper — persistence is exercised, not faked, since
        # "did it write `verified`?" is the assertion that matters most here.
        shutil.copy2(_REAL_UPSERT, root / ".claude" / "lib" / "upsert_status_keys.py")
        (root / ".claude" / "lib" / "gate_integrity.py").write_text(_STUB_AUDIT)
        return root

    def _run(self, status: dict, *, stub_exit: int = 0, override: str | None = None):
        root = self._sandbox(status)
        block = extract_step_11_5b_block().replace("{M}", _WAVE)
        block = block.replace('REPO_ROOT="$(git rev-parse --show-toplevel)"', f'REPO_ROOT="{root}"')
        script = root.parent / "step.sh"
        script.write_text(block)

        call_log = root.parent / "calls.txt"
        call_log.write_text("")
        env = {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": str(root.parent),
            "STUB_EXIT": str(stub_exit),
            "STUB_CALL_LOG": str(call_log),
        }
        if override is not None:
            env["GATE_INTEGRITY_OVERRIDE_RATIONALE"] = override

        # Narrowed for mypy: every test class carries `skipIf(_SHELL is None)`,
        # which the type checker cannot see.
        shell = _SHELL
        assert shell is not None
        proc = subprocess.run([shell, str(script)], capture_output=True, text=True, env=env)
        persisted = json.loads((root / "cross-repo-status.json").read_text())
        return proc, persisted, call_log.read_text().splitlines()

    def assertNotFalselyClean(self, proc, persisted, audited):
        """The composite property every fail-open case must violate.

        Split out because "exit 0" alone understates the defect: the wrapper
        also WRITES its verdict, and `/wave-retro`'s carry-forward reads that key
        back and reports it as a measured result. A run that examined zero repos
        must fail BOTH halves — it must not exit 0, and it must not leave a
        `verified` claim behind for the retro to narrate.
        """
        self.assertNotEqual(
            proc.returncode,
            0,
            f"wrapper exited 0 over an audit that examined {len(audited)} repo(s).\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
        )
        self.assertNotEqual(
            persisted.get(f"wave_{_WAVE}_gate_integrity"),
            "verified",
            "wrapper persisted a `verified` claim that /wave-retro will read back "
            "as a measured clean result",
        )


@unittest.skipIf(_SHELL is None, "no shell available")
class ZeroRepoAuditTests(_WrapperHarness):
    """An audit that examined zero repos must be impossible to render clean."""

    def test_absent_repos_in_scope_blocks(self):
        """Case 1 — the key is missing entirely.

        Of the wave keys in `cross-repo-status.json` today, thirteen waves carry
        `repos_in_scope` and only five carry `started_at`, so this is the MORE
        fallible of the two — and the sibling key was already guarded two lines
        above, which makes this an omission rather than a decision.
        """
        proc, persisted, audited = self._run({f"wave_{_WAVE}_started_at": _SINCE})
        self.assertNotFalselyClean(proc, persisted, audited)
        self.assertEqual(audited, [], "no repo should have been audited")
        self.assertIn("repos_in_scope", proc.stdout)

    def test_empty_repos_in_scope_blocks(self):
        """Case 2 — the key is present but `[]`.

        Indistinguishable from case 1 at the shell level (both leave the
        variable empty), and it must not be distinguishable in outcome either.
        """
        proc, persisted, audited = self._run(
            {f"wave_{_WAVE}_started_at": _SINCE, f"wave_{_WAVE}_repos_in_scope": []}
        )
        self.assertNotFalselyClean(proc, persisted, audited)
        self.assertEqual(audited, [])

    def test_all_blank_repo_entries_block(self):
        """Belt-and-braces: a list that is non-empty but yields no audited repo.

        The pre-check alone passes this (the variable is non-empty); only a
        POSITIVE assertion on how many repos were actually audited catches it.
        """
        proc, persisted, audited = self._run(
            {
                f"wave_{_WAVE}_started_at": _SINCE,
                f"wave_{_WAVE}_repos_in_scope": ["", "  "],
            }
        )
        self.assertNotFalselyClean(proc, persisted, audited)


@unittest.skipIf(_SHELL is None, "no shell available")
class UnexpectedExitStatusTests(_WrapperHarness):
    """Case 3 — an exit code outside {0,1,2} is not a verdict."""

    def _scope(self):
        return {
            f"wave_{_WAVE}_started_at": _SINCE,
            f"wave_{_WAVE}_repos_in_scope": ["noorinalabs-main"],
        }

    def test_sigkill_status_137_blocks(self):
        proc, persisted, audited = self._run(self._scope(), stub_exit=137)
        self.assertNotFalselyClean(proc, persisted, audited)
        self.assertEqual(len(audited), 1, "the audit should still have been invoked")
        self.assertIn("137", proc.stdout)

    def test_unexpected_status_has_its_own_diagnostic(self):
        """Not folded into the exit-2 wording.

        "UNDETERMINED (gh/API error)" sends an operator to check `gh auth
        status`; a killed process is a different problem with a different fix,
        and a gate that misnames the cause wastes the reader's time (#981).
        """
        proc, _persisted, _audited = self._run(self._scope(), stub_exit=137)
        self.assertIn("UNEXPECTED", proc.stdout)
        self.assertNotIn("gh/API error", proc.stdout)

    def test_status_3_blocks(self):
        """Any code outside the documented set, not just signal-shaped ones."""
        proc, persisted, audited = self._run(self._scope(), stub_exit=3)
        self.assertNotFalselyClean(proc, persisted, audited)


@unittest.skipIf(_SHELL is None, "no shell available")
class DocumentedExitCodeTests(_WrapperHarness):
    """Positive controls — the guards above must not break the real paths.

    Without these, every assertion in this module could be satisfied by a
    wrapper that blocks unconditionally, which is not a gate either.
    """

    def _scope(self, repos):
        return {
            f"wave_{_WAVE}_started_at": _SINCE,
            f"wave_{_WAVE}_repos_in_scope": repos,
        }

    def test_clean_audit_exits_zero_and_persists_verified(self):
        proc, persisted, audited = self._run(self._scope(["noorinalabs-main"]), stub_exit=0)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(persisted[f"wave_{_WAVE}_gate_integrity"], "verified")
        self.assertEqual(persisted[f"wave_{_WAVE}_gate_integrity_window"], _SINCE)
        self.assertEqual(len(audited), 1)

    def test_every_in_scope_repo_is_audited(self):
        repos = ["noorinalabs-main", "noorinalabs-deploy", "noorinalabs-isnad-graph"]
        proc, _persisted, audited = self._run(self._scope(repos), stub_exit=0)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(len(audited), len(repos))
        for repo in repos:
            self.assertTrue(
                any(f"noorinalabs/{repo}" in call for call in audited),
                f"{repo} was in scope but never audited",
            )

    def test_unreviewed_merge_blocks_and_persists_nothing(self):
        proc, persisted, _audited = self._run(self._scope(["noorinalabs-main"]), stub_exit=1)
        self.assertEqual(proc.returncode, 1)
        self.assertNotIn(f"wave_{_WAVE}_gate_integrity", persisted)

    def test_undetermined_blocks_and_persists_nothing(self):
        proc, persisted, _audited = self._run(self._scope(["noorinalabs-main"]), stub_exit=2)
        self.assertEqual(proc.returncode, 1)
        self.assertNotIn(f"wave_{_WAVE}_gate_integrity", persisted)
        self.assertIn("UNDETERMINED", proc.stdout)

    def test_override_records_the_rationale(self):
        proc, persisted, _audited = self._run(
            self._scope(["noorinalabs-main"]),
            stub_exit=1,
            override="dependabot auto-merge; policy question open on #1476",
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(persisted[f"wave_{_WAVE}_gate_integrity"], "overridden")
        self.assertIn("#1476", persisted[f"wave_{_WAVE}_gate_integrity_override_rationale"])

    def test_override_does_not_rescue_a_zero_repo_audit(self):
        """The override acknowledges a FINDING, not a missing measurement.

        An operator who has an override exported for an unrelated reason must
        not thereby convert "nothing was audited" into a closed wave.
        """
        proc, persisted, audited = self._run(
            {f"wave_{_WAVE}_started_at": _SINCE, f"wave_{_WAVE}_repos_in_scope": []},
            override="unrelated acknowledgement carried over from an earlier run",
        )
        self.assertNotFalselyClean(proc, persisted, audited)

    def test_missing_started_at_still_blocks(self):
        """The pre-existing sibling guard must survive the new one."""
        proc, persisted, _audited = self._run(
            {f"wave_{_WAVE}_repos_in_scope": ["noorinalabs-main"]}
        )
        self.assertEqual(proc.returncode, 1)
        self.assertIn("started_at", proc.stdout)
        self.assertNotIn(f"wave_{_WAVE}_gate_integrity", persisted)


if __name__ == "__main__":
    unittest.main()
