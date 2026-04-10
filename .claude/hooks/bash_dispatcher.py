#!/usr/bin/env python3
"""Consolidated PreToolUse dispatcher for all Bash-matcher hooks.

Instead of spawning 12 separate Python processes per Bash command, this
single dispatcher routes the hook input to each validation function in
sequence. If any validation blocks, it short-circuits and returns the
block result. If all pass, it exits 0 (allow).

Exit codes:
  0 — allow (all validations passed)
  2 — block (a validation blocked the command)
"""

import importlib.util
import json
import os
import sys

# Directory containing individual hook scripts
HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))

# Hook modules to run, in order. Each module must have a main() function
# that reads from stdin and calls sys.exit(). We intercept stdin and
# sys.exit to run them in-process.
BASH_HOOKS = [
    "validate_commit_identity.py",
    "block_no_verify.py",
    "block_git_config.py",
    "auto_set_env_test.py",
    "validate_labels.py",
    "validate_lockfile_paths.py",
    "validate_pr_review.py",
    "validate_branch_freshness.py",
    "validate_vps_host.py",
    "warn_ghcr_image.py",
    "block_gh_pr_review.py",
    "validate_review_comment_format.py",
]


class HookExit(Exception):
    """Raised to intercept sys.exit() calls from hook modules."""

    def __init__(self, code: int = 0) -> None:
        self.code = code
        super().__init__(f"Hook exit: {code}")


def load_hook_module(filepath: str) -> object:
    """Dynamically load a hook Python module."""
    module_name = os.path.splitext(os.path.basename(filepath))[0]
    spec = importlib.util.spec_from_file_location(module_name, filepath)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_hook(hook_file: str, input_data: dict) -> tuple[int, str]:
    """Run a hook module's main() with the given input data.

    Returns (exit_code, stdout_output).
    """
    filepath = os.path.join(HOOKS_DIR, hook_file)
    if not os.path.exists(filepath):
        return 0, ""

    # Prepare stdin with the input data
    import io

    original_stdin = sys.stdin
    original_exit = sys.exit
    original_stdout = sys.stdout

    captured_output = io.StringIO()
    sys.stdin = io.StringIO(json.dumps(input_data))
    sys.stdout = captured_output

    exit_code = 0
    try:
        # Override sys.exit to capture the exit code
        def mock_exit(code: int = 0) -> None:
            raise HookExit(code)

        sys.exit = mock_exit  # type: ignore[assignment]

        module = load_hook_module(filepath)
        if module and hasattr(module, "main"):
            module.main()  # type: ignore[attr-defined]
    except HookExit as e:
        exit_code = e.code
    except Exception:
        # If a hook crashes, allow the command (fail-open)
        exit_code = 0
    finally:
        sys.stdin = original_stdin
        sys.exit = original_exit
        sys.stdout = original_stdout

    return exit_code, captured_output.getvalue()


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    # Verify this is a Bash tool call
    tool_name = input_data.get("tool_name", "")
    if tool_name != "Bash":
        sys.exit(0)

    # Run each hook in sequence
    for hook_file in BASH_HOOKS:
        exit_code, output = run_hook(hook_file, input_data)

        if exit_code == 2:
            # Hook blocked — output the block result and exit
            if output:
                print(output, end="")
            sys.exit(2)
        elif exit_code == 0 and output:
            # Hook allowed but has a message (e.g., warning)
            print(output, end="")

    # All hooks passed
    sys.exit(0)


if __name__ == "__main__":
    main()
