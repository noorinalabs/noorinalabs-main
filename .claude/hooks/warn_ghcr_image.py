#!/usr/bin/env python3
"""PreToolUse hook: Warn if GHCR image may not exist before deploy.

Warns (does not block) when `gh workflow run` triggers a deploy-related workflow
and the expected GHCR image might not exist.

Exit codes:
  0 — always allow (this is a warning-only hook)
"""

import json
import re
import subprocess
import sys

# Deploy-related workflow names/files
DEPLOY_PATTERNS = re.compile(
    r"deploy|release|cd[.-]|deliver", re.IGNORECASE
)

# Map of repo short names to GHCR image paths
REPO_IMAGE_MAP = {
    "noorinalabs-isnad-graph": "ghcr.io/noorinalabs/noorinalabs-isnad-graph",
    "noorinalabs-landing-page": "ghcr.io/noorinalabs/noorinalabs-landing-page",
    "noorinalabs-design-system": "ghcr.io/noorinalabs/noorinalabs-design-system",
    "noorinalabs-isnad-graph-ingestion": "ghcr.io/noorinalabs/noorinalabs-isnad-graph-ingestion",
}


def check_ghcr_image(image: str, tag: str = "latest") -> bool:
    """Check if a GHCR image exists via gh api."""
    # Extract org and package name from image path
    # ghcr.io/noorinalabs/noorinalabs-isnad-graph -> noorinalabs/noorinalabs-isnad-graph
    parts = image.replace("ghcr.io/", "").split("/")
    if len(parts) < 2:
        return True  # Can't determine — assume exists

    org = parts[0]
    package = parts[1]

    try:
        result = subprocess.run(
            [
                "gh", "api",
                f"orgs/{org}/packages/container/{package}/versions",
                "--jq", ".[0].metadata.container.tags[]",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            return True  # API error — don't warn on transient failures
        tags = result.stdout.strip().splitlines()
        return tag in tags or len(tags) > 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return True


def extract_repo_from_command(command: str) -> str | None:
    """Try to extract repo context from the workflow run command."""
    # Check for -R flag
    match = re.search(r"-R\s+[\"']?(\S+)[\"']?", command)
    if match:
        repo = match.group(1)
        # noorinalabs/noorinalabs-isnad-graph -> noorinalabs-isnad-graph
        if "/" in repo:
            return repo.split("/")[-1]
        return repo
    return None


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    if tool_name != "Bash":
        sys.exit(0)

    command = input_data.get("tool_input", {}).get("command", "")

    # Match gh workflow run
    if not re.search(r"\bgh\s+workflow\s+run\b", command):
        sys.exit(0)

    # Check if it's a deploy-related workflow
    if not DEPLOY_PATTERNS.search(command):
        sys.exit(0)

    repo = extract_repo_from_command(command)
    if not repo:
        # No repo context — generic warning
        result = {
            "decision": "allow",
            "systemMessage": (
                "WARNING: Triggering a deploy workflow. Verify the GHCR image "
                "exists before deploying. Run the service's build workflow first "
                "if the image hasn't been published."
            ),
        }
        print(json.dumps(result))
        sys.exit(0)

    image = REPO_IMAGE_MAP.get(repo)
    if not image:
        sys.exit(0)

    if not check_ghcr_image(image):
        result = {
            "decision": "allow",
            "systemMessage": (
                f"WARNING: GHCR image {image}:latest may not exist. "
                "The deploy may fail. Run the service's build workflow first.\n"
                f"Check: gh api orgs/noorinalabs/packages/container/{repo}/versions"
            ),
        }
        print(json.dumps(result))

    sys.exit(0)


if __name__ == "__main__":
    main()
