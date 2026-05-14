"""Unit tests for apply_branch_protection.

These tests exercise the unit-mechanic correctness — manifest validation,
desired-state assembly, GET-normalisation, diff computation, mode dispatch —
without making real GitHub API calls. Run with `python -m pytest` from this
directory.

The actual `gh api PUT` calls against the 7 real org repos can ONLY be
verified by post-merge runtime acceptance. See the issue thread for the test
plan applied after merge.
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
import apply_branch_protection as abp  # noqa: E402


def _minimal_manifest() -> dict:
    return {
        "_common": {
            "enforce_admins": False,
            "required_pull_request_reviews": None,
            "restrictions": None,
            "allow_force_pushes": False,
            "allow_deletions": False,
            "required_linear_history": False,
            "required_conversation_resolution": False,
        },
        "repos": {
            "alpha": {"required_status_checks": {"strict": True, "contexts": ["lint"]}},
            "beta": {
                "_note": "ignored",
                "required_status_checks": None,
            },
        },
    }


class TestLoadManifest(unittest.TestCase):
    def test_load_real_manifest(self) -> None:
        manifest = abp.load_manifest(abp.DEFAULT_MANIFEST)
        self.assertIn("_common", manifest)
        self.assertIn("repos", manifest)
        # All 7 child repos plus noorinalabs-main = 8.
        self.assertEqual(len(manifest["repos"]), 8)
        for key in ("noorinalabs-main", "noorinalabs-isnad-graph", "noorinalabs-deploy"):
            self.assertIn(key, manifest["repos"])

    def test_missing_file(self) -> None:
        with self.assertRaises(abp.BranchProtectionError):
            abp.load_manifest(Path("/tmp/nonexistent-manifest-abp.json"))

    def test_malformed_json(self, tmp_path: Path | None = None) -> None:
        # write to /tmp directly (Hook 15 allow-listed)
        p = Path("/tmp/abp_malformed.json")
        p.write_text("{not json")
        with self.assertRaises(abp.BranchProtectionError):
            abp.load_manifest(p)

    def test_missing_required_top_level_keys(self) -> None:
        p = Path("/tmp/abp_missing.json")
        p.write_text(json.dumps({"_common": {}}))
        with self.assertRaises(abp.BranchProtectionError):
            abp.load_manifest(p)


class TestBuildDesired(unittest.TestCase):
    def test_per_repo_overrides_merge_into_common(self) -> None:
        m = _minimal_manifest()
        desired = abp.build_desired_for_repo(m, "alpha")
        self.assertEqual(
            desired["required_status_checks"],
            {"strict": True, "contexts": ["lint"]},
        )
        self.assertFalse(desired["enforce_admins"])
        self.assertFalse(desired["allow_force_pushes"])

    def test_comment_keys_stripped(self) -> None:
        m = _minimal_manifest()
        desired = abp.build_desired_for_repo(m, "beta")
        # _note must not be present
        for k in desired:
            self.assertFalse(k.startswith("_"))

    def test_unknown_repo_errors(self) -> None:
        with self.assertRaises(abp.BranchProtectionError):
            abp.build_desired_for_repo(_minimal_manifest(), "gamma")

    def test_required_keys_all_present_in_output(self) -> None:
        m = _minimal_manifest()
        desired = abp.build_desired_for_repo(m, "alpha")
        for key in abp._REQUIRED_PUT_KEYS:
            self.assertIn(key, desired)

    def test_missing_required_key_errors(self) -> None:
        m = _minimal_manifest()
        del m["_common"]["allow_deletions"]
        with self.assertRaises(abp.BranchProtectionError):
            abp.build_desired_for_repo(m, "alpha")


class TestNormalizeActual(unittest.TestCase):
    def test_none_actual(self) -> None:
        norm = abp.normalize_actual(None)
        for key in abp._REQUIRED_PUT_KEYS:
            self.assertIsNone(norm[key])

    def test_full_actual(self) -> None:
        actual = {
            "required_status_checks": {
                "strict": True,
                "contexts": ["x", "y"],
                "checks": [{"context": "x", "app_id": 1}],
                "url": "https://api.example/...",
            },
            "enforce_admins": {"enabled": False},
            "allow_force_pushes": {"enabled": False},
            "allow_deletions": {"enabled": False},
            "required_linear_history": {"enabled": False},
            "required_conversation_resolution": {"enabled": False},
            "required_pull_request_reviews": None,
            "restrictions": None,
        }
        norm = abp.normalize_actual(actual)
        self.assertEqual(
            norm["required_status_checks"],
            {"strict": True, "contexts": ["x", "y"]},
        )
        self.assertFalse(norm["enforce_admins"])
        self.assertFalse(norm["allow_force_pushes"])
        self.assertIsNone(norm["required_pull_request_reviews"])

    def test_legacy_bool_shape(self) -> None:
        # Some older GET responses return `enforce_admins: true/false` directly.
        actual = {
            "required_status_checks": None,
            "enforce_admins": True,
            "allow_force_pushes": False,
            "allow_deletions": False,
            "required_linear_history": False,
            "required_conversation_resolution": False,
            "required_pull_request_reviews": None,
            "restrictions": None,
        }
        norm = abp.normalize_actual(actual)
        self.assertTrue(norm["enforce_admins"])
        self.assertFalse(norm["allow_force_pushes"])

    def test_required_pull_request_reviews_strips_get_only_fields(self) -> None:
        # GET wraps RPR with `url` and may carry extra keys; normalize must
        # strip them so the diff matches a PUT-shape desired body.
        actual = {
            "required_status_checks": None,
            "enforce_admins": True,
            "allow_force_pushes": False,
            "allow_deletions": False,
            "required_linear_history": False,
            "required_conversation_resolution": False,
            "required_pull_request_reviews": {
                "url": "https://api.github.com/repos/x/y/branches/main/protection/required_pull_request_reviews",
                "dismiss_stale_reviews": True,
                "require_code_owner_reviews": False,
                "required_approving_review_count": 2,
                "require_last_push_approval": False,
                "dismissal_restrictions": {},
            },
            "restrictions": None,
        }
        norm = abp.normalize_actual(actual)
        self.assertEqual(
            norm["required_pull_request_reviews"],
            {
                "required_approving_review_count": 2,
                "dismiss_stale_reviews": True,
                "require_code_owner_reviews": False,
                "require_last_push_approval": False,
            },
        )


class TestDiffState(unittest.TestCase):
    def test_in_sync(self) -> None:
        desired = {
            "required_status_checks": {"strict": True, "contexts": ["lint"]},
            "enforce_admins": False,
            "required_pull_request_reviews": None,
            "restrictions": None,
            "allow_force_pushes": False,
            "allow_deletions": False,
            "required_linear_history": False,
            "required_conversation_resolution": False,
        }
        actual_norm = dict(desired)
        self.assertEqual(abp.diff_state(desired, actual_norm), [])

    def test_drift_on_contexts(self) -> None:
        desired = {
            "required_status_checks": {"strict": True, "contexts": ["lint", "test"]},
            "enforce_admins": False,
            "required_pull_request_reviews": None,
            "restrictions": None,
            "allow_force_pushes": False,
            "allow_deletions": False,
            "required_linear_history": False,
            "required_conversation_resolution": False,
        }
        actual_norm = dict(desired)
        actual_norm["required_status_checks"] = {"strict": True, "contexts": ["lint"]}
        drift = abp.diff_state(desired, actual_norm)
        self.assertEqual(len(drift), 1)
        self.assertIn("required_status_checks", drift[0])

    def test_drift_on_negative_protection(self) -> None:
        desired: dict = {k: False for k in abp._REQUIRED_PUT_KEYS}
        desired["required_status_checks"] = None
        desired["required_pull_request_reviews"] = None
        desired["restrictions"] = None
        actual_norm = dict(desired)
        actual_norm["allow_force_pushes"] = True
        drift = abp.diff_state(desired, actual_norm)
        self.assertEqual(len(drift), 1)
        self.assertIn("allow_force_pushes", drift[0])


class TestFetchActual(unittest.TestCase):
    def test_unprotected_returns_none(self) -> None:
        with mock.patch.object(abp, "subprocess") as sp:
            sp.run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=1,
                stdout="",
                stderr='{"message":"Branch not protected","status":"404"}',
            )
            self.assertIsNone(abp.fetch_actual("noorinalabs", "x"))

    def test_protected_returns_payload(self) -> None:
        payload = {"required_status_checks": {"strict": True, "contexts": []}}
        with mock.patch.object(abp, "subprocess") as sp:
            sp.run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=json.dumps(payload),
                stderr="",
            )
            self.assertEqual(abp.fetch_actual("noorinalabs", "x"), payload)

    def test_other_failure_raises(self) -> None:
        with mock.patch.object(abp, "subprocess") as sp:
            sp.run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=1,
                stdout="",
                stderr="permission denied",
            )
            with self.assertRaises(abp.BranchProtectionError):
                abp.fetch_actual("noorinalabs", "x")


class TestPutProtection(unittest.TestCase):
    def test_put_sends_full_body(self) -> None:
        body = {"x": 1}
        captured = {}

        def fake_run(args, input=None, capture_output=None, text=None):
            captured["args"] = args
            captured["input"] = input
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="{}", stderr="")

        with mock.patch.object(abp.subprocess, "run", side_effect=fake_run):
            abp.put_protection("noorinalabs", "x", body)
        self.assertIn("-X", captured["args"])
        self.assertIn("PUT", captured["args"])
        self.assertIn("--input", captured["args"])
        self.assertEqual(json.loads(captured["input"]), body)

    def test_put_failure_raises(self) -> None:
        with mock.patch.object(abp.subprocess, "run") as run:
            run.return_value = subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr="boom"
            )
            with self.assertRaises(abp.BranchProtectionError):
                abp.put_protection("noorinalabs", "x", {})


class TestRunCheck(unittest.TestCase):
    def test_check_in_sync(self) -> None:
        m = _minimal_manifest()
        with mock.patch.object(abp, "fetch_actual") as fa:
            # Build a fake actual matching the desired.
            fa.side_effect = [
                {
                    "required_status_checks": {"strict": True, "contexts": ["lint"]},
                    "enforce_admins": {"enabled": False},
                    "allow_force_pushes": {"enabled": False},
                    "allow_deletions": {"enabled": False},
                    "required_linear_history": {"enabled": False},
                    "required_conversation_resolution": {"enabled": False},
                    "required_pull_request_reviews": None,
                    "restrictions": None,
                },
                None,  # beta is unprotected — manifest says None for rsc and
                # False for negative protections, but None != False:
            ]
            # Wait: beta's manifest has required_status_checks=None AND
            # enforce_admins=False. If actual is None, normalize_actual yields
            # all-None which does NOT equal {enforce_admins: False, ...}. So
            # beta SHOULD drift. Test that.
            rc = abp.run_check("noorinalabs", m, ["alpha", "beta"])
        self.assertEqual(rc, 1)  # beta drifts

    def test_check_returns_zero_when_all_synced(self) -> None:
        m = _minimal_manifest()
        # Make alpha and beta both reflect the desired state.
        alpha_actual = {
            "required_status_checks": {"strict": True, "contexts": ["lint"]},
            "enforce_admins": {"enabled": False},
            "allow_force_pushes": {"enabled": False},
            "allow_deletions": {"enabled": False},
            "required_linear_history": {"enabled": False},
            "required_conversation_resolution": {"enabled": False},
            "required_pull_request_reviews": None,
            "restrictions": None,
        }
        beta_actual = dict(alpha_actual)
        beta_actual["required_status_checks"] = None
        with mock.patch.object(abp, "fetch_actual", side_effect=[alpha_actual, beta_actual]):
            rc = abp.run_check("noorinalabs", m, ["alpha", "beta"])
        self.assertEqual(rc, 0)


class TestMainCli(unittest.TestCase):
    def test_check_requires_exactly_one_mode(self) -> None:
        with self.assertRaises(SystemExit):
            abp.parse_args([])  # neither --check nor --apply

    def test_repo_flag_limits_scope(self) -> None:
        m = _minimal_manifest()
        manifest_path = Path("/tmp/abp_main_test.json")
        manifest_path.write_text(json.dumps(m))
        with mock.patch.object(abp, "fetch_actual") as fa:
            fa.return_value = None
            rc = abp.main(["--check", "--manifest", str(manifest_path), "--repo", "alpha"])
            self.assertEqual(fa.call_count, 1)
        # alpha's manifest is rsc={strict,contexts:[lint]} but actual is None
        # → drift → rc 1.
        self.assertEqual(rc, 1)


class TestRealManifestSchema(unittest.TestCase):
    """Schema checks for the real manifest shipped in this PR."""

    def setUp(self) -> None:
        self.manifest = abp.load_manifest(abp.DEFAULT_MANIFEST)

    def test_seven_unprotected_repos_present(self) -> None:
        # The seven unprotected (from #403 verification) + isnad-graph.
        expected = {
            "noorinalabs-main",
            "noorinalabs-isnad-graph",
            "noorinalabs-user-service",
            "noorinalabs-deploy",
            "noorinalabs-design-system",
            "noorinalabs-landing-page",
            "noorinalabs-data-acquisition",
            "noorinalabs-isnad-ingest-platform",
        }
        self.assertEqual(set(self.manifest["repos"].keys()), expected)

    def test_main_contexts_match_workflow_job_names(self) -> None:
        # Verified against noorinalabs-main/.github/workflows/ci.yml job `name:` fields.
        desired = abp.build_desired_for_repo(self.manifest, "noorinalabs-main")
        ctx = desired["required_status_checks"]["contexts"]
        self.assertEqual(
            set(ctx),
            {
                "Ruff lint",
                "Ruff format check",
                "Mypy type check",
                "Smoke test — hooks compile and exit cleanly",
            },
        )

    def test_negative_protections_uniform(self) -> None:
        for repo_name in self.manifest["repos"]:
            desired = abp.build_desired_for_repo(self.manifest, repo_name)
            self.assertFalse(desired["allow_force_pushes"], repo_name)
            self.assertFalse(desired["allow_deletions"], repo_name)

    def test_enforce_admins_uniform_true(self) -> None:
        for repo_name in self.manifest["repos"]:
            desired = abp.build_desired_for_repo(self.manifest, repo_name)
            self.assertTrue(desired["enforce_admins"], repo_name)

    def test_required_pull_request_reviews_uniform(self) -> None:
        for repo_name in self.manifest["repos"]:
            desired = abp.build_desired_for_repo(self.manifest, repo_name)
            rpr = desired["required_pull_request_reviews"]
            self.assertIsNotNone(rpr, repo_name)
            self.assertEqual(rpr["required_approving_review_count"], 2, repo_name)
            self.assertTrue(rpr["dismiss_stale_reviews"], repo_name)
            self.assertFalse(rpr["require_code_owner_reviews"], repo_name)
            self.assertFalse(rpr["require_last_push_approval"], repo_name)


if __name__ == "__main__":
    unittest.main()
