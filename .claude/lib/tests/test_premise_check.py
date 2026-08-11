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


class Main1138LooksLikePathTest(unittest.TestCase):
    """main#1138: the false-positive classes the wave-30 scope run hit.

    Pure ``looks_like_path`` classification — no git involved.
    """

    def test_rejects_bare_extension_token(self) -> None:
        # main#1138 class 3: a bare extension mentioned in prose (main#1112
        # flagged a bare `.py`, main#1118 a bare `.yaml`) has no filename stem
        # before the dot and must not parse as a path.
        self.assertFalse(pc.looks_like_path(".py"))
        self.assertFalse(pc.looks_like_path(".yaml"))
        self.assertFalse(pc.looks_like_path(".md"))
        # A real dotfile-style stem (non-empty content before the final dot)
        # must still be accepted.
        self.assertTrue(pc.looks_like_path("wave_key_reset.py"))
        self.assertTrue(pc.looks_like_path(".pre-commit-config.yaml"))

    def test_rejects_absolute_tmp_scratchpad_path(self) -> None:
        # main#1138 wave-30 class: an ephemeral, session-scoped scratchpad
        # path quoted verbatim in an issue body (the shape wave-29's own
        # `block_stale_tmp_message_file` false-positive writeup used) is not
        # a repo-relative path and must never resolve against git HEAD.
        self.assertFalse(
            pc.looks_like_path(
                "/tmp/claude-1000/-home-parameterization-code-noorinalabs-main/"
                "abc123/scratchpad/verdict_probe.md"
            )
        )
        self.assertFalse(pc.looks_like_path("/tmp/foo.py"))
        self.assertFalse(pc.looks_like_path("/var/log/out.txt"))

    def test_rejects_deliberate_example_filenames(self) -> None:
        # main#1138 wave-30 class: a doc-placeholder filename used purely for
        # illustration (`X.md` is the exact placeholder wave-30's own #1352
        # used for "insert your body-file path here"; `foo.py`/`example.py`
        # are the generic org-wide convention) must not assert existence.
        self.assertFalse(pc.looks_like_path("X.md"))
        self.assertFalse(pc.looks_like_path("Y.py"))
        self.assertFalse(pc.looks_like_path("foo.py"))
        self.assertFalse(pc.looks_like_path("example.py"))
        # A real, non-placeholder short name must still be accepted.
        self.assertTrue(pc.looks_like_path("gh.py"))


class Main1138VerdictLayerTest(unittest.TestCase):
    """main#1138: verdict-layer fixes exercised with injected (fake) checkers."""

    def test_cross_repo_symmetric_parent_misses_child_resolves(self) -> None:
        """main#1138 class 1 (a.k.a. wave-30 "child-repo workflow paths").

        A `noorinalabs-main` issue names a `.github/workflows/` file that is
        MISSING in the parent but resolves in a child repo — the reverse of
        the existing child-misses/parent-resolves rule (main#1047 da#427).
        Must downgrade to CROSS_REPO -> WARN, not STOP.
        """
        target = ".github/workflows/ghcr-publish.yml"
        issue = {"ref": "main#1110", "repo": "noorinalabs-main", "body": f"see `{target}`"}

        def _path(repo_dir: str, _ref: str, _value: str) -> str:
            # MISSING at the parent (repos_root itself); EXISTS under any
            # child-repo subdirectory.
            return pc.MISSING if repo_dir == "/repos" else pc.EXISTS

        res = pc.check_issue(issue, Path("/repos"), "origin/main", _path, _checker({})[1])
        self.assertEqual(res.verdict, pc.WARN)
        self.assertEqual(res.candidates[0].status, pc.CROSS_REPO)
        self.assertIsNotNone(res.candidates[0].note)

    def test_cross_repo_bare_filename_main_1110_literal_token(self) -> None:
        """main#1138 MF1 (merge-gate follow-up, Aino Virtanen): class 1's own
        reported instances — main#1110 and main#1111 — name the workflow file
        by BARE filename (``ghcr-publish.yml``), never the qualified
        ``.github/workflows/...`` path. The class-1 fixture above used the
        qualified form, which the shared-prefix trigger already caught; the
        literal #1110 token did not move. This pins the literal token.
        """
        issue = {
            "ref": "main#1110",
            "repo": "noorinalabs-main",
            "body": "**C3 — `ghcr-publish.yml` -> reusable build/push/dispatch**",
        }

        def _path(repo_dir: str, _ref: str, _value: str) -> str:
            return pc.MISSING if repo_dir == "/repos" else pc.EXISTS

        res = pc.check_issue(issue, Path("/repos"), "origin/main", _path, _checker({})[1])
        self.assertEqual(res.verdict, pc.WARN)
        self.assertEqual(res.candidates[0].value, "ghcr-publish.yml")
        self.assertEqual(res.candidates[0].status, pc.CROSS_REPO)

    def test_cross_repo_bare_filename_not_found_anywhere_still_stops(self) -> None:
        # Recall guard: a bare filename that is genuinely absent from the
        # parent AND every child must still STOP — the MF1 widening is a
        # second chance, not a blanket bare-filename pass.
        issue = {
            "ref": "main#705",
            "repo": "noorinalabs-main",
            "body": "targets `wave_key_reset.py`",
        }
        res = self._check(issue, {"wave_key_reset.py": pc.MISSING})
        self.assertEqual(res.verdict, pc.STOP)

    def test_cross_repo_bare_filename_not_widened_on_child_to_parent_side(self) -> None:
        # The MF1 widening is deliberately ONE-DIRECTIONAL (parent->child
        # only): a child-repo issue naming a bare filename that happens to
        # exist somewhere in the parent tree must still STOP, not downgrade
        # — only a shared-root-prefixed path gets the child->parent second
        # chance (main#1047 da#427's original, narrower rule).
        issue = {
            "ref": "da#1",
            "repo": "noorinalabs-data-acquisition",
            "body": "see `composition.py`",
        }

        def _path(repo_dir: str, _ref: str, _value: str) -> str:
            # MISSING in the child; EXISTS at the parent (repos_root) — but
            # bare, not shared-prefixed, so must NOT downgrade.
            return pc.EXISTS if repo_dir == "/repos" else pc.MISSING

        res = pc.check_issue(issue, Path("/repos"), "origin/main", _path, _checker({})[1])
        self.assertEqual(res.verdict, pc.STOP)

    def test_creates_array_prevents_stop_on_proposed_file(self) -> None:
        """main#1138 class 2: an issue that PROPOSES a file (its own output)
        must not premise-rot-STOP on that file being absent today.

        main#1118 (G6) named `.claude/lib/org_repos.py` as the artifact it
        would create; the gate read that as a rotted premise. An explicit
        ``creates`` array marks the path as a declared creation: never
        checked against git, never contributes to the verdict.
        """
        issue = {
            "ref": "main#1118",
            "repo": "noorinalabs-main",
            "body": "extract the org repo list into `.claude/lib/org_repos.py`",
            "creates": [".claude/lib/org_repos.py"],
        }
        # Checker would report MISSING if it were ever consulted for this
        # path — proves the fix routes around the checker entirely, not that
        # the checker happens to return a passing status.
        res = self._check(issue, {".claude/lib/org_repos.py": pc.MISSING})
        self.assertEqual(res.verdict, pc.OK)
        self.assertEqual(res.candidates[0].status, pc.CREATES)

    def test_creates_does_not_suppress_other_missing_paths(self) -> None:
        # A `creates` entry only exempts the declared path(s); an unrelated
        # named path that is genuinely missing must still STOP.
        issue = {
            "ref": "main#1118",
            "repo": "noorinalabs-main",
            "body": "extract into `.claude/lib/org_repos.py`, touches `gone.py`",
            "creates": [".claude/lib/org_repos.py"],
        }
        res = self._check(issue, {".claude/lib/org_repos.py": pc.MISSING, "gone.py": pc.MISSING})
        self.assertEqual(res.verdict, pc.STOP)
        self.assertEqual([c.value for c in res.missing], ["gone.py"])

    def _check(self, issue: dict, table: dict[str, str], default: str = pc.EXISTS):
        path_fn, sym_fn = _checker(table, default)
        return pc.check_issue(issue, Path("/repos"), "origin/main", path_fn, sym_fn)


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

    def test_gitignored_path_is_warn_not_stop(self) -> None:
        """main#1138 wave-30 class: a legitimately gitignored path (e.g.
        `.claude/annunaki/errors.jsonl`) can never be found by
        `git cat-file`, since it is by design never tracked — that must not
        read as premise rot. Downgrades to WARN, not STOP.
        """
        with TemporaryDirectory() as d:
            root = Path(d)
            self._git(root, "init", "-q")
            self._git(root, "config", "user.email", "t@t")
            self._git(root, "config", "user.name", "t")
            (root / ".gitignore").write_text("annunaki/errors.jsonl\n")
            self._git(root, "add", "-A")
            self._git(root, "commit", "-q", "-m", "base")
            (root / "annunaki").mkdir()
            (root / "annunaki" / "errors.jsonl").write_text("{}\n")

            issue = {
                "ref": "main#1138",
                "repo": "noorinalabs-main",
                "body": "see `annunaki/errors.jsonl`",
            }
            res = pc.check_issue(issue, root, "HEAD")
            self.assertEqual(res.candidates[0].status, pc.GITIGNORED)
            self.assertEqual(res.verdict, pc.WARN)

    def test_relative_fragment_suffix_resolves_under_claude(self) -> None:
        """main#1138 4th FP class (not in the issue body): a slash-containing
        relative fragment (`lib/check_agent_liveness.py`) whose basename
        fallback never fires because the token is not slash-free, even
        though the file exists at `.claude/lib/check_agent_liveness.py`.
        """
        with TemporaryDirectory() as d:
            root = Path(d)
            self._git(root, "init", "-q")
            self._git(root, "config", "user.email", "t@t")
            self._git(root, "config", "user.name", "t")
            nested = root / ".claude" / "lib"
            nested.mkdir(parents=True)
            (nested / "check_agent_liveness.py").write_text("x = 1\n")
            self._git(root, "add", "-A")
            self._git(root, "commit", "-q", "-m", "base")

            issue = {
                "ref": "main#1138",
                "repo": "noorinalabs-main",
                "body": "the liveness check lives at `lib/check_agent_liveness.py`",
            }
            res = pc.check_issue(issue, root, "HEAD")
            statuses = {c.value: c.status for c in res.candidates}
            self.assertEqual(statuses["lib/check_agent_liveness.py"], pc.EXISTS)
            self.assertEqual(res.verdict, pc.OK)

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
