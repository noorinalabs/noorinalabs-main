#!/usr/bin/env python3
"""PreToolUse hook: Verify cited file paths at origin before applying wave labels.

Three-occurrence W8 pattern (deploy#276, isnad-graph#866-870, audit-re-framing
#871): issue bodies assert artifact state X (file path) that is false at origin
head_sha at the time of wave-labeling. Manual review caught some; missed cases
consumed implementer-spawn cycles.

Per `feedback_enforcement_hierarchy.md` (hook > skill > charter), promote
from manager-discipline to PreToolUse hook.

Input Language:
  Fires on: PreToolUse Bash
  Matches:
    gh issue create [--repo R] ... --label '...p<N>-wave-<M>...'
    gh issue edit <NUM> [--repo R] ... --add-label '...p<N>-wave-<M>...'
  Does NOT match: gh issue list/view, gh label create, gh pr create.

Algorithm:
  1. Tokenize command via shlex.
  2. Detect wave-label application (regex `p\\d+-wave-\\d+` in any --label /
     --add-label value).
  3. Resolve issue body:
       - gh issue create: from --body, --body-file, or stdin (skip if neither)
       - gh issue edit:   from `gh api repos/{repo}/issues/{num} --jq .body`
  4. If body contains `Origin-Verification:` line → ALLOW (override).
  5. Else extract cited Python file paths via regex.
  6. If no cited paths → ALLOW (nothing to verify; pure-policy issue).
  7. For each cited path, check existence at:
       - origin/main:                  gh api .../contents/<path>?ref=main
       - origin/deployments/phase-<N>/wave-<M>: same but at wave branch
  8. If EVERY cited path 404s at BOTH refs → BLOCK with override directive.
  9. Else ALLOW (at least one path verified).

Override: include `Origin-Verification: <reason>` in issue body. The hook
performs a substring match — typical values: `Origin-Verification: <path>
exists at <ref>`, or `Origin-Verification: not-applicable` for policy issues.

Exit codes:
  0 — allow (not a wave-label command, no cited paths, override present, or
      at least one path verified)
  2 — block (wave-label command with cited paths and none verify at origin)
"""

import json
import os
import re
import shlex
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from annunaki_log import log_pretooluse_block  # noqa: E402

_WAVE_LABEL_RE = re.compile(r"p\d+-wave-\d+")
_PHASE_WAVE_RE = re.compile(r"p(\d+)-wave-(\d+)")

# Python paths in the .claude tree (hooks, skills, tests). Broad-enough to catch
# the W8 reproducer shape `noorinalabs-isnad-graph/.claude/hooks/<name>.py`
# AND child-repo source files. Tightening to specific subdirs avoids matching
# arbitrary `foo.py` mentions in prose.
_CITED_PATH_RE = re.compile(
    r"\b(?:noorinalabs-[a-z-]+/)?\.claude/[a-z][a-z0-9_/-]*\.py\b"
    r"|\bnoorinalabs-[a-z-]+/(?:src|tests)/[a-z][a-z0-9_/.-]*\.py\b"
)

_OVERRIDE_RE = re.compile(r"^Origin-Verification:\s*\S", re.MULTILINE)


def _tokenize(command: str) -> list[str] | None:
    try:
        return shlex.split(command, posix=True)
    except ValueError:
        return None


def _is_gh_issue_create(tokens: list[str]) -> bool:
    for i in range(len(tokens) - 2):
        if tokens[i] == "gh" and tokens[i + 1] == "issue" and tokens[i + 2] == "create":
            return True
    return False


def _is_gh_issue_edit(tokens: list[str]) -> tuple[bool, str | None]:
    """Detect `gh issue edit <NUM>` and return the issue number."""
    for i in range(len(tokens) - 3):
        if tokens[i] == "gh" and tokens[i + 1] == "issue" and tokens[i + 2] == "edit":
            num = tokens[i + 3]
            if num.isdigit():
                return True, num
    return False, None


def _walk_flag_values(tokens: list[str], wanted: set[str]) -> list[str]:
    """Collect values for any flag in `wanted`. Supports `--flag value` and
    `--flag=value`. Comma-separated values are split (gh's list-flag style)."""
    out: list[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in wanted and i + 1 < len(tokens):
            out.extend(p for p in tokens[i + 1].split(",") if p)
            i += 2
            continue
        matched = False
        for flag in wanted:
            if flag.startswith("--") and tok.startswith(flag + "="):
                out.extend(p for p in tok[len(flag) + 1 :].split(",") if p)
                matched = True
                break
        i += 1 if not matched else 1
    return out


def _walk_first_value(tokens: list[str], wanted: set[str]) -> str | None:
    """Return the FIRST value for any flag in `wanted` (single-value flags
    like --body or --body-file)."""
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in wanted and i + 1 < len(tokens):
            return tokens[i + 1]
        for flag in wanted:
            if flag.startswith("--") and tok.startswith(flag + "="):
                return tok[len(flag) + 1 :]
        i += 1
    return None


def _read_body_file(path: str) -> str | None:
    """Read body content from --body-file path. Returns None on any error."""
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def _resolve_issue_body_for_edit(issue_num: str, repo: str | None) -> str | None:
    """Fetch the issue body for `gh issue edit` matcher. None on any error."""
    args = ["gh", "issue", "view", issue_num, "--json", "body", "--jq", ".body"]
    if repo:
        args.extend(["--repo", repo])
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            return None
        return r.stdout
    except (subprocess.TimeoutExpired, OSError):
        return None


def _path_exists_at_ref(repo: str, path: str, ref: str) -> bool:
    """Check `gh api .../contents/<path>?ref=<ref>`. True if 200, False if 404."""
    args = [
        "gh",
        "api",
        f"repos/{repo}/contents/{path}",
        "-f",
        f"ref={ref}",
        "--silent",
    ]
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=10)
        return r.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def _extract_repo_for_path(path: str, default_repo: str) -> tuple[str, str]:
    """If path starts with `noorinalabs-X/`, that's the repo; rest is the
    in-repo path. Otherwise the path is in `default_repo`."""
    if path.startswith("noorinalabs-"):
        slash = path.find("/")
        if slash > 0:
            return path[:slash], path[slash + 1 :]
    if "/" in default_repo:
        return default_repo, path
    return f"noorinalabs/{default_repo}", path


def check(input_data: dict) -> dict | None:
    """Hook entrypoint. Returns None to allow, dict with block decision to block."""
    if input_data.get("tool_name") != "Bash":
        return None
    command = input_data.get("tool_input", {}).get("command", "")
    if not command:
        return None

    tokens = _tokenize(command)
    if tokens is None:
        return None

    is_create = _is_gh_issue_create(tokens)
    is_edit, issue_num = _is_gh_issue_edit(tokens)
    if not is_create and not is_edit:
        return None

    label_flag = {"--label", "-l"} if is_create else {"--add-label"}
    labels = _walk_flag_values(tokens, label_flag)
    wave_label = next(
        (lbl for lbl in labels if _WAVE_LABEL_RE.search(lbl)),
        None,
    )
    if not wave_label:
        return None

    repo_default = _walk_first_value(tokens, {"--repo", "-R"}) or ""

    # Resolve issue body
    body: str | None = None
    if is_create:
        body = _walk_first_value(tokens, {"--body"})
        if body is None:
            bf = _walk_first_value(tokens, {"--body-file", "-F"})
            if bf:
                body = _read_body_file(bf)
    elif is_edit and issue_num is not None:
        body = _resolve_issue_body_for_edit(issue_num, repo_default)

    if not body:
        return None  # Nothing to verify against

    # Override path
    if _OVERRIDE_RE.search(body):
        return None

    # Extract cited paths
    cited_paths = list(set(_CITED_PATH_RE.findall(body)))
    if not cited_paths:
        return None  # No paths to verify

    # Resolve wave branch ref
    pw = _PHASE_WAVE_RE.search(wave_label)
    phase_num, wave_num = pw.groups() if pw else (None, None)
    wave_branch = (
        f"deployments/phase-{phase_num}/wave-{wave_num}" if phase_num and wave_num else None
    )

    # Verify each cited path at origin
    unverified: list[str] = []
    for path in cited_paths:
        repo, inner_path = _extract_repo_for_path(path, repo_default)
        exists_at_main = _path_exists_at_ref(repo, inner_path, "main")
        exists_at_wave = (
            _path_exists_at_ref(repo, inner_path, wave_branch) if wave_branch else False
        )
        if not (exists_at_main or exists_at_wave):
            unverified.append(path)

    if unverified == cited_paths:
        # EVERY cited path 404'd at BOTH refs — block
        result = {
            "decision": "block",
            "reason": (
                f"BLOCKED: wave-label `{wave_label}` would be applied to an issue "
                f"whose body cites file paths that do NOT exist at origin.\n"
                f"Unverified paths (404 at both `main` and `{wave_branch}`):\n"
                + "\n".join(f"  - {p}" for p in unverified)
                + "\n\n"
                "Three-occurrence W8 pattern (deploy#276, isnad-graph#866-870, "
                "PR#871 stale-worktree) — issue body asserts state X, origin head_sha "
                "shows X doesn't exist. Manual review caught some; this hook catches "
                "the rest before implementer spawns are wasted.\n\n"
                "Fix-forward options:\n"
                "  (a) Verify the path EXISTS at origin and update the issue body to "
                "cite a real one; OR\n"
                "  (b) If the path is intentionally not-yet-existing (e.g., proposed "
                "new hook), add `Origin-Verification: not-applicable — <reason>` to "
                "the issue body; OR\n"
                "  (c) If the path exists at a non-standard ref, add\n"
                "      `Origin-Verification: <path> exists at <ref>` to the body.\n"
                "See main#337 for the rule + override path."
            ),
        }
        log_pretooluse_block("validate_wave_label_evidence", command, result["reason"])
        return result

    return None


if __name__ == "__main__":
    data = json.load(sys.stdin)
    result = check(data)
    if result is None:
        sys.exit(0)
    print(json.dumps(result))
    sys.exit(2 if result.get("decision") == "block" else 0)
