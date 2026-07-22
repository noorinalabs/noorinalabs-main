"""Tests for premise_check — the /wave-scope premise-rot gate (main#837).

Covers the three layers the module is split into:

  1. Pure extraction/classification — ``looks_like_path``, ``normalize_path``,
     ``extract_path_candidates``: prose must NOT yield candidates (no false
     STOP), real paths and symbol-in-file refs must.
  2. Verdict logic with INJECTED checkers (zero git): MISSING -> STOP,
     UNVERIFIABLE -> WARN (env gap, never a STOP), all-present -> OK, and the
     #705/#816 regression cases.
  3. A real ``git`` integration test over a throwaway repo — proves
     ``git cat-file -e`` / ``git grep`` are invoked correctly against a ref,
     distinguishing a present path, a deleted path, and an unknown ref.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

# Helper lives at .claude/lib/premise_check.py; this test is at
# .claude/lib/tests/test_*.py. parent.parent reaches the lib root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import premise_check as pc  # noqa: E402


class LooksLikePathTest(unittest.TestCase):
    def test_accepts_slash_paths(self) -> None:
        self.assertTrue(pc.looks_like_path(".claude/lib/wave_seq.py"))
        self.assertTrue(pc.looks_like_path("ontology/repos/deploy.yaml"))
        self.assertTrue(pc.looks_like_path(".claude/lib/"))  # directory tree

    def test_accepts_bare_filename_with_known_ext(self) -> None:
        self.assertTrue(pc.looks_like_path("wave_key_reset.py"))
        self.assertTrue(pc.looks_like_path("CLAUDE.md"))

    def test_rejects_prose_and_non_paths(self) -> None:
        for tok in ("origin", "the", "wave-scope", "HEAD", "premise"):
            self.assertFalse(pc.looks_like_path(tok), tok)

    def test_rejects_bare_filename_unknown_ext(self) -> None:
        # No slash and an unknown extension -> not confidently a path.
        self.assertFalse(pc.looks_like_path("v1.2"))
        self.assertFalse(pc.looks_like_path("e.g"))

    def test_rejects_url_issue_ref_number(self) -> None:
        self.assertFalse(pc.looks_like_path("https://example.com/a/b.py"))
        self.assertFalse(pc.looks_like_path("#705"))
        self.assertFalse(pc.looks_like_path("42"))

    def test_rejects_whitespace(self) -> None:
        self.assertFalse(pc.looks_like_path("a b.py"))

    def test_rejects_slash_prose_main_1047(self) -> None:
        """main#1047: a slash alone is NOT a positive path signal.

        Every one of these is a verbatim false-positive token from the wave-26
        scope run (12/12 STOP, 0 genuine rot) — none has a code extension and
        none has a known repo-root leading component, so all must be rejected.
        """
        for tok in (
            "/",
            "A/B",
            "Latin/English",
            "benediction/Prophet-title",
            "ism/kunya",
            "token-count/matn-density",
            "recall/precision",
            "display/graph",
            "Identity/matching",
            "taṣliya/eulogy",
            "pollution/mc",
            "resolve/load",
            "collectors/commentators",
            "Validate/scrub",
            "boundary/particle",
            "name/nisba",
            "transliteration/cross-script",
            "Code/git",
        ):
            self.assertFalse(pc.looks_like_path(tok), tok)

    def test_rejects_numeric_fraction_main_1047(self) -> None:
        # "650,986/650,986 rows" -> the bare token "986/650" is a count, not a path.
        self.assertFalse(pc.looks_like_path("986/650"))
        self.assertFalse(pc.looks_like_path("650,986/650,986"))

    def test_rejects_git_ref_main_1047(self) -> None:
        # A git ref contains a slash but is never a path.
        self.assertFalse(pc.looks_like_path("origin/main"))
        self.assertFalse(pc.looks_like_path("refs/heads/main"))

    def test_accepts_known_root_component_without_extension(self) -> None:
        # A leading known-root directory is a positive signal even with no
        # recognized extension on the final component.
        self.assertTrue(pc.looks_like_path("src/parse"))
        self.assertTrue(pc.looks_like_path("noorinalabs-deploy/terraform/main"))

    def test_accepts_true_positive_paths_main_1047(self) -> None:
        # Every one of these genuinely resolved OK in the wave-26 run — the
        # fix must not regress real paths into false negatives.
        for tok in (
            "src/resolve/ner.py",
            "src/utils/arabic.py",
            "docs/testing-on-subsets.md",
            "data/curated/narrators_canonical.parquet",
        ):
            self.assertTrue(pc.looks_like_path(tok), tok)

    def test_mutation_guard_slash_alone_would_readmit_prose(self) -> None:
        """Pin the exact defect shape so a regression of the `"/" in tok`
        short-circuit (main#1047's root cause) is caught even if someone
        "simplifies" the extension/root-component branches back together.
        """
        prose_with_slash = "recall/precision"
        self.assertFalse(pc.looks_like_path(prose_with_slash))
        # The old (buggy) rule as a local re-implementation, for contrast only
        # — NOT calling into pc, just documenting what must NOT be true.
        old_buggy_rule = "/" in prose_with_slash
        self.assertTrue(old_buggy_rule)  # sanity: the token does contain "/"
        self.assertNotEqual(pc.looks_like_path(prose_with_slash), old_buggy_rule)


class NormalizePathTest(unittest.TestCase):
    def test_strips_backticks_and_trailing_punct(self) -> None:
        self.assertEqual(pc.normalize_path("`foo.py`,"), "foo.py")
        self.assertEqual(pc.normalize_path("foo.py."), "foo.py")

    def test_strips_leading_dot_slash(self) -> None:
        self.assertEqual(pc.normalize_path("./a/b.py"), "a/b.py")

    def test_strips_line_and_anchor_suffix(self) -> None:
        self.assertEqual(pc.normalize_path("a/b.py:42"), "a/b.py")
        self.assertEqual(pc.normalize_path("a/b.py:10-20"), "a/b.py")
        self.assertEqual(pc.normalize_path("a/b.py#L42"), "a/b.py")


class ExtractPathCandidatesTest(unittest.TestCase):
    def test_pulls_from_backticks_and_text(self) -> None:
        body = (
            "Two issues slipped: **#705** targeted the already-deleted "
            "`wave_key_reset.py` (removed by #804), and #816 referenced "
            "ontology/repos/deploy.yaml in passing."
        )
        got = pc.extract_path_candidates(body)
        self.assertIn("wave_key_reset.py", got)
        self.assertIn("ontology/repos/deploy.yaml", got)

    def test_prose_yields_nothing(self) -> None:
        body = "The premise no longer holds at origin HEAD; re-scope before kickoff."
        self.assertEqual(pc.extract_path_candidates(body), [])

    def test_dedup_and_order(self) -> None:
        body = "`a/b.py` then `a/b.py` again then `c/d.md`"
        self.assertEqual(pc.extract_path_candidates(body), ["a/b.py", "c/d.md"])

    def test_empty(self) -> None:
        self.assertEqual(pc.extract_path_candidates(""), [])

    def test_wave_26_regression_fixture_no_false_positives(self) -> None:
        """main#1047: pin all 12 wave-26 scope-run issue bodies as a fixture.

        Every body below produced a false STOP under the old `"/" in tok`
        rule. None of them should extract as path candidates now; the four
        genuine paths embedded alongside the prose must still extract.
        """
        bodies = [
            "Needs bidirectional A/B fixtures to compare recall/precision.",
            "Handle Latin/English transliteration mismatches in `src/resolve/ner.py`.",
            "The benediction/Prophet-title (taṣliya/eulogy) detector over-fires.",
            "Distinguish ism/kunya name-parts per `src/utils/arabic.py`.",
            "Tune token-count/matn-density thresholds; see `docs/testing-on-subsets.md`.",
            "Row counts read 650,986/650,986 after the backfill.",
            "Diff against origin/main before merging.",
            "display/graph parity check for the new collectors/commentators view.",
            "Identity/matching regression on the boundary/particle splitter.",
            "resolve/load ordering bug affects name/nisba resolution.",
            "Validate/scrub step needs a transliteration/cross-script pass.",
            "Code/git housekeeping only; touches `data/curated/narrators_canonical.parquet`.",
        ]
        real_paths = {
            "src/resolve/ner.py",
            "src/utils/arabic.py",
            "docs/testing-on-subsets.md",
            "data/curated/narrators_canonical.parquet",
        }
        false_positive_tokens = {
            "A/B",
            "recall/precision",
            "Latin/English",
            "benediction/Prophet-title",
            "taṣliya/eulogy",
            "ism/kunya",
            "token-count/matn-density",
            "986/650",
            "650,986/650,986",
            "origin/main",
            "display/graph",
            "collectors/commentators",
            "Identity/matching",
            "boundary/particle",
            "resolve/load",
            "name/nisba",
            "Validate/scrub",
            "transliteration/cross-script",
            "Code/git",
        }
        seen_real_paths: set[str] = set()
        for body in bodies:
            got = set(pc.extract_path_candidates(body))
            leaked = got & false_positive_tokens
            self.assertEqual(leaked, set(), f"false positive(s) in body: {body!r} -> {leaked}")
            seen_real_paths |= got & real_paths
        self.assertEqual(seen_real_paths, real_paths)

    def test_mutation_verify_old_rule_would_fail_this_fixture(self) -> None:
        """Restoring the old `"/" in tok` short-circuit must fail the wave-26
        fixture above — proves the regression test actually exercises the fix
        (main#1047 mutation-verification requirement).
        """

        def _old_looks_like_path(token: str) -> bool:
            tok = token.strip()
            if not tok or " " in tok or "\t" in tok:
                return False
            if "://" in tok:
                return False
            if not __import__("re").fullmatch(r"[\w./\-]+", tok):
                return False
            if tok.lstrip("#").isdigit():
                return False
            if "/" in tok:
                return True
            ext = tok.rsplit(".", 1)[-1].lower() if "." in tok else ""
            return ext in pc._CODE_EXTENSIONS

        self.assertTrue(_old_looks_like_path("recall/precision"))
        self.assertFalse(pc.looks_like_path("recall/precision"))


# --- verdict layer with injected (fake) checkers ----------------------------


def _checker(table: dict[str, str], default: str = pc.EXISTS):
    """A path/symbol checker that looks the value up in ``table``."""

    def _path(_repo_dir: str, _ref: str, value: str) -> str:
        return table.get(value, default)

    def _symbol(_repo_dir: str, _ref: str, value: str, _pathspec: str | None = None) -> str:
        return table.get(value, default)

    return _path, _symbol


class CheckIssueVerdictTest(unittest.TestCase):
    def _check(self, issue: dict, table: dict[str, str], default: str = pc.EXISTS):
        path_fn, sym_fn = _checker(table, default)
        return pc.check_issue(issue, Path("/repos"), "origin/main", path_fn, sym_fn)

    def test_705_deleted_file_is_stop(self) -> None:
        # The #705 regression: names a file that was deleted at HEAD.
        issue = {"ref": "main#705", "body": "targets `wave_key_reset.py`"}
        res = self._check(issue, {"wave_key_reset.py": pc.MISSING})
        self.assertEqual(res.verdict, pc.STOP)
        self.assertEqual([c.value for c in res.missing], ["wave_key_reset.py"])

    def test_present_file_is_ok(self) -> None:
        issue = {"ref": "main#999", "body": "touches `.claude/lib/wave_seq.py`"}
        res = self._check(issue, {".claude/lib/wave_seq.py": pc.EXISTS})
        self.assertEqual(res.verdict, pc.OK)

    def test_unverifiable_is_warn_not_stop(self) -> None:
        # Env gap (repo not cloned / ref not fetched) must never read as rot.
        issue = {"ref": "deploy#1", "repo": "noorinalabs-deploy", "body": "`infra/main.tf`"}
        res = self._check(issue, {"infra/main.tf": pc.UNVERIFIABLE})
        self.assertEqual(res.verdict, pc.WARN)
        self.assertEqual(len(res.unverifiable), 1)

    def test_missing_dominates_unverifiable(self) -> None:
        issue = {"ref": "main#42", "body": "`gone.py` and `maybe.py`"}
        res = self._check(issue, {"gone.py": pc.MISSING, "maybe.py": pc.UNVERIFIABLE})
        self.assertEqual(res.verdict, pc.STOP)

    def test_no_candidates_is_ok(self) -> None:
        issue = {"ref": "main#7", "body": "purely process; nothing concrete named"}
        res = self._check(issue, {})
        self.assertEqual(res.verdict, pc.OK)
        self.assertEqual(res.candidates, [])

    def test_explicit_symbol_missing_is_stop(self) -> None:
        # The #816-shaped case: a named symbol no longer present at HEAD.
        issue = {
            "ref": "main#816",
            "body": "root cause in the cspell map",
            "symbols": [{"name": "build_cspell_map", "pathspec": ".claude/lib/"}],
        }
        res = self._check(issue, {"build_cspell_map": pc.MISSING})
        self.assertEqual(res.verdict, pc.STOP)
        self.assertEqual(res.candidates[0].kind, "symbol")
        self.assertEqual(res.candidates[0].pathspec, ".claude/lib/")

    def test_explicit_paths_merged_with_body(self) -> None:
        issue = {
            "ref": "main#5",
            "body": "see `a.py`",
            "paths": ["b/c.py"],
        }
        res = self._check(issue, {"a.py": pc.EXISTS, "b/c.py": pc.EXISTS})
        self.assertEqual({c.value for c in res.candidates}, {"a.py", "b/c.py"})

    def test_cross_repo_resolution_is_warn_not_stop(self) -> None:
        """main#1047 da#427: a `.claude/`-rooted path that MISSES in the child
        repo but EXISTS in the parent downgrades to CROSS_REPO -> WARN.
        """
        target = ".claude/memory/feedback_drop_gate_bidirectional_ab.md"
        issue = {
            "ref": "da#427",
            "repo": "noorinalabs-data-acquisition",
            "body": f"see `{target}`",
        }

        def _path(repo_dir: str, _ref: str, value: str) -> str:
            # MISSING in the child repo dir, EXISTS at the parent (repos_root).
            return pc.EXISTS if repo_dir == "/repos" else pc.MISSING

        res = pc.check_issue(issue, Path("/repos"), "origin/main", _path, _checker({})[1])
        self.assertEqual(res.verdict, pc.WARN)
        self.assertEqual(res.candidates[0].status, pc.CROSS_REPO)
        self.assertIsNotNone(res.candidates[0].note)

    def test_non_claude_missing_in_child_repo_is_still_stop(self) -> None:
        # Only `.claude/`-rooted paths get the cross-repo second chance.
        issue = {
            "ref": "da#1",
            "repo": "noorinalabs-data-acquisition",
            "body": "see `src/parse/composition.py`",
        }
        res = self._check(issue, {"src/parse/composition.py": pc.MISSING})
        self.assertEqual(res.verdict, pc.STOP)


class ResolveRepoDirTest(unittest.TestCase):
    def test_main_maps_to_root(self) -> None:
        self.assertEqual(pc.resolve_repo_dir({"repo": "noorinalabs-main"}, Path("/r")), "/r")

    def test_child_maps_under_root(self) -> None:
        self.assertEqual(
            pc.resolve_repo_dir({"repo": "noorinalabs-deploy"}, Path("/r")),
            "/r/noorinalabs-deploy",
        )

    def test_explicit_repo_dir_wins(self) -> None:
        self.assertEqual(
            pc.resolve_repo_dir({"repo": "x", "repo_dir": "/custom"}, Path("/r")),
            "/custom",
        )


class CliTest(unittest.TestCase):
    def _run(self, issues: list[dict], extra: list[str] | None = None) -> tuple[int, str]:
        with TemporaryDirectory() as d:
            p = Path(d) / "issues.json"
            p.write_text(json.dumps(issues))
            buf = io.StringIO()
            with redirect_stdout(buf):
                # No real repo at /repos -> all candidates UNVERIFIABLE -> WARN,
                # so exit 0 (a STOP requires a readable ref that lacks the path).
                rc = pc.main(
                    ["check", "--issues", str(p), "--repos-root", "/nonexistent", *(extra or [])]
                )
            return rc, buf.getvalue()

    def test_warn_only_exits_zero_even_with_stop(self) -> None:
        # Force a STOP via a real temp repo would be heavier; instead assert the
        # --warn-only flag downgrades. Use a repo dir that resolves so the path
        # check returns MISSING is not possible without git, so we rely on the
        # integration test for STOP exit. Here just confirm WARN -> rc 0.
        rc, out = self._run([{"ref": "main#1", "body": "`x/y.py`"}])
        self.assertEqual(rc, 0)
        self.assertIn("WARN", out)

    def test_json_output_is_parseable(self) -> None:
        rc, out = self._run([{"ref": "main#1", "body": "`x/y.py`"}], extra=["--json"])
        self.assertEqual(rc, 0)
        parsed = json.loads(out)
        self.assertEqual(parsed[0]["ref"], "main#1")
        self.assertEqual(parsed[0]["verdict"], pc.WARN)


class GitIntegrationTest(unittest.TestCase):
    """Real git over a throwaway repo — the only test that shells out."""

    def _git(self, repo: Path, *args: str) -> None:
        subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True,
            capture_output=True,
            text=True,
        )

    def _make_repo(self, root: Path) -> Path:
        # The org root *is* noorinalabs-main, so resolve_repo_dir maps that repo
        # name to repos_root itself — init the repo directly at root.
        repo = root
        self._git(repo, "init", "-q")
        self._git(repo, "config", "user.email", "t@t")
        self._git(repo, "config", "user.name", "t")
        (repo / "kept.py").write_text("def kept_symbol():\n    return 1\n")
        (repo / "doomed.py").write_text("x = 1\n")
        self._git(repo, "add", "-A")
        self._git(repo, "commit", "-q", "-m", "base")
        # Delete doomed.py in a second commit -> absent at HEAD.
        (repo / "doomed.py").unlink()
        self._git(repo, "add", "-A")
        self._git(repo, "commit", "-q", "-m", "remove doomed")
        return repo

    def test_present_deleted_and_symbol(self) -> None:
        with TemporaryDirectory() as d:
            root = Path(d)
            self._make_repo(root)
            ref = "HEAD"

            issue = {
                "ref": "main#705",
                "repo": "noorinalabs-main",
                "body": "needs `kept.py` and `doomed.py`",
                "symbols": [
                    {"name": "kept_symbol"},
                    {"name": "vanished_symbol"},
                ],
            }
            res = pc.check_issue(issue, root, ref)

            statuses = {(c.kind, c.value): c.status for c in res.candidates}
            self.assertEqual(statuses[("path", "kept.py")], pc.EXISTS)
            self.assertEqual(statuses[("path", "doomed.py")], pc.MISSING)
            self.assertEqual(statuses[("symbol", "kept_symbol")], pc.EXISTS)
            self.assertEqual(statuses[("symbol", "vanished_symbol")], pc.MISSING)
            self.assertEqual(res.verdict, pc.STOP)

    def test_basename_fallback_resolves_nested_file(self) -> None:
        """main#1047 da#373: a bare filename named `composition.py` that lives
        at `src/parse/composition.py` must resolve OK, not MISSING.
        """
        with TemporaryDirectory() as d:
            root = Path(d)
            self._git(root, "init", "-q")
            self._git(root, "config", "user.email", "t@t")
            self._git(root, "config", "user.name", "t")
            nested = root / "src" / "parse"
            nested.mkdir(parents=True)
            (nested / "composition.py").write_text("x = 1\n")
            self._git(root, "add", "-A")
            self._git(root, "commit", "-q", "-m", "base")

            issue = {
                "ref": "da#373",
                "repo": "noorinalabs-main",
                "body": "fix a bug in `composition.py`",
            }
            res = pc.check_issue(issue, root, "HEAD")
            statuses = {c.value: c.status for c in res.candidates}
            self.assertEqual(statuses["composition.py"], pc.EXISTS)
            self.assertEqual(res.verdict, pc.OK)

    def test_basename_fallback_does_not_resurrect_a_real_deletion(self) -> None:
        # A genuinely deleted slash-free file must still STOP — the basename
        # fallback only helps when the name resolves SOMEWHERE in the tree.
        with TemporaryDirectory() as d:
            root = Path(d)
            self._make_repo(root)
            issue = {"ref": "main#705", "repo": "noorinalabs-main", "body": "`doomed.py`"}
            res = pc.check_issue(issue, root, "HEAD")
            self.assertEqual(res.candidates[0].status, pc.MISSING)
            self.assertEqual(res.verdict, pc.STOP)

    def test_unknown_ref_is_unverifiable(self) -> None:
        with TemporaryDirectory() as d:
            root = Path(d)
            self._make_repo(root)
            issue = {"ref": "main#1", "repo": "noorinalabs-main", "body": "`kept.py`"}
            res = pc.check_issue(issue, root, "origin/does-not-exist")
            self.assertEqual(res.verdict, pc.WARN)
            self.assertEqual(res.candidates[0].status, pc.UNVERIFIABLE)

    def test_cli_stop_exit_code_over_real_repo(self) -> None:
        with TemporaryDirectory() as d:
            root = Path(d)
            self._make_repo(root)
            issues = [{"ref": "main#705", "repo": "noorinalabs-main", "body": "`doomed.py`"}]
            p = root / "issues.json"
            p.write_text(json.dumps(issues))
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = pc.main(
                    ["check", "--issues", str(p), "--repos-root", str(root), "--ref", "HEAD"]
                )
            self.assertEqual(rc, 1)
            self.assertIn("STOP", buf.getvalue())

            # --warn-only downgrades the same input to exit 0.
            buf2 = io.StringIO()
            with redirect_stdout(buf2):
                rc2 = pc.main(
                    [
                        "check",
                        "--issues",
                        str(p),
                        "--repos-root",
                        str(root),
                        "--ref",
                        "HEAD",
                        "--warn-only",
                    ]
                )
            self.assertEqual(rc2, 0)


if __name__ == "__main__":
    unittest.main()
