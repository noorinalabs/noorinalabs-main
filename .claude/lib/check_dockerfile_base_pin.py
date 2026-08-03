#!/usr/bin/env python3
"""Lint Dockerfile `FROM` statements for digest-pin + distro-upgrade compliance.

Deterministic conversion of `.claude/team/charter/tech-decisions.md § Base Image
Pinning` (noorinalabs-main#735, the charter-prose-inventory worklist item #4 /
epic #726). The section requires every `FROM` to use a **digest-pinned tag**
(`image:tag@sha256:<digest>`) **combined with an in-image package upgrade**, to
close the two failure modes it names — floating-tag drift and within-tag package
drift (the shape isnad-graph#853 hit).

What this gate enforces (verbatim from the section's distro table)
================================================================
For every `FROM` that is not exempt:

1. The image reference MUST carry an `@sha256:` digest pin.
1a. The digest VALUE must be well-formed — `sha256:` followed by exactly 64
    lowercase hex characters (noorinalabs-main#1204). Shape-only checking let
    `@sha256:deadbeef` and `@sha256:` through the gate.
1b. The registry host the reference resolves to must be in the allowed set
    (see "Registry allowlist" below) — also #1204.
2. The stage MUST run the package-manager upgrade matching the base distro:

   | Family      | Pin shape               | Upgrade command                                 |
   |-------------|-------------------------|-------------------------------------------------|
   | Alpine      | image:tag@sha256:digest | `RUN apk upgrade --no-cache`                    |
   | Debian-slim | image:tag@sha256:digest | `apt-get update && apt-get -y upgrade && clean` |
   | Distroless  | image:tag@sha256:digest | none — no package manager (pinned-only is fine) |

   The distro family is inferred from the image name: `alpine` → Alpine,
   `distroless` → Distroless (no upgrade required), otherwise the glibc/Debian
   default (an apt upgrade is required). A genuinely-other base that has no
   package manager should carry the `# RATIONALE:` exemption below.

Exemptions honored (verbatim from the section)
=============================================
- **`scratch`** final/any layer — no package manager; the upstream stages that
  produced its contents still follow the rule and are checked on their own
  `FROM`.
- **Distroless** — pinned-only is sufficient (no package manager); the digest
  pin is still required.
- **Multi-stage stage reference** — a `FROM <earlier-stage>` inherits the
  upstream stage's pin, so it is not re-checked (the named stage was checked at
  its defining `FROM`).
- **Vendor images** documented with an inline `# RATIONALE:` comment on the
  `FROM` line (or the comment line immediately above it). This remains the full
  escape hatch: a RATIONALE-documented `FROM` skips *every* rule below,
  including the digest-value and registry rules, because the exemption is
  visible and reviewed in the diff.

Registry allowlist — what "expected registry" means (#1204)
==========================================================
There is no single expected hostname to hardcode: this file is an org-wide
template vendored into every child repo, and a repo may legitimately pull a base
image from a registry another repo never touches. "Expected" is therefore a
**declared policy set**, layered, with the narrow/loud default the org's
standing stance on classifier defaults requires (unknown ⇒ narrow ⇒ loud exit-1):

1. `DEFAULT_ALLOWED_REGISTRIES` — the built-in org floor below. Every entry is
   evidence-grounded (see the per-entry comments); a registry that no repo pulls
   a base image from is deliberately NOT here.
2. `--allow-registry HOST` (repeatable) — a per-repo extension, declared in that
   repo's `.pre-commit-config.yaml` `args:` and its CI step, so the widening is
   itself a reviewed, diffable line rather than a silent default.
3. `# RATIONALE:` on the `FROM` — the per-statement escape hatch.

Anything outside (1) ∪ (2), not covered by (3), is a violation. A legitimate but
unanticipated registry therefore FAILS LOUDLY with a message naming the flag —
it is never silently permitted. Two deliberate non-widenings:

- **No alias canonicalization.** `index.docker.io` / `registry-1.docker.io` are
  not silently folded into `docker.io`; a ref naming a different literal host
  must be allowlisted explicitly.
- **Ports are part of the host.** `registry.example.com:5000` must be
  allowlisted with its port; the bare hostname does not cover it.

A reference whose registry component is a build-arg/variable (`FROM
${REGISTRY}/img@sha256:...`) is not statically determinable and is flagged
rather than assumed to be Docker Hub.

CLI
===
    python3 .claude/lib/check_dockerfile_base_pin.py [--allow-registry HOST]... \
        <Dockerfile> [<Dockerfile> ...]

Exit codes:
    0 — every FROM in every file is compliant (or exempt)
    1 — at least one violation (each printed as `path:line: FROM <image> — <why>`)
    2 — usage / unknown-flag / file-not-found error

This is a reusable template (same CLI/exit-code shape as
`.claude/lib/pre_commit_ci_sync.py`) so it wires identically into a repo's
pre-commit config and its CI. The parent repo `noorinalabs-main` ships no
Dockerfiles itself; the cross-repo rollout that points this at each child's
Dockerfiles is a #735 follow-up.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterable
from pathlib import Path

# --- Digest value (#1204) ---------------------------------------------------
# An OCI content digest is `sha256:` + exactly 64 LOWERCASE hex characters. The
# registry spec's grammar is lowercase-only, so uppercase hex is rejected rather
# than normalized — a ref Docker itself would refuse must not pass the lint.
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

# --- Registry host (#1204) --------------------------------------------------
# A ref with no explicit registry component resolves to Docker Hub. This is the
# host such a ref is checked against; it is NOT an alias table (see the module
# docstring — `index.docker.io` is a different literal host and must be
# allowlisted on its own).
_IMPLICIT_REGISTRY = "docker.io"

# The org floor. Narrow by construction: each entry is a registry some repo in
# this org actually pulls a base image from, or that the charter's own distro
# table names. A registry used only for `image:` refs in compose (e.g.
# `quay.io/prometheuscommunity/postgres-exporter`) is NOT here — this gate reads
# `FROM` lines, and widening the default on non-evidence is the same defect as
# permitting `evil.example.com`. Repos that legitimately need more declare it
# with `--allow-registry`.
DEFAULT_ALLOWED_REGISTRIES: frozenset[str] = frozenset(
    {
        # Every real base image across all seven repos is an un-prefixed Docker
        # Hub ref (python:*-slim, node:*-alpine, nginx:*-alpine, neo4j, ubuntu).
        _IMPLICIT_REGISTRY,
        # The org's own registry — every child repo publishes to it via its
        # `ghcr-publish.yml`, so a `FROM ghcr.io/noorinalabs/...` base built by
        # us is an anticipated pattern.
        "ghcr.io",
        # Distroless is a family the charter's own distro table names as
        # supported, and it is published only under `gcr.io/distroless/...`.
        "gcr.io",
    }
)

# A `$VAR` / `${VAR}` occurrence — used only against the registry component, to
# tell "statically Docker Hub" apart from "we cannot know".
_VARIABLE_RE = re.compile(r"\$\{?\w")

# `FROM` is the only keyword we parse; Dockerfile keywords are case-insensitive.
_FROM_RE = re.compile(r"^\s*FROM\s+(?P<rest>\S.*?)\s*$", re.IGNORECASE)
# A leading `--platform=...` flag precedes the image and must be stripped.
_PLATFORM_RE = re.compile(r"^--platform=\S+\s+", re.IGNORECASE)
# A trailing `AS <stage>` names the build stage.
_AS_RE = re.compile(r"\s+AS\s+(?P<stage>\S+)\s*$", re.IGNORECASE)

# Upgrade-command signatures per distro family (searched over the stage body).
_ALPINE_UPGRADE_RE = re.compile(r"\bapk\s+upgrade\b", re.IGNORECASE)
# `apt-get update && apt-get -y upgrade` / `apt upgrade` — an apt invocation
# followed (in the same command segment) by `upgrade`. `apt-get update` alone
# does NOT match (that is "update", not "upgrade").
_DEBIAN_UPGRADE_RE = re.compile(r"\bapt(?:-get)?\s+(?:-{1,2}\S+\s+)*upgrade\b", re.IGNORECASE)

_RATIONALE_RE = re.compile(r"#\s*RATIONALE:", re.IGNORECASE)


class FromStatement:
    """One parsed `FROM` line: its image ref, optional stage name, exemptions."""

    def __init__(self, lineno: int, image: str, stage: str | None, has_rationale: bool) -> None:
        self.lineno = lineno
        self.image = image
        self.stage = stage
        self.has_rationale = has_rationale


def _preceding_comment_has_rationale(lines: list[str], from_idx: int) -> bool:
    """True if the comment line(s) immediately above `from_idx` carry RATIONALE."""
    j = from_idx - 1
    while j >= 0:
        stripped = lines[j].strip()
        if stripped == "":
            j -= 1
            continue
        if stripped.startswith("#"):
            return bool(_RATIONALE_RE.search(stripped))
        return False
    return False


def parse_froms(text: str) -> list[FromStatement]:
    """Parse every `FROM` statement in a Dockerfile, in source order."""
    lines = text.splitlines()
    froms: list[FromStatement] = []
    for idx, raw in enumerate(lines):
        m = _FROM_RE.match(raw)
        if not m:
            continue
        rest = m.group("rest")
        has_rationale = bool(_RATIONALE_RE.search(raw)) or _preceding_comment_has_rationale(
            lines, idx
        )
        # Drop any trailing inline comment, then a leading --platform flag.
        code = rest.split("#", 1)[0].strip()
        code = _PLATFORM_RE.sub("", code).strip()
        stage: str | None = None
        as_m = _AS_RE.search(code)
        if as_m is not None:
            stage = as_m.group("stage")
            code = code[: as_m.start()].strip()
        image = code.split()[0] if code.split() else ""
        froms.append(FromStatement(idx + 1, image, stage, has_rationale))
    return froms


def digest_of(image: str) -> str | None:
    """Return the digest component of an image ref, or None if it carries none.

    Everything after the FIRST `@` is the digest, so a ref with a stray second
    `@` yields a value that fails `_DIGEST_RE` rather than being silently
    truncated to a well-formed prefix.
    """
    if "@" not in image:
        return None
    return image.split("@", 1)[1]


def registry_host(image: str) -> str | None:
    """Return the ref's explicit registry host, or None for implicit Docker Hub.

    Docker's own rule: the first `/`-separated component is a registry iff it
    contains a `.` or a `:`, or is exactly `localhost`. Otherwise it is a Hub
    namespace (`myorg/myimage`), and a ref with no `/` at all is a Hub library
    image (`python:3.14-slim`).
    """
    ref = image.split("@", 1)[0]
    if "/" not in ref:
        return None
    head = ref.split("/", 1)[0]
    if head == "localhost" or "." in head or ":" in head:
        return head
    return None


def _registry_component_is_variable(image: str) -> bool:
    """True if the ref has a registry component that is a build arg/variable.

    Only the component before the first `/` is inspected: a variable in the
    NAME or TAG (`FROM neo4j:${NEO4J_VERSION}`) leaves the registry statically
    known (Docker Hub), whereas `FROM ${REGISTRY}/img@sha256:...` does not.
    """
    ref = image.split("@", 1)[0]
    if "/" not in ref:
        return False
    return bool(_VARIABLE_RE.search(ref.split("/", 1)[0]))


def _stage_body(text: str, from_lineno: int, next_from_lineno: int | None) -> str:
    """Return the text between a `FROM` (exclusive) and the next `FROM`/EOF."""
    lines = text.splitlines()
    start = from_lineno  # from_lineno is 1-based; body starts on the next line
    end = (next_from_lineno - 1) if next_from_lineno is not None else len(lines)
    return "\n".join(lines[start:end])


def check_dockerfile_text(
    path: str,
    text: str,
    allowed_registries: Iterable[str] | None = None,
) -> list[str]:
    """Return a list of human-readable violation strings for one Dockerfile.

    `allowed_registries` defaults to `DEFAULT_ALLOWED_REGISTRIES`; callers pass
    the repo's declared set (default ∪ `--allow-registry` values).
    """
    allowed = {
        h.lower()
        for h in (DEFAULT_ALLOWED_REGISTRIES if allowed_registries is None else allowed_registries)
    }
    violations: list[str] = []
    froms = parse_froms(text)
    defined_stages: set[str] = set()
    for i, stmt in enumerate(froms):
        next_lineno = froms[i + 1].lineno if i + 1 < len(froms) else None
        image_l = stmt.image.lower()

        # Exemptions, in order. `scratch` and stage-references have no package
        # manager / inherit the upstream pin; a documented vendor RATIONALE opts
        # out explicitly. Record this stage's own name for later references.
        is_exempt = image_l == "scratch" or image_l in defined_stages or stmt.has_rationale
        if stmt.stage:
            defined_stages.add(stmt.stage.lower())
        if is_exempt:
            continue

        # Rule 1 — a digest pin is present, and (1a, #1204) its VALUE is a
        # well-formed sha256 content digest. Shape-only checking passed
        # `@sha256:deadbeef` and `@sha256:`.
        digest = digest_of(stmt.image)
        if digest is None:
            violations.append(
                f"{path}:{stmt.lineno}: FROM {stmt.image} — not digest-pinned "
                f"(require image:tag@sha256:<digest>)"
            )
        elif _DIGEST_RE.match(digest) is None:
            violations.append(
                f"{path}:{stmt.lineno}: FROM {stmt.image} — malformed digest "
                f"'{digest}' (require sha256: followed by exactly 64 lowercase "
                f"hex characters)"
            )

        # Rule 1b (#1204) — the ref must resolve to an allowed registry host.
        if _registry_component_is_variable(stmt.image):
            violations.append(
                f"{path}:{stmt.lineno}: FROM {stmt.image} — registry host is not "
                f"statically determinable (it is a build arg/variable); use a "
                f"literal registry host so the allowlist can be enforced"
            )
        else:
            host = registry_host(stmt.image) or _IMPLICIT_REGISTRY
            if host.lower() not in allowed:
                violations.append(
                    f"{path}:{stmt.lineno}: FROM {stmt.image} — registry "
                    f"'{host}' is not in the allowed set "
                    f"({', '.join(sorted(allowed))}); if this registry is "
                    f"legitimate for this repo, declare it with "
                    f"--allow-registry {host} in .pre-commit-config.yaml and CI"
                )

        body = _stage_body(text, stmt.lineno, next_lineno)
        if "distroless" in image_l:
            continue  # distroless has no package manager; pinned-only is sufficient
        if "alpine" in image_l:
            if not _ALPINE_UPGRADE_RE.search(body):
                violations.append(
                    f"{path}:{stmt.lineno}: FROM {stmt.image} — missing Alpine upgrade "
                    f"step (RUN apk upgrade --no-cache)"
                )
        elif not _DEBIAN_UPGRADE_RE.search(body):
            violations.append(
                f"{path}:{stmt.lineno}: FROM {stmt.image} — missing Debian upgrade step "
                f"(RUN apt-get update && apt-get -y upgrade && apt-get clean)"
            )
    return violations


def check_file(path: Path, allowed_registries: Iterable[str] | None = None) -> list[str]:
    return check_dockerfile_text(str(path), path.read_text(encoding="utf-8"), allowed_registries)


_USAGE = (
    "usage: check_dockerfile_base_pin.py [--allow-registry HOST]... <Dockerfile> [<Dockerfile> ...]"
)


def parse_args(argv: list[str]) -> tuple[list[str], set[str]] | None:
    """Split argv into (paths, allowed registries), or None on a usage error.

    Hand-rolled rather than argparse so `main` keeps returning its exit code
    instead of raising SystemExit. An unrecognized `--flag` is a usage error,
    never a path — a typo'd `--allow-registy` must not be silently swallowed
    into the file list and leave the default allowlist quietly in force.
    """
    paths: list[str] = []
    allowed = set(DEFAULT_ALLOWED_REGISTRIES)
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--allow-registry":
            if i + 1 >= len(argv):
                print("ERROR: --allow-registry requires a HOST argument", file=sys.stderr)
                return None
            allowed.add(argv[i + 1])
            i += 2
            continue
        if arg.startswith("--allow-registry="):
            value = arg.split("=", 1)[1]
            if not value:
                print("ERROR: --allow-registry requires a HOST argument", file=sys.stderr)
                return None
            allowed.add(value)
            i += 1
            continue
        if arg.startswith("-"):
            print(f"ERROR: unknown option: {arg}", file=sys.stderr)
            return None
        paths.append(arg)
        i += 1
    return paths, allowed


def main(argv: list[str]) -> int:
    parsed = parse_args(argv[1:])
    if parsed is None:
        print(_USAGE, file=sys.stderr)
        return 2
    paths, allowed = parsed
    if not paths:
        print(_USAGE, file=sys.stderr)
        return 2

    all_violations: list[str] = []
    for p in paths:
        path = Path(p)
        if not path.is_file():
            print(f"ERROR: not a file: {p}", file=sys.stderr)
            return 2
        all_violations.extend(check_file(path, allowed))

    if all_violations:
        print("Base Image Pinning violations (tech-decisions.md § Base Image Pinning, #735):")
        for v in all_violations:
            print(f"  {v}")
        print(
            "\nEvery FROM must be digest-pinned with a well-formed digest "
            "(image:tag@sha256:<64 lowercase hex>), resolve to an allowed registry "
            f"({', '.join(sorted(allowed))}), AND carry the matching distro upgrade "
            "(apk/apt). Exemptions: scratch, distroless (pin-only), a FROM that "
            "references an earlier stage, or a vendor image with an inline "
            "`# RATIONALE:` comment on the FROM line."
        )
        return 1

    print("OK: all Dockerfile FROM statements are digest-pinned with the required upgrade.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
