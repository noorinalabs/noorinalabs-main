"""Tests for check_dockerfile_base_pin — the Base Image Pinning gate (#735).

Verifies the deterministic conversion of `tech-decisions.md § Base Image
Pinning`: every FROM must be digest-pinned AND carry the matching distro
upgrade, with the section's exact exemptions (scratch, distroless, stage
references, vendor `# RATIONALE:`). Positive cases use the real required pattern
the section documents; negative cases use the exact prohibited shapes it names
(floating tag, pin-only, apk-only).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from check_dockerfile_base_pin import (  # noqa: E402
    DEFAULT_ALLOWED_REGISTRIES,
    check_dockerfile_text,
    digest_of,
    main,
    parse_args,
    parse_froms,
    registry_host,
)

# A well-formed digest: `sha256:` + exactly 64 lowercase hex characters.
#
# NOTE (#1204): this constant carried 65 hex characters until the digest-VALUE
# rule landed — a digest no registry would accept, undetected because the gate
# only checked for the `@sha256:` substring. The new rule flagged the test
# suite's own fixture. Kept charter-example-derived (`0272e460...`), corrected
# to the real 64-character length.
_DIGEST = "@sha256:0272e4609f1b5f3a2d8c9e1a4b6c8d0e2f4a6b8c0d2e4f6a8b0c2d4e6f8a0b2c"

# The real digest from the #1204 mutation corpus — the head of
# noorinalabs-deploy `integration-tests/fake_oauth/Dockerfile`.
_REAL_DIGEST = "@sha256:d3400aa122fa42cf0af0dbe8ec3091b047eac5c8f7e3539f7135e86d855dc015"

_APT_UPGRADE = "RUN apt-get update && apt-get -y upgrade && apt-get clean"


class CompliantFromsPass(unittest.TestCase):
    def test_alpine_pinned_with_apk_upgrade(self) -> None:
        df = f"""# Digest-pinned tag + apk upgrade for defense-in-depth
FROM nginx:stable-alpine3.23{_DIGEST}
RUN apk upgrade --no-cache
"""
        self.assertEqual(check_dockerfile_text("Dockerfile", df), [])

    def test_debian_slim_pinned_with_apt_upgrade(self) -> None:
        df = f"""FROM python:3.12-slim{_DIGEST}
RUN apt-get update && apt-get -y upgrade && apt-get clean && rm -rf /var/lib/apt/lists/*
"""
        self.assertEqual(check_dockerfile_text("Dockerfile", df), [])

    def test_distroless_pin_only_is_sufficient(self) -> None:
        # Distroless has no package manager — pinned-only passes, no upgrade.
        df = f"FROM gcr.io/distroless/static-debian12{_DIGEST}\n"
        self.assertEqual(check_dockerfile_text("Dockerfile", df), [])

    def test_multistage_scratch_final_layer_exempt(self) -> None:
        df = f"""FROM golang:1.22-alpine{_DIGEST} AS builder
RUN apk upgrade --no-cache
RUN go build -o /app

FROM scratch
COPY --from=builder /app /app
"""
        self.assertEqual(check_dockerfile_text("Dockerfile", df), [])

    def test_multistage_stage_reference_inherits_pin(self) -> None:
        # `FROM builder` references an earlier stage; it inherits the pin and is
        # not re-checked for a digest or an upgrade.
        df = f"""FROM python:3.12-slim{_DIGEST} AS builder
RUN apt-get update && apt-get -y upgrade && apt-get clean

FROM builder
RUN pip install .
"""
        self.assertEqual(check_dockerfile_text("Dockerfile", df), [])

    def test_vendor_rationale_inline_comment_exempts(self) -> None:
        df = "FROM vendor/proprietary:1.4  # RATIONALE: not redistributable digest-pinned\n"
        self.assertEqual(check_dockerfile_text("Dockerfile", df), [])

    def test_vendor_rationale_preceding_comment_exempts(self) -> None:
        df = """# RATIONALE: vendor image, not available as a digest-pinned ref
FROM vendor/proprietary:1.4
"""
        self.assertEqual(check_dockerfile_text("Dockerfile", df), [])

    def test_platform_flag_is_stripped(self) -> None:
        df = f"""FROM --platform=linux/amd64 node:20-alpine{_DIGEST}
RUN apk upgrade --no-cache
"""
        self.assertEqual(check_dockerfile_text("Dockerfile", df), [])


class ProhibitedShapesFlagged(unittest.TestCase):
    def test_floating_tag_flagged(self) -> None:
        # WRONG (floating tag): no digest, no upgrade — both defenses missing.
        violations = check_dockerfile_text("Dockerfile", "FROM nginx:alpine\n")
        self.assertEqual(len(violations), 2)
        self.assertTrue(any("not digest-pinned" in v for v in violations))
        self.assertTrue(any("Alpine upgrade" in v for v in violations))

    def test_pin_only_alpine_missing_upgrade(self) -> None:
        # INSUFFICIENT (pin-only): tag frozen but Alpine packages drift — the
        # exact shape isnad-graph#853 hit.
        df = f"FROM nginx:stable-alpine3.23{_DIGEST}\n"
        violations = check_dockerfile_text("Dockerfile", df)
        self.assertEqual(len(violations), 1)
        self.assertIn("missing Alpine upgrade", violations[0])

    def test_apk_only_missing_digest(self) -> None:
        # INSUFFICIENT (apk-only): upgrade present but base layer is unpinned.
        df = "FROM nginx:alpine\nRUN apk upgrade --no-cache\n"
        violations = check_dockerfile_text("Dockerfile", df)
        self.assertEqual(len(violations), 1)
        self.assertIn("not digest-pinned", violations[0])

    def test_debian_pinned_missing_apt_upgrade(self) -> None:
        df = f"FROM python:3.12-slim{_DIGEST}\nRUN pip install .\n"
        violations = check_dockerfile_text("Dockerfile", df)
        self.assertEqual(len(violations), 1)
        self.assertIn("missing Debian upgrade", violations[0])

    def test_apt_update_only_is_not_an_upgrade(self) -> None:
        # `apt-get update` is not `apt-get upgrade`; pin present, upgrade absent.
        df = f"FROM debian:bookworm-slim{_DIGEST}\nRUN apt-get update\n"
        violations = check_dockerfile_text("Dockerfile", df)
        self.assertEqual(len(violations), 1)
        self.assertIn("missing Debian upgrade", violations[0])

    def test_line_number_reported(self) -> None:
        df = """# header comment
FROM nginx:alpine
RUN apk upgrade --no-cache
"""
        violations = check_dockerfile_text("Dockerfile", df)
        self.assertEqual(len(violations), 1)
        self.assertIn("Dockerfile:2:", violations[0])


class MultiStageMixed(unittest.TestCase):
    def test_compliant_builder_but_bad_runtime_flags_only_runtime(self) -> None:
        df = f"""FROM golang:1.22-alpine{_DIGEST} AS builder
RUN apk upgrade --no-cache
RUN go build -o /app

FROM nginx:alpine
COPY --from=builder /app /app
"""
        violations = check_dockerfile_text("Dockerfile", df)
        # builder is clean; only the floating runtime FROM is flagged (pin+upgrade).
        self.assertEqual(len(violations), 2)
        self.assertTrue(all("FROM nginx:alpine" in v for v in violations))


class ParserBehavior(unittest.TestCase):
    def test_parse_collects_stage_names_and_images(self) -> None:
        df = f"""FROM python:3.12-slim{_DIGEST} AS builder
FROM scratch
"""
        froms = parse_froms(df)
        self.assertEqual(len(froms), 2)
        self.assertEqual(froms[0].stage, "builder")
        self.assertTrue(froms[0].image.startswith("python:3.12-slim@sha256:"))
        self.assertEqual(froms[1].image, "scratch")

    def test_from_keyword_case_insensitive(self) -> None:
        df = f"from nginx:alpine{_DIGEST} as web\nRUN apk upgrade --no-cache\n"
        self.assertEqual(check_dockerfile_text("Dockerfile", df), [])


class DigestValueValidated(unittest.TestCase):
    """#1204 item 1a — the digest VALUE, not just the `@sha256:` shape.

    Cases are the silent mutants from the issue's mutation table, run against
    the real head of noorinalabs-deploy `integration-tests/fake_oauth/Dockerfile`.
    """

    def test_short_hex_digest_is_malformed(self) -> None:
        # Mutant 4 from #1204: `@sha256:deadbeef` — 8 hex chars, was silent.
        df = f"FROM python:3.14-slim@sha256:deadbeef\n{_APT_UPGRADE}\n"
        violations = check_dockerfile_text("Dockerfile", df)
        self.assertEqual(len(violations), 1)
        self.assertIn("malformed digest", violations[0])
        self.assertIn("sha256:deadbeef", violations[0])

    def test_empty_digest_is_malformed(self) -> None:
        # Mutant 5 from #1204: `@sha256:` with no value — was silent.
        df = f"FROM python:3.14-slim@sha256:\n{_APT_UPGRADE}\n"
        violations = check_dockerfile_text("Dockerfile", df)
        self.assertEqual(len(violations), 1)
        self.assertIn("malformed digest", violations[0])

    def test_bare_at_with_no_algorithm_is_malformed(self) -> None:
        df = f"FROM python:3.14-slim@\n{_APT_UPGRADE}\n"
        violations = check_dockerfile_text("Dockerfile", df)
        self.assertEqual(len(violations), 1)
        self.assertIn("malformed digest", violations[0])

    def test_uppercase_hex_digest_is_malformed(self) -> None:
        # The registry grammar is lowercase-only; a ref Docker would refuse
        # must not pass the lint.
        df = f"FROM python:3.14-slim@sha256:{'A' * 64}\n{_APT_UPGRADE}\n"
        violations = check_dockerfile_text("Dockerfile", df)
        self.assertEqual(len(violations), 1)
        self.assertIn("malformed digest", violations[0])

    def test_sixty_three_hex_digest_is_malformed(self) -> None:
        # Off-by-one on the length: 63 hex chars, everything else well-formed.
        df = f"FROM python:3.14-slim@sha256:{'a' * 63}\n{_APT_UPGRADE}\n"
        violations = check_dockerfile_text("Dockerfile", df)
        self.assertEqual(len(violations), 1)
        self.assertIn("malformed digest", violations[0])

    def test_sixty_five_hex_digest_is_malformed(self) -> None:
        df = f"FROM python:3.14-slim@sha256:{'a' * 65}\n{_APT_UPGRADE}\n"
        violations = check_dockerfile_text("Dockerfile", df)
        self.assertEqual(len(violations), 1)
        self.assertIn("malformed digest", violations[0])

    def test_non_sha256_algorithm_is_malformed(self) -> None:
        df = f"FROM python:3.14-slim@sha512:{'a' * 64}\n{_APT_UPGRADE}\n"
        violations = check_dockerfile_text("Dockerfile", df)
        self.assertEqual(len(violations), 1)
        self.assertIn("malformed digest", violations[0])

    def test_second_at_sign_is_not_truncated_away(self) -> None:
        # Everything after the FIRST `@` is the digest, so a well-formed prefix
        # followed by junk still fails rather than matching a truncated head.
        df = f"FROM python:3.14-slim@sha256:{'a' * 64}@evil\n{_APT_UPGRADE}\n"
        violations = check_dockerfile_text("Dockerfile", df)
        self.assertEqual(len(violations), 1)
        self.assertIn("malformed digest", violations[0])

    def test_real_deploy_head_digest_passes(self) -> None:
        # Mutant 1 from #1204 (unmodified head) must still pass — the new rule
        # is not a blanket reject.
        df = f"FROM python:3.14-slim{_REAL_DIGEST}\n{_APT_UPGRADE}\n"
        self.assertEqual(check_dockerfile_text("Dockerfile", df), [])

    def test_missing_digest_keeps_the_not_pinned_message(self) -> None:
        # A ref with no `@` at all is still "not digest-pinned", not "malformed".
        violations = check_dockerfile_text("Dockerfile", "FROM nginx:alpine\n")
        self.assertTrue(any("not digest-pinned" in v for v in violations))
        self.assertFalse(any("malformed digest" in v for v in violations))

    def test_digest_of_helper(self) -> None:
        self.assertIsNone(digest_of("python:3.14-slim"))
        self.assertEqual(digest_of("python:3.14-slim@sha256:abc"), "sha256:abc")
        self.assertEqual(digest_of("python@sha256:a@b"), "sha256:a@b")


class KnownGapRollbackStillPasses(unittest.TestCase):
    """The #1204 scope boundary, asserted rather than only described in prose.

    Item 1 (this change) is no-network validation. Item 2 — forward-monotonicity
    via the images' config-blob `created` timestamps — needs registry access and
    is tracked separately. Mutant 6 of the #1204 table (a rollback to an older
    but perfectly well-formed digest on the expected registry) is therefore
    STILL not caught, and nothing here should be read as closing it.

    This test fails the day monotonicity lands, which is the point: it forces
    the follow-up to delete it consciously rather than leaving a stale claim.
    """

    def test_rollback_to_an_older_valid_digest_is_not_detected(self) -> None:
        # Both are real digests of python:3.14-slim from the deploy repo's
        # history; `older` predates `newer`. Statically they are indistinguishable.
        older = "@sha256:44dd04494ee8f3b538294360e7c4b3acb87c8268e4d0a4828a6500b1eff50061"
        newer = _REAL_DIGEST
        for digest in (older, newer):
            df = f"FROM python:3.14-slim{digest}\n{_APT_UPGRADE}\n"
            self.assertEqual(
                check_dockerfile_text("Dockerfile", df),
                [],
                "item 1 is no-network validation; digest ORDERING is item 2",
            )


class RegistryAllowlistEnforced(unittest.TestCase):
    """#1204 item 1b — the ref must resolve to a declared registry host."""

    def test_evil_registry_is_flagged(self) -> None:
        # Mutant 7 from #1204: registry swapped to evil.example.com with an
        # otherwise valid digest — was silent.
        df = f"FROM evil.example.com/python:3.14-slim{_REAL_DIGEST}\n{_APT_UPGRADE}\n"
        violations = check_dockerfile_text("Dockerfile", df)
        self.assertEqual(len(violations), 1)
        self.assertIn("registry 'evil.example.com' is not in the allowed set", violations[0])
        self.assertIn("--allow-registry evil.example.com", violations[0])

    def test_unprefixed_ref_is_implicit_docker_hub_and_allowed(self) -> None:
        df = f"FROM python:3.14-slim{_DIGEST}\n{_APT_UPGRADE}\n"
        self.assertEqual(check_dockerfile_text("Dockerfile", df), [])

    def test_docker_hub_user_namespace_is_not_a_registry(self) -> None:
        # `myorg/myimage` — the first component has no dot/colon, so it is a Hub
        # namespace, not a registry host.
        df = f"FROM myorg/myimage:1.0{_DIGEST}\n{_APT_UPGRADE}\n"
        self.assertEqual(check_dockerfile_text("Dockerfile", df), [])

    def test_ghcr_and_gcr_are_in_the_default_floor(self) -> None:
        df = f"FROM ghcr.io/noorinalabs/base:1.0{_DIGEST}\n{_APT_UPGRADE}\n"
        self.assertEqual(check_dockerfile_text("Dockerfile", df), [])
        self.assertEqual(
            check_dockerfile_text(
                "Dockerfile", f"FROM gcr.io/distroless/static-debian12{_DIGEST}\n"
            ),
            [],
        )

    def test_default_floor_is_narrow_not_a_catch_all(self) -> None:
        # The default must NOT quietly include registries the org only uses for
        # compose `image:` refs. quay.io is the live example.
        self.assertEqual(set(DEFAULT_ALLOWED_REGISTRIES), {"docker.io", "ghcr.io", "gcr.io"})
        df = f"FROM quay.io/prometheus/busybox:latest{_DIGEST}\n{_APT_UPGRADE}\n"
        violations = check_dockerfile_text("Dockerfile", df)
        self.assertEqual(len(violations), 1)
        self.assertIn("registry 'quay.io' is not in the allowed set", violations[0])

    def test_explicit_allowlist_extension_permits_the_registry(self) -> None:
        df = f"FROM quay.io/prometheus/busybox:latest{_DIGEST}\n{_APT_UPGRADE}\n"
        allowed = set(DEFAULT_ALLOWED_REGISTRIES) | {"quay.io"}
        self.assertEqual(check_dockerfile_text("Dockerfile", df, allowed), [])

    def test_docker_hub_alias_is_not_silently_canonicalized(self) -> None:
        # `index.docker.io` is a different literal host; folding it into
        # docker.io would be a silent widening.
        df = f"FROM index.docker.io/library/python:3.14-slim{_DIGEST}\n{_APT_UPGRADE}\n"
        violations = check_dockerfile_text("Dockerfile", df)
        self.assertEqual(len(violations), 1)
        self.assertIn("registry 'index.docker.io' is not in the allowed set", violations[0])

    def test_port_is_part_of_the_host(self) -> None:
        # Allowlisting the bare hostname must not cover a ported ref.
        df = f"FROM ghcr.io:5000/noorinalabs/base:1.0{_DIGEST}\n{_APT_UPGRADE}\n"
        violations = check_dockerfile_text("Dockerfile", df)
        self.assertEqual(len(violations), 1)
        self.assertIn("registry 'ghcr.io:5000' is not in the allowed set", violations[0])

    def test_localhost_registry_is_flagged(self) -> None:
        df = f"FROM localhost:5000/base:1.0{_DIGEST}\n{_APT_UPGRADE}\n"
        violations = check_dockerfile_text("Dockerfile", df)
        self.assertEqual(len(violations), 1)
        self.assertIn("registry 'localhost:5000' is not in the allowed set", violations[0])

    def test_variable_registry_component_is_flagged(self) -> None:
        # `${REGISTRY}` is not statically determinable — it must not be assumed
        # to be Docker Hub just because it carries no dot.
        df = f"FROM ${{REGISTRY}}/python:3.14-slim{_DIGEST}\n{_APT_UPGRADE}\n"
        violations = check_dockerfile_text("Dockerfile", df)
        self.assertEqual(len(violations), 1)
        self.assertIn("not statically determinable", violations[0])

    def test_variable_in_tag_only_is_not_a_registry_problem(self) -> None:
        # `FROM neo4j:${NEO4J_VERSION}` (a real child-repo shape): the registry
        # IS statically known (Docker Hub); only the pin rule should fire.
        violations = check_dockerfile_text("Dockerfile", "FROM neo4j:${NEO4J_VERSION}\n")
        self.assertFalse(any("statically determinable" in v for v in violations))
        self.assertTrue(any("not digest-pinned" in v for v in violations))

    def test_rationale_exemption_still_covers_the_registry_rule(self) -> None:
        # The documented, reviewed escape hatch remains total.
        df = (
            "# RATIONALE: vendor image, only published on the vendor registry\n"
            "FROM vendor.example.com/proprietary:1.4\n"
        )
        self.assertEqual(check_dockerfile_text("Dockerfile", df), [])

    def test_registry_host_helper(self) -> None:
        self.assertIsNone(registry_host("python:3.14-slim"))
        self.assertIsNone(registry_host("myorg/myimage:1.0"))
        self.assertEqual(registry_host("gcr.io/distroless/static"), "gcr.io")
        self.assertEqual(registry_host("localhost:5000/base"), "localhost:5000")
        self.assertEqual(registry_host("evil.example.com/x@sha256:abc"), "evil.example.com")


class CliBehavior(unittest.TestCase):
    def test_clean_file_exits_zero(self) -> None:
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".dockerfile", delete=False) as fh:
            fh.write(f"FROM nginx:stable-alpine3.23{_DIGEST}\nRUN apk upgrade --no-cache\n")
            name = fh.name
        try:
            self.assertEqual(main(["check_dockerfile_base_pin.py", name]), 0)
        finally:
            Path(name).unlink()

    def test_violating_file_exits_one(self) -> None:
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".dockerfile", delete=False) as fh:
            fh.write("FROM nginx:alpine\n")
            name = fh.name
        try:
            self.assertEqual(main(["check_dockerfile_base_pin.py", name]), 1)
        finally:
            Path(name).unlink()

    def test_no_args_is_usage_error(self) -> None:
        self.assertEqual(main(["check_dockerfile_base_pin.py"]), 2)

    def test_missing_file_is_error(self) -> None:
        self.assertEqual(main(["check_dockerfile_base_pin.py", "/no/such/Dockerfile"]), 2)

    def _write(self, body: str) -> str:
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".dockerfile", delete=False) as fh:
            fh.write(body)
            self.addCleanup(Path(fh.name).unlink)
            return fh.name

    def test_disallowed_registry_exits_one_by_default(self) -> None:
        name = self._write(f"FROM quay.io/prometheus/busybox:1.0{_DIGEST}\n{_APT_UPGRADE}\n")
        self.assertEqual(main(["check_dockerfile_base_pin.py", name]), 1)

    def test_allow_registry_flag_makes_it_pass(self) -> None:
        name = self._write(f"FROM quay.io/prometheus/busybox:1.0{_DIGEST}\n{_APT_UPGRADE}\n")
        self.assertEqual(
            main(["check_dockerfile_base_pin.py", "--allow-registry", "quay.io", name]), 0
        )

    def test_allow_registry_equals_form_makes_it_pass(self) -> None:
        name = self._write(f"FROM quay.io/prometheus/busybox:1.0{_DIGEST}\n{_APT_UPGRADE}\n")
        self.assertEqual(
            main(["check_dockerfile_base_pin.py", "--allow-registry=quay.io", name]), 0
        )

    def test_unknown_option_is_usage_error_not_a_path(self) -> None:
        # A typo'd flag must stop the run, never be silently skipped leaving the
        # default allowlist quietly in force. The `=` form is used deliberately:
        # with the separate-value form a fall-through would still exit 2 (the
        # orphaned "quay.io" fails the is-a-file check), so the test would pass
        # for the wrong reason and not detect the missing guard.
        name = self._write(f"FROM python:3.14-slim{_DIGEST}\n{_APT_UPGRADE}\n")
        self.assertEqual(main(["check_dockerfile_base_pin.py", "--allow-registy=quay.io", name]), 2)

    def test_allow_registry_without_value_is_usage_error(self) -> None:
        self.assertEqual(main(["check_dockerfile_base_pin.py", "--allow-registry"]), 2)

    def test_parse_args_defaults_to_the_org_floor(self) -> None:
        parsed = parse_args(["Dockerfile"])
        assert parsed is not None
        paths, allowed = parsed
        self.assertEqual(paths, ["Dockerfile"])
        self.assertEqual(allowed, set(DEFAULT_ALLOWED_REGISTRIES))

    def test_parse_args_extends_rather_than_replaces(self) -> None:
        parsed = parse_args(["--allow-registry", "quay.io", "Dockerfile"])
        assert parsed is not None
        _, allowed = parsed
        self.assertEqual(allowed, set(DEFAULT_ALLOWED_REGISTRIES) | {"quay.io"})

    def test_parse_args_rejects_unknown_flag(self) -> None:
        self.assertIsNone(parse_args(["--nope", "Dockerfile"]))


if __name__ == "__main__":
    unittest.main()
