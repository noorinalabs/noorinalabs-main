"""Isolate temp-repo git tests from an inherited git environment (main#719).

Mirrors `.claude/lib/tests/conftest.py`. git exports `GIT_DIR`/
`GIT_WORK_TREE`/`GIT_INDEX_FILE` (and friends) into hook subprocesses —
notably the pre-push `pytest` hook. A test that builds a throwaway repo
and runs git against it via `git -C <tmp>` gets its working directory
overridden but NOT its `GIT_DIR`, so an inherited value silently redirects
the command at the parent repo instead of the tmp one.

As of #1116, `test_ontology_tracker.py` is the only file in this suite
that shells out real git commands against a constructed repo, and it
already protects itself via the hook module's own `_hermetic_git_env()`
helper at each call site — this fixture changes none of its outcomes
(verified: 2729 collected / passed, identical with and without a
simulated inherited `GIT_DIR`/`GIT_WORK_TREE`, before and after adding
this file). It is adopted here defensively, not correctively: the next
test that builds a tmp git repo without knowing about
`_hermetic_git_env()` gets the same hermetic guarantee `lib/tests/` gives
for free, instead of a footgun.
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _isolate_git_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("GIT_"):
            monkeypatch.delenv(key, raising=False)
