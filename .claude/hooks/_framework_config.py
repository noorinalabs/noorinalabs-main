#!/usr/bin/env python3
"""Shared config loader for framework hooks/libs.

The opinionated values that used to be hard-coded in the dispatchers (which
hook modules run, in what order) and elsewhere are read through this module
instead. The config lives at ``<repo>/.claude/framework.config.json``; this
loader finds it by walking up from the invocation cwd, parses it, and exposes a
dotted-path getter merged over the schema defaults.

Design contract
===============

- **Stdlib only.** No PyYAML / pydantic dependency — a hook must run in a
  freshly-pulled checkout with zero install step. Config is JSON for the same
  reason (``json`` is stdlib; YAML is not).
- **Fail-open to defaults.** A missing/unreadable/malformed config never raises
  and never blocks — :func:`config` returns the defaults so a hook degrades to
  its documented behaviour rather than crashing the tool call. Because
  ``_DEFAULTS`` carries the full hook lists, a config-less (or corrupt-config)
  checkout still dispatches every gate — the fail-open direction is "run the
  gates", never "silently drop them".
- **Defaults live here.** Dotted lookups fall back to ``_DEFAULTS`` when the
  loaded config omits a key. Keep ``_DEFAULTS['hooks']`` in sync with
  ``.claude/framework.config.json`` — the two are cross-checked by
  ``tests/test_hook_registration_coverage.py``.

Usage
=====

    from _framework_config import config
    cfg = config(input_data)                       # input_data optional
    if cfg.get("scm.allow_force", False): ...
    pre = cfg.get("hooks.pre_bash", [])

``config()`` caches per resolved config-file path, so repeated calls within one
hook invocation are cheap.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

CONFIG_FILENAME = "framework.config.json"

# Runtime shadow of ``.claude/framework.config.json``. Dotted lookups fall back
# here when the loaded config omits a key, and a config-less checkout runs on
# these values verbatim. Keep in sync with the committed config file.
#
# ``hooks.*`` — the ordered module lists the dispatchers run. A module named
# here MUST expose the dispatcher contract ``check(input_data) -> dict | None``;
# the dispatchers skip any module without it, so a non-conforming name is an
# inert entry that reads as enabled but never runs (issue #698). Hooks that only
# implement ``main()`` — session_start, session_handoff, validate_wave_context —
# are registered standalone in ``.claude/settings.json`` instead, and are
# deliberately absent here.
#
# ``pre_bash`` order matters: cheap/local checks first, network-calling checks
# last. In particular smart_grep_ontology routes a symbol-shaped rg/grep to the
# structural ontology BEFORE the block_bare_grep backstop (#1017), and
# block_squash_wave_merge runs LAST because it resolves a PR base via
# ``gh pr view`` (a network call, cheap-prefiltered on ``--squash``).
#
# A supplied ``hooks.*`` list REPLACES the default (see _deep_merge: lists are
# not merged) so a repo can disable a default hook by omitting it. The cost is
# that an omission is indistinguishable from an oversight —
# ``tests/test_hook_registration_coverage.py`` is the safety net that fails when
# a ``check()``-exposing hook ends up dispatched nowhere.
_DEFAULTS: dict[str, Any] = {
    "version": 1,
    "scm": {"provider": "github", "default_branch": "main", "allow_force": False},
    "branch": {
        "feature": "{FirstInitial}.{LastName}/{issue}-{slug}",
        "integration": "deployments/phase-{phase}/wave-{wave}",
    },
    "identity": {
        "enforce": True,
        "email_pattern": "parametrization+{First}.{Last}@gmail.com",
        "roster_source": ".claude/team/roster.json",
        "allow_emails": ["parametrization@gmail.com"],
    },
    "shell": "zsh",
    "hooks": {
        "pre_bash": [
            "validate_commit_identity",
            "block_no_verify",
            "smart_grep_ontology",
            "block_bare_grep",
            "block_git_config",
            "block_gh_pr_review",
            "block_stale_tmp_message_file",
            "no_worktree_self_delete",
            "validate_edit_completion",
            "auto_set_env_test",
            "validate_lockfile_paths",
            "validate_labels",
            "validate_wave_label_evidence",
            "validate_review_comment_format",
            "validate_pr_review",
            "validate_pr_ci_status",
            "validate_branch_freshness",
            "validate_workflow_paths_coverage",
            "validate_vps_host",
            "warn_ghcr_image",
            "warn_zsh_wordsplit",
            "block_squash_wave_merge",
        ],
        "post_bash": [
            "annunaki_monitor",
            "warn_pipe_mask_rc",
            "auto_sync_main",
            "auto_add_issue_to_board",
            "post_wave_kickoff_comment",
            "post_label_change_wave_field_sync",
        ],
        "post_file": [
            "ontology_tracker",
            "suggest_generic_prompt",
            "validate_edit_completion",
        ],
        "post_notebook": [
            "validate_edit_completion",
        ],
    },
}

# Cache: resolved-config-path -> merged dict. Keyed by path so different repos in
# one process (rare) don't collide; the None key caches "not found → defaults".
_CACHE: dict[str | None, dict[str, Any]] = {}


def _find_config_file(start: Path) -> Path | None:
    """Walk up from ``start`` looking for ``.claude/framework.config.json``."""
    cur = start.resolve()
    for d in (cur, *cur.parents):
        candidate = d / ".claude" / CONFIG_FILENAME
        if candidate.is_file():
            return candidate
    return None


def _deep_merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    """Return ``base`` deep-merged with ``over`` (over wins; dicts merge recursively).

    Lists are replaced wholesale, not concatenated — so a supplied ``hooks.*``
    list fully overrides the default, which is how a repo disables a hook.
    """
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _resolve_start_dir(input_data: dict | None) -> Path:
    """Best-effort cwd for the tool call."""
    if input_data:
        cwd = input_data.get("cwd")
        if isinstance(cwd, str) and cwd:
            return Path(cwd)
    return Path(os.getcwd())


class _Config:
    """Thin wrapper exposing :meth:`get` with dotted-path access over a merged dict."""

    __slots__ = ("_data", "path")

    def __init__(self, data: dict[str, Any], path: Path | None) -> None:
        self._data = data
        self.path = path

    def get(self, dotted: str, default: Any = None) -> Any:
        """Return the value at ``dotted`` (e.g. ``"hooks.pre_bash"``), or ``default``.

        ``default`` is returned only when the key is absent from BOTH the loaded
        config and ``_DEFAULTS`` — so callers can omit ``default`` for keys that
        always have a default, and pass one for genuinely-optional keys.
        """
        node: Any = self._data
        for part in dotted.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                return default
        return node

    def as_dict(self) -> dict[str, Any]:
        return dict(self._data)


def config(input_data: dict | None = None, *, start_dir: str | Path | None = None) -> _Config:
    """Load the framework config merged over defaults. Never raises.

    Resolution order for the config file: explicit ``start_dir`` →
    ``input_data["cwd"]`` → ``os.getcwd()``, walking up to the filesystem root.
    If no config file is found (or it is unreadable/invalid JSON), the pure
    defaults are returned.
    """
    start = Path(start_dir) if start_dir else _resolve_start_dir(input_data)
    path = _find_config_file(start)
    key = str(path) if path else None
    if key in _CACHE:
        return _Config(_CACHE[key], path)

    merged = dict(_DEFAULTS)
    if path is not None:
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                merged = _deep_merge(_DEFAULTS, loaded)
        except (OSError, json.JSONDecodeError, ValueError):
            merged = dict(_DEFAULTS)  # fail-open

    _CACHE[key] = merged
    return _Config(merged, path)


def clear_cache() -> None:
    """Drop the memoized config (tests that write a config mid-run call this)."""
    _CACHE.clear()
